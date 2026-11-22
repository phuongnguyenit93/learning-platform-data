# Phân biệt lịch sử trao đổi HTTP với log truy cập, metrics và distributed tracing

## Một yêu cầu HTTP có thể để lại nhiều loại bằng chứng

Giả sử khách hàng báo rằng một lần gọi API đặt hàng bị chậm. Bạn có thể nhìn thấy mã phản hồi và thời gian xử lý trong lịch sử HTTP, một dòng trong log truy cập, độ trễ tăng trên biểu đồ metrics và một trace đi qua các dịch vụ đặt hàng, kho và thanh toán.

Những dữ liệu này liên quan tới cùng hoạt động nhưng giữ lại **các góc nhìn khác nhau**. Bật một tính năng không đồng nghĩa đã có đầy đủ ba tính năng còn lại.

Trong Spring Boot 3.3, cần nhận diện bốn khái niệm:

- **Lịch sử trao đổi HTTP (HTTP exchanges)**: các bản ghi yêu cầu–phản hồi được lưu trong một `HttpExchangeRepository`, có thể đọc qua endpoint `httpexchanges`.
- **Log truy cập (access log)**: các bản ghi truy cập được máy chủ HTTP hoặc proxy phát ra theo định dạng và chính sách lưu trữ đã cấu hình.
- **Số liệu đo lường (metrics)**: số đếm, thời gian và các phân phối được tổng hợp theo những nhãn xác định.
- **Truy vết phân tán (distributed tracing)**: các đơn vị công việc được liên kết thành dấu vết để theo dõi đường đi qua nhiều thành phần hoặc dịch vụ.

Hãy bắt đầu bằng câu hỏi bạn cần trả lời, rồi chọn bằng chứng phù hợp.

## 1. So sánh theo câu hỏi, đơn vị dữ liệu và phạm vi

| Nguồn dữ liệu | Câu hỏi phù hợp | Đơn vị dữ liệu | Phạm vi thường thấy | Giới hạn cần nhớ |
| --- | --- | --- | --- | --- |
| HTTP exchanges | “Ứng dụng vừa nhận những yêu cầu nào và trả lời ra sao?” | Một cặp yêu cầu–phản hồi | Một ứng dụng/instance, tùy repository | Bộ nhớ đệm có giới hạn không phải lịch sử đầy đủ |
| Access log | “Tại điểm tiếp nhận này, yêu cầu nào đã đi qua, trả mã gì, mất bao lâu?” | Một bản ghi truy cập theo định dạng log | Proxy, máy chủ HTTP hoặc tập log đã thu gom | Không tự mô tả các bước xử lý bên trong |
| Metrics | “Lưu lượng, tỷ lệ lỗi và độ trễ thay đổi thế nào trong một khoảng thời gian?” | Số đo/chuỗi thời gian theo bộ nhãn | Instance hoặc toàn dịch vụ khi tổng hợp đúng | Không giữ nguyên danh tính từng yêu cầu |
| Distributed tracing | “Một lần xử lý đã đi qua đâu và chậm ở bước nào?” | Trace gồm các span có liên kết | Những thành phần có instrumentation và truyền ngữ cảnh | Lấy mẫu hoặc thiếu instrumentation có thể làm thiếu dấu vết |

`Instrumentation` là mã hoặc thư viện được gắn vào điểm xử lý để phát sinh dữ liệu quan sát. Một thành phần không được đo sẽ tạo ra khoảng trống; không có dữ liệu không đồng nghĩa không có hoạt động.

Ví dụ chọn nguồn:

- Muốn biết p99 của API trong 15 phút: bắt đầu từ metrics có dữ liệu phân phối phù hợp.
- Muốn tìm mã phản hồi của một lần gọi cụ thể: tra access log hoặc bản ghi HTTP nếu còn được lưu.
- Muốn biết vì sao lần gọi đó chậm ở dịch vụ thanh toán: tìm trace và các log liên quan.
- Muốn kiểm tra nhanh header của một yêu cầu vừa hoàn tất trong môi trường phát triển: HTTP exchanges thường thuận tiện.

