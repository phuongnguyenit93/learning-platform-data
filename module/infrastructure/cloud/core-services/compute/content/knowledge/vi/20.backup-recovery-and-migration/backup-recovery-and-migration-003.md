# Thiết kế lịch sao lưu và thời gian lưu giữ

Sao lưu là bản sao dữ liệu hoặc trạng thái hệ thống được giữ riêng để có thể khôi phục khi xảy ra xóa nhầm, lỗi ứng dụng, hỏng dữ liệu, ransomware hoặc mất cả một vùng hạ tầng. Trong môi trường cloud compute, đối tượng cần bảo vệ có thể là boot volume của VM, data volume, database, object storage, cấu hình mạng, image máy, manifest triển khai hoặc checkpoint của workload tính toán dài.

Một chính sách backup tốt phải trả lời được bốn câu hỏi: **sao lưu cái gì, sao lưu bao lâu một lần, giữ mỗi bản trong bao lâu và khôi phục trong thời gian nào**. Lịch sao lưu cần đáp ứng Recovery Point Objective (RPO); thời gian lưu giữ cần phù hợp yêu cầu vận hành, kiểm toán và pháp lý; còn Recovery Time Objective (RTO) quyết định cách tổ chức bản sao, vị trí lưu trữ và mức độ sẵn sàng để restore.

Không có một lịch chung phù hợp cho mọi dữ liệu. Database giao dịch, dữ liệu người dùng, boot disk, log tạm và image triển khai có tốc độ thay đổi, mức quan trọng và chi phí khôi phục khác nhau. Hãy phân loại dữ liệu trước, sau đó xây dựng lịch và retention cho từng nhóm.

## 1. RPO, RTO và retention là ba mục tiêu khác nhau

### Recovery Point Objective (RPO)

RPO là lượng dữ liệu tối đa tổ chức chấp nhận mất, tính theo thời gian từ thời điểm xảy ra sự cố về điểm dữ liệu gần nhất có thể khôi phục. Nếu RPO là 4 giờ, chính sách phải bảo đảm có điểm phục hồi phù hợp không cũ hơn khoảng 4 giờ trong điều kiện vận hành được định nghĩa.

RPO không nhất thiết bằng tần suất chạy backup. Một job backup chạy mỗi 4 giờ nhưng thường mất 90 phút mới hoàn tất có thể tạo ra khoảng trống bảo vệ lớn hơn dự kiến. Cần đo thời điểm dữ liệu thực sự nhất quán và bản sao đã được xác nhận thành công.

### Recovery Time Objective (RTO)

RTO là khoảng thời gian mục tiêu để khôi phục dịch vụ sau gián đoạn. RTO bao gồm phát hiện sự cố, quyết định điểm phục hồi, cấp phát hạ tầng, restore dữ liệu, cấu hình network/identity, kiểm tra ứng dụng và đưa traffic trở lại.

Có backup không đồng nghĩa đạt RTO. Một VM image lưu ở archive tier có thể rẻ nhưng cần nhiều giờ để lấy ra; một database backup lớn có thể mất thời gian restore và replay log; một bản sao ở region khác cần chuẩn bị network, quota và quyền truy cập.

### Retention period

Retention là thời gian giữ một bản backup hoặc điểm phục hồi trước khi được phép xóa theo policy. Retention giải quyết nhu cầu quay lại các thời điểm trong quá khứ, điều tra, kiểm toán hoặc đáp ứng quy định lưu trữ.

Retention dài không tự động cải thiện RPO. Giữ backup 7 năm nhưng chỉ tạo bản sao mỗi ngày vẫn có thể mất gần một ngày dữ liệu khi sự cố xảy ra. Ngược lại, backup mỗi 5 phút nhưng chỉ giữ 2 ngày có thể không đáp ứng nhu cầu khôi phục dữ liệu bị hỏng từ nhiều tuần trước.

| Mục tiêu | Câu hỏi cần trả lời | Yếu tố thiết kế chính |
|---|---|---|
| RPO | Có thể mất tối đa bao nhiêu dữ liệu? | Tần suất backup, log shipping, replication và consistency |
| RTO | Dịch vụ cần trở lại trong bao lâu? | Tốc độ restore, vị trí bản sao, automation và capacity |
| Retention | Cần quay lại những thời điểm trong quá khứ nào? | Thời gian giữ, số bản, lifecycle tier và legal hold |

## 2. Phân loại dữ liệu trước khi lập lịch

Không nên áp dụng cùng một lịch backup cho toàn bộ VM hoặc toàn bộ tài khoản cloud. Hãy phân loại theo giá trị dữ liệu, tốc độ thay đổi, mức độ quan trọng và khả năng tái tạo.

