# Ma trận JDK, Spring Boot và phiên bản dịch vụ phụ thuộc

## 1. Vì sao một bản build xanh chưa đủ?

Trong hệ thống Spring Boot, một commit có thể vượt qua mọi unit test trên máy của developer nhưng lỗi khi triển khai trên một tổ hợp runtime khác:

- Dự án biên dịch bằng **JDK 17**, nhưng khi chạy trên **JDK 21** thì một thư viện dùng reflection/bytecode instrumentation hoạt động khác.
- Build plugin tương thích với một bản Spring Boot nhưng dependency management kéo nhầm phiên bản Spring Framework, Jackson, Hibernate hoặc JDBC driver khi nâng Boot.
- Repository query hoạt động trên **PostgreSQL 16** nhưng lỗi trên **PostgreSQL 15** do cú pháp SQL, collation, extension hoặc thay đổi planner.
- Service dùng Redis commands/phương thức serialization phù hợp **Redis 7**, nhưng gặp semantics khác với một phiên bản được vận hành thực tế.
- Kafka consumer có thể tương thích với một broker version, nhưng serialization, offset handling hoặc rebalance gây lỗi trên version khác.
- Gradle daemon chạy JDK 21 trong khi test worker JVM vẫn chạy JDK 17, khiến một CI job gắn nhãn “Java 21” **không thật sự kiểm runtime 21**.
- CI chạy hàng chục tổ hợp mà không kiểm version server đang kết nối; tất cả tests có thể vô tình dùng cùng một database URL từ biến môi trường cũ.
- Một bản candidate Spring Boot mới đã nâng transitive dependencies, nhưng test chỉ chạy `compileJava` chứ không chạy integration test với database/broker thật.

**Ma trận tương thích (compatibility matrix)** là tập các tổ hợp **JDK + Spring Boot + dịch vụ phụ thuộc** được chọn để chứng minh phần mềm hoạt động trên những phiên bản mà sản phẩm thực sự hỗ trợ. Ma trận là **một kiểm chứng kỹ thuật dựa trên hợp đồng hỗ trợ**, không đơn thuần là bảng liệt kê phiên bản.

Bài thuộc phần **Build và CI** của module **Spring Boot – testing**, với đề bài **Ma trận JDK, Spring Boot và phiên bản dịch vụ phụ thuộc**.

Sau bài học, bạn sẽ:

1. Phân biệt **JDK biên dịch**, **JDK chạy Gradle**, **JDK của test worker JVM** và **JDK runtime triển khai**.
2. Dùng Java **toolchains** để biên dịch mã hướng Java 17 nhưng kiểm ứng dụng trên JDK 17 và 21.
3. Phân biệt **Spring Boot Gradle plugin version**, **Spring Boot BOM/dependency management** và **version mà ứng dụng thực sự nạp khi chạy**.
4. Chọn đúng các versioned dependencies: PostgreSQL, Redis và những dịch vụ như Kafka/RabbitMQ.
5. Dùng Testcontainers khởi tạo service đúng **Docker image tag/digest** và tự kết nối với Spring Boot bằng `@ServiceConnection`.
6. Viết tests kiểm **actual runtime version** bằng `Runtime.version()`, `SpringBootVersion.getVersion()`, `SHOW server_version` và Redis `INFO server`.
7. Tổ chức `test` và `integrationTest` riêng: unit tests không bắt buộc Docker, integration tests dùng database/cache thật.
8. Tạo **GitHub Actions strategy.matrix** có các job JDK/Boot và các tổ hợp dịch vụ chọn lọc.
9. Thiết kế PR matrix, nightly full matrix, release certification và policy cho unsupported combinations.
10. Phân tích số lượng jobs tăng theo tích Descartes, tối ưu chi phí và thời gian CI.
11. Xử lý context caching, parallel forks, DB isolation, dynamic ports, artifact reporting và timeouts.
12. Chẩn đoán lỗi là do JDK, Boot, driver, service version, Testcontainers hay chính môi trường runner.
13. Giữ ma trận **tái lập được** bằng Gradle Wrapper, BOM, lockfiles/image digests và artifact provenance.
14. Cập nhật ma trận khi nâng JDK LTS, Spring Boot minor hoặc database major version mà không vô tình làm giảm coverage.

**Thông điệp cốt lõi:** “Chạy trên JDK 21” phải được xác minh bằng JVM thực chạy tests; “kiểm PostgreSQL 17” phải được xác minh qua server đã kết nối. Một nhãn trong CI YAML hoặc một dependency string chưa đủ làm bằng chứng.

## 2. Ba trục chính của ma trận

Một tổ hợp có thể được mô tả bằng bộ:

~~~text
Combination = (
  build-toolchain / compiler level,
  test-runtime JDK,
  Spring Boot line + patch,
  PostgreSQL major/minor,
  Redis major/minor,
  optional Kafka/RabbitMQ versions,
  operating system / CPU architecture
)
~~~

Không phải mọi tổ hợp đều hợp lệ hoặc cần chạy. Ví dụ:

- Một ứng dụng **cố định Java 17 bytecode** có thể kiểm **test runtime JDK 17/21** nếu Spring Boot, Gradle và thư viện hỗ trợ.
- Một bản Spring Boot không hỗ trợ JDK rất mới thì job đó thuộc nhóm **experiment**, không nên được ghi là officially supported.
- Một database major đã hết thời hạn hỗ trợ của vendor thường cần migration plan, không nhất thiết được giữ trong required CI matrix.
- Nếu sản phẩm không dùng Kafka, không tạo Kafka dimension chỉ để cho ma trận “to”.
- Các version database được vận hành thực tế phải quyết định coverage ưu tiên, không lấy ngẫu nhiên ba tags mới nhất.

### 2.1. JDK có ít nhất ba ý nghĩa

| Khái niệm | Nơi thiết lập | Điều nó chứng minh |
| --- | --- | --- |
| Gradle daemon JVM | `JAVA_HOME`, Gradle launcher, GitHub Actions setup-java | Gradle và build plugins chạy được |
| Java compiler/toolchain | Gradle `java.toolchain`/`JavaCompile.javaCompiler` | Source/bytecode tương thích mức đã chọn |
| Test worker JVM | Gradle `Test.javaLauncher` | Test classes chạy thật trên JDK đã chọn |
| Production runtime | Docker base image/JDK ở deploy | Production JVM tương ứng; cần smoke riêng |
| Gradle Wrapper version | `gradle/wrapper/gradle-wrapper.properties` | Build tool đủ hỗ trợ Java/plugin version |

Ví dụ, máy CI có `java --version` trả 21 nhưng trong `build.gradle`, `java.toolchain.languageVersion=17` và Test task dùng **default toolchain**. Lúc này Gradle có thể chạy tests bằng **JDK 17**: job không chứng minh code hoạt động trên Java 21. Cần gán riêng **`Test.javaLauncher`**.

### 2.2. Spring Boot version có nhiều lớp

| Thành phần | Ví dụ trong bài | Khi nâng |
| --- | --- | --- |
| Boot Gradle plugin | `org.springframework.boot` 3.3.5 | Kiểm plugin/build support |
| Spring Boot BOM | `spring-boot-dependencies` cùng phiên bản | Kiểm transitive dependency graph |
| Spring Framework | Version do BOM Boot quản lý | Kiểm framework API/runtime behavior |
| Hibernate/Jackson/Lettuce | Version do BOM quản lý | Kiểm database/serialization/cache behavior |
| Spring Cloud release train | Nếu dự án dùng Spring Cloud | Phải đối chiếu compatibility với Boot |
| Testcontainers libraries | Do Boot BOM hoặc riêng quản lý | Kiểm Docker API/client/runtime |
| Boot runtime on classpath | `SpringBootVersion.getVersion()` | Chứng minh job không dùng nhầm artifact |

Không tự coi `-PspringBootVersion=3.x` là đủ nếu build file vẫn hardcode `org.springframework.boot` plugin version khác hoặc dependency versions bị override. Phải in dependency tree và kiểm runtime version.

### 2.3. Dịch vụ phụ thuộc

Một dự án thường dùng nhiều lớp:

| Dịch vụ | Cần kiểm theo version | Hành vi đáng kiểm |
| --- | --- | --- |
| PostgreSQL | Server major, driver, extensions | SQL dialect, DDL, transaction, collation, constraints |
| MySQL/MariaDB | Server major, connector | SQL modes, timezone, index/locking |
| Redis | Server major, Lettuce/Jedis driver | Commands, expiration, serialization, cluster |
| Kafka | Broker version, client, protocol | Offset, consumer rebalance, topic configs, serialization |
| RabbitMQ | Broker, Spring AMQP version | Publisher confirms, DLX, retries, ack |
| Elasticsearch/OpenSearch | Server, HTTP client | Mappings, query DSL, compatibility headers |
| MongoDB | Server, driver | Transactions, indexes, BSON codecs |
| S3-like storage | API/server version | Presigned URLs, multipart, ETag, eventual behavior |
| External REST services | Contract/versioned stub/real sandbox | Status/error schema, timeouts, auth, compatibility |

Bài thực hành chạy thật với **PostgreSQL và Redis**, còn Kafka/RabbitMQ được đưa vào hướng dẫn mở rộng để tập trung đúng mục tiêu của ma trận.

## 3. Phân biệt “supported”, “tested” và “expected”

Dùng ba nhãn riêng:

**Supported:** nhóm sản phẩm chính thức cam kết với user/khách hàng. Phải có nguồn quyết định hỗ trợ, chính sách an ninh và thời hạn kết thúc.

**Tested:** tổ hợp đã thực sự chạy suite tương ứng và có bằng chứng pass ở CI, bao gồm image/runtime thực, test result artifacts và ngày chạy.

