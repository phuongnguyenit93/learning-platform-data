# Không tìm thấy hàm trong FunctionCatalog

## 1. Tình huống: có Java Function nhưng lookup hoặc adapter báo không tìm thấy

Bạn định nghĩa một bean của **Spring Cloud Function**:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Nhưng một lời gọi tới `FunctionCatalog` không cho kết quả mong muốn:

~~~java
Function<String, String> f =
    functionCatalog.lookup(Function.class, "uppercase");
~~~

Hoặc ứng dụng chạy nhưng HTTP `/uppercase` trả 404, Spring Cloud Stream không tạo binding, AWS Lambda không chọn được function hay một expression routing trỏ tới tên không tồn tại.

Các triệu chứng này **không nhất thiết cùng nguyên nhân**. Spring Cloud Function tách logic nghiệp vụ `Supplier`, `Function`, `Consumer` khỏi HTTP, message broker và serverless; chúng được đưa vào `ApplicationContext`, `FunctionCatalog`, composition và các adapter khác nhau. Khi một hàm không hoạt động, cần tìm chính xác ranh giới đang lỗi.

**Nguyên tắc chẩn đoán:**

> Đừng suy ra catalog thiếu hàm chỉ vì một HTTP endpoint không tồn tại hoặc consumer không nhận message. Hãy chứng minh lần lượt: **bean có được tạo → catalog có tên → lookup theo tên/loại thành công → function gọi trực tiếp được → adapter có chọn và kết nối đúng**.

Bài học thuộc chương **Chẩn đoán**, với đề mục **“Không tìm thấy hàm trong FunctionCatalog”**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cách các bean Java `Supplier`/`Function`/`Consumer` tham gia `FunctionCatalog`.
2. Dùng `getNames(null)`, `size()`, `lookup(...)` và `ApplicationContext` để khoanh vùng lỗi.
3. Chẩn đoán vấn đề component scan, `@Bean`, `@Configuration`, profile, conditional bean và kiểu generic.
4. Phân biệt tên bean, function definition/composition, HTTP path, binding name và broker destination.
5. Hiểu cơ chế *single-function fallback* có thể che lỗi gõ sai tên và cách tắt trong test.
6. Phân biệt catalog không có function với lỗi routing, conversion, subscription hoặc adapter.
7. Viết test xác nhận function đã đăng ký, composition hoạt động và việc deploy không phụ thuộc fallback.

## 2. Các ranh giới cần phân biệt

Spring Cloud Function hỗ trợ các giao diện:

~~~java
java.util.function.Supplier<O>
java.util.function.Function<I, O>
java.util.function.Consumer<I>
~~~

Một bean kiểu chức năng được Spring quản lý có thể được đưa vào catalog. Catalog cung cấp khả năng lookup và các lớp wrapper phục vụ chuyển đổi kiểu, composition cùng các chức năng tích hợp. Lấy bean gốc bằng `ApplicationContext.getBean(...)` không nhất thiết giống việc tra wrapper qua `FunctionCatalog`.

~~~mermaid
flowchart LR
    CODE["Mã @Bean hoặc functional class"] --> CTX["ApplicationContext"]
    CTX --> CAT["FunctionCatalog"]
    CAT --> DEF["lookup(name / definition)"]
    DEF --> AD["HTTP / Spring Cloud Stream / Serverless"]
    AD --> INV["invoke + chuyển đổi payload"]
~~~

| Ranh giới | Câu hỏi cần kiểm tra | Dấu hiệu lỗi |
| --- | --- | --- |
| Source → Spring context | Class cấu hình được scan/import? Bean được tạo? | Context không có bean |
| Spring context → catalog | Bean có dạng functional đủ điều kiện? Có bị filter? | Context có bean, catalog không có |
| Catalog → lookup | Tên, loại, composition và fallback đúng? | Tên có trong danh sách nhưng lookup nhầm |
| Catalog → adapter | Adapter có chọn function cần dùng? | Lookup trực tiếp OK, HTTP/Stream lỗi |
| Adapter → business | Kiểu payload, header, publisher và logic đúng? | Invoke lỗi sau khi function được tìm thấy |

Điểm quan trọng: thông báo lỗi ứng dụng có thể mang chữ “function not found”, nhưng để kết luận nguyên nhân cần biết nó xuất phát từ **catalog**, **router**, **adapter** hay cách code sử dụng catalog.

## 3. Ứng dụng mẫu có tên function xác định

Sử dụng một class cấu hình Spring Boot đơn giản:

~~~java
package demo.diagnostics;

import java.util.Locale;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }

    @Bean
    public Supplier<String> greeting() {
        return () -> "hello";
    }
}
~~~

Ví dụ giả định project đã khai báo các dependency Spring Boot/Spring Cloud Function tương thích. Ba tên bean là `uppercase`, `reverse` và `greeting`. Việc một class chứa phương thức tên giống function **không có nghĩa method đó đã được đăng ký**; trong ví dụ trên `@Bean` mới thực hiện việc đăng ký.

### 3.1. Lookup wrapper và lấy bean gốc là hai thao tác khác nhau

~~~java
Function<String, String> wrapped =
    functionCatalog.lookup(Function.class, "uppercase");

Function<String, String> original =
    applicationContext.getBean("uppercase", Function.class);
~~~

`original` là bean do Spring tạo; `wrapped` là function do catalog trả về. Spring Cloud Function có thể wrap function để hỗ trợ chuyển đổi message và composition. Không nên viết test bắt hai object phải là cùng instance; hãy kiểm tra hợp đồng hoạt động.

