# Tối ưu Cloud Storage classes, lifecycle và phí truy xuất

Một doanh nghiệp lưu ảnh sản phẩm, hóa đơn, kết quả xử lý dữ liệu, bản sao lưu và nhật ký ứng dụng trên Google Cloud Storage (GCS). Sau vài năm, chi phí tăng dù lượng người dùng không đổi. Nguyên nhân có thể không chỉ nằm ở dung lượng: dữ liệu cũ vẫn nằm ở lớp Standard, tệp tạm được lưu thêm do soft delete, các phiên bản cũ không được dọn, nhiều triệu object nhỏ phải chuyển lớp qua lifecycle, hoặc hệ thống liên tục đọc dữ liệu Archive để phục vụ báo cáo hằng ngày.

**Tối ưu Cloud Storage** là lựa chọn đúng storage class và vị trí lưu, thiết lập vòng đời đối tượng, đồng thời kiểm soát *toàn bộ* chi phí đọc/ghi/truyền dữ liệu. Mục tiêu không đơn thuần là chuyển tất cả dữ liệu sang lớp có giá lưu thấp nhất; tối ưu đúng phải giữ được yêu cầu về latency, khả năng truy xuất, RPO/RTO, bảo mật, retention và quyền sở hữu dữ liệu.

Trên Google Cloud, các thành phần thường kết hợp gồm **Standard, Nearline, Coldline, Archive**, **Object Lifecycle Management**, **Autoclass**, **Object Versioning**, **soft delete**, Cloud Billing, Cloud Monitoring và Inventory/Storage Intelligence. Các cơ chế này có quy tắc riêng. Đặc biệt, thay đổi storage class thủ công, chuyển lớp bằng lifecycle và dùng Autoclass có cách tính phí khác nhau.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt bốn storage classes phổ biến và biết khi nào dùng Rapid storage cho nhu cầu chuyên biệt.
- Phân tích phí lưu trữ, operations, retrieval, minimum storage duration, early deletion, network và replication.
- Thiết kế bucket strategy theo access pattern, RTO/RPO, location và data classification.
- Viết Object Lifecycle Management rules để chuyển lớp, hết hạn dữ liệu và quản lý phiên bản.
- So sánh Autoclass với các lifecycle rules do nhóm tự thiết kế.
- Nhận diện chi phí tiềm ẩn từ soft delete, Object Versioning, tệp nhỏ và overwrite thường xuyên.
- Lập mô hình FinOps bằng dữ liệu Cloud Billing và workload access logs.
- Sử dụng lệnh chỉ đọc của gcloud để khảo sát bucket, sau đó đề xuất change có kiểm chứng.
- Thực hành phương án tối ưu bucket cho ứng dụng Java/Spring và kho dữ liệu sao lưu.
- Thiết kế guardrails để không xóa dữ liệu production hoặc vi phạm retention policy.

## 1. Cloud Storage lưu trữ object, không phải ổ đĩa truyền thống

Cloud Storage lưu **objects** trong **buckets**. Mỗi object có tên, nội dung, metadata, generation và storage class. Bucket có location và các cấu hình về IAM, retention, lifecycle, encryption và soft delete.

~~~text
Google Cloud project
       |
       v
Cloud Storage bucket (location / IAM / policy)
       |
       +-- images/product-001.webp       [STANDARD]
       +-- invoices/2025/invoice-001.pdf [NEARLINE]
       +-- backups/2024/db-dump.tar      [COLDLINE]
       +-- audit/2023/events.jsonl       [ARCHIVE]
~~~

Các object trong một bucket không nhất thiết có cùng storage class. Bucket default storage class xác định lớp ban đầu cho object mới nếu uploader không chỉ định lớp riêng. Đổi default class của bucket không có nghĩa mọi object cũ được chuyển lớp ngay.

### Lưu trữ object khác block/file storage

- Cloud Storage được truy cập qua API HTTP, SDK hoặc một số cơ chế mount phù hợp.
- Không nên dựa vào hành vi POSIX hoặc độ trễ của local disk cho mọi thao tác.
- Mỗi lần đọc, ghi, list hoặc rewrite có thể tạo operation charges.
- Objects phù hợp với dữ liệu blob, tài liệu, media, backup và dữ liệu phân tích.
- Các workload cần transaction, random block writes hoặc database filesystem semantics có thể phù hợp hơn với Cloud SQL, Persistent Disk, Filestore hoặc sản phẩm khác.

## 2. Chọn storage class theo cách truy cập dữ liệu

| Storage class | Phù hợp với | Thời gian lưu tối thiểu | Retrieval fee | Ghi chú |
|---|---|---:|---|---|
| **Standard** | Ảnh đang phục vụ, dữ liệu nóng, tải truy xuất thường xuyên | Không có | Không | Chi phí lưu cao hơn nhưng không thêm phí retrieval theo class |
| **Nearline** | Dữ liệu ít đọc, backup thường chỉ truy xuất theo tháng | 30 ngày | Có | Tránh dùng nếu liên tục đọc lại dung lượng lớn |
| **Coldline** | Disaster recovery, dữ liệu ít đọc hơn, cỡ hàng quý | 90 ngày | Có | Rẻ hơn khi lưu lâu nhưng phí đọc/operations tăng |
| **Archive** | Lưu trữ dài hạn, compliance, ít được truy xuất | 365 ngày | Có | Giá lưu thấp nhất trong nhóm thông dụng, phí retrieval cao |
| **Rapid storage** | Workload hiệu năng cao trên Rapid Bucket ở zone hỗ trợ | Không có | Không | Loại chuyên biệt, không phải lựa chọn mặc định cho archive |

Các mức 30/90/365 ngày là **minimum storage duration**, không phải thời gian chờ để đọc được object. Nearline, Coldline và Archive đều là lưu trữ online: object có thể được đọc qua API mà không phải "rehydrate" trong nhiều giờ theo mô hình một số nền tảng lưu trữ khác.

### Khi nào chọn class lạnh?

Một cách phân loại ban đầu:

- Đọc nhiều lần/ngày: **Standard**.
- Đọc khoảng một lần/tháng hoặc ít hơn, lưu tối thiểu 30 ngày: xem **Nearline**.
- Đọc theo quý hoặc ít hơn, lưu tối thiểu 90 ngày: xem **Coldline**.
- Dữ liệu giữ ít nhất một năm, cực hiếm khi đọc: xem **Archive**.

Đây chỉ là hướng dẫn định tính. Quyết định cuối cùng phải dựa trên số lượng và dung lượng object, tần suất đọc, thao tác list/copy/rewrite, vị trí network và retention thực tế. Một object 100 GiB được đọc lại toàn bộ mỗi ngày có thể khiến Archive đắt hơn Standard.

## 3. Tổng chi phí Cloud Storage gồm những gì?

Một hóa đơn Cloud Storage có nhiều thành phần:

~~~text
Tổng chi phí
 = Storage at-rest
 + Class A / Class B operation charges
 + Retrieval charges (nếu áp dụng)
 + Network egress / data transfer
 + Inter-region replication charges (nếu áp dụng)
 + Autoclass management/enablement charges (nếu bật)
 + Storage Intelligence / tính năng bổ sung (nếu sử dụng)
 + Early deletion / phần dữ liệu được giữ bởi retention
 + Chi phí vận hành và các dịch vụ liên quan
~~~

### 3.1. Storage at-rest

Tính theo dung lượng lưu trữ thực tế, class, location và thời gian tồn tại. Một bucket chứa 10 TiB tại region A không tự có giá giống bucket 10 TiB ở multi-region B.

Ngoài dữ liệu đang hoạt động, các phần sau cũng có thể tạo storage charges:

- Noncurrent versions do Object Versioning.
- Soft-deleted objects trong thời gian được giữ.
- Metadata tính vào dung lượng object.
- Dữ liệu upload/multipart chưa hoàn tất theo cơ chế hỗ trợ.
- Đối tượng được lưu thêm do retention, object holds và quy trình DR.

### 3.2. Operation charges

Các API requests được phân loại theo nhóm Class A, Class B và một số thao tác miễn phí. Ví dụ ghi, list, rewrite hoặc thay đổi storage class có thể có phí operation; đọc object và metadata cũng có nhóm phí tương ứng theo loại thao tác.

Giá operations thay đổi theo storage class và đôi khi theo loại bucket (ví dụ hierarchical namespace). Hàng triệu object nhỏ có thể tạo chi phí request đáng kể dù tổng dung lượng thấp.

### 3.3. Retrieval charges

Đọc dữ liệu nằm trong Nearline, Coldline hoặc Archive thường phát sinh retrieval charges theo dung lượng truy xuất. Đây là **chi phí bổ sung**, không thay thế operation hoặc network charges.

Theo bảng giá tham khảo của Google Cloud, các lớp thông dụng có mức retrieval phí minh họa:

| Class | Phí retrieval tham khảo |
|---|---:|
| Standard | 0 USD/GiB |
| Nearline | 0,01 USD/GiB |
| Coldline | 0,02 USD/GiB |
| Archive | 0,05 USD/GiB |

Giá thực tế cần xác minh ở trang Cloud Storage pricing và Billing SKUs tại thời điểm lập kế hoạch; bảng trên không phải cam kết giá dài hạn. Một API đọc 5 TiB dữ liệu Archive có thể tốn nhiều phí truy xuất dù dữ liệu lưu rất rẻ.

### 3.4. Network và replication

Đọc dữ liệu từ Cloud Storage sang hệ thống ngoài Google Cloud hoặc qua các khu vực địa lý khác có thể phát sinh network egress. Việc ghi lên dual-region/multi-region có thể có phí inter-region replication. Chi phí phụ thuộc source/destination, loại location và cấu hình replication.

Một bản sao lưu nằm ở region xa có thể đáp ứng DR nhưng làm tăng chi phí ghi, đồng bộ và phục hồi. Cần tính cả **phí truy xuất + data transfer + xử lý khôi phục** chứ không chỉ phí giữ bản sao.

## 4. Minimum storage duration và phí early deletion

Nearline, Coldline và Archive yêu cầu lưu tối thiểu lần lượt **30, 90 và 365 ngày**. Nếu object bị xóa, overwrite hoặc đổi class thủ công quá sớm, có thể bị tính **early deletion charges** cho thời gian chưa đủ.

### Ví dụ

Một object 1 TiB được ghi thẳng vào Archive rồi bị xóa sau 20 ngày. Phí lưu không đơn thuần là 20 ngày: có thể xuất hiện early deletion charge cho phần thời gian còn thiếu của mức tối thiểu 365 ngày.

Một object 1 TiB trong Coldline chỉ lưu 10 ngày có thể đắt hơn dự kiến nếu ứng dụng liên tục thay thế object bằng cùng tên mỗi đêm.

### Ngoại lệ quan trọng: lifecycle transitions

Google Cloud phân biệt:

- **Manual rewrite / đổi storage class thông qua rewrite:** có thể kích hoạt early deletion charges với lớp lạnh khi chưa đủ thời gian.
- **Object Lifecycle Management chuyển class bằng SetStorageClass:** không bị tính early deletion charge cho chính thao tác lifecycle transition.
- **Object nằm trong bucket bật Autoclass:** không bị tính early deletion charge theo cơ chế thường dùng, ngoại trừ trường hợp phí enablement khi bật trên bucket đang tồn tại.
- **Delete thực sự trước hạn:** có thể kích hoạt early deletion charge khi object bị xóa vĩnh viễn; chuyển sang noncurrent hoặc soft-deleted chưa tự kích hoạt ngay.

Vì vậy, không áp một công thức phí early deletion giống nhau cho tất cả cách chuyển class. Tuy lifecycle chuyển lớp không chịu early deletion fee, mỗi chuyển lớp bằng SetStorageClass vẫn có thể phát sinh **Class A operation charge**.

### Thời gian được giữ thêm cũng quan trọng

Khi Object Versioning hoặc soft delete được bật, thời gian object tồn tại dưới dạng current, noncurrent hoặc soft-deleted đều được tính vào minimum storage duration. Tuy nhiên, việc duy trì những bản này cũng tiếp tục phát sinh phí lưu trữ.

## 5. Phân tích access pattern trước khi chọn class

Không nên thay storage class chỉ dựa trên ngày tạo object. Hãy kết hợp:

| Câu hỏi | Nguồn thông tin |
|---|---|
| Những prefix nào lớn nhất? | Inventory reports, Storage Intelligence, listing/metadata |
| Object kích thước trung bình bao nhiêu? | Object metadata và inventory |
| Bao nhiêu read requests trong kỳ? | Cloud Monitoring, Cloud Audit Logs nếu bật phù hợp |
| Bao nhiêu GiB/TiB được đọc? | Billing export, request telemetry |
| Object nào thường xuyên bị overwrite? | Generation history, logs, application workflow |
| Dữ liệu được giữ vì compliance bao lâu? | Data retention policy và legal owner |
| Có kỳ report/restore bất thường không? | Incident history, scheduler, DR drill |
| Dữ liệu phục vụ từ region nào? | App topology, egress billing, latency tests |
| Có dùng soft delete/versioning không? | Bucket configuration |
| Ai chịu trách nhiệm quyết định xóa? | Data owner, security, SRE và FinOps |

### Khác biệt giữa access frequency và access volume

1.000 lần đọc metadata của object nhỏ không giống 1.000 lần tải lại một video 20 GiB. Retrieval charges chủ yếu chịu tác động bởi lượng dữ liệu thực đọc/copy, còn operations chịu tác động bởi số request và loại request.

Một hệ thống ảnh có CDN cache tốt có thể ít đọc origin Cloud Storage hơn ứng dụng chưa cache; điều đó thay đổi bài toán chọn lớp lưu.

## 6. Chọn bucket location để giảm latency và egress

Bốn loại vị trí thường gặp:

- **Region:** một khu vực địa lý, phù hợp ứng dụng và dữ liệu tập trung tại một region.
- **Dual-region:** dữ liệu tồn tại trên hai regions theo cấu hình, phù hợp một số mục tiêu availability/DR và data placement.
- **Multi-region:** dữ liệu được lưu trong phạm vi địa lý rộng hơn theo cơ chế sản phẩm.
- **Zone với Rapid Bucket:** mô hình chuyên biệt cho Rapid storage/high performance.

### Không chỉ nhìn giá lưu

Chọn location dựa trên:

- Nơi workload xử lý dữ liệu (Cloud Run/GKE/Compute Engine/BigQuery).
- Quy định residency và vùng được phép.
- RTO/RPO, mức độ chịu lỗi, yêu cầu DR.
- Data ingress/egress và chi phí inter-region transfer.
- Mức latency chấp nhận được.
- Khả năng availability và replication.
- Kế hoạch migration, data lake hoặc analytics.

**Không tự suy diễn "multi-region luôn rẻ hơn" hay "dual-region luôn tốt hơn".** Giá lưu, phí replication, egress và khả năng đáp ứng RTO/RPO khác nhau. Cần so sánh nhiều kịch bản bằng bảng giá đúng region.

## 7. Object Lifecycle Management là gì?

Object Lifecycle Management (OLM) là cấu hình gắn lên bucket. Mỗi **rule** có một action và một hoặc nhiều condition. Cloud Storage tự thực thi khi object đáp ứng điều kiện.

Các action chính:

- **SetStorageClass:** chuyển object sang storage class được hỗ trợ.
- **Delete:** xóa object theo điều kiện.
- **AbortIncompleteMultipartUpload:** dọn multipart upload chưa hoàn tất theo điều kiện tương thích.

Các condition thường dùng:

| Condition | Ý nghĩa |
|---|---|
| age | Số ngày kể từ lúc object được tạo |
| isLive | Object version hiện tại hay noncurrent |
| matchesStorageClass | Chỉ áp dụng cho các lớp được chọn |
| matchesPrefix / matchesSuffix | Chọn theo tên object |
| sizeAboveBytes / sizeBelowBytes | Giới hạn theo kích thước |
| daysSinceNoncurrentTime | Số ngày kể từ khi version trở thành noncurrent |
| numNewerVersions | Số phiên bản mới hơn |
| createdBefore | Object được tạo trước ngày chỉ định |
| daysSinceCustomTime | Số ngày từ custom time đã gắn |

**Các điều kiện trong cùng một rule phải đồng thời thỏa mãn.** Nếu nhiều rules độc lập có cùng action, object có thể bị tác động khi thỏa rule bất kỳ.

Khi nhiều rules cùng match một object, Cloud Storage áp dụng thứ tự ưu tiên: Delete có ưu tiên hơn SetStorageClass; giữa các SetStorageClass tương tranh, lựa chọn lớp có at-rest price thấp hơn có thể thắng. Không tạo rules chồng chéo rồi kỳ vọng chúng luôn chạy tuần tự theo thứ tự trong file JSON.

### Lifecycle không chạy tức thì chính xác ở thời điểm thỏa điều kiện

Các rule có thể được thực thi bất đồng bộ. Việc cập nhật policy có thể mất đến **24 giờ** để có hiệu lực, và rule cũ có thể tiếp tục tác động trong thời gian này.

Nếu vừa thay "xóa sau 10 ngày" thành "xóa sau 30 ngày", object 15 ngày tuổi vẫn có thể bị rule cũ xóa trong khoảng chuyển tiếp. Đây là lý do không triển khai policy phá hủy dữ liệu ngay trên bucket quan trọng khi chưa kiểm thử.

## 8. Ví dụ lifecycle cho chứng từ lưu dài hạn

Giả sử bucket chứa chứng từ trong prefix records/ với yêu cầu:

- Dữ liệu mới phục vụ tải thường xuyên.
- Sau một tháng, tần suất đọc giảm.
- Sau bốn tháng, chỉ còn nhu cầu báo cáo theo quý.
- Sau khoảng 16 tháng, chuyển sang archive.
- Chỉ xóa sau khoảng 30 tháng khi đã hết retention theo phê duyệt nghiệp vụ.
- Object nhỏ dưới 1 MiB được giữ nguyên, tránh chi phí chuyển lớp trên số lượng object quá lớn.

Cấu hình JSON minh họa:

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
        "isLive": true,
        "matchesStorageClass": ["STANDARD"],
        "matchesPrefix": ["records/"],
        "sizeAboveBytes": 1048576
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "COLDLINE"
      },
      "condition": {
        "age": 120,
        "isLive": true,
        "matchesStorageClass": ["NEARLINE"],
        "matchesPrefix": ["records/"],
        "sizeAboveBytes": 1048576
      }
    },
    {
      "action": {
        "type": "SetStorageClass",
        "storageClass": "ARCHIVE"
      },
      "condition": {
        "age": 485,
        "isLive": true,
        "matchesStorageClass": ["COLDLINE"],
        "matchesPrefix": ["records/"],
        "sizeAboveBytes": 1048576
      }
    },
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "age": 900,
        "isLive": true,
        "matchesPrefix": ["records/"]
      }
    }
  ]
}
~~~

**Giải thích:**

- age là tuổi *tính từ khi object được tạo*, không phải số ngày kể từ lần đổi storage class.
- Giai đoạn Standard → Nearline sau 30 ngày, Nearline → Coldline ở tuổi 120 ngày và Coldline → Archive ở tuổi 485 ngày.
- Lớp Nearline có khoảng 90 ngày từ ngày 30 đến 120; Coldline khoảng 365 ngày từ 120 đến 485; Archive tồn tại khoảng 415 ngày trước mốc 900.
- sizeAboveBytes tránh class transitions cho object có dung lượng nhỏ; điều kiện này không giới hạn rule Delete, vì chính sách xóa chứng từ được thiết kế áp dụng cho toàn prefix.
- Delete ở tuổi 900 ngày chỉ hợp lệ nếu data owner đã xác nhận retention, legal hold, audit và chính sách bảo vệ dữ liệu.
- Bucket có soft delete hoặc Object Versioning có thể tiếp tục giữ dữ liệu sau khi rule Delete chạy.
- Nếu có retention lock/hold, hành động xóa có thể không được thực hiện cho tới khi đủ điều kiện.

**Không áp dụng JSON ví dụ vào production trước khi phê duyệt.** Số ngày là giả định đào tạo, không phải thời hạn pháp lý cho mọi hóa đơn/chứng từ.

## 9. Xem và cập nhật lifecycle bằng gcloud

Các lệnh chỉ đọc nên thực hiện trước:

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="json(name,location,storageClass,lifecycle,autoclass,versioning,softDeletePolicy)"
~~~

~~~bash
gcloud storage ls gs://BUCKET_NAME/records/
~~~

