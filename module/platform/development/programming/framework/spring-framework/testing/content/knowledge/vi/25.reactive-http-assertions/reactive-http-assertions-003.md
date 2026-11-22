# JSONPath, so sánh JSON và kiểm tra body trống

Khi kiểm thử response của Spring MVC, có ba nhu cầu thường gặp: đọc một phần dữ liệu JSON theo đường dẫn, so sánh toàn bộ response với JSON mong đợi và xác nhận response không có body. Mỗi cách kiểm tra phù hợp với một loại hợp đồng khác nhau. JSONPath phù hợp khi chỉ một số field quan trọng; so sánh JSON phù hợp khi cấu trúc và dữ liệu response cần được kiểm tra cùng nhau; kiểm tra body trống phù hợp với các response như `204 No Content`, `HEAD` hoặc endpoint chỉ xác nhận một thao tác.

MockMvc cung cấp các matcher này qua `MockMvcResultMatchers.jsonPath(...)` và `MockMvcResultMatchers.content()`. Test gửi request như một servlet request mô phỏng, sau đó kiểm tra status, headers và body mà Spring MVC tạo ra.

## Chuẩn bị MockMvc và dependency

Với Spring Boot, có thể dùng `@WebMvcTest` để nạp web layer và inject `MockMvc`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;
}
```

Với Spring MVC thuần hoặc một application context đầy đủ, có thể dựng MockMvc bằng `MockMvcBuilders.webAppContextSetup(webApplicationContext)`. Các ví dụ bên dưới tập trung vào phần assertion nên giả định `mockMvc` đã được khởi tạo và controller trả JSON theo hợp đồng được minh họa.

JSONPath matcher cần thư viện Jayway JSONPath (`com.jayway.jsonpath:json-path`) trên test classpath. So sánh JSON bằng `content().json(...)` cần JSONassert (`org.skyscreamer:jsonassert`). Spring Boot test starter thường quản lý các thư viện kiểm thử phổ biến này; với dự án Spring thuần, hãy khai báo dependency test tương ứng và để dependency management của dự án quản lý version tương thích.

## JSONPath là gì?

JSONPath là cú pháp truy vấn một phần tử hoặc tập phần tử trong tài liệu JSON. Nó tương tự cách XPath truy vấn XML, nhưng dành cho JSON. Trong Spring MockMvc, `jsonPath(expression)` tạo một `ResultMatcher` dùng để đọc giá trị theo biểu thức và so sánh với kết quả mong đợi.

Các ký hiệu thường dùng:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `$` | Root JSON document | `$` |
| `.property` | Thuộc tính của object | `$.customer.name` |
| `['property']` | Thuộc tính theo bracket notation | `$['customer']['name']` |
| `[0]` | Phần tử đầu tiên của array | `$.items[0]` |
| `[*]` | Tất cả phần tử trong array | `$.items[*].id` |
| `..property` | Tìm thuộc tính ở các cấp con | `$..id` |
| `[?(...)]` | Filter các phần tử theo điều kiện | `$.items[?(@.active == true)]` |

Giả sử endpoint trả response:

```json
{
  "id": 42,
  "status": "PAID",
  "total": 125.50,
  "customer": {
    "name": "Mai Nguyen",
    "email": "mai@example.test"
  },
  "items": [
    { "sku": "KB-01", "quantity": 1, "active": true },
    { "sku": "MS-02", "quantity": 2, "active": true }
  ]
}
```

Có thể kiểm tra một field đơn giản:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.customer.name").value("Mai Nguyen"));
```

Một request có thể có nhiều `andExpect(jsonPath(...))`. Mỗi matcher tập trung vào một phần hợp đồng, vì vậy khi thất bại, thông báo lỗi thường chỉ rõ path nào có giá trị không đúng.

## Kiểm tra object lồng nhau và array

Với object lồng nhau, nối tên thuộc tính bằng dấu chấm:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.customer.email")
                .value("mai@example.test"));
```

Với array, dùng index nếu vị trí là một phần của hợp đồng:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[0].sku").value("KB-01"))
        .andExpect(jsonPath("$.items[1].quantity").value(2));
```

Nếu thứ tự phần tử không quan trọng, truy vấn tất cả giá trị bằng wildcard và dùng Hamcrest matcher:

```java
import static org.hamcrest.Matchers.containsInAnyOrder;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[*].sku")
                .value(containsInAnyOrder("KB-01", "MS-02")));
```

Khi thứ tự là một phần của API contract, dùng matcher có thứ tự:

```java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[*].sku")
                .value(contains("KB-01", "MS-02")));
```

Wildcard trả về tập giá trị phù hợp với biểu thức. Nếu dùng `containsInAnyOrder`, test không bị phụ thuộc thứ tự array; nếu dùng `contains`, test đồng thời xác nhận thứ tự.

