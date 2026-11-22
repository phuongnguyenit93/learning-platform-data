# Lost update và thiết kế khóa lạc quan bằng cột phiên bản

Khi nhiều transaction cùng đọc rồi cập nhật một hàng, một lần ghi có thể vô tình ghi đè kết quả của lần ghi trước. Hiện tượng này gọi là **lost update** (mất cập nhật). Ứng dụng thường gặp lỗi khi đọc dữ liệu vào bộ nhớ, tính giá trị mới ở tầng Java, rồi ghi lại giá trị tuyệt đối mà không kiểm tra dữ liệu đã thay đổi hay chưa.

Một cách phát hiện tình huống đó là **khóa lạc quan** (optimistic locking) bằng cột phiên bản `version`. Mỗi lần cập nhật thành công, ứng dụng tăng phiên bản. Câu `UPDATE` chỉ được phép ghi nếu phiên bản trong cơ sở dữ liệu vẫn bằng phiên bản mà ứng dụng đã đọc. Nếu có transaction khác cập nhật trước, điều kiện không còn khớp và ứng dụng nhận biết xung đột thay vì âm thầm ghi đè.

Đây là kỹ thuật quan trọng khi xây dựng hệ thống MySQL có nhiều người dùng cùng sửa dữ liệu, chẳng hạn số lượng tồn kho, hồ sơ khách hàng, trạng thái đơn hàng hoặc nội dung được nhiều nhân viên cập nhật.

## 1. Lost update xảy ra như thế nào?

Giả sử bảng `inventory` đang có số lượng sản phẩm là `10`. Hai transaction A và B cùng đọc số lượng này. A muốn giảm 2 đơn vị, B muốn giảm 3 đơn vị. Cả hai ứng dụng đều tính giá trị mới trong bộ nhớ:

- A đọc `10`, tính `10 - 2 = 8`.
- B đọc `10`, tính `10 - 3 = 7`.
- A ghi `8` và commit.
- B ghi `7` và commit sau đó.

Kết quả cuối cùng là `7`, trong khi nếu cả hai lần giảm đều được áp dụng thì số lượng phải là `5`. Lần cập nhật của A đã bị lần ghi sau của B ghi đè.

| Thời điểm | Transaction A | Transaction B | Giá trị trong bảng |
|---|---|---|---:|
| 1 | Đọc số lượng `10` |  | 10 |
| 2 |  | Đọc số lượng `10` | 10 |
| 3 | Tính giá trị mới `8` | Tính giá trị mới `7` | 10 |
| 4 | Ghi `8`, commit |  | 8 |
| 5 |  | Ghi `7`, commit | 7 |

Vấn đề nằm ở chỗ B ghi một giá trị được tính từ dữ liệu cũ mà không xác nhận hàng vẫn ở trạng thái B đã đọc. Nếu câu lệnh ghi là phép biến đổi trực tiếp trên cột, ví dụ `SET quantity = quantity - 3`, MySQL sẽ áp dụng phép trừ trên giá trị hiện tại của hàng sau khi lấy khóa ghi; tình huống ghi đè bằng giá trị cũ trong bộ nhớ được tránh. Tuy nhiên, với nghiệp vụ cần đọc, kiểm tra, tính toán ở ứng dụng rồi ghi lại, vẫn cần cơ chế phát hiện dữ liệu đã đổi.

## 2. Tạo cột phiên bản

Thêm một cột `version` vào bảng cần bảo vệ. Có thể dùng `BIGINT` để có không gian tăng lớn:

```sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

Khi tạo một hàng mới, `version` bắt đầu từ `0`. Giá trị này đại diện cho phiên bản trạng thái của hàng tại thời điểm đọc. Mỗi lần thay đổi thành công một hàng, ứng dụng tăng `version` lên một đơn vị.

Nếu bảng đã có dữ liệu, có thể bổ sung cột bằng lệnh:

```sql
ALTER TABLE inventory
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Các hàng hiện tại nhận phiên bản ban đầu `0`. Từ thời điểm triển khai khóa lạc quan, mọi đường ghi cần tuân thủ quy tắc tăng phiên bản.

## 3. Cập nhật có điều kiện theo phiên bản

Quy trình khóa lạc quan có ba bước:

1. Đọc dữ liệu và giá trị `version` hiện tại.
2. Tính toán thay đổi dựa trên dữ liệu đã đọc.
3. Cập nhật với điều kiện `WHERE version = phiên_bản_đã_đọc`, đồng thời tăng phiên bản trong cùng câu lệnh.

Ví dụ ứng dụng đọc hàng tồn kho:

```sql
SELECT product_id, quantity, version
FROM inventory
WHERE product_id = 9001;
```

Giả sử kết quả là `quantity = 10` và `version = 4`. Ứng dụng muốn đặt số lượng thành `8`. Câu lệnh cập nhật phải kiểm tra phiên bản:

```sql
UPDATE inventory
SET quantity = 8,
    version = version + 1
WHERE product_id = 9001
  AND version = 4;
```

Sau khi thực thi, ứng dụng kiểm tra số hàng bị ảnh hưởng:

- **Một hàng được cập nhật:** phiên bản vẫn khớp. Thay đổi thành công; phiên bản mới là `5`.
- **Không có hàng nào được cập nhật:** hàng có thể đã bị xóa hoặc phiên bản đã thay đổi sau lần đọc. Đây là xung đột cần xử lý.

Điều kiện so khớp phiên bản và phép tăng phiên bản nằm trong cùng một câu `UPDATE`, nên MySQL kiểm tra và thay đổi hàng theo cơ chế đồng thời của InnoDB. Hai transaction cùng đọc phiên bản `4` có thể cùng gửi câu lệnh trên, nhưng chỉ một câu lệnh có thể cập nhật hàng từ phiên bản `4` lên `5`. Câu lệnh còn lại không còn thỏa `version = 4` và cập nhật `0` hàng.

Mẫu tổng quát:

```sql
UPDATE some_table
SET business_column = ?,
    version = version + 1
WHERE primary_key = ?
  AND version = ?;
```

Không được bỏ điều kiện phiên bản ở các đường cập nhật khác. Nếu một màn hình dùng khóa lạc quan nhưng một tác vụ nền vẫn cập nhật dữ liệu mà không tăng `version`, cơ chế phát hiện xung đột sẽ không còn đáng tin cậy.

## 4. Mô phỏng hai transaction cạnh tranh

Giả sử ban đầu hàng có `quantity = 10`, `version = 4`. Cả A và B đều đọc phiên bản `4`:

```sql
-- Transaction A: ứng dụng đã đọc version = 4
UPDATE inventory
SET quantity = 8,
    version = version + 1
WHERE product_id = 9001 AND version = 4;
-- A cập nhật 1 hàng, version trở thành 5
```

Sau khi A commit, B chạy lệnh dựa trên phiên bản cũ:

```sql
-- Transaction B: ứng dụng cũng đã đọc version = 4
UPDATE inventory
SET quantity = 7,
    version = version + 1
WHERE product_id = 9001 AND version = 4;
-- B cập nhật 0 hàng vì version hiện tại đã là 5
```

Nhờ điều kiện phiên bản, B không thể ghi đè thay đổi của A. Ứng dụng B cần tải lại dữ liệu mới, thông báo xung đột hoặc tính toán lại theo quy tắc nghiệp vụ.

## 5. Xử lý xung đột trong ứng dụng Java/JDBC

Trong JDBC, `executeUpdate()` trả về số hàng bị ảnh hưởng. Với câu lệnh khóa lạc quan luôn tăng `version`, kết quả `1` nghĩa là cập nhật thành công; kết quả `0` nghĩa là không có hàng nào thỏa khóa chính và phiên bản đã đọc.

Ví dụ dưới đây minh họa việc đọc và cập nhật trong cùng một transaction:

```java
connection.setAutoCommit(false);

try {
    int quantity;
    long version;

    String selectSql = """
        SELECT quantity, version
        FROM inventory
        WHERE product_id = ?
        """;

    try (PreparedStatement select = connection.prepareStatement(selectSql)) {
        select.setLong(1, 9001L);

        try (ResultSet rs = select.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Không tìm thấy sản phẩm");
            }
            quantity = rs.getInt("quantity");
            version = rs.getLong("version");
        }
    }

    int newQuantity = quantity - 2;
    String updateSql = """
        UPDATE inventory
        SET quantity = ?, version = version + 1
        WHERE product_id = ? AND version = ?
        """;

    try (PreparedStatement update = connection.prepareStatement(updateSql)) {
        update.setInt(1, newQuantity);
        update.setLong(2, 9001L);
        update.setLong(3, version);

        int affectedRows = update.executeUpdate();
        if (affectedRows == 0) {
            throw new OptimisticLockException("Dữ liệu đã được thay đổi");
        }
    }

    connection.commit();
} catch (SQLException | RuntimeException e) {
    connection.rollback();
    throw e;
}
```

