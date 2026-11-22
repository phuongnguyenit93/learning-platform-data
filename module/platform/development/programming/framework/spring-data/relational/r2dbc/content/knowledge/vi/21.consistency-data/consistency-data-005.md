# Kiểm soát đồng thời bằng điều kiện cập nhật và số hàng bị tác động

## 1. Vấn đề cập nhật đồng thời

Trong ứng dụng có nhiều request, nhiều worker hoặc nhiều instance cùng truy cập database, hai thao tác có thể đọc cùng một trạng thái rồi cố gắng cập nhật nó. Nếu ứng dụng chỉ đọc dữ liệu về Java, tính toán giá trị mới và ghi lại mà không có cơ chế bảo vệ, một cập nhật có thể ghi đè cập nhật khác hoặc làm vi phạm quy tắc nghiệp vụ.

Ví dụ, kho còn 5 sản phẩm. Hai request cùng đọc số lượng là 5:

1. Request A muốn giữ 4 sản phẩm.
2. Request B muốn giữ 3 sản phẩm.
3. Cả hai đều đọc thấy số lượng 5.
4. A tính còn 1 rồi ghi `available = 1`.
5. B tính còn 2 rồi ghi `available = 2`.

Kết quả cuối cùng có thể là 2, mặc dù tổng số đã giữ là 7. Một request đã ghi đè kết quả của request kia và dữ liệu kho không còn phản ánh đúng thực tế.

Spring Data R2DBC cho phép thực hiện cập nhật trực tiếp bằng SQL có điều kiện. Điều kiện được đặt ngay trong câu `UPDATE`, để database kiểm tra trạng thái và thay đổi hàng trong cùng một statement. Số hàng bị tác động sau đó cho ứng dụng biết điều kiện có khớp hay không theo semantics của database/driver.

## 2. Ý tưởng: kiểm tra điều kiện ngay trong UPDATE

Thay vì thực hiện hai bước riêng:

```text
SELECT available
Ứng dụng kiểm tra available >= quantity
UPDATE inventory SET available = giá_trị_đã_tính
```

