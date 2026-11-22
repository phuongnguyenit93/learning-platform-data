# Nén, mã hóa, thời gian lưu và bản sao ngoài máy chủ

Trong module **DATABASE_MYSQL**, sao lưu và phục hồi là một phần của vận hành cơ sở dữ liệu quan hệ. Một bản sao lưu chỉ có giá trị khi dữ liệu nhất quán, có thể giải mã, có thể khôi phục trong thời gian mục tiêu và vẫn tồn tại khi máy chủ chính hoặc tài khoản quản trị bị xâm phạm.

Bài học này tập trung vào bốn quyết định vận hành: **nén** để giảm dung lượng và chi phí truyền, **mã hóa** để bảo vệ dữ liệu, **thời gian lưu** để cân bằng khả năng phục hồi với chi phí, và **bản sao ngoài máy chủ** để giữ dữ liệu khi hạ tầng chính gặp sự cố. Các quyết định này cần phối hợp với chiến lược sao lưu đầy đủ, sao lưu tăng dần và binary log của MySQL.

Trong phạm vi DATABASE_MYSQL, chủ đề này nối các kỹ năng thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời với việc đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý sự cố vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và nguyên tắc

Sau bài học, bạn có thể:

- Chọn cách nén phù hợp với loại bản sao lưu và giới hạn CPU, dung lượng, băng thông.
- Phân biệt mã hóa dữ liệu trong MySQL, mã hóa ổ đĩa, mã hóa tệp sao lưu và mã hóa khi truyền.
- Thiết kế vòng đời khóa để bản sao lưu vẫn giải mã được trong toàn bộ thời gian lưu.
- Xây dựng chính sách lưu giữ cho bản sao đầy đủ, bản sao tăng dần và binary log.
- Sao chép bản sao lưu ra hạ tầng độc lập, kiểm tra tính toàn vẹn và bảo vệ bản sao khỏi bị xóa hoặc sửa trái phép.
- Diễn tập khôi phục để xác nhận bản sao lưu đáp ứng RPO và RTO.

Hai chỉ số cần thống nhất với chủ hệ thống:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường biểu diễn bằng thời gian. RPO 15 phút nghĩa là mục tiêu khôi phục dữ liệu đến một thời điểm không cũ hơn khoảng 15 phút trước sự cố.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để đưa dịch vụ trở lại hoạt động sau sự cố.

RPO ảnh hưởng đến tần suất tạo bản sao và chuyển binary log. RTO ảnh hưởng đến loại bản sao, tốc độ khôi phục, dung lượng cần truyền và thời gian diễn tập. Không thể chọn lịch sao lưu chỉ dựa trên dung lượng đĩa mà bỏ qua hai mục tiêu này.

## 2. Nén bản sao lưu

### 2.1. Vì sao cần nén?

Bản sao lưu logic thường chứa câu lệnh SQL và dữ liệu dạng văn bản. Dữ liệu văn bản lặp lại nhiều nên thường nén tốt. Bản sao lưu vật lý chứa các trang dữ liệu, redo log và metadata của hệ thống lưu trữ; mức nén phụ thuộc vào dữ liệu và công cụ tạo bản sao.

Nén có thể giúp:

- Giảm dung lượng lưu trữ và chi phí bản sao ngoài máy chủ.
- Giảm lượng dữ liệu truyền qua mạng khi sao chép đến vùng lưu trữ từ xa.
- Giảm thời gian truyền khi giới hạn chính là băng thông.
- Tạo thêm thời gian lưu lịch sử trong cùng ngân sách lưu trữ.

Nén cũng tiêu tốn CPU và có thể làm chậm tác vụ sao lưu hoặc phục hồi. Nếu hệ thống đã chịu tải CPU cao, nén ở mức quá mạnh có thể ảnh hưởng truy vấn nghiệp vụ. Nếu dữ liệu vốn đã nén như ảnh JPEG, video, tệp ZIP hoặc dữ liệu mã hóa, mức tiết kiệm thường thấp.

### 2.2. Nén ở đâu trong quy trình?

Với bản sao lưu logic, có thể đưa luồng xuất qua bộ nén mà không cần lưu tệp SQL chưa nén:

~~~bash
set -o pipefail
mysqldump --login-path=backup \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases shop | gzip -c > shop.sql.gz
~~~

