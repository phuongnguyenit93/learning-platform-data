# Benchmark có tải đại diện, warmup và phân bố kích thước dữ liệu

> **Module:** `INTEGRATION_API_REST` — chương **Hiệu năng**. Bài học hướng dẫn thiết kế benchmark REST API có thể tin cậy và lặp lại: chọn **workload đại diện**, warmup JVM và các tầng phụ thuộc, kiểm soát **phân bố kích thước dữ liệu**, đo latency/throughput/error dưới tải, và đánh giá bằng HTTP, Java/Spring, bảo mật cùng kiểm thử tự động. Ví dụ xuyên suốt là một Orders API dùng resource URI, ETag, phân trang, OAuth2/JWT, idempotency và Spring Boot.

## 1. Benchmark nhanh chưa chắc là benchmark đúng

Nhóm vận hành báo cáo:

> “`GET /v1/orders/1` trả 12 ms ở 1.000 request/giây; vậy production chịu được 1.000 request/giây.”

Kết luận có thể sai vì phép đo chỉ dùng **một order nhỏ luôn nằm trong cache**, không có token validation thực, không có phân trang dài, không ghi dữ liệu, chưa mô phỏng giờ cao điểm và không quan sát lỗi dưới tải. Một API tốt ở 1 request đơn lẻ có thể chậm khi:

- 20% GET trả danh sách 100 phần tử thay vì một object 1 KB;
- 5% yêu cầu trả chi tiết hàng nghìn dòng làm tăng serialization/heap/GC;
- 10% POST/PATCH cần DB transaction, khóa và xác thực;
- token/JWKS cache hoặc DB connection pool chưa warm;
- client gửi request nhanh hơn server xử lý, hàng đợi tăng rồi timeout.

**Benchmark** là thí nghiệm có điều kiện và giả thuyết rõ ràng, không phải chỉ chạy một lệnh stress rồi lấy số RPS cao nhất. Tối thiểu, báo cáo phải nói được: **thứ gì đã được tải, tải đến mức nào, dữ liệu lớn ra sao, giai đoạn warmup nào bị loại khỏi số liệu, và bao nhiêu request đã lỗi**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xây dựng workload theo tỷ lệ route/method, arrival rate, mức đồng thời, loại caller và kích thước request/response.
2. Phân biệt **open-loop / arrival-rate** và **closed-loop / concurrency-limited**; tránh benchmark che giấu độ trễ do *coordinated omission*.
3. Tách cold start, warmup và steady state cho JVM, DB, TLS, cache, pool và client.
4. Đo p50/p95/p99, throughput *đạt được*, error rate, CPU/GC/DB saturation cùng một cửa sổ thời gian.
5. Viết kịch bản tải, tích hợp Spring Boot Actuator/Micrometer, kiểm thử hợp đồng HTTP và bảo mật trong khi đo.
6. Làm benchmark tái lập được, so sánh các phiên bản công bằng và quyết định đạt/chưa đạt SLO.

## 2. Xác định câu hỏi và tiêu chí thành công trước khi chạy

Ví dụ mục tiêu của một Orders API:

| Thành phần | Giả định cho ví dụ | Ý nghĩa |
|---|---|---|
| Mức tải mục tiêu | 400 HTTP requests/s trong 15 phút | Tốc độ request **đưa vào** hệ thống |
| Tải đỉnh ngắn | 600 requests/s trong 2 phút | Kiểm sức chịu đựng và hồi phục |
| Latency API | p95 dưới 250 ms, p99 dưới 800 ms tại tải mục tiêu | Đo trên **các request thành công** theo nhóm quan trọng |
| Lỗi do server | 5xx dưới 0,5%; network/timeout cũng phải báo riêng | Không “lọc bỏ request chậm vì bị lỗi” |
| Resource headroom | CPU/heap/pool không bị bão hòa kéo dài | Tránh đạt SLO một lần nhưng không có dư địa |
| Business correctness | Không nhân đôi POST, không lost update | Tốc độ không đánh đổi tính đúng |

Các số trên **hoàn toàn là mục tiêu minh họa**, không phải khuyến nghị chung cho mọi hệ thống. Trong dự án thực, lấy từ SLO, traffic production đã được tổng hợp và kỳ vọng tăng trưởng.

**Đơn vị phải rõ:** RPS đo request hoàn tất hay request được phát? Latency là thời gian phía client (bao gồm mạng/TLS) hay thời gian ở server? Tỷ lệ lỗi tính 5xx, 4xx, timeout và failed checks ra sao? Nếu một nhóm báo “400 RPS” từ generator còn nhóm kia đo “350 RPS” từ server, cần giải thích 50 requests/s đang ở hàng đợi, bị từ chối hay đã timeout.

### 2.1. SLO theo hành trình thay vì một trung bình tổng

Không chỉ dùng một ngưỡng cho mọi route:

~~~text
GET  /v1/orders/{id}                 p95 <= 180 ms
GET  /v1/orders?limit=20             p95 <= 250 ms
GET  /v1/orders/{id}/items?limit=100 p95 <= 450 ms
POST /v1/orders                      p95 <= 650 ms
PATCH /v1/orders/{id}                p95 <= 350 ms
~~~

Một bộ dữ liệu có 90% GET nhỏ có thể khiến **p95 toàn hệ thống** đẹp trong khi 100% request upload lớn bị timeout. Hãy báo cáo **theo route template và nhóm kích thước**, cùng tỷ lệ mix, thay vì chỉ một con số chung.

## 3. Workload đại diện: tần suất route, người dùng và chuỗi thao tác

Workload gồm ít nhất **request mix**, **tốc độ đến**, **phân bố dữ liệu**, **trạng thái cache**, **chủ thể xác thực** và **quan hệ giữa các request**.

### 3.1. Ví dụ traffic mix có căn cứ

| Route / thao tác | Tỷ trọng mẫu | Kích thước, side effect |
|---|---:|---|
| `GET /v1/orders/{id}` | 55% | JSON chi tiết nhỏ/vừa, có ETag |
| `GET /v1/orders?limit=20&cursor=...` | 20% | Danh sách có phân trang, query phụ thuộc dữ liệu |
| `GET /v1/orders/{id}/items` | 10% | Item count lệch phải, đôi khi rất lớn |
| `POST /v1/orders` | 10% | DB transaction, `201 Location`, idempotency |
| `PATCH /v1/orders/{id}` | 5% | `If-Match`, optimistic concurrency và kiểm quyền |

Đây là mix **ví dụ**; không dùng nguyên các tỷ lệ này cho ứng dụng khác. Số liệu nên lấy từ metrics route-template và analytics đã ẩn định danh, với quan sát theo giờ thường, giờ đỉnh và chu kỳ nghiệp vụ. Không sao chép raw request logs chứa token/PII vào môi trường benchmark.

Tỷ lệ route không kể hết thực tế. Một người dùng thường **GET danh sách → GET chi tiết → PATCH với ETag vừa đọc → GET lại**. Nếu phát PATCH ngẫu nhiên trên một order cố định, bài test tạo một lượng `412 Precondition Failed` khổng lồ không đại diện. Nếu tạo một order mới trên mỗi request mà không dọn dữ liệu, chính benchmark làm DB tăng kích thước và lệch kết quả giữa các lần chạy.

