# Ghi lại quyết định trong thiết kế Java toolchain

Khi thiết kế Java toolchain, nhóm phát triển phải chọn và phối hợp nhiều thành phần: JDK vendor và version, JVM chạy build tool, compiler, Java API/bytecode target, test runtime, Maven hoặc Gradle, wrapper, plugin, dependency, công cụ đóng gói, runtime image và môi trường CI. Mỗi lựa chọn có thể ảnh hưởng tới khả năng build lại, tương thích, hiệu năng, bảo mật, chi phí vận hành và cách nâng cấp sau này.

**Ghi lại quyết định** giúp người đọc hiểu nhóm đã chọn điều gì, vì sao chọn, những phương án nào đã được cân nhắc và đánh đổi nào được chấp nhận. Với các lựa chọn có ảnh hưởng lâu dài, cách phổ biến là dùng **Architecture Decision Record (ADR)**. ADR là tài liệu ngắn ghi một quyết định quan trọng cùng bối cảnh và hệ quả của nó.

Một quyết định chỉ có giá trị khi người khác có thể hiểu và kiểm tra nó. Câu “chúng ta dùng Java 17 vì ổn định” chưa đủ. Một ghi chép hữu ích cần nêu yêu cầu tương thích, JDK thực tế được dùng, lý do chọn, cách xác nhận build và điều kiện khiến nhóm phải xem xét lại.

## 1. Vì sao cần ghi lại quyết định toolchain?

Không ghi lại quyết định thường dẫn tới:

- Thành viên mới không biết vì sao project yêu cầu một JDK cụ thể.
- Máy developer và CI dùng JDK khác nhau, tạo kết quả build khác nhau.
- Nhóm thay Maven/Gradle hoặc plugin mà không nhận ra ảnh hưởng tới artifact.
- Một quyết định cũ bị tranh luận lại vì không ai tìm thấy lý do ban đầu.
- Security update bị trì hoãn vì không rõ ai chịu trách nhiệm theo dõi JDK và plugin.
- Runtime image hoặc installer không tái tạo được vì thiếu module list và lệnh build.
- Nâng version gây lỗi tương thích nhưng không có baseline để so sánh.

Một ADR tốt giúp trả lời nhanh: vấn đề nào cần quyết định, ràng buộc và tiêu chí nào quan trọng, phương án nào đã được cân nhắc, nhóm chọn gì và vì sao, hệ quả là gì, bằng chứng nào xác nhận quyết định được thực hiện đúng, và điều kiện nào khiến quyết định cần được xem xét lại.

ADR lưu lý do và phạm vi của quyết định. Cấu hình build, pipeline và code mới là nơi thực thi quyết định. Hai loại tài liệu cần liên kết với nhau.

## 2. Khi nào nên tạo decision record?

Không cần tạo ADR cho mọi thay đổi nhỏ. Hãy ghi lại khi lựa chọn khó đảo ngược hoặc tốn kém nếu thay đổi; ảnh hưởng nhiều module, team, service hoặc môi trường; tác động tới bảo mật, độ tin cậy, hiệu năng, khả năng tương thích hoặc chi phí; chọn giữa các công cụ hoặc nền tảng có hệ quả vận hành khác nhau; đặt ra chuẩn chung cho cách build, test, package hoặc phát hành; hoặc có khả năng người khác sẽ hỏi “vì sao project làm theo cách này?” trong tương lai.

Ví dụ quyết định đáng ghi lại trong Java toolchain:

| Quyết định | Vì sao có ý nghĩa |
|---|---|
| Chọn JDK vendor và version | Ảnh hưởng runtime, support, security patch và native behavior |
| Chọn Maven hay Gradle | Ảnh hưởng build model, plugin ecosystem và cách maintain |
| Bắt buộc dùng Wrapper | Chuẩn hóa build tool version trên developer và CI |
| Chọn Java release target | Xác định API và bytecode tối thiểu mà ứng dụng hỗ trợ |
| Chọn test runtime matrix | Xác định các JDK được kiểm thử |
| Chọn plugin đóng gói hoặc shading | Ảnh hưởng nội dung artifact và runtime behavior |
| Chọn jlink/jpackage | Ảnh hưởng runtime image, installer và OS support |
| Chọn repository và signing flow | Ảnh hưởng phân phối, xác thực và truy vết artifact |