**Expected:** tổ hợp được dự đoán sẽ hoạt động theo tài liệu hoặc kiến trúc, nhưng **chưa có một run kiểm chứng**. Không tự nâng nhãn thành Tested.

Trong bài, các versions Spring Boot 3.3.5, 3.4.13 và image tags PostgreSQL/Redis là **ví dụ tái lập kiến trúc của lab**, không phải khuyến nghị sử dụng patch cũ trong production ở thời điểm đọc. Danh sách support thực tế phải được rà soát theo policy vendor và tình trạng EOL/security. Nếu hệ thống production đã dùng bản patch mới, hãy thay tags bằng các patch/digest đã được phê duyệt và kiểm lại tương thích.

### Quy tắc với bản Spring Boot đang nâng cấp

- **Baseline:** version sản phẩm hiện đang triển khai và được hỗ trợ.
- **Candidate:** version có kế hoạch chuyển lên.
- **Canary/experimental:** JDK hoặc server version mới chưa được tuyên bố supported.
- **Deprecated:** tổ hợp còn trong thời kỳ chuyển tiếp nhưng có sunset date.
- **Unsupported:** tổ hợp không được kiểm hoặc không thể hoạt động; CI cần nói rõ vì sao bị loại.

Một job với version không nằm trong support policy có thể chạy định kỳ để phát hiện sớm, nhưng không nên làm mơ hồ kết quả release gate.

## 4. Thiết kế coverage trước khi viết workflow

### 4.1. Cartesian product bùng nổ

Giả sử:

~~~text
JDK          = 17, 21               -> 2
Spring Boot  = 3.3.5, 3.4.13         -> 2
PostgreSQL   = 15.8, 16.4, 17.0    -> 3
Redis        = 7.2.4, 7.4.0         -> 2

Full product = 2 * 2 * 3 * 2 = 24 jobs
~~~

Nếu thêm 2 OSes và 3 Kafka versions, có thể thành 144 jobs. Mỗi job khởi động Spring context, Docker images và test suite; số jobs, CPU minutes, artifact storage và tải lên Docker registry tăng mạnh.

### 4.2. Ma trận theo rủi ro

Thường chia thành:

1. **PR smoke (required):** JDK baseline + next LTS, baseline Boot + candidate, 1–2 services phổ biến đang deployed.
2. **Nightly extended (scheduled):** gần full matrix với những versions trong support window.
3. **Release certification:** kiểm tất cả tổ hợp sản phẩm thực sự cam kết, đặc biệt major upgrades/security-sensitive paths.
4. **Canary/experimental:** versions mới chưa được hỗ trợ, có nhãn rõ và ban đầu có thể non-blocking nếu policy cho phép.

Ma trận phải được thống nhất với đội vận hành, không chỉ do người viết test chọn. Nếu khách hàng dùng PostgreSQL 14 còn được hỗ trợ thì việc chỉ test 16/17 sẽ bỏ sót rủi ro lớn.

### 4.3. Chọn combination bằng dữ liệu

Ưu tiên các yếu tố:

- Tỉ lệ deployments thực tế theo JDK/database versions;
- các version dự kiến nâng trong 1–2 quý;
- vendor EOL và security advisories;
- rủi ro khi đổi driver/ORM/SQL dialect;
- sự khác nhau giữa supported OS/CPU architectures;
- dữ liệu migration và fallback/rollback;
- giới hạn ngân sách CI;
- thời gian feedback tối đa của PR.

Có thể dùng pairwise testing để giảm số kết hợp, **nhưng pairwise không bảo đảm** bắt được các lỗi cần ba điều kiện hoặc tương tác bốn chiều. Giữ thêm explicit “high-risk triples” dựa trên incident history.

## 5. Khác biệt giữa bản biên dịch và JVM thực chạy test

Một cấu hình Gradle phổ biến:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Theo mặc định, toolchain này ảnh hưởng Java compile, test và một số tasks liên quan. Nếu CI thiết lập `JAVA_HOME=JDK21`, **chưa đủ** để kết luận các tests chạy JDK 21.

Chọn launcher cho test:

~~~groovy
int selectedJdk = Integer.parseInt(
    (findProperty('testJdk') ?: '17').toString())

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(selectedJdk)
    }
}
~~~

Cách này cho phép:

- `compileJava`/`compileTestJava` dùng toolchain **17** (target bytecode Java 17);
- `test` và `integrationTest` worker chạy JDK **17 hoặc 21** do `-PtestJdk` chọn;
- Gradle daemon có thể chạy JDK đủ hỗ trợ Gradle 8.8 nhưng không đồng nhất với JVM thực thi tests.

**Đánh đổi:** Khi runtime JDK 21 chạy bytecode Java 17, đây là bài kiểm **forward runtime compatibility**. Nó **không** chứng minh một dự án dùng Java 21 language features có thể compile trên JDK 17. Nếu cần cả hai mức source compilation, hãy tạo axis riêng cho compile-level, dùng JDK 21 toolchain và set `options.release`/`--release` theo policy; không nhầm “đổi test launcher” với “đổi compiler target”.

### 5.1. JDK toolchain availability

Máy local cần cài cả JDK 17/21 hoặc cấu hình Gradle toolchain download repositories. Nếu chỉ có JDK 21 trong CI và toolchain 17 chưa có, Gradle sẽ báo không tìm thấy compiler. Workflow ở phần sau **cài cả JDK 17 và runtime JDK của job** để không phụ thuộc auto-download ngoài kiểm soát.

### 5.2. Không kiểm những tổ hợp không được hỗ trợ

Một bản Gradle Wrapper cũ có thể không chạy được trên JDK quá mới dù ứng dụng về lý thuyết tương thích. Spring Boot plugin và thư viện ASM/Byte Buddy/Mockito còn có compatibility windows. Vì vậy kiểm ma trận **JDK–Gradle–Boot–test libraries** trước khi cho job đó thành required gate.

Ví dụ trong lab: Gradle 8.8, Java 17/21 và Spring Boot 3.3.5 là một tổ hợp lịch sử phù hợp để minh họa. Khi dùng JDK thế hệ mới, nâng Gradle Wrapper và xác minh Boot support matrix trước.

## 6. Spring Boot BOM và version alignment

Spring Boot cung cấp một dependency-management BOM để giữ các nhóm thư viện phù hợp. Ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Không tự pin `postgresql` driver quá cũ/mới nếu BOM đang quản lý và không có lý do rõ; khi override, CI cần biết đó là **một trục mới**.

### 6.1. Version plugin và BOM phải đi cùng policy

Trong ví dụ dùng Spring Boot Gradle plugin + `io.spring.dependency-management`. Khi thay `springBootVersion`, dependency management plugin import BOM tương ứng qua integration với Boot plugin. Điều đó cho phép kiểm **tập dependencies mới** chứ không chỉ đổi tên version trong log.

Không dùng riêng:

~~~groovy
id 'org.springframework.boot' version '3.4.13'
~~~

trong khi lại ép một BOM `spring-boot-dependencies:3.3.5` nếu mục đích là kiểm một Boot 3.4 app đồng bộ. Một số dự án có chủ đích override sẽ cần ma trận riêng và lý do compatibility được ghi nhận.

### 6.2. Tại sao không đặt mọi dependencies theo newest?

Boot BOM, Spring Framework, Spring Data, Security, Jackson, Reactor, Micrometer, Hibernate và Testcontainers có các compatibility relationships. Nâng tất cả về “latest” trong cùng PR khiến khó tìm root cause và có thể phá behavior. Phân lớp version:

- **Platform axis:** Boot release line và BOM.
- **Runtime axis:** JDK level.
- **Service axis:** database/cache/broker server version.
- **Deliberate overrides:** driver/plugin/lib version được track riêng khi thực sự cần.

Khi nâng Spring Cloud, chọn **release train tương thích Boot version** theo official compatibility matrix, không copy một release train mới nhất rồi chạy trên Boot cũ.

### 6.3. Dependency evidence

Trước khi chẩn đoán, lấy:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Output xác định **resolved versions**, có thể khác version được request vì platform constraints. Gắn báo cáo resolved dependency graph với CI artifact ở release certification khi cần.

## 7. Dịch vụ phụ thuộc: vì sao unit test H2 không đủ?

Nếu production dùng PostgreSQL mà integration tests chỉ dùng H2, bạn chưa kiểm:

- PostgreSQL-specific SQL functions/casts;
- collations, timezone và numeric precision;
- JSONB, arrays, UUID, generated columns;
- constraint violations và exception translation của JDBC;
- transaction isolation/locking;
- migration scripts Flyway/Liquibase;
- dialect tương thích giữa Hibernate và server;
- server configuration/extension availability.

Tương tự, Redis embedded/fake map không kiểm TTL, key eviction, Redis wire protocol, driver codec hoặc connection behavior thật. Kafka in-memory stubs không kiểm consumer group rebalance và broker protocols.

**Testcontainers** khởi chạy server thực trong Docker image đúng version, tạo ephemeral ports và lifecycle do test kiểm soát. Nó giúp integration tests gần production hơn nhưng **không tự chứng minh** network proxy/TLS/HA cluster, managed-service policies hay production data scale.

### 7.1. @ServiceConnection của Spring Boot

Spring Boot 3.3 hỗ trợ `@ServiceConnection` để đưa thông tin kết nối của Testcontainers vào auto-configuration thông qua `ConnectionDetails`. Với PostgreSQL typed container, Spring có thể tạo `JdbcConnectionDetails` cho `DataSource`.

Với Redis dùng `GenericContainer`, ghi `@ServiceConnection(name = "redis")` để Boot nhận ra service type. Đây là điểm khác với `@DynamicPropertySource` thủ công:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16.4");

@Container
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
    new GenericContainer<>("redis:7.2.4")
        .withExposedPorts(6379);
~~~

Đây là **snippet bên trong một test class có imports thích hợp**; source runnable ở phần sau còn lấy image version từ Gradle project properties.

