# Thiết kế form có địa chỉ lồng, danh sách và Map trong Spring MVC

## 1. Mục tiêu của bài thực hành

Một biểu mẫu đặt giao hàng không chỉ gồm vài `String` phẳng. Nó có thể chứa:

- Thông tin người đặt: `customerName`.
- **Địa chỉ lồng nhau**: `address.street`, `address.city`, `address.postalCode`.
- **Danh sách người nhận**: `recipients[0].name`, `recipients[0].email`, `recipients[1].name`...
- **Map tùy chọn**: `preferences[language]`, `preferences[deliveryWindow]`.

Mục tiêu là xây **một biểu mẫu HTML thực sự** bằng Spring MVC + Thymeleaf, bind vào một DTO JavaBean riêng, xử lý validation đệ quy, nhận lỗi chính xác ở từng property path và giới hạn những field client được phép gửi.

Kết quả mong muốn:

1. Trang `GET /delivery` có sẵn hai dòng người nhận, địa chỉ và hai tùy chọn.
2. Người dùng nhập form hoặc nhấn **Thêm người nhận** để có dòng thứ ba.
3. `POST /delivery` bind các request parameters qua `@ModelAttribute("deliveryForm")`.
4. `@Valid` kiểm tra `AddressForm`, từng `RecipientForm` và giá trị bên trong `Map`.
5. `BindingResult` giữ lỗi theo những đường dẫn như `address.city` và `recipients[1].email`.
6. `@InitBinder` khai báo allowlist cho đúng các nested paths, indexed paths và Map keys.
7. Controller từ chối field ngoài hợp đồng (ví dụ `accountRole=ADMIN` hoặc `preferences[admin]=true`).
8. MockMvc kiểm tra cả view GET, POST hợp lệ, POST invalid, dòng bổ sung và over-posting.

**Ngữ cảnh kỹ thuật:** Java 17+, Spring Boot 3.4.x, Spring Framework 6.2, Jakarta Validation, Spring MVC Servlet stack và Thymeleaf. Đây là **form-urlencoded data binding**, không phải Jackson `@RequestBody` JSON. Những khác biệt của JSON và WebFlux sẽ được nêu rõ, không trộn lẫn pipeline.

## 2. Thiết kế cấu trúc object trước khi viết HTML

Một request có cấu trúc logic:

```text
DeliveryForm
├── customerName : String
├── address : AddressForm
│   ├── street : String
│   ├── city : String
│   └── postalCode : String
├── recipients : List<RecipientForm>
│   ├── [0]
│   │   ├── name : String
│   │   └── email : String
│   └── [1]
│       ├── name : String
│       └── email : String
└── preferences : Map<String, String>
    ├── [language]       -> "vi" hoặc "en"
    └── [deliveryWindow] -> "day" hoặc "evening"
```

Chúng ta không lưu toàn bộ object graph vào database trong demo. `DeliveryForm` là **input command DTO**, không phải JPA entity. Điều này quan trọng vì web data binding có thể gán giá trị vào những property có setter. Bind trực tiếp entity với `id`, `role`, `tenantId` hoặc `verified` dễ tạo mass-assignment risk.

### 2.1. Phân biệt dấu chấm và ngoặc vuông

Spring `DataBinder`/`BeanWrapper` dùng property paths theo JavaBeans convention:

| Request parameter name | Dữ liệu đích | Ý nghĩa |
| --- | --- | --- |
| `customerName` | `form.customerName` | Property cấp một |
| `address.street` | `form.address.street` | Property trong object lồng |
| `address.city` | `form.address.city` | Chuỗi trong nested object |
| `recipients[0].name` | `form.recipients.get(0).name` | Property của List element tại index 0 |
| `recipients[1].email` | `form.recipients.get(1).email` | Property của List element tại index 1 |
| `preferences[language]` | `form.preferences.get("language")` | Map entry với key language |
| `preferences[deliveryWindow]` | `form.preferences.get("deliveryWindow")` | Map entry với key deliveryWindow |

Trong **HTTP name attribute**, không cần đặt dấu nháy quanh key đơn giản: `preferences[language]`. Dấu `[0]` là **index số** của List; `[language]` là **key String** của Map.

Ví dụ raw payload:

```text
customerName=Lan
address.street=12 Nguyen Hue
address.city=Ho Chi Minh City
address.postalCode=70000
recipients[0].name=Lan
recipients[0].email=lan@example.org
recipients[1].name=Minh
recipients[1].email=minh@example.org
preferences[language]=vi
preferences[deliveryWindow]=day
```

Các dòng trên mô tả **tên và giá trị tham số**; chúng không phải JSON object và không có dấu chấm lồng theo JSON. HTTP form-urlencoded truyền chuỗi tham số phẳng, Spring binder diễn giải dấu chấm/ngoặc để xây object graph.

### 2.2. Không dùng tên HTML độc lập với DTO

Sai về mặt hợp đồng:

```html
<input name="city">
<input name="recipient.email">
<input name="language">
```

Nếu DTO chỉ có `address.city`, `recipients` là List và `preferences` là Map, những tên trên không diễn đạt đúng target path. Spring không có lý do để tự đoán `city` phải gắn vào `address.city`.

Đúng:

```html
<input name="address.city">
<input name="recipients[0].email">
<input name="preferences[language]">
```

Để tránh gõ sai tên khi làm view, dùng `th:object` + `th:field` của Thymeleaf. Chúng kết nối HTML với form-backing object và Spring BindingResult, đồng thời hỗ trợ hiển thị lại giá trị sau khi validation thất bại.

## 3. @ModelAttribute, WebDataBinder và BindingResult phối hợp thế nào?

Khi một request đến controller:

```text
Browser POST application/x-www-form-urlencoded
             |
             v
Servlet request parameters (name -> String)
             |
             v
@ModelAttribute("deliveryForm")
             |
             v
Form object lấy từ Model hoặc tạo mới
             |
             v
WebDataBinder:
  - allowlist/disallowed fields
  - nested property access
  - indexed List access
  - Map[key] access
  - type conversion
             |
             v
@Valid -> Jakarta Bean Validation:
  - nested @Valid AddressForm
  - List<@Valid RecipientForm>
  - Map<String, @NotBlank String>
             |
             v
BindingResult (ngay sau form argument)
             |
             +--> hasErrors(): render lại form cùng lỗi
             |
             +--> không lỗi: gọi service, render confirmation
```

Spring Framework 6.2 cho phép `@ModelAttribute` dùng constructor binding và property/setter binding. Ví dụ này cố ý chọn **JavaBean setters** để làm rõ các property paths của biểu mẫu HTML.

**Lưu ý:** `BindingResult` hoặc `Errors` phải đặt **ngay sau** argument được bind/validate:

```java
public String submit(
        @Valid @ModelAttribute("deliveryForm") DeliveryForm form,
        BindingResult errors,
        Model model) {
    // ...
}
```

Không chen `Model`, `Locale`, `@RequestParam` hay một DTO khác giữa `form` và `errors`. Nếu không có result ở vị trí phù hợp, validation failure có thể chuyển sang `MethodArgumentNotValidException` và controller không chạy nhánh xử lý cục bộ.

## 4. Quy tắc thiết kế DTO lồng nhau

### 4.1. Mỗi lớp chỉ nhận dữ liệu đúng trách nhiệm

- `AddressForm`: các field về địa chỉ.
- `RecipientForm`: tên/email người nhận.
- `DeliveryForm`: kết hợp các phần và những preference keys được cho phép.
- `DeliverySummary`: output dùng cho trang xác nhận, không phải toàn bộ domain entity.

Không đưa `userId`, `accountRole` hay `billingLimit` từ domain entity vào một form chỉ cần dữ liệu giao hàng.

