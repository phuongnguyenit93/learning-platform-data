# Đảm bảo lỗi hệ thống giám sát không làm gián đoạn chức năng nghiệp vụ

## 1. Xác định đúng ranh giới giữa nghiệp vụ và dữ liệu chẩn đoán

Ứng dụng cần metric, log và trace để người vận hành phát hiện, giải thích và xử lý sự cố. Nhưng việc hệ thống nhận trace mất kết nối không nên biến một thao tác đặt hàng hợp lệ thành lỗi. Tương tự, dashboard không truy cập được không phải lý do tự động dừng mọi bản sao ứng dụng.

Mục tiêu là **cô lập lỗi của đường thu thập dữ liệu quan sát khỏi đường xử lý nghiệp vụ**, đồng thời cho phép người vận hành biết rằng khả năng quan sát đang suy giảm.

Ví dụ, một thao tác xác nhận đơn hàng có hai kết quả khác nhau:

- Đơn hàng đã được ghi nhận theo hợp đồng nghiệp vụ.
- Dữ liệu chẩn đoán về thao tác đó đã được xuất tới hệ thống giám sát hay chưa.

Không được đồng nhất hai kết quả. Nếu đơn hàng đã xác nhận nhưng gửi trace thất bại, trả lỗi và yêu cầu khách gửi lại có thể tạo một lần xử lý nghiệp vụ nữa.

Phân biệt ngay từ thiết kế:

| Loại dữ liệu/công việc | Chính sách phù hợp |
| --- | --- |
| Metric hiệu năng, trace chẩn đoán, log vận hành được phép mất | Tiếp tục nghiệp vụ khi đường xuất dữ liệu lỗi, với giới hạn tài nguyên rõ ràng |
| Sự kiện cần thiết để hoàn tất hợp đồng nghiệp vụ | Thiết kế độ bền và xác nhận theo hợp đồng đó |
| Bản ghi đối soát hoặc audit mà nghiệp vụ yêu cầu phải lưu | Không đưa vào hàng đợi chẩn đoán được phép bỏ |
| Lỗi thật của cơ sở dữ liệu, kiểm tra đầu vào hoặc quyền truy cập | Vẫn xử lý như lỗi nghiệp vụ, không che bằng cơ chế bỏ qua lỗi giám sát |

Nếu một sự kiện phải được lưu cùng giao dịch, hãy xem nó là dữ liệu nghiệp vụ và dùng cơ chế bền vững phù hợp, chẳng hạn ghi trong cùng giao dịch hoặc thiết kế outbox. Không đổi tên sự kiện thành “log” rồi cho phép bỏ khi đầy hàng đợi.

