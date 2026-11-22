# Timeout cho từng yêu cầu và quản lý luồng không kết thúc

> Phạm vi: Spring Framework Messaging với RSocket, Project Reactor và Java 17+. Trọng tâm là đặt giới hạn thời gian cho từng lần gọi, kết thúc stream đúng lúc, và giải phóng tài nguyên khi subscriber ngừng nhận dữ liệu.

## 1. Vì sao cần timeout và quản lý vòng đời stream?

RSocket hỗ trợ giao tiếp hai chiều, bất đồng bộ và multiplex trên một kết nối. Một kết nối có thể mang nhiều request độc lập. Mỗi request tạo ra một stream có vòng đời riêng:

- **Request-Response** gửi một payload và nhận tối đa một payload phản hồi. Trong Spring/Reactor, kiểu trả về thường là `Mono<T>`.
- **Request-Stream** gửi một payload và nhận nhiều payload. Kiểu trả về thường là `Flux<T>`.
- **Channel** trao đổi nhiều payload ở cả hai chiều. Phía gửi có thể truyền một `Publisher`, phía nhận trả về một `Publisher`.
- **Fire-and-Forget** gửi một payload mà không chờ payload phản hồi. `RSocketRequester.send()` trả về `Mono<Void>`; việc Mono hoàn tất chỉ cho biết thông điệp đã được gửi, không chứng minh handler đã xử lý thành công.

Một request có thể chậm, không bao giờ trả lời, hoặc trả về một stream kéo dài vô hạn. Nếu không đặt chính sách rõ ràng, caller có thể chờ vô thời hạn; stream cũ có thể tiếp tục giữ subscription, socket, cursor, listener hoặc tài nguyên bên ngoài. Vì vậy cần xác định ít nhất ba điều: thời gian chờ phản hồi, khoảng im lặng tối đa giữa hai sự kiện, và tuổi thọ tối đa của cả stream.

Timeout cần được đặt theo hợp đồng của từng thao tác. Một lệnh đọc dữ liệu thường có deadline ngắn; một luồng telemetry có thể được phép chạy lâu nhưng phải kết thúc khi người dùng rời màn hình hoặc khi hết phiên theo dõi.

## 2. RSocket trong Spring và vị trí đặt timeout

Spring cung cấp `RSocketRequester` trong module `spring-messaging`. API này đóng gói payload và metadata, sau đó chuyển kết quả thành `Mono` hoặc `Flux`. Kiểu tương tác được suy ra từ số lượng payload đầu vào và đầu ra.

Ví dụ một request-stream: gửi một đối tượng và nhận nhiều kết quả:

```java
Flux<Reading> readings = requester.route("sensor.readings")
    .data(new SensorRequest("sensor-17"))
    .retrieveFlux(Reading.class);
```

Ví dụ request-response không cần payload đầu vào:

```java
Mono<Reading> reading = requester.route("sensor.latest")
    .retrieveMono(Reading.class);
```

`retrieveMono` phù hợp với một kết quả; `retrieveFlux` phù hợp với nhiều kết quả. Đừng chuyển một stream thành `Mono` chỉ để né việc quản lý vòng đời: cần giữ đúng cardinality của giao thức và dữ liệu thực tế.

Các publisher của Reactor thường lazy. Việc gọi phương thức để tạo `Mono` hoặc `Flux` chưa bắt đầu request. Request bắt đầu khi có subscription; do đó timeout đặt trên chuỗi reactive thường bắt đầu tính từ lúc subscriber đăng ký.

Có thể đặt timeout ở nhiều lớp:

1. **Client timeout** giới hạn thời gian caller chờ kết quả. Đây là lớp bảo vệ trực tiếp cho trải nghiệm người gọi.
2. **Server timeout** giới hạn thời gian xử lý một thao tác ở phía responder. Nó ngăn công việc nội bộ chạy mãi khi phụ thuộc phía dưới bị treo.
3. **Stream timeout** phát hiện stream không còn phát sự kiện trong khoảng thời gian cho phép.
4. **Stream lifetime** giới hạn tổng thời gian một subscription được phép tồn tại.

Các giới hạn này giải quyết các vấn đề khác nhau. Không nên dùng một giá trị timeout duy nhất cho mọi thao tác.

