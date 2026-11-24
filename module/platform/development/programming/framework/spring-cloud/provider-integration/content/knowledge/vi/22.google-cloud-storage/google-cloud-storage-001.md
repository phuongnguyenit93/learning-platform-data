# Bucket, object name, generation và metadata trên Google Cloud

## 1. Bối cảnh: lưu trữ object trên Google Cloud

Một ứng dụng Spring Boot có thể cần lưu tài liệu người dùng, ảnh, bản xuất báo cáo, tệp log hoặc dữ liệu trao đổi giữa các service. Trên Google Cloud, dịch vụ lưu trữ object phổ biến là **Cloud Storage**. Ứng dụng tổ chức dữ liệu trong **bucket**, định danh từng object bằng **object name**, theo dõi phiên bản dữ liệu qua **generation**, và mô tả nội dung bằng **metadata**.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng tới thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học danh tính và quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này đặt nền tảng cho nhánh Google Cloud Storage trước khi triển khai adapter Spring và kiểm thử tích hợp.

Sau bài học, bạn có thể:

- Phân biệt project, bucket, object name và object data.
- Giải thích vì sao dấu / trong object name thường chỉ là quy ước prefix, không mặc nhiên là thư mục thật.
- Phân biệt **generation** với **metageneration**, hiểu versioning và precondition.
- Chọn metadata hệ thống và custom metadata đúng mục đích.
- Thiết kế tên bucket/object, location, storage class, quyền truy cập và chính sách vòng đời.
- Gọi Cloud Storage từ Java/Spring Boot bằng client library và Application Default Credentials.
- Kiểm thử upload, đọc, cập nhật metadata và xử lý xung đột ghi an toàn.

> **Phạm vi:** Bài tập trung vào Google Cloud Storage (GCS) và Java client library **google-cloud-storage**. Các ví dụ về bucket, project, region và tên object là dữ liệu minh họa. Artifact, API và cấu hình Spring Cloud GCP/Google Cloud Spring cần chọn theo release tương thích với Spring Boot và Java của dự án.

## 2. Mô hình tài nguyên: project, bucket và object

Cloud Storage lưu dữ liệu dạng object. Một object gồm **dữ liệu (bytes)**, **tên định danh**, **generation** và **metadata**. Object được chứa trong bucket; bucket thuộc một Google Cloud project.

~~~mermaid
flowchart TD
    P["Google Cloud project"] --> B["Cloud Storage bucket"]
    B --> O1["Object: reports/2026/report-001.pdf"]
    B --> O2["Object: avatars/user-123.png"]
    B --> O3["Object: exports/daily.csv"]
    O1 --> G1["Generation: phiên bản dữ liệu"]
    O1 --> M1["Metageneration: phiên bản metadata"]
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Project | **training-platform-dev** | Ranh giới quản lý, IAM, billing và quota |
| Bucket | **training-documents-dev** | Container lưu trữ object, có location và cấu hình |
| Object name | **reports/2026/report-001.pdf** | Định danh object trong bucket |
| Object data | Nội dung PDF | Dãy byte được lưu trữ |
| Generation | **1740000000000000** (minh họa) | Định danh một phiên bản dữ liệu object |
| Metageneration | **3** (minh họa) | Định danh phiên bản metadata của một generation |

Đường dẫn **gs://training-documents-dev/reports/2026/report-001.pdf** là cách biểu diễn bucket và object name trong công cụ GCP. Nó **không phải** đường dẫn file local và cũng không phải URL HTTP công khai để mọi người tải được.

### 2.1. Bucket là ranh giới cấu hình quan trọng

Một bucket có các thuộc tính và chính sách ảnh hưởng đến mọi object bên trong, ví dụ:

- **Location:** region, dual-region hoặc multi-region.
- **Default storage class:** lớp lưu trữ mặc định cho object mới nếu không chỉ định khác.
- **Access control:** IAM và, nếu bật mô hình cũ, ACL.
- **Uniform bucket-level access (UBLA):** thống nhất quản lý quyền qua IAM ở cấp bucket/project.
- **Public access prevention:** ngăn vô tình cấp quyền public.
- **Object versioning:** giữ các generation cũ khi object bị ghi đè hoặc xóa theo cơ chế versioning.
- **Lifecycle management:** tự động chuyển storage class hoặc xóa object/phiên bản theo điều kiện.
- **Retention policy / Bucket Lock:** kiểm soát thời gian lưu giữ và khả năng thay đổi chính sách.

Bucket thuộc project cụ thể; quyền tạo bucket, xem bucket và truy cập object là các IAM permission khác nhau. Không nên coi một bucket name là bí mật hoặc dùng tên bucket để thay thế kiểm tra quyền.

### 2.2. Tên bucket và location

Tên bucket Cloud Storage phải tuân thủ quy tắc đặt tên của GCP và có tính duy nhất trong namespace Cloud Storage. Vì tên được dùng trong nhiều URI/hostname, nên đặt tên ổn định, dễ nhận biết môi trường, tránh thông tin cá nhân hoặc dữ liệu nhạy cảm. Hãy dùng gcloud hoặc API để xác nhận tên hợp lệ trước khi provision.

Ví dụ:

- **acme-documents-dev**
- **acme-documents-staging**
- **acme-documents-prod**

Không nên đặt một bucket duy nhất dùng chung mọi môi trường chỉ để giảm số lượng tài nguyên. Tách bucket/project giúp giới hạn IAM, lifecycle, dữ liệu và chi phí.

Location quyết định nơi dữ liệu được lưu trữ và có thể ảnh hưởng độ trễ, khả năng sẵn sàng, tuân thủ dữ liệu và chi phí network. Cần chọn location phù hợp với ứng dụng và yêu cầu dữ liệu trước khi tạo bucket; **không nên thiết kế quy trình như thể có thể đổi location bucket tùy ý sau khi đã sử dụng**. Storage class là quyết định khác với location: cùng một location có thể chứa object ở các lớp lưu trữ khác nhau theo cấu hình hỗ trợ.

