# Annotation tổng hợp, alias và custom composed annotation

Trong Spring và Spring Boot, nhiều annotation quen thuộc thực chất được tạo từ những annotation khác. Ví dụ, `@RestController` kết hợp vai trò controller với khả năng trả response body; `@GetMapping` là một dạng chuyên biệt của `@RequestMapping` cho HTTP GET; `@SpringBootApplication` gom các annotation cấu hình ứng dụng thường dùng.

Cách tổ chức đó được gọi là **composed annotation** (annotation tổng hợp). Một annotation có thể mang những annotation khác làm **meta-annotation**, kế thừa ý nghĩa cấu hình của chúng và mở rộng thêm một giao diện ngắn gọn hơn cho ứng dụng.

Khi cần cho người dùng annotation tùy chỉnh ghi đè thuộc tính của meta-annotation, Spring cung cấp **`@AliasFor`**. Alias cho phép một thuộc tính trong annotation tùy chỉnh chuyển giá trị đến thuộc tính của annotation nền, hoặc tạo nhiều tên tương đương cho cùng một thuộc tính.

Bài học tập trung vào ba năng lực:

1. Đọc và hiểu composed annotation có sẵn trong Spring Boot.
2. Thiết kế custom composed annotation để đóng gói một quy ước của ứng dụng.
3. Dùng `@AliasFor` đúng cách để chuyển tiếp hoặc đồng bộ thuộc tính, đồng thời kiểm tra kết quả bằng Spring merged-annotation APIs.

## 1. Annotation và meta-annotation

Java annotation là metadata gắn vào class, method, field, parameter hoặc những phần tử được `@Target` cho phép. Framework có thể đọc metadata này bằng reflection hoặc annotation processing để thay đổi cách đăng ký bean, mapping request, validation, transaction và nhiều hành vi khác.

Ví dụ:

~~~java
@Service
public class OrderService {
}
~~~

`@Service` là một annotation trên class. Nhưng bản thân `@Service` cũng được khai báo bằng một annotation khác:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Component
public @interface Service {
    @AliasFor(annotation = Component.class)
    String value() default "";
}
~~~

Ở đây:

- `@Component` là **meta-annotation** của `@Service`.
- `@Service` là annotation tổng hợp (composed annotation) mang ý nghĩa chuyên biệt hơn.
- Spring component scanning nhận diện `@Service` như một stereotype để đăng ký bean.
- Thuộc tính `value` của `@Service` được alias tới `value` của `@Component`, nhờ đó có thể đặt tên bean bằng `@Service("orderService")`.

Meta-annotation là annotation được đặt trên một annotation khác. Khi Spring đọc một annotation trên class, framework có thể tìm sâu vào các meta-annotation để hiểu những metadata được kế thừa.

### 1.1. Ví dụ đọc cấu trúc

~~~text
OrderService
    |
    v
@Service
    |
    v
@Component
    |
    v
Spring component scanning nhận diện bean
~~~

Nếu chỉ dùng Java reflection trực tiếp với `OrderService.class.getAnnotation(Component.class)`, kết quả có thể không phản ánh cách Spring tìm annotation meta. Java reflection thông thường không tự tổng hợp mọi meta-annotation thành annotation trực tiếp trên class. Spring cung cấp các API riêng để thực hiện việc tìm kiếm và hợp nhất metadata đó.

## 2. Composed annotation giải quyết vấn đề gì?

Giả sử mọi controller trong một module đều cần:

- Được đăng ký là Spring MVC controller.
- Trả dữ liệu qua response body.
- Có cùng prefix URL.
- Tuân theo một quy ước API nội bộ.

Nếu mỗi class phải lặp lại nhiều annotation:

~~~java
@RestController
@RequestMapping("/api/v1")
public class OrderController {
}
~~~

~~~java
@RestController
@RequestMapping("/api/v1")
public class CustomerController {
}
~~~

~~~java
@RestController
@RequestMapping("/api/v1")
public class ProductController {
}
~~~

Có thể đóng gói quy ước chung vào một annotation:

~~~java
@ApiV1Controller
public class OrderController {
}
~~~

~~~java
@ApiV1Controller
public class CustomerController {
}
~~~

Một composed annotation tốt giúp:

- Giảm lặp metadata.
- Đặt tên theo ngôn ngữ của ứng dụng.
- Tạo quy ước thống nhất giữa các module.
- Giới hạn số lựa chọn mà người dùng annotation phải biết.
- Cho phép mở những thuộc tính cần tùy chỉnh mà vẫn giữ các mặc định chung.

Composed annotation là một **abstraction của metadata**. Nó không tự động tạo một object wrapper, không sinh subclass và cũng không phải proxy AOP. Hành vi thực tế phụ thuộc framework nào đọc annotation đó.

## 3. Các composed annotation quen thuộc trong Spring

### 3.1. @RestController

`@RestController` được xây dựng từ `@Controller` và `@ResponseBody`.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Controller
@ResponseBody
public @interface RestController {

    @AliasFor(annotation = Controller.class)
    String value() default "";
}
~~~

Ý nghĩa:

- `@Controller` đánh dấu một Spring MVC controller.
- `@ResponseBody` yêu cầu kết quả handler được ghi vào HTTP response body qua cơ chế message conversion.
- `@AliasFor` chuyển tên bean từ `RestController.value` sang `Controller.value`.

Ví dụ:

~~~java
@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

Nếu dùng `@Controller` đơn thuần, method trả object có thể được hiểu theo cơ chế view resolution tùy kiểu return và annotation. `@RestController` đóng gói quy ước trả response body cho cả controller.

### 3.2. @GetMapping

`@GetMapping` là một composed annotation dựa trên `@RequestMapping` và đặt HTTP method là `GET`.

~~~java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@RequestMapping(method = RequestMethod.GET)
public @interface GetMapping {

    @AliasFor(annotation = RequestMapping.class)
    String name() default "";

