# SQLite: chế độ journal, WAL và mô hình đồng thời giữa đọc với ghi

SQLite là hệ quản trị cơ sở dữ liệu quan hệ nhúng: ứng dụng thường truy cập database thông qua một thư viện trong cùng process và dữ liệu được lưu trong một file. SQLite không vận hành như một database server có nhiều worker ghi song song. Nó điều phối truy cập bằng transaction, khóa file và journal để bảo vệ tính nguyên tử, nhất quán và bền vững.

Hai chế độ journal quan trọng nhất là **rollback journal** và **Write-Ahead Logging (WAL)**. Chúng có cách phối hợp reader, writer và commit khác nhau. Rollback journal ghi lại nội dung trang cũ để có thể khôi phục nếu transaction chưa hoàn tất. WAL ghi các trang mới vào file log trước, rồi checkpoint chúng trở lại database sau.

WAL thường cải thiện concurrency cho workload có nhiều lượt đọc đồng thời với một lượt ghi: reader có thể tiếp tục đọc snapshot trong khi writer thêm dữ liệu vào WAL. Tuy nhiên, SQLite vẫn chỉ cho phép **một writer tại một thời điểm**. WAL không biến SQLite thành hệ thống có nhiều transaction ghi song song.

## 1. SQLite lưu dữ liệu và bảo vệ transaction như thế nào?

Một database SQLite thông thường là một file, ví dụ `app.db`. Khi transaction thay đổi dữ liệu, SQLite phải bảo đảm rằng sau commit, dữ liệu mới có thể được đọc; nếu transaction rollback hoặc process/crash xảy ra giữa chừng, database không bị để lại ở trạng thái ghi dở.

SQLite dùng journal để phục vụ mục tiêu này. Tùy journal mode, các file phụ thường gặp là:

| File | Vai trò |
| --- | --- |
| `app.db` | File database chính, chứa các trang dữ liệu hiện hành |
| `app.db-journal` | Rollback journal trong các chế độ rollback-journal; lưu thông tin cần để khôi phục trang cũ |
| `app.db-wal` | WAL; lưu các frame trang mới đã được ghi, bao gồm dữ liệu commit chưa được checkpoint vào file chính |
| `app.db-shm` | Vùng chia sẻ dùng làm WAL index trong WAL mode; giúp các connection tìm frame trong WAL hiệu quả |

Không được tự ý xóa `-journal`, `-wal` hoặc `-shm` trong lúc database đang được sử dụng. Đặc biệt, file `-wal` có thể chứa các transaction đã commit nhưng chưa checkpoint; xóa nó bằng thao tác file có thể làm mất dữ liệu. File `-shm` có thể được dựng lại, nhưng vẫn không nên can thiệp thủ công khi connection đang mở.

SQLite phối hợp các connection thông qua cơ chế khóa của hệ điều hành và các cấu trúc nội bộ. Một connection có thể đọc trong khi connection khác đang chuẩn bị ghi, nhưng quyền ghi được điều phối để tránh hai writer thay đổi database đồng thời.

## 2. Rollback journal: ghi lại trang cũ trước khi sửa database

Rollback journal là mô hình journal truyền thống và thường là chế độ mặc định của SQLite. Trước khi ghi đè một trang trong file database, SQLite lưu bản sao trang cũ vào journal. Nếu transaction rollback hoặc crash xảy ra trước khi commit hoàn tất, SQLite có thể dùng bản sao đó để khôi phục file database.

Quy trình khái quát:

```text
BEGIN
  |
  v
Đọc trang database
  |
  v
Ghi bản sao trang cũ vào rollback journal
  |
  v
Thay đổi trang trong cache của SQLite
  |
  v
Đến commit: lấy quyền độc quyền cần thiết
  |
  v
Ghi các trang mới về database
  |
  v
Hoàn tất journal theo journal_mode
  |
  v
COMMIT hoàn tất
```

Điểm quan trọng là dữ liệu gốc được bảo vệ trong journal trước khi các trang database bị ghi đè. Journal cho phép phục hồi nếu việc ghi database chưa hoàn tất.

### Các trạng thái khóa trong rollback-journal mode

SQLite mô tả các trạng thái khóa file chính gồm:

- **UNLOCKED:** connection không giữ khóa đọc/ghi trên file database.
- **SHARED:** connection có thể đọc database. Nhiều connection có thể cùng giữ SHARED lock.
- **RESERVED:** một connection đã tuyên bố ý định ghi. Nó vẫn có thể cùng tồn tại với SHARED lock của reader khác; chỉ một RESERVED lock được tồn tại tại một thời điểm.
- **PENDING:** writer đang chờ quyền độc quyền. PENDING ngăn reader mới vào, trong khi reader đang có SHARED lock được phép kết thúc.
- **EXCLUSIVE:** connection có quyền truy cập độc quyền cần thiết để ghi các trang database; không connection nào khác được giữ SHARED lock trên file trong thời gian này.

Sơ đồ đơn giản:

```text
UNLOCKED
   |
   | bắt đầu đọc
   v
SHARED
   |
   | yêu cầu quyền ghi
   v
RESERVED
   |
   | chờ reader hiện tại rời đi
   v
PENDING
   |
   | không còn SHARED lock
   v
EXCLUSIVE
   |
   | ghi database và hoàn tất commit
   v
UNLOCKED
```

