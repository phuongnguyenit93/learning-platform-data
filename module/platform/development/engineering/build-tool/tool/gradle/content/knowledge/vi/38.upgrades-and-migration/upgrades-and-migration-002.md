# Đọc Compatibility Matrix, Release Notes và Upgrading Guide khi nâng cấp Gradle

## 1. Vì sao phải đọc cả ba loại tài liệu?

Đổi Gradle từ 8.x lên 9.x không chỉ là sửa một số trong `gradle/wrapper/gradle-wrapper.properties`. Gradle là build engine chạy trên JVM; nó còn tích hợp Kotlin/Groovy DSL, plugins, Java toolchains, dependency resolution, Test tasks, cache, task execution model và IDE/CI. Chỉ một phiên bản mới có thể thay đổi nhiều ranh giới tương thích:

- Java nào chạy được **Gradle Daemon**?
- JDK nào có thể dùng làm **Java toolchain để biên dịch hoặc chạy test**?
- Ứng dụng sinh bytecode cho Java bao nhiêu?
- Plugin nào sử dụng API đã deprecated hoặc removed?
- Version Kotlin Gradle Plugin/Android Gradle Plugin có thực sự hỗ trợ bản Gradle mới?
- Behavior của `Test`, `JavaCompile`, Wrapper, Tooling API có đổi không?
- Đường nâng từ source version đến target version đi qua những breaking changes nào?
- Các tác động đó sẽ được chứng minh bằng test/report/CI như thế nào?

Ba tài liệu có ba nhiệm vụ:

| Tài liệu | Trả lời | Không thay thế được |
| --- | --- | --- |
| **Compatibility Matrix** | Tổ hợp JVM/Gradle/toolchain/Kotlin/Groovy/Android/OS được thử và hỗ trợ đến đâu | Danh sách code cần sửa hoặc known issues |
| **Release Notes** | Bản mới thêm gì, sửa gì, thay behavior gì, known issues nào | Hướng dẫn đầy đủ nâng từ phiên bản cũ bất kỳ |
| **Upgrading Guide** | Breaking changes, deprecations, yêu cầu migration từ nguồn cũ | Kiểm tra vendor plugin versions và môi trường thực |

**Bài học này dạy cách đọc và đối chiếu tài liệu, biến chúng thành kế hoạch nâng cấp kiểm chứng được**, không chỉ cung cấp bảng số version. Các ví dụ Java 17+ và Gradle Kotlin DSL có lệnh `javac`, `java`, expected stdout, test và workflow CI.

**Mốc tài liệu:** ngày 09/11/2026, bản Gradle chính thức mới nhất được xác minh là **9.9.0**, phát hành ngày **07/11/2026**. Các nhận xét về Gradle 9.9 được gắn với mốc này. Khi thực hiện một nâng cấp thật, phải dùng **phiên bản đích đã được tổ chức duyệt** và tài liệu theo version, không tự mặc định target luôn là 9.9.

## 2. Quy trình tổng quát từ câu hỏi đến quyết định

~~~text
1. Kiểm kê hiện trạng
   Gradle Wrapper, JVM Daemon, toolchains, plugins, IDE, OS, CI
                      |
                      v
2. Đọc Compatibility Matrix cho TARGET
   Tìm constraints và những trục không hợp lệ
                      |
                      v
3. Đọc Release Notes các bản liên quan
   Features, behavior changes, known issues
                      |
                      v
4. Đọc toàn các Upgrading Guides áp dụng
   8.x -> major 9.0 -> từng thay đổi trong 9.x
                      |
                      v
5. Đọc vendor matrix của AGP/KGP/plugins
   Xác định plugin upgrades/compatibility gaps
                      |
                      v
6. Lập migration checklist có owners + evidence
                      |
                      v
7. Upgrade JDK/Wrapper/plugins có kiểm soát
                      |
                      v
8. Check build, test discovery, artifact, CI, IDE
                      |
                      v
9. Merge/rollout/rollback theo bằng chứng
~~~

**Đừng** nhảy thẳng tới lệnh nâng Wrapper chỉ vì thấy release mới. Trước đó phải chắc chắn runtime/CI có thể khởi động Gradle và những plugins quan trọng có đường nâng.

## 3. Dùng links có version thay vì chỉ /current

Trang `https://docs.gradle.org/current/...` trỏ tới phiên bản mới nhất **tại lúc truy cập**. Một PR năm 2026 có thể được audit lại sau vài năm, khi `current` đã đổi. Vì vậy lưu links gắn target version:

- Matrix Gradle 9.9: <https://docs.gradle.org/9.9.0/userguide/compatibility.html>
- Release Notes 9.9: <https://docs.gradle.org/9.9.0/release-notes.html>
- Hướng dẫn lên major 9.0: <https://docs.gradle.org/9.9.0/userguide/upgrading_major_version_9.html>
- Hướng dẫn trong nhánh 9.x: <https://docs.gradle.org/9.9.0/userguide/upgrading_version_9.html>
- Hướng dẫn trong nhánh 8.x: <https://docs.gradle.org/9.9.0/userguide/upgrading_version_8.html>
- Wrapper: <https://docs.gradle.org/9.9.0/userguide/gradle_wrapper.html>

Một tài liệu **9.9** có thể chứa guide cho **8.x** để hỗ trợ đọc đường di chuyển. Điều này không có nghĩa Gradle 8.x đã có tính năng 9.9: hãy luôn nhận diện version **được nói tới trong section**, không chỉ version của trang host.

### 3.1. Tài liệu Gradle không thay vendor docs

Gradle có Compatibility Matrix Android, nhưng Google Android Gradle Plugin (AGP) và Kotlin Gradle Plugin (KGP) có tài liệu compatibility/release notes riêng. Các plugins như Spring Boot, Shadow, Spotless, protobuf, Develocity hoặc internal convention plugin cũng vậy. **Gradle hỗ trợ một JVM không bảo đảm mọi plugin hỗ trợ JVM ấy.**

## 4. Kiểm kê baseline thật trước khi đọc matrix

Tối thiểu cần thu thập:

| Thành phần | Tìm tại đâu? | Điều phải ghi |
| --- | --- | --- |
| Gradle Wrapper | `gradle/wrapper/gradle-wrapper.properties` | Version/distribution URL/SHA |
| Gradle version đang chạy | `./gradlew --version` | Chính xác bản thực thi |
| JVM chạy Gradle | `--version`, Daemon JVM criteria, `org.gradle.java.home`, `JAVA_HOME` | JVM vendor/version/path |
| Java compiler/toolchain | `java { toolchain {...} }`, `javaToolchains` | JDK languageVersion/vendor |
| Target Java bytecode | `JavaCompile.options.release`, targetCompatibility | Classfile/API level |
| Plugins | `plugins` block, version catalog, `buildSrc`, included builds | ID/version/source |
| Dependency repositories | settings, enterprise init scripts | Plugin vs library repositories |
| CI/IDE | Workflow/runner configs/IDE settings | JDK/OS/architecture/tooling |
| Test frameworks | JUnit/TestNG/Spock/plugin | Engine/filtering/report baseline |
| Build state | Baseline logs, deprecation warnings, test counts | So sánh sau nâng |

Trên Linux/macOS:

~~~bash
./gradlew --version
java -version
javac -version
./gradlew help --warning-mode=all --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
java -version
javac -version
.\gradlew.bat help --warning-mode=all --stacktrace
~~~

**Chú ý:** `java -version` trong terminal **không nhất thiết** là JVM chạy Gradle Daemon, nếu `org.gradle.java.home` hoặc Daemon JVM criteria, IDE JVM được cấu hình khác. Và `javac` trên PATH không nhất thiết là Java toolchain mà `compileJava` chọn.

**An toàn:** Wrapper/settings/plugins là mã thực thi. Chạy những lệnh này trên checkout đáng tin hoặc CI sandbox có quyền thấp, không chạy PR chưa review trên host giữ deployment secrets.