### 3.2. Hot keys và long tail

Phân bố ID nên phản ánh:

- **Hot resources:** một tập nhỏ đơn hàng/sản phẩm bị xem nhiều lần.
- **Cold resources:** phần lớn ID được truy cập rất ít, gây cache miss và DB I/O.
- **Orders có nhiều items:** dữ liệu lệch phải, không chỉ order một dòng.
- **Tenant/permission diversity:** caller có thể bị 403/404, nhưng tỷ lệ thử quyền phải đúng kịch bản.
- **Pagination depth:** trang đầu phổ biến, nhưng vẫn có cursor trang sâu và filter/sort phức tạp.

Phân bố `uniform random` trên mọi ID đôi khi không đại diện vì production thường có độ lệch truy cập. Ngược lại, chỉ một `orderId` sẽ tạo cache hit phi thực tế. Có thể dùng hỗn hợp hot/cold, Zipf-like distribution hoặc trace tải đã làm sạch; ghi rõ cách tạo dữ liệu và seed.

## 4. Phân bố kích thước dữ liệu: đừng benchmark bằng giá trị trung bình

Một API trả JSON 3 KB “trung bình” vẫn có thể có 1% request lên 2 MB. Percentile latency, serialization time, network throughput và heap pressure bị chi phối bởi **đuôi phân bố**, không chỉ giá trị trung bình.

Ví dụ phân bố response size (giả định):

| Nhóm | Tỷ lệ | Body sau giải mã | Đặc trưng |
|---|---:|---:|---|
| S — nhỏ | 65% | 0,5–4 KiB | Order ít items |
| M — vừa | 25% | 4–64 KiB | Danh sách 20–100 items |
| L — lớn | 9% | 64–512 KiB | Nhiều items, nested data |
| XL — đuôi | 1% | 512 KiB–3 MiB | Export/aggregate đặc biệt |

Những tỷ lệ này chỉ minh họa cách mô hình hóa; **không đồng nhất kích thước “mục tiêu tạo ra” với body thực nhận**. Ghi nhận thực tế `Content-Length` nếu có, kích thước body mã hóa truyền trên mạng và bytes sau decompression khi cần. `gzip/br` làm kích thước truyền khác kích thước xử lý JSON; một body nén rất tốt vẫn gây chi phí giải nén và cấp phát lớn.

### 4.1. Hai loại kích thước phải đo riêng

1. **Request size:** JSON body cho POST/PATCH, số item trong batch, multipart upload, số header, JWT size.
2. **Response size:** số phần tử, độ sâu nested DTO, field expansion, phân trang, content encoding, payload binary.

Với GET, kích thước **response** thường quan trọng; với POST bulk hoặc file upload, kích thước **request** và tốc độ upload mới là nút cổ chai. Đừng trộn test truyền file lớn với benchmark JSON nhỏ rồi báo một latency chung.

### 4.2. Fixture phải có kích thước và tương quan thực

Seed DB nên chứa tổng số rows tương ứng production scale, chỉ mục, phân bố tenant/order/items, timestamp, hot keys và bản ghi có nhiều quan hệ. Mỗi nhóm kích thước cần **nhiều IDs**. Cần đo kích thước response thực, không giả định `limit=100` đồng nghĩa 100 records luôn được trả.

Với API phân trang, so sánh page đầu và page sâu, filter chọn lọc và không chọn lọc. Offset pagination ở trang sâu có thể tốn nhiều DB work hơn cursor/keyset; nhưng phải đo trên cùng dữ liệu/ordering. Nếu benchmark có quá ít rows, mọi query nằm trong buffer cache và che N+1 queries, index scan hoặc allocation spike.

## 5. Tải được *đưa vào* khác tải server xử lý: open vs closed loop

**Closed-loop** thường có N virtual users (VUs), mỗi user đợi response rồi mới gửi request kế tiếp. Khi server chậm, VU tự giảm request rate — khiến tải phát sinh giảm đúng lúc hệ thống quá tải. **Open-loop/arrival-rate** cố gắng phát request theo lịch độc lập với độ trễ response, thích hợp kiểm SLO ở một offered load xác định.

~~~mermaid
flowchart LR
    A["Mục tiêu: 400 requests/s"] --> B["Arrival-rate generator"]
    B --> C["API / LB"]
    C --> D["App pool + DB + cache"]
    D --> E["Responses + latency + errors"]
    B --> F["Offered, dropped, scheduled requests"]
    E --> G["Achieved throughput, p95/p99, 5xx"]
    F --> H["So sánh offered vs achieved"]
    G --> H
~~~

### 5.1. Coordinated omission

Nếu generator chờ request A mất 5 giây rồi mới phát request B, nó không đo được thời gian chờ mà nhiều request **lẽ ra đã đến** trong 5 giây ấy. Đây là một dạng *coordinated omission*: tail latency trông đẹp hơn thực tế vì nguồn tải đã tự “nghỉ” khi server chậm.

Để giảm sai lệch:

- Dùng arrival-rate/open workload khi đánh giá năng lực chịu **tốc độ đến** cố định.
- Thu thập cả **scheduled/offered**, **dropped iterations**, **completed** và **timeout**; không chỉ latency từ các request hoàn tất.
- Kiểm CPU, network và VU của **load generator**; nếu không phát được lịch, đó là lỗi phép thử, không phải bằng chứng server nhanh.
- Với closed-loop journey thực tế, vẫn dùng để đo UX/think time; **ghi rõ nó là closed-loop**, không suy ra server chịu được offered RPS độc lập.

Trong trạng thái ổn định, Little's Law gợi ý `concurrency ≈ arrival_rate × mean_response_time` (khi cùng ranh giới đo và hệ thống ổn định). Ví dụ 400 requests/s × 0,15 giây ≈ 60 requests đang xử lý; khi latency tăng lên 0,5 giây, nhu cầu in-flight có thể lên khoảng 200 nếu giữ offered load. Đây là **ước lượng**, không thay quan sát hàng đợi/pool thật.

### 5.2. Các kiểu test khác nhau

| Kiểu | Mục đích | Cách đọc kết quả |
|---|---|---|
| Baseline/low load | Kiểm correctness và overhead nền | Không đại diện tải peak |
| Load test ở RPS mục tiêu | SLO p95/p99, errors, headroom | So với mục tiêu đã chốt |
| Ramp test | Tìm điểm gãy, tăng queue/timeout | Kết quả tại từng bước tải |
| Stress test | Tìm giới hạn và failure mode | Có thể không đạt SLO theo chủ đích |
| Soak test (thời gian dài) | Memory leak, pool leak, GC, DB growth | Nhìn xu hướng theo thời gian |
| Cold start test | Instance mới/scale-out, cache lạnh | Báo riêng, không trộn warm steady state |

Một benchmark có thể kết hợp các pha, nhưng **phải tách số liệu**. Không lấy số p95 của ramp-up lẫn warmup rồi gọi là “steady-state p95”.

## 6. Warmup: điều gì phải nóng lên trước khi đo?

