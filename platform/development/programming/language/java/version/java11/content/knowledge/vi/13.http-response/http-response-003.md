# HttpHeaders và truy vấn một, nhiều giá trị (Java 11+)

**Chủ đề cha: HTTP Response.** Một HTTP response bao gồm status code, headers và body. Các headers như `Content-Type`, `Content-Length`, `Cache-Control`, `Set-Cookie` hoặc tên tùy biến cung cấp metadata về phản hồi. Từ Java 11, module chuẩn `java.net.http` dùng lớp `java.net.http.HttpHeaders` để đọc chúng: lấy **giá trị đầu tiên**, **mọi giá trị**, **giá trị số**, hoặc **toàn bộ map tên–danh sách giá trị**. API này vẫn được hỗ trợ trong Java hiện đại.

Bài học tập trung vào `firstValue`, `allValues`, `firstValueAsLong`, `map`, `HttpHeaders.of`, tra cứu tên không phân biệt chữ hoa/thường, tính bất biến, xử lý header lặp và chuỗi chứa dấu phẩy, kèm ví dụ Java 11 có thể chạy không cần Internet.

## 1. Vì sao header có thể có nhiều giá trị?

Xét response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Trace: alpha
X-Trace: beta
Cache-Control: max-age=60, private

{"ok":true}
```

Tên `X-Trace` xuất hiện hai lần. Trong khi đó `Cache-Control` xuất hiện một lần nhưng chứa dấu phẩy bên trong giá trị. Vì vậy cấu trúc `Map<String,String>` là không đủ; Java biểu diễn headers theo dạng:

```java
Map<String, List<String>>
```

Mỗi tên tương ứng với **một danh sách chuỗi giá trị**:

- Mỗi lần một header cùng tên xuất hiện, giá trị đó là một phần tử của danh sách.
- Với response, thứ tự giá trị trong danh sách là **thứ tự nhận được**.
- Tên header **không phân biệt hoa/thường**: `Content-Type` và `content-type` trỏ đến cùng một header.
- `HttpHeaders` **không tự tách hoặc ghép** chuỗi chứa dấu phẩy. Một giá trị `"max-age=60, private"` vẫn là một phần tử.
- Thứ tự các **entry trong map** không được bảo đảm, dù thứ tự các **giá trị cùng tên** được bảo toàn theo hợp đồng API.

Đây là khác biệt giữa “một header có hai giá trị” và “một giá trị chứa dấu phân cách”. Hai tình huống có thể có cách xử lý nghiệp vụ rất khác nhau.

## 2. Lấy HttpHeaders từ HttpResponse

Cách dùng thông thường trong một ứng dụng HTTP Client:

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
HttpHeaders headers = response.headers();
```

Đây là **đoạn minh họa** bên trong phương thức có `HttpClient client`, `HttpRequest request`, các import `java.net.http` và xử lý `IOException`/`InterruptedException`.

- `response.headers()` trả về tập **response headers** đã nhận.
- `response.statusCode()` là mã HTTP, không phải một header.
- `response.body()` là body tương ứng với BodyHandler, không phải một header.
- `request.headers()` cũng trả về `HttpHeaders` nhưng là tập **request headers** đã build, không phải metadata phản hồi từ server.

Một `HttpHeaders` là tập header **bất biến**, có thể tra cứu nhưng không sửa trực tiếp bằng cách thêm/bớt phần tử.

### Bảng API chính

| API | Kiểu trả về | Nếu header không có | Khi nên dùng |
| --- | --- | --- | --- |
| `firstValue(String name)` | `Optional<String>` | `Optional.empty()` | Chỉ cần giá trị đầu tiên |
| `allValues(String name)` | `List<String>` | Danh sách rỗng | Cần các giá trị lặp |
| `firstValueAsLong(String name)` | `OptionalLong` | `OptionalLong.empty()` | Giá trị đầu tiên dạng số long |
| `map()` | `Map<String,List<String>>` | Trả toàn bộ map | Duyệt toàn bộ headers |
| `HttpHeaders.of(map, filter)` | `HttpHeaders` | Không áp dụng | Tạo fixture cho test/framework |

