# Giới hạn của annotation khi dữ liệu chưa được chuyển đúng kiểu

## 1. Vấn đề: annotation không thể kiểm tra một giá trị mà hệ thống chưa đọc được đúng kiểu

Trong Spring Framework, dữ liệu đầu vào từ HTTP thường bắt đầu dưới dạng chuỗi (form, query, path) hoặc JSON. Trước khi các ràng buộc như **@NotNull**, **@Min**, **@Past**, **@Email**, **@Valid** hoặc **@Validated** có ý nghĩa, Spring phải tạo được đối tượng và các giá trị Java cần thiết. Chuyển kiểu và kiểm tra ràng buộc là **hai trách nhiệm khác nhau**.

Ví dụ, một ứng dụng đăng ký yêu cầu tuổi tối thiểu là 18:

~~~java
public class RegistrationForm {
    @NotNull
    @Min(18)
    private Integer age;

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
}
~~~

Với dữ liệu age = "17", Spring có thể chuyển chuỗi thành **Integer(17)** rồi Bean Validation phát hiện vi phạm **@Min(18)**. Với age = "abc", **Integer** chưa được tạo từ giá trị người dùng gửi; **@Min** không có một số nguyên ẩn bên trong "abc" để đem so sánh. Đây trước hết là lỗi **chuyển kiểu/binding** (hoặc lỗi giải tuần tự JSON), không phải một lỗi “nhỏ hơn 18”.

Cần tránh ba suy luận sai:

- **@Valid không phải bộ chuyển đổi kiểu**: nó kích hoạt validation tại điểm Spring hỗ trợ sau khi dữ liệu được gắn vào đối tượng.
- **@Min không tự phân tích mọi chuỗi số sai định dạng**: kiểu đích và cơ chế chuyển đổi được xác định riêng; nếu chuyển đổi thất bại thì không thể giả vờ giá trị đó là một số hợp lệ để tiếp tục kiểm tra ngưỡng.
- **@NotNull không thay thế kiểm tra định dạng đầu vào**: nếu giá trị không chuyển được, trường Java có thể vẫn null hoặc giữ giá trị mặc định. Tùy cách binding/validation được kích hoạt, lỗi về null có thể xuất hiện cùng lỗi chuyển kiểu; không được vì thế mà bỏ qua lỗi gốc.

Bài học này đặt trong chủ đề **Đối tượng đầu vào** của Spring MVC. Mục tiêu là hiểu rõ annotation nào phụ trách phần nào, chuyện gì xảy ra nếu chuyển đổi thất bại, và cách thiết kế DTO/cách trả lỗi chính xác.

## 2. Phân tách các giai đoạn xử lý

Một luồng thường gặp của **@ModelAttribute** (form/query):

~~~text
HTTP: age=abc
   │
   ▼
Spring tạo/lấy form object
   │
   ▼
WebDataBinder đọc thuộc tính và chuyển String → Integer
   ├── THẤT BẠI → BindingResult ghi lỗi binding/typeMismatch
   └── THÀNH CÔNG → gán Integer vào thuộc tính age
   │
   ▼
Nếu @Valid/@Validated phù hợp: chạy validator trên object đã bind
   │
   ▼
Controller nhận object + BindingResult (nếu khai báo đúng vị trí)
   │
   ▼
Trả phản hồi hoặc xử lý nghiệp vụ
~~~

**Lưu ý về nhánh thất bại:** với **@ModelAttribute**, Spring có thể tiếp tục validate đối tượng đã bind một phần, nhưng validator chỉ nhìn thấy trạng thái Java thực tế của nó; không thể áp dụng ràng buộc số học lên giá trị thô "abc" như thể đó là số nguyên. Một trường có thể có lỗi binding và những lỗi validation liên quan; cần phân loại rõ.

Luồng **@RequestBody JSON** khác:

~~~text
HTTP body: {"age":"abc"}
   │
   ▼
HttpMessageConverter (ví dụ Jackson) đọc JSON → DTO
   ├── THẤT BẠI → HttpMessageNotReadableException; không có DTO hợp lệ
   └── THÀNH CÔNG → DTO chứa giá trị Java
   │
   ▼
@Valid/@Validated (khi có) → lỗi ràng buộc có thể thành
MethodArgumentNotValidException
   │
   ▼
