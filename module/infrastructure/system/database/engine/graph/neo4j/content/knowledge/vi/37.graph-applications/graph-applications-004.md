# Quản lý phân quyền và đường kế thừa quyền trong tổ chức

## 1. Bài toán: một quyền có thể đến từ nhiều đường trong graph

Trong tổ chức, quyền truy cập một tài liệu không nhất thiết được gán trực tiếp cho từng nhân viên. Một người có thể thuộc **nhóm dự án**, nhóm được gán **vai trò**, vai trò cao kế thừa vai trò thấp, còn quyền trên **thư mục** có thể áp dụng cho tài liệu con. Vì vậy câu hỏi “Người dùng U01 có thể sửa DOC1 không?” thực chất là truy vấn nhiều đường quan hệ có điều kiện.

Ví dụ về một chuỗi cấp quyền:

~~~text
U01 --MEMBER_OF--> G_DEV --ASSIGNED_ROLE--> EDITOR
EDITOR --INHERITS--> VIEWER
VIEWER --GRANTS {action:READ}--> PRJ
DOC1 --PART_OF--> PRJ
~~~

Chuỗi trên giải thích vì sao U01 có thể đọc DOC1 dù không có cạnh `GRANTS` trực tiếp từ U01 đến DOC1. Nhưng nếu U01 có một **DENY** áp dụng cho DOC1, kết luận cuối cùng có thể chuyển thành **không cho phép**, bất kể có bao nhiêu đường cấp quyền.

