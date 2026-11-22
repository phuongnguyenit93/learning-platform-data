# Chọn tệp cần quản lý bằng Git và tệp đầu ra cần bỏ qua trong dự án Gradle

Trong dự án Java dùng Gradle, **Git nên lưu những gì cần để người khác tái tạo, kiểm tra và sửa dự án**, còn các tệp được tạo ra khi chạy build hoặc chỉ có ý nghĩa trên máy cá nhân thường nên được bỏ qua. Cấu hình đúng giúp pull request dễ đọc, giảm xung đột, tránh lưu cache và hạn chế vô tình đưa thông tin bí mật vào repository.

Cần nhớ ngoại lệ quan trọng: **`gradle/wrapper/gradle-wrapper.jar` là tệp nhị phân nhưng phải được quản lý bằng Git** cùng các tệp Gradle Wrapper để người khác có thể chạy đúng phiên bản Gradle của dự án.

## 1. Cách quyết định tệp nào cần đưa vào Git

Trước khi thêm một đường dẫn vào `.gitignore`, trả lời bốn câu hỏi:

1. **Đây có phải nguồn sự thật do người/nhóm duy trì?** Mã Java, bài test, cấu hình build, version catalog, tài liệu và quy trình CI thường cần được commit.
2. **Có thể tạo lại tệp bằng một lệnh build từ các nguồn đã commit không?** Bytecode, JAR đầu ra, báo cáo test và cache Gradle thường cần được ignore. Bản build cuối nên phát hành qua kho artifact hoặc CI release khi cần phân phối.
3. **Tệp chỉ phụ thuộc máy hoặc tài khoản cá nhân?** Đường dẫn JDK riêng, cấu hình IDE cá nhân, nhật ký và thư mục tạm thường không nên commit. Những cấu hình IDE mang tính quy ước chung có thể được chọn commit theo thỏa thuận nhóm.
4. **Tệp chứa bí mật?** Token, mật khẩu, khóa riêng, thông tin đăng nhập repository hoặc chứng chỉ riêng phải được loại khỏi Git và được quản lý qua secret manager, biến môi trường hay vị trí cục bộ an toàn. `.gitignore` chỉ giúp giảm commit nhầm tệp **chưa được theo dõi**; nó không thay thế cơ chế bảo vệ bí mật.

Quy tắc này là **mặc định để ra quyết định**, không phải “mọi tệp được sinh ra đều bị bỏ qua”. Gradle Wrapper JAR, dependency lockfiles và dependency verification metadata có thể được công cụ sinh/cập nhật, nhưng vẫn là một phần của cấu hình build cần tái lập nên thường phải commit.

## 2. Phân loại tệp thường gặp

