# Lập chiến lược backup cho Compute, Storage và Database

Trong Oracle Cloud Infrastructure (OCI), một ứng dụng thường phụ thuộc đồng thời vào máy ảo Compute, các loại Storage, cơ sở dữ liệu, mạng VCN và quyền IAM. Sao lưu riêng từng tài nguyên chưa đủ để khôi phục toàn bộ dịch vụ: máy ảo có thể khởi động nhưng thiếu volume dữ liệu; database có thể mở nhưng không còn tài liệu mà các bản ghi tham chiếu đến.

Bài học thuộc chương **Sao lưu và khôi phục thảm họa**, tập trung vào cách lập chiến lược backup có thể triển khai và kiểm chứng trên OCI. Kết quả cần đạt là kế hoạch nêu rõ dữ liệu phải bảo vệ, cơ chế sử dụng, lịch chạy, thời gian lưu giữ, quyền truy cập, nơi khôi phục và bằng chứng đáp ứng mục tiêu kinh doanh.

## 1. Bắt đầu bằng yêu cầu khôi phục

### 1.1. RPO, RTO và cửa sổ khôi phục

**Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa chấp nhận được, đo bằng thời gian. RPO 15 phút có nghĩa là khi sự cố xảy ra, tổ chức chấp nhận mất tối đa 15 phút thay đổi gần nhất.

**Recovery Time Objective (RTO)** là thời gian gián đoạn tối đa chấp nhận được để đưa dịch vụ trở lại mức hoạt động đã thống nhất. RTO bao gồm phát hiện, quyết định xử lý, dựng hạ tầng, lấy dữ liệu, phục hồi, kiểm tra và mở lại lưu lượng.

**Retention** là thời gian giữ bản sao. **Recovery window** là khoảng thời gian có thể chọn điểm khôi phục; với database, điều này còn phụ thuộc vào backup nền và chuỗi log cần thiết. Giữ một backup 30 ngày không tự tạo khả năng phục hồi đến mọi giây trong 30 ngày đó.

Ví dụ: sự cố xảy ra lúc 10:20; điểm dữ liệu mới nhất đã bảo vệ và khôi phục được là 10:00. Mức mất dữ liệu tiềm năng là 20 phút. Nếu kế hoạch yêu cầu RPO 15 phút thì mục tiêu chưa đạt, dù tác vụ backup gần nhất báo thành công.

Cần phân biệt ba mốc:

- Thời điểm dữ liệu mà backup đại diện.
- Thời điểm backup hoàn tất và có thể sử dụng.
- Thời điểm bản sao ở nơi khôi phục dự phòng sẵn sàng.

Khi đánh giá mất region, chỉ dùng những điểm khôi phục có thể truy cập ở region đích. Backup mới còn nằm trong region đang mất kết nối chưa giúp giảm RPO cho kịch bản đó.

### 1.2. Đánh giá theo loại sự cố

| Sự cố | Khả năng cần có | Câu hỏi thiết kế |
| --- | --- | --- |
| Xóa nhầm file hoặc object | Lấy lại phiên bản trước | Có tìm được đúng phiên bản và kiểm tra nội dung không? |
| Lỗi hệ điều hành sau cập nhật | Phục hồi boot volume hoặc dựng lại máy | Dữ liệu ứng dụng có độc lập với hệ điều hành không? |
| Hỏng dữ liệu logic | Quay về trước giao dịch lỗi | Có đủ backup, log và thông tin thời điểm lỗi không? |
| Mất availability domain (AD) | Khôi phục ở AD khác nếu region hỗ trợ | Mạng, Compute và quyền ở đích đã sẵn sàng chưa? |
| Mất region | Vận hành từ region khác | Bản sao đích, khóa, quota và cấu hình có dùng được không? |
| Tài khoản quản trị bị chiếm quyền | Bản sao được bảo vệ khỏi xóa/sửa | Một danh tính có thể xóa cả nguồn lẫn lịch sử không? |

Lập RPO/RTO riêng cho từng kịch bản. Kết quả phục hồi volume trong cùng region không đồng thời chứng minh khả năng phục hồi khi mất region.

### 1.3. Phân biệt backup, replication và tính sẵn sàng

Backup giữ các điểm dữ liệu trong quá khứ để quay lui. Replication duy trì bản sao theo thay đổi của nguồn, giúp chuyển hoạt động sang vị trí khác. High availability giảm gián đoạn khi thành phần gặp lỗi.

Hệ thống có replica vẫn cần backup để xử lý lỗi logic hoặc xóa nhầm đã lan sang bản sao. Ngược lại, backup hằng ngày có thể phù hợp cho dữ liệu ít thay đổi nhưng khó đáp ứng yêu cầu khôi phục trong vài phút. Khi RPO/RTO vượt khả năng phục hồi từ backup, phải bổ sung cơ chế DR phù hợp, chẳng hạn standby database hoặc hạ tầng dự phòng.

## 2. Kiểm kê tài nguyên và ranh giới bảo vệ

Lập danh mục theo **dịch vụ nghiệp vụ**, thay vì chỉ liệt kê tài nguyên rời rạc.

