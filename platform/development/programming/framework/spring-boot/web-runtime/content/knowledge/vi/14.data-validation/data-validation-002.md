# @Valid, @Validated và kiểm tra đối tượng nhận từ HTTP trong Spring Boot

Một HTTP request có thể chứa JSON, form fields, query parameters, path variables hoặc multipart content. **Đọc được request không đồng nghĩa dữ liệu hợp lệ**: JSON có thể đúng cú pháp nhưng tên rỗng, email sai định dạng, tuổi âm hoặc địa chỉ lồng nhau thiếu thông tin. Spring Boot tích hợp Spring Validation và Jakarta Bean Validation để mô tả các ràng buộc này ngay trên kiểu dữ liệu, rồi kiểm tra tại ranh giới HTTP.

Hai annotation cần phân biệt:

- **@Valid** thuộc package jakarta.validation.Valid. Nó yêu cầu kiểm tra theo Jakarta Validation, thường ở **Default group**, và cho phép validation **lan xuống đối tượng lồng nhau** khi đặt trên field/property tương ứng.
- **@Validated** thuộc package org.springframework.validation.annotation.Validated. Đây là annotation của Spring hỗ trợ chọn **validation groups**, dùng cho đối tượng trong MVC/WebFlux và một số trường hợp method validation của Spring.

Trong Spring Framework 6.2, còn có **built-in method validation** của controller: nếu constraint như @NotBlank hoặc @Min nằm trực tiếp trên tham số của một @RequestMapping method, framework có thể kiểm tra toàn bộ tham số bằng cơ chế riêng. Nó không giống hệt kiểm tra một DTO @RequestBody.

Bài trình bày cách khai báo constraints, nested validation, groups, kết quả HTTP, xử lý lỗi và kiểm thử. Ví dụ chạy đầy đủ sử dụng **Java 17+, Spring Boot 3.5.16 và Spring MVC**. Phần cuối phân biệt những khác biệt của WebFlux và WebFlux.fn.

## 1. Ba lớp cần hiểu: binding, validation và business rules

Luồng xử lý một request JSON thông thường:

~~~text
HTTP POST /api/signups
    |
    | Content-Type: application/json
    v
Spring MVC HandlerMapping
    |
    v
HttpMessageConverter (Jackson)
    |
    v
JSON -> SignupRequest (Java record)
    |
    v
Bean Validation
  @NotBlank, @Email, @Min, @Valid ...
    |
    +-- Invalid -> HTTP 400 (theo xử lý mặc định)
    |
    v
Controller -> application service
    |
    v
Business rules, persistence, authorization
    |
    v
HTTP response
~~~

**Binding/deserialization** biến dữ liệu HTTP thành object Java. **Bean Validation** kiểm tra những constraint khai báo trên object. **Business validation** kiểm tra các điều kiện phụ thuộc trạng thái hệ thống hoặc quyền truy cập.

Ví dụ:

- JSON sai cú pháp: parser không tạo được object -> thường 400, nhưng đây **không phải** lỗi @NotBlank.
- JSON hợp lệ với email="abc": object đã tạo, @Email phát hiện sai -> thường 400.
- Email đúng định dạng nhưng đã được đăng ký: phải hỏi database/service -> có thể là 409 Conflict theo API contract, không nên giả định @Email kiểm tra được uniqueness.
- Người dùng định sửa account của người khác: kiểm tra quyền -> thường 403, @Valid không phải cơ chế authorization.

Khi quan sát một response 400, nên phân biệt lỗi parser, type conversion, missing parameter, validation và lỗi nghiệp vụ được map thành 400. Không phải mọi 400 đều phát sinh từ cùng một exception class.

## 2. Dependency bắt buộc và namespace import

Với Spring Boot 3.5.x, để dùng Jakarta Bean Validation trong web app, nên thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Starter này cung cấp Bean Validation provider phù hợp (thường Hibernate Validator) và tích hợp cấu hình với Boot. Chỉ có spring-boot-starter-web không nên được xem là bảo đảm đã có provider. Nếu thiếu provider, chỉ viết annotation trên DTO không bảo đảm request sẽ được kiểm tra.

Những import dễ nhầm:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
~~~

Đối với Spring Boot 3 / Spring Framework 6, dùng **jakarta.validation.***, không lấy ví dụ cũ dùng javax.validation.*. Hai namespace đến từ các thế hệ Java EE/Jakarta EE khác nhau.

@Valid và @Validated không phải hai annotation luôn cần đặt cạnh nhau. Chọn annotation theo mục đích: @Valid cho validation Default và cascade; @Validated khi cần group hoặc Spring method validation phù hợp.

## 3. Bộ constraint phổ biến và khác biệt về null

| Constraint | Áp dụng điển hình | Kiểm tra điều gì? | Điều dễ nhầm |
|---|---|---|---|
| @NotNull | Object, Integer, record component | Giá trị khác null | Không cấm chuỗi rỗng hoặc list rỗng |
| @NotBlank | CharSequence | Không null và có ký tự không chỉ là whitespace | Phù hợp với tên, mã văn bản bắt buộc |
| @NotEmpty | String, Collection, Map, array | Không null và không rỗng | Chuỗi chỉ có dấu cách vẫn không rỗng |
| @Size(min,max) | String, Collection, Map, array | Độ dài/số phần tử | Thường chấp nhận null; ghép @NotNull nếu bắt buộc |
| @Email | Chuỗi | Cú pháp email theo provider | Không xác minh hộp thư có thật; thường chấp nhận null |
| @Pattern(regexp=...) | Chuỗi | Regex cho giá trị | Null thường hợp lệ trừ khi thêm constraint bắt buộc |
| @Min/@Max | Kiểu số phù hợp | Ngưỡng giá trị số | Null thường hợp lệ; với field bắt buộc thêm @NotNull |
| @DecimalMin/@DecimalMax | Kiểu số phù hợp | Ngưỡng thập phân | Cân nhắc BigDecimal cho số tiền |
| @Positive/@PositiveOrZero | Số | Dương / không âm | Không đồng nghĩa có giá trị khi null |
| @Past/@Future và biến thể | Kiểu ngày giờ hỗ trợ | So sánh thời gian | Có thể phụ thuộc ClockProvider và timezone |
| @AssertTrue/@AssertFalse | Boolean | Điều kiện boolean phải đúng/sai | Boolean null thường hợp lệ nếu không thêm @NotNull |
| @Valid | Object hoặc collection elements | Kích hoạt kiểm tra cascade | **Không phải constraint**; không ngăn null |