Ví dụ này minh họa luồng tạo dump và nén bằng gzip. --single-transaction tạo ảnh chụp nhất quán cho các bảng InnoDB trong giao dịch; nó không bảo đảm ảnh chụp nhất quán cho bảng không hỗ trợ giao dịch. Trong lúc dump, cần hạn chế thay đổi DDL có thể làm ảnh hưởng đến quá trình đọc metadata. Nếu có bảng không giao dịch hoặc yêu cầu nhất quán phức tạp, hãy dùng phương pháp khóa hoặc công cụ backup phù hợp với kiến trúc.

--routines, --events và --triggers giúp đưa các đối tượng tương ứng vào bản dump. Tuy nhiên, dump một schema nghiệp vụ không tự động thay thế việc sao lưu tài khoản, role, quyền cấp, cấu hình máy chủ, plugin và tài liệu vận hành. Hãy kiểm tra phạm vi thực tế của từng loại bản sao.

Với bản sao lưu vật lý, công cụ như MySQL Enterprise Backup hoặc Percona XtraBackup có thể cung cấp các chế độ nén và tối ưu luồng sao lưu riêng. Cú pháp, khả năng song song và yêu cầu phiên bản phụ thuộc công cụ và phiên bản đang dùng. Cần kiểm tra tài liệu của đúng phiên bản, đồng thời xác nhận quy trình prepare/restore trước khi triển khai.

### 2.3. Chọn thuật toán và mức nén

| Cách nén | Đặc điểm | Khi phù hợp |
|---|---|---|
| gzip | Phổ biến, tương thích rộng, mức nén và tốc độ ở mức cân bằng | Quy trình đơn giản, cần dễ giải nén trên nhiều máy |
| zstd | Có nhiều mức cân bằng tốc độ và tỷ lệ nén; thường phù hợp luồng dữ liệu lớn | Cần điều chỉnh theo CPU, băng thông và tốc độ phục hồi |
| Nén tích hợp trong công cụ backup | Có thể tận dụng định dạng và xử lý song song của công cụ | Backup vật lý hoặc hệ thống đã chuẩn hóa công cụ chuyên dụng |

Đừng chọn mức nén chỉ theo tỷ lệ nhỏ nhất. Hãy đo cả thời gian tạo bản sao, CPU sử dụng, kích thước kết quả, tốc độ truyền và thời gian giải nén khi phục hồi. Mục tiêu là hoàn thành sao lưu trong cửa sổ vận hành và phục hồi trong RTO.

### 2.4. Nén trước khi mã hóa

Thứ tự thông thường là **sao lưu → nén → mã hóa**. Dữ liệu đã mã hóa có tính ngẫu nhiên cao nên hầu như không nén thêm được. Nếu mã hóa trước rồi mới nén, CPU và thời gian thường bị lãng phí mà dung lượng giảm rất ít.

Với quy trình nhiều bước, phải kiểm tra mã thoát của từng lệnh trong pipeline. Trên Bash, có thể bật set -o pipefail để lỗi từ lệnh xuất hoặc nén không bị che khuất bởi lệnh phía sau. Chỉ đánh dấu bản sao hoàn tất khi toàn bộ pipeline thành công và tệp đầu ra được kiểm tra.

## 3. Mã hóa bản sao lưu

### 3.1. Phân biệt các lớp mã hóa

Có nhiều lớp bảo vệ dữ liệu, nhưng chúng không thay thế lẫn nhau:

| Lớp bảo vệ | Bảo vệ điều gì? | Giới hạn cần nhớ |
|---|---|---|
| TLS khi kết nối MySQL | Dữ liệu truyền giữa client và server | Không bảo vệ tệp sao lưu sau khi tệp được tạo |
| Mã hóa ổ đĩa hoặc volume | Dữ liệu lưu trên thiết bị khi thiết bị hoặc volume bị truy cập trái phép | Tệp có thể được đọc bởi tiến trình đã mở volume hợp lệ |
| Mã hóa tablespace hoặc dữ liệu trong MySQL | Một số tệp dữ liệu của MySQL trên đĩa | Phụ thuộc phiên bản, edition, engine và cấu hình keyring; không tự động mã hóa mọi bản dump |
| Mã hóa tệp sao lưu | Bản sao lưu đã xuất hoặc đóng gói | Cần quản lý khóa để có thể giải mã khi khôi phục |
| Mã hóa khi truyền đến nơi lưu trữ | Bảo vệ dữ liệu trên đường truyền đến máy chủ hoặc object storage | Không thay thế mã hóa khi lưu trữ |

