# Crash recovery và khôi phục trạng thái giao dịch

Khi MySQL dừng đột ngột, InnoDB phải đưa dữ liệu trên đĩa về trạng thái nhất quán trước khi cho phép ứng dụng tiếp tục ghi. Cơ chế **crash recovery** dùng redo log để áp dụng lại thay đổi cần thiết và dùng undo log để hoàn tác các transaction chưa hoàn tất. Vì vậy, sau khi khởi động lại thành công, transaction đã commit được giữ theo chính sách durability đã cấu hình, còn transaction chưa commit được rollback.

Bài học thuộc phần **Lưu trữ InnoDB** của MySQL. Bạn sẽ hiểu vai trò của redo, undo, checkpoint, doublewrite và binary log; lần theo các giai đoạn InnoDB phục hồi sau crash; kiểm tra cấu hình durability; xử lý tình huống client mất kết nối khi COMMIT; và khôi phục dữ liệu đến một thời điểm cụ thể từ backup kết hợp binary log.

## 1. Crash recovery giải quyết vấn đề gì?

Trong lúc hoạt động, InnoDB thường thay đổi page trong buffer pool trước. Những page đã thay đổi nhưng chưa ghi về data file được gọi là **dirty page**. Nếu máy chủ dừng đột ngột, data file có thể còn thiếu một phần thay đổi đã được commit hoặc chứa page chỉ mới được ghi một phần.

InnoDB dùng write-ahead logging (WAL): thông tin redo cần thiết phải được ghi vào redo log trước khi page dữ liệu tương ứng được ghi xuống data file. Khi khởi động lại sau crash, engine có thể dùng redo log để đưa page về trạng thái cần thiết, sau đó dùng undo để loại bỏ tác động của các transaction chưa commit.

Hai mục tiêu chính:

- **Consistency:** cấu trúc dữ liệu và trạng thái transaction được đưa về trạng thái nhất quán theo quy tắc của InnoDB.
- **Durability:** thay đổi đã commit được bảo toàn trong giới hạn của cấu hình flush, hệ điều hành, thiết bị lưu trữ và cơ chế backup.

Crash recovery là cơ chế tự động của InnoDB khi server khởi động lại sau một lần dừng không sạch. Nó khác với việc phục hồi một database đã mất file hoặc khôi phục về thời điểm trước đó từ backup.

## 2. Redo log, undo log và binary log

Ba loại log có vai trò khác nhau:

| Thành phần | Nội dung/mục đích | Dùng khi nào? |
| --- | --- | --- |
| Redo log | Ghi lại thông tin cần để phát lại thay đổi page của InnoDB. | Crash recovery: áp dụng lại thay đổi đã được ghi log nhưng page dữ liệu có thể chưa được flush. |
| Undo log | Lưu thông tin cần để rollback thay đổi và dựng lại phiên bản dòng cũ cho MVCC. | Rollback transaction chưa commit; consistent read cần phiên bản trước. |
| Binary log (binlog) | Ghi các sự kiện thay đổi ở mức logic hoặc row event theo cấu hình. | Replication và point-in-time recovery sau khi restore backup. |

Redo không thay thế undo. Khi crash recovery chạy, một thay đổi của transaction chưa commit vẫn có thể được redo vào page, sau đó transaction đó được rollback bằng undo. Đây là lý do không thể kết luận rằng mọi thay đổi đã được phát lại từ redo đều thuộc transaction đã commit.

Binary log cũng không thay thế redo log. Redo phục vụ phục hồi nội bộ của InnoDB; binlog phục vụ replication và khôi phục theo chuỗi sự kiện SQL/row. Khi bật binary logging, MySQL phối hợp commit giữa InnoDB và binlog bằng cơ chế two-phase commit nội bộ để hạn chế trạng thái không khớp giữa hai log.

## 3. LSN, checkpoint và write-ahead logging

Mỗi thay đổi được ghi vào redo log gắn với một vị trí logic gọi là **Log Sequence Number (LSN)**. LSN tăng dần theo luồng redo. Nó giúp InnoDB xác định redo nào đã được ghi nhận và page dữ liệu đã được checkpoint đến đâu.

