# Kiểm thử khả năng phục hồi bằng giả lập sự cố có mục tiêu

Một hệ thống microservices có thể hoạt động tốt trong điều kiện bình thường nhưng thất bại dây chuyền khi một dịch vụ chậm, một kết nối bị ngắt hoặc một phiên bản ứng dụng vừa khởi động lại. **Kiểm thử khả năng phục hồi bằng giả lập sự cố có mục tiêu** (targeted fault injection) là cách chủ động tạo ra một kiểu lỗi đã chọn, trong một phạm vi được kiểm soát, để quan sát hệ thống phát hiện, cô lập, xử lý và phục hồi như thế nào.

Mục đích không phải tạo ra nhiều sự cố nhất có thể. Mục đích là kiểm chứng một giả thuyết cụ thể về khả năng chịu lỗi bằng bằng chứng đo được: người dùng bị ảnh hưởng ra sao, dịch vụ khác có bị kéo theo hay không, dữ liệu có còn đúng và hệ thống có trở lại trạng thái ổn định sau khi bỏ tác nhân lỗi hay không.

## 1. Kết quả cần đạt

Sau bài này, người học có thể:

- Chọn một rủi ro thực tế của luồng nghiệp vụ và chuyển nó thành một thí nghiệm giả lập sự cố có mục tiêu.
- Phân biệt **fault** (tác nhân gây lỗi), **failure** (hành vi dịch vụ không đáp ứng yêu cầu) và **recovery** (quá trình phục hồi).
- Xác định phạm vi ảnh hưởng, điều kiện dừng và phương án khôi phục trước khi tiêm lỗi.
- Đo tỷ lệ lỗi, độ trễ, lượng yêu cầu tồn đọng, tác động nghiệp vụ và tính toàn vẹn dữ liệu.
- Diễn giải kết quả để cải thiện timeout, retry, circuit breaker, bulkhead, graceful degradation và cơ chế tự phục hồi.

## 2. Vì sao cần chủ động giả lập sự cố?

Trong kiến trúc phân tán, một request thường đi qua nhiều thành phần. Ví dụ:

~~~text
Khách hàng
    |
    v
API Gateway
    |
    v
Checkout Service
    |--------------------------|
    v                          v
Inventory Service        Payment Service
    |                          |
    v                          v
Inventory DB             Payment Provider
~~~

Một số lỗi chỉ xuất hiện khi các thành phần tương tác:

- Inventory phản hồi chậm khiến thread hoặc connection pool tại Checkout bị chiếm hết.
- Checkout retry đồng loạt sau timeout khiến Inventory càng quá tải.
- Payment trả kết quả không rõ ràng làm ứng dụng thu tiền hai lần.
- Một pod bị xóa nhưng load balancer vẫn gửi request vào pod đang dừng.
- Circuit breaker đã mở nhưng không quay lại hoạt động bình thường sau khi dịch vụ phụ thuộc phục hồi.
- Request thất bại, nhưng hàng đợi, reservation hoặc transaction trung gian không được dọn dẹp.

Unit test cho một hàm timeout có thể đúng, nhưng chưa chứng minh toàn bộ luồng nghiệp vụ sẽ phục hồi. Fault injection tạo ra điều kiện bất lợi có chủ đích để kiểm chứng các tương tác đó.

**Phân biệt với thử nghiệm gây lỗi ngẫu nhiên:** Trong targeted fault injection, ta xác định trước thành phần, kiểu lỗi, cường độ, thời lượng, nhóm traffic, số liệu quan sát và ngưỡng dừng. Chaos engineering có thể bao gồm các thí nghiệm như vậy, nhưng không đồng nghĩa với việc gây lỗi tùy ý trên production.

