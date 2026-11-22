# Tạo constraint và ConstraintValidator theo yêu cầu riêng cho Spring Boot Configuration Properties

## 1. Vì sao các annotation kiểm tra sẵn có đôi khi chưa đủ?

Một ứng dụng Spring Boot có thể đọc cấu hình từ `application.yaml`, biến môi trường, Java System properties hoặc đối số `--key=value`. Khi dùng `@ConfigurationProperties`, Binder liên kết những giá trị có hiệu lực vào một đối tượng Java có kiểu.

Ví dụ một dịch vụ xử lý đơn hàng:

~~~yaml
shop:
  store-code: ABC-1024
  batch-size: 200
~~~

Từ góc nhìn kiểu dữ liệu, `store-code` là chuỗi và `batch-size` là số nguyên. Nhưng ứng dụng còn có **quy tắc nghiệp vụ**:

- Mã cửa hàng phải có dạng ba chữ cái in hoa, một dấu gạch ngang và bốn chữ số, ví dụ `ABC-1024`.
- Số lượng phần tử xử lý mỗi lô phải ít nhất là 1.
- Nếu một nhóm cấu hình có `initial-delay` và `max-delay`, khoảng thời gian tối đa phải lớn hơn hoặc bằng thời gian bắt đầu.
- Một URL cấu hình có thể phải dùng HTTPS hoặc thuộc danh sách domain được phép.
- Một nhóm thông số chỉ hợp lệ khi **nhiều field có quan hệ đúng với nhau**, chứ không thể kiểm tra từng field riêng biệt.

Bean Validation cung cấp những constraint sẵn có như `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Size`, `@Pattern` và `@Email`. Khi yêu cầu vượt khả năng diễn đạt rõ ràng của chúng, ta có thể tạo **constraint annotation riêng** và cài đặt **`ConstraintValidator`**.

Bài này giải thích chi tiết cách xây dựng custom constraint trong Spring Boot 3.x dựa trên `jakarta.validation`, tích hợp nó với `@Validated` trên `@ConfigurationProperties`, kiểm tra từng thuộc tính, kiểm tra quan hệ giữa nhiều thuộc tính, hiển thị thông báo lỗi và viết kiểm thử.

## 2. Phân biệt binding và validation trong luồng khởi động

Một cấu hình hợp lệ đi qua nhiều bước:

~~~text
application.yaml / .properties / OS environment / CLI
                         |
                         v
              Spring Environment
                         |
                         v
             @ConfigurationProperties
                         |
                         v
                Spring Boot Binder
          lấy tên khóa, chuyển kiểu dữ liệu
                         |
                         v
         Bean cấu hình được tạo / điền giá trị
                         |
                         v
           Bean Validation nếu được bật
             |                        |
             v                        v
    Constraint hợp lệ          Constraint vi phạm
             |                        |
             v                        v
      Bean sẵn sàng         Khởi động có thể thất bại
             |
             v
      Dependency Injection
             |
             v
           Service
~~~

Ví dụ:

~~~properties
shop.batch-size=abc
~~~

Trong khi Java khai báo `int batchSize`: Binder không chuyển được chữ `abc` thành `int`. Đây là **lỗi chuyển kiểu/binding**, chưa phải việc custom validator quyết định `batchSize` có đủ lớn hay không.

Ngược lại:

~~~properties
shop.batch-size=0
~~~

Binder chuyển `0` thành `int` thành công. Constraint `@Min(1)` có thể xác định giá trị đó **không đáp ứng quy tắc nghiệp vụ**.

Còn:

~~~properties
shop.store-code=abc-1024
~~~

là chuỗi hợp lệ về kiểu dữ liệu, nhưng có thể không phù hợp quy ước chỉ nhận chữ in hoa. Custom `ConstraintValidator` giải quyết trường hợp này.

**Điểm mấu chốt:** Binder chuyển và liên kết giá trị; Bean Validation kiểm tra giá trị sau liên kết. Tạo một constraint không có nghĩa tự tạo bean cấu hình hoặc thay đổi cách chọn nguồn cấu hình.

## 3. Hệ thống Bean Validation trong Spring Boot 3.x

Spring Boot 3.x sử dụng **Jakarta Validation**. Các kiểu chính nằm trong package:

~~~java
jakarta.validation
jakarta.validation.constraints
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `@Constraint` | Đánh dấu một annotation là Bean Validation constraint. |
| `ConstraintValidator<A, T>` | Kiểm tra một giá trị kiểu `T` theo constraint `A`. |
| `ConstraintValidatorContext` | Tạo hoặc điều chỉnh thông báo và đường dẫn lỗi. |
| `@Valid` | Cho phép validation đi vào một object lồng nhau. |
| `@Validated` | Annotation Spring giúp kích hoạt validation theo ngữ cảnh, bao gồm `@ConfigurationProperties`. |
| `Validator` | API Jakarta chạy validation trên object. |
| `ConstraintViolation` | Mô tả một vi phạm: property path, thông báo, giá trị và metadata. |

Trong Spring Boot 3.x, **không** sử dụng import `javax.validation.*` từ các hướng dẫn dành cho Spring Boot 2.x:

~~~java
// Spring Boot 3.x
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
~~~

Lưu ý quan trọng: `@Validated` là annotation của **Spring**:

~~~java
import org.springframework.validation.annotation.Validated;
~~~

Còn `@Valid` là của Jakarta:

~~~java
import jakarta.validation.Valid;
~~~

Hai annotation này khác nhau về vai trò. Trong `@ConfigurationProperties`, `@Validated` kích hoạt kiểm tra bean cấu hình, còn `@Valid` thường dùng để kiểm tra sâu các thành viên lồng nhau.

## 4. Dependency cần thiết

Tạo annotation và cài đặt interface cần Jakarta Validation API. Để thực sự thực thi validation ở runtime, ứng dụng cần một **Bean Validation provider** phù hợp. Một lựa chọn quen thuộc trong Spring Boot là starter validation.

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với Gradle Groovy DSL:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

Nếu dự án đã có provider tương thích thông qua một dependency khác thì không nhất thiết thêm trùng. Nhưng đừng giả định rằng chỉ có `jakarta.validation-api` là đã đủ để constraint được thực thi lúc chạy.

Starter validation thường mang theo Hibernate Validator như một provider. Hibernate Validator ở đây là **công cụ Bean Validation**, không có nghĩa ứng dụng cần dùng Hibernate ORM hay kết nối cơ sở dữ liệu.

Một dự án ví dụ có thể gồm:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── config/
│   ├── StoreProperties.java
│   └── RetryProperties.java
├── validation/
│   ├── StoreCode.java
│   ├── StoreCodeValidator.java
│   ├── ValidRetryPolicy.java
│   └── RetryPolicyValidator.java
└── service/
    └── StoreService.java

src/main/resources/
└── application.yaml
~~~

## 5. Trước khi tạo custom constraint, hãy xem constraint sẵn có

Ví dụ:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
~~~

Một số quy tắc có thể dùng trực tiếp:

~~~java
@NotBlank
String name;

@Min(1)
int batchSize;

@Max(1000)
int maxAttempts;

@NotNull
URI endpoint;

@Size(min = 2, max = 32)
String username;

@Pattern(regexp = "[A-Z]{3}-[0-9]{4}")
String storeCode;
~~~

Nếu chỉ cần kiểm tra một regular expression cố định cho một field, `@Pattern` có thể đã đủ. Custom constraint hợp lý hơn khi:

1. Quy tắc cần đặt một tên có **ý nghĩa nghiệp vụ** rõ ràng, ví dụ `@StoreCode`.
2. Quy tắc được dùng ở nhiều module và cần thay đổi tại một nơi.
3. Quy tắc có tham số riêng, ví dụ giới hạn định dạng hoặc danh sách loại được phép.
4. Cần kiểm tra quan hệ giữa nhiều thuộc tính của cùng object.
5. Cần tạo thông báo lỗi và property path có cấu trúc.
6. Kiểm tra vượt quá một biểu thức regex đơn giản.

