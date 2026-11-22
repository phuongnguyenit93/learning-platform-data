# Kiểm thử allowedFields, suppressedFields và giới hạn auto-grow trong Spring Data Binding

## 1. Mục tiêu bài học

**Data binding** biến HTTP request parameters, form fields hoặc các giá trị đầu vào khác thành thuộc tính Java object. Tính năng này hữu ích, nhưng dễ gây **mass assignment/overposting** nếu client có thể gửi thêm tên field mà giao diện không hiển thị.

Ví dụ một trang chỉnh hồ sơ chỉ cho phép sửa `nickname` và `address.city`. Nhưng JavaBean có cả `admin`, `address.verified`, `items[0].discount`. Một client có thể tự tạo request:

~~~http
POST /binding/profile
Content-Type: application/x-www-form-urlencoded

nickname=Lan&admin=true&address.verified=true&items[0].discount=99
~~~

Để kiểm thử binder an toàn, phải chứng minh **cả điều được phép và điều bị cấm**:

1. `setAllowedFields(...)` thực sự giới hạn writable property paths.
2. `BindingResult#getSuppressedFields()` ghi nhận field bị loại ở đường **property binding**.
3. `getSuppressedFields()` không đồng nghĩa `hasErrors()` và **không tự biến request thành HTTP 400**.
4. Nested paths, indexed paths và wildcard patterns không mở rộng bề mặt cập nhật ngoài thiết kế.
5. `setAutoGrowNestedPaths(...)` điều khiển tạo nested objects từ null.
6. `setAutoGrowCollectionLimit(...)` kiểm soát **mức tự mở rộng list/array**, phải test index ở ngay dưới và ngay tại giới hạn.
7. `setDeclarativeBinding(true)`, constructor binding và `@RequestBody` JSON có quy tắc riêng; không suy rộng kết quả test property binding sang tất cả input pathways.

Bài có **unit tests dùng `DataBinder`** và **integration tests dùng `MockMvc`**, với Java 17+, Spring Boot 3.2+ (Spring Framework 6.1+). Phần cuối giải thích giới hạn bảo mật, bao gồm cảnh báo Spring công bố năm 2026 liên quan đến custom list tự mở rộng.

## 2. API cốt lõi và phạm vi áp dụng

| API | Ý nghĩa | Assertion quan trọng |
| --- | --- | --- |
| `DataBinder#setAllowedFields(String...)` | Đăng ký allowlist cho property/setter binding. | Allowed property được gán; field còn lại không thay đổi. |
| `BindingResult#getSuppressedFields()` | Các property names bị loại bởi allowed/disallowed fields filter khi bind. | Chứa đúng field bị chặn; có thể rỗng dù input bị bỏ theo cơ chế khác. |
| `BindingResult#hasErrors()` | Có binding/conversion/validation errors. | Không thay cho việc kiểm tra suppression. |
| `DataBinder#setAutoGrowNestedPaths(boolean)` | Cho phép tự tạo intermediate object đang null và tăng collection khi access index. | Bật thì có thể tạo nested bean; tắt thì không. |
| `DataBinder#setAutoGrowCollectionLimit(int)` | Giới hạn auto-growth với list/array trong setter/property binding. | Index dưới limit có thể thành công; tại/vượt limit không tự tăng. |
| `DataBinder#getAutoGrowCollectionLimit()` | Giá trị limit hiện tại. | Default **256** ở DataBinder chuẩn. |
| `DataBinder#setDeclarativeBinding(true)` | Constructor binding vẫn được phép; property binding chỉ được dùng nếu có `allowedFields`. | No allowlist trên JavaBean setter-only → không bind setters. |
| `DataBinder#setIgnoreUnknownFields(...)` | Điều khiển cách xử lý property không tồn tại. | Unknown field không nhất thiết là suppressed field. |
| `DataBinder#setIgnoreInvalidFields(...)` | Xử lý một số inaccessible nested properties. | Không phải cơ chế cho phép bind mọi invalid path. |
| `WebDataBinder` và `@InitBinder` | Kết nối policy với controller/model attribute. | HTTP integration test chứng minh binder đúng được gọi. |
| `@Valid`/`@Validated` | Constraint validation sau binding. | Test riêng với suppression và conversion. |

**Phân biệt:** allowlist trả lời câu hỏi **field nào được ghi**; auto-grow limit trả lời **collection có thể tự mở rộng tới mức nào**. Một path vẫn có thể vượt limit dù được allowlist; một index còn trong limit vẫn phải bị chặn nếu path ngoài allowlist.

## 3. Các test cần có đối với allowedFields

### 3.1. Không cấu hình allowlist: test để nhìn rõ rủi ro

Ví dụ JavaBean có:

~~~java
public class ProfileForm {
    private String nickname;
    private boolean admin;

    public String getNickname() { return nickname; }
    public void setNickname(String value) { this.nickname = value; }
    public boolean isAdmin() { return admin; }
    public void setAdmin(boolean value) { this.admin = value; }
}
~~~