### 4.2. Khởi tạo nested object và collection

Với property binding, một DTO có:

```java
private AddressForm address = new AddressForm();
private List<RecipientForm> recipients = new ArrayList<>();
private Map<String, String> preferences = new LinkedHashMap<>();
```

sẽ có những container sẵn để binder truy cập. Nếu nested path null, Spring `DataBinder` có khả năng auto-grow object graph ở chế độ mặc định, nhưng không nên phụ thuộc vào hành vi ấy như một hợp đồng nghiệp vụ. Khởi tạo ở constructor làm form GET có dữ liệu cấu trúc cần render và giúp tests rõ ràng.

**Không dùng `List.of(...)` hoặc `Map.of(...)` để khởi tạo một cấu trúc mà binder cần mutate.** Hai factory này tạo immutable collections/maps. Dùng `ArrayList` và `LinkedHashMap` cho form có thể thay đổi.

### 4.3. Kiểm tra đệ quy với @Valid

Một annotation `@Valid` trên field object:

```java
@Valid
@NotNull
private AddressForm address;
```

khiến Jakarta Validator đi sâu vào các constraints của `AddressForm`. Không có `@Valid`, các constraints trên `address.street`/`address.city` có thể không được đánh giá khi bạn validate root `DeliveryForm`.

Đối với List:

```java
@NotEmpty
@Size(max = 3)
private List<@Valid RecipientForm> recipients;
```

- `@NotEmpty`: danh sách phải có ít nhất một phần tử.
- `@Size(max=3)`: tối đa ba người nhận trong hợp đồng demo.
- `@Valid` trên element type: mỗi `RecipientForm` được kiểm tra.
- `@NotBlank`/`@Email` nằm trong `RecipientForm` sẽ tạo violations với indexed paths.

Đối với Map:

```java
private Map<String, @NotBlank String> preferences;
```

đặt `@NotBlank` trên **value String** thay vì lên toàn bộ Map. Nếu muốn Map không được rỗng, thêm `@NotEmpty` trên field Map. Với Map keys động, cũng có thể đặt constraints trên key type argument, nhưng trong demo key set được whitelist cụ thể tại binder nên không cần mở toàn bộ không gian key.

**Null semantics:** constraint như `@Email` thường cho null hợp lệ để tách yêu cầu bắt buộc; kết hợp `@NotBlank` khi email không được bỏ trống.

## 5. @InitBinder: giới hạn những trường được phép bind

Nếu chỉ dựa vào DTO có setters, một client có thể gửi thêm parameters không xuất hiện trên HTML. Spring khuyến nghị dùng DTO riêng hoặc constructor binding; khi dùng property binding, nên có **positive allowedFields**.

Ví dụ:

```java
@InitBinder("deliveryForm")
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "customerName",
            "address.street",
            "address.city",
            "address.postalCode",
            "recipients[*].name",
            "recipients[*].email",
            "preferences[language]",
            "preferences[deliveryWindow]"
    );
    binder.setAutoGrowCollectionLimit(3);
}
```

**Chú thích:**

- `"customerName"`: một scalar field.
- `"address.city"`: chỉ đúng property được phép; không dùng `"address*"` quá rộng.
- `"recipients[*].email"`: wildcard index cho List, tương thích với `recipients[0].email`, `recipients[1].email`...
- `"preferences[language]"` và `"preferences[deliveryWindow]"`: **chỉ hai key đã công bố**, không dùng `"preferences*"`.
- `setAutoGrowCollectionLimit(3)`: giới hạn cơ chế tự tăng kích thước indexed collections trong property binding, **không phải** tổng giới hạn body/HTTP request.
- `@InitBinder("deliveryForm")` áp dụng theo **model attribute objectName**. Nếu đổi tên `@ModelAttribute("deliveryForm")`, phải cập nhật binder.
- `setAllowedFields(...)` dùng patterns **phân biệt hoa/thường** trong Spring Framework 6.x; đừng dựa vào case folding.

### 5.1. Tại sao cần xem getSuppressedFields?

Khi client gửi:

```text
accountRole=ADMIN
preferences[admin]=true
```

hai keys không nằm trong allowlist. `DataBinder` có thể **suppress** chúng và lưu danh sách trong `BindingResult#getSuppressedFields()`. Tuy nhiên `hasErrors()` **không tự động thành true chỉ vì có suppressed fields**.

Trong bài, controller kiểm tra:

```java
if (result.getSuppressedFields().length > 0) {
    result.reject("unexpected.fields",
            "Form contains unsupported fields");
}
```

Việc chuyển suppressed fields thành global error là **policy có chủ đích** của ứng dụng. Nếu API chọn ignore unknown fields vì tương thích, service vẫn phải không dùng chúng; không xem “bỏ qua” là có thể yên tâm bỏ authorization.

Đừng trả raw values của field bị suppress lên giao diện hoặc log không redaction. Chỉ cần mã lỗi ổn định hoặc thông báo chung.

### 5.2. Cẩn trọng với wildcard và index lớn

Một pattern như `"recipients[*].email"` cho phép **đường dẫn email ở mọi index khớp wildcard**, không tự chứng minh index đó được cấp quyền hay phù hợp với kích thước dữ liệu.

Cần kết hợp:

- `@Size(max=3)`/business limit.
- `setAutoGrowCollectionLimit(3)`.
- Server-side request parameter count/body size limits.
- Kiểm tra những index bất thường trước khi binder đụng vào (khi API public cần contract 4xx nhất quán).
- Quy tắc giới hạn IDs của các phần tử khi cập nhật dữ liệu đã tồn tại.

Một index vượt giới hạn auto-grow có thể phát sinh binding exception ở infrastructure, **không mặc nhiên chuyển thành FieldError dễ đọc**. Đừng hứa rằng mọi payload `recipients[999999]` sẽ luôn trả validation 400. Thử hành vi trên Spring version thực tế và kiểm soát request sớm.

### 5.3. Constructor binding và @RequestBody có phạm vi khác

`setAllowedFields` kiểm soát **property/setter binding**. Nó không phải bộ lọc tổng quát cho constructor arguments hoặc các JSON keys được Jackson deserialize qua `@RequestBody`. Nếu chuyển form-urlencoded thành JSON REST, hãy dùng input DTO/record riêng, cấu hình unknown-property policy của Jackson khi cần và test JSON pipeline.

Spring 6.2 có `setDeclarativeBinding(true)` để ưu tiên constructor binding, chỉ cho property binding khi có allowed fields. Đây là lựa chọn đáng cân nhắc khi chuẩn hóa nhiều forms, nhưng cần regression tests, nhất là đối với nested lists và Map.

## 6. Project Java 17: form Thymeleaf đầy đủ

### 6.1. Cấu trúc thư mục

```text
nested-form-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── NestedFormApplication.java
    │   │   ├── AddressForm.java
    │   │   ├── RecipientForm.java
    │   │   ├── DeliveryForm.java
    │   │   ├── DeliverySummary.java
    │   │   ├── DeliveryService.java
    │   │   └── DeliveryController.java
    │   └── resources/templates/
    │       ├── delivery-form.html
    │       └── delivery-success.html
    └── test/java/demo/
        ├── DeliveryBinderTest.java
        └── DeliveryMvcTest.java
```

Dự án chủ đích dùng một template engine thật để xem chính xác tên field được render. Không cần database; `DeliveryService` chỉ trả summary. Trong sản phẩm thật, nơi lưu dữ liệu, authentication/authorization và persistence invariants phải được thiết kế bổ sung.

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>nested-form-demo</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Boot parent quản lý versions của Spring MVC và Thymeleaf, tránh cấu hình thủ công các version không tương thích. `spring-boot-starter-validation` cung cấp Jakarta Bean Validation provider, thường là Hibernate Validator.

