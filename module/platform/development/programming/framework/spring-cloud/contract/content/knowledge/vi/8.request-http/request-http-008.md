# Form URL-encoded và mã hóa ký tự

## 1. Bài toán và mục tiêu

Trong **Spring Cloud Contract (SCC)**, một hợp đồng HTTP mô tả điều kiện request mà **consumer** gửi, cùng response mà **producer** phải trả. Hợp đồng viết bằng **Groovy DSL** hoặc **YAML DSL** được sử dụng để sinh **producer tests** và **stub**. Consumer có thể chạy **Stub Runner** với stub ứng viên; CI kết hợp hai phía để phát hiện các thay đổi API không tương thích.

Không phải HTTP request nào cũng mang JSON. Các form HTML truyền thống, một số API đăng nhập, xác nhận đơn hàng và tích hợp hệ thống cũ gửi dữ liệu theo định dạng **`application/x-www-form-urlencoded`**. Nếu contract vô tình mô tả JSON, hoặc nhầm ký tự `+` với khoảng trắng, request sinh ra có thể khác request của consumer dù dữ liệu nhìn bằng mắt có vẻ giống nhau.

Bài này tập trung vào **request HTTP dạng form URL-encoded và mã hóa ký tự**: quy tắc chuyển tên/giá trị thành body, cách viết contract, cách gửi form từ Spring, cách kiểm chứng producer và consumer.

Sau bài học, bạn có thể:

1. Phân biệt form URL-encoded với JSON, query parameters và multipart.
2. Giải thích cách mã hóa khoảng trắng, dấu cộng, ký tự đặc biệt và chữ tiếng Việt bằng UTF-8.
3. Viết ví dụ contract Groovy và YAML với **body dạng chuỗi đã mã hóa**.
4. Tạo request bằng `RestClient` và `MultiValueMap` mà không tự mã hóa hai lần.
5. Kiểm tra generated producer test và stub để phát hiện sai khác **Content-Type**, bytes, charset và điều kiện so khớp.
6. Thiết kế kiểm tra CI phát hiện thay đổi không tương thích đối với các form consumer còn đang sử dụng.

## 2. Form URL-encoded nằm ở đâu trong HTTP?

Giả sử Checkout Service cần gửi tên người nhận, ghi chú giao hàng và số lượng tới Inventory Service:

~~~http
POST /api/reservations/preview HTTP/1.1
Host: inventory.example.test
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2
~~~

Body phía trên mang **ba cặp tên–giá trị**:

| Tên trường | Giá trị trước mã hóa | Dữ liệu trong body |
|---|---|---|
| `fullName` | `Trần Văn A` | `Tr%E1%BA%A7n+V%C4%83n+A` |
| `note` | `Khuyến mãi 10% & giao nhanh` | `Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh` |
| `quantity` | `2` | `2` |

Khi nhận đúng `Content-Type` và charset, server giải mã body để lấy lại các giá trị ban đầu. Form field vốn truyền ở dạng **chuỗi**; Spring MVC có thể chuyển chuỗi `"2"` thành `int` cho tham số controller.

Đây là form URL-encoded trong **request body**. Dù cú pháp nhìn giống phần query của URL, vị trí và cách sử dụng trong hợp đồng hoàn toàn khác: phần path vẫn là `/api/reservations/preview`; các cặp tên–giá trị ở sau dòng trống HTTP là **body**.

## 3. Quy tắc mã hóa application/x-www-form-urlencoded

Mô hình cơ bản:

~~~text
encode(name1)=encode(value1)&encode(name2)=encode(value2)&...
~~~

Với từng tên và giá trị riêng rẽ:

1. Chuyển chuỗi Unicode thành các byte theo charset đã chọn, thông thường là **UTF-8**.
2. Giữ nguyên những ký tự an toàn theo quy tắc form encoding.
3. Biểu diễn **khoảng trắng** bằng dấu `+`.
4. Biểu diễn những byte cần escape dưới dạng `%HH` (hai chữ số hex).
5. Ghép mỗi tên với giá trị bằng `=`; ghép các cặp bằng `&`.

Chú ý: ký tự `&` và `=` **bên trong giá trị** phải được mã hóa trước khi ghép, vì hai ký tự này còn được dùng làm dấu phân cách.

### Bảng quy đổi thường gặp

| Dữ liệu ban đầu | Mã hóa form | Vì sao? |
|---|---|---|
| `hello world` | `hello+world` | Khoảng trắng thành `+` |
| `a+b` | `a%2Bb` | Dấu cộng **thật** thành `%2B` |
| `a&b` | `a%26b` | Dấu `&` trong giá trị không được biến thành dấu ngăn field |
| `a=b` | `a%3Db` | Dấu `=` trong giá trị không được biến thành dấu phân cách tên/giá trị |
| `10%` | `10%25` | Dấu `%` thật thành `%25` |
| `a+b&c=d` | `a%2Bb%26c%3Dd` | Mã hóa từng ký tự đặc biệt |
| `Cà phê sữa` | `C%C3%A0+ph%C3%AA+s%E1%BB%AFa` | UTF-8: dấu tiếng Việt tạo thành nhiều byte |
| `a+b@example.com` | `a%2Bb%40example.com` | `+` và `@` đều được escape |

