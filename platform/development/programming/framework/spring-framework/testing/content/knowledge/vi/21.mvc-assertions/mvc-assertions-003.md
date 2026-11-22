# JSONPath để xác nhận trường và tập hợp

Khi kiểm thử một endpoint Spring MVC trả về JSON bằng MockMvc, chỉ xác nhận HTTP status là chưa đủ. Một response có thể trả về 200 OK nhưng vẫn thiếu trường, sai giá trị, sai cấu trúc object hoặc chứa một tập hợp không đúng. JSONPath giúp truy cập một phần cụ thể của tài liệu JSON để kiểm tra chính xác các trường và tập hợp đó.

Spring cung cấp các matcher JSONPath trong `MockMvcResultMatchers.jsonPath(...)`. Ta có thể kết hợp chúng với `andExpect(...)` để xác nhận giá trị của trường, kiểu dữ liệu, sự tồn tại của đường dẫn, kích thước mảng hoặc các phần tử thỏa điều kiện.

## 1. JSONPath là gì?

JSONPath là ngôn ngữ biểu thức dùng để truy vấn dữ liệu trong một cấu trúc JSON. Có thể hình dung JSONPath giống cách dùng CSS selector để chọn phần tử trong HTML, nhưng đối tượng được truy vấn ở đây là JSON object và array.

Xét response mẫu:

~~~json
{
  "orderId": 101,
  "status": "CONFIRMED",
  "customer": {
    "name": "Nguyễn An",
    "vip": true
  },
  "items": [
    {
      "sku": "BOOK-01",
      "name": "Spring Guide",
      "quantity": 2,
      "unitPrice": 120000
    },
    {
      "sku": "PEN-02",
      "name": "Notebook Pen",
      "quantity": 1,
      "unitPrice": 20000
    }
  ],
  "tags": ["new", "priority"],
  "total": 260000,
  "note": null
}
~~~

Một số JSONPath thường dùng:

| Biểu thức | Ý nghĩa | Kết quả trong JSON mẫu |
|---|---|---|
| `$` | Root, tức toàn bộ tài liệu JSON. | Toàn bộ object đơn hàng. |
| `$.orderId` | Trường orderId ở root. | `101`. |
| `$.customer.name` | Trường name bên trong customer. | `"Nguyễn An"`. |
| `$['orderId']` | Truy cập trường bằng cú pháp bracket. | `101`. |
| `$.items[0]` | Phần tử đầu tiên của mảng items. | Object BOOK-01. |
| `$.items[0].sku` | sku của phần tử đầu tiên. | `"BOOK-01"`. |
| `$.items[*].sku` | Trường sku của mọi phần tử trong mảng. | Danh sách BOOK-01, PEN-02. |
| `$.tags[1]` | Phần tử ở vị trí index 1. | `"priority"`. |
| `$.items[?(@.quantity > 1)]` | Các phần tử có quantity lớn hơn 1. | Object BOOK-01. |

Trong JSONPath, index mảng bắt đầu từ 0. Ký hiệu `@` trong biểu thức filter đại diện cho phần tử hiện tại đang được xét. Các biểu thức có thể được nối để đi sâu từ object root đến object con, rồi đến một trường hoặc phần tử trong array.

## 2. Dùng JSONPath trong MockMvc

Các static import thường dùng:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Một test cơ bản có thể kiểm tra status, Content-Type và một trường JSON:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.status").value("CONFIRMED"));
~~~

`jsonPath(expression)` tạo một `ResultMatcher`. Khi MockMvc thực thi response, matcher đọc nội dung JSON và đánh giá biểu thức đã cung cấp. Nếu biểu thức không tìm thấy dữ liệu hoặc giá trị không khớp, test thất bại ngay tại assertion tương ứng.

Nên kiểm tra status và Content-Type trước các trường dữ liệu để lỗi được diễn giải rõ ràng: request có đi đúng endpoint không, response có đúng loại nội dung không, rồi mới xác nhận cấu trúc JSON.

## 3. Xác nhận trường ở root và object lồng nhau

Với object JSON, dùng dot notation để đi qua các thuộc tính:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.status").value("CONFIRMED"))
    .andExpect(jsonPath("$.customer.name").value("Nguyễn An"))
    .andExpect(jsonPath("$.customer.vip").value(true));
~~~

Ví dụ:

- `$.orderId` đọc trường orderId tại root.
- `$.customer.name` đi vào object customer rồi đọc name.
- `$.customer.vip` đọc một giá trị boolean.

Nếu tên thuộc tính chứa dấu gạch ngang, dấu cách hoặc ký tự không thuận tiện cho dot notation, dùng bracket notation:

~~~json
{
  "order-id": "ORD-101",
  "metadata": {
    "source-system": "web-store"
  }
}
~~~

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$['order-id']").value("ORD-101"))
    .andExpect(jsonPath("$.metadata['source-system']").value("web-store"));
~~~

Bracket notation cũng hữu ích khi tên field được tạo động hoặc trùng với ký hiệu đặc biệt. Trong biểu thức JSONPath, tên key phải khớp với JSON response sau khi serialize, không nhất thiết trùng tên field Java nếu ứng dụng dùng Jackson annotation để đổi tên.

## 4. Xác nhận phần tử trong array

JSON array được truy cập bằng index:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
    .andExpect(jsonPath("$.items[0].quantity").value(2))
    .andExpect(jsonPath("$.items[1].sku").value("PEN-02"));
~~~

Index phù hợp khi thứ tự phần tử là một phần của hợp đồng API. Nếu thứ tự không được đảm bảo, assertion cố định `[0]` và `[1]` sẽ khiến test phụ thuộc vào chi tiết không ổn định. Khi đó nên kiểm tra toàn bộ tập hợp bằng wildcard và matcher.

### Wildcard để lấy trường từ mọi phần tử

Ký hiệu `[*]` chọn tất cả phần tử của array:

~~~java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[*].sku",
        contains("BOOK-01", "PEN-02")));
~~~

Biểu thức `$.items[*].sku` trả về tập hợp các giá trị sku. Matcher `contains` xác nhận cả giá trị lẫn thứ tự. Nếu chỉ quan tâm các giá trị có xuất hiện mà không quan tâm thứ tự, có thể dùng `containsInAnyOrder`:

~~~java
import static org.hamcrest.Matchers.containsInAnyOrder;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items[*].sku",
        containsInAnyOrder("PEN-02", "BOOK-01")));
~~~

### Kiểm tra kích thước tập hợp

Có thể kiểm tra array có đúng số phần tử:

~~~java
import static org.hamcrest.Matchers.hasSize;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").value(hasSize(2)))
    .andExpect(jsonPath("$.tags").value(hasSize(2)));
~~~

Các matcher khác thường dùng:

~~~java
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.anyOf;
import static org.hamcrest.Matchers.startsWith;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.tags", hasItem("priority")))
    .andExpect(jsonPath("$.items[*].sku",
        everyItem(anyOf(startsWith("BOOK-"), startsWith("PEN-")))));
~~~

Ví dụ trên minh họa việc kiểm tra phần tử thuộc tập hợp và quy luật áp dụng cho mọi phần tử. Khi dùng matcher kết hợp, hãy chọn điều kiện phù hợp với dữ liệu thực tế của endpoint; không nên đưa quy tắc kiểm tra quá rộng khiến test vẫn pass khi response chứa dữ liệu sai.

## 5. Dùng filter để chọn phần tử theo điều kiện

Filter giúp chọn những phần tử thỏa điều kiện thay vì phụ thuộc vào vị trí của chúng. Cú pháp thường gặp:

~~~text
$.arrayName[?(@.field == 'value')]
~~~

Trong đó:

- `$.arrayName` chọn array cần truy vấn.
- `?` bắt đầu một filter expression.
- `@` đại diện cho từng phần tử đang được xét.
- `@.field` truy cập field của phần tử đó.

Ví dụ chỉ chọn sản phẩm có quantity lớn hơn 1:

~~~java
import static org.hamcrest.Matchers.contains;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.quantity > 1)].sku",
        contains("BOOK-01")
    ));
~~~

Có thể kiểm tra một phần tử theo SKU, rồi xác nhận các field liên quan:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.sku == 'PEN-02')].quantity",
        contains(1)
    ));
~~~

