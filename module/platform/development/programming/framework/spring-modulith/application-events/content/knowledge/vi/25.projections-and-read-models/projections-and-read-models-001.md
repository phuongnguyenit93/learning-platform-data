# Projection từ event

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Một ứng dụng có thể dùng những sự kiện đó để xây dựng **projection**: dữ liệu được tổ chức riêng cho nhu cầu đọc, tìm kiếm, báo cáo hoặc hiển thị của một use case.

Projection thường là một phần của **read model** trong kiến trúc CQRS. Khi nghiệp vụ thay đổi, module sở hữu dữ liệu phát event mô tả sự thay đổi. Listener nhận event và cập nhật cấu trúc đọc phù hợp. Nhờ đó, màn hình hoặc API truy vấn không cần ghép nhiều bảng nghiệp vụ mỗi lần đọc, và module tạo read model không cần truy cập trực tiếp repository nội bộ của module phát event.

## 1. Projection và read model là gì?

Projection là kết quả của việc biến một hoặc nhiều event thành dữ liệu có cấu trúc phục vụ truy vấn. Read model là mô hình dữ liệu được tối ưu cho các câu hỏi mà ứng dụng cần trả lời. Một projection có thể là một hàng trong bảng, một document, một bản ghi tìm kiếm hoặc một cấu trúc tổng hợp.

Ví dụ, module Order sở hữu đơn hàng và công bố các event như OrderPlaced, OrderConfirmed và OrderCancelled. Một read model cho trang danh sách đơn hàng có thể giữ orderId, customerId, trạng thái, tổng tiền và thời điểm cập nhật. Khi nhận event, listener cập nhật projection để API danh sách đọc trực tiếp từ cấu trúc đó.

| Khái niệm | Trách nhiệm |
| --- | --- |
| Write model | Mô hình và quy tắc dùng để thực hiện thay đổi nghiệp vụ. |
| Domain/application event | Mô tả sự kiện nghiệp vụ đã xảy ra và dữ liệu cần cho bên nhận. |
| Projection | Biến event thành một biểu diễn dữ liệu phù hợp cho truy vấn. |
| Read model | Cấu trúc dữ liệu và API phục vụ một hoặc nhiều nhu cầu đọc. |
| Projector | Listener hoặc thành phần xử lý event để cập nhật projection. |

Một event có thể cập nhật nhiều projection khác nhau. OrderPlaced có thể cập nhật danh sách đơn hàng của khách, số liệu doanh thu theo ngày và một read model phục vụ màn hình vận hành. Mỗi projection có mục đích, cấu trúc và nhịp cập nhật riêng.

## 2. Vì sao xây dựng read model từ event?

Trong một hệ thống chia module, mỗi module sở hữu dữ liệu và quy tắc nghiệp vụ của mình. Một màn hình tổng hợp có thể cần dữ liệu từ Order, Customer và Payment. Nếu API truy vấn gọi trực tiếp repository nội bộ của cả ba module, nó tạo phụ thuộc vào cấu trúc lưu trữ và làm ranh giới module khó thay đổi.

Thay vào đó, mỗi module công bố event có ý nghĩa ổn định. Một module hoặc thành phần query nhận event và duy trì read model của riêng nó. API đọc chỉ truy vấn read model.

Lợi ích thường gặp:

- Truy vấn được tối ưu cho màn hình hoặc use case cụ thể.
- Giảm số lần join hoặc gọi đồng bộ nhiều module trong đường đọc.
- Module query có thể chọn cấu trúc dữ liệu riêng mà không thay đổi write model.
- Một event có thể nuôi nhiều projection độc lập.
- Read model có thể được xây dựng lại từ nguồn event bền vững hoặc dữ liệu snapshot phù hợp.

Đổi lại, read model được cập nhật bất đồng bộ nên có thể trễ hơn write model. Đây là tính nhất quán cuối cùng (eventual consistency). API và giao diện cần chấp nhận hoặc thể hiện độ trễ đó thay vì giả định dữ liệu đọc thay đổi tức thì cùng transaction ghi.

## 3. Luồng từ event đến projection

Giả sử Order công bố OrderConfirmed sau khi transaction xác nhận đơn hàng commit. Module OrderSummary lắng nghe event và cập nhật projection danh sách đơn hàng.

