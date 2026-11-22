# Cấu trúc `src/test/java`, `src/test/resources` và cách tổ chức package trong Spring Boot

Một dự án Spring Boot có thể chạy ứng dụng bình thường nhưng kiểm thử lại khó bảo trì nếu mã test, dữ liệu mẫu và cấu hình môi trường đặt lẫn lộn. Cách tổ chức đúng giúp người đọc trả lời nhanh bốn câu hỏi: **test nào bảo vệ lớp/chức năng nào, fixture nằm ở đâu, test đang nạp cấu hình nào, và lệnh nào sẽ chạy test đó?**

Mục tiêu của bài học: hiểu vai trò hai thư mục test chuẩn của Maven/Gradle, chọn package hợp lý cho unit/slice/integration test, dùng tài nguyên classpath đúng cách và tránh những lỗi khiến bài kiểm thử chỉ chạy trên máy cá nhân.

## 1. Nguồn mã production và nguồn mã test là hai source root khác nhau

Với một dự án Java Spring Boot dùng bố cục tiêu chuẩn, Maven và Gradle Java plugin nhận diện các thư mục sau:

| Đường dẫn | Chứa gì? | Có mặt ở đâu? |
|---|---|---|
| `src/main/java` | Java source của ứng dụng: controller, service, domain, repository, config | Biên dịch thành main classes; có thể đóng gói vào ứng dụng |
| `src/main/resources` | Cấu hình và tài nguyên phục vụ lúc chạy ứng dụng, ví dụ `application.yml`, template, migration | Main runtime classpath; thường nằm trong artifact ứng dụng |
| `src/test/java` | Mã Java kiểm thử: JUnit test, helper, fake, factory, cấu hình hỗ trợ test | Test compile/runtime classpath; mặc định không đóng gói vào JAR ứng dụng |
| `src/test/resources` | Fixture JSON/CSV/XML, file SQL, cấu hình profile test, dữ liệu mẫu | Test runtime classpath; mặc định không đóng gói vào JAR ứng dụng |

**Source root** là gốc đường dẫn mà công cụ build dùng để suy ra package và classpath. Nó không phải một phần của tên Java package. Vì vậy file ở `src/test/java/com/example/shop/order/ShippingPolicyTest.java` sẽ khai báo `package com.example.shop.order;`, không khai báo `package src.test.java.com.example...`.

Khi chạy test, test classpath thường chứa **classes của `main` + classes của `test` + resources của cả hai + test dependencies**. Nhờ đó mã trong `src/test/java` có thể dùng lớp từ `src/main/java` và thư viện JUnit, nhưng source production không được phụ thuộc vào helper chỉ tồn tại trong test. Một ứng dụng chạy từ artifact release mặc định cũng không nhìn thấy fixture chỉ nằm ở `src/test/resources`.

> Ghi nhớ: `src/test/java` dành cho **mã thực thi kiểm thử**; `src/test/resources` dành cho **dữ liệu/cấu hình để kiểm thử**. Đừng đặt test case Java vào resources hoặc đặt JSON fixture thành hằng chuỗi dài trong nhiều lớp test nếu chúng cần chia sẻ.

## 2. Cây thư mục mẫu theo chức năng

Ví dụ module Spring Boot tên `shop`, package gốc `com.example.shop`:

```text
shop/
├── pom.xml                          # hoặc build.gradle(.kts)
└── src/
    ├── main/
    │   ├── java/com/example/shop/
    │   │   ├── ShopApplication.java
    │   │   ├── order/
    │   │   │   ├── OrderController.java
    │   │   │   ├── OrderService.java
    │   │   │   └── ShippingPolicy.java
    │   │   └── customer/
    │   │       └── CustomerService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/shop/
        │   ├── ShopApplicationContextTest.java
        │   ├── order/
        │   │   ├── ShippingPolicyTest.java
        │   │   ├── OrderControllerTest.java
        │   │   ├── OrderServiceTest.java
        │   │   └── OrderRepositoryIT.java
        │   ├── customer/
        │   │   └── CustomerServiceTest.java
        │   └── testing/
        │       ├── OrderTestDataFactory.java
        │       └── IntegrationTestSupport.java
        └── resources/
            ├── application-test.yml
            ├── fixtures/
            │   └── orders/
            │       ├── create-order-valid.json
            │       └── create-order-invalid.json
            └── sql/
                ├── orders-before.sql
                └── orders-cleanup.sql
```

