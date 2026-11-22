# Phân bố lỗi, sao lưu ngoài cụm và kế hoạch khôi phục thảm họa

Một hệ thống PostgreSQL có thể hoạt động ổn định trong nhiều tháng nhưng vẫn mất dữ liệu hoặc ngừng phục vụ khi một vùng hạ tầng gặp sự cố, tài khoản quản trị bị chiếm quyền, thao tác xóa nhầm lan sang bản sao, hoặc bản sao lưu không thể phục hồi. Thiết kế triển khai bền vững vì thế phải xử lý đồng thời ba vấn đề: đặt các thành phần vào những miền lỗi độc lập, giữ bản sao dữ liệu ở ngoài cụm đang vận hành và có quy trình khôi phục đã được diễn tập.

Sao lưu, sao chép dữ liệu và tính sẵn sàng cao có vai trò khác nhau. Standby giúp tiếp tục phục vụ khi primary hỏng. Backup cho phép dựng lại dữ liệu tại một thời điểm trước khi lỗi hoặc thao tác phá hoại xảy ra. Kế hoạch khôi phục thảm họa (Disaster Recovery, DR) kết hợp hạ tầng, dữ liệu, con người, quyền truy cập và các quyết định vận hành để đưa dịch vụ về trạng thái có thể phục vụ người dùng trong giới hạn RTO và RPO đã cam kết.

Bài học này tập trung vào PostgreSQL trong môi trường triển khai thực tế: phân tích miền lỗi, chọn kiến trúc dự phòng, thiết kế physical backup và logical backup, lưu trữ WAL ngoài cụm, phục hồi theo thời điểm (PITR), chuyển đổi primary, bảo vệ bản sao và tổ chức diễn tập khôi phục.

## 1. Xác định miền lỗi trước khi chọn kiến trúc

Miền lỗi (failure domain) là phạm vi mà một sự cố có thể làm hỏng đồng thời nhiều thành phần. Hai máy chủ khác tên hoặc hai volume khác nhau chưa chắc thuộc hai miền lỗi độc lập. Nếu chúng dùng chung một rack, một vùng sẵn sàng, một tài khoản cloud, một hệ thống quản trị danh tính hoặc một đường truyền, một sự cố ở lớp dùng chung vẫn có thể làm cả hai mất khả năng hoạt động.

Khi thiết kế PostgreSQL, cần xem xét ít nhất các miền sau:

| Miền lỗi | Ví dụ sự cố | Tác động có thể xảy ra |
|---|---|---|
| Tiến trình hoặc instance | PostgreSQL crash, hết bộ nhớ, lỗi cấu hình | Một instance dừng phục vụ |
| Máy chủ hoặc host | Hỏng nguồn, RAM, ổ đĩa, kernel panic | Primary hoặc standby trên host đó mất |
| Rack hoặc cụm lưu trữ | Lỗi switch, controller, nguồn điện hoặc SAN | Nhiều host cùng mất kết nối |
| Availability Zone (AZ) | Mất điện, mạng hoặc dịch vụ hạ tầng trong một AZ | Nhiều node trong AZ cùng bị ảnh hưởng |
| Region | Sự cố diện rộng của cloud provider, thiên tai hoặc lỗi mạng liên vùng | Cụm chính và các standby cùng region có thể không truy cập được |
| Tài khoản hoặc control plane | Tài khoản cloud bị chiếm, quyền quản trị bị lạm dụng, lỗi automation | Kẻ tấn công hoặc thao tác sai có thể xóa cả database và bản sao |
| Danh tính và bí mật | Mất KMS key, secret, chứng thư hoặc tài khoản backup | Có backup nhưng không thể giải mã hoặc truy cập |
| Phần mềm và dữ liệu logic | Bug ứng dụng, migration lỗi, câu lệnh DELETE nhầm | Lỗi được sao chép sang standby |
| Con người và quy trình | Xóa nhầm, chạy nhầm lệnh, thay đổi retention | Dữ liệu hoặc bản sao bị phá hủy ngoài dự kiến |

Hãy lập sơ đồ phụ thuộc cho từng thành phần: primary, standby, proxy, connection pool, DNS, object storage, hệ thống quản lý khóa, secret manager, monitoring, CI/CD và tài khoản vận hành. Sơ đồ cần thể hiện thành phần nào dùng chung hạ tầng, tài khoản hoặc quyền quản trị. Đây là cách phát hiện những điểm lỗi chung bị che khuất bởi sơ đồ chỉ có hai máy chủ database.

### Ví dụ về hai cấu hình trông có vẻ dự phòng

- Primary ở host A và standby ở host B nhưng cả hai cùng một AZ: chống được một số lỗi host, không chống được mất AZ.
- Primary ở region A và backup ở một bucket trong cùng tài khoản quản trị: chống được lỗi máy chủ hoặc lỗi region, nhưng tài khoản bị chiếm quyền có thể xóa cả bucket.
- Primary và standby ở hai AZ, backup ở object storage region khác, tài khoản backup riêng và retention bất biến: giảm được nhiều rủi ro độc lập hơn.
- Hai bản sao lưu ở hai thư mục trên cùng volume: không tạo ra hai bản sao độc lập. Volume hỏng hoặc bị mã hóa vẫn làm mất cả hai.

Mục tiêu không phải là loại bỏ mọi rủi ro. Mục tiêu là xác định rõ sự cố nào được kiến trúc xử lý tự động, sự cố nào cần khôi phục từ backup và sự cố nào đòi hỏi quyết định thủ công.

## 2. Phân biệt HA, replication, backup và DR

Các khái niệm này thường bị dùng thay thế cho nhau, dẫn đến kế hoạch phục hồi thiếu một lớp bảo vệ quan trọng.

| Cơ chế | Mục tiêu chính | Có thể giúp khi | Không tự giải quyết được |
|---|---|---|---|
| High Availability (HA) | Giảm thời gian gián đoạn khi một thành phần hỏng | Primary hoặc host bị lỗi | Xóa nhầm, dữ liệu hỏng đã lan sang standby, mất toàn bộ region |
| Physical streaming replication | Duy trì standby gần với primary bằng WAL | Primary hỏng, cần promote standby | Khôi phục trạng thái trước một thao tác DELETE đã commit |
| Logical replication | Đồng bộ một tập bảng hoặc thay đổi logic | Di chuyển, tích hợp, một số mô hình đọc/ghi riêng | Thay thế backup nhất quán của toàn cluster |
| Base backup | Tạo điểm nền để dựng lại cluster | Mất dữ liệu hoặc cần dựng cluster mới | Khôi phục đến mọi thời điểm nếu không có WAL cần thiết |
| WAL archiving | Lưu chuỗi thay đổi sau base backup | PITR và phục hồi sau base backup | Tự phục hồi nếu thiếu base backup tương thích hoặc có khoảng trống WAL |
| Logical dump | Lưu cấu trúc và dữ liệu ở mức SQL | Khôi phục database hoặc đối tượng chọn lọc, di chuyển phiên bản | Phục hồi nhanh toàn cluster ở quy mô lớn hoặc PITR liên tục |
| Disaster Recovery plan | Điều phối toàn bộ quy trình khôi phục | Sự cố diện rộng, mất region, mất quyền hoặc cần chuyển site | Không thay thế backup và không tự tạo dữ liệu có thể phục hồi |