## 5. Cách đọc Compatibility Matrix: bắt đầu từ đúng cột

Matrix của Gradle phân nhóm:

1. **Java Runtime**
2. **Kotlin**
3. **Groovy**
4. **Android**
5. **Target Platforms**

Phần Java đặc biệt dễ đọc sai. Câu “Java 21 có tương thích với Gradle 8.4?” có ít nhất ba nghĩa:

- JVM 21 **chạy Gradle Daemon** được không?
- JDK 21 được dùng làm **toolchain biên dịch/test** không?
- Ứng dụng cần chạy trên Java 21 nên bytecode target 21 có được phát không?

Matrix Java phân biệt **Support for toolchains** và **Support for running Gradle**. Không được lấy giá trị từ cột thứ nhất để kết luận cột thứ hai.

### 5.1. Trích những mốc Java đã xác minh trong Gradle 9.9 Matrix

| Java version | Gradle đầu tiên hỗ trợ **toolchain** | Gradle đầu tiên hỗ trợ **chạy Gradle** |
| --- | --- | --- |
| Java 17 | 7.3 | 7.3 |
| Java 20 | 8.1 | 8.3 |
| Java 21 | 8.4 | 8.5 |
| Java 22 | 8.7 | 8.8 |
| Java 23 | 8.10 | 8.10 |
| Java 24 | 8.14 | 8.14 |
| Java 25 | 9.1.0 | 9.1.0 |
| Java 26 | 9.4.0 | 9.4.0 |
| Java 27 | 9.8.0 | 9.8.0 |

**Cách diễn giải:** Gradle 8.4 có thể dùng JDK 21 làm toolchain, nhưng chỉ từ Gradle 8.5 mới chính thức hỗ trợ chạy Gradle trên JVM 21. Để chọn Java 27 làm Daemon JVM trên nhánh 9.x cần Gradle 9.8 trở lên theo matrix tham chiếu.

### 5.2. Gradle 9.9 Daemon JVM phải ở dải nào?

Tại mốc Gradle 9.9, Matrix nêu **JVM 17 đến JVM 27** được hỗ trợ chạy Gradle, còn JVM 28 trở lên chưa được hỗ trợ. Đặc biệt **Gradle 9.0 trở đi yêu cầu JVM 17+ để chạy Gradle Daemon**.

Đây **không** đồng nghĩa mọi chương trình Java phải compile thành bytecode 17; Gradle vẫn có khả năng dùng các JDK khác qua toolchains trong phạm vi được hỗ trợ. Wrapper/launcher/Tooling API **client** có một số tương thích Java 8 riêng, nhưng đừng suy Gradle **Daemon** 9.x chạy Java 8 được.

### 5.3. Bảng nào không chứng minh plugin bên thứ ba tương thích?

Java Matrix không chứng minh Kotlin Gradle Plugin, Android Gradle Plugin, Error Prone, Spotless hoặc plugin nội bộ đã hỗ trợ Java/Gradle target. Với plugin, cần **version support range của vendor** và ít nhất một functional test trên target Gradle.

### 5.4. “Không liệt kê” không tự bằng “chắc chắn crash”

Matrix liệt kê các cấu hình được Gradle thử và công bố support. Có tổ hợp chưa được chính thức xác nhận vẫn có thể chạy; tuy nhiên production CI cần dựa vào **support policy và bằng chứng kiểm thử**, không dựa vào một lượt may mắn.

## 6. Tách ba Java version: Daemon, toolchain, bytecode

~~~text
JVM chạy Gradle Daemon
          |
          v
Gradle configuration + task graph
          |
          v
JavaCompile Toolchain JDK
          |
          v
javac --release N
          |
          v
Bytecode + Java API target N
          |
          v
JVM của người dùng / test runtime
~~~

Ví dụ trong `build.gradle.kts` của project có Java plugin:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

- `java.toolchain` yêu cầu JDK 17 cho các tasks hỗ trợ toolchains.
- `options.release.set(17)` ràng buộc compile target Java API/bytecode 17.
- JVM để chạy Gradle có thể là 17 hoặc 21 với Gradle version hỗ trợ; không tự thay khi đặt toolchain.
- JVM để chạy artifact cuối cùng có thể khác; phải thử đúng runtime mà sản phẩm hỗ trợ.

**Anti-pattern:** báo lỗi “Gradle 9 requires JVM 17” rồi chỉ sửa `options.release` từ 11 thành 17. Nó không nâng Java runtime của Gradle Daemon, nên không giải quyết root cause.

### 6.1. Thứ tự khi source Gradle quá cũ

Nếu source Gradle chỉ chạy trên JVM 8/11 và target yêu cầu JVM 17, bạn có thể cần:
1. Giữ một JDK tương thích với source để chạy bước trung gian.
2. Nâng Gradle tới một release hỗ trợ runtime JDK mới.
3. Chuyển Daemon JVM sang 17 hoặc bản hợp lệ khác.
4. Tiếp tục tới target Gradle/plug-in version.
5. Giữ bytecode target theo contract ứng dụng, không tự nâng vì đổi build tool.

Không giả định chỉ thay `JAVA_HOME` một lần là giải quyết mọi old Gradle/plugin issues.

## 7. Cách đọc Kotlin, Groovy, Android và OS entries

### Kotlin và Kotlin DSL

Gradle có **embedded Kotlin version** cho Gradle Kotlin DSL scripts/precompiled build logic. Application có thể dùng **Kotlin Gradle Plugin** với version khác. Đây là hai hệ version liên quan nhưng **không bắt buộc bằng nhau**. Khi nâng Gradle, cần:
- Đọc embedded Kotlin section của Matrix.
- Đọc KGP/Gradle support range từ Kotlin docs.
- Compile lại `buildSrc`/included `build-logic`/precompiled plugins.
- Kiểm tra Kotlin DSL compilation và IDE sync riêng.

### Groovy và Groovy DSL

`build.gradle` chạy bằng Groovy DSL trong Gradle, và plugin viết bằng Groovy có thể phụ thuộc Groovy runtime. Gradle 9 chuyển embedded Groovy lên dòng 4.x. Đừng tin một Groovy binary plugin build cho Gradle 7/8 sẽ hoạt động ở 9.x nếu dùng Groovy/Gradle internals chưa public; cần test/update vendor version.

### Android / AGP

Gradle Matrix Android mô tả các AGP versions được thử với Gradle. AGP còn có **minimum Gradle/JDK/Android Studio/SDK requirements** của chính Android. Xét **giao của hai matrices**, không nhìn một bên.

Ví dụ quan trọng đã được Gradle 9.x Upgrading Guide ghi nhận: ở Gradle 9.6, một số **internal Problems API** classes bị loại, làm **AGP 8.x** hoặc plugin khác dùng internals ấy lỗi. Khuyến nghị dùng AGP 9.x tương thích hoặc ở lại Gradle version vendor hỗ trợ trong lúc chuẩn bị. Đừng thêm JAR chứa `org.gradle.api.problems.internal.*` vào classpath để “chữa” thiếu class.

### Target Platforms

Kiểm OS/CPU (Windows x86/ARM, Ubuntu, macOS, Alpine, v.v.) cùng JDK/runtime. CI container có architecture hoặc filesystem khác local. Một tổ hợp không được Gradle thử có thể chạy nhưng không đương nhiên chính thức supported.

## 8. Lập bảng giao giữa Gradle và plugin vendor

