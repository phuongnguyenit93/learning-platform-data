# Query lặp, danh sách tham số và quy ước tuần tự hóa

Một URI như `/orders?status=PAID&status=SHIPPED` có hai lần xuất hiện của key `status`. Đó có thể là cách biểu diễn một danh sách hợp lệ. Trong khi đó, `/orders?page=0&page=1` lại có hai giá trị cạnh tranh cho một tham số phân trang vốn chỉ được nhận một giá trị. Chỉ nhìn thấy key lặp chưa đủ để quyết định request đúng hay sai: quyết định phải dựa vào hợp đồng của từng tham số.

Trong chương **Thiết kế URI** của module `INTEGRATION_API_REST`, bài này tập trung vào cách biến ý định lọc, sắp xếp và phân trang thành query có thể được client, Java/Spring, gateway và công cụ OpenAPI hiểu thống nhất. Mục tiêu là thiết kế một hợp đồng dữ liệu rõ ràng, có thể triển khai và kiểm thử được.

Sau bài học, bạn cần có khả năng:

- Chọn cách biểu diễn danh sách và phân biệt nó với tham số đơn bị lặp.
- Quy định ý nghĩa của thứ tự, phần tử trùng, tham số vắng mặt và giá trị rỗng.
- Khai báo đúng quy ước tuần tự hóa trong OpenAPI.
- Tiếp nhận toàn bộ giá trị tại server, kiểm tra hợp đồng rồi mới chuyển thành bộ lọc nghiệp vụ.
- Nhận diện tác động của quy ước query đến cache, chữ ký request và xử lý lỗi.

## 1. Query không tự mang kiểu dữ liệu của ứng dụng

Xét URI sau:

```text
/orders?status=PAID&status=SHIPPED&sort=-createdAt&sort=id&page=0
```

Ở mức cú pháp URI, query là phần sau dấu `?`, trước fragment nếu có. URI tổng quát không bắt buộc query phải là một map, một mảng hay một tài liệu JSON. Cách dùng `&` để ngăn các cặp và `=` để ngăn tên với giá trị là quy ước phổ biến của ứng dụng và các thư viện web.

Theo quy ước đó, nên hình dung đầu vào của request là một **chuỗi các cặp tên–giá trị**, có thể chứa cùng một tên nhiều lần:

```text
("status", "PAID")
("status", "SHIPPED")
("sort", "-createdAt")
("sort", "id")
("page", "0")
```

Một cấu trúc như `Map<String, String>` không biểu diễn đủ đầu vào này. Nếu thư viện tự giữ giá trị đầu hoặc cuối, server có thể mất thông tin trước khi kiểm tra được request.

Cấu trúc như `MultiValueMap<String, String>` phù hợp hơn khi cần giữ danh sách giá trị của từng key. Tuy nhiên, nó không có nghĩa là hợp đồng phải cho phép mọi key xuất hiện nhiều lần. Parser vẫn phải phân biệt:

| Tham số | Kiểu theo hợp đồng | Ví dụ hợp lệ | Khi key lặp |
|---|---|---|---|
| `status` | Danh sách trạng thái | `status=PAID&status=SHIPPED` | Được phép trong giới hạn |
| `sort` | Danh sách tiêu chí có thứ tự | `sort=-createdAt&sort=id` | Được phép; giữ thứ tự |
| `page` | Một số nguyên | `page=0` | Từ chối |
| `size` | Một số nguyên | `size=20` | Từ chối |

**Key lặp**, **giá trị trùng** và **thứ tự phần tử** là ba vấn đề khác nhau. Cần có quyết định riêng cho từng vấn đề.

## 2. Những cách phổ biến để tuần tự hóa danh sách

Một danh sách logic:

```json
["PAID", "SHIPPED"]
```

có thể được đưa vào query bằng nhiều cách:

| Cách biểu diễn | Query minh họa | Điều phải làm rõ |
|---|---|---|
| Lặp cùng key | `status=PAID&status=SHIPPED` | Server phải đọc được nhiều giá trị |
| Phân cách bằng dấu phẩy | `status=PAID,SHIPPED` | Dấu phẩy trong chính một phần tử được xử lý thế nào |
| Phân cách bằng dấu cách | `status=PAID%20SHIPPED` | Khoảng trắng là dữ liệu hay dấu phân cách |
| Phân cách bằng dấu gạch đứng | `status=PAID%7CSHIPPED` | Dấu `|` thuộc dữ liệu được biểu diễn thế nào |
| Key có cặp ngoặc | `status%5B%5D=PAID&status%5B%5D=SHIPPED` | `status[]` chỉ có ý nghĩa mảng nếu framework hoặc hợp đồng quy định |
| Key có chỉ số | `status%5B0%5D=PAID&status%5B1%5D=SHIPPED` | Quy tắc chỉ số, lỗ trống và phần tử trùng chỉ số |
| JSON trong một giá trị | `status=%5B%22PAID%22%2C%22SHIPPED%22%5D` | Cần bộ tuần tự hóa và parser JSON được khai báo rõ |

