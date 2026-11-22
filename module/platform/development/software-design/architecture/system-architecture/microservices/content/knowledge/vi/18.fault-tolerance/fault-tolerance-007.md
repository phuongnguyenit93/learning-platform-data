# Giới hạn lưu lượng, tải nhận vào và loại bỏ tải có chủ đích

**Chủ đề:** Khả năng chịu lỗi trong kiến trúc hệ thống và microservices.

Một dịch vụ có thể hoạt động đúng ở 100 yêu cầu/giây nhưng sụp đổ ở 300 yêu cầu/giây, dù mỗi yêu cầu riêng lẻ đều hợp lệ. Khi quá tải, hàng đợi dài ra, thời gian phản hồi tăng, kết nối và luồng xử lý bị giữ lâu hơn; các yêu cầu hết hạn lại kích hoạt thử lại, khiến chính hệ thống đang yếu nhận thêm tải. Vì vậy, khả năng chịu lỗi không chỉ là phục hồi sau sự cố mà còn là **quyết định có kiểm soát loại công việc nào được nhận, loại nào phải chờ và loại nào cần từ chối sớm**.

Bài học này trình bày ba cơ chế bổ trợ: **rate limiting** (giới hạn tốc độ yêu cầu), **admission control** (kiểm soát việc tiếp nhận công việc dựa trên năng lực) và **load shedding** (chủ động loại bớt tải khi hệ thống bị áp lực). Mục tiêu cuối cùng là giữ cho phần công việc đã chấp nhận có cơ hội hoàn thành đúng hạn, bảo vệ tài nguyên chung và tránh quá tải lan truyền giữa các dịch vụ.

## 1. Mô hình tư duy: nhu cầu đến không đồng nghĩa với năng lực xử lý

Hãy hình dung chuỗi gọi trong hệ thống đặt hàng:

~~~mermaid
flowchart LR
    U[Client] --> G[API Gateway]
    G --> O[Order Service]
    O --> I[Inventory Service]
    O --> P[Payment Service]
    I --> D[(Database)]
    P --> X[Payment Provider]
~~~

Ở giờ cao điểm, gateway có thể nhận 2.000 yêu cầu/giây, nhưng dịch vụ thanh toán hoặc cơ sở dữ liệu chỉ chịu được một phần trong số đó ở mức độ trễ chấp nhận được. Nếu gateway tiếp tục chuyển mọi yêu cầu, các dịch vụ phía sau sẽ xếp hàng; một dịch vụ chậm còn giữ tài nguyên của dịch vụ gọi nó, tạo hiệu ứng dây chuyền.

Một mô hình đơn giản:

- **Tải đến (offered load):** lượng công việc muốn vào hệ thống, tính theo yêu cầu/giây, tác vụ/giây hoặc chi phí tài nguyên.
- **Tải được nhận (admitted load):** phần công việc hệ thống thực sự cho phép bắt đầu xử lý.
- **Năng lực bền vững (sustainable capacity):** mức tải dịch vụ có thể duy trì mà độ trễ, tỷ lệ lỗi và mức dùng tài nguyên vẫn nằm trong mục tiêu.
- **Tải bị từ chối (rejected/shed load):** công việc không được nhận hoặc bị loại một cách có chủ đích để giữ hệ thống ổn định.

Không có chính sách nào bắt buộc tất cả yêu cầu phải thành công tức thời. Khi tài nguyên khan hiếm, từ chối sớm một phần yêu cầu thường tốt hơn nhận tất cả rồi để phần lớn hết hạn.

## 2. Phân biệt ba cơ chế

| Cơ chế | Câu hỏi quyết định | Tín hiệu chính | Hành vi thường gặp |
|---|---|---|---|
| **Rate limiting** | Chủ thể này được gửi bao nhiêu công việc trong một khoảng thời gian? | Quota, tốc độ yêu cầu, token còn lại | Từ chối vượt hạn mức, thường HTTP 429 |
| **Admission control** | Ngay lúc này hệ thống còn chỗ để bắt đầu công việc mới không? | Số yêu cầu đang xử lý, slot, hàng đợi, ngân sách thời gian | Chấp nhận, xếp hàng có giới hạn hoặc từ chối |
| **Load shedding** | Khi quá tải, nên bỏ bớt công việc nào để bảo vệ phần quan trọng? | Bão hòa, độ tuổi hàng đợi, độ trễ, độ ưu tiên, mức tiêu thụ tài nguyên | Loại tải ít quan trọng hoặc từ chối sớm, thường HTTP 503 |

