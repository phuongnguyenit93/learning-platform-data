# Affected rows và nhận diện trường hợp dữ liệu không thay đổi

Trong MySQL, một câu lệnh thay đổi dữ liệu có thể chạy thành công nhưng số dòng bị ảnh hưởng bằng 0. Trường hợp này thường xuất hiện khi `UPDATE` tìm thấy bản ghi nhưng giá trị mới giống giá trị đang lưu, hoặc khi điều kiện `WHERE` không khớp bản ghi nào. Nếu chỉ nhìn vào con số trả về mà không hiểu cách MySQL đếm dòng, ứng dụng có thể báo sai trạng thái cập nhật hoặc xử lý nhầm xung đột dữ liệu.

Module `DATABASE_MYSQL` hướng đến việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; người học cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Thay đổi dữ liệu**, hiểu đúng *affected rows* giúp kiểm tra kết quả của `INSERT`, `UPDATE`, `DELETE` và xây dựng logic ứng dụng an toàn khi nhiều người dùng cùng thao tác dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt số dòng khớp điều kiện (*matched rows*) với số dòng thực sự thay đổi (*changed rows*).
- Đọc kết quả DML và lấy số dòng bằng `ROW_COUNT()`.
- Giải thích vì sao một câu lệnh `UPDATE` thành công nhưng báo 0 dòng bị ảnh hưởng.
- Nhận biết ảnh hưởng của cấu hình `CLIENT_FOUND_ROWS` và cách đếm của một số câu lệnh ghi dữ liệu đặc biệt.
- Dùng affected rows để kiểm tra cập nhật có điều kiện, phát hiện xung đột và phối hợp với transaction.

## 1. Affected rows là gì?

*Affected rows* là số dòng mà MySQL báo đã bị tác động bởi câu lệnh vừa thực thi. Ý nghĩa cụ thể phụ thuộc vào loại câu lệnh và cấu hình kết nối. Với `UPDATE`, cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Matched rows | Số dòng thỏa mãn điều kiện `WHERE`. |
| Changed rows | Số dòng mà giá trị lưu trữ thực sự thay đổi sau khi thực hiện `SET`. |
| Affected rows | Số dòng mà MySQL trả về cho client hoặc hàm đếm; với `UPDATE`, mặc định là số dòng changed. Cấu hình kết nối có thể làm số này phản ánh matched rows. |

Ví dụ, bảng có một sản phẩm với `quantity = 10`. Câu lệnh sau tìm thấy sản phẩm, nhưng gán lại đúng giá trị đang có:

```sql
UPDATE inventory
SET quantity = 10
WHERE sku = 'KB-01';
```

Có một dòng khớp điều kiện, nhưng không có giá trị nào thay đổi. Theo mặc định, MySQL báo 0 dòng bị ảnh hưởng. Đây là một câu lệnh hợp lệ và thực thi thành công; con số 0 không tự động có nghĩa là lỗi SQL.

Ngược lại, nếu không có sản phẩm mang mã `UNKNOWN`, câu lệnh sau cũng báo 0:

```sql
UPDATE inventory
SET quantity = 5
WHERE sku = 'UNKNOWN';
```

Hai tình huống có cùng affected rows nhưng nguyên nhân khác nhau:

- **Có dòng khớp, không có thay đổi:** câu lệnh tìm thấy dòng nhưng giá trị sau cập nhật giống giá trị hiện tại.
- **Không có dòng khớp:** điều kiện `WHERE` không chọn được dòng nào để cập nhật.

Vì vậy, affected rows bằng 0 là một tín hiệu cần diễn giải theo điều kiện truy vấn và trạng thái dữ liệu, không phải một kết luận đầy đủ về nguyên nhân.

## 2. Thực hành nhận diện ba kết quả của UPDATE

Ta tạo một bảng tồn kho nhỏ để quan sát kết quả:

```sql
CREATE TABLE inventory (
    id       BIGINT PRIMARY KEY AUTO_INCREMENT,
    sku      VARCHAR(30) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (sku, quantity)
VALUES
    ('KB-01', 10),
    ('MS-02', 5),
    ('HD-03', 0);
```

### Trường hợp A: Có dòng khớp nhưng dữ liệu không đổi

```sql
UPDATE inventory
SET quantity = 10
WHERE sku = 'KB-01';

SELECT ROW_COUNT() AS affected_rows;
```

Kết quả mặc định:

```text
affected_rows
-------------
0
```

Điều kiện `sku = 'KB-01'` khớp một dòng. Tuy nhiên, `quantity` vốn đã bằng 10 nên không có thay đổi thực tế. Trong MySQL client, phần thông tin của câu lệnh cập nhật có thể hiển thị riêng số dòng khớp và số dòng thay đổi, chẳng hạn `Rows matched: 1  Changed: 0`.

