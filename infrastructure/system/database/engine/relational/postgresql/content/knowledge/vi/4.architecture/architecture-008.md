# WAL, checkpoint và khôi phục sau sự cố trong bức tranh tổng thể PostgreSQL

Một giao dịch PostgreSQL có thể cập nhật hàng nghìn bản ghi rồi trả về `COMMIT` chỉ sau một khoảng thời gian ngắn, mặc dù dữ liệu của các bản ghi đó chưa nhất thiết được ghi ngay xuống những trang của tệp bảng trên ổ đĩa. Điều này đặt ra câu hỏi quan trọng: **nếu máy chủ mất điện ngay sau khi ứng dụng nhận thông báo commit thành công, PostgreSQL dựa vào đâu để khôi phục dữ liệu?**

Câu trả lời nằm ở sự phối hợp giữa **Write-Ahead Logging (WAL)**, **checkpoint**, cơ chế quản lý các trang dữ liệu trong bộ nhớ và **crash recovery**. WAL ghi lại thông tin đủ để PostgreSQL thực hiện lại các thay đổi cần thiết sau sự cố; checkpoint giúp giới hạn lượng WAL phải xử lý trong quá trình khôi phục. Những cơ chế này cũng là nền tảng cho sao chép vật lý (*physical replication*), lưu trữ WAL để khôi phục theo thời điểm (*point-in-time recovery*, PITR) và nhiều thao tác vận hành khác.

Bài học tập trung vào PostgreSQL dùng các bảng thông thường có WAL, chẳng hạn bảng InnoDB tương đương bên MySQL nhưng ở PostgreSQL là các **bảng logged** mặc định. Một số đối tượng như `UNLOGGED` và bảng tạm có tính chất độ bền khác, sẽ được phân biệt rõ. Các tên hàm, thông số và view có thể thay đổi giữa các major PostgreSQL; khi thực hành trên server cụ thể, hãy đọc manual của đúng phiên bản đó.

## 1. Đặt WAL và checkpoint vào kiến trúc tổng thể

Trước tiên, hãy tách ba khái niệm rất dễ bị trộn lẫn:

- **Trang dữ liệu (*data page*)**: vùng lưu dữ liệu bảng hoặc chỉ mục, có thể được đọc vào bộ nhớ đệm và chỉnh sửa tại đó.
- **WAL record**: bản ghi nhật ký mô tả những thay đổi cần thiết để phục hồi trạng thái, được ghi theo thứ tự trong luồng WAL.
- **Checkpoint**: mốc đồng bộ và kiểm soát tiến độ ghi các trang dữ liệu bẩn từ bộ nhớ xuống bộ lưu trữ, qua đó giới hạn điểm bắt đầu cần redo khi phục hồi.

Sơ đồ giản lược:

```text
                           ỨNG DỤNG
                              |
                       BEGIN / UPDATE
                              |
                              v
                   PostgreSQL backend
                       /           \
                      v             v
              shared_buffers      WAL buffers
              trang dữ liệu        WAL records
              đã thay đổi              |
                  |                    v
                  |                WAL write/flush
                  |                    |
                  v                    v
             Data files             pg_wal/
          (heap / indexes)      (WAL segments)
                  ^                    |
                  |                    |
                Checkpoint ------------+
             ghi dữ liệu bẩn      bảo đảm WAL đi trước

KHI MÁY CHỦ BỊ CRASH:
  data files tại checkpoint + WAL còn cần thiết
                   |
                   v
             WAL REDO / RECOVERY
                   |
                   v
        Trạng thái database có thể sử dụng lại
```

Sơ đồ chỉ thể hiện **quan hệ logic**. Trong triển khai thật, nhiều backend cùng chạy, các trang được ghi vào bộ nhớ và xuống đĩa bởi các tiến trình khác nhau, WAL có nhiều loại record, và hệ điều hành cũng có page cache riêng.

### Các thành phần liên quan

| Thành phần | Vai trò chính |
| --- | --- |
| Backend process | Xử lý SQL của client, sửa trang dữ liệu trong bộ nhớ và tạo WAL record khi cần. |
| Shared buffers | Bộ nhớ đệm các trang dữ liệu PostgreSQL, gồm trang sạch và trang đã thay đổi (*dirty pages*). |
| WAL buffers | Giữ tạm WAL record trước khi được ghi vào các tệp WAL. |
| WAL writer | Hỗ trợ ghi WAL định kỳ; các backend cũng có thể tham gia việc ghi/flush WAL để đáp ứng yêu cầu commit. |
| Checkpointer | Điều phối checkpoint và việc ghi các trang cần thiết nhằm tạo mốc phục hồi. |
| Background writer | Góp phần ghi trang bẩn ra đĩa trong quá trình hoạt động bình thường, giảm áp lực cho backend. |
| `pg_wal` | Thư mục chứa các WAL segment đang được PostgreSQL quản lý để vận hành và phục hồi. |
| Startup/recovery process | Đọc trạng thái checkpoint và thực hiện WAL replay khi cần khôi phục dữ liệu. |
| WAL archiver, nếu cấu hình | Sao chép WAL segment đã hoàn tất sang kho lưu trữ cho các phương án backup/PITR. |

**Không có quy tắc “mỗi lần COMMIT là ghi ngay mọi trang của bảng xuống đĩa”.** Điều cần đảm bảo cho giao dịch bền vững theo cấu hình chuẩn là thông tin WAL liên quan được làm bền trước khi hệ thống xác nhận giao dịch, còn việc ghi các trang dữ liệu có thể diễn ra sau.

## 2. Write-Ahead Logging nghĩa là gì?

Tên gọi **Write-Ahead Logging** mô tả quy tắc “ghi nhật ký trước”: trước khi một trang dữ liệu đã thay đổi được ghi an toàn xuống bộ lưu trữ, các WAL record cần thiết để phục hồi thay đổi đó phải được ghi/flush theo thứ tự thích hợp.

Khi một transaction cập nhật bản ghi:

1. Backend xác định và cập nhật dữ liệu theo cơ chế lưu trữ/MVCC.
2. PostgreSQL sinh WAL record mô tả thay đổi cần thiết cho quá trình redo.
3. Các WAL record được đưa vào WAL buffers và sau đó ghi xuống các WAL segment.
4. Khi commit yêu cầu độ bền đồng bộ theo mặc định, PostgreSQL phải đưa WAL đến mốc commit cần thiết xuống bộ lưu trữ bền vững trước khi báo commit thành công.
5. Trang bảng hoặc chỉ mục tương ứng **có thể được flush sau**, bởi background writer, checkpoint hoặc một đường ghi phù hợp khác.

```text
Thời gian ---->

Trang dữ liệu trong RAM:   UPDATE ------ dirty --------------------- flush
WAL trong RAM:            WAL record --- commit record
WAL trên bộ lưu trữ:                    write + durable flush
                                                  |
                                                  v
                                         COMMIT được xác nhận

Trang dữ liệu không bắt buộc phải được flush tại mốc COMMIT.
```

Nếu xảy ra crash sau khi WAL đã được flush nhưng trước khi trang dữ liệu được ghi, PostgreSQL có thể **đọc WAL và thực hiện redo**. Đây là lý do WAL là thành phần trung tâm của tính bền vững (*durability*) trong ACID.

### WAL không phải bản sao đầy đủ của mọi bảng

WAL là một **luồng bản ghi thay đổi và thông tin phục hồi**, không phải một thư mục chứa bản sao dễ đọc của mỗi bảng. Dù đôi lúc WAL chứa ảnh trang (*full-page image*), không nên hình dung rằng mỗi `INSERT` tạo một bản sao nguyên vẹn của bảng hoặc WAL là một định dạng backup độc lập đủ để dựng lại mọi dữ liệu từ con số không.

Đối với các thao tác của PostgreSQL, WAL record có thể mô tả thay đổi ở cấp trang, trạng thái giao dịch và nhiều hoạt động nội bộ. Người dùng thông thường không trực tiếp tạo WAL record bằng SQL; engine tạo chúng khi thực hiện công việc.

## 3. Ví dụ: một giao dịch được commit trước khi trang dữ liệu được flush

Tạo bảng logged mặc định trong schema thử nghiệm:

```sql
CREATE SCHEMA IF NOT EXISTS wal_lab;

CREATE TABLE wal_lab.account_balances (
    account_id bigint PRIMARY KEY,
    balance numeric(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO wal_lab.account_balances (account_id, balance)
VALUES (101, 1000.00), (202, 500.00);
```

Một giao dịch chuyển 100 đơn vị:

```sql
BEGIN;

UPDATE wal_lab.account_balances
SET balance = balance - 100.00
WHERE account_id = 101;

UPDATE wal_lab.account_balances
SET balance = balance + 100.00
WHERE account_id = 202;

COMMIT;
```

