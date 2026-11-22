# Khóa lạc quan bằng phiên bản và xử lý xung đột

Trong một hệ thống quản lý kho, hai nhân viên có thể cùng mở thông tin của một mặt hàng khi số lượng khả dụng đang là 10. Nhân viên thứ nhất giữ 7 đơn vị. Gần như cùng lúc, nhân viên thứ hai cũng yêu cầu giữ 6 đơn vị dựa trên thông tin họ đã đọc trước đó. Nếu cả hai thao tác đều ghi đè số lượng theo dữ liệu cũ, hệ thống có thể ghi nhận những quyết định mâu thuẫn và bán vượt lượng hàng thực có.

Đây là một dạng lỗi cập nhật đồng thời (*concurrent update*), thường được gọi là **lost update** khi một thay đổi bị ghi đè bởi thay đổi khác. Trong Domain-Driven Design (DDD), Aggregate phải bảo vệ các invariant của nó, kể cả khi nhiều request cùng tác động vào trạng thái. Một cách phổ biến để phát hiện xung đột là **optimistic locking** (khóa lạc quan) bằng trường phiên bản (*version*).

Ý tưởng là mỗi lần đọc Aggregate, ứng dụng nhận được trạng thái cùng một version. Khi ghi, ứng dụng chỉ cập nhật nếu version trong database vẫn bằng version mà nó đã đọc. Nếu một giao dịch khác đã cập nhật trước, version không còn khớp và lần ghi hiện tại bị từ chối. Ứng dụng khi đó phải đọc trạng thái mới và quyết định lại theo quy tắc nghiệp vụ.

Sau bài học này, bạn có thể:

- Giải thích lost update và lý do cần kiểm soát cập nhật đồng thời.
- Mô tả cách optimistic locking dùng version để phát hiện xung đột.
- Triển khai kiểm tra version bằng SQL và JPA/Hibernate.
- Phân biệt xung đột kỹ thuật với xung đột nghiệp vụ.
- Chọn cách xử lý phù hợp: tải lại, thử lại, hợp nhất hoặc yêu cầu người dùng xác nhận.
- Xác định giới hạn của version locking khi invariant trải qua nhiều Aggregate.

## 1. Vấn đề cập nhật đồng thời

Một hệ thống có thể nhận nhiều request cùng lúc. Hai request có thể đọc cùng một trạng thái, tính toán riêng và sau đó ghi kết quả. Nếu lần ghi sau không kiểm tra trạng thái đã thay đổi hay chưa, nó có thể ghi đè kết quả của lần ghi trước.

Giả sử một sản phẩm có `availableQuantity = 10`:

| Thời điểm | Nhân viên A | Nhân viên B | Database |
|---|---|---|---|
| T1 | Đọc số lượng 10 | | 10 |
| T2 | | Đọc số lượng 10 | 10 |
| T3 | Tính 10 - 7 = 3 | | 10 |
| T4 | | Tính 10 - 6 = 4 | 10 |
| T5 | Ghi số lượng 3 | | 3 |
| T6 | | Ghi số lượng 4 | 4 |

Kết quả cuối cùng là 4. Thay đổi của A bị ghi đè, và hệ thống không phản ánh đúng hai yêu cầu giữ hàng. Nếu nghiệp vụ coi cả hai yêu cầu đã thành công, số lượng đã giữ là 13 dù kho chỉ có 10.

Vấn đề không nằm ở phép trừ. Mỗi request tính toán đúng trên dữ liệu mà nó đọc. Vấn đề là dữ liệu đã cũ tại thời điểm ghi (*stale state*) nhưng ứng dụng vẫn cho phép ghi như thể nó còn mới.

### Lost update ảnh hưởng đến invariant

Invariant của Inventory có thể là:

> Số lượng được giữ không được vượt quá số lượng có thể bán.

Nếu hai thao tác đồng thời không được kiểm soát, mỗi thao tác riêng lẻ có thể thấy invariant vẫn đúng, nhưng kết quả kết hợp lại vi phạm invariant. Vì vậy, kiểm tra nghiệp vụ trong bộ nhớ sau khi đọc dữ liệu chưa đủ. Việc ghi phải đảm bảo trạng thái được kiểm tra vẫn là trạng thái mà thao tác cập nhật dựa vào.

## 2. Optimistic locking là gì?

Optimistic locking giả định xung đột ghi không xảy ra thường xuyên. Thay vì khóa dữ liệu trong suốt thời gian người dùng đọc và chỉnh sửa, hệ thống cho phép nhiều request làm việc trên bản sao trạng thái. Khi ghi, nó kiểm tra xem bản gốc có bị thay đổi kể từ lúc đọc hay không.

Một trường `version` được lưu cùng Aggregate. Ví dụ:

```text
stock_item
-----------------------------------------------
id          sku       available_quantity version
101         SKU-01    10                  4
```

Khi đọc, ứng dụng nhận `availableQuantity = 10` và `version = 4`. Khi cập nhật, ứng dụng gửi cả ID và version đã đọc. Database chỉ cập nhật hàng nếu version vẫn là 4. Nếu thành công, version tăng lên 5.

