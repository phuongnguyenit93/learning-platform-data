# Binding collection, Map và tên trường có chỉ số trong Spring MVC

## 1. Bài toán: một form không chỉ có trường đơn

Một trang nhập đơn hàng thường có nhiều dòng hàng, nhãn tùy chọn và thông tin liên hệ theo nhóm:

- Dòng hàng thứ 0: mã `PEN`, số lượng `2`.
- Dòng hàng thứ 1: mã `BOOK`, số lượng `1`.
- Nhãn `priority` có giá trị `high`.
- Email của nhóm `support` là `help@example.com`.

Với `@ModelAttribute` của Spring MVC, các dữ liệu này có thể đi từ request parameters vào một object Java chứa `List` và `Map`, **không cần tự tách từng tên tham số**. Để Spring biết phần tử nào đang được cập nhật, HTML form phải đặt thuộc tính `name` theo **đường dẫn property có dấu ngoặc vuông** (*indexed/keyed property path*).

~~~text
items[0].sku                 = PEN
items[0].quantity            = 2
items[1].sku                 = BOOK
items[1].quantity            = 1
labels[priority]             = high
contacts[support].email      = help@example.com
tags[0]                     = spring
~~~

Kết quả mong muốn trong Java:

~~~text
OrderForm
├── items: List<LineItem>
│   ├── [0] -> { sku="PEN",  quantity=2 }
│   └── [1] -> { sku="BOOK", quantity=1 }
├── labels: Map<String, String>
│   └── ["priority"] -> "high"
├── contacts: Map<String, Contact>
│   └── ["support"] -> { email="help@example.com" }
└── tags: List<String>
    └── [0] -> "spring"
~~~

Bốn ý quan trọng:

1. `[0]`, `[1]` là **vị trí** trong `List`/mảng, bắt đầu từ 0; `[priority]` và `[support]` là **khóa** trong `Map`.
2. Dấu chấm `.` đi vào property của **object nằm trong phần tử**, ví dụ `items[0].sku` và `contacts[support].email`.
3. Spring nhận tên field từ **request**, chuyển kiểu và gán qua `WebDataBinder`. Đây là **data binding**, khác với Bean Validation.
4. Những tên path do client gửi là **input không đáng tin cậy**. Cần giới hạn trường được bind, chỉ số tối đa, kích thước request, và validate cấu trúc trước khi xử lý nghiệp vụ.

Ngữ cảnh bài này là **Spring MVC Servlet stack**, chủ yếu với `application/x-www-form-urlencoded` hoặc form multipart và `@ModelAttribute`. JSON đi qua `@RequestBody` và Jackson theo cơ chế khác, được phân biệt ở mục 8.

## 2. Cú pháp tên trường và cách hiểu

| Tên field trong request/HTML | Property Java đích | Ý nghĩa |
| --- | --- | --- |
| `customerName` | `String customerName` | Property đơn |
| `address.city` | `Address address` | Property lồng nhau |
| `items[0].sku` | `List<LineItem> items` | `sku` của phần tử list tại index 0 |
| `items[3].quantity` | `List<LineItem> items` | `quantity` của phần tử index 3 |
| `tags[0]` | `List<String> tags` | Chuỗi ở index 0 |
| `codes[1]` | `String[] codes` | Phần tử mảng tại index 1 |
| `labels[priority]` | `Map<String,String> labels` | Value của key `"priority"` |
| `contacts[support].email` | `Map<String,Contact> contacts` | Property `email` của object gắn với key `"support"` |

Các cặp ngoặc vuông có ý nghĩa theo **kiểu property** đã khai báo:

- Với `List<T>` hoặc array, phần trong ngoặc là **index nguyên, không âm**.
- Với `Map<K,V>`, phần trong ngoặc được diễn giải như **key**, có thể cần conversion sang kiểu `K` (ví dụ `Integer`).
- Với nested bean, dấu chấm phân cách các property của object graph.
- Với object graph nhiều tầng, có thể dùng `groups[0].members[1].name` nếu các property, constructors, setters và cấu trúc dữ liệu thực tế hỗ trợ.

Tên `items[0].sku` là **tên tham số hoàn chỉnh**. Không viết `items.0.sku` để giả làm index; với JavaBean property binding, hai cách này không tương đương. Đừng dùng một tên `items` không có index rồi kỳ vọng nó luôn tự tách thành nhiều `LineItem`; với danh sách object, dùng các field indexed rõ ràng.

### HTML form tương ứng

~~~html
<form method="post" action="/orders">
  <input name="items[0].sku" value="PEN">
  <input name="items[0].quantity" type="number" value="2">

  <input name="items[1].sku" value="BOOK">
  <input name="items[1].quantity" type="number" value="1">

  <input name="labels[priority]" value="high">
  <input name="contacts[support].email" type="email"
         value="help@example.com">
  <input name="tags[0]" value="spring">

  <button type="submit">Gửi đơn</button>
</form>
~~~