Có thể kiểm tra số phần tử bằng hàm `length()` của JSONPath:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items.length()").value(2));
```

Nếu muốn xác nhận một phần tử đáp ứng điều kiện, dùng filter:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[?(@.sku == 'MS-02')].quantity")
                .value(contains(2)));
```

Filter đặc biệt hữu ích khi response là danh sách có thứ tự thay đổi nhưng test cần xác nhận một phần tử theo khóa nghiệp vụ. Đừng dùng index cố định nếu API không cam kết thứ tự.

## Kiểm tra kiểu dữ liệu

JSON phân biệt string, number, boolean, object, array và null. Không nên chỉ kiểm tra giá trị hiển thị giống nhau; ví dụ số `42` khác chuỗi `"42"`.

Spring cung cấp các matcher kiểu dữ liệu:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.id").isNumber())
        .andExpect(jsonPath("$.status").isString())
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.customer").isMap());
```

Với boolean:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.items[0].active").isBoolean())
        .andExpect(jsonPath("$.items[0].active").value(true));
```

Với số thực, có thể dùng matcher dung sai để tránh phụ thuộc biểu diễn floating-point:

```java
import static org.hamcrest.Matchers.closeTo;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(jsonPath("$.total").value(closeTo(125.50, 0.001)));
```

Nếu giá trị số được serialize thành `BigDecimal`, `Double` hoặc một kiểu `Number` khác, matcher cần chấp nhận kiểu số phù hợp. Khi cần ép kiểu đích một cách tường minh, Spring có overload `value(expectedValue, targetType)` hoặc `value(matcher, targetType)` trên JSONPath matcher ở các phiên bản hỗ trợ. Chỉ dùng ép kiểu khi test cần kiểm tra kiểu chuyển đổi cụ thể; thông thường kiểm tra giá trị và `isNumber()` là đủ.

## Phân biệt field không tồn tại, field null và field rỗng

Ba trạng thái này có ý nghĩa khác nhau trong JSON:

```json
{
  "nickname": null,
  "tags": [],
  "metadata": {}
}
```

- Field không tồn tại: response không có key đó.
- Field có giá trị `null`: key tồn tại nhưng không có giá trị JSON.
- Field rỗng: key tồn tại và chứa string rỗng, array rỗng hoặc object rỗng.

JSONPath matcher có các phép kiểm tra riêng:

```java
mockMvc.perform(get("/api/profile"))
        .andExpect(jsonPath("$.nickname").hasJsonPath())
        .andExpect(jsonPath("$.nickname").value(nullValue()))
        .andExpect(jsonPath("$.legacyCode").doesNotHaveJsonPath())
        .andExpect(jsonPath("$.tags").isArray())
        .andExpect(jsonPath("$.tags").isEmpty())
        .andExpect(jsonPath("$.metadata").isMap())
        .andExpect(jsonPath("$.metadata").isEmpty());
```

Các matcher `exists()` và `doesNotExist()` thường được dùng để kiểm tra có/không có giá trị phù hợp. Khi cần phân biệt rõ một key tồn tại với giá trị `null` với một key hoàn toàn không tồn tại, dùng `hasJsonPath()`/`doesNotHaveJsonPath()` kết hợp `value(nullValue())` cho trường hợp null.

Với string rỗng, có thể kiểm tra trực tiếp:

```java
mockMvc.perform(get("/api/profile"))
        .andExpect(jsonPath("$.nicknameLabel").value(""));
```

Không dùng `doesNotExist()` để kiểm tra array rỗng hoặc string rỗng. Path vẫn tồn tại; giá trị của nó chỉ là rỗng.

## Kiểm tra JSON bằng content().json()

JSONPath phù hợp khi chỉ cần kiểm tra một vài thuộc tính. Khi cần xác nhận cả cấu trúc và nhiều giá trị trong response, có thể so sánh response JSON với một JSON mẫu:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

String expectedJson = """
        {
          "id": 42,
          "status": "PAID",
          "customer": {
            "name": "Mai Nguyen",
            "email": "mai@example.test"
          }
        }
        """;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson));
```

`content().json(...)` parse hai tài liệu JSON rồi so sánh cấu trúc và giá trị. Nó không so sánh chuỗi JSON theo từng ký tự, vì vậy khác biệt về khoảng trắng, xuống dòng hoặc thứ tự key trong object không làm test thất bại.

### Strict và lenient comparison

Spring MockMvc hỗ trợ chế độ so sánh nghiêm ngặt hoặc linh hoạt:

```java
// Strict: yêu cầu cấu trúc và thứ tự array khớp.
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, true));