Không cần ADR cho việc đổi tên biến hoặc cập nhật một test nhỏ nếu nó không làm thay đổi quy ước kỹ thuật.

## 3. Phân biệt quyết định, cấu hình và tài liệu vận hành

| Loại tài liệu | Câu hỏi chính | Ví dụ |
|---|---|---|
| Decision record / ADR | Vì sao chọn phương án này? | Vì sao project dùng Gradle Wrapper và Java 17 toolchain |
| Build configuration | Build thực tế được cấu hình thế nào? | build.gradle.kts, pom.xml, wrapper properties |
| Runbook | Khi vận hành hoặc xử lý lỗi phải làm gì? | Cách kiểm tra JDK trên CI, cách cập nhật wrapper |

ADR không phải bản sao của pom.xml hay build.gradle. Không nên biến ADR thành hướng dẫn cài đặt từng bước hoặc danh sách toàn bộ dependency. Hãy ghi quyết định, lý do và hệ quả; liên kết tới cấu hình, pipeline hoặc runbook làm bằng chứng triển khai.

Meeting notes ghi lại nội dung thảo luận. ADR ghi lại kết luận đã được quyết định. Một cuộc họp dài không thay thế một quyết định rõ ràng.

## 4. Các thành phần của Java toolchain cần ghi riêng

Từ “Java version” thường quá mơ hồ. Một project có thể dùng nhiều Java version cho các mục đích khác nhau. Khi ghi quyết định, hãy tách các lớp sau:

| Thành phần | Câu hỏi cần ghi |
|---|---|
| Build JVM | JDK nào chạy Maven hoặc Gradle daemon? |
| Compiler toolchain | JDK nào cung cấp javac để compile? |
| Release target | API và bytecode mục tiêu là Java mấy? |
| Test launcher | Unit/integration test chạy trên JDK nào? |
| Production runtime | Ứng dụng được hỗ trợ trên JDK/runtime nào? |
| jlink toolchain | JDK nào tạo custom runtime image? |
| jpackage toolchain | JDK nào tạo application image/installer? |
| OS/architecture | Artifact được build cho Windows/Linux/macOS và x64/ARM64 nào? |
| Build tool | Maven/Gradle version nào được pin bằng Wrapper? |
| Plugin | Plugin nào ảnh hưởng compile, test, package và publish? |

Đặc biệt, ba khái niệm này không thay thế nhau:

- JDK toolchain xác định bộ công cụ Java mà task sử dụng.
- Compiler option release xác định API và bytecode tương thích.
- JAVA_HOME thường chọn Java mặc định cho process hoặc công cụ, nhưng không nhất thiết ghi đè cấu hình toolchain riêng của project.

Ví dụ, Gradle có thể chạy bằng một JVM được hỗ trợ, dùng JDK 17 để compile, nhưng cấu hình release 11 để đảm bảo code chỉ sử dụng API Java 11. Đây là ba quyết định liên quan nhưng khác nhau.

## 5. Quy trình ghi lại một quyết định

### Bước 1: Xác định câu hỏi cần quyết định

Viết câu hỏi đủ hẹp để biết quyết định sẽ tác động tới đâu.

Tốt: “Project Java service này sẽ pin Gradle version và chọn JDK compiler toolchain như thế nào để developer và CI tạo cùng loại artifact?”

Quá rộng: “Chúng ta nên hiện đại hóa toàn bộ Java platform như thế nào?”

Một ADR nên chứa một quyết định độc lập. Nếu một lựa chọn có thể được thay đổi riêng mà không cần thay đổi phần còn lại, cân nhắc tách thành ADR khác.

### Bước 2: Ghi bối cảnh bằng sự kiện

Context mô tả trạng thái và vấn đề trước khi chọn giải pháp. Ghi dữ liệu có thể kiểm chứng: JDK và build tool hiện tại; số môi trường build và OS được hỗ trợ; Java version tối thiểu mà người dùng cần; plugin hoặc dependency có giới hạn tương thích; thời gian build, lỗi build hoặc khác biệt giữa local và CI; security policy, support window và lịch nâng cấp; hạn chế về network, quyền cài JDK, artifact repository hoặc native tool.

