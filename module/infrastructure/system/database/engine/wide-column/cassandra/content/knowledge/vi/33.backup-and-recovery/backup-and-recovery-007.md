# Sao lưu schema, cấu hình, system_auth và khóa/chứng thư liên quan

> **Chương:** Sao lưu và phục hồi  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — kiến trúc phân tán, mô hình wide-column và vận hành Apache Cassandra: partition key, bảng thiết kế theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, khắc phục lỗi và kết nối Java.

Khi nhắc đến backup Apache Cassandra, nhiều người chỉ nghĩ tới **SSTable của các bảng nghiệp vụ**. Nhưng khôi phục được hàng dữ liệu mà **không có định nghĩa bảng**, **không dựng lại được datacenter/rack**, **không có quyền đăng nhập**, hoặc **không còn khóa TLS/KMS** thì hệ thống vẫn có thể không phục vụ ứng dụng.

Bài này trình bày cách lập **bộ sao lưu có khả năng phục hồi** gồm: (1) schema CQL, (2) cấu hình node và topology, (3) metadata xác thực/phân quyền — đặc biệt keyspace `system_auth` khi dùng các cơ chế nội bộ Cassandra, và (4) khóa riêng, chứng thư, truststore/keystore cùng phụ thuộc bí mật liên quan. Trọng tâm không phải sao chép mọi thư mục rồi coi là xong, mà là **chứng minh có thể dựng lại một cluster thử nghiệm theo thứ tự đúng** và bảo vệ dữ liệu nhạy cảm trong suốt vòng đời backup.

> **An toàn:** Ví dụ lệnh thao tác chỉ dành cho môi trường lab có quyền quản trị. Backup `system_auth` và private key có thể tạo ra một bản sao thông tin có đặc quyền rất cao. Không tải chúng lên kho chia sẻ công khai, không đưa mật khẩu vào shell history, tài liệu Markdown, ticket hoặc log, và không thử restore trực tiếp lên cụm production đang hoạt động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Liệt kê các thành phần cần sao lưu ngoài dữ liệu nghiệp vụ, giải thích **mỗi thành phần phục hồi chức năng gì**.
2. Xuất schema CQL, đối chiếu DDL với topology và nhận biết giới hạn của `DESCRIBE SCHEMA`.
3. Lập inventory cấu hình quan trọng (replication, snitch/DC/rack, JVM, native transport, commit log, compaction, auth, TLS) mà không đưa bí mật vào tài liệu thường.
4. Hiểu vì sao `system_auth` chứa dữ liệu xác thực/phân quyền, được replication và phục hồi **khác** các bảng nghiệp vụ.
5. Phân biệt chứng thư public, **private key**, keystore, truststore, passphrase và khóa KMS; thiết kế sao lưu, phân quyền, luân chuyển và khôi phục riêng cho chúng.
6. Thiết lập manifest/kiểm tra checksum và restore drill dựa trên RPO, RTO, chứng minh ứng dụng Java có thể xác thực qua TLS và đọc/ghi sau phục hồi.

## 2. Khôi phục Cassandra thực sự cần những lớp nào?

### 2.1. Bốn lớp không thay thế nhau

| Lớp | Thành phần điển hình | Nếu thiếu khi restore | Nên kiểm chứng bằng |
|---|---|---|---|
| **Schema CQL** | Keyspace, RF/strategy, table, UDT, indexes/SAI, materialized views, functions/aggregates, thuộc tính TTL/compaction | Có byte SSTable nhưng schema không phù hợp, loader không biết kiểu dữ liệu hoặc truy vấn không chạy | `DESCRIBE KEYSPACE`, `system_schema`, ứng dụng chạy truy vấn |
| **Cấu hình vận hành** | `cassandra.yaml`, snitch/DC/rack, JVM/options, endpoint, TLS/auth, log, đường data/commitlog | Node không join đúng DC/rack, RF sai, không bind port hoặc bật sai security policy | `nodetool status`, `describecluster`, kiểm tra cấu hình theo release |
| **Identity và authorization** | `system_auth` với CassandraRoleManager/CassandraAuthorizer, roles, memberships, grants; backend bên ngoài nếu dùng | Administrator/service account mất quyền hoặc truy cập sai chính sách | `LIST ROLES`, `LIST ALL PERMISSIONS`, test quyền thực |
| **Crypto/secrets** | Private key, certificate chain/CA, keystore/truststore, mật khẩu, KMS/key-encryption material | Client/node TLS handshake thất bại; có thể không giải mã dữ liệu đã mã hóa | TLS handshake có xác minh, kiểm tra expiry/chain/permissions |

Đây là các **lớp khôi phục độc lập nhưng có thứ tự phụ thuộc**. Backup SSTable không tự chứa tất cả bí mật cấu hình; bản xuất CQL schema không tự sao lưu mật khẩu/role grants; một chứng thư public không thay thế private key; có file cấu hình nhưng không có thư mục khóa vẫn khiến node không thể khởi động với TLS bắt buộc.

~~~mermaid
flowchart TD
    A["Bản sao lưu Cassandra có thể phục hồi"] --> B["1. Schema CQL / metadata"]
    A --> C["2. Config node, DC/rack và RF"]
    A --> D["3. system_auth hoặc IdP/ACL backend"]
    A --> E["4. Chứng thư, private key và secrets"]
    A --> F["5. SSTable dữ liệu / backup bổ sung"]
    B --> G["Restore drill trên cluster cô lập"]
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H["Kiểm tra schema, auth, TLS, CL, ứng dụng Java"]
~~~

### 2.2. “Backup thành công” khác “phục hồi thành công”

Một snapshot được tạo và có thể liệt kê chưa chứng minh rằng **toàn bộ tập dữ liệu**, **khóa giải mã**, **mật khẩu bootstrap** và **schema cùng thời điểm** đã nằm trong kho lưu trữ. Cần định nghĩa trước:

- **RPO (Recovery Point Objective):** tối đa mất bao nhiêu dữ liệu/thay đổi cấu hình sau điểm khôi phục. Ví dụ RPO 15 phút cho nghiệp vụ không thể được bảo đảm chỉ bằng snapshot mỗi ngày.
- **RTO (Recovery Time Objective):** thời gian tối đa cần có để cluster và ứng dụng phục vụ lại, **bao gồm khởi động node, stream/repair, khôi phục auth và kiểm thử**.
- **Phạm vi thảm họa:** một SSTable hỏng, mất một node, mất toàn DC, xóa nhầm bảng/keyspace, mất hệ thống quản lý khóa, hay bị lộ private key.
- **Điểm nhất quán của backup:** schema/auth có thể thay đổi trong khi SSTable đang được chụp. Snapshot từng node không tự tạo **giao dịch chụp toàn cluster tại đúng một thời điểm**.

Nếu schema và grants bị thay đổi liên tục qua IaC/migrations, lịch sao lưu cần kết hợp **event-driven export sau thay đổi** cùng snapshot định kỳ, không chỉ chạy cron chung cho tất cả thành phần.

## 3. Sao lưu schema: định nghĩa để giải mã và truy vấn đúng dữ liệu

### 3.1. Cần ghi lại những thuộc tính nào?

**Keyspace:** tên, replication class (như `NetworkTopologyStrategy`), RF **theo từng datacenter**, `durable_writes`. Chỉ ghi RF=3 mà không ghi tên DC là chưa đủ.

**Tables:** danh sách cột/kiểu, partition key và thứ tự clustering columns, `CLUSTERING ORDER BY`, compaction strategy, compression codec/chunk size, `default_time_to_live`, `gc_grace_seconds`, caching, speculative retry và các tùy chọn tùy phiên bản.

**Đối tượng phụ thuộc:** user-defined types (UDT), indexes (2i/SAI), materialized views, user-defined functions/aggregates và những đối tượng ứng dụng sử dụng trong phiên bản đó. Các thành phần có thể yêu cầu build/rebuild sau restore và có thứ tự phụ thuộc.

**Version compatibility:** export DDL từ Cassandra 5.x không nhất thiết chạy nguyên vẹn trên 3.11/4.0: tên property, index implementation, compaction option và tính năng CQL khác nhau. Cần lưu **Cassandra release và định dạng SSTable** bên cạnh schema.

### 3.2. Xuất DDL bằng cqlsh

Ví dụ trong **terminal an toàn của lab**, giả định có cấu hình kết nối/auth được bảo vệ riêng thay vì ghi mật khẩu trong command:

~~~bash
# Xuất tất cả schema có thể mô tả từ cqlsh.
cqlsh -e "DESCRIBE SCHEMA" > schema-export.cql

# Hoặc chỉ một keyspace nghiệp vụ đã xác định.
cqlsh -e "DESCRIBE KEYSPACE shop_lab" > shop-schema.cql
~~~

`DESCRIBE SCHEMA` là lệnh hỗ trợ của **cqlsh**, không phải câu truy vấn CQL có thể truyền trực tiếp qua Java Driver. Nó tạo dạng DDL có thể đọc và lưu phiên bản; cách cqlsh trình bày hoặc phạm vi xuất phụ thuộc release. **Không coi DDL export là backup dữ liệu**: nó không chứa các hàng nghiệp vụ, các byte SSTable, chứng thư hay toàn bộ trạng thái roles/grants.

Khi cluster có auth, dùng cơ chế client config, secret injection hoặc môi trường dành riêng với file permissions phù hợp. Tránh `cqlsh -p <password>` vì argument có thể lưu trong history/process list.

Trong `cqlsh` có thể kiểm tra trực tiếp:

~~~sql
SELECT release_version FROM system.local;

SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop_lab';
~~~

Kết quả `system_schema.keyspaces` hữu ích để đối chiếu keyspace, nhưng **không thay thế DDL đầy đủ** của tables/indexes/UDTs. Có thể kiểm tra schema agreement bằng `nodetool describecluster` trước lúc export; nếu cluster đang bất đồng schema, không coi một node được hỏi là đại diện cho tất cả.

