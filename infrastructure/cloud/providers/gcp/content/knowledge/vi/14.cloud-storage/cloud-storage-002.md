# Chọn bucket location và storage class trong Google Cloud Storage

Một đội phát triển vận hành hệ thống bán hàng trên **Google Cloud**. Ứng dụng **Cloud Run** nhận ảnh sản phẩm, một pipeline **GKE** biến đổi ảnh, **Compute Engine** xử lý báo cáo và **Cloud SQL** lưu metadata. Ảnh mới được đọc hàng nghìn lần mỗi ngày, báo cáo cũ chỉ xem lại theo quý, còn bản sao lưu phải giữ lâu để tuân thủ quy định. Nếu chọn cùng một **bucket location** và **storage class** cho tất cả, tổ chức có thể phải trả thêm phí không cần thiết hoặc không đạt yêu cầu về nơi lưu dữ liệu và khôi phục sau sự cố.

**Cloud Storage** là dịch vụ **object storage**: dữ liệu được lưu thành object trong bucket, truy cập qua API, SDK hoặc công cụ dòng lệnh. Khi tạo bucket, hai quyết định quan trọng là:

1. **Bucket location:** dữ liệu được đặt trong **region, dual-region hoặc multi-region** nào, ảnh hưởng tới phạm vi địa lý, mô hình dự phòng, khả năng đáp ứng yêu cầu dữ liệu, đường kết nối và chi phí.
2. **Storage class:** chọn **Standard, Nearline, Coldline, Archive** hoặc chiến lược quản lý lớp lưu trữ tự động khi phù hợp, ảnh hưởng tới giá lưu, phí truy xuất, các khoản phí khi xóa/chuyển lớp sớm và tổng chi phí theo vòng đời.

Bài học thuộc chương **Cloud Storage** của mô-đun **CLOUD_PROVIDERS_GCP**. Mục tiêu rộng của mô-đun là biết tổ chức project, quản lý IAM/VPC, lựa chọn Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu, triển khai an toàn, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Bài này tập trung vào việc **ra quyết định có thể giải thích và kiểm chứng** khi đặt dữ liệu vào bucket.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt rõ **bucket**, **object**, **bucket location**, **default storage class** và **storage class của từng object**.
2. So sánh **regional**, **dual-region** và **multi-region** theo nhu cầu dữ liệu, khả năng chịu lỗi và chi phí.
3. Chọn giữa **Standard, Nearline, Coldline và Archive** dựa trên tần suất truy cập, thời gian giữ và kiểu thao tác thực tế.
4. Hiểu tác động của **minimum storage duration**, phí đọc/truy xuất và việc đổi storage class.
5. Phân biệt **Autoclass** với các quy tắc **Object Lifecycle Management** tự viết.
6. Dùng `gcloud storage` để tạo và kiểm tra bucket, quản lý default storage class, cấu hình lifecycle an toàn.
7. Thiết kế storage cho ứng dụng chạy trên Cloud Run/GKE/Compute Engine, xét thêm IAM, bảo mật, khôi phục và tối ưu chi phí.

## 2. Ba khái niệm nền tảng: bucket, location và class

### 2.1. Bucket và object

Một bucket là container logic chứa các object. Object có dữ liệu, tên và metadata. Ví dụ:

~~~text
Bucket: gs://retail-media-prod-example
Location: asia-southeast1
Default storage class: STANDARD

Objects:
  products/2026/11/item-1001.jpg
  products/2026/11/item-1002.jpg
  reports/monthly/2026-10.csv
~~~

Tên bucket phải **duy nhất trong không gian tên áp dụng của Cloud Storage**, tuân thủ quy tắc đặt tên và không chứa thông tin nhạy cảm. Tên ở ví dụ chỉ để minh họa; không giả định có thể tạo đúng tên này trong project của bạn.

**Location là thuộc tính của bucket.** Mỗi bucket có một vị trí lưu trữ được chọn theo loại location được hỗ trợ. **Storage class có thể là thuộc tính của từng object**; default storage class của bucket chỉ quyết định lớp mặc định áp dụng cho những object mới khi không được chỉ định lớp riêng.

### 2.2. Location và storage class giải quyết hai câu hỏi khác nhau

| Quyết định | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Bucket location** | Dữ liệu nằm trong phạm vi địa lý và mô hình replication nào? | Region `asia-southeast1`, dual-region được hỗ trợ hoặc multi-region `ASIA`. |
| **Storage class** | Tần suất đọc và thời gian giữ dữ liệu có phù hợp mức phí nào? | Ảnh bán chạy dùng `STANDARD`; báo cáo lưu lâu có thể dùng `COLDLINE`. |
| **IAM/policy** | Ai được đọc, ghi, xóa hoặc công khai object? | Service account của ứng dụng chỉ được đọc/ghi đối tượng cần thiết. |
| **Lifecycle/retention** | Khi nào đổi lớp, xóa, hoặc bắt buộc giữ dữ liệu? | Chuyển lớp sau 90 ngày; giữ dữ liệu theo nghĩa vụ pháp lý. |

Một bucket đặt ở dual-region nhưng chứa object `ARCHIVE` vẫn là dual-region về vị trí. Một bucket ở region đơn nhưng dùng `STANDARD` không tự có dự phòng giữa hai region. **Location không tự thay đổi storage class và ngược lại.**

### 2.3. Sơ đồ đường đi dữ liệu

~~~mermaid
flowchart LR
    U["Người dùng / ứng dụng"] --> API["Cloud Storage JSON/XML APIs"]
    API --> B["Bucket: location được chọn"]
    B --> O1["Object A: STANDARD"]
    B --> O2["Object B: NEARLINE"]
    B --> O3["Object C: ARCHIVE"]
    I["IAM + security policies"] -. "Kiểm soát truy cập" .-> API
    L["Lifecycle / Autoclass (khi cấu hình)"] -. "Quản lý storage class" .-> B
~~~

Sơ đồ mô tả lớp logic. Cloud Storage **không phải một thư mục nằm trên ổ đĩa VM**; `gs://...` là URI đối tượng. VM/GKE/Cloud Run gọi dịch vụ qua những endpoint và cơ chế mạng phù hợp. Việc bucket nằm cùng region với ứng dụng không tự tạo một private VPC IP cho bucket.

## 3. Chọn bucket location

### 3.1. Regional location

**Regional bucket** đặt dữ liệu trong một region cụ thể, ví dụ `asia-southeast1`. Dịch vụ Cloud Storage quản lý độ bền và khả năng sẵn sàng trong phạm vi region theo đặc tính sản phẩm; không nên hiểu dữ liệu nằm trên một máy chủ hay một zone duy nhất.

**Khi nên cân nhắc regional:**

- Ứng dụng Cloud Run, GKE hoặc VM chủ yếu hoạt động trong một region.
- Dữ liệu có quy định phải nằm trong **region cụ thể**, không được sao chép sang vùng khác.
- Tổ chức muốn kiểm soát nơi đặt dữ liệu và tránh chọn phạm vi địa lý rộng hơn nhu cầu.
- Hệ thống chấp nhận thiết kế DR riêng cho trường hợp cả region không sẵn có.

**Giới hạn cần nhớ:** regional storage không đồng nghĩa có bản sao dữ liệu ở region khác. Nếu rủi ro mất khả năng truy cập do sự cố toàn region không thể chấp nhận, cần đánh giá dual-region/multi-region hoặc kiến trúc replication/backup phù hợp.

### 3.2. Dual-region location

**Dual-region bucket** lưu dữ liệu dư thừa qua **hai region cụ thể** được Google Cloud hỗ trợ. Tùy loại dual-region, có thể chọn một **cặp predefined** hoặc cấu hình hai region theo những ràng buộc của **configurable dual-region**. Không phải mọi cặp region đều được phép.

