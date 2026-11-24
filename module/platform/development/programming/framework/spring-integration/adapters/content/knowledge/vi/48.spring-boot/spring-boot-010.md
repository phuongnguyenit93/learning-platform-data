# Kiểm tra dependency version tương thích trong Spring Boot và Spring Integration Adapters

## 1. Mục tiêu: vì sao dependency đúng tên vẫn có thể chạy sai?

Trong một ứng dụng **Spring Boot** dùng **Spring Integration Adapters**, chúng ta thường ghép nhiều thành phần: Spring Framework, Spring Integration Core/Java DSL, adapter File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC, client thư viện của từng giao thức, Spring Security, hệ thống message, database và công cụ kiểm thử. Các thành phần đều có **phiên bản (version)** và **hợp đồng tương thích**. Chỉ cần một thư viện bị nâng/hạ lệch nhóm, ứng dụng có thể:

- Không biên dịch: class, method hoặc overload đã đổi khi nâng major.
- Khởi động lỗi: `NoClassDefFoundError`, `NoSuchMethodError`, `BeanCreationException` hoặc lỗi auto-configuration.
- Khởi động được nhưng chạy sai: header mapper không phù hợp, message converter đổi behavior, producer/consumer không nhận schema hoặc broker/client không tương thích.
- Chỉ lỗi ở production: JDK khác CI, transitive dependency ở runtime khác compile-time, client thực làm TLS/SSH negotiation thất bại.
- Bị lỗ hổng bảo mật vì cố giữ thư viện cũ không còn được bảo trì, hoặc vì override version mà không kiểm thử toàn bộ graph.
- Không còn tái lập bản build vì dùng dynamic version hoặc thiếu cơ chế quản lý artifact repository.

**Kiểm tra dependency version tương thích** không chỉ là nhìn một dòng `<version>` trong `pom.xml` hay `build.gradle.kts`; đó là việc kiểm chứng **toàn bộ dependency graph, BOM, phiên bản công cụ, API/ABI, cấu hình runtime, protocol và phạm vi kiểm thử**.

Bài thuộc chương **Spring Boot** trong module **SPRING_INTEGRATION_ADAPTERS**. Nội dung phục vụ việc kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel, đặc biệt ở file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Sau bài học, bạn có thể:

1. Xác định các **trục tương thích** bắt buộc khi chọn Spring Boot và Spring Integration.
2. Sử dụng **Spring Boot BOM** (Bill of Materials) và, khi cần, **Spring Cloud release train** thay vì đặt phiên bản tùy ý.
3. Đọc dependency tree/effective POM hoặc dependencyInsight để phát hiện direct/transitive override và xung đột.
4. Thiết kế ma trận kiểm thử compile–startup–flow–protocol–security cho từng adapter.
5. Nâng cấp dependency theo quy trình có bằng chứng, rollback và kiểm tra regression.

> **Nguyên tắc về phiên bản:** Ví dụ trong bài có thể sử dụng một bản phát hành minh họa như **Spring Boot 3.5.0** để giải thích cấu trúc file build; đó **không phải khẳng định là phiên bản mới nhất hay được khuyến nghị cho mọi dự án ở thời điểm đọc**. Phải kiểm tra support matrix, release notes và danh sách phiên bản thực tế đang được hỗ trợ trước khi chọn version production. Bài không suy diễn một cặp Spring Boot/Spring Integration “mới nhất” nếu chưa có xác nhận từ nguồn chính thức.

## 2. Các trục tương thích phải kiểm tra cùng nhau

Một hệ thống adapter có nhiều lớp ràng buộc:

~~~mermaid
flowchart TD
    JDK["JDK / bytecode target"] --> BOOT["Spring Boot release line"]
    BOOT --> FW["Spring Framework"]
    BOOT --> SI["Spring Integration BOM/modules"]
    BOOT --> DEP["Boot-managed dependencies"]
    CLOUD["Spring Cloud release train (nếu dùng)"] --> STREAM["Spring Cloud Stream/binders"]
    STREAM --> SI
    SI --> AD["Adapters: File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC"]
    AD --> CLIENT["Protocol clients / serializers / drivers"]
    CLIENT --> INFRA["SFTP server / HTTP API / broker / DB"]
    TEST["JUnit/Mockito/Spring Test/Testcontainers"] --> BOOT
    TEST --> AD
    SEC["Security advisories + vendor support"] --> BOOT
    SEC --> CLIENT
~~~

| Trục | Kiểm tra gì? | Ví dụ rủi ro |
|---|---|---|
| **Java/JDK** | Minimum Java, target bytecode, runtime JDK của build/CI/production | Build bằng JDK mới nhưng server chạy JDK cũ → `UnsupportedClassVersionError` |
| **Spring Boot** | Release line đang dùng, support status, BOM/plugin tương ứng | Parent BOM cũ bị trộn với starter mới |
| **Spring Framework** | Major/minor mà Boot line hỗ trợ | Override riêng `spring-core` hoặc `spring-messaging` gây lỗi method |
| **Spring Integration** | Core, DSL và toàn bộ adapter modules có cùng release line phù hợp Boot | `spring-integration-core` và `spring-integration-sftp` không đồng bộ |
| **Spring Cloud** (tùy chọn) | Release train tương thích Boot; binder + Stream cùng hệ | Đưa binder Kafka từ train khác vào app |
| **HTTP/SFTP/JMS/AMQP/Kafka clients** | API, serialization, authentication/TLS, broker/server compatibility | Client Kafka hoặc SSH thiếu class/transitive cần thiết |
| **Database driver/ORM** | JDK, DB server, JDBC API, transaction manager | Driver không hỗ trợ auth protocol hoặc timezone |
| **Test/runtime** | Test libs cùng dòng với framework; hạ tầng test đủ gần runtime | Unit test pass, deployed JDK/broker fail |
| **Security/operations** | CVE, version bị EOL, allowlist artifact, chính sách cập nhật | “Build xanh” nhưng dependency bị đánh dấu critical |

**Một version duy nhất không quyết định hết.** Ví dụ Java có thể hỗ trợ bản Spring Boot, nhưng client Kafka vẫn không tương thích với cluster/broker đã triển khai; hoặc client HTTP hoạt động nhưng API của Spring Integration outbound gateway đã đổi giữa hai major.

## 3. “Compatible” có ít nhất năm mức

Không nên kết luận “tương thích” chỉ vì Maven resolve dependency thành công.

| Mức | Bằng chứng cần có | Không tự chứng minh |
|---|---|---|
| **Dependency resolution** | Maven/Gradle giải được version và artifact | API tồn tại, không có lỗ hổng |
| **Compile compatibility** | Build source/test compile được | Startup configuration hợp lệ |
| **Runtime linkage/startup** | ApplicationContext lên được, không lỗi linkage | Adapter hoạt động với server/broker thật |
| **Behavior/protocol compatibility** | Contract tests, send/receive, ack, serializer, reconnect, transaction | Đủ performance, không có CVE |
| **Operational/security compatibility** | Hỗ trợ vendor, JDK/broker matrix, security scan, rollout/rollback | Không có mọi lỗi hiếm trong production |

Một bài kiểm tra version tốt phải xác định **đã xác minh ở mức nào**. `mvn dependency:tree` là bằng chứng resolution; `@SpringBootTest` là bằng chứng startup/configuration; integration test với SFTP/Kafka/DB mới có bằng chứng ở ranh giới protocol.

## 4. Nguồn xác nhận phiên bản: ưu tiên BOM và tài liệu chính thức

Khi chọn version, hãy tham khảo theo thứ tự:

1. **Spring Boot Reference / Dependency Versions:** cho biết dependency được Boot line quản lý, minimum Java và các thay đổi API/auto-configuration.
2. **Spring Integration Reference / Release Notes / Migration Guide:** xác định module, API, cấu hình endpoint, breaking changes của version Integration được sử dụng.
3. **Spring Framework reference:** kiểm tra các thay đổi nền tảng như Spring Messaging, JDBC, transaction, Web/HTTP và yêu cầu JDK.
4. **Spring Cloud compatibility / release train** nếu app dùng Spring Cloud Stream/binder; không áp dụng train tùy tiện dựa vào số semver trông gần.
5. **Tài liệu client và hệ thống đích:** Apache MINA SSHD/SFTP server, Kafka client/broker, RabbitMQ/AMQP, JMS provider, JDBC driver/DB, HTTP API/TLS.
6. **Security advisories, support policy, SBOM và kết quả CI:** phát hiện vulnerable/EOL releases và xác nhận binary thực tế.
7. **Dependency graph của chính dự án:** vì BOM chỉ là cơ chế chọn version; POM, build plugins hoặc transitive conflict có thể làm kết quả khác mong đợi.

Các địa chỉ để đối chiếu (URL tham khảo, kiểm tra release line đang dùng):

