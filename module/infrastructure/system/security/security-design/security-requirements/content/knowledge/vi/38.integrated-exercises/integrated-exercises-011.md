# Thiết kế backup và recovery requirement

## 1. Mục tiêu bài thực hành

“Có backup hằng ngày” mô tả một hoạt động vận hành, chưa phải yêu cầu phục hồi có thể nghiệm thu. Cần biết hệ thống khôi phục được dữ liệu nào, về thời điểm nào, trong bao lâu, dưới loại sự cố nào và ai có quyền quyết định đưa dịch vụ trở lại hoạt động.

Trong bài thực hành tổng hợp này, bạn chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành bộ **yêu cầu sao lưu và phục hồi**. Yêu cầu phải bảo vệ đồng thời khả năng phục vụ, tính toàn vẹn và tính bí mật; một bản sao chứa đầy đủ dữ liệu nhưng bị kẻ tấn công xóa được hoặc không còn khóa giải mã chưa đáp ứng mục đích phục hồi.

Sau bài học, bạn cần thực hiện được các việc sau:

- Phân loại dữ liệu và phụ thuộc cần khôi phục, bao gồm cấu hình, danh tính, khóa mã hóa và trạng thái xử lý bất đồng bộ.
- Định nghĩa RPO, RTO, cửa sổ phục hồi và tiêu chí dữ liệu nhất quán bằng mốc thời gian cụ thể.
- Đặc tả sao lưu độc lập, quyền truy cập, tính bất biến, retention và khả năng phục hồi sau sự cố bảo mật.
- Liên kết rủi ro với yêu cầu, quyết định kiến trúc, runbook và bằng chứng diễn tập.
- Thiết kế kiểm thử mất vùng, mã hóa phá hoại, mất khóa, dữ liệu hỏng, phục hồi từng tenant và retry sau khôi phục.

Các dung lượng, ngưỡng và thời gian trong bài là giả định thiết kế của tình huống. Chúng phải được đo và được chủ nghiệp vụ chấp nhận trước khi áp dụng cho hệ thống thực tế.

## 2. Tình huống: nền tảng quản lý công việc nhiều doanh nghiệp

Một dịch vụ SaaS quản lý công việc cho nhiều doanh nghiệp. Mỗi doanh nghiệp là một tenant. Người dùng tạo công việc, bình luận, tải tài liệu đính kèm và nhận thông báo. Hệ thống sử dụng cơ sở dữ liệu quan hệ, object storage, hàng đợi và dịch vụ danh tính.

Giả định tại thời điểm thiết kế:

| Thành phần | Dữ liệu hoặc vai trò | Quy mô/phạm vi |
| --- | --- | --- |
| Cơ sở dữ liệu | Tenant, người dùng, công việc, bình luận, metadata tệp, chính sách quyền, outbox và idempotency | 200 GiB dữ liệu cần khôi phục |
| Object storage | Nội dung tài liệu đính kèm và các phiên bản cần thiết | 800 GiB cho bộ dữ liệu phục hồi tham chiếu |
| Log giao dịch | Các thay đổi cần để phục hồi cơ sở dữ liệu tới một điểm cụ thể | Giả định 8 GiB/ngày để lập ngân sách ban đầu |
| Cấu hình và triển khai | Mã triển khai được phê duyệt, schema, cấu hình mạng, phiên bản ứng dụng, chính sách truy cập | Phải xác định được phiên bản tương thích |
| Danh tính và khóa | Quyền truy cập, cấu hình mã hóa, phiên bản khóa và quyền giải mã | Không được phụ thuộc hoàn toàn vào tài khoản production đang hỏng |
| Cache và chỉ mục tìm kiếm | Dữ liệu dẫn xuất | Có thể dựng lại từ nguồn chính |
| Hàng đợi | Thông báo và tác vụ xử lý nền | Khôi phục từ outbox/trạng thái bền vững, không giả định mọi message còn nguyên |
| Audit và hồ sơ phục hồi | Dấu vết hành động quan trọng, manifest, kết quả kiểm tra | Lưu riêng theo chính sách kiểm toán của tình huống |

### 2.1. Chức năng nghiệp vụ phải trở lại trước

Tầng cốt lõi gồm đăng nhập, kiểm tra quyền theo tenant, đọc/tạo/cập nhật công việc, đọc bình luận và truy cập tài liệu đính kèm được phép. Tìm kiếm toàn văn, báo cáo tổng hợp và gửi thông báo có thể phục hồi sau.

“Database đã khởi động” không đồng nghĩa dịch vụ cốt lõi đã phục hồi. Nếu người dùng chưa đăng nhập được, tệp bị thiếu, quyền truy cập sai hoặc API chỉ đọc trong khi nghiệp vụ cần ghi, RTO cốt lõi chưa kết thúc.

Bài tập giả định môi trường đích có thể được cấp đủ tài nguyên và mạng theo năng lực đã được kiểm chứng. Nếu kế hoạch phụ thuộc vào việc xin quota, chờ mua hạ tầng hoặc tìm lại tài khoản quản trị khi xảy ra sự cố, các thời gian đó phải nằm trong ngân sách phục hồi.

### 2.2. Các kịch bản cần đặc tả riêng

| Kịch bản | Phạm vi giả định | Mục tiêu của bài tập |
| --- | --- | --- |
| S-01: mất vùng production | Dữ liệu/vùng chính không sử dụng được; vùng, tài khoản backup và khóa phục hồi vẫn khả dụng | RPO không quá 15 phút; RTO cốt lõi không quá 4 giờ |
| S-02: tài khoản production bị chiếm và dữ liệu bị mã hóa | Bản sao bất biến, quyền quản trị backup và khóa độc lập chưa bị chiếm; xác định được điểm sạch trong 24 giờ trước khi dừng ghi | Mất dữ liệu không quá 24 giờ; phục hồi cốt lõi trong 8 giờ, có điều kiện chứng minh điểm sạch |
| S-03: lỗi dữ liệu âm thầm được phát hiện muộn | Thời điểm bắt đầu lỗi và mức lan truyền có thể chưa rõ | Không tự cam kết RPO 15 phút; điều tra điểm sạch, công bố khoảng mất dữ liệu và thời gian thực tế |
| S-04: xóa nhầm dữ liệu một tenant | Tenant còn thuộc phạm vi được phép phục hồi; yêu cầu nằm trong cửa sổ 35 ngày | Phục hồi có chọn lọc trong 4 giờ từ lúc tiếp nhận yêu cầu đã xác minh, không quay lùi tenant khác |

Thời gian 4 giờ của S-04 là mục tiêu thực hiện một yêu cầu phục hồi chọn lọc, không tự đồng nhất với RTO tính từ thời điểm tenant bắt đầu bị gián đoạn. Hồ sơ phải báo cả thời điểm xóa, thời điểm yêu cầu và thời điểm hoàn thành.

Nếu S-02 không có điểm sạch trong 24 giờ hoặc vùng backup cũng bị chiếm, mục tiêu đã nêu không còn được bảo đảm theo giả định này. Đội xử lý phải khai báo vi phạm/ngoài phạm vi và xin quyết định chấp nhận rủi ro; không chọn một bản sao nghi ngờ chỉ để báo đạt RTO.

## 3. Mô hình đe dọa và ranh giới tin cậy

Backup cũng là một kho dữ liệu nhạy cảm. Nó có thể chứa lịch sử dữ liệu đã thay đổi, bản sao nhiều tenant, quyền cũ và thông tin có thể giúp kẻ tấn công khôi phục môi trường của hệ thống.