Không có quy tắc HTTP tổng quát nào biến mọi dạng trên thành cùng một mảng. Nếu backend đang đọc key `status`, key có tên thực tế là `status[]` có thể bị coi là tham số khác.

Với danh sách đơn giản, **lặp cùng key thường là lựa chọn dễ duy trì**. Mỗi giá trị có ranh giới rõ ràng, không cần chọn thêm một dấu phân cách bên trong giá trị, và có thể mô tả trực tiếp bằng OpenAPI.

Điều đó không có nghĩa là hệ thống cũ đang dùng dấu phẩy bắt buộc phải đổi. Với một tập giá trị đóng như mã trạng thái, dấu phẩy có thể phù hợp nếu hợp đồng và các công cụ đã hỗ trợ nhất quán. Điều quan trọng là chọn và công bố một quy ước chính thức.

### 2.1. Không tự trộn nhiều quy ước

Nếu hợp đồng chọn query lặp, request này có hai phần tử:

```text
/orders?status=PAID,SHIPPED&status=CANCELLED
```

```text
["PAID,SHIPPED", "CANCELLED"]
```

Nó không tự động có ba phần tử. Nếu `PAID,SHIPPED` không phải một giá trị enum hợp lệ, server phải trả lỗi theo hợp đồng.

Việc âm thầm hỗ trợ cả query lặp lẫn dấu phẩy khiến mỗi client có thể tạo ra cách hiểu khác nhau. Nếu cần giai đoạn chuyển đổi tương thích, phải quy định rõ cách phát hiện định dạng, trường hợp mơ hồ, thời hạn hỗ trợ và cách kiểm thử từng dạng.

### 2.2. Dấu phẩy trong phần tử là một vấn đề thực sự

Giả sử một tag có nội dung `research,design`. Với query lặp, nó là một phần tử:

```text
/articles?tag=research%2Cdesign&tag=java
```

Nếu chọn danh sách phân cách bằng dấu phẩy, cần phân biệt dấu phẩy dùng làm dấu phân cách với dấu phẩy thuộc nội dung tag. Percent-encoding không tự giải quyết vấn đề nếu thư viện đã giải mã toàn bộ giá trị rồi mới tách bằng `,`.

Một parser hiểu định dạng có thể cần giữ thông tin ở dạng thô trước khi giải mã, hoặc hợp đồng phải giới hạn tập ký tự của từng phần tử. Khi chuỗi tự do có thể chứa dấu phân cách, query lặp thường giúp tránh được lớp mơ hồ này.

## 3. Phân biệt vắng mặt, rỗng và danh sách rỗng

Các request sau không mặc nhiên tương đương:

```text
/orders
/orders?status=
/orders?status
/orders?status=PAID&status=
/orders?status=[]
```

Một quy ước rõ ràng cho bộ lọc trạng thái có thể là:

| Đầu vào | Cách hiểu được chọn |
|---|---|
| Không có `status` | Không áp dụng bộ lọc trạng thái |
| `status=PAID` | Lọc theo trạng thái `PAID` |
| `status=PAID&status=SHIPPED` | Nhận một trong hai trạng thái |
| `status=` | Lỗi: phần tử rỗng |
| `status` không có `=` | Lỗi nếu parser tiếp nhận dưới dạng giá trị rỗng |
| `status=PAID&status=` | Lỗi toàn bộ request |
| `status=[]` | Lỗi enum; đây là chuỗi `[]`, không phải mảng rỗng |

Dạng `key` không có `=` có thể được các thư viện xử lý khác nhau. Vì vậy, cần kiểm tra hành vi thực tế của stack triển khai và công bố rằng tham số bộ lọc phải có giá trị hợp lệ.

Đối với endpoint trên, danh sách không có phần tử được biểu diễn bằng cách **bỏ hẳn key**. Không có một cú pháp danh sách rỗng chung cho mọi loại query.

Có nghiệp vụ mà danh sách rỗng phải có nghĩa “không kết quả”, khác với “không lọc”. Khi đó, cần một thiết kế biểu đạt được sự khác biệt này, chẳng hạn một cấu trúc tìm kiếm trong request body có hợp đồng riêng. Không nên tự gán nghĩa đặc biệt cho chuỗi `[]` nếu client chưa được thông báo.

## 4. Phần tử trùng, thứ tự và phép kết hợp bộ lọc

### 4.1. Danh sách dùng như tập hợp

