# wal_level, retention và nhu cầu của các loại sao chép trong PostgreSQL

PostgreSQL ghi lại những thay đổi quan trọng của database vào **Write-Ahead Log (WAL)** trước khi các page dữ liệu tương ứng được ghi bền vững xuống data files. WAL giúp database phục hồi sau sự cố, hỗ trợ backup/PITR và cung cấp dữ liệu cho các standby hoặc hệ thống CDC.

Ba cấu hình thường được nhắc đến là:

- **wal_level**: quyết định mức thông tin PostgreSQL ghi vào WAL để phục vụ crash recovery, archiving, physical replication và logical decoding.
- **WAL retention**: quyết định WAL cũ được giữ lại bao lâu hoặc đến mức nào để một consumer còn có thể đọc.
- **Replication/archiving configuration**: xác định consumer nào cần WAL, PostgreSQL giữ WAL bằng cách nào và giới hạn tài nguyên ra sao.

Ba khái niệm này liên quan nhưng không thay thế nhau. Chọn wal_level=logical không tự động bảo đảm giữ đủ WAL cho một logical subscriber bị ngừng nhiều ngày. Ngược lại, giữ rất nhiều WAL cũng không thể tạo logical change records nếu server chỉ chạy ở mức wal_level=replica.

Một thiết kế đúng phải trả lời được ba câu hỏi:

1. **Consumer cần loại thông tin nào trong WAL?**
2. **Consumer có thể ngừng hoạt động bao lâu trước khi cần WAL đã bị thu hồi?**
3. **Dung lượng đĩa, WAL generation rate, archive và replica lag có đủ đáp ứng khoảng thời gian đó không?**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích WAL, WAL records, LSN và WAL segments.
2. Phân biệt wal_level=minimal, replica và logical.
3. Chọn wal_level theo nhu cầu crash recovery, PITR, physical replication và logical replication/CDC.
4. Phân biệt WAL generation với WAL retention.
5. Hiểu vai trò và giới hạn của wal_keep_size, replication slots, max_slot_wal_keep_size, max_wal_size và min_wal_size.
6. Cấu hình WAL archiving, archive_command, archive_timeout và retention của archive.
7. Giải thích vì sao physical standby, cascading standby, logical subscriber và backup/PITR có yêu cầu khác nhau.
8. Hiểu cách replication slot giữ WAL, restart_lsn, confirmed_flush_lsn và rủi ro đầy disk.
9. Ước lượng dung lượng WAL theo tốc độ sinh WAL và thời gian consumer có thể offline.
10. Theo dõi primary, standby, archiver và replication slots bằng system views.
11. Chẩn đoán archive failure, replication lag, inactive slots và standby mất WAL.
12. Lập kế hoạch đổi wal_level, restart, failover, backup và cleanup WAL an toàn.

## 2. WAL là gì?

WAL là chuỗi record mô tả những thay đổi cần thiết để PostgreSQL phục hồi database. Thay vì phải ghi mọi page dữ liệu đã thay đổi xuống đúng vị trí trước khi xác nhận transaction, PostgreSQL có thể ghi WAL trước rồi flush data pages sau.

Đây là nguyên tắc **write-ahead**:

```text
Transaction thay đổi row
          |
          v
Tạo WAL records
          |
          v
WAL được ghi/flush theo durability requirements
          |
          v
Transaction có thể được xác nhận COMMIT
          |
          v
Data pages được ghi xuống data files sau đó
```

Nếu server crash sau khi commit được xác nhận nhưng trước khi mọi dirty data pages được ghi, PostgreSQL dùng WAL để redo những thay đổi cần thiết khi khởi động lại.

### 2.1. WAL không phải bản sao SQL statements

WAL không đơn giản là một file log chứa nguyên văn câu UPDATE hoặc INSERT mà ứng dụng gửi. WAL chứa record ở mức storage/recovery và thông tin cần cho các chế độ replication/decoding. Nội dung record phụ thuộc loại thao tác, wal_level, PostgreSQL version và những cấu hình liên quan.

### 2.2. WAL không phải audit log nghiệp vụ

Không nên dùng WAL như lịch sử nghiệp vụ dễ đọc để trả lời “ai đổi email vì lý do gì”. WAL có mục đích phục hồi và replication. Nếu cần audit trail, hãy thiết kế audit tables, event log hoặc CDC pipeline có schema/retention phù hợp.

### 2.3. WAL không phải backup độc lập

WAL giúp phục hồi khi kết hợp với một base backup phù hợp hoặc trạng thái database còn tồn tại. Một thư mục WAL rời rạc không thay thế backup đầy đủ.

## 3. WAL records, LSN và segments

### 3.1. LSN

**Log Sequence Number (LSN)** là vị trí trong luồng WAL. LSN thường được hiển thị dưới dạng hai phần hexadecimal:

```text
0/16B6C50
0/16B7A20
0/16C0128
```

LSN tăng theo tiến trình ghi WAL. Có thể dùng LSN để so sánh vị trí WAL giữa primary, standby và replication slot.

Một số hàm thường dùng:

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn() AS flush_lsn;
```

Các hàm pg_current_wal_* áp dụng cho primary và phiên bản hỗ trợ; tên hàm ở các phiên bản PostgreSQL cũ có thể khác.

### 3.2. WAL segment

WAL được chia thành các segment file trong thư mục pg_wal. Kích thước segment phổ biến là 16 MB, nhưng đây là thuộc tính của build PostgreSQL và không nên hard-code khi tính capacity.

Một segment được hoàn tất khi PostgreSQL chuyển sang segment kế tiếp. Segment cũ có thể được:

- Giữ lại vì vẫn cần cho crash recovery/checkpoint.
- Giữ lại vì standby hoặc replication slot còn cần.
- Chờ archive thành công.
- Recycle để dùng lại.
- Xóa khi không còn cần và chính sách cho phép.

### 3.3. WAL directory

Trên các phiên bản hiện đại, thư mục WAL thường là:

```text
$PGDATA/pg_wal/
```

Không xóa hoặc sửa file trong pg_wal bằng lệnh filesystem thủ công. PostgreSQL quản lý vòng đời các segment; xóa thủ công có thể làm hỏng khả năng phục hồi hoặc khiến server không khởi động được.

### 3.4. WAL generation rate

WAL generation rate là lượng WAL được tạo ra trong một khoảng thời gian. Nó thay đổi theo:

- Số lượng INSERT/UPDATE/DELETE.
- Kích thước row và số index cần cập nhật.
- Bulk load và các thao tác DDL.
- Full-page images sau checkpoint.
- Logical decoding requirements.
- Các workload và tính năng PostgreSQL đang bật.

Không thể suy ra WAL generation chỉ từ số transaction mỗi giây; một transaction cập nhật nhiều row lớn có thể tạo WAL nhiều hơn hàng nghìn transaction nhỏ.

## 4. wal_level điều khiển điều gì?

wal_level quyết định lượng thông tin được ghi vào WAL. PostgreSQL có ba mức chính:

| Giá trị | Mục đích | Các nhu cầu được hỗ trợ |
| --- | --- | --- |
| minimal | Giảm thông tin WAL tới mức cần cho crash recovery | Crash recovery cục bộ; không dùng cho archiving/PITR hoặc replication |
| replica | Ghi đủ thông tin cho WAL archiving và physical replication | Crash recovery, PITR, physical streaming/cascading replication, hot standby |
| logical | Bổ sung thông tin cần cho logical decoding | Các nhu cầu của replica và logical replication/CDC |

Mặc định phổ biến của PostgreSQL hiện đại là replica.

### 4.1. minimal

minimal chỉ ghi thông tin cần thiết để phục hồi database sau crash hoặc shutdown không sạch. Ở mức này, PostgreSQL có thể tối ưu một số thao tác bulk như tạo hoặc nạp relation mới bằng cách không ghi toàn bộ dữ liệu relation vào WAL theo cách cần cho replication/archiving.

Đổi lại:

- Không dùng được WAL archiving cho PITR.
- Không hỗ trợ hot standby/physical streaming replication.
- Không hỗ trợ logical decoding.
- Không phù hợp với hệ thống cần standby hoặc CDC.

Không chọn minimal cho primary production chỉ vì muốn giảm WAL nếu hệ thống có backup/PITR hoặc replication requirements.

### 4.2. replica

replica ghi đủ thông tin để hỗ trợ WAL archiving và physical replication, bao gồm hot standby.

Đây là lựa chọn phù hợp cho:

- Primary với một hoặc nhiều physical standbys.
- Streaming replication đồng bộ hoặc bất đồng bộ.
- Cascading replication.
- WAL archive kết hợp base backup để PITR.
- Các hệ thống backup cần WAL liên tục.

replica không cung cấp đầy đủ row-level change information cho logical decoding như mức logical.

### 4.3. logical

logical bổ sung WAL information cần thiết cho logical decoding. Đây là điều kiện quan trọng cho PostgreSQL logical replication và các hệ thống CDC dùng logical decoding output plugins.

logical vẫn hỗ trợ các nhu cầu physical replication của mức replica, nhưng có thể tạo thêm WAL overhead tùy workload và features được sử dụng.

Dùng khi cần:

- Publication/subscription của PostgreSQL.
- CDC qua logical replication protocol.
- Output plugins như pgoutput hoặc plugin khác.
- Đồng bộ một phần bảng hoặc chuyển đổi dữ liệu theo row changes.

### 4.4. Chọn mức cao hơn không tự động tạo consumer

Đặt wal_level=logical không tự tạo publication, subscription, replication slot hay CDC consumer. Nó chỉ làm cho PostgreSQL ghi loại thông tin cần thiết. Các phần còn lại phải được cấu hình riêng.

## 5. wal_level và WAL retention là hai vấn đề khác nhau

Đây là điểm rất dễ nhầm:

- wal_level trả lời **WAL chứa thông tin gì**.
- Retention trả lời **WAL cũ được giữ lại tới đâu**.

Ví dụ:

1. Primary chạy wal_level=logical.
2. Logical subscriber bị ngừng 24 giờ.
3. Replication slot giữ WAL cần thiết trong thời gian subscriber offline.
4. Nếu disk đầy hoặc giới hạn slot khiến WAL cần thiết bị thu hồi, subscriber có thể không tiếp tục được từ vị trí cũ.

wal_level=logical không tự đảm bảo subscriber có đủ WAL mãi mãi.

### 5.1. WAL generation

Là tốc độ tạo WAL mới.

### 5.2. WAL retention

Là lượng/thời gian WAL chưa được phép loại bỏ vì còn consumer hoặc recovery requirement cần.

### 5.3. WAL archival

Là việc sao chép WAL segments đã hoàn tất sang kho lưu trữ bên ngoài pg_wal.

### 5.4. WAL recycling

Là việc tái sử dụng segment file cũ thay vì luôn tạo và xóa file mới. Segment được recycle vẫn là dung lượng được quản lý trong pg_wal, không phải bằng chứng dữ liệu đó còn cần cho replication.

### 5.5. Một segment có thể cần cho nhiều mục đích

WAL segment chỉ được loại bỏ/recycle khi không còn yêu cầu nội bộ nào giữ nó, chẳng hạn:

- Checkpoint/recovery.
- wal_keep_size.
- Replication slots.
- Archiving chưa thành công.

Vì vậy, một cấu hình retention đơn lẻ không thể thay thế việc theo dõi toàn bộ các consumer.

## 6. Các tham số WAL quan trọng

| Tham số | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| wal_level | Mức thông tin trong WAL | Thay đổi cần restart server |
| wal_keep_size | Dung lượng WAL tối thiểu giữ lại trong pg_wal cho standby | Không phải giới hạn tối đa |
| max_slot_wal_keep_size | Giới hạn WAL được giữ do replication slots | Có thể làm slot mất khả năng tiếp tục nếu vượt giới hạn |
| max_wal_size | Mục tiêu mềm cho WAL/checkpoint | Không phải hard cap của pg_wal |
| min_wal_size | Mức WAL tối thiểu PostgreSQL cố gắng recycle/giữ | Không phải thời gian retention cho standby |
| archive_mode | Bật WAL archiving | Cần mức wal_level phù hợp và restart |
| archive_command | Lệnh archive mỗi segment | Phải báo thành công chỉ khi archive thực sự bền vững |
| archive_timeout | Buộc switch WAL segment sau khoảng thời gian nếu có WAL activity | Có thể tăng archive volume |
| max_wal_senders | Số process sender phục vụ replication connections | Cần đủ cho standbys và các client replication |
| max_replication_slots | Số replication slots tối đa | Tính cả physical và logical slots |
| checkpoint_timeout | Khoảng thời gian tối đa giữa checkpoints | Ảnh hưởng checkpoint/WAL behavior, không phải slot retention |
| synchronous_standby_names | Chọn synchronous standbys | Điều khiển commit acknowledgment, không thay wal_level |

Các setting có context và giới hạn theo phiên bản. Có thể kiểm tra trên server:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'max_wal_size',
    'min_wal_size',
    'archive_mode',
    'archive_timeout',
    'max_wal_senders',
    'max_replication_slots',
    'checkpoint_timeout',
    'synchronous_standby_names'
)
ORDER BY name;
```