### 6.3. src/main/java/demo/NestedFormApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NestedFormApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedFormApplication.class, args);
    }
}
```

### 6.4. src/main/java/demo/AddressForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class AddressForm {

    @NotBlank
    @Size(max = 120)
    private String street;

    @NotBlank
    @Size(max = 80)
    private String city;

    // Pattern minh họa các mã bưu chính đơn giản;
    // production phải có policy theo quốc gia.
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9 -]{3,12}")
    private String postalCode;

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
```

**Giải thích:** `AddressForm` là bean lồng, có public no-arg constructor ngầm định và public getters/setters. `@NotBlank` ngăn giá trị rỗng/blank; `@Size` giới hạn chiều dài; `@Pattern` chỉ là chính sách bài học chứ không phải validator bưu chính toàn cầu.

Khi người dùng bỏ trống thành phố, validation tạo lỗi ở path `address.city` vì root `DeliveryForm` sẽ có `@Valid` trên `address`.

### 6.5. src/main/java/demo/RecipientForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RecipientForm {

    @NotBlank
    @Size(max = 80)
    private String name;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Mỗi entry của List là một `RecipientForm` hoàn chỉnh. Validation trên `email` sẽ được thực thi nếu root form có cascade `@Valid` đến element. `@Email` chỉ kiểm tra định dạng theo provider; không chứng minh email đã được xác minh hay người nhận đã đồng ý.

### 6.6. src/main/java/demo/DeliveryForm.java

```java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class DeliveryForm {

    @NotBlank
    @Size(max = 80)
    private String customerName;

    @Valid
    @NotNull
    private AddressForm address = new AddressForm();

    @NotEmpty
    @Size(max = 3)
    private List<@Valid RecipientForm> recipients =
            new ArrayList<>();

    @NotEmpty
    private Map<String, @NotBlank String> preferences =
            new LinkedHashMap<>();

    public DeliveryForm() {
        // Có sẵn 2 dòng người nhận trên GET /delivery.
        recipients.add(new RecipientForm());
        recipients.add(new RecipientForm());

        // Hai key hợp lệ được khởi tạo và render.
        preferences.put("language", "vi");
        preferences.put("deliveryWindow", "day");
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public AddressForm getAddress() {
        return address;
    }

    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public List<RecipientForm> getRecipients() {
        return recipients;
    }

    public void setRecipients(List<RecipientForm> recipients) {
        this.recipients = recipients;
    }

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void setPreferences(
            Map<String, String> preferences) {
        this.preferences = preferences;
    }
}
```

**Phân tích các quyết định thiết kế:**

1. `address` được khởi tạo ngay thay vì đợi binder tạo vì đây là dữ liệu bắt buộc của biểu mẫu.
2. `recipients` là mutable `ArrayList` và có sẵn 2 entries. Điều đó cho phép Thymeleaf render hai dòng với paths `recipients[0].name`, `recipients[1].name`.
3. `@NotEmpty @Size(max=3)` mô tả giới hạn 1–3 recipients, được kiểm soát bổ sung ở binder.
4. `List<@Valid RecipientForm>` khiến provider validate mỗi phần tử.
5. `preferences` là mutable `LinkedHashMap` với hai keys cố định. `LinkedHashMap` giữ thứ tự chèn ổn định cho phần hiển thị; không có ý nghĩa bảo mật riêng.
6. `Map<String, @NotBlank String>` thể hiện **container-element constraints** cho map values. Các giá trị lạ như `language=javascript` không tự bị `@NotBlank` chặn, vì đó là chuỗi không blank; controller sẽ kiểm tra tập giá trị hợp lệ.
7. Dùng JavaBean getters/setters để property binder hoạt động. Nếu đổi sang record constructor binding, phải thiết kế lại cách khởi tạo List/Map và hiểu sự khác biệt về `allowedFields`.

**Điểm cần nhớ:** khi user gửi form mà không có một field (ví dụ `preferences[language]`), model factory tạo mặc định `vi` và binder có thể giữ giá trị đó. Đây là **defaulting semantics có chủ đích** của demo. Trong API cần phân biệt field missing/explicit null hoặc bắt buộc client chọn tùy chọn, hãy tạo DTO mới không tự điền default và dùng validation/tri-state phù hợp.

### 6.7. src/main/java/demo/DeliverySummary.java

```java
package demo;

public record DeliverySummary(
        String customerName,
        String city,
        int recipientCount,
        String language,
        String deliveryWindow) {
}
```

Output DTO chỉ chứa summary cần thiết, không xuất toàn bộ địa chỉ/email người nhận lên trang xác nhận. Một hệ thống thật cần policy riêng về dữ liệu được phép xem và lưu.

### 6.8. src/main/java/demo/DeliveryService.java

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    public DeliverySummary review(DeliveryForm form) {
        // Không tự tạo JPA entity hay ghi database
        // trong bài học về data binding.
        return new DeliverySummary(
                form.getCustomerName().strip(),
                form.getAddress().getCity().strip(),
                form.getRecipients().size(),
                form.getPreferences().get("language"),
                form.getPreferences().get("deliveryWindow")
        );
    }
}
```

Service chỉ làm projection sau khi controller xác định form hợp lệ. Trong ứng dụng có nhiều entrypoints ngoài HTTP, **đừng tin rằng service luôn chỉ nhận DTO đã qua @Valid**. Cần domain/business validation ở service boundary khi rule quan trọng; authentication, authorization và persistence là những lớp riêng.

### 6.9. src/main/java/demo/DeliveryController.java

```java
package demo;

import java.util.Set;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/delivery")
public class DeliveryController {

    private static final Set<String> LANGUAGES =
            Set.of("vi", "en");

    private static final Set<String> WINDOWS =
            Set.of("day", "evening");

    private final DeliveryService service;

    public DeliveryController(DeliveryService service) {
        this.service = service;
    }

    // Được Spring gọi để chuẩn bị model cho cả GET và POST.
    @ModelAttribute("deliveryForm")
    public DeliveryForm createForm() {
        return new DeliveryForm();
    }

