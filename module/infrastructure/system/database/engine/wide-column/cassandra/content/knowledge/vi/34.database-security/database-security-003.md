# Authentication/authorization và cấu hình theo phiên bản

## 1. Vì sao một cluster Cassandra khỏe về replication vẫn có thể không an toàn?

**Apache Cassandra** được thiết kế để phân tán partition theo token, đặt nhiều replica theo replication factor (RF) và đáp ứng đọc/ghi theo consistency level (CL). Những cơ chế này hỗ trợ tính sẵn sàng và độ bền, nhưng **không quyết định ai được phép đọc, sửa hoặc xóa dữ liệu**.

Ví dụ một dịch vụ telemetry có ba replica trong `dc1`, dùng `LOCAL_QUORUM`. Nếu cluster cho phép kết nối CQL mà không xác thực, một người có quyền truy cập mạng tới cổng native protocol có thể thử thực hiện các truy vấn mà chính sách doanh nghiệp không cho phép. **RF = 3 và `LOCAL_QUORUM` không ngăn truy cập trái phép**. Tương tự, nếu một tài khoản ứng dụng có quyền superuser, lộ thông tin kết nối có thể dẫn tới sửa schema, xóa dữ liệu hoặc thay đổi các role.

Bài học trong chương **Bảo mật** tập trung vào **authentication (xác thực)**, **authorization (phân quyền)** và sự khác biệt **cấu hình theo phiên bản Cassandra**; đồng thời liên hệ với TLS, JMX, Java Driver, replication của dữ liệu bảo mật, kiểm toán và xử lý lỗi.

**Sau bài này, bạn có thể:**

1. Phân biệt xác thực, phân quyền, mã hóa đường truyền và audit — bốn lớp không thay thế nhau.
2. Hiểu vai trò của `Authenticator`, `Authorizer`, `RoleManager`, role membership và CQL permissions.
3. Thiết kế role **least privilege** cho dịch vụ Java, người phân tích dữ liệu và nhóm migration.
4. Giải thích vì sao phải chăm sóc keyspace `system_auth`, nhất là cluster nhiều datacenter.
5. Biết cách đối chiếu **phiên bản Cassandra, cấu hình thực tế và công cụ client** thay vì sao chép một tệp `cassandra.yaml` mẫu.
6. Thực hành CQL RBAC, kết nối Java Driver 4.x có TLS, kiểm tra cả trường hợp được phép và bị từ chối.
7. Lập kế hoạch bật authentication/authorization, xoay credential, theo dõi và khôi phục khi cấu hình sai.

**Giới hạn học thuật:** ví dụ giả định Cassandra dùng full replica thông thường và `NetworkTopologyStrategy`; tên DC là `dc1`. Các lớp/plugin xác thực, tùy chọn TLS, hệ thống logging, các permission bổ sung, cách cấp credential và mặc định thay đổi giữa Cassandra **3.x, 4.x, 5.x** cũng như bản phân phối của nhà cung cấp. Bất kỳ mẫu cấu hình nào đều phải kiểm tra với **phiên bản đang triển khai**, không áp dụng trực tiếp lên production.

## 2. Bốn câu hỏi bảo mật khác nhau

| Câu hỏi | Cơ chế | Ví dụ | Điều cơ chế đó **không** tự làm |
| --- | --- | --- | --- |
| **Bạn là ai?** | **Authentication** | Kết nối CQL dùng user/password hoặc cơ chế xác thực được hỗ trợ. | Không quyết định user được xem bảng nào. |
| **Bạn được phép làm gì?** | **Authorization** | Role `events_reader` được `SELECT` trên đúng một bảng. | Không mã hóa password đang truyền qua mạng. |
| **Dữ liệu có bị đọc/sửa trên đường truyền không?** | **Transport security/TLS** | Client-to-node TLS và internode encryption. | Không thay chính sách role; kết nối TLS vẫn có thể bị cấp quyền quá rộng. |
| **Ai đã làm gì, khi nào?** | **Audit/monitoring** | Ghi actor, CQL action, UTC timestamp, outcome và change ID. | Không ngăn một hành động nếu quyền vẫn cho phép; không thay backup. |

Một hệ thống an toàn cần kết hợp các lớp. Bật **PasswordAuthenticator** nhưng để client kết nối qua đường truyền không mã hóa làm tăng rủi ro lộ bí mật; bật TLS mà để **AllowAllAuthorizer** có thể dẫn tới mọi user đã kết nối được thực hiện thao tác rộng hơn dự tính.

### 2.1. Bốn kiểu danh tính thường gặp

- **Ứng dụng Java:** mỗi service/workload có identity riêng, quyền tối thiểu trên keyspace/table cần thiết.
- **Automation/migration:** identity chuyên dùng cho schema change hoặc tác vụ bảo trì, có approval và thời hạn.
- **Người vận hành:** identity cá nhân qua quản lý danh tính/bastion, có thể được cấp quyền tạm theo nhiệm vụ.
- **Đường quản trị node:** identity dùng SSH, container/orchestrator, JMX hoặc backup; **khác kênh CQL**.

**Không dùng một tài khoản superuser cho tất cả bốn nhóm.** Nếu tất cả cùng chia sẻ một password, không thể thu hồi riêng một workload hay quy trách nhiệm đúng người khi xảy ra sự cố.

## 3. Kiến trúc xác thực và phân quyền trong Cassandra

~~~mermaid
flowchart TD
    A["Java Driver / cqlsh"] --> B["Kết nối native protocol qua TLS"]
    B --> C["Authenticator: xác minh danh tính"]
    C --> D{"Đăng nhập hợp lệ?"}
    D -->|Không| E["Authentication error"]
    D -->|Có| F["RoleManager: role, login, membership"]
    F --> G["Authorizer: quyền hiệu lực trên tài nguyên CQL"]
    G --> H{"Được phép thao tác?"}
    H -->|Không| I["Unauthorized / permission denied"]
    H -->|Có| J["Coordinator xử lý CQL và liên hệ replicas"]
    J --> K["Dữ liệu trong keyspace nghiệp vụ"]
    L["system_auth và metadata/cache liên quan"] -.-> C
    L -.-> F
    L -.-> G
    M["Audit / server logs / metrics"] -.-> C
    M -.-> G
    M -.-> J
~~~

Các thành phần có trách nhiệm khác nhau:

- **`Authenticator`** xác minh danh tính ở lúc thiết lập kết nối; cấu hình thường gặp trong Apache Cassandra là `PasswordAuthenticator` hoặc cơ chế khác được phiên bản hỗ trợ. `AllowAllAuthenticator` nghĩa là không có kiểm tra xác thực CQL theo cách password auth.
- **`Authorizer`** xác định hành động đối với resource có được phép không; `CassandraAuthorizer` dùng hệ permissions Cassandra. `AllowAllAuthorizer` không phải cấu hình least-privilege cho sản xuất.
- **`RoleManager`** quản lý role, trạng thái `LOGIN`, `SUPERUSER`, thông tin xác thực và quan hệ kế thừa role. `CassandraRoleManager` là một lựa chọn thường gặp.
- **Các cơ chế giới hạn theo mạng/DC hoặc plugin nâng cao** có thể tồn tại trong một số phiên bản/phân phối. Chúng bổ sung policy, không thay kiểm tra CQL resource permissions.

