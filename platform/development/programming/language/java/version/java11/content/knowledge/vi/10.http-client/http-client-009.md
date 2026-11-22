# Tách HTTP transport khỏi ánh xạ dữ liệu nghiệp vụ (Java 11)

Java 11 đưa `java.net.http.HttpClient` vào bộ API Java SE tiêu chuẩn. `HttpClient` giải quyết việc **gửi yêu cầu HTTP và nhận phản hồi**; kết quả có thể là `HttpResponse<String>`, `HttpResponse<byte[]>`, `HttpResponse<InputStream>` hoặc kiểu khác tùy `BodyHandler`. Tuy nhiên, chuỗi JSON hay byte phản hồi **chưa phải đối tượng nghiệp vụ** của ứng dụng.

Khi viết chương trình tích hợp với một API bên ngoài, cần phân biệt các trách nhiệm:

- **HTTP transport:** tạo request, kết nối, TLS, timeout, gửi/nhận HTTP, lấy status, headers, body, xử lý lỗi mạng.
- **HTTP/API adapter (gateway):** hiểu hợp đồng endpoint, quyết định `200` là thành công, `404` có nghĩa gì, các mã lỗi khác được biểu diễn ra sao.
- **Payload decoder và mapper:** đọc định dạng dữ liệu (ví dụ JSON thành DTO), kiểm tra kiểu/trường bắt buộc, chuyển DTO thành **mô hình nghiệp vụ**.
- **Application/domain service:** thực hiện use case bằng đối tượng nghiệp vụ, không phải biết `HttpRequest`, `HttpResponse` hoặc chi tiết HTTP.

Tách các lớp này giúp thay nhà cung cấp API, viết kiểm thử không cần gọi mạng, xử lý lỗi chính xác và bảo vệ nghiệp vụ khỏi thay đổi định dạng transport. Đây là kiến thức **vẫn áp dụng với Java 11 và các JDK được bảo trì hiện nay**; bài không phụ thuộc những API legacy.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích vì sao `HttpResponse<String>` không nên được dùng như kiểu dữ liệu nghiệp vụ.
2. Tổ chức một luồng gọi API qua `HttpTransport` → `ApiGateway` → `PayloadMapper` → `Service`.
3. Tạo adapter Java 11 dùng `HttpClient` và `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)`.
4. Diễn giải `2xx`, `404`, `4xx` và `5xx` theo **hợp đồng endpoint**, thay vì parse mọi body như dữ liệu thành công.
5. Xử lý riêng lỗi mạng, response không hợp lệ, dữ liệu nghiệp vụ thiếu hoặc sai và trường hợp không tìm thấy.
6. Dùng dependency injection để đưa **fake transport** vào kiểm thử; không cần gọi API thật.
7. Biết chỗ đặt timeout, retry, authentication, giới hạn body và các quy tắc ánh xạ JSON/DTO/domain.
8. Áp dụng mô hình tương tự với `sendAsync` mà vẫn giữ ranh giới giữa I/O và nghiệp vụ.

## 2. Nhìn cùng một kết quả qua bốn tầng

Giả sử hệ thống truy vấn người dùng có mã `7`:

```text
PersonService.findSummary(7)
             |
             v
PersonGateway.find(7)          <-- giao diện theo nghiệp vụ
             |
             +--> HttpTransport.get(URI, timeout)
             |           |
             |           +--> HttpClient.send(...)   <-- HTTP transport
             |           +--> HTTP status/headers/body
             |
             +--> API status policy (200 / 404 / 503 ...)
             |
             +--> Payload decoder: text/JSON -> DTO
             |
             +--> PersonMapper: DTO -> Person
             v
Optional<Person>
             |
             v
"Found: 7 / Lan Anh"
```

Đây là **sơ đồ trách nhiệm**, không phải một framework bắt buộc. Với chương trình nhỏ có thể gộp một số lớp vào cùng tệp; với dự án lớn thường nên tách thành package/module. Điều quan trọng là **chiều phụ thuộc**: nghiệp vụ chỉ nhìn thấy các hợp đồng có ý nghĩa với nó.

### Bảng phân công trách nhiệm

| Việc cần làm | Nơi phù hợp | Vì sao |
| --- | --- | --- |
| Tạo `HttpClient`, kết nối HTTPS, quản lý timeout, redirect, proxy | HTTP transport | Đây là cơ chế giao tiếp, không phải quy tắc nghiệp vụ |
| Tạo `HttpRequest`, nhận `HttpResponse` | HTTP transport | Thay cách giao tiếp sẽ không kéo theo thay đổi domain |
| Đọc status `200/404/503` theo hợp đồng của endpoint | API gateway/adapter | Cùng mã `404` có thể mang ý nghĩa khác nhau ở từng endpoint |
| Giải mã JSON thành DTO theo schema | Payload decoder | Là chi tiết định dạng dữ liệu của nhà cung cấp |
| Kiểm tra trường bắt buộc, đổi mã trạng thái sang enum nghiệp vụ | Mapper/anti-corruption layer | Giảm rò rỉ mô hình của đối tác vào domain |
| Tính toán, ra quyết định và hiển thị dữ liệu nghiệp vụ | Service/domain | Không cần biết HTTP status, headers hay thư viện JSON |
| Đặt chính sách retry khi lỗi mạng/`429`/`503` | Gateway/transport policy | Cần biết HTTP, tính idempotent và mức độ an toàn khi gửi lại |
| Viết test trên đối tượng nghiệp vụ | Service + fake gateway | Chạy nhanh, độc lập mạng và có kết quả ổn định |

