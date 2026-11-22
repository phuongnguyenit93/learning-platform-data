# JSONPath, JSON assertions và dữ liệu trả về

Trong Spring MVC, trả về HTTP 200 chưa chứng minh API đúng. Một endpoint có thể trả đúng status nhưng sai tên field, thiếu phần tử trong mảng, nhầm đơn vị tiền, lộ thông tin nhạy cảm hoặc trả `null` ở nơi contract yêu cầu trường phải vắng mặt. Vì vậy, **kiểm thử dữ liệu JSON trả về** là một phần thiết yếu của test controller và integration test.

Với Spring MVC Test, **`MockMvc`** giả lập request đi qua cấu hình Spring MVC mà không cần mở HTTP server. `MockMvcResultMatchers.jsonPath(...)` kiểm tra một phần cụ thể của JSON bằng biểu thức **JSONPath**; `content().json(...)` so sánh một cấu trúc JSON tổng thể. Kết hợp chúng với status, header, content type và assertion nghiệp vụ giúp test phát hiện lỗi thật nhưng không ràng buộc quá chặt vào thứ tự field hoặc whitespace.

Bài học áp dụng cho **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x và JUnit Jupiter 5**. Ví dụ chạy được ở `@WebMvcTest` với `@MockitoBean` cho dependency ngoài MVC. Với Boot 3.3 trở về trước, annotation để mock Spring bean thường là `@MockBean`; khi nâng version phải dùng API tương ứng. Ở các nhánh Spring Boot 4/Spring Framework 7, hãy kiểm tra lại tên package, dependency và đặc tính mặc định đúng phiên bản.

**Sau bài học, bạn có thể:**

- Viết JSONPath để truy cập field, nested object, phần tử mảng, wildcard, filter và length.
- Phân biệt `exists()`, `hasJsonPath()`, `doesNotExist()` và `doesNotHaveJsonPath()` khi dữ liệu có thể là `null`.
- Dùng Hamcrest `contains`, `containsInAnyOrder`, `hasSize` và các matcher kiểu dữ liệu.
- Chọn `content().json(..., JsonCompareMode.STRICT)` hay `LENIENT` theo hợp đồng API.
- Kiểm chứng cấu trúc response, mảng, phân trang, HTTP 404, lỗi validation, Unicode và escaping.
- Tránh false positive do mock dữ liệu sai phạm vi, do số thực/định dạng ngày, do thứ tự mảng không xác định hoặc do so sánh chuỗi JSON nguyên văn.
- Viết và chạy một bộ test hoàn chỉnh với `MockMvc`, Spring Boot và JSON assertions.

## 1. JSON assertions cần bảo vệ những điều gì?

Giả sử API trả:

```json
{
  "id": 41,
  "status": "PAID",
  "lines": [
    {"sku": "BOOK", "quantity": 2, "unitPriceVnd": 120000},
    {"sku": "PEN", "quantity": 1, "unitPriceVnd": 20000}
  ],
  "totalVnd": 260000,
  "note": null,
  "tags": ["priority", "gift"]
}
```

Những điều đáng kiểm tra gồm:

| Hợp đồng | Assertion ví dụ | Lỗi có thể phát hiện |
|---|---|---|
| HTTP thành công | `status().isOk()` | Sai mã trạng thái |
| Response JSON | `content().contentTypeCompatibleWith(APPLICATION_JSON)` | Trả HTML/text ngoài ý muốn |
| Đúng mã đơn | `jsonPath("$.id").value(41)` | Lấy nhầm đơn |
| Đúng trạng thái | `jsonPath("$.status").value("PAID")` | Trạng thái chuyển sai |
| Có danh sách | `jsonPath("$.lines").isArray()` | Đổi shape thành object/null |
| Đủ phần tử | `jsonPath("$.lines.length()").value(2)` | Thiếu/thừa mặt hàng |
| Đúng dữ liệu lồng | `jsonPath("$.lines[0].sku").value("BOOK")` | Mapping sai SKU |
| Đúng tổng tiền | `jsonPath("$.totalVnd").value(260000)` | Lỗi tính toán hoặc mapping |
| Note có mặt nhưng null | `hasJsonPath()` kết hợp `doesNotExist()` ở `$.note` | Nhầm trường vắng mặt với trường được khai báo null |
| Không lộ internal field | `jsonPath("$.internalTrace").doesNotHaveJsonPath()` | Vô tình serialize chi tiết nội bộ |

**Đừng kiểm tra tất cả chỉ vì JSON có nhiều field.** Hãy xác định field thuộc hợp đồng nào: mã đơn, tổng tiền, trạng thái và không lộ dữ liệu nhạy cảm thường quan trọng; một field chỉ dùng cho hiển thị có thể được kiểm tra ở test riêng.

Một test tốt nên trả lời được: “Nếu API bị sai theo một cách đáng lo, assertion nào sẽ đỏ?”

## 2. MockMvc đứng ở đâu trong pipeline Spring MVC?

`MockMvc` cho phép tạo request và nhận response qua các thành phần MVC như mapping, argument binding, converter, validation, controller advice và filter được đăng ký trong test context. Không phải mở socket HTTP thật.

```text
JUnit 5 @Test
    |
    v
MockMvc.perform(GET /api/orders/41)
    |
    v
Spring MVC infrastructure
    +--> HandlerMapping
    +--> argument binding / conversion
    +--> Controller
    +--> HttpMessageConverter (Jackson JSON)
    +--> ControllerAdvice / exception handler khi có lỗi
    |
    v
MockHttpServletResponse
    |
    +--> status()
    +--> header() / contentType()
    +--> jsonPath() / content().json()
    +--> MvcResult / ObjectMapper nếu cần phân tích sâu
```

Trong `@WebMvcTest(OrderController.class)`, controller thật được chạy, còn dependency nghiệp vụ bên ngoài có thể được thay bằng `@MockitoBean`. Bài test như vậy bảo vệ **hợp đồng MVC và serialization**, **không tự chứng minh logic nghiệp vụ của service mock**. Cần test domain/service riêng để bảo vệ tính tiền hoặc transition trạng thái thật.

Hai cách phổ biến:

