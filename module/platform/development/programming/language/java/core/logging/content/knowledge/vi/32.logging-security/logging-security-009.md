# Phát hiện log bất thường trong bảo mật logging Java

## 1. Phát hiện log bất thường là gì?

**Phát hiện log bất thường (log anomaly detection)** là việc phân tích những sự kiện đã được ghi nhận để tìm hành vi khác với quy tắc, chuỗi hoạt động hoặc mức nền (baseline) dự kiến. Trong bối cảnh **bảo mật logging**, mục tiêu là phát hiện kịp thời dấu hiệu truy cập trái phép, lạm dụng quyền, thay đổi cấu hình đáng ngờ, hành vi tự động hóa bất thường và cả tình trạng pipeline log bị can thiệp hoặc không còn hoạt động đúng.

Một dòng log ERROR đơn lẻ **không nhất thiết là tấn công**; ngược lại, một chuỗi log INFO hoàn toàn “hợp lệ” có thể cho thấy quá trình thử đăng nhập thất bại hàng loạt hoặc thay đổi quyền truy cập khác thường. Vì vậy, hệ thống phát hiện cần nhìn vào **ngữ nghĩa sự kiện, tần suất, tương quan nhiều nguồn và ngữ cảnh vận hành**, không chỉ tìm chữ `ERROR` hoặc một từ khóa bất kỳ.

Ví dụ các câu hỏi mà hệ thống muốn trả lời:

- Có bao nhiêu lần đăng nhập thất bại cho cùng tài khoản, nguồn IP hoặc nhóm tài khoản trong 5 phút gần nhất?
- Có một lần cấp quyền quản trị bất thường ngay sau khi một tài khoản đăng nhập từ thiết bị/vị trí chưa từng thấy không?
- Số lỗi xác thực, truy cập bị từ chối hoặc yêu cầu tới endpoint nhạy cảm có tăng mạnh so với bình thường không?
- Một service có đột ngột **ngừng gửi security log** dù traffic vẫn diễn ra không?
- Payload trong log có cấu trúc bất hợp lệ, xuất hiện ký tự điều khiển làm gãy ranh giới bản ghi hoặc nội dung do client cung cấp bị giả mạo thành dòng log mới không?

Mục tiêu không phải chứng minh chắc chắn có tấn công chỉ từ một điều kiện; **cảnh báo là tín hiệu cần điều tra**. Quy tắc cần định nghĩa nguồn dữ liệu, điều kiện kích hoạt, mức độ ưu tiên, khả năng giải thích và cách giảm false positive.

## 2. Những sự kiện bảo mật nên ghi từ ứng dụng Java

Muốn phát hiện bất thường, phải thu thập được **security events** có cấu trúc. Log thuần văn bản tùy ý như `"Login failed!"` rất khó thống kê chính xác vì thiếu principal, kết quả, lý do và request context.

| Nhóm sự kiện | Event name minh họa | Thuộc tính có ích để phát hiện |
| --- | --- | --- |
| Xác thực | `auth.login.failed`, `auth.login.succeeded` | Thời điểm, principal ID/pseudonym, source IP, client/device class, kết quả, reason code |
| Phân quyền | `authz.access.denied`, `authz.role.changed` | Actor, target resource, action, trước/sau thay đổi quyền, approval ID |
| Quản trị | `admin.config.changed`, `admin.account.disabled` | Actor, target, type of change, môi trường, correlation ID |
| Truy cập dữ liệu | `data.export.started`, `data.read.denied` | Resource category, lượng dữ liệu, operation, requester |
| Chính sách ứng dụng | `security.policy.violation`, `rate_limit.rejected` | Rule ID, action taken, resource và số lần tái diễn |
| Tình trạng logging | `logging.export.failed`, `logging.pipeline.heartbeat` | Service/instance, queue depth, drop count, exporter errors |

Các tên sự kiện trên là **quy ước minh họa**, không phải chuẩn có sẵn trong JDK hoặc một backend. Hãy thống nhất schema giữa các service. Cần log các hành động quan trọng **thành công và thất bại**: chỉ quan sát thất bại sẽ bỏ lỡ một thao tác cấp quyền đáng ngờ đã thành công.

Không đưa mật khẩu, access token, session cookie, khóa API, secret, thông tin thanh toán hay nội dung cá nhân không cần thiết vào log. Nếu cần tương quan theo tài khoản, ưu tiên ID nội bộ được kiểm soát quyền truy vấn hoặc pseudonym phù hợp chính sách; không phải lúc nào địa chỉ email/IP ở dạng thô cũng nên lưu vĩnh viễn.