Đây là **cấu trúc minh họa**, không phải danh sách file bắt buộc. Chỉ tạo những package và helper thực sự được dùng. Chẳng hạn, module không có persistence thì không cần `OrderRepositoryIT` hay thư mục `sql`.

### Quy tắc đặt package

1. **Giữ test gần đối tượng được kiểm**: mã production `com.example.shop.order.ShippingPolicy` thì test ở `com.example.shop.order.ShippingPolicyTest`. Đường dẫn của test phản chiếu package production, giúp IDE chuyển qua lại dễ dàng.
2. **Không thêm `.test` vào mọi package một cách máy móc**: `com.example.shop.order` là hợp lý cho unit test cần kiểm tra thành viên package-private. `com.example.shop.order.test` là package Java khác, không có quyền truy cập package-private.
3. **Nhóm theo feature khi mã production nhóm theo feature**: nếu ứng dụng đã chia `order`, `customer`, `payment`, test nên theo cùng ranh giới. Nếu dự án tổ chức `service`/`repository`/`web`, có thể phản chiếu cấu trúc đó, nhưng tránh tạo cây package test độc lập không thể lần theo mã chính.
4. **Tách tiện ích thực sự dùng chung**: ví dụ `com.example.shop.testing.OrderTestDataFactory` để tạo dữ liệu hợp lệ; không đưa logic nghiệp vụ thật vào helper test khiến bài test dựa vào một bản sao hành vi cần kiểm.
5. **Test ở package con của package chứa `@SpringBootApplication`** khi muốn Spring Boot tự tìm cấu hình gốc. Tùy cấu hình, `@SpringBootTest` và test slice tìm lớp `@SpringBootConfiguration` bằng cách dò từ package test lên package cha. Nếu đặt test ngoài cây package đó, cần chỉ định cấu hình rõ ràng, ví dụ `@SpringBootTest(classes = ShopApplication.class)`.

**Package phản chiếu mã production không đồng nghĩa mọi test đều cần khởi động Spring.** Unit test dùng JUnit thuần có thể đặt cạnh lớp tương ứng và tạo đối tượng trực tiếp; chỉ dùng Spring context khi hành vi cần chứng minh phụ thuộc bean wiring, web, database hoặc cấu hình Spring.

## 3. Ví dụ unit test đầy đủ: file nằm ở đâu, package viết thế nào?

Giả sử chi phí vận chuyển là 30.000 VND với đơn dưới 500.000 VND; từ 500.000 VND trở lên được miễn phí. Đầu vào âm bị từ chối.

File **`src/main/java/com/example/shop/order/ShippingPolicy.java`**:

```java
package com.example.shop.order;

public final class ShippingPolicy {
    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }
        return subtotalVnd >= 500_000 ? 0 : 30_000;
    }
}
```

File **`src/test/java/com/example/shop/order/ShippingPolicyTest.java`**:

```java
package com.example.shop.order;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {
    private final ShippingPolicy policy = new ShippingPolicy();

    @Test
    void feeAppliesBelowThreshold() {
        assertEquals(30_000, policy.feeVnd(499_999));
    }

    @Test
    void freeShippingStartsAtThreshold() {
        assertEquals(0, policy.feeVnd(500_000));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1));
    }
}
```

Ví dụ cần Java 17+ và JUnit Jupiter (thường đã được đưa vào bằng dependency kiểm thử như `spring-boot-starter-test` theo phiên bản Spring Boot dự án). Với Maven Wrapper đã cấu hình plugin kiểm thử, chạy riêng lớp:

```bash
./mvnw -Dtest=ShippingPolicyTest test
```

Hoặc trên Gradle với JUnit Platform đã được bật:

```bash
./gradlew test --tests "com.example.shop.order.ShippingPolicyTest"
```