**Ví dụ:** Tenant A có quota 20 yêu cầu/giây. Dù tenant mới gửi 5 yêu cầu/giây, dịch vụ có thể đã đầy 64 slot do các tenant khác nên admission control vẫn từ chối yêu cầu mới. Khi cơ sở dữ liệu bắt đầu bão hòa, load shedding có thể tạm bỏ thao tác gợi ý sản phẩm nhưng giữ thao tác thanh toán. Do đó, đạt quota không bảo đảm yêu cầu luôn được tiếp nhận.

Ba lớp giải quyết ba vấn đề khác nhau: **công bằng và ngân sách sử dụng**, **năng lực tiếp nhận hiện tại**, và **sự sống còn của dịch vụ khi tải vượt khả năng**.

## 3. Tại sao hàng đợi vô hạn nguy hiểm?

Giả sử tốc độ đến trung bình là lambda và tốc độ hoàn thành trung bình là mu. Với mô hình hàng đợi rất đơn giản, khi lambda tiến gần mu, thời gian chờ tăng mạnh; nếu lambda duy trì lớn hơn mu, số công việc chờ sẽ tiếp tục tăng cho đến khi hết bộ nhớ, kết nối, luồng hoặc ngân sách thời gian.

Định luật Little trong điều kiện hệ thống ổn định:

**L = lambda × W**

Trong đó L là số công việc trung bình đang ở trong hệ thống, lambda là thông lượng hoàn thành trung bình, W là thời gian trung bình ở trong hệ thống. Nếu dịch vụ hoàn thành 120 yêu cầu/giây, mỗi yêu cầu ở trong hệ thống trung bình 0,2 giây, ta có khoảng 24 yêu cầu đồng thời. Con số này giúp hiểu quy mô, nhưng **không tự động là giá trị giới hạn tối ưu**: phân phối thời gian xử lý, giới hạn DB, mức song song trong từng request và độ lệch tải giữa instance đều quan trọng.

Hàng đợi dài còn làm phát sinh **công việc đã hết giá trị**: client hủy yêu cầu hoặc hết deadline, nhưng server vẫn xử lý. Cần giới hạn độ dài hàng đợi, kiểm tra deadline trước khi bắt đầu công việc tốn kém và hủy xử lý khi an toàn.

Nguyên tắc: **xếp hàng chỉ có ích khi thời gian chờ dự kiến còn nằm trong ngân sách đáp ứng và tốc độ xử lý có khả năng bắt kịp**.

## 4. Rate limiting: kiểm soát nhịp yêu cầu và quyền dùng tài nguyên

### 4.1. Chọn phạm vi giới hạn

Một giới hạn có thể gắn với IP, người dùng, API key, tenant, endpoint, loại thao tác hoặc hệ thống phía sau. Chọn khóa theo mục tiêu thật sự:

- **IP:** giảm bùng nổ traffic chưa xác thực, nhưng nhiều người có thể dùng chung NAT; không được tin mù quáng header địa chỉ IP do client tự gửi.
- **User/API key:** hạn chế lạm dụng có danh tính, nhưng một người có thể có nhiều key.
- **Tenant:** bảo đảm khách hàng A không chiếm hết phần năng lực của khách hàng B.
- **Route hoặc thao tác:** yêu cầu ghi, xuất báo cáo và truy vấn nặng cần chính sách khác nhau.
- **Downstream shared resource:** tổng chi phí gọi DB hoặc dịch vụ ngoài có thể cần giới hạn chung ngay cả khi từng route chưa vượt quota.

Một request tra cứu cache và một request xuất báo cáo 30 giây có chi phí rất khác nhau. Với tài nguyên đắt, dùng **weighted rate limiting**: mỗi công việc tiêu thụ số token tương ứng với ước lượng chi phí, thay vì mặc định mọi request là một token.

### 4.2. Các thuật toán phổ biến

| Thuật toán | Ý tưởng | Ưu điểm | Giới hạn |
|---|---|---|---|
| Fixed window counter | Đếm yêu cầu theo cửa sổ thời gian cố định | Rẻ, dễ triển khai | Có thể cho phép hai đợt lớn sát ranh giới cửa sổ |
| Sliding window log | Lưu mốc thời gian từng yêu cầu gần đây | Chính xác trong cửa sổ trượt | Tốn bộ nhớ và thao tác với lưu lượng lớn |
| Sliding window counter | Xấp xỉ cửa sổ trượt bằng các bộ đếm | Cân bằng chi phí và độ mượt | Có sai số do nội suy |
| Token bucket | Token hồi phục theo tốc độ r; mỗi request lấy token | Cho phép burst ngắn có giới hạn | Cần chọn dung lượng burst phù hợp |
| Leaky bucket / bộ điều tiết nhịp | Đưa công việc ra với tốc độ tương đối đều | Bảo vệ tài nguyên không chịu được burst | Có thể tăng thời gian chờ nếu duy trì hàng đợi |

