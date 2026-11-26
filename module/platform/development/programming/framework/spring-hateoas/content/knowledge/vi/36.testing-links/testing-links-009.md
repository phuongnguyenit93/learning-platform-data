# JSON path cho HATEOAS

Khi kiểm thử REST API dùng Spring HATEOAS, response JSON chứa cả dữ liệu nghiệp vụ và cấu trúc hypermedia. Ngoài các field như `id`, `status` hoặc `total`, client còn phụ thuộc vào `_links`, `_embedded`, relation, `href`, URI template và metadata phân trang. Một response có thể trả HTTP `200 OK` nhưng vẫn làm client hỏng nếu link `self` biến mất, relation collection đổi tên hoặc một link chuyển từ object sang array.

JsonPath giúp kiểm tra trực tiếp các phần của JSON mà không phải so sánh toàn bộ chuỗi response. Trong Spring MVC Test, `MockMvc` cung cấp `jsonPath(...)` để xác nhận giá trị, kiểu dữ liệu, sự tồn tại và cấu trúc của một node. Kết hợp JsonPath với assertion về status và media type, test có thể bảo vệ hợp đồng HAL/HATEOAS theo cách dễ đọc và ít phụ thuộc vào khoảng trắng hoặc thứ tự property.

## JSONPath và cấu trúc HAL

HAL biểu diễn link trong `_links` và tài nguyên được nhúng trong `_embedded`. Một response collection có thể có dạng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-1001",
        "status": "OPEN",
        "_links": {
          "self": { "href": "/api/orders/ORD-1001" }
        }
      },
      {
        "id": "ORD-1002",
        "status": "PAID",
        "_links": {
          "self": { "href": "/api/orders/ORD-1002" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders" },
    "next": { "href": "/api/orders?page=1&size=2" }
  },
  "page": {
    "size": 2,
    "totalElements": 10,
    "totalPages": 5,
    "number": 0
  }
}
```

JsonPath luôn bắt đầu từ `$`, đại diện cho root JSON. Dấu chấm đi qua property, dấu ngoặc vuông truy cập index hoặc key có ký tự đặc biệt:

| Mục tiêu | JsonPath |
|---|---|
| ID của response đơn | `$.id` |
| Link self của collection | `$._links.self.href` |
| Link next | `$._links.next.href` |
| Collection được nhúng | `$._embedded.orders` |
| ID phần tử đầu tiên | `$._embedded.orders[0].id` |
| Link self của phần tử thứ hai | `$._embedded.orders[1]._links.self.href` |
| Tổng số trang | `$.page.totalPages` |
| Số trang hiện tại | `$.page.number` |

Index mảng bắt đầu từ `0`. Khi relation hoặc property có dấu gạch nối, dấu hai chấm, dấu chấm hoặc dấu `/`, nên dùng bracket notation với tên key đặt trong dấu nháy, ví dụ `$._links['acme:approval'].href`.

## Dùng jsonPath trong MockMvc

Spring MVC Test tích hợp JsonPath qua `MockMvcResultMatchers.jsonPath(...)`. Test thường kiểm tra bốn phần: HTTP status, `Content-Type`, field dữ liệu và hypermedia link.

Ví dụ endpoint trả `EntityModel<OrderResponse>`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderResponse> one(@PathVariable UUID id) {
        return assembler.toModel(service.findRequired(id));
    }
}
```

Test dùng `Accept: application/hal+json` và xác nhận response thực tế:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHalJsonTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderWithSelfAndCustomerLinks() throws Exception {
        UUID orderId = UUID.fromString("c4126a60-0d15-4df3-9d9d-5bb9b88a2a10");

        mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(orderId.toString()))
            .andExpect(jsonPath("$.status").value("OPEN"))
            .andExpect(jsonPath("$._links.self.href")
                    .value(endsWith("/api/orders/" + orderId)))
            .andExpect(jsonPath("$._links.customer.href").exists());
    }
}
```

`contentTypeCompatibleWith(...)` kiểm tra media type tương thích mà không buộc test phụ thuộc vào tham số charset. `endsWith(...)` xác nhận phần path cần thiết nhưng không khóa test vào hostname, scheme hoặc port của môi trường.

Các đoạn code tiếp theo là phần assertion có thể ghép vào test class tương tự. Mỗi ví dụ giả định `mockMvc` đã được inject và endpoint trả HAL JSON.

## Kiểm tra giá trị, kiểu và sự tồn tại

`jsonPath(expression).value(expected)` kiểm tra giá trị tại path. Có thể dùng giá trị trực tiếp hoặc Hamcrest matcher:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.status").value("OPEN"))
    .andExpect(jsonPath("$.total").value(1250000))
    .andExpect(jsonPath("$._links.self.href")
            .value(endsWith("/orders/ORD-1001")));
```