### 3.2. Đừng kiểm tra HTTP trước khi kiểm tra catalog

Trong một ứng dụng chỉ dùng `spring-cloud-function-context`, catalog có thể hoạt động mà **không có HTTP endpoint**. HTTP adapter là thành phần tích hợp tùy chọn.

Bước đầu tiên là xác minh catalog trong chính process đang chạy, không gửi hàng trăm request tới `/uppercase` để đoán xem route nào đúng.

## 4. Quan sát catalog bằng API chính thức

Spring Cloud Function cung cấp các API liệt kê function:

~~~java
import java.util.Set;
import org.springframework.cloud.function.context.FunctionCatalog;

FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

int size = catalog.size();
Set<String> names = catalog.getNames(null);

System.out.println("catalog size: " + size);
System.out.println("catalog names: " + names);
~~~

`catalog.getNames(null)` cho biết các tên được catalog công bố theo API. Nó hữu ích hơn việc suy đoán từ tên class hoặc path HTTP.

### 4.1. Đọc kết quả

- **Không inject được `FunctionCatalog`:** cần kiểm tra dependency, autoconfiguration và việc ứng dụng khởi động.
- **Inject được, không thấy tên mong đợi:** quay lại bean registration, scan, điều kiện và filter.
- **Thấy tên, lookup không đúng:** xem loại function, tên, composition, fallback.
- **Lookup hoạt động, adapter báo lỗi:** chuyển hướng sang HTTP/binder/serverless.
- **Lookup hoạt động, invoke ném exception:** xem kiểu dữ liệu, message conversion, logic hoặc reactive subscription.

### 4.2. So sánh với ApplicationContext

~~~java
import java.util.Arrays;
import java.util.function.Function;
import java.util.function.Consumer;
import java.util.function.Supplier;

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Function.class)
));

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Supplier.class)
));

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Consumer.class)
));

System.out.println("Catalog names: " + catalog.getNames(null));
~~~

Hai tập kết quả **không nhất thiết giống hệt nhau**: context cho biết các Spring beans được nhận diện theo kiểu, còn catalog áp dụng quy tắc đăng ký, chức năng bổ trợ và các bộ lọc riêng.

Nếu context không có tên, kiểm tra Spring registration. Nếu context có mà catalog không có, kiểm tra eligibility và metadata của function.

### 4.3. Một ApplicationRunner chẩn đoán tạm thời

~~~java
package demo.diagnostics;

import java.util.Arrays;
import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class FunctionDiagnostics implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(FunctionDiagnostics.class);

    private final ApplicationContext context;
    private final FunctionCatalog catalog;
    private final Environment environment;

    FunctionDiagnostics(
            ApplicationContext context,
            FunctionCatalog catalog,
            Environment environment) {
        this.context = context;
        this.catalog = catalog;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Selected function definition: {}",
            environment.getProperty(
                "spring.cloud.function.definition", "<unset>"
            ));

        log.info("Spring Function beans: {}",
            Arrays.toString(
                context.getBeanNamesForType(Function.class)
            ));

        log.info("Catalog names: {}", catalog.getNames(null));
        log.info("Catalog size: {}", catalog.size());
        log.info("uppercase lookup present: {}",
            catalog.lookup(Function.class, "uppercase") != null);
    }
}
~~~

Dùng đoạn này trong môi trường phát triển hoặc profile chẩn đoán có kiểm soát. Không log mọi environment variable, token, dữ liệu nhạy cảm hoặc toàn bộ payload chỉ vì function khó tìm.

## 5. Bảng phân loại triệu chứng

| Triệu chứng | Nguyên nhân nghi vấn | Phép kiểm tra ưu tiên |
| --- | --- | --- |
| `FunctionCatalog` không được inject | Thiếu dependency/autoconfiguration, context lỗi | Log khởi động và bean list |
| `ApplicationContext` không có bean | Sai `@Bean`, scan, profile/condition | Bean name, component scan, active profiles |
| Context có nhưng catalog không có | Dạng bean/metadata hoặc `ineligible-definitions` | So danh sách tên hai nơi |
| `lookup("foo")` sai | Sai tên, loại hoặc composition | `getNames(null)` và typed lookup |
| Lookup tên **sai** vẫn thành công | Single-function fallback | Tắt fallback trong test |
| Function có trong catalog nhưng không có HTTP route | Chưa có web adapter/path/mapping | Check web module và HTTP config |
| Catalog có bean nhưng Stream không nhận event | Definition/binding/destination/binder | Startup binding log và broker |
| Lambda gọi function khác | Entry point/handler và definition/routing | Deployment settings |
| Function đã gọi nhưng JSON lỗi | Converter/generic type/header | Exception chuyển đổi payload |
| Reactive function trả Flux không thấy dữ liệu | Không có subscription | StepVerifier/caller/adapter |

Không sửa tất cả cấu hình cùng lúc. Khoanh vùng ở đâu trước, sửa đúng một lớp rồi xác minh lại.

## 6. Nguyên nhân: thiếu @Bean hoặc @Configuration chưa được tải

### 6.1. Method Java thông thường không tự thành bean

~~~java
@Configuration
public class OrderFunctions {

    // Không tự được đăng ký thành bean vì thiếu @Bean.
    public Function<String, String> normalizeOrder() {
        return String::trim;
    }
}
~~~

Khai báo đúng theo `@Bean`:

~~~java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<String, String> normalizeOrder() {
        return String::trim;
    }
}
~~~

`@Configuration` cũng phải được Spring scan hoặc import thì `@Bean` mới được xử lý.

### 6.2. Package của SpringBootApplication đặt quá sâu

Giả sử:

~~~text
demo.app.Application                (@SpringBootApplication)
demo.functions.OrderFunctions       (@Configuration)
demo.other.MySupplier
~~~

Mặc định, `@SpringBootApplication` scan từ package của class ứng dụng và các package con. Nếu `demo.functions` không nằm dưới `demo.app`, cấu hình có thể không được tìm thấy.

Có thể:

- Chuyển application class lên package cha phù hợp.
- Dùng `@Import(OrderFunctions.class)` để import cấu hình chính xác.
- Dùng `scanBasePackages` hoặc `@ComponentScan` có phạm vi rõ nếu cần.
- Đối chiếu class có nằm trong artifact/JAR deploy hay không.

Ví dụ:

~~~java
@SpringBootApplication
@Import(OrderFunctions.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Tránh scan quá rộng làm xuất hiện các function ngoài dự kiến, gây xung đột tên hoặc thay đổi hành vi fallback.

### 6.3. Profile và condition không đáp ứng

~~~java
@Configuration
@Profile("dev")
public class DevFunctions {

    @Bean
    public Function<String, String> devOnly() {
        return String::trim;
    }
}
~~~

Nếu profile `dev` không active, `devOnly` không được tạo. Tương tự với `@ConditionalOnProperty` và các điều kiện Spring Boot.

`spring.cloud.function.definition=devOnly` chỉ **chọn function**, không ép Spring tạo bean đã bị tắt bởi điều kiện.

Kiểm tra active profiles, property hiệu lực và condition evaluation report khi cần. Luôn tìm **startup exception đầu tiên** trước: nếu context chưa khởi động thành công, báo lỗi lookup chỉ là biểu hiện thứ cấp.

## 7. Nguyên nhân: nhầm component scan của Spring với Function Component Scan

Spring Cloud Function còn có **Function Component Scan** để phát hiện class triển khai `Supplier`, `Function` hoặc `Consumer` theo quy tắc riêng của SCF, kể cả trường hợp không có `@Component`.

Tài liệu mô tả package `functions` được quét theo convention và hai property liên quan:

~~~properties
spring.cloud.function.scan.packages=demo.myfunctions
spring.cloud.function.scan.enabled=true
~~~

Khi muốn tắt function-specific scan:

~~~properties
spring.cloud.function.scan.enabled=false
~~~

| Cơ chế | Vai trò | Thường dùng |
| --- | --- | --- |
| Spring component scanning | Tìm `@Configuration`/`@Component` và các bean Spring thông thường | `@SpringBootApplication`, `@ComponentScan` |
| SCF function scanning | Tìm implementation của functional interfaces theo package convention/config | Các class functional không khai báo Spring annotation |

**Không coi `spring.cloud.function.scan.packages` là cách chữa mọi lỗi Spring component scan.** Với một `@Bean` trong class `@Configuration` nằm ngoài package Spring scan, hãy kiểm tra chính class cấu hình trước.

### 7.1. Class name có thể quyết định tên được đăng ký

Một implementation có tên `functions.UpperCaseFunction` có thể được tìm dưới tên `upperCaseFunction`, không phải `uppercase`. Naming conventions và registration mode quyết định tên cuối cùng.

`catalog.getNames(null)` là nguồn kiểm tra đáng tin hơn suy đoán. Nếu cần tên ổn định, ưu tiên bean hoặc registration tường minh.

### 7.2. Tắt SCF scan khác với xóa tất cả @Bean

`spring.cloud.function.scan.enabled=false` chỉ ảnh hưởng chức năng scan đặc thù của SCF. Các `@Bean` được Spring Boot tạo thông thường không tự biến mất chỉ vì property này.

## 8. Nguyên nhân: bean có kiểu không rõ hoặc không phải Java functional interface

Spring Cloud Function tập trung vào `java.util.function.Function`, `Supplier` và `Consumer`.

Một class tự tạo phương thức `apply` nhưng không implement `java.util.function.Function`, hoặc một bean có declared type quá chung, có thể không được framework nhận diện như mong muốn.

### 8.1. Tránh khai báo @Bean trả Object

~~~java
@Bean
public Object uppercase() {
    return (Function<String, String>) String::toUpperCase;
}
~~~

Hình thức này làm mất thông tin generic trong chữ ký khai báo và có thể gây khó khăn cho việc suy kiểu, chuyển đổi payload hoặc đăng ký catalog tùy cơ chế framework.

Ưu tiên:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

### 8.2. Kiểm tra import

~~~java
import java.util.function.Function;
import java.util.function.Consumer;
import java.util.function.Supplier;
~~~

Đừng nhầm `Function` của thư viện khác hoặc một interface tùy chỉnh có tên giống nhau với Java functional interfaces.

### 8.3. Functional registration và FunctionRegistration

Ngoài `@Bean`, Spring Cloud Function hỗ trợ `FunctionalSpringApplication` và `FunctionRegistration`. Với functional registration, tên và generic type metadata có thể cần được khai báo tường minh vì lambda không luôn mang đầy đủ generic information ở runtime.

Khi sử dụng mô hình này, hãy đối chiếu:

1. Function đã thực sự được đăng ký vào đúng context chưa?
2. `FunctionRegistration` có tên mong muốn không?
3. Thông tin input/output type được cung cấp đủ chưa?
4. Có vô tình trộn `@Bean` và functional registration tạo hai function khác tên không?
5. Test có chạy đúng startup mode của production không?

Tham khảo tài liệu **Functional Bean Definitions** của phiên bản đang triển khai; không tự đổi mô hình khởi động chỉ để thử sửa lỗi lookup.

### 8.4. Proxy và kiểu runtime

AOP proxy, factory bean hoặc cấu hình nâng cao có thể làm declared bean type khác type bạn kỳ vọng. Dùng `applicationContext.getType(name)` và bean definition để kiểm tra. Không mặc định AOP là nguyên nhân khi chưa có bằng chứng.

## 9. Nguyên nhân: tên bean không trùng tên method hoặc class

~~~java
@Bean("normalizeOrder")
public Function<String, String> uppercase() {
    return String::trim;
}
~~~

Tên được khai báo ở đây là `normalizeOrder`. Caller lookup `uppercase` có thể sai vì chỉ nhìn tên method.

Với method không chỉ định tên:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

tên mặc định là `uppercase`.

### 9.1. Năm loại tên khác nhau

| Loại tên | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bean/function name | `normalizeOrder` | Định danh function trong catalog |
| Function definition | `normalizeOrder|audit` | Composition của các function |
| HTTP path | `/normalizeOrder` | Route web adapter nếu được export |
| Stream binding | `normalizeOrder-in-0` và `normalizeOrder-out-0` | Kết nối logic với binder |
| Broker destination | `orders-in` và `orders-out` | Topic/queue ở transport |

Broker destination **không phải** tên function catalog. Không tra `catalog.lookup("orders-in")` nếu function tên `normalizeOrder`.

### 9.2. So sánh tên chính xác

Đừng phỏng đoán khác biệt hoa/thường, chữ viết tắt hoặc dấu gạch nối. In tên thực bằng `getNames(null)`. Trong deployment lớn, property có thể đến từ profile/environment khác với file local.

## 10. Nguyên nhân đặc biệt: single-function fallback che lỗi gõ sai

Tài liệu chính thức mô tả rằng khi ứng dụng chỉ có **một functional bean** đủ điều kiện, lookup theo tên rỗng, `null` hoặc thậm chí một tên không đúng có thể trả về **hàm duy nhất**.

Ví dụ chỉ có `uppercase`:

~~~java
Function<String, String> expected =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> misspelled =
    catalog.lookup(Function.class, "upprcase");
~~~

Trong điều kiện fallback được áp dụng, `misspelled` **có thể không null**. Điều đó **không** chứng minh `upprcase` thực sự là tên function.

### 10.1. Tắt fallback trong test

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

Khi tắt, một tên không tồn tại sẽ dễ bị phát hiện hơn. Đây là cơ chế hữu ích cho regression test tên function.

### 10.2. Vì sao thêm bean thứ hai làm app “bỗng lỗi”?

Ban đầu chỉ có `uppercase` nên `lookup("upprcase")` vẫn được fallback. Sau khi thêm `reverse`, việc lựa chọn không còn chỉ có một ứng viên; caller gõ sai bắt đầu thất bại.

Đừng xóa `reverse` để khôi phục fallback. Cần sửa caller hoặc `spring.cloud.function.definition` theo tên chính xác.

### 10.3. Không dùng fallback làm hợp đồng production

Với Spring Cloud Stream và serverless có nhiều function, cấu hình selection tường minh:

~~~properties
spring.cloud.function.definition=uppercase
~~~

và test danh sách catalog cùng lookup đúng tên. Fallback nên là behavior được hiểu rõ, không phải phương án tự sửa tên sai.

## 11. Nguyên nhân: spring.cloud.function.definition không chọn đúng function

Property:

~~~properties
spring.cloud.function.definition=uppercase
~~~

chọn một function có tên phù hợp.

Còn:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

là **một composition**: đầu ra của `uppercase` đi vào `reverse`.

### 11.1. Một function bị thiếu trong composition

Nếu cấu hình là `normalize|enrich|audit` mà `enrich` chưa được đăng ký:

1. Đọc `catalog.getNames(null)`.
2. Lookup `normalize`.
3. Lookup `enrich`.
4. Lookup `audit`.
5. Kiểm tra kiểu output/input tương thích từng cặp.
6. Cuối cùng lookup cả definition.

Một composition không tạo được **không có nghĩa tất cả bean đã biến mất**.

### 11.2. Pipe và dấu chấm phẩy mang ý nghĩa khác nhau trong Stream

~~~properties
# Một pipeline gồm hai bước:
spring.cloud.function.definition=uppercase|reverse
~~~

Trong Spring Cloud Stream, nếu muốn **hai function độc lập** được bind riêng:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Cú pháp selection có thể ảnh hưởng số và tên binding được tạo. Đừng đặt `;` nếu mục tiêu là chuyển đầu ra `uppercase` thẳng vào `reverse`.

### 11.3. Property có thể bị ghi đè ở runtime

Dù một file source chứa `definition=uppercase`, deployment có thể dùng profile khác, environment variable hoặc command-line argument khác.

~~~java
String actual = environment.getProperty(
    "spring.cloud.function.definition", "<unset>"
);
log.info("Runtime function definition={}", actual);
~~~

Đây là **giá trị thực tế trong Environment** của process. Đừng log toàn bộ environment vì có thể chứa credentials.

## 12. Nguyên nhân: function bị loại bởi ineligible-definitions

SCF có thể loại trừ các bean không mong muốn khỏi catalog:

~~~properties
spring.cloud.function.ineligible-definitions=foo,bar
~~~

Nếu `uppercase` được đưa vào danh sách này, bean có thể còn trong context nhưng không được catalog công bố.

### 12.1. Bằng chứng cần có

- Context có tên `uppercase`.
- Catalog không có tên `uppercase`.
- Property `spring.cloud.function.ineligible-definitions` đang chứa tên đó.
- Sau khi chỉnh exclusion phù hợp, catalog có tên mong muốn.

Chỉ bỏ tên khỏi filter khi nó thực sự được phép export. Không tắt cơ chế filter rộng rãi để đưa cả function nội bộ ra ngoài.

## 13. Nguyên nhân: typed lookup không đúng loại bean

Giả sử một bean:

~~~java
@Bean
public Supplier<String> greeting() {
    return () -> "hello";
}
~~~

Nếu caller gọi:

~~~java
Function<String, String> wrong =
    catalog.lookup(Function.class, "greeting");
~~~

thì đang yêu cầu lookup theo loại `Function` cho một bean `Supplier`. Kết quả có thể không khớp hoặc bị từ chối theo hợp đồng của catalog/adapter.

Tra cứu đúng kiểu khi biết nó là supplier:

~~~java
Supplier<String> greeting =
    catalog.lookup(Supplier.class, "greeting");
~~~

| Loại | Phương thức Java | Hợp đồng |
| --- | --- | --- |
| `Supplier<T>` | `get()` | Không có input |
| `Function<T,R>` | `apply(input)` | Có input và output |
| `Consumer<T>` | `accept(input)` | Có input, trả `void` |

Một `Consumer` không tự biến thành `Function` chỉ vì có tên trong catalog. Khi composition, cần kiểm tra khả năng ghép giữa các loại, không chỉ sự tồn tại của từng bean.

## 14. Nguyên nhân: catalog đúng nhưng HTTP endpoint không được export

Đừng kết luận catalog rỗng từ HTTP 404.

Với **Spring Cloud Function web adapter** và một bean `uppercase` được export, có thể thử:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data "hello" \
  http://localhost:8080/uppercase
~~~

Nếu không có endpoint:

1. `catalog.lookup("uppercase")` có ra function không?
2. App có dependency web adapter của Spring Cloud Function, không chỉ context?
3. Server có chạy đúng port, context path và quản trị proxy không?
4. `spring.cloud.function.web.path` có đổi base path không?
5. `spring.cloud.function.definition` có giới hạn những function được export không?
6. HTTP method, content type và security có cho phép request không?
7. Reverse proxy/gateway có rewrite URL hay chặn path không?

### 14.1. Single-function root mapping

Một web adapter có thể cho phép gọi root path khi chỉ có một function. Khi thêm function thứ hai, quy tắc route hoặc selection có thể thay đổi. Không viết integration test chỉ dựa trên root path nếu production có nhiều bean.

### 14.2. 404 và lỗi converter là hai lớp khác nhau

HTTP 404 thường liên quan mapping hoặc route; HTTP 4xx/5xx vì không parse được body có thể xảy ra **sau khi function được chọn**. Cần xem exception/trace của request để phân biệt.

Không lập tức thêm `@RestController` để chữa vấn đề: như vậy là dùng một cơ chế HTTP khác và có thể che lỗi cấu hình của Spring Cloud Function web adapter.

## 15. Nguyên nhân: Spring Cloud Stream dùng sai definition hoặc binding

Ví dụ bean:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Cấu hình Stream:

~~~properties
spring.cloud.function.definition=uppercase

spring.cloud.stream.bindings.uppercase-in-0.destination=orders-in
spring.cloud.stream.bindings.uppercase-out-0.destination=orders-out
~~~

Ở đây:

- `uppercase`: function name.
- `uppercase-in-0`: tên binding input theo convention.
- `uppercase-out-0`: tên binding output.
- `orders-in`, `orders-out`: destination thực tế ở broker.

Một consumer không nhận message có thể do binder không kết nối, quyền truy cập topic, tên destination hoặc serializer, dù `uppercase` đã nằm trong catalog.

### 15.1. Ba phép kiểm tra độc lập

1. **Catalog:** `getNames(null)` có `uppercase`?
2. **Binding:** log khởi động có tạo đúng `uppercase-in-0`/`uppercase-out-0`?
3. **Transport:** destination, consumer group, partition, credential và network có hoạt động?

Đừng sửa tên bean chỉ vì topic sai. Cũng đừng lookup tên `orders-in` thay vì `uppercase`.

### 15.2. Composition làm đổi convention của binding

Nếu definition là `uppercase|reverse`, adapter sử dụng **tên composition** theo quy tắc binding thay vì hai function độc lập. Trong ứng dụng có nhiều definition, property `;` lại mang ý nghĩa khác.

Chẩn đoán dựa trên tên binding thực được ghi trong startup logs và tài liệu binder/version, không suy ra chắc chắn chỉ bằng tên một bean riêng.

### 15.3. Message conversion là bước sau lookup

Nếu function nhận `OrderEvent` nhưng broker gửi byte[] hoặc JSON có header không phù hợp, lỗi converter có thể xảy ra ngay khi binding gửi message vào wrapper. Hàm có thể vẫn được tìm thấy hoàn toàn chính xác.

Kiểm tra input generic type, `contentType`, DTO, serializer/deserializer và message header trước khi thay bean name.

## 16. Nguyên nhân: serverless handler và business function bị nhầm tên

Trên AWS Lambda hoặc môi trường serverless tương tự, cần phân biệt:

- **Handler/entry point** do nền tảng gọi.
- **Business function** trong `FunctionCatalog`.
- **Property lựa chọn/routing** function sẽ chạy.

Với AWS Lambda adapter của SCF, một handler thường dùng là `org.springframework.cloud.function.adapter.aws.FunctionInvoker`. Tên đó **không phải** business bean `uppercase`.

### 16.1. Quy trình kiểm tra

1. Handler/entry point của deployment có đúng với loại adapter đã đóng gói?
2. Artifact và phiên bản deploy có chứa class function?
3. Profiles/conditions trong runtime có tạo bean không?
4. Catalog của runtime có liệt kê đúng tên không?
5. Khi có nhiều function, `spring.cloud.function.definition` hoặc routing instructions có chỉ target đúng không?
6. Event được deserialize và chuyển vào function đúng kiểu không?
7. Timeout và memory của runtime có đủ để khởi động Spring context và thực thi không?

Một invocation thất bại trước lúc tạo context không thể chữa bằng việc đổi tên business function.

## 17. Nguyên nhân: nhầm RoutingFunction với target function

SCF có router với tên chuẩn `functionRouter`. Nó có thể chọn một function khác qua routing instructions:

- `spring.cloud.function.definition`.
- `spring.cloud.function.routing-expression`.
- Routing callback hoặc header trong các trường hợp được hỗ trợ.

Router được tìm thấy **không đồng nghĩa target đã tồn tại**. Nếu routing expression resolve thành `upprcase` còn catalog chỉ có `uppercase`, đó là lỗi **target selection**.

### 17.1. Chẩn đoán router theo hai lượt

**Lượt 1:** `catalog.lookup("functionRouter")` có mặt không và ứng dụng có bật routing phù hợp không?

**Lượt 2:** routing instruction thực tế sẽ tạo tên gì, có trong `getNames(null)` không, function target có kiểu đầu vào/đầu ra tương thích không?

Đừng chỉ nhìn log “router invoked” rồi kết luận business function đã chạy.

### 17.2. Reactive routing khác routing theo từng message

Với imperative `Function<T,R>`, framework có thể route theo message header nếu cấu hình hỗ trợ. Với reactive `Function<Flux<T>,Flux<R>>`, đơn vị lời gọi thường là **toàn stream**; tài liệu SCF yêu cầu routing instructions ở application properties cho reactive function, thay vì đổi function theo header từng phần tử.

Nếu cố gắn `spring.cloud.function.definition` vào từng message trong một Flux dài hạn để chọn function khác nhau, bạn có thể đang dùng sai mô hình, không phải function bị mất khỏi catalog.

## 18. Lookup thành công nhưng invocation lỗi là vấn đề khác

Nếu:

~~~java
Function<String, String> f =
    catalog.lookup(Function.class, "uppercase");
~~~

trả function hợp lệ nhưng gọi `apply` lỗi, hãy khoanh vùng **sau catalog**.

| Giai đoạn | Triệu chứng | Cần kiểm tra |
| --- | --- | --- |
| Input conversion | JSON/bytes không thành DTO | Generic type, Content-Type, converters |
| Java invocation | Exception trong lambda hoặc service | Business logic và dependency |
| Reactive execution | `apply(flux)` trả publisher nhưng chưa chạy | Có subscription không? |
| Output conversion | Không serialize được DTO | Output type và converter |
| HTTP adapter | Response lỗi/timeout | Mapping, status, stream lifecycle |
| Stream binder | Không gửi/ack message | Binder và transport |
| Serverless runtime | Invocation timeout | Deadline, routing, context và I/O |

### 18.1. Wrapper từ catalog không nhất thiết cùng instance với bean

Không kiểm tra bằng identity:

~~~java
// Không phải hợp đồng bắt buộc của Spring Cloud Function:
// assertSame(context.getBean("uppercase"), catalog.lookup("uppercase"));
~~~

Kiểm tra hành vi:

~~~java
Function<String, String> f =
    catalog.lookup(Function.class, "uppercase");

assertThat(f).isNotNull();
assertThat(f.apply("hello")).isEqualTo("HELLO");
~~~

`assertThat` ở đây là AssertJ dùng trong test.

### 18.2. Reactive function phải được subscribe

~~~java
Function<Flux<String>, Flux<String>> normalizeStream =
    catalog.lookup(Function.class, "normalizeStream");

Flux<String> output =
    normalizeStream.apply(Flux.just(" A ", " B "));
~~~

Với nguồn Reactor cold, `apply` có thể chỉ tạo pipeline. Cần subscriber để toán tử xử lý dữ liệu.

~~~java
StepVerifier.create(output)
    .expectNext("A", "B")
    .verifyComplete();
~~~

Không coi việc `doOnNext` chưa log là bằng chứng catalog không có function khi publisher chưa được subscribe.

## 19. Sơ đồ quyết định chẩn đoán

~~~mermaid
flowchart TD
    A["Function không hoạt động"] --> B{"Context có catalog?"}
    B -->|Không| C["Dependency / autoconfiguration / startup"]
    B -->|Có| D{"catalog.getNames có tên?"}
    D -->|Không| E{"ApplicationContext có bean?"}
    E -->|Không| F["@Bean / scan / @Import / profile / condition"]
    E -->|Có| G["Kiểu / registration / ineligible filter"]
    D -->|Có| H{"Lookup đúng tên và loại?"}
    H -->|Không| I["Tên sai / fallback / composition"]
    H -->|Có| J{"Gọi trực tiếp thành công?"}
    J -->|Không| K["Type conversion / exception / subscription"]
    J -->|Có| L["HTTP mapping / binder / serverless routing"]
    C --> Z["Xác minh lại"]
    F --> Z
    G --> Z
    I --> Z
    K --> Z
    L --> Z
~~~

### 19.1. Quy trình thao tác theo thứ tự

1. Xem exception đầu tiên, không chỉ log cuối cùng.
2. Xác nhận đang chạy đúng artifact, profile và phiên bản dependency.
3. Kiểm tra `FunctionCatalog` có mặt trong context.
4. Liệt kê `catalog.getNames(null)` và `catalog.size()`.
5. So tên mong đợi với bean thực trong `ApplicationContext`.
6. Nếu thiếu bean, sửa registration/scan/condition.
7. Nếu có bean nhưng thiếu catalog, sửa type/registration/filter.
8. Nếu tên có trong catalog, thử lookup từng function và typed lookup.
9. Nếu dùng composition, thử các thành phần riêng rồi mới thử definition tổng.
10. Tắt fallback ở test để tên sai không vô tình chạy function duy nhất.
11. Gọi function trực tiếp bằng input đúng kiểu.
12. Cuối cùng mới kiểm tra HTTP, Stream binder hoặc serverless runtime.

## 20. Kiểm thử catalog bằng SpringBootTest

Test sau dựa trên `DiagnosticsApplication` ở mục 3 (hai function và một supplier):

~~~java
package demo.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = DiagnosticsApplication.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=false"
    }
)
class CatalogLookupTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void expectedBeanIsExposedByCatalog() {
        assertThat(context.containsBean("uppercase")).isTrue();