Trên Windows dùng `mvnw.cmd` hoặc `gradlew.bat`. Kết quả kỳ vọng: **3 test pass**. Không có stdout nghiệp vụ bắt buộc. Bài test không cần `@SpringBootTest`, không nạp bean, không truy cập DB; đường dẫn đúng và package trùng production giúp IDE và build tool nhận diện lớp dễ dàng.

Tên `ShippingPolicyTest` mô tả đối tượng được kiểm; tên method mô tả hành vi. Một lớp test nên tập trung vào một đối tượng hoặc trách nhiệm rõ ràng; không tạo `AllTests.java` khổng lồ chỉ vì dùng cùng package.

## 4. `src/test/resources`: đường dẫn classpath khác đường dẫn file hệ điều hành

Giả sử tạo file **`src/test/resources/fixtures/orders/create-order-valid.json`**:

```json
{
  "sku": "BOOK-001",
  "quantity": 2
}
```

Ở test runtime, resource có đường dẫn classpath **`fixtures/orders/create-order-valid.json`**. Prefix `src/test/resources` không xuất hiện trong tên tài nguyên classpath.

Ví dụ test đọc fixture mà không phụ thuộc thư mục làm việc hiện tại.

File **`src/test/java/com/example/shop/order/OrderFixtureTest.java`**:

```java
package com.example.shop.order;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderFixtureTest {
    @Test
    void loadsOrderRequestFromTestClasspath() throws Exception {
        try (InputStream input = Objects.requireNonNull(
                getClass().getResourceAsStream(
                        "/fixtures/orders/create-order-valid.json"))) {
            String json = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(json.contains("\"BOOK-001\""));
        }
    }
}
```

Kỳ vọng test pass khi file JSON đúng đường dẫn. `Objects.requireNonNull` báo rõ resource bị thiếu; với mã thực tế có thể dùng assertion với message mô tả đường dẫn. Cặp đường dẫn này rất quan trọng:

| Cách truy cập | Đường dẫn đúng |
|---|---|
| `SomeTest.class.getResourceAsStream(...)` | `"/fixtures/orders/create-order-valid.json"` với `/` đầu để tính từ classpath root |
| `SomeTest.class.getClassLoader().getResourceAsStream(...)` | `"fixtures/orders/create-order-valid.json"` không có `/` đầu |
| Spring `ClassPathResource` | `new ClassPathResource("fixtures/orders/create-order-valid.json")` |

Nếu dùng `Class.getResourceAsStream("create-order-valid.json")` không có dấu `/` đầu, Java sẽ tìm resource **tương đối với package của lớp test** (ví dụ `com/example/shop/order/`), thường không phải vị trí fixture ở root. Đó là một nguyên nhân phổ biến gây `null` và `NullPointerException`.

**Tránh** `Files.readString(Path.of("src/test/resources/..."))` trong test cần chạy ở mọi môi trường: cách này phụ thuộc current working directory và cách build tool bố trí dự án. Đọc qua classpath phù hợp hơn với CI, chạy test từ IDE và các module con. Chỉ dùng đường dẫn filesystem khi hành vi thực sự cần kiểm là thao tác với file trên đĩa.

### Nên tổ chức dữ liệu mẫu ra sao?

- `fixtures/orders/`: dữ liệu yêu cầu HTTP/JSON; tách `valid`, `missing-field`, `invalid-state` theo tình huống được test.
- `sql/`: script setup/cleanup khi có DB integration test; đặt tên gợi quan hệ với suite hoặc scenario, tránh một file SQL khổng lồ dùng bởi tất cả bài.
- `contracts/` hoặc `stubs/`: schema và phản hồi mẫu của các dịch vụ ngoài khi thật sự dùng contract/stub tests.
- `application-test.yml`: thuộc root của test resources vì Spring Boot tìm config theo tên chuẩn trong classpath.
- Không đưa secret, token thật, dữ liệu cá nhân thật hoặc binary rất lớn vào fixture; dùng dữ liệu giả, xác định, có thể tạo lại.

Nếu một fixture phục vụ duy nhất một test, để nó trong thư mục con có tên của feature là đủ. Nếu nhiều test cùng dùng một fixture, giữ một bản canonical và tránh sửa toàn cục trong quá trình test (vì có thể khiến test phụ thuộc thứ tự).

## 5. Cấu hình `application-test.yml` và test profile