Tách sự kiện khỏi ý kiến. “CI đang dùng JDK 21.0.x còn máy developer dùng JDK 17” là sự kiện. “CI cấu hình không tốt” là nhận xét chưa chỉ ra nguyên nhân.

### Bước 3: Xác định decision drivers và hard constraints

Decision drivers là các tiêu chí khiến một lựa chọn có giá trị. Ví dụ: phải hỗ trợ Java API tối thiểu 17; build phải tái lập giữa developer và CI; JDK cần có security update và vendor support phù hợp; plugin đóng gói phải tương thích với build tool; artifact cần chạy trên Linux x64 và Linux ARM64; pipeline không được tải dependency từ repository không được phê duyệt.

Phân biệt hard constraint với tiêu chí có thể đánh đổi. Nếu một lựa chọn không đáp ứng yêu cầu bắt buộc, loại nó trước khi chấm điểm. Không để điểm hiệu năng cao bù cho việc vi phạm yêu cầu bảo mật.

### Bước 4: Liệt kê phương án thực sự được cân nhắc

Nên có phương án đang dùng, phương án được đề xuất và một lựa chọn thay thế hợp lý. Đưa cả “giữ nguyên hiện trạng” vào danh sách nếu đó là lựa chọn thực tế.

Ví dụ: dùng system Maven/Gradle và JAVA_HOME của từng máy; dùng Maven Wrapper hoặc Gradle Wrapper để pin build tool; dùng Wrapper kết hợp Java toolchain ở cấp project; dùng container build image đã pin digest và cung cấp JDK chuẩn; hoặc dùng JDK được quản lý tập trung trên CI runner.

Không liệt kê phương án giả tạo chỉ để làm quyết định trông có vẻ đã so sánh nhiều.

### Bước 5: So sánh bằng tiêu chí và bằng chứng

Có thể dùng bảng ưu/nhược hoặc ma trận trọng số. Trước tiên loại các phương án không đạt hard constraint. Sau đó so sánh những lựa chọn còn lại theo tiêu chí có thể quan sát.

Ví dụ ma trận dưới đây chỉ minh họa cách ghi; trọng số và điểm phải được nhóm xác định từ yêu cầu thực tế.

| Tiêu chí | Trọng số ví dụ | Câu hỏi đánh giá |
|---|---:|---|
| Reproducibility | 30% | Hai môi trường có tạo build theo cùng toolchain không? |
| Compatibility | 25% | Có đáp ứng Java release, plugin và runtime target không? |
| Security/support | 20% | Có quy trình cập nhật JDK, plugin và checksum không? |
| Operations | 15% | Dễ cài, debug, nâng cấp và hỗ trợ đến đâu? |
| Build performance | 10% | Thời gian build và cache có đáp ứng mục tiêu không? |

Nếu dùng điểm 1–5, hãy ghi định nghĩa điểm và bằng chứng. Điểm số không phải chân lý; nó giúp hiển thị trade-off. Không dùng một con số tổng hợp để che mất hard constraint hoặc rủi ro nghiêm trọng.

### Bước 6: Chạy thử trước khi chấp nhận

Với lựa chọn có ảnh hưởng lớn, tạo spike hoặc proof of concept:

1. Build một module đại diện.
2. Chạy unit test và integration test.
3. Tạo artifact đúng định dạng dự kiến.
4. Chạy artifact trên runtime mục tiêu.
5. Kiểm tra build trên local và CI.
6. Đo build time, cache hit, image size hoặc startup nếu đó là driver.
7. Kiểm tra checksum, download source và khả năng tái lập.
8. Ghi lại lỗi và giới hạn phát hiện được.

Liên kết log, pull request, benchmark hoặc test report vào ADR. Không chép hàng nghìn dòng log vào decision record.

### Bước 7: Chốt quyết định và nêu rõ đánh đổi

Decision phải là một câu khẳng định cụ thể, ví dụ: “Project dùng Gradle Wrapper đã pin version; Java compile tasks dùng Java 17 toolchain và release target 17.”

Rationale trả lời tại sao phương án này phù hợp với context và drivers. Consequences ghi cả mặt tốt lẫn chi phí: cần duy trì wrapper, cập nhật JDK patch, cấu hình toolchain cho developer và kiểm tra CI khi nâng version.

### Bước 8: Review, chấp nhận và theo dõi thực thi

