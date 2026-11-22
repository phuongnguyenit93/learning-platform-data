# Lựa chọn thông tin yêu cầu, phản hồi và thời gian được ghi nhận

## 1. Ghi đủ để trả lời câu hỏi, đồng thời biết rõ dữ liệu đang giữ

Giả sử một API trả về lỗi không đều. Bạn muốn biết phương thức HTTP, đường dẫn, mã phản hồi và thời gian xử lý. Trong một tình huống khác, bạn cần kiểm tra `Accept` ở yêu cầu và `Content-Type` ở phản hồi để tìm lỗi thương lượng nội dung.

Hai câu hỏi đó cần những tập thông tin khác nhau. Nếu luôn ghi mọi header, bộ đệm có thể giữ cả thông tin xác thực, cookie hoặc các khóa tùy biến. Nếu bỏ thông tin thời gian mà vẫn định điều tra độ trễ, bản ghi lại thiếu bằng chứng cần thiết.

Với Spring Boot Actuator, **lựa chọn thông tin ghi nhận** là quyết định ở lúc tạo bản ghi HTTP exchange: giữ nhóm dữ liệu nào của yêu cầu, phản hồi và thời gian. Nó khác với việc cho phép một người đọc endpoint, giới hạn số bản ghi hoặc chọn một số request để lưu.