Tùy kích thước bucket, một thao tác list toàn bộ objects có thể tạo phí operations và mất thời gian. Ưu tiên phân vùng prefix hoặc inventory reports thay vì list hàng triệu objects chỉ để kiểm tra kích thước.

### Áp dụng lifecycle file

Khi đã có phê duyệt và file lifecycle-policy.json được review:

~~~bash
gcloud storage buckets update gs://BUCKET_NAME \
  --lifecycle-file=lifecycle-policy.json
~~~

**Cảnh báo:** cấu hình lifecycle mới có thể **thay thế toàn bộ rules cũ** của bucket. Trước khi cập nhật, phải đọc cấu hình hiện có, hợp nhất các rules cần giữ và review full diff. Không chạy lệnh này với ví dụ đào tạo trên bucket production.

### Kiểm chứng sau cập nhật

~~~bash
gcloud storage buckets describe gs://BUCKET_NAME \
  --format="json(lifecycle)"
~~~

Sau đó theo dõi:

- Rule configuration có khớp bản đã phê duyệt không?
- Có Delete rule không mong muốn?
- Có object thuộc prefix khác bị tác động không?
- Operation charges và storage-class distribution có thay đổi như dự kiến?
- Data retention/hold có chặn rule đúng cách không?
- Trong khoảng tối đa 24 giờ kể từ thay đổi, rule cũ còn tạo rủi ro gì?

Không chỉ nhìn thấy rule trong bucket rồi tuyên bố dữ liệu đã được chuyển/xóa hoàn toàn. Lifecycle actions diễn ra bất đồng bộ.

## 10. Lifecycle và Object Versioning

Object Versioning giữ các phiên bản object đã bị overwrite hoặc delete. Nó hỗ trợ phục hồi thao tác sai, nhưng có thể khiến chi phí tăng nhanh nếu object được ghi lại thường xuyên.

~~~text
report.csv (live generation 103)
   |
   +-- generation 102 (noncurrent)
   +-- generation 101 (noncurrent)
   +-- generation 100 (noncurrent)
~~~

Các phiên bản noncurrent vẫn chiếm dung lượng. Nếu cứ overwrite file 100 GiB mỗi ngày, sau 30 ngày có thể tích lũy nhiều TiB phiên bản cũ.

### Quy tắc dọn noncurrent versions

Một ví dụ khi chính sách cho phép giữ mỗi version cũ tối thiểu 30 ngày sau khi noncurrent:

~~~json
{
  "rule": [
    {
      "action": {
        "type": "Delete"
      },
      "condition": {
        "isLive": false,
        "daysSinceNoncurrentTime": 30
      }
    }
  ]
}
~~~

Lưu ý:

- daysSinceNoncurrentTime khác age: một object tồn tại nhiều tháng trước khi bị ghi đè chỉ bắt đầu đếm noncurrent duration từ khi trở thành noncurrent.
- Nếu lifecycle xóa live version khi versioning đang bật, phiên bản đó có thể chuyển thành noncurrent thay vì biến mất ngay.
- Xóa một noncurrent version có thể chuyển nó sang soft-deleted nếu bucket có chính sách soft delete.
- Đánh giá khả năng phục hồi trước khi giảm retention của versioning.

Không dùng thời hạn 30 ngày trong ví dụ này cho dữ liệu có nghĩa vụ lưu nhiều năm.

## 11. Soft delete: chi phí giữ thêm dữ liệu đã xóa

Soft delete bảo vệ object bị xóa hoặc ghi đè khỏi mất ngay lập tức. Với các bucket Cloud Storage hỗ trợ soft delete, chính sách mặc định hiện hành thường giữ **7 ngày**; có thể cấu hình thời gian giữ trong phạm vi dịch vụ cho phép hoặc disable khi phù hợp.

Đối tượng đã xóa vẫn tồn tại ở trạng thái soft-deleted tới khi hết retention. Trong giai đoạn đó:

- Không đọc hoặc sửa bình thường như live object.
- Có thể restore theo cơ chế được hỗ trợ.
- Tiếp tục phát sinh storage charges.
- Có thể làm tăng chi phí đáng kể cho bucket chứa temporary objects.

### Ví dụ: bucket chứa file tạm 24 giờ

Một pipeline tạo 1 TiB file tạm mỗi ngày và xóa sau một ngày. Nếu soft delete giữ thêm 7 ngày, tại trạng thái ổn định có thể có khoảng 7 TiB file soft-deleted bên cạnh lượng live data theo lịch xử lý, chưa kể variation.

Giải pháp có thể là:

1. Đánh giá dữ liệu tạm có cần khả năng restore hay không.
2. Nếu không, tạo bucket riêng có soft delete policy phù hợp hoặc tắt theo phê duyệt.
3. Tránh đặt file tạm cùng bucket với backup cần bảo vệ mạnh.
4. Dùng retention/lifecycle riêng cho dữ liệu tạm và dữ liệu quan trọng.
5. Theo dõi bytes soft-deleted qua monitoring/billing.

**Không tắt soft delete cho dữ liệu nghiệp vụ trọng yếu chỉ vì muốn giảm hóa đơn** mà chưa có backup/restore strategy và approval. Soft delete, versioning và retention policy là ba cơ chế khác nhau; cần xác định mục đích từng lớp bảo vệ.

## 12. Object retention và holds có thể ghi đè mục tiêu tiết kiệm

Một bucket hoặc object có thể có:

- Bucket retention policy hoặc Bucket Lock.
- Per-object retention.
- Event-based hold.
- Temporary hold.
- Legal/compliance holds do quy trình tổ chức.

Nếu object chưa hết thời hạn bắt buộc hoặc đang bị hold, lifecycle Delete không được phép xóa như một object thông thường. Một policy bất biến có thể không thể rút ngắn sau khi lock.

### Vì sao phải kiểm tra?

- Rút lifecycle age từ 365 xuống 90 không tự xóa dữ liệu đang được bảo vệ bởi retention lock.
- Điều chỉnh policy có thể có hệ quả pháp lý hoặc governance.
- Một bản sao đã mã hóa bằng CMEK vẫn cần khả năng dùng khóa để restore; retention không khắc phục được việc mất key.
- Restore test phải bao gồm metadata, IAM, encryption và ứng dụng đọc dữ liệu.

Thứ tự ưu tiên là **quy định dữ liệu và khả năng phục hồi trước, tối ưu chi phí sau**.

## 13. Autoclass: tự điều chỉnh storage class theo truy cập

Autoclass là tính năng ở cấp bucket cho phép Cloud Storage tự chuyển object giữa các lớp dựa trên access pattern. Nó hữu ích khi tần suất đọc không dự báo được hoặc khó duy trì nhiều lifecycle rules thủ công.

Hai kiểu cấu hình thường dùng:

- **Terminal Nearline:** tự chuyển giữa Standard và Nearline.
- **Terminal Archive:** có thể chuyển tiếp tới Coldline và Archive khi object ít được truy cập lâu dài.

### Thời gian chuyển lớp tham khảo

Với object đủ điều kiện:

- Sau 30 ngày không được đọc: **Nearline**.
- Sau 90 ngày không được đọc: **Coldline**, nếu terminal class cho phép.
- Sau 365 ngày không được đọc: **Archive**, nếu terminal class là Archive.
- Khi dữ liệu được đọc, object chuyển về **Standard** theo cơ chế của Autoclass.

Các chuyển đổi thực hiện bất đồng bộ nên không nhất thiết xảy ra đúng giờ/phút đạt ngưỡng. Object dưới **128 KiB** không được Autoclass đưa sang lớp lạnh, mà thường giữ Standard. Việc chỉ đọc/sửa metadata không được tính như đọc dữ liệu để reset access pattern.

### Autoclass thay đổi bài toán tính phí

Đối với bucket bật Autoclass:

- Không tính retrieval fees thông thường cho object trong bucket.
- Không áp early deletion charges thông thường, trừ trường hợp enablement charges khi bật với object đã tồn tại.
- Có **Autoclass management fee**, tính theo số object đủ điều kiện.
- Khi bật Autoclass trên bucket có sẵn objects có thể có **one-time enablement charge**.
- Một số chuyển lớp do Autoclass miễn operation charge; khi object từ Coldline/Archive được đưa lên lớp ấm hơn có thể có Class A charge tùy hướng chuyển.
- Operations được tính theo cơ chế Autoclass pricing, không giống cách tính mặc định của mọi class thủ công.

Không kết luận Autoclass luôn rẻ hơn lifecycle tự viết; bucket có hàng triệu object nhỏ và access patterns rất ổn định có thể phù hợp chiến lược khác.

### Điều kiện không tương thích

Khi Autoclass được bật, không cấu hình Object Lifecycle Management **SetStorageClass** hoặc điều kiện **matchesStorageClass**. Autoclass quản lý việc chuyển lớp. Các lifecycle rules khác, chẳng hạn Delete theo age khi hợp lệ, vẫn cần được đánh giá riêng.

### Bật Autoclass trên bucket hiện có

Thao tác này có thể làm objects hiện có chuyển sang Standard và tạo một lần phí enablement, bao gồm một số retrieval, early deletion và operation charges tùy trạng thái hiện tại. Phải mô phỏng chi phí trước khi bật; không dùng Autoclass như nút chuyển đổi miễn phí.

## 14. Khi nào chọn thủ công và khi nào chọn Autoclass?

| Tiêu chí | Storage class + lifecycle thủ công | Autoclass |
|---|---|---|
| Access pattern | Dự báo được theo tuổi object hoặc prefix | Khó dự báo, thay đổi theo truy cập |
| Điều khiển thời điểm chuyển | Theo age/custom time/conditions | Theo ngưỡng không truy cập do hệ thống quản lý |
| Quản lý class | Tự đặt SetStorageClass | Cloud Storage tự chuyển |
| Retrieval fee | Áp dụng với Nearline/Coldline/Archive | Không tính thông thường |
| Early deletion | Có thể áp dụng khi delete/rewrite sớm | Không áp dụng thông thường, trừ enablement |
| Class transition operations | Có phí Class A với SetStorageClass | Theo quy tắc Autoclass |
| Management fee | Không có Autoclass fee | Có |
| Small objects | Có thể lọc bằng sizeAboveBytes | Object nhỏ dưới 128 KiB giữ Standard |
| Kiểm soát compliance | Cần phối hợp retention/holds | Cần phối hợp retention/holds |
| Phí bật trên bucket cũ | Không phải enablement của Autoclass | Có thể đáng kể |

### Quy tắc lựa chọn thực tế

- Archive log theo thời gian, không đọc lại: lifecycle tuổi object thường dễ kiểm soát.
- Bộ sưu tập ảnh cũ thỉnh thoảng bất ngờ được truy cập nhiều: Autoclass đáng thử.
- Data lake có access theo mùa và số lượng object lớn: benchmark hai kịch bản.
- File build/cache ngắn hạn: đặt lifecycle xóa và cân nhắc soft delete, không nhất thiết Autoclass.
- Các dữ liệu có legal hold/retention: thiết kế pháp lý và backup trước khi tối ưu class.

## 15. Chi phí của hàng triệu object nhỏ

Giả sử bucket có 20 triệu objects kích thước 8 KiB. Tổng data size khoảng 153 GiB, nhưng số object rất lớn. Nếu một lifecycle rule chuyển từng object sang Coldline, phí Class A có thể đáng kể so với phần tiết kiệm storage mỗi tháng.

### Ví dụ giả định

- 20.000.000 objects.
- Mỗi object 8 KiB.
- Tất cả object chuyển lớp một lần.
- Class A operation giả định 0,02 USD / 1.000 operations.

Phí operations minh họa:

~~~text
20.000.000 / 1.000 × 0,02 USD = 400 USD
~~~

Đây là phép tính minh họa với đơn giá giả định; phải kiểm tra SKU hiện hành theo class/location/bucket type. Nếu tiền lưu trữ chỉ giảm vài USD mỗi tháng, sẽ mất nhiều thời gian để bù operation fee.

### Cách giảm chi phí small objects

1. Dùng sizeAboveBytes để không chuyển lớp các object rất nhỏ.
2. Nếu workload cho phép, gom các bản ghi nhỏ thành file lớn theo partition/time window.
3. Tối ưu số lần list/metadata requests.
4. Dùng inventory report thay vì quét toàn bucket bằng API.
5. Dùng compression cho dữ liệu phù hợp.
6. Giữ schema/index để vẫn có thể tìm và đọc một phần dữ liệu.
7. Không gộp object nếu làm suy giảm kiểm toán, khả năng truy xuất từng bản ghi hoặc latency.

Với file ảnh cá nhân hoặc dữ liệu cần random access, việc gộp có thể làm chi phí đọc tăng; phải cân bằng.

## 16. Phân tích phí truy xuất qua một tình huống

Một kho báo cáo lưu **3 TiB** ở Coldline và mỗi tháng người dùng tải lại **1 TiB**. Với giá retrieval giả định 0,02 USD/GiB, riêng retrieval có thể khoảng:

~~~text
1 TiB = 1.024 GiB
1.024 × 0,02 USD = 20,48 USD/tháng
~~~

Ngoài ra còn operations và network egress nếu dữ liệu được chuyển tới đích tính phí. Nếu báo cáo được tải liên tục, Standard hoặc Nearline có thể có tổng chi phí hợp lý hơn, dù giá lưu at-rest cao hơn.

### Công thức break-even

Gọi:

- S: dung lượng lưu trung bình (GiB).
- R: lượng dữ liệu đọc mỗi tháng (GiB).
- P_standard: giá lưu Standard trên GiB/tháng.
- P_cold: giá lưu class lạnh trên GiB/tháng.
- P_retrieval: giá truy xuất GiB.
- O: chênh lệch phí operations.
- N: chênh lệch network/replication.

