# Supplier<T>: tạo dữ liệu không nhận đầu vào

Trong Spring Cloud Function, **Supplier<T>** mô tả một nguồn tạo hoặc cung cấp dữ liệu. Mỗi khi nguồn được kích hoạt, ứng dụng gọi phương thức **get()** để lấy một giá trị kiểu **T**. Hàm không nhận đối số nghiệp vụ từ phía người gọi, vì vậy cùng một logic có thể được kích hoạt bằng HTTP, lịch phát sự kiện hoặc một môi trường serverless thông qua adapter phù hợp.

Bài này thuộc chương **Mô hình hàm** của **SPRING_CLOUD_FUNCTION**. Trọng tâm là cách thiết kế, đăng ký, thực thi và kiểm thử một Supplier độc lập với giao thức gọi; sau đó kết nối nguồn dữ liệu đó với FunctionCatalog, composition, message và các cơ chế triển khai.

## 1. Supplier<T> là gì?

**java.util.function.Supplier<T>** là một functional interface có duy nhất một phương thức trừu tượng:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

- **Không có tham số đầu vào:** lời gọi là **get()**, không phải **apply(input)**.
- **Có một kết quả kiểu T:** chẳng hạn String, đối tượng Java, Message<T> hoặc một publisher phản ứng như Flux<T>.
- **Có thể được gọi nhiều lần:** mỗi lời gọi có thể tạo kết quả mới hoặc đọc lại dữ liệu hiện tại, tùy cách triển khai.
- **Không đồng nghĩa với không có phụ thuộc:** Supplier vẫn có thể dùng Clock, repository, cấu hình hoặc một dịch vụ để tính kết quả. Điều không tồn tại là *đối số nghiệp vụ đưa vào get()*.

Ví dụ Java thuần:

~~~java
Supplier<String> greeting = () -> "Xin chào Spring Cloud Function";

String first = greeting.get();
String second = greeting.get();
~~~

Trong ví dụ này, **get()** trả về cùng một chuỗi. Với Supplier tạo thời điểm, mã định danh hoặc ảnh chụp trạng thái hệ thống, hai lần gọi có thể trả về dữ liệu khác nhau.

| Mô hình hàm | Chữ ký | Vai trò chính | Ví dụ |
| --- | --- | --- | --- |
| **Supplier<T>** | () → T | Tạo hoặc cung cấp dữ liệu | Tạo heartbeat định kỳ |
| **Function<I, O>** | I → O | Biến đổi dữ liệu đầu vào | Chuyển đơn hàng thành hóa đơn |
| **Consumer<T>** | T → void | Tiếp nhận và xử lý dữ liệu | Ghi một sự kiện vào hệ thống lưu trữ |

Một yêu cầu cần nội dung của request, chẳng hạn tìm đơn hàng theo ID do khách gửi, thường phù hợp hơn với **Function<Request, Response>**. Supplier phù hợp khi nguồn tự biết phải tạo hoặc lấy dữ liệu gì.

## 2. Supplier trong Spring Cloud Function vận hành thế nào?

Spring Cloud Function nhận diện các bean chức năng kiểu **Supplier**, **Function** và **Consumer**, rồi đăng ký chúng vào **FunctionCatalog**. Catalog cung cấp cách tìm và kết hợp các hàm theo tên, giúp adapter gọi đúng logic nghiệp vụ.

~~~mermaid
flowchart LR
    A["HTTP GET"] --> B["HTTP adapter"]
    C["Lịch poller"] --> D["Stream adapter"]
    E["Serverless trigger"] --> F["Serverless adapter"]
    B --> G["FunctionCatalog: heartbeat"]
    D --> G
    F --> G
    G --> H["Supplier.get()"]
    H --> I["Heartbeat"]
~~~

Sơ đồ thể hiện **một hợp đồng hàm** với các cơ chế kích hoạt khác nhau, không hàm ý rằng chỉ cần tạo một bean là cả ba giao thức tự động hoạt động. Mỗi môi trường cần dependency, cấu hình và adapter tương ứng.