| Thành phần | Source | Target | Kiểm tra phải có |
| --- | --- | --- | --- |
| Gradle Wrapper | 8.x/9.x | 9.9.0 (ví dụ) | Gradle Matrix + Upgrade Guides |
| JVM chạy Daemon | Java 11/17/21 | Java 17+ hợp lệ | Java Runtime cột “running Gradle” |
| Compile toolchain | Java 17 | Java 17 | Java toolchain + CI JDK provisioning |
| Bytecode target | 8/11/17 | Theo product | `options.release`/runtime consumer tests |
| Kotlin Gradle Plugin | Theo catalog | Vendor supported | Kotlin compatibility docs |
| Android Gradle Plugin | AGP 8.x/9.x | Vendor supported | AGP+Gradle matrices |
| Spring Boot/Shadow/... | Version hiện tại | Vendor supported | Plugin release notes/TestKit |
| Internal convention plugin | Source binary plugin | Rebuild/test | Public Gradle API compatibility |
| IDE/Tooling API | IDE/plugin hiện tại | Supported version | IDE/vendor notes |
| CI runner | Linux/Windows/ARM/... | Target env | OS/JDK/arch tests |

Cột “Target” không nên ghi theo phỏng đoán. Nếu vendor chưa hỗ trợ Gradle đích, cần mở issue nâng plugin, giữ lại bản Gradle cũ tạm thời hoặc thử trong isolated branch **không publish**.

## 9. Đọc Release Notes để tìm tác động, không chỉ tính năng mới

Release Notes gồm nhiều phần:
- New features and usability improvements.
- Performance changes.
- CLI, logging, Problems API/Tooling API.
- Core plugin/task/test changes.
- Docs/feature lifecycle.
- Fixed issues và Known issues.
- Upgrade instructions và links tới Matrix/Guide.

Cách đọc mỗi bullet:

1. **Điều kiện:** dự án có dùng feature/plugin/task ấy?
2. **Behavior thay đổi:** config, output, test count, API hay chỉ performance?
3. **Risks:** có thể phá CI, plugin, IDE hoặc artifact?
4. **Tests:** dùng lệnh/assertion/report nào để xác minh?
5. **Owner:** ai xử lý nếu có regression?
6. **Rollout:** có cần tăng dần hoặc pin version không?

| Kiểu release note | Việc nên hỏi | Evidence |
| --- | --- | --- |
| Build nhanh hơn | Workload của mình có trùng benchmark? | Profile median/p95 |
| Embedded Kotlin/Groovy update | Scripts/plugins có compile? | build-logic tests |
| Test filtering | Test counts/selectors có đổi? | XML/HTML report |
| Wrapper behavior | Mirror URL/checksum có đổi? | Wrapper diff |
| Problems API change | CI parser/tooling client có lỗi? | Tooling integration tests |
| Known issue | Dự án có trúng điều kiện? | Repro/workaround document |
| Feature incubating | Có dám bật production? | Vendor policy + guardrails |

Release Notes thường không đủ để xác định **toàn bộ** các thay đổi phải làm từ version cũ; chúng cần đi cùng Upgrading Guide.

## 10. Ví dụ cụ thể từ Release Notes Gradle 9.9.0

Ngày phát hành 07/11/2026, Release Notes 9.9 ghi những mục đáng quan tâm:

1. **Kotlin DSL scripts hỗ trợ incremental compilation**. Khi recompilation do đổi `buildSrc`/included build, Gradle có thể compile phần scripts bị ảnh hưởng; một benchmark của Gradle cho kết quả **nhanh hơn tới 65%** trong tình huống được đo. Không suy cả build nhanh hơn 65%.
2. **JUnit Platform test filtering** chính xác hơn đối với tests không được khai báo là methods, như một số ArchUnit rules hoặc Spek scopes. `--tests` có thể chọn tập tests khác trước; kiểm report/test count.
3. **Wrapper giữ nhiều customized properties** khi regenerate: distribution type, timeout/retry, paths/bases, URL validation. Nhưng `distributionUrl` vẫn được regenerate theo version mới, do đó **custom mirror host không nhất thiết được giữ**. Review diff.
4. **Problems API** nhóm diagnostic problem IDs theo hierarchy rõ hơn. Tooling client, Build Scan hoặc CI parser dựa vào legacy IDs có thể cần cập nhật.
5. **Isolated Projects/Eclipse Buildship** cải thiện; chỉ có tác dụng nếu dùng feature.
6. **ProviderFactory APIs và Sync enhancement** hữu ích cho plugin author, không có nghĩa mọi build script phải dùng ngay.

**Hướng diễn giải quan trọng:** “cải thiện tới 65%” là số benchmark **Kotlin DSL script recompilation** trong tình huống cụ thể, không phải guarantee cho Gradle CI của bạn. Nếu script không thường recompilation, thay đổi có thể không thấy rõ.

### 10.1. Với Test filtering, kiểm đúng tập chứ không chỉ BUILD SUCCESSFUL

Nếu CI có:

~~~bash
./gradlew test --tests "demo.ExampleTest.someCase"
~~~

cần xem test XML/report để xác nhận đúng test case được chọn. Đặc biệt với test engines dùng non-method tests, so behavior/source vs target; một pipeline vẫn xanh khi chạy **ít tests hơn dự kiến** là regression.

## 11. Upgrading Guides mới là bộ quy tắc migration

Gradle tách:

- **Upgrading to Gradle 9.0.0:** ranh giới major từ Gradle 8 lên 9.
- **Upgrading within Gradle 9.x:** các breaking changes, deprecations từ 9.0 qua từng bản 9.1…9.9.
- **Upgrading within Gradle 8.x:** thay đổi khi còn đi qua các bản 8.x.
- Major guide trước đó nếu source là 7.x hoặc cũ hơn.

Nếu dự án đang ở Gradle 8.7 và đích là 9.9:
1. Đọc những thay đổi trong 8.x sau 8.7 mà bạn cần đi qua.
2. Đọc tất cả yêu cầu thay đổi của major 9.0.
3. Đọc những thay đổi trong 9.x từ 9.0 đến 9.9.
4. Đọc Release Notes/known issues của target và các bản trung gian trọng yếu.
5. Tra vendor compatibility của plugins.

**Sai phổ biến:** chỉ mở section “Upgrading from 9.8.0 and earlier” vì target là 9.9, rồi bỏ qua các yêu cầu major 9.0.

### 11.1. Hiểu tiêu đề “Upgrading from X and earlier”

Guide 9.x gồm sections dạng:

~~~text
Upgrading from 9.8.0 and earlier
Upgrading from 9.7.0 and earlier
Upgrading from 9.6.0 and earlier
...
Upgrading from 9.0.0 and earlier
~~~

Mỗi section nêu changes được đưa vào các bản sau X. Nếu source là 9.3, bạn cần xét **tất cả changes sau 9.3 đến target**, không chỉ phần có chữ “9.3”. Cách làm an toàn là đọc các mục trên toàn guide phù hợp, đánh dấu “Applies?/No/Needs investigation” và test.

### 11.2. Potential Breaking Changes khác Deprecations

**Potential Breaking Changes:** behavior/API/constraints có thể gây lỗi ngay khi sang bản mới.

**Deprecations:** API còn hoạt động trong một thời gian, nhưng đã có cảnh báo và có kế hoạch xóa hoặc đổi behavior; đây là nợ nâng cấp phải xử lý trước target remove.

**Known Issues:** lỗi đã được nhận diện nhưng chưa chắc sửa trong release. **Fixed Issues:** lỗi cũ đã được xử lý, nhưng vẫn phải xem có regressions không.

Nếu guide nói “will become an error in Gradle 10”, tức là cần đưa việc sửa vào kế hoạch **trước 10**, ngay cả khi hiện tại 9.9 vẫn chạy.

## 12. Các ranh giới lớn khi chuyển lên Gradle 9.0

Một số nhóm được major 9 guide nêu:

| Nhóm | Điều thay đổi | Hệ quả với dự án |
| --- | --- | --- |
| JVM runtime | Gradle Daemon cần Java 17+ | CI/IDE/JDK setup phải được nâng |
| Groovy DSL | Embedded Groovy 4.x | Scripts/plugins cũ có thể không tương thích |
| Kotlin/Groovy DSL plugin binaries | Minimum Gradle/plugin compatibility thay đổi | Cần rebuild/update binary plugins |
| AGP/KGP/enterprise plugin | Minimum supported versions thay đổi | Tra vendor matrices |
| Settings/project directories | Project dirs phải tồn tại và writable | Scripts tạo modules động có thể cần sửa |
| Test task behavior | Một số test execution changes | Assert tests thực chạy |
| Plugin task validation | Toolchain/API/validation constraints | Sửa custom plugin/task code |
| Internal Gradle APIs | Một số internals không còn | Nâng plugin, dùng public API |