## 3. Timeout cho request-response bằng Mono

Với một phản hồi đơn, `Mono.timeout(Duration)` phát sinh `TimeoutException` nếu Mono không phát ra phần tử trong thời gian quy định. Ví dụ:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

Mono<Reading> read(String sensorId) {
    return requester.route("sensor.read")
        .data(new SensorRequest(sensorId))
        .retrieveMono(Reading.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
            TimeoutException.class,
            error -> new SensorRequestTimeoutException(sensorId, error)
        );
}
```

Trong ví dụ này, caller dành tối đa ba giây cho thao tác đọc. Nếu không có phản hồi đúng hạn, lỗi timeout được chuyển thành exception của miền nghiệp vụ để tầng trên có thể phân loại, ghi log hoặc trả mã lỗi phù hợp.

Có thể thay lỗi bằng một publisher dự phòng nếu nghiệp vụ cho phép:

```java
Mono<Reading> readWithFallback(String sensorId) {
    return requester.route("sensor.read")
        .data(new SensorRequest(sensorId))
        .retrieveMono(Reading.class)
        .timeout(
            Duration.ofSeconds(3),
            Mono.just(Reading.unavailable(sensorId))
        );
}
```

Fallback chỉ phù hợp khi giá trị thay thế có ý nghĩa rõ ràng. Không nên biến timeout thành dữ liệu thành công giả nếu caller cần biết rằng hệ thống không nhận được phản hồi.

Một trường hợp khác cần phân biệt: `Mono.empty()` hoàn tất mà không phát phần tử. Nếu nó hoàn tất trước deadline thì `timeout` không kích hoạt, vì publisher đã kết thúc. Khi nghiệp vụ bắt buộc phải có kết quả, hãy kiểm tra trường hợp rỗng riêng:

```java
return requester.route("sensor.read")
    .data(new SensorRequest(sensorId))
    .retrieveMono(Reading.class)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Sensor không trả về dữ liệu")
    ))
    .timeout(Duration.ofSeconds(3));
