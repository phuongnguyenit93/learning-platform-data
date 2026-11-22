# Annotation, meta-annotation và vai trò của reflection trong Spring Boot

Khi đọc một ứng dụng Spring Boot, ta thường gặp những dòng như `@SpringBootApplication`, `@Service`, `@RestController`, `@GetMapping` hoặc `@Transactional`. Chúng ngắn gọn, nhưng đằng sau là cả một cơ chế đọc metadata, đăng ký đối tượng và thực thi hành vi của framework. Muốn hiểu Spring Boot hoạt động thế nào, trước hết cần phân biệt **annotation**, **meta-annotation** và **reflection**.

## 1. Annotation là gì?

**Annotation** là metadata được gắn vào một thành phần của chương trình Java: lớp, interface, phương thức, constructor, trường, tham số, kiểu sử dụng, v.v. Annotation mô tả thông tin để compiler, công cụ hoặc framework đọc và xử lý.

Ví dụ:

```java
@Override
public String toString() {
    return "Product";
}
```

`@Override` cho compiler biết phương thức dự định ghi đè một phương thức của lớp cha hoặc interface. Compiler có thể báo lỗi nếu không có phương thức phù hợp.

Trong Spring:

```java
@Service
public class ProductService {
    public String findName() {
        return "Keyboard";
    }
}
```

`@Service` đánh dấu lớp có vai trò là một service. Khi lớp nằm trong phạm vi quét phù hợp, Spring có thể nhận diện nó như một bean và quản lý vòng đời của đối tượng tương ứng.

**Điểm mấu chốt:** bản thân annotation không tự chạy logic. Việc annotation có tác dụng gì phụ thuộc vào bên đọc và xử lý nó. `@Override` chủ yếu được compiler kiểm tra; `@Service` được Spring xử lý; một annotation tự định nghĩa sẽ không làm gì nếu không có mã sử dụng nó.

### 1.1. Tự định nghĩa annotation

Java sử dụng cú pháp `@interface` để khai báo một annotation type:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface AuditAction {
    String value();
    int priority() default 1;
}
```

Áp dụng annotation:

```java
public class PaymentService {

    @AuditAction(value = "CREATE_PAYMENT", priority = 2)
    public void createPayment() {
        // Xử lý thanh toán
    }

    @AuditAction("CANCEL_PAYMENT")
    public void cancelPayment() {
        // Sử dụng priority mặc định là 1
    }
}
```

Các khai báo `value()` và `priority()` ở đây là **annotation elements** (thuộc tính annotation), không phải những phương thức nghiệp vụ được gọi để thực thi thanh toán. Thuộc tính không có `default` phải được cung cấp. Khi annotation chỉ có một thuộc tính cần khai báo tên `value`, ta có thể viết `@AuditAction("CANCEL_PAYMENT")` thay cho `@AuditAction(value = "CANCEL_PAYMENT")`.

Java giới hạn kiểu thuộc tính annotation: primitive, `String`, `Class`, enum, annotation và mảng của các kiểu hợp lệ đó. Giá trị được truyền phải là biểu thức hằng phù hợp tại thời điểm biên dịch; không thể truyền trực tiếp một đối tượng service hoặc giá trị biến đổi tùy ý khi chạy.

## 2. Meta-annotation: annotation dùng để mô tả annotation

**Meta-annotation** là annotation được đặt trên phần khai báo của **một annotation khác**. Java cung cấp những meta-annotation chuẩn trong `java.lang.annotation`:

| Meta-annotation | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `@Target` | Giới hạn nơi được sử dụng annotation | `ElementType.TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `CONSTRUCTOR`, `ANNOTATION_TYPE`, `TYPE_USE` |
| `@Retention` | Quy định annotation được giữ lại đến giai đoạn nào | `SOURCE`, `CLASS`, `RUNTIME` |
| `@Documented` | Cho phép annotation xuất hiện trong Javadoc của thành phần được gắn | `@Documented` |
| `@Inherited` | Cho phép lớp con kế thừa một annotation ở cấp lớp theo quy tắc Java | `@Inherited` |
| `@Repeatable` | Cho phép lặp cùng loại annotation trên một thành phần | `@Repeatable(Tags.class)` |

### 2.1. `@Retention`: thời điểm metadata còn tồn tại

`@Retention` đặc biệt quan trọng khi làm việc với reflection:

| Chính sách | Có trong mã nguồn | Được lưu vào `.class` | Đọc được qua Java reflection lúc runtime |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Có | Không | Không |
| `RetentionPolicy.CLASS` | Có | Có | Không, theo API reflection thông thường |
| `RetentionPolicy.RUNTIME` | Có | Có | Có |

Ví dụ, với một annotation được xử lý bởi Java reflection khi ứng dụng đang chạy, thường cần khai báo:

```java
@Retention(RetentionPolicy.RUNTIME)
```

Nếu không ghi `@Retention`, mặc định là `CLASS`. Điều đó **không** đồng nghĩa mọi thư viện đều không nhìn thấy annotation: công cụ đọc bytecode có thể phân tích metadata trong file `.class` ngay cả khi Java reflection không trả về annotation đó.

### 2.2. `@Target`: annotation có thể đặt ở đâu?

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface ExampleMarker {
}
```

Annotation này có thể gắn lên khai báo lớp và phương thức. Compiler sẽ từ chối việc gắn nó trực tiếp vào một trường nếu `FIELD` không thuộc danh sách target. `ElementType.TYPE` áp dụng cho khai báo kiểu; `ElementType.TYPE_USE` áp dụng cho nơi *sử dụng* một kiểu, chẳng hạn trong một kiểu generic.

### 2.3. `@Inherited` và `@Repeatable` có giới hạn riêng

- `@Inherited` chỉ áp dụng cho cơ chế kế thừa annotation từ **lớp cha sang lớp con** khi truy vấn annotation ở cấp lớp theo quy tắc Java. Nó không tự làm annotation trên phương thức hoặc interface được kế thừa theo cách tương tự.
- `@Repeatable` yêu cầu khai báo một annotation chứa (container). Khi cần lấy đầy đủ các lần xuất hiện, dùng `getAnnotationsByType(...)` thay cho chỉ `getAnnotation(...)`.
- Một framework như Spring có thể cung cấp quy tắc tìm kiếm annotation qua quan hệ meta-annotation, interface và lớp cha rộng hơn quy tắc Java reflection cơ bản. Cần phân biệt quy tắc của Java với quy tắc của Spring.

## 3. Reflection: đọc cấu trúc và annotation khi chạy

**Reflection** là khả năng chương trình Java kiểm tra hoặc tương tác với thông tin về lớp, constructor, trường, phương thức và annotation khi runtime. Các API chủ yếu nằm trong `java.lang.Class` và `java.lang.reflect`.

Ví dụ sau có thể đặt trong một file `AnnotationReflectionDemo.java` và chạy bằng Java thông thường, không cần Spring Boot:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface AuditAction {
    String value();
    int priority() default 1;
}

class PaymentService {
    @AuditAction(value = "CREATE_PAYMENT", priority = 2)
    public void createPayment() {
    }
}

public class AnnotationReflectionDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Class<PaymentService> type = PaymentService.class;
        Method method = type.getDeclaredMethod("createPayment");

        AuditAction metadata = method.getAnnotation(AuditAction.class);
        if (metadata != null) {
            System.out.println("Action: " + metadata.value());
            System.out.println("Priority: " + metadata.priority());
        }
    }
}
```

Kết quả:

```text
Action: CREATE_PAYMENT
Priority: 2
```

Luồng xử lý là:

1. `PaymentService.class` cung cấp đối tượng `Class` mô tả kiểu `PaymentService`.
2. `getDeclaredMethod("createPayment")` tìm metadata của phương thức được khai báo trong lớp.
3. `getAnnotation(AuditAction.class)` đọc annotation có thể nhìn thấy ở runtime.
4. `value()` và `priority()` lấy các giá trị đã khai báo trong annotation.

Nếu thay `@Retention(RetentionPolicy.RUNTIME)` bằng `CLASS` hoặc `SOURCE`, lời gọi `getAnnotation(...)` ở ví dụ trên sẽ trả về `null`. Reflection đọc metadata, nhưng **không tự động ghi log hay audit**; muốn thực hiện hành vi audit, mã ứng dụng hoặc framework phải triển khai hành vi đó.

### 3.1. Những API reflection thường gặp

