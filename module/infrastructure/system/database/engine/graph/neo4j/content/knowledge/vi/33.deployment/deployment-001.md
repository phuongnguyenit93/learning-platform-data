# Chọn tự quản lý hay dịch vụ quản lý theo yêu cầu vận hành

Sau khi mô hình hóa node, relationship, constraint và truy vấn Cypher, một đội phát triển Neo4j phải trả lời câu hỏi vận hành: **tự chạy Neo4j trên hạ tầng của mình hay sử dụng dịch vụ Neo4j được quản lý?** Cả hai đều có thể phục vụ ứng dụng Java Driver và Spring Data Neo4j, nhưng mức kiểm soát, trách nhiệm bảo trì, chi phí và cách bảo đảm tính sẵn sàng khác nhau đáng kể.

Bài thuộc chương **Triển khai** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module tập trung vào property graph Neo4j, quan hệ và đường đi bằng Cypher, index/constraint, tối ưu truy vấn, nhập dữ liệu, Java Driver, Spring Data Neo4j và vận hành đồ thị. Bài này trình bày **khung ra quyết định** để chọn mô hình triển khai theo yêu cầu thực, không mặc định “cloud luôn tốt hơn” hoặc “tự quản lý luôn rẻ hơn”.

> **Phạm vi:** Neo4j tự quản lý (*self-managed*) có thể chạy trên máy ảo, bare metal, Docker hoặc Kubernetes. Dịch vụ được quản lý (*managed service*) có ví dụ điển hình là **Neo4j AuraDB**. Các tính năng, vùng triển khai, SLA, backup/restore, giới hạn tài nguyên, quyền mạng, plugin, hỗ trợ GDS và giá dịch vụ **thay đổi theo gói và thời điểm**. Mọi quyết định production phải đối chiếu hợp đồng, tài liệu và tính năng của gói đang cân nhắc; bảng trong bài diễn tả trách nhiệm và xu hướng chung, không hứa hẹn tính năng cho mọi gói.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt mô hình **self-managed** với **managed Neo4j** và giải thích mô hình trách nhiệm chia sẻ.
2. Thu thập yêu cầu **SLO, RPO, RTO, dữ liệu, bảo mật, mạng, plugin và ngân sách** trước khi chọn nơi triển khai.
3. So sánh chi phí sở hữu tổng thể (**TCO**) và chi phí rủi ro, thay vì chỉ so giá máy chủ với giá thuê dịch vụ.
4. Nhận diện những khác biệt quan trọng đối với Cypher, APOC, Graph Data Science, Java Driver và Spring Data Neo4j.
5. Lập sơ đồ tối thiểu cho một triển khai tự quản lý và một kết nối đến dịch vụ quản lý.
6. Xây dựng checklist pilot, kế hoạch di chuyển, cutover, rollback và xác minh sau chuyển môi trường.

## 2. Hai mô hình triển khai nghĩa là gì?

### 2.1. Neo4j tự quản lý (self-managed)

Đội sở hữu hoặc thuê hạ tầng, sau đó **tự triển khai và quản lý** tiến trình Neo4j. Hạ tầng có thể là:

- Máy vật lý trong trung tâm dữ liệu của tổ chức.
- Máy ảo hoặc instance trên nhà cung cấp cloud.
- Container Docker để đóng gói và chuẩn hóa môi trường.
- Kubernetes có operator/chart và quy trình vận hành phù hợp.

Người vận hành phải xử lý cấu hình server, TLS, kết nối Bolt, ổ đĩa, cập nhật phiên bản, sao lưu/phục hồi, giám sát, tối ưu tài nguyên, và nếu cần **high availability (HA)** thì còn phải thiết kế nhiều thành viên, định tuyến và quy trình failover theo edition/bản Neo4j được cấp phép.

Self-managed **không đồng nghĩa** tự mua phần cứng: bạn có thể tự quản trị Neo4j trên máy ảo cloud. Khi đó nhà cung cấp cloud quản lý phần cứng nền, còn **đội bạn quản lý database**.

### 2.2. Neo4j được quản lý (managed service)

Dịch vụ như **Neo4j AuraDB** cung cấp một DBMS/instance được nhà cung cấp vận hành ở cấp hạ tầng dịch vụ. Người dùng chủ yếu tạo instance, quản lý cấu hình mà sản phẩm cho phép, kết nối, định nghĩa schema, import dữ liệu, viết Cypher và vận hành ứng dụng.

Nhà cung cấp đảm nhận nhiều tác vụ như triển khai nền tảng, một phần nâng cấp/giám sát, bố trí tài nguyên và cơ chế backup/availability **theo gói sản phẩm**. Đội ứng dụng **vẫn** chịu trách nhiệm về:

- Mô hình dữ liệu, constraint/index và tính đúng đắn của Cypher.
- Tài khoản ứng dụng, thông tin xác thực, phân quyền và chính sách dữ liệu trong phạm vi được giao.
- Tích hợp Java Driver/SDN, cấu hình kết nối, retry và idempotency.
- Khối lượng công việc, truy vấn chậm, dung lượng dữ liệu, chi phí và thời điểm nâng cấp.
- Đảm bảo yêu cầu kinh doanh về dữ liệu, sao lưu/khôi phục và DR thực sự được đáp ứng bởi gói đã chọn.

**Managed không có nghĩa “không cần DBA/kiến trúc sư dữ liệu”**: việc nhà cung cấp giữ máy chủ chạy ổn định không tự sửa truy vấn `MATCH` nở hàng, thiếu index hoặc sai mô hình relationship.

## 3. Sơ đồ trách nhiệm

~~~mermaid
flowchart LR
    subgraph S["Tự quản lý"]
      A["Nhóm ứng dụng:<br/>Cypher, schema, dữ liệu"] --> B["Nhóm vận hành:<br/>DBMS, backup, patch, HA"]
      B --> C["Hạ tầng:<br/>VM / Docker / Kubernetes / máy chủ"]
    end
    subgraph M["Dịch vụ quản lý"]
      D["Nhóm ứng dụng:<br/>Cypher, schema, dữ liệu"] --> E["Nhà cung cấp:<br/>nền tảng DB theo gói/SLA"]
      E --> F["Hạ tầng của nhà cung cấp"]
    end
~~~