Với bộ lọc trạng thái:

```text
status=PAID&status=SHIPPED
status=SHIPPED&status=PAID
status=PAID&status=PAID&status=SHIPPED
```

Hợp đồng có thể quy định cả ba cho cùng điều kiện nghiệp vụ:

```text
order.status thuộc tập {PAID, SHIPPED}
```

Ở đây, thứ tự không ảnh hưởng kết quả và phần tử trùng được loại bỏ sau khi kiểm tra tính hợp lệ. Nếu chọn từ chối phần tử trùng thay vì loại bỏ, cũng phải ghi rõ và phản ánh vào kiểm thử.

Trong bài này, bộ lọc `status` chấp nhận giá trị trùng và loại bỏ chúng. Giới hạn số phần tử vẫn áp dụng trên **đầu vào trước khi loại trùng**, để request rất dài không trở thành hợp lệ chỉ vì cuối cùng còn một giá trị.

### 4.2. Danh sách có thứ tự

Với sắp xếp:

```text
sort=-createdAt&sort=id
```

nghĩa là sắp xếp theo `createdAt` giảm dần, rồi theo `id` tăng dần khi giá trị `createdAt` bằng nhau.

Đổi thứ tự:

```text
sort=id&sort=-createdAt
```

là đổi độ ưu tiên sắp xếp. Không được sắp xếp lại các giá trị `sort` chỉ để tạo URL trông gọn hoặc để chuẩn hóa cache.

Hợp đồng phải yêu cầu client, proxy và server giữ thứ tự các giá trị của danh sách này. Nếu hạ tầng không bảo đảm điều đó, cần chọn một cách biểu diễn thứ tự khác và kiểm thử toàn bộ đường đi của request.

Thêm một khóa phân xử như `id` giúp kết quả có thứ tự xác định khi các giá trị khác bằng nhau. Việc này không loại bỏ hiện tượng dữ liệu dịch chuyển giữa các trang nếu dùng phân trang offset trong lúc dữ liệu thay đổi.

### 4.3. Danh sách không tự quyết định AND hay OR

Hai URI có hình thức tương tự nhưng có thể có ngữ nghĩa khác:

```text
/orders?status=PAID&status=SHIPPED
/articles?tag=java&tag=spring
```

Một API có thể định nghĩa:

- `status`: đơn hàng có một trong các trạng thái, tức OR trong cùng danh sách.
- `tag`: bài viết phải có đủ các tag, tức AND trong cùng danh sách.
- Giữa các nhóm bộ lọc khác nhau: kết hợp bằng AND.

Cách tuần tự hóa chỉ mô tả cách truyền giá trị. Phép logic là một phần khác của hợp đồng. Không được suy ra AND hay OR chỉ từ việc key lặp.

## 5. Percent-encoding và thứ tự phân tích query

Các ký tự có vai trò phân cách phải được mã hóa khi chúng thuộc về dữ liệu:

| Giá trị logic của một phần tử | Dạng trong query |
|---|---|
| `C++` | `C%2B%2B` |
| `a&b` | `a%26b` |
| `x=y` | `x%3Dy` |
| `research,design` | `research%2Cdesign` |
| `hello world` | `hello%20world` |
| `50%` | `50%25` |
| `part#2` | `part%232` |

Một dấu `&` chưa được mã hóa có thể bắt đầu cặp query mới. Một dấu `#` chưa được mã hóa bắt đầu fragment; fragment không được gửi đến server như một phần của HTTP request target.

### 5.1. Dấu cộng cần được chú ý

Một số bộ mã hóa và giải mã theo quy ước `application/x-www-form-urlencoded` dùng `+` để biểu diễn dấu cách. Trong cú pháp URI tổng quát, dấu `+` không tự mang nghĩa dấu cách.

Để truyền chuỗi `C++` một cách rõ ràng qua các stack thường dùng quy ước form, client nên tạo:

```text
/articles?tag=C%2B%2B
```

Nếu client gửi thẳng `tag=C++`, một parser theo quy ước form có thể trả về `C` kèm hai dấu cách. Không nên sửa lỗi này bằng cách trim tại server: dữ liệu gốc đã bị thay đổi.

### 5.2. Phân tích ranh giới trước khi giải mã dữ liệu

Theo quy ước cặp query đang dùng, trình tự khái niệm là:

```text
Query thô
    -> tách các cặp tại dấu & thô
    -> tách tên và giá trị tại dấu = thô đầu tiên
    -> giải mã từng thành phần theo đúng quy ước và UTF-8
    -> gom các giá trị theo key, giữ thứ tự cần thiết
    -> kiểm tra kiểu dữ liệu và quy tắc nghiệp vụ
```