### Trường tối thiểu của một sự kiện

Một schema có thể gồm:

```json
{
  "timestamp": "2026-01-01T00:00:30Z",
  "event_id": "evt-3",
  "event_name": "auth.login.failed",
  "severity": "WARN",
  "service.name": "identity-api",
  "deployment.environment.name": "prod",
  "result": "failure",
  "reason_code": "INVALID_CREDENTIALS",
  "actor_id": "user-42",
  "source_ip": "203.0.113.7",
  "request_id": "req-1003",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Authentication attempt rejected"
}
```

Đây là **JSON minh họa**, không phải định dạng API mà mọi SIEM/cloud tự hiểu. Dải IP `203.0.113.0/24` chỉ được dùng làm địa chỉ ví dụ trong tài liệu. Khi vận hành, cần chuẩn hóa trường, phân loại dữ liệu nhạy cảm, chính sách retention và ánh xạ sang schema của backend.

`event_id` là định danh của một **sự kiện logic**, phù hợp để dedup; `request_id` có thể bao phủ nhiều sự kiện của một request; `trace_id` liên kết các span trong hệ thống phân tán. Không dùng chung một ID cho mọi log của request nếu cần đếm chính xác từng event.

## 3. Bất thường có thể xuất hiện dưới những hình thức nào?

### A. Bất thường theo quy tắc (rule-based)

Một điều kiện bảo mật được mô tả rõ: ví dụ `≥ 5` lần đăng nhập thất bại từ cùng IP trong 60 giây, hoặc thay đổi vai trò quản trị bên ngoài quy trình phê duyệt. Ưu điểm: dễ giải thích, dễ kiểm thử, dễ điều chỉnh. Hạn chế: cần tuning và có thể bỏ sót kỹ thuật chưa có rule.

### B. Bất thường theo tần suất hoặc tỷ lệ

Đo tổng số event trong cửa sổ, tỷ lệ lỗi trên tổng lần thử, số tài khoản khác nhau bị nhắm tới, số endpoint khác nhau được truy cập, hoặc tốc độ dữ liệu được xuất. Cần **mẫu số đúng** để phân biệt “100 lần từ một IP có traffic rất lớn” với “100 lần từ một IP ít hoạt động”.

### C. Bất thường so với baseline

So sánh với phân bố trước đó theo service, endpoint, tenant hoặc thời điểm trong ngày. Ví dụ khối lượng login failure tăng đột ngột so với các ngày tương đồng. Cần xử lý yếu tố seasonality, release mới, campaign hợp pháp, quy mô traffic và môi trường staging/test để giảm false positive.

### D. Bất thường theo trình tự, ngữ cảnh

Một sự kiện đơn lẻ không lạ nhưng **chuỗi sự kiện** đáng chú ý: nhiều lần thất bại, sau đó một lần thành công, rồi đổi mật khẩu hoặc tăng quyền; hoặc thay đổi cấu hình audit ngay trước một hoạt động nhạy cảm. Cần state/correlation ID phù hợp và thời hạn giữ trạng thái.

### E. Bất thường của chính hệ thống logging

Mất heartbeat, drop count tăng, log rate rơi về 0 khi request count vẫn cao, parser error đột biến, timestamp sai lệch hoặc nhiều event cùng event ID có thể báo hiệu lỗi vận hành hoặc dấu hiệu can thiệp. Không mặc định mọi khoảng trống log là hành động cố ý; kiểm chứng với metrics và audit sources độc lập.

| Loại tín hiệu | Ví dụ quy tắc | Điều dễ gây báo giả |
| --- | --- | --- |
| Failure burst | Nhiều đăng nhập thất bại từ IP/actor trong 1 phút | NAT chung, người dùng quên mật khẩu, sự kiện retry hợp lệ |
| Account spraying | Một nguồn thử nhiều tài khoản khác nhau | Proxy chung hoặc kiểm thử được ủy quyền |
| Privilege escalation | Role được nâng bất thường | Thay đổi quyền có phê duyệt |
| Sensitive access spike | Lượng export hoặc denied access tăng | Công việc batch, release, thay đổi traffic |
| Unexpected geo/device | Đăng nhập từ thiết bị hoặc vị trí khác biệt | VPN, travel, geolocation sai |
| Logging silence | Event bảo mật ngừng xuất hiện nhưng hệ thống còn xử lý request | Thay đổi traffic hợp lệ, filter/sampling, pipeline lỗi |