## 3. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa trong thí nghiệm |
|---|---|
| Fault | Độ trễ mạng, HTTP 503, mất kết nối, pod bị dừng, CPU tăng đột ngột... được chủ động tạo ra. |
| Failure | Hành vi quan sát được vi phạm hợp đồng: request lỗi, xử lý quá lâu, dữ liệu sai hoặc hành động nghiệp vụ không hoàn thành. |
| Steady state | Trạng thái vận hành ổn định trước khi tiêm lỗi, được mô tả bằng số liệu thay vì cảm nhận. |
| Hypothesis | Dự đoán có thể kiểm chứng về hành vi hệ thống khi fault xuất hiện. |
| Blast radius | Tập người dùng, request, pod, vùng mạng hoặc dịch vụ có thể bị ảnh hưởng bởi thí nghiệm. |
| Recovery | Khả năng phục hồi cả traffic lẫn trạng thái nghiệp vụ sau khi dừng fault. |
| Abort condition | Ngưỡng buộc phải dừng thử nghiệm ngay khi mức ảnh hưởng vượt dự kiến. |
| SLI / SLO | Chỉ số đo chất lượng dịch vụ / mục tiêu chất lượng đã định; giúp đặt giả thuyết và ngưỡng dừng. |

Một fault không nhất thiết dẫn đến failure. Chẳng hạn, một instance chết nhưng các instance khác vẫn phục vụ đủ tải; người dùng có thể không nhận thấy gián đoạn. Ngược lại, một fault nhỏ có thể gây lỗi dây chuyền nếu timeout, retry và giới hạn tài nguyên không phù hợp.

## 4. Chọn loại sự cố có mục tiêu

Bắt đầu từ **một đường phụ thuộc quan trọng** và **một cơ chế chịu lỗi cần chứng minh**, thay vì thử tất cả lỗi cùng lúc.

| Tác nhân tiêm lỗi | Phạm vi mục tiêu phù hợp | Cơ chế cần kiểm chứng | Điều cần quan sát |
|---|---|---|---|
| Tăng latency phản hồi | Một dependency hoặc tỷ lệ nhỏ request | Timeout, deadline, hủy request | p95/p99, request treo, pool kết nối |
| Trả HTTP 503 có kiểm soát | Một endpoint của downstream | Retry có giới hạn, fallback, circuit breaker | Retry amplification, tỷ lệ trả lỗi đúng |
| Reset hoặc từ chối kết nối | Kết nối Checkout → Inventory | Fail fast, phát hiện lỗi, chuyển hướng | Thời gian phát hiện lỗi và phục hồi |
| Dừng một pod | Một instance không phải toàn bộ cụm | Readiness, load balancing, self-healing | Request in-flight, pod replacement |
| Giới hạn CPU hoặc memory | Một container trong staging | Bulkhead, autoscaling, backpressure | Saturation, queue, OOM, lan truyền lỗi |
| Tăng lỗi một message consumer | Một topic/consumer group thử nghiệm | Retry queue, dead-letter queue, idempotency | Lag, poison message, xử lý trùng |
| Tạm ngắt database của một service | Môi trường dữ liệu dùng cho thử nghiệm | Circuit breaker, transaction boundary | Connection pool, rollback, dữ liệu dang dở |

Không cần tất cả thí nghiệm chạy trên production. Bài học nên bắt đầu bằng unit/integration test với fake hoặc proxy, tiếp tục ở staging gần giống thực tế. Chỉ cân nhắc production khi có kiểm soát đủ chặt, quyền vận hành phù hợp và nhu cầu kiểm chứng hành vi thực tế.

## 5. Từ rủi ro đến giả thuyết đo được

Xét nghiệp vụ đặt hàng:

1. Checkout nhận request với khóa idempotency của đơn hàng.
2. Checkout yêu cầu Inventory giữ hàng.
3. Khi giữ hàng thành công, Checkout mới tiếp tục bước thanh toán.
4. Checkout xác nhận kết quả hoặc trả trạng thái cho phép khách hàng kiểm tra sau.

**Rủi ro:** Inventory trả HTTP 503 trong một khoảng ngắn. Nếu Checkout retry vô hạn, request có thể chất đống, làm cạn connection pool và tạo lượng gọi lớn bất thường sang Inventory. Nếu xử lý lỗi sai, người dùng có thể thấy đơn hàng thành công dù chưa giữ được hàng.

**Giả thuyết kiểm thử:**