### Trường hợp B: Có dòng khớp và dữ liệu thực sự đổi

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'KB-01'
  AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;
```

Kết quả:

```text
affected_rows
-------------
1
```

Một dòng được tìm thấy và `quantity` đổi từ 10 thành 9. Affected rows là 1, dù câu lệnh có thể cập nhật nhiều cột cùng lúc; MySQL đếm dòng bị ảnh hưởng, không đếm số cột thay đổi.

### Trường hợp C: Không có dòng nào khớp

```sql
UPDATE inventory
SET quantity = 5
WHERE sku = 'UNKNOWN';

SELECT ROW_COUNT() AS affected_rows;
```

Kết quả là 0 vì không có dòng nào thỏa mãn điều kiện. Không có bản ghi nào được cập nhật.

Có thể tóm tắt ba trường hợp như sau:

| Tình huống | Matched rows | Changed rows mặc định | Affected rows mặc định |
| --- | ---: | ---: | ---: |
| Khớp một dòng, gán lại cùng giá trị | 1 | 0 | 0 |
| Khớp một dòng, giá trị thay đổi | 1 | 1 | 1 |
| Không có dòng khớp | 0 | 0 | 0 |

## 3. Lấy số dòng bằng ROW_COUNT()

MySQL cung cấp hàm `ROW_COUNT()` để đọc số dòng bị ảnh hưởng bởi câu lệnh gần nhất trong cùng kết nối:

```sql
UPDATE inventory
SET quantity = quantity + 2
WHERE sku = 'MS-02';

SELECT ROW_COUNT() AS affected_rows;
```

Hãy gọi `ROW_COUNT()` ngay sau câu lệnh cần kiểm tra. Một câu lệnh khác chạy xen giữa có thể thay đổi ngữ cảnh mà hàm đọc. Ví dụ, nếu chạy một câu `SELECT` trả về result set trước rồi mới gọi `ROW_COUNT()`, giá trị nhận được là -1 vì câu lệnh gần nhất là `SELECT` trả về tập kết quả.

Một số giá trị cần nhớ:

| Câu lệnh gần nhất | Giá trị `ROW_COUNT()` |
| --- | --- |
| `INSERT`, `UPDATE`, `DELETE` | Số dòng bị ảnh hưởng theo quy tắc của câu lệnh và kết nối. |
| `CREATE TABLE`, `DROP TABLE` (DDL) | 0 |
| `SELECT ...` trả về result set | -1 |
| `SELECT ... INTO OUTFILE` | Số dòng được ghi ra file |

Không nên nhầm `ROW_COUNT()` với `FOUND_ROWS()`. `ROW_COUNT()` đọc số dòng bị ảnh hưởng bởi câu lệnh gần nhất. `FOUND_ROWS()` liên quan đến số dòng của một truy vấn `SELECT`, thường được nhắc đến cùng `SQL_CALC_FOUND_ROWS`; cơ chế `SQL_CALC_FOUND_ROWS` và `FOUND_ROWS()` đã bị deprecated trong MySQL 8.4. Với nhu cầu đếm tổng số bản ghi thỏa điều kiện, hãy cân nhắc một truy vấn `COUNT(*)` riêng.

Nếu cần giữ kết quả để dùng sau, hãy lưu ngay sau DML:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'MS-02'
  AND quantity > 0;

SET @changed_rows = ROW_COUNT();

-- Có thể dùng lại biến trong các câu lệnh tiếp theo.
SELECT @changed_rows AS changed_rows;
```

## 4. Quy tắc đếm của các câu lệnh DML

Không phải câu lệnh ghi dữ liệu nào cũng có cùng cách đếm. Bảng sau tóm tắt các trường hợp thường gặp trong MySQL:

| Câu lệnh | Cách tính affected rows |
| --- | --- |
| `INSERT` | Số dòng mới được chèn thành công. |
| `UPDATE` | Mặc định là số dòng thực sự thay đổi; có thể chuyển sang số dòng khớp điều kiện bằng `CLIENT_FOUND_ROWS`. |
| `DELETE` | Số dòng bị xóa. |
| `INSERT ... ON DUPLICATE KEY UPDATE` | Theo từng dòng: 1 nếu chèn mới, 2 nếu cập nhật dòng đã tồn tại, 0 nếu dòng đã tồn tại và được gán lại đúng các giá trị hiện tại. |
| `REPLACE` | Nếu thay thế một dòng cũ do trùng khóa, giá trị affected rows là 2 vì thao tác gồm xóa dòng cũ và chèn dòng mới. |