Không nên tạo custom validator chỉ để bọc lại một constraint sẵn có mà không mang thêm giá trị về khả năng tái sử dụng hoặc ý nghĩa nghiệp vụ.

## 6. Ví dụ 1 — định nghĩa annotation @StoreCode

Giả sử mã cửa hàng có hợp đồng:

~~~text
ABC-1024  hợp lệ
HCM-2026  hợp lệ

abc-1024  không hợp lệ (chữ thường)
AB-1234   không hợp lệ (hai chữ)
ABCD-1234 không hợp lệ (bốn chữ)
ABC-123   không hợp lệ (ba chữ số)
ABC1234   không hợp lệ (thiếu dấu -)
~~~

Ta tạo một annotation có tên `@StoreCode`.

File `StoreCode.java`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = StoreCodeValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
public @interface StoreCode {

    String message() default
            "mã cửa hàng phải có dạng ABC-1234";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Một Bean Validation constraint annotation cần cung cấp các thành viên chuẩn:

- `message()`: thông báo mặc định nếu vi phạm.
- `groups()`: nhóm validation; mặc định là nhóm mặc định khi không khai báo riêng.
- `payload()`: metadata bổ sung, không phải dữ liệu nghiệp vụ của giá trị đang kiểm tra.

Và cần:

- `@Constraint(validatedBy = StoreCodeValidator.class)` để liên kết annotation với lớp validator.
- `@Retention(RUNTIME)` để metadata được kiểm tra ở runtime.
- `@Target(...)` để xác định annotation có thể đặt ở field, getter, constructor parameter hoặc record component.
- `@Documented` để annotation xuất hiện trong tài liệu JavaDoc khi thích hợp.

### Không nhầm @Constraint với @Validated

`@Constraint` xác định **một loại luật kiểm tra**. `@Validated` trên class `@ConfigurationProperties` giúp **kích hoạt việc kiểm tra** khi Spring Boot xử lý bean cấu hình.

Chỉ tạo annotation `@StoreCode` không làm toàn bộ các field có kiểu String trong ứng dụng tự động bị áp dụng quy tắc này. Chỉ những nơi dùng `@StoreCode` mới chịu điều kiện ấy.

## 7. Cài đặt StoreCodeValidator

File `StoreCodeValidator.java`:

~~~java
package com.example.demo.validation;

import java.util.regex.Pattern;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class StoreCodeValidator
        implements ConstraintValidator<StoreCode, String> {

    private static final Pattern CODE_PATTERN =
            Pattern.compile("[A-Z]{3}-[0-9]{4}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {

        // Null được giao cho @NotNull / @NotBlank.
        if (value == null) {
            return true;
        }

        return CODE_PATTERN.matcher(value).matches();
    }
}
~~~

Ý nghĩa của generic type:

~~~java
ConstraintValidator<StoreCode, String>
                    |          |
                    |          +-- kiểu dữ liệu được kiểm tra
                    +------------- loại constraint annotation
~~~

Phương thức `isValid(...)` trả:

- `true`: giá trị thỏa quy tắc.
- `false`: giá trị vi phạm constraint và provider tạo `ConstraintViolation`.

### Tại sao dùng matches()?

`Pattern.matcher(value).matches()` yêu cầu **toàn bộ chuỗi** phù hợp với biểu thức. Nếu chỉ dùng một thao tác kiểm tra chuỗi con, giá trị như `prefix-ABC-1234-suffix` có thể vô tình được chấp nhận.

### Tại sao null lại trả true?

Đó là một **quyết định thiết kế có chủ ý**: `@StoreCode` kiểm tra **định dạng nếu có giá trị**, còn sự bắt buộc có giá trị nên được diễn đạt bằng `@NotBlank` hoặc `@NotNull`.

Ví dụ:

~~~java
@NotBlank
@StoreCode
String storeCode;
~~~

Khi `storeCode` là `null`:

- `@StoreCode` trả `true` theo quy ước ví dụ.
- `@NotBlank` báo vi phạm vì giá trị bắt buộc.

Khi `storeCode` là chuỗi rỗng, `@NotBlank` và `@StoreCode` đều có thể báo vi phạm. Điều đó không sai về mặt cơ chế; nếu muốn giảm thông báo lặp, bạn có thể cân nhắc thiết kế constraint tổng hợp hoặc điều chỉnh quy tắc. Không nên làm validator âm thầm đổi `null` thành một mã mặc định.

### Không thay đổi giá trị trong isValid

Validator nên tập trung kiểm tra, không tự:

~~~java
value = value.trim().toUpperCase();
~~~

rồi lưu ngược vào object. `isValid` trả Boolean, không phải API chuyển đổi dữ liệu. Nếu muốn chuẩn hóa giá trị trước validation, hãy thực hiện ở bước chuyển đổi hoặc thiết kế cấu hình phù hợp.

## 8. Áp dụng @StoreCode trong @ConfigurationProperties

File `StoreProperties.java`:

~~~java
package com.example.demo.config;

import com.example.demo.validation.StoreCode;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shop")
public record StoreProperties(

        @NotBlank
        @StoreCode
        String storeCode,

        @Min(1)
        int batchSize) {
}
~~~

Tệp `application.yaml`:

~~~yaml
shop:
  store-code: HCM-2026
  batch-size: 200
~~~

Khi bean `StoreProperties` được đăng ký theo cơ chế phù hợp, Spring Boot:

1. Xác định các khóa `shop.store-code` và `shop.batch-size` trong `Environment`.
2. Binder liên kết chúng vào hai thành viên `storeCode` và `batchSize`.
3. Provider Bean Validation kiểm tra `@NotBlank`, `@StoreCode` và `@Min(1)` vì class có `@Validated`.
4. Nếu không có vi phạm, properties bean sẵn sàng để Spring tiêm cho các service.

### Đăng ký bean trong ứng dụng

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Với cấu trúc package ở ví dụ, `StoreProperties` nằm dưới package `com.example.demo` và có thể được phát hiện bởi `@ConfigurationPropertiesScan`.

Một cách khác là đăng ký tường minh:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StoreProperties.class)
public class StoreConfiguration {
}
~~~

Cách này phù hợp khi không dùng scanning hoặc class nằm ngoài phạm vi quét. Nhớ import `org.springframework.context.annotation.Configuration` và `org.springframework.boot.context.properties.EnableConfigurationProperties`.