Ghi người có quyền quyết định, người chịu trách nhiệm triển khai và ngày chấp nhận. Khi quyết định được duyệt, cập nhật cấu hình build/pipeline và kiểm tra rằng implementation phù hợp với ADR.

Không đánh dấu Accepted chỉ vì file đã được tạo. Proposed có nghĩa là còn chờ review; Accepted nghĩa là quyết định đã được thông qua.

## 6. Cách đánh giá phương án toolchain

Một bảng so sánh cần đánh giá chính nhu cầu của project. Ví dụ khi chọn cách quản lý build tool:

| Phương án | Ưu điểm | Chi phí/rủi ro |
|---|---|---|
| System-installed build tool | Cài một lần trên máy | Version có thể lệch giữa máy và CI |
| Wrapper trong repository | Version build tool được khai báo cùng project | Cần review wrapper files và distribution download |
| Wrapper + toolchain | Pin build tool và JDK task sử dụng | Cần cấu hình và quản lý JDK provisioning |
| Container build image | Môi trường OS/JDK/tool có thể pin bằng digest | Image cần rebuild và scan; local workflow có thêm container layer |

Khi chọn JDK vendor, hãy so sánh support policy, release cadence, platform coverage, license, update process, performance và cách xác minh binary. Không chọn vendor chỉ vì tên quen thuộc.

Khi chọn Java release target, hãy xem deployment runtime thực tế, API mà code cần, dependency bytecode, framework support và thời gian hỗ trợ sản phẩm. Release target thấp hơn không tự động làm ứng dụng chạy được trên mọi JDK cũ nếu dependency yêu cầu runtime mới hơn.

Khi chọn jlink/jpackage, ghi rõ JDK tạo runtime image, module root, locale, service binding, OS/architecture, native dependency và installer format. Đừng chỉ ghi “dùng JDK 25” nếu build, test và runtime dùng các version khác nhau.

## 7. Bằng chứng cần thu thập trước khi ghi quyết định

### Xác minh Java và build tool

Linux/macOS:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
~~~

Maven Wrapper:

~~~bash
./mvnw -version
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
~~~

Ghi cả JDK chạy build tool và JDK mà task compiler/test thực sự chọn. Chỉ ghi output java -version từ terminal là chưa đủ để mô tả toàn bộ toolchain.

### Kiểm tra build configuration

Với Gradle:

~~~bash
./gradlew tasks
./gradlew dependencies
./gradlew clean check
~~~

Với Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

Effective POM và dependency tree giúp xác định plugin, dependency và cấu hình được áp dụng sau khi kế thừa. Không đưa output có credential hoặc repository secret vào ADR.

### Ghi nhận artifact

Sau khi build, lưu artifact name, version và classifier; SHA-256 digest; compiler release và class file version; JDK vendor/version của build và runtime; OS/architecture và build image digest; dependency/SBOM reference; test report và kết quả smoke test.

Các bằng chứng phải trỏ tới đúng commit và artifact đã kiểm thử. Một link tới “latest build” không đủ để truy vết quyết định lịch sử.

## 8. Lưu decision record ở đâu?

Với quyết định của một project, cách đơn giản là lưu Markdown trong repository:

~~~text
project/
  docs/
    adr/
      README.md
      0001-standardize-java-toolchain.md
      0002-select-runtime-image-modules.md
      0003-publish-artifacts-to-repository.md
~~~

README trong docs/adr nên là index ngắn: số ADR, tiêu đề, trạng thái và liên kết. Đặt tên file theo số thứ tự và nội dung quyết định để dễ tìm kiếm.

Ưu điểm của việc lưu trong source repository là quyết định đi cùng code và build configuration; có lịch sử Git và review qua pull request; có thể liên kết ADR với issue, commit, release và pipeline; người sửa build có thể đọc quyết định trước khi thay đổi.

Quyết định cấp tổ chức có thể cần một architecture register hoặc hệ thống tài liệu có quyền truy cập phù hợp. Dù lưu ở đâu, cần có một nơi chuẩn, quyền sở hữu rõ và liên kết từ repository liên quan.

Không lưu token, mật khẩu, private key, dữ liệu cá nhân hoặc output hệ thống có secret trong ADR. Ghi tên secret manager hoặc policy tham chiếu thay vì giá trị bí mật.

## 9. Mẫu ADR dành cho Java toolchain

