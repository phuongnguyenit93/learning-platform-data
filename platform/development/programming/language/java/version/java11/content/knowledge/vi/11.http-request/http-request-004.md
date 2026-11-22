# `header()`, `headers()` và `setHeader()` trong `HttpRequest.Builder` (Java 11+)

## 1. Mục tiêu bài học

Trong module `java.net.http` được chuẩn hóa từ **Java 11**, đối tượng `HttpRequest.Builder` giúp chuẩn bị URI, HTTP method, request body và các **request header** trước khi tạo ra một `HttpRequest`. Ba phương thức rất dễ nhầm là:

- **`header(String name, String value)`:** **thêm** một cặp tên–giá trị; nếu tên đã có thì **thêm một giá trị** vào danh sách.
- **`headers(String... headers)`:** **thêm nhiều cặp** tên–giá trị trong cùng một lời gọi, theo thứ tự `name, value, name, value, ...`. Với tên lặp lại, phương thức cũng **thêm nhiều giá trị**, chứ không thay thế.
- **`setHeader(String name, String value)`:** **thay thế** tất cả giá trị đã cấu hình trước đó của **cùng tên header** bằng đúng giá trị mới.

Cả ba là API hiện hành trên JDK mới, không phải phương thức đã bị thay thế hay legacy. Chúng **cấu hình builder**; chưa có yêu cầu mạng nào được gửi cho tới khi `HttpRequest` đã `build()` được truyền cho `HttpClient.send(...)` hoặc `sendAsync(...)`.

Điểm then chốt: lựa chọn **thêm** hay **ghi đè** phải căn cứ vào hợp đồng HTTP của từng header. Không phải mọi header đều phù hợp chứa nhiều giá trị.

## 2. Vì sao một header có thể có nhiều giá trị?

HTTP header gồm tên và giá trị, ví dụ:

```http
Accept: application/json
X-Trace: first
X-Trace: second
```

Tên header **không phân biệt chữ hoa/thường** (`X-Trace` và `x-trace` là cùng một tên). Một số tên có thể xuất hiện nhiều lần hoặc có danh sách giá trị theo quy tắc cú pháp riêng của HTTP. Việc Java cho phép nhiều giá trị **không bảo đảm** server coi mọi trường trùng tên như nhau; hãy dựa vào đặc tả của header và API đích.

Ví dụ:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("X-Trace", "first")
        .header("X-Trace", "second")
        .build();
```

Khi xem `request.headers().allValues("X-Trace")`, ta nhận được hai giá trị `[first, second]` theo trình tự đã thêm.

**Lưu ý mã minh họa:** đoạn trên cần import `java.net.URI` và `java.net.http.HttpRequest`, nằm trong class/phương thức hợp lệ. Chương trình hoàn chỉnh ở mục 5 bao gồm đủ import, lệnh biên dịch và đầu ra chính xác.

## 3. So sánh trực tiếp ba phương thức

| Phương thức | Kiểu tham số | Hành vi khi tên đã có | Mục đích |
| --- | --- | --- | --- |
| `header("X-Trace", "first")` | Một `name` và một `value` | **Thêm** giá trị mới | Đưa một cặp header vào builder |
| `headers("Accept", "application/json", "X-Trace", "first")` | Một dãy cặp `name, value` | **Thêm** từng cặp; có thể lặp tên | Cấu hình nhiều header gọn trong một lệnh |
| `setHeader("X-Trace", "final")` | Một `name` và một `value` | **Xóa các giá trị cũ trên builder, thay bằng một giá trị mới** | Cập nhật hoặc bảo đảm chỉ còn một giá trị |

Các phương thức đều trả về **chính builder đang được sửa**, do đó có thể nối lệnh:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Accept", "application/json")
        .headers("X-Trace", "first", "X-Mode", "demo")
        .setHeader("X-Trace", "final")
        .GET()
        .build();
```

Kết quả trong request cuối:

- `Accept`: `[application/json]`.
- `X-Mode`: `[demo]`.
- `X-Trace`: `[final]`, vì `setHeader` thay giá trị trước đó.
- Method: `GET`.

### 3.1. `header(name, value)` thêm, không ghi đè