Với `INSERT ... ON DUPLICATE KEY UPDATE`, ví dụ một dòng có khóa duy nhất đã tồn tại:

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('KB-01', 10) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity;

SELECT ROW_COUNT() AS affected_rows;
```

Nếu `KB-01` chưa tồn tại thì thao tác chèn mới được tính là 1. Nếu đã tồn tại và `quantity` đổi, kết quả cho dòng đó là 2. Nếu đã tồn tại và `quantity` vẫn là 10, kết quả mặc định là 0. Với lệnh nhiều dòng, các giá trị này được cộng theo từng dòng được xử lý.

Lưu ý rằng `REPLACE` có ngữ nghĩa xóa dòng trùng rồi chèn dòng mới, không nên xem nó như một cách viết khác của `UPDATE`. Khi chọn câu lệnh, hãy cân nhắc cả khóa, ràng buộc và tác động dữ liệu đi kèm, thay vì chỉ nhìn vào con số affected rows.

## 5. CLIENT_FOUND_ROWS và khác biệt giữa client

Mặc định, với `UPDATE`, MySQL trả về số dòng thực sự thay đổi. Khi client kết nối bằng cờ `CLIENT_FOUND_ROWS`, affected rows được tính theo số dòng khớp điều kiện `WHERE`. Khi đó, ví dụ gán `quantity = 10` cho một dòng vốn đã có `quantity = 10` có thể được báo là 1 thay vì 0.

Cờ này cũng ảnh hưởng đến trường hợp không thay đổi trong `INSERT ... ON DUPLICATE KEY UPDATE`: giá trị 0 được báo thành 1 cho dòng đã tồn tại nhưng giữ nguyên giá trị. Đây là tùy chọn ở lớp kết nối/client, không phải một mệnh đề SQL để thêm vào câu `UPDATE`.

Do đó, cùng một câu SQL có thể cho số affected rows khác nhau nếu ứng dụng và MySQL client dùng cấu hình kết nối khác nhau. Khi kiểm tra kết quả trong ứng dụng, hãy xem tài liệu và cấu hình của connector đang dùng, đặc biệt nếu logic nghiệp vụ dựa vào việc phân biệt “đã tìm thấy” với “đã thay đổi”. Đừng mặc định mọi thư viện đều trả về cùng một ý nghĩa nếu chưa xác minh cấu hình.

## 6. Dùng affected rows để phát hiện xung đột cập nhật

Affected rows rất hữu ích khi nhiều người dùng hoặc tiến trình có thể cùng sửa một bản ghi. Một cách phổ biến là *optimistic locking* (khóa lạc quan): mỗi bản ghi có cột phiên bản `version`; ứng dụng chỉ cập nhật nếu phiên bản vẫn bằng giá trị mà nó đã đọc.

Ví dụ bảng đơn hàng có các cột `id`, `status` và `version`. Ứng dụng đã đọc đơn hàng với `id = 101`, trạng thái `PENDING` và phiên bản 4. Khi xác nhận đơn, ứng dụng chạy:

```sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = 101
  AND status = 'PENDING'
  AND version = 4;