### 3.3. Ví dụ DDL cho lab và thứ tự phục hồi

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS shop_lab.orders_by_customer_month (
    customer_id uuid,
    month_bucket int,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
  AND gc_grace_seconds = 864000;
~~~

Đây chỉ là ví dụ nếu DC tên `dc1` có đủ node; sửa RF và topology theo lab. Khi phục hồi:

1. Dựng cluster và hệ thống identity/certificates cần thiết để có thể kết nối quản trị.
2. Tạo **UDT và schema theo thứ tự phụ thuộc**, tạo keyspace/table với định nghĩa phù hợp SSTable/loader.
3. Khôi phục dữ liệu và các đối tượng cần build/index theo runbook phiên bản.
4. Đối chiếu bảng được phục hồi, partition/clustering key, RF/CL và tính đúng của truy vấn.

**Đừng dùng `IF NOT EXISTS` để tuyên bố schema đã khôi phục đúng:** nếu bảng tồn tại nhưng khác khóa chính hoặc compression property, CQL sẽ không sửa nó. Cần so sánh export với schema thực tế và xử lý mismatch rõ ràng.

## 4. Sao lưu cấu hình: giữ được topology và hành vi của node

### 4.1. Inventory ngoài `cassandra.yaml`

Tên file/vị trí thay đổi theo cách cài đặt (package, container, Kubernetes, service manager và release). Hãy thu thập **cấu hình thực được triển khai**, không chỉ template trong Git.

| Nhóm | Thí dụ cần ghi | Tại sao khi restore cần |
|---|---|---|
| Cluster identity/topology | `cluster_name`, seed providers, listen/rpc/broadcast addresses, snitch, DC/rack | Node join đúng cụm/ring và vị trí replica |
| Replication | Keyspace RF theo DC; trạng thái topology/node tokens | Tránh vô tình thiếu replica hoặc đặt dữ liệu sai DC |
| Data paths | data file, commitlog, saved caches, hints directories; mount points | Node tìm đúng ổ/đường lưu trữ và có đủ dung lượng |
| JVM và hệ điều hành | Java version, heap, GC, `jvm.options`, sysctl, file limits, timezone/NTP | Giữ hành vi latency/GC và khả năng mở file |
| Read/write tuning | Compaction, memtable/flush, compression, cache, commitlog sync | Tránh thay durability hay chi phí I/O sau phục hồi |
| Client/network | native transport port, internode port, firewall, DNS, routing/load balancer | Ứng dụng kết nối và node trao đổi với nhau |
| Security | authenticator, authorizer, role manager, TLS encryption options, secret references | Phục hồi cơ chế đăng nhập, phân quyền và mã hóa |
| Observability | exporter/JMX configs, logging, alerting, backup schedules, repair runbooks | Có thể phát hiện lỗi và tiếp tục backup sau restore |
| Triển khai | manifests/Helm/IaC, package version, image digest, scripts, secret mounting | Dựng lại cùng release và cấu hình lặp lại được |

**Điều không nên làm:** sao chép nguyên metadata `system.local`, `system.peers` hoặc dữ liệu trạng thái ring của một node cũ lên node replacement rồi giả định cluster sẽ nhận như node mới. Những metadata này gắn với host ID, tokens, gossip và topology; **phục hồi node** phải dùng quy trình bootstrap/replace đúng release, không clone mù quáng thư mục hệ thống.

### 4.2. File cấu hình điển hình và thông tin dễ thất lạc

Các file có thể nằm trong thư mục cấu hình Cassandra hoặc mount từ hệ điều phối:

~~~text
cassandra.yaml                 # keyspace-independent settings, auth, TLS, endpoints
cassandra-rackdc.properties     # DC/rack khi dùng GossipingPropertyFileSnitch
cassandra-topology.properties   # topology nếu triển khai theo loại snitch tương ứng
cassandra-env.sh / jvm.options  # JVM/heap, phiên bản và cách khởi động
logback.xml                     # logging; cần kiểm soát lộ secrets trong log
cqlshrc / client trust config   # cấu hình client quản trị hoặc kết nối
deployment manifests / Helm    # volumes, secret references, service identity
~~~

Danh sách chỉ là **inventory gợi ý**: không phải cụm nào cũng dùng tất cả file. Ở Kubernetes, giá trị có thể xuất hiện dưới ConfigMap/Secret, operator CRD, environment variables và hệ thống quản lý bí mật bên ngoài; cần sao lưu định nghĩa lẫn cách phục hồi nguồn secret của chúng.

Không để file cấu hình chứa mật khẩu keystore/truststore nằm chung một kho plaintext với private key. Có thể lưu **bản config đã che bí mật** trong artifact triển khai và lưu **bí mật thật** trong secret manager/backup mã hóa riêng. Nhưng khi test restore, phải chứng minh hai nguồn có thể được kết hợp lại.

### 4.3. Ghi nhận metadata cluster ở thời điểm backup

Các lệnh **đọc trạng thái** hữu ích trên node được phép:

~~~bash
nodetool status
nodetool describecluster
nodetool version
nodetool info
~~~

Ghi lại metadata release, cluster name, các node/DC/rack, role và RF của keyspace, snapshot tag, lịch repair. `nodetool status` thể hiện một góc nhìn của cluster ở thời điểm hỏi; nếu đang bootstrap/decommission/move tokens, **hoãn backup dùng làm recovery baseline** hoặc đánh dấu rõ trạng thái chuyển tiếp.

## 5. system_auth: bảo vệ danh tính và quyền truy cập

### 5.1. system_auth giữ cái gì?

Khi sử dụng cơ chế xác thực/phân quyền tích hợp như `PasswordAuthenticator`, `CassandraRoleManager` và `CassandraAuthorizer`, keyspace `system_auth` lưu thông tin tương ứng như **roles, quyền đăng nhập, biểu diễn mật khẩu đã băm, membership và grants**. Các bảng nội bộ có thể khác giữa release, nên không phụ thuộc vào danh sách bảng hard-code trong bài học.

| Thành phần | Vai trò | Mức độ nhạy cảm |
|---|---|---|
| Roles/login metadata | Danh tính có được phép đăng nhập, vai trò quản trị | Cao: lộ cấu trúc account và quyền |
| Password hashes/credential metadata | Kiểm tra xác thực | **Rất cao**: hash cũng là dữ liệu bảo mật, không phải public |
| Role memberships | Vai trò thừa kế đặc quyền | Cao: có thể vô tình khôi phục quyền quá rộng |
| Resource permissions/grants | Ai được SELECT/MODIFY/ALTER/... trên keyspace/table | Cao: mất quyền có thể gây outage; thừa quyền gây rủi ro |
| Permission cache tại node | Tăng tốc xác thực/phân quyền, có hạn hiệu lực | Không phải bản sao lưu bền vững |

Nếu triển khai xác thực **ngoài Cassandra** (LDAP/Kerberos/cloud IAM/custom role manager), `system_auth` **có thể không chứa toàn bộ nguồn sự thật của danh tính/quyền**. Cần sao lưu cấu hình/bindings bên ngoài và cách khôi phục IdP/KMS tương ứng; không suy rằng snapshot `system_auth` đã giải quyết toàn bộ xác thực.

### 5.2. Replication của system_auth là cấu hình cần kiểm tra riêng

Các keyspace hệ thống có chính sách replication và quy trình quản lý khác bảng nghiệp vụ. `system_auth` trong nhiều triển khai bắt đầu với replication mặc định không phù hợp cho production (ví dụ RF thấp); cần kiểm tra và thiết lập đúng trên cluster nhiều node/DC theo hướng dẫn phiên bản.

Trong `cqlsh` với quyền hợp lệ:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'system_auth';
~~~

Ví dụ **chỉ để minh họa** cấu hình mong muốn cho DC có tên `dc1` và ba replica thực:

~~~sql
-- KHÔNG chạy trên production khi chưa có kế hoạch thay đổi RF.
ALTER KEYSPACE system_auth
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

**Lưu ý quan trọng:** thay RF là sửa metadata; nó **không tự bảo đảm** mọi replica mới đã có đầy đủ dữ liệu `system_auth`. Sau thay đổi cần quy trình đồng bộ/repair, xác minh hoạt động auth và rollback/break-glass theo release. Với multi-DC, khai báo RF theo **từng DC thật**, cân nhắc yêu cầu sẵn sàng đăng nhập ngay cả khi một DC lỗi.

### 5.3. Kiểm tra logic roles/grants trước khi chụp

Các câu lệnh quản trị của CQL/cqlsh:

~~~sql
-- Cần quyền phù hợp; không nhúng mật khẩu trong ví dụ.
LIST ROLES;
LIST ALL PERMISSIONS;
~~~

Nếu permissions bị giới hạn, kết quả có thể chỉ bao gồm các vai trò/quyền mà tài khoản hiện tại được phép xem. Một bản export text được ghi **không đồng nghĩa đầy đủ** với snapshot database nội bộ, đặc biệt khi có thay đổi đồng thời hoặc cơ chế auth tùy biến.

Mục tiêu của bản kiểm tra logic là lưu danh mục role/service accounts, role memberships và quyền đã phê duyệt — **không xuất mật khẩu hoặc hash ra tài liệu thường**. Tránh dùng `SELECT * FROM system_auth.roles` trong tài liệu/pipeline chung vì có thể vô tình lộ hash/metadata nhạy cảm.

### 5.4. Snapshot system_auth trên từng node liên quan

Với quyền hệ điều hành được ủy quyền, ví dụ lệnh tạo snapshot trên **node hiện tại**:

~~~bash
# Kiểm tra cú pháp release trước khi thao tác:
nodetool help snapshot

# Ví dụ trong cluster lab, tag theo mốc thời gian:
nodetool snapshot -t auth_lab_20261121 system_auth

# Kiểm tra snapshot đang có:
nodetool listsnapshots
~~~

`nodetool snapshot` tạo hard links/copies theo cơ chế SSTable snapshot **trên node được điều khiển**, không phải một snapshot phân tán đồng bộ trên mọi node. Nếu cần bản sao của `system_auth` trên các replica liên quan, thực hiện theo kế hoạch nhiều node và ghi tag, host ID, token/ranges, keyspace/table, timestamp cùng trạng thái schema/repair.

**Hard link snapshot trên cùng volume không phải backup ngoài site.** Ổ đĩa hỏng, ransomware hoặc mất node vẫn có thể làm cả SSTable lẫn snapshot biến mất. Phải chuyển bản sao phù hợp sang storage ngoài cluster, bảo vệ bằng encryption và quyền truy cập tối thiểu, rồi **kiểm tra có thể khôi phục**.

Vì auth metadata có thể được ghi trong lúc snapshot nhiều node, không suy các bản chụp là **một giao dịch đồng thời**. Trong quy trình nghiêm ngặt, cần cửa sổ kiểm soát thay đổi roles/grants, metadata manifest và đối chiếu lại sau backup.

### 5.5. Khi restore system_auth, rủi ro chính là gì?

- **Mất quyền truy cập:** role admin/service account không có trong bản phục hồi, mật khẩu khác hoặc permissions thiếu khiến không thể kết nối/khởi động phần ứng dụng.
- **Khôi phục quyền quá rộng:** snapshot cũ chứa tài khoản đã bị thu hồi hoặc grants không còn hợp lệ, vô tình mở lại quyền.
- **Sai topology/RF:** dữ liệu auth chỉ được nạp ở một replica/DC hoặc CL không đáp ứng, dẫn tới đăng nhập hoạt động lúc được lúc không.
- **Cache quyền stale:** role/permission cache ở các node có thời hạn; thay đổi trực tiếp file SSTable mà không theo runbook có thể làm hành vi không nhất quán.
- **Không tương thích release/backend:** nội bộ schema `system_auth`, hash format và auth implementation có thể đổi; restore snapshot cross-version cần kế hoạch hỗ trợ chính thức.

**Không chạy `DROP KEYSPACE system_auth`, `TRUNCATE system_auth.*`, chép SSTable bằng tay vào cụm đang phục vụ, hay bật/tắt auth để “đăng nhập lại cho nhanh”.** Phục hồi `system_auth` cần **runbook được kiểm thử riêng cho Cassandra release và cơ chế authentication/authorization đang dùng**, thường trên cluster cô lập trước, với tài khoản quản trị khẩn cấp/break-glass được bảo vệ ngoài bản snapshot.

## 6. Khóa, chứng thư và bí mật: phần backup phải được khóa chặt nhất

### 6.1. Phân biệt các loại vật liệu mã hóa

| Vật liệu | Chứa gì? | Có thể công bố? | Phải có để phục hồi? |
|---|---|---|---|
| **Server certificate** | Public key và identity của node/server, thời hạn, chữ ký CA | Thường có thể chia sẻ theo chính sách nội bộ | Cần chứng thư hợp lệ phù hợp endpoint |
| **Private key** | Khóa ký/chứng minh danh tính, giải mã/khởi tạo khóa phiên tùy giao thức | **Tuyệt đối không công bố** | Cần key hợp lệ tương ứng cert hoặc cấp lại thay thế |
| **CA certificate/chain** | Certificate chain để kiểm tra độ tin cậy | Public nhưng vẫn quản lý nguồn tin cậy | Client/node cần trust anchor phù hợp |
| **Keystore** | Container chứng thư và có thể chứa private key | Nhạy cảm nếu có private key | Cần hoặc có thể tái tạo qua cấp lại key/cert |
| **Truststore** | Danh sách CA/cert được tin cậy | Thường không chứa private key nhưng là cấu hình bảo mật | Cần để xác thực peer/CA đúng |
| **Passphrase/keystore password** | Mở container/bảo vệ key | **Bí mật** | Cần để dùng bản key lưu hoặc được thay bằng secret mới |
| **KMS/HSM key hoặc key reference** | Root/master/data-encryption keys và policy | **Rất nhạy cảm**; có key không xuất được | Phải còn đường giải mã và cấp quyền phù hợp |

**Điểm sống còn:** sao lưu **chứng thư public nhưng mất private key** không đủ để node chứng minh danh tính; sao lưu **SSTable đã mã hóa** nhưng mất data-encryption key cũng không khôi phục được dữ liệu. Đối với HSM/KMS **không cho export key**, phương án đúng có thể là backup policy, replication của KMS, tài khoản break-glass và khả năng restore trong vùng/tenant mới — chứ không “xuất file private key bằng mọi giá”.

### 6.2. Hai đường TLS khác nhau

Cassandra có cấu hình mã hóa cho:

1. **Client-to-node** (native protocol): driver Java/cqlsh xác thực chứng thư node, có thể cần mutual TLS; thường liên quan `client_encryption_options`.
2. **Node-to-node** (internode): các node xác thực và mã hóa giao tiếp tùy cấu hình; thường liên quan `server_encryption_options`.

Không tự cho rằng một keystore/truststore có thể thay thế cho cả hai. Mỗi đường có thể dùng CA, SAN, certificate rotation và yêu cầu client-auth khác nhau. Cần lưu **inventory mapping**:

~~~text
Node A, dc1/rack1:
  internode certificate identity -> secret ref: cassandra/dc1/A/internode
  native transport certificate   -> secret ref: cassandra/dc1/A/client
  trusted CA chain               -> trust bundle version: vN
  renewal owner/expiry           -> theo inventory PKI
  key material                   -> secret manager/KMS, KHÔNG đưa vào manifest plaintext

Java service orders-api:
  trust bundle reference         -> app/orders-api/cassandra-ca
  client identity (nếu mTLS)     -> app/orders-api/client-key
~~~

Trong manifest thường, chỉ lưu **đường tham chiếu** hoặc ID, fingerprint public cert, issuer, SAN, expiry, phiên bản và nơi cấp lại. Không điền private key, passphrase, secret token hoặc kube Secret đã giải mã.

### 6.3. Cấp lại khác với khôi phục nguyên private key

Tùy chính sách PKI, khi mất certificate trên một node có thể:

- **Khôi phục bản private key từ backup được kiểm soát** nếu cần giữ nguyên identity và key chưa bị lộ.
- **Cấp key pair/chứng thư mới** với SAN và trust chain phù hợp nếu PKI cho phép; cập nhật keystore/truststore, node, Java clients và các kết nối mTLS liên quan.
- **Thu hồi (revoke) và thay thế** chứng thư/key nếu nghi đã bị lộ. Không phục hồi lại một private key đã bị xem là bị xâm phạm chỉ vì backup vẫn dùng được.

Nếu cluster dùng envelope encryption cho dữ liệu lưu trữ, việc xoay TLS cert **không** khôi phục được khóa mã hóa dữ liệu. Phải phân biệt TLS transport identity với at-rest encryption keys và cơ chế KMS riêng.

### 6.4. Bảo vệ bản sao lưu bí mật

Áp dụng đồng thời:

- Encryption at rest và khi truyền; lưu bản backup ở vị trí tách khỏi cluster, quản lý key mã hóa backup bằng hệ thống riêng, có kế hoạch khôi phục key.
- IAM theo **least privilege**, tách người đọc backup chứa private key/system_auth khỏi người chỉ cần schema hoặc log; ghi audit truy cập và mọi lần restore.
- Lịch rotation, revocation, expiry monitoring; không để chứng thư backup quá cũ trở thành phương án restore duy nhất.
- Bản sao **immutable/offline** theo yêu cầu chống ransomware, retention rõ ràng, xóa/huỷ an toàn khi hết thời gian.
- Không để private key và passphrase trong cùng file ZIP plaintext; cân nhắc dual-control cho việc mở khóa backup bảo mật cao.
- Test restore trên môi trường cô lập **với mạng và quyền truy cập bị giới hạn**. Dữ liệu auth được khôi phục có thể chứa tài khoản/mật khẩu vẫn có hiệu lực.

## 7. Thiết kế một bộ backup có manifest kiểm chứng được

### 7.1. Phạm vi và nguồn sự thật

Một manifest tốt trả lời được: bản sao lưu này thuộc **cluster nào, phiên bản nào, topology nào, thời điểm nào, đã gồm đối tượng nào và người restore lấy secret ở đâu**?

Ví dụ nội dung minh họa (không có giá trị bí mật):

~~~yaml
backup_id: cassandra-lab-20261121-0900Z
cluster: cassandra-lab
release: "5.x (ghi số phiên bản thực tế)"
snapshot_window_start: "2026-11-21T09:00:00Z"
snapshot_window_end: "2026-11-21T09:07:00Z"
schema_export: schema-export.cql
auth:
  backend: CassandraRoleManager/CassandraAuthorizer
  source_keyspace: system_auth
  snapshot_tags_by_node:
    node-A: auth_lab_20261121
    node-B: auth_lab_20261121
    node-C: auth_lab_20261121
topology:
  datacenters: ["dc1"]
  node_count: 3
  replication_source: system_schema.keyspaces export
config:
  source: managed IaC revision / signed config export
secrets:
  tls_bundle_reference: "secret-manager/... (reference only)"
  backup_encryption_key_reference: "kms/... (reference only)"
verification:
  sha256_manifest: "artifact checksums kept and signed separately"
  restore_drill: "pending"
~~~

YAML trên là **mẫu inventory**, không phải schema tool có thể tự động nhận. Không ghi một snapshot tag là đủ: cần inventory **node, table/keyspace, các file SSTable snapshot, dung lượng, checksum, timestamp và trạng thái sao lưu ngoài site**. Một snapshot tạo thành công nhưng file copy thất bại giữa chừng phải được đánh dấu incomplete.

### 7.2. Schema và system_auth có thể không cùng thời điểm

Ví dụ, ở 09:00 backup SSTable nghiệp vụ bắt đầu; 09:02 ứng dụng chạy migration thêm cột và đổi permission; 09:07 snapshot `system_auth` mới hoàn tất. Nếu restore DDL ở 09:02 nhưng SSTable chủ yếu từ 09:00 và grants từ 09:07, hệ thống có thể có **mismatch** về schema/role permissions.

Do đó cần một **cửa sổ change freeze** hoặc event log có thể phát lại theo thứ tự, cùng manifest thời gian các thành phần. Khả năng đạt snapshot nhất quán toàn cluster phụ thuộc công cụ backup và thiết kế vận hành; **`nodetool snapshot` theo từng node tự nó không cung cấp global transaction**. Với RPO chặt, phải bổ sung chiến lược incremental backups/CDC/continuous backup phù hợp.

### 7.3. Checksum, độ đầy đủ và khả năng giải mã

Sau khi copy file ra ngoài cluster:

1. Kiểm kê đủ file theo danh sách snapshot, cả metadata cần thiết của SSTable và cấu trúc thư mục.
2. Tạo/check **checksum cryptographic** (ví dụ SHA-256) cho từng artifact; ký manifest hoặc dùng object-store integrity/versioning để chống sửa metadata.
3. Kiểm tra backup được mã hóa và khóa giải mã **còn truy cập được theo quy trình khẩn cấp**; không đặt chính khóa chỉ trên node vừa được backup.
4. Xác minh restore **đọc được** DDL, config, file snapshot và secret references trên cluster cô lập.
5. Gắn thời điểm restore drill gần nhất và kết quả pass/fail; một checksum đúng chỉ chứng minh byte không đổi, **không chứng minh dữ liệu có thể khôi phục logic**.

Đối với dữ liệu cần tuân thủ pháp luật/quy định, kiểm soát cả retention, location, xóa sau hết hạn và xử lý backup chứa dữ liệu cá nhân; đừng dùng snapshot sống quá lâu chỉ vì “giữ càng nhiều càng tốt”.

## 8. Runbook phục hồi: đúng thứ tự, có kiểm soát quyền truy cập

### 8.1. Trước khi restore

**Không áp dụng các bước tiếp theo vào production đang chạy**. Thực hiện trên cluster phục hồi cô lập/DR staging và kiểm tra phiên bản/compatibility trước:

1. Xác định sự cố và mục tiêu: mất node, mất DC, schema bị xóa, quyền xác thực bị mất hay compromise TLS private key? Một phương án phù hợp mất DC **không nhất thiết** phù hợp compromise credentials.
2. Kiểm tra tính toàn vẹn manifest, checksum, completeness, backup encryption và nguồn secret.
3. Dựng cluster với **release/JVM và topology được hỗ trợ**, dung lượng disk, DC/rack, snitch, RF và network phù hợp. Không clone trực tiếp host identity từ node cũ.
4. Thiết lập quyền quản trị/break-glass trong môi trường cô lập với logging/audit; tránh vô tình bật kết nối production khi auth chưa phục hồi.
5. Dựng certificate chain/truststore/keystore và secret access; nếu phát hiện key bị lộ phải **cấp lại/revoke** theo quy trình thay vì reuse.

### 8.2. Phục hồi schema và dữ liệu

Thứ tự khái quát:

~~~mermaid
flowchart TD
    A["Xác minh backup và secret/KMS availability"] --> B["Dựng network/DC/rack/release phù hợp"]
    B --> C["Thiết lập TLS và break-glass access"]
    C --> D["Khôi phục schema CQL + RF"]
    D --> E["Nạp SSTable dữ liệu theo cơ chế hỗ trợ"]
    E --> F["Khôi phục/đối soát auth và grants theo runbook"]
    F --> G["Đồng bộ replica/repair khi phù hợp"]
    G --> H["Kiểm tra TLS, CL, role permissions, Java read/write"]
    H --> I["Mở traffic có kiểm soát, monitor RTO/RPO"]
~~~

Lưu ý thứ tự giữa bước nạp dữ liệu nghiệp vụ và nạp `system_auth` **có thể phải thay đổi** nếu cần role để xác thực công cụ loader; điều này phụ thuộc authenticator, cách bootstrap quyền và công cụ. Một runbook phải ghi rõ cách phá vòng phụ thuộc “cần auth để nạp auth” mà vẫn duy trì an toàn.

Với dữ liệu bảng:

- Dựng đúng schema và replication metadata trước khi dùng loader/restore.
- Phương pháp có thể là **streaming SSTable** bằng công cụ loader được release hỗ trợ, hoặc **phục hồi offline SSTable** rồi refresh/stream theo runbook. Cách nào phù hợp tùy sự cố, định dạng SSTable, keyspace/table, topology và phiên bản.
- Cần khôi phục mọi component liên quan SSTable snapshot, không chỉ file `*-Data.db` nếu công cụ yêu cầu đủ metadata.
- Snapshot một node không thay thế dữ liệu của mọi replica/range trong cluster; phải kiểm tra coverage và tính nhất quán.
- Với dữ liệu liên quan tombstone/TTL, **không phục hồi bản cũ vô tội vạ** vào cluster đang có dữ liệu mới: có thể hồi sinh giá trị đã xóa hoặc tạo xung đột timestamp. Cần kế hoạch reconcile/replace hợp lệ.

### 8.3. system_auth cần một restore drill riêng

Không cung cấp một câu lệnh `cp` hoặc `sstableloader` chung để restore `system_auth` trên mọi phiên bản. Quy trình cụ thể phải được phê duyệt và **kiểm thử theo release, auth backend, topology và cơ chế loader**, với các kiểm tra:

- Phạm vi role/grants của bản snapshot đúng **thời điểm nghiệp vụ mong muốn**, không tái kích hoạt account đã bị vô hiệu hóa do sự cố bảo mật.
- Schema `system_auth` nội bộ tương thích; replication đúng các DC, dữ liệu được nạp/repair tới đủ replica theo runbook.
- Authentication cache/permission cache và sự lan truyền thay đổi quyền được kiểm soát, không kỳ vọng mọi node cập nhật ngay mà không xác minh.
- Có admin break-glass riêng, không đưa superuser password vào YAML/Markdown, và chỉ mở lại client traffic sau khi kiểm tra thực.
- Nếu dùng IAM/LDAP/Kerberos tùy chỉnh, **khôi phục IdP/external ACL/keytab** tương ứng trước khi xác nhận auth đã sẵn sàng.

Không đánh đồng **phục hồi quyền** với **phục hồi secret cũ**. Có thể cần reset/rotate passwords, revoke old tokens hoặc tái cấp chứng thư để phù hợp chính sách khi sự cố liên quan compromise.

### 8.4. Kiểm tra từ Cassandra và Java

Trong `cqlsh` với quyền quản trị hợp lệ:

~~~sql
SELECT release_version FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name IN ('shop_lab', 'system_auth');

LIST ROLES;
LIST ALL PERMISSIONS;
~~~

Trên từng node:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats shop_lab.orders_by_customer_month
nodetool netstats
nodetool compactionstats
~~~

Quan sát schema agreement, các node ở trạng thái Up/Normal, RF và DC/rack đúng, không có streaming bị treo, tình trạng disk và độ trễ khi truy cập dữ liệu. Những kiểm tra này **không tự chứng minh** từng hàng nghiệp vụ đã được khôi phục; cần đối chiếu checksum/row sets và các truy vấn mẫu đại diện cho mọi token ranges.

Ví dụ Java Driver 4.x, giả định đã tạo `CqlSession session` **với TLS, truststore, authentication và local DC cấu hình đúng**:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

// session được khởi tạo từ cấu hình bảo mật bên ngoài source code.
PreparedStatement ps = session.prepare(
    "SELECT created_at, order_id, status " +
    "FROM shop_lab.orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ?");

BoundStatement statement = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"),
        202611)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet result = session.execute(statement);