## 7. wal_keep_size: giữ một lượng WAL tối thiểu cho standby

wal_keep_size yêu cầu PostgreSQL giữ lại tối thiểu một lượng WAL trong pg_wal để standby có thêm cơ hội bắt kịp nếu bị chậm hoặc ngắt kết nối.

Ví dụ:

```conf
wal_keep_size = 2GB
```

### 7.1. Đây không phải thời gian giữ WAL

2GB không có nghĩa là giữ WAL trong hai giờ. Thời gian tương ứng phụ thuộc WAL generation rate.

Nếu hệ thống tạo 10 MB/s, 2 GB chỉ tương đương vài phút. Nếu hệ thống tạo 100 KB/s, cùng dung lượng có thể bao phủ thời gian dài hơn nhiều.

### 7.2. Đây không phải hard cap

wal_keep_size là mức tối thiểu bổ sung cho standby, không giới hạn tổng pg_wal ở đúng giá trị đó. Checkpoint, archive backlog, replication slots và workload có thể khiến pg_wal lớn hơn.

### 7.3. Không có slot vẫn có thể mất WAL

Nếu standby bị ngắt lâu hơn lượng WAL được giữ và segment cần thiết đã bị recycle, standby không thể tiếp tục streaming từ LSN cũ chỉ bằng wal_keep_size. Có thể cần WAL archive để lấy lại segment hoặc phải tạo lại standby từ base backup.

### 7.4. Phiên bản cũ

Ở các phiên bản PostgreSQL cũ, tham số wal_keep_segments được dùng để giữ số segment tối thiểu. Từ PostgreSQL 13, wal_keep_size thay thế cách cấu hình theo số segment. Khi quản trị cluster cũ, hãy xem tài liệu đúng major version.

## 8. Replication slots: giữ WAL theo nhu cầu consumer

Replication slot là cơ chế PostgreSQL theo dõi tiến độ của một consumer và ngăn WAL cần thiết bị loại bỏ trước khi consumer xác nhận đã nhận/tiêu thụ.

Hai loại phổ biến:

- **Physical replication slot:** dành cho physical standby.
- **Logical replication slot:** dành cho logical decoding/subscriber/CDC.

### 8.1. Vì sao slot hữu ích?

Nếu một standby bị ngắt vài giờ, slot có thể giữ lại WAL từ vị trí mà standby cần. Khi kết nối lại, standby có thể tiếp tục nếu WAL vẫn còn và các điều kiện khác đáp ứng.

Không cần đoán một con số wal_keep_size cố định cho mọi outage; slot theo dõi vị trí consumer cụ thể.

### 8.2. Tạo physical slot

Ví dụ tạo slot trên primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

Tên slot phải unique trong cluster. Physical standby được cấu hình để sử dụng slot đó qua primary_slot_name.

### 8.3. Tạo logical slot

Ví dụ:

```sql
SELECT *
FROM pg_create_logical_replication_slot(
    'cdc_customers_slot',
    'pgoutput'
);
```

Logical decoding slot cần output plugin phù hợp. PostgreSQL logical replication thường quản lý slot trong quá trình tạo subscription; không tự tạo một slot trùng tên rồi để subscription cũng cố tạo cùng slot.

### 8.4. Slot không phải backup

Slot chỉ giữ WAL mà consumer cần. Nó không giữ một bản đầy đủ của table, schema, roles hoặc database. Muốn khôi phục toàn bộ database vẫn cần base backup và WAL archive theo mục tiêu recovery.

## 9. Rủi ro lớn nhất của replication slot: WAL làm đầy disk

Nếu consumer ngừng hoạt động, slot có thể giữ lại WAL trong pg_wal. Khi đó:

```text
Consumer ngừng đọc WAL
        |
        v
restart_lsn không tiến lên
        |
        v
Primary tiếp tục tạo WAL mới
        |
        v
WAL cũ vẫn cần cho slot
        |
        v
pg_wal tăng dung lượng
        |
        v
Filesystem có thể đầy
```

### 9.1. Slot inactive vẫn giữ WAL

active=false không có nghĩa slot vô hại. Slot inactive có thể vẫn giữ một lượng WAL lớn vì consumer chưa xác nhận tiến độ.

### 9.2. Nhiều slot

Mỗi slot có thể giữ một điểm WAL riêng. Về tổng thể, WAL cũ nhất còn cần bởi bất kỳ slot nào có thể ngăn PostgreSQL recycle segment. Một slot bị bỏ quên có thể giữ WAL dù tất cả standbys khác đã bắt kịp.

### 9.3. Slot tồn tại lâu hơn consumer

Nếu CDC pipeline bị xóa nhưng logical slot vẫn còn, primary có thể tiếp tục giữ WAL vô hạn theo cấu hình mặc định không giới hạn. Cần quy trình lifecycle cho slot.

### 9.4. Không xóa slot để giải phóng disk mà không kiểm tra

Drop slot có thể cho phép PostgreSQL loại bỏ WAL mà consumer cần. Nếu consumer còn được dùng, nó có thể mất khả năng resume và phải tạo lại/re-snapshot.

## 10. max_slot_wal_keep_size: giới hạn WAL do slot giữ

max_slot_wal_keep_size giới hạn lượng WAL mà replication slots được phép giữ lại. Giá trị mặc định phổ biến là -1, nghĩa là không giới hạn.

Ví dụ:

```conf
max_slot_wal_keep_size = 20GB
```

### 10.1. Vì sao cần giới hạn?

Giới hạn bảo vệ primary khỏi một consumer inactive kéo dung lượng pg_wal tăng vô hạn.

### 10.2. Đổi lại: slot có thể bị invalidated

Nếu slot cần WAL cũ hơn nhưng lượng WAL giữ vượt giới hạn, PostgreSQL có thể loại bỏ WAL cần thiết tại checkpoint. Slot có thể mất khả năng tiếp tục từ vị trí cũ; standby hoặc logical consumer phải được khôi phục bằng cách phù hợp, có thể là tạo lại/reinitialize.

Giới hạn không phải “giữ tối đa rồi tự làm consumer bắt kịp”. Nó là trade-off giữa bảo vệ disk và khả năng resume.

### 10.3. Giới hạn được áp dụng theo checkpoint

Việc loại bỏ WAL để thực thi giới hạn slot có liên hệ với checkpoint. Đừng coi con số cấu hình như một hard real-time alarm chính xác từng byte; theo dõi pg_replication_slots, disk usage và logs.

### 10.4. Chọn giới hạn dựa trên outage budget

Nếu muốn một CDC consumer có thể offline 6 giờ, hãy đo peak WAL generation trong 6 giờ và cộng headroom. Không đặt 20 GB chỉ vì nó có vẻ lớn.

### 10.5. Version compatibility

max_slot_wal_keep_size có từ các phiên bản PostgreSQL hiện đại (PostgreSQL 13 trở lên). Kiểm tra SHOW max_slot_wal_keep_size và tài liệu major version trước khi dùng trong automation.

## 11. max_wal_size không phải retention cap

Đây là nhầm lẫn phổ biến.

max_wal_size là **mục tiêu mềm** liên quan đến việc kích hoạt checkpoints. Nó không đặt giới hạn tuyệt đối cho tổng dung lượng WAL trong pg_wal.

Ví dụ:

```conf
max_wal_size = 8GB
min_wal_size = 1GB
```

pg_wal vẫn có thể lớn hơn 8 GB khi:

- Replication slots giữ WAL cũ.
- Archive command thất bại và WAL chưa được archive.
- wal_keep_size yêu cầu giữ thêm WAL.
- WAL generation tăng mạnh.
- Checkpoint chưa thể loại bỏ những segment còn cần.

### 11.1. max_wal_size ảnh hưởng checkpoint

Khi WAL tăng đến mức khiến PostgreSQL cần checkpoint theo mục tiêu max_wal_size, checkpoint có thể được lên lịch sớm hơn. Đây là một trong những cách kiểm soát checkpoint frequency và I/O behavior.

### 11.2. min_wal_size

min_wal_size điều khiển mức WAL PostgreSQL cố gắng giữ/recycle để dùng lại. Nó không đảm bảo một standby có thể resume từ bất kỳ LSN nào trong khoảng đó.

### 11.3. Checkpoint không được phép xóa WAL còn cần

Checkpoint đánh dấu trạng thái cần cho crash recovery. Nhưng archive backlog, replication slots và wal_keep_size còn có thể giữ WAL vượt qua điểm checkpoint.