```java
@WebMvcTest(OrderController.class)
class OrderControllerJsonTest {
    // Chỉ tải MVC slice thích hợp cho controller.
}
```

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApiIntegrationTest {
    // Tải Boot context rộng, cũng có MockMvc.
}
```

Hai đoạn chỉ minh họa annotation, chưa phải file chạy độc lập. `@WebMvcTest` phù hợp khi chỉ kiểm API contract/controller và muốn test nhẹ. `@SpringBootTest + @AutoConfigureMockMvc` phù hợp khi cần phối hợp nhiều bean thật. Cả hai **không mặc nhiên mở embedded web server**; nếu muốn kiểm qua cổng TCP thật, dùng web environment và HTTP client phù hợp.

## 3. Cú pháp cơ bản của JSONPath

JSONPath dùng ký hiệu gần giống đường dẫn vào một tài liệu JSON:

- `$`: gốc của tài liệu.
- `.field`: tên field trong object.
- `['field-with-dash']`: cú pháp bracket cho field có ký tự đặc biệt.
- `[0]`: phần tử đầu tiên của mảng; index bắt đầu từ 0.
- `[*]`: mọi phần tử của mảng.
- `..field`: truy cập đệ quy các field cùng tên, dùng thận trọng.
- `[?(@.quantity >= 2)]`: filter các phần tử thỏa điều kiện trên object hiện tại.
- `length()`: biểu thức tính độ dài theo thư viện JSONPath được MockMvc sử dụng.

Từ JSON ở phần 1:

| JSONPath | Kết quả dự kiến |
|---|---|
| `$.id` | `41` |
| `$.status` | `"PAID"` |
| `$.lines` | Một array có 2 object |
| `$.lines[0].sku` | `"BOOK"` |
| `$.lines[1].quantity` | `1` |
| `$.lines[*].sku` | Danh sách `["BOOK","PEN"]` |
| `$.lines.length()` | `2` |
| `$.lines[?(@.quantity >= 2)]` | Array có 1 object (BOOK) |
| `$.note` | Giá trị JSON `null` |
| `$.tags[0]` | `"priority"` |

Ví dụ trong `MockMvc`:

```java
mvc.perform(get("/api/orders/{id}", 41L))
        .andExpectAll(
                status().isOk(),
                jsonPath("$.id").value(41),
                jsonPath("$.status").value("PAID"),
                jsonPath("$.lines[0].sku").value("BOOK"),
                jsonPath("$.lines.length()").value(2));
