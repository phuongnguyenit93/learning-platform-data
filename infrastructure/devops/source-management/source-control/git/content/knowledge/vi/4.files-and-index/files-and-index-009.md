# Nhận diện thư mục rỗng, tệp sinh ra và tệp cấu hình theo máy

Khi chuẩn bị một repository để nhiều người cùng phát triển, bạn cần quyết định những gì nên được lưu trong Git và những gì chỉ tồn tại trên máy của từng người. Thư mục rỗng, tệp build sinh ra sau khi chạy chương trình và cấu hình chứa đường dẫn hoặc bí mật riêng của máy thường cần cách xử lý khác với mã nguồn và tài liệu dùng chung.

Git theo dõi nội dung tệp cùng đường dẫn và một số metadata của tệp. Git không lưu thư mục rỗng như một đối tượng độc lập. Các tệp được sinh ra có thể được bỏ qua bằng `.gitignore` nếu chúng có thể tái tạo. Cấu hình riêng của máy nên có mẫu dùng chung trong repository và phần giá trị local được giữ bên ngoài lịch sử.

## 1. Git không lưu thư mục rỗng

Trong mô hình Git, thư mục được biểu diễn gián tiếp thông qua các tree chứa những mục bên trong. Một thư mục chỉ có thể xuất hiện trong commit khi có ít nhất một mục được lưu dưới nó. Nếu thư mục không chứa tệp nào, Git không có mục để ghi nhận nên thư mục đó không xuất hiện trong tree của commit.

Ví dụ, cấu trúc làm việc có thể là:

```text
sample-app/
├── src/
├── logs/          <- thư mục rỗng
├── uploads/       <- thư mục rỗng
└── README.md
```

Sau khi commit, `src/` có thể xuất hiện nếu chứa tệp nguồn, còn `logs/` và `uploads/` rỗng sẽ không được tạo lại khi người khác clone repository. Đây là hành vi bình thường của Git.

### Dùng tệp placeholder để giữ cấu trúc thư mục

Nếu ứng dụng cần một thư mục tồn tại ngay sau khi clone, hãy đặt một tệp có nội dung nhỏ bên trong. Một quy ước phổ biến là dùng tên `.gitkeep`:

```text
sample-app/
├── logs/
│   └── .gitkeep
└── uploads/
    └── .gitkeep
```

`.gitkeep` không phải tên tệp đặc biệt mà Git nhận diện. Đây chỉ là quy ước của cộng đồng để báo rằng thư mục cần được giữ lại. Bạn cũng có thể dùng `README.md`, `.gitignore` hoặc một tệp placeholder có tên phù hợp với dự án.

Tạo placeholder và stage:

```bash
mkdir -p logs uploads
touch logs/.gitkeep uploads/.gitkeep
git add logs/.gitkeep uploads/.gitkeep
git status --short
```

Trên PowerShell, có thể tạo file rỗng bằng:

```powershell
New-Item -ItemType Directory -Force logs, uploads
New-Item -ItemType File -Force logs/.gitkeep, uploads/.gitkeep
git add logs/.gitkeep uploads/.gitkeep
```

Nếu placeholder chỉ có mục đích giữ cấu trúc, hãy ghi chú rõ trong README hoặc dùng một dòng giải thích bên trong file để người khác hiểu vì sao nó tồn tại. Không cần tạo placeholder cho mọi thư mục; chỉ giữ những thư mục mà ứng dụng, quy trình triển khai hoặc hướng dẫn thực sự cần.

## 2. Giữ thư mục nhưng bỏ qua các tệp sinh ra bên trong

Một thư mục có thể cần tồn tại trong repository trong khi các tệp được tạo ra bên trong nó không nên được commit. Ví dụ, ứng dụng cần `logs/` nhưng log runtime là dữ liệu riêng của mỗi máy.

Có thể dùng `.gitignore` ở repository root:

```gitignore
# Bỏ qua mọi mục trực tiếp trong logs, nhưng giữ placeholder
/logs/*
!/logs/.gitkeep
```

Sau khi commit `logs/.gitkeep`, thư mục `logs/` sẽ được tái tạo khi clone. Các file log được tạo trong đó sẽ bị ignore. Mẫu `!/logs/.gitkeep` mở ngoại lệ cho placeholder.

Một cách khác là đặt `.gitignore` ngay trong thư mục cần giữ:

```gitignore
# logs/.gitignore
*
!.gitignore
```

Khi commit `logs/.gitignore`, thư mục vẫn có một tệp được theo dõi; các nội dung khác trong thư mục bị ignore. Cách này tự mô tả quy tắc ngay tại nơi áp dụng.