| Nhóm dữ liệu | Ví dụ | Cách bảo vệ thường dùng |
|---|---|---|
| Dữ liệu giao dịch | Database, transaction log, queue state | Backup nhất quán ứng dụng, log backup/PITR, replication |
| Dữ liệu người dùng | File upload, tài liệu, ảnh, object | Versioning, object backup, replication và retention |
| Dữ liệu hệ điều hành | Boot volume, cấu hình OS, package state | Image/golden image, volume snapshot, configuration management |
| Dữ liệu ứng dụng | File cấu hình, artifact, model, index | Versioned artifact, object storage, snapshot theo nhu cầu |
| Cấu hình hạ tầng | IaC, network rule, IAM policy, launch template | Version control, backup repository và audit history |
| Dữ liệu tạm | Cache, scratch disk, temporary file | Thường tái tạo; chỉ backup nếu có giá trị khôi phục rõ ràng |
| Checkpoint compute | Training state, batch progress, simulation state | Checkpoint định kỳ tới persistent/object storage |

Với workload stateless, có thể tái tạo VM từ image và cấu hình chuẩn thay vì backup toàn bộ máy thường xuyên. Với workload stateful, cần xác định dữ liệu nằm trên persistent volume, local/ephemeral disk, database hay dịch vụ ngoài VM. Dữ liệu duy nhất chỉ tồn tại trên local disk cần được chuyển hoặc sao lưu trước khi host/instance bị thay thế.

### Xác định owner và mức độ quan trọng

Mỗi nhóm dữ liệu nên có owner chịu trách nhiệm xác nhận RPO, RTO, retention và thử nghiệm restore. Phân loại có thể theo tier:

- **Critical:** mất dữ liệu hoặc gián đoạn gây ảnh hưởng lớn; cần RPO/RTO ngắn và kiểm thử thường xuyên.
- **Important:** cần khôi phục trong ngày làm việc hoặc theo cam kết dịch vụ; backup định kỳ và bản sao tách biệt.
- **Standard:** dữ liệu có thể tái tạo một phần hoặc chấp nhận thời gian khôi phục dài hơn.
- **Ephemeral:** dữ liệu tạm không cần giữ sau khi workload kết thúc, nếu owner xác nhận có thể tái tạo.

Tên tier không thay thế con số cụ thể. Ghi rõ RPO, RTO, retention, phạm vi tài nguyên và quy trình restore cho từng dịch vụ.

## 3. Chọn phương pháp backup phù hợp

### Full backup

Full backup sao chép toàn bộ dữ liệu thuộc phạm vi tại một thời điểm. Restore thường đơn giản vì không cần ghép nhiều bản tăng dần, nhưng thời gian chạy, dung lượng và chi phí truyền dữ liệu thường lớn.

Full backup phù hợp làm baseline định kỳ hoặc khi cần một điểm khôi phục độc lập. Tần suất full backup phụ thuộc tốc độ thay đổi dữ liệu và khả năng vận hành backup window.

### Incremental backup

Incremental backup chỉ sao chép phần thay đổi kể từ lần backup trước đó. Nó giảm dung lượng và thời gian tạo bản sao, nhưng quá trình restore có thể cần baseline cùng chuỗi incremental liên quan.

Nếu một mắt xích trong chuỗi bị thiếu hoặc hỏng, khả năng khôi phục có thể bị ảnh hưởng. Hệ thống backup cần xác minh chain integrity, quản lý metadata và định kỳ tạo điểm tổng hợp hoặc full mới theo thiết kế sản phẩm.

### Differential backup

Differential backup sao chép phần thay đổi kể từ lần full backup gần nhất. Dung lượng mỗi bản thường tăng theo thời gian cho tới lần full tiếp theo; restore cần full backup và differential gần nhất.

### Snapshot

Snapshot ghi nhận trạng thái volume hoặc tài nguyên tại một thời điểm logic. Snapshot có thể nhanh và tiết kiệm nhờ cơ chế copy-on-write hoặc block-level incremental, nhưng không phải lúc nào cũng tương đương backup độc lập.

Snapshot nằm trong cùng account, project hoặc hệ thống quyền với tài nguyên gốc có thể bị xóa cùng lúc khi credential bị chiếm. Snapshot volume đang được ghi có thể chỉ crash-consistent nếu không phối hợp với filesystem hoặc ứng dụng. Cần kiểm tra semantics của provider và yêu cầu consistency.

### Application-consistent backup

Application-consistent backup phối hợp với ứng dụng để tạo điểm dữ liệu nhất quán. Với database, có thể cần quiesce I/O, checkpoint, flush transaction hoặc dùng native backup/log mechanism. Với filesystem, có thể cần freeze filesystem trong thời gian ngắn.

Crash-consistent snapshot thường tương đương tình huống máy bị mất điện đột ngột: hệ thống có thể cần replay journal hoặc transaction log khi khởi động. Điều này có thể chấp nhận được với một số workload, nhưng không nên mặc định là đủ cho mọi database.

### Point-in-time recovery (PITR)

PITR kết hợp một full/base backup với transaction log hoặc change log để phục hồi tới một thời điểm cụ thể trong phạm vi log còn giữ. Nó hữu ích khi người dùng xóa nhầm dữ liệu hoặc ứng dụng ghi sai dữ liệu trong một khoảng thời gian.