int rows = 0;
for (Row row : result) {
    row.getUuid("order_id");
    rows++;
}
// Đối soát số lượng/khóa và dữ liệu nghiệp vụ với tập kiểm chứng.
~~~

Ở ví dụ này, thành công của request chứng minh ít nhất có thể **TLS handshake, authenticate, authorize và đọc dữ liệu** trên đường truy vấn đó. Nhưng một SELECT không xác minh mọi grants, mọi token range hoặc đủ RPO; cần thêm positive/negative permission tests, phép ghi được ủy quyền, dữ liệu mẫu có checksum và kiểm tra nhiều DC nếu có.

**Negative test quan trọng:** tài khoản chỉ có `SELECT` phải bị từ chối `MODIFY`; tài khoản đã bị thu hồi phải không thể đăng nhập. Khôi phục các hàng dữ liệu nhưng vô tình mở quyền là thất bại về bảo mật.

## 9. Checklist kiểm thử restore và đánh giá RTO/RPO

| Hạng mục | Kiểm tra đạt | Nếu không đạt |
|---|---|---|
| DDL | Keyspace, tables, types, indexes/views, RF/CL/compaction đồng nhất với manifest | Sửa thứ tự schema, mapping release hoặc migration |
| Cluster topology | Node/DC/rack/host identity và stream hoàn tất | Sửa topology/bootstrap/replace đúng runbook |
| system_auth | Role, memberships, grants, backend, RF và admin access đúng | Khôi phục role/grant an toàn trong staging, tránh mở traffic |
| TLS | Chain/SAN/expiry, mTLS nếu bật, node-to-node và client-to-node hợp lệ | Cấp lại/khôi phục secrets từ nguồn đúng, thu hồi key lộ |
| KMS/backup encryption | File giải mã được theo cơ chế có audit, không có key nằm trong source repo | Khôi phục quyền KMS/key dependency, không bypass security |
| Dữ liệu nghiệp vụ | Khóa mẫu và coverage nhiều partition/token range, timestamp/TTL/tombstone đúng kỳ vọng | Rà soát snapshot/loader và point-in-time consistency |
| Java clients | Đúng local DC, TLS auth, permission SELECT/MODIFY, p95/p99, retry errors | Chỉnh trust bundle/credentials/CL hoặc quyền |
| RPO/RTO | Thời điểm phục hồi và elapsed time nằm trong cam kết | Điều chỉnh lịch backup và tự động hóa DR |
| Backup kế tiếp | Sau restore có backup schedule, retention, alerting và restore drill định kỳ | Khôi phục năng lực bảo vệ liên tục |

