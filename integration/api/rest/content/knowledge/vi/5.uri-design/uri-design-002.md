# Tham số đường dẫn để định danh, tham số truy vấn để chọn dữ liệu

Khi thiết kế REST API, cùng một yêu cầu nghiệp vụ thường có thể được biểu diễn bằng nhiều URI. Ví dụ, để lấy các đơn hàng đang xử lý của một khách hàng, bạn có thể nghĩ đến `/customers/42/orders/processing`, `/orders/customer/42/status/processing` hoặc `/customers/42/orders?status=processing`. Chọn cách nào ảnh hưởng trực tiếp đến khả năng đọc hiểu, mở rộng, kiểm thử và kiểm soát truy cập của API.

Trong chương **Thiết kế URI** của module `INTEGRATION_API_REST`, bài này tập trung vào một quy tắc thực hành: **dùng tham số đường dẫn để định danh tài nguyên hoặc phạm vi tài nguyên; dùng tham số truy vấn để diễn tả cách chọn dữ liệu trong phạm vi đó**. Ví dụ Java/Spring bên dưới minh họa cách biến quy tắc thiết kế thành hợp đồng HTTP rõ ràng.

Sau bài học, bạn có thể:

- Phân biệt vai trò của path parameter và query parameter trong một yêu cầu HTTP.
- Chọn vị trí tham số theo mô hình tài nguyên, quan hệ sở hữu và nhu cầu truy vấn.
- Thiết kế bộ lọc, sắp xếp, phân trang mà không tạo ra nhiều tuyến đường khó duy trì.
- Xử lý giá trị thiếu, rỗng, lặp, không hợp lệ và các ký tự cần mã hóa.
- Triển khai, mô tả và kiểm thử hợp đồng tham số nhất quán bằng Java/Spring hoặc công nghệ tương đương.

## 1. Nhìn một URI theo từng phần

Xét yêu cầu:

```http
GET /customers/42/orders?status=PROCESSING&sort=createdAt,desc&limit=20 HTTP/1.1
Host: api.example.com
Accept: application/json
```

Có thể phân tích như sau:

```text
/customers/42/orders ? status=PROCESSING & sort=createdAt,desc & limit=20
└────── path ──────┘   └──────────────── query ──────────────────────┘
           ↑
     customerId = 42
```

Trong một mô tả tuyến đường, API thường viết:

```text
/customers/{customerId}/orders
```

`{customerId}` là biến do framework hoặc tài liệu API quy ước; dấu ngoặc nhọn không được gửi nguyên dạng trong yêu cầu thực tế. Đường dẫn chứa `42` xác định tập đơn hàng thuộc khách hàng đó. Các tham số truy vấn tiếp tục chọn những đơn hàng phù hợp, sắp xếp chúng và giới hạn số kết quả.

| Thành phần | Câu hỏi thường trả lời | Ví dụ |
| --- | --- | --- |
| Tham số đường dẫn | Đang truy cập tài nguyên nào, trong phạm vi nào? | `/orders/ord_1001`, `/customers/cus_42/orders` |
| Bộ lọc truy vấn | Những phần tử nào của tập tài nguyên được chọn? | `?status=PROCESSING&minTotal=100000` |
| Sắp xếp truy vấn | Các phần tử được trả về theo thứ tự nào? | `?sort=createdAt,desc` |
| Phân trang truy vấn | Lấy đoạn nào, tối đa bao nhiêu phần tử? | `?limit=20&cursor=...` |
| Chọn trường truy vấn | Cần những trường nào trong biểu diễn? | `?fields=id,status,total` |

Đây là quy tắc thiết kế ứng dụng, không phải một định luật nói rằng query không tham gia định danh. Về cấu trúc URI, cả path và query đều có thể góp phần xác định tài nguyên đích. `/orders?status=PROCESSING` và `/orders?status=SHIPPED` là hai URI khác nhau. Quy tắc trong bài giúp bạn phân chia trách nhiệm dễ hiểu khi xây dựng API theo resource.

## 2. Dùng path parameter cho định danh ổn định

### 2.1. Định danh một tài nguyên cụ thể

Một đơn hàng có ID `ord_1001` có thể được truy cập bằng:

```http
GET /orders/ord_1001
PATCH /orders/ord_1001
DELETE /orders/ord_1001
```

Đường dẫn giữ nguyên tài nguyên đích; phương thức HTTP diễn tả thao tác. Không cần tạo thêm những đường dẫn như `/orders/get/ord_1001` hoặc `/orders/delete/ord_1001` cho CRUD thông thường.

Các định danh phù hợp thường có những tính chất sau:

- Có ý nghĩa duy nhất trong phạm vi đã công bố.
- Đủ ổn định để liên kết vẫn hữu ích khi tên hiển thị thay đổi.
- Có một quy tắc cú pháp được mô tả rõ: số nguyên dương, UUID, mã có tiền tố hoặc chuỗi opaque.
- Không buộc client phải phân tích cấu trúc nội bộ nếu ID được công bố là opaque.

