# Tham số constraint trong thông báo và nội suy biểu thức

## 1. Mục tiêu và vấn đề thực tế

Một Spring MVC API nhận JSON có các quy tắc sau:

- `displayName` phải chứa từ 3 đến 8 ký tự.
- `quantity` phải từ 2 trở lên.
- `tag` phải dài tối thiểu 4 ký tự; khi lỗi muốn chỉ rõ **số ký tự thực tế**.
- Người dùng có thể chọn thông báo bằng tiếng Anh hoặc tiếng Việt.

Không nên viết riêng “Tên phải có từ 3 đến 8 ký tự”, “Tên phải có từ 4 đến 10 ký tự” mỗi khi ràng buộc thay đổi. Jakarta Validation hỗ trợ **nội suy thông báo** bằng những thành phần có cấu trúc:

```java
@Size(min = 3, max = 8,
      message = "{order.name.size}")
private String displayName;
```

```properties
order.name.size=Name must contain between {min} and {max} characters
```

Khi vi phạm, message key `{order.name.size}` được giải mã qua bundle, còn `{min}`/`{max}` được lấy từ thuộc tính của `@Size`. Kết quả:

```text
Name must contain between 3 and 8 characters
```

Với những trường hợp phức tạp hơn, template có thể dùng Jakarta Expression Language:

```text
At least {value} item${value > 1 ? 's' : ''} required
```

hoặc **tham số động** được thêm trong một `ConstraintValidator`.

Bài này giải thích:
1. Message descriptor/key, constraint attribute parameters, dynamic parameters và EL khác nhau ở đâu.
2. Jakarta Validation nội suy theo thứ tự nào, xử lý escaping và bundle ra sao.
3. Spring Boot `MessageSource` tích hợp với Jakarta Validator để chọn ngôn ngữ thế nào.
4. Custom constraint bổ sung `{actual}` bằng Hibernate Validator.
5. Cách dùng `getMessage()`, `getMessageTemplate()`, `ConstraintDescriptor` và trả lỗi cho HTTP.
6. Những giới hạn an toàn của EL, cách kiểm thử en/vi và những lỗi thường gặp.

Phạm vi ví dụ: Java 17+, Spring Framework 6.2.x, Spring Boot 3.5.x, Jakarta Validation 3.x và Hibernate Validator 8.x. Phần `HibernateConstraintValidatorContext` là **API riêng của Hibernate Validator**, không phải API bắt buộc cho mọi Jakarta Validation provider.

## 2. Phân biệt ba loại placeholder

| Loại | Ký hiệu | Nguồn giá trị | Ví dụ |
| --- | --- | --- | --- |
| Message key | `{order.name.size}` | File bundle theo locale | `messages_vi.properties` |
| Constraint parameter | `{min}`, `{max}`, `{value}` | Annotation attributes | `@Size(min=3,max=8)` |
| EL expression | `${validatedValue}`, `${value > 1 ? 's' : ''}` | EL context/logic | Giá trị đầu vào, ternary |
| Dynamic message parameter (Hibernate) | `{actual}` | `addMessageParameter("actual", n)` | Chiều dài thực tế |
| Dynamic EL variable (Hibernate) | `${actual}` | `addExpressionVariable("actual", n)` | Sử dụng khi EL bật |
| Spring MessageFormat argument | `{0}`, `{1}` | `MessageSource.getMessage(key,args,locale)` | Không phải thuộc tính constraint |

Điểm dễ nhầm:
- `@Min(value=2)` có `{value}` là **ngưỡng 2**, không phải input hiện tại `1`.
- `@Size(min=3,max=8)` có `{min}` và `{max}` từ metadata annotation.
- `${validatedValue}` là **giá trị đang được kiểm tra** trong EL, có thể chứa dữ liệu nhạy cảm.
- `{actual}` là tên do chúng ta tự tạo trong custom Hibernate validator, không mặc nhiên tồn tại ở mọi constraint.
- `@Valid` là chỉ dẫn cascade/validation integration, **không** có parameter `{min}` riêng.

## 3. Nội suy annotation attributes: `{min}`, `{max}`, `{value}`

### 3.1. `@Size`

```java
@Size(min = 3, max = 8,
      message = "Length must be between {min} and {max}")
String name;
```

Với `"AB"`, thông báo sau nội suy:

```text
Length must be between 3 and 8
```

Không phải caller truyền `3` và `8` vào một hàm format. Provider lấy trực tiếp từ descriptor của `@Size`. Nếu sau này đổi `min = 4` và `max = 10`, cùng message template có thể cho `4`/`10`.

### 3.2. `@Min`

```java
@Min(value = 2,
     message = "Quantity must be at least {value}")
int quantity;
```

Input `quantity = 1` gây violation:

```text
Quantity must be at least 2
```

`{value}` ở đây là thuộc tính `value()` của annotation `@Min`. Muốn nhắc giá trị không hợp lệ, cân nhắc `${validatedValue}` (có lưu ý riêng về lộ dữ liệu).

### 3.3. Đặt key và template trong annotation

```java
@Size(min = 3, max = 8,
      message = "{order.name.size}")
String displayName;
```

`@Size.message` chứa **key**, không phải câu cuối. Bundle chứa:

```properties
order.name.size=Name must contain between {min} and {max} characters
```

Khi tìm thấy key, provider tiếp tục giải quyết placeholders của constraint. Dịch vụ khác có thể dùng cùng resource key nhưng metadata annotation khác nhau; bản dịch vẫn tái sử dụng được nếu những attribute cần thiết tồn tại.

### 3.4. Đừng dùng `{min}` trên một constraint không có `min()`

Ví dụ `@NotBlank` không có thuộc tính `min()`. Nếu message của `@NotBlank` chứa `{min}` mà không có resource key hoặc custom parameter tương ứng, `{min}` có thể không được nội suy.

Hãy đọc API của annotation. Với custom constraint, bạn có thể khai báo `int min() default 4;` rồi tham chiếu `{min}` trong message template.

## 4. Thứ tự mặc định của Jakarta Validation message interpolation

Về bản chất, provider thực hiện các bước trong Jakarta Validation specification:

1. **User resource bundle:** tìm những biểu thức dạng `{key}` trong resource bundle của ứng dụng, thông thường `ValidationMessages*.properties` khi khởi tạo Jakarta Validator thuần. Nếu kết quả thay thế còn key, có thể giải quyết đệ quy.
2. **Provider resource bundle:** tìm những key mặc định của Jakarta built-in constraints, ví dụ `jakarta.validation.constraints.Size.message`, trong bundle do provider cung cấp.
3. **Constraint attributes:** thay các placeholders còn lại trùng tên thành phần của annotation như `{min}`, `{max}`, `{value}`.
4. **Jakarta EL:** đánh giá phần `${expression}` nếu EL implementation và feature level cho phép.

Việc tra bundle tiêu chuẩn và user bundle có thể lặp lại theo thuật toán chuẩn; sơ đồ trên chỉ là cách nhớ các bước chính, không phải cài đặt lại bằng regex.

Ví dụ cụ thể:

```text
Constraint descriptor:
  {order.name.size}

Lookup in application bundle:
  Name must contain between {min} and {max} characters

Read @Size attributes:
  min = 3, max = 8

Interpolate constraint parameters:
  Name must contain between 3 and 8 characters

No remaining EL expression:
  Name must contain between 3 and 8 characters
```

**Quan trọng:** Message parameter interpolation xảy ra trước EL. Tránh nhầm `${value}` với cách ghi số ngưỡng: do chuỗi `{value}` là một đoạn nằm trong biểu thức, nó có thể được thay trước, khiến ký tự `$` còn lại. Nếu chỉ muốn ngưỡng, dùng `{value}`; nếu muốn logic, dùng biểu thức như `${value > 1 ? 's' : ''}`.

### 4.1. Bundle key có thể lồng nhau

```properties
field.displayName=Display name
order.name.size={field.displayName} must contain {min} to {max} characters
```

Key thứ hai có thể gọi key thứ nhất, rồi các thuộc tính annotation mới được nội suy. Giữ mức lồng hợp lý; các chuỗi đệ quy quá phức tạp dễ gây xung đột key và khó kiểm thử.

### 4.2. Tránh xung đột giữa resource key và attribute name

Không nên tạo resource key chung:

```properties
min=minimum
max=maximum
value=some-value
```

Vì bundle được tra trước, các giá trị đó có thể vô tình được dùng thay cho constraint attributes trong một message. Hãy dùng namespaced keys: `order.name.size`, `signup.age.minimum`, `profile.email.required`. Giữ `min`/`max`/`value` cho annotation metadata.

### 4.3. Fallback và key bị thiếu

Khi một key thiếu trong bundle, provider có thể tiếp tục tra provider bundle; nếu không tìm được, phần key chưa resolve có thể tồn tại trong message. Nếu response trả literal `{order.name.size}`, đó là dấu hiệu cần kiểm tra:
- Tên file resource bundle.
- Basename của MessageSource.
- Encoding.
- Locale.
- Đường đi có thực sự dùng Jakarta MessageInterpolator không.
- Key có bị typo hay trùng từ ngữ khác không.

Đừng coi thông báo chứa ngoặc nhọn là một localization hoàn tất.

## 5. Đa ngữ: `ValidationMessages.properties` và `messages.properties`

### 5.1. Dự án Jakarta Validation độc lập với Spring

Theo convention tiêu chuẩn, có thể khai báo:

```text
src/main/resources/
├── ValidationMessages.properties
├── ValidationMessages_en.properties
├── ValidationMessages_vi.properties
└── ValidationMessages_vi_VN.properties
```

Ví dụ:

```properties
# ValidationMessages.properties
order.name.size=Name must contain {min} to {max} characters
```

```properties
# ValidationMessages_vi.properties
order.name.size=Tên phải có từ {min} đến {max} ký tự
```

Nếu không cấu hình locale resolver riêng, provider thường dựa vào JVM default locale. Ứng dụng Spring MVC có thể có cách xác định locale khác vì request mang `Accept-Language` và Spring dùng `LocaleContextHolder`.

### 5.2. Spring Boot 3.x tích hợp `MessageSource`

Spring Boot dùng `MessageSource` của ứng dụng để giải quyết message parameters trong constraint templates, sau đó để default Bean Validation interpolator xử lý các phần còn lại. Do đó ứng dụng Boot thường dùng:

```text
src/main/resources/
├── messages.properties
└── messages_vi.properties
```

Với Boot convention, **file cơ sở `messages.properties` nên tồn tại** để message source tự cấu hình. Resource file `messages_vi.properties` cung cấp bản dịch cho locale vi; `messages.properties` cung cấp fallback.

```properties
# application.properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

Spring MessageSource và Jakarta MessageInterpolator là hai API riêng. Việc Boot tích hợp chúng không có nghĩa `{min}` bị thay bằng positional `{0}` của Java MessageFormat. Hãy giữ templates kiểu `{min}`, `{max}`, `{value}` cho Jakarta constraints.

### 5.3. Phân biệt trực tiếp hai API

Spring `MessageSource`:

```java
String message = messageSource.getMessage(
        "order.created",
        new Object[] {42},
        Locale.forLanguageTag("vi"));
```

Với resource text `Đã tạo đơn {0}`, `{0}` là positional argument của MessageFormat.

Jakarta `MessageInterpolator`:

```java
String message = interpolator.interpolate(
        messageTemplate,
        constraintContext,
        Locale.forLanguageTag("vi"));
```

Đây là **fragment minh họa**: `interpolator`, `messageTemplate` và `constraintContext` được cung cấp bởi code khởi tạo/validation, không phải biến tự có trong controller. Interpolator dùng constraint descriptor và hệ thống bundle để xử lý `{min}`, `${...}`. Không gộp hai cách vào một hàm `String.replace(...)`.

### 5.4. Locale theo HTTP request

Với cấu hình Spring MVC mặc định phù hợp:
- `Accept-Language: en` → message English (base bundle hoặc locale bundle).
- `Accept-Language: vi` → message từ `messages_vi.properties`.
- `Accept-Language: vi-VN` → có thể tìm `messages_vi_VN.properties`, rồi `messages_vi.properties`, rồi fallback.
- Locale chưa hỗ trợ → fallback base/provider phù hợp.

Spring dùng `LocaleContextHolder` và có `LocaleContextMessageInterpolator` để liên kết locale đang quản lý với provider. Nếu ứng dụng thay `LocaleResolver`, `MessageSource`, hoặc dùng riêng `Validation.buildDefaultValidatorFactory()` ngoài Spring, cần kiểm tra lại locale resolution.

Thông báo có dấu tiếng Việt cần lưu file ở đúng encoding và được đóng gói vào classpath. Không dựa vào locale của máy CI nếu test có thể gửi locale rõ ràng.

## 6. EL expressions: điều kiện, giá trị đang được kiểm tra và formatter

Jakarta EL cho phép dùng biểu thức `${...}` khi provider hỗ trợ. Một số biến/ngữ cảnh được cung cấp gồm:

| Biến/đối tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `min` / `max` / `value` | Annotation attributes | `${value > 1 ? 's' : ''}` |
| `validatedValue` | Giá trị đang bị validate | `${validatedValue}` |
| `formatter` | Formatter hỗ trợ theo locale | `${formatter.format('%.2f', validatedValue)}` |
| Custom EL variable | Do provider-specific API thêm | `${actual}` |

### 6.1. Số ít/số nhiều với constraint attribute

```java
@Min(
    value = 2,
    message = "At least {value} item${value > 1 ? 's' : ''} required"
)
int quantity;
```

Khi `quantity=1`, rule yêu cầu tối thiểu 2 và thông báo có thể là:

```text
At least 2 items required
```

`{value}` → `2`, còn `${value > 1 ? 's' : ''}` → `s`. EL expression dùng **attribute `value`**, không phải `quantity`.

Đối với ngôn ngữ có quy tắc số nhiều phức tạp, đừng cố nhét mọi pluralization vào một EL ternary; một hệ thống ICU MessageFormat hoặc frontend i18n có thể phù hợp hơn.

### 6.2. `${validatedValue}`

```java
@Size(min = 3, max = 8,
      message = "Value ${validatedValue} must have {min}..{max} chars")