Vòng đời cơ bản:

1. Spring khởi tạo bean Supplier trong application context.
2. Spring Cloud Function đăng ký bean dưới tên hàm, ví dụ **heartbeat**.
3. Adapter nhận tín hiệu kích hoạt: một GET, một chu kỳ poll hoặc một lần gọi từ runtime serverless.
4. Adapter lấy hàm từ catalog, gọi **get()**, rồi xử lý giá trị trả về theo giao thức đích.

**Phân biệt thời điểm khởi tạo bean và thời điểm tạo dữ liệu:** khai báo bean Supplier không có nghĩa là dữ liệu đã được tạo ngay khi ứng dụng khởi động. Với lambda **() -> tạoDữLiệu()**, phần thân thường chỉ chạy khi **get()** được gọi.

## 3. Ví dụ hoàn chỉnh: phát heartbeat cho một dịch vụ

Giả sử hệ thống kho muốn cung cấp một bản tin cho biết tên dịch vụ và thời điểm phát tín hiệu. Logic tạo bản tin không cần request body hoặc sự kiện đầu vào.

Với dự án Spring Boot đã quản lý phiên bản Spring Cloud tương thích, thêm starter dành cho adapter HTTP:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Khai báo ứng dụng và bean **heartbeat**:

~~~java
package example.function;

import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FunctionApp {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApp.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    Supplier<Heartbeat> heartbeat(Clock clock) {
        return () -> new Heartbeat("warehouse", Instant.now(clock));
    }

    public record Heartbeat(String service, Instant createdAt) {}
}
~~~

Ở đây:

- Tên phương thức bean **heartbeat** là tên hàm để Spring Cloud Function nhận diện.
- **Heartbeat** là dữ liệu đầu ra có cấu trúc; adapter HTTP có thể tuần tự hóa nó thành JSON.
- **Clock** được tiêm qua dependency injection để tách việc lấy thời gian khỏi logic hàm và thuận tiện cho kiểm thử.
- **Instant.now(clock)** nằm *bên trong* lambda. Mỗi lần **get()** chạy, một heartbeat mới được tạo với thời điểm lúc gọi.

Khi ứng dụng sử dụng adapter web và chạy trên cổng 8080 mặc định, có thể thử:

~~~bash
curl -i http://localhost:8080/heartbeat
~~~

Ví dụ phần thân phản hồi:

~~~json
{
  "service": "warehouse",
  "createdAt": "2026-01-15T08:30:00Z"
}
~~~

Thời gian trong JSON chỉ là giá trị minh họa; kết quả thực tế phụ thuộc thời điểm gọi. Do Supplier không có tham số, body request không phải dữ liệu đầu vào của **get()**. Endpoint kiểu GET nên dùng cho thao tác quan sát/cung cấp dữ liệu an toàn, tránh gắn hành động có tác dụng phụ như trừ tiền hoặc tạo đơn hàng.

## 4. Phân biệt tạo dữ liệu mỗi lần gọi và chụp sẵn một lần

Hai cách viết sau có ý nghĩa rất khác nhau.

**Cách dễ gây lỗi:** thời điểm được ghi nhận lúc Spring tạo bean, nên các lần gọi về sau cùng trả về một bản tin cũ.

~~~java
@Bean
Supplier<Heartbeat> staleHeartbeat(Clock clock) {
    Heartbeat snapshot = new Heartbeat("warehouse", Instant.now(clock));
    return () -> snapshot;
}
~~~

**Cách phù hợp khi cần dữ liệu mới:** tạo dữ liệu trong thân hàm.

~~~java
@Bean
Supplier<Heartbeat> freshHeartbeat(Clock clock) {
    return () -> new Heartbeat("warehouse", Instant.now(clock));
}
~~~