Về mặt logic, hai thay đổi tạo thành một transaction. Với cấu hình durability thông thường của PostgreSQL, khi `COMMIT` trả thành công, engine đã xử lý WAL cần thiết theo ranh giới đồng bộ của giao dịch, nhưng **không yêu cầu hai trang heap tương ứng đều đã được ghi vào file bảng ở thời điểm đó**.

Nếu hệ điều hành hoặc tiến trình PostgreSQL bị crash trước khi hai trang dirty được ghi, PostgreSQL sẽ dùng WAL trong quá trình crash recovery để đưa dữ liệu về trạng thái phù hợp của các giao dịch đã commit.

**Không nên** tạo lỗi crash thật trên production để kiểm chứng luận điểm này. Việc mô phỏng crash cần dùng lab cách ly và biết rõ cách tắt/mất nguồn, cơ chế lưu trữ, backup cũng như dữ liệu có thể mất.

### Một câu hỏi thường gặp: có cần UPDATE ghi dữ liệu trước COMMIT không?

`UPDATE` thường ghi thay đổi vào các trang trong bộ nhớ và phát sinh WAL; điều kiện ghi xuống file dữ liệu hay WAL xuống bộ lưu trữ phụ thuộc nhiều tiến trình và trạng thái buffer. Người học không nên đồng nhất ba sự kiện:

1. PostgreSQL đã **xử lý logic UPDATE** trong transaction.
2. WAL record đã **được ghi hoặc flush**.
3. Trang dữ liệu đã **được ghi xuống data file**.

Ba sự kiện này không xảy ra cùng một thời điểm bắt buộc. WAL cho phép tách việc xác nhận giao dịch khỏi việc phải ghi tất cả trang dữ liệu ngay lập tức.

## 4. WAL segment, pg_wal và WAL sequence number (LSN)

Các WAL record được sắp theo thứ tự logic trong một dòng WAL liên tục. PostgreSQL lưu dòng này trong những **WAL segment files** dưới thư mục `pg_wal` của data directory.

Một segment thường có kích thước **16 MiB** với cách khởi tạo mặc định, nhưng kích thước WAL segment có thể được chọn khi khởi tạo database cluster bằng cách phù hợp với phiên bản PostgreSQL. Vì vậy không nên coi 16 MiB là hằng số cho mọi hệ thống.

### 4.1. LSN là gì?

**Log Sequence Number (LSN)** biểu diễn một vị trí logic trong luồng WAL. Nó thường được in theo dạng:

```text
0/16B6C50
0/16B6D20
```

Giá trị sau nằm về phía sau giá trị trước trong dòng WAL. LSN không phải timestamp và không phải ID giao dịch của ứng dụng.

Ứng dụng của LSN:

- Xác định vị trí ghi/flush WAL.
- Đánh giá mức độ tiến triển của replication hoặc recovery.
- So sánh vị trí đã nhận và đã replay trên standby.
- Liên hệ trạng thái checkpoint với điểm bắt đầu cần redo.

Trong một primary đang hoạt động, có thể xem:

```sql
SELECT pg_current_wal_lsn() AS current_wal_lsn;
```

Một số hàm chẩn đoán cần quyền thích hợp, và các hàm `pg_current_wal_*` được thiết kế cho ngữ cảnh server đang hoạt động như primary; trên standby cần dùng các hàm nhận/replay WAL tương ứng.

Ví dụ xem khoảng cách byte giữa hai LSN minh họa:

```sql
SELECT pg_wal_lsn_diff('0/16B6D20'::pg_lsn, '0/16B6C50'::pg_lsn)
       AS wal_bytes_between;
```

Hàm `pg_wal_lsn_diff` trả chênh lệch vị trí WAL theo byte. Nếu đo tốc độ sinh WAL, có thể lấy hai mẫu LSN cách nhau một khoảng thời gian rồi tính chênh lệch, nhưng kết quả là **lượng WAL phát sinh**, không phải lượng dữ liệu nghiệp vụ thay đổi hay dung lượng bảng.

### 4.2. LSN, timeline và vị trí vật lý

Khi theo dõi phục hồi hoặc failover, có thể gặp thêm **timeline ID**. Timeline mô tả một nhánh lịch sử WAL sau những sự kiện như phục hồi và promotion. Hai chuỗi WAL trên những timeline khác nhau không được so sánh một cách ngây thơ chỉ dựa trên việc LSN có số lớn hơn.

Tên WAL segment bao gồm thông tin liên quan timeline và vị trí segment. Không nên dựa vào tên file theo chuỗi ký tự để kết luận lịch sử giao dịch đã được giữ đủ, nhất là sau PITR hoặc promotion.

### 4.3. Vì sao không được tự xóa tệp trong pg_wal?

Thư mục `pg_wal` do PostgreSQL quản lý. Các segment có thể đang cần cho:

- Crash recovery và mốc checkpoint.
- Streaming replication cho standby.
- Replication slots chưa được tiêu thụ.
- WAL archiving.
- Các tác vụ backup hoặc khôi phục đang diễn ra.

Xóa file WAL bằng lệnh hệ điều hành để “giải phóng dung lượng” có thể khiến server không phục hồi được hoặc khiến replica không bắt kịp. Giải quyết vấn đề dung lượng phải dựa trên nguyên nhân giữ WAL và phương án quản trị chính thức, không xóa tùy tiện file bên trong `pg_wal`.

## 5. Checkpoint là gì và giải quyết vấn đề nào?

Giả sử PostgreSQL đã chạy liên tục nhiều ngày, tích lũy một lượng lớn WAL trong khi các trang dữ liệu được ghi dần xuống đĩa. Nếu không có mốc phục hồi, khi crash PostgreSQL có thể phải xem một đoạn lịch sử rất dài để xác định những thay đổi nào cần redo.

**Checkpoint** tạo một mốc đảm bảo rằng các trang dữ liệu bẩn thuộc phạm vi cần thiết đã được đồng bộ theo quy tắc checkpoint, và thông tin checkpoint được ghi nhận vào WAL/trạng thái điều khiển cluster. Khi khởi động lại sau sự cố, PostgreSQL có thể dùng checkpoint gần nhất phù hợp để chọn điểm bắt đầu redo thay vì quét lại toàn bộ lịch sử từ khi tạo database.

```text
WAL theo thời gian

--------- [checkpoint A] ---------- [checkpoint B] -------- crash
                      |                         |
                      |                         +-- chọn mốc phục hồi phù hợp
                      +-- phần WAL cũ có thể không còn cần
                          cho crash recovery, nếu không
                          bị yêu cầu khác giữ lại

Phục hồi thường redo từ vị trí do checkpoint xác định
đến cuối phần WAL hợp lệ cần áp dụng.
```

Checkpoint không xóa dữ liệu hoặc commit mọi transaction của ứng dụng. Nó phục vụ **độ bền và khả năng phục hồi của các trang**, không phải thay thế `COMMIT`.

### 5.1. Checkpoint làm những công việc gì?

Ở mức khái niệm:

1. Checkpointer xác định các trang dirty cần được bảo đảm ghi theo checkpoint.
2. PostgreSQL điều phối việc ghi các trang dữ liệu tương ứng ra hệ lưu trữ.
3. Những thao tác đồng bộ file và WAL cần thiết được thực hiện để bảo đảm mốc có thể dùng cho phục hồi.
4. Thông tin checkpoint được lưu để lần khởi động sau biết trạng thái nào đã được xác nhận là ổn định.
5. Những WAL segment cũ không còn được yêu cầu có thể được tái sử dụng hoặc loại bỏ theo chính sách và các điều kiện giữ WAL khác.

Từ “có thể” ở bước 5 rất quan trọng: **checkpoint không có nghĩa PostgreSQL lập tức xóa tất cả WAL trước nó**. Backup, archiving, replication, slots và mục tiêu giữ lại WAL có thể khiến những segment tiếp tục tồn tại.

### 5.2. Có thể INSERT trong khi checkpoint chạy không?

Có. PostgreSQL cho phép các backend tiếp tục phục vụ giao dịch khi checkpoint đang xử lý, theo cơ chế phối hợp bộ nhớ, WAL và ghi trang. Checkpoint không đồng nghĩa một “nút pause” buộc mọi transaction đứng yên cho đến khi toàn bộ dữ liệu được ghi.

Mặt khác, checkpoint tiêu thụ tài nguyên I/O; nếu cấu hình không phù hợp với tốc độ sinh WAL và thiết bị lưu trữ, nó có thể gây biến động latency. Đây là lý do checkpoint cần được điều phối và theo dõi, không phải thực hiện liên tục.

## 6. Checkpoint và COMMIT khác nhau như thế nào?

