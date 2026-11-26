# Cấu hình bảo mật, giám sát và giới hạn tài nguyên

Một đồ án Neo4j không hoàn thành chỉ vì ứng dụng có thể tạo node, nối relationship và chạy Cypher. Khi đưa vào môi trường có nhiều người dùng, hệ thống còn phải **bảo vệ dữ liệu**, **phát hiện sớm dấu hiệu bất thường** và **kiểm soát mức tiêu thụ CPU, bộ nhớ, kết nối và thời gian giao dịch**. Nếu ba phần này không được thiết kế cùng nhau, một truy vấn duyệt quan hệ quá rộng có thể làm chậm các giao dịch khác; một tài khoản ứng dụng có quyền admin có thể làm lộ dữ liệu; hoặc một sự cố chỉ được phát hiện khi người dùng báo API đã ngừng hoạt động.

Bài **“Cấu hình bảo mật, giám sát và giới hạn tài nguyên”** nằm trong chương **Đồ án thực hành** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Người học sẽ áp dụng các kiến thức về property graph, Cypher, index/constraint, tối ưu truy vấn, Java Driver, Spring Data Neo4j và vận hành Neo4j vào **một gói triển khai có thể kiểm chứng**, thay vì chỉ học từng setting riêng lẻ.

**Sản phẩm cuối của đồ án:** một môi trường Neo4j dùng cho ứng dụng quản lý thành viên dự án, kèm chính sách truy cập, cấu hình tài nguyên, tín hiệu giám sát, bộ kiểm thử tích hợp, kịch bản sự cố và biên bản nghiệm thu.

> **Giới hạn phiên bản:** Ví dụ cơ sở sử dụng Neo4j **5.26** trên Docker và Java Driver đời 5/6 có `executeRead`/`executeWrite`. Nó minh họa **một instance self-managed phục vụ lab**, không phải cluster có HA. Phân quyền đồ thị chi tiết, Prometheus metrics phía server, một số kiểu query logging và cơ chế backup chuyên nghiệp phụ thuộc **Neo4j Enterprise Edition** hoặc gói dịch vụ được quản lý. Neo4j AuraDB có giao diện quản trị và phạm vi cấu hình riêng. Không giả định một tính năng Enterprise chạy được trên Community.

## 1. Mục tiêu, đầu ra và tiêu chí hoàn thành

Sau bài học, bạn có thể:

1. Thiết lập một Neo4j test instance có **authentication**, cổng chỉ lắng nghe tại nơi dự định và secret không ghi trực tiếp trong mã nguồn.
2. Phân biệt **xác thực**, **phân quyền Neo4j**, **quyền nghiệp vụ trong ứng dụng** và **mã hóa đường truyền**.
3. Thiết kế role đọc tối thiểu, xác minh thao tác được phép và thao tác bị từ chối trên edition hỗ trợ.
4. Cấu hình giới hạn **CPU/container memory**, **JVM heap**, **page cache**, **transaction timeout**, **driver connection pool** và **retry budget** có lý do.
5. Thu thập **latency, throughput, lỗi truy vấn/giao dịch, dấu hiệu chờ khóa và sức khỏe tài nguyên** ở lớp ứng dụng và database.
6. Kiểm chứng bằng dữ liệu mẫu, negative tests, một bài thử tải nhỏ và một diễn tập sự cố trong môi trường cô lập.
7. Viết **runbook**, bảng rủi ro, dashboard/SLO và báo cáo nghiệm thu có bằng chứng.

### Các đầu ra phải nộp

| Mã | Sản phẩm | Bằng chứng tối thiểu |
|---|---|---|
| D1 | Sơ đồ kiến trúc và luồng kết nối | Ứng dụng → Driver → Neo4j, ranh giới mạng và danh tính |
| D2 | Cấu hình database test | Cấu hình đã kiểm tra, không công khai mật khẩu |
| D3 | Chính sách bảo mật | Ma trận danh tính–quyền, kiểm thử được phép/bị từ chối |
| D4 | Ngân sách tài nguyên | Giá trị CPU, heap, page cache, pool, timeout và lý do chọn |
| D5 | Bộ giám sát | Dashboard/log/metrics hoạt động với dữ liệu thật |
| D6 | Bộ kiểm thử | Kiểm tra kết quả Cypher, bảo mật, giới hạn, phục hồi |
| D7 | Runbook và báo cáo | Cách xử lý chậm/lỗi, số đo, rủi ro còn lại, kết luận |

**Tiêu chí nghiệm thu không phải** “file cấu hình tồn tại”, mà là “cấu hình thực sự có hiệu lực, phép thử đúng cho kết quả mong đợi và có bằng chứng”. Nếu một tính năng không khả dụng trong edition đang dùng, ghi **NOT APPLICABLE/NOT AVAILABLE** và đề xuất cơ chế bổ sung, **không đánh dấu PASS giả**.

## 2. Bối cảnh nghiệp vụ của đồ án

Giả sử một dịch vụ nội bộ quản lý người dùng và dự án:

~~~text
(:CapUser {uid: 'U01', name: 'An', email: 'an@example.test'})
   -[:MEMBER_OF]->
(:CapProject {code: 'P01', name: 'Graph Platform'})

(:CapSecret {key: 'S01', note: 'private-demo'})
~~~

Ứng dụng có ba luồng:

- **Đọc:** tìm dự án của người dùng theo `uid`.
- **Ghi:** tạo hoặc cập nhật liên kết thành viên dự án theo yêu cầu đã được cho phép.
- **Quản trị:** tạo constraint/index, tạo tài khoản và role, giám sát/khôi phục hệ thống.

Ba luồng này **không nên sử dụng cùng quyền**. Dịch vụ hiển thị dự án cần biết `CapUser.uid`, `CapUser.name`, `CapProject.code` và `CapProject.name`, nhưng không cần biết `CapUser.email` hoặc `CapSecret.note`.

### Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart LR
    USER["Người dùng / API"] --> APP["Spring Boot / Java service"]
    SEC["Secret manager<br/>hoặc biến môi trường an toàn"] -.-> APP
    APP -->|"Bolt + TLS trong production"| DRIVER["Neo4j Java Driver"]
    DRIVER --> DB["Neo4j database"]
    DB --> OBS["Metrics / logs nội bộ"]
    MON["Monitoring service"] --> OBS
    ADM["Tài khoản quản trị riêng"] --> DB
~~~

**Ranh giới cần ghi rõ:** ai được kết nối cổng Bolt, ai đọc được log/metrics, ứng dụng lấy credential từ đâu, tài khoản nào được thực thi migration và ai có quyền khôi phục backup.

## 3. Chọn phạm vi theo edition

Để đồ án có thể triển khai trên môi trường khác nhau, chia thành **hai tầng thực hiện**:

| Năng lực | Baseline Neo4j Community self-managed | Mở rộng Neo4j Enterprise / managed phù hợp |
|---|---|---|
| Authentication bằng mật khẩu | Có | Có hoặc cơ chế được gói hỗ trợ |
| Không công khai Bolt ra Internet | Có, cấu hình network | Có, thêm private networking khi phù hợp |
| Parameterized Cypher, validation và constraint | Có | Có |
| Giới hạn heap/page cache/CPU trên self-managed | Có | Với managed: do tier và bề mặt cấu hình quy định |
| Giới hạn driver pool, retry, transaction timeout | Có trong phạm vi API/cấu hình hỗ trợ | Có |
| Application metrics/log/trace | Có | Có |
| Fine-grained graph RBAC theo label/property | **Không đầy đủ** như Enterprise | Enterprise và gói hỗ trợ |
| Server-side Prometheus metrics chi tiết | Không giả định có | Enterprise self-managed và môi trường có khả năng xuất |
| Query logging chuyên sâu/kiểm toán | Phụ thuộc edition/phiên bản | Theo edition/gói/quyền |
| Tự cài plugin, truy cập máy chủ và file cấu hình | Có trong self-managed, với hạn chế của edition | Enterprise self-managed linh hoạt; managed thường giới hạn |

**Quy tắc:** muốn nghiệm thu việc “reader không thể xem email dù chạy Cypher trực tiếp”, cần một database có **fine-grained RBAC thực sự hỗ trợ**. Nếu dùng Community và chỉ che email ở lớp API, đó là **kiểm soát khác**, không phải bằng chứng Neo4j đã từ chối đọc property.