- Spring Boot: https://docs.spring.io/spring-boot/reference/
- Spring Boot managed versions: https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html
- Spring Integration: https://docs.spring.io/spring-integration/reference/
- Spring Integration changes: https://github.com/spring-projects/spring-integration/releases
- Spring Cloud: https://spring.io/projects/spring-cloud
- Maven dependency plugin: https://maven.apache.org/plugins/maven-dependency-plugin/
- Gradle dependency resolution: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html

**Không suy đoán** rằng “Spring Integration major N luôn đi với Spring Boot major M” cho mọi minor/patch và mọi Spring Cloud train. Lấy phiên bản được BOM resolve, đối chiếu compatibility/migration guide rồi kiểm tra bằng test.

### 4.1. Tại sao không chọn version bằng cách nhìn tên file JAR?

Tên JAR cho biết version của **một** artifact; không cho biết có transitive override hoặc một JAR khác được classloader chọn thay ở runtime. Chọn version theo policy trước, rồi kiểm toàn graph thay vì tải JAR thủ công bỏ vào `lib/`.

### 4.2. Có nên luôn dùng latest?

**Không tự động.** Latest có thể cải thiện security và tính năng, nhưng đồng thời mang thay đổi API, JDK baseline hoặc behavior. Chọn **bản được hỗ trợ**, đã khớp BOM và policy của hệ thống, áp dụng patch an ninh có kiểm thử, rồi nâng major có kế hoạch.

## 5. Spring Boot BOM quản lý dependency như thế nào?

**BOM** (Bill of Materials) cung cấp tập version đã được dự án phát hành phối hợp kiểm thử. Với Spring Boot, nguồn trung tâm thường là `spring-boot-dependencies`:

- Nếu dùng **Maven `spring-boot-starter-parent`**, dự án nhận dependency management và nhiều plugin defaults thông qua parent.
- Nếu không dùng parent, có thể **import Boot BOM** trong `<dependencyManagement>`.
- Với **Gradle**, plugin Spring Boot thường được dùng cùng `io.spring.dependency-management` hoặc Gradle native `platform(...)` để đưa BOM vào dependency resolution.
- Một dependency **không khai báo version** sẽ nhận version được quản lý nếu nó nằm trong phạm vi dependency management đã có.
- Một dependency có **version trực tiếp**, rule/constraint hoặc dependency management riêng có thể dẫn tới lựa chọn khác; phải kiểm resolved graph.
- BOM không tự thêm dependency vào ứng dụng. Nó **quản lý version của dependency đã được khai báo**, không thay thế `<dependencies>`.

~~~mermaid
flowchart TD
    POM["pom.xml / build.gradle.kts"] --> BOM["Boot BOM"]
    BOM --> CORE["spring-integration-core"]
    BOM --> FILE["spring-integration-file"]
    BOM --> SFTP["spring-integration-sftp"]
    BOM --> HTTP["spring-integration-http"]
    BOM --> KAFKA["spring-integration-kafka"]
    BOM --> JMS["spring-integration-jms"]
    BOM --> AMQP["spring-integration-amqp"]
    BOM --> JDBC["spring-integration-jdbc"]
    OVERRIDE["Explicit version / other BOM / constraint"] -. "có thể đổi resolved version" .-> CORE
    OVERRIDE -. "có thể đổi" .-> KAFKA
~~~

**BOM khác dependency lockfile.** BOM quy định cách chọn phiên bản trong graph; lockfile (nếu dùng) ghi lại resolved versions theo cơ chế build tool. Một build có BOM nhưng vẫn có thể thay đổi graph sau khi thêm dependency hoặc thay đổi version plugin/BOM.

## 6. Maven: mẫu quản lý version theo Spring Boot parent

Ví dụ sau dùng **Spring Boot 3.5.0** như một mốc **minh họa cấu trúc** (không coi đây là bản mới nhất). Hãy thay version bằng bản đã được nhóm dự án chọn qua nguồn chính thức, đồng thời kiểm JDK và module thực sự cần.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>integration-adapters-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-file</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-sftp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-http</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Điểm kiểm tra quan trọng:**

1. Không khai báo version riêng cho từng `spring-integration-*` khi đã có BOM phù hợp.
2. Không cần thêm tất cả adapter: **chỉ chọn các module cần cho ứng dụng**. Ví dụ dùng Kafka/AMQP/JMS thì bổ sung module tương ứng theo architecture.
3. `java.version` phải phù hợp JDK của Boot line, toolchain và runtime; không lấy “máy lập trình chạy được” làm bằng chứng server chạy được.
4. `spring-integration-test` cần được dùng với line Spring Integration phù hợp; tránh copy test jar version từ bài blog khác.
5. Mẫu không có datasource, credentials, broker config, build plugins ứng dụng tùy chỉnh và các bài test; đây là **skeleton học thuật**, không phải cam kết triển khai production ngay.

### 6.1. Nếu không dùng spring-boot-starter-parent

Một dự án có corporate parent riêng vẫn có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Đây chỉ là phần cấu hình BOM** đặt bên trong POM hợp lệ. Import BOM khác kế thừa parent ở quản lý plugin/build settings; cần cấu hình Maven compiler/test plugins cho corporate parent nếu chưa có.

### 6.2. Khi nào đặt explicit dependency version?

Chỉ khi có lý do cụ thể như bản vá bảo mật được phép, compatibility matrix đã được xác minh hoặc thư viện **không thuộc BOM**. Khi override, phải:

- Ghi ticket/lý do, version trước–sau và thời hạn xử lý.
- Kiểm API/binary compatibility trên **toàn bộ nhóm phụ thuộc liên quan**.
- Chạy dependency graph, compile, startup và adapter integration tests.
- Không dùng một override để né xung đột ngay trước release mà không xác minh transitive graph.
- Theo dõi BOM mới có chứa bản vá để quay về managed version khi thích hợp.

## 7. Gradle Kotlin DSL: không hardcode version từng adapter

Ví dụ áp dụng cho cùng mốc Boot 3.5.0 minh họa:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "example.learning"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-file")
    implementation("org.springframework.integration:spring-integration-sftp")
    implementation("org.springframework.integration:spring-integration-http")
    implementation("org.springframework.integration:spring-integration-jdbc")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.integration:spring-integration-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Khi kết hợp Spring Boot Gradle plugin với `io.spring.dependency-management`, plugin quản lý dependency theo Boot BOM. **Không đồng thời đưa thêm các BOM cạnh tranh hoặc override trùng dependency nếu không hiểu thứ tự/rule resolution.**

Đối với dự án chỉ dùng Gradle native BOM support, có thể dùng `platform(...)`/`enforcedPlatform(...)` và constraints phù hợp. Nhưng **`enforcedPlatform` có thể ép version lên các module phụ thuộc khác**; không dùng bừa để “sửa” version conflict. Chọn **một chiến lược quản lý phiên bản rõ ràng** rồi kiểm `runtimeClasspath`.

### 7.1. Gradle version catalog không phải compatibility guarantee

`libs.versions.toml` giúp tập trung tọa độ/version, nhưng việc pin các số version khác nhau trong catalog **không tự đảm bảo** Spring Boot, Spring Integration, Kafka client và Spring Cloud tương thích. BOM/constraints và kiểm thử vẫn cần thiết.

### 7.2. Plugin version và library version có phải một?

Không. Version Gradle/Maven **plugin** điều khiển build/lifecycle; version Java **library** dùng ở compile/runtime. Cần kiểm Gradle wrapper tương thích Spring Boot Gradle plugin, JDK mà plugin hỗ trợ, và project toolchain cho bytecode ứng dụng. Không suy luận “plugin build thành công” thì app runtime tương thích.

## 8. Lệnh kiểm tra version thực tế (không chỉ file build)

**Đây là các lệnh tham khảo để người học chạy trong repo khi được phép.** Bước soạn bài này **không thực thi** Gradle/Maven hoặc test dự án.

### 8.1. Maven

~~~powershell
# Liệt kê dependency đã resolve theo graph.
mvn dependency:tree

# Chỉ xem Spring Integration.
mvn dependency:tree -Dincludes=org.springframework.integration

# Chỉ xem Spring Framework, Integration, Kafka.
mvn dependency:tree -Dincludes=org.springframework:spring-core,org.springframework.integration:spring-integration-core,org.springframework.kafka:spring-kafka

# Xuất effective POM (có thể lớn).
mvn help:effective-pom -Doutput=effective-pom.xml

# In phiên bản Java/Maven đang thực thi.
mvn --version
~~~

Lệnh `help:effective-pom` có thể tạo `effective-pom.xml` trong thư mục đang chạy, nên dùng **chỉ khi được phép tạo artifact chẩn đoán**, rồi dọn theo quy trình. Một số mục tiêu/plugin có thể tải artifact từ Maven repository và cần network. Trong bài viết này, lệnh chỉ mang tính minh họa, **không được chạy trong lượt worker**.

Khi xem output, tìm **resolved version cuối cùng**, thứ tự nearest dependency/management và các đường transitive đưa vào cùng artifact. Không chỉ grep dòng `spring-integration-sftp` rồi bỏ qua `spring-integration-core`/Spring Framework.