Streaming replication truyền WAL từ primary sang standby. Khi primary commit một thao tác xóa nhầm, WAL tương ứng cũng được phát lại trên standby. Standby vì thế thường phản ánh dữ liệu mới nhất, bao gồm cả lỗi logic đã được commit.

Backup giữ lại các trạng thái lịch sử độc lập với trạng thái hiện tại của primary. Nếu thao tác sai được phát hiện muộn, có thể phục hồi backup đến trước thời điểm lỗi, hoặc dựng một cluster tạm để trích xuất phần dữ liệu cần cứu.

HA và backup bổ trợ cho nhau. HA xử lý gián đoạn vận hành; backup và PITR xử lý nhu cầu quay về một trạng thái dữ liệu trước đó. DR là kế hoạch kết hợp các cơ chế này cùng hạ tầng và quy trình.

## 3. Xác định RPO và RTO

Hai chỉ số nền tảng của DR là Recovery Point Objective (RPO) và Recovery Time Objective (RTO).

- **RPO** là lượng dữ liệu tối đa mà tổ chức chấp nhận mất, tính theo khoảng thời gian giữa lúc sự cố xảy ra và thời điểm dữ liệu mới nhất có thể phục hồi.
- **RTO** là thời gian tối đa mà tổ chức chấp nhận để khôi phục dịch vụ về mức hoạt động đã định.

Ví dụ, một hệ thống có RPO 5 phút và RTO 1 giờ cần bảo đảm rằng điểm phục hồi dữ liệu không cũ hơn giới hạn 5 phút và dịch vụ có thể hoạt động trở lại trong vòng 1 giờ sau khi tuyên bố sự cố. Đây là mục tiêu thiết kế và kiểm thử, không phải kết quả được bảo đảm chỉ bằng việc bật một tùy chọn PostgreSQL.

RPO và RTO cần được xác định theo từng loại nghiệp vụ. Hệ thống thanh toán có thể yêu cầu RPO rất thấp, trong khi kho phân tích có thể chấp nhận phục hồi dữ liệu cũ hơn. Không nên áp một con số chung cho mọi database nếu giá trị nghiệp vụ và chi phí bảo vệ khác nhau.

### RPO phụ thuộc vào đường dữ liệu có thể phục hồi

Với kiến trúc backup và WAL archiving, thời điểm phục hồi mới nhất phụ thuộc vào base backup hợp lệ và chuỗi WAL liên tục được lưu ngoài cụm. Nếu WAL mới nhất chưa được archive thành công hoặc một segment bị thiếu, điểm phục hồi thực tế có thể cũ hơn thời điểm hiện tại.

Với standby bất đồng bộ, RPO phụ thuộc vào WAL đã được gửi, ghi bền vững và phát lại ở standby tại thời điểm primary gặp sự cố. Một standby có độ trễ thấp thường giảm mất dữ liệu nhưng không mặc nhiên bảo đảm RPO bằng 0.

Với synchronous replication, mức bảo đảm phụ thuộc cấu hình đồng bộ, số standby được yêu cầu và chính sách commit. PostgreSQL có các mức chờ khác nhau thông qua synchronous_commit: remote_write chờ standby ghi WAL tới hệ điều hành, on chờ WAL được flush bền vững ở standby, còn remote_apply chờ standby replay WAL. Các mức này có bảo đảm và chi phí độ trễ khác nhau; remote_write không tương đương với flush bền vững qua sự cố hệ điều hành. Cần đọc đúng cấu hình đang chạy và kiểm thử hành vi khi standby mất kết nối. Synchronous replication có thể tăng độ trễ ghi hoặc làm giao dịch phải chờ khi không còn standby đáp ứng điều kiện đồng bộ.

### RTO phải tính toàn bộ đường khôi phục

Không chỉ tính thời gian chạy lệnh restore. RTO thực tế gồm:

1. Phát hiện và xác nhận sự cố.
2. Quyết định failover hoặc khôi phục từ backup.
3. Cấp phát máy chủ, mạng, volume và quyền truy cập.
4. Lấy backup, giải mã và giải nén.
5. Phục hồi WAL đến mục tiêu.
6. Khởi động PostgreSQL, kiểm tra tính nhất quán và extension.
7. Kiểm tra nghiệp vụ, kết nối ứng dụng và quyền.
8. Chuyển DNS, proxy hoặc endpoint.
9. Theo dõi tải, độ trễ và lỗi sau khi mở lại dịch vụ.

Nếu chỉ đo thời gian restore một database trên máy thử nghiệm đã chuẩn bị sẵn, con số đó không đại diện cho RTO toàn hệ thống. Hãy ghi lại từng giai đoạn trong diễn tập và đo cả thời gian chờ phê duyệt, cung cấp tài nguyên, lấy khóa giải mã và chuyển traffic.

## 4. Chọn kiến trúc dự phòng theo miền lỗi

Không có một cấu hình duy nhất phù hợp với mọi hệ thống. Kiến trúc cần cân bằng RPO, RTO, chi phí, độ phức tạp và khả năng vận hành.

### Dự phòng trong cùng AZ

Một standby trên host khác có thể bảo vệ trước lỗi phần cứng hoặc tiến trình. Cấu hình này có độ trễ mạng thấp và dễ đồng bộ hơn. Tuy nhiên, nó không bảo vệ trước sự cố làm mất cả AZ, mạng nội bộ hoặc dịch vụ lưu trữ dùng chung.

### Dự phòng giữa các AZ

Primary và standby nằm ở các AZ độc lập trong cùng region. Khi một AZ gặp sự cố, standby ở AZ còn lại có thể được promote nếu đáp ứng điều kiện nhất quán và quyền truy cập. Cần kiểm tra rằng các AZ thực sự độc lập về điện, mạng và hạ tầng lưu trữ theo cam kết của nhà cung cấp.

### Dự phòng liên region

Một standby hoặc hệ thống phục hồi ở region khác giúp giảm rủi ro mất region. Độ trễ liên vùng có thể khiến replication bất đồng bộ và có nguy cơ mất phần WAL chưa được nhận khi primary bị mất đột ngột. Cần đo replication lag, định nghĩa quy tắc promote và chấp nhận rõ mức RPO.

### Backup ngoài region và ngoài tài khoản

Backup được đẩy sang object storage hoặc hệ thống backup ở region khác. Tài khoản lưu trữ nên có quyền và thông tin xác thực độc lập với tài khoản quản trị database. Việc xóa cluster hoặc xâm phạm quyền của ứng dụng không được mặc nhiên cho phép xóa mọi bản backup.

### Mô hình cold, warm và hot standby

| Mô hình | Trạng thái site dự phòng | Ưu điểm | Chi phí và giới hạn |
|---|---|---|---|
| Cold site | Chưa có hoặc chỉ có hạ tầng tối thiểu | Chi phí thấp | Cần nhiều thời gian cấp phát và restore; RTO thường dài |
| Warm site | Có hạ tầng và một phần dữ liệu được đồng bộ hoặc backup sẵn | Cân bằng chi phí và thời gian phục hồi | Cần duy trì cấu hình, kiểm tra đồng bộ và dung lượng |
| Hot standby | Có standby đang chạy và liên tục nhận WAL | RTO thấp, chuyển đổi nhanh hơn | Chi phí cao; vẫn cần backup độc lập và bảo vệ trước lỗi logic |

