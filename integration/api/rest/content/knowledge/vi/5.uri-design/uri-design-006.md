# Percent-encoding, Unicode và ký tự đặc biệt

## 1. Vì sao thiết kế URI cần quan tâm đến mã hóa?

Trong module `INTEGRATION_API_REST`, URI là một phần của hợp đồng giữa client, API gateway và dịch vụ. Một API có tên resource hợp lý vẫn có thể nhận sai dữ liệu nếu client ghép chuỗi trực tiếp, server giải mã hai lần hoặc các lớp trung gian diễn giải ký tự khác nhau.

Giả sử người dùng tìm sản phẩm bằng cụm từ:

```text
cà phê + trà
```

Ghép trực tiếp cụm từ này vào URL không tạo ra một biểu diễn truyền tải có hợp đồng rõ ràng:

```text
https://api.example.test/products?q=cà phê + trà
```

Khoảng trắng cần được biểu diễn phù hợp; dấu `+` có thể bị bộ giải mã kiểu form hiểu thành khoảng trắng. Với giá trị chứa `&`, lỗi còn có thể làm thay đổi số lượng tham số truy vấn.

Một URI dùng quy ước khoảng trắng là `%20` có thể được tạo thành:

```text
https://api.example.test/products?q=c%C3%A0%20ph%C3%AA%20%2B%20tr%C3%A0
```

Sau khi lớp xử lý HTTP giải mã đúng thành phần query theo UTF-8, ứng dụng nhận lại chính xác `cà phê + trà`.

Sau bài này, người học có thể:

- Phân biệt cấu trúc URI với dữ liệu nằm trong từng thành phần.
- Giải thích percent-encoding dựa trên byte và cách biểu diễn Unicode bằng UTF-8.
- Xử lý đúng khoảng trắng, dấu cộng, dấu phân cách và dữ liệu đã mã hóa.
- Dùng công cụ dựng URI trong Java/Spring mà không ghép chuỗi hoặc giải mã lặp.
- Đặt quy tắc URI nhất quán cho routing, cache, chữ ký và phân quyền resource.

## 2. Tách cấu trúc URI trước khi mã hóa dữ liệu

Xét URI:

```text
https://api.example.test/products/P123?name=green%20tea&limit=20#details
```

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Cách truy cập resource |
| Authority | `api.example.test` | Máy chủ và các thông tin authority nếu có |
| Path | `/products/P123` | Xác định resource trong không gian của máy chủ |
| Query | `name=green%20tea&limit=20` | Dữ liệu truy vấn theo hợp đồng API |
| Fragment | `details` | Tham chiếu được xử lý phía client; không được gửi trong request-target HTTP thông thường |

Trong API trên, `/` phân tách path segment; `&` phân tách cặp query và `=` phân tách tên với giá trị. Quy ước `key=value&key=value` thuộc cách API diễn giải query; cú pháp URI tổng quát không tự quy định query phải là một bản đồ tham số.

Khi `&` là một phần của tên sản phẩm, nó phải được giữ ở vai trò dữ liệu:

```text
Giá trị cần tìm: tea & milk
URI: /products?q=tea%20%26%20milk
```

Nếu ghép thành `/products?q=tea & milk`, bộ phân tích query có thể hiểu dấu `&` là bắt đầu một tham số khác.

Quy trình đúng về mặt thiết kế là:

```text
Dữ liệu nghiệp vụ
    → chọn path segment, tên hoặc giá trị query
    → mã hóa dữ liệu theo thành phần đó
    → ghép thành URI bằng thư viện
```

Không mã hóa toàn bộ chuỗi URL như một giá trị đơn lẻ: làm vậy sẽ biến cả các dấu phân cách cần giữ, chẳng hạn `:` và `/`, thành dữ liệu mã hóa.

## 3. Percent-encoding biểu diễn byte, không biểu diễn trực tiếp ký tự

Một đơn vị percent-encoding có dạng:

```text
%HH
```

`HH` là hai chữ số hệ thập lục phân biểu diễn một byte. Ví dụ, byte `0x20` được viết là `%20`. Hai cách viết `%2F` và `%2f` biểu diễn cùng byte, nhưng nên phát sinh chữ số hex viết hoa để có biểu diễn đầu ra nhất quán.