~~~text
Savings khi chuyển sang class lạnh
  ≈ S × (P_standard - P_cold)
    - R × P_retrieval
    - O - N - EarlyDelete - TransitionCosts
~~~

Nếu savings âm, class lạnh không hợp lý về mặt tài chính. Nếu savings dương nhưng SLO không đạt hoặc restore drill quá đắt, cũng không nên chọn.

Đừng dựa vào một tháng bình thường nếu có sự kiện cuối năm hoặc DR rehearsal đọc dữ liệu rất lớn.

## 17. Cloud Billing và cách tìm nguồn lãng phí

Cloud Billing reports và export sang BigQuery giúp phân tích chi phí Cloud Storage theo:

- Project và service.
- SKU mô tả storage class/location.
- Operation charges.
- Retrieval SKUs.
- Data transfer và replication.
- Early deletion.
- Soft delete và Autoclass charges.
- Credits/discounts và nhãn cost allocation.

Một câu SQL minh họa về ý tưởng nhóm chi phí theo SKU (phải thay tên bảng của billing export thực tế):

~~~sql
SELECT
  service.description AS service_name,
  sku.description AS sku_name,
  DATE(usage_start_time) AS usage_day,
  SUM(cost) AS cost_before_credits_usd
FROM PROJECT_ID.BILLING_DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID
WHERE service.description = 'Cloud Storage'
  AND usage_start_time >= TIMESTAMP('2026-10-01')
GROUP BY 1, 2, 3
ORDER BY usage_day DESC, cost_before_credits_usd DESC;
~~~

**Chú ý:** tên bảng trong ví dụ là placeholder, không phải BigQuery identifier có thể chạy nguyên văn. Với tên thật có ký tự đặc biệt, cần dùng backticks theo cú pháp BigQuery. Tùy cấu hình export và billing model, phải trừ credits/discounts phù hợp mới ra net cost. Query ở trên chỉ minh họa tổng cost trước credits.

### Những câu hỏi dashboard nên trả lời

- Bucket nào tăng storage bytes nhanh nhất?
- Tỷ lệ Standard/Nearline/Coldline/Archive theo dữ liệu thực tế?
- Retrieval charges có tăng khi chuyển lớp không?
- Có peak phí operations khi lifecycle chạy?
- Bao nhiêu bytes/objects ở trạng thái noncurrent hoặc soft-deleted?
- Egress tới region/provider nào đang lớn nhất?
- Chi phí tính trên mỗi backup, mỗi report, mỗi 1.000 requests có giảm không?

Một khoản tiết kiệm do khối lượng dữ liệu ít đi không nên được ghi toàn bộ là savings từ thay đổi storage class. Hãy chuẩn hóa theo dung lượng, tần suất đọc và số lượng giao dịch.

## 18. Metrics, inventory và cảnh báo vận hành

### Cloud Monitoring

Các nhóm metric đáng quan sát:

- Bytes lưu theo storage class.
- Object count.
- API request count và request latency.
- Read/write/error rate.
- Egress và network.
- Số lượng soft-deleted/noncurrent objects nếu metric/source hỗ trợ.
- Dấu hiệu retry, 429 hoặc request surge từ ứng dụng.
- Storage growth rate và dự báo dung lượng.

### Inventory reports và Storage Intelligence

Với bucket có hàng triệu object, inventory report định kỳ có thể cung cấp metadata để phân tích:

- Name/prefix.
- Size.
- Storage class.
- Creation time.
- Generation.
- Retention/hold fields nếu có.
- Các trường hỗ trợ trong schema report.

Storage Intelligence và các công cụ insight/advisor bổ sung có thể có phí hoặc yêu cầu enablement. Cần xác minh entitlement, pricing, region và quyền truy cập trước khi dùng.

### Alert hữu ích

| Alert | Ý nghĩa |
|---|---|
| Storage cost tăng > ngưỡng baseline | Có thể do tăng dữ liệu, versioning hoặc soft delete |
| Retrieval charges tăng đột biến | Ứng dụng đọc nhiều object lạnh |
| Early deletion SKU xuất hiện | Object bị xóa/rewrite trước thời hạn |
| Object count tăng nhanh | Rò rỉ object nhỏ hoặc multipart upload |
| Soft-deleted bytes tăng | Retention giữ dữ liệu tạm |
| Egress vượt ngân sách | Data transfer hoặc DR/analytics ngoài dự kiến |
| Lifecycle change audit event | Quy tắc tự xóa/chuyển class vừa bị sửa |

## 19. Bảo mật và an toàn khi thay đổi lifecycle

Lifecycle Delete không phải thao tác tối ưu vô hại. Nếu rule sai prefix hoặc age, số lượng lớn object có thể bị xóa, không thể khôi phục nếu soft delete/backup/retention không còn đáp ứng.

### Trước khi thay đổi

1. Xác nhận đúng bucket, project, location và owner.
2. Xuất/read toàn bộ lifecycle hiện tại.
3. Kiểm tra soft delete, Object Versioning, retention policy và object holds.
4. Dùng inventory để ước tính số object sẽ match từng rule.
5. Đánh giá charges của lớp cũ và lớp mới.
6. Kiểm tra tiêu chí RTO/RPO và legal retention.
7. Thử rule trên bucket test hoặc prefix nhỏ.
8. Đảm bảo có thể restore các object thuộc nhóm quan trọng.
9. Có approval của data owner/SRE/FinOps.
10. Áp dụng IaC hoặc pipeline reviewable, không sửa tay trên Console không ghi nhận.

### Sau khi thay đổi

- Đọc lại cấu hình lifecycle của bucket.
- Theo dõi 24–48 giờ đầu về lớp lưu, deletion, operations và billing.
- Xem audit logs nếu có thay đổi ngoài pipeline.
- Kiểm tra test retrieval, generation và checksum.
- Đo cost reduction qua chu kỳ phù hợp, không chỉ ngày đầu.
- Ghi nhận rollback caveat: thay rule không khôi phục object đã bị xóa, và rule cũ có thể còn hoạt động trong cửa sổ propagation.

### Quản lý IAM

Chỉ nhóm được ủy quyền mới có quyền sửa bucket lifecycle, retention và soft delete policy. Runtime Java service thường chỉ cần quyền đọc/ghi đúng bucket hoặc managed folder; không nên được cấp quyền quản trị bucket policy.

Sử dụng uniform bucket-level access, public access prevention và CMEK theo yêu cầu, nhưng không coi các control này là thay thế cho backup hoặc versioning.

## 20. Terraform: quản lý lifecycle theo IaC

Một cấu hình Terraform minh họa cho bucket dữ liệu báo cáo:

~~~hcl
resource "google_storage_bucket" "reports" {
  project       = var.project_id
  name          = var.bucket_name
  location      = var.location
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age                   = 60
      matches_storage_class = ["STANDARD"]
      matches_prefix        = ["reports/"]
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 730
      matches_prefix = ["reports/"]
    }
  }
}
~~~

