# Tách dữ liệu kiểm thử khỏi seed data của ứng dụng

## 1. Vì sao cần tách?

Trong ứng dụng Spring Boot, dữ liệu được nạp lúc startup và dữ liệu phục vụ test thường bị gọi chung là **seed data**. Nhưng hai nguồn này có mục tiêu khác nhau. Dữ liệu demo giúp developer mở ứng dụng và thấy vài sản phẩm; test fixture chỉ tạo precondition để kiểm tra một behavior; dữ liệu tham chiếu bắt buộc lại là một phần của contract nghiệp vụ. Nếu trộn chúng, repository test có thể phụ thuộc vào sản phẩm demo, CI có thể chạy khác local hoặc test A để lại dữ liệu khiến test B thất bại.

Ví dụ một test:

```java
assertEquals(3L, catalogRepository.count());
```

không đáng tin nếu ba sản phẩm đó được seed bởi một runner toàn cục: người phụ trách demo có thể thêm sản phẩm thứ tư mà không hề đổi logic repository. Kết quả test đỏ phản ánh coupling vào demo, không phải regression nghiệp vụ.

Bài học thuộc nhóm **Dữ liệu kiểm thử** và tập trung chính xác vào **“Tách dữ liệu kiểm thử khỏi seed data của ứng dụng”**. Chúng ta dùng **Java 17+, Spring Boot 3.3.5**, Spring Data JPA/Hibernate, H2, JUnit Jupiter và Spring Test `@Sql`. Mục tiêu là một project minh họa đủ file, có lệnh chạy và assertions cụ thể.

### Kết quả sau bài học

- Phân biệt **reference data**, **development/demo seed** và **per-test fixtures**.
- Hiểu những cơ chế có thể tự nạp dữ liệu: `data.sql`, `import.sql`, Flyway/Liquibase, `ApplicationRunner`, `CommandLineRunner` và `@Sql`.
- Biết vì sao `src/test/resources` giúp tránh đóng gói fixture trong jar production nhưng **không tự ngăn main resources tham gia test runtime**.
- Dùng `@Profile("dev")` để giới hạn demo seed, `@ActiveProfiles("test")` cho cấu hình test và `spring.sql.init.mode=never` để tắt SQL initializer tự động.
- Nạp fixture riêng từ `src/test/resources/fixtures/catalog-items.sql` bằng `@Sql`.
- Hiểu rollback transaction mặc định của `@DataJpaTest`, cũng như trường hợp real HTTP/server thread không nằm trong transaction của test.
- Test rằng profile test không có demo rows, test fixture chỉ nạp khi được khai báo, còn profile dev thực sự có dữ liệu demo.
- Thiết kế data factories, migrations, cleanup, CI và database isolation để suite có thể tái hiện.

**Phạm vi:** ví dụ chọn Spring Boot 3.3.5 để các imports/API nhất quán. Các hệ thống chạy phiên bản khác cần kiểm tra package và hành vi của phiên bản đó; không xem 3.3.5 là bản mới nhất.

## 2. Ba loại dữ liệu phải có ownership khác nhau

| Loại dữ liệu | Ví dụ | Nơi thích hợp | Được phép xuất hiện trong test nào? |
| --- | --- | --- | --- |
| **Reference/master data** bắt buộc | Mã trạng thái nghiệp vụ, loại phí, các quyền cố định | Migration chính thức hoặc bootstrap có version | Những tests cần contract đó |
| **Development/demo seed** | Sản phẩm DEV-CUP, DEV-BAG để xem màn hình local | Profile `dev`, dev-only loader hoặc dev-only script | Chỉ khi test chủ ý kiểm tra demo profile |
| **Test/scenario fixture** | TEST-BOOK, TEST-CABLE phục vụ query | `src/test/resources`, `@Sql`, test factory | Test nào cần thì nạp test đó |

### Reference data không phải “rác”

Có những hàng bắt buộc cho ứng dụng chạy đúng, ví dụ trạng thái đơn hàng và mã nghiệp vụ. Chúng nên được versioned và kiểm tra giống migrations/schema. Đừng loại mọi reference rows khỏi test để ép baseline là database trống; nếu production luôn có một nhóm mã chuẩn, test cũng phải chấp nhận và xác nhận những mã đó.

### Demo seed không phải contract của repository

Dữ liệu demo thường thay đổi theo nhu cầu trải nghiệm UI. Repository test không nên assert giá sản phẩm DEV-CUP hay tổng số demo rows trừ khi **chính loader demo** là đối tượng đang test. Với query tests, tạo các rows test riêng, ổn định, tối thiểu và có ý nghĩa phân biệt.

### Fixtures không nên được tạo bằng side effect ngầm

Fixture tốt phải rõ trong test class hoặc test method: `@Sql("/fixtures/...")`, `repository.save(...)` trong Arrange hoặc test object builder. Nếu test không biết dữ liệu đến từ một `ApplicationRunner` nào đó thì assertion rất khó debug và thứ tự tests dễ tạo ô nhiễm.

Trong project này, **không có reference data bắt buộc**, nên JPA test không yêu cầu fixture sẽ có thể assert `count()==0`. Trong sản phẩm có reference tables, điều chỉnh baseline và lọc theo namespace/row scope thay vì assert toàn database trống.

## 3. Các đường dữ liệu xuất hiện trong Spring Boot