Spring/Java API không bắt đầu từ một trạng thái cố định. Lần đầu gọi một endpoint có thể kích hoạt class loading, khởi tạo singleton, build serialization metadata, kết nối DB, đọc schema/cache, resolve DNS hoặc thiết lập TLS. HotSpot JVM còn cần thời gian thực thi để **JIT compile**, tối ưu và đôi khi deoptimize đường code thường dùng.

| Tầng | Hiện tượng khi lạnh | Dấu hiệu/cách kiểm |
|---|---|---|
| JVM | Class loading, JIT tiered compilation, GC chưa ổn định | JFR/GC logs, CPU, code cache, latency theo thời gian |
| Spring & Jackson | Khởi tạo handler, validation và serializer | First-request latency, allocation profile |
| HikariCP / DB | Mở connections, prepare statements, làm nóng buffer cache | Pool active/pending, query latency, DB cache hit |
| TLS/HTTP | DNS lookup, TLS handshake, keep-alive/HTTP2 pool | Connect/TLS timing, connection reuse |
| Redis/application cache | Cold misses, prefill/TTL, eviction | Cache hit/miss và latency theo route |
| JWT/JWKS | Lần đầu fetch key/cache kiểm chữ ký | Độ trễ auth, JWKS fetch và refresh errors |
| Load generator | Khởi tạo VUs, JS modules, pool và network sockets | Dropped iterations, CPU, generator errors |

Warmup **không phải “chờ 30 giây rồi bỏ số liệu”** cho mọi hệ thống. Thời lượng và điều kiện kết thúc dựa trên tín hiệu đã quan sát: p95, throughput, GC, connection pool, cache hit, DB latency **ổn định trong nhiều cửa sổ liên tiếp**. Một giai đoạn warmup có thể từ vài chục giây đến vài phút hoặc hơn; ghi lại thời lượng thực.

### 6.1. Warmup phải đại diện chính workload cần đo

Nếu warmup chỉ GET một ID nhỏ, nó không khởi động code path POST, PATCH, JSON lớn, phân trang sâu, JWT verification hoặc SQL query phức tạp. Khi bước sang đo, các path này vẫn “lạnh”. Vì vậy:

1. Warmup với **cùng route mix** và các nhóm kích thước S/M/L/XL, ở mức tải phù hợp.
2. Kiểm đủ tenant/role hợp lệ, khả năng kiểm scope, serialization, các nhánh có `If-Match`/`If-None-Match`.
3. Không chủ động **prime mọi cache bằng một tập ID nhỏ không thực tế**.
4. Nếu test write làm thay đổi DB, sử dụng dataset/vòng đời fixture để warmup không làm cạn stock hoặc biến tất cả records thành trạng thái không còn sửa được.
5. Chỉ báo cáo **steady-state** sau khi warmup; giữ cold-start report riêng.

### 6.2. Không “warmup để xóa vấn đề thật”

Nếu production thường autoscale trong giờ cao điểm hoặc cache có TTL ngắn, cold start/cold cache là hành vi **cần đo**. Làm hai bộ thử:

- **Steady-state throughput:** warmup để hệ ổn định trước khi ghi kết quả.
- **Cold-start hoặc post-restart:** đo từ trạng thái instance/cache theo thực tế production, bao gồm thời gian sẵn sàng, first-request p99 và lỗi trong lúc scale-out.

Một bài báo cáo chỉ công bố steady-state 10 ms nhưng production user thường gặp first-request 3 giây là báo cáo thiếu phạm vi. Không xóa cache giữa các request nếu mục tiêu là warm production, cũng không để cache nóng hoàn toàn nếu production có phân bố hot/cold.

### 6.3. Cách tách pha và thời điểm đo

~~~text
00:00–02:00   startup / fixture validation (không ghi SLO)
02:00–05:00   warmup cùng request mix, quan sát JIT/cache/pool
05:00–20:00   measurement ở offered RPS mục tiêu (15 phút)
20:00–22:00   peak/ramp riêng (không nhập vào SLO thường)
22:00–25:00   recovery: queue, memory, GC, connection usage
~~~

Nếu tốc độ hoặc p95 còn trôi sau phút thứ năm, **không tự nhận đã warm**; kéo dài warmup hoặc phân loại nguyên nhân. Khi chạy so sánh build A/B, cả hai cần cùng warmup policy, dataset và trạng thái tài nguyên ban đầu. Đo bằng cửa sổ thời gian và tags `phase=warmup|measure|peak` **cố định**, không thêm timestamp hoặc run ID độc nhất vào HTTP server metric labels.

## 7. Môi trường, dữ liệu và thiết kế thí nghiệm tái lập

Một benchmark có giá trị phải có khả năng lặp lại mà không phụ thuộc may rủi. Tối thiểu ghi lại:

- **Code:** commit/build, JDK distribution/version và JVM flags, Spring Boot/Micrometer version, cấu hình thread/connection pools.
- **Hạ tầng:** CPU/memory limits, replicas, load balancer, TLS/proxy, DB engine/version/size/indexes, storage, Redis, network RTT.
- **Data fixture:** số orders/items, tenant counts, nhóm S/M/L/XL, hot key set, seed và tình trạng cache ban đầu.
- **Load:** tỉ lệ route, offered RPS, arrival model, per-request timeout, connection reuse, max virtual users, thời lượng warmup/measurement.
- **Instrumentation:** metrics/traces/GC profiling bật ở mức nào; sampling và metric bucket configuration.
- **Thời gian:** múi giờ, clock synchronization, phiên bản script, test window; tránh chạy cùng batch maintenance/backup.

Load generator nên nằm ở **máy/instance riêng** hoặc ít nhất tài nguyên tách biệt với API để không tranh CPU. Đảm bảo network bandwidth, ephemeral ports, TLS session cache, VU capacity và I/O của generator đủ tải. Nếu load generator chạm 100% CPU hoặc có `dropped_iterations`, không diễn giải throughput thấp là giới hạn chắc chắn của server.

### 7.1. Reproducibility của dữ liệu

Một test POST 10% tại 400 RPS trong 15 phút có thể tạo hàng chục nghìn orders, làm ảnh hưởng index size và query plan; lần chạy sau không còn cùng fixture. Có thể dùng:

1. **DB snapshot/restore** trước mỗi lần đo, trên môi trường test độc lập.
2. **Namespace/tenant test riêng** và cleanup có kiểm soát ngoài giai đoạn đo.
3. **Kho dữ liệu đã seed đủ lớn** và định kỳ reset trạng thái cần thay đổi.

Đừng cleanup database **trong lúc** đo nếu production không làm như vậy; nó tạo áp lực nền giả. Tránh chạy benchmark ghi lên production thật hoặc dùng thông tin cá nhân thật. Với backend phụ thuộc thanh toán/email, phải dùng sandbox/test doubles có đặc tính latency đã được mô tả, **không** gửi giao dịch tiền thật hoặc email cho khách hàng.

### 7.2. Tách nhiễu và lặp phép đo

Chạy baseline nhiều lần (ví dụ 3–5 runs độc lập) theo cùng cấu hình, đặc biệt khi đang so sánh thay đổi hiệu năng nhỏ. Báo median/interval của **run-level result**, không chỉ tổng sample requests gộp từ một lần chạy. Đổi thứ tự A/B hoặc làm A-B-A khi có thể để giảm bias do cache, neighbor workloads và môi trường. Khi không thể kiểm soát các yếu tố này, **nêu rõ hạn chế**, không gán mọi khác biệt cho code.

