# Sử dụng `InMemoryHttpExchangeRepository` cho chẩn đoán có giới hạn

## 1. Một cửa sổ quan sát nhỏ trong bộ nhớ

Giả sử bạn vừa tái hiện một lỗi HTTP trên máy phát triển. Bạn muốn xem lại vài yêu cầu gần đó: đường dẫn nào được gọi, phản hồi thành công hay thất bại và thời gian xử lý là bao lâu. Giữ toàn bộ lịch sử trong ứng dụng sẽ làm chi phí lưu trữ tăng theo thời gian; giữ một số lượng bản ghi hữu hạn giúp việc kiểm tra đơn giản hơn.

`InMemoryHttpExchangeRepository` là lớp triển khai `HttpExchangeRepository` bằng bộ nhớ của tiến trình. Spring Boot cung cấp nó để lưu các trao đổi yêu cầu–phản hồi gần đây, mặc định là 100 bản ghi. Tài liệu Boot khuyến nghị dùng lớp này trong môi trường phát triển. [Ghi nhận HTTP exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

**Chẩn đoán có giới hạn** nghĩa là kết luận dựa trên một cửa sổ dữ liệu có giới hạn rõ ràng về số lượng, vòng đời và phạm vi ứng dụng. Bạn cần biết cả những gì đang thấy lẫn những gì có thể đã bị loại khỏi cửa sổ đó.

| Thành phần | Trách nhiệm trong luồng quan sát |
| --- | --- |
| Cơ chế ghi nhận HTTP của Boot | Tạo thông tin về một trao đổi HTTP rồi đưa vào repository |
| `InMemoryHttpExchangeRepository` | Giữ một số lượng bản ghi trong bộ nhớ |
| Endpoint `httpexchanges` | Cho phép đọc thông tin đã được repository giữ lại |

Repository trả lời câu hỏi “hiện đang giữ những bản ghi nào?”. Việc endpoint có được mở qua HTTP hay người gọi có quyền đọc là những điều kiện riêng. Bài này tập trung vào cách sử dụng và diễn giải dữ liệu của repository.

## 2. Dung lượng là số bản ghi, không phải số giây

Hai phương thức cấu hình đáng chú ý là `setCapacity(int)` và `setReverse(boolean)`. Hãy chọn dung lượng dương và thiết lập cả hai khi khởi tạo bean, trước khi có lưu lượng. `setReverse` có giá trị mặc định `true`. [API `InMemoryHttpExchangeRepository`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/InMemoryHttpExchangeRepository.html)

Trong ví dụ dùng Boot 3.3.0 dưới đây, khi dung lượng đã cố định là 3 và giữ thứ tự mặc định, việc thêm bản ghi mới làm bản ghi cũ bị loại:

| Sau khi thêm | Danh sách đọc được, mới thêm trước | Bản ghi vừa bị loại |
| --- | --- | --- |
| A | A | Không có |
| B | B, A | Không có |
| C | C, B, A | Không có |
| D | D, C, B | A |
| E | E, D, C | B |

Do đó, dung lượng 100 không có nghĩa là giữ dữ liệu của 100 giây, 100 người dùng hoặc 100 lỗi gần nhất. Yêu cầu thành công cũng chiếm chỗ nếu được ghi nhận; repository không dành riêng dung lượng cho yêu cầu lỗi.

Một phép ước lượng hữu ích khi lưu lượng tương đối đều:

```text
C = dung lượng, tính bằng bản ghi
r = số bản ghi thực sự được thêm mỗi giây

Khoảng lịch sử gần đúng ≈ C / r giây
```

Ví dụ, C = 100 và r = 50 bản ghi/giây chỉ cho khoảng lịch sử cỡ 2 giây. Nếu r giảm xuống 1 bản ghi/giây, cửa sổ có thể dài hơn nhiều. Đây là suy luận để ước lượng từ lưu lượng, không phải thời hạn lưu mà repository cam kết.

Không có cơ chế tự hết hạn theo thời gian (TTL) trong ví dụ này. Khi không có lượt thêm mới và tiến trình vẫn tồn tại, việc đồng hồ chạy thêm một phút không tự làm bản ghi biến mất. Ngược lại, một đợt lưu lượng lớn có thể đẩy bản ghi cần tìm ra rất nhanh.

Số bản ghi bị giới hạn cũng không tạo ra một giới hạn bộ nhớ chính xác theo byte. Kích thước URI, header và các trường tùy chọn có thể khác nhau giữa các bản ghi. Khi tăng C, hãy cân nhắc cả lượng dữ liệu của mỗi trao đổi và chi phí tạo dữ liệu trả về khi đọc.

## 3. Thí nghiệm chạy được: quan sát việc loại bản ghi

Thí nghiệm này tạo các `HttpExchange` giả lập và thêm trực tiếp vào repository. Nó kiểm tra hành vi lưu trữ mà không khởi động máy chủ web, không tạo yêu cầu mạng và không cần cơ sở dữ liệu.

Ví dụ dùng JDK 21 và thư viện Spring Boot 3.3.0. Constructor công khai của `HttpExchange`, `HttpExchange.Request` và `HttpExchange.Response` cho phép tạo đối tượng với dữ liệu đã có. Trong ứng dụng web thông thường, bạn để hạ tầng Boot ghi nhận trao đổi, thay vì tự thêm lại cùng yêu cầu trong controller. [API `HttpExchange`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html), [Request](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.Request.html), [Response](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.Response.html)

### 3.1. Dự án thực hành tối thiểu

Tạo một dự án Java độc lập với Gradle Wrapper 8.5 đã có sẵn. Các đường dẫn sau tính từ thư mục dự án mẫu.

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'bounded-http-exchanges'
```

Nội dung `build.gradle`:

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
    mainClass = 'BoundedExchangeDemo'
}
```

Dự án này dùng thư viện Actuator trực tiếp; plugin `application` chỉ phục vụ chạy hàm `main`. Nó không phải một ứng dụng Spring Boot có endpoint HTTP.

### 3.2. Chương trình đầy đủ

Lưu thành `src/main/java/BoundedExchangeDemo.java`:

```java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public class BoundedExchangeDemo {

    public static void main(String[] args) {
        var newestFirst = new InMemoryHttpExchangeRepository();
        newestFirst.setCapacity(3);

        newestFirst.add(exchange(1, 200));
        newestFirst.add(exchange(2, 500));
        newestFirst.add(exchange(3, 200));

        List<HttpExchange> snapshot = newestFirst.findAll();
        System.out.println("initial=" + paths(snapshot));

        newestFirst.add(exchange(4, 200));
        List<HttpExchange> current = newestFirst.findAll();
        System.out.println("after4=" + paths(current));
        System.out.println("oldSnapshot=" + paths(snapshot));

        long retainedServerErrors = current.stream()
                .filter(item -> item.getResponse().getStatus() >= 500)
                .count();
        System.out.println("retained5xx=" + retainedServerErrors);

        boolean unmodifiable = false;
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        System.out.println("snapshotUnmodifiable=" + unmodifiable);

        var oldestFirst = new InMemoryHttpExchangeRepository();
        oldestFirst.setCapacity(3);
        oldestFirst.setReverse(false);
        for (int i = 1; i <= 4; i++) {
            oldestFirst.add(exchange(i, 200));
        }
        System.out.println("oldestFirst=" + paths(oldestFirst.findAll()));

        var defaults = new InMemoryHttpExchangeRepository();
        for (int i = 1; i <= 101; i++) {
            defaults.add(exchange(i, 200));
        }
        List<HttpExchange> defaultSnapshot = defaults.findAll();
        System.out.println("defaultSize=" + defaultSnapshot.size());
        System.out.println("defaultNewest="
                + defaultSnapshot.get(0).getRequest().getUri().getPath());
        System.out.println("defaultOldest="
                + defaultSnapshot.get(defaultSnapshot.size() - 1)
                        .getRequest().getUri().getPath());

        var freshInstance = new InMemoryHttpExchangeRepository();
        System.out.println("freshInstanceSize=" + freshInstance.findAll().size());
    }

    private static HttpExchange exchange(int number, int status) {
        var request = new HttpExchange.Request(
                URI.create("http://localhost/sample/" + number),
                null,
                "GET",
                Map.of());
        var response = new HttpExchange.Response(status, Map.of());

        return new HttpExchange(
                Instant.parse("2025-01-01T00:00:00Z").plusSeconds(number),
                request,
                response,
                null,
                null,
                Duration.ofMillis(10));
    }

    private static List<String> paths(List<HttpExchange> exchanges) {
        return exchanges.stream()
                .map(item -> item.getRequest().getUri().getPath())
                .toList();
    }
}
```

Timestamp cố định và URI đánh số giúp đối chiếu kết quả; các đối tượng này không đại diện cho lưu lượng thật. `null` ở ví dụ thể hiện không cung cấp địa chỉ từ xa, principal và session; header là map rỗng. Trạng thái `500` chỉ được gán cho bản ghi số 2 để kiểm tra một phép lọc.

### 3.3. Chạy và đọc kết quả

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
initial=[/sample/3, /sample/2, /sample/1]
after4=[/sample/4, /sample/3, /sample/2]
oldSnapshot=[/sample/3, /sample/2, /sample/1]
retained5xx=1
snapshotUnmodifiable=true
oldestFirst=[/sample/2, /sample/3, /sample/4]
defaultSize=100
defaultNewest=/sample/101
defaultOldest=/sample/2
freshInstanceSize=0
```

Các kết quả cho thấy:

- Thêm bản ghi số 4 vào repository dung lượng 3 làm bản ghi số 1 không còn trong lần đọc mới.
- Đặt `setReverse(false)` trước khi thêm dữ liệu cho thứ tự cũ trước trong nhóm còn giữ lại; nó không làm tăng dung lượng.
- Repository mặc định giữ 100 bản ghi sau 101 lần thêm, nên bản ghi số 1 đã bị loại.
- Hai đối tượng repository được tạo riêng không tự chia sẻ dữ liệu.

Với bản triển khai Boot 3.3.0 dùng trong thí nghiệm, `findAll()` trả một bản chụp danh sách không cho sửa: lần thêm số 4 không làm biến `snapshot` tự cập nhật, và gọi `clear()` trên danh sách đó gây `UnsupportedOperationException`. Đây là hành vi của lớp cụ thể đã kiểm tra; không suy rộng thành hợp đồng bắt buộc của mọi `HttpExchangeRepository` tự triển khai.

## 4. Diễn giải thứ tự và bản chụp cho đúng

### 4.1. “Mới” theo lần thêm, không phải một phép sắp xếp mọi timestamp

Trong thí nghiệm, thứ tự thời gian và thứ tự thêm được cố ý cho trùng nhau. Repository 3.3.0 không thực hiện một truy vấn sắp xếp theo `getTimestamp()` sau mỗi lần thêm.

Với yêu cầu chạy đồng thời, yêu cầu bắt đầu trước có thể hoàn tất sau. `HttpExchange.timestamp` biểu diễn thời điểm bắt đầu trao đổi; vì vậy, đừng coi vị trí trong danh sách là bằng chứng tuyệt đối về thứ tự bắt đầu của mọi yêu cầu. Khi điều tra theo thời gian, hãy đọc trường timestamp và thông tin liên quan. [Ý nghĩa timestamp của `HttpExchange`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html#getTimestamp())

Đặt chiều liệt kê ngay khi tạo repository. Bài này không sử dụng `setReverse(...)` hoặc đổi dung lượng giữa lúc repository đã có dữ liệu; các setter không nên được xem như thao tác quản lý lịch sử có thể tùy ý hoán đổi khi đang chẩn đoán.

### 4.2. Một lần đọc cho một phép phân tích

Nếu cần vừa đếm, vừa lọc và vừa hiển thị cùng một tập bản ghi, hãy giữ kết quả của một lần `findAll()` vào biến rồi làm các phép phân tích trên biến đó, như `current` trong chương trình.

Đọc repository lần thứ nhất để lấy kích thước rồi đọc lần thứ hai để lấy nội dung có thể cho hai tập quan sát khác nhau khi ứng dụng tiếp tục nhận yêu cầu. Trong bản triển khai 3.3.0, thao tác thêm và chụp danh sách được đồng bộ hóa; điều đó bảo vệ thao tác nội bộ, nhưng không đóng băng ứng dụng hoặc tạo một giao dịch chung cho nhiều lần đọc.

Không dùng danh sách trả về như API xóa hoặc chỉnh sửa lịch sử. Nếu cần quản trị dữ liệu, hãy thiết kế một repository có hợp đồng phù hợp thay vì dựa vào khả năng sửa `List`.

## 5. Cấu hình một cửa sổ chẩn đoán trong ứng dụng web

Đoạn cấu hình sau được đặt trong một ứng dụng Spring Boot 3.3 dùng Spring MVC và đã có `spring-boot-starter-web` cùng `spring-boot-starter-actuator`. Đây là lớp cấu hình cho ứng dụng có sẵn, không phải chương trình `main` độc lập của phần 3.

Lưu lớp trong package được ứng dụng quét, chẳng hạn `example.diagnostics`:

```java
package example.diagnostics;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("local-http-diagnostics")
public class HttpExchangeDiagnosticsConfiguration {

    @Bean
    public HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(50);
        repository.setReverse(true);
        return repository;
    }
}
```

Profile giúp việc đăng ký bean gắn với một mục đích phát triển cụ thể. Nếu ứng dụng đã có repository bean, hãy chỉnh cấu hình bean đang được sử dụng; không thêm một bean thứ hai chỉ để thay dung lượng.

Đặt cấu hình dưới đây trong `src/main/resources/application-local-http-diagnostics.yml`:

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

Trong môi trường mẫu dùng cấu hình web mặc định và không có cổng quản trị riêng, địa chỉ bind này giới hạn máy chủ ở loopback. Nó không thay thế quy tắc xác thực/phân quyền nếu ứng dụng đã tích hợp bảo mật.

Với dự án web đang có Gradle Wrapper và Boot plugin, kích hoạt profile trên PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local-http-diagnostics"
```

