# `@AutoConfigureTestDatabase` và chính sách thay thế `DataSource` trong Spring Boot test slice

## Mục tiêu học tập

Kiểm thử repository/JDBC trong Spring Boot thường cần một database để chạy SQL, tạo bảng, lưu và đọc dữ liệu. Với các test slice như `@DataJpaTest` hoặc `@JdbcTest`, Spring Boot có thể **thay `DataSource` vốn được cấu hình cho ứng dụng bằng một database nhúng dành cho test**. Cơ chế này giúp test khởi chạy nhanh và không phụ thuộc server database bên ngoài, nhưng cũng có thể khiến test vô tình chạy trên H2 thay vì PostgreSQL/MySQL mà bạn tưởng đang sử dụng.

Annotation **`@AutoConfigureTestDatabase`** cho phép quyết định **có thay `DataSource` hay không, thay loại nào và dùng embedded database gì**. Quy tắc **không hoàn toàn giống nhau giữa Spring Boot 3.3 và 3.4+**, nhất là với Testcontainers.

Sau bài này, bạn có thể:

- Giải thích `DataSource` và “replacement” trong một Spring Boot test slice.
- Phân biệt `Replace.ANY`, `Replace.AUTO_CONFIGURED`, `Replace.NONE` và `Replace.NON_TEST` theo **phiên bản Spring Boot**.
- Biết tại sao `@DataJpaTest` và `@JdbcTest` thường dùng database nhúng, trong khi `@SpringBootTest` không tự động có cùng quy tắc thay thế.
- Chọn **H2 test database**, database được cấu hình riêng hoặc **Testcontainers** theo mục tiêu và tính tương thích SQL.
- Viết project **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit Jupiter** chạy được, kiểm cả tình huống thay một DataSource và giữ nguyên DataSource.
- Xác minh **database thực sự được sử dụng** qua JDBC metadata, không chỉ tin vào `application-test.yml` hay log.
- Chẩn đoán thiếu embedded driver, sai cổng DB, khác dialect, migration/transaction, nhiều DataSource và test vô tình kết nối production.

**Trọng tâm:** `replace = NONE` không tạo DataSource mới; nó chỉ **ngăn Spring Boot thay thế DataSource** mà test context đã được cấu hình. Muốn kiểm PostgreSQL, bạn vẫn phải thực sự cấp PostgreSQL, cấu hình kết nối và kiểm rằng test đã dùng đúng DB.

## 1. Vì sao test slice lại thay `DataSource`?

Trong JDBC/JPA, một `javax.sql.DataSource` là abstraction cấp kết nối JDBC, thường được cung cấp bằng connection pool như HikariCP. Một service/repository có thể lấy `Connection` thông qua `DataSource`, thực thi SQL rồi trả kết quả.

Ví dụ application có cấu hình:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=...
~~~

Đây là **cấu hình minh họa**, không phải giá trị để dùng trong test; không đặt mật khẩu production vào test hoặc repository. Nếu `@DataJpaTest` mặc định vô tình kết nối database production thật, test có thể sửa dữ liệu nhạy cảm hoặc phụ thuộc hạ tầng không ổn định.

Vì vậy trong các test slice liên quan JDBC/JPA, Boot có cơ chế **test database auto-configuration**:

~~~text
Test class @DataJpaTest / @JdbcTest
             |
             v
Spring Boot tạo test ApplicationContext có DataSource
             |
             +-- DataSource đã được cấu hình qua properties / @Bean
             |
             v
TestDatabaseAutoConfiguration
             |
             +-- replacement policy có cho phép thay không?
             |       |
             |       +-- Có -> tìm embedded driver, dựng test DataSource
             |       |         (H2/HSQLDB/Derby khi phù hợp)
             |       |
             |       +-- Không -> giữ DataSource đã cấu hình
             |
             v
Repository/JdbcTemplate/JPA giao tiếp với DataSource thực tế
             |
             v
@Test kiểm SQL/dữ liệu trên DB đó
~~~

Cơ chế này **thay lựa chọn bean DataSource trong test context**, không sửa file `application.yml` và không tự cấu hình server DB production. Khi đang dùng database nhúng, kết quả test chứng minh hành vi với database nhúng, **chưa chắc chứng minh SQL/dialect của database production**.

Một test pass trên H2 có thể vẫn lỗi ở PostgreSQL do kiểu cột, câu SQL native, collation, index, constraint hoặc transaction. Ngược lại, các phép CRUD chuẩn với schema nhỏ có thể rất phù hợp với H2 để phản hồi nhanh trong quá trình phát triển.

## 2. Những test slice nào liên quan?

| Annotation/kiểu test | Phạm vi chính | Mặc định liên quan database |
| --- | --- | --- |
| `@DataJpaTest` | JPA entities, Spring Data JPA repositories, Hibernate, `TestEntityManager` | Có thể thay DataSource bằng embedded test DB; thường transactional và rollback sau mỗi test |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, SQL/JDBC | Có thể thay DataSource bằng embedded test DB; thường transactional và rollback |
| `@DataJdbcTest` | Spring Data JDBC repositories, relational mapping | Có cơ chế database test tương tự |
| `@JooqTest` | jOOQ `DSLContext` và SQL | Thường giữ DataSource đã cấu hình, có thể dùng `@AutoConfigureTestDatabase` để yêu cầu thay |
| `@SpringBootTest` | Spring Boot ApplicationContext rộng hơn | **Không mặc định áp dụng chính sách embedded replacement của `@DataJpaTest`**; muốn thay cần thiết lập test DB cụ thể hoặc `@AutoConfigureTestDatabase` phù hợp |
| `@WebMvcTest` | Controller/MVC serialization, validation | Không nhằm tạo JPA/DataSource; thường mock service boundary |
| JUnit unit test thuần | Logic Java không cần Spring | Không có Spring DataSource; không cần `@AutoConfigureTestDatabase` |

Ví dụ `@DataJpaTest` thường chỉ nạp các thành phần JPA liên quan, không tự nạp mọi `@Service`/`@Controller` của ứng dụng. `@JdbcTest` không kiểm entity mapping của Hibernate; nó chú trọng trực tiếp JDBC. Annotation thay DB là **một lựa chọn về hạ tầng test**, không biến một slice thành full integration test.

### Đường import đúng của Spring Boot 3.3.x

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase.Replace;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
~~~