**Không coi kiểm tra “cluster đã Up/Normal” là đủ.** Cluster có thể hoạt động nhưng thiếu keyspace, sai grants, private key sắp hết hạn hoặc ứng dụng đang dùng CL không hợp lệ trong DC mới.

### 9.1. Chỉ số cần đo trong diễn tập

Ví dụ mẫu báo cáo, các giá trị cần điền **từ diễn tập thực**, không giả mạo số liệu:

| Chỉ số | Kết quả đo | Mục tiêu được phê duyệt | Pass/Fail |
|---|---|---|---|
| Thời gian từ phát hiện đến truy cập quản trị | _điền_ | _điền_ | _điền_ |
| Thời gian dựng lại TLS/credentials | _điền_ | _điền_ | _điền_ |
| Thời gian schema và system_auth sẵn sàng | _điền_ | _điền_ | _điền_ |
| Thời gian restore/stream dữ liệu | _điền_ | _điền_ | _điền_ |
| Thời điểm dữ liệu cuối cùng khôi phục được | _điền_ | Theo RPO | _điền_ |
| Java service phục vụ truy vấn/ghi thành công | _điền_ | Theo RTO | _điền_ |
| Số role/grants được đối soát | _điền_ | Theo inventory | _điền_ |
| Kiểm thử chứng thư bị thu hồi/expired | _điền_ | Không chấp nhận kết nối | _điền_ |