| Đường dẫn hoặc nhóm tệp | Nên làm gì? | Lý do |
| --- | --- | --- |
| `settings.gradle` hoặc `settings.gradle.kts` | **Track** | Khai báo tên dự án, module, plugin/dependency repositories và included builds |
| `build.gradle` hoặc `build.gradle.kts` ở root và các module | **Track** | Mô tả plugin, dependency và task |
| `gradle.properties` của dự án, nếu **không chứa bí mật** | **Track** | Giữ cấu hình Gradle dùng chung (ví dụ các cờ build an toàn) |
| `gradlew`, `gradlew.bat` | **Track** | Script chạy Gradle Wrapper cho Unix/macOS và Windows |
| `gradle/wrapper/gradle-wrapper.properties` | **Track** | Cố định distribution/version của Gradle Wrapper |
| `gradle/wrapper/gradle-wrapper.jar` | **Track** | Phần bootstrap cần để script Wrapper hoạt động; **không loại vì đuôi `.jar`** |
| `gradle/libs.versions.toml` | **Track**, nếu dùng | Version catalog cho dependency/plugin |
| `gradle.lockfile`, `**/gradle.lockfile`, `gradle/dependency-locks/` | **Track**, nếu dùng dependency locking | Giữ các phiên bản dependency đã khóa để tái lập build |
| `gradle/verification-metadata.xml`, keyring liên quan | **Track**, nếu dùng dependency verification | Kiểm soát thông tin xác thực artifact |
| `src/main/`, `src/test/`, `src/integrationTest/` do nhóm duy trì | **Track** | Source, resource, test và fixture chủ đích |
| `buildSrc/src/`, `buildSrc/build.gradle[.kts]` | **Track** | Build logic do nhóm duy trì, không phải output |
| `build-logic/` hoặc included build tương tự | **Track** phần source/config | Convention plugins, build logic dùng lại |
| `.gitignore`, `.gitattributes`, `.editorconfig`, `README.md`, tài liệu và CI workflow | **Track** | Quy ước repository và hướng dẫn cộng tác |
| `.gradle/` | **Ignore** | Cache, daemon/build metadata và dữ liệu Gradle tạo cục bộ |
| `build/` ở root hoặc module | **Ignore** | `.class`, JAR đầu ra, test results, report, generated resources và sản phẩm build |
| `out/`, `*.class` rơi ngoài thư mục build | **Ignore** | Output biên dịch của IDE hoặc thao tác thủ công |
| `.env`, `.env.local`, `local.properties` có cấu hình máy/bí mật | **Ignore** | Không tái sử dụng giữa mọi máy; có thể chứa credential |
| `*.log`, tệp tạm, OS artifacts | **Ignore** theo tình huống | Không phải source ổn định; tránh noise |
| `.idea/`, `.vscode/`, `*.iml` | **Quyết định theo nhóm** | Có cấu hình chỉ dùng cá nhân, nhưng cũng có cấu hình run/debug/lint dùng chung nên cân nhắc từng loại |

**Ngoại lệ cần xác định rõ:** nếu dự án chủ động duy trì một file sinh ra như một hợp đồng được kiểm duyệt (ví dụ client code được vendoring, fixture nhị phân có chủ đích, snapshot cho test hoặc tài liệu phát hành), nó có thể được track. Phải ghi rõ ai tạo, khi nào cập nhật và cách kiểm chứng để tránh sửa tay bản sinh ra rồi bị ghi đè.

## 3. Nhìn vào cấu trúc dự án nhiều module

Ví dụ một repository Gradle có hai module `app` và `lib`:

```text
demo-gradle/
├── .gitignore                         # Track
├── .gitattributes                     # Track
├── README.md                          # Track
├── settings.gradle                    # Track
├── build.gradle                       # Track
├── gradle.properties                  # Track nếu không có bí mật
├── gradlew                            # Track
├── gradlew.bat                        # Track
├── gradle/
│   ├── wrapper/
│   │   ├── gradle-wrapper.jar         # Track
│   │   └── gradle-wrapper.properties  # Track
│   └── libs.versions.toml             # Track nếu dùng
├── app/
│   ├── build.gradle                   # Track
│   ├── src/main/java/                 # Track
│   ├── src/test/java/                 # Track
│   └── build/                         # Ignore: đầu ra app
├── lib/
│   ├── build.gradle                   # Track
│   ├── src/main/java/                 # Track
│   └── build/                         # Ignore: đầu ra lib
├── .gradle/                           # Ignore: cache cục bộ
└── build/                             # Ignore: output root
```

Một file `.gitignore` đặt ở gốc repository có thể áp dụng cho cả subproject. Trong file này, mẫu **`build/`** (không có dấu `/` ở đầu) khớp thư mục có tên `build` ở nhiều cấp, vì vậy bỏ qua `build/`, `app/build/` và `lib/build/`. Ngược lại, mẫu **`/build/`** được neo vào vị trí chứa file `.gitignore` ở root, nên chỉ khớp `build/` tại root.

Phân biệt **`gradle/`** (thư mục chứa Wrapper và cấu hình cần track) với **`.gradle/`** (cache/runtime metadata thường bỏ qua). Chỉ khác một dấu chấm nhưng hậu quả rất lớn.