| Cơ chế | Khi chạy | Rủi ro |
| --- | --- | --- |
| `schema.sql`/`data.sql` | Spring Boot SQL initializer | Main resource có thể tự chạy trong embedded test database |
| `schema-PLATFORM.sql`/`data-PLATFORM.sql` | Khi `spring.sql.init.platform` được đặt | Dataset thay đổi theo platform |
| Hibernate `import.sql` | Khi Hibernate tạo schema bằng `create`/`create-drop` | Có thể seed dù Boot SQL initializer bị tắt |
| Flyway/Liquibase | Migrations khi context khởi tạo | Test-only data bị đưa nhầm vào production migration |
| `CommandLineRunner`/`ApplicationRunner` | Sau application context startup | Loader thiếu guard chạy trong tests |
| `@PostConstruct`/event listeners | Bean/app lifecycle | Seed side effect không rõ chỗ gọi |
| `@Sql` | TestContext theo annotation và execution phase | Class-level fixture làm test khác nhận dữ liệu không cần |
| `@BeforeEach`/factory | Test method lifecycle | Fixture lớn hoặc mutable shared objects |
| DB snapshot/bootstrap ngoài ứng dụng | Trước test start | Data trùng hoặc không nhất quán với schema hiện tại |

### Spring Boot SQL init và điều kiện mặc định

Spring Boot 3.3 tìm các đường dẫn dạng `optional:classpath*:schema.sql` và `optional:classpath*:data.sql`. Với embedded database, SQL initializer có thể chạy tự động theo policy mặc định. `spring.sql.init.mode=always` khiến initializer chạy cả trên non-embedded datasource khi có script, còn `spring.sql.init.mode=never` tắt riêng cơ chế SQL script initialization của Boot.

Nếu cần `data.sql` chạy **sau** schema do Hibernate tạo, có `spring.jpa.defer-datasource-initialization=true`. Dù vậy, trộn nhiều schema management mechanisms thường làm thứ tự khó quản lý. Khi dự án dùng migration tool, ưu tiên một nguồn quản lý schema rõ ràng.

**Bẫy:** `spring.sql.init.mode=never` **không** tắt `import.sql` do Hibernate xử lý, không tắt Flyway/Liquibase, không tắt runner và không tắt một `@Sql` được test chủ động yêu cầu.

### Tại sao src/test/resources chưa đủ?

Gradle test runtime nhìn thấy cả main và test classes/resources. Vì vậy test fixture ở `src/test/resources` **không được đưa vào production executable jar**, nhưng `src/main/resources/data.sql` vẫn có thể xuất hiện trong test classpath. Cần xử lý cả **đường nạp** và **profile**; không chỉ di chuyển một số file.

## 4. Kiến trúc demo: chỉ nạp demo bằng profile dev

```text
PRODUCTION-LIKE DEFAULT:
  application.yml: SQL auto init disabled
  Không có main data.sql hoặc import.sql

DEV:
  application-dev.yml: H2 và ddl-auto=create-drop
  @Profile("dev") ApplicationRunner -> DEV-CUP, DEV-BAG

TEST:
  application-test.yml: H2 test schema, SQL auto init disabled
  @DataJpaTest + @ActiveProfiles("test")
  Không tự load demo runner
  @Sql("/fixtures/catalog-items.sql") -> chỉ nạp TEST-* khi cần
  Test transaction rollback sau mỗi method
```

Đây là thiết kế học tập, không phải cấu hình production database: không dùng Hibernate `create-drop` cho dữ liệu thật và không dùng H2 trong production chỉ vì nó tiện cho demo.

## 5. Project Java 17+ đầy đủ

Cây thư mục:

```text
isolated-test-data/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/catalog/
│   ├── CatalogApplication.java
│   ├── CatalogItem.java
│   ├── CatalogRepository.java
│   └── DevCatalogSeedConfig.java
├── src/main/resources/
│   ├── application.yml
│   └── application-dev.yml
├── src/test/java/com/example/catalog/
│   ├── CatalogTestObjects.java
│   ├── CatalogWithoutSeedTest.java
│   ├── CatalogFixtureSqlTest.java
│   └── DevSeedProfileTest.java
└── src/test/resources/
    ├── application-test.yml
    └── fixtures/catalog-items.sql
```

### 5.1. settings.gradle

```groovy
rootProject.name = 'isolated-test-data'
```

### 5.2. build.gradle

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-data-jpa` cung cấp Hibernate/JPA và Spring Data repositories. H2 cần `runtimeOnly` để cả lệnh chạy dev app lẫn test runtime có driver. `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring TestContext, `@DataJpaTest` và assertions.

Gradle Wrapper không được liệt kê trong cây thư mục minh họa; nếu project chưa có `gradlew`, phải tạo Wrapper bằng Gradle tương thích hoặc dùng `gradle test` trên máy đã cài Gradle. Không gọi `./gradlew` trên một thư mục chưa hề có Wrapper rồi coi lỗi thiếu file là test failure.

### 5.3. CatalogApplication.java

`src/main/java/com/example/catalog/CatalogApplication.java`:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Application root cùng package với entity/repository/config. Spring Boot component scan có thể tìm dev seed config trong full context; `@DataJpaTest` dùng package hierarchy để tìm Boot configuration nhưng cố ý chỉ nạp JPA slice.

## 6. Entity và repository

### 6.1. CatalogItem.java