Ví dụ, tên khách hàng có thể thay đổi nên `/customers/cus_42` thường ổn định hơn `/customers/Nguyen-Van-An`. Slug vẫn là một lựa chọn hợp lệ nếu sản phẩm chấp nhận quy tắc đổi tên, chuyển hướng hoặc lưu slug cũ; điều quan trọng là hợp đồng vòng đời của định danh.

ID xuất hiện trong path không đồng nghĩa ID là bí mật, và ID khó đoán không thay thế kiểm tra quyền truy cập.

### 2.2. Định danh phạm vi hoặc tài nguyên có định danh cục bộ

Đường dẫn có thể chứa nhiều định danh:

```http
GET /projects/prj_7/tasks/task_18
GET /stores/store_3/products/sku_9
```

Thiết kế này hữu ích nếu task được nhận diện trong phạm vi project, hoặc mã sản phẩm chỉ duy nhất trong một cửa hàng. Khi đó, cả cặp định danh mới đủ xác định tài nguyên.

Một collection con cũng là tài nguyên có thể được truy cập:

```http
GET /customers/cus_42/orders
```

Ở đây, `cus_42` xác định phạm vi collection; yêu cầu vẫn có thể trả về không có đơn hàng nào.

Nếu `orderId` đã duy nhất toàn hệ thống, API có thể công bố đường dẫn chuẩn ngắn hơn:

```http
GET /orders/ord_1001
GET /customers/cus_42/orders
```

Tuyến thứ nhất lấy một đơn hàng cụ thể; tuyến thứ hai duyệt đơn hàng theo khách hàng. Không cần lồng mọi quan hệ vào đường dẫn như `/companies/co_1/regions/r_2/customers/cus_42/orders/ord_1001` chỉ vì dữ liệu có các quan hệ đó.

### 2.3. Path phải thể hiện quan hệ có thật

Nếu API chấp nhận:

```http
GET /customers/cus_42/orders/ord_1001
```

server phải kiểm tra `ord_1001` thực sự thuộc `cus_42`, bên cạnh quyền truy cập của người gọi. Nếu chỉ tìm đơn hàng theo `orderId` và bỏ qua `customerId`, URI đang hứa một phạm vi mà hệ thống không thực thi.

Với tài nguyên không thuộc phạm vi đã nêu, API có thể trả `404 Not Found`. Trường hợp tài nguyên tồn tại nhưng người gọi thiếu quyền cần được xử lý theo chính sách `403` hoặc `404` nhất quán của hệ thống; không dùng hình dạng URI để suy ra đã được phân quyền.

## 3. Dùng query parameter để chọn dữ liệu

### 3.1. Bộ lọc trên một collection

Bộ lọc thu hẹp tập dữ liệu được trả về:

```http
GET /orders?status=PROCESSING
GET /orders?customerId=cus_42&status=PROCESSING
GET /products?categoryId=cat_9&minPrice=100000&maxPrice=500000
```

Đưa bộ lọc vào query giúp mở rộng nhu cầu tìm kiếm mà không phải thêm tuyến đường cho từng tổ hợp:

```http
GET /orders?status=PROCESSING&createdFrom=2026-01-01&createdBefore=2026-02-01
```

Hợp đồng phải nói rõ hai mốc ngày có nghĩa gì. Ví dụ trên có thể quy ước `createdFrom` bao gồm thời điểm đầu ngày 01/01/2026, `createdBefore` loại trừ thời điểm đầu ngày 01/02/2026, cả hai theo UTC. Nếu dữ liệu là timestamp, một lựa chọn khác là nhận trực tiếp thời điểm ISO 8601 có offset. Không để client tự đoán múi giờ hoặc tính bao gồm của biên.

Khi không có kết quả phù hợp, một truy vấn collection hợp lệ thông thường trả `200 OK` với danh sách rỗng, thay vì `404`:

```json
{
  "items": [],
  "limit": 20,
  "nextCursor": null
}
```

Riêng `/customers/cus_42/orders`, việc khách hàng không tồn tại và việc khách hàng tồn tại nhưng chưa có đơn hàng là hai tình huống khác nhau. API cần công bố cách phân biệt; một hợp đồng thường dùng là khách hàng không tồn tại trả `404`, còn collection rỗng trả `200`.

### 3.2. Sắp xếp

Ví dụ:

```http
GET /orders?sort=createdAt,desc
GET /products?sort=price,asc
```

Hợp đồng cần định nghĩa:

- Những trường nào được phép sắp xếp.
- Giá trị hướng sắp xếp hợp lệ, chẳng hạn `asc` và `desc`.
- Thứ tự mặc định khi không truyền `sort`.
- Cách xử lý nhiều tiêu chí nếu API hỗ trợ.
- Tiêu chí phụ để có thứ tự xác định khi nhiều bản ghi trùng giá trị.

