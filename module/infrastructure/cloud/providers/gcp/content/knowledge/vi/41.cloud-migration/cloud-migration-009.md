# Transfer Appliance và bài toán dữ liệu khối lượng lớn

## 1. Mục tiêu bài học và bối cảnh

Trong quá trình **di chuyển lên Google Cloud**, doanh nghiệp không chỉ chuyển máy ảo hoặc ứng dụng mà còn phải đưa các tập dữ liệu nhiều chục đến hàng trăm terabyte từ trung tâm dữ liệu hiện tại lên đám mây. Khi băng thông đường truyền bị giới hạn, chỉ riêng việc tải dữ liệu qua Internet có thể kéo dài hàng tuần hoặc hàng tháng, ảnh hưởng tới lịch chuyển đổi hệ thống.

**Google Cloud Transfer Appliance** là thiết bị lưu trữ dung lượng lớn do Google cung cấp để tiếp nhận dữ liệu tại địa điểm của khách hàng, sau đó chuyển dữ liệu vào **Cloud Storage**. Với chế độ **offline**, khách hàng sao chép dữ liệu vào thiết bị, niêm phong và gửi lại Google; Google nhập dữ liệu vào bucket đích. Một số thiết bị có **online mode**, cho phép truyền dữ liệu từ thiết bị lên Cloud Storage qua mạng khi đang sử dụng.

Bài học thuộc mạch kiến thức **CLOUD_PROVIDERS_GCP**: từ tổ chức project, IAM, VPC, dịch vụ lưu trữ, cơ sở dữ liệu đến triển khai và theo dõi độ tin cậy, chi phí. Ở đây, Transfer Appliance là phương tiện **đưa dữ liệu ban đầu vào Cloud Storage** để các dịch vụ như Dataflow, BigQuery, GKE hoặc Cloud Run có thể tiếp tục khai thác theo kiến trúc phù hợp.

Sau bài này, người học có thể:

- Giải thích nguyên lý hoạt động và sự khác nhau giữa chế độ offline và online.
- Ước lượng thời gian chuyển dữ liệu qua mạng, thời gian nạp vào thiết bị và nhu cầu dung lượng.
- Chọn Transfer Appliance, Storage Transfer Service hoặc công cụ dòng lệnh theo bài toán thực tế.
- Lập kế hoạch bảo mật, thao tác nhận thiết bị, sao chép, niêm phong, vận chuyển và kiểm chứng dữ liệu.
- Nhận diện giới hạn về file, vị trí cung cấp dịch vụ, tính nhất quán dữ liệu và thời điểm chuyển đổi ứng dụng.

## 2. Tại sao dữ liệu lớn trở thành nút thắt khi di chuyển?

Giả sử doanh nghiệp có **180 TB** ảnh, video, nhật ký và tệp lưu trữ trên NAS nội bộ. Đường truyền dành riêng cho việc chuyển dữ liệu đạt danh nghĩa **200 Mbps** và hiệu suất truyền hữu ích trung bình khoảng **75%**.

Thời gian tối thiểu theo mô hình đơn giản:

~~~text
Thời gian (ngày)
  = Dung lượng (TB) × 10^12 (byte/TB) × 8 (bit/byte)
    / [Băng thông (Mbps) × 10^6 × Hiệu suất × 86.400 (giây/ngày)]

Với 180 TB, 200 Mbps và hiệu suất 0,75:
  = 180 × 10^12 × 8 / (200 × 10^6 × 0,75 × 86.400)
  ≈ 111 ngày.
~~~

Đây chỉ là **ước lượng truyền thuần túy**. Thời gian thực còn bị tác động bởi giới hạn tốc độ đầu đọc, số lượng file, thao tác xác thực, độ trễ, mất gói, thời gian chạy lại khi lỗi, giờ cao điểm và dữ liệu tiếp tục thay đổi trong thời gian chuyển. Nếu đường truyền đó còn phục vụ ứng dụng vận hành, không thể mặc định dùng toàn bộ 200 Mbps để tải dữ liệu.

Đối với **offline Transfer Appliance**, cùng 180 TB được sao chép qua mạng nội bộ vào thiết bị. Nếu tốc độ ghi **hữu ích thực đo** là 500 MB/s, riêng thời gian truyền dữ liệu về mặt lý thuyết khoảng:

~~~text
180 × 10^12 byte / (500 × 10^6 byte/giây) / 86.400
≈ 4,17 ngày.
~~~

Sau đó vẫn phải cộng thời gian cấp phát thiết bị, chuẩn bị, kiểm tra, giao nhận, Google nhập dữ liệu và xác minh. Không được lấy 4,17 ngày làm cam kết hoàn thành toàn bộ dự án.

**Ý tưởng cốt lõi:** truyền nhanh qua mạng LAN tới thiết bị, sau đó đưa dung lượng lớn tới Google bằng vận chuyển vật lý; hiệu quả phụ thuộc vào toàn bộ chuỗi công việc chứ không riêng dung lượng hay băng thông.