| Mã | Sự cố hoặc hành vi đe dọa | Điều cần bảo vệ |
| --- | --- | --- |
| R-01 | Mất vùng, xóa nhầm database hoặc hỏng storage | Có bộ dữ liệu dùng được ngoài miền lỗi production |
| R-02 | Người chiếm tài khoản production xóa hoặc ghi đè backup | Các phiên bản đã cam kết không thể bị production phá hủy |
| R-03 | Kẻ tấn công đọc bản sao hoặc chiếm phiên phục hồi | Bí mật dữ liệu và cách ly tenant trong môi trường phục hồi |
| R-04 | Mất khóa, quyền giải mã hoặc danh tính khẩn cấp | Giải mã và truy cập được bản sao khi production không còn |
| R-05 | Backup thành công nhưng dữ liệu không nhất quán hoặc đã bị hỏng | Khả năng phục hồi tới điểm có thể chứng minh hợp lệ |
| R-06 | Database về thời điểm A, tệp/cấu hình/quyền về thời điểm B | Không có tham chiếu hỏng, schema sai hoặc quyền truy cập ngoài ý muốn |
| R-07 | Tiến trình phục hồi chậm vì dung lượng, mạng, replay log hoặc thiếu quyền | RTO được kiểm chứng bằng toàn bộ đường phục hồi |
| R-08 | Hàng đợi/outbox/idempotency bị quay lùi và tác vụ được thực hiện lại | Không gửi lặp hoặc tạo thêm tác dụng nghiệp vụ ngoài ý muốn |
| R-09 | Restore đưa tài khoản đã thu hồi, dữ liệu đã xóa hoặc mã độc trở lại | Trạng thái bảo mật hiện hành được áp dụng trước khi mở dịch vụ |
| R-10 | Một quản trị viên tự khôi phục toàn bộ dữ liệu ra môi trường không kiểm soát | Phê duyệt, quyền tối thiểu và dấu vết độc lập |
| R-11 | Backup ngừng cập nhật nhưng chỉ theo dõi job cuối báo thành công | Độ mới của điểm thực sự phục hồi được được giám sát |

Không coi replica, snapshot, backup và disaster recovery là các từ thay thế cho nhau. Replica giúp tính sẵn sàng nhưng có thể sao chép cả thao tác xóa hoặc dữ liệu hỏng. Snapshot có thể là thành phần của backup nếu được bảo vệ, giữ phụ thuộc và khôi phục kiểm chứng được. Disaster recovery còn bao gồm danh tính, mạng, ứng dụng, con người và quyết định chuyển lưu lượng.

## 4. Định nghĩa các đại lượng để tránh báo cáo sai

### 4.1. RPO và điểm phục hồi nhất quán

Trong S-01, gọi:

- `t0`: thời điểm chức năng cốt lõi bắt đầu không khả dụng do sự cố.
- `t_ref`: thời điểm cuối cùng trước khi hệ thống mất khả dụng hoặc bị chặn ghi để phục hồi; lấy mốc có dữ liệu đã được chấp nhận cuối cùng trong kịch bản.
- `t_c`: thời điểm commit cuối cùng được bảo đảm thuộc một điểm phục hồi nhất quán đã chọn, không có khoảng trống giao dịch trước mốc đó.

Độ mất dữ liệu theo thời gian được đánh giá bằng:

```text
actual_data_loss_window = max(0, t_ref - t_c)
S-01 PASS về RPO khi actual_data_loss_window <= 15 phút
```

Nếu vùng mất ngay tại `t0`, thường `t_ref = t0`. Nếu ứng dụng còn nhận ghi sau khi một phần hệ thống hỏng, phải ghi lại mốc dừng ghi thực tế; không bỏ các commit đã báo thành công đó khỏi phép đánh giá.

Số request/giao dịch đã được ứng dụng xác nhận nhưng không còn sau khôi phục cũng phải được báo cáo. Một khoảng mất dữ liệu 10 phút có thể chứa rất nhiều thay đổi; thỏa ngưỡng thời gian không có nghĩa không gây thiệt hại nghiệp vụ.

`t_c` không phải giờ bắt đầu backup, giờ tạo file hoặc timestamp của job cuối. Nó là mốc dữ liệu ứng dụng có thể phục hồi được, có đủ database, object version, cấu hình và khóa liên quan.

Ví dụ mất vùng lúc `09:00`, không còn nhận ghi sau đó:

| Điểm phục hồi | Kết quả |
| --- | --- |
| Bộ nhất quán tới `08:52` | Khoảng mất dữ liệu 8 phút, đạt RPO 15 phút |
| File backup tạo `08:59` nhưng dữ liệu chỉ tới `08:35` | Khoảng mất dữ liệu 25 phút, không đạt |
| Database tới `08:58`, tệp chỉ đủ tới `08:40` | Không được công bố `08:58` là điểm phục hồi đầy đủ của dịch vụ |
| Có log tới `08:59` nhưng thiếu khóa hoặc một đoạn log bắt buộc | Chưa chứng minh được điểm phục hồi tương ứng |

### 4.2. RTO và thời điểm kết thúc

Với S-01/S-02, `t_ready` là thời điểm luồng truy cập thực tế tại môi trường đích vượt qua các kiểm tra chấp nhận cốt lõi và được phép phục vụ người dùng đúng quyền.

```text
actual_RTO = t_ready - t0
```

Phát hiện, điều phối, phê duyệt, dựng môi trường, lấy backup, giải mã, khôi phục, replay, xác minh và chuyển lưu lượng đều nằm trong khoảng này. Không đặt lại đồng hồ khi tuyên bố sự cố hoặc lúc bấm lệnh restore.

Trong S-03, cần tách thời điểm dữ liệu bắt đầu sai, thời điểm phát hiện, thời điểm đóng băng ghi và thời điểm khôi phục an toàn. Nếu không biết điểm bắt đầu tác động, báo phạm vi ước lượng; không gán thời gian thực thi sau phát hiện thành RTO toàn bộ sự cố.

### 4.3. RPO dưới sự cố bảo mật

Backup gần nhất có thể đã chứa dữ liệu bị sửa hoặc mã độc. Khi chọn điểm sạch cũ hơn, phần thay đổi hợp lệ sau điểm đó cần được đối soát và tái nhập có kiểm soát, nếu có nguồn đáng tin để làm việc này.

Đối với S-02, lấy mốc dừng ghi cuối cùng làm `t_ref` và yêu cầu `t_ref - t_clean <= 24 giờ` trong giả định của kịch bản. Nếu phải quay về ba ngày trước thì không đạt mục tiêu 24 giờ, dù quá trình restore chỉ mất hai giờ. Dữ liệu tái nhập chỉ giảm mất dữ liệu thực tế khi đã được xác minh đầy đủ, không được suy diễn từ việc còn một file log.

RPO tốt trong mất vùng không tự chứng minh RPO tương đương trong ransomware hoặc dữ liệu hỏng âm thầm. Bài đặc tả phải nêu riêng các giới hạn này để chủ nghiệp vụ quyết định.

## 5. Định nghĩa bộ phục hồi và cửa sổ giữ dữ liệu

### 5.1. Recovery set

Một **recovery set** là tập các thành phần có thể kết hợp để phục hồi dịch vụ về một điểm nhất quán, không chỉ là một file database.

Manifest của recovery set cần có tối thiểu:

- Mã bộ phục hồi, phiên bản định dạng, thời gian UTC và phạm vi tenant/dữ liệu.
- Mã bản full, chuỗi log/phụ thuộc, vị trí log hoặc checkpoint của database.
- Điểm `t_c` được cam kết, trạng thái kiểm tra và bằng chứng không có khoảng trống log.
- Danh mục object/version cần để phục vụ các tham chiếu tồn tại tại điểm database đó.
- Phiên bản schema, ứng dụng, cấu hình hạ tầng và các chính sách tương thích.
- Định danh phiên bản khóa cần dùng và đường truy cập phục hồi; không chứa khóa bí mật dạng rõ.
- Kích thước, checksum của các thành phần và thông tin xác thực manifest bằng cơ chế được bảo vệ độc lập.
- Vị trí các bản sao, thời gian khóa lưu giữ và những phụ thuộc không được phép xóa trước.