// Lenient: cho phép field bổ sung và không bắt buộc thứ tự array.
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, false));
```

Chế độ `strict = true` yêu cầu response không có field dư so với JSON mẫu và thứ tự phần tử array phải khớp. Chế độ `strict = false` cho phép field dư trong object và không bắt buộc thứ tự array; các field và giá trị được nêu trong JSON mẫu vẫn phải có trong response.

Chọn chế độ dựa trên hợp đồng API:

| Trường hợp | Chế độ phù hợp |
|---|---|
| Response có schema cố định, không cho phép field ngoài hợp đồng | Strict |
| API có thể thêm field tương thích ngược | Lenient |
| Thứ tự array được quy định và quan trọng | Strict hoặc kiểm tra riêng bằng JSONPath có thứ tự |
| Thứ tự array không được đảm bảo | Lenient hoặc JSONPath với `containsInAnyOrder` |
| Chỉ một vài field quan trọng | JSONPath thường dễ đọc hơn |

Nếu version Spring Test hỗ trợ `JsonCompareMode`, có thể dùng overload nhận enum thay cho boolean để biểu đạt ý định rõ hơn. Boolean overload phổ biến trong các phiên bản Spring trước đó vẫn thường được dùng trong test hiện có.

### Khi JSON mẫu chứa array

Strict comparison làm thứ tự array trở thành một phần của assertion:

```java
String expected = """
        {
          "items": [
            {"sku": "KB-01"},
            {"sku": "MS-02"}
          ]
        }
        """;

mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expected, true));
```

Nếu API không đảm bảo thứ tự, lenient comparison có thể phù hợp hơn. Tuy nhiên, lenient comparison vẫn so sánh nội dung các object; nó không có nghĩa là bỏ qua mọi khác biệt.

## Kết hợp JSONPath và JSON comparison

Hai cách kiểm tra có thể bổ sung cho nhau. Dùng `content().json(...)` để xác nhận cấu trúc tổng thể, sau đó dùng JSONPath cho các quy tắc nghiệp vụ quan trọng hoặc các field cần kiểm tra kiểu:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(content().json(expectedJson, false))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.total").isNumber())
        .andExpect(jsonPath("$.items").isNotEmpty());
```

Không nên lặp lại mọi field trong cả JSON mẫu và JSONPath. Hãy dùng JSON comparison cho cấu trúc tổng thể, còn JSONPath cho các điều kiện cần thông báo lỗi rõ hoặc có ý nghĩa nghiệp vụ riêng.

Nếu JSON response có timestamp, UUID hoặc giá trị sinh động, việc so sánh toàn bộ JSON có thể khiến test phụ thuộc dữ liệu không liên quan. Khi đó, JSONPath cho các field ổn định sẽ dễ bảo trì hơn; hoặc cố định clock/ID trong test để tạo response xác định.

## Kiểm tra response body trống

Một số endpoint hợp lệ trả status nhưng không có nội dung response. Ví dụ:

- `204 No Content` sau khi xóa thành công.
- `HEAD` trả headers tương ứng với GET nhưng không có body.
- Một endpoint trả `202 Accepted` mà không gửi payload.
- `304 Not Modified` trong luồng conditional request.

Với MockMvc, có thể kiểm tra body rỗng bằng `content().string("")`:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Nếu muốn kiểm tra ở mức byte, dùng `content().bytes(new byte[0])`:

```java
mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().bytes(new byte[0]));
```

Hai cách trên kiểm tra body không chứa ký tự hoặc byte nào. Nếu response chứa một dấu cách hoặc ký tự xuống dòng, body không còn rỗng và assertion sẽ thất bại. Đừng dùng `trim()` trong test nếu hợp đồng yêu cầu response thật sự không có byte nào.

### Body trống khác JSON null và JSON rỗng

Các response sau không tương đương:

| Body | Nội dung thực tế | Có phải body trống? |
|---|---|---|
| Không có byte nào | `""` | Có |
| JSON null | `null` | Không |
| JSON object rỗng | `{}` | Không |
| JSON array rỗng | `[]` | Không |
| JSON string rỗng | `""` (hai dấu nháy kép trong body) | Không |
| Chỉ có whitespace | ` ` hoặc newline | Không |

Nếu endpoint trả JSON object rỗng, hãy dùng `content().json("{}")` hoặc JSONPath phù hợp. Nếu endpoint trả JSON `null`, kiểm tra body bằng `content().string("null")`. Chỉ dùng `content().string("")` khi hợp đồng thực sự yêu cầu không có response body.

Không gọi `jsonPath(...)` hoặc `content().json(...)` trên response body trống. Các matcher đó cần tài liệu JSON hợp lệ để parse; với body rỗng, hãy kiểm tra trực tiếp bằng string hoặc bytes matcher.

## Kiểm tra body trống cho HEAD và status đặc biệt