Mẫu dưới đây đủ ngắn để dùng thường xuyên nhưng vẫn lưu được bối cảnh và hệ quả. Mỗi ADR chỉ nên có một quyết định chính.

~~~markdown
# ADR-NNNN: [Tên quyết định ở dạng khẳng định]

- Status: Proposed
- Date: YYYY-MM-DD
- Deciders: [Vai trò/người có quyền quyết định]
- Owner: [Người theo dõi triển khai]
- Scope: [Project/module/CI/release]
- Related: [Issue, PR hoặc ADR liên quan]

## Context and problem

[Mô tả trạng thái hiện tại, vấn đề và ràng buộc có thể kiểm chứng.]

## Decision drivers

- [Yêu cầu bắt buộc]
- [Tiêu chí tương thích]
- [Bảo mật, vận hành hoặc hiệu năng]

## Options considered

### Option A

- Pros:
- Cons:

### Option B

- Pros:
- Cons:

### Option C

- Pros:
- Cons:

## Decision

[Viết rõ phương án được chọn và phạm vi áp dụng.]

## Rationale

[Giải thích vì sao phương án phù hợp hơn các lựa chọn khác.]

## Consequences

### Positive

- [Lợi ích cụ thể]

### Negative and accepted trade-offs

- [Chi phí/rủi ro được chấp nhận]

## Implementation and validation

- [Cấu hình hoặc repository path]
- [Lệnh kiểm tra]
- [Test/metric cần đạt]
- [Artifact hoặc evidence link]

## Rollback and review triggers

- [Cách quay lại hoặc thay thế]
- [Điều kiện phải xem xét lại quyết định]

## References

- [Tài liệu chính thức]
~~~

Nếu nhóm muốn dùng template nhẹ hơn, có thể giữ bốn phần tối thiểu: Title, Status, Context, Decision và Consequences. Thêm bảng lựa chọn, người quyết định, bằng chứng và review trigger khi độ phức tạp yêu cầu.

## 10. Ví dụ ADR hoàn chỉnh: chuẩn hóa Gradle Wrapper và Java toolchain

Ví dụ sau là một tình huống giả định để minh họa cách viết. Nó không phải tuyên bố rằng mọi project nên dùng Gradle hoặc Java 17.

~~~markdown
# ADR-0007: Pin Gradle Wrapper và Java 17 compile toolchain

- Status: Accepted
- Date: 2026-11-10
- Deciders: Java service maintainers
- Owner: Build engineering
- Scope: Main Java service and CI build

## Context and problem

Developer machines and CI runners have used different Gradle and JDK
installations. The same commit can therefore be built with different
compiler APIs or build plugin behavior. The service contract requires
the application to use Java 17 APIs and produce Java 17-compatible
class files.

The project already uses Gradle Kotlin DSL. Replacing the build system
would create migration work without addressing the immediate source
of toolchain drift.

## Decision drivers

- A project must declare its Gradle version.
- Compile tasks must use a Java 17 toolchain.
- Compile output must target the Java 17 API and bytecode level.
- Local and CI builds must run the same verification tasks.
- JDK patch updates must follow the approved security update process.

## Options considered

### System-installed Gradle and JAVA_HOME

Pros:
- Minimal repository configuration.

Cons:
- Build tool and JDK versions can differ by workstation or runner.
- A developer may build with a version that CI does not use.

### Gradle Wrapper without a Java toolchain

Pros:
- Gradle version is standardized.
- Small configuration change.

Cons:
- Compiler selection can still depend on the machine environment.

### Gradle Wrapper plus Java toolchain and release target

Pros:
- Build tool version is declared by the repository.
- Compile tasks select the required Java language version.
- The release setting prevents accidental use of APIs newer than Java 17.

Cons:
- The team must provision and update a matching JDK.
- The Gradle daemon JVM and compile toolchain must be documented separately.

## Decision

Use the Gradle Wrapper for every project build. Configure Java compile
tasks to use a Java 17 toolchain and release target 17. CI must use the
approved JDK distribution and immutable build image. Test and release
jobs must run the same verification task set.

## Rationale

The project already uses Gradle. Wrapper plus toolchain addresses both
build-tool drift and compiler selection while preserving the existing
build model. The release setting enforces the Java 17 API and bytecode
contract.

## Consequences

### Positive

