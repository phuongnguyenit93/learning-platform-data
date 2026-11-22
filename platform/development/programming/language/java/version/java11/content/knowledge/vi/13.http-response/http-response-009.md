# `BodySubscribers.mapping` và biến đổi kết quả HTTP Response (Java 11+)

## 1. Mục tiêu bài học

Trong HTTP Client chuẩn của Java 11 (`java.net.http`), máy khách nhận dữ liệu phản hồi dưới dạng byte. `HttpResponse.BodySubscriber<T>` chịu trách nhiệm tiếp nhận dòng byte của response và cung cấp kết quả dạng `T`, chẳng hạn `String`, `byte[]`, `InputStream` hoặc một đối tượng do ứng dụng định nghĩa.

Từ **Java 11**, phương thức:

```java
static <T, U> HttpResponse.BodySubscriber<U> mapping(
        HttpResponse.BodySubscriber<T> upstream,
        Function<? super T, ? extends U> mapper)
```

cho phép **biến đổi kết quả body** mà một `BodySubscriber<T>` khác tạo ra thành giá trị `U`. Ví dụ: tiếp nhận response text `"10,20,30"` dưới dạng `String` rồi chuyển thành số nguyên `60`; hoặc nhận `"red,green,blue"` rồi trả `List<String>` thay vì trả chuỗi gốc.

Ba đối tượng phải phân biệt:

- **`BodyHandler<T>`:** quyết định tạo `BodySubscriber<T>` nào sau khi nhận metadata phản hồi (status code và headers). Nó là đối số được truyền cho `HttpClient.send(...)` hoặc `sendAsync(...)`.
- **`BodySubscriber<T>`:** nhận body bytes và sinh kết quả kiểu `T` thông qua cơ chế reactive streams (`Flow.Subscriber`, `getBody()` trả `CompletionStage<T>`).
- **`BodySubscribers.mapping(upstream, mapper)`:** **bọc** subscriber có sẵn, áp dụng hàm chuyển đổi cho giá trị body mà subscriber đó tạo ra, để kết quả cuối có kiểu `U`.

Đây là API **vẫn áp dụng trên các JDK hiện đại**, không phải cách làm legacy. Bài tập tập trung vào Java 11 và các lưu ý quan trọng còn có ý nghĩa hiện nay, đặc biệt là hiệu năng, việc xử lý lỗi và tài nguyên của `InputStream`.

## 2. Cơ chế hoạt động và chữ ký generic

Xét biểu thức:

```java
HttpResponse.BodySubscriber<Integer> subscriber =
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                String::length);
```

Giải thích:

1. `BodySubscribers.ofString(UTF_8)` tạo `BodySubscriber<String>`, tích lũy byte phản hồi và giải mã sang văn bản UTF-8.
2. `String::length` là `Function<String, Integer>`: nhận chuỗi, trả độ dài `int` được boxing thành `Integer`.
3. `mapping(...)` tạo một **`BodySubscriber<Integer>`** mới. Nhờ generic, kiểu body cuối cùng có thể khác kiểu của subscriber ban đầu.
4. `mapping` không tự thực hiện request HTTP, cũng không làm thay đổi byte trên mạng. Nó thay đổi **giá trị `HttpResponse.body()`** nhận được bởi chương trình.

Minh họa dòng dữ liệu:

```text
HTTP response body (byte)
          |
          v
upstream BodySubscriber<String>
          |
          | ofString(UTF_8): giải mã toàn bộ byte thành String
          v
      "10,20,30"       (kiểu T = String)
          |
          | mapper: s -> parse/sum
          v
           60          (kiểu U = Integer)
          |
          v
HttpResponse<Integer>.body()
```

**Quan trọng:** `mapping` biến đổi **đối tượng kết quả body**, không phải hàm tự động xử lý từng mảnh `ByteBuffer` trong callback `onNext`. Khi upstream là `ofString(UTF_8)`, toàn bộ text được gom thành `String` rồi mới có thể map. Với upstream khác như `ofInputStream()`, thời điểm body object sẵn sàng có thể sớm hơn lúc toàn bộ byte đã tới, vì `InputStream` là đối tượng đọc dữ liệu theo luồng.

