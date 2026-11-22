# Quy định hành vi khi chức năng cắt ngang không khả dụng trong AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **aspect** bổ sung những chính sách cắt ngang như đo thời gian, tracing, ghi log, kiểm toán, kiểm tra quyền, giao dịch, cache hoặc retry vào các **join point** được **pointcut** lựa chọn. Những chức năng này không phải lúc nào cũng sẵn sàng: máy chủ ghi log có thể chậm, bộ thu metrics ngừng nhận dữ liệu, bộ kiểm tra quyền có thể không phản hồi, nơi lưu audit có thể đầy, hoặc một interceptor không khởi tạo được.

Câu hỏi quan trọng không phải chỉ là “bắt ngoại lệ nào?”, mà là: **khi chức năng cắt ngang không khả dụng, nghiệp vụ có được tiếp tục không, tiếp tục trong điều kiện nào, và người gọi phải nhận kết quả gì?**

Nếu cơ chế **quan sát tùy chọn** không khả dụng, có những hệ thống được thiết kế để **tiếp tục nghiệp vụ** và báo tình trạng suy giảm. Nhưng nếu một chính sách **bảo mật bắt buộc** không thể xác minh quyền, tiếp tục như người dùng đã được phép có thể tạo lỗ hổng. Nếu **ghi nhận kiểm toán bền vững** là điều kiện trước một tác dụng phụ quan trọng, việc không ghi được có thể bắt buộc **từ chối trước khi thay đổi dữ liệu**. Nếu lỗi chỉ lộ ra **sau khi nghiệp vụ đã cam kết hiệu ứng**, kết luận “không thành công, cứ retry” có thể tạo hiệu ứng trùng.

Không có một câu trả lời `fail-open` hay `fail-closed` đúng cho mọi aspect. Phải định nghĩa **hợp đồng suy giảm (degradation contract)** dựa trên tính bắt buộc của chính sách, ranh giới tin cậy, khả năng xác nhận trạng thái nghiệp vụ và những đường có thể bypass.

Bài này trình bày **Aspect/AOP cơ bản và nâng cao nói chung**. Cú pháp và loại join point được một công cụ hỗ trợ có thể khác nhau; ví dụ Java 17 dùng JDK dynamic proxy để minh họa một đường triển khai và chủ động ghi rõ các giới hạn của nó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **chức năng nghiệp vụ chính** với **chức năng cắt ngang**, rồi đánh giá chính sách nào chỉ hỗ trợ quan sát và chính sách nào là điều kiện an toàn bắt buộc.
2. Mô tả những trạng thái **AVAILABLE, UNAVAILABLE, UNKNOWN, DEGRADED** và hậu quả của việc diễn giải một lỗi kết nối thành quyết định nghiệp vụ.
3. Chọn và ghi thành hợp đồng hành vi **fail-open, fail-closed, fail-safe, fallback** và **degrade-with-signal** trong từng tình huống.
4. Tách lỗi xảy ra **trước khi target chạy**, **trong target**, **sau khi target tạo hiệu ứng** và lỗi trong **cleanup/advice**.
5. Xác định rõ chính sách về **kết quả trả về, ngoại lệ, retry, idempotency, audit và dữ liệu điều khiển**.
6. Hiểu vai trò của **thứ tự aspect**, đặc biệt khi một interceptor có thể chặn không cho `proceed`.
7. Thiết kế cơ chế dự phòng đúng phạm vi, health check, timeout, circuit breaker, backpressure và phục hồi mà không khiến hệ thống che giấu lỗi quan trọng.
8. Đọc và chạy ví dụ Java 17 về observer có thể suy giảm, authorization bắt buộc, audit trước hiệu ứng và bảo toàn ngoại lệ.
9. Xây dựng ma trận kiểm thử lỗi bao gồm nguồn lỗi cắt ngang, nguồn lỗi nghiệp vụ, sự không chắc chắn sau commit và đường bypass AOP.
10. Quy định trách nhiệm xử lý thông báo, dấu vết vận hành và phục hồi theo hợp đồng.

## 2. Hiểu đúng “không khả dụng”

“Không khả dụng” có thể là nhiều hiện tượng khác nhau:

| Hiện tượng | Ví dụ | Điều không được suy ra |
| --- | --- | --- |
| **Dependency down** | Metrics sink không nhận kết nối | Không suy rằng target nghiệp vụ cũng lỗi |
| **Timeout** | Policy service không trả trong thời hạn | Không suy rằng người dùng được phép hay bị từ chối |
| **Initialization failure** | Aspect/interceptor không tạo được | Không suy rằng hệ thống có thể chạy bỏ qua an toàn |
| **Configuration invalid** | Thiếu khóa cấu hình audit | Không nên im lặng tắt audit bắt buộc |
| **Capacity exhausted** | Queue telemetry đầy, audit store hết dung lượng | Không giả định thêm retry sẽ giải quyết |
| **Partial failure** | Tạo dữ liệu xong nhưng không ghi audit | Không suy rằng hiệu ứng nghiệp vụ chưa xảy ra |
| **Stale state** | Cache quyền còn dữ liệu cũ | Không mặc định dữ liệu hết hạn là quyết định hiện tại |
| **Path not intercepted** | Caller gọi target gốc ngoài proxy | Không coi đó là backend aspect bị down |
| **Advice bug** | `NullPointerException` trong logger | Không nên tự xếp mọi lỗi code vào “dịch vụ không khả dụng” |
| **Shutdown/reload** | Runtime đóng interceptor hoặc đổi cấu hình | Phải xác định policy đang có hiệu lực ở giai đoạn nào |

Một trạng thái **UNKNOWN** có thể quan trọng hơn cả “down”: ví dụ request kiểm tra quyền đã gửi nhưng phản hồi bị mất. Đó **không phải bằng chứng cho phép**. Với thao tác có tác dụng phụ, timeout sau khi đã gửi lệnh cũng **không chứng minh hiệu ứng chưa xảy ra**.

### 2.1. Tách lỗi của advice khỏi lỗi của target

Tại một join point, cần hỏi:

- Lỗi do advice/đối tác của aspect tạo ra?
- Lỗi do chính target nghiệp vụ ném?
- Lỗi do proxy/reflection chuyển đổi hoặc bọc?
- Lỗi do lời gọi `proceed` bị bỏ qua, gọi hai lần, hoặc từ chối?
- Lỗi do xử lý sau target, ví dụ ghi audit hoàn tất?
- Lỗi do `finally` khi giải phóng tài nguyên?

Nếu một interceptor `catch (Exception)` rồi mặc định tiếp tục, nó có thể vô tình **nuốt cả lỗi nghiệp vụ**. Nếu một interceptor quanh target `catch (Throwable)` rồi trả `null`, nó còn có thể che lỗi nghiêm trọng hoặc gây lỗi khác ở phương thức trả primitive.

**Chỉ xử lý những lỗi được hợp đồng của từng chính sách cho phép xử lý**; truyền tiếp các lỗi còn lại.

## 3. Phân loại bắt buộc trước khi viết fallback

Để quyết định ứng dụng có thể chạy khi aspect không khả dụng, hãy phân loại **giá trị nghiệp vụ và nghĩa vụ pháp lý/kỹ thuật** của từng chính sách.

### 3.1. Nhóm quan sát hỗ trợ