Trình duyệt URL-encode ký tự đặc biệt khi gửi form. Ví dụ chuỗi `items[0].sku` có thể xuất hiện thành `items%5B0%5D.sku` trong HTTP body. Spring nhận giá trị đã được Servlet container giải mã, nên tên field logic vẫn là `items[0].sku`.

Nếu sử dụng Thymeleaf, sau khi model có form object `orderForm`, có thể viết `th:field="*{items[0].sku}"` trong một `th:object="\${orderForm}"`. Trong trường hợp này Thymeleaf tạo `name` và `id` thích hợp. Lỗi bind cho field tương ứng có thể hiển thị bằng `th:errors="*{items[0].sku}"`. **Các dòng HTML trên là form thuần**, không đòi hỏi Thymeleaf dependency trong ví dụ Maven bên dưới.

## 3. Pipeline Spring MVC: request → object → lỗi

~~~text
HTTP form/query parameters
      |
      | items[0].sku=PEN, labels[priority]=high, ...
      v
Spring MVC handler argument @ModelAttribute("orderForm")
      |
      v
Tạo/lấy instance OrderForm
      |
      v
WebDataBinder cho request hiện tại
  |-- kiểm tra allowedFields
  |-- phân giải property paths: items[0].sku, labels[priority]
  |-- tự mở rộng nested/list trong giới hạn được cấu hình
  |-- ConversionService/PropertyEditor chuyển String -> Integer, ...
  |-- ghi lỗi chuyển kiểu vào BindingResult
      |
      v
@Valid / @Validated (nếu được yêu cầu)
  |-- @NotBlank, @NotNull, @Min, @Valid, ...
  |-- thêm validation errors vào BindingResult
      |
      v
Controller:
  BindingResult.hasErrors() -> xử lý lỗi hoặc tiếp tục nghiệp vụ
~~~

`WebDataBinder` làm việc trên object được đặt tên trong MVC; mặc định Spring hỗ trợ **constructor binding** và **property binding**. Các ví dụ dùng JavaBean mutable với no-args constructor/setters để làm rõ cơ chế property binding và indexed property paths. Với record/immutable DTO, Spring cũng hỗ trợ constructor binding và nhiều dạng tham số có index/key; nhưng **khả năng auto-grow của property binding không phải là khả năng của constructor binding**.

Nếu request có `items[0].quantity=abc` trong khi property Java có kiểu `Integer`, lỗi thuộc **conversion/binding**, không phải `@Min`. Ngược lại, `items[0].quantity=0` chuyển kiểu thành công, nhưng có thể vi phạm `@Min(1)` khi validation chạy. Cả hai có thể được nhìn thấy qua `BindingResult`, song nguyên nhân và mã lỗi khác nhau.

Lưu ý: `@ModelAttribute` không tự tạo một `Map` theo nghĩa giống `@RequestParam Map<String,String>`. Trong bài này, ta đang gán vào **property `labels` của một form object**, còn `@RequestParam Map` thường là tập tham số request phẳng (mục 8).

## 4. Dự án chạy được: Java 17 và Spring Boot 3.5.7

Ví dụ dùng:
- Spring MVC với `@ModelAttribute` nhận form-urlencoded.
- `List<LineItem>` cho dòng hàng; `List<String>` cho tags.
- `Map<String,String>` cho nhãn; `Map<String,Contact>` cho contact theo key.
- `@Valid`, Bean Validation và `BindingResult` cho lỗi ở đúng path.
- `@InitBinder` để bảo vệ property binding, giới hạn chỉ số tự mở rộng.

Cấu trúc:

~~~text
pom.xml
src/main/java/com/example/binding/
  BindingApplication.java
  LineItem.java
  Contact.java
  OrderForm.java
  OrderController.java
src/test/java/com/example/binding/
  OrderControllerTest.java
  DataBinderTest.java
~~~

### 4.1. Cấu hình Maven

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>indexed-binding-demo</artifactId>
    <version>1.0.0</version>

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
</project>
~~~

`spring-boot-starter-web` mang Spring MVC và JSON response support; `spring-boot-starter-validation` bổ sung Jakarta Validation provider; `spring-boot-starter-test` cung cấp JUnit 5 và MockMvc integration. Mẫu không cần database.

### 4.2. Khởi động ứng dụng

~~~java
// src/main/java/com/example/binding/BindingApplication.java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingApplication.class, args);
    }
}
~~~

### 4.3. DTO của phần tử collection