| Tiêu chí | `COMMIT` | Checkpoint |
| --- | --- | --- |
| Thuộc phạm vi | Một transaction hoặc nhóm giao dịch cần xác nhận | Toàn bộ tiến độ ghi trang và mốc phục hồi của database cluster |
| Ai yêu cầu | Ứng dụng/backend hoặc thành phần thực thi transaction | Checkpointer theo lịch/ngưỡng WAL hoặc yêu cầu quản trị |
| Mục tiêu | Kết thúc transaction và xác nhận các thay đổi theo độ bền cấu hình | Tạo mốc phục hồi và đồng bộ trang dirty theo quy tắc checkpoint |
| Có buộc ghi mọi trang của transaction ngay lúc đó? | Không | Đồng bộ các trang thuộc mốc checkpoint theo cơ chế điều phối |
| Có làm transaction của client được commit? | Có, nếu thành công | Không tự commit transaction đang mở |
| Hậu quả với crash recovery | WAL commit bền vững giúp nhận diện giao dịch đã xác nhận | Giới hạn phạm vi WAL cần redo |

Ví dụ:

```sql
BEGIN;
UPDATE wal_lab.account_balances
SET balance = balance + 10
WHERE account_id = 101;

-- Một checkpoint có thể diễn ra trong khi transaction vẫn đang mở.
ROLLBACK;
```

Checkpoint không biến `UPDATE` chưa commit thành giao dịch đã commit. PostgreSQL vẫn thực thi ngữ nghĩa transaction/MVCC. Các trang có thể đã chứa dữ liệu về mặt vật lý nhưng những phiên bản bản ghi chưa được commit không được xem là kết quả hợp lệ của transaction đã rollback.

### Nếu checkpoint xảy ra trước COMMIT?

WAL và checkpoint đảm bảo tính đúng đắn ở tầng phục hồi, nhưng **trạng thái giao dịch** vẫn do cơ chế transaction xác định. Không có quy tắc “trang dữ liệu đã xuống đĩa thì transaction tự động thành công”. PostgreSQL quản lý trạng thái commit/abort và khả năng nhìn thấy của các tuple theo MVCC, độc lập với suy luận đơn giản về vị trí file chứa tuple.

## 7. PostgreSQL quyết định khi nào chạy checkpoint?

Checkpoint có thể được yêu cầu bởi nhiều điều kiện. Những thông số thường cần biết:

| Thông số | Ý nghĩa tổng quát |
| --- | --- |
| `checkpoint_timeout` | Khoảng thời gian tối đa giữa các checkpoint tự động theo lịch trong trạng thái bình thường. |
| `max_wal_size` | Mục tiêu quy mô WAL; khi lượng WAL tăng, PostgreSQL có thể yêu cầu checkpoint dựa trên ngưỡng WAL. |
| `min_wal_size` | Mục tiêu giữ lại một lượng WAL để tái sử dụng, hạn chế tạo/xóa segment quá thường xuyên khi phù hợp. |
| `checkpoint_completion_target` | Mức phân bổ công việc ghi của checkpoint trong khoảng thời gian dự kiến giữa các checkpoint. |
| `checkpoint_warning` | Phục vụ cảnh báo khi các checkpoint do WAL bị yêu cầu quá gần nhau theo ngưỡng cấu hình. |

Kiểm tra giá trị hiện hành:

```sql
SHOW checkpoint_timeout;
SHOW checkpoint_completion_target;
SHOW min_wal_size;
SHOW max_wal_size;
SHOW checkpoint_warning;
```

Hoặc xem nguồn và đơn vị:

```sql
SELECT
    name, setting, unit, source, context, pending_restart
FROM pg_settings
WHERE name IN (
    'checkpoint_timeout',
    'checkpoint_completion_target',
    'min_wal_size',
    'max_wal_size',
    'checkpoint_warning'
)
ORDER BY name;
```

### 7.1. max_wal_size không phải giới hạn tuyệt đối

Người học dễ hiểu nhầm rằng `max_wal_size = '2GB'` nghĩa là thư mục `pg_wal` **không bao giờ** vượt 2 GB. Trên thực tế, đây là một **ngưỡng mục tiêu dùng cho hành vi checkpoint và quản lý WAL**, không phải hard quota của thư mục.

Trong nhiều tình huống, WAL vẫn có thể chiếm nhiều dung lượng hơn:

- Có lượng WAL phát sinh đột biến.
- Quá trình checkpoint/ghi hoặc archive bị chậm.
- Replication slot giữ WAL chưa được consumer nhận.
- Standby hoặc một tiến trình backup cần các WAL segment cũ.
- Cấu hình `wal_keep_size` hoặc yêu cầu duy trì WAL khác.

Do đó, gặp `pg_wal` tăng liên tục thì **không được chỉ giảm `max_wal_size` một cách mù quáng**. Cần kiểm tra nguyên nhân tích lũy WAL.

### 7.2. checkpoint_completion_target và độ mượt I/O

Checkpoint ghi nhiều dirty page. Nếu cố gắng hoàn tất tất cả quá nhanh, hệ thống có thể có “đỉnh” I/O và làm truy vấn chậm bất thường. Thông số `checkpoint_completion_target` giúp PostgreSQL trải công việc ghi checkpoint trên một phần khoảng thời gian checkpoint dự kiến.

Đặt mục tiêu phù hợp giúp giảm đỉnh I/O, nhưng không loại bỏ chi phí vật lý của việc ghi dữ liệu. Khi lượng ghi quá lớn hoặc ổ đĩa không đủ khả năng, vẫn có thể xuất hiện checkpoint kéo dài, backend phải tự ghi trang hoặc latency tăng.

Đừng thay đổi đồng thời nhiều tham số chỉ vì một truy vấn chậm. Hãy đo lượng WAL, tốc độ ghi trang, thời gian checkpoint và latency ứng dụng trước/sau trong môi trường kiểm soát.

## 8. Crash recovery diễn ra như thế nào?

**Crash recovery** là quá trình PostgreSQL khôi phục trạng thái database sau khi tiến trình hoặc máy chủ kết thúc bất thường. Ví dụ: mất điện, kernel crash, máy chủ bị tắt không sạch hoặc tiến trình server lỗi nghiêm trọng.

Về mặt tổng quát:

1. PostgreSQL phát hiện dữ liệu không ở trạng thái shutdown sạch.
2. Engine đọc trạng thái điều khiển database cluster và thông tin checkpoint thích hợp.
3. Nó xác định **điểm bắt đầu redo** gắn với checkpoint đó.
4. Hệ thống đọc và áp dụng các WAL record hợp lệ cần thiết, theo đúng thứ tự và quy tắc replay.
5. Trạng thái transaction/MVCC được khôi phục để giao dịch đã commit được nhìn thấy đúng, còn giao dịch dở dang không được coi là đã commit.
6. Khi hoàn tất các bước phục hồi cần thiết, máy chủ sẵn sàng nhận kết nối theo vai trò và cấu hình hiện tại.

```text
Trước crash:

                 checkpoint
                     |
WAL  ---- A ---- B ---- C ---- D ---- E ---- crash
                     |                 |
                     |                 +-- WAL hợp lệ cuối cùng
                     +-- cơ sở xác định redo start

Data files:
    chứa những trang đã flush ở nhiều thời điểm khác nhau
    có thể chưa chứa mọi thay đổi đã commit gần đây

Khi khởi động lại:
    đọc checkpoint / redo location
            |
            v
    replay WAL cần thiết
            |
            v
    xác định trạng thái giao dịch đúng
            |
            v
    database ready
```

Không nên hiểu rằng PostgreSQL lấy toàn bộ database cũ rồi thay bằng một bản sao “đã lưu ở checkpoint”. Checkpoint **không tạo một snapshot backup độc lập**; recovery dựa vào các file dữ liệu hiện có cùng WAL còn cần thiết.

### 8.1. Redo và transaction chưa commit

Một ý rất quan trọng: WAL replay ở tầng vật lý có thể tái thực hiện những thay đổi trang được sinh bởi một transaction **chưa commit** tại thời điểm crash. Điều đó **không** có nghĩa transaction ấy được xem là thành công.

PostgreSQL dùng cơ chế **MVCC và trạng thái giao dịch** để xác định tuple nào có thể nhìn thấy. Những phiên bản dữ liệu thuộc giao dịch chưa commit không trở thành dữ liệu hợp lệ chỉ vì WAL chứa record liên quan; chúng có thể được dọn dẹp về sau bởi VACUUM và cơ chế quản lý lưu trữ.

Vì vậy, tránh diễn đạt crash recovery theo cách quá đơn giản “chỉ replay mọi record của transaction đã commit, bỏ qua toàn bộ record của transaction chưa commit”. Thực tế WAL redo và khả năng nhìn thấy của transaction là hai lớp phối hợp với nhau.