Bài dùng cơ chế `HttpExchangeRepository` và `management.httpexchanges.recording.include` của **Spring Boot 3.3.x**. Không dùng các tên cấu hình của endpoint `httptrace` trong các thế hệ Boot cũ. [Spring Boot 3.3: Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

## 2. Phân biệt thông tin nền và thông tin có thể chọn

Một `HttpExchange` mô tả một cặp yêu cầu–phản hồi. Các thông tin nền như thời điểm bắt đầu, phương thức, URI và mã phản hồi giúp xác định trao đổi đang được mô tả.

Những nhóm bổ sung được lựa chọn bằng tập `Include`:

| Tên trong YAML | Hằng Java | Dữ liệu được chọn | Điều cần cân nhắc |
| --- | --- | --- | --- |
| `request-headers` | `REQUEST_HEADERS` | Nhóm header yêu cầu, có quy tắc loại riêng một số header | Có thể chứa header tùy biến nhạy cảm |
| `response-headers` | `RESPONSE_HEADERS` | Nhóm header phản hồi, có quy tắc loại riêng cookie | Có thể lộ thông tin qua các header của ứng dụng |
| `time-taken` | `TIME_TAKEN` | Thời lượng xử lý được bộ ghi nhận tính | Không phải thời gian CPU hoặc toàn bộ thời gian trên mạng |
| `principal` | `PRINCIPAL` | Tên danh tính gắn với trao đổi, nếu có | Là dữ liệu liên quan người dùng; không phải bản sao toàn bộ đối tượng xác thực |
| `remote-address` | `REMOTE_ADDRESS` | Địa chỉ bên gửi mà ứng dụng nhìn thấy | Có thể là proxy; cần hiểu điểm quan sát |
| `session-id` | `SESSION_ID` | Mã phiên do lớp tích hợp cung cấp, nếu có | Là định danh nhạy cảm; không cần cho mọi API |
| `authorization-header` | `AUTHORIZATION_HEADER` | Cho phép giữ header `Authorization` khi ghi nhóm header yêu cầu | Có thể giữ thông tin xác thực thực tế |
| `cookie-headers` | `COOKIE_HEADERS` | Cho phép giữ `Cookie` ở yêu cầu và `Set-Cookie` ở phản hồi trong nhóm tương ứng | Có thể giữ dữ liệu phiên và cookie nhạy cảm |

Các tên YAML dùng dạng chữ thường với dấu gạch nối; mã Java dùng tên enum viết hoa. Đây là các lựa chọn theo **nhóm dữ liệu**, không phải danh sách tên header tùy ý. [API Include của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html).

Không có lựa chọn chuẩn tên `request-body`, `response-body`, `all` hoặc `time-taken-ms` trong tập enum này. Không tự thêm chúng vào YAML rồi kỳ vọng Boot sẽ lưu payload hoặc đổi đơn vị thời gian.

### Mặc định không có nghĩa là mọi trường đều được ghi

Tập mặc định trong nhánh 3.3 được kiểm chứng ở ví dụ là:

```text
TIME_TAKEN
REQUEST_HEADERS
RESPONSE_HEADERS
```

Khi ghi các nhóm header mặc định:

- `Authorization` và `Cookie` không được giữ trong header yêu cầu.
- `Set-Cookie` không được giữ trong header phản hồi.
- Các header khác vẫn có thể được giữ, kể cả header tùy biến mang khóa hoặc thông tin riêng.

Đó là quy tắc loại một số tên header, không phải cơ chế nhận diện mọi bí mật. Ví dụ `X-Api-Key` không tự được che chỉ vì giá trị của nó là khóa truy cập.

## 3. Chọn tập include có chủ đích

### 3.1. Cấu hình chỉ giữ thêm thời lượng

Khi chỉ cần phương thức, URI, status và thời lượng, có thể chọn:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
```

Danh sách được khai báo này **thay thế tập mặc định**; nó không tự cộng thêm `time-taken` vào hai nhóm header mặc định.

Với cấu hình trên, thông tin nền vẫn được giữ nhưng các bản đồ header không có dữ liệu đã chọn. Không hiểu “chỉ time-taken” là bản ghi chỉ còn duy nhất một con số thời gian.

Đặc biệt, URI vẫn có thể chứa query string. Bỏ `request-headers` không làm một token trong URL biến mất.

### 3.2. Thêm hai nhóm header để kiểm tra giao thức

Nếu đang điều tra việc client gửi hoặc nhận định dạng nào:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
        - request-headers
        - response-headers
```

Tập này phù hợp cho việc quan sát các trường như `Accept` và `Content-Type`, nhưng nó cũng chọn các header khác trong nhóm sau khi áp dụng quy tắc loại tên riêng.

Cấu hình sau **không phải** cách chỉ ghi hai header:

```text
include: [Accept, Content-Type]
```

`Accept` và `Content-Type` không phải giá trị của enum `Include`. Nếu cần danh sách header được phép riêng, phải có lớp tùy biến xử lý dữ liệu với chính sách đó; thuộc tính `include` chuẩn không cung cấp bộ lọc theo từng tên header.

### 3.3. Chọn thông tin danh tính khi thật sự cần

Ví dụ cần liên hệ lỗi với danh tính đã được xác thực nhưng chưa cần đọc header:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
        - principal
```

`principal` chỉ có ý nghĩa khi lớp tích hợp có danh tính để cung cấp. Bật cờ không xác thực người dùng, không cấp vai trò và không bảo đảm mọi bản ghi đều có tên danh tính.

Tương tự, `session-id` chỉ ghi mã phiên nếu có. API không dùng phiên có thể không có giá trị đó. Không thêm phiên chỉ để làm một trường chẩn đoán xuất hiện.

`remote-address` là địa chỉ theo góc nhìn của ứng dụng, có thể là địa chỉ proxy. Việc tin các header chuyển tiếp phải dựa trên cấu hình proxy đáng tin cậy; không coi địa chỉ do client tự gửi là bằng chứng danh tính.

### 3.4. Tránh bật thông tin xác thực chỉ để “cho đủ dữ liệu”

`authorization-header` và `cookie-headers` là những lựa chọn có ảnh hưởng rõ đến dữ liệu nhạy cảm. Chúng bổ sung hành vi cho các nhóm header tương ứng; không nên bật như một phần của cấu hình quan sát thông thường chỉ vì muốn thấy tất cả trường.

Nếu vấn đề là token hết hạn, thường có thể ghi một mã nguyên nhân đã kiểm soát hoặc kết quả xác thực phù hợp thay vì lưu nguyên token. Nếu cần phân biệt phiên, đánh giá phương án định danh chẩn đoán riêng thay cho việc phát tán session ID.

Không đưa token, cookie hoặc dữ liệu người dùng thật vào ví dụ thử nghiệm.

## 4. Thời điểm và thời lượng trả lời hai câu hỏi khác nhau

### Timestamp: trao đổi bắt đầu khi nào?

`timestamp` là thời điểm bắt đầu được cơ chế ghi nhận lưu lại. Nó hữu ích để đối chiếu với log và dữ liệu từ hệ thống khác.

Một giá trị như:

```text
2024-01-01T00:00:00Z
```

là mốc thời gian UTC. Nó không cho biết request kéo dài bao lâu.

### Time taken: cơ chế ghi nhận quan sát được bao lâu?

Khi có `time-taken`, trường `timeTaken` biểu diễn thời lượng. Ví dụ:

```text
PT0.125S = 0,125 giây = 125 mili giây
```

Không đọc `PT0.125S` thành 0,125 mili giây. Trong Java, kiểu tương ứng là `Duration`; khi viết công cụ xử lý, nên phân tích bằng API thời lượng thay vì cắt chuỗi theo vị trí. [API dữ liệu httpexchanges](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html).

Nếu không chọn `time-taken`, không có thời lượng trong mô hình được tạo theo tập lựa chọn đó. Điều này không có nghĩa request mất 0 ms. Cách biểu diễn giá trị không có trong JSON còn phụ thuộc cách tuần tự hóa; hãy phân biệt dữ liệu không được ghi với một số đo bằng 0.

### Đừng suy rộng phạm vi phép đo

Thời lượng này không phải:

- Tổng thời gian CPU đã sử dụng.
- Mọi thời gian DNS, kết nối và mạng từ thiết bị người dùng.
- Thời gian từng câu SQL hoặc từng dịch vụ phía sau.
- Một phân vị p95/p99 của toàn bộ lưu lượng.

Ranh giới ghi nhận phụ thuộc lớp tích hợp Servlet/WebFlux và đường xử lý thực tế. Với xử lý bất đồng bộ hoặc phản hồi dạng luồng, phải kiểm chứng lúc nào bộ ghi coi trao đổi là hoàn tất; không suy từ một request đồng bộ ngắn sang mọi loại phản hồi.

Ví dụ Java bên dưới dùng hai `Clock` cố định để kiểm tra đúng thời lượng 125 ms. Đó là cách kiểm chứng mô hình, không phải benchmark hoặc cam kết về độ chính xác đồng hồ trong ứng dụng đang chạy.

## 5. Thí nghiệm Java kiểm chứng từng lựa chọn

### Chuẩn bị một dự án thử không có máy chủ HTTP

Chương trình dùng trực tiếp `HttpExchange.start(...).finish(...)` với dữ liệu tổng hợp. Nó không gửi request thật, không mở cổng mạng và không tạo phiên đăng nhập.

Thí nghiệm dùng Spring Boot 3.3.0 để tái lập API và kết quả đã kiểm chứng, cùng Java 17 trở lên. Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>exchange-selection-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

Lưu mã tại `src/main/java/ExchangeSelectionDemo.java`:

```java
import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.Include;
import org.springframework.boot.actuate.web.exchanges.RecordableHttpRequest;
import org.springframework.boot.actuate.web.exchanges.RecordableHttpResponse;

public class ExchangeSelectionDemo {
    private static final Instant START = Instant.parse("2024-01-01T00:00:00Z");

    private static final RecordableHttpRequest REQUEST = new RecordableHttpRequest() {
        public URI getUri() {
            return URI.create("https://example.test/orders/42?view=summary");
        }
        public String getRemoteAddress() {
            return "192.0.2.10";
        }
        public String getMethod() {
            return "GET";
        }
        public Map<String, List<String>> getHeaders() {
            return Map.of(
                    "Accept", List.of("application/json"),
                    "Authorization", List.of("Bearer demo-token"),
                    "Cookie", List.of("sid=demo"),
                    "X-Api-Key", List.of("demo-key"));
        }
    };

    private static final RecordableHttpResponse RESPONSE = new RecordableHttpResponse() {
        public int getStatus() {
            return 200;
        }
        public Map<String, List<String>> getHeaders() {
            return Map.of(
                    "Content-Type", List.of("application/json"),
                    "Set-Cookie", List.of("sid=demo; HttpOnly"));
        }
    };

    public static void main(String[] args) {
        show("defaults", record(Include.defaultIncludes()));

        HttpExchange minimal = record(EnumSet.of(Include.TIME_TAKEN));
        show("minimal", minimal);
        System.out.println("minimal.uri=" + minimal.getRequest().getUri());

        show("identity", record(EnumSet.of(
                Include.TIME_TAKEN, Include.PRINCIPAL,
                Include.REMOTE_ADDRESS, Include.SESSION_ID)));

        HttpExchange noTime = record(EnumSet.noneOf(Include.class));
        System.out.println("noTime.timeTaken=" + noTime.getTimeTaken());
    }

    private static HttpExchange record(Set<Include> includes) {
        Clock begin = Clock.fixed(START, ZoneOffset.UTC);
        Clock end = Clock.fixed(START.plusMillis(125), ZoneOffset.UTC);
        return HttpExchange.start(begin, REQUEST).finish(
                end, RESPONSE, () -> () -> "demo-user", () -> "demo-session", includes);
    }

    private static void show(String label, HttpExchange exchange) {
        System.out.println(label + ".requestHeaders="
                + new TreeSet<>(exchange.getRequest().getHeaders().keySet()));
        System.out.println(label + ".responseHeaders="
                + new TreeSet<>(exchange.getResponse().getHeaders().keySet()));
        System.out.println(label + ".timeTaken=" + exchange.getTimeTaken());
        System.out.println(label + ".identity="
                + (exchange.getPrincipal() != null) + "/"
                + (exchange.getRequest().getRemoteAddress() != null) + "/"
                + (exchange.getSession() != null));
    }
}
```

Tất cả token, cookie, danh tính và địa chỉ trong chương trình là dữ liệu giả. Chương trình chỉ in **tên** header và trạng thái có/không, không in các giá trị header.

### Biên dịch và chạy

Với Maven và JDK 17 trở lên:

```bash
mvn -q compile dependency:copy-dependencies
```

Trên Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' ExchangeSelectionDemo
```

Trên Linux/macOS:

```bash
java -cp 'target/classes:target/dependency/*' ExchangeSelectionDemo
```

Dấu ngăn cách classpath trên Windows là `;`, trên Linux/macOS là `:`. Maven cần truy cập được dependency nếu cache chưa có.

Stdout chính xác:

```text
defaults.requestHeaders=[Accept, X-Api-Key]
defaults.responseHeaders=[Content-Type]
defaults.timeTaken=PT0.125S
defaults.identity=false/false/false
minimal.requestHeaders=[]
minimal.responseHeaders=[]
minimal.timeTaken=PT0.125S
minimal.identity=false/false/false
minimal.uri=https://example.test/orders/42?view=summary
identity.requestHeaders=[]
identity.responseHeaders=[]
identity.timeTaken=PT0.125S
identity.identity=true/true/true
noTime.timeTaken=null
```

Trong dòng `identity`, ba giá trị lần lượt cho biết có principal, remote address và session hay không. `TreeSet` được dùng khi in tên header để thứ tự stdout ổn định, không phụ thuộc thứ tự lặp của `Map`.

### Đọc kết quả thành các kết luận cụ thể

| Kết quả | Điều đã chứng minh |
| --- | --- |
| Mặc định chỉ còn `Accept` và `X-Api-Key` ở yêu cầu | Có lọc tên header xác thực/cookie riêng nhưng không tự lọc mọi header có thể mang bí mật |
| Mặc định chỉ còn `Content-Type` ở phản hồi | `Set-Cookie` không được chọn bởi tập mặc định |
| Tập tối thiểu có các danh sách header rỗng | Chỉ chọn `TIME_TAKEN` không giữ hai nhóm header |
| URI của tập tối thiểu vẫn có `?view=summary` | Loại header không đồng thời loại query string |
| Tập identity có `true/true/true` | Các cờ danh tính ghi dữ liệu do các supplier trong thí nghiệm cung cấp |
| Tập không có `TIME_TAKEN` trả `null` ở Java | Không được ghi nhận thời lượng khác với đo được thời lượng bằng 0 |

Không dùng các supplier giả trong chương trình như cách triển khai xác thực của ứng dụng thật. Lớp tích hợp web phải cung cấp ngữ cảnh từ request đang xử lý, theo cơ chế bảo mật và phiên đã cấu hình.

Việc tạo bản ghi bằng constructor đầy đủ ở một repository tùy biến không tự áp dụng lại tập `Include`. Nếu tự xây dựng hoặc nạp lại bản ghi, bạn phải bảo đảm dữ liệu đó đã tuân thủ chính sách chọn/làm sạch mong muốn.

## 6. Áp dụng trong ứng dụng Spring Boot

### Cần có nơi nhận bản ghi

Đối với ứng dụng web có Actuator, có thể khai báo một repository phục vụ phát triển:

```java
package example.httpcapture;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HttpExchangeStorageConfiguration {

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(50);
        return repository;
    }
}
```

Đoạn này là cấu hình tích hợp vào ứng dụng Spring Boot có web stack; nó không thuộc chương trình độc lập ở trên.

Sau đó chọn tập `include` trong cấu hình ứng dụng, chẳng hạn `[time-taken]` để bắt đầu với ít dữ liệu bổ sung. Đường `httpexchanges` chỉ đọc những bản ghi repository đang giữ; muốn truy cập qua HTTP còn cần exposure và quyền đọc phù hợp.

Sức chứa 50 là **50 bản ghi**, không phải 50 giây, 50 MB hoặc một giới hạn riêng cho từng URI. Repository trong bộ nhớ cũng không tự tạo kho kiểm toán bền vững cho toàn dịch vụ.

### Kiểm tra bằng request thử có thể nhận diện

Trong môi trường thử đã có xác thực, có thể thực hiện một lượt kiểm tra như sau:

1. Dùng dữ liệu giả để gửi một request tới API đã có, kèm `Accept` và một header thử vô hại.
2. Đọc `httpexchanges` bằng danh tính được phép.
3. Tìm đúng bản ghi của request thử; đừng nhầm với bản ghi của chính lần đọc endpoint.
4. Kiểm tra method, URI, status, tập header và thông tin thời gian theo cấu hình.
5. Đổi sang tập include tiếp theo trong một lần chạy thử riêng và gửi request mới.
6. Kiểm tra các bản ghi mới thay vì cho rằng cấu hình đã biến đổi dữ liệu cũ.

Mẫu đọc endpoint trên một hệ thống HTTPS đã được cấu hình sẵn:

```bash
curl --user exchange-reader --fail \
  -H 'Accept: application/json' \
  https://ops.example.test/actuator/httpexchanges
```

Thay địa chỉ ví dụ bằng môi trường thử phù hợp; lệnh này không cấu hình quyền truy cập. Trên PowerShell dùng `curl.exe` và viết trên một dòng nếu shell không hỗ trợ dấu xuống dòng Bash. curl sẽ hỏi mật khẩu khi chỉ cung cấp tên người dùng như trên.

Tách quyền đọc endpoint và chính sách thu thập dữ liệu: người được phép đọc cũng chỉ nên nhận tập dữ liệu thực sự cần thiết.

### Thay include không xóa dữ liệu đã ghi

Trong ứng dụng không có cơ chế cập nhật cấu hình động riêng, thay YAML cần được áp dụng qua vòng đời cấu hình/khởi động phù hợp. Không mặc định sửa tệp là tập include của tiến trình đang chạy đổi ngay.

Nếu một repository còn giữ bản ghi cũ, thay tập lựa chọn cho các bản ghi mới không tự xóa hoặc làm sạch bản ghi cũ. Với kho lưu bền vững hoặc các bản sao đã xuất, phải có quy trình xử lý dữ liệu riêng.

Với `InMemoryHttpExchangeRepository`, khởi động lại tiến trình làm mất bộ đệm trong bộ nhớ. Tuy nhiên, điều đó không thu hồi những bản ghi người khác đã tải hoặc lưu ở nơi khác.

## 7. Chọn nhóm dữ liệu khác với làm sạch dữ liệu

### Header: chọn cả nhóm không phải một danh sách cho phép

Giả sử ứng dụng dùng:

```text
X-Api-Key: demo-key
X-Customer-Email: person@example.test
```

Đây là các giá trị minh họa. Nếu chọn `request-headers`, không thể dựa vào việc mặc định loại `Authorization` để kết luận hai header này cũng đã được xử lý.

Khi cần chính sách chặt theo từng header, thiết kế lớp xử lý chỉ cho phép những tên và giá trị đã chọn, giới hạn độ dài/số lượng và loại thông tin nhạy cảm **trước khi lưu**. Chỉ che ở màn hình đọc không làm dữ liệu đã nằm trong repository biến mất.

Không tự giả định việc ghi đủ header là cần thiết cho mọi lỗi HTTP. Nếu chỉ kiểm tra mã phản hồi và độ trễ, bỏ cả nhóm có thể hợp lý hơn một quy tắc che khó kiểm chứng.

### URI và query string: vẫn phải có chính sách riêng

Một đường dẫn có thể chứa mã khách hàng; một query string có thể chứa email hoặc token. Tập `Include` không phải bộ ẩn danh URL.

Nếu cần thu hẹp URI, có thể thiết kế bản ghi đã chuẩn hóa theo mẫu đường dẫn hoặc chỉ giữ các tham số đã được cho phép. Khi tự dựng lại URI, cần xử lý đúng mã hóa, user-info và query; không dùng biểu thức thay chuỗi đơn giản rồi mặc định mọi dạng URL đều đã sạch.

### Danh tính, IP và mã phiên: không phải thông tin vô hại

Tên principal, địa chỉ IP và session ID có thể liên kết hoạt động với một người hoặc một phiên cụ thể. Với mỗi trường, cần xác định câu hỏi sử dụng, người đọc, thời gian lưu và cách xóa khi hết mục đích.

Đừng dùng một trường có sẵn chỉ vì nó dễ thu thập. Tập tối thiểu cho việc chẩn đoán giao thức không nhất thiết giống tập tối thiểu cho điều tra xác thực.

## 8. Những nhầm lẫn khi cấu hình

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Chỉ thêm `principal` thì vẫn có thời gian và header mặc định | Danh sách include được khai báo thay thế tập mặc định; liệt kê đầy đủ các nhóm cần dùng |
| Bỏ request header thì URI cũng được che | URI là phần khác; query/path cần chính sách riêng |
| Không chọn `time-taken` nghĩa là request mất 0 ms | Không có số đo, không phải số đo bằng 0 |
| Bật `principal` sẽ xác thực request | Cờ chỉ chọn thông tin được cung cấp; bảo mật có cơ chế riêng |
| Bật `session-id` bảo đảm mọi API có session | Không có dữ liệu phiên thì không có mã để ghi |
| `request-headers` chỉ ghi các header “an toàn” | Chỉ có một số quy tắc loại tên riêng; header tùy biến vẫn cần đánh giá |
| Tập include lọc luôn route, status và tần suất lấy mẫu | Nó chọn trường/nhóm thông tin, không phải bộ chọn request theo những tiêu chí đó |
| Đổi include làm sạch mọi bản ghi đang giữ | Chính sách áp dụng khi tạo dữ liệu mới; dữ liệu cũ và bản sao có vòng đời riêng |
| Bật recording nghĩa là ai cũng đọc được endpoint | Ghi nhận, exposure và phân quyền là các lớp tách biệt |

Không dùng `include: []` như cách tắt toàn bộ chức năng ghi nhận. Nếu mục đích là dừng recording theo cấu hình chuẩn, dùng thuộc tính rõ ràng:

```yaml
management:
  httpexchanges:
    recording:
      enabled: false
```

Việc dừng ghi không tự xóa repository, không tắt access log, không tắt metrics và không thu hồi các bản dữ liệu đã xuất.

## 9. Bài thực hành tự kiểm tra

1. Cần method, URI, status và thời lượng nhưng không cần header hoặc danh tính. Viết tập include phù hợp và nêu phần dữ liệu nền vẫn tồn tại.
2. Vì sao cấu hình chỉ có `principal` có thể làm `timeTaken` không còn được ghi?
3. Trong chương trình thử, vì sao `X-Api-Key` còn trong nhóm header mặc định còn `Authorization` bị loại?
4. Nếu bí mật nằm trong query string, bỏ hai nhóm header đã giải quyết được vấn đề chưa?
5. Phân biệt timestamp, Duration `PT0.125S`, thời gian CPU và thời gian người dùng chờ qua mạng.
6. Muốn dừng recording, nên đổi tập include hay đặt `recording.enabled=false`? Những dữ liệu nào vẫn có thể còn sau đó?

Đối chiếu câu 1: `include: [time-taken]` chọn thêm thời lượng; các thông tin nền vẫn có. Câu 2 xuất phát từ việc thay thế tập lựa chọn, không phải lỗi đo thời gian. Một cấu hình tốt phải nêu rõ **giữ dữ liệu gì, vì sao cần, dữ liệu nào vẫn có thể nhạy cảm và cách kiểm chứng trên bản ghi mới**.