    @InitBinder("deliveryForm")
    public void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "address.street",
                "address.city",
                "address.postalCode",
                "recipients[*].name",
                "recipients[*].email",
                "preferences[language]",
                "preferences[deliveryWindow]"
        );
        binder.setAutoGrowCollectionLimit(3);
    }

    @GetMapping
    public String showForm() {
        return "delivery-form";
    }

    // POST /delivery/add: cùng input form,
    // không validate các field trống khi người dùng
    // chỉ muốn thêm một dòng người nhận.
    @PostMapping("/add")
    public String addRecipient(
            @ModelAttribute("deliveryForm") DeliveryForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            errors.reject("unexpected.fields",
                    "Biểu mẫu có trường không được phép");
        }

        if (errors.hasErrors()) {
            return "delivery-form";
        }

        if (form.getRecipients().size() < 3) {
            form.getRecipients().add(new RecipientForm());
        }

        return "delivery-form";
    }

    // POST /delivery: validate toàn bộ object graph.
    @PostMapping
    public String submit(
            @Valid @ModelAttribute("deliveryForm") DeliveryForm form,
            BindingResult errors,
            Model model) {

        if (errors.getSuppressedFields().length > 0) {
            errors.reject("unexpected.fields",
                    "Biểu mẫu có trường không được phép");
        }

        String language =
                form.getPreferences().get("language");
        if (!LANGUAGES.contains(language)) {
            errors.rejectValue(
                    "preferences[language]",
                    "invalid.language",
                    "Ngôn ngữ không hợp lệ");
        }

        String window =
                form.getPreferences().get("deliveryWindow");
        if (!WINDOWS.contains(window)) {
            errors.rejectValue(
                    "preferences[deliveryWindow]",
                    "invalid.deliveryWindow",
                    "Khung giao hàng không hợp lệ");
        }

        if (errors.hasErrors()) {
            return "delivery-form";
        }

        model.addAttribute(
                "summary",
                service.review(form));

        return "delivery-success";
    }
}
```

**Lưu ý thiết kế controller:**

- Dùng `@Controller` vì trả HTML views, không dùng `@RestController` cho template name.
- `@ModelAttribute("deliveryForm")` cấp một object mới có sẵn address/List/Map cho GET và POST.
- `@InitBinder("deliveryForm")` match chính xác objectName. Chỉ allow các paths cần thiết.
- `@PostMapping("/add")` tách đường thêm dòng ra khỏi đường submit, **không truyền parameter button name vào binder**, nên action không bị nhầm với một field bị suppress.
- Khi thêm dòng, **không đặt `@Valid`** ở add handler: người dùng chưa hoàn tất form; vẫn giữ `BindingResult` cho lỗi binding/conversion.
- `@PostMapping` kiểm tra `@Valid`. `BindingResult` ngay sau form là yêu cầu của Spring MVC.
- `getSuppressedFields()` không tự tạo FieldError nên controller chủ động `reject(...)` để form không được chấp nhận khi client gửi field không được phép.
- `LANGUAGES` và `WINDOWS` thể hiện allowed **values**, bổ sung cho binder allowed **field names**. `@NotBlank` không đủ để chặn chuỗi `hacker`.
- `rejectValue("preferences[language]",...)` tạo field error cho Map value; nếu key thiếu nhưng form có default, việc kiểm tra `Set.contains` vẫn dùng giá trị đang có.
- Service chỉ được gọi khi không có lỗi; demo **không persist dữ liệu**.

**Vấn đề production:** controller chưa có authentication/authorization, CSRF configuration, transaction hoặc audit. Nếu cập nhật địa chỉ thật của người dùng đã đăng nhập, service phải xác định actor và resource được sửa. Đừng gửi `accountId`/`role` từ form rồi tin chúng là quyền người dùng.

### 6.10. src/main/resources/templates/delivery-form.html

```html
<!doctype html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký giao hàng</title>
</head>
<body>
<h1>Thông tin giao hàng</h1>

<form th:action="@{/delivery}"
      th:object="${deliveryForm}"
      method="post">

    <div role="alert" th:if="${#fields.hasAnyErrors()}">
        Biểu mẫu có lỗi. Vui lòng kiểm tra lại dữ liệu.
    </div>

    <section>
        <h2>Người đặt</h2>
        <label for="customerName">Họ tên</label>
        <input type="text"
               th:field="*{customerName}">
        <span th:if="${#fields.hasErrors('customerName')}"
              th:errors="*{customerName}">Lỗi họ tên</span>
    </section>

    <section>
        <h2>Địa chỉ giao hàng</h2>

        <label for="address.street">Đường</label>
        <input type="text"
               th:field="*{address.street}">

        <label for="address.city">Thành phố</label>
        <input type="text"
               th:field="*{address.city}">
        <span th:if="${#fields.hasErrors('address.city')}"
              th:errors="*{address.city}">Lỗi thành phố</span>

        <label for="address.postalCode">Mã bưu chính</label>
        <input type="text"
               th:field="*{address.postalCode}">
    </section>

    <section>
        <h2>Danh sách người nhận (tối đa 3)</h2>

        <div th:each="recipient, stat : *{recipients}">
            <h3 th:text="'Người nhận ' + ${stat.count}">
                Người nhận
            </h3>

            <label>Họ tên</label>
            <input type="text"
                   th:field="*{recipients[__${stat.index}__].name}">

            <label>Email</label>
            <input type="email"
                   th:field="*{recipients[__${stat.index}__].email}">

            <span th:if="${#fields.hasErrors(
                      'recipients[' + stat.index + '].email')}"
                  th:errors="*{recipients[__${stat.index}__].email}">
                Email không hợp lệ
            </span>
        </div>

        <button type="submit"
                th:formaction="@{/delivery/add}">
            Thêm người nhận
        </button>
    </section>

    <section>
        <h2>Tùy chọn</h2>

        <label>Ngôn ngữ</label>
        <select th:field="*{preferences[language]}">
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
        </select>

        <label>Khung giờ giao hàng</label>
        <select th:field="*{preferences[deliveryWindow]}">
            <option value="day">Ban ngày</option>
            <option value="evening">Buổi tối</option>
        </select>
    </section>

    <button type="submit">Xác nhận</button>
</form>
</body>
</html>
```

**Giải thích template:**

1. `th:object="${deliveryForm}"` (viết trong HTML thực tế là expression Thymeleaf với dấu dollar) chọn **form-backing object**.
2. `th:field="*{address.city}"` tạo `name="address.city"`, đồng thời lấy giá trị qua Spring binding infrastructure.
3. `th:each="recipient, stat : *{recipients}"` duyệt List, có `stat.index` 0-based.
4. `__${stat.index}__` là **Thymeleaf expression preprocessing**. Nó thay index thực vào property path trước khi Spring đánh giá. Với row index 1, `*{recipients[__${stat.index}__].email}` trở thành `*{recipients[1].email}`.
5. `th:field="*{preferences[language]}"` dùng Map key language. Field name gửi về tương ứng `preferences[language]`.
6. Add button dùng `formaction="/delivery/add"` qua `th:formaction`; submit bình thường dùng action `/delivery`.
7. `#fields.hasAnyErrors()` hiển thị banner khi có bất kỳ field/global errors trong BindingResult của form.
8. `th:errors` hiển thị messages của những trường tương ứng, kể cả nested/indexed paths.

**Chú ý khi sao chép:** trong Markdown đã lưu, mọi ký hiệu dollar ở trên là dollar thật; không cần thay thế placeholder. Các template expressions là cú pháp HTML/Thymeleaf, không phải JavaScript template literals.

### 6.11. src/main/resources/templates/delivery-success.html

```html
<!doctype html>
<html lang="vi"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Thông tin đã được kiểm tra</title>
</head>
<body>
<h1>Biểu mẫu hợp lệ</h1>
<p>Người đặt: <strong th:text="${summary.customerName}">Tên</strong></p>
<p>Thành phố: <span th:text="${summary.city}">Thành phố</span></p>
<p>Số người nhận:
    <span th:text="${summary.recipientCount}">0</span>
</p>
<p>Ngôn ngữ: <span th:text="${summary.language}">vi</span></p>
<p>Khung giao:
    <span th:text="${summary.deliveryWindow}">day</span>
</p>
<a th:href="@{/delivery}">Tạo biểu mẫu khác</a>
</body>
</html>
```

Trang này dùng `th:text` nên các chuỗi được HTML escape. Không dùng `th:utext` để xuất raw user input. Đây là trang xác nhận sau validation, **không tuyên bố đã lưu database**.

## 7. Kiểm thử trực tiếp DataBinder: chứng minh property paths

Ngoài MockMvc, có thể dùng `DataBinder` trong Spring Core để xem đúng cách nested/List/Map property paths được diễn giải. Test này không cần khởi động server.

### 7.1. src/test/java/demo/DeliveryBinderTest.java

