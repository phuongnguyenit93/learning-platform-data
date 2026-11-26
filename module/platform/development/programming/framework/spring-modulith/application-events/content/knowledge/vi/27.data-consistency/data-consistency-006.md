# Đối soát giữa module

## Vì sao cần đối soát giữa module?

Trong ứng dụng Spring Modulith, mỗi module sở hữu dữ liệu và quy tắc nghiệp vụ của mình. Các module phối hợp qua application event, module API hoặc các hợp đồng được công bố. Khi một thay đổi được truyền bất đồng bộ, các mô hình dữ liệu ở những module khác nhau có thể cập nhật lệch thời điểm.

Ví dụ, Orders xác nhận đơn hàng và phát OrderConfirmed. Billing cập nhật khoản phải thu, Fulfillment chuẩn bị giao hàng, còn một read model tổng hợp cập nhật màn hình quản trị. Nếu một listener lỗi, event bị xử lý trễ hoặc một projection bị cập nhật sai, trạng thái giữa các module có thể không còn khớp với nhau.

**Đối soát giữa module** là quy trình kiểm tra định kỳ hoặc theo yêu cầu để xác định dữ liệu, trạng thái hay các bất biến nghiệp vụ liên quan giữa các module có còn nhất quán hay không. Khi phát hiện sai lệch, hệ thống ghi nhận nguyên nhân và chọn cách khắc phục có kiểm soát.

Đối soát bổ sung cho giao sự kiện. Event giúp truyền thay đổi trong luồng bình thường; đối soát giúp phát hiện sai lệch còn sót lại do lỗi, cấu hình, triển khai, dữ liệu cũ hoặc những trường hợp mà luồng event không thể tự sửa.

~~~mermaid
flowchart TD
    O[Orders module: nguồn dữ liệu đơn hàng] -->|OrderConfirmed| B[Billing module]
    O -->|OrderConfirmed| F[Fulfillment module]
    O -->|OrderConfirmed| P[Read model]
    B --> C[Reconciliation process]
    F --> C
    P --> C
    C --> D{Phát hiện sai lệch?}
    D -->|Không| E[Ghi nhận lần đối soát thành công]
    D -->|Có| G[Phân loại và lưu discrepancy]
    G --> H[Khắc phục qua module API hoặc event]
    H --> I[Đối soát lại và xác nhận]
~~~

Đối soát không nên trở thành một đường ghi dữ liệu tùy tiện xuyên qua ranh giới module. Mỗi module vẫn chịu trách nhiệm thay đổi dữ liệu do mình sở hữu.

## Đối soát khác gì với xử lý application event?

| Cơ chế | Vai trò | Thời điểm |
|---|---|---|
| Application event | Thông báo một sự kiện nghiệp vụ đã xảy ra | Trong luồng xử lý nghiệp vụ |
| Retry/resubmission | Thử lại một publication hoặc lần xử lý bị lỗi | Khi phát hiện xử lý chưa hoàn tất |
| Projection rebuild | Tạo lại read model từ nguồn dữ liệu hoặc event history | Khi cần phục hồi hoặc thay đổi cấu trúc projection |
| Reconciliation | So sánh các trạng thái liên quan để phát hiện sai lệch | Theo lịch, theo yêu cầu hoặc sau sự cố |

Retry xử lý một công việc đã được ghi nhận là chưa hoàn tất. Đối soát tìm những sai lệch mà retry có thể không biết đến, chẳng hạn một bản ghi bị thiếu do lỗi logic cũ, dữ liệu được sửa thủ công hoặc một consumer từng bỏ qua event.

Đối soát cũng không đồng nghĩa với replay toàn bộ event. Một hệ thống có thể đối soát bằng snapshot hiện tại và version mà không cần lưu toàn bộ lịch sử sự kiện.

Event Publication Registry của Spring Modulith theo dõi publication cho các listener được quản lý và trạng thái hoàn tất của chúng. Registry hỗ trợ phát hiện publication chưa hoàn tất theo cấu hình persistence, nhưng không mặc nhiên là event store lưu lịch sử vô hạn để dùng làm nguồn đối soát toàn bộ dữ liệu.

