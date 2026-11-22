# Khóa bi quan: điều kiện sử dụng và chi phí

Trong Domain-Driven Design (DDD), Aggregate bảo vệ những bất biến nghiệp vụ cần được duy trì khi một hành động hoàn tất. Tuy nhiên, việc kiểm tra invariant trong bộ nhớ chưa đủ nếu nhiều giao dịch có thể cùng đọc và thay đổi một dữ liệu. Hai yêu cầu đồng thời có thể đều thấy trạng thái hợp lệ, cùng vượt qua kiểm tra rồi ghi kết quả khiến trạng thái cuối cùng vi phạm quy tắc.

**Khóa bi quan (pessimistic locking)** là cách kiểm soát đồng thời trong đó một giao dịch giành quyền khóa dữ liệu trước khi đọc hoặc thay đổi nó. Giao dịch cạnh tranh phải chờ, bị từ chối hoặc bỏ qua tài nguyên tùy cơ chế được chọn. Cách này hữu ích khi xung đột xảy ra thường xuyên, tài nguyên khan hiếm và invariant cần được quyết định ngay tại một điểm ghi nhận.

Khóa bi quan cũng có chi phí: giao dịch phải giữ khóa trong một khoảng thời gian, các yêu cầu khác có thể bị chặn, throughput giảm khi cạnh tranh cao và hệ thống có thể gặp deadlock hoặc timeout. Vì vậy, quyết định dùng khóa cần dựa trên mức độ tranh chấp, thời gian giao dịch, hậu quả của xung đột và khả năng dùng một cơ chế khác như optimistic locking, cập nhật có điều kiện hoặc reservation.

## 1. Khóa bi quan là gì?

Khóa bi quan giả định rằng xung đột có khả năng xảy ra và cần được ngăn chặn trước khi một giao dịch thay đổi dữ liệu. Một transaction yêu cầu khóa một hoặc nhiều hàng dữ liệu; khi khóa được cấp, transaction có thể đọc trạng thái cần thiết, kiểm tra điều kiện, cập nhật và commit. Giao dịch khác muốn lấy khóa xung đột phải đợi cho đến khi khóa được giải phóng hoặc nhận kết quả timeout/deadlock.

Trong cơ sở dữ liệu quan hệ, cách dùng phổ biến là đọc hàng với `SELECT ... FOR UPDATE`. Câu lệnh này yêu cầu database khóa các hàng được chọn theo ngữ nghĩa của hệ quản trị cơ sở dữ liệu. Sau khi transaction commit hoặc rollback, khóa giao dịch được giải phóng.

Ví dụ, một kho có 5 sản phẩm khả dụng. Hai đơn hàng cùng yêu cầu giữ 4 sản phẩm. Nếu cả hai giao dịch chỉ đọc số lượng mà không khóa hoặc dùng cơ chế cập nhật nguyên tử, chúng có thể cùng thấy 5 và cùng xác nhận. Với khóa bi quan trên hàng tồn kho, giao dịch đầu tiên lấy khóa và xử lý; giao dịch thứ hai phải đợi. Sau khi giao dịch đầu tiên commit, giao dịch thứ hai đọc lại trạng thái mới và thấy chỉ còn 1 sản phẩm khả dụng.

### 1.1. Khóa là cơ chế phối hợp giữa các giao dịch

Khóa bi quan không thay thế invariant trong domain model. Aggregate vẫn cần kiểm tra điều kiện nghiệp vụ, chẳng hạn số lượng yêu cầu phải dương và lượng giữ không được vượt tồn khả dụng. Database lock bổ sung cơ chế để các giao dịch cạnh tranh không cùng đưa ra quyết định dựa trên một trạng thái cũ.

Có thể phân biệt:

- **Domain rule:** điều gì được phép xảy ra theo nghiệp vụ.
- **Aggregate behavior:** nơi kiểm tra và thực hiện quy tắc trong mô hình miền.
- **Transaction:** phạm vi các thay đổi dữ liệu được commit hoặc rollback cùng nhau.
- **Lock:** cơ chế điều phối truy cập cạnh tranh trong thời gian transaction hoạt động.

Một thiết kế đúng thường cần cả quy tắc miền và cơ chế lưu trữ phù hợp. Chỉ thêm `FOR UPDATE` mà không kiểm tra điều kiện nghiệp vụ vẫn có thể cho phép một hành động sai; chỉ kiểm tra trong Java mà không kiểm soát ghi đồng thời vẫn có thể tạo race condition.

## 2. Cách khóa bi quan xử lý tranh chấp

Xét invariant tồn kho:

\[
available = onHand - reserved
\]

với điều kiện:

\[
onHand \geq 0,\quad reserved \geq 0,\quad reserved \leq onHand
\]

