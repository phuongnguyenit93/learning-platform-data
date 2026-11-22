# Sửa lỗi mất cập nhật bằng cập nhật nguyên tử và kiểm tra phiên bản

Lỗi mất cập nhật (*lost update*) xảy ra khi hai giao dịch cùng đọc một giá trị cũ, tự tính toán giá trị mới trong ứng dụng rồi ghi đè lên nhau. Mỗi giao dịch có thể hoàn tất mà không báo lỗi, nhưng kết quả cuối cùng làm mất một thay đổi đã được giao dịch khác thực hiện.

Có hai cách sửa phổ biến, tùy kiểu nghiệp vụ:

- **Cập nhật nguyên tử (atomic update):** để database thực hiện phép tính trực tiếp trên giá trị hiện tại, ví dụ `SET quantity = quantity - 3`. Cách này phù hợp với bộ đếm, số lượng tồn kho và phép cập nhật có thể diễn đạt bằng một câu lệnh có điều kiện.
- **Kiểm tra phiên bản (optimistic version check):** ứng dụng đọc dữ liệu kèm `version`, sau đó chỉ ghi nếu phiên bản vẫn đúng như lúc đọc. Cách này phù hợp khi người dùng hoặc chương trình đọc một đối tượng, tính toán/chỉnh sửa trong một khoảng thời gian rồi mới lưu.

Hai cách giải quyết cùng một nhóm vấn đề nhưng có mục đích khác nhau. Atomic update bảo vệ phép biến đổi trên giá trị hiện tại; version check phát hiện dữ liệu đã đổi kể từ lúc ứng dụng đọc và cho phép xử lý xung đột một cách rõ ràng.

## 1. Hiểu lỗi mất cập nhật

Giả sử kho còn 10 sản phẩm. Hai khách hàng cùng mua hàng gần như đồng thời:

- Giao dịch A mua 3 sản phẩm.
- Giao dịch B mua 4 sản phẩm.

Kết quả đúng phải là (10 - 3 - 4 = 3) sản phẩm còn lại.

Một cách viết dễ mắc lỗi là đọc số lượng vào ứng dụng, trừ trong bộ nhớ rồi ghi lại giá trị tuyệt đối:

```sql
SELECT Quantity
FROM dbo.Inventory
WHERE ProductId = 1;

-- Ứng dụng đọc Quantity = 10 và tính quantity mới trong bộ nhớ.
-- Sau đó ghi lại giá trị đã tính.
UPDATE dbo.Inventory
SET Quantity = 7
WHERE ProductId = 1;
```

Nếu A và B đều đọc được `10`, A tính `7`, B tính `6`. Nếu B ghi `6` trước rồi A ghi `7` sau, kết quả cuối là `7`. Thay đổi của B bị mất dù câu `UPDATE` của B đã thành công.

```text
Giá trị ban đầu: Quantity = 10

Session A                          Session B
-------------------------------------------------------
SELECT -> 10
                                   SELECT -> 10
tính 10 - 3 = 7
                                   tính 10 - 4 = 6
                                   UPDATE Quantity = 6
                                   COMMIT
UPDATE Quantity = 7
COMMIT

Kết quả cuối: 7
Kết quả đúng: 3
```

Đây là lost update ở tầng ứng dụng: hai câu `UPDATE` riêng lẻ đều hợp lệ, nhưng mỗi câu ghi một giá trị đã tính từ cùng một trạng thái cũ.

## 2. Chuẩn bị bài thực hành hai phiên SQL Server

Mở hai query window riêng trong SQL Server Management Studio (SSMS), cùng kết nối một SQL Server instance và cùng database thử nghiệm. Thay `YourTestDatabase` bằng tên database của bạn. Chạy phần setup một lần.

