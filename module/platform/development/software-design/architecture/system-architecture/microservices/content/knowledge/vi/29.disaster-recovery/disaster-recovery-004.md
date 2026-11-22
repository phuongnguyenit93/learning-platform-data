# Phục hồi cơ sở dữ liệu, broker và cấu hình dịch vụ

Trong kiến trúc microservices, phục hồi thảm họa không kết thúc ở việc khởi động lại các container hay đưa một cơ sở dữ liệu từ bản backup về trạng thái hoạt động. Một hành trình nghiệp vụ có thể dựa trên **database**, **message broker**, **schema registry**, **cấu hình**, **secret**, **danh tính workload**, **artifact của ứng dụng** và nhiều hệ thống bên ngoài. Nếu chỉ khôi phục từng thành phần độc lập, các thành phần có thể hoạt động nhưng **không cùng nói về một trạng thái nghiệp vụ**: đơn đã ghi trong database nhưng sự kiện không còn trong broker; broker phát lại message đã xử lý và gây trừ kho hai lần; service được phục hồi với cấu hình hoặc khóa mã hóa không còn tương thích dữ liệu.

Bài học này trình bày cách thiết kế và diễn tập quy trình phục hồi đồng bộ **cơ sở dữ liệu, broker và cấu hình dịch vụ**. Mục tiêu không chỉ là các thành phần “Up”, mà còn là bảo đảm **RPO/RTO được hiểu đúng**, dữ liệu không bị mất hoặc nhân đôi ngoài ngưỡng cho phép, những bất biến nghiệp vụ còn đúng và hệ thống có thể nhận traffic trở lại một cách có kiểm soát.

Các ví dụ dùng hệ thống thương mại điện tử gồm Order, Payment, Inventory và Notification; database quan hệ kiểu PostgreSQL, broker dạng log phân vùng kiểu Kafka và cấu hình được quản lý qua GitOps/secret manager. Ví dụ là mô hình học tập: lựa chọn công cụ, câu lệnh backup, lưu trữ và quy trình failover thật phải phù hợp với phiên bản phần mềm, managed service, topology và quy định tổ chức.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt **backup**, **replication**, **high availability**, **failover**, **disaster recovery** và **business continuity**.
- Đặt và đo **Recovery Point Objective (RPO)**, **Recovery Time Objective (RTO)** cho cả một hành trình nghiệp vụ, không chỉ cho từng máy chủ.
- Thiết kế backup, restore và point-in-time recovery (PITR) cho database, xác minh dữ liệu và khả năng ứng dụng chạy trên dữ liệu đã phục hồi.
- Xác định các thành phần phải bảo toàn khi khôi phục broker: dữ liệu topic, partition, offset, metadata, ACL, schema/serializer, consumer group và trạng thái xử lý.
- Phục hồi cấu hình, secret reference, khóa mã hóa, workload identity và phiên bản image tương thích với trạng thái dữ liệu.
- Lập thứ tự khôi phục theo dependency graph, kiểm soát **split-brain**, replay/duplicate và dữ liệu được ghi sau thời điểm restore.
- Thiết kế reconciliation, idempotency, transactional outbox/inbox và quyết định khi nào có thể mở traffic.
- Viết runbook và tổ chức game day thực sự đo được thời gian phục hồi và mức mất dữ liệu.

## 2. Trước tiên: xác định điều gì cần được phục hồi

Một ứng dụng nhiều dịch vụ có thể có kiến trúc:

~~~text
                 Người dùng / API Gateway
                          |
                          v
                   Checkout Service
                     /          \
                    v            v
              Order Service   Payment Service
                    |            |
                    v            v
                Order DB     Payment DB
                    |            |
                 Outbox        Outbox
                    \            /
                     v          v
                  Message Broker
                  /            \
                 v              v
        Inventory Consumer   Notification Consumer
                 |              |
                 v              v
            Inventory DB    Delivery ledger

Những phần phụ trợ:
  Container registry, deployment manifests,
  config repository, secret manager, KMS,
  workload identities, DNS, certificates,
  schema registry, monitoring và external providers
~~~

Giả sử hạ tầng primary region không còn khả dụng. Khôi phục lại Order DB thành công **không đủ** nếu:

- Payment DB có dữ liệu từ thời điểm muộn hơn và hai bên bất đồng về trạng thái thanh toán.
- Topic `OrderCreated` bị mất, Inventory không nhận lệnh reserve.
- Offset của consumer được khôi phục muộn hơn dữ liệu nghiệp vụ, khiến message chưa xử lý bị bỏ qua.
- Secret manager bị thiếu khóa giải mã giá trị trong DB hoặc bị reset policy truy cập.
- Deployment khởi động nhầm image mới chưa tương thích với schema database đã khôi phục.
- DNS vẫn trỏ tới primary cũ, gây hai khu vực nhận lệnh ghi cùng lúc.

**Đối tượng khôi phục thực sự là khả năng thực hiện hành trình nghiệp vụ với dữ liệu nhất quán**, không phải số lượng pod hoặc cluster đang hoạt động.

## 3. Phân biệt backup, replication, HA và DR

| Khái niệm | Giải quyết chủ yếu | Không tự bảo đảm |
|---|---|---|
| Backup | Có bản sao dữ liệu để khôi phục sau mất/xóa/hỏng | Khả năng phục vụ liên tục hoặc RTO thấp |
| Point-in-time recovery | Khôi phục database về một thời điểm được hỗ trợ | Các hệ thống khác cũng ở cùng trạng thái nghiệp vụ |
| Replication | Duy trì bản sao tương đối gần dữ liệu gốc | Bảo vệ khỏi xóa nhầm, logical corruption hay ransomware nếu lỗi lan sang replica |
| High availability | Giảm downtime khi một instance/node lỗi | Vượt qua lỗi toàn region hoặc mất nhiều lớp phụ thuộc |
| Failover | Chuyển workload sang nơi còn hoạt động | Tính đúng đắn khi có hai primary đồng thời |
| Disaster recovery | Phục hồi dịch vụ và dữ liệu sau sự cố lớn | Tự động bảo đảm mọi dữ liệu ứng dụng đúng nếu không diễn tập |
| Business continuity | Duy trì hoạt động kinh doanh theo phương án đã chọn | Có thể yêu cầu quy trình thủ công, không chỉ hệ thống IT |

**Replication không phải backup.** Nếu một thao tác `DELETE` sai bị replicate ngay, bản sao cũng có thể mất dữ liệu. **Backup không phải DR đã kiểm chứng** nếu không có khả năng restore và chạy ứng dụng trên dữ liệu đó.

Tương tự, có ba replica của Kafka không đồng nghĩa topic còn dữ liệu sau việc xóa nhầm, retention quá ngắn hoặc cluster metadata bị phá đồng loạt. Phải xác định failure domain và mục tiêu phục hồi riêng.

## 4. Phạm vi sự cố và failure domain

Một runbook tốt phân biệt các cấp sự cố:

1. **Lỗi process/pod:** ứng dụng crash hoặc health probe sai; thường do orchestration tự xử lý.
2. **Lỗi node/zone:** một nhóm host mất; thường cần replication/failover trong region.
3. **Lỗi service dependency:** database primary hoặc broker cluster bị lỗi; cần cơ chế chuyển vai trò, kiểm tra đồng bộ.
4. **Lỗi toàn region:** network, storage, control plane hoặc nhiều dependency cùng mất.
5. **Logical corruption:** bug ghi dữ liệu sai, deploy migration lỗi, dữ liệu bị xóa nhầm; replica có thể đã nhận lỗi.
6. **Security incident:** ransomware, credential compromise, unauthorized config change; bản backup hoặc bản phục hồi có thể bị nhiễm.
7. **Mất control plane:** Git repository, secret manager, KMS, artifact registry hoặc DNS không hoạt động; data plane có thể còn chạy một thời gian.

Mỗi cấp đòi một cách phục hồi khác nhau. Không nên kích hoạt toàn bộ DR sang secondary region chỉ vì một pod restart. Ngược lại, khi một regional dependency không còn khả dụng, chỉ scale thêm pod ở primary có thể không có ích.

### Câu hỏi ở giai đoạn đánh giá

- Sự cố có còn đang diễn ra và có khả năng lan sang nơi khôi phục không?
- Vùng nào đang giữ bản dữ liệu **được xác định là có thẩm quyền**?
- Có rủi ro hai hệ thống cùng nhận ghi không?
- Thời điểm nào được xem là “last known good”?
- Các bản sao dữ liệu/backup có chứng cứ kiểm tra toàn vẹn và quyền truy cập không?
- Khả năng phục hồi tự động có đáp ứng RTO, hay phải thực hiện điều tra logical corruption trước?

## 5. Định nghĩa RPO, RTO và mục tiêu nghiệp vụ

**RPO (Recovery Point Objective)** là lượng mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn dưới dạng khoảng thời gian giữa điểm dữ liệu đã phục hồi và thời điểm xảy ra sự cố. RPO 5 phút là **mục tiêu**, không phải cam kết backup 5 phút một lần tự động làm cho mọi database và broker đều mất tối đa 5 phút.

