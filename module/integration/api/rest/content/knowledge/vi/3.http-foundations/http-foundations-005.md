# Content-Type, Accept và biểu diễn được trao đổi

## 1. Mục tiêu bài học

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này giúp bạn xác định nội dung đang được gửi là gì và phía gọi chấp nhận nhận lại nội dung nào. Hai câu hỏi đó tương ứng với hai header thường gặp: **`Content-Type`** và **`Accept`**.

Sau bài học, bạn có thể:

- Phân biệt tài nguyên với biểu diễn của tài nguyên được truyền qua HTTP.
- Đặt và đọc `Content-Type`, `Accept` đúng chiều request và response.
- Hiểu việc thương lượng nội dung khi một tài nguyên có nhiều biểu diễn.
- Chẩn đoán lỗi kiểu nội dung, lỗi phân tích body và lỗi không có biểu diễn đáp ứng yêu cầu của client.
- Viết client Java xử lý phản hồi dựa trên cả status, header và body.
- Mô tả các kiểu nội dung được hỗ trợ trong hợp đồng API dùng Java/Spring hoặc công nghệ tương đương.

## 2. Tài nguyên, biểu diễn và các byte truyền đi

### 2.1. URI xác định tài nguyên

Giả sử URI sau xác định một sản phẩm:

```text
/products/P-100
```

Tài nguyên đó có những thông tin như mã sản phẩm, tên và giá. Server có thể truyền một biểu diễn của nó bằng JSON:

```json
{
  "id": "P-100",
  "name": "Sổ tay",
  "unitPrice": 125000,
  "currency": "VND"
}
```

Hoặc, nếu API hỗ trợ, server có thể cung cấp biểu diễn XML cho cùng tài nguyên. Đổi định dạng phản hồi không nhất thiết có nghĩa là đổi sang một sản phẩm khác.

Biểu diễn cũng không bắt buộc chứa toàn bộ bản ghi cơ sở dữ liệu. Nó có thể chỉ cung cấp các trường thuộc hợp đồng và được phép công khai cho người gọi.

### 2.2. Đối tượng trong chương trình không tự trở thành nội dung HTTP

Một object Java hoặc JavaScript cần được chuyển thành dạng truyền phù hợp:

```text
Đối tượng trong ứng dụng
  -> tuần tự hóa thành JSON hoặc định dạng đã chọn
  -> mã hóa thành các byte
  -> gửi qua HTTP cùng metadata
  -> bên nhận đọc metadata và xử lý các byte
  -> phân tích thành dữ liệu theo hợp đồng
```

`Content-Type` mô tả kiểu nội dung. Header này không tự tuần tự hóa object, không sửa body sai cú pháp và không tự định nghĩa ý nghĩa nghiệp vụ của các trường.

Trong ví dụ sản phẩm, hợp đồng quy định `unitPrice` là số nguyên đồng Việt Nam. `application/json` chỉ cho biết cấu trúc được biểu diễn bằng JSON; nó không tự định nghĩa đơn vị tiền.

## 3. Content-Type: kiểu nội dung đang được gửi

### 3.1. Ý nghĩa và cấu trúc

`Content-Type` cho bên nhận biết media type của nội dung đi kèm thông điệp. Cấu trúc thường gặp là:

```text
type/subtype
type/subtype; parameter=value
```

Ví dụ:

| Giá trị | Nội dung được mô tả |
|---|---|
| `application/json` | Dữ liệu theo cú pháp JSON |
| `application/xml` | Dữ liệu theo cú pháp XML |
| `text/plain; charset=utf-8` | Văn bản thuần với bộ ký tự được chỉ rõ |
| `application/x-www-form-urlencoded` | Các cặp tên và giá trị được mã hóa theo định dạng form |
| `multipart/form-data; boundary=example-boundary` | Nội dung nhiều phần với ranh giới được khai báo |
| `application/problem+json` | Chi tiết lỗi theo mô hình Problem Details dạng JSON |

