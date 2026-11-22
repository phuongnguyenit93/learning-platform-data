# Bảo mật

## Audit, Enterprise Audit và ranh giới với general/slow log

Trong module `DATABASE_MYSQL`, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Audit nối các kỹ năng đó với yêu cầu bảo mật: khi có một hoạt động đáng chú ý trong cơ sở dữ liệu, đội vận hành cần biết **ai** đã thực hiện, **khi nào**, từ **đâu**, trên **đối tượng nào**, và thao tác có **thành công** hay không.

Bài này phân biệt MySQL Enterprise Audit với general query log và slow query log. Ba cơ chế đều có thể ghi nhận hoạt động SQL, nhưng chúng phục vụ các mục tiêu khác nhau. Chọn nhầm cơ chế có thể khiến hệ thống ghi quá nhiều dữ liệu nhạy cảm mà vẫn không có đủ bằng chứng cho một cuộc điều tra bảo mật.

### 1. Audit database là gì?

Audit database là việc ghi nhận có chủ đích các sự kiện liên quan đến bảo mật và tuân thủ. Một bản ghi audit hữu ích thường trả lời được những câu hỏi sau:

- **Who:** tài khoản MySQL nào thực hiện thao tác? Nếu cần xác định người dùng cuối, ứng dụng phải cung cấp thêm danh tính nghiệp vụ.
- **When:** sự kiện xảy ra lúc nào? Đồng bộ đồng hồ giữa MySQL, máy ứng dụng và hệ thống thu thập log để đối chiếu chính xác.
- **Where:** kết nối đến từ máy khách, địa chỉ hoặc dịch vụ nào?
- **What:** thao tác nào được thực hiện, trên schema, bảng hay tài nguyên nào?
- **Outcome:** thao tác thành công, thất bại hay bị từ chối?

Những sự kiện thường cần xem xét gồm đăng nhập thành công hoặc thất bại, ngắt kết nối, thay đổi tài khoản và quyền, thao tác DDL, thay đổi dữ liệu, truy cập bảng nhạy cảm và lệnh quản trị. Phạm vi thực tế phụ thuộc chính sách của tổ chức, loại dữ liệu và yêu cầu điều tra.

Audit khác với việc chỉ lưu lịch sử nghiệp vụ trong ứng dụng. Một bảng lịch sử đơn hàng có thể ghi người dùng đổi trạng thái đơn hàng, nhưng không nhất thiết cho biết tài khoản DBA nào đã chạy một câu `UPDATE` trực tiếp. Ngược lại, log ở tầng MySQL thường biết tài khoản kết nối và câu lệnh, nhưng không tự hiểu người dùng cuối, mã yêu cầu HTTP hay lý do nghiệp vụ. Với hệ thống quan trọng, hai lớp này bổ sung cho nhau.

### 2. MySQL Enterprise Audit

MySQL Enterprise Audit là plugin audit thuộc MySQL Enterprise Edition. Plugin nhận các sự kiện từ máy chủ MySQL và ghi chúng vào audit log theo định dạng, chính sách và bộ lọc được cấu hình. Tùy phiên bản và cấu hình, các nhóm sự kiện có thể bao gồm kết nối, câu lệnh SQL và truy cập bảng.

Điểm mạnh của Enterprise Audit là khả năng chọn sự kiện cần ghi theo chính sách. Ví dụ, tổ chức có thể yêu cầu ghi nhận hoạt động của tài khoản quản trị, thay đổi quyền, hoặc truy cập vào các bảng chứa dữ liệu nhạy cảm. Bộ lọc cần được thiết kế và kiểm thử theo phiên bản MySQL đang chạy; không nên giả định mọi phiên bản có cùng cú pháp hay cùng tập sự kiện.

**Cài đặt và kiểm tra plugin**

Plugin phải có sẵn trong gói cài đặt Enterprise tương ứng. Trên hệ thống dùng thư viện plugin dạng `.so`, có thể cài bằng câu lệnh sau:

```sql
INSTALL PLUGIN audit_log SONAME 'audit_log.so';

SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'audit_log';

SHOW VARIABLES LIKE 'audit_log%';
```