Ví dụ, InnoDB tablespace encryption có thể bảo vệ tệp tablespace theo cấu hình và khả năng của phiên bản MySQL. Một bản dump SQL được xuất ra vẫn là dữ liệu có thể đọc nếu không được mã hóa riêng. Vì vậy, hãy xác định rõ dữ liệu nào được mã hóa ở từng chặng.

### 3.2. Mã hóa tệp sau khi nén

Có thể dùng GnuPG để mã hóa đối xứng một tệp dump đã nén:

~~~bash
set -o pipefail
mysqldump --login-path=backup \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases shop \
  | gzip -c \
  | gpg --symmetric --cipher-algo AES256 \
      --output /srv/backups/shop.sql.gz.gpg
~~~

GPG sẽ yêu cầu cụm mật khẩu theo cơ chế tương tác được cấu hình. Không đưa mật khẩu MySQL, cụm mật khẩu mã hóa hoặc khóa bí mật trực tiếp vào câu lệnh, script được chia sẻ, log hoặc biến môi trường dễ bị lộ. Tài khoản dùng để tạo backup cũng nên có quyền tối thiểu và được quản lý riêng.

Giải mã và phục hồi bản dump:

~~~bash
set -o pipefail
gpg --decrypt /srv/backups/shop.sql.gz.gpg \
  | gzip -dc \
  | mysql --login-path=restore
~~~

Lệnh phục hồi minh họa cho bản dump được tạo với --databases shop, do đó nội dung dump có thông tin tạo/chọn cơ sở dữ liệu. Hãy chạy trong môi trường khôi phục đã chuẩn bị, xác nhận đúng máy chủ và đúng mục tiêu trước khi nạp dữ liệu. Với dữ liệu sản xuất, nên phục hồi thử trên máy độc lập trước.

Một số công cụ backup vật lý có khả năng mã hóa tích hợp. Khi sử dụng, cần kiểm tra thuật toán, cách cấp khóa, cách khôi phục khóa và khả năng tương thích của phiên bản công cụ. Tránh mã hóa hai lần nếu chưa đánh giá tác động đến tốc độ và quy trình khôi phục.

### 3.3. Quản lý khóa và cụm mật khẩu

Mất khóa giải mã có thể khiến bản sao lưu không thể sử dụng dù tệp còn nguyên vẹn. Ngược lại, người có khóa và quyền đọc bản sao lưu có thể truy cập dữ liệu nhạy cảm. Quản lý khóa phải là một phần của kế hoạch khôi phục.

Các nguyên tắc nên áp dụng:

- Lưu khóa mã hóa trong KMS, HSM hoặc hệ thống quản lý bí mật được kiểm soát; giới hạn người và dịch vụ có thể sử dụng khóa.
- Tách quyền quản trị khóa khỏi quyền xóa hoặc tải bản sao lưu. Một tài khoản bị xâm phạm không nên đồng thời có thể xóa bản sao và phá hủy khóa.
- Không lưu khóa hoặc cụm mật khẩu trong cùng thư mục, cùng tài khoản hoặc cùng bản sao lưu với dữ liệu đã mã hóa.
- Có bản sao dự phòng của vật liệu khóa theo quy trình được kiểm soát, có người chịu trách nhiệm và có kiểm tra khả năng truy xuất.
- Ghi nhận phiên bản khóa, thời điểm tạo, phạm vi sử dụng và quy trình luân chuyển.
- Kiểm tra giải mã bằng khóa thực tế trong các buổi diễn tập khôi phục.

Nếu dùng mã hóa theo mô hình envelope encryption, dữ liệu được mã hóa bằng khóa dữ liệu (DEK), sau đó DEK được bảo vệ bằng khóa mã hóa khóa (KEK) trong KMS/HSM. Khi luân chuyển KEK, cần bảo đảm các DEK cũ vẫn có thể được giải bọc hoặc tái bảo vệ. Không xóa khóa cũ khi còn bản sao lưu phụ thuộc vào khóa đó.

Thời gian lưu khóa phải ít nhất bằng thời gian lưu bản sao lưu liên quan, cộng thêm khoảng dự phòng theo chính sách. Một bản backup lưu 12 tháng nhưng khóa bị xóa sau 90 ngày sẽ không thể khôi phục khi cần kiểm tra dữ liệu lịch sử.

## 4. Chính sách thời gian lưu

### 4.1. Thiết kế theo RPO, RTO và nhu cầu nghiệp vụ