**Token bucket** thường phù hợp cho API có lưu lượng tăng đột biến ngắn hạn. Gọi r là số token nạp mỗi giây và B là dung lượng tối đa. Sau khoảng thời gian delta, lượng token được tính:

**tokens = min(B, tokens + r × delta)**

Yêu cầu có chi phí c được chấp nhận nếu tokens lớn hơn hoặc bằng c; khi chấp nhận, trừ c. Nếu không đủ token, từ chối và có thể ước tính thời gian chờ nạp bù. Một cấu hình **10 token/giây, bucket 20 token** cho phép burst tối đa 20 request một lần sau khi bucket đầy, rồi duy trì trung bình khoảng 10 request/giây về dài hạn nếu mỗi request tốn một token.

Mã giả cho một khóa hạn mức:

~~~text
allow(key, now, cost):
    state = load_atomically(key)
    elapsed = max(0, now - state.last_refill)
    available = min(capacity, state.tokens + elapsed * refill_rate)

    if available >= cost:
        save_atomically(key, tokens=available-cost, last_refill=now)
        return ALLOW

    save_atomically(key, tokens=available, last_refill=now)
    return DENY(retry_after=(cost-available)/refill_rate)
~~~

Trong nhiều instance, phần đọc–tính–ghi **phải nguyên tử** để hai instance không cùng tiêu một token. Nếu dùng Redis, có thể dùng thao tác/script nguyên tử và nguồn thời gian nhất quán. Cần quản lý TTL, hot key, sai lệch đồng hồ và lỗi kho lưu trạng thái. Khi kho limit bị lỗi, chọn chính sách **fail-open** hay **fail-closed** theo mức rủi ro: endpoint chi phí cao hoặc nhạy cảm thường cần cách ứng xử chặt hơn; có thể dùng giới hạn cục bộ khẩn cấp với chính sách suy giảm được công bố.

### 4.3. Local limit và global limit

Nếu mỗi instance tự cho 100 request/giây, cụm 5 instance có thể nhận tới khoảng 500 request/giây; autoscaling làm tổng hạn mức thay đổi. Muốn quota toàn cụm, cần một bộ đếm chung, phân bổ quota theo instance hoặc cơ chế đồng bộ có kiểm soát. Cần nêu rõ **mức nhất quán yêu cầu**: hệ thống ưu tiên quota chính xác, độ trễ thấp hay tính sẵn sàng khi bộ điều phối lỗi? Không có một lựa chọn đúng cho mọi API.

Rate limit ở gateway giúp giảm tải sớm, nhưng dịch vụ sâu bên trong vẫn có thể cần giới hạn riêng cho tài nguyên dùng chung hoặc các luồng nội bộ không đi qua gateway.

## 5. Admission control: chỉ nhận công việc khi còn ngân sách thực thi

Khác với rate limiting dựa trên khoảng thời gian, admission control nhìn vào **năng lực tại thời điểm tiếp nhận**. Cơ chế cơ bản là giới hạn số request đang xử lý đồng thời, gọi là **concurrency limit**.

Ví dụ, Order Service có 4 instance. Mỗi instance cho tối đa 8 request đồng thời dùng DB; tổng giới hạn danh nghĩa là 32. Đây mới là điểm khởi đầu: DB còn có thể phục vụ dịch vụ khác, workload không đồng nhất, và giới hạn kết nối DB không tương đương với giới hạn request. Phải đo năng lực qua thử tải và theo dõi độ trễ thực tế.

Một bộ điều phối tiếp nhận thường thực hiện:

1. Xác thực và kiểm tra yêu cầu bằng thao tác đủ rẻ; chặn traffic bất thường từ sớm.
2. Kiểm tra quota phù hợp với danh tính và loại yêu cầu.
3. Ước lượng hoặc gán chi phí công việc, kiểm tra deadline còn đủ.
4. Xin một **permit/slot** cho tài nguyên tắc nghẽn; nếu không có, chỉ chờ trong hàng đợi **có giới hạn** khi còn đủ thời gian.
5. Thực thi, áp dụng timeout cho downstream và **trả permit ở mọi đường kết thúc**: thành công, lỗi, hủy hoặc timeout.

Ví dụ tối giản trong ứng dụng Spring MVC đồng bộ:

~~~java
@RestController
@RequestMapping("/reports")
final class ReportController {
    private final Semaphore permits = new Semaphore(32);
    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    ResponseEntity<?> get(@PathVariable String id) {
        if (!permits.tryAcquire()) {
            return ResponseEntity.status(503)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .body(Map.of("code", "OVERLOADED"));
        }

        try {
            return ResponseEntity.ok(reportService.find(id));
        } finally {
            permits.release();
        }
    }
}
~~~

Ví dụ cho thấy việc từ chối **trước khi thực hiện thao tác đắt**, và giải phóng permit trong finally. Nó chỉ giới hạn **trong một JVM** và dành cho xử lý đồng bộ. Với WebFlux, CompletableFuture hoặc xử lý bất đồng bộ, phải giữ permit cho đến khi công việc thực sự kết thúc/hủy, không giải phóng ngay khi trả về publisher/future. Trong thực tế, filter, middleware hoặc thư viện giới hạn đồng thời thường phù hợp hơn việc lặp lại logic ở từng controller.

### 5.1. Giới hạn tĩnh và giới hạn thích ứng

- **Tĩnh:** đặt số slot từ phép đo thông lượng, p95/p99, CPU, DB pool và ngân sách bộ nhớ. Dễ dự đoán, dễ vận hành, nhưng không phản ứng tốt với downstream bị chậm bất thường.
- **Thích ứng:** tăng slot khi hệ thống ổn định và giảm khi độ trễ, thời gian chờ hoặc lỗi vượt ngưỡng. Họ thuật toán kiểu additive increase/multiplicative decrease (AIMD) là một lựa chọn; phải tránh dao động do tín hiệu nhiễu.
- **Theo lớp công việc:** phân slot riêng cho request tương tác, request batch, thao tác ghi quan trọng. Có thể cho mượn năng lực nhàn rỗi nhưng phải giữ mức dự phòng cho nhóm ưu tiên.

Giới hạn đồng thời bảo vệ số công việc **đang chạy**, trong khi rate limiting bảo vệ tốc độ **được gửi đến**. Dịch vụ cần cả hai nếu những request dài và ngắn tạo ra kiểu quá tải khác nhau.

## 6. Load shedding: loại bớt tải để giữ phần quan trọng sống được

Load shedding được kích hoạt khi các tín hiệu cho thấy hệ thống đang hoặc sắp vượt ngưỡng chịu tải, kể cả lúc một request chưa vượt quota cá nhân. Thay vì để toàn bộ request chậm và timeout, hệ thống từ chối sớm một số công việc theo chính sách.

### 6.1. Tín hiệu để bắt đầu shed

- Số request đang xử lý và thời gian đợi permit chạm ngưỡng.
- Độ sâu hoặc **độ tuổi** công việc trong hàng đợi vượt ngân sách.
- Connection pool, worker pool, memory hoặc CPU sát ngưỡng; chọn tín hiệu thực sự liên quan đến tài nguyên nghẽn.
- Độ trễ downstream và tỷ lệ timeout tăng, cho thấy giữ thêm request sẽ làm áp lực nặng hơn.
- Dự báo deadline của request đã không đủ để hoàn tất, dù hàng đợi chưa quá dài.

Chỉ nhìn CPU là chưa đủ: một dịch vụ bị nghẽn I/O có thể đợi DB hàng giây dù CPU thấp. Cũng không nên chỉ dùng p99 làm tín hiệu duy nhất vì nó thường phản ánh vấn đề đã xảy ra. Kết hợp tín hiệu dẫn trước (queue, in-flight, pool usage) và tín hiệu kết quả (latency, errors).

### 6.2. Chọn công việc cần loại

**Ưu tiên theo giá trị nghiệp vụ.** Ví dụ:

| Mức | Công việc | Phản ứng khi quá tải |
|---|---|---|
| Cao | Xác nhận thanh toán, thao tác bắt buộc để hoàn tất đơn | Dành trước năng lực, fail-fast rõ ràng nếu thật sự không còn khả năng |
| Trung bình | Xem giỏ hàng, xem trạng thái đơn, tra cứu thông thường | Giới hạn đồng thời, trả cache/stale data nếu ngữ nghĩa cho phép |
| Thấp | Gợi ý sản phẩm, dựng dashboard tốn tài nguyên, đồng bộ không khẩn cấp | Tạm bỏ bước tùy chọn, trì hoãn hoặc trả phản hồi rút gọn |

Phân loại ưu tiên phải dựa trên **danh tính và quy tắc phía server**. Không chấp nhận trực tiếp header do client tự khai “critical” để bỏ qua hạn mức. Hạn mức dự phòng cho luồng quan trọng cũng không phải vô hạn.