- Developer and CI builds use the declared Gradle distribution.
- Compile tasks request Java 17.
- The compiler rejects accidental use of APIs newer than Java 17.
- Toolchain updates can be reviewed as explicit repository changes.

### Negative and accepted trade-offs

- JDK provisioning becomes part of developer and CI setup.
- A toolchain language version alone does not pin a vendor or patch.
- The Gradle daemon JVM still needs its own supported version policy.
- JDK patch updates require a build and regression review.

## Implementation and validation

- Commit Gradle Wrapper files and the distribution checksum.
- Configure Java toolchain language version 17.
- Configure JavaCompile release 17.
- Run ./gradlew --version and ./gradlew -q javaToolchains.
- Run ./gradlew clean check on local and CI.
- Verify the artifact class file version and run smoke tests on Java 17.
- Record the CI image digest and JDK vendor/version with each release.

## Rollback and review triggers

Create a new ADR if the service changes its minimum Java runtime,
the build tool becomes unsupported, a required plugin cannot run on
the selected toolchain, or a security/support change requires another
JDK distribution. Preserve this accepted ADR and link the replacement.

## References

- Gradle Wrapper documentation
- Gradle JVM toolchains documentation
- Java compiler --release documentation
~~~

### Cấu hình Gradle minh họa tương ứng

Tệp build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Cấu hình trên yêu cầu Java 17 toolchain cho các task Java và giới hạn API/bytecode ở release 17. Nó không pin patch version hoặc vendor của JDK. Nếu tổ chức yêu cầu một vendor cụ thể, hãy cấu hình vendor/toolchain resolver phù hợp và ghi policy đó trong ADR. Nếu yêu cầu pin patch tuyệt đối, quản lý JDK distribution trong CI image hoặc provisioning system đã được kiểm soát.

Tệp gradle/wrapper/gradle-wrapper.properties phải khai báo distribution URL của Gradle version được duyệt. Nên xác minh checksum của distribution theo quy trình Wrapper được hỗ trợ.

### Các lệnh xác minh

Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean check
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat clean check
~~~

Kiểm tra class file version:

~~~bash
javap -verbose -classpath build/classes/java/main com.acme.Main
~~~

Với Java 17, class file major version là 61. Đây là kiểm tra bytecode; vẫn cần test và chạy artifact trên runtime Java 17 để xác nhận dependency và hành vi thực tế.

## 11. Ghi quyết định Maven toolchain

Maven Wrapper và Maven Toolchains giải quyết hai việc khác nhau:

- Maven Wrapper xác định Maven distribution được project sử dụng.
- Maven Toolchains cho phép plugin tương thích sử dụng một JDK được chọn độc lập với JVM đang chạy Maven.

Ví dụ Maven Wrapper có thể được gọi như sau:

~~~bash
./mvnw -version
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
~~~

Đầu ra giúp nhận diện Maven version và Java runtime chạy Maven. Nó không tự chứng minh compiler plugin đã dùng JDK nào.

Maven toolchain có thể được khai báo trong file toolchains.xml của user hoặc build agent. Ví dụ cấu hình JDK:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Đường dẫn trên là ví dụ Linux; máy Windows cần đường dẫn JDK tương ứng. Không commit đường dẫn local của một developer vào project. CI cần provisioning path hoặc image có thể tái tạo.

Trong pom.xml, cấu hình Compiler Plugin dùng release target:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Để chọn toolchain, project phải cấu hình Maven Toolchains Plugin và các plugin thực thi phải hỗ trợ toolchain. Kiểm tra version tài liệu của plugin đang dùng; không giả định mọi plugin đều tự động dùng JDK được chọn.

Một ADR Maven nên ghi rõ Maven Wrapper version, JDK chạy Maven, JDK compiler toolchain, release target, toolchains.xml provisioning, plugin version và cách CI xác minh lựa chọn.

## 12. Quản lý trạng thái ADR và lịch sử quyết định

Một decision record thường có các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Proposed | Đang được xem xét, chưa được chấp nhận |
| Accepted | Đã được thông qua và đang có hiệu lực |
| Rejected | Đã xem xét nhưng không chọn |
| Deprecated | Không còn được khuyến nghị hoặc không còn phù hợp |
| Superseded | Đã được thay thế bởi ADR khác |