Ví dụ:

~~~java
public record CreateUserRequest(
        @NotBlank String displayName,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age,
        @Size(max = 120) String bio) {
}
~~~

Ý nghĩa:

- displayName không thể null, "", hoặc chỉ có khoảng trắng.
- email phải khác blank và có định dạng email theo provider.
- age dùng Integer để phân biệt "không gửi giá trị" với 0. @NotNull bắt thiếu; @Min(18) bắt dưới 18.
- bio được phép null, nhưng nếu có giá trị thì giới hạn độ dài 120.

**Lưu ý về primitive:** nếu field age khai báo int, không thể nhận null như Integer; khi JSON thiếu age, giá trị mặc định của primitive hoặc lỗi binding có thể làm yêu cầu khác ý định. Với input DTO, dùng wrapper khi cần phân biệt missing/null.

**Lưu ý về email:** @Email không bảo đảm domain có mailbox, email chưa được đăng ký, hoặc địa chỉ thuộc quyền người dùng. Các bước đó cần flow xác minh riêng.

## 4. @Valid trên @RequestBody kiểm tra object lúc nào?

Với Spring MVC:

~~~java
@PostMapping("/users")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateUserRequest request) {
    userService.create(request);
    return ResponseEntity.status(201).build();
}
~~~

Đây là đoạn minh họa, giả định CreateUserRequest và userService đã được định nghĩa. @RequestBody yêu cầu Jackson/HttpMessageConverter tạo DTO. @Valid làm Spring áp dụng Bean Validation cho DTO được bind.

Khi không có ràng buộc phương thức khác cần method validation, lỗi của DTO thường sinh **MethodArgumentNotValidException**; Spring MVC xử lý mặc định thành **HTTP 400 Bad Request**.

Một số trường hợp không giống nhau:

- **Request body rỗng** trong endpoint yêu cầu @RequestBody (mặc định required=true): thường 400 do thiếu body, trước khi Bean Validation có DTO để kiểm tra.
- **JSON sai cú pháp**: thường HttpMessageNotReadableException / 400; không phải MethodArgumentNotValidException.
- **JSON hợp lệ nhưng @NotBlank fail**: MethodArgumentNotValidException / 400 trong luồng argument validation thông thường.
- **Content-Type không tương thích** với consumes/converter: có thể 415 Unsupported Media Type.
- **@RequestBody thiếu @Valid**: DTO vẫn có thể deserialize thành công, nhưng field constraints không tự được kích hoạt ở đúng bước này.

Với Spring Framework 6.1+, nếu một constraint như @NotBlank được khai báo trực tiếp trên tham số khác của cùng controller method, framework dùng **built-in method validation**; khi đó exception có thể là HandlerMethodValidationException thay vì MethodArgumentNotValidException. Vì vậy, error handler nên bao phủ đúng những loại validation hiện đang dùng.

## 5. Cascade validation: đối tượng lồng nhau

HTTP DTO thường có address, contacts, line items hoặc thông tin sản phẩm lồng nhau:

~~~java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String postalCode) {
}

public record SignupInput(
        @NotBlank String displayName,
        @NotNull @Valid AddressInput address) {
}
~~~

Ở đây:

- @NotNull trên address buộc request phải có đối tượng address.
- @Valid trên address cho phép validate các ràng buộc **bên trong AddressInput**.
- Nếu bỏ @Valid, trường city trống có thể không bị kiểm tra khi validate SignupInput.
- Nếu bỏ @NotNull và address=null, @Valid một mình không làm null trở thành lỗi.

Ví dụ body cần bị từ chối:

~~~json
{
  "displayName": "Lan",
  "address": {
    "city": "",
    "postalCode": "10000"
  }
}
~~~

Khi @Valid được đặt đúng ở field lồng nhau, validator sẽ kiểm tra city và phát hiện @NotBlank fail.

### 5.1. Validation cho phần tử Collection

Bean Validation hỗ trợ các constraint trên **type arguments**:

~~~java
public record BatchInput(
        @NotEmpty List<@NotBlank String> tags,
        @Valid List<AddressInput> addresses) {
}
~~~

- @NotEmpty yêu cầu tags không null và có ít nhất một phần tử.
- List<@NotBlank String> kiểm tra từng chuỗi trong danh sách.
- @Valid List<AddressInput> yêu cầu cascade tới từng AddressInput khi có giá trị.
- Nếu danh sách addresses có yêu cầu bắt buộc và không rỗng, bổ sung @NotEmpty cho chính collection.

Đoạn này minh họa Jakarta Validation 3.x trên Java 17, cần import java.util.List cùng constraint tương ứng.

Tránh dùng @Valid để mong một List luôn có phần tử: @Valid chỉ kích hoạt cascade; số lượng phần tử là trách nhiệm của @NotEmpty hoặc @Size.

## 6. @Validated khác gì với @Valid?

**@Valid** thuộc Jakarta Validation; trường hợp phổ biến là chạy **Default group** và kiểm tra cascade.

**@Validated** của Spring hỗ trợ chỉ định nhóm kiểm tra, ví dụ:

~~~java
@PostMapping("/premium")
public ResponseEntity<Void> premium(
        @Validated({Default.class, PremiumChecks.class})
        @RequestBody SignupRequest body) {
    return ResponseEntity.status(201).build();
}
~~~

Đây là đoạn minh họa trước khi các class đầy đủ được định nghĩa trong dự án ở mục 8. Trong đó:

- Default.class thuộc jakarta.validation.groups.Default.
- PremiumChecks.class là **marker interface** do ứng dụng tự khai báo.
- @Validated({Default.class, PremiumChecks.class}) yêu cầu kiểm tra cả những constraint mặc định lẫn constraint của nhóm PremiumChecks.
- @Validated(PremiumChecks.class) **không tự động bao gồm Default**. Muốn kiểm tra cả hai nhóm, cần chỉ định đủ hoặc thiết kế group inheritance/sequence phù hợp.

### 6.1. Ví dụ constraint theo group

~~~java
public interface PremiumChecks {
}

public record SignupRequest(
        @NotBlank String displayName,
        @NotBlank(groups = PremiumChecks.class)
        String inviteCode) {
}
~~~

Với @Valid @RequestBody, mặc định displayName cần hợp lệ còn inviteCode không bắt buộc theo group mặc định. Với @Validated({Default.class, PremiumChecks.class}) @RequestBody, cả hai ràng buộc được xét.

**Validation groups là kỹ thuật chọn tập quy tắc**, không thay thế API versioning hay kiểm tra quyền. Đừng tạo quá nhiều nhóm theo từng endpoint nếu nó khiến DTO thành một tập điều kiện khó hiểu. DTO riêng cho Create/Update thường đơn giản hơn nếu hai hợp đồng khác nhau rõ rệt.

### 6.2. Group sequence và ràng buộc phức tạp

Jakarta Validation hỗ trợ @GroupSequence để điều khiển thứ tự đánh giá nhóm khi business contract thực sự cần. Nhưng nếu chỉ muốn phân biệt endpoint tạo mới và cập nhật, hãy bắt đầu bằng DTO riêng hoặc một vài marker groups đơn giản. Không dựa vào thứ tự trả lỗi khi không có group sequence cụ thể; nhiều constraint fail có thể được tổng hợp, và thứ tự message không phải hợp đồng ổn định.

## 7. Không đặt @Validated lên controller class theo thói quen

Trong Spring Framework **6.1+**, Spring MVC và WebFlux có **built-in method validation** cho handler methods. Nếu cần ràng buộc trực tiếp tham số controller, ví dụ:

~~~java
@GetMapping("/search")
public List<String> search(
        @RequestParam @NotBlank String keyword) {
    return List.of(keyword);
}
~~~

framework có thể kiểm tra tham số keyword mà **không cần @Validated ở controller class**. Lỗi đầu vào thường sinh **HandlerMethodValidationException** và được map 400.

Đặt @Validated ở mức class có thể kích hoạt đường **AOP method validation** thay vì cơ chế tích hợp của MVC. Điều đó làm exception type, điểm đánh giá constraint và cách xử lý BindingResult khác kỳ vọng.

**Khuyến nghị cho controller trên Spring Framework 6.2:** sử dụng @Valid/@Validated tại tham số DTO; dùng constraint trực tiếp trên @RequestParam hoặc @PathVariable khi cần; **không thêm @Validated ở controller class chỉ để bật method validation**.

Phân biệt trường hợp **Spring service thông thường**: @Validated đặt trên service class vẫn là cách kích hoạt Spring method validation qua proxy cho các phương thức service, với các lưu ý AOP về self-invocation. Đây là một cơ chế khác với built-in handler validation.

## 8. Dự án mẫu chạy được với Java 17+ và Spring Boot 3.5

Dự án minh họa ba tình huống:

1. POST /api/signups: @Valid kiểm tra Default constraints và object AddressInput lồng nhau.
2. POST /api/signups/premium: @Validated chọn Default + PremiumChecks, bắt thêm inviteCode.
3. GET /api/signups/search?keyword=...: @NotBlank trực tiếp trên @RequestParam, dùng built-in method validation của Spring MVC.

Dữ liệu được trả mô phỏng, không ghi database. Test sẽ xác minh HTTP 201, 200, 400 và validation nhóm.

### 8.1. Cấu trúc thư mục

~~~text
validation-http-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/validation/
    │   │   ├── ValidationApplication.java
    │   │   ├── AddressInput.java
    │   │   ├── PremiumChecks.java
    │   │   ├── SignupRequest.java
    │   │   ├── SignupResponse.java
    │   │   └── SignupController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/validation/
            └── SignupControllerTest.java
~~~

### 8.2. pom.xml

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

    <groupId>com.example</groupId>
    <artifactId>validation-http-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Đây là file Maven hoàn chỉnh. Validation starter cung cấp Jakarta Validation provider, nên các annotation trên record thực sự có thể được kiểm tra.

### 8.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: validation-http-demo
~~~

Không cần bật @EnableWebMvc hoặc khai báo custom Validator cho trường hợp mặc định. Spring MVC tự dùng validator có sẵn khi provider ở classpath và Boot auto-configuration phù hợp.

### 8.4. ValidationApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
~~~

Lớp khởi động ở cùng package gốc để component scan tìm các controller khác.

### 8.5. AddressInput.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record AddressInput(
        @NotBlank(message = "city is required")
        String city,

        @NotBlank(message = "postalCode is required")
        @Pattern(
                regexp = "\\d{5}",
                message = "postalCode must have five digits")
        String postalCode) {
}
~~~

@Pattern cho phép null theo hợp đồng constraint; @NotBlank bổ sung yêu cầu phải có giá trị. Quy tắc năm chữ số chỉ là **quy tắc giả định của bài demo**, không đại diện mọi địa chỉ quốc tế. Dự án thật cần quy tắc mã bưu chính theo quốc gia và API contract.

### 8.6. PremiumChecks.java

~~~java
package com.example.validation;

public interface PremiumChecks {
}
~~~

Interface rỗng này chỉ dùng làm **validation group marker**. Nó không cần implementation hay Spring bean.

### 8.7. SignupRequest.java

~~~java
package com.example.validation;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "displayName is required")
        @Size(max = 60)
        String displayName,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @NotNull(message = "age is required")
        @Min(value = 18, message = "age must be at least 18")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        AddressInput address,

        @NotEmpty(message = "interests must not be empty")
        List<@NotBlank String> interests,

        @NotBlank(
                groups = PremiumChecks.class,
                message = "inviteCode is required for premium")
        String inviteCode) {
}
~~~

Điểm cần quan sát:

- Với @Valid, Default constraints yêu cầu displayName, email, age, address, interests.
- AddressInput được validate lồng nhau nhờ @Valid đặt trên component address.
- Các phần tử interests được kiểm tra bằng List<@NotBlank String>.
- inviteCode có constraint thuộc **PremiumChecks**, không tự kích hoạt trong Default group.
- inviteCode được phép null trong request chuẩn; nhưng premium endpoint sẽ yêu cầu trường này.

Không dùng DTO này làm entity JPA hay nơi giữ quyền người dùng. Đây là một object chỉ biểu diễn dữ liệu do client cung cấp.

### 8.8. SignupResponse.java

~~~java
package com.example.validation;

public record SignupResponse(
        long id,
        String displayName,
        String tier) {
}
~~~

Response chỉ có những field ứng dụng chủ động công bố. Nó không trả thẳng toàn bộ request (bao gồm email, age và inviteCode).

### 8.9. SignupController.java

~~~java
package com.example.validation;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.Default;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    @PostMapping
    public ResponseEntity<SignupResponse> standard(
            @Valid @RequestBody SignupRequest input) {

        SignupResponse body = new SignupResponse(
                1L, input.displayName().trim(), "STANDARD");

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @PostMapping("/premium")
    public ResponseEntity<SignupResponse> premium(
            @Validated({Default.class, PremiumChecks.class})
            @RequestBody SignupRequest input) {

        SignupResponse body = new SignupResponse(
                2L, input.displayName().trim(), "PREMIUM");

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @GetMapping("/search")
    public Map<String, String> search(
            @RequestParam @NotBlank String keyword) {

        return Map.of("keyword", keyword);
    }
}
~~~

**Quan trọng:** không có @Validated trên class SignupController. Spring MVC 6.2 có built-in handler method validation khi thấy @NotBlank đặt trực tiếp trên keyword.

Controller chỉ phản hồi dữ liệu mô phỏng. Trong production, nên gọi service, persistence và thiết kế Location header cho tài nguyên vừa tạo. Đừng giả định demo đã tạo account thật.

### 8.10. Các request mong đợi

POST /api/signups với body sau sẽ hợp lệ **dù không có inviteCode**:

~~~json
{
  "displayName": "Lan",
  "email": "lan@example.com",
  "age": 22,
  "address": {
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "interests": ["java", "spring"]
}
~~~

Response HTTP 201, body có dạng:

~~~json
{"id":1,"displayName":"Lan","tier":"STANDARD"}
~~~

Nếu gửi đúng body trên tới **POST /api/signups/premium**, constraint thuộc PremiumChecks sẽ phát hiện thiếu inviteCode và thường trả HTTP 400. Để hợp lệ, thêm:

~~~json
"inviteCode": "PREMIUM-2026"
~~~

vào object JSON đầu vào (phải đặt dấu phẩy hợp lệ nếu bổ sung field). Response premium sau khi valid là 201 với tier=PREMIUM.

GET /api/signups/search?keyword=spring trả 200 và body có keyword="spring". GET /api/signups/search?keyword= chỉ chứa chuỗi rỗng sẽ không qua @NotBlank và được xử lý thành HTTP 400.

## 9. Kiểm thử integration bằng MockMvc

File **src/test/java/com/example/validation/SignupControllerTest.java**:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    private static final String VALID_REQUEST = """
            {
              "displayName": "Lan",
              "email": "lan@example.com",
              "age": 22,
              "address": {
                "city": "Ha Noi",
                "postalCode": "10000"
              },
              "interests": ["java", "spring"]
            }
            """;

    @Autowired
    MockMvc mvc;

    @Test
    void standardAcceptsDefaultConstraints() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tier").value("STANDARD"))
                .andExpect(jsonPath("$.displayName").value("Lan"));
    }

    @Test
    void premiumRequiresGroupSpecificField() throws Exception {
        mvc.perform(post("/api/signups/premium")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST))
                .andExpect(status().isBadRequest());
    }

    @Test
    void premiumAcceptsValidInviteCode() throws Exception {
        String premiumJson = """
                {
                  "displayName": "Lan",
                  "email": "lan@example.com",
                  "age": 22,
                  "address": {
                    "city": "Ha Noi",
                    "postalCode": "10000"
                  },
                  "interests": ["java", "spring"],
                  "inviteCode": "PREMIUM-2026"
                }
                """;

        mvc.perform(post("/api/signups/premium")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(premiumJson))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tier").value("PREMIUM"));
    }

    @Test
    void invalidEmailIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "lan@example.com", "not-an-email")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void underageIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "\"age\": 22", "\"age\": 16")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void nestedCityIsValidated() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "Ha Noi", "")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void blankCollectionElementIsRejected() throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(VALID_REQUEST.replace(
                            "\"spring\"", "\" \"")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void directRequestParamConstraintReturns400() throws Exception {
        mvc.perform(get("/api/signups/search")
                    .param("keyword", " "))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validSearchReturns200() throws Exception {
        mvc.perform(get("/api/signups/search")
                    .param("keyword", "spring"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.keyword").value("spring"));
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/signups")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"displayName\":"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Bộ test phân biệt ba kiểu quan trọng: **Default DTO validation**, **group-specific validation**, và **method parameter validation**. Nó cũng kiểm tra nested object và collection elements.

Chạy:

~~~bash
mvn test
mvn spring-boot:run
~~~

Các test không phụ thuộc database hoặc network bên ngoài. Khi chạy thành công, Maven trả exit code 0. Log, cổng random trong môi trường CI và thứ tự test không phải output cố định.

**Lưu ý QA:** ví dụ HTTP và các class trên được xây dựng nhất quán cho Spring Boot 3.5.16/Java 17; không chuyển trực tiếp sang Boot 4 mà chưa đối chiếu API test package và dependency thay đổi.

## 10. Thử endpoint bằng curl

Chạy Spring Boot ở cổng 8080:

~~~bash
curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  --data '{
    "displayName":"Lan",
    "email":"lan@example.com",
    "age":22,
    "address":{"city":"Ha Noi","postalCode":"10000"},
    "interests":["java","spring"]
  }'
~~~

Kết quả mong đợi: HTTP 201, body JSON với tier=STANDARD.

Đổi email sang chuỗi không phải email:

~~~bash
curl -i -X POST "http://localhost:8080/api/signups" \
  -H "Content-Type: application/json" \
  --data '{
    "displayName":"Lan",
    "email":"invalid-email",
    "age":22,
    "address":{"city":"Ha Noi","postalCode":"10000"},
    "interests":["java"]
  }'
~~~

Kết quả mong đợi: HTTP 400; error body cụ thể phụ thuộc error handling và Problem Details config.

Thử method validation của query parameter:

~~~bash
curl -i "http://localhost:8080/api/signups/search?keyword=spring"
curl -i "http://localhost:8080/api/signups/search?keyword="
~~~

Request đầu trả 200, request thứ hai trả 400. Nếu gửi request thiếu **hẳn** keyword, @RequestParam mặc định required=true cũng có thể trả 400 vì thiếu parameter, đây là lỗi binding khác với giá trị blank vi phạm @NotBlank.

Các lệnh trên phù hợp shell Unix; với Windows PowerShell, dùng curl.exe và điều chỉnh quoting khi cần.

## 11. Hai nhánh validation trong Spring MVC 6.2

Spring Framework 6.2 phân biệt:

**Nhánh A — validate một tham số đối tượng:** @ModelAttribute, @RequestBody hoặc @RequestPart được đánh dấu @Valid/@Validated, không có yêu cầu method validation khác và không có Errors/BindingResult được dùng để xử lý ngay tại method. Lỗi thường là **MethodArgumentNotValidException**.

**Nhánh B — validate ở cấp method:** constraint như @NotBlank, @Min được đặt trực tiếp trên một tham số controller hoặc trên return value. Khi đó built-in method validation có thể kiểm tra cả những tham số DTO lồng nhau thông qua @Valid; lỗi đầu vào thường là **HandlerMethodValidationException**, còn lỗi return-value có thể mang status server error.

| Ví dụ controller parameter | Cơ chế đáng kỳ vọng | Lỗi điển hình |
|---|---|---|
| @Valid @RequestBody SignupRequest body | Argument-level validation | MethodArgumentNotValidException / 400 |
| @Validated(Group.class) @RequestBody SignupRequest body | Argument-level validation theo group | MethodArgumentNotValidException / 400 |
| @RequestParam @NotBlank String keyword | Built-in method validation | HandlerMethodValidationException / 400 |
| @Valid @RequestBody DTO body **và** tham số khác có @Min | Method validation có thể bao phủ cả method | HandlerMethodValidationException / 400 |
| @RequestBody DTO body có JSON sai cú pháp | Message converter không tạo DTO | HttpMessageNotReadableException / 400 |

**@Valid bản thân không phải constraint.** Nếu bạn thêm @NotNull trực tiếp vào tham số cũng đã có @Valid, tình huống có thể chuyển sang method validation. Không tự đổi các annotation chỉ để ép exception đi vào một handler đã viết sẵn; hãy thiết kế handler hỗ trợ các loại lỗi thực tế.

### 11.1. Với @Validated ở cấp class trên controller thì sao?

Trong Spring Framework 6.1+, class-level @Validated có thể khiến method validation chạy qua AOP proxy. Khi đang dùng built-in controller method validation, Spring khuyến nghị bỏ class-level @Validated để tận dụng cơ chế tích hợp. AOP path có thể phát sinh ConstraintViolationException hoặc MethodValidationException tùy configuration; không giả định nó luôn là HandlerMethodValidationException.

Đây là điểm dễ mắc khi nâng cấp từ Spring 5/Boot 2: code cũ gắn @Validated trên controller class theo thói quen có thể cần điều chỉnh để thống nhất error handling ở thế hệ mới.

## 12. BindingResult và xử lý lỗi ngay trong controller

Nếu muốn controller xử lý validation errors thay vì ném exception cho global handler, có thể đặt **BindingResult hoặc Errors ngay sau tham số đã validate**:

~~~java
@PostMapping("/manual-check")
public ResponseEntity<?> create(
        @Valid @RequestBody SignupRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest().body(
                Map.of("message", "invalid request"));
    }

    return ResponseEntity.status(201).build();
}
~~~

Đây là đoạn minh họa rời, cần import BindingResult, ResponseEntity, Map, annotation tương ứng và class SignupRequest; không thuộc SignupController mẫu. Điều kiện quan trọng:

1. BindingResult phải đứng **ngay sau** tham số @Valid/@Validated mà nó xử lý.
2. Nếu không có BindingResult thích hợp, lỗi validation thông thường đi qua exception handling.
3. Nếu method có constraint trực tiếp trên tham số khác và built-in method validation được áp dụng, có những trường hợp controller vẫn không được gọi vì lỗi thuộc tham số không có Errors/BindingResult tương ứng.
4. Tránh vừa xử lý lỗi tại mọi controller vừa tạo một global handler trùng lặp, khiến API trả nhiều format khác nhau.

Với API nhiều endpoint, **@RestControllerAdvice** thường dễ thống nhất hơn; với form cần hiển thị validation errors ngay trong view, BindingResult là công cụ phù hợp.

## 13. Thiết kế error response nhất quán

Khi request không hợp lệ, API cần phản hồi rõ trường nào sai nhưng không tiết lộ dữ liệu không cần thiết. Spring hỗ trợ **ProblemDetail** theo RFC 9457 và cơ chế error responses. Có thể chủ động tạo một schema riêng với error code, field, message và request identifier.

Ví dụ response mang tính **thiết kế**, không phải JSON mặc định bất biến của Spring Boot:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "One or more fields are invalid",
  "invalidFields": [
    {
      "field": "email",
      "message": "email format is invalid"
    },
    {
      "field": "address.city",
      "message": "city is required"
    }
  ]
}
~~~

Lưu ý:

- **MethodArgumentNotValidException** chứa BindingResult/FieldError giúp nhận field và message.
- **HandlerMethodValidationException** biểu diễn kết quả validation của nhiều method parameters; không đơn giản ép về một FieldError duy nhất.
- **ConstraintViolationException** thường xuất hiện khi Jakarta method validation chạy qua AOP hoặc Validator được gọi thủ công; không tự giả định luôn là lỗi HTTP client vì có trường hợp vi phạm invariant nội bộ.
- **WebExchangeBindException** thuộc WebFlux; không import nó vào Spring MVC handler chỉ vì đều kiểm tra @Valid.
- Error body không nên bao gồm rejectedValue nếu đó là password, access token, bí mật hoặc dữ liệu nhạy cảm.

Khi viết @RestControllerAdvice, dùng ResponseEntityExceptionHandler hoặc @ExceptionHandler tương ứng theo đúng version, tránh bắt Exception chung và đổi mọi lỗi server thành HTTP 400.

### 13.1. Không biến return-value validation thành 400

Nếu output do server tạo ra vi phạm constraint (ví dụ controller/service trả dữ liệu không hợp lệ), đó không nhất thiết là lỗi người gọi. Spring Framework có thể dùng **500** cho vi phạm return-value constraint của controller method. Trả 400 cho trường hợp này sẽ khiến giám sát và trách nhiệm sửa lỗi sai lệch.

## 14. @ModelAttribute: dữ liệu từ query/form

Trong Spring MVC, form hoặc query parameters thường được bind thành object bằng @ModelAttribute:

~~~java
public class SearchForm {

    @NotBlank
    private String keyword;

    @Min(1)
    private int page = 1;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}
~~~

Đoạn minh họa cần import jakarta.validation.constraints.NotBlank và Min. Endpoint tương ứng:

~~~java
@GetMapping("/search-form")
public List<String> search(
        @Valid @ModelAttribute SearchForm form) {
    return List.of(form.getKeyword());
}
~~~

Không đặt đoạn minh họa này vào dự án ở mục 8 nếu chưa thêm class và import. Nó cho thấy validation không chỉ áp dụng cho JSON.

**Điểm khác biệt:** @RequestBody dùng HttpMessageConverter để đọc toàn body; @ModelAttribute bind từ request parameters/form fields qua WebDataBinder. Với multipart/form-data, có thể dùng @RequestPart cho một JSON DTO hoặc @ModelAttribute cho form fields tùy kiến trúc.

Đối với file upload:

- FilePart là kiểu reactive WebFlux; MultipartFile thường dùng trong Servlet MVC.
- Annotation validation trên metadata DTO có thể kiểm tra text fields, nhưng size, mime type, nội dung file và malware scanning là công việc bổ sung.
- Không lưu hoặc phục vụ file dựa trên tên client gửi mà thiếu kiểm tra đường dẫn, quyền truy cập và cách lưu an toàn.

## 15. Validation groups: tạo mới, cập nhật và tác động đến Default group

Một kịch bản thường gặp:

- Khi tạo mới, password bắt buộc.
- Khi cập nhật profile, password là tùy chọn.
- Khi tạo premium account, inviteCode bắt buộc.

Có thể dùng groups:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}