```sql
UPDATE stock_item
SET available_quantity = 3,
    version = version + 1
WHERE id = 101
  AND version = 4;
```

Ứng dụng kiểm tra số hàng được cập nhật:

- `1 row affected`: cập nhật thành công, version đã được tăng.
- `0 rows affected`: hàng không còn ở version 4 hoặc không tồn tại; cần xác định nguyên nhân và xử lý xung đột.

Điều kiện `WHERE version = 4` khiến việc kiểm tra và cập nhật diễn ra như một thao tác nguyên tử ở database. Nếu một request khác đã tăng version lên 5, câu lệnh trên không thể ghi đè trạng thái mới.

### Version là gì?

Version là số phiên bản của trạng thái được quản lý đồng thời. Nó thường là số nguyên tăng sau mỗi lần cập nhật thành công. Version không nhất thiết là số lần người dùng chỉnh sửa, số phiên bản sản phẩm hay version của schema. Nó là dấu mốc để phát hiện một bản đọc đã cũ.

Version thường có các đặc điểm:

- Được lưu cùng dữ liệu của Aggregate hoặc đối tượng cần kiểm soát.
- Được đọc cùng trạng thái.
- Được gửi lại khi cập nhật.
- Chỉ tăng khi thay đổi được commit thành công.
- Được so sánh trong điều kiện cập nhật để phát hiện xung đột.

Có thể dùng `long`, `BIGINT` hoặc một token phiên bản khác. Số nguyên tăng dần thường dễ hiểu và ít phụ thuộc đồng hồ hơn timestamp.

## 3. Cách compare-and-swap hoạt động

Optimistic locking thường được triển khai bằng kỹ thuật *compare-and-swap* (CAS): chỉ ghi giá trị mới nếu giá trị/version hiện tại vẫn bằng giá trị mà caller mong đợi.

Luồng tổng quát:

```text
1. Đọc Aggregate và version = v
2. Kiểm tra command trên trạng thái đã đọc
3. Tính trạng thái mới
4. UPDATE ... WHERE id = ? AND version = v
5. Nếu đúng 1 hàng: thành công, version thành v + 1
6. Nếu 0 hàng: xung đột hoặc bản ghi không tồn tại
```

Điểm quan trọng là bước 4 phải kiểm tra version trong cùng câu lệnh ghi hoặc cơ chế tương đương có tính nguyên tử. Nếu ứng dụng làm hai thao tác riêng:

1. `SELECT version` để kiểm tra.
2. `UPDATE` mà không có điều kiện version.

thì một request khác vẫn có thể cập nhật ở giữa hai bước. Đó là một race condition và việc kiểm tra không còn bảo vệ được thao tác ghi.

### SQL minh họa đầy đủ

```sql
UPDATE stock_item
SET available_quantity = :new_quantity,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND version = :expected_version;
```

Nếu câu lệnh cập nhật 0 hàng, ứng dụng không được coi đó là thành công. Nó có thể truy vấn lại để phân biệt bản ghi đã bị xóa, version đã thay đổi hoặc một điều kiện khác không còn đúng.

Một biến thể có thể thêm điều kiện nghiệp vụ vào cùng câu lệnh:

```sql
UPDATE stock_item
SET available_quantity = available_quantity - :requested,
    reserved_quantity = reserved_quantity + :requested,
    version = version + 1
WHERE id = :id
  AND version = :expected_version
  AND available_quantity >= :requested;
```

Ở đây cả version và điều kiện đủ hàng đều được kiểm tra tại thời điểm cập nhật. Tuy nhiên, khi câu lệnh trả về 0 hàng, nguyên nhân có thể là version conflict, thiếu hàng hoặc ID không tồn tại. Nếu cần phân biệt để trả thông điệp nghiệp vụ phù hợp, ứng dụng phải đọc lại trạng thái trong một luồng xử lý an toàn.

## 4. Mô phỏng hai request cùng cập nhật

Ban đầu:

```text
available_quantity = 10
version = 4
```

Hai request A và B cùng đọc version 4.

```text
Request A                         Request B
---------                         ---------
Read quantity=10, version=4       Read quantity=10, version=4
Reserve 7                         Reserve 6
UPDATE ... version=4
  -> 1 row updated
  quantity=3, version=5
                                  UPDATE ... version=4
                                    -> 0 rows updated
                                  Conflict detected
```

Request B không được tiếp tục ghi kết quả tính trên số lượng 10. Nó phải đọc lại Aggregate. Sau khi đọc version 5, B thấy chỉ còn 3 đơn vị khả dụng. Quy tắc domain từ chối yêu cầu giữ 6 đơn vị.

<badge color="success">Kết quả đúng</badge> Chỉ yêu cầu A được chấp nhận. Invariant “không giữ vượt số lượng khả dụng” vẫn được bảo vệ.

Optimistic locking không tự quyết định B nên được thông báo thế nào hoặc có thể đổi số lượng hay không. Nó chỉ phát hiện rằng giả định ban đầu của B đã lỗi thời. Quyết định tiếp theo thuộc về application flow và domain policy.

