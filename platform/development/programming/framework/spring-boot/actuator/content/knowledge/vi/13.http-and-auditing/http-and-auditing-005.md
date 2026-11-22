# Kiểm soát dung lượng lưu, header nhạy cảm và dữ liệu cá nhân trong HTTP exchange

## 1. Chọn dữ liệu cần quan sát trước khi chọn nơi lưu

Một bản ghi trao đổi HTTP giúp trả lời các câu hỏi như: đường dẫn nào vừa được gọi, phản hồi có lỗi không và quá trình xử lý mất bao lâu. Nhưng yêu cầu HTTP cũng có thể mang token, cookie phiên, email, địa chỉ IP hoặc mã định danh khách hàng. Thu thập nhiều hơn không tự làm việc chẩn đoán tốt hơn nếu thông tin ấy không phục vụ câu hỏi đang điều tra.

Với `HttpExchangeRepository`, cần kiểm soát ba vấn đề riêng:

| Vấn đề | Câu hỏi thiết kế |
| --- | --- |
| Dung lượng | Giữ tối đa bao nhiêu bản ghi và mỗi bản ghi chứa bao nhiêu dữ liệu? |
| Nội dung | Trường nào cần giữ, trường nào cần loại bỏ hoặc thay bằng mô tả khái quát? |
| Quyền đọc và vòng đời | Ai được đọc, đọc ở đâu, dữ liệu tồn tại tới khi nào? |