Lưu ý: khi một thư mục cha bị ignore hoàn toàn, Git thường không đi sâu vào thư mục đó để tìm một tệp con được mở ngoại lệ. Nếu cần mở ngoại lệ cho một đường dẫn sâu, phải bảo đảm các thư mục cha trên đường dẫn cũng được phép đi vào. Với trường hợp đơn giản như `logs/.gitkeep`, mẫu bỏ qua các mục con rồi mở ngoại lệ trực tiếp thường dễ hiểu hơn.

## 3. Phân loại tệp sinh ra trước khi quyết định ignore

Không phải tệp nào được tạo tự động cũng cần bỏ khỏi Git. Hãy xem tệp đó có thể tái tạo hay không, ai cần sử dụng nó và repository có cần lưu đúng phiên bản của nó không.

| Loại tệp | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Build output | `build/`, `target/`, `dist/` | Ignore nếu có thể tạo lại từ mã nguồn và cấu hình build |
| Cache | `.cache/`, `.gradle/`, cache của bundler | Ignore vì phụ thuộc môi trường hoặc có thể tái tạo |
| Log runtime | `logs/*.log`, `npm-debug.log` | Ignore; không đưa dữ liệu runtime vào lịch sử mã nguồn |
| Test output | `coverage/`, báo cáo test tạm | Thường ignore; lưu artifact trong CI nếu cần xem lại |
| Dependency được cài tại chỗ | `node_modules/`, virtual environment | Thường ignore và cài lại theo manifest/lockfile |
| File tạm của IDE/hệ điều hành | workspace cá nhân, `.DS_Store`, `Thumbs.db` | Ignore theo quy ước nhóm hoặc cấu hình cá nhân |
| Generated source cần phân phối | mã nguồn sinh từ schema/protobuf hoặc client SDK | Có thể commit nếu người dùng repository cần dùng trực tiếp và không chạy generator |
| Dependency lockfile | `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock` | Thường commit khi dự án cần tái lập phiên bản dependency |
| Release artifact | gói cài đặt, binary, image | Theo chính sách phát hành; thường lưu trong registry hoặc hệ thống artifact riêng |

Một câu hỏi hữu ích là: **nếu xóa tệp này, nhóm có thể tái tạo chính xác nó từ những đầu vào đã được quản lý hay không?** Nếu có, ignore thường hợp lý. Nếu tệp là đầu vào, là kết quả được người dùng cần tải trực tiếp, hoặc việc tái tạo không ổn định, nhóm cần quyết định rõ cách version hóa.

### Không ignore mọi thứ có chữ “generated”

Một số tệp được sinh tự động nhưng vẫn là một phần cần thiết của dự án. Lockfile là ví dụ điển hình: nó được công cụ tạo ra nhưng giúp các thành viên cài cùng phiên bản dependency. Generated source cũng có thể cần commit nếu người dùng downstream không cài generator hoặc không có schema nguồn.

Ngược lại, binary build cục bộ, cache, log và báo cáo coverage thường không phải nguồn sự thật của dự án. Hãy ignore chúng hoặc lưu trong hệ thống artifact thay vì đưa vào commit mã nguồn.

## 4. Tạo `.gitignore` cho artifact phổ biến

Một file `.gitignore` ở gốc có thể chứa các quy tắc phù hợp với stack của dự án. Ví dụ tổng quát:

```gitignore
# Build output
/build/
/dist/
/target/

# Dependency và cache
/node_modules/
/.cache/
.gradle/

# Log và test output
*.log
/coverage/

# File hệ điều hành
.DS_Store
Thumbs.db

# Cấu hình local - xem phần cấu hình theo máy
.env
.env.*
!.env.example
/config/app.local.yml
```

Đây chỉ là ví dụ; không nên sao chép toàn bộ mà không kiểm tra dự án. Ví dụ, một dự án có chủ đích commit `dist/` để triển khai static site thì không nên ignore thư mục đó. Một dự án Java dùng Maven có thể cần ignore `target/`, trong khi dự án khác có thể quản lý một thư mục `target` như dữ liệu đầu vào.

Đặt `.gitignore` trong repository và commit để mọi người dùng chung quy tắc:

```bash
git add .gitignore
git diff --cached -- .gitignore
git commit -m "Add project ignore rules"
```

## 5. Tệp cấu hình theo máy là gì?

Tệp cấu hình theo máy (machine-local configuration) chứa giá trị chỉ đúng với môi trường của một lập trình viên hoặc một máy triển khai. Ví dụ:

- Đường dẫn thư mục dữ liệu hoặc SDK trên máy.
- Cổng dịch vụ local, tên database development.
- Tên người dùng, token, mật khẩu hoặc API key.
- Địa chỉ dịch vụ nội bộ chỉ truy cập được từ một mạng cụ thể.
- Cấu hình IDE hoặc công cụ phụ thuộc hệ điều hành.

Nếu commit những giá trị này, chúng có thể làm dự án không chạy trên máy khác, gây xung đột liên tục hoặc vô tình tiết lộ thông tin nhạy cảm. Cách tổ chức phổ biến là commit **mẫu cấu hình** và ignore **file cấu hình local thực tế**.

Ví dụ cấu trúc:

```text
sample-app/
├── .env.example          <- commit: tên biến và giá trị minh họa
├── .env                  <- ignore: giá trị riêng của máy
├── config/
│   ├── app.example.yml   <- commit: mẫu cấu hình
│   └── app.local.yml     <- ignore: cấu hình riêng
└── .gitignore
```

`.env.example` có thể chứa các khóa với giá trị giả hoặc placeholder:

```dotenv
APP_ENV=development
APP_PORT=3000
DATABASE_URL=postgres://user:password@localhost:5432/sample_app
API_TOKEN=replace-with-your-local-token
```

Không đặt credential thật vào file mẫu. Dùng hướng dẫn để mỗi thành viên tự sao chép mẫu và điền giá trị local:

```bash
cp .env.example .env
```

Trên PowerShell:

```powershell
Copy-Item .env.example .env
```

Sau đó người dùng chỉnh `.env` trên máy mình; `.gitignore` ngăn file này được thêm theo cách thông thường.

## 6. Mẫu cấu hình và file local override

Với cấu hình dạng YAML, JSON hoặc TOML, có thể dùng cặp file mẫu và file local:

```text
config/
├── app.example.yml
└── app.local.yml
```

`.gitignore`:

```gitignore
/config/app.local.yml
```

File mẫu được commit:

```yaml
server:
  host: 127.0.0.1
  port: 8080
database:
  url: jdbc:postgresql://localhost:5432/sample_app
  username: local_user
  password: change-me
```

Giá trị trong ví dụ chỉ để minh họa; không dùng mật khẩu thật trong mẫu được commit. Tài liệu dự án nên giải thích cách tạo `app.local.yml` từ mẫu và cách ứng dụng nạp override. Git chỉ quản lý các file được commit; Git không tự biết ứng dụng cần ghép hai file cấu hình như thế nào.

Nếu cấu hình chỉ khác nhau ở vài giá trị nhạy cảm, có thể ưu tiên biến môi trường hoặc secret manager thay vì sao chép toàn bộ file. Cách này giúp cấu hình dùng chung ít bị phân nhánh và giảm nguy cơ commit nhầm bí mật.

## 7. Ba nơi đặt quy tắc ignore

Không phải mọi quy tắc ignore đều cần commit vào repository. Git có nhiều nơi để khai báo:

| Nơi khai báo | Phạm vi | Khi nào dùng |
|---|---|---|
| `.gitignore` trong dự án | Dùng chung cho repository và được commit | Build output, log, file local theo quy ước nhóm |
| `.git/info/exclude` | Chỉ repository local hiện tại | Tệp tạm hoặc cấu hình cá nhân không muốn chia sẻ |
| File ignore toàn cục qua `core.excludesFile` | Các repository của người dùng hiện tại | File do IDE, editor hoặc hệ điều hành sinh ra trên máy cá nhân |

Ví dụ thêm quy tắc local cho một repository bằng `.git/info/exclude`:

```gitignore
# Chỉ bỏ qua trong clone hiện tại
scratch-notes.txt
local-test-data/
```

File này nằm trong Git directory nên không được commit cùng dự án.

Đặt file ignore toàn cục:

```bash
git config --global core.excludesFile ~/.config/git/ignore
```

Nội dung file ignore toàn cục có thể là:

```gitignore
.DS_Store
Thumbs.db
.idea/workspace.xml
```

Quy tắc global phù hợp cho tệp cá nhân hoặc hệ điều hành. Nếu cả nhóm đều cần bỏ qua một thư mục build cụ thể của dự án, hãy đặt quy tắc trong `.gitignore` được commit thay vì yêu cầu từng người tự cấu hình global.

## 8. Ignore không ngừng theo dõi tệp đã được commit

`.gitignore` chỉ ảnh hưởng đến cách Git nhận diện các đường dẫn chưa được theo dõi. Nếu `.env` hoặc `config/app.local.yml` đã được commit, thêm chúng vào `.gitignore` không khiến Git ngừng theo dõi. Thay đổi của những tệp đó vẫn xuất hiện trong `git status`.