**RTO (Recovery Time Objective)** là thời gian tối đa đặt mục tiêu để chức năng được phục hồi đến mức đã định sau khi gián đoạn. RTO phải gắn với tiêu chí “dịch vụ phục hồi” cụ thể, không dừng ở việc database process đã mở cổng TCP.

Ngoài ra có thể xem **Maximum Tolerable Period of Disruption (MTPD/MAO)** trong phân tích liên tục kinh doanh: khoảng gián đoạn dài nhất trước khi hậu quả không thể chấp nhận; RTO cần nằm trong ranh giới kinh doanh cho phép.

Ví dụ bảng mục tiêu minh họa:

| Năng lực | RPO mục tiêu | RTO mục tiêu | Điều kiện xem là phục hồi |
|---|---|---|---|
| Checkout/Order | <= 5 phút | <= 45 phút | Tạo đơn mới hợp lệ, đơn cũ không nhân đôi |
| Payment ledger | Gần 0 theo mức cam kết đã phân tích | <= 60 phút | Đối soát payment attempts và không charge trùng |
| Catalog | <= 30 phút | <= 30 phút | Đọc sản phẩm/giá đúng ngưỡng freshness |
| Notification | <= 30 phút | <= 120 phút | Backlog gửi được xử lý, không mất event |
| Analytics | <= 4 giờ | <= 8 giờ | Pipeline xử lý lại từ nguồn được giữ |
| Cấu hình/secret | Phục hồi được phiên bản đã phê duyệt | Trước khi mở service | Identity, secrets và policy có hiệu lực đúng |

Tất cả con số chỉ là bài tập thiết kế. Payment có thể yêu cầu invariant nghiêm ngặt và quy trình reconciliation đặc biệt, không được diễn giải “RPO 0” như lời hứa không mất dữ liệu nếu topology chưa chứng minh được điều đó.

### RPO và RTO của chuỗi phụ thuộc

Nếu Order khôi phục trong 15 phút nhưng Payment và broker cần thêm 50 phút, **checkout RTO không thể được suy ra bằng 15 phút**. Cần xét critical path và các bước kiểm tra end-to-end.

Tương tự, nếu Order DB phục hồi tại 10:00, Payment DB tại 10:08 và broker tại 09:56, **RPO của hành trình** không chỉ bằng RPO tốt nhất trong ba thành phần. Phải có chiến lược đồng bộ, replay và đối soát để đưa các thành phần tới một trạng thái nghiệp vụ chấp nhận được.

## 6. Inventory tài sản và dependency graph để phục hồi

Khi DR bắt đầu, nhóm phải biết chính xác những gì cần dựng lại. Một danh sách tài sản:

| Thành phần | Dữ liệu/metadata quan trọng | Cơ chế bảo vệ |
|---|---|---|
| Order DB | Tables, indexes, sequences, WAL, roles, migrations | Backup + WAL/PITR + restore test |
| Payment DB | Ledger, payment attempts, idempotency keys | Backup/PITR + reconciliation với provider |
| Inventory DB | Reservation, available stock, allocation | Backup + invariant checking |
| Message broker | Topic data, partitions, offsets, configs, ACL | Replication + backup/replication phù hợp |
| Schema registry | Schema IDs/versions/compatibility settings | Backup/export metadata có kiểm soát |
| Secret manager/KMS | Secrets, phiên bản, key references, policies | Khả năng khôi phục và quyền truy cập độc lập |
| Config source | Deployment manifests, feature flags, runtime config | Git/versioned config + protected backup |
| Artifact registry | Image/JAR digest, signatures, SBOM | Immutable artifact + multi-region/redundant storage |
| DNS/network | Endpoint, TLS, load balancer, private routes | IaC/runbook failover có kiểm soát |
| Observability | SLO dashboard, log/trace, alert rules | Telemetry phục hồi sớm để giám sát recovery |
| External providers | Payment status, email delivery status | API đối soát, operation id và lịch sử request |

Dependency graph không nhất thiết là một chuỗi tuyến tính. Có thể phục hồi nhiều thành phần song song, nhưng phải biết **thành phần nào cần có trước khi cho phép ghi mới**.

## 7. Tài liệu phục hồi không thể chỉ là “run backup mỗi đêm”

Một kế hoạch đầy đủ cần thông tin:

- **Owner và người có quyền ra quyết định** cho từng dữ liệu, service và bước failover.
- Bản backup được tạo ở đâu, ở chế độ nào, retention bao lâu, mã hóa bằng key nào.
- Nhận diện backup, checksum, timestamp, WAL/archive hoặc log sequence và điểm khôi phục hỗ trợ.
- Vị trí và quyền khôi phục ở region/tenant/account tách biệt.
- Quy trình tạo môi trường sạch và khôi phục IAM, network, KMS, DNS.
- Mapping giữa database schema, application image version và message schema.
- Giới hạn dữ liệu có thể bị mất và cách xác minh tính đúng đắn nghiệp vụ.
- Quy trình fencing primary cũ và mở traffic mới.
- Cách rollback hoặc dừng nếu phát hiện restore không đáng tin.
- Danh sách kiểm tra sau khôi phục và kênh liên lạc khi ứng cứu.

Nếu tài liệu khôi phục trỏ đến một registry hoặc secret manager duy nhất vốn cũng nằm trong region đã mất, đó là **phụ thuộc vòng**. Cần có đường bootstrap độc lập đủ để dựng lại hệ thống.

## 8. Cơ sở dữ liệu: chiến lược bảo vệ và khả năng PITR

Một database quan hệ thường hỗ trợ vài cơ chế:

1. **Logical backup**: export schema/data theo định dạng công cụ, thuận tiện cho migration và kiểm tra ở một số trường hợp.
2. **Physical/base backup**: chụp tập dữ liệu vật lý nhất quán theo công cụ database.
3. **Transaction log archival**: lưu WAL/binlog/redo hoặc cơ chế tương đương để phục hồi tới một mốc.
4. **Replication/failover**: duy trì standby/read replica cho lỗi hạ tầng nhanh.
5. **Snapshot của hệ thống lưu trữ**: chỉ an toàn khi được phối hợp theo quy tắc consistency của database hoặc cung cấp consistency phù hợp.

Không có cơ chế nào phù hợp tất cả. Với PostgreSQL, **PITR** thường dựa trên base backup và WAL archive liên tục. Nếu chỉ giữ base backup mà mất chuỗi WAL cần thiết, không thể phục hồi tùy ý đến thời điểm gần sự cố.

### 8.1. Backup phải đầy đủ chuỗi phụ thuộc

Ví dụ:

~~~text
T0  Base backup hoàn tất
T1  WAL segment được archive
T2  WAL segment tiếp theo được archive
T3  Bug ghi dữ liệu sai
T4  Thảm họa hoặc phát hiện lỗi

Mục tiêu PITR: phục hồi về trước T3 nếu có đủ WAL,
sau đó đánh giá tác động tới các sự kiện đã phát ra.
~~~

Điểm restore cần được xác định bằng cơ chế và timestamp/log sequence mà database hỗ trợ; không chỉ chọn một giờ trên dashboard. Với logical corruption, việc “khôi phục càng mới càng tốt” có thể đưa dữ liệu sai trở lại.

### 8.2. Thiết kế lịch backup

Tần suất backup phụ thuộc lượng dữ liệu, tốc độ ghi, độ dài log được giữ, băng thông, chi phí và RPO. Ví dụ tạo base backup mỗi ngày kèm archive WAL liên tục có thể cho PITR giữa hai bản base backup nếu chuỗi WAL hoàn chỉnh và chính sách công cụ đúng.

Cần xác minh:

- Backup job **đã hoàn tất**, không chỉ được schedule.
- Backup có thể giải mã và đọc, metadata/công cụ tương thích.
- WAL/archive lag không vượt ngưỡng rủi ro.
- Bản backup được lưu ở failure domain phù hợp, không bị xóa đồng thời với primary.
- Retention cho phép quay về **trước** thời điểm phát hiện corruption, không chỉ trước outage.
- Có xác minh phục hồi định kỳ vào môi trường cô lập.

## 9. Tính toàn vẹn và bảo mật của backup

Một bản backup chứa dữ liệu khách hàng và có thể là mục tiêu tấn công. Nên có:

- Mã hóa khi lưu/truyền, tách quyền đọc backup khỏi quyền quản trị production khi thích hợp.
- Snapshot hoặc backup immutable/WORM/object lock trong thời hạn được chọn để hạn chế xóa/sửa trái phép.
- IAM theo quyền tối thiểu, audit mọi thao tác restore, download, delete và rotate.
- Key management và cơ chế **khôi phục khóa mã hóa** khi primary KMS không hoạt động.
- Kiểm tra checksum/manifest và khả năng đọc theo công cụ.
- Bản sao ở region hoặc account độc lập theo threat model.
- Restore drill trên dữ liệu đã bảo vệ quyền riêng tư và quyền truy cập.
- Quy trình xử lý legal retention, xóa dữ liệu theo chính sách và dữ liệu nhạy cảm.