## 3. Transfer Appliance hoạt động như thế nào?

~~~mermaid
flowchart LR
    A["NAS / file server / kho lưu trữ tại chỗ"] -->|"NFS, SMB hoặc SCP/SFTP"| B["Transfer Appliance"]
    B -->|"Offline: niêm phong và gửi thiết bị"| C["Cơ sở tiếp nhận của Google"]
    C -->|"Nhập dữ liệu an toàn"| D[("Cloud Storage bucket")]
    B -.->|"Online: truyền qua mạng nếu được cấu hình"| D
    D --> E["Xác minh dữ liệu, xử lý và khai thác trên Google Cloud"]
~~~

Với **offline mode**, luồng tổng quát gồm:

1. Khảo sát bộ dữ liệu, kiểm tra nơi đặt thiết bị và yêu cầu mẫu thiết bị.
2. Tạo hoặc xác định project, bucket Cloud Storage đích và chuẩn bị quyền truy cập.
3. Nhận thiết bị, kiểm tra tính toàn vẹn vật lý và thực hiện **attestation** trước khi kết nối vào mạng nội bộ.
4. Kết nối mạng, cấu hình giao thức và sao chép dữ liệu vào thiết bị.
5. Đối soát số file, dung lượng, lỗi sao chép; chạy lệnh kết thúc phiên ghi dữ liệu.
6. Niêm phong, bàn giao cho bên vận chuyển theo chỉ dẫn của Google.
7. Google kiểm tra thiết bị, nhập dữ liệu vào bucket, xuất log kết quả và xử lý xóa dữ liệu trên thiết bị.
8. Khách hàng kiểm chứng kết quả trên Cloud Storage rồi mới quyết định ngừng hệ thống lưu trữ nguồn.

**Điểm phân biệt quan trọng:** Transfer Appliance không tự biến dữ liệu tệp thành cơ sở dữ liệu, không di chuyển máy ảo thành Compute Engine, không duy trì đồng bộ liên tục theo kiểu replication của ứng dụng và không tự bảo toàn mọi ngữ nghĩa của file system (ACL, symbolic link, hard link hoặc thuộc tính POSIX) trong object storage.

### Các dạng thiết bị và khả năng chính

Theo thông số Transfer Appliance 4.0 được Google công bố tháng 11/2026:

| Dòng thiết bị | Dung lượng dữ liệu mã hóa có thể sử dụng tối đa | Ghi chú |
| --- | ---: | --- |
| TA40 / TA40F | 40 TB | Bản đặt rack hoặc dạng độc lập |
| TA300 / TA300F | 300 TB | Bản đặt rack hoặc dạng độc lập |
| Các đơn hàng nhiều thiết bị | Phụ thuộc số thiết bị được Google xác nhận | Có thể chia tập dữ liệu để sao chép song song |

Thiết bị sử dụng SSD; cổng dữ liệu có RJ45 10 Gbps và QSFP28 100 Gbps **trên mẫu rack tương ứng**. Thông số cổng thể hiện khả năng kết nối, **không đồng nghĩa** đạt tốc độ ghi thực tế tương đương. Cần xem xét nguồn đọc, thiết bị chuyển mạch, cấu trúc file, giao thức, số luồng và tốc độ xử lý.

Trước khi đặt hàng, kiểm tra **mẫu đang được cung cấp, dung lượng còn khả dụng, kích thước, điện 100–240 V/50–60 Hz, yêu cầu làm mát, không gian đặt và giới hạn giao nhận**. Dung lượng định danh là mức tối đa; nên dành khoảng trống dự phòng theo kết quả khảo sát.

### Offline mode và online mode

| Tiêu chí | Offline | Online |
| --- | --- | --- |
| Đường truyền tới Cloud Storage | Không cần dùng Internet để tải toàn bộ dữ liệu từ thiết bị | Cần kết nối mạng tới Google Cloud |
| Thời điểm dữ liệu vào Cloud Storage | Sau khi Google nhận và xử lý thiết bị | Thiết bị đẩy dần dữ liệu lên Cloud Storage |
| Nơi giữ dữ liệu tạm thời | Ổ lưu trữ của thiết bị cho tới khi hoàn tất và gửi trả | Ổ lưu trữ của thiết bị dùng làm vùng đệm; dữ liệu được xóa khỏi vùng đệm sau khi truyền thành công |
| Phù hợp | Dữ liệu rất lớn, đường truyền hạn chế hoặc không ổn định | Muốn nhập dần, tận dụng kết nối mạng đang có |
| Lưu ý vận hành | Có bước niêm phong, vận chuyển, nhập dữ liệu sau khi nhận | Cần cấu hình quyền, tài khoản dịch vụ và kết nối trực tuyến |

Khi **đặt loại thiết bị có khả năng online**, có thể chuyển giữa online/offline theo hướng dẫn. Thiết bị **được đặt chỉ cho offline** không thể tự bật online mode sau khi nhận. Việc chọn chế độ phải được xác định từ giai đoạn đặt hàng.