## 4. Chuẩn bị môi trường thực hành

### 4.1. Điều kiện cần

- Docker Engine và Docker Compose phiên bản hiện đại.
- Máy thực hành đủ dung lượng RAM/đĩa để chạy container với giới hạn dưới đây; không ép cấu hình 4 GiB vào một host không có tài nguyên tương ứng.
- Một thư mục đồ án riêng **ngoài dữ liệu production**.
- Mật khẩu Neo4j test được cung cấp từ biến môi trường; **không đưa vào Git**.
- JDK 17+ và ứng dụng Java/Spring Boot nếu làm phần tích hợp.

Trong ví dụ, giả định tên database là `neo4j`. Khi dùng AuraDB hoặc DBMS nhiều database, cần xác minh tên database thực tế; đừng dựa vào kết nối mặc định mà không kiểm tra.

### 4.2. Docker Compose cho lab

Một cấu hình self-managed tối thiểu:

~~~yaml
services:
  neo4j:
    image: neo4j:5.26
    restart: unless-stopped
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set_NEO4J_PASSWORD}"
      NEO4J_server_memory_heap_initial__size: "512m"
      NEO4J_server_memory_heap_max__size: "1G"
      NEO4J_server_memory_pagecache_size: "1G"
      NEO4J_db_transaction_timeout: "30s"
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    mem_limit: 4g
    cpus: "2.0"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
~~~

**Những điểm cần nhận diện:**

- `NEO4J_AUTH` bật authentication với user mặc định `neo4j`. Mật khẩu lấy từ biến môi trường tại thời điểm chạy Compose.
- Quy tắc chuyển tên setting Neo4j sang biến môi trường Docker: dấu chấm `.` → `_`; dấu gạch dưới `_` trong tên gốc → `__`. Ví dụ `server.memory.heap.max_size` thành `NEO4J_server_memory_heap_max__size`.
- `127.0.0.1:7687:7687` chỉ bind cổng Bolt tới loopback máy host. Đây là **biện pháp cô lập cho lab một máy**, không thay TLS cho kết nối đi qua mạng không tin cậy.
- `mem_limit: 4g` và `cpus: "2.0"` chỉ là **giới hạn thực hành**; bộ nhớ Neo4j gồm heap, page cache và cả vùng native/off-heap.
- `/data` và `/logs` dùng persistent volumes. **Volume không phải backup** và không thay restore drill.
- `db.transaction.timeout` đặt ngưỡng giao dịch mặc định. Một số job nhập dữ liệu lớn cần kế hoạch timeout riêng; không tăng vô hạn chỉ để job chạy qua.

**Cảnh báo về credential:** biến môi trường container có thể được xem bởi người quản trị Docker và một số công cụ chẩn đoán. Mẫu này phù hợp lab cô lập; production nên dùng cơ chế secret management/cấp credential theo nền tảng, không coi Compose environment là kho secret chống mọi truy cập. Tránh in kết quả `docker compose config` có chứa giá trị đã được nội suy ra log công khai.

### 4.3. Khởi động và xác minh, không chỉ nhìn container “Up”

Các lệnh minh họa để **người học tự thực hiện trong môi trường lab**:

~~~bash
# Khai báo NEO4J_PASSWORD trong môi trường shell bằng cách bảo mật phù hợp.
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Sau khi database sẵn sàng, mở Neo4j Browser ở `http://127.0.0.1:7474`, đăng nhập bằng credential test, rồi chạy:

~~~cypher
RETURN 1 AS ready;
~~~

~~~cypher
SHOW DATABASE neo4j
YIELD name, currentStatus
RETURN name, currentStatus;
~~~

`RETURN 1` chứng minh server nhận được một truy vấn đơn giản; **không chứng minh** người dùng có quyền cần thiết, dữ liệu đúng, backup tồn tại hay query nghiệp vụ đủ nhanh.

## 5. Tạo dữ liệu và constraint có thể kiểm chứng

Để có cùng đầu vào cho các phép thử bảo mật, giám sát và tài nguyên, hãy tạo fixture **chỉ trên database thực hành**.

### 5.1. Tạo constraint

~~~cypher
CREATE CONSTRAINT cap_user_uid_unique IF NOT EXISTS
FOR (u:CapUser)
REQUIRE u.uid IS UNIQUE;

CREATE CONSTRAINT cap_project_code_unique IF NOT EXISTS
FOR (p:CapProject)
REQUIRE p.code IS UNIQUE;
~~~

Constraint giúp tìm node theo khóa và tránh tạo hai node có cùng khóa nghiệp vụ. **Uniqueness không đồng nghĩa property bắt buộc tồn tại**; existence/key constraint cần edition phù hợp nếu chính sách đòi hỏi.

### 5.2. Nạp dữ liệu mẫu

~~~cypher
MERGE (u1:CapUser {uid: 'U01'})
SET u1.name = 'An',
    u1.email = 'an@example.test',
    u1.isActive = true
MERGE (u2:CapUser {uid: 'U02'})
SET u2.name = 'Bình',
    u2.email = 'binh@example.test',
    u2.isActive = true
MERGE (p1:CapProject {code: 'P01'})
SET p1.name = 'Graph Platform'
MERGE (p2:CapProject {code: 'P02'})
SET p2.name = 'Monitoring'
MERGE (u1)-[:MEMBER_OF]->(p1)
MERGE (u1)-[:MEMBER_OF]->(p2)
MERGE (u2)-[:MEMBER_OF]->(p2)
MERGE (s:CapSecret {key: 'S01'})
SET s.note = 'private-demo';
~~~

Kiểm tra độc lập:

~~~cypher
MATCH (u:CapUser)
RETURN count(u) AS users;
// Dữ liệu mẫu: 2
~~~

~~~cypher
MATCH (:CapUser)-[r:MEMBER_OF]->(:CapProject)
RETURN count(r) AS membershipEdges;
// Dữ liệu mẫu: 3
~~~

~~~cypher
MATCH (u:CapUser {uid: 'U01'})-[:MEMBER_OF]->(p:CapProject)
RETURN p.code AS projectCode, p.name AS projectName
ORDER BY projectCode;
// P01 / Graph Platform; P02 / Monitoring
~~~

**Giả định:** bài đang dùng database sạch hoặc dữ liệu nhãn `CapUser`/`CapProject`/`CapSecret` chưa tồn tại. Nếu dữ liệu từ bài test khác chia sẻ cùng label và ID, phải cô lập database hoặc fixture trước khi dựa vào `count`.

## 6. Thiết kế mô hình quyền tối thiểu

### 6.1. Tách các danh tính theo công việc

| Danh tính | Công việc | Quyền cần có | Không nên có |
|---|---|---|---|
| `cap_reader` | Hiển thị dự án của người dùng | ACCESS, duyệt `MEMBER_OF`, đọc ID/tên cần thiết | Xem email/`CapSecret`, ghi, admin |
| `cap_writer` | Quản lý liên kết thành viên | Đọc khóa và ghi đúng đối tượng cần thiết | Quản trị user, schema, backup |
| `cap_migrator` | Triển khai index/constraint | Quyền schema/migration được ủy quyền | Chạy làm runtime identity của API |
| `cap_observer` | Quan sát hoạt động | Quyền quan sát/log/metrics theo hệ thống | Sửa dữ liệu nghiệp vụ |
| `cap_admin` | Provision/restore khi có phê duyệt | Quyền quản trị trong phạm vi được kiểm soát | Dùng làm credential mặc định của dịch vụ |

**Tách người dùng HTTP khỏi người dùng Neo4j:** nếu API kết nối bằng `cap_reader`, ứng dụng vẫn phải kiểm tra người dùng HTTP có quyền xem dự án nào. Neo4j RBAC không tự biết danh tính HTTP cuối cùng nếu mọi request cùng dùng một database user.

### 6.2. Authentication ở baseline Community

Trong Docker Compose lab, `NEO4J_AUTH` giúp bảo vệ đăng nhập. Các phép thử cơ bản:

1. Đăng nhập đúng mật khẩu, chạy `RETURN 1` thành công.
2. Đăng nhập sai mật khẩu, kết nối bị từ chối.
3. Kiểm tra cổng Bolt/Browser chỉ truy cập qua loopback host như cấu hình.
4. Xác minh API không ghi password, token, toàn bộ URI chứa credential vào log.
5. Kiểm tra query luôn truyền tham số thay vì ghép user input vào Cypher.

