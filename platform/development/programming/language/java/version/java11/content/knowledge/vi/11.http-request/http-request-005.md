# Header nhiều giá trị và quy tắc tên, nội dung trong HTTP Request (Java 11+)

## 1. Tại sao HTTP Request cần hiểu header nhiều giá trị?

Một HTTP request thường mang metadata dưới dạng **header name/value**, ví dụ:

```http
GET /api/items HTTP/1.1
Accept: application/json
Accept: text/plain
X-Trace: request-123
```

Mỗi dòng có **tên header** (ở trái dấu hai chấm) và **giá trị** (ở phải dấu hai chấm). Một số header, ví dụ `Accept`, cho phép nhiều giá trị. Nhưng không phải header nào cũng được lặp tùy ý: ý nghĩa của mỗi header phụ thuộc vào **định nghĩa của chính trường đó** theo chuẩn HTTP.

Từ **Java 11**, mô-đun tiêu chuẩn `java.net.http` cung cấp `HttpRequest`, `HttpRequest.Builder`, `HttpHeaders` và `HttpClient`. Đây vẫn là API hiện hành để xây dựng HTTP request.

```java
import java.net.URI;
import java.net.http.HttpRequest;

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Accept", "application/json")
        .header("Accept", "text/plain")
        .build();
```

`HttpRequest.newBuilder(...)` xây dựng cấu hình request; `build()` tạo đối tượng `HttpRequest` bất biến. **Chỉ `build()` chưa gửi request lên mạng**. Để gửi cần dùng `HttpClient.send(...)` hoặc `sendAsync(...)`; ví dụ kiểm chứng ở bài này chỉ build và đọc header nên chạy được khi không có mạng.

Mục tiêu của bài:

1. Biết khi nào `header()` **thêm** giá trị và khi nào `setHeader()` **thay thế** giá trị.
2. Dùng `headers(String...)` đúng định dạng các cặp tên–giá trị.
3. Truy xuất `HttpHeaders.allValues`, `firstValue` và `map`.
4. Hiểu **tên header không phân biệt hoa–thường**, nhưng **giá trị không được tự diễn giải/split**.
5. Viết đúng **quy tắc tên**, **quy tắc nội dung**, tránh header injection và các header do HTTP client quản lý.

## 2. Ba phương thức trên HttpRequest.Builder

### 2.1. `header(String name, String value)` — thêm một giá trị

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data"))
        .header("Accept", "application/json")
        .header("Accept", "text/plain")
        .build();
```

Mỗi lần `header("Accept", ...)` **thêm** một giá trị vào danh sách của cùng tên, không thay giá trị trước. Khi đọc lại:

```java
System.out.println(request.headers().allValues("Accept"));
// [application/json, text/plain]
```

Đặc biệt, `header("X-Trace", "one")` và `header("x-trace", "two")` có **cùng tên về mặt HTTP**. Tên header không phân biệt chữ hoa/chữ thường; không tạo hai khóa logic độc lập chỉ vì cách viết khác nhau.

### 2.2. `headers(String... headers)` — nhiều cặp tên/giá trị

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data"))
        .headers(
                "Accept", "application/json",
                "Accept", "text/plain",
                "X-Mode", "demo")
        .build();
```

`headers(...)` nhận một dãy `String` với **vị trí chẵn là tên, vị trí lẻ là giá trị**, bắt đầu từ phần tử đầu. Để thêm nhiều giá trị của một tên, phải **lặp lại tên trong từng cặp**.

Đúng:

```java
.headers("Accept", "application/json",
         "Accept", "text/plain")
```

Sai về số lượng phần tử:

```java
// CỐ Ý SAI: 3 chuỗi, không tạo đủ cặp tên–giá trị.
.headers("Accept", "application/json", "X-Mode")
```

Với số lượng đối số lẻ hoặc tên/giá trị không hợp lệ, API ném `IllegalArgumentException`. Không có cơ chế `headers("Accept", "a", "b")` tự hiểu `"b"` là giá trị thứ hai của `Accept`.