Một số toán tử thường dùng trong filter:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `==` | Bằng | `@.status == 'ACTIVE'` |
| `!=` | Khác | `@.status != 'CANCELLED'` |
| `>` | Lớn hơn | `@.quantity > 1` |
| `>=` | Lớn hơn hoặc bằng | `@.price >= 100` |
| `<` | Nhỏ hơn | `@.quantity < 10` |
| `<=` | Nhỏ hơn hoặc bằng | `@.price <= 500` |
| `&&` | Đồng thời thỏa hai điều kiện | `@.active == true && @.quantity > 0` |
| `||` | Thỏa ít nhất một điều kiện | `@.status == 'NEW' || @.status == 'PAID'` |

Ví dụ kết hợp hai điều kiện:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath(
        "$.items[?(@.quantity > 0 && @.unitPrice >= 100000)].sku",
        contains("BOOK-01")
    ));
~~~

Filter đặc biệt hữu ích với collection mà thứ tự không được đảm bảo. Nó giúp test mô tả điều kiện nghiệp vụ của phần tử, ví dụ tìm dòng hàng có SKU cụ thể hoặc tìm tất cả phần tử đang ở trạng thái ACTIVE.

Lưu ý: JSONPath trong Spring MockMvc dựa trên thư viện Jayway JsonPath. Các biểu thức nâng cao có thể phụ thuộc phiên bản thư viện và JSON provider được dùng. Hãy ưu tiên cú pháp cơ bản, dễ đọc; với filter phức tạp, giữ test nhỏ và kiểm tra rằng biểu thức phù hợp với phiên bản dependency của dự án.

## 6. Xác nhận tập hợp rỗng, thiếu phần tử và giá trị null

Ba tình huống này khác nhau:

1. Field không có trong JSON.
2. Field có trong JSON và giá trị là `null`.
3. Field có trong JSON và là một collection rỗng `[]`.

Ví dụ:

~~~json
{
  "note": null,
  "tags": [],
  "status": "PENDING"
}
~~~

Spring cung cấp các matcher khác nhau để kiểm tra đường dẫn:

| Matcher | Ý nghĩa |
|---|---|
| `exists()` | Đường dẫn có giá trị khác null. |
| `hasJsonPath()` | Đường dẫn tồn tại, kể cả khi giá trị là null. |
| `doesNotExist()` | Không có giá trị khác null tại đường dẫn; trường không tồn tại hoặc null đều thỏa. |
| `doesNotHaveJsonPath()` | Đường dẫn hoàn toàn không tồn tại, kể cả trường hợp giá trị null. |

Ví dụ:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.status").exists())
    .andExpect(jsonPath("$.note").hasJsonPath())
    .andExpect(jsonPath("$.note").doesNotExist())
    .andExpect(jsonPath("$.missingField").doesNotHaveJsonPath())
    .andExpect(jsonPath("$.tags").isArray())
    .andExpect(jsonPath("$.tags").value(hasSize(0)));
~~~

Trong ví dụ, `note` có mặt trong JSON nhưng giá trị null. Vì vậy `hasJsonPath()` đúng, `exists()` không đúng và `doesNotExist()` đúng. Trường `missingField` không xuất hiện, nên `doesNotHaveJsonPath()` đúng.

Nếu nghiệp vụ yêu cầu phân biệt rõ null với thiếu field, hãy dùng `hasJsonPath()` và `doesNotHaveJsonPath()` theo đúng ý nghĩa. Không dùng `doesNotExist()` để chứng minh một key hoàn toàn không xuất hiện, vì matcher này cũng chấp nhận giá trị null.

Đối với collection rỗng, field vẫn tồn tại và có giá trị là array. Có thể kết hợp `isArray()` với `hasSize(0)` để xác nhận đúng cả kiểu dữ liệu lẫn số lượng phần tử.

## 7. Xác nhận kiểu dữ liệu

JSON có các kiểu object, array, string, number, boolean và null. Spring cung cấp các matcher kiểu dữ liệu cho JSONPath:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.orderId").isNumber())
    .andExpect(jsonPath("$.status").isString())
    .andExpect(jsonPath("$.customer").isMap())
    .andExpect(jsonPath("$.customer.vip").isBoolean())
    .andExpect(jsonPath("$.items").isArray());
~~~

Các matcher này hữu ích khi hợp đồng API yêu cầu kiểu dữ liệu cụ thể. Ví dụ, một field quantity phải là JSON number; nếu backend vô tình serialize nó thành chuỗi `"2"`, kiểm tra giá trị theo cách lỏng lẻo có thể không thể hiện đầy đủ lỗi kiểu dữ liệu.