## 4. Một file `.gitignore` tham khảo

Đặt file dưới đây tại **root của repository**; dùng như mẫu khởi đầu, rồi điều chỉnh theo công cụ và quy tắc nhóm:

```gitignore
# Gradle cache và build output (root lẫn module con)
.gradle/
build/

# Kết quả biên dịch ngoài thư mục Gradle build
out/
*.class

# Log và artefact hệ điều hành
*.log
.DS_Store
Thumbs.db

# Cấu hình môi trường cục bộ/bí mật
.env
.env.*
!.env.example
!.env.*.example
/local.properties

# Tuỳ chính sách IDE của nhóm: bật dòng phù hợp nếu thực sự cần
# .idea/
# .vscode/
# *.iml
```

Đây là mẫu **phục vụ dự án Gradle thông thường**, không phải danh sách tuyệt đối. Một số dự án có log được dùng làm fixture; nếu vậy không nên ignore toàn bộ `*.log` hoặc cần định nghĩa ngoại lệ chính xác. Một dự án Maven/Gradle hỗn hợp có thể bổ sung `target/`; một ứng dụng Android có thể cần thêm đường dẫn output và cấu hình cục bộ riêng.

### Hiểu đúng từng pattern

- `build/`: khớp một thư mục có tên `build` ở bất kỳ cấp nào bên dưới `.gitignore` gốc; dấu `/` cuối chỉ thư mục.
- `.gradle/`: bỏ qua thư mục cache `.gradle`, **không** bỏ qua thư mục cấu hình `gradle`.
- `*.class`: chặn bytecode nằm ngoài `build/`; dấu `*` không phải lý do để bỏ qua tất cả tệp nhị phân.
- `/local.properties`: trong `.gitignore` ở root, chỉ áp dụng tệp `local.properties` ở root. Có thể thay bằng `local.properties` nếu muốn áp dụng mọi cấp.
- `.env.*`: bỏ qua `.env.local`, `.env.production`, v.v.; `!.env.example` và `!.env.*.example` đưa các **template không chứa bí mật** trở lại danh sách có thể track. Trước khi commit template vẫn phải kiểm tra không chứa giá trị thực.
- Ký tự `#` ở đầu dòng là comment; dấu `!` ở đầu pattern là phủ định (unignore). Pattern phía sau có thể thay đổi kết quả của pattern phía trước.

Đường dẫn có slash giữa mẫu và mẫu neo bằng slash có cách áp dụng khác. Ví dụ, `app/build/` chỉ nhắm cấu trúc `app/build` tương ứng; `/build/` chỉ nhắm `build` trực tiếp dưới thư mục chứa file ignore. Khi không chắc, hãy kiểm tra bằng `git check-ignore -v` thay vì đoán.

### Điều không nên thêm một cách máy móc

```gitignore
# VÍ DỤ SAI cho repository Gradle thông thường:
gradle/
*.jar
*.kts
src/
```

Tại sao sai?

- `gradle/` che mất Wrapper JAR/properties, version catalog và metadata quan trọng.
- `*.jar` có thể làm bỏ sót **`gradle-wrapper.jar`** khi tạo repository. JAR do build sinh ra đã nằm dưới `build/` và được ignore thông qua thư mục.
- `*.kts` chặn các file cấu hình Kotlin DSL như `build.gradle.kts`, `settings.gradle.kts`.
- `src/` chặn mã nguồn, tài nguyên và test — đúng thứ Git cần quản lý.

Ngay cả khi thêm luật `!gradle/wrapper/gradle-wrapper.jar`, việc unignore một file nằm trong **thư mục cha đã bị ignore** không tự động hoạt động nếu chưa mở lại toàn bộ thư mục cha liên quan. Dễ và an toàn hơn là **không ignore `gradle/` ngay từ đầu**.

## 5. Quy trình đưa một dự án Gradle vào Git

Giả định đang ở thư mục gốc dự án có `settings.gradle` (hoặc `settings.gradle.kts`) và bộ Wrapper đã được tạo.