Một thiết kế thực tế thường kết hợp hot hoặc warm standby để xử lý lỗi hạ tầng và backup ngoài region để xử lý sự cố diện rộng, xóa nhầm hoặc dữ liệu hỏng.

## 5. Thiết kế chiến lược backup PostgreSQL

Một chiến lược backup nên có nhiều lớp bảo vệ, mỗi lớp phục vụ một mục đích khác nhau.

### Physical base backup

Physical backup lưu cấu trúc vật lý của PostgreSQL cluster, bao gồm các file dữ liệu cần thiết để dựng lại một cluster tương thích. Đây là nền tảng thường dùng cho phục hồi toàn cluster và PITR.

Có thể tạo base backup bằng pg_basebackup hoặc công cụ chuyên dụng như pgBackRest, Barman hay WAL-G. Các công cụ chuyên dụng thường hỗ trợ lập lịch, retention, nén, mã hóa, lưu trữ object storage, WAL archiving, kiểm tra và quản lý nhiều bản backup. Hãy chọn một công cụ và vận hành theo cấu hình đã được kiểm thử; không tự giả định mọi công cụ có cùng cách đặt tên, format hoặc lệnh restore.

Ví dụ tạo physical backup dạng thư mục bằng pg_basebackup:

    pg_basebackup \
      -h pg-primary.internal \
      -U backup_repl \
      -D /backup/staging/base-2026-11-14 \
      -Fp \
      -Xs \
      -P

Ý nghĩa các tham số chính:

- -h chỉ định máy chủ nguồn.
- -U chỉ định role dùng để tạo backup; role cần quyền phù hợp cho replication/backup.
- -D chỉ định thư mục đích.
- -Fp yêu cầu định dạng plain directory.
- -Xs stream WAL cần thiết trong quá trình backup.
- -P hiển thị tiến độ.

Đây là ví dụ cho môi trường thử nghiệm hoặc vùng staging. Thư mục đích phải có đủ dung lượng, quyền truy cập phù hợp và cần được chuyển an toàn sang kho lưu trữ ngoài cụm. Không để bản duy nhất ở một thư mục trên cùng host hoặc volume với database. Hãy dùng secret manager hoặc cơ chế xác thực an toàn của hệ thống thay vì ghi mật khẩu trực tiếp vào lệnh hoặc log.

Physical backup có ràng buộc tương thích với phiên bản PostgreSQL, kiến trúc và cấu trúc cluster. Khi nâng cấp major version, cần có kế hoạch backup và restore phù hợp với phiên bản đích; không coi physical backup của một major version là file dữ liệu có thể mở tùy ý bằng major version khác.

### Logical backup

Logical backup lưu dữ liệu dưới dạng lệnh SQL hoặc định dạng dump logic. pg_dump thường dùng để backup một database; pg_dumpall có thể xuất các đối tượng toàn cluster như role và tablespace.

Ví dụ:

    pg_dump -h pg-primary.internal -U backup_user \
      -Fc -d appdb -f /backup/staging/appdb.dump

    pg_dumpall -h pg-primary.internal -U backup_user \
      --globals-only -f /backup/staging/globals.sql

Có thể xem danh sách nội dung của custom-format dump bằng:

    pg_restore --list /backup/staging/appdb.dump

Logical backup hữu ích khi cần phục hồi chọn lọc một database, schema hoặc bảng, di chuyển dữ liệu giữa phiên bản, hoặc tạo một bản xuất độc lập với bố cục file vật lý. Nó không tự cung cấp PITR liên tục. Muốn phục hồi đến một thời điểm bất kỳ cần kết hợp physical base backup và WAL archive, hoặc có chiến lược ghi nhận thay đổi ở tầng ứng dụng phù hợp.

Khi backup logical, hãy lưu cả thông tin global object cần thiết như role và tablespace. Nếu chỉ có dump của database nhưng thiếu role, ownership hoặc quyền, quá trình restore có thể không tái tạo được hành vi ứng dụng. Cần bảo vệ file globals vì chúng có thể chứa thông tin xác thực đã băm và cấu hình nhạy cảm.

### Snapshot ở tầng lưu trữ

Snapshot volume có thể hữu ích khi nhà cung cấp hỗ trợ snapshot nhất quán và quy trình backup hiểu PostgreSQL. Một snapshot tùy tiện của nhiều volume tại các thời điểm khác nhau có thể tạo ra bản sao không nhất quán, đặc biệt nếu PGDATA, WAL hoặc tablespace nằm trên các volume khác nhau.

Chỉ sử dụng snapshot khi đã xác minh cách hệ thống phối hợp trạng thái database, WAL và các volume. Không coi việc tạo snapshot thành công ở tầng cloud là bằng chứng database có thể khởi động từ snapshot đó. Hãy restore thử trên một máy độc lập.

### Phối hợp nhiều lớp

Một chiến lược thường dùng gồm:

- Physical base backup định kỳ để tạo điểm nền cho toàn cluster.
- WAL archiving liên tục để hỗ trợ PITR giữa các base backup.
- Logical dump định kỳ cho database hoặc dữ liệu cần phục hồi chọn lọc.
- Backup riêng cấu hình, hạ tầng dưới dạng mã, chứng thư và hướng dẫn vận hành.
- Bản sao ngoài region, có retention và quyền xóa độc lập.
- Restore drill để kiểm chứng tất cả các lớp có thể dùng được.

Quy tắc 3-2-1 là một cách ghi nhớ: giữ ít nhất ba bản sao dữ liệu, trên hai loại phương tiện hoặc miền lưu trữ độc lập, trong đó ít nhất một bản ở ngoài site chính. Với hệ thống cloud, cần diễn giải nguyên tắc này theo miền lỗi thực tế: khác region, khác tài khoản hoặc boundary quyền, có bản bất biến và có quy trình phục hồi đã thử nghiệm.

## 6. Lưu WAL ngoài cụm để hỗ trợ PITR

PostgreSQL ghi các thay đổi vào Write-Ahead Log (WAL). WAL là chuỗi record cho phép phục hồi tính nhất quán sau crash và phát lại thay đổi trên standby. Khi bật WAL archiving, PostgreSQL hoặc công cụ backup có thể chuyển các WAL segment đã hoàn tất sang kho lưu trữ độc lập.

PITR (Point-in-Time Recovery) kết hợp một base backup với chuỗi WAL liên tục sau thời điểm backup. Khi restore, PostgreSQL phục hồi base backup rồi phát lại WAL đến thời điểm, transaction hoặc restore point được chọn.

### Cấu hình WAL archiving

Các tham số cơ bản thường được cấu hình trong postgresql.conf:

    archive_mode = on
    archive_command = 'test ! -f /var/lib/pg-archive/%f && cp %p /var/lib/pg-archive/%f'
    archive_timeout = '60s'

Ví dụ trên chỉ sao chép vào thư mục archive cục bộ để minh họa cách archive_command nhận tên file và đường dẫn nguồn. Trong môi trường production, thư mục này cần là staging được quản lý và dữ liệu phải được chuyển đến kho ngoài cụm bằng công cụ backup phù hợp. Không dùng một thư mục cùng volume với PGDATA làm bản backup duy nhất.