~~~mermaid
flowchart TB
    APP["Ứng dụng và Google Cloud APIs"] --> BUCKET["Dual-region bucket"]
    BUCKET --> R1["Bản sao tại region A"]
    BUCKET --> R2["Bản sao tại region B"]
    APP -. "Tính sẵn sàng phải được kiểm chứng" .-> BUCKET
~~~

Dual-region thích hợp khi:

- Có yêu cầu **độ bền/khả năng phục vụ dữ liệu qua hai region** trong phạm vi địa lý được chấp nhận.
- Các dịch vụ xử lý ở hai region cần một bucket lưu trữ chung phù hợp kiến trúc.
- Đội vận hành muốn cơ chế replication do Cloud Storage quản lý thay vì tự chép từng object.

**Không nhầm replication với backup.** Nếu ứng dụng có quyền xóa object hoặc ghi đè dữ liệu sai, bản sao lưu trữ theo cơ chế location vẫn có thể phản ánh thay đổi không mong muốn. Các nhu cầu phục hồi do xóa nhầm, ransomware hoặc lỗi ứng dụng cần **Object Versioning, soft delete, retention, backup/replication độc lập** khi phù hợp.

### 3.3. Multi-region location

**Multi-region bucket** đặt dữ liệu trong một **khu vực địa lý rộng** được Google Cloud xác định, ví dụ `US`, `EU` hoặc `ASIA`, với dữ liệu được lưu dư thừa qua nhiều region trong khu vực đó theo mô hình của dịch vụ.

Mục tiêu thường gặp là hỗ trợ ứng dụng/khách hàng ở nhiều vùng trong một khu vực rộng, đồng thời dựa vào đặc tính sẵn sàng của Cloud Storage. Tuy nhiên:

- Bạn **không tự chọn chính xác tất cả region vật lý** bên trong multi-region.
- `ASIA` không đồng nghĩa dữ liệu được lưu trong mọi region châu Á.
- Multi-region không tự giải quyết toàn bộ yêu cầu **độ trễ đọc gần người dùng**: với static content có lượng truy cập lớn, vẫn cần đánh giá **Cloud CDN** và chính sách cache.
- Không mặc nhiên rẻ hơn regional; giá lưu, replication, transfer và tương tác với compute có thể khác.

### 3.4. Bảng so sánh ba loại location

| Tiêu chí | Regional | Dual-region | Multi-region |
| --- | --- | --- | --- |
| Phạm vi | Một region cụ thể. | Hai region được hỗ trợ. | Nhóm region trong một khu vực địa lý rộng. |
| Kiểm soát vị trí | Chính xác một region. | Hai region cụ thể theo khả năng hỗ trợ. | Chọn phạm vi địa lý, không chọn mọi region thành viên. |
| Khả năng dùng cho workload một region | Thường là lựa chọn dễ giải thích. | Có thể phù hợp nếu cần dự phòng hai region. | Cần chứng minh lợi ích so với chi phí. |
| Dữ liệu phải ở một region duy nhất | Phù hợp hơn về ràng buộc địa lý. | Không phù hợp nếu region thứ hai không được phép. | Thường không phù hợp nếu chỉ được lưu đúng một region. |
| Kỳ vọng chịu sự cố toàn region | Cần kế hoạch DR khác. | Có bản sao qua hai region theo dịch vụ. | Có redundancy nhiều region theo dịch vụ. |
| Quyết định chi phí | Giá regional và traffic liên quan. | Giá vị trí dual-region, replication và traffic. | Giá multi-region, truy cập và traffic. |

**Không có lựa chọn tốt nhất cho mọi workload.** Một ứng dụng chủ yếu ở một region thường nên xem **regional** trước; nếu có yêu cầu đa vùng về dữ liệu, mới mở rộng sang **dual-region** hoặc **multi-region** sau khi đánh giá tiêu chí pháp lý, RPO/RTO và chi phí.

## 4. Location ảnh hưởng tới mạng, độ trễ và tuân thủ thế nào?

### 4.1. Đặt dữ liệu gần workload cần truy cập nhiều nhất

Giả sử ứng dụng Cloud Run, cluster GKE và VM đều ở `asia-southeast1`, thường xuyên xử lý ảnh trên Cloud Storage. Chọn bucket regional cùng region là một **phương án khởi đầu hợp lý** để đơn giản hóa thiết kế:

~~~text
Cloud Run / GKE / VM: asia-southeast1
Cloud Storage bucket: asia-southeast1
Cloud SQL:             region phù hợp theo kiến trúc dữ liệu
~~~

Lợi ích cần **kiểm chứng**, không phỏng đoán:

- Độ trễ từng loại thao tác (`GET`, `PUT`, liệt kê object, xử lý chunk).
- Khối lượng dữ liệu truyền qua các vùng và cách Google Cloud tính phí trong topology thực.
- Đường truy cập từ Cloud Run/GKE/VM tới Google APIs có được cấu hình an toàn không.
- Chi phí khi xử lý ứng dụng ở một region nhưng cần đọc object từ vùng khác.

**Cùng region không đồng nghĩa mọi data transfer đều miễn phí**: giá phụ thuộc dịch vụ nguồn/đích, đường truyền, loại request và chính sách giá. Luôn xem bảng giá của Cloud Storage, Compute Engine, GKE hoặc Cloud Run liên quan.

### 4.2. Dữ liệu tới người dùng toàn cầu

Giả sử người dùng ở nhiều quốc gia xem ảnh sản phẩm. Việc chọn multi-region bucket không phải sự thay thế hoàn chỉnh cho **edge caching**. Một mô hình khả thi:

~~~mermaid
flowchart LR
    CLIENT["Khách hàng Internet"] --> CDN["Cloud CDN / edge cache"]
    CDN --> LB["Load balancer + backend bucket hoặc backend phù hợp"]
    LB --> GCS["Cloud Storage bucket"]
    APP["Cloud Run / GKE tạo ảnh mới"] --> GCS
~~~

Cloud CDN giúp giảm số lần phải lấy object gốc khi cache hit; độ trễ phụ thuộc chính sách cache, địa lý và hành vi người dùng. Ảnh công khai có thể phù hợp cache; hóa đơn hoặc dữ liệu riêng của người dùng thường cần kiểm soát chặt header, cache key và quyền truy cập. Không dùng CDN để biện minh cho một bucket public không có cơ chế phân quyền hợp lệ.

### 4.3. Yêu cầu data residency

Nếu dữ liệu cá nhân chỉ được phép lưu trong một quốc gia hoặc một region, hãy xác minh:

1. **Location được Cloud Storage hỗ trợ** có đáp ứng nơi lưu theo chính sách pháp lý/nội bộ không.
2. Với dual-/multi-region, **mọi region được dùng để lưu dữ liệu** có được chấp nhận không.
3. **Logging, KMS keys, backups, phiên bản object, temporary files** và các hệ thống phụ trợ có đáp ứng yêu cầu địa lý tương ứng không.
4. Có chính sách tổ chức, ví dụ **Organization Policy với resource locations constraint**, giúp kiểm soát việc tạo tài nguyên sai vị trí không.

**Bucket location không phải chứng nhận pháp lý tự thân.** Cần phối hợp với bộ phận an toàn thông tin/pháp chế để làm rõ loại dữ liệu, yêu cầu hợp đồng và trách nhiệm lưu giữ.

### 4.4. Truy cập từ VPC không đồng nghĩa truy cập bucket “nội bộ”

