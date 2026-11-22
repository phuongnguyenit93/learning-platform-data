# Thử lại sau xung đột bằng cách nạp lại và đánh giá lại nghiệp vụ

Trong một hệ thống Domain-Driven Design, xung đột đồng thời là tín hiệu cho biết quyết định nghiệp vụ được tạo trên một trạng thái đã cũ. Khi một thao tác ghi bị từ chối vì phiên bản của Aggregate đã thay đổi, cách xử lý an toàn là nạp lại Aggregate mới nhất rồi đánh giá lại cùng yêu cầu nghiệp vụ trên trạng thái mới.

Điểm quan trọng nằm ở cụm từ **đánh giá lại nghiệp vụ**. Retry không có nghĩa là lấy Aggregate cũ và gửi lại câu lệnh ghi. Aggregate cũ chứa các giả định đã hết hiệu lực. Nếu trạng thái mới vẫn thỏa invariant thì thao tác có thể được thực hiện lại; nếu invariant không còn đúng, lần thử lại phải kết thúc bằng một kết quả nghiệp vụ phù hợp.

Bài học này thuộc phạm vi Domain-Driven Design, nơi Aggregate là ranh giới nhất quán cho các quy tắc cần được bảo vệ cùng nhau. Cơ chế đồng thời giúp phát hiện việc trạng thái đã thay đổi; chính mô hình domain quyết định sau đó thao tác có còn hợp lệ hay không.

## 1. Xung đột đồng thời xuất hiện ở đâu?

Hãy xét một Aggregate quản lý tồn kho.

Tại phiên bản 12, kho còn 10 sản phẩm. Hai yêu cầu đồng thời cùng đọc Aggregate:

    Kho phiên bản 12
    available = 10

    Yêu cầu A đọc phiên bản 12
    Yêu cầu B đọc phiên bản 12

A muốn giữ 7 sản phẩm. B cũng muốn giữ 7 sản phẩm.

Nếu cả hai chỉ kiểm tra trạng thái đã đọc mà không có cơ chế kiểm soát ghi, cả hai đều thấy 10 >= 7 và có thể cùng ghi kết quả. Khi đó số tồn cuối cùng có thể trở thành 3 trong khi hệ thống đã hứa 7 sản phẩm cho mỗi yêu cầu. Invariant về tồn kho đã bị phá vỡ.

Optimistic concurrency control giải quyết phần phát hiện xung đột bằng một version. Khi A ghi thành công, phiên bản tăng từ 12 lên 13. B vẫn đang giữ phiên bản 12 nên phép ghi với điều kiện "phiên bản hiện tại phải là 12" thất bại.

    A:
      đọc v12 -> reserve(7) -> ghi nếu version = 12 -> thành công -> v13

    B:
      đọc v12 -> reserve(7) -> ghi nếu version = 12 -> xung đột

Xung đột ở đây không phải là kết quả nghiệp vụ cuối cùng. Nó chỉ nói rằng trạng thái mà B dùng để ra quyết định không còn là trạng thái hiện tại.

## 2. Vì sao phải nạp lại trước khi thử lại?

Một Aggregate đã được đọc ở phiên bản cũ có thể chứa nhiều dữ kiện mà lần thử đầu tiên đã dùng:

- số lượng hiện tại;
- trạng thái vòng đời;
- các giới hạn đã tiêu thụ;
- quyền hoặc điều kiện áp dụng tại thời điểm đọc;
- các lựa chọn đã được thực hiện dựa trên dữ liệu cũ;
- các bất biến mà Aggregate phải bảo vệ.

Sau khi một transaction khác commit, bất kỳ dữ kiện nào trong số đó cũng có thể thay đổi.

Nếu B giữ nguyên object đã đọc ở phiên bản 12 rồi chỉ đổi version thành 13 và ghi lại, B đang che giấu xung đột thay vì giải quyết nó. Nếu B gọi lại phương thức trên cùng object cũ, B vẫn đang kiểm tra invariant dựa trên state cũ.

Retry đúng phải tạo một chu kỳ quyết định mới:

    nạp Aggregate mới nhất
        ↓
    đánh giá command trên state mới
        ↓
    nếu hợp lệ → thay đổi state
        ↓
    lưu với expected version mới
        ↓
    nếu lại xung đột → bắt đầu chu kỳ mới

Vì vậy, retry sau optimistic concurrency conflict là một phần của quy trình ra quyết định nghiệp vụ, không chỉ là một vòng lặp ở tầng persistence.