File **`src/test/resources/application-test.yml`**:

```yaml
app:
  greeting: "hello-from-test"
logging:
  level:
    root: WARN
```

Đặt `@ActiveProfiles("test")` trên test **dùng Spring context** để bật profile `test` và nạp cấu hình theo quy tắc Spring Boot:

File **`src/test/java/com/example/shop/TestProfileLoadingTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class TestProfileLoadingTest {
    @Value("${app.greeting}")
    private String greeting;

    @Test
    void readsTestProfileConfig() {
        assertEquals("hello-from-test", greeting);
    }
}
```

Điều kiện: có `@SpringBootApplication` nằm trong `com.example.shop` (hoặc một cấu hình gốc được chỉ định rõ). Kết quả kỳ vọng là **1 test pass** khi ứng dụng có thể khởi tạo context với các dependency đã cấu hình. `application-test.yml` chỉ được tự động áp dụng khi profile `test` được kích hoạt bằng cách phù hợp; **chỉ tạo file chưa đủ để bảo đảm nó luôn có hiệu lực**.

Spring Boot thường ghép cấu hình nền như `application.yml` với cấu hình theo profile; giá trị profile có ưu tiên theo quy tắc nạp config của Spring. Không nên đặt một bản `application.yml` khác ở test root để vô tình che nội dung ứng dụng nếu mục đích thực sự là ghi đè có chọn lọc: dùng `application-test.yml`, `@TestPropertySource` hoặc `@DynamicPropertySource` tùy nhu cầu.

Với database hoặc broker do Testcontainers khởi tạo, host/port có thể thay đổi mỗi lần chạy; lấy thông tin từ container và đăng ký vào Spring Environment bằng cơ chế hỗ trợ phù hợp (`@DynamicPropertySource`, service connection nếu phiên bản hỗ trợ), đừng hardcode port. Không dùng thông tin kết nối production làm fallback trong profile kiểm thử.

**Phân biệt hai tầng cấu hình:** `@ActiveProfiles` chọn profile của **Spring** cho bài test có application context; việc Gradle/Maven có chạy lớp test hay không do **build/test engine** quyết định, không do tên profile.

## 6. Package test ảnh hưởng thế nào tới Spring Boot context?

Xét ứng dụng:

```text
src/main/java/com/example/shop/ShopApplication.java
src/test/java/com/example/shop/order/OrderControllerTest.java
src/test/java/com/example/shop/ShopApplicationContextTest.java
```

Lớp `ShopApplication` thường ở package gốc `com.example.shop`. Test trong `com.example.shop.order` nằm dưới package gốc, nên Spring Boot có thể tìm cấu hình khi một test dùng annotation như `@SpringBootTest` hoặc slice test hỗ trợ cơ chế đó.

Có ba kiểu bố trí hay gặp:

| Mục tiêu | Chỗ đặt test | Cách nạp context |
|---|---|---|
| Unit của `OrderService` | Cùng package với `OrderService` | Không cần Spring context |
| Web slice của `OrderController` | Package `order`, bên dưới gốc ứng dụng | `@WebMvcTest(OrderController.class)` cùng các mock/security setup cần thiết |
| Integration giữa controller, service và DB | Package feature hoặc `com.example.shop.integration`, bên dưới gốc | `@SpringBootTest` cộng dependency/môi trường test thật tương ứng |

Không để unit test khởi động context chỉ vì nó nằm trong package `integration`, và cũng không giả định test được coi là integration chỉ vì file có hậu tố `IT`. Annotation, dependencies, source set và build task thực sự mới quyết định điều gì chạy.

Nếu trong cùng repository có **nhiều ứng dụng Spring Boot** hoặc **nhiều lớp `@SpringBootConfiguration`** có thể được phát hiện, hãy chỉ định `classes = ...` hoặc cấu hình kiểm thử rõ ràng để tránh nạp nhầm context. Khi dùng `@WebMvcTest`, cần hiểu slice chỉ nạp phần web liên quan; phần service được mock/stub theo nhu cầu và behavior của DB không được chứng minh bởi slice.

