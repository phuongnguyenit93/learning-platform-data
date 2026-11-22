# Ghi đè phiên bản được quản lý và đánh giá tương thích trong Spring Boot

## 1. Mục tiêu và bài toán thực tế

Spring Boot cung cấp **Bill of Materials (BOM)** `spring-boot-dependencies` để quản lý phiên bản của nhiều thư viện, giúp các thành phần được sử dụng cùng nhau theo một tập phiên bản mà mỗi bản Spring Boot đã kiểm thử. Trong dự án thông thường, bạn khai báo dependency theo `groupId:artifactId` và để BOM cung cấp phiên bản.

Tuy nhiên, đôi khi bạn cần **ghi đè (override)** một phiên bản được BOM quản lý, chẳng hạn vì lỗ hổng bảo mật có bản vá, lỗi tương thích với hệ thống khác, hoặc cần một tính năng thư viện mới. Thao tác này thay đổi một phần của tập phiên bản mà Spring Boot đã kiểm thử, nên phải đi kèm **đánh giá tương thích và bằng chứng kiểm thử**.

Sau bài học, bạn có thể:

1. Phân biệt phiên bản **được BOM quản lý**, **được yêu cầu** trong cấu hình, và **thực tế được chọn** vào dependency graph.
2. Nhận diện kiểu quản lý dependency của dự án: Maven kế thừa `spring-boot-starter-parent`, Maven import BOM, Gradle dùng `io.spring.dependency-management`, hoặc Gradle native `platform()`.
3. Ghi đè đúng cách trong từng trường hợp, kiểm soát phạm vi và tránh ép toàn bộ thư viện liên quan lên phiên bản tùy tiện.
4. Dùng dependency tree, `dependencyInsight`, effective POM và kết quả build/test để xác minh phiên bản thực tế.
5. Đưa ra quyết định chấp nhận hay hoàn tác override dựa trên khả năng tương thích, an toàn, phạm vi ảnh hưởng và khả năng nâng cấp Spring Boot.

**Quy ước ví dụ:** các số phiên bản trong đoạn mã chỉ **minh họa cú pháp**, không là tuyên bố rằng phiên bản ấy là bản vá bảo mật hoặc tương thích với mọi Spring Boot release. Khi làm thật, dùng đúng phiên bản dự án đã được phê duyệt và kiểm tra tài liệu của chính phiên bản Spring Boot đó.

## 2. BOM quản lý cái gì, và không quản lý cái gì?

Một BOM Maven là POM có `<dependencyManagement>`, tập hợp tọa độ thư viện và phiên bản được đề xuất/quản lý. Spring Boot BOM quản lý nhiều thành phần như Spring Framework, Jackson, logging, HTTP client, JDBC driver và các bộ thư viện khác (danh sách thay đổi theo bản Spring Boot).

Ví dụ về *khai báo sử dụng* thư viện đã được quản lý:

~~~xml
<!-- pom.xml: Maven dùng Spring Boot Parent hoặc import BOM -->
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

~~~groovy
// build.gradle: đã cấu hình Spring Boot dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Hai khai báo trên không ghi số phiên bản của starter: việc quản lý phiên bản đã được cấu hình nơi khác. **BOM không tự thêm mọi thư viện** vào classpath. Một dependency chỉ xuất hiện nếu được khai báo trực tiếp hoặc kéo vào *transitively* từ dependency khác.

Phân biệt ba khái niệm:

| Khái niệm | Nghĩa | Bằng chứng |
| --- | --- | --- |
| **Managed version** | Phiên bản được BOM hoặc `dependencyManagement` chỉ định khi một module xuất hiện | BOM, effective POM, dependency management report |
| **Requested version** | Phiên bản/constraint được một dependency trực tiếp hoặc gián tiếp yêu cầu | `pom.xml`, `build.gradle[.kts]`, dependency tree |
| **Resolved/selected version** | Phiên bản cuối cùng được công cụ build chọn trong từng cấu hình/classpath | Maven `dependency:tree`; Gradle `dependencies`, `dependencyInsight` |

**BOM không phải lockfile** và không thay thế kiểm chứng dependency graph. Maven và Gradle có quy tắc giải xung đột khác nhau; cùng một BOM vẫn có thể cho kết quả khác nếu dự án khai báo những ràng buộc khác nhau.