### 2.1. Ý nghĩa của `<T, U>`

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu body của upstream subscriber | `String` |
| `U` | Kiểu body muốn nhận sau chuyển đổi | `List<String>`, `Integer`, `MyDto` |
| `upstream` | Subscriber đang biết cách nhận body bytes và tạo `T` | `BodySubscribers.ofString(UTF_8)` |
| `mapper` | Hàm chuyển `T` thành `U` | `String::length`, `csv -> parse(csv)` |
| `mapping(...)` | Subscriber bọc, giữ chức năng nhận bytes nhưng đổi giá trị kết quả | `BodySubscriber<List<String>>` |

Kiểu `T` và `U` có thể giống nhau. Ví dụ `String::trim` chuyển `String` thành `String` đã xóa whitespace đầu/cuối. Tuy nhiên, điểm mạnh của `mapping` là có thể tạo **kết quả mới có kiểu chính xác**, giảm việc phải xử lý chuỗi thủ công sau mỗi lần gửi.

## 3. Tích hợp với `HttpClient.send` và `BodyHandler`

`HttpClient` nhận một `BodyHandler<U>`, không nhận trực tiếp một `BodySubscriber<U>` ở tham số thứ hai của `send`. Vì vậy cách dùng phổ biến là tạo subscriber **trong lambda handler**:

```java
HttpResponse<List<String>> response = client.send(request, info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                text -> Arrays.stream(text.split(","))
                        .map(String::trim)
                        .collect(Collectors.toList())));

List<String> values = response.body();
```

**Mã minh họa không độc lập:** cần khai báo `client`, `request`, import `HttpResponse`, `StandardCharsets`, `Arrays`, `Collectors`, `List`, và xử lý `IOException`/`InterruptedException`. Một chương trình chạy độc lập, không cần Internet, nằm ở mục 6.

Diễn giải:

- `info` là `HttpResponse.ResponseInfo`, cung cấp status code, headers, phiên bản HTTP. Nếu không dùng tới metadata, có thể đặt tên `ignored` cho rõ.
- `BodySubscribers.mapping(...)` trả `BodySubscriber<List<String>>`, đúng kiểu yêu cầu bởi `BodyHandler<List<String>>`.
- Sau khi `client.send(...)` hoàn thành thành công, `response.body()` là `List<String>`, **không phải `String`**.

Nếu cần tái sử dụng logic, đặt handler vào biến:

```java
HttpResponse.BodyHandler<Integer> lengthHandler = info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                String::length);

// Có thể dùng với send hoặc sendAsync.
```

Mỗi lần `HttpClient` xử lý một response, handler sẽ được gọi để tạo subscriber phù hợp với response đó. Không lưu một subscriber có trạng thái nhận body rồi tái sử dụng cho nhiều response; hãy tạo subscriber mới cho mỗi lần.

## 4. Những kiểu biến đổi kết quả phù hợp

### 4.1. Chuỗi → đối tượng đơn giản

Ví dụ response body là một số nguyên dưới dạng văn bản:

```java
HttpResponse.BodyHandler<Integer> numberHandler = info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                text -> Integer.parseInt(text.trim()));
```

Nếu body là `" 42 "` thì `response.body()` là số nguyên `42`. Nếu body không phải số nguyên hợp lệ, `Integer.parseInt` ném `NumberFormatException`, khiến thao tác map thất bại; xem mục 8.

### 4.2. Chuỗi → danh sách phần tử

```java
HttpResponse.BodyHandler<List<String>> csvHandler = info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                text -> Arrays.stream(text.split(","))
                        .map(String::trim)
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.toList()));
```

Đây chỉ là ví dụ cho **danh sách phân tách dấu phẩy không có escaping/quoting**. Nó **không phải parser CSV chuẩn RFC 4180**: trường có dấu phẩy trong dấu ngoặc kép, ký tự xuống dòng hoặc escape phức tạp phải được xử lý bằng thư viện/parser CSV đáng tin cậy. Tương tự, nếu response là JSON thật, dùng thư viện JSON (ví dụ Jackson hoặc JSON-B tùy stack) để parse, thay vì dùng `split(",")` hay substring tùy tiện.

### 4.3. Mảng byte → kết quả tùy biến

```java
HttpResponse.BodyHandler<Integer> byteCount = info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofByteArray(),
                bytes -> bytes.length);
```

Kết quả `Integer` là số **byte body** mà subscriber nhận được. Cách này có thể phù hợp với payload nhỏ; tuy nhiên `ofByteArray()` vẫn gom toàn bộ dữ liệu vào bộ nhớ. Với body lớn, ưu tiên xử lý streaming có giới hạn thay vì tích lũy mảng khổng lồ chỉ để tính kích thước.

### 4.4. Chuỗi → DTO