~~~mermaid
sequenceDiagram
    participant O as Order module
    participant R as Event Publication Registry
    participant L as OrderSummary listener
    participant P as Projection database
    participant Q as Query API

    O->>O: Cập nhật đơn hàng
    O->>R: Publish OrderConfirmed trong transaction
    O->>O: Commit transaction
    R-->>L: Giao event sau commit
    L->>P: Upsert read model trong transaction riêng
    P-->>L: Commit projection
    L->>R: Xác nhận listener hoàn tất
    Q->>P: Đọc danh sách đơn hàng
    P-->>Q: Trả projection
~~~

Luồng minh họa cho thấy việc cập nhật write model và read model thuộc hai transaction khác nhau. Event Publication Registry có thể theo dõi publication đến transactional listener nội bộ; nó không biến hai transaction đó thành một transaction database duy nhất.

Nếu listener thất bại trước khi projection commit, lần xử lý có thể được recovery theo cơ chế publication đã cấu hình. Nếu projection commit thành công nhưng tiến trình dừng trước khi publication được đánh dấu hoàn tất, event có thể được giao lại. Vì vậy, projector phải xử lý duplicate an toàn.

## 4. Thiết kế event đủ dữ liệu cho projection

Projector chỉ có thể cập nhật read model khi event mang đủ thông tin hoặc có thể truy xuất bổ sung qua API công khai. Hãy xác định projection cần hiển thị những field nào rồi thiết kế event contract tương ứng.

Ví dụ:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    UUID customerId,
    BigDecimal total,
    String currency,
    long aggregateVersion,
    Instant occurredAt
) {}
~~~

Các field có ý nghĩa:

| Field | Vì sao cần |
| --- | --- |
| eventId | Nhận diện event để chống xử lý trùng. |
| orderId | Khóa của đối tượng trong projection. |
| customerId | Hỗ trợ truy vấn đơn hàng theo khách hàng. |
| total và currency | Cung cấp dữ liệu hiển thị mà không cần đọc bảng nội bộ Order. |
| aggregateVersion | Phát hiện event cũ hoặc event đến sai thứ tự nếu phiên bản được tăng đơn điệu. |
| occurredAt | Thời điểm nghiệp vụ xảy ra, phục vụ hiển thị và điều tra. |

Không nên đưa toàn bộ entity hoặc object graph của write model vào event. Payload quá lớn, chứa quan hệ lazy hoặc field nội bộ sẽ làm consumer phụ thuộc vào implementation của module phát. Hãy công bố một DTO ổn định, chỉ chứa dữ liệu mà consumer được phép sử dụng.

Nếu event chỉ mang orderId và projector phải gọi API Order để tải toàn bộ trạng thái hiện tại, read model có thể vẫn hoạt động nhưng phát sinh coupling và tải truy vấn bổ sung. Cách này phù hợp khi payload lớn hoặc dữ liệu thay đổi nhạy cảm; cần cân nhắc snapshot event, API truy vấn công khai và cách xử lý khi trạng thái đã tiến xa hơn event đang được xử lý.

## 5. Cập nhật projection trong Spring Modulith

Module OrderSummary có thể đăng ký listener cho OrderConfirmed. Listener chuyển event vào service sở hữu transaction cập nhật read model:

~~~java
@Component
@RequiredArgsConstructor
class OrderSummaryProjector {

    private final OrderSummaryProjectionService projections;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.apply(event);
    }
}
~~~

Service cập nhật projection:

~~~java
@Service
@RequiredArgsConstructor
class OrderSummaryProjectionService {

    private final OrderSummaryRepository repository;

    @Transactional
    public void apply(OrderConfirmed event) {
        repository.upsert(
            event.orderId(),
            event.customerId(),
            event.total(),
            event.currency(),
            event.aggregateVersion(),
            event.occurredAt()
        );
    }
}
~~~

Đoạn code thể hiện ranh giới trách nhiệm; phương thức upsert là API repository minh họa và cần được triển khai phù hợp với database được chọn. Khi dùng @ApplicationModuleListener, Spring Modulith cung cấp listener bất đồng bộ và transaction xử lý theo cơ chế của annotation. Nếu dùng @TransactionalEventListener trực tiếp, hãy chọn phase phù hợp, thường là AFTER_COMMIT, và cấu hình transaction cho phần cập nhật read model.

