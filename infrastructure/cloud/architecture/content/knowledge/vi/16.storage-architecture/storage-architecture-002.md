# Thiết kế namespace, khóa đối tượng và phân vùng dữ liệu

## 1. Vì sao cách tổ chức dữ liệu là quyết định kiến trúc?

Khi dữ liệu tăng từ vài nghìn bản ghi lên hàng tỷ đối tượng hoặc nhiều terabyte, câu hỏi “lưu ở đâu?” chưa đủ. Hệ thống cần một cách tổ chức để biết **dữ liệu thuộc ai, nằm trong phạm vi nào, được truy vấn bằng cách gì, phân phối ra sao và sẽ được di chuyển hoặc xóa như thế nào**. Nếu thiết kế namespace, object key và partition thiếu chủ đích, hệ thống có thể gặp hot partition, chi phí truy vấn cao, khó cô lập tenant, khó thay đổi cấu trúc hoặc không thể thực hiện yêu cầu lưu giữ/xóa dữ liệu.

Ba khái niệm có liên quan nhưng khác nhau:

- **Namespace:** không gian tên logic giúp nhóm, định danh và phân định quyền sở hữu dữ liệu. Ví dụ bucket/container, schema, database, tenant namespace hoặc prefix.
- **Object key:** tên định danh một đối tượng trong namespace, thường được dùng để đọc, ghi, xóa và tra cứu object. Với object storage, key thường là chuỗi; dấu gạch chéo thường chỉ tạo cảm giác phân cấp, không nhất thiết là thư mục vật lý.
- **Partition:** cách chia dữ liệu thành những phần có thể được quản lý, lưu trữ, truy vấn hoặc phân phối độc lập. Partition có thể dựa trên thời gian, tenant, hash key, range hoặc kết hợp nhiều chiều.

Trong module **CLOUD_ARCHITECTURE**, thiết kế lưu trữ phải kết nối yêu cầu nghiệp vụ với lựa chọn dữ liệu, mạng, compute và mô hình triển khai. Mục tiêu là cân bằng **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ lưu ảnh phòng, hóa đơn, tệp đính kèm, dữ liệu booking và sự kiện phân tích. Hệ thống có nhiều khách hàng doanh nghiệp (tenant), dữ liệu tăng theo ngày, cần truy vấn theo tenant và thời gian, đồng thời hỗ trợ retention, backup, audit và xóa dữ liệu theo chính sách.

## 2. Phân biệt namespace ở các lớp lưu trữ

Từ namespace được dùng ở nhiều công nghệ nhưng phạm vi và semantics không giống nhau. Thiết kế phải xác định rõ **namespace đang được nói tới ở lớp nào**.

| Lớp | Cấu trúc/namespace thường gặp | Vai trò |
| --- | --- | --- |
| Object storage | Account/project → bucket/container → object key | Tách vùng dữ liệu, quyền, lifecycle và định danh object |
| Relational database | Instance/cluster → database → schema → table → partition | Tổ chức logic, quyền truy cập, truy vấn và phân phối dữ liệu |
| Key-value / NoSQL | Table/collection → partition key → sort key | Phân vùng dữ liệu và truy xuất theo access pattern |
| Distributed cache | Cluster → keyspace hoặc key convention | Tách cache theo ứng dụng/tenant và tránh xung đột key |
| Data lake/warehouse | Catalog/database/schema → dataset/table → partition columns | Quản lý metadata và tối ưu quét dữ liệu |
| Kubernetes | Cluster → namespace → resource names | Cô lập logic tài nguyên và quyền trong cluster; không phải namespace lưu trữ object |

**Namespace logic không mặc nhiên là ranh giới bảo mật mạnh.** Prefix tenant trong object key không tự ngăn tenant khác đọc object nếu IAM/bucket policy cho phép truy cập rộng. Tương tự, PostgreSQL schema giúp phân nhóm object nhưng không tự thay thế row-level security hoặc quyền truy cập của database role.

### 2.1. Chọn ranh giới namespace

Một tổ chức có thể lựa chọn namespace dùng chung, namespace theo tenant, theo môi trường, theo miền nghiệp vụ hoặc theo phân loại dữ liệu. Mỗi cách có đánh đổi:

| Cách tổ chức | Ưu điểm | Hạn chế/đánh đổi |
| --- | --- | --- |
| Dùng chung, phân biệt tenant bằng key/column | Ít tài nguyên quản trị, dễ dùng chung capacity và pipeline | Cần kiểm soát quyền chặt; noisy neighbor và truy vấn sai tenant có blast radius lớn |
| Tách namespace theo tenant | Cô lập logic, dễ áp policy/retention riêng | Nhiều bucket/database/schema làm tăng metadata, quota, chi phí và automation |
| Tách theo môi trường | Giảm rủi ro thao tác nhầm giữa dev và prod | Tốn tài nguyên và phải quản lý sao chép/ẩn danh dữ liệu thử nghiệm |
| Tách theo domain | Ownership và vòng đời rõ, thuận tiện phân quyền | Cần quy tắc tích hợp và tra cứu xuyên domain |

