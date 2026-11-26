# Chính sách tiếp tục xử lý

Khi một application event được giao tới listener, xử lý có thể thất bại vì nhiều lý do: dịch vụ phụ thuộc tạm thời không sẵn sàng, dữ liệu không hợp lệ, lỗi lập trình hoặc một thao tác bên ngoài đã thành công nhưng phản hồi bị mất. Cách ứng dụng phản ứng quyết định event sẽ được thử lại, bỏ qua, dừng để điều tra hay kích hoạt một hành động nghiệp vụ bù trừ.

**Chính sách tiếp tục xử lý** xác định điều gì xảy ra sau một lỗi và điều kiện để luồng event được tiếp tục. Một chính sách tốt cần dựa trên loại lỗi và ý nghĩa nghiệp vụ, có giới hạn retry, giữ dấu vết của quyết định và bảo đảm việc thử lại không tạo hiệu ứng trùng. Không nên dùng một quy tắc retry giống nhau cho mọi listener.

## 1. Những quyết định có thể đưa ra khi xử lý lỗi

Khi listener thất bại, ứng dụng thường cần chọn một trong các hướng:

| Quyết định | Khi phù hợp | Kết quả mong đợi |
|---|---|---|
| Retry | Lỗi tạm thời và thao tác có thể chạy lại an toàn | Thử lại sau một khoảng chờ có giới hạn |
| Skip / acknowledge | Event không còn cần thiết hoặc nghiệp vụ cho phép bỏ qua | Tiếp tục luồng và lưu audit về event đã bỏ qua |
| Stop / pause | Lỗi ảnh hưởng tính đúng đắn hoặc dependency đang gây sự cố diện rộng | Tạm dừng xử lý để tránh làm tình hình xấu hơn |
| Quarantine / dead-letter | Event không thể xử lý tự động hoặc đã hết ngân sách retry | Cô lập event cùng thông tin lỗi để điều tra |
| Compensate | Một bước nghiệp vụ đã tạo hiệu ứng cần được bù trừ | Thực hiện hành động nghiệp vụ đối ứng |
| Reconcile | Kết quả thao tác bên ngoài chưa rõ do timeout hoặc mất phản hồi | Đối chiếu trạng thái trước khi retry hoặc bù trừ |

Các quyết định này không thể thay thế lẫn nhau. Retry giải quyết lỗi kỹ thuật có khả năng phục hồi. Skip là quyết định nghiệp vụ cho phép bỏ qua. Quarantine giữ lại công việc cần con người xử lý. Compensation thay đổi trạng thái nghiệp vụ bằng một hành động bù trừ. Reconciliation làm rõ kết quả khi hệ thống chưa biết thao tác trước đó đã thành công hay chưa.

## 2. Phân loại lỗi trước khi quyết định tiếp tục

Cần phân loại lỗi theo khả năng phục hồi và mức độ an toàn khi chạy lại:

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout mạng, connection reset, HTTP 503, database deadlock | Retry có backoff |
| Bị giới hạn tốc độ | HTTP 429, throttling từ dịch vụ ngoài | Tôn trọng Retry-After, giảm concurrency và retry |
| Lỗi phụ thuộc kéo dài | Broker hoặc database không sẵn sàng trong thời gian dài | Pause/circuit breaker, cảnh báo rồi phục hồi có kiểm soát |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, enum không hỗ trợ, payload sai schema | Quarantine hoặc dead-letter |
| Lỗi nghiệp vụ | Trạng thái không cho phép chuyển tiếp, đối tượng đã bị hủy | Skip, chờ điều kiện hoặc compensation theo quy tắc nghiệp vụ |
| Lỗi lập trình | Null ngoài dự kiến, invariant bị vi phạm, mapping sai | Dừng hoặc quarantine; sửa lỗi trước khi replay |
| Kết quả không xác định | Request tới dịch vụ ngoài timeout sau khi có thể đã được thực hiện | Reconcile bằng idempotency key hoặc truy vấn trạng thái |

Không nên bắt mọi exception rồi xem là lỗi tạm thời. Một lỗi dữ liệu sẽ không tự biến mất khi retry thêm nhiều lần. Ngược lại, bỏ qua mọi exception để listener luôn kết thúc thành công có thể làm mất event mà không ai biết.

