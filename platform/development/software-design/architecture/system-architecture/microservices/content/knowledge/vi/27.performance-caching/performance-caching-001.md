# Xác định ngân sách độ trễ cho hành trình người dùng

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Hiệu năng và bộ nhớ đệm. Tài liệu hướng dẫn chuyển mục tiêu trải nghiệm của người dùng thành **ngân sách độ trễ (latency budget)** cho toàn bộ hành trình, phân bổ xuống các thành phần frontend, gateway, service, database, cache và dịch vụ bên ngoài; sau đó đo, kiểm tra, điều chỉnh và bảo vệ ngân sách bằng deadline, concurrency control, caching, graceful degradation và observability.

## 1. Vấn đề: một API nhanh không đảm bảo hành trình người dùng nhanh

Trong hệ thống microservices, người dùng không quan tâm một service trả lời trong bao nhiêu mili giây nếu màn hình “Thanh toán” vẫn đứng yên vài giây. Một hành trình có thể gồm tải HTML/JavaScript, xác thực, gọi API gateway, kiểm tra hàng tồn, tính giá, xử lý mã khuyến mại, gọi payment provider, ghi database, phát sự kiện và cập nhật giao diện.

Ví dụ hành trình “Đặt hàng”:

~~~text
Người dùng bấm "Đặt hàng"
      |
      v
Browser: input -> JavaScript -> network
      |
      v
API Gateway: auth / routing / limits
      |
      v
Order Service
   |          \
   |           \--> Inventory Service --> Database
   |
   +--------------> Pricing Service --> Cache/DB
   |
   +--------------> Payment Service --> External Provider
   |
   +--------------> Order Database / Outbox
      |
      v
HTTP response -> browser render -> phản hồi trực quan
~~~

Nếu mỗi nhóm tự đặt mục tiêu “API của tôi p95 dưới 300 ms” mà không có ngân sách tổng, hành trình có thể không đạt kỳ vọng khi các độ trễ nối tiếp hoặc khi fan-out khuếch đại tail latency.

**Latency budget** là giới hạn thời gian được hoạch định cho một thao tác hoặc một giai đoạn của hành trình sao cho toàn bộ trải nghiệm đáp ứng mục tiêu, có phần dự phòng và có cơ chế xử lý khi công việc tiêu thụ hết thời gian. Đây không chỉ là tập hợp cấu hình timeout; nó là một hợp đồng hiệu năng giữa sản phẩm, kiến trúc và các nhóm sở hữu dịch vụ.

## 2. Phân biệt latency, response time, throughput và availability

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| End-to-end latency | Người dùng chờ từ hành động đến phản hồi hữu ích bao lâu? | Click → xác nhận đặt hàng hiện trên giao diện |
| Server response time | Backend mất bao lâu để trả HTTP response? | API POST /orders hoàn tất trong 650 ms |
| Service time | Một worker thật sự xử lý công việc bao lâu? | SQL execution 15 ms |
| Queue waiting time | Công việc chờ trước khi được phục vụ bao lâu? | 80 ms chờ connection pool hoặc executor |
| Network latency | Truyền dữ liệu và round-trip mất bao lâu? | Browser ↔ edge 60 ms |
| Rendering/interaction delay | UI cần bao lâu để hiển thị/phản hồi? | 120 ms sau khi nhận API |
| Throughput | Xử lý bao nhiêu request/giây? | 500 req/s |
| Concurrency | Có bao nhiêu request đồng thời trong hệ thống? | 250 in-flight |
| Error rate | Bao nhiêu yêu cầu không đạt hợp đồng? | 0,3% 5xx trong một giờ |
| Availability | Hành trình có sử dụng được trong cửa sổ SLO không? | 99,9% request thành công theo định nghĩa |

**Latency** thường đo trên các request đã hoàn tất; nếu bỏ hẳn timeout, client cancellation hoặc error khỏi phân tích, chỉ số có thể trông rất đẹp trong khi người dùng gặp thất bại. Cần đo đồng thời **tỷ lệ thành công, tỷ lệ lỗi, thời gian chờ và khả năng hoàn tất trước deadline**.

Một request 503 trả trong 3 ms không phải trải nghiệm checkout tốt. Một API trả 202 Accepted trong 80 ms nhưng tác vụ thực tế hoàn thành sau 30 giây không thể được trình bày như “đặt hàng hoàn tất trong 80 ms”. Phải định nghĩa chính xác **mốc kết thúc của hành trình**.

## 3. Bắt đầu từ hành trình và giá trị sản phẩm

Trước khi phân bổ từng service, xác định hành trình quan trọng bằng ngôn ngữ người dùng.

| Hành trình | Điểm bắt đầu | Điểm kết thúc hữu ích | Đặc điểm |
| --- | --- | --- | --- |
| Tìm kiếm sản phẩm | Người dùng nhập và gửi tìm kiếm | Danh sách kết quả có thể tương tác | Đọc nhiều, nhạy với p95/p99, có cache |
| Xem chi tiết sản phẩm | Click vào sản phẩm | Tên/giá/tồn kho có thể hiển thị | Nhiều nguồn dữ liệu, có thể tải dần |
| Thêm vào giỏ | Click “Thêm” | UI xác nhận giỏ được cập nhật | Có thể optimistic UI nếu có rollback |
| Xác nhận đơn | Click “Đặt hàng” | Biết đơn đã được ghi nhận bền vững | Write path, cần idempotency |
| Thanh toán | Click “Thanh toán” | Kết quả đủ tin cậy để hiển thị | Phụ thuộc provider, trạng thái có thể bất đồng bộ |
| Theo dõi đơn | Mở màn hình đơn | Trạng thái hiện tại/last-updated hiển thị | Dữ liệu eventual consistency có thể chấp nhận |

Không phải màn hình nào cũng cần cùng một con số SLO. Ví dụ dữ liệu tìm kiếm có thể chấp nhận cache cũ trong thời gian ngắn, nhưng tính tiền và xác nhận thanh toán yêu cầu độ đúng cao hơn việc giảm vài chục mili giây. Product owner, kỹ sư frontend, backend và SRE nên cùng thống nhất định nghĩa mốc “hữu ích”.

**Đặt mục tiêu cho hành trình, không chỉ cho service**: nếu người dùng bấm nút lúc 10:00:00.000 và màn hình xác nhận có thể tương tác lúc 10:00:01.100, latency của hành trình là khoảng 1.100 ms dù request API riêng lẻ nhanh hơn nhiều.

## 4. Chọn chỉ số đo và SLO cho hành trình

Một mục tiêu mẫu:

> Trong 28 ngày, ít nhất 95% thao tác “xem giỏ hàng” hợp lệ phải hiển thị nội dung hữu ích trong 800 ms từ lúc người dùng kích hoạt, đồng thời tỷ lệ thao tác thành công theo định nghĩa phải đạt ít nhất 99,9%.

Đây là **ví dụ để giải thích**, không phải chuẩn mặc định cho mọi sản phẩm. SLO cần có:

1. **Population:** request/hành trình nào được tính, phân biệt mobile/desktop, vùng mạng, logged-in/guest khi cần.
2. **Start event:** điểm bắt đầu nhất quán như user interaction timestamp.
3. **End event:** khi UI có nội dung/confirmation hữu ích, không nhất thiết là khi network request xong.
4. **Success criteria:** mã HTTP, dữ liệu đúng, trạng thái nghiệp vụ hoặc acknowledgement có ý nghĩa.
5. **Latency threshold:** chẳng hạn 800 ms.
6. **Compliance target:** ít nhất 95%, 99% hay tỷ lệ khác của hành trình trong cửa sổ.
7. **Window:** rolling 7 ngày, 28 ngày, hoặc cửa sổ kinh doanh phù hợp.
8. **Exclusions:** các loại traffic synthetic, bot, client abort không do hệ thống, nếu chính sách SLO cho phép; phải công bố minh bạch.
9. **Owner:** ai theo dõi, ra quyết định khi vượt ngân sách và ưu tiên cải thiện.

**p95 dưới 800 ms** nghĩa là xấp xỉ 95% các quan sát có latency không vượt 800 ms theo cách tính percentile phù hợp; không có nghĩa mọi request đều nhanh hơn 800 ms. **p99** đặc biệt hữu ích khi trải nghiệm đuôi dài gây bỏ giỏ hàng hoặc ảnh hưởng các khách hàng mạng yếu.

Không lấy trung bình cộng làm thước đo duy nhất. Một phân bố có 99 request 100 ms và 1 request 10 giây vẫn có average dễ gây hiểu nhầm về tail. Đồng thời, percentile cao có nhiều nhiễu thống kê khi số mẫu ít; phải báo sample count, cửa sổ và confidence khi thích hợp.

## 5. Từ hành trình người dùng tới ngân sách tổng

Một ví dụ cho thao tác “Xem trang chi tiết sản phẩm”:

**Target:** 95% hành trình có phản hồi hữu ích không quá 1.200 ms.

Chia ngân sách từ bên ngoài vào:

| Giai đoạn | Ngân sách hoạch định | Ghi chú |
| --- | ---: | --- |
| Input + main-thread scheduling ở browser | 80 ms | Không để JS block quá lâu |
| Request network đến edge | 100 ms | Thay đổi theo vùng/kết nối |
| Edge/Gateway + auth | 70 ms | Bao gồm định tuyến và queue |
| Backend application critical path | 650 ms | Service, DB/cache, downstream |
| Response transfer + render UI | 150 ms | Payload, hydration, vẽ giao diện |
| **Dự phòng/jitter** | **150 ms** | Headroom cho biến động |
| **Tổng** | **1.200 ms** | Chỉ là phân bổ minh họa |

Cộng: 80 + 100 + 70 + 650 + 150 + 150 = 1.200 ms.

**Phân bổ không phải dự đoán chắc chắn:** latency mạng và render có thể biến động mạnh giữa thiết bị. Các con số trên là mục tiêu quản trị, cần hiệu chỉnh bằng dữ liệu real-user monitoring (RUM), server tracing và load test. Nếu hành trình phải đạt trên thiết bị/đường truyền khác nhau, có thể có ngân sách theo phân khúc, nhưng không được giấu traffic chậm khỏi SLO chung nếu sản phẩm cần phục vụ nhóm đó.

**Dự phòng là thành phần thiết kế, không phải lãng phí.** Khi các nhóm cam kết dùng hết toàn bộ 1.200 ms không còn headroom, chỉ một đợt tăng network jitter hoặc p99 DB cũng khiến hành trình vượt mục tiêu.

## 6. Mô hình hóa critical path, không chỉ cộng mọi lời gọi

Một request tới Order có thể gọi Inventory và Pricing song song, rồi mới ghi Order và trả response.

~~~text
Gateway (40)
   |
   v
Order validation (30)
   |
   +----> Inventory (120) ----+
   |                          |
   +----> Pricing (180) ------+-- join (10)
                                   |
                                   v
                              Order DB (70)
                                   |
                                   v
                              Response (20)
~~~

Nếu Inventory và Pricing thực sự chạy **song song độc lập** thì critical path danh nghĩa:

40 + 30 + max(120, 180) + 10 + 70 + 20 = **350 ms**.

Nếu hai call bị thực thi tuần tự, hoặc dùng chung pool chỉ có một worker, mô hình trở thành khoảng:

40 + 30 + 120 + 180 + 10 + 70 + 20 = **470 ms**.

**Cảnh báo:** Các giá trị trên là thời lượng một lần thực thi minh họa. Không được tự động lấy p95 từng service rồi cộng hoặc lấy max để kết luận đó là p95 của hành trình, vì percentile của tổng/max phụ thuộc phân bố, tương quan, queueing, thời điểm tải và phương thức tính. Dùng mô hình critical path để **thiết kế ngân sách**, còn SLO thực được xác minh từ latency end-to-end đã đo.

Với một DAG (directed acyclic graph) của các span, tổng thời gian người dùng chờ được chi phối bởi **đường găng** cộng các phần overhead không nằm trong span. Một span dài nhưng nằm hoàn toàn song song với span còn dài hơn có thể không quyết định latency tổng; tối ưu nó chưa chắc giảm thời gian người dùng.

## 7. Phân bổ ngân sách xuống các service

Từ phần backend budget 650 ms ở ví dụ trước, đặt mục tiêu cho các khâu:

| Thành phần | Budget nội bộ | Chủ sở hữu | Rủi ro chính |
| --- | ---: | --- | --- |
| Gateway → application entry | 35 ms | Platform/API | Routing, auth context, queue |
| Request parsing/validation | 30 ms | Product service | Input lớn, JSON allocation |
| Inventory + Pricing fan-out | 250 ms | Catalog/Inventory | Tail latency và contention |
| DB read/cache path | 120 ms | Product/Data | Pool wait, SQL, cache misses |
| Assembly/serialization | 65 ms | Product service | Payload và object graph |
| **Backend reserve** | **150 ms** | Cross-team | Jitter, shared dependencies |
| **Tổng hoạch định** | **650 ms** | | |

Cộng: 35 + 30 + 250 + 120 + 65 + 150 = 650 ms.

Lưu ý nếu Inventory + Pricing độc lập chạy song song, ngân sách 250 ms mô tả **fan-out segment**, không phải 250 ms cho mỗi nhánh cộng lại. Thực tế cần phân bổ target theo nhánh và tính xác suất fan-out chậm nhất:

- Inventory nên đáp ứng đủ nhanh để không thành critical path thường xuyên.
- Pricing có cache hit/miss; đuôi DB query phải được đo riêng.
- Trạng thái cache cold, deploy mới và invalidation có thể khiến các nhánh cùng chậm.
- Một upstream có thể có budget nhỏ hơn backend tổng vì còn phải reserve thời gian cho fallback, serialization và response.

Mỗi nhóm sở hữu nên nhận **budget, traffic envelope, điều kiện kiểm thử và hậu quả khi vượt budget**, chứ không chỉ một timeout cấu hình. SLO ở cấp service có thể nghiêm ngặt hơn mục tiêu hành trình nếu service đó xuất hiện nhiều lần trong một request.

## 8. Cẩn trọng khi sử dụng p95/p99 của các thành phần

**Sai lầm thường gặp:** Gateway p95 50 ms, Inventory p95 150 ms, Pricing p95 100 ms, DB p95 80 ms, nên checkout p95 = 380 ms.

