# Timeline, promotion và lịch sử phục hồi trong PostgreSQL

Khi một PostgreSQL standby được promote thành primary, hoặc khi một cluster được khôi phục tới một thời điểm rồi tiếp tục nhận ghi mới, database bắt đầu một **timeline mới**. Timeline cho PostgreSQL biết WAL đang thuộc nhánh lịch sử nào, nhánh đó bắt đầu từ đâu và cần kết hợp WAL của những timeline cha nào để phục hồi đúng dữ liệu.

Hãy hình dung một primary có timeline 1. Standby nhận WAL và replay các thay đổi. Sau một sự cố, standby được promote tại LSN X. Từ điểm X, nó bắt đầu ghi WAL trên timeline 2. Timeline 2 kế thừa lịch sử timeline 1 tới điểm phân nhánh, rồi có các thay đổi riêng:

```text
Timeline 1:
Base backup ---- WAL ---- WAL ---- WAL ---- LSN X
                                            |
                                            | Promotion
                                            v
Timeline 2:                                 WAL ---- WAL ---- WAL
                                            |
                                            +-- Các thay đổi mới sau failover
```

Timeline không phải một bản backup, không phải transaction ID và cũng không phải audit log. Nó là **định danh một nhánh của lịch sử WAL**. PostgreSQL kết hợp timeline, WAL segments và timeline history files để chọn đúng chuỗi log trong crash recovery, standby recovery và Point-in-Time Recovery (PITR).

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Khôi phục**, tập trung vào **“Timeline, promotion và lịch sử phục hồi”**. Nội dung giải thích cách timeline hình thành, cách promotion tạo nhánh WAL mới, cách PITR chọn nhánh, cách standby theo timeline mới sau failover và cách đưa primary cũ quay lại cluster an toàn.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích timeline trong PostgreSQL và lý do cần phân biệt các nhánh WAL.
2. Phân biệt timeline ID, LSN, transaction ID, checkpoint và restore point.
3. Mô tả cấu trúc lịch sử dạng cây khi một standby được promote.
4. Giải thích fork point và quan hệ giữa timeline cha với timeline con.
5. Nhận diện WAL segment filename có chứa timeline ID.
6. Giải thích timeline history file và thông tin trong file .history.
7. Mô tả thời điểm PostgreSQL tạo timeline mới.
8. Phân biệt crash recovery thông thường với promotion.
9. Dùng hàm pg_promote() hoặc pg_ctl promote trong quy trình promotion.
10. Hiểu vai trò của recovery.signal và standby.signal trên PostgreSQL hiện đại.
11. Giải thích recovery_target_timeline với các lựa chọn current, latest và timeline ID cụ thể.
12. Phân biệt archive recovery, standby recovery và PITR.
13. Chọn đúng timeline khi khôi phục từ base backup và WAL archive có nhiều nhánh.
14. Hiểu vì sao timeline history files phải được archive và giữ lại.
15. Theo dõi primary/standby bằng LSN, timeline và replication statistics.
16. Giải thích asynchronous và synchronous replication ảnh hưởng thế nào tới failover data loss.
17. Nhận biết split brain và vai trò của fencing trong failover.
18. Đưa primary cũ trở lại cluster bằng pg_rewind hoặc tạo lại standby từ base backup.
19. Nêu các điều kiện tiên quyết và giới hạn của pg_rewind.
20. Lập kế hoạch backup, archive retention và PITR qua nhiều timeline.
21. Kiểm chứng recovery bằng restore drill, row checks và ứng dụng.
22. Thiết kế runbook failover, promotion, rejoin và rollback có kiểm soát.

**Phạm vi:** PostgreSQL hiện đại, đặc biệt các bản dùng standby.signal và recovery.signal (PostgreSQL 12 trở lên). Tên cột của statistics views, một số tham số và tùy chọn công cụ có thể khác theo major version. Hãy xác nhận tài liệu tương ứng với cluster thực tế trước khi vận hành.

---

## 2. Timeline giải quyết vấn đề gì?

WAL là một chuỗi thay đổi có thứ tự. Trong hoạt động bình thường, một primary tạo WAL liên tục. Standby nhận và replay WAL để theo kịp primary.

Khi standby được promote, nó có thể bắt đầu nhận ghi độc lập. Từ thời điểm đó, WAL mới không còn là phần tiếp nối duy nhất của primary cũ. Có thể tồn tại hai nhánh lịch sử khác nhau.

Ví dụ:

- Primary A đang ở timeline 1, WAL tới LSN 0/5000000.
- Standby B chỉ replay tới 0/4F00000.
- A gặp sự cố.
- B được promote và bắt đầu ghi WAL mới trên timeline 2.
- A cũ được khởi động lại mà không được đồng bộ về nhánh B, rồi tiếp tục ghi trên timeline 1.

Lúc này hai server có thể có dữ liệu khác nhau sau điểm phân nhánh. Timeline giúp PostgreSQL và công cụ phục hồi nhận biết các nhánh đó.

### 2.1. Timeline là nhãn của lịch sử WAL

Mỗi timeline có một ID số nguyên. Timeline ban đầu thường là timeline 1. Khi promotion tạo một nhánh mới, PostgreSQL cấp timeline ID mới và ghi lịch sử nhánh.

### 2.2. Timeline không phải phiên bản database

Timeline không đánh số phiên bản schema, transaction hay snapshot. Nó chỉ phân biệt lịch sử WAL của cluster.

### 2.3. Timeline không tự giải quyết xung đột

Timeline cho biết các nhánh khác nhau. Nó không tự merge dữ liệu của hai primary độc lập và không chọn primary có thẩm quyền cho hệ thống HA. Việc đó thuộc failover orchestration và quy trình vận hành.

### 2.4. Timeline không thay thế backup

Nếu mất toàn bộ data directory và không có base backup phù hợp, chỉ có timeline history files và WAL không đủ để dựng lại database từ đầu.

### 2.5. Timeline không phải audit log

Timeline history không chứa danh sách câu SQL, người dùng hay mọi thay đổi nghiệp vụ. Nó mô tả quan hệ giữa các nhánh WAL và vị trí phân nhánh.

---

## 3. Timeline ID, LSN và transaction ID

Ba khái niệm này thường bị nhầm lẫn.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Timeline ID (TLI) | Định danh nhánh WAL | 1, 2, 3 |
| LSN | Vị trí trong WAL stream | 0/5000000 |
| Transaction ID (XID) | Định danh transaction theo cơ chế PostgreSQL | XID của một transaction |
| Checkpoint | Điểm đồng bộ phục vụ recovery | Checkpoint record/redo location |
| Restore point | Marker có tên được ghi vào WAL | before_release |

### 3.1. LSN tiếp tục theo WAL position

Khi timeline mới bắt đầu, WAL tiếp tục từ điểm phân nhánh về mặt vị trí LSN. Timeline ID giúp phân biệt bytes ở nhánh mới với bytes ở nhánh cũ khi chúng cùng có vị trí/segment number tương tự.

### 3.2. XID không được reset khi promotion

Promotion không phải thao tác tạo một database mới với transaction IDs bắt đầu lại. Nó kết thúc recovery và chuyển server sang hoạt động như primary trên nhánh WAL mới.

### 3.3. Checkpoint không tạo timeline mới

Checkpoint thiết lập recovery state trên timeline đang dùng. Checkpoint bình thường không phải một nhánh WAL mới.

### 3.4. Restore point không tạo timeline

Hàm pg_create_restore_point() ghi một marker được đặt tên trong WAL. Nó hữu ích cho recovery target theo tên, nhưng bản thân lời gọi này không promote server và không cấp timeline mới.

Ví dụ:

```sql
SELECT pg_create_restore_point('before_schema_migration');
```

Kết quả trả về là LSN của restore point. Có thể dùng tên đó làm recovery target trong một quy trình PITR.

---

## 4. Lịch sử timeline có dạng cây

Timeline có thể được hình dung như một cây có các nhánh. Một timeline con kế thừa lịch sử timeline cha tới fork point, sau đó ghi các thay đổi riêng.

```text
                       Timeline 1
Base backup ---- WAL ---- WAL ----+---- WAL cũ tiếp tục
                                  |
                                  | Fork point
                                  |
                                  +---------------- Timeline 2
                                  |                   WAL mới
                                  |                   WAL mới
                                  |
                                  +---------------- Timeline 3
                                                      WAL của nhánh khác
```

Trong sơ đồ, timeline 2 và timeline 3 có thể xuất phát từ cùng một timeline cha nhưng được tạo ở những thời điểm/phân nhánh khác nhau. Chúng không thể được ghép thành một chuỗi ghi duy nhất sau fork point.

### 4.1. Timeline cha

Timeline chứa lịch sử chung trước điểm phân nhánh.

### 4.2. Timeline con