Thời gian lưu quyết định ta có thể quay lại những mốc nào trong quá khứ. Chính sách cần trả lời:

- Cần khôi phục đến thời điểm nào nếu lỗi được phát hiện muộn?
- Dữ liệu cần lưu trong bao lâu theo hợp đồng, quy định hoặc yêu cầu kiểm toán?
- Bao lâu thì một bản sao lưu được thay thế bởi bản mới?
- Các bản sao tăng dần có phụ thuộc vào bản đầy đủ nào?
- Binary log cần được giữ bao lâu để phục hồi đến một thời điểm?
- Khóa mã hóa và metadata khôi phục sẽ được lưu đến khi nào?

Lưu trữ lâu hơn không phải lúc nào cũng tốt hơn nếu không có khả năng kiểm soát truy cập, mã hóa và xóa theo quy định. Ngược lại, lưu quá ngắn có thể khiến sự cố âm thầm hoặc lỗi dữ liệu chỉ được phát hiện sau khi bản sao sạch đã bị ghi đè.

### 4.2. Ví dụ lịch lưu giữ

Bảng dưới đây là ví dụ để thảo luận với chủ hệ thống; không phải lịch bắt buộc cho mọi workload:

| Loại bản sao | Ví dụ tần suất | Ví dụ thời gian lưu | Mục đích |
|---|---|---|---|
| Full backup | Hàng tuần | 8 tuần | Mốc phục hồi độc lập theo chu kỳ |
| Incremental backup | Hàng ngày | Đến khi chuỗi full tương ứng hết hạn | Giảm lượng dữ liệu phải sao lưu mỗi ngày |
| Binary log | Ghi liên tục, chuyển ra kho lưu trữ định kỳ | 14–35 ngày hoặc theo RPO và nhu cầu PITR | Phục hồi đến thời điểm cụ thể |
| Bản full dài hạn | Hàng tháng | 6–12 tháng hoặc theo yêu cầu | Kiểm toán, điều tra hoặc nghĩa vụ lưu trữ |

Thời gian thực tế cần căn cứ vào yêu cầu pháp lý, hợp đồng, độ nhạy dữ liệu, tốc độ tăng trưởng và ngân sách. Nếu có bản incremental phụ thuộc vào một bản full và các incremental trước đó, phải giữ đủ toàn bộ chuỗi cần thiết. Xóa bản full nền trong khi vẫn giữ incremental phụ thuộc vào nó sẽ làm chuỗi khôi phục mất hiệu lực.

### 4.3. Binary log và phục hồi đến thời điểm

Bản full hoặc incremental tạo mốc dữ liệu. Binary log ghi lại các thay đổi đủ điều kiện để phát lại sau mốc đó, giúp thực hiện **point-in-time recovery (PITR)**. Để PITR hoạt động, cần:

1. Có một bản full hoặc chuỗi backup có thể phục hồi.
2. Có binary log liên tục từ mốc backup đến thời điểm mục tiêu.
3. Lưu metadata như GTID set hoặc tọa độ binlog tương ứng với bản backup.
4. Có công cụ và quy trình phát lại log đến đúng thời điểm hoặc vị trí cần khôi phục.
5. Có khóa và cấu hình cần thiết để mở dữ liệu sau phục hồi.

Chính sách lưu binary log phải tính cả thời gian phát hiện sự cố. Nếu lỗi dữ liệu được phát hiện sau 20 ngày nhưng binary log chỉ được lưu 7 ngày, hệ thống có thể không còn đủ log để quay về trước thời điểm lỗi.

Không xóa binary log chỉ vì bản full mới đã tạo xong. Hãy xác nhận bản backup đã được sao chép, kiểm tra và không còn cần các log cũ cho bất kỳ chuỗi phục hồi nào trước khi dọn dẹp.

### 4.4. Ước tính dung lượng

Dung lượng không chỉ là kích thước của một bản full. Cần tính:

- Kích thước full sau nén.
- Dữ liệu thay đổi mỗi ngày và kích thước incremental.
- Tốc độ phát sinh binary log.
- Số bản lưu theo từng chu kỳ.
- Bản sao ngoài máy chủ và vùng tạm dùng trong lúc tạo hoặc phục hồi.
- Bản lưu dài hạn, metadata, checksum và vật liệu khóa theo chính sách.

Một ước tính sơ bộ:

\[
S_{\text{total}} \approx
N_f S_f + N_i S_i + N_b S_b + S_{\text{temp}} + S_{\text{overhead}}
\]

Trong đó \(N_f\), \(N_i\), \(N_b\) là số bản full, incremental và đơn vị lưu binary log; \(S_f\), \(S_i\), \(S_b\) là kích thước trung bình tương ứng. Đây là mô hình ngân sách ban đầu; cần đo dữ liệu thực tế vì incremental và binary log thay đổi theo workload.

Theo dõi dung lượng theo thời gian. Khi tốc độ tăng dữ liệu hoặc tốc độ ghi log thay đổi, hãy tính lại thời gian lưu có thể đáp ứng trong ngân sách hiện tại.

## 5. Bản sao ngoài máy chủ

### 5.1. Vì sao cần bản sao độc lập?

Nếu tất cả bản sao lưu nằm trên cùng máy chủ, cùng volume hoặc cùng tài khoản quản trị với MySQL, một sự cố có thể làm mất cả dữ liệu gốc lẫn bản sao. Các tình huống thường gặp:

- Hỏng thiết bị lưu trữ hoặc lỗi volume.
- Xóa nhầm thư mục backup trong quá trình vận hành.
- Tài khoản quản trị hoặc máy chủ backup bị chiếm quyền.
- Ransomware mã hóa dữ liệu và các bản sao đang gắn trực tuyến.
- Sự cố tại trung tâm dữ liệu hoặc vùng triển khai.
- Lỗi cấu hình, thao tác hoặc phần mềm làm hỏng nhiều bản sao cùng lúc.

Bản sao ngoài máy chủ cần có ranh giới lỗi độc lập: máy chủ khác, vùng lưu trữ khác, tài khoản hoặc dự án cloud khác, và thông tin xác thực riêng. Nếu yêu cầu phục hồi sau thảm họa vùng, hãy lưu thêm bản sao ở vùng địa lý khác.

### 5.2. Nguyên tắc 3-2-1-1-0

Một cách kiểm tra thiết kế phổ biến là:

- **3 bản:** dữ liệu chính và ít nhất hai bản sao.
- **2 loại phương tiện hoặc miền lưu trữ:** giảm rủi ro một loại thiết bị hay dịch vụ gặp lỗi chung.
- **1 bản ngoài địa điểm:** tách khỏi trung tâm dữ liệu chính.
- **1 bản offline hoặc immutable:** khó bị sửa/xóa trong khoảng thời gian bảo vệ.
- **0 lỗi chưa được phát hiện:** kiểm tra checksum, giải mã và diễn tập khôi phục.

Đây là nguyên tắc thiết kế, không phải bảo đảm tuyệt đối. Các bản sao vẫn cần kiểm soát quyền truy cập, theo dõi trạng thái và kiểm tra phục hồi thực tế.

### 5.3. Quy trình chuyển bản sao ra ngoài

Một luồng vận hành an toàn có thể gồm:

1. Tạo bản backup vào thư mục staging có quyền truy cập hạn chế.
2. Đợi công cụ hoàn tất và kiểm tra mã thoát, kích thước, định dạng, tính nhất quán.
3. Nén và mã hóa trước khi rời khỏi vùng tin cậy của máy chủ, nếu quy trình mã hóa được thực hiện ở lớp ứng dụng.
4. Tạo checksum hoặc manifest có chữ ký để kiểm tra tệp khi truyền và khi lưu trữ.
5. Truyền qua kênh mã hóa đến máy chủ backup hoặc object storage.
6. Xác minh bản sao từ phía đích: kích thước, checksum, quyền đọc và khả năng truy xuất.
7. Áp dụng chính sách retention và immutability ở nơi lưu trữ đích.
8. Chỉ dọn bản tạm theo chính sách sau khi bản sao từ xa được xác minh.

Có thể dùng rsync qua SSH cho máy chủ backup độc lập hoặc công cụ đồng bộ object storage có TLS. Ví dụ sao chép tệp đã hoàn tất:

~~~bash
rsync -a --partial \
  /srv/backups/shop.sql.gz.gpg \
  backupuser@backup-host:/srv/mysql-backups/
~~~

Lệnh minh họa việc truyền tệp đến một máy chủ khác. Nó không tự tạo tính bất biến và cũng không chứng minh bản sao ở đích giải mã được. Cần xác minh tệp ở đích, phân quyền riêng và cơ chế ngăn xóa/sửa ngoài ý muốn.