```sql
USE YourTestDatabase;
GO

IF OBJECT_ID(N'dbo.LostUpdateInventoryLab', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LostUpdateInventoryLab
    (
        ProductId INT NOT NULL
            CONSTRAINT PK_LostUpdateInventoryLab PRIMARY KEY,
        Quantity INT NOT NULL,
        VersionNo BIGINT NOT NULL
            CONSTRAINT DF_LostUpdateInventoryLab_Version DEFAULT (0),
        CONSTRAINT CK_LostUpdateInventoryLab_Quantity
            CHECK (Quantity >= 0)
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.LostUpdateInventoryLab
    WHERE ProductId = 1
)
BEGIN
    INSERT INTO dbo.LostUpdateInventoryLab
        (ProductId, Quantity, VersionNo)
    VALUES (1, 10, 0);
END;
GO

IF OBJECT_ID(N'dbo.LostUpdateDocumentLab', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LostUpdateDocumentLab
    (
        DocumentId INT NOT NULL
            CONSTRAINT PK_LostUpdateDocumentLab PRIMARY KEY,
        Title NVARCHAR(200) NOT NULL,
        VersionNo BIGINT NOT NULL
            CONSTRAINT DF_LostUpdateDocumentLab_Version DEFAULT (0)
    );
END;
GO

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.LostUpdateDocumentLab
    WHERE DocumentId = 1
)
BEGIN
    INSERT INTO dbo.LostUpdateDocumentLab
        (DocumentId, Title, VersionNo)
    VALUES (1, N'Bản nháp ban đầu', 0);
END;
GO

SELECT @@SPID AS SessionId, DB_NAME() AS DatabaseName;
SELECT * FROM dbo.LostUpdateInventoryLab WHERE ProductId = 1;
SELECT * FROM dbo.LostUpdateDocumentLab WHERE DocumentId = 1;
```

Ghi lại `SessionId` ở mỗi cửa sổ. Hai giá trị phải khác nhau. Nếu hai tab cùng dùng một connection, bạn chưa có hai session độc lập.

## 3. Thí nghiệm 1: tái hiện lost update bằng read-modify-write

Đầu tiên, đưa số lượng về 10:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = 10,
    VersionNo = 0
WHERE ProductId = 1;
```

Mục tiêu là để cả hai session cùng đọc `Quantity = 10` trước khi một session ghi kết quả. Dùng `WAITFOR` để tạo khoảng thời gian dễ quan sát.

### Session A

Chạy A trước:

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;

DECLARE @QuantityRead INT;

SELECT @QuantityRead = Quantity
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;

SELECT N'Session A đã đọc' AS StepName,
       @QuantityRead AS QuantityRead;

-- Chờ để Session B cũng đọc giá trị cũ và ghi trước.
WAITFOR DELAY '00:00:15';

UPDATE dbo.LostUpdateInventoryLab
SET Quantity = @QuantityRead - 3
WHERE ProductId = 1;

SELECT N'Session A đã ghi' AS StepName,
       ProductId, Quantity, VersionNo
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;
```

### Session B

Ngay sau khi A bắt đầu chờ, chạy B:

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;

DECLARE @QuantityRead INT;

SELECT @QuantityRead = Quantity
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;

SELECT N'Session B đã đọc' AS StepName,
       @QuantityRead AS QuantityRead;

-- B ghi sớm hơn A.
WAITFOR DELAY '00:00:05';

UPDATE dbo.LostUpdateInventoryLab
SET Quantity = @QuantityRead - 4
WHERE ProductId = 1;

SELECT N'Session B đã ghi' AS StepName,
       ProductId, Quantity, VersionNo
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;
```

Kịch bản mong đợi:

1. A đọc 10 và chờ 15 giây.
2. B đọc 10, chờ 5 giây, rồi ghi 6.
3. A tiếp tục và ghi 7 dựa trên giá trị 10 cũ.
4. Kết quả cuối là 7, trong khi hai lần bán tổng cộng 7 sản phẩm nên kết quả đúng phải là 3.

Kiểm tra:

```sql
SELECT ProductId, Quantity, VersionNo
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;
```

`VersionNo` vẫn là 0 vì hai câu lệnh sai không tăng version. Bài thực hành dùng autocommit cho từng câu SQL; khoảng đọc và ghi trong ứng dụng nằm ngoài một transaction bao trùm. Dù vậy, lỗi vẫn xuất hiện vì giá trị cũ được giữ trong biến ứng dụng rồi ghi lại sau.

Nếu thứ tự chạy không đúng dự kiến, đặt lại `Quantity = 10` và chạy lại A rồi B trong khoảng chờ của A.

## 4. Sửa lỗi bộ đếm và tồn kho bằng atomic update

Với phép tăng/giảm một giá trị số, không cần đọc giá trị vào ứng dụng rồi ghi lại kết quả tuyệt đối. Hãy để database tính từ giá trị hiện hành trong cùng câu lệnh:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - 3
WHERE ProductId = 1;
```