PITR chỉ hoạt động nếu log được thu thập liên tục, lưu bền vững và có thể replay. Cần kiểm tra độ trễ log, khoảng trống log, retention của log và khả năng restore trên một môi trường riêng.

| Phương pháp | Chi phí tạo bản | Độ phức tạp restore | Điểm cần lưu ý |
|---|---|---|---|
| Full | Cao hơn | Thường đơn giản | Backup window và dung lượng lớn |
| Incremental | Thấp hơn mỗi lần | Có thể cần chuỗi bản sao | Bảo vệ chain và metadata |
| Differential | Tăng dần sau full | Full + bản differential gần nhất | Dung lượng tăng theo chu kỳ |
| Snapshot | Thường nhanh | Phụ thuộc provider và loại tài nguyên | Có thể không application-consistent |
| Native backup + log | Theo workload | Cần restore và replay log | Phù hợp database/PITR nếu kiểm thử đầy đủ |

## 4. Tính tần suất backup từ RPO

Tần suất backup cần được chọn sao cho khoảng cách giữa các điểm phục hồi thực sự đáp ứng RPO, kể cả thời gian chạy, lỗi retry và thời gian truyền dữ liệu.

Ví dụ đơn giản:

- RPO yêu cầu tối đa 24 giờ: backup hằng ngày có thể phù hợp nếu job hoàn tất và được xác minh trong giới hạn.
- RPO 4 giờ: backup mỗi 2 giờ có thể tạo headroom cho thời gian chạy và lỗi tạm thời.
- RPO 15 phút: snapshot hoặc backup theo lịch có thể chưa đủ nếu thời gian tạo bản dài; cần log backup, continuous protection hoặc cơ chế PITR.
- RPO gần bằng 0: thường cần replication đồng bộ hoặc kiến trúc ghi dữ liệu nhiều bản; backup vẫn cần để khôi phục lỗi logic và ransomware.

Các ví dụ trên chỉ minh họa cách suy luận. Tần suất cuối cùng phải dựa trên RPO đã thỏa thuận, thời gian tạo bản sao, độ trễ log và khả năng phục hồi đã đo.

### Lịch phải tính cả thời gian hoàn tất

Giả sử job chạy lúc 00:00 nhưng mất 70 phút. Nếu lần tiếp theo chỉ bắt đầu sau khi job trước hoàn tất, khoảng cách giữa các điểm backup có thể dài hơn chu kỳ danh nghĩa. Nếu job bị retry hoặc chờ quota, khoảng trống còn lớn hơn.

Theo dõi các thời điểm:

1. Backup bắt đầu.
2. Snapshot/data capture hoàn tất.
3. Log hoặc dữ liệu bổ sung đã được chuyển đầy đủ.
4. Integrity check hoàn tất.
5. Bản sao được đánh dấu usable/available.

RPO nên được đo từ điểm dữ liệu khôi phục được gần nhất, không chỉ từ timestamp bắt đầu job.

### Lịch theo loại workload

| Workload | Lịch tham khảo | Bổ sung cần cân nhắc |
|---|---|---|
| Database giao dịch quan trọng | Base backup hằng ngày hoặc theo thiết kế; transaction log liên tục/định kỳ ngắn | PITR, native backup, consistency và restore test |
| Database nội bộ tiêu chuẩn | Full hằng ngày hoặc theo chu kỳ; log theo RPO | Kiểm tra dung lượng, retention và thời gian replay |
| File/object người dùng | Versioning liên tục hoặc backup theo ngày | Lifecycle, replication và bảo vệ xóa nhầm |
| Boot volume VM | Snapshot trước/sau thay đổi lớn và lịch định kỳ | Golden image, config backup, application consistency |
| Data volume | Theo tốc độ thay đổi và RPO | Snapshot phối hợp ứng dụng hoặc backup agent |
| IaC và cấu hình | Mỗi commit/version; backup repository định kỳ | Protected branch, audit và bản sao độc lập |
| Checkpoint AI/batch | Theo thời gian tính toán có thể chấp nhận chạy lại | Checkpoint trước sự kiện bảo trì hoặc trước thay đổi lớn |

Không sao lưu dữ liệu tạm theo lịch dày nếu có thể tái tạo nhanh và không có yêu cầu giữ lại. Ngược lại, dữ liệu quan trọng cần backup độc lập kể cả khi đã có replication.

## 5. Thiết kế retention: giữ bao lâu và giữ những bản nào?

Retention cần đáp ứng nhu cầu phục hồi ngắn hạn, điều tra lỗi phát hiện muộn và yêu cầu lưu trữ dài hạn. Giữ mọi bản mãi mãi làm tăng chi phí và bề mặt rủi ro; xóa quá sớm khiến tổ chức không thể quay lại trước khi dữ liệu bị hỏng hoặc mã độc xâm nhập.