Đây là sơ đồ khái niệm; chi tiết chuyển trạng thái và thời điểm lấy khóa phụ thuộc thao tác đọc/ghi và đường đi của transaction.

### Reader và writer trong rollback journal

Nhiều reader có thể cùng giữ SHARED lock. Một writer có thể lấy RESERVED lock trong khi reader vẫn đọc. Điều này cho phép writer chuẩn bị thay đổi và ghi journal mà chưa cần chặn tất cả reader ngay lập tức.

Khi đến giai đoạn ghi các trang database để commit, writer cần EXCLUSIVE lock. Nếu còn reader đang giữ SHARED lock, writer phải chờ. Khi writer chuyển sang PENDING, reader mới không được bắt đầu; reader cũ kết thúc rồi writer mới có thể lấy EXCLUSIVE.

Vì vậy, trong rollback-journal mode, một transaction ghi có thể thực hiện phần chuẩn bị song song với reader, nhưng giai đoạn commit cần quyền độc quyền và có thể làm reader mới phải chờ. Với workload đọc liên tục, writer có thể gặp thời gian chờ khi cần commit.

## 3. Các rollback journal mode

SQLite có một số chế độ quản lý rollback journal. Chúng khác nhau chủ yếu ở cách xử lý file journal sau commit.

| Chế độ | Cách xử lý journal | Đặc điểm |
| --- | --- | --- |
| `DELETE` | Xóa file journal sau commit | Chế độ truyền thống và thường là mặc định |
| `TRUNCATE` | Giữ file nhưng cắt về độ dài 0 | Tránh tạo/xóa file liên tục |
| `PERSIST` | Giữ file và vô hiệu hóa header journal | Có thể giảm thao tác filesystem khi transaction lặp lại |
| `MEMORY` | Giữ rollback journal trong bộ nhớ | Không có journal bền vững để phục hồi sau process/power failure |
| `OFF` | Tắt rollback journal | Có rủi ro nghiêm trọng về atomicity và hỏng database nếu lỗi/crash khi ghi |
| `WAL` | Dùng write-ahead log thay rollback journal | Cho phép reader tiếp tục đọc snapshot trong khi writer ghi WAL |

Có thể chọn rollback-journal mode bằng pragma, ví dụ:

```sql
PRAGMA journal_mode = DELETE;
PRAGMA journal_mode = TRUNCATE;
PRAGMA journal_mode = PERSIST;
```

SQLite trả về chế độ thực tế được áp dụng. Hãy đọc kết quả pragma thay vì giả định lệnh đã thành công. Không nên dùng `MEMORY` hoặc `OFF` cho dữ liệu cần khả năng phục hồi thông thường chỉ để giảm I/O. `OFF` đặc biệt nguy hiểm vì một lỗi giữa lúc ghi có thể để lại database hỏng.

`journal_mode` là thiết lập ở cấp database và một số thay đổi chế độ không thể thực hiện khi transaction đang mở hoặc connection khác đang sử dụng database. Hãy cấu hình ở giai đoạn khởi tạo, không đổi mode tùy tiện giữa các request.

## 4. WAL là gì?

WAL là viết tắt của Write-Ahead Logging. Thay vì ghi đè ngay các trang cũ trong file database chính, SQLite ghi các phiên bản trang mới vào file `app.db-wal`. Khi transaction commit, WAL chứa các frame và dấu mốc commit để SQLite biết transaction nào đã hoàn tất.

File database chính chưa nhất thiết được cập nhật ngay sau mỗi commit. Một hoạt động riêng gọi là **checkpoint** sẽ chuyển các trang đã commit từ WAL về file database chính.

```text
                 +------------------+
Reader ----------|  app.db (main)   |
                 +------------------+
                          ^
                          | checkpoint
                          |
Writer ---> app.db-wal ---+
            (append frames)
```

WAL thay đổi cách reader và writer tương tác: reader có thể tiếp tục đọc snapshot từ database chính kết hợp với các frame phù hợp trong WAL, trong khi writer nối thêm frame mới vào WAL. Writer không cần ghi đè các trang mà reader đang dùng để đọc.

## 5. Cách reader nhìn thấy snapshot trong WAL mode

Khi một read transaction bắt đầu, SQLite xác định một mốc trong WAL, thường được gọi là **end mark**. Mốc này xác định các commit mà snapshot của reader được phép nhìn thấy.

Reader tra cứu một trang theo nguyên tắc khái quát:

1. Nếu WAL có frame phù hợp với trang và frame đó nằm trong snapshot của reader, dùng phiên bản trong WAL mới nhất nhưng không vượt quá end mark.
2. Nếu không có frame phù hợp trong phạm vi snapshot, đọc trang từ file database chính.
3. Các frame được writer thêm sau end mark không xuất hiện trong snapshot hiện tại của reader.

Do đó, một reader đang chạy có thể tiếp tục nhìn thấy snapshot nhất quán ngay cả khi writer commit dữ liệu mới trong lúc reader chưa kết thúc.

Ví dụ:

```text
Thời điểm 1: R1 bắt đầu đọc, snapshot kết thúc ở commit C10.
Thời điểm 2: W1 ghi transaction mới vào WAL và commit C11.
Thời điểm 3: R1 tiếp tục truy vấn.

R1 vẫn đọc theo snapshot đến C10.
Một reader mới R2 có thể nhìn thấy C11.
```

Đây là hành vi snapshot isolation của WAL reader. Nó không có nghĩa R1 tự động chuyển sang dữ liệu mới khi writer commit. Muốn nhìn thấy thay đổi mới, reader cần kết thúc transaction cũ và bắt đầu transaction mới.

## 6. WAL cho phép nhiều reader nhưng vẫn chỉ một writer

Trong WAL mode:

- Nhiều reader có thể cùng đọc database.
- Một writer có thể ghi thêm vào WAL trong khi các reader đang đọc snapshot.
- Chỉ một writer được ghi vào WAL tại một thời điểm.
- Các writer khác phải chờ hoặc nhận lỗi `SQLITE_BUSY` tùy tình huống và cấu hình chờ.

Sơ đồ:

```text
R1: đọc snapshot C10 ---------------------- kết thúc
R2:       đọc snapshot C10/C11 ------------------- kết thúc
W1:             ghi WAL -> COMMIT C11
W2:                                      chờ W1 xong -> ghi WAL
```

WAL cải thiện concurrency chủ yếu vì reader không phải nhường quyền đọc file chính cho writer ở mọi commit. Nhưng SQLite không cho hai writer cùng thay đổi database đồng thời. Nếu workload có nhiều ghi liên tục vào cùng database, writer vẫn phải xếp hàng và WAL không loại bỏ nút thắt một writer.

WAL thường phù hợp với ứng dụng có nhiều lượt đọc, ghi ngắn và số writer vừa phải. Với workload ghi dày đặc, cần đo throughput và lock wait; một database server như PostgreSQL hoặc MySQL có thể phù hợp hơn nếu ứng dụng cần nhiều writer song song.

## 7. Checkpoint: chuyển dữ liệu từ WAL về database chính

Checkpoint là quá trình sao chép các frame đã commit từ WAL về các trang tương ứng trong file database chính. Khi checkpoint hoàn tất đủ điều kiện, SQLite có thể tái sử dụng hoặc thu gọn WAL.

Checkpoint không phải là commit của transaction ứng dụng. Transaction đã commit khi commit record được ghi vào WAL theo cơ chế durability đang cấu hình. Checkpoint là bước hợp nhất dữ liệu từ WAL vào file chính để quản lý kích thước và phục hồi.

SQLite hỗ trợ các kiểu checkpoint chính:

| Kiểu | Hành vi khái quát |
| --- | --- |
| `PASSIVE` | Checkpoint những frame có thể xử lý ngay, không chờ reader/writer cản trở |
| `FULL` | Chờ điều kiện cần thiết để checkpoint toàn bộ WAL hiện có đến giới hạn có thể checkpoint |
| `RESTART` | Giống FULL và chờ để WAL có thể được bắt đầu lại từ đầu khi không còn reader cần nội dung cũ |
| `TRUNCATE` | Giống RESTART và cố gắng cắt file WAL về độ dài 0 |

Có thể yêu cầu checkpoint thủ công:

```sql
PRAGMA wal_checkpoint(PASSIVE);
PRAGMA wal_checkpoint(FULL);
PRAGMA wal_checkpoint(RESTART);
PRAGMA wal_checkpoint(TRUNCATE);
```

Kết quả pragma chứa thông tin về checkpoint; ứng dụng vận hành nên đọc kết quả và theo dõi WAL thay vì chỉ gửi lệnh rồi giả định toàn bộ frame đã được chuyển.

SQLite thường tự động checkpoint khi WAL đạt một ngưỡng số trang nhất định. Có thể cấu hình `wal_autocheckpoint`, nhưng không nên tắt auto-checkpoint nếu chưa có worker hoặc quy trình checkpoint thay thế.

## 8. Reader lâu có thể làm WAL tăng kích thước

Một reader giữ snapshot cũ cần những frame WAL thuộc snapshot đó. Checkpoint không thể tùy tiện ghi đè hoặc tái sử dụng các frame mà reader còn cần. Nếu một transaction đọc kéo dài, checkpoint có thể chỉ hoàn tất một phần và WAL không thể reset.

Ví dụ:

```text
R1: BEGIN; SELECT ...; giữ snapshot C10 ---------------------------
W1:                ghi và commit C11
W2:                       ghi và commit C12
W3:                              ghi và commit C13
Checkpoint: có thể bị giới hạn bởi snapshot cũ mà R1 đang giữ
```

Nếu R1 giữ snapshot lâu, các writer tiếp tục thêm dữ liệu vào WAL. File `-wal` có thể tăng kích thước vì checkpoint chưa thể hoàn tất việc reset. Đây thường được gọi là checkpoint starvation hoặc checkpoint bị reader lâu cản trở.

Các biện pháp giảm vấn đề:

1. Giữ read transaction ngắn; không mở transaction rồi chờ người dùng hoặc gọi dịch vụ mạng.
2. Đọc theo từng trang/batch và kết thúc transaction khi không còn cần snapshot cũ.
3. Theo dõi kích thước file WAL và kết quả checkpoint.
4. Chọn chế độ checkpoint phù hợp với latency của ứng dụng.
5. Tránh một cursor hoặc result set mở lâu nếu nó giữ read transaction trong thời gian dài.