## 5. Optimistic locking và Aggregate trong DDD

Aggregate là ranh giới nhất quán (*consistency boundary*) bảo vệ một nhóm invariant. Nếu một command làm thay đổi trạng thái Aggregate, việc kiểm soát version thường được đặt ở Aggregate Root.

Ví dụ, `StockItem` là Aggregate Root và quản lý các reservation của SKU tại một kho. Mỗi yêu cầu giữ hàng phải đi qua hành vi của root:

```java
public class StockItem {
    private final StockItemId id;
    private int availableQuantity;
    private int reservedQuantity;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (availableQuantity < quantity) {
            throw new InsufficientStockException();
        }

        availableQuantity -= quantity;
        reservedQuantity += quantity;
    }
}
```

Phương thức `reserve()` bảo vệ invariant trong bộ nhớ của Aggregate. Repository và persistence mechanism đảm bảo thay đổi chỉ được ghi nếu version vẫn là version đã đọc. Hai phần bổ trợ nhau:

- Domain model kiểm tra quy tắc nghiệp vụ trên trạng thái đang xử lý.
- Optimistic locking ngăn trạng thái cũ ghi đè trạng thái mới.

Chỉ có `@Version` mà không có domain validation vẫn có thể cho phép một command sai nghiệp vụ. Chỉ có validation trong bộ nhớ mà không có kiểm soát concurrency vẫn có thể gặp lost update.

### Version thường đặt ở Aggregate Root

Nếu các Entity con chỉ được sửa thông qua Aggregate Root, version của root có thể đại diện cho phiên bản nhất quán của toàn Aggregate. Mọi thay đổi ảnh hưởng đến invariant của Aggregate cần làm version thay đổi.

Không nên để code khác cập nhật trực tiếp bảng con mà bỏ qua root/version. Nếu một cập nhật trực tiếp có thể phá vỡ invariant nhưng không tăng version, cơ chế optimistic locking sẽ không phát hiện được xung đột đó.

## 6. Dùng `@Version` với JPA và Hibernate

JPA hỗ trợ optimistic locking thông qua annotation `@Version`. Provider quản lý version khi entity được cập nhật. Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class StockItemEntity {
    @Id
    private Long id;

    private String sku;
    private int availableQuantity;
    private int reservedQuantity;

    @Version
    private long version;

    protected StockItemEntity() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (availableQuantity < quantity) {
            throw new InsufficientStockException();
        }
        availableQuantity -= quantity;
        reservedQuantity += quantity;
    }
}
```

Khi entity được nạp, Hibernate giữ version đã đọc. Khi flush thay đổi, provider phát câu lệnh có điều kiện theo ID và version cũ, sau đó tăng version. Nếu không có hàng nào được cập nhật, provider phát hiện optimistic locking conflict và ném exception phù hợp, thường là `OptimisticLockException` hoặc một exception được framework bao bọc.

Ví dụ application service:

```java
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;

public class ReserveStockService {
    private final EntityManager entityManager;

    public ReserveStockService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void reserve(Long stockItemId, int quantity) {
        StockItemEntity stock = entityManager.find(
            StockItemEntity.class, stockItemId
        );

        if (stock == null) {
            throw new StockItemNotFoundException();
        }

        stock.reserve(quantity);
        // Dirty checking và version check được thực hiện khi flush/commit.
    }
}
```

Đoạn code minh họa cách dùng JPA. Trong một ứng dụng DDD tách domain và persistence model, Entity JPA có thể là persistence adapter riêng, còn Aggregate domain được map qua repository. Không cần đưa annotation JPA vào domain object nếu điều đó làm domain phụ thuộc hạ tầng.

### Xung đột có thể xuất hiện ở flush hoặc commit

Không phải lúc nào exception cũng xuất hiện ngay tại dòng gọi `save()`. Với ORM dùng dirty checking, SQL có thể chỉ được gửi khi flush hoặc commit transaction. Vì vậy, `try/catch` quanh `entityManager.find()` hoặc quanh một lời gọi `save()` chưa chắc bắt được conflict.

Nếu cần phát hiện trong thân transaction, có thể gọi `flush()` có chủ đích, nhưng transaction vẫn có thể thất bại ở commit vì các ràng buộc khác. Cách xử lý exception phải dựa vào transaction boundary thực tế của framework.

Sau optimistic locking exception, transaction hiện tại thường đã bị đánh dấu rollback-only hoặc không còn an toàn để tiếp tục. Hãy kết thúc transaction đó rồi bắt đầu transaction mới để tải lại và xử lý lại.

## 7. Optimistic locking với repository

Domain interface không nhất thiết phải để lộ cách lưu version. Repository có thể cung cấp thao tác lưu Aggregate và persistence adapter thực thi version check.

```java
public interface StockItemRepository {
    Optional<StockItem> findById(StockItemId id);
    void save(StockItem stockItem);
}
```

Trong một số kiến trúc, repository có thể trả về version hoặc một kết quả cập nhật có thông tin conflict. Cách thiết kế phụ thuộc vào việc version là chi tiết kỹ thuật hay một phần của contract application layer.

Điều quan trọng là repository không được âm thầm ghi đè trạng thái mới bằng một Aggregate cũ. Nếu persistence adapter dùng câu lệnh SQL tùy chỉnh, nó phải đưa expected version vào điều kiện cập nhật và kiểm tra số hàng bị tác động.

### Cập nhật trực tiếp bằng JPQL hoặc SQL

Bulk update JPQL/SQL thường bỏ qua cơ chế dirty checking và có thể không tự áp dụng version theo cách mà bạn kỳ vọng. Nếu dùng bulk update, hãy chủ động:

- kiểm tra expected version trong `WHERE`,
- tăng version trong cùng câu lệnh,
- kiểm tra số hàng được cập nhật,
- đồng bộ hoặc làm mới persistence context nếu cần.

Ví dụ:

```sql
UPDATE stock_item
SET available_quantity = :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Nếu một luồng ghi bỏ qua version, các luồng dùng `@Version` có thể không nhận ra trạng thái đã bị thay đổi. Tất cả đường ghi vào cùng Aggregate phải tuân thủ cùng một quy tắc.

