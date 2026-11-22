# Build từ mã nguồn sạch thay vì dựa vào tệp có sẵn trên máy

Một pipeline CI/CD đáng tin cậy phải có khả năng tạo sản phẩm từ mã nguồn và các đầu vào đã khai báo trong repository. Nếu build chỉ thành công vì trên máy đang có một file JAR cũ, thư mục generated source chưa được cập nhật, dependency tải từ lần chạy trước hoặc một cấu hình cục bộ không được commit, kết quả đó không phản ánh đúng nội dung của commit hiện tại.

**Build từ mã nguồn sạch** nghĩa là bắt đầu từ một revision Git xác định trong workspace sạch, tái tạo các tệp phát sinh theo quy trình đã khai báo, rồi build và kiểm thử bằng toolchain cùng dependency được kiểm soát. Pipeline không được cần đến đầu ra tình cờ còn sót lại từ lần chạy trước hoặc file chỉ tồn tại trên máy của một lập trình viên.

Đây là nền tảng của build tái lập trong CI/CD. Nó giúp nhóm phát hiện sớm dependency bị khai báo thiếu, build script phụ thuộc trạng thái máy, generated code lỗi thời và sự khác biệt giữa môi trường phát triển với môi trường CI. Một build sạch là điều kiện quan trọng, nhưng chưa tự bảo đảm hai lần build sẽ tạo ra byte đầu ra giống hệt nhau; tính tái lập còn phụ thuộc toolchain, dependency, cấu hình và các yếu tố không xác định khác.

## 1. “Mã nguồn sạch” có nghĩa gì?

Một workspace được xem là sạch khi nội dung cần thiết để build đến từ revision đã chọn và các đầu vào được khai báo rõ ràng. Thông thường, điều đó bao gồm:

- Checkout đúng commit SHA, không build nhầm nhánh hoặc thay đổi chưa commit.
- Không có file build output, generated file cũ hoặc file cấu hình cá nhân làm thay đổi kết quả.
- Các submodule, Git LFS object và nguồn mã phụ trợ được lấy đầy đủ theo revision đã ghi nhận.
- Các file sinh tự động được tạo lại từ schema, template hoặc source input bằng công cụ có phiên bản xác định.
- Dependency và toolchain được resolve theo cấu hình/lockfile của repository.
- Biến môi trường và cấu hình hệ thống cần thiết được cung cấp rõ ràng.

Mã nguồn sạch không có nghĩa xóa mọi cache trên máy trong mọi lần chạy. Cần phân biệt file thuộc workspace có thể ảnh hưởng đến kết quả với cache dependency hoặc build cache được quản lý theo khóa đầu vào. Cache hợp lệ có thể tăng tốc build nếu việc tái sử dụng được kiểm soát và không làm thay đổi tính đúng đắn.

## 2. Vì sao file có sẵn trên máy có thể làm sai kết quả?

Một build có thể thành công trên máy phát triển nhưng thất bại trong CI hoặc trên một máy mới vì máy cũ đang chứa dữ liệu mà repository không cung cấp. Các tình huống thường gặp:

| Tệp hoặc trạng thái còn sót | Rủi ro | Cách xử lý |
|---|---|---|
| JAR, class file hoặc thư mục `build/`, `target/` cũ | Build hoặc test vô tình sử dụng output từ source revision trước | Tạo workspace mới hoặc xóa đúng build output trước khi build |
| Generated source cũ | Code sinh ra không còn khớp schema/template hiện tại | Chạy bước generate từ đầu vào đã khai báo |
| File cấu hình cục bộ không được commit | Build chỉ chạy được trên máy có file đó | Commit cấu hình không nhạy cảm hoặc cấp cấu hình qua cơ chế rõ ràng |
| Dependency được cài thủ công ngoài lockfile | Kết quả khác giữa máy và CI | Dùng dependency declaration, lockfile và quy trình resolve chuẩn |
| Environment variable có sẵn trên máy | Build phụ thuộc giá trị không được pipeline khai báo | Khai báo biến cần thiết và kiểm tra biến bắt buộc |
| File untracked hoặc ignored | Tệp không xuất hiện trong diff thông thường nhưng vẫn được build script đọc | Dùng workspace sạch; kiểm tra cả ignored files khi điều tra |
| Submodule/LFS chưa được checkout đầy đủ | Thiếu source hoặc asset cần thiết | Khởi tạo submodule và tải LFS object theo cấu hình repository |