Với văn bản Unicode trong hợp đồng API dùng UTF-8, có hai bước:

1. Chuyển ký tự thành một hoặc nhiều byte UTF-8.
2. Biểu diễn các byte cần mã hóa bằng `%HH`.

| Dữ liệu | Byte UTF-8 | Biểu diễn percent-encoding |
| --- | --- | --- |
| Khoảng trắng | `20` | `%20` |
| `+` | `2B` | `%2B` |
| `%` | `25` | `%25` |
| `à` | `C3 A0` | `%C3%A0` |
| `ê` | `C3 AA` | `%C3%AA` |
| `đ` | `C4 91` | `%C4%91` |
| `😀` | `F0 9F 98 80` | `%F0%9F%98%80` |

Vì `à` được mã hóa UTF-8 bằng hai byte, kết quả là `%C3%A0`. Cách viết `%E0` không phải biểu diễn UTF-8 hợp lệ của ký tự này; không lấy giá trị Unicode rồi gắn trực tiếp sau dấu `%`.

Ví dụ đầy đủ:

```text
Dữ liệu: cà phê
UTF-8:  63 C3 A0 20 70 68 C3 AA
URI:    c%C3%A0%20ph%C3%AA
```

Các ký tự ASCII `c`, `p`, `h` được giữ nguyên vì có thể xuất hiện trực tiếp ở vị trí này.

### 3.1. Nhóm ký tự không dành riêng

Nhóm unreserved gồm:

```text
A-Z  a-z  0-9  -  .  _  ~
```

Chúng thường được giữ nguyên khi tạo URI. Theo quy tắc chuẩn hóa URI, mã hóa hoặc không mã hóa một ký tự unreserved có thể là hai biểu diễn tương đương, chẳng hạn `%7E` và `~`.

Điều này không bảo đảm mọi gateway, bộ nhớ đệm hoặc ứng dụng đang triển khai đều dùng cùng khóa lưu trữ. API nên phát sinh một biểu diễn chuẩn thay vì để client tùy ý tạo nhiều cách viết.

### 3.2. Nhóm ký tự dành riêng

Các ký tự reserved gồm:

```text
: / ? # [ ] @ ! $ & ' ( ) * + , ; =
```

Không áp dụng quy tắc “luôn giữ nguyên” hoặc “luôn mã hóa” cho toàn bộ nhóm. Quyết định phụ thuộc vào thành phần URI và việc ký tự đang mang nghĩa cấu trúc hay dữ liệu.

Ví dụ:

- `/` phân cách path segment trong `/orders/42/items`.
- `%2F` có thể biểu diễn dấu `/` thuộc dữ liệu của một segment, nhưng cách xử lý encoded slash còn phụ thuộc gateway, server và router.
- `&` phân tách tham số theo hợp đồng query thông dụng.
- `%26` giữ `&` bên trong một giá trị query.
- `#` bắt đầu fragment khi phân tích URL; `%23` giữ dấu thăng như dữ liệu.

Riêng `%` mở đầu percent-encoding, không thuộc nhóm reserved vừa liệt kê. Nếu cần truyền dấu phần trăm như dữ liệu, dùng `%25`.

## 4. Path và query có những điểm cần xử lý khác nhau

### 4.1. Path segment và dấu gạch chéo

Với hợp đồng:

```http
GET /products/{productId}
```

ID `P123` có thể nằm trực tiếp trong một segment:

```text
/products/P123
```

Nếu ID bên ngoài là `A/B`, ghép trực tiếp tạo ra:

```text
/products/A/B
```

Router nhìn thấy hai segment sau `products`; đó có thể là route khác với resource có ID nguyên vẹn `A/B`.

Mã hóa thành `/products/A%2FB` thể hiện ý định giữ slash trong dữ liệu. Tuy nhiên, đây chưa phải bảo đảm hoạt động xuyên suốt: một lớp có thể từ chối encoded slash, giữ nguyên hoặc giải mã trước khi routing. Không thiết kế ID tùy ý chứa `/` rồi giả định mọi hạ tầng đều hỗ trợ giống nhau.

