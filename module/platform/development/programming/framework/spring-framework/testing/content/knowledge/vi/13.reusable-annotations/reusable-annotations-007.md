# Giữ annotation tổ hợp đơn giản và dễ truy tìm

Trong Spring Framework Testing, một test class thường cần nhiều annotation để khai báo Spring context, profile, transaction, SQL fixture hoặc cách bootstrap test. Khi nhiều test lặp lại cùng một nhóm cấu hình, có thể gom các annotation đó thành một *composed annotation* (annotation tổ hợp). Spring nhận diện các annotation nền thông qua cơ chế meta-annotation, nhờ đó test class chỉ cần khai báo một annotation có tên mô tả mục đích.

Annotation tổ hợp giúp giảm lặp lại và thể hiện quy ước kiểm thử của dự án. Tuy nhiên, nếu nó gom quá nhiều hành vi, ẩn các cấu hình quan trọng hoặc có tên chung chung, người đọc sẽ khó biết test thực sự được cấu hình như thế nào. Một annotation dùng lại tốt cần có một mục đích rõ ràng, số thuộc tính vừa đủ và vị trí dễ tìm trong mã nguồn.

## 1. Annotation tổ hợp trong Spring là gì?

Trong Java, một annotation có thể được đặt trên khai báo annotation khác. Annotation được đặt bên trong được gọi là *meta-annotation*. Spring sử dụng thông tin meta-annotation để nhận diện cấu hình và hành vi kiểm thử.

Ví dụ, `@SpringJUnitConfig` là annotation tổ hợp do Spring cung cấp. Nó kết hợp việc đăng ký `SpringExtension` cho JUnit Jupiter với cấu hình `@ContextConfiguration`. Vì vậy, test có thể dùng một annotation để khai báo tích hợp Spring và nguồn cấu hình context.

Tương tự, một dự án có thể tạo annotation riêng để kết hợp profile và transaction:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@SpringJUnitConfig
@ActiveProfiles("test")
@Transactional
public @interface DatabaseSpringTest {
}
```

Test class sử dụng annotation:

```java
@DatabaseSpringTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void findsSavedOrder() {
        // Kiểm tra repository
    }
}
```

Ở ví dụ này, `@DatabaseSpringTest` biểu thị một quy ước kiểm thử gồm Spring test context, profile `test` và transaction dành cho test. Spring có thể đọc các annotation nền thông qua annotation tổ hợp.

Annotation tổ hợp không phải một cơ chế khởi tạo context riêng. Nó gom metadata của các annotation đã có để Spring TestContext Framework và JUnit Jupiter xử lý theo đúng chức năng của chúng.

## 2. Khi nào nên tạo annotation dùng lại?

Nên cân nhắc annotation tổ hợp khi nhiều test class lặp lại cùng một nhóm annotation có ý nghĩa ổn định.

Ví dụ, nhiều repository integration test đều cần:

- Khởi tạo Spring context từ cấu hình kiểm thử.
- Kích hoạt profile `test`.
- Chạy trong transaction do Spring Test quản lý.
- Sử dụng một nhóm thuộc tính kiểm thử chung.

Nếu từng test class khai báo toàn bộ nhóm này, thay đổi quy ước sẽ phải cập nhật nhiều nơi. Một annotation tổ hợp có tên rõ ràng gom cấu hình đó tại một điểm.

Annotation dùng lại cũng hữu ích khi tên của nó diễn đạt tốt hơn danh sách annotation nền. Ví dụ, `@TransactionalRepositoryTest` cho người đọc biết mục đích của test ngay trên class.

Không nên tạo annotation chỉ để rút ngắn một hoặc hai dòng nếu nhóm cấu hình chỉ xuất hiện một lần. Annotation mới tạo thêm một khái niệm mà người đọc cần tìm hiểu. Giá trị của nó xuất hiện khi có một quy ước chung thực sự cần được dùng lại.

## 3. Giữ mỗi annotation một mục đích rõ ràng

Tên annotation nên mô tả phạm vi kiểm thử hoặc cấu hình mà nó cung cấp. Một số tên có thể dùng trong dự án:

| Tên annotation | Ý nghĩa nên thể hiện |
|---|---|
| `@MvcSliceTest` | Test lớp MVC với phạm vi slice phù hợp |
| `@JdbcIntegrationTest` | Integration test tập trung vào JDBC |
| `@TransactionalRepositoryTest` | Test repository có transaction |
| `@ExternalServiceContractTest` | Test hợp đồng với một dịch vụ bên ngoài |
| `@SpringComponentTest` | Test một nhóm component Spring theo cấu hình xác định |

Tên như `@TestConfig`, `@CommonTest` hoặc `@SpringTest` thường quá rộng. Khi dự án có nhiều loại test, những tên này không cho biết annotation kích hoạt profile nào, có transaction hay không, và phạm vi context ra sao.

Một annotation nên có một chủ đề chính. Ví dụ, `@MvcSliceTest` không nên đồng thời mang ý nghĩa của full application integration test, database migration test và kiểm thử message broker. Nếu các nhóm test có phạm vi khác nhau, hãy tạo các annotation riêng với tên phản ánh đúng phạm vi.

## 4. Khai báo annotation tổ hợp đúng chuẩn Java

Một annotation tổ hợp thường cần các metadata sau:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
public @interface RepositoryIntegrationTest {
}
```