### 7.2. Không dùng hardcoded localhost port

Testcontainers map container internal ports sang host ephemeral ports. Dùng `@ServiceConnection` hoặc `@DynamicPropertySource` lấy đúng URL/port. Nếu hardcode `localhost:5432`, CI có thể vô tình kết nối một PostgreSQL khác, khiến test pass trên **sai server version**.

### 7.3. Phiên bản thực tế cần được assert

Đừng chỉ in `postgres:17.0` từ build property. Hãy thực hiện:

~~~sql
SHOW server_version;
~~~

Cùng ý tưởng, Redis có:

~~~text
INFO server
~~~

Khi dùng Kafka, kiểm broker version qua broker metadata/config/cluster tooling phù hợp; `AdminClient` metadata không phải lúc nào cũng cung cấp server release version trực tiếp. Đừng bịa một API `getBrokerVersion()` luôn tồn tại.

### 7.4. Tại sao test driver cũng quan trọng?

Server version chỉ là một vế. JDBC driver, Spring Data, Hibernate và connection pool khác nhau có thể đổi SQL/generated queries/exception handling. Một job “PG17” nhưng vẫn dùng một driver version do Boot BOM quản lý phải ghi **resolved driver version** để khi phát sinh regression, biết server thay đổi hay dependency graph thay đổi.

## 8. Project mẫu đầy đủ

Lab cố định **Java 17 bytecode**; test runtime có thể dùng JDK **17 hoặc 21**; Boot version do `-PspringBootVersion` điều khiển thông qua Gradle plugin management; PostgreSQL/Redis images do `-PpostgresImage`/`-PredisImage` điều khiển.

### 8.1. File tree

~~~text
boot-service-matrix/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── .github/workflows/compatibility-matrix.yml
└── src/
    ├── main/java/com/example/matrix/
    │   ├── MatrixApplication.java
    │   └── PriceCalculator.java
    └── test/
        ├── resources/schema.sql
        └── java/com/example/matrix/
            ├── RuntimeMatrixTest.java
            ├── PriceCalculatorTest.java
            └── ServiceMatrixTest.java
~~~

Wrapper scripts/JAR là artifacts của Gradle, không thể tạo chính xác bằng cách copy toàn bộ từ Markdown. Sau khi có Wrapper 8.8, các files text trong bài có thể được đặt đúng đường dẫn để chạy.

### 8.2. settings.gradle: quản lý plugin versions theo property

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version "${springBootVersion}"
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'boot-service-matrix'
~~~

Trong Markdown cuối cùng, `${springBootVersion}` được chuyển thành đúng **Groovy GString interpolation** dạng dollar-brace. Gradle hỗ trợ lấy plugin version từ project `gradle.properties` qua pluginManagement. Với `-PspringBootVersion=...`, giá trị được override cho build tương ứng.

### 8.3. gradle.properties

~~~properties
springBootVersion=3.3.5
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

Đây là baseline ví dụ. `-Xmx2g` chỉ dành cho Gradle daemon trong bài; không tự áp dụng heap của Test JVM. Nếu cần heap limit cho forked tests, cấu hình `Test.maxHeapSize` riêng và đo memory.

### 8.4. build.gradle: compiler 17, test launcher 17/21

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

int selectedJdk = Integer.parseInt(
        (findProperty('testJdk') ?: '17').toString())

String selectedPostgres = (
        findProperty('postgresImage') ?: 'postgres:16.4').toString()

String selectedRedis = (
        findProperty('redisImage') ?: 'redis:7.2.4').toString()

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(selectedJdk)
    }

    systemProperty 'matrix.expectedJdk',
            selectedJdk.toString()

    systemProperty 'matrix.expectedBoot',
            springBootVersion.toString()

    systemProperty 'matrix.postgres.image', selectedPostgres
    systemProperty 'matrix.redis.image', selectedRedis

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}

// Unit tests luôn chạy offline, không cần Docker.
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration'
    }
}

// Integration tests dùng Testcontainers PostgreSQL + Redis.
tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'JDK/Boot/PG/Redis compatibility checks'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }

    shouldRunAfter(tasks.named('test'))
    maxParallelForks = 1
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

`useJUnitPlatform()` là API của Gradle hỗ trợ chạy JUnit Jupiter; với bộ lọc tag dùng cú pháp `useJUnitPlatform { includeTags/excludeTags ... }`.

**Các điểm cần đọc đúng:**

- `java.toolchain` vẫn biên dịch với Java 17.
- `Test.javaLauncher` chọn runtime JVM cho **test và integrationTest** bằng `-PtestJdk`.
- `springBootVersion` từ `gradle.properties` được sử dụng trong plugin management và evidence assertion.
- `postgresImage`/`redisImage` được truyền thành **JVM system properties** cho integration test; Java Testcontainers đọc những properties đó.
- `test` loại tag integration nên không khởi động Docker.
- `integrationTest` chỉ lấy tests có tag integration; giảm nguy cơ chạy lại unit tests.
- `check` phụ thuộc integrationTest. Nếu máy local không có Docker và chỉ muốn unit tests, chạy `./gradlew test`, **không** chạy `check`.
- `maxParallelForks=1` áp dụng cho một integrationTest task trong **một job**, nhưng CI matrix jobs chạy độc lập và có thể song song trên runners khác nhau.
- CI không dựa vào hardcoded DB/Redis ports.

### 8.5. MatrixApplication.java

~~~java
package com.example.matrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }
}
~~~

Không thêm Spring MVC hay HTTP server vì bài tập trung build/dependency compatibility. Service tests dùng JDBC/Redis thật để kiểm contract.

### 8.6. PriceCalculator.java

~~~java
package com.example.matrix;

public final class PriceCalculator {

    private PriceCalculator() {
    }

    public static long totalCents(
            long unitPriceCents, int quantity) {

        if (unitPriceCents < 0) {
            throw new IllegalArgumentException(
                    "Price must be nonnegative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

Một domain invariant đơn giản được kiểm bằng JUnit thuần. `Math.multiplyExact` tránh integer overflow im lặng. Dù project matrix chạy trên nhiều JDK/Boot versions, logic này không cần khởi động Spring context để test.

### 8.7. src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS compat_probe (
    marker VARCHAR(80) PRIMARY KEY,
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents >= 0)
);
~~~

File này thuộc **test resources**, không phải production database migrations. Trong integration test đặt `spring.sql.init.mode=always`, Spring Boot chạy script với PostgreSQL container đã kết nối qua `@ServiceConnection`. Production app nên dùng Flyway/Liquibase được quản lý riêng, không đặt schema test vào main resources.

**Vì sao có CHECK constraint?** Ma trận PostgreSQL không chỉ “connect được” mà còn kiểm các constraint/SQL semantics cần cho ứng dụng. Bài test còn kiểm uniqueness vi phạm để xác nhận Spring JDBC exception translation.

## 9. Test chứng minh đúng JDK và Spring Boot runtime

**src/test/java/com/example/matrix/RuntimeMatrixTest.java**

~~~java
package com.example.matrix;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootVersion;

import static org.junit.jupiter.api.Assertions.*;

class RuntimeMatrixTest {

    @Test
    void testWorkerReallyUsesSelectedJdk() {
        int expected = Integer.parseInt(
            System.getProperty("matrix.expectedJdk", "17"));

        int actual = Runtime.version().feature();

        System.out.printf(
            "JVM: expected=%d actual=%d vendor=%s%n",
            expected, actual,
            System.getProperty("java.vendor"));

        assertEquals(expected, actual);
    }

    @Test
    void resolvedSpringBootMatchesMatrixAxis() {
        String expected = System.getProperty(
            "matrix.expectedBoot", "3.3.5");

        String actual = SpringBootVersion.getVersion();

        System.out.printf(
            "Spring Boot: expected=%s actual=%s%n",
            expected, actual);

        assertEquals(expected, actual);
    }
}
~~~

### Vì sao điều này hữu ích?

Nếu CI job hiển thị `JDK 21` nhưng `Runtime.version().feature()` là 17, test **fail** thay vì lặng lẽ báo success. Nếu build plugin/BOM bị hardcode version cũ hoặc dependency classpath sai, `SpringBootVersion.getVersion()` có thể khác expected và test fail.

**Lưu ý:** Khi chạy bằng IDE không truyền `-PtestJdk` và system property, default assertion mong JDK 17. Nếu IDE dùng JDK 21, test sẽ fail có chủ ý vì test runner chưa được cấu hình theo ma trận. Đây là diagnostic, không phải lỗi của Spring Boot.

Kiểm ứng dụng **production** chạy JDK nào còn cần runtime/version evidence từ Docker base image/production telemetry; một test worker JVM không thể chứng minh deploy runtime bên ngoài CI.

## 10. Unit tests không phụ thuộc database/Redis

**src/test/java/com/example/matrix/PriceCalculatorTest.java**

~~~java
package com.example.matrix;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PriceCalculatorTest {

    @Test
    void calculatesIntegerCentsExactly() {
        assertEquals(
            3998L,
            PriceCalculator.totalCents(1999L, 2));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalCents(-1L, 2));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalCents(100L, 0));
    }

    @Test
    void detectsLongOverflowInsteadOfWrapping() {
        assertThrows(
            ArithmeticException.class,
            () -> PriceCalculator.totalCents(
                Long.MAX_VALUE, 2));
    }
}
~~~

Bốn tests này nên chạy nhanh ở mọi JDK trong support matrix, không cần Spring context. Nếu tất cả unit tests đều được gắn `@SpringBootTest`, CI sẽ tốn startup và có nguy cơ yêu cầu DB/Redis cho những phép tính thuần không cần chúng.

## 11. Integration tests dùng PostgreSQL/Redis từ matrix images

**src/test/java/com/example/matrix/ServiceMatrixTest.java**

