# Global Tables và xử lý xung đột đa Region

> **Chương:** DynamoDB  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **Amazon DynamoDB Global Tables** và mô hình replica table tại nhiều AWS Regions.
2. Phân biệt **Multi-Region Eventual Consistency (MREC)** với **Multi-Region Strong Consistency (MRSC)** về replication, read/write semantics, latency, conflict handling và giới hạn.
3. Giải thích cơ chế **last writer wins (LWW)** của MREC và nhận diện nguy cơ mất cập nhật khi nhiều Region ghi cùng một item.
4. Chọn write model phù hợp: **write to any Region**, **write to one Region**, hoặc **write to your Region**.
5. Thiết kế idempotency, optimistic concurrency, versioning và partitioning dữ liệu để giảm xung đột.
6. Hiểu ảnh hưởng của global tables tới **transactions, DynamoDB Streams, TTL, GSI/LSI** và capacity.
7. Thiết kế routing ứng dụng, failover, Region evacuation, RPO/RTO và kiểm thử khôi phục.
8. Phân biệt **same-account** và **multi-account global tables**, quản lý IAM, service-linked roles, resource policies và KMS.
9. Theo dõi **ReplicationLatency**, throttling, system errors và trạng thái replica bằng CloudWatch/CloudTrail/CLI.
10. Ước lượng chi phí replicated writes, storage, read capacity, indexes, backups và vận hành đa Region.

## 1. Bài toán: người dùng ở nhiều Region cùng sửa một dữ liệu

Một ứng dụng thương mại điện tử có khách hàng tại Việt Nam, Singapore, châu Âu và Bắc Mỹ. Nếu mọi request đều phải gọi một DynamoDB table đặt tại một Region duy nhất, người dùng ở xa có thể chịu thêm network latency và hệ thống phụ thuộc nhiều hơn vào khả năng phục vụ của Region đó.

**DynamoDB Global Tables** cho phép giữ các replica của cùng một table tại nhiều AWS Regions. Ứng dụng tại mỗi Region có thể gọi **regional DynamoDB endpoint cục bộ** để đọc/ghi dữ liệu. DynamoDB tự quản lý replication giữa các replica.

~~~mermaid
flowchart TB
    subgraph SG["ap-southeast-1"]
      APPSG["Orders API - Singapore"]
      DBSG[("Orders replica")]
      APPSG --> DBSG
    end
    subgraph JP["ap-northeast-1"]
      APPJP["Orders API - Tokyo"]
      DBJP[("Orders replica")]
      APPJP --> DBJP
    end
    subgraph EU["eu-west-1"]
      APPEU["Orders API - Ireland"]
      DBEU[("Orders replica")]
      APPEU --> DBEU
    end
    DBSG <-->|"Replication"| DBJP
    DBJP <-->|"Replication"| DBEU
    DBEU <-->|"Replication"| DBSG
~~~

Sơ đồ thể hiện kiến trúc khái niệm. Mỗi replica là một DynamoDB table tại Region riêng; người dùng không gửi request tới một “global endpoint” duy nhất vì DynamoDB **không cung cấp global endpoint**. Ứng dụng phải quyết định Region nào xử lý request và gọi endpoint của Region đó.

### 1.1. Vì sao Global Tables hữu ích?

- **Độ trễ truy cập thấp hơn:** dữ liệu có bản sao gần application stack và người dùng.
- **Business continuity:** có thể chuyển traffic sang Region khác khi Region hiện tại gặp sự cố.
- **Multi-active:** nhiều replica có thể nhận request đọc/ghi, tùy consistency mode và write model.
- **Tách ranh giới vận hành:** có thể đặt workload, IAM, billing và governance theo Region/account.
- **Mở rộng toàn cầu:** giảm phụ thuộc vào một Region cho lớp dữ liệu.

Global Tables giúp tăng khả năng sẵn sàng của lớp dữ liệu, nhưng **không tự tạo một ứng dụng multi-Region hoàn chỉnh**. Compute, API, authentication, DNS/routing, secrets, queues, observability và deployment cũng cần được triển khai/kiểm thử ở các Region dự phòng.

### 1.2. Những gì Global Tables không tự giải quyết

- Không tự chọn Region gần nhất cho người dùng.
- Không tự điều phối traffic khi application stack ở một Region bị lỗi.
- Không biến MREC thành strong consistency xuyên Region.
- Không bảo đảm mọi giao dịch nhiều items được replicate nguyên tử giữa các Region.
- Không tự giải quyết nghiệp vụ khi hai người cùng sửa một đơn hàng.
- Không thay backup, point-in-time recovery, data retention hoặc quy trình disaster recovery.
- Không loại bỏ yêu cầu thiết kế idempotency và xử lý duplicate requests.

## 2. Phiên bản Global Tables: Current và Legacy

AWS có hai phiên bản lịch sử:

| Phiên bản | Tên thường gọi | Đặc điểm |
| --- | --- | --- |
| **2019.11.21** | Current / V2 | Dùng DynamoDB table hiện có rồi thêm replica qua API UpdateTable; hỗ trợ nhiều Region hơn, vận hành đơn giản hơn và thường tiết kiệm write capacity hơn. |
| **2017.11.29** | Legacy / V1 | Dùng API CreateGlobalTable riêng; trước đây cần tạo các regional tables rỗng tương thích rồi ghép thành global table; có hạn chế Region và cách tính capacity cũ. |

Với thiết kế mới, ưu tiên **Global Tables version 2019.11.21 (Current)** theo khuyến nghị AWS.

### 2.1. Xác định phiên bản

Đối với current version, gọi **DescribeTable** ở Region của replica. Response có trường **GlobalTableVersion = 2019.11.21**.

Đối với legacy version, lệnh **DescribeGlobalTable** thành công cho tên global table là dấu hiệu table dùng mô hình cũ. Nếu không xác định đúng phiên bản, đừng dùng nhầm quy trình quản trị replica của V1 với V2.

### 2.2. Vì sao phiên bản ảnh hưởng chi phí?

Với item 1 KB và hai Regions, tài liệu AWS minh họa Current version tiêu thụ ít replicated write units hơn Legacy:

| Operation | Legacy 2017.11.29 | Current 2019.11.21 |
| --- | ---: | ---: |
| PutItem | 4 rWRUs tổng cộng | 2 rWRUs tổng cộng |
| UpdateItem | 3 rWRUs tổng cộng | 2 rWRUs tổng cộng |
| DeleteItem | 3 rWRUs tổng cộng | 2 rWRUs tổng cộng |

Đây là ví dụ theo giả định item 1 KB và hai replicas; mức tiêu thụ thực tế phụ thuộc kích thước item, operation, số replica, indexes và billing mode. Không áp các số trên cho mọi request hoặc table legacy có cấu hình khác.

### 2.3. Nâng cấp Legacy

Nếu hệ thống đang dùng Legacy:

1. Xác định chính xác phiên bản bằng API/CLI.
2. Đọc quy trình nâng cấp AWS dành cho phiên bản 2017.11.29.
3. Kiểm tra Streams, capacity, replica health, indexes, backups và ứng dụng phụ thuộc.
4. Lập change plan, quan sát replication và kiểm thử sau nâng cấp.
5. Không tự tạo một global table mới rồi xóa các regional tables cũ nếu chưa có kế hoạch cutover và reconciliation dữ liệu.

Nâng cấp version là thao tác control plane có ảnh hưởng vận hành; thực hiện theo hướng dẫn AWS và môi trường kiểm thử trước.

## 3. Hai consistency modes: MREC và MRSC

Khi tạo Global Table, chọn một consistency mode. Nếu không chỉ định, mặc định là **MREC**. Một global table không thể có replicas dùng các consistency modes khác nhau và **không thể đổi consistency mode sau khi tạo**.

| Tiêu chí | **MREC — Multi-Region Eventual Consistency** | **MRSC — Multi-Region Strong Consistency** |
| --- | --- | --- |
| Replication | Bất đồng bộ qua các Region. | Đồng bộ đủ tới ít nhất một Region khác trước khi write trả thành công. |
| Read mạnh | Strongly consistent read chỉ đảm bảo dữ liệu mới nhất tại replica local theo semantics của DynamoDB; chưa bảo đảm thấy ngay write vừa xảy ra ở Region khác. | Strongly consistent read tại replica trả phiên bản mới nhất trên global table. |
| Eventual read | Có thể chưa thấy write vừa được xác nhận ở Region khác cho tới khi replication hoàn tất. | Có thể stale, kể cả thay đổi rất gần đây trong cùng hoặc Region khác. |
| Conflict cùng item | Giải quyết theo **last writer wins** dựa trên timestamp nội bộ. | Write xung đột có thể trả **ReplicatedWriteConflictException** để caller retry. |
| Latency | Local writes/reads thường thấp hơn, replication tới nơi khác diễn ra nền. | Write và strongly consistent read cần cross-Region communication nên latency cao hơn. |
| Số Region | Hai hoặc nhiều Regions, mở rộng theo Regions hỗ trợ. | Chính xác **3 Regions**: 3 replicas hoặc 2 replicas + 1 witness. |
| Transactions | Atomic trong Region gọi transaction; không replicate nguyên tử thành một transaction xuyên Region. | Không hỗ trợ transaction APIs. |
| TTL | Hỗ trợ; TTL delete được replicate. | Không hỗ trợ TTL deletion. |
| Streams | Bật mặc định để phục vụ replication và không thể tắt trên MREC replicas. | Không dùng Streams làm cơ chế replication; có thể bật Streams riêng theo tính năng hỗ trợ. |
| Multi-account | Có hỗ trợ mô hình multi-account. | Chỉ hỗ trợ same-account. |
| RPO | Phụ thuộc replication lag; thường vài giây nhưng không có SLA cho ReplicationLatency. | RPO bằng 0 cho những writes đã được xác nhận thành công. |

### 3.1. Chọn mode theo yêu cầu nghiệp vụ

Chọn **MREC** khi:

- Chấp nhận một khoảng thời gian ngắn trước khi mọi Region thấy cùng một thay đổi.
- Ưu tiên local write latency thấp.
- Ứng dụng có thể chọn một Region ghi cho mỗi item/nhóm dữ liệu hoặc chấp nhận LWW.
- Cần transactions trong một Region và có thể điều phối một primary Region.
- Cần TTL hoặc multi-account global tables.

Chọn **MRSC** khi:

- Strongly consistent reads và writes xuyên các replica là yêu cầu quan trọng.
- Nghiệp vụ không thể chấp nhận mất một write đã được xác nhận thành công khi một Region gặp sự cố.
- Chấp nhận latency cao hơn cho writes/strong reads do trao đổi liên Region.
- Không phụ thuộc transactions hoặc TTL của DynamoDB.
- Mô hình dữ liệu phù hợp với giới hạn ba Regions và witness.

**Không chọn MRSC chỉ vì tên “strong” nghe an toàn hơn.** Cần so sánh latency, quorum availability, transactions, TTL, indexes và chi phí với yêu cầu nghiệp vụ thực.

## 4. MREC hoạt động như thế nào?

MREC sử dụng mô hình **active-active, asynchronous replication**:

1. Ứng dụng ghi vào replica local, ví dụ Singapore.
2. DynamoDB xác nhận write theo điều kiện của Region nhận request.
3. DynamoDB đọc các thay đổi từ DynamoDB Streams và replicate sang các replica khác.
4. Mỗi Region nhận cập nhật và dần hội tụ về cùng dữ liệu.
5. Nếu một replica tạm thời không khả dụng, các thay đổi chưa chuyển được sẽ tiếp tục được thử lại khi replica phục hồi.

Một item mới thường được truyền tới các replica khác trong khoảng một giây hoặc ít hơn theo tài liệu, nhưng độ trễ phụ thuộc Region pair, workload và throughput. Đây **không phải SLA** và không nên dùng “một giây” như cam kết cho mọi request.

### 4.1. Replication theo từng item

Global Tables replicate **từng item**, không replicate một tập items như một transaction xuyên Region. Các partitions cũng replicate song song; thứ tự các write operations ở Region nhận có thể khác thứ tự ở Region nguồn.

Ví dụ, Region A commit hai item trong một transaction:

- Order item chuyển sang PAID.
- Payment summary tăng tổng tiền.

Region B có thể quan sát một item đã replicate trong khi item còn lại chưa tới. Transaction đã atomic ở Region A, nhưng **không được nhìn như một transaction atomic ở Region B**.

### 4.2. Đọc dữ liệu trong lúc replication chưa hoàn tất

Giả sử người dùng cập nhật địa chỉ ở Singapore:

- Write được xác nhận tại Singapore.
- Ngay sau đó, một API ở Tokyo đọc replica Tokyo.
- Nếu replication chưa tới, Tokyo có thể trả địa chỉ cũ.

Đây là hành vi bình thường của MREC. Với yêu cầu **read-your-writes**, ứng dụng có thể tiếp tục đọc từ Region đã ghi trong một khoảng thời gian, hoặc dùng write routing/homing để bảo đảm luồng đọc sau ghi quay về Region phù hợp.

### 4.3. Strongly consistent read trong MREC có ý nghĩa gì?

DynamoDB cho phép Strongly Consistent Read trên table hoặc Local Secondary Index ở từng replica theo semantics của dịch vụ. Nhưng với MREC, đọc mạnh tại Tokyo chỉ bảo đảm đọc dữ liệu đã có ở replica Tokyo; nó không buộc Tokyo đợi mọi write gần đây từ Singapore replicate xong.

**Strong consistency tại một replica không đồng nghĩa strong consistency xuyên tất cả Regions.**

### 4.4. Không có partial replication theo table scope

Một global table replicate toàn bộ items của table tới tất cả participating Regions. Không thể cấu hình một replica chỉ chứa một subset items bằng cách thêm filter theo tenant hoặc partition key.

Nếu cần data residency/replication scope khác nhau, cân nhắc tách thành nhiều tables với tập Regions riêng, hoặc thiết kế kiến trúc dữ liệu khác.

## 5. Xử lý xung đột MREC: Last Writer Wins

Xung đột có thể xảy ra khi cùng một item bị sửa ở hai Regions trong lúc các writes chưa kịp replicate qua lại.

Ví dụ:

- 10:00:00.100 — Region Singapore ghi **shippingAddress = Hanoi**.
- 10:00:00.120 — Region Tokyo ghi **shippingAddress = Da Nang**.
- Hai writes diễn ra gần nhau trước khi replication hoàn tất.

MREC dùng **last writer wins (LWW)** theo timestamp nội bộ của write operation. Phiên bản được xem là mới hơn sẽ thắng; item cuối cùng sẽ hội tụ về phiên bản đó.

~~~mermaid
sequenceDiagram
    participant SG as Replica Singapore
    participant JP as Replica Tokyo
    participant EU as Replica Europe
    SG->>SG: Update item: address = Hanoi
    JP->>JP: Update cùng item: address = Da Nang
    SG-->>JP: Replicate write từ Singapore
    JP-->>SG: Replicate write từ Tokyo
    SG-->>SG: So sánh timestamp nội bộ
    JP-->>JP: So sánh timestamp nội bộ
    SG-->>EU: Replicate phiên bản thắng
    JP-->>EU: Replicate phiên bản thắng
    Note over SG,EU: Các replicas hội tụ theo last writer wins
~~~

### 5.1. LWW không phải merge theo từng field

Không giả định DynamoDB tự hợp nhất hai cập nhật khác thuộc tính thành một item kết hợp.

Ví dụ hai Region cập nhật cùng item:

- Singapore đổi phoneNumber.
- Tokyo đổi preferredLanguage.

Nếu các writes xung đột trên cùng item, cơ chế LWW có thể khiến một phiên bản item thắng và một thay đổi bị mất. DynamoDB không cung cấp automatic semantic merge cho các thuộc tính nghiệp vụ.

### 5.2. Xung đột không được ghi thành một CloudWatch alarm event

Các conflict do LWW được xử lý bên trong cơ chế replication; chúng không được ghi thành một loại event xung đột riêng trong CloudWatch hoặc AWS CloudTrail.

Vì vậy, nếu nghiệp vụ cần biết hai người dùng cùng sửa một hồ sơ, ứng dụng phải tự ghi nhận:

- Actor/user ID.
- Request/operation ID.
- Region xử lý.
- Version trước và sau.
- Timestamp nghiệp vụ.
- Kết quả conflict/merge ở lớp ứng dụng nếu có.

Không chờ CloudTrail báo “LWW conflict” để điều tra.

### 5.3. Vì sao timestamp không thay thế business version?

Timestamp nội bộ DynamoDB phục vụ giải quyết conflict của dịch vụ. Nó không phải một business sequence mà ứng dụng có thể dựa vào để bảo đảm:

- Một đơn hàng chỉ chuyển trạng thái theo workflow hợp lệ.
- Không ghi đè một payment đã capture bằng trạng thái cũ.
- Không cập nhật hồ sơ dựa trên dữ liệu mà người dùng đã đọc từ lâu.
- Không mất một sự kiện cần kiểm toán.

Dùng **version nghiệp vụ**, conditional writes, event log hoặc state machine nếu thứ tự nghiệp vụ quan trọng.

## 6. Indexes và cấu trúc replica

Các replica của cùng một global table phải giữ cùng **table name**, **primary key schema** và dữ liệu items. Global Tables không cho phép mỗi Region tự định nghĩa một partition key khác nhau cho cùng replication group.

### 10.1. Global Secondary Indexes

Với Global Tables current:

- Khi tạo GSI trên một replica, DynamoDB tạo GSI tương ứng trên các replicas khác.
- Quá trình backfill dữ liệu index diễn ra theo cơ chế dịch vụ.
- Định nghĩa GSI phải nhất quán giữa replicas.
- Reads trên GSI là **eventually consistent**, kể cả khi table là MRSC.

Không dùng GSI để giải quyết yêu cầu strong read-after-write xuyên Region. Nếu cần strongly consistent read, đọc table hoặc Local Secondary Index theo giới hạn mode hỗ trợ.

### 10.2. Local Secondary Indexes

MREC hỗ trợ LSI theo các quy tắc DynamoDB thông thường; LSI phải được xác định khi tạo table và có cùng schema trên replicas.

**MRSC không hỗ trợ LSI.** Nếu data model hiện tại phụ thuộc LSI, cần thiết kế lại access patterns hoặc chọn MREC.

### 10.3. Những thuộc tính table phải được đồng bộ

Các replicas cần thống nhất table name, primary key schema và các định nghĩa indexes. Với multi-account global tables, nhiều settings được tự động đồng bộ trên mọi replicas; không được mặc định có thể override capacity mode hoặc GSI schema riêng từng account.

## 7. Same-account và multi-account Global Tables

Global Tables hỗ trợ hai mô hình ownership.

| Tiêu chí | Same-account | Multi-account |
| --- | --- | --- |
| Ownership | Một AWS account quản lý các replicas. | Mỗi replica thuộc một AWS account riêng. |
| Region | Nhiều Regions trong cùng account. | Mỗi replica ở một account và Region khác nhau. |
| Consistency | MREC hoặc MRSC. | Chỉ MREC. |
| IAM/KMS boundary | Cùng account boundary. | Tách IAM, KMS, billing, CloudTrail và governance theo account. |
| Control plane | Account owner quản lý việc thêm/xóa replicas. | Các account tham gia replication group và cung cấp quyền replication. |
| Use case | Tổ chức quản trị tập trung. | Nhóm độc lập, business units hoặc yêu cầu cô lập account. |

### 11.1. Điều kiện multi-account

- Mỗi replica phải nằm trong một AWS account khác nhau; N replicas cần N accounts.
- Multi-account global tables chỉ hỗ trợ **MREC**.
- Chỉ có thể bắt đầu bằng một regional table và thêm replicas ở accounts khác theo quy trình AWS.
- Các account phải cung cấp quyền cần thiết cho DynamoDB global tables service principal trong resource policies.
- GlobalTableSettingsReplicationMode cần được bật cho các replicas để cấu hình được đồng bộ theo mô hình multi-account.

### 11.2. Settings được đồng bộ và không đồng bộ

Multi-account global tables đồng bộ nhiều cấu hình để mọi replicas có cùng behavior:

**Các settings được đồng bộ** gồm capacity mode, provisioned read/write capacity, auto scaling, LSI/GSI definitions, GSI capacity/auto scaling, Streams definition trong MREC, TTL, warm throughput và on-demand maximum throughput.

**Các settings không tự đồng bộ** và cần cấu hình riêng từng replica gồm:

- Table class.
- Server-side encryption type và KMS key ID.
- Point-in-time recovery.
- Deletion protection và disassociation protection.
- Kinesis Data Streams destination.
- Tags và resource policies.
- CloudWatch Contributor Insights cho table/GSI.

Vì vậy, việc thêm một replica mới không có nghĩa mọi security/backup settings tự động giống hệt các Regions khác. Dùng IaC và kiểm tra drift theo từng account/Region.

### 11.3. Security boundary và trách nhiệm account

Multi-account tạo ranh giới blast radius: nếu credentials của một account bị xâm phạm, attacker không tự động có quyền quản trị tất cả accounts khác. Tuy nhiên, replication vẫn có thể bị gián đoạn nếu resource policy, IAM, KMS hoặc Region opt-in bị cấu hình sai.

Mỗi account chịu trách nhiệm bảo vệ local replica, keys, IAM roles, logs và chi phí của mình. Không coi multi-account là một cơ chế tự động bảo đảm data sovereignty hoặc compliance.

## 8. Regional endpoint và request routing

DynamoDB Global Tables **không có global endpoint**. Ứng dụng tại Region A nên gọi DynamoDB endpoint của Region A để truy cập replica local. Khi Region A gặp sự cố, cách phục hồi tốt thường là chuyển **toàn bộ request tới application stack ở Region B**, để stack đó gọi replica DynamoDB local ở B.

~~~mermaid
flowchart TB
    U["Người dùng"] --> ROUTE["Client / Route 53 / Global Accelerator"]
    ROUTE --> SGAPI["API stack Singapore"]
    ROUTE --> JPAPI["API stack Tokyo"]
    SGAPI --> SGDB[("DynamoDB replica SG")]
    JPAPI --> JPDB[("DynamoDB replica Tokyo")]
    SGDB <-->|"Global Tables replication"| JPDB
~~~

### 12.1. Các cách định tuyến

| Chiến lược | Cách hoạt động | Trade-off |
| --- | --- | --- |
| **Client-driven** | Client chọn API endpoint Region dựa trên cấu hình/health/latency. | Client phải biết endpoints và logic failover. |
| **Compute-layer routing** | Service trong Region quyết định xử lý local hay forward tới Region đang primary. | Code phải hiểu data topology và xác thực primary. |
| **Route 53** | DNS failover/latency routing trả về regional application endpoint. | DNS TTL, OS/browser/app caches ảnh hưởng RTO. |
| **AWS Global Accelerator** | Anycast IP đưa traffic qua AWS edge rồi tới endpoint Region được chọn. | Cần cấu hình health/routing và chi phí dịch vụ. |

### 12.2. Không gọi remote DynamoDB endpoint như phương án failover mặc định

Một thiết kế dễ sai là ứng dụng Singapore gặp lỗi DynamoDB rồi gọi thẳng endpoint DynamoDB ở Tokyo, trong khi compute và các dịch vụ phụ trợ vẫn nằm ở Singapore.

Cách này có thể tạo cross-Region latency, khiến các dependency khác vẫn ở Region lỗi và làm khó việc kiểm soát routing. AWS khuyến nghị triển khai application stack ở nhiều Regions và chuyển người dùng tới stack hoạt động tại Region khác.

### 12.3. DNS TTL và failover

Route 53 health checks/failover có thể chuyển endpoint, nhưng client và resolver có thể cache DNS. TTL 60 giây thường được dùng làm một giá trị tham khảo trong thiết kế failover, nhưng không phải mọi client tuân thủ TTL chính xác.

RTO thực tế còn phụ thuộc:

- Thời gian phát hiện sự cố.
- Thời gian cập nhật routing control.
- DNS caching.
- Application warm-up/autoscaling.
- Reconnect của SDK/JDBC/HTTP clients.
- Session/token continuity và downstream dependencies.

## 9. Disaster recovery và Region evacuation

Global Tables hỗ trợ khả năng chuyển workload sang Region khác, nhưng quy trình khác nhau theo consistency mode và write model.

### 13.1. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất khi khôi phục.
- **RTO (Recovery Time Objective):** thời gian tối đa để dịch vụ hoạt động lại.

| Mode | RPO | RTO |
| --- | --- | --- |
| **MREC** | Phụ thuộc replication lag; thường tính bằng giây trong điều kiện bình thường, nhưng writes chưa replicate có thể bị trễ khi Region mất kết nối. | Phụ thuộc application routing, compute, DNS, dependency và quy trình failover. |
| **MRSC** | **0 cho writes đã được xác nhận thành công**. | Không bằng 0; cần thời gian chuyển traffic/compute và có thể phụ thuộc quorum availability. |

### 13.2. Evacuate một Region còn hoạt động với MREC