Ý nghĩa:

- `@Target(ElementType.TYPE)`: giới hạn nơi có thể dùng annotation, ở đây là khai báo class hoặc interface.
- `@Retention(RetentionPolicy.RUNTIME)`: giữ annotation ở runtime để Spring có thể đọc bằng reflection và cơ chế merged annotation.
- `@Documented`: đưa annotation vào tài liệu JavaDoc của phần tử được đánh dấu.
- `@Inherited`: cho phép annotation được kế thừa qua superclass theo quy tắc của Java khi annotation được đặt trên class.

Không phải annotation nào cũng cần `@Inherited`. Chỉ thêm khi dự án muốn các test class con nhận quy ước từ lớp cha. `@Inherited` không làm annotation tự động được kế thừa qua interface hoặc qua mọi vị trí method.

Với annotation dành riêng cho test class, `ElementType.TYPE` thường là đủ. Nếu muốn dùng annotation trên test method, cần kiểm tra các annotation nền có hỗ trợ `ElementType.METHOD` hay không và xác định rõ ý nghĩa khi áp dụng ở method. Không mở rộng `@Target` chỉ để annotation có vẻ linh hoạt hơn.

## 5. Tổ hợp các annotation Spring Testing có sẵn

Ví dụ đơn giản kết hợp Spring context và profile:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
@SpringJUnitConfig
@ActiveProfiles("test")
public @interface SpringComponentTest {
}
```

Test class:

```java
@SpringComponentTest
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void calculatesPrice() {
        // ...
    }
}
```

`@SpringJUnitConfig` tích hợp SpringExtension và ContextConfiguration. `@ActiveProfiles("test")` chọn profile dành cho test. Test class có thể khai báo cấu hình bằng các cơ chế cấu hình context mà Spring hỗ trợ, chẳng hạn lớp `@Configuration` lồng bên trong hoặc cấu hình được cung cấp qua annotation tổ hợp có thuộc tính.

Khi dùng annotation tổ hợp, hãy nhớ rằng các annotation nền vẫn giữ nguyên quy tắc của chúng. Ví dụ, `@ActiveProfiles` quyết định profile cho test context; nó không tự tạo bean. `@SpringJUnitConfig` cung cấp tích hợp JUnit và cấu hình context; nó không tự quyết định mọi dependency của ứng dụng.

## 6. Dùng @AliasFor để mở thuộc tính cần tùy chỉnh

Một annotation tổ hợp có thể cần cho phép test class thay đổi một phần cấu hình. Spring cung cấp `@AliasFor` để ánh xạ thuộc tính của annotation tổ hợp tới thuộc tính của meta-annotation.

Ví dụ, annotation `@DatabaseSpringTest` có thể cho phép mỗi test chỉ định lớp cấu hình và danh sách profile:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.core.annotation.AliasFor;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.transaction.annotation.Transactional;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ExtendWith(SpringExtension.class)
@ContextConfiguration
@ActiveProfiles("test")
@Transactional
public @interface DatabaseSpringTest {

    @AliasFor(
            annotation = ContextConfiguration.class,
            attribute = "classes"
    )
    Class<?>[] classes() default {};

    @AliasFor(
            annotation = ActiveProfiles.class,
            attribute = "profiles"
    )
    String[] profiles() default {};
}
```

Ở đây:

- `classes` của annotation tổ hợp ánh xạ tới `@ContextConfiguration(classes = ...)`.
- `profiles` ánh xạ tới `@ActiveProfiles(profiles = ...)`.
- Giá trị mặc định của thuộc tính tổ hợp được giữ phù hợp với mặc định của thuộc tính meta-annotation. Profile `test` được khai báo sẵn trên `@ActiveProfiles("test")`; khi test truyền `profiles`, giá trị đó được thay bằng danh sách được chỉ định.

Test có thể dùng:

```java
@DatabaseSpringTest(
        classes = OrderTestConfiguration.class,
        profiles = {"test", "database"}
)
class OrderRepositoryTest {
    // ...
}
```

Cách viết này giúp test class thay đổi cấu hình cần thiết ngay tại annotation sử dụng. Người đọc cũng thấy rõ lớp cấu hình và profile mà test yêu cầu.

Khi dùng `@AliasFor`, tên annotation đích và tên thuộc tính phải chính xác. Kiểu dữ liệu phải tương thích với thuộc tính được ánh xạ. Các alias trong cùng annotation nếu được khai báo như một cặp tương đương cũng cần được cấu hình nhất quán theo quy tắc của Spring.

Không nên thêm thuộc tính chỉ để phơi bày toàn bộ API của mọi annotation nền. Chỉ đưa ra những tùy chọn mà người dùng annotation thực sự cần thay đổi. Nếu mỗi test phải cấu hình hàng loạt thuộc tính, annotation tổ hợp có thể đang gom quá nhiều trách nhiệm.

## 7. Phân biệt giá trị mặc định và giá trị được ghi đè

Một annotation tổ hợp thường có một cấu hình mặc định thể hiện quy ước chung. Ví dụ, mọi test repository đều dùng profile `test`. Một số test có thể cần thêm profile hoặc thay lớp cấu hình.

Hãy phân biệt:

- **Giá trị mặc định:** quy ước áp dụng khi test không truyền thuộc tính.
- **Giá trị được ghi đè:** tùy chọn test class chủ động khai báo để thay đổi quy ước.
- **Giá trị bắt buộc:** thông tin mà annotation không thể tự xác định và người dùng phải cung cấp.

Nếu một thuộc tính luôn phải có, cân nhắc yêu cầu người dùng truyền nó thay vì đưa một mặc định giả có thể dẫn đến context sai. Ngược lại, nếu phần lớn test dùng cùng một profile, đặt mặc định phù hợp sẽ giảm lặp lại.

Không nên tạo nhiều thuộc tính boolean để bật tắt các phần cấu hình ẩn:

```java
// Khó đọc khi sử dụng
@ProjectTest(
        database = true,
        web = false,
        transaction = true,
        messaging = false
)
class SomeTest {
}
```

Lời gọi như vậy không thể hiện rõ loại test và rất dễ tạo ra tổ hợp không hợp lệ. Thường nên dùng các annotation riêng theo mục đích, hoặc một enum có tên rõ nghĩa nếu thực sự có một lựa chọn loại trừ nhau.

## 8. Tránh kết hợp các cấu hình kiểm thử xung đột

Không phải annotation nào cũng có thể kết hợp tùy ý. Một annotation tổ hợp có thể vô tình mang các metadata không tương thích.

Ví dụ, `@WebMvcTest` và `@SpringBootTest` biểu thị hai cách bootstrap context khác nhau: một bên tạo MVC slice, bên kia thường nạp application context theo phạm vi rộng hơn. Gom cả hai vào cùng annotation có thể tạo cấu hình mơ hồ hoặc khiến test bootstrap thất bại.

Tương tự, cần thận trọng khi tổ hợp:

- Nhiều annotation bootstrap context khác nhau.
- Nhiều khai báo `@ContextConfiguration` không có quy tắc hợp nhất rõ ràng.
- Các profile mặc định đối lập nhau.
- `@Transactional` với cấu hình transaction manager không phù hợp.
- `@DirtiesContext` trên mọi test class dù chỉ một số test làm thay đổi context.
- Các annotation thay đổi property theo cách làm người đọc khó xác định giá trị cuối cùng.

Một annotation tổ hợp nên đại diện cho một cấu hình có thể giải thích được. Nếu hai loại test có bootstrap hoặc vòng đời khác nhau, hãy giữ chúng thành hai annotation riêng.

## 9. Không biến annotation tổ hợp thành một “gói mọi thứ”

Một annotation dùng lại quá lớn có thể chứa Spring Boot bootstrap, MVC slice, database, security, mock bean, transaction, profile, property override, SQL script và context cleanup. Khi đó, chỉ nhìn tên annotation không đủ để biết test đang phụ thuộc vào những gì.