hãy đưa điều kiện vào chính câu lệnh cập nhật:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
```

Database thực hiện việc kiểm tra điều kiện và thay đổi hàng trong một statement. Với một hàng kho được nhận diện duy nhất bằng `product_id`, các request cạnh tranh sẽ được database điều phối theo cơ chế khóa và isolation của hệ quản trị. Một request chỉ cập nhật khi điều kiện `available >= quantity` còn đúng tại thời điểm statement thực hiện cập nhật.

Đây là một dạng **conditional update** hoặc **compare-and-set (CAS)**: chỉ thay đổi dữ liệu nếu trạng thái hiện tại vẫn thỏa điều kiện mà caller yêu cầu.

Điều kiện trong `WHERE` có thể kiểm tra:

- Số lượng hoặc số dư còn đủ.
- Trạng thái hiện tại vẫn là trạng thái mong đợi.
- Version chưa bị request khác thay đổi.
- Bản ghi chưa bị soft delete.
- Người sở hữu hoặc tenant khớp với ngữ cảnh request.
- Thời hạn hoặc điều kiện nghiệp vụ vẫn còn hiệu lực.

## 3. Mô hình số hàng bị tác động

Một câu UPDATE hoặc DELETE có thể tác động 0, 1 hoặc nhiều hàng. Số hàng bị tác động giúp ứng dụng diễn giải kết quả:

| Kết quả thường gặp | Cách hiểu |
| ---: | --- |
| `0` | Không có hàng nào được báo cáo là bị tác động; có thể do không tồn tại hoặc điều kiện không còn đúng |
| `1` | Một hàng được báo cáo là bị tác động; phù hợp với thao tác mong đợi đúng một bản ghi |
| Lớn hơn `1` | Nhiều hàng bị tác động; hợp lệ với bulk update, nhưng có thể là lỗi nếu nghiệp vụ kỳ vọng một hàng duy nhất |

Ví dụ, nếu cập nhật một tài khoản theo khóa chính, kết quả mong đợi thường là 1. Nếu cập nhật trạng thái tất cả task hết hạn, kết quả có thể lớn hơn 1.

Không nên diễn giải `0` một cách quá cụ thể. Nó có thể có nghĩa:

- ID không tồn tại.
- Điều kiện số dư/tồn kho không còn đủ.
- Trạng thái hiện tại khác trạng thái mong đợi.
- Version đã thay đổi do request khác cập nhật.
- Bản ghi đã bị xóa mềm.
- Điều kiện quyền truy cập hoặc tenant không khớp.

Nếu câu lệnh chỉ trả số hàng, các lý do này thường không thể phân biệt trực tiếp. Có thể thiết kế thêm truy vấn chẩn đoán, kết quả SQL trả về có mã lý do, hoặc một quy trình nghiệp vụ phù hợp.

## 4. Lấy số hàng bị tác động bằng DatabaseClient

Spring `DatabaseClient` hỗ trợ thực thi câu SQL và đọc số hàng đã cập nhật:

```java
public Mono<Integer> reserve(
        DatabaseClient databaseClient,
        Long productId,
        int quantity) {

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND :quantity > 0
              AND available >= :quantity
            """)
            .bind("productId", productId)
            .bind("quantity", quantity)
            .fetch()
            .rowsUpdated();
}
```

`rowsUpdated()` trả publisher chứa số hàng bị tác động theo API Spring Framework và driver đang dùng. Trong các phiên bản Spring R2DBC phổ biến, kiểu trả về là `Mono<Integer>`; cần kiểm tra chữ ký của phiên bản dự án nếu nâng cấp framework.

Các điểm đáng chú ý:

- `available = available - :quantity` tính từ giá trị hiện tại của hàng trong database.
- `available >= :quantity` ngăn số lượng âm do request cạnh tranh.
- `:quantity > 0` bảo vệ thêm điều kiện đầu vào ngay tại SQL.
- Các giá trị được bind bằng tham số, không nối chuỗi từ dữ liệu request.
- Nếu điều kiện không khớp, số hàng bị tác động thường là 0.

Kiểm tra `quantity > 0` ở tầng domain/service vẫn cần thiết để trả lỗi đầu vào rõ ràng. Điều kiện SQL là lớp bảo vệ dữ liệu khi có nhiều đường ghi hoặc caller không đáng tin cậy.

## 5. Dùng @Modifying trong repository

Với câu SQL cố định và đơn giản, có thể khai báo modifying query trong repository:

```java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE product_id = :productId
          AND :quantity > 0
          AND available >= :quantity
        """)
    Mono<Integer> reserveIfAvailable(
            @Param("productId") Long productId,
            @Param("quantity") Integer quantity);
}
```

Sử dụng trong application service:

```java
public Mono<Void> reserveInventory(Long productId, int quantity) {
    if (quantity <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Quantity must be positive"));
    }

    return inventoryRepository.reserveIfAvailable(productId, quantity)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(
                            new InsufficientInventoryException(productId));
                }
                return Mono.error(new IllegalStateException(
                        "Expected one inventory row, got " + rows));
            });
}
```

Ví dụ giả định `product_id` là duy nhất nên tối đa một hàng được cập nhật. Nếu schema cho phép nhiều hàng cùng `product_id`, cần sửa khóa hoặc điều kiện truy vấn để phản ánh đúng mô hình.

`@Modifying` cho biết `@Query` là câu lệnh thay đổi dữ liệu. Với modifying query reactive, kiểu số như `Mono<Integer>` giúp nhận số hàng bị tác động; nếu chỉ cần tín hiệu hoàn tất, có thể dùng kiểu reactive không phát dữ liệu theo khả năng của phiên bản Spring Data R2DBC.

## 6. Tránh mẫu SELECT rồi UPDATE

Một cách viết dễ gặp nhưng không an toàn khi có cạnh tranh:

```java
return inventoryRepository.findByProductId(productId)
        .flatMap(inventory -> {
            if (inventory.getAvailable() < quantity) {
                return Mono.error(new InsufficientInventoryException(productId));
            }

            inventory.setAvailable(inventory.getAvailable() - quantity);
            return inventoryRepository.save(inventory);
        });
```

Vấn đề là điều kiện được kiểm tra trong Java dựa trên một snapshot đã đọc trước đó. Trước khi `save` chạy, request khác có thể đã thay đổi số lượng. Cả hai request có thể cùng vượt qua điều kiện kiểm tra.

Một transaction ở mức mặc định không tự động làm cho chuỗi đọc rồi ghi trở thành an toàn trước mọi cập nhật đồng thời. Kết quả còn phụ thuộc isolation level, locking, version và cách truy vấn.

Nếu quy tắc có thể biểu diễn bằng điều kiện SQL, hãy dùng một câu UPDATE có điều kiện. Nếu cần đọc aggregate và áp dụng logic phức tạp, hãy cân nhắc optimistic locking với `@Version` hoặc cơ chế khóa phù hợp.

## 7. Ví dụ: giữ hàng tồn kho an toàn

Giả sử schema:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

Câu lệnh giữ hàng:

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE product_id = :productId
  AND :quantity > 0
  AND available >= :quantity;
```