### Retention theo nhiều lớp thời gian

Một policy thường kết hợp:

- Bản sao ngắn hạn để phục hồi lỗi vận hành gần đây.
- Bản sao hằng ngày để phục hồi trong vài tuần.
- Bản sao hằng tuần hoặc hằng tháng để điều tra lỗi phát hiện muộn.
- Bản sao dài hạn theo quý/năm nếu có yêu cầu kiểm toán hoặc pháp lý.

Mô hình GFS (Grandfather-Father-Son) là một cách tổ chức điểm phục hồi:

- **Son:** các bản gần đây, ví dụ theo giờ hoặc theo ngày.
- **Father:** các bản theo tuần.
- **Grandfather:** các bản theo tháng hoặc năm.

GFS giúp giữ các điểm đại diện trong thời gian dài mà không phải giữ mọi bản backup với cùng tần suất. Cần xác định rõ cách chọn bản, thời hạn và quy tắc xóa.

### Ví dụ retention minh họa

| Nhóm bản sao | Số lượng/chu kỳ ví dụ | Mục đích |
|---|---|---|
| Hourly | 24 bản gần nhất | Khôi phục lỗi trong ngày |
| Daily | 30 bản | Khôi phục trong tháng |
| Weekly | 12 bản | Khôi phục theo tuần trong quý |
| Monthly | 12 bản | Khôi phục theo tháng trong năm |
| Annual | Theo yêu cầu, ví dụ 7 năm | Kiểm toán hoặc nghĩa vụ lưu trữ |

Đây không phải khuyến nghị áp dụng mặc định. Hãy xác định retention từ yêu cầu của dữ liệu, luật áp dụng, hợp đồng và chi phí. Một số hệ thống có thể cần giữ log lâu hơn backup; một số dữ liệu cá nhân phải xóa khi hết mục đích lưu trữ.

### Retention và legal hold

Legal hold hoặc investigation hold có thể yêu cầu giữ một số bản sao vượt quá lịch xóa thông thường. Hold cần có người phê duyệt, phạm vi dữ liệu, lý do và điều kiện kết thúc. Khi hold được gỡ, retention lifecycle có thể tiếp tục.

Không dùng legal hold như cách giữ vô thời hạn mọi dữ liệu. Cần kiểm soát quyền, audit và phân biệt bản backup vận hành với bản lưu trữ phục vụ pháp lý.

## 6. Lưu ý về retention của snapshot và incremental chain

Nhiều dịch vụ snapshot lưu block thay đổi theo kiểu incremental. Xóa một snapshot cũ không nhất thiết giải phóng toàn bộ block mà snapshot đó tham chiếu; provider có thể duy trì block cần thiết cho các snapshot còn lại. Ngược lại, xóa thủ công object hoặc metadata bên dưới có thể phá hỏng chuỗi backup nếu dịch vụ không quản lý lifecycle.

Do đó:

- Dùng retention/lifecycle API chính thức của dịch vụ backup.
- Không xóa trực tiếp block/object nội bộ nếu nhà cung cấp không hỗ trợ.
- Kiểm tra snapshot dependency và restore point sau mỗi lần lifecycle chạy.
- Xác minh bản gần nhất còn restore được trước khi xóa bản cũ.
- Theo dõi chi phí thực tế sau xóa; dung lượng tính phí có thể cập nhật trễ hoặc theo block duy nhất.

Với incremental backup dạng file/agent, cần giữ đầy đủ metadata, catalog và các bản liên quan. Backup catalog cũng là dữ liệu quan trọng cần được bảo vệ riêng.

## 7. Backup window, tải hệ thống và lịch chạy

Backup có thể tiêu thụ CPU, RAM, disk I/O, network bandwidth, API request và quota. Chạy nhiều job cùng lúc có thể làm chậm ứng dụng hoặc vượt giới hạn của provider.

### Chọn backup window

Lịch nên cân nhắc:

- Giờ cao điểm và thấp điểm của ứng dụng.
- Batch job, ETL, maintenance và thời gian đóng sổ.
- Thời gian tạo snapshot hoặc export database.
- Băng thông tới region/backup vault.
- Số lượng VM/volume cùng lúc và giới hạn concurrency.
- Thời gian retry nếu job thất bại.

Nếu nhiều hệ thống dùng cùng thời điểm backup, phân tán lịch bằng jitter hoặc staggered schedule. Tránh để toàn bộ VM bắt đầu full backup cùng phút đầu giờ.

### Backup có thể ảnh hưởng hiệu năng như thế nào?

- Backup agent đọc nhiều block có thể tăng disk queue và latency.
- Nén/mã hóa ở guest có thể tiêu thụ CPU.
- Truyền bản sao qua mạng có thể tranh băng thông với traffic ứng dụng.
- Snapshot ở mức provider có thể có giới hạn concurrency hoặc API throttling.
- Database export có thể tạo tải đọc, lock hoặc ảnh hưởng cache.

