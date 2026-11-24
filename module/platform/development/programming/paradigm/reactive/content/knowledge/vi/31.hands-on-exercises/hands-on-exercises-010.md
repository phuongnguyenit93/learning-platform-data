# Đo tải, phát hiện lời gọi chặn và so sánh các mô hình thực thi

Bài thực hành này xây dựng một phép thử nhỏ trên Spring WebFlux để so sánh ba cách thực hiện cùng một công việc mất khoảng 100 ms: gọi API blocking trực tiếp trên thread đang subscribe pipeline, cô lập API blocking trên scheduler dành cho blocking, và dùng một thao tác reactive không chặn để mô phỏng thời gian chờ I/O.

Sau đó, dùng BlockHound để phát hiện lời gọi chặn trên scheduler non-blocking và dùng k6 để tạo tải với arrival rate cố định. Bạn sẽ quan sát thread thực thi, throughput, latency percentiles, lỗi và số iteration bị bỏ lỡ; từ đó giải thích vì sao ba cách có hành vi khác nhau.

Mục tiêu không phải tìm một con số benchmark tuyệt đối. Bạn cần tạo được một quy trình đo có thể lặp lại, giữ workload như nhau giữa các biến thể và đưa ra kết luận dựa trên số liệu thu được.

## 1. Mục tiêu và kết quả cần nộp

Sau khi hoàn thành, bạn cần:

- Tạo ba endpoint có cùng thời gian xử lý danh nghĩa.
- Quan sát thread thực hiện phần công việc ở từng endpoint.
- Viết một test BlockHound chứng minh blocking call bị phát hiện trên scheduler non-blocking.
- Chạy cùng một k6 workload cho cả ba endpoint.
- Ghi throughput, p50, p95, p99, error rate và `dropped_iterations`.
- Giải thích khác biệt giữa blocking trực tiếp, blocking được cô lập và I/O reactive không chặn.
- Đề xuất giới hạn concurrency và cách bảo vệ hệ thống khi tải vượt capacity.

**Kết quả cần lưu trong báo cáo thực hành:** mã nguồn ba endpoint, test BlockHound, file k6, bảng số liệu của ba lần chạy và phần nhận xét dựa trên số liệu thực tế. Không điền số đo giả định hoặc lấy kết quả của máy khác làm kết quả của mình.

## 2. Chuẩn bị môi trường

Dùng một ứng dụng Spring Boot có WebFlux và Project Reactor. Các thành phần cần có:

| Thành phần | Mục đích |
|---|---|
| Java 17 trở lên | Chạy ứng dụng và test |
| `spring-boot-starter-webflux` | HTTP server reactive |
| `reactor-test` | `StepVerifier` |
| BlockHound | Phát hiện một số lời gọi blocking trên thread non-blocking |
| k6 | Tạo tải HTTP có arrival rate xác định |
| Công cụ metrics/log | Quan sát latency, thread, CPU và memory |

Đảm bảo ứng dụng chạy bằng WebFlux/Reactor Netty. Nếu project có cả Spring MVC và WebFlux, kiểm tra runtime thực tế đang dùng server nào; chỉ có dependency WebFlux không đảm bảo ứng dụng đã chạy theo mô hình reactive nếu framework chọn MVC.

Trong bài lab, một hàm giả lập dùng `Thread.sleep(100)` để đại diện cho SDK cũ hoặc thư viện đồng bộ phải chờ I/O. Đây là chủ ý tạo tình huống blocking để quan sát. Không dùng `Thread.sleep` làm cách mô phỏng hoặc triển khai I/O trong code production.

## 3. Tạo API blocking mô phỏng

Tạo một client giả lập lời gọi đồng bộ:

~~~java
import org.springframework.stereotype.Component;

@Component
final class LegacyCatalogClient {
    String find(String id) {
        try {
            Thread.sleep(100);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Legacy lookup interrupted", error);
        }

        return "item-" + id;
    }
}
~~~

