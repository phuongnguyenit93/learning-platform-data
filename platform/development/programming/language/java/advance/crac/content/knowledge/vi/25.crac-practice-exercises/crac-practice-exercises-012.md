# Xây dựng báo cáo hiệu năng và tiêu chí chấp nhận cho ứng dụng mẫu

Một ứng dụng dùng CRaC chỉ có giá trị vận hành khi checkpoint và restore giúp cải thiện thời gian đưa dịch vụ vào trạng thái phục vụ mà vẫn giữ được hành vi và hiệu năng cần thiết. Để chứng minh điều đó, cần đo trên cùng một ứng dụng, cùng workload và môi trường có kiểm soát; sau đó trình bày kết quả trong một báo cáo có thể lặp lại và xác định rõ điều kiện để chấp nhận triển khai.

Bài thực hành này hướng dẫn xây dựng báo cáo hiệu năng cho một ứng dụng Java mẫu có endpoint HTTP. Ta so sánh đường khởi động JVM thông thường với đường restore từ checkpoint CRaC, đồng thời đo chi phí tạo checkpoint, kích thước ảnh, hiệu năng sau khi sẵn sàng và khả năng phục hồi khi dependency thay đổi.

Một báo cáo tốt phải trả lời được các câu hỏi:

- Restore đưa ứng dụng đến trạng thái sẵn sàng nhanh hơn cold start bao nhiêu?
- Thời gian từ lúc process được tạo đến lúc readiness mở có được đo nhất quán không?
- Request đầu tiên sau restore có chậm bất thường không?
- Throughput, latency và error rate khi chạy ổn định có thay đổi không?
- Checkpoint/restore tiêu thụ bao nhiêu CPU, memory, disk và thời gian?
- Kết quả có lặp lại trên nhiều lần chạy và nhiều instance không?
- Các điều kiện chức năng, tương thích và vận hành nào phải đạt trước khi chấp nhận?

Các con số trong ví dụ kết quả của bài này là dữ liệu minh họa để thực hành cách tính và trình bày. Chúng không phải benchmark đã chạy trên một JDK, CRIU hoặc phần cứng cụ thể. Khi triển khai, thay bằng dữ liệu đo được từ môi trường của bạn.

## 1. Xác định mục tiêu và phạm vi đo

Trước khi chạy benchmark, viết rõ mục tiêu. Nếu mục tiêu là giảm thời gian scale-out, phép đo chính là thời gian từ khi tạo instance đến khi instance nhận traffic. Nếu mục tiêu là giảm thời gian khởi động sau deploy, cần đo từ khi process bắt đầu đến khi readiness và dependency đều sẵn sàng. Nếu mục tiêu là giảm thời gian phục hồi sau node failure, cần đo thêm thời gian phát hiện lỗi, cấp instance mới, tải ảnh, restore và mở traffic.

Không gộp tất cả thành một con số “startup time”. Mỗi giai đoạn có thể có nút thắt khác nhau.

### Phân biệt các mốc thời gian

| Mốc | Định nghĩa | Điều được phản ánh |
|---|---|---|
| Process start | Thời điểm OS tạo process JVM | Chi phí tạo process và nạp runtime |
| JVM ready | JVM hoàn tất phần khởi tạo runtime cần thiết | Chi phí khởi tạo JVM |
| Application ready | Ứng dụng hoàn tất khởi tạo bean, route và resource cục bộ | Chi phí khởi tạo ứng dụng |
| Dependency ready | Database, broker, secret provider và dependency bắt buộc đã kết nối | Chi phí phục hồi tích hợp |
| Readiness open | Instance được phép nhận traffic | Thời điểm bắt đầu phục vụ |
| First successful response | Request đầu tiên hoàn tất thành công | Chi phí cold path/first request |
| Steady state | Hệ thống đã qua giai đoạn warm-up và tải ổn định | Hiệu năng phục vụ lâu dài |

Với mục tiêu scale-out, dùng `process start → readiness open` làm mốc chính và báo riêng `readiness open → first successful response`. Với người dùng cuối, first response có thể quan trọng hơn thời điểm readiness nếu probe chỉ kiểm tra một endpoint rất nhẹ.

### Các nhóm chỉ số

Chia chỉ số thành bốn nhóm:

1. **Khởi động và phục hồi:** cold-start-to-ready, restore-to-ready, first-request latency và thời gian phục hồi dependency.
2. **Hiệu năng phục vụ:** throughput, latency percentiles, error rate và mức sử dụng tài nguyên.
3. **Chi phí checkpoint:** thời gian checkpoint, kích thước ảnh, CPU, memory, I/O và dung lượng lưu trữ.
4. **Độ tin cậy:** tỷ lệ checkpoint/restore thành công, tính đúng đắn nghiệp vụ, khả năng restore nhiều instance và hành vi khi dependency không sẵn sàng.

Không dùng một chỉ số riêng lẻ để quyết định. Restore-to-ready nhanh nhưng request lỗi hoặc throughput giảm mạnh thì ứng dụng chưa đạt.

## 2. Mô tả ứng dụng mẫu

Để kết quả có thể so sánh, dùng một ứng dụng Java có hành vi xác định và workload ổn định. Ví dụ ứng dụng cung cấp:

- `GET /health/live`: xác nhận process và event loop còn hoạt động.
- `GET /health/ready`: trả thành công chỉ khi các resource bắt buộc đã sẵn sàng.
- `GET /api/catalog/{id}`: trả dữ liệu catalog có kích thước cố định.
- `POST /api/compute`: thực hiện một phép tính CPU có thời lượng kiểm soát.
- `GET /metrics`: xuất metric runtime và ứng dụng.