### 8.2. Crash recovery có cần ứng dụng chạy ROLLBACK không?

Không. Sau một crash, session và transaction đang mở không còn tồn tại theo nghĩa có thể tiếp tục gửi `ROLLBACK` từ kết nối cũ. PostgreSQL tự khôi phục trạng thái giao dịch để các thay đổi chưa commit không được công nhận là dữ liệu đã commit.

Từ phía ứng dụng:

- Giao dịch đang mở khi mất kết nối không thể được tiếp tục trên kết nối mới.
- Giao dịch đã được xác nhận commit thành công trước crash, trong điều kiện độ bền phù hợp, được kỳ vọng tồn tại sau recovery.
- Giao dịch mà client **không biết COMMIT đã thành công hay chưa** cần được xác minh bằng định danh nghiệp vụ hoặc cơ chế idempotency, không retry một thao tác có thể gây trùng dữ liệu một cách mù quáng.

## 9. Phân biệt shutdown sạch với crash

PostgreSQL có các kiểu tắt máy chủ với hậu quả khác nhau. Khi dừng có kiểm soát, server có thể xử lý các kết nối, transaction, buffer và trạng thái lưu trữ theo cơ chế shutdown. Khi bị kết thúc đột ngột, lần khởi động sau có thể cần WAL redo.

Ví dụ những lựa chọn shutdown của công cụ `pg_ctl`:

| Chế độ | Ý nghĩa vận hành |
| --- | --- |
| `smart` | Chờ các client hiện có ngắt kết nối rồi dừng; có thể chờ lâu nếu có kết nối giữ liên tục. |
| `fast` | Dừng có kiểm soát, ngắt kết nối, rollback các transaction đang hoạt động rồi shutdown. |
| `immediate` | Dừng đột ngột, không thực hiện shutdown sạch; lần khởi động tiếp theo cần crash recovery. |

Trên môi trường lab có data directory phù hợp:

```bash
# Chỉ minh họa cú pháp; không chạy lên production khi chưa có runbook.
pg_ctl -D /path/to/pgdata stop -m fast
```

`immediate` không phải cách dừng thường ngày để “nhanh hơn”; nó chủ động tạo tình huống đòi hỏi recovery ở lần chạy tiếp. Ngoài ra, nhiều môi trường quản lý PostgreSQL qua systemd, Kubernetes operator hoặc dịch vụ cloud, nên phải dùng quy trình của chính môi trường đó.

### Dấu hiệu trong nhật ký khởi động

Sau shutdown sạch, log có thể chứa thông tin database đã shutdown bình thường. Sau crash, thường thấy những thông báo liên quan recovery, ví dụ:

```text
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  redo starts at ...
LOG:  redo done at ...
LOG:  checkpoint starting: end-of-recovery immediate wait
LOG:  database system is ready to accept connections
```

Đây là **mẫu minh họa**, không phải chuỗi chắc chắn xuất hiện nguyên văn ở mọi phiên bản và mọi sự cố. Trong tình huống recovery, log có thể hiển thị thêm vị trí WAL, thời gian xử lý, timeline, checkpoint và lỗi khi thiếu WAL.

Nếu PostgreSQL báo thiếu WAL record/segment cần thiết hoặc không thể đọc tệp dữ liệu, không nên tự xóa file WAL hoặc thay đổi trạng thái recovery để ép server chạy. Cần bảo toàn hiện trạng, đối chiếu backup và quy trình phục hồi được phê duyệt.

## 10. full_page_writes và ảnh trang trong WAL

Một tình huống khó xảy ra khi hệ thống ghi một data page (thường 8 KiB với PostgreSQL cấu hình mặc định) xuống bộ lưu trữ nhưng bị mất điện giữa chừng. Tùy thiết bị và tầng lưu trữ, trang có thể rơi vào trạng thái **ghi dở** (*torn page*).

Thông số `full_page_writes` giúp giảm nguy cơ mất khả năng phục hồi từ tình huống này. Khi bật (giá trị mặc định thông thường), PostgreSQL ghi một **full-page image** của trang khi trang được sửa lần đầu sau checkpoint trong các trường hợp phù hợp. Khi replay WAL, ảnh trang có thể cung cấp cơ sở đáng tin cậy để khôi phục trang ngay cả khi bản ghi trên data file bị ghi dở.

```text
Sau checkpoint:

Lần đầu một data page được sửa
            |
            v
     WAL có thể chứa full-page image
            |
            v
     Các thay đổi tiếp theo trên trang
     tiếp tục tạo WAL theo cơ chế thích hợp

Khi crash và data page bị ghi dở:
     WAL redo + full-page image giúp khôi phục trang
```

Kiểm tra:

```sql
SHOW full_page_writes;
```

### Đánh đổi về dung lượng WAL

Full-page images có thể làm lượng WAL tăng, đặc biệt ngay sau checkpoint khi nhiều trang được sửa lần đầu. Vì vậy, **checkpoint quá thường xuyên có thể làm tăng lượng WAL do full-page writes**, ngoài chi phí flush các trang dữ liệu.

Điều này kết nối ba vấn đề:

1. Checkpoint tạo mốc redo.
2. Sau checkpoint, lần sửa đầu tiên trên nhiều trang có thể sinh full-page image.
3. Nhiều checkpoint quá sát nhau có thể tăng I/O và lượng WAL.

Đừng tắt `full_page_writes` đơn giản để giảm dung lượng WAL nếu chưa đánh giá điều kiện lưu trữ và rủi ro mất dữ liệu. Đây là cấu hình ảnh hưởng tới khả năng phục hồi trong một số loại lỗi vật lý.

### wal_compression

PostgreSQL có thông số `wal_compression` cho phép nén một số full-page images trong WAL bằng những thuật toán được phiên bản hỗ trợ. Nén có thể giảm lưu lượng WAL nhưng đổi lại có thêm chi phí CPU; hiệu quả phụ thuộc nội dung trang và workload.

```sql
SHOW wal_compression;
```

Không coi nén WAL là sự thay thế cho `full_page_writes` hoặc backup; đó là các tính năng giải quyết những mục đích khác nhau.

## 11. synchronous_commit, fsync và cam kết độ bền

Một nhầm lẫn phổ biến là nghĩ rằng “WAL tồn tại” nghĩa là **mọi câu COMMIT đều được flush bền vững trên ổ đĩa trước khi client nhận phản hồi**, không phụ thuộc cấu hình.

Trên thực tế, độ bền phụ thuộc vào các lựa chọn như:

- `synchronous_commit`: mức độ chờ WAL được flush ở local và trong những trường hợp có cấu hình synchronous replication, điều kiện xác nhận từ standby.
- `fsync`: cơ chế yêu cầu hệ điều hành đồng bộ dữ liệu xuống bộ lưu trữ bền vững.
- `full_page_writes`: bảo vệ khỏi một số trường hợp data page bị ghi dở.
- Chất lượng của thiết bị lưu trữ, hệ điều hành, controller, cache và mức độ trung thực khi xác nhận flush.

Kiểm tra:

```sql
SHOW synchronous_commit;
SHOW fsync;
SHOW full_page_writes;
```

### 11.1. synchronous_commit = on

Với `synchronous_commit = on` trong cấu hình **không yêu cầu standby đồng bộ**, PostgreSQL chờ WAL commit được flush cục bộ ở mức cần thiết trước khi xác nhận commit với client.

Nếu hệ thống có cấu hình synchronous replication, ý nghĩa của mức `on` còn bao gồm quy tắc chờ standby tương ứng, tùy `synchronous_standby_names` và cấu hình thực tế. Vì vậy, đừng dùng mỗi giá trị `on` để suy ra hệ thống có replica đồng bộ hay không.

### 11.2. synchronous_commit = off

Khi `synchronous_commit = off`, PostgreSQL có thể phản hồi commit trước khi WAL commit đó được flush xuống bộ lưu trữ bền vững. Cách này có thể giảm độ trễ ở một số workload, nhưng **một lượng giao dịch đã báo thành công gần thời điểm crash có nguy cơ bị mất**.

Điều này không phải “PostgreSQL chắc chắn sẽ hỏng database khi tắt `synchronous_commit`”. Rủi ro chính là **mất những giao dịch đã được xác nhận nhưng WAL chưa kịp bền vững**. Khả năng chấp nhận đánh đổi đó phải xuất phát từ yêu cầu nghiệp vụ, không chỉ từ mục tiêu tăng tốc benchmark.

### 11.3. fsync = off là rủi ro nghiêm trọng hơn

Nếu tắt `fsync`, PostgreSQL không thực hiện các yêu cầu đồng bộ bền vững theo cơ chế thông thường; khi hệ thống bị crash hoặc mất nguồn, có nguy cơ **hư hỏng dữ liệu** ngoài việc mất một số transaction gần nhất. Không nên tắt `fsync` trên hệ thống cần bảo toàn dữ liệu chỉ để tăng tốc ghi.