Parameter có ý nghĩa theo media type cụ thể. Ví dụ, `boundary` của multipart tham gia trực tiếp vào cách phân tách các phần trong body; không thể chọn một giá trị header mà body lại dùng ranh giới khác.

### 3.2. Content-Type trong request

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
```

Header mô tả body mà client đang gửi đến server. Server có thể dựa vào nó để chọn bộ đọc JSON và áp dụng hợp đồng tạo đơn.

Nếu client gửi XML nhưng khai báo JSON, metadata và body không thống nhất. Đổi riêng tên header chỉ đúng khi các byte thực sự phù hợp với kiểu được khai báo.

### 3.3. Content-Type trong response

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /orders/ord_8421

{
  "id": "ord_8421",
  "status": "PENDING",
  "totalAmount": 250000,
  "currency": "VND"
}
```

Lúc này `Content-Type` mô tả body do server trả về. `201 Created` mô tả kết quả HTTP; `PENDING` là trạng thái nghiệp vụ trong biểu diễn đơn hàng.

Request và response là hai thông điệp khác nhau. Chúng có thể có `Content-Type` khác nhau, chẳng hạn request là JSON còn response lỗi là Problem Details dạng JSON.

Các ví dụ trong bài lược bỏ một số chi tiết đóng khung truyền tải và thông tin xác thực. API thực tế vẫn cần cơ chế xác thực, phân quyền và xử lý truyền tải theo thiết kế của hệ thống.

### 3.4. Khi không có body

Một `GET` thông thường không cần body để lấy sản phẩm. Không cần đặt `Content-Type: application/json` chỉ vì muốn nhận JSON.

Tương tự, phản hồi `204 No Content` không mang body. Client không nên luôn gọi bộ phân tích JSON cho mọi phản hồi thành công; cần xét status và việc có nội dung hay không.

Nếu hợp đồng yêu cầu body nhưng request thiếu `Content-Type`, server cần có chính sách xử lý rõ ràng. Không nên giả định mọi server đều tự đoán JSON hoặc đều trả cùng một mã lỗi trong tình huống thiếu header.

## 4. Accept: kiểu phản hồi mà client chấp nhận

### 4.1. Accept không mô tả body request

```http
GET /products/P-100 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Client đang yêu cầu biểu diễn JSON trong phản hồi. Request không có body nhưng `Accept` vẫn có ý nghĩa.

So sánh hai câu:

- `Content-Type: application/json`: nội dung tôi đang gửi có kiểu JSON.
- `Accept: application/json`: tôi chấp nhận nhận lại kiểu JSON.

Một header không thay thế header còn lại.

### 4.2. Dùng đồng thời trong request có body

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json, application/problem+json

{
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
```

Client gửi JSON và chấp nhận hai loại phản hồi: JSON theo hợp đồng thông thường hoặc Problem Details dạng JSON. Việc nêu nhiều media type không bắt buộc server trả nhiều body; server chọn kiểu phù hợp cho phản hồi cụ thể.

### 4.3. Không có Accept và các dạng wildcard

| Header trong request | Ý nghĩa cơ bản |
|---|---|
| Không có `Accept` | Không đặt giới hạn media type bằng header này |
| `Accept: */*` | Chấp nhận mọi media type theo phạm vi wildcard |
| `Accept: application/*` | Chấp nhận các media type thuộc nhóm `application` |
| `Accept: application/json` | Chấp nhận media type được nêu cụ thể |

Không có `Accept` không đồng nghĩa với “bắt buộc JSON”. Server có thể dùng biểu diễn mặc định mà hợp đồng hoặc cấu hình đã quy định.

Wildcard cũng không bổ sung khả năng xử lý cho client. Nếu client thực tế chỉ có bộ đọc JSON, gửi `Accept: */*` rồi mặc định mọi phản hồi là JSON sẽ tạo ra một hợp đồng không nhất quán.

### 4.4. Mức ưu tiên q

```http
Accept: application/json, application/xml;q=0.5
```

Trong danh sách này, JSON có trọng số mặc định `1`; XML có trọng số `0.5`. Client thể hiện ưu tiên JSON hơn XML. `q` là mức ưu tiên thương lượng, không phải tỷ lệ nén, mức chính xác của dữ liệu hoặc thời gian chờ.