Có thể kết hợp kiểm tra kiểu và giá trị:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.customer.vip").isBoolean())
    .andExpect(jsonPath("$.customer.vip").value(true))
    .andExpect(jsonPath("$.total").isNumber())
    .andExpect(jsonPath("$.total").value(260000));
~~~

Các giá trị `false`, `0` và chuỗi rỗng vẫn là giá trị tồn tại. Không nhầm chúng với field thiếu hoặc null:

~~~java
mockMvc.perform(get("/settings"))
    .andExpect(jsonPath("$.enabled").exists())
    .andExpect(jsonPath("$.enabled").value(false))
    .andExpect(jsonPath("$.retryCount").exists())
    .andExpect(jsonPath("$.retryCount").value(0))
    .andExpect(jsonPath("$.description").exists())
    .andExpect(jsonPath("$.description").value(""));
~~~

## 8. Xác nhận root array và collection lồng nhau

Không phải response JSON nào cũng bắt đầu bằng object. Một endpoint có thể trả về trực tiếp một array:

~~~json
[
  {"id": 1, "name": "An"},
  {"id": 2, "name": "Bình"}
]
~~~

Khi root là array, dùng `$[index]` hoặc `$[*]`:

~~~java
mockMvc.perform(get("/customers"))
    .andExpect(jsonPath("$").isArray())
    .andExpect(jsonPath("$").value(hasSize(2)))
    .andExpect(jsonPath("$[0].id").value(1))
    .andExpect(jsonPath("$[*].name",
        contains("An", "Bình")));
~~~

Với collection lồng nhau, nối các cấp array/object:

~~~json
{
  "groups": [
    {
      "name": "A",
      "members": [
        {"id": 10, "active": true},
        {"id": 11, "active": false}
      ]
    },
    {
      "name": "B",
      "members": [
        {"id": 20, "active": true}
      ]
    }
  ]
}
~~~

~~~java
mockMvc.perform(get("/groups"))
    .andExpect(jsonPath("$.groups[0].members[0].id").value(10))
    .andExpect(jsonPath("$.groups[*].name",
        contains("A", "B")))
    .andExpect(jsonPath("$.groups[1].members").value(hasSize(1)));
~~~

Đường dẫn có index phù hợp để kiểm tra cấu trúc cố định hoặc thứ tự có ý nghĩa. Wildcard phù hợp khi muốn xác nhận một thuộc tính trên tất cả phần tử của collection.

## 9. Kết hợp JSONPath với Hamcrest

MockMvc cho phép truyền Hamcrest matcher vào JSONPath để kiểm tra linh hoạt hơn so với so sánh một giá trị đơn lẻ.

Một số matcher hữu ích:

| Matcher | Mục đích |
|---|---|
| `is(value)` | So sánh giá trị. |
| `not(value)` | Xác nhận giá trị khác một giá trị cụ thể. |
| `notNullValue()` | Xác nhận không null. |
| `hasSize(n)` | Xác nhận kích thước collection. |
| `hasItem(value)` | Xác nhận collection chứa phần tử. |
| `contains(a, b)` | Xác nhận các phần tử theo đúng thứ tự. |
| `containsInAnyOrder(a, b)` | Xác nhận các phần tử không phụ thuộc thứ tự. |
| `greaterThan(n)` | Xác nhận số lớn hơn ngưỡng. |
| `lessThan(n)` | Xác nhận số nhỏ hơn ngưỡng. |
| `startsWith(text)` | Xác nhận chuỗi bắt đầu bằng đoạn text. |
| `everyItem(matcher)` | Xác nhận mọi phần tử đều thỏa matcher. |

Ví dụ:

~~~java
import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.notNullValue;
import static org.hamcrest.Matchers.startsWith;

mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.status", not("CANCELLED")))
    .andExpect(jsonPath("$.customer.name", notNullValue()))
    .andExpect(jsonPath("$.total", greaterThan(0)))
    .andExpect(jsonPath("$.items[*].sku", hasItem(startsWith("BOOK-"))));
~~~

Với matcher dạng collection, hãy nhớ JSONPath wildcard thường tạo ra một danh sách kết quả. Vì thế, matcher được áp dụng lên danh sách các giá trị được chọn, không phải lên từng object gốc. Nếu muốn kiểm tra từng object, hãy chọn trường phù hợp hoặc dùng filter expression.