**Lưu ý về phiên làm việc:** Authentication thường xảy ra khi kết nối được tạo; authorization có thể sử dụng cache. Thu hồi role/password **không bảo đảm mọi kết nối đã mở tự bị ngắt ngay lập tức**. Chính sách rotation và thu hồi khẩn cấp phải tính đến connection pools, thời gian sống cache và việc tái kết nối.

## 4. Cấu hình theo phiên bản: nguyên tắc và bảng đối chiếu

### 4.1. Tại sao không copy một tệp `cassandra.yaml` bất kỳ?

Khi đọc tài liệu trên Internet, bạn có thể thấy cấu hình dành cho Cassandra 3.11, 4.0, 4.1, 5.x, bản thương mại hoặc môi trường operator-managed. Dù cùng dùng từ “authentication”, các biến thể có thể khác ở:

- **Giá trị mặc định** của authenticator, authorizer, TLS và cấu hình ví dụ.
- **Tên key** trong `cassandra.yaml`, thuộc tính JVM và khả năng reload động.
- **Cơ chế network/DC authorization**, role management, certificate authentication hoặc plugin mở rộng.
- **Kiểu audit logging**, mức chi tiết/retention và ảnh hưởng hiệu năng.
- **Cách cấu hình TLS** cho native transport, internode, JMX, client và cách truststore/keystore được xử lý.
- **Cache authorization/credential**, khoảng thời gian TTL và cơ chế làm mới.

Do đó, tài liệu triển khai phải bắt đầu bằng **phiên bản đang chạy**, bản phân phối, hình thức cài đặt (bare metal, VM, container/operator) và trạng thái cấu hình hiện có.

### 4.2. Bảng định hướng theo dòng phiên bản

| Phạm vi | Điều có thể tìm thấy | Điều cần kiểm tra với đúng bản phát hành |
| --- | --- | --- |
| **Apache Cassandra 3.x** | Xác thực dựa trên role/password và CQL permissions, `PasswordAuthenticator`, `CassandraAuthorizer` trong các bản phù hợp. | Tài liệu cho đúng minor release; cách bật TLS/JMX, audit ngoài hoặc cơ chế ghi log sẵn có, role metadata cache. |
| **Apache Cassandra 4.0/4.1** | Các cơ chế role/permission tiếp tục tồn tại; có thêm thay đổi về vận hành, logging, security options so với 3.x. | Tên thuộc tính cache, audit logging, các khả năng phân quyền mở rộng theo network/DC và cơ chế TLS cụ thể. |
| **Apache Cassandra 5.x** | Mô hình role/permission vẫn là nền tảng; một số tính năng chính sách và plugin nâng cao tiếp tục phát triển. | Hình thức auth plugin đang hỗ trợ, TLS/JMX, mặc định, key bị đổi/bỏ và tính tương thích client/driver. |
| **Bản managed/vendor/operator** | Có thể dùng identity, certificate, IAM, secrets và policy từ nền tảng. | Cái gì do provider quản lý, quyền nào do tenant kiểm soát, và những lệnh config/nodetool nào bị hạn chế. |

Bảng này **không phải ma trận cam kết tính năng**. Chẳng hạn không nên kết luận “bản 4.x nào cũng có đúng cùng tính năng audit/authorization network” hoặc “cấu hình TLS ở 3.11 và 5.x giống nhau”. Nếu tài liệu bảo mật không ghi rõ **version**, hãy xem đó là **gợi ý cần kiểm chứng**, chưa phải runbook.

### 4.3. Mẫu cấu hình cốt lõi mang tính minh họa

Nhiều triển khai Cassandra dựa trên các mục tương tự sau trong `cassandra.yaml`:

~~~yaml
# MẪU KHÁI NIỆM — KHÔNG sao chép vào production khi chưa so version.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
~~~

Đây là **ba cơ chế khác nhau**, không phải ba alias của một chức năng. Có môi trường dùng custom provider, proxy hoặc plugin thay vì password auth. Một số cấu hình cần **restart/rolling restart** và phải được chuẩn bị trước; không thay đổi hàng loạt mọi node trong cluster mà thiếu kế hoạch giữ quorum và đường truy cập khẩn cấp.

**Không kết luận đã an toàn chỉ vì nhìn thấy ba dòng trên.** Phải kiểm chứng quyền CQL thực sự được thực thi, TLS, `system_auth`, cổng JMX, danh tính superuser, audit và các đường truy cập OS.

## 5. Keyspace `system_auth`: dữ liệu bảo mật cũng cần replication và repair

Với các cơ chế auth built-in, Cassandra lưu thông tin role, mật khẩu dạng được bảo vệ và permissions trong **keyspace hệ thống liên quan authentication**, thường là `system_auth`. Nó là dữ liệu phân tán phục vụ việc đăng nhập và quyết định quyền, không phải một tệp password đơn trên một node.

**Hệ quả:** nếu `system_auth` có RF hoặc bố trí replica quá yếu, một sự cố node/DC có thể ảnh hưởng đến **khả năng tạo kết nối mới hoặc đánh giá quyền**, ngay cả khi keyspace dữ liệu nghiệp vụ vẫn đủ replica.

### 5.1. Không bỏ qua RF theo từng DC

Ví dụ một cluster có:

~~~text
Datacenter dc1: 3 nodes
Datacenter dc2: 3 nodes
Keyspace nghiệp vụ: NetworkTopologyStrategy {dc1: 3, dc2: 3}

Điều cần kiểm tra thêm:
  system_auth có RF và replica placement phù hợp ở cả hai DC?
  Các replica mới của system_auth đã nhận đủ dữ liệu role/permission?
  Nếu dc1 mất, client ở dc2 còn đăng nhập được theo CL/cache thực tế?
~~~

Kiểm tra replication metadata:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name IN ('system_auth');
~~~

Câu lệnh trên chỉ cho biết **replication metadata**, không chứng minh mọi replica của `system_auth` đã nhận đủ dữ liệu cũ. Nếu phải thay RF, cần **lập kế hoạch dữ liệu và repair/streaming** cho keyspace đó, không chỉ sửa metadata. Thực hành với `system_auth` có nguy cơ khóa quản trị viên khỏi cluster; không tự ý thay trong production.

### 5.2. Điều gì xảy ra khi thay RF của `system_auth`?

Về mặt CQL, việc đổi replication của keyspace dùng cú pháp `ALTER KEYSPACE`; ví dụ minh họa **chỉ để đọc hiểu**:

~~~sql
-- MINH HỌA; không chạy trước khi có runbook/backup và xác minh topology.
ALTER KEYSPACE system_auth
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Điều kiện để một cấu hình như vậy có ý nghĩa:

1. Hai DC **thực sự tồn tại** với đúng tên mà snitch báo; có đủ node/rack theo mục tiêu.
2. Có kế hoạch thay đổi an toàn theo **phiên bản** Cassandra đang chạy và quyền `ALTER` cần thiết.
3. Sau khi RF metadata thay đổi, dữ liệu role/permission cũ cần được **đồng bộ tới những natural replicas mới** qua quy trình repair/streaming phù hợp.
4. Đã kiểm tra đăng nhập, quyền hiệu lực, session và kết nối **tại từng DC** sau chuyển đổi.
5. Có phương án khôi phục credential và dữ liệu `system_auth` nếu thất bại.

**Không dùng `TRUNCATE system_auth` hoặc sửa trực tiếp các bảng nội bộ** để “reset mật khẩu” khi mất quyền. Cấu trúc bảng hệ thống, bootstrap credentials và công cụ phục hồi khác theo phiên bản; cần runbook được phê duyệt.

### 5.3. Cache làm cho quyền nhìn như cập nhật chậm

Để giảm chi phí đọc dữ liệu role/permission ở mỗi request, Cassandra có thể cache credentials, roles và permissions. Vì vậy:

- `GRANT` hoặc `REVOKE` thành công không bảo đảm mọi node ngay lập tức áp dụng kết quả với cùng tốc độ.
- Một node mới gia nhập, node vừa restart hoặc client đã có kết nối có thể biểu hiện khác nhau trong khoảng hội tụ/cache.
- Các tùy chọn có tên kiểu `credentials_validity_in_ms`, `roles_validity_in_ms`, `permissions_validity_in_ms` có thể xuất hiện theo phiên bản, nhưng **mặc định và hành vi cần được xác minh**.
- Với thay đổi **thu hồi quyền khẩn cấp**, không chỉ chờ TTL cache một cách thụ động; phải dùng quy trình thu hồi phiên kết nối, credential, mạng và xác minh thực quyền theo khả năng của phiên bản.

Cache tối ưu hiệu năng; nó **không thay thế kiểm soát chính sách và hậu kiểm**.

## 6. CQL RBAC: tài nguyên, quyền và role membership

### 6.1. Những quyền CQL nền tảng

| Permission (thường gặp) | Ý nghĩa khái quát | Ví dụ phạm vi |
| --- | --- | --- |
| `SELECT` | Đọc dữ liệu. | Một bảng hoặc keyspace. |
| `MODIFY` | Thay đổi dữ liệu được phép, gồm các thao tác ghi/xóa trong phạm vi tương ứng. | Bảng phục vụ ghi. |
| `CREATE` | Tạo một loại resource/schema phù hợp. | Keyspace, table hoặc resource được hỗ trợ. |
| `ALTER` | Thay đổi cấu trúc hoặc thuộc tính resource. | Một bảng, keyspace hoặc role phù hợp. |
| `DROP` | Xóa resource được cấp quyền. | Bảng/keyspace/role phù hợp. |
| `AUTHORIZE` | Cấp/thu hồi permissions trong phạm vi resource cho phép. | Một bảng/keyspace/role. |
| Các quyền bổ sung như `DESCRIBE`, `EXECUTE` | Có thể áp dụng cho resource riêng, function hoặc các tính năng theo version. | Phải đối chiếu đúng phiên bản. |

Quyền phụ thuộc **resource hierarchy** và có thể được cấp ở nhiều phạm vi: bảng, keyspace, toàn bộ keyspace, role, toàn bộ role hoặc các đối tượng khác được phiên bản hỗ trợ. Một role có `SELECT` ở cấp **keyspace** có thể đọc nhiều bảng hơn role chỉ có `SELECT` trên **một bảng**.

**Tránh dùng `GRANT ALL PERMISSIONS` cho ứng dụng** trừ khi đã có lý do được duyệt và hiểu chính xác resource/phiên bản. Đặc biệt, `AUTHORIZE` hoặc quyền quản trị role có thể khiến một identity cấp thêm quyền cho identity khác.

### 6.2. Role có thể không được phép login

Role nhóm kiểu `events_reader` thường được tạo với:

~~~sql
CREATE ROLE IF NOT EXISTS events_reader
WITH LOGIN = false
AND SUPERUSER = false;
~~~

`LOGIN = false` giúp role đóng vai trò **nhóm quyền**, không phải user kết nối trực tiếp. Identity đăng nhập thực tế có thể được provisioning bằng công cụ bảo mật/secrets và được gán role nhóm. `SUPERUSER = false` giữ quyền quản trị ở mức bình thường; **không cần superuser** để đọc một bảng.

### 6.3. Role membership không đồng nghĩa hai tài khoản dùng chung password

Giả sử tài khoản đăng nhập `telemetry_api_identity` **đã tồn tại** do hệ thống provisioning tạo và quản lý credential:

~~~sql
-- Administrator chạy lệnh trong môi trường lab đã bật authorizer.
GRANT events_reader TO telemetry_api_identity;

-- Xem role membership và quyền hiệu lực theo phiên bản phù hợp.
LIST ROLES OF telemetry_api_identity;
LIST ALL PERMISSIONS OF telemetry_api_identity;
~~~

Lúc này identity đăng nhập **thừa hưởng quyền** từ role nhóm nhưng không cần chia sẻ password của nhóm. Nếu role membership thay đổi, phải kiểm tra mọi đường thừa hưởng; `REVOKE events_reader FROM telemetry_api_identity` chỉ thu hồi membership đó, **không tự thu hồi quyền trực tiếp hoặc role khác** mà identity có.

## 7. Lab an toàn: cấp `SELECT` cho một bảng, xác minh `MODIFY` bị từ chối

### 7.1. Tạo keyspace và bảng trên cluster lab

Giả sử lab có DC `dc1` với ít nhất ba full replica, authentication/authorization đã bật và có admin được cấp quyền:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_secure
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_secure.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO telemetry_secure.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001,
   'temperature', '21.5');
~~~

Partition key là `(device_id, event_day)`; clustering key là `(event_time, event_id)`. Thiết kế này giúp read theo thiết bị/ngày, nhưng **việc query có partition key đúng không liên quan trực tiếp tới việc identity có quyền `SELECT` hay không**. Authorization kiểm tra **ai được đọc bảng**; token routing quyết định **đọc ở replica nào**.

### 7.2. Tạo role nhóm và chỉ cấp quyền đọc

~~~sql
CREATE ROLE IF NOT EXISTS telemetry_day_reader
WITH LOGIN = false
AND SUPERUSER = false;

GRANT SELECT ON TABLE telemetry_secure.events_by_device_day
TO telemetry_day_reader;

LIST ALL PERMISSIONS OF telemetry_day_reader;
~~~

Provision identity `readonly_lab_identity` bằng cơ chế cấp credential được duyệt của lab. Sau khi identity đó tồn tại:

~~~sql
GRANT telemetry_day_reader TO readonly_lab_identity;