**Cấu hình build plugin cũng là vấn đề riêng:** BOM chủ yếu quản lý **library dependencies**. Đừng cho rằng thêm một override vào dependency BOM sẽ tự nâng phiên bản Maven Compiler Plugin, Gradle plugin hoặc chính Spring Boot plugin.

## 3. Khi nào cần ghi đè, và lúc nào nên tránh?

Lý do thường có thể chấp nhận được nếu có chứng cứ:

- Có advisory/CVE ảnh hưởng trực tiếp tới phiên bản **được dự án sử dụng**, bản vá đã được upstream phát hành, nhưng Spring Boot release mà dự án đang dùng chưa cập nhật.
- Một lỗi đã được nhà phát triển thư viện xác nhận và bản vá tối thiểu sửa được lỗi, có issue/release note tương ứng.
- Phải tương thích với giao thức, server, driver hoặc API của hệ thống bên ngoài, và bộ phiên bản mới đã được kiểm chứng.
- Một tính năng cần thiết có trong phiên bản mới; nhóm chấp nhận chi phí kiểm thử hồi quy và vận hành.

Các câu hỏi phải trả lời **trước khi sửa**:

1. Vì sao không nâng lên **Spring Boot patch/minor release** chứa dependency fix? Nâng Spring Boot theo đường hỗ trợ chính thức thường duy trì tốt hơn sự phối hợp giữa thư viện.
2. Dependency đó đang được **sử dụng thực tế** hay chỉ có mặt trong báo cáo? Nó ở `compileClasspath`, `runtimeClasspath`, test classpath hay build plugin classpath?
3. Override một artifact có an toàn, hay dependency thuộc **cả họ phải đi cùng nhau** (ví dụ Jackson modules, Netty, Spring Framework, Spring Security, Spring Data)?
4. Phiên bản mới có thay đổi **Java tối thiểu**, API/ABI, package, cấu hình, transitive dependencies, yêu cầu server/database hay license?
5. Có kế hoạch rollback và thời điểm xóa override khi BOM chính thức được nâng không?

Tránh dùng override chỉ để “làm hết cảnh báo dependency”, để lấy bản mới nhất không có nhu cầu, hoặc để che lỗi phiên bản cốt lõi mà không tìm nguyên nhân. **Đừng đánh đồng “build thành công” với “runtime tương thích”.**

## 4. Xác lập baseline trước khi chỉnh phiên bản

Trước khi sửa cấu hình, lưu lại: phiên bản Spring Boot, loại build tool, phiên bản Wrapper, tọa độ `group:artifact` bị ảnh hưởng, **selected version trước thay đổi** và lý do cần đổi. Dùng đúng Wrapper của repository để kết quả có thể tái lập.

### 4.1 Maven

Trên Linux/macOS:

~~~bash
./mvnw --version
./mvnw dependency:tree -Dincludes=org.slf4j:slf4j-api
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd dependency:tree -Dincludes=org.slf4j:slf4j-api
.\mvnw.cmd help:effective-pom -Doutput=effective-pom.xml
~~~

`dependency:tree` cho biết dependency đến từ nhánh nào và phiên bản hiện được chọn; `effective-pom.xml` cho biết cấu hình đã hợp nhất từ parent, profile và dependency management. **File `effective-pom.xml` chỉ là đầu ra kiểm tra**, không thay thế `pom.xml` nguồn và không nên vô tình commit.

Nếu thư viện chưa có trong dependency tree, `dependencyManagement` có thể chỉ quản lý phiên bản **khi nào nó xuất hiện**, chứ chưa khiến nó xuất hiện. Trong Maven multi-module, hãy chạy ở module ứng dụng hoặc dùng `-pl` thích hợp, và xét profile thực sự dùng trong build.

### 4.2 Gradle

Trên Linux/macOS:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency org.slf4j:slf4j-api --configuration runtimeClasspath
~~~

`dependencyInsight` cho biết phiên bản được chọn, những đường phụ thuộc yêu cầu nó và **lý do chọn phiên bản** (ví dụ constraint/conflict resolution/forced). `runtimeClasspath` phù hợp để điều tra thư viện chạy thật; với lỗi biên dịch kiểm tra thêm `compileClasspath`, với lỗi test kiểm tra `testRuntimeClasspath`. Một dự án multi-module có thể cần tiền tố module, ví dụ `:app:dependencyInsight`.