> Khi 10% lời gọi giữ hàng từ nhóm traffic thử nghiệm nhận HTTP 503 trong 3 phút, Checkout sẽ thất bại nhanh với thông báo phù hợp cho các đơn bị ảnh hưởng, không ghi nhận đơn đã xác nhận khi chưa giữ được hàng, không tạo thanh toán trùng; các luồng không thuộc nhóm thử nghiệm tiếp tục đáp ứng SLO, và các chỉ số trở lại đường cơ sở trong vòng 60 giây sau khi bỏ fault.

Đây là **ví dụ về ngưỡng chấp nhận**, không phải SLA dùng chung cho mọi hệ thống. Các con số phải được điều chỉnh theo baseline, mục tiêu kinh doanh và khả năng chịu tải của môi trường.

Một bộ tiêu chí giả định cho staging có thể là:

| Chỉ tiêu | Trước khi tiêm lỗi | Khi tiêm lỗi | Sau khi gỡ lỗi |
|---|---|---|---|
| Lưu lượng thử nghiệm | 30 request/giây, ổn định | Giữ nguyên tải | Giữ nguyên tải 2 phút |
| Latency p95 của Checkout | Dưới 400 ms | Không vượt 1.500 ms | Quay lại dưới 400 ms trong 60 giây |
| Request không thuộc nhóm lỗi | Tỷ lệ thành công ít nhất 99,5% | Không giảm dưới 99,5% | Ổn định như baseline |
| Retry từ Checkout sang Inventory | Gần 1 call mỗi thao tác | Không quá 2 lần thử mỗi thao tác | Về mức bình thường |
| Đơn xác nhận khi chưa giữ hàng | 0 | 0 | 0 |
| Thanh toán trùng cho cùng khóa idempotency | 0 | 0 | 0 |
| Backlog hàng đợi liên quan | Ổn định | Không tăng vượt ngưỡng thử nghiệm | Được xử lý về mức baseline |

Lưu ý: nếu Inventory không đáp ứng, kết quả **trả lỗi có kiểm soát** có thể là hành vi đúng. Không được dùng một tỷ lệ HTTP 2xx cao để che giấu việc xác nhận đơn hàng sai hoặc bỏ qua kiểm tra tồn kho.

## 6. Thiết kế phạm vi tác động và rào chắn an toàn

Một thí nghiệm tốt trả lời được năm câu hỏi trước khi bắt đầu:

**Tiêm ở đâu?** Ví dụ: đường gọi Checkout → Inventory, không phải toàn bộ mạng của cluster.

**Tiêm cho ai?** Nhóm request có header thử nghiệm và tenant/dataset dành riêng cho staging; hoặc một canary được xác định rõ.

**Tiêm cái gì, bao lâu, với cường độ nào?** Ví dụ: HTTP 503 trên 10% request đã chọn trong 3 phút. Chỉ một biến lỗi chính được thay đổi mỗi lần.

**Dừng khi nào?** Dừng ngay nếu nhóm không thử nghiệm bị ảnh hưởng, độ trễ vượt ngưỡng, lỗi tăng ngoài phạm vi, tài nguyên có dấu hiệu cạn hoặc phát hiện nguy cơ sai dữ liệu.

**Khôi phục thế nào?** Gỡ rule của proxy, dừng job injection hoặc đưa service test về bản cấu hình ban đầu; xác minh đường gọi, hàng đợi và dữ liệu trở lại bình thường.

Các điều kiện vận hành tối thiểu:

- Có baseline gần nhất, dashboard và trace truy vết được request thử nghiệm.
- Có quyền dừng fault ngay, biết chính xác đối tượng chịu tác động và người chịu trách nhiệm thao tác.
- Tách dữ liệu thử nghiệm khỏi dữ liệu có giá trị thực; dùng thanh toán giả lập cho thí nghiệm checkout.
- Giới hạn thời lượng tự động (time-to-live), số request bị ảnh hưởng và tải sinh ra; không để rule lỗi tiếp tục hoạt động vì quên tắt.
- Không thực hiện đồng thời deploy, migration, load test lớn và fault injection trên cùng đối tượng: sẽ rất khó quy trách nhiệm cho kết quả.
- Xác nhận cơ chế quan sát vẫn hoạt động khi đường phụ thuộc gặp lỗi; metric và log phải đủ để phân biệt lỗi chủ động với lỗi phát sinh tự nhiên.

