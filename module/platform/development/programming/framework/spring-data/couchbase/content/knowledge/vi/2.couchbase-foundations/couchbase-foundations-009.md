# Đặc điểm của Couchbase Server tự quản lý và Couchbase Capella

> **Chương:** Nền tảng Couchbase  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, transaction và API reactive để đáp ứng yêu cầu hiệu năng, tính nhất quán và vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Couchbase Server tự quản lý** (*self-managed*) với **Couchbase Capella** (*managed database service*) theo quyền kiểm soát và trách nhiệm vận hành.
2. Hiểu những thành phần **giống nhau ở tầng dữ liệu**: document, bucket/scope/collection, KV, SQL++, GSI, CAS, TTL và transaction.
3. Lựa chọn mô hình triển khai dựa trên tiêu chí kiểm soát hạ tầng, bảo mật, dữ liệu, vùng địa lý, SLO, nhân lực và tổng chi phí sở hữu.
4. Thiết kế kết nối **Spring Boot / Spring Data Couchbase** cho cả hai môi trường, đặc biệt là TLS, DNS, quyền database và quản lý secrets.
5. Phân biệt trách nhiệm của nhà cung cấp và của nhóm ứng dụng trong backup/restore, scaling, failover, observability và tối ưu truy vấn.
6. Lập kế hoạch chuyển từ môi trường tự quản lý lên Capella mà không nhầm việc **di chuyển dữ liệu** với việc **đổi connection string**.
7. Nhận ra các phụ thuộc phiên bản, cloud/region và gói dịch vụ, tránh giả định mọi tính năng đều giống nhau trong mọi môi trường.

## 2. Hai mô hình triển khai giải quyết cùng một nhu cầu dữ liệu

Couchbase Server là hệ quản trị cơ sở dữ liệu document với đường truy cập **key-value (KV)** và khả năng truy vấn JSON bằng **SQL++**. Ứng dụng Java có thể dùng Couchbase Java SDK hoặc Spring Data Couchbase để lưu entity, truy vấn, cập nhật có CAS và làm việc với TTL.

Hai lựa chọn vận hành thường gặp:

- **Couchbase Server tự quản lý:** tổ chức tự triển khai và vận hành Couchbase Server trên hạ tầng của mình hoặc hạ tầng thuê, chẳng hạn máy vật lý, máy ảo hoặc Kubernetes. Tổ chức chịu trách nhiệm nhiều hơn về cấu hình node, bảo mật mạng, nâng cấp, giám sát, dung lượng và quy trình khôi phục.
- **Couchbase Capella:** dịch vụ Couchbase được quản lý trên nền tảng cloud. Nhà cung cấp đảm nhiệm nhiều nhiệm vụ quản lý cơ sở hạ tầng và vận hành dịch vụ; người dùng cấu hình database deployment, truy cập, cấu trúc dữ liệu, workload và chính sách được dịch vụ hỗ trợ.

Đây là **hai mô hình trách nhiệm và vận hành**, không phải “một bên là SQL, một bên là NoSQL”. Cả hai đều phục vụ document, KV và SQL++ theo những tính năng/phiên bản được hỗ trợ.

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot / Spring Data Couchbase"]
    SDK["Couchbase Java SDK"]
    S["Couchbase Server tự quản lý"]
    C["Couchbase Capella"]
    OPS["Nhóm vận hành kiểm soát node, OS, mạng, nâng cấp"]
    MNG["Dịch vụ quản lý hạ tầng và nhiều tác vụ nền"]
    A --> SDK
    SDK --> S
    SDK --> C
    S --> OPS
    C --> MNG
~~~

**Điểm cốt lõi:** ứng dụng nhìn thấy API dữ liệu gần tương tự, nhưng **quy trình cấp tài nguyên, kết nối, quyền truy cập và trách nhiệm xử lý sự cố** có thể rất khác.

## 3. Bảng so sánh tổng quan

| Khía cạnh | Couchbase Server tự quản lý | Couchbase Capella |
|---|---|---|
| **Vị trí chạy** | Do tổ chức lựa chọn: on-premises hoặc cloud/VM/container theo hỗ trợ | Trên hạ tầng cloud theo khu vực, nhà cung cấp và tùy chọn dịch vụ khả dụng |
| **Quản lý hệ điều hành/node** | Nhóm vận hành chủ động, phụ trách nhiều việc | Nhà cung cấp quản lý phần hạ tầng dịch vụ |
| **Tạo và mở rộng cluster** | Tự thiết kế topology, cấp node, cấu hình service và rebalance | Qua console/API/quy trình dịch vụ; mức tự động phụ thuộc loại deployment/gói |
| **Nâng cấp, vá lỗi DB** | Tổ chức lên kế hoạch, kiểm thử và triển khai | Nhà cung cấp điều phối nhiều tác vụ, vẫn cần đánh giá tương thích và lịch thay đổi |
| **Mạng** | Tự cấu hình DNS, firewall, TLS, routing, private network | Cấu hình các phương thức truy cập được dịch vụ hỗ trợ như allowlist/private connectivity |
| **Database RBAC** | Tổ chức tạo và quản lý quyền | Vẫn phải cấp quyền database phù hợp cho ứng dụng |
| **Backup/restore** | Tự tổ chức công cụ, lịch, lưu trữ và diễn tập | Có khả năng quản lý backup theo cấu hình/tier; khách hàng vẫn chọn policy và kiểm chứng restore |
| **Monitoring** | Tự kết hợp công cụ Couchbase và hệ thống giám sát hạ tầng | Có dashboard/metric tích hợp và khả năng xuất telemetry tùy dịch vụ |
| **Kiểm soát OS/file system** | Cao, tùy quyền hạ tầng của tổ chức | Thường không có quyền truy cập trực tiếp vào host/OS của database managed |
| **Chi phí** | Hạ tầng, bản quyền/hỗ trợ, vận hành, dự phòng, backup | Phí dịch vụ/cloud theo cấu hình/tiêu thụ và các khoản liên quan |
| **Phù hợp** | Cần kiểm soát sâu hoặc yêu cầu hạ tầng riêng | Muốn giảm công việc vận hành cơ sở dữ liệu thường nhật |

Bảng mang tính **định hướng**, không phải cam kết tính năng hoặc SLA. Những chi tiết như cloud nào, vùng nào, private endpoint, loại node, retention backup hay autoscaling phải kiểm tra theo phiên bản và dịch vụ đang sử dụng.

## 4. Tầng dữ liệu giữ nguyên những khái niệm nào?

Dù triển khai theo cách nào, ứng dụng vẫn phải hiểu **mô hình document Couchbase**:

~~~text
Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   │   └── Document ID: tenant::42::order::1001
│   └── Collection: payments
└── Scope: catalog
    └── Collection: products
~~~

Ví dụ body JSON của một đơn:

~~~json
{
  "tenantId": "42",
  "status": "PAID",
  "total": 1490000,
  "currency": "VND",
  "schemaVersion": 2,
  "createdAt": "2026-11-25T02:00:00Z"
}
~~~