**Đọc kết quả trước khi kết luận:** một phiên bản xuất hiện trong BOM chưa chắc có mặt trong classpath; một phiên bản được ghi trong file build chưa chắc là phiên bản cuối cùng được chọn bởi Gradle.

## 5. Maven: ghi đè khi kế thừa Spring Boot Starter Parent

Nếu `pom.xml` có `<parent>` là `org.springframework.boot:spring-boot-starter-parent`, Spring Boot cho phép chỉnh nhiều managed versions qua **property trong BOM**. Ví dụ, nếu release hiện tại có thuộc tính `slf4j.version`:

~~~xml
<!-- Đoạn thuộc tính nằm trong <project> của pom.xml -->
<properties>
    <slf4j.version>2.0.16</slf4j.version>
</properties>
~~~

Đây là đoạn cấu hình trong POM đã kế thừa Spring Boot Parent, **không phải POM độc lập**. Bạn phải kiểm tra danh mục *Dependency Version Properties* của Spring Boot release đang dùng để biết **đúng tên thuộc tính**. Không tự suy ra rằng mọi artifact đều có property cùng tên. Property có thể điều khiển **một nhóm module/BOM** chứ không chỉ một JAR, nên phạm vi tác động phải được kiểm tra lại bằng dependency tree.

Trong trường hợp chỉ muốn override phiên bản của một dependency được khai báo trực tiếp, Maven cũng chấp nhận `<version>` tường minh:

~~~xml
<dependency>
    <groupId>org.slf4j</groupId>
    <artifactId>slf4j-api</artifactId>
    <version>2.0.16</version>
</dependency>
~~~

**Khác nhau về phạm vi:** ghi version trực tiếp kiểm soát dependency đó tại khai báo trực tiếp; property BOM có thể ảnh hưởng tới nhiều dependency được quản lý. Nếu library chỉ xuất hiện transitively, thêm nó làm direct dependency chỉ để ép version có thể làm POM khó hiểu; cân nhắc dùng `dependencyManagement` nếu muốn quản lý phiên bản khi nó xuất hiện.

Khi dùng Maven Spring Boot Parent, ưu tiên **property được Spring Boot công bố** cho nhóm phụ thuộc cần đồng bộ. Nếu cần override không có property thích hợp, khai báo quản lý cụ thể tại POM hiện tại rồi kiểm tra effective POM và dependency tree.

## 6. Maven: ghi đè khi chỉ import BOM, không dùng Starter Parent

Một dự án có corporate parent riêng thường import `spring-boot-dependencies` như BOM. Trong trường hợp này, **đặt property `slf4j.version` ở project POM không tự thay đổi giá trị đã được xử lý bên trong BOM import**. Đây là khác biệt quan trọng so với cơ chế kế thừa Starter Parent.

Muốn override một module, thêm entry trong **`<dependencyManagement>` của chính project** trước entry import BOM. Ví dụ dưới đây minh họa cấu trúc (phiên bản Spring Boot và SLF4J chỉ là số mẫu):

~~~xml
<!-- Trích phần <dependencyManagement> của pom.xml -->
<dependencyManagement>
    <dependencies>
        <!-- Override được khai báo ở project, trước BOM import -->
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Dùng **chính phiên bản BOM đang áp dụng cho dự án**, không lấy `3.3.13` làm chuẩn cho mọi Spring Boot project. Entry trong dependency management **không tự kéo `slf4j-api` vào ứng dụng**; nếu ứng dụng thực sự cần dùng trực tiếp thư viện, vẫn khai báo dependency bình thường ở `<dependencies>`.

Với trường hợp phải override **cả release train**, thường cần import BOM tương ứng trước Spring Boot BOM, rồi xác minh từng artifact liên quan. Ví dụ Spring Data có BOM riêng; không tự chọn phiên bản độc lập cho từng Spring Data module. Các BOM import có quy tắc ưu tiên khi cùng quản lý artifact; đừng dựa vào cảm giác “BOM nào mới hơn sẽ thắng”. Cần đọc effective POM và tree của từng module cần kiểm soát.

### Quy tắc chọn version của Maven

