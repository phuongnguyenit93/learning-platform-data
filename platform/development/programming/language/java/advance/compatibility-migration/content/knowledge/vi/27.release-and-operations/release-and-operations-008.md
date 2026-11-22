# Cập nhật tài liệu hỗ trợ, môi trường phát triển và hướng dẫn vận hành

## 1. Vì sao tài liệu là một phần của Java compatibility migration?

Khi nâng JDK, nhóm kỹ thuật thường ưu tiên mã nguồn, thư viện phụ thuộc, biên dịch và kiểm thử. Nhưng một đợt migration chỉ có thể vận hành bền vững khi những người **không trực tiếp sửa code** cũng biết hệ thống yêu cầu JDK nào, thiết lập môi trường ra sao, triển khai thế nào và xử lý sự cố khi bản mới gặp vấn đề.

Giả sử một dịch vụ đã chuyển từ Java 17 sang Java 21:

- Source được compile bằng JDK 21.
- CI đã chạy integration tests.
- Container production sử dụng runtime Java 21.
- Nhưng README vẫn ghi “Java 11+”.
- Developer onboarding vẫn đặt `JAVA_HOME` vào JDK 17.
- Một hướng dẫn của support yêu cầu chạy công cụ chẩn đoán trên JDK 8.
- Runbook rollback chỉ đổi container tag, trong khi schema hoặc dữ liệu do bản mới ghi không còn tương thích với bản cũ.

Khi đó, **source code có thể đúng nhưng quy trình phát hành không nhất quán**. Người mới không dựng được dự án; support đưa hướng dẫn sai; on-call không biết JVM options/agent nào đang được chạy; khách hàng nâng sai thứ tự; hoặc rollback được runtime mà không khôi phục được khả năng xử lý dữ liệu.

Trong chủ đề **Java Advance Compatibility Migration — Phát hành và vận hành**, bài học này tập trung vào ba nhóm tài liệu:

1. **Tài liệu hỗ trợ:** Chính sách JDK/OS/architecture được hỗ trợ, phạm vi tương thích, thời hạn và thông tin cho khách hàng/support.
2. **Tài liệu môi trường phát triển:** JDK/toolchain, Maven/Gradle, IDE, test environment, container, native libraries và quy trình tái lập lỗi.
3. **Hướng dẫn vận hành:** Các bước preflight, deploy/canary, observability, incident response, rollback/roll-forward, hậu kiểm và cập nhật theo JDK security patches.

Nguyên tắc quan trọng nhất: **tài liệu không được cập nhật độc lập khỏi artifact và bằng chứng kiểm thử**. Một lời khẳng định “hỗ trợ Java 21” cần nêu điều kiện cụ thể và cách xác minh.

## 2. Kết quả mong đợi sau bài học

Người đọc có thể:

- Xây một danh mục tài liệu cần đổi khi nâng JDK.
- Phân biệt **JDK dùng để phát triển/biên dịch**, **bytecode target** và **JVM chạy production**.
- Viết ma trận hỗ trợ cho JDK release, distribution, OS, CPU architecture và runtime image.
- Cập nhật README, hướng dẫn IDE, Maven/Gradle toolchains và CI theo cùng một policy.
- Viết release notes và migration guide không gây hiểu nhầm về breaking changes.
- Chuẩn hóa runbook triển khai, canary, rollback và xử lý lỗi JDK/agent/JNI/module.
- Cung cấp cho support một bộ câu hỏi, câu trả lời và thông tin đủ để phân loại sự cố.
- Đưa tài liệu vào release gates, ownership và vòng đời cập nhật thay vì sửa sau khi sự cố đã xảy ra.

## 3. Ba tầng tài liệu phải nhất quán

~~~text
                      Product support policy
                 (what the product promises)
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
       Developer documentation              Operations runbooks
       (how to build and test)             (how to deploy and recover)
              |                                   |
              +-----------------+-----------------+
                                |
                                v
                 Release notes / Support FAQ
               (what changed and who is affected)
                                |
                                v
                   Evidence from release CI
~~~

Nếu product support policy nói “Java 17 là mức tối thiểu”, developer guide không được vô tình dùng source Java 21 cho module SDK công khai. Nếu release notes nói “Java 21 only”, runbook production không nên cố rollback về Java 17 mà không đánh giá compatibility.

### 3.1. Chính sách không đồng nghĩa ghi nhận hiện trạng

**Policy:** “SDK v4 hỗ trợ Java 17 và Java 21 trên các platform đã liệt kê.”

**Observed result:** “Build 4.2.3 đã vượt qua suite X trên Temurin 21.0.x, Linux amd64, image digest Y.”

Kết quả test tại một thời điểm hỗ trợ cho policy nhưng **không tự thay thế** chính sách. Cần ghi phạm vi cam kết, bằng chứng, owner và trạng thái rõ ràng.

### 3.2. Không để tài liệu trở thành nguồn sự thật đối nghịch

Một dự án có thể chứa README, wiki, release pages, ticket templates, Dockerfile và CI YAML. Nếu mỗi nơi tự có một bảng version, các giá trị dễ lệch. Nên xác định **một nguồn authoritative cho support matrix và JDK target**, sau đó dẫn chiếu hoặc kiểm tra nhất quán ở các tài liệu khác.

## 4. Đối tượng đọc và câu hỏi họ cần trả lời

| Đối tượng | Câu hỏi chính | Tài liệu nên cung cấp |
| --- | --- | --- |
| Developer mới | Cài JDK nào, build/test bằng gì? | README, local setup, IDE guide |
| Developer đang migration | Module nào giữ Java minimum cũ? | Compatibility policy, module matrix |
| Reviewer | Thay đổi này có phá source/binary/runtime contract không? | Architecture decision, API policy, PR checklist |
| QA/test engineer | Những JDK/OS/CPU nào là release-blocking? | Test matrix, test profiles, evidence |
| DevOps/SRE | Deploy image nào và quan sát gì? | Deployment runbook, dashboards, alerts |
| On-call | Khi JVM không khởi động hoặc crash phải làm gì? | Incident runbook, triage matrix |
| Customer support | Phiên bản khách hàng đang dùng có được hỗ trợ? | Support matrix, FAQ, escalation paths |
| Khách hàng dùng SDK | Nâng JDK có cần sửa code/compile lại? | Migration guide, release notes, examples |
| Security/compliance | Runtime có được vá và có nguồn gốc rõ không? | Patch policy, SBOM/provenance, exception register |
| Release manager | Khi nào được phát hành và ai phê duyệt? | Release gates, sign-off, rollback plan |

Nội dung nên **đúng độ sâu của đối tượng**: người dùng SDK không cần một bản giải thích toàn bộ `StackMapTable`; nhóm on-call cần câu lệnh an toàn để xác định JDK build và classpath mà không phải đọc hết source code.

## 5. Lập inventory tài liệu trước khi sửa

Khi bắt đầu migration, nên lập danh sách các địa điểm ghi yêu cầu Java:

- `README.md` và `CONTRIBUTING.md`.
- Trang “Prerequisites”, “Getting Started”, “Build from source”.
- Hướng dẫn IntelliJ IDEA, Eclipse, VS Code và Java language server.
- Maven/Gradle toolchain instructions, wrapper version, test scripts.
- Dockerfile, Helm/manifest/deployment templates và environment variables.
- CI/CD pipeline documentation, runner images, artifact publish workflows.
- Runtime prerequisites cho SDK, CLI, desktop tool hoặc service.
- API compatibility policy, platform support matrix và deprecation notice.
- Release notes, migration guide, customer FAQ, known issues.
- Runbook start/stop, health check, TLS/truststore, JVM agents, diagnostics.
- Incident response/escalation templates và operational dashboards.
- Hướng dẫn local debug, log collection, heap dump/JFR/JVM crash.
- Support macros, help center articles và sản phẩm có documentation riêng.

### 5.1. Mẫu bảng inventory

| Tài liệu | Người dùng | Những gì cần thay | Owner | Release gate |
| --- | --- | --- | --- | --- |
| Developer quick start | Developers | JDK/toolchain, IDE import | DevEx | Có |
| SDK support matrix | Customers/support | Minimum JVM, OS, arch | Product + runtime | Có |
| CI guide | Build engineers | Runner/toolchains, test profiles | CI owner | Có |
| Container operations | SRE | Image digest, startup flags, agents | Platform | Có |
| Java migration guide | Consumers | Breaking changes, actions, examples | Library owner | Có |
| Incident runbook | On-call | Error signatures, data collection | SRE | Có |
| Internal FAQ | Support | Triage và escalation | Support engineering | Tùy policy |

Một trang còn link nhưng không có owner có nguy cơ lỗi thời. Khi cập nhật tài liệu, xác định người chịu trách nhiệm trong những lần JDK/OS patch sau.

## 6. Chọn nguồn sự thật và quy tắc đồng bộ

Một cấu trúc quản lý đơn giản có thể là:

~~~text
docs/
  compatibility/
    support-policy.md
    supported-platforms.md
    module-java-targets.md
  development/
    prerequisites.md
    build-and-test.md
    ide-setup.md
  operations/
    deploy.md
    troubleshoot-java.md
    rollback.md
  releases/
    migration-java21.md
README.md
~~~