Nếu tối ưu một query làm p95 giảm 10 ms nhưng error rate tăng hoặc data correctness bị sai, không coi đó là cải tiến. Benchmark phải có **correctness gates** bên cạnh performance thresholds.

## 8. Ví dụ k6: arrival-rate, warmup và nhiều nhóm dữ liệu

Ví dụ sau là kịch bản benchmark cho **Orders API giả định** với các URI tương ứng mục 3. Trước khi chạy phải có **dữ liệu seed và quyền test thật**; endpoint `GET /v1/orders/{id}/items`, `POST /v1/orders` và `PATCH /v1/orders/{id}` phải được implement theo contract của môi trường bài tập. Kịch bản không được dùng lên production có dữ liệu khách hàng.

### 8.1. Chuẩn bị fixture và tham số

Mỗi danh sách sau là chuỗi ID ngăn cách bởi dấu phẩy, lấy từ những orders đã seed:

~~~text
BASE_URL=https://api-bench.example.test
RUN_ID=run_2026_11_18_a
ORDER_IDS_SMALL=ord_s1,ord_s2,ord_s3,...
ORDER_IDS_MEDIUM=ord_m1,ord_m2,ord_m3,...
ORDER_IDS_LARGE=ord_l1,ord_l2,ord_l3,...
ORDER_IDS_XL=ord_x1,ord_x2,...
MUTABLE_ORDER_IDS=ord_edit_1,ord_edit_2,...
BENCH_ACCESS_TOKEN=<token cấp riêng, không log>
PRODUCT_ID=p_bench_17
~~~

Các nhóm **phải chứa nhiều order IDs**, và nhóm mutable nên dành riêng cho updates để giảm 412 do benchmark tự tạo. Token phải có audience/scope/tenant đúng, còn hạn trong toàn thời gian đo; nếu production dùng token refresh, benchmark cần mô phỏng refresh/expiry đúng tần suất thực thay vì dùng token không bao giờ hết hạn.

### 8.2. Script k6 minh họa

~~~javascript
import http from "k6/http";
import exec from "k6/execution";
import {check} from "k6";

const BASE = __ENV.BASE_URL; // Environment test, không là URL tùy ý.
const TOKEN = __ENV.BENCH_ACCESS_TOKEN;
const RUN_ID = __ENV.RUN_ID;

function csv(name) {
  return (__ENV[name] || "").split(",").map(s => s.trim())
    .filter(Boolean);
}
const pools = {
  S: csv("ORDER_IDS_SMALL"),
  M: csv("ORDER_IDS_MEDIUM"),
  L: csv("ORDER_IDS_LARGE"),
  XL: csv("ORDER_IDS_XL")
};
const mutable = csv("MUTABLE_ORDER_IDS");

if (!BASE || !TOKEN || !RUN_ID ||
    Object.values(pools).some(p => p.length === 0) ||
    mutable.length === 0 || !__ENV.PRODUCT_ID) {
  throw new Error("Missing benchmark config or seeded ID pools");
}

export const options = {
  scenarios: {
    warmup: {
      executor: "constant-arrival-rate",
      exec: "exercise",
      rate: 200,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 200,
      maxVUs: 600,
      gracefulStop: "30s"
    },
    measure: {
      executor: "constant-arrival-rate",
      exec: "exercise",
      startTime: "3m30s",
      rate: 400,
      timeUnit: "1s",
      duration: "15m",
      preAllocatedVUs: 400,
      maxVUs: 1000,
      gracefulStop: "30s"
    }
  },
  thresholds: {
    "http_req_duration{scenario:measure}": [
      "p(95)<250", "p(99)<800"
    ],
    "http_req_failed{scenario:measure}": ["rate<0.005"],
    "checks{scenario:measure}": ["rate>0.999"],
    "dropped_iterations{scenario:measure}": ["count==0"]
  }
};

function pick(pool) {
  return pool[Math.floor(Math.random() * pool.length)];
}

function sizeBucket() {
  const r = Math.random();
  if (r < 0.65) return "S";
  if (r < 0.90) return "M";
  if (r < 0.99) return "L";
  return "XL";
}

function headers(extra = {}) {
  return {
    Authorization: "Bearer " + TOKEN,
    Accept: "application/json",
    ...extra
  };
}

export function exercise() {
  const r = Math.random();
  const bucket = sizeBucket();
  const id = pick(pools[bucket]);
  const baseTags = {size_bucket: bucket};
  const timeout = "8s";

  if (r < 0.55) {
    const res = http.get(
      BASE + "/v1/orders/" + encodeURIComponent(id),
      {headers: headers(), timeout,
       tags: {...baseTags, name: "GET /v1/orders/{id}"}});
    check(res, {"detail HTTP 200": x => x.status === 200});
    return;
  }
  if (r < 0.75) {
    const res = http.get(BASE + "/v1/orders?limit=20",
      {headers: headers(), timeout,
       tags: {name: "GET /v1/orders"}});
    check(res, {"list HTTP 200": x => x.status === 200});
    return;
  }
  if (r < 0.85) {
    const res = http.get(
      BASE + "/v1/orders/" + encodeURIComponent(id) + "/items",
      {headers: headers(), timeout,
       tags: {...baseTags, name: "GET /v1/orders/{id}/items"}});
    check(res, {"items HTTP 200": x => x.status === 200});
    return;
  }
  if (r < 0.95) {
    // Một key duy nhất cho MỘT ý định create. Retry cùng ý định
    // phải giữ nguyên key và body, không tạo key mới.
    const key = RUN_ID + "-" + exec.scenario.name
      + "-" + exec.scenario.iterationInTest;
    const res = http.post(BASE + "/v1/orders",
      JSON.stringify({
        productId: __ENV.PRODUCT_ID, quantity: 1
      }),
      {headers: headers({
          "Content-Type": "application/json",
          "Idempotency-Key": key
        }), timeout,
        tags: {name: "POST /v1/orders"}});
    check(res, {"created HTTP 201": x => x.status === 201});
    return;
  }

  // PATCH workflow: GET lấy current ETag trước khi ghi.
  // Mỗi VU nên có order riêng; số ID ít hơn VUs sẽ tạo race.
  const editId = mutable[(exec.vu.idInTest - 1) % mutable.length];
  const target = BASE + "/v1/orders/" + encodeURIComponent(editId);
  const first = http.get(target,
    {headers: headers(), timeout,
     tags: {name: "GET before PATCH /v1/orders/{id}"}});
  const etagEntry = Object.entries(first.headers)
    .find(([name]) => name.toLowerCase() === "etag");
  const etag = etagEntry && etagEntry[1];
  if (first.status !== 200 || !etag) {
    check(first, {"etag precondition available": () => false});
    return;
  }
  const res = http.patch(target,
    JSON.stringify({
      deliveryNote: "benchmark-" + exec.scenario.iterationInTest
    }),
    {headers: headers({
        "Content-Type": "application/merge-patch+json",
        "If-Match": etag
      }), timeout, tags: {name: "PATCH /v1/orders/{id}"}});
  check(res, {"patch HTTP 200": x => x.status === 200});
}
~~~