**Blast radius** cần nhỏ ngay từ thiết kế. Một thí nghiệm trả 503 trên 10% request có nhãn riêng dễ khống chế hơn thí nghiệm chặn toàn bộ traffic đến Inventory. Nếu không thể chứng minh cách cô lập một fault, nên thực hiện trong môi trường chuyên dụng trước.

## 7. Quy trình chạy thí nghiệm từ đầu đến cuối

### Bước 1 — Chọn một luồng nghiệp vụ

Chọn hành vi có giá trị đối với người dùng: tạo đơn, thanh toán, đăng nhập, đọc dữ liệu hoặc xử lý message. Ghi lại đường gọi và các dependency chính. Không chọn một endpoint kỹ thuật đơn lẻ nếu nó không đại diện cho hành vi nghiệp vụ.

### Bước 2 — Chụp đường cơ sở (baseline)

Trong một cửa sổ đủ ổn định, đo request rate, lỗi, p50/p95/p99, CPU, memory, connection pool, queue depth và chỉ số nghiệp vụ. Ghi lại phiên bản ứng dụng, số replica và tải. Không so sánh thí nghiệm tải 30 request/giây với baseline tải 3 request/giây mà kết luận chỉ do fault.

### Bước 3 — Viết giả thuyết và điều kiện dừng

Ví dụ: “Nếu Inventory trả 503 cho 10% lời gọi giữ hàng thuộc nhóm thử nghiệm, Checkout sẽ trả lỗi rõ ràng trong tối đa 1,5 giây; không xác nhận đơn sai; traffic ngoài nhóm vẫn ổn định.” Đặt trước ngưỡng cho độ trễ, tài nguyên và tính đúng đắn của dữ liệu.

### Bước 4 — Chuẩn bị cơ chế tiêm lỗi

Có thể dùng fake ở integration test, proxy điều khiển lỗi giữa hai service, công cụ network fault hoặc job chaos trên nền tảng orchestration. Chọn vị trí tiêm sát đường phụ thuộc cần kiểm chứng. Bảo đảm có một lệnh hoặc thao tác để tắt ngay và không để rule tồn tại vô thời hạn.

### Bước 5 — Chạy ở mức nhỏ trước

Ví dụ: bắt đầu với 1% request thử nghiệm trong 30 giây, quan sát. Nếu hành vi đúng và ổn định, mới tăng tới cường độ đã định. Việc tăng dần giúp phát hiện các hiệu ứng không dự kiến trước khi mở rộng tác động.

### Bước 6 — Quan sát trong lúc fault còn hoạt động

Đối chiếu metric, trace và trạng thái dữ liệu. Kiểm tra cả nhóm bị tiêm lỗi và nhóm không bị tiêm lỗi. Phân biệt request thất bại có kiểm soát với request treo, lỗi lan truyền hoặc trạng thái nghiệp vụ sai.

### Bước 7 — Dừng fault và kiểm tra phục hồi

Gỡ rule injection và giữ traffic thử nghiệm chạy thêm một khoảng. Quan sát circuit breaker chuyển về trạng thái bình thường, queue backlog được xử lý, pool kết nối hồi phục và không còn tác vụ đang “kẹt” gây hiệu ứng muộn. **Gỡ fault chưa có nghĩa hệ thống đã phục hồi hoàn toàn.**

### Bước 8 — Ghi kết quả và hành động kỹ thuật

Đối chiếu từng tiêu chí đã đề ra: đạt, chưa đạt hoặc thiếu bằng chứng. Ghi rõ phạm vi, thời gian, biểu đồ liên quan, trace mẫu, ảnh hưởng nghiệp vụ và nguyên nhân nghi ngờ. Nếu một giả thuyết không đúng, tạo công việc cải thiện cơ chế chịu lỗi rồi lặp lại thí nghiệm để xác nhận thay đổi.

## 8. Ví dụ tiêm lỗi ở ranh giới dịch vụ

Giả sử Checkout gọi Inventory thông qua interface ứng dụng sau:

~~~java
public interface InventoryGateway {
    Reservation reserve(String orderId, String sku, int quantity);
}
~~~

Trong integration test, có thể thay implementation thật bằng một **test double có điều khiển**. Ví dụ giả mã Java sau minh họa chèn lỗi chính xác tại bước gọi Inventory:

~~~java
// Pseudocode: chỉ sử dụng trong test profile, không đưa vào production bean.
final class InjectingInventoryGateway implements InventoryGateway {
    private final InventoryGateway delegate;
    private final Set<String> targetedOrderIds;

    InjectingInventoryGateway(
            InventoryGateway delegate,
            Set<String> targetedOrderIds
    ) {
        this.delegate = delegate;
        this.targetedOrderIds = targetedOrderIds;
    }

    @Override
    public Reservation reserve(String orderId, String sku, int quantity) {
        if (targetedOrderIds.contains(orderId)) {
            throw new InventoryUnavailableException("Injected upstream 503");
        }
        return delegate.reserve(orderId, sku, quantity);
    }
}
~~~

Các lớp Reservation và InventoryUnavailableException trong ví dụ là kiểu minh họa của ứng dụng. Để kiểm thử ở mức HTTP thật, đặt proxy test giữa Checkout và Inventory và cấu hình proxy trả 503 hoặc thêm độ trễ cho đúng endpoint/nhóm request. Không biến việc chèn lỗi thành nhánh nghiệp vụ mặc định trên production.

Thí nghiệm ở lớp ứng dụng trả lời câu hỏi: **Checkout xử lý phản hồi lỗi như thế nào?** Nó không chứng minh Kubernetes có chuyển traffic khỏi pod bị chết hay network mesh xử lý reset kết nối đúng. Muốn kiểm chứng hạ tầng, phải tiêm lỗi ở lớp hạ tầng tương ứng.

Ví dụ dùng một pod trong **namespace staging cô lập** để kiểm thử self-healing:

~~~text
1. Xác định chính xác một pod Inventory thử nghiệm đang Ready.
2. Đo phân phối traffic và số replica trước sự cố.
3. Cho pod đó dừng theo thao tác có kiểm soát.
4. Theo dõi readiness, routing, replacement pod và request đang xử lý.
5. Dừng thí nghiệm nếu lỗi lan ngoài phạm vi đã đặt.
6. Xác minh số replica, traffic và độ trễ trở lại baseline.
~~~

Không xóa tất cả pod bằng selector rộng khi mục tiêu chỉ là hỏng một instance. Cũng không dùng pod deletion để thay thế cho kịch bản kiểm tra lỗi logic trả HTTP 503: hai thử nghiệm chứng minh hai cơ chế khác nhau.

## 9. Cần quan sát những gì?

Một dashboard chỉ cho biết số pod đang chạy là chưa đủ. Tối thiểu nên kết hợp bốn lớp tín hiệu:

| Lớp tín hiệu | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Trải nghiệm người dùng | Success rate theo hành vi, lỗi nghiệp vụ, latency p95/p99 | Người dùng nhận kết quả gì, có chờ quá lâu không? |
| Đường gọi giữa service | Timeout, HTTP status, retry count, circuit breaker state, dependency latency | Lỗi được chặn tại ranh giới nào, có khuếch đại không? |
| Tài nguyên và hàng đợi | CPU, memory, connection/thread pool, queue lag, saturation | Có tài nguyên chung nào bị chiếm hết hoặc nghẽn không? |
| Tính đúng đắn dữ liệu | Đơn đã xác nhận, stock reservation, payment attempts, idempotency key | Có side effect trùng hoặc trạng thái nửa chừng không? |

**Metrics:** Gắn nhãn service, dependency, route và fault experiment ID để so sánh nhóm thí nghiệm với nhóm đối chứng. Giữ cardinality ở mức hợp lý; không đẩy mọi orderId vào metric label.

**Traces:** Theo dõi một request từ Gateway đến Checkout, Inventory và Payment. Các span cần thể hiện latency, mã lỗi, lần thử lại và trạng thái kết thúc. Với thao tác bất đồng bộ, liên hệ trace/request ID với message xử lý sau.