## Xác định nguồn dữ liệu có thẩm quyền

Trước khi so sánh, phải biết dữ liệu nào là nguồn có thẩm quyền (*source of truth*) cho từng thuộc tính. Không nên so sánh hai bản sao rồi tùy ý chọn một bản để ghi đè bản còn lại.

Ví dụ:

| Dữ liệu | Module sở hữu | Module khác có thể giữ |
|---|---|---|
| Trạng thái đơn hàng | Orders | Fulfillment, Billing, read model |
| Trạng thái thanh toán | Payments | Orders, Billing, read model |
| Tồn kho khả dụng | Inventory | Catalog, Orders |
| Trạng thái giao hàng | Shipping | Orders, Notification |
| Tên hiển thị khách hàng | Customers | Orders, read model |

Nếu Billing giữ một bản sao trạng thái đơn hàng để phục vụ xử lý hóa đơn, Orders vẫn là nơi quyết định đơn hàng đã xác nhận hay bị hủy. Billing có thể yêu cầu Orders cung cấp snapshot qua module API hoặc nhận event đã công bố; Billing không nên sửa trực tiếp bảng của Orders.

Một số dữ liệu có thể được nhiều module sở hữu độc lập. Ví dụ, Orders sở hữu tổng tiền đơn hàng đã chốt, còn Payments sở hữu số tiền thực thu. Hai giá trị này không nhất thiết bằng nhau trong mọi thời điểm. Quy tắc đối soát phải dựa trên invariant nghiệp vụ, không dựa vào giả định mọi field trùng tên đều phải bằng nhau.

## Định nghĩa invariant cần kiểm tra

Invariant là điều kiện nghiệp vụ phải luôn đúng hoặc phải đúng khi đạt đến một trạng thái xác định. Đối soát cần chuyển invariant thành điều kiện có thể kiểm tra.

Ví dụ:

- Một đơn hàng đã xác nhận phải có bản ghi yêu cầu giao hàng, trừ các loại đơn không cần giao.
- Tổng phân bổ thanh toán không được vượt số tiền phải thu của hóa đơn.
- Một projection đơn hàng không được mang aggregate version thấp hơn version đã công bố trong snapshot mới nhất.
- Một yêu cầu hoàn tiền đã hoàn tất phải có trạng thái tương ứng trong Payments.
- Tồn kho đã giữ cho đơn hàng phải được giải phóng khi đơn hàng bị hủy theo quy tắc nghiệp vụ.

Mỗi invariant cần nêu rõ:

1. Các module hoặc dữ liệu tham gia.
2. Module nào có thẩm quyền cho từng thuộc tính.
3. Điều kiện áp dụng và các trường hợp ngoại lệ.
4. Thời gian cho phép dữ liệu hội tụ.
5. Cách xác định sai lệch và mức độ nghiêm trọng.
6. Ai hoặc quy trình nào có quyền khắc phục.

Không nên đánh dấu sai lệch ngay khi event vừa phát nhưng listener chưa có thời gian xử lý. Nếu hệ thống cho phép hội tụ trong 30 giây, đối soát cần phân biệt một trạng thái đang chờ hợp lệ với một sai lệch đã vượt thời hạn.

## Các kiểu sai lệch thường gặp

| Loại sai lệch | Ví dụ | Cách kiểm tra |
|---|---|---|
| Thiếu bản ghi | Orders đã xác nhận nhưng Fulfillment chưa có shipment request | Tìm ID nguồn không tồn tại ở module nhận |
| Bản ghi mồ côi | Fulfillment có shipment cho order ID không tồn tại hoặc không hợp lệ | Tìm bản ghi đích không có nguồn tương ứng |
| Trạng thái không khớp | Orders đã hủy nhưng Billing vẫn giữ trạng thái cần thu tiền | So sánh trạng thái theo mapping nghiệp vụ |
| Giá trị tổng hợp sai | Read model có tổng tiền khác nguồn | So sánh giá trị đã chuẩn hóa |
| Projection cũ | Read model đang ở version 7 trong khi nguồn đã ở version 9 | So sánh version/checkpoint |
| Quan hệ bị thiếu | Invoice không có tham chiếu tới order hợp lệ | Kiểm tra foreign reference qua API hoặc snapshot |