Nếu Region A còn hoạt động nhưng cần chuyển primary sang Region B:

1. Chặn hoặc tạm dừng writes mới tới A.
2. Đợi các writes đã nhận được propagate tới B.
3. Dùng ReplicationLatency để ước lượng thời gian chờ.
4. AWS Prescriptive Guidance nêu rằng khi A khỏe, chờ khoảng **10 lần giá trị ReplicationLatency maximum gần đây** thường đủ để xác định replication đã hoàn tất; đây là heuristic, không phải bằng chứng tuyệt đối.
5. Chuyển routing/control plane để B trở thành Region được phép ghi.
6. Xác nhận A không còn nhận writes, rồi mở writes ở B.
7. Theo dõi duplicates, stale writes và business reconciliation.

Không có một metric nào chứng minh tuyệt đối rằng mọi writes từ A đã được replicate hoàn tất. Hãy kết hợp pause writes, stream/checkpoint, event source và business invariants.

### 13.3. Region MREC offline đột ngột

Nếu A mất kết nối hoàn toàn:

- Các writes đã xác nhận ở A nhưng chưa propagate sẽ chưa có ở B.
- DynamoDB giữ replication pending và sẽ tiếp tục khi A phục hồi.
- Nếu ứng dụng tiếp tục ghi vào B, các writes mới trên cùng item có thể thắng các writes cũ đang chờ propagate từ A theo LWW.
- Khi A trở lại, replication tiếp tục; nhưng business state có thể cần reconciliation nếu các operations không idempotent.

Các phương án ứng dụng có thể cân nhắc:

- Tiếp tục hoạt động với write-to-any-Region cho dữ liệu idempotent, chấp nhận trạng thái thiếu tạm thời.
- Quarantine những account/order có khả năng thiếu transaction.
- Replay các operations từ upstream event log khi dữ liệu gốc chưa propagate, nếu operations idempotent và có business operation IDs.
- Tách balance/ledger thành các partitions/home Regions để giới hạn blast radius.
- Đối chiếu source of truth trước khi cho phép một workflow tài chính tiếp tục.

**Không mặc định failover MREC là zero data loss.** Nếu Region cũ mất vĩnh viễn và có writes chưa replicate, RPO phụ thuộc các bản ghi đã được xác nhận ở nơi khác hoặc nguồn event/backup độc lập.

### 13.4. Region MRSC offline

MRSC có RPO bằng 0 đối với successful writes. Khi một Region bị offline:

- Các Regions còn lại có thể tiếp tục nếu quorum/replica availability đáp ứng yêu cầu.
- Khi Region trở lại, DynamoDB tự catch up.
- Trong thời gian catch-up, writes và strongly consistent reads vào replica đang phục hồi có thể trả lỗi.
- Các Regions còn lại tiếp tục xử lý theo khả năng quorum.

Không chạy thao tác tạo lại table hoặc copy dữ liệu thủ công chỉ vì một replica MRSC chưa catch up.

### 13.5. Failover không chỉ là đổi endpoint

Trước production, phải thử cả application stack:

- API Gateway/ALB, Lambda/ECS/EC2 và autoscaling.
- IAM roles, Secrets Manager, KMS keys và VPC endpoints.
- Cognito/identity/session continuity.
- SQS/EventBridge/Step Functions hoặc event sources phụ thuộc.
- DynamoDB local endpoint và regional capacity.
- DNS/Global Accelerator/ARC routing.
- Idempotency, duplicate requests và business reconciliation.

## 10. IAM, service-linked roles và KMS

### 14.1. Service-linked role cho replication

DynamoDB sử dụng service-linked role:

**AWSServiceRoleForDynamoDBReplication**

DynamoDB tự tạo role này khi account tạo global table đầu tiên nếu caller có quyền **iam:CreateServiceLinkedRole**. Role cho phép dịch vụ quản lý cross-Region replication.

Nếu IAM resource policy hoặc explicit Deny vô tình chặn các quyền của replication service-linked role:

- Replication có thể dừng.
- Replica có thể chuyển sang trạng thái **REPLICATION_NOT_AUTHORIZED**.
- Với MREC, nếu trạng thái này kéo dài hơn 20 giờ, replica có thể bị chuyển vĩnh viễn thành regional table.
- Với MRSC, việc deny quyền có thể làm write/strongly consistent read trả AccessDeniedException; trạng thái kéo dài có thể khiến replica không thể truy cập theo giới hạn AWS.

Khi tạo SCP/resource policy chặt, phải bảo đảm không vô tình chặn service-linked role của DynamoDB.

### 14.2. IAM permissions cho control plane

Tạo global table hoặc thêm replica có thể yêu cầu các quyền như:

- **dynamodb:UpdateTable** trên source table.
- **dynamodb:CreateTable** và **dynamodb:CreateTableReplica** tại Regions được thêm.
- Quyền đọc/ghi table cần thiết để dịch vụ thiết lập replication theo tài liệu.
- **iam:CreateServiceLinkedRole** cho lần đầu tạo role.
- **dynamodb:CreateGlobalTableWitness** khi tạo MRSC có witness.

Quyền phải giới hạn vào đúng table ARNs, Regions và operations. Không cấp **dynamodb:\*** trên mọi Region chỉ để triển khai một global table.

### 14.3. Resource policies và multi-account

Với multi-account global tables, khách hàng phải cấp quyền replication cho **DynamoDB global tables service principal** trong resource policies của replicas theo hướng dẫn AWS.

Khi sửa resource policy, kiểm tra:

- Principal service được phép.
- Actions cần cho replication.
- Conditions theo account/Region phù hợp.
- Explicit Deny từ identity policy, SCP hoặc resource policy.
- Service-linked role không bị chặn.

Một replica có thể vẫn đọc/ghi local trong một số tình huống nhưng replication cross-account đã dừng; phải giám sát status/latency để phát hiện.

### 14.4. Encryption at rest và KMS

Mọi DynamoDB replica đều mã hóa dữ liệu at rest bằng KMS. Các replicas trong cùng global table phải sử dụng **cùng loại KMS key** theo yêu cầu dịch vụ:

- AWS owned key.
- AWS managed key.
- Customer managed key.

Với customer managed key:

- Key policy phải cho phép DynamoDB sử dụng key.
- Không disable/delete key trước khi replica được gỡ đúng quy trình.
- Thu hồi quyền decrypt có thể khiến replication dừng và replica chuyển sang trạng thái inaccessible encryption credentials.
- Key IDs/keys có thể được cấu hình riêng theo account/Region trong mô hình multi-account, nhưng phải tuân thủ cùng loại key và policy.

**Không xóa KMS key chỉ vì muốn ngừng một replica.** Gỡ replica theo quy trình trước, đợi các table statuses cần thiết, sau đó mới xem xét disable/delete key.

## 11. Capacity planning và throttling

Global Tables cần capacity cho **application writes và replicated writes**. Một write ở một Region có thể tạo replicated write consumption ở các Regions khác.

### 15.1. Provisioned capacity

- Replication tiêu thụ write capacity ở các replicas.
- Nếu application writes + replication writes vượt write capacity, replica có thể throttling.
- Với global table provisioned mode, write auto scaling settings được đồng bộ giữa Regions; mức provisioned thực tế có thể thay đổi độc lập theo từng Region.
- Read capacity có thể được cấu hình khác nhau giữa Regions theo nhu cầu đọc địa phương trong mô hình same-account.
- Cần dự phòng capacity cho failover traffic khi một Region nhận tải từ nơi khác.

Không chỉ sizing theo số writes trực tiếp vào một Region. Khi failover, một Region có thể phải gánh lượng writes/reads lớn hơn workload bình thường.

### 15.2. On-demand capacity

Với on-demand:

- DynamoDB tự điều chỉnh throughput theo traffic.
- Write settings/max throughput có các điều kiện đồng bộ giữa replicas.
- On-demand không có provisioned capacity target nhưng vẫn có table-level maximum throughput limits và quotas.
- Một đợt failover có thể tạo burst khác baseline; cần load test và kiểm tra account/table quotas.

### 15.3. GSI và replicated writes

GSI update được tính capacity riêng theo quy tắc của DynamoDB. Với Global Tables, việc ghi base table và cập nhật GSI có thể tạo write consumption đáng kể ở từng Region.

Một write pattern gây nhiều GSI updates có thể làm replica throttling dù base table capacity nhìn có vẻ đủ. Theo dõi table và từng GSI riêng.

### 15.4. Hot partition và hot key

Replication không loại bỏ giới hạn partition throughput. Nếu mọi Region đều cập nhật cùng một hot item hoặc partition key:

- Write contention có thể tăng.
- Một item trở thành điểm nóng.
- MREC có nguy cơ LWW conflicts.
- MRSC có thể phát sinh ReplicatedWriteConflictException khi writes đồng thời.
- GSI partition key cũng có thể trở thành hot key.

Cân nhắc sharding, write distribution, item decomposition và home Region ownership.



## 12. Chọn write model để kiểm soát xung đột

Dù Global Tables là multi-active ở tầng dịch vụ, ứng dụng vẫn cần quy định **ai được ghi item nào và ở Region nào**. AWS Prescriptive Guidance mô tả ba write models chính.

### 6.1. Write to any Region — không có primary

Mọi Region đều có thể nhận writes vào cùng dữ liệu.

Phù hợp:

- **MRSC**, khi ứng dụng cần writes từ bất kỳ Region nào và chấp nhận xử lý retry khi có ReplicatedWriteConflictException.
- **MREC** nếu mọi writes idempotent hoặc xung đột chấp nhận được.

Ví dụ MREC phù hợp: người dùng thay đổi trạng thái bookmark thành một giá trị cụ thể, ví dụ latestPosition = 25. Nếu cùng một request được gửi lại, kết quả không cộng thêm một lần nữa.

Ví dụ MREC rủi ro: cập nhật số dư bằng phép cộng ADD 100. Nếu hai Region cùng cộng trên các bản sao chưa đồng bộ, LWW có thể khiến một cập nhật bị ghi đè.

### 6.2. Write to one Region — một primary do ứng dụng quản lý

Ứng dụng định tuyến **tất cả writes** tới một Region đang hoạt động. Các Region còn lại có thể phục vụ eventual reads và sẵn sàng trở thành primary khi failover.

Phù hợp với MREC khi:

- Cần conditional writes dựa trên dữ liệu mới nhất.
- Cần TransactWriteItems hoặc TransactGetItems.
- Nghiệp vụ có thao tác cộng/trừ, chuyển trạng thái hoặc cập nhật không idempotent.
- Muốn đơn giản hóa conflict resolution bằng cách tránh nhiều Region cùng ghi.

DynamoDB không có khái niệm primary Region toàn cục tự động. **Ứng dụng hoặc hệ thống điều phối** phải giữ trạng thái Region đang được phép ghi, cập nhật routing và ngăn split-brain khi chuyển primary.

Strongly consistent reads cần được thực hiện tại Region đang xử lý writes nếu ứng dụng cần thấy ngay những cập nhật đó.

### 6.3. Write to your Region — mỗi item có home Region

Chia dữ liệu thành các tập không chồng lấn, mỗi tập có một Region sở hữu quyền ghi.

Ví dụ:

- User có ID thuộc shard A được gán home Region Singapore.
- User thuộc shard B được gán home Region Tokyo.
- Mỗi item chỉ được cập nhật tại home Region, nhưng có thể đọc bản sao ở nơi khác theo consistency requirement.

Cách xác định home Region:

- **Intrinsic:** mã Region nằm trong partition key hoặc thuộc tính item.
- **Negotiated:** một dịch vụ điều phối cấp assignment có thời hạn.
- **Table-oriented:** tạo các global tables riêng theo nhóm Region/home Region.

Mô hình này giảm xung đột và có thể giữ write latency thấp cho người dùng toàn cầu. Nhưng khi failover, cần chuyển quyền sở hữu item và bảo đảm Region cũ không tiếp tục ghi.

### 6.4. So sánh ba write models

| Write model | MREC | MRSC | Khi nên dùng |
| --- | --- | --- | --- |
| **Write to any Region** | Chỉ phù hợp nếu writes idempotent hoặc chấp nhận LWW. | Phù hợp; vẫn phải retry write conflict. | Bookmark, trạng thái có thể ghi lại, metadata độc lập. |
| **Write to one Region** | Phù hợp với transactions, conditional writes và non-idempotent operations. | Có thể chọn để đơn giản routing, dù MRSC cho phép ghi ở nhiều Region. | Ledger, workflow trạng thái, dữ liệu cần single-writer. |
| **Write to your Region** | Phù hợp với dữ liệu phân vùng theo user/tenant. | Không cần thiết để tránh LWW, nhưng có thể dùng vì kiến trúc. | Hồ sơ người dùng, session hoặc dữ liệu có home Region. |