Các chiến lược thường gặp:

- **Early rejection:** từ chối khi chưa cấp DB connection hoặc tạo công việc tốn kém.
- **Priority shedding:** loại nhóm ưu tiên thấp trước, dành năng lực cho yêu cầu cốt lõi.
- **Brownout / suy giảm chức năng:** bỏ phần tùy chọn như recommendation hoặc enrichment; giữ chức năng chính.
- **Deadline-aware shedding:** không chạy tác vụ mà ước lượng hoàn tất đã vượt deadline còn lại.
- **Cost-aware shedding:** ưu tiên việc ít tốn tài nguyên hơn khi phù hợp cam kết nghiệp vụ.
- **Probabilistic shedding:** giảm tỷ lệ chấp nhận dần khi bão hòa, nhưng cần cơ chế công bằng và tránh loại ngẫu nhiên công việc quan trọng.

**Không được âm thầm đánh rơi công việc đã cam kết.** Với thao tác ghi, thanh toán hoặc message đã ACK, phải giữ đúng hợp đồng xử lý: hoặc hoàn tất, hoặc có hàng đợi bền vững và cơ chế phục hồi, hoặc trả lỗi rõ trước khi xác nhận tiếp nhận. HTTP 202 chỉ nên dùng khi công việc **đã thực sự được chấp nhận theo hợp đồng bất đồng bộ**, chẳng hạn ghi bền vững vào queue.

## 7. Phối hợp trong chuỗi microservices

Một đường xử lý hợp lý tại service có thể là:

~~~text
Incoming request
    |
    +-- Giới hạn sớm traffic chưa xác thực / bất thường
    |
    +-- Xác thực, xác định tenant và loại công việc
    |
    +-- Rate limit theo quota và chi phí                 -> quá quota: 429
    |
    +-- Kiểm tra deadline + chính sách ưu tiên
    |
    +-- Load-shedding policy khi có dấu hiệu bão hòa    -> loại tải: 503
    |
    +-- Admission control: xin slot / queue có giới hạn -> không còn slot: 503
    |
    +-- Xử lý với timeout, ngân sách retry, circuit breaker
    |
    +-- Giải phóng tài nguyên và ghi metric
~~~

Thứ tự cụ thể có thể khác tùy dịch vụ: request chưa xác thực cần bảo vệ trước khi xử lý tốn kém; thao tác theo tenant phải phân loại đúng; policy load shedding có thể được tích hợp vào admission controller để dành slot theo ưu tiên. Điều quan trọng là **đặt quyết định sớm nhất có thể trước tài nguyên đang nghẽn**.

Ở mỗi tầng bảo vệ một nút cổ chai khác nhau:

- **Edge/Gateway:** giới hạn bùng nổ từ client, quota danh tính, bảo vệ route công khai.
- **Service:** giới hạn số công việc đang xử lý, ưu tiên endpoint, deadline, queue.
- **Downstream client:** giới hạn kết nối/đồng thời đến dịch vụ được gọi, timeout và circuit breaker.
- **Worker/queue consumer:** giới hạn prefetch, số job chạy đồng thời, tốc độ gọi DB hoặc API ngoài.

Không nên đặt một global limit duy nhất rồi cho rằng mọi tài nguyên phía sau đều an toàn. Ví dụ, cùng 100 RPS nhưng tỷ lệ truy vấn nặng tăng có thể làm DB bão hòa.

## 8. Giao thức từ chối rõ ràng với client

| Tình huống | Phản hồi HTTP thường phù hợp | Ý nghĩa |
|---|---|---|
| Vượt quota đã công bố của người dùng/tenant | **429 Too Many Requests** | Client gửi nhanh hơn ngân sách cho phép |
| Service thiếu năng lực tạm thời hoặc cố ý shed để chống quá tải | **503 Service Unavailable** | Dịch vụ chưa thể nhận thêm việc lúc này |
| Yêu cầu hợp lệ được đưa vào hàng đợi xử lý bền vững | **202 Accepted** | Đã nhận xử lý bất đồng bộ theo hợp đồng API |
| Từ chối vì xác thực hoặc phân quyền | **401/403** | Vấn đề danh tính/quyền, không được ngụy trang thành quá tải |

Có thể cung cấp header **Retry-After** khi xác định được khoảng chờ hợp lý; giá trị có thể là số giây hoặc ngày HTTP theo định dạng chuẩn. Với rate limiting, header mô tả hạn mức và thời gian đặt lại có thể giúp client điều chỉnh, nhưng phải nhất quán với hợp đồng API. Không hứa một thời điểm thử lại chính xác khi tải phụ thuộc nhiều yếu tố biến động.