**Không có quy tắc “mọi 2xx đều giống nhau”:** một endpoint trả `200` kèm dữ liệu, endpoint khác có thể dùng `201`, `202` hoặc `204`. Adapter phải diễn giải chính xác **hợp đồng API đang tích hợp**; ví dụ minh họa bên dưới cố tình yêu cầu `200` cho GET trả dữ liệu.

## 3. Vì sao không nên trộn HTTP với mapping?

Đoạn dưới đây là **phản ví dụ**, chỉ minh họa cách tổ chức thiếu ranh giới (không phải chương trình độc lập):

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

if (response.statusCode() == 200) {
    // Parse response.body() rồi xây dữ liệu nghiệp vụ trực tiếp tại đây.
    // Sau đó tiếp tục xử lý use case ngay trong cùng phương thức.
}
```

Khi code vừa gọi HTTP vừa parse payload vừa áp quy tắc nghiệp vụ, ba loại thay đổi cùng tác động một phương thức:

- Đổi TLS, timeout hoặc cơ chế xác thực có thể buộc sửa logic nghiệp vụ.
- Đổi JSON field tên `full_name` thành `displayName` có thể ảnh hưởng cả tầng gọi HTTP.
- Muốn test quy tắc nghiệp vụ phải kết nối API thật hoặc mock nhiều chi tiết không liên quan.
- Lỗi `500` có thể vô tình bị parse như một DTO thành công, gây ngoại lệ khó hiểu.

Một điểm rất dễ nhầm trong Java 11: **`HttpResponse.BodyHandlers.ofString()` chỉ chuyển byte phản hồi thành `String`**, không chuyển JSON thành `Person` và không tự xác thực schema nghiệp vụ. Các `BodyHandler` chuẩn không tự từ chối body theo HTTP status; code gọi cần kiểm tra `response.statusCode()`. Tương tự, `HttpClient.send()` có thể trả về một `HttpResponse` mang mã `404` hoặc `503` như một kết quả HTTP bình thường; các mã đó **không tự biến thành `IOException`**.

## 4. Ví dụ Java 11 hoàn chỉnh: transport, gateway, mapper và service

Để ví dụ chạy được **không cần truy cập mạng**, chương trình dùng một fake transport cung cấp phản hồi cố định. Nó cũng chứa adapter **`JdkHttpTransport` thực sự dùng `java.net.http.HttpClient`** để bạn thấy vị trí cắm kết nối thật. Payload cố ý có dạng **`id|name`** cho ngắn gọn và có thể kiểm tra bằng mắt: đây **không phải JSON parser**, không phải giao thức khuyên dùng cho production.

Tạo tệp **`HttpLayersDemo.java`**, chứa toàn bộ mã sau:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class HttpLayersDemo {

    // 1. Hợp đồng vận chuyển: không biết Person hay nghiệp vụ.
    interface HttpTransport {
        RawResponse get(URI uri, Duration timeout)
                throws IOException, InterruptedException;
    }

    static final class RawResponse {
        final int statusCode;
        final String body;

        RawResponse(int statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }
    }

    // 2. HTTP transport thật, chỉ dùng API tiêu chuẩn Java 11.
    static final class JdkHttpTransport implements HttpTransport {
        private final HttpClient client;

        JdkHttpTransport(HttpClient client) {
            this.client = Objects.requireNonNull(client, "client");
        }

        @Override
        public RawResponse get(URI uri, Duration timeout)
                throws IOException, InterruptedException {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(timeout)
                    .header("Accept", "text/plain")
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            return new RawResponse(
                    response.statusCode(), response.body());
        }
    }

    // 3. Fake cho test: không có HTTP server và không cần mạng.
    static final class FakeHttpTransport implements HttpTransport {
        private final Map<String, RawResponse> responses =
                new HashMap<>();

        void reply(String path, int statusCode, String body) {
            responses.put(path, new RawResponse(statusCode, body));
        }

        @Override
        public RawResponse get(URI uri, Duration timeout)
                throws IOException {
            RawResponse response = responses.get(uri.getPath());
            if (response == null) {
                throw new IOException("No fake for " + uri.getPath());
            }
            return response;
        }
    }

    // 4. Domain model: hoàn toàn không chứa HttpResponse.
    static final class Person {
        final long id;
        final String name;

        Person(long id, String name) {
            this.id = id;
            this.name = name;
        }
    }

    // 5. Mapping payload theo hợp đồng minh họa "id|name".
    static final class PersonTextMapper {
        Person map(String payload) {
            if (payload == null) {
                throw new IllegalArgumentException("Invalid person payload");
            }

            int separator = payload.indexOf('|');
            if (separator <= 0
                    || separator == payload.length() - 1
                    || payload.indexOf('|', separator + 1) >= 0) {
                throw new IllegalArgumentException("Invalid person payload");
            }

            long id;
            try {
                id = Long.parseLong(
                        payload.substring(0, separator).strip());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Invalid person payload", ex);
            }

            String name = payload.substring(separator + 1).strip();
            if (id <= 0 || name.isBlank()) {
                throw new IllegalArgumentException("Invalid person payload");
            }

            return new Person(id, name);
        }
    }

    // 6. Gateway giải thích status + hợp đồng payload.
    interface PersonGateway {
        Optional<Person> find(long id);
    }

    static class GatewayException extends RuntimeException {
        GatewayException(String message) {
            super(message);
        }

        GatewayException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class RemoteStatusException extends GatewayException {
        final int statusCode;

        RemoteStatusException(int statusCode) {
            super("Remote HTTP status: " + statusCode);
            this.statusCode = statusCode;
        }
    }

    static final class RemotePersonGateway implements PersonGateway {
        private final HttpTransport transport;
        private final URI baseUri;
        private final PersonTextMapper mapper;

        RemotePersonGateway(HttpTransport transport, URI baseUri,
                            PersonTextMapper mapper) {
            this.transport = Objects.requireNonNull(
                    transport, "transport");
            this.baseUri = Objects.requireNonNull(baseUri, "baseUri");
            this.mapper = Objects.requireNonNull(mapper, "mapper");
        }

        @Override
        public Optional<Person> find(long id) {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }

            URI uri = baseUri.resolve("persons/" + id);
            RawResponse response;

            try {
                response = transport.get(uri, Duration.ofSeconds(3));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new GatewayException("Request interrupted", ex);
            } catch (IOException ex) {
                throw new GatewayException("Transport failed", ex);
            }

            if (response.statusCode == 404) {
                return Optional.empty();
            }
            if (response.statusCode != 200) {
                throw new RemoteStatusException(response.statusCode);
            }

            final Person person;
            try {
                person = mapper.map(response.body);
            } catch (IllegalArgumentException ex) {
                throw new GatewayException(
                        "Invalid person payload", ex);
            }

            if (person.id != id) {
                throw new GatewayException("Response id mismatch");
            }

            return Optional.of(person);
        }
    }

    // 7. Service chỉ phụ thuộc vào giao diện nghiệp vụ.
    static final class PersonService {
        private final PersonGateway gateway;

        PersonService(PersonGateway gateway) {
            this.gateway = gateway;
        }

        String summary(long id) {
            return gateway.find(id)
                    .map(p -> "Found: " + p.id + " / " + p.name)
                    .orElse("Not found");
        }
    }

    public static void main(String[] args) {
        FakeHttpTransport fake = new FakeHttpTransport();
        fake.reply("/persons/7", 200, "7|Lan Anh");
        fake.reply("/persons/8", 404, "Not found");
        fake.reply("/persons/9", 503, "Temporarily unavailable");
        fake.reply("/persons/10", 200, "broken payload");
        fake.reply("/persons/11", 200, "999|Wrong person");

        PersonGateway gateway = new RemotePersonGateway(
                fake,
                URI.create("https://api.example.invalid/"),
                new PersonTextMapper());

        PersonService service = new PersonService(gateway);

        System.out.println(service.summary(7));
        System.out.println(service.summary(8));

        try {
            service.summary(9);
        } catch (RemoteStatusException ex) {
            System.out.println("HTTP status: " + ex.statusCode);
        }

        try {
            service.summary(10);
        } catch (GatewayException ex) {
            System.out.println("Payload error: " + ex.getMessage());
        }

        try {
            service.summary(11);
        } catch (GatewayException ex) {
            System.out.println("Contract error: " + ex.getMessage());
        }
    }
}
```