~~~java
// src/main/java/com/example/binding/LineItem.java
package com.example.binding;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class LineItem {
    @NotBlank(message = "Mã hàng không được trống")
    private String sku;

    @NotNull(message = "Số lượng là bắt buộc")
    @Min(value = 1, message = "Số lượng phải từ 1")
    private Integer quantity;

    public LineItem() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

`LineItem` có **public no-args constructor** và property setters/getters. Khi property binding cần phát triển `items[0]` thành một instance, Spring có đường để tạo object và đi vào `sku` hoặc `quantity`. Trong model immutable hoặc constructor-based binding, phải bảo đảm constructor mapping tương ứng thay vì kỳ vọng auto-instantiation bằng setter.

### 4.4. DTO của Map value là object

~~~java
// src/main/java/com/example/binding/Contact.java
package com.example.binding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class Contact {
    @NotBlank(message = "Email không được trống")
    @Email(message = "Email không đúng định dạng")
    private String email;

    public Contact() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Trong `Map<String, Contact>`, tên `contacts[support].email` cần tìm object `Contact` dưới khóa `support` rồi gán property `email`. Để tránh phụ thuộc việc một map key chưa tồn tại có được khởi tạo tự động trong mọi ngữ cảnh hay không, ví dụ **khởi tạo sẵn key `support`** trong `OrderForm`.

### 4.5. Form object có List, Map, nested Map value

~~~java
// src/main/java/com/example/binding/OrderForm.java
package com.example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OrderForm {

    @NotEmpty(message = "Cần ít nhất một dòng hàng")
    private List<@NotNull @Valid LineItem> items = new ArrayList<>();

    @Size(max = 4, message = "Tối đa bốn tag")
    private List<@NotBlank String> tags = new ArrayList<>();

    private Map<String, @NotBlank String> labels = new LinkedHashMap<>();

    private Map<String, @Valid Contact> contacts = new LinkedHashMap<>();

    // Chỉ nhằm minh họa mass assignment; client không có quyền sửa.
    private boolean managerApproved;

    public OrderForm() {
        contacts.put("support", new Contact());
    }

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }

    public Map<String, Contact> getContacts() {
        return contacts;
    }

    public void setContacts(Map<String, Contact> contacts) {
        this.contacts = contacts;
    }

    public boolean isManagerApproved() {
        return managerApproved;
    }

    public void setManagerApproved(boolean managerApproved) {
        this.managerApproved = managerApproved;
    }
}
~~~

Giải thích:

- `List<@NotNull @Valid LineItem>`: các phần tử không được `null` và Bean Validation đi sâu vào `sku`/`quantity` của mỗi dòng.
- `@NotEmpty` trên `items`: danh sách phải có ít nhất một phần tử.
- `List<@NotBlank String> tags`: từng tag không được chỉ là khoảng trắng; `@Size(max=4)` giới hạn số phần tử của collection.
- `Map<String,@NotBlank String> labels`: constraints áp dụng lên **value** của mỗi entry, không phải key.
- `Map<String,@Valid Contact> contacts`: validation cascade vào các `Contact` khi kiểm tra `OrderForm`.
- `contacts.put("support", new Contact())`: tạo sẵn object cho nested path `contacts[support].email`, làm hành vi binding rõ ràng và ổn định.
- `managerApproved` là ví dụ một property **không nên để client thao túng**. Ứng dụng thực nên chuyển quyền phê duyệt sang service/domain logic, tránh để property nhạy cảm trên form DTO.

Điều quan trọng: các generic type arguments mang `@Valid`/constraint sẽ được Jakarta Validation đọc khi chạy validation; còn cơ chế Spring dùng generic type để suy ra loại phần tử cần tạo/chuyển đổi khi **binding** là một bước riêng.

### 4.6. Controller và `@InitBinder` giới hạn field/index

~~~java
// src/main/java/com/example/binding/OrderController.java
package com.example.binding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
public class OrderController {

    @InitBinder("orderForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "items[*].sku",
                "items[*].quantity",
                "tags[*]",
                "labels[priority]",
                "contacts[support].email"
        );
        binder.setAutoGrowNestedPaths(true);
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(
            path = "/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<Map<String, Object>> submit(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", fields));
        }

        return ResponseEntity.ok(Map.of(
                "itemCount", form.getItems().size(),
                "firstSku", form.getItems().get(0).getSku(),
                "tags", form.getTags(),
                "priority", form.getLabels()
                        .getOrDefault("priority", ""),
                "supportEmail", form.getContacts()
                        .get("support").getEmail(),
                "managerApproved", form.isManagerApproved()
        ));
    }
}
~~~

**`@InitBinder("orderForm")`** chỉ tùy biến binder dành cho model attribute có object name `orderForm` trong controller này. Với các object name khác, cần cấu hình phù hợp; trong bài không áp dụng tùy tiện toàn bộ model.

`setAllowedFields(...)` tạo **danh sách cho phép**. Các pattern hỗ trợ dấu `*`:
- `items[*].sku` cho phép `items[0].sku`, `items[1].sku`, v.v.
- `items[*].quantity` cho phép bind quantity của từng dòng.
- `tags[*]` cho phép bind các tag có index.
- `labels[priority]` chỉ cho phép đúng key `priority` trong map labels.
- `contacts[support].email` chỉ cho phép cập nhật email ở entry `support`.

Bất kỳ property binding field nào khác, ví dụ `managerApproved=true` hoặc `contacts[admin].email=x`, sẽ bị loại khỏi các property values được bind. Chúng thường được ghi vào **`BindingResult#getSuppressedFields()`**, không nhất thiết tạo `FieldError`. Trong production, nên cân nhắc giám sát các field bị suppress; không trả thẳng thông tin nhạy cảm hoặc rejected value cho client.