Phản hồi nên có mã lỗi máy đọc được, chẳng hạn:

~~~json
{
  "code": "CAPACITY_EXCEEDED",
  "message": "Service is temporarily overloaded",
  "retryable": true
}
~~~

Client cần phân biệt **bị giới hạn theo quota** với **quá tải tạm thời** để quyết định backoff, hiển thị thông báo hoặc giảm tần suất gọi. Với công việc có tác dụng phụ, thử lại phải đi kèm **idempotency key** hoặc cơ chế chống thực thi trùng khi hợp đồng yêu cầu.

## 9. Tránh vòng xoáy retry và quá tải dây chuyền

Một request lỗi không đồng nghĩa nên thử lại ngay. Nếu 100 request/giây được thử thêm 2 lần khi có sự cố, downstream có thể phải thấy tới **300 lần gọi/giây** trong tình huống xấu. Nếu từng tầng microservice đều retry, lưu lượng còn khuếch đại hơn nữa.

Các quy tắc thiết kế:

1. **Timeout và deadline tổng thể:** request xuyên nhiều hop có ngân sách thời gian chung; mỗi hop tiêu một phần ngân sách. Đừng bắt đầu retry khi không còn đủ thời gian hoàn tất.
2. **Exponential backoff kèm jitter:** tránh đồng bộ hàng nghìn client cùng thử lại tại một thời điểm.
3. **Retry budget:** giới hạn số lần retry hoặc tỷ lệ retry so với request gốc; chỉ retry lỗi tạm thời được quy định.
4. **Tôn trọng Retry-After** khi được cung cấp và vẫn áp dụng giới hạn tối đa hợp lý.
5. **Circuit breaker:** khi downstream liên tục lỗi/chậm, ngắt tạm lời gọi để tránh chiếm tài nguyên vô ích. Circuit breaker khác admission control: nó phản ứng với sức khỏe phụ thuộc, không thay thế quota và giới hạn công việc.
6. **Idempotency cho thao tác có tác dụng phụ:** cùng yêu cầu thanh toán không được tạo nhiều giao dịch chỉ vì client timeout.
7. **Backpressure:** truyền áp lực ngược lên producer hoặc consumer thông qua giới hạn prefetch, credit, cửa sổ nhận và tín hiệu điều tiết thay vì tích lũy hàng đợi vô hạn.

Rate limiting ở tầng ngoài, admission control ở service và retry budget ở client phải cùng mục tiêu. Nếu service trả 503 nhưng client retry ngay lập tức, hiệu quả load shedding gần như bị triệt tiêu.

## 10. Thiết kế công bằng giữa tenant và nhóm ưu tiên

Bảo vệ hệ thống không đồng nghĩa bảo đảm mọi tenant có cùng tốc độ tuyệt đối. Cần xác định **chính sách phân chia năng lực**:

- **Quota tối thiểu được bảo vệ:** tenant nhỏ vẫn có cơ hội truy cập khi một tenant lớn tăng tải.
- **Weighted fairness:** chia slot/token theo gói dịch vụ hoặc mức ưu tiên đã thỏa thuận.
- **Borrowing:** tenant có thể dùng công suất đang rảnh, nhưng khi chủ sở hữu cần thì trả lại năng lực dự phòng.
- **Giới hạn theo từng tầng:** tenant quota không cho phép vượt giới hạn chung của DB; global overload có thể buộc mọi tenant chịu một phần giảm dịch vụ.
- **Không lộ danh tính bằng nhãn metric:** ghi theo nhóm/route/priority; tránh dùng user ID trực tiếp làm nhãn có cardinality quá lớn.

Tách **ngân sách nghiệp vụ** (quota ngày/tháng, chi phí hóa đơn) khỏi **giới hạn bảo vệ tức thời** (token/giây, concurrent requests). Một tenant còn rất nhiều quota tháng vẫn phải chịu từ chối tạm thời nếu DB đang quá tải.

## 11. Tình huống tính toán: tìm ngưỡng ban đầu

Một API truy vấn báo cáo có 4 instance. Sau thử tải trong điều kiện gần sản xuất, thông lượng bền vững đo được là 120 request/giây ở độ trễ trung bình 200 ms. Số request trung bình đang ở hệ thống ước tính theo định luật Little:

**L ≈ 120 × 0,2 = 24 request.**

Nếu phân phối đều, trung bình khoảng 6 request đang xử lý trên mỗi instance. Nhóm có thể **thử nghiệm** giới hạn 8 request đồng thời/instance, tương đương trần danh nghĩa 32, rồi xác nhận bằng thử tải. Đây không phải công thức tự động chọn limit: phải kiểm tra p99, DB connection pool, tỷ lệ cache miss, độ lệch điều phối và các request tốn chi phí khác nhau.