**Mã hóa backup nhưng làm mất key giải mã không tạo ra khả năng phục hồi.** Kế hoạch DR phải xác định ai có quyền dùng khóa, cách bootstrap và khi nào có thể khôi phục một key hoặc key material theo công nghệ được dùng. Không sao chép secret plaintext vào tài liệu DR như phương án dự phòng.

## 10. Quy trình database restore an toàn

Một quy trình khái niệm:

~~~text
(1) Chặn ghi/fence primary lỗi
(2) Xác định điểm dữ liệu tin cậy cần khôi phục
(3) Dựng database restore target cô lập
(4) Nạp base backup hoặc snapshot hợp lệ
(5) Áp transaction logs tới mốc đã chọn
(6) Kiểm tra consistency, schema, indexes, roles
(7) Chạy business invariants và đối soát
(8) Chọn image/config tương thích
(9) Mở read-only kiểm thử, rồi mới mở writes
(10) Ghi nhận recovery point và bắt đầu theo dõi RPO/RTO
~~~

Đây không phải danh sách câu lệnh SQL có thể áp dụng cho mọi database. Với managed database, thao tác restore/PITR thường thông qua API của nhà cung cấp. Với database tự quản lý, phải dùng tài liệu tương ứng phiên bản DB/backup tool và tuân thủ isolation, ownership, permission.

### 10.1. Không restore đè production khi chưa xác định điểm tốt

Nếu nghi lỗi ứng dụng ghi sai dữ liệu từ 09:30, restore một bản lúc 10:05 có thể đưa lại corruption. Restore vào môi trường cô lập, kiểm tra thời điểm và phạm vi ảnh hưởng, chọn recovery point phù hợp, rồi mới quyết định cutover.

Nếu dữ liệu sai chỉ ảnh hưởng vài bản ghi, có thể ưu tiên **logical repair/reconciliation** thay vì quay lùi toàn database và làm mất nhiều giao dịch hợp lệ. Quyết định dựa trên phạm vi corruption và mục tiêu RPO.

### 10.2. Khôi phục schema và vai trò

Database không chỉ có các bảng:

- Schema migrations, indexes, constraints, extensions, stored procedures.
- Roles/privileges, row-level security policies, database settings.
- Sequences/identity values sau restore để tránh xung đột ID.
- Connection endpoint, TLS CA/certificates, server parameters.
- Collation/encoding/timezone liên quan hành vi ứng dụng.
- Version tương thích của engine và extension.

Một database được restore với dữ liệu nhưng thiếu extension hoặc role có thể khiến ứng dụng khởi động lỗi hoặc bỏ qua kiểm soát truy cập. Không cấp quyền admin cho mọi service chỉ để “cho chạy lại nhanh”.

## 11. Khôi phục nhiều database: không có một transaction toàn hệ thống

Microservices thường sở hữu database riêng. Giả sử:

~~~text
T0  Order O-42 tạo -> Order DB commit
T1  OrderCreated event phát
T2  Payment xử lý -> Provider charge
T3  Payment DB lưu PAID
T4  PaymentCompleted event phát
T5  Order DB cập nhật trạng thái PAID
~~~

Nếu Order DB được restore tới T1, Payment DB tới T3 và broker tới T2, trạng thái có thể là:

~~~text
Order: PENDING
Payment: PAID
Broker: thiếu PaymentCompleted hoặc offset không rõ
Provider: đã charge
~~~

Không thể chỉ cho Order retry payment mới với idempotency key khác; điều đó có thể charge trùng. Cần xác định **nguồn có thẩm quyền** cho từng loại sự thật và reconciliation theo business ID.

### Chiến lược xử lý

- Payment Provider/ledger là nguồn kiểm tra trạng thái charge thực.
- Order DB là nguồn đơn/hợp đồng bán hàng trong phạm vi owner.
- Transactional outbox/inbox giúp phát lại sự kiện an toàn.
- Idempotency key ổn định để cùng operation không tạo tác động hai lần.
- Reconciliation job so sánh Order/Payment/Inventory với provider, phát hiện trạng thái cần sửa.
- Một số nghiệp vụ có thể tạm ở trạng thái `PENDING_RECONCILIATION` thay vì trả kết luận sai.

**Sự nhất quán sau DR cần được chứng minh bằng invariant**, không bằng việc mọi database được chọn cùng một timestamp trên các máy có đồng hồ khác nhau.

## 12. Transactional outbox giúp phục hồi sự kiện đã commit

Vấn đề phổ biến:

~~~text
Order DB COMMIT thành công
       |
Process crash
       |
Event chưa được publish -> service khác không biết Order mới
~~~

Nếu business update và outbox record được ghi **trong cùng database transaction**, một publisher độc lập có thể đọc lại outbox sau restore và publish:

~~~text
BEGIN TRANSACTION
  INSERT/UPDATE business row
  INSERT INTO outbox(event_id, aggregate_id, payload, status)
COMMIT
~~~

Sau sự cố:

- Nếu transaction chưa commit, cả business row và outbox row đều không được xác nhận.
- Nếu transaction đã commit, outbox record còn trong cùng recovery point của database.
- Publisher có thể gửi lại event chưa xác nhận; consumer phải deduplicate.
- Nếu restore mất các transaction sau recovery point, cần đánh giá những event đã phát trước DR nhưng business row không còn trong bản restore.

**Outbox không xóa được bài toán lệch timeline** nếu broker còn event mới hơn database vừa được rollback. Cần đối soát nguồn dữ liệu và kế hoạch xử lý message đến sau recovery point.

## 13. Inbox/idempotency giúp replay không gây side effect trùng

Khi broker phát lại message sau restore hoặc consumer crash, phải chống xử lý trùng.

Schema minh họa:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction với business update:

~~~text
BEGIN
  INSERT processed_message (consumer_name, event_id)
  Nếu đã tồn tại:
      không chạy business effect lần nữa
  Nếu chưa tồn tại:
      kiểm tra version/business key
      cập nhật database
      ghi outbox tiếp theo nếu cần
COMMIT
ACK broker sau COMMIT
~~~

Nếu business effect là gọi external provider, database transaction không bao phủ provider; cần **idempotency key do provider hiểu**, kết quả tra cứu hoặc reconciliation khi outcome chưa xác định.

Một rủi ro của restore: processed_message ledger có thể bị rollback về **trước** một message đã thực thi side effect. Nếu replay event đó, chỉ dedup bằng ledger mới phục hồi có thể không đủ. Cần kiểm tra business record và external operation key để bảo vệ side effect xuyên recovery boundary.

## 14. Message broker phải khôi phục những gì?

Với broker phân tán kiểu Kafka, không chỉ có “nội dung một topic”. Cần xét:

| Đối tượng | Ý nghĩa | Rủi ro khi mất/sai |
|---|---|---|
| Topic records | Sự kiện/command đã publish | Mất workflow hoặc dữ liệu phân tích |
| Partition count và key mapping | Xác định đường phân phối event | Thay mapping có thể phá ordering theo aggregate |
| Topic configuration | Retention, compaction, cleanup, replication, min ISR | Dữ liệu bị xóa sớm hoặc độ bền thay đổi |
| Consumer group offsets | Vị trí ứng dụng dự kiến tiếp tục đọc | Skip message chưa xử lý hoặc replay quá nhiều |
| Transactional/producer metadata | Liên quan producer fencing và giao dịch trong phạm vi broker | Nguy cơ duplicate, conflict hoặc workflow lẫn lộn |
| ACL và identities | Ai có quyền publish/subscribe/admin | Service lỗi hoặc mở quyền quá rộng |
| Schema registry | Schema IDs/versions/compatibility | Consumer decode lỗi dù record còn |
| Connectors/source/sink state | Offset và trạng thái đồng bộ với nguồn/đích | Duplicate hoặc bỏ sót dữ liệu ở external systems |
| DLQ/retry topics | Sự kiện đang chờ xử lý lại | Mất khả năng khôi phục nghiệp vụ lỗi tạm thời |

Chi tiết metadata và hành vi phục hồi khác nhau theo broker và chế độ triển khai; ví dụ cụ thể phải bám vào tài liệu đúng phiên bản Kafka và kiến trúc metadata quorum/controller. Không nên tự copy thư mục dữ liệu giữa cluster khác identity rồi giả định chạy được.

### Replication nội bộ không phải bảo vệ mọi thảm họa

Một topic có replication factor 3 bảo vệ trước một số lỗi broker/node khi các replicas ở failure domain phù hợp. Nhưng nếu toàn bộ region mất, topic bị xóa bởi quản trị viên, retention xóa dữ liệu hoặc thông tin xác thực bị xâm nhập, các replica cùng cluster có thể không giúp phục hồi dữ liệu đã mất.

Để có DR, có thể cân nhắc cross-region replication, backup/export, durable source log, hoặc khả năng tái phát event từ database outbox. Mỗi phương án có RPO, RTO, chi phí và tính đúng đắn khác nhau.

## 15. Phục hồi broker từ replication/backup không phải “resume offset cũ”