Đẳng thức đó nói chung **không đúng**. Những request nằm ở đuôi của mỗi thành phần có thể không trùng nhau. Ngược lại, sự cố shared DB hoặc overload có thể khiến nhiều thành phần chậm đồng thời; độ trễ có tương quan.

Nếu n lời gọi độc lập cùng chạy song song và mỗi lời gọi hoàn thành trước thời điểm t với xác suất F(t), xác suất **cả n lời gọi** hoàn thành trước t là F(t) mũ n. Với tám nhánh:

- Nếu mỗi nhánh đạt mốc t ở p95, tỷ lệ cả tám cùng đạt mốc chỉ khoảng 0,95 mũ 8 = 66,3%.
- Để nhánh chậm nhất của tám nhánh đạt mốc t với xác suất 95% dưới giả định độc lập, mỗi nhánh cần F(t) ít nhất 0,95 mũ (1/8), xấp xỉ 99,36%.
- Nếu các nhánh có tương quan, kết quả thực khác; không dùng công thức này khi chưa đánh giá workload và topology.

Điều này giải thích vì sao **fan-out khuếch đại tail latency**. Khi một hành trình gọi nhiều dịch vụ, không thể chỉ yêu cầu mỗi dịch vụ “p95 tốt” rồi kỳ vọng hành trình cũng p95 tốt.

Các nguyên tắc đo lường:

1. Ghi latency end-to-end từ client/RUM hoặc synthetic journey.
2. Dùng distributed tracing để phân tích span, wait time, connection pool và critical path.
3. Đo percentile theo cùng cửa sổ, segment và population; tránh so sánh bảng có traffic mix khác nhau.
4. Không lấy trung bình của p95 từ các instance để tạo p95 toàn cluster; cần gộp histogram/distribution phù hợp.
5. Đo lỗi/timeout riêng vì request thất bại nhanh hoặc bị drop không phải thành công về trải nghiệm.
6. Với bộ mẫu ít, percentile p99 dễ dao động; dùng số lượng mẫu và rolling window.

## 9. Percentile và error budget liên hệ thế nào?

**Latency budget** là phân bổ thời gian cho một lần hành trình và các giai đoạn. **Error budget** của SLO là mức vi phạm được phép trong một khoảng thời gian, có thể gồm lỗi chức năng và thao tác chậm quá ngưỡng theo định nghĩa.

Nếu mục tiêu yêu cầu ít nhất 95% thao tác dưới 800 ms, tối đa khoảng 5% quan sát được phép vượt ngưỡng latency trong cửa sổ đó, theo population và quy tắc đếm đã xác định. Nhưng không nên tự cộng phần vi phạm latency và lỗi nghiệp vụ mà không định nghĩa cụ thể success/validity của SLI.

Ví dụ khác: yêu cầu checkout success 99,9% và trong các thao tác thành công, 95% hiển thị xác nhận dưới 1 giây. Hai SLO này đo hai khía cạnh khác nhau; một checkout fail nhanh vẫn là lỗi availability, không làm SLO latency của thao tác thành công đẹp hơn theo cách che giấu trải nghiệm thật.

Khi ngân sách cạn, cần có **policy vận hành**: tạm dừng rollout rủi ro, giảm fan-out, bật cache/stale-while-revalidate theo giới hạn nghiệp vụ, tối ưu query hoặc mở rộng capacity có kiểm soát.

## 10. Deadline end-to-end khác timeout từng request

**Timeout** là giới hạn một thao tác chờ cụ thể, ví dụ HTTP client chờ Inventory 300 ms. **Deadline** là mốc thời gian cuối cho toàn hành trình, ví dụ request phải hoàn thành trước thời điểm monotonic tương đối tương ứng 900 ms sau khi nhận.

Nếu mỗi service có timeout 2 giây nhưng chuỗi đi qua năm service, tổng chờ có thể lên nhiều giây. Cần **điều phối deadline** để mỗi hop biết còn bao nhiêu thời gian.

~~~text
Client budget 900 ms
  |
  v
Gateway receives after 80 ms -> remaining 820 ms
  |
  v
Order parsing/auth 40 ms -> remaining 780 ms
  |
  v
Inventory request must finish within its local cap
  |
  v
Order DB + response reserve
  |
  v
Finish before end-to-end deadline
~~~

Khi chuẩn bị gọi downstream, tính:

**Allowed downstream time = min(local dependency cap, remaining parent deadline − reserved time for response/finalization)**.

Ví dụ parent còn 500 ms, local Inventory cap là 350 ms và cần reserve 100 ms cho DB/response, thời gian gọi Inventory tối đa 350 ms. Nếu parent chỉ còn 260 ms thì cap lúc này còn tối đa 160 ms. Khi remaining không đủ để hoàn thành tác vụ an toàn, có thể **fail fast** hoặc trả trạng thái async/degraded thay vì khởi tạo thêm công việc chắc chắn trễ.

**Đồng hồ:** đo elapsed trong process bằng monotonic clock như System.nanoTime hoặc clock monotonic của runtime. Khi truyền deadline giữa máy, cần giao thức có semantics rõ ràng, thường truyền **remaining timeout/budget** hoặc một deadline được chuẩn hóa và hiểu clock skew; không tin tuyệt đối vào wall-clock timestamp của client công khai.

Trong gRPC, deadline/timeout propagation được thư viện hỗ trợ; trong HTTP tùy stack cần context/middleware rõ. Không gửi một header client-provided có giá trị “chờ 1 giờ” rồi để nó ghi đè giới hạn server.

## 11. Ví dụ Java: deadline tương đối bằng đồng hồ đơn điệu

Một helper đơn giản để giữ ngân sách trong **cùng JVM**:

~~~java
import java.time.Duration;

public final class DeadlineBudget {
    private final long deadlineNanos;

    private DeadlineBudget(long deadlineNanos) {
        this.deadlineNanos = deadlineNanos;
    }

    public static DeadlineBudget start(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("budget must be positive");
        }
        return new DeadlineBudget(
            System.nanoTime() + budget.toNanos()
        );
    }

    public Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanos));
    }

    public Duration allowance(
        Duration dependencyCap, Duration reserve
    ) {
        Duration available = remaining().minus(reserve);
        if (available.isNegative() || available.isZero()) {
            return Duration.ZERO;
        }
        return available.compareTo(dependencyCap) < 0
            ? available
            : dependencyCap;
    }
}
~~~

Sử dụng:

~~~java
DeadlineBudget deadline =
    DeadlineBudget.start(Duration.ofMillis(800));

Duration inventoryTimeout = deadline.allowance(
    Duration.ofMillis(300),
    Duration.ofMillis(140) // reserve for DB + serialization
);

if (inventoryTimeout.isZero()) {
    throw new RequestDeadlineExceededException();
}

InventoryResponse result = inventoryClient.reserve(
    command, inventoryTimeout
);
~~~

Đây là **minh họa** về cách phân bổ budget. Code thực cần xử lý giới hạn tràn khi cộng nanos cho duration quá lớn; validate budget input từ outside, policy timeout của HTTP client, cancellation và exception mapping. Khi request chuyển qua JVM khác phải propagate **giới hạn còn lại** qua protocol an toàn hoặc dùng API deadline của framework.