Giả sử lúc sự kiện ra mắt, có 250 request/giây tràn vào:

- Gateway áp dụng quota theo tenant để tránh một khách hàng độc chiếm.
- Mỗi instance chỉ nhận lượng công việc phù hợp với số permit; hàng đợi chờ có giới hạn ngắn.
- Nếu downstream chậm, admission controller giảm số slot nhận mới hoặc shed lớp báo cáo ít quan trọng.
- Request bị từ chối sớm nhận 503/429 phù hợp, với hướng dẫn retry nếu hợp lý; client backoff có jitter.
- Luồng thanh toán/đặt hàng, nếu có chung tài nguyên, được giữ mức dự phòng độc lập.

**Tiêu chí thành công** không phải là “tất cả 250 request/giây đều được phục vụ”, mà là **thông lượng được nhận vẫn ổn định, độ trễ của phần việc quan trọng nằm trong SLO và hệ thống phục hồi khi tải giảm**.

## 12. Quan sát và vận hành

Tách metric **yêu cầu đến**, **yêu cầu được chấp nhận** và **yêu cầu bị từ chối**; nếu chỉ xem RPS thành công, load shedding tốt có thể bị hiểu nhầm là traffic biến mất.

| Nhóm metric | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Traffic | offered_rps, admitted_rps, rejected_rps | Có bao nhiêu công việc muốn vào, nhận, bị loại? |
| Lý do từ chối | rejected_total theo quota, concurrency, queue, deadline, overload | Cơ chế nào đang chặn? |
| Bão hòa | in_flight, permit_wait, queue_depth, oldest_queue_age, pool_usage | Nút cổ chai nào sắp tới ngưỡng? |
| Kết quả | latency p50/p95/p99, timeout, error, completed_rps | Phần request được nhận có hoàn tất đúng hạn? |
| Phụ thuộc | downstream latency, open circuits, DB pool wait | Dịch vụ nào gây hiệu ứng dây chuyền? |
| Retry | original_requests, retry_attempts, retry_ratio | Client đang làm tăng tải bao nhiêu? |

Nên phân tách biểu đồ theo route, priority, service và nhóm tenant ở mức cardinality có kiểm soát. Dashboard cần nhìn thấy cả tỷ lệ từ chối **và** độ trễ của phần traffic được chấp nhận: chỉ giảm latency bằng cách từ chối gần hết traffic không chứng minh hệ thống đáp ứng mục tiêu.

Alert có thể dựa trên **SLO vi phạm kéo dài**, queue age, permit saturation, retry ratio, tỷ lệ shed vượt ngân sách, hoặc mức năng lực dự phòng giảm; tránh cảnh báo chỉ vì RPS cao nếu hệ thống vẫn khỏe.

### 12.1. Kiểm thử trước khi phát hành

- **Ramp test:** tăng tải dần để xác định điểm bắt đầu bão hòa và thông lượng bền vững.
- **Spike test:** bơm burst ngắn, kiểm tra token bucket, admission limit, queue và tốc độ phục hồi.
- **Soak test:** duy trì tải cao để phát hiện rò permit, memory, connection và tăng hàng đợi theo thời gian.
- **Downstream degradation:** chủ động làm chậm DB/API ngoài, xác nhận timeout, circuit breaker và shedding không lan truyền sự cố.
- **Mixed workload:** trộn request nhẹ/nặng, tenant nhỏ/lớn và mức ưu tiên khác nhau để kiểm tra fairness.
- **Retry storm simulation:** xác nhận client backoff, retry budget và phản hồi 429/503 không nhân tải quá mức.

Quan sát cả trường hợp client **hủy giữa chừng** và server **timeout** để kiểm chứng giải phóng permit và dừng công việc thừa.

### 12.2. Triển khai dần và điều chỉnh

Bắt đầu bằng việc đo offered load và năng lực hiện có. Có thể chạy chính sách ở chế độ **chỉ ghi metric** để ước lượng lượng request sẽ bị từ chối, sau đó canary với một phần traffic. Xác định ngưỡng, mức dự phòng, cách rollback, người sở hữu cấu hình và quy trình điều chỉnh khi thay đổi số instance hoặc tài nguyên downstream.