**Không nên chọn write to any Region cho mọi loại dữ liệu chỉ vì API cho phép.** Hãy phân loại từng aggregate: dữ liệu nào ghi lại được, dữ liệu nào cần single writer, dữ liệu nào đòi hỏi strong consistency.

## 13. MRSC: strong consistency xuyên các replica

**Multi-Region Strong Consistency (MRSC)** thay đổi semantics của global table:

1. Ứng dụng ghi vào một replica.
2. DynamoDB đồng bộ thay đổi tới ít nhất một Region khác trong kiến trúc trước khi trả write thành công.
3. Strongly consistent read ở bất kỳ replica nào trả phiên bản mới nhất.
4. Conditional writes được đánh giá trên phiên bản mới nhất.
5. Nếu cùng item đang được sửa ở Region khác, write có thể bị từ chối với **ReplicatedWriteConflictException**.

~~~mermaid
sequenceDiagram
    participant SG as Replica Singapore
    participant JP as Replica Tokyo
    participant EU as Replica witness/replica
    SG->>JP: Replicate write đồng bộ
    JP-->>SG: Quorum/ack theo cơ chế dịch vụ
    SG-->>APP: Write thành công
    APP->>JP: Strongly consistent read
    JP-->>APP: Phiên bản mới nhất
~~~

Sơ đồ là mô hình khái niệm, không mô tả chi tiết giao thức quorum nội bộ của DynamoDB.

### 7.1. Ba Region bắt buộc

MRSC cần **chính xác ba Regions** theo một trong hai topology:

- **Ba full replicas:** mỗi Region có một replica có thể đọc/ghi.
- **Hai replicas + một witness:** hai Region có table replicas, Region thứ ba chứa witness do DynamoDB quản lý.

Witness:

- Tham gia kiến trúc consistency/quorum.
- Không có endpoint table để ứng dụng đọc hoặc ghi.
- Không xuất hiện như một DynamoDB table do khách hàng quản lý trong account.
- Không phát sinh storage hoặc replicated write costs như full replica.
- Nằm ở Region khác với hai full replicas.

Không thể thêm một replica thứ tư vào MRSC đang tồn tại. Các thao tác thêm/xóa replica hoặc witness bị giới hạn chặt; cần thiết kế topology ngay từ đầu và đọc quy trình lifecycle AWS trước khi thay đổi.

### 7.2. Region support hiện hành

Tại thời điểm **20/11/2026**, AWS công bố MRSC hỗ trợ 15 Regions:

- **Bắc Mỹ:** US East (N. Virginia), US East (Ohio), US West (Oregon), Canada (Central).
- **Châu Âu:** Europe (Ireland), Europe (London), Europe (Paris), Europe (Frankfurt), Europe (Stockholm), Europe (Spain).
- **Châu Á - Thái Bình Dương:** Asia Pacific (Tokyo), Asia Pacific (Seoul), Asia Pacific (Osaka), Asia Pacific (Mumbai), Asia Pacific (Singapore).

Từ ngày **23/09/2026**, AWS mở rộng MRSC để cho phép chọn bất kỳ tổ hợp ba Regions nào trong danh sách 15 Regions hỗ trợ, bao gồm cấu hình xuyên Bắc Mỹ, châu Âu và châu Á - Thái Bình Dương. Khả năng hỗ trợ có thể tiếp tục thay đổi; luôn kiểm tra tài liệu AWS trước khi chọn Region.

### 7.3. Latency và quorum

MRSC cần trao đổi liên Region cho writes và strongly consistent reads. Vì vậy:

- Write latency cao hơn MREC local write.
- Strongly consistent read latency cũng tăng theo round-trip tới Region tham gia gần nhất.
- Eventually consistent reads không chịu phần latency cross-Region bổ sung theo semantics MRSC.
- Nếu không còn Region thứ hai khả dụng để thiết lập quorum, Region còn lại chỉ có thể phục vụ eventually consistent reads; writes và strongly consistent reads không thể tiếp tục như bình thường.

**RPO bằng 0 không có nghĩa RTO bằng 0.** Ứng dụng vẫn cần routing, compute stack dự phòng, DNS, authentication, quota và quy trình phục hồi.

### 7.4. ReplicatedWriteConflictException

Khi hai Region cố sửa cùng item gần như đồng thời, một write có thể bị từ chối tạm thời. Ứng dụng nên:

1. Nhận diện lỗi cụ thể, không retry mọi lỗi ValidationException/AccessDenied.
2. Dùng exponential backoff và jitter.
3. Giữ idempotency key cho operation nghiệp vụ.
4. Đọc lại trạng thái mới nhất nếu business logic cần quyết định dựa trên state.
5. Tính lại update dựa trên phiên bản mới rồi retry.
6. Có giới hạn attempts và trả lỗi có kiểm soát nếu vẫn xung đột.

Không retry mù một thao tác charge tiền hoặc tạo order nếu không có idempotency key; retry có thể tạo duplicate business effects.

### 7.5. Giới hạn MRSC quan trọng

| Tính năng | MRSC |
| --- | --- |
| Transactions (TransactWriteItems/TransactGetItems) | **Không hỗ trợ**. |
| TTL deletion | **Không hỗ trợ**. |
| Local Secondary Index (LSI) | **Không hỗ trợ**. |
| Global Secondary Index (GSI) | Có hỗ trợ; đọc GSI là eventually consistent. |
| DynamoDB Streams | Không dùng làm replication engine và không bật mặc định; có thể bật Streams riêng theo khả năng hỗ trợ. |
| Multi-account global table | **Không hỗ trợ**, chỉ same-account. |
| ReplicationLatency metric | Không phát metric này cho MRSC. |

### 7.6. Khi Region trở lại sau sự cố

MRSC tự catch up dữ liệu cho Region vừa phục hồi. Trong lúc Region đó chưa catch up, writes và strongly consistent reads vào replica đang catch up có thể trả lỗi; các Region còn hoạt động vẫn tiếp tục xử lý theo quorum.

Không cố chuyển sang MREC bằng cách chỉnh một setting trên table hiện hữu. Consistency mode không thể đổi sau khi tạo.

## 14. Thiết kế data model để tránh conflict

Global Tables không thay thế data modeling. Cách chia item quyết định phạm vi conflict.

### 8.1. Tách các thuộc tính được cập nhật độc lập

Nếu nhiều nhóm người dùng sửa những phần khác nhau của cùng một hồ sơ, có thể tách thành các items riêng:

~~~text
PK = USER#1001, SK = PROFILE
PK = USER#1001, SK = CONTACT
PK = USER#1001, SK = PREFERENCES
PK = USER#1001, SK = NOTIFICATION_SETTINGS
~~~

Nếu Singapore chỉ cập nhật CONTACT và Tokyo chỉ cập nhật PREFERENCES, chúng ghi vào các items khác nhau nên tránh xung đột LWW trên cùng item.

Trade-off: đọc hồ sơ đầy đủ có thể cần nhiều item/Query, và transaction nhiều item vẫn có semantics riêng giữa các Regions.

### 8.2. Ưu tiên absolute assignment hơn increment trong MREC

Ví dụ dễ retry/idempotent:

~~~text
SET latestViewedPosition = 125
SET notificationEnabled = true
SET deliveryStatus = "SHIPPED"
~~~

Ví dụ dễ gây conflict nếu cùng item được ghi từ nhiều Regions:

~~~text
ADD walletBalance : 100
ADD totalOrderCount : 1
SET inventory = inventory - 1
~~~

Trong MREC, các thao tác dựa trên giá trị hiện tại của replica local có thể ghi đè nhau khi hai Region cùng cập nhật. Nếu nghiệp vụ yêu cầu cộng/trừ chính xác:

- Dùng **single-writer Region** cho item/ledger.
- Tách event log/ledger với operation IDs duy nhất.
- Dùng MRSC nếu phù hợp và không cần transactions/TTL.
- Hoặc thiết kế một mô hình dữ liệu khác để giữ invariants.

### 8.3. Dùng unique deterministic keys cho append-only data

Một sự kiện mới có thể được lưu dưới khóa xác định từ operation ID:

~~~json
{
  "PK": "ORDER#10023",
  "SK": "EVENT#PAYMENT#TXN-2026-00091",
  "eventType": "PaymentCaptured",
  "operationId": "TXN-2026-00091",
  "amount": 125000,
  "currency": "VND",
  "originRegion": "ap-southeast-1"
}
~~~

Nếu cùng operation được retry từ nhiều Regions với cùng primary key, ứng dụng có thể dùng conditional PutItem để tránh tạo hai records trong một replica. Tuy nhiên trong MREC, condition được đánh giá tại replica nhận request và không thay thế một global transaction; thiết kế routing/idempotency vẫn quan trọng.

### 8.4. Optimistic concurrency bằng version nghiệp vụ

Một item có thể chứa:

~~~json
{
  "PK": "ORDER#10023",
  "status": "PAID",
  "version": 8,
  "updatedBy": "billing-service",
  "updatedAt": "2026-11-20T03:00:00Z"
}
~~~

Ứng dụng đọc version 8 và chỉ ghi khi version hiện tại vẫn là 8. Sau thành công, tăng lên version 9. Đây là **optimistic concurrency control (OCC)**.

- Với **MREC**, OCC chỉ bảo vệ dựa trên state replica local. Nếu hai Region cùng đọc version 8, cả hai có thể chấp nhận conditional write ở Region riêng trước khi replication tới. Dùng home Region/single writer hoặc cơ chế phối hợp khác để bảo đảm.
- Với **MRSC**, condition được đánh giá theo phiên bản mới nhất; concurrent writes có thể nhận ReplicatedWriteConflictException và cần retry/re-read.

### 8.5. Không dùng đồng hồ ứng dụng để mô phỏng LWW

Không tự thêm client timestamp rồi kết luận timestamp lớn nhất là đúng nhất. Đồng hồ máy khách có thể lệch, request có thể tới muộn và thứ tự nghiệp vụ không nhất thiết trùng wall-clock time.

Nếu cần audit hoặc thứ tự business, lưu **sequence/version do domain service quản lý**, operation ID và nguồn thay đổi.

## 15. Transactions, Streams và TTL trên Global Tables

### 9.1. Transactions trên MREC chỉ atomic trong Region nguồn

MREC hỗ trợ các DynamoDB transaction APIs theo giới hạn DynamoDB thông thường, nhưng transaction chỉ atomic tại Region nơi request được thực hiện.

Ví dụ một TransactWriteItems gồm:

1. Cập nhật Order status = PAID.
2. Ghi Payment record.
3. Trừ Inventory.

Ở Region nguồn, ba operations thành công hoặc thất bại như một transaction. Khi replicate sang Region khác, từng item được chuyển độc lập; một read ở Region nhận có thể quan sát một phần các cập nhật trước khi tất cả items đến.

Nếu ứng dụng yêu cầu remote Region không bao giờ thấy trạng thái dở dang, hãy dùng một **commit marker/version** hoặc một mô hình read projection chỉ công bố trạng thái khi đủ dữ liệu; không giả định transaction được replicate nguyên tử.

### 9.2. MRSC không hỗ trợ transaction APIs

MRSC không hỗ trợ **TransactWriteItems** và **TransactGetItems**. Nếu ứng dụng phụ thuộc giao dịch nhiều items, MRSC có thể không phù hợp dù cần strong consistency cho từng item.

Cân nhắc:
- MREC với single-writer Region cho transactional aggregate.
- Tách aggregate và dùng workflow/outbox/saga.
- Dùng một datastore khác nếu cần transaction mạnh xuyên nhiều records/Regions.

### 9.3. DynamoDB Streams với MREC

MREC dùng DynamoDB Streams làm cơ chế replication:

- Streams được bật mặc định trên các replicas và không thể tắt khi table là MREC global table.
- Mỗi replica có stream riêng.
- Stream có thể chứa thay đổi phát sinh tại Region đó và các thay đổi được replicate tới.
- Thứ tự thay đổi của cùng item được giữ theo semantics của Streams; thứ tự tương đối giữa các items khác nhau có thể khác giữa các replicas.
- Quá trình replication có thể gộp một số thay đổi gần nhau thành một replicated write; stream records giữa các replicas không nhất thiết giống hệt nhau.

Nếu chỉ muốn xử lý local-origin writes, có thể thêm thuộc tính **originRegion** vào item/event và lọc Stream records ở Lambda. Không chỉ dựa vào tên stream để phân biệt nguồn.