Đây là **ví dụ rút ra từ các nhóm**, không phải bản sao toàn guide. Nếu một project không dùng Groovy plugin hay Android thì đánh dấu No với evidence; nhưng không gạch bỏ khi chưa kiểm plugins transitive.

### 12.1. Chỉ nâng JavaCompile target không làm Gradle Daemon đạt yêu cầu

Trường hợp:
- Source Daemon Java 11.
- Target Gradle 9.9 cần JVM 17+.
- Project `options.release.set(11)` để phục vụ users Java 11.

Bạn phải nâng **Daemon JVM** lên 17+ theo matrix, nhưng **có thể vẫn compile Java 11 bytecode** bằng toolchain/`--release 11` nếu Gradle/toolchain hỗ trợ và product cần. Đây là hai yêu cầu độc lập.

## 13. Ví dụ breaking/deprecation trong nhánh Gradle 9.x

Hướng dẫn trong nhánh 9.x đến 9.9 có những ví dụ cụ thể:

- **Gradle 9.9:** thay đổi nhóm/ID của Problems API diagnostics; những tooling clients match theo legacy deprecation/compilation IDs cần sửa. `GradleException` có resolution suggestions API; custom subclass định nghĩa cùng method name với return type không tương thích có thể fail compile.
- **Gradle 9.8:** cập nhật embedded Kotlin/Groovy/ASM/JaCoCo; plugin/build logic có thể cần test.
- **Gradle 9.8 deprecation:** tự gọi `ProcessBuilder.start`, `Runtime.exec` hoặc `ExecOperations.exec` ngay **configuration phase** bị deprecated; chuyển work vào task action hoặc dùng `providers.exec`/ValueSource khi cần.
- **Gradle 9.8 deprecation:** Tooling API model parallelism phụ thuộc ngầm vào `org.gradle.parallel` không còn là policy bền vững. Có `org.gradle.tooling.parallel` riêng; phải xác định rõ khi dùng IDE/model APIs.
- **Gradle 9.6:** một số Gradle internal Problems API classes bị loại. Các bản AGP 8.x hoặc plugin khác dựa vào internals có thể fail; nâng plugin hoặc giữ Gradle version được hỗ trợ.
- **Các phiên bản 9.x khác:** thay đổi Configuration Cache, plugin validation, implicit dependencies giữa composite builds, task outputs và deprecated Gradle APIs.

**Lưu ý:** danh sách trên chỉ minh họa **cách trích ảnh hưởng** từ upgrading guide, không thể thay toàn bộ guide. Để lên target 9.9, phải đọc mọi mục áp dụng giữa source và target, bao gồm những mục không có trong bảng.

### 13.1. Ví dụ process launch trong configuration phase

Anti-pattern, **không dùng trên production**:

~~~kotlin
// Không nên: process chạy ngay khi Gradle cấu hình build.
val revision = ProcessBuilder(
    "git", "rev-parse", "--short", "HEAD"
).start().inputStream.bufferedReader().readText().trim()
~~~

Trong các bản Gradle mới, chạy process trực tiếp ở configuration phase làm Configuration Cache không tương thích và bị deprecated. Một cách cấu trúc lại khi thật sự cần dữ liệu từ process:

~~~kotlin
// Provider-backed process output, chỉ nên dùng trong trusted project.
val revision = providers.exec {
    commandLine("git", "rev-parse", "--short", "HEAD")
}.standardOutput.asText.map { it.trim() }
~~~

Đây là **mẫu provider**, không phải chương trình runnable độc lập. Phải nối `revision` vào `@Input` hoặc task property thực sự cần nó; không ép `get()` sớm. Nếu CI không cài git hoặc workspace không có .git, lệnh sẽ fail khi provider được resolve: cần fallback/policy có chủ đích.

## 14. Chạy deprecation checks trên bản đang dùng

Trước khi nâng Wrapper, trên trusted repo:

~~~bash
./gradlew help --warning-mode=all --stacktrace
./gradlew test --warning-mode=all --stacktrace
./gradlew build --warning-mode=all --stacktrace
~~~

Tại sao cần nhiều tasks?
- `help` thấy nhiều settings/plugin/configuration warnings.
- `test` chạm test engine, compile và test plugins.
- `build` có packaging/verification lifecycle.
- Custom integration/release tasks có thể chỉ bộc lộ warning khi được cấu hình/thực thi; cần liệt kê chúng riêng.

PowerShell:

~~~powershell
.\gradlew.bat help --warning-mode=all --stacktrace
.\gradlew.bat test --warning-mode=all --stacktrace
.\gradlew.bat build --warning-mode=all --stacktrace
~~~

Sau khi đã xử lý warning baseline, có thể áp gate:

~~~bash
./gradlew help --warning-mode=fail
~~~

`--warning-mode=fail` có thể fail vì deprecation warnings, nên đừng bật không có kế hoạch với plugins cũ chưa sửa được. `--warning-mode=all` cung cấp chi tiết để gán nguồn warning.

### 14.1. Warning từ third-party plugin

Nếu không tìm thấy deprecated API trong build script nhưng warnings xuất hiện, kiểm plugin stacktrace. Plugin implementation có thể gọi Gradle internals/old APIs; cần update vendor plugin hoặc internal convention plugin, không sửa Java app source không liên quan.

### 14.2. Build Scan là một tùy chọn, không bắt buộc

Gradle upgrading guides gợi ý `gradle help --scan` và xem deprecations. Nhưng Build Scan/Develocity có thể upload metadata theo cấu hình. Nếu security policy không cho phép, dùng console `--warning-mode=all`/local diagnostics và không bắt buộc dùng scan.

## 15. Tạo migration table từ ba nguồn

Một PR nâng 8.x lên 9.9 có thể tạo bảng:

| Evidence | Constraint/Change | Applies? | Owner | Validation |
| --- | --- | --- | --- | --- |
| Matrix 9.9 | Daemon JVM ≥17 | Có nếu CI Java 11 | CI owner | `./gradlew --version` |
| Matrix toolchain | Java 17 compile toolchain | Có | Java owner | `compileJava --info` |
| Major 9 guide | Plugin/Groovy DSL compatibility | Kiểm | Build platform | build-logic/TestKit |
| 9.x guide | Config-time process execution deprecated | Kiểm | Plugin owner | warning scan |
| 9.x guide | AGP 8.x/Problems API internals | Nếu Android | Android owner | vendor matrix + build |
| Release 9.9 | Test filters non-method | Nếu `--tests` custom | QA | Assert count/report |
| Release 9.9 | Wrapper properties regeneration | Nếu mirror host custom | DevEx | diff Wrapper |
| Plugin docs | KGP, Spotless, internal plugins | Theo plugin | Module owner | Functional tests |
| CI policy | Artifact/dependency integrity | Có | Release owner | Wrapper checksum + scan |

Cột `Applies?` nên là **Yes/No/Investigate với bằng chứng** (file/path/plugin/reference), không dựa suy đoán. Mỗi entry cần action được thực thi/test xác minh chứ không chỉ URL.

## 16. Lộ trình mẫu 8.7 → 9.9.0

~~~text
Gradle 8.7
   |
   +--> warnings hiện có + plugin inventory
   |
   +--> read changes in Gradle 8.x after 8.7
   |       |
   |       +--> optional intermediate 8.14.x validation
   |
   +--> read major Upgrade to Gradle 9.0
   |       |
   |       +--> Daemon JVM 17+, plugin upgrades
   |
   +--> read applicable changes within Gradle 9.x
   |       |
   |       +--> remove deprecated/incompatible patterns
   |
   v