**Logs:** Ghi trạng thái fault được bật/tắt và thời điểm tương ứng; có correlation ID để truy nguyên. Không đưa secret, thông tin thanh toán hoặc dữ liệu cá nhân vào log thí nghiệm.

**Business invariants:** Đây là những điều phải đúng ngay cả khi một số request thất bại. Ví dụ: một khóa idempotency không tạo hai lần charge; một order không được xác nhận khi reserve thất bại; một message thất bại không mất dấu khi chuyển dead-letter queue.

Không nên chỉ nhìn tổng HTTP error rate. Trong trường hợp chủ động trả 503 cho một nhóm nhỏ, error rate tăng trong nhóm đó là dự kiến; vấn đề là **mức độ lan truyền, thời gian phản hồi, hiệu ứng phụ và khả năng phục hồi**.

## 10. Những cơ chế chịu lỗi cần kiểm chứng

### Timeout và deadline

Nếu Checkout cho phép request tối đa 1,5 giây nhưng một lần gọi Inventory có timeout 5 giây, Checkout không thể giữ deadline tổng. Thiết kế timeout cần xét ngân sách thời gian còn lại và chi phí mỗi bước.

Tiêm độ trễ 2 giây vào Inventory để xem Checkout có hủy lời gọi đúng hạn, giải phóng connection và trả phản hồi có thể dự đoán hay không. Một timeout ở tầng API nhưng downstream vẫn tiếp tục làm việc vô hạn là dấu hiệu cần điều tra.

### Retry có giới hạn

Retry chỉ hợp lý với lỗi tạm thời, operation phù hợp và ngân sách thời gian còn lại. Mỗi request thử lại tăng tải lên dependency đang gặp khó khăn.

Nếu 100 request/giây ban đầu, mỗi request thử tối đa 3 lần, tải lý thuyết ở đường phụ thuộc có thể vọt lên gần 300 lời gọi/giây khi mọi lần đều thất bại. Phải đo số lần thử thực tế, đặt backoff có jitter và tôn trọng idempotency. Không retry mù một thao tác thanh toán không xác định trạng thái.

### Circuit breaker

Khi lỗi vượt ngưỡng, circuit breaker cho phép fail fast để tránh tiếp tục chờ dependency. Fault injection nên chứng minh cả ba giai đoạn: phát hiện lỗi để mở circuit, bảo vệ tài nguyên khi circuit mở, và thử hồi phục có giới hạn khi dependency khỏe trở lại.

Nếu breaker mở quá nhạy, lượng request bị từ chối có thể cao hơn cần thiết. Nếu nó không tự đóng sau khi dependency khỏe, hệ thống vẫn gián đoạn dù fault đã bị gỡ.

### Bulkhead và giới hạn tài nguyên

Một dependency chậm không được chiếm toàn bộ thread, worker hoặc connection của các endpoint khác. Tạo độ trễ chỉ trên lời gọi Inventory rồi đo latency của các tuyến không liên quan để kiểm chứng cô lập. Nếu một lỗi downstream làm mọi endpoint cùng chậm, cần xem xét pool chia sẻ, queue không giới hạn hoặc concurrency cap.

### Graceful degradation và fail closed

Không phải luồng nào cũng được phép “phục vụ dữ liệu cũ”. Trang gợi ý sản phẩm có thể dùng cache cũ; xác nhận tồn kho hoặc chuyển tiền có thể cần **fail closed** và trả trạng thái chưa thể xử lý. Một fallback chỉ được coi là đúng khi bảo toàn hợp đồng nghiệp vụ.

### Idempotency, queue và bù trừ

Thử nghiệm network timeout có thể tạo kết quả không rõ: thao tác upstream đã hoàn tất nhưng response bị mất. Dùng idempotency key để ngăn side effect trùng và cơ chế truy vấn trạng thái để hòa giải. Với Saga, phải quan sát bước bù trừ và trạng thái cuối, không chỉ HTTP response của bước đầu.

## 11. Đọc kết quả: thành công, thất bại và tín hiệu bất ngờ