**Đây mới là authentication và network exposure**, chưa chứng minh có fine-grained quyền theo label/property. Không dùng admin login chung cho ứng dụng production chỉ vì môi trường lab Community không có phân quyền chi tiết tương đương Enterprise.

## 7. Mở rộng Enterprise: cấp quyền đọc đúng label/property

Phần này **chỉ chạy trên Neo4j Enterprise test** có RBAC hỗ trợ, hoặc dịch vụ managed hỗ trợ cùng chức năng. Các lệnh tạo user/role và cấp quyền được quản trị viên thực thi trên **system database**.

### 7.1. Provision role và user

~~~cypher
// SYSTEM database — admin, cung cấp $readerPassword từ nơi an toàn.
CREATE ROLE cap_reader_role IF NOT EXISTS;
~~~

~~~cypher
CREATE USER cap_reader IF NOT EXISTS
SET PASSWORD $readerPassword
CHANGE NOT REQUIRED;
~~~

~~~cypher
GRANT ROLE cap_reader_role TO cap_reader;
~~~

Đừng nhập mật khẩu thật trực tiếp thành literal trong tài liệu, lịch sử query hoặc ticket. Một số công cụ có thể ghi tham số truy vấn vào log nếu được cấu hình; khi provision credential cần có chính sách log riêng.

### 7.2. Cấp quyền cần thiết

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO cap_reader_role;

GRANT MATCH {uid, name}
ON GRAPH neo4j NODES CapUser
TO cap_reader_role;

GRANT MATCH {code, name}
ON GRAPH neo4j NODES CapProject
TO cap_reader_role;

GRANT TRAVERSE
ON GRAPH neo4j RELATIONSHIPS MEMBER_OF
TO cap_reader_role;
~~~

Không cấp quyền `MATCH {*} ON GRAPH *`, `WRITE` hay quyền quản trị chỉ để API đọc được một trang. Nếu thực tế cần thêm property, cập nhật ma trận quyền và test trước khi mở rộng.

**Quan trọng:** user có thể được gán nhiều role, bao gồm các quyền liên quan đến `PUBLIC`; một `GRANT` khác có thể làm quyền hiệu lực rộng hơn dự kiến. Không coi script cấp quyền tối thiểu là bằng chứng cuối cùng.

### 7.3. Kiểm tra quyền hiệu lực

~~~cypher
// SYSTEM database — người có quyền xem privilege.
SHOW USER cap_reader PRIVILEGES AS COMMANDS;
~~~

~~~cypher
SHOW USERS
YIELD user, roles, suspended
WHERE user = 'cap_reader'
RETURN user, roles, suspended;
~~~

Đối chiếu tên database, label, property, type relationship và mọi role thực tế của `cap_reader`. Nếu một role khác cho phép đọc `email` hoặc `CapSecret`, test bảo mật phải được đánh dấu **FAIL**, không xóa bớt assertion.

## 8. Bộ kiểm thử bảo mật có đối chứng

**Luôn seed fixture bằng credential có quyền phù hợp và COMMIT trước khi chạy reader test.** Nếu reader truy vấn trong lúc transaction seed chưa commit, kết quả rỗng có thể do isolation, không phải do RBAC.

### 8.1. Positive control: reader đọc được dữ liệu công khai

Đăng nhập bằng `cap_reader` trên database `neo4j`:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})-[:MEMBER_OF]->(p:CapProject)
RETURN u.uid AS uid, u.name AS userName,
       p.code AS projectCode, p.name AS projectName
ORDER BY projectCode;
~~~

**Kỳ vọng:** đúng 2 hàng `P01` và `P02`. Positive test bắt được trường hợp tài khoản **bị chặn quá mức** làm API không còn hoạt động.

### 8.2. Negative read: property bí mật không lộ

Reader:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})
RETURN u.uid AS uid, u.email AS email;
~~~

Nếu chỉ được cấp quyền như mục 7, reader vẫn đọc được `uid` nhưng không thấy giá trị `email` (thường là `null` theo ngữ nghĩa fine-grained READ). Với admin:

~~~cypher
MATCH (u:CapUser {uid: 'U01'})
RETURN u.email AS email;
// Admin thấy an@example.test.
~~~

Để kết luận PASS phải có **cả hai bằng chứng**: dữ liệu thật tồn tại khi đọc với danh tính có quyền, nhưng không bị lộ khi đọc với reader.

### 8.3. Negative traversal: node không thuộc phạm vi

Reader:

~~~cypher
MATCH (s:CapSecret)
RETURN count(s) AS visibleSecrets;
// Thường 0 khi reader không có TRAVERSE trên label này.
~~~

Admin:

~~~cypher
MATCH (s:CapSecret)
RETURN count(s) AS totalSecrets;
// Dữ liệu mẫu: 1.
~~~

Không có quyền `TRAVERSE` có thể khiến node **biến mất khỏi kết quả** thay vì tạo exception. Test cần phân biệt dữ liệu bị che với dữ liệu thật sự không tồn tại.

### 8.4. Negative write: không sửa được tài nguyên

Reader cố thay tên dự án:

~~~cypher
MATCH (p:CapProject {code: 'P01'})
SET p.name = 'Tampered'
RETURN p.name;
~~~

**Kỳ vọng:** không thể ghi; kiểm tra mã lỗi quyền phù hợp với version và xác minh sau đó bằng admin:

~~~cypher
MATCH (p:CapProject {code: 'P01'})
RETURN p.name AS name;
// Vẫn phải là Graph Platform.
~~~

Chỉ `assertThrows(...)` mà không đối chiếu database **chưa đủ** cho negative write test. Với một giao dịch nhiều bước, cần kiểm tra đúng ranh giới rollback.

### 8.5. Ma trận bảo mật

| Test | Baseline Community | Enterprise fine-grained |
|---|---|---|
| Đúng/sai mật khẩu | Thực hiện | Thực hiện |
| Cổng không lộ ngoài loopback/private network | Thực hiện | Thực hiện |
| SQL/Cypher parameterization, không lộ secret trong log | Thực hiện | Thực hiện |
| Reader xem `uid`/`name` | Kiểm tra API behavior | Kiểm tra RBAC và query thật |
| Reader không xem `email` qua Cypher trực tiếp | Không coi API masking là DB RBAC | **Bắt buộc test** khi có chính sách |
| Reader không traverse `CapSecret` | Không đủ fine-grained để khẳng định | **Bắt buộc test** |
| Reader không `SET`/`DELETE` | Theo quyền thực tế của edition | **Bắt buộc test** |
| App user không có quyền admin/schema | Kiểm tra điều kiện khả dụng | Kiểm tra quyền hiệu lực |

## 9. Bảo mật trong Cypher, Java Driver và kết nối

### 9.1. Không nối chuỗi input vào câu Cypher

**Sai:**

~~~java
String cypher =
    "MATCH (u:CapUser {uid: '" + inputUserId + "'}) RETURN u";
~~~

**Đúng:**

~~~java
var result = tx.run("""
    MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->(p:CapProject)
    RETURN p.code AS code, p.name AS name
    ORDER BY code
    """, Map.of("uid", inputUserId));
~~~

Tham số hóa giúp giữ giá trị đầu vào tách khỏi cấu trúc Cypher. Khi cần chọn label/type từ người dùng, không chèn text tùy ý; dùng **allowlist** cho những phần cấu trúc mà phiên bản không thể parameterize trực tiếp.

### 9.2. TLS và giới hạn mạng

- **Lab loopback:** các cổng Compose chỉ bind trên `127.0.0.1`; dùng cho thử nghiệm một máy, **không** truyền credential qua mạng công cộng.
- **Production self-managed:** dùng TLS hợp lệ cho Bolt, kiểm tra cấu hình chứng chỉ, DNS, firewall và hostname được công bố. Có thể dùng `neo4j+s://` hoặc `bolt+s://` theo topology.
- **Cluster:** với routing URI, mọi địa chỉ driver nhận trong routing table phải được ứng dụng truy cập qua mạng và TLS theo thiết kế.
- **Managed AuraDB:** dùng URI và cách thiết lập bảo mật được instance cung cấp; không cố sửa `neo4j.conf` trên dịch vụ không cho truy cập máy chủ.
- **Secret:** lấy từ secret manager hoặc cơ chế triển khai tương ứng; tránh in `AuthTokens.basic(...)`, mật khẩu và URL chứa credential ra log.