Nếu hai session cùng thực hiện `Quantity = Quantity - n`, database điều phối cập nhật trên hàng. Mỗi câu lệnh áp dụng phép trừ lên giá trị mới nhất khi nó được thực hiện, nên hai thay đổi không ghi đè kết quả tính từ cùng một bản đọc cũ.

Với nghiệp vụ bán hàng, cần bảo đảm không trừ xuống số âm. Hãy đưa điều kiện vào cùng câu `UPDATE`:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - @RequestedQuantity
WHERE ProductId = @ProductId
  AND Quantity >= @RequestedQuantity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- `1` hàng: trừ kho thành công.
- `0` hàng: sản phẩm không tồn tại hoặc không đủ số lượng; nếu cần phân biệt hai trường hợp, truy vấn thêm bằng logic phù hợp.

Điều kiện kiểm tra và phép trừ nằm trong cùng statement nên không có khoảng trống giữa bước kiểm tra tồn kho và bước ghi số lượng.

### Thí nghiệm 2: hai session cập nhật nguyên tử

Đặt lại dữ liệu:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = 10,
    VersionNo = 0
WHERE ProductId = 1;
```

Chạy Session A:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - 3
WHERE ProductId = 1
  AND Quantity >= 3;

SELECT @@ROWCOUNT AS RowsUpdated;
```

Chạy Session B gần như đồng thời:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - 4
WHERE ProductId = 1
  AND Quantity >= 4;

SELECT @@ROWCOUNT AS RowsUpdated;
```

Nếu cả hai statement đều thành công, kiểm tra kết quả:

```sql
SELECT ProductId, Quantity
FROM dbo.LostUpdateInventoryLab
WHERE ProductId = 1;
```

Kết quả phải là `3`, bất kể A hay B được database thực hiện trước. Nếu tổng số lượng yêu cầu vượt quá tồn kho, một statement có thể cập nhật 0 hàng; không có số lượng âm.

### Vì sao atomic update giải quyết được lỗi?

Trong câu lệnh:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - 3
WHERE ProductId = 1;
```

`Quantity` ở vế phải được database đánh giá trong thao tác cập nhật trên hàng hiện tại. Khi hai transaction cạnh tranh cùng hàng, engine điều phối quyền ghi. Transaction sau áp dụng phép trừ trên giá trị mà nó được phép cập nhật, không ghi lại một số tuyệt đối đã tính từ bản đọc cũ ở ứng dụng.

Atomic update phù hợp với:

- Tăng/giảm bộ đếm.
- Trừ số lượng tồn kho có điều kiện.
- Cộng điểm hoặc số dư theo một phép biến đổi đơn giản.
- Cập nhật trạng thái theo điều kiện hiện tại.
- Ghi nhận lượt xem, lượt tải hoặc số lần thử.

Nó không tự giải quyết mọi nghiệp vụ đọc nhiều hàng rồi ra quyết định phức tạp. Nếu quy tắc phụ thuộc nhiều bản ghi hoặc nhiều bảng, cần transaction và cơ chế bảo vệ bất biến tương ứng.

## 5. Sửa lỗi chỉnh sửa đối tượng bằng optimistic version check

Atomic arithmetic không phù hợp khi ứng dụng đọc một đối tượng gồm nhiều trường, cho người dùng chỉnh sửa rồi gửi lại toàn bộ giá trị. Trong trường hợp này, ghi một giá trị tuyệt đối có thể ghi đè thay đổi mới của người khác.

Giải pháp là lưu cột `VersionNo`. Khi đọc, ứng dụng nhận cả dữ liệu và version. Khi ghi, ứng dụng yêu cầu version vẫn bằng giá trị đã đọc.

```sql
SELECT DocumentId, Title, VersionNo
FROM dbo.LostUpdateDocumentLab
WHERE DocumentId = 1;
```

Giả sử hai người dùng cùng đọc `VersionNo = 0` và tiêu đề `Bản nháp ban đầu`. Người dùng A sửa thành `Bản nháp của A`; B sửa thành `Bản nháp của B`.

Khi A lưu:

```sql
UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp của A',
    VersionNo = VersionNo + 1
WHERE DocumentId = 1
  AND VersionNo = 0;
```

Nếu statement cập nhật một hàng, A thành công và version trở thành 1. Khi B lưu với version cũ:

```sql
UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp của B',
    VersionNo = VersionNo + 1
WHERE DocumentId = 1
  AND VersionNo = 0;
```

Điều kiện `VersionNo = 0` không còn đúng, nên B cập nhật 0 hàng. B phát hiện xung đột thay vì âm thầm ghi đè A.

## 6. Thí nghiệm 3: hai session cùng sửa một phiên bản

Đặt lại dữ liệu:

```sql
UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp ban đầu',
    VersionNo = 0
WHERE DocumentId = 1;
```

### Session A — đọc version, sau đó cập nhật

Chạy A trước:

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;

DECLARE @VersionRead BIGINT;

SELECT @VersionRead = VersionNo
FROM dbo.LostUpdateDocumentLab
WHERE DocumentId = 1;

SELECT N'Session A đã đọc version' AS StepName,
       @VersionRead AS VersionRead;

WAITFOR DELAY '00:00:15';

UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp của A',
    VersionNo = VersionNo + 1
WHERE DocumentId = 1
  AND VersionNo = @VersionRead;

SELECT @@ROWCOUNT AS RowsUpdatedByA;
```

### Session B — cập nhật sớm hơn với version đã đọc

Chạy B trong lúc A đang chờ:

```sql
USE YourTestDatabase;
GO
SET NOCOUNT ON;

DECLARE @VersionRead BIGINT;

SELECT @VersionRead = VersionNo
FROM dbo.LostUpdateDocumentLab
WHERE DocumentId = 1;

SELECT N'Session B đã đọc version' AS StepName,
       @VersionRead AS VersionRead;

WAITFOR DELAY '00:00:05';

UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp của B',
    VersionNo = VersionNo + 1
WHERE DocumentId = 1
  AND VersionNo = @VersionRead;

SELECT @@ROWCOUNT AS RowsUpdatedByB;
```

Kết quả mong đợi:

1. A đọc version 0 và chờ.
2. B đọc version 0, chờ 5 giây rồi cập nhật thành công; version thành 1.
3. A tiếp tục sau 15 giây. Điều kiện `VersionNo = 0` không còn đúng, nên `RowsUpdatedByA = 0`.
4. Bản ghi cuối cùng giữ tiêu đề của B và version 1.

Kiểm tra:

```sql
SELECT DocumentId, Title, VersionNo
FROM dbo.LostUpdateDocumentLab
WHERE DocumentId = 1;
```

Đây là hành vi mong muốn: ứng dụng biết dữ liệu đã thay đổi và có thể yêu cầu người dùng tải lại, hợp nhất hoặc xác nhận ghi đè theo quy tắc nghiệp vụ.

## 7. Phân biệt atomic update và version check

| Tiêu chí | Atomic update | Optimistic version check |
|---|---|---|
| Cách làm | Database áp dụng phép biến đổi trên giá trị hiện tại | Ghi chỉ khi version vẫn bằng version đã đọc |
| Phù hợp | Bộ đếm, tồn kho, phép cộng/trừ đơn giản | Chỉnh sửa đối tượng hoặc dữ liệu được tính toán ngoài database |
| Phát hiện xung đột | Thường không cần báo conflict nếu phép biến đổi có thể áp dụng tuần tự | Có: affected rows = 0 hoặc ORM ném optimistic lock exception |
| Cách xử lý khi không thành công | Kiểm tra điều kiện nghiệp vụ, ví dụ không đủ hàng | Đọc lại, hợp nhất hoặc báo conflict |
| Giá trị ghi | Biểu thức dựa trên cột hiện tại | Giá trị mới kèm điều kiện version cũ |
| Ví dụ | `SET quantity = quantity - @n` | `WHERE id = @id AND version = @expected` |

Có thể kết hợp hai kỹ thuật. Ví dụ, cập nhật tồn kho nguyên tử và đồng thời tăng version để các client đang giữ bản đọc cũ biết dữ liệu đã thay đổi:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - @RequestedQuantity,
    VersionNo = VersionNo + 1
WHERE ProductId = @ProductId
  AND Quantity >= @RequestedQuantity;
```

Nếu client cần phát hiện chính xác dữ liệu đã thay đổi kể từ lần đọc của mình, thêm điều kiện version:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - @RequestedQuantity,
    VersionNo = VersionNo + 1