### 8.2. Gradle (PowerShell/Windows)

~~~powershell
# Dependency tree theo configuration dùng lúc chạy.
.\gradlew.bat dependencies --configuration runtimeClasspath

# Vì sao spring-integration-core được chọn phiên bản này?
.\gradlew.bat dependencyInsight --dependency spring-integration-core --configuration runtimeClasspath

# Kiểm tra client Kafka, HTTP hoặc SSH/SFTP tương tự.
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency sshd-sftp --configuration runtimeClasspath

# Các phụ thuộc chỉ hiện diện trong test.
.\gradlew.bat dependencies --configuration testRuntimeClasspath

# Gradle/JDK hiện tại.
.\gradlew.bat --version
~~~

`dependencyInsight` trả lời **vì sao version được chọn**, bao gồm conflict resolution/constraints. Không mặc định một tên artifact SFTP nhất định luôn tồn tại; nếu project dùng client khác, query tên artifact thực tế trong dependency tree.

### 8.3. So sánh các classpath

| Classpath | Có thể khác gì? | Rủi ro |
|---|---|---|
| `compileClasspath` | API dùng khi biên dịch | Biên dịch pass nhưng runtime thiếu class |
| `runtimeClasspath` | Implementation/client thực sự khi chạy | `NoSuchMethodError`, duplicate libraries |
| `testRuntimeClasspath` | Test/JUnit/Mockito/server stubs | Test pass do test-only jar che lỗi production |
| Fat JAR / container runtime | Artifact được đóng gói và JDK chạy thật | Classpath khác build hoặc layer cached |
| Server-managed classpath | Application server/provider cung cấp thư viện | Xung đột `javax`/`jakarta` hoặc framework version |

**Kết luận kiểm tra version phải dựa vào classpath mà ứng dụng thực sử dụng.** Nếu compile/test đều pass nhưng deployment fail, cần kiểm nội dung artifact đóng gói, container image và runtime Java, không chỉ POM.

## 9. Gỡ lỗi version xung đột bằng dependency tree

Giả sử graph minh họa cho thấy:

~~~text
application
  +-- spring-boot-starter-integration
  |    +-- spring-integration-core: VERSION_MANAGED_BY_BOOT
  |
  +-- spring-integration-sftp: VERSION_MANAGED_BY_BOOT
  |    +-- spring-integration-core: same managed line
  |    +-- ssh client library: version managed/resolved
  |
  +-- custom-vendor-sdk: vendor-version
       +-- spring-messaging: different older version (conflict)
~~~

Các chuỗi `VERSION_MANAGED_BY_BOOT` và `vendor-version` là **ký hiệu minh họa**, không phải bản in thật. Cách xử lý:

1. Xác nhận version Spring Messaging **đang thực được resolve**, không chỉ version vendor khai báo.
2. Kiểm Spring Boot BOM có quản lý artifact đó không và có override trực tiếp nào không.
3. Kiểm vendor SDK **chính thức hỗ trợ** Spring Framework/Boot version dự án.
4. Dùng exclusion **chỉ khi biết thư viện loại bỏ không cần ở runtime** và vẫn đáp ứng contract; không xóa transitive bằng suy đoán.
5. Chạy compile/startup/protocol tests để xác minh giải pháp; **đừng tin dependency tree đẹp là đã đủ**.
6. Nếu vendor SDK đòi phiên bản bất tương thích thật, cân nhắc nâng SDK, đổi client, tách boundary/service hoặc kế hoạch migration; không ép BOM che lỗi.

### 9.1. Thế nào là một override nguy hiểm?

~~~xml
<!-- Anti-pattern: vô cớ ép core thấp hơn dòng Boot đang dùng. -->
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
    <version>AN_UNAPPROVED_VERSION</version>
</dependency>
~~~

Một module adapter phụ thuộc API của core line khác; đổi riêng core có thể dẫn đến lỗi linkage hoặc hành vi khác ngay khi dispatch message. **Không chọn version bằng thử số cho đến khi startup không lỗi**.

### 9.2. Maven và Gradle có thuật toán chọn version khác nhau

- Maven dùng dependency management và mediation theo cấu trúc graph/độ gần, với quy tắc cụ thể về khai báo trực tiếp và thứ tự khi xung đột.
- Gradle có conflict resolution, constraints, platform và các rule tùy dự án; mặc định có thể chọn version cao hơn trong một số xung đột.
- `dependencyManagement` và Gradle `platform` cùng nhằm ổn định version nhưng **không cùng cơ chế trong mọi trường hợp**.

Không dựa vào một mô tả đơn giản kiểu “luôn dùng version cao nhất” hoặc “BOM luôn thắng tất cả”. **Kiểm output đã resolve** rồi mới kết luận.

## 10. Giữ Spring Integration Core và các adapter cùng dòng phiên bản

Spring Integration không chỉ là một artifact. Một flow có thể dùng:

| Module | Phạm vi thường gặp |
|---|---|
| `spring-integration-core` | Message channels, endpoints, transformers, routers, filters, aggregators, Java DSL |
| `spring-integration-file` | File inbound/outbound, file filters, file reading/writing |
| `spring-integration-sftp` | SFTP inbound synchronization, outbound upload, session factories |
| `spring-integration-http` | HTTP inbound/outbound gateways và channel adapters |
| `spring-integration-jms` | JMS inbound/outbound adapters, gateways |
| `spring-integration-amqp` | AMQP/RabbitMQ inbound/outbound integration |
| `spring-integration-kafka` | Kafka adapters và message-driven flows |
| `spring-integration-jdbc` | JDBC inbound polling/outbound, metadata store |
| `spring-integration-test` | Hỗ trợ kiểm thử flow, mock endpoint, test utilities |

**Chỉ dùng module thật sự cần**, và để BOM điều phối version khi nó có quản lý artifact ấy. Không vì một API mới trong `spring-integration-sftp` mà tự nâng riêng SFTP lên major mới, để core/file/http ở major cũ.

### 10.1. Java DSL không nên có dependency từ bài viết quá cũ

Trong các dòng Spring Integration hiện đại, Java DSL được tích hợp vào hệ sinh thái module chính. Một hướng dẫn cũ có thể gợi ý một artifact DSL riêng từ thời điểm lịch sử khác. Trước khi thêm dependency lạ, kiểm tra class `IntegrationFlow`, builders và tài liệu phiên bản của Spring Integration đang dùng. **Không đưa hai thế hệ DSL/API vào cùng classpath** chỉ để source code từ blog cũ compile được.

### 10.2. Dependency management và API migration là hai việc riêng

BOM giúp chọn JAR tương thích với dòng Boot. Nó **không tự sửa source code** khi interface, factory method, annotation hoặc overload bị thay ở major mới. Nâng version cần đọc migration notes và sửa code, nhất là khi dùng gateway, poller, message converter, error handler hoặc class thuộc namespace thay đổi.

### 10.3. Kiểm thử “một flow nhỏ” sau khi nâng Integration

Một flow smoke test nên chứa:

~~~mermaid
flowchart LR
    INPUT["MessageChannel"] --> TRANS["Transformer"]
    TRANS --> OUTPUT["QueueChannel"]
    OUTPUT --> ASSERT["JUnit payload/header assertion"]
~~~

Chỉ cần tạo `IntegrationFlow`, gửi một message có `correlationId` và đọc reply/output là đã phát hiện nhiều lỗi wiring/runtime linkage. Nhưng đây **không thay thế** test adapter File/SFTP/HTTP/Kafka thực sự.

## 11. Java, Spring Framework và thay đổi javax → jakarta

Tương thích JDK có ít nhất ba phạm vi:

1. **Build JDK:** compiler, Gradle/Maven plugin đang chạy.
2. **Java toolchain/target:** bytecode và API source được ứng dụng biên dịch.
3. **Runtime JDK:** máy/container nơi Spring Boot JAR thực sự chạy.

Nếu dùng một JDK mới để biên dịch ra bytecode không được runtime hỗ trợ, ứng dụng có thể ném `UnsupportedClassVersionError`. Đặt `java.version` hoặc Gradle toolchain không thay cho việc xác nhận **container image và môi trường production** thực có JDK phù hợp.

Spring Boot 3 chuyển sang các namespace **Jakarta EE** trong nhiều API như servlet/JMS/JPA, còn các hệ thống rất cũ dùng `javax.*`. Khi nâng từ dòng Boot 2 hoặc các client cũ, cần kiểm:

| Thành phần | Dấu hiệu cần xem |
|---|---|
| JMS provider | Client và API có hỗ trợ `jakarta.jms.*` theo Boot/Spring line hiện tại? |
| Servlet/HTTP | Filter/servlet sử dụng `jakarta.servlet.*` thay cho API cũ khi cần? |
| JPA/validation | Các thư viện dùng namespace/major phù hợp? |
| Test infrastructure | Mock servlet/context và embedded server đồng bộ Spring Framework? |
| Vendor SDK | Có nhúng `javax.*` dependency hoặc framework JAR cũ không? |

