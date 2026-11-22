# Consistent snapshot với single-transaction và giới hạn khi có DDL/nontransactional table

Khi sao lưu một cơ sở dữ liệu đang phục vụ ứng dụng, dữ liệu có thể tiếp tục được thêm, sửa hoặc xóa trong lúc công cụ đọc bảng. Nếu mỗi bảng được đọc tại một thời điểm khác nhau, bản dump có thể chứa các phần dữ liệu không cùng thuộc về một trạng thái nhất quán. MySQL giải quyết tình huống này cho bảng InnoDB bằng cơ chế consistent read của MVCC. Với `mysqldump`, tùy chọn `--single-transaction` sử dụng một transaction và một snapshot nhất quán để đọc dữ liệu mà không khóa các thao tác ghi thông thường trong toàn bộ thời gian dump.

Cơ chế này có giới hạn quan trọng: snapshot MVCC áp dụng cho dữ liệu transactional của InnoDB. Nó không làm cho MyISAM hoặc các bảng nontransactional trở thành transactional, và không bảo vệ bản dump trước các thay đổi cấu trúc bảng (DDL) diễn ra đồng thời. Muốn chọn đúng chiến lược sao lưu, cần kiểm tra storage engine, hiểu thời điểm snapshot được tạo và phối hợp lịch backup với hoạt động thay đổi schema.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích consistent snapshot dựa trên MVCC và cách `mysqldump --single-transaction` sử dụng snapshot đó.
- Dự đoán dữ liệu nào được nhìn thấy khi ứng dụng vẫn ghi trong lúc dump.
- Nhận diện giới hạn của `--single-transaction` với DDL và bảng nontransactional.
- Chọn giữa snapshot transaction, khóa đọc và khoảng thời gian dừng ghi dựa trên engine và yêu cầu nhất quán.
- Kiểm tra engine, tạo bản dump phù hợp và xác minh bằng quy trình restore thử.

## 1. Vì sao bản sao lưu cần một điểm nhất quán?

Giả sử một giao dịch bán hàng cập nhật hai bảng: `orders` và `payments`. Ứng dụng ghi trạng thái đơn hàng trước, sau đó ghi nhận thanh toán trong cùng một transaction. Nếu công cụ sao lưu đọc `orders` trước khi transaction commit và đọc `payments` sau khi transaction commit, kết quả có thể phản ánh hai thời điểm khác nhau. Khi khôi phục, dữ liệu có thể không thể hiện một trạng thái mà ứng dụng từng nhìn thấy.

Một bản sao lưu logic nhất quán cần đọc các bảng transactional tại cùng một điểm nhìn. InnoDB cung cấp điều này bằng **Multi-Version Concurrency Control (MVCC)**: thay vì buộc mọi reader chờ writer hoặc ngược lại, InnoDB giữ các phiên bản bản ghi cần thiết để transaction đọc có thể nhìn thấy một ảnh chụp dữ liệu ổn định.

Với một consistent snapshot được tạo tại thời điểm T0:

- Những thay đổi đã commit trước T0 được nhìn thấy.
- Những thay đổi chưa commit tại T0 không được nhìn thấy.
- Những thay đổi được commit sau T0 không xuất hiện trong các consistent read của transaction đó.
- Các lần đọc tiếp theo trong cùng transaction tiếp tục sử dụng cùng snapshot, thay vì chuyển sang trạng thái mới nhất của từng câu lệnh.

Điều này giúp bản dump không bị trộn dữ liệu đã commit ở các thời điểm khác nhau trong quá trình đọc, miễn là các bảng liên quan đều dùng InnoDB và không có DDL phá vỡ giả định của snapshot.

## 2. Consistent snapshot của InnoDB

### 2.1. MVCC và consistent read

InnoDB lưu thông tin phiên bản bản ghi và thông tin undo cần thiết để tái dựng phiên bản phù hợp với read view của transaction. Khi một transaction thực hiện consistent read, InnoDB xác định transaction nào đã commit tại thời điểm tạo read view. Nếu một bản ghi đã bị transaction khác cập nhật sau thời điểm đó, reader có thể đọc phiên bản cũ từ undo information.

Ví dụ, bảng `accounts` có số dư của hai tài khoản. Transaction chuyển tiền cập nhật cả hai dòng rồi commit. Một transaction đọc có snapshot được tạo trước khi commit sẽ tiếp tục thấy số dư cũ của cả hai dòng. Snapshot được tạo sau khi commit sẽ thấy số dư mới của cả hai dòng. Nhờ vậy, reader không nhìn thấy trạng thái nửa chừng của transaction chuyển tiền.