Timeline con tiếp tục từ fork point và ghi các WAL records riêng kể từ đó.

### 4.3. Fork point

Fork point là LSN mà timeline con bắt đầu tách khỏi timeline cha. Trước điểm này, hai nhánh dùng chung lịch sử WAL.

### 4.4. Vì sao cần biết ancestry?

Một base backup được tạo trên timeline 1 có thể được phục hồi tới timeline 2 nếu archive chứa lịch sử cha cần thiết, history file của timeline 2 và WAL liên tục trên nhánh con.

### 4.5. Hai nhánh không thể tự động merge

Nếu timeline 2 và timeline 3 đều có các transaction khác nhau sau fork point, PostgreSQL không tự hòa giải những transaction đó. Muốn hợp nhất dữ liệu nghiệp vụ, cần quy trình export/import hoặc replication logic ở tầng ứng dụng.

---

## 5. WAL segment filename chứa timeline ID

Tên WAL segment có cấu trúc hexadecimal gồm ba phần:

```text
TTTTTTTT LLLLLLLL SSSSSSSS
   |        |        |
   |        |        +-- Segment number
   |        +----------- Log number
   +-------------------- Timeline ID
```

Ví dụ tên minh họa:

```text
00000001000000000000005A
00000002000000000000005A
```

Hai file trên có cùng log/segment portion nhưng timeline prefix khác nhau. Chúng thuộc hai nhánh WAL khác nhau và không được coi là cùng một nội dung.

### 5.1. Timeline ID được mã hóa trong tên file

Phần đầu tên WAL segment biểu diễn TLI theo hexadecimal. Vì vậy archive tool phải giữ nguyên tên file, không tự đổi prefix.

### 5.2. Không chỉ lưu segment number

Nếu chỉ lưu segment number mà bỏ timeline prefix, archive có thể ghi đè dữ liệu của một nhánh bằng file từ nhánh khác.

### 5.3. WAL archive cần giữ nguyên tên đầy đủ

Archive repository cần giữ nguyên tên WAL segment và timeline history files. Không rename segment theo ngày giờ nếu cách rename làm mất thông tin định danh gốc hoặc gây nhầm lẫn khi restore.

### 5.4. Segment size không quyết định timeline

Kích thước WAL segment và timeline ID là hai thuộc tính khác nhau. Segment size thường được cố định khi build PostgreSQL; timeline chỉ phân biệt nhánh lịch sử.

---

## 6. Timeline history file

Khi một timeline mới được tạo, PostgreSQL tạo một **timeline history file**, thường có phần mở rộng .history.

Ví dụ:

```text
00000002.history
```

File này ghi quan hệ giữa timeline mới và lịch sử cha. Nội dung bao gồm timeline cha, LSN phân nhánh và thông tin mô tả lý do/nguồn tạo nhánh.

### 6.1. History file không phải WAL segment

WAL segment chứa WAL records. History file mô tả cây timeline và fork points.

### 6.2. Một history file có thể mô tả nhiều tổ tiên

Nếu timeline 3 được tạo từ timeline 2, mà timeline 2 lại được tạo từ timeline 1, history của timeline 3 giúp recovery lần theo chuỗi ancestry.

### 6.3. History file cần được archive

PostgreSQL archive cơ chế WAL cũng có thể archive timeline history files. Archive tooling phải giữ chúng để phục hồi qua timeline switches.

### 6.4. History file giúp chọn đúng WAL

Khi recovery cần timeline con, PostgreSQL dùng history file để biết WAL của timeline cha cần tới fork point nào, rồi tiếp tục đọc WAL của timeline con.

### 6.5. Không sửa history file bằng tay

History file là metadata quan trọng cho recovery. Không chỉnh sửa timeline ID, fork LSN hoặc nội dung file để ép PostgreSQL chọn nhánh mong muốn.

### 6.6. Kiểm tra archive inventory

Một archive có đủ WAL segment nhưng thiếu history file vẫn có thể không cung cấp đủ thông tin để đi qua timeline switch đúng cách.

---

## 7. Khi nào PostgreSQL tạo timeline mới?

Timeline mới thường xuất hiện khi một server kết thúc recovery và được promote để tiếp tục hoạt động như primary.

Các tình huống phổ biến:

- Standby được promote sau failover.
- Một bản backup được phục hồi tới recovery target rồi promote.
- Một server đang archive recovery được đưa ra khỏi recovery và bắt đầu nhận ghi.
- Một nhánh recovery được tạo sau khi chọn một điểm trong lịch sử WAL.

### 7.1. Promotion

Promotion kết thúc recovery mode. Server chuyển sang hoạt động như primary, nhận ghi mới và bắt đầu WAL trên timeline mới.

### 7.2. Crash recovery thông thường không tự tạo timeline mới

Nếu primary crash rồi khởi động lại và tiếp tục recovery trên cùng lịch sử, nó thường tiếp tục timeline hiện có. Chỉ việc restart không tự tạo một nhánh mới.

### 7.3. Checkpoint không tạo timeline mới

Checkpoint chỉ cập nhật recovery state của timeline hiện tại.

### 7.4. Restart standby không đồng nghĩa promotion

Một standby có thể restart và tiếp tục recovery/streaming trên timeline của upstream. Nó chỉ trở thành primary khi được promote.

### 7.5. Một timeline mới không có nghĩa mọi dữ liệu trước đó thay đổi

Lịch sử trước fork point vẫn được kế thừa. Khác biệt xuất hiện ở WAL sau fork point.

---

## 8. Promotion là gì?

**Promotion** là quá trình đưa một PostgreSQL server đang ở recovery/standby mode ra khỏi recovery để nó có thể hoạt động như primary.

Trước promotion:

- Server replay WAL.
- Với physical standby, dữ liệu thường ở chế độ read-only.
- WAL receiver có thể tiếp tục nhận WAL từ upstream.
- Server chưa nhận ghi thông thường như primary.

Sau promotion:

- Recovery kết thúc.
- Server có thể nhận ghi.
- WAL tiếp tục trên timeline mới.
- History file mô tả nhánh mới được tạo.
- Standby cũ không còn tự động theo primary cũ.

### 8.1. Promotion không phải copy dữ liệu

Promotion không tạo một bản sao mới của toàn bộ database. Nó thay đổi trạng thái recovery và mở một nhánh WAL mới từ dữ liệu standby đã replay.

### 8.2. Promotion không tự đồng bộ phần WAL bị thiếu

Nếu standby chưa nhận/replay các WAL records cuối cùng của primary cũ, promotion có thể khiến các transaction đó không xuất hiện trên nhánh mới.

### 8.3. Promotion là quyết định HA

Cần xác định primary cũ đã thật sự dừng hoặc bị fencing trước khi promote standby. Nếu hai server cùng nhận ghi, hệ thống có split brain.

### 8.4. Promotion có thể chủ động

Có thể promote trong bảo trì, switchover hoặc diễn tập DR nếu quy trình đã bảo đảm dữ liệu và vai trò của các nodes.

---

## 9. Promote standby bằng SQL hoặc pg_ctl

### 9.1. Dùng SQL function

Trên standby đang ở recovery:

```sql
SELECT pg_promote();
```

Hàm có thể chờ promotion hoàn tất và trả kết quả boolean. Có overload cho phép điều chỉnh thời gian chờ trên các phiên bản hỗ trợ. Quyền thực thi phụ thuộc role và phiên bản.

### 9.2. Dùng pg_ctl

Ở máy chủ có quyền truy cập data directory:

```bash
pg_ctl promote -D /path/to/standby-data
```

Lệnh yêu cầu server tương ứng thoát standby recovery và promote.

### 9.3. Chọn một phương thức phù hợp

Không cần gọi cả SQL function và pg_ctl cho cùng một promotion. Dùng một phương thức được runbook hỗ trợ và kiểm tra trạng thái sau đó.

### 9.4. Xác nhận server đã thoát recovery

```sql
SELECT pg_is_in_recovery();
```

- true: server vẫn đang recovery/standby.
- false: server không còn ở recovery mode và có thể hoạt động như primary nếu các điều kiện khác cho phép.

### 9.5. Xác nhận timeline hiện tại

Có thể đọc thông tin checkpoint/control file bằng công cụ phù hợp với phiên bản và quyền truy cập. Ví dụ OS-level:

```bash
pg_controldata /path/to/standby-data
```

Tìm trường timeline/checkpoint trong output. Không dùng một dòng output đơn lẻ thay cho kiểm tra replication và dữ liệu ứng dụng.

---

## 10. Promotion và standby signal files

Từ PostgreSQL 12, chế độ recovery được xác định bằng signal files trong data directory thay cho file cấu hình recovery.conf kiểu cũ.

### 10.1. standby.signal

