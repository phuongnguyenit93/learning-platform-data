# Luồng dữ liệu liên tục và kiểm soát tốc độ nhận

Trong nhiều ứng dụng, dữ liệu không đến thành từng yêu cầu riêng lẻ mà xuất hiện liên tục: giá thị trường thay đổi, cảm biến gửi số đo, người dùng phát sinh sự kiện, log được ghi liên tục hoặc trạng thái đơn hàng được cập nhật theo thời gian. Khi producer phát dữ liệu nhanh hơn khả năng xử lý của consumer, hệ thống có thể tích tụ hàng đợi, tăng độ trễ, tiêu thụ nhiều bộ nhớ và cuối cùng bị quá tải.

Luồng dữ liệu (stream) mô hình hóa một chuỗi phần tử được phát theo thời gian. Kiểm soát tốc độ nhận là việc điều phối lượng dữ liệu được chuyển tới consumer sao cho tốc độ xử lý và tài nguyên của hệ thống vẫn nằm trong giới hạn chấp nhận được. Trong hệ sinh thái Spring, cần hiểu mối quan hệ giữa từng Message, luồng reactive nhiều phần tử và cơ chế backpressure để chọn đúng công cụ.

## 1. Vì sao cần luồng dữ liệu và kiểm soát tốc độ?

Giả sử một hệ thống giám sát nhận 5.000 số đo mỗi giây, trong khi một consumer chỉ xử lý được 1.000 số đo mỗi giây. Nếu producer cứ gửi liên tục, phần dữ liệu chưa xử lý sẽ tăng khoảng 4.000 phần tử mỗi giây. Sau một thời gian, hàng đợi có thể chiếm hết bộ nhớ hoặc dữ liệu đến consumer quá muộn để còn hữu ích.

Các tình huống tương tự xuất hiện khi:

- Một ứng dụng nhận nhiều sự kiện từ người dùng hoặc thiết bị IoT.
- Một dịch vụ tiêu thụ dữ liệu từ broker hoặc hệ thống log.
- Một endpoint gửi dữ liệu liên tục tới trình duyệt.
- Một pipeline thực hiện nhiều bước biến đổi, ghi cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài.
- Nhiều consumer cùng đọc dữ liệu và có tốc độ xử lý khác nhau.

Các vấn đề chính gồm:

**Consumer bị quá tải:** CPU, bộ nhớ, kết nối cơ sở dữ liệu hoặc thread pool bị sử dụng quá mức.

**Backlog tăng:** dữ liệu chờ xử lý ngày càng nhiều, làm tăng độ trễ đầu-cuối.

**Mất dữ liệu:** nếu hàng đợi đầy và chính sách xử lý là loại bỏ phần tử, một số sự kiện có thể bị bỏ qua.

**Tài nguyên bị giữ quá lâu:** thông điệp nằm trong bộ nhớ hoặc trạng thái xử lý quá lâu, làm giảm khả năng phục vụ yêu cầu mới.

**Tốc độ không ổn định:** lưu lượng thường tăng đột biến theo thời điểm, nên cấu hình phù hợp ở tải thấp có thể thất bại khi tải tăng.

Vì vậy, thiết kế streaming phải trả lời ba câu hỏi: dữ liệu được phát như thế nào, consumer báo khả năng tiếp nhận ra sao và hệ thống làm gì khi producer nhanh hơn consumer.

## 2. Phân biệt Message và stream

Trong Spring Messaging, Message<T> là một đơn vị thông điệp gồm payload và headers. Ví dụ một thông điệp có thể chứa một số đo nhiệt độ cùng thông tin về thiết bị gửi.

Một stream là chuỗi nhiều phần tử được phát theo thời gian. Mỗi phần tử có thể là một giá trị đơn giản hoặc một Message<T>. Có thể hình dung:

~~~text
Stream
  |
  +--> Message 1: payload + headers
  +--> Message 2: payload + headers
  +--> Message 3: payload + headers
  +--> ...