LIST ROLES OF readonly_lab_identity;
LIST ALL PERMISSIONS OF readonly_lab_identity;
~~~

**Chú ý:** nếu `readonly_lab_identity` đã có `MODIFY` trực tiếp ở cấp keyspace hoặc đã là superuser, phép thử “chỉ đọc” sẽ không có ý nghĩa. Phải bắt đầu bằng một identity lab mới có quyền tối thiểu và kiểm tra membership/permissions thực tế.

### 7.3. Thử đăng nhập bằng identity chỉ đọc

Khi kết nối đã dùng TLS và xác thực đúng identity, chạy:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_type, payload
FROM telemetry_secure.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

**Kỳ vọng:** SELECT thành công nếu role được cấp đúng và `dc1` có đủ replica đáp ứng CL.

Sau đó kiểm chứng trường hợp **phải bị từ chối**, nhưng không thực hiện thao tác phá hủy trên dữ liệu thật:

~~~sql
-- CHỈ dùng trong lab biệt lập, với identity readonly_lab_identity.
-- Lệnh phải bị từ chối khi không có MODIFY:
DELETE FROM telemetry_secure.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:00:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174001;
~~~

Nếu `DELETE` **thành công**, đó là **tín hiệu lỗi phân quyền** trong bài lab: kiểm tra `authorizer`, user identity đang login, superuser, role membership và quyền hiệu lực cấp keyspace/table. Đừng lập tức kết luận Cassandra “bỏ qua role”; có thể bài kiểm thử dùng nhầm tài khoản admin.

**Hậu kiểm:** xác minh bằng **tài khoản thật**, trên **nhiều node/coordinator** nếu yêu cầu policy và cấu hình cache phân tán; đối chiếu audit log. Một `LIST ALL PERMISSIONS` thành công không thay cho phép thử allow/deny.

### 7.4. Thu hồi một role nhóm theo đúng phạm vi

Khi muốn kết thúc bài lab:

~~~sql
-- Administrator thực hiện trong lab; không thay role production.
REVOKE telemetry_day_reader FROM readonly_lab_identity;
~~~

Không tùy tiện `DROP ROLE` nếu role còn được identity khác sử dụng. Sau `REVOKE`, kiểm tra thực quyền và **khoảng thời gian tác dụng của cache/kết nối**; đăng nhập lại nếu cần để xác minh policy đối với kết nối mới.

## 8. Chính sách mật khẩu và bootstrap quyền quản trị

### 8.1. Tài khoản đầu tiên là vấn đề quản trị, không chỉ CQL

Khi bật `PasswordAuthenticator` và `CassandraAuthorizer`, cluster phải có **cách hợp lệ để tạo/quản lý identity quản trị ban đầu**. Ở một số phiên bản hoặc trạng thái mặc định, có thể tồn tại role bootstrap/superuser mặc định nổi tiếng. Mọi mật khẩu khởi tạo như vậy phải được xử lý **theo tài liệu phiên bản**:

1. Tạo/kiểm tra đường truy cập quản trị được phép theo đúng bootstrap sequence.
2. Thiết lập credential mạnh qua kênh được mã hóa; không gửi password trong ticket/chat/log.
3. Tạo danh tính quản trị **định danh riêng**, kiểm chứng hoạt động trước khi thay đổi identity bootstrap.
4. Thu hồi/vô hiệu hóa đường mặc định theo runbook đã duyệt; không để quyền truy cập mặc định tồn tại lâu.
5. Kiểm tra hoạt động của **nhiều node/DC**, đặc biệt nếu `system_auth` vừa đổi RF hoặc cache chưa hội tụ.
6. Chuẩn bị **break-glass procedure** có audit và người phê duyệt độc lập.

Không sử dụng password mẫu trong tài liệu làm credential thật. **Không đăng nhập bằng superuser để chạy workload ứng dụng.**

### 8.2. Vì sao không viết password vào CQL script hoặc command line?

`CREATE ROLE ... WITH PASSWORD = '...'` là cú pháp có thể tồn tại, nhưng giá trị plaintext có thể bị lưu trong:

- File migration/source control hoặc lịch sử `cqlsh`.
- Terminal scrollback, shell history, process list nếu password là argument.
- Debug/audit logs hoặc đầu ra CI/CD khi script được echo.
- Backups của workspace hoặc tài liệu hỗ trợ.

Nếu provisioning bắt buộc dùng password:

- Lấy giá trị từ **secret manager/cấp phát identity**; chỉ công cụ có quyền tối thiểu được biết.
- Dùng kết nối **TLS đã xác thực server**, không truyền plaintext trên mạng.
- Tránh đưa secret vào argv, file không mã hóa và log; bảo vệ quyền đọc của công cụ cấp phát.
- Rotate khi nhân sự thay đổi hoặc nghi lộ secret; không dùng chung giữa dev/staging/prod.
- Tính đến việc người dùng/các connection pools phải kết nối lại khi thay credential.

Ở môi trường có cơ chế **chứng chỉ hoặc identity federation**, có thể cân nhắc nếu phiên bản/phân phối hỗ trợ, nhưng không khẳng định mọi Cassandra đều hỗ trợ cùng plugin và cú pháp cấu hình.

## 9. TLS cho native protocol và internode: riêng với authorization

**Native transport** là đường ứng dụng/`cqlsh` kết nối tới Cassandra (cổng thường gặp `9042`). **Internode communication** là đường các node trao đổi mutation, đọc, gossip/streaming và dữ liệu cần thiết cho phân tán. Hai kênh cần **thiết kế TLS riêng**, thường tương ứng nhóm cấu hình `client_encryption_options` và `server_encryption_options`, nhưng **tên key cụ thể thay đổi theo phiên bản**.

~~~mermaid
flowchart LR
    A["Java client + truststore"] -->|"TLS native transport"| B["Node N1: coordinator"]
    B -->|"TLS internode nếu bật đúng"| C["Node N2: replica"]
    B -->|"TLS internode nếu bật đúng"| D["Node N3: replica"]
    E["CQL role/permission check"] -.-> B
    F["JMX admin channel: bảo vệ riêng"] -.-> B
~~~

### 9.1. Các điểm kiểm tra TLS

| Vấn đề | Câu hỏi bắt buộc |
| --- | --- |
| **Server identity** | Client có kiểm tra chain chứng chỉ, hostname/SAN và trust anchors hay chỉ “mã hóa nhưng tin mọi certificate”? |
| **Protocol/cipher** | Chỉ chấp nhận phiên bản giao thức và cipher suite được policy cho phép? |
| **Certificate lifecycle** | Ai cấp, phân phối, rotate, thu hồi certificate? Nếu cert hết hạn giữa cao điểm thì sao? |
| **Client certificate/mTLS** | Phiên bản/cấu hình có yêu cầu client certificate không? Nếu có, mapping sang identity nào? |
| **Internode** | Mọi liên kết node/rack/DC cần mã hóa đã thực sự sử dụng TLS chưa? |
| **Mixed rollout** | Có đoạn chuyển tiếp nào cho kết nối không mã hóa? Có hết hạn/khóa lại sau rollout không? |
| **Network exposure** | Cổng CQL/JMX/internode có bị public không cần thiết; firewall và bastion có kiểm soát không? |