Sự hiện diện của standby.signal yêu cầu server khởi động ở standby mode và tiếp tục recovery/streaming theo cấu hình.

### 10.2. recovery.signal

recovery.signal yêu cầu archive recovery, thường được dùng trong quy trình PITR.

### 10.3. Không nhầm hai signal files

- standby.signal: server tiếp tục chạy như standby và có thể chờ WAL upstream.
- recovery.signal: server thực hiện archive recovery theo restore settings/recovery targets.

### 10.4. Promotion kết thúc standby mode

Khi standby được promote, PostgreSQL kết thúc recovery và chuyển sang primary. Không tự tạo/xóa signal files bằng tay trong lúc server đang chạy để thay đổi vai trò.

### 10.5. PostgreSQL cũ

Các phiên bản trước PostgreSQL 12 dùng cơ chế recovery.conf. Không áp dụng hướng dẫn signal file cho cluster cũ nếu tài liệu major version yêu cầu cách khác.

---

## 11. Promotion sau failover: ví dụ hai nodes

Giả sử hệ thống có:

- db-primary: primary.
- db-standby: physical standby.
- WAL streaming đang hoạt động.
- Archive WAL được bật.

Trạng thái trước sự cố:

```text
db-primary (timeline 1)
       |
       | streaming WAL
       v
db-standby (timeline 1)
  replay tới LSN Y
```

Primary gặp sự cố. Standby có thể đã nhận/replay tới LSN Y nhưng primary có thể đã tạo thêm WAL tới LSN Z mà standby chưa nhận.

### 11.1. Đánh giá standby state

Kiểm tra:

- WAL receiver có đang hoạt động không.
- LSN nhận và replay gần nhất.
- Synchronous hay asynchronous replication.
- Archive có WAL sau LSN Y không.
- Primary cũ còn có thể nhận ghi không.

### 11.2. Fence primary cũ

Trước khi promote, bảo đảm primary cũ không thể tiếp tục nhận writes. Có thể cần tắt instance, cô lập network, thu hồi quyền truy cập storage hoặc dùng fencing trong HA platform.

### 11.3. Promote standby

Khi đã quyết định failover và có primary cũ được fencing, promote standby.

### 11.4. Timeline mới

Standby trở thành primary trên timeline mới. Các transaction sau fork point được ghi vào nhánh mới.

### 11.5. Cập nhật topology

Các replicas/clients phải kết nối tới primary mới. Các standby cần follow timeline mới hoặc được rebuild/rewind nếu chúng ở nhánh cũ.

### 11.6. Không đưa primary cũ lên như primary thứ hai

Primary cũ có thể chứa các WAL records ở nhánh cũ không có trong nhánh mới. Phải rewind hoặc clone lại trước khi rejoin.

---

## 12. Synchronous và asynchronous replication ảnh hưởng failover

Timeline cho biết nhánh lịch sử; replication mode ảnh hưởng nhánh mới có thể thiếu bao nhiêu transaction so với primary cũ.

### 12.1. Asynchronous replication

Primary không cần đợi standby xác nhận WAL trước khi trả COMMIT. Khi primary hỏng đột ngột, standby có thể chưa nhận/replay các WAL records cuối cùng.

Promotion standby có thể làm mất những transaction đã commit trên primary nhưng chưa tới standby.

### 12.2. Synchronous replication

Primary đợi synchronous standby acknowledgement theo cấu hình và synchronous_commit. Nếu dùng remote flush, commit đã được xác nhận thường có WAL được flush trên standby đủ điều kiện.

### 12.3. remote_apply

Với mức remote apply, primary đợi standby replay transaction trước khi xác nhận commit. Điều này có thể giúp read-after-write trên standby và tăng độ trễ.

### 12.4. Synchronous replication không loại bỏ mọi rủi ro failover

Cần bảo đảm đúng standby đã được chọn, acknowledgement đúng policy, promotion đúng node và không có split brain. Một hệ thống synchronous cấu hình sai vẫn có thể mất dữ liệu hoặc không sẵn sàng.

### 12.5. So sánh

| Cơ chế | Primary đợi gì? | Tác động khi failover |
| --- | --- | --- |
| Asynchronous | Không đợi standby | Có thể mất WAL chưa gửi/nhận/replay |
| Synchronous remote_write | Standby ghi WAL tới OS | Mức bảo vệ thấp hơn remote flush trước mất điện standby |
| Synchronous remote_flush | Standby flush WAL | Bảo vệ commit tốt hơn khi promotion standby phù hợp |
| Synchronous remote_apply | Standby replay WAL | Standby đã apply commit được xác nhận; latency cao hơn |

### 12.6. RPO phải được kiểm chứng

Không tuyên bố RPO bằng 0 chỉ vì bật synchronous replication. Xác nhận topology, quorum, failover selection, storage guarantees và test tình huống mất primary thực tế.

---

## 13. Timeline history file và recovery path

Giả sử base backup được tạo trên timeline 1. Sau đó timeline 2 được tạo từ fork point F.

Để restore tới một thời điểm trên timeline 2, PostgreSQL cần:

1. Base backup hợp lệ.
2. WAL timeline 1 liên tục từ backup tới fork point F.
3. History file mô tả timeline 2 bắt nguồn từ timeline 1 tại F.
4. WAL timeline 2 từ sau F tới recovery target.
5. Các history files của tổ tiên nếu timeline có nhiều nhánh.

```text
Base backup (TLI 1)
       |
       v
WAL TLI 1 ----------------------+
                                |
                           Fork point F
                                |
History file TLI 2 -------------+
                                |
                                v
                         WAL TLI 2
                                |
                                v
                         Recovery target
```

### 13.1. WAL cha chỉ cần tới fork point cho nhánh con

Sau fork point, nhánh con có WAL riêng. Không ghép WAL cha sau fork point vào lịch sử con.

### 13.2. History file nối ancestry

History file cho PostgreSQL biết timeline cha và vị trí phân nhánh để chọn WAL đúng.

### 13.3. Missing history file có thể làm recovery không đi đúng nhánh

Archive có thể chứa nhiều segments nhưng thiếu history file, khiến recovery không thể xác định/đi theo timeline mới như mong muốn.

### 13.4. Giữ history files lâu như backup phụ thuộc

Nếu còn giữ base backups có thể cần timeline đó, phải giữ các history files và WAL segments cần thiết cho chúng.

---

## 14. recovery_target_timeline: chọn nhánh nào?

Tham số recovery_target_timeline điều khiển timeline mà recovery hoặc standby sẽ theo.

Các lựa chọn thường gặp:

- current: dùng timeline được xác định từ base backup/cluster đang khôi phục.
- latest: theo timeline mới nhất tìm thấy trong WAL archive.
- Một timeline ID cụ thể: chọn chính xác nhánh mong muốn.

Trong các phiên bản hiện đại, mặc định thường là latest; hãy xác nhận giá trị hiệu lực trên cluster.

### 14.1. Dùng latest

Phù hợp khi muốn standby theo nhánh timeline mới nhất trong archive sau failover.

### 14.2. Dùng current

Phù hợp khi muốn giữ lịch sử timeline của base backup và không tự chuyển sang một nhánh mới hơn có trong archive.

### 14.3. Dùng timeline ID cụ thể

Phù hợp khi archive chứa nhiều nhánh và recovery phải dừng/đi theo đúng một nhánh đã được xác định.

Ví dụ minh họa:

```conf
recovery_target_timeline = '2'
```

Đây là giá trị minh họa. Chỉ chọn ID có thật trong history/archive của cluster.

### 14.4. latest không phải lúc nào cũng là nhánh nghiệp vụ mong muốn

Nếu archive có nhiều nhánh do các lần promotion, test restore hoặc failover cũ, timeline mới nhất có thể không phải nhánh mà ứng dụng muốn phục hồi. Khi cần tính xác định, chọn timeline cụ thể và ghi rõ trong runbook.

### 14.5. Timeline mới phải có ancestry hợp lệ

Chỉ đặt TLI không đủ. Recovery vẫn cần history files và WAL của timeline cha/con liên tục theo fork points.

---

## 15. PITR trên timeline cụ thể

PITR thường dùng một base backup và WAL archive để dừng tại một recovery target.

### 15.1. Recovery target có thể là thời gian

```conf
recovery_target_time = '2026-11-14 10:30:00+07'
```

Timezone phải được xác định rõ. Thời điểm không có timezone có thể bị diễn giải theo timezone cấu hình của server.

### 15.2. Recovery target có thể là LSN

```conf
recovery_target_lsn = '0/7A000120'
```

LSN minh họa. Dùng giá trị thực được ghi nhận trong cùng lịch sử WAL.

### 15.3. Recovery target có thể là transaction ID

```conf
recovery_target_xid = '123456'
```

Chỉ dùng XID thực tế, phù hợp cluster và phiên bản.