~~~

Message mô tả cấu trúc của một phần tử; stream mô tả cách nhiều phần tử được phát và tiêu thụ. Chỉ dùng MessageChannel không tự tạo ra một giao thức backpressure. Việc gửi có thể đồng bộ hoặc bất đồng bộ tùy implementation của channel, và bản thân thao tác send không cung cấp đầy đủ giao thức demand của Reactive Streams.

Đây là điểm quan trọng khi kết hợp Spring Messaging với Spring WebFlux, Reactor, RSocket hoặc một broker: phải xác định rõ cơ chế điều tiết tải nằm ở tầng nào.

## 3. Reactive Streams và tín hiệu demand

Reactive Streams là một đặc tả để trao đổi dữ liệu bất đồng bộ với cơ chế điều khiển luồng. Nó định nghĩa bốn vai trò:

- **Publisher:** nguồn phát dữ liệu.
- **Subscriber:** thành phần nhận và xử lý dữ liệu.
- **Subscription:** mối quan hệ giữa publisher và subscriber, qua đó subscriber yêu cầu dữ liệu hoặc hủy đăng ký.
- **Processor:** thành phần vừa nhận vừa phát dữ liệu, thường dùng để biến đổi hoặc nối các bước trong pipeline.

Một subscriber nhận thông báo onSubscribe trước. Sau đó subscriber gọi request(n) để báo rằng nó sẵn sàng nhận tối đa n phần tử. Publisher phát dữ liệu qua onNext cho đến khi hết lượng demand đã được yêu cầu. Khi luồng kết thúc bình thường, publisher gọi onComplete; nếu xảy ra lỗi không thể tiếp tục, publisher gọi onError. Subscriber cũng có thể gọi cancel() để ngừng nhận.

Luồng tín hiệu cơ bản:

~~~text
Subscriber                    Publisher
    |                             |
    |<------ onSubscribe ---------|
    |                             |
    |-------- request(3) -------->|
    |<--------- onNext(1) --------|
    |<--------- onNext(2) --------|
    |<--------- onNext(3) --------|
    |                             |
    |-------- request(2) -------->|
    |<--------- onNext(4) --------|
    |<--------- onNext(5) --------|
    |                             |
    |<--------- onComplete -------|
~~~

Demand là số phần tử subscriber cho phép publisher phát tiếp. Publisher tuân thủ Reactive Streams không được phát onNext vượt quá lượng demand đã được yêu cầu. Cơ chế này tạo ra một hình thức backpressure từ consumer ngược về producer.

Trong thực tế, một pipeline có thể có nhiều operator ở giữa. Các operator có thể giữ một lượng phần tử nội bộ, chia lô request hoặc chuyển dữ liệu qua scheduler khác. Vì vậy, backpressure cần được hiểu xuyên suốt pipeline, bao gồm cả buffer và các nguồn dữ liệu bên ngoài.

## 4. Flux và Mono trong hệ sinh thái Spring

Project Reactor là thư viện reactive được Spring WebFlux sử dụng. Hai kiểu dữ liệu quan trọng là:

| Kiểu | Số phần tử | Trường hợp sử dụng |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Một kết quả, ví dụ tìm một bản ghi |
| Flux<T> | 0 đến nhiều | Danh sách, luồng sự kiện hoặc dữ liệu liên tục |

Flux<T> triển khai Publisher trong Reactive Streams. Subscriber có thể điều khiển demand của Flux thông qua Subscription. Mono<T> cũng hỗ trợ giao thức reactive nhưng chỉ phát tối đa một phần tử.

Ví dụ về một nguồn phát tuần tự:

~~~java
Flux<Integer> numbers = Flux.range(1, 5);
~~~

Ví dụ về một nguồn phát theo thời gian:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
~~~