## 3. Ví dụ tồn kho: cùng một command có thể cho kết quả khác

Giả sử command là:

    ReserveStock(productId, quantity = 7)

Ở lần đầu, B nhìn thấy:

    version = 12
    available = 10

Domain method cho phép reserve 7 vì invariant:

    available >= quantity

B giảm tồn từ 10 xuống 3. Nhưng khi ghi, B phát hiện A đã ghi trước.

B phải bỏ kết quả tính toán trên Aggregate cũ và nạp lại:

    version = 13
    available = 3

Sau đó B đánh giá lại chính yêu cầu ReserveStock(7).

Lần này:

    available = 3
    quantity = 7
    3 >= 7 → false

Kết quả đúng là lỗi nghiệp vụ "không đủ tồn", chứ không phải tiếp tục retry cho đến khi ghi được.

Nếu command của B là ReserveStock(2), kết quả lại khác:

    available = 3
    quantity = 2
    3 >= 2 → true

B có thể thực hiện reserve trên Aggregate phiên bản 13 và lưu thành phiên bản 14.

Cùng một cơ chế concurrency nhưng kết quả sau retry phụ thuộc vào trạng thái nghiệp vụ mới. Đó là lý do không được xem conflict như một lỗi kỹ thuật có thể tự động lặp vô hạn.

## 4. Invariant mới là nơi quyết định retry có được tiếp tục hay không

Concurrency control trả lời câu hỏi:

> "Dữ liệu tôi đọc còn là phiên bản mà tôi được phép ghi không?"

Domain model trả lời câu hỏi:

> "Với trạng thái hiện tại, hành động này còn hợp lệ không?"

Hai câu hỏi phải được giữ riêng.

Ví dụ Aggregate tồn kho có các invariant:

| Invariant | Ý nghĩa |
|---|---|
| Số lượng yêu cầu phải lớn hơn 0 | Không tạo reservation vô nghĩa |
| Số lượng khả dụng không âm | Không được bán vượt tồn |
| Reservation chỉ được tạo khi SKU đang bán | Trạng thái vòng đời ảnh hưởng hành vi |
| Mỗi request có idempotency key duy nhất | Retry không tạo reservation trùng |
| Reservation không vượt giới hạn của chính request | Bảo vệ quy tắc nghiệp vụ |

Một conflict có thể xảy ra sau khi một transaction khác làm thay đổi bất kỳ dữ kiện nào liên quan đến các invariant đó. Vì vậy lần retry phải chạy lại toàn bộ logic domain cần thiết.

Không nên chỉ kiểm tra version rồi "replay" phần delta đã tính trên state cũ.

## 5. Mô hình Aggregate nên đặt quy tắc ở đâu?

Aggregate Root nên là nơi kiểm soát các thay đổi có thể phá vỡ invariant bên trong boundary của nó.

Ví dụ Java:

    public final class InventoryItem {
        private final InventoryItemId id;
        private int availableQuantity;

        public InventoryItem(
                InventoryItemId id,
                int availableQuantity
        ) {
            if (availableQuantity < 0) {
                throw new IllegalArgumentException(
                        "availableQuantity must be >= 0"
                );
            }

            this.id = id;
            this.availableQuantity = availableQuantity;
        }

        public void reserve(int quantity) {
            if (quantity <= 0) {
                throw new InvalidReservationQuantity();
            }

            if (availableQuantity < quantity) {
                throw new InsufficientStock(
                        id,
                        quantity,
                        availableQuantity
                );
            }

            availableQuantity -= quantity;
        }

        public int availableQuantity() {
            return availableQuantity;
        }
    }

Phương thức reserve không nhận một "availableQuantity mới" từ application service. Nó nhận ý định nghiệp vụ là reserve một số lượng và tự kiểm tra invariant trên state hiện tại của Aggregate.

Điều này rất quan trọng khi retry. Sau khi nạp lại Aggregate, application service gọi lại cùng hành vi domain:

    inventory.reserve(command.quantity());

Lần đánh giá thứ hai vì vậy dùng dữ liệu mới.

Nếu application service tự tính:

    newAvailable = oldAvailable - quantity

rồi gửi giá trị đó xuống repository, logic retry dễ bị gắn với state cũ. Boundary của Aggregate cũng trở nên yếu hơn vì quy tắc nghiệp vụ bị kéo ra ngoài.

## 6. Version là bằng chứng của state mà quyết định dựa vào