Giá trị `q=0` thể hiện không chấp nhận kiểu tương ứng. Quy tắc khớp còn xét mức cụ thể của media range, không chỉ chọn số `q` lớn nhất nhìn thấy trong cả header.

Ví dụ:

```http
Accept: application/*;q=0.9, application/json;q=0.4
```

Media range cụ thể `application/json` xác định trọng số `0.4` cho JSON. Một biểu diễn XML phù hợp với `application/*` có thể có trọng số `0.9`. Không nên gán `0.9` cho JSON chỉ vì nó cũng nằm trong nhóm `application`.

Server còn xét các biểu diễn thực sự có thể cung cấp và chính sách thương lượng. Bên gọi luôn cần đọc `Content-Type` thực tế của response thay vì suy rằng kiểu được đặt đầu tiên chắc chắn được trả về.

## 5. Thương lượng nội dung cho cùng một tài nguyên

### 5.1. Client chọn JSON

```http
GET /products/P-100 HTTP/1.1
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: Accept

{
  "id": "P-100",
  "name": "Sổ tay",
  "unitPrice": 125000,
  "currency": "VND"
}
```

### 5.2. Client chọn XML

Giả sử endpoint cũng hỗ trợ XML:

```http
GET /products/P-100 HTTP/1.1
Accept: application/xml
```

```http
HTTP/1.1 200 OK
Content-Type: application/xml
Vary: Accept

<product>
  <id>P-100</id>
  <name>Sổ tay</name>
  <unitPrice>125000</unitPrice>
  <currency>VND</currency>
</product>
```

Hai response biểu diễn cùng sản phẩm theo các định dạng khác nhau. API vẫn phải định nghĩa ý nghĩa dữ liệu cho mỗi biểu diễn; không thể giả định mọi phép chuyển đổi JSON và XML đều giữ nguyên toàn bộ quy tắc nếu chưa thiết kế.

### 5.3. Vì sao có Vary: Accept?

Khi lựa chọn biểu diễn phụ thuộc `Accept`, `Vary: Accept` giúp cache biết rằng các request đến cùng URI có thể cần những biến thể khác nhau theo header này.

Nếu một phản hồi JSON được dùng nhầm cho client chỉ chấp nhận XML, body có thể không xử lý được. `Vary` hỗ trợ phân biệt biến thể; nó không tự cấp quyền lưu cache và không thay thế các quy tắc `Cache-Control` hoặc quy tắc đối với dữ liệu riêng tư.

Một API chỉ hỗ trợ JSON không bắt buộc bổ sung XML để được coi là REST. Thương lượng nội dung chỉ lựa chọn giữa những biểu diễn mà server thực sự hỗ trợ.

## 6. Phân biệt các lỗi liên quan đến nội dung

### 6.1. 415 Unsupported Media Type: kiểu nội dung gửi đến không được hỗ trợ

Giả sử `POST /orders` chỉ nhận `application/json`, nhưng client gửi:

```http
POST /orders HTTP/1.1
Content-Type: application/xml
Accept: application/json, application/problem+json

<order>
  <productId>P-100</productId>
  <quantity>2</quantity>
</order>
```

Server có thể trả `415 Unsupported Media Type` vì kiểu nội dung của request không được endpoint hỗ trợ. Đổi `Accept` không sửa được lỗi này; cần gửi body theo kiểu được hỗ trợ và khai báo đúng `Content-Type`.

### 6.2. 406 Not Acceptable: không có phản hồi đáp ứng thương lượng

Giả sử `GET /products/P-100` chỉ cung cấp JSON, còn client gửi:

```http
GET /products/P-100 HTTP/1.1
Accept: application/xml
```

Nếu server áp dụng chính sách tôn trọng chặt yêu cầu thương lượng, nó có thể trả `406 Not Acceptable`. Lỗi nằm ở việc không có biểu diễn phản hồi phù hợp, không phải body request, vì request này không cần body.