Giả sử group `inventory-consumer` đã xử lý tới offset 5.000 ở primary. Secondary broker chỉ có dữ liệu tới offset tương ứng 4.800 theo chiến lược replication. Nếu copy metadata group hoặc tự set offset mà không đối chiếu trạng thái database, có thể:

- **Skip** 200 message chưa được xử lý tại secondary.
- **Replay** message đã được xử lý tại database.
- **Đọc sai vị trí** vì offset của hai cluster không có cùng quy tắc mapping.
- **Bỏ message sau retention** nếu offset trỏ tới dữ liệu đã bị xóa.
- **Phá thứ tự theo key** nếu partition mapping thay đổi.

Offset là vị trí trong một log cụ thể, **không phải business sequence toàn cục** và không tự tương đương giữa hai cluster.

### 15.1. Chọn vị trí khôi phục theo nguồn có thẩm quyền

Một quy trình:

1. Xác định broker/log đích, topic/partition mapping và replication lag.
2. Xác định trạng thái database đã phục hồi của từng consumer.
3. Chọn điểm replay đủ sớm để không bỏ message cần thiết, trong retention còn sẵn.
4. Đảm bảo consumer có idempotency/inbox và version handling.
5. Dừng outbound side effect nhạy cảm hoặc chuyển sang mode reconciliation nếu chưa chắc outcome.
6. Khởi chạy consumer trong chế độ có kiểm soát, đo lag, duplicate, DLQ và tác động nghiệp vụ.
7. Chỉ chuyển sang xử lý bình thường sau khi xác minh được trạng thái.

Với broker có công cụ chuyển đổi offset hoặc replication metadata, phải kiểm tra cơ chế cụ thể; không mặc định offset số N ở source chính là offset N ở target.

## 16. Broker recovery: ba chiến lược phổ biến

### 16.1. Khôi phục cluster từ backup đúng định dạng

Dùng backup/restore được broker hoặc platform hỗ trợ, cùng các metadata cần thiết; giữ record order, configs, identity và quyền tương ứng. Phù hợp khi backup thực sự có thể restore đúng version/topology. Cần kiểm tra thử trong môi trường tách biệt.

### 16.2. Chuyển sang secondary replicated cluster

Nếu replication liên vùng đã được thiết kế, có thể chuyển producer/consumer sang secondary sau khi đánh giá replication lag và fencing primary. Cần quyết định rõ nguồn nào là primary mới, kiểm tra schema registry, client auth và offset mapping.

**Không khởi động hai producer/cluster cùng nhận business commands từ cùng hệ thống ngoài** khi không có chiến lược xử lý split-brain. Hai primary có thể cùng xử lý đơn hàng hoặc thanh toán.

### 16.3. Tái tạo event từ nguồn bền vững

Nếu broker không còn record, đôi khi có thể rebuild projection từ event store/outbox/business database. Nhưng không phải event nào cũng tái tạo được: lệnh đã gửi tới provider ngoài, external event đến từ đối tác hoặc log chỉ tồn tại ở broker có thể đã mất vĩnh viễn.

Phải phân loại **event tái tạo được** và **event không thể tái tạo** trước khi lấy chiến lược replay làm kế hoạch DR duy nhất.

## 17. Ví dụ cụ thể: OrderCreated và PaymentCompleted bị lệch

Giả sử trước thảm họa:

~~~text
Order DB: O42 = PAID
Payment DB: P42 = CAPTURED
Broker: đã publish PaymentCompleted(E42)
Inventory DB: đã reserve hàng cho O42
Notification DB: email chưa gửi
~~~

Sau DR:

~~~text
Order DB restore: O42 = CREATED
Payment DB restore: P42 = CAPTURED
Broker secondary: chưa thấy E42
Inventory DB: đã reserve
Notification DB: chưa có record
~~~

Nếu coi Order DB là nguồn duy nhất rồi gửi `ChargePayment` mới, hệ thống có thể trừ tiền lần nữa. Nếu chỉ lấy trạng thái Payment DB và bỏ qua Order, người dùng có thể không tìm thấy đơn đã thanh toán.

**Quy trình đề xuất:**

1. Tạm chặn mutation/checkout hoặc đưa trạng thái vào maintenance mode.
2. Dùng `orderId`, `paymentAttemptId`, `providerChargeId` và event IDs để ghép các bản ghi.
3. Hỏi provider/ledger về khoản tiền đã thực hiện, ưu tiên nguồn có thẩm quyền.
4. Chỉnh trạng thái Order bằng nghiệp vụ reconciliation được kiểm soát, tránh update SQL tùy tiện nếu cần domain invariants.
5. Phát lại `PaymentCompleted` có event identity/business key ổn định khi hợp đồng cho phép; consumer chống duplicate.
6. Kiểm tra inventory và notification trước khi mở traffic.
7. Lưu dấu vết khôi phục, số operation được điều chỉnh và các case chưa thể tự quyết.

Trạng thái `PAID` ở một bảng chỉ là bằng chứng của hệ thống đó, không tự chứng minh provider đã capture thành công. Ngược lại, timeout của Order không chứng minh provider chưa charge.

## 18. Cấu hình dịch vụ cũng là một phần của dữ liệu cần phục hồi

Config thường nằm ở nhiều nơi:

- Git repository chứa Kubernetes manifests, Helm values hoặc Kustomize overlays.
- Infrastructure as Code (IaC) cho network, namespace, role và storage.
- Config server, feature-flag service, parameter store hoặc environment variables.
- Secret manager/KMS chứa phiên bản secret, key material hoặc reference.
- Container registry với image digest đã được duyệt.
- Admission policies, certificates, DNS và external endpoints.

Khôi phục **image đúng** nhưng **config sai** có thể nguy hiểm hơn service không khởi động: ứng dụng có thể kết nối tới database production cũ, publish vào broker nhầm hoặc bật tính năng chưa được kiểm thử.

### Bảng ví dụ các thành phần config

| Thành phần | Cần xác minh khi DR |
|---|---|
| Image digest | Binary tương thích schema restored và được phê duyệt |
| DB endpoint | Trỏ tới primary mới, không tới region lỗi |
| Broker bootstrap addresses | Đúng cluster, TLS và producer/consumer ACL |
| Feature flags | Không bật lệnh ghi khi reconciler chưa hoàn tất |
| Retry policy | Không tạo retry storm khi dependency chưa sẵn sàng |
| Secret references | Đúng version/alias và quyền đọc theo service |
| TLS truststore/CA | Tin đúng certificate của endpoint DR |
| Clock/timezone | Phù hợp quy tắc timestamp, token expiry, audit |
| Object storage bucket | Không ghi nhầm dữ liệu DR về bucket lỗi |
| External provider credentials | Sandbox/production được phân biệt rõ |
| DNS/Ingress | Traffic chỉ đi vào vùng đã được kiểm tra |

## 19. GitOps và khôi phục trạng thái đã phê duyệt

Một repository cấu hình có thể chứa:

~~~text
infra/
  regions/
    primary/
    disaster-recovery/
  databases/
  broker/
applications/
  order/
    base/
    overlays/
      staging/
      production/
      dr/
  payment/
  inventory/
policies/
  network/
  admission/
  identity/
~~~

Đây là cấu trúc minh họa. Quan trọng không phải tên folder, mà là **cấu hình versioned, review được, có quyền sở hữu và có thể dựng lại ở môi trường khác**.

Khi DR:

1. Chọn commit/tag cấu hình đã được biết tốt.
2. Xác nhận image digests tương ứng, không chỉ dùng `latest`.
3. Áp IaC/network/IAM và storage dependency theo thứ tự phù hợp.
4. Kết nối config đến DB/broker mục tiêu, chưa mở người dùng ghi ngay.
5. Kiểm tra diff giữa desired và live state.
6. Chỉ sau khi điều kiện dữ liệu/secret thỏa mãn mới mở lại reconciliation và autoscaling theo policy.

**GitOps không thể thay backup database**. Git chứa cấu hình và desired state, không chứa toàn bộ bản ghi giao dịch đang chạy. Ngược lại, restore database không giúp dựng lại namespace, TLS và workload identities nếu chúng không được quản lý.

## 20. Secret manager, KMS và khóa mã hóa trong DR

Một service có thể lưu dữ liệu được mã hóa bởi KMS key. Restore database thành công nhưng mất khả năng sử dụng key gốc khiến ứng dụng **không giải mã được**. Cần thiết kế key availability/backup/replication theo khả năng của KMS được chọn.

Phân biệt:

- **Secret value:** password/token/credential cần cho một service.
- **Secret reference:** đường dẫn/tên/version chỉ tới giá trị, có thể lưu trong config.
- **KMS key:** key dùng mã hóa hoặc wrap data key; cách bảo vệ và export khác nhau theo provider.
- **Workload identity/IAM policy:** danh tính nào được phép đọc secret hoặc sử dụng KMS key.
- **Certificate/CA:** xác minh TLS, ký request hoặc mTLS giữa các dịch vụ.
- **Rotation state:** secret cũ/mới có thể cùng cần trong cửa sổ chuyển tiếp.

Một recovery checklist:

1. Secret manager có sẵn từ region DR chưa?
2. Reference trong config có trỏ đúng secret và version?
3. Workload identity sau restore có quyền tối thiểu cần thiết?
4. KMS key cho dữ liệu lịch sử còn khả dụng và được phép sử dụng?
5. Certificate/trust chain có đúng hostname/region mới?
6. Các token cũ bị compromise đã được thu hồi chưa?
7. Có cơ chế rotate credentials sau incident theo mức rủi ro?
8. Audit có ghi lại ai đã truy cập hoặc phục hồi secret không?

**Không đưa plaintext secret vào Git, image, log, ticket hoặc README** để đơn giản hóa DR. Cần thiết kế bootstrap/escrow theo policy và bảo vệ quyền truy cập.

## 21. Phục hồi Kubernetes và môi trường runtime

Ngay cả khi database và broker sẵn sàng, runtime cần được tái tạo:

- Cluster/network, ingress/load balancer, DNS, private routing.
- Namespaces, service accounts, RBAC/IAM, NetworkPolicy.
- CRDs/controllers/operators nếu service phụ thuộc.
- StorageClasses, PVC/volume và CSI driver.
- HPA/autoscaler, resource quotas/limits, priority classes.
- Deployments/StatefulSets/Jobs/CronJobs và image pull secrets.
- ConfigMaps, Secret references, admission policy, pod security.
- Observability agents, alert routing và backup operators.

**Không nhất thiết snapshot nguyên trạng mọi object Kubernetes.** Với các object desired state được quản lý tốt bằng GitOps/IaC, có thể dựng lại bằng khai báo. Nhưng stateful workloads, PVC, custom-resource state và metadata điều phối đòi kế hoạch bảo vệ riêng. Cần phân biệt tài nguyên có thể tái tạo với dữ liệu bắt buộc restore.

### Đừng mở Deployment quá sớm

Nếu mọi service được bật đồng loạt khi database vừa lắng nghe TCP, các consumer có thể:

- Commit offset khi schema registry chưa sẵn sàng.
- Retry và gây tải lớn vào provider chưa ổn định.
- Phát sự kiện sai khi database đang cần reconciliation.
- Chạy migration ngoài thứ tự, phá schema vừa restore.
- Khởi động CronJob billing/settlement và nhân đôi các lệnh tiền.

Có thể scale consumer/write-capable components về 0 hoặc bật **maintenance/read-only mode** trong giai đoạn kiểm tra, theo thiết kế và năng lực của ứng dụng.

## 22. Thứ tự khôi phục phụ thuộc dependency graph

Một thứ tự điển hình cho sự cố lớn:

~~~text
0. Incident command / quyết định DR / freeze changes
                     |
                     v
1. Fence primary cũ + xác nhận authoritative region
                     |
                     v
2. Bootstrap IAM / network / KMS / secrets / registry
                     |
                     v
3. Restore DB + broker + schema registry (có thể song song)
                     |
                     v
4. Kiểm tra recovery points, schema, metadata, quyền
                     |
                     v
5. Reconcile dữ liệu, outbox/inbox, offset và providers
                     |
                     v
6. Khởi động internal services trong maintenance mode
                     |
                     v
7. Canary reads, controlled writes, synthetic journeys
                     |
                     v
8. Chuyển DNS/traffic và mở dần production
                     |
                     v
9. Giám sát, đối soát sau DR, đóng incident
~~~

Thứ tự chính xác thay đổi theo kiến trúc. Ví dụ config server phụ thuộc vào database có thể tạo vòng dependency; cần thiết kế bootstrap mode hoặc seed config trước. Một số database/broker có thể phục hồi song song, nhưng **mở consumers** phải tuân thủ quy tắc dữ liệu/offset.

## 23. Fencing và phòng tránh split-brain

**Split-brain** xảy ra khi hai môi trường cùng tin mình là primary và nhận ghi độc lập. Trong e-commerce, hai vùng cùng xử lý một order hoặc cả hai phát lệnh thanh toán có thể tạo hậu quả khó đối soát.

Trước khi cutover:

- Xác định ai có quyền quyết định primary.
- Ngăn primary cũ nhận writes hoặc revoke credential/network route khi cần.
- Dùng cơ chế leader election/fencing/quorum theo platform, không chỉ “tắt DNS”.
- Đảm bảo producer mới không phát event từ hai nguồn cùng business key một cách không kiểm soát.
- Xác minh database primary election và write endpoint đúng.
- Đánh giá nguy cơ primary cũ hồi phục muộn rồi tiếp tục nhận lệnh.
- Có quy trình đưa primary cũ trở lại làm standby bằng resynchronization, không cho ghi tùy tiện.

**DNS TTL không phải hàng rào an toàn tuyệt đối.** Client có cache, connection pool hoặc IP cố định; DNS đã chuyển không đảm bảo mọi writer đã ngừng kết nối vùng cũ.

## 24. Điểm phục hồi nhất quán giữa database và broker

Một hệ thống có thể lưu `orderId=O42` trong DB và phát event E42 vào broker. Tại DR, nếu:

~~~text
DB restored to:    T=10:01
Broker restored to T=10:05
~~~

thì broker có thể còn event nói về order mà bản DB không có. Nếu ngược lại:

~~~text
DB restored to:    T=10:05
Broker restored to T=10:01
~~~

DB có thể có outbox record cho event chưa được thấy trong broker restore, và publisher cần phát lại.

Không thể giải quyết mọi trường hợp bằng một câu “restore cùng timestamp”. Các hệ thống có cơ chế clock/log riêng, chưa chắc cung cấp distributed consistent snapshot. Thay vào đó:

1. **Ghi business/event identity bền vững** cùng transaction khi có thể.
2. Lưu outbox/inbox và version/sequence cho aggregate.
3. Chọn nguồn dữ liệu có thẩm quyền theo miền nghiệp vụ.
4. Phân loại trường hợp `DB ahead` và `broker ahead`.
5. Replay những event được phép theo idempotency.
6. Đối soát event chưa chắc chắn với record và external providers.
7. Dừng mở traffic nếu xuất hiện sai lệch không giải thích được trong giao dịch quan trọng.

### Một bảng reconciliation minh họa

| Order DB | Broker/outbox | Payment provider | Hành động |
|---|---|---|---|
| Có order, event chưa phát | Có outbox record | Chưa charge | Publish event theo cùng eventId, kiểm tra tiếp |
| Có order, event bị replay | Đã từng phát | Không liên quan | Consumer dedup, không tạo order/stock effect trùng |
| Mất order do DB rollback | Event vẫn tồn tại | Chưa charge | Quarantine/rebuild theo nguồn có thẩm quyền, tránh tự tạo dữ liệu mù |
| Order PENDING | PaymentCompleted thiếu | Đã charge | Reconcile với provider, cập nhật trạng thái đúng và phát event an toàn |
| Order PAID | Broker thiếu event cho downstream | Đã charge | Reconstruct từ ledger/outbox khi contract cho phép |
| Order CANCELLED | Broker có event cũ OrderCreated | Có thể đã có side effect | Dùng version/state machine, không ghi lùi trạng thái |

Đây là ma trận xử lý thiết kế, không phải kịch bản để chạy UPDATE trực tiếp lên production. Mỗi thao tác sửa trạng thái cần có audit và tuân thủ nghiệp vụ.

## 25. Consumer offset và database checkpoint: một cặp phải đối chiếu

Một consumer xử lý event theo thứ tự:

~~~text
A. Poll event E
B. Bắt đầu DB transaction
C. Ghi inbox + business state
D. Commit DB
E. Commit/ACK offset ở broker
~~~

Sự cố giữa D và E gây redelivery; idempotency xử lý được nếu checkpoint và state cùng tồn tại như thiết kế. Nhưng DR có thể restore broker và database về **hai thời điểm khác nhau**. Đó là lý do cần đối chiếu:

- Offset đã commit trong broker.
- Message ID/sequence đã xử lý trong DB.
- Business data thực sự đã commit.
- Retention của log còn đủ để replay hay không.
- Retry topics, DLQ và trạng thái message đang chờ.

Nếu broker offset đi **trước** DB restored state, consumer có thể bỏ qua work chưa còn trong DB. Có thể cần rewinding offset theo quy trình an toàn; không làm mù, vì replay có thể gây side effect ngoài. Nếu DB đi trước broker, có thể cần tái tạo event từ outbox hoặc xử lý recovery gap.

**Không coi `consumer lag = 0` là dữ liệu đã nhất quán**. Lag = 0 chỉ cho biết vị trí tiêu thụ so với log hiện có trong cách đo cụ thể, không chứng minh những message bị mất do retention hoặc cross-cluster replication đã được bù.

## 26. Quản lý retention, DLQ và replay window

Một hệ thống chỉ có thể replay event còn được giữ hoặc tái tạo. Nếu broker giữ message 24 giờ nhưng thời gian phát hiện logical corruption có thể là 3 ngày, broker không tự cung cấp log đủ cho recovery ba ngày trước.

Chính sách cần xét:

- Retention theo loại topic (command, event, analytics, retry, DLQ).
- Khả năng tái sinh event từ database outbox hoặc event store.
- Backup/export logs nếu cần thời gian bảo vệ dài hơn.
- Dung lượng lưu trữ và chi phí tăng khi retention kéo dài.
- Compacted topics không phải bản lưu đầy đủ mọi historical event.
- Dead-letter queue và parking topics có chính sách backup/khôi phục riêng.
- Schema cần để giải mã event cũ vẫn còn truy cập được.
- Khả năng consumer phiên bản mới đọc event format lịch sử.

**Không tăng retention vô hạn** như biện pháp DR duy nhất. Cần thiết kế quy tắc dữ liệu, bảo mật, deletion policy, throughput replay và kiểm thử thời gian thực sự cần để reprocess.

## 27. Thảm họa do cấu hình sai hoặc deploy lỗi

Không phải mọi DR bắt đầu từ mất hạ tầng. Một thay đổi config có thể khiến hàng chục service cùng kết nối sai broker hoặc credential bị thu hồi đồng loạt.

Ví dụ:

~~~text
T0  Config commit thay broker URL
T1  GitOps áp manifest mới
T2  Consumers lỗi authentication và ngừng xử lý
T3  Queue lag tăng
T4  Đội on-call phát hiện
~~~

Trong trường hợp này, có thể **rollback config** nhanh hơn phục hồi broker từ backup; không nên khởi động một cuộc restore data không cần thiết.

Tuy nhiên nếu config sai đã khiến service ghi vào database nhầm vùng hoặc phát side effect tới provider, chỉ rollback Git commit không giải quyết dữ liệu đã bị thay đổi. Cần đánh giá:

- Config/version nào có hiệu lực lúc đó?
- Service nào đã thực sự nhận và áp config?
- Có tác động lên data plane không?
- Secret/credential mới có bị lộ hoặc revoke sai?
- Có cần restore dữ liệu, reconcile hay chỉ khôi phục config?

Một yếu tố vận hành quan trọng là **deployment audit**: phải truy ngược mỗi service đang chạy tới image digest, config revision, secret version và database/broker endpoint.

## 28. Khôi phục secret sau sự cố bảo mật

Nếu primary bị compromise, **không nên tự động sao chép nguyên trạng toàn bộ credential bị nghi đã lộ** sang secondary rồi mở traffic. Cần có phương án:

1. Xác định thông tin xác thực nào có thể đã bị chiếm.
2. Tạo danh tính/credential mới trong môi trường đã làm sạch.
3. Thu hồi token, khóa API hoặc certificate cũ theo khả năng của dependency.
4. Phục hồi data encryption keys cần đọc dữ liệu lịch sử theo quy trình an toàn, không lẫn với việc tiếp tục sử dụng user password bị lộ.
5. Cập nhật secret references, RBAC và các quyền service.
6. Kiểm tra service không còn dùng credential cũ từ cache hoặc environment.
7. Theo dõi audit log và truy cập bất thường sau DR.

Không phải mọi loại KMS key có thể export hoặc copy giữa region/account. Thiết kế DR phải hiểu giới hạn của key service và có đường tiếp cận tương thích với chính sách bảo mật.

## 29. Kiểm tra phục hồi trước khi mở traffic

Một checklist dữ liệu:

| Hạng mục | Kiểm tra tối thiểu |
|---|---|
| Database accessible | Kết nối được qua identity đúng, không mở quyền admin tràn lan |
| Schema compatibility | Version schema đúng với image dự định chạy |
| Data integrity | Row count, constraints, checksum/sample hoặc tính nhất quán phù hợp |
| Business invariant | Order/payment/stock ledger không mâu thuẫn nghiêm trọng |
| Broker | Topic/partition/config/ACL/schema registry có đủ |
| Consumer | Offset mapping và replay policy đã được kiểm soát |
| Outbox/inbox | Pending records có thể tiếp tục, duplicate không gây effect mới |
| Config | Endpoint, feature flags, TLS, secrets đúng DR environment |
| Artifact | Image digest đã phê duyệt, còn trong registry |
| Runtime | Readiness, CPU/memory, shutdown, autoscaling hoạt động |
| Network | DNS, routing, firewall và external callback đúng vùng |
| Observability | Logs/metrics/traces/alerts thực sự tới nơi theo dõi |
| Security | IAM, encryption và audit đã bật theo chính sách |

### Synthetic user journeys

Trước khi mở traffic rộng, chạy kịch bản bằng tài khoản thử nghiệm và provider sandbox:

- Đăng nhập hoặc sử dụng session hợp lệ.
- Xem sản phẩm và giá đúng.
- Đặt một đơn test duy nhất, xác nhận không phát trùng order.
- Reserve inventory và kiểm tra stock delta đúng.
- Thanh toán qua sandbox với cùng idempotency key.
- Xác minh Order cuối cùng ở trạng thái hợp lệ.
- Phát lại event test để chắc chắn consumer dedup.
- Kiểm tra notification, order visibility và reconciliation.
- Dừng/khởi động một consumer để kiểm tra recovery tiếp tục.

**Không test trực tiếp bằng giao dịch thanh toán thật** nếu không có quy trình sandbox/ủy quyền phù hợp. Mọi test phải có cách dọn và tránh gây ảnh hưởng khách hàng thật.

## 30. Kế hoạch mở lại traffic theo giai đoạn

Không nhất thiết chuyển 100% người dùng ngay khi smoke test xanh.

Một cách an toàn:

~~~text
Phase 0: Môi trường DR cô lập, không nhận traffic public
Phase 1: Read-only và internal synthetic tests
Phase 2: Một số write test có kiểm soát và đối soát
Phase 3: Canary một phần traffic hoặc cohort đã định
Phase 4: Mở rộng dần khi SLI/ledger/lag ổn định
Phase 5: Full traffic + giám sát sau DR
~~~

Trong mỗi giai đoạn cần tiêu chí chuyển tiếp:

- Tỷ lệ success và latency user journey có đạt?
- Payment/stock invariants có đúng?
- Broker lag có giảm, DLQ có tăng bất thường?
- Database lock, connection pool và WAL/archive có ổn?
- Secret auth errors, certificate và DNS lỗi có xuất hiện?
- Có message cũ được replay tạo hiệu ứng trùng?
- Có kế hoạch dừng/rollback nếu tiêu chí không đạt?

Nếu hệ thống chỉ phục hồi read-only trong RTO nhưng chưa nhận được write quan trọng, cần ghi rõ **mức dịch vụ đã phục hồi**. Không tuyên bố RTO đạt cho checkout chỉ vì trang sản phẩm đã mở.

## 31. Khôi phục môi trường primary cũ sau failover

Sau khi secondary thành primary mới, primary cũ có thể hoạt động lại. Đây là thời điểm nguy hiểm.

**Không** đơn giản bật lại primary cũ và cho service kết nối vào dữ liệu cũ:

- Có thể có giao dịch đã ghi ở DR nhưng primary cũ chưa nhận.
- Broker logs đã diverge hoặc offset mapping khác.
- Secrets và roles có thể đã được rotate.
- DNS/client cache còn trỏ qua hai vùng.
- Các job scheduled có thể chạy hai lần.

Quy trình:

1. Giữ primary cũ ở trạng thái không nhận ghi.
2. Kiểm tra storage/cluster có phù hợp để resync từ nguồn authoritative mới.
3. Dùng cơ chế rebuild standby/replication được database/broker hỗ trợ.
4. Không merge hai lịch sử ghi diverged nếu chưa có conflict-resolution plan thực sự.
5. Chạy consistency checks, chuyển cấu hình và identity có kiểm soát.
6. Cập nhật topology/runbook; quyết định có **failback** hay giữ DR region thành primary.
7. Diễn tập failback riêng; không coi failback luôn an toàn hoặc luôn bắt buộc.

## 32. Quan sát RPO/RTO trên thực tế

Khi sự cố xảy ra, cần ghi timeline:

~~~text
10:00  Sự cố bắt đầu ảnh hưởng checkout
10:04  Alert phát hiện
10:10  Incident command kích hoạt DR
10:15  Primary được fence
10:25  Database restore target sẵn sàng
10:32  Broker/schema registry phục hồi
10:40  Reconciliation và smoke test đạt
10:47  Canary ghi thành công
10:55  Mở lại production traffic phù hợp
~~~

Ví dụ trên cho **actual recovery duration** từ 10:00 tới 10:55 là 55 phút, nếu định nghĩa RTO kết thúc ở “checkout phục hồi và nhận traffic đúng”. Nếu RTO mục tiêu 45 phút, đã **không đạt** dù mọi thành phần đều hoạt động cuối cùng.

RPO phải đo riêng:

- Dữ liệu cuối có thể xác nhận ở recovery point nào?
- Những business operations nào có thể thiếu?
- Có bao nhiêu operation được lấy lại từ log, outbox hoặc provider?
- Bao nhiêu operation còn chưa thể đối soát?
- Độ trễ/khả năng mất dữ liệu của broker và từng database có gì khác?
- Số liệu được xác minh bởi ai, ở nguồn nào?