```

Đặt `timeout` sau khi tạo request để nó bao phủ toàn bộ publisher mà caller đang chờ. Khi cần một deadline thống nhất xuyên qua nhiều lời gọi, hãy truyền thời gian còn lại xuống các tầng dưới thay vì để mỗi tầng bắt đầu lại một khoảng chờ dài.

## 4. Timeout cho request-stream bằng Flux

Với `Flux<T>`, `timeout(Duration)` có nghĩa là **khoảng thời gian tối đa không có phần tử mới**. Đồng hồ được tính từ lúc subscription bắt đầu chờ phần tử đầu tiên, rồi được đặt lại sau mỗi `onNext`.

```java
Flux<Reading> watch(String sensorId) {
    return requester.route("sensor.watch")
        .data(new SensorRequest(sensorId))
        .retrieveFlux(Reading.class)
        .timeout(Duration.ofSeconds(15));
}
```

Luồng sẽ phát sinh `TimeoutException` nếu:

- Không nhận được phần tử đầu tiên trong 15 giây; hoặc
- Sau một phần tử, không nhận được phần tử tiếp theo trong 15 giây.

Nếu stream cứ phát dữ liệu đều đặn mỗi 10 giây, nó có thể chạy hàng giờ hoặc mãi mãi mà không timeout. Đây là hành vi đúng: `timeout(Duration)` của `Flux` là timeout theo khoảng im lặng, không phải deadline tổng.

Khi mỗi phần tử có SLA khác nhau, Reactor còn hỗ trợ `timeout(firstTimeout, nextTimeoutFactory)`. Publisher đầu tiên đặt giới hạn cho phần tử đầu; hàm `nextTimeoutFactory` tạo giới hạn chờ phần tử tiếp theo dựa trên phần tử vừa nhận. Cách này hữu ích khi khoảng chờ được quyết định bởi loại sự kiện hoặc trạng thái nghiệp vụ.

Nếu luồng có thể im lặng lâu một cách hợp lệ, hãy chọn ngưỡng phù hợp với tần suất dữ liệu hoặc thiết kế heartbeat ở tầng ứng dụng. RSocket KEEPALIVE chỉ kiểm tra sức sống của kết nối; frame KEEPALIVE không phải payload nghiệp vụ và không thay thế sự kiện dữ liệu mà `Flux.timeout` đang chờ.

## 5. Giới hạn tổng tuổi thọ của stream

Một stream có thể hoạt động bình thường nhưng không bao giờ hoàn tất. Khi nghiệp vụ chỉ cho phép theo dõi trong một khoảng thời gian, hãy đặt giới hạn tổng bằng `take(Duration)`:

```java
Flux<Reading> watchForTenMinutes(String sensorId) {
    return requester.route("sensor.watch")
        .data(new SensorRequest(sensorId))
        .retrieveFlux(Reading.class)
        .timeout(Duration.ofSeconds(15))       // Tối đa 15 giây im lặng
        .take(Duration.ofMinutes(10))          // Tối đa 10 phút cho cả stream
        .doFinally(signal ->
            log.info("sensor.watch kết thúc: {}", signal)
        );
}
```

Sau 10 phút, `take(Duration)` hoàn tất luồng downstream và hủy subscription upstream. Nhờ vậy caller nhận tín hiệu hoàn tất bình thường và request đang mở được yêu cầu dừng. Nếu muốn giới hạn số sự kiện, dùng `take(n)`. Nếu muốn kết thúc khi gặp sự kiện nghiệp vụ, dùng `takeUntil(predicate)`; toán tử này vẫn chuyển tiếp phần tử khớp điều kiện cuối cùng. `takeWhile(predicate)` thì dừng trước khi chuyển tiếp phần tử đầu tiên không còn thỏa điều kiện.

| Nhu cầu | Cách dùng | Kết quả khi chạm giới hạn |
|---|---|---|
| Không nhận được phản hồi đơn đúng hạn | `Mono.timeout(Duration)` | Phát lỗi timeout |
| Stream không phát phần tử mới | `Flux.timeout(Duration)` | Phát lỗi timeout |
| Stream chạy quá thời gian cho phép | `Flux.take(Duration)` | Hoàn tất bình thường và hủy upstream |
| Chỉ cần tối đa N phần tử | `Flux.take(n)` | Hoàn tất sau N phần tử |
| Dừng khi gặp điều kiện nghiệp vụ | `Flux.takeUntil(predicate)` | Bao gồm phần tử khớp điều kiện rồi hoàn tất |

Nếu API cần báo lỗi khi vượt tổng deadline thay vì hoàn tất bình thường, hãy định nghĩa rõ deadline và biểu diễn nó thành lỗi ở tầng ứng dụng. Đừng diễn giải `take(Duration)` thành timeout exception: hai hành vi này có hợp đồng khác nhau.

## 6. Hủy request và giải phóng tài nguyên

Reactive Streams có tín hiệu cancellation. Khi downstream hủy subscription, các toán tử như `timeout` hoặc `take` truyền yêu cầu hủy về upstream. Trong RSocket, requester có thể gửi frame `CANCEL` cho stream đang hoạt động. Responder nhận cancellation và có thể dừng việc tạo dữ liệu cho request đó.

Điều này chỉ giải phóng tài nguyên đúng cách nếu publisher và nguồn dữ liệu phía server tôn trọng cancellation. Ví dụ handler trả về `Flux` nên gắn cleanup với vòng đời của subscription:

```java
@Controller
class SensorRSocketController {

    private final SensorService sensorService;

    SensorRSocketController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensor.watch")
    Flux<Reading> watch(SensorRequest request) {
        return sensorService.watch(request.sensorId())
            .doFinally(signal ->
                log.info("watch {} kết thúc với {}", request.sensorId(), signal)
            );
    }
}
```

`doFinally` được gọi khi chuỗi hoàn tất, lỗi hoặc bị hủy; `SignalType` giúp phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`. Dùng nó để ghi nhận vòng đời, tăng metric hoặc thực hiện cleanup đồng bộ ngắn. Không chặn thread và không đặt thao tác I/O đồng bộ lâu trong callback này.

Nếu mỗi subscription sở hữu một tài nguyên bất đồng bộ, `usingWhen` phù hợp hơn vì cho phép khai báo cleanup riêng cho hoàn tất, lỗi và cancellation:

```java
Flux<Reading> watch(String sensorId) {
    return Flux.usingWhen(
        streamRegistry.open(sensorId),
        handle -> handle.events(),
        handle -> handle.close(),
        (handle, error) -> handle.close(),
        handle -> handle.close()
    );
}
```