**Ba giá trị cần phân biệt:**

~~~text
name=Minh+Anh        -> "Minh Anh"
name=Minh%20Anh      -> "Minh Anh"  (sau giải mã form)
name=Minh%2BAnh      -> "Minh+Anh"
~~~

Trong form URL-encoded, cả `+` và `%20` có thể được giải mã thành **khoảng trắng**, nhưng chuỗi bytes trên wire không giống nhau. Một **stub so khớp body thô** có thể xem chúng khác nhau. Khi kiểm chứng cần xác định hợp đồng đòi hỏi **giá trị form sau giải mã** hay đòi hỏi **biểu diễn body byte-for-byte**.

## 4. UTF-8 và tiếng Việt: từ ký tự thành byte

Giả sử giá trị người nhận là **`Trần Văn A`**. Một số ký tự được mã hóa như sau:

- `T`, `r`, `n`, `V`, `A`: là các ký tự ASCII, có thể giữ nguyên.
- `ầ`: UTF-8 gồm nhiều byte, được viết thành một chuỗi `%HH`, ví dụ `%E1%BA%A7`.
- `ă`: được mã hóa thành `%C4%83`.
- Khoảng trắng: được chuyển thành `+`.

Kết quả:

~~~text
Trần Văn A
    ↓ application/x-www-form-urlencoded, UTF-8
Tr%E1%BA%A7n+V%C4%83n+A
~~~

Đối với **`Khuyến mãi 10% & giao nhanh`**:

~~~text
Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh
~~~

Điều quan trọng là từng ký tự Unicode được chuyển thành **byte UTF-8 trước khi percent-encode**. Không thể tự suy `%HH` từ mã Unicode bằng cách lấy bốn chữ số hex của code point.

### Charset và khả năng tái tạo

Header thường dùng:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Chính sách charset cần nhất quán ở **client, server, generated test và Stub Runner**. Không phải mọi client đều ghi charset tường minh; một số implementation mặc định UTF-8. Nếu hợp đồng cần `charset=UTF-8`, hãy kiểm tra cả request thực sự phát ra.

Đừng coi cùng một chuỗi hiển thị có nghĩa là cùng byte Unicode. Một chữ có dấu đôi khi có thể tồn tại ở dạng **ký tự dựng sẵn** hoặc **ký tự cơ sở + dấu kết hợp**. Với hợp đồng cần so khớp bytes chính xác, nhóm nên thống nhất chuẩn normalization như NFC; ở mức nghiệp vụ, thường ưu tiên kiểm tra giá trị đã giải mã.

## 5. Phân biệt bốn định dạng dễ nhầm

| Kiểu dữ liệu | Content-Type / vị trí | Ví dụ | Đặc điểm |
|---|---|---|---|
| **Form URL-encoded** | `application/x-www-form-urlencoded` ở **body** | `name=Minh+Anh&qty=2` | Các cặp tên–giá trị, mã hóa dấu và khoảng trắng |
| **Query parameters** | Phần sau dấu `?` trong URL | `/items?name=Minh%20Anh` | Dữ liệu nằm trên URL, khai báo riêng trong `queryParameters` |
| **JSON** | `application/json` ở body | `{"name":"Minh Anh","qty":2}` | Có kiểu string/number/boolean/object/array |
| **Multipart** | `multipart/form-data; boundary=...` ở body | Các part có header và boundary | Thường dùng upload file hoặc gửi part hỗn hợp |

Cùng một trường `qty` trong form body có giá trị văn bản `"2"`, còn trong JSON có thể là số `2`. Đừng để generated test tình cờ gửi JSON khi consumer thật gửi form.

Một lỗi đặc biệt thường gặp là đưa các form field vào `queryParameters` của SCC:

~~~yaml
# Ví dụ SAI khi chủ đích là POST form trong body:
request:
  method: POST
  urlPath: /api/reservations/preview
  queryParameters:
    fullName: Trần Văn A
    quantity: "2"
~~~

Đoạn này biểu diễn **query của URL**, không tự biến request thành body form URL-encoded. Nếu API thực sự đọc form fields từ body, hãy mô tả **body và Content-Type**.

## 6. Hợp đồng Groovy DSL với body URL-encoded

Một cách biểu diễn rõ ràng cho **payload form cố định** là đặt chuỗi form đã mã hóa trong `body(...)`, đồng thời khai báo `Content-Type`.