Ví dụ, `createdAt DESC, id DESC` tạo thứ tự xác định nếu `id` là duy nhất. Một thứ tự xác định giúp phân trang có thể dự đoán được, nhưng riêng nó không ngăn mọi hiện tượng dịch chuyển trang khi dữ liệu thay đổi; mức nhất quán còn tùy cơ chế phân trang và snapshot.

Không đưa nguyên chuỗi `sort` của client vào câu SQL. Hãy ánh xạ tên công khai sang danh sách trường và hướng sắp xếp được phép.

### 3.3. Phân trang

Hai hợp đồng thường gặp:

```http
GET /orders?page=0&size=20
GET /orders?limit=20&cursor=eyJ...
```

| Kiểu phân trang | Cần ghi rõ trong hợp đồng |
| --- | --- |
| Page/size | Trang bắt đầu từ 0 hay 1, kích thước mặc định/tối đa, thứ tự sắp xếp và hành vi với trang vượt phạm vi |
| Cursor | Cursor có tính opaque, giới hạn số phần tử, hướng duyệt, thời hạn hoặc điều kiện hết hiệu lực nếu có |

Với cursor, client nên dùng lại token server trả về, không tự dựng token bằng cách đoán cấu trúc. Các tham số lọc và sắp xếp phải tương thích với cursor. Nếu token chỉ có nghĩa cho `status=PROCESSING`, hợp đồng cần nêu việc đổi sang `status=SHIPPED` yêu cầu bắt đầu một lượt duyệt mới.

Không trộn page và cursor trong cùng một yêu cầu nếu API không định nghĩa rõ cách kết hợp. Với tham số mâu thuẫn, trả lỗi rõ ràng tốt hơn là âm thầm ưu tiên một kiểu.

### 3.4. Chọn trường và mở rộng dữ liệu liên quan

Một số API hỗ trợ:

```http
GET /orders/ord_1001?fields=id,status,total
GET /orders/ord_1001?include=items
```

Hai yêu cầu vẫn hướng đến đơn hàng `ord_1001`, nhưng yêu cầu biểu diễn khác nhau. `fields` và `include` là quy ước của API, không phải khả năng tự động có sẵn trong mọi REST framework.

Server phải có danh sách trường hoặc quan hệ được phép chọn, vẫn áp dụng phân quyền và giới hạn chi phí truy vấn. `include=payments` không thể tự động cho phép một người dùng xem thông tin thanh toán mà họ không có quyền đọc.

## 4. Cùng một thuộc tính có thể xuất hiện ở vị trí khác nhau

Không thể quyết định vị trí tham số chỉ từ tên cột dữ liệu. Hãy nhìn vai trò của nó trong tài nguyên đang được thiết kế.

| Nhu cầu | URI minh họa | Lý do |
| --- | --- | --- |
| Lấy khách hàng cụ thể | `/customers/cus_42` | `customerId` là định danh tài nguyên đích |
| Duyệt đơn hàng của một khách hàng | `/customers/cus_42/orders` | Khách hàng xác định phạm vi collection |
| Tìm đơn hàng trên collection toàn cục | `/orders?customerId=cus_42` | Khách hàng là điều kiện lọc |
| Lấy một đơn hàng cụ thể | `/orders/ord_1001` | `orderId` định danh một resource |
| Tìm nhiều đơn hàng theo danh sách ID | `/orders?id=ord_1001&id=ord_1002` | Query chọn một tập con; phải mô tả cú pháp lặp |
| Lấy bản dịch cụ thể có thể quản lý độc lập | `/articles/art_8/translations/vi` | Mã ngôn ngữ là phần của định danh bản dịch |
| Yêu cầu một biến thể ngôn ngữ khi đọc bài viết | `/articles/art_8?lang=vi` hoặc dùng `Accept-Language` | Lựa chọn phụ thuộc hợp đồng biểu diễn và thương lượng nội dung |

`/customers/cus_42/orders` và `/orders?customerId=cus_42` đều có thể hợp lý. Quyết định cần dựa vào các câu hỏi:

1. Client đang duyệt một collection nằm dưới khách hàng, hay tìm kiếm trong collection đơn hàng?
2. Đơn hàng có tồn tại và được định danh độc lập với khách hàng không?
3. Mô hình phân quyền cần phạm vi nào, và server sẽ thực thi phạm vi đó thế nào?
4. Hành vi khi khách hàng không tồn tại có cần khác hành vi lọc không có kết quả không?

Không cần công bố cả hai dạng nếu chỉ một dạng đã phục vụ đủ nhu cầu. Nếu công bố cả hai, hãy xác định đường dẫn chuẩn của từng đơn hàng để link trong response và tài liệu được nhất quán.

## 5. Thiết kế hợp đồng query rõ ràng

### 5.1. Phân biệt vắng mặt, rỗng và sai giá trị