Đây là các import minh họa; trong chương trình Java hoàn chỉnh chỉ thêm những import cần dùng. Spring Boot 4 đã tổ chức lại một số test modules/packages, nên **không sao chép import của Boot 3.x vào Boot 4** mà không kiểm Javadoc theo phiên bản.

## 3. Các chính sách thay thế: hiểu đúng từng `Replace`

`@AutoConfigureTestDatabase` có thuộc tính `replace` nhận enum `AutoConfigureTestDatabase.Replace`.

### `Replace.ANY`

~~~java
@AutoConfigureTestDatabase(replace = Replace.ANY)
~~~

Cho phép **thay DataSource dù được tạo bằng auto-configuration hay khai báo thủ công bằng `@Bean`**, theo cơ chế test database auto-configuration và các ràng buộc liên quan. Đây là cách quyết liệt, thích hợp khi muốn chắc rằng test slice sử dụng một embedded DB được lựa chọn thay vì DataSource ứng dụng.

Trong Spring Boot **3.3.x**, `Replace.ANY` là **giá trị mặc định** của `@AutoConfigureTestDatabase`. Các test slice mang annotation này cũng có xu hướng dùng embedded database nếu driver có sẵn. Đây là điểm quan trọng khi kết hợp Testcontainers trong Boot 3.3: **một DataSource do test cấu hình cho container cũng có thể bị thay bằng embedded DB** nếu không đặt `Replace.NONE`.

### `Replace.AUTO_CONFIGURED`

~~~java
@AutoConfigureTestDatabase(replace = Replace.AUTO_CONFIGURED)
~~~

Chỉ cân nhắc thay DataSource được **Spring Boot auto-configure**, không thay một DataSource do người dùng tự khai báo thủ công theo nhánh được hỗ trợ. Đây không phải “chỉ thay khi database là production”; điểm phân biệt là **nguồn gốc bean definition**, không phải database đó nguy hiểm hay an toàn.

Cẩn thận: nếu bạn dùng `spring.datasource.url` để chỉ Postgres, Hikari `DataSource` vẫn có thể do **Boot auto-configuration** tạo ra. Vì vậy `AUTO_CONFIGURED` có thể thay DataSource đang kết nối PostgreSQL; **không dùng nó để cam kết giữ Testcontainers hoặc cấu hình JDBC URL** mà chưa kiểm chính xác đường auto-configuration.

### `Replace.NONE`

~~~java
@AutoConfigureTestDatabase(replace = Replace.NONE)
~~~

**Không thay** application/configured DataSource bằng embedded database. Thường dùng khi cần:

- Kiểm migration/schema/query trên PostgreSQL hoặc MySQL thật trong môi trường test.
- Dùng Testcontainers mà không muốn nó bị thay bằng H2.
- Giữ một test DataSource đã được thiết lập tường minh bằng properties, `@DynamicPropertySource`, `@ServiceConnection` hoặc test config.
- Kiểm behavior của datasource/pool/driver đã chọn thay vì chỉ kiểm thuật toán SQL độc lập.

**`NONE` không tự tạo Postgres container, không cấp quyền truy cập DB, không thay URL thành JDBC test URL, và không bảo đảm tránh kết nối production.** Nếu properties hiện tại đang chỉ tới DB production, test **có thể kết nối production**. Cần có fixture, credentials, network isolation và kiểm JDBC URL.

### `Replace.NON_TEST` — thêm từ Spring Boot 3.4

~~~java
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
~~~

Từ **Spring Boot 3.4**, enum `NON_TEST` được bổ sung và trở thành lựa chọn mặc định mới của annotation: thay DataSource trừ khi nó **được auto-configure và đã được nhận diện là đang kết nối tới test database**.

Những dấu hiệu test database được Boot 3.4+ nhận diện gồm, tùy phiên bản/cấu hình:

- `ContainerImageMetadata` có nguồn từ Testcontainers `@ServiceConnection` hoặc Docker Compose connection metadata.
- JDBC URL được thiết lập qua `@DynamicPropertySource`.
- Testcontainers JDBC URL với cú pháp `jdbc:tc:...`.

Nhờ đó một `@DataJpaTest` dùng container test được auto-configure có thể **giữ** nó mà không cần viết `replace = NONE`. Nhưng cần hiểu các giới hạn:

- `NON_TEST` **không tồn tại trong Boot 3.3.x**. Viết `Replace.NON_TEST` ở Boot 3.3 sẽ **không biên dịch**.
- Dấu hiệu “test DB” không đơn giản là tên database có chữ `test` hoặc host là `localhost`.
- Việc bảo vệ chủ yếu áp dụng khi DataSource **được auto-configure** và Boot có đủ metadata nhận diện; DataSource khai báo thủ công bằng `@Bean` có thể cần chính sách rõ hơn.
- Nếu quyết định của bạn là “**tuyệt đối giữ DataSource test đã chỉ định**”, `Replace.NONE` vẫn là cách diễn đạt tường minh, dễ review.
- Cần đọc Javadoc đúng bản 3.4/3.5 đang chạy vì nhận diện test database có thể được cập nhật qua các phiên bản.

### Bảng tóm tắt chính sách theo phiên bản

| Policy | Spring Boot 3.3.x | Spring Boot 3.4+ | Ý nghĩa chính |
| --- | --- | --- | --- |
| `ANY` | Có; **mặc định 3.3** | Có | Cho phép thay auto-configured hoặc manually defined DataSource |
| `AUTO_CONFIGURED` | Có | Có | Chỉ thay DataSource do auto-configuration tạo |
| `NONE` | Có | Có | Không thay DataSource đã cấu hình |
| `NON_TEST` | **Chưa có** | Có; **mặc định từ 3.4** | Bảo toàn DataSource auto-configured mà Boot nhận diện là test DB |

Không có một câu “`@DataJpaTest` luôn thay mọi DataSource” đúng cho mọi Spring Boot version. **Ghi rõ phiên bản trước khi giải thích behavior mặc định.** Khi dự án có nhiều module nâng cấp không đồng bộ, dùng enum tường minh để thể hiện intent và kiểm dependency tree thực tế.

## 4. `connection`: thay bằng embedded database nào?

Thuộc tính khác của annotation là `connection` nhận `EmbeddedDatabaseConnection`:

~~~java
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
~~~