Nên có danh sách exception có thể retry, exception cần quarantine và exception cần dừng. Với loại lỗi chưa phân loại, chọn hành vi mặc định an toàn, thường là giữ publication chưa hoàn tất hoặc chuyển sang điều tra, thay vì âm thầm acknowledge.

## 3. Chính sách phải gắn với ý nghĩa nghiệp vụ của listener

Hai listener có thể nhận cùng một event nhưng có mức độ quan trọng khác nhau. Listener cập nhật projection phục vụ dashboard có thể chấp nhận trễ vài phút. Listener phát lệnh giao hàng hoặc ghi nhận thanh toán có thể cần dừng khi không chắc kết quả.

Khi định nghĩa policy cho listener, cần trả lời:

- Event có bắt buộc phải được xử lý hay có thể bỏ qua?
- Nếu xử lý trễ, nghiệp vụ còn hợp lệ không?
- Listener có thể chạy lại cùng event mà không tạo hiệu ứng lặp không?
- Thao tác có thể đã thành công ở hệ thống ngoài dù ứng dụng nhận timeout không?
- Có thể xử lý event sau mà không vi phạm thứ tự nghiệp vụ không?
- Khi hết retry, ai chịu trách nhiệm xử lý tiếp?

Ví dụ, event cập nhật search index có thể được rebuild từ nguồn có thẩm quyền nên có thể quarantine rồi xử lý lại. Event ghi nhận khoản thanh toán không nên bị bỏ qua chỉ vì listener gặp lỗi; cần retry hoặc đối soát trạng thái giao dịch.

Không áp dụng skip chỉ để giảm backlog. Skip phải là một quyết định nghiệp vụ có lý do, phạm vi và dấu vết kiểm toán.

## 4. Retry có giới hạn và backoff

Retry chỉ phù hợp khi lỗi có khả năng tự phục hồi và thao tác có thể thực hiện lại an toàn. Cần giới hạn số lần thử, thời gian chờ và tổng thời gian event được phép nằm trong trạng thái retry.

Một lịch exponential backoff có thể dùng công thức:

d(n) = min(d_max, d_0 × m^(n - 1))

Trong đó n là số lần thất bại, d0 là khoảng chờ ban đầu, m là hệ số nhân và dmax là khoảng chờ tối đa.

Ví dụ với 2 giây ban đầu, hệ số nhân 2 và giới hạn 5 phút:

| Lần thất bại | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 2 giây |
| 2 | 4 giây |
| 3 | 8 giây |
| 4 | 16 giây |
| 5 | 32 giây |
| 6 | 64 giây |
| 7 trở đi | Tối đa 300 giây |

Jitter thêm yếu tố ngẫu nhiên vào khoảng chờ để nhiều instance không cùng retry tại một thời điểm. Khi dịch vụ ngoài trả về Retry-After, policy cần tôn trọng thời điểm đó. Không dùng Thread.sleep trong listener để chờ retry vì sẽ giữ thread và không lưu được lịch khi process dừng.

Cần đặt cả giới hạn số lần thử lẫn deadline. Một event có thể đạt max attempts rất nhanh nếu retry liên tục, hoặc chưa đạt max attempts nhưng đã vượt quá thời gian nghiệp vụ cho phép. Khi vượt một trong các giới hạn, chuyển sang quarantine hoặc manual review.

## 5. Không retry lỗi vĩnh viễn vô hạn

Một event có payload sai schema sẽ tiếp tục thất bại dù thử lại hàng trăm lần. Đây là dạng poison event. Nếu event đó nằm ở đầu một luồng xử lý tuần tự, nó có thể chặn các event tiếp theo.

Với lỗi không thể tự phục hồi:

1. Ghi nhận event ID, listener, loại lỗi và vị trí nguồn.
2. Lưu payload hoặc tham chiếu tới payload theo chính sách bảo mật.
3. Đưa event vào quarantine hoặc dead-letter storage.
4. Phát cảnh báo và gắn owner xử lý.
5. Sửa dữ liệu, schema hoặc logic.
6. Replay event theo quy trình có kiểm soát và giữ nguyên event ID.