`InMemoryHttpExchangeRepository` giữ dữ liệu trong bộ nhớ và mặc định lưu 100 trao đổi gần nhất. Spring Boot khuyến nghị dùng lớp này cho môi trường phát triển. Đây là giới hạn số bản ghi của một repository, không phải cam kết rằng mọi dữ liệu bên trong đều phù hợp để lưu hoặc chia sẻ. [Ghi nhận HTTP exchanges trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

Bài này dùng Spring Boot 3.3 và JDK 21 để minh họa cách giảm dữ liệu ngay trước khi lưu. Các token, email và địa chỉ trong mã là dữ liệu giả dành cho thí nghiệm.

## 2. Kiểm soát dung lượng theo cả số lượng và kích thước

Đối với repository bộ nhớ, `setCapacity(...)` chọn số bản ghi tối đa khi sử dụng với dung lượng dương đã cấu hình từ lúc khởi tạo. Bản ghi cũ sẽ nhường chỗ cho bản ghi mới khi đầy.

Chọn 50 bản ghi không có nghĩa là:

- dữ liệu chỉ tồn tại trong 50 giây;
- bộ nhớ bị giới hạn chính xác ở một số byte cụ thể;
- chỉ có 50 yêu cầu lỗi được giữ;
- dữ liệu đã bị xóa khỏi mọi nơi khác sau khi rời repository.

Lưu lượng cao có thể thay toàn bộ cửa sổ rất nhanh; khi không có lưu lượng mới, các bản ghi vẫn có thể nằm trong bộ nhớ của repository. Nếu cần thời hạn lưu cố định theo thời gian, phải thiết kế cơ chế đó riêng.

Để ước lượng chi phí:

```text
C: số bản ghi tối đa
S: kích thước dữ liệu trung bình của một bản ghi

Dữ liệu được giữ xấp xỉ C × S, cộng chi phí đối tượng Java.
```

Đây là mô hình ước lượng, không phải công thức đo heap chính xác. Header nhiều giá trị hoặc URI dài làm S tăng. Chỉ giảm C mà vẫn giữ các header lớn không giải quyết đầy đủ vấn đề.

Cách áp dụng thực tế là chọn cửa sổ vừa đủ để tái hiện lỗi, bỏ các trường không cần, tránh sao chép giá trị dài không kiểm soát và đo bộ nhớ dưới lưu lượng phù hợp. Không dùng `capacity=0` để tắt ghi nhận; Boot có thuộc tính `management.httpexchanges.recording.enabled=false` dành cho mục đích đó. [Điều khiển cơ chế ghi nhận](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

## 3. Biết chính xác header nào được thu thập

### 3.1. Hành vi của cơ chế ghi nhận chuẩn

Trong bản Boot 3.3.0 dùng cho thí nghiệm, các lựa chọn mặc định từ `Include.defaultIncludes()` gồm thời lượng, header yêu cầu và header phản hồi. Khi đi qua cơ chế tạo exchange chuẩn, `Authorization` và `Cookie` của yêu cầu, cùng `Set-Cookie` của phản hồi, bị loại nếu không bật các lựa chọn nhạy cảm tương ứng.

Các lựa chọn quan trọng:

| Tùy chọn trong cấu hình `recording.include` | Ý nghĩa |
| --- | --- |
| `time-taken` | Ghi thời lượng xử lý |
| `request-headers` | Thu thập nhóm header yêu cầu |
| `response-headers` | Thu thập nhóm header phản hồi |
| `authorization-header` | Cho phép giữ `Authorization` khi thu thập header yêu cầu |
| `cookie-headers` | Cho phép giữ `Cookie`/`Set-Cookie` trong nhóm header tương ứng |
| `principal` | Thu thập danh tính đã xác thực khi có |
| `session-id` | Thu thập mã phiên khi có |
| `remote-address` | Thu thập địa chỉ từ xa khi có |

Đây là các nhóm dữ liệu của `Include`, không phải danh sách tên header tùy ý. Ví dụ, `recording.include: X-Api-Key` không phải cách khai báo một header được phép. [API `Include`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html)

Việc loại một số header quen thuộc không có nghĩa là có bộ phát hiện mọi bí mật. Khi chọn `request-headers`, các header tự đặt như `X-Api-Key`, `X-Customer-Email` hoặc `X-Access-Token` cần chính sách riêng. Phản hồi cũng có thể mang thông tin nhạy cảm trong `Location` hay header nghiệp vụ.

### 3.2. Cấu hình ít dữ liệu trước

Nếu chỉ cần đường dẫn, phương thức, trạng thái và thời lượng, bắt đầu với:

```yaml
management:
  httpexchanges:
    recording:
      enabled: true
      include:
        - time-taken
```

Danh sách khai báo rõ này thay cho các nhóm mặc định, nên không yêu cầu thu thập header, principal, session ID hoặc địa chỉ từ xa. Nó không loại bỏ URI khỏi phần thông tin cơ bản của exchange.

Cấu hình nhóm dữ liệu cũng không phải một bộ lọc áp lên mọi đối tượng bạn tự tạo. Nếu mã ứng dụng gọi constructor công khai của `HttpExchange.Request`/`Response` với một map header rồi tự gọi `repository.add(...)`, bạn phải kiểm soát map đó. Đừng giả định thuộc tính ghi nhận sẽ tự sửa mọi exchange được thêm thủ công. [Các constructor của `HttpExchange`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html)

## 4. Dữ liệu cá nhân có thể nằm ngoài header

| Vị trí | Ví dụ dữ liệu giả | Cách giảm dữ liệu có thể áp dụng |
| --- | --- | --- |
| Query string | `?email=learner%40example.test` | Bỏ toàn bộ query nếu không cần cho chẩn đoán |
| Path | `/users/learner@example.test` | Dùng nhãn đường dẫn đã biết hoặc thay bằng nhãn chung |
| Mã tài nguyên trong path | `/orders/123` | Đổi thành nhóm `/orders/_id` khi chỉ cần phân biệt loại API |
| Principal | Tên tài khoản | Không thu nếu câu hỏi chẩn đoán không cần danh tính |
| Session | Mã phiên | Không giữ mã phiên để tránh liên kết hoặc lộ phiên |
| Remote address | Địa chỉ IP | Không thu nếu không cần phân tích mạng |
| Header tự đặt | Email, token nghiệp vụ | Bỏ toàn bộ hoặc chỉ cho phép những trường đã đánh giá |

Không nên sửa URL bằng cách chỉ xóa một tham số có tên `password`: tên tham số mới hoặc dữ liệu trong path vẫn có thể bị bỏ sót. Khi không có nhu cầu giữ query, bỏ cả query đơn giản và dễ kiểm tra hơn.

Nếu cần giữ header, danh sách cho phép (allowlist) phải xác định cả tên, số giá trị, độ dài và nội dung giá trị được chấp nhận. Tên header không phân biệt hoa thường; `authorization` không được trở thành một lối đi vòng qua bộ lọc chỉ so sánh đúng chuỗi `Authorization`.

Chỉ thay vài ký tự cuối của email hoặc băm một mã định danh không đủ để khẳng định dữ liệu đã hoàn toàn vô danh. Hãy mô tả chính xác thao tác đã làm và phần thông tin còn giữ. OWASP khuyến nghị tránh đưa token, mã phiên và dữ liệu nhạy cảm không cần thiết vào dữ liệu ghi nhận; nguyên tắc này cũng hữu ích cho kho chẩn đoán HTTP. [OWASP: dữ liệu cần loại khỏi log](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)

## 5. Đặt ranh giới giảm dữ liệu trước khi lưu

Một điểm kiểm soát tập trung là triển khai `HttpExchangeRepository` rồi ủy quyền cho một `InMemoryHttpExchangeRepository` ở bên trong:

```text
Exchange đầu vào
      ↓
Chính sách giảm dữ liệu của ứng dụng
      ↓
Tạo exchange mới chỉ chứa dữ liệu được phép
      ↓
Repository bộ nhớ có dung lượng hữu hạn
      ↓
Endpoint hoặc mã chẩn đoán đọc dữ liệu đã giảm
```

Chỉ che dữ liệu ở giao diện hoặc trong JSON trả về vẫn để dữ liệu gốc nằm trong repository. Giảm dữ liệu ở `add(...)` giúp ranh giới lưu của repository chỉ nhận bản đã xử lý.

Tuy vậy, exchange đầu vào đã được tạo trước khi phương thức này chạy. Cách làm này không bảo đảm dữ liệu gốc chưa từng xuất hiện trong bộ nhớ yêu cầu, log máy chủ, proxy, trace hoặc heap dump. Cần xét những nơi ghi nhận khác theo chính sách của ứng dụng.

## 6. Ví dụ đầy đủ: kho nhỏ chỉ giữ metadata đã chọn

Ví dụ sau chọn một chính sách cố ý đơn giản:

- Giữ tối đa C bản ghi; C trong khoảng 1–500 là giới hạn riêng của ví dụ.
- Bỏ toàn bộ header yêu cầu và phản hồi.
- Bỏ principal, session và địa chỉ từ xa.
- Bỏ query, host gốc và thông tin xác thực trong URI.
- Chỉ giữ hai nhóm đường dẫn đã biết; đường dẫn khác thành `/redacted`.
- Giữ timestamp, trạng thái, thời lượng và phương thức HTTP thuộc tập cho phép.

Đổi lại, người đọc mất chi tiết để điều tra từng tài khoản hoặc từng đơn hàng. Đây là lựa chọn phù hợp khi câu hỏi chỉ liên quan đến nhóm API và tình trạng xử lý, không phải một chính sách có thể sao chép nguyên trạng cho mọi ứng dụng.

### 6.1. Lớp repository

Tệp `src/main/java/example/exchangeprivacy/MinimizedHttpExchangeRepository.java`:

```java
package example.exchangeprivacy;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public final class MinimizedHttpExchangeRepository
        implements HttpExchangeRepository {

    private static final Set<String> METHODS = Set.of(
            "GET", "POST", "PUT", "PATCH", "DELETE",
            "HEAD", "OPTIONS", "TRACE", "CONNECT");

    private final InMemoryHttpExchangeRepository delegate;

    public MinimizedHttpExchangeRepository(int capacity) {
        if (capacity < 1 || capacity > 500) {
            throw new IllegalArgumentException("capacity must be between 1 and 500");
        }
        delegate = new InMemoryHttpExchangeRepository();
        delegate.setCapacity(capacity);
    }

    @Override
    public void add(HttpExchange exchange) {
        Objects.requireNonNull(exchange, "exchange");
        var originalRequest = Objects.requireNonNull(
                exchange.getRequest(), "request");
        var originalResponse = Objects.requireNonNull(
                exchange.getResponse(), "response");
        URI originalUri = Objects.requireNonNull(
                originalRequest.getUri(), "uri");

        String method = originalRequest.getMethod();
        String safeMethod = method != null && METHODS.contains(method)
                ? method : "OTHER";
        URI safeUri = URI.create(
                "http://diagnostics.invalid" + minimizedPath(originalUri));

        var safeRequest = new HttpExchange.Request(
                safeUri, null, safeMethod, Map.of());
        var safeResponse = new HttpExchange.Response(
                originalResponse.getStatus(), Map.of());

        var minimized = new HttpExchange(
                exchange.getTimestamp(),
                safeRequest,
                safeResponse,
                null,
                null,
                exchange.getTimeTaken());
        delegate.add(minimized);
    }

    @Override
    public List<HttpExchange> findAll() {
        return delegate.findAll();
    }

    private static String minimizedPath(URI uri) {
        String path = uri.getRawPath();
        if ("/catalog/items".equals(path)) {
            return "/catalog/items";
        }
        if (path != null && path.matches("/orders/[0-9]{1,18}")) {
            return "/orders/_id";
        }
        return "/redacted";
    }
}
```

`minimizedPath(...)` chỉ trả một trong ba chuỗi hằng. Nó không trả lại đường dẫn chưa được nhận diện, kể cả khi đường dẫn đó chứa email, Unicode hay dữ liệu được mã hóa phần trăm. `/orders/_id` là nhãn chẩn đoán của ví dụ, không phải URL để gọi lại một đơn hàng.

`http://diagnostics.invalid` cũng là địa chỉ thay thế cố định để duy trì cấu trúc URI. Nó không mô tả host hoặc giao thức thực tế của yêu cầu. Nếu bài toán cần phân biệt dịch vụ, hãy thiết kế một nhãn dịch vụ được kiểm soát thay vì giữ tùy ý host do yêu cầu mang tới.

Map header rỗng được tạo mới cho bản ghi đã giảm. Vì không sao chép header nào, chính sách này cũng loại header nhiều giá trị, header lạ và mọi biến thể hoa/thường của tên nhạy cảm. Mã không in exchange gốc ra log trong lúc xử lý.

### 6.2. Chương trình kiểm tra độc lập

Tệp `src/main/java/example/exchangeprivacy/ExchangePrivacyDemo.java`:

```java
package example.exchangeprivacy;

import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;

public class ExchangePrivacyDemo {

    public static void main(String[] args) {
        var repository = new MinimizedHttpExchangeRepository(2);
        String orderUri = "https://shop.example.test/orders/123"
                + "?email=learner%40example.test";

        repository.add(sample(200, orderUri));
        repository.add(sample(500, orderUri));

        List<HttpExchange> firstSnapshot = repository.findAll();
        HttpExchange latest = firstSnapshot.get(0);
        System.out.println("size=" + firstSnapshot.size());
        System.out.println("firstStatus=" + latest.getResponse().getStatus());
        System.out.println("uri=" + latest.getRequest().getUri());
        System.out.println("requestHeaders=" + latest.getRequest().getHeaders());
        System.out.println("responseHeaders=" + latest.getResponse().getHeaders());
        System.out.println("remoteAddress=" + latest.getRequest().getRemoteAddress());
        System.out.println("principal=" + latest.getPrincipal());
        System.out.println("session=" + latest.getSession());
        System.out.println("timeTaken=" + latest.getTimeTaken());

        repository.add(sample(204,
                "https://shop.example.test/users/learner%40example.test"));
        List<HttpExchange> secondSnapshot = repository.findAll();
        System.out.println("afterThirdSize=" + secondSnapshot.size());
        System.out.println("retainedStatuses=" + secondSnapshot.stream()
                .map(item -> item.getResponse().getStatus()).toList());
        System.out.println("unknownPath="
                + secondSnapshot.get(0).getRequest().getUri().getPath());
    }

    private static HttpExchange sample(int status, String uri) {
        Map<String, List<String>> requestHeaders = Map.of(
                "authorization", List.of("Bearer demo-only-token"),
                "Cookie", List.of("sid=demo-only-session"),
                "X-Api-Key", List.of("demo-only-key"),
                "X-Customer-Email", List.of("learner@example.test"));
        Map<String, List<String>> responseHeaders = Map.of(
                "Set-Cookie", List.of("sid=demo-only-session"),
                "Location", List.of("/next?email=learner%40example.test"));

        return new HttpExchange(
                Instant.parse("2025-01-01T00:00:00Z"),
                new HttpExchange.Request(
                        URI.create(uri), "192.0.2.10", "GET", requestHeaders),
                new HttpExchange.Response(status, responseHeaders),
                new HttpExchange.Principal("demo-user"),
                new HttpExchange.Session("demo-only-session"),
                Duration.ofMillis(10));
    }
}
```

Chương trình dùng constructor trực tiếp để cố ý đưa các trường nhạy cảm giả vào đầu vào, rồi kiểm tra chính ranh giới lưu của repository. Nó không khởi động máy chủ HTTP và không gửi dữ liệu ra mạng.

### 6.3. Cấu hình và chạy dự án mẫu

Dùng JDK 21 và một dự án có sẵn Gradle Wrapper 8.5. Tệp `settings.gradle`:

```groovy
rootProject.name = 'http-exchange-privacy-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-actuator:3.3.0'
}

application {
    mainClass = 'example.exchangeprivacy.ExchangePrivacyDemo'
}
```

Trên PowerShell:

```powershell
.\gradlew.bat -q run
```

Trên Linux/macOS:

```bash
./gradlew -q run
```

Phần stdout của chương trình:

```text
size=2
firstStatus=500
uri=http://diagnostics.invalid/orders/_id
requestHeaders={}
responseHeaders={}
remoteAddress=null
principal=null
session=null
timeTaken=PT0.01S
afterThirdSize=2
retainedStatuses=[204, 500]
unknownPath=/redacted
```

Như vậy, bản ghi số một đã nhường chỗ sau lần thêm thứ ba, còn dữ liệu được giữ không chứa query email, mã đơn hàng, header gốc hoặc các trường định danh đã loại. Trạng thái và thời lượng vẫn còn để phục vụ câu hỏi chẩn đoán đã chọn.

## 7. Nối repository vào ứng dụng Boot

Trong ứng dụng web Boot 3.3 đã có dependency Actuator, đặt lớp cấu hình sau trong package được ứng dụng quét. Đoạn này bổ sung cho ứng dụng có sẵn, không phải phần khởi động của chương trình độc lập phía trên:

```java
package example.exchangeprivacy;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("local-exchange-diagnostics")
public class HttpExchangePrivacyConfiguration {

    @Bean
    public HttpExchangeRepository httpExchangeRepository() {
        return new MinimizedHttpExchangeRepository(50);
    }
}
```

Chỉ đăng ký một repository theo chính sách này. Đối tượng `delegate` nằm bên trong và không được đăng ký thêm thành một bean công khai để mã khác vô tình ghi thẳng dữ liệu gốc vào đó.

Đặt các thuộc tính trong `application-local-exchange-diagnostics.yml`:

```yaml
server:
  address: 127.0.0.1

management:
  endpoint:
    httpexchanges:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,httpexchanges
  httpexchanges:
    recording:
      enabled: true
      include:
        - time-taken
```

Kích hoạt profile `local-exchange-diagnostics` khi chạy ứng dụng phát triển. Cấu hình chỉ chọn nhóm thời lượng giúp giảm thu thập từ đầu; repository tiếp tục bảo vệ chính sách lưu kể cả khi có mã khác thêm exchange trực tiếp.

Trong mô hình dùng chung máy chủ với cấu hình mặc định và không có cổng quản trị riêng, bind `127.0.0.1` giới hạn máy chủ ở loopback. Nếu ứng dụng có cổng quản trị riêng, cần cấu hình phạm vi mạng của máy chủ quản trị tương ứng.

Exposure chỉ quyết định endpoint được mở qua công nghệ nào; nó không tự xác thực hoặc phân quyền người đọc. Nếu đã có Spring Security, kiểm tra quy tắc của ứng dụng cho endpoint này; không mở quyền đọc công khai chỉ để thuận tiện chẩn đoán. [Exposure và bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 8. Kiểm tra chính sách bằng dữ liệu giả

Trước khi dùng với lưu lượng thật, nên có các trường hợp kiểm tra tập trung vào ranh giới lưu:

| Dữ liệu đầu vào | Điều cần xác nhận sau khi đọc repository |
| --- | --- |
| `Authorization`, `authorization` và header tự đặt | Không còn giá trị nào nếu chính sách bỏ toàn bộ header |
| Header có nhiều giá trị hoặc giá trị dài | Không bị giữ lại qua một nhánh sao chép phụ |
| Query chứa email/token giả | Query đã bị bỏ hoàn toàn |
| Path có email, ký tự mã hóa hoặc tuyến chưa biết | Trả nhãn chung, không trả nguyên path |
| Principal, session ID và IP | Không còn trong bản được lưu theo chính sách ví dụ |
| Thêm C+1 trao đổi | Repository chỉ giữ C bản ghi với dung lượng đã cố định |
| Dữ liệu khác nhau nhưng cùng nhóm API | Còn đủ thông tin phục vụ câu hỏi chẩn đoán, không giữ nhầm mã tài nguyên |

Không chỉ nhìn ảnh chụp giao diện đã che dữ liệu. Hãy kiểm tra đối tượng được repository trả về và, khi tích hợp web, phản hồi JSON của `/actuator/httpexchanges`. API này có các trường URI, header, principal, session và thông tin khác tùy dữ liệu được ghi nhận. [Schema HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

Giới hạn của ví dụ cần được giữ rõ: timestamp và một số metadata vẫn còn; đây là chính sách giảm dữ liệu đã chọn, không phải chứng nhận rằng không ai có thể liên hệ một trao đổi với sự kiện khác. Timestamp cố định trong chương trình chỉ giúp stdout ổn định, không phải chính sách thay timestamp của ứng dụng.

## 9. Các lỗi thiết kế thường gặp

- **Để mặc định rồi cho rằng mọi bí mật đều bị che:** cơ chế chuẩn có loại một số header, nhưng không biết toàn bộ tên header nghiệp vụ.
- **Chỉ giảm dung lượng:** ít bản ghi hơn vẫn có thể chứa token hoặc dữ liệu cá nhân.
- **Chỉ bỏ query:** đường dẫn, principal, session và header phản hồi vẫn có thể tiết lộ thông tin.
- **Chỉ sửa JSON khi đọc:** dữ liệu gốc vẫn đã được lưu ở phía trong.
- **Bật `authorization-header` hoặc `cookie-headers` để dễ debug:** có thể đưa thông tin xác thực vào kho chẩn đoán; hãy tìm cách xác minh giả thuyết mà không thu token thật.
- **Ghi exchange gốc vào log trước khi giảm dữ liệu:** tạo một bản sao ngoài ranh giới đang kiểm soát.
- **Coi khởi động lại hoặc tắt ghi nhận là xóa mọi bản sao:** snapshot đã xuất, log hay heap dump có vòng đời riêng.

Nếu không cần HTTP exchanges cho một lần chạy, có thể tắt cơ chế ghi nhận thay vì để nó thu thập rồi mới tìm cách xóa. Nếu cần lịch sử bền vững hoặc chẩn đoán phân tán, hãy chọn kiến trúc quan sát phù hợp và áp dụng cùng chính sách dữ liệu ở nơi lưu tương ứng.

## 10. Tự kiểm tra

1. Vì sao `recording.include: [time-taken]` vẫn chưa giải quyết email nằm trong URI?
2. Một header `X-Api-Key` có tự được bảo vệ chỉ vì `Authorization` bị loại mặc định không?
3. Chính sách ví dụ giữ gì và đánh đổi điều gì khi biến `/orders/123` thành `/orders/_id`?
4. Việc repository chỉ có 50 bản ghi có chứng minh rằng dữ liệu không tồn tại quá 10 phút không?

Đối chiếu: (1) URI là phần thông tin cơ bản, không phải nhóm header đã bỏ; (2) không, cần chính sách riêng cho header tự đặt; (3) còn biết nhóm API nhưng mất mã đơn hàng để truy tìm từng tài nguyên; (4) không, số bản ghi và thời gian lưu là hai giới hạn khác nhau.