### 2.3. `setHeader(String name, String value)` — thay các giá trị cùng tên

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data"))
        .header("X-Trace", "one")
        .header("x-trace", "two")
        .setHeader("X-TRACE", "replacement")
        .build();

System.out.println(request.headers().allValues("x-trace"));
// [replacement]
```

`setHeader(...)` **ghi đè mọi giá trị đã có của tên đó**, đối chiếu tên theo quy tắc không phân biệt hoa–thường. Nếu sau `setHeader` lại gọi `header(...)`, giá trị mới sẽ tiếp tục được **thêm** vào danh sách.

Dùng `setHeader` cho các trường nghiệp vụ phải có **một giá trị cuối cùng**; dùng `header` khi ý nghĩa của trường cho phép nhiều giá trị. Không mặc định rằng một header bất kỳ có thể mang nhiều giá trị chỉ vì Java hỗ trợ thao tác thêm.

### 2.4. Bảng so sánh nhanh

| API trên Builder | Nếu tên chưa có | Nếu tên đã có |
| --- | --- | --- |
| `header(name, value)` | Tạo danh sách một giá trị | **Thêm** giá trị |
| `headers(name1, value1, name2, value2, ...)` | Thêm từng cặp | **Thêm** từng giá trị theo cặp; tên có thể lặp |
| `setHeader(name, value)` | Tạo danh sách một giá trị | **Thay tất cả** giá trị của tên đó |

Đây là **các phương thức chỉnh cấu hình request** trước `build()`. Sau `build()`, đối tượng `HttpRequest` là bất biến; muốn thay header phải cấu hình một request mới hoặc làm việc với một Builder khác. `HttpRequest.Builder` có thể chỉnh sửa nhưng **không được thiết kế để nhiều thread thay đổi đồng thời khi chưa đồng bộ hóa**.

## 3. Quy tắc tên HTTP header (field-name)

Theo **RFC 9110 `5.1**, tên trường HTTP là một **token**, **không phân biệt chữ hoa–chữ thường**. Các tên đơn giản dễ tương tác nhất thường gồm **chữ cái ASCII, chữ số, dấu gạch nối `-` và dấu chấm `.`**, nên ưu tiên tên mô tả rõ chức năng, ví dụ:

```text
Accept
Content-Type
X-Request-Id
Trace-Id
Cache-Control
```

Tập token hợp lệ trong HTTP rộng hơn (theo ngữ pháp `tchar`). Tuy nhiên để dễ tương tác với proxy, gateway và hệ thống ghi log, **không cần dùng những dấu câu ít phổ biến chỉ vì chuẩn cho phép**.

Các ví dụ **sai** về tên:

| Tên đưa vào | Vấn đề |
| --- | --- |
| `Bad Name` | Có dấu cách trong tên |
| `Bad:Name` | Có dấu hai chấm `:`, vốn phân tách tên và giá trị trong cú pháp HTTP/1.1 |
| `Ten Có Dấu` | Tên không phải token ASCII hợp lệ |
| Chuỗi rỗng `""` | Không có tên |

`HttpRequest.Builder.header`, `headers` và `setHeader` kiểm tra tên được cung cấp. Tên không hợp lệ gây `IllegalArgumentException`. Khi xử lý chuỗi do người dùng kiểm soát, **không ghép trực tiếp dữ liệu bất kỳ thành tên header**; nên dùng danh sách tên đã định nghĩa bởi ứng dụng.

**Tên không phân biệt hoa–thường, nhưng không nên phụ thuộc vào cách viết được lưu hay truyền trên mạng.** `HttpHeaders.allValues("ACCEPT")` và `allValues("accept")` truy xuất cùng nhóm giá trị. Với HTTP/2, tên trường trên wire được biểu diễn chữ thường; đừng viết test phụ thuộc nguyên dạng chữ hoa của tên header.

## 4. Quy tắc nội dung (field-value): hợp lệ về cú pháp vẫn phải đúng ngữ nghĩa