**Lưu ý:** chính `HttpHeaders` không có getter dạng `headers.get("X")`. Nếu cần đọc từ map, dùng `headers.map().get("X")`; đa số trường hợp, `firstValue`/`allValues` rõ nghĩa và an toàn hơn.

## 3. firstValue: chỉ lấy giá trị đầu tiên

`headers.firstValue("Content-Type")` trả `Optional<String>`. Có thể dùng:

```java
String contentType = headers.firstValue("Content-Type")
        .orElse("application/octet-stream");
```

Đây là đoạn minh họa với biến `headers`. `orElse(...)` là **giá trị dự phòng do ứng dụng lựa chọn**, không phải nội dung header tự phát sinh từ Java.

Nếu response có:

```http
X-Trace: alpha
X-Trace: beta
```

thì `firstValue("X-Trace")` trả `Optional.of("alpha")`, không trả `"alpha,beta"` và không tự lấy giá trị cuối. Chỉ dùng nó khi nghiệp vụ thật sự muốn giá trị đầu tiên.

Nếu header **vắng mặt**, kết quả là `Optional.empty()`, không phải `null` hoặc `""`. Không gọi `Optional.get()` khi chưa xác nhận tồn tại; dùng `orElse`, `ifPresent` hoặc nhánh `isPresent()/isEmpty()` thích hợp.

Đặc biệt, một header **có mặt với chuỗi rỗng** có thể trả `Optional.of("")`: hoàn toàn khác với header không có. Điều này quan trọng khi phân biệt “thiếu thuộc tính” và “thuộc tính được gửi nhưng rỗng”.

## 4. allValues: một hoặc nhiều chuỗi giá trị

`headers.allValues("X-Trace")` trả một `List<String>` chứa tất cả giá trị có tên này. Nếu thiếu header, kết quả là **danh sách rỗng**, không phải `null`. Danh sách không cho phép thay đổi.

```java
List<String> traces = headers.allValues("X-Trace");
for (String trace : traces) {
    System.out.println(trace);
}
```

Đây là đoạn minh họa cần import `java.util.List` và có biến `headers`. Với hai giá trị `alpha` và `beta` như ví dụ, vòng lặp in hai dòng. Java giữ thứ tự giá trị khi nhận response.

**Phân biệt thứ tự:**

- `allValues("X-Trace").get(0)` là giá trị đầu tiên theo thứ tự tập header có được.
- `headers.map().entrySet()` **không bảo đảm thứ tự tên header** khi duyệt.
- Nếu cần tạo log/test output theo thứ tự cố định, nên tự sắp xếp **tên** header trước khi xuất. Không dùng thứ tự bất kỳ từ map làm yêu cầu nghiệp vụ.

Khi cần những giá trị lặp như `Set-Cookie`, `Link` hoặc một header tùy biến, `allValues` thường phù hợp hơn `firstValue`, nhưng việc hiểu ngữ nghĩa từng chuỗi vẫn là trách nhiệm của ứng dụng.

## 5. Tên header tra cứu không phân biệt hoa/thường

Các phương thức nhận tên và map trả về từ `HttpHeaders.map()` đều hỗ trợ tra cứu **case-insensitive**:

```java
headers.firstValue("Content-Type");
headers.firstValue("content-type");
headers.firstValue("CONTENT-TYPE");
headers.map().get("content-type");
```

Đây là đoạn minh họa trong ngữ cảnh có biến `headers`. Nếu tập header chứa `Content-Type`, bốn cách tra cứu đều hướng đến cùng tên. Không cần tự thay đổi case trước khi gọi API.

Trái lại, khi xây map để gọi `HttpHeaders.of(...)`, **hai khóa chỉ khác case** như `"X-Id"` và `"x-id"` là tên trùng theo HTTP; factory sẽ ném `IllegalArgumentException`. Để biểu diễn nhiều giá trị, phải dùng **một khóa duy nhất** với `List<String>` nhiều phần tử.

## 6. Ví dụ độc lập: giá trị đầu, tất cả giá trị, tên khác case

Tệp **`HttpHeadersLookupDemo.java`**:

```java
import java.net.http.HttpHeaders;
import java.util.List;
import java.util.Map;

public class HttpHeadersLookupDemo {
    public static void main(String[] args) {
        HttpHeaders headers = HttpHeaders.of(
                Map.of(
                        "Content-Type", List.of("application/json"),
                        "X-Trace", List.of("alpha", "beta"),
                        "X-Comma", List.of("red, blue"),
                        "X-Count", List.of("12")),
                (name, value) -> true);

        System.out.println("type: "
                + headers.firstValue("content-type").orElse("missing"));
        System.out.println("first trace: "
                + headers.firstValue("X-TRACE").orElse("missing"));
        System.out.println("all traces: "
                + headers.allValues("x-trace"));
        System.out.println("trace count: "
                + headers.allValues("X-Trace").size());
        System.out.println("missing first: "
                + headers.firstValue("X-Missing").isPresent());
        System.out.println("missing all: "
                + headers.allValues("X-Missing").size());
        System.out.println("numeric count: "
                + headers.firstValueAsLong("X-Count").orElse(-1));
        System.out.println("comma value count: "
                + headers.allValues("X-Comma").size());
        System.out.println("comma value: "
                + headers.firstValue("X-Comma").orElse("missing"));
        System.out.println("map lookup count: "
                + headers.map().get("x-trace").size());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HttpHeadersLookupDemo.java
java HttpHeadersLookupDemo
```

Stdout:

```text
type: application/json
first trace: alpha
all traces: [alpha, beta]
trace count: 2
missing first: false
missing all: 0
numeric count: 12
comma value count: 1
comma value: red, blue
map lookup count: 2
```

Hàm `HttpHeaders.of` trong ví dụ là **công cụ tạo dữ liệu test**; trên HTTP response thật, hãy lấy headers bằng `response.headers()`. Tập `X-Trace` có hai phần tử; chuỗi `red, blue` của `X-Comma` không bị tách thành hai phần tử.

## 7. Dấu phẩy trong giá trị: không được nhầm với số lần xuất hiện

| Dữ liệu HTTP | `allValues("X-List")` | Số phần tử |
| --- | --- | :---: |
| Hai dòng `X-List: a` và `X-List: b` | `["a", "b"]` | 2 |
| Một dòng `X-List: a, b` | `["a, b"]` | 1 |
| Một dòng `X-List: a` | `["a"]` | 1 |
| Không có `X-List` | `[]` | 0 |

`HttpHeaders` lưu các **chuỗi header value**, không parse grammar chuyên biệt của từng loại. Không nên tự động gọi `value.split(",")` đối với mọi header:

- `Cache-Control` có cú pháp chỉ thị, có thể chứa danh sách; muốn phân tích đúng cần parser theo quy tắc của header đó.
- `Set-Cookie` có thể xuất hiện nhiều lần và có thuộc tính ngày hết hạn `Expires` chứa dấu phẩy. Việc nối/tách bằng dấu phẩy tùy tiện dễ làm hỏng cookie.
- Header tùy biến có thể coi dấu phẩy là dữ liệu thông thường; phải dựa trên **hợp đồng của chính header**.
- Kết quả in `List.toString()` đôi khi khó phân biệt một phần tử `"a, b"` và hai phần tử `"a"`, `"b"`. Kiểm tra `size()` và giá trị từng phần tử trong test.

### Tệp `RepeatedAndCommaDemo.java`

```java
import java.net.http.HttpHeaders;
import java.util.List;
import java.util.Map;

public class RepeatedAndCommaDemo {
    public static void main(String[] args) {
        HttpHeaders headers = HttpHeaders.of(
                Map.of(
                        "Set-Cookie", List.of(
                                "session=a; Path=/",
                                "theme=dark; Path=/"),
                        "Cache-Control", List.of("max-age=60, private")),
                (name, value) -> true);

        System.out.println("cookies: "
                + headers.allValues("set-cookie").size());
        System.out.println("first cookie: "
                + headers.firstValue("Set-Cookie").orElse("missing"));
        System.out.println("cache values: "
                + headers.allValues("Cache-Control").size());
        System.out.println("cache text: "
                + headers.firstValue("cache-control").orElse("missing"));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 RepeatedAndCommaDemo.java
java RepeatedAndCommaDemo
```