**Không dùng SSLContext “trust-all”, bỏ kiểm tra chứng chỉ hoặc tự tắt hostname verification** để chữa lỗi bắt tay TLS. Những “cách sửa nhanh” đó có thể khiến client kết nối tới node giả mạo.

### 9.2. Cấu hình tham khảo chỉ về **ý định**, không phải file hoàn chỉnh

~~~yaml
# KHÁI NIỆM; tên field/cấu trúc/mặc định phải kiểm tra bản Cassandra thật.
# Hai nhóm cấu hình thường gặp trong cassandra.yaml:
client_encryption_options:
  enabled: true
  # truststore/keystore, client_auth, certificate policy theo phiên bản

server_encryption_options:
  # bảo vệ internode traffic (node-node, cross-DC) theo phiên bản
  internode_encryption: all
~~~

Không được copy khối này và kỳ vọng TLS hoạt động. Nó **chưa chứa chính sách certificate, key material, trust, port, rollout strategy** hay giải thích phiên bản. Khi bật TLS cần xác minh bằng **kết nối client thực với certificate hợp lệ** và **đường internode**; chỉ nhìn `enabled: true` không đủ.

**Mã hóa tại chỗ lưu (at rest)** là vấn đề khác: TLS không mã hóa sẵn mọi SSTable, commit log, hints, snapshot hay backup trên ổ. Cần chính sách encryption at rest, volume/key management và bảo vệ backup theo rủi ro của dữ liệu.

## 10. Java Driver 4.x: xác thực đúng identity và từ chối TLS không tin cậy

Ứng dụng Java nên kết nối bằng **identity riêng**, truststore đã cấu hình và `localDatacenter` chính xác. Ví dụ dùng Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.Objects;
import javax.net.ssl.SSLContext;

public final class SecureCassandraRead {
    public static void main(String[] args) throws Exception {
        // CHỈ để minh họa lab: secret từ biến môi trường có hạn chế bảo mật.
        // Production nên tích hợp secret manager và quy trình rotation.
        String username = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_USER"), "missing username");
        String password = Objects.requireNonNull(
            System.getenv("CASSANDRA_APP_PASSWORD"), "missing password");

        // Truststore hợp lệ phải được cấu hình trước trong JVM.
        // Không sử dụng trust-all SSLContext.
        SSLContext tls = SSLContext.getDefault();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("cassandra.lab.example", 9042))
                .withLocalDatacenter("dc1")
                .withAuthCredentials(username, password)
                .withSslContext(tls)
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_type " +
                "FROM telemetry_secure.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ? LIMIT 20");

            BoundStatement read = query.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " " + row.getString("event_type"));
            }
        }
    }
}
~~~

**Giải thích:**

1. `withAuthCredentials` dùng identity đã được provisioning, **không** dùng tài khoản superuser. Mỗi môi trường/service cần credential riêng.
2. `SSLContext.getDefault()` chỉ an toàn khi JVM có **truststore và policy xác thực server đúng**; mặc định có thể không tin CA nội bộ và việc kết nối sẽ thất bại — đó là tín hiệu cần sửa trust, **không tắt TLS**.
3. Biến môi trường tiện minh họa nhưng có thể bị đọc qua quyền quản trị/process/container. Production nên dùng **secret manager hoặc identity provider được hỗ trợ**, không log giá trị và hạn chế quyền xem cấu hình.
4. `cassandra.lab.example` là DNS ví dụ; endpoint thật phải khớp certificate SAN/hostname và chính sách load balancing.
5. `LOCAL_QUORUM` với RF = 3 tại `dc1` yêu cầu **hai replica phản hồi**, nhưng CL **không cấp quyền** đọc bảng. Authorization được xử lý độc lập với replica quorum.
6. Không lưu `password` trong message, metrics, exception hay tracing. Java `String` có hạn chế xóa khỏi bộ nhớ nên phải kiểm soát vòng đời process, heap dump và quản lý secrets.
7. Nếu dùng paging hoặc retry, không biến authentication/authorization error thành vòng retry vô hạn; lỗi đó cần sửa **credential hoặc quyền**, không phải tăng timeout.

### 10.1. Khi lỗi xảy ra, phân biệt các lớp

| Lỗi quan sát | Cần kiểm tra |
| --- | --- |
| TLS handshake/certificate validation failure | Truststore, CA, SAN/hostname, ngày hết hạn, TLS protocol, proxy và clock. |
| Bad credentials/authentication error | User, secret, cơ chế authenticator, account `LOGIN`, `system_auth` và cache. |
| Unauthorized/permission denied | `CassandraAuthorizer`, effective roles, resource/permission, membership và cache. |
| `Unavailable` | RF/CL, node/DC và replica health; **không phải** lỗi password. |
| Read/write timeout | Latency, I/O, GC, tombstone, network, replica và deadline; **không tự chứng minh** thiếu quyền. |
| Connection refused/no route | Port, firewall, TLS listener, node service và routing. |

**Không tự động retry lỗi xác thực/phân quyền ở tần suất cao.** Retry storm gây thêm log/CPU và có thể kích hoạt kiểm soát bảo mật; xoay secret hoặc điều chỉnh role phải theo quy trình có hậu kiểm.

## 11. CQL, JMX và hệ điều hành: ba bề mặt quyền phải xét độc lập

`PasswordAuthenticator` và `CassandraAuthorizer` kiểm soát **native CQL** theo cấu hình. Chúng **không mặc nhiên cấp hay tước quyền** cho tất cả đường quản trị:

| Kênh | Ví dụ hành động | Đường kiểm soát |
| --- | --- | --- |
| **CQL** | `SELECT`, `INSERT`, `ALTER KEYSPACE`, `GRANT`, `REVOKE`. | Authentication/authorization của Cassandra và role permissions. |
| **JMX / nodetool** | `repair`, `snapshot`, `cleanup`, `drain`, xem MBeans. | JMX authentication/authorization, TLS/network isolation, quyền dùng công cụ. |
| **OS / SSH / container** | Đổi `cassandra.yaml`, đọc log, xem data directory, restart node. | OS ACL, sudo, SSH/IAM, container/orchestrator RBAC. |
| **Backup/storage** | Đọc snapshot, tải SSTable, xóa backup. | IAM, object storage policies, encryption key access và retention. |

Một identity bị **Unauthorized** ở CQL vẫn có thể gây tác động nếu có SSH root hoặc JMX quản trị không kiểm soát. Ngược lại, tài khoản CQL có quyền `SELECT` không nên được hiểu là có quyền dùng `nodetool status` trên máy chủ.

**Nguyên tắc triển khai:**