Để bỏ tệp khỏi index nhưng giữ bản sao trên máy:

```bash
# Thêm quy tắc ignore trước
printf '\n.env\n/config/app.local.yml\n' >> .gitignore

# Gỡ khỏi index, giữ file trong working tree
git rm --cached -- .env config/app.local.yml

# Kiểm tra thay đổi chuẩn bị commit
git status
git diff --cached
```

Sau đó commit thay đổi `.gitignore` và việc gỡ tệp khỏi repository. Thành viên khác sẽ không còn nhận file local từ commit mới; họ cần tạo file của mình từ mẫu cấu hình.

Nếu file từng chứa password, token hoặc key thật, việc gỡ file khỏi commit mới **không xóa bí mật khỏi lịch sử cũ**. Hãy thu hồi hoặc xoay vòng credential trước, sau đó xử lý lịch sử theo quy trình bảo mật của dự án. Không coi `.gitignore` là biện pháp xóa bí mật đã bị commit.

## 9. Kiểm tra tệp bị ignore và tệp đang được theo dõi

Dùng `git check-ignore -v` để biết quy tắc, file và số dòng đã bỏ qua một đường dẫn:

```bash
git check-ignore -v .env
git check-ignore -v build/output.jar
```

Nếu cần kiểm tra quy tắc ignore đối với một đường dẫn đã tracked, dùng `--no-index`:

```bash
git check-ignore -v --no-index config/app.local.yml
```

Liệt kê trạng thái có cả ignored files:

```bash
git status --short --ignored
```

Xem một đường dẫn có đang được Git theo dõi không:

```bash
git ls-files -- .env
```

Nếu lệnh `git ls-files` in ra đường dẫn, tệp đang nằm trong index của commit hiện tại hoặc index staged. Nếu tệp không xuất hiện nhưng `git check-ignore -v` tìm thấy quy tắc, nó đang bị ignore và chưa được theo dõi.

## 10. Phân biệt ignored, untracked và deleted

Ba trạng thái này không giống nhau:

| Trạng thái | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| Untracked | Tệp mới, chưa nằm trong index và không bị ignore | `git status --short` |
| Ignored | Tệp chưa tracked và khớp quy tắc ignore | `git check-ignore -v <path>` hoặc `git status --short --ignored` |
| Deleted | Tệp đã tracked nhưng bị xóa khỏi working tree | `git status --short` hoặc `git diff --summary` |

Nếu một file local biến mất khỏi `git status`, không nên kết luận ngay rằng Git đã xóa hoặc bỏ theo dõi nó. Hãy kiểm tra `git ls-files`, `git check-ignore -v` và trạng thái filesystem để biết file đang ở trạng thái nào.

## 11. Xem trước tác động khi dọn tệp sinh ra

Các tệp build, cache và log có thể được xóa để giải phóng dung lượng, nhưng hãy xem trước danh sách trước khi thực hiện. `git clean` có thể xóa tệp untracked và ignored khỏi working tree.

```bash
# Xem trước các tệp/thư mục untracked sẽ bị xóa (không bao gồm ignored)
git clean -nd

# Xem trước riêng các tệp/thư mục ignored sẽ bị xóa
git clean -ndX

# Xem trước mọi tệp untracked, kể cả ignored
git clean -ndx
```

Các tùy chọn `-n` (dry run) và `-d` (đi vào thư mục) giúp xem danh sách mà không xóa. Chỉ chạy lệnh xóa thật sau khi đã xem kỹ danh sách, ví dụ `git clean -fdX` sẽ xóa các tệp và thư mục ignored. Lệnh này không xóa tệp tracked, nhưng có thể xóa `.env` local hoặc dữ liệu runtime mà bạn chưa sao lưu.

Để dọn build output, ưu tiên lệnh clean của hệ thống build nếu có. Chỉ dùng `git clean` khi hiểu rõ phạm vi untracked/ignored trong repository.

## 12. Quy trình thiết lập cho một dự án mới

Khi chuẩn bị repository để cả nhóm cùng sử dụng, có thể làm theo trình tự:

1. Liệt kê thư mục mà ứng dụng cần có sau khi clone, ví dụ `logs/`, `uploads/`, `tmp/`.
2. Với thư mục rỗng cần giữ, thêm `.gitkeep`, `.gitignore` hoặc README có giải thích.
3. Phân loại artifact theo khả năng tái tạo và nhu cầu phân phối; ignore build output, cache, log và dependency cài tại chỗ nếu chúng không phải đầu vào cần version hóa.
4. Quyết định rõ các generated source, lockfile và release artifact có cần commit theo workflow dự án không.
5. Tạo file mẫu như `.env.example` hoặc `config/app.example.yml`, chỉ chứa giá trị giả và hướng dẫn.
6. Ignore file local như `.env`, `config/app.local.yml` và dữ liệu theo máy.
7. Đặt quy tắc cá nhân trong `.git/info/exclude` hoặc file ignore global.
8. Kiểm tra bằng `git status --short --ignored`, `git check-ignore -v` và `git ls-files`.
9. Stage và review `.gitignore`, placeholder và template trước khi commit.

Ví dụ trạng thái mong muốn:

```text
sample-app/
├── .gitignore             <- tracked
├── .env.example           <- tracked
├── .env                   <- ignored
├── config/
│   ├── app.example.yml    <- tracked
│   └── app.local.yml      <- ignored
├── logs/
│   └── .gitkeep           <- tracked
├── build/                 <- ignored
└── src/                   <- tracked source
```

Kiểm tra trước commit:

```bash
git status --short --ignored
git check-ignore -v .env config/app.local.yml build/output.jar
git ls-files -- .gitignore .env.example config/app.example.yml logs/.gitkeep
git diff --cached
```

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Git theo dõi thư mục rỗng | Không. Git lưu file; muốn giữ thư mục cần có placeholder hoặc file cấu hình bên trong. |
| `.gitkeep` là lệnh hoặc tính năng đặc biệt của Git | Không. Đây là quy ước tên file do dự án lựa chọn. |
| Mọi file được sinh tự động đều phải ignore | Không. Lockfile hoặc generated source có thể cần commit để bảo đảm khả năng tái lập hoặc sử dụng downstream. |
| Thêm file vào `.gitignore` sẽ ngừng theo dõi nó | Không. Tệp đã tracked vẫn được theo dõi; cần gỡ khỏi index bằng `git rm --cached` nếu muốn giữ bản local. |
| `.git/info/exclude` được chia sẻ với đồng đội | Không. Nó chỉ áp dụng cho repository local hiện tại. |
| File ignore global thay thế `.gitignore` dự án | Không. Global dành cho thói quen cá nhân; quy tắc chung của dự án nên được commit. |
| Xóa `.env` khỏi commit mới là bí mật biến mất khỏi lịch sử | Không. Cần thu hồi/đổi credential và xử lý lịch sử nếu bí mật đã được công bố. |
| `git clean -fdX` chỉ xóa cache vô hại | Không. Nó xóa mọi mục ignored phù hợp, có thể gồm cấu hình local hoặc dữ liệu chưa sao lưu. |

## 14. Tự kiểm tra

1. **Vì sao Git không giữ một thư mục rỗng sau khi clone?**
   - Vì tree của Git lưu các mục file và thư mục con; thư mục không có mục nào không được biểu diễn độc lập.
2. **`.gitkeep` có ý nghĩa đặc biệt với Git không?**
   - Không. Đây chỉ là quy ước để đặt một file placeholder trong thư mục.
3. **Nên làm gì với build output có thể tái tạo?**
   - Thường thêm quy tắc ignore phù hợp, trừ khi workflow dự án chủ động phân phối hoặc version hóa artifact đó.
4. **Vì sao nên commit `.env.example` nhưng ignore `.env`?**
   - File mẫu chia sẻ tên biến và cấu trúc; file thật chứa giá trị riêng hoặc bí mật của từng máy.
5. **Làm sao biết quy tắc nào đã ignore một tệp?**
   - Dùng `git check-ignore -v <path>`.
6. **Tệp đã tracked có bị bỏ theo dõi khi thêm vào `.gitignore` không?**
   - Không. Dùng `git rm --cached <path>` để gỡ khỏi index nhưng giữ file local.
7. **Lệnh nào xem trước các tệp ignored mà `git clean` sẽ xóa?**
   - `git clean -ndX`.

## Kết luận

Git không lưu thư mục rỗng, vì vậy hãy dùng placeholder như `.gitkeep` hoặc `.gitignore` khi cần giữ cấu trúc. Tệp sinh ra nên được phân loại theo khả năng tái tạo và nhu cầu phân phối; build output, cache và log thường được ignore, trong khi lockfile hoặc generated source có thể cần commit. Với cấu hình theo máy, hãy commit file mẫu và ignore file local chứa giá trị riêng. Dùng `.gitignore` cho quy tắc chung, `.git/info/exclude` hoặc ignore global cho nhu cầu cá nhân, rồi kiểm tra bằng `git check-ignore`, `git status --ignored` và `git ls-files` trước khi commit hoặc dọn dữ liệu.