```

Đây là **mẩu code đặt trong một method `@Test`**, cần mock response, imports và biến `mvc`. Ở phần 10 có bộ file đầy đủ có thể chạy.

### 3.1. JSONPath không phải cú pháp Java

`"$.lines[0].sku"` là **một chuỗi biểu thức** được thư viện JSONPath phân tích lúc test chạy. Java compiler không biết field `lines` có tồn tại. Một typo như `"$.line[0].sku"` thường khiến assertion thất bại khi parser không tìm thấy path.

### 3.2. Root JSON array khác root JSON object

Nếu endpoint trả array làm root:

```json
[
  {"id": 41},
  {"id": 42}
]
```

thì dùng `$[0].id`, `$[1].id` hoặc `$[*].id`. Nếu response là object có field `items`:

```json
{
  "items": [{"id": 41}, {"id": 42}],
  "total": 2
}
```

thì dùng `$.items[0].id` và `$.total`. Chọn đường dẫn theo **shape thật của hợp đồng**, không phỏng đoán từ tên method controller.

## 4. Bộ matcher JSONPath trong Spring MVC Test

Spring cung cấp `MockMvcResultMatchers.jsonPath(String, ...)` và đối tượng `JsonPathResultMatchers`. Những method đáng dùng nhất:

| Matcher | Diễn giải | Ví dụ |
|---|---|---|
| `value(expected)` | Bằng giá trị đã chỉ ra | `jsonPath("$.id").value(41)` |
| `value(hamcrestMatcher)` | Thỏa matcher Hamcrest | `jsonPath("$.tags", hasSize(2))` |
| `exists()` | Path có giá trị **khác null**; array/map rỗng vẫn được coi tồn tại theo nghĩa definite path | `jsonPath("$.status").exists()` |
| `doesNotExist()` | Không có giá trị khác null ở path; path vắng hoặc có null (với definite path) đều phù hợp | `jsonPath("$.note").doesNotExist()` |
| `hasJsonPath()` | Path **có mặt**, kể cả giá trị `null` | `jsonPath("$.note").hasJsonPath()` |
| `doesNotHaveJsonPath()` | Path hoàn toàn **không có**, kể cả null cũng không được chấp nhận | `jsonPath("$.debug").doesNotHaveJsonPath()` |
| `isArray()` | Giá trị là JSON array | `jsonPath("$.lines").isArray()` |
| `isMap()` | Giá trị là JSON object/map | `jsonPath("$").isMap()` |
| `isString()` | Giá trị là string | `jsonPath("$.status").isString()` |
| `isNumber()` | Giá trị là number | `jsonPath("$.totalVnd").isNumber()` |
| `isBoolean()` | Giá trị là boolean | `jsonPath("$.paid").isBoolean()` |
| `isEmpty()` / `isNotEmpty()` | Theo quy tắc empty của Spring với giá trị tìm được | Dùng cho collection hoặc string khi contract yêu cầu |

**Phân biệt rất quan trọng:**

```json
{
  "note": null
}
```

và:

```json
{}
```

không có cùng shape JSON. Với object đầu:

```java
jsonPath("$.note").hasJsonPath();     // PASS: field tồn tại, dù null
jsonPath("$.note").doesNotExist();    // PASS: không có giá trị non-null
jsonPath("$.note").exists();          // FAIL: giá trị null
jsonPath("$.note").doesNotHaveJsonPath(); // FAIL: field thực sự có mặt
```

Đây là **bảng hành vi minh họa**, không phải những dòng `ResultMatcher` được thực thi riêng lẻ. Với object rỗng, `doesNotHaveJsonPath()` sẽ phù hợp vì `note` không xuất hiện.

Nếu yêu cầu là **field phải tồn tại và bằng null**, hãy kiểm tra cả `hasJsonPath()` lẫn `doesNotExist()`, hoặc dùng Jackson `JsonNode` để kiểm `has("note")` + `get("note").isNull()`. Chỉ `doesNotExist()` **không đủ** phân biệt absent với explicit null.

## 5. JSON null, empty string, empty array và missing field

Bốn trường hợp sau mang ý nghĩa khác nhau:

```json
{
  "note": null,
  "nickname": "",
  "tags": [],
  "items": [{}]
}
```

| Giá trị | Ý nghĩa | Cách assert được khuyến nghị |
|---|---|---|
| `note: null` | Field có trong tài liệu, không có value | `hasJsonPath()` + `doesNotExist()` hoặc Jackson `isNull()` |
| `nickname: ""` | Field có string rỗng | `jsonPath("$.nickname").value("")` |
| `tags: []` | Field có array rỗng | `jsonPath("$.tags").isArray()` và `hasSize(0)` |
| `items: [{}]` | Array có 1 object rỗng | `jsonPath("$.items", hasSize(1))`; kiểm object nếu là contract |
| `debug` không tồn tại | Field không nằm trong payload | `jsonPath("$.debug").doesNotHaveJsonPath()` |

`isEmpty()` có thể tiện khi chỉ cần biết giá trị rỗng, nhưng không nên dùng nó để kiểm cùng lúc nhiều hình thức rỗng nếu API phân biệt `null`, `""` và `[]`. Hãy assert **đúng kiểu dữ liệu và shape** của contract.

Một lưu ý về Jackson: nếu DTO cấu hình `@JsonInclude(Include.NON_NULL)`, field null có thể được **bỏ hẳn** khỏi payload. Test nào đòi `hasJsonPath()` sẽ đỏ. Đây có thể là **thay đổi contract hợp lệ hoặc bug**, tùy API; không nên sửa assertion cho xanh trước khi xác định yêu cầu.

## 6. Kiểm tra collection và thứ tự mảng với Hamcrest

Khi JSONPath lấy ra một array hoặc danh sách kết quả, có thể dùng Hamcrest:

```java
import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
```

Với `"tags": ["priority", "gift"]`:

```java
jsonPath("$.tags", hasSize(2));
jsonPath("$.tags", contains("priority", "gift"));
jsonPath("$.tags", containsInAnyOrder("gift", "priority"));
jsonPath("$.tags", hasItem("gift"));
```

Các dòng trên là **mẫu ResultMatcher dùng trong `andExpect(...)` hoặc `andExpectAll(...)`**, không phải statement JUnit độc lập.

Khác biệt giữa các matcher:

- **`contains("priority","gift")`** yêu cầu đúng hai phần tử và **đúng thứ tự**.
- **`containsInAnyOrder("gift","priority")`** yêu cầu đúng các phần tử nhưng không phụ thuộc thứ tự.
- **`hasItem("gift")`** chỉ yêu cầu ít nhất một phần tử phù hợp; các phần tử khác có thể tồn tại.
- **`hasSize(2)`** kiểm số lượng, nhưng không bảo đảm nội dung là đúng.

**Nguyên tắc chọn assertion:** nếu API nói “mới nhất trước” hoặc có `sort=createdAt,desc`, thứ tự là contract và nên dùng `contains`/index. Nếu API trả tập hợp mà thứ tự không được quy định, `containsInAnyOrder` phù hợp hơn. **Không dựa vào thứ tự ngẫu nhiên của database**; nếu yêu cầu có thứ tự, query/service phải định nghĩa rõ `ORDER BY` hoặc comparator.

Đối với mảng object, có thể chọn các field ổn định:

```java
jsonPath("$.lines[*].sku", contains("BOOK", "PEN"));
jsonPath("$.lines[*].quantity", contains(2, 1));
```

Nếu cần chứng minh SKU và quantity thuộc **cùng một phần tử**, kiểm `$.lines[0].sku` cùng `$.lines[0].quantity` hoặc dùng predicate/object comparison. Chỉ kiểm hai danh sách riêng biệt có thể chưa đủ phát hiện việc tráo các cặp dữ liệu.

## 7. JSONPath với filter, wildcard và nested data

JSONPath cho phép lọc array object theo điều kiện:

```json
{
  "items": [
    {"id": 41, "totalVnd": 260000, "status": "PAID"},
    {"id": 42, "totalVnd": 20000, "status": "PAID"},
    {"id": 43, "totalVnd": 500000, "status": "NEW"}
  ]
}
```

Một số truy vấn:

```text
$.items[*].id                       -> [41, 42, 43]
$.items[?(@.totalVnd > 200000)]     -> [object 41, object 43]
$.items[?(@.status == 'PAID')].id    -> [41, 42]
$..status                           -> mọi field status lồng trong document
```

Kiểm số phần tử phù hợp:

```java
jsonPath("$.items[?(@.totalVnd > 200000)]", hasSize(2));
```

**Đây là snippet**, cần ngữ cảnh test và static import `hasSize`.

Hãy ưu tiên JSONPath **rõ ràng**. `$..status` truy vấn đệ quy tiện khi điều tra, nhưng một response thêm object mới cũng có field `status` có thể làm test vỡ hoặc thậm chí che nhầm. Với API contract ổn định, `$.items[*].status` thường đọc dễ hiểu hơn.

Tương tự, filter `?(@.totalVnd > 200000)` rất hữu ích khi muốn kiểm một nhóm dữ liệu, nhưng nếu yêu cầu là “phần tử đầu phải là đơn 41” thì direct index mới là assertion đúng.

## 8. `content().json(...)`: so sánh toàn bộ JSON theo cấu trúc

JSON là một định dạng dữ liệu có cấu trúc; hai response có thể tương đương dù khác khoảng trắng và thứ tự key:

```json
{"id":41,"status":"PAID"}
```

và:

```json
{
  "status": "PAID",
  "id": 41
}
```

So sánh byte/string tuyệt đối bằng `content().string(...)` sẽ thấy chúng khác nhau. Nếu contract chỉ yêu cầu giá trị JSON tương đương, hãy dùng **`content().json(...)`**, không so sánh formatting.

Ở Spring Framework 6.2 có overload:

```java
content().json(expectedJson, JsonCompareMode.STRICT);
content().json(expectedJson, JsonCompareMode.LENIENT);
```

Import:

```java
import org.springframework.test.json.JsonCompareMode;
```

**Ý nghĩa:**

| Mode | Object có field ngoài expected? | Thứ tự JSON array | Khi dùng |
|---|---|---|---|
| `STRICT` | Không cho thêm field ngoài expected theo phép so sánh strict | Có kiểm thứ tự | Response schema phải chính xác; tránh lộ field hoặc đổi shape |
| `LENIENT` | Cho phép thêm field | Không bắt buộc cùng thứ tự array theo mode | Chỉ quan tâm một phần nội dung, contract không yêu cầu cấm field bổ sung |

Ở cả hai mode, **thứ tự key trong object không phải thứ tự mảng** và thường không nên là thứ phải kiểm. `STRICT` không đồng nghĩa so byte-for-byte.

Ví dụ:

```java
mvc.perform(get("/api/orders/{id}", 41L))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {
                  "id": 41,
                  "status": "PAID",
                  "lines": [],
                  "totalVnd": 0,
                  "note": null,
                  "tags": []
                }
                """, JsonCompareMode.STRICT));
```

Đây là snippet minh họa; muốn test pass phải trả JSON có **đúng** các field và giá trị đó. Test runnable dùng response khác ở phần 10–11.

### 8.1. Vì sao không mặc định dùng LENIENT cho mọi test?

Nếu API vô tình trả thêm `passwordHash` hoặc `internalTrace`, một test `LENIENT` chỉ dựa vào vài field expected có thể **vẫn xanh**. Khi danh sách field trả về là hợp đồng bảo mật/chất lượng quan trọng, hãy dùng `STRICT` hoặc assert vắng mặt của những field nhạy cảm.

Ngược lại, nếu API cho phép thêm metadata và chỉ cần kiểm hai field trọng tâm, `LENIENT` hoặc vài JSONPath sẽ ít ràng buộc hơn. **Mode là lựa chọn hợp đồng**, không phải “STRICT luôn tốt hơn”.

### 8.2. JSONAssert và dependency

`content().json(...)` trong Spring Framework 6.2 có tích hợp so sánh JSON; overload thông dụng yêu cầu thư viện **JSONassert** có trên test classpath. Với Spring Boot 3.5 và `spring-boot-starter-test`, bộ dependency kiểm thử thường bao gồm nó. Nếu test báo thiếu class JSONassert, kiểm tra dependency graph thay vì viết một comparator chuỗi tự chế.

## 9. Những phần sẽ được chạy thật trong ví dụ

Ví dụ chính bảo vệ **HTTP mapping, serialization và JSON response**:

- Endpoint `GET /api/orders/{id}`: trả một order hoặc 404.
- Endpoint `GET /api/orders`: nhận `status`, `page`, `size`, bọc danh sách trong một object có metadata phân trang.
- Khi `page` hoặc `size` không hợp lệ, trả HTTP 400 với JSON error xác định.
- DTO dùng Java records; Jackson của Spring Boot serialize thành JSON.
- `OrderLookup` là interface nghiệp vụ, được **mock tại ranh giới MVC slice**. Trong bài này không khẳng định logic tra cứu database hoặc tính tổng tiền bên trong service đã được kiểm tra.
- Unit/service test và repository integration test vẫn cần tồn tại riêng trong ứng dụng thật.

**Lưu ý về ví dụ:** số tiền dùng integer VND để không phụ thuộc biểu diễn số thực nhị phân. Phần giả lập có tên SKU/giá chỉ minh họa JSON contract; dữ liệu do test stub có kiểm soát.

## 10. Project runnable: Java 17+, Spring Boot 3.5.x

### 10.1. Cấu trúc file

```text
src/main/java/com/example/orderapi/
    OrderApiApplication.java
    OrderLineView.java
    OrderView.java
    OrderPage.java
    ApiError.java
    OrderLookup.java
    OrderController.java

src/test/java/com/example/orderapi/
    OrderControllerJsonTest.java
```

Đặt đúng package `com.example.orderapi` ở từng file. Các file dưới đây **có thể biên dịch trong một Gradle/Maven project Spring Boot 3.5 đã có web và test starter**.

### 10.2. Spring Boot application root

**`src/main/java/com/example/orderapi/OrderApiApplication.java`**

```java
package com.example.orderapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
```

Đặt application class ở package gốc để Boot tìm thấy nó từ package của test. `@WebMvcTest` dùng một MVC slice, không tự tạo toàn bộ service hay repository ứng dụng.

### 10.3. DTO cho item, đơn hàng, trang kết quả, lỗi

**`src/main/java/com/example/orderapi/OrderLineView.java`**

```java
package com.example.orderapi;

public record OrderLineView(
        String sku,
        int quantity,
        long unitPriceVnd) {
}
```

**`src/main/java/com/example/orderapi/OrderView.java`**

```java
package com.example.orderapi;

import java.util.List;

public record OrderView(
        long id,
        String status,
        List<OrderLineView> lines,
        long totalVnd,
        String note,
        List<String> tags) {
}
```

**`src/main/java/com/example/orderapi/OrderPage.java`**

```java
package com.example.orderapi;

import java.util.List;

public record OrderPage(
        List<OrderView> items,
        int total,
        int page,
        int size) {
}
```

**`src/main/java/com/example/orderapi/ApiError.java`**

```java
package com.example.orderapi;

public record ApiError(
        String code,
        String message) {
}
```

Các record tạo accessor `id()`, `status()`..., cùng `equals` và `hashCode` theo component. Jackson trong Spring Boot 3.5 với starter-web có thể serialize records thành JSON object với field theo component name.

**Giới hạn chủ đích:** DTO không thêm Jackson naming strategy, `@JsonInclude` hoặc custom serializer, nên hành vi serialize giữ theo cấu hình mặc định của ví dụ. Nếu dự án thay đổi object mapper toàn cục, output thực tế có thể khác; test cần phản ánh contract của dự án, không chỉ mẫu này.

### 10.4. Service port làm collaborator của controller

**`src/main/java/com/example/orderapi/OrderLookup.java`**

```java
package com.example.orderapi;

import java.util.List;
import java.util.Optional;

public interface OrderLookup {
    Optional<OrderView> findById(long id);
    List<OrderView> findByStatus(String status);
}
```

Không có implementation production trong ví dụ vì mục tiêu là MVC slice. `@MockitoBean` trên test sẽ cung cấp một bean mock để controller được tạo. Với ứng dụng thật, cần implementation thực của `OrderLookup`; điều đó được kiểm tra bằng unit/integration test riêng.

### 10.5. Controller thật: HTTP 200, 404, phân trang, lỗi 400

**`src/main/java/com/example/orderapi/OrderController.java`**

```java
package com.example.orderapi;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderLookup lookup;

    public OrderController(OrderLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> findOne(@PathVariable long id) {
        return lookup.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping
    public OrderPage search(
            @RequestParam(defaultValue = "ALL") String status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "size must be between 1 and 100");
        }

        List<OrderView> all = lookup.findByStatus(status);
        long offset = (long) page * size;
        int from = (int) Math.min(offset, all.size());
        int to = (int) Math.min((long) from + size, all.size());

        return new OrderPage(
                all.subList(from, to), all.size(), page, size);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError invalidArgument(IllegalArgumentException cause) {
        return new ApiError("INVALID_REQUEST", cause.getMessage());
    }
}
```

Controller thực hiện **phân trang đơn giản trên danh sách đã được collaborator trả về**. Trong hệ thống thật với dữ liệu lớn, phải phân trang ở tầng repository/query và có order ổn định; không load toàn bộ DB rồi mới `subList`. Mục tiêu ở đây là tạo response JSON có nested array và metadata để test.

Handler `invalidArgument` chỉ minh họa JSON error cho lỗi do code chủ động ném. Nó **không tự thay toàn bộ validation framework** và không chứng minh mọi lỗi deserialize/`@Valid` sẽ có cùng shape. Với API sản phẩm, nên thống nhất error contract qua `@ControllerAdvice` hoặc `ProblemDetail` khi phù hợp.

## 11. Bộ test đầy đủ bằng `@WebMvcTest`

**`src/test/java/com/example/orderapi/OrderControllerJsonTest.java`**

```java
package com.example.orderapi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    OrderLookup lookup;

    private static OrderView firstOrder() {
        return new OrderView(
                41L, "PAID",
                List.of(
                        new OrderLineView("BOOK", 2, 120_000L),
                        new OrderLineView("PEN", 1, 20_000L)),
                260_000L,
                null,
                List.of("priority", "gift"));
    }

    private static OrderView secondOrder() {
        return new OrderView(
                42L, "PAID",
                List.of(new OrderLineView("PEN", 1, 20_000L)),
                20_000L,
                "Ready",
                List.of());
    }

    @Test
    void checksFieldsArraysAndNullUsingJsonPath() throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        mvc.perform(get("/api/orders/{id}", 41L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpectAll(
                        status().isOk(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.id").isNumber(),
                        jsonPath("$.id").value(41),
                        jsonPath("$.status").isString(),
                        jsonPath("$.status").value("PAID"),
                        jsonPath("$.lines").isArray(),
                        jsonPath("$.lines.length()").value(2),
                        jsonPath("$.lines[0].sku").value("BOOK"),
                        jsonPath("$.lines[1].quantity").value(1),
                        jsonPath("$.lines[*].sku",
                                contains("BOOK", "PEN")),
                        jsonPath("$.totalVnd").value(260_000),
                        jsonPath("$.note").hasJsonPath(),
                        jsonPath("$.note").doesNotExist(),
                        jsonPath("$.tags",
                                contains("priority", "gift")),
                        jsonPath("$.internalTrace")
                                .doesNotHaveJsonPath());

        verify(lookup).findById(41L);
    }

    @Test
    void comparesWholeResponseStrictly() throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        mvc.perform(get("/api/orders/41"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "id": 41,
                          "status": "PAID",
                          "lines": [
                            {
                              "sku": "BOOK",
                              "quantity": 2,
                              "unitPriceVnd": 120000
                            },
                            {
                              "sku": "PEN",
                              "quantity": 1,
                              "unitPriceVnd": 20000
                            }
                          ],
                          "totalVnd": 260000,
                          "note": null,
                          "tags": ["priority", "gift"]
                        }
                        """, JsonCompareMode.STRICT));
    }

    @Test
    void checksPaginatedArrayAndFilter() throws Exception {
        when(lookup.findByStatus("PAID"))
                .thenReturn(List.of(firstOrder(), secondOrder()));

        mvc.perform(get("/api/orders")
                        .param("status", "PAID")
                        .param("page", "0")
                        .param("size", "20"))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$").isMap(),
                        jsonPath("$.items").isArray(),
                        jsonPath("$.items", hasSize(2)),
                        jsonPath("$.items[*].id",
                                containsInAnyOrder(41, 42)),
                        jsonPath("$.items[0].lines[0].sku")
                                .value("BOOK"),
                        jsonPath("$.items[?(@.totalVnd > 200000)]",
                                hasSize(1)),
                        jsonPath("$.total").value(2),
                        jsonPath("$.page").value(0),
                        jsonPath("$.size").value(20));

        verify(lookup).findByStatus("PAID");
    }

    @Test
    void missingOrderHas404AndNoJsonBody() throws Exception {
        when(lookup.findById(404L))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/orders/{id}", 404L))
                .andExpectAll(
                        status().isNotFound(),
                        content().string(""));

        verify(lookup).findById(404L);
    }

    @Test
    void invalidPageReturnsControlledJsonError() throws Exception {
        mvc.perform(get("/api/orders")
                        .param("page", "-1"))
                .andExpectAll(
                        status().isBadRequest(),
                        content().contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON),
                        jsonPath("$.code")
                                .value("INVALID_REQUEST"),
                        jsonPath("$.message")
                                .value("page must be >= 0"),
                        jsonPath("$.stackTrace")
                                .doesNotHaveJsonPath());

        verifyNoInteractions(lookup);
    }

    @Test
    void distinguishesExplicitNullFromMissingField()
            throws Exception {
        when(lookup.findById(41L))
                .thenReturn(Optional.of(firstOrder()));

        MvcResult result =
                mvc.perform(get("/api/orders/{id}", 41L))
                        .andExpect(status().isOk())
                        .andReturn();

        JsonNode root = mapper.readTree(
                result.getResponse().getContentAsByteArray());

        assertTrue(root.has("note"));
        assertTrue(root.get("note").isNull());
        assertFalse(root.has("internalTrace"));
    }

    @Test
    void preservesUnicodeQuotesAndNewlines() throws Exception {
        String note = "Dòng 1: \"Mai\"\nDòng 2";
        OrderView view = new OrderView(
                43L, "NEW", List.of(), 0L,
                note, List.of());

        when(lookup.findById(43L))
                .thenReturn(Optional.of(view));

        mvc.perform(get("/api/orders/{id}", 43L))
                .andExpectAll(
                        status().isOk(),
                        jsonPath("$.id").value(43),
                        jsonPath("$.note").value(note));
    }
}
```

### 11.1. Đọc đúng giá trị các assertion

Có **7 test methods** và mỗi test kiểm một hợp đồng:

1. `checksFieldsArraysAndNullUsingJsonPath`: JSONPath cho primitive, nested array, note null và field nhạy cảm không xuất hiện.
2. `comparesWholeResponseStrictly`: nguyên JSON object phải khớp nội dung, bao gồm hai line đúng thứ tự và không có field lạ.
3. `checksPaginatedArrayAndFilter`: root object có `items` array, đủ hai order, filter JSONPath tìm đúng một order có tổng tiền lớn hơn 200.000.
4. `missingOrderHas404AndNoJsonBody`: HTTP 404 với body rỗng. **Không parse JSON trên body rỗng**.
5. `invalidPageReturnsControlledJsonError`: HTTP 400, error payload được điều khiển bởi handler, không lộ stack trace và không gọi lookup.
6. `distinguishesExplicitNullFromMissingField`: Jackson `JsonNode` xác nhận `note` tồn tại với giá trị null, còn `internalTrace` vắng mặt.
7. `preservesUnicodeQuotesAndNewlines`: JSON serialization có escaping hợp lệ và khi parse lại vẫn ra **đúng chuỗi Unicode** ban đầu.

Mỗi test có stub riêng, không dựa vào thứ tự chạy. `@MockitoBean` tạo mock Spring bean cho `OrderLookup` trong MVC slice. Controller chạy thật; service query thật không được kiểm trong bộ test này.

### 11.2. Vì sao so sánh `JsonNode` ở test thứ sáu?

`JsonNode.has("note")` trả true kể cả khi `note` là null, `get("note").isNull()` phân biệt explicit JSON null, và `has("internalTrace")` kiểm sự hiện diện của field. Đây là một lựa chọn rõ ràng khi cần kiểm **shape tinh tế** mà JSONPath một mình dễ bị nhầm.

Ta dùng `getContentAsByteArray()` để đưa byte JSON gốc vào Jackson, tránh phụ thuộc chuyển đổi charset khi đọc body dạng string.

### 11.3. Vì sao `@WebMvcTest` mà không dùng `@SpringBootTest`?

Mục tiêu là response HTTP mapping và Jackson serialization. Một MVC slice cung cấp đúng bộ hạ tầng này, thường nhẹ hơn full Boot context. Khi yêu cầu chuyển sang kiểm transaction, JPA query, authorization thực hoặc nghiệp vụ qua nhiều bean, chọn test cấp khác và chỉ mock ở boundary thích hợp.

## 12. Phân trang: không chỉ kiểm `items.length()`

Một API phân trang thường có ít nhất ba lớp hợp đồng:

1. **Dữ liệu** trong `items` có đúng phần tử/field không.
2. **Metadata** gồm `page`, `size`, `total` hoặc `totalElements` có đúng không.
3. **Thứ tự và giới hạn** có được áp dụng đúng theo `sort` và `size` không.

Ví dụ:

```json
{
  "items": [{"id": 41}, {"id": 42}],
  "total": 7,
  "page": 0,
  "size": 2
}
```

Các assertion:

```java
jsonPath("$.items", hasSize(2));
jsonPath("$.total").value(7);
jsonPath("$.page").value(0);
jsonPath("$.size").value(2);
jsonPath("$.items[*].id", contains(41, 42));
```

Đây là **snippet**. Nó chưa tự chứng minh có đúng 7 records trong DB; nếu metadata do mock service trả về, test chỉ bảo vệ serialization. Muốn xác nhận logic phân trang thật, cần chạy service/repository với dữ liệu fixture và assert cả page boundary, thứ tự cùng truy vấn.

Một số ứng dụng dùng kiểu `Page<T>` của Spring Data, kết quả có thể chứa cấu trúc JSON phong phú và tùy version. **Không nên mặc định API công khai phải có shape nội bộ của Spring Data**. Một DTO response ổn định giúp kiểm thử và tránh làm client phụ thuộc implementation detail.

## 13. JSONPath và kiểu số: Integer, Long, Double, BigDecimal

JSON chỉ có một loại cú pháp “number”, nhưng thư viện đọc JSON vào Java có thể tạo `Integer`, `Long`, `Double`, `BigDecimal` hoặc một kiểu số khác tùy giá trị/cấu hình.

Ví dụ JSON:

```json
{
  "count": 2,
  "totalVnd": 260000,
  "rate": 0.075,
  "largeId": 9007199254740993
}
```

Những điểm cần chú ý:

- `jsonPath("$.count").value(2)` thường rõ và ổn định với số nguyên nhỏ.
- `jsonPath("$.totalVnd").isNumber()` xác nhận kiểu number; `value(260000)` xác nhận giá trị đúng cho ví dụ.
- Với số thập phân, `value(0.075)` có thể gặp sai số/khác kiểu Java ở các phép so sánh phức tạp; có thể dùng matcher tolerance, coercion type hoặc parse bằng Jackson/`BigDecimal` theo contract.
- Với integer rất lớn vượt khả năng biểu diễn chính xác của JavaScript number trong client, API cần cân nhắc biểu diễn bằng string. **Không tự suy luận kiểu số JSON bằng trực giác từ Java record.**
- Tiền tệ nên có contract về currency, đơn vị nhỏ nhất và rounding. Trong ví dụ, `long totalVnd` là **VND nguyên**, không phải số thực floating-point.

Một matcher cho số thực khi thích hợp:

```java
// Snippet, dùng import static org.hamcrest.Matchers.closeTo;
jsonPath("$.rate").value(closeTo(0.075, 0.000001),
                         Double.class);