Target 9.9.0 on migration branch
   |
   +--> CLI/build/test/IDE/CI verification
   |
   v
Reviewed protected-branch rollout
~~~

**Không có yêu cầu mọi dự án bắt buộc phải commit một PR cho mỗi phiên bản trung gian.** Việc nâng qua intermediate steps có lợi khi repo lớn và nhiều plugins hoặc khi source Gradle quá cũ; điều bắt buộc là **đọc đầy đủ thay đổi** trong khoảng nâng và có bằng chứng kiểm thử.

### 16.1. Giữ phạm vi nâng nhỏ để dễ debug

Nếu một PR đổi Gradle, KGP, AGP, 20 libraries, CI image, Java source level và publishing pipeline, lúc có failure khó xác định nguyên nhân. Nên chia thay đổi: runtime readiness → plugin compatibility → Wrapper → build-logic repairs → CI rollout, mỗi phần có test.

## 17. Nâng Gradle Wrapper đúng cách

Wrapper lưu trong:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Trên branch tin cậy và source Gradle/JDK đang chạy được:

Linux/macOS:

~~~bash
./gradlew wrapper --gradle-version 9.9.0
./gradlew wrapper
~~~

PowerShell:

~~~powershell
.\gradlew.bat wrapper --gradle-version 9.9.0
.\gradlew.bat wrapper
~~~

Lần đầu trỏ tới distribution target; lần thứ hai dùng distribution mới và giúp cập nhật scripts/JAR theo Wrapper task. Nếu muốn distribution `all` thay `bin`, chọn theo IDE/policy:

~~~bash
./gradlew wrapper --gradle-version 9.9.0 --distribution-type all
./gradlew wrapper
~~~

**Không tự chạy trên checkout PR chưa tin cậy với release secrets**: Wrapper scripts/JAR được thực thi trước project build. Nếu source Gradle không thể khởi động với JDK mới, dùng JDK cũ phù hợp ở bước trung gian hoặc nâng dần như phần 16.

### 17.1. 9.9 giữ property gì và không giữ gì?

Release Notes 9.9 ghi Wrapper task giữ nhiều customized settings hơn, nhưng **`distributionUrl` được regenerate** theo version target. Nếu công ty dùng internal distribution mirror, phải kiểm tra có bị đổi thành host khác không.

Sau nâng review đủ bốn files và:
- `distributionUrl` version/host/HTTPS/distribution `bin` hay `all`.
- `distributionSha256Sum` dùng SHA-256 **đúng distribution ZIP target** từ trusted source.
- Timeout/retry/retry backoff/custom paths/base/URL validation.
- Quyền executable của `gradlew`.
- Wrapper JAR và scripts có khớp official release được phê duyệt không.
- Git diff có thay đổi ngoài dự kiến không.

**Không dùng checksum cũ của Gradle 8 cho ZIP Gradle 9.9.** Không coi một SHA do PR tự thêm là independent trust anchor; verify từ <https://gradle.org/release-checksums/>.

### 17.2. Wrapper khác system Gradle

`gradle --version` có thể chạy installation toàn máy, không phải version theo repository. Trong hướng dẫn/CI luôn ưu tiên `./gradlew` hoặc `.\gradlew.bat` để dùng distribution được pin.

## 18. Java 17+ demo để so trước và sau nâng cấp

Dự án `gradle-upgrade-lab` sử dụng Application plugin built-in của Gradle, một Java class Java 17 và hai JUnit Jupiter tests. Có thể chạy bằng Gradle hoặc compile trực tiếp bằng `javac`/`java` để tách lỗi Gradle khỏi lỗi Java source.

### 18.1. Cấu trúc project

~~~text
gradle-upgrade-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/UpgradeHello.java
    └── test/java/demo/UpgradeHelloTest.java
~~~

Wrapper phải được tạo thật bằng Gradle, không tự tạo script/JAR rỗng. Cần JDK 17 để chạy Gradle 9.9 và để compile Java 17 trong môi trường mẫu, cùng repository đã duyệt để tải JUnit khi chạy tests.

### 18.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-upgrade-lab"

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

Repository này chỉ phục vụ dependencies như JUnit; `application` là core plugin của Gradle. Tổ chức có mirror riêng nên cấu hình repository policy phù hợp; không thêm repository lạ chỉ để pass một build.

### 18.3. build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

group = "org.example.training"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.UpgradeHello")
}
~~~

JUnit versions được pin để minh họa; **không khẳng định đây là phiên bản mới nhất hiện nay**. `useJUnitPlatform()` cần thiết để Test task nhận JUnit Jupiter tests. Toolchain 17 không đồng nghĩa Daemon JVM đã được đặt thành 17. Nếu plugin/library bên ngoài cần JVM mới hơn, đó là constraint độc lập phải xét.

### 18.4. src/main/java/demo/UpgradeHello.java

~~~java
package demo;

public final class UpgradeHello {
    private UpgradeHello() {
    }

    public static String greeting(String name) {
        return "Gradle upgrade: Hello, " + name + "!";
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(greeting(name));
    }
}
~~~

### 18.5. src/test/java/demo/UpgradeHelloTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class UpgradeHelloTest {
    @Test
    void greetsAda() {
        assertEquals(
            "Gradle upgrade: Hello, Ada!",
            UpgradeHello.greeting("Ada")
        );
    }

    @Test
    void greetsDefault() {
        assertEquals(
            "Gradle upgrade: Hello, Gradle!",
            UpgradeHello.greeting("Gradle")
        );
    }
}
~~~

Đây là mã JUnit test hoàn chỉnh trong Gradle build đã khai báo dependencies. Nó kiểm tra logic chương trình, không tự chứng minh mọi plugin migration đã xong.

## 19. Chạy Gradle demo và đối chiếu stdout

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean test --warning-mode=all
./gradlew run --args="Ada" --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test --warning-mode=all
.\gradlew.bat run --args="Ada" --quiet
~~~

**Stdout chính xác từ Java Main với argument Ada:**

~~~text
Gradle upgrade: Hello, Ada!
~~~

Không truyền args:

~~~bash
./gradlew run --quiet
~~~

Java Main in:

~~~text
Gradle upgrade: Hello, Gradle!
~~~

Còn Gradle logs/test outcome có thể khác nhau theo JDK, Gradle version và trạng thái caches. Không bịa một transcript đầy đủ với task durations và downloads.

### 19.1. Kiểm test selectors

~~~bash
./gradlew test \
    --tests "demo.UpgradeHelloTest.greetsAda" \
    --warning-mode=all
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "demo.UpgradeHelloTest.greetsAda" --warning-mode=all
~~~

Với demo, filter chọn test `greetsAda`. Với JUnit Platform non-method tests (ArchUnit/Spek/custom engines), đọc Release Notes Gradle 9.9 và so **test reports/count** trước–sau. Không chỉ nhìn `BUILD SUCCESSFUL`.

### 19.2. Chạy Java trực tiếp bằng javac/java 17

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/UpgradeHello.java
java -cp out demo.UpgradeHello Ada
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\UpgradeHello.java
java -cp out demo.UpgradeHello Ada
~~~

**Stdout đúng:**

~~~text
Gradle upgrade: Hello, Ada!
~~~

`javac/java` thuần không chạy JUnit/Gradle Wrapper/plugins; nó chỉ tách bài toán Java source. Nếu javac PASS mà Gradle fail, hãy điều tra runtime/toolchain/plugin/build configuration, không tuyên bố migration đã thành công.

## 20. Ma trận môi trường để kiểm chứng ba trục Java

Giả sử Gradle 9.9, app compile target Java 17:

| CI job | Daemon JVM | Compiler toolchain | Target `--release` | Nhận xét |
| --- | --- | --- | --- | --- |
| A | 17 | 17 | 17 | Hợp lệ |
| B | 21 | 17 | 17 | Hợp lệ nếu JDK 17 toolchain khả dụng |
| C | 27 | 17 | 17 | Matrix 9.9 hỗ trợ Daemon JVM 27; vẫn cần plugin test |
| D | 11 | 17 | 17 | Không hợp lệ cho Gradle 9.x Daemon |
| E | 17 | 21 | 21 | Hợp lệ khi toolchain 21 và consumer runtime hỗ trợ |
| F | 17 | 17 | 21 | Không thể dùng javac 17 để phát bytecode Java 21 |

Đây là **điều kiện Gradle/JDK**, không chứng minh AGP/KGP hoặc mọi plugin hoạt động. Khi dùng Java toolchains, kiểm có JDK được cài hoặc resolver/provisioning được cấu hình. Nếu không, có thể nhận lỗi `No matching toolchains found`.

### 20.1. Kiểm thông tin toolchain

Dự án có Java plugin thường có task `javaToolchains` giúp liệt kê JDK Gradle phát hiện. Chạy khi cần chẩn đoán:

~~~bash
./gradlew javaToolchains
./gradlew compileJava --info
~~~

Không dựa vào `java -version` duy nhất để suy compile toolchain.

## 21. Nâng plugin và build logic đúng cách

Một codebase có thể dùng:

- Kotlin DSL scripts, version catalogs.
- Groovy DSL, custom Gradle plugins.
- `buildSrc`/included `build-logic`.
- Android Gradle Plugin hoặc Kotlin Gradle Plugin.
- Spring Boot/Shadow/Spotless/protobuf/Develocity.
- Custom tasks có Gradle `org.gradle.internal.*` references.
- TestKit functional tests dùng một Gradle distribution khác.

Khi target Gradle API thay đổi, first failure có thể ở **plugin configuration** hoặc class loading, trước task JavaCompile. Quy trình:

1. Xác định plugin ID/version, owner và dependencies.
2. Tìm vendor supported Gradle range.
3. Cập nhật plugin version trong `plugins`/version catalog khi cần.
4. Rebuild internal plugin với public Gradle APIs.
5. Chạy plugin functional TestKit tests trên target Gradle distribution.
6. Kiểm caching, task inputs/outputs, Configuration Cache compatibility.
7. Test application consumer trên clean checkout.

Nếu bị `NoClassDefFoundError: org/gradle/api/problems/internal/...`, đó có thể là plugin dùng internal Gradle API đã remove; Gradle 9.x guide có trường hợp AGP 8.x khi đến Gradle 9.6+. Đừng vá bằng cách đưa Gradle internal JAR cũ vào build classpath.

### 21.1. TestKit nhiều Gradle versions

Gradle TestKit hỗ trợ `GradleRunner.withGradleVersion("9.9.0")` trong plugin functional tests. Có thể chạy matrix distribution versions nếu mỗi target được support và JDK/runtime phù hợp. Điều này kiểm plugin API compatibility tốt hơn một lần chạy `help` ở consumer project.

Đây là API tham khảo, không phải lệnh CLI chạy trực tiếp. Plugin-under-test classpath và TestKit test project phải được cấu hình đúng.

## 22. Configuration Cache, Build Cache và incremental tasks

Nâng Gradle có thể khiến cache behavior đổi:

- **Configuration Cache** lưu/reuse task graph/configuration result; custom task action đọc `Project`/extension state có thể bị báo lỗi.
- **Build Cache** lưu/restores task outputs theo inputs/implementation fingerprints; đổi Gradle/task implementation có thể dẫn đến cache miss hợp lệ.
- **UP-TO-DATE** có thể skip task khi inputs/outputs không đổi.
- **Incremental compilation** giảm số class/source cần compile khi có source changes.

**Không suy build có lỗi chỉ vì sau nâng nhiều tasks chạy lại**. Cache key/history có thể đổi; điều quan trọng là outputs đúng, test counts đủ, không có hidden inputs/implicit dependencies.

Ví dụ kiểm Configuration Cache sau khi build đã nâng:

~~~bash
./gradlew test --configuration-cache
./gradlew test --configuration-cache
~~~

Nếu một plugin không tương thích, xem Configuration Cache report để truy task/plugin có lỗi, không lập tức bật flag bỏ qua vấn đề làm release không đáng tin.

## 23. Multi-project, composite build và IDE có thể lỗi riêng

Một monorepo có `:api`, `:core`, `:cli`, `:integration-tests`, `buildSrc` và included `build-logic` cần kiểm:

- Mỗi subproject có plugin/task khác nhau.
- Toolchain/bytecode target của các modules có thể khác.
- Generated sources/resources có task producer đúng.
- Included build có settings/repositories/version catalog riêng.
- Plugin compilation thuộc `buildSrc`/included build có thể lỗi trước app.
- IDE Tooling API sync khác CLI `build`.
- CI tasks publish/integrationTest không tự thuộc root `build`.
- Test filters và test report aggregation có thể thay behavior.

Đừng coi `./gradlew help` PASS hoặc `:cli:test` PASS là bằng chứng toàn monorepo đã được migrate. Cần liệt kê **release-critical task graph** và owner cho từng phần.

### 23.1. Version catalog không giữ Wrapper version

`gradle/libs.versions.toml` cung cấp dependency/plugin aliases và requested versions; Gradle distribution version được pin trong Wrapper properties. Resolved dependency graph có thể khác requested versions do conflict resolution; dùng dependency insight/locking nếu cần kiểm.

## 24. Một CI workflow cho PR migration

Ví dụ `.github/workflows/gradle-check.yml`:

~~~yaml
name: Gradle migration check

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Install Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Prepare Gradle
        uses: gradle/actions/setup-gradle@v4
        with:
          cache-read-only: true

      - name: Show Gradle version and JVM
        run: ./gradlew --version

      - name: Find deprecations
        run: ./gradlew help --warning-mode=all --stacktrace

      - name: Test from clean output
        run: ./gradlew clean check --warning-mode=all --stacktrace

      - name: Smoke run the demo
        run: ./gradlew run --args=Ada --quiet
~~~

Mẫu này dành cho **Java Application demo**, không tự áp vào repo không có `run` task. CI production nên pin actions theo reviewed immutable commit SHAs thay cho version tags như `@v4`; không bịa SHA trong ví dụ. PR runner không nên có publish/deploy/signing secrets.

### 24.1. Không nhầm environment matrix với Gradle version matrix

Một job đặt environment `GRADLE_VERSION=9.9.0` **không tự khiến** `./gradlew` dùng version ấy; Wrapper distribution được chọn bởi Wrapper files. Nếu muốn kiểm một plugin với nhiều Gradle distributions, dùng TestKit `withGradleVersion` hoặc các jobs/workspaces được cấu hình thực sự khác versions.

## 25. Artifact verification sau khi build đã xanh

Khi target Gradle/build plugins thay đổi, có thể có behavior khác dù `BUILD SUCCESSFUL`:

1. Test XML/HTML reports có đủ số tests và đúng filters?
2. Generated sources/resource outputs có đủ và không stale?
3. Jar metadata, manifest, archive entry ordering/permissions có đổi?
4. Dependency graph/resolved versions có lệch yêu cầu?
5. Compiler target Java API/bytecode có phù hợp consumers?
6. Publication POM/Gradle Module Metadata/variants đúng?
7. IDE sync và CI different OS/JDK có xanh?
8. Configuration Cache/Build Cache có hidden input/out-of-date problems?
9. Integration tests có được gọi đúng task graph?
10. Artifact size/digests đổi có được giải thích và review?

**Không mặc định JAR SHA khác là bug**: archive metadata/Gradle version/tool implementation có thể đổi hợp lệ. Nhưng với sản phẩm cần byte-for-byte reproducibility, cần điều tra và chuẩn hóa archive output trước khi release.

## 26. Known issues, rollout và rollback