| Công việc | Self-managed | Managed |
|---|---|---|
| Thiết kế graph, Cypher, index/constraint | Đội ứng dụng/dữ liệu | Đội ứng dụng/dữ liệu |
| Cấu hình Java Driver, connection pool, timeout | Đội ứng dụng | Đội ứng dụng |
| Cài DBMS, cấu hình host, patch hệ điều hành | Đội hạ tầng/DBA | Phần lớn do nhà cung cấp đảm nhận trong phạm vi dịch vụ |
| Cấu hình replication/HA cơ sở dữ liệu | Tự thiết kế, vận hành theo edition | Năng lực do gói dịch vụ quy định; kiểm tra SLA |
| Lịch backup, lưu trữ, test restore | Tự triển khai và chịu trách nhiệm | Nhà cung cấp cung cấp chức năng theo gói; đội khách hàng phải kiểm tra RPO/RTO và khả năng khôi phục |
| Chứng chỉ, network perimeter, private connectivity | Tự quản lý DB/network | Chia sẻ theo khả năng network của gói và thiết kế ứng dụng |
| Tối ưu query, dữ liệu lỗi, quyền ứng dụng | Đội ứng dụng/DBA | Vẫn thuộc trách nhiệm khách hàng |
| Quan sát và xử lý sự cố ứng dụng | Đội ứng dụng/DBA | Khách hàng; nhà cung cấp hỗ trợ phần thuộc dịch vụ theo gói |
| Gia hạn license, bảo trì plugin tùy biến | Theo hợp đồng và triển khai | Phụ thuộc gói, thường không cho tùy ý cài JAR |
| Đối soát hóa đơn, ngân sách và tăng trưởng | Khách hàng | Khách hàng |

Mỗi dòng của bảng là một **mô hình trách nhiệm**, không phải một cam kết SLA. Ví dụ, một gói Aura có thể cung cấp lựa chọn backup/restore và support khác gói khác; đội khách hàng vẫn phải xác nhận những yêu cầu phục hồi cụ thể trước khi ký hợp đồng.

## 4. Bắt đầu từ yêu cầu thay vì từ tên sản phẩm

Không nên khởi đầu bằng câu “Dùng Kubernetes hay Aura?” mà nên viết **bảng yêu cầu có thể kiểm chứng**.

| Trục yêu cầu | Câu hỏi định lượng/kiểm tra | Ví dụ giả định |
|---|---|---|
| Tải | Số query/s, % read/write, dữ liệu trả về, fan-out lớn nhất? | 300 request/s, 80% đọc |
| Độ trễ | API hoặc DB có p95/p99 mục tiêu bao nhiêu? | API p95 ≤ 200 ms |
| Dữ liệu | Số node, relationship, property, tốc độ tăng? | 15 triệu node, 70 triệu relationship |
| Tính sẵn sàng | Thời gian dừng chấp nhận trong một kỳ? | SLO 99,9%/tháng |
| Phục hồi | Mất bao nhiêu dữ liệu là chấp nhận? Bao lâu phải phục hồi? | RPO 15 phút, RTO 1 giờ |
| Vùng dữ liệu | Dữ liệu có được đặt ngoài một khu vực pháp lý không? | Chỉ cho phép một vùng nhất định |
| Network | Có cần private endpoint, peering, outbound egress hạn chế? | Chỉ private routing |
| Bảo mật | Vai trò RBAC, audit, encryption, key management nào bắt buộc? | Fine-grained access, audit |
| Mở rộng | Có dùng custom plugin, APOC Extended, GDS, CDC? | Một procedure tự viết bằng Java |
| Vận hành | Có đội trực 24/7 và khả năng restore/cluster không? | Chỉ một SRE bán thời gian |
| Chi phí | Ngân sách hằng năm và chi phí ngoài DB bao nhiêu? | TCO giới hạn theo quý |

Các con số ở cột cuối **chỉ là ví dụ để học cách viết yêu cầu**, không phải ngưỡng Neo4j được bảo đảm. Đặc biệt, SLO ứng dụng và SLA nhà cung cấp **không đồng nhất**: API có thể lỗi vì ứng dụng hoặc mạng ngay cả khi database vẫn sẵn sàng.

### Phân biệt yêu cầu “phải có” và “nên có”

- **Điều kiện bắt buộc:** vùng dữ liệu hợp lệ, private networking, plugin Java đã bắt buộc không thể thay, RPO/RTO theo hợp đồng.
- **Điều kiện tối ưu:** giảm số giờ trực, giảm độ trễ, tiết kiệm chi phí, triển khai nhanh, khả năng thay đổi tài nguyên.

Nếu một phương án **không đáp ứng điều kiện bắt buộc**, không nên chọn nó chỉ vì điểm số tổng hợp hoặc giá tốt hơn.

## 5. Các trục so sánh quan trọng

### 5.1. Kiểm soát hạ tầng và cấu hình

**Self-managed** phù hợp khi cần tùy chỉnh sâu hệ điều hành, JVM, cấu trúc cluster, chính sách ổ đĩa, lịch nâng cấp, network policy hay agent quan sát. Đổi lại, thay đổi cấu hình thiếu kiểm thử có thể ảnh hưởng data integrity và availability.

**Managed** có bề mặt cấu hình giới hạn nhưng giúp giảm số quyết định vận hành nền tảng. Bạn phải chấp nhận những giới hạn tương ứng: cửa sổ bảo trì, cách điều chỉnh dung lượng, bản Neo4j được hỗ trợ hoặc không được cài module tùy ý.

### 5.2. Tốc độ bắt đầu và nhân sự

- Dự án thử nghiệm nhanh, ít người vận hành thường có lợi từ **managed** nếu các giới hạn tính năng và vùng dữ liệu đều phù hợp.
- Tổ chức có đội DBA/SRE trưởng thành, sẵn cluster, automation và yêu cầu kiểm soát nhiều lớp có thể chọn **self-managed**.
- Một container chạy được trong năm phút **không có nghĩa đã có hệ thống production** với backup, HA, bảo mật, log và diễn tập sự cố.

### 5.3. Tính linh hoạt của plugin và thuật toán

Một chương trình Cypher thuần có thể dễ chuyển giữa hai môi trường hơn một hệ thống phụ thuộc custom procedure. Nếu workload sử dụng:

- **APOC Core:** kiểm tra danh sách function/procedure được hỗ trợ và chính sách thực thi trên gói managed.
- **APOC Extended / custom Java procedures:** thường cần quyền cài plugin trực tiếp, nên phải khảo sát khả năng triển khai trước khi chọn managed.
- **Neo4j Graph Data Science (GDS):** phân biệt khả năng dùng GDS, phiên bản, projection in-memory, kích thước graph và cấp phép với **cơ sở dữ liệu AuraDB**. Tính sẵn có có thể khác theo sản phẩm/gói.
- **Import/export đặc biệt:** nhập CSV từ `file:///...`, đọc file trong `import` hoặc gọi lệnh `neo4j-admin` trên host có thể không tồn tại như cũ trong managed. Cần thiết kế đường nạp dữ liệu được dịch vụ hỗ trợ (API, URL, import workflow, driver).

**Không kết luận “có APOC” là đủ.** Một số dự án chỉ cần `apoc.convert.fromJsonMap`; dự án khác cần một procedure thuộc Extended hoặc thao tác file. Phải kiểm tra **tên procedure cụ thể** trên môi trường đích.

### 5.4. Giới hạn, nâng cấp và lock-in

Khi chạy self-managed, đội vận hành có quyền quyết định nhiều chi tiết phiên bản/triển khai, nhưng phải **tự lập kế hoạch nâng cấp, migration, failback và vá bảo mật**. Với managed, chính sách nâng cấp và tương thích theo sản phẩm; có thể giảm việc bảo trì nhưng cần theo dõi thông báo thay đổi.

Tác nhân lock-in không chỉ là dịch vụ lưu trữ. Một dự án có thể phụ thuộc vào:

- Query dùng tính năng Cypher chỉ có ở một bản Neo4j.
- Procedure của APOC/GDS/custom plugin.
- Cách import, snapshot hoặc tích hợp proprietary.
- Network topology, IAM, script backup hoặc công cụ giám sát.

Sử dụng Java Driver theo giao thức Bolt giúp giữ code ứng dụng gần với Neo4j, nhưng **không tự bảo đảm tính tương thích dữ liệu, procedure hoặc topology mạng** khi chuyển môi trường.

## 6. HA, backup và disaster recovery (DR) không phải một thứ

Ba khái niệm hay bị nhầm:

| Khái niệm | Mục tiêu | Không giải quyết được điều gì một mình? |
|---|---|---|
| **High availability (HA)** | Dịch vụ tiếp tục hoặc nhanh chóng tiếp tục khi một thành viên/zone gặp lỗi | Không thay backup nếu dữ liệu bị xóa logic, corruption hoặc ransomware |
| **Backup/restore** | Có bản dữ liệu để khôi phục sau mất mát hoặc thao tác sai | Không tự bảo đảm thời gian phục hồi đủ ngắn |
| **Disaster recovery (DR)** | Khôi phục nghiệp vụ sau sự cố nghiêm trọng về vùng/hệ thống | Không có tác dụng nếu không diễn tập và xác nhận quy trình |

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa được chấp nhận, thường tính theo thời gian. **RTO (Recovery Time Objective)** là khoảng thời gian mục tiêu để khôi phục dịch vụ.

Ví dụ giả định: doanh nghiệp muốn **RPO ≤ 15 phút**, **RTO ≤ 60 phút**. Không thể suy ra hai mục tiêu đó sẽ được đáp ứng chỉ vì một gói được quảng cáo “có backup tự động” hoặc một cluster có ba máy.

### 6.1. Khi tự quản lý

Cần có tối thiểu:

1. **Mô hình failure domain:** server, ổ đĩa, availability zone, network và region nào có thể cùng hỏng?
2. **Edition/cluster topology hỗ trợ HA:** không giả định một container hay một replica tự chế có tính năng cluster enterprise.
3. **Backup đã được kiểm chứng:** loại full/incremental được bản Neo4j hỗ trợ, lịch chạy, mã hóa, lưu tách biệt và retention.
4. **Restore drill:** định kỳ khôi phục vào môi trường sạch và đo thời gian, không chỉ kiểm tra “file backup tồn tại”.
5. **Giám sát replication/failover:** alert khi member mất kết nối, write routing thất bại, dữ liệu đích trễ hoặc backup lỗi.
6. **Runbook có owner:** ai chẩn đoán, ai chấp thuận failover/restore, lúc nào dừng ghi và cách đối soát sau phục hồi.

Chiến lược backup/restore của một **standalone** và một **cluster** có thể khác nhau. Không sao chép lệnh sao lưu, cổng hay thư mục từ tài liệu cũ sang Neo4j mới mà chưa kiểm tra version/edition.

### 6.2. Khi dùng managed

Kiểm tra trong **gói cụ thể**, bằng tài liệu/hợp đồng:

- Backup có tạo tự động không? Tần suất, thời hạn giữ, điểm khôi phục là gì?
- Restore là tự phục vụ hay cần yêu cầu hỗ trợ? Có thể restore sang **instance khác** để kiểm thử không?
- Có bảo vệ nhiều zone/region không? Trường hợp toàn region gặp sự cố thì quy trình thế nào?
- RPO và RTO được **cam kết** hay chỉ là tính năng **best effort**?
- Có SLA availability không? Điều kiện tính, ngoại lệ và mức hỗ trợ là gì?
- Khi lỗi application do xóa node/relationship nhầm, có thể khôi phục **chọn lọc** hay cần đối soát dữ liệu?

Nhà cung cấp có thể vận hành cơ chế HA nhưng đội ứng dụng vẫn phải bảo đảm **giao dịch idempotent, retry và khả năng chọn lại leader/connection** ở tầng Java Driver.

### 6.3. Bảng bằng chứng cần thu thập

| Yêu cầu | Bằng chứng |
|---|---|
| “Có backup” | Chính sách, lịch thực tế, bản sao gần nhất, log success/failure |
| “Đạt RPO 15 phút” | Khoảng cách dữ liệu được kiểm chứng sau một restore thử |
| “Đạt RTO 60 phút” | Biên bản diễn tập từ lúc phát hiện sự cố đến lúc ứng dụng hoạt động |
| “Có HA” | Topology, kết quả thử dừng một thành viên, ảnh hưởng tới ghi/đọc |
| “Có giám sát lỗi backup” | Dashboard, cảnh báo, owner nhận và xử lý |
| “Khôi phục dữ liệu đúng” | Đối chiếu checksum/tập khóa, constraint, số node/relationship |

**Không lấy 99,9% uptime của DBMS suy ra 99,9% uptime của API** khi API còn phụ thuộc kết nối mạng, ứng dụng, hệ thống xác thực và các dịch vụ ngoài.

## 7. Bảo mật, quyền và nơi đặt dữ liệu