        assertThat(catalog.getNames(null))
            .contains("uppercase", "reverse", "greeting");

        Function<String, String> uppercase =
            catalog.lookup(Function.class, "uppercase");

        assertThat(uppercase).isNotNull();
        assertThat(uppercase.apply("hello")).isEqualTo("HELLO");
    }

    @Test
    void wrongNameIsNotSilentlyAccepted() {
        assertThat(catalog.getNames(null))
            .doesNotContain("upprcase");

        assertThat(catalog.lookup("upprcase")).isNull();
    }

    @Test
    void compositionFindsBothParts() {
        Function<String, String> combined =
            catalog.lookup(Function.class, "uppercase|reverse");

        assertThat(combined).isNotNull();
        assertThat(combined.apply("hello")).isEqualTo("OLLEH");
    }
}
~~~

Các giả định cần đáp ứng:

- Test có Spring Boot Test, Spring Cloud Function và AssertJ tương thích.
- `DiagnosticsApplication` được sử dụng làm context test; không vô tình load một application class khác.
- Hai function có tên đúng và kiểu `String → String`.
- Với kiểu `Message<?>` hoặc reactive signature, cách chuẩn bị input và assert output phải thay đổi phù hợp.

### 20.1. Kiểm thử riêng lớp HTTP/binder