**Checkpoint** là mốc cho biết các page dirty trước một vị trí redo nhất định đã được ghi xuống data file theo yêu cầu. Khi server crash, InnoDB không cần đọc lại toàn bộ redo log từ lúc database được tạo; engine bắt đầu từ checkpoint phù hợp và xử lý phần redo cần thiết sau đó.

Quy trình ghi khái quát:

```text
Transaction thay đổi record
          |
          v
Page trong buffer pool trở thành dirty
          |
          +----------------------+
          |                      |
          v                      v
       Redo log              Dirty page
          |                      |
          v                      |
Ghi/flush redo trước             |
page dữ liệu                     |
          |                      |
          +----------+-----------+
                     |
                     v
          Page được flush xuống data file
                     |
                     v
                 Checkpoint
```

WAL cho phép InnoDB xác nhận transaction commit mà không cần ghi đồng bộ mọi page dữ liệu xuống vị trí cuối cùng của chúng. Redo log cung cấp thông tin để hoàn thiện các page sau đó.

## 4. Transaction commit và cấu hình durability

Khi transaction commit, InnoDB ghi redo tương ứng vào log. Việc log được ghi và flush đến thiết bị lưu trữ nhanh hay chậm phụ thuộc cấu hình `innodb_flush_log_at_trx_commit`.

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
```

| Giá trị | Hành vi khái quát | Đánh đổi |
| --- | --- | --- |
| `1` | Ghi và flush redo log xuống thiết bị lưu trữ ở mỗi lần commit. | Mức durability cao nhất theo thiết kế thông thường, đổi lại có thể tăng chi phí I/O commit. |
| `2` | Ghi redo log vào file ở mỗi lần commit; flush từ bộ đệm hệ điều hành xuống thiết bị lưu trữ theo chu kỳ, thường khoảng một giây. | Có thể mất các commit gần nhất nếu hệ điều hành hoặc máy chủ gặp sự cố trước lần flush. |
| `0` | Ghi và flush redo log theo chu kỳ, thường khoảng một giây, thay vì ở mỗi commit. | Có thể mất các transaction gần nhất khi mysqld hoặc hệ thống dừng đột ngột. |

Chu kỳ flush thực tế chịu ảnh hưởng của `innodb_flush_log_at_timeout`, tải hệ thống và khả năng của thiết bị lưu trữ. Giá trị `1` chỉ bảo đảm theo giả định hệ điều hành và thiết bị thực hiện đúng yêu cầu flush; bộ điều khiển hoặc ổ đĩa có cache không được bảo vệ có thể làm suy yếu durability.

Nếu bật binary log, cần quan tâm thêm `sync_binlog`:

```sql
SHOW VARIABLES LIKE 'sync_binlog';
SHOW VARIABLES LIKE 'log_bin';
```

- `sync_binlog = 1` yêu cầu đồng bộ binlog xuống thiết bị lưu trữ sau mỗi nhóm commit theo cơ chế của MySQL.
- Giá trị `0` để hệ điều hành quyết định thời điểm flush; giá trị `N` lớn hơn 1 đồng bộ sau mỗi N nhóm sự kiện.

Với hệ thống yêu cầu độ bền cao và có binary logging, cấu hình thường được cân nhắc là `innodb_flush_log_at_trx_commit = 1` cùng `sync_binlog = 1`. Cần đo tải I/O và xác minh phần cứng lưu trữ thực sự tôn trọng lệnh flush trước khi coi cấu hình là bảo đảm tuyệt đối.

### Phối hợp InnoDB và binary log

Khi binary logging được bật, commit của transaction InnoDB được phối hợp với binlog theo cơ chế two-phase commit nội bộ. Ở mức khái niệm:

1. InnoDB đưa transaction vào trạng thái **prepare** và ghi thông tin cần thiết vào redo log.
2. MySQL ghi các sự kiện transaction vào binary log và đồng bộ theo cấu hình `sync_binlog`.
3. InnoDB hoàn tất commit sau khi giai đoạn binlog đã thành công.
4. Nếu server crash giữa các giai đoạn, recovery đối chiếu trạng thái prepared của InnoDB với binlog để quyết định transaction cần được hoàn tất hay rollback.

Đây là phối hợp nội bộ giữa storage engine và server. Ứng dụng không tự thực hiện hai pha này bằng hai câu SQL riêng.

## 5. Doublewrite và bảo vệ page khỏi ghi dở

Redo log bảo vệ khả năng phát lại thay đổi, nhưng một page có thể bị ghi dở nếu mất điện hoặc hệ thống gặp sự cố trong lúc ghi page. Hiện tượng page chỉ được ghi một phần thường gọi là **torn page**.

InnoDB có cơ chế **doublewrite buffer**: trước khi ghi page ở vị trí cuối cùng trong data file, engine ghi một bản page vào vùng doublewrite, rồi mới ghi page vào vị trí đích. Nếu crash khiến page đích bị hỏng một phần, InnoDB có thể dùng bản page hợp lệ trong doublewrite để khôi phục rồi áp dụng redo cần thiết.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite';
```