Các nguyên tắc chính vẫn áp dụng:

1. **KV theo ID:** sử dụng đường Data Service, thường không cần Query/Index Service để đọc một document đã biết khóa.
2. **SQL++ theo trường JSON:** cần đánh giá chỉ mục GSI, kế hoạch truy vấn và scan consistency.
3. **CAS:** hỗ trợ optimistic concurrency control khi cập nhật một document.
4. **TTL/expiry:** quản lý vòng đời document; không tự đồng nghĩa với trường `expiresAt` trong JSON.
5. **Transaction:** xử lý nhiều document như đơn vị giao dịch theo điều kiện của server/SDK.
6. **Reactive API:** thay đổi phong cách lập trình và quản lý I/O đồng thời, không thay đổi semantics lưu trữ.
7. **Replica/durability:** phải thiết kế theo RPO/RTO và yêu cầu nghiệp vụ; không được xem là bảo đảm tuyệt đối trong mọi sự cố.

**Không có chuyện chuyển sang Capella thì SQL++ tự có index hoàn hảo hoặc CAS không còn cần thiết.** Công việc thiết kế mô hình dữ liệu và logic ứng dụng vẫn là trách nhiệm của đội phát triển.

## 5. Ranh giới trách nhiệm: managed không có nghĩa là “không phải vận hành”

Khác biệt quan trọng nhất là **ai chịu trách nhiệm** đối với từng lớp.

| Công việc | Self-managed: nhóm vận hành | Capella: nhà cung cấp/dịch vụ | Capella: nhóm ứng dụng vẫn phải làm |
|---|---|---|---|
| Cấp máy/node và thay phần cứng | Chủ động chịu trách nhiệm | Phần lớn do dịch vụ quản lý | Lựa chọn cấu hình/capacity phù hợp |
| Cài Couchbase, vá hệ thống, thay node | Chủ động lập kế hoạch/thực hiện | Nhiều bước do dịch vụ quản lý | Theo dõi lịch thay đổi và kiểm thử compatibility |
| Cấu trúc bucket/scope/collection | Tạo và phân quyền | Cung cấp công cụ/API | Thiết kế schema, đặt tên, RBAC |
| Index SQL++ và query plan | Tạo và tối ưu | Cung cấp Query/Index Service | Tạo GSI, đo query, tối ưu EXPLAIN |
| Users và secrets của app | Cấp và quản lý | Cung cấp cơ chế cấp quyền database | Least privilege, rotation, không lộ secrets |
| Security networking | Tự thiết lập firewall/TLS | Có phương thức network tích hợp | Cấu hình allowed access, private routing, client TLS |
| Backup policy và kiểm thử restore | Tự xây quy trình | Có tiện ích/automation theo gói | Chọn lịch, retention, thử restore, đo RPO/RTO |
| Logging/incident | Giám sát cả host và database | Hỗ trợ và hiển thị trạng thái dịch vụ | Quan sát từ client, retry, business metrics, escalation |
| Đúng dữ liệu nghiệp vụ | Thuộc ứng dụng | Không thể tự hiểu mọi business invariant | Validation, CAS, transaction, idempotency |

Cách đọc bảng: trên Capella, **nhiều tác vụ hạ tầng được chuyển sang nhà cung cấp**, nhưng trách nhiệm về dữ liệu, bảo mật truy cập, hiệu năng câu truy vấn và logic nghiệp vụ **không biến mất**.

### 5.1. Ví dụ “managed nhưng query vẫn chậm”

Ứng dụng dùng:

~~~sql
SELECT META(o).id AS id, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Nếu không có index phục vụ điều kiện và thứ tự, truy vấn có thể chậm hoặc không có execution plan phù hợp. Capella có thể quản lý máy Index Service, nhưng **người thiết kế ứng dụng vẫn phải tạo index** theo workload:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId, status, createdAt DESC
);
~~~

Sau đó kiểm tra `EXPLAIN` và đo hiệu năng trên dữ liệu thực. Với self-managed, quy trình cũng tương tự; điểm khác là nhóm vận hành còn phải quản lý tài nguyên Index node trực tiếp hơn.

## 6. Kiến trúc triển khai tự quản lý

Một môi trường self-managed có thể gồm nhiều node Couchbase với các service được bố trí theo nhu cầu:

~~~mermaid
flowchart LR
    APP["Ứng dụng Spring Boot"]
    LB["DNS / mạng ứng dụng"]
    N1["Node A<br/>Data Service"]
    N2["Node B<br/>Data + Index"]
    N3["Node C<br/>Query + Index"]
    OBS["Monitoring / Backup / Ops"]
    APP --> LB
    LB --> N1
    LB --> N2
    LB --> N3
    OBS --> N1
    OBS --> N2
    OBS --> N3
~~~

Sơ đồ chỉ minh họa việc các service có thể được bố trí trên những node khác nhau, **không phải khuyến nghị topology production cố định**. Độ sẵn sàng của từng service cần xét tài nguyên, replica và failure domain.

### 6.1. Những quyết định nhóm vận hành phải đưa ra

- **Hạ tầng:** bare metal, VM hay container/Kubernetes, theo nền tảng được hỗ trợ.
- **OS, lưu trữ và I/O:** đủ RAM, dung lượng đĩa, IOPS, network, file system phù hợp.
- **Dịch vụ trên node:** Data, Query, Index và các service khác theo workload.
- **Replica/failover:** số Data replica, index replica, quy trình graceful/hard failover.
- **Network/TLS:** DNS, certificates, firewall, routing giữa SDK và các node.
- **Vận hành:** backup, restore, nâng cấp, rolling maintenance, rebalance, alerting.
- **Bảo mật:** database RBAC, service accounts, access audit, secrets rotation.
- **SLO:** theo dõi KV p95/p99, Query/Index Service và hiệu năng khi mất một node.

### 6.2. Tự quản lý không bắt buộc “on-premises”

Có thể chạy Couchbase Server tự quản lý trên cloud VM hoặc một nền tảng Kubernetes được hỗ trợ. Khi đó tổ chức vẫn chịu nhiều trách nhiệm về DB node/cluster và cấu hình Couchbase, ngay cả khi cloud provider quản lý hạ tầng cơ bản.

Nếu sử dụng **Couchbase Autonomous Operator** trên Kubernetes, có thể tự động hóa một số công việc quản trị, nhưng nó **không đồng nghĩa Capella**. Cần vận hành Kubernetes, Operator, storage, certificate, topology và kiểm soát version.

### 6.3. Tính linh hoạt đi kèm chi phí vận hành

Self-managed cho phép kiểm soát chi tiết hơn ở cấp host, topology và tích hợp mạng riêng, hữu ích khi có yêu cầu đặc thù. Đổi lại, nhóm cần kỹ năng chuyên môn để xử lý rebalance, disk pressure, node failure, index build, backup validation và upgrade.