WHERE ProductId = @ProductId
  AND Quantity >= @RequestedQuantity
  AND VersionNo = @ExpectedVersion;
```

Khi đó statement chỉ thành công nếu cả điều kiện tồn kho và version đều đúng.

## 8. Java JDBC: kiểm tra số hàng được cập nhật

Với JDBC, phương thức `executeUpdate()` trả về số hàng bị ảnh hưởng. Đây là tín hiệu để ứng dụng biết atomic update hoặc version check có thành công không.

```java
String sql = """
    UPDATE inventory
    SET quantity = quantity - ?,
        version_no = version_no + 1
    WHERE product_id = ?
      AND quantity >= ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, requestedQuantity);
    statement.setLong(2, productId);
    statement.setInt(3, requestedQuantity);

    int updatedRows = statement.executeUpdate();

    if (updatedRows == 1) {
        // Đã trừ tồn kho thành công.
    } else if (updatedRows == 0) {
        // Không đủ hàng hoặc sản phẩm không tồn tại.
    } else {
        throw new IllegalStateException("Unexpected row count: " + updatedRows);
    }
}
```

Trong transaction nhiều bước, hãy kiểm tra kết quả rồi quyết định commit hoặc rollback toàn bộ nghiệp vụ. Đừng bỏ qua `updatedRows == 0` rồi tiếp tục tạo đơn hàng như thể hàng đã được giữ.

Ví dụ version check:

```java
String sql = """
    UPDATE customer_profile
    SET display_name = ?,
        address = ?,
        version_no = version_no + 1
    WHERE id = ?
      AND version_no = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, newDisplayName);
    statement.setString(2, newAddress);
    statement.setLong(3, profileId);
    statement.setLong(4, expectedVersion);

    int updatedRows = statement.executeUpdate();
    if (updatedRows == 0) {
        throw new OptimisticConflictException(profileId);
    }
}
```

`OptimisticConflictException` ở đây là exception nghiệp vụ minh họa. Ứng dụng cần ánh xạ conflict sang phản hồi phù hợp, ví dụ HTTP `409 Conflict` cho API chỉnh sửa.

## 9. JPA/Hibernate: dùng @Version

Với JPA, có thể đánh dấu một thuộc tính là `@Version`. Hibernate dùng version trong câu `UPDATE` và tăng version khi ghi entity.

```java
@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String displayName;

    private String address;
}
```

Khi hai transaction cùng đọc entity version 4:

1. Transaction A cập nhật entity và ghi với điều kiện version vẫn là 4; database tăng version lên 5.
2. Transaction B cố ghi entity còn mang version 4; câu `UPDATE` không cập nhật hàng nào.
3. Hibernate phát hiện số hàng cập nhật không đúng và ném `OptimisticLockException` hoặc exception Spring tương ứng ở thời điểm flush/commit.

Không phải lúc nào exception cũng xuất hiện ngay tại dòng gọi `repository.save()`. JPA có thể trì hoãn SQL đến flush hoặc commit. Vì vậy, xử lý conflict ở ranh giới transaction/service và không coi `save()` trả về là bằng chứng transaction đã commit thành công.

Ví dụ service:

```java
@Service
public class ProfileService {
    private final CustomerProfileRepository repository;