    @AliasFor(annotation = RequestMapping.class)
    String[] value() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] path() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] params() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] headers() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] consumes() default {};

    @AliasFor(annotation = RequestMapping.class)
    String[] produces() default {};
}
~~~

Ví dụ:

~~~java
@GetMapping(path = "/orders", produces = "application/json")
public List<OrderDto> listOrders() {
    return orderService.findAll();
}
~~~

Khi Spring đọc `@GetMapping`, framework nhận diện các thuộc tính mapping đã được chuyển tiếp tới `@RequestMapping`. Method HTTP vẫn là GET do meta-annotation quy định.

Các annotation chuyên biệt khác có cùng ý tưởng:

- `@PostMapping`: `@RequestMapping(method = POST)`.
- `@PutMapping`: `@RequestMapping(method = PUT)`.
- `@PatchMapping`: `@RequestMapping(method = PATCH)`.
- `@DeleteMapping`: `@RequestMapping(method = DELETE)`.

Thay vì viết `@RequestMapping(method = RequestMethod.GET)` ở mọi method, ta dùng annotation diễn đạt đúng ý nghĩa HTTP.

### 3.3. @SpringBootApplication

`@SpringBootApplication` là một ví dụ quan trọng ở cấp ứng dụng:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public @interface SpringBootApplication {

    @AliasFor(annotation = ComponentScan.class, attribute = "basePackages")
    String[] scanBasePackages() default {};

    @AliasFor(annotation = ComponentScan.class, attribute = "basePackageClasses")
    Class<?>[] scanBasePackageClasses() default {};

    @AliasFor(annotation = EnableAutoConfiguration.class, attribute = "exclude")
    Class<?>[] exclude() default {};

    @AliasFor(annotation = EnableAutoConfiguration.class, attribute = "excludeName")
    String[] excludeName() default {};
}
~~~

Đoạn trên lược bớt một số thuộc tính để tập trung vào cơ chế alias; source thực tế có thể có thêm thuộc tính và thay đổi theo phiên bản Spring Boot.

`@SpringBootApplication` kết hợp:

- `@SpringBootConfiguration`: đánh dấu class cấu hình chính của ứng dụng Boot.
- `@EnableAutoConfiguration`: bật cơ chế auto-configuration.
- `@ComponentScan`: tìm các component trong package phù hợp.

Nhờ alias, người dùng có thể viết:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.orders",
                "com.example.shared"
        },
        exclude = {
                SomeAutoConfiguration.class
        }
)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Các thuộc tính ở annotation cấp cao được chuyển đến annotation nền tương ứng. Người dùng không phải viết riêng `@ComponentScan` và `@EnableAutoConfiguration` chỉ để cấu hình những thuộc tính phổ biến.

**Lưu ý:** `scanBasePackages` chỉ điều chỉnh component scan. Nó không tự thay đổi mọi cơ chế scan khác như JPA entity scanning hoặc repository scanning; những cơ chế đó có annotation/cấu hình riêng.

## 4. @AliasFor dùng để làm gì?

`@AliasFor` thuộc package:

~~~java
import org.springframework.core.annotation.AliasFor;
~~~

Annotation này khai báo một thuộc tính là alias của một thuộc tính khác. Spring sử dụng metadata đó khi phân tích và tổng hợp annotation.

Có ba trường hợp thường gặp:

1. **Explicit aliases trong cùng một annotation:** hai thuộc tính khác tên nhưng mang cùng một giá trị.
2. **Implicit aliases trong cùng một annotation:** nhiều thuộc tính cùng override một thuộc tính của meta-annotation.
3. **Explicit aliases tới meta-annotation:** thuộc tính của composed annotation được chuyển tiếp đến thuộc tính cụ thể của annotation nền.

Các alias phải tuân thủ quy tắc tương thích về kiểu, giá trị mặc định và quan hệ annotation. Không phải chỉ thêm `@AliasFor` vào bất kỳ method annotation nào là Spring tự động hiểu ý định.

## 5. Explicit aliases trong cùng annotation

Giả sử muốn một annotation có hai tên thuộc tính `value` và `name` nhưng cả hai biểu diễn cùng một giá trị.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ClientTag {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "";
}
~~~

Cách sử dụng:

~~~java
@ClientTag("billing")
public class BillingClient {
}
~~~

hoặc:

~~~java
@ClientTag(name = "billing")
public class BillingClient {
}
~~~

Cả hai thuộc tính là alias hai chiều của nhau. Spring xem chúng là cùng một metadata value khi sử dụng merged annotation support.

### 5.1. Quy tắc của alias hai chiều

Với explicit aliases trong cùng annotation:

- Hai thuộc tính phải khai báo `@AliasFor` trỏ qua lại.
- Hai thuộc tính phải có cùng kiểu trả về.
- Hai thuộc tính phải có cùng giá trị mặc định.
- Chúng phải thuộc cùng một annotation.
- Việc đặt tên alias phải không tạo ra một graph alias mâu thuẫn.

Ví dụ không hợp lệ:

~~~java
public @interface InvalidTag {

    @AliasFor("name")
    String value() default "";

    @AliasFor("value")
    String name() default "default-name";
}
~~~

Hai default khác nhau khiến Spring không thể coi chúng là hai cách viết của cùng một thuộc tính một cách nhất quán. Khi Spring xác minh hoặc tổng hợp annotation, cấu hình có thể gây exception về alias configuration.

### 5.2. Khi nào cần alias trong cùng annotation?

Dùng khi muốn hỗ trợ hai tên tương đương vì:

- Tên ngắn gọn thuận tiện khi sử dụng.
- Tên mô tả rõ hơn cho người đọc.
- Tương thích với convention hoặc API annotation hiện có.
- Giữ API annotation tùy chỉnh gần với một annotation Spring nền.