Không xóa event lỗi để làm sạch backlog. Cần giữ thông tin đủ để điều tra và chứng minh quyết định bỏ qua hoặc xử lý lại.

Nếu consumer cần tiếp tục xử lý event sau một poison event, phải xác định rõ yêu cầu ordering. Bỏ qua một event có thể khiến các event sau không còn hợp lệ. Với luồng trạng thái theo aggregate, có thể cần dừng riêng aggregate đó trong khi các aggregate khác tiếp tục.

## 6. Tiếp tục hay dừng khi event đến sai thứ tự

Không phải listener nào cũng có thể xử lý event độc lập. Ví dụ, projection nhận các thay đổi trạng thái theo aggregate version:

~~~text
Order version 10: CREATED
Order version 11: PAID
Order version 12: SHIPPED
~~~

Nếu version 12 đến trước version 11, handler có thể:

- Chờ version còn thiếu nếu cần áp dụng từng delta.
- Đọc lại snapshot mới nhất từ nguồn có thẩm quyền nếu event đủ dữ liệu để thay thế trạng thái.
- Đưa event vào hàng đợi chờ theo aggregate.
- Dừng xử lý aggregate đó và cảnh báo nếu không thể xác định trạng thái.

Không nên retry liên tục event version 12 khi version 11 chưa đến mà không có giới hạn hoặc kiểm tra nguồn. Điều đó chỉ tạo tải và có thể che giấu event bị mất.

Nếu event là snapshot đầy đủ, áp dụng version mới hơn có thể hợp lệ. Nếu event là delta, cần bảo đảm các version trước đã được áp dụng. Policy phải phản ánh rõ khác biệt giữa snapshot event và delta event.

## 7. Exception handling trong listener Spring Modulith

Với listener được Spring Modulith quản lý, publication được theo dõi để biết listener đã xử lý thành công hay chưa. Ví dụ listener:

~~~java
@Component
class InvoiceProjectionListener {

    private final InvoiceProjectionService service;

    InvoiceProjectionListener(InvoiceProjectionService service) {
        this.service = service;
    }

    @ApplicationModuleListener
    void on(InvoiceIssued event) {
        service.apply(event);
    }
}
~~~

Nếu service thất bại và exception được truyền ra khỏi listener, publication tương ứng có thể vẫn ở trạng thái incomplete để ứng dụng phục hồi theo policy. Hành vi chi tiết phụ thuộc cấu hình transaction, listener và phiên bản Spring Modulith.

Một lỗi phổ biến là bắt exception rồi chỉ ghi log:

~~~java
@ApplicationModuleListener
void on(InvoiceIssued event) {
    try {
        service.apply(event);
    } catch (RuntimeException ex) {
        log.error("Cannot apply invoice event", ex);
    }
}
~~~

Trong ví dụ này, listener kết thúc bình thường sau khi bắt exception. Cơ chế theo dõi publication có thể coi lần xử lý là thành công, dù nghiệp vụ chưa hoàn tất. Nếu muốn retry tự động, hãy truyền exception ra ngoài hoặc chuyển event sang một trạng thái lỗi/quarantine có chủ đích và được lưu bền vững.

Nếu exception đã được phân loại là lỗi có thể bỏ qua theo nghiệp vụ, listener có thể kết thúc bình thường sau khi ghi nhận quyết định skip và audit đầy đủ. Việc kết thúc bình thường phải có nghĩa event đã được xử lý theo policy, không phải chỉ vì muốn tránh retry.

## 8. Vai trò của Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication của event tới listener. Registry giúp ứng dụng nhận biết publication đã hoàn tất hay còn incomplete và hỗ trợ phục hồi những publication chưa hoàn tất.

Registry không tự quyết định mọi loại lỗi nên retry bao nhiêu lần, khi nào skip hoặc khi nào cần compensation. Ứng dụng cần policy riêng để phân loại lỗi và điều phối phục hồi.

Một luồng xử lý có thể như sau:

~~~text
Application event
       |
       v
Publication recorded
       |
       v