String publicTag;
```

Nếu `publicTag="AB"`, có thể nhận `Value AB must have 3..8 chars`. Đây là **minh họa kỹ thuật**, không phải mẫu dùng cho password, token, email hoặc dữ liệu riêng tư.

Với API production, trả field + error code + limits thường an toàn hơn trả nguyên `validatedValue`. Ngay cả khi interpolator xử lý escaping, dữ liệu bị từ chối vẫn có thể lộ trong response/logs.

### 6.3. `formatter`

```java
@DecimalMax(
    value = "100.00",
    message = "Actual ${formatter.format('%.2f', validatedValue)} exceeds {value}"
)
BigDecimal amount;
```

Đây là fragment minh họa. Với input `120.567`, trong locale dùng dấu chấm thập phân có thể định dạng thành `120.57`; locale dùng dấu phẩy có thể hiển thị `120,57`. Không sử dụng một stdout áp dụng cho mọi locale.

### 6.4. EL không phải phép thay `{...}` khác tên

`{validatedValue}` không mặc nhiên có nghĩa đặc biệt như `${validatedValue}`. Tương tự, nếu custom validator dùng `addExpressionVariable("actual", 2)`, placeholder tương ứng là `${actual}` **và** cần EL được bật, khác với `addMessageParameter("actual", 2)` + `{actual}`.

## 7. Escaping: đếm đúng các lớp cú pháp

Theo Hibernate Validator, message descriptors dùng:

| Cú pháp descriptor | Kết quả |
| --- | --- |
| `\{` | Ký tự `{` literal |
| `\}` | Ký tự `}` literal |
| `\$` | Ký tự `$` literal |
| `\\` | Ký tự `\` literal |

Một chuỗi message có thể đi qua **hai lớp**: Java string literal hoặc `.properties` loader, rồi mới tới message interpolator. Vì vậy số dấu backslash bạn cần gõ **trong mã nguồn** có thể nhiều hơn số dấu interpolator nhận.

Java source:

```java
String template = "Use \\{min\\} literally";
```

Chuỗi runtime chứa `\{min\}` để interpolator không thay `min`. Trong `.properties`, để truyền một backslash qua properties parser thường dùng:

```properties
example.literal=Use \\{min\\} literally
```

Test message thật sau khi nạp file; cấu hình MessageSource/MessageFormat có thể tạo một lớp xử lý bổ sung. Không sao chép escaping của Java string sang properties một cách máy móc.

## 8. Custom constraint có tham số động

### 8.1. Tại sao attribute tĩnh chưa đủ?

Giả sử rule là “tag dài ít nhất 4 ký tự”. `{min}` lấy được từ annotation:

```java
@MinTextLength(min = 4)
String tag;
```

Nhưng khi `tag="AB"`, con số **2** không nằm trên annotation. Phải đo `value.length()` trong validator và đưa vào thông báo.

Hibernate Validator mở rộng Jakarta `ConstraintValidatorContext` bằng `HibernateConstraintValidatorContext`, có `addMessageParameter`:

```java
HibernateConstraintValidatorContext hv =
        context.unwrap(HibernateConstraintValidatorContext.class);

hv.disableDefaultConstraintViolation();
hv.addMessageParameter("actual", value.length())
  .buildConstraintViolationWithTemplate("{order.tag.min}")
  .addConstraintViolation();
```

Trong bundle:

```properties
order.tag.min=Tag must have at least {min} characters, actual {actual}
```

Kết quả với `min=4` và input có độ dài 2:

```text
Tag must have at least 4 characters, actual 2
```

- `{min}`: attribute static `min()` của `@MinTextLength`.
- `{actual}`: dynamic parameter được thêm lúc `isValid()`.
- `{order.tag.min}`: key của bundle.

### 8.2. `addExpressionVariable` là một con đường khác

```java
hv.addExpressionVariable("actual", value.length());
```

Trường hợp này dùng `${actual}` với EL. Khi chỉ cần in số 2, **ưu tiên `addMessageParameter`** vì đơn giản, không cần bật EL trong custom violation.

### 8.3. Phạm vi provider-specific

`HibernateConstraintValidatorContext` và `addMessageParameter` là API riêng của Hibernate Validator. Nếu chuyển sang Jakarta Validation provider khác, custom validator cần được điều chỉnh. Các annotation attributes thông thường như `{min}` vẫn theo đặc tả chung.

## 9. EL feature levels và phòng tránh expression injection

Hibernate Validator 8.x cho phép cấu hình `ExpressionLanguageFeatureLevel`:

| Level | Khả năng |
| --- | --- |
| `NONE` | Tắt interpolation Jakarta EL |
| `VARIABLES` | Biến EL được đưa vào, resource và formatter |
| `BEAN_PROPERTIES` | Thêm khả năng đọc bean properties |
| `BEAN_METHODS` | Thêm khả năng gọi method; phạm vi rộng, có rủi ro cao |

**Theo default của Hibernate Validator 8.x:**
- Constraint messages được khai báo trên annotation dùng mức `BEAN_PROPERTIES`.
- Custom violations tạo từ `ConstraintValidatorContext` có **EL disabled theo mặc định**.
- Khi custom violation cần EL, Hibernate cung cấp `enableExpressionLanguage()` trên builder và các overload chọn mức feature level.

Provider properties liên quan:

```properties
hibernate.validator.constraint_expression_language_feature_level=bean-properties
hibernate.validator.custom_violation_expression_language_feature_level=none
```

Các dòng trên là **Hibernate Validator provider properties**, không nên mặc định rằng Spring Boot tự bind chúng từ `application.properties` như các thuộc tính của Boot. Có thể cấu hình bằng Hibernate Validator bootstrap hoặc `ValidationConfigurationCustomizer` của Boot và kiểm tra bằng test.

Không bật `BEAN_METHODS` chỉ để hiển thị một con số trong message. Không nối user input trực tiếp vào EL message template:

```java
String unsafe = "Invalid: " + userText;
context.buildConstraintViolationWithTemplate(unsafe)
       .addConstraintViolation();