Có thể gồm một số metric, trace hoặc debug logging **không bắt buộc** để thực hiện giao dịch. Hệ thống có thể chấp nhận mất mẫu quan sát trong thời gian ngắn nếu:

- Mất dữ liệu không vi phạm nghĩa vụ kiểm toán/bảo mật;
- Lỗi observer không sửa input, output hoặc số lần chạy của target;
- Tình trạng degraded được đo/hiển thị theo cách độc lập có thể kiểm chứng;
- Có giới hạn buffer, retry và thời gian chờ;
- Có kế hoạch phục hồi và hậu kiểm chất lượng quan sát.

**Không phải mọi logging đều tùy chọn.** Nhật ký phục vụ tuân thủ, chống gian lận hoặc điều tra bắt buộc có thể thuộc nhóm khác.

### 3.2. Nhóm kiểm soát bắt buộc

Thường gồm kiểm tra quyền trước thao tác nhạy cảm, chính sách bắt buộc để chấp nhận đơn, yêu cầu kiểm toán bền vững hoặc điều kiện bảo toàn nhất quán trước commit. Nếu thiếu kết quả đáng tin, hệ thống cần **từ chối hoặc chuyển sang đường dự phòng được xác thực**.

Một policy service down không phải lý do để diễn giải `UNKNOWN` thành `ALLOW`. Một fallback chỉ được xem là an toàn khi bản thân nó bảo đảm được **cùng bất biến**, ví dụ quyết định đã ký còn hiệu lực theo quy tắc kiểm chứng chặt, chứ không phải đơn giản trả `true`.

### 3.3. Nhóm tối ưu hóa

Cache, batch/aggregation hoặc một số cơ chế rate-control phụ trợ có thể có fallback về đường xử lý gốc **nếu** việc bỏ qua không làm mất bất biến. Ví dụ cache đọc dữ liệu có thể rơi về nguồn chính khi cache down; còn cache đang giữ dữ liệu quyền hoặc một cơ chế chặn giới hạn bắt buộc có thể **không** được bypass.

Chỉ gọi một tính năng là “tối ưu hóa” không đủ: phải xem nó có là **nguồn duy nhất của một kiểm soát** hay không.

### 3.4. Nhóm bảo toàn vòng đời

Aspect mở transaction, lock, tracing scope hay tài nguyên phiên gọi có trách nhiệm giải phóng theo đúng hợp đồng. Nếu không mở được một scope bắt buộc, thường không thể chạy tiếp như scope đã mở. Nếu đã mở rồi mà cleanup lỗi, cần xử lý **lỗi gốc, tài nguyên còn tồn đọng và trạng thái không chắc chắn**, không bỏ qua bằng `catch` rộng.

## 4. Fail-open, fail-closed và fail-safe

| Chiến lược | Ý nghĩa | Tình huống phù hợp theo hợp đồng |
| --- | --- | --- |
| **Fail-open** | Cho phép một đường nghiệp vụ tiếp tục khi policy phụ không phục vụ được | Telemetry phụ trợ không phải điều kiện an toàn |
| **Fail-closed** | Không cho hành động bảo vệ tiếp tục nếu không xác nhận chính sách bắt buộc | Không xác minh được quyền |
| **Degrade-with-signal** | Tiếp tục với chất lượng thấp hơn và phát tín hiệu rõ | Mất metrics sampling, không ảnh hưởng effect |
| **Verified fallback** | Dùng đường dự phòng có cùng cam kết bắt buộc | Chính sách quyền dự phòng đủ tin cậy |
| **Queue/defer** | Tạm nhận yêu cầu ở trạng thái chưa hoàn tất với cam kết ghi nhận phù hợp | Chỉ khi có durable acceptance hợp lệ |
| **Read-only mode** | Chặn ghi nhưng có thể cho một số thao tác đọc an toàn | Mất khả năng xác minh yêu cầu cho thao tác ghi |
| **Hard stop** | Không khởi động/không phục vụ nếu điều kiện bắt buộc sai | Thiếu khóa cấu hình audit bắt buộc |

**Fail-open không đồng nghĩa “bỏ qua mọi exception của advice”.** Nó chỉ được áp dụng cho **loại lỗi và chính sách đã phân loại là cho phép tiếp tục**. Nếu lỗi là vi phạm bất biến hoặc sai thiết kế, chuyển nó thành tín hiệu “observer tạm ngừng” sẽ làm khó chẩn đoán và có thể tạo dữ liệu sai.

**Fail-closed không đồng nghĩa luôn ném một `RuntimeException` chung.** Hợp đồng API có thể trả mã lỗi xác định, trạng thái pending, một kết quả từ chối có kiểu hoặc ngoại lệ chuyên biệt. Điểm cốt lõi là **không thực hiện hành động không còn được phép bảo đảm**.

### 4.1. Ma trận quyết định mẫu

| Chức năng cắt ngang không khả dụng | Có tiếp tục target không? | Ghi chú |
| --- | --- | --- |
| Debug trace tùy chọn | Có thể, nếu được phép mất trace | Ghi degraded signal, không chặn target |
| Metrics collector phụ trợ | Có thể, nếu không là nghĩa vụ bắt buộc | Buffer có giới hạn hoặc drop có kiểm soát |
| Authorization bắt buộc | Không, nếu không có đường kiểm chứng tin cậy khác | UNKNOWN ≠ ALLOW |
| Admission audit bắt buộc trước effect | Không, nếu không có durable fallback tương đương | Chặn trước target |
| Audit đã thất bại **sau effect** | Không thể hoàn tác giả định | Cần trạng thái in-doubt, đối soát/outbox |
| Cache cho phép bỏ qua | Có thể gọi nguồn chính | Không bypass validation/security |
| Rate-limit bắt buộc | Tùy chính sách, thường chặn hoặc dự phòng mạnh | Không vô hiệu quota âm thầm |
| Transaction scope không tạo được | Thường không chạy effect cần transaction | Bảo vệ atomicity |
| Trace span đã mở nhưng đóng lỗi | Xử lý lỗi quan sát theo hợp đồng | Không che ngoại lệ target trái quy tắc |
| Config policy không hợp lệ ở startup | Thường fail startup | Không mặc định tắt guard |

Đây là **ma trận thiết kế**, không phải luật mặc định cho mọi nghiệp vụ. Đặc biệt audit và log có thể là bắt buộc hoặc tùy chọn tùy mức rủi ro và cam kết.

## 5. Viết một hợp đồng suy giảm có thể kiểm chứng

Một hợp đồng vận hành tốt nên ghi:

1. **Chính sách nào?** Tên và trách nhiệm riêng: telemetry, authorization, audit, cache, transaction...
2. **Chức năng đó có bắt buộc cho thao tác nào?** Một request đọc và một giao dịch ghi có thể khác nhau.
3. **Không khả dụng nghĩa gì?** Down, timeout, trả lỗi, invalid config, không xác định, overload...
4. **Lỗi xảy ra ở mốc nào?** Trước khi target chạy, trong target, sau commit, khi cleanup hay lúc khởi tạo.
5. **Có đường fallback hợp lệ nào không?** Tiêu chuẩn xác thực, độ tươi dữ liệu, giới hạn thời gian.
6. **Kết quả người gọi nhận gì?** Giá trị, ngoại lệ, error code, pending/in-doubt, idempotency token.
7. **Tác dụng phụ có thể đã xảy ra không?** Nếu có, không retry thiếu bằng chứng.
8. **Ai có quyền retry?** Aspect, caller, orchestrator hay worker phục hồi.
9. **Giới hạn retry là gì?** Deadline, attempts, backoff, bulkhead, circuit breaker và budget.
10. **Tín hiệu degraded nào được tạo?** Metric nội bộ, readiness/health, alert, event vận hành.
11. **Làm thế nào phục hồi?** Khi backend quay lại, backlog, tái đồng bộ, đối soát và reset state.
12. **Kiểm thử thế nào?** Tất cả nhánh, bao gồm đường bypass và trường hợp chỉ một nửa thành công.