Listener processes event
       |
       +---- success ----------------> publication completed
       |
       +---- retryable failure ------> keep incomplete / schedule retry
       |
       +---- permanent failure -----> quarantine / manual review
       |
       +---- business skip ----------> record skip decision / complete
~~~

Có thể dùng API quản lý incomplete publications của Spring Modulith, chẳng hạn abstraction **IncompleteEventPublications**, để truy vấn hoặc resubmit publication cũ chưa hoàn tất. Một lời gọi resubmit thành công chỉ có nghĩa việc gửi lại đã được yêu cầu; với listener bất đồng bộ, không nên coi đó là bằng chứng nghiệp vụ đã hoàn tất.

Khi cần policy theo từng attempt, ứng dụng nên lưu thêm retry state như số lần thất bại, thời điểm thử tiếp theo, loại lỗi và trạng thái quarantine. Registry giữ trạng thái publication; retry coordinator quyết định publication nào được phép resubmit tại thời điểm hiện tại.

Registry cần persistence phù hợp nếu ứng dụng phải phục hồi publication qua restart. Nó không phải event store đầy đủ và không thay thế kho lưu lịch sử nghiệp vụ.

## 9. Tách retry policy khỏi listener

Listener nên tập trung xử lý nghiệp vụ. Chính sách retry, backoff, giới hạn và quarantine nên được điều phối ở một lớp riêng để có thể áp dụng nhất quán và kiểm thử độc lập.

Một cấu trúc retry state có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| publication_id | Định danh publication được theo dõi |
| listener_id | Listener cần xử lý |
| failed_attempts | Số lần thất bại đã ghi nhận |
| next_attempt_at | Thời điểm sớm nhất được retry |
| last_error_type | Nhóm lỗi gần nhất |
| last_error_message | Thông tin lỗi đã rút gọn |
| state | PENDING, EXHAUSTED, QUARANTINED hoặc MANUAL_REVIEW |
| lease_until | Thời hạn giữ quyền xử lý của worker |

Retry coordinator định kỳ chọn các publication đến hạn, claim bằng lease hoặc khóa, kiểm tra lại trạng thái registry và phân loại lỗi. Nếu lỗi còn retry được, coordinator resubmit. Nếu hết ngân sách, chuyển sang quarantine/manual review và phát cảnh báo.

Không đánh dấu publication hoàn tất chỉ vì coordinator đã gọi resubmit. Registry vẫn cần ghi nhận kết quả thực tế từ listener. Nếu process dừng sau khi claim nhưng trước khi resubmit, lease hết hạn để worker khác có thể tiếp tục.

## 10. Skip có kiểm soát

Skip là quyết định không thực hiện lại event và cho phép luồng tiếp tục. Nó chỉ an toàn khi nghiệp vụ xác nhận event không còn cần thiết hoặc hiệu ứng của nó đã được thực hiện theo cách khác.

Một số trường hợp có thể skip:

- Event là bản cập nhật cũ hơn version hiện tại và policy cho phép bỏ qua.
- Consumer nhận một event không thuộc phạm vi mà nó quan tâm.
- Một sự kiện đã bị thay thế bởi snapshot mới hơn và snapshot đã được áp dụng.
- Nghiệp vụ xác nhận hành động không còn hợp lệ và đã ghi nhận kết quả cuối cùng.

Trước khi skip, cần xác minh event không chứa side effect chưa thực hiện. Ghi lại event ID, listener, lý do, người hoặc policy quyết định và thời điểm. Với event quan trọng như thanh toán, tồn kho hoặc quyền truy cập, skip cần quy trình phê duyệt hoặc đối soát rõ ràng.

Không dùng skip để bỏ qua lỗi kỹ thuật chỉ vì retry đang làm backlog tăng. Hãy giải quyết dependency, giới hạn tốc độ hoặc chuyển event vào quarantine để giữ khả năng phục hồi.

## 11. Quarantine, dead-letter và replay

Quarantine giữ event không thể xử lý tự động để điều tra. Một bản ghi quarantine nên có:

- Event ID và publication ID.
- Tên event, listener và module.
- Payload hoặc tham chiếu payload an toàn.
- Loại lỗi và thông tin lỗi đã rút gọn.
- Số lần thử và thời điểm thất bại gần nhất.
- Correlation ID, trace ID và vị trí nguồn nếu có.
- Trạng thái xử lý, owner và quyết định cuối cùng.