Theo **RFC 9110 `5.5**, mỗi header có **ngữ pháp giá trị riêng**. Giá trị có thể là media type, ngôn ngữ, số, danh sách token, thông tin xác thực, v.v. Vì vậy ngoài kiểm tra ký tự, phải đáp ứng **quy tắc riêng của từng trường**.

Ví dụ:

```java
.header("Accept", "application/json")
.header("X-Request-Id", "req-42")
.header("Content-Type", "application/json; charset=utf-8")
```

Tất cả đều là ví dụ giá trị ASCII rõ ràng. Nhưng `Content-Type` phải **phù hợp với kiểu dữ liệu thực tế trong body**; gắn nhãn JSON không tự biến body thành JSON.

### 4.1. Không có CR, LF hoặc NUL trong giá trị

Những ký tự điều khiển như:

- `\r`: carriage return (CR),
- `\n`: line feed (LF),
- `\0`: NUL,

là **không hợp lệ và nguy hiểm trong nội dung header** vì có thể tạo cách hiểu sai ranh giới header, dẫn tới **HTTP header injection / response splitting** hoặc các vấn đề phân tích HTTP.

Ví dụ Java sẽ bị từ chối:

```java
// CỐ Ý SAI: chứa CRLF, có vẻ cố chèn thêm header.
HttpRequest.newBuilder(URI.create("https://example.com"))
        .header("X-Note", "ok\r\nInjected: yes");
```

Bộ kiểm thử Java ở mục 7 xác nhận lỗi `IllegalArgumentException` trong trường hợp này.

**Không xử lý bằng cách tự nối header thành chuỗi raw như `"X-Note: " + userInput + "\r\n"` rồi gửi qua socket**. Hãy dùng API builder, kiểm tra dữ liệu đầu vào theo chính sách ứng dụng và **từ chối** giá trị không hợp lệ thay vì âm thầm loại ký tự nguy hiểm khiến ý nghĩa dữ liệu bị thay đổi.

### 4.2. Unicode và encoding trong header

HTTP header **không phải nơi mặc định có thể ghi bất cứ chuỗi Unicode nào** như body UTF-8. Những trường cần biểu diễn chữ ngoài ASCII phải theo **quy tắc mã hóa của chính trường đó** (ví dụ cơ chế mở rộng cho một số tham số trường). Không mặc định rằng truyền trực tiếp emoji hoặc tiếng Việt có dấu vào `header(name, value)` sẽ truyền/đọc được đồng nhất trên HTTP/1.1, HTTP/2 và mọi server.

Nếu cần gửi văn bản UTF-8 có dấu, thông thường hãy đặt trong **request body**, chọn `BodyPublisher` phù hợp và khai báo `Content-Type` tương ứng. Nếu cần đặt nội dung phức tạp trong **custom header**, phải quy định một encoding an toàn, không nhập nhằng cho phía nhận và giới hạn độ dài hợp lý.

### 4.3. Không hiểu sai khoảng trắng và dấu phẩy

Theo ngữ pháp HTTP, phần whitespace bao quanh nội dung có quy tắc xử lý riêng. **Không dựa vào khoảng trắng đầu/cuối như dữ liệu nghiệp vụ** của một header. Đối với dữ liệu ứng dụng cần giữ nguyên whitespace, body thường là nơi phù hợp hơn.

Quan trọng hơn, `HttpHeaders` **không tự tách** chuỗi giá trị theo dấu phẩy:

```java
HttpRequest oneEntry = HttpRequest.newBuilder(
        URI.create("https://example.com"))
        .header("Accept", "application/json, text/plain")
        .build();

System.out.println(oneEntry.headers().allValues("Accept").size()); // 1
```

Một giá trị chứa dấu phẩy vẫn là **một `String` trong `List<String>` của Java**. Nếu thêm hai lần `header("Accept", ...)`, kết quả `allValues` có **hai phần tử**. Hai cách biểu diễn có thể tương đương về ngữ nghĩa HTTP với một header dạng danh sách như `Accept`, nhưng **không giống cấu trúc lưu trong `HttpHeaders`**. Việc chia/tách giá trị cần dựa vào cú pháp riêng của header, không tùy tiện `split(",")`.

## 5. Header nhiều giá trị không có nghĩa header nào cũng được lặp

**RFC 9110 `5.3** chỉ cho phép gửi nhiều field line cùng tên theo cách có thể kết hợp thành danh sách phân tách bằng dấu phẩy **khi định nghĩa của trường cho phép**. Do đó cần phân biệt:

- **Header dạng danh sách:** `Accept` cho phép nhiều media range; có thể khai báo nhiều giá trị theo đúng ngữ nghĩa.
- **Header mang giá trị đơn:** các trường như `Content-Type` biểu diễn một media type; không nên gửi nhiều giá trị xung đột.
- **Trường có ngữ nghĩa đặc biệt:** `Set-Cookie` thường xuất hiện **trong HTTP response**, mỗi cookie một field line và **không được gộp bừa bằng dấu phẩy**. Đây là ví dụ ngoại lệ phía **response**, không phải chỉ dẫn thêm `Set-Cookie` vào request.

Ví dụ danh sách `Accept`:

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/api"))
        .headers("Accept", "application/json",
                 "Accept", "text/plain")
        .build();
```

`req.headers().allValues("Accept")` là hai phần tử. Tuy nhiên khi thật sự gửi, HTTP client hoặc phiên bản HTTP có thể biểu diễn field line theo cách tương đương quy định bởi giao thức. **Đừng viết test khẳng định có đúng hai dòng văn bản trên wire chỉ vì `allValues` có hai phần tử.**

### Bảo toàn thứ tự trong nhóm giá trị cùng tên

`HttpHeaders` bảo toàn **thứ tự các giá trị cùng tên khi xây dựng request**. Thứ tự đó có thể quan trọng với header dạng danh sách. Ngược lại, `HttpHeaders.map()` **không cam kết thứ tự duyệt các tên header khác nhau**.

Ví dụ: nếu gọi `header("Accept", "application/json")` rồi `header("Accept", "text/plain")`, `allValues("Accept")` trả lần lượt theo thứ tự đã thêm. Không suy ra rằng khi in toàn bộ `map()`, tên `Accept` sẽ luôn xuất hiện trước tên `X-Mode`.

## 6. Header bị hạn chế và header do HTTP client quản lý

Không phải mọi tên header hợp lệ về cú pháp đều được phép đặt trực tiếp bằng `HttpRequest.Builder`. Java HTTP Client có thể tự xác định hoặc quản lý một số trường.

Với triển khai JDK HTTP Client tiêu chuẩn, các tên thường **bị hạn chế mặc định** gồm:

- `Connection`
- `Content-Length`
- `Expect`
- `Host`
- `Upgrade`

Ví dụ `Content-Length` phụ thuộc vào cách `BodyPublisher` gửi request body; tự ép sai độ dài có thể phá cấu trúc thông điệp. Trong cấu hình mặc định, câu lệnh sau thường ném `IllegalArgumentException`:

```java
// CỐ Ý SAI trong cấu hình JDK mặc định:
HttpRequest.newBuilder(URI.create("https://example.com"))
        .header("Content-Length", "5");
```

Một số header khác như `Authorization`, chuyển hướng và cookie có thể được quản lý bởi API chuyên biệt hoặc bị hạn chế **tùy cấu hình `HttpClient`** (chẳng hạn khi có `Authenticator`). Không kết luận mọi JDK và mọi request đều chấp nhận chỉnh những trường này chỉ vì tên hợp lệ.

Cấu hình triển khai `jdk.httpclient.allowRestrictedHeaders` có thể cho phép **một số** header vốn bị giới hạn, nhưng tài liệu JDK nói rõ thuộc tính này phục vụ **kiểm thử**, **không khuyến nghị dùng trong triển khai sản xuất** vì có thể dẫn tới lỗi giao thức/hành vi không xác định. Bài học không sử dụng nó để lách hạn chế.

Đối với header truyền thông số xác thực (`Authorization`, cookie, token), phải tránh log nguyên giá trị và tránh đưa dữ liệu nhạy cảm vào thông báo lỗi. Cấu hình xác thực đúng tầng thường phù hợp hơn việc chèn thủ công tất cả trường liên quan.

## 7. Chương trình Java 11 hoàn chỉnh, kiểm chứng tất cả cơ chế

Tạo tệp **`HttpRequestHeadersDemo.java`**. Mã chỉ **xây dựng request và kiểm tra headers**, **không gửi request tới `example.com`**, vì vậy không cần mạng hoặc thư viện ngoài JDK.

```java
import java.net.URI;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.util.List;