Với API mới, một lựa chọn đơn giản là dùng ID công khai ổn định thuộc tập ký tự dễ truyền tải, chẳng hạn `P123` hoặc UUID, rồi đặt mã bên ngoài vào field dữ liệu riêng. Nếu bắt buộc dùng ID chứa ký tự phân cách, phải quy định rõ khả năng hỗ trợ và kiểm chứng cả tuyến gateway–server–router.

### 4.2. Query value và ký tự phân cách

Ví dụ cần tìm một mã có giá trị:

```text
A&B=1
```

Một biểu diễn query phù hợp là:

```text
/products?externalCode=A%26B%3D1
```

Sau khi phân tích và giải mã giá trị, API nhận được đúng một tham số `externalCode` với nội dung `A&B=1`.

Một query parser không được biến `%26` bên trong giá trị thành dấu phân cách của tham số mới bằng cách giải mã toàn bộ chuỗi trước rồi tách theo `&`.

### 4.3. Fragment và dấu thăng

Hai URL dưới đây mang ý nghĩa khác nhau:

```text
/products?q=C#
/products?q=C%23
```

Ở URL thứ nhất, phần sau `#` thuộc fragment; server không nhận được dấu thăng như một phần của giá trị `q`. Ở URL thứ hai, API có thể nhận `q` bằng `C#` sau giải mã.

Không dùng fragment để gửi filter, token phân trang hoặc định danh mà server cần xử lý.

## 5. Phân biệt `%20`, `+` và `%2B`

Đây là nguồn lỗi phổ biến khi tích hợp Java, trình duyệt và API gateway.

- Trong cú pháp URI tổng quát, dấu `+` không có nghĩa mặc định là khoảng trắng.
- Trong cách mã hóa `application/x-www-form-urlencoded`, khoảng trắng thường được biểu diễn bằng `+`; dấu cộng thật được biểu diễn bằng `%2B`.
- Nhiều framework cũng dùng cách giải mã kiểu form cho tham số query. Vì vậy, gửi dấu `+` thô trong query có thể làm mất dấu cộng thật.

| Giá trị nghiệp vụ | Query theo quy ước dùng `%20` | Query theo quy ước form |
| --- | --- | --- |
| `red tea` | `q=red%20tea` | `q=red+tea` |
| `red+tea` | `q=red%2Btea` | `q=red%2Btea` |
| `C++` | `q=C%2B%2B` | `q=C%2B%2B` |

Nếu muốn API nhận `C++`, cách truyền dấu cộng như dữ liệu rõ ràng là:

```text
/products?q=C%2B%2B
```

Không dùng quy tắc `+ → khoảng trắng` cho path nói chung. Chẳng hạn, dấu cộng trong `/tags/C++` không tự có nghĩa là hai khoảng trắng theo cú pháp path.

Hợp đồng API nên nói rõ cách diễn giải query và charset. Client nên dùng thư viện tương thích với hợp đồng ấy, nhất là khi làm việc với chữ ký hoặc hệ thống ngoài.

## 6. Unicode: biểu diễn truyền tải và quy tắc nghiệp vụ

### 6.1. Thống nhất UTF-8

Một hợp đồng REST API nên quy định UTF-8 cho dữ liệu văn bản trong path và query. Percent-encoding tự nó chỉ mô tả byte; muốn khôi phục văn bản phải biết cách diễn giải các byte ấy.

Ví dụ `%C3%A0` chỉ trở thành `à` khi được diễn giải theo UTF-8 đúng cách. Giải mã các byte bằng charset không phù hợp có thể tạo ra chuỗi sai như `Ã `.

Header `Content-Type: application/json` mô tả nội dung body, không tự quyết định cách mọi proxy và server sẽ giải mã URI. Cấu hình xử lý URI và hợp đồng client vẫn phải thống nhất.

Một số công cụ hiển thị URL có chữ Unicode để dễ đọc rồi tự chuyển sang biểu diễn truyền tải. Không dựa vào hình thức thanh địa chỉ để kết luận dữ liệu thật trên đường truyền; khi kiểm tra, cần phân biệt request-target gốc với tham số ứng dụng đã giải mã.