```text
cookies: 2
first cookie: session=a; Path=/
cache values: 1
cache text: max-age=60, private
```

Đây là một fixture chỉ nhằm minh họa cách `HttpHeaders` lưu giá trị. Nó không thực hiện parse cookie hay áp dụng logic caching.

## 8. firstValueAsLong: giá trị số và lỗi cần xử lý

`firstValueAsLong(name)` trả `OptionalLong` theo kết quả chuyển **giá trị đầu tiên** của header tương ứng thành số nguyên 64 bit. Ba tình huống:

1. Header **không tồn tại** → `OptionalLong.empty()`.
2. Header tồn tại và giá trị đầu tiên **parse được thành `long`** → `OptionalLong.of(number)`.
3. Header tồn tại nhưng giá trị đầu tiên **không parse được thành `long`** → ném `NumberFormatException` (bao gồm giá trị vượt phạm vi).

Ví dụ dùng với `Content-Length`:

```java
long declaredLength = headers
        .firstValueAsLong("Content-Length")
        .orElse(-1L);
```

Đây là đoạn minh họa. Giá trị `-1` là quy ước của **ứng dụng** khi không có header, không phải một HTTP content length hợp lệ được Java tự cấp. Nếu không muốn đặt sentinel, giữ `OptionalLong` và xử lý sự thiếu vắng rõ ràng.

### Tệp `NumericHeaderDemo.java`

```java
import java.net.http.HttpHeaders;
import java.util.List;
import java.util.Map;

public class NumericHeaderDemo {
    public static void main(String[] args) {
        HttpHeaders headers = HttpHeaders.of(
                Map.of(
                        "X-Size", List.of("120"),
                        "X-Bad", List.of("12MB")),
                (name, value) -> true);

        System.out.println("size: "
                + headers.firstValueAsLong("x-size").orElse(-1));
        System.out.println("missing: "
                + headers.firstValueAsLong("X-Unknown").isPresent());

        try {
            headers.firstValueAsLong("X-Bad");
            System.out.println("unexpected");
        } catch (NumberFormatException expected) {
            System.out.println("invalid number: NumberFormatException");
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NumericHeaderDemo.java
java NumericHeaderDemo
```

```text
size: 120
missing: false
invalid number: NumberFormatException
```

Đối với một HTTP response thực, `Content-Length` **có thể không tồn tại**, vì không phải mọi phản hồi đều khai báo độ dài. Phương thức `firstValueAsLong` kiểm tra chuyển số, chứ không tự bảo đảm con số phù hợp với số byte body đã nhận, quy tắc protocol hoặc giới hạn tài nguyên của ứng dụng.

## 9. map(): truy vấn toàn bộ nhưng không được sửa

`headers.map()` trả `Map<String,List<String>>` **unmodifiable**; các danh sách giá trị cũng không sửa được. Đây là view read-only.

```java
Map<String, List<String>> asMap = headers.map();
List<String> values = asMap.get("x-trace");
```

Đây là đoạn minh họa với biến `headers`. Tra cứu tên trên map cũng **case-insensitive**. Tuy nhiên, không bảo đảm thứ tự `entrySet()`; nếu cần log theo thứ tự, tự trích tên và sắp xếp.

Các thao tác sau **không hợp lệ theo hợp đồng** và gây `UnsupportedOperationException`:

```java
// Ví dụ sai cố ý, không chạy thành công:
// headers.map().put("X-New", List.of("value"));
// headers.allValues("X-Trace").add("gamma");
```

Muốn thêm header vào một **request mới**, hãy dùng `HttpRequest.Builder.header(...)` hoặc `setHeader(...)` trước khi `build()`, không sửa `HttpHeaders` của response.

### Tệp `HeadersReadOnlyDemo.java`