- Với dependency được khai báo trực tiếp cùng `<version>`, version trực tiếp có hiệu lực cho dependency đó.
- `<dependencyManagement>` áp dụng managed version cho dependency thiếu version hoặc dependency transitively xuất hiện; giúp giảm xung đột từ các nhánh phụ thuộc.
- Nếu không có quản lý version nào can thiệp, Maven thường chọn **nearest definition** trong dependency tree; nếu hai nhánh cách gốc bằng nhau, declaration xuất hiện trước có thể được ưu tiên.
- **Cấu hình cuối cùng mới là căn cứ**, vì parent, profiles và các BOM nhập vào có thể thay đổi kết quả. Luôn dùng `dependency:tree` + `help:effective-pom` để xác nhận.

## 7. Gradle với `io.spring.dependency-management`: chỉnh property managed version

Nếu dự án Gradle đã áp dụng cả plugin `org.springframework.boot` và `io.spring.dependency-management`, Spring Boot plugin tự import BOM tương ứng. Cơ chế này hỗ trợ ghi đè qua **Gradle extra property** khi BOM Spring Boot cung cấp property.

Trong Groovy DSL `build.gradle`:

~~~groovy
// Đặt trong build.gradle đã áp dụng các plugin tương ứng
ext['slf4j.version'] = '2.0.16'
~~~

Trong Kotlin DSL `build.gradle.kts`:

~~~kotlin
// Đặt trong build.gradle.kts đã áp dụng các plugin tương ứng
extra["slf4j.version"] = "2.0.16"
~~~

Hai ví dụ trên là **hai cú pháp thay thế**. Việc đặt property cần diễn ra trước khi cơ chế dependency management quyết định phiên bản; hãy để gần phần cấu hình build chung và xác nhận kết quả sau khi reload Gradle.

Kiểm tra:

~~~bash
./gradlew dependencyInsight --dependency slf4j-api --configuration runtimeClasspath
./gradlew clean build
~~~

Nếu classpath đã tồn tại nhiều version SLF4J hoặc thư viện logging liên quan, kiểm tra cả nhóm chứ không chỉ `slf4j-api`. Kiểm tra runtime vì sự không tương thích giữa SLF4J API và provider/binding thường chỉ bộc lộ khi chạy ứng dụng.

**Cảnh báo:** cú pháp `ext['slf4j.version']`/ `extra["slf4j.version"]` là cơ chế của Spring dependency-management plugin; **không có tác dụng tương đương** khi chỉ dùng Gradle native `platform()`.

## 8. Gradle native BOM: phân biệt `platform`, constraints và `enforcedPlatform`

Gradle có thể import BOM qua `platform()` mà không dùng `io.spring.dependency-management`. Ví dụ **trích đoạn** cho `build.gradle` với plugin Spring Boot đã được áp dụng:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

`platform()` đưa phiên bản BOM vào dependency graph làm **constraints**. Nó là gợi ý/ràng buộc để Gradle giải xung đột theo quy tắc phiên bản; **không khẳng định mọi phiên bản BOM luôn được chọn** nếu dependency khác yêu cầu phiên bản cao hơn hoặc có ràng buộc mạnh hơn.

Khi cần quyết định riêng cho một artifact, Gradle native nên dùng **dependency constraint có lý do rõ ràng**, chẳng hạn:

~~~groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    constraints {
        implementation('org.slf4j:slf4j-api') {
            version {
                strictly '2.0.16'
            }
            because 'Compatibility decision verified for the application'
        }
    }
}
~~~

Đoạn trên yêu cầu một phiên bản cụ thể **nếu module đó được dùng trong cấu hình tương ứng**. Constraint **không tự thêm module vào classpath**. `strictly` có thể khiến resolution **fail** nếu có các yêu cầu chặt khác không tương thích; khi đó cần điều tra nguyên nhân, không tự dùng `force` để che xung đột. Nếu chỉ cần yêu cầu mức phiên bản tối thiểu, constraint thông thường hoặc `require` có thể phù hợp hơn, nhưng Gradle vẫn có thể chọn phiên bản cao hơn. **Phải đọc `dependencyInsight` để chứng minh version cuối.**

Khi đã dùng native BOM, **không giả định** extra property như `ext['slf4j.version']` thay được phiên bản trong POM của BOM. Gradle native xử lý metadata/constraints, không tái nội suy property của Maven BOM để override.

### `enforcedPlatform()` có gì khác?