### 15.4. Recovery target có thể là named restore point

```sql
SELECT pg_create_restore_point('before_bad_deploy');
```

Sau đó cấu hình:

```conf
recovery_target_name = 'before_bad_deploy'
```

### 15.5. Chỉ chọn một target chính

Các recovery target settings có quy tắc loại trừ nhau. Không cấu hình đồng thời nhiều target khác loại với kỳ vọng PostgreSQL tự chọn mục tiêu phù hợp.

### 15.6. recovery_target_inclusive

Tham số này điều khiển có bao gồm transaction tại đúng target hay dừng trước nó, tùy loại target. Mặc định thường là true. Nếu dữ liệu nghiệp vụ cần ranh giới chính xác, phải test semantics bằng restore drill.

### 15.7. Kết hợp target với timeline

Target thời gian/LSN phải được diễn giải trên nhánh timeline được chọn. Cùng một khoảng thời gian có thể có các giao dịch khác nhau trên hai nhánh sau fork point.

---

## 16. recovery_target_action: dừng, pause hay promote

Khi đạt recovery target, PostgreSQL có thể thực hiện hành động được cấu hình.

### 16.1. pause

Server dừng replay tại target và ở trạng thái recovery pause. Đây là lựa chọn hữu ích để kiểm tra dữ liệu trước khi quyết định promote.

### 16.2. promote

Server tự động kết thúc recovery và promote khi đạt target. Promotion tạo timeline mới để server tiếp tục nhận ghi.

### 16.3. shutdown

Server dừng sau khi đạt target. Hữu ích cho một số quy trình phục hồi cần kiểm tra trước khi mở server.

### 16.4. Mặc định và phiên bản

Giá trị mặc định phổ biến là pause, nhưng hãy xác nhận tài liệu major version và cấu hình hiệu lực.

### 16.5. Kiểm tra trước promotion

Khi pause, có thể kết nối đọc và xác minh dữ liệu trong môi trường phục hồi. Nếu mọi thứ đúng, thực hiện promotion theo runbook.

### 16.6. Resume recovery

Hàm pg_wal_replay_resume() có thể tiếp tục replay sau pause. Nếu mục tiêu là tiếp tục từ target và tạo primary mới, cần hiểu rõ khi nào gọi resume và khi nào promote; hai hành động có ý nghĩa khác nhau.

---

## 17. Signal files và quy trình PITR

Với PostgreSQL 12 trở lên, quy trình archive recovery thường dùng recovery.signal.

### 17.1. Chuẩn bị base backup

Restore base backup vào data directory riêng, bảo đảm ownership, permissions, tablespace paths và dung lượng.

### 17.2. Cấu hình restore command

```conf
restore_command = 'restore-helper %f %p'
```

restore-helper là placeholder cho script lấy file từ archive. Nó phải trả kết quả đúng khi file có hoặc không có, xử lý history files và bảo đảm integrity.

### 17.3. Cấu hình timeline và target

```conf
recovery_target_timeline = '2'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
```

Chỉ dùng một recovery target phù hợp; ví dụ trên minh họa một target time và timeline cụ thể.

### 17.4. Tạo recovery.signal

Tạo file signal theo quy trình restore đã được kiểm chứng cho PostgreSQL version đang dùng. Không để đồng thời các signal/configurations mâu thuẫn.

### 17.5. Khởi động và đọc logs

PostgreSQL sẽ đọc base backup, tìm WAL cần thiết, lần theo timeline history và replay tới target. Đọc startup logs để xác nhận timeline và recovery target được nhận đúng.

### 17.6. Xác minh trạng thái

Dùng SQL kiểm tra pg_is_in_recovery(), dữ liệu nghiệp vụ, LSN replay và log server. Không chỉ dựa vào process đã start.

### 17.7. Promotion sau kiểm tra

Nếu chọn pause, có thể promote sau khi kiểm tra target và quyết định tiếp tục hoạt động trên nhánh mới. Khi promotion hoàn tất, server nhận writes.

### 17.8. PostgreSQL trước 12

Các bản cũ dùng recovery.conf và có quy tắc cấu hình khác. Không áp dụng signal file procedure vào bản cũ.

---

## 18. Standby theo timeline mới sau failover

Một standby còn hoạt động cần theo primary mới sau promotion. Đây là một trong những lý do quan trọng để hiểu recovery_target_timeline='latest'.

### 18.1. Standby cũ vẫn có thể ở timeline trước

Nếu standby B được promote từ timeline 1 lên timeline 2, một standby C còn lại có thể vẫn đang theo timeline 1.

### 18.2. Cần history file của timeline mới

C cung cấp history file để biết timeline 2 phát sinh từ timeline 1 tại fork point nào.

### 18.3. latest giúp theo nhánh mới

Khi được cấu hình để theo latest, standby có thể phát hiện timeline mới trong archive và đi theo nhánh mới nếu có đủ WAL/ancestry.

### 18.4. Thiếu WAL từ fork point

Nếu standby C đã tụt quá xa và WAL cần thiết không còn trên primary/archive, nó không thể tự bắt kịp bằng streaming. Có thể phải dùng pg_rewind hoặc base backup mới.

### 18.5. Cascading standby

Một standby có thể cung cấp WAL cho standby khác. Khi upstream thay đổi timeline, cascading topology cũng phải theo nhánh mới và giữ đúng history/WAL.

### 18.6. Không chỉ đổi primary_conninfo

Thay connection string mà không xử lý timeline divergence có thể khiến standby không thể tiếp tục recovery. Kiểm tra logs, timeline và WAL availability.

---

## 19. Primary cũ sau promotion

Khi standby được promote, primary cũ có thể quay lại sau khi sự cố được khắc phục. Tuy nhiên nó không thể đơn giản tiếp tục hoạt động trên nhánh cũ như một primary độc lập.

### 19.1. Vì sao primary cũ bị divergent?

Primary cũ có thể đã tạo WAL sau fork point mà standby mới không nhận. Primary mới cũng có các WAL records riêng sau promotion.

### 19.2. Không khởi động primary cũ để nhận writes

Nếu primary cũ và primary mới cùng nhận writes, hệ thống có hai lịch sử khác nhau. Timeline không tự merge chúng.

### 19.3. Chọn cách rejoin

Có hai hướng phổ biến:

- Dùng pg_rewind để đưa data directory cũ về nhánh của primary mới khi đủ điều kiện.
- Tạo lại standby từ base backup của primary mới.

### 19.4. Bảo toàn dữ liệu trước thao tác

Rewind/reinitialize có thể ghi đè hoặc thay đổi data directory target. Nếu cần điều tra nhánh cũ, giữ snapshot/copy trước khi thao tác.

### 19.5. Không coi primary cũ là nguồn dữ liệu chính

Sau khi failover được xác nhận, primary mới là nguồn authoritative. Dữ liệu chỉ có ở nhánh cũ cần được trích xuất và reconcile riêng nếu nghiệp vụ yêu cầu.

---

## 20. pg_rewind đưa primary cũ về nhánh mới

pg_rewind là tiện ích PostgreSQL dùng để đồng bộ một data directory đã diverge với một source cluster bằng cách xác định các blocks cần cập nhật kể từ điểm chung.

### 20.1. Ý tưởng

- Tìm common ancestor/fork point giữa target và source.
- Xác định các blocks đã thay đổi trên nhánh source kể từ điểm phân nhánh.
- Copy các blocks cần thiết từ source.
- Làm cho target có thể tiếp tục trên lịch sử của source sau khi cấu hình làm standby.

### 20.2. Điều kiện tiên quyết quan trọng

Trước khi dùng, xác nhận:

1. Target và source thuộc cùng một PostgreSQL cluster lineage trước khi diverge.
2. Target server đã được shutdown cleanly theo yêu cầu công cụ.
3. Data checksums đã bật từ khi initdb hoặc wal_log_hints đã bật trên target từ trước.
4. full_page_writes được bật theo yêu cầu của pg_rewind.
5. WAL cần thiết từ điểm phân nhánh còn sẵn hoặc có thể lấy từ archive theo phiên bản/cách gọi.
6. PostgreSQL binary và công cụ tương thích với cluster.
7. Có backup/snapshot target trước khi rewind.

Không thể bật checksums hồi tố cho một cluster hiện hữu chỉ để chạy pg_rewind mà không thực hiện quy trình chuyển đổi riêng.

### 20.3. WAL từ điểm phân nhánh

pg_rewind cần đủ WAL để xác định các thay đổi trên target kể từ fork point. Nếu WAL cần thiết đã bị recycle, có thể cần lấy từ archive. Nếu không thể cung cấp, rewind có thể thất bại.

### 20.4. Ví dụ dạng lệnh

```bash
pg_rewind --target-pgdata=/data/old-primary \
          --source-server="host=new-primary dbname=postgres user=rewind_user"
```