Một transaction có thể tạo snapshot tường minh như sau:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT * FROM accounts WHERE account_id IN (101, 202);
-- Các consistent SELECT tiếp theo vẫn dùng cùng read view.

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` tạo read view ngay khi transaction bắt đầu trong điều kiện isolation level phù hợp. Với InnoDB, `REPEATABLE READ` là isolation level mặc định và là mức mà `mysqldump --single-transaction` sử dụng cho snapshot. Các câu `SELECT` thông thường trong ví dụ là consistent read; những loại đọc có khóa như `SELECT ... FOR UPDATE` có ngữ nghĩa khác và không nên dùng để giải thích snapshot đọc.

### 2.2. Dữ liệu thay đổi trong khi dump

Giả sử bản dump tạo snapshot tại 10:00. Ứng dụng vẫn tiếp tục ghi dữ liệu:

| Thời điểm | Hoạt động của ứng dụng | Dữ liệu mà snapshot 10:00 nhìn thấy |
|---|---|---|
| 09:58 | Transaction A cập nhật đơn hàng và commit | Thấy dữ liệu đã cập nhật |
| 10:00 | `mysqldump` bắt đầu transaction và tạo snapshot | Điểm nhìn được cố định tại đây |
| 10:02 | Transaction B thêm đơn hàng mới và commit | Không thấy đơn hàng mới trong snapshot |
| 10:04 | Transaction C cập nhật trạng thái đơn hàng và commit | Vẫn thấy phiên bản trước 10:00 |
| 10:06 | `mysqldump` kết thúc và commit transaction đọc | Snapshot được giải phóng |

Ứng dụng vẫn có thể thực hiện DML trên InnoDB trong thời gian dump. Bản dump phản ánh trạng thái đã commit tại thời điểm snapshot được tạo, không phải trạng thái mới nhất ở thời điểm lệnh dump kết thúc. Đây là hành vi mong muốn của một bản sao lưu nhất quán tại một thời điểm.

## 3. Dùng `mysqldump --single-transaction`

`--single-transaction` yêu cầu `mysqldump` bắt đầu một transaction trước khi đọc dữ liệu và sử dụng consistent snapshot. Tùy chọn này phù hợp nhất khi toàn bộ bảng cần sao lưu là InnoDB.

Ví dụ sao lưu database `shop`:

```bash
mysqldump \
  --login-path=backup \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --databases shop > shop.sql
```

Ý nghĩa các tùy chọn chính:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--login-path=backup` | Dùng thông tin kết nối đã lưu bằng `mysql_config_editor`, tránh ghi mật khẩu trực tiếp trong dòng lệnh |
| `--single-transaction` | Dùng một consistent snapshot cho dữ liệu transactional |
| `--quick` | Đọc và ghi từng dòng theo luồng, tránh giữ toàn bộ kết quả của bảng lớn trong bộ nhớ client |
| `--routines` | Bao gồm stored procedure và stored function |
| `--events` | Bao gồm Event Scheduler events |
| `--triggers` | Bao gồm trigger; đây cũng là hành vi mặc định thông thường của `mysqldump`, ghi rõ để dễ rà soát lệnh |
| `--databases shop` | Dump database `shop` và thêm các câu lệnh tạo/chọn database trong đầu ra |

`--login-path=backup` giả định đã tạo login path phù hợp bằng `mysql_config_editor set --login-path=backup ...`. Không đưa mật khẩu thật vào file script, lịch chạy hoặc lịch sử shell. Tùy chọn `--quick` thường đã nằm trong nhóm tùy chọn mặc định `--opt`, nhưng ghi rõ giúp người đọc nhận biết ý định streaming khi xem cấu hình backup.

Nếu cần dump một database mà không thêm câu lệnh `CREATE DATABASE`/`USE`, có thể dùng `--databases` theo chủ đích hoặc truyền tên database trực tiếp và chọn cách restore tương ứng. Hãy thống nhất định dạng dump với quy trình khôi phục.

### 3.1. Điều kiện để snapshot có ý nghĩa

- Các bảng dữ liệu cần nhất quán phải dùng InnoDB.
- Snapshot phải được giữ trong cùng transaction trong suốt quá trình đọc dữ liệu.
- Không có DDL tác động đến bảng đang dump trong thời gian snapshot hoạt động.
- Tài khoản backup có đủ quyền đọc dữ liệu và metadata cần thiết cho các đối tượng được dump.
- Máy chủ còn đủ tài nguyên để giữ các phiên bản cũ cần thiết trong khi transaction đọc kéo dài.