Trong archive_command:

- %p là đường dẫn file WAL nguồn.
- %f là tên file WAL cần lưu.
- Lệnh trả mã 0 khi lưu thành công.
- Lệnh trả mã khác 0 khi lưu thất bại để PostgreSQL có thể thử lại.

Không được trả thành công khi file chưa thực sự được lưu bền vững ở đích mà chính sách backup yêu cầu. Nếu lệnh archive báo thành công trước khi object storage xác nhận dữ liệu đã được ghi, monitoring có thể cho thấy archive hoàn tất trong khi bản sao ngoài cụm chưa tồn tại.

archive_timeout có thể buộc chuyển WAL segment sau một khoảng thời gian để giảm độ trễ archive khi tải ghi thấp. Nó không thay thế giám sát archive và không bảo đảm RPO nếu đường truyền hoặc kho lưu trữ bị lỗi.

Với object storage hoặc hệ thống backup chuyên dụng, hãy dùng công cụ hỗ trợ retry, checksum, mã hóa, upload multipart, quản lý retention và cảnh báo. Không tự ghép một archive_command đơn giản với lệnh upload thiếu cơ chế xử lý lỗi hoặc tính nguyên tử.

### Theo dõi WAL archiving

Có thể xem trạng thái archive từ PostgreSQL:

    SELECT
        archived_count,
        last_archived_wal,
        last_archived_time,
        failed_count,
        last_failed_wal,
        last_failed_time,
        stats_reset
    FROM pg_stat_archiver;

Cần theo dõi cả thời điểm archive gần nhất, số lần thất bại, thời gian archive bị trễ và dung lượng WAL đang chờ. Chỉ số archived_count tăng không đủ để chứng minh bản sao ở region dự phòng có thể truy cập và giải mã. Phải đối chiếu trạng thái của công cụ backup hoặc object storage.

Nếu archive_command thất bại kéo dài, PostgreSQL có thể giữ lại WAL cần archive trong pg_wal. Dung lượng đĩa có thể tăng đến mức ảnh hưởng hoạt động database. Cảnh báo cần phát hiện sớm trước khi filesystem đầy.

Replication slot cũng có thể giữ WAL chưa được consumer xác nhận. Slot bị bỏ quên hoặc standby ngừng hoạt động có thể làm WAL tích tụ. Theo dõi pg_replication_slots, dung lượng pg_wal và trạng thái consumer; không xóa slot tùy tiện vì có thể làm standby không còn đủ WAL để tiếp tục.

## 7. Thực hiện Point-in-Time Recovery

PITR cho phép khôi phục cluster về một điểm trước khi sự cố logic hoặc dữ liệu xảy ra. Đây là cơ chế quan trọng khi một migration sai, câu lệnh xóa nhầm hoặc bug ứng dụng đã commit thay đổi không mong muốn.

Quy trình tổng quát:

1. Chọn base backup hợp lệ có thời điểm trước mục tiêu phục hồi.
2. Xác minh chuỗi WAL từ base backup đến mục tiêu đầy đủ và có thể giải mã.
3. Cấp phát máy chủ và volume phục hồi độc lập.
4. Khôi phục base backup vào PGDATA đích.
5. Cấu hình truy xuất WAL archive bằng restore_command hoặc công cụ backup.
6. Thiết lập recovery target phù hợp.
7. Tạo recovery.signal trên PostgreSQL 12 trở lên.
8. Khởi động PostgreSQL và theo dõi quá trình replay.
9. Khi đạt target, kiểm tra dữ liệu và quyết định promote hoặc tiếp tục recovery theo kế hoạch.
10. Chỉ mở traffic sau khi hoàn tất kiểm tra kỹ thuật và nghiệp vụ.

Ví dụ cấu hình recovery target trên PostgreSQL 12 trở lên:

    restore_command = 'cp /var/lib/pg-archive/%f %p'
    recovery_target_time = '2026-11-14 10:25:00+07'
    recovery_target_action = 'pause'

Ví dụ này giả định WAL đã được tải về thư mục archive cục bộ. Với kho object storage, restore_command phải gọi công cụ phù hợp để lấy đúng file WAL. Hãy bảo đảm lệnh xử lý đúng file, trả lỗi khi không tìm thấy file và không ghi đè dữ liệu không hợp lệ.

Tạo file tín hiệu recovery trong PGDATA đã restore:

    touch /var/lib/postgresql/data/recovery.signal

Sau đó khởi động PostgreSQL. Trong các phiên bản PostgreSQL hiện đại, recovery settings được cấu hình trong postgresql.conf hoặc tệp cấu hình được include; PostgreSQL 12 trở lên dùng recovery.signal cho standby/PITR workflow. Các phiên bản cũ có cơ chế recovery.conf khác, vì vậy phải theo đúng tài liệu của major version đang vận hành.

recovery_target_time chỉ là một trong các cách chọn mục tiêu. PostgreSQL còn hỗ trợ mục tiêu theo transaction ID, LSN hoặc named restore point; các tùy chọn này hữu ích khi ứng dụng ghi nhận mốc nghiệp vụ hoặc khi cần khôi phục trước một thao tác cụ thể. Cần hiểu hành vi inclusive/exclusive và recovery_target_action của phiên bản đang dùng. Không ước lượng thời điểm theo đồng hồ ứng dụng nếu timestamp và timezone không được đồng bộ.

### Tìm đúng thời điểm cần phục hồi

Khi phát hiện lỗi logic, hãy xác định:

- Thời điểm thao tác sai được commit.
- Thời điểm lỗi bắt đầu lan ra các bảng hoặc dịch vụ liên quan.
- Những giao dịch hợp lệ đã xảy ra sau lỗi cần giữ lại.
- Các event đã được gửi sang hệ thống ngoài.
- Mốc backup và WAL archive khả dụng.

Không phải lúc nào phục hồi toàn cluster về trước lỗi cũng là lựa chọn tốt nhất. Nếu sau thời điểm đó có nhiều giao dịch hợp lệ, có thể dựng một cluster phục hồi tạm, trích xuất dữ liệu cần cứu rồi áp dụng vào cluster mới hoặc cluster hiện hành theo quy trình đối soát. Tránh ghi đè primary đang hoạt động khi chưa xác định rõ dữ liệu nào phải giữ.

### PITR tạo một nhánh lịch sử mới

Sau khi phục hồi đến một thời điểm cũ và promote cluster, lịch sử WAL có thể chuyển sang timeline mới. Không trộn WAL từ các timeline khác nhau theo suy đoán. Cần quản lý timeline history và chọn đúng nhánh lịch sử theo quy trình của PostgreSQL hoặc công cụ backup.

Khi dựng một cluster mới từ PITR, hãy cập nhật thông tin endpoint, monitoring và backup schedule. Cluster vừa phục hồi cần được đưa trở lại quy trình backup và WAL archiving đầy đủ; nếu không, một sự cố tiếp theo có thể làm mất khả năng phục hồi.

## 8. Bảo vệ kho backup ngoài cụm

Backup ngoài cụm chỉ có giá trị khi kẻ tấn công hoặc thao tác sai ở môi trường production không thể dễ dàng xóa, sửa hoặc làm mất khả năng giải mã bản sao.

### Tách tài khoản và quyền