- `platform()`: các version từ BOM là constraints có thể tham gia xung đột với version khác.
- `enforcedPlatform()`: áp đặt phiên bản của platform mạnh hơn và có thể ảnh hưởng **cả dependency graph của bên tiêu thụ**, nhất là thư viện sẽ được các project khác dùng lại.
- `resolutionStrategy.force` và `eachDependency { useVersion(...) }`: là lựa chọn mạnh ở cấp resolution, dễ làm mất ý nghĩa các constraints khai báo; thường chỉ dùng cuối cùng với lý do và kiểm thử đặc biệt.

Đừng chuyển cả Spring Boot BOM sang `enforcedPlatform` chỉ vì muốn override một thư viện; cách đó có thể khóa hàng loạt phiên bản không liên quan. Để giữ cơ chế quản lý rõ ràng, chọn một **phong cách dependency management chủ đạo** cho project thay vì trộn Spring plugin và native BOM tùy tiện.

## 9. Vì sao không thể chỉ “đổi một số version”?

### 9.1 Tương thích source, binary và runtime

Một thư viện có thể biên dịch tốt với API hiện tại nhưng gây `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassCastException` lúc chạy nếu API/ABI giữa các JAR không khớp. Java bytecode còn phải phù hợp JVM production: một thư viện build cho Java 21 không chạy được trên Java 17 nếu class file yêu cầu phiên bản mới hơn.

**Tương thích ngược không đồng nghĩa tương thích tuyệt đối:** semver hỗ trợ ước lượng, nhưng một minor/patch release vẫn có thể đổi behavior, cấu hình mặc định, module name hoặc dependency đi kèm.

### 9.2 Hệ sinh thái thư viện liên quan

| Nhóm | Rủi ro khi override một artifact đơn lẻ | Kiểm chứng cần thiết |
| --- | --- | --- |
| Spring Framework / Spring Security | Spring Boot auto-configuration có thể gọi API/behavior cụ thể; liên kết giữa các module phải đồng bộ | Version matrix, application context, security flows |
| Spring Data / Hibernate / JDBC | Dialect, entity mapping, transaction và query có thể thay đổi | Repository/service integration tests, migration, DB thật hoặc test container |
| Jackson | `jackson-databind`, `jackson-core`, `jackson-annotations` hoặc BOM liên quan có thể cần tương thích | JSON serialize/deserialize, custom modules, HTTP payload |
| Reactor / Netty / HTTP | API nonblocking, SSL/TLS, event loop, transport và dependency native có thể thay đổi | WebClient/WebFlux integration tests, networking, load test phù hợp |
| SLF4J / Logback | API logging và provider không khớp gây warning/lỗi runtime | Khởi động app, log output, MDC, cấu hình logging |
| Driver DB / Kafka / Redis | Tương thích giao thức với server đang triển khai | End-to-end integration test với phiên bản server thực tế |

Nếu release train có BOM riêng, **nâng tập module theo BOM tương thích** thường an toàn hơn việc chọn một phiên bản khác nhau cho từng module.

### 9.3 Bảo mật và vận hành

Một advisory bảo mật không tự động có nghĩa mọi ứng dụng dùng tọa độ đó đều khai thác được. Xác minh artifact thực sự có trong runtime classpath, phiên bản ảnh hưởng, đường gọi bị tác động và cấu hình giảm thiểu. Tuy vậy, nếu rủi ro nghiêm trọng, cần ưu tiên xử lý kịp thời bằng **Spring Boot patch cập nhật, BOM tương thích hoặc override tạm thời có test**.

Khi override, theo dõi thêm thay đổi giấy phép, source of artifact, signature/checksum và provenance nếu quy trình tổ chức yêu cầu. Báo cáo scanner chỉ là một tín hiệu; quyết định phải gắn với **dependency graph thực tế** của artifact.

## 10. Quy trình thay đổi có kiểm soát

Dùng chu trình sau cho **một đề xuất override**:

1. **Ghi baseline:** Boot version, JDK, Wrapper, BOM hiện tại, dependency tree và phiên bản được chọn. Nếu CVE, lưu advisory link và phạm vi ảnh hưởng.
2. **Chọn chiến lược:** ưu tiên cập nhật Spring Boot release hỗ trợ bản vá; nếu chưa phù hợp, chọn cách override tương ứng với Maven Parent, Maven BOM import, Gradle dependency-management plugin hoặc Gradle native platform.
3. **Chỉnh nhỏ nhất:** một property, một managed entry hoặc một constraint có lý do. Không tự đổi JDK, framework version và hàng loạt library cùng lúc.
4. **Resolve lại dependency:** lưu dependency tree/insight sau thay đổi; so sánh các artifact liên quan trong **runtime**, **compile** và **test** classpaths. Một dòng version đúng trong build file chưa đủ.
5. **Kiểm chứng build:** chạy compile, unit test, integration test, đóng gói bằng Wrapper ở local và CI. Chạy trên JDK và môi trường runtime được hỗ trợ.
6. **Kiểm chứng hành vi:** khởi động ứng dụng, thử các luồng có dùng dependency, kiểm tra log, serialization, HTTP, persistence, security hoặc messaging tùy phạm vi.
7. **Đánh giá release:** đọc changelog, compatibility notes, breaking changes và kết quả scanner/analyzer. Kiểm tra dependency mới có kéo thêm version khác không.
8. **Ghi quyết định:** lý do, phiên bản cũ/mới, kiểm thử đã chạy, kết quả, người/phạm vi chấp thuận và điều kiện xóa override.
9. **Đặt điều kiện rollback:** nếu xuất hiện runtime linkage error, regression hoặc incompatibility, quay lại BOM/phiên bản đã xác thực; không tự hạ version khi còn nguy cơ bảo mật chưa xử lý.
10. **Dọn override khi hết cần thiết:** khi Spring Boot BOM chính thức quản lý phiên bản thích hợp, xóa property/constraint/managed entry tạm thời và xác minh dependency graph một lần nữa.

Một quyết định dễ rà soát có thể được ghi ngay trong PR:

| Trường | Ví dụ cách ghi |
| --- | --- |
| Artifact | `org.slf4j:slf4j-api` |
| Bản trước/bản mới | Lấy từ báo cáo dependency tree trước và sau, không suy luận từ POM |
| Nguyên nhân | Advisory hoặc issue upstream cụ thể |
| Kiểu override | Property BOM / Maven dependencyManagement / Gradle constraint |
| Phạm vi kiểm chứng | Các module trực tiếp, transitives liên quan, runtime và test |
| Bằng chứng | Lệnh Wrapper đã chạy và kết quả CI, integration test |
| Thời hạn rà soát | Khi nâng Spring Boot hoặc upstream phát hành fix phù hợp |

## 11. Một tình huống mẫu: cần phiên bản thư viện mới hơn vì lỗi đã xác nhận

**Bối cảnh:** thư viện `org.slf4j:slf4j-api` được đưa vào thông qua các starter và BOM Spring Boot. Nhóm đã xác nhận một yêu cầu tương thích, chọn thử bản `2.0.16`. Các số phiên bản sau đây chỉ để mô phỏng thao tác; **không hàm ý bản này có sửa một CVE cụ thể**.

### Trước thay đổi

1. Chạy Maven `dependency:tree -Dincludes=org.slf4j:slf4j-api` hoặc Gradle `dependencyInsight --dependency slf4j-api --configuration runtimeClasspath`.
2. Ghi version được chọn thực tế và đường dẫn dependency đưa SLF4J vào ứng dụng.
3. Xác định style quản lý dependency, không suy đoán qua phần mở rộng của file build.

### Thực hiện một phương án tương ứng

- Maven kế thừa Boot Parent: thêm `<slf4j.version>2.0.16</slf4j.version>` vào `<properties>`, với điều kiện release BOM có property này.
- Maven import Boot BOM: thêm managed entry cho `org.slf4j:slf4j-api` tại POM dự án trước BOM import, hoặc quản lý release train đúng chuẩn khi cần đồng bộ cả nhóm.
- Gradle có `io.spring.dependency-management`: `ext['slf4j.version'] = '2.0.16'` (Groovy) hoặc `extra["slf4j.version"] = "2.0.16"` (Kotlin).
- Gradle native `platform()`: thêm constraint phù hợp và kiểm chứng `dependencyInsight`; không dùng extra property của Spring plugin.

### Sau thay đổi

Chạy lại **cùng câu lệnh** lấy dependency tree để so sánh. Kiểm tra không có module logging khác vô tình lệch lớn về phiên bản. Build và chạy thử Spring Boot, xác nhận logging thực sự hoạt động, theo dõi warning provider và thử đường nghiệp vụ chính. Nếu yêu cầu ban đầu không được giải quyết hoặc xuất hiện incompatibility, **rollback** và chọn cách xử lý khác.