**Phải hiểu rõ các giới hạn của ví dụ:**

1. Tỉ lệ **55/20/10/10/5 là tỉ lệ iterations theo nghiệp vụ**, không chính xác là tỉ lệ mọi HTTP requests: PATCH còn gửi thêm một GET để lấy ETag. Khi muốn đạt chính xác một mix HTTP, điều chỉnh scenario rates hoặc ghi nhận tỉ lệ request thực tế.
2. `rate:400` là **400 iterations/s được lịch phát**, không mặc nhiên là 400 HTTP requests hoàn tất/s. Khi PATCH có thêm GET, tổng HTTP RPS có thể cao hơn; khi generator thiếu VUs có dropped iterations thì thấp hơn.
3. `preAllocatedVUs/maxVUs` chỉ là số **minh họa**; cần kiểm CPU/RAM và VU utilization của máy phát tải. Không tăng VUs tùy tiện để che server queueing.
4. Test list luôn ở trang đầu và GET dùng pool theo size; production có cursor sâu/cache validators thì bổ sung phân phối đó. Script hiện **chưa đo 304/429 có chủ đích**.
5. Token có thể bị hết hạn, các POST làm DB phình to, PATCH có thể gặp 412 do cạnh tranh nếu mutable pool quá nhỏ. Đây là lỗi cần **đo hoặc sửa fixture**, không được bỏ 412/401 khỏi báo cáo để làm số đẹp.
6. `sizeBucket()` chỉ áp dụng trực tiếp cho requests GET detail/items; list/POST/PATCH có phân bố riêng. Đừng tuyên bố **65/25/9/1 cho mọi HTTP response** chỉ dựa trên trọng số random này; đối chiếu số bytes đo thật theo từng route.
7. `http_req_failed` của k6 mặc định đánh dấu HTTP ngoài tập status kỳ vọng là failure, nhưng `202` có thể được xem là 2xx “thành công” dù contract ở đây yêu cầu 201. Vì vậy còn có threshold `checks`. Nếu benchmark cố ý gửi 304/409/412/429, phân loại expected response **theo từng scenario** và báo status riêng; không cho mọi 4xx là thành công.
8. Hai scenarios warmup/measure có thể cấp phát **VUs và kết nối client khác nhau**. Warmup làm nóng server/DB nhưng không bảo đảm mọi VU đo đã có connection nóng. Khi cần loại bỏ client cold-start khỏi steady-state, đo/gắn nhãn giai đoạn ổn định trong cùng mô hình tải hoặc hiệu chỉnh thời gian chuyển pha và báo rõ cách loại mẫu; đừng tự xóa các spike bất lợi khi chưa giải thích.

Khi chạy, cung cấp các biến môi trường bằng secret store hoặc CLI/CI mechanism an toàn; **không ghi token vào script, shell history hoặc build logs**. Chạy lại khi một lần đo có quá nhiều dropped iterations; báo cáo đó là **invalid offered-load measurement** chứ không lấy p95 của số request ít ỏi còn lại làm kết quả.

## 9. Instrument Java/Spring: đo server, DB và kích thước payload

Với Spring Boot 3, thêm Actuator và Prometheus registry (nếu môi trường dùng Prometheus):

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Một cấu hình cơ bản, cần tinh chỉnh theo phiên bản Spring Boot/Micrometer và cardinality budget:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health, metrics, prometheus
  metrics:
    tags:
      application: orders-api
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

**Không công khai `/actuator/prometheus` ra Internet**: giới hạn bằng management network/port, reverse proxy hoặc authentication đúng môi trường. Endpoint metrics có thể tiết lộ route, tải và thông tin vận hành. Đo bằng Micrometer có overhead; cần bật cùng mức instrumentation ở các phiên bản benchmark đang so sánh.

Trong Spring MVC/WebFlux, HTTP server observation thường cung cấp meter `http.server.requests` với các nhãn hữu hạn `method`, `status`, `uri` (matched **route template**), `outcome`; khi export sang Prometheus thường thấy `http_server_requests_seconds_count`, `_sum`, `_bucket`. Tên và nhãn **có thể thay theo registry/version**, nên xác minh scrape thật.

### 9.1. Cần theo dõi gì cùng HTTP latency?

| Metric/quan sát | Triệu chứng giúp tìm |
|---|---|
| Request rate, p50/p95/p99, 5xx, timeout | SLO, tail latency, overload |
| CPU process/container, throttling | Bị CPU limit; JIT/serialization tiêu tốn CPU |
| JVM heap/allocations, GC pause/time | Body lớn, object churn, stop-the-world |
| Active/pending DB connections | Hikari pool exhausted, queue chờ |
| DB query count/latency, slow SQL, locks | N+1, missing index, deep OFFSET, lock contention |
| Cache hits/misses/eviction | Tải phụ thuộc cache hoặc cold keys |
| HTTP client connection pool và downstream RTT | Dependency timeout, connect bottleneck |
| Network bytes/s, response size percentiles | Compression, bandwidth saturation, payload tail |
| Load generator CPU, dropped iterations, retries | Phép đo không giữ được offered load |

**Đồng bộ cửa sổ thời gian** giữa generator, server, DB và gateway. Nếu p99 tăng từ 200 ms lên 3 giây đồng thời DB pending connections tăng, có bằng chứng để điều tra pool; nhưng correlation chưa chứng minh nguyên nhân. Cần trace/profile/query plan và kiểm thử thay đổi một biến một lần.

### 9.2. Không gắn ID vào label khi đo dữ liệu lớn

Có thể thêm một metric ứng dụng cho kích thước response với **nhóm hữu hạn**, miễn nguồn `actualBytes` thực sự là số byte đã đo và không cần buffer toàn bộ payload:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.DistributionSummary;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {
    private final MeterRegistry registry;

    public PayloadMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordOrderPayload(long actualBytes) {
        if (actualBytes < 0) return;
        DistributionSummary.builder("orders.response.bytes")
            .baseUnit("bytes")
            .tag("route", "/v1/orders/{id}")
            .tag("bucket", bucket(actualBytes))
            .register(registry)
            .record(actualBytes);
    }

    private static String bucket(long bytes) {
        if (bytes < 4L * 1024) return "S";
        if (bytes < 64L * 1024) return "M";
        if (bytes < 512L * 1024) return "L";
        return "XL";
    }
}
~~~

Không gọi hàm với `body.toString().length()` để giả định đó là số byte JSON UTF-8; không serialize toàn bộ DTO **lần thứ hai chỉ để đo**. Đo ở encoder/transport hoặc instrumentation phù hợp, ghi rõ trước/sau nén. Trong benchmark chỉ nên bật custom measurement nếu overhead của nó đã được đánh giá. `bucket` có đúng bốn giá trị; không dùng `orderId`, full URI, `tenantId` hay request body làm tag.

### 9.3. JMH không thay thế HTTP benchmark

JMH phù hợp đo **microbenchmark JVM** như chi phí serialization/deserialization hoặc một hàm chuẩn hóa dữ liệu, vì nó xử lý warmup iterations, measurement iterations, forks và JIT theo cách có cấu trúc. Nhưng JMH **không đo thay** latency API đi qua TLS, network, filters, auth, DB, cache và concurrent load.