Không có một số lượng tenant hay kích thước dữ liệu duy nhất để quyết định tách namespace. Cần xét yêu cầu cô lập, số lượng tenant, tốc độ tăng, quyền quản trị, giới hạn dịch vụ, lifecycle, chi phí và khả năng automation.

## 3. Thiết kế namespace từ yêu cầu và ranh giới tin cậy

Trước khi đặt tên bucket/table/prefix, hãy thu thập:

1. **Chủ sở hữu dữ liệu:** domain/team nào chịu trách nhiệm tạo, sửa, đọc và xóa?
2. **Đối tượng truy cập:** ứng dụng, service account, tenant, người dùng hay hệ thống phân tích?
3. **Phân loại và vị trí:** dữ liệu public/internal/confidential; được phép lưu ở vùng nào; backup/log có cùng yêu cầu không?
4. **Cách truy vấn:** lookup theo ID, liệt kê theo tenant, truy vấn theo thời gian, tìm theo trạng thái hay batch scan?
5. **Tốc độ tăng và kích thước:** object count, object size, write/read rate, tenant lớn nhất và mức burst.
6. **Vòng đời:** thời gian lưu, chuyển lớp lưu trữ, archive, legal hold, xóa và khôi phục.
7. **Đường di chuyển:** có cần đổi key format, partition key, bucket, database hoặc region trong tương lai không?

Ví dụ layout logic cho nền tảng đặt chỗ:

~~~text
organization/
  production/
    booking/
    customer-documents/
    property-media/
    billing/
    audit/
    analytics/
  non-production/
    booking/
    synthetic-test-data/
~~~

Đây là sơ đồ khái niệm. Trên object storage, các nhánh có thể là bucket/container riêng hoặc prefix trong một bucket. Trên database, chúng có thể là schema/table riêng hoặc database riêng. Chọn cách hiện thực sau khi đánh giá quyền truy cập, giới hạn namespace, lifecycle và yêu cầu vận hành.

### 3.1. Namespace phải đi cùng ownership và policy

Mỗi namespace quan trọng nên có metadata:

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| namespaceId | prod-property-media | ID ổn định, không phụ thuộc label hiển thị |
| owner | property-platform | Nhóm chịu trách nhiệm |
| environment | prod | Phân tách vòng đời |
| dataClassification | confidential | Chọn kiểm soát và retention |
| region | approved-region-1 | Ràng buộc vị trí |
| retentionPolicy | media-7y | Lưu giữ theo nghiệp vụ |
| encryptionPolicy | managed-key-policy-a | Cách bảo vệ dữ liệu |
| costCenter | CC-104 | Phân bổ chi phí |

Không nhúng thông tin bí mật vào tên namespace. Tên hiển thị có thể đổi, nhưng ID và mapping tới policy nên ổn định hoặc có quy trình migration rõ.

## 4. Thiết kế object key: định danh ổn định và dễ vận hành

Object key là địa chỉ để thao tác với object trong namespace. Một key tốt cần ổn định, duy nhất trong namespace, hỗ trợ access pattern, không tiết lộ thông tin nhạy cảm, dễ quản lý lifecycle/audit và có đường di chuyển.

### 4.1. Mẫu cấu trúc key

Một mẫu khái niệm:

~~~text
<domain>/<tenant-ref>/<object-type>/<time-bucket>/<stable-id>/<variant>
~~~

Ví dụ:

~~~text
property-media/tnt-8f2a/room-image/2026/12/obj-01J8K2/original.jpg
property-media/tnt-8f2a/room-image/2026/12/obj-01J8K2/thumbnail-640.webp
booking-documents/tnt-8f2a/invoice/2026/12/obj-01J8M4/invoice.pdf
~~~

Key dùng tenant reference giả, thời gian và ID ổn định. tenant-ref không nên là email hay tên tổ chức; stable-id nên là ID ngẫu nhiên/opaque hoặc ID được tạo theo quy tắc không để lộ thông tin nội bộ.

### 4.2. Thư mục trong object storage thường là prefix logic

Nhiều object storage mô hình hóa object theo cặp bucket và key. Ký tự gạch chéo thường được dùng để nhóm prefix cho listing và giao diện; nó không nhất thiết có thư mục vật lý. Vì vậy:

- Xóa “folder” có thể thực chất là liệt kê và xóa tất cả object có prefix.
- Quyền theo prefix phụ thuộc policy hỗ trợ của dịch vụ; không suy rằng folder có ACL riêng.
- Key chứa nhiều dấu gạch chéo không đồng nghĩa object nằm trong nhiều tầng filesystem.
- Công cụ liệt kê prefix có thể có chi phí và giới hạn pagination; tránh thiết kế cần list hàng triệu object mỗi request.

### 4.3. Quy tắc ký tự, encoding và độ dài

Chọn một bộ quy tắc key nhất quán: ưu tiên chữ thường ASCII, chữ số và dấu phân cách đơn giản; tránh khoảng trắng, dấu tiếng Việt, ký tự điều khiển và ký tự dễ bị encode khác nhau qua URL/shell; quy định chuẩn percent-encoding nếu key được truyền trong URL; tránh dấu phân cách mơ hồ; giới hạn độ dài theo dịch vụ object storage.