Ví dụ cần thay path, connection string và quyền bằng thông tin thật. Không chạy lệnh trên production khi chưa xác nhận target đúng, server đã dừng cleanly, backup có thể phục hồi và preconditions đã đáp ứng.

### 20.5. Sau rewind

Cấu hình target thành standby theo quy trình của cluster:

- Đặt connection tới primary mới.
- Cấu hình replication slot nếu dùng.
- Cấu hình WAL archive/restore command nếu cần.
- Thiết lập standby mode theo phiên bản (ví dụ standby.signal ở PostgreSQL 12+).
- Khởi động và kiểm tra WAL receiver/replay.

### 20.6. pg_rewind không phải backup

Rewind thay đổi nội dung data directory target. Không dùng nó thay backup, và không bỏ qua bước snapshot khi cần bảo toàn dữ liệu để điều tra.

### 20.7. Khi nào nên dùng base backup?

Nếu cluster không đáp ứng điều kiện rewind, WAL cần thiết bị thiếu, hoặc muốn một quy trình đơn giản/đã chuẩn hóa, tạo lại standby từ base backup thường là lựa chọn phù hợp.

---

## 21. Reinitialize standby bằng base backup

Khi primary cũ không thể rewind an toàn, hãy tạo lại data directory standby từ primary mới.

### 21.1. Chuẩn bị

- Xác nhận primary mới là nguồn authoritative.
- Dừng và bảo toàn data directory cũ nếu cần.
- Kiểm tra dung lượng đủ cho base backup.
- Chuẩn bị replication user, connection và slot.
- Kiểm tra archive/WAL retention.

### 21.2. Lấy base backup

Có thể dùng pg_basebackup hoặc backup tooling tương thích. Ví dụ:

```bash
pg_basebackup -h new-primary \
              -D /data/new-standby \
              -U replication_user \
              -R -X stream
```

Đây là ví dụ minh họa. Chọn flags, replication slot, WAL method, compression và tablespace mapping theo version/operational policy.

### 21.3. Tùy chọn -R

Trên các phiên bản hỗ trợ, -R ghi cấu hình cần thiết để server có thể tiếp tục như standby, bao gồm thông tin kết nối và signal file phù hợp. Vẫn phải review cấu hình trước khi khởi động.

### 21.4. Khởi động standby

Bảo đảm primary_conninfo, slot, restore command, archive settings và standby signal phù hợp. Sau đó khởi động instance theo runbook.

### 21.5. Xác nhận bắt kịp

Kiểm tra pg_stat_wal_receiver, receive/replay LSN, primary pg_stat_replication, lag trend và dữ liệu đọc.

### 21.6. Rebuild tốn tài nguyên

Base backup có thể truyền lượng dữ liệu lớn, tăng network/storage I/O. Lên lịch, kiểm tra capacity và giữ primary ổn định trong thời gian tạo standby.

---

## 22. Split brain và fencing

**Split brain** xảy ra khi hai server cùng được xem là primary và cùng nhận writes trên các nhánh riêng.

### 22.1. Timeline không tự ngăn split brain

Timeline giúp phân biệt nhánh WAL sau khi sự kiện xảy ra. Nó không khóa server cũ và không điều phối quyền ghi.

### 22.2. Fencing

Fencing bảo đảm node cũ không còn khả năng nhận ghi khi node mới được promote. Tùy hạ tầng, có thể dùng:

- Tắt VM/instance cũ.
- Cô lập network ở lớp hạ tầng.
- Thu hồi quyền truy cập storage.
- Fencing qua cloud control plane.
- STONITH hoặc cơ chế tương đương trong HA manager.

### 22.3. Không chỉ dựa vào ping

Mất kết nối từ monitor không chứng minh primary đã chết. Có thể network partition khiến monitor không thấy primary trong khi ứng dụng vẫn ghi được vào nó.

### 22.4. Promotion phải có quorum/policy

HA system cần quy tắc xác định node nào có quyền promote, dựa vào quorum, fencing và trạng thái replication.

### 22.5. Reconcile dữ liệu từ nhánh cũ

Nếu split brain đã xảy ra, dữ liệu chỉ tồn tại trên nhánh cũ có thể cần trích xuất thủ công và đối soát. PostgreSQL không tự merge hai timeline.

---

## 23. Theo dõi timeline và trạng thái recovery

### 23.1. Server có đang recovery?

```sql
SELECT pg_is_in_recovery();
```

Đây là kiểm tra đơn giản để phân biệt server đang recovery hay đã hoạt động như primary.

### 23.2. LSN replay trên standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

### 23.3. Primary replication status

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_catalog.pg_stat_replication;
```

### 23.4. WAL receiver status

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

Các columns của view có thể thay đổi theo version. Dùng SELECT * để khám phá trên lab, rồi viết query rõ cột cho monitoring production.

### 23.5. Archiver status

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

### 23.6. Kiểm tra control file

pg_controldata cung cấp thông tin checkpoint/timeline trong control file. Đây là công cụ OS-level, cần quyền truy cập data directory và nên chạy khi biết rõ server state.

### 23.7. LSN không thay thế timeline ID

Khi đối chiếu log, ghi cả timeline và LSN. Cùng một LSN trên hai nhánh sau fork point không đại diện cùng một lịch sử WAL.

---

## 24. Kiểm tra WAL filename và vị trí

Các hàm WAL filename hữu ích để ánh xạ LSN sang segment trên timeline hiện tại.

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
```

### 24.1. LSN và WAL file

Một LSN nằm trong một WAL segment. Tên segment có thể giúp xác định timeline prefix và segment location.

### 24.2. Tên file trên timeline hiện tại

Hàm pg_walfile_name() dùng timeline hiện tại của server. Khi phân tích archive chứa nhiều nhánh, cần đối chiếu timeline history và tên segment thay vì suy ra từ một LSN đơn lẻ.

### 24.3. pg_walfile_name_offset()

Hàm này có thể trả về tên file và offset trong segment cho một LSN, tùy phiên bản.

### 24.4. Không suy diễn thời gian từ tên file

WAL segment number không phải timestamp. Muốn biết thời điểm giao dịch cần dữ liệu timestamp/commit records hoặc logs phù hợp.

---

## 25. Archive retention qua nhiều timeline

Archive policy phải giữ đủ dữ liệu cho mọi base backup còn được hỗ trợ.

### 25.1. Giữ WAL của timeline cha

Một base backup cũ có thể cần WAL của timeline cha trước fork point để đi tới timeline con.

### 25.2. Giữ WAL của timeline con

Sau fork point, cần WAL của nhánh con tới target cần phục hồi.

### 25.3. Giữ history files

Mỗi timeline con cần history file để mô tả ancestry. Nếu có nhiều cấp nhánh, giữ các history files liên quan.

### 25.4. Không xóa archive chỉ theo tuổi file

Một WAL segment cũ vẫn có thể cần cho base backup cũ còn trong retention window. Xóa theo tuổi file mà không xét backup dependency có thể phá PITR.

### 25.5. Retention theo backup catalog

Một quy trình cleanup an toàn cần biết:

- Những base backups nào còn hợp lệ.
- Mỗi backup bắt đầu ở timeline nào.
- WAL cần từ backup tới các recovery targets được cam kết.
- Những timeline history files nào nằm trên đường ancestry.
- Standby/logical consumers còn cần WAL nào.

### 25.6. Archive phải chống overwrite

Dùng tên file đầy đủ và quy tắc immutable/atomic publish phù hợp. Nếu một file cùng tên đã tồn tại, kiểm tra checksum/nội dung; không ghi đè âm thầm một archive segment khác.

### 25.7. Kiểm tra archive continuity

Một manifest có thể ghi danh sách WAL segments/history files theo timeline và checksum. Định kỳ kiểm tra các khoảng liên tục mà backup catalog yêu cầu.

---

## 26. PITR qua nhiều lần promotion

Giả sử lịch sử:

1. Timeline 1 là primary ban đầu.
2. Standby được promote, tạo timeline 2 tại LSN A.
3. Timeline 2 hoạt động rồi được backup.
4. Một lần PITR/DR khác tạo timeline 3 tại LSN B của timeline 2.

Để restore tới một target trên timeline 3, recovery phải hiểu ancestry:

```text
Timeline 1
   |
   | Fork A
   v
Timeline 2
   |
   | Fork B
   v
Timeline 3
```

### 26.1. Cần lịch sử tổ tiên

Không chỉ cần file 00000003.history. Cần cả thông tin ancestry để đi qua timeline 2 và timeline 1 khi base backup bắt đầu từ nhánh cũ.

### 26.2. WAL của mỗi timeline có giới hạn

WAL timeline 1 được dùng tới fork A; WAL timeline 2 được dùng tới fork B; WAL timeline 3 dùng sau fork B.