**Lưu ý về async:** CompletableFuture.orTimeout giúp future hoàn thành do timeout nhưng không bảo đảm tác vụ mạng/DB phía dưới tự bị hủy. Phải cấu hình timeout thật trên client, cancellation hoặc cleanup thích hợp; không tiếp tục tiêu thụ tài nguyên sau khi caller đã bỏ cuộc. Với write path, cancellation cần kết hợp idempotency/reconciliation vì downstream có thể đã commit.

## 12. Timeout budget, retry và retry amplification

Retry có thể cải thiện tỷ lệ thành công trước lỗi thoáng qua, nhưng tiêu thụ latency budget và tăng tải cho dependency đang yếu.

Ví dụ request có deadline còn 500 ms:

- Attempt 1: timeout 180 ms.
- Backoff có jitter: 40 ms.
- Attempt 2: timeout tối đa 180 ms.
- Reserve để xử lý response: 100 ms.

Tổng kế hoạch: 180 + 40 + 180 + 100 = 500 ms. Nếu attempt 1 mất 250 ms thay vì 180 do cấu hình client không đúng, kế hoạch sẽ vượt deadline. **Retry phải kiểm tra remaining budget trước mỗi attempt**, kể cả backoff.

Một policy gợi ý:

1. Chỉ retry lỗi được xác định transient và **an toàn về idempotency**.
2. Có giới hạn số lần thử và total retry budget.
3. Dùng exponential backoff với jitter, tránh tất cả client retry đồng loạt.
4. Giữ một idempotency key cho cùng thao tác ghi khi downstream hỗ trợ.
5. Không retry ở mọi tầng; nếu Gateway, Order và Payment cùng retry 3 lần, số lời gọi tới provider có thể tăng mạnh theo cấp số nhân.
6. Theo dõi retry_attempts, retried_requests, wasted_work và latency of successful retries.
7. Nếu deadline còn quá ít hoặc dependency circuit mở, fail fast/degrade thay vì retry.
8. Đối với external payment, timeout có thể có kết quả mơ hồ; cần query trạng thái/reconciliation trước khi cho rằng thất bại.

**Bỏ qua retry cũng là quyết định có giá trị:** một bước không quan trọng như recommendations có thể trả placeholder trong 100 ms thay vì retry rồi kéo cả trang chậm thêm 1 giây.

## 13. Fan-out, parallelism và tail latency

Parallel requests có thể rút ngắn critical path nếu các nhánh **thực sự độc lập** và có đủ capacity. Tuy nhiên fan-out đồng thời làm tăng tổng số công việc và rủi ro một nhánh chậm kéo cả request.

~~~text
Order Aggregator
   |
   +-- Product Info ---- 80 ms
   +-- Inventory ------- 210 ms
   +-- Promotions ------ 340 ms
   +-- Recommendations - 600 ms
   |
   +-- wait-for-all --> ~600 ms + join/overhead
~~~

Nếu recommendations chỉ là phần phụ của trang, **không nên buộc toàn bộ màn hình chờ 600 ms**. Có thể trả dữ liệu chính trước, tải recommendations sau hoặc sử dụng cache/skeleton mà không làm sai thông tin đặt hàng. Phải phân loại nhánh nào là critical và nhánh nào có thể degrade.

Các kỹ thuật:

- **Parallelize có kiểm soát:** giảm sequential waits nếu các call không phụ thuộc dữ liệu nhau.
- **Bound concurrency:** không phát 100 request cùng lúc khi mỗi downstream có pool nhỏ; cân bằng với bulkhead và quota.
- **Timebox optional enrichment:** giới hạn thời gian lấy gợi ý/đánh giá; khi hết budget trả partial response có contract rõ.
- **Cache theo từng dependency:** ưu tiên nhánh ổn định và cache được; không cache nhầm giá/tồn kho hết hạn.
- **Hedged requests:** đôi khi giảm tail bằng lời gọi dự phòng sau ngưỡng, nhưng tăng tải/chi phí; chỉ dùng cho thao tác idempotent, có capacity, cancel và quan sát.
- **Batch/coalesce:** thay N calls cho N sản phẩm bằng API batch hoặc data loader để giảm round-trip và N+1.
- **Avoid fan-out to fan-out:** phân tích toàn bộ DAG; 5 fan-out ở service A nhân 5 ở B có thể tạo 25 downstream calls.

Không chạy song song những bước nghiệp vụ đòi hỏi thứ tự hoặc consistency rõ, như charge payment trước khi xác minh reservation khi chính sách không chấp nhận bù trừ.

## 14. Database, connection pool và queueing trong latency budget

Nhiều API tưởng chậm vì SQL nhưng thời gian phần lớn là **chờ connection** hoặc queue. Nên phân tách:

~~~text
HTTP request
  -> wait thread/executor queue
  -> wait DB connection pool
  -> acquire connection
  -> SQL execution
  -> transaction/commit
  -> serialization
  -> response
~~~

Nếu chỉ đo SQL execution 10 ms nhưng connection pool wait 80 ms, tối ưu một index không giải quyết 80 ms chờ pool. Ngoài query p95/p99, đo pool pending, active/idle, connection acquisition time và DB saturation.

### Little's Law

Với hệ ổn định, **L = λ × W**:

- L: số công việc trung bình đang ở trong hệ thống.
- λ: throughput trung bình (công việc/giây).
- W: thời gian trung bình trong hệ thống (giây).

Ví dụ 200 request/giây với thời gian trong hệ thống trung bình 0,3 giây tương ứng khoảng **60 in-flight requests**. Đây là quan hệ trung bình, không thay thế tính toán p99 hoặc capacity planning khi có burst.

### Queueing khi utilization tăng

Trong mô hình M/M/1 lý tưởng, nếu service xử lý trung bình μ = 100 req/s và traffic đến λ = 80 req/s, thời gian hệ thống trung bình W = 1/(μ−λ) = 1/20 giây = **50 ms** dù thời gian service trung bình là 1/μ = 10 ms. Khi λ tiến gần μ, thời gian chờ tăng phi tuyến.

Mô hình trên giả định arrival/service distributions và một server rất đơn giản; **không áp thẳng M/M/1 cho DB pool hoặc Kubernetes thực tế**. Ý tưởng thiết kế quan trọng là không vận hành liên tục ở mức saturation quá cao rồi kỳ vọng tail latency ổn định.

### Đặt giới hạn queue

- Bounded thread pool và request queue.
- Timeout khi chờ connection, tránh request nằm treo vô hạn.
- Admission control, rate limiting, load shedding với HTTP 429/503 có Retry-After phù hợp.
- Backpressure cho message consumers khi queue đầy.
- Scaling chỉ khi downstream có đủ capacity; tăng replica đôi khi làm DB bị quá tải hơn.

**Năng lực không chỉ là số Pod**: nếu 20 Pod × 40 DB connections = 800 connections mà DB chỉ cho phép 500, tăng Pod có thể làm latency tệ hơn.

## 15. Cache trong ngân sách: hit path và miss path

Cache thường là công cụ cải thiện latency nhưng cần phân biệt **hit**, **miss**, **stale**, **refresh** và consistency.