p99 là phân vị 99 của phân phối độ trễ, không phải thời gian của một yêu cầu có “mã p99”.

## 2. HTTP exchanges: nhìn lại các cặp yêu cầu–phản hồi gần đây

### Bản ghi giữ những gì?

Mô hình `HttpExchange` mô tả thời điểm bắt đầu, yêu cầu, phản hồi, thời gian xử lý và một số thông tin bổ sung tùy cấu hình, như danh tính (principal) hoặc phiên (session). Yêu cầu có thể gồm method, URI và các header được chọn; phản hồi có status và các header được chọn.

Ví dụ trích một bản ghi tổng hợp để đọc cấu trúc:

```json
{
  "exchanges": [
    {
      "timestamp": "2024-01-01T00:00:03Z",
      "request": {
        "uri": "https://example.test/orders/104",
        "method": "GET",
        "headers": {}
      },
      "response": {
        "status": 404,
        "headers": {}
      },
      "timeTaken": "PT0.1S"
    }
  ]
}
```

`PT0.1S` là biểu diễn thời lượng 0,1 giây. Không hiểu nó là một timestamp hoặc là 0,1 mili giây. Tập trường thực tế còn tùy cấu hình ghi nhận. Mô hình chuẩn này không cung cấp bản sao mặc định của toàn bộ request body, response body, câu SQL và stack trace. [Spring Boot 3.3: API httpexchanges](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html).

Thời gian ở lớp ghi nhận HTTP cũng không mặc nhiên gồm mọi thời gian mà người dùng cảm nhận: DNS, thiết lập kết nối, thời gian ở CDN/proxy và truyền trên mạng nằm ở các điểm quan sát khác.

### Repository quyết định việc lưu, endpoint chỉ cung cấp cách đọc

Spring Boot kích hoạt việc ghi nhận qua cấu hình tự động khi có bean `HttpExchangeRepository` phù hợp. Một cấu hình phục vụ phát triển có thể là:

```java
package example.observability;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HttpExchangeConfiguration {

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(100);
        return repository;
    }
}
```

Đây là đoạn cấu hình thêm vào ứng dụng Spring Boot có Actuator và web stack tương ứng; không phải chương trình Java độc lập.

