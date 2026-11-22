# `setAllowedFields`: giới hạn các trường được phép data binding trong Spring

## 1. Tại sao cần danh sách trường được phép gắn?

Khi Spring đưa dữ liệu đầu vào vào đối tượng Java bằng `DataBinder` hoặc `WebDataBinder`, tên thuộc tính từ nguồn dữ liệu có thể quyết định setter/property nào được cập nhật. Nếu input đến từ HTTP request, client hoàn toàn có thể tự tạo thêm tham số mà giao diện không hiển thị. Việc gắn mọi property có thể vô tình cho phép thay đổi các trường nhạy cảm như `admin`, `approved`, `ownerId`, `balance` hoặc `role` — đây là rủi ro **mass assignment / over-posting**.

`DataBinder#setAllowedFields(String... allowedFields)` xác định một **allowlist**: những tên property được phép tham gia *property binding*. Mọi field ngoài allowlist bị loại khỏi bước gán, ngay cả khi DTO có setter hợp lệ.

```text
HTTP form / PropertyValues
  displayName = "An"
  email       = "an@example.com"
  admin       = "true"
              |
              v
DataBinder với allowedFields = ["displayName", "email"]
              |
              +-- displayName -> được gán
              +-- email       -> được gán
              +-- admin       -> bị suppress
              |
              v
BindingResult.getSuppressedFields() -> ["admin"]
```

Điểm quan trọng: `setAllowedFields` là chính sách cho **binding các property**, không phải cơ chế phân quyền người dùng cuối, không thay thế validation và không ngăn ứng dụng tự gọi setter ngoài binder.

## 2. Cú pháp và thời điểm sử dụng

API cơ bản:

```java
import org.springframework.validation.DataBinder;

DataBinder binder = new DataBinder(target, "profile");
binder.setAllowedFields("displayName", "email");
```

Trong ví dụ, `target` là object đã được tạo và có các property tương ứng. Binder sẽ áp dụng danh sách này khi xử lý `bind(PropertyValues)`.

**Thiết lập allowlist trước khi bind.** Nếu đặt sau `bind`, những setter đã được gọi trước đó không tự hoàn tác. Với Spring MVC, thiết lập thường được đặt trong `@InitBinder` để framework áp dụng trước khi binding model attribute.

Không gọi `setAllowedFields()` với danh sách rỗng vì tưởng rằng nó sẽ “tắt binding”: semantics cấu hình allowlist không nên được suy diễn theo cách này. Để chặn property binding hoàn toàn cho một binder, Spring có tùy chọn riêng như `setDeclarativeBinding(true)` trong các phiên bản hỗ trợ, hoặc dùng DTO/handler thiết kế chỉ cho constructor binding. Cần đối chiếu phiên bản Framework và kiểm thử mục tiêu an toàn.

## 3. Ví dụ Java 17+ đầy đủ

Tạo `AllowedFieldsDemo.java` trong một dự án có các module Spring Framework phù hợp:

```java
import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class AllowedFieldsDemo {
    public static class ProfileForm {
        private String displayName;
        private String email;
        private boolean admin;

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }
    }

    public static void main(String[] args) {
        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields("displayName", "email");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("displayName", "An");
        input.add("email", "an@example.com");
        input.add("admin", "true");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println(form.getDisplayName());
        System.out.println(form.getEmail());
        System.out.println(form.isAdmin());
        System.out.println(result.hasErrors());
        System.out.println(Arrays.toString(result.getSuppressedFields()));
    }
}
```

Output:

```text
An
an@example.com
false
false
[admin]
```

Giải thích từng dòng:

1. `displayName` và `email` khớp allowlist nên được gán.
2. `admin` dù có setter vẫn **không được gán**; giá trị mặc định của `boolean` tiếp tục là `false`.
3. Trường bị suppress không mặc nhiên được ghi là `FieldError`, vì vậy `result.hasErrors()` ở ví dụ trả `false`.
4. `getSuppressedFields()` trả tên trường đầu vào đã bị loại; đây là tín hiệu rất hữu ích để **phát hiện request cố cập nhật field ngoài hợp đồng**.