### Biên dịch và chạy

Mở terminal tại thư mục chứa tệp `HttpLayersDemo.java`. Dùng JDK đang được nhà cung cấp hỗ trợ, với compiler hỗ trợ mức Java 11:

```sh
javac --release 11 -encoding UTF-8 HttpLayersDemo.java
java HttpLayersDemo
```

**Stdout mong đợi:**

```text
Found: 7 / Lan Anh
Not found
HTTP status: 503
Payload error: Invalid person payload
Contract error: Response id mismatch
```

Không có request HTTP thật trong `main` vì `FakeHttpTransport` được truyền vào gateway. Tên miền `api.example.invalid` chỉ là tên minh họa để tạo URI; fake dùng `uri.getPath()` để tìm dữ liệu. Vì thế ví dụ chạy **offline** và cho kết quả cố định khi mã thực thi đúng.

### Từng lớp chịu trách nhiệm gì?

**`JdkHttpTransport`** tạo `HttpRequest`, dùng `HttpClient.send` và `BodyHandlers.ofString(UTF_8)`, rồi trả `RawResponse`. Nó không biết `Person` là gì, không truy cập database và không áp quy tắc “người dùng không tồn tại”.

**`RawResponse`** là kiểu dữ liệu trung gian rất nhỏ gồm **status** và **body**. Trong hệ thống thật, có thể thêm headers cần thiết, request ID hoặc metadata đã được lọc. Tránh bê nguyên cả mô hình domain vào transport.