```

Đoạn trên là **anti-pattern**: user input có thể chứa cú pháp message/EL và ảnh hưởng đến nội suy nếu các features bị bật. Dùng key cố định, thêm value thông qua tham số được escape phù hợp, không trả thông tin nhạy cảm.

### 9.1. `ParameterMessageInterpolator` không hỗ trợ EL

Hibernate Validator có `org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator` để nội suy parameters **không cần Jakarta EL**. Với interpolator này, những `${...}` có thể không được xử lý, kể cả một số built-in messages có EL. Khi test câu có EL, hãy kiểm tra đúng provider và interpolator đang hoạt động.

### 9.2. Không coi EL là “template engine tổng quát”

Message interpolation được thiết kế để giải thích ràng buộc, không phải chỗ chạy script từ database/client. Sử dụng message key và constraint attributes cho đa số tình huống; để logic ngôn ngữ phức tạp hơn ở một i18n system chuyên dụng.

## 10. Project chạy được: Spring Boot 3.5.6, Java 17, en/vi

Ứng dụng có:
- Request DTO dùng `@NotBlank`, `@Size`, `@Min`, custom `@MinTextLength`.
- Resource `messages.properties` (English fallback) và `messages_vi.properties`.
- `@RestControllerAdvice` trả danh sách field và message.
- `MockMvc` kiểm tra tiếng Anh/Việt và cả tham số động.
- Test Jakarta `Validator` xác nhận `getMessageTemplate()` vẫn là key gốc.

### 10.1. Cây thư mục

```text
constraint-message-demo/
├── pom.xml
├── src/main/
│   ├── java/demo/messages/
│   │   ├── MessageDemoApplication.java
│   │   ├── OrderRequest.java
│   │   ├── MinTextLength.java
│   │   ├── MinTextLengthValidator.java
│   │   ├── OrderController.java
│   │   └── ErrorAdvice.java
│   └── resources/
│       ├── application.properties
│       ├── messages.properties
│       └── messages_vi.properties
└── src/test/java/demo/messages/
    └── MessageInterpolationTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>constraint-message-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
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
```

Spring Boot parent quản lý các phiên bản dependencies. `spring-boot-starter-validation` đưa Bean Validation provider phù hợp, thường là Hibernate Validator. Ứng dụng không tạo thêm một `ValidatorFactory` cho mỗi request.

### 10.3. `application.properties`

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
```

### 10.4. `messages.properties` (English fallback)

```properties
order.name.required=Name is required
order.name.size=Name must contain between {min} and {max} characters
order.quantity.min=At least {value} item${value > 1 ? 's' : ''} required
order.tag.required=Tag is required
order.tag.min=Tag must have at least {min} characters, actual {actual}
```

### 10.5. `messages_vi.properties`

```properties
order.name.required=Vui lòng nhập tên
order.name.size=Tên phải có từ {min} đến {max} ký tự
order.quantity.min=Số lượng tối thiểu là {value}
order.tag.required=Vui lòng nhập thẻ
order.tag.min=Thẻ phải có ít nhất {min} ký tự, thực tế {actual}
```

Các thông báo tiếng Việt không cần EL để xử lý số nhiều. File English cố ý dùng EL nhằm minh họa logic, không phải yêu cầu rằng mọi bản dịch phải có expression.

### 10.6. `MessageDemoApplication.java`

```java
package demo.messages;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessageDemoApplication.class, args);
    }
}
```

### 10.7. `MinTextLength.java`

```java
package demo.messages;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = MinTextLengthValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface MinTextLength {
    String message() default "{order.tag.min}";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
    int min() default 4;
}
```

`@MinTextLength` có attribute `min`, do đó message bundle có thể dùng `{min}`. Annotation target `FIELD` cho phép ràng buộc trên field được sinh ra từ record component trong Java; target `PARAMETER` hỗ trợ hợp đồng parameter nơi phù hợp.

### 10.8. `MinTextLengthValidator.java`

```java
package demo.messages;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext;

public class MinTextLengthValidator
        implements ConstraintValidator<MinTextLength, String> {

    private int min;

    @Override
    public void initialize(MinTextLength constraint) {
        min = constraint.min();
    }

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            // @NotBlank/@NotNull xác minh sự hiện diện nếu cần.
            return true;
        }

        int actual = value.length();
        if (actual >= min) {
            return true;
        }

        var hibernate = context.unwrap(
                HibernateConstraintValidatorContext.class);
        hibernate.disableDefaultConstraintViolation();
        hibernate.addMessageParameter("actual", actual)
                .buildConstraintViolationWithTemplate("{order.tag.min}")
                .addConstraintViolation();
        return false;
    }
}
```

`String.length()` đếm UTF-16 code units, không nhất thiết số grapheme clusters người dùng nhìn thấy. Nếu ứng dụng cần đếm ký tự Unicode theo cách khác, thay implementation rule và test các trường hợp emoji/tổ hợp dấu; không ngầm đồng nhất `String.length()` với “số ký tự hiển thị”.

### 10.9. `OrderRequest.java`

```java
package demo.messages;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record OrderRequest(
        @NotBlank(message = "{order.name.required}")
        @Size(min = 3, max = 8,
              message = "{order.name.size}")
        String displayName,

        @Min(value = 2,
             message = "{order.quantity.min}")
        int quantity,

        @NotBlank(message = "{order.tag.required}")
        @MinTextLength(min = 4)
        String tag) {
}
```

Nếu cần biết “quantity thiếu” khác “quantity bằng 0”, dùng `Integer` + `@NotNull` trong hệ thống thật. Ở demo dùng primitive `int` để tập trung vào `@Min` và message `{value}`.