Checksum giúp phát hiện sai lệch nội dung so với giá trị tham chiếu. Nếu kẻ tấn công sửa được cả dữ liệu lẫn checksum, checksum đơn thuần chưa chứng minh nguồn gốc; manifest cần cơ chế bảo vệ tính xác thực và quyền ghi tương ứng.

### 5.2. Database và tệp phải khớp nhau

Đối với một công việc có tệp đính kèm, database chứa ID và version nội dung bất biến. Recovery set chỉ được đánh dấu tới `t_c` khi mọi object version mà database yêu cầu tại mốc đó đã hiện diện trong kho phục hồi và có thể xác minh/giải mã.

Không lấy timestamp lớn nhất của một thành phần để đại diện cả hệ thống. Một bản database hoàn chỉnh nhưng thiếu tệp có thể cần lùi điểm phục hồi hoặc chọn chế độ suy giảm được chủ nghiệp vụ chấp thuận; không được tự tính đó là đạt tiêu chí cốt lõi của bài tập.

Tệp đã xóa khỏi production nhưng còn cần cho một điểm phục hồi trong cửa sổ phải được giữ theo version. Quy trình dọn storage phải hiểu phụ thuộc này, thay vì xóa mọi object không còn được database hiện tại tham chiếu.

### 5.3. Cửa sổ phục hồi và retention

Tình huống cung cấp khả năng chọn điểm phục hồi trong **35 ngày gần nhất**, trong phạm vi độ chi tiết mà chuỗi log và recovery set đã chứng minh. Dữ liệu backup được giữ tối thiểu **42 ngày** để có phần dự phòng cho bản full trước đầu cửa sổ và việc tạo bộ phục hồi.

Lịch giả định: full database mỗi tuần; log giao dịch được chuyển ra ngoài miền lỗi production ít nhất mỗi 5 phút; object version, manifest và cấu hình được đồng bộ liên tục đủ để đạt độ mới của recovery set. Lịch chạy này là biện pháp thiết kế, không phải bằng chứng tự động đạt RPO.

Không xóa một bản full, đoạn log, object version hoặc khóa còn là phụ thuộc của một điểm đã cam kết trong cửa sổ 35 ngày, kể cả thành phần đó đã vượt 42 ngày. Tác vụ dọn dẹp phải dựa trên đồ thị phụ thuộc và kiểm tra biên đầu cửa sổ; lỗi job hoặc chậm truyền log có thể làm phần dự phòng cần dài hơn dự kiến.

Các bản sao bất biến được khóa tối thiểu 42 ngày từ lúc ghi. Khi hết hạn, chỉ dọn nếu không còn phụ thuộc và đáp ứng chính sách vòng đời dữ liệu. Không thay retention bằng một con số dài vô hạn; cần dự toán chi phí, dữ liệu lịch sử và quyền truy cập đi kèm.

## 6. Kiến trúc bảo vệ bản sao và đường phục hồi

### 6.1. Tách miền lỗi và quyền quản trị

Một phương án đáp ứng giả định S-01/S-02 có ba bản dữ liệu theo vai trò:

1. Dữ liệu vận hành tại tài khoản production, vùng A.
2. Bản backup phục vụ khôi phục vận hành, được quản lý trong miền quyền khác production.
3. Bản recovery set được giữ bất biến tại tài khoản backup độc lập, vùng B, có khóa và đường truy cập phục hồi còn dùng được khi mất vùng A.

Số lượng bản sao chỉ có ý nghĩa nếu chỉ rõ chúng có thể cùng hỏng theo cách nào. Hai bucket khác tên trong cùng tài khoản, cùng quyền xóa và cùng khóa chưa tạo thành hai miền bảo vệ độc lập trước hành vi chiếm tài khoản đó.

```text
Tài khoản production / vùng A
  dữ liệu + object version + log giao dịch
                |
                | luồng sao lưu, quyền ghi bị giới hạn
                v
Miền quản trị backup độc lập / vùng B
  recovery set bất biến + manifest được xác thực
  khóa/phiên bản khóa + audit độc lập
                |
                | quyền restore tạm thời, có phê duyệt và ghi vết
                v
Môi trường phục hồi sạch
  mạng cô lập -> dựng dịch vụ -> kiểm chứng -> chuyển lưu lượng
```

Vai trò ghi backup chỉ được tạo các thành phần theo namespace/phạm vi đã định; không được xóa, sửa các phiên bản đã cam kết hoặc rút ngắn thời gian giữ. Nếu cần đọc nguồn để sao lưu, quyền đọc đó được cấp riêng và giới hạn đúng nguồn.

Quyền restore được cấp tạm thời theo vụ việc, chỉ đọc bộ backup đã chọn và giải mã trong môi trường được phép. Quyền thay retention, quản trị khóa và xuất toàn bộ dữ liệu phải tách khỏi vai trò production và vai trò vận hành backup hằng ngày.

Mô hình này vẫn có rủi ro chung như cùng nhà cung cấp hoặc một cấp quản trị tổ chức có quyền trên cả hai tài khoản. Nếu cần chống những rủi ro đó, phải thêm miền quản trị hoặc bản sao phù hợp và kiểm thử; không tuyên bố “độc lập tuyệt đối” chỉ vì đã khác vùng.

### 6.2. Mã hóa và khả năng lấy lại khóa

Bản sao được mã hóa khi truyền và khi lưu. Thiết kế nêu rõ khóa nào bảo vệ thành phần nào, ai được giải mã, khóa ở đâu, phụ thuộc vùng/tài khoản nào và các phiên bản cũ được giữ bao lâu.

Một backup không thể phục hồi nếu khóa của nó chỉ tồn tại trong tài khoản production đã mất. Đồng thời, đặt khóa dạng rõ cạnh ciphertext làm mất ý nghĩa kiểm soát truy cập độc lập.

Chính sách của bài tập yêu cầu:

- Có đường giải mã được phê duyệt, đã thử trong điều kiện không dùng danh tính hoặc dịch vụ khóa của vùng production bị mất.
- Giữ phiên bản khóa cũ cho tới khi mọi bản sao phụ thuộc đã hết hạn và không còn bị giữ vì diễn tập/điều tra được phép.
- Khi luân chuyển khóa, thử giải mã cả bản mới và bản cũ còn trong cửa sổ; đổi tên alias không được xem là bằng chứng bản cũ còn đọc được.
- Việc hủy khóa có kiểm tra phụ thuộc và phê duyệt, ghi vào audit độc lập.
- Thông tin khôi phục danh tính khẩn cấp được bảo vệ và thử định kỳ; không ghi mật khẩu/khóa bí mật trong runbook hoặc manifest.

Dữ liệu về khóa, quyền truy cập và cơ chế khẩn cấp cũng phải được quản lý vòng đời. Không giải quyết bài toán mất khóa bằng cách sao chép bí mật ra nhiều vị trí không kiểm soát.

### 6.3. Môi trường phục hồi là một môi trường có dữ liệu thật

Môi trường phục hồi phải dùng danh tính, mạng và image triển khai đã được xác minh. Chặn kết nối ra các đích không cần thiết, đặc biệt dịch vụ email, webhook và tích hợp có tác dụng bên ngoài, trước khi chạy ứng dụng trên dữ liệu vừa restore.

Không sao chép mù quáng mọi cấu hình, token và phiên đăng nhập cũ từ backup. Sau sự cố bảo mật, phải áp dụng các quyết định thu hồi quyền và xoay bí mật hiện hành; các credential có thể đã bị lộ không được tái sử dụng chỉ vì chúng vẫn hoạt động.

Người thực hiện và người phê duyệt phục hồi có vai trò riêng. Đường phê duyệt khẩn cấp phải có người trực, phương tiện xác thực và quyền cần thiết đã thử, đồng thời được tính trong ngân sách RTO.

## 7. Bộ yêu cầu bảo mật có mã định danh