`setAutoGrowCollectionLimit(8)` là **giới hạn auto-grow cho array/list** qua property binding, không phải giới hạn tổng dung lượng HTTP request và không trực tiếp giới hạn số khóa map. Nó ngăn tạo hàng trăm/hàng nghìn vị trí list vì một index tùy ý quá lớn. Hành vi khi request dùng index vượt giới hạn có thể phụ thuộc việc path có được tiếp cận và cách xử lý exception; cần áp dụng kiểm soát input/index ở tầng HTTP/ứng dụng nếu muốn luôn trả 400. **Không được hiểu cấu hình trên bảo đảm request ác ý luôn nhận 400.**

`BindingResult` đặt **ngay sau** tham số `@ModelAttribute`. Thứ tự này cần thiết để Spring gắn kết quả binding/validation với đúng form object. Nếu form có lỗi, ví dụ này trả HTTP 400 cùng danh sách field names; nếu hợp lệ, trả một JSON response tóm tắt, không lưu dữ liệu.

### 4.7. Gửi request thử bằng curl

~~~bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].quantity=2" \
  --data-urlencode "items[1].sku=BOOK" \
  --data-urlencode "items[1].quantity=1" \
  --data-urlencode "labels[priority]=high" \
  --data-urlencode "contacts[support].email=help@example.com" \
  --data-urlencode "tags[0]=spring"
~~~

Response JSON kỳ vọng (thứ tự các keys không được đảm bảo):

~~~json
{
  "itemCount": 2,
  "firstSku": "PEN",
  "tags": ["spring"],
  "priority": "high",
  "supportEmail": "help@example.com",
  "managerApproved": false
}
~~~

Để chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Lệnh `curl` ở trên dành cho shell hỗ trợ dấu `\` để nối dòng (Linux/macOS hoặc Git Bash). Nếu dùng PowerShell, có thể gửi một dòng `curl.exe` hoặc dùng cú pháp nối dòng của PowerShell; không sao chép dấu `\` nối dòng Unix vào PowerShell 5.1 nguyên xi.

## 5. Kiểm thử indexed binding, map binding và chặn mass assignment

### 5.1. MockMvc integration test

~~~java
// src/test/java/com/example/binding/OrderControllerTest.java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsListMapAndNestedMapObject() throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "2")
                .param("items[1].sku", "BOOK")
                .param("items[1].quantity", "1")
                .param("labels[priority]", "high")
                .param("contacts[support].email", "help@example.com")
                .param("tags[0]", "spring")
                .param("managerApproved", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemCount").value(2))
            .andExpect(jsonPath("$.firstSku").value("PEN"))
            .andExpect(jsonPath("$.priority").value("high"))
            .andExpect(jsonPath("$.supportEmail")
                    .value("help@example.com"))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.managerApproved").value(false));
    }

    @Test
    void validationErrorsRetainIndexedPaths() throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", " ")
                .param("items[0].quantity", "0")
                .param("labels[priority]", "high")
                .param("contacts[support].email", "bad-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].sku")))
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].quantity")));
    }

    @Test
    void conversionFailureRetainsTheOriginalFieldPath()
            throws Exception {
        mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("items[0].sku", "PEN")
                .param("items[0].quantity", "not-an-integer")
                .param("contacts[support].email", "help@example.com"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors",
                    hasItem("items[0].quantity")));
    }
}
~~~

Test đầu tiên chứng minh list có thể nhận hai dòng liên tiếp, map chuỗi nhận key `priority`, map object truy cập key `support` rồi bind email và tag được gán tại index 0. Quan trọng hơn, client cố gửi `managerApproved=true` nhưng response vẫn `false` vì field không có trong `allowedFields`. Đó là kiểm thử **mass assignment protection**, không phải validation: property không được gán.

Test thứ hai kiểm tra lỗi `@NotBlank` và `@Min(1)` tại đúng đường dẫn `items[0].sku` và `items[0].quantity`. Test thứ ba gửi chuỗi không chuyển được thành `Integer`, chứng minh binding error cũng chỉ ra đúng indexed path. Các test không cố định nội dung thông điệp lỗi vì message locale có thể khác.

### 5.2. Test trực tiếp với `DataBinder` để xem suppressed fields

~~~java
// src/test/java/com/example/binding/DataBinderTest.java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class DataBinderTest {

    @Test
    void bindsAllowedIndexedPathsAndSuppressesForbiddenField() {
        OrderForm form = new OrderForm();
        DataBinder binder = new DataBinder(form, "orderForm");

        binder.setAllowedFields(
                "items[*].sku",
                "items[*].quantity"
        );
        binder.setAutoGrowCollectionLimit(8);

        binder.bind(new MutablePropertyValues(Map.of(
                "items[0].sku", "PEN",
                "items[0].quantity", "2",
                "managerApproved", "true"
        )));

        assertEquals(1, form.getItems().size());
        assertEquals("PEN", form.getItems().get(0).getSku());
        assertEquals(2, form.getItems().get(0).getQuantity());
        assertFalse(form.isManagerApproved());

        assertArrayEquals(
                new String[]{"managerApproved"},
                binder.getBindingResult().getSuppressedFields()
        );
    }
}
~~~

Dùng `DataBinder` trực tiếp rất hữu ích khi không cần HTTP hay controller. `MutablePropertyValues` đưa tên/value giống request parameters vào binder; ta kiểm tra object sau binding và danh sách field bị từ chối. Test này **chỉ kiểm tra binding**, không tự chạy Bean Validation, vì không gọi `binder.validate()` hay thiết lập validator trên binder.

Chạy test:

~~~bash
mvn test
~~~

Với mã nguồn ở các mục trên, kỳ vọng **4 JUnit tests PASS**: 3 MockMvc và 1 DataBinder trực tiếp. Đây là kết quả kỳ vọng theo semantics framework; số dòng log và thứ tự tests tùy môi trường Maven/Surefire, không ghi cứng stdout của Maven.

## 6. BindingResult: lỗi ở index/key nào?

### 6.1. Binding error và validation error khác nhau

Ví dụ hai request sau đều có thể làm `BindingResult#hasErrors()` bằng `true`, nhưng lý do khác:

~~~text
items[0].quantity=abc
   -> String "abc" không chuyển được thành Integer
   -> binding/conversion error, code thường là typeMismatch

items[0].quantity=0
   -> chuyển được thành Integer 0
   -> vi phạm @Min(1) trong validation
   -> validation error, code thường là Min
~~~

Spring lưu field path đầy đủ trong `FieldError#getField()`, ví dụ `items[0].quantity`. Với Map và nested value, `FieldError#getField()` có thể mang path dạng `contacts[support].email` hoặc path biểu diễn container element theo Bean Validation provider. Nếu xử lý đường dẫn của `ConstraintViolation` thuần, hãy đọc `Path.Node` (kind/index/key) khi cần độ chính xác, tránh đoán từ chuỗi path.

Nếu cần mã lỗi, có thể đọc:

~~~java
// Đoạn minh họa bên trong handler đã có BindingResult result.
for (var error : result.getFieldErrors()) {
    String field = error.getField();       // Ví dụ "items[0].quantity"
    String code = error.getCode();         // Ví dụ "typeMismatch" hoặc "Min"
    String message = error.getDefaultMessage();

    // Tùy kiến trúc, chuyển field/code/message sang response an toàn.
}
~~~

Không trả nguyên `FieldError#getRejectedValue()` về client, vì một số form có thể chứa thông tin nhạy cảm. Trong ví dụ controller, response chỉ liệt kê **tên field** có lỗi.

### 6.2. `@Valid` trên List/Map và các element constraints

Trong `OrderForm`, các ràng buộc hoạt động ở ba mức:

~~~java
@NotEmpty
private List<@NotNull @Valid LineItem> items;

@Size(max = 4)
private List<@NotBlank String> tags;

private Map<String, @Valid Contact> contacts;
~~~

Đoạn trên chỉ là **các dòng khai báo rút gọn**; mã chạy được đầy đủ nằm ở mục 4.

- `@NotEmpty` kiểm tra chính collection `items` không rỗng.
- `@NotNull` trên type argument kiểm tra từng phần tử không null.
- `@Valid` trên type argument cascade vào `LineItem.sku` và `LineItem.quantity`.
- `@NotBlank` trên `List<String>` kiểm tra từng tag (không phải bản thân list).
- `@Valid` trên `Map` value cascade vào `Contact.email`.

Bộ trích xuất phần tử container (*value extractors*) cho `List`/`Map` được Jakarta Validation provider thông thường cung cấp sẵn. Với container tự định nghĩa, cần `ValueExtractor` tương ứng để các type-argument constraints hoạt động.

**Binding không đồng nghĩa validation:** có thể bind `items[0].sku=" "` rất thành công; chỉ sau khi `@Valid` chạy mới phát hiện `@NotBlank`. Ngược lại, binding lỗi kiểu không cần chờ `@Min` mới biết input sai.

### 6.3. Nested List nhiều mức

Cùng quy tắc có thể mở rộng sang list lồng nhau:

~~~text
groups[0].members[0].name = An
groups[0].members[1].name = Bình
groups[1].members[0].name = Chi
~~~

Giả sử form có `List<GroupForm> groups` và mỗi `GroupForm` có `List<MemberForm> members`. Đường dẫn gồm:
- `groups[0]`: chọn phần tử nhóm index 0.
- `members[1]`: chọn thành viên index 1 của nhóm đó.
- `name`: property của thành viên được chọn.

Muốn bind được, cả các property trung gian đều phải có cấu trúc và cách khởi tạo tương ứng. Việc dùng nhiều tầng index cũng làm rủi ro auto-grow cao hơn, vì thế cần kiểm soát độ sâu, số lượng phần tử và dữ liệu gửi lên.

## 7. Auto-grow: thuận tiện nhưng có giới hạn

### 7.1. Vì sao cần auto-grow?

Một form mới có:

~~~java
private List<LineItem> items = new ArrayList<>();
~~~