~~~java
package com.example.matrix;

import java.time.Duration;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assertions;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@Tag("integration")
@Testcontainers
@SpringBootTest(
    classes = MatrixApplication.class,
    properties = "spring.sql.init.mode=always")
class ServiceMatrixTest {

    private static final String PG_IMAGE =
        System.getProperty(
            "matrix.postgres.image", "postgres:16.4");

    private static final String REDIS_IMAGE =
        System.getProperty(
            "matrix.redis.image", "redis:7.2.4");

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(
            DockerImageName.parse(PG_IMAGE));

    @Container
    @ServiceConnection(name = "redis")
    static final GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse(REDIS_IMAGE))
                .withExposedPorts(6379);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    StringRedisTemplate redisTemplate;

    private static String majorFromImage(String image) {
        String version = image.substring(
            image.lastIndexOf(':') + 1);
        return version.split("\\.")[0];
    }

    @Test
    void postgresqlIsReallyRequestedServerMajor() {
        String actual = jdbc.queryForObject(
            "SHOW server_version", String.class);

        assertNotNull(actual);
        String requestedMajor = majorFromImage(PG_IMAGE);

        System.out.printf(
            "PostgreSQL: image=%s actual=%s%n",
            PG_IMAGE, actual);

        assertTrue(
            actual.equals(requestedMajor)
                || actual.startsWith(requestedMajor + "."),
            "Connected to wrong PostgreSQL major");
    }

    @Test
    void jdbcRoundTripPreservesIntegerCents() {
        String marker = UUID.randomUUID().toString();

        int affected = jdbc.update(
            "INSERT INTO compat_probe " +
            "(marker, amount_cents) VALUES (?, ?)",
            marker, 1999L);

        assertEquals(1, affected);

        Long amount = jdbc.queryForObject(
            "SELECT amount_cents FROM compat_probe " +
            "WHERE marker = ?",
            Long.class, marker);

        assertEquals(1999L, amount);
    }

    @Test
    void postgresUniqueConstraintIsEnforced() {
        String marker = UUID.randomUUID().toString();

        jdbc.update(
            "INSERT INTO compat_probe " +
            "(marker, amount_cents) VALUES (?, ?)",
            marker, 1L);

        assertThrows(
            DuplicateKeyException.class,
            () -> jdbc.update(
                "INSERT INTO compat_probe " +
                "(marker, amount_cents) VALUES (?, ?)",
                marker, 2L));
    }

    @Test
    void redisIsReallyRequestedServerMajor() {
        Properties serverInfo = redisTemplate.execute(
            (RedisCallback<Properties>)
                connection -> connection.info("server"));

        assertNotNull(serverInfo);
        String actual = serverInfo.getProperty(
            "redis_version");

        assertNotNull(actual);
        String requestedMajor = majorFromImage(REDIS_IMAGE);

        System.out.printf(
            "Redis: image=%s actual=%s%n",
            REDIS_IMAGE, actual);

        assertTrue(
            actual.equals(requestedMajor)
                || actual.startsWith(requestedMajor + "."),
            "Connected to wrong Redis major");
    }

    @Test
    void redisRoundTripPreservesUnicodeAndTtl() {
        String key = "matrix:" + UUID.randomUUID();
        String value = "Tiếng Việt: đã đồng bộ 🌱";

        redisTemplate.opsForValue().set(
            key, value, Duration.ofMinutes(5));

        assertEquals(
            value, redisTemplate.opsForValue().get(key));

        Long ttl = redisTemplate.getExpire(
            key, TimeUnit.SECONDS);

        assertNotNull(ttl);
        assertTrue(ttl > 0L);

        assertTrue(Boolean.TRUE.equals(
            redisTemplate.delete(key)));
    }
}
~~~

### 11.1. Vì sao dùng @Container + @ServiceConnection?

- `@Container` và `@Testcontainers` để JUnit Testcontainers extension khởi động/dừng resources theo test class.
- `PostgreSQLContainer` là typed container; Spring Boot biết lấy JDBC connection details.
- Redis `GenericContainer` không có type-specific metadata, nên `@ServiceConnection(name="redis")` chỉ rõ server identity cho Boot.
- `withExposedPorts(6379)` cho Testcontainers mapping port tự động.
- Không dùng URL/port database từ environment cũ.
- `JdbcTemplate` và `StringRedisTemplate` được Spring Boot autoconfigure từ actual connections.
- Các assertions kiểm server version bằng query/command **thực**, không chỉ đọc property.

### 11.2. Dynamic image selection

`PG_IMAGE` và `REDIS_IMAGE` được đọc từ system properties tại lúc test class initialize. Gradle gửi values từ project properties `postgresImage`/`redisImage`, nên mỗi CI matrix job có thể khởi tạo versions riêng.

**Không truyền nguyên chuỗi image từ untrusted user input** vào pipeline có quyền cao. Định nghĩa tập versions đã được review trong workflow; ưu tiên images từ registry tin cậy và pin digest ở production/release certification.

### 11.3. Các assertions PostgreSQL bảo vệ gì?

1. **Server version đúng major:** tránh fake coverage nếu kết nối nhầm service.
2. **INSERT/SELECT round-trip:** JDBC driver, SQL dialect, table DDL và kiểu BIGINT hoạt động.
3. **Unique constraint:** PostgreSQL trả lỗi và Spring JDBC translate thành `DuplicateKeyException`.

Một số hành vi production cần mở rộng: `INSERT ... ON CONFLICT`, JSONB, UUID, timestamps with timezone, advisory locks, isolation levels, collations, indexes và migrations.

### 11.4. Các assertions Redis bảo vệ gì?

1. Redis server thực chạy đúng major từ image.
2. `StringRedisTemplate` lưu/đọc text Unicode qua codecs.
3. TTL khác không: expiration semantics hoạt động.
4. Cleanup key sau test, giảm rủi ro shared state ngay cả khi container reuse settings thay đổi.

Không coi các tests này đủ để kiểm Redis Cluster, ACL, TLS, failover/replication, eviction policy hoặc memory pressure. Những scenarios ấy cần harness riêng.

### 11.5. Nguy cơ Spring context cache và Testcontainers lifecycle

Trong demo, **chỉ một integration test class** khởi động containers nên ít rủi ro cached Spring context tham chiếu một container đã dừng sau khi class kết thúc. Nếu nhiều classes chia sẻ cùng Spring cache key nhưng mỗi class có container với lifecycle riêng, Spring có thể reuse context đã được tạo với connection details cũ. Khi production suite lớn, hãy thiết kế container lifecycle phù hợp context caching hoặc giữ test classes/context boundaries rõ; không coi static container fields từ các JVMs là shared service.

### 11.6. Tính độc lập của dữ liệu

Các tests tạo `UUID` cho PostgreSQL marker/Redis key. Không dùng hardcoded key “test-1” có thể bị các runs khác ghi đè. PostgreSQL container được dừng khi class kết thúc. Nếu mở reuse giữa jobs hoặc dùng một external shared DB, cần thêm cleanup và tenant/schema isolation policy.

## 12. Tổng số test và các tầng bắt buộc

Project có **11 phương thức `@Test`**:

| Test class | Số methods | Lớp |
| --- | ---: | --- |
| `RuntimeMatrixTest` | 2 | Assert JDK/Boot runtime |
| `PriceCalculatorTest` | 4 | Unit tests Java 17 |
| `ServiceMatrixTest` | 5 | PostgreSQL + Redis real integration |
| **Tổng** | **11** | JDK, Boot, server version và behavior |

Chạy `./gradlew test` sẽ thực thi **6 unit/runtime methods**, không yêu cầu Docker. Chạy `./gradlew integrationTest` thực thi **5 service methods**, cần Docker. Chạy `./gradlew check` sẽ chạy cả hai vì đã thiết lập dependency trong build.

Kết quả dự kiến nếu dependencies, Docker, image tags và JDK toolchains có sẵn: **6/6 unit + 5/5 integration PASS**. Đây là **kết quả kỳ vọng từ code**, không phải báo cáo đã thực thi thử trong phiên soạn tài liệu này. Thời gian download image và network conditions có thể khác máy.

### 12.1. Lệnh chạy bằng Gradle Wrapper

Unit baseline:

~~~bash
./gradlew test -PtestJdk=17 -PspringBootVersion=3.3.5
~~~

Unit runtime JDK 21 nhưng compile Java 17:

~~~bash
./gradlew test -PtestJdk=21 -PspringBootVersion=3.3.5
~~~

Candidate Spring Boot:

~~~bash
./gradlew test -PtestJdk=21 -PspringBootVersion=3.4.13
~~~

PostgreSQL 15 + Redis 7.2:

~~~bash
./gradlew integrationTest \
  -PtestJdk=17 \
  -PspringBootVersion=3.3.5 \
  -PpostgresImage=postgres:15.8 \
  -PredisImage=redis:7.2.4
~~~

PostgreSQL 17 + Redis 7.4:

~~~bash
./gradlew integrationTest \
  -PtestJdk=21 \
  -PspringBootVersion=3.4.13 \
  -PpostgresImage=postgres:17.0 \
  -PredisImage=redis:7.4.0
~~~