Flux.interval tạo các giá trị theo chu kỳ. Với nguồn vô hạn như vậy, ứng dụng cần xác định thời điểm hủy subscription, chẳng hạn khi client ngắt kết nối hoặc khi tác vụ không còn cần dữ liệu.

Trong Spring:

- **Spring WebFlux** dùng Mono và Flux cho xử lý HTTP reactive. Một endpoint có thể trả về Flux để phát nhiều phần tử, ví dụ dữ liệu dạng Server-Sent Events.
- **Spring Messaging** cung cấp cấu trúc Message, headers và các abstraction channel/handler. Các abstraction này mô tả từng thông điệp và điểm giao tiếp.
- **Spring RSocket** kết hợp mô hình messaging với các kiểu tương tác như request-response, fire-and-forget, request-stream và request-channel. Các handler có thể nhận hoặc trả về Flux để xử lý luồng nhiều phần tử.
- **Reactor** cung cấp các operator để biến đổi, kết hợp, điều tiết và xử lý lỗi trong pipeline.

Không nên đồng nhất MessageChannel với Flux. MessageChannel là abstraction gửi một Message; Flux là một Publisher phát chuỗi phần tử theo giao thức Reactive Streams. Khi kết nối hai mô hình, cần một adapter hoặc cơ chế tích hợp có chính sách về buffer, lỗi, hủy và tốc độ nhận.

## 5. Backpressure: consumer điều khiển lượng dữ liệu

Backpressure là cơ chế để consumer truyền ngược tín hiệu về lượng dữ liệu nó có thể tiếp nhận. Thay vì để producer tự do phát vô hạn, consumer yêu cầu từng lượng phần tử phù hợp với khả năng xử lý.

Ví dụ, một consumer có thể yêu cầu 50 phần tử, xử lý xong rồi mới yêu cầu thêm 50 phần tử. Nếu nó đang bận ghi cơ sở dữ liệu, nó có thể trì hoãn request tiếp theo. Khi client hủy subscription, luồng có thể dừng công việc tương ứng.

Backpressure hữu ích khi:

- Tốc độ consumer thay đổi theo tải.
- Các bước xử lý có chi phí khác nhau.
- Producer có khả năng tôn trọng tín hiệu demand.
- Pipeline cần giới hạn lượng dữ liệu chờ trong bộ nhớ.

Tuy nhiên, backpressure không thể làm cho mọi nguồn dữ liệu bên ngoài tự chậm lại. Một thiết bị chỉ phát UDP, một callback không thể tạm dừng hoặc một nguồn sự kiện không hỗ trợ demand có thể tiếp tục phát dù consumer đang bận. Với những nguồn như vậy, ứng dụng phải chọn chính sách đệm, loại bỏ, lấy mẫu, giới hạn tốc độ hoặc lưu bền vững ở tầng tiếp nhận.

Backpressure cũng không đồng nghĩa với xác nhận nghiệp vụ hoặc xác nhận đã lưu dữ liệu. request(1) chỉ thể hiện demand cho một phần tử tiếp theo; nó không chứng minh rằng giao dịch cơ sở dữ liệu đã commit hoặc sự kiện đã được xử lý thành công theo nghiệp vụ.

## 6. Các cách kiểm soát tốc độ nhận

Không có một chính sách phù hợp cho mọi loại dữ liệu. Cần lựa chọn theo mức độ quan trọng của từng phần tử và khả năng điều khiển nguồn phát.

### 6.1. Yêu cầu theo lô bằng request(n)

Subscriber chỉ yêu cầu một số lượng phần tử nhất định. Sau khi xử lý xong lô hiện tại, nó yêu cầu lô tiếp theo. Đây là cách thể hiện trực tiếp demand của Reactive Streams.

Phù hợp khi consumer có thể quyết định thời điểm nhận thêm dữ liệu và muốn tránh nhận quá nhiều phần tử cùng lúc.

### 6.2. Giới hạn request upstream bằng limitRate