### 11.4. Các mức đồng bộ liên quan standby

PostgreSQL có những giá trị như `remote_write` hoặc `remote_apply` trong ngữ cảnh synchronous replication. Chúng liên quan tới việc standby đã ghi WAL hoặc áp dụng thay đổi đến đâu trước khi primary xác nhận giao dịch. Chúng **không thay thế** việc hiểu ranh giới WAL flush local, độ trễ mạng, cấu hình standby và mô hình sự cố.

Kết luận: khi trao đổi RPO hoặc cam kết durability, cần nêu rõ **cấu hình thực tế và phạm vi sự cố** (backend crash, OS crash, mất điện, hỏng toàn bộ đĩa, mất site), thay vì chỉ nói “PostgreSQL có WAL nên RPO bằng 0 trong mọi tình huống”.

## 12. Theo dõi WAL và checkpoint bằng SQL

Nhiều thông tin giám sát có thể đọc từ các view và hàm hệ thống. Các ví dụ bên dưới dành cho PostgreSQL hiện đại, với lưu ý rằng một số view thống kê checkpoint có thể được tái tổ chức theo major.

### 12.1. Thống kê WAL

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

Các cột tiêu biểu:

| Cột | Diễn giải |
| --- | --- |
| `wal_records` | Số WAL records được tạo kể từ khi reset thống kê. |
| `wal_fpi` | Số full-page images được ghi vào WAL theo thống kê. |
| `wal_bytes` | Lượng byte WAL được tạo theo bộ đếm thống kê. |
| `wal_buffers_full` | Số lần WAL buffers hết chỗ theo chỉ số được ghi nhận. |
| `stats_reset` | Thời điểm bộ thống kê được reset. |

Các giá trị thường là **tích lũy**, không phải “byte WAL mỗi giây”. Muốn tính tốc độ, cần lấy mẫu hai thời điểm, tính chênh lệch rồi chia khoảng thời gian; đồng thời kiểm tra `stats_reset` để tránh nhầm khi bộ đếm đã reset.

Ví dụ dùng LSN để đo khoảng cách giữa hai lần lấy mẫu ở cấp vận hành:

```sql
SELECT pg_current_wal_lsn();
```

Ghi lại LSN lần một và lần hai sau một khoảng cố định, rồi tính:

```sql
SELECT pg_wal_lsn_diff(
    '0/2000000'::pg_lsn,
    '0/1A00000'::pg_lsn
) AS wal_bytes_generated;
```

Các LSN trong đoạn này **chỉ minh họa phép tính**. Ứng dụng giám sát phải thay bằng số đo thật, không dùng ví dụ như dữ liệu từ một máy cụ thể.

### 12.2. Thống kê checkpoint theo major

Trong PostgreSQL ở các major cũ, thống kê checkpoint từng được cung cấp ở `pg_stat_bgwriter`. Ở các major mới, đặc biệt từ PostgreSQL 17, các chỉ số checkpoint được tách sang `pg_stat_checkpointer`.

Do đó không nên sao chép một câu `SELECT checkpoints_timed, checkpoints_req FROM pg_stat_bgwriter` từ tài liệu cũ rồi giả định nó hoạt động trên mọi phiên bản.

**Với server có `pg_stat_checkpointer`**, có thể xem:

```sql
SELECT *
FROM pg_stat_checkpointer;
```

**Với server dùng kiểu thống kê checkpoint cũ**, xem các cột hiện có trong:

```sql
SELECT *
FROM pg_stat_bgwriter;
```

Trong `psql`, có thể khám phá cột của view trên đúng phiên bản:

```text
\d+ pg_stat_checkpointer
\d+ pg_stat_bgwriter
```

Hoặc dùng metadata SQL:

```sql
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'pg_catalog'
  AND table_name IN ('pg_stat_checkpointer', 'pg_stat_bgwriter')
ORDER BY table_name, ordinal_position;
```

Những chỉ số thường cần quan sát gồm số checkpoint theo thời gian/ngưỡng WAL, thời gian ghi/sync và số buffer được ghi trong checkpoint. Tên cột và cách tổ chức **phụ thuộc major**, nên việc dùng đúng manual/version có ý nghĩa trực tiếp.

### 12.3. Log checkpoint

PostgreSQL hỗ trợ logging checkpoint thông qua `log_checkpoints`:

```sql
SHOW log_checkpoints;
```

Khi logging phù hợp, log có thể hiển thị lúc checkpoint bắt đầu, kết thúc, thời gian ghi/sync và thông tin số trang hoặc lượng WAL. Những dòng này giúp chẩn đoán checkpoint quá dày, I/O chậm hoặc khoảng cách giữa các checkpoint thấp hơn dự kiến.

Ví dụ mô phỏng:

```text
LOG:  checkpoint starting: time
LOG:  checkpoint complete: wrote ... buffers; ...
```

Đây là mẫu cấu trúc, không phải số liệu thực tế. Đặc biệt, cần so sánh timestamp checkpoint với đỉnh latency query và các sự kiện WAL/replication khác thay vì quy mọi chậm trễ cho checkpoint.

## 13. Vì sao WAL có thể tăng đầy đĩa?

WAL tăng nhanh chưa chắc là lỗi checkpoint. Một số nguyên nhân khác nhau có biểu hiện tương tự nhưng cách xử lý rất khác.

| Nguyên nhân | Dấu hiệu đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Workload ghi lớn hoặc nhiều full-page images | `pg_stat_wal` tăng mạnh, checkpoint dày, bulk load/update | Đo tốc độ WAL, đánh giá workload và cấu hình checkpoint. |
| Archiving không thành công | `pg_stat_archiver` có lỗi, log `archive_command` thất bại | Kiểm tra kho archive, quyền, lệnh sao lưu và băng thông. |
| Physical replication slot giữ WAL | Slot có `restart_lsn` cũ, standby ngắt lâu | Kiểm tra consumer/slot và chính sách giữ WAL; không xóa slot khi chưa hiểu hậu quả. |
| Logical replication slot không được tiêu thụ | Slot logical không tiến triển, WAL retention tăng | Kiểm tra subscriber/decoder và lag. |
| Cấu hình giữ WAL rộng | `wal_keep_size` hoặc điều kiện backup/replication giữ segment | Đánh giá mục tiêu RPO và khả năng catch-up của standby. |
| Checkpoint bị chậm, I/O không đủ | Log checkpoint kéo dài, nhiều dirty pages hoặc latency thiết bị cao | Đo I/O và khả năng lưu trữ, không chỉ giảm `max_wal_size`. |

Kiểm tra các slot nếu đủ quyền:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Với replication slot, `restart_lsn` liên quan tới vị trí WAL cũ nhất mà slot có thể còn yêu cầu giữ lại. Một slot lâu không được tiêu thụ có thể khiến `pg_wal` tiếp tục phình to, nhất là nếu không có cơ chế giới hạn phù hợp.

**Không tự xóa replication slot** chỉ để giảm dung lượng: slot có thể đang bảo vệ khả năng bắt kịp của standby hoặc subscriber. Nếu slot bị xóa khi consumer còn cần WAL cũ, consumer có thể phải dựng lại hoặc khôi phục bằng phương án khác.

### 13.1. pg_stat_archiver

Khi bật WAL archiving:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
```

Nó giúp xem archive đang tiến triển hay liên tục thất bại. Nhưng **chỉ nhìn một bộ đếm không đủ chứng minh kho archive có đầy đủ WAL phục vụ PITR**; còn phải kiểm tra tính liên tục, chính sách giữ, base backup và thử restore.

### 13.2. pg_wal không phải nơi chứa mọi WAL vĩnh viễn

Sau khi không còn cần cho crash recovery, replication hoặc các yêu cầu khác, WAL segment có thể được tái sử dụng/xóa theo quy tắc PostgreSQL. Nếu thiết kế backup cần giữ lịch sử lâu dài, phải cấu hình **WAL archiving sang kho riêng**, không dựa vào việc `pg_wal` còn chứa dữ liệu từ nhiều tháng trước.

## 14. WAL, replication và standby recovery

WAL là nền tảng của **physical streaming replication**. Primary tạo WAL; standby nhận luồng WAL và replay các record để tái hiện thay đổi vật lý theo thứ tự phù hợp.

```text
             PRIMARY
     SQL -> pages + WAL
                   |
                   v
              WAL stream
                   |
                   v
              STANDBY
          WAL receive / write
                   |
                   v
                WAL replay
                   |
                   v
              Data files