### 11.4. Khi disk đầy, đừng chỉ giảm max_wal_size

Nếu nguyên nhân là inactive slot hoặc archive failure, giảm max_wal_size không giải phóng WAL bị giữ bởi consumer. Phải xác định retention owner.

## 12. WAL archiving

WAL archiving sao chép các WAL segments đã hoàn tất từ pg_wal sang một kho lưu trữ khác. Nó thường được dùng cho:

- Point-in-time recovery (PITR).
- Khôi phục standby khi cần WAL cũ.
- Backup dài hạn kết hợp base backup.
- Disaster recovery.

### 12.1. Bật archive mode

Ví dụ:

```conf
wal_level = replica
archive_mode = on
archive_command = '...'
```

archive_mode cần server restart để thay đổi có hiệu lực. Archive cần wal_level phù hợp; minimal không thể dùng cho WAL archiving.

### 12.2. archive_command

archive_command được gọi với hai placeholder:

- %p: đường dẫn file WAL segment nguồn trên server.
- %f: tên file WAL segment.

Ví dụ cấu hình gọi một script quản lý archive:

```conf
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

Script này chỉ là ví dụ tên đường dẫn. Cần triển khai và kiểm thử script thực tế trên máy chủ database.

### 12.3. Điều kiện trả exit code thành công

Archive command chỉ nên trả thành công khi segment đã được lưu bền vững tại đích và có thể truy xuất. Nếu copy thất bại, command phải trả mã lỗi để PostgreSQL thử lại.

Không trả exit code 0 chỉ vì đã khởi chạy một tiến trình nền hoặc upload chưa hoàn tất.

### 12.4. Archive command phải xử lý retry idempotent

PostgreSQL có thể gọi archive command lại cho cùng segment sau khi một lần trước thất bại hoặc kết quả không chắc chắn. Script phải xử lý trường hợp file đích đã tồn tại:

- Nếu file đích cùng nội dung, coi đó là thành công.
- Nếu file đích khác nội dung, báo lỗi và điều tra.
- Không ghi đè một WAL segment khác chỉ vì trùng tên.

### 12.5. Đích archive phải độc lập với pg_wal

Nếu archive directory nằm trên cùng filesystem đang đầy vì pg_wal, việc archive có thể không giải quyết được rủi ro dung lượng. Nên cân nhắc volume/storage riêng và giám sát capacity.

### 12.6. Bảo vệ archive

WAL có thể chứa dữ liệu nhạy cảm ở mức storage. Cần kiểm soát quyền đọc, mã hóa khi truyền/lưu, backup archive, integrity checks và retention.

## 13. archive_timeout và segment switch

PostgreSQL thường archive một WAL segment khi segment được hoàn tất/switch. Nếu workload rất ít ghi, segment hiện tại có thể chưa đầy trong thời gian dài.

archive_timeout buộc PostgreSQL chuyển segment sau khoảng thời gian đã cấu hình khi có hoạt động WAL phù hợp.

Ví dụ:

```conf
archive_timeout = 300s
```

### 13.1. Vì sao dùng archive_timeout?

Nó có thể giảm thời gian chờ để một ít WAL cuối cùng được chuyển vào archive, hữu ích cho recovery point objective của workload ít ghi.

### 13.2. Đổi lại: archive volume có thể tăng

Segment được switch sớm vẫn được archive theo segment. Với workload thưa, nhiều segment được archive dù chỉ chứa ít WAL hữu ích.

### 13.3. Không biến archive_timeout thành RPO

archive_timeout=5min không đảm bảo backup có thể khôi phục chính xác mọi transaction trong 5 phút. Cần tính thời gian archive command chạy, network/storage availability, WAL flush và các bước backup.

### 13.4. Không giảm archive_timeout cực thấp một cách tùy tiện

Giá trị quá thấp có thể làm tăng số lượng file archive và chi phí metadata/network/object storage. Chọn theo RPO và throughput thực tế.

## 14. archive_mode: on và always

Các giá trị phổ biến:

- off: không chạy WAL archiving.
- on: archive WAL segments được tạo bởi server trong vai trò primary theo chế độ bình thường.
- always: archive cả WAL được server nhận trong recovery/standby theo các quy tắc của chế độ này.

always có thể hữu ích trong một số kiến trúc standby cần archive WAL đã nhận, nhưng phải thiết kế archive destination/ownership để tránh xung đột hoặc ghi đè giữa các nodes.

### 14.1. Tên WAL segment

Physical standby có thể nhận các segment cùng tên với những segment từ primary. Nếu nhiều node archive vào cùng một namespace, cần đảm bảo chúng thuộc cùng WAL history/cluster và có cơ chế phân biệt/kiểm tra phù hợp.

### 14.2. Không bật always chỉ để “an toàn hơn”

Hiểu rõ node nào archive, segment nào được lưu, destination có unique namespace ra sao và quy trình restore sẽ đọc từ đâu.

## 15. Archive cleanup và retention

WAL archive thường được giữ lâu hơn các segment trong pg_wal, nhưng không có nghĩa giữ vô hạn.

Retention archive phải xét:

- Các base backups còn được phép restore.
- PITR window cần đáp ứng.
- Các standby có thể cần fetch WAL từ archive.
- Disaster recovery copies.
- Chính sách pháp lý và chi phí storage.

### 15.1. Base backup và WAL phải đi cùng nhau

Để PITR, cần một base backup hợp lệ và toàn bộ WAL liên tục từ thời điểm backup bắt đầu/điểm cần thiết đến recovery target.

Nếu xóa WAL archive quá sớm, một base backup cũ có thể không còn khôi phục tới thời điểm mong muốn.

### 15.2. pg_archivecleanup

PostgreSQL cung cấp pg_archivecleanup để xóa WAL archive cũ hơn một segment được chỉ định, thường dùng trong archive_cleanup_command cho standby archive recovery.

Công cụ này cần được dùng với đúng WAL history/segment boundary và chính sách backup. Không chạy một lệnh cleanup chung cho kho archive chứa nhiều backup chains hoặc nhiều clusters nếu chưa xác định segment nào còn cần.

### 15.3. Không cleanup chỉ dựa vào standby hiện tại

Một standby đã bắt kịp không chứng minh archive segments cũ không còn cần cho PITR/base backup. Archive retention và streaming retention là hai lifecycle khác nhau.

### 15.4. Object storage lifecycle

Nếu dùng object storage, lifecycle policy có thể chuyển WAL sang storage class rẻ hơn hoặc xóa sau thời hạn. Phải bảo đảm recovery tool vẫn truy xuất được các segments cần thiết và object chưa bị chuyển/xóa ngoài ý muốn.

## 16. Physical streaming replication cần gì?

Physical streaming replication truyền WAL từ primary sang standby để standby replay các thay đổi vật lý.

Yêu cầu chính:

- Primary chạy wal_level=replica hoặc logical.
- Đủ max_wal_senders.
- Role replication và network/TLS phù hợp.
- Standby có primary_conninfo.
- Có chiến lược lấy WAL bị thiếu: streaming, slot và/hoặc archive.
- Có base backup tương thích.

### 16.1. Primary config minh họa

```conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
```

Các con số chỉ để minh họa. Phải tính số standbys, backup clients và replication connections thực tế.

### 16.2. Standby cần base backup

Một standby mới thường được khởi tạo từ base backup của primary hoặc một standby tương thích. Streaming WAL chỉ chứa phần thay đổi tiếp theo; nó không tự gửi toàn bộ dữ liệu lịch sử của database cho một máy trắng.

### 16.3. Streaming replication không đồng nghĩa synchronous

Physical streaming có thể asynchronous hoặc synchronous. Điều đó được điều khiển bằng synchronous_standby_names và synchronous_commit, không chỉ bằng wal_level.

### 16.4. Standby nhận WAL theo LSN

Primary gửi WAL từ vị trí cần thiết; standby ghi nhận, flush và replay. Ba vị trí có thể khác nhau trong thời điểm quan sát.

## 17. Physical replication không dùng slot

Không dùng slot vẫn có thể streaming replication.

### 17.1. Cơ chế

Standby reconnect và yêu cầu WAL từ LSN cần thiết. Primary giữ WAL theo các giới hạn chung như wal_keep_size; nếu segment đã bị recycle, standby có thể tìm WAL từ archive nếu restore_command được cấu hình.

### 17.2. Ưu điểm

- Không có slot inactive giữ WAL vô hạn.
- Quản lý đơn giản hơn với standby có downtime dự kiến ngắn.

### 17.3. Rủi ro

- Nếu standby offline lâu hơn lượng WAL được giữ và archive không có segment cần, standby không thể tiếp tục streaming.
- Có thể cần tạo lại standby từ base backup.

### 17.4. Phù hợp khi nào?

Khi có archive đáng tin cậy và có thể chấp nhận rebuild standby nếu nó offline quá lâu; hoặc khi không muốn slot giữ WAL không giới hạn.

## 18. Physical replication dùng slot

Slot cho phép primary biết standby còn cần WAL từ đâu.

### 18.1. Standby config

Ví dụ trong postgresql.conf của standby:

```conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a'
primary_slot_name = 'standby_a_slot'
```

Credentials/TLS nên quản lý bằng cơ chế phù hợp, không ghi password rõ vào file được commit.

### 18.2. Tạo slot

Primary:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a_slot');
```

### 18.3. Lợi ích

WAL cần cho standby được giữ lại ngay cả khi standby mất kết nối, trong giới hạn tài nguyên/slot policy.

### 18.4. Chi phí

Nếu standby dừng lâu, slot giữ WAL và có thể làm pg_wal tăng tới mức đầy filesystem nếu không có cap/alert.

### 18.5. Kết hợp slot và archive

Slot bảo vệ streaming continuity khi primary còn giữ WAL; archive cung cấp đường lấy WAL cũ độc lập hơn với pg_wal. Cả hai cùng có thể cần trong một DR design.

## 19. Cascading physical replication

Trong cascading replication, một standby có thể gửi WAL tiếp cho standby khác.

```text
Primary
  |
  +---- Standby A
           |
           +---- Standby B
           |
           +---- Standby C
```

### 19.1. Lợi ích

- Giảm số kết nối replication trực tiếp tới primary.
- Có thể đặt replicas theo vùng địa lý hoặc tầng mạng.
- Phân phối tải WAL sender.

### 19.2. Retention vẫn quan trọng

Standby A phải có WAL cần thiết cho B/C hoặc có archive/recovery path phù hợp. Một cascading standby bị chậm có thể ảnh hưởng tới downstream standbys.

### 19.3. Slot ở upstream và downstream

Mỗi tầng có thể cần slot phù hợp. Cần theo dõi slot trên node giữ WAL, không chỉ nhìn primary.