**RPO “0” có nghĩa nghiêm ngặt**, không chỉ là thấy database có replication. Cần chứng minh bằng cơ chế commit, network failure model và mục tiêu đã ký; trong một số kiến trúc, đạt RPO gần 0 đổi lại latency hoặc availability.

## 33. Chỉ số vận hành cần theo dõi trong và sau DR

| Chỉ số | Mục đích |
|---|---|
| Time to detect | Thời gian từ tác động đầu tới khi phát hiện |
| Time to declare DR | Thời gian đưa quyết định chuyển chiến lược |
| Time to restore data | Thời gian database/broker có dữ liệu truy cập được |
| Time to recover user journey | RTO thực tế cho checkout/payment |
| Data loss window/operations | RPO thực đo theo dữ liệu phục hồi |
| WAL archive lag / backup age | Mức sẵn sàng khôi phục database |
| Broker replication lag | Độ lệch dữ liệu giữa primary-secondary |
| Consumer lag/backlog age | Thời gian để downstream bắt kịp |
| Replayed/duplicate events | Kích thước và hiệu quả dedup trong recovery |
| Reconciliation exceptions | Những operation chưa thể giải thích |
| Payment charge mismatches | Lỗi nghiêm trọng cần ưu tiên xử lý |
| Inventory discrepancy | Rủi ro oversell hoặc reservation sai |
| Secret/auth failure | Cấu hình/danh tính DR chưa đúng |
| SLI success/latency | Trải nghiệm người dùng sau cutover |
| Backup restore drill success | Khả năng phục hồi đã được kiểm chứng trước sự cố |

Metric hạ tầng “CPU 20%” không chứng minh checkout được phục hồi. Cần **end-to-end SLI**, ledger correctness và những chỉ số dữ liệu quan trọng.

## 34. Kiểm thử khôi phục: cần diễn tập trước khi thảm họa thật

Một bản backup chỉ đáng tin khi có restore test. Diễn tập nên kiểm chứng cả **thời gian**, **thao tác**, **quyền truy cập** và **dữ liệu**.

### 34.1. Bốn cấp độ diễn tập

1. **Backup integrity check:** xác minh file/manifest/chữ ký/checksum và trạng thái job.
2. **Isolated component restore:** restore một DB, topic hoặc secret reference vào môi trường thử nghiệm riêng.
3. **Application recovery test:** chạy service thật trên dữ liệu khôi phục; test API, schema và IAM.
4. **Full disaster recovery game day:** giả lập mất một failure domain, chuyển hệ thống sang môi trường DR, chạy synthetic user journeys, đo RTO/RPO và failback plan.

Cấp 1 không thể thay thế cấp 4. Một checksum tốt chỉ nói artifact chưa bị lỗi theo phép kiểm tra đó; không chứng minh schema và application sẽ chạy.

### 34.2. Ma trận fault injection

| Case | Sự cố giả lập | Bằng chứng cần thu |
|---|---|---|
| D01 | Xóa nhầm một tập record test | PITR/repair khôi phục đúng và audit được |
| D02 | Mất primary DB node | Standby promotion và write fencing đúng |
| D03 | Mất toàn bộ primary region | DR region xử lý được synthetic checkout |
| D04 | Broker primary mất một số record sau replication lag | Xác định gap, replay hoặc đánh dấu loss rõ |
| D05 | Consumer offset được restore đi trước DB | Không skip business effect chưa được commit |
| D06 | Consumer DB đi trước broker log | Reconcile/outbox lấp thiếu event |
| D07 | Schema registry không khôi phục được | Không cho consumer decode sai âm thầm |
| D08 | Secret reference trỏ phiên bản không còn tồn tại | Service khởi động lỗi có kiểm soát, secret restore đúng |
| D09 | KMS key không truy cập được | Phát hiện sớm, không mở traffic với dữ liệu không đọc được |
| D10 | Primary cũ hồi phục trong lúc DR nhận ghi | Fencing ngăn split-brain |
| D11 | Message trùng sau restart consumer | Inbox/idempotency ngăn effect trùng |
| D12 | Payment provider đã charge nhưng DB restore về PENDING | Reconciliation không charge lại |
| D13 | Artifact registry ở primary không có sẵn | Pull được digest đã phê duyệt từ nguồn DR |
| D14 | Quá tải backlog sau cutover | Controlled replay/backpressure, giữ SLI |
| D15 | Restore từ backup nhiễm logical corruption | Phát hiện, chọn recovery point hoặc logical repair |
| D16 | Failback sang primary cũ | Dữ liệu được resync từ authority mới, không diverge |

## 35. Bài thực hành: diễn tập khôi phục Order–Payment–Inventory

Đề bài: hệ thống có Order DB, Payment DB, Inventory DB, broker, schema registry, GitOps và secret manager. Sự cố xảy ra lúc 14:20, primary region không thể sử dụng. Backup/PITR của các database và replication của broker có recovery points khác nhau. Payment provider ngoài vẫn hoạt động.

### Bước 1 — Xác định mục tiêu

Ví dụ chọn:

~~~text
Checkout RTO: 60 phút
Order DB RPO: <= 5 phút
Broker RPO: <= 10 phút
Payment correctness: không charge trùng
Inventory correctness: không oversell
~~~

Đây là mục tiêu minh họa; phải công bố các ngoại lệ và ranh giới phụ thuộc giữa các hệ thống.

### Bước 2 — Chuẩn bị bằng chứng

Tạo tập dữ liệu thử nghiệm có:

- Một order chưa thanh toán.
- Một order đã thanh toán và phát event.
- Một charge provider đã thành công nhưng response bị mất.
- Một reservation đã commit nhưng consumer ACK chưa ghi.
- Một event nằm trong DLQ.
- Một bản cập nhật cấu hình vừa được phê duyệt.
- Một secret vừa rotate, dữ liệu cũ vẫn dùng key mã hóa cũ.

Ghi những ID/sequence cần đối chiếu; không dùng dữ liệu khách hàng thật nếu không có quyền và biện pháp bảo vệ phù hợp.

### Bước 3 — Tiêm sự cố

Giả lập primary region unreachable. Đảm bảo mục tiêu fault rõ và có thể khôi phục, không vô ý gây tác động production. Dừng writes tại nguồn cũ; xác minh fencing.

### Bước 4 — Restore infrastructure/config

Dựng network/IAM, KMS/secret references, registry artifacts, database target, broker/schema registry và service identities theo dependency graph.

### Bước 5 — Restore data

Chọn DB recovery points hợp lệ từ backup/WAL; phục hồi broker từ replication/backup. Ghi chính xác mỗi điểm restore và khoảng dữ liệu có nguy cơ thiếu.

### Bước 6 — Reconcile

So sánh Order, Payment, Inventory và provider. Với những outcome chưa biết, sử dụng stable operation IDs; không phát payment command mới khi charge cũ chưa được kiểm tra. Kiểm tra replay duplicate và các event gap.

### Bước 7 — Kiểm tra chức năng

Chạy synthetic checkout, payment sandbox và inventory. Kiểm tra readiness, schema, secret access và end-to-end state. Bật consumer có kiểm soát, theo dõi offset/lag và DLQ.

### Bước 8 — Mở traffic và đo RTO/RPO

Đánh dấu thời điểm user journey phục hồi, đo actual recovery, số operations bị mất hoặc chưa được giải thích; không chỉ đánh dấu “pods ready”. So sánh với mục tiêu.

### Bước 9 — Failback hoặc giữ DR

Quyết định authority mới. Nếu failback, resync primary cũ từ nơi đã nhận writes và diễn tập kế hoạch chuyển theo hướng ngược lại. Không cho hai vùng cùng ghi khi thiếu conflict-resolution.

### Bước 10 — Rút kinh nghiệm

Lưu timeline, điểm mất dữ liệu, bước thủ công chậm, credential bị thiếu, consumer replay bugs và danh sách sửa runbook. Tạo nhiệm vụ để lần diễn tập sau có thể đo mức cải thiện.

## 36. Runbook tối thiểu có thể giao ca

Một mẫu khung:

~~~markdown
# Disaster Recovery Runbook — Order/Payment/Inventory

## Trigger và quyết định
- Tiêu chí kích hoạt:
- Incident commander:
- Authority của dữ liệu:
- Mức dịch vụ cần phục hồi:
- RTO/RPO và time window:

## An toàn trước thao tác
- Fencing primary:
- Tạm dừng scheduled jobs:
- Phạm vi credential cần khóa/rotate:
- Bằng chứng và timeline đã chụp:

## Recovery inputs
- Database backup ID / WAL range:
- Broker cluster/topic recovery source:
- Schema registry snapshot:
- GitOps commit / image digests:
- KMS/secret manager path:
- DNS/network/IAM config revision:

## Thực hiện
- Infrastructure bootstrap:
- Database restore và consistency checks:
- Broker/topic/offset restore:
- Cấu hình, identity, secret checks:
- Service startup và hạn chế ghi:

## Reconciliation và acceptance
- Order/Payment/Inventory invariants:
- Replay, duplicate và DLQ:
- Synthetic user journey:
- SLI, lag, auth and latency:
- Sign-off để mở traffic:

## Sau cutover
- RTO/RPO thực tế:
- Dữ liệu còn chưa đối soát:
- Giám sát 24h theo policy:
- Kế hoạch failback:
- Owner và action items:
~~~

Mẫu chỉ thể hiện những trường cần điền, không phải file runbook thực thi tự động. Trong sự cố thật, runbook cần link tới hành động đúng phiên bản platform, command được phê duyệt, người trực và đường liên lạc dự phòng.

## 37. Các sai lầm thường gặp

**Cho rằng replica = backup.** Logical corruption, xóa nhầm hoặc xâm nhập có thể lan sang replica. Cần bản backup tách failure domain và restore test.

**Chỉ đo thời gian DB khởi động.** Checkout có thể chưa chạy vì broker, secret, DNS hoặc provider reconciliation. RTO phải gắn user journey.

**Restore mỗi thành phần tới timestamp khác nhau rồi xem hệ thống nhất quán.** Cần kiểm tra outbox/inbox, event gap, business ledger và external provider.

**Copy consumer offsets mà không đối chiếu database.** Có thể skip message chưa được áp dụng hoặc replay side effect trùng.

**Tăng retention broker và tin đã có DR.** Retention không bảo vệ tất cả cluster metadata, ACL, schema registry hoặc disaster scenarios.

**Bật mọi consumer/CronJob cùng lúc.** Có thể gây retry storm, duplicate billing hoặc publish dữ liệu mâu thuẫn.

**Khôi phục cấu hình Git nhưng không secret/KMS.** Image có thể chạy nhưng không giải mã dữ liệu hoặc xác thực dependency.

**Dùng latest image khi DR.** Không biết binary có tương thích DB schema và message formats đã restore. Pin digest đã được xét.

**Không fence vùng primary cũ.** Nếu primary hồi phục và tiếp tục nhận ghi, có thể phát sinh hai lịch sử nghiệp vụ mâu thuẫn.

**Chỉ kiểm tra HTTP 200.** Một endpoint vẫn có thể trả 200 khi order/payment ledger sai. Cần invariant và synthetic flow end-to-end.

**Giữ backup cùng account/region/credential với hệ thống chính.** Khi failure domain hoặc tài khoản bị compromise, backup có thể mất theo.

**Không phục hồi thử key mã hóa.** Backup data tồn tại nhưng không giải mã được khi KMS/key unavailable.

**Dùng một idempotency ledger đã rollback như bằng chứng tuyệt đối.** Side effect ngoài có thể đã xảy ra sau recovery point; cần reconciliation và business operation key.

**Bỏ qua dữ liệu trong DLQ, retry topic, schema registry và config service.** Hệ thống có thể mất những workflow đang chờ hoặc không decode được event.

**Không diễn tập failback.** Đưa primary cũ trở lại có thể gây split-brain hoặc ghi đè dữ liệu mới từ DR.

**Đo RPO bằng lời hứa của nhà cung cấp mà không kiểm tra dữ liệu thật.** RPO end-to-end phải tính tới lag, backup integrity, khả năng replay và consistency.

## 38. Checklist thiết kế trước khi công nhận kế hoạch DR

1. Những user journeys nào bắt buộc phục hồi và ở mức chức năng nào?
2. RPO, RTO, MTPD và tiêu chí acceptance có được owner kinh doanh chấp thuận?
3. Mỗi database có backup/PITR được test và quyền khôi phục độc lập không?
4. Có bản backup trước thời điểm có thể phát hiện logical corruption không?
5. Dữ liệu backup, WAL, config và KMS có nằm ngoài cùng failure domain?
6. Broker có chiến lược DR cho topic data, config, ACL, offsets, retry/DLQ không?
7. Schema registry có thể khôi phục để giải mã event lịch sử?
8. Có phân biệt offset giữa source cluster và target cluster, tránh copy mù?
9. Outbox, inbox, idempotency và business keys có đủ để replay an toàn?
10. Khi database và broker recovery points lệch, có ma trận reconciliation?
11. External payment/provider status có thể truy vấn lại và đối soát?
12. Identity, secret version, KMS key và TLS certificate được phục hồi an toàn?
13. GitOps config, IaC và image digests có thể truy cập từ DR region?
14. Đã biết cách dừng/disable scheduled jobs và consumers trong recovery?
15. Có cơ chế fencing để tránh hai vùng cùng nhận ghi?
16. Có synthetic user journeys và correctness checks trước cutover?
17. Có dashboard về actual RTO/RPO, lag, bad events và reconciliation exceptions?
18. Có thể rollback/canary và giới hạn tải khi mở traffic?
19. Có runbook failback và kế hoạch resync primary cũ?
20. Đã diễn tập trong môi trường cô lập đủ giống production và lưu kết quả cải tiến?

## 39. Bài tập tự luyện

### Bài A — Recovery point không đồng bộ

Order DB được restore tới 10:05, Payment DB tới 10:08, broker secondary tới 10:02. Một PaymentCompleted event lúc 10:06 đã tạo charge thành công. Hãy lập bảng trạng thái có thể xảy ra, chọn nguồn kiểm chứng và thiết kế reconciliation để không charge lần hai.

### Bài B — Offset đi trước DB

Consumer đã commit offset 6.000 nhưng database được restore về khi mới áp dụng message tới 5.800. Hãy mô tả các rủi ro, cách lựa chọn replay range, điều kiện idempotency và cách xử lý external side effects đã xảy ra.

### Bài C — Restore database từ backup và WAL

Có base backup lúc 00:00, WAL archive hợp lệ tới 09:58, ứng dụng bắt đầu ghi sai từ 09:55, phát hiện lúc 10:10. Hãy xác định các phương án restore/repair, tác động mất dữ liệu hợp lệ và lý do không mặc định restore tới 09:58.

### Bài D — Schema registry không có trong backup

Broker lưu đủ records nhưng consumer mới lỗi khi decode event version cũ. Hãy thiết kế danh sách metadata cần khôi phục, smoke tests và policy không xóa schema vẫn còn dùng bởi historical events.

### Bài E — Mất secret manager và KMS

Database backup còn nguyên, nhưng workloads không truy cập được secret và key giải mã. Hãy phân biệt secret, secret reference, key material và IAM; đề xuất thứ tự bootstrap, cách kiểm tra và cách tránh lưu plaintext secret trong Git/runbook.

### Bài F — Split-brain sau failover

Primary region tạm ngừng mạng rồi hoạt động lại khi DR region đã nhận order mới. Hãy thiết kế fencing, nguồn authoritative, cơ chế resync và điều kiện được phép failback.

### Bài G — Kiểm tra RTO thực tế

Sự cố ảnh hưởng checkout lúc 14:00; phát hiện 14:05; database phục hồi 14:22; broker 14:30; consumer/reconciliation 14:50; người dùng checkout thành công lại từ 15:03. Với RTO mục tiêu 60 phút, hãy xác định thời điểm kết thúc đo và lý do không tính 14:22 là phục hồi đầy đủ.

### Bài H — Phân loại dữ liệu broker

Một số topic chứa event tái sinh từ outbox, một số nhận webhook từ đối tác, một số là analytics stream có thể reprocess. Hãy chọn backup/replay policy theo mức độ không thể tái tạo và đề xuất cách xác minh RPO.

### Bài I — Security incident

Credential của CI và registry bị compromise, nghi image tag đã bị ghi đè. Hãy xác định cách sử dụng digest/signature/provenance, làm sạch runtime, rotate credentials và chọn artifact đáng tin trước khi khôi phục production.

### Bài J — Chỉ số DR cho lãnh đạo

Thiết kế dashboard thể hiện actual RTO, actual RPO, số user journeys đang phục hồi, số giao dịch chưa đối soát, dữ liệu bị ảnh hưởng và người chịu trách nhiệm. Phân biệt số liệu đã xác nhận với ước lượng trong incident.

## 40. Tóm lược

Phục hồi thảm họa trong microservices là bài toán **phục hồi một hệ thống có trạng thái phân tán**, không chỉ khởi động lại vài process. Database cần backup/PITR và kiểm tra dữ liệu; broker cần chiến lược bảo vệ records, offsets, metadata và schemas; cấu hình cần GitOps, image digests, secret manager, KMS, IAM và network phù hợp. Những thành phần này có thể phục hồi tại **những mốc khác nhau**, nên hệ thống cần idempotency, transactional outbox/inbox, reconciliation và một nguồn dữ liệu có thẩm quyền cho từng lĩnh vực.

Một kế hoạch DR đáng tin cậy phải trả lời được bốn câu hỏi: **Dữ liệu nào còn? Dữ liệu nào mất hoặc chưa biết? Có thể xử lý nghiệp vụ mới mà không gây thêm sai lệch không? Người dùng đã thực sự nhận được dịch vụ ở mức cam kết chưa?** Chỉ sau khi có bằng chứng về tính đúng đắn, RPO/RTO và khả năng giám sát end-to-end, quá trình phục hồi mới được coi là hoàn tất về mặt nghiệp vụ.