Nếu ứng dụng mẫu dùng Spring Boot, Quarkus, Micronaut hoặc framework khác, ghi rõ version và cấu hình. Không thay framework giữa baseline và CRaC vì chi phí startup và runtime có thể khác đáng kể.

### Đặc điểm cần giữ cố định

| Thành phần | Cấu hình mẫu |
|---|---|
| Java runtime | Cùng một JDK distribution, version và build |
| Ứng dụng | Cùng artifact SHA-256 |
| Framework | Cùng version và profile |
| HTTP server | Cùng implementation và port configuration |
| Dependency | Cùng database/broker hoặc cùng test double |
| Dataset | Cùng dữ liệu, kích thước response và cache state |
| CPU/memory | Cùng host class và container limits |
| JVM flags | Giống nhau, ngoại trừ option cần cho CRaC |
| Logging | Cùng mức log và appender |
| Workload | Cùng request mix, concurrency và thời lượng |

Nếu checkpoint được tạo sau khi ứng dụng đã warm-up cache hoặc JIT, baseline phải được mô tả rõ. Có thể tạo checkpoint sau một giai đoạn warm-up có chủ đích, nhưng không so sánh nó với cold start chưa warm-up rồi kết luận toàn bộ chênh lệch là do CRaC. Hãy báo riêng lợi ích của trạng thái đã warm-up được giữ lại.

### Dependency trong bài thực hành

Có thể chọn một trong hai kiểu:

**Test double cục bộ:** phù hợp để đo riêng JVM/framework và request path. Dữ liệu được phục vụ từ memory hoặc một service giả lập ổn định. Kết quả không đại diện đầy đủ cho môi trường production có database/broker.

**Dependency thật trong môi trường test:** phù hợp để đo readiness và reconnect thực tế. Database, broker, secret manager và network phải được giữ cùng cấu hình giữa các lần chạy. Ghi rõ việc dependency có được restore cùng ứng dụng hay vẫn là dịch vụ độc lập.

Không trộn hai kiểu trong cùng một bảng kết quả nếu không phân biệt. Mỗi cấu hình dependency là một benchmark scenario riêng.

## 3. Xác định baseline và các đường chạy

Ít nhất cần hai đường chạy:

**Baseline cold start:** khởi chạy JVM mới bằng lệnh production-like, đợi readiness mở và đo first response.

**CRaC restore:** tạo checkpoint từ ứng dụng đã khởi tạo theo quy trình xác định, sau đó restore ảnh và đo từ thời điểm bắt đầu restore đến readiness và first response.

Để hiểu đầy đủ chi phí, thêm:

- Thời gian khởi động JVM mới và tạo checkpoint lần đầu.
- Thời gian đóng gói, truyền và giải nén ảnh nếu quy trình triển khai có các bước này.
- Thời gian restore trên cùng host và trên host đích tương thích.
- Thời gian warm-up sau restore nếu JIT/cache không ở trạng thái tương đương.

### Các khoảng thời gian phải báo riêng

| Chỉ số | Điểm bắt đầu | Điểm kết thúc |
|---|---|---|
| Cold start to ready | Process JVM mới bắt đầu | Readiness mở |
| Restore to ready | Lệnh restore bắt đầu | Readiness mở |
| First request latency | Gửi request đầu tiên sau readiness | Nhận response hoàn chỉnh |
| Checkpoint duration | Yêu cầu checkpoint bắt đầu | Runtime xác nhận checkpoint hoàn tất |
| Artifact preparation | Bắt đầu đóng gói/transfer/verify | Ảnh sẵn sàng cho restore |
| Restore total deployment time | Bắt đầu cấp instance/tải ảnh | Instance nhận traffic |
| Warm-up duration | Readiness mở hoặc bắt đầu warm-up | Chạm tiêu chí steady-state |

Nếu chỉ đo thời gian lệnh java trả về, có thể bỏ sót thời gian ứng dụng chưa sẵn sàng. Nếu đo từ lúc bắt đầu deploy nhưng không tách thời gian tải ảnh, khó biết lợi ích của CRaC có bị chi phí artifact transfer triệt tiêu hay không.

### Sơ đồ quy trình đo

~~~mermaid
flowchart TD
    A[Chuẩn bị cùng artifact và môi trường] --> B[Chạy cold-start baseline]
    B --> C[Đo readiness và first response]
    C --> D[Warm-up theo kịch bản]
    D --> E[Tạo checkpoint]
    E --> F[Đo checkpoint time và image size]
    F --> G[Restore từ image]
    G --> H[Đo restore-to-ready và first response]
    H --> I[Chạy steady-state workload]
    I --> J[Thu latency throughput errors CPU memory]
    J --> K[Lặp lại các lần đo]
    K --> L[Tổng hợp báo cáo và áp tiêu chí]
~~~

## 4. Thiết kế workload có thể lặp lại

Workload cần phản ánh kiểu request mà ứng dụng thực sự phục vụ. Một endpoint chỉ trả `200 OK` có thể đo HTTP server nhưng không phản ánh database, serialization, cache hoặc CPU work.

### Xác định request mix

Ví dụ workload:

| Request | Tỷ trọng | Mục đích |
|---|---:|---|
| `GET /api/catalog/{id}` | 70% | Đọc dữ liệu và serialization |
| `POST /api/compute` | 20% | Đo CPU path |
| `GET /health/ready` | 10% | Kiểm tra trạng thái phục vụ |

Đây chỉ là mix mẫu. Thay tỷ lệ bằng request mix của ứng dụng. Nếu endpoint có payload khác nhau, ghi kích thước request/response và dữ liệu đầu vào.

### Xác định concurrency và thời lượng

Một cấu hình benchmark có thể gồm:

- 1 client để đo latency đơn lẻ.
- 10, 50 và 100 concurrent clients để quan sát khả năng mở rộng.
- 5 phút warm-up.
- 10 phút steady-state measurement.
- Ít nhất 5 lần chạy độc lập cho mỗi scenario; với benchmark nhạy nhiễu, tăng số lần chạy.

Không lấy con số mẫu này làm chuẩn bắt buộc. Chọn concurrency và thời lượng dựa trên tải dự kiến, giới hạn môi trường và thời gian đủ để metric ổn định.

### Tách first request khỏi steady state

Request đầu tiên sau restore có thể chịu chi phí lazy initialization, class loading, JIT compilation, DNS lookup hoặc tạo connection. Ghi riêng:

- First request sau readiness.
- Các request trong 30–60 giây đầu.
- Steady-state sau warm-up.

Nếu chỉ lấy trung bình toàn bộ test dài, độ trễ lớn của vài request đầu có thể bị che khuất.

### Tránh tạo tải lên dependency ngoài ý muốn

Nếu mỗi request tạo một query nặng hoặc một message mới, benchmark có thể đo database/broker thay vì ứng dụng. Giữ dữ liệu, index, cache và trạng thái dependency ổn định. Theo dõi cả dependency để biết bottleneck nằm ở đâu.

## 5. Thu thập thời gian startup và readiness

Readiness phải phản ánh điều kiện thực sự cần thiết để phục vụ traffic. Endpoint readiness không nên trả `200` chỉ vì HTTP server đã mở port nếu database pool, secret provider hoặc consumer bắt buộc chưa sẵn sàng.

### Ghi timestamp từ ứng dụng

Ghi các mốc bằng structured log:

~~~text
event=process_started
event=application_context_ready
event=crac_after_restore_started
event=dependencies_ready
event=readiness_open
event=first_request_completed
~~~

Mỗi event nên có timestamp UTC, checkpoint ID, restore attempt ID, incarnation ID và application build. Không ghi secret hoặc dữ liệu request nhạy cảm.

Trong cùng process, dùng `System.nanoTime()` để đo elapsed duration. Dùng `Instant.now()` hoặc timestamp của log để đối chiếu giữa host. Không trừ timestamp wall-clock giữa hai máy nếu chưa xử lý clock skew.

Ví dụ:

~~~java
long startedAt = System.nanoTime();
initializeDependencies();
long elapsedNanos = System.nanoTime() - startedAt;

logger.info("event=dependencies_ready elapsed_ms={}",
        elapsedNanos / 1_000_000);
~~~

Đối với thời gian từ process start đến readiness, có thể ghi timestamp ở entrypoint/orchestrator và event readiness ở ứng dụng. Bảo đảm cả hai dùng clock đã đồng bộ; tốt hơn nữa là dùng một phép đo từ bên ngoài theo cùng một clock.

### Đo từ bên ngoài

Một script có thể poll readiness và ghi thời điểm bắt đầu/kết thúc:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

READY_URL="http://127.0.0.1:8080/health/ready"
START_NS=$(date +%s%N)

until curl --silent --fail "$READY_URL" >/dev/null; do
  sleep 0.05
done

END_NS=$(date +%s%N)
ELAPSED_MS=$(( (END_NS - START_NS) / 1000000 ))
printf 'readiness_elapsed_ms=%s\n' "$ELAPSED_MS"
~~~

Đây là ví dụ cho Linux với GNU date hỗ trợ %N. Trên hệ điều hành khác, dùng monotonic timer phù hợp. Script poll có độ phân giải hữu hạn; ghi lại chu kỳ poll và không diễn giải kết quả chính xác hơn độ phân giải đó.

Đặt điểm bắt đầu ngay trước lệnh cold start hoặc restore, không phải sau khi process đã xuất hiện. Nếu đo thời gian deployment end-to-end, bắt đầu từ thao tác tạo instance/tải image.

### Đo first response

Sau khi readiness mở, gửi một request đại diện và ghi thời gian:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'http_code=%{http_code} total_seconds=%{time_total}\n' \
  http://127.0.0.1:8080/api/catalog/42
~~~

Chạy cùng request, payload, client location và connection policy cho baseline và restore. Nếu connection reuse được bật ở một bên mà bên kia không bật, kết quả first request không còn tương đương.

## 6. Đo throughput, latency và error rate

Startup improvement chỉ là một phần của lợi ích. Cần xác nhận ứng dụng sau restore có phục vụ ổn định.

### Latency percentiles

Báo ít nhất:

- p50: latency của request điển hình.
- p90 hoặc p95: latency của phần lớn request.
- p99: latency ở đuôi phân phối.
- Maximum: chỉ dùng cùng số request và bối cảnh để hiểu outlier.

Không chỉ báo average. Một số request rất chậm có thể bị che bởi trung bình.

### Throughput

Throughput là số request hoàn tất trong một đơn vị thời gian, thường là requests/second. Ghi concurrency, thời lượng, request mix và số request hoàn tất. Khi client bão hòa CPU hoặc network, throughput đo được có thể phản ánh giới hạn của máy phát tải.

### Error rate

Phân loại lỗi:

- HTTP 5xx.
- HTTP 4xx ngoài dự kiến.
- Timeout hoặc connection reset.
- Request bị từ chối do readiness.
- Lỗi nghiệp vụ hoặc response sai dữ liệu.

Không tính mọi HTTP 4xx là lỗi hệ thống nếu một số mã là kết quả hợp lệ của workload. Định nghĩa error trước khi chạy.

### Ví dụ dùng hey

`hey` là một công cụ tạo tải HTTP. Ví dụ:

~~~bash
hey -z 10m -c 50 -m GET \
  http://127.0.0.1:8080/api/catalog/42
~~~

Lệnh này chạy 10 phút với 50 concurrent workers cho một endpoint GET. Ghi version của hey, host phát tải, CPU/network của load generator và output thô. Với request mix phức tạp, dùng k6, Gatling hoặc công cụ phù hợp với payload và authentication.

