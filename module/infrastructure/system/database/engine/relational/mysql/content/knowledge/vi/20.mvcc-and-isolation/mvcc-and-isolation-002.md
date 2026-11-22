# Undo record, row version và read view trong InnoDB

InnoDB dùng **Multi-Version Concurrency Control (MVCC)** để nhiều transaction có thể đọc cùng một tập dữ liệu trong khi transaction khác đang cập nhật. Thay vì buộc mọi câu `SELECT` phải chờ khóa ghi, InnoDB có thể trả về phiên bản dòng phù hợp với thời điểm nhìn dữ liệu của transaction. Cơ chế này dựa trên ba thành phần liên kết với nhau: **undo record** lưu thông tin cần để khôi phục phiên bản cũ, **row version** biểu diễn các trạng thái khác nhau của một dòng, và **read view** quyết định phiên bản nào một consistent read được phép nhìn thấy.

Bài học thuộc phần **MVCC và mức cô lập** của MySQL. Bạn sẽ lần theo cách InnoDB tạo và đọc phiên bản dòng, hiểu vì sao hai lần `SELECT` có thể trả về kết quả khác nhau ở các mức cô lập khác nhau, và nhận biết tác động của transaction kéo dài lên quá trình purge.

## 1. Vì sao InnoDB cần nhiều phiên bản của một dòng?

Giả sử bảng tài khoản có một dòng:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO accounts (account_id, owner_name, balance)
VALUES (1, 'An', 1000.00);
```

Transaction A bắt đầu đọc số dư. Cùng lúc, transaction B chuyển số dư từ `1000.00` thành `800.00` rồi commit. Nếu A đang cần một snapshot ổn định, A vẫn phải nhìn thấy `1000.00` theo snapshot của mình, dù giá trị mới đã được commit. Nếu A luôn đọc trực tiếp giá trị mới nhất trong trang dữ liệu, kết quả đọc lặp lại trong cùng snapshot có thể thay đổi ngoài ý muốn.

MVCC giải quyết việc này bằng cách cho phép InnoDB dựng lại phiên bản cũ từ undo log khi phiên bản hiện tại không phù hợp với read view của câu đọc. Dữ liệu mới vẫn có thể được ghi và commit trong lúc consistent read đang đọc phiên bản cũ.

MVCC không có nghĩa là mọi thao tác đều không cần khóa. Các câu `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` vẫn sử dụng cơ chế khóa để bảo vệ thao tác đọc hiện tại hoặc ghi dữ liệu. MVCC chủ yếu giúp consistent read thông thường không phải khóa các dòng chỉ để đọc.

## 2. Undo log và undo record

Undo log là vùng thông tin InnoDB dùng để hoàn tác thay đổi và hỗ trợ dựng lại phiên bản dữ liệu trước đó. Một undo log chứa các **undo record**. Nội dung cụ thể tùy loại thao tác, nhưng với cập nhật dòng, undo record giữ thông tin cần thiết để khôi phục các giá trị cũ và lần theo lịch sử phiên bản.

Có thể phân biệt hai nhóm undo quan trọng:

- **Insert undo** được tạo khi chèn dòng và chủ yếu phục vụ rollback nếu transaction chưa commit. Sau khi transaction chèn đã commit, phiên bản chèn không cần một phiên bản cũ để consistent read khôi phục.
- **Update undo** được tạo khi cập nhật hoặc đánh dấu xóa dòng. Nó có thể cần được giữ lại sau commit vì transaction khác vẫn có read view cần nhìn phiên bản trước thay đổi.

Ví dụ:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = 800.00
WHERE account_id = 1;

-- Nếu transaction chưa commit, có thể hoàn tác:
ROLLBACK;
```

Khi `UPDATE` thực hiện, InnoDB phải có đủ thông tin để khôi phục giá trị trước đó nếu transaction rollback. Nếu transaction commit, undo record cập nhật còn có thể phục vụ consistent read của transaction khác. Vì vậy, **commit không đồng nghĩa mọi undo record lập tức bị xóa**.

Undo và redo có mục đích khác nhau:

| Thành phần | Mục đích chính | Cách sử dụng |
| --- | --- | --- |
| Undo log | Hoàn tác thay đổi chưa commit và dựng lại phiên bản cũ cho MVCC. | Rollback transaction; phục vụ consistent read và lịch sử phiên bản. |
| Redo log | Khôi phục các thay đổi trang dữ liệu đã được ghi nhận khi máy chủ gặp sự cố. | Crash recovery để đưa các trang về trạng thái nhất quán sau khởi động lại. |
| Binary log | Ghi lại sự kiện thay đổi ở mức logic hoặc row event theo cấu hình. | Replication và point-in-time recovery kết hợp với backup. |

Không nên coi undo là bản backup. Undo phục vụ hoạt động nội bộ của InnoDB và bị purge khi không còn cần thiết; nó không thay thế chiến lược sao lưu và khôi phục dữ liệu.

## 3. Row version được lưu và liên kết như thế nào?

Trong clustered index của InnoDB, mỗi record có các trường hệ thống nội bộ để quản lý phiên bản. Hai trường quan trọng với MVCC là:

- `DB_TRX_ID`: transaction ID của transaction gần nhất đã chèn hoặc thay đổi record.
- `DB_ROLL_PTR`: con trỏ đến undo record liên quan, cho phép InnoDB tìm phiên bản trước đó.

Nếu bảng không có primary key phù hợp và cũng không có unique key phù hợp để làm clustered index, InnoDB có thể tạo một row ID nội bộ (`DB_ROW_ID`). Đây là chi tiết tổ chức lưu trữ; ứng dụng nên khai báo primary key rõ ràng.

Hãy hình dung một dòng `accounts.account_id = 1` được cập nhật nhiều lần:

```text
Clustered index: phiên bản hiện tại
  balance = 700.00
  DB_TRX_ID = transaction cập nhật gần nhất
  DB_ROLL_PTR -----------------------------+
                                            |
                                            v
Undo record: phiên bản trước                |
  balance = 800.00                          |
  con trỏ đến undo record cũ ---------------+
                                            |
                                            v
Undo record: phiên bản cũ hơn
  balance = 1000.00
```

Sơ đồ chỉ mô tả ý tưởng về chuỗi phiên bản. InnoDB dùng cấu trúc undo nội bộ để dựng lại các giá trị cần thiết; không phải mỗi phiên bản là một bản sao đầy đủ của toàn bộ dòng được lưu thành một record độc lập trong clustered index.

Khi một consistent read cần phiên bản cũ, InnoDB kiểm tra transaction ID của record hiện tại. Nếu transaction tạo ra phiên bản đó không hiển thị trong read view, InnoDB đi theo `DB_ROLL_PTR`, áp dụng undo record để dựng lại phiên bản trước, rồi tiếp tục kiểm tra cho đến khi tìm được phiên bản nhìn thấy được hoặc xác định dòng không tồn tại trong snapshot.

### UPDATE và DELETE tạo phiên bản ra sao?

Với `UPDATE`, InnoDB ghi nhận thông tin cũ trong undo log, sau đó cập nhật record hiện tại và thông tin transaction/con trỏ phiên bản. Một consistent read cũ có thể dùng undo để thấy giá trị trước cập nhật.

Với `DELETE`, InnoDB thường đánh dấu record là đã xóa (delete-mark) thay vì lập tức loại bỏ vật lý record khỏi cấu trúc index. Undo giữ thông tin cần thiết để transaction có snapshot cũ vẫn có thể nhìn thấy dòng. Khi không còn read view nào cần phiên bản cũ, purge mới có thể dọn phần dữ liệu đã đánh dấu xóa và undo không còn cần thiết.

Điều này giải thích vì sao một dòng đã bị transaction khác commit xóa vẫn có thể xuất hiện trong kết quả consistent read của transaction đang giữ snapshot cũ.

## 4. Read view là gì?

**Read view** là tập thông tin InnoDB tạo để xác định transaction nào đã commit đủ sớm và phiên bản nào được phép xuất hiện trong một consistent read. Có thể hiểu nó như ảnh chụp trạng thái các transaction tại một thời điểm.

Về mặt khái niệm, read view theo dõi:

- Transaction ID của transaction tạo read view, để transaction nhìn thấy thay đổi của chính nó.
- Tập transaction ID đang hoạt động tại thời điểm tạo read view.
- Các mốc giới hạn transaction ID để phân biệt transaction đã kết thúc trước snapshot với transaction bắt đầu sau snapshot.