Compute Engine VM không có external IP có thể gọi Cloud Storage API nếu có **Private Google Access** (hoặc phương án kết nối Google APIs khác được hỗ trợ), DNS, route, egress policy và IAM phù hợp. Bucket regional không tự cấp IP thuộc subnet VPC; location ảnh hưởng nơi lưu dữ liệu, không thay thế thiết kế đường mạng đến API.

Tương tự, Cloud Run hoặc GKE có các mô hình egress và identity riêng. Đừng bật external IP cho VM hoặc cấp role Owner chỉ vì một thao tác `gcloud storage` thất bại; cần phân biệt lỗi DNS, TCP/TLS, token và IAM.

## 5. Chọn storage class: Standard, Nearline, Coldline, Archive

### 5.1. Tần suất truy cập là tiêu chí đầu tiên

Cloud Storage có các lớp lưu trữ với mục đích sử dụng và mô hình phí khác nhau:

| Storage class | Đặc điểm sử dụng điển hình | Thời hạn lưu tối thiểu để tránh phí xóa/chuyển lớp sớm* | Ví dụ |
| --- | --- | --- | --- |
| **Standard** | Dữ liệu truy cập thường xuyên, phục vụ ứng dụng và nội dung hoạt động. | Không có mức tối thiểu kiểu Nearline/Coldline/Archive. | Ảnh sản phẩm được tải thường xuyên, file mới upload. |
| **Nearline** | Dữ liệu đọc tương đối ít, chẳng hạn khoảng một lần/tháng hoặc ít hơn. | **30 ngày**. | Báo cáo ít xem, dữ liệu dự phòng ngắn hạn. |
| **Coldline** | Dữ liệu đọc hiếm, chẳng hạn mỗi quý hoặc ít hơn. | **90 ngày**. | Backup theo chu kỳ, dữ liệu lưu phục vụ điều tra không thường xuyên. |
| **Archive** | Dữ liệu truy cập rất hiếm, mục tiêu giữ dài hạn. | **365 ngày**. | Hồ sơ dài hạn, dữ liệu đáp ứng nghĩa vụ lưu giữ. |

\* Những con số trên là **minimum storage duration** phổ biến của các lớp tương ứng. Khi xóa, thay thế hoặc chuyển class sớm, có thể bị tính **early deletion charge** cho phần thời gian còn thiếu theo quy tắc sản phẩm; việc bật Versioning, soft delete hoặc retention có thể làm vòng đời và chi phí phức tạp hơn.

Các lớp này **không có nghĩa “Archive phải mất vài giờ mới lấy được file”** như một số dịch vụ lưu trữ băng lạnh khác. Cloud Storage cung cấp truy cập online với mô hình độ trễ thấp theo đặc tính sản phẩm, nhưng phí **retrieval** và **operations** của lớp lạnh có thể đáng kể.

### 5.2. Phí lưu thấp hơn chưa chắc tổng chi phí thấp hơn

Khi quyết định class, hãy xét đồng thời:

- **Storage cost:** dung lượng × thời gian × giá theo class/location.
- **Retrieval charges:** lượng dữ liệu đọc ra từ các lớp có tính phí truy xuất.
- **Operations charges:** số yêu cầu API và loại thao tác (`GET`, `LIST`, ghi, quản lý metadata...) theo bảng giá.
- **Early deletion charges:** nếu object bị xóa, thay thế hoặc chuyển class trước minimum duration.
- **Data transfer / network charges:** đường truyền đến client, dịch vụ tính toán hoặc region khác.
- **Chi phí bảo vệ dữ liệu:** object versions, soft delete, replication, audit/logging, quản lý và kiểm soát.

**Cách nghĩ quan trọng:** chọn class theo **tổng chi phí cho một vòng đời dữ liệu**, không chọn lớp có giá lưu mỗi GiB/tháng thấp nhất.

### 5.3. Một ví dụ dễ hiểu

Hai tệp có kích thước như nhau:

~~~text
Object A: products/new-arrival.jpg
  - Được đọc hàng nghìn lần mỗi ngày.
  - Có thể bị thay bằng ảnh mới sau vài ngày.

Object B: audit/2026/quarter-01.tar
  - Gần như không đọc lại.
  - Phải lưu lâu theo chính sách đã phê duyệt.
~~~

Với **Object A**, Standard thường hợp lý hơn vì tránh phí truy xuất thường xuyên và không có minimum duration như class lạnh. Với **Object B**, Coldline hoặc Archive có thể mang lại lợi ích nếu thời gian giữ đủ dài và nhu cầu đọc thật sự thấp. Tuy nhiên nếu tệp audit được kiểm tra hàng tuần hoặc thường xuyên rewrite, Archive có thể gây chi phí không phù hợp.

### 5.4. Location và storage class tạo thành ma trận lựa chọn

| Workload | Location cần khảo sát | Class nên khảo sát | Lý do chính |
| --- | --- | --- | --- |
| Ảnh sản phẩm đang bán, Cloud Run/GKE chủ yếu tại Singapore. | Regional `asia-southeast1`. | Standard. | Truy cập thường xuyên, ứng dụng chủ yếu trong một region. |
| Dữ liệu ứng dụng quan trọng phục vụ ở hai region đã được hỗ trợ. | Dual-region được hỗ trợ. | Standard hoặc class theo tần suất thực. | Quyết định replication tách với quyết định class. |
| Tệp báo cáo được giữ sáu tháng, rất ít đọc. | Regional đúng yêu cầu tổ chức. | Coldline, sau khi tính chi phí. | Thời gian giữ có thể đủ dài cho minimum duration. |
| Bản lưu dài hạn vài năm, chỉ phục hồi khi cần. | Region/dual-/multi-region theo ràng buộc DR và pháp lý. | Archive. | Ít truy cập và vòng đời dài. |
| Dữ liệu người dùng truy cập khắp nơi, lưu lượng đọc lớn. | Regional/dual-/multi-region theo thiết kế gốc. | Standard + đánh giá CDN. | Cần xem cả cache, dữ liệu và chi phí phân phối. |

Không tự suy rằng dual-/multi-region luôn đi cùng Standard hoặc Archive luôn đi cùng regional. Đây là **hai chiều cấu hình độc lập** với những ràng buộc dịch vụ cần kiểm tra.

## 6. Default storage class khác storage class của object

### 6.1. Default chỉ áp dụng khi tạo object mới

Một bucket có thuộc tính **default storage class**. Nếu client upload object mà không chỉ định class khác, object mới sẽ dùng class mặc định của bucket theo cơ chế API. Tuy nhiên **object đã tồn tại giữ storage class hiện tại**; sửa default class không tự di chuyển/chuyển toàn bộ đối tượng cũ.

Ví dụ:

~~~text
Ngày 01:
  Bucket default = STANDARD
  Upload a.jpg -> STANDARD
  Upload b.jpg -> STANDARD

Ngày 15:
  Bucket default đổi thành NEARLINE
  a.jpg -> vẫn STANDARD
  b.jpg -> vẫn STANDARD
  Upload c.jpg -> NEARLINE (nếu không chỉ định class riêng)
~~~

Nếu muốn chuyển object cũ sang lớp khác, cần dùng **Object Lifecycle Management**, **Autoclass** hoặc thao tác chuyển class được API/công cụ hỗ trợ. Cần xem hậu quả về phí lưu tối thiểu, retrieval và trạng thái versioning/retention.

### 6.2. Có thể trộn nhiều class trong một bucket?

Có, bucket thông thường có thể chứa các object ở những storage class khác nhau. Đây là lý do cần xem **object-level class** khi phân tích chi phí thay vì chỉ đọc default class ở bucket.