### 10.10. `OrderController.java`

```java
package demo.messages;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.ok(Map.of(
                "accepted", true,
                "displayName", request.displayName()));
    }
}
```

`@Valid` trên request DTO kích hoạt Bean Validation sau khi Jackson decode JSON. Class controller không cần `@Validated` để chạy validation của DTO argument. Nếu request không hợp lệ, MVC có thể ném `MethodArgumentNotValidException` trước khi method `create` được gọi.

### 10.11. `ErrorAdvice.java`

```java
package demo.messages;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Comparator;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException exception) {

        var errors = exception.getBindingResult()
                .getFieldErrors().stream()
                .map(e -> Map.of(
                        "field", e.getField(),
                        "message", Objects.toString(
                                e.getDefaultMessage(), "")))
                .sorted(Comparator.comparing(e -> e.get("field")))
                .toList();

        return ResponseEntity.badRequest().body(Map.of("errors", errors));
    }
}
```

Handler trả **message đã nội suy**, không đưa `rejectedValue` hoặc nguyên object vào response. Trường hợp JSON malformed có thể đi qua exception khác; không gộp parsing error và constraint violation.

### 10.12. `MessageInterpolationTest.java`

```java
package demo.messages;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MessageInterpolationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    private static String json(String name, int quantity, String tag) {
        return """
                {"displayName":"%s","quantity":%d,"tag":"%s"}
                """.formatted(name, quantity, tag);
    }

    private MockHttpServletRequestBuilder submit(Locale locale, String json) {
        return post("/api/orders")
                .locale(locale)
                .contentType(MediaType.APPLICATION_JSON)
                .content(json);
    }

    @Test
    void validRequestWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 2, "ABCD")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }

    @Test
    void englishMinMaxAttributesWork() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("AB", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name must contain between 3 and 8 characters"));
    }

    @Test
    void vietnameseMinMaxAttributesWork() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("AB", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tên phải có từ 3 đến 8 ký tự"));
    }

    @Test
    void englishElPluralizationWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 1, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("At least 2 items required"));
    }

    @Test
    void vietnameseQuantityWorks() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("Linh", 1, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Số lượng tối thiểu là 2"));
    }

    @Test
    void dynamicActualParameterEnglishWorks() throws Exception {
        mvc.perform(submit(Locale.ENGLISH,
                json("Linh", 2, "AB")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Tag must have at least 4 characters, actual 2"));
    }

    @Test
    void dynamicActualParameterVietnameseWorks() throws Exception {
        mvc.perform(submit(Locale.forLanguageTag("vi"),
                json("Linh", 2, "AB")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Thẻ phải có ít nhất 4 ký tự, thực tế 2"));
    }

    @Test
    void notBlankMessageIsTranslated() throws Exception {
        // 4 ký tự trắng: @Size vẫn pass, @NotBlank fail.
        mvc.perform(submit(Locale.ENGLISH,
                json("    ", 2, "ABCD")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].message")
                        .value("Name is required"));
    }

    @Test
    void templateAndDescriptorAreDifferentFromFinalMessage() {
        var violations = validator.validate(
                new OrderRequest("AB", 2, "ABCD"));

        assertEquals(1, violations.size());
        ConstraintViolation<OrderRequest> v =
                violations.iterator().next();

        assertEquals("{order.name.size}", v.getMessageTemplate());
        assertEquals("displayName",
                v.getPropertyPath().toString());
        assertEquals(3,
                v.getConstraintDescriptor().getAttributes().get("min"));
    }

    @Test
    void validObjectHasNoViolations() {
        assertTrue(validator.validate(
                new OrderRequest("Linh", 3, "ABCD")).isEmpty());
    }

    @Test
    void malformedJsonIsNotAConstraintViolation() throws Exception {
        mvc.perform(submit(Locale.ENGLISH, "{\"displayName\":"))
                .andExpect(status().isBadRequest());
    }
}
```

Dự án có **11 tests**. Với Maven/JDK 17 và các dependencies tương thích, kỳ vọng tất cả assertion pass. Đây là ví dụ đầy đủ để người học tự chạy; **không** tuyên bố đã chạy test trong lúc soạn bài.

Chạy:

```bash
mvn test
```

Chạy server:

```bash
mvn spring-boot:run
```

## 11. Thử API qua curl

### 11.1. Request hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"displayName":"Linh","quantity":2,"tag":"ABCD"}'
```

Kỳ vọng HTTP **200**:

```json
{"accepted":true,"displayName":"Linh"}
```

### 11.2. `@Size` tiếng Việt

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"displayName":"AB","quantity":2,"tag":"ABCD"}'
```

Kỳ vọng HTTP **400**, body có:

```json
{
  "errors": [
    {
      "field": "displayName",
      "message": "Tên phải có từ 3 đến 8 ký tự"
    }
  ]
}
```

### 11.3. `@Min` English với EL

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"displayName":"Linh","quantity":1,"tag":"ABCD"}'
```

Kỳ vọng HTTP **400**, message `At least 2 items required`. Ngưỡng `2` đến từ attribute `@Min.value`, không phải input `quantity=1`.

### 11.4. Custom parameter `{actual}`

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"displayName":"Linh","quantity":2,"tag":"AB"}'
```