Repository nên cập nhật hàng projection theo khóa ổn định, thường là orderId. Nếu hàng chưa tồn tại thì tạo mới; nếu đã tồn tại thì cập nhật theo quy tắc phiên bản. Không để hai projector cùng ghi một read model nếu chưa xác định rõ quyền sở hữu và cơ chế phối hợp.

## 6. Idempotency và event đến lặp

Event Publication Registry có thể resubmit publication chưa hoàn tất. Ngoài ra, event có thể được phát lại từ broker hoặc nguồn lưu trữ. Một projector phải an toàn khi nhận cùng event nhiều lần.

Có hai cách phổ biến:

1. **Idempotent upsert:** áp dụng cùng một event nhiều lần vẫn cho ra cùng một projection state.
2. **Inbox/deduplication:** lưu eventId đã xử lý và thay đổi projection trong cùng transaction; unique constraint ngăn event được áp dụng lần nữa.

Ví dụ, nếu OrderConfirmed chỉ đặt trạng thái projection thành CONFIRMED và ghi total, việc chạy lại cùng event có thể không gây thay đổi thêm. Nhưng nếu projector cộng dồn doanh thu bằng câu lệnh tăng tổng tiền, chạy lại sẽ làm số liệu sai. Với phép cộng dồn, cần lưu eventId đã áp dụng hoặc dùng một chiến lược tổng hợp có thể tính lại.

~~~sql
CREATE TABLE processed_projection_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng transaction, projector ghi eventId vào bảng inbox và cập nhật projection. Nếu insert vi phạm unique constraint, event đã được áp dụng trước đó; projector có thể kết thúc như một lần xử lý thành công. Không ghi inbox ở transaction riêng trước khi cập nhật projection, vì crash giữa hai thao tác có thể làm mất thay đổi read model nhưng khiến event bị coi là đã xử lý.

## 7. Thứ tự event và cập nhật cũ

Một aggregate có thể phát nhiều event liên tiếp: OrderPlaced, OrderConfirmed rồi OrderShipped. Listener bất đồng bộ hoặc cơ chế retry có thể khiến event đến không theo thứ tự mong muốn. Nếu projector chỉ ghi đè theo thứ tự nhận, event cũ có thể làm read model quay về trạng thái trước.

Hãy đưa aggregateVersion hoặc sequence tăng đơn điệu vào event. Projection lưu phiên bản mới nhất đã áp dụng. Khi nhận event:

- Nếu version mới lớn hơn version đang lưu và không vi phạm quy tắc nghiệp vụ, áp dụng thay đổi.
- Nếu version bằng version đã xử lý, kiểm tra duplicate theo eventId hoặc chính sách idempotency.
- Nếu version nhỏ hơn version đang lưu, bỏ qua như event cũ hoặc ghi nhận để điều tra.
- Nếu phát hiện thiếu version ở một luồng yêu cầu đầy đủ thứ tự, đánh dấu projection cần đồng bộ lại thay vì âm thầm bỏ qua khoảng trống.

Không phải mọi projection đều cần thứ tự tuyệt đối. Một read model chỉ lưu thời điểm event mới nhất có thể dùng điều kiện cập nhật theo version. Một projection tính tổng hoặc chuyển trạng thái theo chuỗi có thể cần phát hiện gap và xử lý tuần tự theo aggregate key.

## 8. Eventual consistency và trải nghiệm truy vấn

Sau khi write model commit, listener có thể cần thêm thời gian để cập nhật projection. Trong khoảng đó, lệnh ghi trả về thành công nhưng truy vấn read model vẫn hiển thị trạng thái cũ. API nên định nghĩa rõ hành vi này.

Một số lựa chọn:

- Trả về resource ID và trạng thái xử lý, để client truy vấn lại sau.
- Trả về trạng thái pending hoặc projectionVersion nếu use case cần theo dõi tiến độ.
- Dùng read-your-writes fallback: ngay sau khi ghi, trả dữ liệu từ write model hoặc dữ liệu trong response command thay vì chờ projection.
- Hiển thị thời điểm cập nhật cuối của read model để người dùng hiểu dữ liệu có thể trễ.