Không tắt xác thực TLS chỉ để kiểm thử kết nối “xanh”. Tách network reachability, authentication, authorization và correctness thành những ca kiểm thử độc lập.

## 10. Tài nguyên Neo4j: chia ngân sách bộ nhớ đúng cách

Neo4j là hệ thống graph thường xuyên truy cập node, relationship và index. Đặt giới hạn bộ nhớ chỉ bằng `-Xmx` là thiếu, vì **không phải tất cả bộ nhớ Neo4j đều nằm trong JVM heap**.

### 10.1. Các vùng bộ nhớ

| Vùng | Dùng cho | Dấu hiệu thiếu hoặc cấu hình sai |
|---|---|---|
| **JVM heap** | Java objects, một phần trạng thái xử lý query, metadata và transaction | GC kéo dài, lỗi heap, latency tăng |
| **Page cache** | Cache các trang lưu trữ graph/index | Page faults tăng, I/O nhiều, query chậm |
| **Native/off-heap & OS** | Bolt/network buffers, native allocations, thread stacks, runtime overhead | Container bị OOM kill dù heap còn chỗ |
| **Disk** | Store, transaction logs, query/log files, backup | Hết dung lượng, transaction lỗi, recovery khó |

Trong mẫu Compose:

~~~text
Container memory limit = 4 GiB
  Heap initial         = 512 MiB
  Heap maximum         = 1 GiB
  Page cache           = 1 GiB
  Còn lại              = dành cho native/off-heap/OS/overhead

CPU quota              = 2 vCPU (giá trị minh họa)
~~~

Đây là **bảng ngân sách**, không phải mô tả chính xác RSS thực tế. Ngoài heap/page cache còn nhiều khoản native/OS; không cấu hình tổng heap + page cache bằng toàn bộ `mem_limit`. Bộ nhớ khả dụng của host và workload quyết định cấu hình hợp lý.

### 10.2. Nguyên tắc chọn heap và page cache

- Đừng tăng heap vô hạn khi query chậm do thiếu index hoặc fan-out quá lớn.
- Đừng tăng page cache tới mức container thiếu bộ nhớ native.
- Theo dõi **heap usage, GC pauses, page cache hits/faults, RSS và container OOM events** nếu môi trường cho phép.
- Dữ liệu vừa khởi động thường chưa ấm cache; so hiệu năng giữa các cấu hình trong điều kiện tương tự.
- Cấu hình self-managed phải được **validate theo phiên bản** và đo với tập dữ liệu đại diện.
- Trong managed, kích thước heap/page cache có thể do tier/provider quyết định; tối ưu qua query, index và gói tài nguyên được hỗ trợ.

### 10.3. Chống hiểu nhầm về giới hạn container

Giới hạn `cpus: "2.0"` không bảo đảm mỗi query chỉ dùng “tối đa 2 thread”, và `mem_limit: 4g` không có nghĩa Neo4j luôn sử dụng 4 GiB. Đây là **quota/cap** do môi trường container quản lý. Khi vượt giới hạn bộ nhớ thực tế, process có thể bị hệ điều hành/container runtime dừng, nên phải có metrics và alert về OOM chứ không chỉ xem Java heap.

## 11. Giới hạn transaction, query và kết nối

### 11.1. Ba ngưỡng thời gian không được nhầm

| Ngưỡng | Ý nghĩa | Khi vượt ngưỡng |
|---|---|---|
| **Connection acquisition timeout** | Driver chờ lấy kết nối từ pool | Có thể lỗi dù query chưa chạy |
| **Transaction timeout** | Giới hạn thời gian của một transaction ở server/driver theo config | Transaction có thể bị terminate/rollback |
| **Max transaction retry time** | Ngân sách driver thử lại managed transaction khi lỗi tạm thời | Driver ngừng thử và trả lỗi nếu chưa thành công |

Ngoài ra còn **HTTP/API timeout**, connection establishment timeout, network timeout và idle connection behavior. Chọn một giá trị ở tầng driver **không** đồng nghĩa mọi request sẽ kết thúc đúng giá trị đó.

### 11.2. Java Driver: cấu hình có giới hạn

Ví dụ Java 17+:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Config;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

public final class CapProjectGateway implements AutoCloseable {
    private final Driver driver;
    private final String database;