Một endpoint `HEAD` không trả response body. Test có thể kiểm tra status và một số header:

```java
mockMvc.perform(head("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andExpect(content().string(""));
```

Với `204 No Content`, status là một phần của hợp đồng; test nên xác nhận cả status và body trống. Đừng chỉ assert body rỗng vì một lỗi controller có thể trả `200 OK` không có nội dung và vẫn làm assertion đó pass.

Với `304 Not Modified`, response body cũng không được gửi. Nếu test kiểm tra conditional GET, hãy xác nhận request gửi `If-None-Match` hoặc `If-Modified-Since` phù hợp, status `304` và body rỗng. Headers có thể vẫn chứa metadata cần thiết cho cache.

## Một ví dụ đầy đủ cho ba kiểu assertion

Giả sử API có ba endpoint:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable long id) {
        return orderService.get(id);
    }

    @GetMapping
    List<OrderSummary> list() {
        return orderService.list();
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

Test JSONPath cho một vài field:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.customer.email")
                .value("mai@example.test"));
```

Test so sánh toàn bộ JSON:

```java
String expected = """
        [
          {"id": 42, "status": "PAID"},
          {"id": 43, "status": "SHIPPED"}
        ]
        """;

mockMvc.perform(get("/api/orders"))
        .andExpect(status().isOk())
        .andExpect(content().json(expected, true));
```

Test body trống:

```java
mockMvc.perform(delete("/api/orders/{id}", 42L))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));
```

Mỗi test xác nhận một hợp đồng khác nhau: dữ liệu cụ thể trong JSON, cấu trúc của toàn response JSON và sự vắng mặt hoàn toàn của body.

## Lỗi thường gặp khi viết assertion

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JSONPath báo không tìm thấy path | Sai tên field, sai cấp object hoặc response không phải JSON | Kiểm tra response body và biểu thức bắt đầu từ `$` |
| Field có vẻ giống nhưng assertion thất bại | JSON number bị nhầm với string hoặc kiểu số khác nhau | Dùng `isNumber()`, matcher số hoặc ép kiểu tường minh khi cần |
| `doesNotExist()` thất bại với array rỗng | Path tồn tại nhưng giá trị là `[]` | Dùng `isEmpty()` hoặc so sánh với array rỗng |
| Không phân biệt được null và field vắng mặt | Dùng matcher chỉ kiểm tra giá trị | Kết hợp `hasJsonPath()` với `value(nullValue())` hoặc `doesNotHaveJsonPath()` |
| JSON comparison thất bại do field bổ sung | Đang dùng strict mode | Dùng lenient mode nếu API cho phép field mở rộng |
| JSON comparison thất bại do thứ tự array | Strict mode yêu cầu thứ tự khớp | Dùng lenient mode hoặc JSONPath với `containsInAnyOrder` nếu thứ tự không phải hợp đồng |
| `content().json(...)` không parse được | Thiếu JSONassert hoặc body không phải JSON hợp lệ | Bổ sung dependency và kiểm tra response body thực tế |
| JSONPath matcher không chạy được | Thiếu Jayway JSONPath trên test classpath | Bổ sung `json-path` dependency |
| Test body trống vẫn thất bại | Response có whitespace hoặc newline | Kiểm tra bytes/string thực tế và xác định hợp đồng có yêu cầu body tuyệt đối rỗng không |
| Test body trống pass dù endpoint sai | Chỉ assert body, không assert status | Kiểm tra status và headers cùng body |

## Chọn cách kiểm tra phù hợp

| Mục tiêu | Cách kiểm tra |
|---|---|
| Một field hoặc nested property | `jsonPath("$.customer.email").value(...)` |
| Field có đúng kiểu JSON | `isString()`, `isNumber()`, `isBoolean()`, `isArray()`, `isMap()` |
| Phần tử trong array | Index, wildcard hoặc filter expression |
| Array không phụ thuộc thứ tự | `containsInAnyOrder(...)` hoặc lenient JSON comparison |
| Toàn bộ JSON contract | `content().json(expected, true)` |
| JSON cho phép field bổ sung | `content().json(expected, false)` |
| Field null so với field không tồn tại | `hasJsonPath()`/`doesNotHaveJsonPath()` và matcher null |
| Body không có byte nào | `content().string("")` hoặc `content().bytes(new byte[0])` |

JSONPath giúp test tập trung vào các giá trị có ý nghĩa nghiệp vụ. So sánh JSON giúp bảo vệ cấu trúc response theo một mẫu rõ ràng. Assertion body trống xác nhận endpoint thực sự không gửi payload. Kết hợp đúng ba cách này giúp kiểm thử response Spring MVC chính xác mà không khiến test phụ thuộc vào những chi tiết định dạng JSON không thuộc hợp đồng API.
