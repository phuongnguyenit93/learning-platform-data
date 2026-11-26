# Quản lý phụ thuộc qua Spring Boot và Gradle

> **Mục tiêu:** thiết lập một dự án Spring Data Cassandra có thể build lặp lại, dùng đúng phiên bản thư viện theo Spring Boot, hiểu sự khác biệt giữa plugin, starter, BOM và driver Cassandra, đồng thời biết kiểm tra và nâng cấp phụ thuộc an toàn.

## 1. Vấn đề: kết nối Cassandra cần nhiều thư viện nhưng không nên quản lý thủ công từng phiên bản

Một ứng dụng dùng Spring Data Cassandra thường cần đồng thời:

- **Spring Boot** để cấu hình ứng dụng và vòng đời các bean.
- **Spring Data Cassandra** để ánh xạ entity, sử dụng `CassandraRepository`, `CassandraTemplate` và các abstraction truy vấn.
- **Java driver cho Apache Cassandra** để kết nối cluster, gửi CQL, quản lý phiên kết nối, retry và paging state.
- **Gradle** để tải thư viện, biên dịch, chạy kiểm thử, đóng gói và tạo cấu trúc build có thể tái lập.

Những thành phần trên có quan hệ phụ thuộc lẫn nhau. Ví dụ, phiên bản Spring Data Cassandra cần tương thích với thế hệ Spring Framework và Java driver được chọn. Nếu tự ghi các phiên bản thư viện riêng lẻ mà không có quy tắc thống nhất, dự án dễ gặp lỗi `NoSuchMethodError`, `ClassNotFoundException`, lỗi khởi tạo bean hoặc các hành vi khác nhau giữa máy phát triển và CI.

Spring Boot giải quyết phần lớn việc **chọn phiên bản tương thích** thông qua cơ chế *dependency management*. Gradle chịu trách nhiệm **khai báo, giải quyết và tái lập** các phụ thuộc đó. Apache Cassandra server là thành phần hạ tầng độc lập: phiên bản server cũng phải kiểm tra khả năng tương thích với driver, nhưng **không được cài như một thư viện Java của ứng dụng**.

Trong bài này, ta xây dựng dịch vụ đọc lịch sử sự kiện thiết bị:

~~~text
Ứng dụng Spring Boot
  ├── Spring Data Cassandra
  │     ├── Entity mapping
  │     ├── CassandraRepository
  │     └── CassandraTemplate
  └── Java driver Cassandra
        └── kết nối qua CQL protocol
                ↓
          Cluster Apache Cassandra
~~~

Mục tiêu cuối cùng là một dự án có khai báo phụ thuộc gọn, nhất quán và có thể xác minh: ứng dụng hiểu cách tìm partition key để đọc sự kiện theo thiết bị/ngày, còn Gradle đảm bảo các thành phần Java được lấy đúng phiên bản.

## 2. Phân biệt plugin, starter, BOM, driver và server

| Thành phần | Vai trò | Cách quản lý |
| --- | --- | --- |
| Gradle Wrapper | Chốt cách khởi chạy một bản Gradle đã chọn cho dự án | Tệp `gradlew`, `gradlew.bat`, `gradle/wrapper/*` được quản lý cùng mã nguồn |
| Plugin `org.springframework.boot` | Tích hợp build Boot, `bootRun` và tạo executable jar | Chốt phiên bản **plugin** trong `plugins` |
| Plugin `io.spring.dependency-management` | Áp dụng quy tắc quản lý phiên bản phụ thuộc theo BOM | Chốt phiên bản plugin, phối hợp với Boot plugin |
| Spring Boot BOM | Danh sách phiên bản thư viện đã được một phiên bản Boot quản lý | Để plugin hoặc Gradle `platform(...)` nhập BOM |
| `spring-boot-starter-data-cassandra` | Bộ dependency dành cho ứng dụng Spring Data Cassandra | Khai báo starter **không ghi phiên bản riêng** khi đã dùng Boot BOM |
| `spring-data-cassandra` | Entity mapping, repository, `CassandraTemplate` | Thường được starter kéo vào; tránh ghim riêng phiên bản |
| Java driver Cassandra | `CqlSession`, statement CQL, pooling, paging, topology | Thường là phụ thuộc bắc cầu được BOM quản lý |
| Cassandra server | Lưu trữ, replication, partition, consistency | Chạy riêng trong container, VM hoặc dịch vụ quản lý; cấu hình qua `spring.cassandra.*` |