Repository có thể biểu diễn version như một phần của Aggregate snapshot:

    public record InventorySnapshot(
            InventoryItemId id,
            int availableQuantity,
            long version
    ) {}

Khi lưu, repository phải yêu cầu expected version:

    public interface InventoryItemRepository {

        InventoryItem load(InventoryItemId id);

        void save(
                InventoryItem inventory,
                long expectedVersion
        );
    }

Ở tầng persistence, thao tác cập nhật có ý nghĩa tương đương:

    UPDATE inventory
    SET available_quantity = ?,
        version = version + 1
    WHERE id = ?
      AND version = ?

Nếu số dòng bị cập nhật là 0, expected version không còn khớp. Repository chuyển tình huống này thành một lỗi kỹ thuật có ngữ nghĩa rõ ràng, chẳng hạn OptimisticConcurrencyConflict.

Version không phải là một quy tắc nghiệp vụ như "không được bán quá tồn". Nó là bằng chứng để persistence biết rằng state được dùng để quyết định đã bị thay đổi trước khi ghi.

## 7. Luồng retry đầy đủ

Một application service có thể điều phối chu kỳ như sau:

    public ReservationResult reserve(
            ReserveStock command
    ) {
        for (int attempt = 1; attempt <= 3; attempt++) {
            InventoryItem inventory =
                    repository.load(command.productId());

            try {
                inventory.reserve(command.quantity());

                repository.save(
                        inventory,
                        inventory.version()
                );

                return ReservationResult.success(
                        command.productId(),
                        command.quantity()
                );
            } catch (OptimisticConcurrencyConflict conflict) {
                if (attempt == 3) {
                    throw new ConcurrentModification(
                            command.productId()
                    );
                }
            }
        }

        throw new IllegalStateException(
                "unreachable"
        );
    }

Điểm quan trọng của vòng lặp nằm ở vị trí load. Mỗi lần lặp phải nạp Aggregate mới.

Luồng thực tế là:

    attempt 1
      load v12
      evaluate command
      save expected v12
      conflict

    attempt 2
      load v13
      evaluate command again
      save expected v13
      success
      hoặc business rule rejects

Nếu attempt 2 gặp InsufficientStock, exception này không nên được coi là OptimisticConcurrencyConflict. Đây là kết quả của domain logic và phải được chuyển thành kết quả nghiệp vụ thích hợp.

## 8. Không bắt mọi exception để retry

Retry chỉ có ý nghĩa khi nguyên nhân thất bại có khả năng thay đổi sau khi nạp lại state.

| Loại thất bại | Có nên retry theo vòng nạp lại Aggregate? | Lý do |
|---|---|---|
| Optimistic concurrency conflict | Có | State đã thay đổi, cần đánh giá lại |
| Aggregate không tồn tại | Không | Không có state để đánh giá |
| Vi phạm invariant | Không | State hiện tại đã bác bỏ command |
| Command không hợp lệ | Không | Retry không làm input hợp lệ hơn |
| Authorization thất bại | Thường không | Quyền không được tự thay đổi bởi việc ghi lại |
| Database connection timeout | Không cùng loại retry | Đây là transient infrastructure failure |
| Deadlock | Có thể có retry riêng | Cần policy kỹ thuật và transaction mới |
| Duplicate idempotency key | Không tạo thêm tác động | Phải trả lại kết quả đã biết hoặc xử lý theo policy |
| Validation lỗi dữ liệu | Không | Cần sửa input |

Có thể có nhiều lớp retry khác nhau, nhưng chúng không nên bị trộn thành một vòng lặp duy nhất.

Ví dụ database timeout có thể cần retry transaction ở infrastructure layer. Optimistic conflict cần reload Aggregate và chạy lại domain behavior. Hai tình huống có cùng chữ "retry" nhưng mục tiêu khác nhau.

## 9. Conflict retry phải tạo transaction mới

Sau khi transaction phát hiện optimistic conflict, transaction cũ không còn là nơi phù hợp để tiếp tục làm việc.

Một vòng retry nên có ranh giới transaction riêng:

    transaction 1
        load
        domain decision
        conditional write
        conflict
        rollback/end

    transaction 2
        fresh load
        domain decision
        conditional write
        commit

Làm như vậy giúp lần retry nhìn thấy trạng thái mới và không giữ snapshot, session hoặc transaction cũ lâu hơn cần thiết.