Trong ví dụ, `open` trả về `Publisher<StreamHandle>`, `events()` trả về luồng dữ liệu, và `close()` trả về publisher hoàn tất sau khi giải phóng tài nguyên. Hãy bảo đảm cleanup có thể được gọi an toàn và không giải phóng tài nguyên dùng chung của subscriber khác.

Tránh tự gọi `subscribe()` bên trong `@MessageMapping` rồi trả về một publisher khác. Handler nên trả trực tiếp `Mono` hoặc `Flux` để Spring quản lý subscription, lỗi, backpressure và cancellation theo vòng đời request.

## 7. Backpressure và bộ nhớ của stream dài hạn

RSocket mang ngữ nghĩa Reactive Streams qua ranh giới mạng. Với request-stream và channel, requester gửi nhu cầu ban đầu rồi cập nhật bằng các frame `REQUEST_N`. Responder chỉ nên phát số phần tử phù hợp với nhu cầu đã được cấp. Đây là cơ chế điều tiết luồng dữ liệu giữa hai đầu.

Backpressure không tự bảo vệ ứng dụng khỏi mọi bộ đệm cục bộ. Một số toán tử hoặc nguồn dữ liệu có thể tích lũy dữ liệu trong bộ nhớ. Đặc biệt:

- Không dùng `collectList()` cho stream không có điểm kết thúc rõ ràng; nó phải chờ hoàn tất và giữ các phần tử đã nhận.
- Không dùng `cache()` mặc định cho stream vô hạn; nó có thể giữ lịch sử phần tử không giới hạn.
- Tránh `onBackpressureBuffer()` không giới hạn. Nếu thật sự cần buffer, đặt sức chứa tối đa và định nghĩa hành vi khi đầy: lỗi, bỏ phần tử cũ hoặc bỏ phần tử mới theo yêu cầu nghiệp vụ.
- Dùng `limitRate(n)` khi cần điều chỉnh nhịp yêu cầu upstream. Đây là cách điều tiết demand, không phải giới hạn tổng số phần tử hay tuổi thọ stream.
- Ưu tiên nguồn dữ liệu hỗ trợ demand/cancellation thay vì phát dữ liệu vô hạn rồi lưu toàn bộ vào queue.

Với dữ liệu telemetry, log hoặc sự kiện tốc độ cao, cần quyết định rõ dữ liệu nào có thể bỏ, dữ liệu nào phải giữ, và khi consumer chậm thì hệ thống sẽ giảm tốc, lưu tạm có giới hạn hay ngắt subscription.

## 8. Keepalive không phải request timeout

RSocket có frame `KEEPALIVE` ở cấp kết nối. Client gửi heartbeat định kỳ; hai đầu dùng phản hồi để nhận biết peer còn hoạt động. Trong RSocket Java, `RSocketConnector.keepAlive(interval, maxLifeTime)` cấu hình chu kỳ gửi và thời gian tối đa chờ heartbeat từ đầu bên kia. Giá trị mặc định trong RSocket Java là 20 giây và 90 giây.

Spring cho phép tùy chỉnh connector qua `RSocketRequester.Builder.rsocketConnector`:

```java
@Bean
RSocketRequester sensorRequester(RSocketRequester.Builder builder) {
    return builder
        .rsocketConnector(connector ->
            connector.keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90)
            )
        )
        .tcp("localhost", 7000);
}
```

Đây là cấu hình kết nối; nó không giới hạn thời gian xử lý của `sensor.read`, cũng không giới hạn số phút một stream được phép tồn tại. Một kết nối có thể vẫn khỏe trong khi một request cụ thể bị treo. Vì thế vẫn cần timeout ở cấp publisher.

Ngược lại, request-stream có thể im lặng trong thời gian dài dù kết nối còn khỏe. Nếu ứng dụng yêu cầu phát hiện im lặng ở cấp dữ liệu, hãy dùng `Flux.timeout` với ngưỡng phù hợp. Đừng giảm keepalive interval chỉ để thay thế timeout nghiệp vụ.

## 9. Xử lý lỗi và retry an toàn

Timeout là một lỗi có thể được xử lý bằng `onErrorResume`, `onErrorMap` hoặc `retryWhen`. Chọn hành vi dựa trên hợp đồng của thao tác:

- Dùng `onErrorMap` để chuyển `TimeoutException` thành lỗi miền nghiệp vụ, giữ nguyên cause để chẩn đoán.
- Dùng `onErrorResume` khi có fallback thực sự hợp lệ, ví dụ đọc từ cache với nhãn dữ liệu cũ.
- Chỉ retry khi request có thể thực hiện lặp an toàn hoặc có idempotency key. Khi client timeout, server có thể đã thực hiện thao tác nhưng phản hồi bị trễ hoặc thất lạc; retry một lệnh ghi có thể tạo tác dụng phụ hai lần.
- Giới hạn số lần retry, dùng backoff và tổng deadline. Retry không có giới hạn có thể khiến một request quá hạn tiếp tục chạy lâu hơn chính sách caller.
- Không bắt mọi exception rồi trả dữ liệu rỗng. Cần phân biệt timeout, lỗi nghiệp vụ, lỗi kết nối và lỗi giải mã.

Nếu server và client cùng đặt timeout, hãy chọn thứ tự hợp lý. Ví dụ server có thể giới hạn xử lý ở hai giây, còn client dành ba giây cho toàn bộ request để còn thời gian truyền lỗi và xử lý ở phía gọi. Các giá trị thực tế phải dựa trên SLA, độ trễ mạng và thời gian xử lý đo được.

## 10. Ví dụ Reactor chạy độc lập

Ví dụ sau dùng Reactor Core để minh họa ba trường hợp: request đơn không phản hồi, stream vô hạn bị giới hạn số phần tử, và stream bị ngắt khi không có dữ liệu mới. Đây là chương trình minh họa các toán tử Reactor; nó không mở kết nối RSocket thật.

**pom.xml** (Java 17+, Maven):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>rsocket-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
</project>
```

**TimeoutDemo.java**:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class TimeoutDemo {

    public static void main(String[] args) {
        String response = Mono.<String>never()
            .timeout(Duration.ofMillis(50))
            .onErrorResume(
                TimeoutException.class,
                error -> Mono.just("fallback")
            )
            .block();

        System.out.println("request = " + response);

        List<Long> stream = Flux.interval(Duration.ofMillis(10))
            .take(3)
            .collectList()
            .block();

        System.out.println("stream = " + stream);

        List<String> idle = Flux.concat(
                Flux.just("connected"),
                Mono.delay(Duration.ofMillis(200)).thenReturn("late")
            )
            .timeout(Duration.ofMillis(50))
            .onErrorResume(
                TimeoutException.class,
                error -> Flux.just("timed-out")
            )
            .collectList()
            .block();

        System.out.println("idle = " + idle);
    }
}
```

Chạy từ thư mục chứa `pom.xml` và `TimeoutDemo.java`.

Trên Linux/macOS:

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" TimeoutDemo.java
java -cp ".:$(cat cp.txt)" TimeoutDemo
```

Trên Windows PowerShell:

```powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\TimeoutDemo.java
java -cp ".;$cp" TimeoutDemo
```

Kết quả:

```text
request = fallback
stream = [0, 1, 2]
idle = [connected, timed-out]
```

Giải thích:

1. `Mono.never()` không phát dữ liệu và không hoàn tất. Sau 50 ms, `timeout` phát lỗi; `onErrorResume` chuyển sang giá trị dự phòng.
2. `Flux.interval` là nguồn phát liên tục. `take(3)` chỉ chuyển tiếp ba phần tử rồi hủy subscription upstream.
3. Stream thứ ba phát `connected` ngay, sau đó chờ 200 ms. Vì khoảng chờ vượt 50 ms, `timeout` hủy nguồn và chuyển sang publisher dự phòng `timed-out`.

Các lệnh `block()` trong chương trình chỉ dùng để quan sát kết quả của demo. Không dùng `block()` trong reactive request handler hoặc event loop của ứng dụng.

## 11. Kiểm thử timeout mà không phải chờ thời gian thật

Có thể dùng `StepVerifier` từ dependency `reactor-test` và virtual time để kiểm thử timeout nhanh, ổn định:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutPolicyTest {

    @Test
    void timesOutWhenNoResponseArrives() {
        StepVerifier.withVirtualTime(
                () -> Mono.<String>never().timeout(Duration.ofSeconds(3))
            )
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }
}
```