### Ví dụ k6

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '10m',
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<200', 'p(99)<500'],
  },
};

export default function () {
  const response = http.get('http://127.0.0.1:8080/api/catalog/42');
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
~~~

Các threshold trong ví dụ là placeholder để minh họa cú pháp. Hãy thay bằng SLO/tiêu chí của ứng dụng và ghi rõ đơn vị thời gian mà phiên bản công cụ sử dụng.

Không chạy cùng một load generator trên host đang chạy JVM nếu việc đó làm tranh CPU hoặc memory. Ưu tiên máy phát tải riêng hoặc ghi nhận rõ tài nguyên bị chia sẻ.

## 7. Đo tài nguyên và chi phí checkpoint

Ngoài latency, CRaC có thể thay đổi cách sử dụng tài nguyên. Checkpoint image chiếm storage; checkpoint/restore có thể tạo CPU và I/O burst; warm-up state được giữ lại có thể làm heap hoặc RSS lớn hơn.

### Chỉ số tài nguyên

| Chỉ số | Cách hiểu |
|---|---|
| CPU usage | CPU tiêu thụ khi startup, checkpoint, restore và steady-state |
| RSS | Bộ nhớ resident của process |
| Heap used/committed | Bộ nhớ heap đang dùng và heap JVM đã commit |
| Native memory | Thread stack, direct buffer, native library và runtime allocation |
| Peak memory | Mức cao nhất trong một giai đoạn |
| Disk read/write | I/O phục vụ đọc/ghi checkpoint image |
| Checkpoint image size | Dung lượng ảnh được lưu |
| Restore read volume | Dung lượng đọc để khôi phục ảnh |
| File descriptors/threads | Số lượng sau restore so với baseline |

RSS, heap used và heap committed là các đại lượng khác nhau. Không suy ra RSS chỉ từ heap usage. Dùng OS/container metrics cùng JVM metrics.

### Lệnh Linux tham khảo

~~~bash
/usr/bin/time -v java -jar app.jar
~~~

`time -v` báo wall time, CPU time, maximum resident set size và một số thông tin tiến trình. Để đo restore, áp dụng cho lệnh restore tương ứng theo JDK distribution.

Nếu process đang chạy:

~~~bash
ps -o pid,etime,%cpu,%mem,rss,vsz,nlwp,cmd -p <pid>
cat /proc/<pid>/status
~~~

Trong container, đọc thêm cgroup metrics để biết giới hạn và mức sử dụng thực tế. Với Kubernetes, ghi CPU/memory request và limit, node type và tình trạng throttling.

### Kích thước checkpoint

Ghi:

- Kích thước thư mục ảnh sau checkpoint.
- Kích thước archive nếu đóng gói.
- Kích thước sau nén.
- Thời gian đóng gói và giải nén.
- Thời gian truyền qua mạng.
- Số ảnh giữ lại và retention.

Nén có thể giảm storage/network nhưng làm tăng CPU và latency. Đo cả thời gian nén/giải nén nếu đó là một phần của quy trình triển khai.

### Checkpoint overhead

Đo thời gian từ yêu cầu checkpoint đến khi hoàn tất. Đồng thời ghi thời gian ứng dụng không nhận traffic, số request bị queue/reject và mức ảnh hưởng đến các dependency. Một checkpoint rất nhanh nhưng làm mất request hoặc gây transaction timeout không thể được coi là miễn phí.

Nếu checkpoint được tạo khi ứng dụng đã drain traffic, đo riêng drain duration và checkpoint engine duration để biết tổng thời gian gián đoạn.

## 8. Thiết kế ma trận thử nghiệm

Một ma trận rõ ràng giúp phát hiện trường hợp CRaC hoạt động ở một môi trường nhưng không đạt trên môi trường khác.

| Scenario | Cách chạy | Mục đích |
|---|---|---|
| S1 — Cold start | JVM mới, không dùng checkpoint | Baseline |
| S2 — Restore same host | Restore ảnh trên host tương thích đã tạo ảnh | Đo lợi ích cơ bản |
| S3 — Restore target host | Chuyển ảnh sang host đích được hỗ trợ | Đo chi phí phân phối và portability trong phạm vi hỗ trợ |
| S4 — First request | Đo request đầu tiên sau readiness | Phát hiện lazy initialization |
| S5 — Steady state | Workload cố định sau warm-up | So sánh hiệu năng phục vụ |
| S6 — Concurrent restore | Restore nhiều instance cùng lúc | Đo CPU, disk, network và coordination burst |
| S7 — Dependency unavailable | Secret manager/database/broker tạm thời lỗi | Kiểm tra readiness và retry |
| S8 — Repeated restore | Lặp restore nhiều lần từ cùng ảnh theo kịch bản | Phát hiện state cũ hoặc resource leak |
| S9 — Fresh checkpoint | Tạo ảnh mới sau thay đổi build/config | Xác minh quy trình tạo ảnh |

Không phải mọi tổ hợp đều có thể hỗ trợ. Ví dụ restore sang host khác phải tuân theo giới hạn tương thích của JDK, CRIU, kernel, architecture và tài nguyên ứng dụng. Ghi rõ scenario nào nằm trong phạm vi hỗ trợ.

### Số lần chạy và cách tổng hợp

Một quy trình thực tế:

1. Chạy ít nhất một lần pilot để phát hiện lỗi cấu hình.
2. Warm-up theo cùng chính sách.
3. Chạy tối thiểu 5 lần độc lập cho mỗi scenario quan trọng.
4. Nếu kết quả dao động lớn, tăng số lần chạy và điều tra nguồn nhiễu.
5. Báo median, p95 giữa các lần chạy hoặc phân phối mẫu phù hợp.
6. Giữ lại raw result để có thể tính lại.

Đối với startup time, mỗi lần chạy là một mẫu độc lập. Đối với request latency, hàng nghìn request trong một lần chạy không tương đương hàng nghìn lần khởi động độc lập. Không trộn hai loại mẫu trong cùng thống kê.

### Kiểm soát thứ tự thử nghiệm

Không luôn chạy cold start trước rồi CRaC sau nếu host bị nóng lên theo thời gian. Xen kẽ hoặc randomize thứ tự scenario để giảm bias do thermal state, cache filesystem, CPU frequency và background load.

Nếu benchmark trên một host dùng chung, ghi tải nền và tránh chạy update, backup hoặc tác vụ khác trong thời gian đo.

## 9. Tính toán và trình bày kết quả

Chọn một đơn vị nhất quán, ví dụ milliseconds cho startup/latency và requests/second cho throughput.

### Mức cải thiện thời gian

Với:

- \(T_c\): cold-start-to-ready.
- \(T_r\): restore-to-ready.

Tỷ lệ giảm thời gian:

\[
\text{Time reduction} =
\frac{T_c - T_r}{T_c} \times 100\%
\]

Speedup:

\[
\text{Speedup} = \frac{T_c}{T_r}
\]

Ví dụ minh họa: cold start 8.4 giây, restore 1.2 giây:

\[
\text{Time reduction} = \frac{8.4 - 1.2}{8.4} \times 100\%
= 85.7\%
\]

\[
\text{Speedup} = \frac{8.4}{1.2} = 7.0\times
\]

Nêu rõ hai thời gian đều đo đến cùng một mốc readiness. Nếu cold start đo đến first response còn restore đo đến readiness, phép so sánh không hợp lệ.

### Throughput regression

Với:

- \(Q_b\): throughput baseline.
- \(Q_r\): throughput sau restore.

Thay đổi throughput:

\[
\text{Throughput change} =
\frac{Q_r - Q_b}{Q_b} \times 100\%
\]

Giá trị âm là giảm throughput. Dùng cùng request mix, concurrency và thời lượng.

### Ví dụ bảng kết quả minh họa

<text color="secondary" size="sm">Dữ liệu giả lập để minh họa cách báo cáo, không phải kết quả đo thực tế.</text>

| Chỉ số | Cold start | CRaC restore |
|---|---:|---:|
| Process-to-ready median | 8,400 ms | 1,200 ms |
| Process-to-ready p95 | 9,100 ms | 1,450 ms |
| First request p95 | 145 ms | 160 ms |
| Steady-state throughput | 4,800 req/s | 4,760 req/s |
| Steady-state latency p95 | 42 ms | 43 ms |
| Error rate | 0.02% | 0.03% |
| RSS sau warm-up | 620 MiB | 650 MiB |
| Checkpoint duration | — | 780 ms |
| Checkpoint image | — | 185 MiB |

Trong ví dụ, restore-to-ready nhanh hơn đáng kể. Tuy nhiên, first request p95 tăng nhẹ và RSS sau warm-up cao hơn; throughput/steady-state latency gần tương đương. Một báo cáo thực tế cần xác định chênh lệch này có nằm trong giới hạn chấp nhận hay không.

### Đồ thị nên có

Tùy mục tiêu, nên trình bày:

- Bar chart cold-start-to-ready và restore-to-ready theo median/p95.
- Line chart latency theo thời gian để thấy first-request spike và warm-up.
- Throughput theo concurrency.
- RSS/heap/CPU theo từng giai đoạn.
- Checkpoint image size và transfer duration.
- Restore success rate qua các lần chạy.

Không chỉ đưa chart. Ghi rõ đơn vị, số lần chạy, số request, workload, version và môi trường ngay dưới mỗi biểu đồ.

## 10. Xác định tiêu chí chấp nhận

Acceptance criteria phải được viết trước khi xem kết quả cuối cùng. Nếu chỉ đặt ngưỡng sau khi thấy số liệu, nhóm dễ vô tình điều chỉnh tiêu chí để hợp thức hóa kết quả.

Chia điều kiện thành bốn cổng:

1. **Functional correctness:** ứng dụng và nghiệp vụ hoạt động đúng sau restore.
2. **Performance:** startup/restore đạt mục tiêu và steady-state không suy giảm quá mức cho phép.
3. **Reliability/operability:** restore lặp lại, dependency recovery, scaling và observability hoạt động.
4. **Security/compatibility:** ảnh và secret được bảo vệ; môi trường nằm trong ma trận hỗ trợ.

### Ví dụ acceptance criteria

Các ngưỡng dưới đây chỉ là ví dụ để minh họa cách viết. Nhóm dự án phải thay bằng SLO, tải thực tế và ngân sách tài nguyên của ứng dụng.

| Hạng mục | Tiêu chí ví dụ | Loại |
|---|---|---|
| Restore-to-ready | p95 ≤ 2 giây trong cùng host profile | Performance gate |
| Startup improvement | Median restore-to-ready giảm ít nhất 60% so với cold start | Performance gate |
| First request | p95 ≤ 200 ms và không có spike vượt ngưỡng SLO | Performance gate |
| Throughput | Không giảm quá 5% so với baseline | Performance gate |
| Steady-state latency | p95 không tăng quá 5% | Performance gate |
| Error rate | Không vượt SLO; không có lỗi nghiệp vụ mới | Reliability gate |
| Checkpoint success | 20/20 lần thành công trong test matrix đã chọn | Reliability gate |
| Restore success | 20/20 lần thành công trong môi trường hỗ trợ | Reliability gate |
| Functional validation | Tất cả smoke test và data-integrity test đạt | Hard gate |
| Dependency recovery | Không mở readiness trước khi dependency bắt buộc sẵn sàng | Hard gate |
| Multi-instance behavior | Không có duplicate leader/side effect trái policy | Hard gate |
| Resource budget | RSS, CPU và image size nằm trong ngân sách đã định | Resource gate |
| Security | Artifact access, encryption, secret handling đạt policy | Hard gate |
| Compatibility | JDK/CRIU/kernel/architecture nằm trong ma trận hỗ trợ | Hard gate |

### Hard gate và soft target

**Hard gate** là điều kiện không được phép vi phạm, ví dụ dữ liệu đúng, không có duplicate payment, không có hai leader cho cùng role, không lộ secret và không mở readiness khi dependency bắt buộc chưa sẵn sàng.

**Soft target** là mục tiêu hiệu năng có thể đánh đổi trong phạm vi đã duyệt, ví dụ image size, mức cải thiện startup hoặc mức tăng RSS. Nếu soft target không đạt, cần ghi trade-off và người chịu trách nhiệm chấp nhận.

Không cho phép một kết quả startup rất nhanh bù cho lỗi chức năng hoặc vi phạm an toàn dữ liệu.

### Đặt ngưỡng theo SLO

Nếu ứng dụng có SLO latency hoặc availability, acceptance criteria phải phù hợp với ngân sách đó. Ví dụ:

- Nếu instance phải phục vụ traffic trong vòng 5 giây, restore-to-ready p95 cần thấp hơn ngưỡng này với phần dự phòng cho orchestration.
- Nếu API có p95 latency budget 100 ms, first-request spike 500 ms có thể cần được xử lý bằng warm-up hoặc readiness gating.
- Nếu pod có memory limit 1 GiB, checkpoint restore không được tạo peak RSS vượt limit hoặc gây OOM.

Không đặt ngưỡng chỉ dựa trên một con số đẹp. Tính đến deployment overhead, image transfer, readiness probe interval, retry, network và dependency startup.

## 11. Báo cáo mẫu có thể điền

Mỗi báo cáo nên có đủ thông tin để người khác lặp lại benchmark mà không phải hỏi lại cấu hình.

### Thông tin chạy thử

| Trường | Giá trị |
|---|---|
| Report ID | [điền] |
| Ngày/giờ đo | [UTC và timezone] |
| Người thực hiện | [điền] |
| Application build | [version + SHA-256] |
| Framework/version | [điền] |
| JDK vendor/version/build | [điền] |
| CRIU version | [điền] |
| Kernel/OS | [điền] |
| Container runtime/orchestrator | [điền] |
| CPU architecture và host class | [điền] |
| CPU/memory limits | [điền] |
| Dependency profile | [test double hoặc dịch vụ thật] |
| JVM flags | [điền] |
| Checkpoint ID | [điền] |
| Workload profile | [request mix, concurrency, duration] |
| Công cụ đo và version | [điền] |

### Kết quả chính

| Metric | Baseline | CRaC | Ngưỡng | Kết quả |
|---|---:|---:|---:|---|
| Cold/restore to ready median | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Cold/restore to ready p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| First request p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Throughput | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Steady-state latency p95 | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Error rate | [ ] | [ ] | [ ] | [PASS/FAIL] |
| RSS peak | [ ] | [ ] | [ ] | [PASS/FAIL] |
| Checkpoint duration | N/A | [ ] | [ ] | [PASS/FAIL] |
| Image size | N/A | [ ] | [ ] | [PASS/FAIL] |
| Restore success rate | N/A | [ ] | [ ] | [PASS/FAIL] |

### Tóm tắt kết quả

Ghi ngắn gọn:

- Restore-to-ready median/p95 và mức cải thiện so với baseline.
- First request latency và thời gian warm-up.
- Throughput, p95/p99 latency và error rate.
- CPU, RSS, image size, checkpoint duration và transfer cost.
- Số lần chạy, số lần thành công/thất bại và độ biến thiên.
- Scenario chưa đạt và nguyên nhân đã xác nhận.

### Phân tích và quyết định

| Câu hỏi | Ghi nhận |
|---|---|
| Mục tiêu hiệu năng chính đạt không? | [bằng chứng] |
| Có regression steady-state không? | [bằng chứng] |
| Có lỗi chức năng hoặc data integrity không? | [bằng chứng] |
| Restore nhiều instance có an toàn không? | [bằng chứng] |
| Dependency có phục hồi đúng thứ tự không? | [bằng chứng] |
| Resource budget có đạt không? | [bằng chứng] |
| Có rủi ro tương thích hoặc bảo mật còn mở không? | [bằng chứng] |
| Quyết định | [ACCEPT / ACCEPT WITH CONDITIONS / REJECT] |
| Điều kiện còn lại và owner | [điền] |

Đính kèm raw output, log đã redact, cấu hình workload, manifest checkpoint, checksum và script đo. Không đính kèm checkpoint image hoặc secret vào báo cáo thông thường.

## 12. Ví dụ báo cáo hoàn chỉnh với dữ liệu minh họa

Phần này cho thấy cách chuyển số liệu thành kết luận. Tất cả số liệu bên dưới là giả lập.

### Bối cảnh

Ứng dụng catalog Java phục vụ HTTP GET và CPU endpoint. Cùng một build và JDK được chạy trong container có 2 vCPU và memory limit 1 GiB. Dependency được mô phỏng bằng service test ổn định. Baseline là cold start; CRaC image được tạo sau khi application context và cache mẫu đã warm-up. Mỗi scenario chạy 10 lần độc lập; steady-state workload chạy 10 phút với 50 concurrent clients.

### Kết quả minh họa

| Metric | Baseline cold start | CRaC restore | Ngưỡng ví dụ |
|---|---:|---:|---:|
| To-ready median | 8.4 s | 1.2 s | Restore p95 ≤ 2.0 s |
| To-ready p95 | 9.1 s | 1.45 s | ≤ 2.0 s |
| First request p95 | 145 ms | 160 ms | ≤ 200 ms |
| Throughput | 4,800 req/s | 4,760 req/s | Regression ≤ 5% |
| Steady p95 | 42 ms | 43 ms | Regression ≤ 5% |
| Error rate | 0.02% | 0.03% | Theo SLO |
| RSS peak | 620 MiB | 650 MiB | ≤ 800 MiB |
| Checkpoint duration | — | 0.78 s | ≤ 1.5 s |
| Image size | — | 185 MiB | ≤ 250 MiB |
| Restore success | — | 10/10 | 10/10 |

Từ hai median to-ready:

- Speedup = 8.4 / 1.2 = 7.0 lần.
- Time reduction = 85.7%.
- Throughput change = (4,760 − 4,800) / 4,800 = −0.83%.
- Steady p95 change = (43 − 42) / 42 = +2.38%.

Theo ngưỡng ví dụ, restore-to-ready p95, first request p95, throughput, steady p95, RSS, checkpoint duration, image size và restore success đều đạt. Error rate cần đối chiếu SLO đã định nghĩa; không thể tự kết luận chỉ từ số liệu nếu chưa biết error budget.

### Kết luận minh họa

Trong cấu hình thử nghiệm này, CRaC giảm median time-to-ready khoảng 85.7% so với cold start và đạt restore p95 dưới 2 giây. Throughput và steady-state p95 thay đổi ít hơn 5%, còn RSS peak và image size nằm trong ngân sách giả định. Kết quả hỗ trợ việc tiếp tục thử nghiệm CRaC cho workload này.

Quyết định triển khai vẫn cần kết quả từ dependency thật, restore trên node mục tiêu, nhiều instance đồng thời, rotation credential, failover và kiểm thử dữ liệu. Bộ số liệu giả lập không đủ để phê duyệt production.

## 13. Những yếu tố làm sai lệch benchmark

| Sai lệch | Tác động | Cách kiểm soát |
|---|---|---|
| Khác JDK build | Startup và CRaC implementation khác | Cố định vendor/version/build |
| Khác JVM flags | Heap, GC, JIT và container behavior khác | Lưu toàn bộ flags |
| Baseline chưa warm-up, image đã warm-up | Lợi ích có thể bị quy nhầm cho restore | Ghi rõ trạng thái checkpoint và so sánh thêm warm baseline nếu cần |
| Dependency khác nhau | Đo network/database thay vì CRaC | Cố định dependency profile |
| Host bị tải nền | Startup và latency dao động | Cô lập hoặc ghi nhận tải nền |
| Load generator bão hòa | Throughput bị giới hạn bởi client | Theo dõi CPU/network của generator |
| Chỉ chạy một lần | Không phản ánh biến thiên | Lặp nhiều lần và báo phân phối |
| Chỉ báo average | Che khuất tail latency | Báo p50/p95/p99 |
| Không tách first request | Lazy initialization bị che | Đo first request riêng |
| Readiness probe quá nhẹ | Báo ready trước dependency | Readiness phản ánh điều kiện phục vụ thật |
| Đo lệnh restore thay vì deployment end-to-end | Bỏ qua tải ảnh/giải nén | Báo cả restore engine time và total deployment time |
| Cache filesystem nóng ở lần sau | Restore có thể nhanh hơn do cache OS | Xen kẽ thứ tự và ghi trạng thái cache |
| Thay đổi concurrency giữa các lần | Throughput/latency không so sánh được | Cố định workload |
| Log verbosity khác nhau | CPU/I/O và thời gian khác | Cố định logging level |
| Restore nhiều instance nhưng chỉ đo một | Bỏ qua contention | Thử concurrent restore và rollout |

### Warm-up và JIT

Checkpoint có thể giữ lại trạng thái đã nạp class, cache và một phần trạng thái runtime/JIT tùy JDK và cách tạo ảnh. Vì vậy, phải mô tả checkpoint được tạo sau bao lâu, với bao nhiêu request, và có chủ đích warm-up những path nào.

Không tạo checkpoint sau một workload rất nặng rồi so với baseline cold start mà không báo điều kiện đó. Một phép so sánh bổ sung có thể là:

- Cold start không warm-up.
- Cold start với warm-up tương đương trước khi đo steady state.
- CRaC restore từ image tạo sau cùng chính sách warm-up.

Ba đường chạy này giúp tách lợi ích startup, lợi ích giữ trạng thái đã khởi tạo và hiệu năng steady-state.

## 14. Đánh giá chi phí tổng thể, không chỉ thời gian restore

CRaC có thể làm restore nhanh hơn nhưng cần tạo, lưu, phân phối và quản lý checkpoint image. Đánh giá tổng thể theo một vòng đời triển khai:

~~~text
Build application
    -> Start JVM and warm up
    -> Create checkpoint
    -> Package and store image
    -> Transfer image to target
    -> Verify and prepare image
    -> Restore JVM
    -> Reconnect dependencies
    -> Open readiness
~~~

Nếu mỗi lần deploy đều phải tạo ảnh mới, chi phí tạo checkpoint thuộc deployment pipeline. Nếu ảnh được dùng cho nhiều instance, chi phí này có thể được chia sẻ nhưng storage/transfer và restore concurrency tăng lên.

### Các phép tính chi phí

**Tổng thời gian đưa instance vào phục vụ:**

\[
T_{\text{total}} =
T_{\text{provision}} +
T_{\text{image transfer}} +
T_{\text{prepare}} +
T_{\text{restore}} +
T_{\text{dependency recovery}}
\]

**Storage cần giữ:**

\[
S_{\text{total}} =
S_{\text{image}} \times N_{\text{versions}} \times N_{\text{copies}}
\]

Đây là mô hình ước lượng đơn giản; storage deduplication, compression, replication và retention có thể thay đổi kết quả.

**Số instance restore đồng thời:**

Không chỉ đo một restore đơn lẻ. Khi nhiều instance cùng đọc một image, storage và network có thể trở thành bottleneck. Ghi throughput đọc artifact, thời gian restore p95, CPU peak và thời gian readiness của toàn nhóm.

### So sánh lợi ích theo kịch bản

| Kịch bản | Câu hỏi kinh tế/kỹ thuật |
|---|---|
| Scale-out thường xuyên | Thời gian restore tiết kiệm có lớn hơn chi phí tạo/lưu/truyền ảnh không? |
| Deploy ít lần | Chi phí vận hành checkpoint có đáng so với cold start không? |
| Nhiều replica | Artifact store và node có chịu được restore burst không? |
| Image lớn | Transfer và storage có xóa mất lợi ích startup không? |
| Workload có dependency chậm | Restore có giảm thời gian dependency recovery không, hay chỉ giảm JVM startup? |
| Node khác kernel/architecture | Có nằm trong ma trận tương thích được hỗ trợ không? |

## 15. Tiêu chí chấp nhận theo giai đoạn triển khai

Không nhất thiết bật CRaC cho toàn bộ traffic ngay sau một benchmark thành công. Có thể dùng các giai đoạn:

### Giai đoạn lab

- Xác minh checkpoint/restore cơ bản.
- Đo cold start và restore-to-ready.
- Kiểm tra chức năng và first request.
- Ghi lại JDK/CRIU/kernel compatibility.

### Giai đoạn staging

- Chạy workload gần production.
- Restore trên node và container profile mục tiêu.
- Kiểm tra dependency thật, secret rotation và consumer rejoin.
- Thử restore nhiều instance đồng thời.
- Xác nhận rollback về cold start khi image không dùng được.

### Giai đoạn canary

- Chỉ áp dụng cho một tỷ lệ nhỏ instance.
- Theo dõi startup p95, error rate, CPU/RSS, consumer lag và readiness.
- So sánh với replica cold start trong cùng khoảng thời gian.
- Có điều kiện dừng rollout nếu hard gate vi phạm.

### Giai đoạn production

- Chỉ mở rộng sau khi canary đạt trong cửa sổ quan sát đủ dài.
- Duy trì cold-start fallback.
- Quản lý image version và retention.
- Theo dõi drift của JDK, kernel, CRIU, dependency và container policy.
- Chạy lại benchmark khi thay đổi thành phần có ảnh hưởng.

### Quy tắc dừng rollout

Ví dụ, dừng rollout nếu:

- Restore success rate thấp hơn ngưỡng.
- Có data corruption hoặc duplicate side effect.
- Có nhiều leader cho cùng role.
- Readiness mở trước khi dependency sẵn sàng.
- Error rate hoặc p99 latency vượt SLO.
- RSS peak gây OOM hoặc CPU throttling kéo dài.
- Artifact không xác minh được checksum/chữ ký.

Các hard gate cần được tự động hóa khi có thể. Không chờ báo cáo cuối ngày nếu metric đang cho thấy lỗi an toàn dữ liệu hoặc tính đúng đắn.

## 16. Checklist trước khi ký báo cáo

### Thiết kế benchmark

- [ ] Mục tiêu và phạm vi đo được viết rõ.
- [ ] Cold start và CRaC restore dùng cùng artifact và cấu hình tương đương.
- [ ] Định nghĩa process start, readiness và first response thống nhất.
- [ ] Workload, request mix, concurrency và duration được cố định.
- [ ] Dependency profile và warm-up policy được ghi lại.
- [ ] Có đủ lần chạy độc lập và raw result.

### Thu thập số liệu

- [ ] Có median và p95 cho startup/restore-to-ready.
- [ ] Có first-request latency và steady-state percentiles.
- [ ] Có throughput và error rate.
- [ ] Có CPU, RSS/heap/native memory và peak usage.
- [ ] Có checkpoint duration và image size.
- [ ] Có transfer/prepare duration nếu thuộc deployment path.
- [ ] Có restore success rate và functional test result.

### Tiêu chí và quyết định

- [ ] Acceptance criteria được xác định trước khi xem kết quả.
- [ ] Hard gate và soft target được phân biệt.
- [ ] Ngưỡng dựa trên SLO và resource budget.
- [ ] Kết quả được tính từ raw sample, không chỉ average.
- [ ] Regression và trade-off được ghi rõ.
- [ ] Scenario chưa chạy hoặc chưa hỗ trợ được nêu rõ.
- [ ] Quyết định ACCEPT/CONDITIONAL/REJECT có owner và điều kiện.

### Khả năng tái lập và bảo mật

- [ ] Ghi JDK, CRIU, kernel, OS, architecture và container runtime.
- [ ] Lưu script, command, config và tool version.
- [ ] Log đã được redact secret.
- [ ] Checkpoint image không được đính kèm công khai.
- [ ] Manifest/checksum và artifact reference được ghi nhận.
- [ ] Có cold-start fallback và kế hoạch rollback.

Một báo cáo hiệu năng CRaC có giá trị khi phép đo tái lập được, các mốc thời gian được định nghĩa thống nhất và tiêu chí chấp nhận được đặt trước. Hãy đo riêng startup, restore, first request, steady state và chi phí artifact; kiểm tra chức năng cùng hành vi khi restore nhiều instance; sau đó đối chiếu với SLO và ngân sách tài nguyên. Chỉ chấp nhận triển khai khi lợi ích về thời gian đi cùng tính đúng đắn, độ tin cậy, khả năng vận hành và bảo mật.