Khi kiểm tra một phiên bản dòng, InnoDB xét transaction đã tạo phiên bản đó:

1. Thay đổi do chính transaction hiện tại tạo ra được transaction đó nhìn thấy.
2. Phiên bản được tạo bởi transaction đã commit trước thời điểm read view được tạo có thể nhìn thấy.
3. Phiên bản do transaction còn hoạt động tại thời điểm tạo read view tạo ra chưa được nhìn thấy, kể cả khi transaction đó commit sau thời điểm snapshot.
4. Phiên bản do transaction nhận transaction ID sau mốc của read view không thuộc snapshot đó. Trường hợp này cũng có thể xảy ra khi transaction đã mở trước snapshot nhưng chỉ thực hiện thao tác ghi và được cấp transaction ID sau snapshot.

Trong các trường hợp nằm giữa hai mốc giới hạn, InnoDB dùng danh sách transaction đang hoạt động được lưu trong read view để xác định transaction tạo phiên bản đã kết thúc trước snapshot hay vẫn còn hoạt động lúc snapshot được tạo. Nếu phiên bản hiện tại không nhìn thấy được, InnoDB lần theo undo để tìm phiên bản cũ hơn.

Read view không phải bản sao dữ liệu được lưu riêng cho từng câu `SELECT`. Nó là thông tin về khả năng nhìn thấy transaction; dữ liệu cũ được dựng lại từ undo khi cần.

## 5. Khi nào InnoDB tạo read view?

Thời điểm tạo read view phụ thuộc mức cô lập và loại câu đọc. Với consistent read thông thường trên InnoDB:

| Mức cô lập | Hành vi của consistent read |
| --- | --- |
| `READ COMMITTED` | Mỗi consistent read tạo read view mới. Hai câu `SELECT` trong cùng transaction có thể thấy các commit mới xảy ra giữa hai câu. |
| `REPEATABLE READ` | Các consistent read trong cùng transaction sử dụng cùng read view, thường được tạo ở lần consistent read đầu tiên. |
| `READ UNCOMMITTED` | Không có bảo đảm snapshot nhất quán như hai mức trên; transaction có thể đọc thay đổi chưa commit của transaction khác. |
| `SERIALIZABLE` | InnoDB áp dụng hành vi khóa nghiêm ngặt hơn; cách xử lý `SELECT` phụ thuộc chế độ transaction/autocommit. Không nên xem nó như một mức consistent read thông thường. |

Với `REPEATABLE READ`, câu lệnh `START TRANSACTION` thông thường chưa nhất thiết tạo read view ngay. Read view thường được tạo khi transaction chạy consistent read đầu tiên. Nếu cần thiết lập snapshot ngay lúc bắt đầu transaction, có thể dùng `START TRANSACTION WITH CONSISTENT SNAPSHOT` trong điều kiện phù hợp, đặc biệt với InnoDB ở mức `REPEATABLE READ`.

Ví dụ kiểm tra mức cô lập hiện tại trên MySQL 8.0:

```sql
SELECT @@transaction_isolation;
```

Thiết lập mức cô lập cho session trước khi bắt đầu transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Thiết lập này áp dụng cho các transaction tiếp theo trong session. Nếu muốn thay đổi phạm vi cho một transaction cụ thể, có thể dùng cú pháp `SET TRANSACTION ISOLATION LEVEL ...` trước khi bắt đầu transaction đó.

## 6. Thí nghiệm: REPEATABLE READ giữ cùng read view

Chuẩn bị dữ liệu:

```sql
CREATE TABLE inventory (
    product_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (product_id, quantity)
VALUES (10, 50);
```

Mở hai session MySQL. Đảm bảo session A đang dùng `REPEATABLE READ`.

**Session A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Kết quả: 50. Read view được tạo ở consistent read này.
```

**Session B**

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 40
WHERE product_id = 10;

COMMIT;
```