- Không mở cổng JMX ra mạng không tin cậy; dùng bastion/firewall và cơ chế xác thực thích hợp.
- Không chạy Cassandra dưới tài khoản OS có quyền quá rộng nếu không cần.
- Tách role viewer JMX, operator có quyền quản trị và role CQL của ứng dụng khi nền tảng hỗ trợ; nếu JMX không phân quyền chi tiết, bọc bằng **automation allowlist** và approval.
- Không cho CI/CD dùng một mật khẩu chung có khả năng `DROP`, `ALTER` mọi keyspace.
- Giữ quyền xem log, snapshot và backup theo rủi ro truy cập dữ liệu nhạy cảm.

## 12. Audit và giám sát: xác thực thành công chưa phải hệ thống an toàn

Một cluster có thể từ chối đăng nhập sai nhưng vẫn không có bằng chứng rõ ràng về hoạt động **thay quyền**, **xóa bảng**, hoặc **mở JMX** ngoài dự kiến. Vì vậy cần giám sát:

| Nhóm tín hiệu | Câu hỏi cần trả lời | Lưu ý |
| --- | --- | --- |
| Failed/successful authentication | Có làn sóng đăng nhập lỗi, credential hết hạn hay thử brute force không? | Bảo vệ PII, không log password. |
| Authorization denied | Role nào thử thao tác vượt quyền, resource nào bị nhắm tới? | Cần phân biệt lỗi triển khai ứng dụng với truy cập bất thường. |
| Role/permission changes | Ai vừa `GRANT`, `REVOKE`, `ALTER ROLE`? | Gắn change ID, người duyệt, effective identity và mốc UTC. |
| Superuser usage | Tài khoản quản trị có được dùng ngoài window hợp lệ không? | Cần alert và hậu kiểm, không chia sẻ account. |
| TLS/certificate events | Certificate sắp hết hạn, handshake failures, cipher policy vi phạm? | Alert sớm trước rotation/hết hạn. |
| `system_auth` health | Replica RF/repair/timeout và login failures có biến động không? | Khả năng đăng nhập mới phụ thuộc cả dữ liệu bảo mật. |
| JMX/OS management | Ai chạy `nodetool`, restart, sửa config hoặc truy cập snapshot? | CQL audit **không mặc nhiên** ghi đủ những thao tác này. |

Một số phiên bản Cassandra có cấu hình **audit logging** tích hợp, còn những bản khác cần kết hợp cơ chế của nền tảng, proxy hoặc collector. Audit events phải được bảo vệ khỏi chỉnh sửa/xóa, có **retention**, **mốc UTC/NTP**, redaction và lưu ra nơi độc lập với node. **Không bật log payload đầy đủ toàn traffic một cách mù quáng**: nó có thể gây I/O lớn và lộ thông tin nhạy cảm.

### 12.1. Ví dụ một bản ghi audit phù hợp

~~~text
change_id          = CHG-2026-11-21-SEC-03
actor              = db-admin-session-42
effective_identity = db-security-admin
cluster            = cassandra-prod
dc                 = dc1
operation          = GRANT_SELECT
resource           = telemetry_secure.events_by_device_day
target_role        = telemetry_day_reader
timestamp_utc      = 2026-11-21T10:00:00Z
execution_outcome  = success
verification       = allow/deny test passed
secret_recorded    = false
~~~

Đây là **cấu trúc audit do tổ chức thiết kế**, không phải schema bắt buộc của Cassandra. Giữ `execution_outcome` và `verification` **tách biệt**: lệnh `GRANT` thành công không chứng minh role hiệu lực đã đúng ở mọi coordinator sau cache; cần test theo policy.

## 13. Kịch bản triển khai: bật authn/authz trên cluster đang chạy

**Đây là thay đổi có nguy cơ khóa tất cả client khỏi cluster**, không phải một toggle có thể bật thử lúc cao điểm. Một kế hoạch tổng quát:

### Giai đoạn A — Khảo sát

1. Ghi **Cassandra version, JDK, mode triển khai** và config của mọi node/DC.
2. Kiểm tra `system_auth`, replication strategy/RF, trạng thái replica/repair, backup và khả năng khôi phục.
3. Lập inventory **mọi client**: Java Driver, cqlsh, monitoring, migration, Spark/analytics, backup, admin scripts và JMX.
4. Xác định role/permission tối thiểu theo bảng/keyspace và identity sẽ dùng cho từng client.
5. Đảm bảo TLS/certificate đã được thử nghiệm hoặc có kế hoạch chuyển tiếp bảo mật.
6. Thiết lập kênh **break-glass** và rollback, có thể dùng khi role/credential provisioning thất bại.

### Giai đoạn B — Chuẩn bị trên staging

1. Dựng topology và version gần production; thử bật authenticator, authorizer, role manager, TLS.
2. Provision admin và service identities an toàn; không hardcode password trong YAML, CI scripts hoặc ticket.
3. Kiểm tra role membership, các phép `SELECT`/`MODIFY` được phép và truy cập **bị từ chối**.
4. Test Java Driver với TLS, truststore, local DC và tái kết nối sau credential rotation.
5. Test node restart, DC failure simulation hợp lệ và mức độ sẵn sàng của `system_auth`.
6. Đo throughput, p95/p99, lỗi login/authorize và lượng cache/auth operations dưới tải phù hợp.

### Giai đoạn C — Rollout có kiểm soát

~~~mermaid
flowchart TD
    A["Inventory phiên bản, client, system_auth và TLS"] --> B["Thiết kế role + bootstrap/break-glass"]
    B --> C["Staging: allow/deny tests, driver, failure mode"]
    C --> D{"Đã chứng minh có đường admin và rollback?"}
    D -->|Không| E["Dừng, hoàn thiện test/recovery"]
    D -->|Có| F["Đổi cấu hình theo rolling plan của version"]
    F --> G["Kiểm tra authn + authz + TLS từ từng DC"]
    G --> H{"Ứng dụng/automation đăng nhập và có quyền đúng?"}
    H -->|Không| I["Dừng rollout; điều tra/rollback có kiểm soát"]
    H -->|Có| J["Mở rộng rollout, khóa đường mặc định"]
    J --> K["Giám sát, audit, thu hồi credentials tạm"]
~~~

Điểm đặc biệt:

- **Rolling restart** nếu phiên bản yêu cầu nhưng phải bảo toàn quorum/availability, tránh khiến nhiều replica cùng offline.
- Các node không nên ở trạng thái security policy khác nhau **lâu hơn mức cần thiết**; có thể tạo hành vi client không nhất quán hoặc khoảng trống kiểm soát.
- Kiểm tra từ **từng DC** và ít nhất hai loại identity (admin, application) thay vì chỉ từ máy triển khai.
- Đóng/mở firewall theo thứ tự an toàn; đừng khóa kênh break-glass trước khi có bằng chứng tất cả client phục vụ được.

### Giai đoạn D — Hậu kiểm và đóng change

Checklist sau rollout:

~~~text
[ ] Authenticator, Authorizer, RoleManager đúng cấu hình dự kiến trên các node.
[ ] Kết nối CQL không có danh tính hợp lệ bị từ chối theo policy.
[ ] Role đọc SELECT được, nhưng INSERT/DELETE/ALTER không được nếu chưa cấp.
[ ] Role ghi chỉ MODIFY đúng bảng; không có SUPERUSER ngoài mong đợi.
[ ] Authentication error/Unauthorized được phân biệt khỏi timeout/Unavailable.
[ ] TLS handshake xác thực server hoạt động; cert/truststore và expiry có giám sát.
[ ] system_auth RF/repair/health hợp lệ ở mỗi DC.
[ ] Các Java services, cqlsh, migration jobs và automation đã chuyển identity.
[ ] JMX/OS/backup paths vẫn được kiểm soát riêng; không có cổng admin public.
[ ] Audit log ghi role changes và failed access, không lộ secret.
[ ] Mật khẩu/đường bootstrap mặc định đã khóa theo runbook.
[ ] Credential tạm được thu hồi; có rollback/recovery đã kiểm chứng.
~~~

## 14. Phân biệt lỗi cấu hình, cache và lỗi cụm

| Triệu chứng | Giả thuyết cần ưu tiên | Hành động xác minh |
| --- | --- | --- |
| `cqlsh` vào được khi chưa cung cấp credential | `AllowAllAuthenticator`, proxy đã xác thực hộ hoặc đang nối nhầm cluster. | Kiểm tra endpoint thật, config effective, TLS, danh tính session và policy. |
| `SELECT` chạy, `INSERT` báo Unauthorized | Role chỉ có `SELECT` hoặc chưa được `MODIFY`. | `LIST ALL PERMISSIONS`, direct/inherited roles, đúng resource và user. |
| Vừa `REVOKE` nhưng một connection cũ vẫn truy cập được | Cache hiệu lực chưa hội tụ hoặc kết nối/session cũ. | Kiểm tra cache/connection lifecycle/version, test kết nối mới, thủ tục thu hồi khẩn cấp. |
| Đăng nhập lỗi trên một số node của DC2 | `system_auth` replication/repair, cache hoặc khác biệt cấu hình giữa node. | So RF/NTS, node health, auth logs, repair và effective config. |
| Sau bật TLS, Java báo certificate exception | CA/truststore/SAN/hostname không phù hợp. | Kiểm tra chứng chỉ thật và peer validation; **không dùng trust-all**. |
| Login ổn nhưng các request trả `Unavailable` | RF/CL/quorum hoặc node down. | `nodetool status`, keyspace RF và trạng thái replica. |
| Login/role checks chậm khi một DC đứt kết nối | Auth data/cache/replica hoặc network đang ảnh hưởng. | `system_auth`, metrics authentication và DC routing. |
| Thấy CQL role bị chặn nhưng `nodetool` vẫn chạy | JMX có đường bảo mật độc lập. | JMX authz, OS/bastion credentials, firewall và audit automation. |
| Một role ít quyền tạo/xóa bảng được | Quyền kế thừa từ role khác, resource quá rộng, superuser hoặc authorizer không bật. | Kiểm tra toàn bộ effective roles; chạy negative tests. |
| Audit không thấy thao tác SSH sửa YAML | CQL audit không bao phủ OS/JMX. | Đối chiếu bastion/OS/CI/CD session logs. |

**Nếu mất quyền admin:** không xóa/sửa trực tiếp `system_auth` để thử “reset”; dùng runbook khôi phục của đúng phiên bản/phân phối, backup, snapshot và người phê duyệt. Tùy sự cố, phải phục hồi khả năng truy cập trước khi đổi bất kỳ tham số auth nào khác.

## 15. Security, query design và tính sẵn sàng liên hệ ra sao?

### 15.1. Authorization không chữa truy vấn tốn tài nguyên

Một tài khoản `SELECT` hợp lệ có thể gửi:

~~~sql
-- PHẢN MẪU: không chạy trên bảng dữ liệu lớn.
SELECT *
FROM telemetry_secure.events_by_device_day
WHERE event_type = 'temperature'
ALLOW FILTERING;
~~~

Truy vấn thiếu `(device_id, event_day)`, nên không phải partition lookup; có thể bị từ chối hoặc phải quét nhiều dữ liệu tùy bản Cassandra và execution plan. Việc một identity **được phép đọc bảng** không có nghĩa mọi kiểu query trên bảng là **an toàn về capacity**.

Vì thế security phải đi kèm:

- Thiết kế **partition key theo truy vấn**, bucketing dữ liệu time-series, giới hạn clustering ranges.
- Rate limiting, bounded concurrency, request timeout và guardrails.
- Tracing/metrics có chọn lọc để phát hiện hot partition/tombstone scan.
- Phân quyền theo **bảng phục vụ riêng** cho từng ứng dụng/tenant khi policy yêu cầu.

### 15.2. Consistency level không ảnh hưởng quyền

Với RF = 3 trong `dc1`, `LOCAL_QUORUM` yêu cầu hai replica phản hồi. Một identity không có `SELECT` vẫn bị Unauthorized dù dùng `LOCAL_ONE`, `QUORUM` hay `ALL`. Ngược lại, nếu đã có `SELECT`, request vẫn có thể timeout do replica/GC/network.

~~~text
Authentication: User X có hợp lệ không?
Authorization : User X có SELECT trên telemetry_secure.events_by_device_day không?
Routing       : Partition key → token → natural replicas nào?
Consistency   : Bao nhiêu phản hồi cần để hoàn tất request?
Encryption    : Dữ liệu/credential có được bảo vệ khi truyền không?
~~~

Không thể thay một lớp bằng lớp khác. Chẳng hạn nới timeout không sửa permission denied; tăng RF không bảo vệ mật khẩu; bật TLS không ngăn account superuser xóa bảng.

### 15.3. Backup và multi-DC là phần của an ninh dữ liệu

Replication giữa DC giúp phục vụ khi một nơi gặp sự cố; **không bảo vệ chắc chắn trước thao tác `DELETE` sai** được phân tán tới các replica. Snapshot và backup phải có:

- Identity truy cập tách khỏi workload, **mã hóa tại chỗ lưu**, bảo vệ key và giới hạn quyền xóa.
- Retention/immutability theo yêu cầu, audit truy cập và kiểm chứng backup export.
- Thử restore trên môi trường cô lập, không chỉ tạo snapshot trên cùng volume Cassandra.
- Xem xét quyền xem dữ liệu trong backup tương đương quyền đọc dữ liệu ở bảng nguồn.

**Không coi backup là ngoại lệ khỏi RBAC và kiểm toán**: file SSTable có thể chứa nhiều dữ liệu nhạy cảm dù client CQL đã bị giới hạn.

## 16. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một cluster bật TLS native transport và có RF = 3, nhưng `authenticator` là `AllowAllAuthenticator` và `authorizer` là `AllowAllAuthorizer`. Có thể nói dữ liệu đã được bảo vệ theo role người dùng không?

**Đáp án:** **Không.** TLS bảo vệ đường truyền, RF bảo vệ phân tán dữ liệu, nhưng chưa có kiểm tra danh tính/permissions như mô hình RBAC mong muốn. Phải chọn cơ chế authn/authz phù hợp và kiểm thử thực.

