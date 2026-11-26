# Kiểm tra kết nối, dữ liệu và chỉ mục sau triển khai

## 1. Vì sao deploy thành công chưa có nghĩa ứng dụng đã sẵn sàng?

Trong module **DATABASE_ENGINE_GRAPH_NEO4J**, Neo4j là cơ sở dữ liệu **property graph** lưu node, relationship, property và các cấu trúc hỗ trợ truy vấn như index, constraint. Ứng dụng thường truy cập graph bằng **Cypher**, **Java Driver** hoặc **Spring Data Neo4j (SDN)**. Một lần triển khai có thể đồng thời thay đổi cấu hình kết nối, ứng dụng, schema, dữ liệu và phiên bản Neo4j.

Một pipeline báo **deployment SUCCESS** chỉ chứng minh các bước do pipeline thực hiện đã kết thúc. Nó **không bảo đảm**:

- Java Driver có thể kết nối từ đúng môi trường chạy ứng dụng, qua DNS/TLS và routing.
- Tài khoản ứng dụng có quyền đọc/ghi **đúng database** cần dùng.
- Dữ liệu được migration đầy đủ, đúng tenant, đúng loại và chiều relationship.
- Index đã ở trạng thái **ONLINE** thay vì còn **POPULATING** hoặc đã **FAILED**.
- Cypher quan trọng dùng kế hoạch thực thi có chi phí chấp nhận được.
- Sau khi bật lưu lượng, lỗi, độ trễ và hoạt động đọc sau ghi vẫn đạt yêu cầu.

Bài thuộc chương **Triển khai**, tập trung vào cách thiết kế một **post-deployment verification**: từ việc kiểm tra endpoint tới đánh giá graph, index và trải nghiệm của ứng dụng thật. Mỗi kiểm tra phải có **kỳ vọng và hành động khi thất bại**, không chỉ là một lệnh chạy cho có.

### 1.1. Ba câu hỏi cốt lõi

| Câu hỏi | Bằng chứng cần có | Ví dụ lỗi được phát hiện |
|---|---|---|
| **Kết nối được chưa?** | Driver kết nối, xác thực, chọn database, thực thi READ/WRITE theo vai trò | Mật khẩu cũ, TLS lỗi, URI sai, routing quảng bá host nội bộ |
| **Dữ liệu đúng chưa?** | Golden queries, count tại mốc được kiểm soát, khóa duy nhất, quan hệ và tenant scope | Migration thiếu cạnh, dữ liệu trùng, đọc nhầm tenant |
| **Chỉ mục sẵn sàng chưa?** | SHOW INDEXES, constraint, index state, EXPLAIN/PROFILE, đo truy vấn | Index FAILED, đang POPULATING, query bị full scan |

**Đạt một cột không thay thế hai cột còn lại.** Ví dụ **driver.verifyConnectivity()** có thể thành công trong khi database ứng dụng chưa ONLINE hoặc user thiếu quyền đọc node. Ngược lại, database ONLINE không bảo đảm endpoint Bolt/TLS từ pod ứng dụng có thể truy cập được.

## 2. Cổng kiểm tra theo thứ tự triển khai

Một quy trình gọn nhưng có chiều sâu gồm sáu cổng:

~~~mermaid
flowchart TD
  A["G0: Chốt phiên bản, backup, baseline"] --> B["G1: TLS/DNS/Bolt/routing và auth"]
  B --> C["G2: Database ONLINE và đúng quyền"]
  C --> D["G3: Dữ liệu, relationship, invariant"]
  D --> E["G4: Constraint/index ONLINE, query plan"]
  E --> F["G5: Java Driver/SDN smoke và canary"]
  F --> G{"Tất cả gate PASS?"}
  G -->|"Có"| H["Mở lưu lượng có kiểm soát + giám sát"]
  G -->|"Không"| I["Giữ hoặc dừng rollout, điều tra, xử lý/rollback"]
~~~

| Gate | Ai thường thực hiện | Tiêu chí đầu ra |
|---|---|---|
| **G0 — Baseline** | DevOps/DBA và nhóm ứng dụng | Biết bản nào vừa deploy, có nguồn đối soát và phương án phục hồi |
| **G1 — Connectivity** | Pipeline chạy từ môi trường app | Kết nối thực từ mạng ứng dụng thành công |
| **G2 — Database readiness** | DBA và service owner | Đúng database/role, trạng thái ONLINE, quyền phù hợp |
| **G3 — Graph data** | Nhóm nghiệp vụ/dữ liệu | Các bất biến quan trọng và đối soát migration đạt |
| **G4 — Schema/performance** | DBA, nhóm truy vấn | Index cần thiết ONLINE, constraint đúng, query trọng tâm không hồi quy |
| **G5 — Application smoke** | Nhóm Java/SDN | API/repository dùng dữ liệu đúng; không có lỗi vận hành trọng yếu |

Không mở 100% lưu lượng chỉ dựa vào **G1**. Nếu một gate thất bại, cần **phân loại blocker** và giữ kết quả kiểm thử để không lặp lại sự cố trong lần deploy sau.

## 3. Chuẩn bị baseline trước khi kiểm tra

Hệ thống có thể có nhiều database, nhiều tenant và nhiều phiên bản API. Vì vậy trước deploy hãy ghi rõ:

1. **Release:** commit/tag của ứng dụng, version Neo4j Server, Java Driver, Spring Data Neo4j và plugin APOC/GDS nếu sử dụng.
2. **Database đích:** tên thật của database, database alias nếu có, môi trường cluster/standalone/Aura và endpoint do quản trị viên cấp.
3. **Schema bắt buộc:** tên index, loại index, nhãn/relationship type, property, constraint, trường hợp uniqueness/key.
4. **Golden queries:** các truy vấn đại diện về đọc Customer, Order, quan hệ, hướng, dữ liệu thiếu và cô lập tenant.
5. **Recovery:** trạng thái backup gần nhất, cách restore hoặc rollback release, migration nào không thể đảo ngược.
6. **SLO:** p95/p99 latency, error rate, tỉ lệ request thành công và các chỉ số bộ nhớ/connection pool.

**Baseline không phải số đếm lấy tùy ý trước một thời điểm rồi so với dữ liệu đang ghi liên tục vài phút sau.** Nếu production luôn có đơn mới, **count(Order)** sau deploy có thể khác baseline một cách hoàn toàn hợp lệ. Cần snapshot/mốc đối soát, test tenant ổn định hoặc kiểm tra invariant không phụ thuộc tổng số dòng tại thời điểm đó.