```

Overload `value(Matcher, Class)` có thể hỗ trợ ép kiểu kết quả trước khi so khớp. Tuy nhiên, **không dùng tolerance rộng để che sai lệch số tiền**. Với tiền cần kiểm chính xác, nên biểu diễn bằng integer minor units hoặc dùng decimal type + JSON contract rõ ràng.

## 14. JSON string và escaping: test nội dung đã giải mã

Chuỗi chứa ký tự nháy kép hoặc xuống dòng sẽ được JSON escape:

```json
{
  "note": "Dòng 1: \"Mai\"\nDòng 2"
}
```

Nhưng khi controller trả Java string:

```java
String note = "Dòng 1: \"Mai\"\nDòng 2";
```

thì giá trị trong bộ nhớ chứa **dấu nháy thực** và **ký tự newline thực**. Jackson encode sang JSON; JSONPath parse lại và trả về Java string gốc.

Do đó:

```java
jsonPath("$.note").value(note);
```

thường là assertion có ý nghĩa hơn so với kiểm từng dấu backslash của output serialized. Nếu contract yêu cầu chính xác byte encoding/escaping hoặc chữ ký số trên payload, cần test ở tầng raw byte chuyên biệt thay vì chỉ JSON semantic comparison.

Với tiếng Việt, emoji và ký tự Unicode khác, cũng nên so giá trị **sau khi parse JSON**, không dựa vào lựa chọn encode dưới dạng ký tự trực tiếp hay `\\uXXXX` của serializer. Hai biểu diễn có thể mang cùng dữ liệu JSON.

## 15. Date, time, timezone và định dạng JSON

Date/time là nguyên nhân phổ biến khiến test JSON phản ánh sai yêu cầu.

Ví dụ contract:

```json
{
  "createdAt": "2026-11-08T09:15:00Z"
}
```

Nếu ứng dụng dùng `Instant`, Jackson với module Java Time thông thường có thể serialize thành ISO-8601 theo cấu hình. Nhưng `LocalDateTime` không chứa timezone và có ý nghĩa khác `Instant`. Nếu serializer/project thiết lập timestamp dạng số, custom pattern hoặc zone riêng, response có thể khác.

Một JSON assertion có thể:

```java
jsonPath("$.createdAt")
        .value("2026-11-08T09:15:00Z");