Trong Reactor, limitRate(n) điều chỉnh cách pipeline yêu cầu dữ liệu từ upstream theo từng lô. Điều này giúp tránh việc một bước downstream yêu cầu một lượng rất lớn dữ liệu cùng lúc.

Ví dụ:

~~~java
Flux.range(1, 1000)
    .limitRate(32)
    .subscribe(this::process);
~~~

Ở đây, limitRate điều chỉnh lượng request được chuyển ngược lên nguồn. Nó không phải bộ giới hạn chính xác số phần tử mỗi giây. Nếu yêu cầu là tối đa 100 sự kiện trong một giây, cần một chính sách giới hạn theo thời gian hoặc rate limiter phù hợp.

### 6.3. Đệm dữ liệu

Buffer lưu phần tử trong lúc consumer chưa xử lý kịp. Đệm có thể hấp thụ các đợt tăng tải ngắn, nhưng cần đặt giới hạn rõ ràng.

- **Buffer có giới hạn:** giữ tối đa một số phần tử; khi đầy phải xác định hành vi overflow.
- **Buffer không giới hạn:** có nguy cơ làm bộ nhớ tăng không kiểm soát nếu producer luôn nhanh hơn consumer.
- **Dead-letter hoặc lưu bền vững:** phù hợp hơn khi dữ liệu quan trọng và cần quy trình xử lý lại sau lỗi, tùy khả năng của broker hoặc hệ thống lưu trữ.

Buffer chỉ trì hoãn vấn đề khi tốc độ trung bình của producer luôn cao hơn consumer. Nó không giải quyết được chênh lệch tải kéo dài.

### 6.4. Loại bỏ phần tử hoặc giữ giá trị mới nhất

Với dữ liệu telemetry hoặc trạng thái giao diện, không phải lúc nào cũng cần xử lý mọi mẫu. Có thể chọn bỏ phần tử mới khi quá tải, hoặc chỉ giữ phần tử mới nhất.

Reactor cung cấp các operator như onBackpressureDrop() và onBackpressureLatest() cho những tình huống phù hợp. Chính sách này làm giảm áp lực bộ nhớ, nhưng đồng nghĩa với việc một số giá trị không được xử lý. Không dùng nó cho các sự kiện nghiệp vụ cần bảo toàn đầy đủ như lệnh thanh toán hoặc thay đổi trạng thái đơn hàng.

### 6.5. Làm chậm hoặc lấy mẫu theo thời gian

delayElements(Duration) tạo khoảng trễ giữa các phần tử được chuyển xuống downstream. sample(Duration) lấy mẫu theo chu kỳ, còn window hoặc buffer theo thời gian có thể gom phần tử thành nhóm.

Các operator này hữu ích cho trình bày dữ liệu hoặc xử lý theo nhịp. Tuy nhiên, delayElements không phải một bộ giới hạn tốc độ toàn cục và không bảo đảm giới hạn số sự kiện mỗi giây cho nhiều subscriber. Với yêu cầu giới hạn lưu lượng nghiêm ngặt, dùng rate limiter hoặc cơ chế quota được thiết kế theo thời gian.

### 6.6. Giới hạn số tác vụ xử lý đồng thời

Ngay cả khi tốc độ nhận phù hợp, consumer vẫn có thể tạo quá nhiều tác vụ đồng thời. flatMap cho phép xử lý các phần tử theo hướng đồng thời; có thể đặt giới hạn concurrency để kiểm soát số tác vụ đang chạy. concatMap xử lý tuần tự, hữu ích khi cần giữ thứ tự hoặc chỉ cho phép một tác vụ hoạt động tại một thời điểm.

Kiểm soát concurrency giúp bảo vệ các tài nguyên như connection pool, API bên ngoài và thread pool. Cần cân bằng giữa thông lượng và độ trễ.

## 7. Chọn chính sách theo loại dữ liệu