Với Kafka consumer, dead-letter topic có thể giữ record lỗi cùng topic/partition/offset nguồn, key và headers cần thiết. Với Spring Modulith listener nội bộ, có thể dùng bảng quarantine hoặc quy trình quản lý lỗi riêng. Không nhầm dead-letter topic với Event Publication Registry; chúng theo dõi các phần khác nhau của luồng xử lý.

Replay cần giữ event ID ban đầu để consumer deduplicate được redelivery. Ghi nhận ai hoặc job nào yêu cầu replay, lý do, thời điểm và phiên bản handler được dùng. Nếu payload cần sửa, không âm thầm thay nội dung event gốc; hãy lưu bản sửa có audit hoặc phát một event nghiệp vụ mới.

## 12. Compensation và reconciliation

Retry không phải cách giải quyết mọi lỗi. Nếu một bước nghiệp vụ đã tạo hiệu ứng ở hệ thống ngoài, nhưng bước tiếp theo thất bại, có thể cần compensation.

Ví dụ, quy trình đặt hàng đã giữ chỗ thành công nhưng không thể hoàn tất thanh toán. Sau khi xác minh thanh toán chưa thành công, nghiệp vụ có thể phát lệnh giải phóng chỗ. Đây là hành động bù trừ, không phải retry của event giữ chỗ.

Khi request tới dịch vụ ngoài timeout, không biết chắc thao tác đã thành công hay chưa. Trước khi retry hoặc compensation, cần reconcile bằng idempotency key, transaction reference hoặc truy vấn trạng thái từ hệ thống đích. Nếu thao tác đã thành công, retry có thể tạo hiệu ứng trùng; compensation có thể hoàn tác một giao dịch hợp lệ.

Mỗi compensation cần có event hoặc command riêng, idempotency, trạng thái và audit. Không tự động chạy compensation chỉ vì số lần retry đã hết; cần có quy tắc nghiệp vụ xác định hành động nào được phép.

## 13. Với Kafka consumer: tiếp tục xử lý và commit offset

Kafka có thêm quyết định về offset. Nếu consumer commit offset trước khi xử lý nghiệp vụ hoàn tất, record có thể bị mất khỏi luồng xử lý sau restart. Nếu xử lý xong nhưng chưa commit offset, record có thể được giao lại.

Một consumer thường chọn at-least-once delivery và bảo vệ side effect bằng idempotency. Chỉ commit offset sau khi record đã được xử lý thành công hoặc đã được chuyển sang một nơi lưu lỗi bền vững theo policy.

Nếu chọn dead-letter, cần bảo đảm record đã được ghi vào DLT trước khi commit offset của record gốc. Nếu gửi DLT thất bại, không được commit như thể lỗi đã được lưu an toàn.

Khi dùng retry topic, cần hiểu rằng chuyển record sang topic retry có thể làm thay đổi thứ tự quan sát. Nếu thứ tự theo aggregate là bắt buộc, hãy thiết kế key, partition và cách tạm dừng xử lý record sau cho phù hợp.

## 14. Cấu hình policy theo listener hoặc loại event

Một ứng dụng có thể khai báo policy theo listener hoặc event type thay vì dùng một giá trị toàn cục. Ví dụ cấu hình do ứng dụng định nghĩa:

~~~yaml
app:
  events:
    error-handling:
      policies:
        invoice-projection:
          max-attempts: 8
          initial-delay: 2s
          max-delay: 5m
          action-on-exhausted: QUARANTINE
        search-index:
          max-attempts: 5
          initial-delay: 1s
          max-delay: 1m
          action-on-exhausted: REBUILD
~~~

Tên property trong ví dụ là cấu hình riêng của ứng dụng, không phải property mặc định mà Spring Modulith tự động cung cấp. Cần validate cấu hình khi khởi động: max attempts phải dương, max delay không nhỏ hơn initial delay, action phải thuộc danh sách hỗ trợ và mỗi listener quan trọng phải có policy xác định.