**Bài 2.** `events_reader` có `SELECT` trên một bảng, `LOGIN = false`. Role đó có phải tài khoản dịch vụ Java đăng nhập trực tiếp không?

**Đáp án:** **Không.** Nó là role nhóm không cho login. Cần identity đăng nhập đã provisioning và được `GRANT events_reader TO identity`.

**Bài 3.** Identity `api_v1` chỉ được `SELECT` trên `ks.tbl`, nhưng thực tế vẫn `DELETE` thành công. Kể hai nguyên nhân khả dĩ.

**Đáp án:** Có thể có **`MODIFY` kế thừa/cấp trực tiếp ở cấp rộng hơn**, identity là superuser, hoặc authorizer không được cấu hình/thực thi như dự kiến. Phải xem effective permissions và test bằng đúng identity.

**Bài 4.** Một người sửa `system_auth` từ RF = 1 lên RF = 3 bằng `ALTER KEYSPACE`. Có được khẳng định ngay mọi node đã lưu đủ roles và permissions không?

**Đáp án:** **Không.** Thay RF metadata **không tự bảo đảm dữ liệu cũ đã đến replica mới**. Cần quy trình transfer/repair thích hợp và kiểm chứng đăng nhập/permissions trên các node/DC.

**Bài 5.** Java client nhận TLS handshake exception vì CA nội bộ chưa có trong truststore. Có nên bật trust-all để kết nối nhanh?

**Đáp án:** **Không.** Cần cấu hình truststore/CA/SAN và policy xác thực server chính xác. Trust-all làm mất cơ chế xác thực peer và có nguy cơ bị giả mạo endpoint.

**Bài 6.** Một role vừa bị `REVOKE`, nhưng kết nối client đã mở trước đó vẫn chạy được một thao tác. Điều này có nhất thiết chứng minh lệnh REVOKE không chạy?

**Đáp án:** **Không.** Authorization cache, phiên kết nối và sự hội tụ giữa node có thể ảnh hưởng thời điểm chính sách có hiệu lực. Cần test trên kết nối mới, đối chiếu effective roles/cache và áp runbook thu hồi khẩn cấp nếu cần.

**Bài 7.** `cqlsh` báo Unauthorized khi `ALTER TABLE`, nhưng engineer vẫn chạy được `nodetool repair`. Vì sao?

**Đáp án:** `ALTER TABLE` đi qua **CQL RBAC**; `nodetool repair` thường qua **JMX** với cơ chế authz/OS/network riêng. Một kênh bị chặn không chứng minh kênh khác bị chặn.

**Bài 8.** Service A và Service B cùng dùng một password superuser. A bị lộ credential. Vì sao việc rotate gây rủi ro vận hành?

**Đáp án:** Hai service chia sẻ identity nên không thể thu hồi riêng A mà không ảnh hưởng B; khó quy trách nhiệm và khó phối hợp connection restart. Nên chuyển sang identity riêng, least privilege và secret manager.

**Bài 9.** Một role có `SELECT` trên `telemetry_secure.events_by_device_day`. Query thiếu partition key và dùng `ALLOW FILTERING` trở nên rất chậm. Đây là lỗi authentication hay query modeling?

**Đáp án:** Đây là vấn đề **query modeling/resource usage**, không phải xác thực. Role có thể được phép đọc nhưng query vẫn cần partition key, clustering range, guardrail và rate limiting phù hợp.

**Bài 10.** Khi chuyển cấu hình auth trên cluster hai DC, vì sao cần thử login từ cả hai DC, kể cả khi `nodetool status` đều `UN`?

**Đáp án:** Membership `UN` không chứng minh `system_auth` đã có replica/repair đúng, mọi node dùng cùng security config, certificate/trust đúng hay cache permissions đã hội tụ. Login và allow/deny tests là hậu điều kiện riêng.

## 17. Checklist cuối bài và cây quyết định

~~~mermaid
flowchart TD
    A["Thiết kế bảo mật Cassandra"] --> B["Xác định version, edition, cluster topology"]
    B --> C["Chọn Authenticator + Authorizer + RoleManager"]
    C --> D["Kiểm tra system_auth RF/repair ở từng DC"]
    D --> E["Bật và kiểm chứng TLS client/internode"]
    E --> F["Tạo identity riêng + role least privilege"]
    F --> G["Test allow/deny qua cqlsh và Java Driver"]
    G --> H{"Đúng quyền, đúng endpoint và không gián đoạn?"}
    H -->|Không| I["Dừng rollout, kiểm tra config/cache/replica/TLS"]
    I --> G
    H -->|Có| J["Khóa default admin, audit, rotate và giám sát"]
    J --> K["Định kỳ review roles, restore và incident response"]
~~~

~~~text
[ ] Đã ghi chính xác phiên bản Cassandra/JDK/driver và loại triển khai.
[ ] Biết cơ chế authenticator, authorizer, role manager đang active.
[ ] Không dựa vào AllowAll trong production có yêu cầu RBAC.
[ ] CQL native transport dùng TLS với kiểm tra CA/SAN/hostname đúng.
[ ] Internode/JMX/OS/backup security được xét riêng, không chỉ CQL.
[ ] system_auth RF, DC/rack, health và repair đáp ứng availability mục tiêu.
[ ] Mỗi service có identity riêng, không đăng nhập bằng superuser.
[ ] Role nhóm LOGIN=false; quyền SELECT/MODIFY đúng bảng/keyspace.
[ ] Đã kiểm tra cả allow và deny bằng role thật, cả direct/inherited rights.
[ ] Đã tính đến auth/permission cache và existing connection khi REVOKE.
[ ] Không ghi password, certificate private key hoặc access token vào log/CI.
[ ] Có audit role changes, failed logins, JMX/OS actions và UTC timeline.
[ ] Có quy trình credential rotation, khóa bootstrap và break-glass.
[ ] Rollout đã thử staging/canary và rollback, không đổi hàng loạt mù quáng.
[ ] Backup và dữ liệu nhạy cảm được bảo vệ cả khi export/restore.
~~~

**Kết luận:** Trong Cassandra, **authentication** trả lời *ai đang kết nối*, **authorization** trả lời *được phép làm gì trên tài nguyên nào*, còn **TLS** và **audit** bảo vệ đường truyền và khả năng truy vết. Cấu hình phải được **đối chiếu đúng phiên bản**, không chỉ copy ba dòng `cassandra.yaml`. Những thành phần đặc thù của hệ phân tán — **`system_auth`, RF theo datacenter, replica health, cache và connection lifecycle** — quyết định việc đăng nhập và thu hồi quyền có đáng tin cậy hay không. Một triển khai tốt kết hợp **least privilege, identity riêng, TLS xác thực peer, hậu kiểm allow/deny, kiểm toán và khả năng khôi phục**, đồng thời không nhầm CQL RBAC với quyền JMX hay hệ điều hành.