```

Standby không nhất thiết nhận hoặc replay ngay lập tức mọi WAL từ primary. Có thể có nhiều loại chênh lệch:

- **Send lag**: primary chưa gửi hết WAL cần thiết.
- **Receive/write lag**: standby chưa nhận/ghi hết WAL đã sinh.
- **Flush lag**: WAL trên standby chưa được flush đến cùng vị trí.
- **Replay lag**: standby đã có WAL nhưng chưa áp dụng hết vào dữ liệu.

Trên primary, khi có standby kết nối phù hợp:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
```

Trên standby, có thể quan sát:

```sql
SELECT
    pg_is_in_recovery() AS is_standby_recovery,
    pg_last_wal_receive_lsn() AS last_received_lsn,
    pg_last_wal_replay_lsn() AS last_replayed_lsn;
```

Nếu `pg_is_in_recovery() = true`, instance đang ở chế độ recovery/standby thích hợp; không nên nhầm nó với primary nhận ghi bình thường. Các giá trị LSN là một phần thông tin; lag tính theo thời gian và trạng thái mạng/apply cần được diễn giải cùng nhau.

### WAL và synchronous replication

Khi cấu hình đồng bộ, primary có thể đợi xác nhận từ một hoặc nhiều standby tùy `synchronous_standby_names` và mức `synchronous_commit`. Điều này thay đổi điều kiện xác nhận commit và khả năng chịu lỗi theo cấu hình; nó **không có nghĩa mọi standby đều có dữ liệu hoàn toàn giống nhau tại mọi thời điểm**.

Ví dụ nếu standby bị chậm hoặc mất kết nối, cấu hình đồng bộ có thể khiến giao dịch phải chờ. Đó là đánh đổi giữa độ bền trên nhiều nút, latency và tính sẵn sàng của đường ghi. Cần phân tích yêu cầu nghiệp vụ thay vì bật một chế độ chỉ vì tên gọi có từ “synchronous”.

## 15. Crash recovery khác gì PITR?

Hai khái niệm sử dụng WAL nhưng **không nhằm giải quyết cùng một sự cố**:

**Crash recovery**: PostgreSQL dùng những data files hiện tại và WAL còn cần thiết để khôi phục trạng thái nhất quán sau khi máy chủ kết thúc bất thường. Nó không cần người quản trị chọn một thời điểm lịch sử khác khi chỉ cần khởi động lại sau crash thông thường.

**Point-in-time recovery (PITR)**: người vận hành khôi phục **một base backup** rồi replay chuỗi WAL phù hợp tới một thời điểm hoặc mốc được chọn, ví dụ trước khi có lệnh xóa nhầm quan trọng. PITR cần có kế hoạch backup và archive WAL đầy đủ, cùng quy trình recovery rõ ràng.

```text
CRASH RECOVERY:
  data files hiện tại + WAL hiện có cần thiết
                |
                v
         trạng thái nhất quán sau crash

PITR:
  base backup tại T0
          |
          +--- WAL archive liên tục T0 -> T1 -> T2 -> T3
                                         |
                                         v
                             chọn recovery target T2
                                         |
                                         v
                               trạng thái ở T2
```

### 15.1. Vì sao không thể PITR chỉ với WAL?

WAL ghi thông tin thay đổi, không phải ảnh đầy đủ có thể dựng mọi tệp dữ liệu từ đầu trong một kịch bản thông thường. Để PITR, cần:

1. **Base backup hợp lệ** của database cluster.
2. **Chuỗi WAL liên tục đủ dùng** từ mốc backup tới mục tiêu khôi phục.
3. Cấu hình recovery để PostgreSQL tìm được WAL từ kho archive.
4. Kiểm chứng extension, tablespaces, cấu hình và yêu cầu khác của môi trường phục hồi.
5. Thử nghiệm restore thực tế để xác nhận khả năng khôi phục.

Khi đã mất toàn bộ data directory và không có base backup, việc còn vài segment WAL rời rạc thường **không đủ** để phục hồi database.

### 15.2. WAL archiving

Một ví dụ cấu hình khái niệm:

```conf
wal_level = replica
archive_mode = on
archive_command = '... sao chep WAL segment an toan den kho archive ...'
```

Giá trị `archive_command` trên là **placeholder để diễn giải**, không phải lệnh shell thực thi được. Triển khai thật phải dùng công cụ sao lưu và cơ chế copy/verify đủ an toàn, idempotent, có xử lý lỗi, bảo vệ dữ liệu và kiểm tra quyền truy cập.

Nếu archive thất bại liên tục, PostgreSQL có thể phải giữ WAL segment lâu hơn dự kiến, khiến `pg_wal` tăng dung lượng. Đừng vô hiệu hóa archiving hoặc xóa WAL mà chưa hiểu yêu cầu phục hồi lịch sử.

### 15.3. Recovery target, timeline và promotion

Với các major PostgreSQL hiện đại, cấu hình archive recovery dùng những thông số như `restore_command`, các `recovery_target_*` phù hợp và các tín hiệu `recovery.signal` hoặc `standby.signal`, tùy mục đích. Những phiên bản cũ dùng cơ chế `recovery.conf`; không nên sao chép hướng dẫn cũ cho server mới.

Khi phục hồi tới một thời điểm quá khứ và mở lại database để ghi, có thể hình thành timeline mới. Vì vậy backup tooling cần quản lý **timeline history** và không được chỉ giả định “segment WAL có cùng vị trí LSN là cùng một lịch sử dữ liệu”.

## 16. UNLOGGED và TEMPORARY: ngoại lệ về độ bền

Theo mặc định, bảng PostgreSQL thông thường là **logged table** và các thay đổi cần thiết được ghi vào WAL theo cơ chế engine. Nhưng PostgreSQL có những loại bảng mà không thể áp dụng máy móc cùng một kết luận về crash recovery.

### 16.1. UNLOGGED table

```sql
CREATE UNLOGGED TABLE wal_lab.import_staging (
    batch_id bigint NOT NULL,
    item_code text NOT NULL,
    raw_payload jsonb NOT NULL
);
```

Bảng `UNLOGGED` có thể hữu ích cho dữ liệu trung gian có thể tạo lại vì dữ liệu của nó không được WAL bảo vệ theo cách của bảng logged. Hệ quả quan trọng:

- Nội dung bảng unlogged **không crash-safe** theo nghĩa thông thường của bảng logged.
- Sau crash hoặc shutdown không sạch, dữ liệu của bảng unlogged có thể bị **truncate** khi PostgreSQL khôi phục.
- Dữ liệu bảng unlogged **không được streaming replicate** sang standby theo cách dữ liệu bảng logged được WAL replay.

Vì vậy, không dùng `UNLOGGED` cho sổ cái, đơn hàng đã thanh toán hoặc dữ liệu duy nhất không thể tái tạo chỉ để tăng tốc ghi.

### 16.2. TEMPORARY table

```sql
CREATE TEMP TABLE temp_daily_totals (
    report_date date,
    total numeric(14, 2)
) ON COMMIT DROP;
```

Bảng tạm có vòng đời gắn với session hoặc transaction theo cách định nghĩa. Với `ON COMMIT DROP`, bảng sẽ bị loại bỏ khi transaction chứa thao tác tạo bảng commit theo quy tắc áp dụng. Dữ liệu của bảng tạm không được xem là dữ liệu nghiệp vụ cần sống sót qua việc mất session hay crash.

**Phân biệt ba đối tượng:**

| Loại bảng | Mục đích điển hình | Độ bền sau crash |
| --- | --- | --- |
| Logged table | Dữ liệu nghiệp vụ lâu dài | Được cơ chế WAL và recovery bảo vệ theo cấu hình độ bền. |
| Unlogged table | Dữ liệu staging/cache có thể tạo lại | Có thể mất nội dung sau crash; không dùng cho dữ liệu không thể tái tạo. |
| Temporary table | Dữ liệu tạm của phiên xử lý | Không sống như dữ liệu lâu dài sau khi session/transaction kết thúc theo quy tắc của nó. |

Việc tạo một bảng `UNLOGGED` không vô hiệu hóa WAL cho toàn database. Các bảng logged khác và metadata vẫn có những quy tắc WAL riêng; không nên suy luận “cả database từ đây không cần WAL”.

## 17. Tình huống thực tế: checkpoint quá thường xuyên

Giả sử máy chủ OLTP có log như sau:

```text
LOG:  checkpoints are occurring too frequently ...
HINT: Consider increasing the configuration parameter "max_wal_size".
```

Thông điệp này thường gợi ý tốc độ tạo WAL khiến checkpoint do ngưỡng WAL xảy ra quá sát nhau, nhưng cần đo trước khi thay đổi.

Quy trình phân tích:

1. Kiểm tra `checkpoint_timeout`, `max_wal_size` và `checkpoint_completion_target` hiện hành.
2. Đọc số checkpoint theo thời gian và theo yêu cầu trên view phù hợp **với major đang chạy**.
3. Xem lượng WAL tạo ra qua `pg_stat_wal` và dấu hiệu full-page images.
4. Đối chiếu log checkpoint với latency đĩa và đỉnh ghi ứng dụng.
5. Cân nhắc điều chỉnh mục tiêu WAL/checkpoint trong giới hạn dung lượng và SLA, sau đó đo lại.

Một điểm đánh đổi:

- Checkpoint thưa hơn có thể giảm tần suất flush nặng và giảm lượng WAL do full-page images trong một số workload.
- Nhưng WAL giữa các checkpoint có thể nhiều hơn, làm tăng lượng redo có thể phải đọc khi crash recovery.
- Checkpoint vẫn cần đáp ứng mục tiêu thời gian phục hồi và năng lực I/O.

Không có một giá trị `max_wal_size` đúng cho mọi hệ thống. Cấu hình phụ thuộc tốc độ sinh WAL, RAM, storage throughput, mục tiêu recovery time và yêu cầu replica/backup.

## 18. Tình huống thực tế: pg_wal tăng nhưng checkpoint vẫn chạy

Giả sử thư mục `pg_wal` tăng liên tục, trong khi log cho thấy checkpoint chạy đều đặn. Nguyên nhân có thể là một **replication slot giữ WAL cũ** hoặc **archiving thất bại**, không phải checkpoint hỏng.

Kiểm tra:

```sql
SELECT slot_name, slot_type, active, restart_lsn
FROM pg_replication_slots;

SELECT
    archived_count,
    last_archived_time,
    failed_count,
    last_failed_time
FROM pg_stat_archiver;
```

Sau đó đối chiếu:

- Replication slot nào không còn consumer nhưng vẫn giữ `restart_lsn` quá cũ?
- Standby có đang ngừng hoạt động hoặc không bắt kịp không?
- Archive command có trả lỗi và kho lưu trữ có hết chỗ không?
- `wal_keep_size` hoặc một công cụ backup có đang yêu cầu giữ WAL không?

Về nguyên tắc, checkpoint có thể làm **một phần** WAL cũ không còn cần cho crash recovery, nhưng segment đó vẫn có thể phải tồn tại cho các mục đích khác. Đây là lý do không thể giải thích dung lượng `pg_wal` chỉ bằng checkpoint.

### Điều không nên làm

Không:

```bash
# TUYET DOI KHONG CHAY: minh hoa thao tac nguy hiem.
rm -f /path/to/pgdata/pg_wal/*
```

Lệnh trên có thể phá hỏng khả năng recovery và replication. Trong một sự cố hết dung lượng, cần ưu tiên đánh giá tình trạng WAL/backup/replication và mở rộng dung lượng hoặc xử lý nguyên nhân giữ WAL bằng công cụ/quy trình phù hợp.

## 19. Tình huống thực tế: mất kết nối ngay tại COMMIT

Xét quy trình ứng dụng tạo đơn hàng:

```sql
BEGIN;

INSERT INTO orders (
    request_key, order_id, customer_id, amount
) VALUES (
    'checkout-2026-00017', 50017, 101, 250000
);

COMMIT;
```

Giả sử client gửi `COMMIT` rồi bị ngắt kết nối trước khi nhận phản hồi. Có hai khả năng:

- Giao dịch **đã commit**, nhưng phản hồi không tới ứng dụng.
- Giao dịch **chưa được commit thành công**, ví dụ kết nối bị lỗi trước thời điểm xác nhận giao dịch.

WAL và crash recovery giải quyết việc database tự khôi phục trạng thái đúng theo các record hợp lệ và cấu hình bền vững, nhưng **không tự nói cho client biết câu yêu cầu đã có kết quả hay chưa** khi thông điệp phản hồi bị mất.

Vì vậy, ứng dụng cần:

1. Một `request_key` bất biến cho cùng một yêu cầu nghiệp vụ.
2. Ràng buộc `UNIQUE` phù hợp với khóa idempotency.
3. Cơ chế kiểm tra kết quả sau khi reconnect.
4. Chính sách retry phân biệt lỗi tạm thời, lỗi ràng buộc trùng khóa và lỗi nghiệp vụ.

Trong tình huống tạo đơn, retry với `order_id` mới mà không có cơ chế idempotency có thể tạo đơn trùng, dù PostgreSQL đã phục hồi đúng sau crash.

> Đoạn `INSERT INTO orders` chỉ minh họa luồng nghiệp vụ; cần có bảng `orders` với các cột và ràng buộc thích hợp trong môi trường của bạn. Không dùng lệnh này trực tiếp trên bảng sản xuất khi chưa có cấu trúc tương ứng.

## 20. Câu hỏi “WAL đã flush nhưng data page chưa flush” và các hệ quả

Để kiểm tra đã hiểu, xét bốn tình huống:

**Tình huống A — WAL commit được flush, data page chưa flush, sau đó crash.**

Với các giả định độ bền chuẩn và storage hoạt động đúng, PostgreSQL có thể replay WAL cần thiết để phục hồi thay đổi đã commit. Đây là hành vi mà write-ahead logging được thiết kế để hỗ trợ.

**Tình huống B — Data page đã được ghi, transaction chưa COMMIT, sau đó crash.**

Trang vật lý có thể phản ánh một số thao tác, nhưng transaction chưa commit không trở thành giao dịch đã xác nhận. PostgreSQL xử lý visibility theo trạng thái transaction/MVCC và khôi phục trạng thái nhất quán.

**Tình huống C — Checkpoint vừa hoàn tất thì mất điện.**

Recovery có thể dùng thông tin checkpoint làm cơ sở xác định điểm redo; nhưng vẫn có thể cần replay WAL phát sinh **sau** mốc đó. Checkpoint không đóng băng database ở thời điểm nó hoàn tất.

**Tình huống D — Đã COMMIT với synchronous_commit=off rồi crash ngay.**

Có nguy cơ những giao dịch mới được xác nhận nhưng WAL chưa được flush bền vững bị mất. Không nên khẳng định cùng mức durability như cấu hình đồng bộ mặc định.

## 21. Các bài tập thực hành

Chỉ sử dụng môi trường PostgreSQL lab có quyền phù hợp. Các câu đọc thông số và thống kê dưới đây không làm thay đổi dữ liệu; những thao tác tắt/khởi động server hoặc chỉnh thông số phục hồi không thuộc nội dung thực hành bắt buộc.

### Bài 1. Quan sát các thông số WAL và checkpoint

```sql
SELECT name, setting, unit, context, source
FROM pg_settings
WHERE name IN (
    'wal_level',
    'synchronous_commit',
    'fsync',
    'full_page_writes',
    'wal_compression',
    'checkpoint_timeout',
    'max_wal_size',
    'min_wal_size',
    'checkpoint_completion_target'
)
ORDER BY name;
```

**Câu hỏi:** thông số nào tác động tới WAL durability, thông số nào tác động chủ yếu tới checkpoint, và thông số nào liên quan kích thước WAL?

**Gợi ý:** `synchronous_commit` và `fsync` liên quan tới mức xác nhận durability; `full_page_writes` hỗ trợ recovery khi có torn pages; `checkpoint_timeout` và `checkpoint_completion_target` liên quan lịch/phân bố checkpoint; `max_wal_size` và `min_wal_size` liên quan mục tiêu duy trì WAL.

### Bài 2. Đọc WAL statistics

```sql
SELECT wal_records, wal_fpi, wal_bytes, stats_reset
FROM pg_stat_wal;
```

**Yêu cầu:** ghi nhận các giá trị ở hai thời điểm cách nhau một khoảng đủ dài để có workload thực. Mô tả sự khác biệt giữa giá trị tích lũy và tốc độ WAL theo thời gian.

**Gợi ý:** chênh lệch `wal_bytes` là lượng WAL sinh ra giữa hai lần đọc nếu `stats_reset` không thay đổi. Chia cho số giây quan sát để ước lượng byte/s.

### Bài 3. Phân biệt checkpoint và commit

Giả sử ứng dụng:

```sql
BEGIN;
UPDATE wal_lab.account_balances
SET balance = balance + 50
WHERE account_id = 202;
ROLLBACK;
```

**Câu hỏi:** nếu hệ thống tình cờ thực hiện checkpoint trong khoảng transaction này, dữ liệu sau `ROLLBACK` có được coi là đã cộng 50 không?

**Đáp án:** Không. Checkpoint không tự commit một transaction. PostgreSQL tiếp tục áp dụng transaction semantics và MVCC.

### Bài 4. Kiểm tra replica replay

Trên một standby có quyền đọc thống kê:

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

**Câu hỏi:** nếu receive LSN tiến nhanh hơn replay LSN, có thể suy ra điều gì?