- Dùng tài khoản, project hoặc subscription riêng cho kho backup nếu hạ tầng cho phép.
- Tách role ghi backup khỏi role đọc, restore và quản trị retention.
- Ứng dụng production chỉ có quyền ghi đúng prefix hoặc repository cần thiết; không có quyền xóa toàn bộ backup.
- Quyền thay đổi retention, object lock và KMS key phải được giới hạn cho nhóm quản trị độc lập.
- Dùng credential ngắn hạn hoặc workload identity khi có thể; xoay vòng secret và thu hồi credential cũ.
- Bảo vệ tài khoản khẩn cấp bằng MFA và quy trình phê duyệt.

### Bất biến và versioning

Object versioning, retention lock hoặc immutable storage có thể giúp giữ bản backup trước khi bị xóa hoặc ghi đè. Cần hiểu chế độ governance/compliance của nhà cung cấp, quyền bypass retention và thời điểm hết hạn. Nếu tài khoản production có quyền vô hiệu hóa chính sách bất biến, mức bảo vệ trước ransomware hoặc tài khoản bị chiếm vẫn còn hạn chế.

Thiết kế retention phải tính đến cả backup và WAL. Xóa WAL quá sớm có thể khiến base backup còn tồn tại nhưng không thể PITR đến mục tiêu mong muốn. Một bản base backup chỉ dùng được trong phạm vi WAL cần thiết cho recovery chain của nó.

### Mã hóa và quản lý khóa

Backup chứa dữ liệu nhạy cảm nên cần mã hóa khi truyền và khi lưu. Có thể dùng mã hóa của công cụ backup, object storage hoặc cả hai lớp. Khóa mã hóa phải được quản lý độc lập với dữ liệu được mã hóa.

Kế hoạch DR phải bao gồm cách lấy khóa, quyền giải mã và quy trình phục hồi khi KMS ở region chính không hoạt động. Nếu backup được mã hóa nhưng khóa chỉ tồn tại trong một region đã mất, dữ liệu không thể phục hồi. Lưu bản sao metadata và quy trình khôi phục khóa theo chính sách an toàn của tổ chức; không để khóa thô trong cùng bucket backup.

### Kiểm tra toàn vẹn

Dùng checksum hoặc manifest do công cụ backup cung cấp để phát hiện file thiếu hoặc bị thay đổi. Với backup được tạo bằng pg_basebackup và có manifest, pg_verifybackup có thể kiểm tra tính toàn vẹn của backup theo manifest:

    pg_verifybackup /backup/staging/base-2026-11-14

Kiểm tra manifest không chứng minh rằng mọi ứng dụng có thể khởi động hoặc mọi dữ liệu nghiệp vụ đúng. Chỉ restore thử trên môi trường độc lập mới chứng minh được toàn bộ chuỗi backup, WAL, quyền, cấu hình và extension có thể hoạt động.

### Retention và vòng đời dữ liệu

Retention cần được thiết kế theo RPO, quy định pháp lý và khả năng lưu trữ. Một ví dụ có thể gồm backup hằng ngày, backup tuần và backup tháng, nhưng lịch thực tế phụ thuộc dung lượng, tốc độ thay đổi WAL, yêu cầu kiểm toán và thời gian cần giữ lịch sử.

Trước khi xóa một base backup cũ, công cụ phải xác định các WAL và backup phụ thuộc có thể được dọn an toàn. Không tự xóa file WAL bằng thao tác filesystem nếu không hiểu dependency của backup catalog. Dọn sai có thể phá hỏng recovery chain.

## 9. Backup cấu hình và các phụ thuộc ngoài dữ liệu

Một PostgreSQL cluster có thể được phục hồi về mặt file dữ liệu nhưng ứng dụng vẫn không thể hoạt động nếu thiếu cấu hình và phụ thuộc môi trường.

Cần lưu và quản lý riêng:

- postgresql.conf, pg_hba.conf, pg_ident.conf và các tệp include.
- Tham số khởi động, systemd unit hoặc cấu hình container.
- Cấu hình extension, shared_preload_libraries và các gói hệ điều hành tương ứng.
- Role, grant, ownership, tablespace và thông tin kết nối.
- Chứng thư TLS, CA, cấu hình proxy và DNS.
- Secret ứng dụng, credential replication, credential backup và quyền truy cập KMS.
- Infrastructure as Code, manifest triển khai, firewall rule và route mạng.
- Script migration, version ứng dụng tương thích và tài liệu runbook.
- Cấu hình monitoring, alert và backup scheduler.

Không đưa secret thô vào Git hoặc kho backup chỉ để tiện khôi phục. Hãy lưu tham chiếu tới secret manager và bảo đảm có quy trình truy cập khẩn cấp độc lập. Tài liệu DR cần chỉ rõ ai có quyền cấp quyền và cách xác minh danh tính trong tình huống hệ thống đăng nhập chính không hoạt động.

Các extension cần được cài đúng phiên bản trên máy phục hồi trước khi khởi động hoặc trước khi sử dụng đối tượng phụ thuộc. Cũng cần xem xét collation provider, locale, encoding và phiên bản thư viện hệ điều hành. Khác biệt giữa môi trường nguồn và đích có thể ảnh hưởng index, so sánh chuỗi hoặc hành vi truy vấn.

## 10. Failover và tránh split-brain

Failover là quá trình chuyển vai trò primary sang standby hoặc site dự phòng khi primary hiện tại không thể tiếp tục phục vụ. Đây là thao tác có ảnh hưởng lớn đến tính nhất quán; không nên chỉ dựa vào việc một health check thất bại.

### Xác nhận primary cũ đã được fencing

Split-brain xảy ra khi hai node cùng được xem là primary và nhận ghi độc lập. Nếu primary cũ chỉ bị mất kết nối từ hệ thống giám sát nhưng vẫn có thể nhận ghi từ một số client, promote standby mà không cô lập node cũ có thể tạo hai nhánh dữ liệu không thể hợp nhất tự động.

Trước khi promote, hệ thống cần xác nhận primary cũ đã được fencing hoặc chắc chắn không còn nhận ghi. Fencing có thể dùng cơ chế tắt máy, thu hồi quyền truy cập lưu trữ, cô lập mạng hoặc cơ chế điều phối leader có quorum. Chỉ đổi DNS không phải fencing đầy đủ vì client có thể còn giữ connection cũ hoặc dùng endpoint khác.

### Quyết định promote

Trước khi promote standby, kiểm tra:

- Standby thuộc đúng cluster và timeline dự kiến.
- Standby đã nhận và replay WAL đến mức nào.
- Có WAL chưa được nhận ở primary cũ có thể cần để đạt RPO không.
- Cơ chế đồng bộ và trạng thái synchronous standby tại thời điểm sự cố.
- Có nguy cơ primary cũ tiếp tục nhận ghi không.
- Endpoint, quyền ghi, proxy và ứng dụng sẽ chuyển sang node nào.

Nếu standby bất đồng bộ, có thể mất các transaction đã commit ở primary nhưng chưa đến standby. Hãy ghi nhận rõ điểm mất dữ liệu dự kiến và quyết định theo chính sách nghiệp vụ. Không tuyên bố RPO bằng 0 chỉ vì standby có replication lag thấp tại lần quan sát cuối.