Quay lại session A:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Vẫn thấy: 50, vì consistent read dùng read view cũ.
```

Session A chưa nhìn thấy phiên bản `40` do transaction B tạo ra sau khi read view của A được thiết lập. Undo record cho phép InnoDB dựng lại giá trị `50`.

Kết thúc transaction A rồi đọc lại:

```sql
COMMIT;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Kết quả: 40 trong transaction mới/autocommit.
```

Khi transaction A kết thúc, read view cũ không còn bị transaction đó giữ lại. Một transaction mới tạo snapshot mới và có thể nhìn thấy thay đổi đã commit của B.

## 7. Thí nghiệm: READ COMMITTED tạo read view mới cho mỗi câu đọc

Giữ nguyên dữ liệu ở trạng thái `quantity = 50` trước khi chạy thí nghiệm. Đặt session A thành `READ COMMITTED`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Kết quả ban đầu: 50.
```

Trong session B, cập nhật và commit:

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 40
WHERE product_id = 10;

COMMIT;
```

Session A đọc lại:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 10;
-- Kết quả: 40, vì câu SELECT này tạo read view mới.
```

Với `READ COMMITTED`, transaction A có thể nhìn thấy commit mới giữa hai consistent read. Điều này giảm khả năng giữ phiên bản cũ lâu, nhưng ứng dụng không thể giả định mọi lần đọc trong một transaction đều nhìn cùng một snapshot.

## 8. Consistent read và current read

Một điểm rất quan trọng khi làm việc với MVCC là phân biệt **consistent read** với **current read**.

| Loại đọc | Ví dụ | Dữ liệu được đọc |
| --- | --- | --- |
| Consistent read | `SELECT ...` thông thường ở mức cô lập hỗ trợ consistent read | Phiên bản phù hợp với read view của transaction. Thông thường không đặt khóa trên các dòng chỉ để đọc. |
| Current read có khóa | `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE` | Phiên bản hiện tại phù hợp để khóa và phối hợp với transaction ghi; có thể phải chờ transaction khác nhả khóa. |
| Thao tác ghi | `UPDATE`, `DELETE`, và phần đọc dòng phục vụ thao tác ghi | Dùng cơ chế đọc hiện tại/khoá cần thiết để xác định và thay đổi dòng. |

Ví dụ, khi session A ở `REPEATABLE READ` đã tạo read view và vẫn nhìn thấy `quantity = 50`, session B cập nhật thành `40` rồi commit. Một câu `SELECT` thông thường tiếp theo của A vẫn có thể trả về `50`, nhưng một locking read như `SELECT ... FOR UPDATE` có mục đích đọc phiên bản hiện tại và khóa dòng để cập nhật an toàn. Hai câu đọc vì vậy có thể cho kết quả khác nhau trong cùng transaction.

```sql
-- Consistent read: theo read view của transaction
SELECT quantity
FROM inventory
WHERE product_id = 10;

-- Current read: đọc phiên bản hiện tại và khóa dòng
SELECT quantity
FROM inventory
WHERE product_id = 10
FOR UPDATE;
```

`FOR SHARE` lấy khóa chia sẻ để bảo vệ dòng khỏi bị cập nhật/xóa xung đột trong thời gian transaction giữ khóa. `FOR UPDATE` lấy khóa độc quyền phù hợp cho luồng đọc rồi cập nhật. Các câu locking read có thể chờ, bị deadlock hoặc gặp lock wait timeout; MVCC không loại bỏ các tình huống đó.

Không nên dùng một câu `SELECT` thông thường để kiểm tra số dư rồi mặc định rằng giá trị vẫn còn nguyên khi câu `UPDATE` sau đó chạy. Nếu nghiệp vụ cần đọc và thay đổi một dòng như một thao tác phối hợp, hãy cân nhắc locking read, câu `UPDATE` có điều kiện, constraint và kiểm tra số dòng bị ảnh hưởng.

## 9. Purge: khi nào phiên bản cũ được dọn?

Undo record cần cho rollback hoặc cho read view đang hoạt động phải được giữ lại. Khi không còn transaction nào có thể cần một phiên bản cũ, tiến trình **purge** của InnoDB có thể dọn undo history đã hết hạn và các record đã được đánh dấu xóa mà không còn cần thiết.

Quy trình khái quát:

1. Transaction cập nhật hoặc xóa một dòng; InnoDB ghi undo record và liên kết lịch sử phiên bản.
2. Transaction commit; phiên bản mới trở thành phiên bản đã commit.
3. Một transaction khác có read view cũ vẫn có thể cần phiên bản trước đó.
4. Khi read view cũ kết thúc và không còn snapshot nào cần undo record đó, purge có thể thu hồi phần lịch sử không còn hữu ích.