Một điểm rất quan trọng: **có Spring Boot Gradle plugin không đồng nghĩa mọi dependency Java tự nhận phiên bản**. Trong mô hình dưới đây, ta chủ động dùng plugin `io.spring.dependency-management`. Một lựa chọn khác là dùng cơ chế BOM gốc của Gradle (`platform`); hai cách được trình bày riêng ở mục 5.

### Bản chất của starter

Khai báo:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
~~~

sẽ kéo theo tập thư viện phục vụ Spring Data Cassandra, bao gồm các thành phần Spring Data và driver cần thiết theo dependency graph của phiên bản Boot đã chọn. Không cần thêm `spring-data-cassandra` và `java-driver-core` bằng tay chỉ để sử dụng repository hoặc template.

Điều **không** xảy ra khi thêm starter: Gradle không cài Cassandra server; Cassandra không tự tạo keyspace sản xuất; Gradle không tự xác định partition key cho truy vấn. Đó là trách nhiệm của hạ tầng và thiết kế dữ liệu.

## 3. Điều kiện trước khi tạo dự án

Đối với ví dụ sử dụng **Spring Boot 3.5.0** và **Java 17**, bạn cần:

1. JDK 17 (hoặc JDK nằm trong dải mà phiên bản Boot đang dùng hỗ trợ).
2. Một Gradle Wrapper tương thích với phiên bản Spring Boot và JDK được chọn.
3. Quyền truy cập repository Maven chứa các dependency, thông thường là Maven Central.
4. Một instance Cassandra tương thích để kiểm tra kết nối, chạy riêng ở `127.0.0.1:9042` hoặc trong môi trường phát triển.

**Phiên bản `3.5.0` được cố định chỉ để các ví dụ dưới đây nhất quán, không được hiểu là phiên bản mới nhất tại thời điểm bạn đọc.** Dự án thật cần tra release notes và bảng tương thích của Spring Boot/Gradle/JDK, chọn một phiên bản được tổ chức hỗ trợ, rồi cố định và kiểm thử nó. Không dùng dấu `+` hay `latest.release` cho phiên bản Boot trên nhánh phát hành.

Kiểm tra môi trường bằng wrapper của dự án:

~~~bash
java -version
./gradlew --version
~~~

Trên Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
~~~

`JAVA_HOME` và Gradle JVM cần trỏ đến JDK phù hợp. Gradle Java toolchain ở phần tiếp theo điều khiển JDK biên dịch ứng dụng, nhưng **không thể làm một Gradle/JDK không tương thích tự chạy được**. Cần xem riêng yêu cầu JDK để chạy Gradle và yêu cầu toolchain để biên dịch.

## 4. Thiết lập dự án với Gradle Groovy DSL

Tạo dự án với `settings.gradle`:

~~~groovy
rootProject.name = 'cassandra-device-events'
~~~

Định nghĩa `build.gradle` tối thiểu, dùng Maven Central, một phiên bản Boot được ghim, starter Cassandra và JUnit:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là ví dụ cơ sở đủ để phát triển một Spring Boot application dùng Cassandra; không cần đặt phiên bản ở hai dòng starter. Phiên bản plugin `1.1.7` cũng là giá trị cụ thể của **ví dụ**, cần kiểm tra tương thích với phiên bản Boot mà dự án lựa chọn khi nâng cấp.

Ý nghĩa của từng khối:

- `plugins` xác định năng lực build Java, Boot và quản lý version theo BOM.
- `java.toolchain` chỉ định Java 17 cho biên dịch và các tác vụ tương ứng, giúp máy phát triển và CI ít khác biệt.
- `repositories` là nguồn tải các Maven artifacts. Một hệ thống doanh nghiệp có thể dùng artifact proxy nội bộ; khi đó tổ chức cần cấu hình repository đúng tại build/settings.
- `implementation` chứa thư viện sử dụng khi chạy ứng dụng; `testImplementation` chỉ phục vụ biên dịch/chạy test; `testRuntimeOnly` chỉ cần khi thực thi test.
- `tasks.named('test')` bật JUnit Platform cho các kiểm thử JUnit 5.

### Cấu trúc thư mục dự án minh họa