HTTP cũng cho phép server lựa chọn bỏ qua yêu cầu thương lượng trong tình huống không có lựa chọn phù hợp. Vì vậy, hành vi cụ thể cần được thống nhất và xác minh theo API; không nên giả định mọi server luôn trả `406` khi `Accept` không khớp.

### 6.3. 400 Bad Request: không phân tích được JSON đã khai báo

```http
POST /orders HTTP/1.1
Content-Type: application/json

{
  "items": [
}
```

Endpoint hỗ trợ JSON, nhưng body không đúng cú pháp. Với hợp đồng chọn cách xử lý này, server trả `400 Bad Request` khi không thể phân tích nội dung thành dữ liệu đầu vào.

Không nên gộp tình huống này với việc endpoint hoàn toàn không hỗ trợ JSON. Hai lỗi dẫn đến hai cách sửa khác nhau.

### 6.4. JSON hợp lệ vẫn có thể sai dữ liệu

```json
{
  "items": [
    {
      "productId": "P-100",
      "quantity": 0
    }
  ]
}
```

Đây là JSON hợp lệ, nhưng số lượng có thể vi phạm hợp đồng yêu cầu số nguyên dương. API có thể chọn `400 Bad Request` hoặc một mã phù hợp khác như `422 Unprocessable Content` theo chính sách được tài liệu hóa.

Không thể sửa lỗi số lượng bằng cách đổi `Content-Type`. Phân tích được cú pháp và chấp nhận được dữ liệu là hai bước khác nhau.

### 6.5. Bảng chẩn đoán nhanh

| Quan sát | Câu hỏi cần kiểm tra trước |
|---|---|
| Nhận `415` | Body đang dùng kiểu nào, `Content-Type` khai báo gì, endpoint nhận những kiểu nào? |
| Nhận `406` | `Accept` cho phép những kiểu nào, server có thể trả những biểu diễn nào? |
| Nhận lỗi phân tích body | Các byte có thực sự phù hợp cú pháp và mã hóa đã chọn không? |
| Nhận lỗi trường dữ liệu | Schema và quy tắc nghiệp vụ yêu cầu giá trị nào? |
| Client không đọc được body | Response có đúng `Content-Type`, có body và có đúng kiểu đã thương lượng không? |

Mã lỗi là điểm bắt đầu chẩn đoán. Chi tiết còn phụ thuộc hợp đồng và cách xử lý thực tế của endpoint; chỉ nhìn một header thường chưa đủ kết luận.

## 7. Kiểu phản hồi lỗi cần được thống nhất riêng

### 7.1. Thành công và thất bại có thể dùng các media type khác nhau