Một lần diễn tập ngắn trên một node không thay thế được khôi phục nhiều DC, mạng phân tách và yêu cầu bảo mật thực. Trên production, cần dự kiến đủ storage/headroom khi phục hồi; restore có thể tạo tải streaming, compaction và repair gây thay đổi p99.

## 10. Các sai lầm phổ biến và cách sửa

| Ngộ nhận | Hậu quả | Cách tiếp cận đúng |
|---|---|---|
| “SSTable snapshot bao gồm toàn bộ schema và quyền” | Restore thiếu định nghĩa bảng, roles hoặc grants | Xuất DDL, inventory system_auth và config/secrets riêng |
| “DESCRIBE SCHEMA là full database backup” | Không có hàng dữ liệu/khóa TLS | Lưu snapshot/incrementals và secret dependencies |
| “system_auth chỉ là dữ liệu hệ thống, không cần backup” | Login thất bại hoặc mất quyền sau DR | Backup an toàn theo auth backend và test restore |
| “Có chứng thư public là đủ” | Không có private key để chứng minh danh tính | Giữ key an toàn hoặc kế hoạch cấp lại/thu hồi |
| “Hash mật khẩu không phải secret” | Rò rỉ credential material và cấu trúc quyền | Phân loại snapshot system_auth là nhạy cảm cao |
| “Sao lưu secret cùng file config plaintext cho tiện” | Lộ cả key lẫn password khi thất thoát một artifact | Tách secret manager và mã hóa backup có audit |
| “Bản snapshot một node là backup toàn cluster” | Thiếu token ranges/replicas, thiếu metadata đồng bộ | Manifest theo node/range và kiểm tra coverage |
| “restore data trước, schema tính sau” | Loader thiếu kiểu/cột hoặc không tương thích | Dựng schema và dependencies đúng trình tự |
| “Đổi RF system_auth là các replica tự đồng bộ” | Login có thể sai lệch giữa node/DC | Lập repair/stream theo runbook, xác minh role trên nhiều node |
| “Chép thư mục system của node cũ vào node mới” | Đụng host ID/token/gossip metadata, nguy cơ cluster lỗi | Bootstrap/replace và chỉ restore dữ liệu theo hướng dẫn |
| “Khi key bị lộ, dùng key từ backup là an toàn” | Khóa đã bị compromise tiếp tục có giá trị | Revoke/rotate và cấp lại, audit truy cập |
| “Restore drill pass vì SELECT trả một hàng” | Bỏ sót quyền, token ranges, dữ liệu TTL/tombstone và RPO | Kiểm tra dữ liệu đại diện, positive/negative auth, TLS, checksum |
| “Tắt auth/TLS tạm trong production để restore” | Mở cửa xâm nhập và tạo chênh lệch policy | Runbook break-glass cô lập, có kiểm soát và audit |