Ví dụ, một dự án Java có `src/main/java` mới nhưng máy lập trình viên vẫn giữ `build/classes` từ lần build trước. Nếu build script có cấu hình sai và lấy class cũ vào package, JAR có thể chứa code không tương ứng với commit hiện tại. Máy CI mới không có thư mục đó nên build thất bại, hoặc tạo artifact khác.

Tương tự, một schema OpenAPI được cập nhật nhưng generated client không được tạo lại. Máy có generated source cũ vẫn compile được, trong khi môi trường sạch phát hiện thiếu class hoặc API không tương thích. Build sạch giúp lộ ra dependency bị che giấu này.

## 3. Tạo workspace sạch từ Git

### Ưu tiên checkout mới hoặc workspace dùng một lần

Cách rõ ràng nhất là tạo workspace mới cho mỗi lần chạy CI, checkout commit cần build và hủy workspace sau khi job kết thúc. Với hosted runner dạng ephemeral, nền tảng thường cấp workspace mới theo job; với self-hosted runner, cần kiểm soát việc tái sử dụng thư mục giữa các lần chạy.

Nếu phải dùng runner lâu dài, mỗi job nên làm việc trong thư mục riêng theo run ID hoặc commit, sau đó dọn workspace theo chính sách. Không để hai job ghi vào cùng thư mục checkout vì file sinh ra từ job này có thể ảnh hưởng job kia.

### Xác minh revision và trạng thái Git

Trước khi build, ghi nhận commit đang được checkout:

```bash
git rev-parse HEAD
git status --short
git diff --exit-code
git diff --cached --exit-code
```

`git rev-parse HEAD` cho biết commit thực tế. Hai lệnh diff kiểm tra thay đổi trong tracked files ở working tree và staging area. `git status --short` giúp phát hiện file untracked thông thường. Khi điều tra file bị `.gitignore` che khuất, có thể dùng `git status --short --ignored` để xem thêm ignored files.

Lưu ý: `git status` không tự chứng minh workspace không có file ignored. Một file build output trong `.gitignore` có thể không xuất hiện ở kết quả mặc định nhưng vẫn bị một script tùy chỉnh đọc. Workspace mới là cách đơn giản hơn để tránh phải suy luận về trạng thái còn sót.

Lệnh `git clean` có thể xóa file untracked hoặc ignored và gây mất dữ liệu cục bộ. Không chạy các biến thể xóa như `git clean -xfd` tùy tiện trên máy phát triển. Nếu cần khảo sát, dùng chế độ dry-run `git clean -ndx` để xem trước danh sách; chỉ thực hiện xóa trong workspace CI dùng một lần hoặc sau khi xác nhận phạm vi.

### Lấy đủ source phụ trợ

Nếu repository dùng Git submodule, cần checkout đúng revision được ghi trong gitlink. Nếu dùng Git LFS, cần tải object tương ứng thay cho pointer file. Nếu build phụ thuộc tag hoặc lịch sử Git để tạo version, cấu hình fetch depth phải đủ để lấy dữ liệu đó.

Ví dụ với GitHub Actions:

```yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<FULL_COMMIT_SHA>
    with:
      clean: true
      submodules: recursive
      lfs: true
      fetch-depth: 0
```

`<FULL_COMMIT_SHA>` là placeholder cần thay bằng commit SHA đầy đủ đã xác minh. `submodules`, `lfs` và `fetch-depth` chỉ bật theo nhu cầu repository; fetch toàn bộ lịch sử có thể tốn thời gian và không cần thiết nếu build không dùng Git history hoặc tag. `clean: true` yêu cầu action làm sạch trạng thái tracked/untracked theo hành vi checkout của nó, nhưng không thay thế việc kiểm tra workspace và cấu hình runner.

## 4. Tạo lại build output và generated files

Build output là kết quả của quá trình build, không phải đầu vào nguồn mặc định. Những thư mục như `build/`, `target/`, `out/`, `dist/` hoặc `bin/` thường được tạo lại trong mỗi lần build và nên được quản lý qua `.gitignore` phù hợp.