## 8. Phân biệt conflict kỹ thuật và conflict nghiệp vụ

Một optimistic locking conflict cho biết version đã thay đổi kể từ lần đọc. Nó không tự chứng minh rằng command của người dùng sai.

Ví dụ:

- Nhân viên A đổi ghi chú giao hàng.
- Nhân viên B đổi số lượng hàng.
- Cả hai cùng đọc version 7.
- A lưu trước, version thành 8.
- B lưu sau và gặp conflict.

Hai thay đổi có thể không mâu thuẫn về mặt nghiệp vụ. Tuy nhiên, nếu chúng cùng thuộc một Aggregate và version được quản lý ở root, hệ thống vẫn phát hiện xung đột. Application có thể tải lại trạng thái rồi áp dụng lại thay đổi của B nếu hành vi vẫn hợp lệ.

Ngược lại, hai request có thể không gặp version conflict nhưng vẫn tạo ra xung đột nghiệp vụ nếu invariant nằm ngoài phạm vi version được kiểm soát. Ví dụ hai Aggregate khác nhau cùng chiếm một chỗ ngồi duy nhất. Mỗi Aggregate có version riêng nên cả hai cập nhật có thể thành công, nhưng invariant “mỗi chỗ chỉ có một người” bị vi phạm. Khi đó cần một cơ chế khác như unique constraint, Aggregate boundary phù hợp, transaction isolation hoặc một quy trình giữ chỗ.

| Loại vấn đề | Ý nghĩa | Ví dụ | Cách xử lý |
|---|---|---|---|
| Version conflict | Trạng thái đã đổi sau lần đọc | Hai request sửa cùng StockItem | Tải lại và đánh giá lại command |
| Business rule rejection | Trạng thái hiện tại không cho phép hành vi | Sau khi tải lại, hàng không đủ | Trả lỗi nghiệp vụ |
| Cross-aggregate conflict | Invariant trải qua nhiều Aggregate | Hai đơn cùng đặt ghế cuối | Rà soát boundary, constraint hoặc coordination |
| Duplicate command | Cùng yêu cầu được gửi nhiều lần | Client retry sau timeout | Idempotency và deduplication |

Không nên gộp tất cả thành một thông báo “concurrent update”. Cách xử lý đúng phụ thuộc nguyên nhân.

## 9. Các chiến lược xử lý khi gặp xung đột

Khi version không còn khớp, ứng dụng có một số lựa chọn. Không có một chiến lược phù hợp cho mọi command.

### Tải lại và thử lại

Ứng dụng tải Aggregate mới nhất, thực thi command trên trạng thái mới rồi thử lưu lại. Cách này phù hợp khi ý định của command vẫn rõ và có thể đánh giá lại tự động.

Ví dụ, command `IncreaseReservedQuantityBy(2)` có thể được áp dụng lại trên trạng thái mới nếu vẫn còn đủ hàng. Nhưng command `SetAvailableQuantityTo(5)` có ý nghĩa ghi một giá trị tuyệt đối; tự động áp dụng lại có thể ghi đè quyết định của người khác.

### Tải lại và hợp nhất thay đổi

Nếu hai thay đổi độc lập, application có thể hợp nhất chúng theo quy tắc rõ ràng. Ví dụ, một người cập nhật ghi chú nội bộ, người khác cập nhật địa chỉ giao hàng. Nếu domain xác nhận hai phần độc lập, có thể áp dụng lại từng thay đổi sau khi đọc trạng thái mới.

Không nên hợp nhất chỉ vì các field khác nhau. Một field có thể ảnh hưởng đến invariant hoặc chính sách của field khác. Ví dụ, đổi địa chỉ giao hàng có thể làm thay đổi thuế hoặc vùng vận chuyển.

### Yêu cầu người dùng giải quyết