## 11. Bài tập tình huống

### Bài 1 — Bản backup thiếu gì?

Nhóm A chỉ sao chép các SSTable của keyspace `shop_lab`, đồng thời giữ một file `schema-export.cql`. Sau thảm họa mất toàn DC, ứng dụng Java không đăng nhập được và TLS handshake thất bại. Hãy liệt kê ít nhất **ba nhóm artifact** còn thiếu.

**Gợi ý:** `system_auth` hoặc IdP/ACL backend, private key/keystore/truststore/CA và passphrase/KMS, cấu hình node/DC/rack/ports/auth/TLS. Có thể còn thiếu snapshot của nhiều replica và inventory repair/topology.

### Bài 2 — Vì sao cần bảo vệ system_auth khác dữ liệu thường?

Một nhân viên cho rằng `system_auth` chỉ chứa hash mật khẩu nên có thể đặt snapshot trong bucket public read-only. Quyết định này có an toàn không?

**Gợi ý:** không. Hash, role memberships và grants là dữ liệu nhạy cảm; việc lộ có thể hỗ trợ tấn công offline/phân tích đặc quyền. Cần encryption, access control, audit, retention và chính sách cấp quyền phù hợp.

### Bài 3 — Thay đổi quyền giữa các lần snapshot

09:00 snapshot dữ liệu nghiệp vụ; 09:03 thu hồi tài khoản `old_admin`; 09:05 snapshot `system_auth`. Bản backup cuối ngày có thể khôi phục ra trạng thái nào? Nếu bản sao auth thực tế lại được chụp lúc 08:55 thì nguy cơ khác biệt là gì?