Với Java 17+ và classpath đã chứa `spring-context` hoặc các module Spring liên quan cùng dependency tương thích, có thể biên dịch/chạy bằng lệnh Linux/macOS sau nếu `SPRING_CP` đã chứa đầy đủ JAR:

```bash
javac -cp "$SPRING_CP" AllowedFieldsDemo.java
java -cp ".:$SPRING_CP" AllowedFieldsDemo
```

Trên Windows, dấu phân tách classpath là `;`. Một lệnh `javac AllowedFieldsDemo.java` thuần túy không chạy được nếu chưa có Spring JAR. Ví dụ có `main` độc lập với HTTP server.

## 4. `setAllowedFields` và Spring MVC `@InitBinder`

Trong Spring MVC, `WebDataBinder` được framework tạo cho model attribute và có thể được cấu hình qua `@InitBinder`:

```java
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @InitBinder("profileForm")
    void restrictProfileFields(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "email");
    }

    @PostMapping("/profile")
    String update(@ModelAttribute("profileForm") AllowedFieldsDemo.ProfileForm form,
                  BindingResult result) {
        if (result.getSuppressedFields().length != 0) {
            return "Unsupported fields";
        }
        if (result.hasErrors()) {
            return "Invalid profile";
        }
        return "Updated: " + form.getDisplayName();
    }
}
```

Đây là snippet của controller trong ứng dụng Spring MVC đã cấu hình, không phải Java file có `main` hoàn chỉnh. Với request `displayName=An&email=an@example.com`, các property được gắn theo allowlist. Nếu client thêm `admin=true`, field đó bị suppress, còn controller ví dụ chủ động phát hiện và từ chối.

**Lưu ý về HTTP status:** các chuỗi `"Unsupported fields"` và `"Invalid profile"` trong ví dụ không tự biến thành HTTP 4xx. Ứng dụng production nên trả `ResponseEntity.badRequest()` hoặc dùng exception handler để phát biểu rõ HTTP status/response schema.

`@InitBinder("profileForm")` dùng tên model attribute để giới hạn phạm vi cấu hình. Tên cần khớp `@ModelAttribute("profileForm")`; nếu dùng `@InitBinder` không giới hạn tên, chính sách có thể áp dụng cho nhiều object khác nhau và làm mất field cần thiết.

## 5. Exact field names, pattern và nested paths

Allowlist được áp dụng theo **tên property path** mà binder nhìn thấy:

```java
binder.setAllowedFields("name", "address.city", "address.postalCode");
```

Khi input chứa `name` và `address.city`, chúng có thể được gán nếu cấu trúc JavaBean hợp lệ. Nếu client gửi `address.country` hoặc `address.internalCode`, chúng nằm ngoài allowlist.

Spring hỗ trợ pattern matching trong tên allowed fields theo semantics của `DataBinder`/`PatternMatchUtils`, ví dụ `address.*` hoặc `items[*].name` ở những trường hợp phù hợp. Cẩn trọng: `address.*` là một chính sách rộng, có thể cho phép **các property mới** được thêm vào `Address` sau này. Không sử dụng wildcard rộng chỉ để giảm công bảo trì khi dữ liệu do client kiểm soát.

| Allowlist | Input property | Kết quả chính sách |
| --- | --- | --- |
| `name` | `name` | Cho phép |
| `address.city` | `address.city` | Cho phép |
| `address.city` | `address.country` | Suppress |
| `address.*` | `address.city` | Có thể khớp theo pattern |
| `address.*` | `address.internalFlag` | Cũng có thể khớp; rủi ro mở rộng phạm vi |

Không nhầm dấu chấm của property path với đường dẫn JSON hay tên column trong database. Với `@ModelAttribute`, Spring có thể dùng path `address.city` trực tiếp; với `@RequestBody` JSON, việc deserialization do message converter (thường Jackson) đảm nhiệm nên **allowlist của DataBinder không mặc nhiên chặn field JSON**.

## 6. `getSuppressedFields()` là gì?

Sau `bind`, `BindingResult.getSuppressedFields()` cho biết những property names đã bị loại bởi cơ chế binding field filtering. Ví dụ:

```java
String[] suppressed = binder.getBindingResult().getSuppressedFields();
if (suppressed.length > 0) {
    throw new IllegalArgumentException(
            "Unexpected fields: " + String.join(", ", suppressed));
}
```

Đây là snippet trong method đã có biến `binder`. Chính sách fail-fast này giúp coi một request ghi field ngoài hợp đồng là lỗi đầu vào, thay vì âm thầm bỏ qua.

Tuy nhiên không nên đưa nguyên văn tên field hoặc rejected value nhạy cảm vào log công khai. Nếu phát hiện input độc hại, trả thông báo an toàn cho client và ghi audit theo chính sách phù hợp. Đừng dùng `getSuppressedFields()` để thay thế kiểm tra authorization của người đang cập nhật bản ghi.

### `suppressed field` khác `field error`

| Tình huống | Trạng thái | API quan sát |
| --- | --- | --- |
| Client gửi `admin=true` ngoài allowlist | Field bị suppress | `getSuppressedFields()` |
| Client gửi `age=abc` nhưng `age` được cho phép và target là `int` | Lỗi chuyển kiểu | `hasFieldErrors("age")`, `getFieldError("age")` |
| Client gửi `email` hợp lệ nhưng validator thấy sai quy tắc nghiệp vụ | Validation error | `hasFieldErrors("email")` |
| Client không gửi `name` nhưng binder yêu cầu `name` | Missing required field | `BindingResult` theo chính sách required fields |

Field bị suppress không có nghĩa toàn bộ operation tự động thất bại. Muốn từ chối, phải kiểm tra và phản hồi rõ ràng.

## 7. `setAllowedFields`, `setDisallowedFields` và `setRequiredFields`

Ba nhóm API giải quyết ba câu hỏi khác nhau:

- `setAllowedFields`: client **được phép gửi field nào để bind?**
- `setDisallowedFields`: những field nào **bị cấm bind?**
- `setRequiredFields`: những field nào **phải hiện diện trong tập property values đầu vào?**

```java
binder.setAllowedFields("name", "email");
binder.setRequiredFields("name");
```

Cho phép bind `name` và `email` không có nghĩa chúng bắt buộc phải xuất hiện; `setRequiredFields("name")` mới bổ sung điều kiện required ở binding layer. Cần phân biệt với `@NotBlank`/`@NotNull` của Jakarta Bean Validation, vì validation kiểm tra **giá trị object sau binding** và có semantics khác với input missing.

Có thể kết hợp allowed và disallowed fields, nhưng hãy ưu tiên **allowlist rõ ràng**. Denylist có nguy cơ bỏ sót property mới, như `role` hoặc `creditLimit`, nếu developer bổ sung field sau này mà quên cập nhật danh sách cấm. Khi kết hợp, cần hiểu thứ tự lọc và kiểm thử các path đặc thù.

## 8. Giới hạn: constructor binding không giống property binding

Ở Spring Framework hỗ trợ constructor binding, một object có thể được tạo từ constructor arguments trước khi gắn properties. `setAllowedFields` điều khiển **property binding**, không nên mặc nhiên coi nó là danh sách cho phép các constructor parameters. Một record có constructor parameter `admin` vẫn có thể nhận input tương ứng ở đường constructor binding nếu model và resolver cho phép.

Giải pháp thiết kế an toàn là **request DTO chỉ chứa những field công khai**; tránh dùng domain entity có thuộc tính quản trị làm request target. Với phiên bản Spring hỗ trợ `setDeclarativeBinding(true)`, có thể khai báo một chiến lược chỉ cho constructor binding và property binding được kiểm soát rõ, nhưng vẫn phải xác định constructor parameters nào an toàn.

Ví dụ DTO:

```java
public record UpdateProfileRequest(String displayName, String email) {}
```

Loại DTO này không có tham số constructor `admin` để client yêu cầu set theo hợp đồng request. Khi chuyển sang entity, service vẫn phải kiểm tra quyền và chọn các field được cập nhật.

## 9. Kiểm thử allowlist

Với unit test trên `DataBinder`, tối thiểu cần kiểm tra:

1. Chỉ có các field hợp lệ: gắn đúng giá trị, không có suppressed fields.
2. Có field ngoài allowlist: không thay đổi property đó, `getSuppressedFields()` chứa tên đúng.
3. Tên nested path không cho phép: bị suppress, không tạo/nới object graph ngoài dự kiến.
4. Wildcard nếu dùng: thử cả tên hợp lệ và tên nhạy cảm tương tự.
5. Các field hợp lệ nhưng sai kiểu: nhận lỗi conversion/binding theo đúng policy.
6. Trường bắt buộc vắng mặt: có phản hồi cần thiết theo required/validation rules.
7. Cả Spring MVC và Java unit test: kiểm tra `@InitBinder` thật sự áp dụng cho model name đã chọn.

JUnit 5 snippet (dùng class `ProfileForm` ở ví dụ chính):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

class AllowedFieldsTest {
    @Test
    void disallowsAdminProperty() {
        var form = new AllowedFieldsDemo.ProfileForm();
        var binder = new DataBinder(form);
        binder.setAllowedFields("displayName", "email");
        binder.bind(new MutablePropertyValues(java.util.Map.of(
                "displayName", "An", "admin", "true")));

        assertEquals("An", form.getDisplayName());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[]{"admin"},
                binder.getBindingResult().getSuppressedFields());
    }
}
```

Snippet kiểm thử này cần dependencies Spring và JUnit trên classpath; nó không phải một chương trình `main`. Khi sử dụng trong thực tế, kiểm thử các field nhạy cảm thực sự của hệ thống, không chỉ field minh họa `admin`.

## 10. Những sai lầm thường gặp

- **Chỉ ẩn field trên HTML form:** không có tác dụng bảo mật server-side, vì client có thể gửi parameter thủ công.
- **Dùng entity trực tiếp làm request model:** dễ vô tình mở quyền ghi vào property nhạy cảm; tách request DTO.
- **Chỉ dùng `setDisallowedFields("admin")`:** có thể bỏ qua các field nhạy cảm được bổ sung sau; allowlist phù hợp hơn.
- **Đặt allowed fields sau binding:** quá muộn để ngăn những setter đã được gọi.
- **Không kiểm tra suppressed fields:** ứng dụng bỏ qua yêu cầu sửa dữ liệu trái phép mà không phát hiện.
- **Dùng pattern quá rộng:** wildcard có thể cho phép cả nested property không mong muốn.
- **Cho rằng allowed fields là validation:** nó chỉ kiểm soát khả năng gán, không đảm bảo email hợp lệ hoặc tuổi đạt yêu cầu.
- **Cho rằng nó bảo vệ `@RequestBody` JSON trong mọi trường hợp:** JSON binding thường do `HttpMessageConverter` điều phối, không đồng nghĩa property binding của `DataBinder`.
- **Cho rằng nó chặn mọi constructor parameter:** cần thiết kế constructor/DTO riêng.
- **Không kiểm tra quyền ở service layer:** allowlist không thay thế kiểm tra ai được sửa bản ghi và được thay đổi field nào.

## 11. Checklist áp dụng an toàn

1. Tạo DTO đầu vào nhỏ, chỉ gồm những trường client cần chỉnh sửa.
2. Với property binding, thiết lập `setAllowedFields` trước mọi lời gọi bind.
3. Trong Spring MVC, dùng `@InitBinder` có phạm vi đúng model name.
4. Không cho phép wildcard rộng nếu không kiểm thử toàn bộ thuộc tính nested liên quan.
5. Đọc cả `BindingResult.hasErrors()` **và** `getSuppressedFields()`.
6. Từ chối field bị suppress nếu hợp đồng API quy định request không được chứa chúng.
7. Tiếp tục chạy conversion, validation và kiểm tra quyền thay đổi ở tầng nghiệp vụ.
8. Tạo test khi DTO thay đổi, nhất là thêm properties mới hoặc mở rộng constructor.

**Ghi nhớ:** `setAllowedFields` giúp ngăn over-posting bằng cách chỉ cho phép Spring bind đúng các property paths được liệt kê. Kết hợp DTO tối thiểu, kiểm tra suppressed fields, validation và authorization mới tạo nên ranh giới dữ liệu đầu vào đáng tin cậy.