**`@TestConfiguration`**, khi cần để khai báo bean phụ trợ cho test, thuộc mã kiểm thử (ví dụ trong `src/test/java` hoặc nested static class của test) và được import/nạp có chủ đích. Không đặt test-only bean vào `src/main/java` chỉ để test chạy dễ hơn, vì sẽ thay đổi artifact production hoặc cách scan bean.

## 7. Đặt tên lớp, test suite và lệnh chạy

Bộ tên dễ hiểu trong một feature:

- `ShippingPolicyTest`: unit test cho rule.
- `OrderControllerTest`: HTTP/MVC slice hoặc controller test; xem annotation để biết phạm vi thực.
- `OrderRepositoryIT`: integration test với DB; hậu tố `IT` thể hiện ý định nhưng cần cấu hình build để chạy ở nhịp mong muốn.
- `ShopApplicationContextTest`: kiểm tra context khởi tạo, không thay thế assertion nghiệp vụ.

**Maven:** Maven Surefire mặc định thường nhận `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java`. Tên `*IT.java` thường dành cho Maven Failsafe với cấu hình và lifecycle `integration-test` / `verify`; đừng mặc định `mvn test` đã chạy tất cả `*IT`.

**Gradle:** lớp test nằm trong test source set được chạy bằng task `test` khi test engine và JUnit Platform được cấu hình tương ứng. Nếu muốn tách integration test, tạo source set/task riêng hoặc dùng JUnit tags và filter trong build script; tên `*IT` tự nó không tạo thêm task. Ví dụ, dự án Gradle Groovy DSL có thể cần:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Tham khảo các lệnh phổ biến tại thư mục module chứa `pom.xml` hoặc `build.gradle`:

```bash
# Maven: chạy test thông thường
./mvnw test

# Maven: chọn một lớp unit test theo tên
./mvnw -Dtest=ShippingPolicyTest test

# Gradle: chạy test task
./gradlew test

# Gradle: chọn một lớp theo fully qualified name
./gradlew test --tests "com.example.shop.order.ShippingPolicyTest"
```

Trên Windows sử dụng wrapper tương ứng với `.cmd` hoặc `.bat`. Lệnh và tên task trong thực tế phụ thuộc build của module; ví dụ `./gradlew :shop:test` khi chạy multi-module từ root.

Đừng tin vào việc IDE hiện nút Run như bằng chứng CI sẽ chạy test đó. Luôn xác nhận pattern phát hiện test, JUnit engine, task và command của pipeline. Nếu đặt test vào `src/integrationTest/java` mà chưa khai báo source set/plugin, build tool có thể không biên dịch hay chạy nội dung ấy.

## 8. Dự án nhiều module: mỗi module sở hữu test của mình

Với Maven multi-module hoặc Gradle multi-project:

```text
project-root/
├── settings.gradle
├── order-domain/
│   └── src/
│       ├── main/java/...
│       └── test/java/...
└── order-api/
    └── src/
        ├── main/java/...
        ├── test/java/...
        └── test/resources/application-test.yml
```

- Unit test của `order-domain` nên nằm trong module `order-domain`, nơi chúng có thể chạy độc lập và không phụ thuộc web framework.
- Test web của `order-api` nằm trong `order-api`, là nơi có Spring MVC và cấu hình ứng dụng phù hợp.
- Chỉ tạo module hoặc source set `integration-test` riêng khi có lý do thực tế: chạy nhiều service, cần dependency khác, lịch chạy khác và ownership rõ. Việc chỉ tạo thư mục không tạo ra task.
- Nếu nhiều module dùng chung fixture/helper, ưu tiên fixture tách thành artifact test có cấu hình minh bạch, ví dụ Gradle `java-test-fixtures` hoặc cấu hình test JAR Maven được công bố rõ. Không làm module production phụ thuộc vào source set test của module khác.
- Trong monorepo có nhiều application, đừng đặt một test package “toàn cục” rồi dựa vào context scan ngẫu nhiên. Mỗi module phải biết application/configuration nào là đối tượng test của nó.