Một discrepancy cần chứa đủ thông tin để điều tra mà không buộc người vận hành phải đoán dữ liệu nào được so sánh.

## Thiết kế hợp đồng snapshot cho đối soát

Khi cần so sánh dữ liệu thuộc module khác, hãy dùng module API hoặc hợp đồng snapshot được công bố. Không truy cập trực tiếp repository hoặc bảng nội bộ của module khác.

Một snapshot có thể chứa:

~~~java
public record OrderConsistencySnapshot(
    UUID orderId,
    long aggregateVersion,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant updatedAt
) {}
~~~

Module Orders cung cấp snapshot thông qua API có quyền kiểm soát:

~~~java
public interface OrdersConsistencyApi {

    Optional<OrderConsistencySnapshot> findSnapshot(UUID orderId);

    Page<OrderConsistencySnapshot> findSnapshotsAfter(
        UUID afterId,
        int pageSize
    );
}
~~~

Đây là ví dụ về hợp đồng nội bộ được công bố cho mục đích tích hợp; cách phân trang và kiểu trả về cần được điều chỉnh theo kiến trúc ứng dụng. API nên chỉ trả các field cần cho invariant và không làm lộ entity hoặc cấu trúc persistence.

Nếu đối soát giữa hai hệ thống độc lập, có thể trao đổi snapshot qua API, file export có version hoặc event snapshot. Cần có thời điểm tạo snapshot, version dữ liệu và định danh nguồn để biết hai phía đang so sánh những mốc nào.

## So sánh theo version thay vì chỉ theo timestamp

Timestamp hữu ích để quan sát, nhưng không luôn đủ để xác định thứ tự thay đổi. Clock giữa các máy có thể lệch và nhiều cập nhật có thể xảy ra trong cùng một đơn vị thời gian.

Aggregate version hoặc sequence tăng đơn điệu thường phù hợp hơn để kiểm tra projection đã theo kịp nguồn chưa.

Ví dụ:

- Orders trả snapshot order A với version 12.
- Projection của Fulfillment ghi nhận version 11.
- Đối soát xác định projection đang cũ và tạo discrepancy loại STALE_PROJECTION.
- Nếu projection nhận event version 12 sau đó, lần đối soát tiếp theo có thể xác nhận sai lệch đã được khắc phục.

Cần phân biệt version của từng aggregate với offset của Kafka partition. Offset biểu diễn vị trí trong partition, không phải version nghiệp vụ của một đơn hàng. Một projection nhận event từ nhiều partition có thể cần checkpoint riêng theo aggregate hoặc theo từng nguồn.

Timestamp vẫn cần thiết để đo độ trễ và đặt SLA. Không dùng timestamp làm khóa duy nhất để bỏ qua event hoặc quyết định dữ liệu mới hơn nếu hệ thống không bảo đảm clock và thứ tự.

## Đối soát theo snapshot và watermark

Một lần đối soát có thể kéo dài trong khi dữ liệu vẫn tiếp tục thay đổi. Nếu đọc từng module tại các thời điểm khác nhau, kết quả so sánh có thể phản ánh hai trạng thái không cùng thời điểm.

Có một số chiến lược:

- **Snapshot nhất quán:** đọc dữ liệu từ một snapshot transaction hoặc API hỗ trợ snapshot token.
- **Watermark:** chốt mốc version, timestamp hoặc offset đến đó dữ liệu được xem là ổn định để đối soát.
- **Version recheck:** khi phát hiện mismatch, đọc lại version nguồn và đích trước khi tạo hành động sửa.
- **Eventual reconciliation:** chấp nhận dữ liệu hai phía được đọc ở thời điểm gần nhau, sau đó kiểm tra lại trước khi kết luận sai lệch cần can thiệp.