`--single-transaction` không có nghĩa là toàn bộ quá trình backup hoàn toàn không tạo tác động. Transaction đọc dài có thể làm tăng lượng undo history phải giữ lại, ảnh hưởng hoạt động purge và làm tăng dung lượng undo tablespace. Bảng càng lớn, tốc độ đọc càng chậm hoặc thời gian dump càng dài thì tác động này càng cần được theo dõi.

## 4. Giới hạn với DDL trong thời gian dump

Consistent snapshot của InnoDB bảo vệ cách đọc phiên bản dữ liệu theo MVCC. Nó không tạo một snapshot lịch sử cho định nghĩa bảng và metadata của toàn bộ schema. Các thay đổi cấu trúc trong khi dump có thể làm quá trình đọc thất bại hoặc khiến đầu ra không còn phản ánh một cấu trúc nhất quán.

Trong lúc `mysqldump --single-transaction` đang chạy, không thực hiện các thao tác DDL trên những bảng được dump, bao gồm:

- `ALTER TABLE`: thay đổi cột, index hoặc cấu trúc bảng.
- `DROP TABLE`: xóa bảng đang được đọc.
- `RENAME TABLE`: đổi tên bảng.
- `TRUNCATE TABLE`: làm rỗng bảng bằng thao tác DDL.
- `CREATE TABLE`: tạo thêm bảng trong schema đang được dump, có thể làm thay đổi tập đối tượng mà quá trình dump xử lý.

DDL thường có implicit commit và cần metadata lock. Nó có thể thay đổi data dictionary hoặc cấu trúc mà câu lệnh dump dựa vào. Vì vậy, read view MVCC không đủ để đảm bảo dump tiếp tục an toàn khi schema thay đổi đồng thời. Tác động cụ thể tùy thao tác và thời điểm; không nên dựa vào việc một lần dump trước đây tình cờ thành công để cho phép DDL chạy song song.

### 4.1. Cách phối hợp với migration

Một quy trình dễ kiểm soát là:

1. Lập lịch backup và migration schema vào các khoảng thời gian có thể phối hợp.
2. Trước khi dump, xác nhận không có migration hoặc thao tác DDL đang chạy trên các bảng trong phạm vi backup.
3. Trong suốt thời gian dump, tạm hoãn deploy có thay đổi cấu trúc bảng, `TRUNCATE`, `RENAME` hoặc xóa bảng.
4. Sau khi dump kết thúc, mới tiếp tục migration đã hoãn.
5. Ghi lại thời điểm bắt đầu/kết thúc backup, phiên bản schema và trạng thái job để phục vụ điều tra khi cần restore.

Nếu hệ thống triển khai DDL liên tục và không thể tạo khoảng dừng, hãy chọn giải pháp backup được thiết kế để phối hợp với DDL và topology cụ thể của hệ thống. Không giả định rằng `--single-transaction` tự giải quyết được thay đổi schema.

## 5. Giới hạn với bảng nontransactional

MyISAM là ví dụ phổ biến của storage engine nontransactional. Engine này không cung cấp MVCC consistent read và không thể rollback DML như InnoDB. Nếu một bảng MyISAM bị cập nhật trong lúc `mysqldump` đọc bảng, các dòng trong bản dump có thể phản ánh nhiều thời điểm khác nhau.

Điều này cũng áp dụng cho database có cả InnoDB và nontransactional table. `--single-transaction` vẫn có thể tạo snapshot nhất quán cho các bảng InnoDB, nhưng không thể bảo đảm rằng những bảng MyISAM hoặc engine nontransactional khác thuộc cùng một điểm thời gian. Bản dump hỗn hợp engine vì thế không thể được xem là một snapshot toàn database nhất quán chỉ dựa trên tùy chọn này.

Kiểm tra engine của các bảng trước khi chọn chiến lược backup:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM information_schema.tables
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN (
      'mysql', 'information_schema', 'performance_schema', 'sys'
  )
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

Tập trung tìm các bảng có `ENGINE` khác `InnoDB`, hoặc giá trị `NULL` nếu metadata cho thấy engine không được xác định. Có thể tóm tắt số bảng theo engine:

```sql
SELECT
    ENGINE,
    COUNT(*) AS table_count
FROM information_schema.tables
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA = 'shop'
GROUP BY ENGINE
ORDER BY ENGINE;
```