Giả sử `onHand = 5`, `reserved = 0`. Hai transaction A và B đều muốn giữ 4 đơn vị.

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: SELECT stock FOR UPDATE
    DB-->>A: onHand=5, reserved=0 (lock granted)
    B->>DB: SELECT stock FOR UPDATE
    Note over B,DB: B waits for A's lock
    A->>DB: UPDATE reserved=4
    A->>DB: COMMIT
    DB-->>B: Lock granted after A commits
    DB-->>B: Read latest state: reserved=4
    B->>B: available=1; requested=4 is rejected
    B->>DB: ROLLBACK
```

Điểm quan trọng là transaction B phải đánh giá lại trạng thái sau khi lấy được khóa. Không được đọc trước khi khóa rồi sử dụng giá trị cũ sau thời gian chờ. Thứ tự đúng là lấy khóa, đọc dữ liệu đã được bảo vệ, kiểm tra invariant, cập nhật và kết thúc transaction.

## 3. Các loại khóa thường gặp

Tên gọi và ngữ nghĩa chi tiết phụ thuộc vào database, driver và ORM. Một số khái niệm phổ biến:

| Loại khóa | Mục đích khái quát | Ghi chú |
|---|---|---|
| Shared/read lock | Cho phép nhiều giao dịch cùng đọc theo cơ chế khóa, hạn chế ghi xung đột | Cách tương tác với các loại khóa khác tùy hệ quản trị |
| Exclusive/write lock | Bảo vệ dữ liệu đang được ghi | Giao dịch khác muốn ghi thường phải chờ |
| Row-level lock | Khóa hàng được chọn | Giảm phạm vi chặn so với khóa bảng khi truy vấn phù hợp |
| Table-level lock | Khóa phạm vi bảng | Có thể chặn nhiều thao tác không liên quan |
| Predicate/range/gap lock | Bảo vệ một điều kiện hoặc khoảng khóa | Có thể liên quan đến isolation level và cách database thực thi truy vấn |
| Advisory lock | Khóa theo một khóa logic do ứng dụng quy ước | Thường đặc thù database; ứng dụng phải thống nhất giao thức sử dụng |

Với ứng dụng nghiệp vụ, `SELECT ... FOR UPDATE` thường được dùng để lấy khóa ghi trên các hàng cụ thể. Không nên suy luận rằng mọi database đều khóa giống nhau. Một số hệ thống dùng MVCC, một số dùng khóa theo phạm vi khác nhau; isolation level, chỉ mục và câu truy vấn có thể làm thay đổi tập dữ liệu bị khóa.

## 4. Khi nào nên dùng khóa bi quan?

Khóa bi quan phù hợp khi có đủ lý do để ưu tiên tuần tự hóa các thao tác cạnh tranh trên cùng tài nguyên.

### 4.1. Tỷ lệ xung đột cao

Nếu nhiều người dùng hoặc tiến trình thường xuyên cập nhật cùng một hàng hay cùng một tài nguyên, optimistic locking có thể gây nhiều lần thất bại và retry. Khóa bi quan có thể giúp tuần tự hóa từ đầu, tránh nhiều transaction cùng thực hiện tính toán rồi mới phát hiện xung đột.

Ví dụ:

- Nhiều đơn cùng giữ những đơn vị cuối cùng của một SKU tại cùng kho.
- Nhiều nhân viên cùng xử lý một hồ sơ đang chờ phê duyệt.
- Nhiều lệnh cùng cập nhật hạn mức hoặc số dư của một tài khoản.
- Nhiều worker cùng nhận một công việc cần được xử lý bởi một worker tại một thời điểm.

Tỷ lệ xung đột cần được đo từ dữ liệu thực tế như số lần optimistic conflict, lock wait, deadlock, timeout và số yêu cầu đồng thời trên cùng khóa.

### 4.2. Tài nguyên khan hiếm và hậu quả sai lệch cao

Khi một tài nguyên chỉ có số lượng hữu hạn, hai giao dịch cùng xác nhận có thể gây bán vượt, cấp phát vượt hoặc sử dụng trùng. Nếu hậu quả nghiệp vụ lớn và cần quyết định ngay, khóa trên tài nguyên có thẩm quyền là một lựa chọn đáng cân nhắc.

Ví dụ: giữ ghế cuối cùng trên chuyến bay, đặt phòng cuối cùng, giữ hàng tồn kho hoặc phân bổ một hạn mức còn lại. Cần xác định đúng hàng hoặc khóa logic đại diện cho tài nguyên cần bảo vệ.

### 4.3. Giao dịch ngắn và có phạm vi khóa rõ

Khóa bi quan hiệu quả hơn khi transaction:

- Thực hiện nhanh và kết thúc trong thời gian ngắn.
- Chỉ khóa số lượng hàng nhỏ, có chỉ mục phù hợp.
- Không chờ người dùng nhập liệu.
- Không gọi API hoặc dịch vụ mạng chậm trong khi giữ khóa.
- Có thứ tự lấy khóa nhất quán nếu phải khóa nhiều hàng.

Một transaction ngắn giúp giảm thời gian các giao dịch khác phải chờ và giảm xác suất deadlock.

### 4.4. Cần tuần tự hóa một quyết định nghiệp vụ

Đôi khi điều quan trọng không chỉ là phát hiện xung đột mà là bảo đảm các quyết định được đưa ra lần lượt trên trạng thái mới nhất. Khóa bi quan làm rõ điểm tuần tự hóa: giao dịch nào lấy khóa trước sẽ xử lý trước trong phạm vi cơ chế database cung cấp. Tuy nhiên, không nên giả định thứ tự chờ luôn công bằng hoặc phản ánh đúng thứ tự nghiệp vụ; nếu thứ tự ưu tiên quan trọng, cần mô hình hóa nó riêng.

## 5. Khi nào không nên dùng khóa bi quan?

Khóa bi quan thường không phù hợp khi:

- Xung đột hiếm và optimistic locking có tỷ lệ thành công cao.
- Giao dịch kéo dài hoặc cần người dùng xác nhận sau nhiều phút.
- Hệ thống có nhiều request đọc nhưng ít cập nhật.
- Một thao tác cần gọi dịch vụ ngoài hoặc chờ message trong lúc transaction đang mở.
- Một hàng nóng bị hàng trăm hoặc hàng nghìn request cùng khóa, tạo hàng đợi dài.
- Quy tắc thực tế cho phép xử lý bất đồng bộ qua reservation, event hoặc compensation.
- Không thể xác định rõ dữ liệu cần khóa hoặc mọi đường ghi không tuân theo cùng một giao thức.

Không nên giữ khóa database trong lúc khách hàng điền biểu mẫu, chờ xác nhận thanh toán, gọi đơn vị vận chuyển hoặc chờ một hệ thống bên ngoài phản hồi. Thay vào đó, hãy tạo trạng thái reservation hoặc pending có thời hạn, commit nhanh rồi tiếp tục quy trình ở bước khác.

## 6. Ví dụ SQL: giữ hàng bằng SELECT FOR UPDATE

Giả sử bảng `stock_item` có một hàng cho mỗi cặp SKU và địa điểm:

```sql
CREATE TABLE stock_item (
    sku             VARCHAR(64) NOT NULL,
    location_id     VARCHAR(64) NOT NULL,
    on_hand         INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved        INTEGER NOT NULL CHECK (reserved >= 0),
    PRIMARY KEY (sku, location_id),
    CHECK (reserved <= on_hand)
);
```

Transaction giữ hàng có thể được triển khai theo trình tự sau. Cú pháp `FOR UPDATE` phổ biến trong PostgreSQL và nhiều hệ quản trị quan hệ khác, nhưng chi tiết khóa và cú pháp có thể khác giữa các hệ thống.

```sql
BEGIN;