Có thể kiểm tra kiểu node để bảo vệ cấu trúc response:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links").isMap())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._links.self.href").isString())
    .andExpect(jsonPath("$.page.totalPages").isNumber());
```

Các matcher kiểu thường dùng:

| Matcher | Điều kiện |
|---|---|
| `isString()` | Node là chuỗi |
| `isNumber()` | Node là số |
| `isBoolean()` | Node là boolean |
| `isArray()` | Node là JSON array |
| `isMap()` | Node là JSON object |
| `isEmpty()` | Node là collection, map hoặc chuỗi rỗng |
| `isNotEmpty()` | Node có nội dung |
| `exists()` | Path phân giải được thành giá trị khác `null` |
| `doesNotExist()` | Path không có giá trị khác `null` |

`exists()` và `doesNotExist()` không phân biệt rõ property bị thiếu với property tồn tại nhưng có giá trị `null`. Khi hợp đồng cần phân biệt hai trường hợp này, dùng `hasJsonPath()` và `doesNotHaveJsonPath()`.

Ví dụ property có thể tồn tại với giá trị null:

```java
import static org.hamcrest.Matchers.nullValue;

mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.note").hasJsonPath())
    .andExpect(jsonPath("$.note").value(nullValue()));
```

Nếu serializer bỏ hẳn property `note`, dùng:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.note").doesNotHaveJsonPath());
```

Vì vậy, `hasJsonPath()` trả lời “property có xuất hiện trong JSON không?”, còn `exists()` trả lời “path có giá trị khác null không?”. Hãy chọn matcher theo đúng hợp đồng về null inclusion của Jackson.

## Kiểm tra link và relation trong _links

Các relation chuẩn như `self`, `next`, `prev`, `first`, `last` thường truy cập bằng dot notation:

```java
mockMvc.perform(get("/api/orders?page=1&size=2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.first.href").exists())
    .andExpect(jsonPath("$._links.prev.href").exists())
    .andExpect(jsonPath("$._links.next.href").exists())
    .andExpect(jsonPath("$._links.last.href").exists());
```

Đoạn test giả định server công bố đủ các relation tại trang đang kiểm tra. Ở trang đầu, `prev` thường không tồn tại; ở trang cuối, `next` thường không tồn tại. Test phải khớp với vị trí trang và chính sách công bố link của API.

Với custom relation là URI đầy đủ hoặc CURIE, dùng bracket notation:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['acme:approval'].href").exists())
    .andExpect(jsonPath("$._links['https://api.example.com/rels/invoice'].href")
            .exists());