Không giải mã toàn bộ query rồi mới tách tại `&`, vì `%26` trong dữ liệu sẽ bị biến nhầm thành dấu phân cách. Cũng không gọi giải mã lần hai trên giá trị mà framework đã giải mã.

Ví dụ, `%2526` qua một lần giải mã trở thành chuỗi `%26`. Nếu ứng dụng tự giải mã thêm, nó trở thành `&` và thay đổi nội dung đầu vào ngoài hợp đồng.

Trong Java/Spring, thông thường nên dùng parser của framework và nhận dữ liệu đã được giải mã. Không viết lại parser query bằng `split("&")` hoặc gọi `URLDecoder` trên mọi giá trị nhận được từ `@RequestParam`.

## 6. Một hợp đồng cụ thể cho `GET /orders`

Ví dụ xuyên suốt:

```http
GET /orders?status=PAID&status=SHIPPED&sort=-createdAt&sort=id&page=0&size=20 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Quy ước của endpoint:

| Tham số | Quy tắc |
|---|---|
| `status` | Query lặp; tối đa 8 phần tử đầu vào; giá trị thuộc `NEW`, `PAID`, `SHIPPED`, `CANCELLED` |
| Ngữ nghĩa `status` | OR giữa các giá trị; bỏ key nghĩa là không lọc; loại phần tử trùng |
| `sort` | Query lặp; tối đa 3 tiêu chí do client gửi; giữ nguyên thứ tự |
| Cú pháp `sort` | Tên trường để tăng dần, tiền tố `-` để giảm dần; cho phép `createdAt`, `totalAmount`, `id` |
| Trường lặp trong `sort` | Từ chối, kể cả `id` và `-id` cùng xuất hiện |
| Mặc định `sort` | `-createdAt`, rồi `id` |
| Khóa phân xử | Nếu client gửi `sort` mà chưa có trường `id`, server nối thêm `id` tăng dần |
| `page` | Tham số đơn; số nguyên thập phân từ 0 đến 1.000.000; mặc định 0 |
| `size` | Tham số đơn; số nguyên thập phân từ 1 đến 100; mặc định 20 |
| Key không được khai báo | Trả `400 Bad Request` theo chính sách của endpoint này |
| Giá trị rỗng hoặc chỉ có khoảng trắng | Không hợp lệ |
| Hoa/thường và khoảng trắng | Giá trị enum và tên trường phân biệt hoa/thường; không tự trim |

Giới hạn trang ở đây là một quyết định của ví dụ, không phải giới hạn của HTTP. Hệ thống thật cần chọn giới hạn dựa trên nghiệp vụ và khả năng truy vấn.

Các giá trị của `page` và `size` chỉ gồm chữ số ASCII. Hợp đồng này không nhận dấu `+`, dấu `-`, khoảng trắng hay phần thập phân. Có thể chấp nhận số có số 0 ở đầu và chuẩn hóa về giá trị số; nếu muốn cấm, phải bổ sung quy tắc và kiểm thử tương ứng.

Ví dụ:

```text
/orders?page=0&page=1       -> 400: page phải xuất hiện đúng một lần
/orders?page=0&page=0       -> 400: vẫn là tham số đơn bị lặp
/orders?status=paid         -> 400: enum không hợp lệ
/orders?status=PAID,SHIPPED -> 400: không dùng định dạng dấu phẩy
/orders?sort=-createdAt     -> hợp lệ; nối thêm id tăng dần
/orders?sort=id&sort=-id    -> 400: trùng trường sắp xếp
/orders?stats=PAID          -> 400: key không được hỗ trợ
```

Không nên làm cho tham số lọc cũng đồng thời trở thành cơ chế phân quyền. Ví dụ, nhận một `tenantId` từ query không đủ để cho phép truy cập tenant đó; server vẫn phải xác thực và kiểm tra quyền theo danh tính người gọi.

## 7. Mô tả bằng OpenAPI

Với query parameter dạng mảng trong OpenAPI 3, cặp cấu hình cần chú ý là `style` và `explode`:

| Cấu hình | Dạng query điển hình |
|---|---|
| `style: form`, `explode: true` | `status=PAID&status=SHIPPED` |
| `style: form`, `explode: false` | `status=PAID,SHIPPED` |
| `style: spaceDelimited`, `explode: false` | `status=PAID%20SHIPPED` |
| `style: pipeDelimited`, `explode: false` | `status=PAID%7CSHIPPED` |

Với query parameter, `form` là style mặc định; khi dùng `form`, `explode` mặc định là `true`. Dù vậy, ghi tường minh giúp người đọc và người sinh SDK nhận ra ngay lựa chọn của API.

`deepObject` dùng cho trường hợp biểu diễn đối tượng trong query theo quy ước tương ứng. Nó không phải công tắc tổng quát để mọi cấu trúc mảng lồng nhau tự có cách tuần tự hóa thống nhất.

Phần khai báo dưới đây mô tả các tham số của ví dụ. Nó là một đoạn trích cần đặt trong tài liệu OpenAPI đầy đủ:

```yaml
paths:
  /orders:
    get:
      summary: Liệt kê đơn hàng
      parameters:
        - name: status
          in: query
          required: false
          style: form
          explode: true
          description: >-
            OR giữa các trạng thái. Bỏ tham số nghĩa là không lọc.
            Không nhận phần tử rỗng. Nhận tối đa 8 giá trị đầu vào;
            phần tử trùng được loại bỏ trước khi truy vấn.
          schema:
            type: array
            minItems: 1
            maxItems: 8
            items:
              type: string
              enum: [NEW, PAID, SHIPPED, CANCELLED]
          example: [PAID, SHIPPED]
        - name: sort
          in: query
          required: false
          style: form
          explode: true
          description: >-
            Giữ thứ tự tiêu chí. Dấu - biểu thị giảm dần.
            Không nhận cùng một trường nhiều lần, dù khác chiều.
            Nếu chưa có trường id, server nối thêm id tăng dần.
          schema:
            type: array
            minItems: 1
            maxItems: 3
            default: [-createdAt, id]
            items:
              type: string
              pattern: '^-?(createdAt|totalAmount|id)$'
          example: [-createdAt, id]
        - name: page
          in: query
          required: false
          description: >-
            Một giá trị duy nhất, chỉ gồm chữ số ASCII;
            không nhận key lặp, kể cả khi các giá trị giống nhau.
          schema:
            type: integer
            minimum: 0
            maximum: 1000000
            default: 0
        - name: size
          in: query
          required: false
          description: >-
            Một giá trị duy nhất, chỉ gồm chữ số ASCII;
            không nhận key lặp, kể cả khi các giá trị giống nhau.
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Trang kết quả phù hợp với bộ lọc
        '400':
          description: Query không đúng hợp đồng