Ví dụ bản hợp đồng ngắn:

```text
Policy: OptionalMeasurement
Failure: exporter timeout / queue full
Action: keep one target invocation, do not alter result/exception
Buffer: bounded; drop samples after budget exhausted
Signal: exporter_degraded, dropped_samples
Recovery: resume on successful health probe

Policy: MandatoryAuthorization
Failure: denied -> reject; unknown/unreachable -> unavailable error
Action: do not execute sensitive effect
Fallback: only independently verified authorization decision
Signal: policy_unavailable; no private data in event
Recovery: health check then allow new verified decisions
```

Đây là **mẫu mô tả hợp đồng**, không phải cú pháp cấu hình AOP chung.

## 6. Mốc lỗi tương đối với `proceed`

Một chuỗi interceptor có thể hình dung:

```text
Caller
  |
  v
Telemetry (optional)
  |
  v
Authorization (mandatory)
  |
  v
AdmissionAudit (mandatory)
  |
  v
Target (effect)
  |
  v
Completion processing
```

Điểm phân biệt quan trọng là **lỗi xảy ra trước hay sau khi lời gọi đã vượt qua ranh giới tạo hiệu ứng**.

### 6.1. Lỗi trước khi chuyển tiếp

Một authorization interceptor không thể xác minh quyền:

```text
before target:
    decision = UNKNOWN
    -> reject without proceed()
```

Nếu target chưa chạy, việc chặn tương đối rõ: không có hiệu ứng của target **qua đường đang xét**. Nhưng phải đảm bảo không có đường bypass khác.

### 6.2. Lỗi ở lời gọi target

Nếu target ném `IllegalArgumentException`, một telemetry interceptor ở ngoài **không được tự coi đây là lỗi của telemetry backend** rồi nuốt lỗi. Cần phân biệt đường throw của nghiệp vụ và lỗi khi thực hiện chính logic quan sát.

Khi dùng reflection, `Method.invoke` có thể bọc lỗi do target ném trong `InvocationTargetException`. Một proxy/interceptor cần bóc đúng `getCause()` khi muốn bảo toàn loại lỗi gốc.

### 6.3. Lỗi sau khi effect đã xảy ra

Một trình ghi audit hậu xử lý hoặc exporter có thể lỗi **sau khi target đã cam kết**:

```text
Target creates effect -> returns successful result
After-advice sends audit -> network timeout
```

Nếu after-advice ném lỗi ra client, client thấy thất bại dù effect có thể đã hoàn thành. Nếu client retry ngay mà không có cơ chế idempotency, có thể tạo **effect thứ hai**. Nếu advice nuốt lỗi để trả success nhưng audit thực sự là bắt buộc, hệ có thể **vi phạm cam kết ghi nhận**.

Giải pháp thường cần điều chỉnh **ranh giới commit, durable audit/outbox, giao thức xác nhận hoặc trạng thái in-doubt**, không chỉ thêm một `catch` trong after advice.

### 6.4. Lỗi trong cleanup

Nếu target đã ném lỗi gốc và `finally` của một advice lại ném lỗi khác, caller có thể chỉ thấy lỗi cleanup. Với aspect chỉ quan sát, quy tắc thường mong muốn là **bảo toàn lỗi gốc** và báo sự cố quan sát trên kênh riêng.

Với tài nguyên bắt buộc, cleanup failure có thể làm trạng thái giao dịch không chắc chắn. Không được luôn nuốt lỗi cleanup nếu điều đó che việc lock/transaction chưa được giải phóng.

## 7. Thứ tự aspect thay đổi ý nghĩa khi một thành phần hỏng

Xét:

```text
Cache(Authorization(Target))
```

Nếu Cache hit và không gọi `proceed`, Authorization bên trong không chạy. Nếu dữ liệu cần được kiểm quyền mỗi lần đọc, thứ tự này có thể cho phép đường truy cập trái hợp đồng khi cache không yêu cầu quyền.

Ngược lại:

```text
Authorization(Cache(Target))
```

giúp bảo đảm auth check chạy trước đường cache trong mô hình chuỗi, **nhưng** còn phải bảo vệ quyền ở tất cả đường gọi khác và thiết kế cache key gắn với tenant/user đúng cách.

### 7.1. Telemetry ngoài guard

```text
Telemetry(Authorization(Target))
```

Nếu Telemetry xử lý lỗi của **chính exporter** và tiếp tục, guard vẫn chạy. Nếu Telemetry dùng `catch (Throwable)` bao cả `proceed` và coi mọi lỗi là “exporter offline”, nó có thể nuốt luôn ngoại lệ **từ Authorization hoặc Target**. Đây là lỗi phân loại **nguồn lỗi**, không phải chính sách fail-open hợp lệ.

### 7.2. Retry bao ngoài guard

```text
Retry(Authorization(Target))
```

Một Retry rộng bắt mọi `RuntimeException` có thể retry ngay cả **SecurityException** hoặc lỗi input. Điều này không tạo quyền; chỉ lặp kiểm tra vô ích hoặc gây tải lớn. Thường phải phân loại lỗi có thể retry, tổng deadline và giới hạn attempts.

### 7.3. Rate-limit, fallback và short-circuit

Một fallback có thể trả kết quả mà không `proceed`. Nếu một chính sách bắt buộc nằm bên trong, fallback ấy có thể bỏ qua guard. Một interceptor rate-limit nếu mất backend phải có quyết định đã được phê chuẩn: chặn, dùng quota cục bộ an toàn hoặc cho tiếp tục với rủi ro đã được chấp nhận bằng hợp đồng.

Không thể định nghĩa “tạm tắt toàn bộ chain khi một interceptor lỗi” rồi coi là đáp ứng đầy đủ AOP.

## 8. Mô hình trạng thái của dependency

Không chỉ có biến Boolean `available` trong sản xuất. Một dependency có thể trải qua:

```text
HEALTHY
   |
   v
SUSPECT (timeouts, increased latency)
   |
   v
UNAVAILABLE / CIRCUIT_OPEN
   |
  probes
   v
RECOVERING (half-open / controlled traffic)
   |
   v
HEALTHY
```

Đây là sơ đồ minh họa; circuit breaker có nhiều biến thể và không phải thành phần bắt buộc của mọi kiến trúc AOP.

### 8.1. Lỗi policy không được biến thành `ALLOW` qua timeout

Một API quyết định có thể trả `ALLOW`, `DENY` hoặc `UNKNOWN`. `UNKNOWN` thường là **không đủ bằng chứng**; nó không được chuyển thành `ALLOW` trong thao tác bắt buộc kiểm soát. Một cache có quyết định đã ký còn hiệu lực có thể là fallback được phê duyệt, nhưng cần kiểm tra expiry, revocation, scope, đối tượng, thao tác và rủi ro.