```

Dot notation không phù hợp với key chứa dấu `:`, `/` hoặc `.` vì JsonPath có thể diễn giải các ký tự đó như cú pháp truy cập property. Bracket notation giúp coi toàn bộ relation là một key duy nhất.

Nếu API không cấu hình CURIE, relation có thể được serialize bằng URI đầy đủ. Nếu API bật CURIE, key có thể là `acme:approval`. Test cần khớp chính sách serialization mà client được công bố sử dụng.

## Kiểm tra _embedded và collection

`_embedded` chứa tài nguyên được nhúng theo relation. Với collection, nên kiểm tra node là array, số phần tử và nội dung của từng phần tử:

```java
mockMvc.perform(get("/api/orders?page=0&size=2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(2))
    .andExpect(jsonPath("$._embedded.orders[0].id").value("ORD-1001"))
    .andExpect(jsonPath("$._embedded.orders[1].id").value("ORD-1002"))
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

JsonPath hỗ trợ wildcard `[*]` để lấy tất cả phần tử trong mảng:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[*].id").isNotEmpty())
    .andExpect(jsonPath("$._embedded.orders[*]._links.self.href").isNotEmpty());
```

Wildcard hữu ích khi không cần phụ thuộc vào vị trí phần tử. Nếu thứ tự collection là một phần của hợp đồng, hãy kiểm tra index cụ thể hoặc dùng matcher so sánh list theo thứ tự.

### Lọc phần tử bằng predicate

Filter expression giúp tìm phần tử theo field. Ví dụ kiểm tra collection có ít nhất một đơn hàng đang mở:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[?(@.status == 'OPEN')]")
            .isNotEmpty());
```

Có thể kiểm tra item theo ID:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders[?(@.id == 'ORD-1001')]")
            .isNotEmpty());
```

Predicate trong ví dụ dùng cú pháp Jayway JsonPath: `?()` mở filter và `@` đại diện cho phần tử hiện tại. Chuỗi so sánh đặt trong dấu nháy đơn. Với dữ liệu số, boolean hoặc nested field, dùng literal và path phù hợp với kiểu JSON thực tế.

### Collection rỗng

Nếu hợp đồng quy định relation embedded vẫn xuất hiện dưới dạng mảng rỗng, kiểm tra cả kiểu và số phần tử:

```java
mockMvc.perform(get("/api/orders?status=UNKNOWN")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(0));
```

Tùy cách tạo `CollectionModel`, fallback type và HAL configuration, một collection rỗng có thể không tạo `_embedded.orders`. Nếu hợp đồng cho phép lược relation khi không có phần tử, hãy test hành vi đó bằng `doesNotHaveJsonPath()` thay vì mặc định coi mọi collection rỗng phải là mảng. Điều quan trọng là giữ một quy tắc ổn định và mô tả nó cho client.

## Kiểm tra pagination metadata và link

`PagedModel` thường có object `page` với các trường `size`, `totalElements`, `totalPages` và `number`. Có thể kiểm tra metadata cùng link điều hướng:

```java
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/api/orders?page=1&size=2")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(2))
    .andExpect(jsonPath("$.page.totalElements").value(10))
    .andExpect(jsonPath("$.page.totalPages").value(5))
    .andExpect(jsonPath("$.page.number").value(1))
    .andExpect(jsonPath("$._links.first.href").value(containsString("page=0")))
    .andExpect(jsonPath("$._links.prev.href").value(containsString("page=0")))
    .andExpect(jsonPath("$._links.next.href").value(containsString("page=2")));
```

Trong test thực tế, nên import `containsString` từ `org.hamcrest.Matchers`. Tránh khóa test vào hostname hoặc port; kiểm tra query parameter hoặc path có ý nghĩa với hợp đồng. Nếu API giữ filter và sort trong các link trang, hãy kiểm tra chúng không bị mất:

```java
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/api/orders?page=1&size=2&status=OPEN&sort=createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.next.href")
            .value(allOf(
                    containsString("status=OPEN"),
                    containsString("sort=createdAt"),
                    containsString("page=2")
            )));
```

`allOf(...)` kết hợp nhiều matcher trên cùng một giá trị. Nếu query parameter được URL encode, hãy kiểm tra giá trị đã encode tương ứng hoặc parse URI của `href` trong một assertion riêng.

## Link đơn và link nhiều phần tử

HAL mặc định thường serialize một link trong relation thành object:

```json
{
  "_links": {
    "self": { "href": "/api/orders/ORD-1001" }
  }
}
```

Nếu một relation có nhiều link, giá trị của relation là array:

```json
{
  "_links": {
    "item": [
      { "href": "/api/cart/items/1" },
      { "href": "/api/cart/items/2" }
    ]
  }
}
```

Assertion tương ứng:

```java
mockMvc.perform(get("/api/cart")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    // Một link, HAL rendering mặc định.
    .andExpect(jsonPath("$._links.self.href").exists())
    // Nhiều link cùng relation.
    .andExpect(jsonPath("$._links.item").isArray())
    .andExpect(jsonPath("$._links.item[0].href").exists())
    .andExpect(jsonPath("$._links.item[1].href").exists());
```

Ứng dụng có thể cấu hình `HalConfiguration` để render cả link đơn dưới dạng array. Khi đó path phải là `$._links.self[0].href`. Đừng dùng một JsonPath assertion cố định mà không xét cấu hình HAL thực tế; thay đổi từ object sang array là thay đổi cấu trúc JSON mà client có thể cảm nhận.

## Kiểm tra URI template

Link template có thuộc tính `templated: true` và `href` chứa biến theo URI Template:

```json
{
  "_links": {
    "search": {
      "href": "/api/orders/search{?status,page,size}",
      "templated": true
    }
  }
}
```

Test xác nhận cả flag lẫn tên biến được công bố:

```java
import static org.hamcrest.Matchers.containsString;

mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
            .value(containsString("{?status,page,size}")));