| API | Công dụng |
| --- | --- |
| `SomeClass.class` / `object.getClass()` | Lấy đối tượng `Class` |
| `getDeclaredMethods()` | Lấy các phương thức khai báo trực tiếp trong lớp, bất kể mức truy cập |
| `getMethods()` | Lấy các phương thức `public`, gồm cả các phương thức public được kế thừa |
| `getDeclaredMethod(name, parameterTypes...)` | Tìm phương thức khai báo trực tiếp theo tên và kiểu tham số |
| `getDeclaredFields()` / `getDeclaredConstructors()` | Xem các trường / constructor được khai báo |
| `getAnnotation(MyAnnotation.class)` | Lấy annotation theo quy tắc của `AnnotatedElement` |
| `getDeclaredAnnotation(MyAnnotation.class)` | Lấy annotation được khai báo trực tiếp trên thành phần |
| `isAnnotationPresent(MyAnnotation.class)` | Kiểm tra annotation có hiện diện theo quy tắc API |
| `getAnnotationsByType(MyAnnotation.class)` | Lấy các annotation cùng loại, kể cả dạng repeatable |
| `method.getParameters()` | Xem tham số của phương thức và annotation trên chúng |

Reflection còn cho phép khởi tạo đối tượng, gọi phương thức và đọc/ghi trường trong những điều kiện truy cập cho phép. Tuy nhiên, không phải lúc nào cũng nên truy cập thành phần `private`: cơ chế module của Java và cấu hình runtime có thể giới hạn quyền truy cập phản chiếu.

## 4. Meta-annotation trong Spring: kết hợp nhiều ý nghĩa

Spring dùng annotation để biểu đạt cấu hình và vai trò thành phần. Một annotation có thể được **gắn lên một annotation khác** để tạo ra annotation kết hợp (*composed annotation*).

Ví dụ về quan hệ giữa một số annotation trong Spring:

```text
@Component
    ↑
 @Service

@SpringBootApplication
    ├── @SpringBootConfiguration
    ├── @EnableAutoConfiguration
    └── @ComponentScan
```

`@Service` là một dạng chuyên biệt của `@Component`: nó giúp diễn đạt ý nghĩa tầng nghiệp vụ và vẫn được Spring nhận diện để đăng ký bean. `@Repository` và `@Controller` cũng là những stereotype liên quan đến `@Component`; ngoài việc đánh dấu vai trò, một số annotation còn có cơ chế xử lý riêng.

`@SpringBootApplication` kết hợp các chức năng trọng tâm:

- `@SpringBootConfiguration`: xác định lớp cấu hình ứng dụng Spring Boot (dựa trên `@Configuration`).
- `@EnableAutoConfiguration`: kích hoạt cơ chế auto-configuration dựa trên classpath, cấu hình và các điều kiện.
- `@ComponentScan`: quét và phát hiện những thành phần Spring trong phạm vi package liên quan.

Đây là lý do một annotation trên lớp `main` có thể kích hoạt nhiều hoạt động của framework. Cần lưu ý: hiệu quả đó đến từ **bộ xử lý cấu hình và hạ tầng Spring**, không đến chỉ từ việc annotation được đặt trên lớp.

### 4.1. Tạo stereotype riêng

Giả sử dự án muốn đặt tên rõ ràng cho service chứa nghiệp vụ ứng dụng:

```java
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Service;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
public @interface BusinessService {
    @AliasFor(annotation = Service.class, attribute = "value")
    String value() default "";
}
```

Sử dụng ở lớp nghiệp vụ:

```java
@BusinessService
public class PricingService {
    public int calculateTotal(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

Nếu `PricingService` nằm trong vùng component scan, Spring có thể đăng ký nó thành bean vì `@BusinessService` mang meta-annotation `@Service`, mà `@Service` lại mang meta-annotation `@Component`. Thuộc tính `value` với `@AliasFor` cho phép chuyển tên bean tùy chọn qua annotation kết hợp.

Về mặt tra cứu, có một khác biệt đáng nhớ:

```java
// Truy vấn Java reflection cơ bản: chỉ kiểm tra @Component theo
// quy tắc annotation trực tiếp/kế thừa của Java, không đi theo chuỗi meta-annotation.
boolean byJava = PricingService.class.isAnnotationPresent(
        org.springframework.stereotype.Component.class
); // false

// Spring hỗ trợ tìm qua chuỗi meta-annotation.
boolean bySpring =
        org.springframework.core.annotation.AnnotatedElementUtils.hasAnnotation(
                PricingService.class,
                org.springframework.stereotype.Component.class
        ); // true
```

API `AnnotatedElementUtils` và `MergedAnnotations` giúp Spring tìm annotation đã kết hợp và xử lý quan hệ alias. Khi làm việc với annotation kết hợp của Spring, không nên giả định `Class.getAnnotation(...)` sẽ tự tìm đến mọi tầng meta-annotation.

## 5. Reflection góp phần gì vào cơ chế Spring Boot?

Xét một ứng dụng có controller và service:

```java
// StoreApplication.java
@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