Doublewrite hỗ trợ bảo vệ page trước ghi dở; nó không thay thế redo log, backup hoặc bản sao lưu ở máy chủ khác. Vị trí và cách triển khai doublewrite có thể khác theo phiên bản và cấu hình, vì vậy không nên tự sửa hoặc xóa các file nội bộ liên quan.

## 6. Các giai đoạn crash recovery khi MySQL khởi động

Khi mysqld phát hiện InnoDB không được shutdown sạch, engine thực hiện recovery trước khi cho phép workload bình thường tiếp tục. Có thể tóm tắt quy trình như sau:

1. **Đọc trạng thái khởi động và checkpoint.** InnoDB xác định checkpoint LSN và vùng redo cần xử lý.
2. **Kiểm tra/khôi phục page cần thiết.** Cơ chế doublewrite có thể được dùng để xử lý page bị ghi dở.
3. **Redo.** Engine phát lại thay đổi từ redo log để đưa các page lên trạng thái tương ứng với log.
4. **Rollback transaction chưa hoàn tất.** Những transaction chưa commit được hoàn tác bằng undo log. Transaction đã commit được giữ lại theo trạng thái phục hồi và chính sách durability.
5. **Tiếp tục xử lý nền.** Purge và các công việc dọn dẹp có thể tiếp tục sau khi server đã khởi động; một số công việc còn lại có thể được xử lý bất đồng bộ.

Thứ tự chi tiết của các công việc nội bộ phụ thuộc phiên bản. Điều quan trọng là redo và undo giải quyết hai việc khác nhau: redo đưa page lên trạng thái có thể phục hồi, undo loại bỏ tác động của transaction chưa commit.

### Trạng thái transaction sau crash

| Trạng thái trước crash | Kết quả sau recovery |
| --- | --- |
| Transaction đã commit và log cần thiết được lưu bền vững | Thay đổi được giữ lại. |
| Transaction chưa commit | Thay đổi được rollback bằng undo. |
| Transaction đang ở pha prepared khi bật binlog | MySQL đối chiếu trạng thái InnoDB với binlog để hoàn tất commit hoặc rollback đúng quyết định. |
| Client mất kết nối đúng lúc gửi COMMIT | Client có thể không biết commit đã thành công hay chưa; cần xác minh trạng thái nghiệp vụ trước khi gửi lại. |

Crash recovery không thể biến một commit chưa được flush bền vững thành commit chắc chắn. Nếu cấu hình cho phép mất redo hoặc binlog gần nhất khi mất điện, các transaction đó có thể không xuất hiện sau khi phục hồi.

## 7. Thí nghiệm: transaction chưa commit bị rollback sau crash

Có thể quan sát nguyên tắc này trong môi trường lab riêng. Không thử cố ý kill mysqld hoặc tắt máy trên production.