Controller xử lý nếu không có lỗi làm dừng lời gọi
~~~

Không nên coi các ngoại lệ trên là một loại duy nhất. Chính sách ép kiểu của JSON serializer cũng có thể khiến một chuỗi trông giống số được chấp nhận; kết quả phụ thuộc cấu hình. Đối với ví dụ mặc định sau, chuỗi **"abc"** không thể thành số nguyên.

## 3. Những annotation phổ biến làm được gì, và giới hạn ở đâu?

| Thành phần | Vai trò đúng | Giới hạn khi chưa chuyển kiểu |
| --- | --- | --- |
| **@Valid** (Jakarta Validation) | Yêu cầu validation cho đối tượng/đối số ở vị trí được framework hỗ trợ; kích hoạt kiểm tra các ràng buộc bên trong | Không tự biến "abc" thành Integer, không vá lỗi JSON |
| **@Validated** (Spring) | Kích hoạt validation và có thể chọn nhóm ràng buộc (validation groups) | Vẫn cần đối tượng/kiểu đầu vào phù hợp |
| **@NotNull** | Từ chối giá trị Java null khi validator chạy | Không xác nhận chuỗi thô nhập vào có đúng cú pháp số/ngày |
| **@Min**, **@Max**, **@Positive** | Kiểm tra ngưỡng/giá trị số thuộc kiểu mà validator hỗ trợ | Không thay thế bộ phân tích kiểu số của binder/Jackson |
| **@NotBlank**, **@Size**, **@Pattern** | Kiểm tra chuỗi hoặc kiểu dữ liệu được từng constraint hỗ trợ | Không áp dụng tùy ý cho Integer/LocalDate; ghép sai kiểu có thể gây lỗi cấu hình validator |
| **@DateTimeFormat**, **@NumberFormat** | Hướng dẫn format/parse ở những điểm chuyển đổi mà Spring hỗ trợ | Đây là hỗ trợ chuyển đổi, không phải ràng buộc bảo đảm mọi input đều hợp lệ |
| **@JsonFormat** | Chỉ dẫn Jackson giải tuần tự/tuần tự hóa một kiểu JSON trong ngữ cảnh hỗ trợ | Không tự chạy Bean Validation và không sửa JSON lỗi |
| **@ModelAttribute** | Chỉ định dữ liệu binding thành model attribute | Không có nghĩa mọi thuộc tính đều bind thành công |
| **@RequestBody** | Đọc request body qua HttpMessageConverter thành object | Annotation này không tự bảo đảm body tạo được object đúng kiểu |

Ở Spring MVC hiện đại còn có **method validation** cho constraint đặt trực tiếp trên tham số handler. Tùy chữ ký phương thức và phiên bản, lỗi ràng buộc có thể được biểu diễn bằng **HandlerMethodValidationException** thay vì **MethodArgumentNotValidException**. Nhưng việc một tham số **@RequestParam Integer** không thể chuyển từ "abc" vẫn là bài toán chuyển kiểu trước khi kiểm tra ràng buộc số.

### Ví dụ phân biệt ba tình huống

Với thuộc tính **Integer age** có **@NotNull @Min(18)**:

| Giá trị HTTP | Kết quả chuyển sang Integer | Vấn đề chính |
| --- | --- | --- |
| "20" | 20 | Có thể tiếp tục, đáp ứng ràng buộc |
| "17" | 17 | Chuyển kiểu thành công, vi phạm **@Min(18)** |
| "abc" | Không chuyển được | Lỗi conversion/binding hoặc JSON deserialization |
| Rỗng hoặc thiếu | Có thể thành null/tình huống thiếu tham số, tùy nhánh nhận dữ liệu | Kiểm tra null hoặc missing theo hợp đồng từng endpoint |
| "18.5" | Không phù hợp Integer theo bộ chuyển đổi mặc định | Lỗi conversion; không thể chỉ dùng **@Min** để giải thích |

Không suy diễn rằng mọi ô trống tự động sinh lỗi **@NotNull**. Với **@RequestParam(required=true)**, Spring có thể báo thiếu tham số trước khi gọi handler; với **@ModelAttribute**, quy trình khác và còn phụ thuộc kiểu đích, editor/converter, giá trị mặc định.