**Điểm phân biệt:** `@Validated` kích hoạt validation, nhưng không thay thế vai trò đăng ký bean của `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 9. Sử dụng bean cấu hình sau validation

Một service chỉ cần nhận bean qua constructor:

~~~java
package com.example.demo.service;

import com.example.demo.config.StoreProperties;
import org.springframework.stereotype.Service;

@Service
public class StoreService {

    private final StoreProperties properties;

    public StoreService(StoreProperties properties) {
        this.properties = properties;
    }

    public String describe() {
        return "store=" + properties.storeCode()
                + ", batchSize=" + properties.batchSize();
    }
}
~~~

Trong trường hợp thông thường, bean đã được bind và validate trước khi được sử dụng như một dependency hợp lệ. Nếu cấu hình không thỏa constraint và Spring Boot không thể hoàn tất tạo bean cấu hình, context thường không khởi động được.

Cơ chế này hữu ích với những cấu hình *phải đúng trước khi hệ thống phục vụ request*, chẳng hạn mã đối tác, chính sách timeout, phạm vi số lượng, thông số định tuyến hoặc cấu hình broker.

## 10. Điều gì xảy ra khi cấu hình sai?

Thay YAML thành:

~~~yaml
shop:
  store-code: hcm-2026
  batch-size: 0
~~~

Các giá trị đã hợp lệ về kiểu Java:

- `hcm-2026` là chuỗi.
- `0` là số nguyên.

Nhưng vi phạm:

- `@StoreCode` vì mã cửa hàng không có ba chữ hoa đúng định dạng.
- `@Min(1)` vì batch size phải lớn hơn hoặc bằng 1.

Khi Spring Boot bind và validate `StoreProperties`, quá trình khởi tạo có thể báo lỗi với thông tin về prefix `shop`, thuộc tính lỗi, giá trị cấu hình liên quan và constraint vi phạm.

Các exception bọc bên ngoài có thể khác nhau theo phiên bản và ngữ cảnh, chẳng hạn một `ConfigurationPropertiesBindException` chứa nguyên nhân liên quan đến validation. Quan trọng là đọc **đường dẫn thuộc tính** và **thông báo constraint**, thay vì đoán mọi lỗi khởi động đều do dependency injection.

Một quy trình chẩn đoán:

1. Tên bean/configuration properties nào khởi tạo thất bại?
2. Khóa nào không hợp lệ: `shop.store-code` hay `shop.batch-size`?
3. Binding đã thành công về kiểu chưa?
4. Constraint nào báo vi phạm?
5. Giá trị đến từ YAML, biến môi trường, CLI hay nguồn ưu tiên cao hơn?
6. Quy tắc nghiệp vụ của custom constraint có được mô tả đúng trong thông báo không?

Không cần sửa annotation `@ConfigurationProperties(prefix = "shop")` chỉ vì lỗi định dạng mã cửa hàng.

## 11. Tùy biến thông báo lỗi

Annotation đã có thông báo mặc định:

~~~java
String message() default
        "mã cửa hàng phải có dạng ABC-1234";
~~~

Khi sử dụng, có thể ghi đè:

~~~java
@StoreCode(message = "shop.store-code cần dạng HCM-2026")
String storeCode;
~~~

Nội dung message dùng để giải thích quy tắc. Nên viết:

- Ngắn gọn, mô tả kỳ vọng.
- Không đổ lỗi cho người dùng.
- Không in token, password hay dữ liệu nhạy cảm.
- Có ví dụ định dạng hợp lệ khi cần.
- Không giả định mọi môi trường triển khai đều dùng cùng một giá trị cụ thể.

### Sử dụng bundle thông điệp

Theo cơ chế Jakarta Validation, thông báo có thể tham chiếu một khóa từ tài nguyên thông điệp:

~~~java
String message() default "{validation.storeCode.invalid}";
~~~

Ví dụ file `ValidationMessages.properties` trên classpath:

~~~properties
validation.storeCode.invalid=Store code must match ABC-1234
~~~

Provider Bean Validation có khả năng tra cứu thông điệp qua message interpolation, từ đó giúp duy trì nhiều ngôn ngữ hoặc đổi thông báo mà không sửa mã annotation.

Để sử dụng bundle phù hợp trong dự án, cần cấu hình và kiểm tra cơ chế thông điệp theo provider đang dùng. Đây là vấn đề **biểu diễn thông báo**, không thay đổi nội dung điều kiện `isValid`.

## 12. Tạo constraint có tham số riêng

Ví dụ `@StoreCode` chỉ kiểm tra định dạng cố định. Một custom constraint khác có thể cần thông số như độ dài, tên một loại thuật toán, danh sách trạng thái hợp lệ hoặc chế độ kiểm tra.

Ví dụ annotation `@AllowedRegion`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = AllowedRegionValidator.class)
@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
public @interface AllowedRegion {

    String message() default "region không thuộc danh sách cho phép";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    String[] value();
}
~~~

Validator:

~~~java
package com.example.demo.validation;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class AllowedRegionValidator
        implements ConstraintValidator<AllowedRegion, String> {

    private Set<String> allowedRegions;

    @Override
    public void initialize(AllowedRegion annotation) {
        allowedRegions = Arrays.stream(annotation.value())
                .collect(Collectors.toUnmodifiableSet());
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || allowedRegions.contains(value);
    }
}
~~~

Sử dụng:

~~~java
@NotBlank
@AllowedRegion({"apac", "emea", "americas"})
String region;
~~~

Khi `region="apac"`, validator trả true. Khi `region="moon"`, trả false. Danh sách cho phép đến từ **annotation parameter**, không tự được đọc từ `application.yaml`.

### initialize dùng để làm gì?

`initialize(...)` được gọi để validator chuẩn bị dữ liệu từ annotation, ví dụ:

- Tập giá trị hợp lệ.
- Giới hạn số lượng.
- Một mẫu regex được biên dịch trước.
- Chế độ có phân biệt chữ hoa/thường.

Một instance validator có thể được provider tái sử dụng, vì vậy mã trong `isValid(...)` nên tránh trạng thái biến đổi theo từng request. Trong ví dụ, `allowedRegions` được tính một lần ở `initialize` và dùng như dữ liệu chỉ đọc.

**Nếu chỉ có một phép kiểm tra đơn giản**, có thể không cần override `initialize`; đó là lý do `StoreCodeValidator` ở ví dụ trước chỉ cài đặt `isValid`.

## 13. Khi cần so sánh nhiều thuộc tính: field-level constraint không đủ

Giả sử cấu hình retry:

~~~yaml
client:
  retry:
    initial-delay: 2s
    max-delay: 30s
    max-attempts: 5
~~~

Yêu cầu nghiệp vụ:

1. `initial-delay` phải dương.
2. `max-delay` phải dương.
3. `max-delay` phải **lớn hơn hoặc bằng** `initial-delay`.
4. `max-attempts` phải ít nhất 1.

`@NotNull` có thể kiểm tra thiếu giá trị. `@Min(1)` có thể kiểm tra số lần thử. Nhưng quan hệ `maxDelay >= initialDelay` liên quan đến **hai field**, nên một constraint cấp lớp sẽ diễn đạt tốt hơn.

Ta tạo:

~~~java
@ValidRetryPolicy
public record RetryProperties(...) {
}
~~~

`@ValidRetryPolicy` sẽ được đặt trên **class/record**, không phải chỉ một thành viên đơn lẻ.

## 14. Định nghĩa annotation cấp lớp @ValidRetryPolicy

File `ValidRetryPolicy.java`:

~~~java
package com.example.demo.validation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = RetryPolicyValidator.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidRetryPolicy {

    String message() default
            "cấu hình retry không hợp lệ";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

`@Target(TYPE)` thể hiện rằng annotation kiểm tra **toàn bộ object** sau khi Binder đã xây dựng nó, khác với `@StoreCode` kiểm tra một String.

Một class-level constraint thường phù hợp khi:

- Thời điểm bắt đầu phải trước thời điểm kết thúc.
- `minConnections` không được lớn hơn `maxConnections`.
- Hai thuộc tính chỉ được bật đồng thời.
- Nếu `mode=secure` thì `tls.enabled` phải là true.
- Khoảng thời gian retry tối đa phải không nhỏ hơn khoảng ban đầu.

Những quy tắc này phụ thuộc **quan hệ giữa các field** chứ không chỉ giá trị của từng field.

## 15. Cài đặt RetryPolicyValidator

File `RetryPolicyValidator.java`:

~~~java
package com.example.demo.validation;

import java.time.Duration;

import com.example.demo.config.RetryProperties;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class RetryPolicyValidator
        implements ConstraintValidator<ValidRetryPolicy, RetryProperties> {

    @Override
    public boolean isValid(
            RetryProperties value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        Duration initial = value.initialDelay();
        Duration maximum = value.maxDelay();

        // @NotNull trên từng field chịu trách nhiệm báo thiếu giá trị.
        if (initial == null || maximum == null) {
            return true;
        }

        if (initial.isZero() || initial.isNegative()) {
            return violation(
                    context,
                    "initialDelay",
                    "initial-delay phải lớn hơn 0");
        }

        if (maximum.isZero() || maximum.isNegative()) {
            return violation(
                    context,
                    "maxDelay",
                    "max-delay phải lớn hơn 0");
        }

        if (maximum.compareTo(initial) < 0) {
            return violation(
                    context,
                    "maxDelay",
                    "max-delay không được nhỏ hơn initial-delay");
        }

        return true;
    }

    private boolean violation(
            ConstraintValidatorContext context,
            String property,
            String message) {

        context.disableDefaultConstraintViolation();

        context.buildConstraintViolationWithTemplate(message)
                .addPropertyNode(property)
                .addConstraintViolation();

        return false;
    }
}
~~~

Các điểm kỹ thuật:

- Generic thứ hai là `RetryProperties`, vì validator này kiểm tra toàn object.
- Mã giữ giá trị null để `@NotNull` thông báo thiếu field, tránh lỗi `NullPointerException`.
- Kiểm tra `Duration` trực tiếp bằng `isZero`, `isNegative` và `compareTo`, không cần đoán từ chuỗi `2s`.
- Khi vi phạm, dùng `ConstraintValidatorContext` để hướng thông báo đến property Java tương ứng.
- Hàm trợ giúp `violation(...)` tạo đúng một violation cho nhánh lỗi rồi trả false.

### Tại sao dùng addPropertyNode?

Class-level constraint mặc định gắn lỗi lên chính object. Nhưng đôi khi muốn chỉ ra field cần sửa, ví dụ `maxDelay`.

Đoạn:

~~~java
context.buildConstraintViolationWithTemplate(
        "max-delay không được nhỏ hơn initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();
~~~

giúp violation có property path cụ thể hơn. `maxDelay` ở đây là **tên thành viên Java**, không nhất thiết là chuỗi kebab-case `max-delay` trong file YAML.

Với một lỗi thực sự liên quan đến cả nhóm, bạn cũng có thể giữ thông báo ở cấp object. Khi đó nên mô tả rõ quan hệ giữa các thuộc tính để người vận hành biết cần thay gì.

### Đừng tạo thông báo nhưng quên addConstraintViolation

`buildConstraintViolationWithTemplate(...)` mới khởi tạo việc xây dựng đường dẫn lỗi. Cần gọi `addConstraintViolation()` để hoàn tất violation mới. Nếu đã `disableDefaultConstraintViolation()` mà không tạo violation thay thế khi trả false, provider có thể coi đó là trạng thái không hợp lệ.

## 16. Áp dụng @ValidRetryPolicy lên ConfigurationProperties

File `RetryProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;