Windows PowerShell sử dụng `.\gradlew.bat` và viết toàn bộ flags trên một dòng hoặc dùng backtick line continuation của PowerShell theo đúng shell semantics. Không dùng backslash `\` làm line continuation trong PowerShell.

### 12.2. Xác minh toolchains

~~~bash
./gradlew -q javaToolchains
./gradlew --version
java --version
~~~

**Chú ý:** `java --version` ở shell chỉ nói JDK trên PATH, không bảo đảm test worker launcher. Vì thế bài có `RuntimeMatrixTest` kiểm `Runtime.version().feature()` trực tiếp trong test JVM.

### 12.3. Xem reports

~~~text
build/
├── reports/tests/
│   ├── test/index.html
│   └── integrationTest/index.html
└── test-results/
    ├── test/
    │   ├── TEST-com.example.matrix.RuntimeMatrixTest.xml
    │   └── TEST-com.example.matrix.PriceCalculatorTest.xml
    └── integrationTest/
        └── TEST-com.example.matrix.ServiceMatrixTest.xml
~~~

CI sẽ upload XML và HTML reports để phân biệt test fail, image pull fail, toolchain resolution fail và bean/context fail.

## 13. GitHub Actions: ma trận unit và dịch vụ phụ thuộc

**.github/workflows/compatibility-matrix.yml**

Workflow sau đây là một ví dụ đầy đủ với:

- Job `unit` chạy cartesian product **JDK 17/21 × Boot 3.3.5/3.4.13** = 4 jobs.
- Job `services` chỉ chạy 4 tổ hợp ưu tiên, không cố chạy toàn bộ 24 combinations mỗi PR.
- GitHub-hosted Ubuntu runner có Docker.
- `setup-java` cài cả JDK 17 và JDK job target, đảm bảo compiler toolchain 17 tìm được.
- Gradle Wrapper 8.8 dùng qua `./gradlew`.
- `fail-fast: false` giúp thu thập failures ở nhiều axes thay vì cancel hết khi job đầu thất bại.
- Artifacts có tên chứa tổ hợp giúp đối chiếu kết quả sau run.
- Không sử dụng service ports cố định trong YAML vì Testcontainers tự map ports.

~~~yaml
name: Spring Boot compatibility matrix

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  unit:
    name: Unit JDK ${{ matrix.jdk }} / Boot ${{ matrix.boot }}
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21']
        boot: ['3.3.5', '3.4.13']

    steps:
      - uses: actions/checkout@v4

      - name: Install compiler JDK 17 and test JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.jdk }}

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify JDK/Boot and Java business tests
        run: |
          ./gradlew test \
            -PtestJdk=${{ matrix.jdk }} \
            -PspringBootVersion=${{ matrix.boot }} \
            --no-daemon

      - name: Upload unit test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-jdk${{ matrix.jdk }}-boot${{ matrix.boot }}
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore

  services:
    name: Services JDK ${{ matrix.jdk }} / Boot ${{ matrix.boot }} / PG ${{ matrix.postgres }}
    runs-on: ubuntu-24.04
    timeout-minutes: 40

    strategy:
      fail-fast: false
      matrix:
        include:
          - jdk: '17'
            boot: '3.3.5'
            postgres: 'postgres:15.8'
            redis: 'redis:7.2.4'
          - jdk: '17'
            boot: '3.3.5'
            postgres: 'postgres:16.4'
            redis: 'redis:7.2.4'
          - jdk: '21'
            boot: '3.3.5'
            postgres: 'postgres:16.4'
            redis: 'redis:7.4.0'
          - jdk: '21'
            boot: '3.4.13'
            postgres: 'postgres:17.0'
            redis: 'redis:7.4.0'

    steps:
      - uses: actions/checkout@v4

      - name: Install JDKs for Gradle and tests
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.jdk }}

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify real PostgreSQL and Redis versions
        run: |
          ./gradlew integrationTest \
            -PtestJdk=${{ matrix.jdk }} \
            -PspringBootVersion=${{ matrix.boot }} \
            -PpostgresImage=${{ matrix.postgres }} \
            -PredisImage=${{ matrix.redis }} \
            --no-daemon

      - name: Upload integration test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: services-jdk${{ matrix.jdk }}-boot${{ matrix.boot }}-pg${{ matrix.postgres }}-redis${{ matrix.redis }}
          path: |
            build/reports/tests/integrationTest/
            build/test-results/integrationTest/
          if-no-files-found: ignore
~~~

### 13.1. Vì sao không dùng GitHub Actions service containers?

GitHub Actions hỗ trợ `jobs.<job_id>.services` với images/ports, phù hợp khi service lifecycle được quản lý ở mức job. Trong bài này, Testcontainers **gắn trực tiếp mỗi server version với Java test** và sinh host port động; khi đổi matrix image, Java code khởi tạo container version tương ứng. Không kết hợp đồng thời Actions service PostgreSQL và Testcontainers PostgreSQL mà thiếu lý do, tránh vô tình test sai server.

### 13.2. Vì sao hai nhóm jobs?

**Unit** kiểm Java runtime + Spring Boot BOM/Boot version axis mà không khởi động Docker. **Services** kiểm biến thể server thật. Nếu gộp thành một product lớn, chi phí CI tăng nhanh và lỗi đơn giản mất nhiều thời gian chờ.

### 13.3. Nếu một tổ hợp không hợp lệ

Ví dụ Spring Boot candidate chưa hỗ trợ JDK target, hoặc JDBC driver không hỗ trợ server major. Đừng để job fail “đương nhiên” mà không có chủ đích. Có thể dùng `matrix.exclude` hoặc các `include` chọn lọc, nhưng ghi nguyên nhân trong support policy/decision record.

### 13.4. Pin Actions và Docker digests

Major tags (`checkout@v4`, `setup-java@v6`, `setup-gradle@v6`) là ví dụ. Trong repository production, kiểm chính sách supply-chain; ưu tiên pin GitHub Actions theo **full immutable commit SHA** đã được review và cập nhật định kỳ.

Docker image tag như `postgres:16.4` là phiên bản dễ hiểu nhưng registry tags về nguyên tắc có thể thay đổi theo thời gian; release certification nên ghi **resolved image digest** và khi cần pin `image@sha256:...`. Không tự chế một digest trong tài liệu. Version list trong workflow là **historical sample**, không có nghĩa các patch ấy vẫn đạt security policy hiện hành.

## 14. Nightly/full matrix và release gate

Một full product có thể chạy vào lịch đêm để giảm PR latency:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    jdk: ['17', '21']
    boot: ['3.3.5', '3.4.13']
    postgres: ['postgres:15.8', 'postgres:16.4', 'postgres:17.0']
    redis: ['redis:7.2.4', 'redis:7.4.0']
~~~

Đây là snippet của **job strategy**, không phải workflow độc lập. Nó sinh **24 combinations** nếu không exclude. Cần thêm trigger schedule, resources, test invocation, Docker và artifacts tương tự workflow đầy đủ phần 13.

Khi triển khai thật:

- PR: chạy bắt buộc trên các combinations quan trọng nhất.
- Nightly: chạy rộng để phát hiện server-version drift sớm.
- Release: chạy **toàn bộ officially supported combinations** hoặc chứng minh các exceptions đã duyệt.
- Experimental: có thể tách non-blocking job, không dùng nó để phủ định failed required gate.
- Lưu results theo tuple và artifact digest, không chỉ một status “green”.

### 14.1. Fail-fast=false không có nghĩa bỏ qua lỗi

GitHub Actions `strategy.fail-fast: false` chỉ **không hủy các matrix jobs còn lại** khi một job fail. Mỗi job vẫn báo FAILED, tổng pipeline/release gate vẫn phản ánh status. Nếu muốn một experimental job non-blocking, phải dùng policy riêng được duyệt; không đặt `continue-on-error: true` cho cả matrix rồi báo tất cả đều thành công.

### 14.2. Khi nào ghép matrix.exclude?

Để loại một tổ hợp không được hỗ trợ theo chính sách. Ví dụ JDK version quá mới với Boot cũ. Điều quan trọng là **định nghĩa support policy trước** và ghi rõ lý do exclude. Một `exclude` vô tình vì test fail không phải cách sửa compatibility.

## 15. Không nhầm version request với actual version

Một bài test chỉ đọc:

~~~java
String expected = System.getProperty(
        "matrix.postgres.image");
assertTrue(expected.startsWith("postgres:"));
~~~

không chứng minh server đã kết nối là PostgreSQL version đó. Bài lab **query server** qua JDBC và Redis INFO. Trong dự án thật, báo cáo CI nên chứa:

~~~text
Matrix tuple:
  compile target: Java 17
  test runtime JVM: 21.0.x / Temurin
  Spring Boot runtime: 3.4.13
  Gradle wrapper: 8.8
  PostgreSQL image: postgres:17.0 (resolved digest recorded)
  PostgreSQL server: 17.0
  Redis image: redis:7.4.0 (resolved digest recorded)
  Redis server: 7.4.0
  Test count: 6 unit + 5 integration
  Outcome: PASS/FAIL with JUnit XML artifacts
~~~

**Đây là cấu trúc report minh họa**, không phải kết quả test đã chạy. Version details nên lấy từ runtime/log/driver metadata thực, không điền cứng từ YAML cho trường “actual”.

### 15.1. Gradle task UP-TO-DATE có thể đánh lừa

Nếu Test task trả `UP-TO-DATE`/`FROM-CACHE`, trong invocation ấy tests có thể không được thực thi. Khi benchmark version compatibility, điều đó làm nhầm “đã kiểm service version mới”. Gradle Test task sẽ coi system properties có thể là task inputs khi khai báo đúng, nhưng để certification/debug chắc chắn, có thể chạy:

~~~bash
./gradlew test integrationTest --rerun-tasks
~~~

Đừng coi Gradle build cache artifact là Spring TestContext cache. Context cache là đối tượng sống trong **test worker JVM**, không tái sử dụng qua một CI job mới.

### 15.2. Chặn stale test reports

Nếu báo cáo cũ còn trong workspace, một bước artifact upload có thể thu JUnit XML cũ. Dùng clean workspace trên CI hoặc `./gradlew clean test integrationTest` khi certification yêu cầu, và kiểm timestamps/run IDs. Không chạy destructive clean trên user workspace khi không được phép; workflow clean chỉ áp dụng trong CI-owned checkout.

### 15.3. Đừng report “version supported” chỉ vì class loads

Một Kafka client có thể kết nối broker nhưng không đọc/commit offsets đúng. Một PostgreSQL JDBC connection thành công không chứng minh migrations/JSONB/locks. Một Redis PING pass không chứng minh TTL/serialization/ACL. Ma trận phải chạy **representative contracts** của service, không chỉ smoke connect.

## 16. Những nhóm hành vi cần kiểm cho PostgreSQL

| Nhóm | Bài test tiêu biểu | Vì sao khác server version |
| --- | --- | --- |
| DDL/migration | Flyway/Liquibase migrations chạy trên DB mới/cũ | Syntax/constraint support |
| SQL queries | Derived query/JPQL/native SQL thật | Dialect/functions khác |
| Types | UUID, JSONB, DECIMAL, timestamp tz | Driver mapping/casts |
| Constraints | Unique, FK, CHECK, NOT NULL | Error/transaction semantics |
| Transactions | Commit/rollback, isolation, deadlocks | Locking/transaction behavior |
| Pagination | ORDER BY stable, cursor | Collation/null ordering |
| Performance | Explain/representative workload | Planner/index stats thay đổi |
| Security | TLS, roles/schema permissions | Managed-service settings |
| Migrations rollback | App v1/v2 cùng DB khi rolling upgrade | Expand-contract compatibility |

Lab runnable dùng DDL, JDBC round-trip và duplicate key để minh họa. Với Spring Data JPA/Hibernate production, cần mở rộng sang actual entity mappings, converters, native SQL, locking và migrations.

### Không dùng H2 thay thế mọi PostgreSQL matrix

H2 tiện cho unit/slice tests, nhưng khác SQL dialect và transactional behavior. Test repository chạy với H2 chỉ chứng minh H2 scenario. Dùng Testcontainers PostgreSQL hoặc một PostgreSQL sandbox đúng version khi cần compatibility evidence.

## 17. Những nhóm hành vi cần kiểm cho Redis

| Nhóm | Bài test tiêu biểu |
| --- | --- |
| Encoding | String/JSON/byte-array round-trip |
| TTL | EXPIRE/PEXPIRE semantics và delete |
| Atomic commands | INCR/SETNX/transactions nếu nghiệp vụ dùng |
| Locks | SET NX PX và release an toàn |
| Streams | XADD/XREADGROUP/ack nếu dùng |
| Pub/Sub | Subscribe/receive |
| Cluster | Redirect/MOVED/ASK, slot distribution |
| ACL/TLS | Auth/permissions/secure connection |
| Eviction | maxmemory policies |
| Failure recovery | Reconnect/timeouts/failover |

Lab kiểm version, Unicode và TTL, không tuyên bố kiểm Cluster/HA. Khi ma trận Redis major đổi, thêm negative test cho command không còn hỗ trợ và serialization migration.

## 18. Kafka/RabbitMQ và versioned brokers

Nếu hệ thống thực dùng Kafka, thêm axis cho **broker release** và **Kafka client version** do Boot BOM quản lý. Những behaviors quan trọng:

- Topic creation/admin permissions;
- producer key/value serializer, headers và timestamp;
- acks/idempotent producer/transactions;
- consumer group assignment/rebalance;
- offset commit/seek/replay;
- error handlers, retries và dead-letter topics;
- schema registry/Avro/Protobuf versions;
- message ordering theo partitions;
- broker/client protocol compatibility;
- TLS/SASL/ACL.

Spring Kafka tests có thể dùng `@EmbeddedKafka` để kiểm một subset, nhưng với broker-version compatibility nên dùng Testcontainers hoặc môi trường Kafka được quản lý theo **đúng broker image**. Mỗi broker cluster có bootstrap addresses động, không hardcode `localhost:9092`.

Với RabbitMQ, cần kiểm confirm/nack, dead-letter exchanges, queue arguments và retry semantics. Cùng tên message/event không có nghĩa protocol/header behavior giống nhau giữa versions.

### Vì sao không thêm luôn Kafka vào runnable project?

Mục tiêu là dạy cấu trúc ma trận và **hai server-version axes thực sự có assertions**. Thêm Kafka Testcontainers sẽ làm tăng startup, images và code mà không bổ sung một kỹ thuật CI mới. Khi sản phẩm có Kafka, áp dụng lại pattern: pin image, connect dynamically, query/verify capabilities thật, chạy consumer/producer contract suite. Không thêm service không được dùng chỉ để ma trận có nhiều cột.

## 19. Test isolation và concurrency trong matrix

Mỗi GitHub Actions matrix job thường chạy trên runner riêng; Docker Testcontainers có lifecycle theo job/JVM. Tuy vậy:

- Các test methods trong một job có thể chạy song song;
- nhiều Gradle forks có thể khởi động nhiều containers riêng;
- test classes dùng chung `@SpringBootTest` context cache có thể giữ connection details của container đã dừng;
- external staging DB dùng chung giữa jobs vẫn có thể collide;
- hardcoded ports, usernames, database names và keys có thể trùng;
- Kafka topics và Redis keys có thể rò giữa tests.

Lab dùng `maxParallelForks=1` cho integration task, random UUID keys và Testcontainers ephemeral ports. Điều đó giảm rủi ro nhưng không tự dọn mọi loại external resource trên production.

### @ServiceConnection vs @DynamicPropertySource

Spring Boot service connections tạo `ConnectionDetails` phù hợp cho auto-configuration. `@DynamicPropertySource` hữu ích khi service không có factory hoặc phải cung cấp custom properties. Không cùng lúc cấu hình connection properties từ env và `@ServiceConnection` rồi kỳ vọng giá trị bất kỳ thắng; hãy hiểu precedence của ConnectionDetails và assert actual server.

### Spring context caching có thể làm test dùng sai service

Nếu nhiều test classes dùng chung context cache key nhưng container lifecycle kết thúc sau từng class, cached context có thể giữ URL/bean của một container cũ. Khi cần reuse, dùng container lifecycle nhất quán với Spring context hoặc phân tách contexts. Trong multi-fork builds, mỗi worker có context cache riêng; không có shared cache giữa JVMs.

## 20. Nâng Spring Boot: kiểm migration chứ không chỉ compile

Một upgrade Boot có thể đổi:

- Spring Framework annotations/conditional logic;
- Jackson serialization/deserialization defaults;
- Hibernate dialect/schema generation;
- Spring Data repository behavior;
- Micrometer metrics;
- Security filter defaults;
- actuator endpoint behavior;
- Testcontainers/JUnit/Mockito versions;
- embedded Tomcat/Jetty/Netty;
- configuration property deprecations;
- JDBC driver/Lettuce/Kafka client dependencies.

### Migration plan

1. Xác định baseline Boot, candidate và support policy.
2. Đọc migration/release notes chính thức.
3. Tạo branch upgrade và thay Boot version bằng property quản lý tập trung.
4. Chạy compilation/unit tests trên JDK baseline.
5. Chạy Spring Boot context startup và integration tests trên service versions đang deployed.
6. Chạy candidate trên JDK LTS tiếp theo nếu hỗ trợ.
7. So resolved dependencies và log warnings/deprecations.
8. Kiểm HTTP/JSON contracts, database migrations, security và observability.
9. Chạy staging/canary với workload đại diện.
10. Chuẩn bị rollback khi service/data schema mới không tương thích với app cũ.

**Không coi việc sửa test theo behavior mới là hợp lệ nếu client/DB contract cũ chưa được migration.** Ma trận cần bắt regression, không tự làm xanh mọi combination.

## 21. Nâng JDK: source compatibility vs runtime behavior

### 21.1. Classfile level

Java 17 thường tạo classfile major version **61** khi compile target Java 17; Java 21 classfile major **65**. JVM 17 không chạy classfile 65. Do đó có hai chiều khác nhau:

- Java 17 bytecode trên JDK 21: thông thường có thể kiểm.
- Java 21 bytecode trên JDK 17: không được hỗ trợ.

`java.toolchain=17` trong lab cố định bytecode target 17, trong khi `Test.javaLauncher` có thể là 17/21. Đây là một **runtime compatibility** matrix, không phải matrix language features.

### 21.2. Các lỗi khi chạy runtime mới

Các thư viện reflection/proxy/bytecode như Hibernate, Byte Buddy, Mockito và một số agents có thể cần version mới để hỗ trợ JDK mới. Kiểm cả:

- `@SpringBootTest` context startup;
- CGLIB/JDK dynamic proxy/AOP;
- Jackson JavaTime records/sealed classes;
- TLS/truststore/cipher configuration;
- timezone/locale/charset;
- performance/GC/virtual threads nếu bật;
- native libraries/JNI;
- Java module encapsulation.

Đừng dùng `--add-opens` rộng chỉ để test pass mà không hiểu nguyên nhân. Nếu thư viện chưa hỗ trợ JDK, nâng dependency phù hợp hoặc chặn unsupported combination theo policy.

### 21.3. JDK vendor/architecture axis

Hai JDK có cùng major nhưng vendor/build patch khác nhau vẫn có thể khác về certificates, cryptography policies, container memory detection hoặc native libs. Nếu sản phẩm có yêu cầu Temurin/Corretto/Zulu hoặc amd64/arm64, thêm trục vendor/arch **có lý do**, không mặc định multiply toàn bộ matrix.

## 22. Đo chi phí và độ ổn định CI

Một bảng benchmark hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Matrix tuple | JDK, Boot, PG, Redis, runner OS |
| Gradle Wrapper version | Cố định build engine |
| Resolved BOM/dependency versions | Bằng chứng runtime classpath |
| Docker image digest | Bằng chứng service artifact |
| Actual server versions | Tránh fake coverage |
| Test count/pass/fail/skipped | Bằng chứng suite đã chạy |
| CI wall-clock p50/p95 | Hiệu quả feedback |
| Cold image pull time | Tách khỏi test logic |
| Container startup time | Phân biệt Docker registry/daemon vấn đề |
| JVM heap/GC/CPU | Chi phí runtime |
| DB connections | External resource capacity |
| Flaky rate per tuple | Chất lượng test |
| Support status | Required/experimental/deprecated |

Không kết luận “JDK21 nhanh hơn” từ một CI job với image cached và một job khác vừa cold-download PostgreSQL. Đo nhiều runs hoặc tách warm/cold measurements.

### Lợi ích của artifact names có tuple

Nếu một integration test fail chỉ ở **Boot 3.4 + JDK 21 + PostgreSQL 17**, artifact name chứa tuple giúp phân biệt với lỗi xuất hiện đồng loạt ở mọi version. Khi triage, cần nhìn **first failing assertion/root cause**, không chỉ trạng thái job.

### Quản lý chi phí

- PR smoke giữ 4–8 jobs trọng tâm.
- Nightly chạy ma trận rộng; có thể dùng reusable workflows.
- Group Docker pulls bằng registry caches nếu policy cho phép.
- Dùng `max-parallel` để giới hạn số concurrent matrix jobs khi registry/CI budget bị quá tải.
- Chạy unit jobs sớm; integration jobs sau hoặc song song tùy feedback goals.
- Tách slow load/performance benchmark khỏi functional matrix.
- Không skip required jobs khi chạy release.

## 23. Triaging lỗi theo trục

| Triệu chứng | Khả năng | Bước đầu |
| --- | --- | --- |
| Mọi combo fail cùng test | Regression logic/test fixture | Kiểm commit và unit tests |
| Chỉ JDK 21 fail | Reflection/bytecode/agent/runtime behavior | Kiểm actual JVM, dependency support |
| Chỉ Boot candidate fail | Auto-config/BOM/Framework behavior | Diff resolved dependencies, migration notes |
| Chỉ PostgreSQL 17 fail | SQL/migration/driver/server semantics | Query version, SQLState, server logs |
| Chỉ Redis 7.4 fail | Command/serialization/ACL change | Redis INFO, client logs |
| Chỉ job CI fail khi local pass | Docker/permissions/ports/toolchains | Runner evidence, Docker info |
| Fail trước tests | Gradle plugin/toolchain resolution | Kiểm wrapper, JDK installations |
| Integration test không phát hiện | Tag/filter/task misconfig | Kiểm JUnit reports 5 tests |
| Kết quả DB giống nhau ở mọi image tag | Có thể connect nhầm external DB | SHOW server_version và ConnectionDetails |
| Tests UP-TO-DATE | Gradle bỏ qua task | --rerun-tasks/certification workflow |
| Docker pull rate limit | Registry issue | Retry có giới hạn, mirrors có kiểm soát |
| Testcontainers cannot find Docker | Runner không có daemon/socket | Kiểm Docker availability |
| SQL schema không được tạo | spring.sql.init.mode/schema resource | Kiểm startup SQL init logs |
| JDK property đúng nhưng Runtime.version sai | javaLauncher/JAVA_HOME mismatch | Kiểm Test.javaLauncher |
| Boot property đúng nhưng runtime Boot khác | BOM/plugin hardcoded/mixed classpath | SpringBootVersion + dependencyInsight |
| Rất nhiều containers startup | JUnit/Gradle forks × Testcontainers | Giảm forks, kiểm lifecycle |
| Tests chỉ fail trong parallel | Shared test data/ports/connections | Unique resources/isolation |
| Chỉ Windows fail | Path/line endings/permissions | Thêm OS dimension khi supported |

### Root cause trước khi retry

Nếu job PostgreSQL 17 fail vì SQL syntax, rerun ba lần sẽ không chữa. Nếu image pull fail do transient network, retry có giới hạn có thể hợp lý. Dùng **error category** để quyết định retry; không đặt unconditional retries cho assertions để che incompatibility.

### Không tự bỏ hết assertions để “support JDK mới”

Tương thích nghĩa là giữ hành vi đã công bố. Nếu business calculation khác trên JDK mới hoặc driver exception không được translate đúng, đó là finding thực. Cần sửa app/test expectations theo hợp đồng và review, không tự xóa test case fail.



## 24. Mở rộng sang GitLab CI và Jenkins

Workflow GitHub Actions không phải cách duy nhất dựng matrix. Trên GitLab CI có `parallel:matrix` để tạo jobs theo variables, script chạy Gradle Wrapper với flags tương ứng. Trên Jenkins declarative pipeline có `matrix { axes { ... } }` hoặc scripted combinations.

### GitLab CI example (snippet)

~~~yaml
compatibility:
  image: eclipse-temurin:17-jdk
  parallel:
    matrix:
      - TEST_JDK: ["17", "21"]
        BOOT_VERSION: ["3.3.5", "3.4.13"]
  script:
    - ./gradlew test
      -PtestJdk=$TEST_JDK
      -PspringBootVersion=$BOOT_VERSION
~~~

Đây là **snippet cấu trúc**, không phải runnable CI job khi không có Docker/JDK21 toolchain. Image Temurin 17 chỉ cài JDK 17; để chạy `-PtestJdk=21`, runner phải có thêm JDK 21 hoặc cấu hình provisioning toolchain phù hợp. Khi dùng GitLab container runner để chạy Testcontainers, cần Docker-in-Docker/socket được cấp quyền có kiểm soát.

### Jenkins example (snippet)

~~~groovy
pipeline {
    agent any
    stages {
        stage('Compatibility') {
            matrix {
                axes {
                    axis {
                        name 'TEST_JDK'
                        values '17', '21'
                    }
                    axis {
                        name 'BOOT_VERSION'
                        values '3.3.5', '3.4.13'
                    }
                }
                stages {
                    stage('Unit') {
                        steps {
                            bat '.\\gradlew.bat test -PtestJdk=%TEST_JDK% -PspringBootVersion=%BOOT_VERSION%'
                        }
                    }
                }
            }
        }
    }
}
~~~

Đây là **ví dụ Windows Jenkins agent** sử dụng `bat`. Agent cần cài JDK 17/21 và Gradle Wrapper có quyền chạy. Với Linux agent, thay `bat` bằng `sh` và syntax shell. Không copy snippet Jenkins này vào GitHub Actions YAML.

### Điểm chung

Dù CI system khác nhau, cần bảo vệ:

- Matrix tuple được truyền vào Gradle/Test JVM;
- Actual runtime versions được assert;
- Service containers/ports được cô lập;
- Errors và artifacts gắn với tuple;
- Required vs experimental jobs rõ;
- Secrets tối thiểu; image dependencies trusted;
- Retry policy không che lỗi tương thích.

## 25. Testcontainers không thay được managed-service compatibility

Một official `postgres` container không giống hoàn toàn một managed PostgreSQL instance có extensions, parameter groups, read replicas, backup/restore và TLS/role policies. Redis Cluster/Sentinel cũng khác Redis standalone trong lab.

Với production managed-service upgrades:

1. Chạy basic compatibility matrix bằng Testcontainers.
2. Chạy migrations và representative data fixtures.
3. Có sandbox cloud env dùng cấu hình tương đương production.
4. Kiểm TLS/auth, network policies và timeout behavior.
5. Kiểm compatibility với phiên bản client/driver và rolling upgrades.
6. Đo query plans/performance nếu có SQL workloads lớn.
7. Chạy canary và theo dõi error rate/latency.
8. Chuẩn bị rollback và data migration strategy.

Không dùng một JDBC INSERT/SELECT pass làm chứng cứ mọi failover/performance constraint production sẽ pass.

## 26. Policy nâng phiên bản và xử lý EOL

Một ma trận cần được bảo trì liên tục:

- Ghi một **version support policy** kèm owner.
- Theo dõi JDK LTS, Spring Boot maintenance windows, PostgreSQL/Redis/Kafka vendor EOL.
- Khi một major mới xuất hiện, thêm **experimental** lane trước.
- Khi candidate đã đủ kiểm chứng, thêm vào required CI.
- Khi một version EOL, lập migration plan cho clients đang dùng trước khi bỏ job.
- Cập nhật Docker image **patch/digest** để nhận fixes, giữ reproducible artifact evidence.
- Kiểm supply-chain của GitHub Actions và Gradle Wrapper.
- Ghi resolved dependency graph khi Boot BOM đổi.
- Giữ data migrations compatible trong rolling deployment/rollback window.
- Sau release, audit failures theo matrix tuple; đừng để nightly đỏ kéo dài rồi bị phớt lờ.

**Cảnh báo:** Những versions nêu trong lab là các bản cụ thể để code minh họa có thể tái lập, không phải danh sách vendor support “mới nhất”. Phải đối chiếu tài liệu chính thức tại thời điểm release, không dựa vào bài học để kết luận một version còn nhận security patches.

## 27. Những lỗi thiết kế thường gặp

### Lỗi 1: Chỉ đổi JAVA_HOME nhưng không đổi Test.javaLauncher

JDK test vẫn có thể là Java 17 do toolchain mặc định. **Sửa:** cấu hình `javaLauncher` và assert `Runtime.version().feature()`.

### Lỗi 2: Đổi Spring Boot plugin version, bỏ quên BOM

Lúc build có thể kéo mixed versions. **Sửa:** quản lý plugin/BOM theo cùng property và đối chiếu resolved dependency graph.

### Lỗi 3: Mọi combo trỏ tới localhost:5432

Không biết server version nào được kiểm, có thể connect nhầm developer DB. **Sửa:** dùng Testcontainers/@ServiceConnection và `SHOW server_version`.

### Lỗi 4: Dùng H2 làm bằng chứng PostgreSQL compatibility

Dialect khác. **Sửa:** chạy PostgreSQL thật trong container cho integration contract.

### Lỗi 5: Chỉ ping Redis mà không kiểm TTL/serialization

Connection success không bảo đảm behavior. **Sửa:** test representative commands và version bằng `INFO server`.

### Lỗi 6: Ma trận cartesian quá lớn cho mỗi PR

Feedback chậm và tốn credits. **Sửa:** core smoke + nightly extended + release certification.

### Lỗi 7: Exclude mọi combo từng fail

Một ma trận toàn pass nhưng bỏ unsupported/failed versions âm thầm không đáng tin. **Sửa:** có documented compatibility decision và migration/sunset plan.

### Lỗi 8: Dùng tags “latest”

Kết quả không tái lập giữa hai runs. **Sửa:** pin patch tags và resolved SHA256 digest cho certification.

### Lỗi 9: Chạy Docker với đặc quyền quá rộng

CI Testcontainers cần Docker access nhưng không cần expose production credentials. **Sửa:** dùng ephemeral runners/quyền tối thiểu, trusted images, không cho untrusted PR control privileged build secrets.

### Lỗi 10: Tất cả jobs dùng chung database schema

Tests race và cleanup xóa data của nhau. **Sửa:** per-job containers và unique IDs/schemas.

### Lỗi 11: @SpringBootTest quá nhiều

Unit test logic đơn giản mất thời gian startup. **Sửa:** phân loại unit vs integration; dùng JUnit thuần khi không cần Spring.

### Lỗi 12: Testcontainers container kết thúc nhưng Spring context vẫn cache

Lần sau bean kết nối cũ. **Sửa:** đồng bộ lifecycle của containers và contexts; tránh cross-class reuse không phù hợp.

### Lỗi 13: Coi một job canceled là pass

`fail-fast` hoặc timeout có thể khiến không có coverage cho tổ hợp. **Sửa:** bắt buộc report trạng thái chạy đủ; canceled/not-run là coverage gap.

### Lỗi 14: Tests được filter nhầm

`ServiceMatrixTest` mang tag integration nhưng Gradle `test` exclude; nếu không chạy `integrationTest`, chưa có service coverage. **Sửa:** CI release gate phải gọi task đúng và kiểm JUnit test count.

### Lỗi 15: Không gắn report với combination

Khó biết lỗi thuộc JDK, Boot hay DB. **Sửa:** artifact names/manifest gồm tuple và actual versions.

## 28. Hướng mở rộng bài tập

**Bài A — JDK runtime:** Chạy `testJdk=17`, rồi `testJdk=21`. In `Runtime.version()` và xác minh compiler vẫn target Java 17.

**Bài B — sai launcher:** Xóa `javaLauncher` trong branch thử nghiệm; quan sát job “JDK21” có thể fail runtime assertion khi tests thực chạy 17.

**Bài C — Boot candidate:** Chạy `springBootVersion=3.4.13` và so dependencyInsight với 3.3.5. Phân loại những artifacts đổi version do BOM.

**Bài D — PostgreSQL:** Chạy `postgres:15.8`, `16.4` và `17.0`, kiểm `SHOW server_version` khớp major.

**Bài E — Redis:** Chạy Redis 7.2.4 và 7.4.0, kiểm `INFO server` và Unicode/TTL behavior.

**Bài F — schema migration:** Thêm Flyway và tạo migration dùng PostgreSQL-specific SQL; test nhiều server versions trước rollout.

**Bài G — JDBC exception:** Xóa unique constraint trong test schema và xác nhận duplicate test đỏ.

**Bài H — money precision:** Đổi `amount_cents` BIGINT thành DECIMAL, kiểm JDBC Java mapping và nguyên tắc không dùng floating point cho tiền.

**Bài I — context cache:** Chạy integration class với Gradle forks=2 và kiểm có tạo container lặp; phân biệt JVM/process context cache.

**Bài J — CI cost:** Tính số job của 2 JDK × 3 Boot × 4 PG × 2 Redis, chọn pairwise + high-risk combinations để giảm PR latency.

**Bài K — nightly:** Viết scheduled workflow chạy full supported matrix và upload JUnit XML theo tuple.

**Bài L — image digest:** Resolve/tag một official PostgreSQL image đã được phê duyệt rồi pin digest trong release certification, ghi digest vào report.

**Bài M — JDK vendor:** Thêm Temurin và Corretto trên JDK 21 ở experimental lane, không thay required JDK major coverage.

**Bài N — Kafka:** Thêm Kafka Testcontainers, kiểm produce/consume, offset commits trên hai broker versions; đối chiếu client versions do Boot BOM.

**Bài O — Redis Cluster:** Tạo integration harness với cluster/failover, không kết luận standalone Redis tests đủ.

**Bài P — security:** Tạo bản Spring Boot candidate có dependency vulnerability fix, kiểm compatibility cùng SBOM/dependency scan.

**Bài Q — backward compatibility:** Chạy app v1/v2 trên cùng PostgreSQL schema migration đã mở rộng, kiểm rolling upgrade.

**Bài R — Windows CI:** Thêm một Windows unit lane; test JDK/Boot vẫn chạy nhưng Testcontainers cần Docker availability phù hợp runner.

**Bài S — observability:** Lưu versions runtime, server versions, image digests, elapsed time và flaky count vào artifacts.

**Bài T — failure injection:** Tạo sai PostgreSQL image tag; kiểm pipeline fail thật, không tự skip integration.

**Bài U — dependency locking:** Bật Gradle dependency locking phù hợp repo, kiểm diff locks khi đổi Spring Boot BOM.

**Bài V — report:** Đọc JUnit XML xác nhận đúng 6 unit + 5 integration; không tuyên bố tested chỉ vì CI steps tồn tại.

## 29. Checklist trước khi merge một thay đổi ma trận

- [ ] Ma trận bám vào versions thực sự được sản phẩm hỗ trợ?
- [ ] JDK baseline và next LTS đã được xác nhận theo Boot/Gradle support?
- [ ] Gradle Wrapper version được pin và hỗ trợ JDK dùng chạy Gradle?
- [ ] Java compiler/toolchain level và test JVM level được phân biệt?
- [ ] Test.javaLauncher được cấu hình đúng axis?
- [ ] Runtime.version().feature() assert JVM thật?
- [ ] SpringBootVersion.getVersion() assert Boot runtime thật?
- [ ] BOM dependency graph theo Boot candidate, không mixed versions ngoài ý muốn?
- [ ] Spring Cloud release train (nếu có) tương thích Boot?
- [ ] Services được chạy trên versioned images/server instances thật?
- [ ] PostgreSQL/Redis actual server major được query/assert?
- [ ] Không dùng localhost hardcode hay shared production DB?
- [ ] Có representative SQL/cache behavior tests, không chỉ connect/PING?
- [ ] JDBC driver/Lettuce/Kafka clients resolved versions được ghi nhận?
- [ ] Container lifecycle phù hợp Spring context caching?
- [ ] Testcontainers startup/cleanup/ports an toàn khi CI matrix song song?
- [ ] Unit test không cần Docker được tách khỏi integration tests?
- [ ] Tags Gradle lọc đúng; CI thực sự chạy integrationTest?
- [ ] JUnit report có số test methods đúng?
- [ ] CI có timeout phù hợp và artifacts khi failure?
- [ ] Không có untrusted images/actions hay excessive permissions?
- [ ] Docker images được pin patch/digest theo release policy?
- [ ] PR smoke, nightly extended và release certification tách rõ?
- [ ] Không âm thầm exclude unsupported/failed combos?
- [ ] Mỗi required tuple có PASS/FAIL thực, không counted skipped/canceled?
- [ ] Có review định kỳ vendor EOL/security advisories?
- [ ] Có migration/rollback plan khi nâng DB/Boot major?
- [ ] Đã đo wall-clock/CPU/heap/DB connections/trunk CI cost?
- [ ] Logs và artifacts không chứa secrets/passwords/PII?
- [ ] Không tuyên bố “tested” khi chỉ soạn code mà chưa thực thi?

## 30. Tài liệu tham khảo chính thức

Các nguồn chính giúp xác minh tính đúng của ma trận (version support có thể thay đổi theo thời điểm):

- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java minimum/maximum, Gradle support.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, `ConnectionDetails`, Redis/typed containers.
- [Spring Boot 3.3 — Testing Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, slices và test lifecycle.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test launcher separation.
- [Gradle — Plugin Version Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin versions qua gradle.properties/pluginManagement.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test task, Java launcher, filtering và test outputs.
- [Gradle — Working with Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html): dependency resolution/platforms.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): pin resolved dependencies.
- [Testcontainers — Java Guide](https://java.testcontainers.org/): JUnit 5, PostgreSQL module, Docker image names/lifecycle.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer.
- [GitHub Actions — Matrix Strategy](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs): include/exclude/fail-fast.
- [GitHub Actions — Build Java with Gradle](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-gradle): setup-java, setup-gradle, Wrapper.
- [GitHub Actions setup-java](https://github.com/actions/setup-java): install JDK versions and expose Java home variables.
- [Gradle Actions — setup-gradle](https://github.com/gradle/actions): Gradle caching/wrapper validation.
- [PostgreSQL — Versioning Policy](https://www.postgresql.org/support/versioning/): PostgreSQL majors/minors, maintenance/EOL.
- [Redis — Documentation](https://redis.io/docs/latest/): server commands/versioning.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): clients, broker behavior và protocol.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud): Boot/Cloud support alignment.

**Ghi nhớ:** Ma trận JDK, Spring Boot và service versions là một **hợp đồng kiểm chứng triển khai**, không phải danh sách YAML. Chứng minh **JDK test worker thật**, **Boot runtime/BOM thật**, **PostgreSQL/Redis server thật**, rồi chạy representative functional contracts. Tối ưu số tổ hợp bằng risk-based PR lanes, nightly extended và release gates. Kết quả “PASS” chỉ có giá trị cho các tuples được thực sự chạy và có artifacts truy vết.
