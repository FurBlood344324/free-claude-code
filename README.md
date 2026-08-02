# Free Claude Code

Claude Code'u kendi seçtiğin cloud veya local model sağlayıcısıyla çalıştırmak için
kullanılan kişisel bir local proxy.

Ana kullanım komutu:

```text
claude-code
```

Bu komut FCC server'ı gerektiğinde başlatır, Claude Code'u proxy üzerinden çalıştırır
ve son oturum kapandığında kendi başlattığı server'ı durdurur.

## Gereksinimler

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Claude Code
- Bir model sağlayıcısı ve gerekiyorsa API anahtarı

## Kurulum

### Linux

Repo klasöründen kurulum:

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

GitHub üzerinden doğrudan kurulum:

```bash
curl -fsSL "https://raw.githubusercontent.com/FurBlood344324/free-claude-code/main/scripts/install.sh" | sh
```

Sesli not desteği gerekiyorsa:

```bash
./scripts/install.sh --voice-nim
./scripts/install.sh --voice-local
./scripts/install.sh --voice-all
```

Kurulumdan sonra yeni terminal aç veya shell ortamını yenile:

```bash
source ~/.bashrc
```

### macOS

Repo klasöründen kurulum:

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

GitHub üzerinden doğrudan kurulum:

```bash
curl -fsSL "https://raw.githubusercontent.com/FurBlood344324/free-claude-code/main/scripts/install.sh" | sh
```

İsteğe bağlı ses desteği için Linux ile aynı `--voice-nim`, `--voice-local` veya
`--voice-all` seçeneklerini kullanabilirsin. Kurulumdan sonra yeni terminal aç;
macOS'ta **Free Claude Code** uygulaması menü çubuğundan da başlatılabilir.

### Windows PowerShell

Repo klasöründen kurulum:

```powershell
.\scripts\install.ps1
```

GitHub üzerinden doğrudan kurulum:

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/FurBlood344324/free-claude-code/main/scripts/install.ps1")))
```

Sesli not desteği gerekiyorsa:

```powershell
.\scripts\install.ps1 -VoiceNim
.\scripts\install.ps1 -VoiceLocal
.\scripts\install.ps1 -VoiceAll
```

Kurulumdan sonra yeni PowerShell aç. **Free Claude Code** Start menüsünden veya
masaüstü kısayolundan başlatılabilir.

Kurulumu önce değiştirmeden görmek için:

```bash
./scripts/install.sh --dry-run
```

```powershell
.\scripts\install.ps1 -DryRun
```

## Kullanım

Kurulumdan sonra doğrudan çalıştır:

```bash
claude-code
```

Claude Code argümanları normal şekilde aktarılır:

```bash
claude-code --resume <session-id>
claude-code --help
```

`claude-code`, upstream Claude Code komutunu (`claude`) FCC proxy'sine bağlayan
wrapper'dır. Manuel server yönetmek istersen:

```bash
fcc-server
fcc-claude
```

## İlk ayar

1. `claude-code` komutunu çalıştır.
2. Tarayıcıda açılan Admin UI'ı aç. Varsayılan adres:
   `http://127.0.0.1:8082/admin`
3. Kullanmak istediğin provider'ın API anahtarını gir.
4. `MODEL` alanından bir model seç.
5. **Validate**, ardından **Apply** düğmesine bas.
6. Claude Code'u yeniden başlat.

Varsayılan model:

```text
nvidia_nim/nvidia/nemotron-3-super-120b-a12b
```

Model formatı:

```text
provider/model
```

Örnekler:

```text
commandcode/deepseek-v4-flash
opencode/deepseek-v4-pro
opencode_go/minimax-m2.7
ollama/llama3.1
lmstudio/<local-model-id>
```

## Sık kullanılan provider ayarları

| Provider | Admin UI ayarı | Model örneği |
| --- | --- | --- |
| NVIDIA NIM | `NVIDIA_NIM_API_KEY` | `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` |
| CommandCode AI | `COMMANDCODE_API_KEY` | `commandcode/deepseek-v4-flash` |
| OpenCode Zen | `OPENCODE_API_KEY` | `opencode/deepseek-v4-pro` |
| OpenCode Go | `OPENCODE_API_KEY` | `opencode_go/minimax-m2.7` |
| OpenRouter | `OPENROUTER_API_KEY` | `open_router/openrouter/free` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/deepseek-chat` |
| Ollama | `OLLAMA_BASE_URL` | `ollama/llama3.1` |
| LM Studio | `LM_STUDIO_BASE_URL` | `lmstudio/<model-id>` |

Tüm ayarları görmek için [`.env.example`](.env.example) dosyasına bakabilirsin.

## Elle kurulum ve güncelleme

Projeyi klonladıktan sonra:

```bash
uv tool install --force --editable .
claude-code --help
```

Güncellemek için aynı komutu tekrar çalıştır:

```bash
uv tool install --force --editable .
```

## Sorun giderme

### `claude-code` bulunamıyor

Yeni terminal aç veya uv tool bin dizinini PATH'e ekle:

```bash
uv tool update-shell
```

### Claude Code giriş istiyor

`claude-code` komutunu kullan. Bu wrapper gerekli proxy ortam değişkenlerini otomatik
ayarlar; upstream `claude` komutunu doğrudan çalıştırma.

### Port kullanılıyor

FCC varsayılan olarak `8082` portunu kullanır. Portu kullanan process'i kontrol et:

Linux/macOS:

```bash
lsof -i :8082
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8082
```

### Server'ı elle başlatmak

```bash
fcc-server
```

Admin UI varsayılan olarak şurada açılır:

```text
http://127.0.0.1:8082/admin
```

## Kaldırma

### Linux/macOS

Repo klasöründe:

```bash
./scripts/uninstall.sh
```

Önce ne yapılacağını görmek için:

```bash
./scripts/uninstall.sh --dry-run
```

### Windows PowerShell

Repo klasöründe:

```powershell
.\scripts\uninstall.ps1
```

Önizleme için:

```powershell
.\scripts\uninstall.ps1 -DryRun
```

Kaldırma işlemi FCC komutlarını ve `~/.fcc/` ayarlarını siler; uv, Python ve
Claude Code'u silmez.

## Lisans

MIT