Không nên xóa file WAL bằng filesystem để xử lý WAL lớn. Hãy xác định reader nào đang giữ snapshot, cho transaction kết thúc và dùng checkpoint theo quy trình SQLite.

## 9. BEGIN DEFERRED, BEGIN IMMEDIATE và BEGIN EXCLUSIVE

SQLite hỗ trợ ba transaction mode thường gặp. Chúng quyết định thời điểm transaction yêu cầu quyền ghi.

### BEGIN DEFERRED

```sql
BEGIN DEFERRED;
```

Đây là mode mặc định khi dùng `BEGIN` không ghi rõ mode. Lệnh bắt đầu transaction logic nhưng chưa giành quyền đọc/ghi ngay lập tức. Khi câu lệnh đầu tiên đọc database chạy, transaction bắt đầu giữ snapshot/khóa đọc. Khi câu lệnh ghi đầu tiên chạy, transaction cố nâng cấp thành writer.

Ưu điểm là không chiếm quyền writer nếu transaction chỉ đọc. Nhược điểm là transaction có thể đọc trước rồi mới phát hiện không thể nâng cấp sang writer vì transaction khác đã ghi hoặc đang giữ quyền ghi.

### BEGIN IMMEDIATE

```sql
BEGIN IMMEDIATE;
```

Lệnh này yêu cầu bắt đầu write transaction ngay. Nếu một writer khác đang hoạt động, SQLite có thể trả `SQLITE_BUSY` (hoặc chờ theo busy handler/timeout). Nếu thành công, transaction đã giành được quyền writer trước khi thực hiện phần đọc và tính toán.

`BEGIN IMMEDIATE` hữu ích khi biết chắc transaction sẽ ghi và muốn phát hiện tranh chấp writer ngay từ đầu, thay vì đọc nhiều dữ liệu rồi mới thất bại khi nâng cấp. Đổi lại, nó chiếm slot writer sớm hơn, nên không nên dùng cho transaction chỉ đọc hoặc giữ transaction quá lâu.

### BEGIN EXCLUSIVE

```sql
BEGIN EXCLUSIVE;
```

Trong rollback-journal mode, EXCLUSIVE transaction lấy quyền độc quyền và ngăn connection khác đọc database trong thời gian transaction giữ khóa. Trong WAL mode, `BEGIN EXCLUSIVE` có hành vi giống `BEGIN IMMEDIATE` đối với reader: reader vẫn có thể tiếp tục đọc snapshot, còn quyền writer vẫn chỉ có một.

Không nên dùng `BEGIN EXCLUSIVE` chỉ vì tên nghe có vẻ an toàn hơn. Nó có thể chặn reader trong rollback mode và làm giảm concurrency. Chọn mode theo mục tiêu cụ thể.

### So sánh nhanh

| Mode | Khi lấy quyền | Rollback-journal mode | WAL mode | Thường phù hợp |
| --- | --- | --- | --- | --- |
| `DEFERRED` | Khi statement đầu tiên đọc/ghi cần truy cập database | Có thể bắt đầu đọc rồi mới nâng cấp để ghi | Có thể bắt đầu snapshot đọc rồi thử lấy quyền writer sau | Transaction có thể chỉ đọc |
| `IMMEDIATE` | Ngay khi BEGIN | Lấy quyền writer chuẩn bị ghi; reader hiện tại vẫn có thể đọc | Lấy slot writer; reader vẫn tiếp tục đọc | Transaction chắc chắn sẽ ghi |
| `EXCLUSIVE` | Ngay khi BEGIN | Giành quyền độc quyền, ngăn reader khác | Về cơ bản như IMMEDIATE đối với reader | Trường hợp cần độc quyền trong rollback mode và chấp nhận chặn reader |

## 10. SQLITE_BUSY và SQLITE_BUSY_SNAPSHOT

Vì SQLite chỉ có một writer, ứng dụng phải xử lý trường hợp không lấy được quyền ghi ngay.

### SQLITE_BUSY

`SQLITE_BUSY` thường có nghĩa một connection không thể lấy khóa hoặc quyền cần thiết vì connection khác đang giữ tài nguyên xung đột. Ví dụ:

- Một writer khác đang thực hiện transaction.
- Transaction rollback-journal cần EXCLUSIVE để commit nhưng reader chưa kết thúc.
- `BEGIN IMMEDIATE` không thể lấy slot writer vì writer khác đang hoạt động.

Ứng dụng có thể cấu hình thời gian chờ:

```sql
PRAGMA busy_timeout = 5000;
```

Lệnh trên đặt busy timeout khoảng 5 giây cho connection hiện tại. Cũng có API tương ứng ở SQLite C interface và các tùy chọn trong JDBC driver. Timeout không làm xung đột biến mất; nó chỉ cho phép SQLite chờ trước khi trả lỗi. Nếu transaction vẫn không thể tiếp tục, ứng dụng cần rollback và thử lại theo chính sách phù hợp.

### SQLITE_BUSY_SNAPSHOT trong WAL mode