## 4. Ví dụ Spring Boot chạy được: cùng một DTO, hai nhánh lỗi khác nhau

Ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.5**, **Spring MVC** và **Jakarta Bean Validation**. Phiên bản được cố định để tái hiện kết quả học tập; ứng dụng production cần chọn phiên bản đang được hỗ trợ và rà soát cập nhật bảo mật.

Tạo thư mục:

~~~text
annotation-conversion-demo/
├── pom.xml
└── src/main/java/demo/validation/ValidationLimitsApplication.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>annotation-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

**src/main/java/demo/validation/ValidationLimitsApplication.java**:

~~~java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;

@SpringBootApplication
public class ValidationLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationLimitsApplication.class, args);
    }

    // DTO đầu vào cho cả form và JSON.
    public static class AgeInput {
        @NotNull
        @Min(18)
        private Integer age;

        public AgeInput() {
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }
    }

    @RestController
    public static class DemoController {

        @PostMapping(value = "/form",
                     consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                     produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> form(
                @Valid @ModelAttribute("ageInput") AgeInput input,
                BindingResult errors) {

            // Ưu tiên nhận diện lỗi đổi kiểu trước những lỗi validation
            // có thể đi kèm trên object mới bind một phần.
            boolean typeMismatch = errors.getFieldErrors("age")
                    .stream()
                    .anyMatch(FieldError::isBindingFailure);

            if (typeMismatch) {
                return ResponseEntity.badRequest().body("FORM:TYPE_MISMATCH");
            }
            if (errors.hasErrors()) {
                return ResponseEntity.badRequest().body("FORM:CONSTRAINT");
            }
            return ResponseEntity.ok("FORM:OK age=" + input.getAge());
        }

        @PostMapping(value = "/json",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.TEXT_PLAIN_VALUE)
        public String json(@Valid @RequestBody AgeInput input) {
            return "JSON:OK age=" + input.getAge();
        }
    }

    @RestControllerAdvice
    public static class DemoErrors {

        @ExceptionHandler(HttpMessageNotReadableException.class)
        public ResponseEntity<String> unreadableBody(
                HttpMessageNotReadableException ignored) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body("JSON:UNREADABLE_BODY");
        }

        @ExceptionHandler(MethodArgumentNotValidException.class)
        public ResponseEntity<String> invalidBody(
                MethodArgumentNotValidException ignored) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body("JSON:CONSTRAINT");
        }
    }
}
~~~

Đây là một ứng dụng đầy đủ có phương thức **main**, không phải các đoạn mã rời. **AgeInput** là DTO JavaBean với constructor rỗng và getter/setter để Spring bind form và Jackson đọc JSON. **@NotNull** và **@Min** chỉ có hiệu lực ở bước validation.

Chạy trong thư mục chứa **pom.xml** (cần JDK 17+ và Maven; lần đầu Maven cần tải dependencies):

~~~bash
mvn spring-boot:run
~~~

Mở terminal thứ hai và chạy các yêu cầu sau; lệnh ví dụ sử dụng cú pháp shell Bash. Trên PowerShell, có thể dùng **curl.exe** và điều chỉnh dấu nháy JSON cho đúng shell.

**A. Form có tuổi sai kiểu:**

~~~bash
curl -sS -X POST -d 'age=abc' http://localhost:8080/form
~~~

Nội dung response và mã trạng thái mong đợi:

~~~text
HTTP 400
FORM:TYPE_MISMATCH
~~~

Ở đây bộ bind cố đổi **"abc"** thành **Integer** nhưng thất bại. **BindingResult** chứa ít nhất lỗi binding tương ứng; chương trình chủ động kiểm tra **FieldError.isBindingFailure()** trước các lỗi validation khác.

**B. Form có tuổi đúng kiểu nhưng chưa đủ 18:**

~~~bash
curl -sS -X POST -d 'age=17' http://localhost:8080/form
~~~

~~~text
HTTP 400
FORM:CONSTRAINT
~~~

Lần này **Integer(17)** đã được tạo, và **@Min(18)** phát hiện giá trị không hợp lệ.

**C. Form hợp lệ:**

~~~bash
curl -sS -X POST -d 'age=20' http://localhost:8080/form
~~~