Điều kiện `available >= :quantity` nằm trong cùng statement với phép trừ. Database không nhận giá trị `available` cũ do Java tính rồi ghi đè; nó thực hiện phép tính trên giá trị của hàng tại thời điểm cập nhật.

Giả sử ban đầu `available = 5` và hai request đồng thời:

| Request | Số lượng muốn giữ |
| --- | ---: |
| A | 4 |
| B | 3 |

Một request có thể cập nhật trước và đưa `available` xuống 1. Khi request còn lại được database xử lý, điều kiện `available >= 3` không còn đúng nên không cập nhật hàng đó. Kết quả là chỉ một request thành công, số lượng còn lại không âm.

Hành vi cụ thể phụ thuộc concurrency control và isolation của database, nhưng câu lệnh có điều kiện loại bỏ khoảng trống giữa kiểm tra và ghi trong ứng dụng. Constraint `CHECK (available >= 0)` là lớp bảo vệ bổ sung ở schema.

## 8. Ví dụ: trừ số dư tài khoản

Một tài khoản không được phép có số dư âm. Schema:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

Repository:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
        UPDATE account
        SET balance = balance - :amount,
            version = version + 1
        WHERE id = :accountId
          AND :amount > 0
          AND balance >= :amount
        """)
    Mono<Integer> debitIfSufficient(
            @Param("accountId") Long accountId,
            @Param("amount") BigDecimal amount);
}
```

Service:

```java
public Mono<Void> debit(Long accountId, BigDecimal amount) {
    if (amount == null || amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Amount must be positive"));
    }

    return accountRepository.debitIfSufficient(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(
                            new InsufficientBalanceException(accountId));
                }
                return Mono.error(new IllegalStateException(
                        "Unexpected number of accounts updated: " + rows));
            });
}
```

Đối với tiền, dùng `BigDecimal` và cột `NUMERIC/DECIMAL`; không dùng `double`. Precision/scale của cột phải đủ cho giá trị nghiệp vụ.

Điều kiện `balance >= :amount` bảo đảm không trừ vượt số dư trong cùng statement. Constraint `CHECK` bảo vệ invariant ở database ngay cả khi một đường ghi khác bỏ qua service.

## 9. Ví dụ: chuyển tiền cần nhiều câu lệnh trong một transaction

Chuyển tiền gồm ít nhất hai thay đổi:

1. Trừ tiền tài khoản nguồn.
2. Cộng tiền tài khoản đích.

Hai thay đổi phải cùng commit hoặc cùng rollback. Nếu trừ tiền thành công nhưng cộng tiền thất bại, không được để số dư bị mất.

```java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        if (fromId.equals(toId)) {
            return Mono.error(new IllegalArgumentException(
                    "Source and destination must differ"));
        }
        if (amount == null || amount.signum() <= 0) {
            return Mono.error(new IllegalArgumentException(
                    "Amount must be positive"));
        }

        return accountRepository.debitIfSufficient(fromId, amount)
                .flatMap(debited -> {
                    if (debited != 1) {
                        return Mono.error(
                                new InsufficientBalanceException(fromId));
                    }

                    return accountRepository.credit(toId, amount)
                            .flatMap(credited -> credited == 1
                                    ? Mono.<Void>empty()
                                    : Mono.error(new AccountNotFoundException(toId)));
                });
    }
}
```

`credit` có thể được khai báo bằng modifying query:

```java
@Modifying
@Query("UPDATE account SET balance = balance + :amount, version = version + 1 WHERE id = :accountId")
Mono<Integer> credit(
        @Param("accountId") Long accountId,
        @Param("amount") BigDecimal amount);
```

Nếu tài khoản nguồn không đủ tiền, service phát lỗi trước khi cộng tiền. Nếu tài khoản đích không tồn tại, service phát lỗi sau khi đã trừ nguồn; reactive transaction sẽ rollback thay đổi nguồn nếu lỗi đi qua transaction boundary và cả hai thao tác dùng cùng `ConnectionFactory`/transaction manager.

Đoạn code chỉ minh họa transaction local trong một database. Nếu tài khoản nguồn và đích ở hai database khác nhau, một `R2dbcTransactionManager` không thể bảo đảm atomicity cho cả hai. Khi đó cần quy trình phân tán như saga hoặc một giải pháp transaction đa tài nguyên được hỗ trợ rõ ràng.

## 10. Chuyển trạng thái bằng compare-and-set

Một use case thường chỉ cho phép chuyển trạng thái khi bản ghi đang ở trạng thái mong đợi. Ví dụ, đơn hàng chỉ được xác nhận khi đang `PENDING`:

```sql
UPDATE purchase_order
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PENDING';
```

Nếu hai request cùng xác nhận một đơn hàng, request đầu tiên có thể cập nhật hàng từ `PENDING` sang `CONFIRMED`. Request sau đó không còn thỏa điều kiện `status = 'PENDING'` nên số hàng bị tác động là 0.

Repository:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = 'CONFIRMED',
        confirmed_at = CURRENT_TIMESTAMP
    WHERE id = :orderId
      AND status = 'PENDING'
    """)