Đây là snippet rút gọn; file chạy đầy đủ ở phần 8 thêm nested objects và list.

Nếu không giới hạn fields:

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profileForm");

binder.bind(new MutablePropertyValues(Map.of(
        "nickname", "Lan",
        "admin", "true"
)));

assertEquals("Lan", form.getNickname());
assertTrue(form.isAdmin());
~~~

Trong trường hợp này, binding mặc định có thể gán `admin=true`. Đây là **anti-pattern regression test** nhằm chứng minh vì sao cần chính sách input, không phải lời khuyên bind trực tiếp JPA entity vào public API.

### 3.2. Allowlist chỉ cho phép nickname

~~~java
ProfileForm form = new ProfileForm();
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAllowedFields("nickname");

binder.bind(new MutablePropertyValues(Map.of(
        "nickname", "Lan",
        "admin", "true"
)));

assertEquals("Lan", form.getNickname());
assertFalse(form.isAdmin());
assertArrayEquals(
        new String[] {"admin"},
        binder.getBindingResult().getSuppressedFields());
~~~

Spring loại `admin` khỏi danh sách property values để gán. Nhưng **chính sách chặn field và chính sách trả lỗi HTTP là hai thứ khác nhau**.

### 3.3. suppressedFields khác binding errors

Với ví dụ trên, kết quả điển hình:

~~~text
nickname = "Lan"
admin = false
getSuppressedFields() = ["admin"]
hasErrors() = false
~~~

Vì field đã bị **loại trước khi write**, Spring không nhất thiết phát sinh `FieldError`. Không được kiểm tra chỉ `result.hasErrors()` để khẳng định không có overpost.

Nếu business API yêu cầu từ chối request gửi field ngoài schema:

~~~java
if (result.hasErrors()
        || result.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest()
            .body(Map.of("code", "INVALID_INPUT"));
}
~~~

Ở đây HTTP 400 là **quyết định của controller**, không phải lời hứa mặc định của `DataBinder`. Ứng dụng khác có thể bỏ qua fields bị suppressed và trả 200 nếu đó là hợp đồng mong muốn.

### 3.4. So sánh nhiều field suppressed

Nếu request chứa `admin=true` và `address.verified=true`, test có thể so tập hợp:

~~~java
Set<String> actual = Set.copyOf(Arrays.asList(
        result.getSuppressedFields()));

assertEquals(Set.of("admin", "address.verified"), actual);
~~~

Không phụ thuộc thứ tự trả về nếu thứ tự không phải contract. Giữ nguyên tên property cho phép debug nhưng **không log/serialize nguyên input values**; rejected values có thể là password, token hoặc dữ liệu nhạy cảm.

## 4. Nested và indexed property paths

Giả sử object có:

~~~text
nickname
admin
address.city
address.verified
items[0].sku
items[0].quantity
items[0].discount
items[1].sku
items[2].sku
~~~

Cấu hình allowlist:

~~~java
binder.setAllowedFields(
        "nickname",
        "address.city",
        "items[0].sku",
        "items[1].sku");
~~~

| Input key | Được phép? | Vì sao |
| --- | --- | --- |
| `nickname` | Có | Tên field trùng. |
| `address.city` | Có | Đúng nested property path. |
| `address.verified` | Không | Cùng bean nhưng property khác. |
| `items[0].sku` | Có | Đúng element 0 và đúng property. |
| `items[1].sku` | Có | Đúng element 1 và đúng property. |
| `items[2].sku` | Không | Index 2 chưa nằm trong allowlist. |
| `items[0].quantity` | Không | Không cho phép quantity trong form này. |
| `items[0].discount` | Không | Server-owned property. |
| `admin` | Không | Server-owned property. |

### Khi dùng wildcard

~~~java
binder.setAllowedFields("nickname", "items*.sku");
~~~

Pattern `items*.sku` cho phép indexed paths khác nhau, chẳng hạn `items[0].sku` hoặc `items[50].sku`. Nếu API không muốn quá 2 item, **đừng chỉ dựa vào wildcard**. Kết hợp input-size/index policy, auto-grow limit và Bean Validation.

Pattern `items*` còn rộng hơn, có thể match `items[0].discount`. Không dùng `*` cho toàn object khi cần bảo vệ server-owned fields. `setAllowedFields` hỗ trợ wildcard đơn giản theo Spring pattern matching, **không phải regex tự do**.

Các property names có thể được Spring canonicalize khi binding, đặc biệt với map keys và bracket notation. Nếu test dùng `addresses['home'].city` hoặc nested map, đọc `getSuppressedFields()` thực tế và so sánh theo quy tắc canonicalization tương ứng.

## 5. Auto-grow nested paths: khác với giới hạn collection

### 5.1. Tự tạo object lồng khi null

Khi `ProfileForm.address == null` và request gửi `address.city=Da Nang`, với mặc định:

~~~java
binder.setAutoGrowNestedPaths(true);
binder.setAllowedFields("address.city");
binder.bind(new MutablePropertyValues(
        Map.of("address.city", "Da Nang")));