### 7.1. Quyền truy cập Neo4j

Ứng dụng Java Driver và Spring Data Neo4j cần tài khoản có **quyền tối thiểu**. Một service đọc `:Customer` và `:Order` không cần quyền admin hoặc sửa schema. Tính năng RBAC chi tiết phụ thuộc Neo4j edition/gói.

Với self-managed, đội vận hành chịu trách nhiệm triển khai authentication/authorization, phân quyền, cấu hình transport encryption và bảo vệ secret. Với managed, nền tảng cung cấp tập khả năng quản trị theo gói, nhưng **khách hàng vẫn phải tạo và quản lý identity phù hợp**, tách quyền runtime với schema migration và kiểm tra đường truy vấn thật.

### 7.2. TLS và network

Trước khi chọn phương án, vẽ luồng kết nối:

~~~mermaid
flowchart LR
    APP["Java app / Spring Boot"] -->|"Bolt + TLS"| ENDPOINT["Neo4j endpoint"]
    ENDPOINT --> DB["Database"]
    SEC["Firewall / private networking / DNS"] -.-> ENDPOINT
    AUTH["Secrets / IAM / RBAC"] -.-> APP
~~~

- **Self-managed:** tự quản lý firewall, public/private subnet, load balancer/cluster routing, DNS, chứng chỉ TLS, network egress và vòng đời secret.
- **Managed:** kiểm tra sản phẩm/gói có hỗ trợ private endpoint, peering, IP allowlist, region cụ thể và kiểu xác thực cần dùng không.
- **Cả hai:** hạn chế port Bolt ra Internet nếu không cần, dùng TLS xác minh danh tính server, tránh hard-code mật khẩu, rotate credential và log cẩn thận.

Không dùng `bolt://` không mã hóa qua mạng không tin cậy. Với một endpoint dùng chứng chỉ hợp lệ, các scheme `neo4j+s://` hoặc `bolt+s://` có thể phù hợp theo kiểu routing/topology; chọn dựa trên khuyến nghị của dịch vụ/cluster. **Không** tắt xác thực TLS chỉ để làm thử nghiệm kết nối thành công.

### 7.3. Data residency và compliance

Một số tổ chức yêu cầu dữ liệu, bản sao backup, log và nơi xử lý dữ liệu nằm trong phạm vi pháp lý xác định. “Database chạy trong region X” **không tự chứng minh** log/support/backup hay mọi luồng dữ liệu chỉ ở region X.

Checklist cần hỏi:

1. Region nào thực sự được cung cấp ở **gói dịch vụ định mua**?
2. Dữ liệu chính, backup, log và thông tin hỗ trợ được lưu/di chuyển thế nào?
3. Có yêu cầu network isolation, encryption key riêng, audit log, thời hạn retention không?
4. Cơ chế xóa dữ liệu, khôi phục, xuất dữ liệu và rời dịch vụ có đáp ứng chính sách nội bộ không?
5. Ai chịu trách nhiệm thực thi quyền yêu cầu dữ liệu của khách hàng/người dùng?

Nếu không đáp ứng được các điều kiện đó, phương án managed có thể không phù hợp dù trải nghiệm triển khai đơn giản; ngược lại self-managed **không tự động đạt compliance** nếu đội vận hành thiếu biện pháp kiểm soát và bằng chứng kiểm toán.

## 8. Tính toán tổng chi phí sở hữu (TCO)

So **giá máy ảo** với **giá một instance managed** là so thiếu. TCO phải tính cả nhân công, rủi ro gián đoạn, backup, giám sát, mạng, nâng cấp và license.

### 8.1. Công thức khái niệm

~~~text
TCO self-managed / kỳ
  = compute + storage + network + license/support
  + backup/DR + monitoring/security tooling
  + DBA/SRE time + upgrade/incident cost
  + expected risk cost

TCO managed / kỳ
  = subscription/usage + storage/compute tier
  + network/egress/private connectivity
  + support/add-ons + ứng dụng và data engineering
  + migration cost + expected risk cost
~~~

Đây là **khung hạng mục**, không phải công thức định giá Neo4j. Một số hạng mục đã nằm trong giá managed; phải tránh **đếm hai lần**. Tương tự, bản self-managed có thể chịu license Enterprise/support hoặc chi phí cloud khác nhau.

### 8.2. Chi phí theo chu kỳ tăng trưởng

Khi 10 triệu node tăng thành 100 triệu node, số relationship và kích thước property có thể tăng theo tốc độ khác. Cần dự báo:

- Disk + transaction logs + backup retention.
- Page cache, heap và memory overhead cho truy vấn/algorithms.
- CPU phục vụ scan, expand path, sort, `MERGE` và import.
- Network egress giữa ứng dụng và database, nhất là cross-region.
- Chi phí downtime khi hết dung lượng hoặc query timeout.
- Chi phí nâng cấp tier hoặc mở rộng cluster.

**Tự quản lý có thể tiết kiệm** ở quy mô lớn và đội đã có hạ tầng, **managed có thể tiết kiệm** khi số giờ vận hành và rủi ro sự cố là thành phần đáng kể. Không có một chiều hướng chi phí đúng cho mọi workload.

### 8.3. Dự báo bằng phép đo thay vì đoán

Thay vì mua cấu hình dựa trên số node đơn thuần:

1. Sinh bộ dữ liệu **đại diện**, gồm tỷ lệ relationship theo node.
2. Chạy bộ query thật từ ứng dụng Java/SDN.
3. Đo p50/p95/p99, queries/s, transaction rollback, CPU, memory, page cache và độ trễ lấy kết nối.
4. Thử import, index build, snapshot/restore và lúc cao điểm.
5. Đo ở nhiều cấu hình tương ứng phương án đang so sánh, cùng truy vấn và tham số.

Một query có độ dài đường đi tăng không giới hạn hoặc thiếu index có thể phá vỡ mọi dự báo chi phí dựa trên node count.

## 9. Ma trận quyết định và thứ tự ưu tiên

Dùng bảng dưới đây như **điểm bắt đầu để thảo luận**, không phải công thức máy móc.