Một tình huống đặc trưng của WAL xảy ra khi transaction đã bắt đầu đọc snapshot cũ, một writer khác commit thay đổi mới, rồi transaction đọc cũ cố nâng cấp thành writer. SQLite không thể cho transaction đó ghi dựa trên snapshot đã lỗi thời theo cách làm mất tính tuần tự hóa. Nó có thể trả `SQLITE_BUSY_SNAPSHOT`.

Ví dụ:

```text
T1: BEGIN DEFERRED
T1: SELECT ...       -> snapshot S0

T2: BEGIN IMMEDIATE
T2: UPDATE ...
T2: COMMIT           -> database có snapshot mới S1

T1: UPDATE ...       -> SQLITE_BUSY_SNAPSHOT
```

T1 không thể chỉ retry câu UPDATE trong transaction cũ vì snapshot của nó vẫn là S0. Cách xử lý đúng thường là rollback T1, bắt đầu transaction mới để lấy snapshot mới S1, đọc lại dữ liệu và tính toán lại toàn bộ quyết định.

`busy_timeout` không giải quyết được stale snapshot theo cách chờ đơn thuần. Đây không chỉ là writer đang bận; transaction hiện tại cần một snapshot mới để tiếp tục ghi hợp lệ.

### SQLITE_LOCKED

`SQLITE_LOCKED` là một nhóm lỗi khóa khác với `SQLITE_BUSY`, thường liên quan đến xung đột trong cùng connection hoặc shared-cache/table-level locking. Không nên gom mọi lỗi khóa thành một lỗi timeout duy nhất. Hãy xem mã lỗi mở rộng và ngữ cảnh driver để quyết định rollback, đóng statement/cursor hoặc thử lại.

## 11. Cách thiết kế transaction đọc rồi ghi

Nếu transaction chắc chắn sẽ ghi, `BEGIN IMMEDIATE` thường giúp tránh đọc xong rồi mới tranh slot writer. Ví dụ:

```sql
BEGIN IMMEDIATE;

SELECT quantity
FROM inventory
WHERE product_id = 501;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 501
  AND quantity > 0;

-- Ứng dụng kiểm tra đúng một hàng được cập nhật.
COMMIT;
```

Transaction lấy quyền writer trước khi đọc số lượng. Writer khác phải chờ, nên transaction không gặp tình huống một writer khác commit chen vào giữa snapshot đọc và bước nâng cấp quyền ghi theo cách của deferred transaction.

Tuy vậy, hãy dùng điều kiện trong UPDATE và constraint như `CHECK (quantity >= 0)` để bảo vệ quy tắc tồn kho. Khóa điều phối không thay thế kiểm tra nghiệp vụ ở câu ghi.

Nếu transaction chỉ đọc, hãy dùng read transaction thông thường thay vì chiếm writer slot. Một truy vấn báo cáo dài không nên dùng `BEGIN IMMEDIATE` vì nó sẽ ngăn writer khác hoạt động trong suốt thời gian báo cáo.

## 12. Cấu hình WAL và các pragma thường dùng

Để bật WAL:

```sql
PRAGMA journal_mode = WAL;
```

SQLite trả về journal mode thực tế. Nên thực hiện cấu hình này trong giai đoạn khởi tạo database, ngoài transaction đang mở. WAL mode được lưu bền trong database và các connection sau thường tiếp tục sử dụng mode đó.