```

Không khai báo `uniqueItems: true` cho `status` nếu server cho phép gửi phần tử trùng rồi loại bỏ như ví dụ. Ngược lại, nếu hợp đồng từ chối phần tử trùng, ràng buộc này có thể diễn đạt một phần yêu cầu đó.

Schema và mô tả không tự bảo đảm tất cả hành vi runtime. Quy tắc “không lặp trường sắp xếp dù khác chiều”, “không nhận scalar bị lặp” và chính sách key lạ vẫn cần được thực thi trong ứng dụng hoặc lớp xác thực request phù hợp. Cần kiểm tra URL thực tế do SDK sinh ra, vì công cụ có thể có mức hỗ trợ khác nhau cho các kiểu tuần tự hóa.

## 8. Tiếp nhận và kiểm tra với Java/Spring

### 8.1. Giữ toàn bộ giá trị trước khi chuyển kiểu

Ví dụ sau dùng Java 17+ và kiểu `MultiValueMap` của Spring. Parser nhận các chuỗi đã được framework giải mã, rồi thực thi hợp đồng ở phần trước.

Việc đọc `page` và `size` dưới dạng danh sách chuỗi trước giúp phát hiện key lặp. Nếu bind ngay vào một kiểu số đơn, hành vi xử lý nhiều giá trị có thể phụ thuộc converter và cấu hình; không nên dùng hành vi ngầm đó làm hợp đồng API.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.util.MultiValueMap;
import org.springframework.web.server.ResponseStatusException;

public final class OrderQueryParser {
    private static final Set<String> KEYS =
            Set.of("status", "sort", "page", "size");
    private static final Set<String> SORT_FIELDS =
            Set.of("createdAt", "totalAmount", "id");

    public enum Status { NEW, PAID, SHIPPED, CANCELLED }

    public record SortTerm(String field, boolean descending) {}

    public record Criteria(
            List<Status> statuses,
            List<SortTerm> sort,
            int page,
            int size) {}

    public static Criteria parse(MultiValueMap<String, String> query) {
        for (String key : query.keySet()) {
            if (!KEYS.contains(key)) {
                throw bad("query", "Có tham số không được hỗ trợ");
            }
        }

        List<String> rawStatuses = many(query, "status", 8);
        Set<Status> statuses = new LinkedHashSet<>();
        for (String value : rawStatuses) {
            try {
                statuses.add(Status.valueOf(value));
            } catch (IllegalArgumentException ex) {
                throw bad("status", "Trạng thái không hợp lệ");
            }
        }

        List<String> rawSort = many(query, "sort", 3);
        if (!query.containsKey("sort")) {
            rawSort = List.of("-createdAt", "id");
        }

        List<SortTerm> sort = new ArrayList<>();
        Set<String> seenFields = new LinkedHashSet<>();
        for (String value : rawSort) {
            boolean descending = value.startsWith("-");
            String field = descending ? value.substring(1) : value;
            if (!SORT_FIELDS.contains(field)) {
                throw bad("sort", "Trường sắp xếp không hợp lệ");
            }
            if (!seenFields.add(field)) {
                throw bad("sort", "Không được lặp trường sắp xếp");
            }
            sort.add(new SortTerm(field, descending));
        }
        if (!seenFields.contains("id")) {
            sort.add(new SortTerm("id", false));
        }

        int page = singleInt(query, "page", 0, 0, 1_000_000);
        int size = singleInt(query, "size", 20, 1, 100);
        return new Criteria(
                List.copyOf(statuses), List.copyOf(sort), page, size);
    }

    private static List<String> many(
            MultiValueMap<String, String> query, String key, int maximum) {
        if (!query.containsKey(key)) {
            return List.of();
        }
        List<String> values = query.get(key);
        if (values == null || values.isEmpty() || values.size() > maximum) {
            throw bad(key, "Số lượng giá trị không hợp lệ");
        }
        for (String value : values) {
            if (value == null || value.isBlank()) {
                throw bad(key, "Không được để giá trị rỗng");
            }
        }
        return values;
    }

    private static int singleInt(
            MultiValueMap<String, String> query,
            String key, int fallback, int minimum, int maximum) {
        if (!query.containsKey(key)) {
            return fallback;
        }
        List<String> values = many(query, key, 1);
        String raw = values.get(0);
        if (!raw.matches("[0-9]+")) {
            throw bad(key, "Phải là số nguyên chỉ gồm chữ số ASCII");
        }
        final int value;
        try {
            value = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw bad(key, "Số nguyên vượt giới hạn biểu diễn");
        }
        if (value < minimum || value > maximum) {
            throw bad(key, "Giá trị ngoài khoảng cho phép");
        }
        return value;
    }

    private static ResponseStatusException bad(String key, String message) {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, key + ": " + message);
    }
}
```