Cần quyết định rõ: nếu Redis quota lỗi, hệ thống ứng xử thế nào; nếu telemetry bị thiếu, limiter thích ứng giữ giá trị nào; khi scale-out, ngân sách toàn cụm có bị nhân lên ngoài ý muốn không; ai được phép nâng priority hoặc quota. Những chính sách này thuộc hợp đồng vận hành, không nên để đến lúc sự cố mới xác định.

## 13. Những sai lầm thường gặp

1. **Giới hạn mỗi instance nhưng tưởng là giới hạn toàn cụm:** autoscaling làm quota tăng ngoài ý muốn.
2. **Chỉ dùng rate limiting:** request kéo dài vẫn chiếm hết worker/DB connection dù RPS thấp.
3. **Hàng đợi không giới hạn:** thời gian chờ tăng vô tận, client timeout nhưng server vẫn giữ tải.
4. **Đặt limiter sau thao tác đắt:** đã dùng DB và CPU rồi mới trả 429/503, không bảo vệ được nút cổ chai.
5. **Retry ngay khi nhận 429/503:** tạo làn sóng tải lặp lại và giảm hiệu quả tự bảo vệ.
6. **Chỉ theo dõi CPU:** bỏ qua nghẽn I/O, connection pool, queue age và downstream saturation.
7. **Dùng limit cứng từ môi trường thử nghiệm mãi mãi:** đặc tính request, hạ tầng và phụ thuộc thay đổi, cần quan sát và hiệu chỉnh.
8. **Phân loại ưu tiên từ đầu vào không đáng tin:** một client tự nhận “priority cao” phá vỡ fairness.
9. **Thả permit quá sớm hoặc không thả khi hủy:** cơ chế giới hạn đồng thời trở nên sai, gây quá tải hoặc kẹt vĩnh viễn.
10. **Âm thầm bỏ job đã ACK:** phá hợp đồng xử lý và gây mất dữ liệu/đơn hàng.
11. **Đánh giá thành công chỉ qua latency của request còn sống:** phải tính tỷ lệ từ chối và SLO của từng nhóm nghiệp vụ.

## 14. Bài tập ứng dụng

**Tình huống A — nhiều tenant:** Hệ thống có quota 40 request/giây/tenant, nhưng tenant lớn mở 50 luồng xuất báo cáo kéo dài 20 giây. Vì sao chỉ dùng token bucket vẫn có thể làm cạn tài nguyên? Hãy đề xuất giới hạn đồng thời theo tenant, giới hạn tổng và số slot dự phòng.

**Tình huống B — phụ thuộc bị chậm:** Payment Service thường phản hồi 100 ms, nay tăng đến 3 giây. Vẽ diễn tiến số request in-flight khi Order Service vẫn nhận cùng RPS. Nêu vị trí đặt timeout, circuit breaker, admission control và phương án phản hồi cho client. Giải thích cách ngăn retry storm.

**Tình huống C — lựa chọn hy sinh:** Trong sự kiện mua hàng, chức năng recommendation và checkout cùng dùng DB. Hãy phân loại ưu tiên, đề xuất việc có thể bỏ tạm thời, định nghĩa metric theo dõi và chỉ ra điều kiện trả lại hoạt động bình thường.

**Tình huống D — kiểm thử sự ổn định:** Từ kết quả load test, hãy chọn ngưỡng khởi đầu cho max in-flight, max queue wait, quota tenant và shed trigger. Thử các mức tải vượt ngưỡng; kiểm chứng độ trễ request được nhận, tỷ lệ từ chối, fairness và thời gian phục hồi. Không chọn ngưỡng chỉ từ một phép đo CPU hoặc một giá trị RPS.

## 15. Ghi nhớ

- **Rate limiting** bảo vệ ngân sách/tốc độ sử dụng theo chủ thể hoặc thao tác.
- **Admission control** bảo vệ số công việc có thể thực thi **ngay lúc này**, thường bằng giới hạn đồng thời và hàng đợi hữu hạn.
- **Load shedding** chủ động từ chối hoặc suy giảm chức năng khi quá tải để bảo vệ công việc ưu tiên và tránh sụp đổ dây chuyền.
- **429** thường nói về quota; **503** thường nói về thiếu năng lực tạm thời; phản hồi phải rõ và retry phải có ngân sách.
- Một kiến trúc chịu lỗi phải đưa quyết định **trước nút cổ chai**, phối hợp deadline, backpressure, timeout, circuit breaker, idempotency và quan sát đúng traffic được nhận lẫn bị loại.

Một hệ thống bền vững không nhất thiết phục vụ mọi công việc khi quá tải. Nó cần biết **nhận đúng lượng việc, giữ đúng ưu tiên và từ chối đúng lúc**, để phần cam kết còn lại hoàn thành một cách đáng tin cậy.