Các trường và support cụ thể cần đối chiếu với phiên bản hashicorp/google provider đã được khóa trong dự án. Tên bucket phải duy nhất theo quy tắc Cloud Storage. Các lifecycle rules trên chỉ là ví dụ, không phải chính sách retention phù hợp mọi loại dữ liệu.

### Terraform plan cần review gì?

- Có hành động tạo/xóa bucket ngoài dự kiến?
- Lifecycle cũ có bị thay thế toàn bộ không?
- age, prefix và class có đúng không?
- Có policy deletion/retention khác liên quan?
- Bucket có Object Versioning hoặc soft delete mà change không xét tới?
- Có resource được quản lý bởi state khác?
- IAM cho service account có bị mở rộng không?

Không chạy apply production chỉ để "test" HCL. Validate/plan và review đầu ra là bước cần thiết; việc áp dụng thực tế cần quy trình change.

## 21. Java/Spring: cách ứng dụng làm thay đổi chi phí truy xuất

Một dịch vụ Spring Boot sử dụng Cloud Storage để đọc tài liệu thường xuyên. Cách code tải dữ liệu có thể tác động tới hóa đơn:

- Gọi readAllBytes cho object lớn sẽ tải toàn bộ nội dung, làm tăng memory và lượng dữ liệu đọc.
- Đọc nhiều lần cùng object có thể nhân phí retrieval nếu class lạnh.
- List bucket hoặc prefix liên tục tạo operation requests.
- Overwrite cùng tên object thường xuyên có thể sinh noncurrent versions.
- Kết hợp CDN/cache hoặc metadata cache theo cách phù hợp có thể giảm origin reads.
- Truyền file từ storage qua backend tới người dùng có thể tăng egress hoặc bottleneck; signed URLs cần thiết kế quyền và expiry.

### Ví dụ Java đọc metadata trước khi tải nội dung

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReportReader {
    private final Storage storage = StorageOptions.getDefaultInstance().getService();

    public long sizeOf(String bucket, String object) {
        Blob metadata = storage.get(BlobId.of(bucket, object));
        if (metadata == null) {
            throw new IllegalArgumentException("Object not found");
        }
        return metadata.getSize();
    }
}
~~~

Ví dụ trên đọc metadata để biết object size mà chưa tải toàn bộ payload; metadata requests vẫn có thể chịu phí operations. Với production, dùng Spring bean/client lifecycle phù hợp, xử lý authentication/authorization, timeout, retries, generation checks, limits và không dùng nội dung metadata như nguồn xác thực nghiệp vụ.

### Quản lý cache trong ứng dụng

Nếu ứng dụng nhiều lần tải cùng một file lớn:

1. Đánh giá cache theo ETag/generation và freshness.
2. Dùng HTTP conditional requests/range requests khi có ích.
3. Không cache dữ liệu nhạy cảm không có bảo vệ.
4. Theo dõi cache hit ratio và số GiB Cloud Storage thực đọc.
5. Chọn storage class sau khi đã tính lưu lượng cache miss.

Một object "lạnh" theo business có thể trở thành "nóng" ở cấp API nếu mỗi user request đều tải lại toàn bộ nội dung.

## 22. Tình huống 1: kho ảnh của sàn thương mại điện tử

Một đội vận hành 30 TiB ảnh sản phẩm:

- 5 TiB ảnh sản phẩm bán chạy, được đọc liên tục.
- 15 TiB ảnh sản phẩm ít được xem, có đợt khuyến mãi làm traffic tăng bất ngờ.
- 10 TiB ảnh sản phẩm đã ngừng bán, chỉ cần lưu theo policy.

### Kịch bản tối ưu

| Nhóm | Hướng xử lý | Lý do |
|---|---|---|
| Hot images | Standard, CDN/cache phù hợp | Tối ưu latency và tránh phí retrieval |
| Warm/cold unpredictable | Thử Autoclass trong bucket riêng | Access thay đổi theo chiến dịch |
| Retired images | Lifecycle theo age/prefix và retention | Quy tắc dữ liệu rõ, ít read |
| Thumbnail rất nhỏ | Tránh chuyển lớp từng object thiếu hiệu quả | Phí Class A có thể ăn hết savings |

### Quy trình

1. Phân tích access logs, CDN cache hit và object size distribution.
2. Tách hoặc tổ chức bucket/prefix theo ownership và access patterns.
3. Chạy cost simulation bằng số GiB đọc và operations.
4. Thử Autoclass trên nhóm đủ điều kiện, tính phí management/enablement.
5. Triển khai lifecycle cho retired images theo policy được duyệt.
6. Theo dõi tổng hóa đơn 1–3 chu kỳ, không chỉ class storage.
7. Kiểm tra ảnh vẫn phục vụ đúng từ CDN/origin và không mất đối tượng.

## 23. Tình huống 2: backup Java database và logs

Một hệ thống Java/Spring trên GKE xuất backup database và application audit logs:

- Backup hằng ngày 500 GiB.
- Giữ 35 ngày để khôi phục nhanh.
- Backup cuối tháng lưu 13 tháng.
- Audit logs phải được giữ theo chính sách tuân thủ.
- Định kỳ diễn tập restore.

### Quyết định quan trọng

**Backup hằng ngày:** nếu lưu ngắn ngày và bị xóa trước 90/365 ngày, không nên mặc định chọn Coldline/Archive vì minimum duration. Standard hoặc Nearline có thể hợp lý hơn tùy lịch restore.

**Backup cuối tháng:** nếu giữ hơn một năm và rất ít đọc, Archive có thể phù hợp với lưu dài hạn, nhưng phải tính phí đọc trong DR drill.

**Audit logs:** lifecycle Delete chỉ được cấu hình sau khi security/legal xác nhận retention. Có thể cần Bucket Lock/retention, encryption và audit.

### Chi phí DR drill

Một restore drill đọc 20 TiB Archive data có thể tạo retrieval charges đáng kể cộng operations và network. Nhưng việc bỏ diễn tập để tiết kiệm tiền là sai hướng: cần **dự toán** chi phí khôi phục như một phần ngân sách độ tin cậy.

### Bài học về backup

- Có metadata backup và checksum.
- Có chính sách verify và khôi phục thử.
- Không giữ bản sao duy nhất ở cùng failure domain với ứng dụng.
- Xác định RPO/RTO trước khi chọn region/dual-region.
- Theo dõi backup size, retention và restore frequency.
- Dùng lifecycle cho các bản cũ sau khi đủ thời hạn.
- Tách dữ liệu tạm khỏi backup bắt buộc giữ lâu.

## 24. Runbook tối ưu bucket production

~~~text
1. Inventory & billing baseline
           |
           v
2. Owner + retention + RTO/RPO review
           |
           v
3. Cost model (Standard / manual / Autoclass)
           |
           v
4. Policy simulation + sample prefix
           |
           v
5. Approval + IaC plan
           |
           v
6. Apply in maintenance/change window
           |
           v
7. Verify data + policy + operations
           |
           v
8. Monitor billing + error budgets
           |
           v
9. Record savings, exceptions, next review
~~~