Bài này thuộc chương **Ứng dụng đồ thị** trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`. Nó kết nối mô hình **property graph**, truy vấn đường đi bằng **Cypher**, index/constraint, tối ưu truy vấn và việc kiểm tra quyền từ **Neo4j Java Driver** hoặc **Spring Data Neo4j** để xây một hệ thống quản lý truy cập có thể giải thích và kiểm thử được.

**Sau bài học, bạn sẽ có thể:**

1. Chuyển yêu cầu phân quyền của tổ chức thành node, relationship và các quy tắc truy vấn rõ ràng.
2. Phân biệt quyền được gán **trực tiếp**, qua **nhóm**, qua **kế thừa vai trò** và qua **phạm vi tài nguyên**.
3. Tính quyền hiệu lực (*effective permission*) với chính sách **default deny** và **explicit deny overrides grant**.
4. Truy vấn **đường giải thích** vì sao một quyền được đề xuất cấp, rồi kiểm tra xem có đường từ chối phủ định hay không.
5. Tích hợp kiểm tra và thay đổi dữ liệu trong transaction Java/SDN, không tin vào `userId` do client tự khai báo.
6. Nhận diện rủi ro vòng lặp kế thừa, leo thang đặc quyền, lộ dữ liệu giữa tenant, stale cache và N+1 query.
7. Kiểm thử tính đúng bằng fixture có bảng kết quả dự kiến độc lập.

> **Phạm vi và nguyên tắc:** Đây là **mô hình phân quyền ở tầng ứng dụng** trên graph Neo4j, **không phải** cách Neo4j DBMS nội bộ triển khai `GRANT`/`DENY` cho database roles. Chính sách cụ thể trong bài được định nghĩa tường minh để có thể kiểm chứng; không được coi nó là một chuẩn bảo mật dùng chung cho mọi tổ chức. Ví dụ hướng tới Neo4j 5+ và Java 17+; cần đối chiếu API với phiên bản thực tế.

## 2. Từ RBAC cơ bản đến RBAC có thứ bậc và phạm vi

**RBAC (Role-Based Access Control)** gán quyền theo vai trò thay vì gán mọi quyền cho từng người dùng. Với mô hình có kế thừa (*hierarchical RBAC*), vai trò cao có thể nhận quyền của vai trò thấp.

Ví dụ:

~~~text
MANAGER --> EDITOR --> VIEWER
AUDITOR -------------> VIEWER
~~~

Trong bài, chiều cạnh là:

`(roleCon)-[:QA004_INHERITS]->(roleCha)`

Nghĩa là:

- MANAGER có quyền của MANAGER, EDITOR và VIEWER.
- EDITOR có quyền của EDITOR và VIEWER.
- AUDITOR có quyền của AUDITOR và VIEWER.
- VIEWER **không** tự nhận quyền của EDITOR/MANAGER/AUDITOR.

Ngoài vai trò, ta còn xét **phạm vi tài nguyên**. Một quyền `READ` được cấp ở thư mục PRJ có thể áp dụng cho DOC1 và DOC2 nếu cả hai thuộc PRJ:

~~~text
DOC1 --PART_OF--> PRJ --PART_OF--> ROOT
DOC2 --PART_OF--> PRJ --PART_OF--> ROOT
FIN1 --PART_OF--> FIN --PART_OF--> ROOT
~~~

Đường `PART_OF` được truy từ tài nguyên con **lên** tài nguyên cha để tìm grant/deny áp dụng trên các ancestor. Cấp quyền ở DOC1 **không** tự cấp quyền cho thư mục PRJ hoặc DOC2.

### 2.1. Mô hình này không tự động là ABAC

**ABAC (Attribute-Based Access Control)** xét thêm thuộc tính như bộ phận, độ mật, chủ sở hữu, thời gian, trạng thái duyệt hoặc thiết bị truy cập. Một hệ thống thực tế có thể kết hợp RBAC và ABAC, nhưng fixture của bài **chỉ tính RBAC + cây tài nguyên + direct deny**. Những kiểm tra như “chỉ nhân viên đang làm việc”, “chỉ xem tài liệu nội bộ”, “không duyệt đơn của chính mình” phải được bổ sung rõ, không được giả định đã có trong Cypher.

## 3. Định nghĩa chính sách trước khi viết câu truy vấn

Để kết quả không phụ thuộc cách hiểu ngầm, ta chọn các quy tắc sau:

| Quy tắc | Ý nghĩa chính xác |
|---|---|
| **P1 — Default deny** | Không có đường cấp quyền hợp lệ thì **từ chối** |
| **P2 — Direct role** | Người dùng có thể được gán vai trò trực tiếp |
| **P3 — Group role** | Người dùng có thể thuộc nhóm, nhóm được gán vai trò |
| **P4 — Role inheritance** | Vai trò được gán nhận cả quyền từ tổ tiên theo `INHERITS` |
| **P5 — Resource inheritance** | Grant trên một tài nguyên áp dụng cho chính nó và mọi hậu duệ `PART_OF` |
| **P6 — Explicit deny** | Deny trực tiếp của user trên tài nguyên hoặc ancestor **thắng** mọi grant |
| **P7 — Deny ALL** | Một cạnh deny có `action='ALL'` chặn mọi action được yêu cầu trong phạm vi đó |
| **P8 — Action độc lập** | `WRITE` không tự bao hàm `READ`; `APPROVE` không tự bao hàm `WRITE` |
| **P9 — Không có group lồng nhau** | Fixture chỉ hỗ trợ một cạnh user → group → role |
| **P10 — Độ sâu giới hạn** | Ví dụ truy vấn xét tối đa 5 cạnh `INHERITS` và 5 cạnh `PART_OF` |

**Mô hình trực tiếp chỉ có DENY từ user**; chưa có deny từ group/role. Nếu hệ thống cần chính sách deny của group/role hoặc hiệu lực theo thời gian, phải mở rộng Cypher và bộ test tương ứng. Không thể tự coi các quy tắc đó đã được thực hiện.

Trong production, giới hạn độ sâu phải là **một bất biến của dữ liệu** được kiểm tra khi ghi. Nếu graph có đường kế thừa dài 6 cạnh mà query chỉ duyệt 5, kết quả quyền có thể sai; không được âm thầm dùng giới hạn tùy tiện rồi coi là security policy hoàn chỉnh.

### 3.1. Công thức quyền hiệu lực

Với người dùng `u`, action `a` và tài nguyên `x`:

\[
\operatorname{allowed}(u,a,x)
=
\operatorname{hasGrant}(u,a,x)
\;\land\;
\neg \operatorname{hasDeny}(u,a,x)
\]

Trong đó:

- `hasGrant` đúng nếu tồn tại ít nhất một vai trò được gán cho user (trực tiếp/qua nhóm), một đường kế thừa tới vai trò có grant action `a` trên `x` hoặc một ancestor của `x`.
- `hasDeny` đúng nếu user có cạnh deny action `a` hoặc `ALL` trên `x` hoặc một ancestor của `x`.

**Deny thắng grant**, kể cả khi grant có đường ngắn hơn hoặc đến từ vai trò cao hơn. Không dùng “quyền mới nhất thắng” hay “đường ngắn nhất thắng” nếu chính sách không định nghĩa như vậy.

## 4. Sơ đồ property graph cho tổ chức

~~~mermaid
flowchart LR
    U["QA004User"] -->|"MEMBER_OF"| G["QA004Group"]
    U -->|"ASSIGNED_ROLE"| R["QA004Role"]
    G -->|"ASSIGNED_ROLE"| R
    R -->|"INHERITS (con → cha)"| B["QA004Role tổ tiên"]
    R -->|"GRANTS {action}"| P["QA004Resource"]
    B -->|"GRANTS {action}"| P
    D["QA004Resource con"] -->|"PART_OF"| P
    U -->|"DENIES {action / ALL}"| D
~~~

| Label | Property định danh | Ví dụ | Vai trò |
|---|---|---|---|
| `QA004User` | `userId` | U01, U02 | Danh tính ứng dụng đã xác thực |
| `QA004Group` | `groupId` | G_DEV | Nhóm tổ chức/dự án |
| `QA004Role` | `roleId` | VIEWER, EDITOR | Gói quyền và quan hệ kế thừa |
| `QA004Resource` | `resourceId` | DOC1, PRJ | Đối tượng cần được bảo vệ |

| Relationship | Hướng | Thuộc tính | Ý nghĩa |
|---|---|---|---|
| `QA004_MEMBER_OF` | User → Group | *(không có)* | User thuộc nhóm |
| `QA004_ASSIGNED_ROLE` | User/Group → Role | *(không có)* | Chủ thể được gán vai trò |
| `QA004_INHERITS` | Role con → Role cha | *(không có)* | Kế thừa quyền |
| `QA004_PART_OF` | Resource con → Resource cha | *(không có)* | Cấu trúc phạm vi tài nguyên |
| `QA004_GRANTS` | Role → Resource | `action` | Cho phép action tại scope |
| `QA004_DENIES` | User → Resource | `action` | Từ chối action tại scope |

Tiền tố `QA004` giúp các câu lệnh thực hành không đụng vào label/relationship của mô hình khác. Tuy nhiên, điều này **không bảo đảm** an toàn nếu database thật tình cờ dùng cùng tên; vì vậy chỉ chạy trên database test.

### 4.1. Các quyết định mô hình hóa không thể bỏ qua

- **Role không phải user:** một user có thể có nhiều role và một role có nhiều user.
- **Group không phải role:** đổi cơ cấu nhân sự có thể thay đổi membership mà không sửa định nghĩa quyền.
- **Resource tree là graph có hướng:** child → parent, có thể mở rộng thành DAG khi nghiệp vụ cho phép nhiều scope; khi đó phải xử lý nhiều đường trùng và quy tắc kế thừa.
- **Action là giá trị có kiểm soát:** `READ`, `WRITE`, `APPROVE`, không phải chuỗi tùy ý truyền từ giao diện.
- **Không dùng Neo4j internal node ID làm khóa quyền lâu dài:** dùng business ID có constraint, tránh phụ thuộc định danh lưu trữ có thể thay đổi sau export/restore.

## 5. Fixture có đáp án: sáu nhân viên, bốn vai trò, sáu tài nguyên

### 5.1. Người dùng và vai trò ban đầu

| User | Tên | Gán trực tiếp | Nhóm | Vai trò hiệu lực dự kiến |
|---|---|---|---|---|
| U01 | An | *(không)* | G_DEV → EDITOR | EDITOR, VIEWER |
| U02 | Binh | MANAGER | *(không)* | MANAGER, EDITOR, VIEWER |
| U03 | Chi | *(không)* | G_AUDIT → AUDITOR | AUDITOR, VIEWER |
| U04 | Dung | VIEWER | *(không)* | VIEWER |
| U05 | Em | EDITOR | *(không)* | EDITOR, VIEWER |
| U06 | Giang | *(không)* | *(không)* | *(rỗng)* |

### 5.2. Phạm vi quyền

Các grant của role:

| Vai trò sở hữu grant | Action | Scope | Phạm vi truyền xuống |
|---|---|---|---|
| VIEWER | READ | PRJ | PRJ, DOC1, DOC2 |
| EDITOR | WRITE | PRJ | PRJ, DOC1, DOC2 |
| MANAGER | APPROVE | PRJ | PRJ, DOC1, DOC2 |
| AUDITOR | READ | FIN | FIN, FIN1 |

Các deny trực tiếp:

| User | Action deny | Scope | Tác dụng |
|---|---|---|---|
| U01 | ALL | DOC2 | Không được READ/WRITE/APPROVE trên DOC2 dù có role EDITOR |
| U05 | WRITE | DOC2 | Vẫn READ DOC2, nhưng không được WRITE DOC2 |

**DOC1** và **DOC2** nằm trong PRJ; **FIN1** nằm trong FIN. Cả PRJ và FIN thuộc ROOT nhưng **không có grant trên ROOT**. Do vậy, role VIEWER không thể đọc FIN1 chỉ vì cả hai cùng thuộc một tổ chức.

### 5.3. Ma trận expected authorization

| User | DOC1 READ | DOC1 WRITE | DOC1 APPROVE | DOC2 READ | DOC2 WRITE | FIN1 READ |
|---|---|---|---|---|---|---|
| **U01** (EDITOR từ nhóm) | Có | Có | Không | **Không: DENY ALL** | **Không: DENY ALL** | Không |
| **U02** (MANAGER) | Có | Có | Có | Có | Có | Không |
| **U03** (AUDITOR từ nhóm) | Có | Không | Không | Có | Không | **Có** |
| **U04** (VIEWER) | Có | Không | Không | Có | Không | Không |
| **U05** (EDITOR) | Có | Có | Không | Có | **Không: DENY WRITE** | Không |
| **U06** (không role) | Không | Không | Không | Không | Không | Không |

Đây là **đáp án độc lập** để kiểm chứng truy vấn, không phải bảng được suy ra từ kết quả chạy thử. Các cột đại diện hành động **độc lập**: ví dụ user được WRITE không tự được APPROVE.

## 6. Tạo dữ liệu thực hành: constraint và node

> **An toàn:** Chỉ chạy các câu dưới đây trong database lab không có dữ liệu thật dùng chung nhãn `QA004`. Không chạy đoạn cleanup trước khi kiểm tra chính xác database đích.

### 6.1. Reset fixture nếu đang chạy lại trong lab

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa004_user_id IF EXISTS;
DROP CONSTRAINT qa004_group_id IF EXISTS;
DROP CONSTRAINT qa004_role_id IF EXISTS;
DROP CONSTRAINT qa004_resource_id IF EXISTS;
~~~

Tùy giao diện Cypher, chạy riêng từng câu `DROP CONSTRAINT` nếu công cụ không nhận nhiều statement trong một lệnh. `DETACH DELETE` có tính phá hủy, nên chỉ dùng trong fixture đã được xác nhận.

### 6.2. Tạo business-key constraints

~~~cypher
CREATE CONSTRAINT qa004_user_id IF NOT EXISTS
FOR (u:QA004User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_group_id IF NOT EXISTS
FOR (g:QA004Group)
REQUIRE g.groupId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_role_id IF NOT EXISTS
FOR (r:QA004Role)
REQUIRE r.roleId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa004_resource_id IF NOT EXISTS
FOR (r:QA004Resource)
REQUIRE r.resourceId IS UNIQUE;
~~~

`IS UNIQUE` giúp không tạo hai node cùng business key đối với property **có tồn tại**; nó không tự yêu cầu mọi node đều có ID. Khi cấp quyền trong production, cần kiểm soát cả tính hiện diện/loại dữ liệu của khóa, tùy khả năng constraint của edition và quy trình validation.

### 6.3. Tạo sáu user, hai group, bốn role, sáu resource

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'},
  {id:'U03', name:'Chi'},
  {id:'U04', name:'Dung'},
  {id:'U05', name:'Em'},
  {id:'U06', name:'Giang'}
] AS row
MERGE (u:QA004User {userId:row.id})
SET u.fullName=row.name;
~~~

~~~cypher
UNWIND [
  {id:'G_DEV', title:'Nhom phat trien'},
  {id:'G_AUDIT', title:'Nhom kiem toan'}
] AS row
MERGE (g:QA004Group {groupId:row.id})
SET g.title=row.title;
~~~

~~~cypher
UNWIND ['VIEWER','EDITOR','MANAGER','AUDITOR'] AS id
MERGE (:QA004Role {roleId:id});
~~~

~~~cypher
UNWIND [
  {id:'ROOT', kind:'ORG', title:'To chuc'},
  {id:'PRJ', kind:'FOLDER', title:'Du an A'},
  {id:'DOC1', kind:'DOC', title:'Thiet ke'},
  {id:'DOC2', kind:'DOC', title:'Ke hoach'},
  {id:'FIN', kind:'FOLDER', title:'Tai chinh'},
  {id:'FIN1', kind:'DOC', title:'Bang luong'}
] AS row
MERGE (r:QA004Resource {resourceId:row.id})
SET r.kind=row.kind, r.title=row.title;
~~~

**Đáp án:** tổng **18 node** thuộc bốn label fixture: 6 users + 2 groups + 4 roles + 6 resources.

## 7. Tạo quan hệ kế thừa và cấp/từ chối quyền

### 7.1. Role inheritance: con kế thừa cha

~~~cypher
UNWIND [
  {child:'EDITOR', parent:'VIEWER'},
  {child:'MANAGER', parent:'EDITOR'},
  {child:'AUDITOR', parent:'VIEWER'}
] AS link
MATCH (child:QA004Role {roleId:link.child})
MATCH (parent:QA004Role {roleId:link.parent})
MERGE (child)-[:QA004_INHERITS]->(parent);
~~~

### 7.2. Cấp vai trò trực tiếp cho ba user

~~~cypher
UNWIND [
  {user:'U02', role:'MANAGER'},
  {user:'U04', role:'VIEWER'},
  {user:'U05', role:'EDITOR'}
] AS link
MATCH (u:QA004User {userId:link.user})
MATCH (r:QA004Role {roleId:link.role})
MERGE (u)-[:QA004_ASSIGNED_ROLE]->(r);
~~~

### 7.3. Cấp vai trò thông qua nhóm

~~~cypher
UNWIND [
  {user:'U01', group:'G_DEV'},
  {user:'U03', group:'G_AUDIT'}
] AS link
MATCH (u:QA004User {userId:link.user})
MATCH (g:QA004Group {groupId:link.group})
MERGE (u)-[:QA004_MEMBER_OF]->(g);
~~~

~~~cypher
UNWIND [
  {group:'G_DEV', role:'EDITOR'},
  {group:'G_AUDIT', role:'AUDITOR'}
] AS link
MATCH (g:QA004Group {groupId:link.group})
MATCH (r:QA004Role {roleId:link.role})
MERGE (g)-[:QA004_ASSIGNED_ROLE]->(r);
~~~

### 7.4. Cây tài nguyên: con hướng lên cha

~~~cypher
UNWIND [
  {child:'PRJ', parent:'ROOT'},
  {child:'DOC1', parent:'PRJ'},
  {child:'DOC2', parent:'PRJ'},
  {child:'FIN', parent:'ROOT'},
  {child:'FIN1', parent:'FIN'}
] AS link
MATCH (child:QA004Resource {resourceId:link.child})
MATCH (parent:QA004Resource {resourceId:link.parent})
MERGE (child)-[:QA004_PART_OF]->(parent);
~~~

### 7.5. Bốn grant

~~~cypher
UNWIND [
  {role:'VIEWER', action:'READ', scope:'PRJ'},
  {role:'EDITOR', action:'WRITE', scope:'PRJ'},
  {role:'MANAGER', action:'APPROVE', scope:'PRJ'},
  {role:'AUDITOR', action:'READ', scope:'FIN'}
] AS row
MATCH (role:QA004Role {roleId:row.role})
MATCH (scope:QA004Resource {resourceId:row.scope})
MERGE (role)-[:QA004_GRANTS {action:row.action}]->(scope);
~~~

### 7.6. Hai deny trực tiếp

~~~cypher
MATCH (u:QA004User {userId:'U01'})
MATCH (doc:QA004Resource {resourceId:'DOC2'})
MERGE (u)-[:QA004_DENIES {action:'ALL'}]->(doc);
~~~

~~~cypher
MATCH (u:QA004User {userId:'U05'})
MATCH (doc:QA004Resource {resourceId:'DOC2'})
MERGE (u)-[:QA004_DENIES {action:'WRITE'}]->(doc);
~~~

### 7.7. Đối soát graph trước khi kiểm tra quyền

~~~cypher
MATCH (n)
WHERE n:QA004User OR n:QA004Group
   OR n:QA004Role OR n:QA004Resource
RETURN count(n) AS fixtureNodes;
~~~

**Đáp án:** `fixtureNodes=18`.

~~~cypher
MATCH ()-[r]->()
WHERE type(r) STARTS WITH 'QA004_'
RETURN type(r) AS relType, count(r) AS amount
ORDER BY relType;
~~~

| relType | amount |
|---|---:|
| QA004_ASSIGNED_ROLE | **5** |
| QA004_DENIES | **2** |
| QA004_GRANTS | **4** |
| QA004_INHERITS | **3** |
| QA004_MEMBER_OF | **2** |
| QA004_PART_OF | **5** |

Tổng **21 relationship**. Nếu sai, phải kiểm tra fixture và quan hệ trước khi diễn giải kết quả security. Trong đó `ASSIGNED_ROLE=5` gồm ba cạnh từ user và hai cạnh từ group.

## 8. Bước 1: lấy vai trò trực tiếp và qua nhóm

Đầu tiên cần phân biệt **vai trò được gán** với **vai trò kế thừa**.

~~~cypher
MATCH (u:QA004User {userId:$userId})
OPTIONAL MATCH (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
WITH u, collect(DISTINCT direct) AS directRoles
OPTIONAL MATCH (u)-[:QA004_MEMBER_OF]->
               (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
               (groupRole:QA004Role)
WITH directRoles + collect(DISTINCT groupRole) AS allRoles
UNWIND allRoles AS role
RETURN DISTINCT role.roleId AS assignedRole
ORDER BY assignedRole;
~~~

Chạy với `$userId='U01'`: **EDITOR**. Với U02: **MANAGER**. Với U03: **AUDITOR**. Với U06: **0 dòng**, vì không có role được gán.

**Chú ý:** một quyền có thể đến từ nhiều nhóm; dùng `DISTINCT` để tránh hiển thị trùng. Nhưng số **đường dẫn** vẫn có ích cho audit: một role được gán bởi hai nhóm là hai nguồn cấp quyền cần biết khi thu hồi.

### 8.1. Vì sao không ghép role name bằng chuỗi?

Không nên lưu tên các role thành chuỗi CSV trong property của user rồi dùng `CONTAINS` để suy quyền. Cách đó khó duy trì thứ bậc, thu hồi qua group và giải thích đường cấp quyền. Các quan hệ có hướng cho phép Cypher đi từ chủ thể đến các nguồn quyền một cách tường minh.

## 9. Bước 2: tính closure của vai trò kế thừa

Với role MANAGER, cần duyệt **0 hoặc nhiều cạnh** `INHERITS` để lấy chính nó và toàn bộ vai trò tổ tiên:

~~~cypher
MATCH (u:QA004User {userId:'U02'})
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH path=(seed)-[:QA004_INHERITS*0..5]->
           (effective:QA004Role)
RETURN DISTINCT effective.roleId AS effectiveRole
ORDER BY effectiveRole;
~~~

**Đáp án U02:** EDITOR, MANAGER, VIEWER.

`*0..5` có hai ý nghĩa:

- `0` cạnh: role tự nó có hiệu lực. Nếu bỏ 0, MANAGER sẽ **không nhận grant được gán trực tiếp trên MANAGER**.
- Tối đa `5` cạnh: giới hạn độ sâu mẫu test; production phải kiểm soát chiều sâu hợp lệ, không dùng số 5 như một giả định âm thầm.

Với U03 qua nhóm G_AUDIT:

~~~cypher
MATCH (u:QA004User {userId:'U03'})
      -[:QA004_MEMBER_OF]->(:QA004Group)
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH (seed)-[:QA004_INHERITS*0..5]->
      (effective:QA004Role)
RETURN DISTINCT effective.roleId AS effectiveRole
ORDER BY effectiveRole;
~~~

**Đáp án U03:** AUDITOR, VIEWER. U03 đọc được tài liệu dự án thông qua VIEWER và tài liệu tài chính thông qua AUDITOR, nhưng không có WRITE vì không kế thừa EDITOR.

## 10. Bước 3: tìm phạm vi tài nguyên được thừa hưởng

Grant trên PRJ có hiệu lực cho cả DOC1 và DOC2 vì cả hai nằm dưới PRJ. Với DOC1:

~~~cypher
MATCH path=(doc:QA004Resource {resourceId:'DOC1'})
           -[:QA004_PART_OF*0..5]->
           (scope:QA004Resource)
RETURN scope.resourceId AS scopeId,
       length(path) AS stepsToScope
ORDER BY stepsToScope;
~~~

| scopeId | stepsToScope |
|---|---:|
| DOC1 | 0 |
| PRJ | 1 |
| ROOT | 2 |

Với FIN1, kết quả tương ứng là **FIN1, FIN, ROOT**. Grant WRITE trên PRJ **không thể** áp dụng cho FIN1 vì không có đường `FIN1 → ... → PRJ`.

### 10.1. Chiều truyền quyền không thể đảo tùy ý

Có cạnh `(DOC1)-[:PART_OF]->(PRJ)` nên grant trên **PRJ** truyền xuống **DOC1**. Không thể suy từ grant trên DOC1 rằng chủ thể có quyền với PRJ hoặc mọi tài liệu cùng thư mục.

Câu truy vấn sai chiều có thể âm thầm mở rộng quyền ngoài ý muốn; test cần bao gồm cả **positive** và **negative** path.

## 11. Câu Cypher quyết định quyền đầy đủ

Đây là truy vấn trọng tâm, kết hợp role trực tiếp/qua nhóm, role inheritance, phạm vi tài nguyên và deny override. Truyền tham số `$userId`, `$resourceId`, `$action` từ tầng server đáng tin cậy.

~~~cypher
MATCH (u:QA004User {userId:$userId})
MATCH (target:QA004Resource {resourceId:$resourceId})

OPTIONAL MATCH
  (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
WITH u, target, collect(DISTINCT direct) AS directRoles

OPTIONAL MATCH
  (u)-[:QA004_MEMBER_OF]->
  (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
  (viaGroup:QA004Role)
WITH u, target,
     directRoles + collect(DISTINCT viaGroup) AS seeds

WITH u, target,
     any(seed IN seeds WHERE EXISTS {
       MATCH (seed)-[:QA004_INHERITS*0..5]->
             (effective:QA004Role)
       MATCH (effective)-[grant:QA004_GRANTS]->
             (scope:QA004Resource)
       MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
       WHERE grant.action = $action
     }) AS hasGrant,
     EXISTS {
       MATCH (u)-[deny:QA004_DENIES]->
             (scope:QA004Resource)
       MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
       WHERE deny.action IN [$action, 'ALL']
     } AS hasDeny

RETURN u.userId AS userId,
       target.resourceId AS resourceId,
       $action AS action,
       hasGrant,
       hasDeny,
       hasGrant AND NOT hasDeny AS allowed;
~~~

**Ví dụ tham số:**

~~~json
{"userId":"U01","resourceId":"DOC1","action":"READ"}
~~~

Kết quả logic mong đợi:

| userId | resourceId | action | hasGrant | hasDeny | allowed |
|---|---|---|---|---|---|
| U01 | DOC1 | READ | true | false | **true** |

Với U01/DOC2/READ: `hasGrant=true`, `hasDeny=true`, `allowed=false`. Với U06/DOC1/READ: `hasGrant=false`, `hasDeny=false`, `allowed=false`.

### 11.1. Vì sao truy vấn dùng EXISTS?

- `EXISTS { MATCH ... }` trả **đúng/sai** mà không phải dựng toàn bộ danh sách các đường cấp quyền.
- `any(seed IN seeds ...)` kiểm tra có **ít nhất một** role được gán tạo grant hợp lệ.
- `collect(DISTINCT ...)` giới hạn nhân bản role khi một người thuộc nhiều nhóm.
- Từ chối được kiểm tra **độc lập** với grant, rồi áp dụng ưu tiên bằng phép logic cuối cùng.
- Người không có role sẽ có danh sách seeds rỗng và `hasGrant=false`; không được xem việc thiếu role như một lỗi dẫn tới cấp quyền.

### 11.2. Khi user hoặc resource không tồn tại

Hai câu `MATCH` đầu có thể trả **0 record** nếu `userId` hoặc `resourceId` không tồn tại. **Ứng dụng phải coi 0 record là DENY**, không được mặc định true và không được gán quyền “guest” tự phát.

Trong API bên ngoài, cân nhắc trả lỗi không tiết lộ tài nguyên có tồn tại hay không (403/404 theo threat model) để tránh **resource enumeration**. Thông điệp audit nội bộ có thể ghi lý do chi tiết, nhưng response công khai phải theo chính sách tiết lộ thông tin.

### 11.3. Các giới hạn đã chủ động đặt trong bài

- Role inheritance và resource ancestry tối đa 5 cạnh.
- Membership chỉ 1 cấp, không duyệt nested groups.
- Deny được gán trực tiếp cho user, không xử lý deny của role/group.
- Không có conditional permissions theo thời gian, IP, thiết bị hoặc phân loại tài liệu.
- Cypher chỉ kiểm tra mô hình policy. Neo4j DBMS RBAC và đường gọi API có thể áp điều kiện độc lập.

Đây là các giới hạn **cần ghi trong thiết kế và test**, không phải lỗ hổng được phép bỏ qua.

## 12. Kiểm chứng grant/deny theo từng tình huống

| Yêu cầu | Lý do cấp quyền | Có deny? | Quyết định |
|---|---|---|---|
| U01 READ DOC1 | U01 → G_DEV → EDITOR → VIEWER → READ PRJ; DOC1 ∈ PRJ | Không | **ALLOW** |
| U01 WRITE DOC1 | EDITOR → WRITE PRJ | Không | **ALLOW** |
| U01 READ DOC2 | VIEWER → READ PRJ | **ALL trên DOC2** | **DENY** |
| U01 WRITE DOC2 | EDITOR → WRITE PRJ | **ALL trên DOC2** | **DENY** |
| U02 APPROVE DOC1 | MANAGER → APPROVE PRJ | Không | **ALLOW** |
| U03 READ FIN1 | G_AUDIT → AUDITOR → READ FIN; FIN1 ∈ FIN | Không | **ALLOW** |
| U03 WRITE DOC1 | Không có grant WRITE | Không | **DENY** |
| U05 READ DOC2 | EDITOR → VIEWER → READ PRJ | Deny chỉ áp WRITE | **ALLOW** |
| U05 WRITE DOC2 | EDITOR → WRITE PRJ | **WRITE trên DOC2** | **DENY** |
| U06 READ DOC1 | Không có role | Không | **DENY** |

Để tránh nhập nhằng giữa “tài nguyên tồn tại” và “tài nguyên được phép truy cập”, mỗi ca ở bảng phải được chạy bằng **người dùng và resource có thật**; thêm negative test riêng cho ID không tồn tại.

### 12.1. Thử deny ở scope cha

Nếu user có deny `ALL` trên PRJ, deny ấy cũng áp dụng cho DOC1/DOC2. Không phải vì relationship `DENIES` tự lan truyền; mà vì truy vấn kiểm tra xem **target có đường PART_OF lên scope deny**.

**Không chạy thử thay đổi deny trong fixture đang được test đồng thời** nếu muốn giữ ma trận `5.3` nguyên vẹn. Nếu muốn thử, dùng transaction test và rollback/restore fixture trước ca kế tiếp.

## 13. Truy vết “vì sao được cấp quyền?”

Một hệ thống audit thường cần biết **đường dẫn cấp quyền**, không chỉ true/false. Với U01 → DOC1 → READ:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[:QA004_MEMBER_OF]->(g:QA004Group)
      -[:QA004_ASSIGNED_ROLE]->(seed:QA004Role)
MATCH rolePath=(seed)-[:QA004_INHERITS*0..5]->
               (role:QA004Role)
MATCH (role)-[grant:QA004_GRANTS {action:'READ'}]->
      (scope:QA004Resource)
MATCH resourcePath=
      (target:QA004Resource {resourceId:'DOC1'})
      -[:QA004_PART_OF*0..5]->(scope)
RETURN g.groupId AS sourceGroup,
       [r IN nodes(rolePath) | r.roleId] AS rolePath,
       [r IN nodes(resourcePath) | r.resourceId] AS scopePath,
       grant.action AS action;
~~~

**Đáp án:**

| sourceGroup | rolePath | scopePath | action |
|---|---|---|---|
| G_DEV | [EDITOR, VIEWER] | [DOC1, PRJ] | READ |

Đường đi này là **bằng chứng về grant**, **chưa phải quyết định cuối cùng**. Một deny của user có thể phủ định grant đó; muốn giải thích từ chối, phải kiểm tra `QA004_DENIES` riêng.

Ví dụ truy vấn tìm đường deny:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[deny:QA004_DENIES]->
      (scope:QA004Resource)
MATCH path=(target:QA004Resource {resourceId:'DOC2'})
           -[:QA004_PART_OF*0..5]->(scope)
WHERE deny.action IN ['READ','ALL']
RETURN deny.action AS blockedAction,
       scope.resourceId AS denyScope,
       [r IN nodes(path) | r.resourceId] AS scopePath;
~~~

**Đáp án:** `blockedAction='ALL'`, `denyScope='DOC2'`, `scopePath=['DOC2']`.

Đối với hệ thống thật, chỉ cung cấp giải thích chi tiết cho admin/auditor có thẩm quyền; không trả toàn bộ tên group, role, graph structure và policy của tổ chức cho người dùng đang bị từ chối.

## 14. Java Driver: kiểm tra quyền trước khi sửa tài liệu

Neo4j Java Driver cho phép chạy Cypher tham số hóa trong một transaction. Một service ví dụ có thể dùng truy vấn ở mục 11 làm hằng `AuthQueries.POLICY_CYPHER`:

~~~java
public final class AuthQueries {
    private AuthQueries() {}

    // Nội dung là nguyên văn câu Cypher ở mục 11, không ghép input.
    public static final String POLICY_CYPHER = """
        MATCH (u:QA004User {userId:$userId})
        MATCH (target:QA004Resource {resourceId:$resourceId})
        OPTIONAL MATCH
          (u)-[:QA004_ASSIGNED_ROLE]->(direct:QA004Role)
        WITH u, target, collect(DISTINCT direct) AS directRoles
        OPTIONAL MATCH
          (u)-[:QA004_MEMBER_OF]->
          (:QA004Group)-[:QA004_ASSIGNED_ROLE]->
          (viaGroup:QA004Role)
        WITH u, target,
             directRoles + collect(DISTINCT viaGroup) AS seeds
        WITH u, target,
             any(seed IN seeds WHERE EXISTS {
               MATCH (seed)-[:QA004_INHERITS*0..5]->
                     (role:QA004Role)
               MATCH (role)-[g:QA004_GRANTS]->
                     (scope:QA004Resource)
               MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
               WHERE g.action=$action
             }) AS granted,
             EXISTS {
               MATCH (u)-[d:QA004_DENIES]->
                     (scope:QA004Resource)
               MATCH (target)-[:QA004_PART_OF*0..5]->(scope)
               WHERE d.action IN [$action,'ALL']
             } AS denied
        RETURN granted AND NOT denied AS allowed
        """;
}
~~~

**Lưu ý:** Hằng ở đây trả duy nhất cột `allowed`; câu `RETURN` ở mục 11 trả thêm lý do `hasGrant` và `hasDeny`. Hai câu **tương đương về quyết định**, không phải hoàn toàn giống danh sách cột. Nếu thay đổi policy, phải cập nhật một implementation duy nhất trong mã thật và có test bảo vệ tránh drift giữa các bản.

### 14.1. Hàm kiểm tra quyền read-only

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class GraphAuthorization {
    private GraphAuthorization() {}

    public static boolean can(
            Driver driver, String database,
            String authenticatedUserId,
            String resourceId, String action) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> {
                var result = tx.run(
                    AuthQueries.POLICY_CYPHER,
                    Values.parameters(
                        "userId", authenticatedUserId,
                        "resourceId", resourceId,
                        "action", action
                    )
                );

                // 0 record khi user/resource không tồn tại => deny.
                return result.hasNext()
                    && result.single().get("allowed").asBoolean();
            });
        }
    }
}
~~~

Trước khi gọi, **kiểm tra action trong một enum/allowlist** (READ, WRITE, APPROVE) và lấy `authenticatedUserId` từ token/session đã xác thực bởi backend, **không** đọc từ JSON body kiểu `{"userId":"U02"}` do người dùng tự nhập.

### 14.2. Gộp kiểm tra và sửa trong một transaction

Để tránh kiểu code:

~~~text
HTTP A: canWrite(...) => true
HTTP B: revokePermission(...)
HTTP A: editDocument(...) trong transaction riêng
~~~

nên đưa việc kiểm tra quyền và cập nhật document vào **cùng transaction ghi** khi nghiệp vụ yêu cầu:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class DocumentWriter {
    public static void rename(
            Driver driver, String database,
            String authenticatedUserId,
            String resourceId, String newTitle) {

        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {

            session.executeWrite(tx -> {
                var decision = tx.run(
                    AuthQueries.POLICY_CYPHER,
                    Values.parameters(
                        "userId", authenticatedUserId,
                        "resourceId", resourceId,
                        "action", "WRITE"
                    )
                );
                if (!decision.hasNext() ||
                    !decision.single().get("allowed").asBoolean()) {
                    throw new SecurityException("Access denied");
                }

                long updated = tx.run("""
                    MATCH (doc:QA004Resource {
                      resourceId:$id, kind:'DOC'
                    })
                    SET doc.title=$title
                    RETURN count(doc) AS modified
                    """, Values.parameters(
                        "id", resourceId,
                        "title", newTitle
                    ))
                    .single().get("modified").asLong();

                if (updated != 1L) {
                    throw new IllegalArgumentException(
                        "Document not found"
                    );
                }
                return null;
            });
        }
    }
}
~~~

**Điểm đúng:** kiểm tra và sửa nằm trong cùng transaction; nếu bị từ chối thì transaction không commit cập nhật. Callback `executeWrite` có thể được retry khi lỗi transient; vì thế không gửi email, trừ tiền hoặc phát sự kiện không idempotent trong callback.

**Giới hạn quan trọng:** cùng transaction **không tự giải quyết hoàn toàn việc thu hồi quyền đồng thời**. Một transaction kiểm tra quyền trước khi thay đổi policy ở transaction khác commit có thể vẫn cần cơ chế version/locking hoặc serialization policy theo threat model. Với nghiệp vụ nhạy cảm, xác định điểm thời gian quyết định quyền, khóa/version policy và consistency khi revoke.

## 15. Spring Data Neo4j: repository không tự áp quyền tổ chức

Entity SDN chỉ biểu diễn node và relationship; nó **không tự hiểu** các quy tắc `P1–P10`. Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("QA004Resource")
public class ProtectedResource {
    @Id
    private String resourceId;
    private String title;
    private String kind;

    protected ProtectedResource() {}

    public String getResourceId() { return resourceId; }
    public String getTitle() { return title; }
    public String getKind() { return kind; }
}
~~~

Một `Neo4jRepository<ProtectedResource,String>` vẫn có thể đọc object theo ID nếu backend gọi phương thức đó với database credentials đủ quyền. **Chỉ có @Node/@Relationship hay @PreAuthorize("isAuthenticated()") không có nghĩa đã kiểm tra quyền trên từng document.**

### 15.1. Ví dụ service sử dụng Neo4jClient

Có thể chạy cùng policy Cypher bằng `Neo4jClient` và dùng Spring transaction cho cả quyết định và sửa tài liệu:

~~~java
import java.util.Map;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SdnDocumentService {
    private final Neo4jClient client;

    public SdnDocumentService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void rename(String authenticatedUserId,
                       String resourceId, String title) {

        boolean allowed = client.query(
                AuthQueries.POLICY_CYPHER)
            .bindAll(Map.of(
                "userId", authenticatedUserId,
                "resourceId", resourceId,
                "action", "WRITE"
            ))
            .fetchAs(Boolean.class)
            .mappedBy((ts, record) ->
                record.get("allowed").asBoolean())
            .one()
            .orElse(false);

        if (!allowed) {
            throw new SecurityException("Access denied");
        }

        long modified = client.query("""
                MATCH (d:QA004Resource {
                  resourceId:$resourceId, kind:'DOC'
                })
                SET d.title=$title
                RETURN count(d) AS modified
                """)
            .bind(resourceId).to("resourceId")
            .bind(title).to("title")
            .fetchAs(Long.class)
            .mappedBy((ts, record) ->
                record.get("modified").asLong())
            .one()
            .orElse(0L);

        if (modified != 1L) {
            throw new IllegalArgumentException(
                "Document not found"
            );
        }
    }
}
~~~

`@Transactional` phải do đúng `Neo4jTransactionManager`/SDN configuration điều phối. Tránh xen `driver.session().executeWrite(...)` riêng vào giữa một Spring transaction rồi giả định hai thao tác cùng rollback. Tương tự, không gọi `repository.save(...)` trên entity được hydrate thiếu relationship mà chưa kiểm chứng tác dụng của việc lưu graph.

**Yêu cầu vận hành:** những code path đọc/xuất/tải file, tìm kiếm toàn văn, background jobs và endpoints admin cũng phải đi qua policy hoặc cơ chế kiểm soát phù hợp. Bảo vệ mỗi endpoint `rename` nhưng để `findAll()` trả toàn bộ graph là một lỗ hổng phân quyền.

## 16. Vai trò của quyền Neo4j DBMS và quyền ứng dụng

Có **hai tầng an ninh khác nhau**:

| Tầng | Quyết định | Ví dụ |
|---|---|---|
| **Neo4j DBMS RBAC** | Tài khoản kết nối Bolt có thể truy cập database, label, property hoặc chạy procedure nào | App service account được `MATCH`/`WRITE` theo quyền được cấp |
| **Graph authorization của ứng dụng** | Nhân viên U01 có được xem/sửa DOC1 theo vai trò tổ chức không | U01 qua G_DEV → EDITOR, deny theo DOC2 |

Nếu một backend dùng **một Neo4j service account** cho nhiều người dùng, Neo4j có thể nhìn thấy cùng một database principal; database không tự biết ai là U01 hay U02 nếu ứng dụng không truyền danh tính đã xác thực và thực thi policy.

**Kiến trúc cần phòng thủ nhiều lớp:**

- Neo4j service account có **quyền tối thiểu** để thực hiện đúng query nghiệp vụ.
- Không cho người dùng cuối truy cập Bolt bằng credential của backend.
- Không cung cấp endpoint “chạy Cypher tùy ý” dưới cùng service account.
- Chỉ service/quy trình được ủy quyền mới được sửa graph roles/groups/grants/denies.
- Những quy tắc truy cập tài nguyên phải được thực thi ở **mọi đường đọc/ghi** liên quan.
- Chính sách Neo4j `GRANT`/`DENY` cho database cần được cấu hình độc lập theo phiên bản/edition; **không nhầm** với cạnh `QA004_DENIES`.

Đừng tuyên bố “có graph RBAC” là đủ nếu ứng dụng có một đường truy vấn bỏ qua `hasDeny` hoặc trust ID do caller tự điền.

## 17. Đường kế thừa có vòng: phát hiện và ngăn từ nguồn

Vòng trong `INHERITS` là lỗi quản trị. Ví dụ:

~~~text
MANAGER → EDITOR → VIEWER → MANAGER
~~~

Một chu trình như vậy có thể khiến vai trò VIEWER nhận quyền MANAGER theo chiều ngược qua vòng, gây **leo thang đặc quyền**. Với resource tree, vòng `PART_OF` khiến các thư mục trở thành ancestor của nhau và cấp quyền lan sai.

### 17.1. Query kiểm tra chu trình trong fixture

~~~cypher
MATCH path=(r:QA004Role)
           -[:QA004_INHERITS*1..5]->(r)
RETURN r.roleId AS cycleStart,
       [n IN nodes(path) | n.roleId] AS roleCycle
LIMIT 20;
~~~

~~~cypher
MATCH path=(r:QA004Resource)
           -[:QA004_PART_OF*1..5]->(r)
RETURN r.resourceId AS cycleStart,
       [n IN nodes(path) | n.resourceId] AS scopeCycle
LIMIT 20;
~~~

**Đáp án fixture:** cả hai truy vấn trả **0 record**. Nếu phát hiện vòng ở production, phải xử lý cấu trúc quyền, không chỉ tăng `LIMIT` hoặc giới hạn traversal để che lỗi.

### 17.2. Ngăn khi tạo cạnh mới

Khi định tạo cạnh `child-[:INHERITS]->parent`, trước hết xác định **parent đã có đường trở về child hay chưa**. Nếu có, cạnh mới tạo chu trình. Bài toán tương tự với `PART_OF`.

Trong môi trường có nhiều admin cập nhật đồng thời, kiểm tra đường rồi ghi cạnh ở hai transaction riêng có thể xảy ra **race condition**. Phải dùng giao dịch có cơ chế đồng bộ/khóa phù hợp, kiểm tra invariant sau ghi và audit thay đổi; không chỉ tin vào một `WHERE NOT EXISTS` chạy riêng lẻ.

**Quy tắc khác phải kiểm tra:** tài nguyên không thuộc hai tenant ngoài chính sách, group không được cấp vai trò quá quyền, mọi node có ID duy nhất và các đường inheritance không vượt quá giới hạn query đã công bố.

## 18. Thu hồi quyền: cấp nhanh nhưng thu hồi phải chắc

Hai trường hợp có ý nghĩa khác nhau:

1. **Thu hồi membership:** xóa `(u)-[:MEMBER_OF]->(g)` khiến mọi role từ group đó không còn hiệu lực với user, trừ khi user nhận cùng quyền qua đường khác.
2. **Thêm DENY:** chặn một action/resource ngay cả khi có nhiều đường cấp quyền khác; thường phù hợp ngoại lệ có tính khẩn cấp, nhưng vẫn cần cơ chế kiểm toán và bảo trì ngoại lệ.

Ví dụ thử nghiệm trên **transaction/fixture tách biệt**:

~~~cypher
MATCH (u:QA004User {userId:'U01'})
      -[m:QA004_MEMBER_OF]->
      (g:QA004Group {groupId:'G_DEV'})
DELETE m;
~~~

Sau khi xóa membership, U01 không còn role từ G_DEV, nên DOC1 READ và WRITE trở thành **DENY theo default deny**, dù cạnh deny DOC2 vẫn tồn tại.

**Lưu ý:** Truy vấn trên làm thay đổi fixture. Nếu dùng cho một ca test, cần rollback hoặc seed lại trước khi kiểm tra ma trận `5.3`.

### 18.1. Stale cache và thời gian hiệu lực thu hồi

Nếu API cache `canRead(U01,DOC1)=true` trong 10 phút, việc thu hồi group ở Neo4j **không bảo đảm** cache lập tức hết hạn. Với yêu cầu revoke gần như tức thì, phải xác định policy version, event invalidation, TTL rất ngắn hoặc kiểm tra realtime trên đường truy cập nhạy cảm.

Các điểm cần tính đến:

- Cache key gồm **user, action, resource và policy/tenant version**; không chỉ resource ID.
- Cập nhật membership, role inheritance, grant, deny hoặc resource parent có thể làm nhiều quyết định trước đó không còn đúng.
- Có request đang chạy và background job có policy snapshot cũ.
- Trong cluster, consistency/read-after-write phải được quan sát khi thao tác policy và request phân quyền xảy ra sát nhau.
- Không bỏ qua denial chỉ vì cache không tìm được câu trả lời; **fail closed** theo yêu cầu bảo mật.

## 19. Multi-tenant: không để đường graph vượt ranh giới khách hàng

Fixture có một tổ chức ROOT nên chưa có tenant isolation. Trong SaaS nhiều tenant, các node có thể thuộc các công ty khác nhau. Nếu hai tenant có cùng tên role `EDITOR` hoặc resource `DOC1`, tra cứu bằng ID không có tenant scope có nguy cơ áp nhầm quyền.

Một mô hình cần bổ sung:

~~~text
User, Group, Role, Resource đều có tenantId
Unique business key: (tenantId, localId)
Edges MEMBER_OF / ASSIGNED_ROLE / INHERITS / PART_OF
chỉ nối trong đúng tenant được ủy quyền.
~~~

### 19.1. Ví dụ truy vấn định danh theo tenant

~~~cypher
MATCH (u:User {
  tenantId:$tenantId,
  userId:$authenticatedUserId
})
MATCH (r:Resource {
  tenantId:$tenantId,
  resourceId:$resourceId
})
RETURN u.userId AS userId,
       r.resourceId AS resourceId;
~~~

Đoạn này chỉ minh họa điều kiện **khởi đầu**; label `User/Resource` khác fixture `QA004` và **chưa đủ** để thực thi policy. Trong câu authorization thực phải kiểm tra **mọi role, group, grant, deny, ancestor** đều thuộc đúng tenant; không chỉ kiểm tra hai node đầu.

**Cần test negative:** nếu user ở tenant A đưa resourceId của tenant B, kết quả phải là DENY, kể cả khi role name trùng và đồ thị có cạnh liên tenant do dữ liệu lỗi.

### 19.2. Quy tắc hành động tùy ngữ cảnh

Một công ty có thể yêu cầu `APPROVE` chỉ khi người duyệt khác người soạn, document đang ở trạng thái `PENDING` và thời gian trong ca làm. Đó là **ABAC và separation of duties**, không tự được bảo vệ bởi role MANAGER.

Hãy đưa predicate nghiệp vụ vào quyết định và transaction ghi, cùng test các trạng thái. Đừng chỉ kiểm tra `hasRole('MANAGER')` rồi cho phép mọi approval.

## 20. Truy vấn danh sách tài nguyên mà user được xem

Kiểm tra một resource bằng `EXISTS` tương đối trực tiếp; một màn hình “Tất cả tài liệu tôi được xem” khó hơn vì phải xác định tập ứng viên, lọc deny và phân trang.

**Anti-pattern:** lấy tất cả DOC rồi gọi `can(...)` bằng Java cho từng item:

~~~java
// Ví dụ chống mẫu: dễ tạo N+1 round trips.
for (String resourceId : allDocumentIds) {
    if (GraphAuthorization.can(
            driver, db, userId, resourceId, "READ")) {
        visible.add(resourceId);
    }
}
~~~

Giả sử có 10.000 tài liệu, cách này có thể tạo 10.000 lượt query phụ. Ngoài ra, lấy toàn bộ tài liệu trước rồi mới kiểm tra quyền ở ứng dụng làm tăng rủi ro **over-fetch**.

### 20.1. Phương án truy vấn theo batch

Một quy trình dễ kiểm soát:

1. Lấy danh sách ID tài liệu ứng viên theo filter/sort/phân trang có ý nghĩa nghiệp vụ.
2. Với một lô ID nhỏ, chạy **một Cypher** đánh giá quyền cho từng ID (có thể dùng `UNWIND $ids`, subquery và policy giống mục 11).
3. Chỉ trả về những item `allowed=true`; giữ thứ tự trang và tổng count theo đúng semantics.
4. Nếu cần đủ `pageSize` **tài liệu được phép**, không được đơn giản LIMIT 20 tài liệu **trước** khi lọc quyền rồi coi là “đã phân trang 20 tài liệu nhìn thấy”. Có thể cần query cho toàn bộ tập đã được phép hoặc cơ chế cursor batched có kiểm soát.
5. Giới hạn tối đa tài liệu được xét mỗi lượt và đo `Rows`, `DB Hits`, response bytes.

Một hệ thống lớn có thể dùng **materialized access view**, bitmap/cache có policy version hoặc kiến trúc search được đồng bộ với ACL, nhưng phải có cơ chế thu hồi nhanh và đối soát để không tiết lộ tài liệu đã bị deny.

### 20.2. Tính đúng trước tốc độ

Tối ưu một query quyền để chạy 2 ms nhưng trả **ALLOW sai** là lỗi bảo mật, không phải cải thiện hiệu năng. Trước khi cache hoặc tiền tính closure, phải có regression test cho deny precedence, role/group thay đổi và tenant isolation.

## 21. Tối ưu Cypher và schema khi graph quyền lớn

### 21.1. Dùng ID và index thay vì quét theo tên

Các constraint trên `userId`, `groupId`, `roleId`, `resourceId` hỗ trợ tra cứu điểm đầu bằng index. Trong production, nên định danh theo business key đã chuẩn hóa, không dùng tên hiển thị vì tên có thể trùng/đổi.

~~~cypher
EXPLAIN
MATCH (u:QA004User {userId:'U01'})
RETURN u.userId AS id;
~~~

Kiểm tra planner có dùng index/constraint tương ứng không. Không suy từ “có constraint” rằng mọi truy vấn quyền đều tối ưu; thời gian chủ yếu có thể nằm ở mở rộng các cạnh tiếp theo.

### 21.2. Giới hạn fan-out và chiều sâu theo chính sách

Một user thuộc hàng trăm nhóm, mỗi nhóm có hàng trăm role, mỗi role kế thừa sâu và mỗi resource có nhiều ancestor có thể sinh nhiều đường trùng. Để giới hạn:

- Xác định role hierarchy là **DAG**, có chiều sâu tối đa rõ ràng.
- Resource scope là tree hoặc DAG được kiểm soát, không tạo vòng.
- Dùng `EXISTS` khi chỉ cần boolean; chỉ liệt kê paths cho audit có giới hạn.
- Dùng `DISTINCT` khi số đường trùng không mang nghĩa bổ sung.
- Giám sát các node nhóm/role/resource có degree bất thường.
- Cân nhắc tách query quyền từng resource và query danh sách, vì chúng có yêu cầu plan khác nhau.

### 21.3. Đo plan nhưng đừng suy từ DB Hits thành I/O thật

~~~cypher
PROFILE
MATCH (u:QA004User {userId:'U01'})
OPTIONAL MATCH (u)-[:QA004_MEMBER_OF]->
               (g:QA004Group)
RETURN u.userId AS id, collect(g.groupId) AS groups;
~~~

Xem `Rows`, `DB Hits` và khi có, `Page Cache Hits/Misses`. Fixture 18 node chỉ dùng để kiểm chứng đúng/sai; muốn quyết định index, memory và cache trên hệ lớn phải benchmark với dữ liệu quyền đại diện.

**Không** mở rộng mọi đường `*0..` không giới hạn trên graph chưa kiểm soát; điều này có thể gây bùng nổ path hoặc query DoS.

## 22. Kiểm thử bảo mật: test quyền phải có cả ca bị từ chối

### 22.1. Ma trận test tích hợp

| Ca | Input | Kết quả cần assert |
|---|---|---|
| Role qua group | U01 READ DOC1 | ALLOW |
| Role inheritance | U02 APPROVE DOC1 | ALLOW |
| Scope inheritance | U05 WRITE DOC1 | ALLOW |
| Deny ALL thắng grant | U01 READ DOC2 | DENY |
| Deny action cụ thể | U05 WRITE DOC2 | DENY |
| Deny không chặn action khác | U05 READ DOC2 | ALLOW |
| Vai trò không mang quyền khác | U03 WRITE DOC1 | DENY |
| Phạm vi tài nguyên tách biệt | U04 READ FIN1 | DENY |
| Auditor đọc finance | U03 READ FIN1 | ALLOW |
| No roles | U06 READ DOC1 | DENY |
| User không tồn tại | U99 READ DOC1 | DENY (0 record từ query) |
| Resource không tồn tại | U01 READ DOC99 | DENY (0 record) |
| Không nâng quyền ngược | U04 APPROVE DOC1 | DENY |
| Thu hồi membership | U01 sau khi rời G_DEV | Không còn READ DOC1 từ nhóm |
| Vòng role/resource | Thử thêm cycle trong transaction test | Giao dịch quản trị phải chặn |
| Cross-tenant | User tenant A xin resource tenant B | DENY |
| Ghi tài liệu khi deny | U01 WRITE DOC2 | Không sửa title, transaction rollback |
| Cache sau revoke | Xóa group grant rồi gọi lại | Không tiếp tục ALLOW từ cache stale |

Một unit test chỉ mock `AuthorizationRepository.can(...)` trả true/false **không đủ** để kiểm chứng Cypher thực sự duyệt đúng đường quan hệ. Cần integration test với Neo4j test instance, fixture độc lập và so sánh kết quả theo ma trận `5.3`.

### 22.2. Mẫu JUnit kiểm tra bảng expected

Giả sử test đã seed fixture ở mục 6–7 bằng một Neo4j test instance, và `GraphAuthorization.can(...)` là phương thức ở mục 14:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class AuthorizationContractTest {

    // driver, database được fixture/test container cung cấp.

    @Test
    void inheritedGrantAndExplicitDeny() {
        assertTrue(GraphAuthorization.can(
            driver, database, "U01", "DOC1", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U01", "DOC2", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U05", "DOC2", "WRITE"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U05", "DOC2", "READ"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U02", "DOC1", "APPROVE"
        ));
        assertTrue(GraphAuthorization.can(
            driver, database, "U03", "FIN1", "READ"
        ));
        assertFalse(GraphAuthorization.can(
            driver, database, "U06", "DOC1", "READ"
        ));
    }
}
~~~

Đây là **đoạn test minh họa**; nó không tự khai báo `driver`, `database`, `@BeforeEach` hay container. Trong bộ test thực cần thêm setup/teardown, cấu hình phiên bản Neo4j và isolation. Không chạy test trên database production.

### 22.3. Test “không đọc lộ dữ liệu”

Đừng chỉ test endpoint cập nhật. Test cả:

- Danh sách tài liệu và số tổng phần tử không lộ thông tin của resource bị deny.
- Tìm kiếm theo title, pagination và download không lộ metadata/file của tài liệu không có quyền.
- Query qua relationship từ một tài liệu được đọc tới tài liệu bị deny không tự trả đầy đủ node đích.
- Trace/log/error message không chứa tên nhóm bí mật, private roles hoặc nội dung tài liệu nhạy cảm.
- API caller không thể tự thay `authenticatedUserId` để giả danh MANAGER.

Kiểm soát tính đúng của security policy **ở đầu ra cuối cùng**, không chỉ tại một method riêng lẻ.

## 23. Audit và giải thích quyết định quyền

Một bản ghi audit nội bộ nên lưu các trường tối thiểu:

| Trường | Tác dụng |
|---|---|
| Thời điểm, requestId, correlationId | Truy hồi chuỗi sự kiện |
| Chủ thể đã xác thực | Ai yêu cầu, nguồn xác thực nào |
| Action và resource ID | Đã xin làm gì trên đối tượng nào |
| Kết quả ALLOW/DENY | Quyết định cuối cùng, không chỉ grant |
| Policy version | Quyết định theo chính sách nào |
| Lý do nội bộ | No grant, explicit deny, invalid user/resource, tenant mismatch |
| Thời gian thực thi | Theo dõi độ trễ kiểm tra quyền |
| TraceId của thay đổi role/group | Ai đã sửa quan hệ tạo ra quyết định |

**Không lưu** token truy cập, thông tin bí mật, payload tài liệu hoặc nguyên graph path không được phép vào log công khai. Nếu cần lưu bằng chứng quyền, giới hạn quyền xem audit và thời gian retention.

### 23.1. Vì sao đường giải thích phải gắn với thời điểm?

Quyền có thể thay đổi sau vài giây. Nếu audit chỉ lưu “U01 được READ DOC1” mà không lưu policy version hoặc tập thay đổi tương ứng, ngày hôm sau graph đã khác và không thể giải thích quyết định trước đó.

Có thể sử dụng **policy version**/event sourcing cho việc cập nhật grants, denies, memberships và resource ancestry. Nếu yêu cầu pháp lý buộc tái dựng chính xác quyền tại thời điểm cũ, dữ liệu graph hiện tại **không đủ**, cần lịch sử thay đổi được lưu bảo vệ khỏi chỉnh sửa không thẩm quyền.

## 24. Runbook đưa mô hình quyền vào tổ chức

### Giai đoạn thiết kế

1. Liệt kê actions thật: READ/WRITE/APPROVE, không dùng role name làm action.
2. Phân loại resources, owner, tenant và data sensitivity.
3. Xác định ai có thể tạo role, gán user vào group, thay deny hoặc đổi cây tài nguyên.
4. Viết chính sách **deny precedence**, inherited scope, depth và tiêu chí đối xử khi user/resource không tồn tại.
5. Xác nhận sự phân tách nhiệm vụ, ví dụ người soạn không tự phê duyệt tài liệu có yêu cầu kiểm soát đặc biệt.

### Giai đoạn triển khai

6. Tạo business IDs và unique constraints/indexes.
7. Seed roles/groups/resource tree có kiểm tra DAG, tenant boundaries và tình trạng cấp quyền.
8. Đưa toàn bộ đọc/ghi resource qua authorization gateway; giữ database service account ở mức quyền tối thiểu.
9. Cài integration tests với bảng expected positive/negative.
10. Quan sát query plans, cache invalidation, latency và những quyết định DENY.

### Giai đoạn vận hành

11. Giám sát số tài khoản không role, role cấp quyền rộng bất thường và deny exceptions tăng nhanh.
12. Có quy trình **joiner/mover/leaver**: vào công ty, chuyển nhóm, nghỉ việc phải cập nhật membership/quyền và session/token/cache phù hợp.
13. Tổ chức periodic access review: user nào còn quyền quản trị, role nào không còn dùng, grant nào trên tài nguyên nhạy cảm.
14. Diễn tập thu hồi khẩn cấp và kiểm tra rằng quyền không còn dùng được qua API, batch jobs và các cache.
15. Backup/restore graph policy kèm dữ liệu identity và thử chức năng authorization sau restore; một graph phục hồi thiếu user/role có thể từ chối hợp lệ hàng loạt hoặc có đường bỏ qua security.

**Nguyên tắc rollout:** nếu đang di trú từ một policy engine khác, áp dụng **shadow evaluation** (tính quyết định nhưng chưa chặn), so sánh với expected/engine cũ, xử lý sai lệch, rồi canary enforcement. Không bật enforcement toàn doanh nghiệp khi chưa có quy trình mở khóa khẩn cấp được kiểm soát và đường rollback phù hợp.

## 25. Bài tập có đáp án

### Bài 1 — Kế thừa vai trò

MANAGER → EDITOR → VIEWER. MANAGER có quyền nào nếu VIEWER được READ PRJ, EDITOR được WRITE PRJ và MANAGER được APPROVE PRJ?

**Đáp án:** MANAGER có **READ, WRITE, APPROVE** trên PRJ và tài nguyên con trong phạm vi kế thừa. VIEWER không tự được WRITE/APPROVE.

### Bài 2 — Kế thừa phạm vi tài nguyên

DOC1 → PRJ → ROOT và FIN1 → FIN → ROOT. VIEWER chỉ có READ trên PRJ. VIEWER có READ FIN1 không?

**Đáp án:** **Không.** Không có đường từ FIN1 lên PRJ; cùng thuộc ROOT chưa đủ vì không có grant trên ROOT.

### Bài 3 — Vai trò qua nhóm

U01 thuộc G_DEV, G_DEV có EDITOR, EDITOR kế thừa VIEWER. U01 có WRITE DOC1 không?

**Đáp án:** **Có**, vì EDITOR có WRITE PRJ, DOC1 nằm dưới PRJ và không có deny áp dụng DOC1.

### Bài 4 — Deny thắng grant

U01 có quyền READ/WRITE qua G_DEV nhưng có `DENIES {action:'ALL'}` trên DOC2. Có được READ/WRITE DOC2 không?

**Đáp án:** **Không cả hai.** `hasGrant=true` nhưng `hasDeny=true` nên `allowed=false`.

### Bài 5 — Deny theo action

U05 có EDITOR và DENY WRITE trên DOC2. Có đọc DOC2 được không? Có ghi được không?

**Đáp án:** **READ được**, **WRITE không**. Quy tắc P8 cho action độc lập, deny WRITE không tự chặn READ.

### Bài 6 — Kiểm toán đặc quyền

U02 được MANAGER trực tiếp. Nếu yêu cầu APPROVE DOC1, giải thích theo đường nào?

**Đáp án:** U02 → ASSIGNED_ROLE → MANAGER → GRANTS {APPROVE} → PRJ; DOC1 → PART_OF → PRJ; không có deny nên ALLOW.

### Bài 7 — Người không có vai trò

U06 tồn tại nhưng không có direct role hay group. Kết quả kiểm tra READ DOC1 là gì?

**Đáp án:** **DENY theo default deny**. Danh sách seeds rỗng, `hasGrant=false`, không được cho phép chỉ vì không có deny.

### Bài 8 — Node không tồn tại

Client yêu cầu U01 READ DOC99 nhưng DOC99 không tồn tại. Query mục 11 trả gì và API phải làm gì?

**Đáp án:** Query trả **0 record**. Backend phải **fail closed**; không coi 0 record là ALLOW, và tránh tiết lộ thông tin về tồn tại của tài nguyên không được phép.

### Bài 9 — Vòng kế thừa nguy hiểm

Nếu thêm VIEWER → MANAGER trong khi MANAGER → EDITOR → VIEWER đã tồn tại, chuyện gì xảy ra?

**Đáp án:** Tạo chu trình có thể khiến VIEWER đi tới quyền MANAGER, dẫn đến leo thang đặc quyền. Phải từ chối cập nhật tạo chu trình và test cạnh mới trong một quy trình quản trị có kiểm soát đồng thời.

### Bài 10 — Thu hồi quyền qua nhóm

U01 không có direct role, chỉ thuộc G_DEV. Nếu xóa membership G_DEV, U01 còn READ DOC1 không?

**Đáp án:** **Không**, trừ khi có đường grant khác được thêm ngoài fixture. Phải invalidation cache để quyết định cũ không còn hiệu lực ở API.

### Bài 11 — Quyền trong một transaction

Java service gọi `canWrite` trong transaction A rồi cập nhật tài liệu trong transaction B. Tại sao chưa tốt khi có revoke đồng thời?

**Đáp án:** Quyền có thể thay đổi giữa hai transaction. Nên kiểm tra và ghi trong cùng transaction, đồng thời thiết kế policy version/locking nếu yêu cầu thu hồi tức thời trước commit.

### Bài 12 — N+1 query

Danh sách có 2.000 tài liệu, service lấy hết ID rồi gọi truy vấn quyền riêng cho mỗi tài liệu. Hệ quả nào và cách tối ưu?

**Đáp án:** Có thể tạo ít nhất **2.000 lượt kiểm tra phụ**, tăng round trips và over-fetch. Dùng truy vấn quyền theo batch với `UNWIND` hoặc chiến lược index/materialized view có policy version, đo tính đúng và p95 trước khi triển khai.

### Bài 13 — Tenant isolation

Tenant A và B cùng có roleId EDITOR và resourceId DOC1. Nếu query chỉ `MATCH (r {resourceId:'DOC1'})` mà không kiểm tra tenant, rủi ro gì?

**Đáp án:** Có thể áp quyền từ tenant khác hoặc trả dữ liệu của tenant khác. Cần composite IDs/tenant scoping **trên mọi node và đường kế thừa**, không chỉ user/resource đầu vào.

### Bài 14 — Kiểm tra số lượng fixture

Có 6 user, 2 group, 4 role, 6 resource; 3 cạnh kế thừa role, 5 cạnh PART_OF, 5 cạnh ASSIGNED_ROLE, 2 MEMBER_OF, 4 GRANTS và 2 DENIES. Tổng node và relationship là bao nhiêu?

**Đáp án:** **18 node** và **21 relationship**. Nếu khác, cần reset/kiểm tra fixture trước khi dùng bảng quyền dự kiến.

## 26. Cleanup fixture và kiểm tra cuối

Chỉ chạy trên **database test** dùng đúng fixture của bài; không dùng lệnh này trên production.

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa004_user_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_group_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_role_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa004_resource_id IF EXISTS;
~~~

Kiểm chứng:

~~~cypher
MATCH (n)
WHERE n:QA004User
   OR n:QA004Group
   OR n:QA004Role
   OR n:QA004Resource
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining=0`. Nếu đang thử nghiệm thu hồi group/cấp deny, cleanup cũng xóa thay đổi đó vì nó thuộc các node fixture. Không chạy nếu các label này bị tái sử dụng bởi dữ liệu thật.