| Thông tin cần ghi | Ví dụ |
| --- | --- |
| Chủ sở hữu | Nhóm vận hành ứng dụng quản lý đơn hàng |
| Vị trí | Tenancy, compartment, region, AD nếu có |
| Định danh | OCID của instance, volume, file system hoặc database |
| Nội dung thực tế | Hệ điều hành, dữ liệu giao dịch, file đính kèm, log |
| Dung lượng và tốc độ thay đổi | 500 GiB, khoảng 20 GiB thay đổi/ngày |
| Nguồn có thể tái tạo | Image chuẩn, mã nguồn, Terraform, gói phát hành |
| Mục tiêu | RPO/RTO cho sự cố cục bộ và mất region |
| Ràng buộc | Dữ liệu nhạy cảm, nơi được phép lưu, thời gian giữ |
| Phụ thuộc | Khóa mã hóa, secret, DNS, IAM, mạng, phiên bản ứng dụng |

Phân loại dữ liệu thành ba nhóm:

1. **Không thể tái tạo:** đơn hàng, tài liệu người dùng, cấu hình chỉ tồn tại trong hệ thống.
2. **Có thể dựng lại:** máy ứng dụng được tạo từ image, mã nguồn và cấu hình có quản lý phiên bản.
3. **Có thể tạo lại với chi phí xác định:** cache, chỉ mục tìm kiếm, báo cáo tổng hợp.

Nhóm thứ ba vẫn ảnh hưởng RTO. Nếu tạo lại chỉ mục mất sáu giờ trong khi RTO là hai giờ, phải đổi cách phục hồi hoặc bảo vệ thêm chỉ mục.

Mô tả quan hệ nhất quán giữa các nhóm. Nếu database giữ đường dẫn tới file trên File Storage, một database ở 10:15 và file system ở 08:00 có thể không tạo thành trạng thái ứng dụng hợp lệ. Cần điểm đối chiếu chung, log nghiệp vụ hoặc quy trình bù trừ.

## 3. Chọn cơ chế cho từng loại tài nguyên OCI

| Thành phần | Cơ chế cần xem xét | Việc phải bổ sung |
| --- | --- | --- |
| Compute boot volume | Boot volume backup | Cấu hình instance, mạng và khả năng khởi động |
| Block Volume chứa dữ liệu | Volume backup | Kiểm tra filesystem và tính nhất quán ứng dụng |
| Nhiều volume liên quan | Volume group backup | Phối hợp với ứng dụng hoặc database khi cần |
| Object Storage | Versioning hoặc bản sao lịch sử độc lập | Quyền xóa, retention và khả năng truy xuất |
| File Storage | Snapshot theo chính sách | Bảo vệ trước lỗi vượt phạm vi nguồn |
| Oracle Database trên Compute | RMAN và bảo vệ log | Control file, cấu hình, khóa và quy trình DBA |
| Oracle Database được quản lý | Backup tích hợp của đúng dịch vụ | Recovery window, destination, xử lý khi xóa database |
| Hạ tầng và cấu hình | Infrastructure as Code, quản lý cấu hình | State, phiên bản provider, secret và quyền dựng lại |

Không có một chính sách backup duy nhất tự bảo vệ tất cả các hàng. Với mỗi hàng, phải chỉ ra người chịu trách nhiệm và cách kiểm chứng phục hồi.

## 4. Chiến lược cho Compute và Block Volume

### 4.1. Tách dữ liệu máy ảo khỏi cấu hình điều khiển

Một máy ảo bao gồm:

- Boot volume chứa hệ điều hành và phần mềm.
- Block volume hoặc file system chứa dữ liệu.
- Cấu hình điều khiển: shape, VNIC, subnet, NSG, metadata, volume attachment.
- Phụ thuộc ngoài máy: database, bucket, secret, khóa và dịch vụ mạng.

Custom image phù hợp để tạo máy từ boot disk đã chuẩn hóa. Dữ liệu của block volume gắn thêm **không nằm trong custom image**, nên phải bảo vệ riêng. [Nguồn: Managing Custom Images](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/managingcustomimages.htm).

Với máy ứng dụng dựng lại được, lưu phiên bản image, cấu hình và gói triển khai, đồng thời backup dữ liệu phát sinh. Với máy có nhiều thay đổi thủ công, tăng tần suất bảo vệ boot volume và đưa dần cấu hình vào quản lý phiên bản.

Khôi phục đĩa không tự dựng lại subnet, NSG hoặc load balancer. Những thành phần này cần bản mô tả hạ tầng và quy trình riêng.

### 4.2. Full, incremental và phục hồi volume