**`PersonTextMapper`** chỉ biến payload `"7|Lan Anh"` thành `Person(7, "Lan Anh")`. Hàm này độc lập kết nối mạng và có thể được kiểm thử với một chuỗi bất kỳ. Với dữ liệu JSON thật, thay mapper text bằng **JSON decoder + DTO/domain mapper**.

**`RemotePersonGateway`** biết endpoint `persons/{id}` và hợp đồng: `200` có dữ liệu; `404` nghĩa là không tìm thấy; status khác gây `RemoteStatusException`; body lỗi hoặc ID không khớp cũng được báo lỗi. Gateway **chặn chi tiết HTTP** trước khi service nhận `Optional<Person>`.

**`PersonService`** chỉ làm việc với `PersonGateway`. Khi đổi HTTP sang một API khác, hoặc thay fake bằng transport thật, lớp service **không cần sửa logic**. Phần hiển thị `summary` là minh họa use case nhỏ; ứng dụng lớn có thể trả view model thay vì string.

### Chuyển từ fake sang transport thật

Đoạn sau là **ví dụ khởi tạo bên trong chương trình cùng phạm vi truy cập các nested class ở trên**, không phải một chương trình độc lập:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpTransport http = new JdkHttpTransport(client);

PersonGateway remote = new RemotePersonGateway(
        http,
        URI.create("https://partner.example/"),
        new PersonTextMapper());

PersonService service = new PersonService(remote);
```

Trong code production thực tế, thay `https://partner.example/` bằng endpoint **được phép truy cập** và sử dụng đúng định dạng payload của nhà cung cấp. Không chạy đoạn này với domain minh họa rồi kỳ vọng có dữ liệu thật.

**Quan trọng:** việc đổi sang transport thật chỉ yêu cầu thay object được inject. `PersonTextMapper` và `PersonService` không cần biết request được gửi qua HTTP/1.1 hay HTTP/2, có proxy hay không, hoặc có TLS thế nào.

## 5. JSON, DTO và domain: tách tiếp một ranh giới

Các dịch vụ HTTP thực tế thường trả JSON:

```json
{
  "id": 7,
  "full_name": "Lan Anh",
  "account_status": "ACTIVE"
}
```

Đây là **ví dụ payload API**, không phải đầu vào của `PersonTextMapper` ở phần 4. Trong Java 11, `HttpClient` **không tích hợp bộ ánh xạ JSON thành POJO/domain object**. Chọn một thư viện JSON hiện được bảo trì và tương thích JDK của dự án (ví dụ Jackson), hoặc một cơ chế decode tương đương đã được framework hỗ trợ.

Các bước nên được phân định:

```text
HTTP bytes
   |
   | Content-Type / charset (transport, adapter)
   v
JSON text
   |
   | JSON decoder (kiểm tra cú pháp JSON)
   v
PersonDto { id, full_name, account_status }
   |
   | Mapper (đổi tên, kiểu, validation, chính sách)
   v
Person { id, name, status }
   |
   v
Business use case
```

Một DTO phản ánh **hợp đồng JSON của đối tác**. Domain object phản ánh **ngữ nghĩa nội bộ** của sản phẩm. Không ép tên trường và enum của bên ngoài thành tên miền nghiệp vụ trong mọi tầng.

Ví dụ chính sách ánh xạ:

| Dữ liệu từ API | DTO/adapter | Dữ liệu nghiệp vụ |
| --- | --- | --- |
| `id: 7` | `Long id` | `PersonId` hoặc `long` hợp lệ, dương |
| `full_name: "Lan Anh"` | `String fullName` | `Person.name`, đã kiểm tra không rỗng |
| `account_status: "ACTIVE"` | `String statusCode` | Enum nghiệp vụ `ACTIVE` khi giá trị được công nhận |
| `account_status: "SUSPENDED"` | Giá trị mới bên ngoài | Chính sách rõ: ánh xạ trạng thái, đánh dấu unknown hoặc từ chối |
| Trường bắt buộc thiếu/sai kiểu | Decoder/schema validation | Lỗi hợp đồng tích hợp; **không** tự gán bừa một giá trị có ý nghĩa nghiệp vụ |

Trong một thiết kế gọn, có thể định nghĩa:

```java
interface PayloadDecoder<T> {
    T decode(String payload);
}

interface DomainMapper<S, T> {
    T map(S source);
}
```

Đây là **các interface minh họa**, không phải chương trình hoàn chỉnh. Một implementation có thể dùng JSON decoder để tạo DTO, sau đó dùng mapper thuần Java để tạo domain object. Các lớp trên không cần import `HttpClient`.

**Không nên parse JSON bằng `split(",")`, regex tự chế hoặc thao tác substring theo tên trường.** JSON có escape, dấu nháy, mảng, object lồng nhau, `null` và biến thể kiểu dữ liệu; parser chuẩn có kiểm tra hợp đồng là cách phù hợp. Nếu payload thành công không hợp lệ, báo lỗi **mapping/contract** rõ ràng thay vì coi đó là lỗi socket.