### 19.4. archive_mode=always

Trong một số kiến trúc cascading/standby archive, archive_mode=always có thể cần để archive WAL được nhận trong recovery. Xác định rõ vai trò từng node và archive namespace trước khi bật.

## 20. Synchronous replication và wal_level

Synchronous replication yêu cầu primary chờ một hoặc nhiều standby xác nhận WAL theo mức được chọn trước khi báo commit thành công.

Ví dụ:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

Đây chỉ là cấu hình minh họa; cần hiểu cú pháp, node names và failover policy của cụm.

### 20.1. wal_level không quyết định sync/async

wal_level=replica cung cấp thông tin WAL cho physical replication. Việc commit chờ standby hay không là quyết định khác.

### 20.2. synchronous_commit

Một số mức có thể chờ local WAL flush, remote write, remote flush hoặc remote apply theo semantics phiên bản. remote_apply có thể chờ standby replay WAL trước khi commit trả về.

### 20.3. Trade-off

- Đồng bộ có thể giảm RPO cho các commit được xác nhận theo cấu hình.
- Có thể tăng latency và phụ thuộc standby availability.
- Thiết kế sai có thể khiến write traffic bị block khi synchronous standby mất kết nối.

### 20.4. Retention không thay commit acknowledgment

Giữ WAL lâu hơn không đồng nghĩa transaction đã được standby xác nhận. Retention bảo đảm WAL còn sẵn để gửi/replay; synchronous commit quyết định thời điểm primary xác nhận commit.

## 21. WAL archiving và Point-in-Time Recovery

PITR cho phép khôi phục database từ base backup và replay WAL đến một thời điểm/LSN mục tiêu.

### 21.1. Cấu hình primary minh họa

```conf
wal_level = replica
archive_mode = on
archive_timeout = 300s
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

### 21.2. Quy trình khái quát

1. Tạo base backup nhất quán.
2. Lưu trữ WAL liên tục sau/bao phủ điểm cần thiết của backup.
3. Bảo đảm archive command không bỏ sót segments.
4. Khi restore, đặt restore_command để lấy WAL từ archive.
5. Chọn recovery target time/LSN/transaction nếu cần.
6. Kiểm thử recovery định kỳ.

### 21.3. restore_command

Trong cấu hình recovery, restore_command lấy WAL segment cần thiết từ archive vào vị trí PostgreSQL yêu cầu. Lệnh phải trả exit status đúng khi file tồn tại hoặc không tồn tại, và xử lý retry phù hợp.

### 21.4. Archive completeness

Một base backup chỉ hữu ích tới recovery target nếu có đủ WAL cần thiết. Lưu một vài file WAL cuối cùng không bảo đảm có thể PITR.

### 21.5. Backup và replication có mục tiêu khác

- Replication giúp standby theo kịp primary.
- Backup giúp khôi phục khi primary và replicas cùng mất dữ liệu hoặc cần quay về thời điểm trước lỗi.
- Archive WAL là một thành phần của PITR.

Không coi standby đang chạy là backup độc lập; thao tác DELETE nhầm có thể được replicate sang standby.

## 22. Logical replication và CDC cần wal_level=logical

Logical replication chuyển row changes theo logical representation thay vì sao chép toàn bộ physical storage layout.

```text
Primary
  wal_level = logical
  publication
  logical replication slot
       |
       v
Logical decoding / pgoutput
       |
       v
Subscriber hoặc CDC consumer
       |
       v
Target database / Kafka / data platform
```

### 22.1. Publication và subscription

PostgreSQL native logical replication sử dụng publication trên publisher và subscription trên subscriber. Khi tạo subscription với copy data, PostgreSQL có thể thực hiện initial table synchronization rồi tiếp tục apply changes.

### 22.2. Cấu hình liên quan

Publisher thường cần:

```conf
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
```

Số slots/senders phải bao gồm native subscriptions, table synchronization và các CDC consumers khác.

### 22.3. Replica identity

Để logical replication xác định row cần UPDATE/DELETE ở subscriber, table cần replica identity phù hợp. Primary key thường là lựa chọn tốt:

```sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
```

Nếu không có primary key phù hợp, có thể cân nhắc unique index đáp ứng điều kiện hoặc REPLICA IDENTITY FULL:

```sql
ALTER TABLE app.customers
REPLICA IDENTITY FULL;
```

FULL có thể làm tăng lượng dữ liệu cần gửi/đọc và chi phí tìm row ở subscriber. Chỉ dùng khi cần.

### 22.4. Logical replication không tự đồng bộ mọi thứ

Native logical replication tập trung vào table data changes. Không mặc định rằng nó tự sao chép mọi DDL, roles, grants, sequence state hoặc mọi loại object database. Các phần này cần quy trình deployment/migration riêng hoặc công cụ bổ sung.

### 22.5. Logical replication không thay physical HA hoàn toàn

Logical subscriber có schema/objects và dữ liệu theo logical mapping riêng. Nó không phải byte-for-byte physical standby có thể thay thế primary theo cùng cơ chế failover vật lý.

## 23. Logical replication slots và LSN

Logical slot giữ WAL cho tới khi decoder/consumer xác nhận đã tiêu thụ.

Các cột quan trọng trong pg_replication_slots:

- restart_lsn: vị trí WAL sớm nhất mà slot còn có thể cần.
- confirmed_flush_lsn: vị trí consumer đã xác nhận flush/acknowledge theo logical replication protocol.
- active: slot hiện có consumer đang dùng hay không.
- catalog_xmin: xmin liên quan tới catalog rows mà logical decoding còn cần.
- wal_status: trạng thái WAL availability trên các phiên bản có cột này.

### 23.1. restart_lsn và confirmed_flush_lsn khác nhau

confirmed_flush_lsn thường cho biết consumer đã xác nhận tới đâu. Nhưng restart_lsn có thể cũ hơn vì PostgreSQL còn cần WAL trước đó cho decoding/reorder/catalog requirements.

Vì vậy không chỉ nhìn confirmed_flush_lsn để kết luận slot không giữ WAL.

### 23.2. Inactive logical slot

Nếu consumer ngừng hoạt động, active=false; slot vẫn có thể giữ WAL và catalog history. Một CDC connector bị xóa khỏi orchestration nhưng slot còn sót có thể gây tăng disk.

### 23.3. Logical decoding và catalog retention

Logical slots có thể giữ catalog tuples thông qua catalog_xmin. Điều này có thể làm vacuum không thu hồi được một số catalog rows cũ như bình thường. Theo dõi slot lâu ngày và xử lý lifecycle.

### 23.4. Nhiều consumers

Mỗi consumer cần slot riêng nếu cần tiến độ độc lập. Slot chậm nhất có thể giữ WAL lâu nhất.

## 24. Logical replication và WAL volume

wal_level=logical ghi thêm thông tin phục vụ logical decoding. Tác động dung lượng phụ thuộc workload, schema, replica identity, full-page images, loại thay đổi và các tính năng được dùng.

### 24.1. Không có hệ số cố định

Không nói “logical luôn tạo thêm đúng 20% WAL”. Hãy đo pg_stat_wal, archive volume, slot retention và workload thật trên staging.

### 24.2. REPLICA IDENTITY FULL

Với UPDATE/DELETE, FULL có thể yêu cầu nhiều thông tin row hơn để xác định old row. Nó có thể tăng WAL/decoding/network/apply cost so với identity bằng primary key.

### 24.3. Table không có primary key

Đây là vấn đề schema/replication design cần giải quyết. Không mặc định bật FULL cho mọi table mà không đo.

### 24.4. Logical replication slots có thể giữ WAL lâu

Ngay cả khi WAL generation bình thường, consumer lag có thể làm pg_wal tăng. Cần retention budget riêng cho mỗi loại consumer.

## 25. Các loại sao chép và yêu cầu WAL

| Nhu cầu | wal_level tối thiểu | Cơ chế giữ/đọc WAL | Điểm cần chú ý |
| --- | --- | --- | --- |
| Crash recovery trên primary | minimal | WAL nội bộ tới checkpoint/recovery | Không hỗ trợ archive/replication |
| PITR bằng base backup + archive | replica | WAL archive liên tục | Archive phải đầy đủ tới recovery target |
| Physical streaming standby | replica | Streaming + wal_keep_size/slot/archive | Standby cần base backup và WAL continuity |
| Cascading physical standby | replica | Upstream streaming/slot/archive | Mỗi tầng phải đủ WAL cho downstream |
| Synchronous physical replication | replica | Streaming và sync acknowledgment | Sync settings khác wal_level |
| Native logical replication | logical | Logical slot và WAL sender | Publication, replica identity, slot lifecycle |
| CDC qua logical decoding | logical | Logical slot/output plugin | Consumer ack, restart_lsn và retention |
| Archive trên standby nhận WAL | Theo nhu cầu physical, thường replica | archive_mode=always trong thiết kế phù hợp | Namespace/history và archive ownership |

### 25.1. Một primary có thể phục vụ nhiều loại consumer

Ví dụ một hệ thống vừa có physical standby để HA, vừa có logical CDC để đẩy events sang analytics. Primary cần wal_level=logical vì đây là mức cao nhất cần cho các consumers đó.

### 25.2. Tính capacity theo consumer chậm nhất

Physical standby A có thể bắt kịp, nhưng logical CDC B bị treo. WAL vẫn có thể được giữ bởi slot của B. Không chỉ giám sát standby có vai trò HA.

### 25.3. Mỗi consumer có SLA khác nhau

HA standby có thể cần resume trong vài phút; CDC pipeline có thể cần replay sau vài giờ; PITR archive có thể cần giữ nhiều tuần. Đừng ép tất cả vào cùng một retention number.

## 26. Kết hợp archive, slot và wal_keep_size

Ba cơ chế phục vụ mục tiêu khác nhau:

| Cơ chế | Bảo vệ điều gì? | Giới hạn/rủi ro |
| --- | --- | --- |
| wal_keep_size | Giữ một lượng WAL tối thiểu trong pg_wal | Không bảo đảm đủ cho outage dài |
| Replication slot | Giữ WAL theo tiến độ consumer | Inactive slot có thể làm đầy disk; cap có thể làm slot mất hiệu lực |
| WAL archive | Lưu segment ra storage bên ngoài pg_wal | Cần archive completeness, restore path và retention policy |

### 26.1. Thiết kế kết hợp

Một primary production có thể:

- Dùng physical slot cho standby quan trọng.
- Dùng logical slots cho CDC consumers.
- Bật WAL archiving cho PITR và recovery.
- Đặt wal_keep_size làm buffer cho standby reconnect.
- Đặt max_slot_wal_keep_size để giới hạn rủi ro disk.
- Alert trước khi bất kỳ giới hạn nào bị chạm.

### 26.2. Không có một tham số thay thế tất cả

Tăng wal_keep_size không giải quyết archive command lỗi. Bật archive không tự ngăn slot giữ WAL trong pg_wal. Đặt max_wal_size nhỏ không bảo đảm disk không đầy.

## 27. Ước lượng dung lượng WAL retention

Một công thức khởi đầu:

```text
WAL cần giữ (bytes)
  ≈ Peak WAL generation rate (bytes/second)
    × Consumer outage budget (seconds)
    + Safety headroom