Mono<Integer> confirmIfPending(@Param("orderId") Long orderId);
```

Service có thể diễn giải `1` là chuyển trạng thái thành công, `0` là trạng thái không còn phù hợp hoặc đơn hàng không tồn tại. Nếu cần phân biệt “không tồn tại” với “đã được xác nhận”, có thể đọc trạng thái sau khi nhận 0 hoặc dùng một câu lệnh có `RETURNING` để trả dữ liệu theo khả năng database.

Mẫu này cũng hữu ích cho:

- Chỉ claim một job đang `READY`.
- Chỉ phát hành hóa đơn chưa phát hành.
- Chỉ đánh dấu token chưa sử dụng.
- Chỉ xử lý message chưa được xử lý.
- Chỉ hủy đặt chỗ nếu trạng thái còn `PENDING`.

## 11. Kết hợp version trong điều kiện cập nhật

Optimistic locking là một cách kiểm soát cập nhật đồng thời. Spring Data Relational hỗ trợ `@Version` khi lưu entity qua repository. Với custom SQL hoặc bulk update, ứng dụng cần tự đưa version vào câu lệnh.

Ví dụ bảng:

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

Một request đọc document có `version = 7`. Khi lưu thay đổi, câu lệnh compare-and-set là:

```sql
UPDATE document
SET title = :title,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Nếu request khác đã cập nhật version lên 8, câu lệnh với `expectedVersion = 7` không khớp và không cập nhật hàng nào.

Repository:

```java
@Modifying
@Query("""
    UPDATE document
    SET title = :title,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
    """)
Mono<Integer> updateTitleIfVersionMatches(
        @Param("id") Long id,
        @Param("title") String title,
        @Param("expectedVersion") Long expectedVersion);
```

Diễn giải:

- `1`: ID tồn tại và version khớp; cập nhật thành công.
- `0`: ID không tồn tại hoặc version đã thay đổi.
- Lớn hơn `1`: có vấn đề với giả định ID duy nhất hoặc schema/query.

Nếu dùng `@Version` và `repository.save(entity)`, Spring Data có thể tự xây dựng điều kiện version. Nếu dùng `@Modifying`, không nên giả định cơ chế optimistic locking của entity tự chạy; phải đưa điều kiện version và thao tác tăng version vào SQL.

## 12. Phân biệt rows matched và rows changed

Thuật ngữ “số hàng bị tác động” không hoàn toàn giống nhau giữa mọi database. Một số hệ quản trị báo số hàng khớp điều kiện; một số driver/cấu hình có thể báo số hàng thực sự thay đổi giá trị. Ví dụ, MySQL có thể trả số hàng changed hoặc found tùy cấu hình client; PostgreSQL command tag cho UPDATE báo số hàng được xử lý, kể cả khi giá trị được gán bằng giá trị cũ.

Vì vậy, với câu lệnh:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = :id;
```

nếu customer đã có `status = 'ACTIVE'`, kết quả rows affected có thể phụ thuộc semantics của database/driver. Không nên dùng `rows == 0` để kết luận chắc chắn “ID không tồn tại” nếu statement có thể khớp nhưng không làm thay đổi giá trị.

Để kết quả rõ ràng hơn, có thể:

- Thiết kế câu lệnh chỉ khớp khi cần chuyển trạng thái thực sự, ví dụ thêm `AND status <> 'ACTIVE'`.
- Dùng `RETURNING` nếu database hỗ trợ và cần biết hàng nào đã được cập nhật.
- Kiểm thử semantics với đúng phiên bản database và driver.
- Đặt tên kết quả theo ý nghĩa thực tế, chẳng hạn `rowsAffected`, không gọi là `entitiesChanged` nếu chưa xác minh.

## 13. Khi số hàng bằng 0: xử lý kết quả nghiệp vụ

Số 0 không nhất thiết là lỗi database. Nó thường cho biết điều kiện cập nhật không còn đúng hoặc không có hàng phù hợp.

Ví dụ kiểm soát số dư:

```java
return accountRepository.debitIfSufficient(accountId, amount)
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.just(DebitResult.success());
            }
            if (rows == 0) {
                return accountRepository.findById(accountId)
                        .map(account -> DebitResult.insufficientFunds())
                        .defaultIfEmpty(DebitResult.accountNotFound());
            }
            return Mono.error(new IllegalStateException(
                    "Unexpected rows affected: " + rows));
        });