Parser không trim giá trị. Chuỗi ` PAID ` bị từ chối khi chuyển enum; ` createdAt` bị từ chối vì không thuộc danh sách trường cho phép. Cả dấu phẩy lẫn cú pháp `status[]` cũng không được chuyển đổi ngầm.

Một controller có thể tiếp nhận query rồi chuyển tiêu chí đã kiểm tra xuống tầng nghiệp vụ:

```java
@GetMapping("/orders")
public OrderPage listOrders(@RequestParam MultiValueMap<String, String> query) {
    OrderQueryParser.Criteria criteria = OrderQueryParser.parse(query);
    return orderService.search(criteria);
}
```

Đây là đoạn tích hợp minh họa: `OrderPage` và `orderService` là kiểu dữ liệu và dịch vụ của ứng dụng, không phải thành phần do Spring cung cấp. Các annotation cần import từ `org.springframework.web.bind.annotation`.

Tầng truy vấn cần ánh xạ các trường được cho phép sang biểu thức ORM hoặc tên cột cố định. Không nối trực tiếp chuỗi `sort` từ request vào SQL, dù bước phân tích query đã tồn tại.

### 8.2. Lỗi cần có cấu trúc nhất quán

`ResponseStatusException` ở trên minh họa việc trả trạng thái 400. Hình dạng response thực tế còn phụ thuộc cấu hình xử lý lỗi của ứng dụng. Nếu API công bố một cấu trúc lỗi cụ thể, phải có exception handler hoặc cơ chế tương đương để tạo đúng cấu trúc đó.

Ví dụ hợp đồng lỗi theo kiểu Problem Details cho request có hai giá trị `page`:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
```

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Tham số page phải có đúng một giá trị.",
  "invalidParams": [
    {
      "name": "page",
      "reason": "multiple_values_not_allowed"
    }
  ]
}
```

`invalidParams` là phần mở rộng do API lựa chọn; client cần được biết schema và mã lỗi ổn định. Không giả định mọi framework tự tạo sẵn trường này.

Nếu query không đúng định dạng đầu vào, không nên trả `200` với danh sách rỗng để che lỗi. Danh sách rỗng có nghĩa request hợp lệ nhưng không tìm thấy dữ liệu. Đây là tình huống khác với request không thể được hiểu theo hợp đồng.

## 9. Tạo URI ở phía client

Client nên tạo query bằng thư viện URI thay vì nối chuỗi thủ công:

```java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
        .fromUriString("https://api.example.com/articles")
        .queryParam("tag", "{first}")
        .queryParam("tag", "{second}")
        .encode()
        .buildAndExpand(Map.of("first", "C++", "second", "a&b"))
        .toUri();

// https://api.example.com/articles?tag=C%2B%2B&tag=a%26b
```

Ở đây, dùng biến URI và gọi `encode()` trước khi mở rộng biến giúp mã hóa các ký tự dành riêng nằm trong giá trị. `articles` là ví dụ riêng cho danh sách tag dạng chuỗi tự do; nó không thêm `tag` vào hợp đồng `/orders`.

Với một danh sách, client thêm một query parameter cho mỗi phần tử và giữ thứ tự khi tham số đó có thứ tự. Khi danh sách rỗng được quy ước là “không lọc”, client bỏ key thay vì gửi `key=[]` hoặc `key=`.

Không mã hóa giá trị trước rồi lại đưa vào builder ở chế độ tiếp tục mã hóa. Ví dụ, truyền chuỗi đã mã hóa `C%2B%2B` như dữ liệu thô có thể khiến `%` thành `%25`, tạo ra `C%252B%252B`.

## 10. Cache và chuẩn hóa query

Hai URI có cùng kết quả nghiệp vụ không nhất thiết dùng chung cache entry:

```text
/orders?status=PAID&status=SHIPPED
/orders?status=SHIPPED&status=PAID
```

Cache có thể coi chúng là hai khóa khác nhau nếu chưa có quy tắc chuẩn hóa tương ứng. Một CDN cũng có thể được cấu hình chỉ dùng một số tham số cho cache key; cấu hình bỏ sót bộ lọc có thể trả nhầm dữ liệu cho request khác.

Với ví dụ này, nếu muốn chuẩn hóa, cần thiết kế chính sách nhất quán:

1. Phân tích và kiểm tra toàn bộ query trước, bao gồm việc từ chối scalar bị lặp.
2. Chuẩn hóa `status` theo tính chất tập hợp: loại trùng và sắp xếp theo một thứ tự đã chọn.
3. Giữ thứ tự các tiêu chí `sort` và áp dụng cùng quy tắc khóa phân xử.
4. Quyết định rõ có gộp giá trị mặc định với trường hợp bỏ tham số hay không.
5. Mã hóa lại bằng cùng một quy ước, đồng thời giữ chính sách cache và phân quyền phù hợp.

Không dùng một hàm “sort mọi cặp query theo key và value” cho tất cả endpoint. Nó có thể làm thay đổi ý nghĩa danh sách `sort`.

Header `Vary` mô tả sự phụ thuộc của response vào các request header. Nó không thay thế cấu hình sử dụng query parameter trong cache key. Với dữ liệu cá nhân hoặc dữ liệu cần xác thực, việc chuẩn hóa URI cũng không thay thế các chỉ thị cache và ranh giới truy cập thích hợp.

Nếu hệ thống ký request, client và server phải thống nhất dùng chuỗi thô hay một biểu diễn chuẩn hóa cụ thể, bao gồm key lặp, thứ tự, dấu cách và percent-encoding. Không tự chuẩn hóa thêm sau khi đã tính chữ ký theo một quy tắc khác.

## 11. Ngăn sự khác biệt giữa gateway và ứng dụng

Request sau có thể gây rắc rối nếu các lớp xử lý không thống nhất:

```text
/orders?size=20&size=100000
```

Ví dụ, gateway kiểm tra giá trị đầu tiên nhưng ứng dụng lại sử dụng giá trị cuối cùng. Kiểm tra giới hạn của gateway khi đó không mô tả đúng giá trị thực sự được xử lý. Đây là một dạng rủi ro do nhiều cách hiểu tham số HTTP, thường được gọi là HTTP parameter pollution.

Cách thiết kế phù hợp là:

- Khai báo key nào được phép lặp và key nào chỉ được có một giá trị.
- Bảo đảm các lớp có thể nhìn thấy đủ giá trị trước khi đưa ra quyết định.
- Từ chối scalar bị lặp thay vì chọn ngầm giá trị đầu hoặc cuối.
- Dùng cùng quy ước tuần tự hóa giữa tài liệu, gateway, server và SDK.
- Giới hạn số tham số, số phần tử, độ dài mỗi giá trị và tổng độ dài request target.

Parser minh họa giới hạn số phần tử và giá trị số. Giới hạn tổng request target và độ dài chuỗi vẫn cần cấu hình hoặc kiểm tra bổ sung ở HTTP server/gateway và ứng dụng phù hợp với triển khai.

Không có một giới hạn độ dài URL duy nhất áp dụng cho mọi browser, proxy và server. Một request có thể bị từ chối trước khi đi tới controller, chẳng hạn với `414 URI Too Long`, tùy giới hạn và lớp phát hiện lỗi.