Tên file và vị trí mang tính minh họa. Điểm quan trọng là **mỗi thông tin có vị trí authoritative**, còn các entrypoints khác dẫn liên kết, tránh copy bảng rồi sửa một nửa.

### 6.1. Những giá trị nên quản lý tập trung

Nên có một nguồn dữ liệu hoặc một file chính sách duy nhất cho:

- Java minimum/runtime target.
- Supported JDK distributions và OS/CPU combinations.
- Release/version lifecycle và thời hạn ngừng hỗ trợ.
- Compiler `--release` từng module.
- CI runtime/test matrix.
- Container base image policy.
- Owners và escalation contacts.

Không cần bắt buộc mọi repository dùng một kiểu metadata, nhưng những giá trị ấy phải **có thể đối chiếu** với build/CI. Một file Markdown nói “Java 17” trong khi `build.gradle` đặt `options.release = 21` là một mâu thuẫn cần được xử lý trước release.

### 6.2. Tài liệu dưới dạng code (docs-as-code)

Khi khả thi, lưu tài liệu cùng pull request với thay đổi cấu hình:

1. Code và build settings đổi.
2. Developer guide và runbook đổi trong cùng PR hoặc release change set.
3. Reviewer kiểm tra tính khớp.
4. CI kiểm tra links, code snippets hoặc assertions có thể tự động hóa.
5. Documentation được version hóa cùng release artifact.

Những phần không thể tự động hóa vẫn cần owner/reviewer, ví dụ support contract, triage language và rollback policy.

## 7. Viết support policy trước khi ghi “Java 21 supported”

Một chính sách hỗ trợ có thể chia thành:

- **Minimum supported runtime:** JVM thấp nhất mà artifact được cam kết chạy.
- **Preferred/default runtime:** JVM được khuyến nghị cho deployment mới.
- **Certified/tested combinations:** các tổ hợp JDK vendor/build, OS và CPU có bằng chứng.
- **Build JDK:** JDK dùng cho compiler, annotation processors, generators hoặc tooling.
- **Compatibility exclusions:** những JVM vendors, OS, CPU, containers hoặc modes không được hỗ trợ.
- **Deprecation/EOL timeline:** thời điểm cảnh báo, thời điểm ngừng cập nhật và thời điểm không hỗ trợ.
- **Exception handling:** quy trình xin ngoại lệ có owner và expiry.

Ví dụ policy minh họa:

~~~text
Product release: Service A 5.x
Build toolchain: JDK 21
Compiled artifact target: Java 17 for shared-client module
Service runtime: Java 21 on approved Linux images
Supported production JDK vendor: approved distributions listed below
Supported architecture: linux/amd64
linux/arm64: candidate until native/agent validation is complete
Java 11 runtime: not supported for this product release
Security update policy: approved JDK patch baseline per update cycle
Support owner: runtime-platform and product engineering
~~~

Đây là cấu hình giả định để minh họa hình thức. Không nên copy các lựa chọn platform này vào một sản phẩm thực mà chưa xác nhận vendor support, sản phẩm và kiểm thử tương ứng.

### 7.1. “Build bằng JDK 21” không nghĩa “yêu cầu Java 21”

Ví dụ compiler JDK 21 có thể biên dịch một module bằng `--release 17`, tạo class files và giới hạn Java SE APIs theo Java 17. Nhưng một module khác cũng build bằng JDK 21 có thể dùng `--release 21`.

Tài liệu phải ghi rõ **module nào yêu cầu runtime nào**. Một câu chung “dùng JDK 21” không đủ cho multi-module project hoặc SDK có consumers bên ngoài.

### 7.2. Không hứa “mọi JVM vendor”

Các bản phân phối Java cùng release thường tuân theo Java SE compatibility, nhưng các khác biệt về packaging, provider, JVM implementation, native libraries, JVM flags và support lifecycle vẫn có thể quan trọng.

Hãy nêu:

- Vendor/distribution cụ thể đã được kiểm thử và được phê duyệt.
- OS/architecture đúng theo binary vendor cung cấp.
- Những JVM implementations/flags được hỗ trợ.
- Điều kiện cần thêm khi có FIPS, JFR, JNI hoặc native profiler.

Một platform chạy được trong thử nghiệm không tự động trở thành hợp đồng support dài hạn.

## 8. Ma trận platform cần công bố như thế nào?

Mẫu:

| Java | Distribution | OS/image | Architecture | Trạng thái | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| 17.x được duyệt | Vendor A | Linux glibc image X | amd64 | Supported baseline | Legacy services |
| 21.x được duyệt | Vendor A | Linux glibc image Y | amd64 | Supported target | Full regression |
| 21.x được duyệt | Vendor B | Linux glibc image Y | amd64 | Candidate | Awaiting full validation |
| 21.x được duyệt | Vendor A | Linux glibc image Y | arm64 | Experimental | JNI/agent checks pending |
| 21.x được duyệt | Vendor A | Linux musl image Z | amd64 | Unsupported | No approved native binary |

Các vendors A/B và images X/Y/Z chỉ là placeholders. Ở bản thật phải thay bằng **tổ hợp có chứng cứ**, ngày xác nhận và link tới test evidence.

### 8.1. Tách supported, validated, experimental và unsupported

- **Supported:** nằm trong product policy, có trách nhiệm hỗ trợ.
- **Validated:** đã được kiểm thử với artifact/JDK build cụ thể.
- **Experimental:** có dữ liệu thăm dò nhưng chưa có cam kết.
- **Unsupported:** ngoài phạm vi hoặc không có binary/khả năng vận hành phù hợp.

Một hàng `NOT_RUN` trong CI cho tổ hợp supported **không phải PASS**. Nếu thiếu runner/agent phù hợp, báo rõ gap.

### 8.2. Runtime image cũng là một phần của môi trường

Với containers, một nhãn `eclipse-temurin:21` hoặc một tag tương tự có thể trỏ tới các bản vá qua thời gian. Để tái hiện release, nên lưu **image digest**, platform và full JDK build. Đối với image nhiều architecture, ghi actual platform/child image tương ứng.

## 9. Ghi mức Java tối thiểu và phương án nâng cấp cho khách hàng

Khách hàng có thể dùng:

- Một ứng dụng server do tổ chức tự deploy.
- SDK/JAR mà họ nhúng vào ứng dụng chạy JDK khác.
- CLI hoặc desktop tool phân phối kèm JRE/JDK.
- Container image được vendor cung cấp.

Mỗi loại cần câu chữ khác nhau.

**Server-managed deployment:** “Từ bản 5.0, container do nhà cung cấp phát hành chạy Java 21; khách hàng dùng API qua HTTP không phải tự cài Java trừ khi có thành phần client Java riêng.”

**SDK/JAR:** “SDK 4.x yêu cầu JVM Java 17 trở lên. Project build bằng JDK mới hơn phải vẫn dùng target release phù hợp nếu muốn chạy trên Java 17.”

**CLI tool:** “Bản 3.x yêu cầu JDK 21 đã được cài trong PATH hoặc được phân phối kèm runtime; không hỗ trợ chạy bằng Java 11.”

Không nên viết câu chung “Đã nâng lên Java 21” mà không nêu **ai phải làm gì**.

### 9.1. Phân biệt source, binary và behavior compatibility

Release notes nên trả lời:

| Loại tương thích | Câu hỏi |
| --- | --- |
| Source | Consumer build lại có phải sửa code không? |
| Binary | JAR đã compile trước có còn liên kết với API mới không? |
| Runtime | Class-file version và Java SE APIs có chạy trên JDK đã cam kết không? |
| Data/protocol | JSON, XML, protobuf, serialization, database có đọc chéo được không? |
| Operational | Startup flags, agents, TLS, logging/monitoring có thay không? |

Không sử dụng “backward compatible” nếu chưa xác định rõ tương thích trên chiều nào.

## 10. Cập nhật README: phần prerequisites nên viết gì?

Một đoạn có tính thực thi:

~~~markdown
## Prerequisites

- JDK: 21, approved distribution and patch level
- Build tool: repository Maven/Gradle Wrapper
- Container runtime: required for integration tests
- OS: developer platforms listed in supported-platforms.md

The service runs on Java 21. The shared SDK module is
compiled with --release 17 for supported Java 17 consumers.

Check your environment:

    java -version
    javac -version
    ./gradlew --version

Do not rely on the IDE Project SDK as proof of the build
or test JVM.
~~~

Trong tài liệu thật, thay “approved distribution and patch level” bằng nguồn version duy nhất hoặc liên kết policy có thể kiểm chứng. Chọn `./gradlew` **hoặc** `./mvnw` theo repository, đừng đưa cả hai nếu dự án chỉ có một.

### 10.1. README cần là cổng vào ngắn

README nên chứa:

1. Yêu cầu Java chính.
2. Lệnh kiểm tra môi trường.
3. Lệnh build/test cơ bản.
4. Hướng dẫn chọn toolchain.
5. Đường dẫn đến troubleshooting/migration/support matrix.

Tránh nhồi mọi runbook chuyên sâu vào README. Người đọc nên có con đường từ “cài được và build được” đến “vận hành và xử lý sự cố”.

## 11. Developer quick start: từ máy trống đến test pass

Một hướng dẫn setup nên theo trình tự tái lập:

1. Cài **JDK distribution và release được duyệt**, đúng OS/CPU.
2. Xác nhận command line `java` và `javac` đang trỏ đúng installation.
3. Đặt `JAVA_HOME` nếu wrapper/tooling cần, không hardcode absolute path trong repository.
4. Chạy Maven/Gradle Wrapper đã pin trong dự án.
5. Provision local dependencies: database/test containers, brokers, certificates theo policy.
6. Thiết lập environment configuration không chứa secrets thật trong source.
7. Import project vào IDE và kiểm tra module language levels.
8. Chạy compile và unit tests.
9. Chạy integration smoke, kiểm tra một endpoint/workflow cốt lõi.
10. Xem cách reset local state và log lỗi nếu test thất bại.

Mỗi bước cần ghi **lệnh, điều kiện tiên quyết và tiêu chí thành công**, không chỉ “install Java and run app”.

### 11.1. Phát hiện PATH và JAVA_HOME lệch nhau

Ví dụ trên shell POSIX:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
command -v java
~~~

Trên PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
~~~

Nếu `JAVA_HOME` trỏ JDK 21 nhưng command `java` tìm trong PATH lại là JDK 17, tài liệu phải hướng dẫn thống nhất môi trường thay vì nói “chỉ cần cài JDK 21”.

### 11.2. Không dựa vào một lệnh của hệ điều hành trên mọi máy

Không lấy `readlink` hoặc `where` làm cách duy nhất cho tất cả OS. Ghi lựa chọn theo shell/hệ điều hành và giải thích output mong đợi.

## 12. Maven: ghi đúng JDK, compiler release và toolchains

Ví dụ một module muốn dùng JDK 21 compiler nhưng phát hành artifact hỗ trợ Java 17:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Khi dùng Maven Compiler Plugin, cần chọn version đã được phê duyệt, hỗ trợ tổ hợp Maven/JDK. Nếu dự án dùng Maven Toolchains, ghi rõ:

- JDK nào chạy chính `mvnw`/Maven process.
- JDK nào được compiler plugin/toolchains chọn.
- Test runner Surefire/Failsafe chạy JVM nào.
- `--release` của từng module.
- Annotation processors và code generators có yêu cầu JDK riêng không.

Lệnh kiểm tra:

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw verify
~~~

`./mvnw` chỉ là ví dụ cho repository có Maven Wrapper; trên Windows có thể dùng `mvnw.cmd` theo hướng dẫn project. Không ghi một lệnh Unix duy nhất như thể chạy được trên mọi Windows PowerShell installation.

### 12.1. Một lỗi hỗ trợ thường gặp

~~~text
error: release version 21 not supported
~~~

Thông điệp này thường gợi ý compiler JDK đang dùng **không hỗ trợ target release được yêu cầu**. Chỉ tăng Project SDK trong IDE có thể không thay JDK mà Maven/compiler thực sự dùng. Support guide nên yêu cầu gửi `mvn -version`/toolchain details thay vì chỉ screenshot IDE.

## 13. Gradle: phân biệt daemon JVM, toolchain và target

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Đây là cấu hình minh họa compiler toolchain Java 21, target Java 17. Nhưng:

- Gradle **daemon JVM** có thể khác compiler toolchain.
- Gradle Wrapper version phải được hỗ trợ trên JVM chạy daemon.
- `Test` tasks có thể dùng Java launcher được chỉ định riêng.
- Những module yêu cầu Java 21 runtime có thể có `options.release = 21` riêng.
- IDE import Gradle model có thể bị lệch nếu cấu hình JVM của IDE không đồng bộ.

Các lệnh phổ biến:

~~~bash
./gradlew --version
./gradlew :app:compileJava
./gradlew :app:test
~~~

Không hướng dẫn chạy một command cho module `app` nếu repository thực tế dùng tên module khác; đó là placeholder cần đổi.

### 13.1. Luôn mô tả wrapper version

Nên chạy `./gradlew`/`./mvnw` từ repository thay vì dùng Gradle/Maven global tùy developer, trừ khi dự án đã có chính sách khác. Wrapper là một phần tính tái lập nhưng vẫn cần Java runtime/build environment phù hợp.

## 14. IDE setup: cùng một hợp đồng, nhiều editor

Developer guide phải phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| IDE runtime | JVM chạy chính IDE/language server |
| Project SDK | JDK IDE gắn với project |
| Module language level | Cú pháp Java được IDE coi hợp lệ cho module |
| Gradle JVM/Maven JDK | JVM cho build integration/runner |
| Compiler toolchain | JDK thực sự chạy `javac` hoặc compiler tương ứng |
| Target release | Java SE API/bytecode mà artifact được phát hành |
| Test JVM | JVM chạy unit/integration tests |

### 14.1. IntelliJ IDEA

Hướng dẫn nên yêu cầu kiểm tra Project SDK, Module language level, Gradle JVM hoặc Maven runner/importer JDK, annotation processing và các plugin cần thiết. Tên menu có thể đổi theo release IDE, vì vậy nên chỉ rõ **các khái niệm cần chọn** và cập nhật screenshots khi UI thay đổi, không dùng screenshot cũ như nguồn chân lý.

### 14.2. Eclipse/ECJ

Kiểm tra Installed JRE/JDK, compiler compliance level, build path, Maven m2e hoặc Gradle Buildship và plugin dựa trên JDT AST. ECJ và `javac` có thể có diagnostics khác nhau; build chính thức vẫn cần dùng compiler/toolchain đã định trong pipeline.

### 14.3. VS Code Java

Kiểm tra Java extension/language server, Java runtimes, Gradle/Maven import và project language level. JVM chạy language server không nhất thiết là Java compiler/runtime của ứng dụng.

### 14.4. Cập nhật ví dụ ngay khi đổi ngôn ngữ nguồn

Nếu module chỉ hỗ trợ source Java 17, tài liệu không nên dùng pattern switch hoặc record patterns mà chỉ Java 21 có thể biên dịch theo ngôn ngữ chính thức. Nếu ví dụ dùng tính năng Java mới, ghi rõ feature release của ví dụ.

## 15. Cấu hình môi trường: không copy secrets và đường dẫn máy cá nhân

Một hướng dẫn tốt phân biệt:

- **Required public settings:** profile, endpoint local, feature flag.
- **Secrets:** credentials, tokens, private keys; dùng secret manager hoặc cơ chế được duyệt.
- **Developer overrides:** hostname/port, test fixture path.
- **Production-owned settings:** truststore, JVM flags, agent config, container resources.

Ví dụ:

~~~text
APP_PROFILE=local
APP_HTTP_PORT=8080
APP_DB_URL=jdbc:postgresql://localhost:5432/app
JAVA_TOOL_OPTIONS=<approved-local-options-if-required>
~~~

Giá trị chỉ minh họa. Đừng đưa password thật vào README hoặc log `JAVA_TOOL_OPTIONS` nếu chứa secrets. Nếu một endpoint được cung cấp bởi mock/test container, nói rõ nó không phải production URL.

### 15.1. Đường dẫn đa nền tảng

Không commit `C:\Users\Alice\jdk-21` hoặc `/Users/bob/.sdkman/...` vào config chung. Dùng toolchain resolver, environment variables và local-only settings khi phù hợp.

### 15.2. Chú ý `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`

Những biến này có thể đưa options vào Java process mà developer không thấy trong build file. Chúng ảnh hưởng `-javaagent`, module opens, memory, logging và security. Hướng dẫn debug nên yêu cầu kiểm tra JVM arguments thực tế và redact dữ liệu nhạy cảm.

## 16. Cập nhật local integration-test prerequisites

Khi nâng JDK, developer có thể cần những dịch vụ phụ:

- Database container và schema migrations.
- Kafka/RabbitMQ hoặc message broker tương ứng.
- TLS certificates cho test mTLS.
- Testcontainers/Docker runtime có quyền phù hợp.
- Native libraries cho JDBC compression, cryptography, image processing hoặc JNI.
- Test data fixtures nhiều phiên bản.
- Mock HTTP servers, local cloud emulators.
- Java agent coverage/mocking được hỗ trợ.

### 16.1. Tiêu chí “setup đã thành công”

Không chỉ ghi:

~~~bash
./gradlew test
~~~

Nên nêu:

~~~text
Expected:
- Gradle/Maven process starts with approved JDK configuration.
- Unit tests complete successfully.
- Integration test service containers start.
- No tests silently skipped due to unavailable Docker.
- Test reports are available at documented locations.
- Java agent/coverage tools remain functional.
~~~

Nếu suite cần credentials hoặc service không thể provision local, cung cấp một profile local rõ ràng và một profile CI đầy đủ; không đánh tráo “local test pass” thành “mọi release gate pass”.

## 17. Native libraries và agent dependencies trong developer guide

Source Java portable, nhưng ứng dụng có JNI/JNA hoặc native agents có thể không chạy trên mọi OS/architecture:

- `.dll` trên Windows.
- `.so` trên Linux.
- `.dylib` trên macOS.
- Kiến trúc `amd64/x86_64` hoặc `arm64/aarch64`.
- Linux `glibc` khác `musl` ở nhiều trường hợp.
- Native dependency cần version/ABI phù hợp.

Tài liệu local setup phải nêu:

1. Native artifact nào được phép dùng.
2. OS/architecture nào được hỗ trợ.
3. Cách provision binary (không tải DLL tùy ý).
4. Cách kiểm tra library presence và architecture.
5. Cách kiểm thử chức năng thật sự gọi native path.
6. Khi nào báo thiếu hỗ trợ thay vì cố sửa bằng thư viện không tin cậy.

### 17.1. Một lỗi mẫu

~~~text
java.lang.UnsatisfiedLinkError: no nativecodec in java.library.path
~~~

Hướng dẫn support nên phân biệt thiếu native library, library đúng tên nhưng thiếu dependency, sai CPU ABI, khác libc và JNI symbol mismatch. Đừng chỉ gợi ý “thêm folder vào java.library.path” cho mọi tình huống.

### 17.2. APM/coverage/Mockito

Khi đổi JDK, Java agent và công cụ bytecode có thể cần nâng. Một cảnh báo về dynamic agent loading hoặc lỗi `Unsupported class file major version` không thể được giải thích chỉ bằng thay `JAVA_HOME`. Cần ghi version của agent/framework, thời điểm startup/dynamic attach và JDK target.

## 18. CI/CD documentation: mô tả các môi trường thực sự được kiểm thử

Hướng dẫn CI cần ghi:

- CI provider/runner OS và architecture.
- JDK distribution, feature release và full update/build.
- JDK chạy build tool, compiler toolchain và test JVM.
- `--release` của modules.
- Test profiles và release-blocking matrix rows.
- Container image digests, Docker build platforms.
- Native/agent dependencies.
- Artifacts lưu sau test: reports, logs, SBOM, checksums.
- Gating policy khi fail/skipped/not run.

### 18.1. Đừng lấy runner label làm bằng chứng đầy đủ

Một job ghi `ubuntu-latest` có thể đổi OS image khi CI provider cập nhật. Một job có biến `arch: arm64` không chứng minh nó chạy trên ARM64 thật. Với release-blocking validations, hãy lưu runtime fingerprint và OS/CPU thực tế.

### 18.2. Ví dụ ma trận CI ở mức dữ liệu

~~~yaml
platforms:
  - id: linux-amd64-jdk17
    jdk_release: "17"
    distribution: approved-vendor-a
    os: linux
    architecture: amd64
    profile: full
    purpose: baseline

  - id: linux-amd64-jdk21
    jdk_release: "21"
    distribution: approved-vendor-a
    os: linux
    architecture: amd64
    profile: full
    purpose: target

  - id: linux-arm64-jdk21
    jdk_release: "21"
    distribution: approved-vendor-a
    os: linux
    architecture: arm64
    profile: native-integration
    purpose: candidate
~~~

Đây là **dữ liệu minh họa**, không phải cấu hình sẵn của mọi CI provider. Bản thật cần xác nhận runner availability, JDK distribution support và policy.

## 19. Release gates: tài liệu cũng cần điều kiện hoàn tất

Một đợt migration nên có các tiêu chí:

| Nhóm | Release gate |
| --- | --- |
| Source/build | Compile bằng toolchain đã duyệt, target phù hợp |
| Regression | Tests pass trên mandatory JVM/OS/architecture |
| API | Consumer binary/source compatibility theo contract |
| Native/agents | Integration và instrumentation hoạt động |
| Security | JDK patch, TLS/crypto và SBOM/provenance được kiểm |
| Operations | Image/config/health/observability được xác nhận |
| Documentation | README, support matrix, migration guide và runbook đã cập nhật |
| Support readiness | FAQ, triage, known issues và escalation đã sẵn |
| Rollback | Đã kiểm thử hoặc có giới hạn được phê duyệt |

Không nên chỉ ghi “docs done” bằng một checkbox không có cách kiểm tra. Cần ít nhất link tài liệu, owner/reviewer và release commit/version.

### 19.1. Nếu tài liệu chưa hoàn tất?

Một ứng dụng có thể chạy đúng nhưng không thể vận hành an toàn do thiếu hướng dẫn rollback hoặc support chưa biết minimum JDK mới. Theo policy, đây có thể là **release blocker**, không phải tác vụ “sẽ bổ sung sau”.

## 20. Changelog và release notes phải trả lời điều gì?

Release notes cần ngắn nhưng đầy đủ:

1. **Phiên bản nào bị ảnh hưởng?**
2. **Java minimum mới là gì?**
3. **Khách hàng phải làm gì trước khi nâng?**
4. **Có breaking source/binary/runtime changes không?**
5. **Có thay đổi container image, OS/CPU support, TLS/JVM flags hoặc agent không?**
6. **Điều gì vẫn tương thích?**
7. **Có known issues hoặc unsupported configurations không?**
8. **Cách kiểm tra sau upgrade và cách rollback?**
9. **Link migration guide, support matrix và ngày chính sách có hiệu lực?**

### 20.1. Mẫu release notes

~~~markdown
### Java runtime and platform compatibility

- Runtime baseline: Java 21 for the server component.
- Shared client SDK: Java 17 remains the minimum when
  using the release artifact built with --release 17.
- Deployment image: use the published, approved image
  digest for this release.
- Updated: JDK support matrix, developer setup guide
  and operations runbook.
- Action required: review custom JVM flags, agents,
  JNI/JNA libraries, truststore and container settings.
- Verification: run the documented smoke and
  integration checks after deployment.
- Known limitations: see supported-platforms.md.
- Rollback: follow the version-specific runbook;
  database or message schema changes may affect rollback.
~~~

Đây là mẫu chứ không phải chính sách chung. Nếu Java minimum thật đã thay từ 17 sang 21 cho **tất cả artifacts**, không được giữ câu SDK 17.

### 20.2. Tránh từ ngữ mơ hồ

Không nên chỉ ghi:

> “Updated Java compatibility.”

Thay bằng: “Module `server` yêu cầu JVM Java 21 từ phiên bản 5.0; module `client-sdk` vẫn hỗ trợ Java 17 và 21 theo ma trận công bố. Các bản Java 11 không còn thuộc phạm vi hỗ trợ kể từ ngày và phiên bản được nêu.”

## 21. Migration guide: dành cho người phải chuyển từ bản cũ

Một migration guide không chỉ liệt kê thay đổi; nó là **trình tự thao tác có kiểm tra**:

~~~text
Before upgrade
  -> Confirm currently deployed release/runtime
  -> Check target support matrix
  -> Inventory JVM flags, agents, native libraries
  -> Back up data/config when required
  -> Validate deployment and rollback prerequisites

Prepare
  -> Update JDK/toolchain/runtime image
  -> Align dependencies and build target
  -> Validate security certificates/truststores
  -> Run regression and cross-version tests

Deploy
  -> Canary with approved artifact/image
  -> Health and observability checks
  -> Gradually increase traffic

After upgrade
  -> Verify core business workflows
  -> Verify logs/traces/metrics/alerts
  -> Record exact JDK/image/artifact versions
~~~

### 21.1. Mọi bước cần điều kiện thành công

Ví dụ “Update JDK” nên kèm:

~~~text
Input: approved runtime image and target release
Action: deploy image to staging
Success:
  - java.version and image digest match the release plan
  - application starts and health endpoints pass
  - mandatory workflows pass
Failure: stop rollout and follow incident runbook
~~~

### 21.2. Nêu đường nâng không được hỗ trợ

Nếu framework hoặc driver yêu cầu migration trung gian, tài liệu phải nói rõ. Ví dụ khách hàng Java 8 không thể nâng thẳng SDK phiên bản mới nếu minimum Java đã là 17 mà không nâng runtime hoặc chọn artifact phù hợp trước.

## 22. Mẫu so sánh “trước và sau”

| Hạng mục | Trước migration | Sau migration | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| Runtime production | Java 17 image | Java 21 image | Platform |
| Java build JDK | 17 | 21 | Build/DevEx |
| SDK compile target | 17 | 17 (giữ nguyên) | SDK owner |
| Framework/driver | Version cũ | Version tương thích JDK 21 | Service owner |
| APM agent | Version cũ | Vendor-supported version | Observability |
| JVM module flags | Workarounds cũ | Đã review/loại phần dư | Platform/security |
| CI matrix | JDK 17 | JDK 17 + 21 theo policy | QA/CI |
| Developer setup | JDK 17 mặc định | JDK 21, mục SDK tách riêng | DevEx |
| Runbook | Health/startup cũ | Thêm runtime validation/rollback | SRE |
| Support FAQ | “Java 17” | Nêu đúng các module và thời hạn | Support |

Các giá trị chỉ minh họa. Quan trọng là tránh đổi đồng loạt mọi JDK trong tài liệu khi một số artifact vẫn phải giữ Java minimum thấp.

## 23. Runbook vận hành bắt đầu bằng preflight

Một runbook phải làm được việc lúc on-call không có tác giả bên cạnh. Phần preflight cần trả lời:

- Release artifact/image digest chính xác nào sẽ deploy?
- JDK vendor/build trong image là gì?
- Container OS/architecture có khớp với node pool không?
- Agent/JNI/native libraries có bản phù hợp không?
- Truststore/certificates và secrets được provision chưa?
- Schema/database/message compatibility đã được kiểm tra chưa?
- Feature flags và config migration có backward compatible không?
- Dashboards/alerts và sample traffic checks có sẵn chưa?
- Nếu rollback, artifact cũ có đọc được dữ liệu mới không?