Ví dụ service đọc giá sản phẩm:

~~~text
GET price
   |
   v
Cache lookup (5 ms)
   |
   +-- HIT --> return (5 ms + overhead)
   |
   +-- MISS --> DB read (90 ms) --> populate cache
   |
   v
Response
~~~

Nếu cache hit ratio h = 0,90, latency trung bình đơn giản có thể gần 0,90 × 5 + 0,10 × 95 = **14 ms** (chưa tính network, encode, contention). Nhưng p99 có thể thuộc nhánh **cache miss** với DB 95 ms hoặc cao hơn. Vì vậy một cache có hit ratio 90% không tự đảm bảo p99 nhanh.

Cần đo:

- cache_hit_ratio theo endpoint/khóa/hành vi.
- cache_get_latency hit/miss, backend_load_on_miss.
- cache_ttl, evictions, stale_age và invalidation lag.
- Miss burst khi Pod mới deploy, TTL đồng loạt hết hạn hoặc cache cluster restart.
- Cache stampede: nhiều request đồng thời miss cùng key và cùng đánh DB.
- Stale/error fallback có được phép theo nghiệp vụ hay không.

### Chính sách cache theo dữ liệu

| Dữ liệu | Chiến thuật | Rủi ro cần kiểm |
| --- | --- | --- |
| Danh mục sản phẩm ít đổi | Cache TTL có invalidation | Dữ liệu cũ |
| Gợi ý sản phẩm | Cache + stale-while-revalidate | Tính cá nhân hóa và privacy |
| Mô tả/ảnh | CDN, HTTP caching, immutable assets | Purge và version |
| Giá/tồn kho | TTL ngắn, invalidation hoặc query chính xác lúc checkout | Hiển thị sai giá/hàng |
| Session/authorization | Cache theo chính sách bảo mật, TTL/revocation | Quyền đã bị thu hồi |
| Kết quả tính phí | Cache có key đủ tham số | Dùng sai vùng/tenant/currency |

Nếu checkout cần đúng số lượng tồn kho tại thời điểm xác nhận, một cache ấm có thể giúp UI hiển thị nhanh nhưng **không được dùng như bằng chứng đặt giữ hàng đã thành công**. Ngân sách của bước xác nhận giao dịch phải tính phần xử lý authoritative.

### Chống cache stampede

Dùng TTL jitter, request coalescing/single-flight per key, prewarming chọn lọc hoặc stale-while-revalidate khi nghiệp vụ cho phép. Negative caching có thể giúp giảm truy vấn cho key không tồn tại nhưng cần TTL ngắn để không khóa dữ liệu vừa được tạo.

Thêm cache chỉ hữu ích nếu chi phí invalidation, serialization, network hops và nhất quán thấp hơn lợi ích. Với cache remote, một hot-key bị contention hoặc cache cluster quá tải cũng có thể trở thành điểm chậm.

## 16. Thiết kế trải nghiệm để giảm latency được cảm nhận

Một số hành trình có thể cải thiện đáng kể bằng thay đổi **trình tự hiển thị** thay vì chỉ tăng CPU backend.

- **Progressive rendering:** hiển thị tên và ảnh sản phẩm trước, recommendations tải sau.
- **Skeleton/placeholder:** có thể cải thiện cảm nhận chờ nhưng không được coi là “kết thúc hành trình” nếu người dùng chưa có thông tin hữu ích.
- **Optimistic UI:** phù hợp thao tác có thể rollback, ví dụ thêm sản phẩm vào giỏ cục bộ; không nên hiển thị “đã thanh toán thành công” trước khi có trạng thái đủ tin cậy.
- **Prefetch:** tải trước dữ liệu có xác suất cần cao, giới hạn chi phí và privacy.
- **Batching:** gom nhiều request nhỏ để giảm connection/round-trip overhead.
- **Streaming/server-sent updates:** nhận thông tin sớm khi công việc dài, nhưng cần định nghĩa mốc hoàn tất thật.
- **Async workflow:** nếu nghiệp vụ mất nhiều giây, trả 202 Accepted với job ID và trạng thái PENDING thay vì buộc HTTP connection chờ vô hạn.
- **Payload reduction:** tránh tải JSON 2 MB khi UI chỉ cần 10 trường; nén, phân trang và cache static assets.

Một UI xuất hiện skeleton trong 100 ms nhưng giá thực tế chỉ tới sau 4 giây không nên được báo cáo là latency hoàn tất 100 ms. Dùng sự kiện RUM đúng như khi dữ liệu thật được hiển thị và tương tác được.

## 17. Đường critical và optional: degraded response có hợp đồng

Ví dụ API tổng hợp trang chi tiết sản phẩm:

~~~json
{
  "product": {
    "id": "p-001",
    "name": "Sample Product",
    "price": 125000,
    "currency": "VND"
  },
  "availability": "IN_STOCK",
  "recommendations": [],
  "enrichmentStatus": "PARTIAL"
}
~~~

Khi recommendations hết budget, service có thể trả dữ liệu chính kèm `enrichmentStatus=PARTIAL` để frontend hiển thị vùng phụ tải sau. Việc trả partial response phải được **định nghĩa trong API contract**, không âm thầm bỏ trường bắt buộc.

Phân loại:

1. **Critical:** dữ liệu bắt buộc để quyết định nghiệp vụ (giá thanh toán xác thực, tồn kho lúc giữ hàng). Không được đánh đổi correctness để đạt một con số latency.
2. **Important but degradable:** đánh giá, gợi ý, lịch sử xem; có thể stale/placeholder trong một giới hạn.
3. **Background:** email xác nhận, analytics event, indexing; có thể dùng outbox/message sau khi transaction bền vững được ghi, không chặn response đồng bộ nếu không bắt buộc.

Mọi degrade path phải có metric và alert; nếu một nhánh luôn degrade nhưng API vẫn trả 200 thì hệ thống có thể đang che lỗi thực sự. Người dùng phải được thông báo phù hợp khi thông tin quan trọng chưa cập nhật.

## 18. API gateway và client network budget

Backend thường không kiểm soát hết trải nghiệm: DNS, TLS, mobile radio, browser main thread, edge cache và connection reuse đều ảnh hưởng.

Một ngân sách nên phân biệt:

- **Browser to edge:** network RTT, TLS handshakes, connection setup, packet loss.
- **Edge to backend:** regional routing, proxy hops, WAF, auth/ratelimit.
- **Backend critical path:** application and downstream dependencies.
- **Response transfer:** payload size và băng thông người dùng.
- **UI:** hydration, event loop blocking, layout/render.

Không nên hứa p95 dưới 1 giây cho mọi thiết bị/kết nối nếu chỉ đo ở data center. Dùng RUM theo loại thiết bị, mạng và region, bổ sung synthetic tests có network throttling để hiểu nhóm chậm.

**Server-Timing** có thể giúp lộ breakdown an toàn của các giai đoạn tới browser khi được cấu hình phù hợp, nhưng không đưa nội dung nhạy cảm hay tên host nội bộ vào header public. Distributed trace backend giúp điều tra sâu hơn ở server, còn RUM phản ánh hành trình toàn diện.

## 19. Distributed tracing để dựng ngân sách thực tế

Một distributed trace có thể cho biết:

~~~text
checkout trace (total 850 ms)
|
+-- Gateway/Authenticate                 45 ms
+-- Order Service total                 720 ms
    |
    +-- Inventory call                  180 ms
    +-- Pricing call (parallel)         260 ms
    +-- Payment authorization           300 ms
    +-- DB commit                        90 ms
    +-- Serialize response               30 ms
|
+-- Transfer/render                      (đo từ RUM)
~~~

**Lưu ý:** Tổng span không luôn bằng end-to-end latency vì nested/overlap, gaps, network ngoài instrumentation và sampling. Tracing có thể giúp xác định đường găng, service đang chờ connection/queue và where elapsed time is spent, nhưng phải kết hợp server histogram và RUM.

Các field quan sát hữu ích:

| Thuộc tính/tín hiệu | Ý nghĩa |
| --- | --- |
| trace_id, span_id | Liên kết các hop trong một hành trình |
| service.name, service.version | Xác định component và release |
| http.route | Gom request theo route template, tránh cardinality cao |
| duration_ms hoặc histogram | Latency mỗi hoạt động |
| downstream.name | Nhóm dependency |
| timeout_budget_ms | Local budget được cấp |
| deadline_remaining_ms | Phần còn lại khi gọi downstream |
| retry_attempt | Retry amplification |
| pool_wait_ms, queue_wait_ms | Thời gian không làm nghiệp vụ |
| cache.hit/miss | Giải thích phân bố hit/miss |
| error.code, outcome | Phân biệt lỗi và thành công |
| deployment.region | Phân tích topology và locality |

Không đưa request ID/trace ID vào metric label vì cardinality có thể bùng nổ. Chúng phù hợp log/tracing; metrics dùng service, route, outcome và dependency có số lượng hữu hạn.

## 20. Đo percentile đúng với histogram

Đo latency ở ingress và service bằng histogram hoặc distribution với bucket phù hợp SLO. Nếu mục tiêu 800 ms, các bucket cần đủ chi tiết quanh 800 ms để nhìn ngưỡng; đừng chỉ có bucket 100 ms và 10 giây.

Một biểu thức PromQL minh họa cho p95 tổng hợp:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_server_request_duration_seconds_bucket{
      route="/orders"
    }[5m])
  )
)
~~~

Tên metric và labels phụ thuộc instrumentation/Prometheus version. Với native histogram, cú pháp và hàm có thể khác. **Không lấy trung bình p95 giữa Pod**; phải gộp bucket counts của một population trước khi ước lượng percentile.

Để đo tỷ lệ đạt SLO threshold 0,8 giây có thể dùng bucket với `le="0.8"` nếu histogram có boundary chính xác tương ứng; nếu không, chọn boundary và mô tả sai số ước lượng. Cần kết hợp success/error status và quy tắc population để không coi request lỗi nhanh là thành công.

### Dashboard cấp hành trình

Một dashboard nên đặt cùng nhau:

- RUM end-to-end p50/p95/p99 theo hành trình và segment.
- Success rate, 4xx/5xx, timeout, cancellation.
- Backend latency theo route/service/dependency và trace exemplars.
- Critical path breakdown, queue/pool waits, cache hit ratio.
- Retry rate, fan-out call count, total downstream requests per user action.
- Release/config changes, region và load.
- SLO burn rate, traffic/sample count.

Một p95 tăng chỉ trong mobile 4G nhưng backend không đổi có thể do network/payload/render. Một p99 tăng ở mọi region cùng với DB pool pending sẽ gợi ý vấn đề khác. Không dùng duy nhất một biểu đồ “API average latency” để kết luận.

## 21. Load testing theo hành trình thay vì endpoint cô lập

Một load test chỉ bắn GET /products liên tục có thể không tái hiện traffic thực tế gồm login, search, cart, checkout và background events. Muốn đánh giá latency budget, cần workload model:

- Tỷ lệ các loại hành trình trong traffic mix.
- Số người dùng đồng thời hoặc arrival rate; think time nếu test user journey.
- Dữ liệu hot/cold, tenant distribution, số item/order.
- Tỷ lệ cache hit/miss và warm/cold start.
- Kích thước request/response và network profile.
- Phân bố fan-out, timeout, retry, event processing.
- Burst, traffic ramp, steady state và recovery.
- External provider stub có latency distribution hợp lý.

Chạy ít nhất các pha:

1. **Baseline:** tải bình thường, đo phân bố end-to-end.
2. **Expected peak:** lưu lượng đỉnh dự kiến, xác minh SLO và headroom.
3. **Burst:** tăng đột ngột, kiểm tra queue, admission và retry amplification.
4. **Dependency slowdown:** DB hoặc Inventory p99 tăng, xem degraded behavior.
5. **Cache cold/miss spike:** sau deploy hoặc invalidation, đo hiệu ứng trên DB.
6. **Recovery:** sau sự cố, không có backlog/retry storm kéo dài.

Kết quả cần ghi cùng artifact digest, config revision, dữ liệu thử, arrival rate, resource limits, timestamp và profile dependency. Một bài load test pass ở staging với DB mạnh hơn production không chứng minh production sẽ đạt ngân sách.

## 22. Capacity planning từ ngân sách độ trễ

Nếu ở 300 req/s, request trung bình 200 ms thì Little's Law cho khoảng 60 in-flight request ở steady state. Nếu thời gian tăng lên 500 ms tại cùng throughput, số in-flight trung bình tăng lên khoảng 150. Queue và memory pressure có thể tăng ngay cả khi traffic không đổi.

Để thiết kế capacity:

1. Đo service demand và concurrency per hop.
2. Xác định bottleneck thực: CPU, DB IOPS, connection pool, external quota hay broker.
3. Giữ headroom để p95/p99 ổn định khi traffic burst.
4. Giới hạn queue và worker count theo capacity của dependency.
5. Autoscale trên tín hiệu có tương quan với SLO, ví dụ concurrency/queue pressure/CPU phù hợp, không chỉ replica count.
6. Tính tới cold start của Pod mới và cache warm-up.
7. Giữ rate limits/retry budgets để hệ thống xuống cấp có kiểm soát.
8. Kiểm tra khả năng scale DB/external provider; thêm Pod khi DB đã saturation không giúp latency.

**Throughput cao không đồng nghĩa latency thấp:** Một service có thể xử lý được nhiều req/s bằng cách xếp hàng lâu, nhưng hành trình người dùng vẫn quá deadline. Cần đặt throughput, latency, error rate và resource saturation trên cùng đồ thị.

## 23. SLO-driven alert thay vì một ngưỡng CPU cố định

Alert khi CPU > 80% không trực tiếp khẳng định người dùng đang chậm. Một alert cấp hành trình tốt bắt đầu từ:

- Tỷ lệ thao tác vượt latency threshold trong rolling window.
- Burn rate của error/latency SLO.
- p95/p99 end-to-end tăng cùng sample count đáng tin cậy.
- Tỷ lệ checkout failure hoặc payment timeout.
- Queue wait/pool pending hoặc dependency p99 như tín hiệu nguyên nhân.