## 3. Bucket location và storage class

### 3.1. Location

Cloud Storage hỗ trợ các kiểu location, điển hình:

| Kiểu location | Ý nghĩa khái quát | Khi cân nhắc |
| --- | --- | --- |
| Region | Dữ liệu đặt trong một region | Ứng dụng cần vị trí cụ thể, độ trễ gần workload hoặc yêu cầu data residency |
| Dual-region | Dữ liệu được lưu trong một cặp region theo cấu hình GCP | Cần tính sẵn sàng/khả năng phục hồi giữa hai vùng được hỗ trợ |
| Multi-region | Dữ liệu đặt trong khu vực địa lý rộng hơn | Truy cập phân tán và yêu cầu availability ở phạm vi rộng |

Location không phải thuộc tính của object name. Không mã hóa **asia-southeast1** vào mọi key để giả lập location; location thuộc bucket. Nếu ứng dụng cần lưu dữ liệu ở nhiều vùng, có thể quản lý nhiều bucket và định tuyến theo yêu cầu nghiệp vụ.

### 3.2. Storage class

Các lớp lưu trữ thường gặp:

- **Standard:** dữ liệu truy cập thường xuyên.
- **Nearline:** dữ liệu ít truy cập, thường có chu kỳ lưu trữ phù hợp hơn.
- **Coldline:** dữ liệu hiếm khi truy cập.
- **Archive:** dữ liệu rất ít truy cập, thiên về lưu trữ dài hạn.

Storage class ảnh hưởng giá lưu trữ, chi phí truy xuất, thời lượng tối thiểu hoặc phí liên quan theo điều khoản dịch vụ. Không nên chỉ nhìn giá mỗi GB để chọn class; phải đánh giá tần suất đọc, vòng đời, retrieval fee và nhu cầu phục hồi.

Một bucket có default storage class; từng object cũng có storage class thực tế. Lifecycle rule có thể tự chuyển class theo tuổi hoặc điều kiện, tùy cấu hình. Vì vậy, khi phân tích object cụ thể, hãy đọc storage class của **object**, không suy ra chỉ từ tên bucket.

## 4. Object name: định danh, prefix và cách tổ chức dữ liệu

### 4.1. Cloud Storage có flat namespace theo mặc định

Trong bucket dùng flat namespace, object name là một chuỗi định danh. Dấu / là ký tự trong tên object, thường được dùng làm **delimiter quy ước** để nhóm object theo prefix.

Ví dụ ba object:

~~~text
reports/2026/january.csv
reports/2026/february.csv
reports/2025/annual.csv
~~~