Nếu JMH cho serializer mới nhanh hơn 20%, HTTP p95 vẫn có thể không đổi nếu phần lớn thời gian nằm ở SQL. Dùng **JMH để cô lập hàm**, rồi **load test end-to-end để xác nhận lợi ích người dùng**. Với JMH, tránh dead-code elimination và constant folding; dùng state/blackhole theo chuẩn công cụ, kích thước object đại diện và báo JVM/GC/forks.

## 10. Đọc kết quả đúng: percentile, throughput, error và saturation

Một bảng kết quả tốt tách offered/achieved load và phân bố latency:

| Quan sát | Ví dụ giả định | Diễn giải |
|---|---:|---|
| Offered load | 400 iterations/s | Kịch bản cố gắng phát 400 iterations/s |
| Achieved HTTP throughput | 410 requests/s | Có workflow hơn một request; phải đối chiếu mix |
| Dropped iterations | 0 | Generator giữ được lịch trong pha đo |
| p50 / p95 / p99 | 85 / 230 / 720 ms | Đọc **theo toàn bộ cửa sổ đo và route** |
| 5xx / network failures | 0,2% / 0,05% | Lỗi phải hiện ở báo cáo |
| DB pool pending | Thỉnh thoảng tăng đỉnh | Đầu mối cần kiểm tra tail latency |
| Response XL p99 | 2.400 ms | Đuôi kích thước không được che bởi trung bình |

Các số chỉ **mô phỏng cách đọc bảng**, không phải kết quả đo thực tế. `http_req_duration` phía generator bao các giai đoạn gửi request/chờ/nhận body theo định nghĩa công cụ, không mặc nhiên bao thời gian DNS/TLS/connect; ngược lại server HTTP Timer thường đo thời gian xử lý ở server và không gồm toàn bộ round-trip tới client. **Không so sánh hai đồng hồ này như cùng một loại latency**.

### 10.1. Percentile không cộng/trừ trực tiếp

Nếu mỗi route có p95 riêng, **không** lấy trung bình các p95 để tạo “p95 toàn API”. Gộp histogram distributions tương thích hoặc phân tích event samples, rồi tính percentile mới. Cũng không suy ra p99 chỉ bằng p50 × hệ số. Với volume thấp, p99 dao động lớn và phụ thuộc sample count; luôn báo số request cùng cửa sổ.

Đặt p95/p99 bên cạnh:

- **Mean/max** để theo dõi trend, nhưng không thay percentile.
- **Timeout/error**: request thất bại quá chậm có thể bị loại khỏi “latency successful requests”, khiến p95 đẹp giả. Báo failure/timeouts riêng và SLO failure rate đồng thời.
- **Payload bucket**: XL có thể chậm hơn S hàng chục lần; phân nhóm mới biết nguyên nhân.
- **Status**: 304 có body gần như rỗng; 401 do filter trả sớm; 202 chỉ là chấp nhận xử lý nền, không đại diện job hoàn tất.

### 10.2. PromQL minh họa

Nếu Prometheus registry xuất classic histogram `http_server_requests_seconds_bucket` và label `uri`, có thể tính p95 theo route:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{
      application="orders-api"
    }[5m])
  )
)
~~~

Request rate theo route:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="orders-api"
  }[5m])
)
~~~

5xx ratio theo route (chỉ có ý nghĩa khi mẫu đủ lớn):

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="orders-api",status=~"5.."
  }[5m])
)
/
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="orders-api"
  }[5m])
)
~~~

Các query giả định metric/tag theo cấu hình ví dụ. Có stack dùng OpenTelemetry HTTP metrics `http.server.request.duration`/`http.route` và native histograms: khi đó cần query theo tên/format thực, không sao chép máy móc. Đừng gắn raw `/orders/ord_42` làm label mới để có một đường biểu đồ riêng; dùng trace ID khi điều tra request.

## 11. Giữ HTTP contract và tính đúng nghiệp vụ khi benchmark

Benchmark REST không chỉ là `GET 200`. Hệ thống vẫn phải đúng nghĩa HTTP và quyền dữ liệu dưới tải:

| Trường hợp | Điều cần giữ đúng | Cách đo riêng |
|---|---|---|
| `GET` có `If-None-Match` | `304` không body khi ETag khớp, `200` khi khác | Cache hit/revalidation ratio, 200 vs 304 |
| `PATCH` có `If-Match` | 200 khi hợp lệ, 412 khi stale và DB không ghi | 412 rate, optimistic lock failures |
| `POST` có `Idempotency-Key` | Retry cùng key/body không tạo resource thứ hai | Logical creates vs HTTP attempts |
| `GET` phân trang | Không lặp/mất phần tử theo sort/cursor contract | Page depth, latency theo kích thước |
| `202 Accepted` | Job chưa hoàn tất; cần operation monitor | Job queue latency và completion time |
| `429 Retry-After` | Client không retry storm, có quota | Rejected rate và backoff |
| JWT/tenant authorization | 401/403/404 không lộ object và metadata trái quyền | Auth latency, unauthorized test |
| Payload lớn | Size limits, streaming/bounded body | Bytes, serialization/GC, 413/5xx |

### 11.1. Retry có thể làm sai offered load

Khi gặp 503, nếu load generator tự retry ba lần ngay lập tức, tải HTTP thực **tăng cao hơn lịch đã đặt**, tạo retry storm và che nguyên nhân. Nếu mục đích là đo **raw API capacity**, tắt retry tự động để biết request đầu tiên thất bại thế nào. Nếu mục đích là **mô phỏng SDK production**, bật retry như thật: chỉ method/operation replay an toàn, exponential backoff+jitter, `Retry-After`, deadline và báo **số retries riêng**.

Với POST, giữ cùng `Idempotency-Key` qua retries và kiểm server có dedup, không tạo key mới cho lần phát lại cùng ý định. Với `PATCH` dùng `If-Match`, nếu thấy 412 phải đọc lại và xử lý conflict theo business logic, không tự bỏ precondition để “làm phép thử đạt 200”.

### 11.2. Bảo mật khi tạo tải

Chỉ benchmark trên **môi trường được phép**, token test scoped đúng audience/tenant, TLS được xác minh; không tắt certificate/hostname validation để “giảm overhead” trừ khi bài đo riêng và đã công bố rõ. Không lưu token, email, mật khẩu, signed download URL, request/response body chứa PII vào logs hoặc metric labels.

Để đo behavior production, xác thực phải ở trạng thái đại diện: không bỏ qua JWT verification hoặc object ACL chỉ để API nhanh hơn. Nếu cần định lượng chi phí auth, chạy **một thí nghiệm so sánh riêng** với cấu hình kiểm soát, không công bố bản tắt auth như benchmark production.

### 11.3. Hợp đồng OpenAPI hỗ trợ đo đại diện nhưng không bảo đảm SLO