**Không tự thay text `javax` thành `jakarta` rồi kết luận đã tương thích.** Nhà cung cấp JMS, servlet container, validation provider và các thư viện phụ thuộc cần có bản hỗ trợ đúng API, và cần kiểm runtime với provider thực.

### 11.1. Phân biệt JDK support và TLS/protocol support

Một JDK được Boot hỗ trợ vẫn có thể đổi thuật toán TLS/SSH mặc định, truststore, security provider hoặc ciphers. SFTP và HTTP integration cần test handshake với server thử nghiệm phù hợp, đặc biệt khi nâng JDK để xử lý lỗ hổng. Không “sửa” sự cố handshake bằng cách vô hiệu kiểm tra certificate/host key.

## 12. File adapter: đơn giản về giao thức nhưng vẫn có version coupling

File inbound/outbound chủ yếu dùng filesystem Java và Spring Integration File module. Những thay đổi phiên bản đáng chú ý có thể ở:

- Filter API: pattern, accept-once, persistent metadata store.
- File locking/rename/temporary file, encoding, line ending và thời gian sửa file.
- Default poller, scheduler, endpoint lifecycle.
- Header/metadata mapping, message payload type (File, String, bytes sau transformer).
- Triển khai `FileReadingMessageSource`/`FileWritingMessageHandler` hoặc Java DSL factory tương ứng.

**Không được khẳng định một pattern filter tự chống trùng**. Đổi phiên bản có thể thay default metadata/restart behavior; kiểm bằng test đọc cùng file nhiều lần và restart endpoint.

Ma trận test File sau upgrade:

~~~text
[ ] File *.csv vào flow với payload đúng
[ ] File không khớp pattern bị bỏ qua
[ ] File chưa hoàn tất không được xử lý sai policy
[ ] Header filename/path đúng như contract
[ ] Outbound file tạo đúng tên, nội dung và quyền ghi
[ ] Duplicate/restart được xử lý theo metadata store
[ ] Poller stop/start không tạo side effect ngoài ý muốn
~~~

## 13. SFTP adapter: Spring Integration và client SSH phải cùng thế hệ

SFTP có nhiều tầng: Integration adapter, session factory, SSH client library, thuật toán mã hóa và remote server. Các version mới của Spring Integration dùng hệ sinh thái **Apache MINA SSHD** trong những dòng hiện đại; nhiều hướng dẫn rất cũ dựa trên client/JSch và kiểu session khác.

**Rủi ro khi copy code cũ:**

- Import class session factory hoặc SSH client đã đổi package/API.
- Dùng hai bộ SSH client cùng lúc do dependency transitive cũ.
- Cấu hình host key/cipher khác hoặc thuật toán bị JDK/SSH server từ chối.
- Thay đổi metadata store/filter gây nhận lại file sau restart.
- Local temporary suffix, remote path và cách xử lý upload dở không khớp design.
- Test chỉ mock session nên không phát hiện TLS/SSH negotiation thực tế.

Cách kiểm:

1. Xem `spring-integration-sftp` đã resolve theo BOM nào.
2. Xem dependency graph của thư viện SSH/SFTP thực tế đang được dùng (không đoán artifact từ bài viết cũ).
3. Kiểm API `SessionFactory` và loại `Session<?>` theo version đã chọn.
4. Chạy SFTP server test với host key đã tin cậy, credential test.
5. Kiểm inbound sync, outbound upload, rename, retry, remote readback và restart.
6. Không vô hiệu host-key checking để “cho test xanh”.

### 13.1. Đừng chỉ so số version SSH client

Một client SSH version “cao hơn” vẫn có thể không thương lượng được thuật toán với SFTP server cũ; ngược lại, bật lại thuật toán không an toàn chỉ để tương thích có thể vi phạm chính sách bảo mật. Cần đối chiếu server policy, tài liệu vendor và chuẩn an ninh của tổ chức.

## 14. HTTP adapter/gateway: Spring Web và client API liên quan

HTTP inbound/outbound phụ thuộc Spring Web/HTTP client, converter, Jackson/serialization và đôi khi servlet/reactive stack. Tùy phiên bản Spring Integration, Java DSL và HTTP client có thể dùng `RestTemplate`, `RestClient` hoặc thành phần WebFlux khác nhau; không nên trộn overload code từ hai release line.

| Câu hỏi | Vì sao quan trọng? |
|---|---|
| Inbound gateway chạy trên Spring MVC hay reactive stack? | HTTP server, handler adapter và converter khác nhau |
| Outbound handler thực dùng client nào? | MockRestServiceServer, mock server và injection phải đúng instance |
| Content type/JSON converter được quản lý bởi BOM nào? | Serialization có thể thay behavior khi nâng major |
| Header mapper có forward các header đã quy định không? | Correlation, auth, tenant và content type có thể lệch |
| Lỗi 4xx/5xx/timeout map thế nào? | Retry/response status có thể khác |
| TLS/truststore và proxy có tương thích không? | Test in-memory không bắt được handshake network |

Một đổi version có thể compile được nhưng **test HTTP integration đổi status code, error body hoặc converter behavior**. Do đó cần mock HTTP server với request/response thực, kiểm URI/method/headers/JSON và negative tests.

### 14.1. Không nâng Jackson riêng mà bỏ qua BOM

Spring Boot thường quản lý thư viện serialization. Một vendor SDK kéo Jackson khác major có thể gây xung đột API hoặc khác cách serialize `Instant`, record, enum. Đừng chỉ override một artifact `jackson-databind` để vá lỗi mà bỏ qua các module Jackson liên quan. Khi yêu cầu major mới, đánh giá whole serialization stack và nâng Boot/SDK theo đường được hỗ trợ.

### 14.2. HTTP version compatibility không đồng nghĩa API contract compatibility

Dù HTTP client tương thích và gửi 200/201 thành công, API đối tác có thể thay schema, auth hoặc idempotency rules. Cần **consumer/provider contract test** riêng; Maven/Gradle không thể phát hiện thay đổi API của dịch vụ bên ngoài.

## 15. JMS adapter: provider, jakarta.jms và transaction semantics

JMS outbound/inbound không chỉ phụ thuộc `spring-integration-jms`. Còn cần JMS provider client và môi trường broker/connection factory phù hợp.

Ví dụ dependency **có chủ đích tách interface và provider**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jms</artifactId>
    </dependency>

    <!-- Chọn đúng JMS provider hoặc starter tương thích
         theo broker mà ứng dụng dùng; không đưa cả hai
         bộ client javax/jakarta vào classpath theo suy đoán. -->
</dependencies>
~~~

**Kiểm tra quan trọng:**

- Provider hỗ trợ API JMS/Jakarta phù hợp Spring Boot line.
- `ConnectionFactory` thực tế khởi tạo được và có credentials/TLS phù hợp.
- Message converter và JMS properties map đúng.
- Transaction manager/ack mode và redelivery đúng policy.
- Client/broker compatibility được vendor xác nhận.

**Thất bại điển hình:** class `javax.jms.ConnectionFactory` có trong vendor SDK cũ nhưng Spring Integration kỳ vọng `jakarta.jms.ConnectionFactory` của thế hệ mới. Đây không phải lỗi sửa được bằng cách “import thêm cả hai dependency”: cần chọn **provider version tương thích**.

## 16. AMQP/RabbitMQ: Spring AMQP, client và broker

Khi ứng dụng có RabbitMQ, thường có:

- `spring-integration-amqp` cho adapter/gateway.
- Spring AMQP, `RabbitTemplate`, listener infrastructure và RabbitMQ Java client.
- Broker có exchange, queue, binding, TLS và policy quorum/classic/retry.

Ví dụ dependency minh họa với Boot quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-amqp</artifactId>
</dependency>
~~~

Các mục cần kiểm tra sau nâng cấp:

| Phần | Assertion |
|---|---|
| Listener container | Consumer start/stop, concurrency và acknowledgment |
| Publisher | Exchange, routing key, confirms/returns |
| Converter | JSON/bytes/message headers đúng |
| Retry/recovery | Requeue, dead-letter policy, idempotency |
| Network | SSL/auth/reconnect, connection/channel pool |
| Broker server | Client hỗ trợ đúng protocol/features đang sử dụng |

**Mockito verify(`RabbitTemplate`) không chứng minh broker đã nhận hoặc route message.** Bổ sung RabbitMQ test container/broker thử nghiệm, kiểm exchange/binding, publisher confirm và consumer side effect.

## 17. Kafka: chú ý cả Spring Kafka và Kafka client/broker

Một flow Kafka của Spring Integration có thể kéo theo:

- `spring-integration-kafka`.
- `spring-kafka` và Kafka Java client.
- Serializer/deserializer, schema tooling nếu có.
- Consumer group, topic/partition, transactional/idempotent producer.
- Kafka broker phiên bản riêng ngoài JVM.

Ví dụ phần dependencies theo Boot BOM:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Nếu `spring-integration-kafka` đã kéo `spring-kafka` transitively, không nhất thiết phải khai báo lại trực tiếp trừ khi app dùng API Spring Kafka hoặc cần làm rõ dependency policy; **kiểm dependency tree trước khi quyết định**.