Không nên thêm delay cố định rồi giả định projection chắc chắn đã cập nhật. Độ trễ phụ thuộc tải, listener, database và retry. Nếu cần chờ projection, dùng tín hiệu hoặc điều kiện có timeout rõ ràng, không polling vô hạn.

## 9. Nhiều projection từ cùng một event

Một event có thể phục vụ nhiều read model với mục đích khác nhau. Ví dụ OrderConfirmed có thể cập nhật:

| Projection | Tối ưu cho câu hỏi |
| --- | --- |
| CustomerOrderList | Khách hàng có những đơn hàng nào và trạng thái hiện tại? |
| DailySalesSummary | Doanh thu theo ngày và tiền tệ là bao nhiêu? |
| OperationsOrderBoard | Đơn hàng nào cần nhân viên vận hành theo dõi? |
| OrderSearchDocument | Đơn hàng phù hợp với bộ lọc tìm kiếm nào? |

Mỗi projection nên có projector và storage contract riêng. Nếu một projector lỗi, projection khác vẫn có thể cập nhật độc lập. Không nên gộp mọi read model vào một listener khổng lồ vì mỗi use case có thể có quy tắc cập nhật, tốc độ và chính sách phục hồi khác nhau.

Khi một projection phụ thuộc nhiều event type, hãy xác định cách kết hợp dữ liệu. Ví dụ CustomerOrderList có thể cần OrderConfirmed và PaymentCaptured. Nếu hai event đến khác thứ tự, projector phải xử lý trạng thái tạm thời, giữ thông tin cần thiết hoặc chỉ công bố trạng thái tổng hợp khi đủ điều kiện.

## 10. Xóa, hủy và dữ liệu không còn tồn tại

Projection phải phản ánh các thay đổi vòng đời, không chỉ event tạo mới. Khi đơn hàng bị hủy, OrderCancelled có thể chuyển trạng thái projection thành CANCELLED. Khi dữ liệu cần bị xóa, hãy xác định projection dùng tombstone, xóa vật lý hay giữ bản ghi đã ẩn theo chính sách nghiệp vụ và pháp lý.

Nếu event chỉ thông báo một entity đã bị xóa mà không mang khóa định danh, projector có thể không biết cần xóa hàng nào. Event xóa nên chứa identifier ổn định và thông tin cần thiết để cập nhật projection. Nếu projection được lưu ở search index hoặc cache, cần có cơ chế xóa tương ứng và retry khi hệ thống đích không sẵn sàng.

Không nên xóa projection chỉ vì một event đến trễ. Dùng aggregateVersion hoặc timestamp có quy tắc rõ ràng để tránh một event cũ tái tạo dữ liệu đã bị xóa hợp lệ.

## 11. Rebuild và backfill projection

Read model có thể cần xây dựng lại khi thay đổi cấu trúc truy vấn, sửa lỗi projector hoặc bổ sung field mới. Có thể rebuild từ event history nếu ứng dụng có nguồn lưu event bền vững, đầy đủ và có khả năng đọc lại. Cũng có thể backfill từ write model qua API/export được module sở hữu công khai.

Spring Modulith Event Publication Registry là registry theo dõi trạng thái giao event đến listener; không nên coi nó là event store lưu toàn bộ lịch sử nghiệp vụ để replay projection từ đầu. Publication completed có thể được dọn theo retention policy, và registry không được thiết kế để thay thế một event log đầy đủ.

Một quy trình rebuild có kiểm soát thường gồm:

1. Tạo bảng/index projection mới hoặc namespace version mới.
2. Chọn nguồn dữ liệu đầy đủ: event store, snapshot kết hợp event log hoặc API backfill.
3. Chạy projector theo thứ tự và lưu checkpoint/sequence đã xử lý.
4. Trong khi backfill, xử lý các event mới phát sinh bằng cơ chế catch-up để tránh khoảng trống.
5. So sánh số lượng, tổng hợp và một số bản ghi mẫu với nguồn nghiệp vụ.
6. Chuyển query sang projection mới sau khi đạt điều kiện kiểm tra.
7. Giữ phương án quay lại hoặc xóa projection cũ sau thời gian ổn định.

Nếu nguồn replay không bảo đảm thứ tự hoặc có thể phát lại duplicate, projector vẫn cần idempotency và version checks. Không dùng publication registry làm nguồn backfill duy nhất.

## 12. Kiểm thử projection