**Bước 1 — Xem các file hiện tại:**

```bash
git status --short
```

Nếu chưa phải Git repository, cần khởi tạo bằng `git init` theo quy trình tạo repository của nhóm. Không tự chạy `git init` trong repository đã tồn tại.

**Bước 2 — Viết `.gitignore` trước khi stage toàn bộ source.** Dùng mẫu ở mục 4 và điều chỉnh cho module, IDE, secret thực tế. Đừng thêm tên một thư mục vào ignore chỉ vì nó “trông giống output”; kiểm tra ai tạo và dùng nó trước.

**Bước 3 — Kiểm tra quy tắc ignore:**

```bash
git check-ignore -v -- app/build/classes/java/main/demo/App.class
git check-ignore -v -- .gradle/caches/example
git check-ignore -v -- gradle/wrapper/gradle-wrapper.jar
```

Hai lệnh đầu, nếu có quy tắc khớp, sẽ chỉ ra **file ignore, số dòng và pattern** gây ra kết quả. Với Wrapper JAR, điều mong muốn là **không có pattern ignore khớp**; lệnh có thể không in gì và trả mã thoát 1. Vì Git thường không báo ignore cho file **đã track**, có thể thêm `--no-index` khi kiểm tra một file đã được theo dõi:

```bash
git check-ignore -v --no-index -- gradle/wrapper/gradle-wrapper.jar
```

Đây là **công cụ chẩn đoán**, không phải thao tác sửa index.

**Bước 4 — Xem những tệp Git đang track trước khi commit:**

```bash
git ls-files
git status --short
```

Chỉ stage những file được chọn theo chính sách repository. Trước lần commit đầu, `git add .` có thể tiện sau khi đã review `.gitignore` và trạng thái; với repository đang có thay đổi của nhiều người, nên stage chính xác đường dẫn mình phụ trách thay vì mặc định gom tất cả.

**Bước 5 — Kiểm tra lại việc tái lập build** trên môi trường thích hợp (có JDK tương thích):

```bash
./gradlew --version
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean test
```

Hai lệnh kiểm tra Wrapper và thực hiện build/test. Tên task có thể khác tùy dự án; ví dụ có thể cần `build`, `check` hoặc task riêng cho module. Không cố suy ra build sẽ chạy tốt chỉ vì `.gitignore` đúng: vẫn còn phụ thuộc JDK, plugin, repository và secret hợp lệ.

Sau build, dùng `git status --short`: các file `.class`, `build/libs/*.jar`, `build/test-results/`, `build/reports/` mới tạo **không nên xuất hiện như file untracked**. Nếu thấy source hoặc file cấu hình quan trọng bị ẩn, hãy sửa ignore trước khi commit.

## 6. File đã được Git theo dõi: thêm ignore không làm nó biến mất

Giả sử trước đây ai đó commit `app/build/libs/app.jar`. Về sau thêm `build/` vào `.gitignore` **không khiến Git ngừng theo dõi** file đó. Các thay đổi tiếp theo vẫn có thể hiện trong `git status`, vì ignore áp dụng chủ yếu cho file **untracked**.

Kiểm tra file đang track dù khớp luật ignore:

```bash
git ls-files -ci --exclude-standard
```

Nếu xác định một file output thực sự phải bỏ khỏi index, có thể dùng:

```bash
git rm --cached -- app/build/libs/app.jar
```

Nếu toàn bộ một thư mục build của module **đang được track** và đã xác minh không có file cần giữ:

```bash
git rm -r --cached -- app/build/
```

`--cached` loại đường dẫn khỏi **Git index** để commit kế tiếp ngừng quản lý nó; bản sao trong working directory vẫn còn. Sau đó kiểm tra `git status --short`, stage `.gitignore` và commit theo quy trình của nhóm. **Không chạy hàng loạt `git rm -r --cached .` để “làm mới ignore”**: thao tác đó làm đảo tung staging trên diện rộng và dễ ảnh hưởng file không thuộc phạm vi cần sửa.