Hãy cân nhắc tách theo mục đích:

```text
@SpringComponentTest
    └── SpringExtension + context + profile test

@TransactionalRepositoryTest
    └── Spring context + profile database + transaction

@MvcSliceTest
    └── MVC slice + cấu hình MockMvc

@FullApplicationTest
    └── Full Spring Boot application context
```

Mỗi annotation có thể chia sẻ một số meta-annotation nền, nhưng tên và phạm vi phải cho thấy mục tiêu chính. Không cần tạo một hệ thống phân cấp annotation phức tạp nếu vài annotation độc lập đã đủ diễn đạt quy ước.

Nếu một annotation chỉ có một nhóm người dùng nhỏ hoặc chỉ xuất hiện ở một test, có thể giữ các annotation nền trực tiếp trên test class. Điều đó giúp người đọc không phải đi tìm định nghĩa ở nơi khác.

## 10. Đặt annotation ở nơi dễ tìm

Vị trí lưu annotation ảnh hưởng trực tiếp đến khả năng khám phá. Hãy đặt annotation tổ hợp trong package có tên dễ hiểu và nhất quán với cấu trúc dự án.

Ví dụ:

```text
src/test/java/
└── com/example/project/
    ├── testing/
    │   ├── annotation/
    │   │   ├── DatabaseSpringTest.java
    │   │   ├── MvcSliceTest.java
    │   │   └── FullApplicationTest.java
    │   └── config/
    │       ├── TestDatabaseConfiguration.java
    │       └── StubPaymentConfiguration.java
    └── order/
        └── OrderRepositoryTest.java
```

Với annotation chỉ dùng trong một module, đặt nó trong source set test của module đó thường hợp lý. Nếu nhiều module cần dùng chung, có thể chuyển annotation và cấu hình hỗ trợ vào một test fixtures module hoặc test support library mà các module có thể khai báo dependency.

Tránh đặt annotation test dùng chung trong package production nếu nó chỉ phục vụ kiểm thử. Cũng tránh đặt mọi thứ trong package `util` hoặc `common` mà không có phân nhóm. Người mới vào dự án nên có thể đoán được vị trí annotation từ tên package.

## 11. Viết JavaDoc để người dùng biết annotation bao gồm gì

Tên annotation tốt vẫn cần tài liệu ngắn giải thích các hành vi quan trọng. JavaDoc nên trả lời:

- Annotation này dành cho loại test nào?
- Nó kích hoạt profile nào?
- Nó dùng bootstrap hoặc test context nào?
- Có transaction hay không?
- Thuộc tính nào có thể tùy chỉnh?
- Có lưu ý nào về cleanup hoặc context lifecycle?

Ví dụ:

```java
/**
 * Configures a Spring repository integration test.
 *
 * <p>Uses the Spring TestContext Framework, activates the {@code test}
 * profile by default, and runs test methods with Spring-managed
 * transactions.
 *
 * <p>Provide {@link #classes()} when the test needs explicit
 * configuration classes.
 */
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
// Các meta-annotation...
public @interface DatabaseSpringTest {

    // Các thuộc tính...
}
```

JavaDoc giúp người đọc hiểu annotation ngay trong IDE khi hover hoặc mở khai báo. Nên ghi những hành vi thực tế của annotation, không mô tả chung chung như “annotation dùng cho test”.

Khi annotation có thuộc tính alias, hãy giải thích rõ thuộc tính đó điều khiển meta-annotation nào và giá trị mặc định ra sao. Nếu profile có thể bị ghi đè, người dùng cần biết cách khai báo để tránh hiểu nhầm.

## 12. Giúp người đọc truy tìm cấu hình nền

Một annotation tổ hợp có thể làm test class ngắn hơn, nhưng người đọc vẫn cần lần được cấu hình thực tế. Hãy giữ một số quy ước giúp việc tìm kiếm dễ dàng:

**Tên phản ánh phạm vi.** Dùng `@MvcSliceTest` hoặc `@RepositoryIntegrationTest` thay vì `@ProjectTest`.

**Đặt trong package có chủ đích.** Ví dụ `testing.annotation` hoặc `testsupport.annotation`.

**Dùng tên thuộc tính tường minh.** `classes = ...` và `profiles = ...` dễ hiểu hơn một thuộc tính `value` không rõ đại diện cho điều gì.