Nếu framework ORM đang quản lý persistence context, cần đặc biệt cẩn thận với entity đã trở thành stale. Việc "refresh" một object có thể có ngữ nghĩa khác nhau tùy framework; một thiết kế rõ ràng hơn thường là kết thúc unit of work hiện tại rồi bắt đầu unit of work mới và nạp lại Aggregate.

## 10. Không dùng Aggregate cũ để merge mù quáng

Một kiểu xử lý nguy hiểm là:

    oldAggregate = load(v12)
    oldAggregate.reserve(7)

    conflict

    latest = load(v13)

    latest.setAvailableQuantity(
        oldAggregate.getAvailableQuantity()
    )

Cách này đang coi state đã tính trên v12 là một bản patch có thể áp thẳng lên v13. Nó có thể xóa mất thay đổi hợp lệ của transaction khác.

Cách đúng là giữ lại **ý định nghiệp vụ** và bỏ lại **kết quả tính toán trên state cũ**:

    command = ReserveStock(productId, 7)

    oldAggregate = load(v12)
    oldAggregate.reserve(7)
    conflict

    latest = load(v13)
    latest.reserve(7)

Command là ý định. Aggregate là state dùng để đánh giá ý định. Sau conflict, state phải được thay mới trước khi đánh giá lại.

## 11. Phân biệt command với delta

Sự phân biệt này giúp thiết kế retry dễ hơn.

Một command mô tả điều người dùng hoặc process muốn làm:

    ReserveStock(productId, quantity = 7)

Một delta mô tả kết quả tính toán trên state cụ thể:

    availableQuantity: 10 -> 3

Delta thứ hai phụ thuộc vào phiên bản 12. Nếu state đã chuyển sang phiên bản 13, delta đó có thể không còn hợp lệ.

Vì vậy, application service nên giữ command hoặc một use case request bất biến xuyên suốt retry, còn Aggregate mới được tạo lại ở mỗi attempt.

Có thể hình dung:

    Command
       |
       v
    Aggregate v12
       |
       v
    Domain decision
       |
       v
    Conflict
       |
       +---- bỏ kết quả state v12
       |
       v
    Aggregate v13
       |
       v
    Domain decision lần nữa

Retry như vậy bảo toàn ý định của người gọi nhưng không bảo toàn giả định về state.

## 12. Cẩn thận với các quyết định phụ thuộc thời gian

Re-evaluate không phải lúc nào cũng có nghĩa là chạy lại từng dòng code giống hệt nhau. Nếu domain decision phụ thuộc thời gian, thời gian cần được xác định theo đúng ngữ nghĩa của command.

Ví dụ:

    ReserveStock(
        productId,
        quantity,
        expiresAt
    )

Nếu command có một hạn sử dụng cụ thể, retry nên tiếp tục dùng expiresAt đã được xác định bởi nghiệp vụ.

Ngược lại, nếu rule nói "chỉ cho phép reservation trong giờ mở cửa hiện tại", lần đánh giá lại phải kiểm tra thời gian hiện tại theo clock của domain/application. Một retry sau vài giây có thể cho kết quả khác.

Để kiểm thử được, không nên gọi trực tiếp system clock bên trong Aggregate. Có thể truyền một Clock hoặc một giá trị thời gian đã được xác định ở application boundary, tùy ngữ nghĩa của domain.

## 13. Cẩn thận với external side effects

Retry Aggregate an toàn hơn khi phần thay đổi state được giới hạn trong transaction của Aggregate. Tình hình trở nên khó hơn nếu command vừa sửa Aggregate vừa gọi hệ thống bên ngoài.

Ví dụ:

    reserve inventory
    charge payment
    publish message

Nếu conflict xảy ra sau một side effect bên ngoài, việc chạy lại toàn bộ command có thể tạo duplicate charge hoặc duplicate request.

Vì vậy cần tách hai vấn đề:

1. Retry việc đánh giá và ghi Aggregate.
2. Retry các side effect bên ngoài.

Các side effect cần cơ chế phù hợp như idempotency key, outbox hoặc workflow/process manager tùy bài toán. Không nên giả định rằng một HTTP call hoặc payment request sẽ tự nhiên an toàn khi gọi lại.

Nếu payment đã được chấp nhận nhưng response bị mất, việc gửi lại request có thể tạo giao dịch thứ hai nếu bên nhận không nhận diện được request cũ. Đây là bài toán idempotency, khác với optimistic concurrency của Aggregate.

## 14. Domain Event phải được tạo từ kết quả commit hợp lệ

Giả sử Aggregate tạo event:

    StockReserved