```

### 27.1. Ví dụ

Giả sử:

- Peak WAL generation: 20 MB/s.
- Consumer có thể offline: 6 giờ.

Tính:

```text
20 MB/s × 6 × 60 × 60
= 432,000 MB
≈ 432 GB (decimal)
```

Chưa cộng headroom cho spike, archive backlog, segment/checkpoint behavior và các consumers khác. Nếu muốn bảo vệ 6 giờ outage ở peak, 20 GB là không đủ.

### 27.2. Dùng peak hoặc percentile cao

Average WAL rate có thể thấp nhưng batch load, index rebuild hoặc cuối tháng tạo spike. Sizing chỉ theo average có thể thiếu dung lượng đúng lúc cần.

### 27.3. Tính riêng cho archive

Archive retention thường tính theo số ngày/tuần của PITR và base backup chains. Dung lượng archive phụ thuộc tổng WAL generated trong khoảng đó, không chỉ outage của standby.

### 27.4. Một segment dùng chung cho nhiều slots

WAL không được nhân bản riêng cho từng slot trong pg_wal; điểm WAL cũ nhất còn cần bởi consumer có thể quyết định lượng segment giữ. Tuy vậy, nhiều slots làm tăng khả năng có một consumer chậm kéo retention dài.

### 27.5. Headroom

Không chạy sát 100% filesystem. Dành headroom cho burst, archive retry, checkpoint, temporary files, backups và khả năng phản ứng vận hành.

## 28. Cấu hình primary cho physical replication

Ví dụ cấu hình minh họa:

```conf
# WAL information for physical standby and PITR
wal_level = replica

# Replication connections and slots
max_wal_senders = 10
max_replication_slots = 10

# Extra local WAL cushion for standbys without a slot
wal_keep_size = 2GB

# Protect against unlimited retention by an abandoned slot
max_slot_wal_keep_size = 20GB

# Continuous WAL archive for recovery
archive_mode = on
archive_timeout = 300s
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'

# Checkpoint sizing (not a retention cap)
max_wal_size = 8GB
min_wal_size = 1GB
```

Các con số không phải cấu hình khuyến nghị chung. Tính theo peak WAL rate, số standbys, outage budget, archive throughput, disk và backup policy.

### 28.1. Replication role

Tạo role có quyền replication theo least privilege:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
```

Password trong ví dụ chỉ minh họa; production phải dùng secrets management và chính sách xác thực phù hợp. Hạn chế nguồn truy cập trong pg_hba.conf và dùng TLS khi phù hợp.

### 28.2. Kiểm tra config

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
SHOW archive_mode;
SHOW archive_timeout;
```

### 28.3. Thay đổi cần restart

wal_level, archive_mode, max_wal_senders và max_replication_slots là các setting cần restart PostgreSQL để áp dụng. Nhiều setting khác như retention/checkpoint/archive command có thể reload theo context của phiên bản. Xác minh pg_settings.context và pending_restart thay vì giả định.

## 29. Cấu hình logical replication

Nếu cùng primary cần physical standby và logical CDC:

```conf
wal_level = logical
max_wal_senders = 20
max_replication_slots = 20

wal_keep_size = 2GB
max_slot_wal_keep_size = 40GB

archive_mode = on
archive_command = '/usr/local/bin/archive_wal.sh "%p" "%f"'
```

Tăng số sender/slot dựa trên tổng physical standbys, logical subscriptions, table sync workers và CDC clients.

### 29.1. Tạo publication

```sql
CREATE PUBLICATION customer_changes
FOR TABLE app.customers, app.customer_addresses;
```

### 29.2. Tạo subscription

```sql
CREATE SUBSCRIPTION customer_changes_sub
CONNECTION 'host=publisher.example.internal dbname=app user=logical_reader'
PUBLICATION customer_changes;
```

Ví dụ này giả định subscriber có bảng tương thích, kết nối được xác thực và role được cấp quyền. Cần thiết kế initial copy, ownership và DDL separately.

### 29.3. Kiểm tra slot được tạo

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

### 29.4. Cẩn trọng với nhiều consumers

Một logical slot không nên được chia sẻ tùy tiện giữa hai consumer độc lập vì chúng có thể tranh tiến độ và semantics acknowledgement. Mỗi pipeline cần lifecycle và ownership rõ.

## 30. Theo dõi physical replication trên primary

View pg_stat_replication cho biết các WAL sender đang kết nối tới standby.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

### 30.1. Các LSN

- sent_lsn: WAL đã được gửi tới standby.
- write_lsn: standby báo đã ghi WAL tới vị trí.
- flush_lsn: standby báo đã flush WAL bền vững tới vị trí.
- replay_lsn: standby đã replay tới vị trí.

Khoảng cách giữa các LSN giúp xác định lag đang nằm ở network, write/flush hay replay.

### 30.2. Lag theo bytes

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
```

Các phép trừ cần xử lý NULL khi standby chưa có vị trí tương ứng. Đây là chênh lệch LSN tại thời điểm quan sát, không trực tiếp là thời gian lag.

### 30.3. Lag time columns

write_lag, flush_lag, replay_lag là thống kê độ trễ theo những lần ghi/flush/replay gần nhất, không phải lúc nào cũng biểu diễn chính xác khoảng thời gian consumer đang offline. Kết hợp LSN delta và thời gian.

## 31. Theo dõi replication trên standby

Trên standby:

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
```

View có thể không có row khi standby không có WAL receiver đang hoạt động.

### 31.1. Replay location

```sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
```

Các hàm này phù hợp cho standby; tên hàm ở phiên bản cũ có thể dùng tên xlog.

### 31.2. Không chỉ dựa vào timestamp cuối

Nếu primary ít ghi, timestamp replay cuối có thể cũ dù standby hoàn toàn bắt kịp. Dùng LSN gap và WAL activity để hiểu đúng.

### 31.3. Hot standby feedback

hot_standby_feedback có thể giảm conflict do cleanup trên primary đối với query chạy trên standby, nhưng có thể giữ lại dead tuples trên primary và tăng bloat. Đây không phải tham số giữ WAL trực tiếp; nó ảnh hưởng retention của row versions và vacuum.

## 32. Theo dõi replication slots

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
```

Một số cột như wal_status và safe_wal_size chỉ có trên các phiên bản hỗ trợ. Nếu query không chạy trên major version cũ, kiểm tra schema view và loại bỏ các cột chưa tồn tại.

### 32.1. Tính WAL bytes slot đang giữ

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL
ORDER BY pg_wal_lsn_diff(
    pg_current_wal_lsn(), restart_lsn
) DESC;
```

Đây là ước lượng khoảng cách từ current WAL tới restart_lsn, không phải phép đo chính xác bytes độc quyền của slot. Một số WAL segments có thể còn cần cho nhiều consumers và checkpoint/archive.

### 32.2. Tìm slot inactive lâu

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE NOT active
ORDER BY restart_lsn NULLS FIRST;
```

Không drop mọi inactive slots một cách tự động. Xác minh owner/consumer trước.

### 32.3. Slot bị invalidated

Trên phiên bản có wal_status, trạng thái có thể cho biết slot còn WAL cần thiết hay đã mất một phần segment. Kiểm tra safe_wal_size, server logs và trạng thái consumer; không suy luận chỉ từ active.

## 33. Theo dõi WAL archive

pg_stat_archiver cung cấp thống kê archive:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

### 33.1. failed_count tăng

Có thể do archive destination không truy cập được, credentials/permissions hết hạn, storage hết dung lượng, network/object storage timeout, script archive trả exit code sai hoặc file đích xung đột/checksum mismatch.

### 33.2. archived_count không tăng

Không luôn có nghĩa lỗi: nếu workload không tạo WAL segment mới hoặc chưa switch segment, archiver có thể chưa có việc. Đối chiếu WAL activity và archive_timeout.

### 33.3. Archive backlog

Theo dõi số WAL files trong pg_wal đang chờ archive, disk usage và thời gian từ last successful archive. Một archive command chạy lâu có thể làm WAL backlog tăng.

## 34. Đo dung lượng pg_wal

Trên PostgreSQL có hàm pg_ls_waldir():

```sql
SELECT
    count(*) AS wal_file_count,
    pg_size_pretty(sum(size)) AS wal_directory_size
FROM pg_ls_waldir();
```

Hàm này cần quyền phù hợp trên server. Dữ liệu là kích thước các files trong WAL directory tại thời điểm truy vấn.

### 34.1. Không coi tổng file count là retained WAL duy nhất

Directory có thể chứa segment đã recycle hoặc các files khác liên quan WAL management. Cần kết hợp slots, archive status, checkpoint và filesystem metrics.

### 34.2. Theo dõi filesystem

pg_ls_waldir() không thay df/volume metrics. Nếu pg_wal nằm trên symlink hoặc mount riêng, phải theo dõi đúng filesystem chứa nó.

### 34.3. Alert theo dung lượng và tốc độ tăng

Alert khi filesystem vượt ngưỡng capacity, WAL directory tăng liên tục, inactive slot giữ WAL vượt budget, archive failures kéo dài hoặc replica lag vượt outage budget.

## 35. Theo dõi WAL generation rate

Trên các phiên bản có pg_stat_wal:

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    wal_buffers_full,
    stats_reset
FROM pg_stat_wal;
```

### 35.1. Tính rate bằng hai mẫu

```text
rate_bytes_per_second
  = (wal_bytes_sample_2 - wal_bytes_sample_1)
    / elapsed_seconds