Không coi key là đường dẫn filesystem an toàn. Nếu ứng dụng nối key trực tiếp vào path local, cần chuẩn hóa và chống path traversal.

### 4.4. Không để key chứa dữ liệu bí mật

Key thường xuất hiện trong access log, URL ký sẵn, trace, báo cáo chi phí và công cụ quản trị. Không nên đưa trực tiếp email, số điện thoại, tên đầy đủ, địa chỉ cá nhân, token, session ID, thông tin xác thực hoặc nội dung nhạy cảm.

Ngay cả khi key là opaque, cần đánh giá nó có thể được liên kết với danh tính từ hệ thống khác không. Quyền truy cập object phải được kiểm soát ở lớp xác thực/ủy quyền, không dựa vào việc key khó đoán.

## 5. Chọn ID và chiến lược chống ghi đè

Object key thường được tạo từ domain, tenant reference, loại object, thời gian và ID. ID đóng vai trò quan trọng trong khả năng mở rộng và tính đúng đắn.

| Kiểu ID | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| UUID ngẫu nhiên | Dễ tạo phân tán, khó đoán hơn ID tuần tự | Key dài; phân bố theo prefix phải cân nhắc |
| ULID/ID có thành phần thời gian | Có tính sắp xếp gần theo thời gian, thuận tiện debug | Có thể tạo vùng ghi nóng nếu nhiều ID cùng prefix; phần thời gian có thể tiết lộ thời điểm |
| Sequence tăng dần | Ngắn, dễ sắp thứ tự | Có thể tập trung ghi, lộ quy mô và khó tạo duy nhất giữa nhiều producer |
| Hash của định danh | Phân bố khá đều và che một phần thông tin đầu vào | Không khôi phục ngược dễ dàng; cần xử lý collision và secret nếu dùng HMAC |
| Composite key | Mã hóa access pattern rõ | Key dài, thay đổi cấu trúc gây migration và phụ thuộc từng field |

Với object lưu file, ID ngẫu nhiên đủ dài và do server cấp thường phù hợp. Nếu cần chống trùng, dùng conditional write hoặc cơ chế create-only mà dịch vụ hỗ trợ; không chỉ kiểm tra “object chưa tồn tại” rồi mới ghi vì hai writer đồng thời vẫn có thể race.

### 5.1. Ghi object có điều kiện và tính bất biến

Đối với hóa đơn hoặc tài liệu giao dịch, có thể dùng key bất biến gắn với object ID và version. Chỉnh sửa tạo phiên bản mới hoặc một bản ghi metadata trỏ tới phiên bản hiện hành. Cách này hỗ trợ audit nhưng tăng storage và yêu cầu retention rõ.

Không nên cho phép người dùng tải tệp lên key do họ tùy ý đặt trong namespace dùng chung. Hãy tạo object ID phía server, xác minh quyền sở hữu và kiểm tra metadata trước khi công bố tham chiếu.

## 6. Partitioning: chia dữ liệu theo access pattern

**Partitioning** chia một tập dữ liệu lớn thành phần nhỏ hơn theo quy tắc. Mục tiêu là giảm lượng dữ liệu phải quét, phân phối đọc/ghi qua nhiều node hoặc shard, giới hạn phạm vi backup/restore/maintenance, hỗ trợ xóa theo thời gian/tenant và giảm chi phí query bằng partition pruning.

Partitioning không tự động làm truy vấn nhanh hơn. Nếu truy vấn không chứa partition key, hệ thống có thể phải fan-out qua nhiều partition. Nếu dữ liệu phân bố lệch, một partition có thể nóng hơn phần còn lại.

### 6.1. Range partitioning

Dữ liệu được chia theo khoảng giá trị, thường dùng thời gian, ID hoặc vùng. Ví dụ partition theo tháng cho bảng event:

~~~sql
CREATE TABLE booking_events (
    event_id       UUID NOT NULL,
    tenant_id      TEXT NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    event_type     TEXT NOT NULL,
    payload        JSONB NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_events_2026_12
PARTITION OF booking_events
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
~~~

Ưu điểm là truy vấn theo khoảng thời gian và retention có thể hiệu quả, đặc biệt khi database loại bỏ partition không liên quan. Nhược điểm là ghi liên tục vào partition hiện tại có thể tạo hot partition; cần tạo partition trước thời điểm dữ liệu đến và xử lý dữ liệu trễ.

### 6.2. Hash partitioning

Dữ liệu được gán partition theo hash của key:

~~~text
partition = hash(tenantId + ":" + objectId) mod N
~~~

Hash giúp phân tán các giá trị có phân bố không đều tốt hơn range trong một số trường hợp. Tuy nhiên, thay đổi N có thể làm nhiều key ánh xạ sang partition mới, dẫn đến reshard/migration. Hash không bảo đảm cân bằng tuyệt đối nếu có tenant có dung lượng hoặc tốc độ truy cập vượt trội.

### 6.3. List partitioning

Dữ liệu được chia theo danh sách giá trị, ví dụ region, loại dữ liệu hoặc nhóm tenant. Cách này phù hợp khi số nhóm có giới hạn và ranh giới quản trị rõ. Nếu số tenant tăng không giới hạn, tạo partition riêng cho mỗi tenant có thể khiến metadata và vận hành phức tạp.

### 6.4. Composite partitioning

Có thể kết hợp range và hash, chẳng hạn partition theo tháng rồi subpartition theo tenant hash. Cách này hỗ trợ retention theo thời gian và giảm hot spot cho một phần tải, nhưng số partition tăng theo số tháng nhân số bucket hash. Cần ước lượng số partition, index, metadata, backup và thời gian migration trước khi chọn.

## 7. Chọn partition key theo access pattern

Không chọn partition key chỉ vì field có sẵn. Hãy liệt kê truy vấn quan trọng:

| Access pattern | Ví dụ truy vấn | Thuộc tính cần cân nhắc |
| --- | --- | --- |
| Đọc một booking | Get booking by ID | bookingId; có thể cần lookup index hoặc bảng định tuyến |
| Liệt kê booking của tenant theo thời gian | Tenant + time range | tenantId và occurredAt/createdAt |
| Tìm event của một booking | aggregateId + sequence/time | aggregateId, sequence hoặc partition key của stream |
| Liệt kê object media của property | tenant + property + type | tenant reference, property reference và object type |
| Xóa dữ liệu theo retention | time range hoặc tenant + time | partition theo thời gian/tenant phù hợp quy trình xóa |
| Analytics toàn hệ thống | time + event type | partition column để prune; tránh quét không cần thiết |

### 7.1. Cardinality và skew

- **Cardinality thấp:** ít giá trị khác nhau; một giá trị có thể nhận phần lớn traffic.
- **Cardinality cao:** nhiều giá trị; có thể phân phối tốt hơn nhưng vẫn cần kiểm tra skew.
- **Skew:** phân bố không đều, một số key/partition có dữ liệu hoặc tải vượt trội.
- **Hot key:** một key nhận tần suất truy cập cao, làm node/partition tương ứng thành bottleneck.

Nếu partition chỉ theo eventType, vài event type phổ biến có thể tạo partition nóng. Nếu partition theo tenantId, một tenant rất lớn có thể áp đảo partition của mình. Nếu partition theo timestamp ngày, mọi dữ liệu mới có thể dồn vào partition hiện tại.

### 7.2. Thiết kế key phân tán mà vẫn truy vấn được

Một mẫu có thể dùng:

~~~text
partitionKey = hash(tenantId + ":" + objectId) mod 32
sortKey      = occurredAt + "#" + eventId
~~~

Mẫu này phân tán ghi trong nhóm bucket hash, nhưng truy vấn theo tenant và thời gian cần biết hoặc duyệt các bucket thích hợp. Một thiết kế khác có thể dùng tenant ID làm partition key và chấp nhận scale theo tenant, nhưng cần cơ chế chuyển tenant lớn sang shard riêng khi vượt ngưỡng.

Không có key vừa tối ưu mọi truy vấn. Thường phải chọn access pattern quan trọng, tạo index/secondary projection cho truy vấn còn lại và chấp nhận một số truy vấn analytics chạy batch.

## 8. Thiết kế namespace và key cho object storage

Object storage thường phù hợp với ảnh, video, hóa đơn, backup, log archive và tệp dữ liệu lớn. Các thao tác phổ biến gồm put/get/delete/list theo bucket/container và key. Hãy thiết kế key theo cách truy cập, không theo cấu trúc thư mục của máy tính cá nhân.

| Layout | Ví dụ | Phù hợp | Hạn chế |
| --- | --- | --- | --- |
| Theo tenant trước | tenant/id/media/date/object-id | List/retention/quyền ở phạm vi tenant nếu tooling hỗ trợ prefix | Tenant lớn có thể tập trung vào một prefix |
| Theo thời gian trước | media/year/month/tenant/id | Batch theo ngày/tháng, archive và analytics | List theo tenant qua nhiều ngày cần fan-out |
| Theo hash shard trước | media/hash-prefix/tenant/id | Phân tán key theo hash prefix theo đặc tính dịch vụ | Khó list theo tenant/time nếu không có index |

Không áp dụng mẹo thêm prefix ngẫu nhiên một cách máy móc cho mọi object storage. Hành vi scale của dịch vụ và giới hạn theo prefix thay đổi theo nhà cung cấp/thời điểm. Cần đọc tài liệu dịch vụ hiện hành, đo workload và chỉ thêm shard prefix khi có bằng chứng. Hash prefix cũng làm truy vấn/listing khó hơn nếu không có catalog metadata.

### 8.1. Dùng catalog/index thay vì quét bucket

Khi giao diện cần liệt kê “tất cả hóa đơn của tenant A trong tháng”, có thể duy trì metadata index trong database:

| objectId | tenantId | objectType | createdAt | objectKey | status |
| --- | --- | --- | --- | --- | --- |
| obj-01J8 | tnt-8f2a | invoice | 2026-12-18 | billing/tnt-8f2a/2026/12/obj-01J8/invoice.pdf | active |
| obj-01J9 | tnt-8f2a | invoice | 2026-12-19 | billing/tnt-8f2a/2026/12/obj-01J9/invoice.pdf | archived |

Ứng dụng truy vấn catalog theo tenant/time/type rồi mới lấy object. Catalog trở thành metadata quan trọng: cần consistency, backup, index, quyền và cách đồng bộ khi object upload/delete thất bại một nửa.

### 8.2. Quy trình upload an toàn

1. Client yêu cầu API tạo upload session.
2. Server xác thực user/tenant và cấp object ID cùng key dự kiến.
3. Server cấp URL ký sẵn có thời hạn và phạm vi object phù hợp nếu mô hình dùng pre-signed upload.
4. Client upload tới object storage; kích thước, content type và checksum được kiểm tra theo khả năng dịch vụ.
5. Backend xác minh upload hoàn tất, quét malware/kiểm tra nội dung nếu cần và cập nhật catalog.
6. Chỉ công bố object cho consumer sau khi xác nhận trạng thái hợp lệ.

Không coi Content-Type do client gửi là bằng chứng an toàn. Object mới upload chưa được xác minh không nên xuất hiện ở đường tải xuống công khai. Cần giới hạn thời hạn URL, quyền, object size, checksum và xử lý upload dang dở.

## 9. Namespace, tenant isolation và kiểm soát truy cập

Với multi-tenant, ranh giới namespace là một phần của mô hình bảo mật:

| Mô hình | Mức cô lập | Phù hợp khi |
| --- | --- | --- |
| Bucket/container riêng cho từng tenant | Tách namespace rõ, dễ áp policy/retention riêng | Số tenant hữu hạn hoặc khách hàng có yêu cầu cô lập mạnh |
| Prefix riêng trong bucket dùng chung | Đơn giản và tiết kiệm namespace | Policy có thể giới hạn prefix đáng tin cậy, ứng dụng kiểm tra tenant |
| Database/schema riêng | Có thể tách quyền và vòng đời theo tenant | Tenant ít hoặc có yêu cầu quản trị riêng |
| Shared table với tenant_id | Dễ dùng chung schema và connection pool | Row-level policy, query scoping và kiểm thử cách ly đủ mạnh |
| Shard theo nhóm tenant | Phân phối capacity giữa nhiều database | Cần scale-out, tenant lớn và automation quản trị shard |

### 9.1. Không tin tenant ID từ client

Tenant ID phải được suy ra hoặc xác minh từ identity/token/session đã xác thực và membership được kiểm tra. Không cho client gửi tùy ý tenantId rồi dùng trực tiếp để tạo object key hoặc query database.

Trong mọi thao tác, cần bảo đảm:

- Tenant của request được xác minh.
- Object/row thuộc tenant đó trước khi đọc/sửa/xóa.
- Key không thể bị thao túng để truy cập prefix khác.
- Worker và event consumer giữ tenant context, nhưng không tin tenantId trong payload nếu producer không được xác thực.
- Admin/support access có quy trình riêng, audit và quyền tối thiểu.

### 9.2. Row-level security và schema separation

Trong relational database, shared table có thể dùng tenant_id và row-level security (RLS) để áp điều kiện truy cập ở database. Đây là lớp bảo vệ bổ sung, không thay thế kiểm tra ở application. Cần kiểm tra connection pooling và cách thiết lập session context; nếu tenant context bị giữ nhầm giữa connection tái sử dụng, có thể gây rò dữ liệu.

Schema riêng tạo ranh giới quản trị nhưng vẫn cần quyền, connection, backup và migration. Nếu một application role có quyền đọc toàn bộ schema, việc tách schema không tạo cô lập thực chất.

## 10. Hot partition, noisy neighbor và cách giảm tải

Một key hoặc partition nhận quá nhiều traffic có thể khiến latency tăng dù tổng capacity toàn hệ thống còn dư. Cần quan sát request rate, read/write throughput và throttling theo partition/key, dung lượng tenant lớn nhất, latency p95/p99, retry và error.

| Biện pháp | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| Hash suffix/bucket | Chia một key nóng thành nhiều shard logic | Đọc/ghi tổng hợp phải fan-out |
| Salting | Thêm thành phần phân tán vào key | Cần biết salt để đọc hoặc tra index |
| Time bucketing | Chia dữ liệu theo phút/giờ/ngày/tháng | Truy vấn nhiều khoảng cần đọc nhiều partition |
| Tenant isolation | Đưa tenant rất lớn sang shard/namespace riêng | Tăng vận hành và di chuyển |
| Cache | Giảm số lần đọc nguồn dữ liệu | Cache invalidation, stale data và stampede |
| Queue/write buffering | Làm mượt burst ghi | Tăng độ trễ và yêu cầu idempotency |
| Rate limit/quota | Giới hạn tenant hoặc workload gây ồn | Cần công bằng và cơ chế nâng hạn mức |

### 10.1. Ví dụ salting cho counter nóng

Nếu một property có lượt xem quá lớn, một counter duy nhất có thể bị ghi đồng thời cao. Có thể dùng 16 bucket:

~~~text
counterKey = property-42#bucket-(hash(requestId) mod 16)
~~~

Mỗi request cập nhật một bucket; khi đọc tổng, hệ thống cộng 16 giá trị. Kỹ thuật này phân tán ghi nhưng tăng số lần đọc/tổng hợp và cần hash phân bố đủ đều. Nếu cần giá trị chính xác tức thời để quyết định đặt phòng, counter phân tán có thể không phù hợp làm nguồn dữ liệu có thẩm quyền.

## 11. Partition trong database và data lake

Partitioning được triển khai khác nhau theo engine:

- **Table partitioning:** một bảng logic gồm nhiều partition vật lý/logical theo range/list/hash.
- **Sharding:** phân dữ liệu qua nhiều database node hoặc cluster; ứng dụng/router cần xác định shard.
- **Partition key trong NoSQL:** định tuyến bản ghi tới partition hoặc replica set theo semantics của dịch vụ.
- **Data lake partitioning:** chia file/dataset theo cột như date, region hoặc event_type để giảm lượng file/data phải quét.

### 11.1. Partition pruning

Nếu bảng partition theo occurred_at, truy vấn có điều kiện thời gian có thể chỉ đọc partition liên quan:

~~~sql
SELECT tenant_id, COUNT(*)
FROM booking_events
WHERE occurred_at >= TIMESTAMPTZ '2026-12-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+00'
GROUP BY tenant_id;
~~~

Query planner có thể loại partition ngoài khoảng nếu biểu thức và schema hỗ trợ pruning. Nếu ứng dụng bọc cột trong hàm hoặc cast khiến planner không suy ra range, pruning có thể kém hiệu quả. Kiểm tra execution plan trên engine thật thay vì dựa vào SQL nhìn có vẻ đúng.

### 11.2. Partition key và index là hai khái niệm khác nhau

Partition key quyết định cách chia dữ liệu; index giúp định vị hàng trong phạm vi dữ liệu hoặc cấu trúc index. Có partition không có nghĩa mọi query đều nhanh. Có index không có nghĩa dữ liệu được phân phối đều giữa node.

Ví dụ bảng theo tháng vẫn có thể cần index tenant_id và occurred_at bên trong mỗi partition để truy vấn lịch sử tenant hiệu quả. Nhưng index cũng tăng storage, write amplification và thời gian maintenance.

### 11.3. Chọn độ hạt thời gian

| Độ hạt | Lợi ích | Rủi ro |
| --- | --- | --- |
| Theo ngày | Retention và truy vấn ngày chi tiết | Nhiều partition nếu giữ nhiều năm |
| Theo tháng | Ít partition, phù hợp nhiều báo cáo tháng | Partition hiện tại lớn nếu tải lớn |
| Theo quý/năm | Quản trị metadata đơn giản | Quét và xóa dữ liệu chi tiết khó hơn |
| Theo tenant + tháng | Truy vấn/retention theo tenant rõ | Số partition tăng theo tenant × kỳ |

Ước lượng số partition tồn tại đồng thời, dung lượng mỗi partition, phân bố dữ liệu, số index và chi phí maintenance. Với dữ liệu event lớn, có thể dùng data lake partition theo ngày và tenant bucket thay vì tạo partition vật lý cho từng tenant.

## 12. Di chuyển và tiến hóa key/partition

Namespace và key thường tồn tại lâu hơn phiên bản ứng dụng. Đổi cấu trúc key hoặc partition có thể ảnh hưởng URL, database reference, event, cache, backup, analytics, job và công cụ vận hành.

### 12.1. Expand–migrate–contract

1. **Thiết kế layout mới:** định nghĩa key format, version, access pattern, quyền và lifecycle.
2. **Mở rộng catalog:** thêm trường objectKeyV2 hoặc mapping cũ → mới; không xóa tham chiếu cũ.
3. **Dual-read:** ứng dụng đọc key mới trước, fallback key cũ trong giai đoạn migration có kiểm soát.
4. **Backfill/copy:** di chuyển object/bản ghi theo batch có checkpoint, checksum và retry idempotent.
5. **Dual-write hoặc routing:** chỉ áp dụng nếu semantics và đối soát rõ; tránh hai nguồn sự thật cạnh tranh.
6. **Verify:** đối chiếu số lượng, checksum, metadata, quyền, retention và khả năng đọc.
7. **Cutover:** chuyển consumer/producer sang key hoặc partition mới theo từng nhóm.
8. **Contract:** chỉ ngừng đường đọc cũ sau khi không còn tham chiếu, consumer, backup hay job cần đến.

### 12.2. Mapping catalog cho object key

| objectId | keyV1 | keyV2 | migrationStatus |
| --- | --- | --- | --- |
| obj-01J8 | media/tnt-8f2a/2026/12/obj-01J8.jpg | property-media/7f/tnt-8f2a/2026/12/obj-01J8/original.jpg | verified |
| obj-01J9 | media/tnt-8f2a/2026/12/obj-01J9.jpg | property-media/3a/tnt-8f2a/2026/12/obj-01J9/original.jpg | copied |

Catalog cho phép ứng dụng dùng objectId ổn định trong khi vật lý object key thay đổi. Key cũ chỉ được xóa khi chính sách retention và mọi tham chiếu đã được xác minh.

### 12.3. Thay partition key hoặc shard count

Thay hash bucket count từ 16 lên 32 có thể làm ánh xạ cũ và mới khác nhau. Không đơn giản đổi công thức rồi để ứng dụng tự đọc; cần xác định dữ liệu hiện tại ở shard nào, xây mapping/version partition scheme, hỗ trợ dual-read trong thời gian chuyển đổi, di chuyển theo batch, kiểm tra checksum/count và xử lý ghi đồng thời, rồi cutover có rollback.

Nếu sharding bằng consistent hashing hoặc virtual nodes, thay đổi node membership vẫn cần kiểm tra tỷ lệ key phải di chuyển và khả năng rebalance.

## 13. Lifecycle, retention, archive và deletion

Namespace và partition tốt có thể làm quản trị vòng đời dễ hơn. Dữ liệu theo tháng có thể archive/xóa theo kỳ; object theo tenant giúp kiểm tra dữ liệu của tenant khi hợp đồng kết thúc. Nhưng cần phối hợp với metadata catalog và bản sao.

| Chính sách | Câu hỏi cần trả lời |
| --- | --- |
| Retention | Dữ liệu phải giữ bao lâu theo nghiệp vụ/hợp đồng/pháp luật? |
| Lifecycle tiering | Khi nào chuyển sang lớp lưu trữ rẻ hơn; tần suất truy cập có cho phép không? |
| Archive | Có yêu cầu khôi phục trong bao lâu; ai được yêu cầu restore? |
| Deletion | Xóa object, row, index, cache, replica, archive và bản sao như thế nào? |
| Legal hold | Dữ liệu nào không được xóa trong khi có yêu cầu giữ pháp lý? |
| Backup | Backup giữ riêng bao lâu, có immutable protection và test restore không? |

**Xóa namespace không nhất thiết đồng nghĩa xóa hết dữ liệu.** Có thể còn object version, replica, backup, archive, cache, data lake copy hoặc bản export. Quy trình xóa cần xác định phạm vi, bằng chứng và khoảng thời gian hoàn tất.

Với database partition theo thời gian, drop partition có thể nhanh hơn xóa từng row, nhưng chỉ an toàn khi toàn bộ partition thực sự hết retention và không có legal hold. Với object storage, xóa prefix có thể phải liệt kê/xóa nhiều key và xử lý versioning; phải dùng workflow có checkpoint.

## 14. Bảo mật, mã hóa và audit theo namespace

Namespace giúp tổ chức policy nhưng cần kết hợp:

- IAM/role theo bucket, prefix, table, schema hoặc partition nếu dịch vụ hỗ trợ.
- Encryption in transit và at rest; quản lý key, rotation và quyền decrypt.
- Audit access, object lifecycle, schema changes, policy changes và thao tác xóa.
- Data classification và minimization; không nhét PII vào key hoặc partition label.
- Tenant context xác thực xuyên API, worker, event và batch processing.
- Private endpoint/network policy khi có yêu cầu bảo vệ đường truy cập.

Tránh sử dụng tên prefix như cơ chế xác thực. Nếu user biết key của tenant khác, API vẫn phải kiểm tra quyền trên object metadata và tenant ownership trước khi cấp URL tải xuống.

### 14.1. URL ký sẵn và object key

Pre-signed URL thường trao quyền truy cập tạm thời vào một object cụ thể theo điều kiện ký. Cần bảo vệ URL như một bí mật trong thời hạn hiệu lực:

- TTL ngắn theo mục đích.
- Không ghi đầy đủ URL vào log hoặc analytics.
- Giới hạn object, HTTP method và content constraints nếu dịch vụ hỗ trợ.
- Không chia sẻ URL giữa tenant hoặc dùng làm ID lâu dài.
- Sau upload, xác minh object và cập nhật catalog theo quyền server.

## 15. Quan sát, capacity và kiểm tra sức khỏe partition

Theo dõi tổng dung lượng hệ thống chưa đủ. Một partition nóng có thể gây latency cao trong khi utilization trung bình vẫn thấp.

| Nhóm metric | Chỉ số nên quan sát |
| --- | --- |
| Namespace | Số object/row, dung lượng, tăng trưởng, owner, tỷ lệ resource không gắn nhãn |
| Key distribution | Tần suất theo prefix/partition key, top hot keys, key cardinality và skew |
| Storage | Read/write request, latency p95/p99, throughput, throttling, error, object size distribution |
| Database | Partition size, index size, pruning effectiveness, lock, vacuum/maintenance, replication lag |
| NoSQL/sharding | Read/write capacity per partition, throttling, hot partition, rebalance movement |
| Data lake | File count/size, small-file problem, bytes scanned, partition pruning và query cost |
| Lifecycle | Số object/row tới hạn, backlog archive/delete, restore time |
| Security | Access denied, cross-tenant attempt, policy change, unusual download/export |
| Cost | Storage tier, request/list/egress, index/replica, backup và migration cost |

### 15.1. Kiểm tra phân bố trước khi scale

Khi một truy vấn chậm, hãy trả lời: nó đọc bao nhiêu partition và byte/row; có partition/key nào nóng hơn đáng kể không; partition pruning hoặc index có được dùng theo execution plan không; request bị giới hạn bởi storage IOPS, database CPU, lock, network hay serialization; thay đổi key có làm mất khả năng query theo tenant/time không; và scale-out cần di chuyển bao nhiêu dữ liệu, mất bao lâu?

Không chữa hot partition bằng cách tăng số node một cách mù quáng; nếu mọi request vẫn định tuyến tới cùng key, năng lực mới có thể không giúp được.

## 16. Bài thực hành: thiết kế storage layout cho nền tảng đặt chỗ

**Bối cảnh:** hệ thống có 5.000 tenant. Ba nhóm dữ liệu chính: ảnh phòng/property có 30 triệu object, đọc nhiều và ghi theo đợt; booking events có 2 tỷ event, truy vấn theo tenant và khoảng thời gian, retention 7 năm; invoice là dữ liệu nhạy cảm cần phân quyền theo tenant và lưu theo quy định.

### Nhiệm vụ

1. Xây namespace layout cho production/non-production và các domain media, booking, billing, audit.
2. Đề xuất object key cho ảnh và hóa đơn; giải thích ID, tenant reference, time bucket, variant và cách tránh PII.
3. Liệt kê access pattern cho booking events; chọn range/hash/composite partitioning và nêu vì sao.
4. Phân tích tenant lớn có nguy cơ hot partition; đề xuất shard riêng, salting, hash bucket hoặc quota.
5. Thiết kế metadata catalog cho object key để hỗ trợ list theo tenant/time/type mà không quét bucket.
6. Xây dựng policy phân quyền namespace, IAM, tenant validation, encryption, retention và URL ký sẵn.
7. Lập kế hoạch đổi key format từ v1 sang v2, có dual-read, backfill, checksum, cutover, rollback và xóa key cũ.
8. Xác định metric cho hot key, partition skew, request latency, lifecycle backlog và chi phí.
9. Viết ADR ghi lựa chọn, phương án loại bỏ, rủi ro và điều kiện cần xem xét lại.

### Mẫu thiết kế để nộp

| Thành phần | Namespace | Key/partition strategy | Access pattern | Kiểm soát và lifecycle |
| --- | --- | --- | --- | --- |
| Property media | property-media | Tenant ref + object ID + variant; hash bucket nếu cần | List theo property, đọc theo object ID | Private, scan upload, tier theo tuổi |
| Booking event | booking-events | Time range kết hợp tenant hash hoặc shard strategy | Tenant + thời gian, event theo booking | Retention 7 năm, index/catalog |
| Invoice | billing-invoices | Tenant ref + năm/tháng + opaque ID | Tra cứu theo invoice/tenant | Mã hóa, audit, quyền chặt, legal hold |

### Tiêu chí hoàn thành

- Namespace phân biệt được owner, môi trường, domain và phân loại dữ liệu.
- Object key ổn định, duy nhất, không tiết lộ PII và hỗ trợ access pattern.
- Partition key có lý do dựa trên cardinality, skew, throughput và query.
- Có đánh giá hot tenant/noisy neighbor và phương án xử lý.
- Catalog/index có cơ chế đồng bộ và phục hồi khi object upload/delete lỗi.
- Migration không làm mất tham chiếu hoặc xóa bản cũ quá sớm.
- Retention, archive, backup và deletion có bằng chứng và owner.
- Chi phí request, storage, index, replica, egress và vận hành được tính.

## 17. Checklist Well-Architected trước khi chốt storage layout

- [ ] Đã xác định lớp namespace (bucket/schema/table/tenant/partition) và semantics thực của công nghệ.
- [ ] Namespace có owner, environment, classification, region, retention và cost center.
- [ ] Ranh giới bảo mật không chỉ dựa trên prefix hoặc tên; IAM và tenant validation được kiểm chứng.
- [ ] Object key ổn định, duy nhất, không chứa PII/secret và có quy tắc encoding/length.
- [ ] Đã phân tích access pattern trước khi chọn range/hash/list/composite partition.
- [ ] Đã đánh giá cardinality, skew, hot key, hot partition và noisy neighbor.
- [ ] Có catalog/index khi cần truy vấn theo metadata thay vì list/scan toàn bộ object.
- [ ] Đã kiểm tra partition pruning, query plan, index cost và khả năng mở rộng/reshard.
- [ ] Storage topology và backup/replica không tạo cùng một miền lỗi chưa được chấp nhận.
- [ ] Lifecycle/retention/deletion bao gồm version, archive, replica, backup và cache.
- [ ] Migration có mapping, dual-read/cutover, checksum, checkpoint, rollback và tiêu chí kết thúc.
- [ ] URL ký sẵn, encryption, key management, audit và quyền replay/restore được kiểm soát.
- [ ] Metric theo partition/key và chi phí đủ để phát hiện bất thường trước khi ảnh hưởng người dùng.
- [ ] ADR nêu rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** namespace xác định phạm vi tổ chức và quản trị dữ liệu; object key định danh đối tượng theo một quy ước bền vững; partitioning quyết định dữ liệu được chia và phân phối ra sao. Thiết kế tốt phải bắt đầu từ **access pattern, ranh giới tin cậy, tốc độ tăng và vòng đời dữ liệu**, rồi được kiểm chứng bằng phân bố tải, quyền truy cập, khả năng di chuyển, khôi phục và chi phí thực tế.