Có thể có default policy, nhưng cần ghi rõ cách xử lý khi listener chưa được khai báo. Với event có side effect quan trọng, default nên ưu tiên giữ lại và cảnh báo hơn là skip âm thầm.

## 15. Quan sát và cảnh báo

Một policy chỉ vận hành được khi có thể nhìn thấy quyết định và kết quả. Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Listener failure count | Số lần listener thất bại theo event type và listener |
| Retry attempts | Số lần thử lại |
| Retry success rate | Tỷ lệ event được xử lý thành công sau retry |
| Incomplete publication count | Khối lượng publication chưa hoàn tất |
| Oldest incomplete age | Publication bị chờ lâu nhất |
| Quarantine/DLT count | Event cần điều tra hoặc can thiệp |
| Skipped event count | Số event được bỏ qua theo policy |
| Compensation count | Số hành động bù trừ được kích hoạt |
| Processing latency | Thời gian từ lúc phát event đến khi hoàn tất |

Log nên có event ID, publication ID, listener ID, attempt, error category, next attempt time, policy action và correlation ID. Không ghi credential, token hoặc payload nhạy cảm.

Cảnh báo nên dựa trên tuổi publication, xu hướng backlog, tỷ lệ lỗi và số event bị quarantine. Một lần timeout có thể tự phục hồi; nhiều event cùng thất bại với một dependency hoặc publication vượt SLA cần được điều tra.

## 16. Kiểm thử chính sách tiếp tục xử lý

Kiểm thử nên xác nhận cả quyết định policy và kết quả cuối cùng:

1. Lỗi tạm thời được retry với backoff và không vượt max attempts.
2. Lỗi vĩnh viễn được quarantine thay vì retry vô hạn.
3. Lỗi chưa phân loại đi theo default an toàn.
4. Listener không nuốt exception khi cần giữ publication incomplete.
5. Skip ghi audit và chỉ áp dụng cho trường hợp được phép.
6. Publication resubmit không bị coi là hoàn tất trước khi listener thành công.
7. Process restart không làm mất retry state hoặc quarantine record.
8. Event duplicate không tạo side effect trùng.
9. Event sai thứ tự được chờ, bỏ qua hoặc xử lý theo version policy đã chọn.
10. DLT chỉ được xác nhận sau khi record lỗi đã được lưu bền vững.
11. Timeout không rõ kết quả kích hoạt reconciliation trước khi retry hoặc compensation.
12. Compensation có idempotency và không chạy hai lần cho cùng một quyết định nghiệp vụ.

Dùng clock giả để kiểm thử lịch retry mà không phải chờ thời gian thật. Với Spring Modulith, kiểm thử tích hợp cần xác minh trạng thái publication sau cả listener thành công và thất bại. Với Kafka, kiểm tra offset và DLT bằng broker test phù hợp.

## 17. Checklist trước khi đưa policy vào production

Trước khi bật xử lý lỗi tự động, xác nhận:

- Mỗi listener có policy rõ cho retry, skip, stop và quarantine.
- Lỗi được phân loại theo khả năng phục hồi và ý nghĩa nghiệp vụ.
- Retry có max attempts, deadline, backoff, jitter và concurrency limit.
- Listener có thể chạy lại an toàn hoặc có idempotency.
- Exception không bị nuốt khi cần giữ publication incomplete.
- Event Publication Registry có persistence phù hợp và có quy trình resubmit.
- Skip và compensation có audit cùng điều kiện nghiệp vụ rõ ràng.
- Event poison có nơi quarantine và quy trình replay.
- Kafka offset chỉ commit sau khi xử lý hoặc lưu lỗi bền vững.
- Có metric, cảnh báo, dashboard và owner xử lý event bị kẹt.
- Có kiểm thử restart, duplicate, out-of-order, timeout và lỗi kéo dài.

Chính sách tiếp tục xử lý giúp hệ thống phản ứng nhất quán khi listener gặp lỗi. Khi phân loại lỗi đúng, retry có giới hạn, skip và compensation có audit, publication được theo dõi và event không thể xử lý được quarantine an toàn, các module Spring Modulith có thể tiếp tục giao tiếp mà vẫn bảo vệ tính đúng đắn của nghiệp vụ.