Khi lần đầu gọi reserve trên Aggregate v12, domain có thể tạo event trong bộ nhớ. Nếu save gặp concurrency conflict, event đó không được phát như thể reservation đã thành công.

Luồng an toàn là:

    load v12
       ↓
    reserve(7)
       ↓
    tạo event trong unit of work
       ↓
    save -> conflict
       ↓
    bỏ unit of work và event chưa commit
       ↓
    load v13
       ↓
    reserve(7)
       ↓
    save -> thành công
       ↓
    commit event của lần thành công

Nếu sử dụng outbox, bản ghi outbox cũng phải thuộc cùng transaction với Aggregate update. Một event chỉ nên được đưa vào outbox khi lần ghi Aggregate tương ứng đã commit thành công.

Điều này ngăn event của một attempt thất bại đi ra ngoài hệ thống.

## 15. Idempotency vẫn cần thiết

Optimistic concurrency không tự giải quyết duplicate command.

Giả sử người dùng bấm nút "Đặt hàng" hai lần. Hai request có thể có cùng ý định nghiệp vụ nhưng khác transaction. Nếu command được xử lý hai lần tuần tự, mỗi lần đều có thể hợp lệ.

Một idempotency key giúp domain/application phân biệt:

    reservationRequestId = R-123

Request đầu tiên với R-123 thành công. Request thứ hai với cùng R-123 không nên tạo reservation thứ hai chỉ vì application service đang retry hoặc client gửi lại.

Có thể lưu mapping:

    idempotencyKey -> outcome

Khi request đến lại:

- nếu key đã hoàn tất, trả lại outcome đã lưu;
- nếu key đang được xử lý, áp dụng cơ chế đồng bộ phù hợp;
- nếu key chưa từng thấy, bắt đầu xử lý.

Idempotency và optimistic concurrency bổ sung cho nhau:

| Cơ chế | Bảo vệ điều gì? |
|---|---|
| Version / optimistic concurrency | Không ghi đè state đã thay đổi bởi transaction khác |
| Domain invariant | Không cho state rơi vào trạng thái nghiệp vụ không hợp lệ |
| Idempotency key | Không xử lý cùng một ý định nhiều lần |
| Transaction | Giữ các thay đổi trong một unit of work nguyên tử |
| Outbox | Giữ việc phát integration event nhất quán với commit |

## 16. Giới hạn số lần retry

Conflict có thể liên tục xảy ra khi một Aggregate có mức cạnh tranh cao.

Ví dụ một SKU rất phổ biến:

    A -> conflict
    B -> conflict
    C -> conflict
    D -> conflict
    ...

Nếu không có giới hạn, một request có thể giữ tài nguyên rất lâu.

Thường nên có một retry budget rõ ràng:

    MAX_ATTEMPTS = 3

Sau khi hết số lần thử, trả về một kết quả kỹ thuật như ConcurrentModification hoặc để tầng ứng dụng quyết định phản hồi phù hợp.

Số lần retry không nên được chọn chỉ vì "nhiều hơn sẽ an toàn hơn". Mỗi lần retry đều phải nạp lại dữ liệu, chạy domain logic và thực hiện persistence. Trong hệ thống có contention cao, retry quá nhiều có thể làm tăng contention thay vì giảm nó.

## 17. Backoff chỉ giải quyết một phần bài toán

Nếu nhiều request cùng xung đột, tất cả cùng retry ngay lập tức có thể tạo thêm một đợt cạnh tranh mới.

Một policy kỹ thuật có thể dùng backoff và jitter giữa các attempt. Tuy nhiên backoff không thay thế việc reload và re-evaluate.

Trình tự vẫn phải là:

    conflict
       ↓
    kết thúc transaction hiện tại
       ↓
    chờ theo retry policy nếu cần
       ↓
    load state mới
       ↓
    evaluate domain command
       ↓
    conditional save

Backoff thuộc infrastructure/application policy. Quy tắc "có được reserve hay không" vẫn thuộc domain.

## 18. Khi nào không nên retry?

Không phải mọi conflict đều đáng retry tự động.

Có thể không retry hoặc yêu cầu người dùng xác nhận lại nếu:

- command phụ thuộc vào một lựa chọn mà người dùng đã xem trên UI và lựa chọn đó không còn đúng;
- thay đổi mới làm giá, hạn mức hoặc điều kiện hợp đồng thay đổi;
- hành động có side effect không thể đảo ngược;
- domain yêu cầu người dùng đưa ra quyết định mới khi dữ liệu thay đổi;
- Aggregate có contention quá cao;
- command đã hết hạn;
- số lần retry vượt budget.