PostgreSQL có thể promote standby bằng cơ chế quản trị phù hợp, chẳng hạn pg_promote() hoặc công cụ điều phối của nhà cung cấp. Lệnh cụ thể phụ thuộc phiên bản và kiến trúc. Trong môi trường quản lý tự động, phải hiểu rõ ai là thành phần có quyền quyết định leader và cách tránh hai bộ điều phối cùng promote.

### Đưa primary cũ trở lại hệ thống

Sau failover, không khởi động primary cũ như một primary độc lập. Node đó có thể chứa các transaction thuộc timeline cũ. Cần giữ node ở trạng thái cô lập, xác định khả năng đồng bộ lại bằng pg_rewind nếu thỏa điều kiện, hoặc dựng lại từ backup/standby mới. Chỉ đưa node trở lại làm standby sau khi xác minh timeline, WAL và cấu hình replication.

Một quy trình failover tốt cũng phải có bước failback. Failback là việc chuyển vai trò về site ban đầu hoặc site ưu tiên sau khi sự cố đã được xử lý. Đây là một thay đổi topology mới, cần đồng bộ dữ liệu, fencing, kiểm tra ứng dụng và kế hoạch chuyển traffic riêng. Không tự động chuyển ngược ngay khi site cũ vừa online.

## 11. Quy trình khôi phục thảm họa đầu cuối

Runbook DR cần được viết sao cho một nhóm trực vận hành có thể thực hiện trong tình huống áp lực cao, kể cả khi người thiết kế ban đầu không có mặt.

### Giai đoạn A: Phát hiện và tuyên bố sự cố

1. Nhận cảnh báo từ database, hạ tầng, backup hoặc người dùng.
2. Xác định phạm vi: một instance, một AZ, một region, mất quyền truy cập hay lỗi dữ liệu logic.
3. Xác minh bằng nhiều nguồn độc lập; không promote chỉ vì một health check đơn lẻ thất bại.
4. Ghi thời điểm phát hiện, thời điểm bắt đầu ước tính, hệ thống ảnh hưởng và người chỉ huy sự cố.
5. Tuyên bố DR theo ngưỡng đã định; thông báo cho nhóm ứng dụng, bảo mật và nghiệp vụ.

### Giai đoạn B: Bảo vệ dữ liệu còn lại

1. Dừng các job hoặc thao tác có thể tiếp tục gây hỏng dữ liệu.
2. Nếu có dấu hiệu xâm nhập, cô lập credential bị lộ và bảo vệ kho backup.
3. Không xóa hoặc ghi đè primary cũ trước khi thu thập thông tin cần thiết.
4. Xác định backup và WAL archive còn truy cập được từ tài khoản độc lập.
5. Ghi nhận trạng thái replication, archive lag và điểm dữ liệu có thể phục hồi.

### Giai đoạn C: Chọn phương án phục hồi

Có thể chọn một trong các hướng:

- Promote standby khi primary hỏng và standby đủ điều kiện, primary cũ đã được fencing.
- PITR khi dữ liệu logic bị hỏng hoặc cần quay về trước một mốc.
- Restore base backup và WAL ở region khác khi site chính không còn khả dụng.
- Restore logical dump khi chỉ cần khôi phục một database hoặc tập đối tượng chọn lọc.
- Dựng cluster tạm để trích xuất dữ liệu hợp lệ nếu không thể quay lùi toàn bộ production.

Ghi rõ phương án được chọn, RPO dự kiến, RTO dự kiến và rủi ro mất giao dịch. Nếu chưa thể xác định điểm phục hồi, không che giấu độ không chắc chắn bằng một con số ước lượng.

### Giai đoạn D: Khôi phục hạ tầng và dữ liệu

1. Cấp phát máy chủ, mạng, volume và quyền cần thiết ở site đích.
2. Xác minh version PostgreSQL, extension, locale, tablespace và cấu hình.
3. Lấy backup bằng credential độc lập; kiểm tra manifest và giải mã.
4. Restore base backup hoặc logical dump theo runbook.
5. Phát lại WAL đến recovery target đã phê duyệt.
6. Kiểm tra log startup, recovery completion, timeline và trạng thái replication.
7. Cấu hình backup/WAL archiving cho cluster vừa phục hồi.

### Giai đoạn E: Xác minh trước khi mở traffic

Kiểm tra kỹ thuật:

- PostgreSQL đang ở trạng thái sẵn sàng và đúng vai trò.
- Không còn recovery ngoài dự kiến hoặc transaction bị treo.
- Database, schema, extension và role cần thiết tồn tại.
- Kết nối ứng dụng, TLS, DNS, proxy và connection pool hoạt động.
- Replica và archive mới đang được thiết lập.
- Monitoring và alert đang gửi dữ liệu về hệ thống quan sát.

Kiểm tra nghiệp vụ:

- Đối chiếu số lượng và trạng thái bản ghi quan trọng.
- Kiểm tra tổng tiền, sổ cái, đơn hàng, trạng thái thanh toán hoặc invariant đặc thù.
- Kiểm tra các giao dịch gần thời điểm sự cố.
- Đối chiếu event outbox/inbox và message đã gửi sang hệ thống ngoài.
- Xác định các giao dịch cần replay, bù trừ hoặc đối soát.

Không mở traffic chỉ dựa vào việc PostgreSQL đã nhận kết nối. Dữ liệu phải đạt các kiểm tra đã định trước.

### Giai đoạn F: Chuyển traffic và ổn định

1. Chuyển endpoint, DNS, proxy hoặc service discovery sang cluster đã phục hồi.
2. Kiểm tra ứng dụng ghi vào đúng primary.
3. Theo dõi lỗi, độ trễ, connection pool, lock, WAL và replication lag.
4. Mở tải theo từng giai đoạn nếu hệ thống có thể làm vậy.
5. Giữ nguyên backup và log sự cố để phục vụ điều tra.
6. Chỉ đóng sự cố khi owner nghiệp vụ xác nhận dịch vụ và dữ liệu đáp ứng điều kiện.

### Giai đoạn G: Khôi phục trạng thái dự phòng

Sau khi production ổn định:

- Dựng lại standby và xác nhận replication.
- Bật hoặc xác nhận WAL archiving tới kho ngoài cụm.
- Tạo base backup mới nếu recovery chain trước đó không còn phù hợp.
- Kiểm tra retention, quyền và mã hóa.
- Cập nhật sơ đồ topology, endpoint và runbook.
- Lập kế hoạch failback nếu cần.
- Tổ chức post-incident review và ghi lại bài học.

## 12. Kiểm tra tính toàn vẹn sau restore

Restore thành công ở mức file không đồng nghĩa dữ liệu nghiệp vụ đã chính xác. Cần có bộ kiểm tra ở nhiều tầng.

### Tầng PostgreSQL

- Xác minh database và schema cần thiết.
- Kiểm tra role, membership, ownership và grant.
- Kiểm tra extension và phiên bản.
- Kiểm tra constraint, index, sequence và partition.
- Kiểm tra tablespace, locale, encoding và collation.
- Kiểm tra replication, WAL archiving và backup scheduler sau khi phục hồi.