**Đừng chỉ so sánh chi phí máy chủ với giá dịch vụ Capella.** Thời gian nhân sự, rủi ro downtime, năng lực trực sự cố và chi phí duy trì môi trường DR cũng là một phần của TCO.

## 7. Kiến trúc dịch vụ Couchbase Capella

Capella là một cách dùng Couchbase dưới dạng dịch vụ quản lý. Ứng dụng chọn điểm kết nối của **database deployment**, dùng người dùng database và network policy phù hợp, rồi làm việc với bucket/scope/collection như trong mô hình Couchbase.

~~~mermaid
flowchart TD
    APP["Ứng dụng Spring Boot<br/>Cloud VPC / hệ thống ứng dụng"]
    DNS["DNS + TLS + chính sách network"]
    CP["Capella management plane<br/>Console / API"]
    DB["Capella database deployment"]
    DATA["Data Service / KV"]
    QUERY["Query Service / SQL++"]
    INDEX["Index Service / GSI"]
    APP --> DNS
    DNS --> DB
    CP --> DB
    DB --> DATA
    DB --> QUERY
    DB --> INDEX
~~~

Ở Capella, nhà cung cấp quản lý nhiều thành phần của nền tảng database. Nhưng vẫn cần:

- Chọn cloud/region và kích thước/cấu hình database theo dịch vụ hỗ trợ.
- Thiết lập allowed network access hoặc private connectivity khi khả dụng.
- Tạo database credentials với quyền cụ thể.
- Tạo bucket, scope, collection và index.
- Cấu hình backup policy, retention và kiểm thử restore.
- Theo dõi hiệu năng, cảnh báo, năng lực và chi phí.
- Quản lý tương thích khi nâng phiên bản hoặc đổi topology/service tier.

### 7.1. Control plane khác data plane

**Control plane** là giao diện/API quản lý tài nguyên, người dùng/quyền, cấu hình và hoạt động deployment. **Data plane** là nơi client SDK giao tiếp để chạy KV, SQL++ và các thao tác dữ liệu.

Đừng nhầm **tài khoản đăng nhập console Capella** với **database user** được Spring Boot dùng để kết nối. Hai loại quyền được quản lý theo cơ chế khác nhau; ứng dụng production nên dùng credential database chuyên dụng với đặc quyền tối thiểu, không dùng tài khoản quản trị cá nhân.

### 7.2. Cấu hình dịch vụ phụ thuộc môi trường

Các nhãn trong console, loại tier, cách định cỡ/tính phí, khả năng chọn private endpoint, backup options và phạm vi tự động hóa có thể thay đổi theo thời điểm, phiên bản, cloud và gói dịch vụ. Khi thiết kế kiến trúc, hãy xác minh bằng **khả năng thực tế của deployment** chứ không mặc định mọi tính năng được bật sẵn.

## 8. Kết nối mạng: khác biệt dễ gây lỗi nhất

### 8.1. Connection string không phải URL HTTP

Couchbase Java SDK dùng connection string riêng cho giao thức Couchbase. Thường gặp:

~~~text
couchbase://db.internal.example
couchbases://cb.example-managed.cloud.couchbase.com
~~~

Hai hostname trên là **ví dụ không phải endpoint dùng được**. `couchbase://` minh họa kết nối không bật TLS theo scheme; `couchbases://` dùng kết nối bảo mật TLS. Cả hai dạng có thể áp dụng theo khả năng/cấu hình môi trường; trong production nên ưu tiên đường kết nối có TLS và authentication được quản trị phù hợp.

Không chuyển `couchbases://` thành `https://` rồi dùng `RestTemplate` để truy cập KV: đó không phải giao thức của Couchbase Java SDK.

### 8.2. Self-managed: toàn bộ node/port phải truy cập được

Ứng dụng có thể bắt đầu bằng một **seed hostname**, sau đó SDK khám phá thông tin cluster và giao tiếp với những Data/Query node tương ứng. Nếu có thể tới seed nhưng không tới các node được cluster quảng bá, ứng dụng vẫn có thể timeout.

Danh sách kiểm tra self-managed:

1. DNS của seed và các node khác phân giải đúng từ mạng ứng dụng.
2. Firewall/security group cho phép các cổng/dịch vụ Couchbase cần dùng theo phương thức TLS và topology thực tế.
3. Node cung cấp địa chỉ mà client có thể kết nối, kể cả qua NAT hoặc network khác nhau.
4. Chứng chỉ server khớp hostname và CA tin cậy của JVM/client.
5. Không chỉ mở đường management UI rồi cho rằng SDK KV/SQL++ sẽ kết nối được.

### 8.3. Capella: kiểm soát nguồn truy cập và TLS

Với Capella, client cần truy cập vào endpoint database theo **network access policy** mà deployment hỗ trợ. Tùy cấu hình, phương thức có thể gồm allowed public IP hoặc private connectivity trên cloud/tier phù hợp.

Thường cần xác minh:

- Egress IP thực tế của ứng dụng có được cho phép không nếu dùng public network access.
- DNS trả về địa chỉ đúng với mô hình kết nối đang triển khai.
- Security group/firewall outbound và routing cho phép client tới endpoint cần thiết.
- TLS trust chain và hostname verification được cấu hình đúng.
- Trong cloud/Kubernetes, pod/node có thể ra Internet bằng NAT IP khác IP máy lập trình viên.
- Nếu sử dụng private networking, route/DNS private và endpoint phải phù hợp cloud/region/project.

**Không tắt certificate verification để “kết nối cho xong”.** Nếu gặp lỗi TLS, cần kiểm tra CA chain, hostname, JDK truststore, SDK version và hướng dẫn kết nối của chính deployment.

### 8.4. Vấn đề IP động trong môi trường phát triển

Nếu laptop có IP thay đổi và Capella dùng allowlist IP, kết nối có thể hôm nay được, ngày mai timeout. Với production, nên chọn chính sách networking ổn định và giới hạn phạm vi truy cập, không mở truy cập từ mọi địa chỉ để tránh cấu hình đúng mạng.

## 9. Xác thực và phân quyền: hai lớp phải tách riêng

### 9.1. Quyền quản trị nền tảng

Ở self-managed, người quản trị có thể kiểm soát cluster/server theo cơ chế Couchbase và hạ tầng. Ở Capella, console/API có mô hình quản lý tổ chức, dự án hoặc database deployment tùy phiên bản.

**Quyền quản trị Capella** không tự đồng nghĩa quyền dữ liệu của SDK trong một bucket. Ngược lại, database user đủ quyền KV không nhất thiết có quyền thay đổi billing hoặc network policy trên control plane.

### 9.2. Database RBAC cho ứng dụng

Ứng dụng chỉ cần những đặc quyền cần thiết:

| Nhóm chức năng | Quyền cần xem xét | Không nên cấp mặc định |
|---|---|---|
| Đọc order bằng ID | Quyền đọc dữ liệu trong collection đích | Quyền admin toàn cluster |
| Tạo/cập nhật order | Quyền ghi KV vào collection đích | Quyền quản lý người dùng/backup |
| Truy vấn SQL++ | Quyền truy vấn/đọc và truy cập keyspace/index theo mô hình RBAC | Quyền tạo/xóa index nếu chỉ chạy query |
| Migration/index setup | Quyền quản trị schema/index cần thiết | Dùng cùng tài khoản production API |
| Monitoring | Quyền xem metric/trạng thái phù hợp | Mật khẩu database có quyền ghi toàn hệ thống |

Tên role/privilege cụ thể phụ thuộc phiên bản Couchbase và phạm vi RBAC. Nên có **tài khoản runtime**, **tài khoản migration** và **tài khoản vận hành** tách biệt.

### 9.3. Nguyên tắc quản lý secrets

- Lưu credential trong secret manager, vault hoặc biến môi trường được bảo vệ; không commit vào Git.
- Không ghi password, connection secret hoặc token trong application log.
- Lên kế hoạch rotation và thử nghiệm ứng dụng reconnect sau rotation.
- Dùng TLS và chính sách CA/hostname verification thay vì bỏ qua lỗi xác thực.
- Kiểm tra quyền ở **tầng ứng dụng** đối với document của tenant, dù đã có prefix tenant trong ID.

## 10. Cấu hình Spring Boot cho hai môi trường

Điểm thuận lợi là **entity/repository có thể giữ nguyên** khi chuyển deployment, nếu version và tính năng tương thích. Thường chỉ thay cấu hình connection, secrets, bucket và network setup.

Ví dụ `application.yml` dùng biến môi trường:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${CB_BUCKET}"
~~~

Ví dụ này minh họa các property phổ biến trong Spring Boot hiện đại; vị trí property và khả năng hỗ trợ có thể khác theo phiên bản. Không ghi giá trị secret thật vào file cấu hình.

### 10.1. Environment tự quản lý

~~~text
CB_CONNECTION_STRING=couchbases://db.internal.example
CB_USERNAME=order-service
CB_PASSWORD=<được secret manager cung cấp>
CB_BUCKET=commerce
~~~

Nếu môi trường dev chạy Couchbase không TLS trên máy cục bộ, đôi khi có thể dùng `couchbase://localhost`. Không sao chép cấu hình không TLS của lab sang production khi chính sách yêu cầu TLS.

### 10.2. Environment Capella

~~~text
CB_CONNECTION_STRING=couchbases://<hostname-từ-Capella>
CB_USERNAME=order-service
CB_PASSWORD=<được secret manager cung cấp>
CB_BUCKET=commerce
~~~

Hostname cần lấy từ **thông tin kết nối database thật**, không tự dựng bằng tên organization/project. Trước khi ứng dụng kết nối, hãy cấu hình network access và database user đúng phạm vi, sau đó kiểm tra TLS/DNS.

### 10.3. Java entity mapping không chọn hạ tầng

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String status;
    private Long total;

    // Constructor, getter/setter hoặc builder được lược bớt.
}
~~~

Các annotation mô tả cách mapping dữ liệu:

- `@Document` đánh dấu entity document.
- `@Scope` và `@Collection` xác định keyspace.
- `@Id` ánh xạ document ID.
- `@Version` gắn với cơ chế CAS optimistic locking theo Spring Data version.

Không annotation nào “biết” Couchbase Server đang trên VM hay Capella. Việc chọn môi trường được thực hiện qua kết nối/configuration chứ không phải thay domain model.

### 10.4. Repository dùng lại giữa hai deployment

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

~~~java
// Truy cập KV theo ID.
OrderDocument order = orderRepository
        .findById("tenant::42::order::1001")
        .orElseThrow();

// Truy vấn theo field thường sử dụng SQL++ và GSI.
List<OrderDocument> paidOrders =
        orderRepository.findByTenantIdAndStatus("42", "PAID");
~~~

Cả hai môi trường đều cần collection `commerce.sales.orders` và index SQL++ tương ứng. Nếu Capella tạo database mới rỗng, đổi connection string **không tự tạo document, index, user và permission**.

### 10.5. CouchbaseTemplate và reactive

`CouchbaseTemplate` hoặc `ReactiveCouchbaseRepository` dựa trên cùng cluster connection và nguyên tắc keyspace/data service. API reactive có thể tăng khả năng tổ chức pipeline bất đồng bộ, nhưng không tự cải thiện network latency khi endpoint ở xa vùng triển khai.

Khi di chuyển từ local/self-managed sang Capella, hãy đo:

- RTT mạng giữa ứng dụng và database.
- Số lần round-trip của workflow có nhiều KV/SQL++ calls.
- Concurrency và connection reuse của SDK.
- Cấu hình timeout/độ bền ghi, scan consistency và retry.
- Tác động của cluster sizing và Query/Index Service.

**Không tạo cluster connection mới cho mỗi HTTP request.** Dùng lifecycle do Spring Boot/SDK quản lý và tái sử dụng connection.

## 11. SQL++, chỉ mục và query plan giữa hai môi trường

Một query SQL++ hoạt động giống về mục đích:

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status;
~~~

Nó thường cần GSI phù hợp:

~~~sql
CREATE INDEX ix_orders_tenant_status
ON `commerce`.`sales`.`orders`(
    tenantId, status
);
~~~

Cần phân biệt ba lớp khi thấy truy vấn chậm:

1. **Thiết kế query/index:** field, predicate, covering index, Fetch/Sort.
2. **Sức mạnh tài nguyên:** Query/Index Service, CPU, RAM, disk I/O, network.
3. **Độ mới và consistency:** GSI cập nhật bất đồng bộ; `request_plus` có thể chờ index.

### 11.1. Dùng EXPLAIN cho cả hai môi trường

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID";
~~~

Hãy đọc index được chọn, IndexScan, Fetch, Filter và độ rộng scan. Một câu SQL++ chạy nhanh ở local với vài chục document không chứng minh sẽ nhanh trên deployment có hàng triệu document.

### 11.2. Tự quản lý có quyền tinh chỉnh hệ thống sâu hơn

Khi self-managed, nhóm có thể điều chỉnh topology, service placement và tài nguyên node trực tiếp hơn trong giới hạn sản phẩm. Với Capella, các điều chỉnh thường đi qua các lựa chọn sizing/topology và chức năng dịch vụ, không truy cập trực tiếp OS hoặc tự thay file cấu hình hệ thống tùy ý.

Điểm chung: **index design và query plan vẫn phải được tối ưu dựa trên workload**. Dịch vụ managed không tự bỏ qua chi phí Query/Index.

### 11.3. Tính nhất quán chỉ mục không đổi về bản chất

Ghi KV đã hoàn tất chưa chắc GSI ngay lập tức bắt kịp. Ba chiến lược phổ biến vẫn áp dụng:

| Chiến lược | Tác dụng | Lưu ý |
|---|---|---|
| `not_bounded` | Query không chờ index đạt một mốc mutation mới | Có thể chưa thấy thay đổi ngay |
| `request_plus` | Query chờ index theo kịp mutation trước mốc request | Có thể tăng độ trễ khi backlog |
| `consistentWith(MutationState)` | Chờ mutation cụ thể từ SDK | Cần mutation result/token hợp lệ |

Dù là Capella hay self-managed, chọn consistency dựa trên SLA nghiệp vụ. Nếu đã biết ID thì **KV get** thường là đường đơn giản hơn việc query qua index.

## 12. CAS, TTL, transaction và durability vẫn là trách nhiệm thiết kế

### 12.1. CAS: phát hiện lost update

Ví dụ hai request đọc cùng đơn và cùng sửa trạng thái. Với `@Version`/CAS, framework có thể từ chối ghi dùng bản đã đọc cũ. Không có bảo đảm managed service nào tự hiểu rằng `PAID → CANCELLED` là một chuyển trạng thái bị cấm.

Để cập nhật đúng:

- Kiểm tra quy tắc chuyển trạng thái.
- Sử dụng optimistic locking/CAS nếu phù hợp.
- Xử lý conflict, không retry vô hạn.
- Dùng ID ổn định và idempotency cho các yêu cầu có thể lặp.

### 12.2. TTL: vòng đời dữ liệu

Session có thể được ghi với TTL ngắn; đơn hàng cần retention riêng. `expiresAt` là trường JSON nếu ứng dụng lưu, còn expiry metadata được Couchbase quản lý.

Dù ở Capella hay self-managed:

- Cấu hình expiry/maxTTL theo bucket/collection khi hỗ trợ.
- Kiểm tra thao tác update có giữ hay reset TTL.
- Không dùng TTL làm scheduler bảo đảm callback đúng giờ.
- Có retention policy, backup và quy trình xóa dữ liệu phù hợp.

### 12.3. Transaction: nguyên tử nhiều document

Couchbase hỗ trợ transaction nhiều document theo phiên bản/điều kiện phù hợp. Transaction có thể giúp đồng bộ các thay đổi Couchbase, nhưng **không tự bao gồm** API thanh toán bên ngoài hoặc message broker.

Không mặc định chỉ vì chuyển database sang Capella thì `@Transactional` trong Spring có thể điều phối mọi side effect trong hệ thống. Cần xác minh transaction manager/SDK/version và idempotency.

### 12.4. Durability: xác nhận ghi theo mức cần thiết

Các mức synchronous durability có thể gồm `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE` và `PERSIST_TO_MAJORITY` khi loại bucket/phiên bản hỗ trợ. Mức phù hợp phụ thuộc RPO, replica và khả năng chịu lỗi.

Một managed deployment thường giúp giảm công việc duy trì bản sao và node, **nhưng không tự biến một thao tác KV không yêu cầu durability thành bảo đảm persistence mạnh nhất**. Chọn option theo tác động nghiệp vụ.

## 13. Scaling và high availability

### 13.1. Self-managed

Nhóm vận hành chủ động lên kế hoạch:

- Thêm/bớt node, phân bố Data/Query/Index Service.
- Rebalance vBucket và index khi topology thay đổi.
- Data replica, index replica, server groups/failure domains.
- Rolling upgrades và bảo trì.
- Đo latency/SLO khi cluster mất một node (**N-1 capacity**).

Vì có nhiều quyền kiểm soát, nhóm cũng phải chịu trách nhiệm xử lý khi một node thiếu đĩa, network bị ngắt hoặc cluster không rebalance được.

### 13.2. Capella

Capella cung cấp thao tác cấu hình sizing và một số quá trình scaling/HA được dịch vụ điều phối. **Phạm vi tự động scaling, lựa chọn service separation và chính sách failover thay đổi theo loại database/gói/region**, nên cần xem khả năng deployment.

Khi thay size hoặc topology, vẫn nên:

- Dự trù chi phí và thời gian thay đổi.
- Kiểm tra capacity của Data/Query/Index Service.
- Theo dõi latency p95/p99 trong và sau scaling.
- Đảm bảo replica, index availability và network connectivity.
- Thử tải nghiệp vụ, đặc biệt các hot key, query scan rộng và transaction.

Không coi “managed” là lời hứa **không bao giờ downtime**. Ứng dụng cần timeout/retry, idempotency, circuit breaker hoặc graceful degradation phù hợp.

### 13.3. RPO/RTO và failure domain

Bất kể mô hình, cần định nghĩa:

| Thuật ngữ | Ý nghĩa | Ví dụ yêu cầu cần kiểm thử |
|---|---|---|
| **RPO** | Mức mất dữ liệu tối đa có thể chấp nhận | Không mất đơn đã được xác nhận durable trong kịch bản lỗi đã định nghĩa |
| **RTO** | Thời gian chấp nhận để khôi phục dịch vụ | API đọc theo ID phục hồi trong mục tiêu sau một node lỗi |
| **Availability SLO** | Tỷ lệ yêu cầu thành công theo kỳ đo | KV/read và SQL++ được đo riêng |
| **Latency SLO** | Độ trễ mục tiêu cho các thao tác | p95/p99 của `findById`, `save` và query |
| **Failure domain** | Phạm vi lỗi độc lập | Host, rack, zone hoặc region theo kiến trúc |

Nhà cung cấp có thể công bố SLA riêng cho dịch vụ/tier. SLA dịch vụ **không thay thế SLO của ứng dụng** và cần đọc điều kiện áp dụng trước khi hứa với người dùng cuối.

## 14. Backup, restore và disaster recovery

### 14.1. Self-managed: phải tự tổ chức đầy đủ

Một chiến lược backup gồm:

1. Chọn công cụ/phương thức backup được Couchbase hỗ trợ.
2. Lên lịch và retention theo yêu cầu dữ liệu.
3. Bảo vệ backup khỏi mất mát hoặc truy cập trái phép.
4. Ghi nhận schema, collections, GSI, RBAC, secrets và cấu hình cần tái tạo.
5. Thử restore trong môi trường tách biệt.
6. Đo RPO/RTO thực tế, không chỉ tin trạng thái “backup completed”.

Để phục hồi sau lỗi nghiêm trọng, phải biết cách chuyển application traffic, tạo lại kết nối và kiểm tra dữ liệu.

### 14.2. Capella: dùng khả năng backup được dịch vụ hỗ trợ

Capella có những tùy chọn backup/khôi phục theo loại dịch vụ và cấu hình. Dù dịch vụ có thể tự động hóa phần lớn quy trình, nhóm ứng dụng vẫn cần xác định:

- Dữ liệu nào được backup và tần suất bao nhiêu.
- Thời gian lưu giữ (retention), vùng lưu trữ và chi phí liên quan.
- Khả năng point-in-time restore và giới hạn theo gói nếu được cung cấp.
- Thời gian restore thực tế với dung lượng ứng dụng.
- Những gì phải cấu hình lại ở ứng dụng sau restore: connection string, người dùng/quyền, index, secrets, DNS và network.