Ban đầu list rỗng. Khi nhận `items[0].sku=PEN`, property binder có thể **mở rộng list** và tạo `LineItem` ở index 0 bằng no-args constructor, sau đó gọi setter `setSku("PEN")`. Nếu path chứa object con `null` và có cách tạo default object thích hợp, `setAutoGrowNestedPaths(true)` cho phép đi sâu vào property đó.

Mặc định `DataBinder` có auto-grow nested paths bật và giới hạn collection auto-grow mặc định **256** (theo Spring Framework 6.x). `setAutoGrowCollectionLimit(int)` đặt lại giới hạn; bài này chọn **8** để thể hiện cách giảm rủi ro với form nhỏ.

### 7.2. Không gửi index thưa tùy tiện

~~~text
items[0].sku=PEN
items[7].sku=BOOK
~~~

Spring có thể phải tạo/phát triển các slot trung gian `1..6`. Tùy kiểu phần tử và cách binder hoạt động, chúng có thể trở thành object mặc định hoặc `null`; đây không phải cách biểu diễn “hai dòng hàng” đáng tin cậy. Nếu form chỉ còn hai dòng sau khi người dùng xóa các hàng, nên **đánh lại chỉ số liên tiếp**:

~~~text
items[0].sku=PEN
items[1].sku=BOOK
~~~

Không giả định `items[-1]`, `items[9999999]` hoặc một index gửi sai sẽ tự động trở thành `BindingResult`/HTTP 400. Spring có thể ném exception khi property không thể truy cập hoặc vượt giới hạn. Nếu API cần trả lỗi ổn định, hãy kiểm soát số lượng/index trước hoặc trong lớp xử lý request phù hợp, đồng thời giới hạn kích thước body ở server/proxy.

### 7.3. Giới hạn auto-grow không phải quota cho Map

`setAutoGrowCollectionLimit` dành cho array/collection auto-growing khi **setter/property binding**. Nó không trực tiếp chặn một client gửi hàng nghìn key `labels[someKey]`. Với Map:

- Chỉ cho phép những key dự kiến, ví dụ `labels[priority]`, nếu nghiệp vụ có tập key cố định.
- Với key động thực sự, validate whitelist/định dạng/độ dài key và giới hạn **số entry** sau binding hoặc ở lớp input.
- Không bind trực tiếp vào một map domain nội bộ có thể chứa property/permission nhạy cảm.
- Dùng quy tắc giới hạn request size, số parameter và độ sâu object graph bên ngoài `DataBinder` khi cần.

**Không tăng `autoGrowCollectionLimit` lên giá trị rất lớn** chỉ vì có form động. Chọn limit theo số item tối đa hợp pháp, và ưu tiên thiết kế API khác nếu cấu trúc form trở nên quá lớn.

### 7.4. Constructor binding là cơ chế khác

Spring hỗ trợ constructor binding cho object immutable, bao gồm các tham số dạng `List`, `Map` và array theo indexed keys hoặc giá trị có thể convert. Nhưng Javadoc `setAutoGrowNestedPaths`/`setAutoGrowCollectionLimit` nêu rõ chúng áp dụng cho **property binding bằng `bind(PropertyValues)`**, không áp dụng cho việc constructor binding bằng `construct(ValueResolver)`.

Vì thế, nếu đổi `OrderForm` mutable sang record:

~~~java
public record OrderInput(
        List<LineItemInput> items,
        Map<String, String> labels
) {}

public record LineItemInput(String sku, Integer quantity) {}
~~~

hãy kiểm tra constructor binding riêng cho các field names tương ứng, conversion và validation thay vì kỳ vọng hành vi tạo `LineItem` thông qua JavaBean setters vẫn giữ nguyên. Record trên là **phương án model thay thế**, không thuộc dự án runnable ở mục 4.

## 8. Phân biệt `@ModelAttribute`, `@RequestParam` và `@RequestBody`

### 8.1. `@ModelAttribute` cho HTML form

~~~java
@PostMapping("/orders")
public void submit(@ModelAttribute("orderForm") OrderForm form) {
    // form.getItems(), form.getLabels(), ...
}
~~~

Đây là handler minh họa, chưa xử lý validation/response. Bằng cách sử dụng `@ModelAttribute`, Spring MVC bind request parameters (query/form, cùng các nguồn giá trị được hỗ trợ) vào object graph. Đây chính là ngữ cảnh của `items[0].sku` và `labels[priority]`.

### 8.2. `@RequestParam Map` lấy tham số phẳng

~~~java
@PostMapping("/raw")
public void raw(@RequestParam Map<String, String> params) {
    String sku = params.get("items[0].sku");
    // key là tên tham số thô, không phải List<LineItem>.
}
~~~

Với `@RequestParam Map<String,String>`, key thường là **tên tham số**, còn value là chuỗi từ request. Phương thức trên không tự tạo `OrderForm.items`. Nếu một key có nhiều giá trị, cân nhắc `MultiValueMap<String,String>`, vì `Map<String,String>` chỉ thể hiện một giá trị cho mỗi key.

### 8.3. `@RequestBody` cho JSON

Với JSON, cấu trúc đối tượng và mảng được biểu diễn bằng JSON thật:

~~~json
{
  "items": [
    {"sku": "PEN", "quantity": 2},
    {"sku": "BOOK", "quantity": 1}
  ],
  "labels": {"priority": "high"},
  "contacts": {
    "support": {"email": "help@example.com"}
  },
  "tags": ["spring"]
}
~~~

Controller:

~~~java
@PostMapping("/orders-json")
public void submitJson(@Valid @RequestBody OrderForm body) {
    // Jackson chuyển JSON -> Java DTO; @Valid kiểm tra DTO.
}
~~~

Đây là đoạn minh họa, không có method này trong source runnable ở mục 4. Trong pipeline JSON, **Jackson** deserialize mảng và map từ cấu trúc JSON; nó không dùng chuỗi field name như `items[0].sku` làm chỉ số JavaBean property theo cùng đường xử lý form. `WebDataBinder#setAllowedFields` ở mục 4 **không phải cơ chế whitelist JSON deserialization**. Với JSON, phải dùng DTO dành riêng cho input và chính sách Jackson/validation phù hợp. Không tưởng rằng một `@InitBinder` bảo vệ toàn bộ endpoint `@RequestBody` theo cách giống form binding.

### 8.4. List/Map phẳng và các dạng form đơn giản

Với nhiều giá trị cùng tên, ví dụ:

~~~text
tag=java&tag=spring
~~~

Spring có thể resolve trực tiếp thành `@RequestParam List<String> tag`; điều này khác với property path `tags[0]` trong `@ModelAttribute`. Đừng trộn hai cách một cách ngẫu nhiên; chọn một hợp đồng request rõ ràng và test đúng payload mà trình duyệt/client gửi.

## 9. Bảo mật: từ mass assignment đến dữ liệu quá lớn

### 9.1. Over-posting / mass assignment

Nếu form object có setter `setManagerApproved(boolean)`, một client có thể tự ý gửi:

~~~text
managerApproved=true
~~~

Khi property binding không giới hạn, Spring có thể gọi setter tương ứng. Trong ví dụ, `@InitBinder` chỉ cho phép `items[*].sku`, `items[*].quantity`, `tags[*]`, `labels[priority]` và `contacts[support].email`. Vì thế field `managerApproved` bị suppress, dù class vẫn có setter.

**Thiết kế an toàn hơn:** không đặt thuộc tính nhạy cảm như role, trạng thái thanh toán, xác nhận quản lý, ownerId lên web input DTO có setter. Domain entity và web form có trách nhiệm khác nhau. Whitelist binding là phòng tuyến thêm, không nên là lý do để tái dùng bừa domain entity làm form object.

### 9.2. `allowedFields` tốt hơn chỉ blacklist

~~~java
// Minh họa nguyên tắc trong @InitBinder:
binder.setAllowedFields(
        "items[*].sku",
        "items[*].quantity",
        "labels[priority]"
);
~~~

Pattern `*` không phải regular expression đầy đủ; Spring hỗ trợ pattern wildcard cho tên property. Whitelist phải cân nhắc cả nested paths. Nếu dùng `items*` rộng quá mức, có thể vô tình cho phép những property không mong muốn của item. Ưu tiên các path cụ thể và nhóm field được kiểm soát.

`setDisallowedFields(...)` có thể chặn một số field, nhưng blacklist dễ bỏ sót field mới khi DTO phát triển. Với input không đáng tin cậy, whitelist và dedicated DTO thường dễ kiểm soát hơn.

### 9.3. Dấu ngoặc không phải bằng chứng quyền truy cập

Tên `contacts[admin].email` chỉ nói client muốn chọn key `admin`; nó **không chứng minh** người dùng có quyền sửa contact đó. Nếu xử lý key động, server phải kiểm tra quyền sở hữu/quyền thao tác của từng entry theo dữ liệu đã xác thực. Không dùng tên map key do client gửi làm cơ sở authorization.

Tương tự, `items[0].id` có thể xuất hiện trong form chỉnh sửa thực thể. Không nên chỉ đọc ID từ input rồi update thẳng: cần truy vấn bản ghi theo tenant/owner, xác minh quyền, và mapping rõ field nào được phép thay đổi.

### 9.4. Giới hạn cả cấu trúc lẫn giá trị

Ngoài `@Size(max=4)` trên `tags`, cần cân nhắc:
- Số phần tử list/map tối đa (ở cả HTTP layer và model/business validation).
- Index tối đa và tổng độ sâu nested paths.
- Độ dài string key/value và kích thước request body.
- Số parameters trên request do Servlet container chấp nhận.
- Rate limiting nếu endpoint có thể bị lạm dụng.

Constraint `@Size` chạy **sau binding**, vì vậy không đủ thay thế giới hạn để bảo vệ quá trình **tạo cấu trúc dữ liệu**. Đừng trông chờ validation hậu kỳ ngăn mọi dạng resource exhaustion trong binder.