Việc trả về một đối tượng cố định không phải lúc nào cũng sai: Supplier cấp cấu hình bất biến có thể cố ý tái sử dụng kết quả. Cần xác định rõ yêu cầu về độ mới dữ liệu, chi phí truy vấn, bộ nhớ đệm và tác động của mỗi lần gọi.

## 5. FunctionCatalog và composition

FunctionCatalog là lớp tra cứu các bean chức năng do Spring Cloud Function quản lý. Nhờ catalog, phần gọi qua HTTP hoặc qua binder sự kiện có thể tìm hàm bằng tên, thay vì phụ thuộc trực tiếp vào lớp triển khai.

Một Supplier cũng có thể là đầu vào của một chuỗi biến đổi. Ví dụ bổ sung bean **describeHeartbeat** vào lớp cấu hình phía trên:

~~~java
@Bean
java.util.function.Function<Heartbeat, String> describeHeartbeat() {
    return heartbeat ->
        heartbeat.service() + " | " + heartbeat.createdAt();
}
~~~

Chuỗi có dạng:

~~~text
Supplier<Heartbeat> heartbeat
    -> Function<Heartbeat, String> describeHeartbeat
    -> kết quả String
~~~

Có thể chọn một định nghĩa hàm kết hợp trong cấu hình Spring Cloud Function:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat|describeHeartbeat
~~~

Ký hiệu **|** diễn tả thứ tự kết hợp: gọi Supplier trước để lấy **Heartbeat**, rồi truyền kết quả đó vào Function. Kết quả cuối cùng có kiểu **String**. Với ứng dụng chứa nhiều hàm, việc chọn definition tường minh giúp adapter biết hàm hoặc chuỗi hàm nào cần expose/bind. Đường dẫn và cách gọi cụ thể do adapter quyết định.

**Quy tắc ghép kiểu:** đầu ra **T** của Supplier phải tương thích với đầu vào của Function đứng sau nó. Không thể ghép trực tiếp **Supplier<Heartbeat>** với **Function<Order, Invoice>** nếu không có bước chuyển đổi phù hợp.

## 6. Dùng cùng Supplier để phát sự kiện

Trong mô hình sự kiện, Supplier thường đóng vai trò **nguồn phát dữ liệu ra ngoài**. Khi dùng Spring Cloud Stream cùng binder tương ứng (chẳng hạn Kafka hoặc RabbitMQ), một Supplier đồng bộ có thể được framework gọi theo cơ chế polling để gửi từng giá trị tới đích.

Ví dụ cấu hình minh họa cho ứng dụng chỉ chọn hàm **heartbeat** để phát sự kiện:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat
    stream:
      bindings:
        heartbeat-out-0:
          destination: heartbeat-events
      poller:
        fixed-delay: 5000
~~~

Ý nghĩa:

- **heartbeat-out-0** là tên binding đầu ra của Supplier **heartbeat**.
- **destination** là đích logic; broker và binder quyết định ánh xạ thực tế.
- **fixed-delay: 5000** cấu hình khoảng trì hoãn poller theo đơn vị mili giây; không nên hiểu là cam kết giao sự kiện chính xác từng 5 giây.
- Mỗi lần poll phù hợp có thể kích hoạt **get()**, sau đó framework gửi dữ liệu tới đích.

Cấu hình trên chỉ có tác dụng khi ứng dụng có Spring Cloud Stream, binder, broker và thông số kết nối cần thiết. Nếu mục tiêu là **xử lý sự kiện đến**, nên dùng **Consumer<T>** hoặc **Function<I, O>** thay vì cố đọc event đầu vào qua Supplier.

Trong môi trường serverless, cùng logic **Supplier<Heartbeat>** có thể được đóng gói bằng adapter phù hợp với nền tảng. Trigger, cấu hình handler, quy tắc chuyển đổi dữ liệu và vòng đời thực thi sẽ phụ thuộc runtime; bản thân Supplier không tự tạo lịch kích hoạt hay kết nối đến dịch vụ đám mây.

## 7. Supplier và thông điệp có metadata