Generated source có thể thuộc một trong hai loại:

- **Generated source được commit:** file sinh ra là một phần của source revision. Pipeline cần kiểm tra file đó được đồng bộ với schema/template gốc theo quy tắc dự án.
- **Generated source sinh trong lúc build:** file không cần commit; pipeline phải chạy generator từ đầu vào được quản lý trước khi compile hoặc package.

Không nên dựa vào generated file cũ có sẵn trên runner. Hãy khai báo generator như một task có dependency rõ ràng, ghim phiên bản plugin/công cụ và xác định đầu ra. Nếu generation cần schema từ repository khác, cần pin revision/schema version tương ứng.

Ví dụ với Gradle:

```kotlin
val generateApi by tasks.registering(JavaExec::class) {
    // Cấu hình generator, classpath và input schema theo dự án.
    inputs.file("src/main/openapi/orders.yaml")
    outputs.dir(layout.buildDirectory.dir("generated/sources/openapi"))
}

tasks.named("compileJava") {
    dependsOn(generateApi)
}
```

Đây là khung minh họa, cần bổ sung `mainClass`, `classpath`, arguments và source set phù hợp với generator thực tế. Khai báo inputs/outputs giúp Gradle biết khi nào task cần chạy lại và khi nào có thể tái sử dụng output hợp lệ. Không nên khai báo thiếu đầu vào vì Gradle có thể coi output cũ vẫn up-to-date dù schema đã đổi.

## 5. Hiểu đúng các lệnh clean của build tool

Lệnh `clean` thường xóa build output do build tool quản lý. Nó không nhất thiết xóa mọi file untracked, ignored hoặc cấu hình cục bộ trong repository.

| Công cụ | Lệnh thường dùng | Phạm vi chính |
|---|---|---|
| Gradle | `./gradlew clean build` | Xóa thư mục build của các project rồi chạy build task được yêu cầu |
| Maven | `./mvnw clean verify` | Xóa output trong `target/` rồi chạy các phase đến `verify` |
| npm | `npm ci` | Cài dependency theo lockfile trong chế độ clean install; không thay thế việc tạo workspace sạch |
| Make | `make clean` | Phụ thuộc target `clean` do Makefile định nghĩa |

Với Gradle, `clean` thường xóa thư mục `build` của project/subproject. Nó không mặc định xóa toàn bộ Gradle user home hoặc dependency cache. Với Maven, `clean` thường xóa `target` theo cấu hình plugin; nó không xóa toàn bộ local Maven repository. Đây là hành vi mong muốn trong đa số trường hợp: loại bỏ output của dự án nhưng vẫn có thể dùng lại dependency cache đã được quản lý.

Ví dụ cho dự án Java:

```bash
./gradlew --no-daemon clean build
```

Hoặc với Maven Wrapper:

```bash
./mvnw -B clean verify
```

`clean` hữu ích để xác nhận build không cần output cũ. Tuy nhiên, nó không tạo checkout mới, không loại bỏ file cấu hình cá nhân, không đảm bảo environment giống nhau và không tự làm cho dependency có tính bất biến. Cần kết hợp với workspace sạch và đầu vào được kiểm soát.

## 6. Cache được phép dùng khi nào?

Cache là tối ưu hiệu năng, không phải nguồn sự thật của dự án. Có thể phân biệt:

- **Dependency cache:** lưu package đã tải về để tránh tải lại. Khi dùng lockfile, checksum và repository tin cậy, cache có thể được tái sử dụng.
- **Build cache:** lưu output của task dựa trên fingerprint đầu vào. Chỉ an toàn khi task khai báo đầy đủ inputs/outputs và cache không bị đầu độc.
- **Workspace cache:** giữ nguyên thư mục làm việc giữa các lần chạy. Loại này dễ mang theo file tạm, generated output hoặc trạng thái không khai báo, nên cần thận trọng nhất.

Một build sạch không bắt buộc phải tải lại mọi dependency từ Internet. Nếu dependency cache được xác minh bằng checksum và dependency resolution được khóa, dùng cache chỉ thay đổi tốc độ tải, không thay đổi nội dung dependency. Tương tự, build cache có thể tái sử dụng output nếu fingerprint phản ánh đầy đủ tất cả đầu vào có ảnh hưởng.