Với các chỉnh sửa có tính quyết định hoặc nội dung người dùng cần xem lại, hệ thống có thể trả thông báo rằng dữ liệu đã thay đổi và yêu cầu tải lại hoặc xác nhận. Đây thường là lựa chọn an toàn cho màn hình biên tập hồ sơ, hợp đồng hoặc cấu hình quan trọng.

### Từ chối theo quy tắc nghiệp vụ

Sau khi tải lại, command có thể không còn hợp lệ. Ví dụ, yêu cầu reserve 6 đơn vị bị từ chối vì chỉ còn 3. Đây là kết quả nghiệp vụ, không phải lỗi hạ tầng cần retry mãi.

## 10. Retry phải thực hiện trong transaction mới

Một quy trình retry an toàn thường gồm:

1. Transaction thứ nhất đọc Aggregate, áp dụng command và cố gắng commit.
2. Nếu phát hiện optimistic conflict, transaction thứ nhất rollback.
3. Application bắt đầu transaction mới.
4. Tải Aggregate mới nhất.
5. Đánh giá lại command theo trạng thái mới.
6. Nếu vẫn hợp lệ, lưu và commit; nếu không, trả kết quả nghiệp vụ.

Không nên giữ Entity cũ rồi gọi `save()` lặp lại. Nó vẫn chứa version cũ và trạng thái cũ. Với JPA, persistence context của transaction thất bại cũng không nên được tái sử dụng để tiếp tục logic.

### Giới hạn số lần retry

Retry vô hạn có thể tạo vòng lặp khi Aggregate liên tục bị cập nhật. Hãy đặt giới hạn số lần, ghi nhận metric và có cách phản hồi khi hết lượt.

Ví dụ:

```java
public ReserveResult reserveWithRetry(
        StockItemId id,
        int quantity,
        int maxAttempts) {

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionRunner.execute(() -> {
                StockItem stock = repository.findById(id)
                    .orElseThrow(StockItemNotFoundException::new);
                stock.reserve(quantity);
                repository.save(stock);
                return ReserveResult.success();
            });
        } catch (OptimisticConflictException conflict) {
            if (attempt == maxAttempts) {
                return ReserveResult.concurrentModification();
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

Đây là pseudocode để thể hiện vị trí transaction boundary. `transactionRunner.execute()` phải tạo transaction mới cho mỗi lần gọi và chỉ trả kết quả sau khi commit. Không nên bắt mọi exception rồi retry; chỉ retry loại conflict được xác định là có thể thử lại.

Khi mức tranh chấp cao, có thể cần backoff ngắn hoặc jitter để tránh các request liên tục va vào nhau. Nhưng retry không làm giảm bản chất tranh chấp. Nếu một Aggregate luôn bị cập nhật dồn dập, cần xem lại cách phân chia dữ liệu, quy trình hoặc cơ chế đồng bộ.

## 11. Không retry mù quáng các side effect bên ngoài

Giả sử một command vừa cập nhật Order vừa gọi cổng thanh toán. Nếu transaction database thất bại do version conflict sau khi cổng thanh toán đã thu tiền, việc retry toàn bộ command có thể thu tiền lần thứ hai.

Không nên đặt side effect bên ngoài vào vòng retry mà không có cơ chế bảo vệ. Có thể dùng:

- **Idempotency key:** cùng một yêu cầu thanh toán có cùng khóa để provider nhận diện retry.
- **Transactional Outbox:** ghi event/command cần gửi cùng transaction với thay đổi domain, sau đó publisher gửi sau commit.
- **Process Manager/Saga:** điều phối các bước dài qua nhiều context và có hành động bù trừ khi cần.
- **Reconciliation:** đối soát trạng thái với hệ thống bên ngoài khi kết quả request không xác định.

Optimistic locking bảo vệ cập nhật của Aggregate trong transaction. Nó không tự đảm bảo một thao tác HTTP, email, chuyển khoản hoặc message chỉ xảy ra đúng một lần.

## 12. Trả conflict cho API và giao diện

Version cũng có thể được dùng ở ranh giới HTTP. Server trả version hoặc ETag khi client đọc tài nguyên. Khi cập nhật, client gửi lại điều kiện mà nó đã đọc.

Ví dụ:

```http
GET /orders/ORD-2026-00125
```

Response:

```http
HTTP/1.1 200 OK
ETag: "order-v7"
Content-Type: application/json
```

Client gửi cập nhật với:

```http
PUT /orders/ORD-2026-00125
If-Match: "order-v7"
Content-Type: application/json
```

Server chỉ áp dụng thay đổi nếu phiên bản hiện tại vẫn khớp. Với HTTP conditional request, `If-Match` không thỏa điều kiện thường được phản hồi bằng `412 Precondition Failed`. Một API có thể dùng `409 Conflict` cho xung đột nghiệp vụ hoặc quy ước conflict riêng. Hãy chọn status code nhất quán với contract và giải thích cách client khôi phục.

Response conflict có thể chứa thông tin hữu ích:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "Order đã được cập nhật bởi một thao tác khác.",
  "currentVersion": 8,
  "action": "RELOAD_AND_REVIEW"
}
```