```java
HttpRequest.Builder builder = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"));

builder.header("X-Trace", "first");
builder.header("X-Trace", "second");
HttpRequest request = builder.build();

// request.headers().allValues("X-Trace") = ["first", "second"]
```

Nếu cần **nối thêm** giá trị sau khi đã gọi `setHeader`, bạn vẫn có thể gọi `header` tiếp. `header` không có hành vi “chỉ đặt nếu chưa tồn tại”; nó luôn là thao tác thêm một giá trị vào cấu hình header của builder.

### 3.2. `headers(String... headers)` nhận các cặp xen kẽ

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .headers("Accept", "application/json",
                 "X-Trace", "first",
                 "X-Trace", "second")
        .build();
```

Ở đây `headers` nhận **6 chuỗi = 3 cặp**. Hai cặp cùng tên `X-Trace` sẽ cho **hai giá trị**, giống như hai lần gọi `header`.

**Sai về số lượng tham số:**

```java
// Sai khi chạy: 3 chuỗi không ghép thành đủ cặp name/value.
// HttpRequest.newBuilder(uri).headers("Accept", "application/json", "X-Trace");
```

`headers(...)` yêu cầu **số lượng chuỗi chẵn**, nếu lẻ thì ném `IllegalArgumentException`. Đừng hiểu đây là cách truyền một danh sách tên mà không có giá trị.

### 3.3. `setHeader(name, value)` thay thế cả danh sách cũ

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("X-Trace", "first")
        .header("x-trace", "second")
        .setHeader("X-TRACE", "final")
        .build();

// request.headers().allValues("x-trace") = ["final"]
```

Dù dùng ba kiểu viết hoa/thường khác nhau, tên header vẫn được nhận diện là **cùng một trường**. `setHeader` thay **toàn bộ các giá trị trước đó** của tên tương ứng, không chỉ sửa giá trị đầu tiên.

**Thứ tự tác động có ý nghĩa:**

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .setHeader("X-Trace", "final")
        .header("X-Trace", "extra")
        .build();

// req.headers().allValues("X-Trace") = ["final", "extra"]
```

Nếu đảo hai lời gọi thành `header(...).setHeader(...)`, kết quả cuối sẽ chỉ còn `["final"]`.

## 4. Xem lại headers trên `HttpRequest` đã tạo

Khi `builder.build()` được gọi, một `HttpRequest` mới được tạo. Để xem thông tin đã cấu hình, dùng `request.headers()` — kết quả là đối tượng **`HttpHeaders`**:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Accept", "application/json")
        .headers("X-Trace", "first", "X-Trace", "second")
        .build();

java.util.List<String> traces =
        request.headers().allValues("x-TRACE");

java.util.Optional<String> accept =
        request.headers().firstValue("ACCEPT");

java.util.Map<String, java.util.List<String>> all =
        request.headers().map();
```

Ý nghĩa:

- **`allValues(name)`:** trả danh sách các giá trị của header, tìm tên **không phân biệt hoa/thường**; nếu không có header thì danh sách rỗng.
- **`firstValue(name)`:** trả `Optional<String>` của giá trị đầu tiên (nếu có). Đừng lấy giá trị đầu tiên khi contract yêu cầu xử lý **tất cả** giá trị.
- **`map()`:** đọc toàn bộ header dưới dạng map tên → danh sách giá trị. Đối tượng `HttpHeaders` là bất biến; không sửa danh sách/map để kỳ vọng thay request.

Cần phân biệt tên phương thức: **`builder.headers("K","V")`** là *phương thức ghi nhiều cặp* trên builder, trong khi **`request.headers()`** là *phương thức đọc* của request đã build. Hai phương thức có tên gần giống nhưng nằm trên hai kiểu đối tượng khác nhau và có chức năng khác nhau.

Một builder không cung cấp `headers()` không đối số để lấy snapshot trực tiếp. Nếu muốn kiểm tra cấu hình đã đặt, tạo `HttpRequest` bằng `build()` rồi đọc `HttpHeaders`.

## 5. Ví dụ Java 11 hoàn chỉnh: thêm, thay thế và kiểm tra lỗi

Ví dụ chạy **hoàn toàn trong bộ nhớ**, không gửi yêu cầu Internet. Nó giúp so sánh kết quả `header`, `headers`, `setHeader`, kiểm tra tên header không phân biệt hoa/thường và các đầu vào không hợp lệ.