### 9.4. DynamoDB Streams với MRSC

MRSC không dùng Streams để replication, do đó Streams không bật mặc định. Có thể bật Streams trên replica theo hỗ trợ; records của MRSC replicas có cùng nội dung và thứ tự theo tài liệu.

Không được suy rằng Streams là replication bus cho MRSC.

### 9.5. TTL trên MREC

MREC hỗ trợ TTL:

- Cấu hình tên attribute TTL được đồng bộ giữa replicas.
- Khi TTL xóa item ở một Region, delete được replicate tới các Regions còn lại.
- TTL delete tại Region phát sinh không tiêu thụ write capacity theo cơ chế TTL.
- Các replicas nhận replicated delete vẫn tiêu thụ replicated write capacity.
- Nếu provisioned capacity thấp, lượng writes bình thường cộng TTL deletes có thể gây throttling.

### 9.6. TTL không có trên MRSC

MRSC không hỗ trợ TTL deletion. Nếu ứng dụng phụ thuộc expiry tự động, phải thiết kế cleanup bằng một cơ chế khác có idempotency và routing rõ ràng, hoặc chọn MREC.

## 16. Monitoring Global Tables

Giám sát Global Tables cần tách hai nhóm:

1. **Replication health:** dữ liệu có đang truyền giữa các Regions đúng tiến độ không?
2. **Table/application health:** từng replica có throttling, errors, latency hoặc capacity issues không?

### 16.1. ReplicationLatency trên MREC

CloudWatch metric **ReplicationLatency** được phát cho Global Tables MREC:

- Đơn vị: **milliseconds**.
- Theo dõi thời gian từ lúc item được ghi tại replica nguồn đến khi item xuất hiện tại replica nhận.
- Có dimension **TableName** và **ReceivingRegion**; metric được quan sát theo source Region và destination pair.
- Các thống kê hữu ích: **Average, Minimum, Maximum**.
- Không có SLA cho ReplicationLatency.

Giá trị thay đổi theo khoảng cách địa lý, workload, throughput và tình trạng replication. Không đặt ngưỡng cứng “luôn dưới 1 giây” cho mọi cặp Regions.

**MRSC không phát ReplicationLatency**, vì cơ chế đồng bộ khác MREC. Không dùng missing metric để kết luận MRSC replication đang lỗi.

### 16.2. Metrics DynamoDB cần theo dõi theo từng replica

| Metric | Ý nghĩa | Dùng để |
| --- | --- | --- |
| **ConsumedReadCapacityUnits** | Read capacity đã tiêu thụ. | Xem read workload theo table/index. |
| **ConsumedWriteCapacityUnits** | Write capacity đã tiêu thụ. | Phát hiện write pressure và replication load. |
| **ReadThrottleEvents** | Số read events bị throttled. | Phát hiện thiếu read capacity/quota/hot partitions. |
| **WriteThrottleEvents** | Số write events bị throttled. | Phát hiện write capacity hoặc hot key. |
| **ThrottledRequests** | Requests bị throttled theo dimension hỗ trợ. | Theo dõi tác động tới application. |
| **SuccessfulRequestLatency** | Latency request thành công theo operation. | So sánh latency giữa các Regions. |
| **SystemErrors** | Lỗi HTTP 500 từ DynamoDB/Streams. | Điều tra service errors và retry. |
| **UserErrors** | Lỗi do request/client theo định nghĩa metric. | Kiểm tra validation, access hoặc request patterns. |
| **ConditionalCheckFailedRequests** | Conditional writes thất bại do condition không thỏa. | Phân tích optimistic concurrency/business contention. |
| **OnlineIndexConsumedWriteCapacity** | Capacity dùng khi tạo/backfill index theo metric hỗ trợ. | Theo dõi tác động GSI. |

Một số metrics có dimensions cụ thể. Ví dụ **SystemErrors** cần cả **TableName** và **Operation**; alarm chỉ dùng TableName có thể không khớp datapoints. Kiểm tra CloudWatch metric dimensions trước khi tạo alarm.

### 16.3. CloudWatch Contributor Insights

Contributor Insights có thể giúp tìm partition keys/top contributors tạo tải lớn hoặc throttling. Với MRSC, AWS lưu ý Contributor Insights information chỉ được báo cáo tại Region nơi operation xảy ra. Không coi một Region's report là báo cáo tổng hợp toàn cầu.

### 16.4. Application-level metrics cần tự tạo

DynamoDB không biết một write có làm nghiệp vụ hợp lệ hay không. Ứng dụng nên phát metrics/logs cho:

- Region xử lý request và Region home của item.
- Business operation ID, aggregate version và idempotency outcome.
- Conditional check failures.
- ReplicatedWriteConflictException và số lần retry.
- Read-after-write fallback.
- Failover routing decision và thời điểm chuyển Region.
- Reconciliation backlog, quarantined records và duplicate operations.

Không ghi raw PII hoặc toàn bộ item payload vào CloudWatch logs chỉ để đo conflict.

### 16.5. CloudTrail và xung đột dữ liệu

CloudTrail hữu ích để audit **control-plane changes**, ví dụ UpdateTable, replica add/remove, resource policy và IAM changes. Nếu bật DynamoDB data events theo phạm vi phù hợp, có thể audit một số data-plane API calls.

Tuy nhiên, LWW conflict resolution không tạo một CloudTrail event riêng. Dùng application logs/business event log để theo dõi actor và business conflict.

## 17. AWS CLI chỉ đọc: kiểm tra Global Tables

Các lệnh dưới đây chỉ truy vấn trạng thái, không tạo replica, thay policy, ghi item hoặc thay đổi capacity. Dùng AWS profile/role được cấp quyền và đúng Region.

### 17.1. Xác nhận AWS account và Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Đừng nhầm AWS caller identity của CLI với application end user. Global Tables replica được truy cập bằng IAM principal của workload, không phải user Cognito.

### 17.2. Xem replica và phiên bản Current

~~~bash
aws dynamodb describe-table \
  --table-name orders \
  --region ap-southeast-1
~~~

Kiểm tra các trường:

- **TableStatus**.
- **GlobalTableVersion**.
- **Replicas[].RegionName**.
- **Replicas[].ReplicaStatus** và ReplicaStatusDescription.
- **GlobalTableWitnesses** nếu response có.
- BillingModeSummary, ProvisionedThroughput, GlobalSecondaryIndexes và StreamSpecification.

Chạy DescribeTable ở từng Region để xác minh replica status/ARN. Không chỉ xem source table rồi kết luận mọi replicas đều ACTIVE.

### 17.3. Kiểm tra Legacy version

~~~bash
aws dynamodb describe-global-table \
  --global-table-name orders \
  --region ap-southeast-1
~~~

Lệnh này phục vụ **Legacy 2017.11.29**. Nếu trả GlobalTableNotFoundException, table có thể không phải legacy global table; dùng DescribeTable để kiểm tra current version.

### 17.4. Xem auto scaling và TTL

~~~bash
aws dynamodb describe-table-replica-auto-scaling \
  --table-name orders \
  --region ap-southeast-1

aws dynamodb describe-time-to-live \
  --table-name orders \
  --region ap-southeast-1
~~~

Với MREC, TTL setting được đồng bộ. Với MRSC, TTL không được hỗ trợ. Kiểm tra từng Region và hiểu rằng replica-level read auto scaling có thể có cấu hình khác nhau.

### 17.5. Xem continuous backups/PITR

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name orders \
  --region ap-southeast-1
~~~

PITR/backup là cấu hình của replica tại Region đó; trong multi-account global tables, không mặc định settings này đồng bộ. Kiểm tra các replicas quan trọng và restore plan.

### 17.6. Đọc ReplicationLatency

Ví dụ lấy dữ liệu ReplicationLatency ở source Region Singapore cho replica nhận tại Tokyo:

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ReplicationLatency \
  --dimensions Name=TableName,Value=orders Name=ReceivingRegion,Value=ap-northeast-1 \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 60 \
  --statistics Average Maximum \
  --region ap-southeast-1
~~~

Lưu ý:

- Lệnh chỉ áp dụng cho MREC.
- Dimension **ReceivingRegion** là Region nhận dữ liệu; source Region được xác định bởi Region nơi truy vấn metric.
- Khoảng thời gian chỉ là ví dụ UTC; thay bằng incident window.
- Datapoints có thể không được sắp theo timestamp.
- Không có datapoint có thể do không có writes, sai dimension/Region hoặc metric chưa phát; không kết luận replication lỗi chỉ từ một lần query.

### 17.7. Đọc table throttling và system errors

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name WriteThrottleEvents \
  --dimensions Name=TableName,Value=orders \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --statistics Sum \
  --region ap-southeast-1
~~~

Đối với **SystemErrors**, phải dùng dimension pair TableName + Operation theo metric definition; không bỏ Operation rồi giả định alarm sẽ nhận dữ liệu.

### 17.8. Đọc CloudTrail control-plane changes

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateTable \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --region ap-southeast-1
~~~

Có thể tra các thay đổi replica/configuration trong khoảng sự cố. CloudTrail lookup không thay thế replication metrics hoặc application logs; event history/retention cũng có giới hạn theo CloudTrail.

### 17.9. Những lệnh thay đổi không chạy trong bài

Không thực thi các lệnh sau trong lab chỉ đọc:

~~~text
aws dynamodb update-table
aws dynamodb create-global-table
aws dynamodb update-global-table
aws dynamodb delete-table
aws dynamodb update-time-to-live
aws dynamodb update-continuous-backups
aws dynamodb put-resource-policy
aws dynamodb delete-resource-policy
aws dynamodb update-item
aws dynamodb put-item
~~~

Đây là các thao tác có thể thay đổi data, replication, backup, permissions hoặc cost. Thực hiện trong lab riêng hoặc qua IaC/change process được review.

## 18. Java SDK v2: gọi local replica và xử lý conditional write

Ứng dụng Java nên tạo DynamoDB client trỏ tới **Region của application stack**. Không hard-code một endpoint toàn cầu; Global Tables không có endpoint như vậy.

### 18.1. Tạo regional client

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class DynamoClients {
    private DynamoClients() {}

    public static DynamoDbClient forSingapore() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            .build();
    }
}
~~~

Ví dụ minh họa. Trong production, Region nên lấy từ deployment configuration/environment; IAM credentials lấy từ AWS SDK default credential provider chain (task role, execution role hoặc workload identity), không commit access keys.

### 18.2. Conditional update theo business version

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.DynamoDbException;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import java.util.Map;

public final class OrderStateRepository {
    private final DynamoDbClient dynamoDb;
    private final String tableName;

    public OrderStateRepository(DynamoDbClient dynamoDb, String tableName) {
        this.dynamoDb = dynamoDb;
        this.tableName = tableName;
    }

    public void markPaid(String orderId, long expectedVersion) {
        var request = UpdateItemRequest.builder()
            .tableName(tableName)
            .key(Map.of(
                "PK", AttributeValue.builder().s("ORDER#" + orderId).build(),
                "SK", AttributeValue.builder().s("STATE").build()
            ))
            .updateExpression("SET #status = :paid, #version = :next")
            .conditionExpression("#version = :expected")
            .expressionAttributeNames(Map.of(
                "#status", "status",
                "#version", "version"
            ))
            .expressionAttributeValues(Map.of(
                ":paid", AttributeValue.builder().s("PAID").build(),
                ":expected", AttributeValue.builder().n(Long.toString(expectedVersion)).build(),
                ":next", AttributeValue.builder().n(Long.toString(expectedVersion + 1)).build()
            ))
            .build();

        try {
            dynamoDb.updateItem(request);
        } catch (ConditionalCheckFailedException staleVersion) {
            throw new IllegalStateException(
                "Order state changed; reload and re-evaluate the operation",
                staleVersion
            );
        } catch (DynamoDbException serviceError) {
            if ("ReplicatedWriteConflictException".equals(serviceError.awsErrorDetails() == null
                    ? null : serviceError.awsErrorDetails().errorCode())) {
                throw new IllegalStateException(
                    "Concurrent write in another Region; retry with backoff",
                    serviceError
                );
            }
            throw serviceError;
        }
    }
}
~~~

Đây là ví dụ học tập, giả định table có partition key PK và sort key SK, cùng một item có thuộc tính version. Cần bổ sung logging an toàn, retry policy, timeout, idempotency và mapping lỗi HTTP theo ứng dụng.

### 18.3. Cảnh báo khi dùng ví dụ với MREC

Với MREC, conditional expression được đánh giá trên state của **replica nhận request**. Hai Region có thể cùng thấy version 8 và cùng chấp nhận update version 9 trước khi replication tới. Vì vậy đoạn code trên **không tự biến MREC thành global compare-and-swap**.