### 3.1. Ví dụ dữ liệu thử nghiệm xuyên suốt bài

Trong **database thử nghiệm riêng**, tạo một fixture có cả trường hợp nhiều tenant dùng chung ID. Không chạy các lệnh **CREATE** sau nhiều lần trên cùng fixture vì có thể gặp uniqueness constraint.

~~~cypher
CREATE CONSTRAINT demo_deploy_customer_key IF NOT EXISTS
FOR (c:DemoDeployCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_deploy_order_key IF NOT EXISTS
FOR (o:DemoDeployOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoDeployCustomer {
    tenantId: 'shop-a', customerId: 'C-1', active: true
  }),
  (c2:DemoDeployCustomer {
    tenantId: 'shop-a', customerId: 'C-2', active: true
  }),
  (c3:DemoDeployCustomer {
    tenantId: 'shop-b', customerId: 'C-1', active: true
  }),
  (o1:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-1', amountMinor: 15000
  }),
  (o2:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-2', amountMinor: 8000
  }),
  (o3:DemoDeployOrder {
    tenantId: 'shop-a', orderId: 'O-3', amountMinor: 3000
  }),
  (o4:DemoDeployOrder {
    tenantId: 'shop-b', orderId: 'O-1', amountMinor: 9000
  }),
  (c1)-[:DEMO_DEPLOY_PLACED]->(o1),
  (c1)-[:DEMO_DEPLOY_PLACED]->(o2),
  (c2)-[:DEMO_DEPLOY_PLACED]->(o3),
  (c3)-[:DEMO_DEPLOY_PLACED]->(o4);
~~~

Kỳ vọng ban đầu: **3 Customer**, **4 Order**, **4 relationship DEMO_DEPLOY_PLACED**. ID **C-1** và **O-1** xuất hiện ở hai tenant, nên một query bỏ điều kiện **tenantId** có thể bị test phát hiện.

Sơ đồ:

~~~mermaid
flowchart LR
  subgraph SA["Tenant shop-a"]
    CA1["Customer C-1"] -->|PLACED| OA1["Order O-1"]
    CA1 -->|PLACED| OA2["Order O-2"]
    CA2["Customer C-2"] -->|PLACED| OA3["Order O-3"]
  end
  subgraph SB["Tenant shop-b"]
    CB1["Customer C-1"] -->|PLACED| OB1["Order O-1"]
  end
~~~

**Chỉ dùng fixture này ở staging/test.** Trên production, thay các nhãn **DemoDeploy...** bằng những truy vấn đọc theo data contract của ứng dụng đã được phê duyệt; không tự seed dữ liệu thử nghiệm rồi xóa bằng câu truy vấn rộng.

## 4. G1 — Kiểm tra DNS, TLS, Bolt và authentication

### 4.1. Phân biệt URI định tuyến và URI trực tiếp

Neo4j Java Driver kết nối qua giao thức Bolt. Scheme quyết định **routing** và **TLS**:

| URI | Kết nối | Khi phù hợp |
|---|---|---|
| **neo4j://host:7687** | Có routing, không bật TLS theo scheme | Mạng nội bộ thử nghiệm được cấu hình phù hợp |
| **neo4j+s://host:7687** | Có routing và TLS với chứng chỉ CA tin cậy | Cluster production và Aura theo URI được cấp |
| **neo4j+ssc://host:7687** | Có routing, chấp nhận chứng chỉ tự ký | Test có chính sách chứng chỉ rõ ràng |
| **bolt://host:7687** | Direct tới một server | Kiểm tra một instance cụ thể |
| **bolt+s://host:7687** | Direct và TLS CA tin cậy | Kết nối tới server cụ thể có mã hóa |

Trong cụm, dùng **neo4j+s://** (hoặc scheme routing được hệ thống cung cấp) để driver nhận routing table, gửi **executeRead** tới reader phù hợp và **executeWrite** tới writer của database. Chuyển thành **bolt+s://** để bỏ qua lỗi routing có thể chỉ khiến kết nối “tạm chạy” tới một server, rồi thất bại khi đổi leader.

**Không giảm xác thực TLS để xử lý lỗi certificate trên production.** Hãy kiểm tra hostname, SAN/CN của chứng chỉ, CA truststore, độ tin cậy chuỗi chứng chỉ và chính sách của tổ chức.

### 4.2. Kiểm tra từ đúng nơi ứng dụng sẽ chạy

Một máy laptop kết nối được Neo4j không chứng minh pod/container Java kết nối được. Cần kiểm tra từ **mạng ứng dụng thật** hoặc một job CI có cùng DNS, subnet, policy egress và cách lấy secret.

| Kiểm tra | Điều cần biết | Triệu chứng thường gặp |
|---|---|---|
| DNS | Hostname có phân giải được từ pod ứng dụng? | Unknown host |
| TCP/Bolt | Port có được phép qua firewall/NetworkPolicy? | Timeout, connection refused |
| TLS | Chứng chỉ có khớp hostname, CA và thời hạn? | SSL handshake/verification failure |
| Auth | Tài khoản, mật khẩu, token còn hợp lệ? | Authentication failure |
| Routing | Các địa chỉ mà cluster **advertise** có truy cập được từ app? | Seed kết nối được nhưng routing/driver timeout |
| Database | Tên database hoặc alias có tồn tại và đúng? | Database not found, query chạy nhầm database |
| Permissions | Role ứng dụng có quyền đọc/ghi đúng nhãn, thuộc tính? | Forbidden/permission error khi query |

Nếu một node trong routing table quảng bá hostname nội bộ không phân giải từ pod, driver có thể kết nối được seed nhưng không truy cập những thành viên còn lại. Nguyên nhân là **DNS/advertised address/network**, không phải lỗi cú pháp Cypher.

### 4.3. Java Driver: xác minh có thể tạo kết nối thật

**GraphDatabase.driver(...)** chủ yếu khởi tạo đối tượng driver. Kết nối mạng thường được tạo **khi cần**; gọi **verifyConnectivity()** mới chủ động kiểm tra khả năng kết nối.

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

String uri = System.getenv("NEO4J_URI");
String user = System.getenv("NEO4J_USERNAME");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(user, password))) {
    driver.verifyConnectivity();
    System.out.println("Neo4j connectivity OK");
}
~~~