Tạo tệp **`HeaderBuilderDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpRequest;

public class HeaderBuilderDemo {
    public static void main(String[] args) {
        URI uri = URI.create("https://example.com/api/items");

        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .header("Accept", "application/json")
                .header("X-Trace", "first")
                .headers("X-Trace", "second", "X-Mode", "demo");

        HttpRequest before = builder.GET().build();
        System.out.println("method: " + before.method());
        System.out.println("before traces: " +
                before.headers().allValues("x-trace"));
        System.out.println("before mode: " +
                before.headers().firstValue("X-MODE").orElse("missing"));
        System.out.println("before accept: " +
                before.headers().firstValue("accept").orElse("missing"));
        System.out.println("missing header: " +
                before.headers().allValues("X-Missing").size());

        builder.setHeader("x-TRACE", "final");
        builder.setHeader("Accept", "text/plain");
        HttpRequest after = builder.build();
        System.out.println("after traces: " +
                after.headers().allValues("X-TRACE"));
        System.out.println("after accept: " +
                after.headers().firstValue("ACCEPT").orElse("missing"));
        System.out.println("before unchanged: " +
                before.headers().allValues("X-Trace"));

        HttpRequest appended = builder.header("X-Trace", "extra").build();
        System.out.println("appended traces: " +
                appended.headers().allValues("x-trace"));

        try {
            HttpRequest.newBuilder(uri).headers("X-One", "ok", "X-Odd");
            System.out.println("odd count: unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("odd count: IllegalArgumentException");
        }

        try {
            HttpRequest.newBuilder(uri).header("Bad Name", "ok");
            System.out.println("bad name: unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad name: IllegalArgumentException");
        }

        try {
            HttpRequest.newBuilder(uri).header("X-Test", "ok\r\nInjected: yes");
            System.out.println("CRLF value: unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("CRLF value: IllegalArgumentException");
        }
    }
}
```

Dùng JDK 11 trở lên. Nếu biên dịch bằng JDK mới, `--release 11` giúp kiểm tra rằng mã chỉ dùng ngôn ngữ và API có ở Java 11:

```bash
javac --release 11 -encoding UTF-8 HeaderBuilderDemo.java
java HeaderBuilderDemo
```

**Đầu ra chính xác đã chạy thử:**

```text
method: GET
before traces: [first, second]
before mode: demo
before accept: application/json
missing header: 0
after traces: [final]
after accept: text/plain
before unchanged: [first, second]
appended traces: [final, extra]
odd count: IllegalArgumentException
bad name: IllegalArgumentException
CRLF value: IllegalArgumentException
```

### Phân tích đầu ra

1. Lúc đầu `header("X-Trace","first")` thêm một giá trị; `headers("X-Trace","second",...)` thêm giá trị thứ hai. Khi gọi `allValues("x-trace")`, kết quả là `[first, second]`.
2. `firstValue("X-MODE")` đọc giá trị `demo`, bất kể chữ hoa/thường. `firstValue("accept")` nhận `application/json`. Header không tồn tại có `allValues(...).size() == 0`.
3. `setHeader("x-TRACE","final")` xóa hai giá trị trace trước đó **trên builder**, và `setHeader("Accept","text/plain")` thay header Accept. Request `after` chứa giá trị mới.
4. `before` **vẫn** có `[first, second]` vì `HttpRequest` sau `build()` là bất biến. Sửa builder không sửa request đã tạo.
5. Sau khi đã `setHeader`, gọi `header("X-Trace","extra")` sẽ **thêm** vào danh sách; request mới có `[final, extra]`.
6. `headers(...)` với ba chuỗi là số lẻ; tên có dấu cách `"Bad Name"` không hợp lệ; giá trị chứa `CRLF` (`\r\n`) có nguy cơ chia tách dòng header. Trong cả ba trường hợp, builder ném `IllegalArgumentException`.

Đây là kiểm chứng hành vi của **builder**, không phải kiểm thử phản hồi mạng. Khi request thật sự được gửi, client/server/proxy còn chịu các quy tắc HTTP riêng và có thể quản lý hoặc biểu diễn một số header theo cách khác.