~~~text
gs://retail-data-example/
  incoming/new-file.csv       [STANDARD]
  reports/2026-06.csv         [NEARLINE]
  backups/2025-12.tar         [COLDLINE]
  compliance/2020.tar         [ARCHIVE]
~~~

Phân thư mục theo tiền tố (`incoming/`, `reports/`, `backups/`) giúp tổ chức dữ liệu và lifecycle rules, nhưng trong mô hình object storage flat namespace, tên tiền tố không tự tạo quyền, lifecycle hay vị trí địa lý riêng. Những tính năng namespace nâng cao của Cloud Storage nếu dùng phải được xem xét riêng.

## 7. Autoclass và Object Lifecycle Management

### 7.1. Autoclass là gì?

**Autoclass** là tính năng cấp bucket giúp Cloud Storage tự quản lý storage class của object theo hành vi truy cập và chính sách được hỗ trợ. Nó phù hợp khi tổ chức **khó dự báo chính xác tần suất truy cập từng object** hoặc muốn giảm gánh nặng duy trì nhiều quy tắc class.

Ý tưởng:

~~~mermaid
flowchart LR
    NEW["Object mới / truy cập thường xuyên"] --> HOT["Lớp phù hợp truy cập nóng"]
    HOT --> LESS["Ít truy cập sau thời gian quan sát"]
    LESS --> COLD["Lớp lạnh phù hợp"]
    COLD --> REACCESS["Object được truy cập lại"]
    REACCESS --> MANAGE["Autoclass xét lại class theo cơ chế của dịch vụ"]
~~~

Sơ đồ chỉ mô tả nguyên lý, **không phải thuật toán hay mốc thời gian chính xác của Autoclass**. Cần đối chiếu tài liệu hiện hành để hiểu lớp lưu trữ đích, phí quản lý, điều kiện chuyển lớp, ngoại lệ, hạn chế sử dụng đồng thời với các tính năng khác và hành vi khi object được đọc lại.

**Không nên giả định Autoclass luôn rẻ hơn mọi lifecycle rule.** Một tập object có tuổi và kiểu truy cập dự đoán rất rõ có thể được tối ưu tốt bằng lifecycle tự cấu hình. Ngược lại, nếu mỗi object có hành vi khó dự báo, Autoclass có thể giúp giảm sai lệch khi lựa chọn class thủ công.

### 7.2. Lifecycle rules là gì?

**Object Lifecycle Management** cho phép khai báo quy tắc tác động lên object dựa trên điều kiện như **tuổi object**, prefix, storage class hiện tại và các điều kiện khác được hỗ trợ. Hai hành động thường gặp:

- **`SetStorageClass`**: chuyển object sang class được hỗ trợ khi đủ điều kiện.
- **`Delete`**: xóa object theo quy tắc, với giới hạn áp dụng bởi retention policy, object hold, versioning, soft delete và các cơ chế bảo vệ khác.

Ví dụ vòng đời:

~~~mermaid
flowchart LR
    D0["Ngày tạo: STANDARD"] --> D30["Từ ngày 30: NEARLINE"]
    D30 --> D90["Từ ngày 90: COLDLINE"]
    D90 --> D365["Từ ngày 365: ARCHIVE"]
    D365 --> END["Giữ hoặc xóa theo chính sách riêng"]
~~~

Các mốc trên tính theo **tuổi object từ lúc tạo**, không mặc định là “30 ngày sau mỗi lần vừa chuyển class”. Khi đặt điều kiện `age: 90`, nghĩa là object **đã đạt tuổi 90 ngày**; vì vậy cần kiểm tra điều kiện class hiện tại để tránh thay đổi không mong muốn.

### 7.3. File lifecycle JSON minh họa

Trong một lab, người học có thể **tự tạo một file** tên `lifecycle.json` với nội dung:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "NEARLINE"
      },
      "condition": {
        "age": 30,
        "matchesStorageClass": ["STANDARD"]
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 90,
        "matchesStorageClass": ["NEARLINE"]
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "ARCHIVE"
      },
      "condition": {
        "age": 365,
        "matchesStorageClass": ["COLDLINE"]
      }
    }
  ]
}
~~~

Đây là **chính sách minh họa**, không phải cấu hình mặc định nên áp cho mọi bucket. Nó giả định object tồn tại đủ lâu và các class được hỗ trợ. Cần tính minimum storage duration, phiên bản object, điều kiện lifecycle, phí và khả năng xử lý nhiều quy tắc đồng thời.

### 7.4. Cẩn trọng với quy tắc xóa

Một rule `Delete` có thể xóa dữ liệu ngoài ý muốn nếu điều kiện quá rộng hoặc lifecycle đã được bật trên bucket chứa nhiều loại object. Hãy chuẩn bị:

1. Danh sách prefix/object/version trong phạm vi dự kiến.
2. Chính sách retention, object hold, soft delete và versioning.
3. Mốc tuổi và class được xác định theo **giá trị thực của object**.
4. Phương án khôi phục và kiểm thử trong bucket thử nghiệm có dữ liệu không nhạy cảm.
5. Theo dõi sau cập nhật rule, vì lifecycle chạy **bất đồng bộ**, không bảo đảm thay đổi đúng từng giây ngay khi object đủ điều kiện.

Với dữ liệu có nghĩa vụ lưu giữ, **lifecycle Delete không thay thế retention policy**. Khi một retention policy bị **lock**, việc giảm thời hạn hoặc gỡ bỏ có thể bị hạn chế nghiêm ngặt hoặc không thể đảo ngược theo cơ chế sản phẩm; cần phê duyệt bảo mật/pháp chế trước khi cấu hình.

### 7.5. Dùng Autoclass hay lifecycle tự quản lý?

| Tiêu chí | Autoclass | Lifecycle rules thủ công |
| --- | --- | --- |
| Dự báo tần suất đọc | Phù hợp khi hành vi không ổn định/khó dự đoán. | Phù hợp khi có quy tắc tuổi, prefix và truy cập rõ ràng. |
| Độ phức tạp vận hành | Cloud Storage quản lý việc chuyển class trong phạm vi hỗ trợ. | Đội vận hành tự kiểm tra logic rule và chi phí. |
| Kiểm soát mốc chuyển class | Phụ thuộc cơ chế Autoclass. | Chủ động cấu hình theo điều kiện được hỗ trợ. |
| Chi phí | Có mô hình phí/quy tắc riêng; cần đánh giá. | Có chi phí lưu, retrieval, operations và chuyển lớp theo quy tắc. |
| Tương thích | Cần kiểm tra giới hạn kết hợp tính năng. | Cần kiểm tra rule phù hợp với retention, versioning và class. |

Khi lựa chọn, **không bật Autoclass và kỳ vọng các `SetStorageClass` thủ công vẫn hoạt động theo ý mình** nếu sản phẩm quy định hạn chế phối hợp. Xác minh tính tương thích trước khi chuyển đổi.

## 8. Minimum storage duration và các tình huống tính phí bất ngờ

### 8.1. Early deletion không chỉ xảy ra khi gọi DELETE

Ví dụ object `NEARLINE` được tạo rồi bị thay thế sau 10 ngày. Nếu class có yêu cầu tối thiểu 30 ngày, phần thời gian còn thiếu có thể dẫn tới **early deletion charge**, dù thao tác thay thế được thực hiện bằng upload object mới.

Các tình huống cần kiểm tra theo quy tắc giá:

- Xóa object trước minimum duration.
- Thay thế một phiên bản object bằng bản mới.
- Chuyển storage class của object trước thời hạn tối thiểu.
- Xóa object version hoặc chính sách soft delete khiến dữ liệu được tính phí giữ thêm.
- Dùng lifecycle tự động mà mốc tuổi không khớp mô hình phí của class.