Các yêu cầu sau không đương nhiên có cùng ý nghĩa:

```http
GET /orders
GET /orders?status=
GET /orders?status=PROCESSING
GET /orders?status=UNKNOWN
```

Một hợp đồng có thể quy định:

| Đầu vào | Hành vi |
| --- | --- |
| Không có `status` | Không lọc theo trạng thái |
| `status=PROCESSING` | Chỉ trả đơn hàng có trạng thái tương ứng |
| `status=` | `400 Bad Request` vì giá trị rỗng không hợp lệ |
| `status=UNKNOWN` | `400 Bad Request` vì không thuộc tập giá trị cho phép |

Không nên vô tình coi chuỗi rỗng là “không lọc” nếu điều đó khiến một lỗi ở client làm truy vấn trả về tập dữ liệu lớn hơn dự kiến. Nếu API chủ ý gộp hai trường hợp, phải ghi rõ và triển khai nhất quán.

### 5.2. Tham số lặp và bộ lọc nhiều giá trị

Có nhiều cách biểu diễn:

```http
GET /orders?status=PROCESSING&status=SHIPPED
GET /orders?status=PROCESSING,SHIPPED
```

Chọn một cú pháp chính và mô tả rõ:

- Các giá trị trong cùng bộ lọc kết hợp theo OR hay AND.
- Các bộ lọc khác loại kết hợp thế nào.
- Có loại bỏ phần tử trùng nhau hay không.
- Giới hạn số phần tử trong danh sách.
- Ký tự phân cách được hiểu thế nào nếu chính giá trị có dấu phẩy.

Ví dụ: các `status` lặp kết hợp theo OR; `status` và `customerId` kết hợp theo AND. Không dựa vào hành vi framework tự chọn giá trị đầu hoặc cuối của một tham số lặp vốn được định nghĩa là đơn trị.

### 5.3. Tham số không được hỗ trợ

Xét lỗi gõ nhầm:

```http
GET /orders?stauts=PROCESSING
```

Nếu server bỏ qua tên lạ, client có thể hiểu nhầm rằng kết quả đã được lọc. Nếu server trả lỗi, API chặt chẽ hơn nhưng cần kế hoạch tương thích khi client và server được triển khai ở các thời điểm khác nhau.

Cả hai chính sách đều cần được quyết định có chủ đích. Với các truy vấn quan trọng, từ chối tham số lạ bằng `400` là lựa chọn dễ phát hiện lỗi; không được giả định framework tự thực hiện chính sách đó. Ví dụ Spring ở phần sau có kiểm tra danh sách tên được hỗ trợ.

### 5.4. Kiểu dữ liệu, giới hạn và lỗi

Một bảng hợp đồng nhỏ thường ngăn được nhiều lỗi tích hợp:

| Tham số | Kiểu công khai | Mặc định | Quy tắc |
| --- | --- | --- | --- |
| `customerId` trong path | Chuỗi có tiền tố | Không có | Bắt buộc, ví dụ `cus_42` |
| `status` trong query | Enum đơn trị | Không lọc | Phân biệt hoa/thường, không chấp nhận rỗng |
| `limit` trong query | Số nguyên | `20` | Từ `1` đến `100` |
| `sort` trong query | Chuỗi theo cú pháp đã công bố | `createdAt,desc` | Chỉ các trường và hướng cho phép |

Bắt buộc không đồng nghĩa với phải nằm ở path: một query parameter vẫn có thể là bắt buộc nếu hợp đồng yêu cầu, chẳng hạn `q` của một endpoint tìm kiếm. Ngược lại, biến trong một route cụ thể phải có giá trị để route đó khớp; bỏ `orderId` khỏi `/orders/{orderId}` thường chuyển sang route collection `/orders`, không tạo ra một item với ID mặc định.

Phân biệt các loại lỗi:

- Sai định dạng ID, enum hoặc giới hạn: có thể dùng `400 Bad Request` theo hợp đồng của bài này.
- ID hợp lệ về cú pháp nhưng không có tài nguyên tương ứng: `404 Not Found`.
- Chưa xác thực hoặc thông tin xác thực không hợp lệ: `401 Unauthorized` theo cơ chế xác thực của API.
- Đã xác thực nhưng thiếu quyền: `403 Forbidden`, hoặc `404` nếu chính sách nhất quán yêu cầu che giấu sự tồn tại.

## 6. Mã hóa giá trị đúng theo thành phần URI

Giá trị tham số có thể chứa khoảng trắng, dấu tiếng Việt hoặc ký tự có ý nghĩa trong URI:

```text
Cà phê & trà
```

Ví dụ một giá trị query đã được mã hóa theo UTF-8:

```http
GET /products?q=C%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
```