Trên Windows, tên thư viện thường có phần mở rộng `.dll`. Có thể cấu hình nạp plugin khi máy chủ khởi động bằng `plugin-load-add` trong cấu hình MySQL. Chọn một phương thức nạp phù hợp với cách triển khai của máy chủ và kiểm tra trạng thái plugin sau khi khởi động. Không chạy lệnh cài đặt nếu plugin chưa được cung cấp hoặc không tương thích với phiên bản máy chủ.

**Bộ lọc sự kiện**

Các phiên bản Enterprise Audit hỗ trợ bộ lọc qua các hàm quản lý filter. Ví dụ dưới đây tạo một filter ghi mọi sự kiện rồi gán filter cho một tài khoản thử nghiệm:

```sql
SELECT audit_log_filter_set_filter(
  'audit_all_for_lab',
  '{"filter":{"log":true}}'
);

SELECT audit_log_filter_set_user(
  'app_user@localhost',
  'audit_all_for_lab'
);
```

Đây là cấu hình rộng để kiểm tra trong môi trường lab. Ghi tất cả sự kiện của tài khoản có thể tạo log lớn và thu thập nhiều câu lệnh chứa dữ liệu nhạy cảm. Trong môi trường thật, hãy tạo filter theo nhu cầu: nhóm tài khoản, loại sự kiện, câu lệnh hoặc đối tượng cần bảo vệ. Cú pháp JSON và khả năng lọc cụ thể phải đối chiếu với tài liệu của đúng phiên bản MySQL Enterprise Audit.

Sau khi cấu hình, hãy đăng nhập bằng tài khoản thử nghiệm, thực hiện các thao tác đã chọn, rồi xác minh audit log có đủ thông tin về thời điểm, tài khoản, sự kiện và kết quả. Cũng cần thử một thao tác không thuộc filter để chắc chắn chính sách không ghi thừa hoặc bỏ sót ngoài dự kiến.

**Giới hạn cần hiểu rõ**

- Audit log chỉ ghi những sự kiện mà plugin hỗ trợ và filter cho phép. Một sự kiện không xuất hiện trong log chưa chứng minh rằng thao tác đó không xảy ra.
- Audit plugin không mặc nhiên lưu ảnh chụp trước và sau của từng hàng dữ liệu. Nếu cần lịch sử giá trị cũ/mới hoặc ngữ cảnh nghiệp vụ, hãy bổ sung audit ở ứng dụng hoặc cơ chế lưu lịch sử phù hợp.
- Audit log trên máy chủ không tự trở thành bằng chứng bất biến. Người có quyền quản trị hệ điều hành hoặc máy chủ có thể tác động đến tệp log. Hãy chuyển log sang hệ thống tập trung có kiểm soát quyền và cơ chế chống sửa đổi.
- Ghi audit có chi phí CPU, I/O và dung lượng. Filter quá rộng có thể làm tăng tải và khiến việc tìm kiếm sự kiện quan trọng khó hơn.

### 3. General query log

General query log ghi nhận các kết nối và câu lệnh mà máy chủ nhận được. Đây là công cụ hữu ích khi cần quan sát nhanh ứng dụng đang gửi gì đến MySQL, xác định một câu lệnh có thực sự được gửi hay kiểm tra trình tự thao tác trong một phiên gỡ lỗi.

General log không phải một chính sách audit đầy đủ. Nó thiên về ghi nhận hoạt động truy vấn nói chung, không chọn lọc theo mục tiêu bảo mật ở mức chi tiết như Enterprise Audit. Nó cũng không cho biết truy vấn chậm đến đâu; mục tiêu chính là ghi nhận hoạt động nhận được.

**Bật tạm thời để điều tra**

```sql
SHOW VARIABLES LIKE 'general_log';
SHOW VARIABLES LIKE 'log_output';

SET GLOBAL log_output = 'FILE';
SET GLOBAL general_log = ON;

-- Tái hiện thao tác cần quan sát trong khoảng thời gian ngắn.

SET GLOBAL general_log = OFF;
```