Dùng write-to-one-Region hoặc write-to-your-Region nếu cần OCC có ý nghĩa toàn cục trong MREC. Với MRSC, conditional writes đánh giá trên phiên bản mới nhất; vẫn cần xử lý ReplicatedWriteConflictException.

### 18.4. Retry policy

- Chỉ retry lỗi transient/retryable.
- Exponential backoff có jitter để nhiều clients không retry đồng loạt.
- Giới hạn số lần retry và tổng thời gian.
- Dùng operation ID/idempotency key cho business action.
- Sau conflict, đọc lại item/version và tính lại quyết định nghiệp vụ.
- Không retry một command tài chính nếu provider/ledger không hỗ trợ idempotency.

Không bắt tất cả DynamoDbException rồi retry; AccessDenied, ValidationException hoặc ConditionalCheckFailed có thể là lỗi cần xử lý khác.

## 19. Bài tập thực hành có đáp án gợi ý

### Bài tập 1 — Chọn consistency mode

**Đề:** Ứng dụng có khách hàng ở nhiều Regions, chỉ cập nhật trạng thái bookmark bằng cách ghi giá trị tuyệt đối. Chấp nhận trạng thái hội tụ sau một khoảng thời gian ngắn.

**Đáp án:** MREC có thể phù hợp với write-to-any-Region nếu writes idempotent. Cần đo ReplicationLatency và chấp nhận eventual reads. MRSC có thể cung cấp strong consistency nhưng tăng latency và giới hạn transactions/TTL/Region topology; không cần chọn nếu nghiệp vụ không yêu cầu.

### Bài tập 2 — Xung đột địa chỉ

**Đề:** Cùng một user item được sửa phoneNumber tại Singapore và preferredLanguage tại Tokyo gần như đồng thời. Sau replication, một thay đổi bị mất.

**Đáp án:** Đây là rủi ro LWW trên cùng item; DynamoDB không merge thuộc tính theo ý nghĩa nghiệp vụ. Tách CONTACT và PREFERENCES thành items riêng, hoặc gán home Region cho user, hoặc dùng MRSC nếu phù hợp.

### Bài tập 3 — Counter trong MREC

**Đề:** Hai Regions cùng thực hiện ADD inventorySold = 1 trên một item MREC.

**Đáp án:** Hai updates có thể xung đột và LWW có thể làm mất một increment. Chuyển thao tác về single writer/home Region, lưu append-only operation records có ID duy nhất hoặc dùng MRSC cho counter item nếu không cần transactions và chấp nhận các giới hạn.

### Bài tập 4 — Conditional write trong MREC

**Đề:** Hai Regions cùng đọc version = 8 và ghi condition version = 8, sau đó đều nhận thành công tại local replica.

**Đáp án:** Conditional write của MREC chỉ đánh giá state local. Nó không phải global compare-and-swap. Dùng single writer/home Region hoặc chọn MRSC khi cần condition đánh giá trên phiên bản mới nhất.

### Bài tập 5 — Chọn MRSC topology

**Đề:** Một hệ thống cần strong consistency, muốn có ba replicas tại Singapore, Tokyo và Ireland.

**Đáp án:** Tại thời điểm bài học, MRSC có hỗ trợ 15 Regions và cho phép cấu hình ba Regions xuyên châu lục theo thông báo AWS ngày 23/09/2026. Tuy nhiên, phải kiểm tra latency/quorum và business requirement; MRSC không hỗ trợ transactions, TTL, LSI hoặc multi-account.

### Bài tập 6 — MRSC write conflict

**Đề:** Java client nhận ReplicatedWriteConflictException khi hai request cập nhật cùng order item từ hai Regions.

**Đáp án:** Retry có exponential backoff/jitter, đọc lại item/version và tính lại business operation. Dùng operation ID để tránh tạo side effects trùng. Không retry vô hạn hoặc retry mọi DynamoDbException.

### Bài tập 7 — Transactions và replication

**Đề:** MREC transaction cập nhật Order, Payment và Inventory. Region nhận đã thấy Order = PAID nhưng chưa thấy Payment item.

**Đáp án:** Đây là semantics bình thường: transaction atomic trong Region nguồn nhưng các items replicate riêng lẻ. Dùng commit marker/version hoặc projection logic để chỉ công bố trạng thái sau khi đủ records; không giả định remote transaction atomic.

### Bài tập 8 — TTL và capacity

**Đề:** MREC table có nhiều TTL expirations; một replica provisioned mode bắt đầu WriteThrottleEvents tăng.

**Đáp án:** TTL delete ở Region nguồn không tiêu thụ write capacity, nhưng replicated deletes tiêu thụ ở các Regions nhận. Capacity cần đủ cho application writes + replicated TTL deletes. Xem auto scaling, workload và hot partitions.

### Bài tập 9 — Streams và origin Region

**Đề:** Lambda đọc DynamoDB Streams ở Singapore xử lý một event do Tokyo tạo và replicate về Singapore, làm side effect chạy hai lần.

**Đáp án:** Streams của MREC replicas có thể chứa thay đổi local và replicated. Gắn originRegion hoặc event ID nghiệp vụ, lọc local-origin events nếu kiến trúc yêu cầu, đồng thời idempotent consumer. Không coi mỗi stream record là một business operation duy nhất.

### Bài tập 10 — Multi-account global table

**Đề:** Ba business units ở ba accounts muốn có một replica mỗi account, mỗi account quản trị KMS và backup riêng.

**Đáp án:** Đánh giá multi-account Global Tables MREC; mỗi replica nằm ở account/Region riêng, cấp quyền replication service principal, bật settings replication và quản lý các non-synchronized settings như KMS/PITR/deletion protection từng account. MRSC không hỗ trợ multi-account.

### Bài tập 11 — ReplicationLatency tăng

**Đề:** CloudWatch ReplicationLatency Average tăng từ 400 ms lên 8 giây giữa Singapore và Tokyo.

**Đáp án:** Kiểm tra đúng source/receiving pair, workload, throttling, hot keys, replica status, service-linked role, resource policy, KMS và Region health. Không tự tăng capacity trước khi xác định nguyên nhân. Metric không có SLA nên cần so với freshness SLO và baseline.

### Bài tập 12 — Failover MREC

**Đề:** Singapore mất kết nối đột ngột; Tokyo tiếp tục ghi vào các order items. Khi Singapore phục hồi, một số pending writes cũ bị ghi đè theo LWW.

**Đáp án:** Đây là rủi ro của MREC khi Region offline. Dùng write routing/home Region, idempotent operation log, quarantine/reconciliation và business audit. Với dữ liệu cần RPO=0, đánh giá MRSC nếu các giới hạn phù hợp.

### Bài tập 13 — Kiểm tra Global Tables version

**Đề:** CLI DescribeTable trả GlobalTableVersion = 2019.11.21.

**Đáp án:** Đây là Current version. Dùng UpdateTable/DescribeTable và replica model hiện hành. Nếu table dùng Legacy 2017.11.29, quy trình quản lý dùng APIs riêng; không trộn hai bộ lệnh.

### Bài tập 14 — Witness không nhận được query

**Đề:** Team thử gọi GetItem vào Region witness của MRSC và không tìm thấy table endpoint.

**Đáp án:** Witness không phải full replica và không phục vụ reads/writes. Nó là thành phần quorum do DynamoDB quản lý. Ứng dụng chỉ gọi hai full replica Regions.

### Bài tập 15 — Lựa chọn cho inventory reservation

**Đề:** Cần atomically reserve inventory, tạo order và ghi payment intent; nhiều Regions có thể nhận request cùng lúc.

**Đáp án:** MRSC không hỗ trợ transaction APIs. MREC write-to-any-Region có nguy cơ conflict. Có thể dùng single-writer/home Region cho aggregate, transaction trong Region primary và workflow/outbox/saga cho cross-service operations. Nếu cần thay đổi mô hình dữ liệu, tách ledger/reservation records có idempotency keys.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** DynamoDB Global Tables là gì?  
**Đáp án:** Tính năng multi-Region, multi-active tự động replicate table data giữa các AWS Regions.

**Câu 2.** DynamoDB Global Tables có global endpoint không?  
**Đáp án:** Không. Ứng dụng gọi regional endpoint của replica local.

**Câu 3.** Global Tables current version là phiên bản nào?  
**Đáp án:** **2019.11.21**.

**Câu 4.** Nếu không chỉ định consistency mode khi tạo global table, mặc định là gì?  
**Đáp án:** **MREC**.

**Câu 5.** Có thể đổi MREC thành MRSC sau khi tạo không?  
**Đáp án:** Không. Consistency mode không thể đổi sau khi global table được tạo.

**Câu 6.** MREC replicate đồng bộ hay bất đồng bộ?  
**Đáp án:** Bất đồng bộ; replicas hội tụ sau replication lag.

**Câu 7.** MREC xử lý concurrent writes trên cùng item bằng cơ chế nào?  
**Đáp án:** **Last writer wins**, dựa trên timestamp nội bộ.

**Câu 8.** LWW có merge từng attribute theo business meaning không?  
**Đáp án:** Không. Ứng dụng phải tự thiết kế merge/versioning nếu cần.

**Câu 9.** ReplicationLatency có SLA cố định một giây không?  
**Đáp án:** Không. AWS không công bố SLA cho metric này.

**Câu 10.** MREC strong read ở Region B có luôn thấy write vừa xảy ra ở Region A không?  
**Đáp án:** Không. Read mạnh chỉ đảm bảo state local của replica B; cần replication hoàn tất.

**Câu 11.** Ba write models chính là gì?  
**Đáp án:** Write to any Region, write to one Region và write to your Region.

**Câu 12.** MREC write-to-any-Region phù hợp với loại writes nào?  
**Đáp án:** Writes idempotent hoặc trường hợp chấp nhận rủi ro conflict/LWW.

**Câu 13.** Khi nào nên dùng MREC single-writer Region?  
**Đáp án:** Khi cần transactions, conditional writes dựa trên state mới nhất hoặc thao tác non-idempotent.

**Câu 14.** MRSC đồng bộ write tới đâu trước khi trả thành công?  
**Đáp án:** Tới ít nhất một Region khác theo cơ chế dịch vụ.

**Câu 15.** MRSC cần chính xác bao nhiêu Regions?  
**Đáp án:** Ba Regions: ba replicas hoặc hai replicas cộng một witness.

**Câu 16.** Witness có phục vụ GetItem/PutItem không?  
**Đáp án:** Không. Witness không phải full replica và không có application read/write endpoint.

**Câu 17.** MRSC có hỗ trợ TransactWriteItems không?  
**Đáp án:** Không.

**Câu 18.** MRSC có hỗ trợ TTL deletion không?  
**Đáp án:** Không.

**Câu 19.** MRSC có hỗ trợ LSI không?  
**Đáp án:** Không. GSI được hỗ trợ nhưng reads trên GSI là eventually consistent.

**Câu 20.** MRSC concurrent write conflict có thể trả lỗi nào?  
**Đáp án:** **ReplicatedWriteConflictException**.

**Câu 21.** Multi-account Global Tables hỗ trợ consistency mode nào?  
**Đáp án:** Chỉ **MREC**.

**Câu 22.** MREC transactions atomic ở phạm vi nào?  
**Đáp án:** Chỉ Region nơi transaction được gọi; các items replicate riêng lẻ sang Region khác.

**Câu 23.** MREC Streams được bật mặc định vì sao?  
**Đáp án:** DynamoDB dùng Streams để đọc changes và replicate tới các replicas khác.

**Câu 24.** TTL delete replicated tới Region nhận có tiêu thụ write capacity không?  
**Đáp án:** Có, replicated deletes tiêu thụ write capacity ở các Regions nhận.

**Câu 25.** CloudWatch metric nào theo dõi replication lag của MREC?  
**Đáp án:** **ReplicationLatency**, đơn vị milliseconds, theo source/receiving Region pair.

**Câu 26.** MRSC có ReplicationLatency metric không?  
**Đáp án:** Không.

**Câu 27.** Global Tables có tự chuyển traffic khi Region lỗi không?  
**Đáp án:** Không. Ứng dụng cần routing/failover cho compute và request.

**Câu 28.** Tại sao không nên gọi remote DynamoDB endpoint khi Region local lỗi?  
**Đáp án:** Nên chuyển request sang application stack ở Region khỏe và gọi endpoint local tại đó, tránh cross-Region calls và dependencies còn nằm ở Region lỗi.

**Câu 29.** RPO bằng 0 của MRSC có đồng nghĩa RTO bằng 0 không?  
**Đáp án:** Không. Application routing, compute, DNS và dependency failover vẫn cần thời gian.