## 9. Cách kiểm tra source root và fixture khi gặp lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `package ... does not exist` khi biên dịch test | File nằm sai source root, package/import sai hoặc thiếu test dependency | Đối chiếu đường dẫn `src/test/java`, khai báo `package`, dependency và build configuration |
| IDE nhận JUnit nhưng `mvn test` không chạy lớp `*IT` | Surefire và Failsafe có pattern/scope khác nhau | Cấu hình Failsafe cho integration tests hoặc đổi tên theo task muốn chạy |
| `getResourceAsStream` trả `null` | Resource path thiếu/thừa dấu `/`, đặt ở sai thư mục hoặc chưa có trong test classpath | Kiểm tra path từ root `src/test/resources` và dạng Class/ClassLoader lookup |
| Test chạy trong IDE nhưng không chạy CI | Đường dẫn filesystem phụ thuộc working directory, profile khác, test không nằm trong task | Dùng classpath resource, kiểm tra môi trường và chạy đúng wrapper/task |
| `Unable to find a @SpringBootConfiguration` | Test package nằm ngoài cây package ứng dụng hoặc cấu hình gốc không tìm được | Đặt dưới package gốc hoặc chỉ định `classes = ShopApplication.class` |
| Test dùng nhầm DB thật | Profile test không active hoặc datasource chưa được override | `@ActiveProfiles("test")`, datasource test có xác nhận, cấu hình container/test DB rõ ràng |
| Test đọc sai giá trị property | Nhiều file `application*.yml`, profile hoặc property source có ưu tiên khác dự tính | Xem active profiles, config imports và thứ tự precedence thực tế |
| Test dùng chung dữ liệu bị lỗi thất thường | Fixture mutable/shared state, thiếu cleanup hoặc test phụ thuộc thứ tự | Tạo dữ liệu riêng cho từng test, transaction/cleanup phù hợp, reset dependency |
| Test chạy chậm dù chỉ kiểm một phép tính | Sử dụng `@SpringBootTest` không cần thiết | Viết unit test JUnit thuần cho logic độc lập |

Riêng với SQL script: `@Sql(scripts = "/sql/orders-before.sql")` trong integration test Spring dùng classpath (giả định file ở `src/test/resources/sql/orders-before.sql`). Hãy hiểu khi nào script chạy, transaction có rollback không, và nó có thật sự dọn đủ dữ liệu không. Đừng cho rằng `@Transactional` trên test tự động rollback các giao dịch được xử lý ở thread/tiến trình khác trong HTTP E2E test.

## 10. Checklist tổ chức một module Spring Boot dễ kiểm thử

- [ ] Java production ở `src/main/java`, test Java ở `src/test/java`; package khai báo khớp đường dẫn tính từ từng source root.
- [ ] Test class gần package/chức năng production mà nó bảo vệ; có tên chỉ ra đối tượng hoặc hành vi.
- [ ] Fixture/cấu hình test ở `src/test/resources`, tham chiếu qua classpath thay vì relative filesystem path phụ thuộc môi trường.
- [ ] `application-test.yml` chỉ chứa giá trị an toàn phục vụ test; test dùng Spring context kích hoạt profile rõ ràng.
- [ ] Unit test thuần không khởi động Spring khi không cần; slice/integration test nạp đúng cấu hình và dependencies thực.
- [ ] Helper, fake và `@TestConfiguration` thuộc phạm vi test; không gây dependency ngược từ mã production vào mã test.
- [ ] Quy ước `*Test`/`*IT`, source set và Maven/Gradle tasks trùng với điều CI thực sự chạy.
- [ ] Module nhiều ứng dụng xác định rõ `@SpringBootConfiguration` và đường biên của từng bộ test.
- [ ] Dữ liệu test có thể tái lập, độc lập, không chứa bí mật, có chiến lược cleanup đáng tin.
- [ ] Có thể chạy ít nhất một test bằng wrapper từ dòng lệnh và giải thích được resource/classpath nó sử dụng.

**Điểm cốt lõi:** thư mục `src/test/java` xác định **mã kiểm thử**, `src/test/resources` xác định **dữ liệu/cấu hình trên test classpath**, còn package và build task xác định **test kiểm phần nào và được tìm/chạy như thế nào**. Dùng cấu trúc phản chiếu tính năng của ứng dụng và cấu hình tường minh để mỗi bài test dễ tìm, dễ chạy lại và đáng tin trên CI.