~~~

Spring có thể tạo `Address` nếu type có constructor phù hợp, rồi gán `city`. Assertions:

~~~java
assertNotNull(form.getAddress());
assertEquals("Da Nang", form.getAddress().getCity());
~~~

`setAutoGrowNestedPaths(true)` mặc định bật trên `DataBinder` chuẩn. Nó cũng bật khả năng tăng collection elements khi truy cập index ngoài size hiện tại, nhưng còn phụ thuộc `autoGrowCollectionLimit`.

### 5.2. Tắt auto-grow

~~~java
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(false);
binder.setAllowedFields("address.city");
~~~

Nếu `address` vẫn null, binder không tự tạo nó. Với default-style error handling, có thể nhận `NullValueInNestedPathException`; nếu cấu hình `ignoreInvalidFields=true`, hành vi bỏ qua path có thể khác. Hãy **test cấu hình thật**, đừng viết assertion về exception class dựa trên suy đoán hoặc một Spring version khác.

### 5.3. Cấu hình trước khi binder khởi tạo

Với `DataBinder`, hãy gọi auto-grow setters **trước** `getBindingResult()`/`bind(...)`:

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("address.city", "items*.sku");

binder.bind(new MutablePropertyValues(Map.of(
        "address.city", "Hue")));
~~~

Javadoc `setAutoGrowCollectionLimit` nêu rõ cấu hình này không được thay khi binder đã khởi tạo `BindingResult`; nếu gọi muộn có thể ném `IllegalStateException`. Vì vậy có unit test "configuration-after-initialization fails".

## 6. autoGrowCollectionLimit: test đúng biên 0-based

`DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` có giá trị **256**. Khi cấu hình:

~~~java
binder.setAutoGrowCollectionLimit(2);
~~~

và `items` là `new ArrayList<LineItem>()`, các index:

| Index | Cần số phần tử sau auto-grow | Với limit = 2 |
| --- | --- | --- |
| `items[0].sku` | 1 | Có thể tạo. |
| `items[1].sku` | 2 | Có thể tạo. |
| **`items[2].sku`** | **3** | **Không tự mở rộng đến phần tử thứ ba**. |
| `items[999999].sku` | Rất lớn | Không được tự tăng. |

Đây là giới hạn **auto-grow qua property binding trên list/array**, không phải một validation tổng quát cho mọi collection trong object, không phải giới hạn của Map, và **không áp dụng cho constructor binding `DataBinder.construct(...)`** theo Javadoc 6.x.

### Test tại index cuối còn hợp lệ

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("items*.sku");

binder.bind(new MutablePropertyValues(
        Map.of("items[1].sku", "P02")));

assertEquals(2, form.getItems().size());
assertEquals("P02", form.getItems().get(1).getSku());
~~~

Để snippet này chạy, `ProfileForm` phải chứa `List<LineItem> items = new ArrayList<>()` và `LineItem` có public no-arg constructor/getter/setter; bản đầy đủ ở phần 8.

### Test tại index đầu vượt giới hạn

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowCollectionLimit(2);
binder.setAllowedFields("items*.sku");

assertThrows(InvalidPropertyException.class, () ->
        binder.bind(new MutablePropertyValues(
                Map.of("items[2].sku", "P03"))));
~~~

Với **Spring Framework 6.1/6.2 và `ArrayList` tiêu chuẩn**, việc cố đọc phần tử ngoài giới hạn khi không thể auto-grow thường ném `InvalidPropertyException`. Đó là hành vi infrastructure; **không mặc nhiên suy ra HTTP 400**. Nếu một phiên bản khác trả lỗi qua `BindingResult` hoặc exception wrapper, điều phải bảo vệ là **không mở rộng list ngoài policy** và endpoint xử lý input lỗi đúng cách.

### Ngăn index lớn trước khi property traversal

Nếu binder chỉ cho phép `nickname`:

~~~java
binder.setAllowedFields("nickname");
binder.bind(new MutablePropertyValues(
        Map.of("items[999999].sku", "P99")));

assertEquals(0, form.getItems().size());
assertArrayEquals(
        new String[] {"items[999999].sku"},
        binder.getBindingResult().getSuppressedFields());
~~~

Path bị chặn bởi allowlist **trước khi Spring truy cập collection**, nên demo dùng index lớn trong trường hợp này an toàn với `ArrayList` chuẩn. Không dùng custom self-populating list hoặc stress test vô hạn trong môi trường production.

### Những giới hạn khác vẫn cần

- HTTP request body size, parameter count và chiều sâu nested input.
- Number of collection items theo business rule, ví dụ `@Size(max=2)`.
- Constructor binding và `@RequestBody` JSON/Jackson cần giới hạn riêng.
- List đã có nhiều phần tử ban đầu không tự nhỏ đi khi cấu hình limit mới.
- Map entries không bị khống chế bởi list/array auto-grow limit.
- Cấu trúc object graph và collection implementation có thể ảnh hưởng hành vi.