**Trường hợp A — Chịu lỗi đúng:** Inventory trả 503 cho nhóm thử nghiệm; Checkout từ chối đơn bị ảnh hưởng trong giới hạn thời gian; các endpoint khác ổn định; retry được khống chế; sau khi bỏ fault, các chỉ số trở về baseline. Điều này hỗ trợ giả thuyết trong *phạm vi đã kiểm thử*, không chứng minh hệ thống chịu được mọi loại lỗi.

**Trường hợp B — Lỗi khuếch đại:** Chỉ 10% request bị tiêm 503 nhưng hầu hết request Checkout trở nên chậm. Metrics cho thấy connection pool cạn và số retry tăng đột biến. Hướng xử lý: timeout chặt hơn, giới hạn retry theo deadline, concurrency cap/bulkhead và backpressure; sau sửa cần lặp lại cùng thí nghiệm để so sánh.

**Trường hợp C — Hồi phục bề mặt:** HTTP success rate quay lại bình thường ngay sau khi gỡ fault, nhưng queue lag vẫn tăng, pending reservation tồn tại hoặc Payment nhận lệnh xử lý trùng. Thí nghiệm chưa đạt tiêu chí phục hồi nghiệp vụ; cần kiểm tra asynchronous worker, transaction và idempotency.

**Trường hợp D — Không đủ bằng chứng:** Metric không phân biệt nhóm test và nhóm đối chứng, hoặc không có trace tại bước Inventory. Không được kết luận “pass” chỉ vì dashboard tổng có vẻ ổn; cần bổ sung observability và thử lại.

Khi kết quả không phù hợp, tìm nguyên nhân theo đường đi của request và thời điểm fault xuất hiện. Không mặc định mọi thay đổi metric đều do thí nghiệm: deploy, thay đổi tải và sự cố nền có thể gây nhiễu.

## 12. Mẫu bản ghi thí nghiệm hoàn chỉnh

Dưới đây là một **biên bản minh họa** để thấy kết quả cần có; các số liệu là giả định, không phải dữ liệu đo từ một hệ thống thật.

~~~yaml
experiment:
  id: checkout-inventory-503-staging-01
  environment: staging
  business_flow: create-order
  target: checkout-to-inventory/reserve
  fault: http-503
  scope: test-tenant, 10-percent-of-reserve-calls
  duration: 3m
  traffic: 30-requests-per-second
  hypothesis:
    checkout_p95_max_ms: 1500
    unaffected_traffic_success_min_percent: 99.5
    retries_per_operation_max: 2
    confirmed_orders_without_reservation: 0
    duplicate_charges: 0
    recovery_max_seconds: 60
observed:
  checkout_p95_ms: 830
  unaffected_traffic_success_percent: 99.7
  retries_per_operation_max: 2
  confirmed_orders_without_reservation: 0
  duplicate_charges: 0
  recovery_seconds: 42
outcome: hypothesis-supported-in-tested-scope
follow_up: re-run with latency injection and lost-response scenario
~~~

Một biên bản thật nên liên kết đến biểu đồ theo mốc thời gian, trace đại diện, cấu hình injection, phiên bản triển khai và kết quả kiểm tra dữ liệu. Nếu phát hiện lỗi, kèm nguyên nhân và việc khắc phục có người phụ trách. Nội dung có thể lưu trong kho tài liệu thí nghiệm hoặc issue tracker mà nhóm đang sử dụng.

## 13. Các sai lầm thường gặp