**Câu 30.** Vì sao cần idempotency key khi retry MRSC write?  
**Đáp án:** Để cùng business operation không tạo side effects hoặc giao dịch trùng khi request được gửi lại.

**Câu 31.** IAM role nào DynamoDB dùng cho cross-Region replication?  
**Đáp án:** **AWSServiceRoleForDynamoDBReplication** service-linked role.

**Câu 32.** Nếu resource policy deny service-linked role, điều gì có thể xảy ra?  
**Đáp án:** Replication có thể dừng và replica chuyển sang REPLICATION_NOT_AUTHORIZED.

**Câu 33.** Có thể chỉ replicate một subset items của cùng global table không?  
**Đáp án:** Không. Global Tables replicate toàn bộ items; cần tách tables nếu muốn replication scopes khác nhau.

**Câu 34.** Global Tables có thay thế backup/PITR không?  
**Đáp án:** Không. Replication cũng truyền deletes/updates sai; backup và recovery vẫn cần thiết.

**Câu 35.** Multi-account global table giúp ích gì?  
**Đáp án:** Tách ownership, IAM/KMS, governance, CloudTrail và cost allocation giữa các accounts.

## 21. Tổng kết kiến thức và tài liệu AWS tham khảo

Global Tables là nền tảng dữ liệu multi-Region mạnh, nhưng lựa chọn đúng phụ thuộc **consistency requirement, write model, data model và recovery design**.

### 26.1. Ghi nhớ hai consistency modes

- **MREC:** asynchronous replication, LWW conflict resolution, local latency thấp; cần idempotency, home Region/single writer khi nghiệp vụ nhạy với lost updates.
- **MRSC:** synchronous replication/quorum, strongly consistent reads/writes và RPO=0 cho successful writes; đổi lại latency cao hơn, ba Regions cố định, không transactions/TTL/LSI và chỉ same-account.

### 26.2. Checklist trước production

1. Xác định **Global Tables version**; ưu tiên 2019.11.21 Current.
2. Chọn **MREC hoặc MRSC** theo consistency, latency, transaction và TTL requirements.
3. Chọn **write model** cho từng aggregate; không để mọi Region tự ghi cùng item khi chưa phân tích conflict.
4. Thiết kế **business event ID, version, idempotency và audit**.
5. Kiểm tra semantics của **conditional writes, transactions, Streams, TTL, GSI/LSI**.
6. Xây application stack ở từng Region và gọi **local DynamoDB endpoint**.
7. Thiết kế routing, failover, Region evacuation, RPO/RTO và split-brain prevention.
8. Kiểm tra capacity/auto scaling, hot partitions, GSI write pressure và failover headroom.
9. Bảo vệ replication service-linked role, resource policies, SCP và KMS.
10. Với multi-account, xác minh từng account/Region, settings synchronization và non-synchronized settings.
11. Dashboard **ReplicationLatency** cho MREC cùng throttling/errors ở từng replica.
12. Có CloudTrail, business logs, reconciliation và runbooks cho replication issues/conflicts.
13. Test Region isolation, failover, replica catch-up và business correctness bằng AWS Fault Injection Service khi phù hợp.
14. Kiểm soát replicated write costs, storage, backups/PITR, indexes, Streams, CloudWatch và KMS.
15. Diễn tập khôi phục định kỳ và chứng minh ứng dụng đáp ứng SLO sau failover.

**Kết luận:** Global Tables tự động hóa replication, nhưng không tự quyết định dữ liệu nào là đúng khi nhiều Region cùng ghi. MREC yêu cầu ứng dụng quản lý xung đột và chấp nhận eventual consistency; MRSC cung cấp strong consistency cho từng item với latency và giới hạn topology rõ ràng. Khi kết hợp đúng write model, idempotency, routing, IAM/KMS, monitoring và DR tests, DynamoDB Global Tables có thể trở thành nền tảng đáng tin cậy cho ứng dụng AWS đa Region.

### Tài liệu AWS chính thức