## 4. Kiến trúc phát hiện bất thường end-to-end

```text
Java service (SLF4J / JUL / Logback / Log4j2)
  -> security event có schema thống nhất
  -> stdout JSON / OTLP / appender
  -> agent / Collector / message broker
  -> parse + validate + enrich + redact + dedup
  -> stream processing / SIEM / search analytics
  -> rule / baseline / correlation / ML (nếu thích hợp)
  -> alert + suppression + triage
  -> investigation + response + audit
```

Điểm quan trọng:

1. **Nguồn dữ liệu đáng tin:** ứng dụng phải tạo event từ kết quả nghiệp vụ/xác thực thật, không đọc nguyên dòng do client gửi rồi giả định đó là sự kiện bảo mật đã xác minh.
2. **Định dạng chuẩn:** nếu một service ghi `auth_failure` còn service khác ghi `loginFailed`, rule tổng hợp phải chuẩn hóa chúng trước.
3. **Ranh giới tin cậy:** giá trị người dùng cung cấp như username, URI, user agent và request headers có thể không đáng tin. Không cho chúng tùy ý đặt `severity`, `event_name`, `role`, `source_service` hoặc cảnh báo mà không xác thực.
4. **Xử lý dữ liệu:** có thể cần loại trùng do retry, kiểm schema, bổ sung metadata deployment và loại secret trước khi index.
5. **Động cơ phát hiện:** chạy rule theo cửa sổ, so baseline hoặc tìm tương quan nhiều service.
6. **Cảnh báo có ích:** cần bằng chứng gồm thời gian, rule ID/version, các khóa liên quan, tập event ID, mức độ tin cậy và link điều tra, không chỉ thông điệp “Anomaly detected”.

Có thể triển khai bằng SIEM hoặc stream processing, không nhất thiết viết bộ phát hiện trong mỗi Java service. Ứng dụng Java nên **phát security event chính xác**, còn rule tập trung thường dễ quản lý và so sánh trên nhiều instance hơn. Với một service nhỏ, phát hiện cục bộ vẫn có giá trị nhưng phải biết nó không nhìn thấy hoạt động phân tán trên các node khác.

## 5. Thiết kế quy tắc theo cửa sổ thời gian

Một rule cơ bản: phát cảnh báo khi **có ít nhất N lần đăng nhập thất bại từ cùng nguồn IP trong cửa sổ T giây**.

Định nghĩa:

```text
key = (environment, service, source_ip)
window = [event_time - 60 giây, event_time]
count = số event_id duy nhất có event_name = auth.login.failed
alert khi count lần đầu đạt ngưỡng N trong cửa sổ
```

Những điểm cần quyết định:

- **Event time hay processing time?** Event time là lúc sự kiện xảy ra; processing time là lúc detector nhận dữ liệu. Nếu log đến muộn hoặc lệch thứ tự, detector theo processing time có thể không nhận ra burst thực sự; detector theo event time cần xử lý watermark và chính sách late events.
- **Cửa sổ trượt hay cố định?** Cửa sổ cố định 00:00–00:59 và 01:00–01:59 có thể chia một burst qua ranh giới; sliding window nhìn tốt hơn nhưng tốn state/CPU hơn.
- **Khóa nhóm:** cùng IP có thể đại diện hàng nghìn người dùng sau NAT, còn kẻ tấn công có thể phân tán trên nhiều IP. Nên bổ sung rule theo actor, subnet, device, tenant hoặc distinct account tùy tình huống.
- **Đếm duy nhất:** collector/exporter retry có thể tạo duplicate record. Cần event ID đủ ổn định để không đếm một lần thử thành nhiều lần thử.
- **Giới hạn state:** hàng triệu IP/tài khoản có thể gây tăng RAM. Cần TTL, giới hạn số key và giải pháp phân tán khi quy mô lớn.
- **Cooldown/suppression:** một burst dài không nên tạo hàng nghìn cảnh báo gần giống nhau; cần gộp cảnh báo hoặc mở incident duy nhất theo key trong khoảng thời gian hợp lý.
- **Ngưỡng:** N=3 hay N=10 không tự động có ý nghĩa bảo mật. Chọn từ dữ liệu thực, risk tolerance, false-positive cost và tốc độ phản ứng cần thiết.

## 6. Ví dụ Java 17 chạy độc lập: phát hiện burst và loại trùng event