Khi chọn target:
- Đọc Known Issues và những bug reports liên quan.
- Kiểm vendor compatibility của AGP/KGP/IDE.
- Đọc security/maintenance policy; dùng stable release được duyệt.
- Chuẩn bị branch nâng cấp, test trên CI/staging trước merge.
- Ghi baseline commit, versions, changed files và test evidence.
- Giữ đường rollback coherent gồm Wrapper, plugin versions và build-logic changes.
- Không tắt dependency verification/tests để khiến target xanh.
- Nếu blocker do third-party plugin, tạo minimal reproduction và issue vendor, hoặc ở lại compatible Gradle version theo policy.

**Điểm mấu chốt:** một patch version mới không tự có “zero risk”. Known issues, runtime/CI compatibility và migration cost đều ảnh hưởng quyết định thời điểm.

## 27. Bảng lỗi thường gặp khi đọc thiếu tài liệu

| Triệu chứng | Nguyên nhân có thể | Tra đâu? |
| --- | --- | --- |
| Gradle 9 không chạy với Java 11 | Daemon runtime cũ | Java Runtime Matrix |
| Java 21 toolchain được nhưng Daemon lỗi trên Gradle 8.4 | Hai cột support khác | Matrix Java |
| `No matching toolchains found` | Thiếu JDK/toolchain resolver | Toolchains docs/CI setup |
| `Unsupported class file major version` | Bytecode vs JVM/plugin mismatch | Matrix + plugin compatibility |
| Kotlin DSL compilation fail | Gradle/Kotlin/plugin API thay đổi | Matrix Kotlin + upgrade guide |
| Groovy script fail | Embedded Groovy/DSL behavior | Matrix Groovy + guide |
| AGP 8.x lỗi trên Gradle 9.6+ | Removed internal Problems API | 9.x guide + Android docs |
| `Plugin was not found` | Plugin repo/version/marker config | Plugin Management docs |
| `NoClassDefFoundError` Gradle internal class | Plugin dùng internals bị loại | Upgrading Guide |
| Test reports có ít tests hơn | Test filter/framework semantics | Release Notes + test reports |
| Wrapper đổi mirror host | `distributionUrl` regenerate | 9.9 Release Notes + Wrapper diff |
| Wrapper SHA mismatch | ZIP version khác checksum | Wrapper docs/official checksums |
| Problems API parser không nhận ID | 9.9 IDs/groups đổi | 9.x guide + Tooling API docs |
| CI JVM khác local | JAVA_HOME/Daemon criteria | Matrix/`--version` |
| Build green nhưng artifact target Java sai | `options.release`/toolchain drift | javac/JavaCompile options |
| Warning liên tục | Plugin vẫn dùng deprecated APIs | `--warning-mode=all` + vendor |
| IDE sync fail CLI build pass | Tooling API/IDE compatibility | IDE release notes |
| `gradle --version` khác Wrapper | Dùng global installation | `./gradlew --version` |
| Cache miss sau upgrade | Gradle/task fingerprints thay đổi | `--info`/cache reports |

### 27.1. Quy trình chẩn đoán có thứ tự

1. Xác định **source/target Gradle versions** và Wrapper đang chạy.
2. Xác định Daemon JVM thực, không chỉ shell Java.
3. Phân loại lỗi: runtime, toolchain, plugin, DSL, test, dependency, IDE hay publish.
4. Tra **đúng trục** trong Compatibility Matrix và vendor matrix.
5. Tra Release Notes/Upgrading Guide theo source→target.
6. Chạy lệnh nhỏ để reproduce với `--warning-mode=all --stacktrace`.
7. Sửa một nhóm change, chạy regression test liên quan.
8. Ghi evidence và rollback decision.

## 28. Hai mươi hiểu lầm nên loại bỏ

**1.** Compatibility Matrix và Upgrading Guide là một. **Sai:** Matrix là support constraints, guide là migration actions.

**2.** Chỉ đọc Release Notes bản đích là đủ. **Sai:** thiếu thay đổi tích lũy.

**3.** Java 21 toolchain ở Gradle 8.4 nghĩa Gradle 8.4 chạy trên Java 21. **Sai:** Daemon runtime support là 8.5.

**4.** Gradle 9.x yêu cầu mọi application phát Java 17 bytecode. **Sai:** Daemon min 17; target riêng.

**5.** `java -version` chắc chắn là Daemon JVM. **Sai:** có `org.gradle.java.home`, Daemon criteria, IDE.

**6.** Embedded Kotlin version phải bằng KGP version. **Sai:** hai dependency axes.

**7.** Android plugin được Gradle test có nghĩa mọi AGP/JDK/Studio đều được support. **Sai:** xem vendor matrix.

**8.** `/current` là link bất biến. **Sai:** pin docs version trong PR.

**9.** Build xanh nên bỏ qua deprecation warnings. **Sai:** có thể thành hard errors.

**10.** Source 8.7→9.9 chỉ cần guide 9.9. **Sai:** cần 8.x + major 9 + 9.x.

**11.** Wrapper URL mới bảo đảm Wrapper JAR/scripts đồng bộ. **Sai:** review tất cả files.

**12.** Gradle 9.9 giữ nguyên custom distribution host. **Sai:** URL có thể regenerate.

**13.** Java `javac` PASS chứng minh Gradle migration PASS. **Sai:** Gradle/plugin/test khác.

**14.** Deprecated APIs đều nằm trong repo. **Sai:** plugin third-party có thể dùng.

**15.** `--refresh-dependencies` giải quyết plugin API removed. **Sai:** refresh không thay tương thích.

**16.** Build Scan bắt buộc. **Sai:** có console `--warning-mode=all`; xem security policy.

**17.** Test task PASS tức test coverage không đổi. **Sai:** kiểm test counts/filters.

**18.** Nâng Gradle và toàn bộ deps một lúc giúp chẩn đoán. **Sai:** khó isolate root cause.

**19.** Version catalog quản lý Wrapper distribution. **Sai:** Wrapper properties.

**20.** Cache miss sau upgrade luôn là bug. **Sai:** keys/implementation/history có thể đổi hợp lệ.

## 29. Bài tập tự kiểm tra có đáp án

**Câu 1.** Muốn biết Java 21 chạy Gradle 8.4 được không, đọc cột nào?  
**Đáp án:** Java Runtime, Support for running Gradle.

**Câu 2.** Java 21 toolchain được hỗ trợ lần đầu từ Gradle nào?  
**Đáp án:** 8.4.

**Câu 3.** Java 21 chạy Gradle được hỗ trợ lần đầu từ Gradle nào?  
**Đáp án:** 8.5.

**Câu 4.** JVM chạy Gradle 9.9 phải thuộc dải nào theo matrix?  
**Đáp án:** Java 17–27 tại mốc bài.

**Câu 5.** Java 17 toolchain có ép Gradle Daemon chạy Java 17 không?  
**Đáp án:** không; Daemon JVM được chọn riêng.

**Câu 6.** `options.release.set(17)` thay đổi gì?  
**Đáp án:** target Java language/API/bytecode cho `javac`.

**Câu 7.** Source 8.7 → target 9.9 nên đọc guide nào?  
**Đáp án:** guide trong 8.x áp dụng, major 9.0 và trong 9.x áp dụng.

**Câu 8.** Release Notes thay major Upgrading Guide được không?  
**Đáp án:** không.

**Câu 9.** Deprecation warning có thể do plugin bên ngoài không?  
**Đáp án:** có, cần stacktrace/plugin owner.

**Câu 10.** Lệnh nào hiển thị warnings chi tiết?  
**Đáp án:** `./gradlew help --warning-mode=all`.

**Câu 11.** Lệnh nào có thể fail vì deprecated usage warnings?  
**Đáp án:** `--warning-mode=fail`.

**Câu 12.** Gradle 9.9 Release Notes có thay đổi gì với `--tests`?  
**Đáp án:** filter đúng hơn với một số JUnit Platform non-method tests.