`log_output` quyết định log được ghi ra `FILE`, `TABLE` hoặc tắt bằng `NONE`. Khi dùng `TABLE`, có thể đọc dữ liệu từ `mysql.general_log`; khi dùng `FILE`, cần biết đường dẫn tệp log và bảo vệ quyền truy cập ở hệ điều hành. Thiết lập `SET GLOBAL` có hiệu lực ở cấp máy chủ; quyền cần thiết phụ thuộc phiên bản MySQL và mô hình quản trị quyền đang dùng.

Không nên bật general log liên tục trên máy chủ tải cao nếu chưa đánh giá tác động. Log có thể tăng rất nhanh và chứa giá trị tham số hoặc dữ liệu mà ứng dụng đưa vào câu lệnh. Dù MySQL có xử lý che một số thông tin xác thực, bạn vẫn phải xem nội dung log là dữ liệu nhạy cảm, giới hạn người đọc và thời gian lưu.

### 4. Slow query log

Slow query log ghi những câu lệnh vượt ngưỡng thời gian được cấu hình, cùng một số điều kiện lọc khác. Mục tiêu của nó là tìm truy vấn cần tối ưu, chẳng hạn truy vấn đọc quá nhiều hàng, thiếu index hoặc chờ khóa lâu.

Các biến thường dùng gồm:

- `slow_query_log`: bật hoặc tắt slow query log.
- `long_query_time`: ngưỡng thời gian tính bằng giây; truy vấn phải vượt ngưỡng này mới đủ điều kiện được ghi.
- `min_examined_row_limit`: số hàng tối thiểu cần được kiểm tra để truy vấn được ghi.
- `log_queries_not_using_indexes`: tùy chọn ghi thêm truy vấn không dùng index; bật tùy chọn này có thể tạo nhiều log.
- `log_slow_admin_statements`: cho phép ghi một số câu lệnh quản trị chậm.

Ví dụ cấu hình tạm thời để tìm truy vấn có thời gian trên một giây và đã kiểm tra ít nhất 100 hàng:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL min_examined_row_limit = 100;

SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
```

Thay ngưỡng bằng số liệu thực tế của hệ thống. Một giây có thể quá cao với API cần phản hồi vài chục mili giây, nhưng lại quá thấp với một tác vụ báo cáo dài. `long_query_time` có cả phạm vi global và session; thay đổi global thường ảnh hưởng đến các kết nối mới, trong khi session variable có thể được đặt riêng cho phiên hiện tại.

Slow query log không ghi mọi câu lệnh. Một truy vấn nhanh đọc dữ liệu nhạy cảm có thể không xuất hiện; một truy vấn thay đổi quyền nhưng chạy nhanh cũng có thể không xuất hiện. Vì vậy, không dùng slow query log để chứng minh ai đã truy cập dữ liệu hoặc để đáp ứng yêu cầu audit toàn diện.

Sau khi xác định truy vấn đáng chú ý, hãy dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` (nếu phiên bản hỗ trợ) để phân tích kế hoạch thực thi. Slow query log giúp tìm truy vấn cần xem xét; kế hoạch thực thi giúp giải thích cách MySQL dự định hoặc thực sự thực hiện truy vấn.

### 5. So sánh các cơ chế ghi nhận

| Cơ chế | Mục tiêu chính | Phạm vi ghi nhận | Không nên dùng để |
|---|---|---|---|
| MySQL Enterprise Audit | Audit bảo mật theo chính sách | Các lớp sự kiện được plugin hỗ trợ và filter cho phép, như kết nối, câu lệnh hoặc truy cập bảng | Mặc định suy ra ảnh trước/sau của từng hàng hoặc bằng chứng bất biến |
| General query log | Quan sát hoạt động SQL và kết nối | Kết nối và câu lệnh máy chủ nhận được | Đo hiệu năng truy vấn hoặc làm chính sách audit duy nhất |
| Slow query log | Chẩn đoán truy vấn chậm | Truy vấn vượt ngưỡng và các điều kiện cấu hình | Theo dõi toàn bộ truy cập dữ liệu hoặc thay đổi quyền |
| Binary log | Replication và phục hồi theo thời điểm | Các thay đổi được ghi theo định dạng binlog; không phải toàn bộ câu lệnh đọc | Theo dõi mọi lần đọc hoặc thay thế audit log |
| Audit ở ứng dụng | Lịch sử nghiệp vụ và danh tính người dùng cuối | Sự kiện mà ứng dụng chủ động ghi, có thể kèm request ID và giá trị trước/sau | Phát hiện thao tác trực tiếp ngoài ứng dụng nếu không có cơ chế ở tầng MySQL |