Ví dụ sau chỉ dùng JDK 17. Nó nhận một danh sách sự kiện **đã được sắp theo thời gian tăng dần**, giữ timestamp của login failure cho từng IP trong cửa sổ trượt 60 giây, dedup theo `event_id` và in cảnh báo đúng một lần khi số failure trong cửa sổ **lần đầu đạt 3**.

Ví dụ sử dụng IP thuộc dải dành cho tài liệu. Ngưỡng 3 chỉ để minh họa thuật toán, **không phải giá trị khuyến nghị để triển khai production**.

Lưu trong tệp **`SecurityLogAnomalyDemo.java`**:

```java
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class SecurityLogAnomalyDemo {
    record SecurityEvent(
            String eventId,
            Instant occurredAt,
            String eventName,
            String sourceIp) {}

    static final class Detector {
        private final Map<String, Deque<Instant>> failures =
                new HashMap<>();
        private final Set<String> seenEventIds = new HashSet<>();

        private int accepted;
        private int duplicates;
        private int alerts;

        void accept(SecurityEvent event) {
            if (!seenEventIds.add(event.eventId())) {
                duplicates++;
                return;
            }
            accepted++;

            if (!"LOGIN_FAILED".equals(event.eventName())) {
                return;
            }

            Deque<Instant> times = failures.computeIfAbsent(
                    event.sourceIp(), ignored -> new ArrayDeque<>());

            Instant cutoff = event.occurredAt().minusSeconds(60);
            while (!times.isEmpty()
                    && times.peekFirst().isBefore(cutoff)) {
                times.removeFirst();
            }
            times.addLast(event.occurredAt());

            if (times.size() == 3) {
                alerts++;
                System.out.printf(
                        "ALERT type=LOGIN_FAILURE_BURST ip=%s count_60s=%d at=%s%n",
                        event.sourceIp(), times.size(), event.occurredAt());
            }
        }

        void printSummary() {
            System.out.printf(
                    "RESULT unique_events=%d duplicates=%d alerts=%d%n",
                    accepted, duplicates, alerts);
        }
    }

    public static void main(String[] args) {
        String sourceA = "203.0.113.7";
        String sourceB = "198.51.100.9";

        List<SecurityEvent> input = List.of(
                new SecurityEvent("e1", Instant.parse(
                        "2026-01-01T00:00:00Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e2", Instant.parse(
                        "2026-01-01T00:00:10Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e3", Instant.parse(
                        "2026-01-01T00:00:30Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e4", Instant.parse(
                        "2026-01-01T00:00:40Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e4", Instant.parse(
                        "2026-01-01T00:00:40Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e5", Instant.parse(
                        "2026-01-01T00:00:50Z"), "LOGIN_SUCCESS", sourceA),
                new SecurityEvent("e6", Instant.parse(
                        "2026-01-01T00:02:00Z"), "LOGIN_FAILED", sourceA),
                new SecurityEvent("e7", Instant.parse(
                        "2026-01-01T00:02:10Z"), "LOGIN_FAILED", sourceB));

        Detector detector = new Detector();
        for (SecurityEvent event : input) {
            detector.accept(event);
        }
        detector.printSummary();
    }
}
```

Biên dịch và chạy:

```bash
javac SecurityLogAnomalyDemo.java
java SecurityLogAnomalyDemo
```

Stdout chính xác:

```text
ALERT type=LOGIN_FAILURE_BURST ip=203.0.113.7 count_60s=3 at=2026-01-01T00:00:30Z
RESULT unique_events=7 duplicates=1 alerts=1
```

Giải thích:

1. `e1`, `e2` và `e3` cùng nguồn IP trong 30 giây, nên ở `e3` số failure đạt 3 và phát **một** cảnh báo.
2. `e4` làm số failure trong cửa sổ lên 4 nhưng không tạo cảnh báo lặp, vì chương trình chỉ báo khi số lượng bằng 3.
3. `e4` xuất hiện lần thứ hai với cùng `eventId`, được coi là event trùng từ pipeline; nó tăng `duplicates` mà không làm sai count.
4. `e5` là login success, vẫn là một event duy nhất được chấp nhận nhưng **không** được đếm như login failure.
5. `e6` xảy ra sau hai phút, những failure cũ đã nằm ngoài cửa sổ 60 giây và được loại khỏi deque; `e7` đến từ IP khác. Không có burst thứ hai.
6. Tổng đầu vào 8 bản ghi, có 7 ID duy nhất, 1 duplicate và 1 cảnh báo.