**Câu 13.** Incremental Kotlin DSL compilation nhanh hơn tới 65% có áp mọi build?  
**Đáp án:** không, chỉ benchmark cụ thể khi scripts recompilation.

**Câu 14.** Gradle 9.9 Wrapper giữ custom distribution host không?  
**Đáp án:** không bảo đảm, `distributionUrl` được generate lại.

**Câu 15.** Vì sao chạy Wrapper task hai lượt?  
**Đáp án:** update distribution configuration rồi đồng bộ scripts/JAR với Gradle mới.

**Câu 16.** Gradle 9.6+ AGP 8.x có thể gặp loại lỗi nào?  
**Đáp án:** removed internal Problems API classes.

**Câu 17.** Plugin vendor compatibility có được suy từ Gradle Matrix duy nhất không?  
**Đáp án:** không; phải đọc vendor docs và test.

**Câu 18.** `org.gradle.internal.*` có public stable API không?  
**Đáp án:** không; rủi ro lớn khi nâng.

**Câu 19.** Java demo `UpgradeHello` in gì với Ada?  
**Đáp án:** `Gradle upgrade: Hello, Ada!`.

**Câu 20.** Lệnh `javac/java` thuần kiểm được Gradle Wrapper không?  
**Đáp án:** không.

**Câu 21.** `--tests` còn chạy đúng số test cũ sau upgrade không chắc, phải xem gì?  
**Đáp án:** XML/HTML reports và selectors.

**Câu 22.** `GRADLE_VERSION=9.9.0` environment variable tự đổi Wrapper không?  
**Đáp án:** không.

**Câu 23.** API TestKit nào để chọn Gradle distribution?  
**Đáp án:** `GradleRunner.withGradleVersion("9.9.0")`.

**Câu 24.** Build green nhưng Java bytecode cao hơn runtime consumer, upgrade đạt chưa?  
**Đáp án:** chưa; phải sửa target/test runtime compatibility.

**Câu 25.** Khi upgrade fail, có nên đổi Gradle/JDK/plugins/deps cùng lúc để thử?  
**Đáp án:** không; isolate từng nhóm và giữ evidence.

**Câu 26.** Tại sao lưu versioned documentation links?  
**Đáp án:** giữ bằng chứng theo đúng target ngay cả khi `current` đổi.

**Câu 27.** Một alpha AGP được Matrix nhắc tới có tự được duyệt production không?  
**Đáp án:** không; xem stable/vendor/organization policy.

**Câu 28.** JavaCompile không tìm JDK17 toolchain, sửa Daemon runtime là đủ không?  
**Đáp án:** không; phải cài/provision đúng JDK toolchain.

**Câu 29.** Vì sao nên so artifact reports sau upgrade?  
**Đáp án:** build PASS chưa chứng minh test counts/metadata/bytecode giữ đúng.

**Câu 30.** Cache miss sau nâng có tự chứng minh build hỏng không?  
**Đáp án:** không, cần kiểm task inputs/implementation/history.

## 30. Checklist thực hiện nâng Gradle

- [ ] Ghi source/target Gradle version và ngày tài liệu.
- [ ] Mở đúng Compatibility Matrix gắn target version.
- [ ] Phân biệt Daemon JVM, compiler toolchain, bytecode target.
- [ ] Xác nhận CI/IDE/local Daemon JVM hợp lệ với target.
- [ ] Đã có đúng JDK toolchains trên runner.
- [ ] Đọc embedded Kotlin/Groovy, Android, target OS/architecture.
- [ ] Kiểm vendor compatibility của AGP/KGP/third-party plugins.
- [ ] Đọc Release Notes feature + behavior + known issues.
- [ ] Đọc Upgrading Guides tích lũy qua toàn nguồn→đích.
- [ ] Phân loại breaking changes và deprecations theo owner.
- [ ] Chạy `--warning-mode=all` trên các task graphs quan trọng.
- [ ] Không dùng Gradle internal APIs trong plugin sở hữu.
- [ ] Update JDK/plugin theo lộ trình trước hoặc cùng Wrapper khi cần.
- [ ] Chạy Wrapper task đúng cách và review URL/scripts/JAR/checksum.
- [ ] Verify `./gradlew --version` đúng Gradle target và JVM.
- [ ] Test compile/release target Java phù hợp consumer.
- [ ] Test JUnit selectors/number tests sau thay đổi.
- [ ] CI build/test/check/integration/plugin functional tests đạt.
- [ ] IDE sync/Tooling API tương thích.
- [ ] Dependency graph, POM/JAR outputs và artifact behavior được so.
- [ ] Configuration Cache/Build Cache không che lỗi correctness.
- [ ] Release CI không dùng unreviewed PR code có secrets.
- [ ] Migration table có actions/owners/evidence/rollback.
- [ ] Benchmark performance chỉ khi workloads/cache state tương đương.
- [ ] Đã ghi documentation/versioned links để review sau.

## 31. Tài liệu chính thức và cách tra cứu

- [Gradle 9.9 Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html): Java Runtime, Kotlin, Groovy, Android, Target Platforms.
- [Gradle 9.9 Release Notes](https://docs.gradle.org/9.9.0/release-notes.html): new features/behavior changes/known issues.
- [Upgrading to Gradle 9.0.0](https://docs.gradle.org/9.9.0/userguide/upgrading_major_version_9.html): thay đổi ở ranh giới 8→9.
- [Upgrading within Gradle 9.x](https://docs.gradle.org/9.9.0/userguide/upgrading_version_9.html): breaking changes/deprecations trong 9.x.
- [Upgrading within Gradle 8.x](https://docs.gradle.org/9.9.0/userguide/upgrading_version_8.html): khi source còn ở 8.x.
- [Gradle Wrapper](https://docs.gradle.org/9.9.0/userguide/gradle_wrapper.html): upgrade Wrapper/scripts/JAR/checksum.
- [Java Toolchains](https://docs.gradle.org/9.9.0/userguide/toolchains.html): JDK compiler/test khác Daemon.
- [Gradle Feature Lifecycle](https://docs.gradle.org/9.9.0/userguide/feature_lifecycle.html): incubating/stable/deprecated/removal.
- [Gradle CLI](https://docs.gradle.org/9.9.0/userguide/command_line_interface.html): warning modes, stacktrace, dependency reports.
- [Java & JVM Testing](https://docs.gradle.org/9.9.0/userguide/java_testing.html): `Test`, JUnit Platform, filtering.
- [Gradle TestKit](https://docs.gradle.org/9.9.0/userguide/test_kit.html): plugin compatibility tests trên nhiều distributions.
- [Gradle Configuration Cache](https://docs.gradle.org/9.9.0/userguide/configuration_cache.html): config-state API constraints.
- [Gradle Build Cache](https://docs.gradle.org/9.9.0/userguide/build_cache.html): cache results/invalidation.
- [Gradle Release Checksums](https://gradle.org/release-checksums/): SHA-256 từ nguồn chính thức.
- [Android Gradle Plugin release notes](https://developer.android.com/build/releases/gradle-plugin): AGP/Gradle/JDK matrix của vendor.
- [Kotlin Gradle Plugin docs](https://kotlinlang.org/docs/gradle-configure-project.html): KGP/Gradle compatibility.
- [Gradle Releases](https://gradle.org/releases/): xác nhận mốc release và target.

**Kết luận:** Compatibility Matrix cho biết tổ hợp Gradle/JVM/toolchain/Kotlin/Groovy/AGP/OS **có được hỗ trợ không**; Release Notes cho biết phiên bản mới **cải thiện và thay behavior gì**; Upgrading Guide cho biết **những gì phải sửa khi đi qua các phiên bản**. Hãy đọc tài liệu theo đường version nguồn→đích, kết hợp vendor matrix, sửa deprecations và nâng Wrapper có checksum. Một nâng cấp hoàn tất cần **tests, report counts, artifact/CI/IDE validation và rollback plan**, không chỉ một dòng `BUILD SUCCESSFUL`.