Kỳ vọng HTTP **400**, message `Thẻ phải có ít nhất 4 ký tự, thực tế 2`. Con số `4` từ annotation, `2` do validator tính và đưa qua `addMessageParameter`.

## 12. `getMessageTemplate()`, `getMessage()` và `ConstraintDescriptor`

Nếu gọi Jakarta Validator trực tiếp:

```java
Set<ConstraintViolation<OrderRequest>> violations =
        validator.validate(request);
```

với `OrderRequest.displayName="AB"`, violation có:

- `getMessageTemplate()`: chuỗi `{order.name.size}` do annotation khai báo.
- `getMessage()`: thông báo đã nội suy theo locale, ví dụ `Name must contain between 3 and 8 characters`.
- `getPropertyPath()`: field path `displayName`.
- `getConstraintDescriptor().getAttributes().get("min")`: giá trị `3`.
- `getInvalidValue()`: giá trị `"AB"`, **không nên trả hoặc log trực tiếp nếu có thể chứa dữ liệu riêng tư**.

`getMessageTemplate()` giúp chẩn đoán key bị thiếu; `getMessage()` phù hợp cho display. `ConstraintDescriptor` giúp trả thêm metadata có cấu trúc, chẳng hạn limits để frontend tự diễn đạt.

Với Spring MVC, khi `@Valid @RequestBody` thất bại, `MethodArgumentNotValidException` mang `BindingResult` và `FieldError`. Thông báo trong `FieldError.getDefaultMessage()` thường đã được nội suy; đó không phải cùng object `ConstraintViolation`.

Một API public có thể chọn response:

```json
{
  "field": "displayName",
  "code": "order.name.size",
  "params": {"min": 3, "max": 8}
}
```

Frontend tự tra locale. Nhưng cần thiết kế error code mapping và data disclosure cẩn thận; đừng giả định `getMessageTemplate()` luôn là một business code có thể công bố nguyên trạng.

## 13. Tùy chỉnh `MessageInterpolator` trong Spring

Jakarta giao diện:

```java
public interface MessageInterpolator {
    String interpolate(String template, Context context);
    String interpolate(String template, Context context, Locale locale);
}
```

Spring Framework có `LocalValidatorFactoryBean`, hỗ trợ `setValidationMessageSource(MessageSource)` và `setMessageInterpolator(MessageInterpolator)`. Đây là **hai hướng cấu hình thay thế**, không nên dùng đồng thời trong cùng bean.

Ví dụ ý tưởng Spring Framework thuần:

```java
@Bean
LocalValidatorFactoryBean validator(MessageSource source) {
    LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
    bean.setValidationMessageSource(source);
    return bean;
}
```

Đây là fragment cần imports, cách kết nối vào MVC validator config và quyết định về bean lifecycle. Không đưa bean này vào project Boot mẫu ở mục 10, vì project chủ đích sử dụng Boot auto-configuration.

Spring JavaDoc lưu ý `MessageSource` dùng cho constraint messages phải hỗ trợ resolution tùy chọn, không cấu hình `useCodeAsDefaultMessage=true` gây cản trở fallback provider messages. Nếu cần custom interpolator, ưu tiên bọc/delegate provider interpolator mặc định, không viết lại thuật toán nội suy bằng regex.

### 13.1. Nếu muốn truyền locale tường minh ngoài request

Trong một ứng dụng service/CLI không có HTTP header, bạn có thể gọi `MessageInterpolator#interpolate(template, context, locale)` hoặc cấu hình locale resolution cho ValidatorFactory theo provider. Không tự đổi `Locale.setDefault(...)` trên mỗi request vì đó là trạng thái toàn JVM và có thể gây race condition.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `{order.name.size}` xuất nguyên trong response | Sai key, basename, locale hoặc chưa qua interpolator | Kiểm tra bundle/MessageSource |
| `{min}` không thay thành số | Sai attribute, bị key khác chiếm chỗ, hoặc chỉ String.format ngoài provider | Đọc `ConstraintDescriptor#getAttributes()` |
| `{value}` bị tưởng là giá trị input | `value` là attribute của `@Min` | Phân biệt với `validatedValue` |
| `${validatedValue}` còn nguyên | EL implementation thiếu, feature level tắt hoặc ParameterMessageInterpolator | Kiểm tra provider/interpolator |
| Message English dù `Accept-Language: vi` | Locale resolver hoặc bundle vi sai | Test locale trong MockMvc |
| Tiếng Việt mất dấu | Encoding không đúng | UTF-8 ở source và build/runtime |
| `{actual}` không được thay | Custom validator chưa gọi `addMessageParameter` | Thêm message parameter đúng tên |
| `${actual}` không được thay | Chưa gọi addExpressionVariable, EL chưa bật | Chọn đúng hai cơ chế |
| `${value}` dẫn đến `$2` | Placeholder parameter được thay trước EL | Dùng `{value}` hoặc EL có điều kiện |
| Validation trực tiếp không nhận locale HTTP | Không có request context | Chọn locale khi kiểm tra |
| `@NotBlank` không chạy | Thiếu provider, annotation hoặc bước kích hoạt `@Valid` | Kiểm tra dependencies và controller |
| Trả raw `getInvalidValue()` | Có thể lộ PII/password/token | Trả field + code + limits |
| Tự nối chuỗi user vào message template | Expression injection hoặc nội suy sai | Dùng template cố định và param an toàn |
| Bật `BEAN_METHODS` cho custom violation | Quá nhiều khả năng thực thi EL | Giữ NONE/VARIABLES |
| Nhầm parsing với validation | JSON chưa tạo được object | Phân loại HTTP input error riêng |
| Dựa vào một status HTTP 400 | Không biết nguyên nhân và locale | Assert exception type/message |
| Chỉ test tiếng Anh | Bỏ sót lỗi key/encoding/fallback vi | Test đủ các locale |