Có thể dùng multi-window burn-rate alert để phát hiện nhanh nhưng tránh spam do nhiễu ngắn hạn. Không dùng ngưỡng cứng không gắn với lượng traffic hoặc rủi ro. Ví dụ p99 rất cao trên 10 request hiếm có thể cần triage khác với 50.000 request bị chậm cùng lúc.

Người nhận alert cần runbook: từ user journey SLI → trace/metrics critical path → xác định bottleneck → degrade/rollback/rate-limit hoặc tối ưu đúng tầng.

## 24. Quy trình điều tra khi vượt ngân sách

Giả sử p95 checkout tăng từ 650 ms lên 1.400 ms trong 15 phút:

**Bước 1:** Xác nhận measurement: traffic, device/region mix, success rate và thay đổi instrumentation có giống trước không.

**Bước 2:** Phân tích RUM vs backend. Nếu RUM tăng mạnh nhưng API ổn, kiểm tra payload, network, long tasks và rendering; nếu API tăng, mở traces/histograms của route.

**Bước 3:** Nhìn critical path, không chỉ span lâu nhất. Một span Recommendations 900 ms nhưng không chặn response có thể không phải nguyên nhân.

**Bước 4:** Xem queue/pool wait, DB query, cache miss, retries, fan-out, network hop và provider latency. So sánh cùng khoảng thời gian với release/config changes.

**Bước 5:** Chọn biện pháp tạm có rủi ro thấp: disable optional enrichment, serving stale cache khi cho phép, giảm retry, load shed, rollback config/code hoặc giới hạn concurrency.

**Bước 6:** Sau khi giảm tác động, xử lý nguyên nhân gốc: index/SQL, N+1, connection pool, API batch, architecture dependency hoặc SLO/UX misalignment.

**Bước 7:** Thêm scenario load test và dashboard để phát hiện sớm; xác minh p95/p99 và success rate thực sự phục hồi.

Tránh chỉ tăng timeout của Gateway lên 30 giây để “giải quyết” checkout chậm; làm vậy thường khiến request tiếp tục chờ lâu, giữ tài nguyên và che triệu chứng.

## 25. Các ví dụ bài toán phân bổ ngân sách

### 25.1. Hành trình tìm kiếm

Giả định mục tiêu p95 hiển thị kết quả trong 1 giây. Có 200 ms cho input/network/render, 600 ms cho backend và 200 ms reserve. Backend có thể:

- Gateway 40 ms.
- Query parsing/filter 35 ms.
- Search index 300 ms.
- Hydration product metadata 140 ms.
- Serialize 35 ms.
- Reserve 50 ms.

Tổng backend: 40 + 35 + 300 + 140 + 35 + 50 = 600 ms. Nếu hydration 140 ms và index 300 ms có thể chạy phần nào song song, critical path cần được tính lại theo DAG thực; không tự cộng hai span overlap. Với kết quả search không quan trọng hơn thông tin primary, có thể trả trang đầu trong budget rồi tải phần gợi ý sau.

### 25.2. Hành trình checkout

Giả định mục tiêu p95 có phản hồi đáng tin cậy không quá 1.500 ms. Nên tách phần **xác nhận đã nhận yêu cầu** và **thanh toán hoàn tất** nếu provider có thể mất nhiều giây. Có thể cho client nhận 202 với order ID sau khi lưu durable state, sau đó thông báo trạng thái PENDING/PAID theo async workflow.

**Không dùng 202 như cách “gian lận SLO”**: chỉ được gọi là hoàn thành bước gửi yêu cầu, không gọi là thanh toán thành công. SLO cần đo cả thời gian đến trạng thái cuối cùng khi đó là kỳ vọng người dùng.

### 25.3. Hành trình xem chi tiết sản phẩm

Mô hình có nhánh Inventory 100 ms, Product metadata 120 ms, Recommendations 500 ms. Nếu UI chờ cả ba, tail gần nhánh 500 ms. Nếu recommendations không bắt buộc, service trả product+availability ngay rồi fetch recommendations sau; người dùng có thể tương tác sớm hơn. Phân loại dependency critical/degradable từ đầu.

## 26. Hành trình nhiều bước và asynchronous completion

Một hành trình có thể trải qua nhiều HTTP requests và nhiều giây:

~~~text
Click Checkout
   |
   +-- POST /orders -> 202 Accepted (orderId, status=PENDING)
   |
   +-- Poll /orders/{id} hoặc subscribe update
   |
   +-- Payment provider callback
   |
   +-- Order state chuyển PAID / FAILED
   |
   +-- UI hiện kết quả cuối
~~~

Cần định nghĩa **hai latency SLI riêng**:

1. **Acknowledgement latency:** click → hệ thống xác nhận đã nhận request bền vững.
2. **Business completion latency:** click → kết quả cuối cùng hiển thị hoặc có thể truy vấn theo contract.

Không dùng latency POST 202 làm đại diện cho toàn bộ transaction. Với polling, tính cả interval/backoff và khả năng client offline. Nếu completion vượt SLO, hệ thống cần có message rõ ràng thay vì spinner vô hạn.

Một workflow dài có thể không phù hợp “timeout mỗi hop” như synchronous request; nó cần **saga deadline, expiration, retry policy, delayed queue và trạng thái bền vững** theo từng bước. Nếu một bước trễ, vẫn phải biết trạng thái thực tế để tránh thực hiện trùng.

## 27. Ngân sách theo tenant, region và workload

Một SLO trung bình toàn cầu có thể che trải nghiệm kém ở một region/thiết bị. Có thể chia báo cáo:

- Region và khoảng cách tới data center.
- Mobile/desktop và các lớp kết nối mạng.
- Anonymous vs authenticated flows.
- Tenant lớn/nhỏ và SKU/query complexity.
- Cold cache vs warm cache.
- Peak vs off-peak; weekday vs campaign traffic.
- API read vs write và synchronous vs async.

Không tự tạo hàng trăm SLO không ai sở hữu. Chọn những phân khúc có ý nghĩa sản phẩm hoặc khác biệt kiến trúc. Có thể có target khác nhau do điều kiện mạng nhưng vẫn cần tiêu chí tối thiểu cho nhóm khách hàng trọng yếu.

**Fairness:** Khi một tenant tải lớn gây saturation, các tenant nhỏ không nên phải chịu tail latency không giới hạn. Per-tenant concurrency quotas, fair queueing và rate limits có thể bảo vệ ngân sách. Đo cả tỷ lệ request bị shed để không làm latency metrics đẹp hơn bằng cách từ chối tất cả traffic.

## 28. Bảo mật và dữ liệu trong latency observability

Đo latency theo journey không đòi hỏi thu thập payload nhạy cảm. Không nên đặt email, token, số thẻ, địa chỉ hoặc user ID vào metric labels. Các field được phép thường là route template, service, region, status class, error code và cache hit/miss.

Nếu cần nối user journey với trace, dùng request/trace ID được tạo phù hợp và giới hạn truy cập logs/traces. Correlation ID không phải authorization token; không cho phép ai biết ID là đọc được dữ liệu cá nhân.

Trên frontend, RUM instrumentation cần tuân thủ consent/privacy policy, giảm thu thập nội dung màn hình hoặc query search cá nhân. Server-Timing và error response không nên tiết lộ tên host nội bộ, query SQL hoặc stack traces.