```java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DeliveryBinderTest {

    private DataBinder newBinder(DeliveryForm form) {
        DataBinder binder =
                new DataBinder(form, "deliveryForm");

        binder.setAllowedFields(
                "customerName",
                "address.street",
                "address.city",
                "address.postalCode",
                "recipients[*].name",
                "recipients[*].email",
                "preferences[language]",
                "preferences[deliveryWindow]"
        );
        binder.setAutoGrowCollectionLimit(3);
        return binder;
    }

    @Test
    void nestedListAndMapPathsReachTheirTargets() {
        DeliveryForm form = new DeliveryForm();
        DataBinder binder = newBinder(form);

        Map<String, String> params = new LinkedHashMap<>();
        params.put("customerName", "Lan");
        params.put("address.city", "Da Nang");
        params.put("recipients[1].name", "Minh");
        params.put("recipients[1].email",
                "minh@example.org");
        params.put("preferences[language]", "en");

        binder.bind(new MutablePropertyValues(params));

        assertEquals("Lan", form.getCustomerName());
        assertEquals("Da Nang",
                form.getAddress().getCity());
        assertEquals("Minh",
                form.getRecipients().get(1).getName());
        assertEquals("minh@example.org",
                form.getRecipients().get(1).getEmail());
        assertEquals("en",
                form.getPreferences().get("language"));
        assertTrue(binder.getBindingResult()
                .getSuppressedFields().length == 0);
    }

    @Test
    void unlistedMapKeyIsSuppressed() {
        DeliveryForm form = new DeliveryForm();
        DataBinder binder = newBinder(form);

        Map<String, String> params = new LinkedHashMap<>();
        params.put("preferences[language]", "en");
        params.put("preferences[admin]", "true");
        params.put("accountRole", "ADMIN");

        binder.bind(new MutablePropertyValues(params));

        assertEquals("en",
                form.getPreferences().get("language"));
        assertTrue(!form.getPreferences()
                .containsKey("admin"));
        assertEquals(2, binder.getBindingResult()
                .getSuppressedFields().length);
    }
}
```

**Điểm QA:** đây là pure binder test, chỉ kiểm chứng đường dẫn và allowlist. Nó **không chạy Jakarta Bean Validation** vì không gọi validator, không chứng minh Thymeleaf render field name, và không thể thay thế MockMvc integration tests. Nhưng nó rất hữu ích khi nghi ngờ sai property path hoặc Map key.

## 8. MockMvc integration tests: form thực và xử lý lỗi