Binary log thường được nhắc đến cùng general và slow log vì cả ba đều là log của MySQL, nhưng mục tiêu khác nhau. Binary log phục vụ sao chép dữ liệu và phục hồi; tùy `binlog_format`, nó ghi câu lệnh hoặc sự kiện thay đổi hàng. Nó không ghi mọi câu `SELECT`, và không nên được xem là nhật ký truy cập bảo mật.

### 6. Thiết kế chính sách audit có thể điều tra được

Trước khi bật log, hãy viết rõ câu hỏi mà đội vận hành cần trả lời. Ví dụ: “Ai đã đọc bảng chứa thông tin thanh toán?”, “Tài khoản nào đã cấp quyền `SELECT` cho tài khoản khác?” hoặc “Có đăng nhập thất bại từ một máy chủ lạ hay không?”. Từ câu hỏi đó, xác định sự kiện, tài khoản, đối tượng và thời gian lưu cần thiết.

**Danh tính tài khoản.** Tránh dùng chung một tài khoản MySQL cho nhiều người hoặc nhiều dịch vụ. Tạo tài khoản riêng theo ứng dụng và mục đích, áp dụng quyền tối thiểu. Nếu ứng dụng dùng connection pool, log phía MySQL thường nhận diện tài khoản dịch vụ; hãy ghi thêm user ID và request ID ở tầng ứng dụng để nối sự kiện database với người dùng cuối.

**Phạm vi sự kiện.** Cân nhắc ghi nhận đăng nhập thành công/thất bại, thay đổi quyền, tạo hoặc xóa tài khoản, DDL trên schema quan trọng, thao tác ghi dữ liệu nhạy cảm và truy cập đọc vào bảng cần bảo vệ. Không phải hệ thống nào cũng cần ghi mọi `SELECT`; xác định trước yêu cầu điều tra và chi phí lưu trữ.

**Bảo vệ nội dung log.** Câu SQL có thể chứa email, số điện thoại, mã định danh hoặc dữ liệu nghiệp vụ. Hạn chế ghi giá trị nhạy cảm khi không cần thiết, giới hạn quyền đọc log, mã hóa khi truyền và khi lưu, đồng thời áp dụng thời hạn lưu phù hợp với chính sách của tổ chức.

**Tính toàn vẹn và sẵn sàng.** Tách quyền quản trị log khỏi quyền quản trị database khi có thể. Chuyển log đến hệ thống tập trung, giới hạn quyền xóa/sửa, theo dõi việc ngừng gửi log và đồng bộ thời gian. Thiết lập rotation, dung lượng dự phòng và cảnh báo khi filesystem gần đầy. Đừng để log đầy đĩa làm gián đoạn dịch vụ cơ sở dữ liệu.

**Kiểm thử độ bao phủ.** Lập ma trận gồm tài khoản, thao tác, kết quả mong đợi và bản ghi cần thấy. Kiểm tra cả thao tác thành công, thất bại, bị từ chối và thao tác không thuộc filter. Lặp lại kiểm thử sau khi nâng cấp MySQL, đổi plugin hoặc thay đổi chính sách filter.

### 7. Quy trình thực hành chọn và xác minh log

Giả sử đội bảo mật cần theo dõi quyền truy cập vào bảng `payments`, còn đội phát triển đang tìm một truy vấn báo cáo chạy chậm.