### 23.1. Một mẫu preflight

~~~text
[ ] Approved release identifier and artifact checksum
[ ] Approved JDK build and immutable image digest
[ ] Correct OS / CPU architecture / libc
[ ] JVM flags and agents reviewed for target JDK
[ ] Required environment/secret references resolved
[ ] Data migration and rollback constraints reviewed
[ ] Mandatory CI regression gates passed
[ ] Monitoring dashboards and alerts functional
[ ] On-call, release manager and rollback owner assigned
[ ] Deployment window/communications approved
~~~

Một checkbox nên trỏ tới bằng chứng. “Approved JDK build” không đủ nếu không ghi build/release identifier thật.

## 24. Deployment runbook phải có bước kiểm chứng runtime

Một sơ đồ:

~~~text
Validate release artifact
           |
           v
Deploy to staging / canary
           |
           v
Verify JDK build, image, JVM arguments
           |
           v
Health + business smoke checks
           |
           v
Compare errors, latency, memory, GC, traces
           |
       Gate decision
        /      \
       v        v
  Promote     Stop / rollback / investigate
       |
       v
  Post-release evidence and sign-off
~~~

### 24.1. Startup command ví dụ

~~~bash
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log \
     -javaagent:/opt/agents/approved-agent.jar \
     -jar service.jar
~~~

Đây là ví dụ cú pháp trên HotSpot/Linux-like environment, không phải lệnh khuyến nghị cho mọi service. Một runbook thật cần **đúng** startup flags, agent file và quyền ghi thư mục logs theo deployment. Không tự thêm flags/agent vào production nếu không được cấu hình/phê duyệt.

### 24.2. JVM option nằm ở đâu?