### 8.2. Timeout phải có ngân sách

Nếu target xử lý tối đa 100 ms nhưng mỗi aspect có timeout 1 giây, đường gọi thực tế có thể đắt gấp nhiều lần. Nên dùng **deadline tổng** và phân chia budget cho từng dependency.

Timeout không chứng minh bên kia chưa thực thi một thao tác. Đặc biệt trong audit và commit, phải giữ khả năng **trạng thái chưa biết** để đối soát.

### 8.3. Backpressure và hàng đợi

Một observer tùy chọn có thể đẩy sự kiện vào queue bounded. Khi queue đầy, hợp đồng cần nói rõ:

- Drop event nào, có giới hạn;
- Có block caller hay không và tối đa bao lâu;
- Có sampling và loại sự kiện không được drop không;
- Ai đo được số event mất;
- Có bảo vệ dữ liệu nhạy cảm trước khi xếp hàng không.

Không dùng queue vô hạn để “đảm bảo không mất log”; khi downstream hỏng lâu, queue có thể giữ request/payload trong bộ nhớ và gây lỗi hệ thống rộng hơn.

## 9. Ví dụ Java 17: ba chính sách, ba cách xử lý lỗi

Chương trình sau dùng **JDK dynamic proxy** để minh họa:

- **Observer tùy chọn**: khi sink không khả dụng, ghi `OBSERVE degraded` rồi cho phép đường gọi tiếp tục, không đổi return/throw của target.
- **Authorization bắt buộc**: khi không xác minh được quyền, chặn **trước target**; khi bị từ chối, trả lỗi rõ.
- **Admission audit bắt buộc trước effect**: nếu không ghi nhận được **ý định xử lý** trong mô hình, chặn **trước target**.
- **Target**: tạo một hiệu ứng minh họa có bộ đếm; một mã không hợp lệ làm target ném lỗi trước khi tăng counter.
- Các trạng thái dependency được thay đổi có chủ ý trong `main` để kiểm thử từng nhánh.

**Giới hạn an toàn:** `AUDIT intent` chỉ biểu diễn một sự kiện được ghi trước khi target xử lý; nó **không** tuyên bố effect đã commit. Ví dụ in ra console, không lưu audit bền vững và không có xác thực thật. Bộ kiểm tra token `"approved"` chỉ dùng trong chương trình học tập. Muốn có kiểm toán giao dịch thật phải dùng một cơ chế durable/transactional phù hợp; muốn kiểm soát quyền thật phải bảo vệ effect ở ranh giới đáng tin cậy.

Lưu thành tệp `CrosscutFailureContractDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class CrosscutFailureContractDemo {
    interface OrderPort {
        String submit(String principal, String id);
    }

    static final class OrderService implements OrderPort {
        int effects;

        @Override
        public String submit(String principal, String id) {
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("invalid order");
            }
            effects++;
            System.out.println("EFFECT " + id + " #" + effects);
            return "OK:" + id;
        }
    }

    static final class Dependencies {
        boolean observerUp = true;
        boolean policyUp = true;
        boolean auditUp = true;
    }

    static final class OptionalObserver {
        void emit(Dependencies deps, String event) {
            try {
                if (!deps.observerUp) {
                    throw new IllegalStateException("observer offline");
                }
                System.out.println("OBSERVE " + event);
            } catch (IllegalStateException unavailable) {
                System.out.println("OBSERVE degraded");
            }
        }
    }

    static final class RequiredAuthorization {
        void check(Dependencies deps, String principal) {
            if (!deps.policyUp) {
                System.out.println("POLICY unavailable");
                throw new IllegalStateException("policy unavailable");
            }
            if (!"approved".equals(principal)) {
                System.out.println("POLICY denied");
                throw new SecurityException("denied");
            }
            System.out.println("POLICY allowed");
        }
    }

    static final class RequiredAdmissionAudit {
        void recordIntent(Dependencies deps, String id) {
            if (!deps.auditUp) {
                System.out.println("AUDIT unavailable");
                throw new IllegalStateException("audit unavailable");
            }
            System.out.println("AUDIT intent " + id);
        }
    }

    static Object callTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static OrderPort wrap(OrderPort target, Dependencies deps) {
        OptionalObserver observer = new OptionalObserver();
        RequiredAuthorization authorization = new RequiredAuthorization();
        RequiredAdmissionAudit audit = new RequiredAdmissionAudit();

        return (OrderPort) Proxy.newProxyInstance(
                OrderPort.class.getClassLoader(),
                new Class<?>[] { OrderPort.class },
                (proxy, method, args) -> {
                    String principal = (String) args[0];
                    String id = (String) args[1];

                    observer.emit(deps, "start:" + id);
                    authorization.check(deps, principal);
                    audit.recordIntent(deps, id);

                    try {
                        Object result = callTarget(method, target, args);
                        observer.emit(deps, "return:" + id);
                        return result;
                    } catch (Throwable targetFailure) {
                        observer.emit(deps, "throw:" + id);
                        throw targetFailure;
                    }
                });
    }

    static void attempt(OrderPort port, String principal, String id) {
        try {
            System.out.println("CALL " + port.submit(principal, id));
        } catch (RuntimeException error) {
            System.out.println("CALL_ERROR "
                    + error.getClass().getSimpleName() + ":"
                    + error.getMessage());
        }
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        Dependencies deps = new Dependencies();
        OrderPort protectedPort = wrap(service, deps);

        System.out.println("CASE healthy");
        attempt(protectedPort, "approved", "A");

        deps.observerUp = false;
        System.out.println("CASE observer-down");
        attempt(protectedPort, "approved", "B");

        deps.policyUp = false;
        System.out.println("CASE policy-down");
        attempt(protectedPort, "approved", "C");

        deps.policyUp = true;
        deps.auditUp = false;
        System.out.println("CASE audit-down");
        attempt(protectedPort, "approved", "D");

        deps.auditUp = true;
        System.out.println("CASE denied");
        attempt(protectedPort, "guest", "E");

        System.out.println("CASE target-error");
        attempt(protectedPort, "approved", "bad");

        System.out.println("TOTAL_EFFECTS " + service.effects);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 CrosscutFailureContractDemo.java
java CrosscutFailureContractDemo
```

Kết quả stdout dự kiến:

```text
CASE healthy
OBSERVE start:A
POLICY allowed
AUDIT intent A
EFFECT A #1
OBSERVE return:A
CALL OK:A
CASE observer-down
OBSERVE degraded
POLICY allowed
AUDIT intent B
EFFECT B #2
OBSERVE degraded
CALL OK:B
CASE policy-down
OBSERVE degraded
POLICY unavailable
CALL_ERROR IllegalStateException:policy unavailable
CASE audit-down
OBSERVE degraded
POLICY allowed
AUDIT unavailable
CALL_ERROR IllegalStateException:audit unavailable
CASE denied
OBSERVE degraded
POLICY denied
CALL_ERROR SecurityException:denied
CASE target-error
OBSERVE degraded
POLICY allowed
AUDIT intent bad
OBSERVE degraded
CALL_ERROR IllegalArgumentException:invalid order
TOTAL_EFFECTS 2
```

### 9.1. Vì sao observer-down vẫn tạo hiệu ứng B?