Không nên tạo nhiều alias chỉ để có nhiều cách viết. Mỗi alias làm API metadata phức tạp hơn và tăng trách nhiệm kiểm thử.

## 6. Explicit aliases tới meta-annotation

Đây là trường hợp phổ biến nhất khi tạo composed annotation.

Ví dụ muốn mọi service của module billing mặc định là `@Service`, nhưng vẫn cho phép người dùng đặt bean name.

~~~java
package com.example.billing;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Service;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
public @interface BillingService {

    @AliasFor(annotation = Service.class, attribute = "value")
    String value() default "";
}
~~~

Sử dụng:

~~~java
@BillingService("invoiceProcessor")
public class InvoiceProcessor {
}
~~~

Spring nhận `@BillingService` là stereotype dựa trên `@Service`. Giá trị `"invoiceProcessor"` được chuyển tiếp tới `Service.value` và cuối cùng tham gia quy trình đặt tên bean của stereotype component.

### 6.1. Các quy tắc quan trọng

Với explicit alias tới meta-annotation:

- Annotation được tham chiếu phải thực sự là meta-annotation trên annotation tùy chỉnh (trực tiếp hoặc theo quan hệ được Spring hỗ trợ).
- Thuộc tính đích phải tồn tại trong meta-annotation.
- Kiểu trả về của thuộc tính alias và thuộc tính đích phải tương thích, thông thường phải giống nhau.
- Giá trị mặc định của thuộc tính alias phải tương thích với default của thuộc tính meta-annotation.
- Nên chỉ rõ `annotation` và `attribute` để người đọc thấy rõ đích alias.

Ví dụ sau có kiểu sai:

~~~java
public @interface InvalidBillingService {

    @AliasFor(annotation = Service.class, attribute = "value")
    Class<?> value() default Void.class;
}
~~~

`Service.value` là `String`, trong khi thuộc tính tùy chỉnh là `Class<?>`. Hai thuộc tính không thể alias với nhau.

### 6.2. Cố định metadata nền khi không cần expose thuộc tính

Nếu mọi bean của module đều phải mang một metadata cố định, có thể đặt giá trị trực tiếp trên meta-annotation mà không tạo alias.

Ví dụ:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
@Validated
public @interface ValidatedBillingService {
}
~~~

Annotation tùy chỉnh luôn kết hợp service stereotype với validation marker. Không cần expose một thuộc tính `validated` nếu người dùng không được phép thay đổi nó.

**Nguyên tắc:** chỉ alias những thuộc tính mà người sử dụng composed annotation thực sự cần điều chỉnh.

## 7. Implicit aliases: nhiều thuộc tính cùng override một meta-attribute

Một annotation có thể có nhiều thuộc tính cùng được đánh dấu là alias tới **cùng một thuộc tính của cùng meta-annotation**. Khi đó, các thuộc tính đó là implicit aliases của nhau.

Ví dụ khái niệm:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@RequestMapping
public @interface ApiRoute {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] route() default {};
}
~~~

Ở đây `path` và `route` cùng override `RequestMapping.path`. Khi dùng annotation, không nên cung cấp hai giá trị khác nhau cho hai alias cùng lúc:

~~~java
@ApiRoute(path = "/orders")
public class OrderController {
}
~~~

hoặc:

~~~java
@ApiRoute(route = "/orders")
public class OrderController {
}
~~~

Cả hai tên diễn đạt cùng metadata.

Nếu đồng thời khai báo:

~~~java
@ApiRoute(path = "/orders", route = "/invoices")
public class InvalidController {
}
~~~

Spring không thể hợp nhất hai giá trị khác nhau của cùng một alias group; việc tổng hợp annotation sẽ báo lỗi cấu hình alias/conflicting values.

### 7.1. Default của implicit aliases

Các thuộc tính implicit alias phải có kiểu trả về tương thích và cùng default value. Trong ví dụ, cả hai cùng trả `String[]` và default là mảng rỗng.

Không nên dùng implicit aliases chỉ để tạo nhiều synonym tùy tiện. Một tên canonical thường đủ; implicit aliases hữu ích khi phải hỗ trợ các tên thuộc tính tương đương vì API hoặc compatibility.

## 8. Custom composed annotation cho transaction

Một ví dụ thực tế là đóng gói quy ước transaction chỉ đọc cho nhóm truy vấn.

~~~java
package com.example.orders.persistence;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(readOnly = true)
public @interface ReadOnlyTransaction {

    @AliasFor(annotation = Transactional.class, attribute = "transactionManager")
    String transactionManager() default "";
}
~~~

Cách dùng:

~~~java
@Service
public class OrderQueryService {

    @ReadOnlyTransaction
    public OrderDto findOrder(UUID id) {
        // Đọc dữ liệu.
        return ...;
    }
}
~~~

`@ReadOnlyTransaction` luôn áp dụng meta-annotation `@Transactional(readOnly = true)`. Người dùng vẫn có thể chỉ định transaction manager nếu ứng dụng có nhiều transaction manager.

### 8.1. Vì sao không alias readOnly với default true?

`Transactional.readOnly` có default là `false`. Với explicit alias tới thuộc tính meta-annotation, các giá trị mặc định cần tương thích. Vì vậy, nếu custom annotation chỉ muốn cố định `readOnly = true`, hãy đặt giá trị trên meta-annotation và không expose thuộc tính `readOnly` như một alias có default khác.

Nếu cần cho phép caller bật/tắt read-only theo từng vị trí, phải thiết kế API alias với quy tắc default tương thích và xác minh theo semantics của Spring version đang dùng. Đừng chỉ đổi default của alias thành true rồi bỏ qua quy tắc hợp nhất.

### 8.2. Transaction advice vẫn cần proxy hoạt động

Composed annotation không tự mở transaction bằng cách đọc annotation trong constructor. `@ReadOnlyTransaction` hoạt động vì transaction infrastructure của Spring nhận diện `@Transactional` qua meta-annotation và áp dụng advisor/proxy tương ứng.