### 6.2. Cùng hình thức hiển thị có thể khác chuỗi mã Unicode

Từ `café` có thể được biểu diễn bằng:

```text
Dạng dựng sẵn: c a f U+00E9
Dạng tổ hợp:   c a f U+0065 U+0301
```

Hai chuỗi có thể trông giống nhau nhưng có byte UTF-8 khác nhau:

```text
Dạng dựng sẵn: caf%C3%A9
Dạng tổ hợp:   cafe%CC%81
```

Percent-encoding không tự chuẩn hóa Unicode. Nếu resource được định danh bằng slug Unicode, API cần quyết định cách so sánh, lưu trữ và phát sinh slug. Có thể chọn NFC cho một loại dữ liệu văn bản, nhưng đó là quyết định nghiệp vụ được công bố.

Không tự chuẩn hóa mọi chuỗi đầu vào. Chữ ký, token, khóa bất định dạng hoặc ID do hệ thống bên ngoài cấp có thể yêu cầu giữ nguyên từng byte hoặc từng ký tự theo hợp đồng riêng.

### 6.3. Ví dụ chuẩn hóa có chủ đích trong Java

```java
import java.text.Normalizer;

String decomposed = "cafe\u0301";
String normalized = Normalizer.normalize(
        decomposed,
        Normalizer.Form.NFC
);

System.out.println(normalized.equals("caf\u00E9")); // true
```

Chỉ áp dụng đoạn xử lý này ở nơi hợp đồng dữ liệu cho phép. Chuẩn hóa Unicode và percent-encoding là hai bước có mục đích khác nhau: một bước xác định dạng văn bản, bước còn lại biểu diễn byte trong URI.

### 6.4. Tên miền Unicode là một vấn đề riêng

Quy tắc cho hostname quốc tế hóa khác với mã hóa path và query. Không lấy một hostname có dấu rồi percent-encode toàn bộ để tạo tên miền. Việc xử lý hostname cần công cụ hỗ trợ IDN; khi làm việc với API thông thường, có thể dùng hostname ASCII ổn định và xử lý Unicode trong dữ liệu resource.

## 7. Chỉ mã hóa và giải mã tại ranh giới đã xác định

### 7.1. Double encoding

Giá trị nghiệp vụ là `cà`:

```text
Giá trị gốc:          cà
Mã hóa UTF-8 lần một: c%C3%A0
Mã hóa tiếp chuỗi đó: c%25C3%25A0
```

Ở lần thứ hai, các dấu `%` bị xem là dữ liệu và đổi thành `%25`. Server giải mã một lần sẽ nhận chuỗi `c%C3%A0`, chưa phải `cà`.

Lỗi thường xuất hiện khi client tự percent-encode giá trị rồi đưa kết quả vào một URI builder cũng thực hiện encoding.

Một quy tắc dễ duy trì là truyền dữ liệu gốc vào builder và để builder phụ trách mã hóa theo thành phần. Nếu API thư viện có chế độ nhận URI đã mã hóa, cần hiểu đúng chế độ đó; không trộn dữ liệu gốc với dữ liệu đã mã hóa trong cùng một biến không có quy ước.

### 7.2. Double decoding

Xét chuỗi:

```text
%252F
```

Giải mã một lần tạo `%2F`; giải mã lần hai tạo `/`. Nếu tầng phân quyền và tầng routing nhìn thấy hai dạng khác nhau, ứng dụng có thể kiểm tra một resource nhưng truy cập resource khác.

Trong Spring MVC, tham số `@RequestParam` thông thường đã được hạ tầng servlet/framework xử lý từ request. Không gọi thêm `URLDecoder.decode()` lên giá trị này theo thói quen.

Ví dụ, client muốn truyền chuỗi nguyên văn `%2F` thì giá trị query có thể là `%252F`. Ứng dụng cần giữ kết quả `%2F` sau bước giải mã query, không tiếp tục biến nó thành slash.