    @Transactional
    public void updateProfile(
            Long id,
            long expectedVersion,
            String displayName,
            String address) {

        CustomerProfile profile = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Profile not found"));

        if (!profile.getVersion().equals(expectedVersion)) {
            throw new OptimisticConflictException(id);
        }

        profile.setDisplayName(displayName);
        profile.setAddress(address);
        // @Version vẫn là lớp kiểm tra cuối tại thời điểm flush/update.
    }
}
```

So sánh version trong bộ nhớ giúp phản hồi sớm, nhưng không thay thế `@Version`: một transaction khác vẫn có thể cập nhật sau phép so sánh và trước khi transaction hiện tại flush. Cơ chế optimistic lock của ORM mới thực hiện kiểm tra nguyên tử ở database.

## 10. Tại sao không chỉ tăng isolation level?

Isolation level quyết định khả năng quan sát dữ liệu đồng thời và cách engine điều phối khóa/version. Nó không tự động biến một chuỗi đọc vào ứng dụng, tính toán rồi ghi lại giá trị tuyệt đối thành phép cập nhật nguyên tử.

Trong SQL Server, `READ COMMITTED` cho phép shared lock đọc được giải phóng khi statement kết thúc (nếu RCSI tắt); do đó một ứng dụng có thể đọc giá trị, tính toán trong bộ nhớ và ghi lại sau đó trong một statement khác, tạo lost update.

Các mức khác có hành vi khác:

- `REPEATABLE READ` giữ khóa chia sẻ trên hàng đã đọc đến cuối transaction. Hai transaction cùng đọc rồi cùng nâng khóa để ghi có thể chờ nhau hoặc deadlock khi chuyển từ shared lock sang exclusive lock.
- `SERIALIZABLE` bổ sung bảo vệ phạm vi/predicate nhưng không làm biến mất mọi vấn đề thiết kế; nâng khóa đồng thời vẫn có thể dẫn tới deadlock.
- `SNAPSHOT` phát hiện xung đột cập nhật trên cùng hàng trong một số tình huống bằng update conflict; nó không thay thế việc định nghĩa rõ cách xử lý xung đột ở tầng nghiệp vụ.

Atomic update và version predicate diễn đạt trực tiếp ý định của thao tác tại câu lệnh ghi, giúp kết quả dễ kiểm tra hơn. Chọn isolation level vẫn quan trọng cho các bất biến liên quan nhiều hàng hoặc nhiều câu lệnh.

## 11. Chọn cách sửa theo nghiệp vụ

### Dùng atomic update khi phép biến đổi có thể diễn đạt trực tiếp

Ví dụ:

```sql
-- Tăng số lượt xem.
UPDATE article
SET view_count = view_count + 1
WHERE article_id = @ArticleId;

-- Trừ số lượng tồn kho nếu đủ.
UPDATE inventory
SET quantity = quantity - @Quantity
WHERE product_id = @ProductId
  AND quantity >= @Quantity;

-- Chuyển trạng thái chỉ khi trạng thái hiện tại còn là READY.
UPDATE job_queue
SET status = 'RUNNING'
WHERE job_id = @JobId
  AND status = 'READY';
```

Mỗi câu lệnh thực hiện điều kiện và thay đổi trong cùng một statement. Kiểm tra row count để biết thao tác có được áp dụng hay không.

### Dùng version check khi cần phát hiện chỉnh sửa cũ

Ví dụ:

- Người dùng mở hồ sơ rồi chỉnh sửa vài phút sau mới lưu.
- Hai nhân viên cùng sửa nội dung một tài liệu.
- Một tiến trình đọc cấu hình, xử lý rồi cập nhật sau một bước tính toán.
- API nhận `If-Match`/ETag và chỉ chấp nhận update nếu representation chưa đổi.

Khi version không khớp, đừng ghi đè tự động. Đọc lại dữ liệu mới, so sánh thay đổi, hợp nhất hoặc trả conflict để người dùng quyết định.

### Dùng khóa bi quan khi cần điều phối trước

Nếu xung đột thường xuyên và nghiệp vụ cần đọc trạng thái mới nhất rồi thực hiện nhiều bước ngắn trong cùng transaction, có thể dùng locking read như SQL Server `UPDLOCK` hoặc `SELECT ... FOR UPDATE` trên hệ quản trị hỗ trợ. Giữ transaction ngắn và xác định rõ thứ tự lấy khóa.

Ví dụ SQL Server:

```sql
BEGIN TRANSACTION;

SELECT Quantity
FROM dbo.LostUpdateInventoryLab WITH (UPDLOCK, ROWLOCK)
WHERE ProductId = 1;

-- Ứng dụng kiểm tra và tính toán trong transaction.

UPDATE dbo.LostUpdateInventoryLab
SET Quantity = Quantity - 2
WHERE ProductId = 1
  AND Quantity >= 2;