### Gate trước khi apply

- Có bằng chứng số lượng objects sẽ bị ảnh hưởng.
- Không vi phạm retention/legal hold.
- Có khả năng restore.
- Có kế hoạch xử lý rủi ro lifecycle propagation.
- Có ngưỡng chi phí operations, retrieval, soft delete.
- Có người trực theo dõi trong các ngày đầu.
- Có phương án phản hồi khi người dùng không thể đọc object.

### Gate để chấp nhận kết quả

- SLO ứng dụng không suy giảm.
- Số object/generation còn đúng theo policy.
- Không có deletion ngoài prefix dự kiến.
- Bản restore thử đọc thành công.
- Chi phí operations/retrieval/egress không triệt tiêu savings.
- Net cost per workload cải thiện theo chu kỳ đánh giá.

## 25. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chọn Archive vì giá lưu thấp nhất | Retrieval/early deletion làm tổng phí cao | Tính access volume và retention |
| Coi Archive là offline storage có delay nhiều giờ | Thiết kế restore sai | Hiểu Cloud Storage classes là online |
| Chỉ tính dung lượng live | Thiếu chi phí noncurrent/soft-deleted | Inventory toàn bộ generations và soft delete |
| Tạo lifecycle Delete không có prefix | Xóa dữ liệu ngoài phạm vi | Scope bằng prefix/conditions và review |
| Nghĩ age tính từ lần đổi class | Chuyển/xóa sớm hơn dự kiến | age tính từ object creation |
| Nghĩ thay rule áp dụng tức thì | Rule cũ vẫn có thể tác động | Dự phòng cửa sổ propagation tới 24h |
| Chuyển hàng triệu object nhỏ | Class A vượt storage savings | Lọc size hoặc tổ chức dữ liệu khác |
| Bật Autoclass rồi SetStorageClass | Cấu hình không hợp lệ | Để Autoclass quản lý classes |
| Bật Autoclass trên bucket cũ không mô phỏng | Phí enablement và class warm-up cao | So sánh chi phí trước khi bật |
| Tắt soft delete vì muốn giảm phí | Mất cơ chế phục hồi xóa nhầm | Đánh giá data criticality/backup |
| Dùng cùng bucket cho temporary và compliance | Lifecycle/retention xung đột | Tách bucket theo lifecycle |
| Không tính network egress và replication | TCO thấp giả tạo | Bổ sung destination/location |
| Ghi đè file liên tục nhưng bật versioning | Tích lũy versions lớn | Lifecycle dọn noncurrent có policy |
| Không kiểm tra giá region và SKU | Ước tính sai | Đối chiếu Billing/pricing hiện hành |
| Dùng API list toàn bộ bucket hằng giờ | Tăng operation charges | Inventory reports/filters |
| Sửa policy bằng tay không có Git history | Drift và khó rollback | IaC/change review và audit |
| Áp lifecycle vào bucket do Artifact Registry quản lý | Có thể làm hỏng container image layers | Dùng Artifact Registry cleanup policies |

## 26. Checklist FinOps cho Cloud Storage

### Hiểu dữ liệu

- [ ] Bucket có owner, cost center, environment và data classification.
- [ ] Biết kích thước, số object, prefix và access pattern.
- [ ] Có dữ liệu retrieval/operations/egress trong nhiều chu kỳ.
- [ ] Biết RTO/RPO và quy định lưu dữ liệu.
- [ ] Location, class và replication phù hợp ứng dụng.

### Thiết kế policy

- [ ] Đã so sánh Standard, Nearline, Coldline, Archive và trường hợp Rapid.
- [ ] Đã đánh giá minimum duration và early deletion.
- [ ] Lifecycle rules được review theo age, prefix, size và isLive.
- [ ] Không có Delete rule không được owner phê duyệt.
- [ ] Đã kiểm tra Object Versioning và noncurrent lifecycle.
- [ ] Đã kiểm tra soft delete retention và ảnh hưởng chi phí.
- [ ] Đã kiểm tra bucket/object retention và legal holds.
- [ ] Nếu Autoclass: đánh giá management fee, enablement charge và 128 KiB rule.
- [ ] Không cấu hình SetStorageClass trên Autoclass bucket.

### Triển khai và vận hành

- [ ] Đã lưu cấu hình policy trước thay đổi.
- [ ] Thử nghiệm trên staging/bucket nhỏ/prefix an toàn.
- [ ] Có Change Approval và rollback/restore plan.
- [ ] Theo dõi 24h propagation của lifecycle rule.
- [ ] Có Cloud Billing dashboard cho storage/retrieval/operations/egress.
- [ ] Có alerts khi object count và soft delete cost tăng đột biến.
- [ ] Có kiểm tra restore thực tế.
- [ ] Đo savings dựa trên net cost đã chuẩn hóa, không chỉ giảm at-rest storage.
- [ ] Duy trì review định kỳ và exception policy.

## Kết luận

Cloud Storage FinOps cần tối ưu đồng thời **lớp lưu, vòng đời dữ liệu và lượng truy xuất**. Standard phù hợp dữ liệu nóng; Nearline, Coldline và Archive phù hợp mức truy cập thấp hơn nhưng có minimum storage duration và retrieval fees. Object Lifecycle Management giúp chuyển lớp/xóa theo chính sách, còn Autoclass tự điều chỉnh class theo access pattern với phí quản lý và các quy tắc riêng. Soft delete, versioning, retention, số lượng object nhỏ và network transfer có thể tạo chi phí không nhìn thấy khi chỉ kiểm tra giá lưu/GiB. Một quyết định tốt cần bắt đầu từ dữ liệu thực tế, có owner và chính sách retention, được thử nghiệm trước, rồi theo dõi SLO và hóa đơn sau thay đổi.

## Tài liệu tham khảo

- [Google Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Cloud Storage: Storage classes](https://docs.cloud.google.com/storage/docs/storage-classes)
- [Cloud Storage: Object Lifecycle Management](https://docs.cloud.google.com/storage/docs/lifecycle)
- [Cloud Storage: Lifecycle configuration examples](https://docs.cloud.google.com/storage/docs/lifecycle-configurations)
- [Cloud Storage: Manage object lifecycles](https://docs.cloud.google.com/storage/docs/managing-lifecycles)
- [Cloud Storage: Autoclass](https://docs.cloud.google.com/storage/docs/autoclass)
- [Cloud Storage: Use Autoclass](https://docs.cloud.google.com/storage/docs/using-autoclass)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud Storage: Bucket retention policy](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Cloud Storage: Bucket inventory reports](https://docs.cloud.google.com/storage/docs/insights/using-inventory-reports)
- [Cloud Storage: Storage Intelligence](https://docs.cloud.google.com/storage/docs/storage-intelligence/overview)
- [Cloud Billing: Export data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Cloud Monitoring: Cloud Storage metrics](https://docs.cloud.google.com/monitoring/api/metrics_gcp)
- [Terraform google_storage_bucket resource](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/storage_bucket)