Một số pragma thường được cân nhắc:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA wal_autocheckpoint = 1000;
```

Ý nghĩa:

- `journal_mode`: chọn rollback journal hoặc WAL.
- `synchronous`: điều chỉnh mức đồng bộ dữ liệu với thiết bị lưu trữ và trade-off giữa durability với hiệu năng.
- `busy_timeout`: thời gian chờ khi gặp một số xung đột khóa.
- `wal_autocheckpoint`: ngưỡng trang WAL kích hoạt auto-checkpoint.

### synchronous trong WAL mode

Hai cấu hình thường được cân nhắc là `FULL` và `NORMAL`:

- `FULL` đồng bộ WAL ở mỗi commit theo yêu cầu durability của SQLite, giúp bảo vệ commit tốt hơn khi mất điện hoặc hệ thống crash.
- `NORMAL` vẫn bảo vệ tính nhất quán của database, nhưng một số transaction gần nhất có thể bị mất sau power loss do WAL chưa được đồng bộ ở mỗi commit. Database vẫn có thể phục hồi về trạng thái nhất quán.

Chọn `synchronous` theo mức độ chấp nhận mất dữ liệu đã được xác nhận và đặc tính thiết bị lưu trữ. Không nên chọn `NORMAL` chỉ vì benchmark nhanh hơn nếu nghiệp vụ yêu cầu durability cao nhất. `OFF` hoặc cấu hình journal yếu hơn cần được cân nhắc rất thận trọng.

Một số pragma như `busy_timeout`, `foreign_keys` và các thiết lập connection cần được áp dụng cho từng connection. Đừng giả định cấu hình trên một connection tự động áp dụng cho tất cả connection trong pool.

## 13. WAL không phù hợp với mọi môi trường file

WAL dựa vào file WAL và vùng shared memory để phối hợp các connection. Vì vậy, các process truy cập cùng database WAL cần chạy trên cùng một máy chủ có khả năng chia sẻ vùng nhớ phù hợp. WAL không được thiết kế để nhiều máy truy cập cùng database qua filesystem mạng như NFS.

Nếu ứng dụng đặt file SQLite trên network filesystem hoặc thư mục đồng bộ cloud, cần kiểm tra rõ hỗ trợ khóa và shared memory của filesystem. WAL thường yêu cầu database và các file phụ nằm trên filesystem local phù hợp.

Nếu cần truy cập database từ nhiều máy qua mạng, nên đặt SQLite sau một service trên cùng host hoặc cân nhắc hệ quản trị client-server. Không nên chia sẻ trực tiếp file WAL qua mạng cho nhiều host như thể đó là một database server.

## 14. Sao lưu database khi đang dùng WAL

Trong WAL mode, file `app.db` có thể chưa chứa các transaction mới nhất vì một phần dữ liệu đã commit còn nằm trong `app.db-wal`. Chỉ sao chép file database chính trong lúc ứng dụng đang hoạt động có thể tạo bản backup thiếu dữ liệu hoặc không nhất quán.

Các cách an toàn hơn:

- Dùng SQLite Online Backup API hoặc công cụ backup hiểu SQLite.
- Dùng lệnh `.backup` trong SQLite CLI khi phù hợp.
- Dùng `VACUUM INTO` trong phiên bản hỗ trợ và theo quy trình vận hành phù hợp.
- Nếu tự sao chép file, phải phối hợp dừng/đóng connection và checkpoint theo quy trình đảm bảo; không chỉ copy file `.db` riêng lẻ khi WAL còn hoạt động.

WAL và SHM là file phụ có vòng đời do SQLite quản lý. Khi tất cả connection đóng bình thường, SQLite có thể checkpoint và dọn file phụ tùy trạng thái. Không nên xóa chúng thủ công để “dọn dung lượng”.

## 15. Ví dụ Java/JDBC

SQLite thường được truy cập từ Java qua JDBC driver. Connection JDBC mặc định thường ở autocommit; mỗi statement độc lập có thể trở thành một transaction riêng. Khi nhiều câu lệnh cần cùng thành công hoặc cùng rollback, hãy dùng transaction rõ ràng.

Ví dụ JDBC tổng quát:

```java
try (Connection connection = DriverManager.getConnection("jdbc:sqlite:app.db")) {
    connection.setAutoCommit(false);

    try {
        int updated;
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE inventory " +
                "SET quantity = quantity - ? " +
                "WHERE product_id = ? AND quantity >= ?")) {
            statement.setInt(1, 1);
            statement.setLong(2, 501L);
            statement.setInt(3, 1);
            updated = statement.executeUpdate();
        }

        if (updated != 1) {
            throw new IllegalStateException("Không đủ hàng hoặc không tìm thấy sản phẩm");
        }

        connection.commit();
    } catch (Exception ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Đây là mẫu transaction JDBC; cách driver bắt đầu transaction khi `setAutoCommit(false)` phụ thuộc driver. Thông thường transaction bắt đầu theo mode deferred khi câu lệnh đầu tiên truy cập database chạy.

Nếu cần `BEGIN IMMEDIATE`, phải dùng cách cấu hình transaction mode được JDBC driver cụ thể hỗ trợ hoặc điều khiển transaction bằng cú pháp SQLite theo hướng dẫn của driver. Không nên gọi `BEGIN IMMEDIATE` sau khi driver đã mở transaction bằng `setAutoCommit(false)`, vì SQLite sẽ báo lỗi nếu bắt đầu transaction lồng nhau. Cũng không nên trộn `connection.commit()` với explicit SQL transaction theo cách chưa được driver hỗ trợ.

### Cấu hình connection

Ví dụ SQL pragma có thể chạy khi connection được tạo:

```sql
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

`foreign_keys` là thiết lập theo connection trong SQLite, vì vậy cần bật cho mọi connection trong pool. `busy_timeout` cũng cần cấu hình theo connection. Cách cấu hình trong JDBC có thể dùng câu pragma hoặc tùy chọn riêng của driver.

WAL mode thường được bật một lần khi khởi tạo database:

```sql
PRAGMA journal_mode = WAL;
```

Không cần chạy đổi journal mode trên mọi request. Sau khi bật, hãy xác nhận kết quả và quản lý database, WAL, SHM bằng cùng một cấu hình đường dẫn.

## 16. Mẫu worker queue trong SQLite

Vì SQLite chỉ có một writer, nhiều worker có thể cùng đọc danh sách việc nhưng chỉ một worker tại một thời điểm ghi trạng thái. Có thể dùng một câu UPDATE có điều kiện để claim một job nguyên tử:

```sql
BEGIN IMMEDIATE;

UPDATE job_queue
SET status = 'PROCESSING',
    claimed_at = CURRENT_TIMESTAMP
WHERE job_id = (
    SELECT job_id
    FROM job_queue
    WHERE status = 'READY'
    ORDER BY created_at
    LIMIT 1
)
AND status = 'READY';

COMMIT;
```

Sau đó ứng dụng đọc job đã claim và xử lý ngoài transaction nếu công việc kéo dài. Không giữ writer transaction mở trong lúc gọi dịch vụ ngoài. Nếu process chết khi job đang PROCESSING, cần lease/timeout hoặc cơ chế phục hồi để job có thể được claim lại.

Không nên cố mô phỏng `SKIP LOCKED` như một database server có nhiều writer độc lập. Với SQLite, một writer slot đã đủ để tuần tự hóa thao tác claim; các worker khác phải chờ hoặc thử lại. Thiết kế queue cần tính đến mô hình một writer của engine.

## 17. Chọn rollback journal hay WAL?

| Đặc điểm workload | Rollback journal | WAL |
| --- | --- | --- |
| Ứng dụng nhỏ, ít concurrency | Đơn giản và phù hợp | Vẫn dùng được nhưng có thêm file WAL/SHM và checkpoint |
| Nhiều reader và writer ngắn | Reader có thể bị ảnh hưởng khi writer cần EXCLUSIVE để commit | Reader thường tiếp tục đọc snapshot trong lúc writer ghi WAL |
| Nhiều writer đồng thời | Chỉ một writer; writer có thể chờ reader ở giai đoạn commit | Vẫn chỉ một writer; writer khác chờ slot ghi |
| Đọc transaction dài | Có thể khiến writer khó lấy EXCLUSIVE để commit | Có thể làm checkpoint bị chặn và WAL tăng kích thước |
| File trên filesystem mạng | Phụ thuộc locking của filesystem; cần thận trọng | Không phù hợp với truy cập WAL đa host qua network filesystem |
| Vận hành backup | Cần phối hợp transaction và file journal | Phải tính cả WAL; dùng backup API hoặc quy trình hiểu WAL |

WAL thường là lựa chọn tốt cho ứng dụng đọc nhiều và cần reader/writer chạy đồng thời trên cùng host. Rollback journal vẫn phù hợp với workload đơn giản, file database nhỏ hoặc môi trường cần tránh các yêu cầu vận hành đặc thù của WAL.

Hãy benchmark bằng workload thực tế: số reader, số writer, kích thước transaction, thời gian giữ cursor, tần suất checkpoint, filesystem và cấu hình `synchronous`. Không chọn mode chỉ dựa vào một phép đo insert đơn lẻ.

## 18. Những lỗi thiết kế thường gặp

### Nghĩ rằng WAL cho phép nhiều writer cùng lúc

WAL cho reader và writer hoạt động đồng thời tốt hơn, nhưng vẫn chỉ một writer được ghi vào WAL tại một thời điểm. Nhiều transaction ghi vẫn phải xếp hàng.

### Dùng DEFERRED cho transaction chắc chắn sẽ ghi rồi bất ngờ gặp lỗi khi nâng cấp

Transaction có thể đọc snapshot trước, sau đó không nâng cấp được thành writer. Nếu biết chắc sẽ ghi, cân nhắc `BEGIN IMMEDIATE` để giành quyền writer ngay từ đầu.

### Giữ read transaction quá lâu

Reader lâu trong WAL có thể giữ snapshot cũ, ngăn checkpoint reset WAL và làm file WAL tăng kích thước. Hãy đóng cursor/result set và kết thúc transaction sớm.

### Chỉ retry câu UPDATE sau SQLITE_BUSY_SNAPSHOT

Snapshot của transaction cũ đã lỗi thời. Cần rollback và chạy lại toàn bộ transaction với snapshot mới, bao gồm đọc và tính toán lại.

### Tăng busy_timeout để xử lý mọi lỗi khóa

Timeout chỉ giúp chờ một số xung đột khóa có thể giải quyết khi connection khác kết thúc. Nó không sửa stale snapshot, deadlock logic hoặc transaction bị giữ vô hạn. Vẫn cần transaction ngắn, retry có giới hạn và quan sát lỗi.

### Xóa file WAL bằng tay

WAL có thể chứa dữ liệu đã commit nhưng chưa checkpoint. Xóa file khi database đang hoạt động có thể làm mất dữ liệu hoặc phá hỏng trạng thái database. Dùng checkpoint và backup API.

### Đặt WAL trên network filesystem

WAL phụ thuộc shared memory và locking phù hợp trên cùng host. Chia sẻ file WAL qua nhiều máy có thể không hoạt động an toàn. Đặt database trên filesystem local được hỗ trợ hoặc dùng database server.

### Nghĩ rằng flush/statement thành công có nghĩa transaction đã commit

Một statement có thể chạy trong transaction nhưng transaction vẫn rollback. Chỉ coi thay đổi đã hoàn tất khi commit thành công; nếu mất kết nối trong commit, kết quả có thể chưa xác định và cần cơ chế phục hồi phù hợp.

## 19. Quy trình xử lý SQLITE_BUSY trong ứng dụng

Một chiến lược xử lý lỗi có thể gồm:

1. Phân biệt `SQLITE_BUSY`, `SQLITE_BUSY_SNAPSHOT` và `SQLITE_LOCKED` bằng mã lỗi cụ thể của driver.
2. Với `SQLITE_BUSY` khi bắt đầu transaction ghi, chờ theo busy timeout hoặc backoff rồi thử lại transaction nếu thao tác an toàn.
3. Với `SQLITE_BUSY_SNAPSHOT`, rollback transaction đọc cũ, bắt đầu transaction mới và đọc lại dữ liệu trước khi ghi.
4. Với `SQLITE_LOCKED`, kiểm tra cursor/statement chưa đóng, shared-cache hoặc xung đột khóa nội bộ; không retry mù quáng.
5. Giới hạn số lần retry và thêm jitter để nhiều request không liên tục va chạm cùng thời điểm.
6. Giữ transaction ngắn và không thực hiện network I/O khi đang giữ quyền writer.
7. Đảm bảo thao tác retry không lặp tác dụng phụ bên ngoài database; dùng idempotency key hoặc outbox nếu cần.

Không nên retry vô hạn. Nếu workload liên tục gặp writer contention, tăng timeout có thể chỉ làm request chờ lâu hơn. Cần giảm thời gian giữ transaction, gom thao tác hợp lý hoặc chuyển sang hệ quản trị client-server nếu yêu cầu ghi song song vượt khả năng SQLite.

## 20. Kiểm thử mô hình đọc/ghi

Để kiểm tra journal mode, hãy dùng ít nhất hai connection độc lập và điều khiển thời điểm transaction bắt đầu, đọc, ghi và commit.

### Kiểm thử rollback-journal mode

1. Đặt `PRAGMA journal_mode = DELETE`.
2. Mở R1 và bắt đầu read transaction; thực hiện SELECT để giữ SHARED lock.
3. Mở W1 và bắt đầu write transaction; cập nhật một hàng để lấy quyền writer chuẩn bị.
4. Thử commit W1 trong khi R1 vẫn mở.
5. Quan sát W1 phải chờ hoặc nhận `SQLITE_BUSY` khi cần quyền độc quyền.
6. Kết thúc R1 rồi cho W1 commit lại theo chính sách retry.

### Kiểm thử WAL reader snapshot

1. Đặt `PRAGMA journal_mode = WAL`.
2. R1 bắt đầu transaction và đọc giá trị ban đầu.
3. W1 cập nhật cùng hàng và commit.
4. R1 đọc lại trong cùng transaction và xác nhận vẫn thấy snapshot cũ.
5. Kết thúc R1, mở transaction mới R2 và xác nhận R2 nhìn thấy giá trị mới.

### Kiểm thử BUSY_SNAPSHOT

1. R1 bắt đầu deferred transaction và đọc một hàng.
2. W1 cập nhật hàng đó và commit.
3. R1 thử cập nhật dựa trên snapshot cũ.
4. Xác nhận lỗi snapshot/busy phù hợp với driver.
5. Rollback R1, bắt đầu transaction mới, đọc lại và tính toán lại.

### Kiểm thử checkpoint

1. Mở một read transaction dài trong WAL mode.
2. Thực hiện nhiều transaction ghi ngắn để WAL tăng.
3. Chạy checkpoint và quan sát số frame được checkpoint cùng phần còn lại.
4. Kết thúc reader dài.
5. Chạy checkpoint lại và xác nhận WAL có thể được xử lý/reset theo điều kiện.

Kiểm thử cần chạy trên filesystem và SQLite version gần môi trường triển khai. Hành vi timeout, checkpoint và mã lỗi mở rộng có thể phụ thuộc phiên bản SQLite, JDBC driver và cấu hình connection.

## 21. Những điểm cần ghi nhớ

- SQLite dùng journal để bảo vệ transaction; rollback journal lưu trang cũ, còn WAL ghi trang mới vào file log trước khi checkpoint về database chính.
- Rollback-journal mode dùng các trạng thái khóa SHARED, RESERVED, PENDING và EXCLUSIVE để điều phối reader/writer; writer cần quyền độc quyền ở giai đoạn ghi database để commit.
- `DELETE`, `TRUNCATE` và `PERSIST` khác nhau ở cách xử lý rollback journal; `MEMORY` và `OFF` làm giảm khả năng phục hồi khi process/crash xảy ra.
- WAL cho nhiều reader tiếp tục đọc snapshot trong lúc một writer ghi WAL, nhưng SQLite vẫn chỉ cho phép một writer tại một thời điểm.
- Reader trong WAL giữ end mark/snapshot; nó không tự nhìn thấy commit mới cho đến khi transaction đọc cũ kết thúc và transaction mới bắt đầu.
- Checkpoint chuyển frame đã commit từ WAL về file database chính. Reader dài có thể cản checkpoint và làm WAL tăng kích thước.
- `BEGIN DEFERRED` trì hoãn việc lấy quyền; `BEGIN IMMEDIATE` lấy slot writer ngay; `BEGIN EXCLUSIVE` chặn reader trong rollback mode nhưng gần giống IMMEDIATE trong WAL mode.
- `SQLITE_BUSY_SNAPSHOT` đòi hỏi rollback và bắt đầu transaction mới; chỉ chờ hoặc retry statement trong snapshot cũ không giải quyết được.
- `busy_timeout` hữu ích cho một số lock wait nhưng không thay thế retry có giới hạn và thiết kế transaction ngắn.
- WAL cần shared memory và locking phù hợp trên cùng host; không chia sẻ trực tiếp file WAL qua network filesystem nhiều máy.
- Khi backup ở WAL mode, phải tính cả dữ liệu còn trong WAL; dùng Online Backup API hoặc công cụ hiểu SQLite.
- Trong Java/JDBC, dùng transaction rõ ràng, đóng statement/cursor, cấu hình pragma cho từng connection và kiểm tra transaction mode mà driver thực sự sử dụng.
