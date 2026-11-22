# Doublewrite buffer và bảo vệ trước ghi trang chưa hoàn chỉnh

InnoDB lưu dữ liệu theo page. Khi một page bẩn trong buffer pool được ghi xuống data file, thao tác ghi có thể bị gián đoạn giữa chừng do mất điện, hệ điều hành dừng đột ngột hoặc thiết bị lưu trữ gặp sự cố. Kết quả là page trên đĩa chỉ chứa một phần dữ liệu mới và phần còn lại vẫn là dữ liệu cũ. Hiện tượng này thường được gọi là **torn page** (trang bị ghi xé hoặc ghi chưa hoàn chỉnh).

InnoDB dùng **doublewrite buffer** để giữ một bản ghi đầy đủ của page trước khi ghi page đó vào vị trí chính thức trong tablespace. Nếu crash làm page ở vị trí chính thức bị hỏng, InnoDB có thể khôi phục page từ bản sao doublewrite rồi áp dụng redo log. Cơ chế này bổ sung cho redo log: redo bảo vệ khả năng phục hồi các thay đổi đã ghi log, còn doublewrite giúp phục hồi một page bị ghi dở.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao một lần ghi page có thể không hoàn chỉnh và gây torn page.
- Mô tả luồng flush page bẩn từ buffer pool qua doublewrite buffer đến data file.
- Phân biệt vai trò của doublewrite buffer, redo log, undo log và binary log.
- Dự đoán cách InnoDB phục hồi khi crash xảy ra ở các thời điểm khác nhau của quá trình flush.
- Kiểm tra cấu hình và số liệu doublewrite, đồng thời đánh giá rủi ro khi tắt cơ chế này.

Các ví dụ giả định MySQL 8.0 trở lên và bảng dùng storage engine InnoDB.

## 1. Vì sao page có thể bị ghi chưa hoàn chỉnh?

InnoDB đọc và ghi dữ liệu theo page. Kích thước page mặc định thường là 16 KiB, nhưng có thể được cấu hình khi khởi tạo instance. Một page có thể chứa nhiều hàng hoặc một phần cấu trúc chỉ mục. Khi page bẩn được flush, InnoDB yêu cầu hệ điều hành và thiết bị lưu trữ ghi page đó xuống vị trí tương ứng trong file tablespace.

Không phải mọi tầng lưu trữ đều bảo đảm một lần ghi 16 KiB là nguyên tử. Thiết bị có thể ghi theo sector nhỏ hơn; một lần ghi page có thể được chia thành nhiều thao tác vật lý. Nếu nguồn điện mất hoặc hệ thống dừng ở giữa quá trình, một phần sector mới có thể đã được ghi trong khi phần còn lại vẫn là nội dung cũ.

Ví dụ minh họa một page gồm bốn vùng ghi:

```text
Trước khi flush:       Sau khi ghi bị gián đoạn:
+------+------+------+    +------+------+------+
| cũ   | cũ   | cũ   |    | mới  | mới  | cũ   |
+------+------+------+    +------+------+------+
| cũ   |                   | cũ   |
+------+                   +------+
```

Page sau sự cố có thể chứa hỗn hợp dữ liệu cũ và mới. Header, trailer, checksum hoặc cấu trúc record có thể không còn nhất quán. Nếu page là một node của B-tree, lỗi này có thể ảnh hưởng đến khả năng đọc hàng hoặc duyệt chỉ mục.

**Torn page khác với mất một transaction đã commit.** Một transaction có thể đã ghi redo log bền vững nhưng page dữ liệu tương ứng chưa được flush. Khi server khởi động lại, redo log có thể phát lại thay đổi. Nhưng nếu page nền đã bị ghi xé, InnoDB trước hết cần một bản page hợp lệ để làm nền cho quá trình recovery. Đây là vấn đề doublewrite giải quyết.

## 2. Doublewrite buffer hoạt động như thế nào?

Khi InnoDB flush một nhóm page bẩn từ buffer pool, cơ chế doublewrite thực hiện hai bước ghi:

1. Ghi các page vào vùng doublewrite và bảo đảm bản sao này đã được flush xuống lưu trữ.
2. Sau đó ghi các page vào vị trí chính thức của chúng trong data file hoặc tablespace.

Có thể hình dung luồng dữ liệu:

```text
Transaction thay đổi dữ liệu
          |
          v
       Buffer pool
       (page bẩn)
          |
          v
  Doublewrite buffer
  ghi bản sao page đầy đủ
          |
       flush hoàn tất
          |
          v
  Data file / tablespace
  ghi page vào vị trí chính
```

Bản sao doublewrite là một page đầy đủ, được ghi theo batch. Khi page chính thức được ghi xong, vùng doublewrite có thể được tái sử dụng cho batch tiếp theo. Doublewrite không phải một bản sao lưu dài hạn của database; nó là vùng trung gian phục vụ bảo vệ và phục hồi page trong quá trình ghi.