Đặc biệt, `@Size(max=2)` chạy **sau khi input đã bind** nên không phải hàng rào ngăn allocation quá lớn trong giai đoạn binding.

## 7. Ba loại thất bại nên được test tách biệt

| Loại | Ví dụ | Tín hiệu |
| --- | --- | --- |
| **Suppression** | `admin=true` ngoài allowlist | `getSuppressedFields()` chứa `admin`, có thể `hasErrors()==false`. |
| **Type mismatch** | `items[0].quantity=abc` khi quantity được phép bind vào `int` | `FieldError` mã `typeMismatch`, không phải suppressed field. |
| **Bean Validation** | `nickname=""` và `@NotBlank` | Lỗi `NotBlank` sau khi bind/validate. |
| **Auto-grow path limit** | `items[2].sku`, allowlist `items*.sku`, limit 2 | Không được auto-grow; có thể exception của property accessor. |
| **Unknown property** | `ghost=1` khi target không có `ghost` | Do `setIgnoreUnknownFields` quyết định; không đồng nghĩa suppressed. |

Không chỉ assert `hasErrors()` để chứng minh không có overposting. Để test conversion, phải **allow** field tương ứng; nếu bạn cấm `quantity`, Spring sẽ suppress trước và không còn phép conversion để kiểm tra.

Pure `DataBinder#bind` **không tự chạy `@NotBlank`** trên JavaBean. Unit tests bind và validation phải tách; MVC endpoint có `@Valid @ModelAttribute` mới kích hoạt Bean Validation (khi provider đã cấu hình).

## 8. Dự án mẫu chạy được: Java 17+, Spring Boot 3.2+ và JUnit 5

Dùng Maven project đã cấu hình Spring Boot parent/BOM, chọn bản Framework đã vá theo security policy. Thêm:

~~~xml
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
~~~

Java classes dùng package `com.example.bindingtests`. Dự án này dùng **Servlet Spring MVC và MockMvc**, không phải Spring WebFlux; dữ liệu form được tạo trong tests bằng `.param(...)`. Không cần database, security hay persistence layer để test binder. Trong ứng dụng thật, còn phải kiểm tra quyền/tenant khi cập nhật.

### 8.1. File `BindingTestsApplication.java`

Tạo `src/main/java/com/example/bindingtests/BindingTestsApplication.java`:

~~~java
package com.example.bindingtests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingTestsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindingTestsApplication.class, args);
    }
}
~~~

### 8.2. File `ProfileForm.java`

Tạo `src/main/java/com/example/bindingtests/ProfileForm.java`:

~~~java
package com.example.bindingtests;

import jakarta.validation.constraints.NotBlank;

import java.util.ArrayList;
import java.util.List;

public class ProfileForm {

    @NotBlank
    private String nickname;

    private boolean admin;

    private Address address;

    private List<LineItem> items = new ArrayList<>();

    public ProfileForm() {
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }

    public static class Address {

        private String city;
        private boolean verified;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public boolean isVerified() {
            return verified;
        }

        public void setVerified(boolean verified) {
            this.verified = verified;
        }
    }

    public static class LineItem {

        private String sku;
        private int quantity;
        private int discount;

        public LineItem() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public int getDiscount() {
            return discount;
        }

        public void setDiscount(int discount) {
            this.discount = discount;
        }
    }
}
~~~

Fields `admin`, `verified`, `discount` được thêm **chỉ để test rằng binder không cho sửa**. Production nên dùng một request DTO không có server-owned properties thay vì đưa JPA entity vào `@ModelAttribute`. `ArrayList` và public nested classes có no-arg constructors cho phép Spring thử auto-grow path.

### 8.3. File `BindingController.java`

Tạo `src/main/java/com/example/bindingtests/BindingController.java`:

~~~java
package com.example.bindingtests;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/binding")
public class BindingController {

    @InitBinder("profileForm")
    public void configure(WebDataBinder binder) {
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields(
                "nickname",
                "address.city",
                "items[0].sku",
                "items[1].sku");
    }

    @PostMapping(path = "/profile",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> save(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("code", "INVALID_INPUT"));
        }

        String city =
                form.getAddress() == null
                || form.getAddress().getCity() == null
                    ? ""
                    : form.getAddress().getCity();

        return ResponseEntity.ok(Map.of(
                "nickname", form.getNickname(),
                "city", city,
                "admin", form.isAdmin(),
                "itemCount", form.getItems().size()));
    }
}
~~~

`@InitBinder("profileForm")` gắn binder policy cho đúng `@ModelAttribute("profileForm")`. Controller chủ động trả HTTP **400** khi có binding errors **hoặc** suppressed fields. Nếu chỉ kiểm tra `result.hasErrors()`, nó có thể bỏ qua overposted field và trả 200.

Không cần tiết lộ tên field bị suppressed hoặc raw values trong response. Response `admin=false` ở demo chỉ để test không bị mass assignment; đừng trả security flags trong API public khi không có nhu cầu.