    public CapProjectGateway(
            String uri, String username, String password,
            String database) {

        Config config = Config.builder()
                .withMaxConnectionPoolSize(40)
                .withConnectionAcquisitionTimeout(5, TimeUnit.SECONDS)
                .withMaxTransactionRetryTime(15, TimeUnit.SECONDS)
                .build();

        this.driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password), config);
        this.database = database;
        driver.verifyConnectivity();
    }

    public List<String> projectsOf(String uid) {
        TransactionConfig transactionConfig = TransactionConfig.builder()
                .withTimeout(5, TimeUnit.SECONDS)
                .build();

        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->
                          (p:CapProject)
                    RETURN p.code AS code
                    ORDER BY code
                    LIMIT 100
                    """, Map.of("uid", uid))
                    .list(record -> record.get("code").asString()),
                    transactionConfig);
        }
    }

    @Override
    public void close() {
        driver.close();
    }
}
~~~

**Điều cần kiểm tra:**

1. Chỉ tạo một **Driver dài hạn** cho ứng dụng, không tạo Driver mới cho mỗi HTTP request.
2. `Session` là đơn vị công việc ngắn, không chia sẻ giữa nhiều thread.
3. `executeRead` cho biết đây là giao dịch đọc; khi dùng routing URI trong cluster, driver có thể chọn reader phù hợp.
4. `.list(...)` tiêu thụ kết quả trong callback, nên phép đo transaction bao gồm quá trình nhận bản ghi.
5. Giới hạn `LIMIT 100` kiểm soát **số hàng trả về**, nhưng không sửa được truy vấn kém chọn lọc trước khi `LIMIT`.
6. `withMaxConnectionPoolSize(40)` không có nghĩa tổng toàn hệ thống chỉ có 40 kết nối: nhiều instance ứng dụng và nhiều server trong cluster đều ảnh hưởng tổng kết nối thực tế.
7. `withMaxTransactionRetryTime` không bảo đảm lặp lại an toàn với mọi lỗi. Callback ghi phải có idempotency, không gọi thanh toán/email bên trong callback có thể retry.

Các con số trong đoạn Java chỉ dùng cho **lab**. Phải đo số request đồng thời, độ trễ xử lý, quy mô cluster và ngân sách kết nối trước khi dùng ở production.

### 11.3. Spring Data Neo4j và transaction boundary

Với Spring Data Neo4j, cấu hình URI và database thường nằm trong Spring Boot:

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

Ở thực tế, dùng `@Transactional(readOnly = true)` cho tác vụ đọc phù hợp và `@Transactional` cho ghi theo ranh giới nghiệp vụ. **Không coi annotation là giới hạn cứng về tài nguyên hoặc cơ chế bảo mật**: timeout, quyền Neo4j, connection pool, query complexity và chính sách của service vẫn phải được xác minh.

### 11.4. Không tăng giới hạn để che truy vấn sai

Giả sử một query duyệt đồ thị quan hệ nhiều bước không có giới hạn và tạo hàng triệu kết quả trung gian. Tăng heap từ 1 lên 8 GiB có thể chỉ **trì hoãn OOM**. Phải phân tích:

~~~cypher
EXPLAIN
MATCH (u:CapUser {uid: $uid})-[:MEMBER_OF]->(p:CapProject)
RETURN p.code AS code
ORDER BY code
LIMIT 100;
~~~

Trong database test, có thể dùng `PROFILE` để xem `Rows`, `DB Hits` và operator. Với query ghi, **`PROFILE` thực thi và có tác dụng ghi** nên không chạy trên production chỉ để xem plan. Tối ưu query, index, cardinality và phạm vi duyệt trước khi tăng quota.

## 12. Giám sát: quan sát cả ứng dụng và Neo4j

Một dashboard hữu ích phải trả lời được: **người dùng đang bị chậm ở đâu?** Chỉ nhìn `container running` hoặc `CPU < 80%` chưa chứng minh hệ thống khỏe.

~~~mermaid
flowchart TD
    A["HTTP / ứng dụng<br/>request latency, lỗi, throughput"] --> C["Correlation ID / tracing"]
    B["Java Driver<br/>pool, retry, exception"] --> C
    D["Neo4j Server<br/>query, transaction, lock, cache"] --> C
    C --> O["Dashboard + alerts + runbook"]
~~~

### 12.1. Bảng tín hiệu tối thiểu

| Nhóm | Tín hiệu | Ý nghĩa |
|---|---|---|
| **Availability** | Readiness của API và khả năng kết nối DB | Dịch vụ có phục vụ tác vụ nghiệp vụ cơ bản? |
| **Latency** | p50/p95/p99 theo endpoint, repository operation | Phần lớn request và đuôi chậm |
| **Throughput** | Requests/s, successful queries/s, committed tx/s | Tải vào và công việc hoàn thành |
| **Errors** | API error ratio, Neo4j exception code, query failure | Lỗi ứng dụng, quyền, truy vấn hoặc server |
| **Transactions** | Active, committed, rolled back, terminated | Tải giao dịch và khả năng thất bại |
| **Locks** | `waitTime`, `activeLockCount` khi có | Nghi ngờ tranh chấp ghi |
| **Memory/CPU** | Heap, GC, page cache, RSS, container OOM | Sức khỏe tài nguyên |
| **Connections** | Pool wait, acquisition timeout, Bolt connections | Nghẽn kết nối |
| **Storage** | Disk free, store/log growth | Nguy cơ hết dung lượng |
| **Backup** | Backup success, tuổi bản sao, restore test | Khả năng phục hồi dữ liệu |

**Tách đơn vị:** request/s ≠ queries/s ≠ transactions/s. Một HTTP request có thể chạy nhiều Cypher và một transaction có thể chứa nhiều query.

### 12.2. p95/p99 và rate

Ví dụ trong một cửa sổ 60 giây (số giả định):

~~~text
Query success counter: 10.000 → 10.300   = 300 query
Query failure counter:    100 →    106   =   6 query
Transaction rollbacks:     50 →     56   =   6 tx

Successful query rate = 300 / 60 = 5 query/s
Query failure ratio   = 6 / 306 ≈ 1,96%
Rollback rate         = 6 / 60  = 0,1 tx/s
~~~

**Không suy rằng 6 failed queries chính là 6 rolled-back transactions.** Những counter có định nghĩa khác nhau và có thể ghi nhận nhiều sự kiện cho cùng request. Khi exporter/DBMS restart, counter có thể reset; dùng phép `rate`/`increase` phù hợp với nguồn dữ liệu.

`p95` là phân vị của **phân bố latency**, không phải trung bình. Đừng lấy `avg(p95_instance_1, p95_instance_2)` để tạo p95 toàn cluster; phải tổng hợp histogram/distribution đúng cách.

## 13. Giám sát baseline: log và ứng dụng

Ngay cả khi Community không cung cấp đầy đủ metrics server Enterprise, người học vẫn có thể thiết lập giám sát ở tầng ứng dụng.

### 13.1. Đo thời gian repository bằng Java

~~~java
long startNanos = System.nanoTime();
boolean success = false;
try {
    var codes = gateway.projectsOf("U01");
    success = true;
    return codes;
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    // Gửi elapsedNanos, operation="projectsOf", success
    // đến Micrometer/OTel; không dùng uid làm metric label.
}
~~~

Đây là **mẫu code đặt trong một method trả `List<String>`**, không phải file Java độc lập. Số đo bao gồm các bước được gọi qua `gateway.projectsOf`, kể cả thời gian chờ connection, query và lấy kết quả.

Trong Spring Boot, dùng **Micrometer Timer** hoặc OpenTelemetry để đo histogram. Tránh gắn `uid`, email, toàn câu Cypher hay tham số nghiệp vụ vào metric label: chúng có thể chứa dữ liệu nhạy cảm và tạo **high cardinality**.

### 13.2. Log lỗi có cấu trúc

Ứng dụng nên ghi:

- Tên operation ổn định, ví dụ `projectsOf` hoặc `createMembership`.
- Loại lỗi Java Driver, mã Neo4j và GQLSTATUS khi API/phiên bản hỗ trợ.
- Request ID/trace ID **không nhạy cảm**.
- Database, thời điểm, thời lượng, số lần retry nếu instrumentation có.
- Phân loại lỗi: validation, authentication, authorization, transient, timeout, unavailable.

**Không ghi** mật khẩu, token, email, toàn bộ parameter map hoặc câu Cypher có literal nhạy cảm. Log được bảo vệ bằng quyền đọc, retention và khả năng tìm kiếm phù hợp.

### 13.3. Kiểm tra transaction đang chạy

Với quyền giám sát phù hợp, trong Neo4j Browser hoặc cypher-shell:

~~~cypher
SHOW TRANSACTIONS
YIELD database, transactionId, username, status,
      elapsedTime, waitTime, activeLockCount, currentQuery
RETURN database, transactionId, username, status,
       elapsedTime, waitTime, activeLockCount, currentQuery
ORDER BY waitTime DESC
LIMIT 20;
~~~

`waitTime` là **thời gian tích lũy chờ khóa**, không chứng minh transaction **đang chờ** ở thời điểm hiện tại. `activeLockCount` là số khóa đang giữ, không tự nói transaction đang chặn người khác. Cần xem `status`, lấy nhiều snapshot và đối chiếu query log/metrics.

Tài khoản thường có thể chỉ nhìn thấy một phần transaction theo quyền; muốn giám sát toàn hệ thống, dùng một **observer identity** có quyền xem phù hợp thay vì mở admin cho ứng dụng nghiệp vụ.

## 14. Mở rộng Enterprise: query log và Prometheus

Phần này dành cho **Neo4j Enterprise self-managed** với quyền cấu hình máy chủ và tính năng metrics/log được hỗ trợ. Không đặt nguyên các dòng này vào Community hoặc Aura rồi giả định chúng có hiệu lực.

Ví dụ `neo4j.conf` cho môi trường quan sát:

~~~properties
# Query logging: ghi truy vấn hoàn tất chậm hơn ngưỡng thử nghiệm.
db.logs.query.enabled=INFO
db.logs.query.threshold=250ms
db.logs.query.parameter_logging_enabled=false

# Prometheus endpoint: chỉ trên mạng giám sát nội bộ.
server.metrics.prometheus.enabled=true
server.metrics.prometheus.endpoint=0.0.0.0:2004
~~~

**Cảnh báo:** `0.0.0.0:2004` làm server lắng nghe trên các interface của container/host. Chỉ dùng khi mạng giám sát và firewall/network policy **giới hạn chặt**; với Docker, không xuất bản cổng này ra Internet. Nếu Prometheus chạy cùng host, có thể bind loopback và cấu hình scraper phù hợp thay vì mở rộng interface.

**Query log không phải transaction log.** Query log phục vụ chẩn đoán câu Cypher đã chạy, latency và lỗi; transaction log phục vụ ghi thay đổi/durability/recovery. Cần retention khác nhau và không coi query log là backup.

### 14.1. Chọn metric Neo4j thực sự có mặt

Các tên metric logic có thể gặp trong tài liệu Enterprise gồm:

~~~text
<prefix>.db.query.execution.success
<prefix>.db.query.execution.failure
<prefix>.db.query.execution.latency.millis
<prefix>.database.<db>.transaction.active
<prefix>.database.<db>.transaction.committed
<prefix>.database.<db>.transaction.rollbacks
~~~

`success`, `failure` và các tổng transaction là **counter**; `active` là **gauge**; `latency.millis` là **histogram** hoặc dạng phân bố được exporter hỗ trợ. Tên xuất sang Prometheus có thể thay đổi dấu chấm, hậu tố và labels.

Trước khi viết PromQL phải đọc **payload metrics thực** và các dòng `HELP`/`TYPE`, xác định database/member, phiên bản và kiểu metric. **Không tạo dashboard cho tên metric phỏng đoán rồi diễn giải đồ thị rỗng là giá trị 0.**

### 14.2. Bảo vệ endpoint và query log

- Giới hạn người có quyền đọc metrics/log vì chúng có thể tiết lộ topology, tải, thông tin người dùng và query.
- Không bật `parameter_logging_enabled=true` trên dữ liệu thật chỉ để dễ debug.
- Dùng sampling/ngưỡng slow query phù hợp; không ghi toàn bộ query kéo dài trong production nếu chưa đánh giá chi phí.
- Chọn thời gian giữ log và phương án xóa/ẩn dữ liệu nhạy cảm theo chính sách tổ chức.
- Đừng gửi credential hoặc nguyên câu truy vấn có PII vào ticket hỗ trợ.

## 15. Đặt SLO và ngân sách kiểm thử

Không có SLO thì việc “database chạy nhanh” khó nghiệm thu. Với đồ án, chọn các mục tiêu **giả định để thực hành** (không phải SLA Neo4j):

| SLO/giới hạn | Ví dụ mục tiêu lab | Cách đo |
|---|---|---|
| API đọc dự án p95 | Dưới 250 ms ở tải thử xác định | Micrometer/OTel hoặc load test |
| API đọc dự án p99 | Dưới 750 ms ở cùng workload | Histogram/distribution đúng |
| API error ratio | Dưới 1% sau warm-up, khi dữ liệu hợp lệ | Lỗi cuối cùng ở ứng dụng |
| Query correctness | 100% bộ kiểm thử nghiệp vụ đạt | Assertion trên fixture |
| Container memory | Không vượt giới hạn 4 GiB/không bị OOM kill | Docker/host metrics |
| Pool acquisition | Không bị timeout trong tải thiết kế | Driver/app instrumentation |
| Authorization | Reader không lộ property/label nhạy cảm | Positive/negative tests |
| Recovery | Có runbook và restore test theo phạm vi đồ án | Biên bản diễn tập |

**Các mốc latency chỉ có ý nghĩa nếu ghi rõ:** số request đồng thời, thời lượng đo, tỷ lệ read/write, kích thước graph, môi trường máy, cơ chế warm-up và edition. Graph hai người dùng không đủ để kết luận hệ thống production đạt SLO trên hàng triệu node.

### Đừng dùng một biến để chữa mọi vấn đề

| Triệu chứng | Giả thuyết cần kiểm tra | Chưa nên làm ngay |
|---|---|---|
| p99 tăng, server query latency bình thường | Chờ connection, network, retry, mapping | Tăng page cache mù quáng |
| Query `DB Hits` lớn, fan-out cao | Index hoặc mô hình/truy vấn chưa phù hợp | Chỉ tăng `-Xmx` |
| Heap/GC tăng mạnh | Query state quá lớn, cấu hình heap | Nâng pool size vô hạn |
| Container OOM kill, heap chưa đầy | Native memory/OS/page cache | Kết luận “JVM không lỗi nên ổn” |
| Write latency và `waitTime` tăng | Tranh chấp hot node/transaction dài | Tăng số writer vô hạn |
| Query failure và rollback tăng | Schema, quyền, timeout, transient errors | Retry mọi exception |

## 16. Thực nghiệm tải có kiểm soát

### 16.1. Mở rộng dữ liệu test một cách xác định

Trên một database test cô lập, có thể tạo thêm 5.000 node `:CapLoadUser` để thử index và query:

~~~cypher
CREATE CONSTRAINT cap_load_user_id_unique IF NOT EXISTS
FOR (u:CapLoadUser)
REQUIRE u.uid IS UNIQUE;
~~~

~~~cypher
UNWIND range(1, 5000) AS n
MERGE (u:CapLoadUser {uid: 'L' + toString(n)})
SET u.groupId = 'G' + toString(n % 25),
    u.score = n % 100;
~~~

Tạo truy vấn đọc có tham số:

~~~cypher
MATCH (u:CapLoadUser)
WHERE u.groupId = $groupId
RETURN u.uid AS uid, u.score AS score
ORDER BY score DESC, uid ASC
LIMIT 50;
~~~

Đây chỉ là dataset nhỏ để thực hành, không đại diện cho mạng đồ thị nhiều triệu cạnh. Nếu muốn so query plan, có thể tạo range index:

~~~cypher
CREATE RANGE INDEX cap_load_group_score IF NOT EXISTS
FOR (u:CapLoadUser)
ON (u.groupId, u.score);
~~~

Đợi index `ONLINE`, chạy lại cùng query và tham số. Neo4j planner có thể vẫn chọn scan khi dataset nhỏ; **đừng viết assertion bắt buộc phải dùng index trong mọi trường hợp**.

### 16.2. Kiểm thử theo tải tăng dần

Đề xuất lịch workload mẫu:

| Giai đoạn | Tải đề xuất | Điều cần quan sát |
|---|---|---|
| Warm-up | Vài request/s, dữ liệu đã nạp | Kết nối, cache, lỗi cấu hình |
| Baseline | 10 request/s trong cửa sổ đo | p50/p95/p99 và query correctness |
| Tăng dần | 20 rồi 40 request/s | Throughput, pool wait, CPU/RSS |
| Ghi thử | Một số `MERGE` trên khóa riêng | Lock wait, rollback, duplicate |
| Giảm tải | Quay về baseline | Latency có hồi phục, không rò tài nguyên |

Tải trong bảng là **gợi ý**, phải điều chỉnh theo tài nguyên máy. Không dùng script benchmark không giới hạn concurrency hoặc `MATCH` duyệt vô hạn trên production.

**Phân biệt nguyên nhân:** nếu p95 tăng khi concurrency tăng, có thể do CPU, pool, lock hoặc bản thân query. Phải đối chiếu các tín hiệu, không chỉ ghi nhận “Neo4j chịu được 40 RPS”.

## 17. Diễn tập lỗi và kiểm tra khả năng phục hồi

Chỉ thực hiện các thử nghiệm dưới đây trên **môi trường cô lập được phép**. Mục tiêu là học cách quan sát phản ứng và quay về trạng thái an toàn, không phải cố gây lỗi cho hệ thống thật.

### Kịch bản A — Sai credential

1. Thử kết nối bằng password sai.
2. Kỳ vọng xác thực bị từ chối, không thực thi Cypher.
3. Kiểm tra ứng dụng không log mật khẩu.
4. Khôi phục credential đúng, chạy query nghiệp vụ `projectsOf("U01")`.

### Kịch bản B — Neo4j tạm thời không sẵn sàng

1. Trên lab, dừng container Neo4j có kiểm soát.
2. Gọi một request test; ghi exception, timeout và trạng thái API.
3. Xác minh ứng dụng **không retry vô hạn** hoặc bị treo.
4. Khởi động lại Neo4j, chạy readiness và query đối chứng.
5. Ghi nhận dữ liệu/constraint còn đúng; volume giữ dữ liệu không thay cho backup.

### Kịch bản C — Pool connection cạn

1. Trên staging, tạm đặt pool nhỏ hơn tải dự kiến.
2. Tăng số request đồng thời **có giới hạn**.
3. Quan sát acquisition timeout, số request chờ và p95/p99.
4. Hạ tải, kiểm tra pool hồi phục.
5. Khôi phục cấu hình và chọn pool size theo số instance ứng dụng, số kết nối server và tải thật.

### Kịch bản D — Transaction dài/chờ khóa

1. Trong Neo4j test, tạo một node riêng `:CapTestAccount` với ID cố định.
2. Mở hai session ghi trong **hai transaction riêng** cùng cập nhật node đó.
3. Giữ transaction thứ nhất ngắn, có kiểm soát; quan sát transaction thứ hai chờ.
4. Dùng `SHOW TRANSACTIONS`, đo `waitTime` và so latency của ứng dụng.
5. Commit/rollback và đóng cả hai session, không để khóa treo trong lab.

**Không cần cố tạo deadlock hoặc OOM** để hoàn thành đồ án. Diễn tập lỗi mạng, timeout và tranh chấp có kiểm soát đủ để chứng minh giám sát và runbook.

## 18. Kiểm tra backup và phục hồi

Với hệ thống production, **không thể chỉ bảo đảm dữ liệu bằng persistent volume hoặc cluster**. Backup cần chính sách retention, kiểm soát truy cập, lưu tách biệt và kiểm chứng restore.

### Checklist khôi phục

1. Xác định bản Neo4j/edition hỗ trợ công cụ backup nào; không chạy lệnh backup Enterprise trên Community rồi coi lỗi là do dữ liệu.
2. Ghi thời điểm bản sao, loại full/incremental nếu hỗ trợ, vị trí lưu và mức mã hóa.
3. Thử restore vào **instance test mới**, không ghi đè nguồn đang hoạt động.
4. So số node/relationship theo nhãn/type, constraint/index và các truy vấn nghiệp vụ.
5. Kiểm tra quyền, credential và network của instance phục hồi.
6. Ghi khoảng mất dữ liệu (RPO quan sát được) và thời gian phục hồi (RTO quan sát được).

**Managed không loại bỏ trách nhiệm này:** nhà cung cấp có thể vận hành backup theo gói, nhưng đội ứng dụng vẫn phải xác minh phương án restore thực sự đáp ứng yêu cầu. Không đồng nhất SLA availability với RPO hoặc RTO.

## 19. Ma trận kiểm thử tích hợp của đồ án

| ID | Phạm vi | Bài thử | Điều kiện PASS |
|---|---|---|---|
| T01 | Kết nối | Authentication đúng/sai | Đúng cho truy vấn hợp lệ, sai bị từ chối |
| T02 | Network | Kiểm tra Bolt/HTTP binding | Không phơi cổng ngoài phạm vi thiết kế |
| T03 | Dữ liệu | Nạp fixture, chạy truy vấn Java/SDN | U01 có đúng P01 và P02 |
| T04 | Schema | Tạo uniqueness constraint | ID trùng bị từ chối; dữ liệu không hỏng |
| T05 | RBAC Enterprise | Reader xem ID/tên | Query hợp lệ có kết quả đúng |
| T06 | RBAC Enterprise | Reader xem email/CapSecret | Không lộ dữ liệu admin xác nhận tồn tại |
| T07 | RBAC Enterprise | Reader cố `SET` | Bị từ chối, property trước/sau không đổi |
| T08 | Resources | Kiểm tra heap/page cache/container cap | Cấu hình hiệu lực, không OOM ở tải thiết kế |
| T09 | Driver pool | Kiểm tra timeout dưới tải giới hạn | Không có timeout ở tải mục tiêu; lỗi có mã/trace |
| T10 | Monitoring | Có query latency và error metrics | Dashboard có số đo và đơn vị rõ |
| T11 | Transactions | Diễn tập chờ khóa | Có bằng chứng quan sát, kết thúc sạch |
| T12 | Failure | DB dừng/tái khởi động trong lab | App thất bại có giới hạn, phục hồi đúng |
| T13 | Backup | Restore rehearsal khi tính năng cho phép | Dữ liệu/schema sau restore được đối chiếu |
| T14 | Security logging | Đọc log và dashboard | Không có secret/PII không cần thiết |
| T15 | Regression | Test sau khi thay cấu hình | Kết quả nghiệp vụ không đổi, SLO còn đạt |

Một bài thử nên ghi **input, thao tác, kết quả mong đợi, kết quả thực, bằng chứng và kết luận**. Với test không áp dụng do edition, ghi rõ lý do và rủi ro còn lại, không lấp bằng giả định.

### Bằng chứng đáng tin hơn ảnh chụp giao diện

- Mẫu query Cypher và tham số thử **không nhạy cảm**.
- Assertion JUnit/Testcontainers hoặc kết quả kiểm thử có thể lặp lại.
- Query log/exception code và timestamp đã làm sạch thông tin.
- Dashboard có chú thích instance/database/cửa sổ đo.
- Bản so sánh cấu hình trước/sau và kết quả xác minh setting thực.
- Biên bản thử failover/restore theo đúng phạm vi môi trường.

## 20. Runbook khi hệ thống có sự cố

### 20.1. API chậm

1. Xem HTTP latency p95/p99 và request rate.
2. So với server query latency để biết bottleneck nằm trong DB hay ngoài DB.
3. Kiểm tra pool acquisition timeout, các lần retry, kết nối và DNS/TLS.
4. Xem `SHOW TRANSACTIONS` để tìm giao dịch chờ khóa hoặc kéo dài.
5. Đọc query log nếu môi trường hỗ trợ, lấy Cypher thực tế và tham số đã làm sạch.
6. Chạy `EXPLAIN`/`PROFILE` trên **môi trường an toàn** để xem `Rows`, `DB Hits`, index và fan-out.
7. Sửa query/index/transaction boundary trước khi tăng tài nguyên nếu vấn đề là logic truy vấn.
8. Đo lại cùng workload và xác minh kết quả nghiệp vụ không đổi.

### 20.2. Transaction thất bại tăng

1. Phân loại theo exception/code: auth, authorization, schema, deadlock/transient, timeout, unavailable.
2. So query failures với transaction rollback, không mặc định chúng là một sự kiện.
3. Kiểm tra thay đổi role, constraint, index hoặc bản deploy gần nhất.
4. Với lỗi transient, dùng managed transaction retry có giới hạn; xác minh idempotency của ghi.
5. Với lỗi không rõ commit, đọc lại theo khóa nghiệp vụ trước khi tạo bản ghi lần nữa.
6. Ghi incident timeline và rút kinh nghiệm cập nhật alert/runbook.

### 20.3. Bộ nhớ hoặc disk gần giới hạn

1. Kiểm tra RSS/container memory, heap, page cache, GC, native memory và free disk.
2. Kiểm tra truy vấn mới, batch import, sort/aggregation và thời gian transaction.
3. Xem backup/log retention có làm tăng dung lượng không.
4. Giảm tải hoặc dừng job nền theo quy trình nếu có nguy cơ mất dịch vụ.
5. Chỉ mở rộng heap/page cache/disk sau khi xác nhận đủ tài nguyên và tính toán lại tổng ngân sách.
6. Cảnh báo trước khi OOM hoặc hết disk; không chờ tiến trình bị dừng.

## 21. Rubric đánh giá đồ án

Đề xuất chấm theo 100 điểm (rubric minh họa để người học tự kiểm):

| Nhóm | Điểm | Điều kiện đạt điểm cao |
|---|---:|---|
| **Kiến trúc và threat model** | 15 | Ranh giới tin cậy, danh tính, đường mạng, dữ liệu nhạy cảm rõ |
| **Bảo mật và negative tests** | 25 | Auth, least privilege theo edition, không lộ dữ liệu, không ghi trái phép |
| **Ngân sách và giới hạn tài nguyên** | 20 | Heap/page cache/CPU/pool/timeout hợp lý, có test dưới tải |
| **Giám sát và alert** | 20 | Latency/throughput/error/locks/resource có nguồn, đơn vị và baseline |
| **Kiểm thử, recovery và runbook** | 15 | Có positive/negative, lỗi có kiểm soát, khôi phục và đối chiếu |
| **Báo cáo/bằng chứng** | 5 | Có dữ liệu đo và giới hạn, không khẳng định điều chưa kiểm chứng |

**Điều kiện loại trừ khỏi PASS production:** credential admin dùng làm runtime lâu dài, database công khai không cần thiết, tắt auth/TLS qua mạng không tin cậy, không kiểm soát quyền đọc dữ liệu nhạy cảm hoặc thiếu kế hoạch backup/restore cho dữ liệu quan trọng. Một demo có thể chạy được nhưng vẫn không đủ tiêu chuẩn sản xuất.

## 22. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Hướng khắc phục |
|---|---|---|
| Dùng user `neo4j` admin cho mọi service | Quyền quá rộng; lỗi hoặc lộ credential ảnh hưởng toàn DB | Tách identity/runtime và migration |
| Cho rằng Community có mọi RBAC Enterprise | Sai khả năng edition | Ghi giới hạn, chọn edition/gói đáp ứng yêu cầu |
| Giấu email trong DTO nhưng cho tài khoản DB đọc tất cả | Không có defense in depth | Tối thiểu quyền DB khi khả dụng, test viewer authorization |
| Đặt password trong repository Git | Dễ lộ qua commit, backup, image | Secret management/rotate/kiểm tra log |
| Mở `7474`/`7687` ra Internet không cần thiết | Tăng bề mặt tấn công | Bind loopback/private, firewall và TLS |
| Tổng heap + page cache = mem_limit | Thiếu chỗ cho native/OS | Chừa overhead, đo RSS và OOM |
| Tăng pool để chữa mọi request chậm | Có thể làm server bão hòa hơn | Đo pool wait, query cost và concurrency |
| Bỏ timeout để import “không bị ngắt” | Transaction dài giữ tài nguyên/khóa | Batch size, checkpoint, timeout theo job |
| Chỉ đo latency trung bình | Bỏ sót p95/p99 xấu | Histogram/SLO theo endpoint |
| Coi rollback = failed query | Đơn vị và nguyên nhân khác nhau | Theo dõi riêng query và transaction |
| `waitTime` cao nghĩa là đang chặn lúc xem | Là thời gian chờ tích lũy | Kết hợp status, snapshot và logs |
| Coi `LIMIT` là cách ngăn mọi traversal rộng | Engine có thể mở rộng nhiều hàng trước limit | Ràng buộc đường đi, index, `PROFILE` |
| Chỉ đo Community metrics rồi khẳng định có Prometheus Enterprise | Không kiểm tra edition/tên metric | Xác minh source và capabilities |
| Thấy container “Up” là DB sẵn sàng | Neo4j có thể chưa online hoặc query nghiệp vụ lỗi | Readiness và integration query |
| Volume Docker được xem là backup | Không phục hồi khi mất volume/lỗi logic | Backup và restore drill |
| Test lỗi trên production | Có thể làm gián đoạn người dùng thật | Chỉ diễn tập trong lab/staging cô lập |

## 23. Bài tập tự kiểm tra

### Bài 1 — Ngân sách bộ nhớ

Container có giới hạn **4 GiB**, heap tối đa **2.5 GiB**, page cache **2 GiB**. Thiết kế này có vấn đề gì?

**Đáp án gợi ý:** Hai thành phần đã vượt 4 GiB trước khi tính native/off-heap/OS, có nguy cơ OOM kill. Giảm heap/page cache hoặc tăng container budget trên host đủ tài nguyên, rồi đo RSS, page faults và GC với workload thực tế.

### Bài 2 — Bảo mật ở mức nào?

Một ứng dụng Community che `CapUser.email` khỏi JSON response, nhưng dùng credential có quyền đọc mọi node/property. Có thể công bố “Neo4j đã áp dụng least privilege theo property” không?

**Đáp án:** Không. Đây là lọc dữ liệu ở tầng API. Muốn hạn chế property tại DB, cần tính năng RBAC chi tiết của edition/gói tương ứng và test bằng credential reader; vẫn phải duy trì authorization theo người dùng HTTP.

### Bài 3 — Latency bị hiểu nhầm

API p99 là 1.000 ms trong khi query latency server khoảng 80 ms. Bước nào cần kiểm tra trước khi tăng heap Neo4j?

**Đáp án:** Connection pool wait, network/TLS, driver retry, thời gian Spring mapping, xử lý ứng dụng, queue HTTP và các dịch vụ ngoài. Một metric server không bao gồm toàn bộ request.

### Bài 4 — Quyền bị từ chối có phải luôn exception?

Reader chạy `MATCH (s:CapSecret) RETURN count(s)` và nhận `0`. Có phải database không có node `CapSecret`?

**Đáp án:** Chưa thể kết luận. RBAC có thể che node qua thiếu `TRAVERSE`. Admin phải xác nhận dữ liệu fixture thật có node trước khi dùng kết quả reader làm bằng chứng về phân quyền.

### Bài 5 — Giới hạn pool

Một service có 6 instance, mỗi instance cấu hình tối đa 40 kết nối trong pool. Có thể khẳng định toàn hệ thống chỉ mở tối đa 40 connection đến Neo4j không?

**Đáp án:** Không. Mỗi Driver/instance có pool riêng; với cluster và nhiều server, kết nối phân bố theo topology. Phải kiểm tra tổng kết nối, giới hạn server, số replica và cách pool hoạt động ở version driver đang dùng.

### Bài 6 — Retry với thao tác ghi

Lệnh `CREATE (:Invoice)` bị mất kết nối đúng lúc commit. Ứng dụng tự retry câu query, kết quả có hai invoice. Nên bổ sung những gì?

**Đáp án:** Dùng khóa nghiệp vụ/request ID cố định và unique constraint, `MERGE`/luồng idempotent, kiểm tra trạng thái sau lỗi commit không rõ, không retry vô hạn. Transaction retry không bảo đảm exactly-once trên toàn bộ hệ thống.

### Bài 7 — Giám sát có số 0

Dashboard Prometheus không hiển thị metric query latency từ container Community. Người học ghi kết quả “0 ms vì Neo4j rất nhanh”. Vì sao sai?

**Đáp án:** Không có metric không đồng nghĩa giá trị 0. Cần kiểm tra edition/exporter/config, đọc payload metrics và đo latency từ ứng dụng. Ghi rõ khả năng quan sát bị giới hạn, không dựng số liệu.

### Bài 8 — Nghiệm thu sau chỉnh cấu hình

Sau khi tăng page cache, p95 giảm nhưng kiểm thử nghiệp vụ báo thiếu một dự án trong danh sách. Có nên cho bản cập nhật đạt không?

**Đáp án:** Không. Tối ưu tài nguyên không được làm sai kết quả truy vấn hoặc làm mất quyền/data. Phải điều tra vì sao kết quả khác, kiểm tra dữ liệu/transaction/quan hệ và chạy lại cả regression tests lẫn load test.

## 24. Báo cáo mẫu cho người học

Một bản báo cáo hoàn thành nên có cấu trúc:

~~~text
Tên đồ án: Neo4j Capstone - Security, Observability, Resource Limits
Phiên bản / Edition / môi trường:
Database / topology:
Mô tả workload và dữ liệu mẫu:

1. Sơ đồ kiến trúc và danh tính kết nối:
2. Cấu hình bảo mật và ma trận quyền:
3. Cấu hình heap, page cache, CPU, memory, pool, timeout:
4. Dashboard và nguồn đo thực tế:
5. Kết quả positive/negative tests:
6. Kết quả load test (rps, p50/p95/p99, error ratio):
7. Kết quả failure drill và restore rehearsal:
8. Rủi ro còn lại / N/A do edition hoặc gói:
9. Điều kiện go/no-go trước production:
10. Runbook và owner của từng hạng mục:
~~~

Nếu chưa có Neo4j Enterprise, hãy ghi rõ **“fine-grained RBAC/server metrics: NOT TESTED on Community”** và trình bày cách kiểm thử bổ sung trên môi trường hỗ trợ. Một đồ án trung thực về giới hạn kỹ thuật có giá trị hơn báo cáo “PASS toàn bộ” không có bằng chứng.

## 25. Tài liệu chính thức tham khảo

- [Neo4j Operations Manual — Configuration](https://neo4j.com/docs/operations-manual/current/configuration/)
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/)
- [Neo4j Operations Manual — Authentication & authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/)
- [Neo4j Operations Manual — Monitoring](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Neo4j Operations Manual — Metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/)
- [Neo4j Operations Manual — Query logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Transactions](https://neo4j.com/docs/operations-manual/current/database-internals/)
- [Neo4j Java Driver — Configuration](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

Tài liệu theo đường dẫn `current` có thể thay đổi theo release. Khi triển khai thực, phải tra đúng **Neo4j version, edition, Java Driver/SDN version và khả năng cấu hình của môi trường managed**; không đưa cấu hình dành cho Enterprise self-managed vào Aura hoặc Community một cách máy móc.

## 26. Ghi nhớ

- **Bảo mật, giám sát và giới hạn tài nguyên là ba lớp bảo vệ bổ sung**, không thay thế nhau.
- **Authentication thành công không chứng minh least privilege**: cần test quyền hiệu lực, kết quả bị che và ghi bị từ chối khi edition hỗ trợ.
- **Heap, page cache và native memory cùng dùng ngân sách của host/container**; kết hợp giới hạn DB với query tuning và timeout có kiểm soát.
- **Driver pool, timeout và retry phải dựa trên workload đo được**; tăng các ngưỡng không tự sửa truy vấn Cypher không hiệu quả.
- **Theo dõi p95/p99, throughput, lỗi, rollback, khóa, bộ nhớ và kết nối** từ đúng nguồn; không biến metric không có mặt thành giá trị 0.
- **Đồ án chỉ đạt khi có bằng chứng thực nghiệm:** các truy vấn nghiệp vụ đúng, quyền được kiểm chứng, tải phù hợp, lỗi được xử lý và có phương án phục hồi.