`src/main/java/com/example/catalog/CatalogItem.java`:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(name = "price_cents", nullable = false)
    private int priceCents;

    @Column(nullable = false)
    private boolean featured;

    protected CatalogItem() {
        // JPA constructor.
    }

    public CatalogItem(
            String sku, String title,
            int priceCents, boolean featured) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (priceCents < 0) {
            throw new IllegalArgumentException(
                    "priceCents must be non-negative");
        }

        this.sku = sku;
        this.title = title;
        this.priceCents = priceCents;
        this.featured = featured;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public int getPriceCents() {
        return priceCents;
    }

    public boolean isFeatured() {
        return featured;
    }
}
```

`sku` là ID gán tường minh: giá trị `TEST-BOOK` và `DEV-CUP` luôn có thể đọc, không phụ thuộc auto-increment sequence có rollback hay không. `priceCents` là integer minor units để tránh so sánh tiền qua `double` trong test.

Lớp có protected no-arg constructor cho JPA. Đây không phải Java record vì entity cần state và lifecycle Hibernate quản lý. Constructor chỉ bảo vệ invariant Java cục bộ; nếu cần database CHECK/unique/foreign-key constraints thật, phải thể hiện trong schema/migration tương ứng.

### 6.2. CatalogRepository.java

`src/main/java/com/example/catalog/CatalogRepository.java`:

```java
package com.example.catalog;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, String> {

    List<CatalogItem> findByFeaturedTrueOrderBySkuAsc();

    List<CatalogItem> findByPriceCentsBetweenOrderBySkuAsc(
            int minimum, int maximum);
}
```

Hai derived queries sẽ được test trên **scenario fixture**, không dựa vào hàng demo. Có `OrderBySkuAsc` vì SQL không bảo đảm thứ tự nếu thiếu ORDER BY, kể cả khi H2 tình cờ trả theo primary key.

## 7. Cấu hình mặc định không tự seed

`src/main/resources/application.yml`:

```yaml
spring:
  sql:
    init:
      mode: never
  jpa:
    open-in-view: false
```

Property `spring.sql.init.mode=never` tắt Spring Boot JDBC SQL initializer. Project chủ động **không có** file `src/main/resources/data.sql` hoặc `src/main/resources/import.sql`. Khi không có profile dev, app cũng không có loader nạp demo rows.

**Không hiểu nhầm:** mode never không ngăn `ApplicationRunner`, Hibernate `import.sql`, Flyway/Liquibase hoặc Spring Test `@Sql` nếu các cơ chế ấy tồn tại. Vì thế kiến trúc này còn dùng positive profile guard cho runner và test assertion rằng demo rows không bị nạp.

Trong production thật, thường dùng Flyway/Liquibase migrations và DataSource external. Không để sample `create-drop` ở default configuration, bởi startup nhầm môi trường có thể mất schema.

## 8. application-dev.yml và ApplicationRunner có guard

`src/main/resources/application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog_dev;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  jpa:
    hibernate:
      ddl-auto: create-drop
```

`create-drop` là lựa chọn cho local demo H2. Hibernate tạo schema khi application context khởi động và drop khi context đóng. Nếu người học chạy với database có dữ liệu quan trọng, không được sử dụng setting này.

`src/main/java/com/example/catalog/DevCatalogSeedConfig.java`:

```java
package com.example.catalog;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
public class DevCatalogSeedConfig {

    @Bean
    ApplicationRunner createDemoCatalog(
            CatalogRepository repository) {

        return arguments -> {
            if (!repository.existsById("DEV-CUP")) {
                repository.save(new CatalogItem(
                        "DEV-CUP",
                        "Demo ceramic cup",
                        1250,
                        true));
            }

            if (!repository.existsById("DEV-BAG")) {
                repository.save(new CatalogItem(
                        "DEV-BAG",
                        "Demo canvas bag",
                        4200,
                        false));
            }
        };
    }
}
```

### Tại sao @Profile("dev")?

`@Profile("dev")` chỉ cho phép config/runner xuất hiện khi profile dev được bật. Đây là **positive allowlist**. Tránh `@Profile("!prod")` cho demo data: profile test/staging vẫn khớp `!prod` và demo seed có thể chảy vào môi trường ngoài ý muốn.

ApplicationRunner chạy sau khi Spring context startup, khi repository đã có thể được inject. Nó chỉ phục vụ hai sản phẩm giả dành cho dev; không phải migration versioned cho reference data quan trọng.

### Idempotency có giới hạn

`existsById` giúp khi cùng loader chạy lại trên database đã có key, nó không cố ý chèn trùng. Nhưng trong nhiều app instances chạy đồng thời vẫn có race giữa check và save. Đối với production bootstrap, unique constraints và migration/orchestration đáng tin hơn một loader dùng check-then-insert đơn giản.

### Kiểm soát việc chạy dev

Lệnh ví dụ (nếu có Gradle Wrapper):

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Dự án không có web starter, nên lệnh này khởi tạo database H2 và dev seed trong context; không tự tạo một REST endpoint. Không có stdout nghiệp vụ cố định từ loader, vì code không in dòng log riêng.

## 9. application-test.yml và embedded test database

`src/test/resources/application-test.yml`:

```yaml
spring:
  sql:
    init:
      mode: never
  jpa:
    hibernate:
      ddl-auto: create-drop
```

`@DataJpaTest` có cơ chế cấu hình DataSource embedded khi H2 có trên test runtime classpath. Trong ví dụ còn dùng tường minh:

```java
@DataJpaTest
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class ExampleJpaTest {
}
```

Đây là **snippet cấu hình**, không phải test method đầy đủ; class tests thật được khai báo sau. `@ActiveProfiles("test")` chọn `application-test.yml` và không kích hoạt profile dev. `@AutoConfigureTestDatabase(replace=ANY)` nêu rõ mục tiêu dùng embedded test DataSource thay vì DataSource thông thường.

**Giới hạn về bảo mật:** tên profile `test` không phải sandbox về network permissions. Nếu project có nhiều DataSources/custom connectors, phải xác minh đúng clients/transaction managers đang dùng tài nguyên thử nghiệm. Không chạy `repository.deleteAll()` trên production/shared database chỉ vì một test class có `@ActiveProfiles("test")`.

## 10. Fixture SQL chỉ chạy khi test yêu cầu

`src/test/resources/fixtures/catalog-items.sql`:

```sql
INSERT INTO catalog_items
    (sku, title, price_cents, featured)