### 5.1. Các lựa chọn khi có bảng nontransactional

**Lựa chọn A: dừng ghi trong khoảng backup.** Tạm dừng các ứng dụng hoặc job có thể thay đổi bảng nontransactional, chờ các thao tác đang chạy kết thúc, sau đó dump. Đây là cách dễ hiểu nhưng cần phối hợp vận hành và có thể làm gián đoạn chức năng ghi.

**Lựa chọn B: dùng global read lock.** `mysqldump --lock-all-tables` lấy global read lock trong thời gian dump, ngăn các thao tác ghi làm thay đổi dữ liệu trên máy chủ trong thời gian khóa. Cách này có thể bảo vệ tính nhất quán giữa các bảng nontransactional và nhiều database, nhưng có thể chặn ghi trên toàn instance và ảnh hưởng trực tiếp đến ứng dụng.

Ví dụ:

```bash
mysqldump \
  --login-path=backup \
  --lock-all-tables \
  --quick \
  --routines \
  --events \
  --triggers \
  --databases shop > shop-locked.sql
```

`--lock-all-tables` và `--single-transaction` là hai chiến lược khác nhau; hãy chọn chiến lược phù hợp, không ghép chúng với kỳ vọng có thêm một lớp snapshot. Global read lock có thời gian giữ khóa gần bằng thời gian dump, do đó cần đo thử thời gian và đánh giá tác động trước khi áp dụng trên production.

**Lựa chọn C: dùng `--lock-tables` khi phạm vi phù hợp.** Tùy chọn này khóa các bảng của từng database trước khi dump database đó. Nó có thể phù hợp với một số trường hợp dump một database, nhưng không tạo một điểm nhất quán chung giữa nhiều database vì các database được xử lý lần lượt. `--lock-tables` cũng không tương thích với `--single-transaction`, do thao tác khóa bảng có thể gây implicit commit.

**Lựa chọn D: chuyển bảng sang InnoDB.** Nếu workload và yêu cầu ứng dụng cho phép, chuyển đổi engine có thể giúp bảng tham gia vào cơ chế transaction và consistent snapshot. Việc chuyển đổi phải được đánh giá riêng về khóa, dung lượng, index, kiểu dữ liệu, hành vi ứng dụng và thời gian migration; không nên đổi engine chỉ bằng một lệnh vội vàng trong giờ backup.

## 6. Chọn chiến lược theo tình trạng hệ thống

| Tình trạng dữ liệu | Chiến lược thường phù hợp | Điều cần kiểm soát |
|---|---|---|
| Tất cả bảng là InnoDB, không có DDL đồng thời | `--single-transaction --quick` | Thời lượng transaction, undo history và dung lượng lưu trữ |
| Có MyISAM/nontransactional table, có thể dừng ghi | Dừng ghi có kiểm soát trong lúc dump | Thời điểm dừng/mở ghi và xác nhận không còn writer |
| Có nhiều bảng nontransactional, cần nhất quán toàn instance | `--lock-all-tables` nếu chấp nhận được tác động khóa | Global read lock và thời gian chặn ghi |
| Chỉ dump một database và có thể chấp nhận khóa theo database | Cân nhắc `--lock-tables` | Khóa từng database; không bảo đảm điểm chung giữa nhiều database |
| Schema thay đổi trong lúc backup | Điều phối migration hoặc dùng giải pháp backup hỗ trợ DDL theo thiết kế | Không chạy DDL trên bảng đang dump với `--single-transaction` |

Không có một tùy chọn dump phù hợp với mọi topology. Trước tiên hãy phân loại engine, xác định phạm vi database cần sao lưu, đo thời gian dump và thống nhất mức độ gián đoạn ghi có thể chấp nhận.

## 7. Quy trình backup có kiểm soát

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Khảo sát engine:** truy vấn `information_schema.tables` để tìm bảng nontransactional trong phạm vi backup.
2. **Kiểm tra thay đổi schema:** xác nhận không có migration, DDL hoặc tác vụ bảo trì cấu trúc bảng trong cửa sổ backup.
3. **Chọn chế độ:** dùng `--single-transaction` nếu tất cả bảng cần snapshot là InnoDB; chọn dừng ghi hoặc khóa đọc nếu có bảng nontransactional.
4. **Chạy dump:** lưu log, thời gian bắt đầu/kết thúc, mã thoát và đường dẫn file. Theo dõi dung lượng file và tài nguyên máy chủ.
5. **Kiểm tra đầu ra:** xác nhận file được tạo, không rỗng, job trả mã thành công và có thể đọc phần đầu/cuối của file dump.
6. **Thử khôi phục:** import vào môi trường kiểm thử tương thích, xác nhận bảng, routine, event, trigger và dữ liệu quan trọng.
7. **Lưu trữ an toàn:** áp dụng mã hóa, quyền truy cập tối thiểu, chính sách lưu giữ và bản sao ở vị trí độc lập theo yêu cầu vận hành.