## 10. Kiểm tra số và kiểu Java

Giá trị number trong JSON có thể được ánh xạ sang kiểu Java khác nhau tùy JSON provider và giá trị cụ thể. Ví dụ số nguyên nhỏ thường được đọc thành Integer, còn số thập phân có thể thành Double. Vì vậy, assertion số nên thể hiện rõ điều cần xác nhận:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(jsonPath("$.total").value(260000))
    .andExpect(jsonPath("$.items[0].unitPrice").value(120000));
~~~

Nếu kiểm tra số thập phân theo một khoảng dung sai, dùng matcher số:

~~~java
import static org.hamcrest.Matchers.closeTo;

mockMvc.perform(get("/products/1"))
    .andExpect(jsonPath("$.rating", closeTo(4.5, 0.01)));
~~~

Nếu cần ép kiểu Java cụ thể trước khi matcher so sánh, Spring cung cấp overload nhận target type:

~~~java
import java.math.BigDecimal;
import static org.hamcrest.Matchers.comparesEqualTo;

mockMvc.perform(get("/products/1"))
    .andExpect(jsonPath(
        "$.price",
        comparesEqualTo(new BigDecimal("125000.00")),
        BigDecimal.class
    ));
~~~

Overload có target type giúp chuyển kết quả JSONPath về kiểu mong muốn trước khi áp dụng matcher. Điều này hữu ích khi cần so sánh BigDecimal chính xác hoặc khi kiểu số mặc định của JSON provider không trùng với kiểu mong đợi trong test.

Không nên dùng so sánh chuỗi cho mọi giá trị số, ví dụ so sánh `"260000"` với một JSON number `260000`. JSON string và JSON number là hai kiểu khác nhau; test nên giữ đúng kiểu của hợp đồng API.

## 11. JSONPath và kiểm tra toàn bộ JSON

JSONPath phù hợp khi chỉ cần xác nhận một số trường hoặc một phần collection. Nếu cần xác nhận toàn bộ cấu trúc response, MockMvc còn cung cấp `content().json(...)`.

Ví dụ:

~~~java
mockMvc.perform(get("/health"))
    .andExpect(status().isOk())
    .andExpect(content().json("""
        {
          "status": "UP",
          "database": "UP"
        }
        """));
~~~

So sánh toàn bộ JSON hữu ích khi response nhỏ và hợp đồng yêu cầu các trường phải xuất hiện cùng cấu trúc cụ thể. JSONPath phù hợp hơn khi response lớn, có nhiều trường biến động hoặc chỉ một vài thuộc tính là quan trọng với test.

Hai cách có thể kết hợp:

~~~java
mockMvc.perform(get("/orders/101"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value(101))
    .andExpect(jsonPath("$.items").isArray())
    .andExpect(jsonPath("$.items").value(hasSize(2)));
~~~

Không nên dùng JSONPath để lặp lại mọi field nếu mục tiêu thật sự là xác nhận nguyên response. Ngược lại, không nên snapshot toàn bộ JSON nếu test chỉ cần xác nhận một vài hành vi và response có nhiều metadata thay đổi theo thời gian.

## 12. Một ví dụ test tổng hợp

Giả sử endpoint `GET /orders/{id}` trả về object đơn hàng như JSON mẫu ở đầu bài. Test có thể kiểm tra status, field lồng nhau, kiểu dữ liệu, array, filter và giá trị null:

~~~java
import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderWithExpectedFieldsAndItems() throws Exception {
        mockMvc.perform(get("/orders/{id}", 101))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.orderId").value(101))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$.customer.name").value("Nguyễn An"))
            .andExpect(jsonPath("$.customer.vip").value(true))
            .andExpect(jsonPath("$.items").isArray())
            .andExpect(jsonPath("$.items").value(hasSize(2)))
            .andExpect(jsonPath("$.items[*].sku",
                contains("BOOK-01", "PEN-02")))
            .andExpect(jsonPath(
                "$.items[?(@.quantity > 1)].sku",
                contains("BOOK-01")
            ))
            .andExpect(jsonPath("$.total").value(260000))
            .andExpect(jsonPath("$.note").hasJsonPath())
            .andExpect(jsonPath("$.note").doesNotExist());
    }
}
~~~