Những giới hạn proxy vẫn còn:

- Lời gọi phải đi qua proxy trong proxy mode.
- Self-invocation không kích hoạt advice riêng.
- Final/private/static methods không tự trở thành join point có thể intercept bằng proxy thông thường.
- Transaction manager và cấu hình transaction phải sẵn sàng.

Composed annotation chỉ giúp đóng gói metadata, không thay đổi cơ chế thực thi transaction.

## 9. Custom composed annotation cho controller

Một module API có thể định nghĩa annotation riêng để biểu đạt một loại controller.

~~~java
package com.example.api;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@RestController
@RequestMapping(path = "/api/v1")
public @interface ApiV1Controller {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

Sử dụng mặc định:

~~~java
@ApiV1Controller
public class OrderController {

    @GetMapping("/orders")
    public List<OrderDto> list() {
        return ...;
    }
}
~~~

Meta-annotation cung cấp `RequestMapping(path = "/api/v1")`. Thuộc tính `path` trên composed annotation cho phép override thuộc tính path của meta-annotation.

Ví dụ:

~~~java
@ApiV1Controller(path = "/internal")
public class InternalOrderController {
}
~~~

Trong ví dụ này, alias truyền giá trị tới thuộc tính mapping nền; nó không tự nối chuỗi `"/api/v1" + "/internal"`. Alias là cơ chế override metadata, không phải cơ chế ghép prefix/suffix. Nếu cần một quy tắc ghép path phức tạp, hãy dùng một cấu trúc mapping rõ ràng hoặc custom infrastructure được kiểm thử riêng.

### 9.1. Không khai báo hai mapping độc lập rồi kỳ vọng Spring ghép tự động

Nếu annotation tùy chỉnh đã mang `@RequestMapping` và class/method lại thêm một annotation mapping khác, cần xem quy tắc handler mapping của Spring MVC. Không nên giả định hai mapping sẽ luôn được merge theo cách cộng dồn mà ứng dụng mong muốn.

Giữ một nguồn sở hữu rõ ràng cho class-level path và method-level route. Dùng composed annotation để đóng gói metadata cấp class; dùng `@GetMapping`/`@PostMapping` cho handler methods.

## 10. @AliasFor với annotation nền có nhiều thuộc tính

`@RequestMapping` có nhiều thuộc tính như:

- `name`
- `value`
- `path`
- `method`
- `params`
- `headers`
- `consumes`
- `produces`

Một composed annotation chỉ nên expose những thuộc tính cần thiết cho use case. Ví dụ nếu API module luôn chỉ dùng JSON, có thể cố định `produces` trên meta-annotation và chỉ mở `path`.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@RequestMapping(
        path = "/api/v1",
        produces = "application/json"
)
public @interface JsonApiController {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

Cách này thu hẹp bề mặt cấu hình. Người dùng annotation không thể vô tình thay đổi `produces` sang một format trái với quy ước module.

Nếu muốn expose `produces`, thêm alias có kiểu và default phù hợp với `RequestMapping.produces`. Chỉ thêm thuộc tính khi nó có ý nghĩa thực sự.

## 11. Đặt tên value và path: alias của annotation nền

Một số annotation Spring có hai tên thuộc tính tương đương để thuận tiện cho cú pháp ngắn.

Ví dụ `@RequestMapping` khai báo `value` và `path` như aliases trong cùng annotation. Vì vậy, các cách viết sau có cùng ý nghĩa:

~~~java
@RequestMapping("/orders")
~~~

~~~java
@RequestMapping(path = "/orders")
~~~

Tương tự với `@GetMapping`:

~~~java
@GetMapping("/orders")
~~~

~~~java
@GetMapping(path = "/orders")
~~~

Nếu tạo custom annotation và expose cả `value` lẫn `path`, phải thiết kế alias group đúng quy tắc. Ví dụ đơn giản có thể alias cả hai về cùng thuộc tính nền, nhưng phải bảo đảm kiểu/default tương thích và kiểm tra conflict khi người dùng khai báo cả hai.

Trong nhiều trường hợp, chỉ expose `path` là đủ và rõ nghĩa hơn.

## 12. Meta-annotation có thể lồng nhiều tầng

Một composed annotation không chỉ được kết hợp đúng một tầng.

Ví dụ:

~~~text
@InternalApiController
       |
       v
@ApiV1Controller
       |
       +------> @RestController
       |
       +------> @RequestMapping
                    |
                    v
               @Controller / mapping metadata
~~~

Spring có thể tìm annotation qua các tầng meta-annotation theo cơ chế merged annotations. Các stereotype, mapping và configuration annotations của Spring đều dựa trên mô hình này.

Tuy nhiên, càng lồng nhiều tầng, việc truy vết giá trị cuối cùng càng khó. Nên giới hạn số tầng và đặt tên phản ánh vai trò thật sự của annotation.

### 12.1. Alias phải trỏ đến meta-annotation đúng trong hierarchy

Nếu custom annotation muốn alias tới `RequestMapping.path` nhưng không có `@RequestMapping` trong meta-annotation hierarchy, khai báo đó không hợp lệ về mặt cấu trúc.

Ví dụ sai:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Service
public @interface InvalidRoute {