**Gợi ý:** phải ghi chính xác thời điểm từng artifact. Snapshot auth sau thu hồi có thể không chứa quyền cũ; snapshot trước thu hồi có thể **kích hoạt lại** quyền của `old_admin`. Khi có sự cố bảo mật phải ưu tiên revocation/rotation theo trạng thái hiện tại, không tin dữ liệu cũ tuyệt đối.

### Bài 4 — Mất KMS key

SSTable backup còn nguyên, checksum đúng, nhưng khóa giải mã at-rest chỉ tồn tại trong KMS vùng đã mất. Có thể khôi phục không?

**Gợi ý:** chưa chắc, thậm chí có thể **không thể** nếu không còn phương án khôi phục key. Checksum không thay thế key. Cần thiết kế replication/key escrow policy hoặc DR của KMS trước thảm họa và test trên môi trường cô lập.

### Bài 5 — Kế hoạch diễn tập

Viết runbook một trang cho restore cluster lab gồm ba node: liệt kê artifact, owner, thứ tự khôi phục, 5 phép kiểm tra và RPO/RTO. Với kiểm thử bảo mật, yêu cầu một tài khoản chỉ đọc được `SELECT` mà bị từ chối `MODIFY`.

**Gợi ý:** phối hợp schema + configuration + system_auth + TLS/KMS + SSTables + manifest/checksum; kiểm tra RF/CL, role grants, TLS chain, Java read/write và repair/streaming status. Nêu rõ phần nào cần admin break-glass và không lưu secret plaintext.

### Checklist kết thúc bài

- [ ] Phân biệt backup dữ liệu nghiệp vụ với schema, config, system_auth và secret material.
- [ ] Biết `DESCRIBE SCHEMA`/`DESCRIBE KEYSPACE` chỉ xuất DDL, không phải dữ liệu.
- [ ] Biết vì sao auth data/grants phải backup theo backend và replication thực.
- [ ] Không để password hashes/private keys/keystore passphrases trong tài liệu hoặc kho public.
- [ ] Phân biệt certificate public, private key, truststore, keystore và KMS/data-encryption key.
- [ ] Có manifest theo node/tag/thời điểm/version/topology/RF, checksums và audit.
- [ ] Biết snapshot ở node hiện tại không phải global transaction của cả cluster.
- [ ] Biết không restore mù metadata ring/host identity của node cũ.
- [ ] Có bước restore drill xác minh positive/negative authorization, TLS và Java CQL.
- [ ] Đo được RPO/RTO và có phương án rotate/revoke khi secrets bị lộ.

## 12. Tài liệu tham khảo

1. Apache Cassandra Documentation — [Backup and restore](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html): snapshot, incremental backup và các giới hạn phục hồi.
2. Apache Cassandra Documentation — [nodetool snapshot](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/snapshot.html) và [listsnapshots](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/listsnapshots.html): thao tác trên từng node.
3. Apache Cassandra Documentation — [CQL data definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): schema, keyspace, tables, options.
4. Apache Cassandra Documentation — [Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization và TLS.
5. Apache Cassandra Documentation — [cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): topology, authentication và encryption options.
6. Apache Cassandra Documentation — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): đồng bộ replica sau sự cố và rủi ro tombstone.
7. Apache Cassandra Documentation — [cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): lệnh quản trị và xuất DDL.