Cloud Console và các công cụ thường hiển thị những prefix như **reports/2026/** dưới dạng thư mục để dễ duyệt. Nhưng trong mô hình flat namespace, các “folder” này thường **không phải tài nguyên thư mục độc lập**. Object thực sự là chuỗi tên đầy đủ.

Điều này dẫn đến một số hệ quả:

- **reports/2026/january.csv** là một object name duy nhất.
- Prefix **reports/2026/** giúp lọc danh sách object.
- Xóa object **reports/2026/january.csv** không đồng nghĩa xóa một thư mục vật lý.
- Có thể tồn tại object tên **reports/2026/** như một object rỗng; việc console hiển thị folder marker không biến mọi prefix thành directory.

### 4.2. Hierarchical namespace là lựa chọn riêng

Cloud Storage có hỗ trợ **hierarchical namespace (HNS)** cho bucket được cấu hình phù hợp. Khi bật HNS, folder trở thành tài nguyên có cấu trúc phân cấp rõ hơn và có thể hỗ trợ thao tác folder như rename ở cấp thư mục theo semantics của dịch vụ. HNS có yêu cầu/giới hạn riêng và không nên mặc định có trên mọi bucket.

Khi thiết kế ứng dụng, cần xác định bucket dùng flat namespace hay HNS; không dựa vào giao diện Console để suy luận. Một ứng dụng chỉ cần lưu object theo key/prefix thường không cần folder resource thật.

### 4.3. Thiết kế object name

Một object name có thể tổ chức theo nghiệp vụ:

~~~text
receipts/{tenantId}/{yyyy}/{MM}/{documentId}.pdf
avatars/{userId}/{version}.webp
exports/{jobId}/result.csv
events/{yyyy}/{MM}/{dd}/{eventId}.json
~~~

Khuyến nghị:

1. Dùng định danh ổn định như UUID/ID nghiệp vụ thay cho tên file người dùng làm định danh chính.
2. Chọn prefix hỗ trợ truy vấn, phân quyền, lifecycle và dọn dữ liệu.
3. Không đưa email, số điện thoại, access token, secret hoặc dữ liệu nhạy cảm vào object name.
4. Chuẩn hóa ký tự, dấu cách và Unicode nếu tên được đưa vào URL, log hoặc hệ thống khác.
5. Tránh tạo quy ước khó phân biệt giữa **a/b**, **a//b**, **a/../b** và các chuỗi tương tự; GCS không tự biến object name thành đường dẫn an toàn cho filesystem.
6. Không dùng object name làm cơ chế phân quyền. IAM và policy mới là lớp kiểm soát truy cập.

Object name có giới hạn độ dài và quy tắc ký tự theo Cloud Storage; nếu hệ thống nhận tên từ người dùng, phải validate và encode đúng khi chuyển qua URL/HTTP. Không nối chuỗi trực tiếp từ input vào URL hoặc đường dẫn local.

### 4.4. Prefix hỗ trợ list và tổ chức dữ liệu, không thay IAM

Giả sử bucket có:

~~~text
receipts/tenant-a/2026/receipt-001.pdf
receipts/tenant-a/2026/receipt-002.pdf
receipts/tenant-b/2026/receipt-003.pdf
~~~

Ứng dụng có thể liệt kê theo prefix **receipts/tenant-a/**. Tuy nhiên, nếu IAM cho phép đọc toàn bucket thì prefix trong code không phải ranh giới bảo mật. Muốn giới hạn tenant, cần thiết kế IAM condition/authorization phù hợp, bucket/project separation hoặc adapter kiểm soát quyền đáng tin cậy; không dựa vào việc client tự truyền prefix.

## 5. Generation: phiên bản dữ liệu của object

**Generation** là giá trị do Cloud Storage gán cho một phiên bản dữ liệu của object. Khi tạo object hoặc thay thế nội dung object, GCS tạo generation mới. Generation giúp xác định chính xác phiên bản bytes đang được tham chiếu.

Ví dụ minh họa:

| Thời điểm | Thao tác | Generation |
| --- | --- | --- |
| T1 | Tạo **reports/summary.csv** với nội dung A | **1001** |
| T2 | Ghi đè cùng object name bằng nội dung B | **1002** |
| T3 | Ghi đè tiếp bằng nội dung C | **1003** |

Các số trên chỉ để minh họa; generation thực tế do GCS cấp. **Không tự sinh generation** và không diễn giải generation như timestamp. Hãy coi nó là định danh phiên bản dùng cho so sánh và precondition.

### 5.1. Generation khác object name

Object name trả lời: “Đang nói tới object nào trong bucket?”

Generation trả lời: “Đang nói tới phiên bản dữ liệu nào của object đó?”

Một object name có thể trải qua nhiều generation theo thời gian. Khi ứng dụng chỉ lưu bucket và object name, nó thường trỏ đến **live version** tại thời điểm request. Nếu nghiệp vụ cần đọc lại đúng nội dung đã xử lý, nên lưu thêm generation tương ứng hoặc cơ chế versioning/audit phù hợp.

### 5.2. Generation thay đổi khi nào?

- Tạo object mới: GCS gán generation cho object.
- Thay thế nội dung object cùng tên: generation mới được gán.
- Chỉ cập nhật metadata của cùng phiên bản dữ liệu: generation không đổi; metageneration thay đổi.
- Xóa object: generation của phiên bản bị xóa không biến thành một generation mới của dữ liệu; hành vi khôi phục phụ thuộc Object Versioning, soft delete, retention và chính sách liên quan.

Không sử dụng generation như bộ đếm nghiệp vụ hay thứ tự sự kiện toàn hệ thống. Nó thuộc vòng đời object trong GCS.

## 6. Metageneration: phiên bản metadata

**Metageneration** định danh phiên bản metadata của một generation. Khi metadata của object được cập nhật, metageneration thay đổi; bytes của object không nhất thiết thay đổi.

Ví dụ:

| Thao tác | Generation | Metageneration |
| --- | --- | --- |
| Upload object mới | **1001** | **1** (minh họa) |
| Đổi Content-Type | **1001** | **2** |
| Thêm custom metadata reviewed=true | **1001** | **3** |
| Ghi đè object data | **1002** | phiên bản metadata mới |

Các giá trị cụ thể trong bảng là minh họa. Quy tắc cần nhớ:

- **Generation** gắn với phiên bản dữ liệu.
- **Metageneration** gắn với phiên bản metadata của generation đó.
- Update metadata không tạo object data generation mới.
- Khi data generation mới xuất hiện, metadata của generation mới cũng thuộc vòng đời mới.

Metageneration rất hữu ích khi nhiều service cùng chỉnh metadata. Ví dụ worker A thêm **classification=approved**, worker B đồng thời sửa **reviewer=team-2**. Nếu không có precondition, một lần ghi metadata có thể ghi đè thay đổi của lần còn lại tùy cách cập nhật. Dùng **ifMetagenerationMatch** để chỉ cập nhật nếu metadata vẫn ở phiên bản mà worker đã đọc.

## 7. Object Versioning, soft delete và retention

### 7.1. Object Versioning

Khi bật **Object Versioning** cho bucket, thao tác thay thế hoặc xóa object live có thể giữ phiên bản cũ dưới dạng **noncurrent version** thay vì loại bỏ ngay. Các phiên bản được phân biệt bằng generation.

Ví dụ:

~~~text
Object name: reports/summary.csv

Live generation:       1003  (nội dung C)
Noncurrent generation: 1002  (nội dung B)
Noncurrent generation: 1001  (nội dung A)
~~~

Ứng dụng có thể tham chiếu phiên bản cụ thể qua generation khi API/SDK hỗ trợ. Việc giữ nhiều phiên bản làm tăng dung lượng lưu trữ và chi phí; nên thiết kế lifecycle rule để xóa noncurrent versions sau thời hạn phù hợp.

**Object Versioning không phải backup hoàn chỉnh.** Nó không thay thế việc kiểm soát quyền xóa bucket, bảo vệ account, replication/backup chiến lược, retention policy hoặc quy trình phục hồi. Người có quyền xóa phiên bản và lifecycle rule vẫn có thể loại bỏ dữ liệu.

### 7.2. Soft delete

Cloud Storage có cơ chế **soft delete** để giữ object đã bị xóa trong một khoảng thời gian retention được cấu hình. Đây là khái niệm riêng với Object Versioning. Một bucket có thể có versioning và soft delete theo cấu hình hỗ trợ, nhưng cần hiểu hai cơ chế lưu giữ và phục hồi khác nhau.

Không giả định mọi bucket có cùng retention mặc định; kiểm tra cấu hình thực tế của bucket và chính sách tổ chức. Sau khi thời gian soft delete hết hạn hoặc object bị xóa vĩnh viễn theo cơ chế tương ứng, khả năng khôi phục không còn.

### 7.3. Retention policy và Bucket Lock

Retention policy đặt thời gian tối thiểu mà object phải được giữ trước khi có thể xóa/thay đổi theo quy tắc. **Bucket Lock** có thể khóa retention policy theo cách không thể giảm hoặc loại bỏ chính sách sau khi khóa. Đây là lựa chọn có ảnh hưởng lớn tới quản trị dữ liệu; cần review yêu cầu pháp lý, lifecycle, chi phí và quy trình trước khi áp dụng.

Ba khái niệm cần tách:

| Cơ chế | Bảo vệ điều gì? | Cần lưu ý |
| --- | --- | --- |
| Object Versioning | Giữ generation cũ khi thay thế/xóa object theo semantics versioning | Tốn storage; cần lifecycle cleanup |
| Soft delete | Giữ object bị xóa trong thời gian retention cấu hình | Có thời hạn; khác noncurrent version |
| Retention policy / Bucket Lock | Ngăn xóa/sửa trước thời hạn giữ bắt buộc | Khó thay đổi sau khi lock; cần quyết định quản trị |

## 8. Preconditions: ghi dữ liệu an toàn khi nhiều service cùng truy cập

Một hệ thống nhiều worker có thể cùng tạo hoặc cập nhật object. Nếu tất cả đều ghi mà không kiểm tra phiên bản hiện tại, có nguy cơ **lost update**: một thay đổi hợp lệ bị ghi đè bởi request khác.

Cloud Storage hỗ trợ generation và metageneration preconditions để bảo vệ thao tác theo kiểu compare-and-set.

### 8.1. ifGenerationMatch

Điều kiện **ifGenerationMatch=N** yêu cầu generation hiện tại phải bằng N trước khi operation được thực hiện.

- **ifGenerationMatch=0:** chỉ thành công nếu hiện không có live object với tên đó.
- **ifGenerationMatch=1001:** chỉ thành công nếu live generation vẫn là 1001.
- Nếu điều kiện không khớp, request thất bại với lỗi precondition (thường là HTTP 412).

Ví dụ nghiệp vụ: hai worker cùng đọc object generation 1001. Worker A ghi nội dung mới thành công, tạo generation 1002. Worker B vẫn gửi request với **ifGenerationMatch=1001**; request B bị từ chối thay vì âm thầm ghi đè dữ liệu mới của A.

### 8.2. ifMetagenerationMatch

Dùng khi cập nhật metadata mà không muốn thay đổi của service khác bị ghi đè:

- Đọc object với metageneration 3.
- Tạo bản metadata mới dựa trên dữ liệu vừa đọc.
- Chỉ cập nhật nếu **ifMetagenerationMatch=3**.
- Nếu service khác đã sửa metadata thành metageneration 4, request sẽ thất bại và cần đọc lại rồi hợp nhất.

### 8.3. Tạo object chỉ khi chưa tồn tại

Một upload cần đảm bảo không ghi đè object hiện có có thể sử dụng precondition **ifGenerationMatch=0**. Đây là cách chống trùng tên và tránh ghi đè trong race condition; chỉ kiểm tra “object chưa tồn tại” ở application rồi upload sau đó **không an toàn** vì giữa hai bước có thể có worker khác tạo object.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant G as Cloud Storage
    participant B as Worker B
    A->>G: Upload key X, ifGenerationMatch=0
    G-->>A: Success, generation 1001
    B->>G: Upload key X, ifGenerationMatch=0
    G-->>B: Precondition Failed (412)
    Note over A,B: B không ghi đè object của A
~~~

### 8.4. Khi precondition thất bại

Không coi mọi HTTP 412 là lỗi hệ thống cần retry ngay. Đây có thể là **xung đột nghiệp vụ**. Ứng dụng nên:

1. Đọc lại object/generation/metageneration mới nhất nếu có quyền.
2. Quyết định có thể merge, tạo object name khác hay yêu cầu người dùng giải quyết.
3. Nếu retry, tạo request với precondition mới sau khi đã đánh giá logic nghiệp vụ.
4. Ghi log generation/metageneration và request ID cần thiết, không log dữ liệu nhạy cảm.

## 9. Metadata: mô tả object và cách sử dụng

### 9.1. System metadata

Cloud Storage quản lý các trường hệ thống như:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Content-Type | MIME type của nội dung | application/pdf |
| Cache-Control | Hành vi cache | private, max-age=3600 |
| Content-Disposition | Cách trình duyệt xử lý nội dung | attachment; filename="report.pdf" |
| Content-Encoding | Kiểu encoding của object | gzip |
| Content-Language | Ngôn ngữ nội dung | vi |
| Storage class | Lớp lưu trữ object | STANDARD |
| Size | Kích thước bytes | 1048576 |
| Time created / updated | Thời điểm tạo/cập nhật theo API | timestamp |
| CRC32C / MD5 hash | Checksum phục vụ kiểm tra toàn vẹn | giá trị checksum |
| Generation / Metageneration | Phiên bản dữ liệu/metadata | số generation |

Không phải mọi trường đều do ứng dụng có thể tự đặt tùy ý. Một số trường do GCS tính hoặc quản lý, một số trường có thể được thiết lập khi tạo/cập nhật object. Cần đọc API cụ thể trước khi xây adapter generic.

### 9.2. Custom metadata

Ứng dụng có thể gắn các cặp key-value tùy chỉnh, ví dụ:

~~~json
{
  "document-id": "doc-2026-001",
  "tenant-id": "tenant-a",
  "classification": "internal",
  "source-system": "document-api"
}
~~~

Trong Cloud Storage custom metadata được biểu diễn như map key/value dạng chuỗi. Ví dụ Java có thể truyền **Map<String, String>** qua **BlobInfo.Builder.setMetadata(...)**.

Custom metadata phù hợp với thuộc tính nhỏ phục vụ tra cứu hoặc xử lý object, không phải nơi lưu toàn bộ nội dung nghiệp vụ, dữ liệu JSON lớn hay secret. Đặt tên key ổn định, có namespace khi nhiều team cùng dùng và thống nhất quy tắc cập nhật.

### 9.3. Metadata không thay thế database

Không nên dùng custom metadata làm kho dữ liệu truy vấn phức tạp:

- GCS không phải cơ sở dữ liệu quan hệ để query tùy ý theo mọi metadata key.
- Việc list object theo prefix khác với tìm kiếm theo một custom metadata field.
- Metadata update có thể tạo cạnh tranh và cần precondition.
- Metadata có giới hạn kích thước và có thể bị đọc bởi principal được phép đọc object metadata.

Nếu cần tìm kiếm theo tenantId, trạng thái phê duyệt, người sở hữu hoặc thời gian nghiệp vụ, hãy cân nhắc database/index riêng; metadata chỉ là thông tin bổ trợ gắn với object.

### 9.4. Content-Type và Cache-Control ảnh hưởng cách phân phối

Nếu upload PDF nhưng không đặt Content-Type, client downstream có thể nhận metadata không như mong muốn. Nếu object là dữ liệu riêng tư mà đặt Cache-Control: public, max-age=..., cache trung gian có thể lưu nội dung theo cách không phù hợp với chính sách bảo mật.

Hãy chọn Content-Type dựa trên nội dung đã xác thực, không chỉ dựa vào extension do người dùng gửi. Với tài liệu nhạy cảm, thiết kế cache/disposition và cơ chế truy cập (ví dụ signed URL có thời hạn) phù hợp.

## 10. Generation, ETag và checksum: đừng nhầm lẫn

| Giá trị | Mục đích | Có nên dùng làm version token? |
| --- | --- | --- |
| Generation | Định danh phiên bản dữ liệu của object | **Có**, dùng precondition phù hợp |
| Metageneration | Định danh phiên bản metadata | **Có**, khi bảo vệ metadata update |
| ETag | Giá trị validator do API cung cấp | Không nên mặc định coi là generation hoặc MD5 |
| CRC32C / MD5 | Kiểm tra tính toàn vẹn dữ liệu theo hỗ trợ của API | Dùng cho checksum, không thay generation |

ETag có thể hữu ích trong các request có conditional header phù hợp, nhưng không nên tự suy rằng ETag luôn là MD5 của bytes. Với multipart/composite object hoặc các chế độ mã hóa, quan hệ giữa ETag và MD5 có thể không như giả định. Nếu cần kiểm tra dữ liệu, dùng checksum mà Cloud Storage/client library hỗ trợ và hiểu semantics của nó.

## 11. IAM và mô hình quyền truy cập bucket/object

Cloud Storage hỗ trợ IAM ở cấp project/bucket và có thể có ACL theo mô hình cũ. Với thiết kế mới, thường nên ưu tiên **Uniform bucket-level access (UBLA)** để quản lý quyền qua IAM thay vì trộn nhiều ACL object/bucket.

Một số predefined role thường gặp:

| Role | Phạm vi năng lực khái quát | Ví dụ tình huống |
| --- | --- | --- |
| roles/storage.objectViewer | Đọc object và metadata theo phạm vi được cấp | Service chỉ tải tài liệu |
| roles/storage.objectCreator | Tạo object; không mặc nhiên có quyền đọc/xóa/ghi đè object hiện có | Service nhận upload mới |
| roles/storage.objectUser | Tập quyền thao tác object rộng hơn, theo định nghĩa role | Ứng dụng cần tạo/đọc/cập nhật/xóa object |
| roles/storage.objectAdmin | Quản trị object trong phạm vi cấp quyền | Công cụ vận hành/dọn dữ liệu |
| roles/storage.admin | Quản trị rộng bucket/object và cấu hình Storage theo role | Quản trị viên hạ tầng |

Role cụ thể phải được gán ở đúng resource scope. Không cấp **roles/storage.admin** cho runtime service chỉ vì nó cần upload file. Nếu cần tách đọc/ghi, có thể tạo custom role hoặc dùng predefined roles phù hợp.

**Public access prevention** giúp ngăn cấp quyền public ngoài ý muốn; **UBLA** giúp bỏ ACL khỏi đường quản trị. Chúng giải quyết các vấn đề khác nhau và có thể được sử dụng cùng nhau theo yêu cầu bảo mật. Không bật public access chỉ để test nhanh tải file; hãy dùng principal có quyền hoặc signed URL có thời hạn khi phù hợp.

### 11.1. Signed URL không phải public bucket

Signed URL là URL mang chữ ký và thời hạn cho một thao tác/tài nguyên cụ thể. Người có URL có thể thực hiện thao tác được ký trong thời gian hiệu lực theo điều kiện hỗ trợ; do đó URL phải được xem như bearer token và không log/chia sẻ công khai.

Signed URL không thay thế IAM tổng thể, cũng không biến bucket thành public. Ứng dụng cần kiểm soát ai được yêu cầu tạo URL, thời hạn, method và object key.

## 12. Thực hành tạo bucket và upload object bằng gcloud

### 12.1. Chọn project và location

Trước khi tạo bucket, xác nhận project hiện tại:

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID
~~~

Tạo bucket ở một region phù hợp, ví dụ:

~~~bash
gcloud storage buckets create gs://training-documents-dev \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --uniform-bucket-level-access
~~~

**training-documents-dev** và **PROJECT_ID** là placeholder. Tên bucket phải duy nhất theo namespace GCS và hợp lệ theo quy tắc đặt tên hiện hành. Lệnh tạo bucket là thao tác provisioning; chỉ chạy trong project dev đã được cấp quyền.

### 12.2. Upload một object theo prefix

~~~bash
gcloud storage cp ./sample.pdf \
  gs://training-documents-dev/reports/2026/sample.pdf
~~~

Sau khi upload, tên object là **reports/2026/sample.pdf**. Prefix **reports/2026/** giúp nhóm object; với flat namespace, nó không nhất thiết là folder resource.

### 12.3. Xem metadata và generation

~~~bash
gcloud storage objects describe \
  gs://training-documents-dev/reports/2026/sample.pdf
~~~

Lệnh describe có thể trả về thông tin như bucket, name, generation, metageneration, contentType, size, checksums, storageClass và timestamps tùy phiên bản CLI/output. Dùng kết quả này để ghi nhận generation thực tế, không tự giả định giá trị.

### 12.4. Cập nhật custom metadata

Ví dụ với CLI có hỗ trợ cờ cập nhật custom metadata:

~~~bash
gcloud storage objects update \
  gs://training-documents-dev/reports/2026/sample.pdf \
  --update-custom-metadata=classification=internal,source=training
~~~

Cú pháp/khả năng của cờ metadata có thể thay đổi theo phiên bản gcloud; kiểm tra **gcloud storage objects update --help** của CLI đang dùng. Sau khi update, xem lại object describe để quan sát metadata và metageneration. Không đặt secret hoặc dữ liệu nhạy cảm vào custom metadata.

### 12.5. Bật Object Versioning

~~~bash
gcloud storage buckets update \
  gs://training-documents-dev \
  --versioning
~~~

Sau khi bật, ghi đè một object cùng tên rồi kiểm tra các generation. Versioning có thể tăng dung lượng và chi phí; nên kết hợp lifecycle rule cho noncurrent versions theo chính sách lưu giữ. Trước khi thay đổi bucket production, cần review retention, soft delete và quy định dữ liệu.

## 13. Tích hợp Java/Spring Boot với Google Cloud Storage

### 13.1. Client library và Spring integration

Java client chính thức thường dùng artifact:

- **com.google.cloud:google-cloud-storage** cho Cloud Storage Java client.
- Starter tích hợp Spring Cloud GCP/Google Cloud Spring (nếu dùng) để đưa cấu hình và bean vào Spring Boot.
- BOM tương ứng để quản lý phiên bản các thư viện GCP/Spring.

Các artifact và version cần khớp với Spring Boot/Java baseline của dự án. Không chọn version mới nhất một cách độc lập nếu BOM hoặc Spring Cloud release train của dự án đang quản lý các thư viện khác.

### 13.2. Application Default Credentials (ADC)

Java client Cloud Storage thường sử dụng **Application Default Credentials (ADC)** khi tạo service:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

ADC là cơ chế tìm danh tính theo môi trường. Trong phát triển local, developer có thể thiết lập ADC qua **gcloud auth application-default login** theo chính sách tổ chức. Khi chạy trên Google Cloud, workload nên dùng service account gắn với môi trường hoặc Workload Identity/Workload Identity Federation phù hợp, thay vì đưa service account key dài hạn vào image.

Cần phân biệt:

- **gcloud auth login:** đăng nhập để sử dụng các lệnh gcloud theo tài khoản người dùng.
- **gcloud auth application-default login:** tạo credentials cho ứng dụng dùng ADC ở local.
- **Service account/workload identity:** danh tính dành cho workload trên môi trường triển khai.

Đăng nhập gcloud thành công không tự động chứng minh Java process có ADC hợp lệ hoặc có quyền trên bucket. Kiểm tra đúng nguồn credential và principal thực tế.

### 13.3. Tạo Storage bean trong Spring

Nếu starter Spring Cloud GCP/Google Cloud Spring của phiên bản dự án đã auto-configure bean **Storage**, có thể inject bean đó. Nếu không dùng starter hoặc cần tự quản lý, có thể khai báo:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GoogleCloudStorageConfiguration {

    @Bean
    Storage googleCloudStorage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Trong ứng dụng thực tế, kiểm tra điều kiện auto-configuration để tránh tạo hai bean Storage cạnh tranh. Nếu cần project/credential riêng cho nhiều môi trường, cấu hình rõ StorageOptions theo môi trường và quản lý vòng đời client theo hướng dẫn thư viện.

### 13.4. Upload object với content type và custom metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class DocumentObjectStore {

    private final Storage storage;

    public DocumentObjectStore(Storage storage) {
        this.storage = storage;
    }

    public long uploadText(String bucket, String objectName, String text) {
        BlobInfo info = BlobInfo.newBuilder(
                        BlobId.of(bucket, objectName))
                .setContentType("text/plain; charset=utf-8")
                .setCacheControl("private, max-age=0")
                .setMetadata(Map.of(
                        "source-system", "document-api",
                        "classification", "internal"))
                .build();

        Blob created = storage.create(
                info,
                text.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());

        return created.getGeneration();
    }
}
~~~

**doesNotExist()** dùng precondition tạo object chỉ khi chưa có live object cùng tên. Nếu object đã tồn tại, operation thất bại thay vì âm thầm ghi đè. Trong ứng dụng, hãy chuyển lỗi precondition thành kết quả nghiệp vụ rõ ràng (ví dụ conflict/duplicate) và không tự retry bằng cách bỏ precondition.

Ví dụ dùng payload nhỏ dưới dạng byte array. Với file lớn, hãy đánh giá streaming, resumable upload, multipart/parallel composite upload nếu phù hợp, memory footprint, retry và checksum; không đọc toàn bộ file lớn vào heap chỉ để gọi một overload tiện lợi.

### 13.5. Đọc object và generation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public class DocumentObjectReader {

    private final Storage storage;

    public DocumentObjectReader(Storage storage) {
        this.storage = storage;
    }

    public Blob describe(String bucket, String objectName) {
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        if (blob == null) {
            throw new IllegalArgumentException("Object không tồn tại");
        }
        return blob;
    }

    public long currentGeneration(String bucket, String objectName) {
        return describe(bucket, objectName).getGeneration();
    }
}
~~~

**Storage.get(BlobId)** đọc metadata object; nội dung bytes có thể tải riêng qua API thích hợp. Nếu cần một generation cụ thể, dùng BlobId/API option có generation tương ứng theo phiên bản client library, thay vì chỉ truyền object name rồi giả định live object không thay đổi.

### 13.6. Cập nhật metadata có precondition

Ví dụ về mặt API Java, đọc metadata trước rồi cập nhật dựa trên metageneration hiện tại:

~~~java
Blob current = storage.get(BlobId.of(bucket, objectName));
if (current == null) {
    throw new IllegalArgumentException("Object không tồn tại");
}

BlobInfo changed = current.toBuilder()
        .setMetadata(Map.of(
                "classification", "reviewed",
                "reviewed-by", "quality-service"))
        .build();

Blob updated = storage.update(
        changed,
        Storage.BlobTargetOption.metagenerationMatch(
                current.getMetageneration()));
~~~

Nếu một service khác đã cập nhật metadata giữa lần đọc và lần update, precondition không khớp và request bị từ chối. Ứng dụng cần đọc lại và hợp nhất metadata theo logic nghiệp vụ, không bỏ điều kiện chỉ để ép ghi thành công.

## 14. Tổ chức adapter theo ranh giới nghiệp vụ

Một service Spring Boot không nên để controller hoặc domain model phụ thuộc trực tiếp vào chi tiết **Blob**, **BlobInfo** hay Google Cloud SDK. Tách interface giúp thay đổi provider hoặc test dễ hơn:

~~~java
public interface DocumentStorage {
    StoredDocument save(String documentId, byte[] content, String contentType);
    StoredDocument describe(String documentId);
}

public record StoredDocument(
        String bucket,
        String objectName,
        long generation,
        long metageneration,
        String contentType,
        long size) {}
~~~

Adapter GCS chịu trách nhiệm:

- Chuyển documentId thành object name theo quy ước.
- Tạo BlobInfo với content type/metadata.
- Upload với generation precondition phù hợp.
- Đọc generation/metageneration và ánh xạ sang model ứng dụng.
- Chuyển exception của SDK thành lỗi ở tầng adapter.
- Không để lộ bucket name, credentials hoặc metadata nhạy cảm ra API nếu không cần.

Một adapter khác có thể dùng Amazon S3 hoặc Azure Blob Storage. Interface nghiệp vụ nên mô tả hành vi cần thiết, ví dụ **saveDocument**, **loadDocument**, **deleteDocument**, **getVersion**, thay vì cố tạo một API generic bao phủ mọi khác biệt của object storage.

## 15. Kiểm thử bucket, generation và metadata

### 15.1. Unit test

Mock interface DocumentStorage để kiểm tra logic nghiệp vụ, validation object name, ánh xạ document ID, xử lý lỗi duplicate và idempotency. Unit test không cần ADC hay project GCP thật.

### 15.2. Integration test trên project GCP riêng

Một integration test thật nên sử dụng project test, bucket riêng, IAM service account tối thiểu và cleanup rõ ràng:

1. Tạo bucket ở location test theo quy trình hạ tầng đã được phê duyệt.
2. Cấp quyền cho test identity trên đúng bucket.
3. Upload object với **ifGenerationMatch=0**.
4. Đọc object và kiểm tra bytes, content type, custom metadata, generation.
5. Cập nhật metadata có **ifMetagenerationMatch**.
6. Ghi đè có **ifGenerationMatch** đúng; sau đó thử lại với generation cũ và kỳ vọng precondition thất bại.
7. Nếu bật versioning, kiểm tra noncurrent generation theo cấu hình.
8. Dọn object và bucket theo chính sách test; không xóa tài nguyên chia sẻ của nhóm khác.

Không dùng project production cho test generation/versioning vì test có thể tạo phiên bản, chi phí lưu trữ hoặc thay đổi metadata ngoài ý muốn.

### 15.3. Kiểm thử lỗi quan trọng

| Tình huống | Kỳ vọng |
| --- | --- |
| Tạo object với **doesNotExist()** khi object đã có | Conflict/precondition failure, không ghi đè |
| Update metadata với metageneration cũ | Precondition failure, dữ liệu metadata mới được bảo toàn |
| Đọc object name không tồn tại | Kết quả not found rõ ràng |
| Principal không có **storage.objects.get** | Permission denied |
| Bucket location/config không đúng | Phát hiện từ cấu hình/resource, không retry vô hạn |
| Object bị thay thế trong lúc xử lý | Generation precondition ngăn thao tác lên phiên bản ngoài dự kiến |
| Metadata chứa field nhạy cảm | Test validation/masking từ chối hoặc loại bỏ field không được phép |

### 15.4. Kiểm thử không đồng nghĩa với Local emulator

Một số service GCP có emulator, nhưng **không được giả định Cloud Storage luôn có emulator chính thức tương đương mọi hành vi production**. Khi dùng fake server hoặc emulator của bên thứ ba, xác minh rõ API được hỗ trợ và giới hạn. Với các đặc tính quan trọng như IAM, generation precondition, retention, soft delete, versioning và signed URL, nên có integration test trên project GCP riêng để kiểm tra semantics thực tế.

## 16. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **storage.get(...)** trả null | Bucket/object name sai hoặc object không tồn tại | Kiểm tra bucket, object name và generation |
| **403 Forbidden** | ADC principal thiếu IAM permission hoặc policy chặn | Xác minh principal, project/bucket scope, role và condition |
| **401 Unauthorized** | Credential không hợp lệ/hết hạn hoặc token audience/scope không đúng | Kiểm tra ADC/workload identity và thời gian hệ thống |
| Tạo bucket báo tên đã tồn tại | Bucket name duy nhất đã được project khác sử dụng | Chọn tên khác; không giả định tên chỉ duy nhất trong project |
| Ghi đè nhầm object | Không dùng generation precondition hoặc logic tên object không duy nhất | Dùng ifGenerationMatch và ID ổn định |
| Metadata bị mất sau update | Gửi map metadata mới thay cho merge các key hiện có | Đọc metadata, hợp nhất key và dùng metageneration precondition |
| Đọc nhầm nội dung cũ/mới | Chỉ lưu object name, không lưu generation | Ghi nhận generation khi xử lý và đọc đúng version |
| Không thấy thư mục trong console | Prefix chưa có object hoặc đang dùng flat namespace | Liệt kê theo prefix; không coi folder marker là bắt buộc |
| Java dùng ADC khác gcloud CLI | Đăng nhập gcloud user nhưng chưa tạo ADC hoặc workload identity khác | Kiểm tra ADC source và principal của Java process |
| Upload lớn lỗi bộ nhớ | Đọc toàn bộ file vào byte array | Dùng streaming/resumable upload và giới hạn tài nguyên |

Khi điều tra 403, không vội cấp **roles/storage.admin**. Xác định API cần quyền nào, principal nào đang gọi, bucket/project nào và policy/condition nào đang áp dụng.

## 17. Bài tập thực hành tổng hợp

**Tình huống:** Một ứng dụng Spring Boot quản lý tài liệu hợp đồng. Mỗi tenant có prefix riêng trong bucket **training-contracts-dev**. Khi upload thành công, hệ thống lưu bucket, objectName, generation, metageneration, contentType và size vào database. Một worker khác bổ sung custom metadata **review-status** sau khi kiểm tra nội dung.

### Nhiệm vụ A — Thiết kế bucket và object name

1. Đề xuất location và storage class cho dữ liệu hợp đồng truy cập thường xuyên.
2. Đặt quy ước object name có tenant, năm/tháng và document ID.
3. Giải thích vì sao prefix không tự tạo quyền cách ly tenant.
4. Chọn UBLA, Public Access Prevention và IAM role phù hợp.
5. Nêu khi nào cần bật Object Versioning, soft delete hoặc retention policy.

### Nhiệm vụ B — Generation và concurrency

1. API upload phải tạo object mới, không ghi đè; dùng **ifGenerationMatch=0**.
2. Worker đọc object generation G1 và cập nhật metadata với **ifMetagenerationMatch=M1**.
3. Giả sử worker khác cập nhật metadata trước, làm metageneration tăng lên M2. Giải thích tại sao request đầu tiên bị từ chối và cách merge lại.
4. Giải thích vì sao generation khác metageneration, và ETag không mặc nhiên là MD5.
5. Nếu cần tải lại đúng nội dung đã được duyệt, hệ thống phải lưu thêm giá trị nào ngoài object name?

### Nhiệm vụ C — Triển khai Java/Spring

1. Tạo Storage bean qua ADC hoặc dùng bean do Spring Cloud GCP auto-configure.
2. Viết adapter DocumentStorage để upload và trả generation.
3. Viết luồng đọc metadata và update có precondition.
4. Không đưa secret vào custom metadata; xác định field nào phù hợp với database hơn.
5. Thiết kế mapping lỗi precondition thành conflict nghiệp vụ thay vì retry vô điều kiện.

### Nhiệm vụ D — Kiểm thử và vận hành

- Unit test object name validation và logic xử lý conflict.
- Integration test với project/bucket GCP riêng và IAM service account giới hạn.
- Test generation mismatch, metageneration mismatch, versioning và metadata merge.
- Theo dõi lỗi 403, 412, not found, latency, size và checksum.
- Thiết kế lifecycle rule cho noncurrent versions nếu bật versioning.
- Kiểm tra chi phí lưu trữ và truy xuất theo storage class.

**Tiêu chí đạt:** Người học phân biệt được bucket với object name, generation với metageneration, metadata hệ thống với custom metadata; biết sử dụng precondition để chống lost update và có thiết kế IAM/test phù hợp với ứng dụng nhiều tenant.

## 18. Liên hệ với AWS S3 và Azure Blob Storage

Ba nền tảng đều cung cấp object storage, nhưng semantics và API không hoàn toàn giống nhau:

| Khía cạnh | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Container | Bucket | Bucket | Storage account + container |
| Định danh object | Object name | Object key | Blob name |
| Version identifier | Generation | Version ID khi bật versioning | Version ID khi bật versioning |
| Metadata concurrency | Metageneration/precondition | Conditional request/ETag và API tương ứng | ETag/lease/conditional headers |
| Custom metadata | Map key/value | User-defined metadata | Blob metadata |
| Phân quyền | IAM, UBLA, ACL theo cấu hình | IAM, bucket/access point policy, ACL theo cấu hình | Azure RBAC, SAS, access policy theo mô hình |
| Java integration | Google Cloud Storage Java client / Spring Cloud GCP | AWS SDK v2 / AWSpring | Azure SDK / Spring Cloud Azure |

Không xây abstraction đa cloud với giả định generation, S3 Version ID và Azure Blob Version ID có cùng format hoặc vòng đời. Interface nghiệp vụ nên chuẩn hóa hành vi mà ứng dụng cần; adapter từng provider chịu trách nhiệm ánh xạ version token, metadata và precondition theo API riêng.

## 19. Ghi nhớ

- **Bucket** xác định container, project, location, cấu hình truy cập và vòng đời lưu trữ.
- **Object name** là định danh object. Với flat namespace, dấu / thường chỉ là quy ước prefix; HNS là lựa chọn cấu trúc riêng.
- **Generation** nhận diện phiên bản dữ liệu; **metageneration** nhận diện phiên bản metadata.
- **Object Versioning**, **soft delete** và **retention policy** là các cơ chế khác nhau, cần tính chi phí và chính sách phục hồi.
- **Metadata** mô tả object; system metadata và custom metadata có mục đích khác nhau. Không lưu secret hay dữ liệu truy vấn phức tạp vào custom metadata.
- **Generation/metageneration preconditions** giúp ngăn ghi đè và lost update khi nhiều service cùng thao tác.
- Spring Boot có thể dùng Google Cloud Storage Java client với ADC hoặc tích hợp Spring Cloud GCP phù hợp; IAM và workload identity vẫn phải được cấu hình riêng.

Nắm vững các khái niệm này giúp ứng dụng Spring Boot lưu trữ object có cấu trúc, kiểm soát phiên bản và metadata rõ ràng, giảm rủi ro ghi đè dữ liệu, đồng thời tạo nền tảng để so sánh và xây adapter cho AWS S3 và Azure Blob Storage.