```java
// DiscountService.java
@Service
public class DiscountService {
    public BigDecimal apply(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.90"));
    }
}
```

```java
// PriceController.java
@RestController
@RequestMapping("/prices")
public class PriceController {
    private final DiscountService discountService;

    public PriceController(DiscountService discountService) {
        this.discountService = discountService;
    }

    @GetMapping("/discount")
    public BigDecimal discount(@RequestParam BigDecimal amount) {
        return discountService.apply(amount);
    }
}
```

Các đoạn mã trên giả định những lớp nằm trong package được Spring Boot quét, có import tương ứng từ `org.springframework.boot`, `org.springframework.stereotype`, `org.springframework.web.bind.annotation` và `java.math.BigDecimal`. Trong ứng dụng Spring Boot có web starter phù hợp, request `GET /prices/discount?amount=100` sẽ được định tuyến tới phương thức `discount`, chuyển tham số `amount` thành `BigDecimal` và trả về giá trị sau giảm giá.

Về mặt khái niệm, Spring phối hợp nhiều cơ chế:

1. **Khám phá thành phần:** quét phạm vi package và nhận diện lớp được đánh dấu bằng các stereotype như `@Component`, `@Service`, `@RestController`, kể cả qua meta-annotation.
2. **Đăng ký bean definition:** lưu thông tin cần thiết để tạo và quản lý bean trong `ApplicationContext`.
3. **Khởi tạo và dependency injection:** chọn constructor phù hợp và cung cấp phụ thuộc. Trong ví dụ, `PriceController` có một constructor nên không cần thêm `@Autowired`.
4. **Đăng ký endpoint:** Spring MVC phân tích metadata của `@RequestMapping`, `@GetMapping`, `@RequestParam` để thiết lập ánh xạ HTTP và chuyển đổi tham số.
5. **Gọi xử lý nghiệp vụ:** khi có request, framework gọi phương thức phù hợp, xử lý kết quả và tạo HTTP response.

Java reflection đóng vai trò đáng kể khi Spring xem cấu trúc lớp, constructor, phương thức và annotation, rồi tạo/gọi đối tượng. Tuy nhiên, **Spring không dựa duy nhất vào reflection**: framework còn đọc metadata từ bytecode (chẳng hạn khi component scanning), dùng registry, bean factory, các bộ xử lý cấu hình và những cơ chế khác. Nhận diện một annotation trong file `.class` có thể diễn ra trước khi lớp được khởi tạo.

### 5.1. Annotation và dependency injection