| Tiêu chí | Thường nghiêng về self-managed | Thường nghiêng về managed |
|---|---|---|
| Tùy chỉnh hệ điều hành, JVM và hạ tầng | Cần kiểm soát sâu | Không cần can thiệp nền tảng |
| Custom Java procedure / plugin chưa được dịch vụ hỗ trợ | Có nhu cầu bắt buộc | Không cần hoặc có giải pháp thay thế |
| Nhân sự trực và quy trình DBA/SRE | Có đội và automation trưởng thành | Đội nhỏ, muốn giảm vận hành nền |
| Region/network đặc biệt | Hạ tầng riêng đáp ứng tốt hơn | Gói cung cấp đúng region/private connectivity |
| HA/backup | Đội có thiết kế, diễn tập và giám sát | Gói có cơ chế và điều khoản đáp ứng RPO/RTO |
| Lịch nâng cấp | Phải chủ động kiểm soát từng giai đoạn | Chấp nhận chu kỳ/cửa sổ do dịch vụ quy định |
| Tốc độ tạo môi trường mới | Có infrastructure automation sẵn | Ưu tiên triển khai nhanh và ít thao tác |
| Khả năng quan sát nội bộ | Cần host-level access và agent riêng | Dashboard/metrics/API của dịch vụ đã đủ |
| Dự toán chi phí | Hạ tầng sẵn, tải ổn định, đội vận hành mạnh | Muốn gom nhiều chi phí nền thành dịch vụ |

### Cách chấm điểm có kiểm soát

Trước khi chấm điểm, **loại các phương án không đáp ứng điều kiện bắt buộc**. Sau đó cho từng tiêu chí còn lại:

~~~text
score(option) = SUM(weight_i * fit(option, criterion_i))

weight_i: mức quan trọng tương đối (ví dụ tổng = 100)
fit: mức phù hợp (ví dụ từ 1 đến 5)
~~~

Ví dụ bảng đánh giá do một nhóm **tự điền**:

| Tiêu chí | Trọng số | Self-managed (1–5) | Managed (1–5) |
|---|---:|---:|---:|
| Giảm số giờ trực vận hành | 25 | 2 | 5 |
| Tùy biến plugin bắt buộc | 25 | 5 | 1 |
| Đảm bảo kế hoạch phục hồi | 20 | 3 | 4 |
| Phù hợp network và region | 20 | 4 | 4 |
| Tốc độ triển khai | 10 | 3 | 5 |

Với **điểm giả định** trên:

~~~text
Self-managed = 25*2 + 25*5 + 20*3 + 20*4 + 10*3 = 345 / 100 = 3.45
Managed      = 25*5 + 25*1 + 20*4 + 20*4 + 10*5 = 360 / 100 = 3.60
~~~

Managed có tổng điểm cao hơn rất ít, nhưng **nếu custom plugin là điều kiện bắt buộc và không được dịch vụ hỗ trợ**, phương án managed vẫn phải bị loại. Mục đích chấm điểm là làm rõ đánh đổi, không thay thế kiểm tra yêu cầu cứng.

## 10. Một triển khai self-managed tối thiểu để học

Ví dụ **Docker Compose một Neo4j standalone** để chạy bài thử trên máy cục bộ, **không phải cấu hình production HA**:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
~~~

Biến môi trường `NEO4J_PASSWORD` được lấy từ môi trường local (hoặc giải pháp quản lý secret thích hợp); **không đặt giá trị mật khẩu thật trong Git**. Tệp Compose này chỉ dùng để minh họa:

- `7474`: HTTP (Neo4j Browser/UI khi được bật).
- `7687`: Bolt cho Java Driver.
- `127.0.0.1`: chỉ mở port trên loopback máy host, không phơi trực tiếp dịch vụ ra Internet.
- Volume dữ liệu giúp container dừng/khởi động lại không tự làm mất dữ liệu trong volume.

**Nhưng volume không phải backup.** Mất volume, lỗi logic, corruption hoặc bị xóa vẫn cần quy trình sao lưu/khôi phục độc lập.

### Những gì phải bổ sung trước production

1. Quyết định edition/license và kiến trúc standalone/cluster theo SLO.
2. Storage class, disk throughput, durability và dự báo dung lượng.
3. TLS, firewall, DNS, user/role và secret rotation.
4. Backup được diễn tập restore, retention ngoài môi trường chính.
5. Metrics/log/alert, tổng hợp sức khỏe hạ tầng và query latency.
6. Cửa sổ nâng cấp, version pinning và kiểm tra rollback.
7. Resource limit, heap, page cache, query timeout và connection pooling được đo thực tế.
8. Kế hoạch lỗi zone/host, cảnh báo hết dung lượng và cơ chế trực sự cố.

Không nhầm **“container đang chạy”** với **“dịch vụ đáp ứng RPO/RTO và SLA production”**.

## 11. Kết nối một dịch vụ quản lý từ Java Driver

Với AuraDB hoặc endpoint Neo4j hỗ trợ TLS/routing, ứng dụng Java Driver thường chỉ cần thay đổi **URI, credential, database đích và chính sách kết nối** mà không phải viết lại mọi truy vấn.

Ví dụ Java 17+ với Neo4j Java Driver phiên bản hỗ trợ:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderLookup {
    private OrderLookup() {}

    public static void main(String[] args) {
        // Ví dụ cho dịch vụ AuraDB:
        // NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");
        String database = System.getenv().getOrDefault("NEO4J_DATABASE", "neo4j");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                var result = session.executeRead(tx -> tx.run("""
                        MATCH (o:Order {orderId: $orderId})
                        RETURN o.orderId AS orderId,
                               o.amount AS amount
                        """, Map.of("orderId", "O01")).single());

                System.out.println("orderId=" + result.get("orderId").asString());
                System.out.println("amount=" + result.get("amount").asLong());
            }
        }
    }
}
~~~

**Giải thích:**

- `NEO4J_URI` và credential phải lấy từ **secret/config management**, không mã hóa cứng trong source hoặc container image.
- Với AuraDB, `neo4j+s://` là ví dụ thông dụng để kết nối an toàn; xác nhận **URI chính xác** do instance cung cấp.
- Chỉ rõ tên database, không dựa hoàn toàn vào mặc định khi vận hành nhiều DB/instance.
- `verifyConnectivity()` cho biết kết nối và xác thực cơ bản đã sẵn sàng, **không** chứng minh quyền đọc toàn bộ graph hoặc truy vấn đủ nhanh.
- `executeRead(...)` quản lý transaction đọc và retry theo chính sách driver; nếu cùng request phải gọi nhiều hệ thống, vẫn cần quản lý timeout và tracing.
- Trong dịch vụ server thật, tái sử dụng **Driver** lâu dài (thường một bean singleton), mở/đóng **Session** theo thao tác; không tạo mới Driver cho mỗi HTTP request.