OCI hỗ trợ backup boot volume, block volume và volume group. Với Block Volume, full và incremental đều cho phép phục hồi toàn bộ nội dung tại điểm backup; dịch vụ quản lý phụ thuộc dữ liệu bên dưới. Không áp dụng máy móc quy tắc phải tự giữ toàn bộ chuỗi file incremental như với công cụ backup tự quản. [Nguồn: Block Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

Đánh giá vận hành dựa trên điểm dữ liệu, tình trạng hoàn tất, dung lượng thực tế và thời gian đưa ứng dụng trở lại. Không lấy dung lượng đang dùng trong filesystem làm dự toán duy nhất; hãy đo dung lượng backup sau một giai đoạn chạy thử.

### 4.3. Dữ liệu trải trên nhiều volume

Volume group có thể chứa boot volume và block volume, hỗ trợ bản sao tại cùng thời điểm với mức **crash-consistent**. Trạng thái này tương tự khi hệ thống dừng đột ngột; nó không tự bảo đảm mọi giao dịch ứng dụng đã hoàn tất. [Nguồn: Working with Volume Groups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/volumegroups.htm).

Ví dụ, nội dung file nằm ở volume A và metadata ở volume B. Backup từng volume vào thời điểm khác nhau có thể tạo bản sao với metadata tham chiếu tới nội dung chưa tồn tại.

Nếu cần application-consistent:

1. Xác định cơ chế backup được ứng dụng hỗ trợ.
2. Tạm ngừng nhận ghi hoặc dùng checkpoint/quiesce phù hợp.
3. Đẩy dữ liệu xuống lớp lưu trữ theo hướng dẫn ứng dụng.
4. Phối hợp tạo điểm backup bằng quy trình đã kiểm thử.
5. Cho phép ghi trở lại, xử lý cả trường hợp lỗi hoặc timeout.
6. Kiểm chứng trạng thái sau phục hồi.

Flush filesystem đơn lẻ không chứng minh database đã nhất quán. Với Oracle Database, lấy cơ chế database làm trọng tâm của chiến lược bảo vệ dữ liệu.

### 4.4. Lịch chạy, retention và bản sao ngoài region

Dùng chính sách do người dùng định nghĩa khi cần điều chỉnh lịch, retention hoặc tự động sao chép sang region khác. Lịch bắt đầu không được bảo đảm chính xác; OCI cũng lưu ý việc sao chép backup hằng ngày sang region đích có thể mất tới 24 giờ. Vì vậy daily copy chưa chứng minh RPO 24 giờ khi mất region. [Nguồn: Backup Policies](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/schedulingvolumebackups.htm).

Một phương án khởi đầu cho máy chủ ít biến động:

| Nhóm bản sao | Mục đích | Lưu giữ minh họa |
| --- | --- | --- |
| Hằng ngày | Lỗi vận hành gần đây | 14 ngày |
| Hằng tuần | Lỗi phát hiện muộn | 8 tuần |
| Hằng tháng | Mốc kiểm tra nội bộ | 12 tháng |
| Trước thay đổi lớn | Quay lui bản vá hoặc nâng cấp | Đến khi nghiệm thu thay đổi |
| Region dự phòng | Mất region nguồn | Theo yêu cầu DR riêng |

Đây là đề xuất thiết kế, không phải lịch mặc định của OCI. Chọn lịch theo tốc độ thay đổi và giới hạn của cơ chế đang dùng.

Ghi rõ backup dài hạn do policy quản lý hay tạo thủ công, ai chịu trách nhiệm hết hạn và điều gì xảy ra khi xóa nguồn. Không dùng việc xóa tài nguyên nguồn thay cho quản lý vòng đời backup.

## 5. Chiến lược cho Object Storage và File Storage

### 5.1. Object Storage: lịch sử phiên bản và bảo vệ chống xóa

Khi bật versioning, ghi đè tạo phiên bản mới; xóa object thông thường tạo delete marker. Xóa trực tiếp một version vẫn có thể làm mất vĩnh viễn phiên bản đó. Vì vậy versioning cần đi cùng kiểm soát quyền xóa và vòng đời phiên bản. [Nguồn: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Có thể tách hai nhu cầu:

- Bucket vận hành cần nhiều phiên bản để phục hồi thao tác nhầm.
- Bucket lưu bản sao độc lập cần giữ nội dung không đổi trong thời hạn xác định.

Retention rule ngăn sửa hoặc xóa object trong thời gian bảo vệ. Không thể bật đồng thời versioning và retention rule đang hoạt động trên cùng bucket. Khóa retention rule là thao tác không thể đảo ngược; cần thử chính sách trên dữ liệu thử trước khi áp dụng. [Nguồn: Object Storage Data Retention Rules](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

Với bản sao độc lập, dùng tên hoặc prefix theo thời điểm:

~~~text
orders-backup/2026-11-21T020000Z/manifest.json
orders-backup/2026-11-21T020000Z/attachments/...
~~~

Manifest nên ghi danh sách object, phiên bản nguồn nếu có, kích thước, checksum phù hợp và điểm nghiệp vụ liên quan. Không đưa thông tin xác thực hoặc khóa bí mật vào manifest.

### 5.2. Replication không tự cung cấp lịch sử độc lập

Object Storage replication là bất đồng bộ. Object tải lên sau khi tạo policy mới thuộc luồng sao chép; dữ liệu có trước đó không tự được chuyển. Thao tác xóa ở nguồn có thể truyền sang đích; lịch sử phiên bản cũ không được replication sao chép. [Nguồn: Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm), [Versioning và các tính năng liên quan](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Từ các đặc tính trên, kế hoạch cần:

1. Kiểm kê và chuyển dữ liệu có sẵn bằng quy trình riêng.
2. Đối chiếu danh sách và nội dung sau lần chuyển ban đầu.
3. Giữ lịch sử độc lập nếu cần quay lui trước lần xóa hoặc ghi sai.
4. Thử lấy dữ liệu tại nơi dự phòng khi không truy cập được nguồn.

Bucket replica hiện hành và kho lưu lịch sử đảm nhiệm hai chức năng khác nhau.

### 5.3. Storage tier ảnh hưởng RTO

Object ở Archive phải được restore trước khi tải xuống. Cộng thời gian này vào RTO, cùng với truyền dữ liệu và kiểm tra nội dung. [Nguồn: Overview of Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Archive/Concepts/archivestorageoverview.htm).

Thiết kế lifecycle theo nhóm dữ liệu. Không chuyển toàn bộ backup mới sang Archive chỉ vì đơn giá lưu trữ thấp. Có thể giữ các điểm gần đây ở lớp truy cập nhanh, đưa mốc cũ ít dùng sang lớp lưu dài hạn và kiểm thử cả hai đường khôi phục.

### 5.4. File Storage: snapshot và bảo vệ vị trí

Snapshot File Storage là góc nhìn nhất quán tại một thời điểm của toàn file system, sử dụng copy-on-write. Có thể dùng snapshot theo chính sách để tự động hóa. [Nguồn: Managing Snapshots](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/managingsnapshots.htm).

Ví dụ, chụp mỗi bốn giờ và giữ bảy ngày giúp phục hồi lỗi xóa gần đây nhưng không mặc nhiên đáp ứng RPO một giờ. Lịch sử trong cùng phạm vi nguồn cũng chưa chứng minh phục hồi được khi mất region.

Khi cần bảo vệ vị trí, xem xét File Storage replication tới vị trí hỗ trợ và phương án sao lưu độc lập theo yêu cầu. Replication này bất đồng bộ; cần theo dõi điểm sao chép hoàn tất và có quy trình sử dụng dữ liệu đích. [Nguồn: Replication Technologies](https://docs.oracle.com/en/solutions/mid-tier-replication-oci-dr-arch/replication-technologies1.html).

Sau phục hồi file, kiểm tra nội dung, quyền, UID/GID, cấu hình export và khả năng mount. File đúng checksum nhưng ứng dụng không đọc được vẫn chưa hoàn tất khôi phục.

## 6. Chiến lược cho Oracle Database

### 6.1. Xác định mô hình quản lý

| Mô hình | Trọng tâm |
| --- | --- |
| Oracle Database tự quản trên Compute | DBA thiết kế RMAN, log, metadata, khóa và tự động hóa |
| Base Database hoặc Exadata dùng backup tích hợp | Cơ chế được hỗ trợ, destination, policy và giám sát |
| Autonomous Database | Khả năng backup/recovery của đúng mô hình triển khai |
| Engine khác trên OCI | Cơ chế backup và log riêng của engine |

Tên dịch vụ, kiểu triển khai và phiên bản có thể làm thay đổi khả năng bảo vệ. Không áp retention hoặc cách restore của một dịch vụ cho dịch vụ khác.

### 6.2. Database tự quản: bảo vệ cả dữ liệu và thông tin phục hồi

Với database đang mở, chiến lược RMAN phải xét datafile, archived redo log, control file và SPFILE. Khả năng phục hồi tới một thời điểm phụ thuộc vào backup phù hợp và các log cần thiết; bản sao datafile đơn lẻ không chứng minh khả năng này. [Nguồn: RMAN Backup Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-backup-concepts.html).

Kế hoạch phải trả lời:

- Database dùng chế độ và cấu hình log nào?
- Lịch backup nền và bảo vệ archived log có đáp ứng RPO không?
- Bản sao ra khỏi máy và vùng lỗi nguồn bằng cách nào?
- Control file, SPFILE, password file và cấu hình kết nối ở đâu?
- Nếu có TDE, wallet/keystore và quy trình mở khóa còn dùng được không?
- RMAN repository hoặc recovery catalog, nếu dùng, được bảo vệ thế nào?
- Chính sách xóa log có xét nhu cầu phục hồi và các bên tiêu thụ log không?

Không xóa archived log chỉ để giải phóng đĩa trước khi xác minh yêu cầu phục hồi. Không đặt bản sao duy nhất trên cùng máy Compute chứa database nguồn.

Data Pump export hữu ích cho di chuyển hoặc phục hồi một số đối tượng logic. Nó không tự thay thế kế hoạch phục hồi vật lý và log của toàn database.

### 6.3. Dịch vụ được quản lý: xác nhận backup đã được cấu hình

Với dịch vụ hỗ trợ Autonomous Recovery Service, có thể bật automatic backups, chọn destination và protection policy. Cơ chế quản lý gửi backup nền rồi các backup incremental; policy xác định retention. [Nguồn: About Using Recovery Service to Backup and Recover Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/recovery-service/doc/about-automatic-backup-recovery.html).

| Mục cần ghi | Điều phải xác nhận |
| --- | --- |
| Trạng thái | Đã bật cho đúng database và có lần hoàn tất thực tế |
| Destination | Dịch vụ, vị trí và khả năng truy cập khi có sự cố |
| Protection policy | Recovery window đáp ứng yêu cầu |
| Bảo vệ redo | Tùy chọn đang dùng và độ trễ thực tế |
| Khi terminate | Backup giữ bao lâu và phục hồi bằng cách nào |
| Phương thức restore | Tạo database mới hoặc cách được dịch vụ hỗ trợ |
| Theo dõi | Health, lần thành công, lần lỗi, data loss exposure |

Recovery Service có tùy chọn giữ backup sau terminate; real-time data protection cần kiểm tra riêng và có chi phí bổ sung. Oracle cũng cảnh báo vận hành song song backup tới hai destination có thể gây rủi ro mất dữ liệu khi phục hồi. Không tự ghép script backup vào cơ chế quản lý nếu chưa xác nhận cách phối hợp được hỗ trợ. [Nguồn: Enable Automatic Backups to Recovery Service](https://docs.oracle.com/en-us/iaas/recovery-service/doc/enable-automatic-backup.html).

### 6.4. Autonomous Database: dùng thông số thực tế

Autonomous Database có backup tự động và cơ chế recovery do dịch vụ cung cấp. Với mô hình serverless trong tài liệu Oracle, retention và cách tính chi phí backup có khác biệt theo compute model. Không mặc định mọi database có cùng cấu hình và chi phí. [Nguồn: About Backup and Recovery on Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-intro.html).

Ghi lại retention đang cấu hình, điểm phục hồi có sẵn, lựa chọn lưu dài hạn và cơ chế ngoài region nếu cần. Thử khôi phục rồi kết nối từ ứng dụng thử: database hoạt động chưa chứng minh wallet kết nối, secret, DNS và quyền của ứng dụng đều đúng.

## 7. Phạm vi bảo vệ, IAM và khóa mã hóa

### 7.1. Dùng nguyên tắc nhiều bản sao có kiểm chứng

Có thể dùng tư duy 3-2-1-1-0 làm khung thiết kế:

- Nhiều bản sao dữ liệu quan trọng.
- Các cơ chế hoặc miền lỗi đủ độc lập.
- Một bản sao ngoài vị trí nguồn.
- Một bản sao cô lập hoặc có bảo vệ bất biến phù hợp.
- Không còn lỗi phục hồi chưa xử lý trong các lần kiểm thử gần nhất.

Đây là nguyên tắc thiết kế, không phải tính năng OCI bật bằng một tùy chọn. Hai bucket cùng region và cùng nhóm quản trị toàn quyền có thể cùng chịu sự cố địa lý hoặc lạm dụng quyền.

Compartment giúp tổ chức và phân quyền; nó không tạo vùng địa lý độc lập. Chuyển backup sang compartment khác cũng chưa tạo bảo vệ chống xóa nếu danh tính bị chiếm quyền vẫn quản trị được cả hai nơi.

### 7.2. Tách nhiệm vụ theo thao tác

| Vai trò | Quyền cần xem xét | Điều cần kiểm soát |
| --- | --- | --- |
| Tác nhân backup | Đọc nguồn, tạo bản sao cần thiết | Không xóa lịch sử vượt nhu cầu |
| Người restore | Đọc backup, tạo tài nguyên ở nơi phục hồi | Không mặc định sửa production |
| Quản lý retention | Thay đổi policy trong phạm vi giao | Tách khỏi tác nhân vận hành thường ngày |
| Quản lý khóa | Quản lý vòng đời khóa | Kiểm soát thao tác làm mất khả năng giải mã |
| Kiểm tra | Xem cấu hình, trạng thái và Audit | Không cần sửa hoặc xóa dữ liệu |

Viết IAM theo resource type, compartment và thao tác thực tế. Quyền tạo backup không đồng nghĩa đủ quyền restore; còn có thể cần tạo Compute, volume, cấu hình mạng và dùng khóa.

Với tự động hóa, dùng danh tính workload được hỗ trợ như instance principal hoặc resource principal khi phù hợp. Không nhúng API key cá nhân vào mã nguồn hoặc manifest.

### 7.3. Kiểm tra phụ thuộc khóa

Runbook cần xác định:

1. Backup dùng khóa Oracle quản lý hay khóa khách hàng quản lý?
2. Khóa để đọc backup ở nơi phục hồi là khóa nào?
3. Principal phục hồi có quyền cần thiết không?
4. Dữ liệu phục hồi cần cấu hình mã hóa riêng không?
5. Vô hiệu hóa hoặc xóa khóa có ảnh hưởng lịch sử còn phải giữ không?

Với scheduled cross-region backup copy của Block Volume, Vault key nguồn không tự sao chép sang đích. Nếu dùng khóa khách hàng quản lý cho bản sao đích, phải cấu hình khóa hợp lệ tại region đích. [Nguồn: Scheduling Volume Backup Copies Across Regions](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/schedulingvolumebackups.htm#Scheduling_Volume_Backup_Copies_Across_Regions).

Không gói secret giải mã cùng backup để mọi người đọc được backup đều lấy được secret. Bảo vệ bí mật bằng cơ chế phù hợp và thử quy trình truy cập khẩn cấp.

## 8. Ví dụ chiến lược cho ứng dụng quản lý đơn hàng

### 8.1. Bối cảnh và mục tiêu

Giả sử ứng dụng có hai máy Compute dựng lại được bằng Terraform và image; Oracle Database được quản lý lưu đơn hàng; bucket lưu tài liệu bằng tên không ghi đè; File Storage chứa báo cáo có thể tạo lại.

| Phạm vi | RPO mục tiêu | RTO mục tiêu |
| --- | --- | --- |
| Đơn hàng khi gặp sự cố cục bộ | 15 phút | 2 giờ |
| Dịch vụ gồm đơn hàng và tài liệu | 1 giờ | 4 giờ |
| Dịch vụ khi mất region | 48 giờ | 24 giờ |

Đây là yêu cầu giả định của ví dụ, chưa phải kết quả đo hoặc cam kết dịch vụ.

### 8.2. Chuyển yêu cầu thành phương án

| Thành phần | Phương án ban đầu | Bằng chứng cần thu |
| --- | --- | --- |
| Compute | Image và IaC có phiên bản; backup boot khi cần giữ trạng thái | Thời gian tạo máy, triển khai, health check |
| Database | Backup tích hợp, window 35 ngày nếu policy hỗ trợ; bảo vệ redo đáp ứng mục tiêu | Điểm phục hồi khả dụng, thời gian database dùng được |
| Tài liệu | Versioning ở bucket vận hành; bản sao lịch sử độc lập mỗi giờ | Độ trễ, manifest, kiểm tra nội dung |
| Báo cáo | Dựng lại từ dữ liệu đã phục hồi | Thời gian và khả năng sử dụng tối thiểu |
| Ngoài region | Cơ chế riêng cho từng dịch vụ | Khôi phục hoàn toàn không dùng nguồn |

Retention 35 ngày là lựa chọn thiết kế cần ánh xạ sang policy hỗ trợ. Nếu database chưa có phương án phục hồi truy cập được khi mất region, phần DR toàn dịch vụ vẫn thiếu dù boot volume và object đã được chuyển.

### 8.3. Chọn điểm khôi phục chung

Mỗi giờ, ứng dụng có thể ghi checkpoint nghiệp vụ gồm thời gian UTC, tập tài liệu đã tải lên hoàn tất và định danh giao dịch tương ứng. Quy trình backup đưa manifest checkpoint vào kho lịch sử.

Khi khôi phục:

1. Chọn checkpoint có đủ tài liệu tại nơi phục hồi.
2. Chọn điểm database tương thích hoặc dùng quy trình đối soát đã thiết kế.
3. Kiểm tra không có đơn hàng tham chiếu tài liệu bị thiếu.
4. Đối soát giao dịch với hệ thống ngoài, sử dụng idempotency key.
5. Chỉ mở ghi khi tính nhất quán đạt yêu cầu.

Cơ chế này phải được triển khai ở ứng dụng; storage backup không tự tạo checkpoint nghiệp vụ. Database có RPO 15 phút nhưng tài liệu chỉ phục hồi đến một giờ trước thì chưa thể tuyên bố toàn dịch vụ có RPO 15 phút.

## 9. Tự động hóa và giám sát khả năng khôi phục

### 9.1. Luồng vận hành

~~~mermaid
flowchart TD
    A["Kiểm kê và phân mức bảo vệ"] --> B["Policy hoặc bộ lập lịch"]
    B --> C["Backup bằng cơ chế phù hợp"]
    C --> D["Kiểm tra hoàn tất và điểm dữ liệu"]
    D --> E["Sao chép tới nơi dự phòng nếu cần"]
    E --> F["Đối chiếu bản sao và quyền truy cập"]
    F --> G["Khôi phục trong môi trường cô lập"]
    G --> H["Đo RPO, RTO và kiểm tra nghiệp vụ"]
    D --> I["Cảnh báo lỗi hoặc quá hạn"]
    F --> I
    G --> I
~~~

Ưu tiên lịch và retention tích hợp khi đáp ứng yêu cầu. Với phần cần phối hợp riêng, lưu mã yêu cầu, trạng thái và định danh tài nguyên để tránh tạo trùng khi retry.

Không retry vô hạn. Timeout phía client không chứng minh thao tác OCI đã bị hủy; kiểm tra trạng thái trước khi tạo bản sao mới.

### 9.2. Ví dụ OCI CLI tạo backup volume group

Ví dụ Bash dưới đây dành cho môi trường thực hành. Cần OCI CLI đã cấu hình, quyền phù hợp và volume group chứa đúng các volume. Lệnh tạo backup thủ công, chưa thiết lập lịch hoặc cơ chế application-consistent.

~~~bash
set -euo pipefail

OCI_REGION='ap-singapore-1'
VOLUME_GROUP_OCID='ocid1.volumegroup.oc1...THAY_BANG_OCID_THUC'
BACKUP_NAME="orders-before-change-$(date -u +%Y%m%dT%H%M%SZ)"

BACKUP_OCID="$(
  oci bv volume-group-backup create \
    --region "$OCI_REGION" \
    --volume-group-id "$VOLUME_GROUP_OCID" \
    --display-name "$BACKUP_NAME" \
    --type INCREMENTAL \
    --wait-for-state AVAILABLE \
    --max-wait-seconds 7200 \
    --query 'data.id' \
    --raw-output
)"

oci bv volume-group-backup get \
  --region "$OCI_REGION" \
  --volume-group-backup-id "$BACKUP_OCID"
~~~

Lệnh hỗ trợ FULL/INCREMENTAL và chờ AVAILABLE. Nếu hết thời gian chờ, kiểm tra thao tác hiện tại trước khi retry. AVAILABLE chỉ kiểm tra trạng thái tài nguyên; vẫn cần thử restore. [Nguồn: OCI CLI volume-group-backup create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/bv/volume-group-backup/create.html).

Lưu OCID vào sổ theo dõi được bảo vệ, đặt quy tắc hết hạn cho bản sao thủ công và thực hiện phục hồi thử bằng quy trình dịch vụ.

### 9.3. Các chỉ báo cần theo dõi

| Chỉ báo | Ý nghĩa |
| --- | --- |
| Tài nguyên thiếu policy hoặc backup | Lỗ hổng bao phủ |
| Tuổi điểm khôi phục mới nhất sử dụng được | Nguy cơ vi phạm RPO |
| Tuổi điểm khôi phục ở region đích | Nguy cơ vi phạm RPO khi mất region |
| Backup lỗi hoặc chạy quá lâu | Cần xử lý trước khi mất thêm cửa sổ bảo vệ |
| Dung lượng và chi phí theo lớp | Retention hoặc thay đổi dữ liệu vượt dự toán |
| Lần restore thử thành công gần nhất | Độ mới của bằng chứng phục hồi |
| Thay đổi IAM, policy, retention hoặc khóa | Nguy cơ mất dữ liệu hoặc khả năng truy cập |

Kết hợp Events/Notifications cho sự kiện hỗ trợ, Monitoring cho metric có sẵn và bộ kiểm tra định kỳ cho phần còn thiếu. Phải phát hiện cả **backup không hề được tạo**; cảnh báo lỗi tác vụ không bắt được tài nguyên chưa được gán policy.

Ngưỡng cảnh báo nên đến trước giới hạn kinh doanh. Nếu RPO là một giờ, cảnh báo ở 45 phút có thể tạo thời gian xử lý; cần điều chỉnh theo độ trễ thu thập và tốc độ khắc phục thực tế.

## 10. Runbook khôi phục và diễn tập

### 10.1. Khôi phục theo thứ tự phụ thuộc

1. **Khoanh vùng:** xác định thời điểm lỗi và những backup có thể đã chứa dữ liệu lỗi.
2. **Chọn điểm phục hồi:** kiểm tra manifest và sự phù hợp giữa các thành phần.
3. **Chuẩn bị môi trường:** IAM, khóa, VCN, subnet, DNS, quota và Compute.
4. **Phục hồi dữ liệu:** database, volume, file hoặc object theo cơ chế riêng.
5. **Triển khai ứng dụng:** chọn phiên bản tương thích schema và dữ liệu.
6. **Kiểm tra:** toàn vẹn, quyền truy cập, kết nối và quy tắc nghiệp vụ.
7. **Đưa vào phục vụ:** điều chỉnh endpoint, chạy giao dịch kiểm chứng và theo dõi.
8. **Bảo vệ lại:** bật lịch backup cho tài nguyên mới, xác nhận chủ sở hữu.

Môi trường diễn tập nên cô lập với endpoint production. Chặn tác vụ gửi thông báo khách hàng, xử lý thanh toán hoặc ghi sang hệ thống thật; dùng endpoint thử khi cần kiểm tra tích hợp.

### 10.2. Đo RTO của dịch vụ

~~~text
T0: Bắt đầu sự cố giả định
T1: Phát hiện và quyết định khôi phục
T2: Môi trường đích sẵn sàng
T3: Hoàn tất restore/recover dữ liệu
T4: Hoàn tất kiểm tra ứng dụng
T5: Dịch vụ đạt mức hoạt động đã thống nhất

RTO quan sát được = T5 - T0
Mức mất dữ liệu quan sát được = T0 - điểm dữ liệu đã phục hồi
~~~

Nếu diễn tập với môi trường đã dựng sẵn, ghi rõ phần thời gian loại khỏi phép đo. Kết quả chỉ đại diện cho điều kiện đã thử.

Restore database mất 40 phút chưa chứng minh RTO 40 phút nếu còn 70 phút dựng mạng và 30 phút kiểm tra nghiệp vụ.

### 10.3. Kiểm thử nhiều lớp

| Lớp kiểm thử | Ví dụ | Kết luận |
| --- | --- | --- |
| Trạng thái | Backup hoàn tất, đúng metadata/vị trí | Đã tạo tài nguyên dự kiến |
| Khả năng đọc | Lấy thử object, kiểm tra bằng công cụ backup | Dữ liệu cần đọc có thể truy cập |
| Phục hồi kỹ thuật | Tạo volume, mount file system, restore database thử | Đường phục hồi hoạt động trong điều kiện thử |
| Nghiệp vụ | Đối chiếu đơn hàng, tài liệu, tổng tiền | Trạng thái phục hồi có thể dùng |
| Mất region | Dùng tài nguyên đích, không phụ thuộc nguồn | Đã kiểm chứng kịch bản DR cụ thể |

Với Oracle Database tự quản, RMAN hỗ trợ RESTORE ... VALIDATE để kiểm tra backup. Đây là lớp kiểm tra hữu ích nhưng không thay khôi phục thật và chạy ứng dụng. [Nguồn: RMAN VALIDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/VALIDATE.html).

Diễn tập theo mức quan trọng và sau thay đổi lớn về schema, mã hóa, IAM hoặc kiến trúc. Khi thất bại, ghi lỗi, người xử lý, hạn hoàn tất và phép thử lại.

## 11. Kiểm soát chi phí và dung lượng

~~~text
Chi phí dự kiến =
  lưu backup tại nguồn
  + lưu bản sao ở nơi dự phòng
  + truyền dữ liệu
  + truy xuất hoặc phục hồi
  + tài nguyên diễn tập
  + công cụ và công sức vận hành
~~~

Đây là mô hình dự toán; ánh xạ từng hạng mục sang cách tính phí của dịch vụ thực tế.

Các cách điều chỉnh:

- Dựng lại máy ứng dụng từ cấu hình có phiên bản để giảm dữ liệu phải bảo vệ.
- Phân lớp theo RPO/RTO, tránh áp retention dài cho mọi dữ liệu.
- Theo dõi tăng trưởng object version và snapshot.
- Chọn lifecycle theo thời gian truy xuất và yêu cầu lưu giữ.
- Giới hạn thời gian tồn tại môi trường diễn tập sau khi lưu kết quả.
- Theo dõi backup thủ công chưa có quy tắc hết hạn.
- Gắn tag ứng dụng, môi trường, chủ sở hữu và mức bảo vệ khi hỗ trợ.

Không dự toán chỉ bằng kích thước dữ liệu nhân số ngày. Tốc độ thay đổi, cách chia sẻ dữ liệu giữa các bản sao, phiên bản object, retention và nén đều có thể ảnh hưởng. Đo trong giai đoạn chạy thử rồi điều chỉnh.

Không xóa điểm khôi phục còn cần chỉ để đạt ngân sách tháng. Khi vượt chi phí, xem lại lớp lưu trữ, dữ liệu tái tạo được, tần suất và thời gian giữ cùng yêu cầu kinh doanh.

## 12. Hồ sơ bàn giao chiến lược backup

| Hồ sơ | Nội dung tối thiểu |
| --- | --- |
| Ma trận bảo vệ | Tài nguyên, chủ sở hữu, RPO/RTO và kịch bản |
| Chính sách thực thi | Cơ chế, lịch, múi giờ, retention và nơi lưu |
| Bản đồ phụ thuộc | Mạng, IAM, khóa, secret, phiên bản và quota |
| Runbook | Điểm khôi phục, thứ tự, kiểm tra và mở lại dịch vụ |
| Theo dõi | Bao phủ, độ mới, bản sao đích, lỗi và chi phí |
| Bằng chứng diễn tập | Backup đã dùng, thời gian, kết quả kỹ thuật/nghiệp vụ |
| Vòng đời | Xóa nguồn, đổi chủ sở hữu, hết hạn hoặc đóng ứng dụng |

Ví dụ một bản ghi chính sách nội bộ:

~~~yaml
workload: orders-production
owner: platform-team
scope:
  - application-compute
  - oracle-database
  - object-attachments
targets:
  local:
    service_rpo_minutes: 60
    service_rto_minutes: 240
  regional:
    service_rpo_hours: 48
    service_rto_hours: 24
controls:
  application_configuration: versioned-iac
  database_backup: service-managed
  attachment_history: independent-timestamped-copies
  restore_environment: isolated
verification:
  recovery_point_age: monitored
  regional_recovery: requires-successful-drill
~~~

Đây là mẫu mô tả kế hoạch, **không phải cấu hình OCI hoặc Terraform có thể áp dụng trực tiếp**. Các giá trị chỉ trở thành khả năng đã chứng minh khi được đối chiếu với tài nguyên thật, bản sao truy cập được và kết quả diễn tập. Người nhận bàn giao cần xác định được ngay: sẽ dùng bản sao nào, phục hồi ở đâu, bằng danh tính nào và dựa vào kiểm tra nào để cho phép ứng dụng hoạt động trở lại.