## 4. Khi nào nên chọn Transfer Appliance?

Không có một ngưỡng TB duy nhất bảo đảm Transfer Appliance tốt hơn mọi phương án. Google gợi ý đây là lựa chọn phù hợp khi **tải dữ liệu qua mạng cần hơn một tuần**, đồng thời vị trí khách hàng được hỗ trợ.

| Tình huống | Công cụ nên đánh giá trước | Lý do |
| --- | --- | --- |
| Một lượng nhỏ dữ liệu từ máy cục bộ | Google Cloud CLI, ví dụ gcloud storage | Đơn giản, ít bước thiết lập |
| Dữ liệu từ NAS/on-premises, mạng ổn định, cần đồng bộ định kỳ | Storage Transfer Service và agent | Có thể thực hiện truyền qua mạng và đồng bộ thay đổi |
| Dữ liệu từ Amazon S3 hoặc Azure Blob | Storage Transfer Service | Luồng chuyển object giữa dịch vụ cloud |
| Hàng chục/hàng trăm TB tại địa điểm băng thông yếu | Transfer Appliance offline | Giảm phụ thuộc vào đường Internet cho giai đoạn nhập dữ liệu lớn |
| Dữ liệu lớn muốn đẩy lên Cloud Storage trong khi đang sao chép | Transfer Appliance online | Kết hợp sao chép nội bộ với truyền trực tuyến |
| Cơ sở dữ liệu đang nhận giao dịch | Dịch vụ/mô hình migration của cơ sở dữ liệu tương ứng | Cần nhất quán giao dịch, đồng bộ thay đổi và cutover có kiểm soát |

**Bài toán đánh giá phải có đủ bốn trục:**

- **Dung lượng và phân bố file:** TB, số file, kích thước điển hình, tệp nhỏ, độ sâu thư mục, dung lượng tăng thêm.
- **Năng lực truyền:** tốc độ outbound thực tế, giới hạn giờ cao điểm, tốc độ đọc từ nguồn, hiệu suất LAN.
- **Thời hạn chuyển đổi:** ngày phải đưa dữ liệu vào Cloud Storage và ngày phải chuyển ứng dụng.
- **Hạn chế vận hành:** địa điểm có nhận thiết bị hay không, yêu cầu kiểm soát vật lý, quy định dữ liệu, ngân sách.

### Công thức so sánh tổng thời gian

~~~text
T_online  = Thời gian truyền mạng + kiểm tra + đồng bộ dữ liệu phát sinh
T_offline = Thời gian đặt/nhận thiết bị
          + thời gian chép nguồn -> thiết bị
          + thời gian đối soát và finalize
          + thời gian vận chuyển
          + thời gian Google nhập Cloud Storage
          + thời gian xác minh và chuyển đổi
~~~

Dù Transfer Appliance nhanh hơn ở lần tải dữ liệu ban đầu, nếu trong thời gian vận chuyển có **một lượng lớn dữ liệu mới hoặc thay đổi**, nhóm dự án vẫn cần một **kế hoạch delta**: đóng băng nguồn theo một mốc, chuyển phần thay đổi bằng công cụ online phù hợp, hoặc thiết kế một lần sao chép bổ sung. Không được giả định thiết bị đang vận chuyển tự đồng bộ các thay đổi đó.

## 5. Khảo sát dữ liệu và lập kế hoạch dung lượng

Trước khi đặt thiết bị, lập danh mục dữ liệu nguồn và người chịu trách nhiệm cho từng tập dữ liệu:

| Thuộc tính cần thu thập | Câu hỏi xác minh |
| --- | --- |
| Dung lượng thực và dự báo | Hiện có bao nhiêu TB? Tăng bao nhiêu TB mỗi ngày? |
| Số lượng và phân bố file | Có hàng triệu file vài KB hay chủ yếu file vài GB? |
| Định dạng | Tệp thông thường, file nén, archive, snapshot, export từ DB hay symlink? |
| Yêu cầu nhất quán | Dữ liệu có bị ứng dụng sửa trong lúc sao chép không? |
| Phân loại và tuân thủ | Có dữ liệu nhạy cảm, hạn chế lưu trú dữ liệu hoặc cần kiểm soát giao nhận? |
| Khả năng truy cập | Tài khoản copy có quyền đọc tất cả đường dẫn cần thiết không? |
| Đích đến | Project, bucket, location, object prefix, lưu trữ và vòng đời dự kiến? |
| Tiêu chí nghiệm thu | Manifest nào là nguồn sự thật để đối soát sau chuyển? |

Ví dụ khảo sát cơ bản trên **máy nguồn Linux sử dụng GNU coreutils**:

~~~bash
# Dung lượng nguồn theo byte; kết quả chỉ phục vụ khảo sát.
du -sb /data/archive

# Đếm file thông thường (không đếm thư mục).
find /data/archive -type f -printf '.' | wc -c

# Kiểm tra riêng liên kết tượng trưng cần xử lý trước khi nhập object storage.
find /data/archive -type l -print
~~~