SELECT ROW_COUNT() AS affected_rows;
```

Diễn giải kết quả:

- **1 dòng:** điều kiện vẫn đúng và bản ghi đã được cập nhật. Ứng dụng có thể tiếp tục bước tiếp theo trong transaction.
- **0 dòng:** bản ghi không tồn tại, trạng thái đã đổi, hoặc phiên bản đã tăng do một thao tác khác. Đây là dấu hiệu điều kiện cập nhật không còn đúng; ứng dụng cần đọc lại trạng thái và xử lý xung đột theo nghiệp vụ.

Việc tăng `version` khiến một cập nhật hợp lệ luôn thay đổi bản ghi. Nhờ vậy, kết quả 0 trong mẫu này biểu thị điều kiện bảo vệ không khớp, thay vì chỉ là trường hợp gán lại cùng giá trị. Cột phiên bản cũng giúp phát hiện trường hợp một người dùng đang ghi đè lên dữ liệu cũ mà họ đã đọc trước đó.

Affected rows chỉ mô tả kết quả của câu lệnh hiện tại. Nếu thao tác gồm nhiều câu lệnh, hãy đặt chúng trong transaction phù hợp và chỉ xác nhận thành công nghiệp vụ sau khi `COMMIT` thành công. Nếu transaction bị `ROLLBACK`, các thay đổi đã thực hiện trong transaction sẽ bị hoàn tác dù câu `UPDATE` trước đó từng báo có dòng bị ảnh hưởng.

## 7. Quy trình chẩn đoán khi UPDATE báo 0 dòng

Khi ứng dụng nhận affected rows bằng 0, hãy kiểm tra theo thứ tự:

1. **Xác nhận câu lệnh có thực thi thành công.** Phân biệt kết quả trả về 0 với lỗi SQL hoặc lỗi kết nối. Dựa vào mã lỗi/exception của driver để nhận diện lỗi.
2. **Kiểm tra điều kiện `WHERE`.** Xác minh khóa định danh, trạng thái, điều kiện thời gian và các tham số có đúng như dự kiến hay không.
3. **Phân biệt không khớp với không đổi.** Nếu cần chẩn đoán, truy vấn bản ghi bằng cùng điều kiện và xem giá trị hiện tại. Hãy cân nhắc transaction hoặc khóa phù hợp nếu một client khác có thể thay đổi bản ghi giữa lúc kiểm tra và cập nhật.
4. **Kiểm tra cấu hình đếm của kết nối.** Xác định client có bật `CLIENT_FOUND_ROWS` hay không và hiểu rõ API đang trả về số dòng matched hay changed.
5. **Đánh giá trạng thái transaction.** Một câu lệnh có affected rows lớn hơn 0 chưa chứng minh dữ liệu đã được commit bền vững.

Một lưu ý khác: nếu câu lệnh gán cả cột nghiệp vụ lẫn cột audit như `updated_at`, chỉ cần `updated_at` thay đổi thì dòng vẫn được tính là changed, ngay cả khi giá trị nghiệp vụ chính không đổi. Ngược lại, nếu mọi cột được gán đều giữ nguyên giá trị lưu trữ thì `UPDATE` có thể báo 0 theo mặc định.

Không nên dùng riêng affected rows để kết luận bản ghi chắc chắn tồn tại hoặc chắc chắn không tồn tại. Một kết quả 0 có thể đến từ nhiều nguyên nhân; hãy đối chiếu điều kiện, dữ liệu và cấu hình kết nối.

## 8. Checklist khi đọc kết quả DML

- [ ] Đã xác định đang cần số dòng khớp điều kiện hay số dòng thực sự thay đổi.
- [ ] Với `UPDATE`, đã tính đến trường hợp giá trị mới giống giá trị hiện tại.
- [ ] Đã đọc `ROW_COUNT()` ngay sau câu lệnh cần kiểm tra.
- [ ] Đã kiểm tra cấu hình `CLIENT_FOUND_ROWS` của connector nếu kết quả khác kỳ vọng.
- [ ] Không xem affected rows bằng 0 là lỗi SQL nếu câu lệnh đã thực thi thành công.
- [ ] Khi dùng affected rows để kiểm soát đồng thời, đã đưa điều kiện phiên bản/trạng thái vào `WHERE` và xử lý trường hợp 0 dòng.
- [ ] Đã xác nhận transaction được commit trước khi thông báo thao tác nghiệp vụ hoàn tất.

## 9. Tự kiểm tra

**Tình huống 1.** Một dòng có `quantity = 8`. Câu lệnh `UPDATE inventory SET quantity = 8 WHERE sku = 'MS-02'` khớp đúng dòng đó. Theo mặc định, MySQL báo bao nhiêu affected rows?

**Đáp án:** 0. Có một dòng matched nhưng không có dòng changed.

**Tình huống 2.** Câu lệnh cập nhật `quantity = quantity + 1` cho một mã sản phẩm tồn tại và có `quantity = 8`. Kết quả mặc định là bao nhiêu?

**Đáp án:** 1. Một dòng được cập nhật và giá trị lưu trữ thay đổi.

**Tình huống 3.** Ứng dụng cập nhật đơn hàng với điều kiện `id = 101 AND version = 4`, nhưng affected rows bằng 0. Có thể kết luận đơn hàng không tồn tại không?

**Đáp án:** Không. Đơn hàng có thể không tồn tại, hoặc đã được tiến trình khác cập nhật làm phiên bản không còn là 4, hoặc một điều kiện khác trong `WHERE` không còn đúng. Ứng dụng cần kiểm tra trạng thái hiện tại và xử lý xung đột.

**Tình huống 4.** Một câu `UPDATE` đã chạy, sau đó ứng dụng chạy một câu `SELECT` trả về tập kết quả rồi mới gọi `ROW_COUNT()`. Vì sao có thể nhận -1?

**Đáp án:** Vì `ROW_COUNT()` đọc câu lệnh gần nhất. Lúc này câu lệnh gần nhất là `SELECT` trả về result set, nên giá trị là -1. Hãy đọc hoặc lưu `ROW_COUNT()` ngay sau DML.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Information Functions: ROW_COUNT()](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html#function_row-count)
- [MySQL 8.4 Reference Manual — UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