Một số truy vấn hỗ trợ quan sát:

    SELECT datname, pg_database_size(datname)
    FROM pg_database
    ORDER BY datname;

    SELECT extname, extversion
    FROM pg_extension
    ORDER BY extname;

    SELECT
        application_name,
        state,
        sync_state,
        write_lag,
        flush_lag,
        replay_lag
    FROM pg_stat_replication;

Các view có thể khác nhau theo major version và trạng thái node; chỉ truy vấn pg_stat_replication trên primary. Nếu chưa có standby, kết quả rỗng có thể là bình thường.

### Tầng dữ liệu và nghiệp vụ

Không chỉ đếm số dòng. Hãy xác định các invariant cần đúng, ví dụ:

- Tổng ghi nợ và ghi có của sổ cái cân bằng.
- Một idempotency key chỉ tạo một tác động nghiệp vụ.
- Đơn hàng đã thanh toán có giao dịch thanh toán tương ứng.
- Foreign key và quan hệ tenant không bị mất.
- Số lượng bản ghi theo ngày hoặc trạng thái nằm trong khoảng hợp lý.
- Các event cần phát lại đã được xác định và không tạo tác động trùng.

Có thể dùng truy vấn đối chiếu, checksum theo phạm vi, bảng tổng hợp hoặc báo cáo nghiệp vụ. Nếu restore về thời điểm trước một số giao dịch hợp lệ, cần có danh sách giao dịch bị ảnh hưởng và quy trình replay/bù trừ đã được nghiệp vụ chấp thuận.

## 13. Monitoring và cảnh báo cho backup/DR

Không nên chỉ cảnh báo khi backup job trả lỗi. Một backup job có thể trả thành công nhưng dữ liệu không đến được kho ngoài cụm, hoặc backup còn tồn tại nhưng WAL cần thiết đã bị dọn.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Thời điểm base backup thành công gần nhất | Tuổi của điểm nền gần nhất | Vượt lịch backup hoặc RPO nội bộ |
| Thời điểm WAL archive thành công gần nhất | Mức mới của WAL được lưu | Quá lâu không có WAL trong khi database có ghi |
| Archive failure count | Lỗi chuyển WAL | Tăng liên tục hoặc có file thất bại lâu |
| Archive lag | Độ trễ từ WAL tạo ra đến archive | Vượt ngưỡng RPO |
| Dung lượng pg_wal | WAL đang giữ trên primary | Tăng nhanh hoặc gần đầy filesystem |
| Replication lag | Độ trễ gửi/ghi/replay WAL | Vượt ngưỡng failover/RPO |
| Slot retained WAL | WAL bị giữ bởi replication slot | Tăng đến ngưỡng rủi ro đầy đĩa |
| Backup repository capacity | Dung lượng kho backup | Gần đầy hoặc retention không thể chạy |
| Backup checksum/manifest | Tính toàn vẹn file backup | Kiểm tra thất bại |
| Restore drill duration | Thời gian phục hồi đo được | Vượt RTO |
| Restore success rate | Tỷ lệ diễn tập restore thành công | Có lần thất bại hoặc chuỗi WAL thiếu |
| KMS/key availability | Khả năng giải mã backup | Key không truy cập được từ site DR |

Cần cảnh báo theo tuổi dữ liệu có thể phục hồi, không chỉ theo trạng thái job. Ví dụ, backup cuối cùng thành công cách đây 24 giờ có thể là bình thường nếu lịch là hằng ngày, nhưng không đạt RPO 15 phút. Một job báo success không thay thế được kiểm tra điểm phục hồi mới nhất.

PostgreSQL cung cấp pg_stat_archiver để theo dõi archive và các view replication để quan sát standby. Công cụ backup thường có catalog riêng về backup, WAL và retention. Hệ thống giám sát cần kết hợp cả số liệu PostgreSQL lẫn trạng thái kho lưu trữ.

## 14. Diễn tập restore và DR định kỳ

Một bản backup chưa từng được restore chỉ là giả định về khả năng phục hồi. Diễn tập là cách xác nhận rằng backup, WAL, khóa mã hóa, tài liệu, quyền và nhân sự đều hoạt động khi cần.

Nên có các loại diễn tập sau:

### Restore đơn lẻ

Lấy một base backup và restore vào máy chủ cô lập. Kiểm tra PostgreSQL khởi động, database mở được, extension tải được và các truy vấn cơ bản chạy thành công.

### PITR

Chọn một thời điểm cụ thể, phục hồi base backup và WAL đến target. Xác minh một thay đổi trước target có mặt và một thay đổi sau target không xuất hiện. Lặp lại với target gần thời điểm commit để kiểm tra độ chính xác.

### Khôi phục ngoài region

Dùng tài khoản và mạng của site DR để lấy backup từ kho ngoài region. Không dùng credential đang được lưu trên primary. Đo thời gian cấp phát, tải, giải mã, restore, replay WAL và xác minh.

### Failover standby

Mô phỏng mất primary, xác minh fencing, promote standby, chuyển endpoint và kiểm tra ghi. Sau đó dựng lại node cũ thành standby theo quy trình đã phê duyệt.

### Diễn tập mất quyền hoặc ransomware

Mô phỏng tình huống credential production bị thu hồi hoặc không còn đáng tin cậy. Xác minh kho backup vẫn truy cập được bằng tài khoản độc lập, retention không thể bị bypass bởi role ứng dụng và khóa giải mã còn khả dụng.

### Diễn tập tabletop

Nhóm vận hành, bảo mật, ứng dụng và nghiệp vụ cùng đi qua kịch bản trên giấy: ai tuyên bố DR, ai phê duyệt RPO, ai có quyền promote, ai liên lạc khách hàng, ai kiểm tra dữ liệu và ai quyết định mở traffic. Diễn tập này giúp phát hiện khoảng trống quyền và trách nhiệm mà kiểm thử kỹ thuật không thấy.

Mỗi lần diễn tập cần lưu:

- Ngày, phiên bản PostgreSQL và phiên bản công cụ backup.
- Backup ID, thời điểm base backup và WAL range.
- Recovery target và timeline.
- Thời gian từng giai đoạn.
- Kết quả kiểm tra kỹ thuật và nghiệp vụ.
- Sự cố gặp phải, nguyên nhân và hành động khắc phục.
- Người chịu trách nhiệm và thời hạn xử lý.

Tần suất diễn tập phải phù hợp với mức độ quan trọng của hệ thống. Hệ thống có yêu cầu RTO/RPO nghiêm ngặt cần kiểm tra thường xuyên hơn, đồng thời diễn tập sau thay đổi lớn về topology, công cụ backup, KMS hoặc quy trình xác thực.

## 15. Những sai lầm thường gặp

**Coi standby là backup.** Standby nhận WAL và có thể tái hiện thao tác xóa hoặc dữ liệu hỏng. Cần backup lịch sử độc lập và WAL archive để PITR.

**Lưu backup trên cùng miền lỗi với primary.** Một sự cố host, AZ, tài khoản hoặc ransomware có thể làm mất cả dữ liệu chính và bản sao. Phải xác định miền lỗi của kho lưu trữ và quyền quản trị.

**Chỉ backup database mà quên global objects.** Restore có thể thiếu role, tablespace hoặc quyền. Cần lưu globals và kiểm tra ownership sau phục hồi.

**Có base backup nhưng thiếu WAL.** Base backup có thể restore được nhưng không đến được recovery target mong muốn. Phải giám sát tính liên tục của WAL và dependency trong retention.