Latency budgets phải bảo vệ **độ đúng và an toàn**: không bỏ authorization, validation, transaction durability hay payment confirmation chỉ để đạt p95. Khi cần nhanh hơn, tối ưu đường đi hoặc chuyển sang trạng thái async minh bạch.

## 29. Kiểm thử tự động ngân sách độ trễ

Bài performance test có thể mô tả acceptance criteria:

~~~text
Scenario: Product detail, normal traffic
Given:
  - image digest đã pin
  - 500 virtual users với traffic mix xác định
  - cache hit ratio theo target, có kịch bản cold miss riêng
  - Product, Inventory và Pricing theo version tương thích
When:
  - load được tăng tới mức peak dự kiến
Then:
  - journey p95 <= 1200 ms
  - journey p99 được theo dõi và nằm trong guardrail đã đặt
  - tỷ lệ thành công đạt SLO
  - backend path không vượt phân bổ lâu dài
  - retry amplification không vượt giới hạn
  - DB pool/queue không bão hòa
  - không có dependency bị gọi ngoài ngân sách
~~~

Đây là contract minh họa; điều kiện thật phải xác định hardware, data set, warm-up, durations, tenant distribution và network. Chỉ một lần chạy với 50 request không đủ kết luận p99 đáng tin.

**Nên test cả lỗi:** Với Inventory timeout, service có response phù hợp trong deadline thay vì treo. Với cache outage, hệ thống có degrade/throttle bảo vệ DB. Với traffic burst, quá tải được phản hồi bằng 429/503 có kiểm soát và không tạo restart storm. Với payment ambiguous outcome, không retry gây double charge dù client timeout.

## 30. Checklist xác định ngân sách độ trễ

- [ ] Hành trình người dùng được định nghĩa bằng sự kiện bắt đầu và kết thúc hữu ích.
- [ ] Có SLI/SLO với population, percentile/threshold, compliance và cửa sổ rõ ràng.
- [ ] Latency đo từ trải nghiệm thật, không chỉ từ API/server logs.
- [ ] Có phân biệt successful requests, failures, timeouts và cancellations.
- [ ] Tổng budget được chia frontend, network, gateway, backend, render và reserve.
- [ ] Sơ đồ DAG/critical path mô tả sequential, parallel và asynchronous steps.
- [ ] Không cộng p95/p99 các service để suy ra p95/p99 journey.
- [ ] Fan-out và tail amplification được nhận diện, nhánh optional có thời hạn riêng.
- [ ] Deadline end-to-end được truyền/áp dụng với giới hạn remaining budget.
- [ ] Retry, backoff và fallback không vượt parent deadline hoặc retry budget.
- [ ] Có idempotency cho write retries và reconciliation cho kết quả mơ hồ.
- [ ] Connection pool/queue waits được đo riêng với execution time.
- [ ] Cache hit/miss/stale và miss storms được đưa vào performance model.
- [ ] Degradation không che lỗi nghiệp vụ quan trọng hoặc trạng thái chưa hoàn tất.
- [ ] Load test dùng traffic mix, peak/burst, cache cold và dependency slowdown.
- [ ] Metrics/histograms/tracing/RUM có route/service/span IDs và cardinality phù hợp.
- [ ] Dashboard liên kết p95/p99, error rate, critical path và release changes.
- [ ] Có owner, runbook và cơ chế hành động khi ngân sách bị vượt.
- [ ] Không hy sinh correctness, security hay durability để giảm latency.
- [ ] Các target được rà soát định kỳ theo dữ liệu thực tế và ưu tiên sản phẩm.

## 31. Câu hỏi thường gặp

**Có nên chia đều 1 giây cho năm service thành 200 ms mỗi service?**

Không mặc định. Có service chạy song song, service khác nằm trên critical path hoặc có tail lớn; network/frontend cũng tiêu thụ thời gian. Phân bổ theo dependency graph, đo thực, rủi ro và phần reserve.

**p95 của ba service lần lượt 100, 150, 200 ms thì p95 journey có bằng 450 ms?**

Không. Percentile của tổng phụ thuộc phân bố và tương quan. Dùng con số này như một budget rough upper-allocation cũng cần chú thích, nhưng không công bố là p95 thực; hãy đo end-to-end.

**Nên đặt timeout theo SLO p95 không?**

Không nên máy móc. Timeout là giới hạn bảo vệ tài nguyên và deadline, còn p95 là mục tiêu phân bố. Timeout quá sát p95 sẽ cắt nhiều request hợp lệ và có thể gây retries; đặt timeout dựa trên remaining budget, behavior dependency, failure tolerance và business deadline.

**Nếu tăng cache hit ratio thì p99 có chắc giảm không?**

Không. Nếu vẫn còn hơn 1% request cache miss và nhánh miss rất chậm, p99 có thể vẫn thuộc nhánh miss. Cần xem hit/miss latency distributions, stampede, cache outage và dữ liệu stale policy.

**Tại sao tăng số Pod mà latency không cải thiện?**

Bottleneck có thể ở DB pool, external quota, Redis hotspot, locks, fan-out hoặc retry storm. Thêm Pod đôi khi tăng số connection/downstream calls và làm chậm hơn. Xác định bottleneck/queue trước khi scale.

**Có cần đo frontend khi backend đã có tracing?**

Có. Tracing backend không thấy đủ device/network/render/main-thread. User journey latency phải đo ở điểm người dùng cảm nhận qua RUM hoặc synthetic browser test, kết hợp server traces.

**Nếu trả 202 trong 100 ms có phải checkout hoàn tất trong 100 ms?**

Chỉ có thể coi đó là acknowledgement latency. Nếu thanh toán/đặt hàng chưa hoàn tất, phải đo completion latency và trạng thái cuối riêng, truyền đạt rõ trên UI.

**Khi một dependency chậm, nên timeout, retry hay degrade?**

Tùy dependency criticality, idempotency, remaining deadline và failure mode. Nhánh phụ có thể degrade, nhánh bắt buộc cần fail/async state rõ ràng; retry chỉ khi có đủ budget và không tăng tải vô ích.

**Làm sao đặt ngân sách khi chưa có dữ liệu production?**

Bắt đầu từ mục tiêu người dùng và phân bổ giả định có reserve; tạo synthetic/load test với traffic và dependency distributions có cơ sở, sau đó cập nhật bằng RUM và traces khi triển khai. Ghi rõ giả định để không coi con số ban đầu là một bảo đảm đã đo.

**Nên ưu tiên tối ưu span lâu nhất không?**

Chỉ nếu nó chi phối đường găng hoặc là bottleneck dưới workload thực. Một span 600 ms chạy song song với span 800 ms có thể không giảm journey khi tối ưu xuống 100 ms. Xem critical path, wait time và fan-out trước khi đầu tư.

---

**Nguyên lý ghi nhớ:** *Ngân sách độ trễ bắt đầu từ hành trình người dùng, được phân bổ theo đường găng và rủi ro của các dependency, được bảo vệ bằng deadline/retry budget/caching/admission control, và phải được xác minh bằng latency end-to-end cùng tỷ lệ thành công. Một API riêng lẻ nhanh không có ý nghĩa nếu toàn bộ trải nghiệm vẫn chậm hoặc không hoàn tất đúng.*