Với request tạo đơn, một lỗi đầu vào có thể là:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-order",
  "title": "Dữ liệu đơn hàng không hợp lệ",
  "status": 400,
  "detail": "Số lượng sản phẩm phải lớn hơn 0."
}
```

`application/problem+json` có mô hình ngữ nghĩa lỗi riêng và dùng cú pháp JSON. Nó không đồng nghĩa hoàn toàn với một response đơn hàng có media type `application/json`.

Client phải kết hợp:

1. Mã HTTP để xác định kết quả xử lý yêu cầu.
2. `Content-Type` để chọn cách đọc body.
3. Hợp đồng để hiểu dữ liệu đã đọc được.

Không nên thấy body bắt đầu bằng `{` rồi luôn ánh xạ nó sang DTO của phản hồi thành công.

### 7.2. Đừng giả định mọi lỗi đều có body mong muốn

Lỗi có thể do HTTP adapter, ứng dụng, gateway hoặc thành phần trung gian trả về. Một lỗi ngoài dự kiến có thể không dùng đúng biểu diễn mà client mong đợi.

Client nên có cách báo lỗi khi media type không được hỗ trợ, đồng thời giữ thông tin chẩn đoán thích hợp. Không nên âm thầm coi một trang HTML là JSON hợp lệ hoặc kết quả nghiệp vụ thành công.

Việc thương lượng phản hồi lỗi cũng cần được thiết kế. Nếu client chỉ chấp nhận một kiểu mà server không thể cung cấp, không nên mặc định rằng vẫn luôn nhận được problem detail dạng JSON trong mọi trường hợp.

## 8. Mã hóa ký tự, nén nội dung và định dạng form

### 8.1. Media type khác mã hóa ký tự

JSON trao đổi giữa các hệ thống dùng UTF-8 theo quy tắc của JSON. Với API JSON, nên phát sinh các byte UTF-8 thực sự và dùng `Content-Type: application/json` phù hợp, thay vì gửi một bộ ký tự khác rồi hy vọng bên nhận tự đoán.

Với những media type có định nghĩa parameter bộ ký tự, chẳng hạn văn bản thuần, có thể gặp:

```http
Content-Type: text/plain; charset=utf-8
```

Không nên coi mọi media type đều có cùng parameter hoặc cùng quy tắc bộ ký tự. Khi tự tạo thông điệp, độ dài nội dung theo byte cũng không nhất thiết bằng số ký tự trong chuỗi, nhất là với tiếng Việt.

### 8.2. Content-Encoding khác Content-Type

```http
Content-Type: application/json
Content-Encoding: gzip
```

Ở đây, biểu diễn là JSON và nội dung đã được mã hóa theo gzip. Bên nhận xử lý lớp gzip rồi đọc JSON. Chỉ đặt `Content-Encoding: gzip` mà không nén nội dung thực sự sẽ làm thông điệp không nhất quán.

Tương tự, `Accept-Encoding` liên quan đến các content coding mà client chấp nhận, còn `Accept` liên quan đến media type. Đề nghị nhận gzip không có nghĩa là đề nghị nhận JSON.

### 8.3. Dữ liệu form không tự trở thành JSON

Body sau có thể thuộc định dạng form:

```text
productId=P-100&quantity=2
```

Nó không phải JSON. Nếu gửi với `Content-Type: application/json`, bộ đọc JSON không có cơ sở để xem đó là một object hợp lệ.

Với `multipart/form-data`, các công cụ tạo request thường tự sinh boundary và body tương ứng. Khi dùng công cụ như `FormData` trong trình duyệt, cần để công cụ tạo header multipart phù hợp, thay vì tự đặt một `Content-Type` thiếu boundary hoặc không khớp nội dung.

Lựa chọn JSON, form hay multipart phụ thuộc loại dữ liệu và hợp đồng endpoint. Header cần mô tả chính xác định dạng đã chọn.

## 9. Ví dụ client bằng Java

### 9.1. Gửi JSON, khai báo các kiểu phản hồi chấp nhận

Ví dụ dùng HTTP client chuẩn của Java để tạo một đơn. Địa chỉ miền trong mã là địa chỉ minh họa; khi thực hành, thay bằng server thực tế và bổ sung xác thực theo hợp đồng.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

public class OrderApiExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        String requestJson =
                "{\"items\":[{\"productId\":\"P-100\",\"quantity\":2}]}";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.test/orders"))
                .timeout(Duration.ofSeconds(20))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json, application/problem+json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        requestJson, StandardCharsets.UTF_8))
                .build();

        HttpResponse<byte[]> response = client.send(
                request, HttpResponse.BodyHandlers.ofByteArray());

        int status = response.statusCode();
        String contentType = response.headers()
                .firstValue("Content-Type")
                .orElse("");

        System.out.println("HTTP status: " + status);
        System.out.println("Content-Type: " + contentType);

        if (status == 204 || response.body().length == 0) {
            return;
        }

        String baseMediaType = contentType.split(";", 2)[0]
                .trim()
                .toLowerCase(Locale.ROOT);

        if (baseMediaType.equals("application/json")
                || baseMediaType.equals("application/problem+json")) {
            String responseJson = new String(
                    response.body(), StandardCharsets.UTF_8);
            System.out.println(responseJson);
        } else {
            throw new IllegalStateException(
                    "Chưa hỗ trợ kiểu phản hồi: " + contentType);
        }
    }
}
```

### 9.2. Phạm vi xử lý của ví dụ

Mã minh họa khai báo đúng hai chiều, gửi chuỗi JSON bằng UTF-8, đọc status và kiểm tra media type trước khi hiển thị body. Phần tách type/subtype chỉ phục vụ nhận diện hai kiểu cụ thể, không phải bộ phân tích đầy đủ cho mọi cú pháp header HTTP.

Ví dụ chưa phân tích JSON thành DTO và chưa triển khai luồng xử lý nghiệp vụ sau phản hồi. Trong ứng dụng thật:

- Với phản hồi thành công đúng hợp đồng, dùng thư viện JSON đã chọn để đọc biểu diễn đơn hàng.
- Với Problem Details, đọc mô hình lỗi và xử lý theo status cùng loại vấn đề.
- Với phản hồi khác hợp đồng hoặc sai cú pháp, báo lỗi tích hợp phù hợp.
- Với lỗi mạng hoặc timeout, không tự kết luận đơn chắc chắn chưa được tạo; cách tra cứu kết quả và gửi lại cần theo thiết kế idempotency của API.

Việc body đọc được thành chuỗi JSON chưa đủ để coi yêu cầu thành công. Ví dụ chủ động in status riêng để giữ sự phân biệt giữa kết quả HTTP và định dạng nội dung.

## 10. Mô tả và triển khai hợp đồng phía server

### 10.1. Ghi rõ đầu vào và đầu ra

Một phần hợp đồng của API đặt hàng có thể là:

| Thành phần | Hợp đồng ví dụ |
|---|---|
| Endpoint | `POST /orders` |
| Kiểu request body | `application/json` |
| Thành công | `201 Created`, `Location`, body `application/json` |
| Dữ liệu đầu vào không hợp lệ | `400 Bad Request`, body `application/problem+json` theo chính sách lỗi |
| Media type đầu vào không hỗ trợ | `415 Unsupported Media Type` |
| Không có kiểu phản hồi phù hợp | Chính sách thương lượng được mô tả, có thể chọn `406 Not Acceptable` |

OpenAPI có thể mô tả từng media type trong request body và từng nhóm response cùng schema tương ứng. Không nên chỉ viết “API dùng JSON” rồi bỏ qua việc phản hồi lỗi có kiểu gì và body nào được phép vắng mặt.

### 10.2. Áp dụng trong Java/Spring hoặc công nghệ tương đương

HTTP adapter cần phối hợp các quyết định sau:

1. Endpoint chấp nhận những kiểu request nào.
2. Bộ đọc nội dung nào phân tích body thành dữ liệu ứng dụng.
3. Biểu diễn nào có thể được trả theo thương lượng.
4. Status, header và body nào tương ứng với kết quả xử lý.
5. Các nhánh lỗi có giữ đúng hợp đồng phản hồi hay không.

Trong cách cấu hình endpoint thường gặp ở Spring, khái niệm `consumes` liên quan đến kiểu nội dung nhận, còn `produces` liên quan đến các kiểu nội dung có thể trả và việc lựa chọn xử lý theo `Accept`. Cấu hình này cần đi cùng bộ chuyển đổi nội dung thực tế và cơ chế xử lý lỗi phù hợp.

Đặt một giá trị trong cấu hình không tự biến mọi object thành XML, không tự định nghĩa JSON Patch và không bảo đảm mọi exception đã có body Problem Details đúng kiểu.

### 10.3. Tách trách nhiệm kỹ thuật với nghiệp vụ

| Phần xử lý | Câu hỏi chính |
|---|---|
| Định tuyến và thương lượng | Endpoint có hỗ trợ media type này không? |
| Phân tích body | Nội dung có đọc được theo kiểu đã khai báo không? |
| Kiểm tra dữ liệu | Các trường có đúng cấu trúc và giới hạn yêu cầu không? |
| Nghiệp vụ và phân quyền | Người gọi có được thực hiện thao tác và dữ liệu hiện tại có cho phép không? |
| Tạo response | Status, header và biểu diễn nào mô tả đúng kết quả? |

Sự phân chia này giúp xử lý lỗi đúng nguyên nhân. Không nên để lỗi không hỗ trợ XML bị biến thành thông báo “sản phẩm không tồn tại”, hoặc để lỗi quyền truy cập bị che thành lỗi phân tích JSON.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách sửa |
|---|---|
| Muốn nhận JSON nên chỉ đặt `Content-Type` trên GET | Dùng `Accept` để đề nghị kiểu phản hồi |
| Đã đặt header JSON nên object bất kỳ sẽ được gửi thành JSON | Tuần tự hóa dữ liệu đúng và gửi các byte phù hợp |
| Request là JSON thì response chắc chắn cũng là JSON đơn hàng | Đọc status và `Content-Type` của response thực tế |
| Gửi `Accept: */*` nhưng client chỉ biết đọc JSON | Khai báo đúng khả năng hoặc xử lý các kiểu phản hồi đã chấp nhận |
| Body JSON đúng cú pháp thì dữ liệu chắc chắn hợp lệ | Kiểm tra schema, quyền và quy tắc nghiệp vụ riêng |
| Mọi subtype kết thúc bằng `+json` đều có cùng ý nghĩa | Cú pháp JSON chung không làm ngữ nghĩa của các media type tương đương |
| `Accept-Encoding: gzip` là yêu cầu dữ liệu JSON | Phân biệt content coding với media type |
| Nhận `204` vẫn phải phân tích một object JSON rỗng | Tôn trọng phản hồi không có nội dung |
| Đuôi `.json` hoặc query `format=json` luôn quyết định định dạng theo HTTP | Đây có thể là quy ước riêng của API; vẫn cần đọc hợp đồng và `Content-Type` thực tế |

## 12. Bài tập vận dụng

### 12.1. Tìm lỗi trong request

Một client gửi:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/xml

productId=P-100&quantity=2
```

Endpoint chỉ nhận JSON, trả JSON cho thành công và Problem Details dạng JSON cho lỗi.

Hãy xác định:

1. Body thực tế có khớp `Content-Type` không?
2. `Accept` có phản ánh những kiểu phản hồi mà endpoint cung cấp không?
3. Cần sửa header hay cần sửa cả nội dung body?

Một cách sửa nhất quán là:

```http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json, application/problem+json

{
  "items": [
    {
      "productId": "P-100",
      "quantity": 2
    }
  ]
}
```

### 12.2. Chọn cách chẩn đoán

| Tình huống | Hướng xử lý |
|---|---|
| Client gửi XML đến endpoint chỉ nhận JSON | Gửi biểu diễn JSON đúng hợp đồng; kiểm tra `Content-Type` |
| Client chỉ chấp nhận XML, server chỉ cung cấp JSON | Điều chỉnh khả năng chấp nhận hoặc dùng endpoint có biểu diễn phù hợp |
| Server trả HTML lỗi từ gateway | Xử lý lỗi tích hợp theo status và media type; không ánh xạ thành DTO đơn hàng |
| Server trả `201` cùng JSON nhưng thiếu trường bắt buộc theo hợp đồng | Xử lý vi phạm hợp đồng dữ liệu; media type đúng chưa đủ |
| Server trả `204` | Không cố đọc một body JSON không tồn tại |

### 12.3. Tự kiểm tra một tương tác hoàn chỉnh

Trước khi coi một tương tác HTTP là đúng hợp đồng, hãy xác định: client đã gửi những byte gì, chúng được khai báo bằng kiểu nào, client chấp nhận nhận gì, server đã chọn kiểu nào, và status có mô tả đúng kết quả hay không. Sau đó mới kiểm tra cấu trúc cùng ý nghĩa nghiệp vụ của dữ liệu đã đọc được.

`Content-Type` mô tả nội dung đang truyền; `Accept` mô tả lựa chọn phản hồi mà phía gọi chấp nhận. Hai header phối hợp với URI, phương thức, status và hợp đồng dữ liệu để các bên trao đổi đúng biểu diễn, thay vì suy đoán định dạng từ hình dáng body.