Với self-managed cluster, URI cũng có thể sử dụng routing scheme phù hợp. Đừng thay mọi URI bằng `bolt://localhost:7687` khi di chuyển lên cluster: driver phải tìm được các địa chỉ routing công bố và có kết nối mạng tới chúng.

### Spring Data Neo4j

Cấu hình Spring Boot có thể tách theo môi trường:

~~~yaml
spring:
  neo4j:
    uri: "${NEO4J_URI}"
    authentication:
      username: "${NEO4J_USERNAME}"
      password: "${NEO4J_PASSWORD}"
  data:
    neo4j:
      database: "${NEO4J_DATABASE:neo4j}"
~~~

Sau khi chuyển endpoint, **không chỉ kiểm tra “Spring context khởi động được”**. Chạy integration test thật để xác minh repository derived query, `@Query`, mapping relationship, transaction rollback, uniqueness constraint và các phần có dùng APOC/GDS.

## 12. Query và mô hình dữ liệu có thật sự chuyển được không?

Một database mới rỗng với cùng phiên bản Neo4j **chưa đủ** để ứng dụng hoạt động đúng. Phải kiểm tra:

| Thành phần | Cần xác minh |
|---|---|
| Node/relationship | Đúng label, relationship type, hướng cạnh và thuộc tính |
| Identifier | Tính duy nhất theo khóa nghiệp vụ; không phụ thuộc `elementId()` như khóa di chuyển |
| Schema | Range index, text/full-text/vector index, constraints, trạng thái `ONLINE` |
| Cypher | Hỗ trợ đúng ngôn ngữ/phiên bản, query semantics, procedure |
| Dữ liệu kiểu đặc biệt | Date/time, point, list, số nguyên/thực và giá trị null/thiếu |
| APOC/GDS | Đúng function/procedure, version và quyền thực thi |
| Import pipeline | Source URL/file/`LOAD CSV` và đường dẫn nhìn từ server |
| Java Driver/SDN | Driver compatibility, entity mapping, transaction semantics |
| Tìm kiếm/thuật toán | Kế hoạch thực thi, index cần dùng, graph projection và bộ nhớ cần thiết |
| Bảo mật | User/role/privileges, TLS, secrets và network policies |

Ví dụ đếm bằng Cypher theo khóa và relationship:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers,
       count(DISTINCT c.customerId) AS distinctCustomerIds;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders,
       coalesce(sum(o.amount), 0) AS totalAmount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

Số lượng **không đủ** để chứng minh hai graph giống nhau: có thể cùng 1 triệu relationship nhưng nối sai cặp node. Nên kiểm tra checksum/tập khóa, các mẫu quan hệ quan trọng và truy vấn nghiệp vụ đại diện.

## 13. Kế hoạch di chuyển từng bước

Di chuyển giữa self-managed và managed là một **dự án chuyển hệ thống dữ liệu**, không chỉ thay connection string.

~~~mermaid
flowchart TD
    A["Thu thập yêu cầu và baseline"] --> B["Kiểm tra tương thích<br/>version, plugin, network"]
    B --> C["Chuẩn bị instance đích<br/>schema, quyền, secrets"]
    C --> D["Nạp dữ liệu ban đầu"]
    D --> E["Đối soát node, edge, thuộc tính"]
    E --> F["Chạy integration/load/restore tests"]
    F --> G{"Đạt điều kiện cutover?"}
    G -->|Không| H["Khắc phục và kiểm thử lại"]
    H --> E
    G -->|Có| I["Chốt nguồn ghi, đồng bộ delta,<br/>đổi endpoint"]
    I --> J["Theo dõi SLO và đối soát"]
    J --> K["Ổn định, đóng kế hoạch rollback"]
~~~

### Bước 1 — Lấy baseline

Ghi lại phiên bản Neo4j, edition, kích thước graph, schema, tần suất cập nhật, query quan trọng và p95/p99 latency. Lưu tiêu chí **bắt buộc giữ nguyên**: số lượng node/relationship theo khóa, nghiệp vụ không mất đơn, RPO/RTO, quyền truy cập.

### Bước 2 — Kiểm tra compatibility và quyền

Không chọn phương án đích nếu:

- Có custom Java procedure không thể cài và chưa có cách thay thế.
- Quy trình backup/export không đáp ứng luật lưu trữ.
- Không thể nối từ private network hiện tại.
- Cần tính năng Cypher/enterprise capability mà gói đích không hỗ trợ.

### Bước 3 — Chuẩn bị database và schema

Tạo database đích, credential và vùng mạng, sau đó triển khai index/constraint thích hợp. Với dữ liệu lớn, thứ tự import và build index có thể ảnh hưởng thời gian; riêng các upsert dùng `MERGE` theo khóa thường cần index/constraint từ trước.

### Bước 4 — Nạp và đồng bộ dữ liệu

Chọn cơ chế phù hợp với môi trường: công cụ backup/restore được hỗ trợ, export/import, `LOAD CSV`, application batch qua Java Driver hoặc cơ chế đồng bộ CDC/streaming nếu đã có trong thiết kế. **Không giả định mọi công cụ hoặc backup file từ self-managed có thể restore trực tiếp vào mọi gói AuraDB**.

Nếu nguồn vẫn nhận ghi khi import nền, phải có cách nạp **delta** hoặc một khoảng **write freeze** có chủ đích. Nếu không, snapshot đích có thể bỏ lỡ bản ghi cập nhật sau khi copy.

### Bước 5 — Đối soát đúng dữ liệu và hành vi

So node count, relationship count, khóa định danh, thuộc tính quan trọng, chỉ số tổng hợp và các truy vấn đường đi. Chạy kiểm thử với **bộ tham số thực**, nhất là graph có quan hệ một-nhiều để phát hiện nhân số hàng.

### Bước 6 — Đo tải và failover

Chạy load test trên database đích bằng workload đại diện, giới hạn tài nguyên phù hợp; đo p95/p99, queries/s, rollback, deadlock, connection pool wait và chi phí. Với HA/backup, phải có bằng chứng phục hồi hoặc SLA phù hợp thay vì giả định “đã chuyển cloud nên an toàn”.

### Bước 7 — Cutover và rollback

Tại thời điểm chuyển:

1. Chốt thời điểm, phạm vi thay đổi và người chịu trách nhiệm.
2. Tạm dừng ghi hoặc bật cơ chế đồng bộ cuối theo thiết kế.
3. Chạy kiểm tra dữ liệu delta, schema và read/write smoke tests.
4. Đổi `NEO4J_URI`/secrets/database theo cách deploy có kiểm soát.
5. Quan sát lỗi kết nối, p95/p99, query failures và số lượng sự kiện nghiệp vụ mới.
6. Giữ phương án rollback/failback rõ ràng: **trở về nguồn cũ không an toàn nếu đã có ghi mới chỉ tồn tại ở đích**. Phải có chính sách replay/đối soát dữ liệu trước khi quay lại.

Rollback là một **kịch bản dữ liệu**, không chỉ là khôi phục cấu hình URI.

## 14. Vận hành sau triển khai: bảng điều khiển tối thiểu

Với cả hai mô hình, cần một bộ tín hiệu từ **ứng dụng lẫn database**:

| Tín hiệu | Nguồn | Ý nghĩa |
|---|---|---|
| API p50/p95/p99 và error ratio | Micrometer/OpenTelemetry/application logs | Chất lượng trải nghiệm thực |
| Query latency và failure rate | Neo4j metrics/logs được môi trường hỗ trợ | Query chậm hay lỗi |
| Transaction commit/rollback | Neo4j metrics | Tải, thất bại và retry |
| Lock contention / transaction chờ | `SHOW TRANSACTIONS` hoặc metrics hỗ trợ | Giao dịch giữ khóa lâu, hot node |
| Bolt connections / driver pool wait | Neo4j + Java instrumentation | Nghẽn kết nối/routing |
| CPU, memory, page cache, disk | Hạ tầng self-managed hoặc chỉ số managed cung cấp | Sức khỏe tài nguyên |
| Backup/restore status | Hệ thống backup hoặc dịch vụ quản lý | Khả năng phục hồi |
| Dung lượng và tăng trưởng | Schema/data sizing, storage dashboard | Nguy cơ hết tài nguyên, tăng chi phí |

Không phải gói managed nào cũng cho truy cập host metric hay mọi trường trong query log. Khi xây dashboard, phân biệt **chỉ số thực có thể thu** với chỉ số mong muốn; phần thiếu phải được quản lý như **rủi ro quan sát**, không điền giá trị 0 giả.

### Runbook sự cố nên có

**Khi API không kết nối Neo4j:**

1. Kiểm tra DNS, Bolt URI, TLS certificate, network rule/private endpoint.
2. Xem lỗi Driver: `ServiceUnavailableException`, `SessionExpiredException`, `AuthenticationException`, timeout.
3. Kiểm tra trạng thái instance/cluster, incident thông báo từ nhà cung cấp nếu managed.
4. Không retry vô hạn với truy vấn ghi thiếu khóa idempotency.
5. Ghi nhận thời điểm, tác động, nguyên nhân và đường khôi phục.

**Khi truy vấn chậm:**

1. Phân biệt latency API, pool wait, query execution và lock wait.
2. Lấy Cypher thực tế, chạy `EXPLAIN`/`PROFILE` trong môi trường phù hợp.
3. Kiểm tra index, `Rows`, `DB Hits` và fan-out của relationship.
4. So tải đọc/ghi, CPU, memory, page cache, đợt import cùng thời điểm.

Nếu vấn đề thuộc nền tảng managed, gửi case hỗ trợ kèm thời điểm, instance ID, query ID hoặc metric đã làm sạch — **không gửi mật khẩu hay dữ liệu nhạy cảm**.

## 15. Ba kịch bản ra quyết định

### Kịch bản A — MVP graph cho đội nhỏ

Một nhóm bốn kỹ sư xây API giới thiệu bạn bè, chưa có SRE/DBA trực 24/7, dùng `MATCH`, `MERGE`, constraint và Java Driver, không cần plugin tùy biến. Dữ liệu không bị ràng buộc đặc biệt về nơi lưu trữ.

**Ứng viên hợp lý:** managed Neo4j, nếu gói chọn đáp ứng budget, network và ngưỡng tài nguyên. Đội vẫn phải theo dõi query, quyền, backup/restore và phát triển integration tests.

**Không kết luận:** managed đảm bảo tự động mọi SLA của API hoặc không còn cần tối ưu Cypher.

### Kịch bản B — Hệ thống quy định lưu dữ liệu nội bộ

Một tổ chức có data residency chặt, yêu cầu mọi bản sao/backup nằm trên hạ tầng đã kiểm toán, cần custom Java procedure, có đội vận hành Neo4j và chính sách DR.

**Ứng viên hợp lý:** self-managed trên môi trường được duyệt, **nếu** đội vận hành chứng minh được HA, restore, bảo mật, patch và chi phí. Managed chỉ được xem là phương án nếu một gói cụ thể **thỏa toàn bộ điều kiện bắt buộc**.

**Không kết luận:** tự quản lý mặc nhiên an toàn hơn. Thiếu backup drill hoặc phân quyền đúng có thể làm rủi ro cao hơn.

### Kịch bản C — Dịch vụ lớn, tăng trưởng nhanh

Hệ thống giao dịch phân tích các quan hệ nhiều hop, số lượng node/relationship tăng nhanh, có p99 latency nghiêm ngặt và các job import theo lô ban đêm.

**Cần proof-of-concept có đo đạc cả hai mô hình** thay vì chọn theo tên nhà cung cấp:

- Dataset có cùng phân phối bậc node và các đường đi.
- Truy vấn/param Java Driver giống nhau.
- Index/constraint và phiên bản Cypher tương đương.
- Đo cao điểm đọc/ghi, lock contention và ảnh hưởng job import.
- Tính tổng chi phí hạ tầng, egress, license, support và giờ vận hành.
- Thử sự cố và xác minh RPO/RTO.

Phương án phù hợp sẽ phụ thuộc kết quả kiểm chứng, không chỉ quy mô dữ liệu.

## 16. Checklist trước khi phê duyệt mô hình triển khai