    @AliasFor(annotation = RequestMapping.class, attribute = "path")
    String[] path() default {};
}
~~~

`InvalidRoute` không có `RequestMapping` làm meta-annotation. Alias target không nằm trong hierarchy, vì vậy Spring không thể hợp nhất giá trị theo ý định.

## 13. Các annotation cấu hình cũng có thể được compose

Composed annotation không chỉ dành cho stereotype hoặc MVC. Có thể đóng gói một nhóm cấu hình thường dùng.

Ví dụ một annotation module bật import configuration:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(OrdersModuleConfiguration.class)
public @interface EnableOrdersModule {
}
~~~

Sử dụng:

~~~java
@SpringBootApplication
@EnableOrdersModule
public class Application {
}
~~~

Annotation `@EnableOrdersModule` diễn đạt ý định bật module orders; Spring xử lý `@Import` meta-annotation và đăng ký configuration tương ứng.

Nếu annotation cần expose các thuộc tính cấu hình của imported component, có thể dùng `@AliasFor` tới meta-annotation phù hợp hoặc tạo một configuration properties type riêng. Đừng cố biến một annotation thành một file cấu hình lớn với hàng chục thuộc tính không liên quan.

### 13.1. Composed annotation không tự thay thế configuration properties

Annotation phù hợp cho metadata mang tính khai báo và các lựa chọn nhỏ, ổn định. Với cấu hình nhiều giá trị, nested object, duration, endpoint hoặc secret, `@ConfigurationProperties` thường phù hợp hơn.

Ví dụ không nên tạo annotation chứa hàng chục thuộc tính cho mọi timeout, retry count, URL và key. Hãy dùng một properties class typed, có validation và nguồn externalized configuration.

## 14. @Inherited và phạm vi kế thừa annotation

Java có meta-annotation `@Inherited` để cho phép annotation trên superclass được kế thừa khi đọc annotation ở subclass bằng một số reflection APIs.

Ví dụ:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface AuditedType {
}
~~~

~~~java
@AuditedType
class BaseHandler {
}

class OrderHandler extends BaseHandler {
}
~~~

Với `@Inherited`, truy vấn annotation theo cách reflection hỗ trợ có thể tìm thấy annotation trên superclass khi kiểm tra subclass.

Nhưng cần nhớ:

- `@Inherited` chỉ áp dụng cho annotation ở class declaration.
- Nó không làm annotation trên interface tự được kế thừa bởi class implement interface.
- Nó không làm annotation trên method được kế thừa sang override method theo cùng quy tắc.
- Spring merged-annotation search có semantics riêng và có thể tìm meta-annotation/hierarchy theo API được gọi.

Đừng thêm `@Inherited` vào mọi custom annotation một cách mặc định. Chỉ dùng nếu annotation thực sự phải truyền từ superclass xuống subclass và framework consumer cần hành vi đó.

## 15. Các meta-annotation Java cần khai báo đúng

Khi tạo custom annotation, những annotation sau thường quan trọng:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface ModuleService {
}
~~~

### @Target

Xác định annotation được phép đặt ở đâu.

Một số element type thường dùng:

| ElementType | Vị trí |
|---|---|
| `TYPE` | Class, interface, enum, annotation type, record |
| `METHOD` | Method |
| `FIELD` | Field |
| `PARAMETER` | Parameter |
| `CONSTRUCTOR` | Constructor |
| `ANNOTATION_TYPE` | Annotation type |
| `TYPE_USE` | Vị trí sử dụng kiểu |
| `TYPE_PARAMETER` | Khai báo type parameter |

Chọn đúng target theo annotation nền. Nếu custom annotation meta-annotated với `@Transactional` và muốn dùng trên class/method, target nên cho phép cả hai vị trí tương ứng.

### @Retention

`RetentionPolicy.RUNTIME` cho phép framework đọc annotation khi ứng dụng chạy.

Nếu dùng `RetentionPolicy.CLASS` hoặc `SOURCE`, metadata có thể không còn sẵn sàng theo cách reflection-based Spring annotation processing cần. Với composed annotations được Spring đọc runtime, thường phải dùng `RUNTIME`.

### @Documented

Giúp annotation xuất hiện trong Javadoc của phần tử được đánh dấu, làm API annotation dễ khám phá hơn.

### @Inherited

Chỉ thêm khi cần semantics kế thừa trên class như phần trước. Không phải yêu cầu bắt buộc của mọi composed annotation.

### @Repeatable

Chỉ dùng khi annotation có ý nghĩa cho phép xuất hiện nhiều lần trên cùng một element và có container annotation phù hợp. Không dùng `@Repeatable` chỉ vì muốn gắn nhiều alias values; alias và repeatability là hai vấn đề khác nhau.

## 16. Spring merged annotations: đọc composed annotation đúng cách

Khi cần đọc giá trị meta-annotation đã được alias/override, nên dùng API của Spring thay vì chỉ dùng Java reflection trực tiếp.

Ví dụ custom annotation:

~~~java
@ApiV1Controller(path = "/internal")
public class InternalOrderController {
}
~~~

Có thể lấy `RequestMapping` đã được hợp nhất:

~~~java
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RequestMapping;

RequestMapping mapping =
        AnnotatedElementUtils.findMergedAnnotation(
                InternalOrderController.class,
                RequestMapping.class
        );

System.out.println(Arrays.toString(mapping.path()));
~~~

Spring tìm qua meta-annotation hierarchy, áp dụng alias mapping và trả về annotation đã tổng hợp theo semantics của framework.

### 16.1. MergedAnnotations API

Spring Core cũng cung cấp `MergedAnnotations`:

~~~java
import org.springframework.core.annotation.MergedAnnotations;
import org.springframework.web.bind.annotation.RequestMapping;

MergedAnnotations annotations =
        MergedAnnotations.from(InternalOrderController.class);

RequestMapping mapping =
        annotations.get(RequestMapping.class).synthesize();
~~~

API cụ thể có nhiều lựa chọn về search strategy và cách tìm annotation. Ví dụ trên minh họa ý tưởng lấy một annotation meta đã được synthesize; trong code production, cần xử lý trường hợp annotation không tồn tại trước khi gọi `synthesize()`.

Ví dụ kiểm tra presence:

~~~java
boolean hasMapping =
        annotations.isPresent(RequestMapping.class);
~~~

### 16.2. Vì sao getAnnotation() không đủ?

~~~java
RequestMapping mapping =
        InternalOrderController.class.getAnnotation(RequestMapping.class);
~~~

Java reflection trả về annotation gắn trực tiếp theo metadata Java trên class. `@RequestMapping` trong ví dụ là meta-annotation nằm trên `@ApiV1Controller`, không được copy thành một annotation trực tiếp trên class.

Spring merged annotation APIs hiểu hierarchy và alias. Nếu code dùng framework metadata, hãy dùng API phù hợp của framework.

## 17. Test custom composed annotation

Một custom annotation cần được kiểm tra ít nhất ở hai khía cạnh:

1. **Metadata hợp nhất:** alias có truyền giá trị đến meta-annotation không?
2. **Framework behavior:** Spring có thực sự nhận diện annotation đó ở extension point tương ứng không?

### 17.1. Unit test alias value

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.web.bind.annotation.RequestMapping;

class ApiV1ControllerAnnotationTest {