```

Đây là snippet; để test ổn định cần nguồn thời gian **cố định**, ví dụ inject `Clock.fixed(...)` vào service thay vì dựa vào `Instant.now()` ở thời điểm test. Nếu API chỉ yêu cầu valid ISO instant mà không quy định thời điểm cụ thể, có thể parse value thành `Instant` rồi assert các điều kiện phù hợp.

**Không hard-code thời gian hiện tại vào expected JSON rồi chấp nhận test flaky.** Quyết định độ chính xác, offset, millisecond precision và format là một phần API contract.

## 16. JSON error payload: HTTP status và shape đều quan trọng

Một API có thể trả HTTP 400 nhưng không có JSON error đúng contract. Test nên kiểm:

- HTTP status (`400`, `404`, `409` hoặc `422` theo quy ước API).
- `Content-Type` tương ứng (JSON thường hoặc `application/problem+json` nếu dùng Problem Details).
- Mã lỗi ổn định, message công khai và các field được phép.
- Không lộ stack trace, internal SQL, token, email nhạy cảm hoặc server path.
- Với validation có nhiều lỗi, shape danh sách lỗi, field name và thứ tự (nếu quy định) phải đúng.

Ví dụ custom error trong dự án runnable:

```json
{
  "code": "INVALID_REQUEST",
  "message": "page must be >= 0"
}
```

Assertions:

```java
status().isBadRequest();
jsonPath("$.code").value("INVALID_REQUEST");
jsonPath("$.message").value("page must be >= 0");
jsonPath("$.stackTrace").doesNotHaveJsonPath();
```

Đây là **các matcher snippet** dùng trong `andExpectAll`. Nếu một ứng dụng dùng Spring `ProblemDetail`, JSON shape thường chứa những field như `type`, `title`, `status`, `detail`, `instance` theo cấu hình; không tự mặc định ví dụ custom `ApiError` đúng cho mọi dự án.

**Quan trọng:** status/error response do security filter, Jackson parse error, validation framework hoặc controller advice tạo ra có thể đi qua nhánh khác. Một test custom handler không chứng minh mọi nhánh lỗi đều an toàn; bổ sung test cho các nguồn lỗi thật của API.

## 17. So sánh JSONPath, JSONAssert, Jackson và JsonTester

| Công cụ | Mạnh ở đâu | Điểm cần lưu ý |
|---|---|---|
| `MockMvcResultMatchers.jsonPath` | Assert field/nested array/predicate nhanh trực tiếp trên HTTP response | Biểu thức là string, dễ typo; số và null cần hiểu rõ |
| `content().json` | So sánh cấu trúc JSON tổng thể, chọn strict/lenient | Expected lớn khó đọc; mode không được chọn đúng sẽ quá chặt hoặc quá lỏng |
| Jackson `ObjectMapper.readTree` / `JsonNode` | Kiểm tra cấu trúc, loại, field present/null/missing; thao tác dữ liệu phức tạp | Test code dài hơn; cần tách parse và assertion rõ |
| JSONassert API trực tiếp | So sánh hai JSON strings không cần MockMvc | Nếu test HTTP phải tự lấy body; chú ý mode |
| `@JsonTest` / JacksonTester | Test serialization/deserialization của DTO hoặc custom module độc lập MVC | Không xác minh routing, HTTP status, filter hay controller |
| `WebTestClient` | Test HTTP response theo API reactive hoặc bind với server/controller | Không phải cùng API với MockMvc; chọn theo stack/web environment |

Không cần chọn một công cụ cho mọi assertion. Ví dụ:

- `status().isOk()` + `jsonPath("$.id").value(41)`: đủ cho một contract nhỏ.
- `content().json(expected, STRICT)`: phù hợp khi cả schema và absence of extras là quan trọng.
- `JsonNode`: phù hợp khi cần phân biệt thật chặt null, missing, hoặc so sánh hai tập dữ liệu động.

## 18. Tránh kiểm thử bằng output do chính mock đặt ra

Với MVC slice, việc mock `OrderLookup` là **hợp lý** để test JSON mapping. Nhưng nếu mục tiêu là kiểm tra service tính tiền, một test như:

```java
OrderLookup lookup = mock(OrderLookup.class);
when(lookup.findById(41L))
        .thenReturn(Optional.of(expectedOrder));