**Ghi rõ meta-annotation quan trọng trong JavaDoc.** Người đọc biết cần tìm profile, transaction hay context configuration.

**Giữ cấu trúc annotation nông.** Nếu một annotation trỏ tới annotation khác, rồi annotation đó tiếp tục tổ hợp nhiều tầng, hãy kiểm tra xem có thể làm phẳng cấu trúc để người đọc lần theo nhanh hơn không.

**Dùng IDE và tìm kiếm mã nguồn.** Tìm khai báo annotation, nơi sử dụng và các meta-annotation được đặt trên nó. Đặt tên file trùng tên annotation để tìm kiếm trực tiếp.

Spring có cơ chế merged annotation để tìm và tổng hợp metadata qua các meta-annotation và hierarchy. Tuy nhiên, khả năng Spring đọc được cấu hình không đồng nghĩa người phát triển dễ khám phá nó. Tên, package, JavaDoc và cấu trúc đơn giản vẫn rất quan trọng.

## 13. Kế thừa annotation tổ hợp giữa các test class

Nếu annotation tổ hợp được dùng trên base test class, cần hiểu quy tắc kế thừa. `@Inherited` của Java áp dụng cho annotation trên class và chỉ truyền qua chuỗi superclass. Nó không truyền qua interface.

Ví dụ:

```java
@DatabaseSpringTest
abstract class BaseRepositoryTest {
}

class CustomerRepositoryTest extends BaseRepositoryTest {
    // Nhận quy ước từ lớp cha theo cơ chế kế thừa annotation
}
```

Cách này có thể giảm lặp lại khi nhiều test class cùng chia sẻ cấu hình. Tuy nhiên, cần cân nhắc liệu mọi lớp con có thực sự nên nhận cùng profile, transaction và cấu hình context hay không.

Nếu một lớp con cần profile khác hoặc bootstrap khác, hãy dùng cơ chế override được annotation hỗ trợ hoặc tạo một annotation riêng. Không nên dựa vào một chuỗi kế thừa sâu mà người đọc phải mở nhiều lớp mới hiểu test context được cấu hình thế nào.

Cũng cần phân biệt kế thừa annotation với kế thừa trạng thái bean. Annotation mô tả metadata; Spring TestContext Framework sử dụng metadata đó để tạo hoặc tái sử dụng context. Bean và context có vòng đời riêng.

## 14. Kiểm tra annotation tổ hợp bằng một test thực tế

Một annotation tổ hợp cần được kiểm tra trong đúng ngữ cảnh sử dụng. Chỉ kiểm tra rằng annotation có mặt trên class chưa đủ để chứng minh Spring đã nạp đúng profile, cấu hình hoặc transaction.

Ví dụ, có thể tạo một test class nhỏ sử dụng annotation và xác nhận một bean chỉ được đăng ký theo profile mong muốn:

```java
@Configuration
class OrderTestConfiguration {

    @Bean
    @Profile("test")
    TestMarker testMarker() {
        return new TestMarker("test-profile");
    }
}
```

```java
@DatabaseSpringTest(
        classes = OrderTestConfiguration.class,
        profiles = {"test"}
)
class DatabaseSpringTestAnnotationTest {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void loadsBeanFromExpectedProfile() {
        TestMarker marker = applicationContext.getBean(TestMarker.class);

        assertEquals("test-profile", marker.value());
    }
}
```

Test này sử dụng annotation tổ hợp như một người dùng thực tế. Nếu alias `classes` hoặc `profiles` bị cấu hình sai, Spring context có thể không khởi tạo như dự kiến hoặc bean không xuất hiện.

Nếu annotation bao gồm transaction, có thể kiểm tra transaction đang hoạt động bằng API của Spring Test hoặc xác nhận hành vi rollback qua dữ liệu kiểm thử phù hợp. Nếu annotation chỉ kết hợp metadata, hãy xác nhận các hành vi quan trọng mà metadata đó phải tạo ra.

Không cần tạo một bộ test lớn cho mọi annotation. Một test tích hợp nhỏ ở test support module có thể bảo vệ hợp đồng của annotation khi nó được sử dụng rộng rãi.

## 15. Những dấu hiệu annotation tổ hợp đang quá phức tạp