### 26.3. Chọn target trên nhánh cụ thể

Nếu archive có nhiều descendants, chỉ định timeline ID rõ ràng khi cần tái tạo một lịch sử cụ thể.

### 26.4. Backup trên timeline mới đơn giản hóa recovery

Base backup được tạo sau promotion trên timeline mới có thể giảm số WAL ancestor phải replay, nhưng vẫn cần giữ WAL sau backup để PITR.

### 26.5. Không bỏ history files cũ

Một backup mới không nhất thiết khiến mọi backup cũ hết giá trị. Retention phải theo catalog và mục tiêu phục hồi.

---

## 27. Lab: quan sát timeline trước và sau promotion

Lab này cần ít nhất một primary và một physical standby trong môi trường riêng. Không thực hiện promotion trên cluster production chỉ để quan sát.

### 27.1. Trên primary, xem LSN

```sql
SELECT
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
```

### 27.2. Trên standby, xem trạng thái recovery

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

Khi là standby, pg_is_in_recovery() phải trả true.

### 27.3. Ghi dữ liệu test trên primary

```sql
CREATE TABLE IF NOT EXISTS public.timeline_lab (
    id BIGINT PRIMARY KEY,
    note TEXT NOT NULL
);

INSERT INTO public.timeline_lab(id, note)
VALUES (1, 'before-promotion')
ON CONFLICT (id) DO UPDATE SET note = EXCLUDED.note;
```

Đợi standby replay và xác minh row.

### 27.4. Fencing và promotion trong lab

Dừng primary hoặc cô lập nó theo đúng topology test. Sau đó promote standby:

```sql
SELECT pg_promote();
```

Chỉ chạy khi đã xác nhận đang kết nối đúng standby và lab cho phép promotion.

### 27.5. Xác nhận

```sql
SELECT pg_is_in_recovery();
```

Kỳ vọng false sau promotion hoàn tất.

### 27.6. Ghi một row sau promotion

```sql
INSERT INTO public.timeline_lab(id, note)
VALUES (2, 'after-promotion');
```

Row này được ghi trên timeline mới.

### 27.7. Kiểm tra WAL archive

Tìm timeline history file và WAL segment có timeline prefix mới trong archive. Tên file thực tế phụ thuộc timeline ID và WAL position của cluster.

### 27.8. Kết thúc lab

Không đưa primary cũ trở lại như primary độc lập. Dùng pg_rewind nếu đủ điều kiện hoặc tạo lại standby từ base backup theo phần hướng dẫn rejoin.

---

## 28. Lab: tạo restore point và PITR có chọn timeline

Lab này cần base backup, WAL archiving liên tục và một data directory restore riêng.

### 28.1. Tạo marker

Trên primary:

```sql
SELECT pg_create_restore_point('before_test_change');
```

Lưu LSN và thời điểm.

### 28.2. Tạo thay đổi sau marker

```sql
INSERT INTO public.timeline_lab(id, note)
VALUES (100, 'after-restore-point');
```

### 28.3. Lấy base backup

Dùng công cụ backup phù hợp để tạo base backup nhất quán. Lưu metadata về timeline và thời gian backup.

### 28.4. Chuẩn bị restore copy

Restore vào một data directory riêng, không ghi đè primary hoặc standby đang hoạt động.

### 28.5. Cấu hình recovery

Ví dụ cấu hình minh họa:

```conf
restore_command = 'restore-helper %f %p'
recovery_target_name = 'before_test_change'
recovery_target_timeline = 'current'
recovery_target_action = 'pause'
```

Timeline phải được chọn theo lịch sử backup và archive thực tế.

### 28.6. Khởi động recovery

Dùng quy trình version-specific với recovery.signal. Theo dõi logs cho tới khi recovery pause ở named restore point.

### 28.7. Xác minh dữ liệu

Row được ghi trước restore point phải có mặt nếu thuộc base backup/WAL path. Row after-restore-point không được xuất hiện khi recovery dừng trước transaction đó.

### 28.8. Promote nếu muốn tiếp tục ghi

Sau khi kiểm tra, promote bản restore theo runbook. Hành động này tạo timeline mới từ điểm recovery target.

### 28.9. Giữ lại archive gốc

Không xóa WAL/history files dùng trong lab ngay sau promotion nếu còn cần phân tích hoặc tái lập restore.

---

## 29. Lab: kiểm tra nhiều timeline trong archive

Một archive có thể có các file dạng:

```text
00000001.history
00000002.history
00000003.history
000000010000000000000050
000000020000000000000050
000000030000000000000051
```

Đây chỉ là tên minh họa, không phải inventory thực tế.

### 29.1. Phân loại file

- .history: mô tả ancestry/fork point.
- WAL segment: chứa WAL records thuộc TLI trong prefix.

### 29.2. Đọc history files

Dùng công cụ đọc file archive an toàn để xác định timeline cha và fork LSN. Không sửa file.

### 29.3. Dựng cây timeline

Vẽ timeline cha/con theo từng history file. Xác định mỗi nhánh cần WAL từ đâu tới đâu.

### 29.4. Đối chiếu base backup

Ghi lại backup thuộc timeline nào và thời điểm/LSN bắt đầu. Từ đó tính các segments cần thiết cho target.

### 29.5. Kiểm tra continuity

Xác nhận mọi WAL segment trong đường đi đều tồn tại và có checksum hợp lệ. Một file không đọc được cũng có thể phá recovery.

### 29.6. Chọn timeline

Dùng recovery_target_timeline với TLI đã xác định. Không mặc định latest nếu archive có các nhánh không liên quan tới recovery case.

---

## 30. Các tình huống vận hành timeline

### 30.1. Primary failover

Standby được promote, timeline mới được tạo. Các replicas còn lại phải follow timeline mới hoặc được rebuild/rewind.

### 30.2. Planned switchover

Có thể dừng writes trên primary, đợi standby replay tới LSN mục tiêu, rồi promote standby. Quá trình này giúp giảm hoặc loại bỏ data loss trong điều kiện đồng bộ được kiểm chứng.

### 30.3. PITR sau khi xóa nhầm dữ liệu

Restore base backup tới trước transaction lỗi, kiểm tra dữ liệu rồi promote. Nhánh mới tách khỏi lịch sử cũ tại target.

### 30.4. Restore để kiểm tra backup

Có thể restore bản copy và pause ở target mà không promote. Nếu chỉ kiểm tra, giữ bản copy tách biệt khỏi production.

### 30.5. Standby tụt quá xa

Nếu WAL đã bị recycle, standby có thể không theo kịp. Kiểm tra archive và slot; dùng pg_rewind hoặc base backup tùy tình trạng divergence.

### 30.6. Hai nhánh cùng nhận writes

Đây là split brain. Dừng/fence nhánh không authoritative, bảo toàn dữ liệu cần điều tra và thực hiện reconciliation có kiểm soát.

### 30.7. Archive có timeline mới nhưng thiếu parent WAL

History file không thể thay thế WAL cha. Phải phục hồi archive continuity hoặc chọn backup khác có WAL path đầy đủ.

---

## 31. Quy trình failover an toàn

Một quy trình failover nên có các giai đoạn rõ ràng.

### 31.1. Xác nhận sự cố

- Kiểm tra primary health qua nhiều tín hiệu.
- Xác định network partition hay process/storage failure.
- Thu thập LSN và replication state cuối cùng có thể lấy được.
- Xác định standby đủ điều kiện và mức data loss có thể có.

### 31.2. Fence primary cũ

Bảo đảm primary cũ không còn nhận writes. Nếu không thể xác nhận fencing, không nên promote chỉ dựa vào timeout của một health check.

### 31.3. Chọn standby

Chọn node có WAL receive/replay progress tốt nhất theo policy. Với synchronous replication, xác minh node đó là synchronous standby phù hợp.

### 31.4. Promote

Dùng một phương thức promotion đã được kiểm thử. Chờ hoàn tất và xác nhận pg_is_in_recovery() trả false.

### 31.5. Xác nhận timeline

Kiểm tra timeline mới, history file và WAL generation. Lưu TLI, fork point/LSN và thời điểm promotion vào incident record.

### 31.6. Chuyển traffic

Cập nhật connection routing, service discovery, proxy hoặc load balancer để ứng dụng ghi vào primary mới.

### 31.7. Kiểm tra ứng dụng

Chạy smoke tests, transaction checks và xác nhận dữ liệu quan trọng. Theo dõi lỗi ghi, commit latency và replication status.

### 31.8. Rebuild topology

Đưa các standby khác theo timeline mới. Rewind hoặc tạo lại các node ở nhánh cũ.

### 31.9. Lưu bằng chứng

Ghi timeline history, LSNs, archive status, backup reference và các quyết định failover để hỗ trợ audit vận hành.