public record ProfileInput(
        @NotBlank(
                groups = {CreateChecks.class, UpdateChecks.class})
        String displayName,

        @NotBlank(groups = CreateChecks.class)
        String password) {
}
~~~

Khi endpoint dùng @Validated(CreateChecks.class), nó kiểm tra displayName và password. Khi dùng @Validated(UpdateChecks.class), chỉ displayName cần @NotBlank.

Tuy nhiên:

- Constraint không khai báo groups thuộc Default group.
- Chạy @Validated(CreateChecks.class) không tự chạy những constraint thuộc Default.
- Một số kiểu có yêu cầu hoàn toàn khác giữa create/update thì hai DTO riêng rõ ràng hơn.
- Group sequence/inheritance có thể làm behavior tinh vi hơn; ghi test cho mỗi nhóm được public API sử dụng.

Nếu một DTO có nhiều nhóm đến mức khó hiểu field nào bắt buộc ở endpoint nào, xem lại thiết kế hợp đồng đầu vào.

## 16. Custom constraint khi annotation chuẩn chưa đủ

Có tình huống cần quy tắc như "mã đăng ký phải bắt đầu bằng ACCT-" hoặc kiểm tra quan hệ giữa hai field. Các constraint chuẩn không đủ mô tả mọi business format.

Một custom constraint kiểu Jakarta Validation thường gồm:

1. Annotation khai báo @Constraint, message, groups và payload.
2. Một ConstraintValidator<A,T> định nghĩa isValid.
3. Đăng ký hoặc để provider tìm validator qua annotation.
4. Test dữ liệu hợp lệ, rỗng, malformed và các boundary cases.

Ví dụ annotation và validator độc lập cho String:

**AccountCode.java**

~~~java
package com.example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = AccountCodeValidator.class)
public @interface AccountCode {

    String message() default "account code must start with ACCT-";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

**AccountCodeValidator.java**

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class AccountCodeValidator
        implements ConstraintValidator<AccountCode, String> {

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        return value == null || value.matches("ACCT-[A-Z0-9]{4}");
    }
}
~~~

Đây là một **extension độc lập, chưa được áp dụng vào SignupRequest của dự án mẫu**. Muốn dùng, thêm hai class trên vào cùng package và đặt @AccountCode trên một String field thích hợp, kết hợp @NotBlank nếu field bắt buộc.

Validator trả true cho null vì trách nhiệm "bắt buộc có" nên để @NotBlank/@NotNull kiểm tra riêng; điều này giúp ràng buộc tách bạch và dễ tái sử dụng.

**Không đặt database query chậm hoặc HTTP call đồng bộ vào ConstraintValidator.isValid** để kiểm tra uniqueness theo request khi có thể tránh. Việc đó dễ làm validation tốn tài nguyên, khó kiểm soát transaction/timeouts và vẫn có race condition. Những invariant về uniqueness phải được enforce ở database/service, không chỉ ở validation annotation.

## 17. Method validation ở service khác controller validation

Ngoài HTTP boundary, Spring có thể validate method của service:

~~~java
@Service
@Validated
public class RegistrationService {