| Loại dữ liệu | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Lệnh thanh toán, đơn hàng | Backpressure, queue bền vững, retry có giới hạn | Không được tùy tiện bỏ sự kiện |
| Số đo cảm biến tần suất cao | Lấy mẫu, giữ giá trị mới nhất hoặc buffer có giới hạn | Giá trị mới thường hữu ích hơn mẫu cũ |
| Giá thị trường | Stream có demand, buffer ngắn và chính sách bỏ dữ liệu cũ tùy yêu cầu | Cần độ trễ thấp và dữ liệu mới |
| Log và audit | Broker/queue bền vững, batch và kiểm soát consumer | Cần bảo toàn và truy vết |
| Trạng thái giao diện | Latest, sample hoặc giới hạn theo client | Không cần gửi mọi thay đổi trung gian |

Hãy xác định rõ dữ liệu nào có thể bỏ, dữ liệu nào phải lưu, thời gian chờ tối đa và mức độ trễ chấp nhận được trước khi chọn operator.

## 8. Ví dụ: nhận Message theo từng lô bằng Reactor

Ví dụ sau tạo một Flux gồm 10 Spring Message. Subscriber chỉ yêu cầu ba phần tử đầu tiên. Sau khi xử lý xong mỗi lô ba phần tử, nó mới yêu cầu lô tiếp theo.

Ví dụ dùng Java 17, Spring Messaging 6.2.8 và Reactor Core 3.7.6. Đây là chương trình console độc lập để quan sát giao thức demand; nó không khởi động broker hoặc máy chủ WebFlux.

Cấu trúc dự án:

~~~text
stream-demand-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StreamDemandDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stream-demand-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.7.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/StreamDemandDemo.java

~~~java
package demo;

import org.reactivestreams.Subscription;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class StreamDemandDemo {

    public static void main(String[] args) {
        Flux<Message<Integer>> stream = Flux.range(1, 10)
                .map(value -> MessageBuilder.withPayload(value)
                        .setHeader("source", "sensor-01")
                        .build());

        stream.subscribe(new BaseSubscriber<Message<Integer>>() {
            private int receivedInBatch;

            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("Subscribed; request 3");
                request(3);
            }

            @Override
            protected void hookOnNext(Message<Integer> message) {
                System.out.println("Received: " + message.getPayload());
                receivedInBatch++;

                if (receivedInBatch == 3 && message.getPayload() < 10) {
                    receivedInBatch = 0;
                    System.out.println("Request next 3");
                    request(3);
                }
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("Completed");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.err.println("Stream failed: " + error.getMessage());
            }
        });
    }
}
~~~

Chạy trong thư mục có pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.StreamDemandDemo
~~~

Kết quả:

~~~text
Subscribed; request 3
Received: 1
Received: 2
Received: 3
Request next 3
Received: 4
Received: 5
Received: 6
Request next 3
Received: 7
Received: 8
Received: 9
Request next 3
Received: 10
Completed
~~~

Giải thích:

1. Flux.range(1, 10) tạo nguồn gồm mười phần tử.
2. map(...) đóng gói từng số thành Spring Message<Integer> và thêm header source.
3. BaseSubscriber cho phép kiểm soát demand bằng request(n).
4. hookOnSubscribe yêu cầu ba phần tử đầu tiên.
5. hookOnNext xử lý từng Message. Khi nhận đủ ba phần tử, subscriber yêu cầu thêm ba phần tử.
6. Khi nguồn hết dữ liệu, subscriber nhận hookOnComplete.

Flux.range là nguồn đồng bộ và hữu hạn nên ví dụ chạy nhanh trong một luồng thực thi. Nó minh họa số lượng phần tử được yêu cầu qua Reactive Streams; nó không mô phỏng giới hạn theo thời gian như 100 sự kiện mỗi giây. Trong ứng dụng thực tế, consumer có thể yêu cầu lô tiếp theo sau khi hoàn tất ghi dữ liệu hoặc sau khi một tài nguyên đã sẵn sàng.