Tạo bảng và dữ liệu ban đầu:

```sql
CREATE TABLE crash_recovery_lab (
    item_id INT PRIMARY KEY,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO crash_recovery_lab (item_id, quantity)
VALUES (1, 10);
```

Trong session A:

```sql
START TRANSACTION;

UPDATE crash_recovery_lab
SET quantity = 99
WHERE item_id = 1;

-- Không COMMIT.
```

Ở thời điểm này, thay đổi `99` chưa được commit. Nếu mysqld bị dừng đột ngột trong lab và khởi động lại, InnoDB dùng redo để phục hồi các page cần thiết rồi rollback transaction chưa commit bằng undo.

Sau khi MySQL khởi động lại, kiểm tra:

```sql
SELECT quantity
FROM crash_recovery_lab
WHERE item_id = 1;
-- Giá trị kỳ vọng: 10
```

Giá trị trở lại `10` vì transaction cập nhật `99` chưa commit. Nếu transaction đã commit và redo cần thiết được lưu bền vững, kết quả kỳ vọng là `99`.

Để kiểm chứng nhánh commit, khởi tạo lại giá trị `10`, chạy `UPDATE`, sau đó `COMMIT` trước khi dừng MySQL trong một thử nghiệm riêng. Không thể dùng một câu `ROLLBACK` sau khi server đã khởi động lại để hoàn tác transaction trước crash; transaction chưa commit đã được recovery xử lý.

## 8. Đọc log và xác nhận recovery

Error log của MySQL là nguồn đầu tiên để xác định server có chạy crash recovery hay không, thời gian recovery và lỗi phát sinh. Vị trí error log tùy cấu hình:

```sql
SHOW VARIABLES LIKE 'log_error';
```

Trong error log, tìm các thông báo liên quan đến InnoDB, checkpoint LSN, redo, rollback transaction, doublewrite hoặc page corruption. Nội dung và câu chữ cụ thể khác nhau giữa các phiên bản.

Sau khi server lên, kiểm tra trạng thái cơ bản:

```sql
SELECT VERSION();
SHOW ENGINE INNODB STATUS\G
```

Trong phần LOG của `SHOW ENGINE INNODB STATUS`, các thông tin LSN, checkpoint và hoạt động flush giúp đánh giá trạng thái log. Phần TRANSACTIONS giúp nhận biết transaction còn mở. Đây là ảnh chụp tại thời điểm chạy lệnh, không phải báo cáo đầy đủ lịch sử recovery.