Dùng phiên bản chính sách `BRP-TASK-1.0`. Mỗi yêu cầu gồm hành vi bắt buộc, điều kiện áp dụng và bằng chứng nghiệm thu. Lịch chạy backup là một phần triển khai của các yêu cầu, không thay thế phép đo kết quả.

### BR-01 — Phạm vi phục hồi đầy đủ

Hệ thống phải duy trì danh mục nguồn dữ liệu/phụ thuộc theo mục 2 và manifest recovery set theo mục 5. Một bộ chỉ được công bố dùng được khi đủ các phụ thuộc để phục hồi chức năng cốt lõi tới `t_c`.

**Nghiệm thu:** đối chiếu manifest với database, object version, cấu hình, schema và khóa; cố ý bỏ một phụ thuộc để chứng minh hệ thống không đánh dấu bộ đó là phục hồi đầy đủ.

### BR-02 — Độ mới của điểm phục hồi

Trong S-01, điểm nhất quán gần nhất có thể phục hồi ngoài vùng production phải cách dữ liệu được chấp nhận cuối cùng không quá 15 phút. Hệ thống phải đánh giá độ mới của recovery set ít nhất mỗi 1 phút; cảnh báo khi độ trễ vượt 10 phút và báo vi phạm khi vượt 15 phút.

**Nghiệm thu:** tạo các giao dịch/phiên bản tệp có sequence kiểm soát, ngắt luồng backup và kiểm tra cảnh báo, mốc `t_c`, tập commit còn/mất sau restore. Job báo thành công không đủ để ghi PASS.

### BR-03 — Thời gian phục hồi theo kịch bản

S-01 phải đạt RTO cốt lõi không quá 4 giờ; S-02 không quá 8 giờ khi các giả định và điểm sạch ở mục 2 được đáp ứng. Phép đo phải bắt đầu từ tác động thực tế và kết thúc tại kiểm chứng nghiệp vụ sau chuyển lưu lượng.

**Nghiệm thu:** diễn tập toàn tuyến với dung lượng và phụ thuộc đại diện, thu timestamp từng giai đoạn, không loại thời gian phê duyệt, dựng hạ tầng hoặc xác minh ra khỏi tổng.

### BR-04 — Bản sao ngoài miền phá hủy của production

Ít nhất một recovery set đạt mục tiêu độ mới phải nằm ngoài vùng production và ngoài quyền sửa/xóa của tài khoản/role production bị giả định mất trong S-02. Việc mất hoàn toàn quyền truy cập vùng A không được chặn lấy bản sao và khóa phục hồi ở vùng B.

**Nghiệm thu:** dùng danh tính production thử sửa/xóa/đổi retention trong phạm vi diễn tập và xác minh bị từ chối; thực hiện restore khi quyền và kết nối tới vùng A bị chặn.

### BR-05 — Bất biến, retention và chuỗi phụ thuộc

Các thành phần đã cam kết phải được khóa giữ tối thiểu 42 ngày bằng cơ chế mà quyền production và quản trị backup thường nhật không rút ngắn được. Chính sách dọn dẹp phải giữ đủ phụ thuộc cho mọi điểm phục hồi được công bố trong cửa sổ 35 ngày.

**Nghiệm thu:** thử thao tác xóa/ghi đè/rút ngắn giữ trên bản diễn tập đã khóa; phục hồi gần đầu cửa sổ bằng chuỗi phụ thuộc thật. Không dùng cấu hình retention trên giấy làm bằng chứng duy nhất.

### BR-06 — Bí mật dữ liệu và quyền tối thiểu

Bản sao phải được mã hóa khi truyền/lưu, truy cập theo danh tính được xác thực mạnh và vai trò tối thiểu. Restore hoặc xuất dữ liệu thật chỉ được thực hiện trong môi trường và vụ việc đã phê duyệt; có audit độc lập về người, bộ dữ liệu, mục đích, thời gian và kết quả.

**Nghiệm thu:** kiểm thử vai trò không được phép đọc/giải mã/xuất; xác minh không có truy cập công khai và audit vẫn được ghi khi production không khả dụng. Log không chứa nội dung backup hay bí mật.

### BR-07 — Khóa và danh tính khẩn cấp có thể phục hồi

Mọi recovery set trong cửa sổ phải có đường giải mã và đường quản trị phục hồi được kiểm chứng, không phụ thuộc duy nhất vào danh tính/vùng production. Không hủy phiên bản khóa còn phụ thuộc hợp lệ.

**Nghiệm thu:** restore bằng danh tính khẩn cấp được kiểm soát, từ bản mã hóa bằng phiên bản khóa cũ sau rotation và khi khóa production không dùng được. Thất bại lấy khóa phải được báo là không phục hồi được.

### BR-08 — Xác minh tính toàn vẹn và lựa chọn điểm sạch

Trước restore phải xác minh tính xác thực manifest, checksum và chuỗi log. Trước mở lại dịch vụ phải chạy bất biến dữ liệu và kiểm tra an toàn của kịch bản; S-02 phải có hồ sơ lý do tin cậy điểm sạch được người phụ trách sự cố chấp thuận.

**Nghiệm thu:** sửa một phần backup, cắt một đoạn log và đưa một bộ thuộc khoảng nghi bị xâm nhập vào danh sách ứng viên; hệ thống phải phát hiện/loại theo tiêu chí, không tự chuyển sang dùng dữ liệu nghi ngờ để kịp thời gian.

### BR-09 — Nhất quán liên thành phần và chống hai bên cùng ghi

Database, object version, schema và cấu hình phải được phục hồi như một bộ tương thích. Trước mở ghi ở đích, phải chặn/fence bên nguồn cũ và chỉ định duy nhất môi trường có quyền nhận ghi.

**Nghiệm thu:** đối chiếu toàn bộ tham chiếu tệp theo manifest, kiểm tra số lượng/checksum và thử nguồn cũ quay lại mạng. Nguồn cũ không được nhận ghi hoặc phát tác vụ tạo nhánh dữ liệu thứ hai.

### BR-10 — Phục hồi từng tenant và trạng thái bảo mật hiện hành

Yêu cầu chọn lọc phải được xác minh đúng tenant, đối tượng, thời điểm, mục đích và quyền yêu cầu. Restore vào staging cô lập rồi trích xuất/đối soát; không quay lùi database dùng chung và không làm sống lại dữ liệu bị chủ động loại trừ theo chính sách hiện hành.

**Nghiệm thu:** phục hồi tenant A trong khi tenant B tiếp tục có thay đổi; B không mất dữ liệu, không nhìn thấy dữ liệu A. Tài khoản bị thu hồi quyền và đối tượng đã được đánh dấu không được tái xuất hiện không trở lại phục vụ.

### BR-11 — Xử lý tác vụ lặp sau restore

Trước mở worker, phải đối soát outbox, idempotency và tác dụng bên ngoài bằng định danh nghiệp vụ/sự kiện ổn định. Không giả định hàng đợi hoặc bảng chống lặp sau restore còn ghi nhớ đầy đủ tác vụ đã xảy ra ngoài hệ thống.

**Nghiệm thu:** đưa vào fixture một thông báo/webhook đã thực hiện sau `t_c` nhưng trước sự cố; chạy worker sau restore trong chế độ kiểm soát và chứng minh không phát lại tác dụng đó ngoài ý muốn.

### BR-12 — Diễn tập, quan sát và quản lý thay đổi

Mỗi tuần phải thử restore một mẫu dữ liệu có checksum và quan hệ nghiệp vụ; mỗi tháng phải thử một kịch bản mất phụ thuộc như mất khóa production hoặc mất quyền vùng A; mỗi quý phải thử S-01 với dung lượng đại diện toàn tuyến. Chọn thêm S-02/S-04 theo lịch có chủ sở hữu và thực hiện ít nhất mỗi quý trong tình huống này.