```

Ví dụ này thực hiện truy vấn đọc sau khi UPDATE trả 0 để phân biệt account không tồn tại và account tồn tại nhưng không đủ số dư. Đây là thông tin chẩn đoán sau thao tác; trạng thái có thể tiếp tục thay đổi bởi request khác ngay sau lần đọc. Nếu nghiệp vụ cần mã lý do chính xác tại cùng thời điểm, hãy thiết kế một câu lệnh database trả kết quả có phân loại hoặc dùng cơ chế khóa/transaction phù hợp.

Không nên phát lỗi hệ thống cho mọi trường hợp rows bằng 0. Có thể đó là kết quả nghiệp vụ bình thường như “job đã được worker khác claim” hoặc “đơn hàng đã được xử lý”.

## 14. Điều kiện cập nhật không thay thế constraint database

Conditional UPDATE bảo vệ một thao tác cụ thể. Database constraint bảo vệ dữ liệu trước mọi đường ghi.

Ví dụ:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
```

`CHECK (available >= 0)` ngăn dữ liệu âm bất kể câu lệnh đến từ repository, SQL console hay một service khác. Câu UPDATE có `available >= :quantity` bảo vệ use case giữ hàng và giúp nhận biết thao tác thành công bằng số hàng bị tác động.

Các constraint thường dùng:

- `PRIMARY KEY` bảo đảm định danh duy nhất và không null.
- `UNIQUE` bảo đảm không có hai hàng trùng giá trị theo quy tắc unique.
- `NOT NULL` ngăn giá trị SQL NULL.
- `CHECK` bảo đảm một biểu thức trên từng hàng luôn đúng.
- `FOREIGN KEY` bảo đảm tham chiếu giữa các bảng theo schema.

Không nên chỉ dựa vào validation Java để bảo vệ invariant quan trọng như số dư không âm hoặc email duy nhất. Nhiều request và nhiều ứng dụng có thể ghi đồng thời; constraint database là lớp bảo vệ cuối cùng.

## 15. Điều kiện theo tenant và quyền sở hữu

Conditional UPDATE còn giúp đưa điều kiện tenant hoặc owner vào câu lệnh, giảm nguy cơ sửa nhầm dữ liệu:

```sql
UPDATE purchase_order
SET status = 'CANCELLED'
WHERE id = :orderId
  AND customer_id = :authenticatedCustomerId
  AND status = 'PENDING';
```

Ở đây, câu lệnh chỉ thay đổi đơn hàng nếu ID, khách hàng sở hữu và trạng thái đều khớp. `authenticatedCustomerId` phải được lấy từ ngữ cảnh xác thực đã được kiểm tra, không lấy trực tiếp từ một field tùy ý trong request.

Nếu rows affected bằng 0, có thể đơn hàng không tồn tại, không thuộc khách hàng hoặc đã đổi trạng thái. Nhiều API cố tình không phân biệt hai trường hợp không tồn tại và không có quyền để tránh tiết lộ sự tồn tại của tài nguyên.

Điều kiện SQL không thay thế toàn bộ authorization. Các quy tắc phức tạp vẫn cần được kiểm tra ở tầng ứng dụng/domain, và các query đọc cũng phải áp dụng phạm vi tenant phù hợp.

## 16. Bulk update và số hàng bị tác động

Một câu UPDATE có thể tác động nhiều hàng:

```sql
UPDATE task
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND expires_at < :now;
```

`rowsUpdated` có thể trả `0`, `1` hoặc số lớn hơn. Trong trường hợp bulk operation, số hàng là một thông tin hữu ích để ghi log, đo lường hoặc xác nhận phạm vi tác động.

Ví dụ repository:

```java
@Modifying
@Query("""
    UPDATE task
    SET status = 'EXPIRED'
    WHERE status = 'PENDING'
      AND expires_at < :now
    """)
Mono<Integer> expirePendingTasks(@Param("now") OffsetDateTime now);
```

Service:

```java
public Mono<Integer> expireTasks(OffsetDateTime now) {
    return taskRepository.expirePendingTasks(now)
            .doOnNext(rows -> log.info("Expired {} tasks", rows));
}
```

Bulk update không tải từng entity vào Java, do đó domain method, entity callback, auditing hoặc optimistic locking tự động của từng entity không nhất thiết được áp dụng. Nếu cần các hành vi đó, hãy đưa chúng vào SQL hoặc chọn quy trình load-mutate-save.

## 17. Transaction khi một use case có nhiều conditional update

Một câu conditional UPDATE đơn lẻ thường đã được database thực thi nguyên tử ở cấp statement. Nếu use case gồm nhiều câu lệnh cần thành công cùng nhau, cần reactive transaction.

Ví dụ chuyển tiền:

```java
@Transactional
public Mono<Void> transfer(Long sourceId, Long targetId, BigDecimal amount) {
    return accountRepository.debitIfSufficient(sourceId, amount)
            .flatMap(debited -> {
                if (debited != 1) {
                    return Mono.error(new InsufficientBalanceException(sourceId));
                }

                return accountRepository.credit(targetId, amount)
                        .flatMap(credited -> credited == 1
                                ? Mono.<Void>empty()
                                : Mono.error(new AccountNotFoundException(targetId)));
            });
}
```

Nếu credit thất bại và lỗi đi qua transaction boundary, debit có thể được rollback. Cả hai repository phải sử dụng cùng `ConnectionFactory` và reactive transaction manager.

Không gọi `subscribe()` bên trong method transactional. Hãy trả publisher và nối các thao tác bằng `flatMap`, `then` hoặc toán tử phù hợp để Spring theo dõi lifecycle commit/rollback.

Transaction không làm cho hai database độc lập trở thành một tài nguyên nguyên tử. Nếu nguồn và đích nằm ở hai hệ thống, cần saga hoặc quy trình bù trừ.

## 18. Isolation level và concurrent UPDATE

Conditional UPDATE hoạt động cùng cơ chế concurrency control của database. Khi nhiều transaction cùng cập nhật một hàng, hệ quản trị có thể dùng row lock, MVCC hoặc cơ chế tương đương để điều phối.

Một số lưu ý:

- Ở `READ COMMITTED`, statement thường đánh giá điều kiện dựa trên trạng thái mà database cho phép nhìn thấy tại thời điểm thực hiện statement; chi tiết xử lý cạnh tranh phụ thuộc hệ quản trị.
- Ở `REPEATABLE READ` hoặc `SERIALIZABLE`, một số xung đột có thể khiến transaction bị từ chối hoặc cần retry thay vì chỉ trả rows bằng 0.
- Không nên dựa vào một isolation level chung cho mọi database mà không kiểm thử semantics thực tế.
- Khi database báo deadlock hoặc serialization failure, ứng dụng có thể cần retry toàn bộ transaction với giới hạn và backoff.

Điều kiện cập nhật và constraint giúp làm rõ quy tắc ở database. Isolation level xác định thêm cách các transaction cạnh tranh được nhìn thấy và xử lý.

## 19. Retry và idempotency

Khi gặp lỗi tạm thời như serialization failure hoặc deadlock, retry có thể giúp use case hoàn tất. Tuy nhiên, không nên retry mù quáng mọi lỗi hoặc mọi conditional update.

Ví dụ:

- Một UPDATE chuyển trạng thái `PENDING` sang `CONFIRMED` có điều kiện. Nếu request đầu tiên đã commit nhưng response bị mất, retry có thể trả 0 vì trạng thái không còn `PENDING`. Ứng dụng cần cách xác định request trước đã thành công hay chưa.
- Một UPDATE trừ số dư không có idempotency key. Nếu client gửi lại sau timeout không rõ transaction đã commit hay chưa, có nguy cơ trừ tiền lần thứ hai.
- Một job được claim bằng điều kiện `status = 'READY'` có thể được worker khác claim trước; rows 0 có thể là kết quả bình thường chứ không phải lỗi cần retry liên tục.

Với thao tác tài chính hoặc lệnh có thể được gửi lại, nên dùng idempotency key hoặc bảng ghi nhận request duy nhất. Một transaction có thể lưu kết quả xử lý theo key cùng thay đổi nghiệp vụ để lần gọi lặp trả lại kết quả đã ghi nhận.

Retry cần:

- Chỉ áp dụng cho lỗi được xác định là có thể thử lại.
- Có giới hạn số lần và backoff.
- Chạy lại toàn bộ transaction nếu lỗi làm transaction hiện tại rollback.
- Bảo đảm use case idempotent hoặc có cơ chế chống xử lý trùng.
- Không retry lỗi nghiệp vụ như không đủ số dư hoặc trạng thái không còn phù hợp.

## 20. Khi cần RETURNING thay vì chỉ đếm hàng

Một số hệ quản trị như PostgreSQL hỗ trợ `UPDATE ... RETURNING` để trả dữ liệu của hàng sau khi cập nhật:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :productId
  AND available >= :quantity
RETURNING product_id, available, version;
```

Nếu ứng dụng cần số lượng còn lại sau khi giữ hàng, `RETURNING` giúp lấy kết quả trong cùng statement thay vì chạy thêm một SELECT sau UPDATE.

Với `DatabaseClient`, có thể map các hàng trả về:

```java
public Mono<InventorySnapshot> reserveAndRead(
        DatabaseClient databaseClient,
        Long productId,
        int quantity) {

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity,
                version = version + 1
            WHERE product_id = :productId
              AND :quantity > 0
              AND available >= :quantity
            RETURNING product_id, available, version
            """)
            .bind("productId", productId)
            .bind("quantity", quantity)
            .map((row, metadata) -> new InventorySnapshot(
                    row.get("product_id", Long.class),
                    row.get("available", Integer.class),
                    row.get("version", Long.class)))
            .one();
}
```

Nếu không có hàng thỏa điều kiện, `one()` có thể hoàn tất rỗng. Ví dụ dùng cú pháp PostgreSQL `RETURNING`; database khác có thể không hỗ trợ hoặc có cú pháp khác.

`@Modifying` thường phù hợp khi chỉ cần số hàng bị tác động. Nếu cần trả row đã cập nhật, dùng `DatabaseClient` hoặc custom repository để tiêu thụ result rows thay vì giả định modifying query tự ánh xạ `RETURNING` thành entity.

## 21. Kiểm thử cập nhật đồng thời

Unit test đơn lẻ xác nhận điều kiện đúng nhưng không chứng minh được hành vi khi nhiều request cạnh tranh. Cần integration test chạy nhiều publisher đồng thời trên database thực tế.

Ví dụ kiểm tra kho chỉ còn một request có thể giữ số lượng vượt phần còn lại:

```java
Mono<Integer> requestA = inventoryRepository.reserveIfAvailable(100L, 4);
Mono<Integer> requestB = inventoryRepository.reserveIfAvailable(100L, 3);

StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(results -> {
            int totalUpdated = results.getT1() + results.getT2();
            assertEquals(1, totalUpdated);
        })
        .verifyComplete();
```

Ví dụ giả định kho ban đầu có 5 sản phẩm và mỗi statement chỉ tác động tối đa một hàng. Một request cập nhật 1 hàng; request còn lại cập nhật 0 hàng. Sau đó cần đọc lại để xác nhận `available` không âm và `reserved` chỉ tăng theo một request thành công.

`Mono.zip` subscribe hai publisher cùng lúc, nhưng cách scheduler, connection pool và database thực thi thực tế vẫn ảnh hưởng độ đồng thời của test. Với test concurrency đáng tin cậy, cần dùng nhiều connection/transaction phù hợp, lặp lại tình huống và kiểm tra invariant cuối cùng, không chỉ dựa vào một lần chạy.

Những trường hợp nên kiểm thử:

- Hai request cùng giữ hàng nhưng tổng lượng yêu cầu vượt tồn kho.
- Hai request cùng trừ số dư tài khoản.
- Hai request cùng chuyển trạng thái từ `PENDING`.
- Hai request cập nhật cùng version.
- Request lặp lại sau timeout hoặc sau khi response bị mất.
- Số hàng bị tác động khi ID không tồn tại.
- Số hàng bị tác động khi gán cùng giá trị hiện tại.
- Constraint `CHECK`, `UNIQUE` và foreign key khi có cạnh tranh.
- Rollback khi câu lệnh thứ hai trong transaction thất bại.

## 22. Quan sát và chẩn đoán

Khi conditional update trả kết quả bất thường, nên ghi nhận các thông tin đủ để phân tích mà không làm lộ dữ liệu nhạy cảm:

- Loại thao tác và tên use case.
- Khóa định danh đã được che/mã hóa theo chính sách log.
- Số hàng bị tác động.
- Thời gian thực thi statement.
- Loại lỗi database nếu có.
- Số lần retry và lý do retry.
- Version mong đợi nếu thao tác dùng optimistic locking.

Không nên log số dư, token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết. Với thao tác có rows 0, metric có thể phân loại theo use case như `insufficient_inventory`, `version_conflict` hoặc `already_processed` nếu ứng dụng xác định được lý do một cách đáng tin cậy.

Nếu UPDATE chậm, hãy xem execution plan và index cho các cột trong điều kiện WHERE. Ví dụ:

```sql
CREATE INDEX ix_task_status_due_at
    ON task(status, expires_at);
```

Với truy vấn theo khóa chính, index primary key thường đã có. Không nên tạo index trùng lặp nếu đã có index phù hợp; mỗi index làm tăng chi phí ghi và dung lượng.

## 23. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Hai request cùng giữ vượt tồn kho | Đọc rồi tính rồi ghi bằng giá trị cũ | Dùng UPDATE có điều kiện `available >= quantity` |
| Số hàng bằng 0 nhưng ID có tồn tại | Điều kiện trạng thái, version hoặc số dư không còn khớp | Diễn giải 0 là điều kiện không khớp; đọc thêm nếu cần phân loại |
| Số hàng lớn hơn 1 khi cập nhật một ID | Điều kiện không duy nhất hoặc schema thiếu constraint | Kiểm tra khóa chính/unique và WHERE |
| Gán cùng giá trị nhưng rows là 0 | Database/driver báo số hàng thực sự thay đổi | Kiểm tra semantics rows matched/changed của database |
| Cập nhật bulk không tăng version | Custom SQL bỏ qua cơ chế `@Version` tự động | Tăng version và so sánh expected version trong SQL |
| Update thành công nhưng entity trong Java vẫn cũ | Custom modifying query không đồng bộ object đang nằm trong bộ nhớ | Đọc lại hoặc dùng RETURNING |
| Retry làm trừ tiền hai lần | Request không idempotent hoặc không có idempotency key | Ghi nhận request duy nhất cùng transaction |
| Trừ nguồn nhưng không cộng đích | Hai câu lệnh không cùng transaction hoặc lỗi bị nuốt | Dùng reactive transaction và để lỗi đi qua boundary |
| Dữ liệu vẫn âm dù service đã kiểm tra | Có đường ghi khác bỏ qua logic Java | Thêm CHECK constraint và điều kiện SQL |
| Câu UPDATE ảnh hưởng toàn bảng | Thiếu điều kiện WHERE hoặc tham số không đúng | Kiểm tra query, bind và số hàng; dùng test trước khi triển khai |

## 24. Quy trình thiết kế conditional update

Khi một use case cần cập nhật dựa trên trạng thái hiện tại, hãy thực hiện theo trình tự:

1. Xác định invariant cần bảo vệ, ví dụ số dư không âm, tồn kho không âm hoặc chỉ chuyển trạng thái một lần.
2. Xác định các điều kiện phải đúng tại thời điểm cập nhật.
3. Đưa các điều kiện đó vào `WHERE` của cùng câu UPDATE.
4. Tính giá trị mới trực tiếp từ cột hiện tại trong SQL, tránh ghi đè bằng snapshot cũ trong Java.
5. Lấy `rowsUpdated` hoặc kiểu kết quả phù hợp để biết statement có khớp hàng hay không.
6. Quy định rõ ý nghĩa của 0, 1 và lớn hơn 1 theo cardinality nghiệp vụ.
7. Bổ sung `CHECK`, `UNIQUE`, `NOT NULL` hoặc foreign key để bảo vệ dữ liệu ở schema.
8. Nếu có nhiều câu lệnh phải nguyên tử, dùng reactive transaction cùng `ConnectionFactory` và transaction manager.
9. Nếu dùng version, so sánh version mong đợi và tăng version trong cùng statement.
10. Thiết kế idempotency và retry có giới hạn cho request có thể gửi lại.
11. Kiểm thử cạnh tranh với database và driver thực tế, đồng thời kiểm tra invariant sau khi nhiều request chạy đồng thời.

Kiểm soát đồng thời bằng điều kiện cập nhật đặt quy tắc ngay tại nơi dữ liệu được thay đổi. `WHERE` xác định trạng thái nào được phép cập nhật; phép tính trong `SET` sử dụng giá trị hiện tại của hàng; số hàng bị tác động cho biết có bao nhiêu hàng khớp với thao tác theo semantics của database/driver. Kết hợp conditional UPDATE với constraint, version, transaction và idempotency giúp Spring Data R2DBC xử lý các tình huống cạnh tranh như giữ tồn kho, trừ số dư và chuyển trạng thái mà không phụ thuộc vào một lần đọc cũ trong ứng dụng.