Nếu bộ dữ liệu có thay đổi khi copy, hãy chuẩn bị **snapshot nhất quán** hoặc một phương án tương đương trước khi bắt đầu. Không xem một lần quét dung lượng là bằng chứng rằng dữ liệu đã đứng yên.

### Giới hạn dữ liệu cần chú ý

Theo hướng dẫn quy trình Google Cloud Transfer Appliance 4.0:

- Tệp cần là **regular file** hoặc tệp ẩn kiểu Unix. Cần xử lý riêng symlink, special file và dữ liệu có ngữ nghĩa file system.
- File đơn lẻ phải **nhỏ hơn 5 TB** theo điều kiện được nêu trong quy trình Transfer Appliance; đồng thời phải đáp ứng giới hạn object của Cloud Storage.
- Tên file phải phù hợp quy tắc **Cloud Storage object naming**.
- Độ dài đường dẫn đối tượng tối đa được nêu là **1.024 byte**, kể cả object prefix tùy chọn.
- Thư mục rỗng không tự trở thành object trong bucket. Cloud Storage có mô hình **object**, không phải file system POSIX đầy đủ.
- Transfer Appliance **không tự bảo đảm kiểm tra các giới hạn tên file/kích thước khi copy**; dữ liệu không hợp lệ có thể không được Google nhập thành công.

Với số lượng file cực lớn, chi phí thao tác metadata và khởi tạo từng file có thể quan trọng hơn số TB. Có thể cân nhắc gom nhóm dữ liệu tĩnh thành archive khi phù hợp mục tiêu sử dụng, nhưng phải tính chi phí giải nén và khả năng truy cập đối tượng về sau. Không nén hoặc gộp chỉ để đạt một chỉ số tốc độ.

### Chọn số lượng thiết bị

Ví dụ có 180 TB dữ liệu thường, chọn **một TA300** thay vì nhiều TA40 nếu đáp ứng điều kiện cấp phát và khả năng sao chép. Với 420 TB dữ liệu, có thể cần **nhiều thiết bị**, chia tập dữ liệu bằng manifest rõ ràng và tránh trùng/thiếu đường dẫn. Google xác nhận mẫu, số lượng và phương thức nhận trước khi triển khai.

Nên để dự phòng cho dữ liệu phát sinh, sai lệch ước lượng và yêu cầu vận hành. Không đặt dung lượng gần 100% tối đa rồi mặc định toàn bộ dữ liệu sẽ luôn vừa.

## 6. Chuẩn bị Google Cloud và chính sách bảo mật

### Project, bucket và IAM

1. Chọn **Google Cloud project** chứa cấu hình đơn hàng và xác định **bucket Cloud Storage đích**. Theo luồng chuẩn, đăng ký Transfer Appliance trong cùng project với bucket đích.
2. Kiểm tra **location của bucket**, yêu cầu data residency, chính sách lưu giữ, storage class, versioning và chi phí lưu trữ về sau. Việc nhập dữ liệu thành công chưa đồng nghĩa đã chọn đúng nơi lưu lâu dài.
3. Chuẩn bị quyền quản trị cần thiết để hoàn tất checklist thiết lập; cấp cho tài khoản dịch vụ của phiên/thiết bị quyền truy cập bucket theo hướng dẫn chính thức và nguyên tắc **ít quyền nhất**.
4. Nếu dùng online mode, cần quyền và API liên quan đến **Transfer Appliance, Pub/Sub, Storage Transfer Service**, cũng như tài khoản dịch vụ phù hợp. Bảo vệ khóa tài khoản dịch vụ theo chính sách tổ chức; không đưa khóa vào repository, terminal log hoặc tài liệu hướng dẫn công khai.
5. Nếu dùng khóa mã hóa do khách hàng quản lý, phối hợp với nhóm bảo mật để chuẩn bị **Cloud KMS** và chính sách vòng đời khóa. Không xóa hoặc vô hiệu hóa khóa đang cần cho phiên chuyển dữ liệu.

Quyền yêu cầu đơn hàng, quyền ghi object, quyền đọc dữ liệu sau chuyển và quyền quản lý KMS là các trách nhiệm khác nhau; nên phân công và kiểm tra trước.

### Bảo vệ dữ liệu và thiết bị

Transfer Appliance có cơ chế xác minh thiết bị bằng **hardware attestation/TPM**, bảo vệ dữ liệu lưu trên thiết bị bằng **AES-256**, và sử dụng **data encryption key (DEK)** được bảo vệ bởi **key encryption key (KEK)**. Với các phiên phù hợp, KEK có thể do Google quản lý hoặc khách hàng quản lý bằng Cloud KMS. Google xác minh thiết bị khi tiếp nhận trước khi nhập dữ liệu, sau đó thực hiện xóa dữ liệu theo quy trình được công bố.