Việc phân tích URI nên phân biệt cấu trúc trước khi giải mã dữ liệu của từng thành phần. Trong một hệ thống nhiều lớp, cần xác định rõ dạng nào được dùng cho routing, xác thực chữ ký và kiểm tra quyền truy cập.

## 8. Dựng URI an toàn bằng Java/Spring

### 8.1. Truyền giá trị gốc qua URI template

Ví dụ sau dùng `UriComponentsBuilder` của Spring Web. Mã thực hiện encoding trên template trước khi mở rộng biến, nhờ đó các ký tự reserved trong giá trị biến được xử lý như dữ liệu.

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.web.util.UriComponentsBuilder;

public class ProductUriExample {
    public static void main(String[] args) {
        String productId = "P+123";
        String query = "cà phê + trà";

        URI uri = UriComponentsBuilder
                .fromUriString("https://api.example.test")
                .pathSegment("products", "{productId}")
                .queryParam("q", "{q}")
                .encode(StandardCharsets.UTF_8)
                .buildAndExpand(Map.of(
                        "productId", productId,
                        "q", query
                ))
                .toUri();

        System.out.println(uri.toASCIIString());
    }
}
```

Kết quả mong đợi:

```text
https://api.example.test/products/P%2B123?q=c%C3%A0%20ph%C3%AA%20%2B%20tr%C3%A0
```

Những điểm cần giữ trong cách dùng này:

- `productId` và `query` là chuỗi dữ liệu gốc.
- `pathSegment()` thể hiện ranh giới segment thay vì nối ID vào path bằng chuỗi.
- Các giá trị không tin cậy được truyền như biến template; chúng không được chèn trực tiếp vào chuỗi template.
- Gọi `encode()` trên builder trước `buildAndExpand()` là lựa chọn có chủ đích trong ví dụ. Việc chỉ mã hóa một URI đã mở rộng có thể giữ lại các ký tự reserved vốn hợp lệ trong thành phần đó.
- Nếu HTTP client tiếp tục xử lý URI, cần chọn overload nhận `URI` đã dựng hoặc xác định rõ ai chịu trách nhiệm encoding để tránh mã hóa lặp.

Đây là ví dụ cơ chế tạo URI. Với hợp đồng resource thực tế, chỉ thêm `q` vào route chi tiết nếu API có ý nghĩa nghiệp vụ tương ứng; tìm kiếm danh sách sản phẩm thông thường dùng `/products?q=...`.

### 8.2. Không dùng `URLEncoder` như bộ mã hóa mọi thành phần URI

`java.net.URLEncoder` thực hiện mã hóa kiểu `application/x-www-form-urlencoded`. Nó hữu ích khi hợp đồng yêu cầu định dạng ấy, nhưng không phải công cụ mã hóa path tổng quát.

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String encoded = URLEncoder.encode(
        "cà phê + trà",
        StandardCharsets.UTF_8
);

// c%C3%A0+ph%C3%AA+%2B+tr%C3%A0
```

Các dấu `+` không được mã hóa trong kết quả trên đại diện cho khoảng trắng theo quy ước form; `%2B` đại diện cho dấu cộng thật. Nếu dùng kết quả này như path segment rồi kỳ vọng mọi `+` thành khoảng trắng, dữ liệu sẽ sai.

Không tự sửa hàng loạt chuỗi bằng cách thay mọi dấu cộng hoặc mọi `%` sau khi tạo URL. Chọn đúng công cụ và đúng hợp đồng ngay tại bước xây dựng URI.

### 8.3. Controller nhận giá trị đã được xử lý

Đoạn trích sau minh họa một controller Spring MVC; `catalog` và `ProductSummary` là thành phần nghiệp vụ của ứng dụng:

```java
@GetMapping("/products")
public List<ProductSummary> findProducts(@RequestParam String q) {
    // q là giá trị tham số mà framework đã phân tích và giải mã.
    // Ví dụ: "cà phê + trà".
    return catalog.search(q);
}
```

Không thêm `URLDecoder.decode(q, ...)` vào phương thức này chỉ để hỗ trợ tiếng Việt. Nếu nhận sai tiếng Việt, cần kiểm tra charset, request thực tế và cách client dựng URI trước khi thêm một lần decode.