Một lệnh dump trả mã thành công là điều kiện cần, chưa chứng minh bản sao lưu có thể khôi phục đúng. Restore thử định kỳ mới xác nhận được tính hữu dụng của bản backup.

## 8. Các tình huống dễ hiểu nhầm

- **Cho rằng `--single-transaction` khóa toàn bộ bảng:** với InnoDB, nó dùng consistent snapshot để cho phép DML tiếp tục. Nó không khóa mọi thao tác ghi trong toàn bộ thời gian dump.
- **Cho rằng mọi storage engine đều có snapshot:** MVCC consistent read là cơ chế của engine transactional như InnoDB. Bảng MyISAM không được bảo vệ bởi snapshot đó.
- **Cho rằng DDL cũng được snapshot:** snapshot dữ liệu không đóng băng data dictionary hoặc định nghĩa bảng. Phải phối hợp DDL riêng.
- **Kết hợp `--single-transaction` với `--lock-tables`:** hai chế độ có ngữ nghĩa xung đột; `LOCK TABLES` có thể implicit commit transaction. Chọn một chiến lược có chủ đích.
- **Bỏ qua transaction đọc kéo dài:** snapshot dài hạn có thể giữ các phiên bản cũ lâu hơn, làm purge chậm và tăng nhu cầu lưu undo.
- **Đánh đồng dump thành công với restore thành công:** file SQL có thể được tạo nhưng thiếu quyền, đối tượng hoặc dữ liệu cần thiết. Phải kiểm tra bằng restore thử.

## 9. Bài thực hành

Một hệ thống bán hàng có database `shop` với các bảng `orders`, `order_items` dùng InnoDB và bảng `legacy_audit` dùng MyISAM. Trong giờ làm việc, ứng dụng liên tục thêm đơn hàng. Nhóm phát triển cũng triển khai migration `ALTER TABLE orders` vào buổi tối. Yêu cầu là tạo bản dump nhất quán để có thể khôi phục database khi xảy ra sự cố.

Hãy thực hiện các nhiệm vụ sau trong môi trường thử nghiệm:

1. Dùng `information_schema.tables` xác định engine của cả ba bảng và lập danh sách các bảng không phải InnoDB.
2. Giải thích `mysqldump --single-transaction` sẽ bảo đảm điều gì cho `orders` và `order_items`, và vì sao không thể đưa ra cùng cam kết cho `legacy_audit` khi ứng dụng vẫn ghi.
3. Đề xuất lịch phối hợp giữa backup và migration `ALTER TABLE orders`. Nêu rõ khoảng thời gian không được chạy DDL.
4. So sánh phương án tạm dừng ghi với `--lock-all-tables`; xác định tác động đến hoạt động của ứng dụng.
5. Tạo dump theo chiến lược đã chọn, ghi nhận mã thoát và dung lượng file, sau đó restore vào database kiểm thử.
6. Đối chiếu số lượng bản ghi và các đối tượng schema quan trọng sau restore. Giải thích giới hạn của việc chỉ so sánh `COUNT(*)` khi dữ liệu có thể thay đổi theo nghiệp vụ.

Kết quả mong đợi là một quyết định backup có căn cứ: biết bảng nào được bảo vệ bởi consistent snapshot, biết lúc nào phải ngăn DDL hoặc DML, và có bằng chứng rằng bản dump có thể khôi phục.

## Kết luận

`mysqldump --single-transaction` tạo consistent snapshot hữu ích cho các bảng InnoDB nhờ MVCC và isolation level `REPEATABLE READ`. DML có thể tiếp tục trong lúc dump, nhưng DDL trên bảng đang sao lưu có thể làm hỏng giả định về cấu trúc và khiến đầu ra không chính xác. Bảng nontransactional cũng không tham gia snapshot, nên cần dừng ghi, dùng khóa đọc phù hợp hoặc thay đổi thiết kế storage engine. Hãy kiểm tra engine trước mỗi kế hoạch backup, điều phối migration và luôn xác minh bằng một lần restore thử.