COMMIT TRANSACTION;
```

`UPDLOCK` yêu cầu update lock khi đọc và giữ đến cuối transaction, giúp tránh hai transaction cùng lấy shared lock rồi cùng nâng lên exclusive lock. Tuy nhiên, nó tạo chờ khóa rõ ràng và vẫn cần xử lý timeout/deadlock. Với phép trừ đơn giản, atomic conditional update thường ngắn gọn hơn.

## 12. Xử lý khi version không khớp

Khi `UPDATE ... WHERE version = @expectedVersion` cập nhật 0 hàng, có thể xảy ra các trường hợp:

- Hàng đã bị xóa.
- Hàng tồn tại nhưng version đã tăng do transaction khác cập nhật.
- Điều kiện bổ sung khác không còn đúng.

Nếu API cần phân biệt, có thể đọc lại hàng trong một transaction mới hoặc dùng kết quả truy vấn phù hợp. Không nên chỉ coi mọi `0 rows` là optimistic conflict nếu câu lệnh còn có các điều kiện nghiệp vụ khác.

Các cách xử lý thường gặp:

1. **Trả conflict:** phù hợp với chỉnh sửa do người dùng, ví dụ HTTP 409.
2. **Tải lại và hợp nhất:** hiển thị giá trị mới và cho người dùng chọn cách giải quyết.
3. **Tính toán lại:** phù hợp với công việc tự động nếu toàn bộ quyết định có thể tính lại từ dữ liệu mới.
4. **Bỏ qua hoặc đánh dấu stale:** phù hợp với tác vụ nền mà dữ liệu mới khiến công việc cũ không còn cần thiết.

Không retry cùng payload và cùng version cũ vì điều kiện sẽ tiếp tục không khớp. Muốn retry phải đọc phiên bản mới và đánh giá lại nghiệp vụ.

## 13. Retry an toàn và giới hạn

Atomic update thất bại do điều kiện `Quantity >= @RequestedQuantity` thường là kết quả nghiệp vụ như không đủ hàng; không nên retry liên tục. Version mismatch là xung đột dữ liệu; có thể đọc lại và tính lại nếu nghiệp vụ cho phép. Deadlock hoặc serialization failure là lỗi concurrency tạm thời có thể retry toàn bộ transaction nếu thao tác an toàn khi lặp.

Một chính sách retry cần:

- Phân loại lỗi nghiệp vụ và lỗi concurrency tạm thời.
- Giới hạn tổng số lần thử và deadline.
- Dùng backoff có jitter nếu nhiều request cùng tranh chấp.
- Chạy lại toàn bộ đơn vị nghiệp vụ phụ thuộc vào dữ liệu đã đọc, không chỉ lặp câu `UPDATE` cuối cùng với giá trị cũ.
- Bảo vệ side effect bên ngoài bằng idempotency key hoặc outbox.
- Ghi lại số lần thử và nguyên nhân conflict để phát hiện điểm nóng.

Không nên tự động retry vô hạn một thao tác cập nhật do người dùng chỉnh sửa; điều đó có thể âm thầm ghi đè thay đổi của người khác.

## 14. Những lỗi triển khai thường gặp

- **Đọc, tính toán trong ứng dụng rồi ghi số tuyệt đối:** dễ ghi đè cập nhật của transaction khác.
- **Có cột version nhưng không đưa vào WHERE:** cột version không bảo vệ gì nếu câu lệnh không kiểm tra nó.
- **Không tăng version ở mọi đường ghi:** batch job hoặc SQL thủ công bỏ qua version làm cơ chế optimistic lock mất hiệu lực.
- **Kiểm tra version trong bộ nhớ nhưng UPDATE không có điều kiện version:** vẫn có race condition giữa check và write.
- **Bỏ qua số hàng được cập nhật:** worker hoặc request thua cuộc vẫn tiếp tục nghiệp vụ như thể update thành công.
- **Retry với version cũ:** lần thử tiếp tục thất bại hoặc ghi sai nếu bỏ điều kiện.
- **Nhầm conflict với không đủ hàng:** cần phân biệt nguyên nhân theo điều kiện và kết quả nghiệp vụ.
- **Dùng atomic update cho một quy tắc nhiều hàng phức tạp:** một câu lệnh trên một hàng không tự bảo vệ bất biến trải rộng nhiều hàng.
- **Dùng isolation level cao mà không xử lý deadlock:** locking/conversion vẫn có thể gây deadlock và cần retry phù hợp.

## 15. Quy trình thực hành tổng hợp

Thực hiện theo thứ tự sau và ghi lại kết quả mỗi bước:

1. Chạy setup và xác nhận `Quantity = 10`, `VersionNo = 0`.
2. Mở hai session độc lập; xác nhận `@@SPID` khác nhau.
3. Chạy bài read-modify-write: A mua 3, B mua 4. Ghi lại giá trị cả hai session đọc và kết quả cuối. Quan sát lost update.
4. Đặt lại số lượng về 10.
5. Chạy atomic conditional update ở hai session. Xác nhận kết quả cuối là 3 nếu cả hai đều đủ điều kiện.
6. Đặt lại tài liệu về version 0.
7. Chạy bài version check: A và B cùng đọc version 0; B cập nhật trước; A cập nhật sau. Xác nhận chỉ một session cập nhật được một hàng.
8. Đọc lại tài liệu và giải thích vì sao session thua cuộc phải tải lại hoặc báo conflict.
9. Thử thay đổi số lượng yêu cầu vượt tồn kho để xác nhận atomic update trả 0 hàng thay vì tạo số lượng âm.
10. Dọn dữ liệu về trạng thái ban đầu nếu cần.

### Bảng kết quả cần ghi

| Bài | Session A | Session B | Kết quả mong đợi |
|---|---|---|---|
| Read-modify-write | Đọc 10, ghi 7 | Đọc 10, ghi 6 trước A | Một cập nhật bị ghi đè; kết quả cuối sai là 7 |
| Atomic update | Trừ 3 | Trừ 4 | Cả hai được áp dụng; còn 3 |
| Version check | Đọc version 0, cập nhật sau | Đọc version 0, cập nhật trước | B cập nhật 1 hàng; A cập nhật 0 hàng và phát hiện conflict |

## 16. Dọn dẹp

Đưa dữ liệu thực hành về trạng thái ban đầu:

```sql
UPDATE dbo.LostUpdateInventoryLab
SET Quantity = 10,
    VersionNo = 0