## 9. Hợp đồng lỗi và an toàn qua nhiều lớp

### 9.1. Đầu vào sai cú pháp

Các trường hợp cần được xử lý rõ ràng gồm:

| Đầu vào | Vấn đề |
| --- | --- |
| `%` | Thiếu hai chữ số hex |
| `%2` | Thiếu một chữ số hex |
| `%GG` | Chứa ký tự không phải hex |
| `%C3%28` | Các byte không tạo thành chuỗi UTF-8 hợp lệ |
| `%00` | Byte NUL; không phù hợp với hợp đồng văn bản/ID thông thường |
| `%0D%0A` | CR/LF; không phù hợp với dữ liệu được đưa vào nhiều ngữ cảnh header hoặc log |

Một hợp đồng API có thể chọn trả `400 Bad Request` cho URI hoặc giá trị không hợp lệ. Tuy nhiên, gateway hoặc HTTP server có thể từ chối request trước khi controller chạy. Vì vậy, response cho lỗi ở rìa hệ thống có thể không mang cùng JSON lỗi nghiệp vụ của ứng dụng; tài liệu cần phản ánh khả năng triển khai thực tế.

Không âm thầm sửa UTF-8 lỗi thành ký tự thay thế rồi dùng kết quả làm định danh nếu hợp đồng yêu cầu khớp chính xác. Việc từ chối rõ ràng giúp tránh nhiều chuỗi đầu vào bị nhập làm một ID ngoài ý muốn.

### 9.2. Path traversal và diễn giải không nhất quán

Các segment `.` và `..` có ý nghĩa đặc biệt trong xử lý đường dẫn. Những dạng mã hóa như `%2E%2E` hoặc dữ liệu mã hóa lặp có thể bị các lớp chuẩn hóa khác nhau.

Với API resource thông thường, có thể quy định ID không nhận dot-segment, slash, backslash hoặc ký tự điều khiển nếu chúng không có ý nghĩa nghiệp vụ. Kiểm tra cần áp dụng trên dạng định danh mà ứng dụng thực sự sử dụng, đồng thời thống nhất với gateway và router.

Không ánh xạ trực tiếp một path variable tùy ý sang đường dẫn file. Nếu API cung cấp tài liệu, hãy dùng ID tài liệu để tra metadata và quyền truy cập thay vì coi URI là đường dẫn hệ thống tệp.

Percent-encoding giúp truyền dữ liệu qua URI; nó không làm dữ liệu trở nên đáng tin cậy và không thay thế xác thực, phân quyền, kiểm tra đầu vào hay phòng chống injection.

### 9.3. Cache và chữ ký cần biểu diễn nhất quán

Một URI có thể có nhiều cách viết liên quan đến encoding hoặc thứ tự query. Ví dụ:

```text
/products?q=green%20tea
/products?q=green+tea
```

Hai query có thể tạo cùng giá trị trong một parser kiểu form, nhưng vẫn là hai chuỗi request-target khác nhau. Hệ thống cache hoặc cơ chế ký có thể xử lý chúng khác nhau.

Nếu API dùng chữ ký request, quy tắc canonicalization phải nói rõ những điểm như encoding, thứ tự tham số, tham số lặp, khoảng trắng và dạng Unicode được chấp nhận. Không tự decode rồi encode lại một URL đã được ký nếu giao thức không cho phép.

Tương tự, một ID hoặc khóa idempotency là dữ liệu bất định dạng không nên bị biến đổi tùy tiện. Truyền khóa ở vị trí được hợp đồng chỉ định, chẳng hạn header, và giữ nguyên ngữ nghĩa của khóa đó.

## 10. Thiết kế hợp đồng URI dễ tích hợp

Với API tìm sản phẩm, có thể công bố những quy tắc sau:

```text
Resource: GET /products
Tham số: q, là chuỗi tìm kiếm UTF-8
Khoảng trắng do client phát sinh: %20
Dấu cộng trong dữ liệu: %2B
Ký tự phân cách thuộc dữ liệu: percent-encode theo vị trí
Giá trị q tại controller: văn bản đã được phân tích và giải mã
Đầu vào encoding sai: từ chối theo chính sách tại gateway/server/API
```