Không nhất thiết phải công khai số version nội bộ. ETag có thể là token opaque. Client chỉ cần gửi lại đúng validator mà server cấp.

### Giao diện nên xử lý thế nào?

Với form chỉnh sửa, khi server trả conflict, giao diện có thể:

- thông báo dữ liệu đã thay đổi,
- tải bản mới nhất,
- hiển thị các trường thay đổi để người dùng so sánh,
- cho phép áp dụng lại chỉnh sửa nếu không mâu thuẫn,
- yêu cầu xác nhận trước khi ghi đè một giá trị quan trọng.

Đừng tự động thay version cũ bằng version mới rồi gửi lại nguyên payload nếu payload là một bản ghi đầy đủ. Cách đó có thể biến một cảnh báo conflict thành thao tác ghi đè dữ liệu mới nhất.

## 13. Version khác timestamp

Một số hệ thống dùng `updated_at` hoặc timestamp để phát hiện dữ liệu đã đổi. Cách này có thể hữu ích cho audit hoặc API, nhưng timestamp không phải lúc nào cũng là token concurrency tốt.

Các vấn đề có thể gặp:

- Độ phân giải timestamp có thể thấp hơn tần suất cập nhật.
- Đồng hồ giữa các node có thể lệch.
- Hai cập nhật có thể tạo timestamp bằng nhau.
- Timestamp có thể được thay đổi bởi migration hoặc dữ liệu nhập ngoài.
- So sánh thời gian không thể hiện trực tiếp thứ tự version của một Aggregate.

Một version số nguyên tăng dần thường đơn giản hơn để kiểm tra thay đổi. Timestamp vẫn có giá trị cho audit, hiển thị và truy vấn thời gian, nhưng không nên mặc định thay thế version.

## 14. Optimistic locking không thay thế mọi cơ chế đồng thời

Optimistic locking phù hợp khi xung đột tương đối hiếm và có thể xử lý khi phát hiện. Nhưng nó không giải quyết mọi loại concurrency anomaly.

### Invariant nằm trong một Aggregate

Nếu một Aggregate Root bảo vệ invariant và mọi thay đổi đi qua root với version check, optimistic locking có thể là lựa chọn tốt.

### Invariant trải qua nhiều Aggregate

Ví dụ, một rạp có một ghế cuối cùng và hai Aggregate Booking khác nhau cùng muốn đặt ghế đó. Mỗi Booking có version riêng. Cả hai có thể được cập nhật thành công vì không cùng sửa một Aggregate.

Các lựa chọn có thể gồm:

- Đưa quyền sở hữu ghế/slot vào một Aggregate có thể bảo vệ invariant.
- Dùng unique constraint ở database để đảm bảo một ghế chỉ có một reservation đang hiệu lực trong phạm vi thời gian.
- Dùng transaction isolation phù hợp nếu invariant được kiểm tra trong một transaction database.
- Dùng cơ chế reservation/lease với thời hạn và trạng thái rõ ràng.
- Dùng process coordination hoặc Saga khi quy trình trải qua nhiều hệ thống.

Không nên tạo một Aggregate khổng lồ chỉ để khóa mọi thứ. Hãy xem xét tần suất thay đổi, ranh giới consistency và chi phí phối hợp.

### Khi cần pessimistic locking

Pessimistic locking khóa bản ghi hoặc tài nguyên trong lúc transaction xử lý, khiến giao dịch khác phải chờ hoặc thất bại tùy cấu hình. Nó có thể phù hợp khi:

- xung đột rất thường xuyên,
- chi phí retry cao,
- thao tác ngắn và có thể giữ khóa trong thời gian giới hạn,
- domain cần tuần tự hóa một tài nguyên cụ thể.

Nhược điểm là transaction có thể phải chờ, gây contention, deadlock hoặc giảm throughput. Không nên dùng pessimistic locking cho một quy trình người dùng mở form rồi suy nghĩ vài phút; transaction database không nên giữ khóa trong suốt khoảng thời gian đó.

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Giả định | Xung đột hiếm | Xung đột có khả năng xảy ra thường xuyên |
| Cách làm | Kiểm tra version khi ghi | Khóa tài nguyên để ngăn cập nhật đồng thời |
| Khi xung đột | Phát hiện và xử lý/retry | Giao dịch khác thường phải chờ hoặc bị từ chối |
| Phù hợp | Nhiều lượt đọc, ít va chạm ghi | Tranh chấp cao, transaction ngắn |
| Rủi ro | Retry và conflict response | Lock contention, deadlock, thời gian chờ |

## 15. Versioning trong Event Sourcing

Với Event Sourcing, Aggregate được dựng từ chuỗi event. Khi lưu event mới, event store thường yêu cầu expected version hoặc expected sequence number.

Ví dụ, Aggregate hiện có version 12. Một command đọc version 12 và quyết định tạo event `StockReserved`. Khi append, event store chỉ chấp nhận nếu version hiện tại vẫn là 12. Nếu một command khác đã append event và nâng version lên 13, lần append cũ bị từ chối.