## 6. Diễn giải HTTP status trước khi chuyển thành dữ liệu nghiệp vụ

Một số ví dụ về chính sách:

| HTTP status / sự kiện | Ý nghĩa HTTP | Quyết định tại gateway |
| --- | --- | --- |
| `200 OK` | Request thành công | Theo hợp đồng GET ví dụ, decode body rồi map thành domain |
| `201 Created` | Tài nguyên được tạo | Với endpoint tạo mới, có thể đọc Location/body theo hợp đồng |
| `202 Accepted` | Request đã được nhận để xử lý tiếp | Có thể trả trạng thái “đang xử lý”; không tự coi nghiệp vụ đã hoàn tất |
| `204 No Content` | Thành công nhưng không có body | Không cố parse body thành DTO; xử lý theo hợp đồng |
| `400 Bad Request` | Đầu vào không hợp lệ ở giao thức/API | Trả lỗi tích hợp/validation tương ứng, không map body lỗi thành domain thành công |
| `401 Unauthorized`, `403 Forbidden` | Xác thực hoặc phân quyền không đủ | Xử lý theo chính sách bảo mật/đăng nhập, tránh tiết lộ token |
| `404 Not Found` | Không tìm thấy tài nguyên theo URL | Có thể thành `Optional.empty()` **nếu hợp đồng nghiệp vụ quy định như vậy** |
| `409 Conflict` | Trạng thái tài nguyên xung đột | Có thể cần lỗi nghiệp vụ riêng theo operation |
| `429 Too Many Requests` | Bị giới hạn tốc độ | Kiểm tra `Retry-After`, giới hạn retry/backoff hợp lý |
| `500`/`502`/`503`/`504` | Lỗi phía server/gateway | Báo lỗi tích hợp; có thể retry có kiểm soát khi an toàn |
| `IOException` | Lỗi gửi/nhận HTTP hoặc kết nối | Phân biệt với status HTTP; có thể không có response nào |
| `InterruptedException` | Luồng thực hiện bị ngắt lúc gửi đồng bộ | Khôi phục interrupt flag khi bao ngoại lệ, không âm thầm nuốt |
| Decode/mapping failure | HTTP đã trả body nhưng nội dung sai hợp đồng | Lỗi dữ liệu/đối tác, không đánh đồng với timeout |

**`HttpClient.send()` không ném `IOException` chỉ vì server trả `404`/`503`.** Gateway phải tự kiểm tra `statusCode()`. Tương tự, việc có `200` không có nghĩa payload đúng schema hay trường nghiệp vụ hợp lệ.

Trong ví dụ, `RemotePersonGateway` đưa `404` về `Optional.empty()`. Một endpoint thanh toán có thể coi `404` là lỗi nghiêm trọng. Không sao chép quy tắc `404 -> empty` sang mọi nghiệp vụ.

## 7. Biên giới exception và cancellation

Transport đồng bộ trong Java 11 có chữ ký tổng quát:

```java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> bodyHandler)
        throws IOException, InterruptedException;
```

Khi xử lý:

- `IOException` cho biết lỗi I/O, có thể xảy ra trước khi nhận response hoặc trong quá trình đọc body. Retry (nếu có) cần dựa trên ngữ cảnh operation.
- `InterruptedException` báo luồng bị ngắt. Nếu chuyển nó thành ngoại lệ khác ở gateway, cách phổ biến là gọi `Thread.currentThread().interrupt()` trước khi propagate, như ví dụ, để bảo toàn tín hiệu gián đoạn cho caller.
- `IllegalArgumentException` từ mapper thường có nghĩa **payload sai**, không phải lỗi mạng. Tránh trả về một `Person` rỗng để che lỗi dữ liệu.
- Với giao diện nghiệp vụ, có thể dùng một kiểu lỗi riêng như `GatewayException` để không lộ từng loại ngoại lệ của thư viện HTTP. Tuy nhiên, nên giữ `cause` để logs/diagnostics có đủ nguyên nhân kỹ thuật.

Chỉ tầng tích hợp nên biết `HttpResponse<?>` hay mã HTTP cụ thể. Business service có thể xử lý một **result** có ý nghĩa nghiệp vụ (`found`, `not found`, `unavailable`) hoặc nhận một exception đã được phân loại. Khi yêu cầu xử lý lỗi chi tiết hơn, thiết kế một kiểu kết quả tường minh thay vì lạm dụng `Optional.empty()` để che tất cả lỗi.

## 8. Bất đồng bộ `sendAsync` vẫn giữ ranh giới tương tự

Java 11 hỗ trợ:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
```

Đây là **đoạn mã minh họa bên trong phương thức** đã có `HttpClient client` và `HttpRequest request`, với import `java.util.concurrent.CompletableFuture` và `java.nio.charset.StandardCharsets`.

`sendAsync` trả về `CompletableFuture`, cho phép compose các bước. Nhưng **mapping vẫn nên nằm sau transport**, ví dụ trong một adapter:

```java
CompletableFuture<Person> personFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
              .thenApply(response -> {
                  if (response.statusCode() != 200) {
                      throw new RemoteStatusException(
                              response.statusCode());
                  }
                  return mapper.map(response.body());
              });