**Ranh giới cần nhớ:** Google nêu rõ không áp dụng lớp mã hóa riêng giữa nguồn dữ liệu nội bộ và Transfer Appliance. Nhóm vận hành chịu trách nhiệm bảo vệ đoạn mạng này. Khi dùng NFS, SMB hoặc các giao thức khác, hãy áp dụng phân đoạn mạng, kiểm soát host được kết nối, hạn chế cổng, quyền truy cập vật lý và phương pháp truyền phù hợp. Nếu chính sách yêu cầu mã hóa trên chặng nội bộ, đánh giá giao thức hỗ trợ cùng nhóm bảo mật.

Cần ghi nhận bàn giao thiết bị, người thao tác, tình trạng niêm phong, mã phiên, kết quả attestation và tình trạng kết thúc phiên. Sau chuyển, có thể tham khảo thủ tục yêu cầu **chứng nhận xóa dữ liệu** nếu chính sách doanh nghiệp cần.

### Khả dụng theo quốc gia

Transfer Appliance **không mặc định có thể giao ở mọi quốc gia**. Tài liệu tổng quan công bố các thị trường như Hoa Kỳ, các nước thành viên EU, Vương quốc Anh, Singapore, Nhật Bản, Canada và Ấn Độ, nhưng danh sách và mẫu thiết bị có thể khác nhau theo vùng. Nếu làm dự án tại **Việt Nam**, phải kiểm tra quốc gia/địa chỉ trong biểu mẫu đặt hàng Google Cloud và xác nhận với bộ phận hỗ trợ trước khi chốt kiến trúc; không suy ra rằng chỉ cần có project Google Cloud là sẽ nhận được thiết bị.

## 7. Quy trình triển khai offline từ đầu đến cuối

### Bước 1 — Thiết kế kế hoạch chuyển dữ liệu

- Chọn tập dữ liệu, bucket, object prefix và thời điểm chốt manifest.
- Xác định bản sao nguồn sẽ được giữ trong bao lâu sau cutover.
- Lập lịch đặt hàng, nhận thiết bị, sao chép, đối soát, giao nhận và xác minh cuối.
- Giao người chịu trách nhiệm cho hạ tầng, IAM/KMS, sao chép và nghiệm thu.
- Chốt cách xử lý dữ liệu thay đổi trong lúc thiết bị đang được gửi và nhập dữ liệu.

### Bước 2 — Đặt thiết bị và hoàn tất setup checklist

Mở phần Transfer Appliance trong Google Cloud console, chọn mẫu và chế độ phù hợp, cấu hình bucket đích, quyền/khóa cùng địa chỉ nhận thiết bị theo hướng dẫn hiện hành. Không dùng con số ước lượng giao hàng như một SLA. Thời gian phụ thuộc quốc gia, mùa vận chuyển, nguồn cung thiết bị và trạng thái đơn.

### Bước 3 — Nhận, xác minh và cấu hình thiết bị

Trước khi nối thiết bị vào mạng nội bộ:

1. Kiểm tra bao bì, dấu niêm phong và nội dung kiện hàng.
2. Chạy ứng dụng **Transfer Appliance Attestation** theo hướng dẫn để nhận passcode.
3. Xác minh passcode qua quy trình Google Cloud, lấy thông tin truy cập được cung cấp sau khi xác thực thành công.
4. Chọn cổng dữ liệu, IP, DNS, nguồn cấp điện và kết nối tới mạng đã kiểm soát.
5. Cấu hình **một giao thức chia sẻ file** phù hợp với hệ điều hành nguồn.

Lưu ý: tài liệu hiện hành cho biết **mỗi thiết bị chỉ cấu hình một giao thức chia sẻ file tại một thời điểm**. Việc đổi giao thức sau khi cấu hình có thể yêu cầu reset thiết bị, gây **mất dữ liệu đã chép**. Nếu cần hai giao thức, xác nhận phương án với Google từ đầu.

### Bước 4 — Sao chép dữ liệu vào thiết bị

**Ví dụ minh họa trên Linux dùng NFSv4**, giả định đã cấu hình appliance và địa chỉ mẫu 192.0.2.10 có thể truy cập từ máy nguồn:

~~~bash
# Trên máy Linux nguồn; chỉ chạy khi thiết bị đã cấu hình NFS.
sudo mkdir -p /mnt/ta
sudo mount -t nfs -o vers=4 192.0.2.10:/mnt/ta_data /mnt/ta

# Ví dụ copy regular files dưới thư mục archive.
# Đánh giá hành vi đối với file đặc biệt, symlink và quyền trước khi thực thi.
rsync -r --partial --info=progress2 /data/archive/ /mnt/ta/archive/
~~~

Đây là ví dụ cấu trúc lệnh; thay IP, đường dẫn và cách xác thực theo thiết bị thực tế. Đường dẫn đích trên thiết bị là **/mnt/ta_data**. Với Linux/macOS có thể dùng NFS; Windows thường dùng SMB hoặc SFTP/SCP. Tránh thay đổi giao thức sau khi đã ghi dữ liệu. Chạy lệnh copy trong **tmux/screen** hoặc môi trường giám sát thích hợp để chống gián đoạn phiên quản trị.

