# @BindParam khi binding trong Spring MVC hoặc WebFlux

**`@BindParam`** là annotation của Spring Framework để **chỉ định tên giá trị đầu vào** mà Spring phải tìm khi **gắn dữ liệu vào tham số constructor** của model attribute. Nó đặc biệt hữu ích khi tên trường do client gửi lên khác tên tham số Java, ví dụ HTTP form dùng `full-name` còn constructor khai báo `fullName`.

Annotation thuộc package **`org.springframework.web.bind.annotation.BindParam`**, xuất hiện từ **Spring Framework 6.1**, có thể đặt trên **constructor parameter** hoặc **field tương ứng với constructor parameter**. Spring MVC và Spring WebFlux đều hỗ trợ trong cơ chế constructor binding của `@ModelAttribute`.

Ví dụ ngắn nhất:

~~~java
public final class CustomerForm {
    private final String firstName;

    public CustomerForm(@BindParam("first-name") String firstName) {
        this.firstName = firstName;
    }

    public String getFirstName() {
        return firstName;
    }
}
~~~

Đây là **đoạn class minh họa**, cần import `org.springframework.web.bind.annotation.BindParam` và đặt trong dự án Spring Web tương thích. Với input có khóa `first-name=Lan`, Spring dùng `first-name` để tìm giá trị cho tham số constructor Java `firstName`. **Không bắt buộc** phải sửa tên field, đổi tên getter hoặc thêm setter.

Bài này tập trung vào ngữ nghĩa, cách dùng và giới hạn của `@BindParam` trong **constructor binding của Spring MVC/WebFlux**, không nhầm nó với `@RequestParam` hay annotation JSON.

## 1. Vì sao cần @BindParam?

Trong thực tế, hai phía có quy ước đặt tên khác nhau:

| Nơi xuất hiện | Ví dụ |
| --- | --- |
| Trường HTML | `<input name="first-name">` |
| Query/form parameter | `first-name=Lan` |
| Tham số Java constructor | `String firstName` |
| Tên Java property | `firstName` |

Không có ánh xạ tên tùy chỉnh, Spring thường tìm input cùng tên **`firstName`** theo metadata của tham số constructor. Nếu chỉ gửi `first-name`, đối số `firstName` có thể không nhận được giá trị mong muốn.

Khi viết:

~~~java
public CustomerForm(@BindParam("first-name") String firstName) {
    this.firstName = firstName;
}
~~~

ta khai báo rõ: “Đối với tham số Java `firstName`, hãy **tìm giá trị đầu vào tên `first-name`**”.

Sơ đồ:

~~~text
HTTP request                  Constructor binding                Java object
--------------                -------------------                -----------
full-name=Lan       ------>   @BindParam("full-name")    ---->    fullName="Lan"
age=23              ------>   int age (tên mặc định)    ---->    age=23
                                      |
                                      +-- ConversionService chuyển "23" → 23
~~~

Lợi ích chính là **tách tên bên ngoài (wire format) khỏi tên đối số bên trong Java**. Đây là một cơ chế ánh xạ tên khi bind, **không** tự kiểm tra dữ liệu hợp lệ, không áp dụng phân quyền và không đổi tên field JSON cho Jackson.

## 2. Đặt @BindParam ở đâu?

Khai báo annotation về bản chất:

~~~java
@Target({ElementType.PARAMETER, ElementType.FIELD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface BindParam {
    String value() default "";
}
~~~

Khối trên **minh họa hình dạng annotation theo Javadoc**, không phải mã nguồn cần tự tạo. Hãy import annotation từ Spring:

~~~java
import org.springframework.web.bind.annotation.BindParam;
~~~

Hai vị trí chính:

### 2.1. Trên constructor parameter — cách rõ ràng nhất

~~~java
public class ProductForm {
    private final String displayName;
    private final int quantity;

    public ProductForm(
            @BindParam("display-name") String displayName,
            @BindParam("qty") int quantity) {
        this.displayName = displayName;
        this.quantity = quantity;
    }

    public String getDisplayName() {
        return displayName;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Input phù hợp là `display-name=Sach&qty=2`, thay vì mặc định `displayName=Sach&quantity=2`.

Đoạn class ở trên cần import `BindParam` và được dùng như một `@ModelAttribute` trong Spring Web; bản thân class **không tự nhận request**. Có thể chỉ annotate những tham số cần đổi tên; với tham số còn lại, Spring dùng tên Java có sẵn nếu có thể khám phá.

### 2.2. Trên field tương ứng

Spring cũng hỗ trợ đặt `@BindParam` ở **field có tên tương ứng với tham số constructor**:

~~~java
public final class AddressForm {
    @BindParam("postal-code")
    private final String postalCode;

    public AddressForm(String postalCode) {
        this.postalCode = postalCode;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Khối này cần import `BindParam`. Cách viết này giữ constructor gọn khi nhiều tham số phải map theo tên bên ngoài. Tuy nhiên để Spring đối chiếu field với tham số constructor, tên tham số Java phải xác định được; nên biên dịch với `-parameters` hoặc dùng kiểu record/metadata tương thích.

### 2.3. Với Java record

Java 17 hỗ trợ record, rất phù hợp với một DTO nhận đầu vào bất biến:

~~~java
public record ProfileForm(
        @BindParam("given-name") String givenName,
        int age) {
}
~~~

Đây là **đoạn khai báo record minh họa**; cần import annotation Spring. Java cho phép annotation có target `FIELD`/`PARAMETER` ở vị trí record component khi phù hợp và chuyển annotation sang thành phần được sinh tương ứng. Trong constructor binding của Spring, `given-name` ánh xạ đến `givenName`.

Khi record có **canonical constructor tự định nghĩa**, nhiều constructor hoặc quy tắc tạo object đặc biệt, cần kiểm tra Spring chọn đúng constructor và annotation được đặt ở nơi framework có thể đọc. Với trường hợp phức tạp, đặt annotation trực tiếp trên tham số của constructor được sử dụng sẽ dễ kiểm soát hơn.

**Nguyên tắc:** `@BindParam` đặt tại **tham số/field dùng để xây object**, không phải tùy ý trên một setter để đổi tên property binding. Nó cũng **không phải** annotation đặt trên controller method parameter để thay thế `@RequestParam`.

## 3. Luồng xử lý của Spring MVC và Spring WebFlux

Trong controller dùng annotation, cơ chế điển hình:

1. Spring xác định argument có `@ModelAttribute` (hoặc được suy ra là model attribute trong những trường hợp phù hợp).
2. Tìm model object đã có trong model/session hoặc chuẩn bị khởi tạo object từ constructor phù hợp.
3. Với **constructor binding**, xác định tên của từng constructor argument. Tên mặc định đến từ metadata Java; `@BindParam("...")` có thể thay tên lookup.
4. Đọc giá trị đầu vào theo tên này từ dữ liệu request phù hợp.
5. Dùng conversion/formatter để chuyển kiểu, ví dụ `"23"` thành `int 23`.
6. Gọi constructor để tạo instance khi dữ liệu và quá trình khởi tạo cho phép.
7. Theo cấu hình mặc định, Spring còn có thể tiếp tục **property binding** bằng setter vào model; có thể hạn chế bằng `setDeclarativeBinding(true)`.
8. Nếu có validation được cấu hình và kích hoạt, Spring thực hiện bước validation; lỗi binding/validation được biểu diễn qua `BindingResult` hoặc exception tương ứng.

**Quan trọng:** `@BindParam` chỉ ảnh hưởng đến **bước tra tên cho constructor argument**, không làm nhiệm vụ của `ConversionService`, `Validator`, `DataBinder` hay `BindingResult`.

### Những nguồn request được mô hình thuộc tính xem xét

Tài liệu Spring MVC mô tả `@ModelAttribute` có thể gắn dữ liệu từ **request parameters** (bao gồm query/form), **URI path variables** và **request headers** theo cơ chế tương ứng; request parameters được ưu tiên so với path/header khi có cùng tên. WebFlux cũng hỗ trợ form data, query parameters, URI variables và headers, ưu tiên form/query khi trùng tên.

Dù giá trị cụ thể đến từ nguồn nào, `@BindParam("first-name")` chỉ định **khóa cần tìm**, không cam kết “chỉ được phép lấy từ form body”. Nếu ứng dụng có yêu cầu nghiêm ngặt về nguồn dữ liệu, nên thiết kế API và kiểm soát input rõ ràng, không dùng `@BindParam` như một bộ giới hạn nguồn.

## 4. Ví dụ hoàn chỉnh: Spring MVC, Java 17, form URL-encoded

Ví dụ xây endpoint **`POST /signup`** nhận hai thông tin:

- Client gửi `full-name`; constructor Java nhận `fullName` nhờ `@BindParam`.
- Client gửi `age` dạng chuỗi; Spring chuyển sang `int`.
- DTO là class immutable, chỉ có constructor và getter.
- `BindingResult` đứng ngay sau `@ModelAttribute` để controller chủ động xử lý lỗi.
- `@InitBinder` bật `setDeclarativeBinding(true)` để ưu tiên constructor binding, không property bind tùy tiện.

### 4.1. Maven project

Ví dụ dưới đây ghim **Spring Boot 3.5.16** với Java **17**. Boot quản lý Spring Framework 6.2 và các dependency web liên quan. Nếu dự án đang ở bản Boot 4 thì dùng starter MVC và BOM tương ứng với nhánh đó, không ghép tùy tiện library major.

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>bindparam-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`maven.compiler.parameters=true` giúp giữ metadata tên tham số constructor trong bytecode. Spring Boot parent vốn hỗ trợ cấu hình compiler phù hợp, nhưng khai báo tường minh giúp người học thấy rằng tên constructor argument cần được tìm ra. Phần `age` không có `@BindParam` nên phụ thuộc tên `age` trong metadata.

### 4.2. Toàn bộ mã Java

Tạo file `src/main/java/example/BindParamApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.BindParam;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@SpringBootApplication
public class BindParamApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindParamApplication.class, args);
    }

    // Request DTO bất biến: không có setter.
    public static final class SignupForm {
        private final String fullName;
        private final int age;

        public SignupForm(
                @BindParam("full-name") String fullName,
                int age) {
            this.fullName = fullName;
            this.age = age;
        }

        public String getFullName() {
            return fullName;
        }

        public int getAge() {
            return age;
        }
    }

    @RestController
    static class SignupController {

        @InitBinder("signupForm")
        void configure(WebDataBinder binder) {
            // Constructor binding luôn chạy; property binding bị hạn chế.
            binder.setDeclarativeBinding(true);
        }

        @PostMapping(
                value = "/signup",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
        ResponseEntity<String> signup(
                @ModelAttribute("signupForm") SignupForm form,
                BindingResult result) {

            if (result.hasErrors()) {
                String fields = result.getFieldErrors().stream()
                        .map(error -> error.getField())
                        .distinct()
                        .sorted()
                        .collect(Collectors.joining(","));
                return ResponseEntity.badRequest()
                        .body("INVALID: " + fields);
            }

            return ResponseEntity.ok(
                    "OK: " + form.getFullName() + " (" + form.getAge() + ")");
        }
    }
}
~~~

**Vì sao đây là chương trình hoàn chỉnh?** File chứa class `BindParamApplication` có `main`, DTO `SignupForm` và controller `SignupController` là class lồng tĩnh được Spring quét như controller. Phần import, package, dependency và đường dẫn file đã được cung cấp đầy đủ.

Cần đọc kỹ các dòng quan trọng:

- `@BindParam("full-name") String fullName`: chỉ định tên request dùng để tìm giá trị cho tham số `fullName`.
- `int age`: không có alias; Spring tìm tên `age`, rồi chuyển kiểu `String` thành `int`.
- `@ModelAttribute("signupForm")`: xác định **tên model attribute** là `signupForm`, **khác** tên input `full-name`.
- `BindingResult result` phải **đứng ngay sau** tham số `@ModelAttribute` tương ứng, nhằm nhận lỗi trong cùng một lần binding.
- `setDeclarativeBinding(true)`: chặn property binding tự do theo setter khi không khai báo allowed fields; constructor binding vẫn là cơ chế tạo DTO.
- Đối tượng `SignupForm` không có setter; vì thế sau khi tạo, `fullName` và `age` không thể bị sửa theo property binding truyền thống qua các setter của class này.

### 4.3. Chạy ứng dụng và thử request

Cấu trúc:

~~~text
bindparam-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── BindParamApplication.java
~~~

Từ thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i -X POST "http://localhost:8080/signup" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "full-name=Lan" \
  --data-urlencode "age=23"
~~~

Khối lệnh curl trên dùng kiểu xuống dòng của shell Unix. Trên PowerShell có thể viết một dòng bằng `curl.exe`; trên Command Prompt cũng dùng một dòng.

Kết quả mong đợi: HTTP **200 OK**, response body do chương trình tạo ra:

~~~text
OK: Lan (23)
~~~

Giải thích: `"full-name"` khớp alias `@BindParam`, `age` khớp tên constructor param mặc định; Spring chuyển `"23"` thành `int 23` và tạo `SignupForm("Lan", 23)`.

Nếu thay request bằng:

~~~bash
curl -i -X POST "http://localhost:8080/signup" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "full-name=Lan" \
  --data-urlencode "age=abc"
~~~

thì giá trị `abc` không thể chuyển sang `int` với converter mặc định. Spring ghi nhận một **binding/type-conversion error** cho `age`. Trong những cấu hình mà controller tiếp tục nhận `BindingResult` hợp lệ, ví dụ trả HTTP 400 với tên field lỗi thay vì xử lý nghiệp vụ như dữ liệu tốt. Đừng phụ thuộc vào message nội bộ/exception text vì có thể khác theo phiên bản/cấu hình. Hãy kiểm tra `result.hasFieldErrors("age")` và mã `typeMismatch` trong test để xác nhận hành vi cụ thể.

**Không nhầm binding với validation:** ví dụ này chỉ cho thấy ánh xạ tên và chuyển kiểu. Dữ liệu `age=15` chuyển kiểu thành công, dù nghiệp vụ có thể yêu cầu đủ 18 tuổi. Muốn kiểm tra tuổi phải có validator/constraint phù hợp.

## 5. Cùng DTO trong Spring WebFlux

`@BindParam` không chỉ dành cho Spring MVC. Spring WebFlux dùng **cùng annotation** và cơ chế `@ModelAttribute` để ánh xạ constructor argument từ form/query/path/header.

Với ví dụ ở trên, có thể chuyển sang **Spring WebFlux annotated controllers** bằng cách sử dụng `spring-boot-starter-webflux` thay cho `spring-boot-starter-web` trong `pom.xml` (giữ **một** web starter phù hợp mục tiêu, không thêm cả hai rồi giả định Boot chắc chắn chọn reactive server). Ví dụ thay đúng một dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Giữ nguyên `BindParamApplication`, `SignupForm` và phương thức controller nhận model attribute **không bọc reactive type**:

~~~java
@PostMapping(
        value = "/signup",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<String> signup(
        @ModelAttribute("signupForm") SignupForm form,
        BindingResult result) {
    // Cùng cách xử lý form và BindingResult như ví dụ MVC.
}
~~~

**Đây là trích đoạn** của phương thức đã được cung cấp ở phần 4, không phải file Java độc lập. Trong WebFlux, mặc dù server xử lý non-blocking, controller annotated **có thể** dùng đối số model attribute trực tiếp để xử lý form đơn giản. `@BindParam("full-name")` vẫn ánh xạ tên trong constructor.

### WebFlux với Mono<SignupForm> khác gì?

WebFlux còn cho phép khai báo model attribute ở dạng reactive wrapper:

~~~java
@PostMapping("/signup-reactive")
Mono<ResponseEntity<String>> handle(
        @ModelAttribute("signupForm") Mono<SignupForm> formMono) {
    return formMono
            .map(form -> ResponseEntity.ok(
                    "OK: " + form.getFullName()))
            .onErrorResume(
                    org.springframework.web.bind.support.WebExchangeBindException.class,
                    error -> Mono.just(
                            ResponseEntity.badRequest().body("INVALID")));
}
~~~

Đoạn này **chỉ minh họa cách xử lý reactive**, cần được đặt trong WebFlux controller, import `reactor.core.publisher.Mono` và các annotation/http type tương ứng. Với **reactive wrapper**, không đặt `BindingResult` ngay sau `Mono<SignupForm>` theo cách của đối số không bọc: lỗi binding/validation được xử lý **trên reactive pipeline**. Khi không dùng wrapper, có thể dùng `BindingResult` ngay sau `@ModelAttribute` như MVC.

**Khác biệt cần nhớ:**

| Trường hợp | MVC | WebFlux |
| --- | --- | --- |
| Alias constructor qua `@BindParam` | Có | Có |
| `@ModelAttribute Form form, BindingResult errors` | Có | Có khi dùng form không bọc reactive type |
| `@ModelAttribute Mono<Form> formMono` | Không phải mẫu đối số model thông thường của MVC | Có; lỗi được xử lý trong pipeline |
| Binding errors không được xử lý qua `BindingResult` | Thường `MethodArgumentNotValidException` | Thường `WebExchangeBindException` |
| Thực hiện validation thêm `@Valid`/`@Validated` | Có khi có provider/config phù hợp | Có khi có provider/config phù hợp |

Loại exception thực tế còn phụ thuộc điều kiện lỗi và method validation khác đang được kích hoạt. Không nên bắt một class exception duy nhất rồi kết luận đó là tất cả các tình huống validation trên cả hai web stack.

## 6. @BindParam khác những annotation nào?

Những annotation gần tên nhau thực hiện những nhiệm vụ **không giống nhau**:

| Annotation/API | Dùng ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `@BindParam("full-name")` | Constructor param/field của model object | Chọn **tên lookup** cho đối số **constructor binding** |
| `@ModelAttribute("signupForm")` | Tham số controller, method | Đặt/đọc **model attribute**, kích hoạt data binding theo cấu hình |
| `@RequestParam("full-name")` | Tham số controller | Đọc **một request parameter** trực tiếp vào tham số handler |
| `@PathVariable("userId")` | Tham số controller | Lấy biến từ URL path theo route template |
| `@RequestBody` | Tham số controller | Đọc body qua `HttpMessageConverter`/codec, ví dụ JSON |
| `@JsonProperty("full-name")` | Field/getter/setter/constructor/record tùy Jackson | Chỉ định tên property **trong JSON serialization/deserialization** |
| `@Valid` / `@Validated` | Model argument/điểm validation phù hợp | Yêu cầu **validation**, không đổi tên input |
| `@InitBinder` | Phương thức trong controller/advice | Cấu hình WebDataBinder như editor, formatter, allowed fields, declarative binding |

### Ví dụ @RequestParam — không phải constructor binding

~~~java
@PostMapping("/hello")
String hello(@RequestParam("full-name") String fullName) {
    return "Hello " + fullName;
}
~~~

Trên đây là **trích đoạn controller method**, cần import `@PostMapping` và `@RequestParam`. Đây là cách map input thẳng vào tham số **handler method**, không phải ánh xạ một tham số trong constructor của DTO. Đặt `@BindParam` ở tham số handler này không phải cách thay thế `@RequestParam`.

### Ví dụ @RequestBody JSON

~~~java
@PostMapping("/json")
void submitJson(@RequestBody SignupJsonBody body) {
    // Xử lý body được giải mã từ JSON.
}
~~~

Đây là **trích đoạn** cần định nghĩa `SignupJsonBody`. Nếu body JSON là `{"full-name":"Lan"}`, Jackson cần cấu hình tên JSON tương ứng, chẳng hạn `@JsonProperty("full-name")` hoặc naming strategy. Chỉ gắn `@BindParam("full-name")` lên tham số constructor của DTO **không bảo đảm** Jackson dùng annotation đó khi deserialization JSON.

Câu hỏi chọn API: “Giá trị đi **trực tiếp** vào tham số controller hay vào **constructor của model attribute**?” — trực tiếp dùng `@RequestParam` phù hợp; constructor DTO qua `@ModelAttribute` có thể dùng `@BindParam`.

## 7. Compiler parameter names và các constructor đặc biệt

### 7.1. Tại sao -parameters quan trọng?

Trong Java, nếu project không giữ tên tham số constructor trong bytecode, reflection có thể chỉ thấy những tên như `arg0`, `arg1`. Spring cần biết tên các tham số **không có alias** để tra dữ liệu request; Spring hiện đại dựa vào runtime-retained parameter names.

Với Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Đây là **trích đoạn cấu hình Maven**, cần đặt trong `<build><plugins>...</plugins></build>` của `pom.xml`, không phải XML hoàn chỉnh. Với Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đây là **trích đoạn Gradle Groovy DSL** dùng trong `build.gradle`. Dự án Spring Boot thường đã cấu hình phù hợp thông qua plugin/BOM, nhưng nếu build riêng hoặc dùng công cụ tùy chỉnh, cần kiểm tra bằng `javap -v` hoặc test thực tế.

Với **record**, thông tin thành phần record có sẵn trong class file. Tuy nhiên nên kiểm thử cả tên không có alias, annotation trên component/field và constructor được Spring chọn.

### 7.2. Nhiều constructor

Constructor binding cần xác định constructor phù hợp để tạo object. Tài liệu Spring nêu: class nên có **một public constructor** hoặc **một non-public constructor có tham số**; nếu có nhiều constructor và có default constructor, default constructor có thể được chọn. Vì vậy:

~~~java
class MixedForm {
    MixedForm() { /* ... */ }

    MixedForm(@BindParam("display-name") String displayName) {
        /* ... */
    }
}
~~~

Đây là **mẫu minh họa lựa chọn constructor**, không phải DTO hoàn chỉnh. Không nên nghĩ rằng chỉ thêm `@BindParam` vào bất kỳ overload nào thì Spring bắt buộc sử dụng overload đó. Hãy thiết kế một constructor rõ ràng cho request DTO hoặc kiểm thử chiến lược khởi tạo đang dùng.

### 7.3. Field alias khi tên tham số không được tìm thấy

Annotation trên **field** không tự thay cho mọi metadata của constructor. Spring vẫn phải liên hệ đúng field với constructor parameter. Nếu code đã được compile bằng một pipeline không giữ parameter names, hãy ưu tiên annotation tường minh trên constructor parameter và sửa cấu hình compiler; đừng cho rằng field alias luôn khắc phục được mọi trường hợp thiếu metadata.

## 8. Nâng cao: nested objects, collection và tùy biến resolver

Constructor binding của Spring có thể xây dựng object lồng nhau từ request keys có **đường dẫn**:

~~~text
customer.name=Lan
customer.address.city=Hue
items[0].sku=BOOK-01
items[0].quantity=2
~~~

Ví dụ tên đường dẫn trên chỉ minh họa dạng input; chúng không thuộc `SignupForm` ở phần 4. Với một constructor parameter kiểu object phức tạp, Spring có thể tiến hành **recursive constructor binding** nếu có thông tin kiểu, constructor và đường dẫn tương ứng.

Theo Spring Reference, constructor binding còn hỗ trợ `List`, `Map` và array từ một giá trị chuỗi (ví dụ chuỗi phân tách bằng dấu phẩy), hoặc từ các key indexed/mapped như `accounts[2].name` hay `accounts[KEY].name`.

Dùng `@BindParam` cho một alias sẽ đổi **tên được dùng để lookup** ở điểm tương ứng; hãy test rõ cả nested prefix và các key thực tế, không giả định alias tự thay đổi mọi tên property bên trong object graph.

### Dùng DataBinder.NameResolver khi muốn chính sách đặt tên chung

Nếu có quy tắc chuyển tên hệ thống, ví dụ `firstName` ↔ `first-name` cho hàng trăm constructor arguments, có thể cấu hình một **`DataBinder.NameResolver`** thay vì viết `@BindParam` riêng cho từng field. Spring cung cấp API `setNameResolver(...)` trên `DataBinder`.

Tuy nhiên, lựa chọn này phức tạp hơn: phải thiết kế ưu tiên giữa tên mặc định, annotation và quy tắc tùy chỉnh; kiểm thử cả MVC/WebFlux và khả năng tương tác với nested paths. Không nên tạo một resolver quá rộng nếu chỉ cần hai hoặc ba alias tường minh.

## 9. Security: constructor binding không đồng nghĩa tự động an toàn tuyệt đối

Spring có hai cơ chế cơ bản:

- **Constructor binding:** dữ liệu đi vào các constructor argument mà object công khai, thường là một phạm vi xác định rõ.
- **Property binding:** dữ liệu được ghi qua các setter/property sau khi object được tạo.

Mặc định, với `@ModelAttribute`, **cả hai có thể được áp dụng**. `@BindParam` chỉ đổi tên một constructor argument, **không tự vô hiệu hóa setter binding** và cũng không thay kiểm tra quyền.

Để giới hạn property binding, Spring 6.1+ có:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Đây là **đoạn trích controller/advice**. Khi `declarativeBinding=true`, constructor binding vẫn được thực hiện, còn property binding không chạy trừ khi có cấu hình `allowedFields` thích hợp. Nếu cần property binding với setter, dùng allowlist cụ thể:

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "phone");
}
~~~

Đây cũng là **trích đoạn độc lập về cấu hình**, không phải lời khuyên cho DTO `SignupForm` immutable (vì DTO đó không có setter). Lưu ý `setAllowedFields` kiểm soát **property binding**, không phải là danh sách lọc constructor parameters. Với constructor binding, hãy thiết kế DTO/constructor chỉ nhận những field được phép từ request.

**Một số quy tắc cần tuân thủ:**

1. Không bind trực tiếp entity chứa `role`, `isAdmin`, `ownerId` hay thuộc tính nhạy cảm chỉ vì class có getter/setter.
2. Dùng request DTO chuyên biệt, giữ các field do server kiểm soát **ngoài** constructor dành cho request.
3. Xác thực danh tính và quyền thao tác tại service/security layer; `@BindParam` không thực hiện authorization.
4. Giới hạn kích thước input, collection growth và độ sâu nested graph; constructor binding có thể nhận collection/nested object.
5. Phân biệt lỗi binding/type conversion với lỗi validation nghiệp vụ và báo lỗi phù hợp.

## 10. Validation và xử lý lỗi

`@BindParam` **không mang một ràng buộc `@NotBlank` hay `@Min`**. Nếu muốn kiểm tra đầu vào, cần thêm Jakarta Bean Validation provider hoặc Spring Validator và kích hoạt quá trình kiểm tra:

~~~java
public static final class SignupForm {
    private final String fullName;
    private final int age;

    public SignupForm(
            @BindParam("full-name") String fullName,
            int age) {
        this.fullName = fullName;
        this.age = age;
    }
}
~~~

Đoạn trên minh họa việc map tên; để thêm validation, có thể thiết kế field/record constraint phù hợp, thêm starter validation tương ứng và dùng `@Valid @ModelAttribute` trên controller. Không cần thêm `@Valid` chỉ để `@BindParam` hoạt động.

Khi dùng MVC:

~~~java
@PostMapping("/signup")
String handle(@Valid @ModelAttribute SignupForm form,
              BindingResult errors) {
    if (errors.hasErrors()) {
        return "signup-form";
    }
    return "signup-success";
}
~~~

Đây là **đoạn trích controller kiểu trả view**, cần import `@Valid` và các annotation; view template, DTO và provider phải được cấu hình. Đặt `BindingResult` ngay sau argument cần kiểm tra. Nếu không có `BindingResult` phù hợp, một số lỗi có thể được đưa ra dưới dạng `MethodArgumentNotValidException` trong MVC. Với WebFlux dạng unwrapped `@ModelAttribute`, cũng có thể đặt `BindingResult` ngay sau tham số; với `Mono<Form>`, xử lý lỗi trong pipeline, thường qua `WebExchangeBindException`.

**Binding error khác validation error:**

| Đầu vào | Loại vấn đề | Ví dụ kết quả |
| --- | --- | --- |
| `age=abc`, tham số `int age` | Chuyển kiểu thất bại | `typeMismatch` trong binding result |
| `age=16`, constraint `@Min(18)` | Chuyển kiểu thành công, vi phạm quy tắc | Lỗi validation nếu validator được kích hoạt |
| Thiếu `full-name` với `String fullName` | Giá trị có thể `null` nếu không có ràng buộc phù hợp | Muốn bắt buộc thì cần validation/cơ chế required riêng |
| Client gửi `isAdmin=true` ngoài các tham số của DTO immutable | Không có constructor parameter tương ứng | Không tự tạo field admin; cần chính sách reject unknown/suspicious input riêng nếu ứng dụng yêu cầu |

Không giả định `@BindParam` sẽ tự trả HTTP 400 chỉ vì không tìm thấy khóa được đặt trong annotation. Sự bắt buộc nhập phải được diễn đạt bằng constraint/quy tắc thích hợp.

## 11. Những lỗi thường gặp

### Lỗi 1: Import sai annotation

Đúng:

~~~java
import org.springframework.web.bind.annotation.BindParam;
~~~

Không nhầm với `@RequestParam` hay `@Param` từ thư viện khác. Bản Spring Framework phải hỗ trợ annotation: **6.1+**. Trên hệ thống Spring Framework 5 hoặc 6.0, annotation này không có sẵn.

### Lỗi 2: Dùng @BindParam cho JSON @RequestBody

`@RequestBody` với JSON được giải mã qua HTTP message converter/codec, thường là Jackson. `@BindParam` không phải cấu hình tên JSON; nếu cần `"full-name"` trong JSON map tới `fullName`, kiểm tra `@JsonProperty` hoặc Jackson naming strategy.

### Lỗi 3: Đổi tên @ModelAttribute thay vì tên input

`@ModelAttribute("userForm")` đặt tên object trong model là `userForm`, **không** bắt form gửi `userForm.firstName` và cũng không thay khóa `first-name` khi tra constructor argument. Vai trò của nó khác `@BindParam("first-name")`.

### Lỗi 4: Cho rằng Spring sẽ tự đổi kebab-case thành camelCase

Việc client gửi `first-name` không mặc nhiên đồng nghĩa Spring sẽ tra `firstName` ở constructor parameter. Hãy dùng alias tường minh hoặc một resolver được cấu hình có kiểm thử. Không dựa vào “có vẻ Spring thông minh” khi tên API khác tên Java.

### Lỗi 5: Không giữ parameter names

Khi tham số không có annotation và compiler không lưu metadata, Spring có thể không xác định được tên để lookup. Bật `-parameters`, dùng build plugin phù hợp và kiểm tra class file nếu cần.

### Lỗi 6: Constructor được chọn không phải constructor có annotation

Nếu class có nhiều constructor, thêm alias lên một constructor không được chọn sẽ không tạo ra kết quả mong muốn. Dùng DTO có constructor rõ ràng hoặc record, kiểm thử endpoint thực tế.

### Lỗi 7: Coi @BindParam là validation/authorization

`@BindParam` chỉ map tên. Muốn validate hãy dùng `@Valid`/`@Validated` và constraint thích hợp; muốn bảo mật hãy dùng DTO, `setDeclarativeBinding` và kiểm tra quyền.

### Lỗi 8: Dùng BindingResult sai vị trí hoặc trộn reactive wrapper

Trong MVC và WebFlux **unwrapped form**, `BindingResult` phải đi **liền sau** model attribute tương ứng. Với `Mono<Form>` của WebFlux, không gắn một `BindingResult` bên cạnh như trường hợp unwrapped; hãy xử lý lỗi từ publisher.

### Lỗi 9: Không phân biệt form/query với multipart/JSON

Endpoint nhận `application/x-www-form-urlencoded` qua `@ModelAttribute` khác với endpoint nhận JSON qua `@RequestBody`. Content type và cơ chế đọc request quyết định việc gì được bind. Dùng lệnh curl có `--data-urlencode` và đúng content type khi kiểm thử form alias.

### Lỗi 10: Ghi đè library versions không tương thích

`@BindParam` có từ Spring 6.1; không nên ép riêng `spring-web` mới vào một dự án Spring Boot quản lý các module Spring cũ chỉ để lấy annotation. Hãy nâng **cả stack** theo BOM/nhánh tương thích, xác nhận build và runtime.

## 12. Checklist thực hành và câu hỏi tự kiểm tra

**Checklist trước khi hoàn thành chức năng:**

1. Xác định dữ liệu đến qua `@ModelAttribute` (form/query) chứ không phải JSON `@RequestBody`.
2. Xác định Java constructor được Spring chọn và tên tham số thực tế.
3. Với tên ngoài khác tên Java, gắn `@BindParam("wire-name")` lên constructor parameter hoặc field tương ứng.
4. Giữ metadata `-parameters` cho tham số không có alias, hoặc dùng record/metadata phù hợp.
5. Dùng dedicated immutable request DTO; cân nhắc `setDeclarativeBinding(true)` để hạn chế property binding.
6. Kiểm tra conversion, validation, lỗi và `BindingResult` đúng vị trí; với WebFlux reactive wrapper, xử lý lỗi reactive.
7. Viết test gửi chính xác cả `full-name=Lan` và `fullName=Lan` để biết alias đang được áp dụng theo hợp đồng, thêm test khi thiếu field và type mismatch.
8. Kiểm tra đúng phiên bản Spring Framework tối thiểu 6.1 và không trộn các module Spring khác dòng.

**Câu hỏi:**

1. Vì sao `@BindParam("first-name")` trên constructor parameter khác với `@RequestParam("first-name")` trên handler method?
2. Khi `@ModelAttribute("signupForm")` có `@BindParam("full-name")`, đâu là tên model attribute, đâu là tên giá trị đầu vào?
3. Vì sao một class có setter ngoài phạm vi constructor vẫn cần cân nhắc bảo mật trong `@ModelAttribute` binding?
4. Nếu `age=abc` nhưng tham số constructor là `int age`, vấn đề nằm ở **tra tên** hay **chuyển kiểu**?
5. Với WebFlux và `@ModelAttribute Mono<Form>`, vì sao không thêm `BindingResult` ngay sau `Mono<Form>` như với object thường?
6. Nếu chuyển endpoint từ form sang JSON, `@BindParam` có thay cho `@JsonProperty` được không?
7. Khi nào nên viết riêng `@BindParam` trên từng field và khi nào đáng cân nhắc `DataBinder.NameResolver`?

**Tóm tắt:** `@BindParam` là **bí danh cho tên dữ liệu đầu vào trong constructor binding của `@ModelAttribute`**, có ở **Spring MVC và WebFlux** từ **Spring Framework 6.1**. Nó không đổi tên Java property, không thực thi validation, không thay `@RequestParam` hoặc `@JsonProperty` và không tự bảo vệ ứng dụng khỏi mass assignment. Hãy kết hợp DTO chuyên biệt, kiểm soát property binding, conversion, validation và test request thực tế.

## Tài liệu tham khảo chính thức

- [Spring Framework Javadoc — BindParam](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/annotation/BindParam.html)
- [Spring Framework Reference — Data Binding / Constructor Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework MVC — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework WebFlux — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework MVC — Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html)