Thay đổi lớn về engine, schema, khóa, IAM, storage, ingress hoặc dung lượng cần đánh giá tác động và kiểm chứng đường phục hồi trước khi kết luận các mục tiêu cũ vẫn đạt.

**Nghiệm thu:** hồ sơ diễn tập có phiên bản chính sách, dung lượng, timestamp, kết quả, chênh lệch và người xử lý. Một diễn tập thất bại tạo hành động khắc phục có hạn hoàn thành; không đổi ngưỡng để biến thất bại thành PASS.

## 8. Lập ngân sách RTO và kiểm tra tính khả thi

### 8.1. Ngân sách S-01

| Giai đoạn | Ngân sách tối đa | Điều kiện ra khỏi giai đoạn |
| --- | --- | --- |
| Phát hiện và thông báo | 15 phút | Xác định tác động cốt lõi, ghi `t0`, gọi đúng người trực |
| Cô lập nguồn và quyết định phục hồi | 30 phút | Nguồn được fence; bộ ứng viên và người phê duyệt rõ ràng |
| Dựng môi trường đích | 30 phút | Có mạng, danh tính, quota, storage, khóa và phần mềm tương thích |
| Lấy/giải mã/restore/replay dữ liệu | 105 phút | Database và tệp theo recovery set đã sẵn sàng kiểm tra |
| Kiểm chứng dữ liệu và an toàn | 45 phút | Đạt bất biến, quyền tenant, kiểm tra nghiệp vụ và tác vụ nền |
| Chuyển lưu lượng và xác nhận thực tế | 15 phút | Luồng truy cập thực tế dùng được, ghi nhận `t_ready` |
| **Tổng** | **240 phút** | **4 giờ** |

Đây là ngân sách cho đường găng, không phải lý do cộng trùng tác vụ chạy song song. Những công việc song song phải có chủ sở hữu, điều kiện bắt đầu và phụ thuộc rõ ràng. Nếu một giai đoạn trễ, không được bỏ kiểm chứng để giữ tổng dưới 4 giờ.

### 8.2. Tính sơ bộ thời gian chuyển dữ liệu

Với 200 GiB database và 800 GiB object, tổng dữ liệu cần dựng lại là 1000 GiB. Giả sử tốc độ hiệu dụng đầu cuối đã đo là 250 MiB/giây:

```text
thời gian chuyển/xử lý dữ liệu = 1000 * 1024 / 250
                              = 4096 giây
                              ≈ 68,3 phút
```

Nếu replay log mất thêm 30 phút thì riêng giai đoạn dữ liệu khoảng 98,3 phút, chỉ còn khoảng 6,7 phút trong ngân sách 105 phút. Cần diễn tập để xác nhận mức dự phòng có đủ trước biến thiên dung lượng và hiệu năng; không xem phép tính này là bằng chứng đạt.

250 MiB/giây ở đây là tốc độ hiệu dụng của toàn tuyến đọc–mạng–giải mã–giải nén–ghi với dữ liệu đại diện, không phải băng thông danh nghĩa của card mạng. Nếu chỉ đạt 100 MiB/giây, phần chuyển dữ liệu đã khoảng 170,7 phút trước replay, nên thiết kế ngân sách hiện tại không khả thi.

Các lựa chọn xử lý gồm tăng năng lực đích, song song có kiểm soát, thay định dạng/chu kỳ full để giảm replay hoặc thay kiến trúc phục hồi. Nếu vẫn không đạt, trình bày chi phí và tác động để chủ nghiệp vụ quyết định mục tiêu; không viết RTO 4 giờ chỉ vì đó là con số mong muốn.

### 8.3. Dự toán dung lượng backup

Ước lượng đơn giản cho một miền lưu bản sao, chưa tính nén/dedup:

| Thành phần | Giả định | Dung lượng ước lượng |
| --- | --- | --- |
| Full database | 7 bản x 200 GiB | 1400 GiB |
| Log giao dịch | 42 ngày x 8 GiB/ngày | 336 GiB |
| Object còn cần phục hồi | 800 GiB nền + 42 ngày x 20 GiB thay đổi/ngày | 1640 GiB |
| Manifest, cấu hình và phần phụ trợ | Giả định của bài tập | 24 GiB |
| **Tổng cơ sở** | Chưa có dự phòng | **3400 GiB** |
| **Cộng 30% dự phòng** | Tăng trưởng/biến động | **4420 GiB** |

Bảy bản full chỉ là giả định lịch/cửa sổ; số thật có thể lớn hơn nếu phải giữ phụ thuộc, job chạy lại hoặc có vụ việc giữ dữ liệu riêng. Nếu hai miền backup đều giữ một bộ tương đương, tính dung lượng và chi phí của cả hai; không nhầm 4420 GiB là tổng cho mọi bản sao.

Chi phí còn gồm đọc/khôi phục, egress, API storage, khóa, tài nguyên staging và diễn tập. Dung lượng lịch sử object phải đo theo tốc độ thay đổi/version thực tế, không chỉ nhìn số byte đang dùng ở production.

## 9. Runbook phục hồi: biến yêu cầu thành quyết định vận hành

Runbook mô tả cách thực hiện; yêu cầu mô tả điều phải đạt. Một câu lệnh restore thành công chỉ chứng minh một bước runbook đã chạy, không tự chứng minh mọi yêu cầu đã đạt.

| Bước | Công việc và người chịu trách nhiệm | Bằng chứng/điểm quyết định |
| --- | --- | --- |
| 1. Ghi nhận tác động | Người điều phối ghi `t0`, phạm vi tenant/chức năng, mốc cuối nhận ghi và kịch bản | Timeline từ hệ thống quan sát, không chỉ giờ mở ticket |
| 2. Cô lập và bảo toàn | Đội ứng cứu chặn ghi/phát tác vụ từ nguồn, giữ dấu vết, thu hồi quyền bị nghi chiếm | Xác nhận fencing; danh mục chứng cứ được bảo vệ |
| 3. Chọn recovery set | Vận hành và chủ dữ liệu đối chiếu manifest, độ mới, phụ thuộc, điểm sạch | Mã bộ, `t_c`, dữ liệu dự kiến mất, lý do tin cậy |
| 4. Phê duyệt mục tiêu | Người có thẩm quyền xác nhận điểm phục hồi và ảnh hưởng nghiệp vụ | Phê duyệt gắn vụ việc; dùng đường khẩn cấp đã diễn tập |
| 5. Dựng môi trường sạch | Đội nền tảng dựng mạng, khóa, danh tính và phần mềm tương thích | Không phụ thuộc vùng hỏng; egress tác dụng bên ngoài còn bị chặn |
| 6. Restore và replay | Đội dữ liệu xác minh manifest, phục hồi database/object/config theo bộ | Log thực thi, checksum, vị trí replay cuối, lỗi/thử lại |
| 7. Áp dụng trạng thái hiện hành | Đội bảo mật/chủ dữ liệu áp dụng thu hồi quyền, bí mật mới và danh mục không được tái xuất hiện | Không kích hoạt lại người dùng, session hoặc đối tượng đã bị loại trừ |
| 8. Kiểm chứng | QA, chủ dữ liệu và bảo mật chạy tiêu chí mục 10 | Kết quả PASS/FAIL cho từng tiêu chí, không bỏ ca lỗi |
| 9. Chuyển lưu lượng | Nền tảng xác nhận nguồn cũ bị fence, chuyển điểm truy cập, đo luồng thực tế | `t_ready` sau kiểm tra thực tế; RPO/RTO và chênh lệch |
| 10. Mở tác vụ và hoàn tất | Đối soát async, mở dần worker/tìm kiếm/báo cáo, giám sát và xử lý dữ liệu mất | Danh mục tác vụ chưa chắc chắn, báo cáo tổn thất, việc khắc phục |

S-02 cần thêm điều tra phạm vi xâm nhập, xác nhận image/cấu hình sạch, xoay bí mật và lý do chọn dữ liệu không bị ảnh hưởng. Nếu bằng chứng không đủ, người phụ trách an toàn có quyền giữ dịch vụ đóng; hồ sơ báo không đạt thời gian thay vì bỏ bước an toàn.