## 15. Checklist khi viết message đa ngữ

1. Xác định annotation thực sự sinh violation và những attributes có thể sử dụng.
2. Dùng message key ổn định như `order.name.size`, tránh key quá chung.
3. Tạo bundle cơ sở `messages.properties` nếu sử dụng Spring Boot message source convention.
4. Tạo bundle locale `messages_vi.properties` với UTF-8.
5. Bảo toàn `{min}`/`{max}`/`{value}` trong bản dịch, không tự thay chúng bằng số cố định.
6. Hiểu thứ tự: bundle lookup → attributes → EL.
7. Tránh key `min`/`max`/`value` trong resource bundle vì có thể va chạm attributes.
8. Khi dùng dynamic data, ưu tiên `addMessageParameter` với template cố định.
9. Khi cần EL, xác minh provider, feature level và các yêu cầu an toàn.
10. Không dùng `validatedValue` để lộ dữ liệu bí mật.
11. Kiểm thử ít nhất en, vi, một locale fallback và key thiếu.
12. Assert cả `getMessageTemplate()` và `getMessage()` ở đường programmatic nếu cần ổn định error code.
13. Với controller, dùng `MockMvc`/HTTP integration test để xác minh locale thực tế.
14. Với error response, tách validation failures khỏi malformed JSON.
15. Sau khi nâng cấp Spring/Hibernate, chạy lại tests vì default interpolation có thể thay đổi.

## 16. Bài tập tự luyện

1. Đổi `@Size(min=3,max=8)` thành `@Size(min=4,max=10)`; giữ bundle và kiểm tra thông báo tự đổi.
2. Đổi thứ tự `{min}` và `{max}` trong tiếng Việt, giải thích vì sao các giá trị vẫn được thế đúng.
3. Thử `@Min(value=1)` với input 0; EL số ít/số nhiều thay đổi thế nào?
4. Xóa `messages_vi.properties` và kiểm tra fallback khi gửi `Accept-Language: vi`.
5. Đổi key annotation sang một key không tồn tại; so sánh `getMessageTemplate()` và `getMessage()`.
6. Bỏ `addMessageParameter("actual", actual)` trong custom validator và quan sát message.
7. Thêm `addExpressionVariable` vào custom violation nhưng chưa bật EL. Giải thích khác biệt với `addMessageParameter`.
8. Dùng `ParameterMessageInterpolator` trong một test riêng; biểu thức số nhiều có còn được đánh giá không?
9. Tạo một constraint `@DecimalMax` trên `BigDecimal`, dùng formatter EL và test nhiều locale.
10. Thêm test trả error code/parameters thay vì câu đã dịch; kiểm tra không lộ input.
11. Đổi message key theo cấu trúc `module.entity.field.rule` rồi tổ chức lại resource files.
12. Dùng custom Spring MessageSource và kiểm tra fallback đến default provider messages khi key thiếu.
13. Viết test tách parsing error của JSON sai cấu trúc với Bean Validation error của quantity=1.
14. Thử escape literal `{min}` trong Java và `.properties` để thấy hai tầng parser.
15. Thêm request DTO nested dùng `@Valid` và xây bản dịch cho constraint trên nested property.

**Ghi nhớ:** Thông báo đa ngữ dùng **resource key** để chọn câu, **constraint attributes** (`{min}`, `{max}`, `{value}`) để đưa ngưỡng tĩnh vào câu, **dynamic parameters** để truyền dữ liệu tính lúc validation, và **EL** khi cần điều kiện/format. Trong Spring Boot, `MessageSource` giúp tra en/vi nhưng Jakarta MessageInterpolator vẫn chịu trách nhiệm hoàn tất quá trình nội suy. Ưu tiên thiết kế đơn giản, an toàn và kiểm thử theo locale.

## 17. Tài liệu chính thức

- [Jakarta Validation 3.1 — Message interpolation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Hibernate Validator 8 — Chapter 4: Interpolating constraint error messages](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Hibernate Validator 8 — EL feature levels và custom violations](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#section-expression-language-features)
- [Hibernate Validator 8 — `MessageParameterEscaping`](https://docs.hibernate.org/validator/8.0/api/org/hibernate/validator/messageinterpolation/MessageParameterEscaping.html)
- [Spring Boot 3.5 — Validation và MessageSource](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — `LocalValidatorFactoryBean`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework 6.2 — `LocaleContextMessageInterpolator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html)
- [Spring Framework 6.2 — Spring MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)