import com.example.demo.validation.ValidRetryPolicy;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(

        @NotNull
        Duration initialDelay,

        @NotNull
        Duration maxDelay,

        @Min(1)
        int maxAttempts) {
}
~~~

Cấu hình hợp lệ:

~~~yaml
client:
  retry:
    initial-delay: 2s
    max-delay: 30s
    max-attempts: 5
~~~

Cấu hình không hợp lệ:

~~~yaml
client:
  retry:
    initial-delay: 20s
    max-delay: 2s
    max-attempts: 5
~~~

Trong cấu hình không hợp lệ:

- Binder có thể chuyển cả `20s` và `2s` thành `Duration`.
- `@NotNull` không báo lỗi vì hai field đã có giá trị.
- `@ValidRetryPolicy` so sánh hai Duration và báo vi phạm do `maxDelay < initialDelay`.

Đây là ví dụ điển hình của custom constraint cấp lớp: **kiểu hợp lệ, từng field có mặt, nhưng tổng thể object vẫn không hợp lệ theo quy tắc nghiệp vụ**.

## 17. Tại sao cần @Validated trên class cấu hình?

Spring Boot hỗ trợ validate `@ConfigurationProperties` khi class có `@Validated` và hệ thống có Bean Validation provider phù hợp.

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "client.retry")
@ValidRetryPolicy
public record RetryProperties(...) {
}
~~~

Ở đây:

- `@ConfigurationProperties` khai báo prefix cho Binder.
- `@ValidRetryPolicy` khai báo constraint cấp class.
- `@Validated` kích hoạt quá trình validation của Spring Boot đối với bean cấu hình.

Nếu bạn chỉ thêm `@ValidRetryPolicy` nhưng **không kích hoạt** kiểm tra cấu hình theo cơ chế tương ứng, đừng giả định custom validator chắc chắn chạy ở giai đoạn khởi động.

Ngược lại, nếu đã có `@Validated` nhưng không có Bean Validation provider thích hợp, constraint cũng không được thực thi như mong muốn.

### Đăng ký class cấu hình vẫn là bước riêng