Khi một bộ backup hỏng, chỉ chuyển sang bộ dự phòng sau khi xác minh phụ thuộc và tính lại khoảng mất dữ liệu. Thời gian thử bộ lỗi vẫn thuộc thời gian phục hồi thực tế.

Nếu môi trường đích không qua kiểm chứng, giữ trạng thái cô lập hoặc quay về một trạng thái phục vụ được phép theo kế hoạch; không mở ghi đồng thời tại cả nguồn lẫn đích. Kế hoạch quay lại cần có quyết định về dữ liệu mới phát sinh ở đích, không chỉ thao tác đổi DNS.

## 10. Tiêu chí chấp nhận trước khi mở dịch vụ

### 10.1. Toàn vẹn và tính đầy đủ

- Database mở được, schema khớp ứng dụng và replay dừng đúng điểm đã chọn, không có đoạn log bị bỏ qua không giải thích được.
- Bộ dữ liệu ứng dụng không có tham chiếu tệp bắt buộc bị thiếu; manifest object/version được đối chiếu với kho đích.
- Kiểm tra số lượng theo tenant, khóa ngoại và các bất biến nghiệp vụ đã định nghĩa. So sánh với watermark/checksum đáng tin ở cùng điểm, không so nhầm số lượng hiện tại của nguồn với database đã quay về quá khứ.
- Tất cả thành phần của recovery set vượt kiểm tra checksum/xác thực; việc lấy mẫu dữ liệu nghiệp vụ bổ sung cho đối chiếu này, không thay thế nó.
- Các sequence đã được xác nhận trước `t_c` trong fixture không bị thiếu. Những thay đổi sau `t_c` được liệt kê là còn, mất hoặc chưa xác định; không tự coi mọi thứ sau mốc đó đều đã mất nếu thực tế vẫn phục hồi được.

### 10.2. Xác thực, phân quyền và dữ liệu không được tái xuất hiện

Người dùng tenant A không đọc hoặc sửa được dữ liệu tenant B. Quyền quản trị, quyền chia sẻ tệp và các trạng thái thu hồi phải đáp ứng chính sách hiện hành.

Để không làm sống lại đối tượng đã bị loại trừ sau điểm backup, tình huống dùng một sổ quyết định hiện hành lưu trong miền bảo vệ độc lập: định danh tenant/đối tượng, quyết định thu hồi/xóa hoặc cấm phục vụ lại, thời điểm có hiệu lực, người phê duyệt và phiên bản tăng dần. Sổ không chứa nguyên nội dung dữ liệu đã xóa và phải được bảo vệ/đối soát như một phụ thuộc phục hồi riêng.

Trước mở dịch vụ, áp dụng những quyết định còn hiệu lực từ sổ lên dữ liệu cũ vừa restore. Nếu không lấy được nguồn quyết định đáng tin, không mặc định mọi quyền/đối tượng cũ được phép trở lại; giữ phạm vi bị ảnh hưởng đóng và yêu cầu đối soát được phê duyệt.

Backup giữ dữ liệu lịch sử phục vụ mục đích đã xác định, không đồng nghĩa được phục vụ lại mọi dữ liệu đó. Chính sách vòng đời phải nêu cách xử lý bản backup khi hết retention, quyền truy cập khi còn giữ và việc kiểm tra lại sau restore; đây là yêu cầu sản phẩm của tình huống, không phải một kết luận về tuân thủ pháp luật cụ thể.

### 10.3. Nghiệp vụ và khả năng phục vụ

Kiểm thử qua đường truy cập mà người dùng thực tế sẽ dùng: đăng nhập, đọc/tạo/cập nhật công việc, bình luận và lấy tệp đúng quyền. Kiểm tra cả đường ghi và đọc lại sau commit.

Bài tập chốt tải nghiệm thu cốt lõi 50 request/giây, tỷ lệ đọc/ghi 80/20, duy trì 10 phút sau chuyển lưu lượng. Lỗi kỹ thuật dưới 1%, p95 API đọc không quá 800 ms và p95 API ghi không quá 1500 ms với fixture đại diện; các kiểm thử cố ý từ chối quyền không được tính vào lỗi kỹ thuật. Tệp được kiểm tra riêng về nội dung và quyền, không gộp thời gian tải tệp lớn vào ngưỡng API JSON.

Những ngưỡng này là giả định của bài; bản thiết kế thực phải lấy từ tải nghiệp vụ và SLO hiện hành. Mười phút kiểm tra sau chuyển lưu lượng nằm trong ngân sách 15 phút của bước cuối, và `t_ready` được chốt sau khi đạt kiểm tra, không phải ngay lúc đổi tuyến.

Tìm kiếm, báo cáo và thông báo có mục tiêu trở lại đầy đủ trong 24 giờ từ `t0` của S-01. Việc cho chúng phục hồi sau không cho phép trì hoãn đăng nhập, phân quyền hoặc tệp vốn thuộc tầng cốt lõi. Nếu tác vụ async chưa thể đối soát trong 24 giờ, báo vi phạm mục tiêu tương ứng.

### 10.4. Tác dụng bên ngoài và idempotency

Một bảng `processed_events` được restore về quá khứ có thể quên rằng email/webhook đã gửi. Sao lưu bảng này cùng database không tự giải quyết việc bên ngoài đã nhận tác dụng sau `t_c`.

Các phương án có thể kết hợp:

- Dùng định danh sự kiện/nghiệp vụ ổn định và bên nhận có hợp đồng chống lặp còn hiệu lực sau sự cố.
- Đối soát với sổ kết quả nằm ngoài miền quay lùi hoặc với nguồn bên nhận đáng tin.
- Đưa sự kiện có trạng thái không chắc chắn vào danh sách chờ xác nhận, giữ worker tương ứng tắt và xử lý theo quy trình nghiệp vụ.

Nếu không chứng minh được trạng thái đã thực hiện, không tự gửi lại mọi sự kiện còn trong outbox. Đồng thời, không xóa toàn bộ outbox để tránh trùng vì sẽ làm mất tác vụ chưa thực hiện. Báo rõ tập đã gửi, chưa gửi và chưa xác định, cùng quyết định cho từng tập.

Đối với request được client retry, dữ liệu idempotency cũng có thể bị lùi. Khả năng trả kết quả cũ phải được đánh giá cùng các định danh nghiệp vụ và cơ chế đối soát; không hứa chống lặp xuyên sự cố chỉ vì API bình thường có header idempotency.

## 11. Quan sát, cảnh báo và hồ sơ bằng chứng

### 11.1. Những đại lượng cần theo dõi

| Đại lượng | Ý nghĩa | Phản ứng cần có |
| --- | --- | --- |
| Tuổi điểm phục hồi nhất quán | Thời điểm hiện tại trừ `t_c` của bộ có thể dùng | Đánh giá mỗi phút; vượt 10 phút cảnh báo, vượt 15 phút báo vi phạm S-01 |
| Khoảng trống log/phụ thuộc | Có đủ chuỗi để tới điểm đã cam kết không | Hạ trạng thái bộ bị ảnh hưởng, không quảng bá điểm sai |
| Độ mới bản sao ngoài vùng | Phần dữ liệu đã tới miền backup độc lập | Cảnh báo khi luồng sao chép chậm dù backup nội vùng vẫn xanh |
| Khả năng giải mã | Khóa/phiên bản/quyền còn dùng được qua đường phục hồi | Cảnh báo lỗi trước khi cần restore thật |
| Thời gian restore đã đo | Tổng và từng giai đoạn theo dung lượng | So với ngân sách; dự báo tác động tăng trưởng |
| Thử truy cập/xóa trái phép | Hành vi ngoài vai trò cho phép | Ghi audit độc lập và chuyển xử lý an toàn |
| Dung lượng và thành phần sắp hết hạn | Nguy cơ hết chỗ hoặc mất phụ thuộc đầu cửa sổ | Chặn dọn sai, bổ sung năng lực hoặc xử lý lệch chính sách |
| Tuổi lần diễn tập thành công | Bằng chứng còn phù hợp với triển khai hiện tại không | Nhắc chủ sở hữu và ghi nhận quá hạn |