Theo dõi p95 latency, IOPS, throughput, CPU và error rate trong backup window. Nếu ảnh hưởng vượt ngưỡng, giảm concurrency, chuyển lịch hoặc dùng phương pháp backup ít tác động hơn.

### Xử lý timezone và daylight saving

Lịch backup nên được lưu bằng UTC hoặc một timezone được định nghĩa rõ. Nếu lịch theo giờ địa phương, cần xác định hành vi khi chuyển giờ mùa hè, đổi múi giờ hoặc khi hệ thống điều phối chạy ở region khác. Tránh tạo hai backup trùng hoặc bỏ lỡ một lần chạy do đồng hồ thay đổi.

## 8. Bảo vệ tính nhất quán của dữ liệu

Một backup hoàn tất về mặt kỹ thuật chưa chắc là bản sao có thể sử dụng. Cần hiểu trạng thái ứng dụng trong lúc capture.

### Crash-consistent

Crash-consistent backup ghi nhận trạng thái gần giống việc máy bị mất điện đột ngột. Filesystem journal hoặc database transaction log có thể giúp hệ thống tự phục hồi khi mở lại, nhưng một số ứng dụng cần quy trình nhất quán riêng.

### Filesystem-consistent

Filesystem-consistent backup phối hợp flush hoặc freeze filesystem để giảm khả năng có dữ liệu đang nằm trong cache chưa được ghi. Điều này vẫn chưa bảo đảm nhiều volume hoặc database phân tán tạo thành một điểm dữ liệu nhất quán chung.

### Application-consistent

Application-consistent backup phối hợp với ứng dụng để flush transaction, checkpoint hoặc quiesce I/O. Với database, dùng native backup và log backup theo hướng dẫn sản phẩm thường đáng tin cậy hơn việc chỉ snapshot một volume đang ghi.

### Nhiều volume và hệ thống phân tán

Nếu database lưu data, log và metadata trên nhiều volume, cần đảm bảo snapshot đồng bộ hoặc dùng cơ chế backup có nhận biết ứng dụng. Snapshot từng volume ở các thời điểm khác nhau có thể tạo trạng thái không nhất quán.

Với cluster nhiều node, xác định backup ở cấp node hay cluster. Không lấy snapshot đồng thời của mọi node mà không có quy trình đảm bảo quorum, leader state và replication consistency.

## 9. Lưu backup ở đâu và tách biệt như thế nào?

Backup nên có ranh giới lỗi và quyền truy cập độc lập với tài nguyên gốc. Nếu VM và backup cùng phụ thuộc một account, cùng credential và cùng region, một sự cố hoặc hành vi xâm nhập có thể ảnh hưởng cả hai.

### Mô hình 3-2-1-1-0

Một nguyên tắc phổ biến là:

- **3 bản:** giữ tối thiểu ba bản dữ liệu, tính cả bản production.
- **2 loại môi trường/phương tiện:** tránh phụ thuộc duy nhất một hệ thống lưu trữ.
- **1 bản offsite:** có bản sao ở vị trí hoặc fault domain khác.
- **1 bản offline hoặc immutable:** khó bị sửa/xóa bởi tài khoản vận hành thông thường.
- **0 lỗi chưa được xác minh:** kiểm tra tính toàn vẹn và thực hiện restore test.

Đây là nguyên tắc thiết kế, không phải công thức thay thế đánh giá rủi ro. Với cloud, “offsite” có thể là account/project hoặc region khác; “immutable” có thể là vault/object lock có thời hạn không thể rút ngắn bởi role thông thường.

### Tách account/project và quyền quản trị

Tài khoản backup nên có quyền riêng. Workload production chỉ cần quyền ghi bản sao theo policy; không nên có quyền xóa hoặc rút ngắn retention của mọi bản backup. Quyền restore có thể được cấp theo quy trình incident hoặc vai trò riêng.

Dùng MFA, role separation, audit log và approval cho thao tác thay đổi vault, retention hoặc immutable lock. Bảo vệ cả tài khoản quản trị backup và identity tự động hóa.

### Cross-region và cross-account copy

Bản sao ở region khác giúp khôi phục khi region nguồn gặp sự cố, nhưng cần xem xét:

- RPO của replication/copy và thời gian hoàn tất.
- Chi phí truyền dữ liệu, lưu trữ và restore.
- Khả năng tạo VM/volume ở region đích và quota tương ứng.
- Network, DNS, IAM, key và secret có sẵn ở region đích không.
- Quy định về vị trí lưu dữ liệu và chủ quyền dữ liệu.
- Khả năng ứng dụng hoạt động với endpoint và dependency ở region mới.

Cross-region copy không tự động tạo một kế hoạch DR hoàn chỉnh. Cần có runbook khôi phục dịch vụ và kiểm thử định kỳ.

## 10. Mã hóa, quản lý khóa và quyền truy cập backup

Backup thường chứa dữ liệu đầy đủ của hệ thống, vì vậy cần bảo vệ tương đương hoặc cao hơn dữ liệu production.