1. **Tắt ngẫu nhiên nhiều service cùng lúc.** Không xác định được fault nào gây ra triệu chứng. Hãy bắt đầu với một biến độc lập và mở rộng dần.
2. **Không có giả thuyết trước khi chạy.** Sau sự cố chỉ còn ảnh chụp metric mà không biết thế nào là đạt. Hãy mô tả hành vi mong đợi và ngưỡng cụ thể.
3. **Chỉ đo availability.** Dịch vụ còn trả HTTP 200 nhưng đơn hàng, tồn kho hoặc thanh toán sai. Hãy thêm business invariants.
4. **Coi retry là giải pháp cho mọi lỗi.** Retry có thể gây retry storm và trùng side effect. Hãy xác định lỗi nào retry được, giới hạn số lần và bảo đảm idempotency.
5. **Quên quan sát thời gian sau khi gỡ lỗi.** Queue và tác vụ bất đồng bộ có thể tiếp tục thất bại. Hãy đo recovery window đủ dài.
6. **Để rule tiêm lỗi lan ra ngoài phạm vi.** Một nhãn chọn traffic hoặc selector sai có thể ảnh hưởng hệ thống khác. Hãy cô lập namespace, tenant, endpoint hoặc canary rõ ràng.
7. **Kiểm thử mỗi lần một kiểu tải khác nhau.** Không so sánh được p95 hay saturation. Hãy cố định profile tải hoặc ghi lại khác biệt.
8. **Dùng dữ liệu thực cho kịch bản có thể gây side effect.** Tình huống payment/order cần provider giả lập hoặc dataset dùng riêng.
9. **Chứng minh một fault rồi suy diễn cho mọi fault.** HTTP 503, TCP reset, timeout và phản hồi bị mất có các ngữ nghĩa khác nhau; thiết kế bộ thí nghiệm theo từng rủi ro.
10. **Không lặp lại sau khi sửa.** Một cải tiến chỉ đáng tin khi cùng giả thuyết được kiểm chứng với điều kiện tương đương.

## 14. Bài thực hành có hướng dẫn

**Bài 1 — Tối ưu ranh giới timeout**

Cho Checkout có deadline tổng 1.000 ms. Inventory thỉnh thoảng chậm 1.800 ms. Hãy thiết kế thí nghiệm tiêm latency chỉ vào đường Checkout → Inventory ở staging: đặt baseline và ngưỡng dừng, quan sát p95, connection pool và request đang chạy. Kỳ vọng: Checkout fail fast trước deadline tổng; request không thử nghiệm vẫn ổn định; sau khi ngừng fault, tài nguyên được giải phóng. Nếu lớp HTTP timeout nhưng lời gọi bên trong còn chạy, hãy xác định điểm cần truyền deadline hoặc cancellation.

**Bài 2 — Mất response sau side effect**

Giả lập Payment đã chấp nhận charge nhưng response về Checkout bị cắt trước khi người gọi nhận được. Sau đó Checkout retry cùng khóa idempotency. Thiết kế assertion nghiệp vụ: tổng charge cho một đơn không vượt một; trạng thái thanh toán truy vấn được; nếu outcome chưa rõ, Checkout không tự tạo charge mới với khóa khác. Quan sát trace, payment attempts và thao tác hòa giải. Bài này kiểm chứng tính đúng đắn phân tán sâu hơn một trường hợp HTTP 503 thông thường.

**Bài 3 — Một instance bị dừng**

Trong staging có nhiều replica Inventory. Dừng một instance xác định và đo tỷ lệ lỗi request đang xử lý, tốc độ load balancer loại instance không còn Ready, khả năng tạo replica thay thế và mức độ ảnh hưởng đến các endpoint khác. Đặt điều kiện dừng nếu traffic ngoài nhóm thử nghiệm giảm mạnh hoặc cụm không còn khả năng phục vụ đủ tải. Sau khi hệ thống phục hồi, so sánh baseline trước và sau thử nghiệm.

Các bài thực hành có thể thực hiện riêng biệt. Mỗi bài trả lời một câu hỏi khác nhau: giới hạn thời gian, bảo vệ side effect hoặc tự phục hồi ở tầng hạ tầng.

## 15. Kết luận

Khả năng phục hồi không được xác định chỉ bằng số replica, sự hiện diện của retry hay việc đã cấu hình circuit breaker. Nó cần được **chứng minh bằng thí nghiệm có mục tiêu**: chọn một rủi ro cụ thể, phát biểu giả thuyết, khoanh vùng fault, đo trải nghiệm và dữ liệu, dừng an toàn, rồi kiểm tra trạng thái sau phục hồi.

Một thí nghiệm có giá trị khi nó tạo ra kết luận đủ rõ để quyết định kỹ thuật tiếp theo: cơ chế chịu lỗi đang hoạt động trong phạm vi nào, còn lỗ hổng ở đâu và cần thử lại kịch bản nào sau khi cải thiện hệ thống.