Không dùng bản sao đang được sửa liên tục làm đầu vào nếu yêu cầu tính nhất quán cao. Sau lần sao chép đầu, xác minh dữ liệu vừa sao chép so với snapshot/manifest đã chốt.

### Bước 5 — Theo dõi tiến độ và lỗi

Trên môi trường dòng lệnh của Transfer Appliance, ví dụ:

~~~bash
ta status
ta status --verbose
~~~

Theo dõi dung lượng đã sử dụng, dung lượng còn lại, lỗi ổ đĩa/kết nối, lượng dữ liệu và tốc độ sao chép. Google cũng có phương án theo dõi các metric của Transfer Appliance bằng Cloud Monitoring khi được cấu hình đúng.

Với nhiều nguồn, chia tập dữ liệu thành từng lô có mã định danh (ví dụ kho ảnh 2018–2020, 2021–2023, 2024–2026). Ghi log nguồn, tổng số file, byte, thời điểm snapshot và lỗi của từng lô. Nếu xảy ra lỗi copy hoặc file không hợp lệ, xử lý trước khi kết thúc phiên.

### Bước 6 — Kiểm tra và finalize

Trước khi thực hiện lệnh kết thúc phiên, xác nhận:

- Các lô trong manifest đã copy đủ; danh sách lỗi đang mở đã được xử lý hoặc được chấp nhận có ghi nhận.
- Đã kiểm tra mẫu hash nội dung hoặc hash toàn bộ theo yêu cầu rủi ro.
- Không còn quy trình nào đang ghi dữ liệu vào thiết bị.
- Đã lưu đủ thông tin audit và có kế hoạch cho phần delta.

Lệnh **ta finalize** thực hiện kết thúc phiên sao chép để chuẩn bị trả thiết bị. Đây là **thao tác có hệ quả không thể tiếp tục ghi**: thiết bị xóa các khóa và cấu hình cần thiết theo quy trình finalization, nên chỉ chạy khi đã xác minh. Trong phiên thực tế, làm theo chỉ dẫn chính thức và lưu **passcode** trả về để lấy nhãn hoàn trả.

~~~bash
# Chạy trên thiết bị, sau khi đã xác minh xong toàn bộ dữ liệu.
ta finalize
~~~

### Bước 7 — Gửi trả thiết bị

Đóng gói, niêm phong, sử dụng nhãn hoàn trả đúng phiên và ghi nhận chain of custody. Google nhận, xác minh thiết bị rồi nhập dữ liệu từ thiết bị vào Cloud Storage.

### Bước 8 — Xác minh dữ liệu đã nhập Cloud Storage

Chỉ coi quá trình chuyển xong khi có bằng chứng ở **bucket đích**, không chỉ vì bên vận chuyển đã giao thiết bị. Theo hướng dẫn Google, có thể kiểm tra:

- Thông báo hoàn tất từ nhóm Transfer Appliance.
- Các object thực tế trong bucket và prefix đích.
- Log CSV chuyển thành công/thất bại dưới đường dẫn tương tự:

~~~text
gs://DESTINATION_BUCKET/transferappliance/logs/SESSION_ID/TIMESTAMP/transferred/
gs://DESTINATION_BUCKET/transferappliance/logs/SESSION_ID/TIMESTAMP/failedtotransfer/
~~~

Đối chiếu file path, số lượng file, dung lượng và lỗi. Chọn mẫu file quan trọng để tải lại, tính checksum, thử giải nén hoặc chạy ứng dụng đọc dữ liệu. Nếu có object không thể nhập, lập danh sách xử lý lại; không xóa bản gốc.

### Bước 9 — Hoàn tất cutover và dọn dữ liệu nguồn

Sau khi đối soát thành công, quyết định thời điểm đổi ứng dụng sang đường dẫn Cloud Storage và chuyển phần dữ liệu phát sinh nếu có. Kiểm thử quyền truy cập, hiệu năng, workflow xử lý và cơ chế retry. Chỉ kết thúc lưu giữ bản sao on-premises sau khi chủ dữ liệu chấp thuận dựa trên kết quả nghiệm thu, chính sách lưu trữ và kế hoạch phục hồi.

## 8. Tiêu chí nghiệm thu dữ liệu

Có thể dùng bảng sau làm đầu vào cho biên bản nghiệm thu:

| Kiểm tra | Cách kiểm tra | Tiêu chí gợi ý |
| --- | --- | --- |
| Đầy đủ | So manifest nguồn với danh sách object đích | Không còn file thiếu chưa được giải thích |
| Lỗi nhập | Đọc CSV failed-to-transfer | Không có lỗi chưa xử lý |
| Tính toàn vẹn | So checksum cho toàn bộ hoặc mẫu đại diện theo phân loại rủi ro | Khớp nội dung kỳ vọng |
| Cấu trúc | Kiểm tra tên object, prefix, cấu trúc phân vùng | Theo quy ước dữ liệu đích |
| Khả năng sử dụng | Ứng dụng thử đọc, Dataflow/BigQuery xử lý tập mẫu | Kết quả đúng, không lỗi quyền |
| Bảo mật | Kiểm tra IAM, location, KMS và chính sách lưu giữ | Đúng thiết kế được phê duyệt |
| Dữ liệu phát sinh | So sánh mốc snapshot với trạng thái hiện tại | Đã có phương án xử lý delta |
| Bằng chứng | Lưu manifest, log và biên bản bàn giao | Có thể truy vết phiên chuyển |