Không phải mọi database hoặc module API đều hỗ trợ một snapshot phân tán xuyên nhiều module. Không nên tuyên bố một lần quét là snapshot toàn hệ thống nếu không có cơ chế đảm bảo điều đó.

Một cách thực tế là đối soát theo cửa sổ thời gian và version. Ghi lại thời điểm bắt đầu, watermark của từng nguồn và checkpoint phân trang. Khi một bản ghi thay đổi trong lúc quét, version recheck giúp tránh khắc phục dựa trên dữ liệu đã lỗi thời.

## Chạy đối soát theo lô và phân trang an toàn

Không tải toàn bộ dữ liệu của các module vào bộ nhớ. Hãy chia thành lô nhỏ và dùng keyset pagination theo khóa ổn định.

Luồng tổng quát:

~~~text
Bắt đầu reconciliation run
    |
    v
Lấy trang snapshot nguồn sau checkpoint
    |
    v
Lấy trạng thái tương ứng từ module đích
    |
    v
Chuẩn hóa và so sánh theo invariant
    |
    +--> Khớp: ghi nhận kết quả trang
    |
    +--> Sai lệch: lưu discrepancy
    |
    v
Commit checkpoint và tiếp tục trang sau
    |
    v
Hoàn tất run và tổng hợp kết quả
~~~

Một checkpoint có thể lưu:

- reconciliation run ID.
- module nguồn và module đích.
- khóa cuối cùng đã xử lý.
- watermark hoặc version snapshot.
- thời điểm bắt đầu và cập nhật gần nhất.
- trạng thái run và số bản ghi đã kiểm tra.

Keyset pagination thường ổn định hơn offset pagination khi bảng có dữ liệu mới được thêm trong lúc quét. Khóa phân trang cần có thứ tự ổn định và duy nhất; nếu dùng timestamp, thêm ID làm khóa phụ để tránh bỏ sót các bản ghi cùng timestamp.

Mỗi batch nên có transaction ngắn. Không giữ một transaction kéo dài trong suốt hàng triệu bản ghi vì có thể giữ lock, tăng áp lực transaction log và gây ảnh hưởng đến nghiệp vụ trực tuyến.

## Lưu discrepancy có thể truy vết

Một bản ghi sai lệch nên lưu thông tin so sánh và vòng đời xử lý. Ví dụ schema khái niệm:

~~~sql
CREATE TABLE reconciliation_discrepancy (
    discrepancy_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    invariant_code VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    source_version BIGINT,
    target_version BIGINT,
    discrepancy_type VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP NULL,
    resolution_reference VARCHAR(200) NULL
);
~~~

Có thể lưu thêm giá trị đã chuẩn hóa hoặc hash của hai phía để điều tra. Cần cân nhắc quyền riêng tư và dung lượng trước khi lưu payload đầy đủ.

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| DETECTED | Sai lệch vừa được phát hiện |
| INVESTIGATING | Đang xác định nguyên nhân |
| REPAIR_PENDING | Đã chọn cách sửa nhưng chưa thực hiện |
| REPAIRING | Hành động sửa đang chạy |
| RESOLVED | Đã xác minh dữ liệu khớp |
| IGNORED_WITH_REASON | Sai lệch được chấp nhận theo ngoại lệ có ghi nhận |

Dùng khóa idempotency hoặc unique constraint phù hợp để một lần quét lặp không tạo vô số discrepancy giống nhau. Có thể dùng tổ hợp invariant, aggregate ID, source version và target version làm định danh sai lệch; khi version thay đổi, đó có thể là một sự cố khác cần lưu dấu riêng.

Không xóa discrepancy ngay khi vừa gửi yêu cầu sửa. Giữ lịch sử phát hiện, hành động và kết quả để có thể audit.

## Phân loại và chọn cách khắc phục

Không phải mọi sai lệch đều nên tự động sửa. Cần phân loại theo nguyên nhân, mức độ ảnh hưởng và quyền sở hữu dữ liệu.

