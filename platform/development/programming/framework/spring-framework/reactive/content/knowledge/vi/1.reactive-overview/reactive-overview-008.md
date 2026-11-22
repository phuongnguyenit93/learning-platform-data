# Phân biệt khả năng chịu tải với tốc độ một yêu cầu trong Spring WebFlux

Khi đánh giá một dịch vụ **Spring Reactive (Spring WebFlux)**, cần phân biệt hai câu hỏi: **“Một yêu cầu mất bao lâu để có kết quả?”** và **“Hệ thống có thể phục vụ bao nhiêu yêu cầu cùng lúc, trong một khoảng thời gian, mà vẫn đáp ứng chất lượng mong muốn?”**. Hai câu hỏi liên quan nhau nhưng đo những thuộc tính khác nhau. Lập trình reactive chủ yếu hữu ích cho việc sử dụng tài nguyên hiệu quả khi có nhiều thao tác I/O chờ đợi; bản thân nó không bảo đảm mỗi yêu cầu chạy nhanh hơn.

## 1. Những đại lượng cần hiểu

| Đại lượng | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| **Độ trễ (latency/response time)** | Thời gian từ khi bắt đầu gửi yêu cầu đến khi nhận được phản hồi theo ranh giới đo đã chọn. Có thể bao gồm mạng, thời gian chờ hàng đợi, xử lý ứng dụng, truy vấn DB và gọi dịch vụ khác. | ms/yêu cầu; p50, p95, p99, tối đa; đo từ phía client hoặc server và ghi rõ phạm vi. |
| **Thông lượng (throughput)** | Số yêu cầu **đã hoàn thành** trong một đơn vị thời gian, thường là requests/second (RPS). Nên phân biệt số yêu cầu thành công (*goodput*) với toàn bộ yêu cầu kể cả lỗi. | RPS hoặc giao dịch/giây trong một cửa sổ thời gian. |
| **Độ đồng thời (concurrency)** | Số yêu cầu đang được xử lý hoặc còn chờ kết quả ở cùng thời điểm (*in-flight requests*). | Số kết nối, số request in-flight, tác vụ chờ I/O, hàng đợi. |
| **Khả năng chịu tải (capacity)** | Mức tải cao nhất hệ thống **duy trì được** với ngưỡng độ trễ và tỷ lệ lỗi chấp nhận được, ở một loại workload và cấu hình xác định. | RPS bền vững kèm SLO, ví dụ p95 < 400 ms và lỗi < 1%. |
| **Mức sử dụng tài nguyên** | CPU, bộ nhớ/GC, thread, kết nối DB, event loop, giới hạn downstream... | Metrics hệ thống và ứng dụng khi tăng tải. |

**Tốc độ một yêu cầu** thường được diễn đạt bằng latency; **khả năng chịu tải** cần xem đồng thời throughput, concurrency, latency và lỗi. Một con số RPS cao trong vài giây chưa đủ chứng minh hệ thống chịu tải tốt nếu hàng đợi tiếp tục phình ra hoặc p99 tăng mạnh.

## 2. Ví dụ: phục vụ nhiều yêu cầu không có nghĩa mỗi yêu cầu nhanh hơn

Giả sử mỗi request phải đợi một dịch vụ I/O trả lời sau khoảng **200 ms** (chỉ là giả định minh họa, bỏ qua chi phí xử lý khác):

- Nếu chỉ cho một request hoạt động tại một thời điểm, mức tối đa lý tưởng là khoảng **5 request/giây** (1 / 0,2).
- Nếu **100 request có thể chờ I/O đồng thời** mà không tranh chấp tài nguyên, sau khoảng 200 ms cả nhóm có thể hoàn tất: thông lượng lý tưởng khoảng **500 request/giây** (100 / 0,2).
- Trong cả hai trường hợp, một request riêng lẻ vẫn phải đợi khoảng **200 ms**. Con số 500 RPS không có nghĩa thời gian phản hồi đã giảm xuống 2 ms.

Các con số này là **mô hình lý tưởng**, không phải kết quả benchmark của WebFlux. Thực tế còn giới hạn bởi CPU, mạng, số kết nối, connection pool, tốc độ database, giới hạn dịch vụ bên ngoài, cơ chế điều phối và phân bố độ trễ.

Có thể dùng **định luật Little** cho hệ thống ở trạng thái ổn định:

`L = λ × W`

Trong đó `L` là số yêu cầu trung bình đang ở trong hệ thống, `λ` là thông lượng hoàn thành trung bình (request/giây) và `W` là thời gian trung bình một yêu cầu ở trong hệ thống (giây). Ví dụ `λ = 200 RPS`, `W = 0,25 s` thì `L ≈ 50` request in-flight. Công thức mô tả mối liên hệ khi hệ thống ổn định; nó **không tự xác định công suất tối đa**. Khi tải đến vượt khả năng phục vụ, hàng đợi tăng, độ trễ kéo dài và có thể không còn trạng thái ổn định để áp dụng phép tính đơn giản trên.