    @Test
    void aliasesPathToRequestMapping() {
        RequestMapping mapping =
                AnnotatedElementUtils.findMergedAnnotation(
                        InternalOrderController.class,
                        RequestMapping.class
                );

        assertThat(mapping).isNotNull();
        assertThat(mapping.path()).containsExactly("/internal");
    }
}
~~~

Test này xác nhận alias trên custom annotation được hợp nhất với `RequestMapping`.

### 17.2. Test default meta-annotation value

~~~java
@Test
void usesDefaultApiPathWhenNotOverridden() {
    RequestMapping mapping =
            AnnotatedElementUtils.findMergedAnnotation(
                    OrderController.class,
                    RequestMapping.class
            );

    assertThat(mapping).isNotNull();
    assertThat(mapping.path()).containsExactly("/api/v1");
}
~~~

Test giả định `OrderController` dùng `@ApiV1Controller` không truyền path, và meta-annotation đặt `path = "/api/v1"`.

Điểm quan trọng: alias default của composed annotation phải được khai báo theo quy tắc của Spring để không vô tình xóa giá trị đã đặt trên meta-annotation.

### 17.3. Test framework registration

Với stereotype annotation như `@BillingService`, có thể dùng một Spring context test để xác nhận class được component scan đăng ký thành bean.

~~~java
@SpringBootTest
class BillingServiceComponentScanTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversComposedService() {
        assertThat(context.getBean("invoiceProcessor"))
                .isInstanceOf(InvoiceProcessor.class);
    }
}
~~~

Ví dụ giả định `InvoiceProcessor` nằm trong component scan và được đánh dấu `@BillingService("invoiceProcessor")`.

Với custom MVC annotation, dùng MockMvc hoặc handler mapping inspection để xác nhận endpoint được đăng ký đúng path. Với composed transaction annotation, cần test transaction behavior qua proxy thay vì chỉ assert annotation có mặt.

## 18. Lỗi thường gặp khi dùng @AliasFor

### 18.1. Alias target không nằm trong meta-annotation hierarchy

Lỗi thường do khai báo `@AliasFor(annotation = X.class, attribute = "...")` nhưng annotation X không phải meta-annotation phù hợp của annotation tùy chỉnh.

Cách xử lý: kiểm tra annotation nền có thật sự được đặt trên custom annotation hay không; sửa hierarchy hoặc alias tới đúng annotation.

### 18.2. Sai tên attribute

Ví dụ annotation nền có `path` nhưng code chỉ tới `paths`. Spring không thể tìm thuộc tính đích.

Dùng tên attribute đúng nguyên văn và có thể chỉ rõ `attribute` để tránh nhầm.

### 18.3. Sai kiểu trả về

Alias giữa `String` và `String[]`, hoặc `Class<?>` và `String` không hợp lệ. Kiểu của thuộc tính tùy chỉnh cần tương thích với thuộc tính meta.

### 18.4. Default value không tương thích

Nếu explicit alias tới meta-annotation, default của thuộc tính tùy chỉnh phải tuân thủ quy tắc tương thích với default của thuộc tính nền. Với aliases trong cùng annotation, các alias cũng phải có cùng default.

Khi muốn một giá trị nền cố định khác default, đặt nó trực tiếp trên meta-annotation và để alias default phù hợp với default declaration của thuộc tính nền.

### 18.5. Quên @Retention(RUNTIME)

Nếu annotation chỉ có retention mặc định `CLASS`, Spring có thể không đọc được annotation bằng runtime reflection theo cách mong muốn. Composed annotations dùng cho component scan, MVC, transaction và những framework runtime khác thường cần `RUNTIME`.

### 18.6. @Target không phù hợp

Nếu meta-annotation hỗ trợ method nhưng custom annotation chỉ cho phép TYPE, người dùng không thể đặt custom annotation lên method. Ngược lại, mở rộng target tùy tiện có thể tạo ra cách dùng không được framework consumer hỗ trợ.

Chọn target dựa trên vị trí annotation thực sự cần xuất hiện.

### 18.7. Gọi Java reflection và nghĩ rằng alias đã được ghi vào annotation

`@AliasFor` không sửa bytecode hoặc thay đổi annotation instance trong class file. Nó cung cấp metadata để Spring tổng hợp giá trị khi đọc annotation qua merged annotation infrastructure.

Dùng `AnnotatedElementUtils` hoặc `MergedAnnotations` khi cần đọc kết quả đã hợp nhất.

### 18.8. Hai aliases nhận hai giá trị xung đột

Nếu hai thuộc tính là aliases của nhau và người dùng cung cấp giá trị khác nhau cho cả hai, Spring không thể chọn một giá trị hợp lệ. Hãy chỉ truyền một trong hai hoặc thiết kế API để không tạo synonym không cần thiết.

### 18.9. Nghĩ rằng composed annotation tự tạo proxy

`@Transactional` meta-annotation có thể được transaction infrastructure nhận diện, nhưng việc thực thi vẫn phụ thuộc proxy/weaving mode và lời gọi phù hợp. Annotation tổng hợp không tự biến method thành proxy join point.

## 19. Alias không phải kế thừa Java và cũng không phải attribute mapping tùy ý

Cần phân biệt ba cơ chế:

| Cơ chế | Chức năng |
|---|---|
| Java inheritance | Subclass kế thừa member/behavior từ superclass |
| Meta-annotation | Annotation này mang annotation khác làm metadata |
| `@AliasFor` | Spring coi các annotation attributes là aliases và hợp nhất/forward giá trị |
| Configuration binding | Chuyển property sources thành object cấu hình |
| AOP proxy | Intercept method invocation theo proxy strategy |

Ví dụ `@AliasFor` không làm custom annotation kế thừa tất cả method Java của annotation nền theo nghĩa ngôn ngữ. Nó chỉ khai báo quan hệ giữa annotation attributes cho Spring annotation processing.

Tương tự, alias không tự động chuyển một property YAML thành annotation attribute. Đó là công việc của configuration binding.

## 20. Composed annotation và version compatibility

Annotation APIs của Spring đã được mở rộng qua nhiều phiên bản. Khi viết thư viện hoặc custom annotation dùng trong nhiều ứng dụng, cần xác định baseline Spring Framework/Spring Boot.

Một số mốc đáng nhớ:

- `@AliasFor` được giới thiệu trong Spring Framework 4.2.
- Spring cung cấp merged annotation support để tìm meta-annotations, override và synthesize attributes.
- Các phiên bản Spring Framework hiện đại có `MergedAnnotations` API và cơ chế xử lý annotation hierarchy phong phú hơn.
- Spring Boot 2.x và 3.x dùng những thế hệ Spring Framework khác nhau; package/API chính của `@AliasFor` vẫn thuộc `org.springframework.core.annotation`.
- Spring Boot 3 dựa trên Spring Framework 6 và Java 17 baseline, nhưng không có nghĩa custom annotation alias cũ tự động đúng nếu khai báo sai type/default/target.

### 20.1. Nếu viết starter/library dùng nhiều Boot versions

- Compile và test trên baseline Spring Framework thấp nhất mà thư viện tuyên bố hỗ trợ.
- Tránh dùng API merged annotation mới nếu baseline chưa có.
- Không dựa vào implementation detail của annotation scanner.
- Dùng các annotation Spring công khai như `@AliasFor` và API tương ứng.
- Có test xác nhận composed annotation trên từng dòng framework được hỗ trợ.
- Khi thay đổi thuộc tính/default của custom annotation, xem đó là thay đổi API có thể ảnh hưởng consumer.

### 20.2. Không copy source annotation của framework làm hợp đồng cố định

Ví dụ source `@GetMapping` hoặc `@SpringBootApplication` có thể thay đổi thuộc tính giữa phiên bản. Dùng chúng để học cấu trúc là hữu ích, nhưng khi viết custom annotation hãy dựa trên API public của version project đang dùng, không sao chép nguyên toàn bộ source vào code ứng dụng.

## 21. Thiết kế custom annotation sao cho dễ bảo trì

Một composed annotation nên có mục đích rõ và API nhỏ.

### 21.1. Đặt tên theo vai trò

Tên tốt thường diễn đạt một quy ước của module:

- `@BillingService`
- `@ReadOnlyTransaction`
- `@InternalApiController`
- `@AuditedOperation`
- `@EnableOrdersModule`

Tránh tên chung chung như `@CustomAnnotation`, `@MyComponent` hoặc `@SpecialConfig` vì không cho người đọc biết nó làm gì.

### 21.2. Giữ default ổn định

Người dùng annotation thường dựa vào default để giảm cấu hình. Nếu thay default của alias, hành vi của mọi class đang dùng annotation có thể đổi.

Hãy xem default như một phần API công khai và có test.

### 21.3. Expose ít thuộc tính

Nếu custom annotation có 15 alias đến nhiều meta-annotation, người dùng sẽ phải hiểu gần như toàn bộ framework API nền. Khi đó abstraction không còn giúp đơn giản hóa.

Chỉ expose những thuộc tính có ý nghĩa trong use case. Những giá trị mang tính quy ước nên được cố định ở meta-annotation.

### 21.4. Tránh nhiều lớp composed annotation không cần thiết

Một hierarchy quá sâu:

~~~text
@SpecialController
    -> @ModuleController
        -> @InternalController
            -> @RestController
                -> @Controller
                    -> @Component
~~~

có thể hoạt động nếu cấu trúc hợp lệ, nhưng khó truy vết metadata. Nếu chỉ có một quy ước, có thể compose trực tiếp từ annotation nền cần thiết.

### 21.5. Tài liệu hóa side effect framework

Một custom annotation nên mô tả rõ nó:

- Đăng ký bean hay chỉ đánh dấu metadata?
- Tạo MVC mapping nào?
- Bật transaction/read-only hay security rule nào?
- Import configuration class nào?
- Có yêu cầu starter/dependency nào?
- Có điều kiện profile/classpath nào?

Tên annotation chỉ là một phần của hợp đồng; behavior cần được mô tả.

## 22. Ví dụ hoàn chỉnh: một module có custom stereotype và transaction annotation

Giả sử module orders muốn chuẩn hóa service và query transaction.

### 22.1. Custom stereotype

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
public @interface OrderService {