Nếu kết quả `git ls-files` cho thấy source đáng lẽ phải track nhưng bị bỏ sót vì mẫu ignore quá rộng, hãy sửa **mẫu ignore gốc**. Chỉ cân nhắc `git add -f <file>` cho trường hợp ngoại lệ thật sự đã được nhóm chấp nhận; thêm cưỡng bức không sửa được nguyên nhân của rule sai.

## 7. Chọn đúng tệp trong các trường hợp khó

### 7.1. Gradle Wrapper

**Track đủ bộ** `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, `gradle/wrapper/gradle-wrapper.jar`.

Wrapper script và JAR cho phép chạy distribution được khai báo trong properties mà không phải cài sẵn bản Gradle toàn hệ thống. Trên Unix/macOS, thuộc tính executable của `gradlew` cũng cần được lưu trong Git. Nếu bị mất quyền thực thi, sau khi xác minh file có nội dung đúng, có thể sửa bằng:

```bash
git update-index --chmod=+x gradlew
```

Hoặc cấp quyền theo quy trình của hệ điều hành rồi stage lại. Không nên bỏ JAR vì ngộ nhận mọi file nhị phân đều là output. Khi cập nhật Wrapper, cần review cả distribution URL, checksum nếu có và provenance của Wrapper JAR vì đây là mã được chạy khi build.

### 7.2. `gradle.properties` và cấu hình máy

Trong root `gradle.properties`, những thiết lập không chứa bí mật và dùng chung có thể track, ví dụ:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
org.gradle.caching=true
```

Các ví dụ trên cần được điều chỉnh theo tài nguyên máy/CI của nhóm. **Không** lưu credential thực vào root `gradle.properties` được commit. Các giá trị cá nhân hoặc bí mật có thể được cung cấp qua biến môi trường, secret manager của CI hoặc file **`~/.gradle/gradle.properties` nằm ngoài repository** và được bảo vệ phù hợp.

Ví dụ file mẫu an toàn, có thể track: `.env.example` chỉ chứa tên biến và giá trị giả:

```dotenv
REPOSITORY_USERNAME=replace-me
REPOSITORY_PASSWORD=replace-me
```

Không đưa username/password thật hoặc token đã hoạt động vào file mẫu. Nếu đã lỡ commit secret, việc thêm `.gitignore` và xóa file khỏi commit mới **không xóa secret khỏi lịch sử Git**; cần thu hồi/luân chuyển secret và xử lý lịch sử theo quy trình bảo mật của nhóm.

### 7.3. `buildSrc`, `build-logic` và nguồn sinh ra

`buildSrc` hoặc included build như `build-logic` là **mã cấu hình build do người duy trì**: track `src/`, build scripts, resources và test của chúng. Nhưng `buildSrc/build/`, `build-logic/build/` và cache `.gradle/` bên trong vẫn nên ignore qua mẫu `build/` và `.gradle/`.

Các mã nguồn do generator tạo trong `build/generated/` thường không cần track vì Gradle có thể sinh lại khi build. Nếu generator tạo file vào `src/main/`, **không tự ý ignore cả `src/`**: xác định source đó có được quản lý như nguồn chính hay không, đưa output sang `build/generated/` nếu phù hợp, hoặc đặt một rule hẹp với chính sách rõ ràng.

### 7.4. IDE, workspace và công cụ hệ điều hành

`.idea/`, `.vscode/`, `*.iml` thường chứa thông tin môi trường, nhưng chúng cũng có thể chứa cấu hình style, debug, run và extension recommendations đã được nhóm thống nhất. Có ba lựa chọn hợp lý:

- Ignore cả thư mục nếu toàn bộ cấu hình IDE là sở thích cá nhân.
- Track **một số file có ích cho nhóm**, ví dụ `.vscode/extensions.json` hoặc `.vscode/launch.json` đã loại mọi đường dẫn/secret cá nhân; chỉ ignore file cục bộ cụ thể.
- Dùng cấu hình IDE trong repository nếu dự án có quy ước chính thức; review thay đổi như mọi nguồn cấu hình khác.