VALUES
    ('TEST-BOOK', 'Testing Handbook', 1500, TRUE),
    ('TEST-DISPLAY', 'Display', 33000, TRUE),
    ('TEST-CABLE', 'USB Cable', 800, FALSE),
    ('TEST-PEN', 'Blue Pen', 200, FALSE);
```

Nhờ tên khác `data.sql` và đặt dưới test resources, Spring Boot SQL initializer không auto-run file này. Test chỉ nạp bằng `@Sql`:

```java
@Sql(
    scripts = "/fixtures/catalog-items.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
```

`@Sql` đến từ `org.springframework.test.context.jdbc.Sql`. Với class `@DataJpaTest` transactional và cấu hình thông thường, script chạy trong test-managed transaction trước mỗi method được áp dụng và rollback cùng method. **Không thêm `SqlConfig.TransactionMode.ISOLATED`** trong mẫu: khi setup được commit ở transaction riêng, rollback của test method không thể tự dọn nó.

### Vì sao là bốn hàng có chủ đích?

| SKU | Title | Price cents | Featured |
| --- | --- | ---: | --- |
| TEST-BOOK | Testing Handbook | 1500 | true |
| TEST-DISPLAY | Display | 33000 | true |
| TEST-CABLE | USB Cable | 800 | false |
| TEST-PEN | Blue Pen | 200 | false |

Query featured phải trả hai hàng BOOK và DISPLAY. Query giá trong khoảng [500, 2000] trả BOOK và CABLE. Cả hai tests đều assert order theo SKU vì repository method đã khai báo sorting. Không cần seed vài nghìn hàng để test hai derived queries.

### Điều @Sql không làm

`@Sql` không tự biến những rows thành production seed, không tự tạo schema nếu script chỉ chứa INSERT, và không bảo đảm rollback khi test không có transaction phù hợp hoặc dùng `ISOLATED`. Nó là cơ chế thực thi script trong TestContext theo phase và transaction configuration; bạn phải biết các settings ấy.

## 11. Java test object factory

`src/test/java/com/example/catalog/CatalogTestObjects.java`:

```java
package com.example.catalog;

final class CatalogTestObjects {

    private CatalogTestObjects() {
    }

    static CatalogItem simpleItem(
            String sku, int priceCents) {
        return new CatalogItem(
                sku, "Test-only item", priceCents, false);
    }
}
```

Mỗi lời gọi factory trả một object mới; không có mutable singleton entity dùng chung giữa tests. Factory phù hợp khi một method chỉ cần một item với default hợp lệ, trong khi SQL fixture thích hợp khi cần một nhóm rows biết trước để test query.

Một factory có thể hỗ trợ nhiều variations bằng builder, nhưng không nên che hết dữ liệu quan trọng. Nếu test kiểm tra `featured=true`, value featured phải thể hiện rõ ở Arrange; đừng giấu trong random fixture defaults.

## 12. CatalogWithoutSeedTest: không seed khi không yêu cầu

`src/test/java/com/example/catalog/CatalogWithoutSeedTest.java`:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(showSql = false)
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
class CatalogWithoutSeedTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void testProfileDoesNotLoadDemoSeed() {
        assertEquals(0L, repository.count());
        assertFalse(repository.existsById("DEV-CUP"));
        assertFalse(repository.existsById("DEV-BAG"));
    }

    @Test
    void createsOnlyItsOwnScenarioRow() {
        CatalogItem item = CatalogTestObjects.simpleItem(
                "TEST-LOCAL", 990);
        repository.saveAndFlush(item);

        assertTrue(repository.existsById("TEST-LOCAL"));
        assertEquals(1L, repository.count());
        assertFalse(repository.existsById("DEV-CUP"));
    }

    @Test
    void noSqlFixtureMeansFixtureSkuIsMissing() {
        assertTrue(repository.findById("TEST-BOOK").isEmpty());
        assertTrue(
                repository.findByFeaturedTrueOrderBySkuAsc()
                        .isEmpty());
    }
}
```

Có **3 phương thức @Test**. Mỗi test không có `@Sql` và dùng profile `test`; chúng không chờ data từ một runner/method khác. `CatalogTestObjects.simpleItem(...)` tạo đúng một hàng trong method cần nó.

Trong project mẫu không có reference data, `repository.count()==0` là assertion hợp lệ. **Đừng sao chép nguyên assertion này vào ứng dụng production có reference data bắt buộc**: khi đó phải query theo namespace/test-owned SKU thay vì yêu cầu toàn database trống.

### Tại sao test thứ ba không phụ thuộc test thứ hai?

`@DataJpaTest` mặc định transactional và rollback sau mỗi method. Vì thế `TEST-LOCAL` của một method không cần tồn tại ở method khác. Câu `findById("TEST-BOOK").isEmpty()` cũng chứng minh fixture của **class khác** không bị nạp ngầm trong class này.

## 13. CatalogFixtureSqlTest: fixture được khai báo rõ

`src/test/java/com/example/catalog/CatalogFixtureSqlTest.java`:

```java
package com.example.catalog;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(showSql = false)
@ActiveProfiles("test")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
@Sql(
        scripts = "/fixtures/catalog-items.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class CatalogFixtureSqlTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void explicitFixtureContainsExactlyFourRows() {
        assertEquals(4L, repository.count());
        assertTrue(repository.existsById("TEST-BOOK"));
        assertTrue(repository.existsById("TEST-DISPLAY"));
        assertTrue(repository.existsById("TEST-CABLE"));
        assertTrue(repository.existsById("TEST-PEN"));
    }

    @Test
    void featuredQueryReturnsTwoRowsInSkuOrder() {
        List<String> skus = repository
                .findByFeaturedTrueOrderBySkuAsc()
                .stream()
                .map(CatalogItem::getSku)
                .toList();

        assertEquals(
                List.of("TEST-BOOK", "TEST-DISPLAY"),
                skus);
    }

    @Test
    void priceRangeUsesOnlyRelevantFixtures() {
        List<String> skus = repository
                .findByPriceCentsBetweenOrderBySkuAsc(
                        500, 2000)
                .stream()
                .map(CatalogItem::getSku)
                .toList();

        assertEquals(
                List.of("TEST-BOOK", "TEST-CABLE"),
                skus);
    }

    @Test
    void demoSeedNeverMixesWithTestFixture() {
        assertFalse(repository.existsById("DEV-CUP"));
        assertFalse(repository.existsById("DEV-BAG"));
        assertEquals(4L, repository.count());
    }

    @Test
    void methodMutationLivesOnlyInTestTransaction() {
        repository.saveAndFlush(new CatalogItem(
                "TEST-TEMP", "Temporary", 777, false));

        assertEquals(5L, repository.count());
        assertTrue(repository.existsById("TEST-TEMP"));
    }

    @Test
    void everyMethodHasTheSameExplicitBaseline() {
        assertEquals(4L, repository.count());
        assertFalse(repository.existsById("TEST-TEMP"));
        assertTrue(repository.findById("TEST-NOT-FOUND").isEmpty());
    }
}
```

Có **6 phương thức @Test**. SQL fixture chạy trước từng method (không phải chỉ một lần cho toàn class), method tự exercise repository, rồi test transaction rollback. Do đó baseline bốn hàng phải độc lập với thứ tự JUnit thực thi.

### Vòng đời một method

```text
BEGIN test-managed transaction
  |
  +-- @Sql BEFORE_TEST_METHOD
  |      INSERT TEST-BOOK / DISPLAY / CABLE / PEN
  |
  +-- @Test body
  |      SELECT / UPDATE / INSERT TEST-TEMP
  |
  +-- ROLLBACK (DataJpaTest default)
  |
method kế tiếp: BEGIN mới, @Sql chèn lại fixture
```

`methodMutationLivesOnlyInTestTransaction` kiểm tra `TEST-TEMP` tồn tại **trong** method. `everyMethodHasTheSameExplicitBaseline` kiểm tra method của chính nó bắt đầu chỉ với bốn rows. Hai tests không yêu cầu một thứ tự cụ thể: mỗi method đều tự tạo baseline và transaction rollback dọn thay đổi.

Nếu bạn bỏ `@Sql`, những query assertions phải fail hoặc không tìm thấy rows: đây chính là dấu hiệu setup đang tường minh, chứ không dựa vào data.sql global.

### @Sql đặt ở class hay method?

Class-level phù hợp khi mọi test cùng dùng một fixture ngắn. Method-level phù hợp khi chỉ một case cần dữ liệu đặc biệt. Khi phối hợp class-level và method-level `@Sql`, phải hiểu `@SqlMergeMode` và mặc định override/merge semantics; không để test vô tình nạp cả hai script.

### Khi nào không rollback?

Nếu một test cố ý dùng `@SqlConfig(transactionMode=ISOLATED)`, SQL setup có thể commit ở transaction khác, nên rollback method không tự xóa những rows đó. Khi test không transactional, scripts cũng có thể chạy/commit ngoài test transaction. Khi ấy cần teardown có scope, ví dụ `@Sql(..., executionPhase=AFTER_TEST_METHOD)`, hoặc reset database/container. Không áp dụng chung một giả định rollback cho mọi framework annotation.

## 14. DevSeedProfileTest: xác minh nhánh dev thật

Muốn kiểm chứng một `ApplicationRunner` chạy lúc application startup, phải sử dụng context lifecycle phù hợp. `@DataJpaTest` là slice giới hạn component scan, không tự nạp mọi regular configuration/runner. Vì vậy test dev seed bằng `@SpringBootTest`:

`src/test/java/com/example/catalog/DevSeedProfileTest.java`:

```java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("dev")
class DevSeedProfileTest {

    @Autowired
    CatalogRepository repository;

    @Test
    void devProfileCreatesTwoDemoProducts() {
        assertTrue(repository.existsById("DEV-CUP"));
        assertTrue(repository.existsById("DEV-BAG"));
        assertEquals(2L, repository.count());
    }

    @Test
    void devProfileDoesNotLoadTestOnlyFixture() {
        assertFalse(repository.existsById("TEST-BOOK"));
        assertFalse(repository.existsById("TEST-CABLE"));
        assertEquals(2L, repository.count());
    }
}
```

Có **2 phương thức @Test**. Khi profile dev bật, Spring tạo `DevCatalogSeedConfig` và chạy `ApplicationRunner` sau startup. Hibernate tạo schema H2 theo `application-dev.yml`; hai hàng DEV-* được chèn. File SQL fixture ở `src/test/resources` không được Boot tự chạy vì không có `@Sql` trên class này và SQL init mode default là never.

**Tổng bộ ví dụ: 3 + 6 + 2 = 11 phương thức @Test.** Những lời khẳng định là kỳ vọng từ source, không phải kết quả chạy CI thực tế.

### Vì sao không gắn @Transactional vào dev test để “xóa seed”?

`ApplicationRunner` đã chạy **trước test methods**. Transaction mà một test method tự mở không thể quay ngược những thao tác startup hoàn tất trước đó. Bộ test dev profile chủ động chỉ **đọc** hai rows. Nếu test cần mutate chúng, phải dùng context/database dành riêng và cleanup/restore cụ thể.

## 15. Chạy test và đọc báo cáo đúng

Chạy từng lớp khi dự án có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.catalog.CatalogWithoutSeedTest'
./gradlew test --tests 'com.example.catalog.CatalogFixtureSqlTest'
./gradlew test --tests 'com.example.catalog.DevSeedProfileTest'
```

Chạy toàn suite:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Wrapper nhưng đã cài Gradle tương thích:

```bash
gradle test
```

Dự kiến báo cáo có **11 test methods**. Kiểm tra report thật ở `build/reports/tests/test/index.html` và XML ở `build/test-results/test/` để xác định PASS/FAIL/SKIPPED; code mẫu **chưa được chạy Gradle ở thời điểm biên soạn**.

Nếu chỉ test source mà không mở full application, `@DataJpaTest` nhanh hơn `@SpringBootTest` vì chỉ dựng JPA slice. Chỉ `DevSeedProfileTest` mới cần full application startup để kiểm tra `ApplicationRunner`.

## 16. Phân biệt @DataJpaTest rollback với request HTTP thật

`@DataJpaTest` thường chạy trong **test-managed transaction**; `@Sql` và repository method cùng transaction sẽ rollback khi method kết thúc. Nhưng một bài test HTTP:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpCatalogTest {
    // HTTP client ở test thread,
    // controller xử lý request ở server thread.
}
```

là **snippet kiến trúc** (không có controller/client trong project mẫu). `@Transactional` trên **test thread** không tự rollback writes được server xử lý trong transaction riêng. Nếu HTTP request tạo một hàng đã commit, test method kết thúc rollback của chính nó cũng không xóa hàng đó.

Với real HTTP integration tests:

1. Dùng test database/schema/container riêng.
2. Nạp fixture mà server có thể nhìn thấy, không giả định uncommitted SQL setup trong test thread được server đọc.
3. Chạy request và assert response/storage.
4. Cleanup theo namespace hoặc reset database, tránh xóa bảng ngoài ownership.
5. Nếu cần `@SqlConfig(transactionMode=ISOLATED)` cho committed setup, bảo đảm teardown tương ứng.
6. Không dựa vào `@Rollback` của test thread để xử lý mọi background/async side effects.

Các thao tác Redis/Kafka/MongoDB cũng không tự rollback theo JPA transaction của test trừ khi đã có transaction architecture riêng; khi test nhiều hệ thống, phải thiết kế cleanup/invalidation cho từng nơi.

## 17. Dữ liệu tham chiếu với Flyway/Liquibase

Project mẫu dùng Hibernate `ddl-auto=create-drop` để tạo schema H2 nhanh, **không** dùng migrations. Trong dự án thật, schema và reference data nên được quản lý bằng migration versioned.

### Flyway

Giả sử production có:

```text
src/main/resources/db/migration/
  V1__create_catalog.sql
  V2__insert_required_status_codes.sql
```

Những mã status bắt buộc là **reference data**, có thể và nên có mặt trong integration tests chạy production migrations. Còn demo products nên được nạp bằng dev-only directory hoặc `@Profile("dev")` runner, không chèn vào `V2__insert_required_status_codes.sql`.

Một cấu hình dev-only có thể trông như:

```properties
spring.flyway.locations=classpath:db/migration,classpath:dev/db/migration
```

Đây là snippet kiến trúc, **không thuộc project runnable** vì mẫu không thêm dependency Flyway. Khi dùng test-only migrations, file có thể đặt dưới `src/test/resources` hoặc test location riêng; phải kiểm tra ordering, migration discovery và packaging.

### Liquibase

Tương tự, một test changelog có thể include production changelog rồi thêm test-only changesets; production không được trỏ đến test changelog. Khi dùng contexts/labels, test phải kiểm tra profile thực kích hoạt đúng subset.

### Một schema manager chính

Không trộn Hibernate create-drop, `schema.sql` và Flyway/Liquibase để cùng quản lý schema mà không có thiết kế rõ. Với production, migrations thường là nguồn chính; Hibernate `validate` có thể dùng để phát hiện mismatch. Với H2 demo trong bài, chỉ Hibernate tạo bảng và `@Sql` chèn fixture rows.

## 18. Cách dùng dev-only SQL initializer nếu không muốn runner

Một lựa chọn khác, **không ghép song song với DevCatalogSeedConfig trong project trên**, là tạo script dev riêng và cho Boot SQL initializer nạp nó chỉ ở profile dev:

```yaml
spring:
  sql:
    init:
      mode: always
      data-locations: classpath:/db/dev/demo-products.sql
  jpa:
    defer-datasource-initialization: true
    hibernate:
      ddl-auto: create-drop
```

Cấu hình này chỉ phù hợp khi file `db/dev/demo-products.sql` **thực sự tồn tại**, Hibernate tạo schema trước và Boot SQL initializer nạp demo rows sau đó. Nó cần đặt trong `application-dev.yml`, không phải application.yml mặc định; file ở dev-only directory tránh tên `data.sql` dễ auto-run trong test. Không dùng `create-drop` trên production DataSource.

Nếu đã dùng Flyway/Liquibase, thường không nên vừa dùng SQL initializer vừa migration cho cùng schema. Chọn phương án tương thích database strategy của sản phẩm.

## 19. Tại sao @Profile("!prod") không đủ?

Một cách seed dễ mắc lỗi:

```java
@Configuration
@Profile("!prod")
class UnsafeDemoSeed {
    // Runner ghi demo products.
}
```

Đây là **phản ví dụ**, không có code runner độc lập. `!prod` đúng với `test`, `staging`, `qa` và mọi context không bật prod; demo seed vẫn được tạo nếu config được scan. Điều này gây bất ngờ và khiến một integration test nhận dataset khác kỳ vọng.

Thay bằng `@Profile("dev")` hoặc một policy positive allowlist riêng. Với ứng dụng chạy nhiều profiles, nếu `test` và `dev` cùng active thì dev loader **vẫn có thể chạy**. Không tự bật thêm `dev` trong test chỉ để lấy H2 settings; cung cấp `application-test.yml` đầy đủ thay thế.

Một profile guard cũng không phải security boundary: test job vẫn cần credentials/database isolation đúng và không được có quyền ghi production DB.

## 20. Dữ liệu deterministic và factory tốt

Test fixture nên có:

- IDs rõ ràng: `TEST-BOOK` thay vì ID random không được ghi lại.
- Giá trị biên có mục đích: 0, min, max, ngoài khoảng lọc.
- Field cần assert tường minh, các field khác có defaults hợp lệ.
- Số lượng hàng tối thiểu để phân biệt success/failure.
- Time cố định khi logic phụ thuộc thời điểm hiện tại.
- Không dùng tên/email/số thẻ thật của khách hàng.
- Không cần một global singleton entity mutable mà nhiều tests cùng sửa.

Snippet clock cố định, nếu service thực dùng injectable `Clock`:

```java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC);
```

Cần imports `java.time.Clock`, `Instant`, `ZoneOffset`. Đây là snippet mở rộng, không phải file project. Nó tốt hơn việc test dựa vào `Instant.now()` rồi fail sát nửa đêm hoặc giữa hai time zones.

SQL fixtures có thể tốt để kiểm tra repository joins/constraints; factory phù hợp unit/domain tests; test builders phù hợp variations. Không buộc mọi bài test dùng cùng một cách setup.

## 21. Test pollution và context cache

**Test pollution** nghĩa là một test làm thay đổi state mà test khác nhìn thấy ngoài dự kiến. Các dấu hiệu:

- Test chạy đơn lẻ PASS nhưng chạy suite FAIL.
- Đảo thứ tự test methods làm count/expected khác.
- Fixture SQL chèn duplicate primary key ở test thứ hai.
- Một test không có `@Sql` vẫn thấy `TEST-BOOK`.
- Test profile vẫn thấy `DEV-CUP`.
- Một job CI parallel xóa data đang được job khác dùng.
- `@SpringBootTest` context cache reuse một singleton bean có mutable data.
- Một asynchronous job ghi DB sau khi test method rollback.

**Hướng kiểm tra:**

1. Xác nhận active profiles và tên database/schema test (không log password).
2. Tìm mọi nguồn seed: `data.sql`, `import.sql`, migrations, runners, listeners, external bootstrap.
3. Kiểm tra `@Sql` đặt class-level/method-level và transaction mode.
4. Kiểm tra `@Transactional`, `@Commit`/`@Rollback(false)` hoặc test dùng remote HTTP server.
5. Kiểm tra Spring context cache và parallel execution.
6. Tìm static mutable state trong factories, caches, services.
7. Khôi phục per-test baseline và rollback/cleanup đúng ranh giới.
8. Chạy lại từng method và cả suite để bảo đảm không phụ thuộc thứ tự.

Không giải quyết bằng cách thêm `@Order` để ép test A tạo data rồi test B dùng; nếu chạy riêng B, test sẽ mất precondition.

## 22. Dọn dữ liệu đúng phạm vi

### Với @DataJpaTest

Transaction rollback là lựa chọn dễ nhất khi mọi DML và `@Sql` cùng tham gia test transaction. Không cần `repository.deleteAll()` ở mỗi test; lệnh delete rộng còn có thể che data-leak bug.

### Với @SpringBootTest và dữ liệu đã commit

Test startup runner, HTTP server hoặc async process có thể ghi ngoài test-managed transaction. Khi đó dùng isolated DataSource/test container và cleanup theo ownership. Có thể tạo SQL cleanup ở `AFTER_TEST_METHOD` khi transaction setup/teardown đúng, hoặc reset database/container.

`@AfterEach` thường chạy dù assertion fail, nhưng **không bảo đảm** chạy khi JVM/process bị kill. Database riêng cho suite vẫn giúp tránh ảnh hưởng môi trường shared.

### Với database shared

Không gọi `deleteAll()` hoặc `TRUNCATE` trên database chưa xác thực ownership của test. Nếu bắt buộc dùng shared integration service, tạo schema/tenant namespace riêng có quyền hạn phù hợp và cleanup chỉ những rows do test tạo.

### Với parallel execution

Một fixture `TEST-BOOK` cố định có thể an toàn khi mỗi test dùng transaction/database riêng, nhưng sẽ conflict nếu nhiều nontransactional suites ghi cùng database. Khi chạy parallel across workers, dùng distinct database/container/schema hoặc unique namespace per suite. Không tin vào cleanup theo thứ tự ở một global shared H2 instance.

## 23. Tests H2 không chứng minh mọi migration production

H2 nhanh cho repository mapping/query cơ bản, nhưng khác PostgreSQL/MySQL về kiểu dữ liệu, SQL dialect, collations, locking, sequences và transaction isolation. Nếu behavior phụ thuộc vendor, dùng **Testcontainers database cùng loại production**, chạy schema migration thực rồi nạp test-only fixtures.

Không copy một production snapshot chứa PII vào test repository; nếu cần reproduce data shape, dùng synthetic/anonymized data theo chính sách bảo mật.

### Thứ tự migration và fixture

```text
Testcontainers DB starts
     |
     +-- Apply production schema/reference migrations
     |
     +-- Apply test-specific setup (@Sql / test migrations)
     |
     +-- Execute repository/service test
     |
     +-- Rollback/reset test-owned state
```

Khi một test dùng production reference data, baseline không còn là zero rows ở tất cả bảng. Assertions nên giới hạn vào table/tenant/test SKU thay vì `count()==0` toàn DB.

## 24. Checklist QA

- [ ] Reference data, dev seed, test fixtures đã được phân loại và có owner?
- [ ] Dev seed có positive guard `@Profile("dev")`?
- [ ] Không dùng `@Profile("!prod")` cho data demo?
- [ ] Root `data.sql`/`import.sql` có được kiểm soát, không auto-run ngoài ý định?
- [ ] Đã hiểu `spring.sql.init.mode=never` chỉ tắt Boot SQL initializer?
- [ ] Test resources nằm trong `src/test/resources` và không được đóng gói production jar?
- [ ] `application-test.yml` và `@ActiveProfiles("test")` có được dùng đúng?
- [ ] Embedded test DataSource có được cô lập khỏi dev/prod?
- [ ] `@Sql` chỉ nạp fixture khi test yêu cầu và phase phù hợp?
- [ ] SQL fixture có rows tối thiểu với data phân biệt các branches?
- [ ] Test không dùng `@SqlConfig(transactionMode=ISOLATED)` nếu đang dựa vào rollback?
- [ ] Không cần `@Order` hoặc dữ liệu từ method trước?
- [ ] Có test absence của DEV-* trong test profile và presence trong dev profile?
- [ ] Full-context test được dùng khi kiểm tra runner startup?
- [ ] Có phân biệt test transaction với HTTP/async transaction?
- [ ] Không dùng `deleteAll()` trên database không thuộc scope test?
- [ ] Migrations/reference data trên production-compatible DB có được kiểm tra khi cần?
- [ ] Có tránh shared mutable fixture object và nondeterministic time/random?
- [ ] Test dataset không có credentials/PII production?
- [ ] Đã chạy Gradle và xem test report thật trước khi tuyên bố PASS?
- [ ] Một method chạy độc lập và cả suite cho kết quả nhất quán?

## 25. Bài tập củng cố

1. Chạy `CatalogWithoutSeedTest`; giải thích vì sao demo runner không chạy ở test profile.
2. Đổi `@Profile("dev")` thành `@Profile("!prod")` trong sandbox, xem một full-context test có profile test có thể bị seed như thế nào.
3. Bỏ `@Sql` khỏi `CatalogFixtureSqlTest` rồi giải thích vì sao BOOK/CABLE không còn tồn tại.
4. Chuyển `@Sql` từ class-level sang một method-level riêng, kiểm tra method khác không có fixture.
5. Bổ sung `TEST-HEADSET` vào fixture SQL và thay đúng assertion chứ không sửa demo seed.
6. Viết test có fixture giá 0, 500, 2000 và 2001 cents để kiểm tra inclusive range.
7. Thử `@SqlConfig(transactionMode=ISOLATED)` trên test DB riêng, rồi thiết kế cleanup.
8. Tạo một reference table được Flyway migration versioned và so sánh với test-only fixture.
9. Tạo một test `@SpringBootTest(RANDOM_PORT)` khi có web API, nhận biết rollback của test thread khác server transaction.
10. Dùng factory tạo một item riêng, kiểm tra JPA transaction rollback không rò row.
11. Thử chạy tests theo thứ tự ngẫu nhiên hoặc tách riêng một method; không được phụ thuộc thứ tự.
12. Kiểm tra `import.sql` khác `data.sql` thế nào khi Hibernate `create-drop` trong H2 sandbox.
13. Nếu có production PostgreSQL, chạy repository query trên Testcontainers + production migrations.
14. Kiểm tra Gradle test report xem thực tế có đúng 11 @Test methods hay không.
15. Review fixtures để chắc chắn không chứa customer PII và secrets.
16. Chạy CI parallel với database/schema cô lập và ghi lại cách tránh conflict fixtures.

## 26. Tài liệu chính thức

- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `data.sql`/`schema.sql`, `spring.sql.init.mode`, Hibernate `import.sql`, SQL init ordering, Flyway/Liquibase.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, test database và transaction rollback, `@SpringBootTest`.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql`, execution phase và `@SqlConfig`.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions và rollback.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): `@Profile` và profile-specific config.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): YAML properties và configuration sources.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): derived query methods và JPA repository behavior.
- [Testcontainers for Java](https://java.testcontainers.org/): database integration tests với đúng vendor.
- [JUnit Jupiter — User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle và independence.

## 27. Kết luận

**Không nên để một database demo toàn cục quyết định kết quả của repository tests.** Dữ liệu tham chiếu bắt buộc thuộc về migrations/contract; demo seed cần explicit dev profile; test fixtures thuộc các scenario tests và được nạp bằng `@Sql` hoặc Java factory trong test sources.

`spring.sql.init.mode=never` giúp ngăn Spring Boot tự chạy data.sql, nhưng không thay thế guard cho Hibernate import.sql, migrations hoặc ApplicationRunner. Với Spring Boot 3.3, `@ActiveProfiles("test")`, embedded H2, `@DataJpaTest` rollback và per-test `@Sql` tạo một đường kiểm thử ngắn, rõ và tái hiện được. Khi chuyển sang HTTP server, async work hay nhiều storage backends, phải xác định transaction/cleanup boundary mới thay vì tin mọi write đều được rollback.

Bộ mẫu thể hiện cả hai mặt: test profile **không có DEV-* seed** và dev profile **có đúng demo rows**, trong khi repository query tests dùng riêng bốn `TEST-*` fixtures. Nhờ vậy, thay đổi nội dung demo không làm test nghiệp vụ đỏ, và khi test thất bại có thể truy rõ fixture, transaction hoặc query gây lỗi.