Ví dụ người dùng xác nhận mua sản phẩm với giá 100.000 đồng. Trong lúc request chờ xử lý, giá thay đổi thành 120.000 đồng. Nạp lại Aggregate rồi tự động mua ở giá mới có thể đúng về mặt kỹ thuật nhưng sai về mặt nghiệp vụ. Retry lúc này phải dừng và yêu cầu một quyết định mới.

Điều này cho thấy "re-evaluate" không đồng nghĩa với "luôn làm lại". Nó có thể dẫn đến:

    ACCEPT
    REJECT
    REQUIRE_NEW_DECISION
    RETRY

## 19. Một thiết kế rõ ràng cho kết quả re-evaluate

Thay vì dùng exception cho mọi trường hợp, application layer có thể biểu diễn kết quả domain một cách rõ ràng:

    public sealed interface ReservationDecision
            permits ReservationApproved,
                    ReservationRejected,
                    ReservationRequiresConfirmation {
    }

    public record ReservationApproved(
            int quantity
    ) implements ReservationDecision {
    }

    public record ReservationRejected(
            String reason
    ) implements ReservationDecision {
    }

    public record ReservationRequiresConfirmation(
            String reason
    ) implements ReservationDecision {
    }

Sau khi reload, Aggregate hoặc domain service có thể trả về quyết định phù hợp.

Optimistic conflict chỉ làm application service quay lại bước load. Nó không quyết định kết quả domain.

## 20. Một phiên bản application service hoàn chỉnh hơn

Có thể tách việc thực hiện một attempt thành một unit of work:

    public ReservationResult reserve(
            ReserveStock command
    ) {
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return transaction.execute(
                        () -> reserveOnce(command)
                );
            } catch (OptimisticConcurrencyConflict conflict) {
                if (attempt == maxAttempts) {
                    throw new ConcurrentModification(
                            command.productId()
                    );
                }

                retryPolicy.pauseBeforeNextAttempt(attempt);
            }
        }

        throw new IllegalStateException("unreachable");
    }

    private ReservationResult reserveOnce(
            ReserveStock command
    ) {
        InventoryItem inventory =
                repository.load(command.productId());

        inventory.reserve(command.quantity());

        repository.save(
                inventory,
                inventory.version()
        );

        return ReservationResult.success(
                command.productId(),
                command.quantity()
        );
    }

Điểm thiết kế quan trọng là transaction bao quanh cả load, domain decision và conditional save của một attempt.

Khi conflict xảy ra, transaction kết thúc. Attempt tiếp theo bắt đầu với repository load mới.

## 21. Test đúng bản chất của retry

Một unit test hữu ích không chỉ kiểm tra rằng exception được bắt. Nó phải chứng minh rằng Aggregate được nạp lại và invariant được đánh giá trên state mới.

Có thể mô phỏng:

    lần load 1:
        version = 12
        available = 10

    save lần 1:
        OptimisticConcurrencyConflict

    lần load 2:
        version = 13
        available = 3

    domain:
        reserve(7)

    kết quả:
        InsufficientStock

Test này bảo vệ một hành vi quan trọng: retry không được sử dụng state cũ.

Một test khác kiểm tra trường hợp retry thành công:

    lần load 1:
        version = 12
        available = 10

    save lần 1:
        conflict

    lần load 2:
        version = 13
        available = 10

    reserve(7)

    save lần 2:
        success

    kết quả:
        reservation thành công

Cũng nên kiểm tra rằng save lần hai sử dụng expected version của lần load thứ hai, không phải version của lần đầu.

## 22. Test tránh lỗi "replay stale state"

Có một lỗi rất dễ lọt qua nếu test chỉ kiểm tra số lần gọi repository.

Giả sử developer viết:

    load v12
    reserve(7)
    conflict
    load v13
    copy kết quả từ v12 sang v13
    save v13

Test có thể vẫn thấy "load hai lần" và "save hai lần", nhưng behavior vẫn sai.

Một test tốt phải thay đổi state giữa hai lần load:

    lần 1: available = 10
    lần 2: available = 3

Sau đó yêu cầu reserve 7 phải thất bại với InsufficientStock.

Nếu code vẫn thành công, test đã phát hiện việc retry đang replay stale calculation.

## 23. Aggregate boundary ảnh hưởng trực tiếp đến conflict