Kiểm tra cấu hình durability đang có hiệu lực:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'innodb_flush_log_at_trx_commit',
    'innodb_flush_log_at_timeout',
    'sync_binlog',
    'innodb_doublewrite',
    'log_bin'
);
```

Sau recovery, đối chiếu dữ liệu với các bất biến nghiệp vụ: tổng tiền, số dư, số lượng tồn kho, trạng thái đơn hàng và các quan hệ khóa ngoại. Không chỉ dựa vào việc MySQL báo `ready for connections` để kết luận mọi dữ liệu nghiệp vụ đều đúng.

## 9. Client mất kết nối trong lúc COMMIT: kết quả có thể chưa rõ

Một tình huống thực tế là ứng dụng gửi `COMMIT`, nhưng kết nối mạng đứt trước khi nhận được phản hồi. Có hai khả năng: server đã commit nhưng phản hồi bị mất, hoặc server chưa hoàn tất commit. Từ phía client, lỗi kết nối không đủ để phân biệt hai trường hợp.

Không nên tự động gửi lại một thao tác không idempotent như trừ tiền hoặc tạo đơn hàng. Hãy thiết kế thao tác có khóa idempotency hoặc mã nghiệp vụ duy nhất:

```sql
CREATE TABLE payment_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;
```

Ứng dụng ghi `request_id` duy nhất cùng thay đổi số dư trong một transaction. Nếu phản hồi COMMIT bị mất, ứng dụng kết nối lại và tra cứu `request_id` để xác định yêu cầu đã được ghi nhận chưa. Unique key ngăn cùng một request được xử lý hai lần nếu ứng dụng retry.

Mẫu quy trình:

1. Tạo mã request ổn định ở phía ứng dụng trước khi gửi thao tác.
2. Trong cùng transaction, kiểm tra/ghi nhận mã request và thực hiện thay đổi nghiệp vụ.
3. Commit.
4. Nếu mất kết nối, tra cứu lại mã request bằng kết nối mới; chỉ retry theo quy tắc idempotency đã thiết kế.

Không dùng việc “không nhận được phản hồi” làm bằng chứng rằng transaction đã rollback.

## 10. Khôi phục dữ liệu bằng backup và binary log

Crash recovery xử lý trạng thái nội bộ sau khi server dừng bất thường. Nếu data file bị mất, hỏng vật lý hoặc cần quay lại thời điểm trước một thao tác sai, cần quy trình backup/restore. Một phương án point-in-time recovery (PITR) thường gồm:

1. Khôi phục một full backup nhất quán từ thời điểm đã biết.
2. Xác định vị trí hoặc thời điểm bắt đầu replay binary log tương ứng với backup.
3. Dùng `mysqlbinlog` phát lại sự kiện sau backup đến ngay trước thời điểm cần dừng.
4. Kiểm tra dữ liệu và bất biến nghiệp vụ trước khi mở lại ứng dụng.

Ví dụ khung lệnh replay theo vị trí:

```bash
mysqlbinlog \
  --start-position=12345 \
  --stop-position=67890 \
  /backup/binlog.000123 \
  | mysql -u recovery_user -p
```

Ví dụ theo thời gian:

```bash
mysqlbinlog \
  --start-datetime="2026-11-18 09:00:00" \
  --stop-datetime="2026-11-18 10:15:00" \
  /backup/binlog.000123 \
  | mysql -u recovery_user -p