## 9. Kết nối luồng với Spring Messaging

Spring Messaging cung cấp Message và các abstraction để các thành phần trao đổi thông điệp. Khi ứng dụng cần streaming, có thể dùng Reactor và các integration tương ứng ở tầng vận chuyển.

Ví dụ một handler RSocket có thể trả về Flux để phát dữ liệu liên tục:

~~~java
@Controller
public class TelemetryController {

    @MessageMapping("telemetry")
    public Flux<Telemetry> streamTelemetry() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(sequence -> new Telemetry(sequence, sequence * 0.5));
    }
}

public record Telemetry(long sequence, double value) {
}
~~~

Đây là đoạn minh họa handler, cần được đặt trong ứng dụng đã cấu hình RSocket server và các dependency tương ứng. Client gửi request-stream tới route telemetry sẽ nhận chuỗi giá trị. RSocket hỗ trợ tương tác theo luồng và cơ chế demand của Reactive Streams.

Một endpoint WebFlux có thể trả về Flux để truyền dữ liệu dạng Server-Sent Events:

~~~java
@GetMapping(value = "/telemetry", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Telemetry>> telemetry() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> ServerSentEvent.builder(
                    new Telemetry(sequence, sequence * 0.5))
                    .event("measurement")
                    .build());
}
~~~

Đoạn này cần controller WebFlux và cấu hình HTTP tương ứng. Server-Sent Events phù hợp với luồng một chiều từ server tới trình duyệt. Nếu cần giao tiếp hai chiều hoặc định tuyến nhiều kiểu thông điệp, có thể cân nhắc WebSocket hoặc RSocket theo yêu cầu.

Khi nối một Flux với MessageChannel hoặc broker, phải xem xét cách adapter chuyển demand thành thao tác nhận/gửi thực tế. Không được giả định rằng mọi channel hoặc broker đều hỗ trợ request(n) giống nhau. Một adapter có thể cần giới hạn prefetch, hàng đợi có giới hạn, acknowledgment, hoặc chính sách overflow riêng.

## 10. Lỗi và vòng đời của stream

Một stream có vòng đời rõ ràng:

- onNext: một phần tử được phát tới subscriber.
- onError: luồng kết thúc do lỗi.
- onComplete: nguồn hoàn tất bình thường.
- cancel: subscriber chủ động ngừng nhận.

Trong các ứng dụng streaming vô hạn, onComplete có thể không xảy ra cho đến khi nguồn đóng. Khi client ngắt kết nối, cần hủy subscription và giải phóng tài nguyên như kết nối, timer hoặc listener.

Một số nguyên tắc xử lý lỗi:

**Không retry mọi lỗi vô hạn:** lỗi dữ liệu không hợp lệ hoặc lỗi nghiệp vụ thường không tự hết khi thử lại. Giới hạn số lần retry và ghi nhận nguyên nhân.

**Đặt timeout khi chờ tài nguyên bên ngoài:** một phần tử bị kẹt ở bước gọi API hoặc ghi cơ sở dữ liệu có thể làm backlog tăng.

**Phân biệt lỗi phần tử và lỗi toàn luồng:** tùy thiết kế, có thể xử lý lỗi của một phần tử rồi tiếp tục, hoặc kết thúc toàn bộ stream khi trạng thái không còn an toàn.

**Giải phóng khi hủy:** dùng hook hoặc cơ chế cleanup phù hợp để đóng tài nguyên khi subscriber cancel hoặc stream kết thúc.

**Truyền correlation/trace context:** liên kết log của producer, các bước xử lý và consumer để điều tra độ trễ hoặc lỗi.

## 11. Những nhầm lẫn phổ biến

**Cho rằng Flux tự động giới hạn tốc độ theo giây:** Flux hỗ trợ demand và backpressure, nhưng không tự đặt quota như 100 phần tử mỗi giây. Cần phân biệt điều khiển số lượng phần tử với giới hạn theo thời gian.