| Nguyên nhân | Cách khắc phục có thể dùng |
|---|---|
| Listener chưa xử lý publication | Resubmit publication theo cơ chế Spring Modulith đã cấu hình |
| Projection bị cũ nhưng event còn khả dụng | Replay event hoặc cập nhật lại projection theo version |
| Projection sai do bug mapping | Sửa handler, rebuild/backfill projection |
| Thiếu bản ghi nghiệp vụ ở module nhận | Gửi command qua module API hoặc phát event bù theo nghiệp vụ |
| Dữ liệu nguồn không hợp lệ | Chuyển cho chủ sở hữu nghiệp vụ điều tra |
| Sai lệch do thao tác thủ công | Ghi nhận audit và thực hiện quy trình sửa có phê duyệt phù hợp |

Hành động sửa phải đi qua API của module sở hữu dữ liệu. Ví dụ, nếu cần tạo lại shipment request, gọi use case công khai của Fulfillment hoặc phát một command/event phù hợp; không insert trực tiếp vào bảng Fulfillment từ một job đối soát đặt trong Orders.

Nếu cần thay đổi trạng thái nghiệp vụ, hãy tạo một hành động nghiệp vụ rõ ràng như ReopenShipmentRequest hoặc PaymentAllocationCorrected. Không sửa dữ liệu lịch sử bằng cách giả mạo event cũ như thể nó vừa xảy ra.

## Tránh race condition khi khắc phục

Một sai lệch được phát hiện lúc version 10 có thể đã tự hết khi event version 11 đến trước lúc job sửa chạy. Nếu job ghi đè snapshot dựa trên kết quả cũ, nó có thể tạo ra sai lệch mới.

Quy trình sửa an toàn nên:

1. Đọc lại snapshot nguồn và đích ngay trước khi sửa.
2. So sánh version hiện tại với version đã ghi trong discrepancy.
3. Nếu version đã đổi, đánh dấu discrepancy cũ là stale/recheck và chạy lại phép so sánh.
4. Gửi command sửa có idempotency key và expected version nếu module hỗ trợ.
5. Để module sở hữu dữ liệu kiểm tra invariant trong transaction của chính nó.
6. Đọc lại snapshot sau sửa và xác nhận invariant đã đúng.
7. Lưu resolution reference và thời điểm hoàn tất.

Optimistic locking hoặc conditional update giúp ngăn sửa dựa trên trạng thái cũ. Không giữ lock xuyên qua nhiều module hoặc qua network call để cố tạo một transaction phân tán giả tạo.

## Idempotency cho hành động sửa

Job đối soát có thể chạy lại sau timeout hoặc restart. Một command sửa có thể được gửi nhiều lần nếu worker không biết lần gửi trước đã thành công hay chưa.

Mỗi hành động sửa nên có idempotency key ổn định, ví dụ:

~~~text
reconcile:<invariant-code>:<aggregate-id>:<source-version>:<target-version>
~~~

Module nhận lưu key hoặc operation ID cùng kết quả trong transaction với thay đổi nghiệp vụ. Khi nhận lại cùng yêu cầu, module trả kết quả đã có thay vì áp dụng thay đổi lần thứ hai.

Nếu command sửa tạo application event, event cần mang reference tới reconciliation run hoặc discrepancy để truy vết. Không dùng một key mới mỗi lần retry vì điều đó làm mất khả năng nhận diện cùng một hành động.

## Tách phát hiện sai lệch khỏi hành động sửa

Trong nhiều hệ thống, nên tách hai bước:

- **Detection:** đọc snapshot, so sánh invariant và lưu discrepancy.
- **Repair:** nhận discrepancy đã được phân loại, kiểm tra lại dữ liệu hiện tại và gọi module API để khắc phục.

Tách bước giúp có thể chạy chế độ chỉ phát hiện (*dry run*), xem xét kết quả trước khi sửa, giới hạn số hành động đồng thời và áp dụng chính sách riêng cho từng loại sai lệch.