```

Đây là ví dụ cấu trúc lệnh; cần thay file, vị trí, thời gian và thông tin kết nối bằng dữ liệu thật của backup. Vị trí chính xác phải lấy từ metadata backup hoặc công cụ backup đã dùng. Replay sai điểm bắt đầu có thể chạy lặp transaction đã có trong backup; dừng sai vị trí có thể bỏ sót hoặc áp dụng nhầm sự kiện. Khi cần độ chính xác cao, ưu tiên position/GTID và quy trình được công cụ backup ghi nhận thay vì ước lượng bằng thời gian.

Nếu bật GTID, giữ lại thông tin GTID của backup và binlog để xác định tập transaction đã áp dụng. Không trộn binlog từ các nguồn hoặc server khác nhau nếu chưa hiểu topology và GTID set.

### Crash recovery và PITR khác nhau

| Tình huống | Cơ chế chính |
| --- | --- |
| mysqld crash nhưng data file còn nguyên | InnoDB tự chạy crash recovery bằng redo và undo. |
| Một transaction chưa commit khi crash | InnoDB rollback transaction đó bằng undo. |
| Một transaction đã commit nhưng client mất phản hồi | Kết nối lại và xác minh trạng thái nghiệp vụ/idempotency key. |
| Data file bị mất hoặc hỏng không thể phục hồi | Restore backup; nếu cần, replay binlog để tiến đến thời điểm mong muốn. |
| Người dùng chạy nhầm câu lệnh đã commit | Restore backup sang môi trường khôi phục và dùng binlog/PITR để lấy dữ liệu đến thời điểm trước lỗi, sau đó đối chiếu và đưa dữ liệu trở lại theo kế hoạch. |

## 11. Khi khởi động không thành công và innodb_force_recovery

Nếu InnoDB không thể khởi động do hỏng page, redo/undo hoặc vấn đề lưu trữ, trước tiên hãy bảo toàn data directory và bản sao backup. Kiểm tra error log, tình trạng filesystem, dung lượng đĩa, quyền truy cập file và các thay đổi cấu hình gần nhất.

`innodb_force_recovery` là chế độ khẩn cấp để cố khởi động InnoDB trong một số tình huống hỏng dữ liệu nhằm trích xuất dữ liệu. Giá trị `0` là chế độ hoạt động bình thường; các giá trị lớn hơn bỏ qua ngày càng nhiều bước phục hồi hoặc xử lý nền. Các mức cao có thể làm mất dữ liệu hoặc gây hỏng file vĩnh viễn.

```sql
SHOW VARIABLES LIKE 'innodb_force_recovery';
```

Chỉ cân nhắc cấu hình biến này khi đã sao chép nguyên trạng data directory, đã đọc error log và có kế hoạch trích xuất dữ liệu. Không dùng `innodb_force_recovery` như cách khắc phục thường xuyên cho một lần restart chậm; không tăng giá trị tùy tiện và không ghi dữ liệu nghiệp vụ mới vào instance đang chạy ở chế độ cưỡng bức. Mục tiêu thường là khởi động đủ để dump dữ liệu sang một instance sạch rồi restore theo quy trình an toàn.

Nếu có backup tốt, restore vào instance mới thường là phương án rõ ràng và dễ kiểm chứng hơn việc tiếp tục sử dụng data directory bị hỏng.

## 12. Checklist vận hành sau crash

Khi MySQL dừng đột ngột, có thể làm theo thứ tự:

1. Xác định phạm vi sự cố: mysqld crash, hệ điều hành restart, mất điện, filesystem đầy hay thiết bị lưu trữ lỗi.
2. Bảo toàn error log và thông tin thời điểm; không xóa redo, undo hoặc file data để “thử khởi động lại”.
3. Kiểm tra dung lượng filesystem, quyền file, cấu hình data directory và các thay đổi gần đây.
4. Cho InnoDB chạy recovery bình thường; theo dõi error log cho đến khi server sẵn sàng.
5. Kiểm tra `SHOW ENGINE INNODB STATUS`, cấu hình durability và transaction còn hoạt động.
6. Xác minh dữ liệu nghiệp vụ, replication/binlog và các ứng dụng phụ thuộc.
7. Nếu không thể recovery, đánh giá backup và PITR; giữ nguyên bản dữ liệu hỏng để phân tích.
8. Sau khi dịch vụ ổn định, xác định nguyên nhân gốc và điều chỉnh backup, giám sát, flush policy hoặc phần cứng nếu cần.

Không xóa thủ công redo log, undo tablespace hoặc `ibdata1` để ép MySQL khởi động. Những file này là một phần trạng thái bền vững của InnoDB; thao tác sai có thể khiến dữ liệu không thể phục hồi.

## 13. Bài tập tự kiểm tra

1. Vì sao InnoDB cần redo log nếu page đã được sửa trong buffer pool?
2. Tại sao crash recovery có thể redo thay đổi của một transaction chưa commit rồi sau đó vẫn rollback transaction đó?
3. Phân biệt nhiệm vụ của redo log, undo log và binary log.
4. Checkpoint LSN giúp giảm công việc recovery như thế nào?
5. `innodb_flush_log_at_trx_commit` bằng `1`, `2` và `0` tạo ra khác biệt gì về durability?
6. `sync_binlog` phối hợp với InnoDB như thế nào khi binary logging được bật?
7. Doublewrite buffer bảo vệ khỏi loại lỗi nào? Vì sao nó không thay thế backup?
8. Vì sao client mất kết nối trong lúc COMMIT không thể kết luận transaction đã rollback?
9. Nêu các bước khôi phục đến một thời điểm bằng full backup và binary log.
10. Khi nào `innodb_force_recovery` có thể được cân nhắc và vì sao phải thận trọng?

Hãy phân biệt rõ **crash recovery** với **backup restore/PITR**. Crash recovery dùng redo và undo để hoàn tất việc phục hồi nội bộ sau sự cố; backup và binary log giúp khôi phục khi dữ liệu đã mất, hỏng hoặc cần quay về một thời điểm nghiệp vụ trước đó.