**Không nên áp Archive cho dữ liệu có vòng đời chỉ vài ngày**, dù giá lưu mỗi GiB/tháng rất thấp.

### 8.2. Lưu ý về versions và soft delete

Khi **Object Versioning** được bật, thay thế một object có thể tạo ra **noncurrent version** thay vì xóa hoàn toàn phiên bản cũ theo cách đơn giản. Nếu dùng **soft delete**, dữ liệu bị xóa vẫn có thể được giữ trong khoảng thời gian phục hồi theo cấu hình và phát sinh chi phí lưu trữ. Việc áp dụng lifecycle cần xét cả object live và noncurrent versions.

Ví dụ:

~~~text
products/item-1001.jpg
  generation 1001: ảnh cũ, noncurrent
  generation 1002: ảnh hiện hành

Nếu bật versioning:
  chi phí có thể tính trên nhiều phiên bản,
  không chỉ kích thước ảnh hiện hành.
~~~

Versioning giúp khôi phục lỗi overwrite ở một số tình huống, nhưng không phải cơ chế miễn phí hoặc thay thế kế hoạch backup đầy đủ. Nếu yêu cầu tuân thủ cần giữ object bất biến, đánh giá retention/holds theo quy định thay vì chỉ dựa vào versioning.

### 8.3. Archive vẫn có thể đọc online

Khi phải khôi phục dữ liệu Archive, không cần giả định có một quá trình “restore offline” kéo dài như ở những nền tảng khác. Tuy nhiên:

- Dung lượng đọc có thể chịu **retrieval charges**.
- Số API operations lớn có thể tốn phí.
- Traffic gửi tới vùng khác hoặc Internet có thể phát sinh transfer cost.
- Việc truy cập lại nhiều lần nên dẫn tới đánh giá có cần đổi class hoặc copy sang một vùng/lớp phục vụ phù hợp không.

Không chuyển hàng loạt dữ liệu Archive sang Standard chỉ vì có một yêu cầu kiểm toán nhỏ; hãy ước lượng số object và dung lượng thực sự cần đọc.

## 9. Thực hành với `gcloud storage`

Ví dụ này dùng CLI của Google Cloud, project thử nghiệm và tên bucket minh họa. **Tạo bucket hoặc cập nhật class/lifecycle là thao tác thay đổi tài nguyên thực và có thể phát sinh phí**. Chỉ chạy khi đã có quyền và được phê duyệt; đừng sử dụng dữ liệu production để thử rule xóa.

### 9.1. Kiểm tra context và buckets

~~~bash
# READ-ONLY: xác nhận danh tính/project đang chọn.
gcloud auth list
gcloud config get-value project

# READ-ONLY: danh sách buckets của project được chỉ định.
gcloud storage buckets list \
  --project=retail-lab
~~~

Lệnh list chỉ hiện những tài nguyên người dùng có quyền xem. Không nhìn thấy bucket không đồng nghĩa bucket đó không tồn tại.

### 9.2. Tạo bucket regional Standard

~~~bash
PROJECT_ID="retail-lab"
BUCKET="retail-media-lab-unique-example"
LOCATION="asia-southeast1"

# WRITE: tên bucket phải duy nhất và hợp lệ; thay tên mẫu bằng tên được duyệt.
gcloud storage buckets create "gs://$BUCKET" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

**Uniform bucket-level access (UBLA)** giúp sử dụng mô hình phân quyền IAM thống nhất ở cấp bucket thay cho ACL trên object; tuy nhiên vẫn cần cấp role đúng và kiểm tra public access prevention nếu dữ liệu không được phép công khai. Không cho rằng lệnh tạo bucket đã cấp quyền đọc cho người dùng cuối hoặc đã hoàn tất chính sách bảo vệ dữ liệu.

Nếu tên đã có người sử dụng, hãy chọn tên khác. Không đặt thông tin bí mật, mã định danh khách hàng nhạy cảm hoặc token trong tên bucket/object.

### 9.3. Xem location và default class

~~~bash
# READ-ONLY: xem metadata của bucket.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(name,location,locationType,storageClass,autoclass)"

# READ-ONLY: xem đối tượng đang có trong bucket.
gcloud storage ls "gs://$BUCKET/"
~~~

Bucket mới có thể trống, nên lệnh liệt kê object không có kết quả cũng không phải lỗi. Khi đánh giá location, đối chiếu **`location` và `locationType`** với lựa chọn đã phê duyệt, không suy từ chuỗi tên bucket.

### 9.4. Upload và kiểm tra storage class của object

Giả sử người học đã có file ảnh nhỏ `sample.jpg` trên máy:

~~~bash
# WRITE: upload một object thử nghiệm.
gcloud storage cp sample.jpg "gs://$BUCKET/products/sample.jpg"

# READ-ONLY: xem metadata của object.
gcloud storage objects describe "gs://$BUCKET/products/sample.jpg" \
  --format="yaml(name,size,storageClass,timeCreated,updated)"
~~~

Nếu object được tạo mà không chỉ định storage class riêng, class thường lấy từ **default storage class của bucket**. Cần đọc field `storageClass` của **object**, không chỉ default ở bucket.

### 9.5. Đổi default storage class

~~~bash
# WRITE: ảnh hưởng default class của những object mới trong bucket thông thường.
gcloud storage buckets update "gs://$BUCKET" \
  --default-storage-class=NEARLINE

# READ-ONLY: xác minh default mới.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(location,storageClass)"
~~~

Lệnh đổi default **không chuyển class object cũ**. Nếu bucket đang bật Autoclass hoặc có ràng buộc khác, việc điều chỉnh class có thể bị giới hạn; hãy kiểm tra cấu hình và chính sách trước. Để tránh phí bất ngờ, không dùng `NEARLINE` làm default cho dữ liệu mới nếu thường xóa hoặc thay thế chỉ sau vài ngày.

### 9.6. Áp dụng lifecycle rule trong lab

Sau khi tạo file `lifecycle.json` với ví dụ ở phần 7.3 và kiểm tra nội dung kỹ:

~~~bash
# WRITE: cập nhật lifecycle rule của bucket thử nghiệm.
gcloud storage buckets update "gs://$BUCKET" \
  --lifecycle-file=lifecycle.json

# READ-ONLY: xem lifecycle hiện tại để xác nhận.
gcloud storage buckets describe "gs://$BUCKET" \
  --format="yaml(lifecycle)"
~~~

**Không chạy lệnh này để thay thế lifecycle trên bucket production mà chưa lưu cấu hình hiện tại và review đầy đủ**: cập nhật lifecycle có thể làm thay đổi bộ quy tắc đang được áp dụng. Thực thi hành động lifecycle thường là bất đồng bộ; không được đánh giá thành công chỉ dựa trên việc vài giây sau object chưa đổi class.

### 9.7. Vị trí bucket có đổi được không?

Không coi bucket location là một field có thể tự do cập nhật bằng `gcloud storage buckets update`. Nếu cần chuyển dữ liệu sang region/dual-region/multi-region khác, phải xem **khả năng bucket relocation của Google Cloud tại thời điểm triển khai** hoặc lập kế hoạch migration/copy sang bucket ở location mới.

Một migration/relocation phải kiểm tra:

- Công cụ có hỗ trợ **location nguồn, location đích, class và tính năng bucket** hiện tại không.
- Thời gian/số lượng object, phí chuyển và yêu cầu duy trì ứng dụng trong lúc chuyển.
- IAM, retention, versioning, soft delete, default encryption, event notifications và lifecycle.
- URI mà ứng dụng/CI/CD đang dùng; nếu bucket mới có tên khác, cần đổi cấu hình.
- Kế hoạch kiểm tra checksum, đối soát object versions và chuyển quyền truy cập theo thời điểm.