public class HttpRequestHeadersDemo {
    private static void expectInvalid(String name, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(name + " unexpectedly accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println(name + " = rejected");
        }
    }

    public static void main(String[] args) {
        URI uri = URI.create("https://example.com/api/items");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Trace", "first")
                .header("x-trace", "second")
                .headers("Accept", "application/json",
                         "Accept", "text/plain",
                         "X-Mode", "demo")
                .setHeader("X-TRACE", "replaced")
                .header("X-Trace", "last")
                .GET()
                .build();

        HttpHeaders h = request.headers();
        System.out.println("trace = " + h.allValues("x-TrAcE"));
        System.out.println("accept = " + h.allValues("ACCEPT"));
        System.out.println("first accept = " + h.firstValue("accept").orElse("<none>"));
        System.out.println("x-mode = " + h.firstValue("X-MODE").orElse("<none>"));
        System.out.println("missing = " + h.allValues("X-Missing"));
        System.out.println("case insensitive map = "
                + h.map().get("X-trace").equals(List.of("replaced", "last")));

        try {
            h.allValues("Accept").add("application/xml");
            throw new AssertionError("header list mutated");
        } catch (UnsupportedOperationException expected) {
            System.out.println("values immutable = true");
        }

        expectInvalid("space in name",
                () -> HttpRequest.newBuilder(uri).header("Bad Name", "ok"));
        expectInvalid("colon in name",
                () -> HttpRequest.newBuilder(uri).header("Bad:Name", "ok"));
        expectInvalid("newline in value",
                () -> HttpRequest.newBuilder(uri).header("X-Note", "a\r\nInjected: yes"));
        expectInvalid("odd header arguments",
                () -> HttpRequest.newBuilder(uri).headers("X-A", "1", "X-B"));
        expectInvalid("restricted Content-Length",
                () -> HttpRequest.newBuilder(uri).header("Content-Length", "5"));
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy trên JDK 11 trở lên. `--release 11` bảo đảm mã được kiểm tra với API/mức ngôn ngữ Java 11, ngay cả khi máy đang cài JDK mới:

```bash
javac --release 11 HttpRequestHeadersDemo.java
java HttpRequestHeadersDemo
```

**Đầu ra đã kiểm chứng trên JDK tiêu chuẩn với cấu hình mặc định:**

```text
trace = [replaced, last]
accept = [application/json, text/plain]
first accept = application/json
x-mode = demo
missing = []
case insensitive map = true
values immutable = true
space in name = rejected
colon in name = rejected
newline in value = rejected
odd header arguments = rejected
restricted Content-Length = rejected
ALL CHECKS PASSED
```

**Phân tích từng nhóm kiểm thử:**

1. `X-Trace` được thêm bằng `header` hai lần, không phân biệt hoa–thường; `setHeader("X-TRACE", "replaced")` thay cả hai. Sau cùng `header("X-Trace", "last")` nối thêm nên danh sách là `[replaced, last]`.
2. `headers(...)` thêm hai giá trị `Accept` theo thứ tự `application/json` rồi `text/plain`; `firstValue` lấy giá trị đầu.
3. Truy xuất với `ACCEPT`, `accept`, `X-MODE` và `x-TrAcE` đều hoạt động **không phân biệt hoa–thường**.
4. Header không có tên `X-Missing` cho danh sách rỗng `[]`, không trả `null`.
5. `HttpHeaders.map()` cho tra cứu tên không phân biệt hoa–thường, nhưng chỉ là **view bất biến**. Cố thêm vào danh sách trả về gây `UnsupportedOperationException`.
6. Tên chứa khoảng trắng, dấu hai chấm, giá trị có CRLF, và danh sách cặp bị lẻ bị từ chối bằng `IllegalArgumentException`.
7. Trong cấu hình JDK HTTP Client mặc định, `Content-Length` bị hạn chế nên cũng bị từ chối. Nếu môi trường chủ động bật thuộc tính kiểm thử cho restricted header, ca này có thể khác; **không dùng cấu hình đó** khi học cách viết request sản xuất.

**Lưu ý:** `expectInvalid` được viết để ném `AssertionError` nếu một trường hợp đáng lẽ bị từ chối lại được chấp nhận. Lỗi test khi thiết lập restricted headers khác mặc định phản ánh môi trường chạy; bốn test cú pháp còn lại dựa trên quy tắc tên/giá trị/đối số của API.

## 8. Đọc nhiều giá trị qua HttpHeaders

Sau khi `build`, truy xuất:

```java
HttpHeaders h = request.headers();
```

`HttpHeaders` là **đối tượng bất biến** cung cấp view chỉ đọc. Nó cũng được dùng cho header của `HttpResponse`. Những phương thức cần nhớ:

| Phương thức | Trả về | Khi nào dùng |
| --- | --- | --- |
| `allValues(String name)` | `List<String>` bất biến; có thể rỗng | Cần toàn bộ giá trị cùng tên |
| `firstValue(String name)` | `Optional<String>` | Chỉ cần giá trị đầu (nếu có) |
| `firstValueAsLong(String name)` | `OptionalLong` | Muốn đọc giá trị đầu thành số nguyên dài nếu trường có ngữ nghĩa số |
| `map()` | `Map<String, List<String>>` bất biến | Xem toàn bộ nhóm tên–danh sách giá trị |

Ví dụ:

```java
List<String> accept = h.allValues("accept");
String first = h.firstValue("ACCEPT").orElse("not-specified");

System.out.println(accept); // [application/json, text/plain]
System.out.println(first);  // application/json
```

Mảnh mã này thuộc phạm vi chương trình có biến `h` từ mục 7 và import `java.util.List`. Với `firstValueAsLong(...)`, một giá trị có mặt nhưng không phải số nguyên dài hợp lệ có thể gây `NumberFormatException`; không nên áp dụng cho mọi loại header.

**Không tự sửa kết quả `allValues` hoặc `map`.** Đây là các view bất biến. Muốn đổi header, thực hiện trên Builder trước khi xây dựng request mới.

### Dấu phẩy vẫn là một phần của một giá trị String

Ví dụ:

```java
HttpRequest onlyOne = HttpRequest.newBuilder(
        URI.create("https://example.com"))
        .header("Accept", "application/json, text/plain")
        .build();

System.out.println(onlyOne.headers().allValues("Accept"));
// [application/json, text/plain] nhưng List chỉ có MỘT phần tử
System.out.println(onlyOne.headers().allValues("Accept").size()); // 1
```

**Đừng dựa vào `List.toString()` để phân biệt số phần tử** vì hình thức hiển thị có thể gây nhầm. Khi cần biết có bao nhiêu giá trị builder lưu, dùng `size()`. `HttpHeaders` không tự parse giá trị ngăn bằng dấu phẩy.

### Request headers không nhất thiết là mọi byte trên wire

`HttpRequest.headers()` cho thấy các header mà request biểu diễn và ứng dụng có thể truy cập. Khi **gửi**, HTTP Client có thể quản lý hoặc thêm các trường thuộc giao thức như độ dài body hoặc kết nối. Đừng khẳng định rằng danh sách `request.headers().map()` là **bản chụp chính xác tất cả header truyền trên mạng**, hoặc dựa vào nó để kiểm thử casing/định dạng HTTP/2.

## 9. Kỹ thuật dùng header đúng trong ứng dụng

### 9.1. Một giá trị cuối cùng cho header đơn

Khi ứng dụng biết header chỉ nên có một giá trị, `setHeader` thể hiện rõ ý định:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com"))
        .setHeader("Content-Type", "application/json; charset=utf-8")
        .build();
```

Việc đặt `Content-Type` như trên chỉ có ý nghĩa khi body thật sự là JSON UTF-8. Nếu dùng `GET` không có body thì header Content-Type thường không cần thiết; đoạn mã chỉ minh họa thao tác Builder.

### 9.2. Một danh sách ưu tiên cho header dạng list

`Accept` có cú pháp nhiều media range. Có thể dùng:

```java
.header("Accept", "application/json")
.header("Accept", "text/plain")
```

Hoặc, khi muốn chủ động biểu diễn thành **một giá trị**, dùng:

```java
.setHeader("Accept", "application/json, text/plain")
```

Cả hai có thể diễn đạt danh sách media range, nhưng cấu trúc `HttpHeaders.allValues` tương ứng khác nhau. Nên chọn một quy ước nhất quán để dễ kiểm thử và bảo trì.

### 9.3. Dynamic headers: whitelist tên, kiểm tra giá trị

Nếu ứng dụng nhận tên hoặc giá trị header từ cấu hình/đầu vào bên ngoài, hãy:

1. Chỉ cho phép **những tên đã biết** hoặc thỏa điều kiện ứng dụng (thường đơn giản hơn ngữ pháp token đầy đủ).
2. Từ chối ký tự điều khiển, đặc biệt `CR`, `LF` và `NUL`; không tạo header raw bằng phép nối chuỗi.
3. Giới hạn kích thước, số lượng header; server/proxy thường có **giới hạn thực tế** dù HTTP không đặt một mức chung cho tất cả.
4. Dựa vào đặc tả của từng header để quyết định có được thêm nhiều giá trị hay không.
5. Không đưa mật khẩu, token, cookie, thông tin bí mật vào log hoặc exception message.

Ngay cả khi `Builder` kiểm tra cú pháp, vẫn phải kiểm tra **ngữ nghĩa nghiệp vụ**: ví dụ giá trị số phải hợp lệ, media type phải đúng, token phải có định dạng ứng dụng cho phép. API xây dựng request **không thay thế bước validate dữ liệu người dùng**.

## 10. Lỗi thường gặp và cách sửa

| Triệu chứng/sai lầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Header xuất hiện nhiều giá trị ngoài ý muốn | Gọi `header` nhiều lần cho cùng tên | Dùng `setHeader` khi chỉ cần một giá trị cuối |
| Các giá trị cũ biến mất | Dùng `setHeader` thay vì `header` | Chọn `header` nếu trường cho phép nhiều giá trị |
| `IllegalArgumentException` với `headers(...)` | Truyền số lượng `String` lẻ | Truyền từng cặp tên, giá trị |
| `IllegalArgumentException` với tên | Có khoảng trắng, dấu `:`, ký tự không hợp lệ hoặc tên bị restricted | Dùng tên token hợp lệ và xem danh sách restricted |
| `IllegalArgumentException` với giá trị | Có CR/LF, ký tự điều khiển hoặc nội dung bị hạn chế | Validate và từ chối input sai; không ghép header raw |
| `allValues("accept")` trả danh sách có một phần tử chứa dấu phẩy | Java không tự split danh sách theo dấu phẩy | Parse theo cú pháp riêng của header nếu cần |
| Tra cứu với case khác rồi tưởng không tìm được | Dùng một Map riêng có so sánh phân biệt hoa–thường | Dùng `HttpHeaders` / map view của nó; tra cứu tên không phân biệt hoa–thường |
| Không thể `add`/`put` vào header map | `HttpHeaders` là bất biến | Chỉnh Builder trước khi `build` |
| `Content-Length` bị từ chối | HTTP client tự xác định độ dài body | Để `BodyPublisher` và HTTP client quản lý; không bật override trong production |
| Trùng `Content-Type` hoặc header đơn | Thêm nhiều giá trị khi trường chỉ chấp nhận một cấu trúc | Dùng `setHeader` và bảo đảm body/ý nghĩa thống nhất |
| Kỳ vọng y hệt số dòng header trên HTTP/2 | Nhầm `HttpHeaders` với wire encoding | Kiểm thử ngữ nghĩa thay vì casing/dòng wire |
| Gộp `Set-Cookie` bằng dấu phẩy | Không hiểu ngoại lệ của trường response này | Giữ mỗi giá trị response `Set-Cookie` riêng, không gộp tùy tiện |

## 11. Tự kiểm tra

**Bài 1.** Đoạn dưới cho kết quả `allValues("X-Id")` là gì?

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com"))
        .header("X-Id", "1")
        .header("x-id", "2")
        .setHeader("X-ID", "3")
        .header("X-Id", "4")
        .build();
```

**Đáp án:** `[3, 4]`. `setHeader` đã thay `1` và `2`, còn `header` cuối thêm `4`.

**Bài 2.** `headers("Accept", "application/json", "X-Mode")` có hợp lệ không?

**Đáp án:** Không. Có **ba** `String`, không đủ cặp; ném `IllegalArgumentException`.

**Bài 3.** Tên `Bad Name` có hợp lệ không? `X-Correlation-Id` có hợp lệ không?

**Đáp án:** `Bad Name` không, vì có khoảng trắng. `X-Correlation-Id` là tên token hợp lệ về cú pháp; vẫn cần kiểm tra quy ước nghiệp vụ.

**Bài 4.** Tại sao `.header("X-Note", "ok\r\nOther: 1")` bị từ chối?

**Đáp án:** Giá trị có CRLF có thể phá ranh giới field và tạo header injection. Không được đưa CR/LF/NUL vào giá trị.

**Bài 5.** `.header("Accept", "application/json, text/plain")` tạo bao nhiêu phần tử trong `allValues("Accept")`?

**Đáp án:** **Một** phần tử `String` chứa dấu phẩy. `HttpHeaders` không tự tách chuỗi.

**Bài 6.** Có nên thêm `Content-Length` bằng `header(...)` để điều khiển độ dài request body?

**Đáp án:** Thông thường không. JDK HTTP Client hạn chế mặc định vì độ dài được xác định theo `BodyPublisher` và giao thức; không dùng cấu hình kiểm thử để lách giới hạn trong môi trường thật.

## 12. Ghi nhớ

Với HTTP Request trên Java 11+:

- `header(name, value)` **thêm** một giá trị.
- `headers(name1, value1, ...)` **thêm nhiều cặp** tên–giá trị; số đối số phải **chẵn**.
- `setHeader(name, value)` **thay mọi giá trị cũ** của tên tương ứng.
- **Tên** header không phân biệt hoa–thường và phải là token hợp lệ; tránh tên có khoảng trắng hoặc dấu `:`.
- **Giá trị** phải hợp lệ về ký tự lẫn **ngữ nghĩa từng header**; không chứa CR/LF/NUL.
- `HttpHeaders.allValues` trả danh sách **bất biến**, giữ thứ tự giá trị cùng tên và **không tự tách chuỗi dấu phẩy**.
- Không gửi trùng bừa các trường chỉ có một giá trị; đặc biệt không gộp `Set-Cookie` response như danh sách CSV.
- Để HTTP client quản lý những header hạn chế, điển hình `Content-Length`; không phụ thuộc dạng biểu diễn trên wire.

### Tài liệu tham khảo chính thức

- [Java 11 — HttpRequest.Builder: header, headers, setHeader](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java 11 — HttpHeaders: allValues, firstValue, map](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html)
- [Java 11 — HttpRequest.headers()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java 25 — HttpRequest.Builder (API tiếp tục được hỗ trợ)](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java 25 — HttpHeaders (API hiện hành)](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpHeaders.html)
- [RFC 9110 — HTTP Semantics, ``5.1–5.5: tên, nhiều giá trị và cú pháp trường](https://www.rfc-editor.org/rfc/rfc9110.html#section-5)
- [Java 11 Networking — jdk.httpclient.allowRestrictedHeaders và các hạn chế](https://docs.oracle.com/en/java/javase/11/core/java-networking.html)