`%26` biểu diễn dấu `&` nằm trong giá trị; một dấu `&` chưa được mã hóa thường bị bộ phân tích query dùng làm dấu phân cách tham số. Trong các bộ giải mã query theo quy ước form URL encoding, dấu `+` thường được hiểu là khoảng trắng. Nếu cần gửi dấu cộng nguyên nghĩa, hãy để thư viện mã hóa nó thành `%2B`.

Các nguyên tắc thực hành:

1. Dùng URI builder của thư viện thay vì nối chuỗi đầu vào vào URL.
2. Mã hóa từng giá trị theo đúng ngữ cảnh path segment hoặc query value, không mã hóa nguyên URL đã ghép như một giá trị duy nhất.
3. Không mã hóa lặp lại một giá trị đã mã hóa nếu thư viện đang nhận đầu vào dạng thô.
4. Không coi slash `/` tùy ý là một phần an toàn của ID trong path. `%2F` có thể bị proxy, server hoặc router xử lý khác nhau; nếu ID thực sự chứa slash, phải thiết kế và kiểm thử toàn bộ tuyến xử lý.
5. Không giải mã thêm nhiều lần ở các tầng ứng dụng khác nhau.

Ví dụ client Java dùng Spring URI builder:

```java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

String keyword = "Cà phê & trà";

URI uri = UriComponentsBuilder
    .fromUriString("https://api.example.com/products")
    .queryParam("q", "{keyword}")
    .queryParam("limit", 20)
    .encode()
    .buildAndExpand(keyword)
    .toUri();
```

Đầu vào `keyword` ở đây là văn bản thô. Template expansion cùng bước encode giúp giữ ký tự đặc biệt trong vai trò giá trị query.

Fragment sau dấu `#` không được gửi tới server trong yêu cầu HTTP thông thường. Vì vậy, `/orders#status=PROCESSING` không phải cách gửi bộ lọc `status` cho API.

## 7. Triển khai hợp đồng bằng Java/Spring

Ví dụ sau dùng Spring MVC, kiểu `record` của Java và các DTO do ứng dụng định nghĩa. Endpoint chỉ minh họa ba tham số: `customerId`, `status`, `limit`. Các phần sắp xếp hoặc cursor cần hợp đồng và triển khai riêng nếu được bổ sung.

### 7.1. Controller phân biệt rõ hai vai trò

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.http.HttpStatus;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {
    private static final Pattern CUSTOMER_ID = Pattern.compile("cus_[1-9][0-9]*");
    private static final Set<String> ALLOWED_QUERY = Set.of("status", "limit");

    private final OrderQueryService service;

    public CustomerOrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping
    public OrderListResponse list(
            @PathVariable("customerId") String customerId,
            @RequestParam MultiValueMap<String, String> query) {

        if (!CUSTOMER_ID.matcher(customerId).matches()) {
            throw badRequest("customerId phải có dạng cus_42");
        }
        if (!ALLOWED_QUERY.containsAll(query.keySet())) {
            throw badRequest("Có query parameter không được hỗ trợ");
        }

        String rawStatus = singleValue(query, "status");
        String rawLimit = singleValue(query, "limit");
        OrderStatus status = parseStatus(rawStatus);
        int limit = parseLimit(rawLimit);

        // Service phải kiểm tra khách hàng, quyền truy cập và phạm vi dữ liệu.
        return service.findForCustomer(customerId, status, limit);
    }

    private static String singleValue(
            MultiValueMap<String, String> query, String name) {
        List<String> values = query.get(name);
        if (values == null) {
            return null;
        }
        if (values.size() != 1 || values.get(0) == null
                || values.get(0).isBlank()) {
            throw badRequest(name + " phải có đúng một giá trị không rỗng");
        }
        return values.get(0);
    }

    private static OrderStatus parseStatus(String raw) {
        if (raw == null) {
            return null; // Không lọc theo trạng thái.
        }
        try {
            return OrderStatus.valueOf(raw);
        } catch (IllegalArgumentException ex) {
            throw badRequest("status phải là PROCESSING, SHIPPED hoặc CANCELLED");
        }
    }

    private static int parseLimit(String raw) {
        if (raw == null) {
            return 20;
        }
        if (!raw.matches("[0-9]{1,3}")) {
            throw badRequest("limit phải là số nguyên từ 1 đến 100");
        }
        int value = Integer.parseInt(raw);
        if (value < 1 || value > 100) {
            throw badRequest("limit phải là số nguyên từ 1 đến 100");
        }
        return value;
    }

    private static ResponseStatusException badRequest(String detail) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, detail);
    }

    public enum OrderStatus {
        PROCESSING, SHIPPED, CANCELLED
    }

    public record OrderSummary(
            String id, OrderStatus status, BigDecimal total, String currency) {}

    public record OrderListResponse(List<OrderSummary> items, int limit) {}

    public interface OrderQueryService {
        OrderListResponse findForCustomer(
                String customerId, OrderStatus status, int limit);
    }
}
```

`@PathVariable` lấy biến định danh từ đường dẫn. `@RequestParam MultiValueMap` đọc query theo danh sách giá trị, để ví dụ chủ động từ chối tham số lạ, tham số lặp và giá trị rỗng. Với hợp đồng đơn giản hơn, Spring cũng có thể bind trực tiếp `@RequestParam` vào enum hoặc số nguyên; khi đó cần kiểm tra hành vi chuyển đổi, giá trị mặc định và lỗi có khớp tài liệu hay không.

`OrderQueryService` cần có implementation được đăng ký thành bean trong ứng dụng. Controller này không phải toàn bộ dự án chạy độc lập; lớp xác thực, phân quyền, truy cập dữ liệu và chuyển đổi lỗi là các phần phải nối vào hệ thống thực tế.

Ví dụ giới hạn số phần tử nhưng chưa cung cấp cơ chế duyệt tiếp. Nếu client phải lấy toàn bộ collection qua nhiều lần gọi, bổ sung page hoặc cursor cùng metadata tương ứng; không xem `limit` riêng lẻ là một hợp đồng phân trang hoàn chỉnh.

### 7.2. Service phải thực thi phạm vi truy vấn

Đây là luồng xử lý cần có ở tầng nghiệp vụ:

```text
Nhận customerId, status, limit đã hợp lệ
  → Xác thực người gọi tại lớp bảo mật
  → Kiểm tra quyền đọc phạm vi khách hàng theo chính sách hệ thống
  → Kiểm tra khách hàng tồn tại theo hợp đồng đã công bố
  → Truy vấn đơn hàng với điều kiện customer_id = customerId
  → Nếu có status, thêm điều kiện status tương ứng
  → Áp dụng thứ tự xác định và giới hạn kết quả
  → Trả DTO chỉ gồm dữ liệu người gọi được phép đọc