Về kiến trúc, một handler chuyển text JSON thành DTO có thể theo dạng:

```java
// MÃ MINH HỌA: giả định đã định nghĩa lớp Product,
// đã có một JSON mapper thực tế trong ứng dụng.
HttpResponse.BodyHandler<Product> productHandler = info ->
        HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                json -> jsonMapper.readValue(json, Product.class));
```

Mã này **không chạy độc lập** nếu chưa có `Product`, `jsonMapper` và thư viện tương ứng; nếu `readValue` ném checked exception, lambda phải bọc hoặc xử lý ngoại lệ theo cách hợp lệ. Java 11 **không có sẵn một JSON object mapper đa năng trong `java.net.http`**. Ví dụ chạy hoàn chỉnh bên dưới sử dụng định dạng text đơn giản để không thêm dependency.

## 5. Mapping và metadata HTTP là hai tầng độc lập

`BodySubscribers.mapping` chỉ chuyển **body value**; nó không sửa `statusCode()`, response headers, URI hay phiên bản HTTP. Một response mang mã lỗi HTTP như **503** vẫn có thể được subscriber gom và map body thành `String`, `Integer` hoặc đối tượng khác.

Ví dụ chọn cách xử lý dựa trên status:

```java
HttpResponse.BodyHandler<String> checkedHandler = info -> {
    if (info.statusCode() / 100 != 2) {
        return HttpResponse.BodySubscribers.mapping(
                HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
                errorBody -> "HTTP " + info.statusCode() + ": " + errorBody);
    }
    return HttpResponse.BodySubscribers.mapping(
            HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8),
            String::trim);
};
```

Đây là mã minh họa **chọn subscriber theo status**, không tự biến HTTP lỗi thành Java exception. Tùy ứng dụng, có thể trả một kiểu kết quả thống nhất (ví dụ `ApiResult<T>`) hoặc để tầng xử lý response kiểm tra `statusCode()` rồi quyết định ném lỗi. Không mặc định rằng `client.send(...)` ném exception khi server trả 4xx/5xx: HTTP status lỗi thông thường vẫn là một **HTTP response hợp lệ**.

Nếu parser chỉ hiểu body thành công, hãy kiểm tra `ResponseInfo.statusCode()` hoặc tách rõ đường xử lý lỗi. Đừng cố parse một trang HTML lỗi 500 như JSON chỉ vì request bình thường mong JSON.

## 6. Chương trình Java 11 hoàn chỉnh: HTTP cục bộ + mapping nhiều kiểu

Ví dụ dùng một HTTP server nhỏ **trên địa chỉ loopback 127.0.0.1**, nên **không cần Internet hay API bên ngoài**. Đây là phần minh họa end-to-end: `HttpClient` thực sự gửi HTTP đến server đang chạy cùng máy, `BodyHandler` tạo subscriber mapping và `HttpResponse.body()` mang kiểu đã chuyển đổi.

Để dựng server kiểm thử, ví dụ sử dụng module **`jdk.httpserver`** có trong JDK 11 thông dụng. Đây là module thuộc JDK, không phải yêu cầu phải dùng máy chủ này trong ứng dụng production. Nếu chạy trên custom runtime image không chứa `jdk.httpserver`, cần bổ sung module hoặc chọn một server thử nghiệm khác.