~~~text
HTTP 200
FORM:OK age=20
~~~

**D. JSON có tuổi sai kiểu:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":"abc"}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 400
JSON:UNREADABLE_BODY
~~~

Jackson không tạo được **Integer age** từ chuỗi trên. Spring phát sinh **HttpMessageNotReadableException**, handler phản hồi trước khi phương thức controller có thể nhận một DTO hợp lệ để validate.

**E. JSON đúng kiểu nhưng chưa đủ tuổi:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":17}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 400
JSON:CONSTRAINT
~~~

DTO đã được giải tuần tự thành công; **@Valid** kích hoạt validation và **@Min(18)** không đạt. Trong ví dụ này, Spring ném **MethodArgumentNotValidException**, được **DemoErrors** chuyển thành response dễ nhận biết.

**F. JSON hợp lệ:**

~~~bash
curl -sS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"age":20}' \
  http://localhost:8080/json
~~~

~~~text
HTTP 200
JSON:OK age=20
~~~

Những dòng **HTTP 400/200** ở các khối trên là **mã trạng thái**, không phải nội dung body được in bởi lệnh curl dùng cờ **-sS**. Muốn xem header/status thực tế, thêm cờ **-i**; dòng body là những chuỗi cố định trong source. Nếu server đang dùng cổng khác hoặc được cấu hình Jackson khác, cần chỉnh lệnh và kỳ vọng tương ứng.

## 5. Vì sao cần BindingResult ở đúng vị trí?

Ở nhánh form, tham số nhận dữ liệu và đối tượng nhận lỗi phải đứng sát nhau:

~~~java
@PostMapping("/register")
public String submit(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "register-form";
    }
    return "register-success";
}
~~~

Đây là **đoạn minh họa trong controller MVC có view**, cần định nghĩa **RegistrationForm** và các view tương ứng; không phải một chương trình độc lập.

Nếu bỏ **BindingResult** ngay sau **@ModelAttribute**, Spring MVC có thể phát sinh ngoại lệ thay vì trao lỗi cho controller tự xử lý. Ngược lại, có **BindingResult** thì ta kiểm tra lỗi có cấu trúc:

~~~java
for (FieldError fieldError : result.getFieldErrors()) {
    String field = fieldError.getField();
    boolean conversionFailed = fieldError.isBindingFailure();
    String code = fieldError.getCode();

    // "typeMismatch" là mã lỗi binding thường gặp.
    // Mã constraint có thể là "Min", "NotNull", ...
    // Không trả nguyên văn lỗi nội bộ hoặc giá trị nhạy cảm ra client.
}
~~~

**getFieldError("age")**, **getFieldErrors("age")**, **hasFieldErrors("age")**, **isBindingFailure()** giúp phân biệt rõ:
- lỗi binding: dữ liệu không gán được cho thuộc tính; thường có mã **typeMismatch**;
- lỗi validation: đối tượng/giá trị đã có dạng Java nhưng vi phạm ràng buộc, như **Min**.

Không nên giả định chỉ có một lỗi cho mỗi field. Sau khi bind thất bại, validation vẫn có thể phát hiện vấn đề trên trạng thái Java còn lại (thí dụ null), do đó nên ưu tiên báo lỗi cú pháp/chuyển kiểu trước nếu đó là nguyên nhân gốc. Chỉ dùng **getDefaultMessage()** trực tiếp trong log nội bộ phù hợp, sau khi xét khả năng chứa thông tin không mong muốn; API công khai nên có mã lỗi ổn định và thông báo thân thiện.

## 6. @RequestParam và @PathVariable còn có đường lỗi khác

Một tham số trực tiếp không cần DTO:

~~~java
@GetMapping("/adult")
public String adult(@RequestParam @Min(18) Integer age) {
    return "accepted";
}
~~~

Đoạn trên minh họa chữ ký handler, cần import phù hợp và cấu hình validation cho ngữ cảnh phương thức. Khi người dùng gửi **?age=abc**, Spring phải đổi **String** sang **Integer** để gọi method. Nếu chuyển đổi thất bại, thường gặp **MethodArgumentTypeMismatchException**, và body mặc định của Spring Boot tùy cấu hình. Ràng buộc **@Min(18)** không có cơ hội so sánh tuổi với 18 khi tham số Java chưa tạo được. Nếu gửi **?age=17**, việc kiểm tra ngưỡng phụ thuộc vào method validation đã được kích hoạt và cách cấu hình Spring MVC; với Spring Framework 6.1+, cơ chế tích hợp sẵn có thể sử dụng **HandlerMethodValidationException** cho lỗi constraint trực tiếp trên tham số handler.