`OptimisticLockException` trong ví dụ là ngoại lệ nghiệp vụ do ứng dụng định nghĩa hoặc thay bằng kiểu ngoại lệ phù hợp với framework đang dùng. Mã minh họa tập trung vào cách kiểm tra số hàng bị ảnh hưởng; ứng dụng thực tế cũng cần quản lý trạng thái `autoCommit`, rollback khi có lỗi và đóng tài nguyên theo đúng vòng đời của `Connection`.

Nếu cập nhật thất bại do xung đột, có một số cách xử lý:

- Tải lại hàng mới nhất, hiển thị dữ liệu mới và yêu cầu người dùng xác nhận lại.
- Tự động tính toán lại rồi thử cập nhật lần nữa nếu nghiệp vụ cho phép.
- Trả lỗi xung đột cho API để client tải lại dữ liệu.

Không nên lặp vô hạn hoặc gửi lại nguyên giá trị đã tính từ dữ liệu cũ. Nếu thử lại, phải đọc phiên bản và trạng thái mới, sau đó tính toán lại. Giới hạn số lần retry và có khoảng chờ phù hợp để tránh nhiều client liên tục tranh chấp cùng một hàng.

## 6. Khóa lạc quan cho cập nhật và xóa

Khóa lạc quan áp dụng được cho thao tác xóa. Nếu ứng dụng đọc hàng ở phiên bản `12`, câu lệnh xóa phải so khớp phiên bản đó:

```sql
DELETE FROM inventory
WHERE product_id = 9001
  AND version = 12;
```

Nếu một người khác đã sửa hàng và tăng phiên bản lên `13`, lệnh xóa không tác động hàng nào. Ứng dụng có thể báo rằng bản ghi đã thay đổi và yêu cầu tải lại trước khi xóa.

Với cập nhật nhiều bảng trong cùng nghiệp vụ, hãy dùng một transaction. Nếu một trong các câu lệnh cập nhật theo phiên bản trả về `0` hàng, rollback toàn bộ transaction để không lưu một phần thay đổi:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = 7001
  AND version = 3;

-- Ứng dụng kiểm tra ROW_COUNT() ngay sau UPDATE.
-- Nếu kết quả không phải 1: ROLLBACK.

UPDATE reservations
SET status = 'ALLOCATED',
    version = version + 1
WHERE reservation_id = 8001
  AND version = 6;

-- Tiếp tục kiểm tra số hàng bị ảnh hưởng.
-- Chỉ COMMIT nếu tất cả điều kiện phiên bản đều khớp.

COMMIT;
```

Trong ứng dụng, nên lấy số hàng bị ảnh hưởng từ API thực thi câu lệnh thay vì dựa vào một truy vấn khác chạy muộn hơn. Nếu dùng `ROW_COUNT()` trong SQL, phải đọc ngay sau câu lệnh `UPDATE` tương ứng vì câu lệnh tiếp theo có thể thay đổi kết quả của hàm.

## 7. Khi nào nên dùng cập nhật nguyên tử thay vì khóa phiên bản?

Không phải mọi phép cập nhật đều cần đọc dữ liệu về ứng dụng rồi dùng `version`. Nếu nghiệp vụ chỉ là tăng hoặc giảm một giá trị số, có thể biểu diễn phép biến đổi trực tiếp trong SQL:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001
  AND quantity >= 2;
```

Điều kiện và phép trừ được thực hiện trên hàng hiện tại trong cùng câu lệnh. Số hàng bị ảnh hưởng là `1` nếu giảm thành công, `0` nếu không có sản phẩm hoặc số lượng không đủ. Cách này tránh mô hình đọc `10` về ứng dụng rồi ghi giá trị tuyệt đối `8`.

Nếu vẫn cần tăng phiên bản để các màn hình đang mở phát hiện dữ liệu thay đổi, có thể kết hợp:

```sql
UPDATE inventory
SET quantity = quantity - 2,
    version = version + 1
WHERE product_id = 9001
  AND quantity >= 2;
```

Khóa lạc quan phù hợp hơn khi ứng dụng cần kiểm tra nhiều trường, tính toán ở tầng nghiệp vụ hoặc bảo vệ thao tác sửa dựa trên một bản đọc trước đó. Cập nhật nguyên tử phù hợp với phép biến đổi đơn giản có thể biểu diễn đầy đủ bằng một câu SQL.

## 8. Khóa lạc quan và khóa bi quan

InnoDB cung cấp khóa hàng để điều phối các thao tác ghi đồng thời. Một cách tiếp cận khác là khóa bi quan (pessimistic locking): lấy khóa ngay khi đọc để transaction khác phải chờ trước khi sửa cùng hàng.

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 9001
FOR UPDATE;

-- Kiểm tra và tính toán khi đang giữ khóa hàng.
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;

COMMIT;
```

| Tiêu chí | Khóa lạc quan bằng `version` | Khóa bi quan bằng `FOR UPDATE` |
|---|---|---|
| Thời điểm phát hiện/tránh xung đột | Phát hiện tại lúc cập nhật nếu phiên bản đã đổi | Giữ khóa để transaction khác phải chờ |
| Phù hợp khi | Xung đột ít, thời gian xử lý ngoài DB tương đối dài | Tranh chấp cao hoặc cần tuần tự hóa thao tác đọc rồi ghi |
| Chi phí chính | Có thể phải tải lại và thử lại khi xung đột | Có thể chờ khóa, tăng thời gian giữ khóa và nguy cơ deadlock |
| Yêu cầu triển khai | Mọi đường ghi phải kiểm tra và tăng `version` | Transaction phải giữ khóa đến khi hoàn tất hoặc rollback |

Không có lựa chọn tốt nhất cho mọi tình huống. Nếu nhiều người thường xuyên cập nhật cùng một hàng và retry tốn kém, khóa bi quan có thể hợp lý. Nếu phần lớn thao tác không xung đột và ứng dụng có thể xử lý trường hợp dữ liệu cũ, khóa lạc quan thường giúp giảm thời gian giữ khóa.

## 9. Các quy tắc thiết kế cần giữ

1. **Tăng phiên bản trong chính câu lệnh cập nhật.** Không tách việc cập nhật dữ liệu và tăng `version` thành hai câu lệnh độc lập.
2. **Mọi đường ghi đều tuân thủ.** API, tác vụ nền, công cụ quản trị và batch job cùng sửa bảng đều phải tăng phiên bản hoặc có quy trình phối hợp tương đương.
3. **Không tái sử dụng phiên bản cũ.** Khi xung đột, phải tải lại dữ liệu và phiên bản mới trước khi thử lại.
4. **Kiểm tra số hàng bị ảnh hưởng.** Một hàng là thành công; không có hàng là xung đột hoặc bản ghi không còn tồn tại. Nếu khóa chính bảo đảm duy nhất, kết quả lớn hơn một cho thấy giả định hoặc câu lệnh có vấn đề.
5. **Giữ transaction ngắn.** Nếu có nhiều thao tác liên quan, thực hiện chúng trong transaction ngắn và rollback toàn bộ khi một bước kiểm tra phiên bản thất bại.
6. **Không coi isolation level là cơ chế thay thế version.** Mức cô lập điều khiển cách các transaction quan sát dữ liệu; cột phiên bản xác nhận bản ghi ứng dụng định sửa vẫn là phiên bản mà nó đã đọc.

## 10. Tự kiểm tra

1. Lost update xảy ra như thế nào khi hai ứng dụng cùng đọc một giá trị rồi ghi lại các giá trị tuyệt đối?
2. Vì sao điều kiện `WHERE version = ?` giúp phát hiện một lần cập nhật đã xảy ra sau lần đọc?
3. Trong mẫu khóa lạc quan, vì sao phải tăng `version` trong cùng câu `UPDATE`?
4. `executeUpdate()` trả về `0` có thể biểu thị những tình huống nào?
5. Khi phát hiện xung đột, vì sao không nên retry bằng giá trị đã tính từ dữ liệu cũ?
6. Trường hợp nào nên dùng cập nhật nguyên tử bằng SQL hoặc khóa bi quan thay cho khóa lạc quan?