1. **Xác định mục tiêu.** Hoạt động truy cập `payments` và thay đổi quyền là yêu cầu audit. Truy vấn báo cáo chậm là yêu cầu hiệu năng.
2. **Chọn cơ chế.** Dùng Enterprise Audit nếu phiên bản và giấy phép triển khai hỗ trợ các sự kiện cần thiết. Dùng slow query log để tìm truy vấn báo cáo chậm. Chỉ bật general log trong thời gian ngắn khi cần xem ứng dụng thực sự gửi câu lệnh nào.
3. **Cấu hình filter có phạm vi rõ ràng.** Bắt đầu từ tài khoản hoặc nhóm sự kiện cần theo dõi. Tránh filter ghi toàn bộ hoạt động trong môi trường production nếu chưa ước lượng dung lượng và tác động.
4. **Tạo ca kiểm thử.** Đăng nhập bằng tài khoản thử nghiệm, chạy một truy vấn đọc, thực hiện thao tác được cấp quyền và thử một thao tác bị từ chối. Xác minh mỗi sự kiện xuất hiện đúng trong nguồn log đã chọn.
5. **Đối chiếu danh tính.** Kiểm tra user, host, thời gian và connection ID. Nếu cần biết người dùng cuối, đối chiếu với request ID trong log ứng dụng.
6. **Đưa log vào vận hành.** Chuyển log đến nơi lưu tập trung, đặt quyền truy cập, retention, rotation và cảnh báo. Ghi lại ai chịu trách nhiệm rà soát sự kiện bất thường.
7. **Tắt nguồn log tạm thời.** Sau khi điều tra xong, tắt general log nếu đã bật để tránh phát sinh dữ liệu và tải không cần thiết.

### 8. Xử lý một số tình huống thường gặp

| Hiện tượng | Cách kiểm tra |
|---|---|
| Không thấy sự kiện trong Enterprise Audit | Kiểm tra plugin có ở trạng thái `ACTIVE`, filter có tồn tại và đã gán cho đúng `user@host`, đường dẫn log và quyền ghi của tiến trình MySQL; sau đó tái hiện sự kiện thử nghiệm |
| Audit log quá lớn | Thu hẹp filter, rà soát tài khoản đang được gán filter, chuyển log tập trung và điều chỉnh retention; không bỏ các sự kiện bắt buộc chỉ để giảm dung lượng |
| General log tăng nhanh | Tắt general log sau khi tái hiện xong; kiểm tra `log_output` và nơi lưu log |
| Không thấy truy vấn nhanh trong slow log | Đây là hành vi dự kiến nếu truy vấn không vượt `long_query_time` hoặc không đạt điều kiện lọc; dùng nguồn audit phù hợp nếu cần theo dõi truy cập |
| Không xác định được người dùng cuối | Kiểm tra ứng dụng có dùng chung database account hay connection pool không; bổ sung audit nghiệp vụ và correlation ID ở tầng ứng dụng |
| Log cũ biến mất | Kiểm tra rotation, retention và trạng thái chuyển log đến hệ thống tập trung; xác minh chính sách lưu trữ trước khi kết luận sự kiện chưa từng xảy ra |

### 9. Bài tập tự kiểm tra

1. Một người dùng đọc bảng `customer_payment` trong vài mili giây. Vì sao slow query log không phải nguồn phù hợp để xác định lần truy cập này?
2. Đội vận hành cần xem tất cả câu SQL mà một ứng dụng gửi trong 10 phút để tái hiện lỗi. Cơ chế nào phù hợp, và cần làm gì sau khi kết thúc điều tra?
3. Tại sao việc bật Enterprise Audit nhưng không kiểm tra filter và quyền ghi tệp vẫn có thể dẫn đến thiếu bằng chứng?
4. Binary log có thể hỗ trợ phục hồi dữ liệu. Vì sao nó không thay thế nhật ký audit truy cập?
5. Một hệ thống dùng chung tài khoản `app_user` cho mọi người dùng. Bạn cần bổ sung dữ liệu nào ở tầng ứng dụng để truy vết một thao tác về đúng người dùng cuối?

### 10. Nguyên tắc lựa chọn

Hãy chọn nguồn log theo câu hỏi cần trả lời: **Enterprise Audit** cho sự kiện bảo mật được lọc theo chính sách; **general query log** cho việc quan sát ngắn hạn các kết nối và câu lệnh; **slow query log** cho chẩn đoán hiệu năng; **binary log** cho replication và phục hồi; **audit ứng dụng** cho lịch sử nghiệp vụ và danh tính người dùng cuối. Một hệ thống quan trọng có thể cần kết hợp nhiều lớp, nhưng mỗi lớp phải có mục tiêu, người chịu trách nhiệm, quyền truy cập và thời hạn lưu rõ ràng.