Nếu nhu cầu tìm kiếm có hàng nghìn ID hoặc cấu trúc lồng phức tạp, nên thiết kế một thao tác tìm kiếm dùng request body với hợp đồng và chính sách cache riêng. Không mặc nhiên đưa body vào `GET` rồi kỳ vọng tất cả client và trung gian sẽ xử lý thống nhất.

## 12. Ma trận kiểm thử hợp đồng

Kiểm thử nên dùng request thực tế đi qua HTTP parser. Chỉ kiểm thử một hàm nhận `List<String>` đã được tạo sẵn sẽ bỏ sót lỗi giải mã, key lặp và cách framework gom tham số.

| Request hoặc tình huống | Kỳ vọng theo hợp đồng của bài |
|---|---|
| `/orders` | Không lọc trạng thái; sort mặc định; page 0, size 20 |
| `status=PAID&status=SHIPPED` | Hai giá trị được giữ đủ; điều kiện OR |
| `status=PAID&status=PAID` | Một giá trị nghiệp vụ sau khi loại trùng |
| Chín lần xuất hiện của `status=PAID` | 400 vì vượt giới hạn trước khi loại trùng |
| `status=PAID,SHIPPED` | 400, không tự tách dấu phẩy |
| `status=` hoặc `status` | 400 nếu parser đưa về giá trị rỗng |
| `status=PAID&status=` | 400 cho cả request |
| `status=%20PAID%20` | 400, không tự trim |
| `status%5B%5D=PAID` | 400 vì key `status[]` không được hỗ trợ |
| `page=0&page=0` | 400 dù hai giá trị giống nhau |
| `page=0&page=1` | 400, không chọn đầu hoặc cuối |
| `page=abc`, `page=-1`, `size=0` | 400 |
| `page=999999999999999999999` | 400, không tràn số thành giá trị khác |
| `sort=-createdAt&sort=id` | Giữ ưu tiên createdAt rồi id |
| `sort=id&sort=-createdAt` | Giữ ưu tiên id rồi createdAt |
| `sort=totalAmount` | Nối thêm id tăng dần |
| `sort=id&sort=-id` | 400 vì lặp cùng trường |
| `sort=password` | 400 vì trường không được cho phép |
| `stats=PAID` | 400 theo chính sách key lạ |

Đối với endpoint tag minh họa, bổ sung các ca sau:

| Query | Giá trị kỳ vọng sau một lần giải mã |
|---|---|
| `tag=C%2B%2B` | Một phần tử `C++` |
| `tag=a%26b&tag=java` | Hai phần tử `a&b` và `java` |
| `tag=research%2Cdesign` | Một phần tử chứa dấu phẩy |
| `tag=%2526` | Một phần tử `%26`; không giải mã tiếp thành `&` |

Nếu có gateway, CDN hoặc SDK sinh tự động, cần ca kiểm thử đi xuyên qua chúng. Với danh sách có thứ tự, kiểm tra thứ tự giá trị tại ứng dụng; với cache, kiểm tra các request khác bộ lọc không bị dùng chung kết quả ngoài chủ đích.

## 13. Quy trình thiết kế cho một tham số danh sách mới

Khi bổ sung một bộ lọc như `category`, hãy trả lời tuần tự:

1. **Kiểu dữ liệu là gì?** Một chuỗi, một tập hợp, một dãy có thứ tự hay một đối tượng?
2. **Biểu diễn trên đường truyền ra sao?** Query lặp, dấu phân cách hay một định dạng khác?
3. **Vắng mặt và rỗng khác nhau thế nào?** Không lọc, không kết quả hay lỗi?
4. **Phần tử trùng có được chấp nhận không?** Loại trùng hay từ chối; giới hạn được kiểm tra ở thời điểm nào?
5. **Thứ tự có ý nghĩa không?** Nếu có, mọi lớp phải bảo toàn nó.
6. **Điều kiện trong danh sách là AND hay OR?** Các nhóm bộ lọc được kết hợp thế nào?
7. **Nhận và kiểm tra ở server bằng cấu trúc nào?** Có nhìn thấy scalar bị lặp trước khi chuyển kiểu không?
8. **OpenAPI, SDK và gateway có cùng cách hiểu không?** Xác nhận bằng URL thực tế và kiểm thử tích hợp.

Với lựa chọn query lặp, một hợp đồng tốt không dừng ở câu “tham số này là mảng”. Nó phải mô tả cả cách truyền, cách giải mã, ý nghĩa của từng giá trị và cách xử lý đầu vào không hợp lệ. Khi những quyết định này được thể hiện nhất quán trong URI, OpenAPI và mã Java/Spring, client có thể gửi đúng dữ liệu và server có thể xử lý request một cách dự đoán được.