### 17.1. Kafka client/broker là quan hệ version riêng

Không giả định Kafka client phải có số version **giống y hệt** Kafka broker. Một số phiên bản client/broker có phạm vi backward/forward compatibility được công bố, nhưng hỗ trợ feature, message format, TLS/SASL, API versions và transaction semantics có thể khác. **Đối chiếu tài liệu Apache Kafka và vendor distribution** cho cấu hình thật.

### 17.2. Spring Cloud Stream binder không phải luôn bắt buộc

Spring Integration Kafka adapter trực tiếp **không đồng nghĩa** ứng dụng phải dùng Spring Cloud Stream. Nếu dùng Stream function/binder, cần chọn **Spring Cloud release train** tương thích Spring Boot line và binder version thích hợp, rồi kiểm dependencies của cả hai hệ.

### 17.3. Smoke test Kafka sau nâng dependency

~~~text
[ ] Producer có thể publish vào topic test
[ ] Record key, partition, headers và payload đúng
[ ] Consumer group test nhận và deserialize được
[ ] Offset/ack/commit phù hợp contract
[ ] Retry, DLT và idempotency chạy đúng
[ ] Broker unavailable/reconnect có phản hồi dự kiến
[ ] Không nhân đôi side effect khi consumer crash sau xử lý
~~~

## 18. JDBC/JPA/database: driver và transaction manager

Adapter JDBC cần Spring JDBC, DataSource, driver và database; dùng JPA thì còn có provider ORM/EntityManager tương thích.

Một cấu hình dependency **tối thiểu theo mục đích**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>

<!-- Thêm driver runtime phù hợp DB đang dùng,
     để BOM quản lý version nếu artifact nằm trong BOM. -->
~~~

Kiểm tra:

- Driver hỗ trợ database server, auth, timezone, data types và JDK runtime.
- Schema/SQL của poller và outbound handler vẫn hợp lệ.
- `DataSourceTransactionManager`/`JdbcTransactionManager`/JPA transaction setup phù hợp kiến trúc.
- Connection pool và health check hoạt động sau nâng version.
- Locking/isolation và row count có behavior theo contract.
- Nhiều poller instance không tạo duplicate side effect ngoài thiết kế.

**Một mock `JdbcTemplate.update(...)` trả 1 không chứng minh một transaction đã commit thật.** Chạy database test phù hợp (ví dụ container cùng hệ quản trị sản xuất) cho các quyết định liên quan locking, transaction, SQL dialect và constraint.

### 18.1. Database in-memory không luôn tương đương production

H2 có thể hữu ích cho test nhanh, nhưng SQL dialect, lock/isolation, timestamp, JSON type, sequence và constraint khác PostgreSQL/MySQL/Oracle. Với adapter dùng polling và transaction nhạy cảm, **database test gần production** có giá trị cao hơn một bài H2 pass.

## 19. Spring Cloud Stream và Spring Cloud BOM: chỉ thêm khi cần

**Spring Cloud Stream** giúp xây messaging bằng function bindings và binders. Nó có quan hệ dependency với Spring Cloud, Spring Boot, Spring Integration và các transport như Kafka/RabbitMQ. Nhưng module Spring Integration Adapters vẫn có thể dùng **Spring Integration trực tiếp** mà không cần thêm Cloud Stream.

Khi dự án **thực sự dùng Cloud Stream**, chọn:

1. Spring Boot release line đã được phê duyệt.
2. Spring Cloud release train **được công bố tương thích với Boot line ấy**.
3. Stream/binder thuộc train và mức version tương ứng.
4. Java/JDK, broker/client và schema tooling phù hợp.
5. Test binder đúng thế hệ: hiện đại dùng `InputDestination`/`OutputDestination`, tránh import test support `MessageCollector` legacy từ bài hướng dẫn cũ mà không xem version.

Mẫu import **Cloud BOM** vào dự án Maven đã dùng Boot parent:

~~~xml
<properties>
    <!-- Thay bằng release train đã xác minh tương thích Boot. -->
    <spring-cloud.version>APPROVED_CLOUD_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Mẫu là **skeleton**, chưa chạy được khi còn placeholder `APPROVED_CLOUD_TRAIN`. Bản sử dụng thực tế phải thay giá trị property bằng **một release train đã được xác minh tương thích** với Boot, và dùng property đó để import Cloud BOM. Đặt Cloud BOM cùng Boot BOM theo hướng dẫn chính thức cho release train được dùng.

**Không tắt compatibility verifier của Spring Cloud chỉ để startup pass.** Nếu verifier báo Boot/Cloud mismatch, đó là tín hiệu phải tra matrix; việc tắt kiểm tra không làm các thư viện tương thích về binary hoặc semantics.

### 19.1. Không gộp spring-integration-kafka và Stream Kafka binder một cách mù quáng

Nếu app dùng cả API Spring Integration Kafka trực tiếp và Cloud Stream binder, cần xác định:

- Thành phần nào quản lý `spring-kafka`/Kafka clients.
- Topic/key/header mapper nào được dùng.
- Retry/error semantics của binder khác hay giống flow trực tiếp.
- Test binder chỉ kiểm binding in-memory, không thay broker test.
- Có conflict về dependency management hoặc auto-configuration không.

Nếu không thực sự cần cả hai, **giảm số tầng framework phụ thuộc** thường giúp việc kiểm version và vận hành dễ hơn.

## 20. Test dependencies cũng cần cùng hệ phiên bản

Một build có thể **biên dịch ứng dụng thành công nhưng test lỗi runtime** nếu các thư viện test không đồng bộ:

| Thành phần | Dùng để làm gì? | Lỗi khi lệch version |
|---|---|---|
| `spring-boot-starter-test` | Test auto-configuration, Spring Test, JUnit/Mockito theo Boot line | Runner, extension và context setup bị lệch |
| `spring-integration-test` | `@SpringIntegrationTest`, `MockIntegrationContext`, mock endpoint/trigger | Không tìm thấy class/test utility hoặc method |
| JUnit Platform/Jupiter | Chạy tests | Test không được phát hiện, launcher API mismatch |
| Mockito/Byte Buddy | Mock clients và handlers | Mock engine/agent lỗi với JDK mới |
| Testcontainers | SFTP/broker/DB test infrastructure | Docker runtime/client incompatibility |
| Spring Cloud Stream test binder | Test binding giả lập | Test binder khác thế hệ Stream/Cloud |
| `spring-kafka-test` | Broker/consumer test Kafka | Version API khác Spring Kafka runtime |
| Reactor Test, Spring Web test | Reactive/HTTP test | Assertion utilities/runtime classes mismatch |

**Nguyên tắc:** ưu tiên dependency test được Boot/Cloud BOM quản lý khi có, và dùng modules test phù hợp line runtime. Không khai báo `mockito-core`/`junit-jupiter` version tùy ý chỉ vì IDE gợi ý cập nhật patch. Khi override vì bug/security, cần chạy test suite **trên JDK production** và kiểm compatibility ghi trong release notes.

### 20.1. Hai loại lỗi cần phân biệt

- **Test framework mismatch:** `NoSuchMethodError` trong JUnit/Mockito/Spring Test trước khi business logic chạy.
- **Application compatibility regression:** test chạy được nhưng assertion sai do Spring Integration mới đổi serialization, routing, poller hoặc header behavior.

Hãy kiểm stack trace để xác định lớp nào ném lỗi, chứ không vội đổi toàn bộ Spring versions khi chỉ một plugin test thiếu dependency.

## 21. Quét dependency và SBOM: version hợp lệ chưa chắc an toàn

Một BOM có thể cung cấp bộ version tương thích ở thời điểm phát hành, nhưng các CVE mới có thể được phát hiện sau đó. Vì vậy quản lý compatibility phải đi cùng **security posture**:

- Duy trì **SBOM** (ví dụ CycloneDX/SPDX nếu công cụ/pháp lý yêu cầu) cho artifact release.
- Chạy dependency vulnerability scanner phù hợp quy trình tổ chức, đối chiếu nguồn advisory chính thức.
- Kiểm support/EOL của Boot, JDK, integration modules, broker clients, database drivers.
- Phân biệt **vulnerability trong dependency có mặt** với exploitability trong cấu hình/đường chạy của ứng dụng; không bỏ qua CVE nghiêm trọng chỉ vì test xanh.
- Với bản vá khẩn ngoài BOM, ghi rõ lý do và xác minh binary/protocol compatibility.
- Theo dõi việc nâng BOM để giảm override lâu dài.

**Không sửa mọi cảnh báo bảo mật bằng cách ép một transitive dependency lên major mới nhất** nếu không biết API tương thích. Một mitigation có thể là nâng patch release tương thích, nâng cả release line, thay thư viện hoặc áp dụng cấu hình giảm rủi ro có theo dõi.

### 21.1. Lockfile, reproducible build và dependency provenance