`OptionalObserver.emit` chỉ bắt lỗi dự kiến của **chính observer**. Khi observer down, nó in `OBSERVE degraded`, sau đó Authorization và Audit vẫn hoạt động bình thường. Target tạo hiệu ứng B và caller nhận `OK:B`.

Điều này thể hiện một **hợp đồng cho phép suy giảm** được thiết kế trước. Trong chương trình thật, phải có kênh giám sát suy giảm độc lập hoặc counter drop có giới hạn; in `System.out` trong ví dụ chỉ để dễ quan sát.

### 9.2. Vì sao policy-down và audit-down không có effect?

Cả hai điều kiện bắt buộc nằm **trước** `callTarget`. Khi Authorization không khả dụng, nó ném `IllegalStateException("policy unavailable")`, không gọi tiếp. Khi audit không khả dụng, quá trình kiểm quyền đã qua nhưng audit intent **chưa được chấp nhận**, nên `recordIntent` ném lỗi và target vẫn chưa chạy.

Các yêu cầu C và D không tăng bộ đếm. Lỗi cụ thể được truyền ra caller; không trả `OK` giả.

### 9.3. Vì sao guest không được phép?

Với principal `guest`, policy có phản hồi xác định **DENY**, khác trạng thái policy không khả dụng. Nó ném `SecurityException("denied")`; không gọi audit intent theo thứ tự đã thiết kế và không gọi target.

Nếu chính sách yêu cầu ghi nhận cả những yêu cầu bị từ chối, phải có **denial audit** riêng đặt trước/ngoài guard và có hợp đồng fail-safe thích hợp. Không tráo `admission audit` với `denial audit` để suy rằng trường hợp từ chối không cần báo cáo.

### 9.4. Vì sao target-error vẫn có dòng `AUDIT intent bad`?

Audit ở ví dụ ghi **ý định được chấp nhận để thử xử lý**, không phải “giao dịch đã commit”. Sau đó target thấy ID `bad` và ném `IllegalArgumentException` trước khi tăng bộ đếm. Observer ghi nhánh `throw`; caller nhận lỗi gốc nhờ `InvocationTargetException.getCause()`.

Do đó `TOTAL_EFFECTS 2`, chỉ hai yêu cầu A và B đã thực hiện effect. Không nên dùng một sự kiện intent làm căn cứ kết luận nghiệp vụ thành công.

### 9.5. Điều gì chưa được ví dụ giải quyết?

- Observer thực tế có thể lỗi vì nguyên nhân bất ngờ, và không phải mọi `IllegalStateException` nên tự được nuốt. Bản học tập dùng đúng một loại lỗi để đơn giản; sản xuất cần phân loại lỗi cụ thể từ API sink.
- Không có timeout hoặc async; trạng thái down được đổi tuần tự giữa những lời gọi.
- Không có durable audit transaction. In ra console không tạo nghĩa vụ lưu trữ đáng tin.
- Không có bảo vệ ranh giới khi caller giữ đối tượng `OrderService` gốc và gọi trực tiếp; proxy có thể bị bypass.
- Không có logic retry hoặc request idempotency; cố tình tránh tạo một ví dụ gây nhân đôi effect.
- Không có kiểm tra overload vì interface chỉ có một phương thức `submit`.
- Cờ trạng thái Boolean không an toàn để thay đổi concurrent ngoài hợp đồng thread-safety; chương trình chỉ dùng một thread.
- Observer sau return trong ví dụ chỉ báo hoàn tất của phương thức đồng bộ; với `CompletableFuture`, return future không phải completion của tác vụ.

## 10. Không nuốt ngoại lệ của target khi xử lý lỗi telemetry

Một kiểu viết sai thường gặp:

```java
try {
    observeBefore();
    return invocation.proceed();
} catch (Exception any) {
    return fallback;
}
```

Đây là **minh họa**, với tên và biến chưa định nghĩa. `catch` bao cả `proceed`, nên nó có thể bắt lỗi của **nghiệp vụ hoặc guard bên trong**, không chỉ lỗi của `observeBefore`. Nếu tiếp tục trả fallback, hành vi bảo mật và hợp đồng ngoại lệ có thể thay đổi.

Một cách phân tách ý tưởng tốt hơn:

```text
try:
    emitOptionalBefore()
catch EXPECTED_OBSERVER_FAILURE:
    markObserverDegraded()

try:
    result = proceed()  // không nuốt lỗi target
catch targetFailure:
    try:
        emitOptionalFailure(targetFailure)
    catch EXPECTED_OBSERVER_FAILURE:
        markObserverDegraded()
    rethrow SAME targetFailure

try:
    emitOptionalReturn(result)
catch EXPECTED_OBSERVER_FAILURE:
    markObserverDegraded()

return result
```

Đây là **giả mã mô hình điều khiển**, không phải một API AOP chuẩn. Phần quan trọng là phạm vi `catch` dành cho lỗi của observer **không ôm cả `proceed`**.

Với chức năng bắt buộc, không thay `markObserverDegraded()` bằng “cho qua”: phải áp đúng hợp đồng của chức năng ấy.

### 10.1. Lỗi logging có thể che lỗi nghiệp vụ

Nếu một advice cố ghi log một exception và logger lại lỗi, kết quả sẽ tùy cách xử lý của advice. Với observer chỉ hỗ trợ, nên bảo toàn nguyên trạng lỗi nghiệp vụ, ghi sự cố quan sát theo đường đã định hoặc bổ sung thông tin chẩn đoán mà không che nguyên nhân gốc.

Với tài nguyên và giao dịch bắt buộc, có thể cần dùng **suppressed exceptions** hoặc một đối tượng kết quả mô tả hai lỗi. Không có quy tắc “luôn nuốt mọi cleanup error” chung cho mọi chính sách.

## 11. Khi lỗi xảy ra sau commit: hợp đồng trạng thái chưa chắc chắn

Một bài toán khó:

```text
1. Receive request X
2. Target commits effect X
3. Audit/response transport fails
4. Caller sees timeout or error
5. Caller retries X
```

Nếu không có bảo vệ, bước 5 có thể tạo effect thứ hai. Đây là lỗi kiến trúc thường bị nhầm là “chức năng cắt ngang down nên retry”.

### 11.1. Ba mức kết quả cần phân biệt

- **REJECTED BEFORE EFFECT:** biết chắc hành động không được thực hiện qua đường đó.
- **CONFIRMED COMMITTED:** có bằng chứng nghiệp vụ đã hoàn tất theo mức cam kết của hệ thống.
- **IN_DOUBT:** không có đủ bằng chứng để khẳng định đã hoặc chưa tạo effect; cần đối soát.

Không đồng nhất `IN_DOUBT` với `REJECTED`. Cũng không trả `SUCCESS` giả chỉ để tránh người gọi retry.

### 11.2. Idempotency và đối soát

Với thao tác có hiệu ứng lâu dài, có thể cần:

- **Idempotency key** gắn với logical request, ổn định qua các lần thử;
- Ràng buộc key với nội dung yêu cầu phù hợp;
- Một nơi tin cậy ghi nhận kết quả đã cam kết;
- Khả năng trả lại kết quả cũ thay vì tạo effect mới;
- Quy trình phát hiện và giải quyết trạng thái `IN_DOUBT`;
- TTL/lifetime key đủ cho cửa sổ retry theo hợp đồng;
- Phương án xử lý concurrent duplicates.