Tương tự, một **@PathVariable UUID id** nhận chuỗi không đúng định dạng UUID cũng thất bại tại conversion trước khi controller xử lý. Không áp dụng một cơ chế bắt lỗi duy nhất cho form object, JSON body, query parameter và path variable.

## 7. Muốn kiểm tra định dạng trước khi đổi kiểu thì phải giữ lại dạng thô

Nếu sản phẩm thật sự cần báo lỗi chuyên biệt cho **"abc"**, **"1.5"**, chuỗi có dấu phân tách, hoặc dữ liệu ngày không đúng mẫu, có hai hướng rõ ràng:

**Hướng 1 — Để framework chuyển kiểu và xử lý lỗi chuyển đổi.** DTO dùng **Integer**, **LocalDate** hoặc kiểu miền đúng mục đích, cấu hình Converter/Formatter phù hợp, xử lý lỗi binding/deserialization với thông báo chính xác. Cách này thích hợp khi format đầu vào đơn giản, tiêu chuẩn và không cần giữ nguyên cách người dùng biểu diễn.

**Hướng 2 — Tiếp nhận chuỗi thô rồi xác thực cú pháp trước khi parse.** DTO đầu vào có trường **String rawAge**, đặt constraint phù hợp với String hoặc dùng validator cấp object; sau khi định dạng hợp lệ mới tự parse sang **Integer**/kiểu miền trong lớp xử lý. Cách này hữu ích khi có nhiều kiểu lỗi chi tiết hoặc format miền riêng. Ví dụ độc lập sau dùng **Java 17** để minh họa thứ tự, chưa phụ thuộc vào Spring:

~~~java
public class ParseAfterCheck {
    static int parseAge(String raw) {
        if (raw == null || !raw.matches("[0-9]{1,3}")) {
            throw new IllegalArgumentException("age phải là 1-3 chữ số");
        }
        int age = Integer.parseInt(raw);
        if (age < 18) {
            throw new IllegalArgumentException("age phải từ 18");
        }
        return age;
    }

    public static void main(String[] args) {
        for (String input : new String[] {"abc", "17", "20"}) {
            try {
                System.out.println(input + " -> " + parseAge(input));
            } catch (IllegalArgumentException exception) {
                System.out.println(input + " -> " + exception.getMessage());
            }
        }
    }
}
~~~

Lưu thành **ParseAfterCheck.java**, rồi chạy:

~~~bash
javac ParseAfterCheck.java
java ParseAfterCheck
~~~

Kết quả chuẩn xác:

~~~text
abc -> age phải là 1-3 chữ số
17 -> age phải từ 18
20 -> 20
~~~

Chương trình này tách bước **kiểm tra biểu diễn String** ra khỏi **Integer.parseInt**, và tách kiểm tra ngưỡng sau khi parse. Trong Spring MVC, có thể áp dụng cùng ý tưởng với DTO String + Bean Validation như **@Pattern** (nếu regex phù hợp hợp đồng) và bước ánh xạ sang domain type; không cần gán **@Pattern** lên thuộc tính Integer.

Lưu ý phạm vi của ví dụ: regex chỉ chấp nhận 1–3 chữ số ASCII theo hợp đồng giả định; hệ thống thực phải quyết định rõ khoảng trắng, số âm, chữ số Unicode, độ dài, giới hạn và cách báo lỗi. Tăng độ dài đầu vào hoặc nới regex có thể dẫn đến số vượt giới hạn Integer; khi đó vẫn cần xử lý lỗi parse. Đầu vào thô không đáng tin: đặt giới hạn độ dài request và không log giá trị nhạy cảm.

## 8. Chọn công cụ đúng trách nhiệm