```java
import java.net.http.HttpHeaders;
import java.util.List;
import java.util.Map;

public class HeadersReadOnlyDemo {
    public static void main(String[] args) {
        HttpHeaders headers = HttpHeaders.of(
                Map.of("X-Tag", List.of("a", "b")),
                (name, value) -> true);

        System.out.println("case-insensitive: "
                + headers.map().get("x-tag"));

        try {
            headers.map().put("X-New", List.of("value"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("map: unmodifiable");
        }

        try {
            headers.allValues("X-Tag").add("c");
        } catch (UnsupportedOperationException expected) {
            System.out.println("list: unmodifiable");
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HeadersReadOnlyDemo.java
java HeadersReadOnlyDemo
```

```text
case-insensitive: [a, b]
map: unmodifiable
list: unmodifiable
```

Bất biến của `HttpHeaders` không đồng nghĩa **dữ liệu header từ server là đáng tin**. Ứng dụng vẫn phải xác thực header theo nhu cầu và không sử dụng giá trị đầu vào chưa kiểm tra trong ngữ cảnh nhạy cảm.

## 10. HttpHeaders.of: tạo fixture, lọc và xử lý khoảng trắng

Phương thức static có từ Java 11:

```java
static HttpHeaders of(
        Map<String, List<String>> headerMap,
        BiPredicate<String, String> filter)
```

`HttpHeaders.of` chủ yếu được dùng trong **test/framework**, không phải cách điển hình để lấy response headers. Nó xây tập read-only từ map và một predicate quyết định giữ/bỏ mỗi cặp tên–giá trị.

Những điều cần nhớ theo Javadoc:

- Hai khóa nguồn chỉ khác chữ hoa/thường như `X-Tag` và `x-tag` gây `IllegalArgumentException` vì cùng tên header.
- Khoảng trắng ở **đầu/cuối** mỗi chuỗi giá trị được loại bỏ trước khi xử lý.
- Chỉ thêm header nếu sau lọc còn ít nhất một giá trị; **một chuỗi rỗng vẫn có thể là giá trị hiện diện**.
- Map, filter, tên, danh sách hoặc phần tử giá trị `null` gây `NullPointerException`.
- Factory này không có tác dụng sửa `response.headers()` đã nhận.

### Tệp `HeadersFilterDemo.java`

```java
import java.net.http.HttpHeaders;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class HeadersFilterDemo {
    public static void main(String[] args) {
        Map<String, List<String>> input = new LinkedHashMap<>();
        input.put("X-Mode", List.of("  alpha  ", " beta "));
        input.put("X-Drop", List.of("secret"));
        input.put("X-Blank", List.of(" "));

        HttpHeaders headers = HttpHeaders.of(
                input,
                (name, value) -> !name.equalsIgnoreCase("X-Drop"));

        System.out.println("mode: " + headers.allValues("x-mode"));
        System.out.println("dropped: "
                + headers.firstValue("X-Drop").isPresent());
        System.out.println("blank present: "
                + headers.firstValue("X-Blank").isPresent());
        System.out.println("blank length: "
                + headers.firstValue("X-Blank")
                        .orElse("missing").length());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HeadersFilterDemo.java
java HeadersFilterDemo
```

```text
mode: [alpha, beta]
dropped: false
blank present: true
blank length: 0
```

`X-Drop` bị loại hoàn toàn. `X-Blank` vẫn **hiện diện** nhưng chứa một giá trị chuỗi rỗng sau khi loại bỏ khoảng trắng. Điều này xác nhận khác biệt giữa `firstValue(...).isPresent()` và kiểm tra `firstValue(...).orElse("").isEmpty()`.

### Dữ liệu đầu vào có hai tên trùng nhau khác case

```java
Map<String, List<String>> bad = new LinkedHashMap<>();
bad.put("X-Trace", List.of("one"));
bad.put("x-trace", List.of("two"));

// HttpHeaders.of(bad, (name, value) -> true)
// ném IllegalArgumentException.
```

Đoạn này minh họa trong ngữ cảnh có import `Map`, `List` và `LinkedHashMap`. Hãy biểu diễn nhiều giá trị bằng một khóa `"X-Trace"` với `List.of("one", "two")` thay vì tạo hai khóa không phân biệt case.

## 11. Đọc response thật với localhost, không cần Internet

Để minh họa đường thực `HttpResponse.headers()`, ví dụ này tạo HTTP server test trên `127.0.0.1` bằng module `jdk.httpserver` của JDK. Server trả hai lần `X-Tag`, một `X-Memo` chứa dấu phẩy và một số ở `X-Count`. Client nhận response rồi đọc headers.