Khi quyết định được chấp nhận, giữ lại nội dung và rationale như lịch sử. Nếu bối cảnh thay đổi, tạo ADR mới giải thích quyết định mới và liên kết ADR cũ. Đánh dấu ADR cũ là Superseded và ghi số ADR thay thế.

Không sửa lịch sử để làm như nhóm đã luôn chọn phương án mới. Sửa lỗi chính tả hoặc làm rõ câu chữ có thể chấp nhận; thay đổi quyết định, rationale hoặc phạm vi phải có lịch sử review phù hợp.

Ví dụ liên kết:

~~~text
ADR-0007: Pin Gradle Wrapper and Java 17 toolchain
Status: Superseded by ADR-0014

ADR-0014: Move the service build to Java 25 toolchain
Status: Accepted
Supersedes: ADR-0007
Reason: The service runtime baseline and supported dependencies changed.
~~~

Giữ các ADR cũ giúp người đọc hiểu thời điểm nào quyết định nào có hiệu lực và tại sao nhóm thay đổi hướng đi.

## 13. Theo dõi thực thi quyết định

ADR được Accepted nhưng không được triển khai thì chưa giải quyết vấn đề. Mỗi quyết định nên có các công việc và bằng chứng tương ứng:

| Quyết định | Việc triển khai | Bằng chứng |
|---|---|---|
| Pin Maven/Gradle | Commit Wrapper files và checksum | Wrapper version trong CI log |
| Chọn JDK compiler | Cấu hình toolchains/toolchain resolver | Toolchain listing và compiler log |
| Chọn release target | Cấu hình --release | javap class version và compatibility tests |
| Chọn test matrix | Cấu hình CI matrix | Test report theo JDK/OS |
| Chọn runtime image | Cấu hình jlink/jpackage | Module list, image digest và smoke test |
| Chọn artifact repository | Cấu hình publish credentials và repository | Published coordinates, checksum, signature |
| Chọn security cadence | Thiết lập lịch review/update | Update PR, scan report và release metadata |

Có thể thêm cột owner, due date và trạng thái trong issue tracker. ADR chỉ liên kết tới công việc; không cần biến tài liệu thành bảng theo dõi tiến độ dài.

### Kiểm tra conformance

Trong pull request thay đổi toolchain, reviewer nên hỏi:

- Thay đổi có phù hợp ADR đang Accepted không?
- Wrapper version và checksum có được cập nhật cùng nhau không?
- JDK compiler/test/runtime có đúng quyết định không?
- Release target có bị thay đổi ngoài ý muốn không?
- Plugin và dependency có tương thích không?
- CI có xác nhận đúng toolchain và artifact digest không?
- Nếu thay đổi quyết định, ADR mới đã được tạo và liên kết chưa?

Nếu implementation cần đi lệch khỏi ADR, ghi rõ lý do và quyết định mới thay vì để cấu hình trôi dần khỏi tài liệu.

## 14. Khi nào cần xem xét lại quyết định toolchain?

ADR không có nghĩa là công nghệ sẽ được giữ mãi. Hãy xác định trigger ngay khi chấp nhận quyết định:

- JDK vendor kết thúc hỗ trợ hoặc thay đổi chính sách license.
- Java release target không còn đáp ứng dependency hoặc yêu cầu sản phẩm.
- Build tool/plugin ngừng được hỗ trợ hoặc có security issue.
- CI image/base image không còn nhận bản vá.
- Build time hoặc cache performance vượt ngưỡng.
- Runtime image không còn tương thích OS/architecture mục tiêu.
- Một security advisory yêu cầu nâng JDK hoặc plugin.
- Team thay đổi cách phân phối, từ JAR sang jpackage/container.
- Một dependency buộc nâng Java baseline.

Khi trigger xảy ra, đánh giá lại context và options. Nếu thay đổi đáng kể, tạo ADR mới. Không nâng version chỉ vì có bản mới; cần kiểm tra compatibility, support, security và kết quả thử nghiệm.

## 15. Những lỗi thường gặp khi ghi quyết định