Các lựa chọn embedded database truyền thống trong Spring Boot 3.x gồm H2, HSQLDB và Derby, cộng với `NONE` để cơ chế tự phát hiện trên classpath. **`connection = EmbeddedDatabaseConnection.NONE` không giống `replace = Replace.NONE`**:

- `replace = NONE` = **không thực hiện thay DataSource**.
- `connection = NONE` = **không ép một embedded engine cụ thể**; Boot có thể tự phát hiện engine thích hợp khi cần thay.

Muốn thay bằng H2, phải có **H2 JDBC driver trên test runtime classpath**. Annotation không tải thư viện từ Maven giúp bạn. Nếu không có H2/HSQLDB/Derby nào phù hợp mà policy yêu cầu tạo embedded DB, context có thể fail khi khởi tạo.

Các tình huống thường gặp:

| Cấu hình | Kết quả mong đợi |
| --- | --- |
| `replace = ANY`, H2 test runtime có sẵn | DataSource mục tiêu được thay bằng H2 embedded |
| `replace = ANY, connection = H2` nhưng thiếu H2 driver | Không tạo được H2 DataSource, context có thể fail |
| `replace = NONE` cùng `spring.datasource.url=jdbc:postgresql:...` | Giữ DataSource theo properties; cần PostgreSQL sẵn sàng |
| `replace = NONE` cùng URL H2 in-memory do test khai báo | Giữ **chính H2 đó**; vẫn có database nhúng nhưng **không bị thay** |
| `replace = AUTO_CONFIGURED` và DataSource thủ công | DataSource thủ công không thuộc nhóm auto-configured để thay |
| `replace = NON_TEST` ở Boot 3.3.x | Lỗi compile vì enum không tồn tại |

Chọn embedded database dựa trên câu hỏi **muốn kiểm điều gì**: SQL chung và CRUD đơn giản có thể phù hợp H2; mapping/native SQL/DB-specific features yêu cầu database engine tương ứng.

## 5. Demo chạy được: kiểm chính sách thay thế qua JDBC metadata

Ví dụ dùng **Spring Boot 3.3.5**, **Java 17**, **Gradle Groovy DSL**, `@JdbcTest` và H2. Hai test class khởi tạo **hai test ApplicationContext khác nhau**:

- Class A đặt JDBC URL là `jdbc:h2:mem:configureddb` nhưng **`Replace.ANY`** yêu cầu Boot **thay** bằng một embedded H2 instance được chọn/tạo bởi test auto-configuration.
- Class B đặt JDBC URL là `jdbc:h2:mem:keptdb` và **`Replace.NONE`**, vì vậy Boot phải **giữ** DataSource auto-configured từ chính URL `keptdb`.

Cả hai dùng H2 để demo **không cần PostgreSQL, Docker hay dịch vụ bên ngoài**. Do đó class B chỉ chứng minh “NONE giữ cấu hình”, **không chứng minh sử dụng real PostgreSQL**. Đó là sự phân biệt quan trọng.

### 5.1. Cấu trúc file

~~~text
test-datasource-policy-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   └── JdbcTestApplication.java
    └── test/java/com/example/testing/
        ├── ReplacedDataSourceJdbcTest.java
        └── PreservedDataSourceJdbcTest.java
~~~

Dự án demo tập trung vào **chạy test**, không cần khởi động app không có test DataSource bằng `bootRun`. H2 là **test-only dependency**, không được đưa vào production artifact một cách vô tình.

**`settings.gradle`**

~~~groovy
rootProject.name = 'test-datasource-policy-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Giải thích cấu hình:**