## 10. Những tình huống dễ sai và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `items[0].sku` không được gán | Target không có property/constructor/setter phù hợp, hoặc bị whitelist chặn | Xem DTO, `@InitBinder`, `getSuppressedFields()` |
| `items[2]` lỗi khi list rỗng | Auto-grow không khả dụng hoặc chỉ số vượt giới hạn | Sắp xếp index liên tục, cấu hình limit hợp lý, kiểm tra mode binding |
| `contacts[support].email` không truy cập được | Map entry `support` chưa có object, hoặc chưa có cách tạo object | Khởi tạo key/value tương ứng hoặc xây binding strategy rõ ràng |
| `items[0].quantity=abc` gây lỗi | `String` không chuyển được sang `Integer` | Kiểm tra `BindingResult`, error code `typeMismatch` |
| `items[0].quantity=0` gây lỗi | Chuyển kiểu thành công nhưng vi phạm `@Min(1)` | Xem validation messages và rules |
| `items[0].sku` được bind nhưng không báo trống | Chưa chạy `@Valid` hoặc chưa cascade phần tử | Dùng `@Valid @ModelAttribute` và `List<@Valid Item>` |
| `labels[priority]` bị bỏ qua | `allowedFields` thiếu đúng path/key | Kiểm tra pattern, chữ hoa/thường và suppressed fields |
| Client gửi `managerApproved=true` và giá trị đổi | Property nhạy cảm bị expose qua binding | Dùng DTO riêng, whitelist, không cho client quản lý trạng thái |
| Tên field của form không khớp lỗi | Dùng `items.0.sku` hoặc rename index sai | Kiểm tra literal `name` và `FieldError#getField()` |
| JSON có key `items[0].sku` nhưng list không được tạo | JSON dùng Jackson, không phải indexed property-name binding của form | Gửi JSON array/object đúng cấu trúc |
| Mất dữ liệu sau khi xóa một dòng động | Các index phía client để lại lỗ hổng | Đánh lại index liên tục trước submit |
| Request với index quá lớn gây exception | Giới hạn growth/khả năng truy cập property bị vượt | Reject input sớm, cấu hình size/index limit, test boundary |

### Map key phức tạp

Map key như `billing.eu` hoặc `special[guest]` có thể xung đột trực giác về cú pháp dấu chấm/ngoặc của property path. Nếu ứng dụng cho phép key tùy ý, cần kiểm tra parser/escaping của **phiên bản Spring đang chạy** và có test round-trip request-name → Map key. Đối với form thông thường, ưu tiên key đơn giản, ổn định, chỉ chứa ký tự chữ/số/gạch dưới để dễ debug và giảm rủi ro injection qua property path.

### Set và collection không có index ổn định

`Set<T>` không thể hiện vị trí phần tử ổn định như `List<T>`. Đối với form có hàng lặp, `List<LineItem>` thường phù hợp hơn vì index `[0]`, `[1]` phản ánh thứ tự nhập liệu. Nếu miền nghiệp vụ cần `Set` để chống trùng, có thể bind vào List input DTO trước, validate, sau đó chuyển sang Set tại service layer và xử lý phát hiện phần tử trùng một cách tường minh.

### Array và giới hạn index

`String[]` có thể sử dụng `codes[0]`, `codes[1]` qua bean property binding khi binder có thể mở rộng mảng trong giới hạn. Array không thuận tiện bằng `List` cho form có nhiều dòng thêm/xóa. Với cùng dữ liệu, thử cả index 0 và index lớn để bảo đảm behavior khớp với configured growth limit.

## 11. Checklist ứng dụng thực tế

1. Thiết kế DTO web riêng: properties và setters chỉ dành cho input hợp lệ.
2. Dùng tên field đúng cấu trúc: `items[0].sku`, `tags[1]`, `labels[priority]`, `contacts[support].email`.
3. Với List bean, chuẩn bị generic type, no-args constructor và property setters phù hợp; dùng index liên tục bắt đầu từ 0.
4. Với Map chứa object, xác định rõ key/value nào tồn tại và chiến lược tạo nested object, không kỳ vọng mọi map key tùy ý được tạo tự động.
5. Cấu hình `@InitBinder`/`allowedFields` và giới hạn auto-grow theo kích thước hợp pháp của form. Không dùng auto-grow limit làm hàng rào duy nhất.
6. Gắn `@Valid`/`@Validated` và các constraint đúng mức: collection, element, nested object; đặt `BindingResult` ngay sau model attribute.
7. Phân biệt error code của conversion như `typeMismatch` với lỗi constraint như `NotBlank` và `Min`; bảo toàn indexed field path trong response.
8. Viết MockMvc tests cho list, map, nested map, nhiều index, type mismatch, blank input, và over-posting.
9. Nếu API nhận JSON, dùng `@RequestBody` với JSON array/object thực sự và cơ chế bảo vệ deserialization riêng.
10. Giới hạn input, kiểm tra authorization cho Map keys/object IDs và không binding trực tiếp vào domain entity.

## Tài liệu tham khảo

- Spring Framework 6.2 – MVC Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html
- Spring Framework 6.2 – `@ModelAttribute` method arguments, indexed constructor binding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 – Core Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html
- Spring Framework 6.2 – DataBinder Javadoc (`setAllowedFields`, `setAutoGrowCollectionLimit`): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 – `BindingResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Boot 3.5 – Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