Với lỗi nghiêm trọng hoặc hành động có tác động tài chính, nên yêu cầu người có thẩm quyền xem xét trước khi thực hiện. Với projection có thể tái tạo và rủi ro thấp, có thể tự động repair sau khi kiểm tra version và idempotency.

Một reconciliation run nên có mode rõ ràng như DETECT_ONLY hoặc DETECT_AND_REPAIR. Ghi lại ai hoặc hệ thống nào khởi chạy, cấu hình invariant, watermark và số hành động sửa đã thực hiện.

## Đối soát projection và read model

Projection là trường hợp phổ biến của đối soát giữa module. Nguồn dữ liệu có thẩm quyền cung cấp aggregate version hoặc snapshot; read model lưu version cuối cùng đã áp dụng.

Ví dụ:

| Order ID | Version nguồn | Version projection | Kết quả |
|---|---:|---:|---|
| A-100 | 12 | 12 | Khớp |
| A-101 | 9 | 7 | Projection cũ |
| A-102 | 5 | Không có | Thiếu projection |
| A-103 | 8 | 10 | Projection vượt version nguồn, cần điều tra |

Projection có version lớn hơn nguồn không nên tự động bị ghi đè. Có thể nguồn snapshot được đọc ở thời điểm cũ hơn, projection nhận event mới hơn, hoặc version hai phía không cùng phạm vi. Hãy xác nhận semantics của version trước khi kết luận dữ liệu sai.

Nếu projection là snapshot có thể dựng lại, repair có thể lấy snapshot mới nhất từ module sở hữu và upsert theo version. Nếu projection là incremental model phụ thuộc mọi delta, cần kiểm tra event gap và backfill đúng thứ tự thay vì chỉ ghi đè một vài field.

## Đối soát dữ liệu tổng hợp và số tiền

So sánh số tiền cần quy tắc chuẩn hóa rõ ràng:

- Cùng currency và scale.
- Cùng quy tắc làm tròn.
- Phân biệt amount trước thuế, sau thuế và số tiền thực thu.
- Xác định thời điểm chốt dữ liệu.
- Quy định tolerance nếu nghiệp vụ cho phép sai số.

Không so sánh BigDecimal bằng cách chuyển sang double vì có thể phát sinh sai số dấu phẩy động. Dùng phép so sánh decimal và quy tắc scale/currency được công bố.

Một tổng hợp có thể thay đổi trong lúc đối soát. Cần dùng snapshot hoặc watermark nhất quán, và không tự động điều chỉnh số dư bằng một phép cộng/trừ chỉ dựa trên chênh lệch chưa được xác minh. Với dữ liệu tài chính, mọi correction nên có reference, lý do, actor và dấu vết audit.

## Lập lịch và kiểm soát tải đối soát

Đối soát có thể chạy theo lịch, theo sự kiện vận hành hoặc theo yêu cầu hỗ trợ. Tần suất phụ thuộc mức độ quan trọng và chi phí truy vấn.

Nên thiết kế:

- Chạy incremental theo changed-since hoặc checkpoint để tránh quét toàn bộ mỗi lần.
- Có full scan định kỳ với tần suất thấp hơn để phát hiện sai lệch bị bỏ sót.
- Giới hạn page size, concurrency và tốc độ gọi module API.
- Dùng lease hoặc distributed lock nếu nhiều instance có thể khởi chạy cùng một run.
- Cho phép resume từ checkpoint sau restart.
- Có timeout và cancellation để tránh run kéo dài không kiểm soát.
- Ưu tiên giờ tải thấp nếu truy vấn đối soát ảnh hưởng hệ thống trực tuyến.

Không nên dùng một distributed lock làm cơ chế bảo đảm correctness duy nhất. Dù có lock, vẫn cần idempotency và conditional update vì lease có thể hết hạn hoặc worker cũ có thể tiếp tục sau khi mất quyền sở hữu.

## Kiểm thử đối soát giữa module