Trong Kubernetes, startup options có thể xuất hiện ở container command/args, entrypoint script, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` hoặc platform agent injection. Tài liệu phải nêu vị trí authoritative và cách xem config của **process chạy thực**, vì một thay đổi chart có thể không giống command chạy trong local shell.

## 25. Canary và rollout theo độ rủi ro

Nâng JDK có thể tác động performance, GC, native libraries, TLS, reflection và instrumentation. Một canary nên có:

1. Một nhóm instances/replicas có **JDK+image+agent versions được xác định**.
2. Traffic tương đương hoặc có các synthetic transactions.
3. So sánh với baseline còn hoạt động.
4. Các tiêu chí stop/go theo functional errors và SLO.
5. Chủ sở hữu có quyền quyết định rollback.
6. Thời điểm/phạm vi tăng traffic được duyệt.

### 25.1. Những số liệu nên xem

| Chỉ số | Lý do |
| --- | --- |
| Startup/ready time | JDK/agent/framework initialization regressions |
| HTTP 5xx/error rate | Sự cố nghiệp vụ/communication |
| p95/p99 latency | JIT, GC, lock contention hoặc native overhead |
| CPU/memory/GC | Heap, metaspace, direct/native usage, allocation |
| Thread pool/queue depth | Concurrency/backpressure |
| TLS handshake failures | Security provider/truststore |
| DB pool failures | Driver và network compatibility |
| Traces/spans/metrics | APM auto-instrumentation vẫn hoạt động |
| JVM crashes/OOMKills | Native/agent/GC/container issues |
| Data correctness signals | Schema/serializer/cross-version regressions |

Chỉ số được lựa chọn theo workload. Không định nghĩa ngưỡng tùy ý cho mọi sản phẩm; dùng SLO/error budget và baseline đã được nhóm thống nhất.

## 26. Rollback phải được mô tả như một thao tác có điều kiện

Rollback container image chỉ khôi phục **runtime artifact**. Nó không tự đảo ngược:

- Database schema migration.
- Dữ liệu serialized đã được producer mới ghi.
- Message payload mới trong queue/topic.
- Thay đổi encryption/signature format.
- External side effects hoặc state đã cập nhật.
- Tương thích các client/server instances chạy song song.
- Feature flags/config thay đổi ở bên ngoài image.

Một runbook rollback cần ghi **điều kiện được phép**, không chỉ một command “deploy previous image”.

### 26.1. Mẫu quyết định rollback

~~~text
IF:
  the previous application release can read current data
  AND no incompatible schema/protocol changes have been applied
  AND the previous runtime image remains available and approved
THEN:
  rollback application deployment according to release procedure
  verify health, business behavior, tracing and error rates
ELSE:
  stop automatic rollback
  escalate to incident commander / data owner
  use documented roll-forward or data recovery procedure
~~~

Đây là sơ đồ ra quyết định; không phải một script tự động. Nếu dữ liệu đã thay đổi, rollback “nhanh” có thể gây mất dữ liệu hoặc tạo lỗi mới.

### 26.2. Thử rollback trước khi cần

Trong staging với dữ liệu mô phỏng/fixture:

1. Deploy bản cũ, tạo dữ liệu hợp lệ.
2. Nâng lên bản mới và thực hiện kịch bản có thay đổi state.
3. Thử các đường đọc/ghi chéo phiên bản nếu policy yêu cầu.
4. Thử rollback hoặc roll-forward theo kịch bản.
5. Ghi giới hạn, thời gian phục hồi và các bước manual cần phê duyệt.

## 27. Incident runbook: phân loại nhanh lỗi JDK migration

| Dấu hiệu | Tầng cần kiểm tra | Bằng chứng cần yêu cầu |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Runtime thấp hơn class-file target | `java -version`, `javap -verbose`, artifact |
| `NoSuchMethodError`/`NoSuchFieldError` | JAR/ABI mismatch | Resolved dependencies, loaded class |
| `NoClassDefFoundError` | Missing class hoặc failed initialization | Lỗi đầu tiên, classpath, `Caused by` |
| `InaccessibleObjectException` | Reflection/JPMS access | Package/module, library version, flags |
| `VerifyError` | Bytecode malformed/transformer | Class bytes, bci, agent/tool versions |
| ASM “major version unsupported” | Bytecode parser chưa hỗ trợ | ASM/Byte Buddy/agent version |
| `UnsatisfiedLinkError` | JNI/native path/ABI | OS/arch/libc, native library dependencies |
| TLS handshake failure | Truststore/security policy | Provider/cert/endpoint configuration |
| JDK crash, `hs_err_pid*.log` | JVM/native/agent fatal error | Problematic frame, native libraries |
| Dynamic agent loading warning | JEP 451/policy khi phù hợp | JDK release, agent mode, vendor docs |
| Container OOMKill | Resource limits/heap/direct/native memory | JVM args, cgroup limits, workload |

Đây là **bảng phân tuyến**, không thay stack trace đầy đủ. Support/on-call phải tìm lỗi đầu tiên và xác định runtime/artifact thực tế trước khi gợi ý sửa.

## 28. Thu thập thông tin khi JVM không khởi động

Một phần runbook có thể yêu cầu:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Với JDK và quyền phù hợp, có thể dùng:

~~~bash
jcmd <pid> help
jcmd <pid> VM.command_line
~~~

`<pid>` phải được thay bằng process ID của JVM **được phép quản trị**. Không chạy attach/debug vào process của bên khác. Lệnh `jcmd` cũng không bảo đảm khả dụng ở mọi runtime image, JVM implementation hoặc khi attach mechanism bị cấm.

### 28.1. Bằng chứng quan trọng

~~~text
Application release / build SHA:
JDK distribution, java.version, java.runtime.version:
JVM implementation:
OS/image/architecture/libc:
Artifact and image checksum:
JVM startup flags and JAVA_TOOL_OPTIONS (redacted):
Agents and native libraries:
First exception or fatal error:
Container events/restart reason:
Last known good environment:
Reproduction steps:
~~~

Đừng tự động gửi `-XshowSettings` output, environment, core dump hoặc heap dump chưa lọc tới kênh hỗ trợ công khai; chúng có thể chứa thông tin nhạy cảm.

## 29. Hướng dẫn JVM crash và native failure

Nếu JVM crash, có thể xuất hiện `hs_err_pid<id>.log` trên HotSpot, hoặc các crash logs khác theo vendor. Runbook nên nêu:

- Vị trí dự kiến lưu fatal error log.
- Quyền ghi và cơ chế giữ log khi container restart.
- Cách xác định problematic frame và native module.
- Khi nào cần core/minidump/JFR.
- Quy định an toàn dữ liệu cho heap/core dump.
- Kênh escalation tới JVM vendor hoặc native library owner.

### 29.1. Không nhầm lỗi nạp native với JVM crash

`UnsatisfiedLinkError` có thể chỉ là Java `Error` khi loader không tìm được thư viện hoặc symbol. `SIGSEGV`/access violation ở native code có thể kết thúc tiến trình và cần fatal error log/core.

Không khuyên user dùng `try/catch(Throwable)` để “bắt” mọi native crash; đó không phải cơ chế an toàn cho fatal signals.

### 29.2. Agent cũng là dependency runtime

Một `-javaagent`, coverage tool hoặc profiler có thể tự mang native/bytecode libraries. Khi nâng JDK, cần ghi agent version, cách nạp startup/dynamic, module access, permissions và vendor compatibility. Không đánh giá chỉ bằng “application JAR không đổi”.

## 30. Runbook về TLS, truststore và security

Security defaults/algorithms/certificates có thể thay giữa JDK releases, updates, distributions và images.

Tài liệu cần trả lời:

- Truststore thuộc image JDK hay được ứng dụng cung cấp?
- CA certificates được cập nhật bằng quy trình nào?
- Có dùng keystore, mTLS, PKCS#11/HSM hoặc FIPS không?
- Security providers/algorithms nào là bắt buộc?
- Có proxy/certificate interception trong môi trường test không?
- Khi TLS handshake fail, thu thập bằng chứng thế nào mà không lộ private keys?
- Ai có quyền thay policy và ai phê duyệt?

### 30.1. Không vô hiệu hóa TLS verification để vượt migration

Nếu chứng chỉ không được trust hoặc thuật toán bị cấm, fix phải xuất phát từ policy/truststore/provider đúng. Không đưa lời khuyên “trust all certificates”, tắt hostname verification hoặc mở rộng cipher suites một cách mù quáng.

### 30.2. Lệnh debug cần có cảnh báo an toàn

Những flags làm tăng TLS logging có thể tạo dữ liệu nhạy cảm/khối lượng lớn. Trong runbook, ghi rõ:

~~~text
Use only in an approved test or incident context.
Enable for a bounded diagnostic window.
Redact endpoint names, tokens and sensitive certificate details.
Disable verbose logging after collecting evidence.
~~~

Không bật debug chi tiết thường trực chỉ để “dễ điều tra”.

## 31. Operational monitoring phải thay khi JVM/agent thay đổi

Monitoring dashboard có thể dựa vào:

- Metric names và labels.
- GC metrics/collector names.
- JVM memory pool names.
- APM resource attributes, span names.
- Log patterns cho startup/crash/agent warnings.
- Heap/direct/native memory metrics.
- Alert thresholds từ baseline trước migration.

Khi đổi collector, JDK distribution hoặc APM agent, một dashboard có thể trống không phải vì ứng dụng “không dùng memory”, mà vì tên/chế độ xuất metrics đã thay.

### 31.1. Checklist observability

- [ ] JVM/process metrics còn xuất hiện.
- [ ] GC, heap, non-heap và direct memory được theo dõi phù hợp.
- [ ] HTTP/JDBC/messaging spans đủ và không trùng.
- [ ] Error rate và exception logging còn đúng.
- [ ] Dashboards không bị lệch do metric name/label changes.
- [ ] Alerts thật sự được kiểm tra với synthetic conditions khi khả thi.
- [ ] Agent overhead nằm trong budget.
- [ ] Logs và traces còn tuân thủ privacy policy.

Một deployment “HTTP 200” không đủ bằng chứng operational readiness nếu đường cảnh báo đã mất.

## 32. Support FAQ cần thực dụng

Nhóm support nên có câu trả lời theo tình huống, không cần học hết nội bộ build.

**Hỏi: Sản phẩm hiện hỗ trợ Java nào?**  
Trả lời: Chỉ theo support matrix của đúng product release và component. Nêu minimum JVM, distributions/platforms được duyệt và ngày hiệu lực; tránh dùng một con số chung cho server, SDK, CLI nếu khác nhau.

**Hỏi: Tôi đã cài JDK 21 nhưng vẫn báo release version not supported?**  
Trả lời: Kiểm tra JVM của Maven/Gradle daemon/compiler toolchain bằng lệnh được tài liệu hóa. IDE Project SDK không chứng minh build tool đang dùng đúng JDK.

**Hỏi: Vì sao ứng dụng chạy trên Windows mà lỗi trên Linux ARM64?**  
Trả lời: Thu thập OS, architecture, image, JDK build và native library information. Nếu dùng JNI/JNA, phải có binary đúng platform/ABI.

**Hỏi: Vì sao test không chạy trên Java 21 nhưng app startup được?**  
Trả lời: Test agent/coverage/bytecode parser có thể chưa hỗ trợ class-file/JDK mới. Xem error subtype và version test tooling.

**Hỏi: Có thể thêm `--add-opens` để sửa mọi lỗi?**  
Trả lời: Không. Cờ này chỉ điều chỉnh một số quyền truy cập module; nó không giải quyết missing method, bytecode malformed hoặc native ABI mismatch.

**Hỏi: Có thể rollback bằng cách đổi Java version trong container?**  
Trả lời: Cần xem release-specific rollback policy, dữ liệu/protocol/schema compatibility và approved image. Không tự thay JVM version trong production ngoài quy trình.

## 33. Support triage workflow

~~~text
Customer / developer reports a Java-related issue
                     |
                     v
Identify product component + release + deployment type
                     |
                     v
Check support matrix for exact JDK/vendor/OS/arch
                     |
            +--------+--------+
            |                 |
      Supported           Not supported
            |                 |
            v                 v
Collect runtime          Explain limitation,
fingerprint and logs     supported alternatives
            |
            v
Classify first failure
            |
      +-----+------+------+
      |            |      |
   Build/API    JVM/tool  Native/OS
      |            |      |
      v            v      v
Engineering    Runtime   Platform/native
owner          tooling   owner
      \            |      /
       +-----------+-----+
                   |
                   v
      Reproduce, resolve, update FAQ/runbook
~~~

### 33.1. Không yêu cầu dữ liệu quá mức

Support phải yêu cầu thông tin đủ để phân loại nhưng tránh thu thập secrets, toàn bộ environment hoặc heap dump khi chưa cần. Sử dụng kênh bảo mật được tổ chức duyệt cho diagnostic artifacts nhạy cảm.

### 33.2. Phân biệt môi trường không được hỗ trợ với bug có thật

Nếu khách hàng ở một platform chưa được cam kết, support nên giải thích chính sách và giải pháp được hỗ trợ. Nhưng một lỗi nghiêm trọng với bằng chứng rõ vẫn có thể là thông tin hữu ích cho product roadmap. Không dùng nhãn unsupported để bỏ qua mọi báo cáo kỹ thuật.

## 34. Incident template giúp escalations có thể hành động

~~~markdown
## Impact
- Affected service/customer/feature:
- First observed:
- Severity and business impact:

## Runtime environment
- Product release and artifact hash:
- JDK distribution/full version/build:
- JVM implementation:
- OS/base image/CPU architecture:
- Java arguments and agents (redacted):

## Symptoms
- First exception or fatal error:
- Affected class/method/library:
- Logs and correlation IDs:
- Reproduction:

## Compatibility context
- Supported matrix row:
- Last known good version:
- Differences between old/new environments:

## Mitigation and recovery
- Current workaround and risks:
- Rollback preconditions checked:
- Owner/escalation:
- Next action:
~~~

Template này giảm việc hỏi đi hỏi lại khi chuyển ticket giữa support, JVM/runtime, build và SRE. Tránh ghi “Java 21 bug” trước khi xác định runtime thật và root cause.

## 35. Phân vai trách nhiệm bằng một RACI đơn giản

| Hoạt động | Responsible | Accountable/duyệt | Consulted |
| --- | --- | --- | --- |
| Xác định Java support policy | Product/runtime team | Product owner | Support, security |
| Cấu hình JDK/compiler targets | Build/DevEx | Engineering lead | Library owners |
| Kiểm thử compatibility matrix | QA/CI | Release manager | Platform, developers |
| Cập nhật local setup/IDE | DevEx | Engineering lead | Developer representatives |
| Cập nhật release notes/FAQ | Docs/support engineering | Product owner | Service/SDK owners |
| Viết deployment/rollback runbook | SRE/platform | Operations lead | DB/security owners |
| Đối chiếu JDK security patches | Platform/security | Security owner | Product teams |
| Xử lý incident sau rollout | On-call + owning team | Incident commander | Runtime/JDK vendor |

RACI chỉ là ví dụ; tổ chức có thể dùng vai trò khác. Mục tiêu là không để “mọi người cùng chịu trách nhiệm” trở thành không ai sửa các trang sai.

## 36. Thông báo thay đổi theo từng nhóm người dùng

Một kế hoạch truyền thông có thể gồm:

| Khi nào | Người nhận | Nội dung |
| --- | --- | --- |
| Trước migration | Developers/QA | Toolchains, branch policy, CI matrix |
| Trước release | Support/SRE/security | Minimum JDK, runbook, known issues |
| Release announcement | Customers/SDK consumers | Action required, compatibility, timeline |
| Trong rollout | On-call/release manager | Canary status, thresholds, rollback gate |
| Sau rollout | Engineering/support | Verified platforms, issues, follow-ups |
| Mỗi JDK patch update | Platform/service owners | New image/build, regression evidence |

Một thông báo chỉ nên hướng người đọc đến **một phiên bản tài liệu đúng**. Link tới wiki cũ có thể nguy hiểm hơn là không có link.

### 36.1. Câu chữ tốt và không tốt

Không tốt: “Tất cả team chuyển sang Java 21 ngay.”

Tốt hơn: “Từ release X, server runtime dùng Java 21 trong approved images; SDK client giữ `--release 17`; developer build dùng toolchain 21. Các team xác nhận môi trường theo `development/prerequisites` và release gates trong `compatibility/support-policy`.”

Không tốt: “Agent vẫn chạy.”

Tốt hơn: “Agent version A đã được xác nhận trên target JDK build và image B với HTTP/JDBC traces, startup smoke và performance suite; dynamic attach chỉ được hỗ trợ theo policy riêng.”

## 37. Known issues và workaround register

Khi migration có lỗi chưa xử lý hoàn toàn, nên có bảng:

| Issue | Môi trường | Ảnh hưởng | Workaround | Owner | Hạn đánh giá |
| --- | --- | --- | --- | --- | --- |
| Tool A parse Java 21 class file lỗi | Test JDK 21 | Coverage gate bị chặn | Nâng tool phiên bản hỗ trợ | Build | Trước release |
| Native library thiếu ARM64 | Linux ARM64 | Chức năng X không chạy | Tạm không công bố ARM64 support | Platform | Theo kế hoạch |
| Reflection library cần module opens | JDK 17/21 | Init lỗi | Workaround giới hạn package, bản upgrade đã lên lịch | Library owner | Có expiry |
| Dashboard thiếu metrics sau agent upgrade | JDK 21 image | Alerting gap | Cập nhật mapping/agent config | Observability | Trước production |

Tất cả hàng trên là tình huống giả định. Ở tài liệu thật, phải ghi issue ID, impacted versions, trạng thái, owner, ngày cập nhật và link fix.

### 37.1. Workaround cần chính sách gỡ bỏ

Một cờ `--add-opens`, disable checks hoặc manual copy native binary có thể từng cần trong migration. Không để chúng trở thành “best practice” vĩnh viễn. Workaround cần:

- Mô tả nguyên nhân.
- Phạm vi phiên bản/JDK.
- Rủi ro security/operational.
- Điều kiện áp dụng.
- Người duyệt.
- Phương án thay thế lâu dài.
- Mốc xem lại/gỡ bỏ.

## 38. Deprecation và end-of-support announcements

Ngừng hỗ trợ Java cũ thường là **breaking support change**. Khi đưa Java 11 ra khỏi ma trận, tài liệu cần nêu:

- Product release đầu tiên không còn hỗ trợ.
- Ngày thông báo và ngày có hiệu lực.
- Những version cũ còn được cập nhật bảo mật hay không.
- Nguyên nhân/điều kiện kỹ thuật chính (nếu có).
- Khuyến nghị JDK target và platform được duyệt.
- Các bước nâng ứng dụng/SDK/CI.
- Hướng xử lý với customers chưa nâng kịp.
- Kênh support/escalation.

### 38.1. Không hứa support ngoài hợp đồng JDK vendor

JDK distributions có lifecycle và commercial support terms khác nhau. Một Java release được gọi LTS không đồng nghĩa mọi vendor tiếp tục cung cấp patches vô thời hạn. Chính sách sản phẩm nên được đối chiếu với vendor support đang thực tế sử dụng và ngày review.

## 39. Phiên bản hóa tài liệu cùng artifact

Khách hàng đang dùng release 4.x có thể cần tài liệu Java 17, trong khi release 5.x yêu cầu Java 21. Nếu trang “latest” được cập nhật mà xóa hướng dẫn 4.x, support sẽ khó tái hiện sự cố phiên bản cũ vẫn còn được hỗ trợ.

Nên:

1. Có documentation version tương ứng product release hoặc compatibility branch.
2. Gắn phiên bản và **last validated date**.
3. Đặt link từ release notes tới đúng version.
4. Giữ những tài liệu legacy đang còn support.
5. Đánh dấu rõ EOL/archived documents.
6. Không để search results dẫn vào runbook cũ mà không có cảnh báo.

### 39.1. Tránh mutable commands trong tài liệu release-specific

Ví dụ “dùng Docker tag `latest`” không đảm bảo tái lập một incident sau vài tháng. Release runbook nên nêu image digest hoặc artifact identifier được duyệt. Trang hướng dẫn có thể mô tả cách xác định phiên bản mới, nhưng một incident record phải lưu giá trị thực.

## 40. Cập nhật docs theo release lifecycle

Một chu kỳ:

~~~text
Feature / migration proposal
           |
           v
Support-policy change drafted
           |
           v
Build + test implementation
           |
           v
Docs and runbook PR with evidence
           |
           v
Review by owners and support
           |
           v
Release gates + freeze approval
           |
           v
Publish versioned docs and release
           |
           v
Canary, operational feedback, corrections
           |
           v
Update docs at next JDK/OS/agent patch cycle
~~~

### 40.1. “Last verified” quan trọng hơn “last edited”

Một runbook có thể vừa được sửa lỗi chính tả nhưng chưa hề chạy với JDK mới. Nên ghi riêng:

~~~text
Document last updated: ...
Procedure last executed/validated: ...
Validated artifact/image/JDK: ...
Owner: ...
Next review trigger: ...
~~~

Nếu procedure chưa được diễn tập trong môi trường cho phép, ghi “not yet validated”, không tự gọi nó đã sẵn sàng production.

## 41. Kiểm chứng documentation như kiểm thử kỹ thuật

Những kiểm tra có thể tự động hóa:

- Markdown lint và link checking.
- Kiểm tra phiên bản JDK trong docs có nằm trong support policy.
- Build/test code snippets được đánh dấu executable.
- Kiểm tra placeholder không lọt vào release-specific instructions.
- Đảm bảo đường dẫn tài liệu tham chiếu còn tồn tại.
- Chặn PR đổi `--release`/toolchain/runtime image mà không cập nhật changelog/migration notes theo policy.
- Phát hiện thông tin JDK minimum mâu thuẫn giữa module metadata và docs.
- Sinh support matrix public từ nguồn đã duyệt khi khả thi.

### 41.1. Đừng kiểm thử ví dụ ở sai runtime

Ví dụ dùng `List.of` chỉ có từ Java 9; nếu developer guide hứa Java 8 source thì snippet đó sẽ lỗi trên floor 8. Một snippet dùng pattern switch Java 21 không nên được đưa vào tài liệu của module giữ `--release 17`.

Test snippets phải dùng **compiler release phù hợp từng mục**; nếu code chỉ minh họa chứ không chạy độc lập, ghi rõ các dependencies/imports/placeholder.

### 41.2. Documentation QA và runtime QA là hai việc khác nhau

Link check pass không chứng minh lệnh deploy đúng. Ngược lại, deployment smoke pass không chứng minh support FAQ cập nhật. Cả hai cần trong release readiness.

## 42. Mẫu PR cho thay đổi Java compatibility

~~~markdown
## Change summary
- JDK migration target and affected modules:
- Current and new minimum runtime:
- Build JDK / compiler --release:

## Platform/support impact
- Supported JDK distributions:
- OS and CPU architecture:
- Runtime/container image:
- Native libraries / agents:
- Unsupported or deprecated combinations:

## Validation
- CI matrix and run IDs:
- Integration/contract tests:
- Runtime fingerprint and artifact checksums:
- Known issues / workarounds:

## Documentation updates
- README / developer setup:
- IDE/toolchain instructions:
- Support matrix / release notes:
- Deployment / rollback runbook:
- Support FAQ:

## Release operations
- Canary and monitoring plan:
- Stop/go criteria:
- Rollback constraints:
- Owners and approvals:
~~~

Không để phần docs chỉ là checklist máy móc; reviewer phải đối chiếu những giá trị thực với CI/runbook và support policy.

## 43. Ví dụ đầy đủ: dịch vụ chuyển Java 17 sang Java 21

Giả sử service `orders-service` có các thành phần:

~~~text
orders-service
  server runtime: Java 17 -> Java 21
  shared-client SDK: Java 17 minimum remains
  build tooling: Gradle Wrapper with supported daemon JVM
  image: approved Linux glibc image
  native dependency: compression library
  agents: tracing + metrics
  environments: dev, CI, staging, production
~~~

### 43.1. Thay đổi support policy

Ghi rõ `orders-service` yêu cầu Java 21 từ release mới; `shared-client` vẫn target Java 17. Chỉ những OS/architecture đã có native compression binary và agent support mới là production-supported.

### 43.2. Thay đổi developer setup

- Yêu cầu JDK 21 compiler/toolchain cho service build.
- Ghi `./gradlew --version` và `java -version`.
- Chỉnh hướng dẫn IDE/Gradle JVM.
- Chạy local integration tests sử dụng DB/test containers.
- Dùng `--release 17` đối với client SDK.
- Ghi native dependency setup và kiến trúc hỗ trợ.

### 43.3. Thay đổi CI

- Thêm target JDK 21 test jobs.
- Giữ Java 17 tests cho SDK compatibility.
- Test Linux amd64 production image.
- Thêm ARM64 dưới nhãn candidate nếu chưa đủ native support.
- Kiểm tra tracing/metrics instrumentation.
- Lưu artifact SHA, image digest, JVM build và test reports.

### 43.4. Thay đổi runbook

- Dùng image digest đã duyệt.
- Kiểm tra agent version, native compression và truststore.
- Canary traffic, error rate, latency, GC và traces.
- Đặt stop/go gates.
- Ghi rollback preconditions khi service mới đã ghi dữ liệu.

### 43.5. Thay đổi release notes/support FAQ

Gửi thông báo rõ:

~~~text
Server release requires Java 21 in approved runtime images.
Client SDK remains compatible with Java 17 per published
support matrix. Custom deployments must validate agents,
JNI/native libraries and JVM flags before upgrade.
Use the version-specific migration and rollback guides.
~~~

### 43.6. Thế nào được coi là hoàn tất?

Không chỉ “build xanh”. Phải có artifact/version support rõ, developer mới dựng project được theo tài liệu, on-call diễn tập được runbook, support phân loại lỗi theo FAQ, CI matrix có evidence và production canary đạt gate.

## 44. Ví dụ đối chứng: thư viện SDK không tự điều khiển JVM của khách hàng

Với SDK, rủi ro nằm ở runtime của consumer hơn là runtime service do team kiểm soát:

- Thư viện có thể compile bằng JDK 21 nhưng giữ `--release 17`.
- Consumer có thể chạy trên Temurin, Corretto, Zulu hoặc distribution khác theo policy.
- Consumers khác nhau dùng Windows/Linux/macOS.
- Một dependency transitive mới có thể được compile bằng class-file Java 21 và phá compatibility Java 17.
- `multi-release JAR` có thể dùng implementation theo runtime nhưng public API phải nhất quán.
- Annotation processors/code generators có thể cần JDK khác runtime của SDK.

Vì thế SDK migration guide cần:

1. Minimum Java runtime theo artifact version.
2. Dependency compatibility và public API change policy.
3. Build tool setup cho Maven/Gradle consumers.
4. Compatibility test results ở runtime tối thiểu.
5. Cách phát hiện `UnsupportedClassVersionError`, `NoSuchMethodError`.
6. Hướng dẫn cho consumers dùng JPMS/module path nếu hỗ trợ.
7. Chính sách library versions, end-of-support và migration path.

Không viết “JDK của server là 21 nên khách hàng SDK cũng phải dùng 21” khi SDK artifact được giữ tương thích Java 17.

## 45. Các lỗi thường gặp khi cập nhật tài liệu

**“Chỉ sửa README là đủ.”** Không đủ nếu support matrix, CI, Dockerfile và rollback runbook vẫn chứa version cũ.

**“JDK để build và runtime là một.”** Không nhất thiết. Compiler toolchain và bytecode target có thể khác production JVM.

**“Version Java trong IDE là nguồn chân lý.”** Không đủ; cần kiểm tra Maven/Gradle daemon/compiler và test launcher.

**“Đã test một distribution là hỗ trợ mọi vendor.”** Không thể suy ra khi còn OS, JVM implementation, agent, native và security khác biệt.

**“Hỗ trợ Linux nghĩa là hỗ trợ mọi Linux image.”** Sai nếu libc, architecture, certificates hoặc native dependencies khác.

**“CI dùng JDK 21 nên production cũng dùng đúng build đó.”** Không chắc khi image tag/runner versions có thể thay.

**“Thêm một flag `--add-opens` cho mọi môi trường sẽ tránh sự cố.”** Có thể mở rộng quyền không cần thiết và không sửa lỗi API/bytecode khác.

**“Có thể rollback bằng cách đổi image mà không kiểm tra dữ liệu.”** Sai khi schema/protocol/persistent state đã thay.

**“Agent được nạp nghĩa là observability vẫn tốt.”** Không chắc; phải test traces, metric labels, alerts và overhead.

**“JDK LTS luôn được hỗ trợ và vá vô thời hạn.”** Phụ thuộc vendor/support policy.

**“Bảng support ghi PASS nhưng không có logs vẫn chấp nhận.”** Thiếu bằng chứng runtime và artifact cụ thể.

**“Runbook càng nhiều câu lệnh càng tốt.”** Không đúng nếu lệnh sai OS, thiếu quyền, tiết lộ secrets hoặc có thể gây downtime.

**“Một workaround debug nên để vĩnh viễn vì giúp an toàn.”** Không đúng; workaround có thể tạo rủi ro security/compatibility.

**“Tài liệu cập nhật sau khi phát hành cũng được.”** Với thay đổi runtime minimum/rollback, điều này có thể làm khách hàng và on-call gặp lỗi không cần thiết.

**“Docs đã edit nghĩa là procedure đã được thử.”** Hai trạng thái khác nhau; cần last-validated evidence.

## 46. Checklist phát hành: tài liệu và vận hành

- [ ] Có một support policy authoritative, gắn product release.
- [ ] Java minimum/runtime target được nêu riêng từng component/module.
- [ ] JDK distribution/OS/CPU/platform support được xác nhận, không suy đoán.
- [ ] JDK patch/build và container digest được ghi trong release evidence.
- [ ] Developer prerequisites đúng với toolchain đang dùng.
- [ ] README có lệnh kiểm tra `java`/`javac`/wrapper và links đúng.
- [ ] Maven/Gradle instructions phân biệt daemon/compiler/`--release`/tests.
- [ ] IDE guide đã cập nhật cho những phiên bản được tổ chức hỗ trợ.
- [ ] Local integration prerequisites, test containers và secrets được mô tả.
- [ ] JNI/JNA/native/agent dependencies có hướng dẫn phù hợp OS/architecture.
- [ ] CI matrix và mandatory release gates được công bố.
- [ ] Test reports ghi PASS/FAIL/NOT_RUN/SKIPPED đúng.
- [ ] Release notes nêu action required, breaking support changes và known issues.
- [ ] Migration guide có before/during/after steps và success criteria.
- [ ] Runbook có preflight, artifact/JDK/image verification.
- [ ] Canary/rollout có stop/go thresholds và owner.
- [ ] Monitoring, dashboards, metrics, traces và alerts được xác nhận.
- [ ] Rollback preconditions bao gồm schema/protocol/data compatibility.
- [ ] Có hướng dẫn incident triage cho classpath, bytecode, JNI, TLS và agents.
- [ ] Có quy trình thu logs/dumps an toàn và redact secrets.
- [ ] Support FAQ và escalation ownership đã cập nhật.
- [ ] Workarounds có owner, risk và expiry.
- [ ] Deprecation/EOL có ngày hiệu lực và đường migration.
- [ ] Versioned docs còn sẵn cho releases đang hỗ trợ.
- [ ] Link checks/snippet tests hoặc review thủ công đã hoàn tất theo policy.
- [ ] Runbook có lần thực thi/kiểm chứng gần nhất và bằng chứng.
- [ ] Có triggers cập nhật khi JDK patch/OS image/vendor/agent đổi.

Checklist không phải chứng chỉ hoàn tất; từng ô quan trọng phải có tài liệu, CI evidence hoặc người phê duyệt tương ứng.

## 47. Nguồn kỹ thuật nên đối chiếu trước khi công bố

Tài liệu hỗ trợ cần dựa vào **đúng JDK release, distribution và tool version**:

- **JDK Release Notes và Java SE Platform docs:** API, module, security và runtime changes.
- **Java Virtual Machine Specification:** class-file version, loading/linkage/initialization.
- **`javac` Tool Guide:** `--release`, source/target và API restrictions.
- **Gradle Java Compatibility Matrix và Toolchains docs:** build daemon khác compiler/test toolchain.
- **Maven Compiler Plugin, Toolchains, Surefire/Failsafe docs:** compiler JDK, release target và test forks.
- **IDE/vendor Java support docs:** Project SDK, module language level, language server và plugins.
- **JDK distribution vendor support pages:** release lifecycle, OS/CPU architecture và full builds.
- **Container platform docs:** image digest, multi-platform manifests, cgroups/namespace.
- **Java Instrumentation/JVMTI docs:** startup/dynamic agents, native profilers.
- **JDK troubleshooting guides:** `jcmd`, JFR, fatal error logs, NMT và JNI checks.
- **Security/TLS provider documentation:** truststores, certificates, algorithm constraints.
- **Framework/JDBC/APM/native library compatibility matrices:** supported integration combinations.

Tài liệu vendor và support matrix thay đổi theo thời gian. Không chốt “bản mới nhất” hay “vendor X luôn hỗ trợ platform Y” trong một hướng dẫn không có ngày review; ghi chính xác phiên bản/nguồn tại lúc release và quy trình kiểm tra lại.

## 48. Kết luận

Cập nhật tài liệu hỗ trợ, môi trường phát triển và hướng dẫn vận hành là **công việc kỹ thuật bắt buộc** của Java Advance Compatibility Migration, không phải bước viết lại README cho đẹp sau khi code đã hoàn tất. Java compatibility không chỉ là `javac` biên dịch được: nó bao gồm JVM thực thi, class-file target, distribution, OS/architecture, native libraries, agents, security, dữ liệu và hành vi vận hành.

Một đợt migration có trách nhiệm phải **công bố chính xác phạm vi hỗ trợ**, giúp developer tái lập môi trường, để QA/CI chứng minh các tổ hợp production, cho SRE khả năng triển khai và khôi phục theo runbook, đồng thời giúp support giải thích các yêu cầu và phân tuyến lỗi đúng. Những tài liệu này phải đồng bộ với artifact, JVM build, image digest và kiểm thử thực tế.

Hãy quản lý support policy, README, toolchains, release notes, migration guide, runbooks và FAQ như một phần của vòng đời phát hành: có owner, version, review, kiểm chứng và lịch cập nhật khi JDK security patch hoặc runtime image đổi. Khi đó, nâng JDK không dừng ở trạng thái **“ứng dụng chạy được”**, mà đạt trạng thái quan trọng hơn: **người phát triển, vận hành và sử dụng đều biết rõ điều kiện hỗ trợ, cách xác minh và cách xử lý khi có sự cố**.