| Dấu hiệu | Tác động | Cách đơn giản hóa |
|---|---|---|
| Tên annotation chung chung | Người đọc không biết phạm vi test | Đặt tên theo loại test hoặc cấu hình chính |
| Quá nhiều meta-annotation | Khó hiểu context cuối cùng | Chỉ giữ các hành vi dùng chung thực sự |
| Nhiều boolean để bật/tắt tính năng | Tạo nhiều tổ hợp khó dự đoán | Tách annotation theo mục đích hoặc dùng enum có nghĩa |
| Nhiều alias không cần thiết | API của annotation khó sử dụng | Chỉ expose thuộc tính cần tùy chỉnh |
| Nhiều tầng annotation tổ hợp | Khó truy tìm nguồn metadata | Giảm tầng hoặc ghi rõ quan hệ trong JavaDoc |
| Kết hợp bootstrap không tương thích | Test context lỗi hoặc mơ hồ | Tạo annotation riêng cho từng loại bootstrap |
| Mặc định ẩn và không được tài liệu hóa | Test khó đọc và debug | Ghi rõ profile, transaction, property và phạm vi |
| Đặt annotation ở package không rõ nghĩa | Người dùng khó tìm | Tổ chức trong package testing/annotation |
| Một annotation dùng cho nhiều loại test khác nhau | Tên không còn phản ánh hành vi | Tách thành các annotation có mục đích riêng |

Một dấu hiệu khác là khi người dùng phải đọc toàn bộ mã nguồn annotation mới biết test có dùng database thật, mock service hay transaction. Khi đó, tên hoặc JavaDoc chưa thể hiện đủ hợp đồng của annotation.

## 16. Quy trình thiết kế annotation tổ hợp

Có thể xây dựng annotation dùng lại theo các bước sau:

1. **Xác định nhóm test lặp lại:** tìm các test class thực sự chia sẻ cùng bootstrap và cấu hình.
2. **Viết rõ mục đích:** mô tả loại test và những hành vi mà annotation cung cấp.
3. **Chọn meta-annotation cần thiết:** chỉ thêm những annotation có liên quan trực tiếp.
4. **Chọn giá trị mặc định:** dùng giá trị ổn định và phù hợp với phần lớn trường hợp.
5. **Expose thuộc tính cần tùy chỉnh:** dùng `@AliasFor` khi người dùng cần điều khiển thuộc tính của meta-annotation.
6. **Đặt tên và package dễ tìm:** tên phản ánh phạm vi, file cùng tên annotation.
7. **Viết JavaDoc:** ghi profile, context, transaction và các thuộc tính quan trọng.
8. **Dùng thử trên test class:** xác nhận Spring tạo context và áp dụng metadata như dự kiến.
9. **Giữ quy ước được cập nhật:** khi thay đổi meta-annotation, xem lại các test class đang sử dụng annotation tổ hợp.

Nếu nhóm test chỉ có một cấu hình đơn giản, giữ annotation nền trực tiếp có thể dễ hiểu hơn. Khi một nhóm cấu hình được dùng lặp lại và có tên miền rõ ràng, annotation tổ hợp sẽ giúp test class ngắn gọn và nhất quán.

## 17. Ví dụ tổ chức annotation dùng lại trong dự án

Một dự án có thể tổ chức một số annotation theo phạm vi:

```text
com.example.project.testing.annotation
    |
    +-- @SpringComponentTest
    |      SpringExtension + context cấu hình cho component test
    |
    +-- @TransactionalRepositoryTest
    |      Context + profile database + transaction
    |
    +-- @MvcSliceTest
    |      MVC slice + MockMvc
    |
    +-- @FullApplicationTest
           Full Spring Boot context
```

Mỗi annotation có thể có cấu hình nền riêng và chỉ cung cấp các thuộc tính cần thiết. Ví dụ, `@MvcSliceTest` có thể expose controller class hoặc các cấu hình MVC cần thiết; `@TransactionalRepositoryTest` có thể expose cấu hình database và profile.

Khi dự án lớn lên, package annotation có thể được đưa vào một module test support dùng chung. Module này nên có tên và tài liệu cho biết nó phục vụ test của các module nào, đồng thời không kéo các dependency test vào artifact production.

Giữ annotation tổ hợp đơn giản giúp người viết test thể hiện đúng ý định ngay trên class. Giữ tên, package, thuộc tính và JavaDoc dễ truy tìm giúp người đọc lần được các meta-annotation và cấu hình Spring đứng phía sau. Khi hai yêu cầu này được đáp ứng, annotation dùng lại trở thành một quy ước kiểm thử rõ ràng, dễ bảo trì và dễ mở rộng theo nhu cầu thực tế của dự án.