Với object storage, cân nhắc versioning, Object Lock hoặc retention lock theo mô hình lưu trữ được chọn. Cấu hình thời hạn bất biến phải phù hợp với chính sách xóa dữ liệu và yêu cầu tuân thủ. Tài khoản ghi backup không nên có quyền rút ngắn thời gian khóa hoặc xóa phiên bản đã khóa.

### 5.4. Tách quyền và bảo vệ thông tin xác thực

- Dùng tài khoản riêng để ghi bản sao lên hệ thống lưu trữ từ xa.
- Giới hạn tài khoản backup chỉ được ghi vào vùng đích được chỉ định.
- Dùng tài khoản khác cho thao tác xóa hoặc thay đổi retention; bảo vệ bằng MFA và quy trình phê duyệt phù hợp.
- Không lưu SSH private key, cloud access key hoặc mật khẩu trong thư mục backup hay trong script được commit.
- Luân chuyển thông tin xác thực theo quy trình, theo dõi hoạt động tải lên/xóa và cảnh báo khi có thay đổi bất thường.
- Kiểm tra khả năng truy cập kho lưu trữ từ một môi trường khôi phục độc lập, kể cả khi máy chủ MySQL chính không hoạt động.

Bản sao ngoài máy chủ vẫn có thể bị lộ nếu tài khoản đọc hoặc khóa giải mã bị xâm phạm. Vì vậy, tách vị trí lưu trữ, tách quyền và mã hóa phải được thực hiện đồng thời.

## 6. Kiểm tra tính toàn vẹn và khả năng phục hồi

### 6.1. Kiểm tra tệp không đồng nghĩa kiểm tra phục hồi

Một tệp có kích thước hợp lý hoặc checksum khớp chỉ chứng minh một phần. Các bước kiểm tra nên tăng dần:

- Kiểm tra mã thoát và log của công cụ backup.
- Xác nhận tệp không rỗng và kích thước nằm trong khoảng hợp lý.
- Kiểm tra định dạng nén, ví dụ dùng gzip -t với tệp gzip.
- Giải mã thử để xác nhận khóa/cụm mật khẩu còn dùng được.
- So sánh checksum của tệp nguồn và tệp đích sau truyền.
- Phục hồi vào máy chủ thử nghiệm và kiểm tra dữ liệu, đối tượng, quyền cùng khả năng truy vấn.

Với ví dụ tệp đã mã hóa ở trên, có thể giải mã luồng và kiểm tra cấu trúc gzip mà chưa nạp dữ liệu vào MySQL:

~~~bash
set -o pipefail
gpg --decrypt /srv/backups/shop.sql.gz.gpg | gzip -t
~~~

Tạo checksum cho tệp:

~~~bash
sha256sum /srv/backups/shop.sql.gz.gpg \
  > /srv/backups/shop.sql.gz.gpg.sha256
~~~

Sau khi truyền, kiểm tra checksum tại đích bằng manifest đã chuyển cùng tệp qua kênh tin cậy. Nếu đối tượng đe dọa bao gồm kẻ có thể sửa cả tệp lẫn manifest, checksum đơn thuần không đủ để xác thực nguồn; cần chữ ký số hoặc MAC được bảo vệ bằng khóa riêng.

### 6.2. Diễn tập khôi phục

Lập lịch diễn tập trên máy chủ hoặc môi trường cô lập, có phiên bản MySQL tương thích. Một bài diễn tập nên xác nhận:

1. Có thể truy xuất bản full và mọi incremental phụ thuộc.
2. Có thể lấy đủ binary log cho mốc cần phục hồi.
3. Có thể truy xuất khóa hoặc cụm mật khẩu mà không phụ thuộc vào máy chủ đã hỏng.
4. Có thể giải mã và giải nén toàn bộ dữ liệu.
5. Công cụ phục hồi hoàn tất mà không có lỗi chưa xử lý.
6. Schema, bảng, index, trigger, routine, event và quyền cần thiết được khôi phục đúng phạm vi.
7. Các truy vấn kiểm tra dữ liệu và kiểm tra nghiệp vụ trả kết quả mong đợi.
8. Thời gian thực tế đáp ứng RTO và điểm dữ liệu đáp ứng RPO.

Đo thời gian từ lúc bắt đầu truy xuất bản sao đến khi ứng dụng có thể phục vụ. Ghi lại thời gian truyền, giải mã, giải nén, prepare, restore, phát lại binary log và kiểm tra sau phục hồi. Nếu RTO không đạt, hãy điều chỉnh kích thước bản sao, hạ tầng khôi phục, mức nén, băng thông hoặc quy trình.