## 27. Tài liệu tham khảo và bài học rút ra

- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/): truy vấn node/relationship và pattern có hướng.
- [Neo4j Cypher Manual — Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/): các đường có số bước thay đổi, giới hạn và cách mô hình đường đi.
- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/): biểu thức kiểm tra sự tồn tại của đường hợp lệ.
- [Neo4j Cypher Manual — Predicates](https://neo4j.com/docs/cypher-manual/current/functions/predicate/): `any`, `all` và các phép kiểm tra logic.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness và khả năng bảo vệ khóa nghiệp vụ.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`/`PROFILE` để tối ưu truy vấn quyền.
- [Neo4j Operations Manual — Security and access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/access-control/): phân quyền ở tầng DBMS, khác ACL ứng dụng.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): kiểm tra và cập nhật trong managed transaction.
- [Neo4j Java Driver Manual — Run queries](https://neo4j.com/docs/java-manual/current/query-simple/): tham số hóa, `Record` và cách tiêu thụ kết quả.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): mapping entity, `Neo4jClient` và Spring transaction management.
- [NIST RBAC model and standard](https://csrc.nist.gov/projects/role-based-access-control): khái niệm RBAC, vai trò/hierarchy và separation of duties.

**Ghi nhớ:** Graph là công cụ tốt để mô hình hóa **ai thuộc nhóm nào, nhận vai trò nào, kế thừa quyền qua đường nào và quyền có hiệu lực trên tài nguyên nào**. Nhưng một hệ thống phân quyền an toàn phải có **chính sách tường minh**: default deny, deny precedence, giới hạn đường kế thừa, tenant isolation, chống chu trình, xác thực danh tính, transaction/thu hồi/cache nhất quán và test negative. **Có một đường GRANTS không đủ kết luận ALLOW**; quyết định cuối cùng chỉ đúng khi đã kiểm tra đầy đủ cả những đường **DENIES** và các điều kiện nghiệp vụ còn lại.