Không phải mọi thao tác đều cần tầng idempotency như nhau. Nhưng khi retry sau một lỗi transport, cần đặc biệt hỏi **side effect có thể đã xảy ra chưa?**.

### 11.3. Durable outbox

Nếu nghiệp vụ cần **đồng thời ghi trạng thái và bảo đảm sau này có event/audit về sự kiện đó**, một phương án là ghi **outbox record trong cùng ranh giới transaction đáng tin** với cập nhật nghiệp vụ, rồi một worker phát đi sau. Như vậy “backend audit/transport down” không cần làm mất thông tin đã được chấp nhận bền vững.

Đây là **mẫu kiến trúc**, không phải khả năng mặc định của AOP hay bảo đảm exactly-once delivery. Consumer và phát lại thường vẫn cần idempotency.

Nếu ngay nơi lưu outbox bắt buộc cũng không ghi được, **không thể tuyên bố đã chấp nhận yêu cầu bền vững**. Cần chặn hoặc trả trạng thái đúng hợp đồng.

## 12. Retry chỉ cho những lỗi đủ điều kiện

Một retry aspect phải phân biệt:

| Loại lỗi | Có retry tự động không? | Lưu ý |
| --- | --- | --- |
| Logger tùy chọn down | Thường không retry toàn nghiệp vụ | Giảm quan sát hoặc retry telemetry độc lập |
| Kiểm tra quyền `DENY` | Không | Không biến từ chối thành tải lặp |
| Authorization `UNKNOWN` | Có thể thử lại **quyết định kiểm tra** trong deadline, không chạy target | Không cho phép khi chưa xác minh |
| Validation input sai | Không | Người gọi cần sửa dữ liệu |
| Network transient trước khi gửi effect | Có thể nếu chứng minh chưa tạo effect | Hợp đồng transport quan trọng |
| Timeout sau gửi lệnh có effect | Không retry mù | Idempotency và đối soát |
| Audit sink đầy | Có thể backoff riêng nếu đã có durable buffer | Không queue vô hạn |
| Transaction conflict | Có thể retry nếu toàn thao tác retry-safe | Scope transaction và side effect |
| JVM `Error` nghiêm trọng | Không bắt rồi coi là hỏng logger | Giữ ngữ nghĩa lỗi phù hợp |

### 12.1. Giới hạn retry

Một chính sách retry phải có số attempts tối đa, deadline tổng, delay/backoff hợp lý, giới hạn tải và điều kiện kết thúc. Nếu nhiều aspect lồng nhau đều retry, số lần target chạy có thể là **tích các mức retry**, lớn hơn dự kiến.

Ví dụ `RetryOuter(RetryInner(Target))` với mỗi tầng thử hai lần có thể dẫn tới **tối đa bốn target attempts** trong những đường lỗi phù hợp. Không kết luận số lần theo tên aspect mà phải kiểm tra cấu trúc `proceed` thực tế.

### 12.2. Circuit breaker không thay authorization

Circuit breaker có thể giảm tải tới một dependency đang down, nhưng nếu dependency là bộ kiểm tra quyền bắt buộc, trạng thái circuit open phải dẫn tới **từ chối hoặc fallback kiểm chứng hợp lệ**, không có đường tự động cho phép.

Một circuit breaker không tự đảm bảo chính sách bảo mật đúng. Nó quản lý **khả năng gọi dependency**, không sinh quyết định quyền đáng tin.

## 13. Startup, runtime và phục hồi

Chức năng cắt ngang có thể không khả dụng ở nhiều giai đoạn:

### 13.1. Startup

Nếu hệ thống **bắt buộc** kiểm tra quyền hoặc ghi audit trước khi phục vụ, cấu hình không hợp lệ có thể là lý do **không khởi động ở chế độ sẵn sàng phục vụ**. Cơ chế readiness/health phải phản ánh điều kiện thực.

Một ứng dụng vẫn có thể khởi chạy tiến trình để tiếp tục phục hồi, nhưng không nên tự công bố `READY` cho những thao tác vi phạm hợp đồng.

### 13.2. Khi đang chạy

Một optional observer down có thể làm hệ chuyển sang trạng thái `DEGRADED`; một guard bắt buộc down có thể khiến một nhóm endpoint trả unavailable hoặc chuyển read-only theo chính sách.

**Mức độ suy giảm có thể theo thao tác**, không nhất thiết một cờ cho toàn ứng dụng. Ví dụ đọc dữ liệu công khai có thể tiếp tục trong khi thao tác chuyển tiền cần xác nhận quyền bắt buộc bị khóa.

### 13.3. Khi phục hồi

Khi dependency hoạt động trở lại, cần kiểm tra:

- Kết quả health probe có đủ tin cậy chưa?
- Có backlog event cần gửi lại không?
- Các yêu cầu `IN_DOUBT` được đối soát thế nào?
- Quy tắc cache quyền stale có được vô hiệu đúng chưa?
- Có đang gây burst tải lớn vì đồng loạt retry không?
- Những trạng thái local/context cũ có cần đóng và khởi tạo lại không?

Việc một socket kết nối lại không chứng minh toàn bộ dữ liệu đã nhất quán. Phục hồi cần **định nghĩa điều kiện kết thúc**, không chỉ một nút “Enable aspect”.

## 14. Quan sát suy giảm mà không phụ thuộc hoàn toàn vào chính tính năng hỏng

Một nghịch lý: nếu bộ thu metrics down, gửi metric “metrics down” tới đúng bộ thu ấy có thể không đến nơi. Vì vậy trạng thái degraded cần có một hoặc nhiều đường phù hợp khác:

- Health/readiness nội bộ;
- Counter/bounded state trong tiến trình;
- Structured diagnostic tối thiểu tới kênh khác;
- Alert dựa trên heartbeat/absence detection ở phía giám sát;
- Status endpoint được kiểm soát quyền;
- Bản ghi theo lô bền vững khi hợp đồng yêu cầu.

Không nên spam stack trace ở mỗi request khi một dependency down kéo dài. Việc ghi log lỗi chính nó có thể tạo tải, rò dữ liệu và tăng retention. Dùng sampling, rate limit và mốc chuyển trạng thái nếu phù hợp.

### 14.1. Ghi mất dữ liệu quan sát thành số liệu đúng nghĩa

Khi cho phép drop một event, có thể ghi số `droppedSamples` ở một counter giới hạn và xuất tổng hợp khi phục hồi. Cần phân biệt:

- **Request processed:** nghiệp vụ đã đi qua đường hợp lệ;
- **Advice attempted:** đã thử ghi telemetry;
- **Telemetry delivered:** có xác nhận nhận dữ liệu;
- **Telemetry dropped:** bị loại do budget hoặc lỗi;
- **Business effect committed:** nghiệp vụ thực sự có effect.

Không dùng một chỉ số làm đại diện cho tất cả. Một lần advice được gọi có thể không tạo thành một bản ghi đã nhận.

## 15. Lỗi khi thay đổi hợp đồng ngoại lệ

Một aspect quanh có thể xử lý `Throwable` và làm thay đổi:

- Loại ngoại lệ;
- Chuỗi cause;
- Suppressed exceptions;
- Thời điểm caller nhìn thấy lỗi;
- Quy tắc retry của caller;
- Mức độ biết chắc về effect.

Ví dụ nếu target ném `IllegalArgumentException` và observer down, **observer không được đổi kết quả thành `OK`** khi hợp đồng chỉ là quan sát. Nếu bắt buộc chuyển đổi ngoại lệ, hãy định nghĩa rõ kiểu kết quả và giữ nguyên thông tin cause/biên trạng thái.