~~~text
cassandra-device-events/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/telemetry/...
    │   └── resources/application.yml
    └── test/java/com/example/telemetry/...
~~~

Gradle Wrapper giúp thành viên nhóm và CI chạy cùng bản Gradle mà không yêu cầu mọi máy tự chọn một bản khác nhau. Nên commit wrapper scripts, wrapper JAR và `gradle-wrapper.properties` đã được kiểm tra nguồn gốc, đồng thời kiểm soát cách nâng phiên bản wrapper.

## 5. Kotlin DSL và cách nhập BOM bằng Gradle gốc

Nếu dùng Kotlin DSL, cùng cấu hình có thể viết trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-cassandra")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Groovy DSL và Kotlin DSL biểu diễn cùng ý tưởng: một phiên bản Boot quản lý bộ dependency liên quan. Chọn một kiểu DSL thống nhất cho dự án để dễ bảo trì.

### Lựa chọn khác: không dùng plugin dependency-management

Gradle có cơ chế BOM gốc thông qua `platform(...)`. Ví dụ sau là **một cách thay thế độc lập** cho `build.gradle` trên:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')

    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ở đây cần nhập BOM vào các configuration dùng nó; version BOM phải **trùng** với phiên bản Boot plugin. Đây là cách hiểu rõ ràng Gradle platform, nhưng khi dùng nhiều configuration tùy biến bạn phải chủ động áp quy tắc phiên bản phù hợp cho chúng.

**Chọn một chiến lược quản lý phiên bản phụ thuộc** cho mỗi dự án: thông qua `io.spring.dependency-management` hoặc dùng Gradle BOM/platform theo chủ đích. Tránh vô tình nhập các BOM chồng chéo hay ghi version tùy ý cho cùng một nhóm thư viện.

## 6. Tại sao không ghim riêng phiên bản Spring Data và driver?