    @AliasFor(annotation = Service.class, attribute = "value")
    String value() default "";
}
~~~

### 22.2. Custom read-only transaction

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(readOnly = true)
public @interface OrderReadOnly {

    @AliasFor(annotation = Transactional.class, attribute = "transactionManager")
    String transactionManager() default "";
}
~~~

### 22.3. Sử dụng trong service

~~~java
@OrderService("orderQueryService")
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @OrderReadOnly
    public OrderDto findById(UUID id) {
        return repository.findById(id)
                .map(OrderDto::from)
                .orElseThrow();
    }
}
~~~

Kết quả về mặt metadata:

- `OrderQueryService` được component scan nhận diện như một service.
- Bean name có thể là `orderQueryService`.
- Method `findById` mang metadata transaction read-only thông qua meta-annotation.
- Transaction infrastructure có thể áp dụng transaction advice nếu method được gọi qua proxy và cấu hình transaction phù hợp.

### 22.4. Integration test nên xác nhận cả hai phần

- Context có bean tên `orderQueryService`.
- Bean có thể inject `OrderRepository`.
- Method được gọi qua proxy và transaction read-only được áp dụng theo transaction manager.
- Nếu method được gọi nội bộ trong cùng bean, cần xét self-invocation như mọi proxy-based transaction khác.