Class `RetryProperties` cần được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RetryProperties.class)` hay cơ chế thích hợp khác.

Ba nhiệm vụ:

1. **Bean registration:** để Spring biết class cần tạo.
2. **Configuration binding:** để lấy và chuyển giá trị vào field/constructor.
3. **Validation:** để kiểm tra các constraint trên object đã bind.

Đừng nhầm lỗi “không có bean” với lỗi “constraint không hoạt động”.

## 18. Constraint cấp field và constraint cấp class nên kết hợp thế nào?

Một mô hình thường dùng:

~~~java
@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(
        @NotNull Duration initialDelay,
        @NotNull Duration maxDelay,
        @Min(1) int maxAttempts) {
}
~~~

Ý nghĩa:

- `@NotNull` bảo đảm những giá trị thời gian bắt buộc có mặt.
- `@Min(1)` bảo đảm số lần thử không nhỏ hơn 1.
- `@ValidRetryPolicy` kiểm tra quan hệ giữa hai Duration và tính dương của chúng.

Khi một field thiếu, class validator trả true sớm để constraint chuẩn thông báo thiếu field. Đây là **cách phân chia trách nhiệm**, không phải một yêu cầu tuyệt đối của Jakarta Validation. Nếu nghiệp vụ muốn một constraint kiểm tra toàn bộ, bạn có thể thiết kế khác, miễn các thông báo dễ hiểu và tránh null gây exception.

### Có thể phát sinh nhiều lỗi cùng lúc

Nếu YAML chứa:

~~~yaml
client:
  retry:
    initial-delay: 20s
    max-delay: 2s
    max-attempts: 0
~~~

Provider có thể trả về:

- Vi phạm `max-attempts` không đạt `@Min(1)`.
- Vi phạm quan hệ `max-delay >= initial-delay`.

Không được phụ thuộc vào một thứ tự cố định của các violation. Với log và test, hãy kiểm tra **tập đường dẫn/thông báo**, không giả định lỗi nào nhất thiết xuất hiện đầu tiên.

## 19. Object lồng nhau: khi nào cần @Valid?

Một class cấu hình có thể chứa một object con:

~~~java
package com.example.demo.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(

        @NotNull
        @Valid
        Connection connection) {

    public record Connection(
            @NotBlank String host,
            @Min(1) int port) {
    }
}
~~~

YAML:

~~~yaml
service:
  connection:
    host: api.example.test
    port: 8443
~~~

Ở đây, `@Valid` trên thành viên `connection` yêu cầu Bean Validation **đi vào object con** và kiểm tra `host`/`port`.

Nếu thiếu `connection` hoàn toàn, `@NotNull` kiểm tra tính bắt buộc. Nếu `connection` có mặt nhưng `host` rỗng, `@Valid` cho phép kiểm tra sâu và `@NotBlank` báo lỗi.

Theo hướng dẫn Spring Boot, nên dùng `@Valid` trên field nested khi muốn validation được kích hoạt nhất quán, kể cả khi không có dữ liệu cho một số thuộc tính con. Với JavaBean có nested object được khởi tạo sẵn, cách đặt `@Valid` đặc biệt quan trọng.

### Phân biệt @Valid và @Validated

| Annotation | Vị trí phổ biến | Vai trò chính |
| --- | --- | --- |
| `@Validated` | Class `@ConfigurationProperties`, bean hoặc method theo cơ chế Spring | Kích hoạt validation trong ngữ cảnh Spring, có thể hỗ trợ groups. |
| `@Valid` | Field/record component tham chiếu object con | Cho phép validation lan sang object con. |
| `@Constraint` | Định nghĩa annotation tùy chỉnh | Công bố loại ràng buộc và validator tương ứng. |
| `@StoreCode`, `@ValidRetryPolicy` | Trên nơi cần kiểm tra | Tuyên bố một quy tắc nghiệp vụ cụ thể. |

`@Valid` tự nó không phải một quy tắc định dạng như `@Pattern`. Nó là cơ chế **cascading validation**.

## 20. Custom constraint có thể dùng chung cho record và JavaBean

Một annotation cấp field như `@StoreCode` có thể đặt trên record component:

~~~java
public record StoreProperties(
        @NotBlank @StoreCode String storeCode) {
}
~~~

Hoặc trên field JavaBean:

~~~java
public class MutableStoreProperties {

    @NotBlank
    @StoreCode
    private String storeCode;

    public String getStoreCode() {
        return storeCode;
    }

    public void setStoreCode(String storeCode) {
        this.storeCode = storeCode;
    }
}
~~~

Validator vẫn là:

~~~java
ConstraintValidator<StoreCode, String>
~~~

Bởi vì kiểu dữ liệu nó kiểm tra vẫn là `String`.

Ngược lại, `RetryPolicyValidator` là validator cấp class với kiểu đích `RetryProperties`. Nó không mặc nhiên áp dụng cho một class khác như `LegacyRetryProperties` chỉ vì class ấy có hai field tên tương tự. Muốn tái sử dụng kiểm tra cho nhiều kiểu khác, cần thiết kế lại abstraction hoặc cung cấp validator phù hợp cho từng kiểu đích.

### Chú ý annotation trên getter

Jakarta Validation cũng có thể đặt constraint trên property getter khi target cho phép `METHOD`. Nhưng nên tránh đánh dấu cùng một constraint trên cả field **và** getter của cùng property nếu không có mục đích rõ ràng, vì provider có thể coi đó là hai vị trí ràng buộc và báo lỗi trùng.

## 21. Kiểm thử validator riêng biệt không cần khởi động Spring Boot

Custom constraint là thành phần Jakarta Validation. Bạn có thể kiểm thử logic của nó thông qua API `jakarta.validation.Validator` mà không cần dựng toàn bộ ứng dụng.

Ví dụ test:

~~~java
package com.example.demo.validation;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;

import com.example.demo.config.StoreProperties;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

class StoreConstraintTest {

    @Test
    void acceptsValidStoreCode() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            StoreProperties value =
                    new StoreProperties("HCM-2026", 100);

            Set<ConstraintViolation<StoreProperties>> violations =
                    validator.validate(value);

            assertTrue(violations.isEmpty());
        } finally {
            factory.close();
        }
    }

    @Test
    void rejectsLowercaseStoreCode() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            StoreProperties value =
                    new StoreProperties("hcm-2026", 100);

            Set<ConstraintViolation<StoreProperties>> violations =
                    validator.validate(value);

            assertFalse(violations.isEmpty());
        } finally {
            factory.close();
        }
    }
}
~~~

Kiểm thử này tập trung vào **quy tắc annotation/validator**, không khẳng định Spring Boot đã nạp đúng file YAML. Có thể tái sử dụng một `ValidatorFactory` cho nhiều test theo cách tổ chức test suite thay vì tạo mới mỗi method.

### Kiểm tra property path

Với một object có `storeCode` vi phạm, `ConstraintViolation.getPropertyPath()` cho phép biết nơi xảy ra lỗi:

~~~java
for (ConstraintViolation<StoreProperties> violation
        : violations) {

    System.out.println(
            violation.getPropertyPath() + ": "
                    + violation.getMessage());
}
~~~

Ví dụ kết quả:

~~~text
storeCode: mã cửa hàng phải có dạng ABC-1234
~~~

Không phụ thuộc hoàn toàn vào thứ tự Set trả về. Trong test thật, hãy kiểm tra nó **có chứa** path mong đợi.

## 22. Kiểm thử class-level ConstraintValidator

Ta đã có:

~~~java
@Validated
@ValidRetryPolicy
@ConfigurationProperties(prefix = "client.retry")
public record RetryProperties(
        @NotNull Duration initialDelay,
        @NotNull Duration maxDelay,
        @Min(1) int maxAttempts) {
}
~~~

Có thể tạo object trực tiếp:

~~~java
RetryProperties valid = new RetryProperties(
        Duration.ofSeconds(2),
        Duration.ofSeconds(30),
        5);

RetryProperties invalid = new RetryProperties(
        Duration.ofSeconds(20),
        Duration.ofSeconds(2),
        5);
~~~

Dùng `Validator.validate(...)` với hai object để xác minh:

- `valid` không có violation.
- `invalid` có violation gắn tới `maxDelay`, theo đường dẫn được tạo bởi `addPropertyNode("maxDelay")`.

### Test ví dụ

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.time.Duration;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.Test;

class RetryPolicyConstraintTest {

    @Test
    void rejectsMaximumSmallerThanInitial() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();

        try {
            Validator validator = factory.getValidator();

            RetryProperties props = new RetryProperties(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(2),
                    5);

            var violations = validator.validate(props);

            assertFalse(violations.isEmpty());

            assertTrue(
                    violations.stream()
                            .anyMatch(v ->
                                    v.getPropertyPath()
                                            .toString()
                                            .equals("maxDelay")));
        } finally {
            factory.close();
        }
    }
}
~~~

Trong test này, cần import class `RetryProperties` từ package cấu hình tương ứng. Đây là test **logic constraint trên object Java**; nó không kiểm tra relaxed binding, profile hay thứ tự `PropertySource`.

## 23. Kiểm thử tích hợp: Spring Boot có thật sự kiểm tra cấu hình khi khởi động?

Một custom constraint hoạt động trong test thuần Jakarta chưa bảo đảm bean `@ConfigurationProperties` đã được đăng ký và được validation trong ứng dụng.

Để kiểm thử tích hợp, có thể dùng Spring Boot `ApplicationContextRunner`. Nó tạo một context nhỏ với cấu hình kiểm soát được và cho phép xác minh khởi động thành công/thất bại.

Ví dụ:

~~~java
package com.example.demo;

import com.example.demo.config.StoreProperties;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StorePropertiesContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ConfigurationPropertiesAutoConfiguration.class,
                            ValidationAutoConfiguration.class))
                    .withUserConfiguration(TestConfig.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StoreProperties.class)
    static class TestConfig {
    }

    @Test
    void startsWithValidConfiguration() {
        runner.withPropertyValues(
                "shop.store-code=HCM-2026",
                "shop.batch-size=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            StoreProperties.class);
                });
    }

    @Test
    void failsWithInvalidStoreCode() {
        runner.withPropertyValues(
                "shop.store-code=bad-value",
                "shop.batch-size=100")
                .run(context ->
                        assertThat(context).hasFailed());
    }
}
~~~

Ý nghĩa:

- `@EnableConfigurationProperties` đăng ký bean cần bind.
- `withPropertyValues(...)` đóng vai trò nguồn cấu hình cho context thử nghiệm.
- Hạ tầng Spring Boot thực hiện binding và validation.
- Test thành công cho thấy context chứa bean hợp lệ.
- Test thất bại cho thấy cấu hình được đánh giá ở vòng đời khởi động.

Trong ứng dụng thực tế, điều kiện auto-configuration và các dependency cần có trên test classpath phù hợp với Spring Boot đang dùng. Ví dụ dùng `spring-boot-starter-test` và `spring-boot-starter-validation` theo cấu hình dự án.

### Kiểm thử nhiều nguồn cấu hình

Sau khi kiểm thử từng giá trị hợp lệ/không hợp lệ, có thể thử nguồn CLI hoặc biến môi trường để xác định rằng **giá trị cuối cùng** mới được đưa vào validation. Việc test trực tiếp class-level validator không chứng minh được thứ tự ưu tiên giữa YAML và CLI.

## 24. Validator nhận giá trị null, rỗng và dữ liệu sai kiểu thế nào?

Đây là ba nhóm khác nhau:

| Dữ liệu | Tình huống | Tầng phù hợp |
| --- | --- | --- |
| Không có khóa `shop.store-code` | Giá trị có thể là null | `@NotNull` hoặc `@NotBlank`. |
| `shop.store-code=` | Chuỗi rỗng | `@NotBlank`, custom constraint có thể báo thêm. |
| `shop.store-code=hcm-2026` | Chuỗi có định dạng không hợp lệ | `@StoreCode`. |
| `shop.batch-size=abc` | Không chuyển sang số nguyên | Binding/conversion. |
| `shop.batch-size=0` | Số nguyên hợp lệ nhưng trái chính sách | `@Min(1)`. |
| `maxDelay < initialDelay` | Hai Duration hợp lệ riêng lẻ nhưng quan hệ sai | `@ValidRetryPolicy`. |

Một custom validator không nhất thiết phải xử lý tất cả các trường hợp. Tách trách nhiệm giúp thông báo rõ và mã dễ thay đổi.

### Không dùng exception để báo một giá trị chỉ đơn giản không hợp lệ

Trong `isValid(...)`, nếu kiểm tra không thỏa quy tắc thì nên trả `false`, thay vì ném một exception nghiệp vụ như:

~~~java
throw new IllegalArgumentException(
        "Store code không hợp lệ");
~~~

Một exception bất ngờ có thể được provider coi là lỗi thực thi validator, làm thông điệp và luồng xử lý khó hiểu hơn. Exception thích hợp khi có lỗi không thể tiếp tục thực thi validator, chứ không phải thay thế cơ chế `ConstraintViolation` thông thường.

## 25. Validation groups dùng để làm gì?

Mỗi custom constraint cần thành viên:

~~~java
Class<?>[] groups() default {};
~~~

Jakarta Validation cho phép phân nhóm để áp dụng các tập quy tắc khác nhau trong một số ngữ cảnh.

Ví dụ giao diện marker:

~~~java
public interface ProductionChecks {
}
~~~

Một constraint có thể được đặt:

~~~java
@StoreCode(groups = ProductionChecks.class)
String storeCode;
~~~

Khi chỉ validate bằng **nhóm mặc định**, constraint thuộc `ProductionChecks` không nhất thiết được thực thi. Muốn dùng nhóm cụ thể, cần chỉ định groups trong lời gọi validator hoặc cấu hình Spring phù hợp.

Trong `@ConfigurationProperties`, thường nên đặt những quy tắc **thiết yếu cho mọi môi trường** vào nhóm mặc định để tránh cấu hình production bỏ qua validation vì nhóm chưa được kích hoạt.

Đừng tự chọn nhóm theo `spring.profiles.active` bằng cách suy đoán rằng tên profile và tên validation group là cùng một cơ chế:

- Spring profile là tập điều kiện lựa chọn bean và nguồn cấu hình.
- Validation group là cơ chế chọn những constraint nào sẽ chạy.

Chúng không tự ánh xạ một-một.

## 26. Có thể viết custom Spring Validator thay vì ConstraintValidator không?

Có. Spring Framework có interface:

~~~java
org.springframework.validation.Validator
~~~

với các phương thức `supports(...)` và `validate(Object, Errors)`.

Spring Boot cũng hỗ trợ một bean đặc biệt có tên `configurationPropertiesValidator` để thực hiện validation theo cơ chế Spring trong quá trình cấu hình. Theo tài liệu Spring Boot, bean validator này được khởi tạo rất sớm, nên `@Bean` method cần được khai báo `static` khi đặt trong một class cấu hình nhằm tránh khởi tạo class quá sớm.

Tuy nhiên, đó là **một cách mở rộng khác** so với định nghĩa Jakarta Bean Validation annotation và `ConstraintValidator`.

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Dùng lại một constraint trên field ở nhiều class | Jakarta `@Constraint` + `ConstraintValidator`. |
| Kiểm tra quan hệ giữa nhiều field trong một class | Jakarta class-level `@Constraint`. |
| Tận dụng `@NotBlank`, `@Min`, `@Valid` và Bean Validation provider | Jakarta Validation. |
| Cần logic validation tích hợp trực tiếp với Spring `Errors` | Spring `Validator`. |
| Muốn bổ sung validator cấu hình ở cấp hạ tầng | `configurationPropertiesValidator` theo tài liệu Spring Boot. |

Trong bài này, lựa chọn chính là **Jakarta Bean Validation** vì nó cho phép khai báo điều kiện ngay trên class hoặc field và tái sử dụng một cách rõ ràng.

## 27. Có nên inject bean Spring vào ConstraintValidator?

Trong môi trường Spring Boot có integration phù hợp, `ConstraintValidator` có thể được tạo thông qua hạ tầng Bean Validation hỗ trợ dependency injection. Nhưng không nên mặc định mọi cách tạo `ValidatorFactory` bên ngoài Spring đều có thể inject các Spring bean.

Đặc biệt với `@ConfigurationProperties`, validation diễn ra **trong giai đoạn khởi tạo application context**. Một validator phụ thuộc vào nhiều service, database client hoặc bean cũng đang chờ cấu hình có thể tạo ra vòng phụ thuộc hoặc lỗi khởi tạo sớm.

Đối với quy tắc thuần cấu hình, nên ưu tiên validator:

- Không có side effect.
- Không gọi mạng hoặc database.
- Không ghi file.
- Không phụ thuộc vào trạng thái runtime thay đổi.
- Dễ kiểm thử bằng object Java thuần.
- Dùng dữ liệu truyền trong annotation hoặc object cần kiểm tra.

Ví dụ `StoreCodeValidator` với `Pattern` cố định và `RetryPolicyValidator` với hai `Duration` đều là các luật thuần, không cần service bên ngoài.

Nếu nghiệp vụ yêu cầu dữ liệu động từ hệ thống khác, cần xác định đó có thực sự là **validation cấu hình lúc khởi động** hay nên là **kiểm tra readiness/khả năng kết nối** ở một bước khác. Bean Validation không phải công cụ giám sát sức khỏe hệ thống từ xa.

## 28. Thứ tự cấu hình ảnh hưởng dữ liệu đưa vào validator

Một validator không biết giá trị đến từ tệp nào nếu bạn không tự truy vấn thông tin nguồn. Nó chỉ nhận object hoặc field đã được binder chuẩn bị.

Ví dụ YAML:

~~~yaml
shop:
  store-code: HCM-2026
  batch-size: 100
~~~

Nhưng lệnh chạy:

~~~bash
java -jar app.jar --shop.store-code=invalid --shop.batch-size=100
~~~

Trong lần chạy Spring Boot thông thường, command-line property có thể ưu tiên hơn YAML. Vì thế `StoreProperties.storeCode()` nhận `invalid` và custom validator sẽ báo lỗi, dù file `application.yaml` mà bạn đang xem chứa mã hợp lệ.

Cần chẩn đoán theo hai bước:

1. **Nguồn nào có giá trị hiệu lực?** Do `Environment` và `PropertySource` quyết định.
2. **Giá trị đó có hợp lệ không?** Do Bean Validation quyết định.

Không nên sửa regex trong validator nếu nguyên nhân thực tế là một biến môi trường hoặc tùy chọn CLI đã ghi đè cấu hình.

### Profile cũng ảnh hưởng tương tự

~~~yaml
# application-prod.yaml
shop:
  store-code: HCM-2026
~~~

Nếu profile `prod` hoạt động, tài liệu này có thể tham gia Config Data. Nhưng một nguồn ưu tiên cao hơn vẫn có thể ghi đè `shop.store-code`. Constraint được đánh giá trên giá trị cuối của properties bean.

## 29. Báo lỗi ở property path hay ở cấp object?

Với field-level constraint `@StoreCode`, provider thường biết ngay property path là `storeCode`.

Với class-level constraint `@ValidRetryPolicy`, lỗi có thể mặc định nằm ở object `RetryProperties`. Nếu muốn người vận hành biết cần sửa `max-delay`, ta đã thêm:

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "max-delay không được nhỏ hơn initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();
~~~

Cách này đưa lỗi về property Java `maxDelay`. Trong thông báo khởi động do Spring Boot hiển thị, tên khóa có thể được trình bày theo quy ước cấu hình (kebab-case) hoặc theo đường dẫn property. Không nên phụ thuộc vào một chuỗi log định dạng cố định giữa các phiên bản.

### Nhiều lỗi cho một rule cấp lớp

Bạn cũng có thể tạo nhiều violation sau khi gọi `disableDefaultConstraintViolation()`, ví dụ một lỗi ở `initialDelay` và một lỗi ở `maxDelay`. Tuy nhiên cần làm rõ mục đích để tránh gây ra nhiều thông báo cùng nội dung.

Một custom validator không nên lặp lại các lỗi `@NotNull` hoặc `@Min` nếu những constraint riêng đã bao phủ cùng quy tắc, trừ khi điều đó phục vụ cách báo lỗi thống nhất của hệ thống.

## 30. Bảo vệ dữ liệu bí mật trong validation

Đối tượng `@ConfigurationProperties` có thể chứa password, API token, connection string hoặc secret từ environment. Thông báo lỗi cần tránh in giá trị bí mật.

**Không nên**:

~~~java
return violation(context,
        "password",
        "Mật khẩu không hợp lệ: " + value.password());
~~~

Thông báo như vậy có thể xuất hiện trong log khởi động hoặc output CI/CD, làm lộ secret.

**Nên**:

~~~text
app.credentials.password không đáp ứng chính sách độ dài
~~~

nếu thực sự cần thông báo. Tránh đưa secret thô vào message template, exceptions hay log debug.

Bản thân `ConstraintViolation` có thể giữ thông tin về giá trị không hợp lệ. Nếu tự ghi log toàn bộ violation, hãy chọn trường an toàn để xuất. Các endpoint chẩn đoán như `/actuator/configprops` hoặc `/actuator/env` cũng cần được bảo vệ thích hợp.

Constraint chỉ xác định **hợp lệ hay không hợp lệ**; nó không tự mã hóa hoặc che giấu bí mật.

## 31. Lưu ý về hiệu năng và trạng thái của validator

Một provider Jakarta Validation có thể tái sử dụng instance `ConstraintValidator`. Vì vậy:

- Không cất giá trị đang kiểm tra vào field mutable của validator.
- Nếu cần một regex, biên dịch sẵn thành `static final Pattern` như `StoreCodeValidator`.
- Nếu annotation có tham số, chuẩn bị dữ liệu trong `initialize` rồi dùng theo cách chỉ đọc trong `isValid`.
- Không dùng các biến static để nhớ “giá trị cuối cùng đã kiểm tra”.
- Không phụ thuộc vào thứ tự provider gọi những validator khác nhau.
- Viết `isValid` như một hàm không có side effect bất cứ khi nào có thể.

Một custom constraint rất dễ bị gọi nhiều lần: trong kiểm thử, khi bind cấu hình, trong các tầng service hoặc request validation khác nếu annotation được tái sử dụng. Thiết kế thuần giúp kết quả nhất quán.

## 32. Những lỗi phổ biến khi tự viết ConstraintValidator

### Lỗi 1: dùng javax.validation trong Spring Boot 3.x

Code được sao chép từ Spring Boot 2.x có thể import:

~~~java
import javax.validation.ConstraintValidator;
~~~

Với Spring Boot 3.x, dùng:

~~~java
import jakarta.validation.ConstraintValidator;
~~~

Đồng thời đảm bảo dependency validation tương thích phiên bản Jakarta của dự án.

### Lỗi 2: quên @Constraint

Annotation chỉ có `@Target` và `@Retention` nhưng thiếu:

~~~java
@Constraint(validatedBy = StoreCodeValidator.class)
~~~

thì nó không phải một constraint đầy đủ được provider áp dụng như dự kiến.

### Lỗi 3: thiếu message(), groups(), payload()

Đây là những thành viên chuẩn của Bean Validation constraint definition. Nếu thiếu, provider có thể xem annotation là khai báo constraint không hợp lệ.

### Lỗi 4: sai Target

Một annotation chỉ có `@Target(FIELD)` không dùng được trên class-level hoặc constructor parameter mà bạn muốn. Hãy chọn `FIELD`, `METHOD`, `PARAMETER`, `RECORD_COMPONENT` hoặc `TYPE` phù hợp với vị trí cần kiểm tra.

### Lỗi 5: quên @Retention(RUNTIME)

Nếu metadata không tồn tại ở runtime, provider không thể xử lý constraint theo cách thông thường.

### Lỗi 6: generic type không phù hợp

~~~java
ConstraintValidator<StoreCode, Integer>
~~~

không kiểm tra trực tiếp một `String storeCode`. Kiểu Java của đối tượng cần kiểm tra phải phù hợp với generic type validator.

### Lỗi 7: ném exception thay vì trả false

Một giá trị không đáp ứng quy tắc nên tạo `ConstraintViolation`, không phải exception bất ngờ. Exception có thể khiến lỗi bị phân loại thành lỗi thực thi validator.

### Lỗi 8: không xử lý null

Nếu validator dùng:

~~~java
return value.matches("[A-Z]{3}-[0-9]{4}");
~~~

mà `value=null`, phương thức ném `NullPointerException`. Hãy xác định chính sách null và phối hợp với `@NotNull`/`@NotBlank`.

### Lỗi 9: chỉ có annotation nhưng thiếu @Validated

Một class `@ConfigurationProperties` có custom constraint nhưng chưa kích hoạt validation theo ngữ cảnh có thể không được kiểm tra khi bind. Hãy dùng `@Validated` và provider phù hợp.

### Lỗi 10: thiếu @Valid ở object nested

Nếu bạn cần kiểm tra constraint trong object con, hãy đặt `@Valid` trên thành viên chứa object ấy. Chỉ `@Validated` ở class cha không phải cách thay thế cho mọi trường hợp cascading.

### Lỗi 11: đặt tên node theo YAML thay vì Java property

Trong `ConstraintValidatorContext.addPropertyNode(...)`, thông thường dùng tên property Java được Bean Validation hiểu, ví dụ `maxDelay`. Đừng tự giả định mọi tên kebab-case như `max-delay` đều là tên JavaBean property có thể gắn trực tiếp.

### Lỗi 12: không gọi addConstraintViolation()

Khi tùy biến message/path và đã disable default violation, cần hoàn tất một violation mới trước khi trả false.

### Lỗi 13: trộn logic conversion vào validation

Validator không nên tự thay `30s` thành `Duration` hoặc chuẩn hóa dữ liệu. Binder và converter đảm nhận chuyển kiểu; validator nhận giá trị có kiểu và kiểm tra nó.

### Lỗi 14: sử dụng một validator có trạng thái không an toàn

Viết field mutable dùng chung để lưu request cuối khiến kết quả phụ thuộc thứ tự gọi khi validator được tái sử dụng. Hãy giữ state bất biến hoặc riêng cho annotation instance.

### Lỗi 15: kiểm tra bằng cách gọi database khi startup

Cấu hình lỗi có thể khiến context khởi động thất bại vì mạng/database chưa sẵn sàng, dù cú pháp và chính sách local hoàn toàn hợp lệ. Cần phân biệt **validity của cấu hình** với **availability của hệ thống bên ngoài**.

## 33. Bài thực hành có đáp án

### Bài 1 — xác định nơi dùng field constraint

Cho:

~~~properties
shop.store-code=ABC-1024
~~~

Mục tiêu: chỉ nhận `AAA-9999` theo mẫu ba chữ in hoa và bốn chữ số.

**Gợi ý đáp án:** tạo `@StoreCode` với `@Constraint(validatedBy = StoreCodeValidator.class)`; validator dùng `Pattern.compile("[A-Z]{3}-[0-9]{4}")` và `matches()`. Đặt trên field/record component `String storeCode`, kết hợp `@NotBlank` nếu bắt buộc.

### Bài 2 — phân biệt thiếu khóa và sai định dạng

Giả sử dùng:

~~~java
@NotBlank
@StoreCode
String storeCode;
~~~

Dự đoán:

| Giá trị | `@NotBlank` | `@StoreCode` ví dụ |
| --- | --- | --- |
| `null` | Vi phạm | Hợp lệ theo chính sách null của custom validator. |
| `""` | Vi phạm | Vi phạm vì regex không khớp. |
| `"abc-1234"` | Hợp lệ về không rỗng | Vi phạm vì chữ thường. |
| `"ABC-1234"` | Hợp lệ | Hợp lệ. |

### Bài 3 — chọn loại constraint

Quy tắc: `max-delay` phải không nhỏ hơn `initial-delay`.

**Đáp án:** class-level constraint vì phải biết đồng thời hai field. Một constraint trên chỉ `maxDelay` có thể thiết kế theo cách khác nếu được cung cấp ngữ cảnh, nhưng class-level rõ ràng hơn trong Bean Validation.

### Bài 4 — phân loại lỗi

~~~properties
shop.batch-size=abc
~~~

và Java:

~~~java
@Min(1)
int batchSize;
~~~

**Đáp án:** vấn đề chuyển `abc` thành `int` là lỗi binding/conversion, không phải `@Min(1)` được thực thi trên một số hợp lệ.

### Bài 5 — thiếu @Validated

Bạn đã viết:

~~~java
@StoreCode
String storeCode;
~~~

trong class `@ConfigurationProperties` và đã đăng ký class bằng `@ConfigurationPropertiesScan`, nhưng không có `@Validated`.

**Đáp án:** đăng ký bean và ràng buộc trường không đồng nghĩa validation đã được kích hoạt theo cơ chế Spring Boot. Bổ sung `@Validated`, đảm bảo có Bean Validation provider và xác nhận bằng kiểm thử context.

### Bài 6 — custom violation path

Trong class-level validator, muốn gắn lỗi vào Java property `maxDelay` thay vì chỉ ở cấp object.

**Đáp án:**

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "max-delay không được nhỏ hơn initial-delay")
        .addPropertyNode("maxDelay")
        .addConstraintViolation();

return false;
~~~

### Bài 7 — kiểm thử không khởi động Spring

Bạn muốn xác minh `@StoreCode` chấp nhận `HCM-2026` và từ chối `hcm-2026`.

**Đáp án:** dùng `Validation.buildDefaultValidatorFactory()` tạo `Validator`, gọi `validator.validate(new StoreProperties(...))` và kiểm tra `ConstraintViolation`. Không cần full `@SpringBootTest` để kiểm tra một quy tắc thuần.

### Bài 8 — kiểm thử Startup

Bạn muốn đảm bảo ứng dụng không chạy khi `shop.store-code=bad-value`.

**Đáp án:** dùng context test có đăng ký `StoreProperties`, bật Bean Validation, cung cấp cấu hình không hợp lệ và xác minh context khởi động thất bại. Đây là kiểm thử tích hợp giữa Binder và validation.

### Bài 9 — nested validation

~~~java
@Validated
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(Connection connection) {
    public record Connection(@NotBlank String host) {
    }
}
~~~

Muốn kích hoạt kiểm tra sâu cho `host`.

**Đáp án:** đánh dấu `@Valid` trên thành viên `connection`; nếu bản thân connection bắt buộc thì thêm `@NotNull`.

### Bài 10 — validation có cần truy cập HTTP không?

Mục tiêu: xác định URL trong cấu hình có scheme `https` và thuộc nhóm domain được phép.

**Đáp án:** trong đa số trường hợp, có thể kiểm tra scheme và host bằng logic thuần trên `URI`. Không cần gọi endpoint thật để “xác nhận URL hợp lệ”; khả năng dịch vụ hiện đang phản hồi là vấn đề health/readiness khác.

### Bài 11 — giá trị từ nguồn nào được validate?

YAML có:

~~~properties
shop.store-code=HCM-2026
~~~

Nhưng chạy:

~~~bash
java -jar app.jar --shop.store-code=bad-value
~~~

**Đáp án:** trong thứ tự nguồn mặc định, CLI có thể thắng YAML; validator nhận chuỗi `bad-value` từ properties bean, nên báo vi phạm.

### Bài 12 — thông báo lỗi không lộ bí mật

Một custom validator kiểm tra token có đủ độ dài. Không được đưa token thực tế vào thông báo.

**Đáp án:** sử dụng thông điệp như `"security.api-token không đủ độ dài tối thiểu"` thay vì nối giá trị token vào message hay exception.

## 34. Bảng tổng hợp lựa chọn

| Nhu cầu | Lựa chọn |
| --- | --- |
| String không được rỗng | `@NotBlank`. |
| Số nguyên phải ít nhất 1 | `@Min(1)`. |
| String phải khớp regex đơn giản | `@Pattern`, nếu không cần abstraction riêng. |
| Mã cửa hàng có quy tắc riêng dùng nhiều nơi | Custom `@StoreCode` + `ConstraintValidator<StoreCode, String>`. |
| Quan hệ giữa hai Duration | Class-level `@ValidRetryPolicy` + validator cho object. |
| Cấu hình nested cần kiểm tra thuộc tính con | `@Valid` ở field/component chứa object con. |
| Spring Boot cần validate bean cấu hình lúc bind | `@Validated` trên `@ConfigurationProperties` và provider phù hợp. |
| Cần báo lỗi ở field cụ thể từ class-level validator | `ConstraintValidatorContext.addPropertyNode(...)`. |
| Cần nhóm quy tắc cho những trường hợp khác nhau | Bean Validation groups. |
| Cần test logic constraint không khởi động Spring | `Validator.validate(object)`. |
| Cần test khởi động thất bại do cấu hình sai | Spring Boot context test / `ApplicationContextRunner`. |
| Cần custom cơ chế validation bằng Spring Errors | Spring `Validator` hoặc `configurationPropertiesValidator` theo yêu cầu. |

## 35. Kết luận

Trong Spring Boot, **custom constraint** là cách đóng gói một quy tắc kiểm tra mang ý nghĩa nghiệp vụ thành annotation có thể tái sử dụng. `@Constraint` liên kết annotation với một lớp `ConstraintValidator`; `isValid(...)` nhận dữ liệu và quyết định đúng/sai; `ConstraintValidatorContext` cho phép tùy biến thông báo và vị trí lỗi.

Khi áp dụng cho `@ConfigurationProperties`, cần phân biệt đầy đủ chu trình:

1. Spring Boot nạp các nguồn cấu hình và Binder chuyển dữ liệu thành object Java.
2. Class properties được đăng ký qua `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties` hoặc cách phù hợp.
3. `@Validated` kết hợp Bean Validation provider kích hoạt những constraint đã khai báo.
4. Field-level constraint kiểm tra từng giá trị; class-level constraint kiểm tra quan hệ giữa nhiều field; `@Valid` hỗ trợ object nested.
5. Nếu dữ liệu không hợp lệ, Spring Boot có thể chặn ứng dụng khởi động và báo lỗi cấu hình ngay từ đầu.

Hãy ưu tiên constraint sẵn có cho quy tắc đơn giản; tạo custom `ConstraintValidator` khi cần một luật nghiệp vụ rõ ràng, kiểm thử được và dùng lại được. Giữ logic kiểm tra thuần, không chuyển đổi hay thay đổi dữ liệu trong validator, không gọi dịch vụ ngoài nếu không cần, và không để thông báo lỗi làm lộ cấu hình nhạy cảm.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration, phần ConfigurationProperties Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation).
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0).
- [Jakarta Validation — ConstraintValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator).
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html).