**Không giả định mặc định có backup với retention đúng chính sách**; phải kiểm tra cấu hình deployment và diễn tập restore.

### 14.3. XDCR và DR

Nếu cần replication giữa cluster/region, Couchbase có cơ chế **XDCR (Cross Datacenter Replication)** trong những cấu hình hỗ trợ. XDCR thường có tính bất đồng bộ; nó không tự tạo transaction xuyên vùng và không thay thế backup để khôi phục xóa nhầm.

Mô hình triển khai và khả năng cấu hình XDCR/DR trên Capella hay self-managed khác nhau theo dịch vụ. Kế hoạch DR cần cả phần dữ liệu lẫn **ứng dụng, secrets, DNS, truy cập mạng, kiểm chứng consistency và điều phối failover liên vùng**.

## 15. Quan sát vận hành và xử lý sự cố

Một hệ thống managed có thể cung cấp dashboard nhưng không đọc được toàn bộ vấn đề nghiệp vụ từ số liệu server. Một hệ thống self-managed có thể cung cấp metric host sâu hơn nhưng cần tự tích hợp nhiều nguồn.

### 15.1. Các chỉ số cần theo dõi ở cả hai

| Nhóm | Chỉ số điển hình | Mục tiêu |
|---|---|---|
| **KV** | Latency p50/p95/p99, timeout, retry, ambiguous outcomes | Đảm bảo API theo ID ổn định |
| **SQL++** | Query latency, concurrency, timeout, Query Service CPU | Phát hiện query tốn tài nguyên |
| **GSI** | Index availability, index lag/backlog, scan/Fetch | Phân biệt stale index và query plan kém |
| **Data** | Memory, disk, network, replica/active health | Dự đoán thiếu capacity |
| **Change events** | Scaling, rebalance, failover, version change | Liên hệ sự kiện với latency/error |
| **Security** | Authentication failures, permission errors, secret rotation | Phát hiện quyền sai và rủi ro truy cập |
| **Business** | Duplicate order, CAS conflict, payment anomalies | Đánh giá tính đúng đắn cuối cùng |

Metric cụ thể và kênh xuất phụ thuộc Server/Capella/SDK/version. Tên/nguồn metric phải được xác nhận trước khi dựng alert.

### 15.2. Bảng chẩn đoán kết nối

| Triệu chứng | Self-managed cần kiểm tra | Capella cần kiểm tra |
|---|---|---|
| Không bootstrap được | Seed node, DNS, port, cluster health | Endpoint thực, network access, TLS, database status |
| TLS handshake lỗi | CA/truststore, hostname, cert rotation | Trust chain, JDK, hostname, TLS SDK config |
| SDK ping thành công nhưng KV timeout | Published node addresses, Data Service, vBucket/rebalance | Network route đến data plane, allowed endpoint, cluster health |
| Query không chạy | Query node/index/role, keyspace, plan | Database privilege, GSI status, Query/Index availability |
| Query chậm | CPU/IO/Query Index node, `EXPLAIN` | Sizing/tài nguyên được phép, `EXPLAIN`, index lag |
| Sau đổi credentials, app báo auth error | RBAC, secret cache/restart, username | Database user/role, secret rotation và deployment |

**Đừng tăng timeout vô hạn để che vấn đề TLS, quyền hoặc routing.** Timeout là triệu chứng; nguyên nhân ở mạng, topology, index, resource hoặc logic phải được phân loại.

## 16. Hiệu năng và độ trễ khi ứng dụng ở xa database

Một lý do thường bị bỏ qua là **vị trí địa lý và mạng**.

Ví dụ:

~~~text
Ứng dụng: vùng A
Database: vùng B
Mỗi HTTP request thực hiện:
  1. get(order)
  2. get(customer)
  3. query(items)
  4. replace(order)
~~~

Nếu mỗi bước phải round-trip qua mạng xa, tổng latency tăng, dù database mạnh. Vấn đề này xảy ra ở cả Server tự quản lý và Capella.

Cách xử lý:

1. Đặt ứng dụng gần khu vực database khi được phép bởi chính sách dữ liệu.
2. Giảm thao tác tuần tự không cần thiết; kết hợp dữ liệu hợp lý trong document.
3. Dùng connection pooling và lifecycle SDK chuẩn.
4. Tạo index tốt, tránh Fetch/Sort lớn.
5. Chọn scan consistency theo SLA, không dùng `request_plus` mọi nơi.
6. Sử dụng reactive/async khi có lợi cho I/O, nhưng không nhầm với giảm độ trễ của từng round trip.
7. Cân nhắc cross-region read/DR chỉ khi có thiết kế consistency phù hợp.

**Một deployment managed mạnh hơn không tự sửa việc ứng dụng gọi hàng chục truy vấn tuần tự không cần thiết.**

## 17. Chi phí: so sánh TCO thay vì chỉ giá máy

### 17.1. Thành phần chi phí self-managed

- Máy chủ/VM, disk, storage I/O, networking và chỗ đặt máy.
- Bản quyền hoặc hỗ trợ thương mại theo edition/hợp đồng.
- Nhân sự quản trị Couchbase, monitoring, bảo mật, nâng cấp.
- Backup storage, test restore, môi trường staging và DR.
- Chi phí downtime, incident response và công việc ngoài giờ.
- Tài nguyên dự phòng để đạt SLO khi một node lỗi.

### 17.2. Thành phần chi phí Capella

- Database service tier/configuration, năng lực và thời gian hoạt động.
- Backup/retention, data transfer/egress và network/private connectivity nếu có tính phí.
- Các dịch vụ/khả năng bổ sung được bật theo hợp đồng.
- Nhân sự ứng dụng và DBA để tối ưu schema, index, query, security.
- Kiểm thử, migration, monitoring và DR ở cấp ứng dụng.

Giá/đơn vị tính khác nhau theo thời điểm, cloud, region và gói dịch vụ; bài học **không đưa bảng giá cố định** vì có thể sai khi triển khai.

### 17.3. Cách ước lượng thực tế

Thay vì hỏi “Capella hay tự quản lý rẻ hơn?”, hãy lập baseline:

| Biến | Cần thu thập |
|---|---|
| Workload | KV ops/s, query/s, peak traffic, số tenant |
| Dữ liệu | Dung lượng hiện tại, tốc độ tăng, số index, TTL/retention |
| Latency | SLO p95/p99 cho KV và SQL++ |
| HA/DR | Replica, RPO/RTO, backup frequency, region |
| Con người | Thời gian DBA/SRE, lịch trực, yêu cầu hỗ trợ |
| Mạng | Chi phí traffic, cloud egress, private access |
| Migration | Thời gian song song hai môi trường, chi phí kiểm thử/cutover |

Sau đó chạy **load test đại diện** trên phương án triển khai thay vì suy đoán chỉ từ thông số CPU/RAM.

## 18. Chọn mô hình nào cho một dự án Spring Data Couchbase?

Một số tiêu chí có thể giúp quyết định.