Kiểm thử cần bao phủ phát hiện, race condition, hành động sửa và khả năng chạy lại:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Hai phía khớp | Không tạo discrepancy |
| Thiếu bản ghi đích | Phát hiện đúng aggregate và invariant |
| Version đích thấp hơn nguồn | Phân loại stale projection |
| Version thay đổi trong lúc repair | Không ghi đè dữ liệu mới; yêu cầu recheck |
| Đối soát chạy lại | Không tạo discrepancy hoặc correction trùng |
| Module API từ chối command | Lưu trạng thái lỗi và có thể retry |
| Nguồn trả trang rỗng | Kết thúc run đúng checkpoint |
| Dữ liệu thay đổi khi phân trang | Không bỏ sót hoặc kết luận sai do pagination |
| Sai lệch được sửa | Đọc lại và xác nhận invariant trước khi RESOLVED |
| Một module tạm ngừng hoạt động | Run ghi nhận partial failure, không đánh dấu toàn bộ thành công |

Có thể dùng module integration test để xác nhận ranh giới API và event contract. Test đối soát không nên truy cập repository nội bộ của module khác để tạo shortcut; hãy dùng public API hoặc fixture được công bố cho kiểm thử.

Với job bất đồng bộ, dùng điều kiện chờ có giới hạn và kiểm tra checkpoint. Tránh sleep cố định.

## Quan sát và audit

Mỗi lần đối soát cần có run ID để nối log, metric và discrepancy. Các chỉ số hữu ích:

- Số bản ghi đã kiểm tra theo module và invariant.
- Số discrepancy mới, đang xử lý, đã giải quyết và bị bỏ qua có lý do.
- Thời gian chạy và số batch.
- Số lần gọi module API, tỷ lệ lỗi và latency.
- Số command repair thành công/thất bại.
- Tuổi discrepancy cũ nhất.
- Số run dở dang hoặc bị resume.
- Số lần phát hiện version gap hoặc projection lag.

Log nên có run ID, discrepancy ID, aggregate ID ở dạng phù hợp, invariant code và resolution reference. Không ghi payload nhạy cảm hoặc dữ liệu cá nhân không cần thiết.

Metric label nên có cardinality giới hạn như module, invariant code và discrepancy type. Không dùng aggregate ID hoặc event ID làm label metric.

Audit cần ghi ai hoặc thành phần nào khởi chạy run, cấu hình nào được dùng, dữ liệu snapshot/version nào được so sánh, hành động nào đã thực hiện và kết quả xác minh. Nếu một discrepancy được chấp nhận như ngoại lệ, phải lưu lý do và người có thẩm quyền xác nhận.

## Quy trình thiết kế đối soát giữa module

Khi thêm một quy trình reconciliation, hãy thực hiện theo thứ tự:

1. Xác định invariant nghiệp vụ và module sở hữu từng field.
2. Chọn snapshot API hoặc hợp đồng dữ liệu được công bố cho từng nguồn.
3. Xác định watermark, version và cách phân trang ổn định.
4. Chuẩn hóa dữ liệu và định nghĩa chính xác điều kiện khớp.
5. Lưu run, checkpoint và discrepancy có thể truy vết.
6. Phân loại sai lệch và xác định cách repair được phép.
7. Thực hiện repair qua module API hoặc event có idempotency key.
8. Đọc lại dữ liệu và xác nhận invariant sau sửa.
9. Theo dõi backlog, tuổi discrepancy, lỗi API và kết quả run.
10. Kiểm thử chạy lặp, dữ liệu thay đổi đồng thời và phục hồi sau restart.

Đối soát giữa module giúp phát hiện những sai lệch mà luồng event bình thường có thể để sót. Khi xác định rõ nguồn có thẩm quyền, so sánh theo invariant và version, lưu discrepancy có audit, rồi khắc phục qua API của module sở hữu dữ liệu, hệ thống có thể phục hồi nhất quán mà vẫn giữ được ranh giới nghiệp vụ.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events and Event Publication Registry: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith Reference — Application Module Structure and Boundaries: https://docs.spring.io/spring-modulith/reference/fundamentals.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
