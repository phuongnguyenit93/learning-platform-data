# Phân biệt tệp nguồn, cấu hình được quản lý trong Git và đầu ra được sinh khi khởi tạo dự án Spring Boot

## 1. Vì sao phải phân loại tệp từ lúc tạo dự án?

Sau khi tải dự án từ **Spring Initializr**, thư mục dự án thường đã có mã nguồn mẫu, tệp cấu hình Maven hoặc Gradle, script wrapper và các tệp hỗ trợ. Khi chạy build lần đầu, Maven/Gradle tiếp tục tạo nhiều thư mục và file mới. Nếu đưa tất cả vào Git, repository nhanh chóng chứa JAR, class biên dịch, báo cáo test, cache và đôi khi cả thông tin nhạy cảm. Nếu bỏ sót cấu hình cần thiết, đồng đội hoặc CI có thể không tái tạo được bản build.

Hãy tách theo **vai trò và khả năng tái tạo**, thay vì chỉ dựa vào đuôi file:

1. **Tệp nguồn**: do con người viết, chỉnh sửa, hoặc là nguồn sự thật cần lưu giữ lâu dài.
2. **Cấu hình nên quản lý bằng Git**: mô tả cách biên dịch, chạy, kiểm thử, đóng gói, triển khai; các giá trị phải có thể chia sẻ an toàn.
3. **Đầu ra được sinh**: kết quả từ source + cấu hình + công cụ, có thể tạo lại bằng lệnh build hoặc tác vụ tương ứng.

Phân loại này áp dụng cho cả Maven và Gradle. Một file có thể là **cấu hình nguồn** ở `src/main/resources`, rồi xuất hiện thêm một **bản sao đầu ra** trong thư mục build; hai bản sao đó có chính sách Git khác nhau.

## 2. Nhóm 1 — Tệp nguồn cần theo dõi trong Git

Trong dự án Spring Boot Java tiêu chuẩn, những tệp sau là đầu vào của quá trình phát triển:

| Vị trí/tệp | Vai trò | Thường commit? |
|---|---|---|
| `src/main/java/**/*.java` | Mã Java của ứng dụng: `@SpringBootApplication`, controller, service, repository, model | Có |
| `src/test/java/**/*.java` | Unit test, integration test, fixture Java | Có |
| `src/main/resources/**` | Tài nguyên gốc như template, static asset, SQL migration, cấu hình runtime chia sẻ được | Có, sau khi loại bí mật |
| `src/test/resources/**` | Dữ liệu, properties và fixture đầu vào của test | Có, nếu an toàn |
| `api/openapi.yaml`, `src/main/proto/*.proto` | Đặc tả làm đầu vào sinh mã hoặc hợp đồng giao tiếp | Có |
| `README.md`, tài liệu thiết kế, script tự viết | Hướng dẫn tái tạo, vận hành và phát triển dự án | Có |

Với Kotlin, nguồn thường nằm ở `src/main/kotlin` và `src/test/kotlin`; nguyên tắc không đổi. Với giao diện web tích hợp, nguồn JavaScript/CSS gốc cũng nên commit, còn bundle được compiler tạo ra cần phân loại theo pipeline cụ thể.

**Lưu ý về thư mục `resources`:** `src/main/resources/application.yml` là tệp cấu hình gốc; bản copy trong `target/classes/application.yml` (Maven) hoặc `build/resources/main/application.yml` (Gradle) chỉ là đầu ra. Không nên commit cả hai.

## 3. Nhóm 2 — Cấu hình cần quản lý bằng Git để build tái lập

Những tệp cấu hình này không nhất thiết là mã Java, nhưng thiếu chúng có thể khiến thành viên khác tạo ra artifact khác hoặc không chạy được project:

| Tệp/thư mục | Dùng để làm gì? | Khuyến nghị |
|---|---|---|
| `pom.xml` | Maven coordinates, dependency, plugin, lifecycle, packaging | Commit |
| `build.gradle` hoặc `build.gradle.kts` | Plugin, dependency, task và cấu hình build Gradle | Commit |
| `settings.gradle` / `settings.gradle.kts` | Tên và danh sách module Gradle | Commit |
| `gradle.properties` trong project | Thuộc tính chung của build, khi không chứa token hoặc mật khẩu | Commit phần an toàn |
| `mvnw`, `mvnw.cmd`, `.mvn/wrapper/**` | Maven Wrapper và cấu hình tải/sử dụng Maven | Commit các tệp wrapper cần thiết |
| `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, `gradle/wrapper/gradle-wrapper.jar` | Gradle Wrapper, distribution và mã khởi động wrapper | Thông thường commit |
| `.gitignore`, `.gitattributes` | Quy tắc quản lý Git | Commit |
| `.github/workflows/*.yml` hoặc file CI tương đương | Tự động build/test/publish | Commit |
| `Dockerfile`, `compose.yaml`, cấu hình triển khai | Định nghĩa cách đóng gói/vận hành, nếu không chứa bí mật | Commit |
| `src/main/resources/application.yml` | Giá trị cấu hình Spring Boot dùng chung theo môi trường | Commit **nếu không có secret** |

**Wrapper là trường hợp dễ nhầm:** `gradle-wrapper.jar` là file nhị phân, nhưng được quản lý trong Git để giúp nhóm dùng được phiên bản wrapper đã định nghĩa mà không cần cài Gradle toàn cục. Đừng thêm quy tắc `*.jar` bao trùm khiến vô tình bỏ qua wrapper. Trong Maven Wrapper, thành phần thực tế phụ thuộc loại wrapper được sinh: một số dự án có `.mvn/wrapper/maven-wrapper.jar`, một số không. Giữ nguyên các tệp wrapper cần thiết do công cụ tạo; **không** bỏ qua cả `.mvn/`.

**Cấu hình build và runtime khác nhau.** `pom.xml` quyết định cách tạo sản phẩm; `application.yml` cung cấp thuộc tính ứng dụng lúc chạy. `spring.application.name`, cổng HTTP, giá trị mặc định không nhạy cảm có thể được quản lý trong Git; mật khẩu, private key, access token phải lấy từ nguồn bảo mật phù hợp.

## 4. Nhóm 3 — Đầu ra được sinh không nên commit

Khi build dự án, công cụ tạo artifact trung gian và cuối cùng từ các đầu vào đã quản lý:

| Maven | Gradle | Nội dung |
|---|---|---|
| `target/classes/` | `build/classes/` | Bytecode `.class` đã biên dịch |
| `target/test-classes/` | `build/classes/java/test/` | Bytecode test |
| `target/*.jar`, `target/*.war` | `build/libs/*.jar`, `build/libs/*.war` | Artifact đóng gói |
| `target/generated-sources/` | `build/generated/` | Mã Java/Kotlin sinh tự động bởi plugin hoặc annotation processor |
| `target/surefire-reports/` | `build/test-results/`, `build/reports/` | Kết quả test và báo cáo |
| `target/` chứa file tạm | `build/tmp/` | File làm việc trung gian |

Ngoài ra, `.gradle/` trong project là cache/trạng thái build cục bộ, thường không nên đưa vào Git. Log `*.log`, file tạm của IDE và file `.env` chứa cấu hình bí mật hoặc riêng cho máy cũng thường không được commit. Cache dependency ở thư mục người dùng như `~/.m2/repository` và `~/.gradle/caches` không phải source của repository.

**JAR ứng dụng là đầu ra, không phải đầu vào:** với project Spring Boot dùng plugin đóng gói phù hợp, executable JAR có thể chứa class ứng dụng và dependency cần thiết, được tạo lại mỗi lần build. Thông thường CI tạo artifact rồi lưu ở artifact registry hoặc hệ thống phát hành; repository Git giữ source và cấu hình tạo artifact đó.

## 5. Ví dụ cấu trúc thư mục sau khi khởi tạo và build

Giả sử Spring Initializr tạo dịch vụ `order-service` với Maven:

```text
order-service/
├── .gitignore                         # Git: cấu hình theo dõi
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties    # Git: cấu hình wrapper
├── mvnw                                # Git: script wrapper Unix
├── mvnw.cmd                            # Git: script wrapper Windows
├── pom.xml                             # Git: định nghĩa build
├── README.md                           # Git: tài liệu
├── src/
│   ├── main/
│   │   ├── java/com/acme/orders/
│   │   │   ├── OrdersApplication.java  # Git: mã Java nguồn
│   │   │   └── web/OrderController.java
│   │   └── resources/
│   │       └── application.yml         # Git: cấu hình an toàn
│   └── test/
│       └── java/com/acme/orders/
│           └── OrdersApplicationTests.java
└── target/                             # BỎ QUA: Maven tạo sau build
    ├── classes/
    ├── generated-sources/
    ├── surefire-reports/
    └── order-service-0.1.0-SNAPSHOT.jar
```

Đây là **sơ đồ minh họa**: một dự án sinh mới có thể chưa có controller, README hoặc một vài thư mục; `target/` chưa tồn tại trước lần build. Dự án dùng Gradle sẽ có `build.gradle[.kts]`, `settings.gradle[.kts]`, `gradlew`, `gradle/wrapper/` và đầu ra `build/`.

Luồng tạo đầu ra:

```text
Mã nguồn + resources + build configuration
                    |
                    v
         Maven / Gradle Wrapper
                    |
            compile + test
                    |
                    v
          target/ hoặc build/
                    |
          JAR / WAR / báo cáo
```

Git lưu **đầu vào tái tạo**; pipeline build và kho artifact nhận **đầu ra**. Khi cần xác minh một bản phát hành, ghi nhận Git commit, version, phiên bản toolchain và thông tin artifact ở CI/release.

## 6. Viết .gitignore tối thiểu và có chủ đích

Một mẫu phổ biến cho repository có thể build bằng Maven hoặc Gradle:

```gitignore
# Build output: Maven và Gradle
target/
build/
.gradle/

# Log và cấu hình cục bộ
*.log
.env
.env.*
!.env.example
```

Mẫu này chỉ là điểm khởi đầu. Có thể thêm file hệ điều hành/IDE theo nhu cầu thực tế; đừng tự động loại mọi thư mục IDE nếu nhóm cố ý chia sẻ một số cấu hình format hoặc run configuration.

- `target/` và `build/` ở mẫu này loại các thư mục cùng tên ở các mức thư mục bên dưới, hữu ích cả với multi-module.
- `.gradle/` là trạng thái cục bộ. **Không** nhầm với `gradle/wrapper/` là đầu vào cần commit.
- `.env` và `.env.*` tránh vô tình stage file môi trường máy; `!.env.example` cho phép commit file mẫu **không có bí mật**.
- Tránh quy tắc quá rộng như `*.jar`, `*.yml`, `src/main/resources/` hoặc `.mvn/` vì có thể chặn nguồn/cấu hình cần thiết.
- `.gitignore` chỉ ngăn Git tự đưa **file chưa được track** vào danh sách; nó không tự bỏ theo dõi file đã commit.

Ví dụ kiểm tra sau khi build:

```bash
git status --short
git check-ignore -v target/classes/
git ls-files target/
```

`git status --short` liệt kê thay đổi; `git check-ignore -v` cho biết quy tắc nào loại đường dẫn; `git ls-files target/` cho biết có đầu ra nào dưới `target/` đã được Git theo dõi không. Với Gradle, thay `target/` bằng `build/`. Một thư mục chưa được tạo hoặc chưa có file có thể khiến lệnh kiểm tra ignore không có kết quả hữu ích; chạy build trước khi xác minh.

Nếu output đã bị commit từ trước, chỉ thêm `.gitignore` là chưa đủ. Sau khi kiểm tra chính xác đường dẫn và quyết định loại chúng khỏi repository, có thể dùng `git rm -r --cached target/` để **bỏ theo dõi trên Git nhưng giữ file trong working tree**, rồi xem `git diff --cached` trước khi commit. Thao tác này tạo thay đổi Git cần review; không dùng bừa trên thư mục chứa mã nguồn.

## 7. Cấu hình Spring Boot: tệp nào commit, tệp nào bảo mật?

Ví dụ `src/main/resources/application.yml` có thể commit nếu chỉ chứa tên ứng dụng và tham chiếu biến môi trường:

```yaml
spring:
  application:
    name: order-service
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Khi chạy ứng dụng với datasource, hệ thống phải cung cấp các biến `DB_URL`, `DB_USERNAME`, `DB_PASSWORD` (hoặc cấu hình bên ngoài tương đương). Đây là **ví dụ cấu hình**, không phải hướng dẫn cho một ứng dụng Spring Boot trống tự kết nối được cơ sở dữ liệu; nó còn cần dependency JDBC/JPA và driver tương ứng.

Các giá trị thông thường có thể quản lý trong Git: `spring.application.name`, cấu hình logging chung, timeout mặc định, feature flag không bí mật, template cấu hình cho môi trường. Các giá trị cần bảo vệ: password thật, API key, private key, token, connection string có credential, chứng thư cá nhân. Với bí mật, dùng environment variable, secret manager hoặc cơ chế cung cấp secret của hạ tầng. Không ghi secret thật trong `application-prod.yml`, `gradle.properties` hoặc GitHub Actions YAML.

Một `.env.example` có thể ghi **tên biến và giá trị mẫu vô hại**; không copy file `.env` thật vào repository. Gitignore không bảo vệ lịch sử nếu secret đã từng được commit: khi lộ secret cần thu hồi/đổi secret, xử lý lịch sử theo quy trình của tổ chức và kiểm tra nơi artifact/log đã phát tán.

Cũng cần chú ý **tài nguyên được copy vào JAR**: nếu `src/main/resources/application.yml` chứa bí mật, đóng gói có thể đưa bí mật vào JAR. Việc không commit `target/` không giải quyết vấn đề này.

## 8. Trường hợp đặc biệt: mã nguồn được sinh và file nhị phân

**Mã nguồn sinh tự động** như Java từ OpenAPI, Protocol Buffers, annotation processor có thể xuất hiện ở `target/generated-sources/` hoặc `build/generated/`. Nếu quá trình sinh mã là một phần reproducible build, thông thường hãy commit **đặc tả đầu vào + phiên bản generator + cấu hình sinh**, rồi bỏ qua đầu ra. Như vậy tránh conflict và giảm diff ồn khi sinh lại.

Tuy nhiên, không có quy tắc tuyệt đối rằng “file được sinh luôn phải bỏ qua”. Có hệ thống chủ động commit SDK/client đã sinh để người dùng không cần generator, hoặc commit artefact do quy trình phát hành yêu cầu. Trường hợp này phải có chính sách rõ về ai sinh lại, phiên bản generator, cách review diff và khi nào làm mới file. **Nơi đặt file, khả năng tái tạo và hợp đồng phân phối** là yếu tố quyết định.

Tương tự, `gradle-wrapper.jar` là nhị phân do công cụ tạo nhưng vẫn thường commit để bootstrap build. Ngược lại, `build/libs/order-service.jar` là sản phẩm của build và thường được phát hành ra registry. Đừng phân loại chỉ dựa vào đuôi `.jar`.

Một số file “tự sinh” trong IDE (ví dụ metadata riêng của workspace hoặc index) không phục vụ tái tạo build; tránh commit trừ khi nhóm thống nhất rằng chúng là shared settings có giá trị.

## 9. Quy trình thực hành sau khi tải Spring Initializr

**Bước 1 — Xác định nguồn và cấu hình.** Mở `src/`, `pom.xml` hoặc `build.gradle`, wrapper, `.gitignore`; kiểm tra `application.properties` / `application.yml` và file profile không chứa secret.

**Bước 2 — Chạy build bằng wrapper được sinh.** Chọn **một** lệnh phù hợp với build tool:

```bash
# Maven trên macOS/Linux
./mvnw clean package

# Gradle trên macOS/Linux
./gradlew clean build
```

Trên Windows, dùng `mvnw.cmd clean package` hoặc `gradlew.bat clean build` từ thư mục project. Việc build thành công phụ thuộc JDK, kết nối tới dependency repository và cấu hình project/test.

**Bước 3 — Quan sát kết quả.** Maven thường sinh `target/`, Gradle sinh `build/`; kiểm tra rằng chúng không xuất hiện như file mới cần commit trong `git status --short`. Nếu vừa tạo repository mà chưa có commit, Git có thể liệt kê toàn bộ source/config là file chưa theo dõi, điều này bình thường.

**Bước 4 — Rà soát trước khi stage.** Dùng `git status --short` và kiểm tra `.gitignore` cho file nhạy cảm. Sau khi stage những file có chủ đích, `git diff --cached --name-only` cho biết danh sách file sẽ commit; `git diff --cached` hiển thị nội dung thay đổi dạng văn bản. Không dùng `git add .` mà bỏ qua bước kiểm tra nếu repository có cấu hình môi trường cục bộ.

**Bước 5 — Kiểm tra tái tạo.** Đồng đội hoặc CI phải có thể checkout commit, dùng đúng JDK và wrapper, tải dependency, chạy test và build JAR mà không cần copy nguyên `target/` hoặc `build/` từ máy khác. Với môi trường cần dependency riêng, phải cấu hình repository/credential ở nơi phù hợp mà không đưa credential vào Git.

## 10. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| Commit chứa hàng nghìn `.class` | Đưa `target/` hoặc `build/` vào Git | Bỏ theo dõi output, thêm ignore và review diff |
| Clone project không build được | Thiếu `pom.xml`, wrapper, plugin config hoặc khai báo dependency | Commit đủ source/config, dùng wrapper và test clean build |
| Gradle Wrapper không chạy trên máy mới | Quên `gradle-wrapper.jar` hoặc `gradle-wrapper.properties` | Kiểm tra những file wrapper cần được phân phối |
| Secret xuất hiện trong Git/JAR | Đưa password/token vào resources hoặc config | Chuyển sang external secret, thu hồi secret bị lộ, kiểm tra artifact |
| `git status` vẫn hiện output sau khi sửa ignore | Output đã được track trước đó | Xem `git ls-files`, bỏ theo dõi có kiểm soát |
| Lúc build file sinh khác nhau liên tục | Plugin/generator version hoặc đầu vào không được khóa | Xác định version, cấu hình, input và quy trình tái tạo |
| Đã sửa file trong `target/classes` nhưng chạy clean bị mất | Sửa trực tiếp file đầu ra | Sửa nguồn tương ứng ở `src/main` và build lại |

## 11. Checklist trước commit đầu tiên

- **Nguồn:** Có `src/main`, `src/test`, đặc tả và tài liệu cần thiết; không sửa trực tiếp file trong thư mục output.
- **Cấu hình:** Có Maven/Gradle build, wrapper, `.gitignore`, cấu hình CI/runtime an toàn và file mẫu để người mới biết cách chạy.
- **Đầu ra:** `target/`, `build/`, `.gradle/`, báo cáo, log và cache cục bộ đã được loại khỏi danh sách commit, trừ ngoại lệ có chính sách rõ ràng.
- **Bảo mật:** Không có password, token, private key thật trong source/config, file mẫu, lịch sử mới hoặc artifact đóng gói.
- **Tái tạo:** Checkout mới + JDK đúng + wrapper + dependency có thể chạy clean build và sinh lại artifact như kỳ vọng.

**Ghi nhớ:** Git nên lưu **mã nguồn cùng công thức để tạo ra ứng dụng**. Maven/Gradle thực thi công thức và tạo **class, báo cáo, JAR/WAR**. File có được commit hay không phụ thuộc vào vai trò của nó trong quy trình tái tạo và phát hành, không chỉ vì nó là file cấu hình, file nhị phân hay file được công cụ tự sinh.