### Vì sao phải ghi bản sao trước?

Thứ tự là yếu tố quyết định. Nếu InnoDB ghi page chính thức trước rồi mới ghi bản sao, crash ở giữa lần ghi đầu tiên có thể làm mất page cũ mà chưa có bản sao hợp lệ. Khi ghi bản sao doublewrite trước và flush bản sao đó, InnoDB có một page hoàn chỉnh để khôi phục nếu lần ghi vào vị trí chính thức bị gián đoạn.

Doublewrite được tổ chức để ghi nhiều page thành batch, giúp giảm chi phí I/O so với việc tạo một bản sao riêng bằng một thao tác ngẫu nhiên cho từng page. Sau khi batch doublewrite đã được ghi bền vững, các page mới được ghi về vị trí chính thức.

## 3. Doublewrite phối hợp với redo log

Doublewrite và redo log giải quyết hai phần khác nhau của quá trình phục hồi.

| Thành phần | Vai trò | Câu hỏi nó trả lời |
|---|---|---|
| Redo log | Ghi lại thay đổi cần phát lại để phục hồi trạng thái database sau crash | Những thay đổi đã được log cần được áp dụng lại như thế nào? |
| Doublewrite buffer | Giữ bản page đầy đủ trước khi page được ghi vào vị trí chính thức | Nếu page trên data file bị ghi xé, lấy page hợp lệ từ đâu? |
| Undo log | Lưu thông tin cần để rollback và dựng phiên bản cũ cho MVCC | Cần hoàn tác thay đổi chưa commit hoặc đọc phiên bản cũ nào? |
| Binary log | Ghi sự kiện thay đổi ở cấp server để replication và point-in-time recovery | Những sự kiện SQL/row nào cần được replica hoặc khôi phục theo thời điểm? |

Redo log tuân theo nguyên tắc write-ahead logging: thông tin redo liên quan phải được ghi bền vững trước khi page dữ liệu tương ứng được ghi xuống vị trí chính thức. Điều này cho phép InnoDB phát lại thay đổi sau crash ngay cả khi page bẩn chưa được flush.

Tuy nhiên, redo log không phải lúc nào cũng là bản thay thế cho một page đầy đủ. Nếu page trên đĩa bị torn, khôi phục một bản page hợp lệ từ doublewrite trước rồi áp dụng redo là cách InnoDB có thể phục hồi cấu trúc page một cách an toàn.

## 4. Crash xảy ra ở thời điểm nào?

Giả sử page `P` trong buffer pool đã được thay đổi và cần flush. Các tình huống sau minh họa vai trò của doublewrite:

| Thời điểm crash | Trạng thái có thể gặp | Hướng phục hồi |
|---|---|---|
| Trước khi bản sao doublewrite được ghi bền vững | Page chính thức vẫn là bản cũ; page mới có thể chỉ còn trong bộ nhớ | InnoDB dùng redo log để phát lại các thay đổi cần thiết |
| Sau khi doublewrite đã flush, trước khi ghi page chính thức | Bản sao đầy đủ đã có trong vùng doublewrite; page chính thức có thể vẫn cũ | InnoDB có thể dùng bản sao hợp lệ rồi áp dụng redo nếu cần |
| Trong lúc ghi page chính thức | Page chính thức có thể bị torn; bản sao doublewrite đã được ghi trước đó | InnoDB phát hiện page không hợp lệ, phục hồi từ bản sao doublewrite rồi áp dụng redo |
| Sau khi page chính thức ghi hoàn tất | Page chính thức đã được ghi; bản sao trung gian có thể được tái sử dụng sau đó | Recovery thông thường kiểm tra redo và trạng thái page |

Khi crash recovery, InnoDB kiểm tra page và các bản sao doublewrite có liên quan. Nếu phát hiện page chính thức bị hỏng nhưng có bản sao hợp lệ, engine phục hồi page từ doublewrite rồi tiếp tục quá trình áp dụng redo log từ checkpoint. Cơ chế kiểm tra page như checksum giúp phát hiện một số dạng page không hợp lệ.

Không nên hiểu bảng trên như cam kết rằng mọi loại hỏng lưu trữ đều sửa được. Doublewrite chỉ hữu ích khi bản sao của page còn nguyên vẹn và có thể đọc được. Nếu cả vùng doublewrite lẫn page chính thức đều bị hỏng, hoặc thiết bị mất hoàn toàn dữ liệu, cần dùng backup và quy trình phục hồi phù hợp.

## 5. Checksum giúp phát hiện page bất thường

InnoDB lưu thông tin checksum trong page để kiểm tra tính toàn vẹn khi đọc hoặc phục hồi. Nếu nội dung page bị thay đổi ngoài dự kiến hoặc ghi không hoàn chỉnh, checksum có thể không khớp và engine phát hiện page có vấn đề.