Không xóa bucket cũ cho tới khi dữ liệu và ứng dụng đã được xác minh an toàn ở đích.

## 10. Tình huống thực tế: ba nhóm dữ liệu của hệ thống bán lẻ

Giả sử tổ chức có:

- **Cloud Run** cung cấp API sản phẩm ở `asia-southeast1`.
- **GKE** xử lý và biến đổi ảnh.
- **Compute Engine** chạy tác vụ tổng hợp báo cáo.
- **Cloud SQL** lưu metadata đơn hàng.
- Yêu cầu phải kiểm soát truy cập và phân bổ chi phí theo đội nghiệp vụ.

Ba loại dữ liệu có đặc điểm khác nhau:

| Nhóm dữ liệu | Tần suất truy cập | Thời gian giữ | Rủi ro chính |
| --- | --- | --- | --- |
| **Ảnh đang bán** | Nhiều request mỗi ngày. | Có thể được cập nhật/thay thế thường xuyên. | Độ trễ tải ảnh, chi phí phân phối, xóa nhầm. |
| **Báo cáo định kỳ** | Đọc không thường xuyên, có thể tải nhiều file cùng lúc khi kiểm toán. | Vài tháng tới hơn một năm. | Phí truy xuất khi đọc nhiều, thay đổi class quá sớm. |
| **Hồ sơ lưu dài hạn** | Gần như không truy cập, trừ yêu cầu pháp lý. | Nhiều năm. | Yêu cầu residency/retention, xóa trái phép, chi phí lưu lâu. |

### 10.1. Đề xuất ban đầu

**Nhóm ảnh sản phẩm:**

~~~text
Bucket: retail-images-prod
Location: regional asia-southeast1 (nếu đáp ứng chính sách)
Default class: STANDARD
Consumers: Cloud Run / GKE / Cloud CDN khi phù hợp
~~~

Lý do: lưu lượng đọc cao; object có thể được cập nhật; cần xem cache, kiểm soát public access và quyền của service account. Với yêu cầu DR nghiêm ngặt qua nhiều region, đánh giá dual-region hoặc kế hoạch replication/khôi phục riêng thay vì chỉ giữ regional.

**Nhóm báo cáo:**

~~~text
Bucket: retail-reports-prod
Location: regional theo yêu cầu nghiệp vụ và residency
Class: STANDARD cho dữ liệu mới; lifecycle sang NEARLINE/COLDLINE
      khi đã đo tần suất truy cập và thời gian giữ.
~~~

Lý do: báo cáo mới có thể được xem thường xuyên vài tuần, báo cáo cũ ít dùng. Rule chuyển class phải tương thích với thời gian lưu tối thiểu và chính sách xóa.

**Nhóm hồ sơ lưu dài hạn:**

~~~text
Bucket: retail-compliance-archive
Location: lựa chọn được pháp chế và bảo mật chấp thuận
Class: ARCHIVE hoặc chuyển dần theo lifecycle
Protection: retention / holds / audit và phục hồi theo yêu cầu
~~~

Lý do: ít đọc, phải giữ lâu. Cần tính chi phí phục hồi khi có yêu cầu cung cấp hồ sơ và kiểm tra thời gian lưu tối thiểu. Đừng giả định Archive tự áp đặt retention không thể xóa.

### 10.2. Vì sao nên cân nhắc nhiều bucket?

Cloud Storage cho phép nhiều storage class trong cùng bucket, nhưng việc tách bucket có thể hữu ích khi:

- **Location yêu cầu khác nhau**: bucket chỉ có một location, nên dữ liệu phải ở region khác cần bucket khác.
- **Retention và quyền** khác nhau đáng kể giữa dữ liệu công khai và dữ liệu tuân thủ.
- **Autoclass/lifecycle** cần cấu hình khác nhau cho từng nhóm.
- Muốn tách trách nhiệm sở hữu, ngân sách, monitoring và cơ chế phát hành.

Không nên tạo một bucket cho từng tệp hoặc từng người dùng chỉ để phân loại chi phí. Quyết định ranh giới bucket dựa trên location, policy, vòng đời, quyền, sở hữu và khả năng vận hành.

### 10.3. Định tuyến quyền và dữ liệu

~~~mermaid
flowchart TD
    SHOP["Cloud Run: shop API"] --> IMG["Bucket ảnh: Standard / CDN"]
    ETL["GKE: image processing"] --> IMG
    REPORT["Compute Engine: report job"] --> RPT["Bucket báo cáo: lifecycle"]
    RPT --> ARC["Object classes lạnh theo tuổi"]
    AUDIT["Nhóm kiểm toán có quyền giới hạn"] --> COM["Bucket hồ sơ: Archive/retention"]
    IAM["Service accounts + IAM / policy"] -. "Phạm vi quyền" .-> IMG
    IAM -.-> RPT
    IAM -.-> COM
    OBS["Cloud Monitoring + Billing"] -. "Chi phí và truy cập" .-> IMG
    OBS -.-> RPT
    OBS -.-> COM
~~~

Ứng dụng phải được cấp **IAM role tối thiểu** trên bucket/object phù hợp; Cloud SQL và các dịch vụ khác vẫn sử dụng quyền riêng. Nếu muốn công bố ảnh công khai, cần thiết kế đường phục vụ (ví dụ Cloud CDN/load balancer) và access policy, không đưa tất cả bucket nội bộ vào chế độ public.

### 10.4. Luồng upload, chuyển class và khôi phục

1. Cloud Run/GKE upload một object và ghi metadata cần thiết trong Cloud SQL.
2. Đối với dữ liệu thường xuyên truy cập, object ở Standard; hệ thống phục vụ ảnh thông qua cache/CDN khi phù hợp.
3. Với báo cáo, lifecycle đánh giá tuổi object và các điều kiện, sau đó chuyển class khi đủ điều kiện.
4. Với hồ sơ tuân thủ, retention kiểm soát thời gian giữ; Archive hoặc class khác phản ánh tần suất truy cập, **không thay thế bảo vệ xóa**.
5. Khi cần khôi phục, đội vận hành xác minh danh tính, dữ liệu/version cần lấy, chi phí retrieval và lộ trình lưu kết quả phục hồi.
6. Sau yêu cầu phục hồi, đánh giá có cần điều chỉnh class hoặc chiến lược cache nếu tần suất đọc đã thay đổi.

## 11. Bảo mật và các chính sách cần thiết

### 11.1. Bucket location không phải quyền truy cập

Dữ liệu nằm trong đúng region chưa chắc an toàn nếu IAM cấp quá rộng. Một cấu hình lưu trữ production cần:

- **Uniform bucket-level access** khi muốn chuẩn hóa IAM thay cho object ACL.
- **Public Access Prevention** nếu bucket không được phép công khai, theo chính sách tổ chức.
- **Service accounts riêng** cho Cloud Run/GKE/Compute Engine; không dùng một tài khoản có quyền ghi/xóa trên mọi bucket.
- Giám sát thay đổi IAM, lifecycle, retention, encryption và chia sẻ dữ liệu.
- Cân nhắc **CMEK với Cloud KMS** khi tổ chức cần kiểm soát vòng đời khóa; location của key phải tương thích với bucket theo tài liệu.
- **Organization Policy** hạn chế locations hoặc cấu hình public access nếu được yêu cầu.

Cloud Storage tự mã hóa dữ liệu ở trạng thái lưu theo mô hình dịch vụ; việc chọn CMEK là một **quyết định quản trị khóa bổ sung**, không phải tùy chọn duy nhất để dữ liệu được mã hóa.

### 11.2. Khôi phục khi người dùng xóa nhầm