## 6. `build()` chốt request, nhưng không khóa builder

Builder **có thể thay đổi** và các phương thức cấu hình trả lại chính nó:

```java
HttpRequest.Builder builder = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"));
builder.header("Accept", "application/json");

HttpRequest first = builder.build();

builder.setHeader("Accept", "text/plain");
HttpRequest second = builder.build();
```

Kết quả:

- `first.headers().firstValue("Accept")` chứa `application/json`.
- `second.headers().firstValue("Accept")` chứa `text/plain`.
- Cả hai là hai `HttpRequest` riêng và không bị thay đổi ngược khi builder được sửa tiếp.

Theo tài liệu API, `build()` trả **một request mới mỗi lần gọi**. Không được giả định `build()` xóa header cũ, reset builder, gửi dữ liệu hoặc làm builder trở thành bất biến.

Nếu cần tạo các biến thể mà không làm biến đổi builder gốc, sử dụng `copy()`:

```java
HttpRequest.Builder base = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .header("Accept", "application/json");

HttpRequest requestA = base.copy()
        .setHeader("X-Mode", "A")
        .build();

HttpRequest requestB = base.copy()
        .setHeader("X-Mode", "B")
        .build();
```

Đây là mẫu dùng hiện hành để xây các request tương tự nhau. `copy()` sao chép trạng thái tại thời điểm gọi; sửa bản sao không sửa builder nguồn.

**Lưu ý đa luồng:** `HttpRequest.Builder` **không thread-safe** (các setter không đồng bộ). Không cho nhiều thread cùng ghi một builder mà không đồng bộ hóa; cách đơn giản hơn là tạo builder riêng cho mỗi request hoặc tạo bản sao trước khi sửa.

## 7. Dùng thực tế với JSON, Accept và Content-Type

HTTP header có vai trò khác nhau; lựa chọn `header` hay `setHeader` theo **số giá trị mong muốn**, không chỉ theo độ dài cú pháp.

### 7.1. GET yêu cầu phản hồi JSON

```java
HttpRequest get = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .setHeader("Accept", "application/json")
        .GET()
        .build();
```

`Accept` thể hiện kiểu phản hồi client muốn nhận. Nếu chỉ muốn **một giá trị xác định**, `setHeader` là cách thể hiện rõ ý định ngay cả khi builder được cấu hình từ nhiều nguồn.

### 7.2. POST gửi JSON bằng UTF-8

```java
String json = "{\"id\":7}";

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .setHeader("Accept", "application/json")
        .setHeader("Content-Type", "application/json; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, java.nio.charset.StandardCharsets.UTF_8))
        .build();
```

- `Content-Type` mô tả **body của request gửi đi**; `Accept` mô tả kiểu phản hồi mong muốn.
- `BodyPublishers.ofString(..., UTF_8)` tạo publisher phát byte UTF-8. **Không tự suy** rằng publisher sẽ đặt `Content-Type: application/json`; builder đặt header tường minh.
- `setHeader` giúp giảm nguy cơ còn sót hai giá trị mâu thuẫn cho cùng một header khi cấu hình được bổ sung nhiều bước.
- Trình tạo body và header phải khớp với hợp đồng thực tế: việc ghi `Content-Type: application/json` không tự biến một chuỗi bất kỳ thành JSON hợp lệ.

Nếu có header cần nhiều giá trị theo đặc tả của nó, có thể dùng `header` nhiều lần hoặc `headers`. Tuy nhiên **đừng tự ý chia một giá trị HTTP có cấu trúc thành nhiều header** nếu API server không mong đợi điều đó.

### 7.3. Khi nào nên dùng `headers(...)`?

Khi bạn đã có một nhóm **các cặp cố định** cần thêm cùng lúc:

```java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/api/items"))
        .headers("Accept", "application/json",
                 "X-Request-Id", "req-123",
                 "X-Mode", "demo")
        .GET()
        .build();
```

`headers` là tiện ích *thêm nhiều cặp*, không tự biến một chuỗi `"Accept: application/json"` thành hai thành phần. Mỗi tên và mỗi giá trị phải là tham số `String` riêng.

## 8. Kiểm tra tên/giá trị và header bị hạn chế