### 8.4. File `DataBinderPolicyTest.java` — 15 unit tests

Tạo `src/test/java/com/example/bindingtests/DataBinderPolicyTest.java`:

~~~java
package com.example.bindingtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.InvalidPropertyException;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class DataBinderPolicyTest {

    private DataBinder binder(ProfileForm form, String... fields) {
        DataBinder binder = new DataBinder(form, "profileForm");
        binder.setAllowedFields(fields);
        return binder;
    }

    @Test
    void allowedNicknameAndSuppressedAdmin() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void suppressedDoesNotAutomaticallyMeanBindingError() {
        var binder = binder(new ProfileForm(), "nickname");

        binder.bind(new MutablePropertyValues(
                Map.of("admin", "true")));

        assertFalse(binder.getBindingResult().hasErrors());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void compareMultipleSuppressedFieldsWithoutOrdering() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname", "address.city");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan",
                "admin", "true",
                "address.verified", "true")));

        Set<String> suppressed = Set.copyOf(Arrays.asList(
                binder.getBindingResult().getSuppressedFields()));

        assertEquals(Set.of("admin", "address.verified"),
                suppressed);
        assertFalse(form.isAdmin());
    }

    @Test
    void nestedCityIsBoundButVerifiedFlagIsNot() {
        var form = new ProfileForm();
        var binder = binder(form, "address.city");

        binder.bind(new MutablePropertyValues(Map.of(
                "address.city", "Da Nang",
                "address.verified", "true")));

        assertNotNull(form.getAddress());
        assertEquals("Da Nang", form.getAddress().getCity());
        assertFalse(form.getAddress().isVerified());
        assertArrayEquals(
                new String[] {"address.verified"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void nestedAutoGrowIsEnabledByDefault() {
        var form = new ProfileForm();
        var binder = binder(form, "address.city");

        assertTrue(binder.isAutoGrowNestedPaths());
        binder.bind(new MutablePropertyValues(
                Map.of("address.city", "Hue")));

        assertEquals("Hue", form.getAddress().getCity());
    }

    @Test
    void disablingNestedAutoGrowDoesNotCreateAddress() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowNestedPaths(false);
        binder.setIgnoreInvalidFields(false);
        binder.setAllowedFields("address.city");

        assertThrows(NullValueInNestedPathException.class,
                () -> binder.bind(new MutablePropertyValues(
                        Map.of("address.city", "Hue"))));

        assertNull(form.getAddress());
    }

    @Test
    void explicitIndexPolicySuppressesNextIndex() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items[0].sku");

        binder.bind(new MutablePropertyValues(Map.of(
                "items[0].sku", "P01",
                "items[1].sku", "P02")));

        assertEquals(1, form.getItems().size());
        assertEquals("P01", form.getItems().get(0).getSku());
        assertArrayEquals(
                new String[] {"items[1].sku"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void wildcardIndexBelowLimitCanGrowList() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items*.sku");

        binder.bind(new MutablePropertyValues(
                Map.of("items[1].sku", "P02")));

        assertEquals(2, form.getItems().size());
        assertEquals("P02", form.getItems().get(1).getSku());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void indexAtLimitIsNotAllowedToAutoGrowArrayList() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setAutoGrowCollectionLimit(2);
        binder.setAllowedFields("items*.sku");

        assertThrows(InvalidPropertyException.class,
                () -> binder.bind(new MutablePropertyValues(
                        Map.of("items[2].sku", "P03"))));

        assertTrue(form.getItems().size() <= 2);
    }

    @Test
    void hugeDisallowedIndexIsSuppressedWithoutGrowth() {
        var form = new ProfileForm();
        var binder = binder(form, "nickname");

        binder.bind(new MutablePropertyValues(
                Map.of("items[999999].sku", "P99")));

        assertEquals(0, form.getItems().size());
        assertArrayEquals(
                new String[] {"items[999999].sku"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void standardDefaultCollectionLimitIs256() {
        var binder = new DataBinder(
                new ProfileForm(), "profileForm");

        assertEquals(
                DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
                binder.getAutoGrowCollectionLimit());
        assertEquals(256, binder.getAutoGrowCollectionLimit());
    }

    @Test
    void configurationAfterResultInitializationFails() {
        var binder = new DataBinder(
                new ProfileForm(), "profileForm");

        binder.getBindingResult();
        assertThrows(IllegalStateException.class,
                () -> binder.setAutoGrowCollectionLimit(2));
    }

    @Test
    void declarativeModeWithoutAllowlistSkipsSetters() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setDeclarativeBinding(true);

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertNull(form.getNickname());
        assertFalse(form.isAdmin());
        assertEquals(0,
                binder.getBindingResult()
                        .getSuppressedFields().length);
    }

    @Test
    void declarativeModeWithAllowlistBindsOnlyNickname() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("nickname");

        binder.bind(new MutablePropertyValues(Map.of(
                "nickname", "Lan", "admin", "true")));

        assertEquals("Lan", form.getNickname());
        assertFalse(form.isAdmin());
        assertArrayEquals(new String[] {"admin"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void unrestrictedPropertyBindingCanSetAdmin() {
        var form = new ProfileForm();
        var binder = new DataBinder(form, "profileForm");

        binder.bind(new MutablePropertyValues(
                Map.of("admin", "true")));

        // Negative-security regression: lý do phải dùng allowlist.
        assertTrue(form.isAdmin());
    }
}
~~~

**15 unit tests** này được thiết kế để kiểm chứng rõ hai ranh giới: **tên property được phép bind** và **khả năng tăng kích thước list**. Test `indexAtLimitIsNotAllowedToAutoGrowArrayList` phụ thuộc hành vi của `InvalidPropertyException` ở Spring 6.1/6.2 và `ArrayList` chuẩn; nếu đổi implementation hoặc Spring version, cần xác nhận exception thực tế, không nên assert raw exception message.

### 8.5. File `BindingControllerTest.java` — 7 MockMvc tests

Tạo `src/test/java/com/example/bindingtests/BindingControllerTest.java`:

~~~java
package com.example.bindingtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BindingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFieldsReachController() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("address.city", "Da Nang")
                    .param("items[0].sku", "P01"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("Lan"))
                .andExpect(jsonPath("$.city").value("Da Nang"))
                .andExpect(jsonPath("$.itemCount").value(1))
                .andExpect(jsonPath("$.admin").value(false));
    }

    @Test
    void secondItemWithinLimitCanGrow() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[1].sku", "P02"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(2));
    }

    @Test
    void overpostedAdminIsRejectedByController() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("admin", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void nestedVerifiedFieldIsSuppressed() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("address.city", "Da Nang")
                    .param("address.verified", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void itemDiscountIsNotWritable() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[0].sku", "P01")
                    .param("items[0].discount", "99"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void thirdSkuIndexIsSuppressedBeforeTraversal() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", "Lan")
                    .param("items[2].sku", "P03"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void blankNicknameFailsBeanValidation() throws Exception {
        mvc.perform(post("/binding/profile")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("nickname", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
~~~

**7 MockMvc tests** xác nhận `@InitBinder` thực sự áp dụng cho request qua HTTP. Đặc biệt, test index thứ 3 ở HTTP chứng minh **allowlist** chặn trước property traversal; unit test với wildcard chứng minh ranh giới **auto-grow**. Hai thứ không được đánh đồng.

### 8.6. Chạy kiểm thử

~~~bash
./mvnw test -Dtest=DataBinderPolicyTest,BindingControllerTest
~~~

Trên Windows:

~~~powershell
mvnw.cmd test -Dtest=DataBinderPolicyTest,BindingControllerTest
~~~

Hoặc `mvn test` nếu Maven đã được cài. Có tổng cộng **22 test cases** được thiết kế để pass khi code và dependencies tương thích. Không khẳng định đã chạy Maven/JUnit chỉ vì test source có mặt. Output của Surefire/JUnit thay đổi theo cấu hình; các assertions mới là **hợp đồng chính xác**.

## 9. Ma trận kiểm thử và phân tích kết quả

| Nhóm | Input/test | Kết quả mong đợi |
| --- | --- | --- |
| Positive allowlist | `nickname=Lan` | Nickname nhận đúng chuỗi. |
| Overposting | `admin=true` | Admin vẫn false, field bị suppressed. |
| Suppression vs errors | Chỉ gửi `admin=true` | `hasErrors()==false`, suppressed không rỗng. |
| Multi-suppressed | Admin + address verified | So `Set.of(...)` không phụ thuộc thứ tự. |
| Nested allowed | `address.city=Hue` khi address null | Auto tạo Address, gán city. |
| Nested disallowed | `address.verified=true` | Không thay verified flag. |
| Disable nested growth | `address.city=Hue`, autoGrow=false | Không tạo Address; có exception theo cấu hình test. |
| Indexed allowlist | `items[0].sku` | Item 0 được gán. |
| Indexed forbidden | `items[1].sku` khi chỉ allow index 0 | Item 1 suppressed. |
| Boundary limit | `items[1].sku` với limit 2 | List có 2 phần tử. |
| Boundary overflow | `items[2].sku` với limit 2 | Không tạo phần tử thứ 3; Spring 6.1/6.2 có InvalidPropertyException. |
| Large index denied | `items[999999].sku` ngoài allowlist | Bị suppressed trước khi truy cập list. |
| Declarative without allowlist | Setter-only target | Không bind các setters; không mặc định có suppressed list. |
| Declarative with allowlist | Nickname và admin | Chỉ nickname bind, admin suppressed. |
| No allowlist anti-pattern | `admin=true` | Test cho thấy admin **có thể** thành true. |
| HTTP positive | Form nickname/city/SKU hợp lệ | HTTP 200; values đúng. |
| HTTP overpost | Admin/verified/discount/index2 | HTTP 400 do controller policy. |
| Bean Validation | Nickname blank | HTTP 400 do `@NotBlank`. |

Chạy tests trước và sau khi thay:
- Form DTO fields, nested object graph hoặc collection type.
- Tên `@ModelAttribute` và `@InitBinder`.
- Allowed field patterns, max list size, auto-grow setting.
- Spring Framework/Boot versions.
- MVC ↔ WebFlux, form ↔ JSON pipeline.

**Không sửa một test để nó pass bằng cách nới `allowedFields` quá rộng**, trừ khi product/security contract thực sự cho phép trường đó.

## 10. Khi không nên kỳ vọng suppressedFields

### 10.1. Constructor-only binding

`setDeclarativeBinding(true)` cho phép constructor binding và bỏ qua property binding nếu chưa cấu hình `allowedFields`. Điều này **không đồng nghĩa** mọi extra HTTP key đều được ghi vào `getSuppressedFields()`. Nếu yêu cầu "mọi input key lạ đều trả 400", cần thêm strict input schema check.

### 10.2. JSON body

`@RequestBody` JSON đi qua Jackson/HTTP message converters. `WebDataBinder#setAllowedFields(...)` không phải whitelist mọi JSON properties. Dùng DTO riêng, cấu hình unknown-key policy của Jackson, kiểm tra JSON size/nesting và constraints trên collection.

### 10.3. Unknown property và suppressed field

`setIgnoreUnknownFields(true)` mặc định bỏ qua những input properties không có tương ứng trong target. Nó không được thiết kế làm danh sách lỗi overposting. Ngược lại, `getSuppressedFields()` phản ánh những fields bị **policy của binder** từ chối. Nếu cần strict schema, test cả unknown field detection riêng.

### 10.4. Type mismatch và validator errors

Property `quantity` được allow nhưng có chuỗi `"abc"` không đổi được thành `int` → `FieldError` kiểu `typeMismatch`. Constraint `@NotBlank` trên nickname chỉ được đánh giá khi có validation step. Cả hai không phải suppressed fields, dù thường đều nên dẫn tới 400 ở API.

## 11. Bảo mật và các giới hạn của auto-grow

### 11.1. Không coi default 256 là giới hạn toàn bộ HTTP request

`autoGrowCollectionLimit=256` chỉ điều khiển một loại tăng trưởng array/list trong data binder. Nó không thay thế:

- Giới hạn kích thước HTTP body và tổng số parameters.
- Schema cho allowed indexed property names.
- Giới hạn nesting depth và số collection elements theo domain.
- JSON parser constraints và Jackson settings.
- Authorization ở service; không cho client thay role, tenant, admin flags.
- Input DTO riêng; không bind trực tiếp JPA entity chứa các setters nhạy cảm.

Với một form tối đa 2 SKU, việc cấu hình `allowedFields("items[0].sku","items[1].sku")` cùng `setAutoGrowCollectionLimit(2)` dễ kiểm thử hơn wildcard `items*`.

### 11.2. Cảnh báo Spring CVE-2026-59282 (20/08/2026)

Spring công bố **CVE-2026-59282 — Denial of Service via Unbounded List Growth in Data Binding**, liên quan đến trường hợp **self-populating custom List** mà thao tác `get(index)` tự tạo phần tử. Khi một nested property path dùng chỉ số do client cung cấp, list loại này có thể phân bổ bộ nhớ ngay khi được truy cập, dù binder có limit không cho phép tăng trưởng thông thường.

Tài liệu Spring nêu các nhánh bị ảnh hưởng, ví dụ:
- **7.0.0–7.0.8**, bản vá OSS **7.0.9**.
- **6.2.0–6.2.19**, bản vá **6.2.20** qua kênh hỗ trợ tương ứng.
- Các nhánh 6.1/6.0/5.x cũng có phiên bản vá riêng theo advisory.

Đây là một trường hợp **đặc thù của collection implementation**, **không phải `ArrayList` chuẩn trong bộ test trên**. Cách phòng ngừa: nâng cấp Spring Framework theo advisory; không nhận untrusted indexed paths vào self-populating lists; DTO nhỏ, allowlist rõ, giới hạn request size và input index. **Không stress production với một PoC cấp phát vô hạn** chỉ để kiểm thử.

Nguồn Spring chính thức: https://spring.io/security/cve-2026-59282/

### 11.3. Test an toàn thay vì thử tấn công tài nguyên

Bộ test dùng `items[1]`/`items[2]` với limit 2 để kiểm tra boundary, và dùng key lớn chỉ khi allowlist đã chặn **trước traversal**. Nếu triển khai custom collection, hãy dùng security tests kiểm tra contract và memory budget trong môi trường sandbox có resource limits. Không dùng các index cực lớn trên một self-populating collection chưa được vá.

## 12. Troubleshooting

### `getSuppressedFields()` rỗng dù request có field lạ

Kiểm tra `@InitBinder` có gắn đúng object name không, có gọi `setAllowedFields` không, đang dùng constructor-only declarative mode hay JSON `@RequestBody` không, và field có thực sự đi qua property-binding filter không. Cấu hình `setDeclarativeBinding(true)` mà không allowlist bỏ qua **toàn bộ setter binding**, nên suppressed list không nhất thiết có các keys.

### `address.city` không được gán

Xác minh `Address` có thể được tạo (public no-arg constructor/bean access), `setAutoGrowNestedPaths(true)`, exact allowed path `address.city`, getter/setter và target object state. Nếu đã gọi `getBindingResult()` trước khi config auto-grow, sửa thứ tự khởi tạo.

### `items[1].sku` không tự tăng trưởng

Xem mutable `List`, generic element type có thể khởi tạo, `autoGrowNestedPaths` có bật, limit đủ cho index+1, allowed path match, và collection ban đầu có bị thay bằng immutable `List.of(...)` không. Không phải mọi List implementation đều hỗ trợ mutation/auto-grow.

### Test out-of-limit ném exception thay vì trả HTTP 400

Đây là infrastructure behavior. Không tạo `@ExceptionHandler(Exception.class)` trả 400 cho mọi lỗi. Nếu muốn input index vượt giới hạn có response 400 ổn định, **chặn key/index dựa trên route contract trước khi binder traversal**, hoặc xử lý một lỗi input đã phân loại đúng. Tách ra khỏi lỗi server thật.

### `hasErrors()` false dù admin bị chặn

Đúng trong nhiều cấu hình: suppression không đồng nghĩa FieldError. Điều kiện policy cần xét cả `getSuppressedFields().length > 0`.

### Gửi JSON nhưng allowedFields không chặn unknown key

Vì JSON dùng Jackson, không đi qua property binder như form. Tách DTO, deserialization policy và tests.

### Thay version và test exception cụ thể bị fail

Spring có thể điều chỉnh xử lý invalid indexes, error resolution hoặc API packages. Giữ **invariant security**: không gán field cấm, không mở rộng list ngoài policy, trả đúng status đã định nghĩa. Sau đó cập nhật test exception type nếu implementation thay đổi, không sửa allowlist nhằm che lỗi.

## 13. Checklist kiểm thử trước phát hành

- [ ] Có positive test cho từng field được allow.
- [ ] Có negative test cho `admin`, `role`, `tenantId`, nested verification và discount.
- [ ] Test target object **không bị thay đổi** bởi field cấm.
- [ ] Test `getSuppressedFields()` với một và nhiều field; không giả định thứ tự.
- [ ] Test `hasErrors()` riêng với `getSuppressedFields()`.
- [ ] Test nested path được tạo từ null khi auto-grow bật; không được tạo khi tắt.
- [ ] Test index cuối hợp lệ và index đầu vượt `autoGrowCollectionLimit`.
- [ ] Test auto-grow flags được cấu hình **trước** binder init.
- [ ] Test exact indexed allowlist và wildcard riêng.
- [ ] Không nhầm suppressed index với index vượt auto-grow limit.
- [ ] Test `setDeclarativeBinding(true)` có và không có allowlist.
- [ ] Test form binding và JSON `@RequestBody` theo các pipelines riêng.
- [ ] Test `@InitBinder("...")` và `@ModelAttribute("...")` khớp tên.
- [ ] Test `@Valid`, conversion errors, unknown keys và business authorization riêng.
- [ ] Có HTTP integration test (MockMvc hoặc WebTestClient tùy stack).
- [ ] Không trả rejected values hoặc internal object fields trong response/log.
- [ ] Có request-size, parameter-count, index/schema và nesting limits.
- [ ] Kiểm tra Spring version đã vá advisories về data binding.
- [ ] Không dùng self-populating custom List với untrusted indexed input mà chưa đánh giá rủi ro.
- [ ] Chạy lại security regression tests mỗi khi đổi DTO, binder config, controller hoặc dependency.

**Kết luận:** Kiểm thử `allowedFields` phải nhìn cả **field được phép gán** và **field bị suppressed**; kiểm thử `autoGrowCollectionLimit` phải đặt đúng **chỉ số biên** và biết rằng nó chỉ giới hạn một dạng property binding. `BindingResult#hasErrors()` không thay thế `getSuppressedFields()`, còn `setDeclarativeBinding(true)`/constructor binding và JSON có các đường đi riêng. Kết hợp unit tests `DataBinder`, MockMvc integration tests và DTO/authorization/payload policies sẽ giảm nguy cơ mass assignment, hồi quy binding và tăng trưởng tài nguyên ngoài kiểm soát.

## Tài liệu tham khảo

- Spring Framework Javadoc 6.2 — `DataBinder`, `setAllowedFields`, `setAutoGrowCollectionLimit` và `setDeclarativeBinding`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Javadoc 6.2 — `BindingResult#getSuppressedFields()`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework Reference 6.2 — Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework Reference 6.2 — `@InitBinder`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference 6.2 — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference 6.2 — WebFlux data binding: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Security Advisory (20/08/2026) — CVE-2026-59282: https://spring.io/security/cve-2026-59282/
- OWASP Mass Assignment Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