| Câu hỏi | Nghiêng về self-managed khi... | Nghiêng về Capella khi... |
|---|---|---|
| Có yêu cầu host/network đặc thù? | Cần kiểm soát sâu OS, thiết bị, topology | Có thể sử dụng mô hình truy cập do managed service cung cấp |
| Đội vận hành có chuyên môn DB? | Có SRE/DBA và quy trình HA/DR tốt | Muốn giảm công việc DB infrastructure |
| Dữ liệu phải ở môi trường riêng? | Có yêu cầu bắt buộc on-prem/không dùng managed cloud | Cloud và region được pháp lý/chính sách chấp nhận |
| Cần tốc độ triển khai? | Đã có automation/cluster chuẩn | Muốn provision nhanh qua dịch vụ managed |
| Tải và sizing thay đổi? | Muốn tùy chỉnh topology trực tiếp | Ưu tiên khả năng scaling/cấu hình do dịch vụ hỗ trợ |
| Chi phí tổng thể? | TCO sau nhân lực/HA/backup thấp hơn theo số đo | TCO/giảm rủi ro vận hành tốt hơn theo số đo |
| Trách nhiệm tuân thủ? | Muốn tự kiểm soát nhiều lớp chi tiết | Mô hình shared responsibility phù hợp đánh giá nội bộ |

Không có phương án **luôn tốt hơn**. Hai phương án còn có thể tồn tại trong một tổ chức, ví dụ môi trường thử nghiệm self-managed và production Capella, nhưng phải quản lý version, cấu hình và parity để tránh “dev chạy được, production khác”.

### 18.1. Một số tình huống

**Tình huống A — nhóm sản phẩm nhỏ:** Một đội Java cần API đơn hàng, hạn chế nhân lực trực database, cloud hợp lệ và có ngân sách dịch vụ. Capella có thể hợp lý, miễn đánh giá cấu hình backup, network, region và pricing.

**Tình huống B — doanh nghiệp có data center riêng:** Dữ liệu phải ở mạng/hạ tầng kiểm soát chặt, có đội vận hành cơ sở dữ liệu và tiêu chuẩn bảo trì. Couchbase Server tự quản lý có thể phù hợp hơn.

**Tình huống C — tổ chức có Kubernetes:** Đã có nền tảng Kubernetes chuẩn và team SRE, muốn kiểm soát service placement. Couchbase Server với Operator có thể là phương án, nhưng phải tính chi phí vận hành Kubernetes và chính database.

**Tình huống D — đa khu vực và DR:** Cả hai lựa chọn đều cần kiểm chứng hỗ trợ replication/DR theo topology thật; không kết luận chỉ từ việc có “multi-cloud” hay “replica” trong mô tả marketing.

## 19. Kế hoạch di chuyển từ self-managed sang Capella

Di chuyển deployment không phải thao tác thay một dòng cấu hình. Đây là một dự án thay đổi môi trường với dữ liệu, bảo mật, network và hệ quả về consistency.

### 19.1. Giai đoạn 1 — đánh giá tương thích

Lập danh sách có kiểm chứng:

- Phiên bản Couchbase Server nguồn, version và tính năng mà deployment đích hỗ trợ.
- Java SDK, Spring Data Couchbase, Spring Boot và JDK.
- Bucket/scope/collection, naming, JSON schema, loại document, TTL/maxTTL.
- Index SQL++, query plan, dùng `META()`, query parameterization, transaction.
- RBAC, users, network policies, TLS, certificate/truststore.
- Data size, số document, tốc độ mutation, peak traffic.
- Backup/restore, DR, RPO/RTO và yêu cầu downtime.

Không mặc định mọi edition/version có cùng tính năng. Nếu ứng dụng dùng cấu hình server đặc thù, kiểm tra xem Capella có cung cấp tùy chọn tương ứng hay không.

### 19.2. Giai đoạn 2 — chuẩn bị deployment đích

1. Chọn cloud/region đáp ứng yêu cầu dữ liệu và mạng.
2. Provision database deployment, thiết lập network access và TLS.
3. Tạo database users/roles theo least privilege.
4. Tạo bucket/scope/collection và chính sách expiry phù hợp.
5. Tạo GSI cần thiết và đợi index ở trạng thái hoạt động.
6. Bật/chọn backup/retention nếu dịch vụ hỗ trợ; có kế hoạch restore.
7. Chạy smoke test SDK `get`/`insert`/SQL++ trên dữ liệu thử.

### 19.3. Giai đoạn 3 — chuyển dữ liệu

Phương án di chuyển cần được chọn theo đặc tính nguồn/đích, công cụ được hỗ trợ, trạng thái downtime và SLA. Có thể có cách dùng backup/restore, import/export, replication hoặc ứng dụng dual-write theo thiết kế; **không chọn một cơ chế chỉ vì tên gọi tương tự**.

Những nội dung phải kiểm tra:

- Mapping document ID và keyspace.
- Trường JSON và schema version.
- Expiry/TTL sau di chuyển.
- Phạm vi và trạng thái index, độ trễ build.
- Quy tắc duplicate/conflict nếu dữ liệu vẫn thay đổi ở nguồn.
- Khả năng rollback khi cutover thất bại.

**Cảnh báo:** Nếu dữ liệu tiếp tục ghi ở nguồn trong lúc copy, cần một cách đồng bộ phần chênh lệch và cutover nhất quán. Chỉ chạy copy một lần rồi đổi kết nối có thể làm mất những mutation cuối cùng.

### 19.4. Giai đoạn 4 — kiểm thử và cutover