**Không kiểm tra khóa mã hóa.** Backup vẫn còn nhưng không giải mã được khi KMS hoặc credential chính mất. Cần diễn tập khôi phục quyền và khóa ở site DR.

**Promote standby khi primary cũ chưa được fencing.** Có thể tạo split-brain và hai nhánh ghi độc lập. Cần cơ chế cô lập primary cũ trước khi chuyển vai trò.

**Đặt RPO/RTO theo cảm tính.** Một con số không có phép đo restore hoặc replication không phải cam kết có căn cứ. Hãy đo trong diễn tập và tính đủ mọi giai đoạn.

**Chỉ kiểm tra backup job thành công.** Job thành công không chứng minh backup giải mã được, WAL đầy đủ hoặc cluster khởi động được. Cần checksum, restore drill và kiểm tra nghiệp vụ.

**Không lưu cấu hình và phụ thuộc.** Thiếu extension, TLS, secret, DNS hoặc IaC có thể kéo dài RTO dù dữ liệu đã restore xong.

**Không có kế hoạch failback.** Site cũ hoạt động lại không có nghĩa có thể chuyển traffic ngược ngay. Phải đồng bộ lại dữ liệu và xác định rõ primary duy nhất.

**Không bảo vệ backup khỏi quyền production.** Tài khoản ứng dụng hoặc tài khoản quản trị database bị chiếm có thể xóa cả bản sao. Cần tách quyền, tài khoản và retention bất biến.

## 16. Checklist thiết kế và vận hành

### Kiến trúc

- [ ] Đã lập danh sách miền lỗi: host, rack, AZ, region, tài khoản, KMS, network và con người.
- [ ] Primary và standby được bố trí theo mục tiêu HA.
- [ ] Backup nằm ngoài miền lỗi chính và có bản sao ngoài region khi cần.
- [ ] Có cơ chế fencing trước khi promote.
- [ ] Đã xác định quy trình failback.

### Backup và WAL

- [ ] Có lịch base backup và logical backup phù hợp.
- [ ] WAL archiving hoạt động liên tục và được giám sát.
- [ ] Recovery chain có đủ base backup và WAL.
- [ ] Backup có checksum/manifest và kiểm tra toàn vẹn.
- [ ] Retention bao phủ thời gian phát hiện lỗi và nhu cầu PITR.
- [ ] Backup cấu hình, globals, extension và phụ thuộc được quản lý.
- [ ] Kho backup có versioning hoặc immutable retention phù hợp.
- [ ] Credential và KMS key được tách khỏi tài khoản production.

### RPO/RTO

- [ ] RPO và RTO được xác định theo từng nghiệp vụ.
- [ ] RPO được đo từ điểm dữ liệu thực sự có thể phục hồi.
- [ ] RTO tính cả cấp phát, tải backup, giải mã, replay, kiểm tra và chuyển traffic.
- [ ] Có cảnh báo khi điểm backup/WAL vượt ngưỡng.
- [ ] Các mục tiêu được kiểm chứng bằng diễn tập.

### Khôi phục

- [ ] Có runbook failover và PITR.
- [ ] Có runbook phục hồi khi mất region hoặc tài khoản chính.
- [ ] Có quy trình xác minh dữ liệu và nghiệp vụ trước khi mở traffic.
- [ ] Có cách truy cập khẩn cấp vào secret và KMS.
- [ ] Có quy trình dựng lại standby và khôi phục backup sau sự cố.
- [ ] Có người chịu trách nhiệm cho từng bước và cơ chế phê duyệt.

## 17. Bài tập thực hành

1. Vẽ sơ đồ primary, standby, backup repository, KMS, DNS và monitoring. Đánh dấu miền lỗi dùng chung và đề xuất cách tách chúng.
2. Xây dựng bảng RPO/RTO cho ba workload: thanh toán, quản lý đơn hàng và kho phân tích. Giải thích chi phí của từng mức.
3. Tạo một base backup bằng pg_basebackup trong môi trường thử nghiệm. Kiểm tra backup bằng manifest nếu có và restore trên một máy chủ khác.
4. Bật WAL archiving, tạo một số thay đổi dữ liệu và xác nhận WAL được chuyển đến kho lưu trữ ngoài cụm.
5. Thực hiện PITR đến trước một lệnh UPDATE hoặc DELETE thử nghiệm. Xác minh trạng thái trước và sau recovery target.
6. Tạo một logical dump bằng pg_dump, lưu globals bằng pg_dumpall và restore vào database thử nghiệm. Kiểm tra role, owner và grant.
7. Mô phỏng archive_command thất bại. Theo dõi pg_stat_archiver, log và dung lượng pg_wal; sau đó khôi phục đường archive và xác nhận WAL được xử lý.
8. Tạo một standby bất đồng bộ và quan sát write_lag, flush_lag, replay_lag. Thảo luận dữ liệu nào có thể mất nếu promote tại các thời điểm khác nhau.
9. Xây dựng quy trình fencing và failover. Mô phỏng primary cũ mất liên lạc với monitor nhưng vẫn truy cập được từ một client; xác định cách ngăn split-brain.
10. Dựng một site DR cô lập chỉ dùng credential backup. Đo thời gian cấp phát, lấy backup, giải mã, restore, replay WAL và kiểm tra nghiệp vụ.
11. Thiết kế retention bất biến để tài khoản production không thể xóa backup trước hạn. Kiểm tra quyền bypass và quy trình khôi phục khóa.
12. Tổ chức một buổi tabletop cho tình huống mất toàn region. Phân công người tuyên bố DR, người chọn recovery target, người kiểm tra nghiệp vụ và người chuyển traffic.
13. Viết báo cáo diễn tập gồm RPO thực tế, RTO thực tế, các bước chậm nhất, lỗi phát hiện và hành động khắc phục.
14. Giải thích vì sao một backup job thành công không đủ chứng minh khả năng phục hồi, và đề xuất ba phép kiểm tra bổ sung.
15. Đưa ra quy trình xử lý khi phát hiện một thao tác xóa nhầm đã được replay sang standby nhưng backup và WAL vẫn còn đầy đủ.

## 18. Tài liệu tham khảo PostgreSQL

Khi triển khai, hãy đối chiếu tài liệu đúng major version của cluster vì tham số, view giám sát và quy trình recovery có thể thay đổi giữa các phiên bản.

- PostgreSQL Documentation — Backup and Restore: https://www.postgresql.org/docs/current/backup.html
- PostgreSQL Documentation — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL Documentation — pg_basebackup: https://www.postgresql.org/docs/current/app-pgbasebackup.html
- PostgreSQL Documentation — pg_verifybackup: https://www.postgresql.org/docs/current/app-pgverifybackup.html
- PostgreSQL Documentation — pg_dump: https://www.postgresql.org/docs/current/app-pgdump.html
- PostgreSQL Documentation — Warm Standby: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Monitoring Statistics: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Runtime Configuration, Replication: https://www.postgresql.org/docs/current/runtime-config-replication.html

Tài liệu tham khảo cần được kiểm tra theo phiên bản PostgreSQL đang triển khai. Tên tham số, cách cấu hình recovery và khả năng của công cụ backup có thể khác nhau giữa các major version.