Khi nghi ngờ cache gây sai lệch, chạy một lần kiểm tra không dùng build cache hoặc dùng cache namespace mới để so sánh. Nếu kết quả khác nhau, kiểm tra task inputs, cache key, dependency lock và nguồn cache. Với artifact phát hành, cần lưu metadata đủ để biết output được build trực tiếp hay được khôi phục từ cache.

Không chia sẻ cache có thể ghi tùy tiện giữa job không tin cậy và job phát hành có quyền cao. Job từ pull request bên ngoài có thể chạy mã do người khác kiểm soát; cache của job đó không nên trở thành nguồn đáng tin cho quy trình production nếu không có cơ chế phân tách và xác minh.

## 7. Kiểm soát Docker build context

Docker build có thể vô tình đưa file có sẵn trên máy vào image nếu build context chứa toàn bộ thư mục làm việc. Lệnh `COPY . .` sao chép các file trong context (trừ những file bị loại bởi `.dockerignore`), nên output cũ, file `.env`, cache hoặc credential có thể bị đóng vào image nếu không kiểm soát.

Một `.dockerignore` phù hợp có thể loại bỏ các file không phải đầu vào build:

```dockerignore
.git
.gradle
.idea
build
target
out
dist
*.log
.env
```

Danh sách cần điều chỉnh theo dự án. Nếu ứng dụng cần một file được tạo trong build, hãy tạo nó bằng bước rõ ràng và đưa vào context một cách có chủ đích. Không loại bỏ file nguồn hoặc metadata cần thiết chỉ để làm build context nhỏ hơn.

Nên build image từ checkout sạch và ghi nhận commit, build arguments, base image digest cùng image digest đầu ra. Build context cũng là một phần đầu vào; hai lần build cùng commit nhưng context chứa các file khác nhau có thể tạo ra image khác nhau.

## 8. Thiết kế job CI bắt đầu từ source sạch

Một job CI tham khảo cho dự án Gradle có thể gồm các bước sau:

```yaml
name: clean-source-build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout exact source revision
        uses: actions/checkout@<FULL_COMMIT_SHA>
        with:
          clean: true

      - name: Record source revision
        run: |
          git rev-parse HEAD
          git status --short

      - name: Build and test from clean outputs
        run: ./gradlew --no-daemon clean build

      - name: Verify tracked source was not modified
        run: git diff --exit-code
```

Ví dụ dùng hosted runner và placeholder cho action SHA. Với self-hosted runner, cần bảo đảm workspace được cô lập hoặc checkout được làm sạch đúng cách. Nếu build phụ thuộc submodule, Git LFS hoặc Git tags, thêm các tùy chọn checkout phù hợp. Nếu build sinh file tracked, bước cuối có thể cần quy tắc riêng để xác minh generated source thay vì mặc định yêu cầu không có diff.

Một pipeline hoàn chỉnh thường tách các bước:

1. Checkout source revision và lấy đủ source phụ trợ.
2. Xác minh commit, trạng thái workspace và đầu vào build.
3. Khôi phục dependency cache an toàn hoặc resolve dependency theo lockfile.
4. Tạo generated source và resource từ đầu vào đã khai báo.
5. Chạy clean build, unit test và các kiểm tra cần thiết.
6. Đóng gói artifact, ghi commit SHA, toolchain và digest.
7. Lưu artifact cùng test report và metadata để các môi trường sau promote.

## 9. Kiểm tra build có thực sự độc lập với máy cá nhân không

Khi một build chỉ chạy trên một máy, có thể khó biết nó phụ thuộc vào file hoặc cấu hình nào. Một số cách kiểm chứng:

- Tạo clone hoặc worktree mới tại cùng commit và build trong thư mục đó.
- Chạy trong container/runner image đã quản lý với biến môi trường tối thiểu.
- Tạm thời không dùng build cache để so sánh kết quả.
- Kiểm tra file ignored, untracked và generated outputs khi build có hành vi khác thường.
- Xóa đúng output do build tool quản lý bằng task clean trước khi build.
- So sánh artifact digest từ hai workspace độc lập nếu mục tiêu là kiểm tra tính tái lập ở mức byte.
- Chạy test sau build và xác minh artifact được tạo từ đúng commit.