Giả sử lập trình viên bổ sung vào `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'

    // Minh họa một cấu hình cần đánh giá, không nên chép vào dự án:
    implementation 'org.springframework.data:spring-data-cassandra:4.0.0'
    implementation 'com.datastax.oss:java-driver-core:4.13.0'
}
~~~

Đoạn này có thể phá vỡ ma trận tương thích mà Boot đã chọn: các dependency bắc cầu có thể kéo vào phiên bản khác, trong khi một số API Spring Data hoặc driver đã thay đổi. Gradle có quy tắc giải quyết xung đột phiên bản; kết quả cuối **không nhất thiết đúng với giả định của người vừa thêm dòng dependency**.

Các lý do thường thấy khiến người mới tự thêm driver:

- Muốn dùng `CqlSession` để chạy CQL.
- Muốn cấu hình paging hoặc consistency.
- Nhìn thấy driver trong mã nhưng chưa thấy dependency khai báo trực tiếp.

Với starter Cassandra, Java driver đã nằm trong dependency graph; cần xem cấu hình cụ thể bằng `dependencyInsight` trước khi thêm bất kỳ dependency trực tiếp nào.

Nếu thật sự cần tính năng chỉ có ở một phiên bản driver mới hơn, hãy làm rõ:

1. Tính năng cần dùng là gì và phiên bản đang được Boot quản lý đã hỗ trợ chưa?
2. Spring Data Cassandra tương thích với phiên bản driver đó không?
3. Có thể nâng **Spring Boot** lên bản hỗ trợ thay vì override một artifact đơn lẻ không?
4. Nếu buộc override, những API/bài integration test nào phải kiểm chứng, và khi nào có thể bỏ override?

Một override có chủ đích cần tài liệu quyết định và test kết nối Cassandra thực tế. Đừng sửa version chỉ để thông báo dependency scanner biến mất nếu chưa kiểm tra toàn bộ chuỗi tương thích và rủi ro bảo mật.

## 7. Cấu hình chạy ứng dụng và phân biệt với dependency build

Sau khi khai báo dependency, ứng dụng cần cấu hình **điểm kết nối cluster**, không phải thêm một dependency mới. Ví dụ `src/main/resources/application.yml` cho Cassandra cục bộ:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

`local-datacenter` phải đúng với tên datacenter do cluster báo, ví dụ này chỉ dùng `datacenter1` khi môi trường Cassandra thực tế có datacenter đó. `schema-action: none` có nghĩa không để ứng dụng tự ý sửa schema ở bước khởi động; hãy tạo keyspace và bảng bằng quy trình CQL/migration của hệ thống.

Có starter và cấu hình phù hợp, Spring Boot sẽ tự cấu hình `CqlSession` và các thành phần hỗ trợ như `CassandraTemplate`, đồng thời phát hiện repository trong phạm vi package scan. Một repository ví dụ:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
~~~

Trong đó `DeviceEvent` là entity có `@Table`, còn `DeviceEventKey` là composite key ánh xạ bằng `@PrimaryKeyClass` và `@PrimaryKeyColumn`. Đối với bảng sự kiện theo thời gian, partition key thường gồm thiết bị và bucket ngày, clustering key chứa thời gian; cách chọn khóa do **mẫu truy vấn** quyết định, không phải do Gradle.

Có thể inject template trực tiếp:

~~~java
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventReader {
    private final CassandraTemplate template;

    public EventReader(CassandraTemplate template) {
        this.template = template;
    }
}
~~~

Cả repository lẫn template đều sử dụng cấu hình kết nối và driver tương ứng. Nếu muốn viết CQL trực tiếp, có thể inject `CqlSession` mà starter cung cấp; hãy dùng bound parameters/prepared statements cho giá trị động và chỉ đọc/ghi những partition key phù hợp.

### Nhận diện lỗi build và lỗi runtime

Một dự án biên dịch thành công chưa chắc kết nối được Cassandra. Phân biệt:

| Lỗi | Tầng xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| `Could not resolve ...` | Gradle dependency resolution | Repository, mạng/proxy, artifact/version, cache |
| `package ... does not exist` | Compile classpath | Starter đã được thêm vào đúng module/configuration chưa |
| `NoSuchMethodError` khi khởi động | Runtime classpath | Xung đột thư viện, override version, nhiều BOM |
| `AllNodesFailedException` hoặc không kết nối được | Driver/runtime | Host, port, cluster sẵn sàng, datacenter, TLS/auth, routing |
| `InvalidQueryException: Keyspace ... does not exist` | Cassandra schema | Tạo keyspace và cấu hình keyspace đúng |
| Query timeout dù build đúng | Thiết kế dữ liệu/truy vấn và vận hành | Partition key, số partition bị quét, consistency, paging, tải và network |

Việc thêm dependency `spring-data-cassandra` lần nữa không giải quyết lỗi port, datacenter hoặc thiếu keyspace. Tương tự, sửa cấu hình YAML kết nối sẽ không sửa được classpath có version sai.

## 8. Kiểm tra dependency graph bằng Gradle

Sau khi thay đổi `build.gradle`, dùng Wrapper để xem phiên bản thực tế được chọn:

**Linux/macOS:**

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
./gradlew compileJava
./gradlew test
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
.\gradlew.bat compileJava
.\gradlew.bat test
~~~

Đây là lệnh **tham khảo để người học tự thực hành**; không cần chạy Cassandra server nếu chỉ xem dependency graph và compile source không cần kết nối. Tuy vậy, test tích hợp có thể cần cluster chạy hoặc Testcontainers.

Trong output `dependencies`, chú ý:

- Có đúng `spring-boot-starter-data-cassandra` trong `runtimeClasspath`?
- Spring Data Cassandra và driver xuất hiện do starter kéo vào hay do dependency thêm trực tiếp?
- Có dòng version được nâng/chọn khác so với version yêu cầu ban đầu không?
- Một dependency khác có mang theo driver hoặc một Spring Framework version không tương thích không?
- Có trường hợp thêm một dependency nhưng artifact thực tế bị loại trừ bởi `exclude` hoặc dependency constraint không?

`dependencyInsight` giải thích **vì sao** một artifact có mặt và quy tắc nào chọn phiên bản của nó. Nếu thấy hai phiên bản yêu cầu cạnh tranh, phải xem kết quả *resolved* và đường dẫn dependency, thay vì chỉ đọc từng dòng `implementation`.

### Ví dụ đọc xung đột phiên bản

Giả sử bản thiết kế mong driver A, nhưng `runtimeClasspath` chọn bản B do một thư viện khác yêu cầu. Không kết luận “Gradle lỗi” chỉ vì B khác A: Gradle có cơ chế chọn phiên bản theo constraints và metadata. Hãy xác định đường dẫn kéo B vào, kiểm tra nó có nằm trong dải hỗ trợ của Boot/Spring Data không, rồi sửa dependency gốc hoặc nâng cả bộ được quản lý.

Lệnh `--refresh-dependencies` có thể yêu cầu Gradle kiểm tra lại metadata/artifact cache khi thật sự nghi cache lỗi. Nó **không** sửa xung đột version hoặc kiến trúc dự án, và không nên là giải pháp mặc định mỗi lần build gặp lỗi.

## 9. Phụ thuộc cho kiểm thử: mock và Cassandra thật

Có hai loại kiểm thử với mục tiêu khác nhau:

**Unit test/service test** kiểm tra nghiệp vụ, ánh xạ dữ liệu vào yêu cầu repository hoặc logic tạo bucket theo UTC. Thường có thể dùng mock repository và `spring-boot-starter-test`, không cần Cassandra server.

**Integration test** kiểm tra Spring context, entity mapping, primary key, CQL, consistency/paging và tương tác driver thực tế. Với loại này cần Cassandra thật hoặc Cassandra container; mock không xác nhận được schema và đặc tính phân tán.

Khi dùng Testcontainers, có thể thêm riêng vào `dependencies`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:cassandra'
}
~~~

Các dòng trên dành cho bộ Spring Boot/Testcontainers **có version tương thích được BOM quản lý**; kiểm tra dependency graph để xác nhận các artifact và API của phiên bản đang dùng. Container cần Docker hoặc runtime container được hỗ trợ trong môi trường test. Định nghĩa schema bằng init script/migration phù hợp trước khi truy vấn; chỉ khởi động container không chứng minh bảng đã được tạo.

Nếu chọn `@ServiceConnection`, Spring Boot Testcontainers có thể tự lấy connection details từ container được hỗ trợ, giúp tránh hard-code host và mapped port. Tuy nhiên cách khai báo container/JUnit và các module Testcontainers thay đổi theo thế hệ phiên bản, vì vậy cần bám tài liệu dành riêng cho phiên bản Boot đang dùng. Không sao chép ví dụ từ một thế hệ Testcontainers khác mà bỏ qua dependency graph.

Một bài test tích hợp có ích cho module Spring Data Cassandra nên kiểm tra:

1. Ghi entity vào bảng có `PRIMARY KEY ((device_id, event_day), event_time, event_id)` và đọc lại đúng row.
2. Truy vấn repository trong một partition với thứ tự thời gian giảm dần.
3. Duyệt tiếp bằng `CassandraPageRequest`/paging state, tránh offset.
4. Xử lý hai sự kiện cùng millisecond nhưng `event_id` khác nhau.
5. Ghi thất bại hoặc đọc thiếu dữ liệu theo cấu hình consistency được chọn, nếu test cluster cho phép giả lập tình huống đó.

Các bài test này xác minh rằng dependency, mapping và hạ tầng phối hợp đúng trong thực tế; không chỉ kiểm tra Spring context khởi động.

## 10. Thêm phụ thuộc tùy chọn theo nhu cầu thực tế

Không nên thêm tất cả starter “cho đủ bộ”. Mỗi phụ thuộc tăng classpath, thời gian build, bề mặt nâng cấp và có thể kích hoạt auto-configuration mới.

| Nhu cầu | Phụ thuộc thường gặp | Khi nào nên thêm |
| --- | --- | --- |
| Spring Data Cassandra dạng đồng bộ | `spring-boot-starter-data-cassandra` | Ứng dụng dùng repository/template thông thường |
| Spring Data Cassandra reactive | `spring-boot-starter-data-cassandra-reactive` | Luồng reactive và Reactive Cassandra API được lựa chọn có chủ đích |
| REST API Servlet/MVC | `spring-boot-starter-web` | Ứng dụng thực sự cần HTTP API theo mô hình MVC |
| REST API reactive | `spring-boot-starter-webflux` | Ứng dụng có kiến trúc web reactive |
| Metrics và health endpoint | `spring-boot-starter-actuator` | Cần quan sát tình trạng dịch vụ và kết nối |
| Kiểm thử bằng container | `spring-boot-testcontainers` và module Testcontainers Cassandra | Cần integration test với Cassandra thật |

Reactive Cassandra không tự biến một `CassandraRepository` đồng bộ thành non-blocking. Nếu chuyển sang reactive, cần xem xét `ReactiveCassandraRepository`/`ReactiveCassandraTemplate` và luồng dữ liệu đầu-cuối. Việc thêm đồng thời starter đồng bộ và reactive có thể hợp lệ trong một số kiến trúc, nhưng hãy xác định rõ lý do và kiểm thử cách cấu hình các bean.

Với module nhiều Gradle subproject, nên đặt chính sách version/repository thống nhất ở tầng build, còn mỗi subproject chỉ khai báo các starter mà nó thực sự sử dụng. Tránh mỗi module tự ghi một phiên bản Spring Data khác nhau.

## 11. Kết nối, cấu hình và dependency ở các môi trường khác nhau

Dự án thường có **local, test, staging, production**. Dependency build Java nên ổn định; thay đổi môi trường chủ yếu thông qua cấu hình và secret management.

Ví dụ:

~~~yaml
# application-local.yml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

~~~yaml
# application-prod.yml (chỉ là khung, không lưu bí mật thực tế)
spring:
  cassandra:
    contact-points: cassandra-node.internal
    port: 9042
    local-datacenter: dc-production
    keyspace-name: telemetry
    schema-action: none
~~~

Sử dụng hệ quản lý secret hoặc biến môi trường cho tài khoản/mật khẩu, TLS trust material và thông tin nhạy cảm. Không commit password vào `application-prod.yml`. Cấu hình driver trong các phiên bản Boot khác nhau có thể thay đổi property name; khi nâng Boot, đối chiếu *configuration metadata* và release notes thay vì đoán property.

Hai ý dễ nhầm:

- Đổi `contact-points` hoặc `keyspace-name` **không** cần một phiên bản Gradle dependency khác.
- Nâng phiên bản Cassandra server **có thể** yêu cầu kiểm tra driver/protocol, nhưng vẫn nên đánh giá bằng matrix tương thích và integration test trước khi sửa dependency.

Nếu Cassandra sử dụng replication đa datacenter, consistency như `LOCAL_ONE` và `LOCAL_QUORUM` cần được thiết lập có chủ đích cho truy vấn. BOM không quyết định consistency thay ứng dụng. Thư viện chỉ cung cấp API để cấu hình lựa chọn đó; đáp án đúng phụ thuộc vào SLA, replication factor và mức độ chấp nhận đọc dữ liệu cũ.

## 12. Tái lập build và kiểm soát phụ thuộc gián tiếp

BOM cố định nhiều phiên bản, nhưng **reproducible build** còn liên quan đến repository, wrapper, dependency overrides, cách công bố artifact và khóa dependency.

Các thực hành hữu ích:

**Chốt wrapper và toolchain.** Commit tệp Wrapper đã được tạo từ nguồn đáng tin cậy; CI dùng wrapper cùng JDK đã chốt thay vì Gradle toàn cục trên máy agent.

**Tránh phiên bản động.** Các cú pháp như `1.+`, `latest.integration` hoặc `SNAPSHOT` ngoài chủ đích làm build có thể thay đổi kết quả theo thời gian. `0.0.1-SNAPSHOT` trong ví dụ là **version của ứng dụng**, không phải dependency production cần resolve.

**Kiểm soát repository.** Chỉ dùng các repository cần thiết và được tổ chức cho phép. Với artifact proxy nội bộ, cần xác định rõ nguồn upstream và chính sách lưu trữ để tránh vô tình đổi artifact khi một kho khác được ưu tiên.

**Kiểm tra dependency locking khi cần.** Gradle hỗ trợ ghi kết quả version resolution vào lockfile để giảm bất ngờ khi dependency graph thay đổi. Ví dụ cấu hình Groovy DSL:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Khóa dependency cần được tạo/cập nhật bằng quy trình có review khi nâng cấp. Lockfile không thay thế BOM: BOM đưa ra phiên bản được quản lý, lockfile ghi nhận phiên bản **đã được resolve** trong cấu hình được khóa. Không nên bật locking rồi bỏ quên các lockfile khi điều chỉnh dependency.

**Bảo mật supply chain.** Kiểm tra nguồn plugin và thư viện, theo dõi CVE/security advisory, dùng dependency verification/checksum khi chính sách tổ chức yêu cầu, và phân biệt lỗ hổng ở build tool, runtime library và Cassandra server. Sửa bằng một thay đổi có kiểm chứng, tránh ép nâng duy nhất driver làm lệch toàn bộ bộ thư viện.

## 13. Nâng cấp Spring Boot mà không phá hỏng Spring Data Cassandra

Một quy trình nâng cấp có kiểm soát nên theo thứ tự:

1. **Đọc phạm vi thay đổi.** Chọn target Boot version được hỗ trợ; xem release notes, thay đổi Spring Data, Gradle/JDK requirement, Java driver và property deprecations.
2. **Chốt điểm xuất phát.** Ghi phiên bản Boot plugin, Gradle Wrapper, JDK, runtimeClasspath, phiên bản Cassandra server và kết quả test hiện tại.
3. **Nâng version tại đúng nguồn sự thật.** Nếu dùng plugin `io.spring.dependency-management`, cập nhật Boot plugin rồi kiểm tra BOM mới; nếu dùng Gradle `platform`, cập nhật cả Boot plugin và tọa độ BOM cùng version.
4. **Xem lại overrides.** Loại những override không còn cần thiết; kiểm tra artifact bị loại trừ hoặc version constraint tự đặt.
5. **Giải quyết lại graph.** Chạy `dependencies` và `dependencyInsight` để kiểm tra Spring Data Cassandra, driver và test libraries.
6. **Build và kiểm thử.** Chạy compile, unit test và integration test với Cassandra server version mà hệ thống vận hành thực tế sử dụng. Kiểm tra query, paging state, consistency và driver connection settings.
7. **Canary/rollout.** Quan sát tỷ lệ lỗi, latency p95/p99, số kết nối, timeout và tài nguyên. Nếu có vấn đề, rollback cả artifact lẫn config liên quan.

Không nên nâng Cassandra server, Boot, driver override và Gradle Wrapper cùng một lúc nếu không có lý do bắt buộc: khó phân định nguyên nhân khi xảy ra lỗi. Khi có yêu cầu bảo mật gấp, nhóm có thể phải nâng nhanh hơn, nhưng vẫn cần kiểm tra classpath và một tập smoke/integration test trọng yếu.

### Bảng dấu hiệu thường gặp sau nâng cấp

| Hiện tượng | Nguồn gây lỗi hay gặp | Hướng xử lý |
| --- | --- | --- |
| Gradle không chạy với JDK hiện có | Không tương thích Gradle/JDK | Kiểm tra yêu cầu wrapper và runtime JDK |
| Thiếu method trong thư viện Spring | Version Spring Framework/Spring Data bị override | Dọn version thủ công, soi `dependencyInsight` |
| Code import driver cũ không biên dịch | Thay đổi Java driver API/package | Đối chiếu API của driver đang được Boot quản lý |
| Connection fail sau nâng | Driver settings, TLS, protocol, datacenter | Kiểm tra config/migration guide và kết nối thực tế |
| Repository trả sai kiểu page | Khác biệt API paging/repository | Kiểm tra release notes và test phân trang, dùng `CassandraPageRequest` phù hợp |
| Build chạy local nhưng hỏng trên CI | Khác Gradle/JDK, repository hoặc lockfile | Dùng wrapper/toolchain, kiểm tra dependency resolution ở CI |

## 14. Thực hành: thêm và xác minh phụ thuộc từ đầu

Giả sử nhóm xây màn hình “50 sự kiện mới nhất theo thiết bị và ngày UTC”. Làm theo checklist thực hành:

### Bước 1: Khởi tạo build

Tạo `settings.gradle` và `build.gradle` như mục 4; chọn bộ phiên bản được hỗ trợ; không thêm version riêng cho Spring Data Cassandra/Java driver.

### Bước 2: Xem dependency graph trước khi viết entity

~~~bash
./gradlew dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
~~~

Ghi lại artifact và resolved version. Nếu không thấy dependency mong đợi, kiểm tra starter và cấu hình `runtimeClasspath` thay vì thêm ngẫu nhiên nhiều thư viện.

### Bước 3: Tạo schema Cassandra theo truy vấn

Dành cho demo local, ví dụ giản lược:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS telemetry.device_events (
    device_id  uuid,
    event_day  date,
    event_time timestamp,
    event_id   uuid,
    kind       text,
    payload    text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`SimpleStrategy` và RF=1 chỉ phù hợp môi trường một node để học; production thường cần `NetworkTopologyStrategy` với RF dựa trên topology và mức chịu lỗi. Một ngày UTC là bucket để tránh partition tồn tại vô hạn. Truy vấn timeline phải cung cấp cả `device_id` và `event_day`, ví dụ:

~~~sql
SELECT event_time, event_id, kind, payload
FROM telemetry.device_events
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

BOM không liên quan đến việc Cassandra có thể chạy CQL này nhanh hay chậm; hiệu năng dựa vào phân vùng, clustering, phân bố dữ liệu và tải thực tế.

### Bước 4: Cấu hình kết nối, build và smoke test

Đặt `application.yml` từ mục 7, kiểm tra tên datacenter/keyspace, rồi chạy:

~~~bash
./gradlew compileJava
./gradlew test
./gradlew bootRun
~~~

Ứng dụng có thể khởi động khi Cassandra chưa sẵn sàng tùy cấu hình/bean được khởi tạo, nhưng thao tác kết nối/truy vấn thật sẽ thất bại nếu cluster không truy cập được. Với bài smoke test có giá trị, phải thực hiện một truy vấn repository hoặc `CassandraTemplate` trên partition mẫu và kiểm tra kết quả, không chỉ thấy dòng log “Started”.

### Bước 5: Thử thay đổi phụ thuộc và giải thích hệ quả

Giả sử có người đề xuất thêm `com.datastax.oss:java-driver-core` với version được ghim. Trước khi chấp nhận, hãy trả lời: starter đã kéo driver chưa, version nào được resolve, vì sao cần override, và test nào chứng minh Spring Data Cassandra tương thích? Từ đó đề xuất nâng Boot hoặc giữ BOM mặc định khi chưa có yêu cầu chính đáng.

## 15. Bài tập tự đánh giá

**Bài A — Chẩn đoán phiên bản.** Một dự án có Boot plugin 3.5.0, starter Cassandra không ghi version và `spring-data-cassandra` bị ghim riêng một phiên bản cũ. Hãy giải thích vì sao có rủi ro, dùng lệnh nào tìm phiên bản thực tế và cách sửa nhỏ nhất.

**Bài B — Đọc classpath.** `compileJava` chạy thành công nhưng `bootRun` báo `NoSuchMethodError` liên quan Java driver. Chỉ ra cách dùng `dependencyInsight --configuration runtimeClasspath` để tìm đường dependency và vì sao không nên thử đổi ngẫu nhiên `spring.cassandra.contact-points`.

**Bài C — Build tái lập.** Đội phát triển dùng Gradle toàn cục trên mỗi máy, một dependency dùng `1.+` và test local khác CI. Hãy xây đề xuất tối thiểu gồm Gradle Wrapper, Java toolchain, version pin/BOM và cách kiểm soát dependency động.

**Bài D — Kiểm thử Cassandra.** Viết kế hoạch test phân biệt unit test với integration test. Hãy nêu vì sao một mock repository có thể xác nhận logic tính bucket ngày UTC nhưng không chứng minh CQL partition key, sorting trong Cassandra hay paging state hoạt động đúng.

**Bài E — Nâng cấp an toàn.** Khi cần nâng Spring Boot, hãy lập danh sách các thành phần phải đối chiếu: Gradle Wrapper, JDK, Spring Data Cassandra, Java driver, Cassandra server, Testcontainers và cấu hình. Chọn tối thiểu ba phép kiểm thử cần chạy trước rollout.

**Đạt yêu cầu khi** bạn có thể viết cấu hình build chuẩn với một nguồn quản lý phiên bản rõ ràng, giải thích đường đi của dependency, đọc được resolved versions bằng Gradle, phân biệt lỗi build và lỗi kết nối Cassandra, và lập được kế hoạch kiểm thử/nâng cấp có thể tái hiện.

## Tài liệu tham khảo

- [Spring Boot — Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/index.html): cấu hình plugin, đóng gói và sử dụng dependency management.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/index.html): phiên bản thư viện Spring Boot quản lý.
- [Spring Boot — Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter và các thuộc tính kết nối Cassandra.
- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): repository, `CassandraTemplate`, mapping và truy vấn.
- [Gradle — Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html): BOM/platform, dependency resolution và constraints.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): quy trình ghi và cập nhật lockfile.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): chạy build với Gradle version đã chọn.
- [Testcontainers — Cassandra Module](https://java.testcontainers.org/modules/databases/cassandra/): integration test với Cassandra container.