### 8.1. src/test/java/demo/DeliveryMvcTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class DeliveryMvcTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder validForm(String path) {
        return post(path)
                .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", "Lan")
                .param("address.street", "12 Nguyen Hue")
                .param("address.city", "Da Nang")
                .param("address.postalCode", "55000")
                .param("recipients[0].name", "Lan")
                .param("recipients[0].email",
                        "lan@example.org")
                .param("recipients[1].name", "Minh")
                .param("recipients[1].email",
                        "minh@example.org")
                .param("preferences[language]", "vi")
                .param("preferences[deliveryWindow]", "day");
    }

    @Test
    void getRendersNestedListAndMapNames() throws Exception {
        mvc.perform(get("/delivery"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(content().string(
                        containsString("name=\"address.city\"")))
                .andExpect(content().string(
                        containsString("name=\"recipients[0].name\"")))
                .andExpect(content().string(
                        containsString("name=\"recipients[1].email\"")))
                .andExpect(content().string(
                        containsString("name=\"preferences[language]\"")));
    }

    @Test
    void validNestedFormProducesSummary() throws Exception {
        mvc.perform(validForm("/delivery"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-success"))
                .andExpect(model().attributeExists("summary"))
                .andExpect(content().string(
                        containsString("Da Nang")))
                .andExpect(content().string(
                        containsString("Số người nhận")));
    }

    @Test
    void blankNestedCityProducesFieldError()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("address.city", ""))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm", "address.city"));
    }

    @Test
    void invalidSecondRecipientEmailHasIndexedPath()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[1].email",
                                "not-an-email"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "recipients[1].email"));
    }

    @Test
    void blankRecipientNameIsValidatedByCascade()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[0].name", ""))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "recipients[0].name"));
    }

    @Test
    void disallowedRoleIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("accountRole", "ADMIN"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasErrors(
                        "deliveryForm"));
    }

    @Test
    void unknownPreferenceKeyIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("preferences[admin]", "true"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasErrors(
                        "deliveryForm"));
    }

    @Test
    void invalidPreferenceValueIsRejected() throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("preferences[language]",
                                "invalid"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm",
                        "preferences[language]"));
    }

    @Test
    void addRecipientRendersThirdRow() throws Exception {
        mvc.perform(validForm("/delivery/add"))
                .andExpect(status().isOk())
                .andExpect(view().name("delivery-form"))
                .andExpect(content().string(
                        containsString(
                                "name=\"recipients[2].email\"")));
    }

    @Test
    void threeRecipientsCanBeSubmitted()
            throws Exception {
        mvc.perform(validForm("/delivery")
                        .param("recipients[2].name", "An")
                        .param("recipients[2].email",
                                "an@example.org"))
                .andExpect(view().name("delivery-success"))
                .andExpect(content().string(
                        containsString("Số người nhận")))
                .andExpect(model().attribute(
                        "summary",
                        new DeliverySummary(
                                "Lan", "Da Nang", 3,
                                "vi", "day")));
    }

    @Test
    void missingCustomerNameProducesFieldError()
            throws Exception {
        mvc.perform(post("/delivery")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("address.street",
                                "12 Nguyen Hue")
                        .param("address.city", "Da Nang")
                        .param("address.postalCode", "55000")
                        .param("recipients[0].name", "Lan")
                        .param("recipients[0].email",
                                "lan@example.org")
                        .param("recipients[1].name", "Minh")
                        .param("recipients[1].email",
                                "minh@example.org"))
                .andExpect(view().name("delivery-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "deliveryForm", "customerName"));
    }
}
```

**11 integration tests** ở trên kiểm tra từng tầng:

| Nhóm | Test | Điều cần thấy |
| --- | --- | --- |
| Rendering | GET form | HTML có đúng nested, indexed và Map `name` |
| Happy path | POST hợp lệ | Trang confirmation và summary đúng |
| Nested validation | Thành phố trống | `address.city` có FieldError |
| List element validation | Email thứ hai sai | `recipients[1].email` có FieldError |
| List element validation | Tên thứ nhất trống | `recipients[0].name` có FieldError |
| Binding security | Field `accountRole` lạ | Form bị reject; không vào success |
| Map key security | `preferences[admin]` | Key ngoài allowlist bị reject |
| Map value rules | `language=invalid` | FieldError cho Map entry |
| Dynamic row | POST /delivery/add | Render dòng List index 2 |
| Dynamic row | POST với index 2 | Summary có ba recipients |
| Required field | Không gửi `customerName` | FieldError từ `@NotBlank` |

**Lưu ý khi đọc tests:** vì đây là HTML form, controller trả lại template lỗi với **HTTP 200** (cách xử lý phổ biến cho form server-rendered). REST API có thể chọn 400/422. Đừng coi status 200 là “input được chấp nhận” nếu response là form có BindingResult errors. Đối với demo, `delivery-success` mới là nhánh chấp nhận.

### 8.2. Vì sao MockMvc quan trọng hơn chỉ unit-test setter?

Nếu bạn tự gọi:

```java
DeliveryForm form = new DeliveryForm();
form.getAddress().setCity("Da Nang");
```

thì bạn chỉ chứng minh Java setter hoạt động. Bạn **chưa chứng minh** request name `address.city` được Spring bind, Thymeleaf render đúng indexed fields, `@InitBinder` chọn đúng objectName, hoặc nested `@Valid` chạy.

`MockMvc` dùng Spring MVC infrastructure thật (với `@SpringBootTest`) để kiểm tra cả pipeline từ request parameters đến controller và view. Dùng `DataBinder` unit tests cho cơ chế property paths, dùng MockMvc để chứng minh integration.

## 9. Chạy project và thử bằng trình duyệt

### 9.1. Kiểm thử

Cần JDK 17+ và Maven:

```bash
mvn -q clean test
```

**Kỳ vọng theo mã mẫu:** 2 DataBinder unit tests + 11 MockMvc integration tests = **13 tests**. Khi Maven dependencies và môi trường phù hợp, các tests dự kiến pass và Maven exit code 0. Đây là **kết quả dự kiến từ code**, không phải build đã được thực thi/quan sát trong lúc soạn bài; hãy chạy CI để xác thực thực tế.

### 9.2. Chạy server

```bash
mvn spring-boot:run
```

Mở:

```text
http://localhost:8080/delivery
```

Bạn sẽ thấy một form có người đặt, địa chỉ, hai người nhận và hai lựa chọn. Nhấn **Thêm người nhận** một lần sẽ có dòng thứ ba. Nhấn **Xác nhận** sau khi nhập đúng dữ liệu, trang summary hiển thị người đặt, thành phố, số người nhận và hai preferences.

### 9.3. Thử form-urlencoded bằng curl

```bash
curl -i -X POST \
  'http://localhost:8080/delivery' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'customerName=Lan' \
  --data-urlencode 'address.street=12 Nguyen Hue' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'address.postalCode=55000' \
  --data-urlencode 'recipients[0].name=Lan' \
  --data-urlencode 'recipients[0].email=lan@example.org' \
  --data-urlencode 'recipients[1].name=Minh' \
  --data-urlencode 'recipients[1].email=minh@example.org' \
  --data-urlencode 'preferences[language]=vi' \
  --data-urlencode 'preferences[deliveryWindow]=day'
```

Kết quả là **HTML document**, không phải JSON; response status được demo chọn 200. Trang hiển thị `Biểu mẫu hợp lệ` và số người nhận 2 nếu toàn bộ constraints/rules được thỏa.

Thử inject một field:

```bash
curl -i -X POST \
  'http://localhost:8080/delivery' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'customerName=Lan' \
  --data-urlencode 'address.street=12 Nguyen Hue' \
  --data-urlencode 'address.city=Da Nang' \
  --data-urlencode 'address.postalCode=55000' \
  --data-urlencode 'recipients[0].name=Lan' \
  --data-urlencode 'recipients[0].email=lan@example.org' \
  --data-urlencode 'recipients[1].name=Minh' \
  --data-urlencode 'recipients[1].email=minh@example.org' \
  --data-urlencode 'preferences[language]=vi' \
  --data-urlencode 'preferences[deliveryWindow]=day' \
  --data-urlencode 'accountRole=ADMIN'
```

Expected: Controller thấy suppressed field, tạo global error và trả lại `delivery-form` thay vì trang success. Bài học bảo vệ **property binding**, không chứng minh có authorization hoàn chỉnh cho application.

## 10. Thêm và xóa dòng List: làm đúng với chỉ số

### 10.1. Vì sao biểu mẫu dynamic dùng index thay vì id DOM?

Spring property binding đọc `name="recipients[1].email"`, không quan tâm input có id `recipient-email-2` hay không. HTML `id` dùng cho CSS, accessibility và labels; **`name` mới quyết định request parameter binding**.

Khi lặp:

```html
<div th:each="r, s : *{recipients}">
    <input th:field="*{recipients[__${s.index}__].name}">
    <input th:field="*{recipients[__${s.index}__].email}">
</div>
```

Thymeleaf preprocessing biến `s.index` thành index literal trước khi Spring field expression được xử lý. Không viết `*{recipients[s.index].email}` rồi mong Spring EL tự resolve `s.index` trong brackets; cách đó không tương đương.

### 10.2. Một handler thêm dòng không nên bắt người dùng hoàn tất mọi trường trước

Handler `POST /delivery/add` ở demo **không dùng `@Valid`**, vì người dùng có thể đang điền dở. Nó vẫn bind các dữ liệu hiện có để không làm mất nội dung khi render thêm dòng.

Đường submit cuối cùng mới dùng `@Valid` và kiểm tra toàn bộ object graph.

**Cẩn trọng:** khi add không validate, dữ liệu tạm thời chưa hợp lệ có thể được render lại; việc đó chấp nhận được cho UX của form, nhưng không được persist hoặc gửi downstream như một lệnh đã hợp lệ.

### 10.3. Xóa một dòng: phải tái đánh chỉ số

Ví dụ List 3 phần tử:

```text
recipients[0] = Lan
recipients[1] = Minh
recipients[2] = An
```

Sau khi xóa index 1, List còn Lan và An; khi render lại, các names phải là:

```text
recipients[0].name = Lan
recipients[1].name = An
```

Nếu HTML vẫn gửi `recipients[2].name` mà không có index 1, Spring có thể auto-grow phần tử trống ở giữa, dẫn đến validation errors hoặc logic sai. Trong demo **chưa có nút xóa**, để giữ ví dụ runnable gọn và tránh lẫn session state. Khi thêm tính năng xóa, xử lý danh sách trên server rồi render lại từ List với index mới; không chỉ ẩn một dòng bằng CSS.

### 10.4. Index không phải ID nghiệp vụ

Nếu cập nhật recipients đã lưu trong DB, không được suy rằng `recipients[0]` chính là database row ID cũ. Index của form là **vị trí khi render/submit**; nó thay đổi khi thêm/xóa/sắp xếp. Cần dùng một stable identifier được server kiểm tra ownership, hoặc command có operations thêm/sửa/xóa rõ ràng. Không bind trực tiếp JPA entity graph rồi cho client sửa `recipients[0].id` tùy ý.

## 11. Map field names và key security

### 11.1. Key cố định

Trong bài này, chỉ chấp nhận:

```text
preferences[language]
preferences[deliveryWindow]
```

Chúng là hai trường cấu hình có semantics khác nhau:

- `language`: một trong `vi`, `en`.
- `deliveryWindow`: một trong `day`, `evening`.

`@NotBlank` trên Map values chỉ cấm blank, không giới hạn tập giá trị. Vì thế controller có thêm allowlists cho **giá trị**.

### 11.2. Key động

Nếu sản phẩm cho phép nhập Map key tùy ý, cần quyết định:

- Danh sách ký tự hợp lệ và max key length.
- Key có phân biệt hoa/thường hay không.
- Cách xử lý key có dấu chấm, ngoặc vuông, dấu cách và các ký tự đặc biệt.
- Độ sâu/nested paths cho `Map<String,SomeObject>`.
- Số lượng keys tối đa và chi phí map growth.
- Quyền của actor đối với từng Map entry.
- Quản lý collisions, duplicate parameters và canonicalization.

Không dùng `binder.setAllowedFields("preferences*")` chỉ vì “Map có key động”; wildcard có thể cho phép nhiều property paths hơn ý định. Nếu Map keys không thể giới hạn bằng pattern rõ ràng, có thể dùng một request DTO khác như `List<PreferenceEntry>` với `key`/`value` và validator, sau đó service chuyển thành Map sau khi kiểm tra duplicates và business rules.

### 11.3. Key chứa dấu chấm hoặc ngoặc

Một tên như `preferences[user.news]` có thể được Spring property path parser diễn giải khác với `preferences[user].news`; dấu chấm **bên trong brackets** dùng để mô tả key, còn dấu chấm ngoài brackets chuyển đến nested property. Nhưng tên keys tùy ý có các ký tự biểu diễn đặc biệt cần được encode/canonicalize đúng và test trên binder thực tế.

Khuyến nghị cho public HTML form: dùng keys đơn giản (chữ/số/_/-), whitelist và avoid dynamic arbitrary property paths nếu không thật sự cần.

### 11.4. Map đầu vào không phải object lưu trữ

Không làm:

```java
for (var entry : form.getPreferences().entrySet()) {
    entity.setProperty(entry.getKey(), entry.getValue());
}
```

Đây là **anti-pattern fragment**, không phải code runnable. Một Map từ HTTP không được tự biến thành danh sách properties để update entity. Trong service, map chính xác các keys được biết, xác thực actor và giữ domain invariants.

## 12. Cách đọc BindingResult khi có nested errors

Một `BindingResult` có thể chứa:

```text
address.street
address.city
recipients[0].name
recipients[1].email
preferences[language]
preferences[deliveryWindow]
```

Đường dẫn thật của **container-element violations** trong Map có thể kèm node name như `<map value>` tùy cách adapter/provider hiển thị `Path.Node`. Vì vậy đừng cố parse error path bằng `split(".")` hay assume mọi Map violation là đúng một literal field name.

Ví dụ xử lý cơ bản:

```java
for (FieldError error : result.getFieldErrors()) {
    String field = error.getField();
    boolean conversionFailure = error.isBindingFailure();
    String code = error.getCode();
}
```

Đây là fragment cần import `org.springframework.validation.FieldError` và một `BindingResult result` đã có. Phân loại:

- `isBindingFailure()==true`: lỗi chuyển kiểu hoặc binding.
- Constraint error: validation của Jakarta/Spring (ví dụ `@NotBlank`).
- `getGlobalErrors()`: lỗi toàn object, có thể do `result.reject(...)` vì suppressed fields.
- `getSuppressedFields()`: tên fields bị loại trong property binding; **không tự thuộc `getFieldErrors()`**.

Với Thymeleaf, có thể dùng:

```html
<span th:if="${#fields.hasErrors('address.city')}"
      th:errors="*{address.city}">
    City error
</span>
```

Với List:

```html
<span th:errors="*{recipients[__${stat.index}__].email}">
    Email error
</span>
```

Trong một API JSON, nên chuyển `FieldError` thành **error schema ổn định**. Với HTML form, `th:errors` và `#fields` giúp render lại gần field, nhưng vẫn nên có banner tổng quát cho global errors.

## 13. Những lỗi thường gặp và cách sửa

### 13.1. Null nested address gây binding exception

**Triệu chứng:** `address.city` không bind được do `address` null hoặc thiếu setter/no-arg constructor.

**Sửa:** khởi tạo `address = new AddressForm()` trong input DTO; xác nhận getters/setters chuẩn JavaBeans và WebDataBinder property access. Không kỳ vọng Spring tự tạo mọi custom immutable nested value object mà không có constructor/converter phù hợp.

### 13.2. List render đúng nhưng post không bind

**Triệu chứng:** input HTML có `id="recipient0.email"` nhưng thiếu `name="recipients[0].email"`.

**Sửa:** dùng `th:field="*{recipients[__${stat.index}__].email}"` hoặc viết `name` chính xác. Inspect DOM/Network request thực tế, không chỉ dựa vào id hiển thị.

### 13.3. Dùng List.of hoặc Map.of để prepopulate mutable form

**Triệu chứng:** UnsupportedOperationException hoặc không thể thay indexed elements.

**Sửa:** dùng `ArrayList`/`LinkedHashMap` cho form cần chỉnh sửa. Immutable collections có thể phù hợp ở output/domain, nhưng không phải cấu trúc mutable cho property binding.

### 13.4. Quên @Valid trên nested object hoặc elements

**Triệu chứng:** `customerName` được validate nhưng `address.city` và `recipients[1].email` không tạo errors.

**Sửa:** `@Valid` ở `address` và List element `List<@Valid RecipientForm>`, kèm constraints trên các classes con.

### 13.5. Gắn @NotBlank trực tiếp lên List hoặc Map

**Triệu chứng:** `UnexpectedTypeException` vì `@NotBlank` cần một `CharSequence` compatible.

**Sửa:** `@NotEmpty` hoặc `@Size` trên collection/map, `@NotBlank` trên String elements/values.

### 13.6. @Size(max=3) mà vẫn nhận index rất lớn

**Triệu chứng:** binder gặp `recipients[999999]` trước khi @Size có cơ hội báo lỗi.

**Sửa:** dùng `setAutoGrowCollectionLimit`, request parameter count limit, prefilter inputs và tests for out-of-range paths. @Size kiểm tra object đã được bind, không phải firewall ngăn binder tạo object quá lớn.

### 13.7. HTML checkbox missing không đồng nghĩa false

Một checkbox không được tick thường **không gửi key**. Nếu Map value là Boolean, việc thiếu parameter có thể giữ giá trị cũ/default hoặc cần field-marker support. Spring WebDataBinder có field marker/default prefixes; Thymeleaf `th:field` cho checkbox có thể sinh hidden marker.

Demo dùng **select với String values** cho cả hai preferences để tránh ẩn vấn đề checkbox. Khi thêm checkbox vào nested Map, test cả checked, unchecked và missing marker, đồng thời giới hạn keys được phép. Đừng giả định nút `false` sẽ tự xuất hiện từ HTML checkbox chưa chọn.

### 13.8. Lỗi thuộc Map value không hiện cạnh select

**Triệu chứng:** global banner hiện nhưng `th:errors="*{preferences[language]}"` không match violation path chứa container-node.

**Sửa:** inspect actual `BindingResult#getFieldErrors()` và paths. Dùng banner/summary cho Map constraints hoặc custom `rejectValue` với property path rõ; không tự giả định Hibernate Validator luôn render cùng key format trên mọi phiên bản.

### 13.9. @InitBinder không chạy

**Triệu chứng:** `getSuppressedFields()` rỗng dù gửi unknown properties.

**Sửa:** kiểm tra binder objectName: `@InitBinder("deliveryForm")` và `@ModelAttribute("deliveryForm")` phải đúng. Kiểm tra scope controller/advice và request có thực sự dùng property binding hay không.

### 13.10. Gửi extra form button name khiến allowlist reject

Nếu submit button có `name="submit"` mà binder chỉ allow business fields, `submit` có thể bị xem là unknown property và bị suppress. Demo tách action thêm dòng theo URL `/delivery/add` và dùng các buttons **không có name**. Trong ứng dụng có nhiều action buttons qua request params, phải thiết kế routing, parameter preprocessing hoặc allowlist có chủ đích; tránh vô tình chấp nhận action flags như business fields.

### 13.11. Dùng @RequestBody JSON nhưng kỳ vọng setAllowedFields bảo vệ

`@RequestBody` được deserialize qua HTTP message converter, không phải cùng pipeline form property binding. Dùng record/DTO theo tác vụ và test Jackson unknown fields riêng. Không coi test form-urlencoded là bằng chứng bảo mật cho endpoint JSON.

### 13.12. Trộn List index với database ID

`recipients[0]` là vị trí, không phải persistent primary key. Khi cập nhật existing recipients, server phải xác nhận ID/ownership; không tin index của client là quyền đối với row.

### 13.13. Dùng Map tùy ý như cấu hình database

Một map cho phép keys `admin`, `featureFlags` hoặc `permissions` có thể tạo mass assignment. Dùng allowlist exact keys và service explicit mapping; từ chối extra keys nếu hợp đồng yêu cầu.

### 13.14. Không render lại giá trị đã nhập khi có lỗi

Nếu controller tạo một DTO mới rồi trả view mà không dùng bound object + BindingResult hiện tại, các fields người dùng vừa nhập bị mất. Trong Spring MVC, khi local BindingResult có lỗi, trả lại template trực tiếp từ handler để giữ model attribute và binding state.

### 13.15. Thử một form hợp lệ rồi nghĩ đủ

Happy path không chứng minh nested validation, Map key restrictions hoặc indexed paths. Cần negative tests ở tất cả các tầng: nested blank field, indexed invalid email, unlisted map key và out-of-range List index.

## 14. Mở rộng thực hành: dynamic rows, partial update và persistence

### 14.1. Thêm tính năng xóa người nhận

Để hỗ trợ remove, route riêng `POST /delivery/remove` nhận index, kiểm tra index nằm trong khoảng, loại phần tử khỏi List rồi render lại. Sau mỗi thao tác xóa, Thymeleaf phải tạo lại field names liên tiếp từ index 0. Nếu form có nhiều bước hoặc redirect, bạn cần cơ chế lưu state rõ ràng: session command, draft store hoặc idempotent operations.

Đừng chỉ “xóa khỏi DOM” mà không đảm bảo server biết item nào bị xóa. Với persistence, dùng stable IDs và kiểm tra ownership để tránh xóa recipient của tài khoản khác.

### 14.2. Có nên dùng session cho multi-step form?

`@SessionAttributes` có thể giữ form object qua nhiều request trong cùng session, nhưng tạo yêu cầu lifecycle/cleanup, concurrency tab, stale form và session security. Với một form ngắn, cách stateless rebind như demo thường dễ hiểu. Với wizard thực tế, cân nhắc draft ID và server-side state.

### 14.3. CSRF và form methods

Demo không bật Spring Security, vì vậy **chưa có CSRF protection**. Nếu endpoint gắn với tài khoản và mutate dữ liệu, production cần xác thực, authorization và CSRF defense thích hợp cho cookie-based browser sessions. Thymeleaf có tích hợp Spring RequestDataValueProcessor để thêm hidden fields khi Spring Security CSRF được cấu hình tương ứng.

Không tắt CSRF chỉ để form submit được. Trình duyệt có thể gửi form cross-site; cần kiểm tra cơ chế bảo vệ tương ứng authentication model.

### 14.4. Persistence và transaction

Sau khi form được validate, service nên:

1. Xác thực actor và quyền sửa resource.
2. Ánh xạ **chỉ những fields được phép** từ input DTO sang domain model.
3. Validate business invariants như người nhận có trùng nhau hay không.
4. Áp transaction/optimistic locking nếu cập nhật database.
5. Bảo vệ bằng UNIQUE/NOT NULL/FK/CHECK phù hợp ở database.
6. Trả output DTO cần thiết, không serialize entity graph.

Data binding và Bean Validation **không thay** database constraints hay authorization. Một field email đúng format không đồng nghĩa người nhận thuộc caller, và một Map key hợp lệ không đồng nghĩa actor được thay đổi mọi setting của hệ thống.

### 14.5. Form có danh sách lớn

Nếu form có hàng trăm recipients, server-rendered indexed fields có thể tạo request rất lớn, khó rollback và dễ DoS. Hãy cân nhắc separate CRUD endpoints, pagination, batch API có size limit và idempotency. Không mở `setAutoGrowCollectionLimit(1000000)` như cách chữa lỗi index lớn.

### 14.6. Cập nhật chỉ một phần tử

Nếu chức năng chỉ sửa email của recipient cụ thể, một DTO nhỏ như:

```java
public record ChangeRecipientEmail(
        @NotBlank @Email String email) {
}
```

thường an toàn hơn bind lại cả List của account. Resource ID được xác định từ route/authorization, không tin vào index của client. Đây là **fragment** cần imports Jakarta Validation, không thuộc project full form runnable.

## 15. Checklist QA cho form lồng nhau

### DTO / property paths

- [ ] Root form có tên model attribute tường minh.
- [ ] Nested object có constructor/getter/setter hoặc constructor binding plan rõ.
- [ ] Collections/Maps có mutable implementation nếu property binding cần sửa.
- [ ] Input DTO không chứa các domain fields nhạy cảm.
- [ ] Names dùng `address.city`, `recipients[0].email`, `preferences[language]` đúng.
- [ ] @Valid cascade đến address và từng List element.
- [ ] Container constraints áp đúng tầng List/Map/value.
- [ ] Required fields có @NotBlank/@NotNull phù hợp.
- [ ] Thêm test khi đổi một nested property name.

### Controller / security

- [ ] @InitBinder trùng objectName của @ModelAttribute.
- [ ] setAllowedFields dùng exact paths/wildcards hẹp.
- [ ] Có giới hạn auto-grow cho indexed collections.
- [ ] Có request parameter/body size limits và xử lý index bất thường.
- [ ] getSuppressedFields được xét khi cần reject unknown fields.
- [ ] Map keys và values được whitelist theo semantics.
- [ ] BindingResult nằm ngay sau validated argument.
- [ ] Service kiểm tra authentication/authorization nếu mutate state thật.
- [ ] Không bind JPA entities trực tiếp từ form.
- [ ] Không dùng Map<String,Object> tùy ý để copy vào entity.

### Thymeleaf / UX

- [ ] th:object trỏ đúng model attribute.
- [ ] th:field tạo đúng HTTP name attributes.
- [ ] Với List, dùng `__${stat.index}__` preprocessing.
- [ ] Map fields dùng bracket key syntax có kiểm thử.
- [ ] Field errors được hiển thị ở nested/indexed paths.
- [ ] Có global banner cho lỗi Map/global/suppressed.
- [ ] Người dùng không mất dữ liệu khi form invalid.
- [ ] Add/remove rows có giới hạn và reindex phù hợp.
- [ ] Không dùng th:utext cho dữ liệu nhập từ browser.
- [ ] Form mutation trong production có CSRF protection.

### Tests

- [ ] GET test kiểm tra `name="address.city"`.
- [ ] GET test kiểm tra ít nhất một `name="recipients[1].email"`.
- [ ] GET test kiểm tra `name="preferences[language]"`.
- [ ] POST form hợp lệ đi tới view success.
- [ ] Address blank tạo error ở `address.city`.
- [ ] List element sai tạo error ở `recipients[1].email`.
- [ ] Map value ngoài tập được từ chối.
- [ ] Map key ngoài allowlist không được cập nhật.
- [ ] Field role/owner không thể over-post.
- [ ] Add row tạo index đúng, không cần validation khi đang edit.
- [ ] Submit 3 rows thành công; 4+ rows bị chặn theo policy.
- [ ] Có tests cho rejected input và model state, không chỉ status.

## 16. Kết luận

**Thiết kế form có địa chỉ lồng, danh sách và Map** yêu cầu khớp chính xác ba tầng:

1. **Object graph**: DTO có `AddressForm`, `List<RecipientForm>` và `Map<String,String>` với cấu trúc/mutability phù hợp.
2. **Property paths trong HTTP/Thymeleaf**: dùng `address.city`, `recipients[0].email` và `preferences[language]`; Thymeleaf `__${stat.index}__` tạo indexed paths đúng khi lặp.
3. **Data binding + validation + security**: `@ModelAttribute`, `WebDataBinder#setAllowedFields`, `@Valid` cascade, `BindingResult`, list size/auto-grow limits và Map key/value policies.

Ứng dụng mẫu có thể render form, thêm người nhận, submit đầy đủ, trả lại lỗi theo nested paths và chặn extra fields. Các MockMvc và pure DataBinder tests giúp xác nhận **hành vi thực tế của framework**, không chỉ việc Java setters hoạt động.

**Điểm nên nhớ:** List index không phải database ID, Map từ client không phải quyền sửa entity, và annotation validation không thay authorization. Thiết kế input DTO chuyên biệt, allowlist hẹp và kiểm thử negative cases ngay từ đầu giúp form lồng nhau dễ bảo trì hơn nhiều.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MVC Data Binding: nested, indexed và Map property paths](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework 6.2 — @ModelAttribute: constructor và property binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder và Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Thymeleaf + Spring Tutorial 3.1 — th:object, th:field và indexed preprocessing](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.pdf)
- [Thymeleaf 3.1 — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html)