Trong OpenAPI, cần mô tả `q` là tham số query và công bố cách serialization mà API hỗ trợ. Ví dụ con người đọc được của giá trị có thể là `cà phê + trà`; URI minh họa trên đường truyền phải giữ được chính giá trị ấy.

Nếu công cụ có tùy chọn cho phép reserved characters trong query, không bật tùy tiện: một dấu `&` hoặc `#` được thả ra ngoài có thể đổi cách phân tích URL. Cần xác định rõ công cụ sẽ serialize thế nào và server sẽ nhận gì.

Khi trả `Location`, link phân trang hoặc URL của resource, server nên dùng thư viện dựng URI với cùng quy tắc encoding. Client sử dụng link do server trả về theo hợp đồng, tránh tự giải mã toàn bộ link rồi ghép lại.

Với cursor phân trang, token nên được xem là dữ liệu opaque. Client không cần hiểu nội dung token; nó chỉ cần đưa nguyên giá trị token vào đúng thành phần URI bằng một builder phù hợp.

## 11. Các tình huống cần kiểm chứng khi tích hợp

Những tình huống dưới đây giúp xác định API có giữ nguyên dữ liệu qua client, proxy và server hay không. Đây là các kết quả mong đợi để thực hành, không phải khẳng định mã ví dụ đã được chạy trong một ứng dụng cụ thể.

| Dữ liệu gốc | Biểu diễn query minh họa | Giá trị ứng dụng cần nhận |
| --- | --- | --- |
| `cà phê` | `q=c%C3%A0%20ph%C3%AA` | `cà phê` |
| `C++` | `q=C%2B%2B` | `C++` |
| `tea & milk` | `q=tea%20%26%20milk` | `tea & milk` |
| `A=B` | `q=A%3DB` | `A=B` |
| `C#` | `q=C%23` | `C#` |
| `100%` | `q=100%25` | `100%` |
| Chuỗi nguyên văn `%2F` | `q=%252F` | `%2F`, không phải `/` |
| `😀` | `q=%F0%9F%98%80` | `😀` |

Ngoài kết quả thành công, nên kiểm chứng:

- URI lỗi percent-encoding và UTF-8 bị từ chối ở lớp nào.
- ID có encoded slash có được hỗ trợ theo hợp đồng hay bị từ chối rõ ràng.
- Hai dạng Unicode tương đương được xử lý theo đúng chính sách nghiệp vụ.
- Tham số lặp như `q=a&q=b` được chấp nhận hay từ chối; không để các lớp chọn giá trị khác nhau khi kiểm tra và xử lý.
- URL đã ký, link phân trang và khóa cache không bị thay đổi ngoài quy tắc đã công bố.

Khi so sánh kết quả, ghi nhận cả URI đã gửi và giá trị controller nhận được. Nếu chỉ kiểm tra giá trị đã giải mã, có thể bỏ sót lỗi ở gateway hoặc quá trình tạo URI. Nếu chỉ xem chuỗi đã mã hóa, có thể bỏ sót lỗi charset và decode lặp trong ứng dụng.

## 12. Ghi nhớ khi áp dụng

Percent-encoding là cách đưa byte vào URI bằng `%HH`. Với văn bản, hãy thống nhất UTF-8; với mỗi giá trị, hãy xác định nó thuộc path segment hay query trước khi mã hóa.

Dấu phân cách chỉ nên giữ vai trò cấu trúc ở vị trí mà hợp đồng quy định. Dấu cộng thật cần được giữ khác với khoảng trắng; dấu thăng thuộc dữ liệu cần tránh bị hiểu thành fragment. Dữ liệu gốc nên đi qua một công cụ dựng URI có trách nhiệm rõ ràng, còn phía server cần tránh giải mã lặp.

Một hợp đồng REST API tốt cũng xác định cách xử lý Unicode, định danh chứa ký tự đặc biệt, URI lỗi và biểu diễn dùng cho cache hoặc chữ ký. Những quy tắc này giúp client và server cùng truy cập đúng resource với đúng giá trị dữ liệu.