Khi nguồn đang có ghi, độ mới phải phản ánh các commit/object đã được xác nhận. Khi nguồn không thay đổi, cơ chế heartbeat/checkpoint đáng tin có thể chứng minh bộ phục hồi đã bao phủ tới mốc gần hiện tại; không sửa timestamp của một bản backup cũ để tạo cảm giác dữ liệu đang mới.

Cảnh báo phải đi tới người có khả năng hành động và có đường dự phòng khi production mất. Việc cảnh báo xuất hiện trong dashboard nằm cùng vùng bị hỏng chưa đủ cho kịch bản mất vùng.

### 11.2. Hồ sơ của một lần diễn tập

```yaml
exercise_id: DR-2026-Q4-01
policy_version: BRP-TASK-1.0
scenario: S-01
recovery_set_id: rs-20261128-0852
reference_time: '2026-11-28T09:00:00Z'
recoverable_commit_time: '2026-11-28T08:52:00Z'
impact_started_at: '2026-11-28T09:00:00Z'
core_accepted_at: '2026-11-28T12:35:00Z'
data_loss_window_minutes: 8
rto_minutes: 215
data_loss_target_minutes: 15
rto_target_minutes: 240
core_validation: PASS
security_validation: PASS
rpo_result: PASS
rto_result: PASS
```

Đây là ví dụ cấu trúc bằng chứng, không phải kết quả một cuộc diễn tập đã được thực hiện. Các giá trị phải được lấy từ log/timeline thật, kèm dung lượng, tốc độ, phiên bản triển khai và vị trí bằng chứng kiểm tra.

Không lưu nội dung công việc, tài liệu, khóa hay token trong báo cáo kỹ thuật. Dùng mã định danh tham chiếu và kho bằng chứng có kiểm soát quyền. Audit cần ghi được ai đã chọn bộ, ai phê duyệt, ai đọc/giải mã, môi trường đích và kết quả dọn môi trường tạm.

## 12. Bộ ca kiểm thử nghiệm thu

Fixture cần có ít nhất hai tenant, thay đổi có sequence mỗi phút, tệp có version/checksum, tài khoản đã thu hồi, đối tượng không được phục vụ lại và tác vụ có kết quả ngoài hệ thống. Đồng hồ các nguồn bằng chứng phải được đồng bộ đủ cho độ chính xác phép đo; dùng UTC trong timeline và ghi sai số nếu có.

Dùng môi trường diễn tập được phê duyệt, không phá dữ liệu production để tạo bằng chứng. Những phép thử quyền xóa/khóa cần thực hiện trên tài nguyên thử có cùng cơ chế kiểm soát, không tắt bất biến để dọn cho nhanh.

| Mã | Kịch bản thử | Kỳ vọng/bằng chứng | Yêu cầu |
| --- | --- | --- | --- |
| T-01 | Mất quyền/kết nối hoàn toàn tới vùng A | Phục hồi từ miền B và đường khóa độc lập; RPO <= 15 phút, RTO cốt lõi <= 240 phút | BR-01 đến BR-04, BR-07 |
| T-02 | Ngắt đồng bộ log/object trong khi nguồn tiếp tục ghi | Cảnh báo đúng độ trễ; không công bố điểm mới hơn phần đầy đủ | BR-01, BR-02 |
| T-03 | Backup job xanh nhưng thiếu một đoạn log | Recovery set bị đánh dấu không dùng được tới điểm yêu cầu | BR-01, BR-08 |
| T-04 | Database mới hơn object; xóa một object version cần thiết ở bản thử | Phát hiện tham chiếu thiếu; không PASS tầng cốt lõi | BR-01, BR-09 |
| T-05 | Role production thử xóa/sửa/rút ngắn retention | Bị từ chối, bản đã cam kết vẫn dùng được, audit ghi độc lập | BR-04, BR-05 |
| T-06 | Role vận hành backup thường nhật thử phá bản đang khóa | Không vượt cơ chế bất biến bằng quyền thường nhật | BR-05, BR-06 |
| T-07 | Role không được phép đọc/giải mã/xuất | Bị từ chối và có bằng chứng quyền tối thiểu | BR-06 |
| T-08 | Production mất dịch vụ khóa/danh tính | Đường khẩn cấp đã phê duyệt vẫn restore được | BR-07 |
| T-09 | Rotate khóa, restore bộ dùng phiên bản cũ | Giải mã được; kiểm tra phụ thuộc ngăn hủy khóa đang cần | BR-07 |
| T-10 | Sửa byte backup hoặc manifest ở bộ thử | Phát hiện sai checksum/xác thực; không mở dịch vụ từ bộ đó | BR-08 |
| T-11 | S-02 với bản mới nằm trong khoảng nghi xâm nhập | Chọn điểm sạch có bằng chứng; đo lại mất dữ liệu/RTO và kiểm tra bí mật mới | BR-03, BR-08 |
| T-12 | Không tìm được điểm sạch trong 24 giờ của S-02 | Báo không đạt/ngoài giả định, không dùng bản nghi ngờ để đạt thời gian | BR-03, BR-08 |
| T-13 | Lỗi âm thầm từ nhiều ngày trước mới được phát hiện | Báo timeline và tổn thất thực, không lấy RPO mất vùng làm bằng chứng | BR-02, BR-08 |
| T-14 | Khôi phục sát đầu cửa sổ 35 ngày | Còn đủ full/log/object/key; job dọn không cắt chuỗi cần thiết | BR-01, BR-05 |
| T-15 | Nguồn cũ quay lại sau chuyển vùng | Nguồn vẫn bị fence, chỉ một nơi nhận ghi/phát tác vụ | BR-09 |
| T-16 | Restore tenant A trong khi B tiếp tục ghi | A được đối soát; B không quay lùi và không lộ dữ liệu | BR-10 |
| T-17 | Restore điểm trước thu hồi quyền/quyết định loại trừ dữ liệu | Áp dụng sổ hiện hành; không tái kích hoạt quyền/đối tượng bị cấm | BR-06, BR-10 |
| T-18 | Outbox chứa tác vụ đã gửi bên ngoài sau `t_c` | Đối soát/chống lặp; trạng thái chưa chắc chắn không tự phát lại | BR-11 |
| T-19 | Client retry request có idempotency record bị mất sau restore | Xử lý theo định danh/đối soát đã đặc tả; không tuyên bố chống lặp khi thiếu bằng chứng | BR-11 |
| T-20 | Dung lượng tăng hoặc throughput giảm còn 100 MiB/giây | Báo nguy cơ/không đạt ngân sách; có hành động thiết kế rõ ràng | BR-03, BR-12 |
| T-21 | Database đã lên nhưng đăng nhập, tệp hoặc quyền tenant còn lỗi | Chưa chốt `t_ready`, kết quả phục hồi cốt lõi FAIL | BR-03, BR-09, BR-10 |
| T-22 | Lần restore đầu thất bại rồi chọn bộ dự phòng | Tổng thời gian tính cả lần lỗi, tính lại RPO theo bộ cuối | BR-03, BR-08 |
| T-23 | Thay engine/schema/IAM hoặc chính sách khóa | Đánh giá và thử lại đường phục hồi liên quan, phiên bản bằng chứng khớp triển khai | BR-07, BR-12 |
| T-24 | Kết thúc diễn tập, hết quyền tạm và dọn staging | Thu hồi quyền, không còn dữ liệu thử ngoài chính sách, audit vẫn được giữ | BR-06, BR-12 |