### Tệp `HttpResponseHeadersDemo.java`

```java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;

public class HttpResponseHeadersDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/demo", exchange -> {
            exchange.getResponseHeaders().add("X-Tag", "east");
            exchange.getResponseHeaders().add("X-Tag", "west");
            exchange.getResponseHeaders().set("X-Memo", "red, blue");
            exchange.getResponseHeaders().set("X-Count", "7");

            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        server.start();
        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/demo");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET().build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            HttpHeaders headers = response.headers();
            List<String> tags = headers.allValues("x-tag");

            System.out.println("status: " + response.statusCode());
            System.out.println("body: " + response.body());
            System.out.println("tag count: " + tags.size());
            System.out.println("both tags: "
                    + (tags.contains("east")
                            && tags.contains("west")));
            System.out.println("memo count: "
                    + headers.allValues("X-Memo").size());
            System.out.println("memo: "
                    + headers.firstValue("x-memo").orElse("missing"));
            System.out.println("count: "
                    + headers.firstValueAsLong("X-Count").orElse(-1));
        } finally {
            server.stop(0);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 HttpResponseHeadersDemo.java
java --add-modules jdk.httpserver HttpResponseHeadersDemo
```

Stdout khi server loopback hoạt động:

```text
status: 200
body: ok
tag count: 2
both tags: true
memo count: 1
memo: red, blue
count: 7
```

Chương trình chỉ in các header do server test tự đặt, không phụ thuộc thứ tự của `Date` hoặc các header mặc định. Vì server lấy cổng động, không cần đặt cổng cố định. Nếu môi trường sandbox không cho mở socket loopback, ví dụ có thể thất bại do chính sách môi trường; các test `HttpHeaders.of` phía trên không dùng network.

## 12. Các mẫu truy vấn theo nghiệp vụ

### Chỉ cần Content-Type

```java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("application/octet-stream");
```

Đoạn minh họa: giá trị fallback do ứng dụng chọn. Khi quyết định cách đọc body, cần parse MIME type và các tham số (ví dụ charset) theo hợp đồng, đừng chỉ so sánh chính xác chuỗi `"application/json"` khi header có thể kèm tham số.

### Cần toàn bộ Set-Cookie

```java
List<String> cookies = response.headers().allValues("Set-Cookie");
```

Đoạn minh họa: giữ từng giá trị riêng; dùng `CookieManager/CookieHandler` hoặc parser chuyên biệt nếu phải xử lý cookie. Không gộp các giá trị thành một chuỗi nối bằng dấu phẩy.

### Cần độ dài khai báo nếu có

```java
long declaredBytes = response.headers()
        .firstValueAsLong("Content-Length")
        .orElse(-1L);
```

Đoạn minh họa: `-1` là sentinel do ứng dụng đặt, không phải giá trị Content-Length hợp lệ; header có thể thiếu và dữ liệu có thể sai định dạng. Nên kiểm tra kích thước thực nhận nếu có yêu cầu hạn chế tài nguyên hay bảo toàn dữ liệu.

### Tìm một giá trị đúng nguyên chuỗi

```java
boolean enabled = response.headers()
        .allValues("X-Feature")
        .stream()
        .anyMatch("beta"::equals);
```

Đoạn minh họa: trả `true` khi một **phần tử trong danh sách** đúng bằng `"beta"`. Nếu server gửi duy nhất một giá trị `"alpha, beta"`, biểu thức sẽ trả `false`; khi cần parse một header dạng list, phải làm theo cú pháp riêng của header đó.

## 13. An toàn dữ liệu và các giới hạn cần hiểu