**Kết quả mong muốn:** không chỉ thấy số `2.0.16` trong cấu hình, mà thấy phiên bản được chọn trong dependency graph đúng classpath, ứng dụng vượt qua kiểm thử liên quan và PR ghi được nguyên nhân cùng rủi ro còn lại.

## 12. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Maven đã đặt property nhưng version không đổi | Dự án chỉ import BOM, không inherit Spring Boot Parent; property không được nội suy vào BOM import | Chuyển sang managed entry trong `dependencyManagement` ở project và đọc effective POM |
| Gradle đặt `ext['...version']` nhưng version không đổi | Dự án chỉ dùng Gradle `platform()` | Dùng constraint hoặc cơ chế Gradle native; xác minh bằng `dependencyInsight` |
| Gradle hiển thị phiên bản cao hơn phiên bản BOM | Một dependency hoặc constraint khác có yêu cầu cao hơn; regular platform không ép version tuyệt đối | Đọc selection reason và dependency paths, cân nhắc rule/constraint thích hợp |
| Maven classpath không khớp version vừa thêm | Version khai báo ở sai nơi, profile/module khác, hoặc quản lý version khác chi phối | Chạy `help:effective-pom` và `dependency:tree` trong đúng module/profile |
| Build thành công nhưng runtime `NoSuchMethodError` | Không tương thích nhị phân giữa các JAR cùng hệ | Đối chiếu phiên bản module liên quan, rollback hoặc nâng cả BOM theo hỗ trợ upstream |
| JSON/logging/networking hoạt động khác trước | Behavior/default/API của thư viện thay đổi dù compile được | Chạy integration/regression tests trên chức năng bị ảnh hưởng |
| `No matching version` / resolution conflict | Constraint `strictly` xung đột requirement khác | Đọc `dependencyInsight`, sửa yêu cầu thực sự; không mặc định dùng `force` |
| Báo cáo scanner còn cảnh báo sau khi chỉnh file build | Artifact vẫn đang lấy version khác, scanner quét image khác hoặc dependency nằm trong classpath khác | So sánh tree, runtime JAR/container image và dữ liệu scan |
| “Vá xong” nhưng Spring Boot nâng bản sau thì build lỗi | Override cũ che phiên bản mới của BOM hoặc không còn tương thích | Gắn việc gỡ override vào checklist nâng Spring Boot và kiểm thử lại |

## 13. Bài thực hành và tiêu chí hoàn thành

Hãy thử trong **một branch thử nghiệm**, với một Spring Boot project có Wrapper. Không cần nâng library thật trong production để làm bài.

1. Chọn một artifact đã xuất hiện trong dependency graph và đang được BOM quản lý. Ghi phiên bản Boot, loại build tool và selected version.
2. Chọn **một** cách override đúng với kiểu project. Viết lý do rõ ràng và chọn một phiên bản có tồn tại trong repository, không chọn phiên bản ngẫu nhiên.
3. Chạy lại Maven `dependency:tree` hoặc Gradle `dependencyInsight`. Kiểm tra selected version thay đổi đúng như mong muốn và xác định các module liên quan.
4. Chạy `clean verify` với Maven hoặc `clean build` với Gradle. Chạy ứng dụng và ít nhất một integration test phù hợp với thư viện vừa thay đổi.
5. Quan sát sự khác biệt giữa “version trong cấu hình”, “version được chọn” và “runtime hoạt động”. Ghi nhận cả bằng chứng thành công lẫn lỗi.
6. Hoàn tác override và chứng minh dependency graph quay về baseline ban đầu.

Bạn hoàn thành bài khi trả lời được: **Vì sao phải override? Bản nào thực sự được chọn? Bao nhiêu artifact bị ảnh hưởng? Đã kiểm chứng tương thích ra sao? Khi nào có thể bỏ override?**

## Tài liệu chính thức

- [Spring Boot – Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot – Maven plugin: Using the Plugin / Dependency Management](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot – Dependency Versions Properties](https://docs.spring.io/spring-boot/appendix/dependency-versions/properties.html)
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven – POM Reference](https://maven.apache.org/pom.html)
- [Gradle – Platforms and Maven BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle – Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