Tạo tệp **`BodyMappingDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpResponse.BodyHandler;
import java.net.http.HttpResponse.BodySubscribers;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletionException;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class BodyMappingDemo {
    static void respond(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/colors",
                ex -> respond(ex, 200, " red, green , blue "));
        server.createContext("/numbers",
                ex -> respond(ex, 200, "10,20,30"));
        server.createContext("/error",
                ex -> respond(ex, 503, "temporarily unavailable"));
        server.createContext("/bad",
                ex -> respond(ex, 200, "not-an-integer"));
        server.start();

        try {
            String root = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest colors = HttpRequest.newBuilder(
                    URI.create(root + "/colors")).GET().build();

            BodyHandler<List<String>> splitAndTrim = responseInfo ->
                    BodySubscribers.mapping(
                            BodySubscribers.ofString(StandardCharsets.UTF_8),
                            csv -> Arrays.stream(csv.split(","))
                                    .map(String::trim)
                                    .filter(s -> !s.isEmpty())
                                    .collect(Collectors.toList()));

            HttpResponse<List<String>> first = client.send(colors, splitAndTrim);
            System.out.println("colors status: " + first.statusCode());
            System.out.println("colors body: " + first.body());

            HttpRequest numbers = HttpRequest.newBuilder(
                    URI.create(root + "/numbers")).build();
            HttpResponse<Integer> sum = client.send(numbers, responseInfo ->
                    BodySubscribers.mapping(
                            BodySubscribers.ofString(StandardCharsets.UTF_8),
                            csv -> Arrays.stream(csv.split(","))
                                    .map(String::trim)
                                    .mapToInt(Integer::parseInt)
                                    .sum()));
            System.out.println("sum body: " + sum.body());

            HttpResponse<Integer> async = client.sendAsync(numbers, responseInfo ->
                    BodySubscribers.mapping(
                            BodySubscribers.ofString(StandardCharsets.UTF_8),
                            String::length)).join();
            System.out.println("async length: " + async.body());

            HttpRequest error = HttpRequest.newBuilder(
                    URI.create(root + "/error")).GET().build();
            HttpResponse<String> response503 = client.send(error, info ->
                    BodySubscribers.mapping(
                            BodySubscribers.ofString(StandardCharsets.UTF_8),
                            String::toUpperCase));
            System.out.println("error status: " + response503.statusCode());
            System.out.println("error body: " + response503.body());

            BodyHandler<Supplier<String>> deferred = info ->
                    BodySubscribers.mapping(
                            BodySubscribers.ofInputStream(),
                            input -> (Supplier<String>) () -> {
                                try (InputStream stream = input) {
                                    return new String(stream.readAllBytes(),
                                            StandardCharsets.UTF_8).trim();
                                } catch (IOException ex) {
                                    throw new UncheckedIOException(ex);
                                }
                            });

            HttpResponse<Supplier<String>> deferredResponse =
                    client.send(colors, deferred);
            System.out.println("deferred text: " + deferredResponse.body().get());

            HttpRequest bad = HttpRequest.newBuilder(
                    URI.create(root + "/bad")).build();
            try {
                client.sendAsync(bad, info ->
                        BodySubscribers.mapping(
                                BodySubscribers.ofString(StandardCharsets.UTF_8),
                                Integer::parseInt)).join();
                System.out.println("bad mapping: unexpected success");
            } catch (CompletionException expected) {
                Throwable cause = expected;
                while (cause.getCause() != null) {
                    cause = cause.getCause();
                }
                System.out.println("bad mapping cause: " +
                        cause.getClass().getSimpleName());
            }
        } finally {
            server.stop(0);
        }
    }
}
```