### 8.1. Tên và giá trị phải hợp lệ

HTTP header name dùng cú pháp token; không được chứa dấu cách, ký tự xuống dòng hoặc ký tự không hợp lệ trong tên. Header value phải tuân thủ quy tắc an toàn của HTTP client và HTTP specification.

```java
// Lỗi: tên không hợp lệ vì có dấu cách.
// builder.header("Bad Name", "ok");

// Lỗi: giá trị chứa CRLF, có nguy cơ header injection.
// builder.header("X-Test", "ok\r\nInjected: yes");
```

Theo Javadoc, `header`, `headers` và `setHeader` có thể ném **`IllegalArgumentException`** khi tên/giá trị không hợp lệ hoặc bị implementation hạn chế. Ví dụ mục 5 kiểm chứng trực tiếp hai trường hợp không hợp lệ.

**Không dùng việc builder từ chối CRLF thay cho việc kiểm soát đầu vào**: các giá trị nhận từ người dùng vẫn phải được xác thực theo yêu cầu nghiệp vụ; không ghi header chứa nội dung điều khiển, bí mật hoặc dữ liệu chưa được kiểm soát.

### 8.2. Header do HttpClient tự quản lý

**Không phải header nào cũng được ứng dụng tự đặt.** Một số tên/giá trị bị hạn chế theo triển khai vì client phải tự quyết định. Ví dụ, `Content-Length` thường do `BodyPublisher` và HTTP client xác định; cố đặt thủ công có thể bị ném `IllegalArgumentException`.

Một số hành vi liên quan authentication, cookies, redirects hoặc kết nối được xử lý bởi các API và cấu hình khác của `HttpClient`. Không nên hardcode những giá trị mà client quản lý hay khẳng định danh sách header bị cấm là giống nhau ở mọi phiên bản/triển khai JDK.

Phân biệt: các phương thức builder lưu **request headers người lập trình cấu hình**. Khi gửi thật, HTTP client còn có thể thêm hoặc điều chỉnh header protocol-level; vì vậy `request.headers()` không phải cam kết về từng byte header thực sự trên dây.

### 8.3. Giá trị `null` và số đối số

`headers(name1, value1, ...)` cần số chuỗi chẵn; `header` và `setHeader` luôn cần một tên cùng một giá trị. Tránh truyền tham chiếu `null`: giá trị null không biểu thị thao tác xóa header. Với Java 11, nếu cần loại bỏ một header đã thêm mà không có API xóa trên builder, cách rõ ràng là **tạo builder mới không thêm header đó**, hoặc thiết kế cấu hình trước khi gọi builder.

Không dùng `setHeader("Name", null)` như một cách xóa giá trị; nó không phải hợp đồng API.

## 9. Header không phân biệt chữ hoa/thường — nhưng giá trị thì sao?

Theo HTTP, **tên** header không phân biệt chữ hoa/thường:

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .header("X-Trace", "first")
        .setHeader("x-TRACE", "final")
        .build();