### 15.1. Checked exception qua JDK dynamic proxy

JDK dynamic proxy có hợp đồng về những ngoại lệ checked được phép theo chữ ký phương thức giao diện. Một checked exception không nằm trong khai báo hợp lệ có thể bị bọc trong `UndeclaredThrowableException`. Khi dạy hoặc viết advice, không được giả định ném tùy ý mọi `Throwable` sẽ tới caller dưới cùng kiểu.

Ví dụ runnable ở trên dùng những ngoại lệ unchecked và bóc lỗi reflection để giữ kết quả minh bạch.

### 15.2. `void`, `null` và primitive

Một interceptor fail-open không thể mặc định trả `null` cho mọi phương thức. Nếu method trả `int`, proxy có thể cần unbox và việc trả null gây `NullPointerException`. Nếu method trả `void`, một fallback “giả thành công” có thể che thao tác không được thực hiện. Cần xem chính xác chữ ký và hợp đồng trước khi trả fallback.

## 16. Coverage: AOP không tự bảo đảm chính sách có hiệu lực ở mọi đường

Một JDK dynamic proxy chỉ can thiệp những lời gọi đi **qua proxy và giao diện được đại diện**. Lời gọi trực tiếp target, self-invocation hay đường ở lớp không được proxy cung cấp có thể bypass advice.

Một bộ weaver bytecode có phạm vi khác nhưng vẫn phải kiểm tra **mã nào được weave, loại join point nào được hỗ trợ và artifact nào đang chạy**. Không thể dựa trên việc có một aspect Authorization để tuyên bố mọi effect đã được bảo vệ.

**Với chính sách bắt buộc, hãy đặt hoặc xác minh ranh giới kiểm soát đáng tin cậy**, kiểm thử các đường bypass, và bảo đảm fallback không tạo thêm đường vào không được phép.

Một failure mode riêng là **lỗi khởi tạo proxy/interceptor** khiến ứng dụng âm thầm trả đối tượng gốc. Với chức năng tùy chọn, có thể có chế độ degraded hợp lệ; với guard bắt buộc, đó thường phải được coi là **không sẵn sàng phục vụ** chứ không âm thầm “gỡ aspect cho chạy”.

## 17. Ma trận kiểm thử hợp đồng khi chức năng cắt ngang hỏng

| Kịch bản | Kỳ vọng cần kiểm tra |
| --- | --- |
| Observer khỏe | Event được thử/ghi, target chạy đúng một lần |
| Observer down | Nếu optional: target vẫn chạy, return/throw giữ nguyên |
| Logger của observer ném lỗi | Không nuốt lỗi target hoặc guard |
| Authorization `ALLOW` | Có thể tiếp tục tới các điều kiện bắt buộc kế tiếp |
| Authorization `DENY` | Không gọi target, không trả success giả |
| Authorization `UNKNOWN`/timeout | Không mặc định cho phép |
| Audit intent bắt buộc down trước target | Không tạo effect qua đường đó |
| Audit “committed” down sau effect | Không retry mù; trạng thái/đối soát đúng |
| Target ném validation error | Lỗi gốc được truyền, không bị coi là telemetry lỗi |
| Cleanup của aspect lỗi | Xử lý theo policy, không vô tình che lỗi gốc |
| Cache down | Chỉ fallback về target sau guard bắt buộc |
| Cache hit | Guard không bị short-circuit trái hợp đồng |
| Retry nhiều tầng | Tổng số attempts có giới hạn và quan sát được |
| Circuit breaker open | Quyết định cho phép/không cho phép vẫn đúng |
| Dependency phục hồi | Bỏ degraded theo điều kiện rõ, backlog hợp lệ được giải quyết |
| Queue telemetry đầy | Không tăng bộ nhớ vô hạn |
| Lời gọi bypass proxy | Phát hiện/loại bỏ đường không được guard |
| Advice chưa được weave | Không tuyên bố policy bắt buộc đã áp dụng |
| Request đồng thời | Không lẫn authorization state hoặc context |
| Lời gọi trả future | Tách synchronous return với async completion |
| Quy tắc idempotency | Retry không tạo effect trùng ngoài hợp đồng |

### 17.1. Kiểm thử lỗi ở đúng mốc

Không đủ để chỉ mock “dependency throws”. Cần inject lỗi:

1. **Trước khi giao dịch bắt đầu**;
2. **Trước khi target được phép chạy**;
3. **Ngay trong target trước effect**;
4. **Ngay sau effect nhưng trước response**;
5. **Trong after advice**;
6. **Trong finally/close**;
7. **Trong consumer/background task**;
8. **Trong quá trình khởi tạo và phục hồi**.

Các mốc có thể cho hành vi đúng **khác nhau**, dù cùng một tên exception.

### 17.2. Assert về tác dụng phụ

Một test chỉ assert caller nhận `IllegalStateException` có thể đạt dù target đã tăng counter trước đó. Phải assert **effect count, dữ liệu được cam kết và số lần gọi target**, ngoài status/exception.

Trong ví dụ Java 17, dòng `TOTAL_EFFECTS 2` là một tín hiệu hữu ích: các đường policy-down, audit-down, denied và target-error đều không tạo effect trong mô hình. Ở hệ thật, cần kiểm tra trạng thái persisted, không chỉ counter trong bộ nhớ.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| “Bất kỳ advice nào down đều bỏ qua” | Bypass quyền/audit bắt buộc | Phân loại chính sách, fail closed khi cần |
| Catch tất cả `Throwable` quanh `proceed` | Nuốt target errors và lỗi nghiêm trọng | Thu hẹp phạm vi catch cho nguồn lỗi |
| Observer tự tạo `NullPointerException` | Lỗi phụ trợ che nghiệp vụ | Kiểm tra binding, chính sách lỗi riêng |
| Trả `null` làm fallback chung | Sai primitive/void, giả success | Thiết kế kết quả theo chữ ký |
| Policy timeout được hiểu là ALLOW | Vượt kiểm soát quyền | UNKNOWN khác ALLOW |
| Audit intent nhầm với committed effect | Báo cáo sai trạng thái | Tách admitted, committed, in-doubt |
| Retry toàn giao dịch khi after-audit fail | Dễ tạo effect trùng | Outbox/idempotency/đối soát |
| Queue telemetry không giới hạn | Cạn heap khi downstream down | Buffer bounded/drop/backpressure |
| Health check đơn giản coi là dữ liệu đúng | Bỏ sót trạng thái lỗi/stale | Probe và hợp đồng nhất quán |
| Cache permission stale được dùng không kiểm soát | Quyết định quyền lỗi thời | TTL, revocation, verified fallback |
| Log degraded bằng kênh đang hỏng | Không có tín hiệu hữu ích | Kênh giám sát độc lập |
| Đảo Cache/Authorization | Short circuit bỏ qua guard | Precedence/coverage test |
| Proxy down thì trả target gốc | Bypass chính sách bắt buộc | Fail startup/readiness hoặc trusted route |
| Tự retry vô hạn | Thêm tải và giữ tài nguyên | Deadline, attempt budget, circuit breaker |
| Dùng static `currentRequest` cho state | Lẫn dữ liệu đa luồng, giữ object | Context theo invocation/lifecycle |
| Dùng status HTTP lỗi để suy chưa commit | Retry nhầm sau hiệu ứng | Trạng thái in-doubt và idempotency |
| Không test startup/recovery | Cấu hình sai vẫn phục vụ | Readiness, fault injection, rollback |