Unit test cho projector nên xác minh event tạo mới, cập nhật, hủy và xử lý duplicate. Integration test cần kiểm tra transaction, event dispatch và persistence để phát hiện lỗi chỉ xuất hiện khi listener bất đồng bộ hoặc khi transaction rollback.

Các tình huống nên bao phủ:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Event tạo mới | Projection được tạo với đúng dữ liệu. |
| Event cập nhật | Projection thay đổi theo quy tắc của use case. |
| Event trùng | Không cộng dồn hoặc tạo side effect lần hai. |
| Event cũ đến muộn | Version guard ngăn projection lùi trạng thái. |
| Event thiếu dữ liệu | Projector xử lý lỗi có kiểm soát và ghi nhận chẩn đoán. |
| Transaction listener rollback | Projection không bị ghi một phần; publication còn khả năng recovery. |
| Nhiều projector | Mỗi read model được cập nhật độc lập theo hợp đồng của nó. |
| Xóa hoặc hủy | Projection được ẩn, xóa hoặc chuyển trạng thái đúng chính sách. |
| Rebuild/backfill | Kết quả rebuild khớp nguồn dữ liệu theo các invariant đã chọn. |
| Restart/retry | Checkpoint và idempotency ngăn mất hoặc áp dụng trùng dữ liệu. |

Đối với read model tổng hợp, hãy kiểm tra cả tổng số và các invariant nghiệp vụ. Ví dụ tổng doanh thu theo ngày phải bằng tổng các giao dịch hợp lệ trong tập dữ liệu kiểm thử, không chỉ xác minh rằng một event đã gọi repository.

## 13. Quan sát và vận hành read model

Một projection có thể chậm dù Kafka hoặc publisher vẫn hoạt động bình thường. Theo dõi riêng từng projector giúp tìm đúng điểm nghẽn.

Các tín hiệu hữu ích gồm:

- Độ trễ từ occurredAt hoặc publication time đến lúc projection cập nhật.
- Số publication incomplete theo listener và tuổi của publication lâu nhất.
- Tỷ lệ exception, retry và duplicate bị phát hiện.
- Số event được áp dụng, bỏ qua do version cũ hoặc đưa vào trạng thái cần đồng bộ lại.
- Thời điểm và version/checkpoint cuối cùng của projection.
- Số hàng hoặc document trong read model và kết quả kiểm tra invariant.

Log nên có eventId, aggregateId, aggregateVersion, projectionName và correlationId. Những trường này giúp nối lỗi listener với bản ghi projection. Tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log.

Khi điều tra projection không cập nhật, kiểm tra event đã được phát chưa, publication đến listener có trạng thái gì, listener có được gọi không, projector có ném exception không, transaction có commit không, version guard có bỏ qua event không và query API có đọc đúng projection/index không.

## 14. Checklist thiết kế projection từ event

- Read model phục vụ một hoặc nhiều use case đọc được xác định rõ.
- Event contract có identifier và dữ liệu đủ để cập nhật projection.
- Projection được sở hữu bởi module/query component có trách nhiệm rõ ràng.
- Projector cập nhật read model trong transaction cục bộ.
- Upsert hoặc inbox giúp xử lý event lặp an toàn.
- Aggregate version hoặc sequence bảo vệ projection khỏi event cũ và sai thứ tự.
- API và giao diện chấp nhận eventual consistency hoặc có read-your-writes strategy rõ ràng.
- Các projection khác nhau có projector và chính sách phục hồi phù hợp.
- Event hủy/xóa có identifier và quy tắc cập nhật read model.
- Rebuild dùng nguồn lịch sử hoặc backfill đầy đủ; không coi Publication Registry là event store.
- Integration test bao phủ commit, rollback, duplicate, ordering, retry và rebuild.
- Dashboard theo dõi độ trễ, lỗi và checkpoint của từng projection.

Projection từ event giúp tách mô hình ghi nghiệp vụ khỏi cấu trúc dữ liệu phục vụ truy vấn. Khi event có hợp đồng ổn định, projector idempotent, thứ tự được kiểm soát và read model có chiến lược rebuild rõ ràng, các module có thể cung cấp trải nghiệm đọc nhanh mà vẫn giữ ranh giới sở hữu dữ liệu và khả năng phục hồi của giao tiếp bằng application events.