Cấu hình chọn `time-taken` để bổ sung thời lượng, không yêu cầu các nhóm header, principal hoặc session ID. `recording.include` điều khiển trường tùy chọn được ghi, còn `endpoints.web.exposure.include` điều khiển endpoint được mở qua HTTP. [Các tùy chọn ghi nhận](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html), [Exposure và bảo mật endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Tạo yêu cầu đến một API có sẵn của ứng dụng, rồi đọc snapshot:

```powershell
$snapshot = Invoke-RestMethod http://127.0.0.1:8080/actuator/httpexchanges
$snapshot.exchanges | ForEach-Object {
    [pscustomobject]@{
        Method = $_.request.method
        Uri = $_.request.uri
        Status = $_.response.status
        TimeTaken = $_.timeTaken
    }
}
```

Đây là lệnh dành cho cấu hình đường dẫn/cổng mặc định; điều chỉnh URL nếu ứng dụng đã đổi chúng. Không có stdout cố định vì nội dung phụ thuộc lưu lượng của chính ứng dụng. Tên các trường được lấy từ cấu trúc phản hồi của endpoint. [HTTP Exchanges REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

## 6. Quy trình chẩn đoán với một tập dữ liệu hữu hạn

1. **Xác định đúng tiến trình.** Ghi nhận mình đang gọi bản sao ứng dụng nào và profile chẩn đoán đã hoạt động.
2. **Chọn câu hỏi cụ thể.** Ví dụ: lần gọi API vừa tái hiện có trả `500` không? Chỉ thu những trường cần để trả lời câu hỏi đó.
3. **Tái hiện lỗi rồi đọc sớm.** Tránh tạo hàng loạt yêu cầu không liên quan trước khi lấy bản chụp.
4. **Lưu một bản chụp cho việc phân tích.** Lọc theo đường dẫn, thời điểm và trạng thái trên cùng snapshot; nếu lưu ra tệp, xem xét dữ liệu nhạy cảm trước khi chia sẻ.
5. **Kết luận trong phạm vi bằng chứng.** “Trong snapshot này có một phản hồi 500” là kết luận hợp lệ; “hệ thống chỉ từng có một lỗi” thì vượt quá dữ liệu.
6. **Kết thúc phiên quan sát.** Khi đã giải quyết mục tiêu phát triển, bỏ profile chẩn đoán trong lần chạy tiếp theo nếu không còn cần.

Trong chương trình phần 3, `retained5xx=1` chỉ đếm lỗi trong ba bản ghi đang giữ. Nó không phải bộ đếm lỗi tích lũy và không thể dùng làm tỷ lệ lỗi của toàn bộ thời gian ứng dụng hoạt động. Một đợt yêu cầu thành công mới có thể làm lỗi cũ biến mất khỏi repository.

Các lần đọc endpoint và lưu lượng quản trị cũng có thể đi qua hạ tầng ghi nhận trong ứng dụng. Khi dung lượng nhỏ, hãy tính đến chúng thay vì giả định mọi vị trí đều dành cho API nghiệp vụ. Không liên tục đọc endpoint rồi coi mỗi lần đọc là một quan sát không ảnh hưởng đến các bản ghi về sau.

## 7. Những giới hạn làm thay đổi kết luận

| Giới hạn | Hệ quả khi điều tra |
| --- | --- |
| Số lượng bản ghi hữu hạn | Không thấy một yêu cầu không chứng minh yêu cầu đó chưa từng xảy ra |
| Dữ liệu nằm trong đối tượng bộ nhớ | Khi đối tượng bị thay thế hoặc tiến trình khởi động lại, repository mới không tự có lịch sử cũ |
| Mỗi tiến trình tạo repository riêng | Đọc một bản sao không cho lịch sử đầy đủ của các bản sao khác |
| Trường ghi nhận được lựa chọn | Thiếu header, principal hoặc session có thể do cấu hình thu thập |
| Không có kho lịch sử bền vững | Không phù hợp để tự nhận là bằng chứng kiểm toán dài hạn |

Đừng chỉ tăng `capacity` khi thật sự cần lịch sử lâu dài hoặc liên kết hành trình qua nhiều dịch vụ. Những yêu cầu đó cần thiết kế lưu trữ/quan sát tương ứng. Spring Boot nêu giải pháp tracing hoặc observability phù hợp cho production, và cũng cho phép tự triển khai `HttpExchangeRepository`. [Hướng dẫn phạm vi sử dụng](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

Dữ liệu được trình bày qua endpoint là thông tin mô tả trao đổi như URI, phương thức, trạng thái và các trường được chọn; đừng kỳ vọng đây là bản sao đầy đủ của nội dung yêu cầu/phản hồi (request/response body). Schema của endpoint không cung cấp trường body. [Cấu trúc dữ liệu HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

Các thông tin nhạy cảm cần được xét ngay cả với cửa sổ nhỏ. URI có thể chứa tham số truy vấn nhạy cảm; chọn không ghi header không tự làm URI an toàn để chia sẻ. Tăng dung lượng hoặc mở thêm nhóm dữ liệu chỉ sau khi biết thông tin ấy phục vụ câu hỏi chẩn đoán nào.

## 8. Bài tập tự kiểm tra

1. Giữ dung lượng 3 nhưng thêm các bản ghi 1 đến 7. Với thứ tự mặc định, ba đường dẫn cuối cùng là gì?
2. Vì sao bản ghi lỗi có thể biến mất dù bạn không gọi API xóa nào?
3. Nếu có ba bản sao ứng dụng và đọc được 50 bản ghi từ một bản sao, có thể kết luận hệ thống đã xử lý đúng 50 yêu cầu không?
4. Nếu muốn thời hạn lưu tối thiểu 10 phút bất kể lưu lượng, chỉ tăng dung lượng lên 600 đã đủ chưa?

Đối chiếu: (1) `/sample/7`, `/sample/6`, `/sample/5`; (2) lượt thêm mới làm bản ghi cũ bị loại khi đầy; (3) không, dữ liệu vừa bị giới hạn số lượng vừa chỉ thuộc repository được đọc; (4) chưa, số bản ghi và số phút không có quan hệ cố định khi tốc độ thêm thay đổi.