    public void reserve(@NotBlank String email) {
        // Logic nghiệp vụ.
    }
}
~~~

Đây là đoạn minh họa. Đối với Spring method validation qua proxy, Spring Boot có thể tự đăng ký infrastructure phù hợp khi Bean Validation provider tồn tại. Tùy configuration, vi phạm có thể sinh ConstraintViolationException hoặc MethodValidationException.

Lưu ý **self-invocation**: khi một method trong cùng object gọi method khác của chính nó, lời gọi có thể bỏ qua Spring AOP proxy nên validation ở mức service không chạy như kỳ vọng. Test nên gọi qua Spring-managed bean/proxy.

Validation HTTP không thay thế validation tại service khi service được gọi từ scheduled job, message listener hoặc test khác. Ngược lại, service method validation không tự bảo đảm response API có error schema hợp lý: cần map các lỗi đáng quy cho input thành 4xx và giữ invariant lỗi hệ thống là 5xx khi thích hợp.

## 18. Spring WebFlux và reactive validation

Spring WebFlux annotated controllers cũng hỗ trợ @Valid/@Validated cùng Jakarta Bean Validation, nhưng chạy trên reactive stack.

Ví dụ minh họa:

~~~java
@PostMapping("/reactive-signups")
public Mono<SignupResponse> register(
        @Valid @RequestBody Mono<SignupRequest> body) {

    return body.map(input ->
            new SignupResponse(
                    1L, input.displayName(), "STANDARD"));
}
~~~

Đoạn này yêu cầu import Mono, các annotation WebFlux/controller và DTO tương ứng; không thuộc dự án Spring MVC mẫu. Spring WebFlux sẽ decode body reactive trước khi kiểm tra theo quy tắc validation của framework.

Các loại lỗi thường gặp:

| Trường hợp | Spring MVC | Spring WebFlux |
|---|---|---|
| @Valid/@Validated trên một object @RequestBody | MethodArgumentNotValidException | WebExchangeBindException |
| Direct constraint trên handler method param | HandlerMethodValidationException | HandlerMethodValidationException |
| Body JSON sai cú pháp | HttpMessageNotReadableException và họ lỗi đọc | ServerWebInputException hoặc lỗi decode tương ứng |
| Method service qua AOP @Validated | ConstraintViolationException hoặc MethodValidationException theo cấu hình | Tương tự về AOP, nhưng phải xét reactive return type và cơ chế validation |

Không gọi block() trong reactive controller chỉ để validate DTO. Validation ở tầng HTTP nên diễn ra theo cơ chế phù hợp với reactive pipeline. Với business checks cần I/O, thực hiện bằng publisher/scheduler thích hợp và map lỗi rõ ràng.

### 18.1. WebFlux.fn và RouterFunction

Functional endpoints nhận ServerRequest và trả Mono<ServerResponse>, ví dụ request.bodyToMono(SignupRequest.class). Không có phương thức controller mang @Valid @RequestBody để framework tự xử lý tương tự annotated controller.

Một handler functional thường cần chủ động dùng Validator:

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(SignupRequest.class)
            .flatMap(input -> {
                Set<ConstraintViolation<SignupRequest>> errors =
                        validator.validate(input);

                if (!errors.isEmpty()) {
                    return ServerResponse.badRequest().build();
                }

                return ServerResponse.ok()
                        .bodyValue(input.displayName());
            });
}
~~~

Đoạn trên là **minh họa nằm trong một handler class có validator đã inject**, không phải file Java độc lập; cần import ServerRequest, ServerResponse, Set, ConstraintViolation và kiểu DTO. Với WebFlux.fn, không được giả định validation tự bật chỉ vì DTO có @NotBlank. Muốn group-specific, dùng validator.validate(input, PremiumChecks.class) hoặc groups cần thiết và tự map response.

Nếu validation cần gọi database theo cách blocking, không nên thực hiện trực tiếp trên event-loop mà phải thiết kế reactive service hoặc cách ly blocking work phù hợp. Validation Bean Validation thông thường nên ưu tiên các kiểm tra thuần CPU, ít tốn thời gian.

## 19. Quốc tế hóa thông báo validation

Mỗi constraint có message; ví dụ:

~~~java
@NotBlank(message = "{signup.displayName.required}")
String displayName
~~~

Có thể tạo **src/main/resources/messages.properties**:

~~~properties
signup.displayName.required=Display name is required
~~~

và **src/main/resources/messages_vi.properties**:

~~~properties
signup.displayName.required=Ten hien thi la bat buoc
~~~

Đây là cách minh họa message bundle; tùy cấu hình MessageSource và Hibernate Validator, việc interpolate thông báo validation với Spring MessageSource có thể cần được kiểm tra trong integration test. Nếu muốn hỗ trợ tiếng Việt có dấu, có thể lưu file resource ở UTF-8 theo thiết lập dự án.

Dữ liệu đầu ra cần được thiết kế ổn định: client có thể cần một **error code** không phụ thuộc ngôn ngữ, còn message được localize. Không dùng text message làm định danh nghiệp vụ vì dịch thuật có thể thay đổi.

## 20. An toàn khi nhận dữ liệu từ HTTP

Validation giúp giảm lỗi dữ liệu, nhưng **không phải công cụ bảo mật đầy đủ**.

- **Mass assignment:** không bind request JSON trực tiếp vào JPA entity có các field role, ownerId, isAdmin hoặc internalStatus. Dùng DTO public chỉ gồm field client được phép đặt.
- **Authorization:** @Valid không kiểm tra người gửi có quyền cập nhật tài nguyên nào; dùng security layer/service.
- **Uniqueness/race condition:** validator kiểm tra email chưa tồn tại không bảo đảm unique nếu hai request chạy cùng lúc; dùng database uniqueness constraint.
- **Sensitive error data:** không đưa rejectedValue của password/token vào ProblemDetail hoặc logs.
- **Body size:** validation chỉ chạy sau khi framework đọc/giải mã được body; request cực lớn cần HTTP body/multipart limits phù hợp.
- **Regex DoS:** pattern quá phức tạp hoặc input không giới hạn có thể tạo rủi ro hiệu năng; giới hạn độ dài và viết regex đơn giản.
- **Normalization:** trim/case-fold dữ liệu theo quy tắc domain trước hoặc sau validation một cách nhất quán; @NotBlank không tự biến "  Lan  " thành "Lan".
- **Secrets in DTO:** không serialize toàn bộ input trở lại response, ngay cả khi validation thành công.
- **JSON unknown fields:** việc cho phép field không biết là quyết định của Jackson/ObjectMapper, khác với Jakarta Validation; có thể cần strict mapping tùy hợp đồng.