String val = req.headers().firstValue("X-TRACE").orElse("missing");
// val = "final"
```

Tuy nhiên, **giá trị** header không có một quy tắc chung rằng Java sẽ tự so sánh không phân biệt hoa/thường. Giá trị có thể là token, chuỗi có cấu trúc, URI, ngày giờ, hay dữ liệu đặc thù của giao thức; quy tắc so sánh phụ thuộc **từng header**.

Vì vậy, không được tự động lower-case toàn bộ header value hoặc assume `"Bearer TOKEN"` và `"bearer token"` là tương đương. Đặc biệt, dữ liệu xác thực có thể phân biệt chữ hoa/thường và phải được giữ chính xác theo contract.

### Những giá trị nhiều phần tử có đồng nghĩa nhiều dòng header?

Không nhất thiết. Mỗi header có quy tắc cấu trúc riêng, và phần mềm trung gian có thể xử lý một số trường trùng tên khác với một chuỗi chứa dấu phẩy. Chỉ lặp header khi đặc tả/contract cho phép. Với header yêu cầu **một giá trị**, sử dụng `setHeader` để thể hiện ý định cấu hình và tránh tích lũy giá trị cũ.

Tên minh họa `X-Trace` trong bài chỉ để tránh trùng các header đặc biệt do client quản lý, không phải khuyến nghị đặt tên mọi header tùy biến bằng tiền tố `X-`. Tên header thực tế cần tuân theo tiêu chuẩn và quy ước API của hệ thống.

## 10. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một header có nhiều giá trị ngoài ý muốn | Gọi `header`/`headers` nhiều lần cùng tên | Dùng `setHeader` cho giá trị đơn nhất |
| Chỉ còn một giá trị khi muốn có nhiều | Gọi `setHeader` sau các lệnh thêm | Dùng `header`/`headers` với nhiều cặp, theo contract |
| `headers(...)` ném `IllegalArgumentException` | Có số chuỗi lẻ | Ghép đúng cặp `name, value` |
| Builder từ chối header | Tên/giá trị sai cú pháp hoặc header bị hạn chế | Kiểm tra RFC, tên header và API client; không cố ghi `Content-Length` thủ công |
| Header có chữ thường không được tìm thấy vì so sánh bằng chuỗi literal | Code xử lý tên header chưa theo quy tắc HTTP | Dùng `HttpHeaders.firstValue`/`allValues` (tra cứu không phân biệt hoa/thường) |
| Đọc `firstValue` nhưng mất các giá trị khác | Chỉ đọc giá trị đầu | Dùng `allValues` nếu header cho phép và cần xử lý nhiều giá trị |
| Sửa builder mà request đã build không thay đổi | `HttpRequest` bất biến | Build request mới sau khi chỉnh builder |
| Builder có header cũ dù đã gọi `build()` | `build` không reset builder | Tạo builder mới hoặc `copy()` nếu cần cấu hình khác |
| Gọi `header` mà server chưa nhận gì | Builder không gửi network | Gọi `HttpClient.send/sendAsync` sau `build` |
| API nhận body sai định dạng | `Content-Type` không khớp hoặc body chưa serialize đúng | Xác định media type và charset; tạo body hợp lệ |
| Nhiều thread gặp giá trị header lẫn nhau | Dùng chung builder mutable không đồng bộ | Tạo builder riêng cho từng request hoặc đồng bộ |
| Log tiết lộ token, cookie, thông tin nhạy cảm | Ghi toàn bộ request headers | Ẩn/redact dữ liệu nhạy cảm, giới hạn logging |
| Giá trị chứa CRLF bị từ chối | Header injection không an toàn | Không ghép trực tiếp chuỗi chứa ký tự điều khiển vào header |

**Cảnh báo riêng về quyền truy cập:** Nếu phải đặt `Authorization` hoặc khóa API, lấy bí mật từ nguồn cấu hình an toàn, không hardcode vào mã minh họa, không in đầy đủ trong log và dùng HTTPS. Dù request chỉ được build trong bộ nhớ, dữ liệu nhạy cảm vẫn có thể lộ nếu ứng dụng ghi log đối tượng chứa headers.

## 11. Áp dụng vào thiết kế code

### 11.1. Cấu hình default và ghi đè theo request

Trong một helper tạo request, có thể có giá trị mặc định rồi ghi đè theo nhu cầu cụ thể:

```java
static HttpRequest makeRequest(URI uri, String accept) {
    return HttpRequest.newBuilder(uri)
            .setHeader("Accept", "application/json")
            .setHeader("Accept", accept)
            .GET()
            .build();
}
```

Đây là **phương thức minh họa** cần đặt trong class có import `java.net.URI` và `java.net.http.HttpRequest`. Sau cùng chỉ còn giá trị `accept`; nếu dùng `header("Accept", accept)` ở bước hai, builder sẽ có **hai giá trị** có thể mâu thuẫn.

Thực tế, nếu chỉ có một giá trị cuối cùng, có thể tính giá trị đó trước rồi gọi `setHeader` một lần. Tổ chức pipeline cấu hình như vậy giúp giảm thao tác dư thừa.

### 11.2. Tách cấu hình và bước gửi

Quy trình thông dụng:

```java
// Minh họa, không phải chương trình độc lập:
HttpRequest request = HttpRequest.newBuilder(uri)
        .setHeader("Accept", "application/json")
        .GET()
        .build();