~~~mermaid
flowchart TD
    A["Đánh giá tương thích"]
    B["Tạo Capella + mạng/RBAC"]
    C["Chuyển dữ liệu và dựng index"]
    D["Đối soát ID, số lượng, dữ liệu, TTL"]
    E["Chạy test nghiệp vụ và benchmark"]
    F["Đồng bộ chênh lệch / khóa ghi theo kế hoạch"]
    G["Cutover connection + traffic"]
    H["Quan sát, xác minh và rollback nếu cần"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Trước cutover:

- Kiểm tra số lượng document theo scope/collection với phương pháp đối soát phù hợp, không chỉ dựa vào một query GSI có thể chưa mới.
- Đối soát dữ liệu mẫu/kiểm tra hash, schema version, TTL và quyền.
- Chạy use case quan trọng: login/session, tạo đơn, thanh toán, retry, index query và transaction.
- Xác định rollback window, điều kiện abort, ai quyết định và cách đồng bộ dữ liệu nếu quay về nguồn.
- Đo p95/p99 KV, SQL++, CAS conflict và timeout từ **đúng mạng ứng dụng production**.

Sau cutover cần giám sát đủ lâu theo phương án vận hành, nhưng không có một khoảng thời gian cố định áp dụng cho mọi hệ thống.

## 20. Lỗi thường gặp khi chuyển hoặc chọn môi trường

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Local self-managed kết nối được, Capella timeout | Chưa cho phép IP/route, sai hostname hoặc TLS | Kiểm tra network access, private endpoint, DNS và connection string |
| SSL handshake failure | JVM không tin CA, hostname verification lỗi, SDK cũ | Cập nhật truststore/SDK, kiểm tra chứng chỉ; không tắt TLS verification |
| Authentication failure | Nhầm console user với database user hoặc sai secret | Tạo database credential, phân quyền và secret rotation |
| `findById` được, `findByStatus` không chạy | Query/Index Service, thiếu GSI, RBAC, khác keyspace | Kiểm tra query plan, index online và quyền |
| Dữ liệu thiếu sau migration | Copy chưa đủ, dữ liệu tiếp tục ghi, sai collection/ID | Đối soát dữ liệu và đồng bộ chênh lệch |
| Document session hết hạn sai | TTL/maxTTL không tương thích hoặc migration reset expiry | Kiểm tra expiry metadata và thử end-to-end |
| CAS conflict tăng sau cutover | Hai writer chạy song song hoặc logic retry thay đổi | Kiểm tra quyền ghi, chiến lược cutover, idempotency |
| Query p99 tăng dù sizing lớn | Khác RTT, thiếu index, request_plus hoặc scan rộng | Benchmark từ mạng thật, EXPLAIN, giảm round trip |
| Không có quyền tạo index | Runtime user được cấp tối thiểu | Dùng tài khoản migration riêng có role cần thiết |
| Backup policy chưa đáp ứng RPO | Chưa cấu hình/kiểm thử restore hoặc hiểu nhầm retention | Xác định RPO/RTO và kiểm tra backup option thực tế |
| Chuyển sang reactive vẫn timeout | Network/index/capacity chưa được tối ưu | Xác định lớp nghẽn, giới hạn concurrency/retry |

## 21. Bài tập thực hành

### Bài tập A — phân loại trách nhiệm

Một nhóm chuyển từ self-managed sang Capella. Hãy phân loại những việc sau thành **dịch vụ quản lý nhiều hơn** và **nhóm ứng dụng vẫn chịu trách nhiệm**:

1. Provision database host.
2. Thiết kế GSI cho `orders`.
3. Quản lý database credentials của `order-service`.
4. Chọn retention backup và kiểm thử restore.
5. Kiểm tra điều kiện chuyển `NEW → PAID`.
6. Điều chỉnh query dùng `request_plus` phù hợp SLA.

**Gợi ý:** managed không thay thế schema/index design, RBAC ứng dụng, business rule hoặc RPO/RTO.

### Bài tập B — sửa cấu hình kết nối

Một ứng dụng Spring Boot dùng `couchbase://localhost` trên laptop và cần chạy trên Capella. Liệt kê các thay đổi tối thiểu ngoài connection string: TLS, DNS, network access, database user/role, bucket và kiểm thử từ môi trường triển khai.

### Bài tập C — runtime user không có quyền index

Repository `findById` thành công, một pipeline migration `CREATE INDEX` lỗi permission. Có nên cấp quyền quản trị toàn cluster cho runtime API không? Thiết kế tài khoản migration tách biệt.

### Bài tập D — TCO

Hai giải pháp có cùng throughput mục tiêu. Self-managed rẻ hơn tiền hạ tầng trực tiếp, nhưng yêu cầu một đội DBA/SRE trực và hệ thống backup riêng. Capella có phí dịch vụ cao hơn. Hãy lập bảng gồm ít nhất tám biến số để so sánh **TCO 12 tháng** và tác động rủi ro.

### Bài tập E — chuyển dữ liệu đang được ghi

Trong lúc copy đơn hàng sang Capella, API vẫn nhận request mới ở cluster nguồn. Nêu rủi ro mất mutation tại cutover và đề xuất chiến lược đối soát/đồng bộ chênh lệch.

### Bài tập F — SQL++ và index lag

Sau chuyển sang Capella, `findById` thấy order vừa lưu nhưng `findByTenantIdAndStatus` chưa thấy. Có thể kết luận managed service bị lỗi không? Phân tích index lag, scan consistency, query/filter, index availability và cách thử bằng `request_plus`.

### Bài tập G — HA và backup

Một deployment có data replica và đáp ứng KV khi mất một node. Một quản trị viên cho rằng không cần backup. Hãy phản biện dựa trên tình huống xóa nhầm hàng loạt, lỗi logic và DR liên vùng.

## 22. Checklist quyết định triển khai

- [ ] Xác định môi trường được phép lưu dữ liệu theo chính sách/pháp lý và region.
- [ ] Đánh giá TCO đầy đủ: compute, storage, networking, nhân lực, backup, DR.
- [ ] Chọn mô hình dựa trên yêu cầu kiểm soát host/topology và năng lực vận hành.
- [ ] Kiểm tra service/feature/region/tier thực tế thay vì giả định mọi option đều có.
- [ ] Dùng Couchbase Java SDK và Spring Data/Couchbase Server version tương thích.
- [ ] Thiết lập TLS, DNS, firewall/allowlist hoặc private connectivity và thử từ đúng runtime.
- [ ] Tách quyền quản trị control plane và tài khoản database của ứng dụng.
- [ ] Thiết kế bucket/scope/collection, RBAC và index theo workload.
- [ ] Kiểm tra CAS, TTL, transaction, durability và scan consistency theo use case.
- [ ] Có SLO cho KV và SQL++ riêng; theo dõi p95/p99 và index lag.
- [ ] Lập kế hoạch failover, replica, backup/restore và DR theo RPO/RTO.
- [ ] Không nhầm managed service với trách nhiệm dữ liệu được chuyển toàn bộ.
- [ ] Khi migration, đối soát dữ liệu, expiry, index, quyền và cutover gap.
- [ ] Thử rollback trước khi chuyển traffic production.
- [ ] Với reactive, giới hạn concurrency/retry và giữ idempotency cho mutation.

## 23. Tổng kết

**Couchbase Server tự quản lý** cho phép tổ chức kiểm soát nhiều lớp triển khai và topology, đổi lại phải chủ động vận hành node, security, nâng cấp, backup và xử lý sự cố. **Couchbase Capella** chuyển nhiều nhiệm vụ quản lý cơ sở hạ tầng sang dịch vụ cloud, giúp nhóm tập trung hơn vào ứng dụng, nhưng vẫn cần cấu hình network, quyền, backup policy, sizing và quan sát hiệu năng.

Ở tầng lập trình, **document ID, bucket/scope/collection, KV, SQL++, CAS, TTL, transaction, durability và reactive API** có ý nghĩa tương tự theo khả năng tương thích của version. Với **Spring Data Couchbase**, entity và repository có thể được tái sử dụng; thứ thay đổi chủ yếu là kết nối, quyền, network và quy trình vận hành. Sự thành công của lựa chọn triển khai không đo chỉ bằng thời gian provision database, mà còn bằng **tính đúng đắn nghiệp vụ, mức độ an toàn dữ liệu, chi phí tổng thể và khả năng khôi phục khi xảy ra sự cố**.