```

Đây là **đoạn minh họa trong lớp adapter** nơi `client`, `request`, `mapper` và `RemoteStatusException` đã được khai báo; nó không thay thế nguyên vẹn chương trình `HttpLayersDemo.java`. Khi dùng triển khai đầy đủ, cần thêm chính sách cho `404`, lỗi JSON, interruption/cancellation và executor phù hợp.

**Điểm quan trọng:**

1. `sendAsync` vẫn làm HTTP; `thenApply` nhận kết quả và gọi bước diễn giải/map sau đó.
2. Lỗi HTTP status do adapter ném trong `thenApply` làm future hoàn tất **exceptionally**; lỗi transport có thể cũng khiến future thất bại.
3. `CompletableFuture.join()` có thể ném `CompletionException` bọc nguyên nhân; code tiêu thụ nên unwrap/log đúng nguyên nhân.
4. Mapping CPU nặng không nên thực hiện tùy tiện trên thread xử lý HTTP; có thể dùng `thenApplyAsync(..., executor)` với executor có giới hạn và được quản lý.
5. Cancellation của future không phải giao kèo chắc chắn rằng mọi hoạt động server đã được hoàn tác. Không tự retry request có tác dụng phụ khi chưa xác định tính idempotent.

Mỗi tầng vẫn có thể được test độc lập: fake một future phản hồi `200`, `404`, `503`, future lỗi mạng hoặc lỗi parsing; kiểm tra domain result mà không yêu cầu mở kết nối đến đối tác.

## 9. Thiết kế cho ứng dụng thật: bảo mật, tài nguyên và hiệu năng

### Tái sử dụng `HttpClient`

Một `HttpClient` đã build là **immutable** và có thể gửi nhiều request, chia sẻ cấu hình và tài nguyên kết nối. Nên tạo và quản lý một instance theo vòng đời phù hợp (ví dụ thông qua dependency injection) thay vì tạo client mới cho từng entity hoặc gọi mới. `HttpRequest` có thể được tạo riêng cho từng operation.

### Timeout không phải một giá trị duy nhất

- `HttpClient.Builder.connectTimeout(Duration)` là timeout **thiết lập kết nối** khi cần tạo connection.
- `HttpRequest.Builder.timeout(Duration)` là timeout cho request; các chi tiết lỗi/giới hạn phụ thuộc cách gọi và JDK.
- Ứng dụng còn có thể cần **deadline tổng thể**, timeout ở tầng server/proxy, giới hạn số kết nối đồng thời và chính sách hủy.
- Một timeout 3 giây ở ví dụ chỉ là giá trị minh họa; đặt theo SLA và yêu cầu sản phẩm.

### Kiểm soát kích thước và dữ liệu body

`BodyHandlers.ofString(UTF_8)` **tích lũy toàn bộ body thành `String`**. Phù hợp với response nhỏ, được kiểm soát; không mặc định an toàn cho response rất lớn hoặc không tin cậy. Với body lớn, cân nhắc `BodyHandlers.ofInputStream()`, xử lý stream theo chunk với giới hạn byte, rồi đóng stream đúng cách. Khi cần đo giới hạn payload, **đếm byte thực**, không dùng `String.length()` làm giới hạn kích thước mạng.

HTTP `Content-Type` và charset là hợp đồng cần được kiểm tra. Ví dụ ở phần 4 cố định UTF-8 để có kết quả xác định; với API khác, decoder phải phù hợp đặc tả. Với JSON, dùng bộ giải mã đúng chuẩn và kiểm tra schema. Không log nguyên response nếu chứa thông tin nhạy cảm.

### HTTPS, xác thực và URL đầu vào

- Với hệ thống production, ưu tiên HTTPS và endpoint/host có thể tin cậy; không cho người dùng tùy ý điều khiển URI nội bộ nếu chưa có biện pháp ngăn SSRF.
- Header `Authorization` hay cookie chứa bí mật thuộc adapter/configuration, không chuyển vào domain object hoặc log.
- Xem xét chính sách redirect; ví dụ dùng `Redirect.NEVER` để quyết định tường minh trước khi chuyển host, header nhạy cảm hoặc phương thức.
- Giới hạn số request đồng thời, thực thi backpressure và áp circuit breaker nếu nhu cầu thực tế yêu cầu.

### Retry đúng chỗ

Retry là chính sách của **tầng tích hợp**, không phải mapper thuần dữ liệu:

- Với `GET` idempotent, một số lỗi mạng hoặc `503` có thể thử lại có giới hạn, exponential backoff và jitter.
- Với `429`, cân nhắc `Retry-After` và quota của đối tác.
- Với `POST` tạo đơn hàng/thanh toán, không tự gửi lại nếu chưa rõ operation có thể lặp an toàn hay có idempotency key được endpoint hỗ trợ.
- Luôn giới hạn tổng số lượt thử, thời hạn tổng thể và số request đồng thời; báo lỗi cuối cùng có nguyên nhân rõ ràng.

**Không viết retry bên trong `PersonTextMapper.map`.** Mapper có thể chạy thuần CPU và được test bằng dữ liệu cố định; nó không nên biết mạng, timeout hay HTTP status.

## 10. Test theo trách nhiệm, không bắt mọi test gọi mạng

Ví dụ `HttpLayersDemo.java` đã tự kiểm thử năm đường đi:

| Đường đi | Fake response | Kết quả quan sát |
| --- | --- | --- |
| Thành công | `200` + `7|Lan Anh` | `Found: 7 / Lan Anh` |
| Không tìm thấy | `404` | `Not found` |
| Server chưa sẵn sàng | `503` | `HTTP status: 503` |
| Payload sai định dạng | `200` + `broken payload` | `Payload error: Invalid person payload` |
| API trả sai ID | `200` + `999|Wrong person` | `Contract error: Response id mismatch` |

Ngoài năm đường đi này, dự án thật nên có các lớp kiểm thử sau:

1. **Mapper tests (không mạng):** đầu vào hợp lệ; thiếu ID; sai kiểu; thiếu tên; `null`; giá trị enum lạ; kiểm tra quy tắc domain. Với JSON, test decoder theo đúng schema và escape Unicode.
2. **Gateway tests với fake transport:** `200`, `204`, `404`, `429`, `503`, lỗi I/O, timeout, interrupted, response body hỏng; xác nhận lỗi được phân loại đúng.
3. **Service tests với fake `PersonGateway`:** quy tắc nghiệp vụ, kết quả, không cần import `HttpClient`.
4. **HTTP adapter integration tests:** dựng local test server hoặc mock HTTP server để kiểm tra URI, HTTP method, headers, redirect policy, charset, body handler, timeout và request thực sự được gửi. Các test này kiểm tra transport, không dùng API production.
5. **Contract tests với đối tác:** kiểm tra schema, version, field rename và mã lỗi. Dùng môi trường kiểm thử hoặc fixture được cập nhật; không phụ thuộc mặc định vào mạng công cộng trong mỗi unit test.

Một fake transport không chứng minh TLS, DNS, HTTP/2 hay timeout ngoài đời đã hoạt động. Ngược lại, một integration test HTTP không thay thế các mapper test cho toàn bộ trường hợp dữ liệu nghiệp vụ. Mỗi loại test xác nhận đúng trách nhiệm của nó.

## 11. Cấu trúc package gợi ý khi tách khỏi một tệp

Bài thực hành gộp mọi lớp trong `HttpLayersDemo.java` để có thể biên dịch ngay. Ở ứng dụng thực tế, có thể tổ chức:

```text
com.example.app
├── domain
│   ├── Person.java
│   └── PersonGateway.java        # Port mà nghiệp vụ sử dụng
├── application
│   └── PersonService.java
└── infrastructure
    ├── http
    │   ├── HttpTransport.java
    │   ├── JdkHttpTransport.java
    │   └── RawResponse.java
    ├── partner
    │   ├── RemotePersonGateway.java
    │   ├── PersonResponseDto.java
    │   └── PersonMapper.java
    └── config
        └── HttpClientConfig.java