### Encryption at rest và in transit

Mã hóa bản backup khi lưu và bảo vệ đường truyền khi copy/restore. Kiểm tra dịch vụ mã hóa mặc định hay yêu cầu cấu hình riêng, thuật toán, key scope và khả năng đổi khóa.

### Quản lý khóa

Nếu backup được mã hóa bằng customer-managed key, cần đảm bảo key và quyền decrypt còn khả dụng trong tình huống DR. Một bản backup không thể giải mã sẽ không có giá trị phục hồi.

Không để key chỉ tồn tại trong cùng VM hoặc account có thể bị mất trong sự cố. Quản lý key recovery, rotation, disable/delete protection và quyền truy cập khẩn cấp. Thử restore bằng đúng cơ chế key trong môi trường kiểm thử.

### Quyền tối thiểu

- Tách quyền tạo backup, đọc backup, restore và xóa backup.
- Hạn chế role có thể sửa retention hoặc xóa vault.
- Dùng identity ngắn hạn cho automation.
- Ghi audit cho create, copy, restore, delete và thay đổi policy.
- Rà soát quyền định kỳ và khi nhân sự/service thay đổi.

### Dữ liệu nhạy cảm trong backup

Backup có thể chứa password hash, secret, token, private key, dữ liệu cá nhân và log. Giới hạn quyền truy cập, mã hóa, phân loại và áp dụng retention đúng mục đích. Không giữ bản backup vô thời hạn chỉ vì dung lượng rẻ.

## 11. Immutable backup và bảo vệ ransomware

Ransomware hoặc tài khoản bị chiếm có thể tìm cách xóa snapshot, mã hóa volume và xóa cả backup. Immutable backup hoặc write-once retention giúp ngăn sửa/xóa bản sao trong thời hạn được bảo vệ.

Khi thiết kế:

- Bật immutable/WORM hoặc vault lock theo khả năng dịch vụ.
- Dùng thời hạn lock phù hợp yêu cầu phục hồi và pháp lý.
- Tách quyền thay đổi policy khỏi quyền tạo backup.
- Giữ ít nhất một bản ở account hoặc security boundary riêng.
- Giám sát hành vi xóa hàng loạt, thay đổi retention và disable backup policy.
- Kiểm tra khả năng restore khi tài khoản production bị cô lập.

Immutable không ngăn dữ liệu bị hỏng trước thời điểm backup. Nếu mã độc đã tồn tại nhiều tuần trước khi phát hiện, cần giữ đủ lịch sử để chọn điểm sạch. Kết hợp retention dài hạn với malware scanning, anomaly detection và quy trình xác minh điểm phục hồi.

## 12. Lifecycle và tối ưu chi phí retention

Chi phí backup phụ thuộc dung lượng lưu, số bản, tốc độ thay đổi, vùng lưu, bản copy, API, retrieval và thời gian restore. Cần tính tổng chi phí vòng đời thay vì chỉ nhìn giá lưu trữ mỗi GB.

### Storage tier

Một số dịch vụ có lớp lưu trữ nóng, lạnh hoặc archive. Bản gần đây cần restore nhanh có thể ở tier truy cập nhanh; bản cũ ít dùng có thể chuyển sang tier rẻ hơn nếu RTO cho phép.

Trước khi chuyển tier, kiểm tra:

- Thời gian retrieval và phí lấy dữ liệu.
- Minimum storage duration hoặc phí xóa sớm.
- Kích thước object tối thiểu và phí request.
- Backup chain có hỗ trợ tier đó không.
- Restore có cần rehydrate trước hay không.
- Key, metadata và catalog có được giữ đầy đủ không.

### Tính retention theo tổng dung lượng

Ước lượng đơn giản cho full backup:

\[
\text{Stored capacity} \approx
\text{Backup size} \times \text{Number of retained copies}
\]

Với incremental backup, dung lượng phụ thuộc tỷ lệ thay đổi mỗi chu kỳ và cách provider tính block/object duy nhất. Cần dùng số liệu thực tế của dịch vụ thay vì nhân đơn giản số bản với kích thước full.

### Lifecycle policy

Lifecycle policy có thể chuyển tier hoặc xóa bản sao khi hết hạn. Trước khi bật xóa tự động:

1. Xác minh retention đang áp dụng cho đúng resource/tag/tier.
2. Kiểm tra legal hold và exception.
3. Bảo đảm còn đủ restore point theo yêu cầu.
4. Xác minh chuỗi incremental và catalog không bị phá vỡ.
5. Bật ở phạm vi nhỏ, quan sát log xóa và chi phí.
6. Rà soát định kỳ các bản orphan hoặc tài nguyên không còn owner.

Không dùng tag có thể bị người dùng thay đổi tùy tiện làm điều kiện duy nhất để xóa backup quan trọng.

## 13. Lập lịch theo workload: ví dụ cụ thể

### Ví dụ A: API stateless trên VM