```java
@Service
public class InvoiceService {
    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Nếu `TaxCalculator` là bean phù hợp trong container, Spring có thể truyền nó vào constructor. Metadata của kiểu constructor cho biết dependency cần thiết; quy trình chọn và resolve bean do IoC container đảm nhiệm. Với một constructor, Spring thường tự động dùng constructor đó mà không yêu cầu `@Autowired`. Cách tiêm qua constructor giúp biểu đạt phụ thuộc bắt buộc và thuận lợi cho việc kiểm thử.

### 5.2. Annotation liên quan đến AOP và proxy

```java
@Service
public class OrderService {
    @Transactional
    public void placeOrder() {
        // Các thao tác dữ liệu cần thuộc cùng transaction
    }
}
```

`@Transactional` là metadata báo cho hạ tầng transaction của Spring cách áp dụng giao dịch; việc bắt đầu, commit hay rollback giao dịch do transaction interceptor và transaction manager thực hiện. Trong cấu hình AOP dựa trên proxy thường gặp, lời gọi cần đi **qua Spring proxy** để interceptor được kích hoạt.

Một lỗi hay gặp là một phương thức trong cùng đối tượng gọi `this.placeOrder()` với kỳ vọng transaction advice sẽ chạy. Lời gọi nội bộ này thường bỏ qua proxy, nên annotation có thể không tạo ra hiệu ứng mong đợi. Đây là ví dụ rõ ràng cho việc **annotation chỉ là mô tả; hành vi phụ thuộc vào cơ chế thực thi của Spring**.

### 5.3. Điều kiện và cấu hình

Các annotation như `@Configuration`, `@Bean`, `@Profile`, `@ConditionalOnProperty` có thể tham gia quyết định bean nào được đăng ký, trong điều kiện nào. Ví dụ:

```java
@Configuration
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "feature",
        name = "reporting",
        havingValue = "true"
    )
    public ReportGenerator reportGenerator() {
        return new ReportGenerator();
    }
}
```

Khi điều kiện cấu hình thỏa mãn và các kiểu cần thiết tồn tại trong ứng dụng, Spring Boot có thể đăng ký bean `ReportGenerator`. Phương thức này không được gọi chỉ vì có `@Bean`; nó được Spring gọi và quản lý trong quá trình xử lý cấu hình tương ứng.

## 6. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Gắn annotation là code tự chạy.” | Cần compiler, framework hoặc mã ứng dụng xử lý annotation thì mới phát sinh hiệu ứng. |
| “Annotation nào cũng đọc được bằng reflection.” | Java reflection thông thường chỉ nhìn thấy annotation có retention `RUNTIME`. |
| “`@Service` và `@Component` là hai cơ chế đăng ký bean độc lập.” | `@Service` là một stereotype được xây trên `@Component`. |
| “Java `getAnnotation()` tự tìm hết meta-annotation.” | Java reflection và cơ chế merged annotation của Spring có quy tắc khác nhau. |
| “Spring Boot chỉ sử dụng reflection để quét package.” | Spring có thể đọc class metadata từ bytecode, sau đó mới tải hoặc khởi tạo lớp khi cần. |
| “`@Transactional` luôn có hiệu lực với mọi lời gọi.” | Với Spring AOP dùng proxy, đường đi của lời gọi quyết định interceptor có chạy hay không. |
| “Cần đặt `@Autowired` lên mọi constructor.” | Một bean chỉ có một constructor thường không cần thêm `@Autowired`. |

**Về hiệu năng và triển khai:** reflection có tính linh hoạt nhưng không phải lúc nào cũng tối ưu và có thể bị hạn chế trong môi trường native image. Các cơ chế Spring AOT có thể tạo trước một phần cấu hình lúc build và cung cấp reflection hints cho những truy cập động cần thiết. Khi viết thư viện sử dụng reflection sâu, cần cân nhắc khả năng tương thích AOT/native.

## 7. Tự luyện tập

**Bài 1 — Dự đoán kết quả.** Tạo `@Label` với `@Retention(RetentionPolicy.CLASS)`, gắn lên một lớp và gọi `SomeClass.class.getAnnotation(Label.class)`. Kết quả là gì? Nếu đổi sang `RUNTIME` thì sao?

**Bài 2 — Thiết kế annotation.** Tạo `@TrackExecution` chỉ áp dụng cho phương thức, có thuộc tính `String event()` bắt buộc và `boolean enabled()` mặc định `true`. Dùng reflection để tìm và in thuộc tính trên một phương thức đã gắn annotation. Không cần Spring để làm bài này.

**Bài 3 — Giải thích cơ chế Spring.** Vì sao một lớp gắn `@BusinessService` ở mục 4.1 vẫn có thể được Spring đăng ký thành bean dù không gắn trực tiếp `@Component`? Tại sao cùng lúc `isAnnotationPresent(Component.class)` có thể trả về `false`?

**Bài 4 — Xác định giới hạn.** Giải thích vì sao `@Transactional` trên một phương thức có thể không có hiệu lực khi được gọi bằng `this.someMethod()` từ chính bean đó trong mô hình AOP proxy.

Gợi ý đối chiếu: Bài 1 trả về `null` với `CLASS`; có thể đọc được annotation với `RUNTIME`. Bài 2 dùng `@Target(METHOD)`, `@Retention(RUNTIME)` và `Method.getAnnotation(...)`. Bài 3 dựa vào chuỗi meta-annotation và API tìm kiếm của Spring. Bài 4 dựa vào việc lời gọi nội bộ không đi qua proxy.

## 8. Ghi nhớ khi học Spring Boot

**Annotation** diễn đạt metadata và ý định; **meta-annotation** xác định đặc điểm hoặc kết hợp các annotation; **reflection** cho phép chương trình kiểm tra metadata và cấu trúc Java khi chạy. Spring Boot sử dụng cả ba cùng với nhiều thành phần hạ tầng để quét và đăng ký bean, thực hiện dependency injection, tạo HTTP mapping, xử lý transaction và áp dụng cấu hình điều kiện. Khi gặp một annotation mới, hãy tự hỏi ba điều: *Nó được đặt ở đâu? Ai đọc nó? Cơ chế nào biến metadata đó thành hành vi thực tế?*