### 6.3. Các thành phần thường bị bỏ sót

Khi lập danh mục backup, hãy kiểm tra cả:

- Dữ liệu và cấu trúc schema.
- Trigger, stored procedure, function và event.
- Tài khoản, role, grant và cấu hình xác thực cần thiết.
- Cấu hình MySQL như tham số replication, binary logging và các biến vận hành quan trọng.
- Binary log cùng metadata GTID hoặc tọa độ tương ứng.
- Vật liệu khóa/keyring nếu dữ liệu hoặc bản backup phụ thuộc vào mã hóa.
- Chứng thư, cấu hình TLS và thông tin cần để kết nối an toàn.
- Tài liệu triển khai, thứ tự khởi động và runbook phục hồi.

Không đưa bí mật vào một gói backup thông thường mà không phân loại và mã hóa. Với keyring, khóa và thông tin xác thực, cần quy trình sao lưu riêng, quyền riêng và thử nghiệm phục hồi tương ứng.

## 7. Quy trình mẫu từ tạo bản sao đến lưu trữ

Một quy trình có thể chuẩn hóa thành các giai đoạn:

| Giai đoạn | Việc cần làm | Bằng chứng cần lưu |
|---|---|---|
| Chuẩn bị | Xác nhận lịch, phạm vi, dung lượng, trạng thái MySQL và quyền của tài khoản backup | Job ID, thời điểm, máy chủ, loại backup |
| Tạo bản sao | Chạy logical hoặc physical backup theo phương pháp đã chọn | Log, mã thoát, metadata snapshot |
| Nén | Dùng thuật toán và mức nén đã kiểm chứng | Kích thước trước/sau, thời gian, CPU |
| Mã hóa | Mã hóa tệp và tham chiếu phiên bản khóa | Thuật toán, key ID, kết quả mã hóa |
| Kiểm tra | Kiểm tra cấu trúc, checksum và khả năng giải mã | Checksum, kết quả kiểm tra, cảnh báo |
| Sao chép ngoài máy chủ | Truyền đến vùng lưu trữ độc lập | Đường dẫn/ID đối tượng, checksum phía đích |
| Áp retention | Gắn nhãn ngày hết hạn, khóa bất biến và chính sách xóa | Retention class, ngày hết hạn |
| Diễn tập | Phục hồi định kỳ và xác minh nghiệp vụ | RTO thực tế, điểm khôi phục, lỗi phát hiện |

Mỗi bản sao nên có metadata đủ để người trực vận hành biết: nguồn MySQL, phiên bản, thời điểm bắt đầu/kết thúc, loại backup, phạm vi database, GTID hoặc tọa độ binlog, phương pháp nén, thuật toán mã hóa, key ID, checksum, vị trí bản sao từ xa và ngày hết hạn. Không ghi mật khẩu hay khóa bí mật vào metadata.

## 8. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Tệp sau nén lớn hơn dự kiến | Dữ liệu vốn đã nén hoặc mức nén thấp | Đo tỷ lệ nén theo loại dữ liệu; không tăng mức nén nếu CPU hoặc RTO bị ảnh hưởng |
| Backup chạy lâu, tải CPU tăng | Mức nén quá mạnh hoặc nén cạnh tranh tài nguyên với MySQL | Điều chỉnh mức nén, giới hạn tài nguyên hoặc chạy trong cửa sổ phù hợp |
| Tệp mã hóa không giải mã được | Sai cụm mật khẩu, thiếu khóa, sai phiên bản key hoặc keyring không truy xuất được | Tra cứu key ID và quy trình khôi phục khóa; thử trên bản sao cô lập |
| Checksum nguồn và đích khác nhau | Truyền thiếu, tệp bị thay đổi hoặc manifest không tương ứng | Truyền lại từ nguồn đã xác minh, kiểm tra log và tạo manifest mới qua kênh tin cậy |
| Bản sao từ xa bị xóa cùng bản chính | Cùng tài khoản/quyền quản trị hoặc không có immutability | Tách tài khoản và miền quản trị; bật versioning/retention lock phù hợp |
| Không thể PITR đến thời điểm cần | Thiếu binary log, log không liên tục hoặc thiếu metadata vị trí | Kiểm tra chuỗi log, GTID/tọa độ và thời gian lưu; sửa quy trình chuyển log |
| Restore vượt quá RTO | Bản sao quá lớn, truyền chậm, thiếu tài nguyên hoặc thao tác thủ công | Đo từng giai đoạn, tối ưu đường truyền, công cụ backup và hạ tầng phục hồi |
| Dữ liệu đã restore thiếu đối tượng hoặc quyền | Phạm vi dump không gồm routine/event/user/grant hoặc metadata cấu hình | Bổ sung danh mục đối tượng và kiểm tra bằng checklist sau restore |