**Giới hạn của demo:** thuật toán dùng một process, nhận event **theo đúng thứ tự thời gian**; `HashMap` và `HashSet` không an toàn nếu gọi đồng thời từ nhiều thread. `seenEventIds` và các key im lặng có thể tăng RAM vô hạn nếu không có TTL/eviction. Một pipeline thật phải xử lý sự kiện đến trễ/out-of-order, per-key partition, clock skew, checkpoint/restart và xác thực nguồn dữ liệu. Không được tin một `event_id` tùy tiện do client gửi vì có thể gây va chạm hoặc che giấu event; ID cần do thành phần đáng tin tạo và kiểm soát phạm vi.

Đối với hệ thống nhiều instance, việc tính riêng một bản đồ failure mỗi process dễ bỏ sót burst trải trên nhiều node. Cần tập trung event vào SIEM/stream processor hoặc dùng state phân tán, với dedup/cửa sổ theo hợp đồng đã chọn.

## 7. Phát hiện bất thường từ nhiều chiều và nhiều service

Một rule đơn chiều như `count(login_failed by source_ip)` có ích nhưng có thể bỏ sót hoạt động phân tán. Tùy mô hình rủi ro, hãy kết hợp:

- **Theo principal:** số failure trên cùng actor/tài khoản, số thiết bị nguồn mới, lần login success sau chuỗi failure.
- **Theo nguồn:** số tài khoản khác nhau bị thử từ cùng IP, tốc độ request tới các endpoint đăng nhập/reset token/quản trị.
- **Theo tài nguyên:** nhiều lần `access.denied` trên các resource khác nhau, export vượt mức thường ngày hoặc quyền truy cập đột ngột thay đổi.
- **Theo chuỗi nghiệp vụ:** login → đổi mật khẩu → phát token → tăng quyền trong khoảng thời gian bất thường, cần xem actor và session liên quan.
- **Theo ngữ cảnh:** môi trường production khác staging; bot/crawler được phép khác người dùng; ca bảo trì có phê duyệt khác sự kiện không mong đợi.
- **Theo hạ tầng:** cùng actor xuất hiện ở nhiều region/service, thời gian nguồn lệch hoặc thiếu heartbeat trong khi metric request vẫn bình thường.

Correlation theo `trace_id`, `request_id` và `actor_id` rất hữu ích nhưng không phải luôn có cùng ngữ nghĩa. Một trace có thể chứa nhiều event; một actor có thể hoạt động trong nhiều request. Cần tách rõ khóa dùng để **nối log** và khóa dùng để **đếm event duy nhất**.

### Rule-based so với baseline/anomaly scoring

| Cách làm | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Rule ngưỡng cố định | Dễ giải thích, kiểm thử, audit | Khó chọn ngưỡng chung, dễ bỏ sót hoạt động phân tán |
| Threshold theo baseline | Thích nghi với lưu lượng theo service/tenant/giờ | Baseline bị méo do release hoặc dữ liệu bất thường kéo dài |
| Phát hiện trình tự | Tìm chuỗi hành động đáng ngờ | Cần state, thứ tự và phân biệt late events |
| Phát hiện bất thường thống kê | Phát hiện thay đổi chưa có rule cụ thể | False positive, cần dữ liệu sạch và giải thích |
| ML hoặc scoring | Kết hợp nhiều tín hiệu đa chiều | Cần giám sát drift, bias, kiểm soát truy cập và đánh giá thực tế |

Một điểm bất thường thống kê **không tự động là bằng chứng tấn công**. Đặc biệt các quy tắc “đăng nhập từ vị trí không thể xảy ra” có thể sai vì VPN, carrier NAT, IP geolocation không chính xác hoặc proxy. Nên kết hợp với event xác thực và lịch sử hành động trước khi đưa ra biện pháp mạnh như khóa tài khoản.

## 8. Đối mặt với log injection, giả mạo và can thiệp log

Hệ thống phát hiện phải bảo vệ **chính log pipeline**. Nếu ứng dụng ghép trực tiếp dữ liệu do client gửi vào text log, newline hoặc ký tự điều khiển có thể làm kết quả giống nhiều dòng log và gây sai parser/correlation. Kẻ tấn công cũng có thể cố tạo trường dữ liệu giống severity/event type hoặc cố gây bão log làm hệ thống không xử lý hết.

Các nguyên tắc:

1. **Không tin vào payload:** actor, role, source identity, action result và security event type phải lấy từ logic xác thực/phân quyền của server, không nhận từ client mà không đối chiếu.
2. **Structured logging:** dùng JSON encoder đã được kiểm chứng; escape newline, CR, dấu nháy, backslash và các control characters để một event không biến thành nhiều event.
3. **Schema validation:** kiểm loại và độ dài trường, giới hạn kích thước event, bỏ/chuẩn hóa trường không hợp lệ theo chính sách; ghi metric reject thay vì silently mất hết dữ liệu.
4. **Kênh truyền an toàn:** giới hạn quyền ghi và đọc, TLS khi đi qua mạng không tin cậy, xác thực nguồn Collector và service identity; phát hiện thay đổi config bất thường.
5. **Tính toàn vẹn audit:** với log bắt buộc, dùng storage và quy trình có chống sửa trái phép, retention/backup và nhật ký truy cập phù hợp; một file log thông thường không mặc định tamper-proof.
6. **Phát hiện mất tín hiệu:** dùng heartbeat, producer counters và collector/export metrics độc lập; nếu log rate bằng không nhưng request count vẫn cao, đó có thể là lỗi pipeline hoặc dấu hiệu tấn công vào quan sát hệ thống.
7. **Bảo vệ chi phí:** giới hạn log volume và cardinality, rate-limit các sự kiện nhiễu khi an toàn; bảo đảm vẫn giữ được security events bắt buộc theo policy.

Không log nguyên access token, mật khẩu, cookies, PII hoặc request body đầy đủ chỉ để xây detector. Redaction tại Collector giúp phòng vệ thêm, nhưng dữ liệu đã có thể bị ghi vào stdout hoặc queue trước khi đến Collector. Nguyên tắc ưu tiên là **không tạo log chứa dữ liệu nhạy cảm từ đầu**.

## 9. Thu thập bằng Java logging stack

Trong Java, ứng dụng có thể dùng JUL hoặc SLF4J với backend như Logback/Log4j2. Security event nên được phát bằng API logging chuẩn cùng **tập field ổn định**, để pipeline phân tích không phải parse tự do từ message.

Đoạn minh họa SLF4J, không phải chương trình chạy độc lập (cần logger, request context và business logic):

```java
logger.warn(
        "event_name=auth.login.failed reason_code={} actor_id={} request_id={}",
        reasonCode, actorId, requestId);
```

Đây là text pattern, không phải structured JSON thực thụ. Với ứng dụng có JSON encoder, nên map các field thành những thuộc tính có cấu trúc mà backend query được. Lưu ý các giá trị `actorId`, `reasonCode` cũng cần validation và privacy policy.

Đối với request/trace context, MDC có thể giúp bổ sung `request_id` hoặc `trace_id` vào log event. Tuy nhiên MDC có ngữ nghĩa theo thread trong nhiều stack, không tự động đi theo task được gửi tới `ExecutorService` hoặc reactive pipeline. Cần context propagation theo framework và khôi phục/xóa MDC sau tác vụ để log của request khác không mang ID cũ.

Nếu dùng OpenTelemetry, `trace_id` và `span_id` có thể được liên kết qua instrumentation/appender phù hợp. **Chỉ có Java agent hoặc biến môi trường OTEL không bảo đảm mọi logging event tự xuất qua OTLP**; kiểm tra backend, bridge và cấu hình cụ thể. Bảo mật của đường log cần xem cả token/credentials, IAM, endpoint và quyền truy vấn ở nơi lưu trữ.

### Tách detection khỏi enforcement

Một detector thấy bất thường có thể phát alert tới hệ thống ứng cứu, nhưng không nên mặc định đóng tài khoản hoặc chặn IP chỉ dựa vào một rule có false-positive cao. Biện pháp chủ động như chặn truy cập, yêu cầu MFA, giới hạn tốc độ hoặc khóa tài khoản cần chính sách riêng, thời hạn, quyền phê duyệt, khả năng rollback và đo tác động tới người dùng hợp lệ.

## 10. Kiểm soát false positive, false negative và alert fatigue

Hai loại lỗi quan trọng:

- **False positive (FP):** cảnh báo phát ra nhưng hành vi là hợp pháp, ví dụ một văn phòng nhiều nhân viên dùng chung public IP hoặc một integration liên tục retry trong thời gian maintenance.
- **False negative (FN):** bất thường thực sự xảy ra nhưng detector không báo, ví dụ thử xác thực rải trên nhiều IP, logging bị tắt hoặc dữ liệu đến trễ ngoài cửa sổ.