```

Nếu server restart hoặc statistics reset giữa hai mẫu, delta có thể âm hoặc không hợp lệ. Cần kiểm tra stats_reset.

### 35.2. Peak rate

Lưu time series theo khoảng ngắn phù hợp, ví dụ 1 phút hoặc 5 phút, rồi tính percentile cao và peak theo ngày/tuần. Không chỉ dùng một average toàn tháng.

### 35.3. WAL generation khác archive throughput

Nếu generation 50 MB/s nhưng archive chỉ xử lý 20 MB/s, backlog tăng khoảng 30 MB/s trong thời gian đó. Khi kéo dài, pg_wal có thể cạn disk nếu archive failure/slot giữ segment.

## 36. Monitoring dashboard nên có gì?

| Nhóm | Metrics |
| --- | --- |
| WAL production | WAL bytes/s, records/s, full-page images |
| Local storage | pg_wal bytes, filesystem free space, growth rate |
| Checkpoint | Checkpoint frequency/duration và write pressure |
| Archive | archived_count, failed_count, last success age, backlog |
| Physical replication | sent/write/flush/replay LSN, byte lag, time lag |
| Slots | active, restart_lsn, confirmed_flush_lsn, retained estimate, safe_wal_size |
| Standby | receive/replay positions, receiver state, recovery conflicts |
| DR | archive completeness, last successful base backup, restore test age |
| Logical CDC | consumer lag, slot age, apply rate, last acknowledged LSN |

### 36.1. Alert phải phản ánh budget

Nếu hệ thống chấp nhận standby offline tối đa 30 phút, alert khi lag vượt 10 phút có thể hợp lý. Nếu CDC được phép trễ 12 giờ, alert threshold khác.

### 36.2. Alert sớm hơn disk full

Đừng đợi filesystem 95–100% mới hành động. Cần cảnh báo theo tốc độ tăng WAL và thời gian còn lại trước khi đầy.

### 36.3. Correlate metrics

pg_wal tăng có thể do slot, archive failure, wal_keep_size hoặc workload burst. Dashboard nên đặt các số liệu cạnh nhau để xác định retention owner.

## 37. Kịch bản: physical standby offline lâu

Giả sử standby dùng physical slot, standby mất kết nối 4 giờ và primary tiếp tục ghi dữ liệu.

### 37.1. Nếu slot không giới hạn

Primary giữ WAL cần thiết cho standby. Khả năng resume tốt hơn, nhưng disk usage tăng theo WAL generation rate trong suốt 4 giờ và có thể tiếp tục tăng nếu standby không trở lại.

### 37.2. Nếu max_slot_wal_keep_size có cap

Nếu WAL cần giữ vượt cap, PostgreSQL có thể loại bỏ segment cũ ở checkpoint và slot có thể không còn usable. Khi standby quay lại, nó có thể cần reinitialize.

### 37.3. Nếu không dùng slot

Standby có thể cần segment còn trong wal_keep_size hoặc archive. Nếu cả hai không có, cần base backup mới.

### 37.4. Quyết định

Đặt retention theo outage budget, có cap để bảo vệ primary và có runbook rebuild standby. Không đặt unlimited slots mà không có disk alert.

## 38. Kịch bản: logical CDC consumer bị treo

Một CDC consumer có thể dừng vì Kafka/topic downstream unavailable, credential hết hạn, connector crash, schema change không được xử lý hoặc consumer không commit/acknowledge LSN.

### 38.1. Tác động

Logical slot giữ WAL từ restart_lsn và có thể giữ catalog history. Primary vẫn tạo WAL mới; disk tăng dù database workload không bất thường.

### 38.2. Chẩn đoán

1. Xác định slot owner và connector.
2. Xem active state.
3. So restart_lsn và confirmed_flush_lsn.
4. Tính retained WAL estimate.
5. Kiểm tra consumer logs/last acknowledged position.
6. Xác nhận downstream có thể resume.

### 38.3. Khôi phục

Khởi động lại consumer nếu còn WAL. Nếu slot invalidated/mất WAL, có thể phải tạo slot mới và bootstrap/snapshot lại theo khả năng của CDC tool.

### 38.4. Không drop slot trước khi quyết định resnapshot

Drop slot có thể giải phóng retention nhưng consumer sẽ mất vị trí đã theo dõi. Ghi lại LSN, schema, snapshot requirements và downstream recovery plan trước.

## 39. Kịch bản: archive command thất bại

Nếu archive_command trả lỗi, PostgreSQL sẽ thử archive lại segment. WAL chưa archive có thể không được recycle như bình thường.

### 39.1. Triệu chứng

- pg_stat_archiver.failed_count tăng.
- last_failed_time gần đây.
- pg_wal tăng.
- Logs ghi archive command failure.
- Filesystem còn ít chỗ.

### 39.2. Hành động

1. Kiểm tra đích archive/network/credentials.
2. Kiểm tra exit code và logs của script.
3. Xác minh segment chưa archive có còn tồn tại.
4. Khôi phục storage/network.
5. Để PostgreSQL retry theo cơ chế archive.
6. Theo dõi archive backlog giảm và disk ổn định.

### 39.3. Không xóa segment chưa archive

Xóa file để lấy chỗ có thể phá hỏng archive chain và recovery. Cần khôi phục đích archive hoặc mở rộng storage, không tự xóa WAL đang được PostgreSQL quản lý.

## 40. Kịch bản: pg_wal sắp đầy

```text
pg_wal growth
   |
   +--> inactive replication slot?
   |
   +--> archive failures/backlog?
   |
   +--> standby lag / missing consumer?
   |
   +--> wal_keep_size quá lớn?
   |
   +--> workload WAL burst / checkpoint behavior?
```

### 40.1. Các bước điều tra

1. Xem filesystem free space và growth rate.
2. Đọc pg_replication_slots và retained estimates.
3. Đọc pg_stat_archiver.
4. Đọc pg_stat_replication.
5. Đọc pg_stat_wal nếu có.
6. Xác định segment nào còn cần và vì sao.

### 40.2. Các biện pháp

- Khôi phục consumer/standby nếu còn khả năng resume.
- Khôi phục archive destination nếu archive bị lỗi.
- Drop slot chỉ khi owner xác nhận consumer không còn cần.
- Điều chỉnh retention cap theo policy và hiểu rõ khả năng slot bị invalidated.
- Mở rộng disk khi cần thiết.
- Giảm workload/bulk operation nếu WAL generation đang vượt capacity.

### 40.3. Không chạy rm trong pg_wal

Không xóa segment thủ công, không sửa tên file và không tạo file giả để đánh lừa PostgreSQL.

## 41. Thay đổi wal_level trên cluster đang chạy

wal_level là server-start setting. Đổi trong postgresql.conf hoặc ALTER SYSTEM không làm giá trị runtime đổi ngay; cần restart PostgreSQL.

### 41.1. Xem giá trị và trạng thái restart

```sql
SELECT
    name,
    setting,
    context,
    pending_restart,
    source,
    sourcefile,
    sourceline
FROM pg_settings
WHERE name = 'wal_level';
```

### 41.2. Nâng replica lên logical

Trước khi restart:

- Kiểm tra logical consumers và slot capacity.
- Tính WAL generation/retention.
- Tăng sender/slot limits phù hợp.
- Xác định thời gian restart/failover.
- Xác minh archive và backup chain.
- Kiểm tra phiên bản PostgreSQL/CDC tool tương thích.

Sau restart, xác nhận SHOW wal_level trả logical, tạo publication/slot và test consumer.

### 41.3. Hạ logical xuống replica

Không hạ nếu còn logical subscriptions/slots/CDC consumers cần logical decoding. Xác nhận consumer đã dừng, dữ liệu downstream đã đồng bộ, slot lifecycle được xử lý và có thể chấp nhận mất khả năng logical decode từ WAL mới.

### 41.4. Hạ về minimal

Chỉ phù hợp khi không cần archive, PITR, hot standby, physical replication hoặc logical decoding. Đây thường không phải lựa chọn cho production database có yêu cầu disaster recovery.

### 41.5. Downgrade wal_level không hồi tố

Sau khi hạ mức, WAL mới không chứa thông tin logical cần thiết. Không thể bật logical sau này rồi giải mã ngược các segment cũ vốn được ghi ở mức replica/minimal.

## 42. Failover và replication slots

Khi primary failover, replication slots cần được quản lý cẩn thận.

### 42.1. Slot có tồn tại trên standby không?

Physical standby có thể được cấu hình để đồng bộ/đồng hành slot theo các tính năng và phiên bản phù hợp; logical slot failover có các yêu cầu riêng theo phiên bản PostgreSQL và cách cấu hình. Không giả định mọi slot tự xuất hiện trên node mới.

### 42.2. Failover logical consumers

CDC consumer cần biết publisher mới, slot mới hoặc failover slot phù hợp và vị trí tiếp tục. Nếu không, có thể mất changes hoặc phát lại duplicates.

### 42.3. Kiểm tra phiên bản

Các tính năng như synchronized logical failover slots phát triển theo major versions. Đọc tài liệu của đúng phiên bản thay vì áp dụng cấu hình của một bản mới lên cluster cũ.

### 42.4. Failover không giải quyết archive continuity

DR design vẫn cần bảo đảm base backup và WAL archive phù hợp. Một primary mới không tự có toàn bộ lịch sử WAL đã archive trên node cũ nếu storage architecture không chia sẻ/replicate archive.

## 43. archive_mode, archive_command và standby

Một standby ở recovery có thể restore WAL từ archive qua restore_command, hoặc nhận qua streaming. Khi cấu hình archive_mode=always, standby có thể archive WAL nhận được theo semantics của mode này.

### 43.1. Phân biệt restore và archive

- restore_command: lấy một segment từ archive về để recovery/replay.
- archive_command: đẩy một segment đã hoàn tất ra archive.

Đây là hai hướng dữ liệu khác nhau.

### 43.2. Archive loop

Không thiết kế archive_command để ghi lại segment vào chính nơi restore_command lấy theo cách tạo vòng lặp/xung đột. Tổ chức namespace và retention rõ ràng.

### 43.3. Shared archive

Nếu primary và nhiều standbys cùng ghi archive, phải có cơ chế bảo đảm cùng WAL history và idempotent writes. Không cho nhiều clusters độc lập ghi file cùng tên vào cùng namespace.

## 44. synchronous_commit và độ bền của commit

WAL retention thường bị nhầm với durability. Chúng khác nhau:

- synchronous_commit xác định khi nào COMMIT có thể trả thành công theo mức chờ WAL.
- synchronous_standby_names xác định synchronous standbys.
- wal_level xác định thông tin WAL được ghi.
- Retention quyết định WAL cũ có được giữ cho consumers/recovery không.

Ví dụ:

```sql
SHOW synchronous_commit;
SHOW synchronous_standby_names;
```

### 44.1. Local durability

Primary có thể flush WAL local rồi xác nhận commit, trong khi asynchronous standby chưa replay. Điều này có thể tạo một khoảng dữ liệu mất nếu primary mất và failover sang standby chưa nhận/replay.

### 44.2. Synchronous durability

Chờ standby theo cấu hình có thể giảm RPO cho những commits được xác nhận, nhưng tăng latency và phụ thuộc standby.

### 44.3. Archive không phải synchronous standby

Archive command thường chạy sau khi segment được switch; không phải mỗi COMMIT đều đợi archive hoàn tất. Đừng dùng WAL archive như cơ chế synchronous replication.

## 45. Backup và PITR: retention theo recovery window

Một policy backup có thể yêu cầu:

- Daily base backups trong 14 ngày.
- WAL archive liên tục để PITR tới mọi thời điểm trong 14 ngày.
- Một bản backup monthly giữ lâu hơn.

Đây chỉ là ví dụ policy, không phải quy tắc chung.

### 45.1. Xác định WAL cần giữ

Đối với mỗi base backup, xác định backup start/stop LSN hoặc metadata backup tool, WAL segment đầu tiên cần để hoàn tất backup, WAL liên tục tới recovery target được phép và timeline history files khi có failover/promote.

### 45.2. Timeline

Sau promote/failover, PostgreSQL có thể chuyển sang timeline mới. Recovery archive cần giữ các timeline history files và WAL segment phù hợp; không chỉ dựa trên tên segment mà bỏ qua timeline history.

### 45.3. Restore test

Backup chưa được restore test là một giả định. Định kỳ khôi phục vào môi trường cô lập, replay WAL và xác minh dữ liệu/ứng dụng tới recovery target.

### 45.4. Archive retention

Chỉ xóa WAL khi chắc chắn không còn base backup, standby, DR workflow hoặc PITR target nào cần nó. Dùng backup catalog/retention manager thay vì lệnh xóa file thủ công.

## 46. Version-specific settings và migration

Các phiên bản PostgreSQL khác nhau có thể khác:

- Tên tham số retention (wal_keep_segments ở bản cũ, wal_keep_size ở bản mới).
- Các cột của pg_replication_slots.
- Logical failover slot features.
- Các view thống kê WAL/checkpoint.
- Cách cấu hình archive library/command.
- Các chi tiết protocol và replication behavior.

### 46.1. Đọc server thực tế

```sql
SELECT version();