HttpClient client = HttpClient.newHttpClient();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Mã trên cần import `java.net.http.HttpClient`, `HttpResponse` và xử lý `IOException`, `InterruptedException`; nó cũng cần endpoint mạng thực. Không suy đoán mã trạng thái hoặc nội dung `response.body()` khi chưa gửi request.

Ưu điểm của việc tách tạo request và gửi: có thể unit test cấu hình header bằng `request.headers().allValues(...)` mà **không gọi mạng**, như ví dụ hoàn chỉnh ở mục 5. Với ứng dụng có nhiều request, nên tái sử dụng `HttpClient` hợp lý, trong khi builder cấu hình nên độc lập theo từng request.

### 11.3. Gợi ý lựa chọn nhanh

- **Muốn thêm đúng một cặp**: `header(name, value)`.
- **Muốn thêm nhiều cặp trong một lệnh**: `headers(name1, value1, name2, value2, ...)`.
- **Muốn chỉ còn một giá trị cuối cùng cho cùng tên**: `setHeader(name, value)`.
- **Muốn đọc mọi giá trị**: `request.headers().allValues(name)`.
- **Muốn đọc một giá trị tùy chọn**: `request.headers().firstValue(name)`.
- **Muốn thay request đã build**: sửa builder và `build()` request mới; không thể chỉnh sửa request cũ.

## 12. Bài tập tự kiểm tra

**Câu 1.** Kết quả cuối của đoạn dưới là gì?

```java
builder.header("X-Mode", "A")
       .header("X-Mode", "B")
       .setHeader("X-Mode", "C");
```

**Đáp án:** `X-Mode` có duy nhất `["C"]`, vì `setHeader` thay toàn bộ giá trị cũ. `builder` là `HttpRequest.Builder` hợp lệ đã được khai báo trong ngữ cảnh.

**Câu 2.** Nếu sau đó thêm `builder.header("X-Mode","D")` thì sao?  
**Đáp án:** Request được build sau đó có `["C", "D"]`.

**Câu 3.** Lời gọi `headers("Accept","application/json","X-Mode")` có hợp lệ không?  
**Đáp án:** Không, số đối số lẻ; khi chạy ném `IllegalArgumentException`.

**Câu 4.** `request.headers().allValues("x-trace")` có tìm được header được thêm là `"X-Trace"` không?  
**Đáp án:** Có, tên header HTTP không phân biệt chữ hoa/thường.

**Câu 5.** Có thể làm một request đã build thay đổi giá trị header bằng cách gọi `setHeader` trên builder cũ không?  
**Đáp án:** Không; request cũ là bất biến. Chỉ những request build **sau** khi sửa builder nhận cấu hình mới.

**Câu 6.** Với POST JSON, nên đặt `Accept` hay `Content-Type`?  
**Đáp án:** Hai header phục vụ hai mục đích khác nhau: `Accept` mô tả response mong muốn, `Content-Type` mô tả body đang gửi. Có thể đặt cả hai nếu đúng contract API.

**Câu 7.** Vì sao không nên đặt `Content-Length` thủ công bằng `header`?  
**Đáp án:** Đây là thông tin thường được publisher/client quản lý và có thể bị implementation hạn chế; việc đặt thủ công có thể gây lỗi hoặc không đúng body.

## 13. Tổng kết

- **`header(name,value)`**: thêm **một** cặp; khi trùng tên sẽ tích lũy thêm giá trị.
- **`headers(name1,value1,...)`**: thêm **nhiều** cặp; yêu cầu số `String` chẵn và không tự ghi đè tên trùng.
- **`setHeader(name,value)`**: thay thế **tất cả giá trị cũ của cùng tên** bằng một giá trị mới.
- Tên header **không phân biệt hoa/thường**; xem `HttpHeaders.allValues/firstValue` sau `build()`.
- Builder **mutable, không thread-safe**; request đã build **immutable**, và `build()` **không gửi** HTTP.
- Không mọi header đều nên có nhiều giá trị; luôn dựa vào contract HTTP/API, tránh header bị hạn chế, đầu vào chứa CRLF và rò rỉ bí mật.

**Tài liệu chính thức (API Java 11 vẫn hiện hành):** [Oracle JDK 11 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html), [Oracle JDK 11 — HttpHeaders](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html), [Oracle Java 26 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html), [JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321).