| Lỗi | Vì sao không hữu ích | Cách sửa |
|---|---|---|
| Chỉ ghi “dùng Java 17” | Không rõ build JVM, compiler hay runtime | Ghi riêng từng lớp toolchain |
| Không ghi context | Người đọc không hiểu vấn đề gốc | Nêu trạng thái, constraint và bằng chứng |
| Không ghi phương án bị loại | Không biết nhóm đã cân nhắc gì | Ghi các lựa chọn thực sự và lý do |
| Chỉ ghi ưu điểm | Che mất chi phí vận hành | Ghi cả trade-off và rủi ro chấp nhận |
| Ghi “latest version” | Kết quả thay đổi theo thời điểm | Pin version cụ thể và ngày quyết định |
| Ghi vendor nhưng không ghi update policy | Không biết ai cập nhật và khi nào | Ghi owner, cadence và security trigger |
| Nhầm --release với JDK toolchain | Có thể compile bằng JDK ngoài dự kiến | Ghi compiler JDK và API target riêng |
| ADR không liên kết cấu hình | Không xác minh được implementation | Liên kết build file, CI và test evidence |
| Sửa ADR cũ sau khi đổi hướng | Mất lịch sử vì sao quyết định thay đổi | Tạo ADR mới và supersede ADR cũ |
| ADR quá dài như design specification | Khó tìm kết luận | Giữ decision ngắn, liên kết tài liệu chi tiết |
| Tạo ADR cho mọi thay đổi nhỏ | Tăng chi phí tài liệu | Chỉ ghi quyết định có ảnh hưởng đáng kể |

## 16. Checklist trước khi chấp nhận một decision record

- [ ] Tiêu đề nêu rõ quyết định.
- [ ] Phạm vi project/module/môi trường được xác định.
- [ ] Context có sự kiện và ràng buộc kiểm chứng được.
- [ ] Build JVM, compiler toolchain, release target và runtime được phân biệt.
- [ ] Hard constraints và decision drivers được nêu rõ.
- [ ] Có phương án hiện tại và các phương án thay thế thực tế.
- [ ] Có rationale và trade-off tích cực/tiêu cực.
- [ ] Version của JDK, build tool, plugin và dependency được ghi chính xác khi cần.
- [ ] Có bằng chứng thử nghiệm hoặc lý do vì sao chưa thể thử.
- [ ] Có owner và deciders.
- [ ] Có implementation tasks và validation criteria.
- [ ] Có rollback/review triggers.
- [ ] Có liên kết tới build configuration, CI, issue và tài liệu chính thức.
- [ ] Không chứa secret hoặc dữ liệu nhạy cảm.
- [ ] Trạng thái Proposed/Accepted/Rejected rõ ràng.
- [ ] Nếu thay quyết định cũ, ADR mới liên kết ADR cũ và nêu lý do.

## 17. Ghi nhớ

- Ghi quyết định để lưu lại điều gì đã chọn, vì sao chọn và hệ quả được chấp nhận.
- ADR phù hợp với quyết định toolchain có ảnh hưởng lâu dài hoặc nhiều môi trường.
- Một ADR nên tập trung vào một quyết định độc lập.
- Context phải mô tả sự kiện, vấn đề và constraint; Decision phải nói rõ lựa chọn.
- So sánh phương án bằng hard constraints, decision drivers và bằng chứng thử nghiệm.
- Ghi cả lợi ích, chi phí, rủi ro, owner và điều kiện xem xét lại.
- Phân biệt build JVM, compiler toolchain, release target, test runtime và production runtime.
- Maven/Gradle Wrapper pin build tool; Maven/Gradle toolchain kiểm soát JDK task; --release kiểm soát API và bytecode target.
- ADR giải thích lý do; build file và CI thực thi quyết định.
- Accepted ADR là lịch sử có giá trị; khi đổi hướng, tạo ADR mới và liên kết quyết định cũ.
- Theo dõi implementation bằng test, pipeline, artifact digest và review.
- Không ghi secret vào decision record.

## Tài liệu tham khảo chính thức

- [Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Maven Toolchains Guide](https://maven.apache.org/guides/mini/guide-using-toolchains)
- [Gradle Wrapper Basics](https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html)
- [Gradle JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [The javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Architectural Decision Record Process — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
- [Architecture Decision Record Templates](https://github.com/architecture-decision-record/architecture-decision-record/blob/main/skills/architecture-decision-record-skill/reference/templates.md)
- [Documenting Architecture Decisions — Government Digital Service](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html)
- [Architecture Decision Record — Martin Fowler](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)