```

Nếu API thay đổi thứ tự biến trong template nhưng giữ nguyên tập biến và ngữ nghĩa, test có thể chỉ xác nhận các biến bắt buộc thay vì so sánh cả chuỗi. Nếu thứ tự hoặc biểu thức template là một phần hợp đồng client, hãy kiểm tra chính xác hơn.

## Kiểm tra HAL-FORMS bằng JsonPath

HAL-FORMS bổ sung `_templates` để mô tả thao tác và property mà client có thể gửi. Ví dụ:

```json
{
  "_links": {
    "self": { "href": "/api/employees/42" }
  },
  "_templates": {
    "default": {
      "method": "put",
      "properties": [
        { "name": "email", "required": true, "type": "text" }
      ]
    }
  }
}
```

Kiểm tra template và property bằng path lồng nhau hoặc filter:

```java
mockMvc.perform(get("/api/employees/42")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._templates.default.method").value("put"))
    .andExpect(jsonPath("$._templates.default.properties[0].name").value("email"))
    .andExpect(jsonPath("$._templates.default.properties[?(@.name == 'email')]")
            .isNotEmpty());
```

Chỉ kiểm tra `_templates` khi client yêu cầu HAL-FORMS và controller/assembler thực sự công bố affordance. HAL JSON thông thường không bắt buộc có `_templates`.

## Kiểm tra link tùy chọn và field không được công bố

Không phải link nào cũng xuất hiện trong mọi trạng thái. Ví dụ đơn hàng chỉ có relation `cancel` khi còn ở trạng thái `OPEN`. Có thể kiểm tra cả hai trạng thái:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel.href").exists());

mockMvc.perform(get("/api/orders/ORD-1002")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.cancel").doesNotHaveJsonPath());
```

Tương tự, JsonPath có thể bảo vệ response khỏi việc vô tình công bố field nội bộ:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.internalCost").doesNotHaveJsonPath())
    .andExpect(jsonPath("$.databaseVersion").doesNotHaveJsonPath());
```

Kiểm tra link tùy chọn nên dựa trên trạng thái nghiệp vụ cụ thể. Không coi việc thiếu link là lỗi nếu API chủ ý lược capability đó; ngược lại, nếu một relation bắt buộc theo hợp đồng, hãy assert nó phải xuất hiện.

## Relation có key đặc biệt và nhiều link cùng tên

Relation URI thường chứa dấu `:`, `/` hoặc dấu chấm. Dùng bracket notation để truy cập chính xác:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/approval'].href")
            .exists());
```

Nếu relation là CURIE, ví dụ `acme:approval`, path tương ứng:

```java
mockMvc.perform(get("/api/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['acme:approval'].href").exists());
```

Khi relation có nhiều link, JsonPath có thể truy cập từng index hoặc dùng wildcard:

```java
mockMvc.perform(get("/api/cart")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.item[*].href").isNotEmpty());
```

Nếu key chứa dấu nháy đơn, cần escape theo cú pháp JsonPath hoặc dùng cách truy cập JSON node trong Java để tránh tạo expression sai. Không nối dữ liệu không tin cậy trực tiếp vào chuỗi expression.

## Đọc response bằng Jayway JsonPath khi cần logic phức tạp

Các matcher của MockMvc phù hợp với assertion trực tiếp. Khi cần lấy nhiều giá trị để xử lý hoặc so sánh phức tạp, có thể parse body bằng thư viện Jayway JsonPath:

```java
import java.util.List;

import com.jayway.jsonpath.DocumentContext;
import com.jayway.jsonpath.JsonPath;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult result = mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

DocumentContext document = JsonPath.parse(
        result.getResponse().getContentAsString()
);

String selfHref = document.read("$._links.self.href");
List<String> orderIds = document.read("$._embedded.orders[*].id");
Integer totalPages = document.read("$.page.totalPages");
```

Đoạn code giả định endpoint trả `PagedModel` có relation `orders`. Nếu response có cấu trúc khác, cập nhật path và kiểu Java cho phù hợp. `JsonPath.parse(...)` chỉ đọc JSON đã có; nó không thực hiện HTTP request hoặc kiểm tra status/media type thay cho MockMvc.

Nếu `json-path` chưa có trên test classpath, thêm dependency test tương ứng. Với dự án Spring Boot, `spring-boot-starter-test` thường đã cung cấp các thư viện test cần thiết:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Không cần khai báo dependency trực tiếp lần nữa nếu starter đã mang `com.jayway.jsonpath:json-path` vào test runtime.

## Những lỗi thường gặp khi viết JsonPath cho HATEOAS

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `$.links.self` thay cho `$._links.self` | Không tìm thấy link HAL | Bắt đầu từ property `_links` |
| Dùng `$._embedded.order` khi relation là `orders` | Path không khớp relation collection | Kiểm tra đúng tên relation được serialize |
| Dùng dot notation với URI relation | JsonPath diễn giải key thành nhiều property | Dùng bracket notation và quote key |
| Giả định link đơn luôn là object | Test hỏng khi bật `RenderSingleLinks.AS_ARRAY` | Đồng bộ path với `HalConfiguration` |
| Dùng index `[1]` cho phần tử đầu tiên | Đọc nhầm phần tử thứ hai | Nhớ array index bắt đầu từ 0 |
| Dùng `exists()` để phân biệt null với thiếu property | Hai trường hợp có thể cho cùng kết quả | Dùng `hasJsonPath()`/`doesNotHaveJsonPath()` |
| So sánh toàn bộ chuỗi JSON | Test dễ hỏng vì whitespace hoặc thứ tự property | Dùng JsonPath theo từng phần hợp đồng |
| Khóa test vào hostname hoặc port | Test phụ thuộc môi trường | Kiểm tra suffix hoặc query parameter cần thiết |
| Giả định `_embedded` luôn có khi collection rỗng | Test phụ thuộc cách serialize collection rỗng | Xác định hợp đồng và fallback type rõ ràng |
| Kiểm tra `_templates` trên HAL JSON | Assertion không đúng media type | Yêu cầu HAL-FORMS khi kiểm tra affordance |
| Dùng filter expression sai cú pháp | JsonPath không parse hoặc không tìm thấy phần tử | Dùng `?(@.field == 'value')` và đúng kiểu literal |

## Checklist kiểm thử JSON path cho HATEOAS

1. Gửi request với `Accept` đúng media type, ví dụ HAL JSON hoặc HAL-FORMS.
2. Kiểm tra HTTP status và `Content-Type` trước khi kiểm tra body.
3. Xác nhận các field dữ liệu quan trọng và kiểu JSON của chúng.
4. Kiểm tra `_links.self` cùng các relation bắt buộc của workflow.
5. Dùng bracket notation cho custom relation URI hoặc CURIE.
6. Kiểm tra `_embedded`, relation collection, số phần tử và link của item.
7. Kiểm tra pagination metadata và `first`/`prev`/`next`/`last` khi có phân trang.
8. Xác nhận link template có `templated: true` và công bố đúng biến.
9. Phân biệt property null với property không tồn tại.
10. Kiểm tra link tùy chọn theo trạng thái nghiệp vụ và field nội bộ không xuất hiện.
11. Đồng bộ assertion với cấu hình HAL link rendering và relation naming.
12. Tránh so sánh toàn bộ JSON thô nếu cấu trúc từng phần đã đủ bảo vệ hợp đồng.

## Kết luận

JsonPath giúp kiểm tra hợp đồng JSON của Spring HATEOAS ở đúng những vị trí client sử dụng: `_links`, `_embedded`, relation, `href`, URI template, pagination metadata và HAL-FORMS `_templates`. Trong MockMvc, `jsonPath(...)` kết hợp matcher của Spring và Hamcrest cho phép xác nhận giá trị, kiểu, array, filter và sự tồn tại của node. Khi dùng bracket notation cho relation đặc biệt, phân biệt null với property bị thiếu và đồng bộ test với `HalConfiguration`, các bài kiểm thử sẽ phát hiện được thay đổi hypermedia có thể ảnh hưởng tới client mà không phụ thuộc vào định dạng chuỗi JSON.

## Tài liệu tham khảo

- [Spring Framework – Defining Expectations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html): kiểm tra response MockMvc bằng matcher và JsonPath.
- [Spring Framework – JsonPathResultMatchers API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): các matcher `exists`, `hasJsonPath`, `doesNotHaveJsonPath`, `isArray`, `isMap` và `value`.
- [Jayway JsonPath](https://github.com/json-path/JsonPath): cú pháp JSONPath, filter expression và API đọc JSON.
- [Spring HATEOAS Reference – HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal): cấu trúc `_links`, `_embedded`, relation và cấu hình serialize link.
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms): cấu trúc `_templates` và affordance trong HAL-FORMS.