Có thể dùng precision/recall khi có bộ dữ liệu gán nhãn đáng tin:

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
```

Khi mẫu số bằng 0, không tự tính tỷ lệ từ công thức trên mà cần quy ước báo cáo thích hợp. Với an ninh, việc thu thập “ground truth” khó; nhiều alert chưa được kết luận không nên tự coi là true positive. Đừng dùng **accuracy** đơn lẻ cho dữ liệu có tỷ lệ tấn công rất nhỏ.

Điều chỉnh rule dựa trên:

1. **Tín hiệu và mức rủi ro:** phân biệt hành vi xác thực thất bại thông thường với thay đổi quyền quản trị nhạy cảm.
2. **Rate và mẫu số:** số failure theo số attempt, số tài khoản, số endpoint và tổng traffic.
3. **Phân nhóm hợp lý:** tenant, service, môi trường, loại ứng dụng và giờ cao điểm.
4. **Suppression/cooldown:** gộp alert cùng key thành incident hoặc cập nhật alert hiện có, không phát một alert mới cho mỗi event trong một burst.
5. **Danh sách ngoại lệ có kiểm soát:** kiểm thử được ủy quyền và job hợp lệ có thể cần tuning, nhưng exception phải có chủ sở hữu, thời hạn và log thay đổi.
6. **Đánh giá lại theo thời gian:** theo dõi precision, recall khi có ground truth, số alert chưa xử lý, time-to-detect và time-to-triage; cập nhật rule khi traffic hoặc threat model thay đổi.

Một alert “đáng ngờ” tốt nêu rõ **rule ID, điều kiện, số event, khoảng thời gian, các khóa đã chuẩn hóa và bằng chứng truy vấn được**, thay vì chỉ dùng thuật ngữ tổng quát.

## 11. Vấn đề time, duplicate, sampling và dữ liệu bị thiếu

Trong môi trường có nhiều service và collector, log có thể đến **không theo đúng thứ tự phát sinh** vì batching, queue, retry, network và clock skew. Detector cần chính sách rõ:

- **Event time:** dùng thời điểm tạo event và watermark/allowed lateness khi tính cửa sổ. Với dữ liệu đến muộn, quyết định có cập nhật alert trước đó hay không.
- **Processing time:** đơn giản hơn nhưng một burst thực sự có thể bị dàn trải khi ingest bị trễ; điều đó ảnh hưởng kết quả rule.
- **Clock skew:** không dùng timestamp từ nguồn không đáng tin mà không kiểm; giám sát lệch đồng hồ, đồng bộ thời gian các máy và tránh giả định hai service có thứ tự tuyệt đối từ timestamp.
- **Retry/duplicate:** đếm theo event ID đáng tin. Một lần gửi lại sau ACK mất không nên bị tính là một lần đăng nhập thất bại mới.
- **Sampling/filtering:** không áp mẫu số raw attempts lên log đã bị sampling mà không có cơ chế bù phù hợp. Security events bắt buộc có thể cần kênh riêng không sampling.
- **Data loss:** nếu queue overflow làm mất sự kiện, detector bị blind spot. Kiểm dropped count, exporter errors và end-to-end query probes.

Không có khả năng phát hiện tuyệt đối khi nguồn log thiếu. Để biết pipeline đang “mù”, cần **metrics độc lập**: số lần xác thực từ hệ thống nghiệp vụ, số security events phát ra, số event Collector nhận, ingest success, parse errors và số event được query. Sự không khớp giữa các tầng là dấu hiệu cần điều tra.

Một sự kiện `LOGIN_SUCCESS` không mặc định xóa lịch sử failure của cùng IP, vì điều đó có thể che một burst vừa xảy ra. Chính sách reset hay giảm điểm phải dựa vào loại rule, session/actor và threat model, không dùng một quy tắc chung cho mọi hệ thống.

## 12. Quy trình kiểm thử và vận hành detector

Một rule cần được test như một thành phần nghiệp vụ quan trọng:

| Kịch bản kiểm thử | Kỳ vọng |
| --- | --- |
| 2 failure trong cửa sổ, ngưỡng 3 | Không alert |
| Failure thứ 3 trong 60 giây | Một alert với key, khoảng thời gian và số đếm đúng |
| Failure thứ 4 cùng burst | Không phát thêm alert giống hệt nếu policy chỉ cảnh báo khi vượt ngưỡng |
| Gửi trùng event ID | Không tăng số failure logic; duplicate metric tăng |
| Event thứ 3 ở ngoài cửa sổ | Không alert nếu không có đủ sự kiện hợp lệ trong cửa sổ |
| Có `LOGIN_SUCCESS` xen kẽ | Không tự coi là failure; điều chỉnh rule theo yêu cầu riêng |
| Nguồn IP khác | Không nhập chung state khi rule đang nhóm theo IP |
| Event đến muộn | Thực hiện đúng chính sách late event/watermark |
| Nhiều instance và restart | State, checkpoint/dedup khôi phục theo hợp đồng |
| Queue/Collector mất log | Detector có blind-spot alert hoặc discrepancy metric |
| Payload chèn newline/ký tự điều khiển | Parser không nhầm thành event security mới |
| Traffic hợp lệ tăng mạnh | Baseline/threshold không bùng nổ FP ngoài mức chấp nhận |
| Role thay đổi có phê duyệt | Có bằng chứng approval, không cảnh báo như hành vi trái phép |

Với Java, unit test có thể thử detector bằng clock cố định và danh sách event nhân tạo; integration test cần chạy cùng encoder, Collector/SIEM và pipeline query thật. Stress test phải xét nhiều event, nhiều key, concurrency và giới hạn bộ nhớ. Test không nên phụ thuộc `Thread.sleep` cố định để giả định async ingestion đã xong; cần điều kiện chờ và timeout hữu hạn.

### Khi alert phát ra

1. **Triage:** kiểm alert rule ID, severity, thời gian, source/actor, scope và các event liên quan.
2. **Xác thực bằng nguồn thứ hai:** đối chiếu security events với auth service, metric traffic, thay đổi quyền thực tế, audit trail hoặc hệ thống phê duyệt.
3. **Đánh giá ảnh hưởng:** có đăng nhập thành công, đổi quyền, export hay truy cập dữ liệu nhạy cảm không; service/tenant nào bị tác động?
4. **Ứng phó theo chính sách:** có thể yêu cầu thêm xác minh, rate limiting, khóa tạm hoặc tạo incident, tùy mức tin cậy và quyền vận hành.
5. **Lưu bằng chứng:** giữ event ID, query, timeline, rule version và quyết định; phân quyền truy cập theo dữ liệu nhạy cảm.
6. **Tuning sau điều tra:** cập nhật ngưỡng, bổ sung correlation hoặc sửa schema/collection, không chỉ tắt rule vì nhiều alert.

Không để alert tự phát vô hạn gây “alert fatigue”. Gộp sự kiện theo incident key, có mức ưu tiên và kênh cảnh báo riêng cho mất pipeline logging.

## 13. Checklist triển khai thực tế

- [ ] Đã xác định rõ threat model: đăng nhập thất bại, thay đổi quyền, truy cập bị từ chối, xuất dữ liệu, can thiệp logging?
- [ ] Event bảo mật có schema, `event_id`, timestamp, `event_name`, kết quả, service/environment và correlation ID phù hợp?
- [ ] Trường do client cung cấp được kiểm soát, escape, giới hạn kích thước và không được dùng làm bằng chứng đã xác thực?
- [ ] Không log secret/PII quá mức; có quyền truy cập, encryption, retention và audit đọc log phù hợp?
- [ ] Detector có khóa nhóm, ngưỡng, cửa sổ, rule ID/version, chính sách late event và dedup minh bạch?
- [ ] Có giới hạn state, TTL, backpressure và kiểm thử restart/concurrency?
- [ ] Đã đánh giá false positive, false negative, baseline theo traffic và suppression?
- [ ] Log bắt buộc có kênh thu thập đủ tin cậy, không bị sampling tùy tiện?
- [ ] Pipeline có heartbeat, metrics độc lập, dropped count và canary để phát hiện khi mất log?
- [ ] Alert có bằng chứng, hướng dẫn triage, cơ chế phản ứng có kiểm soát và owner rõ ràng?

**Ghi nhớ:** phát hiện log bất thường trong Java không đơn thuần là tìm `ERROR` hoặc đếm chuỗi văn bản. Nó cần **security events đáng tin cậy**, **cửa sổ và correlation đúng**, **kiểm soát chất lượng dữ liệu và false positives**, cùng một **pipeline logging được giám sát**. Khi kết hợp rule dễ giải thích với baseline và quy trình điều tra hợp lý, log trở thành nguồn tín hiệu bảo mật hữu ích mà không phải tự động kết luận mọi khác biệt là một cuộc tấn công.