Nếu hai workspace sạch cùng commit tạo ra kết quả khác, hãy so sánh toolchain, dependency resolution, build arguments, environment variables, timestamp, locale, timezone và nguồn dữ liệu từ xa. Đây là bước điều tra reproducibility; chỉ chạy `clean` nhiều lần trên cùng một workspace không đủ để tìm mọi phụ thuộc ẩn.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Máy lập trình viên build được, CI thất bại | File local hoặc tool cài sẵn bị thiếu trong CI | Tạo workspace mới và khai báo dependency/toolchain |
| CI lần đầu thất bại, lần sau thành công | Job đầu tạo file mà job sau vô tình dùng lại | Làm rõ dependency giữa các task, không phụ thuộc workspace persistence |
| Build sạch thiếu class được tạo tự động | Generator không được nối vào task compile hoặc output bị xóa | Khai báo generator task và dependency chính xác |
| Build trong Docker khác build trực tiếp | Docker context chứa file khác hoặc base image thay đổi | Kiểm soát `.dockerignore`, context và base image digest |
| Build chỉ lỗi trên self-hosted runner | Workspace được tái sử dụng hoặc runner có cấu hình riêng | Dùng workspace/job cô lập và ghi diagnostics |
| Build không ổn định dù đã clean | Dependency/toolchain/OS hoặc yếu tố không xác định thay đổi | Pin đầu vào, ghi provenance và loại bỏ nguồn biến động |
| Build cache trả output không đúng | Task thiếu input declaration hoặc cache không đáng tin | Sửa fingerprint, cô lập cache và chạy kiểm chứng không cache |

## 11. Phân biệt clean build và reproducible build

Hai khái niệm liên quan nhưng không đồng nghĩa:

- **Clean build:** build bắt đầu từ source/workspace không chứa output cũ không được khai báo.
- **Reproducible build:** cùng một tập đầu vào được kiểm soát có thể tạo ra output giống nhau theo tiêu chí đã chọn, thường là cùng checksum.

Clean build loại bỏ một nhóm phụ thuộc ẩn vào trạng thái workspace. Reproducible build còn cần kiểm soát compiler, dependency, OS, build flags, timestamp, thứ tự đóng gói, dữ liệu mạng và các nguồn không xác định khác. Một build có thể sạch nhưng vẫn không reproducible nếu archive ghi timestamp hiện tại hoặc dependency tải từ một URL thay đổi nội dung.

Ngược lại, hệ thống build có thể tái sử dụng build cache hợp lệ và vẫn tạo ra output reproducible, miễn cache được xác định bằng đầy đủ inputs và nội dung output được xác minh. Điều cần tránh là dựa vào tệp ngẫu nhiên còn sót lại trong workspace mà pipeline không thể giải thích.

## 12. Checklist build từ mã nguồn sạch

- [ ] Checkout đúng commit SHA vào workspace mới hoặc workspace đã được làm sạch có kiểm soát.
- [ ] Xác minh trạng thái Git và phát hiện file untracked/ignored có thể ảnh hưởng build.
- [ ] Lấy đủ submodule, Git LFS object và lịch sử/tag nếu build cần.
- [ ] Generated source được tạo từ schema/template/input đã quản lý và tool version xác định.
- [ ] Build output cũ được xóa bằng clean task phù hợp hoặc workspace mới.
- [ ] Dependency cache và build cache có khóa đầu vào, checksum và quyền truy cập phù hợp.
- [ ] Docker build context được kiểm soát bằng `.dockerignore` và không chứa secret.
- [ ] OS, toolchain, build tool và biến môi trường được ghi nhận.
- [ ] Artifact được liên kết với commit, digest, pipeline run và test report.
- [ ] Có thể chạy lại build ở workspace độc lập để điều tra khác biệt.

Khi pipeline luôn bắt đầu từ source revision xác định, tạo lại output theo quy trình khai báo và chỉ tái sử dụng cache có thể kiểm chứng, nhóm không còn phụ thuộc vào trạng thái tình cờ trên máy. Đây là nền tảng để build có thể truy vết, kiểm thử có ý nghĩa và artifact được phát hành đúng từ mã nguồn đã được chấp nhận.