---

## 32. Quy trình switchover có kế hoạch

Switchover khác failover vì primary cũ còn hoạt động và có thể phối hợp chuyển vai trò.

### 32.1. Kiểm tra readiness

- Standby streaming ổn định.
- Không có WAL/archive backlog.
- Replication lag thấp hoặc bằng 0 theo tiêu chí.
- Có đủ dung lượng và health trên standby.
- Ứng dụng chấp nhận khoảng dừng ghi.

### 32.2. Dừng hoặc khóa writes

Dùng cơ chế ứng dụng/DB phù hợp để ngừng nhận writes mới và đợi transaction đang chạy hoàn tất.

### 32.3. Đợi standby replay

So sánh LSN primary với standby và xác nhận standby đã replay tới điểm cần chuyển.

### 32.4. Promote standby

Promote standby sau khi điều kiện đồng bộ đạt yêu cầu.

### 32.5. Chuyển traffic

Đổi endpoint ghi tới primary mới, kiểm tra ứng dụng và xác nhận node cũ đã được đưa về trạng thái standby hoặc dừng.

### 32.6. Tránh hai primary

Ngay cả switchover có kế hoạch cũng cần thứ tự chuyển vai trò và fencing phù hợp. Không để node cũ nhận ghi sau khi node mới đã promote.

---

## 33. Đưa standby còn lại theo timeline mới

Khi một standby được promote, các standby khác có thể đang ở timeline cũ.

### 33.1. Kiểm tra có thể follow timeline mới không

Nếu node có chung ancestry và WAL cần thiết từ fork point còn sẵn, cấu hình recovery_target_timeline='latest' cùng archive/streaming settings có thể giúp node theo nhánh mới.

### 33.2. Nếu WAL thiếu

Nếu WAL cần thiết đã bị recycle hoặc node có dữ liệu diverged, cần đánh giá pg_rewind hoặc base backup.

### 33.3. Không sửa timeline ID trong filename

Không rename WAL segment của timeline cũ thành prefix timeline mới. Chúng chứa records khác nhau.

### 33.4. Kiểm tra replication slot

Slot của standby cũ có thể cần được xử lý theo topology mới. Đảm bảo slot tồn tại và consumer đúng trước khi bật streaming.

### 33.5. Xác nhận replay

Theo dõi receive/replay LSN và log startup. Một standby được kết nối nhưng không replay không có nghĩa đã rejoin thành công.

---

## 34. Khác biệt giữa crash recovery, archive recovery và standby recovery

| Loại recovery | Mục tiêu | Hành vi sau recovery |
| --- | --- | --- |
| Crash recovery | Khôi phục cluster sau shutdown bất thường | Tiếp tục timeline hiện tại như primary nếu đó là primary |
| Archive recovery/PITR | Phát lại WAL archive tới target | Có thể pause, shutdown hoặc promote |
| Standby recovery | Theo WAL từ primary/stream/archive | Tiếp tục read-only standby cho tới promotion |
| Promotion | Kết thúc recovery và bắt đầu nhận ghi | Tạo timeline mới |
| Rewind/rejoin | Đưa data directory divergent về nhánh source | Cấu hình lại thành standby |

### 34.1. Crash recovery

Không mặc nhiên tạo timeline mới. Nó khôi phục trạng thái nhất quán của cùng cluster trên timeline hiện có.

### 34.2. Archive recovery

Dùng base backup và WAL archive. Có thể kết thúc ở recovery target.

### 34.3. Standby recovery

Tiếp tục nhận WAL từ upstream. Khi primary upstream chuyển timeline, standby cần history và WAL mới.

### 34.4. Promotion

Promotion là ranh giới chuyển vai trò và tạo nhánh lịch sử mới.

### 34.5. Rewind

Rewind không phải recovery replay đơn thuần. Nó sửa data directory target để loại bỏ divergence và theo source timeline.

---

## 35. Những lỗi thường gặp khi quản lý timeline

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không archive .history | Không lần được ancestry đúng | Kiểm tra archive tooling và giữ history files |
| Chỉ giữ segment number, bỏ TLI prefix | Ghi đè/nhầm nhánh | Giữ tên file đầy đủ |
| Chọn latest trong archive có nhiều nhánh | Restore nhầm lịch sử | Xác định và chọn TLI cụ thể |
| Promote trước khi fence primary cũ | Split brain | Fencing và quorum trước promotion |
| Primary cũ khởi động lại như primary | Hai nhánh cùng ghi | Rewind hoặc clone lại |
| Thiếu WAL từ fork point | Không thể follow/rewind | Lấy archive hoặc base backup mới |
| Xóa archive theo tuổi file | Backup cũ mất khả năng PITR | Cleanup theo backup dependency |
| Nhầm restore point với timeline | Recovery target sai | Phân biệt marker và branch |
| Nhầm checkpoint với promotion | Sai mô hình recovery | Checkpoint không tạo TLI |
| Chỉ so LSN, không ghi TLI | Đối chiếu sai hai nhánh | Ghi cả timeline và LSN |
| Đổi primary_conninfo nhưng bỏ qua divergence | Standby không replay được | Kiểm tra history/WAL, rewind/reclone |
| Dùng pg_rewind khi thiếu prerequisites | Lỗi hoặc target không thể rewind | Kiểm tra checksum/wal_log_hints/WAL |
| Dùng pg_rewind như backup | Mất bản dữ liệu target cần điều tra | Snapshot trước rewind |
| Giữ standby lag quá lâu | WAL bị recycle | Slot/archive/capacity planning |
| Tin synchronous replication tự chọn đúng node | Failover có thể chọn node sai | Kiểm tra quorum và sync state |
| Không test PITR trên timeline con | Không phát hiện archive path thiếu | Restore drills qua từng nhánh |
| Không giữ timeline history trong offsite archive | Khôi phục DR không đúng nhánh | Replicate history files |
| Hai site cùng promote | Split brain liên vùng | Fencing/quorum toàn topology |
| Cho rằng timeline merge hai primary | Mất hoặc xung đột nghiệp vụ | Reconcile ở tầng dữ liệu |
| Không ghi incident LSN/fork point | Khó điều tra sau failover | Lưu TLI, LSN, timestamp và history |

---

## 36. Bài tập thực hành

### Bài 1 — Khái niệm timeline

Giải thích timeline là gì và vì sao PostgreSQL cần timeline khi standby được promote.

### Bài 2 — Timeline và LSN

Phân biệt timeline ID và LSN. Vì sao phải ghi cả hai khi điều tra recovery?

### Bài 3 — Fork point

Vẽ timeline cha/con và đánh dấu fork point. WAL nào được dùng trước và sau điểm này?

### Bài 4 — Timeline history file

File .history chứa thông tin gì? Vì sao nó không thay thế WAL segment?

### Bài 5 — WAL filename

Phân tích ba phần của tên WAL segment và chỉ ra phần timeline ID.

### Bài 6 — Promotion

Mô tả trạng thái server trước và sau promotion. Vì sao promotion tạo timeline mới?

### Bài 7 — Crash recovery

Primary crash rồi restart trên cùng data directory. Vì sao việc này thường không tự tạo timeline mới?

### Bài 8 — Restore point

Dùng pg_create_restore_point() tạo marker. Vì sao marker không phải timeline?

### Bài 9 — pg_promote

Viết lệnh SQL kiểm tra và promote standby trong môi trường lab. Điều kiện nào cần xác nhận trước khi chạy?

### Bài 10 — pg_ctl promote

Viết lệnh pg_ctl promote và nêu khác biệt giữa công cụ OS-level với SQL function.

### Bài 11 — Signal files

Phân biệt standby.signal và recovery.signal. Tại sao hướng dẫn này khác PostgreSQL trước 12?

### Bài 12 — recovery_target_timeline

So sánh current, latest và một TLI cụ thể. Khi archive có nhiều nhánh, lựa chọn nào dễ kiểm soát nhất?

### Bài 13 — PITR

Thiết kế PITR tới một named restore point trên timeline 2 từ base backup timeline 1.

### Bài 14 — Recovery target time

Giải thích vai trò timezone và recovery_target_inclusive khi dừng theo thời gian.

### Bài 15 — Recovery target action

So sánh pause, promote và shutdown. Khi nào nên pause để kiểm tra dữ liệu?

### Bài 16 — Standby follow timeline

Một standby thứ ba còn theo timeline 1 sau khi standby thứ hai được promote timeline 2. Cần những files và WAL nào để nó theo nhánh mới?

### Bài 17 — Async replication

Primary mất trước khi standby nhận WAL cuối cùng. Điều gì có thể xảy ra khi promote standby?

### Bài 18 — Synchronous replication

Vì sao remote_flush có thể bảo vệ commit tốt hơn async replication? Những điều kiện nào vẫn cần xác nhận?