| Nhu cầu | Cơ chế gợi ý | Lý do |
| --- | --- | --- |
| Form/query phải đổi String → số, ngày hoặc kiểu miền | **ConversionService**, **Converter**, **Formatter**, **PropertyEditor** theo phạm vi phù hợp | Xử lý biểu diễn và kiểu đích tại điểm binding |
| Khai báo định dạng ngày/giờ cho binding Spring | **@DateTimeFormat** và formatter tương ứng | Hỗ trợ parse kiểu ngày tại đúng điểm chuyển đổi |
| Đọc JSON vào DTO | **HttpMessageConverter/Jackson**, cấu hình deserializer khi có hợp đồng riêng | Giải quyết lỗi cấu trúc và kiểu dữ liệu của JSON |
| Kiểm tra Integer đã có phải ≥ 18 | **@Min(18)**, **@Valid** | Kiểm tra giá trị sau khi có kiểu phù hợp |
| Kiểm tra chuỗi không rỗng hoặc khớp mẫu | **@NotBlank**, **@Pattern** trên kiểu được hỗ trợ | Phù hợp khi dữ liệu cần giữ dưới dạng String để kiểm tra |
| Kiểm tra quy tắc liên trường/miền | Validator cấp class, custom constraint, tầng nghiệp vụ | Cần ngữ cảnh nhiều trường hoặc trạng thái ứng dụng |
| Báo lỗi từng field của form | **BindingResult** sau **@ModelAttribute** | Giữ thông tin lỗi binding và validation |
| Báo lỗi body JSON không đọc được | Xử lý **HttpMessageNotReadableException** | Không có DTO đúng kiểu để kiểm tra ràng buộc |
| Báo lỗi tham số URL không đổi được kiểu | Xử lý **MethodArgumentTypeMismatchException** và biến thể phù hợp | Tham số handler chưa nhận được giá trị Java |

Một **Converter<String, SomeType>** có thể tự bao gồm bước chuẩn hóa và parse theo hợp đồng của kiểu đích. Tuy nhiên, đừng kỳ vọng **@Valid** hoặc **@Min** tự động gọi converter bất kỳ để cứu một chuỗi đầu vào sai.

## 9. Thiết kế lỗi API theo giai đoạn thay vì theo annotation

Một ứng dụng cần giúp người dùng phân biệt:

- **INPUT_MALFORMED**: body JSON sai cú pháp hoặc không đọc/giải tuần tự được.
- **TYPE_MISMATCH**: giá trị tham số/field không thể đổi thành kiểu khai báo.
- **CONSTRAINT_VIOLATION**: dữ liệu đã ở dạng phù hợp nhưng vi phạm ràng buộc.
- **BUSINESS_RULE**: giá trị hợp lệ về cú pháp nhưng xung đột quy tắc nghiệp vụ cần ngữ cảnh.

Ví dụ thiết kế response cho form age="abc" (minh họa JSON, không phải kết quả của ứng dụng mẫu):

~~~json
{
  "code": "TYPE_MISMATCH",
  "field": "age",
  "message": "Tuổi phải là số nguyên.",
  "status": 400
}
~~~

Với age="17" sau khi chuyển thành Integer:

~~~json
{
  "code": "CONSTRAINT_VIOLATION",
  "field": "age",
  "message": "Tuổi phải từ 18 trở lên.",
  "status": 400
}
~~~

Nên thống nhất nội dung lỗi theo hợp đồng API và test cho từng nhánh; **HTTP 400** có thể phù hợp cho lỗi nhập liệu của người dùng nhưng một ứng dụng cũng cần tuân thủ quy ước lỗi đã công bố. Không trả stack trace, tên class nội bộ, toàn bộ raw payload hoặc giá trị mật khẩu. Với JSON lỗi cấu trúc, đôi khi không có field đáng tin cậy; không cố đoán tên field nếu trình phân tích chưa xác định được.

## 10. Các lỗi thường gặp