## 3. Spring WebFlux giúp chịu tải ở đâu?

Ở mô hình bất đồng bộ, không chặn (*non-blocking*), request có thể khởi tạo thao tác I/O rồi tạm nhường thread trong lúc chờ. Khi có dữ liệu, luồng xử lý tiếp tục thông qua tín hiệu của `Mono` hoặc `Flux`. Với server reactive như Reactor Netty, các event-loop thread có thể điều phối nhiều kết nối, thay vì phải dành riêng một thread đang ngủ cho mỗi request chờ I/O.

Điều này thường có lợi cho **nhiều request đồng thời có tỷ lệ thời gian chờ I/O cao**: chat, streaming, gateway, gọi API khác, hoặc truy cập nguồn dữ liệu có driver non-blocking. Hệ thống có thể giảm số thread cần dùng và một số chi phí context switch, nhờ đó giữ được throughput tốt hơn dưới một mức tài nguyên nhất định.

Tuy nhiên:

1. **WebFlux không làm database hoặc API bên ngoài phản hồi nhanh hơn.** Nếu một lệnh gọi mất 200 ms thì request vẫn chịu phần độ trễ đó; muốn giảm latency phải tối ưu nguồn gây chậm, số lần gọi, cache, thuật toán, payload hoặc đường mạng.
2. **CPU-bound không tự nhanh lên vì reactive.** Mã tính toán nặng chiếm CPU vẫn cần thời gian CPU; nếu chạy lâu ngay trên event loop còn có thể làm chậm các request khác. Cần giới hạn/điều phối công việc CPU phù hợp hoặc đổi kiến trúc xử lý khi cần.
3. **Gọi blocking bên trong pipeline làm mất lợi ích non-blocking.** Ví dụ `Thread.sleep`, JDBC truyền thống, `block()` trên luồng xử lý request, hoặc thao tác file/API đồng bộ có thể giữ thread chờ. Nếu bắt buộc tích hợp thư viện blocking, có thể cách ly tác vụ trên scheduler thích hợp như `Schedulers.boundedElastic()`, nhưng thread pool đó có giới hạn và vẫn phải chịu chi phí chờ.
4. **Backpressure có phạm vi cụ thể.** Trong Reactive Streams, subscriber yêu cầu lượng dữ liệu nó có thể xử lý từ publisher, giúp điều tiết một dòng `Flux`. Điều này **không tự động giới hạn mọi HTTP request đi vào**, không mở rộng connection pool, và không cứu được backend đang quá tải. Ở biên hệ thống vẫn có thể cần timeout, giới hạn kết nối, hàng đợi hữu hạn, rate limiting và load shedding.
5. **Spring MVC cũng có các lựa chọn xử lý bất đồng bộ hoặc virtual threads.** Không thể kết luận WebFlux luôn có throughput cao hơn hoặc latency thấp hơn; phải so trên cùng workload, thư viện I/O, tài nguyên và phiên bản triển khai.

### Ví dụ Java với Spring WebFlux

Đây là **đoạn controller dùng trong dự án Spring Boot có `spring-boot-starter-webflux` và Java 17+**; nó không phải chương trình Java thuần chạy độc lập bằng `javac`. Đặt vào file `DelayController.java` thuộc package được Spring Boot quét:

```java
package com.example.demo;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DelayController {
    @GetMapping("/demo/wait")
    public Mono<String> waitWithoutBlocking() {
        return Mono.delay(Duration.ofMillis(200))
                .map(tick -> "done");
    }
}
```

`Mono.delay` mô phỏng một sự kiện bất đồng bộ sau khoảng 200 ms: phương thức tạo `Mono` rồi trả về, không dùng `Thread.sleep(200)` để chiếm thread HTTP trong thời gian chờ. Khi chạy ứng dụng, gọi `GET /demo/wait` sẽ nhận body `done` sau thời gian ít nhất xấp xỉ thời gian delay cộng overhead. Nhiều request đồng thời có thể cùng chờ bộ định thời mà không cần mỗi request giữ riêng một thread đang ngủ.

**Giới hạn ví dụ:** bộ định thời không phải một database hoặc HTTP client thật; nó chỉ minh họa nguyên tắc chờ bất đồng bộ. Thời gian đáp ứng và throughput đo được sẽ phụ thuộc môi trường. Với I/O thực, toàn bộ chuỗi thao tác (chẳng hạn `WebClient` và driver dữ liệu reactive) phải hỗ trợ non-blocking để thu được lợi ích tương ứng.

## 4. Khi tải tăng, độ trễ thường thay đổi thế nào?

Trong vùng tải nhẹ, server có thể có đủ tài nguyên: tăng số request đồng thời làm throughput tăng, còn latency mỗi request có thể gần như giữ nguyên. Khi chạm một nút thắt (CPU, event loop, pool kết nối, database hoặc downstream), request phải chờ hàng đợi; lúc đó **latency p95/p99 tăng**, thông lượng tăng chậm lại hoặc đạt trần, timeout và lỗi có thể xuất hiện. Nếu tiếp tục tăng lượng request đến, hệ thống có thể suy giảm nghiêm trọng dù vẫn có thread rảnh.