**Biên dịch và chạy với JDK 11+** (bao gồm module `jdk.httpserver` dùng cho server thử nghiệm):

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 BodyMappingDemo.java
java --add-modules jdk.httpserver BodyMappingDemo
```

**Đầu ra chính xác đã kiểm thử:**

```text
colors status: 200
colors body: [red, green, blue]
sum body: 60
async length: 8
error status: 503
error body: TEMPORARILY UNAVAILABLE
deferred text: red, green , blue
bad mapping cause: NumberFormatException
```

### Phân tích kết quả

1. `/colors` trả văn bản có dấu cách `" red, green , blue "`. Subscriber `ofString(UTF_8)` tạo `String`; mapper `split + trim + filter` biến thành `List<String>` gồm ba phần tử. Vì vậy `first.body()` có kiểu `List<String>` và khi in là `[red, green, blue]`.
2. `/numbers` trả `"10,20,30"`; mapper chuyển từng phần bằng `Integer.parseInt` rồi tính tổng, cho `60`. Đây là chuyển đổi **`String → Integer`**, không phải phép biến đổi HTTP status.
3. `sendAsync(...)` dùng handler tương tự; mapper `String::length` chuyển body `"10,20,30"` thành `Integer 8`, và `join()` lấy `HttpResponse<Integer>` sau khi tác vụ hoàn tất.
4. `/error` trả **HTTP 503**; mapper vẫn chuyển chữ thường sang chữ hoa để body là `"TEMPORARILY UNAVAILABLE"`. Giá trị `statusCode() == 503` **không bị mapping thay đổi**, và Java không tự coi 503 là lỗi parse.
5. `ofInputStream()` kết hợp `mapping` trả về **`Supplier<String>`** thay vì đọc hết stream ngay trong hàm mapping. `deferredResponse.body().get()` mới đọc dữ liệu và tự đóng stream bằng `try-with-resources`. `trim()` bỏ khoảng trắng hai đầu chuỗi nhưng không thay đổi khoảng trắng quanh dấu phẩy ở bên trong, nên kết quả là `"red, green , blue"`.
6. `/bad` trả `"not-an-integer"`; mapper `Integer::parseInt` ném `NumberFormatException`, và `CompletableFuture.join()` ném `CompletionException`. Đoạn kiểm thử duyệt chuỗi `getCause()` để in loại **nguyên nhân gốc**.
7. Server chỉ lắng nghe trên **loopback**, cổng ngẫu nhiên (`0` khi bind), và được dừng trong `finally`, tránh phụ thuộc Internet.

**Giới hạn của demo:** đoạn `deferred` gọi `get()` đúng một lần, đọc hết rồi đóng `InputStream`. Khi thiết kế API thực tế, phải quy định rõ ai sở hữu và đóng stream; nếu tạo supplier nhưng không bao giờ gọi `get()` và cũng không đóng luồng, tài nguyên response có thể không được giải phóng đúng cách.

## 7. Ánh xạ theo chuỗi hoàn tất, không phải đọc từng byte riêng lẻ

`BodySubscriber<T>` là một `Flow.Subscriber<List<ByteBuffer>>`. Nó có thể nhận nhiều lượt `onNext` và tạo kết quả thông qua `getBody()`, vốn trả về `CompletionStage<T>`. `mapping` xây dựng một subscriber mới và biến đổi giá trị body của upstream khi giá trị đó sẵn sàng.

Điều này có vài hệ quả:

- **`ofString` hoặc `ofByteArray`:** phải tích lũy toàn bộ body thành `String`/`byte[]`; sau đó mapper mới làm việc trên đối tượng đầy đủ. Phù hợp với dữ liệu nhỏ/vừa và logic xử lý đơn giản.
- **`ofInputStream`:** có thể cung cấp `InputStream` trước khi toàn bộ body đã được nhận; mapping có thể trả `Supplier<T>` sớm, sau đó caller đọc stream khi cần. Đây là mẫu cần hiểu khi tránh block executor.
- **`ofPublisher`:** cung cấp `Flow.Publisher<List<ByteBuffer>>` cho hướng xử lý streaming có kiểm soát; dùng mapping trực tiếp sang một object từ publisher không có nghĩa đã tiêu thụ các byte hay đóng subscription.

Nếu yêu cầu cần **parse gia tăng từng chunk**, kiểm soát backpressure, tải file lớn hoặc xử lý streaming không lưu toàn bộ body, cân nhắc một `BodySubscriber`/`Flow.Subscriber` có thiết kế phù hợp hoặc một stream API, thay vì mặc định dùng `ofString` rồi map kết quả lớn.

### 7.1. Vì sao không nên xử lý nặng ngay trong mapper?

Theo Javadoc của `BodySubscribers.mapping`, mapper được chạy bằng **executor của `HttpClient`**. Do đó có thể làm việc với body kiểu `InputStream`, nhưng một phép đọc/parse **blocking** có thể chiếm thread của executor trong khoảng thời gian khó dự đoán. Tài liệu JDK hiện đại khuyến nghị, khi việc mapping có khả năng block, **trả về `Supplier<U>` để hoãn thao tác blocking tới thread do caller điều khiển**.

Ví dụ minh họa gọn (mẫu thực tế đã được kiểm thử ở mục 6):

```java
BodyHandler<Supplier<String>> handler = info ->
        BodySubscribers.mapping(
                BodySubscribers.ofInputStream(),
                input -> (Supplier<String>) () -> {
                    try (InputStream in = input) {
                        return new String(in.readAllBytes(),
                                StandardCharsets.UTF_8);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });
```

Khi sử dụng:

```java
HttpResponse<Supplier<String>> response = client.send(request, handler);
String text = response.body().get(); // Có thể block tại đây; stream được đóng.
```

Các đoạn trong mục này **không độc lập** nếu tách khỏi class có đủ import và các biến `client`, `request`. Một `Supplier` đóng stream sau khi thực hiện `get()` không mặc nhiên hỗ trợ gọi `get()` nhiều lần; trong ví dụ chỉ gọi **một lần**, và phải có chính sách giải phóng khi không sử dụng supplier.

**Không suy luận mapper chạy trên main thread** hay giả định luôn cùng thread với lời gọi `send`. Tránh mutable shared state không đồng bộ hoặc cập nhật giao diện người dùng trực tiếp từ callback.

### 7.2. Hàm mapping có nên có side effect?

Nên ưu tiên mapper **thuần, dễ kiểm thử**: nhận giá trị body, trả kết quả mới. Không dùng mapper để tự gửi thêm HTTP request, ghi dữ liệu không idempotent hoặc sửa biến toàn cục khi không có phối hợp luồng. Nếu gửi lại request, mỗi response có quá trình nhận body riêng, nên logic có side effect trong mapper có thể chạy nhiều lần.

## 8. Lỗi parse, ngoại lệ và HTTP status code

Khi mapper thất bại:

```java
BodyHandler<Integer> parseInteger = info ->
        BodySubscribers.mapping(
                BodySubscribers.ofString(StandardCharsets.UTF_8),
                Integer::parseInt);
```

Nếu server trả chuỗi không phải số, `Integer.parseInt` ném `NumberFormatException`. Kết quả cuối **không có giá trị body hợp lệ** để trả về; luồng hoàn tất phản hồi có thể thất bại vì mapper.

- Với **`sendAsync`**, `CompletableFuture<HttpResponse<U>>` có thể hoàn thành **exceptionally**; `join()` phát sinh `CompletionException` mang nguyên nhân phù hợp. Mã mục 6 chứng minh nguyên nhân gốc là `NumberFormatException`.
- Với **`send`**, exception từ quá trình nhận body/map có thể được phản ánh qua lỗi thực thi `send`, thường có cause. Không dựa vào việc `send` luôn ném đúng cùng lớp exception gốc mà không có wrapper; kiểm tra và xử lý chuỗi nguyên nhân theo hợp đồng API và triển khai.
- **HTTP status 4xx/5xx** không tự làm mapper thất bại. Nếu trả về body dạng text nhưng mapper trông đợi JSON/number, việc parse lỗi là **lỗi chuyển đổi dữ liệu**, độc lập với status HTTP.

Quy trình xử lý vững chắc:

1. **Kiểm tra status** với `ResponseInfo.statusCode()` trong handler nếu cần chọn cách đọc body, hoặc kiểm tra `HttpResponse.statusCode()` sau gửi nếu handler phù hợp cho cả hai.
2. **Kiểm tra media type** `Content-Type` trước khi parse định dạng nhạy cảm nếu API có khả năng trả nhiều loại response; dùng charset có chủ đích (ví dụ UTF-8).
3. **Giới hạn kích thước** dữ liệu đã nhận trước khi parse để tránh quá tải bộ nhớ; `BodySubscribers.mapping` tự nó **không giới hạn số byte nhận**.
4. **Xử lý lỗi parse** trong application boundary, không lẫn với lỗi DNS, TLS, timeout hay HTTP status.
5. **Đảm bảo giải phóng tài nguyên** của stream/subscription khi mapper dùng đối tượng cần đóng.

### 8.1. Không nhầm mapping với việc xử lý response status

`HttpResponse<Integer>` nghĩa là **body() có kiểu Integer**, không có nghĩa `statusCode()` thay thành Integer hay HTTP chuyển thành kiểu dữ liệu khác. `statusCode()` luôn là mã trạng thái HTTP dạng `int` theo phản hồi thật.

Với API có error body và success body khác schema, hãy xây một kiểu kết quả rõ ràng (ví dụ sealed result nếu đang dùng Java mới hoặc class bình thường trong Java 11) thay vì dùng cùng một mapper chỉ parse success JSON cho mọi status.

## 9. So sánh `BodySubscribers.mapping`, `thenApply` và các `BodyHandlers` có sẵn

| Cách | Biến đổi xảy ra ở đâu? | Kiểu kết quả | Khi nào phù hợp? |
| --- | --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | Body handler tạo subscriber decode thành text | `HttpResponse<String>` | Chỉ cần nguyên chuỗi response |
| `BodySubscribers.mapping(ofString(UTF_8), mapper)` | Tại subscriber xử lý kết quả body | `HttpResponse<U>` | Muốn response.body() sẵn sàng có kiểu U |
| `sendAsync(...).thenApply(resp -> ...)` | Sau khi tương lai của response hoàn tất | `CompletableFuture<V>` | Muốn xử lý cả metadata, status, headers hoặc giữ trách nhiệm biến đổi ở tầng ứng dụng |
| `client.send(...); map(response.body())` | Sau lời gọi gửi đồng bộ | Kiểu do code tự quyết định | Tác vụ đơn giản, dễ tách lỗi mạng với lỗi parse |
| `BodyHandlers.ofFile(path)` / `ofInputStream()` | Xử lý body trực tiếp thành file/stream | `HttpResponse<Path>` / `HttpResponse<InputStream>` | Body lớn hoặc muốn kiểm soát việc đọc/đóng |

Không có phương án “luôn nhanh hơn” cho mọi trường hợp. `mapping` có lợi khi muốn **đóng gói cách đọc và chuyển đổi body thành một BodyHandler có thể tái sử dụng**. `thenApply` linh hoạt hơn nếu logic kết hợp cả `HttpResponse.statusCode()`, request URI, headers hoặc nhiều bước bất đồng bộ.

Ví dụ dùng `thenApply` (mã minh họa, cần có `client` và `request`):

```java
CompletableFuture<Integer> countFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8))
        .thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected status " + response.statusCode());
            }
            return response.body().length();
        });