```text
Append events:
  aggregateId = STOCK-01
  expectedVersion = 12
  events = [StockReserved]

Nếu stream vẫn ở version 12:
  append thành công -> version 13

Nếu stream đã ở version 13:
  concurrency conflict -> tải lại và quyết định lại
```

Đây cũng là optimistic concurrency control. Expected version bảo vệ thứ tự ghi event cho một Aggregate. Nó không tự giải quyết invariant trải qua nhiều stream hoặc nhiều Aggregate.

## 16. Những lỗi triển khai thường gặp

**Đọc version nhưng không kiểm tra lúc ghi.** Việc đọc `version` không có tác dụng nếu câu lệnh `UPDATE` không chứa điều kiện version hoặc provider không quản lý version.

**Kiểm tra version bằng hai câu lệnh riêng.** `SELECT version` rồi `UPDATE` không điều kiện vẫn có race window. Hãy dùng compare-and-swap nguyên tử.

**Có đường ghi bỏ qua version.** Bulk SQL, batch job hoặc một service khác cập nhật bảng nhưng không tăng version có thể làm cơ chế phát hiện conflict mất tác dụng.

**Đặt version ở sai ranh giới.** Nếu một thay đổi ảnh hưởng invariant của Aggregate nhưng không làm version root đổi, optimistic locking không bảo vệ invariant đó.

**Bắt exception rồi tiếp tục cùng transaction.** Sau conflict, transaction/persistence context có thể đã không còn hợp lệ. Hãy rollback và dùng transaction mới.

**Retry trên cùng object cũ.** Object cũ vẫn giữ version và trạng thái lỗi thời. Phải tải lại trạng thái mới.

**Retry mọi exception.** Lỗi validation, thiếu dữ liệu, lỗi kết nối hoặc business rejection không nên bị retry vô hạn.

**Retry side effect bên ngoài.** Có thể thu tiền hoặc gửi lệnh hai lần. Cần idempotency, outbox hoặc quy trình đối soát.

**Tự động ghi đè sau conflict.** Thay version trong request rồi gửi lại toàn bộ payload có thể làm mất chỉnh sửa của người khác.

**Cho rằng version bảo vệ mọi invariant.** Version thường bảo vệ một Aggregate hoặc một hàng; invariant liên Aggregate cần thiết kế riêng.

## 17. Quy trình thiết kế xử lý xung đột

Khi thêm optimistic locking cho một Aggregate, hãy thực hiện lần lượt:

**Bước 1: Xác định invariant.** Viết rõ điều kiện nào phải luôn đúng và Aggregate nào sở hữu nó.

**Bước 2: Xác định mọi đường ghi.** Bao gồm API, message consumer, batch job, admin tool và SQL trực tiếp. Tất cả đường ghi phải tuân thủ version protocol.

**Bước 3: Chọn version field.** Chọn kiểu dữ liệu đủ dùng, giá trị khởi tạo và nơi lưu. Với ORM, dùng cơ chế version được framework hỗ trợ.

**Bước 4: Đảm bảo compare-and-swap nguyên tử.** Câu lệnh ghi phải kiểm tra expected version cùng lúc cập nhật và tăng version.

**Bước 5: Xác định hành vi khi conflict.** Command nào có thể tự áp dụng lại? Command nào phải yêu cầu người dùng xem lại? Command nào sau khi tải lại có thể bị từ chối bởi domain?

**Bước 6: Thiết kế transaction boundary.** Retry phải tạo transaction mới và tải lại Aggregate. Không giữ transaction mở trong thời gian người dùng thao tác.

**Bước 7: Bảo vệ side effect.** Dùng idempotency key, outbox hoặc coordination phù hợp khi command gửi message hay gọi hệ thống ngoài.

**Bước 8: Xác định contract API.** Quyết định dùng version trong body, ETag/If-Match hoặc cơ chế khác; mô tả status code và hướng khôi phục.

**Bước 9: Kiểm thử tranh chấp thực tế.** Tạo hai transaction cùng đọc một version và thử ghi. Xác minh chỉ một lần ghi thành công.

## 18. Kiểm thử optimistic locking

Một unit test cho `StockItem.reserve()` chỉ kiểm tra invariant trong bộ nhớ. Nó không chứng minh database phát hiện được hai transaction đồng thời. Cần ít nhất một integration test với database hoặc persistence provider thật.

Một kịch bản test:

1. Tạo StockItem có `availableQuantity = 10`, `version = 1`.
2. Transaction A tải entity.
3. Transaction B tải cùng entity.
4. A reserve 7 và commit.
5. B reserve 6 dựa trên bản đã đọc và cố commit.
6. Xác minh B nhận optimistic conflict.
7. Tải lại trạng thái và xác minh quantity còn 3; B không được ghi đè thành 4.

Pseudo test:

```java
StockItemEntity a = transactionA.load(stockId);
StockItemEntity b = transactionB.load(stockId);

a.reserve(7);
transactionA.commit();

b.reserve(6);
assertThrows(OptimisticLockException.class, transactionB::commit);

StockItemEntity latest = repository.findById(stockId).orElseThrow();
assertEquals(3, latest.getAvailableQuantity());
```

Test cần chạy trên các transaction/persistence context riêng. Nếu chỉ dùng một persistence context hoặc một transaction tuần tự, nó không mô phỏng được stale state thực sự. Cũng cần chú ý exception có thể được framework bọc và chỉ xuất hiện ở commit.

### Các trường hợp cần kiểm tra thêm

- Hai cập nhật khác field nhưng cùng Aggregate.
- Một request bị conflict rồi tải lại và thành công.
- Sau khi tải lại, command bị từ chối vì invariant không còn đúng.
- Bản ghi bị xóa trong lúc request đang xử lý.
- Bulk update có tăng version đúng không.
- Hai Aggregate khác nhau cùng tranh chấp một tài nguyên dùng chung.
- Retry không gửi side effect hai lần.
- API trả đúng `409` hoặc `412` theo contract.

## 19. Checklist trước khi đưa vào sử dụng

- [ ] Aggregate có invariant được mô tả rõ.
- [ ] Version nằm ở đúng consistency boundary.
- [ ] Mỗi lần đọc lấy cả trạng thái và version.
- [ ] Mỗi lần ghi kiểm tra expected version một cách nguyên tử.
- [ ] Version tăng sau thay đổi thành công.
- [ ] Không có đường ghi bỏ qua version protocol.
- [ ] Conflict được phân biệt với business rejection.
- [ ] Retry dùng transaction mới và tải Aggregate mới.
- [ ] Số lần retry có giới hạn.
- [ ] Command được đánh giá lại theo trạng thái mới.
- [ ] Side effect bên ngoài có idempotency hoặc cơ chế đáng tin cậy.
- [ ] Client có hướng xử lý khi version conflict.
- [ ] Có integration test với hai transaction độc lập.
- [ ] Invariant liên Aggregate có cơ chế bảo vệ riêng.

## 20. Bài tập tự kiểm tra

Một hệ thống đặt chỗ có Aggregate `RoomAvailability` với `availableSlots = 1` và `version = 12`. Hai khách A và B cùng yêu cầu đặt slot cuối cùng. Cả hai cùng đọc version 12.

Hãy trả lời:

1. Câu lệnh cập nhật cần có điều kiện nào để chỉ một request ghi thành công?
2. Nếu A cập nhật trước và version thành 13, B nên làm gì khi nhận conflict?
3. Nếu B tải lại và thấy `availableSlots = 0`, đây là version conflict hay business rejection?
4. Nếu mỗi Booking là một Aggregate riêng và cả hai cùng đặt một phòng, version của Booking có đủ bảo vệ invariant “một slot chỉ có một booking” không?
5. Có thể dùng unique constraint nào hoặc thay đổi Aggregate boundary ra sao để bảo vệ slot?
6. Nếu client gửi lại cùng command sau timeout, làm sao tránh tạo hai booking?
7. Khi nào nên trả `412 Precondition Failed`, khi nào nên trả `409 Conflict`?

Gợi ý:

- Cập nhật theo `WHERE id = ? AND version = 12`, đồng thời tăng version trong cùng câu lệnh.
- B tải lại trạng thái mới trong transaction mới và thực thi lại quy tắc domain.
- Khi slot đã hết, yêu cầu của B bị từ chối vì quy tắc nghiệp vụ; conflict chỉ là tín hiệu khiến B phải đánh giá lại.
- Version của từng Booking không bảo vệ được một slot dùng chung nếu hai Aggregate khác nhau cùng tạo booking. Cần một Aggregate sở hữu slot, unique constraint hoặc cơ chế reservation/coordination phù hợp.
- Idempotency key hoặc unique request reference giúp nhận diện command được gửi lại.
- `412` phù hợp với conditional request như `If-Match` không còn đúng; `409` có thể dùng cho xung đột trạng thái nghiệp vụ theo contract API.

## Kết luận

Optimistic locking bằng version giúp phát hiện một thao tác đang ghi dựa trên trạng thái đã cũ. Khi đọc Aggregate, ứng dụng giữ version; khi ghi, database chỉ chấp nhận cập nhật nếu version vẫn khớp và tăng version trong cùng thao tác. Cách này bảo vệ các thay đổi đồng thời trong đúng consistency boundary mà version đại diện.

Phát hiện conflict chỉ là bước đầu. Ứng dụng phải rollback transaction cũ, tải trạng thái mới và quyết định có thể thử lại, hợp nhất, yêu cầu người dùng xác nhận hay từ chối theo nghiệp vụ. Retry cần giới hạn và không được lặp side effect bên ngoài một cách mù quáng. Cuối cùng, hãy nhớ version của một Aggregate không tự bảo vệ invariant trải qua nhiều Aggregate; những trường hợp đó cần ranh giới, constraint hoặc cơ chế phối hợp phù hợp.