OpenAPI 3.1 có thể công bố **giới hạn input/pagination, response content và status** giúp test generator không phát yêu cầu ngoài contract:

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /v1/orders:
    get:
      security: [{bearerAuth: []}]
      parameters:
        - name: limit
          in: query
          schema: {type: integer, minimum: 1, maximum: 100, default: 20}
        - name: cursor
          in: query
          schema: {type: string}
      responses:
        '200':
          description: Trang đơn hàng của caller
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    maxItems: 100
                    items: {type: object}
        '429':
          description: Rate limit
          headers:
            Retry-After:
              schema: {type: string}
  /v1/orders/{id}:
    get:
      security: [{bearerAuth: []}]
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Chi tiết đơn hàng
          headers:
            ETag: {schema: {type: string}}
        '304': {description: Not Modified, không có body}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
~~~

`maxItems` chỉ ràng buộc số phần tử trong schema, **không bảo đảm response nhỏ hoặc API nhanh**: mỗi item vẫn có thể chứa field dài/nested structure. Kiểm tính đúng OpenAPI bằng contract test, rồi kiểm p95/p99 và payload sizes **bằng đo thực tế**. Thông số `400 RPS` hay `p95 250 ms` thuộc mục tiêu vận hành/SLO, không được suy ra từ OpenAPI schema.

## 12. Kiểm thử benchmark trước khi tin số liệu

Một **load script sai** cũng có thể tạo dashboard đẹp. Trước khi chạy tải lớn, thực hiện kiểm thử nhỏ để xác nhận:

1. **HTTP contract:** GET/POST/PATCH/HEAD trả đúng status, JSON schema, `ETag`/`If-Match`, `Location`, lỗi 400/401/403/404/412/429.
2. **Fixture:** mọi nhóm ID tồn tại, nhiều tenant, tỷ lệ size được đo đúng, không có trường hợp toàn response trả body rỗng/404.
3. **Client script:** request gửi đúng Authorization, JSON, URL, content type; status checks thất bại khi có regression.
4. **Phân bố:** tần suất route/size bucket gần mục tiêu trong một số lượng mẫu đủ lớn; kiểm **traffic thực** ở gateway/server.
5. **Generator:** cùng cấu hình nhận ít hoặc không có dropped iterations; CPU/network không bị bão hòa.
6. **Server telemetry:** một route template xuất hiện dưới các status khác nhau mà không tạo label theo order ID.
7. **Độ lặp:** warmup/measure windows tách, không có job ngoài gây nhiễu, không dữ liệu tích lũy sai giữa các runs.

### 12.1. Unit test nhóm kích thước metric trong Java

Với `PayloadMetrics` ở mục 9, dùng `SimpleMeterRegistry` để bảo đảm metrics chỉ có bốn bucket hữu hạn:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PayloadMetricsTest {
    @Test
    void assignsFixedBucketsWithoutUsingResourceIds() {
        try (var registry = new SimpleMeterRegistry()) {
            var metrics = new PayloadMetrics(registry);
            metrics.recordOrderPayload(1024);        // S
            metrics.recordOrderPayload(12 * 1024);  // M
            metrics.recordOrderPayload(200 * 1024); // L
            metrics.recordOrderPayload(900 * 1024); // XL

            assertEquals(1L, registry.get("orders.response.bytes")
                .tag("bucket", "XL").summary().count());
            assertEquals(4, registry.getMeters().stream()
                .filter(m -> m.getId().getName()
                    .equals("orders.response.bytes"))
                .count());
            assertTrue(registry.getMeters().stream()
                .noneMatch(m -> m.getId().getTags().stream()
                    .anyMatch(t -> t.getKey().equals("orderId")
                        || t.getKey().equals("tenantId"))));
        }
    }
}
~~~

Test này xác minh **metric custom** có cardinality hữu hạn, **không** xác minh HTTP response bytes đã được đo chính xác. Độ chính xác của `actualBytes` cần test ở boundary serializer/network với payload có ký tự UTF-8, compression và streaming; không nên giả vờ `String.length()` là byte count.

### 12.2. HTTP integration test tối thiểu trước load

Ví dụ `MockMvc` cho API tạo đơn: kiểm 201/Location và payload có field cần thiết; phần auth/fixture phải được cấu hình bằng Spring Security Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderBenchmarkContractTest {
    @Autowired MockMvc mvc;

    @Test
    void createOrderReturnsValidContractBeforeLoad() throws Exception {
        mvc.perform(post("/v1/orders")
                .with(jwt().jwt(j -> j
                    .subject("benchmark-user")
                    .claim("tenant_id", "benchmark_tenant"))
                    .authorities(() -> "SCOPE_orders.write"))
                .header("Idempotency-Key", "test-create-001")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"p_bench_17","quantity":1}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.id").isNotEmpty());
    }
}
~~~

Snippet giả định endpoint hỗ trợ `Idempotency-Key`, tenant/user fixture và product `p_bench_17`; cần **isolate/cleanup test data**. Một `MockMvc` request pass không chứng minh throughput ở 400 RPS. Ngược lại, load test không thay thế kiểm thử dedup/idempotency, optimistic locking và object-level authorization ở DB.

### 12.3. Kiểm bằng dữ liệu thay vì tin nhãn “S/M/L/XL”

Với mỗi size bucket, lấy mẫu nhiều response và ghi:

~~~text
size_bucket | response_count | min_bytes | p50_bytes | p95_bytes | max_bytes
S           | ...            | ...       | ...       | ...       | ...
M           | ...            | ...       | ...       | ...       | ...
L           | ...            | ...       | ...       | ...       | ...
XL          | ...            | ...       | ...       | ...       | ...
~~~

Nếu pool “XL” thực tế trả 404 hoặc JSON 500 bytes vì dữ liệu bị phân quyền/serialization khác, phép thử không còn đại diện. Nếu `Content-Encoding: gzip`, nêu rõ bảng này là **bytes đã giải nén**, **bytes trên wire** hay **kích thước DB row**; không trộn chúng.

### 12.4. Một phép thử hợp lệ phải có validation gates

Đánh dấu run **INVALID** nếu thiếu data seed, token sai, hơn ngưỡng dropped iterations, generator quá tải, không thu được metrics, có khoảng thời gian triển khai/DB backup xen vào, hoặc workload mix sai xa mục tiêu. Trường hợp app thật trả 5xx/timeout ở tải đã chốt là **kết quả FAIL của hệ thống**, không được tự loại run để lấy số đẹp. Phân biệt **lỗi phép đo** và **lỗi sản phẩm**.

## 13. Phương pháp báo cáo và so sánh thay đổi hiệu năng

Mỗi báo cáo có thể dùng mẫu sau:

~~~text
Benchmark: Orders API / load test / benchmark_tenant (synthetic only)
Build: <commit/version>        JDK: <vendor+version>
SUT: 3 replicas, 2 vCPU/4GiB mỗi instance; DB fixture 1 triệu orders
Tool: k6 <version>; script hash <...>; generator: host riêng
Warmup: 3m + 30s chuyển pha (báo riêng)
Measurement: 15m, target=400 iterations/s
Traffic: 55% GET detail, 20% list, 10% items, 10% POST, 5% PATCH
Data size: S=65%, M=25%, L=9%, XL=1% theo phân bố fixture
Observed: offered iterations/s=?, achieved HTTP RPS=?, dropped=?
HTTP: status histogram=?, 5xx=?, timeout=?, 401/412/429=?
Latency: p50=?, p95=?, p99=? theo route và size bucket
Resources: CPU=?, throttling=?, heap=?, GC=?, DB pool/locks=?
Correctness: duplicate creates=0; lost updates=0; tenant leaks=0
Decision: PASS/FAIL/INVALID; bằng chứng & link metrics (đã lọc)
~~~