`InMemoryHttpExchangeRepository` mặc định giữ **100 cặp trao đổi gần nhất**. Spring khuyến nghị dùng loại repository đơn giản này cho phát triển; nhu cầu môi trường vận hành cần giải pháp quan sát phù hợp hoặc một repository được thiết kế theo yêu cầu lưu trữ. [Spring Boot 3.3: Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

Ba việc cần tách biệt:

1. **Ghi nhận**: có repository và cơ chế recording đang hoạt động.
2. **Lưu giữ**: repository giữ được bao nhiêu, trong bao lâu, ở đâu.
3. **Truy cập qua HTTP**: endpoint có được expose và người gọi có quyền đọc hay không.

Chỉ expose `httpexchanges` không tự tạo một kho lịch sử. Ngược lại, không cho đọc endpoint từ xa cũng không nhất thiết tắt việc ghi. Thuộc tính `management.httpexchanges.recording.enabled=false` điều khiển recording; `management.httpexchanges.recording.include` chọn loại thông tin được ghi. Chính sách exposure và phân quyền là lớp riêng.

### Các giới hạn của bộ đệm trong bộ nhớ

Với repository trong bộ nhớ:

- Khởi động lại tiến trình làm mất các bản ghi đang giữ.
- Mỗi instance có bộ đệm riêng, không tự hợp nhất thành lịch sử của toàn cụm.
- Bản ghi cũ bị loại khi vượt sức chứa.
- Sức chứa tính theo số bản ghi, không phải một cửa sổ cố định như “10 phút”.
- Số bản ghi không phải giới hạn byte cứng: header và URI dài vẫn làm tăng chi phí bộ nhớ.

Nếu có 100 chỗ và tốc độ ghi nhận khoảng 200 lượt mỗi giây, lượng lịch sử có thể chỉ tương ứng khoảng **0,5 giây** trong điều kiện đó. Đây là ước lượng theo lưu lượng, không phải cam kết thời gian lưu.

Đường đọc `httpexchanges` cũng có thể tạo thêm một trao đổi được ghi sau khi yêu cầu đọc hoàn tất. Không dựa vào giả định rằng thao tác quan sát luôn nằm ngoài tập dữ liệu đang quan sát.

## 3. Access log: ghi nhận lưu lượng tại một điểm tiếp nhận

### Log truy cập khác log nghiệp vụ

Một access log thường ghi method, đường dẫn, status, số byte và thời gian ở máy chủ/proxy đó. Nó không giống dòng log do lớp nghiệp vụ chủ động viết như “đơn hàng đã được xác nhận”.

Với embedded Tomcat, ví dụ cấu hình trong ứng dụng Spring Boot:

```yaml
server:
  tomcat:
    basedir: ./runtime-tomcat
    accesslog:
      enabled: true
      pattern: '%t method=%m path=%U status=%s bytes=%b elapsed_us=%D'
```

Đây là cấu hình dành cho **Tomcat**, không áp dụng nguyên xi cho Jetty, Undertow hoặc Reactor Netty. Đặt base directory rõ ràng giúp xác định nơi lưu; ví dụ trên đưa log vào thư mục `logs` dưới `runtime-tomcat`. Việc xoay vòng, thu gom và lưu dài hạn vẫn cần chính sách riêng. [Spring Boot 3.3: Configure Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-access-logs).

Trong mẫu Tomcat này, `%U` là đường dẫn, `%s` là status, `%b` là số byte phần thân trả về hoặc `-` khi bằng 0, còn `%D` dùng **micro giây**. Không đọc `elapsed_us=100000` thành 100.000 mili giây; nó là 100 mili giây. Không suy đơn vị của server khác từ cùng một ký hiệu. [Tomcat 10.1: Access Log Valve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html#Access_Log_Valve).

### Điểm quan sát quyết định điều log chứng minh được

Một yêu cầu có thể đi qua:

```text
Trình duyệt -> CDN/proxy -> Tomcat -> Spring Security -> controller -> dịch vụ khác
```

Nếu CDN trả lỗi trước khi chuyển tới ứng dụng, Tomcat có thể không có bản ghi tương ứng. Nếu ứng dụng trả 200 nhưng kết nối phía proxy gặp lỗi, status phía người dùng thấy có thể khác status ứng dụng đã ghi.

Do đó cần biết log đến từ đâu, timestamp biểu diễn thời điểm nào và thời lượng bao gồm đoạn xử lý nào. Không cộng số dòng ở proxy với số dòng ở ứng dụng rồi coi đó là số yêu cầu duy nhất; cùng một lần gọi có thể xuất hiện ở cả hai nơi.

Access log có thể được giữ lâu hơn bộ đệm HTTP nếu có đường lưu bền vững và quy trình thu gom. Nhưng “là log” không tự bảo đảm đầy đủ hoặc bất biến: tệp có thể bị xoay vòng, mất khi container bị thay thế, bị lọc hoặc không được chuyển tới kho tập trung.

Các chi tiết bị thiếu trong định dạng cũng không thể truy vấn lại bằng cách đổi log level sau sự cố.

## 4. Metrics: tổng hợp để nhìn xu hướng và quy mô

### Từ nhiều yêu cầu thành một nhóm số đo

Spring Boot sử dụng Micrometer cho metrics. Với instrumentation HTTP mặc định tương ứng, tên meter phía server thường là `http.server.requests`; các bộ nhãn chia số liệu theo những chiều như method, mẫu đường dẫn (route) hoặc status. [Spring Boot 3.3: HTTP metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

Một timer có thể cung cấp số lần ghi nhận và tổng thời gian, cùng những số liệu bổ sung tùy cấu hình/backend. Ví dụ đã ghi bốn thời lượng `10, 20, 70, 100 ms`:

```text
count = 4
total = 200 ms
mean  = 200 / 4 = 50 ms
```

Từ các số này, bạn biết mức trung bình của tập đã ghi. Bạn không biết yêu cầu nào của khách hàng nào mất 100 ms và cũng không tính được p99 đáng tin chỉ từ count với total. Histogram hoặc phân vị cần cấu hình và cách tổng hợp phù hợp. [Micrometer: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Một metric có thể được cập nhật khi yêu cầu hoàn tất rồi được đọc/đẩy theo chu kỳ. Nó không phải danh sách JSON gồm tất cả yêu cầu. Backend chuỗi thời gian giúp xem biến động lâu dài, nhưng phạm vi dữ liệu vẫn phụ thuộc instrumentation, bộ lọc, chu kỳ xuất dữ liệu và thời gian lưu.

### Nhãn phải có số lượng giá trị được kiểm soát

Hai yêu cầu:

```text
GET /orders/101
GET /orders/102
```

thường nên được tổng hợp theo route `/orders/{id}`, thay vì tạo một chuỗi thời gian riêng cho từng mã đơn.

Số lượng tổ hợp nhãn khác nhau được gọi là **cardinality**. Đưa `requestId`, `traceId`, địa chỉ email hoặc URI có vô số mã vào nhãn có thể làm số chuỗi thời gian tăng rất nhanh. Những định danh cần thiết cho từng trường hợp nên đặt trong dữ liệu chi tiết có chính sách phù hợp, không biến chúng thành nhãn metrics mặc định.

Metrics có ít nhãn không có nghĩa là “thiếu chức năng”. Chính việc tổng hợp theo các nhóm có kiểm soát giúp trả lời câu hỏi quy mô lớn với chi phí hợp lý.

### Tỷ lệ lỗi và độ trễ cần cùng phạm vi dữ liệu

Nếu muốn tính tỷ lệ 5xx, phải lấy số yêu cầu 5xx chia cho tổng yêu cầu trong **cùng khoảng thời gian, cùng dịch vụ và cùng tập route/instance đã chọn**.

Cần xác định thêm:

- Chính sách coi 4xx có là lỗi theo mục tiêu mức độ dịch vụ (SLO) hay không.
- Cách xử lý bộ đếm bị reset khi tiến trình khởi động lại.
- Có bao gồm health check, yêu cầu Actuator và lưu lượng nội bộ hay không.
- Số liệu đến từ toàn bộ instance hay chỉ một instance.
- Bộ lọc hoặc dữ liệu xuất thiếu có làm thay đổi mẫu quan sát không.

Không lấy trung bình đơn giản của hai p99 hoặc hai giá trị trung bình khi số yêu cầu hai nhóm khác nhau. Với trung bình toàn bộ, cần tổng thời gian chia tổng số lượt; với phân vị toàn bộ, cần dữ liệu phân phối có thể tổng hợp theo cơ chế đã chọn.

## 5. Distributed tracing: liên kết các bước của một lần xử lý

### Trace và span có vai trò gì?

Một **span** mô tả một đơn vị công việc có điểm bắt đầu/kết thúc và ngữ cảnh liên quan. Một **trace** liên kết các span trong đường xử lý, thường bằng trace ID cùng quan hệ cha–con hoặc các liên kết phù hợp.

Ví dụ sơ đồ khái niệm của một lần đặt hàng:

```text
Trace T
└─ API đặt hàng
   ├─ gọi dịch vụ kho
   │  └─ truy vấn dữ liệu tồn kho
   └─ gọi dịch vụ thanh toán
      └─ gọi cổng thanh toán
```

Sơ đồ chỉ xuất hiện đầy đủ nếu những điểm cần quan sát thực sự được gắn công cụ đo và truyền ngữ cảnh. Bật tracing ở API đầu vào không tự tạo span cho mọi câu SQL, mọi phương thức Java hoặc mọi dịch vụ bên ngoài. [OpenTelemetry: Traces và Spans](https://opentelemetry.io/docs/concepts/signals/traces/).

Từ trace, bạn có thể tìm bước chậm, các lần retry và mối liên hệ giữa lời gọi vào với lời gọi ra. Nếu hai nhánh chạy song song, không cộng thời gian tất cả span rồi coi đó là thời gian người dùng chờ: các khoảng có thể chồng lên nhau.

### Phải truyền ngữ cảnh qua ranh giới

Để nối được các span qua mạng, bên gọi cần truyền ngữ cảnh và bên nhận cần trích xuất nó theo định dạng tương thích. Tương tự, khi chuyển sang hàng đợi hoặc tác vụ bất đồng bộ, cần giữ hoặc liên kết ngữ cảnh theo cơ chế của thư viện.

Chỉ đặt một chuỗi cùng tên `traceId` vào log ở nhiều dịch vụ không tự tạo trace có quan hệ hợp lệ. `requestId` của ứng dụng cũng không mặc nhiên là trace ID. [OpenTelemetry: Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

Trong Spring Boot 3.3, tracing cần các dependency và cấu hình tương ứng với Micrometer Tracing cùng tracer/exporter. Với HTTP client, nên sử dụng các builder do Boot tự cấu hình để nhận instrumentation và truyền ngữ cảnh tương ứng; tự tạo client ngoài đường cấu hình đó có thể làm đứt trace.

### Lấy mẫu làm trace khác bộ đếm lưu lượng

Tracing thường dùng **lấy mẫu (sampling)** để giới hạn lượng dữ liệu. Cấu hình mặc định được tài liệu Spring Boot 3.3 nêu là lấy mẫu 10% cho tracing; chính sách thực tế còn phải kiểm tra trong hệ thống và đường truyền ngữ cảnh đang dùng. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Không có trace của một yêu cầu có thể do không được lấy mẫu, thiếu instrumentation, đứt ngữ cảnh, lỗi xuất dữ liệu hoặc hết thời gian lưu. Nó không chứng minh yêu cầu chưa xảy ra.

Việc một yêu cầu không được xuất thành trace cũng không có nghĩa số đo HTTP phải bỏ qua yêu cầu đó. Đây là hai tín hiệu với cơ chế thu thập khác nhau. Không dùng số trace đang nhìn thấy như tổng lưu lượng, rồi tính tỷ lệ lỗi toàn hệ thống mà bỏ qua cách lấy mẫu.

Tăng sampling lên 100% trong thử nghiệm giúp dễ quan sát hơn nhưng vẫn không bảo đảm không mất dữ liệu ở exporter/backend. Quyết định cho môi trường vận hành cần xét lưu lượng, chi phí và mục đích điều tra.

## 6. Thí nghiệm Java: hai bản ghi gần nhất không phải tổng của bốn lượt

Thí nghiệm dưới đây dùng trực tiếp `InMemoryHttpExchangeRepository` và Micrometer `SimpleMeterRegistry`. Nó tạo dữ liệu tổng hợp và ghi các thời lượng đã cho, **không mở máy chủ HTTP, không gửi bốn request thật và không tự tạo access log hay trace**.

Các đầu vào:

| Yêu cầu mô phỏng | Status | Thời lượng |
| --- | --- | --- |
| `/orders/101` | 200 | 10 ms |
| `/orders/102` | 200 | 20 ms |
| `/orders/103` | 500 | 70 ms |
| `/orders/104` | 404 | 100 ms |

Repository chỉ được cấp hai chỗ; metrics được ghi cho cả bốn lượt.

Tạo một thư mục thử riêng với `pom.xml` sau để có dependency Spring Boot 3.3.x và Micrometer. Đây là chương trình Java thông thường, không cần lớp `@SpringBootApplication`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>http-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
    </dependencies>
</project>
```

Lưu mã dưới đây tại `src/main/java/HttpSignalsDemo.java`:

```java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public class HttpSignalsDemo {
    public static void main(String[] args) {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(2);

        var registry = new SimpleMeterRegistry();
        try {
            int[] statuses = {200, 200, 500, 404};
            long[] durationsMs = {10, 20, 70, 100};
            Instant start = Instant.parse("2024-01-01T00:00:00Z");

            for (int i = 0; i < statuses.length; i++) {
                var request = new HttpExchange.Request(
                        URI.create("https://example.test/orders/" + (101 + i)),
                        null, "GET", Map.of());
                var response = new HttpExchange.Response(statuses[i], Map.of());
                var exchange = new HttpExchange(
                        start.plusSeconds(i), request, response,
                        null, null, Duration.ofMillis(durationsMs[i]));
                repository.add(exchange);

                Timer.builder("demo.http.requests")
                        .tags("method", "GET", "uri", "/orders/{id}",
                                "status", Integer.toString(statuses[i]))
                        .register(registry)
                        .record(Duration.ofMillis(durationsMs[i]));
            }

            System.out.println("exchanges.retained=" + repository.findAll().size());
            for (HttpExchange exchange : repository.findAll()) {
                System.out.println("exchange=" + exchange.getRequest().getUri().getPath()
                        + " status=" + exchange.getResponse().getStatus());
            }

            var timers = registry.find("demo.http.requests").timers();
            long count = timers.stream().mapToLong(Timer::count).sum();
            double totalMs = timers.stream()
                    .mapToDouble(timer -> timer.totalTime(TimeUnit.MILLISECONDS)).sum();
            long serverErrors = timers.stream()
                    .filter(timer -> timer.getId().getTag("status").startsWith("5"))
                    .mapToLong(Timer::count).sum();

            System.out.println("metrics.count=" + count);
            System.out.printf(Locale.ROOT, "metrics.total.ms=%.1f%n", totalMs);
            System.out.printf(Locale.ROOT, "metrics.mean.ms=%.1f%n", totalMs / count);
            System.out.println("metrics.5xx=" + serverErrors);
            System.out.printf(Locale.ROOT, "metrics.5xx.percent=%.1f%n",
                    100.0 * serverErrors / count);
        } finally {
            registry.close();
        }
    }
}
```

Với JDK 17 trở lên và Maven, biên dịch và gom dependency:

```bash
mvn -q compile dependency:copy-dependencies
```

Chạy trên Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' HttpSignalsDemo
```

Trên Linux/macOS, dùng dấu `:` để ngăn cách các phần classpath:

```bash
java -cp 'target/classes:target/dependency/*' HttpSignalsDemo
```

Maven cần truy cập được các dependency nếu chúng chưa nằm trong cache. Các lệnh này chỉ dành cho dự án thử vừa tạo.

Stdout chính xác:

```text
exchanges.retained=2
exchange=/orders/104 status=404
exchange=/orders/103 status=500
metrics.count=4
metrics.total.ms=200.0
metrics.mean.ms=50.0
metrics.5xx=1
metrics.5xx.percent=25.0
```

Cách giải thích:

- Repository giữ hai lượt gần nhất và trả chúng theo thứ tự mới nhất trước trong cấu hình mặc định.
- Hai bản ghi bị loại khỏi repository không làm các phép đo đã ghi trong registry tự biến mất.
- Tổng là 200 ms và trung bình là 50 ms vì metrics đang tổng hợp cả bốn lượt.
- Có một lượt 5xx trên bốn lượt, nên tỷ lệ 5xx của tập đầu vào là 25%.
- Nếu chỉ nhìn hai bản ghi còn giữ, bạn thấy một lượt 5xx trên hai lượt, tức 50% **của tập hai lượt gần nhất**. Nó không đại diện cho cả bốn lượt.
- 404 không được đếm là 5xx. Nếu chính sách cần theo dõi 4xx, phải định nghĩa nhóm đó riêng.

Tên `demo.http.requests` là timer do chương trình chủ động tạo để minh họa, không phải khẳng định đã bật instrumentation HTTP tự động của Boot. Tag `uri=/orders/{id}` thể hiện cách nhóm route; URI chi tiết vẫn nằm trong các bản ghi exchange đang giữ.

Chương trình cố ý ghi thời lượng định trước thay vì đo `Thread.sleep`, để kết quả số học có thể tái lập. Không dùng các số này như benchmark hiệu năng của repository hoặc ứng dụng web.

## 7. Kết hợp các tín hiệu khi điều tra một sự cố

Giả sử metrics báo độ trễ route `/checkout` tăng, nhưng chỉ vài khách hàng phản ánh lỗi. Một cách điều tra có căn cứ là:

1. Chọn khoảng thời gian và xác định service, route, instance bị ảnh hưởng từ metrics.
2. Tìm các yêu cầu cụ thể trong access log, đối chiếu status, thời gian và mã liên kết nếu có.
3. Dùng trace ID để mở trace đã được lưu, xem bước nào chậm hoặc có retry.
4. Đọc log nghiệp vụ liên quan tới span/trace đó để hiểu ngữ cảnh lỗi.
5. Nếu đang tái hiện trong môi trường phát triển, dùng HTTP exchanges để xem thông tin cặp yêu cầu–phản hồi còn trong repository.

Mỗi bước bổ sung bằng chứng; một biểu đồ tăng không tự chứng minh nguyên nhân nằm ở cơ sở dữ liệu. Một span chậm cũng cần được đọc trong bối cảnh những đoạn chưa được đo.

Để liên kết được, cần thống nhất timestamp/múi giờ, định danh service và instance, cùng cách truyền mã liên kết. Spring Boot có hỗ trợ đưa trace/span ID vào log khi dùng Micrometer Tracing, nhưng không nên mặc định mọi access log ở proxy hoặc server đã có cùng trường đó.

Ngữ cảnh chẩn đoán của bộ ghi log (MDC) và ngữ cảnh truy vết cũng không tự vượt qua mọi ranh giới luồng hoặc executor ngoài cấu hình được hỗ trợ. Khi thấy log “mất trace ID”, kiểm tra đường truyền ngữ cảnh, thay vì tự chèn ngẫu nhiên một ID mới để các dòng trông giống nhau.

### Vì sao số lượng và thời lượng giữa các nguồn có thể lệch?

| Tình huống | Hệ quả có thể thấy |
| --- | --- |
| Request bị chặn ở proxy | Proxy có log, ứng dụng không có exchange tương ứng |
| Bộ đệm HTTP đã đầy | Metrics vẫn phản ánh lượt đã ghi nhưng exchange cũ không còn |
| Tracing lấy mẫu | Có log/metric nhưng không thấy trace được lưu |
| Lời gọi được retry | Một hành động người dùng có thể tạo nhiều request và span |
| Dữ liệu đọc từ các instance khác nhau | Bộ đệm và bộ đếm cục bộ không khớp |
| Hai nguồn đo hai đoạn xử lý khác nhau | Thời lượng khác nhau dù cùng một lần gọi |
| Collector/exporter hoặc đường thu gom lỗi | Dữ liệu ở backend thiếu so với những gì đã xảy ra trong tiến trình |

Trước khi kết luận nguồn nào “sai”, kiểm tra phạm vi, điểm quan sát, cửa sổ thời gian và chính sách lưu/lấy mẫu của từng nguồn.

## 8. Lịch sử HTTP không tự trở thành sổ kiểm toán

Nhóm kiến thức này liên quan đến HTTP và kiểm toán, nhưng một request trả `200` không đủ để chứng minh một thay đổi nghiệp vụ đã được thực hiện đúng.

Ví dụ “ai đã đổi hạn mức của tài khoản nào, từ bao nhiêu sang bao nhiêu, kết quả ra sao?” cần một sự kiện nghiệp vụ có chủ thể, đối tượng, hành động, thời điểm và kết quả rõ ràng. Một dòng `POST /limits -> 200` chưa cung cấp đầy đủ điều đó.

Spring Boot có cơ chế auditing riêng với `AuditEventRepository`. Khi được cấu hình phù hợp cùng Spring Security, các sự kiện như xác thực thành công/thất bại hoặc bị từ chối truy cập có thể được công bố; sự kiện nghiệp vụ cần được phát sinh theo thiết kế của ứng dụng. Đây không phải chức năng tự sinh từ `HttpExchangeRepository`. [Spring Boot 3.3: Auditing](https://docs.spring.io/spring-boot/3.3/reference/actuator/auditing.html).

Nếu cần bằng chứng lưu dài hạn, phải thiết kế khả năng lưu bền vững, kiểm soát sửa/xóa, quyền truy cập và thời gian lưu tương ứng. Một bộ đệm giữ các bản ghi gần nhất, tệp log thông thường hoặc trace lấy mẫu không tự đáp ứng những yêu cầu đó.

## 9. Kiểm soát dữ liệu và chi phí theo từng nguồn

| Nguồn | Rủi ro thường gặp | Hướng kiểm soát |
| --- | --- | --- |
| HTTP exchanges | URI/header/principal có thể nhạy cảm; bộ đệm tăng theo kích thước bản ghi | Chọn dữ liệu được ghi, giới hạn sức chứa và quyền đọc endpoint |
| Access log | Query string, cookie hoặc header được thêm vào pattern có thể làm lộ dữ liệu; tệp tăng liên tục | Giới hạn trường, xoay vòng, thu gom và lưu theo chính sách |
| Metrics | Nhãn có quá nhiều giá trị làm bùng nổ chuỗi thời gian; định danh cá nhân trong tag | Dùng nhóm giá trị có kiểm soát, tránh định danh từng request/người dùng |
| Tracing | Span attribute/baggage có thể mang dữ liệu nhạy cảm; khối lượng trace lớn | Chọn thuộc tính, truyền ngữ cảnh có chủ đích, lấy mẫu và bảo vệ backend |

Không mặc định cơ chế che giá trị cấu hình của Actuator sẽ che mọi URI, log hoặc thuộc tính span. Đặc biệt, một token trong query string có thể lọt vào nhiều nguồn ngay cả khi không ghi header Authorization.

Expose một endpoint quản trị là quyết định về bề mặt truy cập, không phải cách làm dữ liệu tự an toàn. Việc chỉ cho phép người có quyền đọc và giảm dữ liệu ngay tại nơi thu thập bổ sung cho nhau.

## 10. Tự kiểm tra khả năng chọn bằng chứng

1. Cần biết tổng tỷ lệ 5xx của cả dịch vụ trong 30 phút. Vì sao 100 exchange cuối của một instance chưa đủ?
2. Khách hàng có một mã yêu cầu và thời điểm cụ thể. Nên tìm đâu để đối chiếu lần gọi đó, rồi tìm đâu để xem đường đi qua các dịch vụ?
3. Không thấy trace của một request nhưng access log có status 500. Những khả năng nào cần kiểm tra?
4. Trong thí nghiệm, vì sao metrics có count bằng 4 còn repository chỉ có 2 bản ghi?
5. Vì sao không nên đặt trace ID vào tag của `http.server.requests`?
6. Khi cần biết ai thay đổi một quyền nghiệp vụ, vì sao status HTTP 200 và một trace thành công vẫn chưa thay thế sự kiện kiểm toán?

Bạn đã phân biệt được bốn nguồn khi có thể nêu rõ **đơn vị dữ liệu, điểm quan sát, cách lưu giữ và câu hỏi mà nguồn đó trả lời**, đồng thời biết ghép chúng lại mà không biến dữ liệu thiếu hoặc dữ liệu tổng hợp thành bằng chứng chi tiết chưa từng được ghi.