Không nên áp dụng máy móc một file `.gitignore` toàn cầu rồi vô tình làm mất cấu hình cần tái lập cho người mới.

### 7.5. JAR từ dependency và build artifacts

JAR dependency thông thường nên do Gradle tải từ repository qua `repositories`/`dependencies`, còn JAR được tạo bằng `jar` hoặc `bootJar` nằm trong `build/libs/` nên ignore. Nếu dự án chủ đích giữ một third-party local JAR dưới `libs/`, phải có lý do, nguồn gốc, bản quyền và quy trình nâng cấp rõ ràng; không được áp dụng `*.jar` toàn repository rồi đánh mất cả local dependency lẫn Wrapper JAR.

Đầu ra phát hành nên được lưu trong hệ thống release, artifact repository hoặc pipeline được kiểm soát. Git là nguồn của **cách tạo artifact**; không nhất thiết là nơi chứa mỗi lần build ra artifact mới.

## 8. `.gitignore`, local exclude và global ignore khác nhau

| Cơ chế | Phạm vi và cách dùng |
| --- | --- |
| `.gitignore` đã commit | Quy tắc áp dụng cho nhóm; nên chứa output Gradle và loại file cục bộ phổ biến |
| `.git/info/exclude` | Quy tắc riêng cho clone hiện tại; không commit; phù hợp file thử nghiệm cá nhân |
| Global Git ignore (`core.excludesFile`) | Quy tắc cho nhiều repository của **một người dùng**, ví dụ `.DS_Store` hoặc file editor cá nhân |

Nhóm không nên phụ thuộc global ignore riêng của một lập trình viên để bảo đảm `build/` hoặc `.gradle/` không vào repository. Mọi người và CI cần cùng nhìn thấy quy tắc quan trọng thông qua `.gitignore` được commit.

Một thư mục con có thể có `.gitignore` riêng. Khi dùng nhiều cấp, mẫu trong file con áp dụng theo vị trí của nó; vì vậy cần kiểm tra file và dòng rule thật sự bằng `git check-ignore -v`.

## 9. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Clone dự án về nhưng `./gradlew` lỗi do thiếu Wrapper JAR | Bỏ quên `gradle-wrapper.jar` hoặc ignore `gradle/`/`*.jar` | Kiểm tra `git ls-files -- gradle/wrapper`, sửa ignore và track đủ Wrapper |
| Mỗi lần build lại có hàng trăm thay đổi `.class`, JAR, XML test report | `build/` chưa ignore hoặc output đã bị track | Thêm `build/`; dùng `git ls-files -ci --exclude-standard` và bỏ track có chọn lọc |
| Module con `app/build/` vẫn xuất hiện | Dùng `/build/` chỉ root hoặc có override rule | Đổi thành `build/`, kiểm tra `git check-ignore -v` |
| `build.gradle.kts` bị bỏ sót | Rule `*.kts` quá rộng | Gỡ rule, stage lại build scripts |
| Đã sửa `.gitignore` nhưng Git vẫn báo file | File đã track trong Git index | Dùng `git ls-files` kiểm tra; `git rm --cached` cho đường dẫn xác định |
| File mẫu `.env.example` bị ignore | Rule `.env*` hoặc `.env.*` không có ngoại lệ | Thêm pattern unignore chính xác; rà soát bí mật trước commit |
| File cần unignore vẫn không xuất hiện | Thư mục cha đã bị ignore | Gỡ rule ignore cha, hoặc unignore từng thư mục cha cần thiết |
| IDE khác nhau gây diff liên tục | Đang track file state cá nhân | Thống nhất file IDE nào là shared configuration, file nào là local |
| Build trên máy người khác cần file có trong máy mình | Source/config bắt buộc chưa track, hoặc phụ thuộc local path/secret | Xem `git ls-files`, build từ clone sạch, cung cấp config/template an toàn |