Phân biệt:

| Cơ chế | Mục tiêu | Không thay thế |
| --- | --- | --- |
| Dual-/multi-region | Redundancy địa lý theo dịch vụ. | Backup khi thao tác xóa/ghi nhầm. |
| Object Versioning | Giữ phiên bản object khi được thay thế/xóa theo cơ chế cấu hình. | Chính sách retention/phục hồi ở mọi tình huống. |
| Soft delete | Giữ dữ liệu đã xóa trong khoảng phục hồi theo chính sách. | Lưu giữ bất biến dài hạn. |
| Retention policy / object holds | Ngăn xóa hoặc thay đổi trước hạn khi được áp dụng. | Cơ chế dự phòng capacity/tính sẵn sàng của ứng dụng. |
| Backup/replication riêng | Khôi phục khi mất hoặc sai dữ liệu theo mục tiêu riêng. | Kiểm soát IAM và bảo mật nguồn. |

Kế hoạch **RPO** (mất dữ liệu tối đa chấp nhận) và **RTO** (thời gian khôi phục) phải được kiểm thử từ ứng dụng. Không coi việc tạo bucket dual-region là đủ để bảo đảm toàn bộ hệ thống Cloud Run, Cloud SQL và DNS sẽ hoạt động trong thảm họa.

### 11.3. Turbo replication

Trong những cấu hình **dual-region** đủ điều kiện, Google Cloud có tính năng **turbo replication** nhằm cải thiện mục tiêu replication so với chế độ mặc định theo đặc tính dịch vụ. Đây là quyết định có thể ảnh hưởng tới **giá, RPO và giới hạn cấu hình**. Nếu nghiệp vụ yêu cầu RPO rất chặt giữa hai region:

1. Xác định đúng loại dual-region có hỗ trợ turbo replication không.
2. Xem RPO/SLA và phí theo tài liệu hiện hành, không suy từ tên tính năng.
3. Thiết kế ứng dụng có thể truy cập dữ liệu và xử lý lỗi theo region.
4. Kiểm tra dự phòng các dịch vụ ngoài Cloud Storage.

Đừng hứa “RPO bằng 0” chỉ từ việc bật replication. Chấp nhận write, replication hoàn thành và khả năng truy cập khi sự cố là các sự kiện khác nhau.

## 12. Ước lượng chi phí trước khi chọn

### 12.1. Mô hình chi phí theo vòng đời

~~~text
Tổng chi phí lưu trữ dự kiến ≈
    Giá lưu theo class, location, dung lượng, thời gian
  + Phí retrieval và các loại API operations
  + Early deletion / class-change charges nếu có
  + Data transfer và nội dung phục vụ tới client
  + Phí replication hoặc tính năng bổ sung khi áp dụng
  + Versioning, soft delete, retention và dữ liệu không còn dùng
  + Logging, monitoring, các thành phần liên quan
~~~

Đây là công thức **phân loại chi phí**, không phải bảng giá chính thức. Từng loại phí có đơn vị và điều kiện cụ thể; cần xem **Cloud Storage pricing** theo location/class thực tế và đối chiếu báo cáo Billing.

### 12.2. Tạo bảng dữ liệu trước khi quyết định

| Nhóm object | Dung lượng trung bình | Số GET/tháng | Dữ liệu đọc ra/tháng | Thời gian giữ | Class đang cân nhắc |
| --- | --- | --- | --- | --- | --- |
| Ảnh đang bán | Dữ liệu đo từ bucket | Cao | Cao | Vài tháng, có thay thế | Standard |
| Báo cáo | Dữ liệu đo từ bucket | Thấp, theo đợt | Trung bình lúc kiểm toán | 6–18 tháng | Nearline/Coldline |
| Backup | Dữ liệu đo từ bucket | Hiếm | Có thể rất lớn khi restore | Trên 1 năm | Coldline/Archive |
| Dữ liệu tuân thủ | Dữ liệu đo từ bucket | Rất hiếm | Khó dự báo | Nhiều năm | Archive |

Không nhất thiết phải chốt class ngay khi chưa đo hành vi. Có thể khởi đầu bằng Standard cho dữ liệu mới, theo dõi thông số rồi dùng lifecycle hoặc Autoclass ở giai đoạn thích hợp.

### 12.3. Các tình huống làm dự toán sai

- Chỉ đếm dung lượng hiện hành mà bỏ **noncurrent object versions** hoặc soft-deleted data.
- Dùng Archive cho object thường được thay thế trước 365 ngày.
- Quên phí retrieval khi chạy job đọc lại toàn bộ backup.
- Đặt compute một region nhưng bucket ở vùng xa mà không tính inter-region data transfer.
- Sử dụng lifecycle có điều kiện `age` quá ngắn, phát sinh đổi class hoặc early deletion không mong muốn.
- Bỏ qua **Cloud CDN cache miss**, invalidation, egress và phí xử lý request.
- Không tính chi phí thử nghiệm, dữ liệu tạm và thao tác migration.

Khi chi phí không như kỳ vọng, hãy phân tích **số object, dung lượng theo class, số operations, retrieval, network transfer và retention** thay vì chỉ xem default class.

## 13. Troubleshooting khi location/class không như mong đợi

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không tạo được bucket tại location đã chọn. | Location không được hỗ trợ, org policy hạn chế, tên bucket đã tồn tại hoặc thiếu IAM. | Đọc lỗi API, `gcloud storage buckets create --help`, policy và danh sách location hỗ trợ. |
| Bucket tạo xong nhưng location sai nhu cầu. | Sai biến `LOCATION`, dùng tên multi-region thay region hoặc hiểu nhầm dual-region. | `gcloud storage buckets describe`; lập kế hoạch relocation/migration thay vì sửa tùy tiện. |
| Object mới không nằm ở class bucket default. | Client đã chỉ định storage class riêng hoặc Autoclass đang quản lý. | Xem metadata từng object, bucket Autoclass và hành vi công cụ upload. |
| Đổi default class mà object cũ không đổi. | Default chỉ dùng cho object mới. | Kiểm tra object metadata; áp lifecycle/transition theo kế hoạch. |
| Lifecycle chưa chuyển class đúng thời điểm. | Lifecycle bất đồng bộ, rule chưa khớp `age`, class hoặc prefix; policy hạn chế. | Đọc lifecycle, object metadata/tuổi và logs liên quan nếu có. |
| Object bị xóa trước dự kiến. | Rule Delete quá rộng, overwrite, lifecycle khác hoặc quyền xóa không đúng. | Kiểm tra lifecycle, audit logs, versioning/soft delete và retention. |
| Không xóa được object dù đã đủ tuổi lifecycle. | Retention policy, object hold hoặc chính sách khác chặn. | Xem cấu hình retention, holds và trạng thái version. |
| Chi phí Coldline/Archive cao. | Retrieval, early deletion, operations, nhiều versions hoặc transfer. | Cloud Billing, dữ liệu truy cập và vòng đời object. |
| Người dùng ở xa thấy ảnh tải chậm. | Cache miss, ứng dụng/proxy không hiệu quả, network path hoặc location chưa phù hợp. | Đo latency, CDN cache hit, DNS/TLS, transfer và backend. |
| VM không đọc được bucket cùng region. | Thiếu IAM, token, DNS, Private Google Access/egress hoặc lỗi ứng dụng. | Kiểm tra từ API/network tới authorization; không tự di chuyển bucket. |

### 13.1. Phương pháp điều tra sáu bước