Với mỗi ca, ghi rõ PASS/FAIL của mục tiêu dữ liệu, thời gian và an toàn riêng biệt. Một cuộc thử có thể restore dữ liệu đúng nhưng không đạt RTO, hoặc đạt thời gian nhưng sai phân quyền; không gộp thành một nhãn “restore thành công”.

Bổ sung thử thiếu người phê duyệt, quota đích không đủ, cảnh báo production không tới được người trực và worker bị mở trước đối soát. Đó là các lỗi đường phục hồi cần đưa vào kế hoạch, không chỉ là lỗi công cụ backup.

## 13. Ma trận truy vết rủi ro–yêu cầu–bằng chứng

| Rủi ro | Yêu cầu chính | Quyết định thiết kế | Bằng chứng |
| --- | --- | --- | --- |
| R-01 | BR-01, BR-03, BR-04 | Recovery set ngoài vùng, hạ tầng đích dựng lại được | T-01 và timeline toàn tuyến |
| R-02 | BR-04, BR-05 | Miền quyền độc lập, lưu bất biến | T-05, T-06 và log bị từ chối |
| R-03 | BR-06 | Mã hóa, quyền tạm, staging cô lập | T-07, T-24 và audit |
| R-04 | BR-07 | Khóa/phiên bản/danh tính khẩn cấp không chỉ ở production | T-08, T-09 |
| R-05 | BR-08 | Xác thực manifest, kiểm tra chuỗi log, điểm sạch | T-03, T-10 đến T-13 |
| R-06 | BR-01, BR-09 | Manifest liên thành phần và version object | T-04, T-14 |
| R-07 | BR-03, BR-12 | Ngân sách đường găng, dung lượng và throughput thực đo | T-01, T-20 đến T-22 |
| R-08 | BR-11 | Đối soát tác dụng ngoài, giữ trạng thái chưa chắc chắn | T-18, T-19 |
| R-09 | BR-08, BR-10 | Môi trường sạch, quyền/loại trừ hiện hành | T-11, T-17 |
| R-10 | BR-06, BR-10 | Xác minh yêu cầu, phê duyệt, giới hạn xuất dữ liệu | T-07, T-16, T-24 |
| R-11 | BR-02, BR-12 | Giám sát `t_c`, diễn tập và rà thay đổi | T-02, T-03, T-23 |

Mỗi bằng chứng phải ghi phiên bản chính sách, bản triển khai, recovery set, phạm vi dữ liệu và ngày thử. Bằng chứng phục hồi bộ mẫu nhỏ không tự chứng minh thời gian phục hồi bộ 1000 GiB; cần nêu giới hạn của kết luận.

## 14. Nhiệm vụ học viên và sản phẩm cần nộp

### Nhiệm vụ A — Viết chính sách phục hồi

Soạn `BRP-TASK-1.0` với phạm vi dữ liệu, kịch bản, giả định, RPO/RTO, cửa sổ phục hồi, retention, mã hóa, quyền và tiêu chí mở dịch vụ. Giữ rõ khác biệt giữa yêu cầu kết quả và lịch/công cụ thực hiện.

Chủ nghiệp vụ xác nhận mức mất dữ liệu/chức năng được phép trì hoãn; bảo mật xác nhận mô hình đe dọa và điều kiện sạch; nền tảng/dữ liệu chịu trách nhiệm khả năng thực hiện; QA kiểm tra bằng chứng; người điều phối sự cố chịu trách nhiệm timeline và quyết định chuyển trạng thái.

### Nhiệm vụ B — Vẽ kiến trúc và đồ thị phụ thuộc

Chỉ ra tài khoản, vùng, role, khóa, kho manifest, đường backup, đường restore và nguồn quyết định hiện hành. Với mỗi phụ thuộc, trả lời: nếu nó mất cùng production, phục hồi bằng cách nào?

Mô tả cách xác định `t_c` của cả database và tệp, cách bảo vệ đầu cửa sổ 35 ngày và cách chứng minh nguồn cũ không nhận ghi trở lại.

### Nhiệm vụ C — Tính ngân sách và bảo vệ tính khả thi

Lập ngân sách 4 giờ S-01, tính thời gian theo dung lượng/tốc độ hiệu dụng và thêm replay/xác minh. Lập dự toán retention cho các miền lưu, ghi giả định về tốc độ thay đổi và dự phòng.

Phân tích biến thể khi dung lượng gấp đôi hoặc tốc độ đích chỉ đạt 100 MiB/giây. Đề xuất thay đổi kiến trúc/năng lực hoặc một mục tiêu mới có người chịu trách nhiệm chấp nhận; không bỏ các kiểm tra an toàn ra khỏi phép tính.

### Nhiệm vụ D — Lập runbook và kế hoạch diễn tập

Viết runbook có điều kiện bắt đầu/kết thúc, người thực hiện/phê duyệt, điểm dừng an toàn và bằng chứng. Chọn đủ ca trong mục 12 để phủ mọi yêu cầu; thêm fixture cho dữ liệu bị loại trừ và tác vụ bên ngoài.

Nộp một mẫu báo cáo PASS và một mẫu FAIL. Mẫu FAIL phải chỉ rõ mục tiêu nào không đạt, dữ liệu có thể mất, biện pháp hạn chế và việc khắc phục có chủ sở hữu/hạn hoàn thành.

### Nhiệm vụ E — Xử lý một quyết định khó

Điểm sạch gần nhất của S-02 là 30 giờ trước, nhưng mục tiêu mất dữ liệu là 24 giờ. Một bản mới hơn bị nghi chứa thay đổi của kẻ tấn công. Trình bày các lựa chọn, bằng chứng cần thêm, khả năng tái nhập dữ liệu hợp lệ và ai có quyền chấp nhận tác động.

Câu trả lời đạt phải thừa nhận mục tiêu hiện tại chưa được bảo đảm; không tự chọn bản mới chỉ vì timestamp gần hơn, cũng không khẳng định có thể tái dựng toàn bộ dữ liệu khi chưa có nguồn đáng tin.

## 15. Tiêu chí đánh giá và điều kiện hoàn thành

| Tiêu chí | Điểm | Biểu hiện đạt |
| --- | --- | --- |
| Phạm vi, phụ thuộc và mô hình đe dọa | 15 | Bao gồm dữ liệu, tệp, danh tính, khóa và tác dụng ngoài |
| RPO/RTO và kịch bản | 20 | Mốc đo rõ, giả định riêng, không giấu thời gian phát hiện hoặc dữ liệu mất |
| Bảo vệ bản sao và khả năng giải mã | 20 | Miền quyền/lỗi độc lập, bất biến, retention theo phụ thuộc, khóa dùng được |
| Nhất quán và an toàn sau restore | 15 | Không thiếu tệp, không hai nơi cùng ghi, không tái cấp quyền hoặc phát tác vụ mù quáng |
| Runbook, ngân sách và tính khả thi | 15 | Có đường găng, năng lực thực đo, quyết định mở dịch vụ và điểm dừng |
| Kiểm thử, truy vết và bằng chứng | 15 | Có ca thất bại, kiểm thử toàn tuyến, phiên bản và giới hạn kết luận |

Bài chưa hoàn thành nếu chỉ nêu lịch backup, coi replica là bản sao độc lập mà không phân tích quyền xóa, giữ backup nhưng bỏ khóa cũ, tính RTO từ lúc chạy lệnh restore, hoặc mở dịch vụ ngay khi database khởi động.

Một bộ yêu cầu backup và recovery có thể kiểm chứng phải trả lời được: **khôi phục cái gì, từ bản nào, về mốc nào, trong kịch bản nào, mất bao nhiêu dữ liệu, mất bao lâu, ai được thực hiện và bằng chứng nào cho phép mở lại dịch vụ**. Các câu trả lời đó nối mục tiêu an toàn thông tin với kiến trúc, vận hành và kiểm thử trong vòng đời phát triển.