**Về checksum:** Cloud Storage có cơ chế checksum/metadata riêng cho object; không được mặc định mọi object đều có MD5 có thể đem so trực tiếp với hash file nguồn. Lựa chọn loại hash, cách tạo manifest, cách map đường dẫn và phương án đọc lại mẫu phải được thống nhất trước. Với dữ liệu đặc biệt quan trọng, cân nhắc hash mạnh ở nguồn và tính lại khi đọc object để kiểm tra.

## 9. Rủi ro thường gặp và cách xử lý

| Rủi ro | Dấu hiệu | Cách giảm thiểu |
| --- | --- | --- |
| Ước lượng thiếu dung lượng | Thiết bị đầy trước khi copy xong | Khảo sát bằng byte, cộng tăng trưởng và dự phòng; chia nhiều thiết bị khi cần |
| Nhiều file rất nhỏ | Số TB không lớn nhưng tốc độ tổng thấp | Đo thử bằng tập đại diện; tối ưu chiến lược copy và mức độ song song |
| Tên/path hoặc file không hợp lệ | Object thiếu sau khi Google nhập dữ liệu | Quét điều kiện Cloud Storage và giới hạn Transfer Appliance trước khi copy |
| Nguồn thay đổi trong lúc copy | Hash hoặc số file khác manifest | Snapshot, chốt mốc và chuyển delta |
| Quyền bucket hoặc KMS sai | Nhập dữ liệu/giải mã bị chặn | Kiểm tra checklist IAM/KMS và vòng đời khóa trước |
| Mạng nội bộ không an toàn | Nguy cơ lộ dữ liệu trên chặng nguồn–thiết bị | Phân đoạn mạng, kiểm soát truy cập, chọn giao thức truyền phù hợp |
| Mất phiên sao chép | Copy bị gián đoạn giữa chừng | Dùng công cụ có khả năng chạy lại, giữ log và kiểm tra sau lỗi |
| Finalize quá sớm | Không thể tiếp tục ghi vào thiết bị | Bắt buộc đối soát và checkpoint trước lệnh finalize |
| Không nhận được thiết bị tại địa điểm | Đơn hàng không khả dụng ở quốc gia yêu cầu | Xác nhận địa lý và phương thức giao hàng trước khi duyệt kiến trúc |
| Nhầm giữa chuyển tệp và chuyển ứng dụng | File đã vào bucket nhưng ứng dụng không hoạt động | Lập kế hoạch riêng cho database, API, IAM và đường dẫn ứng dụng |

## 10. Chi phí và lịch trình thực tế

Khi đánh giá tổng chi phí chuyển đổi (TCO), cần xem xét ít nhất:

1. **Chi phí dịch vụ/thiết bị và logistics:** loại thiết bị, số lượng thiết bị, thời gian sử dụng và điều kiện vận chuyển theo báo giá hoặc bảng giá đang có hiệu lực.
2. **Chi phí nội bộ:** nhân sự, thời gian vận hành, phần cứng mạng, snapshot, tăng tải trên NAS, thiết lập kiểm soát.
3. **Chi phí Google Cloud sau nhập dữ liệu:** dung lượng Cloud Storage, storage class, thao tác API, truy xuất, xử lý dữ liệu và lưu bản sao.
4. **Chi phí của phương án online:** đường truyền, traffic theo thiết kế, giới hạn Internet và điều kiện thanh toán nếu có.
5. **Chi phí rủi ro:** trễ cutover, công việc làm lại vì lỗi dữ liệu, thời gian giữ song song hai hệ thống.

Không chốt phương án chỉ bằng giá thuê thiết bị hoặc giá Cloud Storage trên mỗi GB. Cần so sánh **tổng chi phí + tổng thời gian + mức độ chấp nhận rủi ro**.

Ví dụ kế hoạch **minh họa** cho 180 TB:

| Giai đoạn | Hoạt động | Đầu ra |
| --- | --- | --- |
| Tuần chuẩn bị | Khảo sát, chọn vùng bucket, xác nhận khả dụng, phân quyền | Inventory, manifest plan, phương án chuyển delta |
| Nhận thiết bị | Attestation, nối mạng, kiểm thử bằng tập nhỏ | Thiết bị hoạt động, tốc độ đo thực |
| Sao chép | Copy dữ liệu nguồn cố định và kiểm tra | Đã ghi dữ liệu cần gửi, không còn lỗi chưa xử lý |
| Hoàn trả | Finalize, niêm phong, vận chuyển | Passcode, biên bản giao nhận |
| Nhập và nghiệm thu | Google nhập bucket; nhóm dự án đối soát | Biên bản nghiệm thu, danh sách lỗi còn lại |
| Cutover | Chuyển delta và kiểm thử ứng dụng | Ứng dụng sử dụng dữ liệu trên GCP |