SHOW wal_level;
SHOW wal_keep_size;
SHOW max_slot_wal_keep_size;
SHOW archive_mode;
```

Nếu SHOW báo unknown parameter, không thêm setting một cách mù quáng; xác định version và tài liệu tương ứng.

### 46.2. Xem parameter context

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name LIKE '%wal%'
   OR name LIKE '%replication%'
   OR name LIKE '%archive%'
ORDER BY name;
```

### 46.3. Major upgrade

Khi major upgrade, kiểm tra replication compatibility, slots, logical decoding plugin, archive tooling và backup/restore procedure. Không mặc định slot cũ có thể được chuyển sang cluster mới mà không cần xử lý.

## 47. Bảo mật WAL và replication

WAL có thể chứa thông tin dữ liệu nhạy cảm ở mức storage. Bảo vệ:

- Network replication connections bằng private network/TLS.
- pg_hba.conf chỉ cho phép hosts/users cần thiết.
- Replication role có quyền tối thiểu.
- Archive storage có encryption, access control và audit.
- Slot management chỉ cho role vận hành có quyền phù hợp.
- Không expose replication protocol ra mạng công cộng tùy tiện.
- Backup/WAL archives được bảo vệ như database backup.

### 47.1. Replication password

Không đặt password thật trong command line, Git, tài liệu hoặc logs. Dùng .pgpass với permission phù hợp hoặc secret manager/orchestration system.

### 47.2. Archive script

Script archive chạy trên host PostgreSQL với quyền OS của service. Không lấy command/path tùy ý từ client hoặc file không tin cậy.

### 47.3. CDC data

Logical decoding có thể xuất các row changes tới hệ thống khác. Consumer phải được quản lý như một data export channel, có authorization, masking và retention phù hợp.

## 48. Runbook: standby không thể resume streaming

1. Ghi lại primary/standby LSN và timeline.
2. Kiểm tra lỗi trong PostgreSQL logs ở cả hai node.
3. Xác định standby cần WAL segment nào.
4. Kiểm tra physical slot và restart_lsn.
5. Kiểm tra wal_keep_size và pg_wal hiện tại.
6. Kiểm tra WAL archive có segment/timeline history cần thiết không.
7. Nếu WAL còn, khôi phục kết nối/slot/restore path và để standby bắt kịp.
8. Nếu WAL đã mất, đánh giá tạo lại standby từ base backup mới.
9. Kiểm tra replica lag và disk trong khi catch-up.
10. Điều chỉnh outage budget/retention/alert để ngăn lặp lại.

Không drop slot hoặc xóa WAL trước khi xác định recovery path.

## 49. Runbook: logical slot giữ WAL quá nhiều

1. Xác định slot name, database, owner và CDC connector.
2. Kiểm tra active, restart_lsn, confirmed_flush_lsn, catalog_xmin.
3. Ước lượng WAL bytes cần giữ.
4. Kiểm tra consumer logs và downstream availability.
5. Khởi động lại consumer nếu còn WAL.
6. Nếu slot invalidated, lập kế hoạch snapshot/resnapshot hoặc rebootstrap.
7. Chỉ drop slot khi xác nhận consumer không còn cần lịch sử đó.
8. Theo dõi pg_wal giảm sau khi retention requirement được giải phóng.
9. Thiết lập max_slot_wal_keep_size, alert và slot owner inventory.

## 50. Runbook: archive backlog hoặc archive failure

1. Đọc pg_stat_archiver và PostgreSQL logs.
2. Xác định archive command/host/storage đang lỗi.
3. Kiểm tra credentials, permissions, network, quota và disk.
4. Kiểm tra file segment đích đã tồn tại và checksum có khớp không.
5. Khôi phục archive destination.
6. Để PostgreSQL retry; không xóa segment chưa archive.
7. Theo dõi failed_count ngừng tăng, archived_count tăng và backlog giảm.
8. Kiểm tra archive completeness bằng backup/restore tooling.
9. Điều chỉnh capacity và alert.

## 51. Runbook: pg_wal tăng nhanh

1. Xem filesystem free space và tốc độ tăng.
2. Đọc pg_replication_slots tìm restart_lsn cũ/inactive slots.
3. Đọc pg_stat_replication tìm standby lag.
4. Đọc pg_stat_archiver tìm archive failure.
5. Đọc pg_stat_wal để đo generation rate.
6. Xác định retention owner và thời gian outage.
7. Khôi phục consumer/archive nếu có thể.
8. Mở rộng storage hoặc giảm tải có kiểm soát khi cần.
9. Drop slot chỉ theo quyết định có hiểu rõ hậu quả.
10. Không xóa files thủ công trong pg_wal.

## 52. Runbook: thay đổi wal_level

1. Xác định loại replication/CDC mới sẽ dùng.
2. Xác nhận PostgreSQL version và tính năng hỗ trợ.
3. Kiểm tra current slots/subscriptions/standbys.
4. Ước lượng WAL generation và retention mới.
5. Tính max_wal_senders/max_replication_slots.
6. Kiểm tra disk, archive và backup capacity.
7. Chuẩn bị restart/failover window.
8. Thay config và restart theo quy trình HA.
9. Xác nhận runtime SHOW wal_level.
10. Test physical standby, logical consumer và PITR/archive tùy nhu cầu.
11. Theo dõi WAL, slot lag, archive và application errors.

## 53. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Dùng minimal cho primary cần standby | Không hỗ trợ physical replication | replica hoặc logical |
| Dùng minimal rồi mong PITR | Không có WAL archive phù hợp | wal_level=replica trở lên |
| Nghĩ logical tự tạo CDC | Không có publication/slot/consumer | Cấu hình pipeline riêng |
| Nghĩ wal_level quyết định retention | WAL đủ thông tin nhưng bị thu hồi | Thiết kế retention riêng |
| Chỉ tăng wal_keep_size cho outage dài | Vẫn có thể mất segment | Slot/archive và sizing theo outage |
| Dùng slot không giới hạn | Inactive slot có thể làm đầy disk | Cap, alert, lifecycle |
| Drop slot để giải phóng disk mà không hỏi owner | Consumer mất WAL cần thiết | Xác minh/rebootstrap plan |
| Coi max_wal_size là hard cap | pg_wal vẫn có thể lớn hơn | Theo dõi slot/archive/keep |
| Coi min_wal_size là standby retention | Không bảo đảm LSN resume | Dùng slot/archive |
| Archive command trả 0 trước khi upload xong | WAL bị coi là archive thành công dù chưa bền vững | Chỉ exit 0 sau khi lưu chắc chắn |
| Archive command không idempotent | Retry gây ghi đè/xung đột | Kiểm tra file tồn tại và checksum |
| Đặt archive cùng filesystem đầy | Archive không giải quyết capacity | Storage riêng và alert |
| Giữ archive vô hạn không policy | Chi phí tăng không kiểm soát | Backup-aware retention |
| Xóa archive theo standby hiện tại | Phá PITR backup chain | Xét mọi backup/recovery consumers |
| Dùng archive_timeout cực thấp | Nhiều file/chi phí archive | Chọn theo RPO |
| Nghĩ archive tương đương synchronous commit | Không bảo đảm mỗi commit đã archive | Phân biệt archive và sync replication |
| Không theo dõi logical restart_lsn | Slot giữ WAL lâu | Monitor restart_lsn/consumer lag |
| Chỉ nhìn confirmed_flush_lsn | Bỏ qua restart_lsn/catalog_xmin | Theo dõi đầy đủ slot state |
| Cho rằng inactive slot không giữ WAL | Disk vẫn tăng | Audit inactive slots |
| Không tính peak WAL rate | Retention thiếu khi burst | Dùng peak/percentile + headroom |
| Đổi wal_level mà không restart | Runtime vẫn ở mức cũ | Kiểm tra pending_restart |
| Hạ wal_level khi CDC còn chạy | Logical decoding không tiếp tục | Dừng/di chuyển consumers trước |
| Nghĩ synchronous_standby_names là wal_level | Nhầm cơ chế commit ack | Cấu hình hai lớp riêng |
| Nghĩ standby đang chạy là backup | Lỗi dữ liệu có thể replicate | Base backup + WAL archive + restore test |
| Xóa WAL bằng rm | Phá recovery/replication | Để PostgreSQL quản lý segment |

## 54. Bài tập thực hành PostgreSQL

Thực hiện trên cluster lab/staging có quyền quản trị phù hợp. Những bài thay đổi wal_level/archive/replication cần restart hoặc có thể ảnh hưởng cluster; không chạy tùy tiện trên production.