```

Ở đây `countFuture` chỉ mang giá trị `Integer`, **không còn là `HttpResponse<Integer>`**. Ngược lại, `BodySubscribers.mapping` thường giữ nguyên đối tượng `HttpResponse<U>` chứa cả status và headers cùng body mới.

## 10. Bảo mật, tài nguyên và hiệu năng

- **Body lớn:** `BodySubscribers.ofString(UTF_8)` và `ofByteArray()` tích lũy nội dung. Không dùng chúng để parse body không có giới hạn từ nguồn không đáng tin; yêu cầu giới hạn byte và memory phù hợp. Nếu có proxy/server gateway, giới hạn response cũng nên cấu hình tại đó.
- **Body độc hại hoặc sai định dạng:** parser phải validate schema và dữ liệu. Với JSON nên sử dụng parser được duy trì, không tự tạo code regex/split cho JSON phức tạp.
- **Encoding:** truyền `StandardCharsets.UTF_8` tường minh khi endpoint dùng UTF-8. Không nhầm `String.length()` với số byte trên mạng; không dựa vào default charset của hệ điều hành.
- **Blocking:** theo tài liệu hiện hành, tránh block lâu trên executor của HttpClient. Với `ofInputStream`, chuyển việc parse có thể block sang thread của caller qua `Supplier` hoặc một cơ chế điều phối riêng.
- **Tài nguyên:** `InputStream`, `Stream` hoặc publisher do subscriber trả ra có thể cần đọc hết, đóng hoặc hủy subscription đúng cách; không bỏ mặc body chưa tiêu thụ.
- **Thread safety:** mapper có thể chạy bất đồng bộ; không cập nhật biến dùng chung mà không đồng bộ hóa; không coi `HttpClient` callback là main thread.
- **Bảo mật thông tin:** không in nguyên dữ liệu nhạy cảm, cookies, tokens trong body, headers hoặc exception message vào log production.
- **Kiểu dữ liệu:** nếu parser có thể thất bại, xác định rõ exception policy và error result; không tự động thay mọi lỗi bằng `null` vì sẽ che giấu nguyên nhân.
- **Version tương thích:** `mapping` đã có từ Java 11. Một số phương thức mới hơn của `BodySubscribers` có thể được bổ sung ở các JDK sau; không giả định mọi API trong Javadoc của JDK mới đều chạy được trên `--release 11`.

## 11. Lỗi phổ biến và cách sửa

| Nhầm lẫn/lỗi | Hành vi đúng |
| --- | --- |
| “Truyền `BodySubscriber` trực tiếp cho `HttpClient.send`” | `send` nhận `BodyHandler<T>`. Tạo subscriber trong handler, ví dụ `info -> BodySubscribers.mapping(...)` |
| “`mapping` thay đổi status code hoặc headers” | Chỉ biến đổi body value; status và headers vẫn do server trả |
| “`mapping` luôn xử lý từng chunk byte riêng lẻ” | Mapper nhận **đối tượng T** từ upstream; nếu upstream dùng `ofString` thì cần có String đầy đủ |
| “`ofString` có thể parse JSON tự động” | Nó chỉ decode văn bản theo charset; muốn DTO phải dùng parser phù hợp |
| “Có `String::length` thì kết quả là số byte response” | `String.length()` đếm UTF-16 code units, không phải số byte HTTP |
| “`sendAsync` thất bại khi status 503” | HTTP 503 thường vẫn cho một `HttpResponse` hợp lệ; mapper có thể chạy bình thường |
| “Mapper ném NumberFormatException thì body vẫn được trả” | Nếu map thất bại, thao tác nhận kết quả có thể hoàn thành exceptionally |
| “Mapping InputStream trực tiếp thì không thể block executor” | Mapper chạy trên executor; thao tác đọc stream có thể block. Trả `Supplier` để hoãn xử lý khi thích hợp |
| “Trả Supplier nhưng không gọi/đóng stream cũng an toàn” | Stream có thể giữ tài nguyên. Caller phải tiêu thụ và đóng hoặc hủy đúng quy trình |
| “Mapping tự giới hạn số byte body” | Không; phải có chiến lược giới hạn dữ liệu phù hợp |
| “Dùng `Integer::parseInt` cho bất kỳ error response” | Chọn logic xử lý theo status/media type, không parse nhầm error body |
| “`thenApply` và `mapping` hoàn toàn giống nhau” | `thenApply` chuyển toàn response/future ở tầng ngoài; `mapping` thay kiểu body qua subscriber |
| “Dùng một instance subscriber cho nhiều response” | Subscriber có trạng thái nhận dòng dữ liệu; tạo instance mới khi handler được gọi cho response mới |

## 12. Ôn tập nhanh

**Câu 1:** `BodySubscribers.mapping(BodySubscribers.ofString(UTF_8), String::length)` sinh kiểu nào?  
**Đáp án:** `BodySubscriber<Integer>`. Sau `client.send(request, info -> ...)`, response có thể là `HttpResponse<Integer>`.

**Câu 2:** Body là `"10,20,30"`, mapper sum các phần tử số nguyên. `response.body()` là gì?  
**Đáp án:** `60`, với kiểu `Integer`; HTTP status code vẫn không bị thay đổi.

**Câu 3:** HTTP 503 có bắt buộc làm `BodySubscribers.mapping` ném lỗi không?  
**Đáp án:** Không. Mapping độc lập với status; mapper có thể đọc/chuyển error body. Cần xử lý status theo contract ứng dụng.

**Câu 4:** Vì sao `ofString(UTF_8)` không phù hợp với body cực lớn?  
**Đáp án:** Nó tích lũy toàn bộ byte và giải mã thành một `String` trước khi mapping, có thể gây áp lực bộ nhớ.

**Câu 5:** Nếu mapper cần đọc `InputStream` blocking, nên lưu ý gì?  
**Đáp án:** Mapper dùng executor của HttpClient; nên cân nhắc trả `Supplier<U>` và đọc/đóng stream có kiểm soát ở thread caller.

**Câu 6:** `sendAsync(...).thenApply(resp -> resp.body().length())` khác `mapping(..., String::length)` thế nào?  
**Đáp án:** Cách `thenApply` tạo future của giá trị mới; mapping tạo subscriber để `HttpResponse.body()` mang kiểu đích, giữ metadata response.

**Câu 7:** Khi `Integer.parseInt` trong mapper gặp `"not-an-integer"` thì sao?  
**Đáp án:** Mapper ném `NumberFormatException`, thao tác nhận body thất bại; với `sendAsync(...).join()` trong ví dụ xuất hiện `CompletionException` với nguyên nhân gốc `NumberFormatException`.

## 13. Ghi nhớ

- **`BodySubscribers.mapping(upstream, mapper)`** là API Java 11+ đang được hỗ trợ để **biến đổi kết quả response body từ `T` sang `U`**.
- Dùng trong `BodyHandler`: `info -> BodySubscribers.mapping(BodySubscribers.ofString(UTF_8), mapper)`.
- Khi thành công, **`HttpResponse<U>.body()` mang kiểu đã chuyển**; status code, headers và URI không đổi.
- `ofString` và `ofByteArray` thường gom toàn bộ body; không mặc định phù hợp dữ liệu lớn. `mapping` **không tự parse JSON**, không áp giới hạn kích thước.
- Mapper chạy trên **executor của HttpClient**. Với phép đọc/parse có thể block trên `InputStream`, cân nhắc trả **`Supplier<U>`** để dời việc đó sang thread caller; giải phóng stream có trách nhiệm.
- Phân biệt **HTTP status lỗi**, **lỗi I/O** và **lỗi chuyển đổi của mapper**. Để xử lý cả response metadata, `thenApply` trên future đôi khi thích hợp hơn.

**Tài liệu chính thức:** [Oracle Java 11 — BodySubscribers.mapping](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html#mapping(java.net.http.HttpResponse.BodySubscriber,java.util.function.Function)); [Oracle Java 11 — BodySubscriber và getBody](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html); [Oracle Java 11 — BodyHandler/BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html); [Oracle Java 26 — BodySubscribers.mapping và khuyến cáo tránh blocking executor](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html#mapping(java.net.http.HttpResponse.BodySubscriber,java.util.function.Function)); [JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321).