```

Thứ tự kiểm tra quyền và sự tồn tại cần phù hợp chính sách chống tiết lộ thông tin của hệ thống. Điều không được bỏ qua là điều kiện phạm vi trong truy vấn thực tế. Việc controller có `customerId` trong path chưa tự làm cho câu truy vấn an toàn.

Các giá trị lọc phải được bind bằng cơ chế tham số hóa hoặc query API phù hợp. Nếu bổ sung `sort`, ánh xạ từ tên công khai sang trường được phép; bind parameter không thay thế được việc kiểm soát tên cột động.

### 7.3. Hợp đồng lỗi có thể đọc được bởi client

Để lỗi cú pháp tham số có hình dạng ổn định, ứng dụng có thể chuẩn hóa response theo Problem Details bằng error handler hoặc cấu hình xử lý lỗi thích hợp:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
```

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "limit phải là số nguyên từ 1 đến 100",
  "instance": "/customers/cus_42/orders"
}
```

Đây là response mục tiêu của hợp đồng; việc chỉ ném `ResponseStatusException` trong controller không bảo đảm mọi cấu hình Spring sẽ tự sinh đúng JSON trên. Cần cấu hình hoặc triển khai handler tương ứng và kiểm thử response thực tế. Tránh trả stack trace hoặc chi tiết truy vấn cơ sở dữ liệu cho client.

## 8. Ghi lại vị trí tham số trong OpenAPI

Đoạn YAML dưới đây minh họa khai báo cho endpoint trong ví dụ, không phải toàn bộ tài liệu OpenAPI:

```yaml
paths:
  /customers/{customerId}/orders:
    get:
      summary: Liệt kê đơn hàng của một khách hàng
      parameters:
        - name: customerId
          in: path
          required: true
          schema:
            type: string
            pattern: '^cus_[1-9][0-9]*$'
          example: cus_42
          description: Định danh khách hàng; định dạng phân biệt hoa/thường.
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [PROCESSING, SHIPPED, CANCELLED]
          description: >-
            Chỉ chấp nhận một giá trị. Bỏ qua tham số để không lọc trạng thái;
            giá trị rỗng hoặc tham số lặp bị từ chối.
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
          description: >-
            Giới hạn số phần tử, chỉ chấp nhận một giá trị. Khi truyền trên URI,
            dùng chuỗi 1 đến 3 chữ số thập phân không dấu; không chấp nhận rỗng.
      description: >-
        Chỉ hỗ trợ status và limit trong query; tên tham số khác bị từ chối.
        Kết quả được sắp xếp theo createdAt giảm dần, sau đó id giảm dần.
        Endpoint này chưa hỗ trợ lấy trang tiếp theo.
      responses:
        '200':
          description: Danh sách có thể rỗng của khách hàng được phép truy cập.
        '400':
          description: Sai định dạng hoặc vi phạm hợp đồng tham số.
        '401':
          description: Chưa xác thực hoặc thông tin xác thực không hợp lệ.
        '403':
          description: Người gọi không được phép đọc dữ liệu khách hàng.
        '404':
          description: Không tìm thấy khách hàng trong phạm vi được phép kiểm tra.