BOM, version catalog, dependency locking, repository mirror và checksum verification phục vụ các mục đích bổ trợ:

| Cơ chế | Giải quyết |
|---|---|
| BOM | Quy tắc phối hợp version của thư viện |
| Version catalog/properties | Tập trung version/coordinate để review |
| Dependency locking | Ghi resolved versions để tránh drift bất ngờ |
| Artifact checksum/provenance | Bảo đảm artifact tải về đúng nguồn/tính toàn vẹn |
| SBOM | Ghi các package/version hiện diện trong build |
| Scanner/advisory | Phát hiện phiên bản có rủi ro được công bố |
| Build/test pipeline | Kiểm binary/behavior thực tế |

Một ứng dụng có BOM nhưng không có lockfile vẫn có thể tái lập được trong những điều kiện nhất định nếu mọi version đã được pin và repository ổn định; lockfile tăng thêm kiểm soát, **không tự thay thế BOM**.

## 22. Dấu hiệu lỗi tương thích và cách khoanh vùng

| Triệu chứng | Nhóm nguyên nhân cần điều tra | Kiểm tra đầu tiên |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime Java thấp hơn class file target | `java -version`, `mvn --version` hoặc `gradlew --version`, image base |
| `NoSuchMethodError` / `AbstractMethodError` | ABI không tương thích; method signature đã đổi | Resolved runtime classpath, jar thực được load |
| `NoClassDefFoundError` / `ClassNotFoundException` | Thiếu dependency hoặc package đổi giữa versions | Dependency tree, module scope, namespace |
| `BeanCreationException` | Bean/auto-config không khởi tạo | Caused-by đầu tiên, config property, provider bean |
| `NoSuchBeanDefinitionException` | Thiếu bean/auto-config module hoặc conditional sai | Starter, auto-config report, package scan |
| `ClassCastException` | Serializer/converter API hoặc payload type không đồng bộ | Message type ở từng channel, converter version |
| HTTP 415/406 hoặc JSON mapping sai | Content type/serialization contract | Adapter header mapper + converter + mock server |
| SFTP session/auth fail | Client/SSH server/cipher/host key incompatibility | Remote host key, algorithm negotiation, client libs |
| JMS `javax`/`jakarta` mismatch | Provider và Boot line thuộc thế hệ khác | JMS API package và provider client version |
| AMQP routing/ack khác | Spring AMQP/client/broker config thay đổi | Exchange/binding, confirms, listener container |
| Kafka serialization/offset lỗi | Client/broker/schema/consumer config khác | Topic/key/header, serializers, broker test |
| DB driver lỗi auth/SQL | Driver–server–JDK hoặc SQL dialect | JDBC driver/version, connection config, DB test |
| Test chạy IDE nhưng CI fail | JDK/build cache/toolchain/test env khác | Wrapper, lock, CI runtime, test resources |
| Startup pass nhưng không có message | Endpoint lifecycle/poller/filter hoặc error channel | IsRunning, channel wiring, inbound source, logs |

**Quy tắc điều tra:** đọc nguyên nhân gốc trong exception chain, xác nhận artifact/classpath thực đã deploy và tạo một test tối thiểu tái hiện lỗi. Đừng thay version ngẫu nhiên trước khi xác định mối quan hệ gây lỗi.

## 23. Case study: cùng project nhưng Boot, Integration và SFTP lệch nhau

Một nhóm dùng ứng dụng Spring Boot đang chạy adapter File/SFTP và HTTP outbound. Sau khi thêm một thư viện đối tác, build vẫn xanh nhưng runtime lỗi khởi tạo outbound SFTP handler.

**Giả thuyết ban đầu (minh họa):**

~~~text
Application:
  Spring Boot managed dependency line: A

Direct dependencies:
  spring-boot-starter-integration: managed by A
  spring-integration-sftp: explicit version B (khác dòng A)
  partner-sdk: version C

Resolved graph:
  spring-integration-core: A
  spring-integration-sftp: B
  SSH client implementation: changed by B/C transitives

Runtime:
  startup/linkage failure or SFTP session failure
~~~

Cách giải quyết có kiểm soát:

1. **Thu thập bằng chứng:** ghi Boot version, Java version, JAR/module hiện diện, stack trace đầu tiên.
2. **Đọc dependency tree:** xác định phiên bản thực tế của `spring-integration-core`, `sftp` và SSH client; không suy từ POM một mình.
3. **Đối chiếu BOM:** bỏ explicit SFTP version nếu không có lý do, để Boot quản lý một bộ phù hợp.
4. **Kiểm vendor SDK:** nếu nó đưa library cũ hoặc API khác, tìm bản vendor phù hợp; không exclude khi chưa biết có runtime user nào dùng.
5. **Biên dịch và startup:** chạy unit + context smoke test, kiểm bean SessionFactory và flow endpoints.
6. **SFTP contract test:** dùng test server để upload/download, xác minh host key, bytes, remote path, rename/restart.
7. **HTTP regression test:** đảm bảo outbound gateway vẫn map body/header/timeout đúng sau khi đổi BOM.
8. **Security scan:** xem bản đã chốt có CVE và support status gì.
9. **Deploy canary/rollback:** rollout theo quy trình, giữ manifest dependency cũ để quay lại nếu cần.

**Không kết luận** nguyên nhân chắc chắn là “SFTP B sai” khi chưa đọc stack trace; cấu hình host key/credential/remote server cũng có thể gây lỗi. Case này minh họa **phương pháp xác định**, không phải một incident đã được quan sát thật.

## 24. Case study: thêm Spring Cloud Stream làm lệch Kafka adapter

Giả sử app vốn dùng `spring-integration-kafka` trực tiếp, sau đó thêm Cloud Stream Kafka binder nhưng không xem Cloud release train.

Dấu hiệu có thể gồm:

- Cloud compatibility verifier cảnh báo mismatch Boot/Cloud.
- Hai nhóm cấu hình Kafka producer/consumer chạy đồng thời với settings khác nhau.
- Test binder pass nhưng broker test fail vì topic/key/header/schema.
- Library graph có nhiều constraint/override của `spring-kafka` hoặc `kafka-clients`.
- Lỗi API tại runtime dù Maven đã resolve thành công.

Quy trình:

1. Xác định có thật sự cần Cloud Stream hay chỉ cần Kafka adapter trực tiếp.
2. Nếu cần, chọn Cloud train khớp Boot line, import BOM đúng cách.
3. Loại override không được phê duyệt; kiểm dependency resolution.
4. Phân biệt test `OutputDestination` in-memory với Kafka integration test.
5. Kiểm topic/key/serializer/offset/ack/rebalance/retry và event idempotency.
6. Không vô hiệu compatibility verifier để chỉ làm lỗi startup biến mất.

**Không cố làm một dependency graph “sạch warning” bằng cách xóa tự động các module transitively cần cho handler đang sử dụng.** Thay đổi kiến trúc cần hiểu rõ bean wiring và contract.

## 25. Bộ kiểm thử phiên bản tương thích cho một ứng dụng adapters

Chia thành các cổng kiểm tra (quality gates):

~~~mermaid
flowchart TD
    INPUT["BOM + JDK + adapter choices"] --> RES["1. Dependency resolution"]
    RES --> COMP["2. Compile/package"]
    COMP --> START["3. Spring context startup"]
    START --> MSG["4. MessageChannel/flow contract"]
    MSG --> AD["5. Adapter protocol smoke"]
    AD --> FAIL["6. Failure/retry/lifecycle"]
    FAIL --> SEC["7. Security + SBOM scan"]
    SEC --> DEPLOY["8. Canary/rollout evidence"]
~~~

| Gate | Input | Pass condition |
|---|---|---|
| **1. Resolve** | Effective POM/dependencyInsight | Không còn override/duplicate bất ngờ, dependency graph có chủ đích |
| **2. Compile** | Source/tests và plugin build | Compile/package đúng JDK target, không API break |
| **3. Startup** | `@SpringBootTest` hoặc chạy app test profile | Context tạo được, bean adapter, converters, channels đầy đủ |
| **4. Message flow** | `Message<?>` với payload/header | Transform/router/gateway/poller chạy đúng contract |
| **5. Protocol smoke** | File test, mock HTTP, SFTP/broker/DB test | Có side effect ở đích và metadata đúng |
| **6. Failure/lifecycle** | Timeout, disconnect, duplicate, restart | Retry/ack/error/recovery/idempotency như chính sách |
| **7. Security** | SBOM, vulnerabilities, secret scan | Version đáp ứng chính sách và có xử lý cảnh báo |
| **8. Rollout** | Artifact đã chốt và release notes | Deploy/test canary, metrics/log/rollback sẵn sàng |

Mỗi gate phải ghi **thực tế đã chạy hay chỉ dự kiến**. Khi chỉ viết bài, không được gắn nhãn PASS cho bất kỳ gate nào của dự án chưa được thực thi.

### 25.1. Ví dụ smoke test Spring Integration không cần network