Checksum và doublewrite có vai trò bổ sung:

- Checksum giúp phát hiện page không hợp lệ.
- Doublewrite cung cấp một bản page đầy đủ để phục hồi trong trường hợp page chính thức bị torn.
- Redo log phát lại các thay đổi cần thiết sau khi có page nền hợp lệ.

Checksum không tự sửa dữ liệu. Một checksum hợp lệ cũng không chứng minh dữ liệu đúng về mặt nghiệp vụ; một thao tác SQL sai vẫn có thể tạo page hợp lệ với giá trị sai.

Có thể xem thuật toán checksum đang cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_checksum_algorithm';
```

Không thay đổi thuật toán checksum hoặc tắt checksum trong môi trường đang chạy chỉ để xử lý một cảnh báo page. Hãy kiểm tra tương thích phiên bản, quy trình backup/restore và tài liệu vận hành trước khi thay đổi cấu hình liên quan.

## 6. Vị trí lưu doublewrite theo phiên bản MySQL

Vị trí vật lý của vùng doublewrite phụ thuộc phiên bản MySQL:

- Trước MySQL 8.0.20, vùng doublewrite được lưu trong system tablespace.
- Từ MySQL 8.0.20, các vùng lưu doublewrite được đặt trong những file doublewrite riêng, cho phép InnoDB tổ chức ghi batch độc lập hơn với system tablespace.

Với các phiên bản mới, tên file và cách tổ chức có thể do InnoDB quản lý. Không xóa, đổi tên hoặc di chuyển thủ công các file doublewrite khi server đang chạy. Khi thay đổi thư mục dữ liệu, cấu hình đường dẫn doublewrite hoặc khôi phục từ backup, hãy dùng quy trình được hỗ trợ cho đúng phiên bản.

Một số biến cấu hình có thể xuất hiện tùy phiên bản:

| Biến | Ý nghĩa khái quát |
|---|---|
| `innodb_doublewrite` | Bật/tắt hoặc chọn chế độ doublewrite được phiên bản hỗ trợ |
| `innodb_doublewrite_dir` | Thư mục lưu file doublewrite trên các phiên bản hỗ trợ cấu hình này |
| `innodb_doublewrite_files` | Số file doublewrite mà InnoDB tổ chức sử dụng theo cấu hình phiên bản |
| `innodb_doublewrite_pages` | Giới hạn số page được ghi trong một batch theo cấu hình phiên bản |

Không phải mọi biến trên đều có trong mọi bản phát hành. Kiểm tra `SHOW VARIABLES` trên đúng server trước khi dựa vào chúng trong automation hoặc runbook.

## 7. Có nên tắt doublewrite không?

Thông thường nên giữ doublewrite bật. Cơ chế này là một lớp bảo vệ trước rủi ro page bị ghi chưa hoàn chỉnh, đặc biệt khi hệ điều hành hoặc thiết bị lưu trữ không bảo đảm atomic write cho kích thước page InnoDB.

Tắt doublewrite có thể giảm một phần I/O ghi, nhưng đồng thời loại bỏ lớp bảo vệ page mà InnoDB dựa vào trong crash recovery. Chỉ cân nhắc khi nền tảng lưu trữ có bảo đảm atomic page write được MySQL hỗ trợ rõ ràng, đã xác minh trên đúng phiên bản và phần cứng, đồng thời chấp nhận rủi ro còn lại. Không nên tắt chỉ vì một benchmark ngắn cho thấy số lần ghi giảm.

Trước khi thay đổi:

1. Xác nhận model thiết bị, firmware, controller, cache và nguồn điện có bảo vệ khi mất điện.
2. Kiểm tra hệ thống file và chế độ I/O mà MySQL đang dùng có duy trì đúng bảo đảm atomic write hay không.
3. Đọc tài liệu MySQL cho đúng phiên bản và nền tảng triển khai.
4. Thử nghiệm workload thực tế, crash recovery và backup/restore trên môi trường cô lập.
5. Ghi lại cấu hình cũ, quy trình rollback và người chịu trách nhiệm phê duyệt rủi ro.

Doublewrite có thể tạo thêm I/O, nhưng chi phí thực tế phụ thuộc workload, thiết bị lưu trữ và cách InnoDB batch page. Hãy đo latency, throughput và thời gian recovery trước khi quyết định tối ưu.

## 8. Kiểm tra cấu hình và hoạt động

Đọc giá trị doublewrite hiện tại:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite';
```

Kiểm tra các biến doublewrite mà server đang hỗ trợ:

```sql
SHOW VARIABLES LIKE 'innodb_doublewrite%';
```

Xem các bộ đếm hoạt động:

```sql
SHOW GLOBAL STATUS LIKE 'Innodb_dblwr%';
```

Hai bộ đếm thường hữu ích là:

- `Innodb_dblwr_pages_written`: tổng số page đã được ghi qua cơ chế doublewrite.
- `Innodb_dblwr_writes`: tổng số lần ghi batch doublewrite.

Đọc bộ đếm hai lần cách nhau một khoảng thời gian để tính mức tăng. Tỷ lệ `pages_written / writes` trong khoảng đo giúp hình dung số page trung bình mỗi batch. Đây là bộ đếm tích lũy từ khi server khởi động; không dùng một giá trị tuyệt đối để kết luận hệ thống đang chậm hoặc có lỗi.

Có thể kết hợp thông tin flush và trạng thái InnoDB:

```sql
SHOW ENGINE INNODB STATUS;
```

Đối chiếu số liệu doublewrite với dirty pages trong buffer pool, tốc độ page cleaner, redo log, độ trễ thiết bị và workload. Doublewrite tăng là hoạt động bình thường khi page được flush; nó không tự động có nghĩa là đã xảy ra torn page.

## 9. Doublewrite không thay thế backup và các lớp bảo vệ khác

Doublewrite có phạm vi hẹp: bảo vệ page trong đường ghi của InnoDB. Nó không thay thế:

- **Backup:** cần thiết khi mất file, mất thiết bị, xóa nhầm dữ liệu hoặc hỏng lan rộng.
- **Binary log và point-in-time recovery:** giúp khôi phục đến một thời điểm dựa trên backup và binlog.
- **Replication:** cung cấp bản sao dữ liệu ở server khác, nhưng vẫn cần backup và kiểm tra tính nhất quán.
- **Redo log:** bảo đảm phát lại thay đổi cần thiết sau crash.
- **Checksum và giám sát:** giúp phát hiện một số dạng hỏng page và theo dõi hoạt động.

Nếu gặp lỗi checksum hoặc thông báo page corruption, hãy giữ nguyên bằng chứng, kiểm tra error log, xác định tablespace/page liên quan và đánh giá backup gần nhất. Tránh thử nghiệm ghi đè trực tiếp lên file dữ liệu hoặc xóa file doublewrite để làm server khởi động. Các chế độ force recovery chỉ phục vụ tình huống cứu dữ liệu có kiểm soát; chúng không phải cách sửa page hỏng thông thường.

## 10. Bài thực hành

Trên một MySQL instance thử nghiệm, không dùng dữ liệu production:

1. Kiểm tra `innodb_doublewrite`, `innodb_checksum_algorithm` và các biến `innodb_doublewrite%` đang có.
2. Đọc `Innodb_dblwr_pages_written` và `Innodb_dblwr_writes`, chờ một khoảng thời gian có workload ghi, rồi đọc lại để tính số page và số batch tăng thêm.
3. Chạy workload cập nhật nhiều hàng InnoDB và quan sát bộ đếm doublewrite cùng trạng thái `SHOW ENGINE INNODB STATUS`.
4. Vẽ lại thứ tự ghi: redo log, doublewrite area và vị trí page chính thức. Giải thích vì sao bản sao doublewrite phải được ghi bền vững trước page chính thức.
5. Mô tả cách recovery xử lý khi page chính thức có checksum không hợp lệ nhưng bản sao doublewrite còn nguyên.
6. Giải thích vì sao doublewrite không thể thay thế backup khi thiết bị lưu trữ bị mất hoàn toàn.

Không cố tình ngắt điện hoặc kill tiến trình database trên máy đang chứa dữ liệu thật để thử torn page. Nếu cần thử crash recovery, hãy dùng máy ảo hoặc instance dùng dữ liệu giả, snapshot có thể phục hồi và quy trình thử nghiệm riêng.

## Ghi nhớ

- Torn page xảy ra khi page bị ghi dở và có thể chứa hỗn hợp dữ liệu cũ/mới.
- Doublewrite ghi bản page đầy đủ vào vùng trung gian và flush bản sao trước khi ghi page vào vị trí chính thức.
- Khi page chính thức bị hỏng, InnoDB có thể phục hồi từ bản sao doublewrite rồi áp dụng redo log.
- Redo log, undo log, doublewrite và binary log có mục đích khác nhau; không cơ chế nào thay thế hoàn toàn các cơ chế còn lại.
- Giữ doublewrite bật trừ khi nền tảng atomic write được MySQL hỗ trợ và xác minh rõ ràng.
- Theo dõi bộ đếm doublewrite theo mức tăng trong khoảng thời gian, đồng thời kiểm tra page cleaner, redo và độ trễ lưu trữ.
- Doublewrite không phải backup; vẫn cần backup đã kiểm thử restore và quy trình phục hồi khi mất thiết bị hoặc hỏng lan rộng.