## 10. Checklist để review pull request

Trước khi merge, có thể tự kiểm tra:

- [ ] Root/module `settings.gradle[.kts]`, `build.gradle[.kts]`, source và test đã được track.
- [ ] Có đầy đủ 4 file Gradle Wrapper cần thiết và không có rule ignore vô tình che chúng.
- [ ] `gradle/` được giữ cho cấu hình; `.gradle/` được ignore.
- [ ] `build/` ignore được cả output root lẫn module con.
- [ ] Version catalog, dependency lock và verification metadata (nếu được dùng) có trong Git.
- [ ] `gradle.properties`, `.env.example`, file CI không chứa bí mật hoặc đường dẫn máy cá nhân.
- [ ] `git status` sau khi chạy build không đưa output/caches vào danh sách file mới.
- [ ] Mọi thay đổi bỏ track qua `git rm --cached` đều được review đúng phạm vi.
- [ ] Một clone mới có thể chạy Wrapper và các task cơ bản khi đã cài JDK, có quyền truy cập dependency và cấu hình secret hợp lệ.

## 11. Bài tự kiểm tra

**Tình huống 1:** Có thư mục `gradle/wrapper/` chứa JAR và properties. Có nên ignore toàn bộ `gradle/` vì “Gradle tự tạo” không?

**Trả lời:** Không. Thư mục `gradle/` chứa các đầu vào quan trọng để bootstrapping và quản lý dependency. Track Wrapper, version catalog và metadata cần thiết; chỉ ignore cache `.gradle/`.

**Tình huống 2:** Sau lệnh `./gradlew build`, xuất hiện `app/build/libs/app.jar`. Có nên commit để đồng đội chạy ứng dụng ngay không?

**Trả lời:** Mặc định không. Đây là build artifact có thể tạo lại hoặc phân phối qua hệ thống artifact/release. Commit build scripts, source và tài nguyên cần thiết; ignore `build/`.

**Tình huống 3:** `.gitignore` đã có `build/`, nhưng `git status` vẫn báo `app/build/classes/App.class` thay đổi. Vì sao?

**Trả lời:** Có khả năng file đó đã được Git track từ trước. Kiểm tra `git ls-files`; nếu đúng là output và được phép bỏ theo dõi, dùng `git rm --cached` đúng đường dẫn rồi commit thay đổi index.

**Tình huống 4:** Bạn thêm `*.jar` vì thấy nhiều JAR sinh ra sau build. Rủi ro là gì?

**Trả lời:** Có thể bỏ qua `gradle-wrapper.jar` và JAR dependency được quản lý chủ động. Nên ignore thư mục `build/` thay cho toàn bộ đuôi JAR.

**Tình huống 5:** Đưa `API_TOKEN` vào `.env` và thêm `.env` vào `.gitignore` đã đủ an toàn chưa?

**Trả lời:** Chưa. Phải kiểm tra file có từng được track/commit không, không đưa secret vào log/build output, quản lý credential đúng cách; nếu secret từng lộ trong lịch sử thì cần thu hồi hoặc luân chuyển.

## Nguồn chính thức

- [Git — gitignore documentation](https://git-scm.com/docs/gitignore): cú pháp pattern, anchoring, phủ định và phạm vi áp dụng.
- [Git — git check-ignore](https://git-scm.com/docs/git-check-ignore): kiểm tra pattern nào đang ảnh hưởng đến đường dẫn.
- [Git — git rm](https://git-scm.com/docs/git-rm): khác nhau giữa xóa khỏi index và xóa khỏi working tree.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): các file Wrapper cần được quản lý và cách chạy distribution của dự án.
- [Gradle — Directory Layout](https://docs.gradle.org/current/userguide/directory_layout.html): thư mục cấu hình, cache và output Gradle.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): vai trò và quy trình lưu dependency lock state.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): file verification metadata và yêu cầu bảo toàn cấu hình.