Khi cần gửi kèm thông tin mô tả sự kiện, Supplier có thể trả về **Message<T>** thay cho chỉ **T**. Ví dụ sử dụng Spring Messaging:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Supplier<Message<Heartbeat>> heartbeatMessage(Clock clock) {
    return () -> MessageBuilder
        .withPayload(new Heartbeat("warehouse", Instant.now(clock)))
        .setHeader("eventType", "HEARTBEAT")
        .build();
}
~~~

Ở ví dụ này, **payload** là dữ liệu nghiệp vụ, còn **eventType** là header. Adapter/binder sẽ quyết định cách ánh xạ header sang giao thức truyền tải. Không nên mặc định mọi loại header được giữ nguyên qua mọi hệ thống.

Spring Cloud Function hỗ trợ chuyển đổi kiểu dữ liệu tại ranh giới của nhiều adapter. Chẳng hạn adapter HTTP có thể chuyển **Heartbeat** thành JSON, còn binder sự kiện sẽ mã hóa payload thành thông điệp gửi qua broker. Supplier không phải tự viết logic tuần tự hóa cho từng giao thức.

## 8. Supplier đồng bộ và Supplier phản ứng

**Supplier<T> thông thường** trả về một kết quả khi **get()** được gọi. Với cơ chế poll, framework có thể gọi lại nhiều lần để lấy các kết quả nối tiếp.

**Supplier<Flux<T>> phản ứng** trả về một publisher có khả năng phát nhiều phần tử theo thời gian. Ví dụ với Project Reactor:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

@Bean
Supplier<Flux<Heartbeat>> reactiveHeartbeat(Clock clock) {
    return () -> Flux.interval(Duration.ofSeconds(5))
        .map(index -> new Heartbeat("warehouse", Instant.now(clock)));
}
~~~

Trong tích hợp stream phản ứng, framework thường lấy publisher từ Supplier rồi đăng ký nhận luồng phần tử; thời gian phát được điều khiển bởi publisher thay vì cứ mỗi sự kiện lại gọi **get()**. Cần kiểm tra hành vi của adapter và phiên bản thư viện đang dùng; không phải mọi endpoint HTTP đều tự động trở thành một luồng dữ liệu liên tục.

| Tiêu chí | Supplier<Heartbeat> | Supplier<Flux<Heartbeat>> |
| --- | --- | --- |
| Kết quả một lần gọi **get()** | Một Heartbeat | Một publisher |
| Nguồn tạo các phần tử kế tiếp | Các lần gọi **get()** hoặc poller | Luồng Flux sau khi được subscribe |
| Phù hợp | Đọc trạng thái tức thời, phát từng bản tin theo lịch | Nguồn dữ liệu liên tục, có xử lý reactive |
| Điều cần lưu ý | Tốc độ poll, độ trễ của **get()** | Subscription, backpressure, hủy luồng và tài nguyên |

Không nên đưa một nguồn vô hạn vào HTTP đồng bộ thông thường khi chưa thiết kế rõ streaming response, timeout và cơ chế đóng kết nối.

## 9. Kiểm thử Supplier độc lập với adapter

Một lợi ích thiết thực của mô hình hàm là có thể kiểm thử chính logic **get()** mà không khởi động web server, broker hay môi trường serverless.

Ví dụ JUnit 5 cho bean **heartbeat**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class FunctionAppTest {

    @Test
    void heartbeatUsesProvidedClock() {
        Instant fixedTime = Instant.parse("2026-01-15T08:30:00Z");
        Clock fixedClock = Clock.fixed(fixedTime, ZoneOffset.UTC);

        Supplier<FunctionApp.Heartbeat> supplier =
            new FunctionApp().heartbeat(fixedClock);

        FunctionApp.Heartbeat result = supplier.get();

        assertEquals("warehouse", result.service());
        assertEquals(fixedTime, result.createdAt());
    }
}
~~~