| Câu hỏi kiểm tra | Bằng chứng tối thiểu |
|---|---|
| Mô hình đáp ứng region, luật dữ liệu, private networking? | Tài liệu kiến trúc và kiểm tra kết nối |
| Đáp ứng RPO, RTO và availability? | SLA/thiết kế + diễn tập hoặc bằng chứng phù hợp |
| Có hỗ trợ toàn bộ APOC/GDS/custom procedure bắt buộc? | Danh sách procedure thực chạy trên đích |
| Có phương án import dữ liệu lớn và delta? | Runbook, kết quả rehearsal, thống kê lỗi |
| Schema/index được tái tạo đầy đủ? | `SHOW CONSTRAINTS`, `SHOW INDEXES` và kiểm tra online |
| Query nghiệp vụ có kết quả và performance đạt SLO? | Integration/load tests trên dữ liệu đại diện |
| App có quyền tối thiểu, TLS, secret rotation? | Kết quả test quyền và security review |
| Có dashboard, alert và runbook? | Dashboard đang có dữ liệu, người trực được chỉ định |
| Chi phí trong giới hạn cả khi tăng trưởng? | Dự báo TCO theo nhiều kịch bản |
| Có kế hoạch cutover, failback và rollback dữ liệu? | Rehearsal + tiêu chí go/no-go |

**Quy tắc phê duyệt:** thiếu bằng chứng ở điều kiện bắt buộc phải được ghi là **chưa xác minh**, không tự chuyển thành “đạt” vì dịch vụ phổ biến hoặc demo chạy thành công.

## 17. Bài tập

### Bài 1 — Xác định trách nhiệm

Một service chạy trên AuraDB, query `MATCH` mở rộng nhiều quan hệ và gây timeout. Ai chịu trách nhiệm đầu tiên về cách viết Cypher? Có thể yêu cầu nhà cung cấp tự sửa query không?

**Đáp án gợi ý:** Đội ứng dụng/nhóm dữ liệu chịu trách nhiệm thiết kế và tối ưu query, kiểm tra index và dữ liệu. Nhà cung cấp chịu trách nhiệm nền tảng trong phạm vi gói và có thể hỗ trợ chẩn đoán, nhưng managed không tự sửa logic truy vấn nghiệp vụ.

### Bài 2 — RPO và RTO

Một tổ chức chỉ chấp nhận mất tối đa **10 phút dữ liệu** và cần phục hồi trong **45 phút**. Dịch vụ quảng cáo “sao lưu hằng ngày” và “độ sẵn sàng cao”. Đã đủ căn cứ chọn chưa?

**Đáp án:** Chưa. Sao lưu hằng ngày không chứng minh RPO ≤ 10 phút; HA không thay backup. Cần kiểm tra snapshot/recovery interval, SLA, phương án khôi phục, biên bản restore drill và xử lý tình huống region gặp sự cố.

### Bài 3 — Plugin tùy chỉnh

Một hệ thống có procedure Java riêng được gọi qua `CALL com.example.graph.recompute(...)`. Phương án managed không cho nạp JAR đó. Đội vẫn muốn chấm managed 5/5 vì tiết kiệm giờ SRE. Nên làm gì?

**Đáp án:** Nếu procedure là yêu cầu bắt buộc và chưa có thay thế, managed không đạt điều kiện cứng. Cần thiết kế thay thế bằng Cypher/Java service/GDS được hỗ trợ rồi thử lại, hoặc chọn self-managed. Không dùng điểm tổng hợp để bỏ qua sự không tương thích.

### Bài 4 — Migration không chỉ thay URI

Sau khi nạp 5 triệu node sang môi trường mới, `count(n)` bằng nguồn nhưng một số truy vấn `Customer-[:PLACED]->Order` sai. Nêu ít nhất bốn kiểm tra tiếp theo.

**Đáp án gợi ý:** So số relationship theo type/hướng; kiểm tra cặp khóa nguồn–đích của relationship; constraint/index; các property định danh và mapping; transaction import bị bỏ sót; truy vấn nghiệp vụ đại diện và lỗi từ pipeline. Node count bằng nhau không chứng minh cấu trúc graph giống nhau.

### Bài 5 — Tránh rollback sai khi cutover

Ứng dụng đã ghi đơn hàng mới lên database đích trong 30 phút. Đội muốn đổi `NEO4J_URI` về database cũ để “rollback nhanh”. Rủi ro là gì?

**Đáp án:** Database cũ có thể không chứa các đơn hàng chỉ ghi ở đích. Đổi URI ngay sẽ làm dữ liệu nghiệp vụ thiếu/không nhất quán. Phải có kế hoạch đồng bộ ngược, đối soát delta hoặc giữ ứng dụng ở chế độ an toàn cho đến khi dữ liệu được xử lý.

### Bài 6 — TCO

Một VM self-managed có giá niêm yết thấp hơn managed 40%, nhưng cần DBA/SRE trực ngoài giờ, backup ngoài vùng, diễn tập restore và hỗ trợ license. Có đủ căn cứ kết luận self-managed rẻ hơn không?

**Đáp án:** Không. Cần so TCO gồm hạ tầng, license, support, backup, network, nhân sự, giám sát, incident và mức rủi ro dự kiến theo cùng kỳ đo. So giá VM với subscription riêng lẻ là không tương đương.

## 18. Tài liệu tham khảo

- [Neo4j Aura documentation](https://neo4j.com/docs/aura/)
- [Neo4j Operations Manual](https://neo4j.com/docs/operations-manual/current/)
- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/)
- [Neo4j Operations Manual — Kubernetes](https://neo4j.com/docs/operations-manual/current/kubernetes/)
- [Neo4j Java Driver Manual — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)

Các trang `current` có thể thay đổi theo bản phát hành. Đặc biệt với **AuraDB, các tính năng backup/DR, tier, giới hạn network, APOC/GDS, quyền và giá** phải được xác minh trên **đúng dịch vụ/gói đang mua**; không suy từ hướng dẫn chung.

## 19. Ghi nhớ

- **Lựa chọn triển khai là quyết định về trách nhiệm vận hành và rủi ro**, không chỉ về chỗ đặt dữ liệu.
- **Self-managed** mang lại kiểm soát sâu, nhưng cần khả năng backup, restore, HA, patch, bảo mật, quan sát và trực sự cố.
- **Managed** giảm nhiều công việc vận hành nền tảng theo gói, nhưng **không** thay trách nhiệm của đội ứng dụng về Cypher, schema, dữ liệu, quyền, SLO và chi phí.
- **RPO, RTO, data residency, private networking và plugin bắt buộc là điều kiện cứng**; kiểm chứng trước khi chấm điểm phương án.
- **Đo workload thật và tính TCO đầy đủ**, so cả query latency, throughput, backup/DR, license, network và nhân sự.
- **Di chuyển Neo4j là di chuyển dữ liệu và ngữ nghĩa graph**, không chỉ đổi URI; phải có đối soát, cutover và kế hoạch failback an toàn.