- `HttpHeaders` immutable nhưng **giá trị server gửi chưa chắc đáng tin**. Nếu dùng header để tính kích thước tải, điều hướng, quyền truy cập hay cache, cần validate theo chuẩn và yêu cầu nghiệp vụ.
- Không log toàn bộ response headers một cách vô điều kiện. `Set-Cookie`, token hoặc header tùy chỉnh có thể chứa dữ liệu nhạy cảm; ẩn hoặc loại trước khi ghi log.
- `firstValueAsLong` parse được số không đồng nghĩa số đó hợp lệ về mặt protocol hay đủ an toàn về giới hạn kích thước.
- Không giả định toàn bộ headers từ mạng sẽ có trong map đúng một thứ tự cố định. Dùng truy vấn theo tên; nếu phải duyệt, hãy sắp xếp tên trước khi xuất log hoặc kiểm thử.
- Không đồng nhất `java.net.http.HttpHeaders` (HTTP Client) với `com.sun.net.httpserver.Headers` (fixture server) hay các lớp headers của thư viện web khác; mỗi API có hợp đồng riêng.
- Nếu chuyển headers giữa thư viện, kiểm tra cách thư viện kia biểu diễn tên không phân biệt case và giá trị lặp, đừng làm mất cấu trúc chỉ vì chuyển thành `Map<String,String>`.

## 14. Bộ regression test chạy độc lập

Các test sau xác nhận tên không phân biệt hoa/thường, một/nhiều giá trị, header thiếu, chuỗi rỗng, số hợp lệ/sai, dấu phẩy, tính bất biến, filter và tên trùng. Sử dụng `AssertionError` thay vì câu lệnh `assert` vì `assert` của Java có thể bị tắt khi JVM không bật `-ea`.

### Tệp `HttpHeadersRegression.java`

```java
import java.net.http.HttpHeaders;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class HttpHeadersRegression {
    private static int checks = 0;

    private static void check(String name, boolean condition) {
        checks++;
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        HttpHeaders headers = HttpHeaders.of(
                Map.of(
                        "Content-Type", List.of("application/json"),
                        "X-Tag", List.of("alpha", "beta"),
                        "X-Comma", List.of("a, b"),
                        "X-Count", List.of("42"),
                        "X-Bad", List.of("oops"),
                        "X-Blank", List.of(" ")),
                (name, value) -> true);

        check("content type", headers.firstValue("Content-Type")
                .orElse("").equals("application/json"));
        check("case insensitive", headers.firstValue("content-type")
                .orElse("").equals("application/json"));
        check("first tag", headers.firstValue("X-Tag")
                .orElse("").equals("alpha"));
        check("two tags", headers.allValues("X-Tag").size() == 2);
        check("second tag", headers.allValues("x-tag")
                .get(1).equals("beta"));
        check("case insensitive map", headers.map()
                .get("x-tag").size() == 2);

        check("missing Optional",
                headers.firstValue("X-Missing").isEmpty());
        check("missing List",
                headers.allValues("X-Missing").isEmpty());

        check("number", headers.firstValueAsLong("X-Count")
                .orElse(-1) == 42);
        check("missing number", headers.firstValueAsLong(
                "X-Missing").isEmpty());

        boolean invalidNumberRejected = false;
        try {
            headers.firstValueAsLong("X-Bad");
        } catch (NumberFormatException expected) {
            invalidNumberRejected = true;
        }
        check("invalid number", invalidNumberRejected);

        check("comma stays one value",
                headers.allValues("X-Comma").size() == 1);
        check("comma unchanged", headers.firstValue("X-Comma")
                .orElse("").equals("a, b"));

        check("empty header present",
                headers.firstValue("X-Blank").isPresent());
        check("empty header value", headers.firstValue("X-Blank")
                .orElse("missing").isEmpty());

        boolean mapRejected = false;
        try {
            headers.map().put("X-New", List.of("v"));
        } catch (UnsupportedOperationException expected) {
            mapRejected = true;
        }
        check("map cannot change", mapRejected);

        boolean listRejected = false;
        try {
            headers.allValues("X-Tag").add("gamma");
        } catch (UnsupportedOperationException expected) {
            listRejected = true;
        }
        check("list cannot change", listRejected);

        HttpHeaders filtered = HttpHeaders.of(
                Map.of("X-Keep", List.of("yes"),
                        "X-Drop", List.of("no")),
                (name, value) -> !name.equalsIgnoreCase("X-Drop"));
        check("filter keeps", filtered.firstValue("x-keep")
                .orElse("").equals("yes"));
        check("filter drops", filtered.allValues("X-Drop").isEmpty());

        Map<String, List<String>> duplicate = new LinkedHashMap<>();
        duplicate.put("X-Dupe", List.of("a"));
        duplicate.put("x-dupe", List.of("b"));
        boolean duplicateRejected = false;
        try {
            HttpHeaders.of(duplicate, (name, value) -> true);
        } catch (IllegalArgumentException expected) {
            duplicateRejected = true;
        }
        check("duplicate case-insensitive keys", duplicateRejected);

        System.out.println("PASS: " + checks + " checks");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HttpHeadersRegression.java
java HttpHeadersRegression
```