## 19. Checklist áp dụng vào kiến trúc AOP

1. Liệt kê những aspect liên quan và loại join point thực sự được cơ chế hỗ trợ.
2. Phân loại mỗi chính sách là optional, mandatory, optimization hay resource lifecycle; xem theo từng thao tác.
3. Định nghĩa lỗi riêng của từng dependency và phân biệt **DOWN, DENY, UNKNOWN, INVALID, IN_DOUBT**.
4. Ghi rõ có được `proceed` khi policy không khả dụng không; không để một advice tùy ý đổi quyết định.
5. Xác định kết quả caller: success, denied, unavailable, pending hay trạng thái chưa chắc chắn.
6. Đặt guard bắt buộc trước mọi đường effect cần kiểm soát; xác minh các đường bypass.
7. Tách try/catch lỗi observer khỏi vùng `proceed` để không che lỗi target.
8. Quy định thứ tự với cache, rate-limit, retry, transaction, audit và fallback.
9. Xác định mốc commit và bảo vệ retry bằng idempotency/đối soát khi cần.
10. Giới hạn timeout, queue, retry, trạng thái cache và tài nguyên; chuẩn bị chế độ degrade rõ.
11. Có health/readiness, alert và số liệu dropped events độc lập với dependency đang hỏng.
12. Kiểm thử fault injection tại trước/giữa/sau effect, cả return, throw, cleanup, startup, recovery.
13. Kiểm chứng action và effect thực, không chỉ exception/status, bằng artifact và đường runtime thật.
14. Viết runbook cho quá trình khôi phục, giải quyết backlog và trạng thái `IN_DOUBT`.

## 20. Bài tập vận dụng có đáp án

### Bài 1 — Observer phụ trợ

Một aspect ghi metrics gặp lỗi backend. Chính sách metrics được xác định là tùy chọn và yêu cầu không làm đổi kết quả nghiệp vụ. Hành vi phù hợp?

**Đáp án:** Bắt riêng lỗi đã được xác định của exporter, giới hạn thời gian chờ, đánh dấu degraded/drop theo ngân sách rồi tiếp tục đường nghiệp vụ. Không bao `proceed` bằng catch rộng có thể nuốt target errors.

### Bài 2 — Kiểm tra quyền không xác định

Authorization trả `UNKNOWN` vì timeout. Có thể mặc định cho phép để giữ uptime không?

**Đáp án:** Không, nếu chính sách xác minh quyền là bắt buộc. Cần chặn hoặc dùng một fallback kiểm chứng đáng tin được quy định trước; UNKNOWN không phải ALLOW.

### Bài 3 — Audit trước effect

Một hợp đồng bắt buộc có admission audit thành công trước khi target chạy. Audit backend down, có thể cứ chạy target và ghi lại sau bằng memory list không giới hạn?

**Đáp án:** Không. Memory list không giới hạn và không bền vững không cung cấp cam kết tương đương. Phải có durable fallback theo hợp đồng hoặc từ chối trước effect.

### Bài 4 — Lỗi sau commit

Target đã lưu một khoản thanh toán, nhưng after-advice gửi audit bị timeout. Caller thấy lỗi. Có được retry toàn bộ thanh toán ngay không?

**Đáp án:** Không retry mù. Effect có thể đã cam kết. Cần idempotency key, ranh giới giao dịch/outbox hoặc truy vấn/đối soát trước khi quyết định thử lại.

### Bài 5 — Lỗi từ target bị nuốt

Interceptor optional `catch(Exception)` bao cả `proceed` rồi trả `null`. Target ném `IllegalArgumentException`. Điều gì sai?

**Đáp án:** Interceptor đã đổi hợp đồng lỗi nghiệp vụ. Nó chỉ nên xử lý lỗi của chính chức năng optional trong phạm vi catch hẹp, còn lỗi target phải được truyền đúng.

### Bài 6 — Cache và guard

Cache nằm ngoài authorization, có cache hit thì không gọi tiếp. Tại sao đây có thể là lỗi?

**Đáp án:** Authorization bên trong có thể không được thực hiện. Nếu dữ liệu cần kiểm quyền ở mọi lần, phải đặt guard ở ranh giới phù hợp và xây cache theo scope quyền đúng.

### Bài 7 — Circuit breaker

Một circuit breaker mở vì policy service down. Nó có quyết định người dùng được phép không?

**Đáp án:** Không. Circuit breaker chỉ quyết định có nên gọi dependency. Khi không gọi được policy bắt buộc, phải từ chối hoặc dùng fallback có cùng cam kết an toàn.

### Bài 8 — Output ví dụ

Trong chương trình Java 17, vì sao `TOTAL_EFFECTS` bằng 2 dù có sáu lượt `attempt`?

**Đáp án:** Chỉ A và B được phép qua các điều kiện bắt buộc và không lỗi ở target. C/D bị chặn vì policy/audit không khả dụng; E bị từ chối; `bad` ném lỗi trước khi tăng counter. Observer-down không ngăn B.

### Bài 9 — Future

Một phương thức trả `CompletableFuture` bình thường, after-returning audit ghi “đã hoàn thành”. Tại sao có thể sai?

**Đáp án:** Return của phương thức chỉ là trả future; tác vụ có thể chưa chạy xong hoặc thất bại sau đó. Audit committed phải gắn với completion/commit thực theo hợp đồng.

### Bài 10 — Khôi phục

Observer phục hồi sau 30 phút. Các event đã bị drop trong lúc down có thể được tuyên bố đã gửi đầy đủ không?

**Đáp án:** Không. Nếu hợp đồng cho phép drop, phải ghi đúng số liệu mất mẫu và không tuyên bố dữ liệu đầy đủ. Nếu hợp đồng yêu cầu durable delivery, cần buffer bền vững và cơ chế phát lại/đối soát.

## 21. Ghi nhớ

- **Chính sách cắt ngang nào không khả dụng phải được xử lý theo hợp đồng riêng**, không áp một catch/fallback chung cho mọi aspect.
- **Fail-open** chỉ hợp lệ khi chính sách cho phép; **fail-closed** bảo vệ những bất biến bắt buộc khi thiếu thông tin đáng tin.
- **Lỗi từ observer khác lỗi từ target**, và timeout/UNKNOWN khác DENY, khác trạng thái đã commit hay chưa biết.
- Xác định **thời điểm lỗi so với effect** trước khi quyết định trả lỗi, retry hoặc báo success.
- **Thứ tự interceptor và short-circuit** có thể khiến một chính sách bắt buộc bị bỏ qua; phải kiểm tra coverage cả đường proxy/weaving.
- Observer tùy chọn nên hạn chế tác động lên return/exception, còn guard/audit bắt buộc phải có fallback đủ tin cậy hoặc chặn trước tác dụng phụ.
- Lỗi **sau effect** đòi hợp đồng idempotency, outbox hoặc đối soát khi phù hợp; không retry toàn nghiệp vụ mù.
- Độ sẵn sàng, queue/backpressure, health, phục hồi và test fault injection là một phần **hợp đồng vận hành của AOP**, không phải phần phụ của vài dòng advice.