**Cho rằng limitRate là rate limiter:** limitRate điều chỉnh lượng request được gửi upstream theo lô. Nó không đảm bảo tốc độ cố định theo giây.

**Cho rằng buffer giải quyết được quá tải lâu dài:** buffer chỉ hấp thụ chênh lệch ngắn hạn. Nếu producer luôn nhanh hơn consumer, buffer sẽ đầy hoặc tăng không giới hạn nếu không đặt ngưỡng.

**Cho rằng backpressure có thể dừng mọi nguồn bên ngoài:** chỉ những publisher hoặc adapter hỗ trợ cơ chế điều tiết mới có thể phản ứng với demand. Nguồn không thể tạm dừng cần chính sách đệm, lấy mẫu, bỏ dữ liệu hoặc lưu bền vững.

**Cho rằng MessageChannel đã có backpressure:** MessageChannel biểu diễn thao tác gửi Message. Cách gửi, buffer và xử lý phụ thuộc implementation; nó không tự mang giao thức Reactive Streams.

**Cho rằng request(n) là xác nhận nghiệp vụ:** request(n) chỉ yêu cầu publisher phát tối đa n phần tử. Nó không xác nhận đã commit dữ liệu hoặc hoàn thành giao dịch.

**Dùng chính sách bỏ dữ liệu cho sự kiện quan trọng:** drop/latest phù hợp với một số luồng telemetry hoặc giao diện, nhưng có thể làm sai nghiệp vụ nếu dùng cho thanh toán, đơn hàng hoặc audit.

## 12. Checklist thiết kế một luồng dữ liệu

Trước khi đưa stream vào vận hành, hãy trả lời:

1. Nguồn dữ liệu có hỗ trợ backpressure hoặc tạm dừng phát không?
2. Consumer xử lý được bao nhiêu phần tử mỗi giây và bao nhiêu phần tử đồng thời?
3. Dữ liệu có được phép bỏ, lấy mẫu hoặc chỉ giữ giá trị mới nhất không?
4. Buffer tối đa là bao nhiêu và hành vi khi buffer đầy là gì?
5. Có cần bảo toàn thứ tự theo khóa nghiệp vụ không?
6. Khi client hủy hoặc dịch vụ dừng, subscription và tài nguyên được giải phóng như thế nào?
7. Lỗi được retry bao nhiêu lần, có dead-letter hoặc lưu bền vững không?
8. Có metric cho throughput, backlog, độ trễ, overflow, lỗi và số subscription đang hoạt động không?
9. Giới hạn được áp dụng theo từng subscriber, từng tenant hay toàn hệ thống?
10. Cơ chế bảo mật và phân quyền được áp dụng cho publisher, consumer và route ra sao?

## 13. Ghi nhớ

- Message là một đơn vị dữ liệu; stream là chuỗi phần tử được phát theo thời gian.
- Reactive Streams dùng Publisher, Subscriber và Subscription để truyền demand.
- request(n) cho biết subscriber sẵn sàng nhận tối đa n phần tử tiếp theo; cancel() dừng subscription.
- Flux biểu diễn 0 đến nhiều phần tử; Mono biểu diễn 0 hoặc 1 phần tử.
- Backpressure giúp điều tiết luồng khi publisher có thể tôn trọng demand.
- limitRate điều chỉnh request theo lô, còn rate limiter kiểm soát lưu lượng theo thời gian.
- Buffer, drop, latest, sample và giới hạn concurrency là các chính sách khác nhau; phải chọn theo mức độ quan trọng của dữ liệu.
- Spring Messaging MessageChannel không tự cung cấp Reactive Streams backpressure. Khi tích hợp với Reactor, WebFlux, RSocket hoặc broker, cần hiểu rõ adapter và chính sách điều tiết ở tầng vận chuyển.