Aggregate càng lớn, càng nhiều thay đổi không liên quan có thể làm tăng conflict cho cùng một write.

Ví dụ nếu toàn bộ Order, CustomerProfile, PaymentPreferences và ShippingHistory nằm trong một Aggregate, một thay đổi nhỏ ở ShippingHistory có thể làm version của toàn bộ Aggregate tăng. Một thao tác khác đang cập nhật OrderLine vì vậy có thể bị conflict dù hai thay đổi nghiệp vụ không thực sự cần nhất quán cùng nhau.

Thiết kế Aggregate cần xác định đúng invariant cần bảo vệ cùng nhau.

Có thể tự hỏi:

- Những dữ liệu nào phải nhất quán trong cùng một transaction?
- Command này cần đọc những state nào để quyết định?
- Nếu một phần state thay đổi, quyết định có phải được tính lại không?
- Những thay đổi nào có thể tách thành Aggregate khác?
- Conflict trên Aggregate này có đang xảy ra quá thường xuyên không?

Nếu conflict quá nhiều, đừng chỉ tăng số lần retry. Có thể vấn đề nằm ở Aggregate boundary.

## 24. Retry và consistency giữa nhiều Aggregate

Một transaction có thể cần nhiều Aggregate. Khi đó việc retry phức tạp hơn vì có thể có nhiều version.

Ví dụ:

    Order v8
    Inventory v12

Command đặt hàng cần cập nhật cả hai.

Nếu hệ thống cần thay đổi cả hai trong một transaction nguyên tử, application service phải bảo đảm consistency theo thiết kế transaction của hệ thống. Nếu một Aggregate conflict, không nên tự ý commit phần còn lại rồi retry riêng mà không có mô hình bù trừ hoặc quy trình phù hợp.

DDD khuyến khích giữ Aggregate nhỏ và bảo vệ invariant trong boundary của từng Aggregate. Khi business process cần phối hợp nhiều Aggregate, có thể dùng domain service, application service, process manager hoặc saga tùy yêu cầu consistency.

Điểm cốt lõi vẫn giữ nguyên: mỗi Aggregate được nạp lại trước khi đánh giá lại những quy tắc mà nó sở hữu.

## 25. Eventual consistency không làm mất nhu cầu re-evaluate

Trong hệ thống phân tán, một read model có thể chưa phản ánh ngay state mới. Nếu command dùng dữ liệu stale từ read model để quyết định một invariant quan trọng, chỉ retry dựa trên read model đó có thể không đủ.

Invariant cần bảo vệ phải được kiểm tra tại nơi có authority cho state đó.

Ví dụ:

    UI read model:
        available = 10

    command:
        reserve 7

    write-side Aggregate:
        available = 3

Nếu write-side Aggregate là nguồn có thẩm quyền, nó mới có thể quyết định reserve 7 còn hợp lệ hay không.

Read model có thể dùng để hiển thị hoặc hỗ trợ quyết định, nhưng không nên được coi là bằng chứng cuối cùng cho invariant mà write side chịu trách nhiệm bảo vệ.

## 26. Quan sát retry để tìm contention thật

Concurrency conflict là một tín hiệu vận hành hữu ích.

Có thể ghi nhận:

| Metric | Ý nghĩa |
|---|---|
| conflict count | Có bao nhiêu attempt thất bại vì version |
| retry success rate | Bao nhiêu conflict cuối cùng retry thành công |
| retry exhaustion | Bao nhiêu request hết retry budget |
| conflicts per Aggregate type | Aggregate nào chịu contention cao |
| attempts per successful command | Một command trung bình cần bao nhiêu attempt |
| business rejection after conflict | Conflict thường dẫn đến reject hay vẫn thành công |

Nếu một Aggregate thường xuyên cần 3 hoặc 4 attempt, vấn đề có thể nằm ở tải, partitioning hoặc Aggregate boundary.

Log cũng nên ghi correlation id và aggregate id, nhưng tránh ghi dữ liệu nhạy cảm không cần thiết. Một log hữu ích có thể cho biết:

    aggregateType = InventoryItem
    aggregateId = SKU-42
    attempt = 2
    expectedVersion = 13
    outcome = INSUFFICIENT_STOCK_AFTER_CONFLICT

Thông tin này giúp phân biệt "retry thất bại vì contention" với "retry thất bại vì business rule".

## 27. Những sai lầm thường gặp