```

Đây là **cấu trúc tham khảo**, không phải quy tắc bắt buộc của Java. Với một tổ chức dùng Spring, Micronaut, Quarkus hoặc framework khác, cơ chế dependency injection và DTO mapping có thể khác nhưng ý tưởng vẫn giữ nguyên: domain không phụ thuộc `java.net.http` hoặc mô hình HTTP cụ thể của đối tác.

Các interface nên được tạo khi có **ranh giới cần thay thế/kiểm thử**, tránh sinh quá nhiều wrapper nếu một ứng dụng nhỏ không cần. Ranh giới chính cần bảo toàn là **HTTP mechanics**, **API contract**, **payload interpretation**, **domain behavior**.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả trực tiếp `HttpResponse<String>` từ service nghiệp vụ | Domain phải biết HTTP, khó thay API và test | Gateway trả `Person`, `Optional<Person>` hoặc kiểu kết quả nghiệp vụ |
| Nhầm `BodyHandlers.ofString()` là JSON mapper | Chỉ nhận `String`, schema chưa được kiểm tra | Dùng JSON decoder riêng, sau đó map DTO sang domain |
| Parse body trước khi kiểm tra HTTP status | Body lỗi `4xx/5xx` bị xử lý như dữ liệu thành công | Kiểm tra status theo hợp đồng endpoint |
| Đưa `statusCode == 404` vào domain model | Rò rỉ chi tiết transport | Gateway đổi thành “không tìm thấy” nếu phù hợp nghiệp vụ |
| Tất cả lỗi đều thành `Optional.empty()` | Che lỗi mạng, lỗi API và dữ liệu không hợp lệ | Phân biệt not-found, unavailable, invalid payload, authorization failure |
| Swallow `InterruptedException` | Mất tín hiệu hủy/chặn, khó kiểm soát tác vụ | Khôi phục interrupt flag khi chuyển ngoại lệ |
| Mapper tự thực hiện HTTP call | Mapper khó test, vi phạm trách nhiệm | Giữ mapper là hàm thuần nhận payload/DTO |
| Test luôn gọi API thật | Chậm, không ổn định, phụ thuộc tài khoản và mạng | Inject fake transport/gateway cho unit test |
| Tạo `HttpClient` mới cho mỗi request | Tốn tài nguyên và khó quản lý cấu hình | Tái sử dụng instance được quản lý |
| Không giới hạn response body hoặc timeout | Có thể treo tác vụ, dùng nhiều RAM | Timeout/deadline, BodyHandler và giới hạn kích thước phù hợp |
| Retry mọi lỗi theo cùng quy tắc | Có thể tạo dữ liệu trùng hoặc làm quá tải đối tác | Retry dựa trên method, status, idempotency và ngân sách thời gian |
| Đưa token/response nhạy cảm vào log | Lộ thông tin | Redact secrets, log metadata cần thiết và áp quyền truy cập |
| Mapper gán giá trị mặc định bừa cho field thiếu | Sai ý nghĩa nghiệp vụ mà không phát hiện contract drift | Validation, enum unknown policy, contract tests |

## 13. Bài tập

**Bài 1 — Chỉ ra ranh giới.** Với chương trình ở phần 4, nêu rõ lớp nào biết `HttpClient`, lớp nào biết HTTP status, lớp nào biết định dạng `id|name`, lớp nào biết đối tượng `Person`. Giải thích vì sao `PersonService` không cần biết URL.

**Bài 2 — Mở rộng fake response.** Thêm:
- `200` với `"0|Invalid"` → mapper phải từ chối ID không hợp lệ;
- `200` với `"7|   "` → mapper phải từ chối tên rỗng;
- `401` → gateway phải báo lỗi tích hợp có phân loại;
- một đường dẫn chưa cấu hình fake → `IOException` phải được gateway bọc thành `GatewayException("Transport failed", cause)`.

**Bài 3 — Bổ sung JSON DTO.** Giả sử API trả `{"id":7,"full_name":"Lan Anh"}`. Viết DTO tương ứng, dùng JSON parser hiện đang được dự án bảo trì để decode rồi map sang `Person`. Không sửa `JdkHttpTransport` để chứa business field; chỉ thay decoder/mapper và hợp đồng gateway nếu cần.

**Bài 4 — Chính sách `204`.** Nếu một endpoint trả `204 No Content`, hãy quyết định ý nghĩa nghiệp vụ trong giao diện gateway. Không gọi `mapper.map("")` rồi hy vọng kết quả hợp lệ; mã status này phải có hợp đồng riêng.

**Bài 5 — Test lỗi và retry.** Thiết kế fake trả `503` hai lần, `200` ở lần thứ ba; nêu chỗ đặt retry, số lần tối đa và backoff. Giải thích vì sao không mặc định áp retry này cho lệnh thanh toán POST.

**Bài 6 — Đồng bộ và bất đồng bộ.** Chỉ ra vì sao `client.send(...)` ném `IOException/InterruptedException`, còn `client.sendAsync(...)` phản ánh phần lớn lỗi ở trạng thái hoàn tất exceptionally của `CompletableFuture`. Vẫn giữ map status và dữ liệu tại tầng gateway ở cả hai trường hợp.

### Checklist hoàn thành

- [ ] Phân biệt được `HttpClient`/`HttpResponse` và dữ liệu nghiệp vụ.
- [ ] Hiểu `BodyHandlers.ofString` chỉ xử lý body thành chuỗi, không tự parse JSON/domain.
- [ ] Chạy được `HttpLayersDemo.java` bằng `javac --release 11` và đối chiếu 5 dòng stdout.
- [ ] Giải thích được vì sao `404` không tự ném `IOException` và phải được gateway diễn giải.
- [ ] Dùng fake transport để test mapper, gateway và service mà không gọi mạng.
- [ ] Phân biệt lỗi network, status lỗi, payload lỗi và mismatch nghiệp vụ.
- [ ] Biết nơi đặt timeout, retry, authentication và giới hạn response.
- [ ] Có thể thay transport HTTP mà không cần sửa domain/service.

## 14. Tài liệu tham khảo còn áp dụng

1. [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): tạo client, `send`, `sendAsync`, tái sử dụng và các tùy chọn transport.
2. [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): URI, method, headers, timeout và cách tạo request.
3. [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode`, headers, body và kiểu `HttpResponse<T>`.
4. [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofInputStream`, `ofByteArray` và hợp đồng không tự diễn giải status.
5. [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): ghép các bước bất đồng bộ và xử lý hoàn tất lỗi.
6. [Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): tham chiếu API trên một dòng JDK LTS hiện đại.

**Kết luận áp dụng:** `HttpClient` là công cụ giao tiếp HTTP, còn **mapping payload thành dữ liệu nghiệp vụ** là trách nhiệm của decoder/mapper trong tầng tích hợp. Đưa ranh giới này vào thiết kế, rồi dùng gateway để diễn giải status và che các chi tiết transport trước domain, sẽ giúp code dễ thay đổi, kiểm thử được mà không cần mạng và hạn chế lỗi do dữ liệu bên ngoài thay đổi.