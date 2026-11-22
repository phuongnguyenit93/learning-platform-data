# Spring TestContext: kế thừa cấu hình, lớp @Nested và annotation tổng hợp

## 1. Mục tiêu và bức tranh tổng thể

**Spring TestContext Framework** kết nối JUnit Jupiter với Spring `ApplicationContext`: nạp bean, inject dependency vào test, chọn profile, áp dụng test properties, quản lý transaction, chạy `TestExecutionListener` và cache context. Khi nhiều test chung một phần cấu hình, có thể tổ chức theo **lớp cha**, **lớp `@Nested`** hoặc **annotation tổng hợp** (composed annotation, meta-annotation).

Ba cơ chế có liên quan nhưng **không giống nhau**:

1. **Kế thừa lớp (class inheritance):** `ChildTest extends BaseTest`; Spring có thể kế thừa `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource` cùng các test annotations phù hợp từ superclass.
2. **Kế thừa lớp bao (enclosing class inheritance):** `@Nested` của JUnit Jupiter là inner test class nằm trong một class khác; từ Spring Framework 5.3, Spring TestContext mặc định kế thừa cấu hình test từ **enclosing classes**, với lựa chọn `INHERIT` hoặc `OVERRIDE`.
3. **Annotation tổng hợp:** khai báo một annotation của dự án được **meta-annotate** bằng những annotation của JUnit và Spring, ví dụ `@SpringJUnitConfig`, `@ActiveProfiles`, `@TestPropertySource`; sau đó nhiều test dùng cùng một quy ước.

Không nên nhầm **kế thừa cấu hình test** với **kế thừa các bean Java**. Kế thừa cấu hình quyết định **những thông tin nào dùng để tạo context**; nó không tự tạo quan hệ cha–con giữa mọi `ApplicationContext`. Chỉ khi chủ động dùng `@ContextHierarchy` mới có ngữ nghĩa parent/child context theo đúng cấu hình đó.

### Khi nào nên dùng cơ chế nào?

| Nhu cầu | Lựa chọn | Lợi ích | Điểm cần chú ý |
| --- | --- | --- | --- |
| Nhiều test cần chung base Spring config và setup | Superclass trừu tượng | Dùng chung context metadata, helper/lifecycle nếu cần | Override sai có thể làm mất bean hoặc profile |
| Test cùng nghiệp vụ nhưng có nhiều kịch bản con | JUnit `@Nested` | Nhóm case theo ngữ cảnh Given/When/Then | Mode `INHERIT`/`OVERRIDE`, lifecycle của outer class |
| Hàng chục test cần cùng cấu hình bằng annotation | Custom composed annotation | Giảm lặp, thống nhất profile và setup | Giữ annotation nhỏ, dễ hiểu, tránh meta-annotation xung đột |
| Mỗi test cần tổ hợp bean hoàn toàn riêng | Test config riêng, có thể `OVERRIDE` | Chủ động cô lập lớp kiểm thử | Context khác nhau có chi phí nạp/caching |
| Ứng dụng Spring Boot cần auto-configuration | `@SpringBootTest` hoặc slice test của Boot | Bao phủ Boot behavior | Đừng mặc định `@SpringJUnitConfig` tương đương toàn bộ Boot auto-config |

Ví dụ trong bài dùng **Java 17, Spring Boot 3.5.x (Spring Framework 6.2), JUnit Jupiter 5**. Các nguyên lý vẫn áp dụng cho Spring Boot 4/Spring Framework 7, nhưng hệ JUnit, dependency và chi tiết extension lifecycle có thay đổi; cần kiểm tra tài liệu đúng dòng phiên bản.

## 2. Cấu hình cơ sở của Spring TestContext

`@ExtendWith(SpringExtension.class)` đăng ký `SpringExtension` cho JUnit Jupiter. `@ContextConfiguration` mô tả cách Spring nạp `ApplicationContext`. Spring cung cấp annotation rút gọn:

```java
@SpringJUnitConfig(MyTestConfig.class)
class MyServiceTest {
    // Các test methods...
}
```

`@SpringJUnitConfig` kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`; không cần gắn cả ba annotation trong ví dụ trên. `MyTestConfig` là cấu hình test có các bean cần kiểm tra.

Một phương án viết rõ từng thành phần:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyTestConfig.class)
class MyServiceTest {
    // Các test methods...
}
```

Hai đoạn trên **chỉ minh họa cấu hình annotation**; các kiểu `MyTestConfig` và imports cần được định nghĩa trong dự án. Ví dụ đầy đủ có thể chạy ở mục 7.

Trong Spring Boot, `@SpringBootTest` đã tích hợp hỗ trợ JUnit Jupiter/Spring TestContext và thường không cần thêm `@ExtendWith(SpringExtension.class)`. `@SpringJUnitConfig` tạo context Spring theo cấu hình chỉ định, **không bảo đảm** toàn bộ Boot auto-configuration, application startup logic hay web server được nạp. Test pure unit không cần Spring context vẫn nên dùng JUnit/Mockito trực tiếp.

## 3. Kế thừa cấu hình từ superclass

Ví dụ:

```java
@SpringJUnitConfig(BaseConfig.class)
@ActiveProfiles("base")
@TestPropertySource(properties = "app.mode=base")
abstract class AbstractIntegrationTest {
}

@ActiveProfiles("billing")
@TestPropertySource(properties = "app.mode=billing")
class BillingTest extends AbstractIntegrationTest {
}
```

Đây là **sơ đồ cấu hình**, chưa phải class test runnable. Với mặc định Spring TestContext:

- `BillingTest` có cấu hình bean từ `BaseConfig` do kế thừa `@ContextConfiguration`.
- Profile được kích hoạt gồm `base` và `billing`, vì mặc định `@ActiveProfiles(inheritProfiles=true)`.
- Thuộc tính `app.mode=billing` của subclass ghi đè giá trị cùng tên từ superclass, do mặc định `@TestPropertySource(inheritProperties=true)` và property khai báo ở lớp con có mức ưu tiên cao hơn trong nhóm thuộc tính kế thừa.
- Nếu thêm nhiều `@ContextConfiguration` theo các cấp, resource/class configuration của subclass được **bổ sung** sau phần kế thừa, trừ khi chọn thay thế.

### Bảng các cờ kế thừa phải nhớ

| Annotation | Cờ | Mặc định | Khi chuyển thành `false` |
| --- | --- | --- | --- |
| `@ContextConfiguration` | `inheritLocations` | `true` | Resource locations/**configuration classes** của superclass không được kế thừa theo cơ chế này |
| `@ContextConfiguration` | `inheritInitializers` | `true` | Context initializers từ superclass không được kế thừa |
| `@ActiveProfiles` | `inheritProfiles` | `true` | Chỉ dùng profile được giải quyết theo khai báo ở lớp hiện tại, không gộp profile từ các cấp trước |
| `@TestPropertySource` | `inheritLocations` | `true` | Không gộp các test properties **file/resource** của superclass |
| `@TestPropertySource` | `inheritProperties` | `true` | Không gộp các **inline properties** từ superclass |
| `@TestExecutionListeners` | `inheritListeners` | `true` | Không lấy custom listeners được khai báo trên superclass |
| `@DirtiesContext` | Tùy mode của annotation | Không có một cờ inherit chung | Có thể đánh dấu context cache bẩn, cần hiểu scope và thời điểm đóng context |

**Điểm dễ nhầm:** `inheritLocations=false` ở `@ContextConfiguration` áp dụng cả trường hợp khai báo `classes`, dù tên cờ có chữ “Locations”. Tương tự, `@TestPropertySource` có hai cờ độc lập: thay inline properties **không có nghĩa** tự động thay danh sách file properties nếu không đặt `inheritLocations=false`.

### Thay thế profile được kế thừa

```java
@ActiveProfiles(profiles = "isolated", inheritProfiles = false)
class IsolatedProfileTest extends AbstractIntegrationTest {
}
```

Kết quả: profile `base` ở lớp cha **không được gộp** vào tập active profiles của subclass này. Nhưng các annotation cấu hình khác vẫn có quy tắc riêng: chẳng hạn `@ContextConfiguration` và `@TestPropertySource` có thể tiếp tục được kế thừa. Chỉ đặt `inheritProfiles=false` không phải cách tách mọi thành phần cấu hình.

### Thay thế bean configuration nhưng vẫn có thể kế thừa những thứ khác

```java
@ContextConfiguration(
    classes = ChildOnlyConfig.class,
    inheritLocations = false)
class ChildOnlyContextTest extends AbstractIntegrationTest {
}
```

Nếu `AbstractIntegrationTest` có `BaseConfig` trong `@ContextConfiguration` thì `ChildOnlyContextTest` không lấy danh sách bean config đó qua kế thừa. Tuy nhiên `@ActiveProfiles("base")`/`@TestPropertySource` **vẫn có thể** được kế thừa nếu không có override riêng. Với initializers, muốn bỏ phần kế thừa cần xử lý cả `inheritInitializers=false` theo hợp đồng.

**Không nên giả định** Spring sẽ tự phát hiện đúng mọi static nested `@Configuration` trong lớp cha. Với test cần ổn định trên các dòng Spring khác nhau, khai báo `classes=...` tường minh là cách dễ kiểm soát hơn. Trình tự auto-discovery cấu hình mặc định có những khác biệt và sửa lỗi qua các phiên bản framework.

## 4. Quy tắc ưu tiên của @TestPropertySource và @ActiveProfiles

Khi có nhiều nguồn cấu hình, không thể chỉ nhìn tên annotation để xác định giá trị cuối. Một số nguyên tắc đáng nhớ:

- `@TestPropertySource(properties = "...")` khai báo **inline properties**; `@TestPropertySource(locations = "...")` chỉ tới file như `classpath:/test.properties`.
- Trong TestContext, **inline test properties** có precedence cao hơn các file test properties khai báo qua `@TestPropertySource`.
- `@DynamicPropertySource` có mức ưu tiên cao hơn `@TestPropertySource` khi chúng cùng định nghĩa một key. Điều này quan trọng với JDBC URL từ Testcontainers.
- Properties do subclass khai báo được hợp nhất theo cờ kế thừa; giá trị đến sau thường che giá trị cùng key trước đó trong nhóm đó.
- Nếu Spring Boot sử dụng `@SpringBootTest(properties = "...")`, `@DynamicPropertySource`, `@TestPropertySource` và profile-specific configuration, cần xem **thứ tự PropertySource thực tế** thay vì suy luận toàn bộ ưu tiên từ một bảng đơn giản.
- `@ActiveProfiles` lựa chọn active profiles cho context; đây **không phải** phép gán trực tiếp cho một property tùy ý. Khi profile chứa các bean khác nhau, thay profile có thể làm đổi toàn bộ graph bean và context cache key.

Ví dụ test quan sát kết quả đúng tầng:

```java
@Test
void effectivePropertyIsVisible(@Autowired Environment environment) {
    assertEquals("billing", environment.getProperty("app.mode"));
}
```

Method này chỉ là **trích đoạn** cần test class có cấu hình phù hợp, các imports và `Environment`. Kiểm tra `environment.getActiveProfiles()` khi test phụ thuộc profile, thay vì chỉ xác nhận tên profile được viết trong source code.

**Tránh lỗi im lặng:** nếu cả base và subclass đều dùng `@TestPropertySource(properties="db.url=...")`, subclass có thể trỏ toàn suite sang một database khác. Nên đặt riêng cấu hình DB test và không cho test context ghi vào production database.

## 5. Lớp @Nested của JUnit Jupiter và Spring TestContext

`@Nested` nằm ở `org.junit.jupiter.api.Nested` và dùng cho một **non-static inner class**. Nó nhóm các test theo kịch bản và cho phép inner class tham chiếu state của outer instance. JUnit chạy các test methods ở nested class như test độc lập và áp dụng lifecycle của enclosing class theo quy tắc của JUnit.

```java
@SpringJUnitConfig(TestBeans.class)
class CheckoutTest {

    @Nested
    class WithValidCart {

        @Test
        void completesCheckout(@Autowired CheckoutService checkout) {
            // Assertions...
        }
    }
}
```

Đây là đoạn minh họa; `TestBeans` và `CheckoutService` phải tồn tại. **Không** khai báo `static class WithValidCart` nếu muốn đây là JUnit `@Nested` test class.

### Hai chiều kế thừa cần phân biệt

1. **Superclass:** `CheckoutTest extends BaseTest` → kế thừa theo **type hierarchy**.
2. **Enclosing class:** `CheckoutTest.WithValidCart` → kế thừa theo **lexical enclosing hierarchy**, được `@NestedTestConfiguration` điều khiển trong Spring TestContext.

Từ **Spring Framework 5.3**, chế độ enclosing mặc định là **`INHERIT`**; từ Spring Framework 5.0–5.2, cấu hình ở outer class chưa được kế thừa theo ngữ nghĩa tương tự. Bài viết này nhắm 6.2/7.x, nơi hỗ trợ nested inheritance đầy đủ.

### INHERIT: dùng cấu hình từ outer class

```java
@SpringJUnitConfig(BaseConfig.class)
@ActiveProfiles("test")
class OrderTest {

    @Nested
    class ValidOrders {
        @Test
        void readsSpringBean(@Autowired SomeBean bean) {
            // Dùng context đã được cấu hình từ outer class.
        }
    }
}
```

`@NestedTestConfiguration(EnclosingConfiguration.INHERIT)` có thể ghi tường minh để nhấn mạnh ý định, nhưng mặc định là INHERIT trừ khi project thay cấu hình toàn cục. `@Nested` không “khởi động một Spring context hoàn toàn mới” cho mỗi inner class; TestContext có thể dùng lại context cache nếu cấu hình tương đương.

### OVERRIDE: không nhận test configuration từ outer class

```java
@Nested
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
@SpringJUnitConfig(IsolatedConfig.class)
@TestPropertySource(properties = "app.mode=isolated")
class IsolatedOrders {
    @Test
    void usesOwnContext(@Autowired SomeBean bean) {
        // Chỉ dựa vào cấu hình Spring test được khai báo cho nested class.
    }
}
```

**Quan trọng:** `OVERRIDE` làm nested class không dùng cấu hình TestContext **từ enclosing class**. Vì vậy, nên khai báo đầy đủ `@SpringJUnitConfig` hoặc các annotation/extension cần thiết trên nested class. `OVERRIDE` không có nghĩa “xóa mọi annotation Java hoặc mọi JUnit extension kế thừa”; nó kiểm soát tập annotation Spring TestContext theo danh mục được framework hỗ trợ. Nếu nested class tự mở rộng một superclass khác, kế thừa superclass vẫn cần được hiểu theo quy tắc riêng.

Một khai báo `@NestedTestConfiguration` trên outer class cũng có thể áp dụng cho các nested classes phía trong. Có thể đặt:

```java
@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)
class TopLevelTest {
    @Nested
    class InnerTest {
        // Theo mode OVERRIDE được áp dụng từ enclosing class.
    }
}
```

Mode mặc định toàn project có thể cấu hình bằng system property `spring.test.enclosing.configuration=OVERRIDE` (hoặc Spring properties mechanism). Khi migrate từ test suite cũ, kiểm tra cờ này để tránh hiểu sai việc class không tìm thấy bean. Nên khai báo `INHERIT`/`OVERRIDE` tường minh ở nơi hành vi phụ thuộc mạnh vào mode dự án.

### Nested class thêm profile/properties

```java
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles("base")
class OuterTest {

    @Nested
    @ActiveProfiles("scenario")
    @TestPropertySource(properties = "app.label=nested")
    class ScenarioTest {
        // Profile gồm base + scenario nếu inheritProfiles=true.
        // Property inline có thể bổ sung/che property từ outer.
    }
}
```

Trong mode `INHERIT`, nested class có thể **mở rộng cấu hình outer** tương tự subclass. Hai nested classes dùng `@ActiveProfiles("scenario-A")` và `@ActiveProfiles("scenario-B")` thường tạo **hai merged context configurations khác nhau**; vì profile tham gia context cache key, chúng không nhất thiết cùng dùng một context.

### Lifecycle của @Nested

- `@BeforeEach` trên outer class chạy trước lifecycle/test method của nested class theo JUnit; `@AfterEach` bên ngoài được gọi theo thứ tự unwind thích hợp.
- `@Nested` non-static giữ reference tới outer instance; đừng lưu mutable state trên outer và giả định các nested tests luôn chia sẻ cùng một object theo cùng thứ tự. JUnit Jupiter mặc định tạo test instance theo method; `@TestInstance(PER_CLASS)` thay vòng đời instance.
- Trên Java 17, static `@BeforeAll`/`@AfterAll` trong nested class được Java hỗ trợ; với Java cũ hơn có giới hạn hoặc cần `PER_CLASS`. Nên đọc phiên bản JUnit đang dùng.
- Khi Spring context bị `@DirtiesContext`, TestContext có thể phải nạp context lại; nested tests đang dùng cùng context có thể chịu ảnh hưởng. Tránh `@DirtiesContext` nếu có thể reset state bằng fixture hoặc transaction rollback phù hợp.
- Không nên đặt test cấu hình khác nhau rồi inject cùng một Spring bean vào **outer field** và kỳ vọng field đó tự đổi giá trị khi từng nested child dùng context khác. Với Spring Framework 6.2, nên inject ở **nested test method/constructor/field** phù hợp. Spring Framework 7.0 cải thiện cơ chế extension context trong nested hierarchy, vì vậy hãy kiểm tra lifecycle khi nâng cấp.

## 6. Annotation tổng hợp và @SpringJUnitConfig

Spring cho phép dùng nhiều annotation của TestContext như **meta-annotation**. Nếu mọi repository test đều cần cùng config và profile, có thể viết một annotation thay cho nhiều dòng lặp:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles("integration")
@TestPropertySource(properties = "app.feature.enabled=true")
@interface IntegrationScenarioTest {
}
```

Sử dụng:

```java
@IntegrationScenarioTest
class OrderRepositoryTest {
    @Test
    void savesOrder() {
        // Code test...
    }
}
```

Đây là hai **đoạn minh họa**; ví dụ chạy được với annotation tổng hợp nằm ở phần 7. Các thành phần cơ bản:

| Thành phần | Mục đích |
| --- | --- |
| `@Target(ElementType.TYPE)` | Cho phép gắn lên type/test class |
| `@Retention(RetentionPolicy.RUNTIME)` | Spring/JUnit có thể đọc annotation khi chạy |
| `@Documented` | Annotation xuất hiện trong Javadoc, tùy chọn nhưng hữu ích |
| `@SpringJUnitConfig(...)` | Đăng ký SpringExtension và cấu hình context |
| `@ActiveProfiles(...)` | Gắn profile tiêu chuẩn cho suite |
| `@TestPropertySource(...)` | Gắn property test dùng chung |
| Annotation của dự án | Một tên ngắn, thể hiện hợp đồng và phạm vi sử dụng |

Không tự mặc định mọi annotation Java đều hợp lệ làm meta-annotation trong mọi Spring/JUnit framework version. Spring TestContext có danh sách annotation hỗ trợ, ví dụ `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@Transactional`, `@Sql`, `@DirtiesContext`, `@SpringJUnitConfig`. `@Test` và `@Tag` của JUnit Jupiter cũng hỗ trợ composition ở method-level theo quy tắc JUnit.

### Phân biệt composed annotation với superclass

- Composed annotation chia sẻ **metadata**; không mang các field/helper/method Java từ test class khác.
- Superclass chia sẻ **metadata được kế thừa** và có thể chia sẻ **Java fields/lifecycle/helper methods**.
- Có thể kết hợp chúng: base class chứa fixture/helper, annotation tổng hợp chứa Spring test context chuẩn.
- Nếu một test có yêu cầu riêng, đừng tạo hàng chục composed annotation với các tên mơ hồ; tốt hơn giữ một annotation đơn giản và khai báo thêm những thay đổi cục bộ rõ ràng.

### Expose thuộc tính bằng @AliasFor

Đôi khi cần cho test chọn profile mà vẫn dùng config chung. Spring cho phép một thuộc tính của composed annotation làm **alias** cho thuộc tính của meta-annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(TestBeans.class)
@ActiveProfiles
@interface ProfiledSpringTest {

    @AliasFor(annotation = ActiveProfiles.class, attribute = "profiles")
    String[] profiles() default {};
}
```

Dùng `@ProfiledSpringTest(profiles = "audit")` để truyền profile tới `@ActiveProfiles`. Đây là **trích đoạn annotation**, yêu cầu import `org.springframework.core.annotation.AliasFor`, `ActiveProfiles`, `SpringJUnitConfig` và các annotation Java tương ứng. Không phải mọi thuộc tính đều được alias tùy ý: kiểu trả về và default phải tuân quy tắc của `@AliasFor`; nên kiểm chứng bằng một test thực chạy context.

Nếu alias vào attribute mặc định của Spring annotation nhưng đồng thời khai báo giá trị meta-annotation khác hoặc tạo nhiều alias xung đột, việc tổng hợp annotation có thể lỗi lúc chạy. Không dùng alias nếu chưa có nhu cầu tái sử dụng thật sự.

### Annotation tổng hợp cho test method

Ví dụ `@Test` + `@Tag("integration")`:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Test
@Tag("integration")
@interface IntegrationCase {
}
```

Sau đó `@IntegrationCase` trên method đồng nghĩa method được JUnit đánh dấu test và gắn tag. Đây là ví dụ composition **ở JUnit Jupiter**, không tự nạp Spring context: class chứa method vẫn cần cơ chế test Spring tương ứng khi cần bean.

**Chú ý:** Một annotation tổng hợp có `@Transactional` có thể làm mọi test dùng nó chạy trong transaction và rollback theo cấu hình TestContext, khiến test vô tình không kiểm tra hành vi commit thực. Chỉ đưa `@Transactional` hoặc `@DirtiesContext` vào annotation chung khi đó là yêu cầu thật của tất cả tests dùng nó.

## 7. Ví dụ hoàn chỉnh: Spring Boot 3.5, Java 17, JUnit Jupiter

Ví dụ này trình diễn **superclass inheritance, `@Nested` INHERIT, `@Nested` OVERRIDE, inline property precedence và composed annotation**. Có thể chạy mà không cần database, network hoặc web server; Spring chỉ tạo context nhẹ chứa một bean.

### 7.1. Cấu trúc

```text
testcontext-inheritance-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── SpringContextInheritanceTest.java
```

### 7.2. pom.xml hoàn chỉnh

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>testcontext-inheritance-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Project dùng parent Boot để quản lý Spring Framework, JUnit và dependency test. Không khai báo version riêng cho `spring-test`/JUnit/Mockito. Khi áp dụng vào dự án đã có BOM, giữ **version chính thức của dự án** thay vì copy `3.5.0`.

### 7.3. SpringContextInheritanceTest.java hoàn chỉnh

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.NestedTestConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

// Context nhẹ để chứng minh property được áp dụng khi tạo bean.
@Configuration(proxyBeanMethods = false)
class MessageConfig {
    @Bean
    MessageReader messageReader(Environment environment) {
        return new MessageReader(
                environment.getProperty("demo.message", "unset"));
    }
}

record MessageReader(String value) {}

// Cấu hình lớp cha được các lớp con kế thừa theo mặc định.
@SpringJUnitConfig(MessageConfig.class)
@ActiveProfiles("base")
@TestPropertySource(properties = {
        "demo.message=base",
        "demo.common=shared"
})
abstract class BaseSpringTest {
}

@ActiveProfiles("feature")
@TestPropertySource(properties = "demo.message=feature")
class SpringContextInheritanceTest extends BaseSpringTest {

    @Test
    void subclassAddsProfileAndOverridesInlineProperty(
            @Autowired MessageReader reader,
            @Autowired Environment environment) {
        assertEquals("feature", reader.value());
        assertEquals("shared",
                environment.getProperty("demo.common"));
        List<String> profiles =
                Arrays.asList(environment.getActiveProfiles());
        assertTrue(profiles.contains("base"));
        assertTrue(profiles.contains("feature"));
    }

    @Nested
    class InheritedNested {

        @Test
        void inheritsEnclosingConfiguration(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("feature", reader.value());
            assertEquals("shared",
                    environment.getProperty("demo.common"));
        }
    }

    @Nested
    @TestPropertySource(properties = "demo.message=nested")
    class NestedWithDifferentProperty {

        @Test
        void nestedPropertyWins(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("nested", reader.value());
            assertEquals("shared",
                    environment.getProperty("demo.common"));
            assertTrue(Arrays.asList(environment.getActiveProfiles())
                    .contains("base"));
        }
    }

    @Nested
    @NestedTestConfiguration(
            NestedTestConfiguration.EnclosingConfiguration.OVERRIDE)
    @SpringJUnitConfig(MessageConfig.class)
    @TestPropertySource(properties = "demo.message=isolated")
    class NestedWithOverride {

        @Test
        void doesNotInheritEnclosingProfileAndProperties(
                @Autowired MessageReader reader,
                @Autowired Environment environment) {
            assertEquals("isolated", reader.value());
            assertFalse(Arrays.asList(environment.getActiveProfiles())
                    .contains("base"));
            assertFalse(Arrays.asList(environment.getActiveProfiles())
                    .contains("feature"));
            assertEquals(null, environment.getProperty("demo.common"));
        }
    }
}

// Annotation tổng hợp sử dụng cùng config nhưng có metadata riêng.
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringJUnitConfig(MessageConfig.class)
@ActiveProfiles("meta")
@TestPropertySource(properties = "demo.message=composed")
@interface MessageScenarioTest {
}

@MessageScenarioTest
class ComposedAnnotationTest {

    @Test
    void composedAnnotationLoadsItsOwnTestMetadata(
            @Autowired MessageReader reader,
            @Autowired Environment environment) {
        assertEquals("composed", reader.value());
        assertTrue(Arrays.asList(environment.getActiveProfiles())
                .contains("meta"));
    }
}
```

Chú ý trong `NestedWithOverride`, `@SpringJUnitConfig(MessageConfig.class)` được khai báo lại để nested class có thông tin context rõ ràng. `@NestedTestConfiguration(OVERRIDE)` không làm mất quyền truy cập Java tới outer instance, nhưng các Spring TestContext annotations từ outer không được gộp theo chế độ này.

Ví dụ deliberately không inject Spring bean vào **field của outer** cho các nested tests: mỗi test method nhận bean theo context của trường hợp nó đang kiểm tra. Điều này tránh hiểu nhầm injection field ngoài luôn thay đổi theo context của từng nested child trong mọi Spring Framework version.

### 7.4. Chạy và kết quả mong đợi

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Có thể chạy riêng top-level test:

```bash
mvn test -Dtest=SpringContextInheritanceTest
```

Tùy Maven Surefire và JUnit Platform discovery, việc chạy một filter cụ thể có thể chọn khác nhau đối với nested classes; chạy toàn bộ `mvn test` là cách đơn giản để quan sát tất cả các method của ví dụ.

**Kỳ vọng:** tổng cộng **5 test methods** đạt PASS: một ở class kế thừa, ba trong các nested classes, một ở test dùng composed annotation. Không có `System.out.println`, nên không có stdout chương trình cố định. Maven in log và kết quả kiểm thử tùy plugin; xem `target/surefire-reports` nếu test fail.

| Test | Điều chứng minh | Kỳ vọng |
| --- | --- | --- |
| `subclassAddsProfileAndOverridesInlineProperty` | Subclass lấy config cha, gộp base + feature, override property | `reader.value() = "feature"` |
| `InheritedNested.inheritsEnclosingConfiguration` | Nested mặc định INHERIT lấy cấu hình từ outer | `reader.value() = "feature"` |
| `NestedWithDifferentProperty.nestedPropertyWins` | Nested thêm inline property cùng key | `reader.value() = "nested"` |
| `NestedWithOverride.doesNotInheritEnclosingProfileAndProperties` | OVERRIDE không nhận profile/property enclosing | `reader.value() = "isolated"`; không có `base`/`feature` |
| `ComposedAnnotationTest.composedAnnotationLoadsItsOwnTestMetadata` | Custom annotation được Spring/JUnit đọc | `reader.value() = "composed"`; profile `meta` |

**Giới hạn của demo:** test chỉ chứng minh Spring TestContext nạp bean, cấu hình và property. Nó không kiểm tra Spring Boot auto-configuration, transaction rollback, HTTP routes, database, Security filter chain hay context initialization bằng `@SpringBootTest`.

## 8. Khi áp dụng vào @SpringBootTest và test slices

Trong ứng dụng Boot thật:

```java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseBootIntegrationTest {
}

class OrderIntegrationTest extends BaseBootIntegrationTest {
    // @Test methods...
}
```

`@SpringBootTest` tham gia bootstrap do Spring Boot quản lý; superclass có thể cung cấp metadata test chung và annotation `@ActiveProfiles`. Không nhất thiết phải thêm `@ContextConfiguration` nếu Boot tự tìm được `@SpringBootApplication`/`@SpringBootConfiguration` theo package.

### @TestConfiguration khác @Configuration của Boot

Khi test Boot cần thêm một bean test, có thể khai báo static nested `@TestConfiguration` để **bổ sung** vào application configuration:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @TestConfiguration(proxyBeanMethods = false)
    static class ExtraTestBeans {
        @Bean
        Clock testClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
```

Đây là đoạn cấu hình minh họa, cần imports và code test/ứng dụng khác để chạy. Một static nested `@Configuration` (không phải `@TestConfiguration`) có thể làm Boot dùng cấu hình đó **thay cho** primary application configuration khi Boot tự phát hiện test config; static nested `@TestConfiguration` thông thường được thêm vào bên cạnh primary config. Một top-level `@TestConfiguration` thường cần `@Import(...)` tường minh để xuất hiện trong test.

**Đừng lẫn lộn** static nested `@TestConfiguration` với JUnit `@Nested` test class:

| Loại class | Chức năng | Khai báo thường gặp |
| --- | --- | --- |
| JUnit nested test | Chứa test methods, kế thừa enclosing test metadata theo mode | `@Nested class Cases { ... }` (non-static) |
| Spring test bean config | Định nghĩa `@Bean` phụ trợ | `@TestConfiguration static class Beans { ... }` |
| Spring `@Configuration` | Định nghĩa application/configuration bean graph | `@Configuration static class Config { ... }` |

Một số slice tests như `@WebMvcTest`, `@DataJpaTest` có bootstrap và scan filters riêng. **Không trộn nhiều slice annotations** trên một test rồi mặc định chúng sẽ hợp nhất. Nếu cần nhiều tầng, chọn test scope rộng hơn hoặc import các cấu hình được hỗ trợ.

Với Boot 4, cấu trúc test starters theo công nghệ thay đổi; cần chọn test starter phù hợp như `spring-boot-starter-webmvc-test` khi dùng MVC test. Nguyên tắc inheritance và composed annotations vẫn đúng, nhưng **package imports và module dependencies** của một số annotation có thay đổi khi chuyển Boot 3 → 4.

## 9. TestExecutionListeners, transaction và annotations có tác dụng sâu

### TestExecutionListeners

`@TestExecutionListeners` quyết định các listeners chạy quanh vòng đời test (dependency injection, transaction, SQL, bean overrides, v.v.). Custom listeners có thể được kế thừa từ superclass hoặc enclosing class tùy mode.

```java
@TestExecutionListeners(
    listeners = MyAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class AuditTest {
}
```

Đoạn trên chỉ minh họa và yêu cầu `MyAuditListener` là implementation hợp lệ. **Không quên `MERGE_WITH_DEFAULTS`** nếu muốn giữ các default listeners cùng custom listener. Khi chỉ khai báo custom listeners mà không merge, test có thể mất dependency injection hoặc transaction test vì cấu hình thay thế tập listeners mặc định.

`inheritListeners=false` chỉ điều khiển listeners kế thừa, không thay cho `mergeMode`. Tương tự các annotation có cờ inherit, cần kiểm tra cả hai chiều: khai báo ở superclass và khai báo trong enclosing class khi dùng `@Nested`.

### @Transactional trên base/composed annotation

`@Transactional` trong TestContext thường kích hoạt test-managed transaction và mặc định rollback sau mỗi method, nếu đã có transaction manager phù hợp. Nếu base test hoặc composed annotation gắn `@Transactional`, các test con có thể chịu tác động mà không thấy annotation viết trực tiếp trên class.

- Test service cần verify commit/side effect sau transaction thật thì rollback tự động có thể che vấn đề.
- Test với `@SpringBootTest(webEnvironment=RANDOM_PORT)` gọi HTTP qua server thread khác không thể dựa vào transaction của test method để rollback transaction phía server.
- Với `@Nested` có cấu hình transaction khác, cần kiểm tra inheritance mode và annotation được áp dụng thực sự.
- Chỉ đưa `@Transactional` vào custom annotation cho suite mà rollback là một phần hợp đồng kiểm thử.

### @Sql, @Rollback, @DirtiesContext

`@Sql` có thể load dataset trước test hoặc cleanup, `@Rollback` thay đổi transaction behavior và `@DirtiesContext` khiến cache entry bị đóng/loại khỏi cache. Nếu một annotation tổng hợp gắn chúng, mọi test dùng annotation sẽ chịu tác dụng đó. Tránh gắn `@DirtiesContext` cho tất cả test chỉ để “sạch dữ liệu” vì nó làm tăng thời gian khởi động context và có thể che thiết kế fixture sai.

## 10. Context caching: cấu hình giống nhau chưa chắc tạo context mới

Spring TestContext cache các `ApplicationContext` theo **merged context configuration** chứ không đơn thuần theo tên class. Những thành phần của cache key có thể bao gồm:

- `@ContextConfiguration` classes/locations/initializers, context loader và hierarchy.
- `@ActiveProfiles`.
- `@TestPropertySource` properties và locations.
- Context customizers, gồm `@DynamicPropertySource`, `@MockitoBean`/bean override và tùy chỉnh từ Spring Boot.
- Những cấu hình Spring test khác có ảnh hưởng tới cách nạp context.

Ví dụ:

| Test | Config | Profile | Inline properties | Tái sử dụng context? |
| --- | --- | --- | --- | --- |
| Test A | `MessageConfig` | `base` | `demo.message=base` | Context đầu tiên |
| Test B | `MessageConfig` | `base` | `demo.message=base` | **Có thể** dùng lại nếu toàn bộ cache key khớp |
| Test C | `MessageConfig` | `base` | `demo.message=feature` | Thường khác key |
| Test D | `MessageConfig` | `feature` | `demo.message=base` | Thường khác key |
| Test E | `MessageConfig` | `base` | `demo.message=base` + mock bean khác | Có thể khác key do context customizers |

**Không dùng `assertSame(contextA, contextB)` như một đảm bảo xuyên mọi Maven fork/JVM**. Cache là static trong cùng process TestContext; khi build tool tạo process mới, context sẽ nạp lại. Mặc định Spring giới hạn kích thước cache và có thể evict LRU; `@DirtiesContext` cũng khiến context không được tái sử dụng theo cách thông thường.

Khi có hai composed annotations khác nhau nhưng cuối cùng tạo **merged metadata tương đương**, Spring vẫn có thể dùng cùng context. Ngược lại, hai lớp cùng annotation tên giống nhau nhưng thêm `@TestPropertySource` khác sẽ có context riêng.

### Tối ưu có cơ sở

1. Giữ cấu hình chung ở một nơi; tránh mỗi test đặt các properties có cùng ý nghĩa nhưng **khác khoảng trắng/thứ tự** không cần thiết. Với inline test property, chuỗi khai báo có thể tham gia cache key.
2. Chỉ dùng `@DirtiesContext` nếu test thật sự thay đổi state của context/bean theo cách không reset an toàn được.
3. Nếu nhiều test bắt buộc có cấu hình khác nhau, chấp nhận context riêng; đừng ép tái sử dụng để rồi dữ liệu/bean bị nhiễm chéo.
4. Ưu tiên test slice hoặc pure unit khi bài test không cần cả application context.
5. Khi gặp test chậm, xem thống kê cache trước khi tăng song song mù quáng hoặc biến mọi test thành singleton.
6. Với Testcontainers và `@DynamicPropertySource`, nếu property động có giá trị khác giữa các subclass nhưng cùng config metadata/cache key, cân nhắc `@DirtiesContext` hoặc thiết kế context riêng phù hợp để tránh lấy nhầm connection từ context cũ.

## 11. Những lỗi thường gặp, nguyên nhân và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Nested test không inject được bean ở outer | Mode `OVERRIDE` hoặc thiếu config riêng; version/package không phù hợp | Kiểm tra `@NestedTestConfiguration` và khai báo `@SpringJUnitConfig` khi override |
| Subclass có bean không mong muốn từ base | `inheritLocations=true` theo mặc định | Xem lại `@ContextConfiguration(inheritLocations=false)` nếu cần thay config |
| Chỉ muốn thay profile nhưng vẫn thấy profile base | `inheritProfiles=true` mặc định | Dùng `inheritProfiles=false` nếu thật sự cần tách |
| Đã đặt `inheritProperties=false` nhưng vẫn thấy file property từ cha | `inheritProperties` chỉ cho inline properties | Xem thêm `inheritLocations=false` của `@TestPropertySource` |
| Test subclass đọc property không như mong đợi | Inline property bị che bởi config khác hoặc dynamic properties | Inspect `Environment`/PropertySources, đối chiếu precedence |
| Thêm custom listener thì `@Autowired` không hoạt động | Vô tình thay toàn bộ listeners mặc định | Dùng `MERGE_WITH_DEFAULTS` |
| Gắn `@Transactional` trong custom annotation làm test luôn rollback | Annotation tổng hợp có side effect | Rà soát meta-annotations và viết integration test commit riêng |
| Context tải lại quá nhiều lần | Profile/properties/mock customizers khác nhau hoặc `@DirtiesContext` | Xem cache key, giảm cấu hình khác biệt không cần thiết |
| Outer field inject bean của context A nhưng nested test dùng context B | Kỳ vọng field tự thay theo nested configuration | Inject dependency ở nested class/test method, không dựa vào field outer |
| `@Nested` báo không có test hoặc lỗi cấu trúc | Dùng static class hoặc runner/JUnit version không hỗ trợ | Dùng non-static inner class, JUnit Jupiter engine và build test platform |
| Custom annotation không được Spring nhận | Thiếu `@Retention(RUNTIME)`, sai `@Target` hoặc không meta-annotate với annotation cần | Kiểm tra declaration và import; chạy test xác nhận |
| `@AliasFor` báo cấu hình alias không hợp lệ | Kiểu/default/attribute sai hoặc meta-annotation xung đột | Dùng alias đúng contract và test khi Spring tổng hợp annotation |
| Đưa `@SpringJUnitConfig` vào Boot test nhưng auto-config không có | `@SpringJUnitConfig` chỉ tạo context theo config Spring chỉ định | Chọn `@SpringBootTest`/test slice nếu cần Boot features |
| Dùng `@Configuration` nested thay `@TestConfiguration` trong Boot | Thay primary configuration ngoài ý muốn | Dùng static nested `@TestConfiguration` khi muốn bổ sung |
| Test 6.2 chạy khác 7.x ở nested injection/lifecycle | Thay đổi trong `SpringExtension` scope với nested hierarchy | Kiểm tra upgrade notes, tránh field outer phụ thuộc context nested |
| Kế thừa annotation rồi thêm nhiều slice-test annotations | Bootstrap chiến lược xung đột | Chọn một test bootstrap/slice đúng cấp độ |

## 12. Quy trình thiết kế test suite và checklist

### Quy trình 8 bước

1. **Xác định mục tiêu test**: unit thuần, Spring context, slice hay Boot full integration. Không tạo context nếu không cần.
2. **Xác định phần chung**: bean config, test properties, active profiles, listeners, transactions, data fixtures.
3. **Chọn abstraction**: base abstract class cho fixture/helpers; `@Nested` cho kịch bản cùng domain; composed annotation cho metadata dùng lại.
4. **Chốt inheritance rules**: liệt kê cờ `inheritLocations`/`inheritInitializers`/`inheritProfiles`/`inheritProperties`, cùng mode `INHERIT`/`OVERRIDE`.
5. **Chọn phạm vi override nhỏ nhất**: nếu chỉ muốn đổi một key, thêm `@TestPropertySource` trên subclass/nested; nếu muốn context riêng hoàn toàn, khai báo rõ `OVERRIDE` và config riêng.
6. **Viết test của merged configuration**: assert bean được inject, giá trị `Environment` thực, active profiles, một vài behavior quan trọng. Đừng suy đoán từ tên annotation.
7. **Đánh giá cache và side effects**: profile/property khác key sẽ tạo context khác; transaction rollback và `@DirtiesContext` ảnh hưởng test suite.
8. **Chạy toàn bộ tests bằng JUnit Platform** và xem reports, bảo đảm nested/composed tests thật sự được phát hiện và chạy.

### Checklist nghiệm thu

- [ ] Hiểu sự khác nhau giữa superclass inheritance và enclosing `@Nested` inheritance?
- [ ] Biết `@SpringJUnitConfig` bao gồm những annotation gì?
- [ ] `@ContextConfiguration` có `inheritLocations`/`inheritInitializers` phù hợp?
- [ ] `@ActiveProfiles(inheritProfiles=...)` được dùng đúng khi thêm hay thay profile?
- [ ] `@TestPropertySource` phân biệt cờ kế thừa inline properties và resource locations?
- [ ] Đã kiểm tra giá trị property thực tế qua `Environment`?
- [ ] `@Nested` là non-static class và mode `INHERIT`/`OVERRIDE` được chủ động chọn?
- [ ] Nested có config riêng đầy đủ khi `OVERRIDE`?
- [ ] Không nhầm `@Nested` với static nested `@TestConfiguration` của Boot?
- [ ] Custom composed annotation có `@Target`, `@Retention(RUNTIME)` và meta-annotations chính xác?
- [ ] Nếu dùng `@AliasFor`, alias đã được test thực tế và không xung đột?
- [ ] `@TestExecutionListeners` giữ default listeners khi cần?
- [ ] `@Transactional`, `@Sql`, `@DirtiesContext` không gây side effect ngoài ý định?
- [ ] Context cache được tái sử dụng khi metadata khớp, và các khác biệt là có chủ đích?
- [ ] Đã chạy toàn bộ test methods của superclass/nested/composed annotation, không để runner lọc nhầm?
- [ ] Nếu chuyển Spring Boot 3 → 4, đã rà soát module, JUnit và lifecycle của SpringExtension?

## 13. Tài liệu tham khảo chính thức

1. [Spring Framework — Context Configuration Inheritance](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/inheritance.html): `@ContextConfiguration` và hai cờ inherit.
2. [Spring Framework — @Nested test class configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html): `INHERIT`, `OVERRIDE` và các ví dụ nested.
3. [Spring Framework — Spring JUnit Jupiter Testing Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html): `@SpringJUnitConfig`, `@NestedTestConfiguration`, danh mục annotation được hỗ trợ.
4. [Spring Framework — Meta-Annotation Support for Testing](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-meta.html): custom composed annotations.
5. [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): inheritance và precedence của inline/file properties.
6. [Spring Framework — Active Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html): `inheritProfiles` và resolver.
7. [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context cache key và thời điểm nạp lại context.
8. [Spring Framework — TestExecutionListener Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html): `inheritListeners` và `MERGE_WITH_DEFAULTS`.
9. [JUnit Jupiter — Nested Tests](https://docs.junit.org/5.14.1/writing-tests/nested-tests.html): cú pháp `@Nested` và lifecycle.
10. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@TestConfiguration`, test slices và context caching.

**Ghi nhớ:** superclass và `@Nested` quyết định **Spring TestContext metadata được kế thừa từ đâu**; `@NestedTestConfiguration` quyết định **có kế thừa metadata của enclosing class hay không**; composed annotation quyết định **cách đóng gói metadata dùng lại**. Hãy kiểm chứng bằng bean, property và profile **thực tế**, sau đó mới tối ưu context caching.