### Sai lầm 1: Retry trên cùng object

    catch (OptimisticConcurrencyConflict e) {
        repository.save(aggregate, aggregate.version());
    }

Object vẫn chứa state cũ. Đây không phải re-evaluate.

### Sai lầm 2: Chỉ reload version

    aggregate.setVersion(latestVersion);

Đổi version không làm state bên trong Aggregate trở thành state mới.

### Sai lầm 3: Copy delta cũ vào Aggregate mới

Delta được tính từ state cũ có thể không còn hợp lệ.

### Sai lầm 4: Retry cả business exception

Nếu Aggregate nói "không đủ tồn", retry ngay lập tức không làm tồn kho tăng.

### Sai lầm 5: Retry vô hạn

Contention có thể kéo dài và làm hệ thống tự tạo thêm tải.

### Sai lầm 6: Phát domain event trước commit

Attempt bị conflict nhưng event vẫn có thể bị gửi ra ngoài.

### Sai lầm 7: Trộn database retry với domain retry

Database timeout, deadlock và optimistic conflict có nguyên nhân khác nhau. Chúng cần policy riêng.

### Sai lầm 8: Bỏ qua idempotency

Retry có thể khiến cùng một request tạo side effect nhiều lần nếu side effect không được nhận diện bằng idempotency key.

### Sai lầm 9: Aggregate quá lớn

Conflict cao có thể là triệu chứng của boundary sai.

### Sai lầm 10: Tự động chấp nhận state mới

Một số nghiệp vụ yêu cầu người dùng xác nhận lại khi giá, quyền hoặc điều kiện đã thay đổi. Không phải command nào cũng có thể tự động tiếp tục.

## 28. Công thức thiết kế có thể nhớ

Một retry an toàn sau optimistic concurrency conflict có thể được mô tả ngắn gọn:

    intent + fresh state + domain rules = new decision

Trong đó:

- **intent** là command hoặc ý định nghiệp vụ ban đầu;
- **fresh state** là Aggregate được nạp lại sau conflict;
- **domain rules** là invariant và behavior của domain;
- **new decision** là kết quả mới: thành công, từ chối, yêu cầu quyết định mới hoặc một conflict khác.

Không nên dùng:

    old state + old decision + new version = retry

Công thức thứ hai chỉ làm thay đổi metadata của một quyết định đã cũ.

## 29. Checklist triển khai

Trước khi triển khai retry sau optimistic conflict, có thể kiểm tra:

- Aggregate có version hoặc cơ chế phát hiện concurrent modification không?
- Persistence có conditional write theo expected version không?
- Conflict có được phân biệt với business exception không?
- Sau conflict, transaction hiện tại có kết thúc không?
- Attempt mới có nạp Aggregate mới không?
- Command gốc có được giữ bất biến không?
- Domain method có chạy lại trên state mới không?
- Invariant có được kiểm tra lại đầy đủ không?
- Save lần retry có dùng version mới không?
- Có retry budget không?
- Có backoff khi contention cao không?
- Domain event chỉ được commit cùng state thành công không?
- Side effect bên ngoài có idempotency không?
- Aggregate có quá lớn khiến conflict tăng không?
- Test có thay đổi state giữa lần load thứ nhất và thứ hai không?
- Có metric để quan sát conflict và retry không?
- Có nghiệp vụ nào cần yêu cầu người dùng quyết định lại khi state thay đổi không?

## 30. Kết luận

Thử lại sau xung đột đồng thời là một vòng ra quyết định mới. Version giúp hệ thống phát hiện rằng quyết định cũ được tạo trên state đã lỗi thời; Aggregate và domain behavior quyết định liệu ý định ban đầu còn hợp lệ trên state mới.

Một thiết kế tốt giữ ba thứ tách biệt:

    Command
      = người dùng muốn làm gì

    Aggregate state
      = hiện tại domain đang ở đâu

    Domain behavior
      = với state hiện tại, việc đó có được phép không

Khi conflict xảy ra, giữ lại command, bỏ kết quả tính toán trên state cũ, nạp lại Aggregate và chạy lại domain behavior. Nếu invariant còn đúng, commit phiên bản mới. Nếu invariant không còn đúng, trả kết quả nghiệp vụ tương ứng. Nếu thay đổi đã làm quyết định mất ý nghĩa, yêu cầu một quyết định mới.

Đó là cách optimistic concurrency trở thành một phần rõ ràng của mô hình nghiệp vụ thay vì một vòng lặp ghi dữ liệu ở tầng persistence.