Test này minh họa nhiều loại assertion trên cùng một response. Trong dự án thực tế, lớp test cần được cấu hình để có MockMvc, chẳng hạn dùng `@WebMvcTest(OrderController.class)` hoặc cấu hình MockMvc phù hợp với loại test đang viết. Nếu dùng `@WebMvcTest`, các dependency service của controller cần được mock hoặc import theo cấu hình ứng dụng.

## 13. Lỗi thường gặp khi viết JSONPath assertion

### Quên ký hiệu root `$`

Biểu thức thường bắt đầu từ root:

~~~java
jsonPath("$.customer.name")
~~~

Nếu bỏ root hoặc viết sai đường dẫn, matcher có thể không tìm được dữ liệu.

### Dùng nhầm index bắt đầu từ 1

Array JSON đánh index từ 0. `$.items[0]` là phần tử đầu tiên, `$.items[1]` là phần tử thứ hai.

### Dùng index khi thứ tự không phải hợp đồng

Nếu API không cam kết thứ tự collection, kiểm tra `[0]` và `[1]` dễ tạo test chập chờn khi dữ liệu được sắp xếp khác. Hãy dùng wildcard, filter hoặc matcher không phụ thuộc thứ tự.

### Nhầm field null với field không tồn tại

`doesNotExist()` chấp nhận cả field không có và field có giá trị null. Nếu cần chứng minh field không xuất hiện, dùng `doesNotHaveJsonPath()`. Nếu cần xác nhận field hiện diện kể cả null, dùng `hasJsonPath()`.

### Chỉ kiểm tra số lượng mà không kiểm tra nội dung

`hasSize(2)` chỉ xác nhận có hai phần tử. Nó không chứng minh đó là hai phần tử đúng. Khi hợp đồng yêu cầu nội dung cụ thể, kết hợp kiểm tra size với `contains`, `containsInAnyOrder`, `hasItem` hoặc filter.

### Chỉ kiểm tra giá trị mà bỏ qua kiểu

JSON number và JSON string là khác nhau. Nếu API yêu cầu number, hãy thêm `isNumber()` hoặc assertion kiểu phù hợp; nếu yêu cầu boolean, xác nhận bằng `isBoolean()`.

### Viết JSONPath quá phức tạp

Một biểu thức dài kết hợp nhiều filter có thể khó đọc và khó chẩn đoán khi lỗi. Chia nó thành nhiều assertion nhỏ hoặc kiểm tra các phần tử bằng những biểu thức đơn giản hơn. Mỗi assertion nên thể hiện một điều kiện có ý nghĩa với hợp đồng API.

### Nhầm JSONPath với tên thuộc tính Java

JSONPath truy vấn JSON sau serialization. Nếu Jackson đổi tên field bằng `@JsonProperty`, biểu thức phải dùng tên đã xuất hiện trong response JSON, không phải tên field Java.

## 14. Cách chọn assertion phù hợp

Khi xác nhận kết quả MVC, hãy bắt đầu từ cấu trúc JSON thực tế và câu hỏi mà test cần trả lời:

1. Dùng `$.field` để xác nhận field ở root.
2. Dùng `$.parent.child` hoặc bracket notation để truy cập object lồng nhau và key đặc biệt.
3. Dùng `$[0]`, `$.items[0]` khi vị trí trong array là một phần của hợp đồng.
4. Dùng `[*]` và Hamcrest matcher khi cần kiểm tra toàn bộ collection.
5. Dùng filter `[?(@.field == value)]` để tìm phần tử theo điều kiện.
6. Dùng `exists()`, `hasJsonPath()`, `doesNotExist()` và `doesNotHaveJsonPath()` để phân biệt giá trị khác null, null và đường dẫn không tồn tại.
7. Dùng `isArray()`, `isMap()`, `isString()`, `isNumber()` và `isBoolean()` để xác nhận kiểu dữ liệu.
8. Dùng `content().json(...)` khi cần xác nhận toàn bộ response JSON nhỏ và ổn định.

JSONPath giúp test MockMvc tập trung vào dữ liệu mà client thực sự nhận được sau khi Spring MVC xử lý và serialize response. Khi chọn đúng đường dẫn, đúng matcher và đúng mức độ kiểm tra, test sẽ phát hiện được cả lỗi về giá trị, cấu trúc, kiểu dữ liệu lẫn nội dung của collection.