Tệp minh họa: `src/test/resources/contracts/reservation/preview-reservation.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout gửi form để xem trước phiếu giữ hàng'

    request {
        method POST()
        url '/api/reservations/preview'

        headers {
            header('Content-Type',
                'application/x-www-form-urlencoded; charset=UTF-8')
            header('Accept', 'application/json')
        }

        body(
            'fullName=Tr%E1%BA%A7n+V%C4%83n+A' +
            '&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh' +
            '&quantity=2'
        )
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            fullName: 'Trần Văn A',
            note: 'Khuyến mãi 10% & giao nhanh',
            quantity: 2,
            status: 'ACCEPTED'
        )
    }
}
~~~

**Ý nghĩa:**

- **`method POST()` và `url`** xác định endpoint producer.
- **`Content-Type`** yêu cầu request được diễn giải theo form URL-encoded với UTF-8.
- **`body(...)`** là **một chuỗi** chứa dữ liệu đã mã hóa; không phải Groovy map hay JSON.
- Response vẫn là **JSON**. Định dạng request và response không bắt buộc giống nhau.
- Giá trị ví dụ là cố định để dễ xác minh end-to-end; nếu API chấp nhận nhiều giá trị động, cần đánh giá cách SCC version đang dùng tạo request matcher cho **body text**.

Một số phiên bản rất cũ của Contract Verifier từng gặp vấn đề escape ký tự `&` trong generated tests. Nếu bạn thấy body trong generated source thành `&amp;`, cần kiểm tra phiên bản và logic sinh test, không thay đổi hợp đồng để chấp nhận chuỗi HTML escape sai.

### Vì sao không thêm `bodyMatchers { jsonPath(...) }`?

Form body bên trên là **chuỗi text có dấu phân cách**, không phải tài liệu JSON. JSONPath `$.fullName` không thể tự trích xuất trường từ `fullName=...` theo quy tắc form encoding. Không nên sử dụng body JSONPath matcher với form body chỉ vì field có cùng tên. Trong bài học này, ta ưu tiên ví dụ form cố định và kiểm tra đúng request thực tế; nếu cần matcher form linh hoạt, phải kiểm tra cơ chế hỗ trợ của SCC/WireMock ở phiên bản dự án và xác minh stub mapping đã sinh.

## 7. Cách khai báo tương tự trong YAML DSL

Nếu nhóm sử dụng YAML thay cho Groovy, `body` nên được viết thành **scalar string** chứa chuỗi form đã mã hóa:

~~~yaml
description: Checkout gửi form để xem trước phiếu giữ hàng
name: preview_reservation_form

request:
  method: POST
  url: /api/reservations/preview
  headers:
    Content-Type: application/x-www-form-urlencoded; charset=UTF-8
    Accept: application/json
  body: 'fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2'

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    fullName: Trần Văn A
    note: Khuyến mãi 10% & giao nhanh
    quantity: 2
    status: ACCEPTED
~~~

Dấu nháy đơn bao quanh `request.body` khiến toàn bộ nội dung được đọc như một chuỗi. Tránh dùng YAML map sau đây khi định nghĩa body form:

~~~yaml
# KHÔNG phải là cách biểu diễn body form URL-encoded cố định:
request:
  body:
    fullName: Trần Văn A
    quantity: 2
~~~

Map có ý nghĩa cấu trúc khác chuỗi form `fullName=...&quantity=2`; tùy Content-Type, SCC có thể xử lý nó thành dữ liệu kiểu JSON, làm thay đổi bytes mà producer nhận.

### Khi body rất dài

Có thể cân nhắc dùng tệp tài nguyên riêng qua cơ chế `bodyFromFile` của YAML DSL hoặc `body(file(...))` của Groovy DSL nếu phiên bản đang dùng hỗ trợ cách nạp tương ứng với payload text. Tệp đó nên chứa **chuỗi form đã mã hóa**, không phải JSON chỉ vì extension giống ví dụ khác. Cần xác nhận generated test và stub giữ nguyên body, nhất là ký tự `&`, `+` và `%`.

Không nên tạo đồng thời hai tệp Groovy và YAML có cùng một tình huống chỉ để so sánh cú pháp trong dự án; chúng có thể được sinh thành hai contract trùng lặp. Hai ví dụ ở trên là **hai cách thay thế nhau**.

## 8. Cách gửi form an toàn từ Spring RestClient

Với ứng dụng Spring dùng **RestClient**, ưu tiên gửi dữ liệu **chưa mã hóa** bằng `MultiValueMap<String, String>`. Spring `FormHttpMessageConverter` sẽ thực hiện form encoding thay vì để lập trình viên tự nối chuỗi.

~~~java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

public class ReservationClient {
    private final RestClient restClient;

    public ReservationClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public PreviewResponse preview() {
        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("fullName", "Trần Văn A");
        form.add("note", "Khuyến mãi 10% & giao nhanh");
        form.add("quantity", "2");

        return restClient.post()
                .uri("/api/reservations/preview")
                .contentType(MediaType.parseMediaType(
                        "application/x-www-form-urlencoded; charset=UTF-8"))
                .accept(MediaType.APPLICATION_JSON)
                .body(form)
                .retrieve()
                .body(PreviewResponse.class);
    }

    public record PreviewResponse(
            String fullName, String note, int quantity, String status) {}
}
~~~

Những điểm đáng kiểm chứng:

1. `form.add("note", "Khuyến mãi 10% & giao nhanh")` dùng **chuỗi gốc**. Converter sẽ xử lý ký tự `%`, `&` và dấu tiếng Việt.
2. `MultiValueMap` hỗ trợ **nhiều giá trị cùng tên trường**, khác với `Map<String, String>` chỉ chứa một giá trị trên mỗi key.
3. Request phải có media type form; nếu gửi `application/json` thì cơ chế chuyển đổi body sẽ khác.
4. Trường số lượng ở form là chuỗi `"2"`, Spring MVC có thể chuyển thành `int` khi ánh xạ tham số.
5. RestClient có trong các phiên bản Spring Framework tương ứng; dự án cũ có thể sử dụng `RestTemplate` hoặc `WebClient`, nhưng nguyên tắc vẫn là giao việc mã hóa cho thư viện.

**Tránh mã hóa trước rồi đưa lại vào converter:**

~~~java
// SAI: dữ liệu đã mã hóa có thể bị mã hóa thêm một lần.
form.add("fullName", "Tr%E1%BA%A7n+V%C4%83n+A");
~~~

Nếu converter mã hóa dấu `%` thành `%25`, server sẽ nhận chuỗi gần dạng `Tr%E1%BA%A7n+V%C4%83n+A` sau khi giải mã **một lần**, thay vì `Trần Văn A`. Đây là lỗi **double encoding**.

## 9. Producer Spring MVC nhận form như thế nào?

Một producer có thể định nghĩa controller dùng `@RequestParam` hoặc `@ModelAttribute` để đọc các field form. Ví dụ đơn giản:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReservationPreviewController {

    @PostMapping(
        path = "/api/reservations/preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public PreviewResponse preview(
            @RequestParam("fullName") String fullName,
            @RequestParam("note") String note,
            @RequestParam("quantity") int quantity) {

        return new PreviewResponse(
            fullName, note, quantity, "ACCEPTED");
    }

    public record PreviewResponse(
            String fullName, String note, int quantity, String status) {}
}
~~~

Trong kịch bản này, Spring MVC đọc body form, giải mã và ánh xạ `fullName`, `note`, `quantity` thành tham số. Nếu hợp đồng gửi đúng body, producer test sẽ thấy response JSON chứa đúng **chữ tiếng Việt sau giải mã**.

Lưu ý: `@RequestParam` trong Spring MVC cũng có thể lấy tham số trên URL. Để chắc chắn producer đang nhận **body form**, hãy kiểm tra request có Content-Type chính xác và body thực tế đã được gửi, thay vì chỉ gọi endpoint với `?fullName=...` rồi kết luận hợp đồng form đã được kiểm thử.

Nếu sử dụng `@RequestBody` để nhận DTO JSON thông thường mà client lại gửi `application/x-www-form-urlencoded`, converter phù hợp với JSON có thể không được chọn; đó là sai khác trong giao thức giữa consumer và producer.

## 10. Tự thử request bằng curl

Bạn có thể tạo request thủ công bằng `curl` khi chạy ứng dụng producer cục bộ:

~~~bash
curl -X POST \
  'http://localhost:8080/api/reservations/preview' \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  --data-urlencode 'fullName=Trần Văn A' \
  --data-urlencode 'note=Khuyến mãi 10% & giao nhanh' \
  --data-urlencode 'quantity=2'
~~~

`--data-urlencode` xử lý **giá trị gốc** để tạo body form. Ví dụ shell trên dùng cách xuống dòng của Bash; trên Windows PowerShell hoặc CMD cần thay cách quote/tiếp dòng phù hợp và có thể gọi `curl.exe` tường minh.

Kiểm tra response mong đợi:

~~~json
{
  "fullName": "Trần Văn A",
  "note": "Khuyến mãi 10% & giao nhanh",
  "quantity": 2,
  "status": "ACCEPTED"
}
~~~

Để kiểm tra chính xác bytes được gửi đi, xem trace HTTP trên môi trường test an toàn, ví dụ dùng `curl --trace-ascii` với dữ liệu giả lập. Chú ý `curl` tự thêm header `Content-Type: application/x-www-form-urlencoded` trong một số trường hợp; nếu contract yêu cầu charset, nên đặt header tường minh như ví dụ.

### Gửi body thủ công đã mã hóa

~~~bash
curl -X POST \
  'http://localhost:8080/api/reservations/preview' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Accept: application/json' \
  --data-raw 'fullName=Tr%E1%BA%A7n+V%C4%83n+A&note=Khuy%E1%BA%BFn+m%C3%A3i+10%25+%26+giao+nhanh&quantity=2'
~~~

Với `--data-raw`, bạn cung cấp **body đã mã hóa**; không dùng `--data-urlencode` một lần nữa lên toàn bộ chuỗi, vì dấu phân cách `&` và các `%HH` có thể bị biến đổi.

## 11. Matcher, so khớp body và mức độ linh hoạt của stub

Trong SCC, matcher có thể xuất hiện ở request hoặc response nhưng mang mục đích khác nhau:

| Phía | Mục đích | Đặc điểm với form |
|---|---|---|
| **Request** | Stub kiểm tra request consumer gửi có phù hợp tình huống không | Body là form string, cần đối chiếu đúng bytes/cơ chế mapping |
| **Response** | Generated producer test kiểm tra producer trả đúng status, header, body | Response có thể là JSON, dùng JSONPath matcher nếu đúng là JSON |
| **Client-side logic** | Consumer test kiểm tra client đọc response và xử lý nghiệp vụ | Nên dùng HTTP client thật, tránh chỉ thử `curl` |

Đặc biệt, **đừng dùng JSONPath `$.fullName` trên body form** rồi cho rằng SCC sẽ hiểu nó như JSON. Cần kiểm tra xem version SCC đang dùng sinh WireMock mapping cho form text như thế nào. Nếu dự án cần chấp nhận nhiều biến thể tương đương về encoding hoặc thứ tự field, cách so khớp body thô có thể quá chặt.

Ví dụ hai body này có thể cho cùng dữ liệu sau giải mã:

~~~text
fullName=Minh+Anh&quantity=2
quantity=2&fullName=Minh%20Anh
~~~

Về **ý nghĩa form**, hai request đều có `fullName="Minh Anh"` và `quantity="2"`. Về **chuỗi raw body**, chúng khác thứ tự và cách encode khoảng trắng. Vì vậy:

- Nếu contract muốn khóa chặt biểu diễn raw body, so khớp literal có thể là chủ đích.
- Nếu contract chỉ muốn xác minh **tên–giá trị sau giải mã**, cần lựa chọn khả năng form-parameter matching phù hợp của WireMock/SCC phiên bản đang dùng, hoặc thêm integration test kiểm tra phía producer và HTTP client thực tế; đừng giả định SCC tự chuẩn hóa raw body.
- Khi stub được sinh, kiểm tra **mapping artifact** để biết nó match body kiểu gì và cần header nào.
- Các test consumer nên chạy thêm biến thể trường lặp, khoảng trắng `+`/`%20` hoặc thứ tự field nếu điều đó thuộc cam kết tương thích.

Ở những trường hợp phức tạp, nên tách hai lớp kiểm tra: contract khẳng định một **tình huống mẫu rõ ràng**, còn integration tests kiểm tra các biến thể encoding mà API cho phép.

## 12. Các tình huống biên dễ phá tương thích

### 12.1. Dấu cộng thật và khoảng trắng

~~~text
source value:       a+b
encoded value:      a%2Bb
decoded by server:  a+b

source value:       a b
encoded value:      a+b
decoded by server:  a b
~~~

Nếu client gửi `a+b` **chưa escape** trong form body với ý định là dấu cộng thật, server thường giải mã nó thành `a b`. Điều này gây lỗi rõ rệt với email chứa dấu cộng, mã SKU có dấu `+` hoặc chuỗi biểu thức.

### 12.2. Dấu `&` và `=` nằm trong giá trị

~~~text
source note: a+b&c=d
wire note:   a%2Bb%26c%3Dd
~~~

Nếu viết `note=a+b&c=d` trực tiếp, server có thể tách thành hai field `note` và `c`, rồi hiểu dấu cộng thành khoảng trắng. Đây là **lỗi khác cấu trúc request**, không chỉ là sai dấu câu.

### 12.3. Field vắng mặt và field rỗng

~~~text
quantity=2               -> không có trường note
quantity=2&note=          -> note có mặt, giá trị chuỗi rỗng
quantity=2&note=%20       -> note là một dấu cách
~~~

Producer có thể xử lý các trường hợp trên khác nhau, nhất là khi validation quy định `required`, `not blank` hoặc default value. Nên viết contract cho các trường hợp quan trọng thay vì cho rằng chúng tương đương.

### 12.4. Nhiều giá trị cùng một key

~~~text
tag=gift&tag=express&quantity=2
~~~

Form URL-encoded cho phép gửi **lặp tên trường**. Trong Spring client, `MultiValueMap` có thể tạo nhiều giá trị:

~~~java
MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
form.add("tag", "gift");
form.add("tag", "express");
form.add("quantity", "2");
~~~

Producer có thể nhận bằng `@RequestParam("tag") List<String> tags` nếu mapping phù hợp. `Map<String, String>` không biểu diễn được nhiều giá trị cùng tên; chuyển sang map thường sẽ mất dữ liệu.

### 12.5. Dấu xuống dòng và ký tự Unicode

Dấu xuống dòng, tab, emoji hoặc chữ có dấu cần được mã hóa theo bytes. Ví dụ dấu LF có thể xuất hiện dưới dạng `%0A`; tuy nhiên một client gửi textarea có thể chuẩn hóa xuống dòng thành CRLF trước khi mã hóa. Nếu hợp đồng cần phân biệt chính xác, phải xem request thực tế và thống nhất quy tắc chuẩn hóa.

### 12.6. Mã hóa một lần hay hai lần

~~~text
Unicode:          Cà phê sữa
Encoded once:     C%C3%A0+ph%C3%AA+s%E1%BB%AFa
Encoded twice:    C%25C3%25A0%2Bph%25C3%25AA%2Bs%25E1%25BB%25AFa
~~~

Dòng thứ hai chỉ minh họa hậu quả của việc percent-encode thêm trên dữ liệu đã được form-encode: server giải mã một lần sẽ vẫn còn ký tự `%`, `+` ở dạng text. Không tự gọi `URLEncoder.encode` rồi đưa kết quả cho `FormHttpMessageConverter` nếu converter sẽ encode tiếp.

## 13. Thư viện Java khi cần tự mã hóa một thành phần

Trong trường hợp bạn thật sự cần tự tạo một phần body form (ví dụ kiểm thử byte-level), Java có `URLEncoder`:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String value = "a+b&c=d";
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);

// encoded: a%2Bb%26c%3Dd
~~~

**Quan trọng:** `URLEncoder` áp dụng quy tắc **HTML form encoding**, trong đó khoảng trắng thành `+`; nó không tương đương mọi trường hợp với percent encoding của path URI.

Muốn ghép body thủ công, phải mã hóa **từng tên và từng giá trị** rồi mới nối bằng `=` và `&`. Không được mã hóa toàn bộ body đã ghép, bởi vì như vậy dấu phân cách cấu trúc cũng bị escape.

~~~java
String body =
    URLEncoder.encode("fullName", StandardCharsets.UTF_8) + "="
    + URLEncoder.encode("Trần Văn A", StandardCharsets.UTF_8)
    + "&"
    + URLEncoder.encode("quantity", StandardCharsets.UTF_8) + "="
    + URLEncoder.encode("2", StandardCharsets.UTF_8);
~~~

Trong mã ứng dụng thông thường, **ưu tiên `MultiValueMap` + converter** vì ít lỗi và hỗ trợ field lặp tự nhiên hơn.

## 14. Những gì generated producer test cần chứng minh

Giả sử contract Groovy/YAML đã được đưa vào đúng thư mục và build plugin Spring Cloud Contract đã cấu hình.

Chuỗi kiểm chứng:

~~~mermaid
flowchart TD
    A["Form contract: POST + header + raw body"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    B --> D["Stub artifact ứng viên"]
    C --> E["Gửi request thực vào producer"]
    E --> F{"Nhận form và trả response đúng?"}
    F -- "Không" --> G["Sửa cấu hình, body, charset hoặc code"]
    D --> H["Consumer test + Stub Runner"]
    H --> I{"Client thật gửi đúng form?"}
    I -- "Không" --> G
    F -- "Có" --> J["Tổng hợp kết quả CI"]
    I -- "Có" --> J
~~~

Khi mở generated test, cần kiểm tra cụ thể:

1. **Method và URL** là POST `/api/reservations/preview`.
2. **Content-Type** của request là form URL-encoded, charset đúng với contract.
3. Request body có **`&` thật** giữa các field, **`%26`** trong giá trị chứa `&`, và biểu diễn Unicode dự kiến.
4. Producer controller thật nhận và giải mã body đúng.
5. Response có status 200, JSON chứa `Trần Văn A`, `Khuyến mãi 10% & giao nhanh` và `quantity: 2`.

Nếu test sinh ra gửi request khác contract, cần kiểm tra trình sinh test của phiên bản SCC, test mode (MockMvc/HTTP/WebTestClient) và cấu hình base class. Với các vấn đề liên quan body text, hãy đọc **source của generated test** thay vì chỉ dựa vào mã exit của build.

Một test xanh mà **không hề sinh hoặc chạy** contract test không phải bằng chứng producer đáp ứng hợp đồng.

## 15. Stub Runner và bài kiểm thử consumer

Sau khi producer tạo stub ứng viên, consumer dùng **Stub Runner** tải artifact đó. Test consumer nên gọi **client form thật** (ví dụ `ReservationClient` dùng `RestClient`) thay vì gửi trực tiếp một request thủ công đã khớp mapping.

Ví dụ cấu hình Stub Runner trong test consumer:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.2.0-rc1:stubs:8081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class ReservationClientContractTest {
    // Dùng ReservationClient thật trỏ đến http://localhost:8081.
    // Assert fullName, note, quantity và status từ response stub.
}
~~~

Với `LOCAL`, stub JAR phải được cài vào kho Maven local trước khi chạy test. Nếu CI tách job, có thể dùng mode `REMOTE` và một repository artifact đã cấu hình. Version trên là ví dụ; khi kiểm tra PR phải dùng **đúng artifact của commit ứng viên**, tránh bản cũ trong cache.

**Điều nên kiểm tra trong consumer test:**

- Client gửi media type form, không phải JSON.
- Client đưa **chuỗi gốc** vào converter; không mã hóa hai lần.
- Body thực tế có các field và giá trị được stub chấp nhận.
- Consumer giải mã **response JSON** và dùng được dữ liệu nghiệp vụ.
- Stub mapping sinh ra thể hiện các điều kiện request mong muốn. Nếu một cách mã hóa tương đương không match stub, cần xác định đây là giới hạn/độ chặt của mapping hay lỗi thực sự của consumer.

## 16. Thay đổi API nào có thể làm hỏng consumer?

| Thay đổi | Vì sao có thể breaking? | Cách kiểm chứng |
|---|---|---|
| Producer đổi `consumes` từ form sang JSON-only | Consumer cũ vẫn gửi `application/x-www-form-urlencoded` và có thể nhận 415 | Test với client form hiện hành và stub/version producer ứng viên |
| Đổi tên field `fullName` thành `recipientName` | Client cũ không gửi tên mới, validation/binding có thể lỗi | Contract giữ field cũ, thêm contract giai đoạn chuyển đổi |
| Chuyển từ `note` tùy chọn sang bắt buộc | Consumer cũ không gửi `note` bị từ chối | Thêm test request thiếu `note` |
| Bỏ hỗ trợ field lặp `tag` | Consumer gửi nhiều giá trị bị mất/thất bại | Test `tag=gift&tag=express` |
| Đổi logic decode `+` hoặc charset | Email/mã có dấu `+`, tên tiếng Việt có thể biến đổi | Test Unicode, literal plus và ký tự đặc biệt |
| Chỉ thay encoding `+` thành `%20` | Server có thể decode giống nhau nhưng stub raw-body không match | So sánh decoded fields và WireMock mapping |
| Đổi response JSON từ `status` sang `state` | Consumer hiện tại có thể không giải mã được field | Chạy consumer test với stub ứng viên |

Tương thích giao tiếp là điều kiện đồng thời của **cách gửi request** và **cách consumer đọc response**. Một test producer xanh sau khi cập nhật contract mới chưa chứng minh các consumer cũ vẫn hoạt động.

Với thay đổi lớn như chuyển form sang JSON, cách tiến hóa an toàn thường là **hỗ trợ đồng thời hai kiểu media type trong giai đoạn chuyển đổi**, kiểm tra client cũ và client mới, rồi ngừng kiểu cũ khi không còn consumer cần hỗ trợ.

## 17. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra | Hành động |
|---|---|---|
| Server nhận `"a b"` thay vì `"a+b"` | Dấu `+` literal chưa được encode thành `%2B` | Dùng form converter hoặc `URLEncoder` cho từng giá trị |
| Server nhận chuỗi `%E1%BA...` thay vì tiếng Việt | Client đã encode hai lần hoặc server decode sai | Gửi chuỗi gốc qua converter; kiểm tra charset và raw body |
| Controller nhận `null` ở các field | Sai Content-Type, client gửi JSON/query thay vì form body, hoặc test mode không gửi body thật | Xem request HTTP thực tế và cách bind controller |
| Body biến `&` thành `&amp;` trong generated test | Lỗi escape ở công cụ sinh test/phiên bản cũ | Kiểm tra generated code, nâng plugin phù hợp, tránh sửa payload thành HTML |
| Server nhận thêm field ngoài ý muốn | Dấu `&` trong value chưa mã hóa thành `%26` | Encode tên và giá trị riêng rẽ |
| Stub không match dù server thật nhận được | Stub so khớp raw body, thứ tự field hoặc biểu diễn `+`/`%20` khác | Kiểm tra WireMock mapping và raw body thực của client |
| CI xanh khi đổi contract nhưng consumer thật lỗi | Stub Runner vẫn dùng artifact phiên bản cũ | Ghim version/commit ứng viên; kiểm tra log tải stub |
| `quantity` chuyển thành `int` lỗi | Form gửi `two`, rỗng hoặc sai kiểu | Kiểm tra validation và tạo contract lỗi riêng |
| Form không nhận file upload | API cần multipart nhưng client gửi URL-encoded | Chuyển sang `multipart/form-data` theo API và viết contract riêng |
| Chữ tiếng Việt sai sau round trip | Charset không đồng nhất, normalize không thống nhất, double encoding | Kiểm tra UTF-8 trên cả hai đầu và bytes ở môi trường test |

Thứ tự chẩn đoán hữu ích: **URL và header → raw body → percent decoding → tham số controller → generated test → stub mapping → consumer client**.

## 18. Bài thực hành: kiểm chứng form có Unicode

**Bối cảnh:** Inventory Service nhận POST form để xem trước yêu cầu giữ hàng; Checkout Service gọi API đó với người nhận và ghi chú bằng tiếng Việt.

### Vòng A — Tạo form contract

1. Viết Groovy hoặc YAML contract cho `POST /api/reservations/preview`.
2. Khai báo `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`.
3. Dùng các giá trị:
   - `fullName = "Trần Văn A"`
   - `note = "Khuyến mãi 10% & giao nhanh"`
   - `quantity = "2"`
4. Mã hóa từng giá trị rồi ghép body theo cú pháp form.
5. Khai báo response JSON chứa các giá trị **đã giải mã**.

**Kỳ vọng:** generated producer test gửi body đúng, controller nhận đúng tiếng Việt, response thỏa contract.

### Vòng B — Xác nhận khả năng gửi form của consumer

1. Tạo `ReservationClient` dùng `MultiValueMap<String, String>`.
2. Đưa **chuỗi Unicode gốc** vào map và để HTTP converter mã hóa.
3. Cho Stub Runner tải đúng stub ứng viên từ producer.
4. Chạy consumer test với client thật, assert response.
5. Đối chiếu raw request với contract, xác nhận dấu cộng, dấu phần trăm và dấu `&` được xử lý đúng.

**Kỳ vọng:** consumer test chứng minh code thực tế có thể gửi form phù hợp và sử dụng response.

### Vòng C — Thử tình huống phá tương thích

1. Đổi tên request field `fullName` thành `recipientName` trong producer.
2. Chạy producer test với contract cũ và ghi nhận sai khác.
3. Nếu cập nhật cả contract theo producer, sinh stub mới rồi chạy test consumer cũ.
4. Đề xuất kế hoạch hỗ trợ song song hai tên field trước khi xóa tên cũ.
5. Thử thêm `note` chứa literal plus: `"a+b@example.com"`, kiểm tra nó trở thành `a%2Bb%40example.com`.

**Bằng chứng nộp bài:** contract đã viết, raw HTTP request đã mã hóa, generated test report, stub coordinate ứng viên, kết quả consumer test, và giải thích nguyên nhân lỗi khi thiếu mã hóa hoặc mã hóa hai lần.

## 19. Checklist trước khi hợp nhất contract form

- [ ] Request dùng đúng method, path và `Content-Type`.
- [ ] Form fields nằm ở **body** nếu API yêu cầu body, không bị nhầm sang query parameters.
- [ ] Chuỗi Unicode được mã hóa bằng UTF-8 theo quy tắc form.
- [ ] Khoảng trắng, literal plus, `&`, `=` và `%` được xử lý đúng.
- [ ] Client sử dụng `MultiValueMap`/form converter hoặc cách encode tương đương đã kiểm chứng.
- [ ] Không có bước encode thừa trước khi HTTP converter xử lý dữ liệu.
- [ ] Đã phân biệt field thiếu, field rỗng và field lặp khi nghiệp vụ cần.
- [ ] Generated producer test thực sự gửi **form body**, không chỉ query hoặc JSON.
- [ ] Producer nhận và bind các field đã giải mã đúng.
- [ ] Stub artifact được sinh từ đúng contract/commit ứng viên.
- [ ] Consumer test dùng Stub Runner với **client thật** và stub version tương ứng.
- [ ] Kiểm tra thêm các trường hợp encoding tương đương nếu đó là cam kết API.
- [ ] CI chặn việc phát hành khi generated producer test hoặc consumer compatibility test thất bại.

## 20. Câu hỏi tự kiểm tra

**1. Trong application/x-www-form-urlencoded, `+`, `%20` và `%2B` khác nhau thế nào?**

Trong giá trị form, `+` và `%20` đều thường giải mã thành **khoảng trắng**; `%2B` giải mã thành **dấu cộng thật**. Một stub kiểm tra raw bytes có thể phân biệt ba cách biểu diễn.

**2. Vì sao `note=a+b&c=d` không biểu thị một giá trị duy nhất là `a+b&c=d`?**

Vì `+` có nghĩa khoảng trắng và `&` chia các cặp tên–giá trị. Cần mã hóa giá trị thành `a%2Bb%26c%3Dd` rồi ghép sau `note=`.

**3. Tại sao không viết `request.queryParameters` khi API nhận form POST?**

Query parameters nằm trong URL; form POST nằm ở body cùng media type. Hai hình thức có thể được framework gom vào chung API tham số nhưng **không tương đương về giao thức** và yêu cầu của consumer.

**4. Vì sao `bodyMatchers.jsonPath('$.fullName', ...)` không phải lựa chọn mặc định cho request form?**

Vì `application/x-www-form-urlencoded` có body dạng text `key=value&...`, không phải JSON. JSONPath được định nghĩa cho cấu trúc JSON; phải dùng cơ chế matching phù hợp với form và xác minh mapping của phiên bản SCC đang sử dụng.

**5. Khi consumer test xanh với stub trước đó, có đủ để chứng minh producer mới tương thích không?**

Không. Test phải lấy **stub ứng viên được tạo từ contract/code của thay đổi hiện tại** để phát hiện các thay đổi về field, Content-Type, mã hóa hoặc response.

## 21. Tài liệu tham khảo

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): cấu trúc request/response và cách sinh hợp đồng HTTP.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): DSL Groovy/YAML, matcher và các luồng producer/consumer.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): gửi `application/x-www-form-urlencoded` bằng `RestClient`, `MultiValueMap` và converter.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): `FormHttpMessageConverter`.
- [HTML Standard — URL-encoded form encoding](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#url-encoded-form-data): quy tắc encode/decode cặp tên–giá trị.

Lưu ý khi nâng cấp: cơ chế sinh test và stub mapping của SCC có thể thay đổi theo version plugin, nhất là với payload text hoặc matcher nâng cao. Trước khi đặt điều kiện match raw-body trong CI, hãy kiểm tra **generated source và stub mapping** của chính phiên bản dự án sử dụng.

---

**Điểm cần nhớ:** Form URL-encoded là **các cặp tên–giá trị được mã hóa trong HTTP body**. Khoảng trắng, literal plus, dấu `&`, `=`, `%` và UTF-8 quyết định producer nhận giá trị nào. Trong Spring Cloud Contract, hãy mô tả đúng **Content-Type + raw form body**, chạy generated producer test, kiểm tra stub mới và xác minh **consumer gửi form thật** để phát hiện thay đổi API không tương thích.