Catalog test thành công **không chứng minh** HTTP route hay Stream binding đúng.

Bổ sung kiểm thử:

| Tầng | Mục tiêu test |
| --- | --- |
| Spring context | Bean được tạo với đúng tên/type |
| Catalog | `getNames` và `lookup` đúng, tên sai bị từ chối |
| Composition | `a|b` được tạo và chạy đúng |
| Web adapter | Method, path, Content-Type, status, body |
| Spring Cloud Stream | Function definition, binding names, message conversion |
| Broker integration | Destination, delivery/ack/retry theo binder |
| Serverless | Handler, event payload, selection, timeout |
| Reactive | Subscription, `onNext`, `onComplete`/`onError` |

Một test với nhiều function tốt hơn chỉ kiểm tra trong môi trường duy nhất có một function, vì nó làm lộ lỗi bị single-function fallback che mất.

## 21. Actuator và logging hỗ trợ chẩn đoán

Tài liệu Spring Cloud Function mô tả endpoint Actuator `functions` nếu ứng dụng có web/Actuator dependency phù hợp và endpoint được expose.

Ví dụ cấu hình trong môi trường được bảo vệ:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

Sau đó có thể thử:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

Kết quả có thể liệt kê tên và metadata các function trong catalog. Tuy nhiên:

- Actuator **không mặc định có mặt** chỉ vì `FunctionCatalog` tồn tại.
- Management port, base path và security có thể thay đổi URL.
- Endpoint không thể truy cập **không chứng minh** catalog rỗng.
- Không expose endpoint nhạy cảm ra Internet chỉ để debug.

### 21.1. Logging mức DEBUG có kiểm soát

~~~properties
logging.level.org.springframework.cloud.function=DEBUG
logging.level.org.springframework.cloud.stream=DEBUG
~~~

Chỉ bật khi thực sự cần, giới hạn thời gian và theo dõi khối lượng log. Log debug có thể chứa dữ liệu liên quan message; tránh ghi payload, headers hoặc credentials không cần thiết.

### 21.2. Những điều không nên làm

- Không xóa mọi `ineligible-definitions` để đưa cả function nội bộ ra public.
- Không tắt security hoặc mở HTTP function endpoints vô hạn cho mục đích thử nghiệm.
- Không sửa đồng thời scan, name, definition, binding và converter.
- Không dùng `catalog.lookup(null)` làm test xác nhận **một tên cụ thể**.
- Không kết luận function đã chạy vì `lookup` không null khi chưa có test invocation/subscription.
- Không nhầm tình trạng broker chưa có message với catalog không tìm thấy bean.