Thêm dependency kiểm thử:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <version>3.8.8</version>
    <scope>test</scope>
</dependency>
```

Nên kiểm thử thêm các tình huống: phản hồi đến trước deadline, Mono hoàn tất rỗng, stream phát đều, stream ngừng phát sau một vài phần tử, stream bị hủy bởi client, và cleanup được gọi đúng khi có cancellation. Với RSocket integration test, kiểm tra cả hai phía để xác nhận server dừng publisher và giải phóng tài nguyên sau khi client timeout.

## 12. Lỗi thường gặp

1. **Dùng `Flux.timeout` như deadline tổng.** Stream phát dữ liệu đều có thể tồn tại vô hạn. Kết hợp timeout theo khoảng im lặng với `take(Duration)` hoặc điều kiện kết thúc nghiệp vụ.
2. **Dùng KEEPALIVE làm timeout request.** Heartbeat chỉ phản ánh sức sống kết nối; request riêng vẫn có thể treo.
3. **Quên cancellation cleanup.** Client đã ngừng nhận nhưng server vẫn giữ subscription hoặc tài nguyên. Gắn cleanup với cancellation và kiểm tra publisher nguồn có tôn trọng hủy hay không.
4. **Gom stream vô hạn vào bộ nhớ.** `collectList()`, `cache()` không giới hạn hoặc buffer không giới hạn có thể làm bộ nhớ tăng liên tục.
5. **Retry mọi timeout.** Server có thể đã thực hiện thao tác trước khi caller hết thời gian chờ. Retry lệnh ghi cần idempotency.
6. **Nuốt lỗi timeout bằng fallback không rõ nghĩa.** Caller sẽ không phân biệt được dữ liệu thật với dữ liệu dự phòng.
7. **Tạo subscription thủ công trong handler.** Tự gọi `subscribe()` làm Spring mất quyền quản lý vòng đời request. Hãy trả publisher từ handler.
8. **Đặt timeout quá ngắn.** Timeout cần tính cả độ trễ mạng, tải hệ thống, thời gian xử lý và jitter; theo dõi tỷ lệ timeout để điều chỉnh bằng số liệu.

## 13. Quy trình chọn chính sách

Khi thiết kế một endpoint RSocket, hãy trả lời lần lượt:

1. Endpoint trả về một kết quả hay nhiều kết quả? Chọn `Mono` hoặc `Flux` tương ứng.
2. Nếu không có phản hồi đầu tiên, caller chờ tối đa bao lâu? Đặt `Mono.timeout` hoặc timeout đầu tiên cho stream.
3. Với stream, khoảng im lặng bao lâu thì được xem là bất thường? Đặt `Flux.timeout`.
4. Stream có được chạy mãi không? Nếu không, đặt giới hạn tổng bằng `take(Duration)`, giới hạn số phần tử hoặc điều kiện nghiệp vụ.
5. Khi caller rời đi hoặc timeout, server cần giải phóng những tài nguyên nào? Dùng cancellation-aware publisher, `doFinally` hoặc `usingWhen`.
6. Khi consumer chậm, hệ thống giảm tốc, buffer có giới hạn hay bỏ dữ liệu? Xác định chính sách backpressure và overflow.
7. Timeout có được retry an toàn không? Kiểm tra idempotency và tổng deadline trước khi bật retry.

Một chính sách tốt phân biệt rõ timeout của một phản hồi, timeout do stream im lặng, và thời gian tồn tại tối đa của subscription. Khi ba giới hạn này được thiết kế cùng với cancellation, cleanup và backpressure, request RSocket có thể kết thúc dự đoán được mà không để lại công việc hoặc tài nguyên không còn cần thiết.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, request interaction models, `retrieveMono` và `retrieveFlux`.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `timeout`, `take`, `takeUntil`, `doFinally` và các toán tử điều khiển stream.
- [RSocket Protocol Specification](https://github.com/rsocket/rsocket/blob/master/Protocol.md): `REQUEST_N`, `CANCEL`, `KEEPALIVE` và vòng đời stream.
- [RSocketConnector Javadoc](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketConnector.html): cấu hình keepalive ở cấp kết nối.