Ứng dụng web có thể tạo lại từ golden image và IaC. Dữ liệu người dùng nằm trong object storage và database managed.

Chính sách có thể gồm:

- Lưu version của image và IaC theo release.
- Snapshot boot volume trước thay đổi hệ điều hành hoặc driver.
- Backup cấu hình và artifact theo commit/release.
- Backup database theo RPO riêng và bật PITR nếu cần.
- Versioning/retention cho object storage theo yêu cầu dữ liệu.

Không cần snapshot mọi boot disk mỗi giờ nếu VM hoàn toàn stateless và có thể tái tạo. Tập trung bảo vệ dữ liệu bền vững và khả năng dựng lại compute.

### Ví dụ B: Database trên VM với data volume riêng

Database có data volume, transaction log volume và boot volume. RPO mục tiêu 15 phút, RTO mục tiêu 2 giờ.

Thiết kế cần phối hợp native database backup và log backup đủ thường xuyên để đáp ứng RPO. Snapshot volume có thể dùng làm baseline nếu có cơ chế quiesce hoặc consistency group phù hợp. Boot volume có thể backup ít thường xuyên hơn vì OS có thể dựng lại từ image chuẩn. Bản backup được copy sang account/region khác và retention theo tier dữ liệu.

Restore test phải bao gồm tạo VM tương thích, attach volume, phục hồi database, replay log tới thời điểm chọn và xác minh dữ liệu trước khi mở ứng dụng.

### Ví dụ C: Worker xử lý video

Worker chạy job dài trên VM GPU/CPU. Input video nằm trong object storage; output được ghi ra bucket; tiến độ xử lý có checkpoint.

Checkpoint được lưu sau mỗi khoảng xử lý hoặc trước khi instance bị bảo trì. Không nhất thiết backup toàn bộ local scratch disk vì có thể tái tạo từ input. Cần giữ metadata của job, phiên bản codec, model, driver và runtime để có thể tiếp tục trên instance tương thích.

### Ví dụ D: File server nội bộ

File server có dữ liệu thay đổi thường xuyên và yêu cầu khôi phục file bị xóa nhầm trong 30 ngày. Có thể dùng snapshot/versioning ngắn hạn với tần suất phù hợp, backup hằng ngày và bản tuần/tháng dài hơn. Bản sao nên được tách khỏi quyền ghi của máy file server để ransomware không thể xóa toàn bộ lịch sử.

## 14. Quy trình restore và kiểm thử backup

Backup chỉ được coi là đáng tin khi đã chứng minh có thể khôi phục. Một job báo success không đảm bảo file không hỏng, key còn dùng được hoặc ứng dụng khởi động được.

### Kiểm tra tự động sau backup

- Xác minh job status và thời điểm hoàn tất.
- Kiểm tra kích thước, số object, checksum hoặc integrity metadata.
- Kiểm tra backup catalog và chain.
- Xác nhận log backup không có gap.
- Kiểm tra bản copy ở vault/region đích.
- Cảnh báo nếu dữ liệu backup nhỏ bất thường hoặc không thay đổi trong khi nguồn đang thay đổi.

### Restore test

Thực hiện restore vào môi trường cô lập để tránh ghi đè production:

1. Chọn một restore point theo lịch retention.
2. Xác nhận quyền và key có thể giải mã.
3. Restore volume/database/object vào tài nguyên mới.
4. Kiểm tra checksum, filesystem, database consistency và dữ liệu nghiệp vụ.
5. Khởi động ứng dụng với network bị giới hạn.
6. Chạy smoke test và truy vấn kiểm chứng.
7. Đo thời gian hoàn tất và so sánh với RTO.
8. Ghi nhận điểm lỗi, thời gian và action item.

### Tần suất diễn tập

Tần suất restore test phụ thuộc mức quan trọng và tốc độ thay đổi. Dữ liệu critical nên được kiểm thử thường xuyên hơn và có diễn tập DR theo kịch bản mất account/region. Ít nhất cần thử cả bản gần nhất và một bản cũ theo retention dài hạn để xác minh lifecycle.

### Kiểm tra RPO và RTO thực tế

Đo:

- Thời điểm dữ liệu cuối cùng có thể phục hồi so với thời điểm sự cố giả lập.
- Thời gian từ khi bắt đầu restore tới khi ứng dụng qua health check và smoke test.
- Thời gian cấp phát compute, network, key, identity và dependency.
- Thời gian replay log, rebuild index hoặc warm cache.

Nếu RTO thực tế vượt mục tiêu, cần tối ưu quy trình hoặc thay đổi kiến trúc: giữ sẵn capacity, dùng replica, tăng song song restore, chọn tier truy cập nhanh hơn hoặc giảm kích thước dữ liệu phải khôi phục.

## 15. Giám sát backup và cảnh báo

Nên theo dõi các chỉ số:

| Chỉ số | Vì sao quan trọng |
|---|---|
| Backup success rate | Phát hiện job thất bại hoặc không chạy |
| Last successful recovery point | Biết điểm dữ liệu gần nhất có thể phục hồi |
| Backup age / RPO gap | Phát hiện vượt RPO |
| Backup duration | Phát hiện job ngày càng lâu hoặc quá backup window |
| Data transferred / changed ratio | Phát hiện bất thường về dung lượng |
| Restore test success | Xác minh bản sao dùng được |
| Restore duration | Đo khả năng đạt RTO |
| Retention compliance | Xác nhận số bản và thời gian giữ phù hợp |
| Immutable coverage | Đo phạm vi bản sao được bảo vệ khỏi xóa/sửa |
| Cross-region copy lag | Đánh giá khả năng phục hồi khi mất region |
| Backup cost | Theo dõi chi phí lưu trữ, copy và retrieval |

Alert cần phát hiện không chỉ job failed mà cả trường hợp không có backup mới trong khoảng thời gian cho phép. Một policy có thể vẫn bật nhưng không tạo bản sao vì quyền đã bị thu hồi hoặc tài nguyên mới chưa được gắn vào policy.

## 16. Những sai lầm thường gặp

- **Nhầm retention với RPO:** giữ lâu không có nghĩa backup đủ thường xuyên.
- **Chỉ nhìn trạng thái job success:** chưa xác minh integrity và khả năng restore.
- **Dùng snapshot thay cho mọi loại backup:** snapshot có thể crash-consistent, cùng failure domain hoặc phụ thuộc provider.
- **Backup database bằng cách copy file đang ghi:** có thể tạo bản không nhất quán.
- **Không bảo vệ transaction log:** mất log có thể làm PITR không đạt RPO.
- **Giữ backup và production cùng quyền quản trị:** tài khoản bị chiếm có thể xóa cả hai.
- **Không giữ key hoặc metadata:** backup còn nhưng không giải mã hoặc không restore được.
- **Xóa incremental chain thủ công:** làm hỏng restore point còn lại.
- **Chuyển archive mà không tính RTO:** retrieval có thể mất nhiều giờ hoặc phát sinh phí.
- **Không tính quota ở region DR:** có backup nhưng không tạo được VM khi cần.
- **Không kiểm thử dữ liệu nghiệp vụ:** filesystem mount được nhưng ứng dụng hoặc database vẫn lỗi.
- **Không quản lý dữ liệu hết hạn:** retention quá dài gây chi phí và rủi ro quyền riêng tư.

## 17. Checklist thiết kế lịch backup và retention

**Phân loại và mục tiêu:**

- [ ] Đã liệt kê dữ liệu cần bảo vệ và owner.
- [ ] Đã xác định RPO, RTO và retention riêng cho từng nhóm.
- [ ] Đã phân biệt dữ liệu stateless, persistent và ephemeral.
- [ ] Đã xác định yêu cầu pháp lý, kiểm toán và legal hold.

**Lịch và phương pháp:**

- [ ] Tần suất backup đáp ứng RPO dựa trên recovery point thực tế.
- [ ] Đã chọn full/incremental/differential/snapshot/native backup phù hợp.
- [ ] Database và workload stateful có application-consistent backup hoặc log strategy.
- [ ] Backup window không gây quá tải CPU, I/O và network.
- [ ] Lịch dùng timezone rõ ràng và có xử lý retry.

**Retention và bảo vệ:**

- [ ] Có retention ngắn hạn và dài hạn theo nhu cầu.
- [ ] Incremental chain/catalog được quản lý bằng công cụ chính thức.
- [ ] Có bản offsite/cross-account hoặc failure domain riêng.
- [ ] Có immutable/offline copy cho dữ liệu quan trọng.
- [ ] Backup được mã hóa và key có kế hoạch recovery.
- [ ] Quyền tạo, restore, xóa và sửa policy được tách biệt.

**Kiểm thử và vận hành:**

- [ ] Có kiểm tra integrity sau backup.
- [ ] Có restore test vào môi trường cô lập.
- [ ] Đo RPO/RTO thực tế và ghi nhận kết quả.
- [ ] Có alert cho backup stale, failed, retention gap và copy lag.
- [ ] Có runbook khôi phục khi mất VM, volume, account hoặc region.
- [ ] Lifecycle deletion được kiểm tra trước khi áp dụng rộng.

## Kết luận

Thiết kế lịch backup và retention bắt đầu từ phân loại dữ liệu cùng RPO/RTO của từng workload. Chọn phương pháp full, incremental, differential, snapshot hoặc native backup theo tính nhất quán và khả năng restore; tính tần suất từ điểm phục hồi thực tế; giữ bản sao theo nhiều lớp thời gian; tách backup khỏi failure domain và quyền quản trị của production. Bảo vệ backup bằng mã hóa, key recovery, immutable copy và lifecycle có kiểm soát. Cuối cùng, đo backup age, kiểm tra integrity và diễn tập restore để chứng minh RPO, RTO và retention thực sự đáp ứng yêu cầu.