Vì vậy, một hệ thống xử lý 1.000 RPS ở p95 = 3 giây chưa chắc đáp ứng yêu cầu sản phẩm tốt hơn hệ thống xử lý 700 RPS ở p95 = 200 ms. Phải xét cùng SLO, tỷ lệ thành công, loại request và ngân sách tài nguyên. Đơn vị `RPS` đơn lẻ không nói lên trải nghiệm người dùng.

## 5. Đo đúng hai mục tiêu

**Để đo tốc độ một yêu cầu:** chạy thử ở tải thấp và đo latency đầu cuối; quan sát p50, p95, p99, tách thời gian xử lý ứng dụng, thời gian queue, gọi downstream, DB, mạng nếu có thể. Tìm thao tác chiếm nhiều thời gian nhất. Đo một request đơn lẻ giúp khảo sát latency cơ sở nhưng không đại diện cho giờ cao điểm.

**Để đo khả năng chịu tải:** tăng tải theo các mức đồng thời hoặc arrival rate có kiểm soát, giữ nguyên loại request và dữ liệu thử; mỗi mức cần đủ thời gian ổn định. Ghi *completed/successful RPS*, số lỗi và timeout, p95/p99, request in-flight, độ dài hàng đợi, CPU/GC, thread/event-loop utilization, connection pool và metrics downstream. Xác định mức RPS **duy trì được trong khi còn thỏa SLO**; đừng lấy giá trị đỉnh ngắn hạn làm capacity.

Khi so sánh Spring MVC với WebFlux, cần giữ cùng phần nghiệp vụ, backend, payload, điều kiện mạng, cấu hình pool, cấu hình máy, thời gian warm-up và chính sách timeout. Tránh benchmark chỉ bằng endpoint trả chuỗi rỗng rồi suy rộng cho ứng dụng gọi DB/API thực. Cũng cần đo riêng workload **I/O-bound** và **CPU-bound** vì lợi ích reactive có thể khác hẳn.

| Quan sát khi thử tải | Cách diễn giải ban đầu | Việc nên kiểm tra |
| --- | --- | --- |
| Latency gần như không đổi, RPS tăng khi nâng concurrency | Hệ thống còn dư năng lực xử lý đồng thời | Tài nguyên và SLO ở mức tải kế tiếp |
| RPS đạt trần, p95/p99 tăng nhanh | Có tài nguyên hoặc phụ thuộc đang bão hòa; request bắt đầu xếp hàng | CPU, event loop, pool DB, mạng, downstream và timeout |
| RPS khá cao nhưng nhiều HTTP 5xx/timeout | Thành công thực tế thấp hơn RPS tổng | Goodput, exception, giới hạn downstream và cơ chế từ chối tải |
| Chuyển sang reactive giảm thread, RPS tăng, latency cơ sở không giảm | Khả năng phục vụ request đồng thời được cải thiện; công việc của một request không ngắn đi | Percentile latency và chi phí mỗi request |
| Một endpoint CPU-bound bị chậm khi tăng concurrency | CPU hoặc chia sẻ thread là nút thắt; non-blocking I/O ít giúp | Profiling CPU, tác vụ dài trên event loop |

## 6. Cải thiện đúng vấn đề

- **Muốn một request nhanh hơn:** giảm số round-trip, tối ưu truy vấn/index, dùng cache đúng cách, giảm công việc CPU, tải dữ liệu cần thiết, tránh gọi tuần tự khi các thao tác độc lập có thể phối hợp an toàn, xử lý timeout và cải thiện độ trễ downstream.
- **Muốn chịu được nhiều request đồng thời hơn:** loại blocking I/O khỏi đường reactive, bảo đảm client/driver phù hợp, quản lý pool và giới hạn concurrency, theo dõi event loop, tăng công suất backend thực sự, dùng backpressure đúng phạm vi, giới hạn tải đầu vào và scale theo điểm nghẽn.
- **Muốn cả hai:** đặt mục tiêu riêng cho p95/p99, successful RPS và chi phí tài nguyên; kiểm chứng bằng load test đại diện thay vì mặc định `Mono`/`Flux` đồng nghĩa với “nhanh”.

**Ghi nhớ:** *latency* trả lời “một yêu cầu phải chờ bao lâu?”; *capacity/throughput dưới SLO* trả lời “có bao nhiêu yêu cầu được phục vụ ổn định trong cùng thời gian?”. Spring WebFlux có thể cải thiện vế thứ hai rõ rệt ở workload nhiều I/O chờ, trong khi vế thứ nhất chỉ cải thiện nếu thực sự rút ngắn đường xử lý hoặc giảm thời gian xếp hàng.