```

Trong OpenAPI, path parameter phải khai báo `required: true`; tên `customerId` phải khớp biến trong path template. Query parameter có thể bắt buộc hoặc tùy chọn theo hợp đồng.

Schema mô tả kiểu và giới hạn, nhưng các quy tắc như từ chối query parameter lạ hoặc lặp vẫn cần triển khai thực tế và kiểm thử. Với tài liệu hoàn chỉnh, bổ sung schema response, hợp đồng lỗi, security scheme và ví dụ tương ứng.

## 9. URI ảnh hưởng đến cache và hành vi HTTP

### 9.1. Query không tự làm response mất khả năng cache

Hai yêu cầu:

```http
GET /orders?status=PROCESSING
GET /orders?status=SHIPPED
```

có URI khác nhau và có thể trả dữ liệu khác nhau. Cache cần phân biệt chúng theo cấu hình và quy tắc cache áp dụng. Không thể kết luận rằng “có query thì không cache được”. Khả năng cache còn phụ thuộc phương thức, status, header như `Cache-Control`, thông tin xác thực và chính sách của các tầng trung gian.

Nếu response phụ thuộc người dùng, phải thiết kế chính sách cache phù hợp để không dùng nhầm dữ liệu giữa người gọi. `Vary` giải quyết biến thể theo các request header được chỉ định; nó không thay thế việc đưa query ảnh hưởng đến kết quả vào cache key.

### 9.2. Chuẩn hóa query phải tôn trọng ngữ nghĩa

Với bộ lọc độc lập, ứng dụng có thể chủ ý định nghĩa:

```text
/orders?status=PROCESSING&limit=20
/orders?limit=20&status=PROCESSING
```

là tương đương về kết quả. Tuy nhiên, không nên mặc định mọi cache, cơ chế ký URL hoặc query parser đều xử lý chúng như một khóa duy nhất.

Đặc biệt, không tự ý sắp xếp hoặc gộp mọi giá trị query nếu API có tham số lặp mang ý nghĩa thứ tự. Chính sách canonicalization phải thống nhất giữa client, gateway, chữ ký và backend.

### 9.3. Vị trí tham số không quyết định tính an toàn và idempotency

```http
GET /orders/ord_1001?cancel=true
```

Nếu yêu cầu này hủy đơn hàng, vấn đề nằm ở việc dùng GET cho thay đổi trạng thái nghiệp vụ. Đưa `cancel` từ query vào path không tự sửa được ý nghĩa của phương thức HTTP.

Tương tự, tính idempotent của một thao tác phụ thuộc hợp đồng phương thức và cách thực thi. Nó không xuất hiện chỉ vì ID nằm trong path hoặc vì client dùng query parameter.

Thông tin xác thực như access token nên truyền qua cơ chế xác thực phù hợp, thường là header `Authorization` với Bearer token; tránh đưa vào path hoặc query vì URL có thể xuất hiện trong log và nhiều công cụ theo dõi.

## 10. Các thiết kế dễ gây nhầm và cách cải thiện

| Thiết kế | Điều cần xem lại | Hướng cải thiện |
| --- | --- | --- |
| `/orders/status/PROCESSING/minTotal/100000` | Path đang chứa chuỗi bộ lọc có thể kết hợp tùy ý | `/orders?status=PROCESSING&minTotal=100000` |
| `/getOrder?id=ord_1001` | Tên thao tác lấn át resource trong một CRUD API | `GET /orders/ord_1001` |
| `/customers/cus_42/orders/ord_1001` nhưng không kiểm tra quan hệ | Phạm vi URI không được thực thi | Truy vấn theo đúng cả hai ID và kiểm tra quyền |
| `/orders?limit=1000000` được chấp nhận | Thiếu giới hạn chi phí truy vấn | Công bố và áp dụng giới hạn tối đa |
| `/orders?status=` âm thầm trở thành không lọc | Dễ che giấu lỗi client | Chọn rõ chính sách rỗng và kiểm thử |
| `/orders?sort=` được ghép trực tiếp vào SQL | Đầu vào điều khiển biểu thức truy vấn | Ánh xạ trường và hướng theo danh sách cho phép |
| `/orders?access_token=...` | Thông tin xác thực có thể lọt vào URL log | Dùng cơ chế xác thực qua header phù hợp |
| `/orders#status=PROCESSING` | Fragment không đến server trong request thông thường | Dùng query parameter |

URI dài và nhiều điều kiện không phải lúc nào cũng phù hợp với GET. Nếu truy vấn có cấu trúc quá phức tạp, API có thể cần một hợp đồng tìm kiếm bằng request body, chẳng hạn `POST /order-searches`, hoặc một tài nguyên truy vấn có vòng đời riêng. Cần thiết kế lại ý nghĩa và đặc tính HTTP của endpoint đó; không giả định GET body sẽ được mọi client, proxy và server xử lý thống nhất. Không có một giới hạn độ dài URL duy nhất áp dụng cho toàn bộ hệ thống; phải xét các thành phần triển khai thực tế.