1. **“Thêm @Valid sẽ sửa được age=abc”.** Sai: **@Valid** kích hoạt validation; nó không chuyển chuỗi thành số.
2. **“Dùng @Min(18) là đủ để bắt mọi đầu vào tuổi không hợp lệ”.** Sai: còn lỗi chuyển kiểu, thiếu dữ liệu và định dạng raw; thứ tự các bước quyết định loại lỗi.
3. **“Không có lỗi @Min nghĩa là age hợp lệ”.** Sai: có thể chưa có Integer nào được tạo, validation chưa chạy, hoặc lỗi binding đã xảy ra trước.
4. **“@NotNull luôn cho một lỗi duy nhất khi parse thất bại”.** Sai: null là trạng thái Java; Spring có thể ghi riêng lỗi binding và validation, hoặc dừng ngay tại deserialization.
5. **“Dùng @Pattern cho Integer để kiểm tra chữ số”.** Sai về loại dữ liệu kiểm tra. Hãy đặt constraint tương thích lên **String** thô, hoặc để converter báo lỗi parse.
6. **“Form và JSON dùng cùng @Valid thì có cùng exception”.** Sai: WebDataBinder và Jackson có điểm thất bại khác nhau; hành vi còn phụ thuộc handler signature.
7. **“Bắt mọi exception rồi trả ‘không đủ tuổi’”.** Sai: thông báo đánh lạc hướng và che giấu lỗi thật. Hãy phân biệt không đọc được dữ liệu, không đổi được kiểu và không đạt constraint.
8. **“Ép kiểu linh hoạt luôn có lợi”.** Sai: tự ý bỏ ký tự thừa, làm tròn hoặc đổi format có thể biến dữ liệu sai thành dữ liệu khác. Chỉ chuẩn hóa theo hợp đồng công khai.
9. **“Viết DTO domain trực tiếp cho mọi request là tiện nhất”.** Nguy cơ: bind những thuộc tính ứng dụng không muốn khách sửa. Dùng DTO đầu vào được giới hạn rõ và chỉ ánh xạ sang model nghiệp vụ sau khi kiểm tra.

## 11. Checklist thực hành và bài tập

Khi một annotation có vẻ “không hoạt động”, đi lần lượt:

1. **Ghi lại nơi dữ liệu đến**: **@ModelAttribute**, **@RequestBody**, **@RequestParam**, **@PathVariable**, hay binder tự gọi?
2. **Kiểm tra kiểu khai báo** của trường Java, input thô và các converter/deserializer có mặt.
3. **Kiểm tra bước đã thất bại**: đọc body, conversion/binding, Bean Validation, hay quy tắc nghiệp vụ?
4. **Xác nhận validation có được kích hoạt**: **@Valid/@Validated**, validator provider, các constraint đặt trên kiểu phù hợp, và cơ chế method validation nếu đặt constraint trực tiếp trên handler.
5. **Kiểm tra đúng kênh lỗi**: **BindingResult** ngay sau đối số cần bind, hoặc exception handler cho JSON/query/path.
6. **Thử ít nhất ba nhóm dữ liệu**: sai kiểu (age=abc), đúng kiểu nhưng sai ràng buộc (age=17), đúng cả hai (age=20).
7. **Phân loại và công bố lỗi ổn định**; giữ raw giá trị nhạy cảm ngoài response và log công khai.

Bài tập mở rộng: thêm trường **LocalDate birthday** có quy tắc ngày sinh, gửi **birthday=hello**, ngày đúng định dạng nhưng nằm trong tương lai, và ngày hợp lệ. Hãy dự đoán ở mỗi trường hợp lỗi thuộc **bước chuyển đổi** hay **bước validation**, rồi kiểm chứng với **@ModelAttribute**, tiếp đó với JSON **@RequestBody**. Cấu hình format cho mỗi nhánh trước khi kết luận; không giả định Jackson và Spring Formatter chia sẻ cùng chính sách.

## 12. Tài liệu tham chiếu

- Spring Framework Reference – [Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html).
- Spring Framework Reference – [Java Bean Validation và DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
- Spring Framework Reference – [@ModelAttribute trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).
- Spring Framework Reference – [@RequestBody trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).
- Spring Framework Reference – [Type Conversion cho tham số handler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- Spring Framework Reference – [Validation trên controller method](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).

**Nguyên tắc cần nhớ:** annotation kiểm tra ràng buộc trên dữ liệu mà framework đã biểu diễn dưới kiểu phù hợp; khi chuyển kiểu hoặc đọc body thất bại, hãy chẩn đoán và xử lý chính giai đoạn đó. Đừng biến lỗi định dạng thành lỗi nghiệp vụ chỉ vì một annotation không nhận được giá trị mà nó cần.