- `spring-boot-starter-jdbc` cung cấp JDBC support, `JdbcTemplate`, transaction infrastructure và JDBC `DataSource` auto-configuration liên quan khi có driver.
- `spring-boot-starter-test` cung cấp Spring TestContext và JUnit Jupiter.
- `testRuntimeOnly 'com.h2database:h2'` chỉ cho phép H2 hiện diện ở **test runtime**, không đưa driver H2 vào production runtime của module demo.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` giúp Gradle/JUnit Platform chạy test theo cấu hình.
- `useJUnitPlatform()` cho Gradle chạy JUnit Jupiter tests.
- Spring Boot 3.3.5 BOM quản lý version dependency; không tự chốt H2/JUnit version khác gây lệch.

Cần có Java 17 và Gradle Wrapper tương thích. Nếu repo đã có `gradlew`, dùng đúng version repo. Nếu tạo mới, có thể bootstrap wrapper từ Gradle đã cài bằng `gradle wrapper --gradle-version 8.8 --distribution-type bin` cho project demo. Sau đó lưu các file wrapper trong repository; không tự viết `gradle-wrapper.jar` bằng tay.

### 5.2. Class gốc giúp slice xác định Boot application configuration

**`src/main/java/com/example/testing/JdbcTestApplication.java`**

~~~java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcTestApplication.class, args);
    }
}
~~~

Đối với `@JdbcTest`, Spring Boot vẫn cần tìm `@SpringBootConfiguration` để bootstrap context. Class có `@SpringBootApplication` cung cấp điểm gốc, nhưng **test slice không tự load toàn bộ các service/controller như một `@SpringBootTest`**. Vì project không cung cấp production JDBC URL/driver để chạy độc lập, main method chỉ là bootstrap metadata cho test; bài tập được xác minh bằng task `test`.

### 5.3. Test A — `ANY` thay DataSource dù có JDBC URL cấu hình

**`src/test/java/com/example/testing/ReplacedDataSourceJdbcTest.java`**

~~~java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:configureddb;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class ReplacedDataSourceJdbcTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void anyReplacesConfiguredDataSourceWithEmbeddedH2()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            String jdbcUrl = connection.getMetaData().getURL();

            assertTrue(jdbcUrl.startsWith("jdbc:h2:mem:"), jdbcUrl);
            assertFalse(jdbcUrl.contains("configureddb"), jdbcUrl);
        }
    }

    @Test
    void replacedDataSourceIsUsableByJdbcTemplate() {
        Integer result = jdbcTemplate.queryForObject(
                "select 3 + 4", Integer.class);

        assertNotNull(result);
        assertEquals(7, result.intValue());
    }
}
~~~

**Điều cần quan sát:**

- `spring.datasource.url` có một giá trị đã cấu hình nhưng `replace = ANY` yêu cầu replacement.
- Vì `connection = H2` và H2 test runtime có sẵn, Boot tạo **embedded H2 test DataSource**.
- URL thực tế từ `Connection.getMetaData().getURL()` phải bắt đầu bằng `jdbc:h2:mem:`, nhưng **không chứa `configureddb`** — tên database cấu hình ban đầu. Tên H2 instance được tạo có thể thay đổi, nên test **không hardcode tên ngẫu nhiên**.
- Query `select 3 + 4` chạy qua `JdbcTemplate` và trả 7, chứng minh DataSource hoạt động, không chỉ được inject.
- Test không cần mở cổng TCP cho H2 in-memory; đây không phải endpoint HTTP hay một database server chạy riêng.

Dữ liệu kiểm thử ở đây có chủ đích đơn giản để chứng minh **chính sách replacement**. Nó chưa kiểm SQL phức tạp, schema migration hay repository persistence.

### 5.4. Test B — `NONE` giữ DataSource theo cấu hình test

**`src/test/java/com/example/testing/PreservedDataSourceJdbcTest.java`**

~~~java
package com.example.testing;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:keptdb;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PreservedDataSourceJdbcTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void nonePreservesTheExplicitJdbcUrl() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            String jdbcUrl = connection.getMetaData().getURL();

            assertTrue(
                    jdbcUrl.startsWith("jdbc:h2:mem:keptdb"),
                    jdbcUrl);
        }
    }

    @Test
    void preservedDataSourceStillRunsQueries() {
        Integer result = jdbcTemplate.queryForObject(
                "select 1 + 2", Integer.class);

        assertNotNull(result);
        assertEquals(3, result.intValue());
    }
}
~~~

**Điều cần quan sát:**

- `Replace.NONE` không thay JDBC URL mà test chỉ định.
- URL thực tế phải bắt đầu bằng `jdbc:h2:mem:keptdb`.
- Test vẫn dùng **H2**, vì **chính test** đã cấu hình H2 làm DataSource. “NONE” **không có nghĩa dùng production DB**.
- Câu query đơn giản cho kết quả 3, chứng minh kết nối hoạt động.

Hai class là **hai cấu hình test khác nhau**, một thay DataSource, một giữ, do đó không nên thiết kế test phụ thuộc chúng dùng chung một context. `JdbcTest` thường chạy transaction cho từng test method rồi rollback khi hoàn tất, nhưng việc dùng transaction không bảo vệ test nếu `DataSource` đang trỏ nhầm production và migration/DDL hoặc side effect nằm ngoài transaction có thể đã xảy ra. Vì vậy luôn xác minh DB mục tiêu trước khi đưa dữ liệu nhạy cảm vào phép thử.

### 5.5. Chạy test và kết quả kỳ vọng

Tại root dự án có Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chỉ chạy test có replacement:

~~~bash
./gradlew test --tests 'com.example.testing.ReplacedDataSourceJdbcTest'
~~~

Chỉ chạy test giữ nguyên DataSource:

~~~bash
./gradlew test --tests 'com.example.testing.PreservedDataSourceJdbcTest'
~~~

Mỗi class có **2 method `@Test`**, tổng cộng **4 lượt JUnit test**. Kỳ vọng cả bốn pass với code/config đúng như mô tả. Không có `System.out.println` và không in JDBC URL ở stdout, nên **không có stdout nghiệp vụ cố định**. Khi Gradle thành công, có thể hiện `BUILD SUCCESSFUL`. Nếu test task `UP-TO-DATE` hoặc `FROM-CACHE`, kết quả có thể được dùng lại; để buộc thực thi lại khi chẩn đoán, có thể chạy `./gradlew test --rerun-tasks`.

Report thường ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ReplacedDataSourceJdbcTest.xml
    └── TEST-com.example.testing.PreservedDataSourceJdbcTest.xml
~~~

Với project multi-module, đường dẫn nằm trong thư mục `build` của module chứa test. Nếu test fail ở `Failed to load ApplicationContext`, hãy đọc root cause liên quan driver/DataSource trước khi sửa assertion.

## 6. Test `@DataJpaTest` với PostgreSQL Testcontainers

Demo trước dùng H2 để không cần Docker, nhưng nhiều hệ thống cần xác minh **SQL thật của PostgreSQL**: `jsonb`, native queries, index/constraint, transaction isolation, sequence, timestamp/UUID hoặc migration theo dialect. Khi đó có thể dùng **Testcontainers** để chạy PostgreSQL tạm thời trong môi trường test.

Ý tưởng:

~~~text
JUnit / @DataJpaTest
       |
       +-- PostgreSQLContainer ("postgres:16-alpine")
       |           |
       |           +-- JDBC URL/credentials động, không hardcode port
       |
       +-- Spring Boot @ServiceConnection / @DynamicPropertySource
       |           |
       |           v
       |       DataSource kết nối container
       |
       +-- @AutoConfigureTestDatabase(replace = NONE)
                   |
                   v
         Không tự đổi thành H2 test DB
                   |
                   v
             JPA repositories chạy PostgreSQL thật
~~~

### 6.1. Dependencies bổ sung trong Spring Boot 3.3.x

Nếu project đã có Spring Boot `spring-boot-starter-data-jpa` và `spring-boot-starter-test`, phần bổ sung điển hình cho Testcontainers là:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là **đoạn thêm vào một Gradle project có sẵn JPA, Spring Boot plugin và dependency management**; không phải file build độc lập. Bộ version phải được quản lý tương thích với Spring Boot của dự án. Testcontainers cần Docker/container runtime hoạt động trong môi trường chạy test.

### 6.2. Cấu trúc annotation của integration test

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private OrderRepository repository;

    // @Test các query/constraint cần kiểm trên PostgreSQL.
}
~~~

Đây là **snippet định hướng, không phải class compile độc lập**: bạn cần định nghĩa `Order`, `OrderRepository` và imports Testcontainers, Spring Data JPA, JUnit, Boot Test; cần schema migration/DDL phù hợp. `@ServiceConnection` (Boot Testcontainers) giúp tạo connection details từ container; trong Spring Boot 3.3, `replace = NONE` bảo vệ DataSource test không bị embedded replacement mặc định.

**Quan trọng về phiên bản:** Với Spring Boot 3.4+, policy mặc định `NON_TEST` đã có logic nhận diện một số DataSource từ Testcontainers, nên có thể không cần `replace = NONE` trong nhiều trường hợp auto-configured được nhận diện đúng. Nhưng nếu chủ đích là **không thay DataSource** theo bất kỳ chính sách implicit nào, khai báo `NONE` là cách bảo đảm intent rõ ràng và tương thích giữa 3.3/3.4+.

### 6.3. Nếu dùng `@DynamicPropertySource`

Một pattern khác là Testcontainers cung cấp JDBC URL/user/password bằng dynamic properties:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Snippet này yêu cầu một biến container `postgres` đã được tạo, cùng imports; chưa phải test độc lập. Trong Boot 3.3, ngay cả khi dynamic properties trỏ đúng PostgreSQL, `@DataJpaTest` mặc định replacement ANY có thể **thay DataSource đi H2**, nên thêm `@AutoConfigureTestDatabase(replace = NONE)`. Từ 3.4, auto-configured datasource có URL qua `@DynamicPropertySource` là một dạng mà `NON_TEST` có thể nhận diện là test DB.

Không vừa dùng `@ServiceConnection` vừa khai báo toàn bộ dynamic properties cùng mục đích **mà không cần thiết**. Chọn một cách nối container rõ ràng, phù hợp version, và giữ cấu hình dễ kiểm chứng.

### 6.4. Kiểm database thực sự được dùng

Một test repository pass **không đủ chứng minh PostgreSQL** nếu SQL được H2 hỗ trợ và datasource đã bị thay. Có thể assert JDBC metadata bằng một test diagnostic:

~~~java
try (Connection connection = dataSource.getConnection()) {
    String product = connection.getMetaData()
            .getDatabaseProductName();

    assertEquals("PostgreSQL", product);
}
~~~

Đây là snippet cần `dataSource`, `assertEquals`, `Connection` và imports phù hợp. Dùng `getDatabaseProductName()` làm kiểm tra hạ tầng rõ ràng, không nhất thiết phải in credentials hoặc full connection URL vào CI log. Khi kiểm vendor-specific migration, test cần xác nhận engine tương thích và fixture DB có đúng schema.

## 7. Nhiều `DataSource`: giới hạn cần biết

`@AutoConfigureTestDatabase` **không có nghĩa sẽ thay tất cả DataSource trong context**. Theo Javadoc của Spring Boot 3.3, khi có **nhiều bean `DataSource`**, cơ chế test database auto-configuration chỉ **cân nhắc `@Primary DataSource`**.

Ví dụ:

~~~java
@Configuration
class MultiDataSourceConfig {

    @Bean
    @Primary
    DataSource ordersDataSource() {
        // ...
    }

    @Bean
    DataSource auditDataSource() {
        // ...
    }
}
~~~

Đây là **snippet minh họa**, chưa có implementation. Nếu test cần cả `ordersDataSource` và `auditDataSource` cùng hoạt động đúng, đừng giả định `@AutoConfigureTestDatabase(replace = ANY)` tự tạo hai embedded databases hoặc thay cả hai. Bạn phải cấu hình chính xác từng datasource/transaction manager/repository scan và xác minh cả hai thông qua qualifier, metadata hoặc test riêng.

### `@Primary` và `@Qualifier` khác replacement policy

- `@Primary` giải quyết việc **chọn bean theo type** khi có nhiều DataSource candidates.
- `@Qualifier("auditDataSource")` chọn bean cụ thể tại injection point.
- `@AutoConfigureTestDatabase` xét policy thay test DataSource trên **phạm vi bean mục tiêu**, không phải quy tắc chọn mọi JDBC connection trong toàn bộ ứng dụng.
- `spring.main.allow-bean-definition-overriding` liên quan đăng ký bean definition trùng **tên**, **không** tương đương với `Replace.ANY/NONE`.

Nếu một repository được nối rõ với `auditDataSource` và transaction manager riêng, việc embedded replacement chỉ ảnh hưởng primary DataSource có thể khiến repository đó vẫn trỏ vào DB thật. Đây là tình huống cần **kiểm hạ tầng của từng DataSource** và bảo vệ credentials, network của môi trường test.

## 8. Policy test an toàn: không kết nối production ngoài ý muốn

Trong các test repository tích hợp, một lỗi cấu hình kết nối có thể nguy hiểm hơn việc test fail: test có thể **xóa, sửa hoặc migrate dữ liệu thật**. Thiết kế chính sách hạ tầng trước khi chọn annotation.

### Checklist bảo vệ bắt buộc

1. **Database riêng:** dùng H2 in-memory hoặc container DB tạm thời. Không dùng connection string/credentials production.
2. **Credentials test:** account riêng, quyền tối thiểu cần thiết; không nhúng password thật vào `application-test.yml` được commit.
3. **Network isolation:** CI chỉ truy cập test database/container đã cấp, không cho đường dẫn vô tình đến production.
4. **Kiểm DataSource runtime:** khi test đòi PostgreSQL, assert database product name; nếu cần, kiểm JDBC URL đã được sanitize, không chứa production host.
5. **Schema/namespace:** dùng schema/database dành riêng test, tên xác định; reset dữ liệu theo fixture.
6. **Migration:** nếu dùng Flyway/Liquibase, chỉ chạy trên test DB đã xác minh, với migration hợp lệ cho engine đó.
7. **Transaction:** hiểu rollback của test slice thường bảo vệ dữ liệu DML trong transaction test, nhưng không thay được network isolation; DDL và side effect ngoài transaction có thể không rollback theo cách mong muốn.
8. **No secrets in logs:** không in JDBC URL đầy đủ nếu nó có credentials/token; tránh debug datasource properties ở CI không kiểm soát.

Nếu mục tiêu test chỉ kiểm domain logic không cần SQL, **không cần tạo DataSource**. Unit test Java thuần với dependency được tiêm qua constructor thường an toàn, nhanh và rõ hơn.

## 9. H2 nhúng so với DB production: phạm vi bằng chứng

| Đặc điểm | Embedded H2/HSQLDB/Derby | PostgreSQL/MySQL trong Testcontainers |
| --- | --- | --- |
| Yêu cầu container runtime | Không | Có, thường cần Docker hoặc compatible runtime |
| Thời gian setup | Thường nhanh | Có thời gian khởi động container, image |
| SQL dialect khớp production | Không đảm bảo | Cao hơn nếu cùng DB engine/version |
| Các kiểu `jsonb`, array, enum DB riêng | Có thể không được hỗ trợ hoặc khác ngữ nghĩa | Kiểm trực tiếp engine phù hợp |
| Migration và index/constraint | Có thể khác production | Gần hơn với production |
| Tính cô lập | Tốt khi mỗi test context có DB độc lập | Tốt nếu container/schema/fixture được quản lý độc lập |
| Độ tin cậy của native query | Giới hạn theo dialect | Tốt hơn khi đúng DB |
| Phù hợp | CRUD đơn giản, smoke JPA/JDBC, phản hồi nhanh | Integration SQL quan trọng, migration, constraint, vendor-specific behavior |

**Không có công thức “mọi test phải chạy PostgreSQL”**. Một chiến lược hợp lý thường có nhiều lớp: unit tests cho domain, slices với embedded DB cho kiểm nhanh, và một tập integration tests Testcontainers cho behavior phụ thuộc DB engine thực tế.

Một test H2 pass **không phải lỗi** nếu mục tiêu chỉ là kiểm mapper hoặc CRUD tương thích; vấn đề là **hiểu nhầm** test H2 đã chứng minh query/migration trên DB production.

### H2 compatibility mode có thay PostgreSQL thật không?

H2 có compatibility modes cho một số dialect, nhưng không tái tạo đầy đủ SQL planner, isolation, extension, collation, index behavior, data type hoặc migration semantics của PostgreSQL. Dùng mode như một công cụ hỗ trợ test nhất định, không tuyên bố nó đồng nhất với production DB. Với tính năng đặc thù, hãy kiểm trên engine tương ứng.

## 10. Transaction, rollback và database lifecycle

### `@DataJpaTest` và `@JdbcTest` thường transactional

Trong Spring Boot test slices, nhiều kiểu `@DataJpaTest`/`@JdbcTest` được cấu hình transaction và rollback sau mỗi test theo mặc định. Điều này giúp test DML độc lập hơn khi cùng context/database được dùng lại.

Nhưng rollback **không tự động bảo đảm**:

- Đã kết nối đúng test DB.
- DDL/migration/trigger tác động ngoài transaction sẽ hoàn tác.
- Side effect qua service ngoài (HTTP, message broker, email) được hoàn tác.
- Test HTTP với server thread khác sẽ rollback theo transaction của test thread.
- Mỗi test luôn có database mới; context cache có thể tái sử dụng DataSource.
- Không còn dữ liệu nếu một test chủ động commit, dùng propagation khác, hoặc tạo state ngoài transaction.

`@Transactional` và database replacement giải quyết **hai vấn đề khác nhau**: một bên quản lý transaction boundary, bên kia quyết định DataSource thực tế. Đừng dùng cái này để thay cái kia.

### Context caching và database nhúng

Spring TestContext có thể cache context giữa nhiều test classes có cấu hình tương đương. Nếu H2 in-memory và connection pool được giữ cùng context, database có thể sống nhiều test. `DB_CLOSE_DELAY=-1` trong JDBC URL cũng có thể khiến H2 DB tồn tại tới khi JVM kết thúc ngay cả khi connection đã đóng.

Vì vậy:

- Đừng viết test A chuẩn bị dữ liệu để test B dựa vào nếu không phải một fixture có chủ đích.
- Reset fixture hoặc dùng `@Sql`, repository cleanup, transaction phù hợp.
- Không coi `@DirtiesContext` là công cụ reset dữ liệu mặc định: nó khiến context phải tạo lại, tốn thời gian.
- Khi test DB có nhiều schema hoặc cần rollback chính xác, thiết kế isolation tại DB level thay vì chỉ dựa vào Spring context caching.

### Sử dụng `@Sql` có đúng không?

`@Sql` có thể chạy script để chuẩn bị dữ liệu test trong Spring TestContext, nhưng chỉ an toàn khi bạn biết script sẽ chạy **trên DataSource nào** và theo transaction mode nào. Nếu có nhiều DataSources, annotation/script có thể cần chỉ rõ dataSource/transaction manager đúng. Một script `DELETE FROM orders` không nên chạy trước khi đã bảo đảm datasource không phải production.

## 11. `@SpringBootTest` với `@AutoConfigureTestDatabase`

`@SpringBootTest` nạp Boot application context, nhưng khác test slices: annotation này **không mặc định đem theo mọi test database replacement auto-configuration** như `@DataJpaTest`. Nếu muốn full context vẫn dùng embedded DB, có thể thêm `@AutoConfigureTestDatabase` hoặc cấu hình test datasource rõ ràng:

~~~java
@SpringBootTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2)
class ApplicationWithEmbeddedDbTest {
    // @Autowired DataSource / services...
}
~~~

Snippet minh họa, cần import và cấu hình app tương ứng. Với ứng dụng có nhiều database, `@ConfigurationProperties`, migration hoặc customized JDBC wiring, việc thêm annotation không tự sửa mọi dependency: phải kiểm DataSource thực tế. Trong codebase lớn, sử dụng test profile và container DB có chủ đích thường rõ hơn việc cố thay dữ liệu ở full context mà không biết hạ tầng gì đang bật.

### Khi nào không dùng annotation này?

- Unit test thuần Java không có Spring context.
- Test controller `@WebMvcTest` chỉ mock service, không chạm repository/JDBC.
- Test chỉ xác minh Jackson/validation không phụ thuộc DB.
- Module R2DBC dùng `ConnectionFactory` thay vì JDBC `DataSource`. `@AutoConfigureTestDatabase` là cơ chế cho JDBC DataSource; R2DBC có policy và auto-configuration riêng, không suy ra annotation này thay mọi reactive connection factory.

## 12. `spring.test.database.replace` và việc cấu hình từ properties

`@AutoConfigureTestDatabase` được ánh xạ đến namespace property `spring.test.database`. Có thể thấy cấu hình `spring.test.database.replace` trong môi trường test của Boot, ví dụ:

~~~properties
spring.test.database.replace=NONE
~~~

Tuy nhiên, annotation/meta-annotation trên test slice, property mapping và giá trị default tương tác theo phiên bản. Khi cần behavior không mơ hồ trong một test cụ thể, **khai báo trực tiếp `@AutoConfigureTestDatabase(replace = Replace.NONE)`** trên class giúp reviewer đọc ngay chính sách mà không phải truy nhiều file property.

**Không đặt property này vào production configuration** như một cách điều khiển datasource runtime. Nó thuộc **test database auto-configuration**; production nên cấu hình datasource/driver/connection pool theo hợp đồng triển khai.

### Không lẫn với bean definition overriding

`@AutoConfigureTestDatabase(replace = ANY)` và `spring.main.allow-bean-definition-overriding=true` không phải hai cách viết cùng một chức năng:

- Test database replacement là cơ chế Boot **chọn/thay DataSource trong context kiểm thử** theo policy.
- Bean definition overriding là cài đặt BeanFactory cho phép một definition **cùng tên** ghi đè definition khác, có rủi ro riêng.
- `@Primary` và `@Qualifier` giải quyết **phân giải candidate theo type/metadata**.

Nếu DataSource test không được chọn, hãy tìm nguyên nhân ở **test database auto-configuration, cách cấu hình DataSource, tên/type/qualifier và Boot version**, không bật bean overriding toàn cục để thử vận may.

## 13. Lỗi phổ biến và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| Test định dùng PostgreSQL nhưng thực tế H2 | Boot 3.3 `@DataJpaTest` có default `Replace.ANY` | Dùng `Replace.NONE` và kiểm metadata |
| `Replace.NON_TEST` không compile | Project đang dùng Boot 3.3 hoặc cũ hơn | Dùng `NONE`/`ANY`/`AUTO_CONFIGURED` có sẵn ở version đó |
| Boot 3.4+ vẫn replace DB thủ công | `NON_TEST` nhận diện dựa trên auto-configuration + test DB metadata | Dùng `NONE` nếu cần giữ DataSource chắc chắn |
| `Failed to replace DataSource with an embedded database` | Thiếu H2/HSQLDB/Derby driver phù hợp trên test runtime | Thêm test runtime driver hoặc đổi policy/connection phù hợp |
| `Cannot determine a suitable driver class` | Datasource URL/driver thiếu hoặc driver không có trên classpath | Kiểm JDBC URL, dependency và test profile |
| `Connection refused` tới DB | Test giữ DataSource nhưng DB server/container chưa sẵn sàng | Khởi tạo DB test đúng cách, kiểm host/port và lifecycle |
| `FATAL: database does not exist` | URL/schema DB test sai | Tạo DB test đúng và dùng test credentials |
| Hibernate lỗi vì SQL syntax | H2 dialect khác PostgreSQL hoặc migration không tương thích | Chạy integration test trên engine production tương ứng |
| `No qualifying bean of type DataSource` | Context không có datasource config hoặc slice không nạp bean dự kiến | Kiểm test slice, auto-config, driver và bean registration |
| Multiple DataSource test sai DB | Chỉ primary DataSource được replacement xét tới | Cấu hình từng DataSource/qualifier và assert từng JDBC URL |
| Cùng test pass đơn lẻ, fail cả suite | Database state hoặc context cache/shared fixtures | Cleanup dữ liệu, tránh state giữa test, kiểm transactions |
| Bật `replace = NONE` rồi test kết nối production | DataSource đang dùng config production thật | Cấm production credentials/network, dùng test URL riêng |
| Test pass nhưng migration production fail | Chỉ kiểm H2, không kiểm vendor SQL | Thêm Testcontainers migration/repository integration test |
| Unit test nhanh trở thành chậm | Tải DB/container dù không cần | Tách domain unit test, chỉ DB tests ở đúng tầng |
| `@SpringBootTest` không tự dùng H2 | Full context không có slice database replacement mặc định | Cấu hình DB test tường minh hoặc dùng annotation phù hợp |
| Testcontainers được tạo nhưng không có container connection | Thiếu `@ServiceConnection`/`@DynamicPropertySource`/dependency | Kết nối container vào datasource auto-config đúng phiên bản |

### Quy trình chẩn đoán từng bước

1. **Xác định phiên bản Boot:** in/kiểm dependency tree để biết có `NON_TEST` hay không; không dựa vào blog của bản khác.
2. **Xác định test annotation:** `@DataJpaTest`, `@JdbcTest`, `@SpringBootTest` hay loại khác? Replacement có đang được kích hoạt không?
3. **Xác định policy thực tế:** `ANY`, `AUTO_CONFIGURED`, `NONE` hoặc `NON_TEST`. Có override ở class test không?
4. **Kiểm embedded driver:** H2/HSQLDB/Derby có trong test runtime classpath không?
5. **Kiểm DataSource runtime:** dùng JDBC `getMetaData().getURL()`/`getDatabaseProductName()` khi phù hợp, **không log secret**.
6. **Kiểm container/migration:** container đã chạy, DB đã sẵn sàng, schema đúng, credential là test-only?
7. **Đọc root cause:** `Failed to load ApplicationContext` chỉ là lỗi ngoài; exception bên trong thường chỉ ra driver, URL, DDL hoặc query.
8. **Đánh giá mục tiêu test:** cần engine thật hay chỉ CRUD/JDBC cơ bản? Đổi đúng mức test, không sửa production config vì một test setup thiếu.

## 14. Quy trình chọn chính sách thay thế cho dự án

Dùng bảng quyết định sau làm điểm khởi đầu, rồi xác minh bằng test thực tế:

| Mục tiêu | Ví dụ | Policy đề xuất |
| --- | --- | --- |
| Kiểm SQL cơ bản, chấp nhận H2 | `@JdbcTest` với H2 test runtime | `ANY` hoặc default thích hợp theo phiên bản |
| Kiểm JDBC/JPA trên một H2 URL do test chọn | `spring.datasource.url=jdbc:h2:mem:chosen` | `NONE` nếu cần giữ đúng URL |
| Kiểm Hibernate/JPA/native query trên PostgreSQL Testcontainers, Boot 3.3 | `@DataJpaTest` + container | **`NONE`** |
| Kiểm Testcontainers, Boot 3.4+ | DataSource được auto-configured và nhận diện là test DB | Default `NON_TEST` thường phù hợp; `NONE` nếu cần intent chắc chắn |
| Thay bất kỳ DataSource nào bằng embedded DB | Test không quan tâm DB nguyên bản | **`ANY`**, có H2/HSQLDB/Derby driver |
| Chỉ thay DataSource do Boot auto-configure | Tránh thay một DataSource khai báo thủ công | `AUTO_CONFIGURED` |
| Kiểm DataSource custom nhiều bean | Primary + các named DataSources | Cấu hình và test riêng từng bean; annotation không thay tất cả |
| Kiểm full integration có DB engine thật | `@SpringBootTest` + Testcontainers | Cấu hình Testcontainers rõ ràng; thường **không muốn embedded replacement** |
| Kiểm logic không cần DB | Domain service/validator | Không dùng annotation; unit test Java thuần |

Chọn policy dựa trên **bằng chứng cần thu thập**, không chỉ mục tiêu “test chạy xanh”. Nếu một test sinh SQL phức tạp nhưng luôn được Boot đổi sang H2, việc pass có thể không mang ý nghĩa về PostgreSQL. Nếu test chỉ kiểm phép tính tiền, một container PostgreSQL lại làm tăng độ phức tạp vô ích.

## 15. Bài tập thực hành

**Bài A — kiểm replacement thật:** Trong demo, chạy `ReplacedDataSourceJdbcTest`. Quan sát test không cần hardcode tên H2 generated; assertion chỉ xác nhận đúng loại DB và **không còn URL có `configureddb`**. Đổi `replace = ANY` thành `NONE` và dự đoán ca `assertFalse(jdbcUrl.contains("configureddb"))` sẽ fail. Hoàn nguyên.

**Bài B — bảo toàn cấu hình:** Với `PreservedDataSourceJdbcTest`, đổi JDBC URL ở annotation sang `jdbc:h2:mem:anotherdb;DB_CLOSE_DELAY=-1` nhưng giữ expected `keptdb`. Test phải fail. Điều này cho thấy assertion phát hiện DB nào được dùng, không chỉ kiểm một query bất kỳ.

**Bài C — thử thiếu embedded driver:** Trong nhánh test riêng, bỏ H2 dependency và giữ `replace = ANY, connection = H2`. Dự đoán context không tạo được embedded datasource; đọc root cause và hoàn nguyên. Không sửa source code nghiệp vụ để che lỗi driver.

**Bài D — đổi Boot version:** Tra Javadoc của 3.3 và 3.4, ghi rõ default `ANY` vs `NON_TEST`. Giải thích vì sao `Replace.NON_TEST` không tồn tại ở 3.3 và tại sao cùng `@DataJpaTest` + Testcontainers có thể chọn DB khác sau nâng version.

**Bài E — kiểm vendor-specific behavior:** Tạo một test repository dùng kiểu PostgreSQL `jsonb` hoặc native query. Chạy trên PostgreSQL Testcontainers và đối chiếu với H2; phân tích sự khác biệt thay vì dùng compatibility mode của H2 để khẳng định hai engine giống hệt.

**Bài F — đảm bảo isolation:** Trong test slice JPA, thêm một test ghi entity rồi rollback. Kiểm test tiếp theo không thấy entity do fixture độc lập; giải thích tại sao rollback vẫn không bảo vệ khỏi việc kết nối sai production DB hoặc chạy migration DDL ở hạ tầng thật.

**Bài G — nhiều DataSources:** Trong một test context có primary và audit datasource, kiểm URL của từng bean thông qua qualifier. Đổi policy primary rồi xác nhận URL audit không bị thay ngoài dự kiến.

## 16. Checklist trước khi merge database test

- [ ] Tôi biết phiên bản Spring Boot thực và enum `Replace` có những giá trị nào?
- [ ] Test đang dùng `@DataJpaTest`/`@JdbcTest` hay full `@SpringBootTest`?
- [ ] Mục tiêu test là SQL cơ bản, mapping JPA hay behavior của database engine production?
- [ ] Tôi đã chọn policy rõ ràng: `ANY`, `AUTO_CONFIGURED`, `NONE` hoặc `NON_TEST` khi phiên bản hỗ trợ?
- [ ] Nếu dùng Testcontainers ở Boot 3.3, tôi đã ngăn replacement không mong muốn bằng `Replace.NONE`?
- [ ] H2/HSQLDB/Derby driver tồn tại trên test runtime khi mong embedded replacement?
- [ ] Nếu `replace=NONE`, test DataSource có URL, credential và DB server **an toàn, tách production**?
- [ ] Tôi có ít nhất một phép xác minh **DataSource runtime** khi hạ tầng DB là một phần mục tiêu?
- [ ] Tôi đã phân biệt `connection=NONE` với `replace=NONE`?
- [ ] Với nhiều DataSources, tôi không mặc định annotation thay mọi bean?
- [ ] Migration/transaction/data cleanup đã phù hợp với engine và test slice chưa?
- [ ] Test không chứa production password hoặc cho CI truy cập production DB?
- [ ] Assertion kiểm đúng business/query contract, không chỉ “kết nối được”?
- [ ] Gradle/JUnit report có xác nhận số test thực thi, không chỉ task `UP-TO-DATE`?

## 17. Tài liệu tham khảo

Các nguồn Spring Boot chính thức dưới đây dùng để kiểm đối chiếu **đúng phiên bản**. Cần dùng tài liệu tương ứng với dependency của dự án trước khi thay policy trong repository thực.

- [Spring Boot 3.3 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html): policy default **ANY**, lựa chọn `connection` và giới hạn primary `DataSource`.
- [Spring Boot 3.3 — Replace API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, `@JdbcTest`, cách giữ real database bằng `Replace.NONE`.
- [Spring Boot 3.4 — Replace API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): bổ sung `NON_TEST` và logic nhận diện test databases.
- [Spring Boot 3.4 — Testcontainers](https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html): `@ServiceConnection`, `@DynamicPropertySource` và cách dùng container test.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): thay đổi chính sách test database replacement để giảm nhu cầu `replace=NONE` với container.

**Ghi nhớ:** `@AutoConfigureTestDatabase` là **chính sách thay DataSource ở test context**. `ANY` có thể đổi datasource đã cấu hình sang embedded DB; `NONE` giữ datasource đã chỉ định nhưng **không tự khiến nó an toàn**; `AUTO_CONFIGURED` chỉ giới hạn theo nguồn bean; `NON_TEST` (Boot 3.4+) giúp bảo toàn những auto-configured datasource được nhận diện là test DB. Hãy luôn **kiểm database thực tế**, đặc biệt khi test phải chạy trên PostgreSQL/MySQL hoặc trong hệ thống có nhiều DataSources.