WHERE ProductId = 1;

UPDATE dbo.LostUpdateDocumentLab
SET Title = N'Bản nháp ban đầu',
    VersionNo = 0
WHERE DocumentId = 1;
```

Nếu không cần giữ các bảng lab trong database thử nghiệm:

```sql
DROP TABLE IF EXISTS dbo.LostUpdateDocumentLab;
DROP TABLE IF EXISTS dbo.LostUpdateInventoryLab;
```

Chỉ chạy `DROP TABLE` khi chắc chắn đây là bảng được tạo riêng cho bài thực hành.

## 17. Những điểm cần nhớ

- Lost update xuất hiện khi nhiều transaction đọc cùng giá trị cũ rồi ghi lại các giá trị tuyệt đối được tính riêng trong ứng dụng.
- Với bộ đếm hoặc phép cộng/trừ đơn giản, dùng atomic update như `SET quantity = quantity - @n`.
- Kết hợp điều kiện nghiệp vụ trong cùng statement, ví dụ `quantity >= @n`, rồi kiểm tra số hàng bị ảnh hưởng.
- Với chỉnh sửa đối tượng dựa trên dữ liệu đã đọc từ trước, dùng version predicate `WHERE id = @id AND version = @expected`.
- Tăng version trong cùng câu `UPDATE`; mọi đường ghi phải tuân theo quy ước version.
- `@Version` trong JPA/Hibernate cung cấp optimistic locking, nhưng conflict có thể chỉ xuất hiện tại flush/commit.
- Version mismatch phải dẫn đến đọc lại, hợp nhất hoặc báo conflict; không lặp lại payload cũ với version cũ.
- Isolation level cao có thể thay đổi cách khóa và phát hiện xung đột, nhưng không thay thế việc viết câu lệnh cập nhật đúng ý định.
- Dùng khóa bi quan cho trường hợp cần điều phối trước và transaction có thể giữ ngắn; xử lý deadlock/timeout vẫn cần thiết.
- Với bất biến nhiều hàng, cần transaction, constraint hoặc cơ chế khóa phù hợp; atomic update trên một hàng không đủ cho mọi quy tắc.

Để sửa lost update, hãy chọn cách ghi phù hợp với bản chất dữ liệu. Nếu chỉ cần thay đổi một giá trị số, để database thực hiện phép tính nguyên tử trên giá trị hiện tại và kiểm tra điều kiện trong cùng statement. Nếu ứng dụng cần lưu một bản chỉnh sửa dựa trên dữ liệu đã đọc trước đó, kèm version trong câu `UPDATE` để phát hiện ai đó đã thay đổi dữ liệu. Cả hai cách đều biến xung đột đồng thời thành kết quả có thể kiểm tra và xử lý thay vì âm thầm làm mất cập nhật.