Vì vậy, transaction đọc kéo dài có thể giữ read view lâu và ngăn purge loại bỏ những phiên bản cũ mà snapshot đó có thể cần. Nếu hệ thống liên tục ghi hoặc xóa dữ liệu trong khi read view cũ tồn tại, lượng undo history chờ purge có thể tăng, làm tăng áp lực lưu trữ và chi phí xử lý.

### Dấu hiệu và cách kiểm tra

Có thể xem các transaction InnoDB đang hoạt động:

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Để xem thêm trạng thái nội bộ của InnoDB, có thể chạy:

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong kết quả, phần TRANSACTIONS và thông tin history list có thể giúp nhận biết transaction tồn tại lâu và lượng undo history đang chờ purge. `History list length` là chỉ báo về backlog lịch sử undo cần xử lý; không nên diễn giải nó như số dòng bị xóa hoặc số phiên bản dòng chính xác.

Khi nghi ngờ transaction dài làm chậm purge, hãy kiểm tra thời điểm bắt đầu transaction, session sở hữu nó, câu truy vấn đang chạy và mục đích nghiệp vụ. Chỉ kết thúc transaction sau khi xác định được tác động lên ứng dụng. Tối ưu thường bắt đầu từ việc giữ transaction ngắn, tránh mở transaction rồi chờ người dùng hoặc dịch vụ bên ngoài, và bảo đảm mọi nhánh xử lý đều commit hoặc rollback.

## 10. Các lỗi hiểu nhầm thường gặp

- **Cho rằng commit xóa ngay undo record.** Update undo có thể còn cần cho snapshot đang hoạt động; purge dọn sau khi an toàn.
- **Cho rằng mọi `SELECT` trong một transaction đều dùng snapshot giống nhau.** Điều này đúng với consistent read ở `REPEATABLE READ`, nhưng ở `READ COMMITTED` mỗi câu consistent read có read view mới.
- **Cho rằng `SELECT ... FOR UPDATE` cũng đọc snapshot cũ.** Locking read là current read, có mục đích đọc phiên bản hiện tại và khóa dòng.
- **Cho rằng MVCC không dùng khóa.** MVCC hỗ trợ đọc nhất quán; thao tác ghi và locking read vẫn cần khóa.
- **Nhầm undo với redo.** Undo phục vụ rollback và phiên bản cũ; redo phục vụ crash recovery.
- **Cho rằng transaction dài chỉ giữ kết nối.** Một read view cũ còn có thể cản purge và khiến undo history tăng.
- **Cho rằng DELETE lập tức loại bỏ vật lý record.** InnoDB có thể đánh dấu xóa trước; purge xử lý loại bỏ vật lý khi không còn cần phiên bản cũ.

## 11. Bài tập tự kiểm tra

1. Một transaction ở `REPEATABLE READ` đã chạy `SELECT` lần đầu. Transaction khác cập nhật dòng và commit. Vì sao lần `SELECT` thông thường thứ hai vẫn có thể trả về giá trị cũ?
2. Nếu cùng tình huống nhưng session đọc dùng `READ COMMITTED`, kết quả của lần đọc thứ hai có thể thay đổi thế nào?
3. Undo record hỗ trợ những công việc nào? Vì sao update undo có thể phải tồn tại sau commit?
4. `DB_TRX_ID` và `DB_ROLL_PTR` có vai trò gì trong việc lần theo row version?
5. Vì sao một dòng đã bị xóa và commit vẫn có thể xuất hiện trong consistent read của transaction khác?
6. Phân biệt consistent read với `SELECT ... FOR UPDATE`.
7. Một transaction đọc mở nhiều giờ trong khi hệ thống ghi/xóa liên tục có thể gây tác động gì đến purge?
8. Vì sao `History list length` không thể được hiểu trực tiếp là số dòng đã xóa?

Khi trả lời, hãy mô tả theo chuỗi **transaction thay đổi dòng → undo record lưu trạng thái trước → read view kiểm tra transaction tạo phiên bản → InnoDB chọn phiên bản phù hợp → purge thu hồi lịch sử khi không còn snapshot cần đến**. Chuỗi này là nền tảng để giải thích hành vi đọc nhất quán của InnoDB và mối liên hệ giữa MVCC với các mức cô lập transaction.