Khi backup thất bại, đừng đánh dấu job thành công chỉ vì tệp đích tồn tại. Kiểm tra mã thoát của toàn bộ pipeline, log, kích thước, checksum và trạng thái sao chép. Nếu bản sao bị nghi ngờ, giữ lại để điều tra theo chính sách, tạo bản mới và kiểm tra phục hồi trước khi dùng nó làm mốc duy nhất.

## 9. Tự kiểm tra

**Tình huống 1:** Một bản dump SQL được nén bằng gzip rồi mã hóa. Vì sao nên nén trước khi mã hóa?

**Gợi ý:** Dữ liệu mã hóa có tính ngẫu nhiên cao nên khó nén. Nén trước thường giảm dung lượng và thời gian truyền tốt hơn.

**Tình huống 2:** Công ty lưu backup mã hóa trong 12 tháng nhưng chỉ giữ khóa giải mã trong 3 tháng. Rủi ro là gì?

**Gợi ý:** Các bản sao lưu cũ có thể còn nguyên nhưng không thể giải mã. Vật liệu khóa và khả năng truy xuất khóa phải được duy trì ít nhất trong toàn bộ vòng đời của bản sao liên quan.

**Tình huống 3:** Máy chủ MySQL có bản backup đầy đủ hàng ngày, nhưng binary log chỉ được giữ hai ngày. Một lỗi dữ liệu được phát hiện sau một tuần. Có thể còn khả năng PITR đến trước thời điểm lỗi không?

**Gợi ý:** Chỉ khi còn một bản backup phù hợp và chuỗi binary log liên tục từ mốc backup đến thời điểm mục tiêu. Nếu log cần thiết đã bị xóa, không thể phát lại để đến mốc đó.

**Tình huống 4:** Bản backup được đồng bộ sang một thư mục khác trên cùng máy chủ và cùng tài khoản quản trị. Bản sao này bảo vệ được những sự cố nào và còn thiếu gì?

**Gợi ý:** Nó có thể giúp phục hồi một số trường hợp xóa nhầm tệp cục bộ, nhưng không tạo miền lỗi độc lập trước hỏng máy, ransomware hoặc tài khoản quản trị bị chiếm quyền. Cần bản sao ở máy chủ/tài khoản/vùng độc lập và có bản immutable hoặc offline.

**Tình huống 5:** Checksum của bản backup trên máy chủ nguồn và object storage khớp nhau. Điều này đã chứng minh có thể khôi phục cơ sở dữ liệu chưa?

**Gợi ý:** Chưa. Checksum chỉ kiểm tra tính toàn vẹn của tệp theo manifest. Cần giải mã, giải nén và restore thử, sau đó kiểm tra dữ liệu và thời gian phục hồi.

## 10. Điểm cần ghi nhớ

- Nén giúp giảm dung lượng và băng thông nhưng tiêu tốn CPU; phải đo cả thời gian backup lẫn restore.
- Nên nén trước khi mã hóa vì dữ liệu đã mã hóa khó nén thêm.
- TLS, mã hóa ổ đĩa, mã hóa tablespace và mã hóa tệp backup bảo vệ các lớp khác nhau.
- Khóa giải mã phải được quản lý độc lập và tồn tại trong toàn bộ thời gian lưu của bản sao liên quan.
- Retention phải bao gồm quan hệ phụ thuộc giữa full, incremental và binary log; PITR cần chuỗi log liên tục cùng metadata vị trí.
- Bản sao ngoài máy chủ cần miền lỗi và quyền quản trị độc lập; immutable/offline giúp chống xóa hoặc sửa trái phép.
- Checksum, giải mã và giải nén là các bước kiểm tra cần thiết; restore thử mới chứng minh được khả năng phục hồi.
- Diễn tập định kỳ, đo RPO/RTO thực tế và cập nhật runbook khi hạ tầng hoặc phiên bản MySQL thay đổi.