### Bài 19 — Split brain

Mô tả tình huống hai primary cùng nhận writes. Timeline có tự merge hoặc ngăn việc này không?

### Bài 20 — Fencing

Đề xuất các cơ chế fencing cho VM, bare metal hoặc cloud environment.

### Bài 21 — Primary cũ

Sau failover, primary cũ quay lại. Vì sao không được cho nó nhận writes ngay?

### Bài 22 — pg_rewind

Giải thích cách pg_rewind tìm common ancestor và cập nhật blocks thay đổi.

### Bài 23 — pg_rewind prerequisites

Nêu yêu cầu về clean shutdown, data checksums hoặc wal_log_hints, full_page_writes và WAL availability.

### Bài 24 — Base backup rejoin

Khi nào nên tạo lại standby bằng pg_basebackup thay vì pg_rewind?

### Bài 25 — Archive history

Vì sao thiếu một timeline history file có thể làm hỏng recovery path dù các WAL segments vẫn còn?

### Bài 26 — Multi-generation timelines

Vẽ timeline 1 -> timeline 2 -> timeline 3. Liệt kê WAL ranges cần cho một base backup từ timeline 1.

### Bài 27 — Archive retention

Thiết kế cleanup policy không xóa WAL/history files còn cần cho backup trong retention window.

### Bài 28 — LSN monitoring

Viết truy vấn lấy receive/replay LSN trên standby và sent/write/flush/replay LSN trên primary.

### Bài 29 — pg_controldata

Dùng pg_controldata để tìm checkpoint/timeline state. Vì sao cần kết hợp với SQL và logs?

### Bài 30 — Timeline ID cụ thể

Một archive có timeline 2 và timeline 3, trong đó timeline 3 là nhánh test. Vì sao latest có thể không phù hợp khi restore production?

### Bài 31 — Planned switchover

Lập trình tự dừng writes, đợi replay, promote và chuyển traffic để giảm data loss.

### Bài 32 — Failover runbook

Lập checklist phát hiện lỗi, fencing, chọn standby, promote, đổi traffic và rejoin replicas.

### Bài 33 — Restore drill

Thiết kế một bài test khôi phục từ base backup qua hai timeline history files tới một target cụ thể.

### Bài 34 — Archive integrity

Đề xuất cách kiểm tra checksum, continuity và immutable storage cho WAL segments và .history files.

### Bài 35 — Standby lag

Một standby không thể follow timeline mới vì thiếu WAL. Nêu các lựa chọn khôi phục và tiêu chí chọn.

### Bài 36 — pg_rewind failure

pg_rewind báo thiếu WAL từ điểm phân nhánh. Bạn sẽ lấy WAL từ đâu và khi nào cần base backup mới?

### Bài 37 — Ambiguous failover

Monitor không liên lạc được primary nhưng không biết primary có còn nhận writes. Vì sao cần fencing trước promotion?

### Bài 38 — Timeline và audit

Một DBA muốn dùng timeline history để biết user nào đã xóa bảng. Vì sao timeline không cung cấp thông tin đó? Cần logging nào?

### Bài 39 — Reconcile branches

Hai primary đã nhận writes trên hai nhánh khác nhau. Đề xuất cách bảo toàn và đối soát dữ liệu nghiệp vụ.

### Bài 40 — Thiết kế end-to-end

Một hệ thống PostgreSQL đa vùng có một primary, hai synchronous standbys và WAL archive 14 ngày. Thiết kế promotion/failover, timeline selection, archive retention, PITR, pg_rewind/rebuild, fencing và restore drills. Nêu rõ trade-off giữa RPO, RTO, availability, latency và chi phí.

---

## 37. Checklist vận hành Timeline, Promotion và Recovery History

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Timeline hiện tại là gì? | TLI trong control/history |
| LSN hiện tại và replay LSN? | Ghi cùng timeline |
| Có fork point nào? | Timeline history |
| History files có được archive? | Archive inventory |
| WAL segment filenames giữ TLI prefix? | Archive naming |
| Có WAL liên tục từ base backup? | Backup/WAL manifest |
| Có nhiều nhánh trong archive? | Timeline tree |
| Recovery target chọn đúng nhánh? | recovery_target_timeline |
| Target time có timezone rõ? | Recovery config |
| Target action có phù hợp? | pause/promote/shutdown |
| Base backup thuộc timeline nào? | Backup metadata |
| Archive giữ đủ ancestry? | Parent WAL/history |
| Standby có follow latest đúng? | standby.signal/config |
| Receive/replay lag? | LSNs và monitoring |
| Sync standby đúng node? | sync_state/quorum |
| Primary cũ đã fence? | HA control plane |
| Promotion hoàn tất? | pg_is_in_recovery() |
| Timeline mới đã được tạo? | Control/history/archive |
| Traffic ghi đã chuyển? | Application routing |
| Replica khác đã rejoin? | Receiver/replay state |
| Có thể dùng pg_rewind? | Prerequisites |
| Target đã shutdown cleanly? | pg_rewind requirement |
| Checksums hoặc wal_log_hints? | Target cluster setup |
| full_page_writes phù hợp? | Cluster setting |
| WAL fork point còn đủ? | Local/archive WAL |
| Có snapshot trước rewind? | Recovery safety |
| Nếu rewind không được, có base backup? | Rebuild plan |
| Không có hai primary? | Fencing/quorum |
| Archive cleanup theo backup dependency? | Retention catalog |
| History files được giữ offsite? | DR archive |
| PITR đã test qua nhiều TLI? | Restore drills |
| Restore data được xác minh? | Application checks |
| RPO/RTO có được đo? | DR evidence |
| Incident record có TLI/LSN? | Operational history |
| Rollback/failback có kế hoạch? | Rejoin runbook |
| Archive có checksum/immutability? | Integrity/security |
| Có cảnh báo slot/WAL retention? | Capacity alerts |

## Kết luận

Timeline là cơ chế PostgreSQL dùng để quản lý các nhánh lịch sử WAL sau promotion hoặc recovery. Nó giúp database biết một nhánh bắt nguồn từ đâu, WAL nào thuộc nhánh nào và cần phát lại những segments nào để khôi phục đúng trạng thái.

Những nguyên tắc quan trọng:

1. **Timeline định danh nhánh WAL.** LSN biểu diễn vị trí trong WAL; cần dùng cả timeline và LSN khi phân tích lịch sử.
2. **Promotion tạo timeline mới.** Standby được promote bắt đầu nhận writes trên nhánh con từ fork point.
3. **Crash recovery bình thường không tự tạo timeline mới.** Restart primary trên cùng lịch sử thường tiếp tục timeline hiện tại.
4. **History file mô tả ancestry.** File .history ghi timeline cha và fork point; nó cần được archive cùng WAL segments.
5. **WAL segment filename chứa timeline ID.** Giữ nguyên tên đầy đủ để không nhầm hoặc ghi đè các nhánh.
6. **PITR cần base backup và WAL liên tục.** Khi có nhiều nhánh, chọn recovery_target_timeline rõ ràng để phục hồi đúng lịch sử.
7. **Standby phải theo timeline của primary mới.** Cần history files, WAL từ fork point và cấu hình follow phù hợp.
8. **Synchronous replication ảnh hưởng lượng WAL có thể mất khi failover.** Xác nhận sync policy, standby được chọn và replay/flush state.
9. **Fencing ngăn split brain.** Timeline phân biệt các nhánh nhưng không ngăn hai primary cùng nhận ghi.
10. **Primary cũ cần rewind hoặc rebuild.** Không cho node ở nhánh cũ nhận writes như primary độc lập sau failover.
11. **pg_rewind có điều kiện tiên quyết.** Cần clean shutdown, checksums hoặc wal_log_hints, full_page_writes và WAL đủ từ điểm phân nhánh.
12. **Archive retention phải xét toàn bộ cây timeline.** Không xóa history/WAL còn cần cho base backups và PITR trong retention window.
13. **Restore drills phải kiểm tra nhánh thật.** Một backup chỉ đáng tin khi có thể restore qua history files, replay WAL và xác minh dữ liệu ở target.
14. **Lưu lại bằng chứng promotion.** Ghi TLI, LSN, fork point, timestamp, history file, archive status và node được fencing.

Một quy trình khôi phục đáng tin cậy phải trả lời được ba câu hỏi: server đang ở timeline nào, timeline đó kế thừa WAL từ nhánh nào và dữ liệu cần thiết để phục hồi tới mục tiêu có còn đầy đủ hay không. Khi failover, promotion, PITR và rejoin được quản lý theo cùng một lịch sử rõ ràng, PostgreSQL có thể tiếp tục phục vụ trên nhánh đúng mà không nhầm lẫn các thay đổi của những nhánh đã phân kỳ.