## 11. Kiểm thử hợp đồng tham số

Với endpoint `/customers/{customerId}/orders`, các ca sau kiểm tra những điểm mà chữ ký method riêng lẻ không bảo đảm:

| Yêu cầu hoặc tình huống | Kết quả cần xác minh |
| --- | --- |
| Khách hàng tồn tại, không truyền query | `200`, mặc định `limit=20`, không lọc trạng thái |
| `?status=PROCESSING&limit=10` | Chỉ trả đơn đúng khách hàng và trạng thái, tối đa 10 phần tử |
| Khách hàng tồn tại nhưng chưa có đơn | `200` và `items: []` |
| `customerId` sai cú pháp | `400` |
| Khách hàng không tồn tại, người gọi được phép kiểm tra phạm vi | `404` theo hợp đồng |
| `?status=` hoặc `?status=UNKNOWN` | `400`, lỗi có hình dạng thống nhất |
| `?status=PROCESSING&status=SHIPPED` | `400` vì endpoint ví dụ chỉ nhận một giá trị |
| `?limit=0`, `?limit=101`, `?limit=abc`, `?limit=` | `400`, không âm thầm thay thành mặc định |
| `?stauts=PROCESSING` | `400` theo chính sách từ chối tham số lạ |
| Cùng query nhưng đổi thứ tự `status` và `limit` | Kết quả dữ liệu tương đương theo hợp đồng của endpoint |
| Người gọi đổi `customerId` sang khách hàng không được phép xem | Không lộ dữ liệu; đúng chính sách `403`/`404` đã chọn |
| Dữ liệu có đơn hàng thuộc khách hàng khác | Không có đơn hàng ngoài phạm vi trong kết quả |

Với endpoint tìm kiếm theo chuỗi tự do, kiểm tra thêm giá trị có tiếng Việt, `&`, `+`, `%` và khoảng trắng qua client URI builder thực tế. Với phân trang cursor, kiểm tra cursor hết hiệu lực, đổi filter giữa các lần gọi và nhiều bản ghi trùng giá trị sort.

Có thể dùng MockMvc cho lớp HTTP và kiểm thử tích hợp cho truy vấn/phân quyền. Một bài test chỉ kiểm tra service đã nhận `customerId` chưa đủ chứng minh rằng câu truy vấn thực sự giới hạn theo khách hàng; cần có dữ liệu khác phạm vi để kiểm chứng.

## 12. Bài tập áp dụng

Một hệ thống quản lý khóa học có các yêu cầu sau:

1. Đọc khóa học có ID `course_12`.
2. Liệt kê bài học thuộc khóa học đó.
3. Trong collection bài học của khóa học, lọc bài đã xuất bản và sắp xếp theo thứ tự học tăng dần.
4. Tìm khóa học theo từ khóa và cấp độ.
5. Đọc một bài học có ID duy nhất toàn hệ thống.

Một thiết kế có thể là:

```http
GET /courses/course_12
GET /courses/course_12/lessons
GET /courses/course_12/lessons?status=PUBLISHED&sort=position,asc
GET /courses?q=java&level=BEGINNER
GET /lessons/lesson_99
```

Giải thích:

- `course_12` và `lesson_99` là định danh tài nguyên nên nằm trong path.
- `status`, `sort`, `q`, `level` lựa chọn dữ liệu hoặc thứ tự nên nằm trong query.
- `course_12` trong collection con xác định phạm vi bài học, không chỉ là một bộ lọc được bỏ qua tùy ý.
- Đường dẫn chuẩn của một bài học có thể là `/lessons/{lessonId}` nếu ID đã duy nhất toàn hệ thống.

Để hoàn thiện hợp đồng, hãy tự xác định hành vi khi khóa học không tồn tại, khi collection rỗng, khi `level` không hợp lệ, khi có nhiều bài trùng `position` và khi người gọi chưa được phép xem nội dung chưa xuất bản.

## 13. Những điểm cần ghi nhớ

Dùng path parameter để diễn tả tài nguyên và phạm vi ổn định; dùng query parameter để lọc, sắp xếp, phân trang và chọn biểu diễn. Cùng một thuộc tính có thể giữ vai trò khác nhau tùy endpoint, vì vậy quyết định phải xuất phát từ mô hình tài nguyên thay vì chỉ nhìn tên trường.

Một URI dễ đọc mới là bước đầu. Hợp đồng đầy đủ còn phải xác định cú pháp, kiểu dữ liệu, giá trị mặc định, giới hạn, cách xử lý rỗng/lặp, mã lỗi và mã hóa. Triển khai phải thực thi đúng phạm vi, phân quyền và truy vấn an toàn; tài liệu OpenAPI và kiểm thử phải phản ánh chính những quy tắc đó.