- [DynamoDB Global Tables overview](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html) — mô hình same-account/multi-account và consistency modes.
- [How Global Tables work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html) — MREC, MRSC, transactions, TTL, Streams và replication.
- [Using DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html) — write modes, routing, failover, RPO/RTO và capacity.
- [Write modes with Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.writemodes.html) — write-to-any, single-primary và home Region.
- [Routing strategies](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.request-routing.html) — client, compute, Route 53 và Global Accelerator.
- [Evacuation processes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.prescriptive-guidance.evacuation.html) — chuyển workload khỏi live/offline Region.
- [Global Tables versions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_versions.html) — Current 2019.11.21 và Legacy 2017.11.29.
- [Global Tables security](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/globaltables-security.html) — service-linked roles, IAM và KMS.
- [Multi-account Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_MA_HowItWorks.html) — replication giữa accounts và settings.
- [Global Tables billing](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/global-tables-billing.html) — replicated write units và chi phí.
- [DynamoDB metrics and dimensions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html) — ReplicationLatency và metrics theo table/operation.
- [DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html) — strongly/eventually consistent reads.
- [AWS announcement — MRSC additional Regions, 23 September 2026](https://aws.amazon.com/about-aws/whats-new/2026/09/dynamodb-mrsc-additional-regions/) — 15 Regions và cấu hình xuyên châu lục.
- [DynamoDB global tables best practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/globaltables-bestpractices.html) — version, deletion protection và CloudFormation deployment.


## 22. Chi phí Global Tables

Global Tables tăng chi phí so với một table chỉ có một Region vì mỗi replica có storage, reads, replicated writes và các cấu hình phụ trợ riêng.

### 19.1. Các thành phần tính phí

| Thành phần | Cách tính cần xem |
| --- | --- |
| **Replicated writes** | rWRUs cho on-demand hoặc rWCUs cho provisioned; phát sinh tại các Regions chứa replica. |
| **Reads** | RRUs/RCUs theo request và consistency của read tại từng Region. |
| **Storage** | Dữ liệu được lưu tại mỗi replica Region. |
| **GSI writes/storage** | Index có capacity và storage usage riêng theo pricing DynamoDB. |
| **Backups/PITR** | Cấu hình backup/point-in-time recovery của từng replica theo Region. |
| **Streams** | Stream reads, Lambda consumers và downstream processing nếu ứng dụng sử dụng. |
| **CloudWatch** | Metrics, alarms, dashboards và custom metrics/logs bổ sung. |
| **KMS** | Customer managed keys, requests và key administration theo cấu hình. |
| **Replica bootstrap** | Khi thêm replica mới, cần xem chi phí khởi tạo/restore và usage phát sinh theo pricing hiện hành. |

### 19.2. Replicated write units

Với Global Tables current, replicated writes được tính theo **rWRU** ở on-demand hoặc **rWCU** ở provisioned mode. Các units này có mức giá tương ứng với write units của DynamoDB single-Region và phát sinh tại **mỗi Region chứa replica**.

Ví dụ minh họa:

- Một write 1 KB vào global table có hai replicas.
- Mỗi replica có thể chịu replicated write usage theo billing model.
- Tổng write cost phụ thuộc số replicas, kích thước item, operation và version global table.

Không chỉ tính writes do application gửi trực tiếp. Replication và TTL deletes có thể tạo write consumption ở Regions nhận dữ liệu.

### 19.3. Data transfer và witness

Theo tài liệu billing Global Tables hiện hành, DynamoDB **không tính cross-Region data transfer fees cho replication giữa các Regions** của global table. Tuy nhiên, application traffic, API calls, event pipelines hoặc các dịch vụ khác truyền dữ liệu cross-Region có thể có chi phí riêng.

Với MRSC dùng witness, witness không phát sinh storage hoặc replicated write unit costs như một full replica. Không nhầm witness với một Region có thể phục vụ application reads/writes.

### 19.4. Multi-account cost allocation

Trong multi-account global tables, mỗi account trả cho resources và requests sử dụng trên local replica của mình, bao gồm reads, writes, storage và data transfer liên quan. Đây là lợi ích phân bổ chi phí theo account; cần phối hợp tags/Cost Explorer/CUR để báo cáo theo team.

### 19.5. TTL và chi phí replicated delete

Với MREC:

- TTL deletion tại Region thực hiện delete không tiêu thụ write capacity theo cơ chế TTL.
- Replicated delete tới các Regions còn lại tiêu thụ replicated write units ở nơi nhận.
- Provisioned capacity quá thấp có thể bị throttling nếu replicated TTL deletes cộng application writes vượt capacity.

### 19.6. Cách dự toán

Ví dụ giả định:

- 2 triệu writes/ngày.
- Item trung bình 1,5 KB.
- 3 replica Regions.
- 10 triệu reads/ngày, phân bố giữa ba Regions.
- Có 2 GSIs và PITR bật ở từng replica.

Không thể nhân đơn giản “2 triệu writes × giá một write” rồi kết luận hóa đơn. Cần tính:

1. Kích thước item và số write units mỗi operation.
2. rWRU/rWCU theo số replica và global table version.
3. GSI update units.
4. Read consistency và read units.
5. Storage mỗi Region, backup/PITR.
6. TTL deletes, Streams consumers, Lambda và CloudWatch.
7. Region pricing, account ownership và các dịch vụ phụ trợ.

Dùng **AWS Pricing Calculator**, Cost Explorer và Cost and Usage Report (CUR) để đối chiếu usage thật. Giá thay đổi theo Region và thời điểm.

## 23. Dashboard và cảnh báo

Một dashboard Global Tables nên có một nhóm panels cho **mỗi replica Region** và các cặp source/receiving Regions.

### 20.1. Gợi ý dashboard

~~~mermaid
flowchart TB
    A["Regional write/read traffic"] --> D["Global Tables dashboard"]
    B["ReplicationLatency theo Region pair"] --> D
    C["Throttles / SystemErrors / UserErrors"] --> D
    E["Replica status / resource policies / KMS"] --> D
    F["Application conflicts / retries / idempotency"] --> D
    G["Failover routing / business reconciliation"] --> D
    D --> H["CloudWatch alarms + incident runbook"]
~~~

### 20.2. Alarm tham khảo

| Tín hiệu | Điều kiện minh họa | Hành động |
| --- | --- | --- |
| **ReplicationLatency Average** | Tăng vượt baseline trong nhiều periods. | Xác định source/receiving pair và workload. |
| **ReplicationLatency Maximum** | Spike kéo dài hoặc vượt freshness SLO. | Kiểm tra capacity, Region health, IAM/KMS. |
| **WriteThrottleEvents** | Tăng trên table hoặc GSI. | Kiểm tra provisioned capacity, auto scaling, hot keys. |
| **ReadThrottleEvents** | Tăng tại một replica. | Kiểm tra read traffic, GSI/partition hotness. |
| **SystemErrors** | Tăng theo TableName + Operation. | Kiểm tra service errors, retry và AWS Health. |
| **ConditionalCheckFailedRequests** | Tăng bất thường. | Kiểm tra contention/version conflicts và business behavior. |
| **ReplicaStatus** | Không còn ACTIVE hoặc có trạng thái lỗi. | Kiểm tra permissions, KMS, Region opt-in và replication SLR. |
| **Application retry rate** | Vượt baseline hoặc retry exhaustion. | Phân biệt transient conflict với lỗi cấu hình. |
| **Business reconciliation gap** | Số operations ở source khác destination. | Quarantine/replay/reconcile theo business IDs. |

Ngưỡng cụ thể phải lấy từ SLO, baseline và business tolerance. Không đặt một con số replication latency giống nhau cho mọi Region pair.

### 20.3. Missing data

- MREC không có writes trong một khoảng có thể không có ReplicationLatency datapoints.
- MRSC không phát ReplicationLatency.
- Metrics theo operation/dimension có thể chỉ xuất hiện khi có request.
- Region không có traffic không đồng nghĩa replica hỏng.

Dùng missing-data treatment phù hợp và kết hợp heartbeat/synthetic checks. Không biến missing ReplicationLatency thành alarm đỏ trên MRSC.

## 24. Runbook: replication lag, conflict và Region failover

### 21.1. ReplicationLatency tăng trên MREC

1. Xác định source Region và ReceivingRegion của metric.
2. Xem Average/Maximum theo cùng time window.
3. Kiểm tra writes/throughput, throttling và hot partitions ở source/receiving replicas.
4. Kiểm tra replica status, DynamoDB Streams settings và resource policies.
5. Kiểm tra service-linked role AWSServiceRoleForDynamoDBReplication.
6. Kiểm tra KMS key policy/disabled key.
7. Kiểm tra Region opt-in, account permissions và AWS Health events.
8. Nếu application cần freshness ngay, route reads tới Region vừa ghi hoặc dùng home Region policy.
9. Khi lag được xử lý, đối chiếu business data/version ở từng replica.

Không chỉ tăng capacity khi nguyên nhân thực là resource policy hoặc KMS access bị revoke.

### 21.2. Replica ở trạng thái REPLICATION_NOT_AUTHORIZED

Các bước điều tra:

- Xác định account/Region sở hữu replica.
- Xem resource-based policy và explicit Deny.
- Đảm bảo replication service principal/service-linked role có quyền theo AWS policy.
- Kiểm tra SCP, permissions boundary và policy condition.
- Khôi phục quyền KMS/resource policy phù hợp.
- Theo dõi trạng thái replica và replication latency sau khi sửa.

Với MREC, nếu trạng thái này kéo dài quá **20 giờ**, AWS cảnh báo replica có thể bị chuyển vĩnh viễn thành regional table. Multi-account replication có thêm notification/escalation khi lag do vấn đề khách hàng kéo dài; cần xử lý sớm, không chờ tới ngưỡng tự động disassociate.

### 21.3. ReplicationLatency tăng nhưng IAM/KMS đúng

Kiểm tra:

- Throughput và write bursts.
- Hot partition/key.
- Item size lớn hoặc GSI write pressure.
- Throttled requests ở source/receiving Regions.
- Regional service health.
- Streams/Lambda processing riêng của ứng dụng (nếu dùng) có bị nhầm với cơ chế replication của DynamoDB không.

### 21.4. MREC conflict hoặc lost update

1. Xác định item key và các Region đã ghi.
2. Đối chiếu operation IDs, business versions và source events.
3. Kiểm tra write model hiện tại: any Region, single primary hay home Region.
4. Xác định conflict có thể chấp nhận theo LWW không.
5. Nếu không, chuyển writes về single-writer/home Region hoặc tách item.
6. Khôi phục dữ liệu bị mất từ business event log/source of truth nếu có.
7. Bổ sung version checks, idempotency và metrics cho lần sau.

DynamoDB không cung cấp conflict record lịch sử để ứng dụng tự tải xuống; business audit cần được lưu ở lớp ứng dụng.

### 21.5. MRSC ReplicatedWriteConflictException

- Kiểm tra item key và request rate ở từng Region.
- Retry với exponential backoff/jitter.
- Đọc lại item nếu business decision cần state mới.
- Dùng idempotency key để retry không lặp side effects.
- Nếu xung đột liên tục, xem xét serialize writes theo item hoặc thay đổi data model.

Không tăng retry attempts vô hạn; điều đó có thể tạo load amplification và tăng latency.

### 21.6. Region evacuation

Với MREC single-primary:

1. Chặn writes vào Region đang active.
2. Xác minh replication đã bắt kịp bằng metric/checkpoints và thời gian chờ có kiểm soát.
3. Cập nhật global routing control.
4. Bật writes ở Region mới.
5. Giám sát duplicate/stale operations.
6. Giữ Region cũ ở read-only/isolated cho đến khi chắc chắn không còn split-brain.

Với MREC write-to-any-Region, cần quyết định có chấp nhận thiếu tạm thời/late writes không. Với MRSC, xác minh quorum và các Region còn lại đáp ứng consistency requirements trước khi chuyển traffic.

## 25. Tình huống kiến trúc thực tế

### Case A — User profile cho người dùng toàn cầu

**Yêu cầu:** User có thể cập nhật tên hiển thị, avatar preference và bookmark từ nhiều Regions. Nếu hai thiết bị cập nhật gần nhau, hệ thống chấp nhận trạng thái cuối cùng thắng.

**Lựa chọn:** MREC, write-to-any-Region cho các trường idempotent hoặc tách items theo nhóm thuộc tính. Dùng business version và audit event nếu cần hiển thị conflict cho người dùng.

**Tránh:** Dùng ADD trên một item chung để đếm hành động ở nhiều Regions nếu không chấp nhận lost update.

### Case B — Inventory và order reservation

**Yêu cầu:** Hai Region có thể cùng nhận đơn hàng cuối cùng của một sản phẩm; không được bán vượt tồn kho.

**Lựa chọn:** Không mặc định MREC write-to-any-Region với counter inventory. Có thể dùng single-writer/home Region cho inventory item, workflow reservation và conditional writes trong Region primary; hoặc xem MRSC nếu thao tác có thể mô hình hóa trên một item và không cần transaction API.

**Trade-off:** MRSC có strong consistency theo item nhưng không có TransactWriteItems/TTL. Nếu cần atomically reserve inventory + create order + payment across several items, phải thiết kế workflow/saga/ledger hoặc chọn mô hình phù hợp hơn.

### Case C — Payment ledger

**Yêu cầu:** Không được mất hoặc ghi trùng giao dịch tài chính; cần audit và reconciliation.

**Lựa chọn:** MREC single-writer Region cho ledger aggregate, append-only records với operation IDs duy nhất, idempotency ở payment provider, transaction trong primary Region và replication sang các Regions đọc. Có quy trình failover kiểm soát và reconcile event log.

**Tránh:** Hai Regions cùng thực hiện ADD balance trên một item MREC mà không có write coordination.

### Case D — Global user entitlement với yêu cầu đọc mạnh

**Yêu cầu:** Sau khi cấp quyền truy cập, bất kỳ Region nào cũng phải đọc thấy entitlement mới nhất.

**Lựa chọn:** Đánh giá MRSC vì strongly consistent reads trên các replica. Kiểm tra latency, quorum, ba Regions được hỗ trợ, không cần TTL/transactions/LSI và chấp nhận same-account constraint.

**Tránh:** Dùng GSI để đọc entitlement mới nhất vì GSI reads là eventually consistent.

### Case E — Multi-account business units

**Yêu cầu:** Orders, Billing và Analytics do các account khác nhau sở hữu, cần local replica và phân chia chi phí.

**Lựa chọn:** Multi-account Global Tables **MREC**, mỗi replica trong account/Region riêng; cấp resource policies cho replication service principal, bật settings replication, cấu hình KMS/backup/resource policies riêng từng account.

**Tránh:** Kỳ vọng multi-account MRSC hoặc per-replica override mọi table setting.

### Case F — Region outage trong MREC

**Yêu cầu:** Singapore bị outage đột ngột; Tokyo tiếp tục nhận writes.

**Lựa chọn:** Chuyển traffic tới Tokyo stack; đánh giá vùng dữ liệu có thể chưa propagate; dùng upstream event log/idempotency để reconcile khi Singapore phục hồi. Với dữ liệu không thể chấp nhận thiếu, quarantine những aggregate có trạng thái chưa xác minh.

**Tránh:** Tuyên bố RPO=0 chỉ vì Global Tables đang ACTIVE trước outage.

## 26. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Global Tables có một global endpoint duy nhất.” | Không có; ứng dụng gọi endpoint regional local. |
| “MREC replicate đồng bộ.” | MREC asynchronous, hội tụ sau replication lag. |
| “MRSC chỉ là MREC nhưng nhanh hơn.” | MRSC có synchronous replication/quorum và latency trade-off khác. |
| “MREC strong read ở Region B sẽ thấy ngay write từ Region A.” | Strong read chỉ đảm bảo local replica state; remote write cần replicate tới B trước. |
| “LWW merge các thuộc tính khác nhau.” | Conflict được giải quyết theo item/version; không có semantic field merge. |
| “LWW conflict xuất hiện trong CloudTrail.” | Không có dedicated LWW conflict event; ứng dụng cần audit riêng. |
| “Transactions MREC atomic trên mọi Regions.” | Atomic chỉ trong Region gọi transaction; remote replicas có thể thấy items theo từng bước replication. |
| “MRSC hỗ trợ TransactWriteItems.” | MRSC không hỗ trợ transaction APIs. |
| “MRSC có thể có bao nhiêu replica tùy ý.” | Chính xác ba Regions: 3 replicas hoặc 2 replicas + 1 witness. |
| “Witness là replica đọc/ghi.” | Witness không phục vụ application reads/writes. |
| “MRSC có TTL.” | MRSC không hỗ trợ TTL deletion. |
| “MRSC hỗ trợ LSI như MREC.” | MRSC không hỗ trợ LSI; GSI reads vẫn eventual. |
| “GSI read trong MRSC luôn strong.” | GSI reads là eventually consistent. |
| “Global Tables tự chọn Region gần user.” | Ứng dụng phải routing request. |
| “Failover chỉ cần đổi DynamoDB Region trong SDK.” | Cần chuyển application stack, routing, auth, dependencies và state. |
| “MREC Region offline vẫn bảo đảm mọi writes có ở replica khác.” | Writes chưa replicate có thể bị trễ cho tới khi Region trở lại. |
| “MREC không cần idempotency vì DynamoDB quản lý replication.” | Application retries/duplicate business operations vẫn cần idempotency. |
| “Một Region có thể lọc chỉ replicate một số items trong cùng global table.” | Global Tables replicate toàn bộ table items. |
| “TTL delete miễn phí ở mọi replicas.” | TTL source delete không tiêu thụ write capacity; replicated deletes tiêu thụ ở Regions nhận. |
| “ReplicationLatency có SLA 1 giây.” | Không có SLA; latency thay đổi theo workload/Region pair. |
| “Không có ReplicationLatency metric nghĩa MRSC hỏng.” | MRSC không phát metric này. |
| “Same-account và multi-account đều hỗ trợ MRSC.” | Multi-account chỉ hỗ trợ MREC. |
| “KMS key bị disable chỉ ảnh hưởng encryption lúc đọc.” | Có thể làm replication dừng và replica inaccessible. |
| “Replica ACTIVE nghĩa ứng dụng đã sẵn sàng DR.” | Compute, routing, IAM, capacity và recovery workflow vẫn cần test. |
| “Global Tables thay thế backup/PITR.” | Không; backup/restore và retention vẫn cần quản lý riêng. |


## 27. Checklist trước khi đưa Global Tables vào production

Dùng checklist này trong architecture review và diễn tập DR:

1. **Version:** xác nhận Global Tables version 2019.11.21 Current; nếu còn Legacy, có kế hoạch nâng cấp theo hướng dẫn AWS.
2. **Consistency mode:** ghi rõ lý do chọn MREC hay MRSC; kiểm tra transaction, TTL, LSI, GSI, multi-account và latency constraints.
3. **Write ownership:** định nghĩa write-to-any, single-primary hoặc home Region cho từng aggregate; không để split-brain khi failover.
4. **Conflict strategy:** có idempotency key, business version, optimistic concurrency và audit trail; xác định rõ khi nào LWW được chấp nhận.
5. **Regional routing:** mỗi application stack gọi endpoint DynamoDB local; có health checks, failover control và kiểm thử DNS/client caches.
6. **Data model:** tách items có vòng đời/cập nhật độc lập; kiểm tra hot keys, partition distribution, item size và GSI write amplification.
7. **Transactions/Streams/TTL:** kiểm thử semantics tại Region nguồn và Region nhận; không giả định transaction replicate nguyên tử.
8. **Capacity:** tính application writes cộng replicated writes, GSI/TTL traffic, burst và failover headroom cho từng replica.
9. **IAM/KMS:** bảo vệ AWSServiceRoleForDynamoDBReplication, resource policies, SCP và KMS key policies; không để explicit Deny chặn replication.
10. **Multi-account:** nếu dùng, xác minh mỗi replica account/Region, settings replication, resource policies và các settings phải cấu hình độc lập.
11. **Monitoring:** dashboard ReplicationLatency cho MREC, throttles/errors/status theo từng replica, cùng application conflict/retry/business metrics.
12. **Backups:** cấu hình PITR/backup riêng từng replica theo yêu cầu; kiểm thử restore và reconciliation.
13. **DR:** định nghĩa RPO/RTO thực tế; runbook live evacuation và offline Region; không tuyên bố MREC RPO=0.
14. **Testing:** kiểm thử duplicate requests, concurrent writes, Region isolation, catch-up, permission denial và failover bằng môi trường/lab phù hợp.
15. **Cost:** dự toán replicated writes ở mọi Regions, storage, reads, GSI, backups, Streams, CloudWatch, KMS và multi-account allocation.
16. **Operations:** có owner, incident severity, rollback, change control và diễn tập định kỳ.

Global Tables chỉ phát huy giá trị khi **consistency semantics, write ownership, routing và recovery process** được thiết kế đồng bộ. Hãy kiểm chứng các quyết định này bằng workload thực tế và diễn tập trước khi phụ thuộc vào kiến trúc multi-Region trong production.