## 22. Bảng khắc phục nhanh theo nguyên nhân

| Vấn đề | Bằng chứng | Hành động |
| --- | --- | --- |
| Spring không có bean | `containsBean` false | Thêm/sửa `@Bean`, scan, import và condition |
| Tên bean bị đổi | Context có `normalizeOrder` nhưng caller tra `uppercase` | Sửa tên được chọn hoặc naming contract |
| Function scan bị tắt | Class chỉ dựa trên SCF component scan | Kiểm tra `spring.cloud.function.scan.enabled` |
| Bean type không rõ | Declared type `Object` hoặc proxy không như dự kiến | Dùng type `Function<I,O>` rõ ràng |
| Functional registration sai | Registration thiếu tên hoặc metadata | Kiểm tra `FunctionRegistration` và startup mode |
| Function bị loại | `ineligible-definitions` chứa tên | Chỉnh exclusion có chủ đích |
| Fallback che tên sai | Lookup typo vẫn thành công khi chỉ có một hàm | Tắt fallback trong test, sửa tên |
| Composition hỏng | Một mắt xích thiếu hoặc type không tương thích | Lookup và test từng bước |
| HTTP 404 | Catalog lookup OK nhưng URL không có mapping | Web module, path, method, security |
| Stream không nhận event | Bean OK, binding/transport sai | Definition, destination, binder |
| Lambda không route | Catalog OK nhưng runtime chọn sai | Handler và deploy config |
| Converter lỗi | Lookup OK, exception khi deserialize | Generic type, contentType, DTO |
| Flux không chạy | `apply` trả publisher, không ai subscribe | Caller/adapter subscription |
| Chỉ production lỗi | Profile, artifact, env override khác local | So cấu hình runtime theo bằng chứng |