1. **Xác định tài nguyên:** project, bucket name, location, locationType và default class thực tế.
2. **Xác định object:** storage class, tuổi, kích thước, phiên bản và thời gian update của object mẫu.
3. **Đọc policies:** IAM, public access, lifecycle, Autoclass, retention/holds, versioning và soft delete.
4. **Xác định request:** GET/LIST/PUT/DELETE, client identity, nơi chạy ứng dụng và số lượng thao tác.
5. **Đối chiếu kết quả và phí:** dùng thông tin lỗi API, logs, Billing và metric đã thu thập.
6. **Đổi trên môi trường thử:** đánh giá tác động với dữ liệu mẫu, có phê duyệt trước khi sửa bucket production.

Không xem chi phí tăng sau khi chuyển sang lớp lạnh là bằng chứng dịch vụ tính sai; truy xuất dữ liệu và thao tác trong vòng đời có thể làm tổng chi phí tăng ngay cả khi giá lưu cơ bản giảm.

## 14. Bài tập

### Bài 1 — Chọn location

Một hệ thống chạy hoàn toàn tại `asia-southeast1`, dữ liệu phải ở đúng region đó. Bạn chọn regional, dual-region hay multi-region? Nếu yêu cầu thay đổi thành phải khôi phục dữ liệu sau sự cố toàn region, điều kiện nào cần đánh giá?

**Gợi ý:** regional trước vì ràng buộc vị trí; khi cần DR, phải làm rõ region thứ hai có được phép, dual-region/backup có đáp ứng RPO/RTO và tác động chi phí hay không.

### Bài 2 — Chọn storage class

Chọn class cho ba object:

1. Ảnh sản phẩm bị truy cập liên tục và được thay thế sau một tuần.
2. Báo cáo có thể bị đọc lại một lần sau 45 ngày, giữ sáu tháng.
3. Hồ sơ ít truy cập, phải giữ năm năm.

**Gợi ý:** bắt đầu khảo sát Standard, Nearline/Coldline và Archive tương ứng; tính lại nếu pattern truy cập khác giả định hoặc có phí retrieval/early deletion.

### Bài 3 — Đọc metadata

Giả sử bucket default là `STANDARD`, nhưng một object trong bucket hiển thị `COLDLINE`. Điều gì có thể xảy ra? Hãy nêu ít nhất ba khả năng và lệnh đọc để kiểm tra.

**Gợi ý:** client chỉ định class khi upload, lifecycle đã chuyển, Autoclass quản lý (nếu được bật). Dùng `gcloud storage buckets describe` và `gcloud storage objects describe`.

### Bài 4 — Thiết kế lifecycle

Một nhóm cần báo cáo mới dùng Standard trong 30 ngày, sau đó Nearline cho tới 90 ngày, Coldline đến 365 ngày và Archive sau đó. Hãy xem JSON ở phần 7.3, giải thích cách `age` và `matchesStorageClass` phối hợp, và vì sao phải kiểm tra minimum duration.

### Bài 5 — Điều tra phí Archive

Đội kiểm toán yêu cầu tải toàn bộ các file Archive có dung lượng rất lớn về một vùng khác. Những khoản phí nào cần ước tính trước? Nếu kết quả phải được phân tích nhiều lần trong tháng, có nên tiếp tục đọc trực tiếp Archive mọi lần không?

**Gợi ý:** retrieval, operations, network transfer, thời gian lưu và vị trí bản dữ liệu phân tích; đánh giá sao chép/chuyển dữ liệu sang class/location phục vụ truy cập lặp lại.

### Bài 6 — Phân biệt độ bền và khôi phục

Một lập trình viên xóa nhầm object trong dual-region bucket. Dual-region có bảo đảm lấy lại phiên bản cũ không? Hãy đề xuất các cơ chế bảo vệ ngoài location.

**Gợi ý:** versioning, soft delete, retention/holds, backup độc lập theo nhu cầu và chính sách quyền tối thiểu.

### Bài 7 — Tình huống đa ứng dụng

Cloud Run và GKE chạy tại Singapore, Compute Engine tạo báo cáo hàng tháng, dữ liệu tuân thủ phải giữ bảy năm. Hãy thiết kế **ít nhất hai bucket**, ghi rõ location/class, vòng đời, quyền truy cập và chỉ số chi phí cần quan sát; giải thích vì sao không dùng một cấu hình cho mọi nhóm dữ liệu.

## 15. Checklist triển khai production

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| **Ownership** | Có người sở hữu dữ liệu, project, bucket và phân bổ chi phí. |
| **Location** | Region/dual-region/multi-region phù hợp workload, pháp lý và mục tiêu DR. |
| **Data residency** | Xác minh phạm vi location, replication, KMS, logs, backups và dữ liệu phụ trợ. |
| **Storage class** | Chọn theo access pattern, kích thước, tuổi dữ liệu và nhu cầu phục hồi. |
| **Default vs object class** | Đã kiểm tra class thực tế của object mới/cũ, không suy từ bucket default. |
| **Minimum duration** | Đã tính phí nếu xóa/thay/đổi class sớm (30/90/365 ngày theo class). |
| **Lifecycle/Autoclass** | Chọn một chiến lược tương thích, rule được review và thử trên dữ liệu mẫu. |
| **Retention/Versioning** | Hiểu vòng đời noncurrent versions, holds, soft delete và khả năng phục hồi. |
| **Security** | IAM tối thiểu, UBLA, public access, encryption/KMS, audit phù hợp. |
| **Networking** | Cloud Run/GKE/VM gọi được APIs qua đường phù hợp, không cần mở quyền rộng. |
| **Performance** | Đo latency GET/PUT, throughput, cache hit và dữ liệu truyền giữa vùng. |
| **Costs** | Dự toán storage, retrieval, operations, transfer, retention, versions và replication. |
| **Operations** | Monitoring, Billing alerts, runbook khôi phục và kế hoạch migration. |
| **Validation** | Thử upload, tải, đọc metadata, chuyển class và phục hồi theo yêu cầu thật. |

## 16. Tài liệu chính thức và ghi nhớ

Tính năng, quy tắc hỗ trợ dual-region, Autoclass, minimum storage duration và bảng giá có thể thay đổi. Trước khi triển khai hoặc tự động hóa ở quy mô lớn, đối chiếu tài liệu chính thức:

- [Cloud Storage locations](https://cloud.google.com/storage/docs/locations)
- [Cloud Storage classes](https://cloud.google.com/storage/docs/storage-classes)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Create a bucket](https://cloud.google.com/storage/docs/creating-buckets)
- [Bucket relocation](https://cloud.google.com/storage/docs/bucket-relocation/overview)
- [Object Lifecycle Management](https://cloud.google.com/storage/docs/lifecycle)
- [Autoclass](https://cloud.google.com/storage/docs/autoclass)
- [Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Soft delete](https://cloud.google.com/storage/docs/soft-delete)
- [Retention policies and Bucket Lock](https://cloud.google.com/storage/docs/bucket-lock)
- [Uniform bucket-level access](https://cloud.google.com/storage/docs/uniform-bucket-level-access)
- [Dual-region turbo replication](https://cloud.google.com/storage/docs/availability-durability)
- [gcloud storage reference](https://cloud.google.com/sdk/gcloud/reference/storage)

**Điểm cần ghi nhớ:** **bucket location** trả lời câu hỏi dữ liệu được lưu ở phạm vi địa lý và mô hình dự phòng nào; **storage class** trả lời bài toán tần suất truy cập và chi phí lưu theo vòng đời. Chỉ khi kết hợp đúng hai quyết định đó với IAM, retention, lifecycle/Autoclass, khả năng phục hồi, mạng và dữ liệu Billing thực tế, đội vận hành mới có một thiết kế Cloud Storage vừa phù hợp nghiệp vụ vừa có thể kiểm chứng về bảo mật, độ tin cậy và chi phí.