OpenTelemetry cũng đặt mục tiêu không để lỗi runtime của SDK/exporter làm thay đổi đáng kể hành vi ứng dụng. Đây là yêu cầu thiết kế thư viện, không thay thế việc kiểm chứng mã tùy biến và cấu hình thực tế. [Nguyên tắc xử lý lỗi OpenTelemetry](https://opentelemetry.io/docs/specs/otel/error-handling/)

## 2. Hiểu những đường mà lỗi giám sát có thể lan sang nghiệp vụ

### 2.1. Gọi mạng đồng bộ trong xử lý yêu cầu

Thiết kế dễ gây lỗi:

```text
Nhận yêu cầu
    → xử lý giao dịch
    → gọi hệ thống nhận telemetry và chờ
    → trả kết quả
```

Nếu bước xuất dữ liệu chờ 10 giây, yêu cầu cũng có thể bị giữ lại tương ứng. Nhiều yêu cầu cùng chờ làm cạn luồng, kết nối hoặc bộ nhớ.

Một biến thể khác là gửi telemetry trong finally rồi để exception của exporter che mất exception nghiệp vụ ban đầu. Khi đó người vận hành còn nhận được nguyên nhân lỗi sai.

### 2.2. Chuyển sang nền nhưng không giới hạn tài nguyên

Đưa công việc sang executor chưa đủ. Một hàng đợi không giới hạn sẽ tích lũy dữ liệu khi backend ngừng nhận. Tạo một luồng cho mỗi sự kiện hoặc dùng chung pool đang xử lý nghiệp vụ cũng có thể làm ứng dụng quá tải.

Cơ chế giới hạn phải bao gồm cả:

- Số phần tử trong hàng đợi.
- Kích thước của mỗi phần tử và batch.
- Số công việc đang chạy.
- Thời gian kết nối, gửi và chờ phản hồi.
- Số lần thử lại và tổng thời gian giữ dữ liệu.
- Công việc được làm khi ứng dụng dừng.

### 2.3. Logging và callback metric vẫn có thể gây chặn

Appender gọi mạng trực tiếp, ghi đĩa chậm hoặc stdout bị nghẽn đều có thể giữ luồng đang ghi log.

Với metric, callback đo gauge có thể được gọi khi lấy mẫu. Nếu callback tự chạy truy vấn cơ sở dữ liệu hoặc gọi dịch vụ khác, một lần scrape có thể kích hoạt công việc tốn tài nguyên. Gauge nên đọc một trạng thái đã có với chi phí nhỏ và rõ ràng. [Cách lấy mẫu gauge Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)

Việc gọi “chỉ là giám sát” không làm công việc đó miễn phí.

### 2.4. Dùng backend giám sát làm điều kiện phục vụ

Nếu readiness thất bại chỉ vì collector mất kết nối, bộ điều phối có thể rút một ứng dụng vẫn xử lý nghiệp vụ được khỏi lưu lượng. Nếu liveness phụ thuộc collector, nhiều bản sao còn có thể bị khởi động lại cùng lúc.

Kết quả là một sự cố của hệ thống quan sát lan thành sự cố của hệ thống được quan sát.

## 3. Thiết kế đường xuất dữ liệu có giới hạn

Một cấu trúc phù hợp cho dữ liệu chẩn đoán được phép mất:

```text
Luồng nghiệp vụ
    → ghi nhận trạng thái nhỏ / đưa bản ghi vào bộ đệm hữu hạn
    → tiếp tục xử lý

Luồng xuất dữ liệu riêng
    → lấy bản ghi hoặc batch
    → xuất với timeout
    → thành công hoặc ghi nhận lỗi xuất
    → thử lại có giới hạn hoặc bỏ theo chính sách
```

Cấu trúc này cần năm quyết định cụ thể.

### 3.1. Không chờ chỗ trống trong đường nghiệp vụ

Khi bộ đệm đầy, chọn chính sách đã phê duyệt: bỏ bản ghi mới, bỏ dữ liệu cũ, giảm mức chi tiết hoặc giảm tỷ lệ thu thập. Với dữ liệu chẩn đoán được phép mất, không tự động chuyển sang chờ vô hạn.

Không dùng chính sách khiến công việc xuất dữ liệu quay lại chạy trên luồng gọi khi executor đầy. Trong trường hợp đó, “bất đồng bộ” lại trở thành gửi đồng bộ đúng lúc backend đang gặp vấn đề.

### 3.2. Giới hạn cả số lượng lẫn kích thước

Giả sử 2.000 bản ghi/giây, mỗi bản ghi chiếm 400 byte dữ liệu trong mô hình, bộ đệm chứa 1.000 bản ghi:

```text
Dữ liệu phần tử ≈ 1.000 × 400 = 400.000 byte
Thời gian lấp đầy khi không xuất được ≈ 1.000 / 2.000 = 0,5 giây
```

Bộ nhớ thật còn gồm đối tượng, cấu trúc hàng đợi, dữ liệu đang xử lý và batch đã dựng.

Muốn giữ năm phút ở cùng lưu lượng cần khoảng 600.000 bản ghi, tức 240.000.000 byte dữ liệu theo mô hình, chưa tính phần phụ trội. Đó là một lựa chọn tài nguyên lớn, không phải chỉ đổi một số cấu hình nhỏ.

Không giữ nguyên request, response hoặc entity có đồ thị đối tượng lớn trong queue. Chụp một bản ghi nhỏ, bất biến và giới hạn trường ngay lúc ghi nhận.

### 3.3. Tách tài nguyên nhưng vẫn theo dõi phần dùng chung

Dùng worker và client riêng giúp giới hạn ảnh hưởng tới pool nghiệp vụ. Tuy nhiên, hai phần vẫn có thể dùng chung CPU, heap, mạng và đĩa.

Collector riêng hoặc sidecar có thể tách một phần công việc xử lý/export, nhưng cũng cần giới hạn tài nguyên, queue và retry của chính nó. [Khả năng phục hồi của OpenTelemetry Collector](https://opentelemetry.io/docs/collector/resiliency/)

Cô lập có nhiều mức; một worker nền trong cùng JVM không phải bảo đảm tuyệt đối trước mọi lỗi cạn tài nguyên.

### 3.4. Timeout và retry phải có ngân sách

Timeout cần áp dụng ở client thực sự gửi dữ liệu. Chỉ đặt thời gian chờ ở phía gọi mà công việc mạng vẫn chạy tiếp có thể làm tích lũy tác vụ.

Retry cần backoff, độ lệch thời gian ngẫu nhiên khi phù hợp và giới hạn tổng công việc. Không retry lỗi xác thực hoặc dữ liệu không hợp lệ với tần suất cao như thể đó là lỗi mạng thoáng qua.

Một lần timeout cũng không chứng minh bên nhận chưa lưu dữ liệu. Tránh tự suy ra bảo đảm “chỉ gửi đúng một lần” chỉ từ cơ chế timeout/retry.

### 3.5. Dừng và khôi phục cũng phải có giới hạn

Không force flush toàn bộ telemetry sau mỗi yêu cầu nghiệp vụ. Khi tắt ứng dụng, dành ngân sách xả bộ đệm hữu hạn rồi áp dụng chính sách cho phần còn lại.

Khi backend hoạt động lại, không xả backlog bằng một đợt gửi vô hạn làm nó quá tải lần nữa. Giới hạn tốc độ và đo khả năng hồi phục trong lúc vẫn có dữ liệu mới.

## 4. Ví dụ Java: exporter lỗi và queue đầy không đổi kết quả nghiệp vụ

Chương trình độc lập dưới đây dùng Java 17+, không cần Spring hay thư viện ngoài. Nó minh họa **kênh chẩn đoán tự viết**, không phải triển khai thay thế Micrometer hoặc OpenTelemetry SDK.

Hai bài thử:

1. Sender ném IOException, nhưng nghiệp vụ vẫn có kết quả CONFIRMED.
2. Sender đang bị giữ lại, queue có hai phần tử, phần tử thêm tiếp bị từ chối mà luồng gọi không chờ chỗ trống.

Lưu thành `MonitoringIsolationDemo.java`:

```java
import java.io.IOException;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public class MonitoringIsolationDemo {
    enum EventKind { ORDER_CONFIRMED }

    record DiagnosticEvent(EventKind kind, long durationNanos) {}

    @FunctionalInterface
    interface Sender {
        void send(DiagnosticEvent event) throws Exception;
    }

    static final class BestEffortSink implements AutoCloseable {
        private final ArrayBlockingQueue<DiagnosticEvent> queue;
        private final Sender sender;
        private final Thread worker;
        private final LongAdder rejected = new LongAdder();
        private final LongAdder exportFailures = new LongAdder();
        // Chỉ dùng để đồng bộ hóa bài thử, không thuộc luồng nghiệp vụ.
        private final CountDownLatch firstHandled = new CountDownLatch(1);
        private volatile boolean running = true;

        BestEffortSink(int capacity, Sender sender) {
            this.queue = new ArrayBlockingQueue<>(capacity);
            this.sender = sender;
            this.worker = new Thread(this::drain, "diagnostic-exporter");
            this.worker.setDaemon(true);
            this.worker.start();
        }

        boolean tryPublish(DiagnosticEvent event) {
            if (event == null || !running || !queue.offer(event)) {
                rejected.increment();
                return false;
            }
            return true;
        }

        private void drain() {
            while (running) {
                try {
                    DiagnosticEvent event = queue.poll(200, TimeUnit.MILLISECONDS);
                    if (event == null) {
                        continue;
                    }
                    try {
                        sender.send(event);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return;
                    } catch (Exception exportFailure) {
                        exportFailures.increment();
                    } finally {
                        firstHandled.countDown();
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }

        @Override
        public void close() {
            running = false;
            worker.interrupt();
            queue.clear();
        }
    }

    static String confirmOrder() {
        // Đại diện kết quả nghiệp vụ; bài thử không truy cập cơ sở dữ liệu.
        return "CONFIRMED";
    }

    static DiagnosticEvent event() {
        return new DiagnosticEvent(EventKind.ORDER_CONFIRMED, 1_000_000);
    }

    public static void main(String[] args) throws Exception {
        try (BestEffortSink sink = new BestEffortSink(2, ignored -> {
            throw new IOException("collector unavailable");
        })) {
            String result = confirmOrder();
            boolean accepted = sink.tryPublish(event());

            // Chờ chỉ để xác minh bài thử, không làm trong xử lý yêu cầu thật.
            if (!sink.firstHandled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Exporter test did not finish");
            }
            System.out.println("business=" + result);
            System.out.println("offerAccepted=" + accepted);
            System.out.println("exportFailures=" + sink.exportFailures.sum());
        }

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try (BestEffortSink sink = new BestEffortSink(2, ignored -> {
            entered.countDown();
            release.await();
        })) {
            sink.tryPublish(event());
            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queue test did not start");
            }

            sink.tryPublish(event());
            sink.tryPublish(event());
            String result = confirmOrder();
            boolean overflowAccepted = sink.tryPublish(event());

            System.out.println("businessWhenFull=" + result);
            System.out.println("overflowAccepted=" + overflowAccepted);
            System.out.println("queueRejected=" + sink.rejected.sum());
        } finally {
            release.countDown();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```text
javac -encoding UTF-8 MonitoringIsolationDemo.java
java MonitoringIsolationDemo
```

Stdout:

```text
business=CONFIRMED
offerAccepted=true
exportFailures=1
businessWhenFull=CONFIRMED
overflowAccepted=false
queueRejected=1
```

### 4.1. Điều gì tạo ra kết quả này?

- confirmOrder() trong bài thử chỉ đại diện cho kết quả nghiệp vụ, không giả lập một giao dịch cơ sở dữ liệu thật.
- Luồng gọi chỉ thử queue.offer(), không gọi sender.send().
- offer() không chờ dung lượng trống khi queue đầy; nó vẫn có chi phí đồng bộ hóa nội bộ, không phải thao tác được bảo đảm thời gian bằng không.
- Sender chạy trong một worker riêng.
- Exception của sender được xử lý trong đúng phạm vi xuất dữ liệu.
- Khi queue đầy, tryPublish() trả false và tăng số đếm bị từ chối.
- CountDownLatch chỉ đồng bộ bài thử; không thêm await() này vào controller hoặc transaction thực tế.

ArrayBlockingQueue có dung lượng cố định; offer và put có hành vi khác nhau khi đầy. [API ArrayBlockingQueue của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)

### 4.2. Giới hạn phải hiểu trước khi áp dụng

Ví dụ cố ý không retry và không bảo đảm giao dữ liệu. offerAccepted=true chỉ có nghĩa bản ghi đã vào bộ đệm tại thời điểm gọi, không có nghĩa backend đã nhận.

close() dừng nhận theo trạng thái, interrupt worker và bỏ dữ liệu đang đợi; nó không xả hết queue, không đợi worker kết thúc và không bảo đảm sender tùy ý sẽ chịu dừng theo interrupt. Một luồng exporter mắc kẹt không được “chữa” bằng việc đặt daemon.

Khi dùng thực tế, sender cần timeout tại tầng I/O, chính sách vòng đời và giới hạn batch. Cũng cần xác định hành vi khi publish đồng thời với shutdown; không dùng queue này cho bản ghi bắt buộc phải lưu.

Chương trình bắt Exception từ sender, không che các lỗi nghiêm trọng của JVM bằng catch Throwable rồi coi tiến trình vẫn bình thường. Lỗi lập trình trong mã nghiệp vụ vẫn phải được xử lý theo hợp đồng của nghiệp vụ.

## 5. Áp dụng với Spring Boot 3.3 và các đường telemetry chuẩn

### 5.1. Dùng cơ chế sẵn có, kiểm tra cấu hình thực sự có hiệu lực

Spring Boot hỗ trợ tracing qua Micrometer và các tracer/exporter tương ứng. [Tracing Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)

Trong cấu hình OpenTelemetry của Spring Boot 3.3.13, auto-configuration tạo BatchSpanProcessor. [Mã auto-configuration OpenTelemetry](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/OpenTelemetryAutoConfiguration.java)

Batch processor có bộ đệm và chính sách xử lý khi đầy. Các giới hạn queue, batch, export và shutdown phải được kiểm tra ở phiên bản SDK đang dùng. [Batch processor trong OpenTelemetry SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/#batching-processor)

Không mặc định queue của trace SDK, queue của collector và queue của log appender là cùng một bộ đệm. Mỗi tầng có thể giữ dữ liệu và dùng tài nguyên riêng.

Cũng không mặc định mọi biến OTEL_* hoặc thuộc tính tìm thấy ở phiên bản Spring Boot khác đều điều khiển SDK trong ứng dụng hiện tại. Xác minh bằng cấu hình, đối tượng thực tế và phép thử lỗi; chú ý SDK được tạo bởi auto-configuration, mã tùy biến hay Java agent.

### 5.2. Ví dụ timeout cho đúng đường OTLP

Khối sau là cấu hình bổ sung cho hệ thống **đã có** OTLP HTTP tracing và OTLP metrics tương ứng:

```yaml
management:
  otlp:
    tracing:
      endpoint: http://collector:4318/v1/traces
      timeout: 2s
    metrics:
      export:
        url: http://collector:4318/v1/metrics
        connect-timeout: 500ms
        read-timeout: 2s
        step: 30s
  tracing:
    sampling:
      probability: 0.05
```

Spring Boot 3.3 có timeout OTLP tracing cho lời gọi xuất batch và các timeout riêng của OTLP metrics. [Thuộc tính OTLP Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Các giá trị là ví dụ để thử nghiệm, không phải ngân sách chung cho mọi ứng dụng. Timeout exporter không thay thế timeout của yêu cầu HTTP nghiệp vụ; hai đường có mục tiêu khác nhau.

Khối này không tự tạo exporter khi thiếu dependency, không cấu hình Zipkin và không cấu hình toàn bộ giới hạn queue. Nếu hệ thống chỉ dùng Prometheus pull, không thêm OTLP chỉ để sao chép ví dụ.

Giảm sampling có thể giảm tải trace, nhưng không phải circuit breaker và không tự cô lập mạng. Khi trace đã có quyết định từ cha hoặc có sampler tùy biến, cần kiểm tra cách tỷ lệ thực sự được áp dụng.

### 5.3. Đường metrics pull và push có đặc điểm khác nhau

Prometheus pull lấy dữ liệu từ endpoint của ứng dụng. Prometheus ngừng hoạt động không buộc ứng dụng phải gọi ngược lại để gửi từng metric.

Với registry dạng push, dữ liệu được xuất theo cơ chế của registry tương ứng. Spring Boot cấu hình registry theo thư viện có trên classpath. [Registry và export metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)

Cả hai vẫn cần bảo vệ tài nguyên: tránh tag không giới hạn, callback đo tốn chi phí và quá nhiều công việc khi scrape/export. Không biến callback metric thành nơi gọi backend giám sát để hỏi nó có đang hoạt động không.

Nếu ứng dụng có nhiều registry hoặc vừa dùng agent vừa dùng SDK trong ứng dụng, kiểm tra việc instrument/export trùng. Không coi có hai đường gửi là cơ chế dự phòng tự động nếu chúng cùng tăng tải lên một backend.

### 5.4. Có phương án tạm giảm chức năng quan sát

Cần chuẩn bị cách tạm dừng exporter hỏng hoặc giảm mức thu thập mà vẫn giữ đường nghiệp vụ. Ví dụ, với auto-configuration tương ứng của Spring Boot:

```yaml
management:
  otlp:
    metrics:
      export:
        enabled: false
  tracing:
    enabled: false
```

Khối này có tác động khác nhau: tắt OTLP metrics export và tắt auto-configuration tracing, có thể làm mất cả phần propagation/correlation do phần đó cung cấp. Nó không tự tắt Java agent hoặc exporter tự tạo ngoài phạm vi thuộc tính.

Đây là phương án phải diễn tập trước, không phải cấu hình mặc định được khuyến nghị. Xác minh cách áp dụng cấu hình của ứng dụng; không giả định sửa một tệp là tiến trình đang chạy tự nhận ngay.

Khi dùng phương án giảm chức năng, ghi thời điểm bắt đầu, phạm vi tín hiệu mất và điều kiện bật lại. Không để việc tạm ngừng quan sát trở thành trạng thái không ai sở hữu.

## 6. Logging, health và vòng đời ứng dụng phải tuân thủ cùng ranh giới

### 6.1. Async logging cần chính sách khi đầy

Appender bất đồng bộ có thể vẫn chặn khi queue đầy. Với Logback, kiểm tra cấu hình neverBlock, ngưỡng bỏ dữ liệu và thời gian flush của đúng phiên bản; đừng suy ra an toàn chỉ từ tên AsyncAppender. [Mã AsyncAppenderBase của Logback](https://raw.githubusercontent.com/qos-ch/logback/v_1.5.6/logback-core/src/main/java/ch/qos/logback/core/AsyncAppenderBase.java)

Với log chẩn đoán được phép mất, có thể chọn không chờ khi đầy và chấp nhận bỏ log theo chính sách. Không áp dụng lựa chọn đó cho toàn bộ audit bắt buộc chỉ vì chúng đang cùng đi qua một appender.

Công việc dựng thông điệp có thể vẫn diễn ra trên luồng gọi: serialize đối tượng lớn, đọc dữ liệu lười tải hoặc lấy khóa để tạo log vẫn có thể làm chậm nghiệp vụ.

Khi exporter lỗi liên tục, không ghi một stack trace lớn cho từng bản ghi rồi đưa log đó qua chính exporter đang lỗi. Dùng thông báo có giới hạn tần suất, số đếm gọn và đường chẩn đoán độc lập phù hợp.

### 6.2. Không biến lỗi collector thành lỗi liveness

Liveness không nên phụ thuộc vào hệ thống ngoài. Readiness chỉ nên xét những điều kiện quyết định khả năng nhận yêu cầu của dịch vụ. [Health probes Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

Ví dụ, nếu nghiệp vụ không cần collector để xử lý một đơn hàng, collector mất kết nối không tự là lý do loại mọi pod khỏi phục vụ.

Một cấu hình minh họa dùng availability nội bộ:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: [livenessState]
        readiness:
          include: [readinessState]
```

Đây là ví dụ phạm vi nhóm, không chứng minh mọi điều kiện readiness của dịch vụ đã đầy đủ. Khi sửa ứng dụng hiện có, giữ các điều kiện nghiệp vụ thực sự cần thiết và loại riêng phụ thuộc giám sát không cần thiết.

Có thể cung cấp trạng thái “khả năng quan sát suy giảm” riêng cho người vận hành. Không gán trực tiếp trạng thái đó vào quyết định restart hoặc readiness nếu hợp đồng phục vụ không yêu cầu.

### 6.3. Không chờ backend giám sát vô hạn lúc khởi động và dừng

Ứng dụng không nên chờ collector sẵn sàng vô hạn mới hoàn tất một khởi động hợp lệ. Kiểm tra các hook tùy biến có đang gọi mạng trong constructor, tạo bean hoặc kiểm tra sau khởi động hay không.

Tuy nhiên, cấu hình sai, dependency không tương thích hoặc lỗi lập trình lúc khởi tạo có thể cần làm tiến trình khởi động thất bại rõ ràng. “Không phụ thuộc vào độ sẵn sàng của backend” không đồng nghĩa “bỏ qua mọi cấu hình không hợp lệ”.

Khi dừng, ưu tiên hoàn tất chính sách xử lý yêu cầu và dành phần ngân sách hữu hạn cho telemetry. Không giữ tiến trình mãi chỉ để chờ backend đang mất kết nối.

## 7. Nghiệm thu bằng cách chủ động làm đường giám sát gặp lỗi

Chỉ chứng minh ứng dụng hoạt động khi mọi thành phần đều khỏe chưa đủ. Phải thử khi thành phần quan sát không đáp ứng, đồng thời đo trực tiếp kết quả nghiệp vụ.

### 7.1. Đặt tiêu chí trước khi thử

Ghi một tập tiêu chí cho dịch vụ cụ thể:

- Giao dịch thành công không bị đổi thành lỗi chỉ vì xuất telemetry thất bại.
- Lỗi nghiệp vụ thật vẫn được trả và ghi nhận đúng, không bị che.
- Độ trễ nghiệp vụ nằm trong ngân sách đã chấp nhận khi telemetry gặp vấn đề.
- Số luồng, heap và queue đạt giới hạn đã thiết kế, không tăng liên tục.
- Không có vòng restart hoặc rút khỏi phục vụ chỉ do backend giám sát lỗi.
- Mất dữ liệu quan sát được phát hiện và có người xử lý.
- Khi phục hồi, không gây một đợt tải xuất dữ liệu không kiểm soát.

Không dùng một tỷ lệ tăng độ trễ cố định cho mọi dịch vụ. Đặt ngân sách từ mục tiêu phục vụ và tải thực tế.

### 7.2. Ma trận lỗi cần thử

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Backend từ chối kết nối | Export thất bại có giới hạn; yêu cầu nghiệp vụ vẫn hoàn tất |
| Backend chấp nhận kết nối nhưng phản hồi rất chậm | Timeout có hiệu lực; queue và worker không tăng ngoài giới hạn |
| Lỗi DNS hoặc TLS | Không làm cạn luồng nghiệp vụ; có chẩn đoán đúng nguyên nhân |
| Backend trả 429 hoặc lỗi máy chủ | Retry/backoff không tạo đợt gửi dồn hoặc vòng lặp không giới hạn |
| Queue đầy | Chính sách bỏ/từ chối hoạt động, không chuyển I/O sang luồng gọi |
| Đường logging chậm hoặc không ghi được | Không chặn ngoài ngân sách; biết log có thể mất |
| Prometheus dừng scrape | Phân biệt mất số liệu với sự cố nghiệp vụ; ứng dụng vẫn được kiểm chứng trực tiếp |
| Khởi động khi collector đang dừng | Không bị giữ vô hạn bởi hook giám sát không thiết yếu |
| Dừng ứng dụng khi backend lỗi | Hoàn tất vòng đời trong ngân sách, không chờ flush vô hạn |
| Backend hoạt động lại | Phục hồi có giới hạn, không trùng/xả tải ngoài chính sách |

“Connection refused” thường trả về nhanh, nên không thay thế bài thử kết nối còn mở nhưng không có phản hồi. Hai tình huống kiểm tra những giới hạn khác nhau.

### 7.3. Đo qua một đường kiểm chứng độc lập

Khi hệ thống giám sát đang là đối tượng gây lỗi, không dùng riêng dashboard của chính nó để kết luận nghiệp vụ còn hoạt động.

Dùng bộ tạo tải hoặc client kiểm chứng có ghi lại mã trạng thái, độ trễ và kết quả nghiệp vụ; khi cần, đối chiếu dữ liệu đã lưu trong hệ thống nghiệp vụ theo cách kiểm thử được phép.

Đồng thời kiểm tra luồng đang chờ, heap, queue và trạng thái tiến trình bằng công cụ độc lập phù hợp. Không biến việc đo kiểm thành một tác vụ tạo thêm tải vượt khả năng ứng dụng.

## 8. Làm suy giảm có kiểm soát nhưng không che mất sự cố quan sát

Việc chấp nhận bỏ telemetry cần đi kèm khả năng biết nó đang bị bỏ. Tối thiểu phải có cách xác định:

- Đường nào đang mất dữ liệu: metric, trace hay log.
- Nguyên nhân là sampling chủ đích, queue đầy, timeout, lỗi cấu hình hay lỗi bên nhận.
- Số liệu nào chỉ phản ánh một phần của hệ thống.
- Lần xuất thành công gần nhất và tình trạng backlog nếu có.
- Ai sở hữu việc phục hồi và tiêu chí xác nhận đã khôi phục.

Số đếm lỗi xuất và queue là hữu ích, nhưng nếu chúng chỉ được gửi qua đúng đường đang hỏng thì không phải cơ chế phát hiện độc lập. Chọn đường bổ sung phù hợp: log cục bộ có giới hạn, trạng thái quản trị nội bộ, giám sát hạ tầng hoặc một phép kiểm tra từ bên ngoài.

Không hiển thị “0 lỗi nghiệp vụ” chỉ vì không nhận được metric. Phản hồi của hệ thống cần phân biệt dịch vụ ít tải, dịch vụ thực sự lỗi và khả năng quan sát bị mất.

Cũng không mở một endpoint quản trị không bảo vệ ra Internet để giải quyết vấn đề mất quan sát. Đường dự phòng vẫn phải có phạm vi truy cập và ngân sách riêng.

## 9. Bài thực hành và điều kiện hoàn thành

Chọn một dịch vụ Spring Boot thí nghiệm có API nghiệp vụ và đường xuất telemetry đã xác định.

1. Vẽ đường đi từ controller/service tới metric, trace và log; đánh dấu mọi lời gọi mạng, queue và pool.
2. Ghi dung lượng queue, giới hạn phần tử/batch, timeout, retry và ngân sách shutdown của từng đường.
3. Chạy ví dụ Java để phân biệt lỗi exporter với lỗi nghiệp vụ.
4. Trong môi trường thí nghiệm, lần lượt làm backend từ chối kết nối, phản hồi chậm và phục hồi.
5. Đối chiếu kết quả nghiệp vụ bằng client độc lập, không chỉ bằng dashboard.
6. Kiểm tra readiness/liveness không thay đổi chỉ vì phụ thuộc giám sát không thiết yếu bị lỗi.
7. Xác nhận dữ liệu bị bỏ và khả năng quan sát suy giảm được thể hiện đúng cho người vận hành.

Báo cáo kết quả cần có tải thử, ngân sách, giới hạn đo được, phần dữ liệu có thể mất và những lỗi chưa được thử. Không ghi “đã bảo đảm hoàn toàn” chỉ vì một lần gửi tới collector thất bại mà API vẫn trả 200.

Thiết kế đạt yêu cầu khi đường nghiệp vụ có ranh giới rõ với đường chẩn đoán, tài nguyên của phần quan sát được giới hạn và các tình huống mất quan sát đã được thử với bằng chứng về kết quả nghiệp vụ.