Nếu input cần kiểm tra nhiều quy tắc xuyên field (ví dụ startDate <= endDate), có thể viết class-level constraint hoặc validation ở service; đừng mã hóa toàn bộ quy tắc miền nghiệp vụ thành một số lượng annotation khổng lồ khó bảo trì.

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| @NotBlank trên DTO không chặn HTTP request | Thiếu @Valid/@Validated tại @RequestBody hoặc thiếu validation provider | Thêm spring-boot-starter-validation và đặt annotation đúng trên tham số |
| Import javax.validation.* không biên dịch | Dự án dùng Boot 3 / Jakarta namespace | Chuyển sang jakarta.validation.* |
| @Valid trên address nhưng address=null vẫn qua | @Valid không tự cấm null | Thêm @NotNull |
| @Email chấp nhận email=null | @Email chỉ kiểm tra format khi có giá trị | Kết hợp @NotBlank |
| @Min trên Integer vẫn nhận null | @Min thường cho phép null | Kết hợp @NotNull |
| @Validated(CreateChecks.class) bỏ qua @NotBlank mặc định | Group CreateChecks không tự chứa Default | Chỉ định cả Default hoặc thiết kế group inheritance |
| POST premium không yêu cầu inviteCode | Dùng @Valid Default group thay vì @Validated PremiumChecks | Đặt groups đúng và viết test |
| Có @Validated ở controller class và exception khác mong đợi | Spring AOP method validation thay built-in handler validation | Xem lại @Validated ở class; xử lý đúng exception type |
| @RequestParam @NotBlank không được check | Chạy phiên bản framework/cấu hình khác hoặc thiếu provider | Kiểm tra Boot/Framework version và method validation integration |
| JSON sai cú pháp không vào @ExceptionHandler(MethodArgumentNotValidException) | Parser thất bại trước validation | Xử lý HttpMessageNotReadableException riêng |
| BindingResult không nhận lỗi | Không đứng ngay sau tham số @Valid, hoặc method validation khác đang áp dụng | Sửa method signature và xem luật handler method validation |
| Nested list có phần tử blank mà không báo lỗi | Thiếu container element constraint hoặc cascade tương ứng | Dùng List<@NotBlank String>, @Valid cho object elements |
| Error body trả toàn bộ request/password | Error serializer/log chứa rejectedValue | Chỉ xuất field name, error code và safe message |
| Constraint custom có database call chậm | Validation chứa I/O không kiểm soát | Chuyển sang service, timeout và DB constraint |
| WebFlux.fn không chạy @Valid như annotated endpoint | Functional handler không có argument validation tự động tương ứng | Inject Validator và gọi validate rõ ràng |
| Lỗi return-value bị gắn nhãn 400 | Global error advice xử lý quá rộng | Phân biệt lỗi input và invariant server-side |
| Dữ liệu POST hợp lệ nhưng tạo account trùng | Bean Validation không thay uniqueness | Dùng service transaction + database unique index |

## 22. Checklist kiểm thử và review

- [ ] Đúng Java/Spring Boot version và namespace jakarta.validation.*.
- [ ] Đã có Bean Validation provider, thường qua spring-boot-starter-validation.
- [ ] Mỗi HTTP DTO cần validate có @Valid hoặc @Validated tại đúng điểm binding.
- [ ] Các field bắt buộc có @NotBlank/@NotNull/@NotEmpty phù hợp.
- [ ] Với nullable wrappers, ràng buộc null và range được khai báo tách biệt khi cần.
- [ ] Với object lồng nhau, có @Valid trên field/component chứa object và constraint bắt buộc nếu null không hợp lệ.
- [ ] Với collection, có constraint trên cả collection và phần tử khi cần.
- [ ] Validation groups được chỉ định rõ; Default group không bị vô tình bỏ qua.
- [ ] Không đặt @Validated ở controller class chỉ vì muốn built-in method validation.
- [ ] Có test @Valid @RequestBody, @Validated nhóm và direct constraint @RequestParam.
- [ ] Phân biệt lỗi JSON parsing, Content-Type, validation và business rule.
- [ ] Có response schema ổn định với lỗi input, không lộ giá trị nhạy cảm.
- [ ] Không dựa vào một HTTP controller làm điểm kiểm tra duy nhất nếu service còn được gọi từ job/message listener.
- [ ] Có test cho missing, blank, null, boundary min/max, invalid format, nested object và item trong collection.
- [ ] Đã kiểm tra khả năng tương thích với Spring MVC/Servlet hay WebFlux/reactive tương ứng.

## 23. Kết luận

**@Valid** phù hợp cho validation mặc định của một DTO nhận từ HTTP và cho việc kiểm tra lồng nhau. **@Validated** phù hợp khi cần chọn validation groups hoặc kích hoạt cơ chế method validation của Spring ở những bean phù hợp. Với Spring MVC 6.2, cần hiểu sự khác biệt giữa **argument-level validation** và **built-in method validation** để xử lý đúng MethodArgumentNotValidException và HandlerMethodValidationException.

Đường đi đáng tin cậy là: xác định input DTO tối thiểu → khai báo constraints → đặt @Valid/@Validated đúng ở tham số HTTP → kiểm thử request tốt/xấu → chuẩn hóa error response → kiểm tra thêm business rules, authorization và database invariants. Đừng nhầm JSON deserialize thành công với dữ liệu hợp lệ, và đừng dùng Bean Validation để thay toàn bộ business logic.

## Tài liệu chính thức

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Jakarta Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Boot 3.5 — Reference Documentation](https://docs.spring.io/spring-boot/3.5/reference/)