Không cần công bố token, tenant thật, order ID thật, raw URL chứa query, dữ liệu cá nhân hoặc response body. Có thể dùng **run ID trong artifact/report** để liên kết dashboard và build, nhưng tránh gắn run ID duy nhất vào **mọi metric HTTP tag** vì nó làm tăng số time series tích lũy.

### 13.1. So sánh A/B có trách nhiệm

Giả sử build B giảm p95 của GET 180 → 150 ms nhưng làm p99 XL tăng 800 → 1.400 ms. Nếu chỉ nói “p95 nhanh hơn 17%” sẽ bỏ qua regression cho payload lớn. Bảng so sánh nên có:

| Chỉ số | Build A | Build B | Quyết định |
|---|---:|---:|---|
| GET detail p95 | 180 ms | 150 ms | Tốt hơn |
| GET XL p99 | 800 ms | 1.400 ms | Regression cần điều tra |
| POST p95 | 420 ms | 440 ms | Kiểm biến động/lặp lại |
| 5xx | 0,1% | 0,1% | Tương đương |
| Dropped iterations | 0 | 0 | Phép thử hợp lệ |
| Duplicate logical creates | 0 | 0 | Không đánh đổi correctness |

Đây là các **giá trị giả định**. Không kết luận cải thiện nhỏ có ý nghĩa nếu chưa có các runs lặp, khoảng dao động và điều kiện môi trường giống nhau. Khi đo sau một thay đổi có cache, đảm bảo cache warm/cold policy giống giữa hai builds.

### 13.2. Những câu hỏi cần trả lời từ kết quả

1. Tốc độ đưa vào hệ thống có được giữ đúng không? Có dropped iterations/queues không?
2. Tất cả route **quan trọng** đạt latency/error SLO riêng hay chỉ trung bình toàn hệ thống đẹp?
3. S/M/L/XL tạo ra tail latency khác nhau ra sao; response size thực có đúng phân bố mong đợi?
4. CPU, heap/GC, DB pool, lock, cache và downstream nào tăng sát trần trước khi lỗi xuất hiện?
5. Benchmark có giữ ngữ nghĩa HTTP, idempotency, kiểm quyền và trạng thái nghiệp vụ không?
6. Kết quả có tái lập ở nhiều runs/các node không; giới hạn và giả định nào chưa được kiểm?

Một kết quả “500 RPS với p95 100 ms” **không đầy đủ** nếu không ghi lỗi, thời lượng, dữ liệu, số người gọi, cache, test environment và cách lấy percentile.

## 14. Bài thực hành: benchmark Orders API có tải đại diện

**Bối cảnh:** ứng dụng Spring Boot có `GET /v1/orders/{id}`, `GET /v1/orders?limit&cursor`, `GET /v1/orders/{id}/items`, `POST /v1/orders` và `PATCH /v1/orders/{id}`. Hệ thống có JWT Resource Server, Spring Data JPA, Redis cache, PostgreSQL, một outbox worker và Prometheus metrics. Có phản ánh từ người dùng rằng GET list trang sâu và POST vào giờ cao điểm chậm dù benchmark nội bộ chỉ thấy 20 ms.

**Nhiệm vụ:**

1. Lập bảng route/method/status và tỉ trọng workload từ dữ liệu quan sát đã ẩn định danh; đề xuất offered rates cho giờ thường/giờ đỉnh.
2. Seed tối thiểu bốn nhóm response size S/M/L/XL với nhiều IDs, long-tail items, hot/cold distribution và trang cursor sâu.
3. Viết k6 script open arrival-rate có warmup/measurement riêng, token test, timeout, max VUs và thresholds; giải thích **iterations/s ≠ HTTP RPS**.
4. Thiết kế một biến thể closed-loop mô phỏng user journey/think time; so sánh tại sao throughput tự giảm khi latency tăng.
5. Tạo ít nhất hai benchmark: steady-state warm và cold-start/cache-cold, báo cáo riêng.
6. Bật Actuator/Micrometer với HTTP route-template labels, histogram p95, DB pool và GC; không ghi order ID/tenant/token vào labels.
7. Đo HTTP 200/201/202/304/401/409/412/429/503, response size thực và tỷ lệ failed checks; phân biệt lỗi script fixture với lỗi server.
8. Kiểm POST retries giữ `Idempotency-Key` và PATCH dùng `If-Match`; test DB chứng minh không duplicate create/lost update.
9. Chạy nhiều runs độc lập với cùng fixture/config, tổng hợp offered/achieved load, p95/p99 theo route/size, error và CPU/DB saturation.
10. Đề xuất một cải tiến (pagination index, connection pool, query batching hoặc serialization), chạy lại và chứng minh **không có regression ở XL/p99**.

**Tiêu chí đạt:** benchmark giữ được mức offered load, có dữ liệu S/M/L/XL thực sự khác nhau, phân biệt warm/cold, không bỏ requests lỗi khỏi báo cáo, có bằng chứng DB/auth đúng và so sánh A/B tái lập được.

## 15. Checklist cuối bài

| Câu hỏi kiểm tra | Đạt khi |
|---|---|
| Có mục tiêu định lượng? | Offered load, window, latency/error SLO, cách đếm rõ |
| Tải đại diện? | Mix route/method/status/tenant, read/write workflow, hot/cold |
| Có size distribution? | S/M/L/XL đo bằng bytes và item counts thực |
| Warmup được tách? | Có tiêu chí ổn định; không trộn cold-start với steady-state |
| Không có coordinated omission nghiêm trọng? | Arrival model phù hợp, theo dõi dropped/achieved |
| Load generator đủ tài nguyên? | Không bão hòa CPU/network/VUs |
| Observability đầy đủ? | HTTP, GC, DB, cache, queue, downstream; route labels hữu hạn |
| HTTP semantics đúng? | 201/202/304/409/412/429, auth, idempotency, preconditions |
| Tài nguyên riêng tư an toàn? | Token test, không PII, không benchmark tiền thật |
| Kết quả lặp lại được? | Commit, JDK, fixtures, cấu hình, runs và sai số |
| Báo cáo không che lỗi? | Timeout, 5xx, business conflicts và invalid runs tách rõ |

## 16. Ghi nhớ

**Benchmark đáng tin là phép thử có workload đại diện, trạng thái warmup được kiểm soát và phân bố dữ liệu được đo thật.** Một ID nhỏ lặp lại hàng triệu lần không đại diện cho API có phân trang, payload đuôi dài, xác thực, ghi DB và concurrent updates. RPS không đủ; cần biết offered/achieved rate, p95/p99 theo route/size, lỗi, GC, DB, cache và generator có giữ nổi lịch hay không.

Hãy tách **microbenchmark Java**, **HTTP end-to-end load**, **cold start** và **steady-state** đúng mục đích. Việc tối ưu chỉ có ý nghĩa khi hợp đồng REST, bảo mật và tính nhất quán vẫn đúng dưới tải, và kết quả có thể **lặp lại, kiểm tra và giải thích**.