Các hàng này là **thứ tự công việc**, không phải cam kết số ngày. Tài liệu Google nêu chu kỳ đầu cuối khoảng ba tuần như một chỉ dẫn tổng quát; thời gian của từng đơn hàng phải được xác nhận riêng.

## 11. Tình huống kiến trúc: chuyển kho dữ liệu media sang GCP

Một công ty có **180 TB** video gốc và ảnh lưu trên NAS, phát sinh thêm 100 GB mỗi ngày. Doanh nghiệp muốn đặt dữ liệu vào Cloud Storage để Dataflow xử lý metadata và dùng BigQuery cho phân tích; ứng dụng giao diện dùng Cloud Run để tra cứu kết quả.

**Thiết kế đề xuất:**

1. Tạo manifest cho kho dữ liệu đến mốc T0, chốt snapshot và phân loại tệp.
2. Ước lượng Internet hữu ích: 200 Mbps × 75% → nhập 180 TB qua mạng khoảng 111 ngày; khảo sát Transfer Appliance TA300 và tình trạng hỗ trợ giao nhận.
3. Chọn bucket đúng vùng lưu trú dữ liệu; thiết lập IAM, chính sách bảo mật và quota phù hợp; thử sao chép một tập nhỏ.
4. Sao chép snapshot T0 vào Transfer Appliance; đối soát manifest, finalize và gửi trả thiết bị.
5. Trong lúc chờ nhập, dữ liệu mới tiếp tục phát sinh: **100 GB/ngày** được lưu trong khu vực delta có ghi timestamp và danh mục để sau đó chuyển qua phương thức online phù hợp, chẳng hạn Storage Transfer Service.
6. Khi Google xác nhận nhập dữ liệu, so khớp object, log, checksum, chuyển phần delta và chạy thử pipeline Dataflow / BigQuery.
7. Chuyển ứng dụng Cloud Run đọc dữ liệu đích theo IAM thích hợp; giữ NAS cho tới khi chủ dữ liệu nghiệm thu.

**Điểm khó nhất không phải gắn cáp thiết bị:** phải bảo đảm tập T0 và tập delta không bỏ sót, không ghi đè sai phiên bản, đồng thời thay đổi ứng dụng vào thời điểm dữ liệu đã đầy đủ. Nếu khối lượng thay đổi lớn hoặc cần RPO rất thấp, nên cân nhắc mô hình chuyển online/replication chuyên dụng cho phần thay đổi.

## 12. Ghi nhớ trước khi áp dụng

- Transfer Appliance là công cụ **chuyển dữ liệu ở quy mô lớn**, đích tiêu biểu là **Cloud Storage**.
- Số TB chỉ là một yếu tố; hãy đo tốc độ hữu ích, số lượng file và thời gian xử lý đầu cuối.
- Offline giúp giảm phụ thuộc băng thông Internet cho lần nhập dữ liệu lớn; online mode hữu ích khi có kết nối phù hợp.
- Kiểm tra khả dụng giao thiết bị tại quốc gia, mẫu thiết bị, dung lượng thực và điều kiện đặt hàng.
- Bảo mật bao gồm **attestation, mã hóa, kiểm soát mạng nội bộ, IAM, Cloud KMS, giao nhận và xóa dữ liệu**.
- Bảo đảm dữ liệu ở đích bằng **manifest, log, checksum và kiểm thử ứng dụng** trước khi xóa dữ liệu nguồn.
- Migration hoàn chỉnh phải có kế hoạch cho **dữ liệu phát sinh, chuyển ứng dụng, chi phí và phương án phục hồi**.

## Tài liệu tham khảo chính thức

Các thông tin về dung lượng, quy trình và giao thức được đối chiếu từ tài liệu Google Cloud. Kiểm tra lại khi triển khai vì tính khả dụng và quy trình có thể được cập nhật.

- [Transfer Appliance — Overview](https://docs.cloud.google.com/transfer-appliance/docs/4.0/overview)
- [Transfer Appliance — Specifications](https://docs.cloud.google.com/transfer-appliance/docs/4.0/specifications)
- [Transfer Appliance — High-level procedure](https://docs.cloud.google.com/transfer-appliance/docs/4.0/procedure-guide)
- [Transfer Appliance — Transfer data](https://docs.cloud.google.com/transfer-appliance/docs/4.0/transfer-data)
- [Transfer Appliance — Security and encryption](https://docs.cloud.google.com/transfer-appliance/docs/4.0/security-and-encryption)
- [Transfer Appliance — Access your data in Cloud Storage](https://docs.cloud.google.com/transfer-appliance/docs/4.0/access-data)
- [Storage Transfer Service — Data transfer options](https://docs.cloud.google.com/storage-transfer/docs/transfer-options)