Không chỉ kiểm tra `OrderQueryService.class.isAnnotationPresent(OrderService.class)` vì điều đó không chứng minh component scan hay transaction advice hoạt động.

## 23. Checklist tạo custom composed annotation

Khi tạo một annotation mới, hãy kiểm tra:

1. Annotation có một mục đích nghiệp vụ/framework rõ ràng không?
2. Meta-annotation nền đã đúng chưa?
3. `@Target` có bao gồm đúng các vị trí sử dụng không?
4. `@Retention(RUNTIME)` đã được khai báo chưa?
5. Có cần `@Documented` hoặc `@Inherited` không?
6. Các thuộc tính nào cần expose cho người dùng?
7. `@AliasFor` trỏ đúng annotation/attribute chưa?
8. Kiểu trả về và default values có tương thích không?
9. Có explicit alias hai chiều hay implicit alias group cần đồng bộ không?
10. Có nguy cơ hai aliases nhận giá trị xung đột không?
11. Framework consumer có nhận diện meta-annotation đó không?
12. Đã kiểm thử merged annotation value và behavior thật chưa?
13. Annotation có tương thích với Spring version thấp nhất mà dự án hỗ trợ không?
14. Tài liệu đã giải thích default, scope và dependency cần thiết chưa?

## 24. Chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Custom stereotype không tạo bean | Thiếu meta-annotation stereotype hoặc component scan không bao phủ package | Kiểm tra `@Component`/`@Service` meta-annotation và scan scope |
| Alias không truyền giá trị | Sai target annotation/attribute hoặc default/type không khớp | Kiểm tra `@AliasFor` và hierarchy |
| Spring báo alias configuration exception | Alias pair/group không hợp lệ hoặc có giá trị xung đột | Đồng bộ type/default và chỉ khai báo một alias value |
| Annotation không đọc được runtime | Retention không phải RUNTIME | Dùng `@Retention(RetentionPolicy.RUNTIME)` |
| Không thể đặt annotation lên method | `@Target` không cho phép METHOD | Bổ sung target đúng nếu semantics hỗ trợ |
| Java getAnnotation không thấy meta-annotation | Annotation chỉ nằm trong hierarchy | Dùng Spring `AnnotatedElementUtils`/`MergedAnnotations` |
| Mapping path không như mong muốn | Alias override giá trị meta-annotation thay vì nối chuỗi | Thiết kế path semantics rõ và kiểm tra merged mapping |
| @Transactional meta-annotation không chạy | Transaction infrastructure/proxy/call path không phù hợp | Kiểm tra proxy, self-invocation, visibility và transaction manager |
| Custom annotation hoạt động trên Boot mới nhưng lỗi Boot cũ | API/version baseline khác nhau | Compile/test trên framework baseline được hỗ trợ |
| Thêm nhiều meta-annotation gây behavior khó đoán | Metadata hierarchy quá rộng hoặc có xung đột | Giảm số tầng và expose ít thuộc tính |

## 25. Nguyên tắc ghi nhớ

- **Composed annotation** đóng gói một hoặc nhiều meta-annotation thành một annotation có ý nghĩa cụ thể hơn.
- `@RestController`, `@GetMapping`, `@Service` và `@SpringBootApplication` là những ví dụ quen thuộc.
- **Meta-annotation** là annotation được đặt trên một annotation khác.
- `@AliasFor` khai báo quan hệ giữa annotation attributes; nó không sửa bytecode và không phải cơ chế Java inheritance.
- Explicit aliases trong cùng annotation cần khai báo quan hệ alias tương ứng, có kiểu và default tương thích.
- Implicit aliases cùng override một meta-attribute cũng cần type/default nhất quán.
- Explicit alias tới meta-annotation phải trỏ đến annotation thật sự trong hierarchy và đúng attribute.
- Muốn cố định giá trị meta-annotation, đặt giá trị trực tiếp trên annotation nền; không cần expose alias nếu người dùng không được thay đổi.
- Custom annotation dùng cho Spring runtime thường cần `@Retention(RetentionPolicy.RUNTIME)` và `@Target` phù hợp.
- Dùng `AnnotatedElementUtils` hoặc `MergedAnnotations` để đọc metadata đã hợp nhất; Java reflection đơn giản không thay thế toàn bộ merged annotation semantics.
- Composed annotation chỉ đóng gói metadata; transaction, MVC mapping, component scan hoặc import vẫn phụ thuộc framework infrastructure.
- Test cả giá trị alias đã hợp nhất và hành vi thực tế của framework.
- Giữ annotation nhỏ, tên rõ nghĩa, default ổn định và version compatibility được xác định.

**Kết luận:** Composed annotation giúp biến một nhóm metadata lặp lại thành một quy ước có tên trong ứng dụng. `@AliasFor` làm cho các thuộc tính của annotation tùy chỉnh có thể chuyển tiếp hoặc đồng bộ với thuộc tính của meta-annotation. Khi thiết kế đúng hierarchy, target, retention, kiểu và default values, custom annotation sẽ giảm lặp code mà vẫn giữ được khả năng cấu hình rõ ràng. Khi gặp lỗi, hãy kiểm tra quan hệ meta-annotation và merged-annotation behavior trước khi nghi ngờ component scan hay framework runtime.