assertEquals(expectedOrder, lookup.findById(41L).orElseThrow());
```

**không chạy service nghiệp vụ thật**. Nó chỉ chứng minh Mockito trả dữ liệu đã stub.

Phân chia phạm vi rõ:

1. **Domain/unit test:** tính tổng tiền, thuế, chiết khấu, trạng thái thật; dùng object thật và mock/fake các outbound ports nếu cần.
2. **MVC slice test:** controller thật, converter thật, response JSON thật; mock service boundary để tạo input xác định cho serialization.
3. **Integration test:** nhiều bean thật, repository/transaction/adapter quan trọng; assert response và side effects qua boundary được kiểm soát.

Test thứ hai không thay thế test thứ nhất, và test thứ nhất không bảo vệ HTTP/JSON schema. Một suite tốt kết hợp các tầng theo rủi ro, không bắt một test làm mọi nhiệm vụ.

## 19. Những lỗi thường gặp khi JSON assertions bị sai hoặc flaky

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `No value at JSON path "$.x"` | Field vắng mặt, sai tên, DTO bị `@JsonIgnore` hoặc naming strategy thay đổi | In/inspect JSON thực tế có kiểm soát; kiểm contract và serializer |
| `jsonPath("$.note").exists()` fail dù JSON có note | `note` là `null`; `exists()` đòi non-null | Dùng `hasJsonPath()` nếu chỉ cần tồn tại, hoặc kiểm null tường minh |
| Test pass dù field nhạy cảm xuất hiện | Dùng `LENIENT` và chỉ kiểm field chính | Thêm `doesNotHaveJsonPath` hoặc `STRICT` khi phải cấm extras |
| So sánh JSON string fail vì whitespace | Dùng `content().string(...)` trên object JSON | Dùng `content().json(...)` hoặc JSONPath |
| Array test flaky | Thứ tự từ DB/HashMap không được bảo đảm | Dùng `containsInAnyOrder` khi order không phải contract, hoặc fix ORDER BY |
| So sánh số thập phân sai | Khác kiểu Java, rounding hoặc floating-point | Chọn numeric representation và matcher rõ; tránh tolerance tùy tiện |
| Path parser lỗi | JSONPath syntax sai hoặc body không phải JSON hợp lệ | Kiểm status, content type, body và biểu thức |
| JSONPath trên HTTP 404 fail | Body rỗng hoặc không phải JSON | Assert `status` + `content().string("")` khi contract có body rỗng |
| `@Autowired MockMvc` null | Test không có Spring MVC TestContext hoặc thiếu `@AutoConfigureMockMvc` | Dùng `@WebMvcTest` hoặc `@SpringBootTest + @AutoConfigureMockMvc` |
| Context thiếu service | Slice không scan service nghiệp vụ | Cung cấp `@MockitoBean` hoặc import collaborator cần thiết theo phạm vi |
| Test chỉ xanh khi chạy riêng | Global state, shared mock/fake, profile hoặc DB fixture ảnh hưởng nhau | Giữ fixture/test độc lập, không dựa thứ tự chạy |
| Response lỗi shape khác test | Default error handling vs `@ControllerAdvice` vs Spring Security | Bảo vệ contract theo đường lỗi thực tế và config/version |
| Ngày giờ fail theo timezone | Dựa vào system clock/default zone | Inject fixed clock, dùng `Instant`/zone rõ, assert format contract |
| Test không phát hiện field bị xóa | `hasItem` hoặc `LENIENT` quá dễ | Chọn matcher đủ ràng buộc theo yêu cầu |
| Test fail sau thêm field không ảnh hưởng client | `STRICT` đang bảo vệ schema cứng dù API cho phép mở rộng | Dùng `LENIENT`/JSONPath khi contract cho phép thêm field |

**Một test dễ bảo trì nên fail vì khác biệt trong hợp đồng, không fail vì kiểu format của JSON printer.** Đồng thời, không làm nó quá lenient để lọt bug bảo mật hoặc serialization quan trọng.

## 20. Chiến lược assertion theo mức rủi ro

Một quy tắc đơn giản:

- **Critical fields** (id, số tiền, trạng thái, quyền, thông tin thuộc khách hàng): assert giá trị chính xác và kiểm không lộ dữ liệu ngoài contract.
- **Collections**: assert số lượng, identity của phần tử và order **nếu order là contract**.
- **Optional fields**: xác định rõ absent, null, empty hay có value; không dùng một matcher mơ hồ.
- **Error payload**: assert status, public code, message hoặc reason; che chi tiết nội bộ.
- **Metadata** (page, total, next cursor): assert điều kiện biên thực tế, không chỉ một happy path.
- **Date/time**: cố định clock, zone và serialization expectations.
- **Evolving/extension fields**: ưu tiên assertion theo ý nghĩa thay vì strict full JSON nếu API cho phép mở rộng.

**Gợi ý khi thêm test mới:** viết JSON response dự kiến trước, gạch dưới 3–7 hợp đồng quan trọng nhất, rồi chọn matcher để bắt đúng lỗi. Không cần biến mọi response thành một snapshot hàng trăm dòng mà bất cứ thay đổi vô hại nào cũng phá.

## 21. Bài tập thực hành

### Bài A — tìm path đúng

Với JSON:

```json
{
  "customer": {
    "id": 9,
    "name": "Mai"
  },
  "orders": [
    {"id": 41, "totalVnd": 260000},
    {"id": 42, "totalVnd": 20000}
  ]
}
```

Hãy viết JSONPath kiểm: tên khách hàng là `Mai`, ID của order thứ hai là 42, mảng orders có hai phần tử, và có một order trên 200.000 VND.

**Gợi ý lời giải:** `$.customer.name`, `$.orders[1].id`, `$.orders.length()`, `$.orders[?(@.totalVnd > 200000)]` kết hợp `hasSize(1)`.

### Bài B — null hay missing?

So sánh:

```json
{"note": null}
```

và:

```json
{}
```

`doesNotExist()` có đủ phân biệt hai tài liệu không? Viết hai assertion chứng minh note tồn tại nhưng null, và một assertion chứng minh note vắng hẳn.

**Đáp án:** Với definite JSONPath, `doesNotExist()` không đủ; dùng `hasJsonPath()` cùng `doesNotExist()` cho null, `doesNotHaveJsonPath()` cho absent.

### Bài C — chấp nhận mảng không có thứ tự

API search trả `["BOOK", "PEN"]` hoặc `["PEN","BOOK"]` và hợp đồng không quy định order. Nên dùng `contains` hay `containsInAnyOrder`? Vì sao chỉ `hasSize(2)` chưa đủ?

**Đáp án:** Dùng `containsInAnyOrder("BOOK","PEN")`; kiểm size đơn thuần không bảo đảm danh sách chứa đúng hai SKU.

### Bài D — phát hiện rò rỉ dữ liệu

Một API trước đây trả:

```json
{"id": 41, "status": "PAID"}
```

Sau refactor trả:

```json
{"id": 41, "status": "PAID", "passwordHash": "internal"}
```

`content().json(expected, JsonCompareMode.LENIENT)` với expected cũ có thể fail không? Viết assertion bảo vệ chống thêm field `passwordHash`.

**Đáp án:** LENIENT có thể chấp nhận extra field nên test vẫn xanh. Dùng `jsonPath("$.passwordHash").doesNotHaveJsonPath()` hoặc so JSON STRICT khi mọi extra field đều bị cấm.

### Bài E — kiểm HTTP status khi không tìm thấy

`GET /api/orders/404` trả 404 và **body rỗng**. Viết assertion đúng và giải thích vì sao không nên dùng `jsonPath("$.message")` trên response này.

**Đáp án:** `status().isNotFound()` cùng `content().string("")`. Body rỗng không phải JSON object nên JSONPath không áp dụng.

### Bài F — kiểm pagination

API trả 15 order, `size=5`, `page=1`. Theo contract phân trang zero-based, expected items là vị trí nào? Metadata nào cần kiểm? Trong ví dụ controller mục 10, nếu danh sách có 15 order, page 1 size 5 sẽ dùng `subList(5,10)`. Assert `page`, `size`, `total`, danh sách 5 id và thứ tự nếu có `sort` được quy định.

### Bài G — thời gian động

Một test assert `createdAt` bằng thời gian `Instant.now()` ngay trước HTTP request. Vì sao test có thể flaky? Sửa bằng cách inject fixed clock hoặc xây dữ liệu fixture với instant cố định, và assert timestamp string đúng định dạng.

### Bài H — phạm vi test service và controller

Nếu test controller dùng `@MockitoBean OrderLookup` trả `totalVnd=260000` và JSONPath pass, có thể kết luận service tính tổng tiền thật đúng không? Không. Hãy viết test domain/service với real calculation và fake/mocked outbound dependency, rồi giữ MVC slice để bảo vệ serialization.

## 22. Checklist trước khi chốt bài kiểm thử JSON

- [ ] Tôi biết rõ API contract của endpoint: status, content type, JSON root và field trọng tâm.
- [ ] Tôi chọn đúng cấp test: MVC slice, Spring Boot integration hoặc serialization-only test.
- [ ] `@MockitoBean` chỉ thay collaborator ngoài phạm vi, không thay code đang định kiểm tra.
- [ ] JSONPath bắt đầu từ đúng `$` và biết root là object hay array.
- [ ] Nested field, array index, wildcard và predicate được dùng đúng dữ liệu response.
- [ ] Với null/missing/empty, tôi hiểu khác biệt `hasJsonPath`, `exists`, `doesNotExist` và `doesNotHaveJsonPath`.
- [ ] Tôi không dùng `isEmpty` thay cho kiểm đúng shape khi contract phân biệt null, empty string và empty array.
- [ ] Với collection, tôi kiểm cả nội dung và size; order chỉ bị bắt buộc khi API quy định.
- [ ] Tôi đã chọn `STRICT` hoặc `LENIENT` có chủ đích, không theo thói quen.
- [ ] Tôi không so chuỗi JSON byte-for-byte khi chỉ cần semantic JSON equality.
- [ ] Số tiền, timestamp và Unicode có representation và assertion rõ.
- [ ] Lỗi 400/404/409 có response shape đúng; không parse JSON trên body rỗng.
- [ ] Tôi kiểm không có field nhạy cảm ngoài hợp đồng.
- [ ] Fixture không phụ thuộc time/random/network hoặc thứ tự chạy của các test khác.
- [ ] Khi test fail, tôi có thể phân biệt lỗi data mapping, serialization, status, config và business logic.
- [ ] Tôi biết test MVC không thay thế service/repository/transaction tests.

**Kết luận:** `jsonPath(...)` thích hợp để kiểm những giá trị và cấu trúc quan trọng trong HTTP response; `content().json(...)` phù hợp để so cấu trúc tổng thể; Jackson `JsonNode` giúp xử lý các trường hợp tinh tế như null và missing. Chọn matcher theo **hợp đồng API**, không chỉ theo cách viết ngắn nhất. Test JSON đáng tin vừa bắt sai dữ liệu, sai cấu trúc và rò rỉ field, vừa tránh phụ thuộc whitespace, thứ tự không được đảm bảo hoặc kết quả từ mock nghiệp vụ ngoài phạm vi.

## 23. Cấu hình Gradle, chạy test và kết quả kỳ vọng

Trong một project Gradle đã có Spring Boot plugin/BOM và repositories tương ứng, phần dependency cần cho code ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải file `build.gradle` độc lập vì chưa khai báo plugins và versions. Spring Boot 3.5 với starter-test cung cấp các thành phần kiểm thử Spring MVC, Mockito, JUnit Jupiter, Hamcrest/JSONassert theo dependency quản lý của Boot. Nếu dự án tùy biến dependencies, kiểm tra dependency graph thực tế.

Chạy từ thư mục dự án có Gradle wrapper:

```bash
./gradlew test --tests com.example.orderapi.OrderControllerJsonTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.orderapi.OrderControllerJsonTest
```

Với project multi-module, dùng đúng task của module chứa test thay vì một tên module tự đoán. Các snippet bên ngoài cây file ở mục 10 chỉ dùng để minh họa cơ chế, không phải những file biên dịch độc lập.

**Kết quả dự kiến theo code ví dụ:** 7 phương thức test được JUnit Jupiter chạy; response JSON trong các kịch bản có ID 41/42/43, body 404 rỗng, JSON error 400, và Unicode note đúng nội dung. Nếu project/dependencies và code được cấu hình đúng, Gradle báo `BUILD SUCCESSFUL`. Đây là **dự kiến từ kiểm tra mã và hợp đồng**, không phải tuyên bố đã chạy test trên workspace cụ thể; không có stdout nghiệp vụ cố định từ bộ test.

Báo cáo Gradle thường ở `build/reports/tests/test/index.html` và file kết quả `build/test-results/test/` của module.

### Tài liệu tham khảo chính thức

- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — `JsonPathResultMatchers`: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html
- Spring Framework 6.2 — `JsonPathExpectationsHelper`, null và missing: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/util/JsonPathExpectationsHelper.html
- Spring Framework 6.2 — `ContentResultMatchers` và `JsonCompareMode`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html
- Spring Boot 3.5 — Testing Spring MVC: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Jayway JsonPath — expression syntax: https://github.com/json-path/JsonPath