**Gợi ý:** standby đã nhận WAL đến vị trí mới hơn nhưng chưa áp dụng hết. Cần xem thêm replay lag, tài nguyên và trạng thái kết nối; một quan sát đơn lẻ không đủ để kết luận replication bị hỏng.

### Bài 5. Nhận diện nguyên nhân giữ WAL

Một server có `pg_wal` tăng liên tục, còn `pg_replication_slots` cho thấy một slot `active = false` và `restart_lsn` đã rất cũ.

**Câu hỏi:** điều đó gợi ý gì và nên làm gì trước tiên?

**Đáp án gợi ý:** slot có thể đang giữ WAL để consumer bắt kịp, gây tăng dung lượng. Trước khi xóa hoặc thay đổi slot, xác định consumer nào sở hữu nó, có còn cần dữ liệu không, và phương án phục hồi/khởi tạo lại nếu mất WAL cũ.

### Bài 6. Crash recovery hay PITR?

Phân loại:

1. Máy chủ bị mất điện, bật lại cùng data directory và PostgreSQL replay WAL tự động.
2. Nhân viên chạy `DROP TABLE` nhầm; quản trị viên muốn dựng trạng thái database trước câu lệnh đó từ base backup và WAL archive.
3. Primary gửi WAL cho standby để standby áp dụng những thay đổi mới.

**Đáp án:** (1) crash recovery; (2) PITR; (3) physical streaming replication. Cả ba có liên hệ WAL nhưng mục tiêu, dữ liệu nguồn và thao tác vận hành khác nhau.

### Bài 7. Bảng UNLOGGED có thích hợp lưu đơn hàng đã thanh toán?

```sql
CREATE UNLOGGED TABLE wal_lab.paid_orders_tmp (
    order_id bigint PRIMARY KEY,
    paid_amount numeric(14, 2) NOT NULL
);
```

**Câu hỏi:** có nên dùng bảng này như nguồn dữ liệu duy nhất của các giao dịch đã thanh toán?

**Đáp án:** Không. Dữ liệu bảng unlogged không được WAL bảo vệ để crash recovery như bảng logged và có thể bị truncate sau crash. Nó chỉ phù hợp khi mất dữ liệu có thể chấp nhận được hoặc dữ liệu có thể được tạo lại.

### Bài 8. Đọc thông số checkpoint từ phiên bản thật

Trong `psql`:

```text
\d+ pg_stat_bgwriter
\d+ pg_stat_checkpointer
```

**Yêu cầu:** trên server đang dùng, xác định view nào có thống kê checkpoint phù hợp. So sánh với manual đúng major. Nếu một view không tồn tại, đó không nhất thiết là server lỗi; cấu trúc thống kê có thể khác theo phiên bản.

## 22. Những nhầm lẫn thường gặp

**1. “COMMIT phải ghi mọi trang dữ liệu xuống đĩa.”** Không. WAL giúp xác nhận giao dịch bền vững theo cấu hình mà không bắt buộc flush mọi data page tại đúng thời điểm commit.

**2. “WAL là một bản backup đầy đủ.”** Không. WAL dùng cho redo, replication và PITR, nhưng PITR cần base backup và chuỗi WAL thích hợp.

**3. “Checkpoint là một lần COMMIT toàn database.”** Không. Checkpoint đồng bộ tiến độ ghi dữ liệu và xác lập mốc recovery, không commit transaction của ứng dụng.

**4. “Checkpoint xoá toàn bộ WAL cũ ngay lập tức.”** Không. WAL có thể phải giữ cho replication slot, standby, archive hoặc backup.

**5. “max_wal_size là quota cứng của pg_wal.”** Không. Dung lượng thực tế có thể vượt mục tiêu.

**6. “Có WAL thì synchronous_commit=off vẫn bảo đảm mọi COMMIT sống sau crash.”** Không. Transaction đã trả thành công nhưng chưa được flush bền vững có thể bị mất.

**7. “fsync=off chỉ làm mất một chút dữ liệu mới nhất.”** Rủi ro có thể nghiêm trọng hơn, kể cả hư hỏng dữ liệu sau OS/storage crash.

**8. “Crash recovery chỉ replay các transaction đã commit ở cấp từng dòng.”** WAL redo là thao tác phục hồi vật lý; trạng thái commit/abort và MVCC quyết định khả năng nhìn thấy dữ liệu.

**9. “WAL segment luôn có kích thước đúng 16 MB.”** 16 MiB thường là mặc định, nhưng kích thước segment có thể khác theo cách khởi tạo cluster.

**10. “Muốn giải phóng ổ đĩa thì xóa pg_wal.”** Làm vậy có thể phá khả năng recovery hoặc replication. Phải điều tra lý do WAL được giữ.

**11. “Bảng UNLOGGED bền vững như bảng thường vì có trong PostgreSQL.”** Không. Nội dung bảng unlogged có thể mất sau crash và không được physical streaming replicate như bảng logged.

**12. “Đọc trên standby luôn nhìn thấy COMMIT vừa xong ở primary.”** Có thể có độ trễ nhận/replay. Cần kiểm tra cấu hình synchronous replication và mức nhất quán của ứng dụng.

**13. “Một view thống kê checkpoint dùng được trên mọi major.”** Không. Các view và cột thống kê có thể thay đổi giữa major, chẳng hạn cách phân tách `pg_stat_checkpointer` và `pg_stat_bgwriter`.

**14. “Server khởi động lại thành công nghĩa là đã có backup và DR tốt.”** Crash recovery giải quyết một loại sự cố; xóa nhầm, hỏng toàn bộ data directory và mất site cần backup/PITR/DR riêng.

## 23. Quy trình đọc một sự cố PostgreSQL theo trục WAL

Khi có sự cố khởi động lại, chậm ghi hoặc WAL tăng bất thường, hãy phân loại theo một chuỗi câu hỏi:

```text
1. Sự cố là CRASH, mất dữ liệu logic, hay replication lag?
                           |
                           v
2. Server đang chạy primary hay standby?
                           |
                           v
3. WAL được tạo, ghi, flush, nhận và replay đến đâu?
                           |
                           v
4. Checkpoint gần đây và trạng thái I/O ra sao?
                           |
                           v
5. Có archiving/replication slot/backup giữ WAL không?
                           |
                           v
6. Cấu hình durability có đánh đổi RPO hay không?
                           |
                           v
7. Phương án an toàn: phục hồi, tăng dung lượng,
   sửa archive/consumer hoặc điều chỉnh checkpoint
   theo dữ liệu quan sát và runbook
```

Đối với hệ thống thật, luôn ghi lại **phiên bản PostgreSQL**, thời điểm sự cố, vị trí/timeline WAL, thông số liên quan, kết quả log và trạng thái backup trước khi thực hiện thao tác thay đổi. Không chạy công cụ sửa chữa cấp thấp, xóa WAL hoặc ép promotion khi chưa hiểu trạng thái dữ liệu và các hệ thống phụ thuộc.

## 24. Tổng kết

Có thể ghi nhớ mối quan hệ giữa ba cơ chế theo một câu: **WAL bảo vệ lịch sử thay đổi cần redo; checkpoint giảm khối lượng lịch sử phải đọc lại khi crash; crash recovery dùng data files và WAL để tái lập trạng thái nhất quán**.

- **WAL** được ghi trước các trang dữ liệu theo write-ahead rule. LSN cho biết vị trí trong luồng WAL; những bản ghi cần thiết giúp recovery khi data page chưa flush.
- **COMMIT** kết thúc transaction, còn độ bền của lời xác nhận phụ thuộc thiết lập như `synchronous_commit`, `fsync` và chất lượng bộ lưu trữ.
- **Checkpoint** tổ chức việc flush dirty pages và ghi nhận mốc redo; nó không tự commit transaction, không phải backup và không bắt buộc dọn sạch mọi segment WAL cũ.
- **Crash recovery** replay WAL từ điểm phù hợp với checkpoint, phối hợp transaction status/MVCC để đảm bảo các thay đổi được nhìn thấy đúng sau restart.
- **Replication** nhận và replay WAL ở standby; **PITR** dùng base backup cùng chuỗi WAL archive để khôi phục tới mốc thời gian đã chọn.
- **Vận hành an toàn** cần xem thống kê WAL, checkpoint, archiver, replication slots, cấu hình và log, đồng thời không bao giờ tùy tiện xóa tệp trong `pg_wal`.

Hiểu bức tranh này giúp bạn giải thích vì sao PostgreSQL có thể trả `COMMIT` nhanh mà vẫn có khả năng khôi phục sau mất điện, vì sao một checkpoint có thể ảnh hưởng tới I/O, vì sao WAL đôi khi chiếm nhiều dung lượng và tại sao backup/replication không được đồng nhất với crash recovery.