Trong `@SpringBootTest` hoặc một `@SpringJUnitConfig` có flow test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DependencyCompatibilitySmokeTest.Config.class)
class DependencyCompatibilitySmokeTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        MessageChannel adapterInput() {
            return new DirectChannel();
        }

        @Bean
        PollableChannel testOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow compatibilityFlow() {
            return IntegrationFlow.from("adapterInput")
                    .<String, String>transform(String::trim)
                    .channel("testOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    PollableChannel output;

    @Test
    void canCreateAndDispatchAMessage() {
        Message<String> request = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("correlationId", "corr-42")
                .build();

        assertTrue(input.send(request));

        Message<?> reply = output.receive(1000);
        assertNotNull(reply);
        assertEquals("order-42", reply.getPayload());
        assertEquals("corr-42",
                reply.getHeaders().get("correlationId"));
    }
}
~~~

Điều test này xác minh là **Core/DSL/MessageChannel wiring/behavior cơ bản hoạt động** với graph hiện tại, nhưng **chưa chứng minh** File/SFTP/HTTP/Kafka/JMS/AMQP/JDBC modules thực tương thích protocol. Mỗi adapter cần ít nhất một test riêng ở ranh giới quan trọng.

### 25.2. Những test bắt buộc bổ sung theo module

- **File:** tạo/đọc file thật với `@TempDir`; filter/metadata/restart.
- **SFTP:** test server, host key, download/upload, reconnect/temporary rename.
- **HTTP:** mock server, method/URI/body/header, 2xx/4xx/5xx/timeout.
- **JMS:** provider test, acknowledgement, transaction, redelivery.
- **AMQP:** RabbitMQ test, exchange/queue, confirm/return, DLQ.
- **Kafka:** broker test, topic/key/schema/offset/consumer group/retry.
- **JDBC:** database test, DataSource/driver, SQL dialect/transaction, concurrent polling.

## 26. Quy trình nâng cấp dependency theo release có kiểm soát

### Giai đoạn 1 — Đóng băng baseline

Ghi lại:

- Java build/runtime, Spring Boot version, Spring Integration resolved versions, Spring Cloud release train nếu có.
- Version Maven/Gradle wrapper và plugins.
- Container image, client libs, driver, broker/server versions được hỗ trợ.
- Snapshot dependency tree, SBOM, build artifact digest và test suite hiện tại.
- Lỗi đã biết, mức đo latency/retry/error và các luồng quan trọng.

### Giai đoạn 2 — Đề xuất target stack

Chọn **release line** theo support policy, không chỉ theo số version lớn nhất. Kiểm JDK baseline, framework major, Integration release notes, Cloud train, adapter-specific migration và security posture.

### Giai đoạn 3 — Nâng có thứ tự

- Khi chỉ áp dụng patch tương thích theo BOM: cập nhật Boot BOM/parent/plugin theo bản phát hành được phê duyệt.
- Khi nâng minor/major: chuẩn bị sửa Java source, module API, namespace, config properties, client/serializer/test tools.
- Nâng Cloud BOM theo release train tương ứng **chỉ nếu dự án dùng Cloud**.
- Gỡ các explicit overrides cũ không còn lý do; giữ exception có tài liệu khi bắt buộc.
- Xử lý vendor SDK/client không hỗ trợ bằng update, replacement hoặc tách biên, không ép chạy với API không tương thích.

### Giai đoạn 4 — Chạy quality gates

Kiểm dependency graph, compile/package, application startup, unit/flow/protocol/negative tests. Đặc biệt chú trọng **gateway reply/error, poller lifecycle, SSH/TLS, Kafka schema/offset, JMS transactions, AMQP confirms và DB isolation**.

### Giai đoạn 5 — Rollout và rollback

- Deploy canary/staging theo risk, kiểm metrics và log an toàn.
- Giữ artifact và cấu hình baseline để rollback nhanh.
- Nếu nâng schema/message format, kiểm khả năng rollback **cả producer và consumer** (forward/backward compatibility).
- Không rollback version làm mất bản vá critical mà không có quyết định rủi ro và biện pháp bảo vệ thích hợp.
- Cập nhật SBOM, dependency inventory và tài liệu vận hành.

### 26.1. Khi migration dài, làm sao giảm rủi ro?

Với major upgrade và nhiều adapters, ưu tiên nâng theo **ranh giới có thể kiểm thử độc lập**: tách client wrappers, adapter configurations, message DTO/contracts và test fixtures. Không nâng tất cả broker/client/provider cùng lúc nếu không có nhu cầu cấp bách; vẫn phải giữ các version phối hợp tương thích theo BOM.

## 27. Automation CI: kiểm version là một kiểm soát liên tục

Có thể đưa vào pipeline:

~~~text
Pull request:
  1. Validate build files (POM/Gradle)
  2. Resolve/check dependency graph
  3. Compile and run unit/flow tests
  4. Run security/SBOM checks
  5. Run protocol contract tests selectively or in CI
  6. Report changed version coordinates and risk
  7. Require code owner/security review for major overrides

Main/release:
  1. Rebuild with controlled JDK/wrapper
  2. Run full adapter integration tests
  3. Verify packaged artifact and SBOM
  4. Stage/canary deployment and monitor
  5. Promote or rollback based on evidence
~~~

Ví dụ **lệnh tham khảo** (không chạy trong bước viết tài liệu):

~~~powershell
# Maven CI:
mvn -B -ntp clean verify
mvn dependency:tree -Dincludes=org.springframework.integration

# Gradle CI trên Windows:
.\gradlew.bat clean test
.\gradlew.bat dependencyInsight --dependency spring-integration-core --configuration runtimeClasspath
~~~

Ở CI thật, thêm chính sách scan phù hợp, integration tests với test infrastructure, cache/repository mirror có xác thực và kiểm JDK/container image. **Đừng chỉ grep chuỗi version từ POM**: cách đó bỏ qua dependency management, overrides và runtime classpath.

### 27.1. Tự động update version bằng bot

Dependency update bot có thể tạo PR khi Boot/Integration/client có release mới. Đừng auto-merge **major/framework/cloud train** chỉ vì dependency resolution pass. Yêu cầu:

- Giải thích version trước–sau và release notes.
- Xác định CVE nếu update nhằm vá lỗi.
- Đọc dependency diff/SBOM.
- Chạy adapter test theo module thay đổi.
- Có rollback plan cho production.

## 28. Ma trận quyết định: sửa gì khi gặp một version conflict?

| Phát hiện | Hướng xử lý ưu tiên | Không nên làm |
|---|---|---|
| Integration core và adapter khác release line do explicit version | Gỡ override, dùng Boot BOM; kiểm graph/test | Nâng riêng core đến khi startup pass |
| Vendor SDK kéo Spring Framework cũ | Tìm vendor SDK tương thích, kiểm transitive | Exclude tất cả Spring JAR của vendor theo cảm tính |
| Cloud compatibility warning | Chọn Cloud train tương thích Boot | Disable verifier rồi triển khai |
| JMS client thuộc namespace cũ | Nâng provider hỗ trợ API phù hợp | Thêm cả javax/jakarta để thử may |
| Kafka broker không hỗ trợ feature mới | Xác nhận client/broker matrix, điều chỉnh config hợp lệ | Bật feature bất tương thích bằng flag không hiểu |
| SSH handshake fail sau JDK upgrade | Xem host key/ciphers/trust/client versions | Tắt host-key verification |
| DB tests pass H2, fail PostgreSQL | Test trên DB gần production, sửa SQL/transaction | Giả định in-memory dialect đủ bằng chứng |
| Test-only version mismatch | Dùng test dependency phù hợp Boot line | Override hàng loạt runtime libs |
| CVE ở transitive dependency | Chọn patch/bộ BOM phù hợp, đánh giá risk | Ép major mới không test |
| Release artifact khác CI classpath | So nội dung JAR/image, toolchain và lock | Đổ lỗi framework khi chưa xác nhận artifact |
| API adapter đã deprecated/removed | Đọc migration guide, sửa code + contract tests | Trộn code snippet của hai major |

## 29. Checklist nghiệm thu compatibility trước khi merge/release

- [ ] Version Spring Boot và status support được chọn có căn cứ.
- [ ] Java build/compile/runtime đáp ứng minimum và target bytecode.
- [ ] Spring Integration Core và các adapter thực dùng cùng release line phù hợp BOM.
- [ ] Không có explicit version overrides không rõ nguồn hoặc thiếu test.
- [ ] Đã đối chiếu compatibility Spring Cloud train nếu dùng Cloud Stream/binders.
- [ ] Phân biệt direct adapter và binder, tránh dependency không cần.
- [ ] Chỉ khai báo những adapter modules cần thiết.
- [ ] Kiểm dependency tree/effective POM hoặc Gradle dependencyInsight/runtimeClasspath.
- [ ] Kiểm Spring Framework, messaging, serialization, Kafka/AMQP/JMS/SSH/JDBC clients.
- [ ] Kiểm namespace Jakarta/Javax khi nâng major từ hệ cũ.
- [ ] Kiểm phiên bản Maven/Gradle plugin và wrapper.
- [ ] Có unit/flow smoke test với MessageChannel/IntegrationFlow.
- [ ] Có integration tests cho file, SFTP, HTTP, JMS, AMQP, Kafka, DB **theo module thực dùng**.
- [ ] Có negative tests cho timeout, reconnect, retries, duplicate, serialization và errors.
- [ ] Test trên JDK và hạ tầng protocol gần production.
- [ ] Có security scan, SBOM, support/EOL check và kế hoạch xử lý CVE.
- [ ] Artifact/container build tái lập, có provenance/checksum theo quy trình.
- [ ] Review dependency diffs, migration notes và config properties thay đổi.
- [ ] Có release/canary monitoring và rollback plan.
- [ ] Kết luận phân biệt resolution/compile/startup/protocol/security đã thực sự được kiểm chứng.

## 30. Tình huống tự đánh giá

### Tình huống A — “Cùng một số version mới nhất là tương thích?”

**Đề:** Một thành viên lấy Spring Boot mới nhất, Spring Integration mới nhất và Spring Cloud release train mới nhất, ghép tất cả vào POM. Maven resolve dependency thành công. Có thể merge ngay?

**Đáp:** **Không.** Những “mới nhất” có thể thuộc các release line không tương thích. Phải kiểm support matrix, BOM/resolved graph, JDK, Cloud train, API migration và test compile–startup–protocol. Maven resolve **không chứng minh** binary/runtime compatibility.

### Tình huống B — “BOM đã quản lý nhưng sao JAR SFTP khác version?”

**Đề:** POM dùng Boot parent, nhưng khai báo `spring-integration-sftp` với explicit version khác Core. SFTP endpoint lỗi runtime. Vì sao?

**Đáp:** Version trực tiếp có thể override version được quản lý, tạo nhóm Integration lệch dòng. Cần kiểm effective POM/dependency tree, đối chiếu BOM và bỏ override không có căn cứ; xác nhận lại với SFTP integration test.

### Tình huống C — “IDE chạy được, container production lỗi UnsupportedClassVersionError”

**Đề:** CI/IDE dùng JDK mới, Docker image chạy JDK cũ hơn. Điều gì phải kiểm?

**Đáp:** Toolchain/target bytecode, Java version trong container và minimum JDK của Boot/client. Không chỉ nhìn `java.version` hoặc JDK máy lập trình; runtime thực phải hỗ trợ bytecode.

### Tình huống D — “JMS import javax.jms.ConnectionFactory ở Boot 3”

**Đề:** Thư viện provider rất cũ dùng `javax.jms`, app đang dùng thế hệ Jakarta. Có nên đưa cả `javax.jms-api` và `jakarta.jms-api` vào classpath?

**Đáp:** **Không tự động.** Hai API không thay thế nhau. Phải chọn phiên bản provider client hỗ trợ API phù hợp với Spring Framework/Boot line, test connection/transaction/redelivery và migration code.

### Tình huống E — “Kafka broker là version X, client phải bằng đúng X?”

**Đề:** Developer ép Kafka client có cùng số với broker thay vì bản Boot BOM đang quản lý. Đây có phải luôn là cách làm đúng?

**Đáp:** **Không.** Kafka client/broker tương thích theo matrix/feature, không mặc định phải cùng số tuyệt đối. Kiểm tài liệu Kafka/vendor, Spring Kafka version và protocol tests trước khi override.

### Tình huống F — “Spring Cloud compatibility verifier đang cản startup”

**Đề:** Sau khi thêm Kafka binder, Spring Cloud cảnh báo Boot/Cloud mismatch. Có thể disable compatibility verifier để tiếp tục triển khai?

**Đáp:** Tắt cảnh báo **không sửa** vấn đề. Cần xác định release train phù hợp Boot line, import BOM đúng, kiểm dependency graph và binding/broker tests.

### Tình huống G — “NoSuchMethodError trong Spring Messaging”

**Đề:** App compile pass, nhưng runtime `NoSuchMethodError` từ class Spring Messaging. Làm gì trước?

**Đáp:** Kiểm JAR thực được load, runtimeClasspath và dependency graph; tìm vendor SDK/explicit override/packaging dẫn đến ABI không tương thích. Xác định cause trước khi thay version; sau đó chạy startup và flow tests.

### Tình huống H — “SFTP mock test xanh nhưng connection fail sau nâng JDK”

**Đề:** Mock session báo upload thành công nhưng test server SSH thất bại handshake. Kết luận?

**Đáp:** Mock chỉ chứng minh handler logic, không chứng minh auth/host key/cipher negotiation. Xem SSH client versions, JDK security settings, server policy và host key; **không** tắt xác minh host key để che lỗi.

### Tình huống I — “Tất cả unit tests pass, HTTP integration trả 415”

**Đề:** Nâng dependency xong unit transformer pass nhưng HTTP server trả `415 Unsupported Media Type`. Có phải Spring Integration Core lỗi?

**Đáp:** Chưa thể kết luận. Kiểm content type, HTTP header mapper, message converter/JSON serialization, client configuration và API contract. Unit test nội bộ không chứng minh body/header khi ra transport.

### Tình huống J — “Đã override Jackson để vá CVE”

**Đề:** Nhóm đổi riêng một Jackson artifact lên major khác để xử lý CVE, chưa test converter. Rủi ro?

**Đáp:** Có thể lệch API giữa các Jackson modules, Spring Web/Boot serializers hoặc thay behavior JSON. Cần chọn patch/bộ BOM phù hợp, kiểm toàn serialization graph, schema compatibility và test HTTP/Kafka/DB khi có liên quan.

### Tình huống K — “Database adapter pass H2 nhưng fail PostgreSQL”

**Đề:** SQL polling chạy trong H2 test, lên PostgreSQL production bị lỗi lock và record bị xử lý hai lần.

**Đáp:** H2 không luôn mô phỏng dialect/isolation/locking của PostgreSQL. Cần database test gần production, kiểm transaction boundary, concurrency và idempotency, không lấy H2 pass làm bằng chứng cho mọi DB.

### Tình huống L — “Một PR cập nhật version nhưng không có bằng chứng”

**Đề:** Bot mở PR nâng Spring Boot patch; changelog chỉ viết “versions updated”, không có dependency diff/test. Có nên auto-merge?

**Đáp:** Không nên coi đó là bằng chứng đầy đủ. Phải có policy dựa rủi ro: resolved graph diff, security scan, unit/flow/protocol regressions và scope ảnh hưởng. Với framework major/Cloud train, yêu cầu review migration và rollout.

### Tình huống M — “Maven dependency tree đẹp, deploy vẫn lỗi”

**Đề:** Trên máy local, `dependency:tree` không thấy xung đột, nhưng app trong container chạy client cũ.

**Đáp:** Kiểm artifact đóng gói, base image/layers, cache, server-managed classpath, registry digest và runtime dependency. Dependency tree của source **không thay thế** inspection của JAR/image được deploy.

### Tình huống N — “Chỉ chọn module adapter cần thiết”

**Đề:** App dùng file và HTTP nhưng POM chứa Integration Kafka, JMS, AMQP và SFTP chỉ để “sẵn sau này”. Vấn đề?

**Đáp:** Thừa dependencies tăng bề mặt cập nhật/CVE, classpath, auto-configuration và công sức test. Chỉ thêm module cần thật; khi mở kết nối mới hãy thêm dependency và contract tests có chủ đích.

### Tình huống O — “Một bài smoke test đã đủ?”

**Đề:** `@SpringJUnitConfig` tạo DirectChannel và transformer, test pass sau khi nâng Integration. Đã chứng minh hệ thống Kafka/SFTP/HTTP tương thích?

**Đáp:** **Chưa.** Smoke test chứng minh core/DSL/wiring ở phạm vi nhỏ. Adapter còn phụ thuộc client, serialization, broker/server, TLS/SSH và lifecycle; cần protocol integration tests để kết luận.

## Kết luận

**Kiểm tra dependency version tương thích** cho **Spring Boot và Spring Integration Adapters** là quản trị **cả một hệ sinh thái phiên bản**, không phải chọn số mới nhất trên Maven Central. **Spring Boot BOM** giúp đồng bộ Spring Framework, Spring Integration và các thư viện được quản lý; **Spring Cloud BOM/release train** chỉ nên thêm khi dùng Cloud Stream/binder và phải tương thích với Boot line. Với File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC, còn phải đối chiếu **JDK, provider/client, broker/server, serializer, transaction, security và vòng đời kết nối**. Một quy trình tốt luôn xác minh **resolved dependency graph → compile → startup → MessageChannel flow → adapter protocol/side effect → failure/lifecycle → security/rollout**, ghi rõ phần nào đã được kiểm thử thực tế. Nhờ đó, việc nâng cấp diễn ra có kiểm soát, hạn chế lỗi linkage, contract drift và truy cập hệ thống ngoài không đáng tin cậy, đồng thời giữ được khả năng vận hành và rollback.