`find` giữ thread gọi trong khoảng 100 ms. Khi số request tăng, mỗi lời gọi cần một thread trong suốt thời gian chờ. Thời gian này không tiêu thụ nhiều CPU, nhưng thread vẫn bị chiếm.

Tạo kiểu kết quả để endpoint trả lại cả dữ liệu và tên thread thực thi:

~~~java
record LabResult(String value, String workerThread) {}
~~~

Tên thread giúp xác minh nơi công việc đã chạy. Không dùng tên thread làm metric tag có cardinality cao trong production; trong bài lab, nó chỉ là thông tin chẩn đoán trong response.

## 4. Tạo ba endpoint để so sánh

Tạo controller sau. Các kiểu `LegacyCatalogClient` và `LabResult` là những kiểu vừa định nghĩa trong bài:

~~~java
import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
class ExecutionModelLabController {
    private final LegacyCatalogClient legacyClient;

    ExecutionModelLabController(LegacyCatalogClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    @GetMapping("/lab/blocking-direct/{id}")
    Mono<LabResult> blockingDirect(@PathVariable String id) {
        return Mono.fromCallable(() ->
            new LabResult(
                legacyClient.find(id),
                Thread.currentThread().getName()
            )
        );
    }

    @GetMapping("/lab/blocking-isolated/{id}")
    Mono<LabResult> blockingIsolated(@PathVariable String id) {
        return Mono.fromCallable(() ->
                new LabResult(
                    legacyClient.find(id),
                    Thread.currentThread().getName()
                )
            )
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/lab/nonblocking/{id}")
    Mono<LabResult> nonBlocking(@PathVariable String id) {
        return Mono.delay(Duration.ofMillis(100))
            .map(ignored ->
                new LabResult(
                    "item-" + id,
                    Thread.currentThread().getName()
                )
            );
    }
}
~~~

Ba endpoint có ý nghĩa khác nhau:

| Endpoint | Cách thực thi | Thread trong lúc chờ |
|---|---|---|
| `/lab/blocking-direct/{id}` | `fromCallable` không có scheduler riêng | Thread subscribe pipeline, thường là event loop của WebFlux |
| `/lab/blocking-isolated/{id}` | `fromCallable` + `subscribeOn(boundedElastic())` | Một worker của bounded elastic bị chiếm |
| `/lab/nonblocking/{id}` | `Mono.delay` | Không giữ thread để chờ timer; callback chạy khi timer phát tín hiệu |

Điểm cần chú ý: `Mono.fromCallable` chỉ trì hoãn lời gọi đến lúc subscribe. Nó không tự biến lời gọi blocking thành non-blocking. Ở endpoint đầu, callable chạy trên thread subscribe. Ở endpoint thứ hai, `subscribeOn` chuyển việc thực thi nguồn sang bounded elastic.

`Mono.delay` không phải bản thay thế trực tiếp cho mọi API blocking. Nó mô phỏng một thao tác chờ bất đồng bộ để bạn so sánh cách sử dụng thread. Trong ứng dụng thật, hãy dùng WebClient, R2DBC hoặc API non-blocking của thư viện tương ứng nếu có.

Khởi động ứng dụng và gọi thử từng endpoint:

~~~bash
curl http://localhost:8080/lab/blocking-direct/42
curl http://localhost:8080/lab/blocking-isolated/42
curl http://localhost:8080/lab/nonblocking/42
~~~

Quan sát trường `workerThread` trong response. Endpoint đầu thường cho thấy thread Netty event loop; endpoint thứ hai thường là thread có tên boundedElastic; endpoint thứ ba thường là thread scheduler phát timer, ví dụ parallel. Tên cụ thể phụ thuộc runtime và cấu hình, vì vậy hãy ghi lại giá trị thực tế.

## 5. Dùng BlockHound phát hiện blocking call

BlockHound instrument một số API blocking phổ biến và báo lỗi khi chúng được gọi trên thread được đánh dấu non-blocking. Nó hữu ích để phát hiện lỗi sớm trong test, nhưng không phải công cụ chứng minh mọi đường code đều không blocking.

Thêm dependency BlockHound tương thích với phiên bản Reactor và JDK đang dùng vào test runtime. Cài đặt hook một lần trước khi test tạo scheduler hoặc khởi chạy pipeline. Hai test dưới đây nằm trong cùng một test class:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockHound;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDetectionTest {
    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }

    @Test
    void reactorTuChoiBlockTrenThreadNonBlocking() {
        Mono<String> work = Mono.just("value")
            .publishOn(Schedulers.parallel())
            .map(value -> Mono.just(value).block());

        StepVerifier.create(work)
            .expectError(IllegalStateException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void blockHoundPhatHienThreadSleepTrenSchedulerNonBlocking() {
        Mono<String> work = Mono.fromCallable(() -> {
                Thread.sleep(20);
                return "done";
            })
            .subscribeOn(Schedulers.parallel());

        StepVerifier.create(work)
            .expectError(BlockingOperationError.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void blockingCallDuocCachLyTrenBoundedElastic() {
        Mono<String> work = Mono.fromCallable(() -> {
                Thread.sleep(20);
                return "done";
            })
            .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(work)
            .expectNext("done")
            .verify(Duration.ofSeconds(2));
    }
}
~~~

Test đầu xác nhận Reactor tự từ chối `block()` trên thread non-blocking bằng `IllegalStateException`. Test thứ hai mong đợi `BlockingOperationError` vì BlockHound phát hiện `Thread.sleep` trên scheduler non-blocking. Test thứ ba là đối chứng: cùng một thao tác blocking có thể chạy trên scheduler được thiết kế để chấp nhận blocking. Điều đó không làm thao tác trở thành non-blocking: worker vẫn bị chiếm trong lúc `sleep`. Bounded elastic chỉ cô lập việc chờ khỏi event loop và giới hạn số worker/queue theo cấu hình.

BlockHound có tích hợp và giới hạn theo runtime. Một số thư viện native hoặc API riêng có thể cần integration bổ sung; trên JVM không cho dynamic attach, cần cấu hình agent theo phiên bản BlockHound đang dùng. Không phát hiện lỗi cũng không chứng minh ứng dụng hoàn toàn không có blocking call. Hãy kết hợp nó với code review, metrics và load test.

## 6. Tạo workload cố định bằng k6

Dùng cùng một kịch bản cho cả ba endpoint. Ví dụ dưới đây tạo arrival rate 80 request/giây trong 30 giây. k6 tự điều chỉnh số virtual user trong giới hạn đã cấu hình để duy trì tốc độ đến.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_arrival: {
      executor: 'constant-arrival-rate',
      rate: 80,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 50,
      maxVUs: 150,
    },
  },
};

export default function () {
  const response = http.get(__ENV.TARGET_URL);

  check(response, {
    'status is 200': (result) => result.status === 200,
  });
}
~~~

Lưu file với tên `load-test.js`. Chạy lần lượt từng endpoint, không chạy ba bài đo cùng lúc trên cùng một ứng dụng:

~~~bash
k6 run -e TARGET_URL=http://localhost:8080/lab/blocking-direct/42 load-test.js
k6 run -e TARGET_URL=http://localhost:8080/lab/blocking-isolated/42 load-test.js
k6 run -e TARGET_URL=http://localhost:8080/lab/nonblocking/42 load-test.js
~~~

Các tham số phải giống nhau giữa ba lần chạy. Nếu chưa thấy khác biệt rõ, tăng arrival rate theo từng nấc và chạy lại cả ba endpoint ở mỗi nấc; không chỉ tăng tải cho một biến thể. Nếu máy không duy trì được arrival rate, giảm `rate` hoặc tăng giới hạn VU theo năng lực load generator; ghi lại mọi thay đổi. Để so sánh chắc chắn hơn, chạy warmup trước, lặp lại mỗi biến thể vài lần và đổi thứ tự chạy giữa các lượt để giảm ảnh hưởng do cache hoặc tải nền.

Các metric k6 cần ghi:

- `http_reqs`: tổng số request hoàn tất và tốc độ request.
- `http_req_duration`: latency end-to-end; đọc p50, p95 và p99.
- `http_req_failed`: tỷ lệ request lỗi.
- `dropped_iterations`: số iteration không được khởi chạy đúng arrival rate vì thiếu VU khả dụng.
- `vus` và `vus_max`: số VU đang dùng và giới hạn VU.

`dropped_iterations` không đồng nghĩa với lỗi HTTP. Nó cho biết load generator không tạo được toàn bộ iteration theo lịch đã đặt. Nếu metric này tăng, kết quả không còn phản ánh đầy đủ arrival rate yêu cầu; cần tăng capacity của generator hoặc giảm tốc độ thử.

## 7. Giữ phép đo công bằng

Một lần chạy chỉ có giá trị so sánh khi môi trường và workload đủ tương đồng. Trước mỗi lượt:

1. Khởi động ứng dụng và chờ ổn định.
2. Gửi một lượng request warmup để JVM và JIT không bị so sánh ở trạng thái khởi động khác nhau.
3. Kiểm tra load generator không bị CPU hoặc network giới hạn.
4. Chạy đúng một endpoint tại một thời điểm.
5. Giữ nguyên `rate`, `duration`, payload, số instance và giới hạn CPU/memory.
6. Ghi lại phiên bản ứng dụng, JDK, cấu hình scheduler và connection pool.
7. Lặp lại các lượt đo và lưu kết quả thô.

Nếu chạy k6 trên cùng máy với ứng dụng, hai tiến trình cạnh tranh CPU và network. Với kết quả có ý nghĩa hơn, chạy load generator trên máy hoặc container khác, hoặc ghi rõ giới hạn của phép đo local.

Không thay đổi đồng thời concurrency, pool size, số worker và arrival rate. Nếu nhiều biến thay đổi cùng lúc, bạn sẽ không biết yếu tố nào tạo ra cải thiện.

## 8. Bảng ghi kết quả

Điền số liệu thật từ output k6 và metrics ứng dụng:

| Chỉ số | Blocking trực tiếp | Blocking trên boundedElastic | Reactive non-blocking |
|---|---:|---:|---:|
| Throughput thực tế (req/s) | | | |
| p50 (ms) | | | |
| p95 (ms) | | | |
| p99 (ms) | | | |
| Error rate (%) | | | |
| Dropped iterations | | | |
| Thread thực hiện công việc | | | |
| CPU trung bình / đỉnh | | | |
| Active / pending worker hoặc connection | | | |

Ghi thêm các thông tin môi trường bên dưới bảng: số CPU được cấp, memory limit, JDK, số instance, phiên bản Reactor, cấu hình bounded elastic và cấu hình k6. Nếu có metrics Micrometer, lưu cả số liệu trước, trong và sau khi tải kết thúc.

Không điền các giá trị “mong đợi” vào cột kết quả. Có thể ghi giả thuyết riêng, nhưng phải phân biệt rõ giả thuyết với số đo thực tế.

## 9. Phân tích kết quả bằng mô hình thực thi

**Blocking trực tiếp:** mỗi request giữ thread subscribe trong khoảng thời gian legacy call chạy. Nếu đó là event loop, event loop không thể xử lý callback hoặc I/O khác trong thời gian bị giữ. Khi nhiều request đến, latency và queue có thể tăng; một số thread event loop bị chiếm lâu dù CPU không nhất thiết cao.

**Blocking trên bounded elastic:** event loop được trả về, còn lời gọi legacy chạy trên worker dành cho blocking. Hệ thống thường chịu được nhiều request hơn so với chặn trực tiếp event loop, nhưng mỗi lời gọi vẫn chiếm worker. Khi số tác vụ vượt giới hạn worker hoặc queue, request tiếp tục chờ và latency tăng.

**Reactive non-blocking:** trong lúc timer hoặc I/O chờ, không có thread bị giữ chỉ để chờ kết quả. Khi tín hiệu đến, scheduler tiếp tục callback. Mô hình này thường dùng tài nguyên thread hiệu quả hơn cho I/O-bound workload, nhưng vẫn bị giới hạn bởi CPU, socket, database, connection pool, memory và capacity của dịch vụ phụ thuộc.

Với cùng thời gian xử lý trung bình 100 ms, định luật Little cho một ước lượng số request đang hoạt động ở trạng thái ổn định:

`L = λ × W`

Trong đó `L` là số request trung bình đang in-flight, `λ` là arrival rate mỗi giây và `W` là latency trung bình tính bằng giây. Ví dụ, 80 request/giây với thời gian 0,1 giây tương ứng khoảng 8 request in-flight trung bình. Đây là ước lượng cho hệ thống ổn định, không phải giới hạn concurrency hoặc cam kết throughput.

Đọc số liệu theo cặp:

- p95/p99 tăng cùng `dropped_iterations`: load generator hoặc hệ thống không theo kịp arrival rate; xác định bên nào là nút thắt.
- CPU thấp nhưng latency cao: kiểm tra thread bị block, queue, connection pool và dependency.
- Bounded elastic có pending task tăng: worker pool hoặc dịch vụ legacy đã đạt capacity.
- Reactive delay có latency gần thời gian timer nhưng throughput ổn định hơn: phù hợp với giả thuyết không giữ thread khi chờ.
- Error rate tăng ở một biến thể: phân loại lỗi HTTP, timeout, rejection và lỗi ứng dụng trước khi kết luận.
- CPU tăng mạnh ở load generator: kết quả không đại diện cho capacity của server.

## 10. Quan sát thêm bằng metrics và thread dump

Trong lúc k6 chạy, quan sát ứng dụng ở cùng một cửa sổ thời gian:

- CPU process và CPU container.
- Heap, allocation rate, GC pause và direct memory nếu dùng Netty.
- Số thread, trạng thái thread và stack trace.
- Scheduler worker/pending task nếu đã instrument.
- Connection pool active, idle, pending acquire và timeout.
- Request rate, response time, error rate và số request in-flight.

Có thể lấy thread dump khi tải đang cao để xem thread nào đang thực hiện `Thread.sleep` hoặc đang chờ trong thư viện legacy. Với WebFlux/Reactor Netty, chú ý các thread event loop có tên dạng `reactor-http-nio-*`; tên cụ thể phụ thuộc cấu hình.

Nếu cần profiling sâu hơn, dùng Java Flight Recorder để tìm thread bị block, CPU hotspot, allocation và lock contention. BlockHound phù hợp phát hiện một số blocking call trong test; JFR và thread dump giúp quan sát hành vi khi ứng dụng chạy dưới tải.

Không thêm request ID hoặc user ID làm tag metric. Dùng log hoặc trace cho giá trị định danh riêng lẻ; metric nên dùng tag hữu hạn như endpoint variant, outcome và dependency.

## 11. Thử thay đổi concurrency và quan sát giới hạn

Sau lượt baseline, chỉ thay đổi một tham số. Với endpoint blocking isolated, có thể so sánh cấu hình bounded elastic mặc định với một scheduler có giới hạn rõ ràng:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

Scheduler legacyScheduler =
    Schedulers.newBoundedElastic(
        16,
        100,
        "legacy-catalog"
    );

Mono<LabResult> lookup(String id) {
    return Mono.fromCallable(() ->
            new LabResult(
                legacyClient.find(id),
                Thread.currentThread().getName()
            )
        )
        .subscribeOn(legacyScheduler);
}
~~~

Scheduler có giới hạn 16 worker và queue task theo tham số cấu hình. Hãy quản lý vòng đời scheduler ở bean hoặc thành phần sở hữu và gọi `dispose()` khi ứng dụng dừng. Không tạo scheduler mới cho mỗi request.

Chạy lại cùng k6 workload, sau đó trả lời:

1. Throughput có tăng hay giảm?
2. p95 và p99 thay đổi thế nào?
3. Pending task hoặc queue có tăng không?
4. Error rate có tăng do quá capacity không?
5. Khi dừng tải, queue có drain và thread có trở về trạng thái bình thường không?

Tăng số worker có thể giúp throughput nếu scheduler là nút thắt và hệ thống phụ thuộc còn capacity. Nhưng nếu database hoặc service legacy chỉ xử lý được một số request nhất định, tăng worker chỉ làm nhiều lời gọi chờ đồng thời và có thể làm dependency quá tải.

## 12. Xác định tiêu chí kết luận

Một kết luận tốt phải gắn với mục tiêu và số liệu. Ví dụ, nếu SLO của bài lab là p95 dưới 500 ms, error rate dưới 1% và không có dropped iteration, dùng cùng các ngưỡng này để đánh giá cả ba biến thể. Điều chỉnh ngưỡng theo môi trường thực tế trước khi chạy; không thay ngưỡng sau khi thấy kết quả chỉ để một biến thể đạt.

Hãy phân biệt:

- **Cải thiện hiệu năng:** throughput hoặc latency tốt hơn mà error rate và tài nguyên vẫn trong giới hạn.
- **Chuyển điểm nghẽn:** event loop được giải phóng nhưng bounded elastic queue hoặc connection pool trở thành nút thắt.
- **Quá tải có kiểm soát:** hệ thống từ chối hoặc timeout một phần request, queue không tăng vô hạn và hệ thống phục hồi sau khi giảm tải.
- **Quá tải mất kiểm soát:** latency và queue tăng liên tục, memory/threads bị giữ và hệ thống khó phục hồi.

Không chọn biến thể chỉ vì throughput cao nhất. Nếu p99 vượt SLO, lỗi tăng hoặc tài nguyên vượt quota, biến thể đó không đạt yêu cầu vận hành.

## 13. Câu hỏi phân tích và phần nộp

Trả lời bằng số liệu từ lần chạy của bạn:

1. Ba endpoint trả về thread name nào? Thread đó nói lên điều gì về vị trí thực thi?
2. Blocking trực tiếp ảnh hưởng event loop ra sao? Dữ liệu nào chứng minh điều đó?
3. Bounded elastic cải thiện điều gì và giới hạn nào vẫn còn?
4. BlockHound phát hiện lời gọi nào, trên scheduler nào? Test đối chứng cho bounded elastic có kết quả gì?
5. Biến thể nào có p95 và p99 thấp nhất trong workload đã chạy? Có dropped iterations không?
6. CPU thấp nhưng latency cao có thể chỉ ra những nguyên nhân nào?
7. Nếu tăng arrival rate gấp đôi, bạn dự đoán nút thắt tiếp theo nằm ở đâu và sẽ xác minh bằng metric nào?
8. Bạn sẽ chọn mô hình nào cho một SDK legacy blocking và mô hình nào cho một HTTP client reactive? Nêu lý do và giới hạn tài nguyên.

**Checklist hoàn thành:**

- [ ] Ba endpoint cùng mô phỏng thời gian xử lý danh nghĩa và trả về thread name.
- [ ] BlockHound phát hiện blocking call trên scheduler non-blocking.
- [ ] Test đối chứng cho blocking call trên bounded elastic chạy thành công.
- [ ] Cùng một k6 script đã chạy riêng cho cả ba endpoint.
- [ ] Đã ghi throughput, p50, p95, p99, error rate và dropped iterations.
- [ ] Đã ghi cấu hình máy, JVM và scheduler.
- [ ] Đã phân tích số liệu, không thay số đo bằng giá trị giả định.
- [ ] Đã nêu giới hạn và cách bảo vệ hệ thống khi tải vượt capacity.

Bài thực hành hoàn tất khi bạn có thể giải thích bằng số liệu vì sao chặn event loop làm giảm khả năng phục vụ, vì sao bounded elastic chỉ cô lập chứ không xóa chi phí blocking, và vì sao I/O reactive không chặn sử dụng thread hiệu quả hơn khi phải chờ. Kết luận cần dựa trên cùng workload, các percentile, error rate và giới hạn tài nguyên quan sát được.