SELECT on_hand, reserved
FROM stock_item
WHERE sku = :sku
  AND location_id = :location_id
FOR UPDATE;

-- Ứng dụng kiểm tra quantity > 0 và
-- quantity <= on_hand - reserved trên hàng vừa khóa.

UPDATE stock_item
SET reserved = reserved + :quantity
WHERE sku = :sku
  AND location_id = :location_id;

INSERT INTO stock_reservation (
    reservation_id, sku, location_id, quantity, status
)
VALUES (
    :reservation_id, :sku, :location_id, :quantity, 'ACTIVE'
);

COMMIT;
```

Trong triển khai thực tế, ứng dụng chỉ chạy `UPDATE` và `INSERT` nếu kiểm tra số lượng thành công. Nếu không đủ hàng, transaction rollback hoặc kết thúc mà không ghi thay đổi. `stock_item` và `stock_reservation` phải được cập nhật trong cùng transaction database nếu invariant phụ thuộc vào cả hai. Nếu chúng nằm ở các resource độc lập, cần thiết kế cơ chế nhất quán khác.

### 6.1. Vì sao cần khóa trước khi đọc?

Nếu đọc `on_hand` và `reserved` bằng một truy vấn bình thường rồi mới lấy khóa, một giao dịch khác có thể thay đổi dữ liệu trong khoảng giữa hai bước. Khi đó ứng dụng đang kiểm tra trên snapshot cũ.

Thứ tự an toàn cho mẫu này là:

1. Bắt đầu transaction.
2. Lấy khóa trên hàng tồn kho đại diện cho tài nguyên.
3. Đọc trạng thái sau khi khóa được cấp.
4. Kiểm tra invariant.
5. Cập nhật tồn và ghi reservation.
6. Commit nhanh để giải phóng khóa.

### 6.2. Nếu hàng tồn kho chưa tồn tại thì sao?

`SELECT ... FOR UPDATE` không thể khóa một hàng chưa tồn tại theo cách thông thường. Hai transaction có thể cùng không tìm thấy hàng rồi cùng cố tạo mới. Cần bảo vệ trường hợp này bằng một cơ chế phù hợp, chẳng hạn:

- Unique constraint trên `(sku, location_id)` để ngăn tạo bản ghi trùng.
- `INSERT ... ON CONFLICT` hoặc cơ chế upsert phù hợp với database.
- Khóa một hàng cha hoặc một khóa logic đã tồn tại.
- Advisory lock theo khóa SKU/địa điểm nếu database hỗ trợ và mọi writer tuân thủ cùng quy ước.
- Isolation level và range/gap locking phù hợp nếu database cung cấp ngữ nghĩa đó.

Không nên giả định rằng một câu `SELECT FOR UPDATE` không trả hàng đã khóa được “khoảng trống” nơi hàng sẽ được tạo. Hành vi với predicate và gap phụ thuộc hệ quản trị, chỉ mục và isolation level.

## 7. Ví dụ Spring Data JPA

Trong ứng dụng Java dùng Spring Data JPA, repository có thể yêu cầu khóa ghi khi truy vấn Aggregate:

```java
public interface StockItemRepository
        extends JpaRepository<StockItemEntity, StockItemId> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select s
        from StockItemEntity s
        where s.id.sku = :sku
          and s.id.locationId = :locationId
        """)
    Optional<StockItemEntity> findForUpdate(
            String sku,
            String locationId
    );
}
```

Application service mở transaction và giữ transaction trong suốt quá trình đọc, kiểm tra và lưu:

```java
@Service
public class ReserveStockHandler {
    private final StockItemRepository repository;

    public ReserveStockHandler(StockItemRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void handle(ReserveStockCommand command) {
        StockItemEntity stock = repository.findForUpdate(
                command.sku(), command.locationId())
            .orElseThrow(StockItemNotFoundException::new);

        if (command.quantity() <= 0) {
            throw new InvalidQuantityException();
        }

        int available = stock.getOnHand() - stock.getReserved();
        if (command.quantity() > available) {
            throw new InsufficientStockException();
        }

        stock.setReserved(stock.getReserved() + command.quantity());
        repository.save(stock);
    }
}
```

Ví dụ minh họa cách lấy khóa và giữ transaction; một ứng dụng DDD hoàn chỉnh nên ánh xạ dữ liệu thành Aggregate domain, gọi hành vi `reserve`, rồi lưu qua repository thay vì để application service tự sửa field của entity persistence. Việc đặt `@Transactional` ở đúng boundary cũng quan trọng: transaction phải còn hoạt động khi truy vấn khóa được thực thi và cho đến khi thay đổi được commit.

### 7.1. Khóa trong JPA không có nghĩa mọi thao tác đều bị khóa

`PESSIMISTIC_WRITE` yêu cầu provider/JPA lấy khóa ghi phù hợp với database. Hành vi cụ thể phụ thuộc dialect, provider và database. Một truy vấn khác không yêu cầu khóa có thể vẫn đọc được dữ liệu theo MVCC ở một số hệ quản trị, nhưng việc ghi xung đột thường phải chờ hoặc thất bại. Cần kiểm tra hành vi trên database thực tế, không chỉ dựa vào unit test với mock.

### 7.2. Timeout khóa

JPA có thể truyền hint như `jakarta.persistence.lock.timeout`, nhưng cách diễn giải và mức hỗ trợ tùy provider/database. Hãy xác định rõ ứng dụng muốn chờ bao lâu, nhận lỗi gì khi hết thời gian và có retry hay trả lỗi tạm thời cho caller.

Không đặt timeout quá dài chỉ để tránh lỗi hiển thị. Thời gian chờ dài có thể làm cạn connection pool và tạo hàng đợi request phía trên.

## 8. Phạm vi khóa và tác động của truy vấn

Khóa bi quan có thể chặn nhiều hơn dự kiến nếu truy vấn không chọn đúng hàng hoặc database cần quét một phạm vi lớn.

### 8.1. Khóa đúng tài nguyên

Nếu invariant được xác định cho một SKU tại một kho, hãy khóa hàng đại diện cho cặp SKU/địa điểm đó. Không khóa toàn bộ bảng tồn kho chỉ vì cách viết truy vấn thuận tiện.

Chỉ mục phù hợp trên các cột lọc giúp database tìm đúng hàng hiệu quả. Khóa rộng, scan nhiều hàng hoặc thiếu index có thể làm tăng thời gian truy vấn và phạm vi tranh chấp. Cần kiểm tra execution plan và lock monitoring trên hệ quản trị thật.

### 8.2. Khóa một hàng không tự bảo vệ mọi dữ liệu liên quan

Nếu invariant phụ thuộc nhiều bảng hoặc nhiều hàng, khóa một hàng tùy ý chưa chắc bảo vệ được nó. Ví dụ, khóa một reservation không ngăn giao dịch khác tạo reservation mới nếu giao thức ghi không khóa cùng tài nguyên đại diện.

Mọi đường ghi có thể ảnh hưởng invariant phải tuân thủ cùng cơ chế bảo vệ hoặc bị ràng buộc bởi database. Nếu một job nền, script vận hành hoặc consumer khác ghi thẳng vào bảng mà không lấy khóa, invariant có thể bị phá vỡ.

### 8.3. Predicate và phantom rows

Một truy vấn khóa các hàng hiện có không nhất thiết khóa những hàng mới có thể được thêm vào để thỏa predicate. Ví dụ, khóa tất cả reservation đang hoạt động của một khách hàng không đảm bảo một transaction khác không thể chèn thêm reservation mới. Muốn bảo vệ quy tắc trên một tập hợp hoặc khoảng giá trị, cần hiểu isolation level, range/gap locks, predicate locking hoặc khóa một hàng đại diện phù hợp của database đang dùng.

Đây là lý do phải thiết kế từ invariant và truy vấn thực tế, không chỉ thêm `FOR UPDATE` vào một câu SQL rồi xem quy tắc đã an toàn.

## 9. Chi phí của khóa bi quan

Khóa bi quan đổi khả năng xử lý song song lấy tính tuần tự hóa trên tài nguyên bị tranh chấp. Chi phí tăng theo thời gian giữ khóa, số giao dịch cạnh tranh và phạm vi khóa.

### 9.1. Thời gian chờ và giảm throughput

Khi một transaction giữ khóa lâu, các transaction khác phải chờ. Một hàng nóng có thể trở thành điểm nghẽn dù phần còn lại của hệ thống còn nhiều tài nguyên. Throughput của tài nguyên đó bị giới hạn bởi tốc độ hoàn tất các transaction nối tiếp.

### 9.2. Deadlock

Deadlock xảy ra khi các transaction giữ khóa mà transaction khác cần, tạo thành vòng chờ. Ví dụ:

1. Transaction A khóa hàng X rồi chờ hàng Y.
2. Transaction B khóa hàng Y rồi chờ hàng X.
3. Không transaction nào có thể tiếp tục.

Database thường phát hiện deadlock và hủy một transaction làm nạn nhân. Ứng dụng phải xử lý lỗi và có thể retry toàn bộ transaction nếu thao tác có tính idempotent và chính sách cho phép.

### 9.3. Lock timeout và request timeout

Một transaction có thể chờ khóa lâu hơn thời gian request hoặc SLA cho phép. Khi timeout, ứng dụng phải rollback và giải phóng tài nguyên. Nếu timeout ở tầng HTTP xảy ra trước khi database hoàn tất, caller có thể không biết transaction đã commit hay chưa; cần request ID hoặc cơ chế tra cứu kết quả để tránh thực hiện trùng.

### 9.4. Chi phí connection và transaction

Transaction giữ khóa thường cũng giữ connection và tài nguyên database. Nếu ứng dụng mở nhiều transaction chờ khóa, connection pool có thể cạn, làm các request không liên quan cũng bị chậm.

### 9.5. Giảm khả năng mở rộng theo chiều ngang

Nhiều application instance vẫn có thể phối hợp qua khóa trong cùng một database, nhưng tất cả cùng tranh chấp tài nguyên database. Tăng số instance không làm một hàng nóng xử lý nhanh hơn; đôi khi còn tăng số transaction cạnh tranh và chi phí chờ.

## 10. Deadlock: nguyên nhân và cách giảm thiểu

Không phải deadlock nào cũng có thể loại bỏ hoàn toàn, nhưng thiết kế có thể giảm xác suất và giới hạn tác động.

### 10.1. Lấy khóa theo thứ tự ổn định

Nếu một transaction cần khóa nhiều hàng, hãy sắp xếp khóa theo một thứ tự xác định, chẳng hạn theo ID tăng dần. Các transaction khác cũng phải dùng cùng thứ tự. Điều này giảm khả năng A khóa X rồi Y trong khi B khóa Y rồi X.

### 10.2. Giữ transaction ngắn

- Chỉ thực hiện công việc cần thiết khi đang giữ khóa.
- Chuẩn bị dữ liệu đầu vào trước khi mở transaction nếu an toàn.
- Không gọi HTTP, gửi email hoặc chờ message trong transaction.
- Không chờ người dùng xác nhận.
- Commit hoặc rollback ngay khi hoàn thành quyết định.

### 10.3. Khóa đúng số hàng và có index

Truy vấn cần lọc bằng khóa định danh và chỉ mục phù hợp. Tránh khóa cả danh sách lớn nếu chỉ cần cập nhật một tài nguyên. Kiểm tra execution plan và lock wait để xác định truy vấn thực sự đang khóa gì.

### 10.4. Retry có giới hạn

Khi database chọn transaction làm deadlock victim, ứng dụng có thể retry toàn bộ transaction với số lần giới hạn và backoff ngắn. Chỉ retry nếu:

- Transaction trước đã rollback hoàn toàn hoặc kết quả được xác định.
- Command có thể thực hiện lại an toàn hoặc có idempotency key.
- Trạng thái được tải lại và invariant được đánh giá lại.
- Không lặp lại tác động bên ngoài đã xảy ra ngoài transaction.

Không retry vô hạn và không retry lỗi nghiệp vụ như hết tồn. Retry quá mức có thể làm tình trạng nghẽn nặng hơn.

## 11. NOWAIT và SKIP LOCKED

Một số database cung cấp biến thể để điều chỉnh hành vi khi hàng đã bị khóa. Cú pháp và ngữ nghĩa không hoàn toàn portable.

### 11.1. NOWAIT

`NOWAIT` yêu cầu truy vấn thất bại ngay nếu không thể lấy khóa, thay vì chờ. Cách này phù hợp khi ứng dụng muốn trả thông báo “tài nguyên đang được xử lý” hoặc thử lại ở một thời điểm khác.

Ví dụ cú pháp trên PostgreSQL:

```sql
SELECT *
FROM stock_item
WHERE sku = :sku AND location_id = :location_id
FOR UPDATE NOWAIT;
```

Ứng dụng cần phân biệt lỗi không lấy được khóa với lỗi không đủ hàng. Đây là hai tình huống có ý nghĩa khác nhau.

### 11.2. SKIP LOCKED

`SKIP LOCKED` bỏ qua những hàng đang bị transaction khác khóa. Nó hữu ích cho hàng đợi công việc: nhiều worker có thể lấy các job khác nhau mà không phải chờ cùng một job.

Ví dụ:

```sql
SELECT id
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

Không nên dùng `SKIP LOCKED` một cách máy móc cho truy vấn tồn kho hoặc số dư mà caller cần biết trạng thái đầy đủ. Việc bỏ qua một hàng đang khóa có thể khiến ứng dụng kết luận không có tài nguyên, trong khi thực tế tài nguyên đang được giao dịch khác xử lý. Chỉ dùng khi ngữ nghĩa nghiệp vụ chấp nhận bỏ qua bản ghi đang bận.

## 12. So sánh Pessimistic Locking và Optimistic Locking

Hai cách tiếp cận giải quyết tranh chấp theo hướng khác nhau.

| Tiêu chí | Pessimistic Locking | Optimistic Locking |
|---|---|---|
| Giả định | Xung đột có khả năng xảy ra | Xung đột tương đối hiếm |
| Thời điểm phát hiện | Lấy khóa trước khi xử lý | Phát hiện khi ghi/commit nếu version đã đổi |
| Hành vi cạnh tranh | Giao dịch chờ, bị từ chối hoặc bỏ qua | Giao dịch xung đột thất bại và cần tải lại/retry |
| Chi phí chính | Lock wait, deadlock, giữ connection/transaction | Retry, tính toán lại và xử lý conflict |
| Phù hợp | Tài nguyên khan hiếm, hàng nóng, transaction ngắn | Nhiều đọc, ít ghi xung đột, transaction đơn giản |
| Rủi ro | Chặn dây chuyền và giảm throughput | Retry storm hoặc người dùng phải xử lý conflict |

Không có lựa chọn tốt nhất cho mọi hệ thống. Hãy đo tỷ lệ xung đột và thời gian chờ trên workload thực. Một số use case có thể dùng optimistic locking; use case khác dùng pessimistic locking; một số trường hợp có thể dùng cập nhật nguyên tử có điều kiện.

## 13. Cập nhật nguyên tử có điều kiện như một lựa chọn khác

Nếu invariant có thể diễn đạt bằng một câu `UPDATE` có điều kiện, database có thể thực hiện phép kiểm tra và thay đổi nguyên tử mà không cần ứng dụng đọc rồi khóa riêng.

Ví dụ:

```sql
UPDATE stock_item
SET reserved = reserved + :quantity
WHERE sku = :sku
  AND location_id = :location_id
  AND :quantity > 0
  AND on_hand - reserved >= :quantity;
```

Ứng dụng kiểm tra số hàng bị cập nhật:

- `1` hàng: yêu cầu giữ hàng được chấp nhận.
- `0` hàng: không tìm thấy tài nguyên hoặc điều kiện không thỏa; cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu.

Phương pháp này ngắn và có thể giảm thời gian giữ khóa tường minh. Database vẫn cần khóa nội bộ để thực hiện update; đây không phải cơ chế “không có khóa”. Điểm khác biệt là kiểm tra và cập nhật được gói trong một thao tác nguyên tử, tránh khoảng thời gian giữa đọc và ghi ở application.

Nếu cần tạo thêm reservation record trong cùng transaction, hãy ghi nó sau khi update thành công và rollback nếu insert thất bại. Nếu quy tắc phụ thuộc nhiều dữ liệu hoặc cần logic phức tạp trong domain model, một thao tác cập nhật có điều kiện đơn lẻ có thể không đủ.

## 14. Khóa bi quan trong thiết kế Aggregate

Aggregate xác định ranh giới logic cần bảo vệ invariant; khóa bi quan là một cách hiện thực concurrency control cho ranh giới đó trong persistence layer.

Một cách tổ chức trách nhiệm:

1. Application service mở transaction.
2. Repository tải Aggregate bằng phương thức yêu cầu khóa.
3. Aggregate Root thực hiện hành vi và kiểm tra invariant.
4. Repository lưu thay đổi.
5. Transaction commit và database giải phóng khóa.

Ví dụ interface repository:

```java
public interface StockItemRepository {
    Optional<StockItem> getForUpdate(Sku sku, LocationId locationId);
    void save(StockItem stockItem);
}
```

Tên `getForUpdate` thể hiện rõ use case cần một Aggregate được nạp trong chế độ khóa. Implementation có thể dùng JPA pessimistic lock hoặc SQL cụ thể. Domain model không cần biết database đang sử dụng loại khóa nào.

### 14.1. Đảm bảo mọi đường ghi đều tuân thủ

Nếu một luồng dùng `getForUpdate` nhưng một luồng khác tải Aggregate bình thường rồi ghi đè dữ liệu, cơ chế bảo vệ có thể không còn hiệu quả như dự định. Mọi command có thể làm thay đổi invariant phải dùng cùng cơ chế hoặc một cơ chế tương thích.

Điều này áp dụng cho REST API, message consumer, batch job, tác vụ quản trị và script vận hành. Nên giới hạn quyền ghi trực tiếp vào bảng và kiểm thử các đường vào quan trọng.

### 14.2. Không để Aggregate Root phụ thuộc vào lock API

Domain model nên diễn đạt hành vi như `reserve`, `release` hoặc `adjustQuantity`. Repository và transaction boundary quyết định cách tải và đồng bộ. Điều này giữ mô hình miền độc lập với JPA, SQL dialect hoặc cơ chế khóa cụ thể.

## 15. Reservation không phải là giữ khóa lâu dài

Một lỗi thiết kế thường gặp là dùng database lock để giữ tài nguyên trong suốt một quy trình kéo dài, chẳng hạn từ lúc khách hàng bắt đầu checkout cho đến khi thanh toán hoàn tất. Một giao dịch database không nên mở trong nhiều phút để chờ người dùng hoặc hệ thống ngoài.

Thay vào đó, mô hình hóa reservation có thời hạn:

1. Transaction ngắn khóa Aggregate tồn kho.
2. Kiểm tra invariant và tạo reservation với trạng thái `ACTIVE`, thời hạn hết hiệu lực.
3. Cập nhật lượng đã giữ và commit.
4. Thanh toán diễn ra ngoài transaction tồn kho.
5. Khi thanh toán thành công, quy trình xác nhận reservation hoặc tiếp tục xử lý đơn.
6. Khi thanh toán thất bại hoặc hết hạn, một hành động riêng giải phóng reservation.

Database lock chỉ được giữ trong transaction ngắn để tạo hoặc thay đổi reservation. Reservation là khái niệm nghiệp vụ có trạng thái và thời hạn; lock là cơ chế kỹ thuật tạm thời để bảo vệ cập nhật. Hai thứ không nên bị nhầm lẫn.

## 16. Quan sát và đo lường trước khi chọn khóa

Quyết định dùng pessimistic locking nên dựa trên số liệu. Có thể theo dõi:

- Thời gian chờ khóa trung bình và phân vị cao (p95/p99).
- Số transaction bị timeout khi lấy khóa.
- Số deadlock và transaction bị database hủy.
- Tỷ lệ optimistic conflict nếu đang dùng versioning.
- Thời gian transaction giữ khóa.
- Số hàng hoặc tài nguyên thường xuyên bị tranh chấp.
- Throughput và latency theo từng use case.
- Connection pool utilization và số request chờ.
- Tỷ lệ lỗi nghiệp vụ do tài nguyên đã hết hoặc đã được xử lý.

Log và trace nên có correlation ID, Aggregate ID hoặc business key phù hợp để tìm ra tài nguyên nóng. Tránh ghi dữ liệu nhạy cảm không cần thiết.

Khi thử thay đổi chiến lược locking, cần so sánh trên workload đại diện. Một cơ chế có thể giảm conflict nhưng làm tăng p99 latency; cơ chế khác có thể tăng throughput nhưng cần nhiều retry. Đánh giá cả tính đúng đắn và trải nghiệm người dùng.

## 17. Kiểm thử hành vi khóa bi quan

Unit test của Aggregate kiểm tra invariant trong một luồng đơn. Nó không chứng minh hai transaction đồng thời không thể vi phạm invariant. Cần integration test với database cùng loại hoặc cùng ngữ nghĩa khóa với môi trường chạy thật.

### 17.1. Kiểm thử hai transaction cạnh tranh

Thiết lập:

- Tồn kho ban đầu là 5.
- Hai transaction độc lập cùng yêu cầu giữ 4.
- Cả hai chạy đồng thời trên hai connection khác nhau.

Kết quả mong đợi:

- Chỉ một yêu cầu giữ hàng thành công.
- Yêu cầu còn lại chờ rồi bị từ chối hoặc nhận kết quả không lấy được khóa theo chính sách.
- `reserved` cuối cùng bằng 4, không phải 8.
- Reservation record phản ánh đúng yêu cầu đã thành công.

### 17.2. Kiểm thử timeout và rollback

Giữ khóa trong transaction A, sau đó cho transaction B yêu cầu cùng hàng với timeout ngắn. Xác minh B nhận lỗi phù hợp, transaction được rollback và connection được giải phóng. Sau khi A kết thúc, một yêu cầu mới có thể tiếp tục.

### 17.3. Kiểm thử deadlock và retry

Tạo hai transaction khóa nhiều hàng theo thứ tự ngược để kiểm tra ứng dụng xử lý deadlock. Sau đó sửa implementation để lấy khóa theo thứ tự ổn định và xác minh số deadlock giảm. Không nên chỉ dùng mock repository vì mock không thể mô phỏng hành vi khóa của database.

### 17.4. Kiểm thử đường ghi khác

Kiểm tra message consumer, batch job hoặc thao tác quản trị có thể thay đổi cùng invariant. Nếu chúng bỏ qua giao thức locking, cần điều chỉnh hoặc bảo vệ ở database.

## 18. Checklist quyết định dùng Pessimistic Locking

Trước khi triển khai, hãy trả lời:

- [ ] Invariant cần bảo vệ được mô tả rõ và có ví dụ cạnh tranh cụ thể.
- [ ] Đã xác định chính xác hàng hoặc tài nguyên cần khóa.
- [ ] Có bằng chứng về tỷ lệ xung đột hoặc hậu quả cao nếu không tuần tự hóa.
- [ ] Transaction đủ ngắn và không chờ người dùng hay dịch vụ mạng.
- [ ] Truy vấn có index phù hợp và phạm vi khóa đã được kiểm tra.
- [ ] Mọi đường ghi liên quan đều tuân thủ cùng cơ chế bảo vệ.
- [ ] Đã xử lý trường hợp hàng chưa tồn tại và tạo đồng thời nếu có.
- [ ] Có timeout và cách phản hồi khi không lấy được khóa.
- [ ] Đã xem xét thứ tự lấy nhiều khóa để giảm deadlock.
- [ ] Retry có giới hạn và chỉ áp dụng khi an toàn/idempotent.
- [ ] Đã cân nhắc optimistic locking và conditional update.
- [ ] Có metric theo dõi lock wait, deadlock, timeout và latency.
- [ ] Có integration test với database phù hợp.

## 19. Kết nối với các khái niệm DDD khác

Invariant giúp xác định điều kiện mà Aggregate Root phải bảo vệ. Repository nạp và lưu Aggregate; transaction xác định phạm vi commit/rollback; pessimistic locking có thể tuần tự hóa các thao tác trên tài nguyên mà Aggregate sở hữu. Domain Event thông báo thay đổi đã được ghi nhận, còn process manager hoặc saga điều phối các bước kéo dài qua nhiều Aggregate hay bounded context.

Khóa bi quan phù hợp nhất khi một invariant cần được bảo vệ tức thời trên một tài nguyên có thể khóa, xung đột đủ thường xuyên và transaction có thể giữ ngắn. Khi quy trình kéo dài, có nhiều context hoặc cần chờ hệ thống ngoài, hãy dùng reservation và phối hợp bất đồng bộ thay vì giữ database lock trong suốt quy trình.

Mục tiêu cuối cùng không phải khóa càng nhiều càng an toàn. Mục tiêu là bảo vệ đúng invariant với phạm vi khóa nhỏ nhất và thời gian giữ ngắn nhất có thể, đồng thời đo lường chi phí để chọn cơ chế phù hợp với tải thực tế.