Bài kiểm thử khẳng định Supplier sinh kết quả có cấu trúc mong đợi và tuân theo Clock được cung cấp. Kiểm thử tích hợp riêng nên kiểm tra đường HTTP, binding sự kiện hoặc adapter serverless khi các thành phần đó được sử dụng thật.

## 10. Những lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Thời gian hoặc dữ liệu luôn cũ | Tạo dữ liệu bên ngoài lambda, ngay lúc khởi tạo bean | Chuyển thao tác tạo dữ liệu vào **get()** nếu cần giá trị mới |
| Supplier không được expose hoặc không được bind đúng | Thiếu adapter, có nhiều bean nhưng chưa chọn function definition, hoặc cấu hình binding sai | Kiểm tra dependency, tên bean và **spring.cloud.function.definition** |
| Phát sự kiện nhanh hoặc chậm bất thường | Không hiểu cơ chế poller hoặc luồng reactive | Cấu hình lịch poll, quan sát tốc độ thực tế và áp dụng giới hạn phù hợp |
| HTTP GET gây thay đổi nghiệp vụ | Đưa thao tác tạo đơn, thanh toán hoặc ghi trạng thái vào **get()** | Dùng API/hàm có đầu vào và ngữ nghĩa HTTP thích hợp |
| Kết quả sai khi nhiều lời gọi đồng thời | Supplier giữ trạng thái mutable dùng chung nhưng không bảo vệ truy cập | Ưu tiên bất biến, tránh trạng thái dùng chung hoặc đồng bộ hóa đúng cách |
| Một lần gọi bị chậm, treo | **get()** truy cập I/O chặn lâu hoặc dịch vụ ngoài không có timeout | Đặt timeout, quan sát latency, cân nhắc cache hoặc kiến trúc bất đồng bộ |

Cũng cần cân nhắc rằng một Supplier tạo sự kiện có thể bị kích hoạt lại sau lỗi hoặc lúc ứng dụng khởi động lại. Nếu kết quả có tác dụng nghiệp vụ ở hệ thống nhận, hãy thiết kế mã định danh sự kiện, tính idempotent của phía xử lý và chiến lược giao nhận ở tầng tích hợp.

## 11. Thực hành củng cố

**Bài tập 1 — Supplier đơn giản:** tạo bean **Supplier<HealthSnapshot>** với hai trường **service** và **capturedAt**; dùng **Clock** để thời gian có thể kiểm thử. Gọi **get()** trong unit test và xác nhận tên dịch vụ đúng.

**Bài tập 2 — Composition:** viết **Function<HealthSnapshot, String>** để xuất chuỗi tóm tắt, sau đó cấu hình chuỗi **healthSnapshot|formatHealthSnapshot**. Giải thích vì sao Function phải nhận đúng kiểu mà Supplier trả về.

**Bài tập 3 — Chọn cách kích hoạt:** với ba nhu cầu *đọc trạng thái khi người dùng mở trang*, *phát heartbeat tới broker theo lịch* và *tiêu thụ lệnh từ Kafka*, hãy chọn lần lượt HTTP Supplier, Stream Supplier và Consumer/Function nhận đầu vào. Xác định thành phần adapter cần cho từng trường hợp.

### Ghi nhớ

- **Supplier<T>** biểu diễn hàm **() → T**, lấy dữ liệu mà không nhận đối số nghiệp vụ từ người gọi.
- **@Bean Supplier<T>** được Spring Cloud Function đăng ký và tra cứu qua **FunctionCatalog**; các adapter phù hợp có thể kích hoạt cùng logic.
- Với dữ liệu động, đặt phần tạo dữ liệu bên trong **get()** và kiểm soát phụ thuộc như thời gian, I/O, trạng thái dùng chung.
- Supplier có thể ghép với **Function<T, R>**, trả về **Message<T>** hoặc publisher phản ứng, nhưng cách kích hoạt và chuyển đổi dữ liệu phụ thuộc môi trường triển khai.