```text
PASS: 20 checks
```

**Đếm test:** 6 cho tra cứu giá trị và case, 2 cho header thiếu, 3 cho giá trị số, 2 cho dấu phẩy, 2 cho giá trị rỗng, 2 cho map/list bất biến, 2 cho filter và 1 cho tên trùng khác case: **20**. Nếu trường hợp nào sai, chương trình ném `AssertionError` với tên điều kiện.

Khi cần kiểm tra HTTP response của backend thật, bổ sung integration test với server do dự án kiểm soát và trường hợp server/proxy thêm hoặc lặp header. Test dùng `HttpHeaders.of` kiểm tra **hợp đồng API**, còn test qua mạng kiểm tra **cách dữ liệu được nhận**.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `firstValue` dù cần nhiều giá trị | Bỏ mất phần tử sau phần tử đầu | Dùng `allValues` |
| Nghĩ header thiếu làm `allValues` trả null | API trả danh sách rỗng | Dùng `isEmpty()` |
| Gọi `firstValue(...).get()` khi thiếu | Optional có thể rỗng | Dùng `orElse`/kiểm tra tồn tại |
| Nhầm `"a, b"` với hai lần xuất hiện header | HttpHeaders không tự split | Xem `size()` và parse theo grammar |
| Tách `Set-Cookie` bằng dấu phẩy tùy tiện | Có thể phá cookie | Cookie parser thích hợp |
| Sửa `headers.map()` | Map unmodifiable | Xử lý trên cấu trúc dữ liệu mới |
| Dựa vào thứ tự duyệt tên từ `map()` | API không bảo đảm thứ tự | Sắp xếp tên |
| Không xử lý `NumberFormatException` | Header số có thể sai | Xử lý lỗi dữ liệu |
| Tạo hai khóa khác case ở `HttpHeaders.of` | Cùng một tên header | Một khóa, danh sách nhiều giá trị |
| Coi headers immutable là trusted | Chuỗi giá trị vẫn là dữ liệu bên ngoài | Validate trước khi sử dụng |

## 16. Câu hỏi tự luyện

**A.** Response có `X-Id: a` và `X-Id: b`. `firstValue("x-id")` và `allValues("X-ID")` trả gì?

**B.** Response chỉ có một lần xuất hiện `X-Id: a, b`. `allValues("X-Id").size()` bằng mấy?

**C.** Nếu không có header `X-Count` thì `firstValueAsLong("X-Count")` trả gì? Nếu giá trị là `"bad"` thì sao?

**D.** Vì sao `HttpHeaders.of` từ chối map có `"X-Id"` và `"x-id"` làm hai khóa?

**E.** Có thể thay đổi một response header bằng `response.headers().map().put(...)` không?

**Đáp án:** A. `Optional.of("a")` và danh sách `["a","b"]`. B. **1**, vì dấu phẩy không tạo phần tử thứ hai. C. `OptionalLong.empty()` khi thiếu; `NumberFormatException` khi không parse được. D. Vì tên header không phân biệt case; dùng một khóa chứa nhiều giá trị. E. Không; map không sửa được và ném `UnsupportedOperationException`.

## Tài liệu chính thức

- [Java SE 11 — HttpHeaders: firstValue, allValues, firstValueAsLong, map, of](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 26 — HttpHeaders vẫn được hỗ trợ trong Java hiện đại](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpHeaders.html).
- [Java SE 11 — HttpResponse.headers()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html).
- [Java SE 11 — HttpRequest.headers()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html).
- [Java SE 11 — HttpClient.send() và BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