## 23. Các câu hỏi tự đánh giá

1. `ApplicationContext.getBean(...)` và `FunctionCatalog.lookup(...)` khác nhau thế nào?
2. Một phương thức Java trả `Function` nhưng không có `@Bean` có chắc được catalog tìm thấy không?
3. Vì sao `@SpringBootApplication` nằm ở package quá sâu có thể khiến configuration ngoài package không được load?
4. Cách Spring component scan và SCF Function Component Scan khác nhau ở điểm nào?
5. Với `@Bean("normalizeOrder")` trên method tên `uppercase()`, tên nào là tên tra cứu đúng?
6. Vì sao `catalog.lookup("upprcase")` đôi khi trả một function dù tên đó chưa từng được đăng ký?
7. Property nào tắt single-function fallback?
8. `spring.cloud.function.definition=uppercase|reverse` và `uppercase;reverse` khác nhau thế nào?
9. Context có function bean nhưng catalog không có tên thì cần kiểm tra gì?
10. `spring.cloud.function.ineligible-definitions` ảnh hưởng catalog thế nào?
11. Tại sao broker destination `orders-in` không phải tên lookup của function `uppercase`?
12. Catalog có `uppercase` nhưng HTTP `/uppercase` 404: cần kiểm tra những tầng nào?
13. Catalog lookup OK nhưng Spring Cloud Stream không nhận event: nên kiểm tra definition, binding hay bean name trước?
14. Khi serverless báo target không tồn tại, làm thế nào phân biệt handler và business function?
15. Vì sao router tìm thấy nhưng target function vẫn có thể vắng mặt?
16. Một `Function<Flux<T>,Flux<R>>` chưa được subscribe có thực hiện các callback của nguồn cold không?
17. Vì sao message conversion lỗi không nên được chữa bằng đổi tên function?
18. Test nào xác nhận tên function thật mà không bị single-function fallback che mất?
19. Nếu actuator `/actuator/functions` trả 404, điều đó có chứng minh catalog rỗng không?
20. Những thông tin nào không nên ghi vào log khi chẩn đoán production?

## 24. Tài liệu tham khảo

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): cách đăng ký và lookup function, `spring.cloud.function.definition`, composition, fallback, exclusion, routing và function scan.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html): functional registration, `FunctionRegistration`, thông tin kiểu.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html): HTTP mapping, path và selection của web adapter.
- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): handler và routing trên serverless.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): chọn function, nhiều function, binding và message transport.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): cơ chế scan và bean registration.

Tài liệu minh họa phương pháp chẩn đoán trên một ứng dụng Spring Boot/Spring Cloud Function. Kiểm tra version/BOM, dependency, profile và adapter của dự án thật trước khi sử dụng một cấu hình cụ thể. Ví dụ unit test không thay thế integration test cho HTTP, binder hoặc serverless.

**Ghi nhớ:** Để tìm nguyên nhân **“Không tìm thấy hàm trong FunctionCatalog”**, kiểm tra theo thứ tự: **ApplicationContext có bean → FunctionCatalog có tên thực → lookup đúng tên và loại → definition/composition hợp lệ → adapter chọn đúng function → invocation có dữ liệu đúng kiểu**. `catalog.getNames(null)` là bằng chứng hữu ích, còn single-function fallback có thể che lỗi chính tả. Một HTTP 404, binding không nhận message hay lỗi converter không tự chứng minh catalog thiếu function. Chẩn đoán từng ranh giới giúp sửa đúng nguyên nhân mà không làm hỏng những function, route và binding khác.