**Không** hardcode mật khẩu hoặc in secret ra console. Trong Spring Boot, nên tạo **một Driver dùng chung** và để framework quản lý lifecycle; không tạo Driver mới cho mỗi HTTP request. Driver là đối tượng thread-safe và tương đối đắt; Session nhẹ hơn nhưng **không thread-safe** và phải được đóng.

Lời gọi thành công ở đây mới là **bằng chứng cấp kết nối**. Nó **không** chứng minh database đúng, data contract đạt, index ONLINE hay một truy vấn nghiệp vụ có thể thực thi.

## 5. G2 — Kiểm tra đúng database và trạng thái phục vụ

### 5.1. SHOW DATABASES trên Neo4j Enterprise

Với **Neo4j Enterprise** có quyền quản trị/phạm vi quan sát phù hợp, chạy trong ngữ cảnh **system**:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus, access, statusMessage
WHERE name = 'neo4j'
RETURN name, currentStatus, requestedStatus, access, statusMessage;
~~~

Kỳ vọng minh họa:

~~~text
name     currentStatus  requestedStatus  access       statusMessage
neo4j    online         online           read-write   ""
~~~

**Đọc đúng ý nghĩa các trường:**

- **requestedStatus**: trạng thái quản trị mong muốn, ví dụ **online**.
- **currentStatus**: trạng thái thực tế, có thể là **starting**, **store copying**, **offline**, **dirty**, **quarantined** hoặc **online**.
- **access**: database đang ở **read-write** hay **read-only**; một ứng dụng ghi không được coi là sẵn sàng nếu database đang read-only ngoài kế hoạch.
- **statusMessage**: thông tin liên quan lỗi/đang chuyển trạng thái.

Thao tác **CREATE/START DATABASE** có thể hoàn tất lệnh quản trị trước khi database thực sự ONLINE, vì chuyển trạng thái có thể **bất đồng bộ**. Chỉ cho qua gate khi trạng thái thực đã đáp ứng điều kiện của workload. Với database đang copy store, đợi/cảnh báo theo chính sách, không tự DROP hoặc RESTORE khi chưa điều tra.

**Lưu ý Edition:** thao tác liệt kê/quản trị nhiều database và các cột chi tiết bằng **SHOW DATABASES** trong tài liệu vận hành là chức năng **Enterprise Edition**. Với môi trường Community hoặc Aura bị giới hạn quyền quản trị, xác minh bằng công cụ/đường quan sát được hỗ trợ và **thực thi truy vấn đọc trên database thực tế**; không coi lỗi thiếu quyền SHOW DATABASES là bằng chứng database đang down.

### 5.2. Chọn database tường minh trong Java Driver

~~~java
import org.neo4j.driver.SessionConfig;

String dbName = System.getenv("NEO4J_DATABASE");
try (var session = driver.session(
        SessionConfig.forDatabase(dbName))) {
    String database = session.executeRead(tx ->
        tx.run("CALL db.info() YIELD name RETURN name")
          .single().get("name").asString());
    System.out.println(database);
}
~~~

**CALL db.info() YIELD name RETURN name** dùng để xác minh database thực sự phục vụ truy vấn, thay vì suy đoán theo home database. Ứng dụng cần so sánh với database đích đã cấu hình; chỉ log tên database, không log mật khẩu.

Nếu dùng multi-database và alias, phân biệt **tên/alias phía client** với database thực được Neo4j định tuyến. Ví dụ Java ở mục 8 đối chiếu với tên database thực; nếu **NEO4J_DATABASE** được cố ý đặt thành alias, phải đối chiếu với **tên database đích đã phê duyệt** thay vì so bằng chuỗi alias. Quan trọng là truy vấn được phục vụ từ dữ liệu đúng mà ứng dụng đã chấp thuận.

### 5.3. Quyền tối thiểu phải được kiểm tra bằng chính tài khoản ứng dụng

Admin chạy câu Cypher thành công **không chứng minh** tài khoản API có quyền chạy nó. Cần thử bằng chính credential hoặc impersonation được triển khai:

~~~cypher
MATCH (c:DemoDeployCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS customerId;
~~~

Nếu không có hàng, phải phân biệt **không tồn tại dữ liệu**, **role không nhìn thấy node/property** hoặc **tham số sai**. Trên Neo4j Enterprise có fine-grained privileges, quyền **TRAVERSE** và **READ** có thể lọc dữ liệu mà user nhìn thấy. Một câu **RETURN 1** không kiểm tra được quyền đọc graph.

Kiểm thử WRITE bằng tài khoản ứng dụng chỉ nên thực hiện trên **staging** hoặc bằng canary riêng được thiết kế đầy đủ, không tạo node thử nghiệm tùy tiện trên production rồi xóa bằng nhãn rộng.

## 6. G3 — Kiểm tra dữ liệu, relationship và tính toàn vẹn nghiệp vụ

### 6.1. Kiểm tra golden query theo business key

Trên fixture mục 3, truy vấn danh sách Order từ một Customer:

~~~cypher
MATCH (c:DemoDeployCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_DEPLOY_PLACED]->(o:DemoDeployOrder)
RETURN o.orderId AS orderId, o.amountMinor AS amountMinor
ORDER BY orderId;
~~~

Với **tenantId = 'shop-a', customerId = 'C-1'**, kỳ vọng:

~~~text
O-1   15000
O-2    8000
~~~

Với **shop-a / C-2**, kỳ vọng **O-3**; với **shop-b / C-1**, kỳ vọng **O-1** của **shop-b** chứ không bao gồm các Order shop-a.

**Không bỏ tenantId** trong MATCH nếu nghiệp vụ yêu cầu cô lập tenant. Một truy vấn có vẻ “đúng” trên dữ liệu ít có thể trả nhầm đơn ngay khi hai tenant có mã khách hàng giống nhau.

### 6.2. Kiểm tra số lượng ở môi trường có fixture cố định

~~~cypher
MATCH (c:DemoDeployCustomer)
RETURN count(c) AS customers;
~~~

~~~cypher
MATCH (o:DemoDeployOrder)
RETURN count(o) AS orders;
~~~

~~~cypher
MATCH (:DemoDeployCustomer)-[r:DEMO_DEPLOY_PLACED]->
      (:DemoDeployOrder)
RETURN count(r) AS placedRelationships;
~~~

Kỳ vọng lần lượt **3, 4, 4**, nhưng **chỉ đúng khi fixture không bị thay đổi**. Trong production có ghi liên tục, tổng count thường chỉ dùng như **một tín hiệu** kết hợp snapshot/manifest; không lấy số đếm giữa hai thời điểm khác nhau làm tiêu chí PASS/FAIL cứng.

### 6.3. Kiểm tra trùng định danh và thiếu khóa

~~~cypher
MATCH (o:DemoDeployOrder)
WITH o.tenantId AS tenantId,
     o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, orderId, copies;
~~~

Kết quả phải **không có hàng**. Đồng thời:

~~~cypher
MATCH (o:DemoDeployOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS ordersMissingId;
~~~

Kỳ vọng **0**. **Uniqueness constraint** bảo vệ giá trị định danh khi chúng có mặt, nhưng **không tự bắt buộc mọi node phải có đủ property**; chính sách tạo dữ liệu hoặc **key/existence constraint** khi edition hỗ trợ phải bảo vệ phần này.

### 6.4. Kiểm tra relationship đúng hướng và đúng tenant

~~~cypher
MATCH (c:DemoDeployCustomer)-[r:DEMO_DEPLOY_PLACED]->
      (o:DemoDeployOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

Kỳ vọng **0**. Kiểm tra Order không có đúng một Customer nguồn:

~~~cypher
MATCH (o:DemoDeployOrder)
OPTIONAL MATCH (c:DemoDeployCustomer)-[:DEMO_DEPLOY_PLACED]->(o)
WITH o, count(c) AS placedBy
WHERE placedBy <> 1
RETURN o.tenantId AS tenantId,
       o.orderId AS orderId,
       placedBy;
~~~

Kết quả phải **không có hàng** nếu domain yêu cầu mỗi Order chỉ có đúng một Customer đặt. **count(c)** cho biết số liên kết khớp, nên cũng phát hiện relationship trùng giữa cùng hai node. Tuy nhiên, nếu nghiệp vụ cho phép nhiều Customer cùng tham gia một Order, cần thay invariant cho phù hợp.

**Cẩn thận với NULL:** điều kiện **c.tenantId <> o.tenantId** không phát hiện được đầy đủ trường hợp một phía thiếu tenantId. Hãy kết hợp với kiểm tra **IS NULL** cho cả Customer và Order nếu data contract yêu cầu chúng bắt buộc.

### 6.5. Kiểm tra migration hai pha

Giả sử phiên bản cũ lưu **o.legacyCustomerId**, phiên bản mới dùng relationship **DEMO_DEPLOY_PLACED**. Trong giai đoạn triển khai chuyển tiếp:

1. Chạy query cũ trên dữ liệu có property.
2. Chạy query mới trên relationship đã được migration.
3. So **tập business key** và dữ liệu thuộc tính liên quan, không chỉ tổng số hàng.
4. Kiểm tra những Order chưa có relationship, relationship sai tenant và bản ghi không tìm thấy Customer.
5. Chỉ bỏ property cũ sau khi tất cả writer/reader đã chuyển và được đối soát.

Nếu migration chạy theo batch và batch cuối lỗi, phần dữ liệu đã commit có thể tồn tại **nửa cũ nửa mới**. Rollout phải có khả năng **dual-read/dual-write có kiểm soát** hoặc tạm ngừng những chức năng phụ thuộc trong thời gian chuyển đổi.

### 6.6. Kiểm tra dựa trên mốc dữ liệu, không dựa vào may mắn

Trong cluster, một read query đi tới reader có thể chưa thấy transaction vừa commit trên writer nếu session không được liên kết nhân quả. Khi một smoke test ghi canary rồi đọc lại trên reader, phải dùng **bookmarks** trong cùng Session, hoặc chuyển bookmarks giữa các Session; không dùng **Thread.sleep** tùy ý và coi đủ chắc chắn.

Trong môi trường mà mỗi request app độc lập có thể chấp nhận eventual consistency, không cần cưỡng ép bookmark toàn hệ thống. Ngược lại, với API tạo Order rồi đọc lại Order vừa tạo, bảo đảm **read-your-writes** là một phần của data contract cần kiểm tra.

## 7. G4 — Kiểm tra constraint và index sau migration

### 7.1. SHOW CONSTRAINTS: có đúng ràng buộc cần thiết không?

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_deploy_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Trên fixture, kỳ vọng có **demo_deploy_customer_key** và **demo_deploy_order_key**, đều là uniqueness constraint có cặp property đúng. Nếu application contract yêu cầu business key có cả **tính tồn tại và duy nhất**, cần đánh giá **node key** (Enterprise) hoặc cơ chế tương đương; không ngầm cho rằng uniqueness bao gồm NOT NULL.

**Lưu ý quyền:** **SHOW CONSTRAINTS** cần privilege tương ứng. Một tài khoản API hạn chế có thể **không được phép** xem metadata; pipeline quan sát schema nên dùng role vận hành riêng thay vì cấp thêm quyền quản trị cho ứng dụng.

### 7.2. SHOW INDEXES: ONLINE không phải POPULATING

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent,
      entityType, labelsOrTypes, properties, owningConstraint
RETURN name, type, state, populationPercent,
       entityType, labelsOrTypes, properties, owningConstraint
ORDER BY name;
~~~

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Quyết định sau deploy |
|---|---|---|
| **ONLINE** | Index được tạo xong và sẵn sàng phục vụ | Có thể tiếp tục kiểm tra truy vấn |
| **POPULATING** | Index đang được xây dựng từ dữ liệu | Chưa PASS nếu query cần index để bảo đảm SLO |
| **FAILED** | Tạo hoặc duy trì index gặp lỗi | FAIL gate, xem **failureMessage**, log và tài nguyên |

**populationPercent = 100** chỉ là tín hiệu phụ; tiêu chí sẵn sàng là **state = ONLINE**. Nếu index thuộc constraint, trường **owningConstraint** giúp xác định nó được tạo làm cấu trúc hỗ trợ cho ràng buộc.

Những loại index khác nhau có mục đích khác nhau: **RANGE**, **TEXT**, **POINT**, **FULLTEXT**, **VECTOR**, **LOOKUP**. Không thay một index RANGE bằng LOOKUP rồi cho rằng mọi query theo property đều được tăng tốc như cũ. Đối với full-text/vector index có cơ chế cập nhật/độ nhất quán riêng, phải kiểm tra thêm bằng **truy vấn chức năng thực tế**.

### 7.3. Chờ index với timeout rõ ràng

Nếu migration vừa thêm index, có thể chờ index ONLINE bằng procedure:

~~~cypher
CALL db.awaitIndex('demo_deploy_order_key', 300);
~~~

hoặc chờ toàn bộ index:

~~~cypher
CALL db.awaitIndexes(300);
~~~

Hai procedure nhận timeout bằng giây. **Không chờ vô hạn** trong pipeline; nếu hết timeout, gate phải đánh dấu chưa đạt và kiểm tra index vẫn đang POPULATING hay FAILED. **db.awaitIndexes()** có thể đợi những index không liên quan tới release; khi chỉ cần một index quan trọng, dùng **db.awaitIndex(...)** theo tên được duyệt.

**Cần xem quyền thực thi procedure** và khả năng hỗ trợ trên server/edition hiện tại; nếu không dùng được, có thể polling **SHOW INDEXES** theo lịch với timeout và điều kiện dừng rõ.

### 7.4. Một index ONLINE chưa chứng minh query đang dùng index

Chạy **EXPLAIN** với query nghiệp vụ và tham số đại diện:

~~~cypher
EXPLAIN
MATCH (o:DemoDeployOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.amountMinor AS amountMinor;
~~~

Planner có thể chọn **NodeUniqueIndexSeek**, **NodeIndexSeek** hoặc một đường truy cập khác tùy constraint, dữ liệu, phiên bản và thống kê. Mục tiêu là xem **có đường truy cập có chọn lọc**, không cố ép đúng tên một operator ở mọi phiên bản.

**EXPLAIN không chạy truy vấn**, còn **PROFILE** sẽ chạy thật:

~~~cypher
PROFILE
MATCH (o:DemoDeployOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.amountMinor AS amountMinor;
~~~

Trên **read-only query**, PROFILE thuận tiện để xem **Rows**, **DB Hits**, page cache và bộ nhớ khi có hỗ trợ. **Không dùng PROFILE trên migration hoặc lệnh ghi ở production** chỉ để xem kế hoạch, vì PROFILE thực thi và có thể làm thay đổi graph.

### 7.5. So sánh hiệu năng với baseline

| Chỉ số | Ý nghĩa | Cảnh báo |
|---|---|---|
| **Rows** trên từng toán tử | Mức fan-out trung gian | Một bước Expand sinh quá nhiều hàng |
| **Estimated Rows** | Ước lượng của planner | Chênh lệch lớn với Rows |
| **DB Hits** | Lượng thao tác truy cập dữ liệu | Tăng mạnh sau khi thiếu index/đổi plan |
| **Index Seek/Scan** | Phương thức truy cập | Từ seek chuyển sang scan khi dữ liệu rất lớn |
| **p95/p99 latency** | Trải nghiệm và SLO ở tải đại diện | Hồi quy trong nhiều lần đo |
| **Memory/Page cache** | Áp lực tài nguyên | Page cache miss, GC hoặc bộ nhớ tăng |

Không so thời gian từ một query chạy ở laptop trước deploy với query chạy trên production đầy tải sau deploy rồi kết luận do index. Để đánh giá đúng, dùng cùng phân phối tham số, dữ liệu tương đương, phiên bản được ghi rõ và điều kiện tải đại diện.

Không nên đặt điều kiện “mọi query phải có index seek”. Truy vấn trả một phần lớn graph có thể dùng scan hợp lý; kiểm tra nên dựa trên **mục tiêu cụ thể** của từng query quan trọng.

## 8. G5 — Java Driver smoke test gần sát ứng dụng

Một smoke test hữu ích kiểm tra **kết nối + database + query thật + kết quả nghiệp vụ** trong cùng một đường chạy. Đoạn Java sau là một chương trình đọc, dùng Java Driver hiện đại (ví dụ 5/6) và fixture ở mục 3. **Không** thực hiện ghi.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;

public final class Neo4jPostDeploySmoke {

    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String username = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");
        String database = requireEnv("NEO4J_DATABASE");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {

            driver.verifyConnectivity();

            try (var session = driver.session(
                    SessionConfig.forDatabase(database))) {

                var actualDb = session.executeRead(tx ->
                    tx.run("CALL db.info() YIELD name RETURN name AS db")
                      .single().get("db").asString());

                if (!Objects.equals(database, actualDb)) {
                    throw new IllegalStateException(
                        "Unexpected database: " + actualDb);
                }

                List<String> orderIds = session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:DemoDeployCustomer {
                          tenantId: $tenantId,
                          customerId: $customerId
                        })-[:DEMO_DEPLOY_PLACED]->(o:DemoDeployOrder)
                        RETURN o.orderId AS orderId
                        ORDER BY orderId
                        """, Map.of(
                            "tenantId", "shop-a",
                            "customerId", "C-1"
                        ))
                      .list(record ->
                          record.get("orderId").asString())
                );

                if (!orderIds.equals(List.of("O-1", "O-2"))) {
                    throw new IllegalStateException(
                        "Data contract mismatch: " + orderIds);
                }
            }
            System.out.println("PASS: connection, database and data");
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing required environment variable: " + key);
        }
        return value;
    }
}
~~~

Đoạn này là **mã minh họa cho staging có fixture**. Nó chưa phải dự án Java hoàn chỉnh và phụ thuộc vào Java Driver có mặt trong classpath. Trong production, thay query/expected result bằng dữ liệu golden đã được chấp thuận; **không tự seed DemoDeployCustomer lên database sản xuất** chỉ để test pass.

**Điểm quan trọng:** kiểm tra **db.info()** giúp đối chiếu database thực được truy cập; **executeRead** kiểm tra quyền đọc thật trên graph; so sánh danh sách **O-1/O-2** kiểm tra cả hướng và tenant. Nếu chỉ dùng **RETURN 1**, bạn chưa kiểm tra bất kỳ điều kiện nào về dữ liệu.

### 8.1. Smoke test ở Spring Data Neo4j

Với ứng dụng Spring Boot/SDN, chạy thêm test ở tầng repository/service:

1. Khởi động application context bằng cấu hình **stage/target**.
2. Xác minh **Neo4jClient/Repository** đang dùng đúng database và tài khoản.
3. Gọi một repository query có custom **@Query** hoặc pattern relationship quan trọng.
4. So entity mapping: business ID, **@Relationship**, chiều quan hệ, property nullable.
5. Với workflow ghi, thử trên **staging** để bảo đảm transaction boundary và rollback đúng.

Một lệnh **driver.verifyConnectivity()** nằm trong bean khởi tạo không đủ kiểm chứng SDN mapping, converter hoặc các truy vấn repository được thay đổi trong release.

### 8.2. Canary WRITE: phải được thiết kế để không gây tác dụng phụ

Nếu cần xác minh quyền ghi thực tế trước khi mở lưu lượng, ưu tiên:

- Dùng **staging** có schema và role tương đương production.
- Nếu production cho phép canary, định danh phải có **namespace riêng**, khóa duy nhất, thời hạn xử lý và quy trình dọn **được phê duyệt**.
- Tránh các label/relationship mà ứng dụng khác, CDC, event listener hoặc nghiệp vụ thanh toán sẽ xử lý như đơn thật.
- Xem tác dụng phụ của index, trigger, APOC, service listener và log trước khi cho phép canary ghi.

**Rollback một transaction thử nghiệm không phải luôn vô hại với hệ thống ngoài**: nếu một tác vụ đã phát request sang email, queue hoặc payment gateway trước rollback, tác dụng đó không nhất thiết tự mất. Đừng thử CREATE/DELETE trên production chỉ để cho báo cáo smoke PASS.

## 9. Cụm Neo4j: định tuyến và read-your-writes

### 9.1. Reader/writer phải phục vụ đúng mục đích

Với URI routing, **executeWrite(...)** được định tuyến tới writer phù hợp; **executeRead(...)** có thể dùng reader. Trong một cụm, **một database** có thể có leader và nhiều server đọc; vai trò cụ thể là **theo database**, không cố định vĩnh viễn theo server.

Post-deploy cần quan sát:

- Tên database đúng, thành viên có vai trò như kỳ vọng.
- Routing table được làm mới sau thay đổi topology.
- Các **advertised addresses** truy cập được từ mạng ứng dụng.
- Truy vấn read không vô tình dồn hết về writer.
- Connection pool, timeout, retry và latency trong giới hạn SLO.

Nếu ứng dụng dùng **bolt://** direct tới một host của cụm, câu query đơn giản có thể thành công nhưng failover có thể khiến ghi thất bại sau khi leader chuyển. Hãy thử qua **URI routing** được phê duyệt.

### 9.2. Không đánh đồng replication lag với lỗi mất dữ liệu

Một luồng ghi rồi đọc qua **Session khác** có thể gặp reader chưa áp dụng transaction trước nếu không chuyển bookmark. Java Driver tự quản lý bookmark cho các transaction tuần tự trong cùng Session và cho **executableQuery()** cùng manager; giữa các Session độc lập cần dùng **lastBookmarks()/withBookmarks()** hoặc **BookmarkManager** dùng chung khi có phụ thuộc nhân quả.

Trong smoke test đọc sau ghi:

1. Chờ **giao dịch ghi commit**, không chỉ chờ callback bắt đầu.
2. Gắn bookmark cho truy vấn phụ thuộc hoặc sử dụng cùng Session/manager.
3. Đọc đúng database và theo role có quyền.
4. Chỉ kết luận sai dữ liệu khi đã loại trừ routing/replication lag.

**Bookmark không biến cache ứng dụng thành dữ liệu mới nhất** và không sửa lỗi migration thiếu relationship. Nó chỉ bảo đảm server phục vụ giao dịch phụ thuộc đạt trạng thái được biểu diễn bởi bookmark.

### 9.3. Phân biệt standalone và cluster

Một container Neo4j đơn trong test CI chứng minh nhiều câu Cypher và constraint hoạt động, nhưng **không** chứng minh khả năng routing/failover trong cluster. Muốn nghiệm thu chuyện leader change, server offline hoặc read replica catch-up cần môi trường cluster thật được phép kiểm thử, hoặc một diễn tập chuyên biệt.

## 10. Kiểm tra plugin và tính tương thích của truy vấn

Nếu ứng dụng dùng **APOC** hoặc **Graph Data Science (GDS)**, sau triển khai cần kiểm tra procedure/function thật sự được nạp và quyền gọi dưới user phù hợp:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
   OR name STARTS WITH 'gds.'
RETURN name
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
~~~

**Không kiểm tra package bằng cách giả định một plugin xuất hiện trong thư mục JAR tức là đã nạp**. Cần khớp Neo4j/Plugin versions, cấu hình **allowlist**, **unrestricted** khi thủ tục đặc biệt cần, role **EXECUTE PROCEDURE/FUNCTION** và các quyền dữ liệu.

Đặc biệt ở **Neo4j Aura**, chỉ một tập tính năng plugin được hỗ trợ; không thể tự chép mọi JAR như self-managed. Nếu ứng dụng dùng procedure APOC/GDS không khả dụng, gate phải đánh dấu blocker chức năng, không tự mở quyền tất cả procedure trên production.

### 10.1. Cypher 5 và Cypher 25

Từ một số phiên bản Neo4j năm 2025 trở đi, hệ thống hỗ trợ lựa chọn **Cypher 5** và **Cypher 25**; default language có thể khác sau upgrade. Khi nâng server, chạy golden queries với **ngôn ngữ đã chốt** rồi thử ngôn ngữ mới trong một vòng kiểm tra riêng để phân biệt:

- Cú pháp không còn tương thích.
- Tên function/procedure thay đổi.
- Hành vi planner/runtime khác.
- Kết quả khác do thay đổi dữ liệu hoặc query, không hẳn do Cypher version.

Không dùng prefix **CYPHER 25** trên server chưa hỗ trợ. Không chỉ so sánh text của execution plan từng ký tự giữa hai version; kiểm tra ngữ nghĩa, chi phí truy cập và latency.

## 11. Quan sát sau khi mở lưu lượng có kiểm soát

Sau G0–G5 PASS ở staging hoặc trên canary, mở lưu lượng theo từng giai đoạn (ví dụ **5% → 25% → 100%** nếu hạ tầng hỗ trợ), chứ không mặc định chuyển toàn bộ ngay.

| Tín hiệu | Dấu hiệu bất thường | Hành động |
|---|---|---|
| API success/error rate | Lỗi 4xx/5xx tăng so với baseline, loại trừ lỗi client hợp lệ | Phân nhóm lỗi auth, query, constraint, timeout |
| p95/p99 latency | Cao bất thường trên truy vấn trọng tâm | So query plan, DB Hits, I/O, connection pool |
| Active/queued transactions | Transaction kéo dài, phải chờ khóa | Xem tranh chấp, timeout và retry |
| Heap/page cache/GC | Tăng memory pressure hoặc cache miss | Kiểm tra workload và cấu hình tài nguyên |
| Index state | Index mới chưa ONLINE hoặc FAILED | Giữ gate, xem log và tài nguyên |
| Cluster members | Thành viên rời cụm, router không trả đúng host | Kiểm tra DNS/routing/leader và log |
| Backup freshness | Job backup lỗi sau deployment | Dừng thay đổi phá hủy và xử lý bảo vệ dữ liệu |
| Golden business invariant | Xuất hiện trùng ID, missing relationship hoặc sai tenant | Dừng rollout, điều tra migration/data correctness |

Một release có thể đạt mọi **smoke test ngắn** nhưng gây hồi quy sau 30 phút tải thật. Vì vậy cần **giai đoạn quan sát có người/automation chịu trách nhiệm**, ngưỡng rollback và phạm vi giao tiếp khi lỗi xảy ra.

**Không tự động rollback schema/data migration chỉ bằng revert image ứng dụng** nếu migration đã xóa property hoặc thay cấu trúc dữ liệu không tương thích ngược. Phải thiết kế **expand–migrate–verify–contract**, backup/restore hoặc migration bù từ trước.

## 12. Runbook phân loại lỗi hậu triển khai

| Triệu chứng | Kiểm tra đầu tiên | Không nên làm |
|---|---|---|
| **Connection refused/timeout** | DNS, port 7687, firewall, pod env, driver logs | Tăng timeout vô hạn |
| **TLS handshake lỗi** | Chứng chỉ, CA, hostname, clock | Đổi sang kết nối không an toàn trên production |
| **Driver lấy routing table lỗi** | Advertised address, seed/router, DNS, cluster status | Ép dùng bolt:// như một fix lâu dài |
| **Authentication failed** | Secret/version/role, DBMS auth | Đưa user admin/mật khẩu vào source code |
| **Database not found/offline** | Tên database, alias, SHOW DATABASES/statusMessage | DROP database trước khi điều tra |
| **Query trả rỗng sau migration** | Đúng database/tenant? data/relationship đã migrate? role? | Chạy CREATE dữ liệu giả để smoke pass |
| **Vi phạm uniqueness** | Constraint đúng khóa? có request trùng hoặc dữ liệu lỗi? | DROP constraint để tránh lỗi |
| **Index POPULATING** | Đợi có timeout, kiểm tra resource và tiến độ | Mở 100% lưu lượng dù SLO phụ thuộc index |
| **Index FAILED** | failureMessage, index config, storage và log | Coi populationPercent đủ và bỏ qua trạng thái |
| **Latency tăng** | EXPLAIN/PROFILE read-only, DB Hits, cache, tải | Kết luận chỉ do driver mà không đo |
| **Read-after-write lúc thấy lúc không** | Session/bookmark, replica lag, routing | Thêm Thread.sleep ngẫu nhiên |
| **APOC/GDS Unknown procedure** | Phiên bản, plugin nạp, allowlist và privilege | Bật unrestricted toàn bộ namespace |

### 12.1. Mẫu quyết định release

~~~text
Release: neo4j-app-2026-11
Database: <database được chấp thuận>
Connectivity/Auth: PASS
Database status: PASS
Golden queries: PASS
Relationship/tenant invariants: PASS
Constraints and indexes: PASS
Read-only PROFILE vs baseline: PASS
Java Driver + SDN smoke: PASS
Canary monitoring: PASS
Decision: PROCEED
~~~

Đây là mẫu báo cáo, **không phải kết quả của một lần triển khai thực tế**. Nếu một bước chưa chạy được, ghi **BLOCKED**, nêu nguyên nhân, người phụ trách và biện pháp xử lý. **Không chuyển BLOCKED thành PASS** bằng cách bỏ dòng kiểm tra.

## 13. Tự động hóa post-deploy verification trong CI/CD

Một pipeline có thể triển khai thành những job tách biệt:

~~~text
Deploy application / database migration
  -> verify TCP/TLS/Bolt/routing từ mạng ứng dụng
  -> Java Driver verifyConnectivity và SELECT database
  -> DBA kiểm tra currentStatus/read-write nếu có quyền
  -> kiểm tra constraint/index ONLINE với timeout
  -> đọc golden queries và business invariants
  -> EXPLAIN/PROFILE read-only cho query quan trọng
  -> chạy SDN/API smoke với tài khoản service thật
  -> mở canary, theo dõi error/latency/resource
  -> đánh dấu PROCEED hoặc STOP/ROLLBACK theo runbook
~~~

### 13.1. Cách viết assertion có tính quyết định

Mỗi script nên trả **exit code khác 0** khi một điều kiện quan trọng sai. Ví dụ:

- **Database status** không ONLINE trong timeout → **FAIL**.
- Thiếu index bắt buộc hoặc index FAILED → **FAIL**.
- Index còn POPULATING sau timeout chấp nhận → **FAIL/BLOCKED**, không ép PASS.
- Một business key trùng tenant hoặc Order không có Customer hợp lệ → **FAIL**.
- Dữ liệu vẫn đúng nhưng p95 vượt ngân sách đã duyệt → **FAIL** theo chính sách release.
- Không thể đọc metadata do thiếu quyền quan sát → **BLOCKED**, chuyển sang job có role phù hợp.

Không xây một script duy nhất chạy **MATCH (n) DETACH DELETE n** để reset production. Fixture và dữ liệu thử nghiệm phải được quản lý ngoài dữ liệu nghiệp vụ thực, tốt nhất ở database/pipeline cô lập.

### 13.2. Lưu bằng chứng phù hợp

| Bằng chứng | Nội dung |
|---|---|
| **Deployment manifest** | Application commit/tag, Neo4j version, database, driver/SDN/plugin version |
| **Connection report** | Loại URI, TLS, routing, latency, kết quả auth không kèm secret |
| **Schema snapshot** | SHOW CONSTRAINTS, SHOW INDEXES và trạng thái |
| **Golden query report** | Tên case, tham số đã ẩn danh, expected/actual và PASS/FAIL |
| **Performance report** | PROFILE/DB Hits/Rows, số lượt đo, p95 và cỡ dữ liệu |
| **Canary report** | Thời gian quan sát, error rate, p95/p99 và quyết định |
| **Recovery note** | Backup, kế hoạch stop/rollback/restore, migration state |

Lưu trữ báo cáo theo chính sách nội bộ, **không để lộ credential hoặc dữ liệu khách hàng**. Khi cần tái tạo lỗi, dùng dữ liệu tổng hợp hoặc ẩn danh và ghi đủ phiên bản để chạy lại.

## 14. Các lỗi thiết kế kiểm tra thường gặp

1. **Chỉ ping port 7687.** TCP mở không bảo đảm TLS, authentication hoặc query hoạt động.
2. **Chỉ gọi verifyConnectivity().** Chưa xác minh database, role và Cypher nghiệp vụ.
3. **Test bằng admin thay cho tài khoản app.** Che mất lỗi RBAC/fine-grained privileges.
4. **Không đặt database tường minh.** Dễ kiểm tra nhầm home/default database.
5. **Thấy index tồn tại là cho qua.** Index còn POPULATING hoặc FAILED chưa sẵn sàng.
6. **Quên constraint backing index.** Dữ liệu có thể trùng do migration không có ràng buộc đúng.
7. **Chỉ so số lượng node.** Hai tập cùng count vẫn có thể khác business key hoặc tenant.
8. **Chạy seed/demo data trên production.** Có thể gây side effect và làm ô nhiễm graph.
9. **Dùng PROFILE trên lệnh ghi production.** PROFILE có thực thi truy vấn.
10. **Ép query plan phải giống hệt giữa hai version.** Planner có thể thay đổi mà kết quả/hiệu năng vẫn đúng.
11. **Dùng bolt:// cho cluster cần failover.** Bỏ mất routing theo leader/reader.
12. **Không liên kết bookmark trong read-after-write.** Có thể gán nhầm replication lag thành mất dữ liệu.
13. **Không xét plugin.** APOC/GDS có thể thiếu hoặc sai phiên bản, dù database ONLINE.
14. **Rollback image nhưng dữ liệu không còn tương thích.** Dữ liệu đã migrate có thể không đảo ngược chỉ bằng rollback ứng dụng.
15. **Không có tiêu chí STOP.** Hệ thống tiếp tục mở lưu lượng dù invariant hoặc SLO đã vi phạm.

## 15. Bài tập thực hành

### Bài 1 — Phân tích kết nối

Ứng dụng chạy trong Kubernetes kết nối được tới **neo4j+s://cluster.example**, nhưng sau đó báo timeout tới **neo4j-2.internal**. Hãy giải thích vì sao **verifyConnectivity()** hoặc truy vấn đầu đôi khi thành công mà những request sau thất bại. Đề xuất kiểm tra routing, advertised address, DNS và NetworkPolicy.

### Bài 2 — Kiểm tra chỉ mục

Một release thêm index cho **DemoDeployOrder(tenantId, orderId)**. **SHOW INDEXES** cho biết **POPULATING 80%**. Có nên mở 100% lưu lượng không nếu API có SLO phụ thuộc index này? Hãy đề xuất timeout, lệnh **db.awaitIndex(...)** và cách xử lý khi index chuyển FAILED.

### Bài 3 — Tìm lỗi tenant

Trên fixture mục 3, cố ý bỏ **tenantId** ở truy vấn Customer C-1. So sánh kết quả với truy vấn đúng, giải thích vì sao **đếm tổng số Order = 4** không thể phát hiện tất cả lỗi cô lập tenant.

### Bài 4 — Quy tắc relationship

Viết Cypher tìm Order có **0** hoặc **nhiều hơn 1** cạnh **DEMO_DEPLOY_PLACED** đi vào. Tiếp tục viết truy vấn phát hiện Customer và Order khác tenant được kết nối với nhau. Các truy vấn này kiểm tra điều gì mà uniqueness constraint của Order không kiểm soát?

### Bài 5 — Java Driver smoke

Xây một chương trình Java đọc dùng **GraphDatabase.driver(...)**, **verifyConnectivity()**, **SessionConfig.forDatabase(...)** và **executeRead(...)**, xác minh chính xác một danh sách business ID. Nêu vì sao test **RETURN 1** và test chạy bằng admin chưa đủ.

### Bài 6 — Hồi quy truy vấn

Sau deploy, query vẫn trả đúng Order nhưng p95 tăng gấp ba. Hãy so sánh **EXPLAIN/PROFILE**, DB Hits, Rows, index, phân phối tham số và tải nền. Tại sao không nên so sánh exact operator tree từng ký tự giữa các Neo4j version?

### Bài 7 — Quyết định rollout

Một release có kết quả: kết nối PASS, database ONLINE, dữ liệu PASS, constraint PASS, một index **FAILED**, Java smoke đọc PASS. Bạn sẽ quyết định **PROCEED, BLOCKED hay ROLLBACK**? Nêu điều kiện phân biệt nếu index đó không liên quan đến workload đang triển khai.

## 16. Ghi nhớ

Triển khai Neo4j chỉ được coi là sẵn sàng khi ứng dụng **kết nối được qua đúng tuyến mạng, xác thực và database**, graph **đúng dữ liệu và quan hệ nghiệp vụ**, index/constraint **đúng cấu trúc và trạng thái**, còn các truy vấn/API trọng tâm **đạt SLO**.

Trình tự dễ nhớ:

**Baseline → kết nối DNS/TLS/Bolt/routing → database ONLINE + quyền → dữ liệu và quan hệ → constraint/index ONLINE → EXPLAIN/PROFILE → Java Driver/SDN smoke → canary + giám sát → quyết định GO/NO-GO.**

Hãy ưu tiên truy vấn **read-only** trên production, dùng fixture và bài test ghi trên staging, kiểm tra với **chính tài khoản ứng dụng**, đặt timeout cho các bước đợi index và lưu bằng chứng PASS/FAIL. Sau cùng, giữ phương án backup/rollback phù hợp với migration: **rollback mã ứng dụng không tự đảo ngược thay đổi dữ liệu đã commit**.

### Tài liệu Neo4j chính thức

- [Neo4j Java Driver Manual – Connection](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Operations Manual – Built-in procedures, db.info và db.awaitIndexes](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Java Driver Manual – Coordinate parallel transactions / bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Operations Manual – Show databases](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/listing-databases/)
- [Neo4j Operations Manual – Monitor databases in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/show-databases-monitoring/)
- [Neo4j Cypher Manual – Show constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher Manual – Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual – Built-in procedures (db.awaitIndex/db.awaitIndexes)](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Cypher Manual – Query plans: EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Constraints and key constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Java Driver Manual – Run transactions](https://neo4j.com/docs/java-manual/current/transactions/)