1. **WAL:** giải thích write-ahead logging và vì sao WAL được flush trước data pages.
2. **Crash recovery:** mô tả vai trò redo WAL sau crash.
3. **WAL vs SQL log:** giải thích vì sao WAL không phải bản ghi SQL statements.
4. **LSN:** truy vấn pg_current_wal_lsn() và giải thích định dạng.
5. **LSN diff:** dùng pg_wal_lsn_diff tính khoảng cách hai vị trí.
6. **Segments:** tìm thư mục pg_wal và giải thích segment files.
7. **WAL generation:** liệt kê những workload có thể làm WAL tăng mạnh.
8. **wal_level:** so sánh minimal, replica và logical.
9. **Minimal:** giải thích vì sao minimal không dùng cho PITR/standby.
10. **Replica:** nêu các tính năng được hỗ trợ ở replica.
11. **Logical:** giải thích logical decoding cần thông tin bổ sung gì ở mức khái niệm.
12. **Selection:** chọn wal_level cho hệ thống chỉ crash recovery.
13. **Selection:** chọn wal_level cho physical standby và PITR.
14. **Selection:** chọn wal_level cho physical HA cộng CDC.
15. **Retention:** phân biệt WAL generation và retention.
16. **Archive:** giải thích archive là copy segment ra storage khác.
17. **Recycle:** phân biệt recycle WAL segment và archive WAL segment.
18. **wal_keep_size:** cấu hình 2GB và giải thích đó không phải 2 giờ.
19. **Legacy:** tìm hiểu wal_keep_segments trên PostgreSQL cũ.
20. **Replication slot:** tạo physical slot trên lab.
21. **Physical slot:** cấu hình primary_slot_name ở standby.
22. **Logical slot:** tạo logical slot dùng pgoutput.
23. **Inactive slot:** giải thích vì sao inactive slot vẫn giữ WAL.
24. **Slot lifecycle:** lập inventory slot và owner.
25. **restart_lsn:** giải thích WAL cần giữ từ vị trí này.
26. **confirmed_flush_lsn:** giải thích khác biệt với restart_lsn.
27. **catalog_xmin:** nêu tác động của logical slot tới catalog vacuum.
28. **Slot cap:** cấu hình max_slot_wal_keep_size và mô tả trade-off.
29. **Slot invalidation:** giải thích standby/CDC phải làm gì khi slot mất WAL.
30. **max_wal_size:** chứng minh nó không phải hard cap của pg_wal.
31. **min_wal_size:** giải thích recycling và retention khác nhau.
32. **Checkpoint:** phân biệt checkpoint với archive/slot retention.
33. **Archive mode:** bật archive_mode và xác định yêu cầu restart.
34. **Archive command:** viết script archive nhận source path và segment name.
35. **Idempotency:** thiết kế archive command xử lý retry và file đã tồn tại.
36. **Exit code:** giải thích vì sao không trả success trước khi object storage upload bền vững.
37. **Archive timeout:** cấu hình 300 giây và phân tích archive volume.
38. **Archive mode always:** mô tả khi nào standby có thể cần archive WAL nhận được.
39. **Cleanup:** tìm hiểu pg_archivecleanup và điều kiện dùng an toàn.
40. **PITR:** mô tả base backup + WAL chain.
41. **Restore command:** viết lệnh khái niệm lấy WAL segment từ archive.
42. **Recovery target:** giải thích target time/LSN trong PITR.
43. **Timeline:** mô tả vai trò timeline history sau promote.
44. **Physical replication:** liệt kê yêu cầu primary/standby.
45. **No slot:** mô tả cách standby lấy WAL và tình huống cần rebuild.
46. **Cascading:** vẽ primary → standby A → standby B.
47. **Synchronous:** phân biệt synchronous_standby_names với wal_level.
48. **Commit:** so synchronous_commit on và remote_apply ở mức semantics.
49. **Logical:** tạo publication cho hai bảng lab.
50. **Replica identity:** kiểm tra primary key và REPLICA IDENTITY.
51. **REPLICA IDENTITY FULL:** phân tích WAL/apply cost.
52. **Native subscription:** tạo subscriber trong lab và kiểm tra slot.
53. **CDC:** thiết kế logical slot consumer với checkpoint/acknowledgment.
54. **Mixed consumers:** tính slots/senders cho 3 standbys và 4 CDC connectors.
55. **Sizing:** tính WAL cần giữ với peak 10 MB/s và outage 2 giờ.
56. **Sizing:** tính WAL cần giữ với peak 20 MB/s và outage 6 giờ.
57. **Headroom:** đề xuất buffer trên con số tính toán.
58. **Generation rate:** đọc pg_stat_wal hai lần và tính bytes/second.
59. **Stats reset:** giải thích vì sao delta không hợp lệ nếu stats_reset thay đổi.
60. **Primary view:** truy vấn pg_stat_replication và đọc sent/write/flush/replay LSN.
61. **Standby view:** truy vấn pg_stat_wal_receiver.
62. **Replay:** đọc pg_last_wal_receive_lsn và pg_last_wal_replay_lsn.
63. **Slot monitor:** truy vấn pg_replication_slots và sắp theo retained estimate.
64. **Archive monitor:** đọc pg_stat_archiver và phân tích failed_count.
65. **Directory size:** dùng pg_ls_waldir tính tổng bytes trong pg_wal.
66. **Disk alert:** thiết kế alert theo filesystem free space và WAL growth rate.
67. **Archive failure:** mô phỏng archive destination lỗi trên lab và quan sát retry.
68. **Inactive slot:** mô phỏng consumer dừng và quan sát retained WAL.
69. **Slot recovery:** lập plan resnapshot khi logical slot invalidated.
70. **Standby outage:** mô tả ba recovery paths: slot, archive, new base backup.
71. **wal_level restart:** kiểm tra pg_settings.context và pending_restart.
72. **Upgrade:** liệt kê các điểm cần kiểm tra khi major upgrade cluster có logical slots.
73. **Failover:** mô tả cách consumer biết publisher mới và LSN tiếp tục.
74. **Archive retention:** thiết kế giữ WAL theo base backup/PITR window.
75. **Security:** thiết kế quyền cho replication role và archive storage.
76. **Runbook:** viết quy trình khi pg_wal tăng nhanh.
77. **Runbook:** viết quy trình khi archive backlog kéo dài.
78. **Runbook:** viết quy trình khi physical standby không thể resume.
79. **Runbook:** viết quy trình khi CDC slot giữ WAL quá budget.
80. **Thiết kế tổng hợp:** chọn wal_level, slot/archive/keep limits, sender/slot capacity, backup/PITR retention, monitoring và failover strategy cho hệ thống có physical HA và logical CDC.

## 55. Checklist trước khi triển khai

### Nhu cầu replication và recovery

- [ ] Đã liệt kê crash recovery, PITR, physical standby, cascading và logical CDC consumers.
- [ ] wal_level được chọn theo consumer cần nhiều thông tin nhất.
- [ ] Không dùng minimal nếu cần archive, PITR hoặc replication.
- [ ] Có base backup và WAL archive đầy đủ cho recovery target.
- [ ] Có restore test thực tế.

### Retention và capacity

- [ ] Đã đo peak WAL generation rate.
- [ ] Đã xác định outage budget của từng standby/CDC consumer.
- [ ] wal_keep_size được chọn theo buffer mong muốn.
- [ ] Replication slots có owner và lifecycle.
- [ ] max_slot_wal_keep_size được chọn theo disk budget và resnapshot policy.
- [ ] max_wal_size không bị coi là hard cap.
- [ ] Có headroom cho WAL burst, archive backlog và replication slots.

### Archiving

- [ ] archive_mode/archive_command được kiểm tra.
- [ ] Archive command chỉ báo success khi segment lưu bền vững.
- [ ] Retry idempotent và checksum/file collision được xử lý.
- [ ] Archive destination có capacity, security và monitoring.
- [ ] archive_timeout phù hợp RPO và chi phí file.
- [ ] Cleanup không xóa WAL cần cho bất kỳ base backup/standby nào.

### Replication

- [ ] max_wal_senders/max_replication_slots đủ capacity.
- [ ] Physical standbys có slot/archive recovery path phù hợp.
- [ ] Logical tables có replica identity đúng.
- [ ] CDC consumers theo dõi LSN và xác nhận tiến độ.
- [ ] Synchronous/asynchronous policy rõ ràng.
- [ ] Failover slot/consumer recovery được thử nghiệm theo version.

### Monitoring và vận hành

- [ ] Có dashboard WAL bytes/s và pg_wal disk usage.
- [ ] Có alert archive failure/backlog.
- [ ] Có alert inactive slots và retained WAL.
- [ ] Có alert physical/logical consumer lag.
- [ ] Có runbook disk pressure, slot invalidation và standby rebuild.
- [ ] Có version-specific config/upgrade plan.
- [ ] Không xóa/sửa WAL files bằng filesystem commands thủ công.

## 56. Tổng kết

wal_level, retention và replication là ba phần của cùng một thiết kế nhưng có nhiệm vụ khác nhau:

```text
wal_level
  -> WAL chứa đủ thông tin cho loại consumer nào?

Retention
  -> WAL cũ được giữ tới đâu để consumer còn đọc?

Replication / Archiving
  -> Ai đọc WAL, đọc bằng cách nào và lưu ở đâu?
```

Những nguyên tắc quan trọng:

- **minimal** chỉ dành cho crash recovery cục bộ khi không cần archiving/replication; **replica** hỗ trợ physical replication và PITR; **logical** bổ sung thông tin cho logical decoding/CDC.
- **Chọn wal_level cao hơn không tự tạo hoặc bảo đảm consumer.** Publication, subscription, slot, sender, archive và backup vẫn cần cấu hình.
- **wal_keep_size là lượng WAL tối thiểu giữ thêm, không phải hard cap hoặc số giờ.**
- **Replication slots bảo vệ tiến độ consumer nhưng có thể làm đầy disk** nếu consumer ngừng hoạt động; max_slot_wal_keep_size đặt trade-off giữa disk safety và khả năng resume.
- **max_wal_size là mục tiêu mềm cho checkpoint**, không phải giới hạn tổng dung lượng pg_wal.
- **WAL archive cần base backup và retention policy** để phục vụ PITR. Archive thành công phải được xác nhận bền vững và retry an toàn.
- **Physical replication, logical CDC và PITR có yêu cầu retention khác nhau.** Hãy tính consumer outage budget riêng và quan sát consumer chậm nhất.
- **Đo WAL generation rate theo thời gian**, dùng peak/percentile và cộng headroom; không sizing chỉ bằng average hoặc một con số cố định.
- **Theo dõi pg_replication_slots, pg_stat_replication, pg_stat_wal_receiver, pg_stat_archiver và filesystem** để biết WAL được giữ vì lý do nào.
- **Không xóa WAL trong pg_wal bằng tay.** Khôi phục consumer/archive, mở rộng capacity hoặc drop slot chỉ sau khi hiểu hậu quả và có recovery plan.

Khi thiết kế đúng, PostgreSQL có thể vừa phục hồi tới thời điểm mong muốn, vừa giữ các physical standbys bắt kịp và cung cấp logical changes cho CDC mà không để WAL retention trở thành rủi ro đầy đĩa. Hãy bắt đầu từ **nhu cầu của từng consumer**, chuyển thành **outage/recovery budget**, rồi mới chọn wal_level, slot limits, wal_keep_size, archive và cảnh báo vận hành.
