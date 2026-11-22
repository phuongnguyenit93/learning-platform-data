# Đọc lỗi cú pháp, lỗi xác thực, unavailable và timeout

## 1. Đọc thông báo lỗi để xác định đúng lớp sự cố

Trong Apache Cassandra, ứng dụng Java hoặc `cqlsh` kết nối một node bằng **native CQL protocol** (thường qua TCP 9042). Node nhận truy vấn đóng vai trò **coordinator**, xác định replica từ partition key, replication strategy và topology, rồi thu thập phản hồi theo **consistency level** (CL). Một câu lệnh không chạy được có thể do bản thân CQL, danh tính người dùng, quyền trên bảng, trạng thái replica hoặc mạng.

Với chương **Công cụ và kết nối** thuộc module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, việc đọc lỗi không chỉ là tìm dòng có chữ “Exception”. Ta phải biết **lỗi xảy ra trước hay sau khi request đến Cassandra**, do CQL sai hay do hệ phân tán chưa đáp ứng điều kiện đọc/ghi. Đây là kỹ năng cần thiết khi thực hành partition key, thiết kế bảng theo truy vấn, replication, consistency, repair/compaction và kết nối Java Driver.

**Mục tiêu học tập:**

1. Nhận diện lỗi **cú pháp** so với lỗi **CQL hợp lệ về cú pháp nhưng không hợp lệ về schema/quy tắc truy vấn**.
2. Phân biệt **authentication** (đăng nhập thất bại) với **authorization** (đăng nhập thành công nhưng thiếu quyền).
3. Đọc thông báo **Unavailable** theo số replica cần và đang sẵn sàng.
4. Phân biệt **ReadTimeout**, **WriteTimeout**, **driver/request timeout** và **mất kết nối TCP**; không suy luận sai về kết quả ghi.
5. Dùng `SHOW HOST`, `DESCRIBE`, `CONSISTENCY`, `TRACING`, `nodetool` và log để thu hẹp nguyên nhân.
6. Viết đoạn Java Driver báo lỗi có ngữ cảnh nhưng không lộ mật khẩu, và tránh retry nguy hiểm.

## 2. Bản đồ lỗi theo từng giai đoạn

~~~mermaid
flowchart TD
    A["Ứng dụng Java hoặc cqlsh gửi request"] --> B{"DNS/TCP tới native port được?"}
    B -->|"Không"| C["Connection refused, connect timeout, không tìm thấy host"]
    B -->|"Có"| D{"TLS/native handshake và đăng nhập được?"}
    D -->|"Không"| E["TLS handshake, AuthenticationException, lỗi protocol"]
    D -->|"Có"| F{"CQL đúng cú pháp và schema?"}
    F -->|"Không"| G["SyntaxException hoặc InvalidRequest"]
    F -->|"Có"| H{"Role được phép thao tác?"}
    H -->|"Không"| I["Unauthorized"]
    H -->|"Có"| J{"Đủ replica cho CL đã chọn?"}
    J -->|"Không"| K["Unavailable"]
    J -->|"Có"| L{"Có đủ phản hồi trước deadline?"}
    L -->|"Không"| M["ReadTimeout / WriteTimeout / driver timeout"]
    L -->|"Có"| N["RESULT thành công"]
~~~

Sơ đồ là **luồng phân loại thực hành**, không phải thứ tự kiểm tra nội bộ bất biến của mọi phiên bản. Ví dụ, một số lỗi schema/quyền có thể được phát hiện tại các điểm khác nhau trong xử lý request. Điều quan trọng là **phân biệt tầng kết nối, tầng kiểm tra request và tầng xử lý phân tán**.

| Nhóm lỗi | Dấu hiệu điển hình | Cần kiểm tra đầu tiên |
| --- | --- | --- |
| Cú pháp CQL | `SyntaxException`, chỉ vị trí `line/column` | Câu lệnh, dấu phẩy/chấm phẩy, tên keyword, dấu nháy. |
| Request/schema không hợp lệ | `InvalidRequest`, `InvalidQuery` hoặc thông báo tương đương | `DESCRIBE TABLE`, partition key, kiểu dữ liệu, tên bảng/cột. |
| Xác thực | `AuthenticationException`, `AuthenticationFailed` | Username/password, auth provider, TLS, role cho phép login. |
| Phân quyền | `Unauthorized` hoặc `UnauthorizedException` | Role thực tế, `GRANT`, quyền trên keyspace/bảng. |
| Không đủ replica | `Unavailable` hoặc `UnavailableException` | CL yêu cầu, replication factor, datacenter, node đang Up/Down. |
| Replica chậm/không đủ phản hồi | `ReadTimeout`, `WriteTimeout` | Số phản hồi, deadline, tải và đường internode. |
| Client hết thời gian | `DriverTimeoutException`, request timeout trong driver (tên cụ thể tùy bản) | Deadline phía ứng dụng, kết nối, server latency, paging/queue. |
| Client không kết nối được node | `AllNodesFailedException` (Java Driver 4.x), connect timeout | Contact points, native port, TLS, địa chỉ peer được công bố. |

Tên lớp exception và cách cqlsh hiển thị khác nhau theo Cassandra/cqlsh/Java Driver. **Đừng chỉ dựa vào tên**: đọc thông báo, câu CQL, host/coordinator, CL và thời điểm phát sinh.

## 3. Chuẩn bị lab để đọc lỗi an toàn

Các ví dụ dưới đây dùng **Cassandra đơn node, RF = 1** để không cần tắt node hoặc can thiệp dữ liệu của cluster production. Muốn quan sát lỗi nhiều replica và chênh lệch quorum, cần một cluster lab riêng với topology phù hợp.

Kết nối từ terminal nơi cài `cqlsh`:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh, kiểm tra điểm kết nối và tạo bảng:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS error_diagnostics_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS error_diagnostics_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO error_diagnostics_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO error_diagnostics_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.3);
~~~

`(device_id, event_day)` là **composite partition key**. Trong partition, Cassandra sắp row theo `event_time` giảm dần rồi `event_id` tăng dần. Hai lệnh `INSERT` dùng primary key cố định: chạy lại lab sẽ **upsert** cùng row, không tạo các bản ghi trùng primary key.

Một truy vấn đúng để đối chiếu:

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_type, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Kết quả kỳ vọng gồm **hai row**, thời điểm 01:05 trước 01:00. `SimpleStrategy`/RF = 1 chỉ phục vụ lab. Hệ nhiều datacenter thường dùng `NetworkTopologyStrategy` và RF theo datacenter; đừng sao chép cấu hình này làm tiêu chuẩn production.

## 4. Lỗi cú pháp: đọc thông báo và sửa đúng chỗ

### 4.1. SyntaxException là gì?

CQL có ngữ pháp riêng. Khi một token xuất hiện không đúng nơi hoặc thiếu thành phần bắt buộc, parser có thể trả **`SyntaxException`**. Ví dụ cố ý sai:

~~~sql
-- Sai: dấu phẩy ngay trước FROM.
SELECT event_time, FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Một thông báo có thể **tương tự**:

~~~text
SyntaxException: line 1:... mismatched input 'FROM' ...
~~~

Đây chỉ là **mẫu hình thông báo**, không phải đầu ra cố định. Cụm từ và số cột phụ thuộc phiên bản và chỗ cqlsh tách dòng. Cách đọc:

1. Xác định câu lệnh gây lỗi trong lịch sử cqlsh/script.
2. Đọc `line` và `column` nếu được cung cấp; đó là vị trí parser phát hiện bất thường, **không luôn là ký tự gây lỗi ban đầu**.
3. Nhìn cả token trước và sau vị trí được báo, đặc biệt dấu phẩy, dấu ngoặc, dấu nháy và `;`.
4. Sửa từng câu lệnh nhỏ, chạy lại trong lab rồi mới sửa script lớn.

Sửa thành:

~~~sql
SELECT event_time
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

### 4.2. SyntaxException khác InvalidRequest

Một câu lệnh có thể **đúng ngữ pháp nhưng sai mô hình truy vấn**. Ví dụ:

~~~sql
-- Ngữ pháp SELECT hợp lệ, nhưng WHERE không chỉ định partition key.
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE event_time > '2026-11-21T01:00:00Z';
~~~

Với bảng lab chưa có index thích hợp, Cassandra thường từ chối vì không thể định tuyến/đọc hiệu quả theo điều kiện này hoặc vì cần lọc dữ liệu mà truy vấn không cho phép. Lỗi được xếp vào nhóm **InvalidRequest/InvalidQuery**, **không phải** lỗi password và không đơn giản là mất kết nối.

Để sửa đúng, quay lại **thiết kế bảng theo truy vấn**. Truy vấn của lab cần lọc đủ `device_id` và `event_day`:

~~~sql
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time > '2026-11-21T01:00:00Z';
~~~

Với kiểu clustering `event_time timestamp`, điều kiện range trên `event_time` sau khi xác định đúng partition là phù hợp. Không thêm `ALLOW FILTERING` vào mọi truy vấn chỉ để “hết lỗi” mà chưa xem chi phí quét partition, schema và truy vấn thực tế.

### 4.3. Những lỗi cú pháp/dữ liệu hay gặp

| Biểu hiện | Cách hiểu | Cách sửa |
| --- | --- | --- |
| `SyntaxException` gần `FROM` hoặc `WHERE` | Sai danh sách cột, thiếu dấu, keyword không đúng vị trí. | Đọc token quanh điểm báo và kiểm tra cú pháp `SELECT`. |
| `unconfigured table` / bảng không tồn tại | Tên bảng/keyspace sai hoặc chưa tạo. | `DESCRIBE KEYSPACES;`, `DESCRIBE TABLE keyspace.table;`. |
| `Unknown identifier` / cột không tồn tại | Tên cột khác schema, có thể nhầm viết hoa/trích dẫn identifier. | Đọc định nghĩa bảng và tên cột chính xác. |
| Sai kiểu dữ liệu | Dùng chuỗi cho giá trị UUID/int hoặc timestamp không hợp lệ. | Kiểm tra CQL type; với Java dùng bind values kiểu đúng. |
| Lỗi thiếu partition key | Mẫu truy vấn không phù hợp primary key. | Xác định partition key từ `DESCRIBE TABLE`; thiết kế bảng theo truy vấn. |
| Query hợp lệ ở keyspace khác | Phiên đang `USE` nhầm keyspace, tên bảng trùng nhau. | Dùng `keyspace.table` hoặc xác minh lại `USE`. |

**Trong script:** `cqlsh -f script.cql` và `SOURCE 'script.cql';` có thể chạy nhiều câu liên tiếp, nhưng không tự biến cả script thành một transaction. Một câu báo lỗi không rollback những câu trước đã thành công. Kiểm tra thứ tự tạo schema, dữ liệu đã ghi và chính sách chạy lại script.

## 5. Lỗi xác thực và phân quyền: đừng đánh đồng

### 5.1. Authentication xảy ra ở đâu?

Nếu server bật `PasswordAuthenticator`, client phải gửi danh tính đăng nhập phù hợp trong quá trình thiết lập phiên native. Ví dụ:

~~~bash
# Mẫu kết nối khi account đã được provision.
cqlsh db.example.internal 9042 --ssl -u report_reader
~~~

Địa chỉ `db.example.internal` là ví dụ; server thật phải có native endpoint reachable. `--ssl` dùng khi server cấu hình TLS; tài khoản và chứng chỉ CA cần cấu hình theo môi trường. Tránh truyền mật khẩu qua tham số `-p` để không lộ trong lịch sử shell, process list hoặc log.

Nếu password sai, role không được đăng nhập hoặc backend auth không sẵn sàng, kết quả có thể là `AuthenticationFailed` hoặc `AuthenticationException`. Dấu hiệu quan trọng: **chưa có session CQL hợp lệ** để chạy `SELECT`.

Các bước kiểm tra an toàn:

1. Xác nhận client đang kết nối đúng cluster/node/port, không trỏ nhầm production và staging.
2. Xác nhận server có bắt buộc TLS không, CA/chứng chỉ server và hostname hợp lệ không.
3. Kiểm tra danh tính **đang được ứng dụng sử dụng** (không chỉ username ghi trong tài liệu), password đã được cập nhật qua secret manager và role có `LOGIN = true`.
4. Nếu nhiều node và sự cố chỉ xuất hiện ở một vài node, kiểm tra trạng thái và replication của **system_auth**, cache auth, clock/config và server logs.
5. Không thử lặp hàng loạt mật khẩu, không tắt `PasswordAuthenticator` hay TLS để chữa tạm lỗi.

### 5.2. Authorization xảy ra sau xác thực

Giả sử người dùng đã đăng nhập thành công nhưng truy vấn:

~~~sql
SELECT *
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

trả về **`Unauthorized`**. Điều này cho thấy role chưa được cấp đúng quyền `SELECT` cho bảng/keyspace, hoặc có khác biệt về danh tính/role kế thừa/cache. Không cần đổi syntax hay tăng consistency để sửa lỗi quyền.

Trong lab đã bật `CassandraAuthorizer`, tài khoản quản trị có thể cấp quyền tối thiểu:

~~~sql
-- Chạy bằng role quản trị được cấp phép.
GRANT SELECT ON TABLE error_diagnostics_lab.events_by_device_day
TO report_reader;

-- Xem quyền tùy khả năng và phiên bản Cassandra.
LIST ALL PERMISSIONS OF report_reader;
~~~

Ví dụ giả định `report_reader` đã tồn tại và có login. Trên hệ thống thật, kiểm tra quyền hiện có, quyền thừa hưởng và chính sách cấp quyền trước khi thay đổi. `GRANT` có thể cần một khoảng thời gian để cập nhật cache authorization ở các node; không giả định mọi kết nối đang hoạt động nhìn thấy ngay lập tức.

Nếu role chỉ có `SELECT`, lệnh `INSERT` vào cùng bảng **phải bị từ chối**, dù SELECT thành công. Đây là hành vi đúng của **least privilege**, không phải lỗi Cassandra.

| Kiểu lỗi | Ví dụ câu trả lời | Cách xử lý |
| --- | --- | --- |
| **Authentication** | “Sai credentials” hoặc `AuthenticationException` khi tạo session. | Kiểm tra role, login, password, auth backend, TLS. |
| **Authorization** | `Unauthorized` khi chạy `SELECT`, `INSERT` hoặc DDL. | Kiểm tra quyền trên resource, role inheritance, `CassandraAuthorizer`. |
| **TLS certificate error** | `SSLHandshakeException`, verify hostname/CA thất bại. | Sửa truststore, hostname/SAN, cert chain, mTLS nếu có; không đổi password tùy tiện. |

**Lưu ý:** TLS/mTLS kiểm tra danh tính ở lớp kết nối; trong cấu hình `PasswordAuthenticator`, client có thể vẫn cần username/password dù TLS đã qua. Mã hóa client ↔ server (`client_encryption_options`) và internode (`server_encryption_options`) là hai cấu hình riêng.

## 6. Unavailable: không có đủ replica sẵn sàng cho consistency

### 6.1. Cách Cassandra đánh giá trước khi chờ kết quả

**Replication factor (RF)** quyết định số replica của partition theo keyspace/datacenter; **consistency level (CL)** quyết định số phản hồi cần đạt cho thao tác. Khi coordinator xác định số replica **đang sẵn sàng** không đủ để đáp ứng CL, nó có thể trả **`Unavailable`** sớm, thay vì tiếp tục chờ đến hết timeout.

Thông báo minh họa:

~~~text
Unavailable: Cannot achieve consistency level QUORUM
Required replicas: 2; alive replicas: 1
~~~

Câu chữ chính xác phụ thuộc phiên bản. Đừng sao chép con số “required/alive” từ ví dụ để giải thích một cluster thực; hãy đọc **số replica được yêu cầu và số replica thực tế** từ thông báo của chính request.

### 6.2. Bảng số replica cho một datacenter RF = 3

| Consistency level | Số replica cần cho RF = 3 (một DC) | Nếu chỉ 1 replica Up |
| --- | ---: | --- |
| `ONE` | 1 | Có thể đáp ứng nếu node đó phản hồi. |
| `TWO` | 2 | Không đủ; có thể trả `Unavailable`. |
| `QUORUM` | 2 | Không đủ; có thể trả `Unavailable`. |
| `LOCAL_QUORUM` | 2 trong DC đang xét | Không đủ trong trường hợp một DC RF = 3. |
| `ALL` | 3 | Không đủ. |

Với nhiều datacenter, `LOCAL_QUORUM` tính quorum **trong local DC**, còn `QUORUM` tính trên tập replica của hệ thống theo semantics nhất quán tương ứng. Cần đọc định nghĩa replication thực tế, không áp dụng RF = 3 của bảng trên cho mọi DC. Với RF = 1 trong lab, **`LOCAL_QUORUM` chỉ cần 1 replica** tại DC có RF = 1, không phải 2.

Quorum giúp cân bằng consistency và availability nhưng không tự tạo transaction nhiều row, không sửa thiết kế partition key và không thay thế LWT (`IF`) khi cần cập nhật có điều kiện.

### 6.3. Thực hành lỗi thiếu replica trên lab RF = 1

Trên lab đơn node đã tạo ở mục 3:

~~~sql
-- Truy vấn hợp lệ với RF=1.
CONSISTENCY ONE;
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Cố ý chọn CL cần 2 replica để minh họa lỗi.
-- Chỉ làm trên lab RF=1, không tự ý đổi CL trên production.
CONSISTENCY TWO;
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Đặt lại CL sau khi quan sát.
CONSISTENCY ONE;
~~~

Truy vấn thứ hai thường trả `Unavailable` hoặc thông báo **không thể đạt consistency yêu cầu**, vì RF = 1 chỉ có một replica logic. Nó không chứng minh một node đang chết; **chính yêu cầu CL vượt quá số replica được cấu hình**.

Nếu cần đánh giá sự cố mất node thực sự, dùng cluster lab nhiều node, dữ liệu không quan trọng và kế hoạch khôi phục. Không tắt node production để “thử Unavailable”.

### 6.4. Khắc phục Unavailable đúng bản chất

1. Xác nhận **keyspace** mà truy vấn đang truy cập và replication strategy của nó:

   ~~~sql
   DESCRIBE KEYSPACE error_diagnostics_lab;
   CONSISTENCY;
   ~~~

2. Xem trạng thái cluster từ node có quyền:

   ~~~bash
   nodetool status
   nodetool gossipinfo
   ~~~

3. Kiểm tra node liên quan có chạy và mạng **internode** (thường 7000) có thông không; đối chiếu rack/datacenter và thông tin gossip.
4. Với production, đánh giá sự cố node, kế hoạch phục hồi và nhu cầu nghiệp vụ trước khi thay CL. **Giảm CL có thể làm thay đổi bảo đảm nhất quán mà ứng dụng cam kết**.
5. Nếu thay replication factor, cần kế hoạch vận hành để dữ liệu và replica thực tế được đồng bộ; chỉ sửa schema keyspace không tự bảo đảm dữ liệu đã có đủ bản sao.

## 7. Timeout: đã chờ nhưng chưa có câu trả lời đủ điều kiện

`Unavailable` nói rằng coordinator nhận thấy không đủ replica *đang sẵn sàng* để đạt CL. **Timeout** thường nghĩa là request hoặc một giai đoạn của nó **không hoàn tất kịp thời hạn**. Phải phân biệt timeout phía server/coordinator với timeout ở client/driver.

### 7.1. So sánh các loại timeout

| Loại | Quan sát ở đâu? | Ý nghĩa cần nhớ |
| --- | --- | --- |
| **ReadTimeout** | Cassandra coordinator trả về lỗi đọc qua native protocol. | Không nhận đủ phản hồi/đáp ứng điều kiện đọc trước deadline; có thể liên quan replica chậm, disk/compaction/tombstone/network. |
| **WriteTimeout** | Coordinator trả lỗi ghi trước deadline. | Không có đủ phản hồi ghi đúng hạn; **một phần hoặc toàn bộ replica có thể đã thực hiện ghi**. |
| **Driver/request timeout** | Java Driver hoặc client hết hạn chờ. | Client không nhận kết quả trong deadline của nó; request trên server có thể vẫn đang chạy/đã hoàn tất. |
| **Connect timeout** | Thiết lập kết nối TCP thất bại vì quá thời gian. | Chưa có phiên native ổn định; xem routing, listener, firewall, DNS. |
| **ReadFailure / WriteFailure** | Server báo lỗi xử lý tại replica. | Có phản hồi lỗi từ replica, khác với chỉ chờ quá hạn. |

Ví dụ thông báo minh họa:

~~~text
ReadTimeout: received 1 responses, required 2
WriteTimeout: received 1 acknowledgements, required 2
DriverTimeoutException: query timed out after a client deadline
~~~

Tên và thông tin thêm (write type, data present, coordinator, request/trace id) có thể khác. Khi có `received`/`required`, hãy đọc cùng **CL, RF, DC** để biết các số đó mang ý nghĩa gì.

### 7.2. ReadTimeout không tự nói dữ liệu không tồn tại

Trong Cassandra, đọc có thể cần nhiều replica phối hợp, một số bước hòa giải/digest, và fetch dữ liệu đáp ứng semantics của CL. Một node chậm do GC, compaction, đọc SSTable, tombstone nhiều hoặc network chập chờn có thể khiến coordinator chưa có đủ kết quả đúng hạn.

Khi gặp `ReadTimeout`:

- Xem câu `WHERE` có chứa **partition key** đúng không; truy vấn quét rộng, partition quá lớn hoặc kết quả nhiều page có thể làm chi phí tăng.
- Kiểm tra `nodetool status`, tài nguyên node, latency, compaction và log server; có thể dùng `TRACING ON` cho **một truy vấn đại diện có kiểm soát**.
- Đối chiếu consistency, RF, datacenter và timeout đang áp dụng.
- Không kết luận “row không tồn tại”: đây là **lỗi không hoàn tất đọc**, không phải kết quả SELECT trả zero row.

### 7.3. WriteTimeout và kết quả ghi không xác định

Một coordinator có thể đã gửi ghi tới nhiều replica, và một hoặc vài replica đã lưu dữ liệu trước khi client nhận `WriteTimeout`. Nếu ứng dụng **tự retry không kiểm soát**, sẽ phát sinh nguy cơ ghi trùng logic hoặc hiệu ứng phụ lặp lại.

Ví dụ hai tình huống:

1. **Upsert cùng primary key, cùng giá trị:** chạy lại có thể phù hợp trong một số tình huống, nhưng timestamp của cell, ghi đồng thời, TTL và các quy tắc nghiệp vụ vẫn phải được xét.
2. **Counter increment, cấp phát số thứ tự, logic “trừ tiền”, workflow phát sự kiện:** retry mù khi kết quả ghi chưa rõ có thể khiến hiệu ứng nghiệp vụ diễn ra **hơn một lần**. Cần idempotency key, cơ chế bảo vệ điều kiện hoặc quy trình đối soát tùy nghiệp vụ.

Với **LWT** (`INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...`), timeout có thể xảy ra trong pha Paxos/commit. **Không suy rằng điều kiện chưa từng được áp dụng**; cần đọc/đối chiếu trạng thái, retry theo semantics ứng dụng và chính sách driver hỗ trợ.

**Quy tắc an toàn:** với ghi không rõ kết quả, xác minh **primary key và trạng thái nghiệp vụ**, thiết kế idempotency, quan sát metrics/log trước khi quyết định retry. Không tăng vô hạn số lần retry và không thay consistency tùy tiện.

### 7.4. Client timeout khác server timeout

Hãy hình dung:

~~~mermaid
sequenceDiagram
    participant App as Java Driver (deadline 2s, ví dụ)
    participant Coord as Coordinator
    participant Rep as Replica
    App->>Coord: INSERT / SELECT với CL
    Coord->>Rep: Đọc/ghi partition
    Note over App: Deadline phía client hết
    App--xApp: Client báo timeout
    Rep-->>Coord: Replica trả kết quả muộn
    Coord-->>App: Response có thể tới sau hoặc bị bỏ qua
~~~

Thời hạn **2 giây** chỉ để minh họa, không phải default Cassandra/Java Driver. Client hết hạn chờ không có nghĩa server đã ngừng xử lý hoặc dữ liệu chưa được ghi. Ngược lại, khi coordinator trả `ReadTimeout`/`WriteTimeout`, đó là tín hiệu native/server với thông tin về loại thao tác và phản hồi replica. Cần xem **stack trace, exception class và message** để phân biệt.

**Cảnh giác với retry storm:** khi nhiều client timeout cùng lúc, retry ngay và lặp liên tục có thể làm cluster đang quá tải càng chậm. Sử dụng timeout, retry policy, backoff/jitter và circuit breaker phù hợp SLA, cùng với giới hạn concurrency; chỉ retry tự động các thao tác đã được xác định là an toàn.

## 8. Dùng cqlsh và nodetool để thu thập bằng chứng

### 8.1. Kiểm tra đúng cluster và schema trước

~~~sql
SHOW HOST;
SHOW VERSION;
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE error_diagnostics_lab;
DESCRIBE TABLE error_diagnostics_lab.events_by_device_day;

-- Có thể xem/thay CL trong cqlsh cho phiên hiện tại.
CONSISTENCY;
CONSISTENCY ONE;
~~~

`SHOW HOST` kiểm tra điểm kết nối của cqlsh. `DESCRIBE` giúp xác nhận schema, keyspace replication và primary key. `CONSISTENCY` **chỉ thay mức consistency của phiên cqlsh hiện tại**, không thay cấu hình ứng dụng Java đang chạy.

### 8.2. TRACING giúp gì và không giúp gì?

~~~sql
-- Chỉ bật trong thời gian ngắn để điều tra một truy vấn nhỏ.
TRACING ON;

SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 2;

TRACING OFF;
~~~

Trace có thể hiển thị coordinator và các hoạt động trên replica, thời gian từng bước và trace session. Tuy nhiên, tracing tạo overhead và cần quyền/khả năng đọc dữ liệu trace. Với **lỗi xác thực trước session**, tracing CQL chưa thể chạy; với **Unavailable rất sớm**, thông tin trace có thể ít hoặc không có. Không bật tracing cho toàn bộ production traffic chỉ để tìm một request chậm.

### 8.3. Kiểm tra cluster từ node quản trị

~~~bash
# Trạng thái các node trong ring theo góc nhìn node được hỏi.
nodetool status

# Thông tin gossip/endpoints; hữu ích khi nghi mạng internode.
nodetool gossipinfo

# Tiến trình streaming, ví dụ khi bootstrap/repair.
nodetool netstats

# Quan sát compaction đang chạy khi có triệu chứng đọc chậm.
nodetool compactionstats
~~~

Kết hợp với **server logs, CPU/GC, disk I/O, latency percentiles, dropped messages, tombstones và queue/concurrency metrics**. Một node có trạng thái `UN` không bảo đảm mọi truy vấn của nó đều nhanh. Đừng khởi chạy `repair` hay `compact` chỉ vì nhìn thấy timeout: đó là các thao tác vận hành có chi phí và mục đích riêng, cần chẩn đoán nguyên nhân trước.

### 8.4. Nếu lỗi xảy ra khi kết nối

Từ **máy chạy client**, kiểm tra:

~~~bash
# TCP: chỉ xác nhận khả năng mở socket, chưa kiểm tra CQL/auth.
nc -vz db.example.internal 9042

# Nếu endpoint yêu cầu TLS:
openssl s_client -connect db.example.internal:9042 \
  -servername db.example.internal
~~~

Trên Windows:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

Nếu cqlsh trên node chạy được nhưng ứng dụng ở container/VM ngoài không được, xem địa chỉ bind `rpc_address`, endpoint công bố `broadcast_rpc_address`, DNS, container network, firewall và TLS của **từng native peer**. Java Driver có thể kết nối contact point thành công nhưng lỗi ở các node được khám phá. Đây không phải `Unavailable` theo CL nếu native handshake với peer chưa hoàn tất.

## 9. Java Driver 4.x: in đúng ngữ cảnh lỗi, tránh lộ secrets

Đoạn minh họa sau dùng API Java Driver 4.x. Các giá trị kết nối phải đến từ cấu hình thực tế; với một cluster bật auth, cấu hình credentials tương ứng qua secret manager/biến môi trường có kiểm soát. Ví dụ bên dưới **giả định lab không bật auth/TLS** để tập trung vào đọc lỗi request.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;

public final class CassandraErrorDiagnostics {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT event_time, value " +
                "FROM error_diagnostics_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement statement = ps.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setTimeout(Duration.ofSeconds(5));

            for (Row row : session.execute(statement)) {
                System.out.println(
                    row.getInstant("event_time") + " : " +
                    row.getDouble("value"));
            }
        } catch (RuntimeException error) {
            // Log có kiểm soát: không in password, token hoặc bind values bí mật.
            System.err.println("Cassandra error type: " +
                error.getClass().getName());
            System.err.println("Message: " + error.getMessage());
            if (error.getCause() != null) {
                System.err.println("Cause type: " +
                    error.getCause().getClass().getName());
            }
            throw error; // Để tầng trên quyết định phản hồi/retry phù hợp.
        }
    }
}
~~~

**Lưu ý về ví dụ:**

- `datacenter1` là tên **giả định** cho lab; xem `SELECT data_center FROM system.local;` và dùng tên thật trong `withLocalDatacenter`.
- `setConsistencyLevel(ONE)` áp dụng **cho câu statement**, khác với lệnh `CONSISTENCY ONE;` của một phiên cqlsh khác.
- `setTimeout(Duration.ofSeconds(5))` là deadline **được đặt cho ví dụ**, không phải default bất biến của driver. Thời hạn thực tế phải dựa trên SLA và năng lực cluster.
- Nếu môi trường yêu cầu TLS/password, session phải cấu hình **SSL context tin cậy CA và auth credentials** tương ứng; không tắt bảo mật để “làm hết lỗi”.
- `getClass().getName()` và cause giúp nhận diện rõ **server-side errors** với **client-side errors**. Trong production, tổ chức cần cấu hình logger an toàn: message có thể chứa tên bảng, nội dung CQL, hostname hoặc giá trị nhạy cảm.
- Trong hệ thống thật nên thu thập thêm **request correlation ID, coordinator/endpoint, query name, CL, elapsed time, retry count** qua observability đã được duyệt; tránh log toàn bộ payload nhạy cảm.

### 9.1. Cách diễn giải các exception thường gặp trong Java

| Nhóm | Ý nghĩa ở Java Driver 4.x | Hành động phù hợp |
| --- | --- | --- |
| `SyntaxError` / lỗi truy vấn không hợp lệ (tên lớp cụ thể theo bản driver) | Server đã từ chối CQL. | Sửa query/schema/bind values, không retry nguyên trạng. |
| `AuthenticationException` | Không đăng nhập được khi tạo kết nối. | Kiểm tra auth và secrets, không retry password sai vô hạn. |
| `UnauthorizedException` | Câu lệnh bị từ chối quyền. | Cấp đúng quyền hoặc thay role theo policy; không hạ bảo mật. |
| `UnavailableException` | Không đủ replica ở CL yêu cầu. | Xem RF/topology, trạng thái node và CL. |
| `ReadTimeoutException` / `WriteTimeoutException` | Server/coordinator trả timeout của thao tác. | Xem số phản hồi, nguyên nhân replica chậm và idempotency. |
| `DriverTimeoutException` | Client hết deadline khi chưa nhận phản hồi phù hợp. | Xem client timeout, backlog, kết nối/latency; kết quả ghi có thể chưa xác định. |
| `AllNodesFailedException` | Driver không thiết lập/duy trì kết nối phù hợp đến các node. | Xem map lỗi theo từng node và nguyên nhân gốc: DNS/TCP/TLS/auth/protocol. |

**Không có công thức “bắt mọi exception rồi retry”.** Truy vấn sai cú pháp/permission là lỗi khó có thể khắc phục bằng retry. Timeout đọc có thể retry trong một số điều kiện; timeout ghi đòi hỏi hiểu idempotency và semantics dữ liệu. Với LWT, counter hoặc nghiệp vụ có hiệu ứng phụ, cần chính sách riêng.

## 10. Quy trình xử lý sự cố trong production

Khi nhận cảnh báo “Cassandra query failed”, thu thập đủ ngữ cảnh trước khi đổi cấu hình:

1. **Định danh request:** thời điểm, service/endpoint, cluster/datacenter, host/coordinator, keyspace/table, loại thao tác (đọc/ghi/LWT), query pattern và partition key có phù hợp không.
2. **Phân nhóm lỗi:** parse/schema, authentication, authorization, unavailable, server timeout, driver timeout hay connect/TLS.
3. **Xác nhận bản chất replica:** xem RF, CL, datacenter, số node cần/sống/đáp ứng và trạng thái ring theo `nodetool`.
4. **Đối chiếu thời gian:** so các mốc client/server, latency, GC, disk, network, compaction, streaming và log liên quan; phân biệt một node chậm với outage diện rộng.
5. **Đánh giá tác động nghiệp vụ:** request đã ghi một phần hoặc đã thành công trước timeout chưa? Có được phép retry không? Có cơ chế idempotency/reconciliation không?
6. **Khắc phục có kiểm soát:** sửa CQL, quyền, credentials, mạng, replica hoặc điều chỉnh timeout/CL theo chính sách. Theo dõi sau thay đổi.
7. **Ghi nhận nguyên nhân và phòng ngừa:** bổ sung metrics, alert, phân vùng hợp lý, giới hạn tải, kế hoạch repair/compaction và test tương thích Java Driver khi cần.

### 10.1. Những hành động cần tránh

- **Không** giảm CL sản xuất từ `LOCAL_QUORUM` xuống `ONE` chỉ để làm hết `Unavailable` mà chưa thống nhất mức nhất quán yêu cầu.
- **Không** tắt TLS, auth hoặc authorizer khi thấy lỗi đăng nhập/`Unauthorized`.
- **Không** chạy `TRACING ON` lâu trên traffic lớn hay mở rộng logging chứa password/bind values.
- **Không** retry mù các ghi không idempotent sau `WriteTimeout`, client timeout hoặc lỗi LWT.
- **Không** dùng `ALLOW FILTERING` như một cách chung để chữa câu truy vấn thiếu partition key.
- **Không** chạy `nodetool repair` hoặc `nodetool compact` để “chữa mọi timeout” nếu chưa biết nguyên nhân và chi phí.

## 11. Bảng tra nhanh: lỗi, câu hỏi và hướng sửa

| Lỗi đang thấy | Câu hỏi chẩn đoán đầu tiên | Hành động tiếp |
| --- | --- | --- |
| `SyntaxException` | Vị trí parser báo ở token nào? | Sửa syntax, kiểm tra kết thúc `;`, dấu nháy và keyword. |
| `InvalidRequest` | Cột, kiểu, primary key hoặc điều kiện lọc có đúng schema không? | `DESCRIBE TABLE` và sửa query/mô hình bảng. |
| `AuthenticationFailed` | Server có nhận đúng credentials và TLS không? | Kiểm tra role login, secret rotation, auth backend, CA/SAN. |
| `Unauthorized` | User thật sự có permission trên resource không? | Xem `GRANT`, role inheritance, authorizer/cache. |
| `Unavailable` | Required vs alive replica bao nhiêu, CL và RF ra sao? | Xem `DESCRIBE KEYSPACE`, `nodetool status`, internode/topology. |
| `ReadTimeout` | Bao nhiêu phản hồi đã đến, node nào chậm, query có hot/large partition không? | Metrics, logs, tracing chọn lọc, GC/compaction/tombstones. |
| `WriteTimeout` | Đã có replica nào ghi rồi? Request có idempotent không? | Đối soát trạng thái và chỉ retry theo chính sách an toàn. |
| `DriverTimeoutException` | Deadline client là bao lâu và server đã xử lý tới đâu? | Xem network/queue/latency, client config và server logs. |
| `AllNodesFailedException` | Những native endpoints nào bị lỗi, tại bước nào? | Kiểm tra DNS, 9042, TLS/auth, discovery, local datacenter. |

## 12. Bài tập thực hành và tự đánh giá

1. Dựng lab `error_diagnostics_lab`, chạy một `SELECT` đúng để có **mốc đối chiếu**; ghi lại keyspace, partition key và CL hiện tại.
2. Cố ý để dấu phẩy thừa trước `FROM`. Tìm token được báo trong `SyntaxException` và sửa lại câu truy vấn.
3. Thử truy vấn chỉ có `event_time` trong `WHERE`. Giải thích vì sao đây là lỗi **mô hình truy vấn/InvalidRequest**, không đơn thuần thiếu dấu phẩy.
4. Trong cluster lab có auth, phân biệt trường hợp nhập sai mật khẩu với trường hợp đăng nhập thành công nhưng role không được `SELECT`. Nêu công cụ và người có quyền cần tham gia khi sửa.
5. Trên lab RF = 1, đặt `CONSISTENCY TWO` rồi đọc một partition. Dự đoán lỗi, đối chiếu với RF, sau đó **đặt lại `CONSISTENCY ONE`**.
6. Với cluster lý thuyết **RF = 3 một DC**, tính số replica cần cho `ONE`, `QUORUM`, `ALL`; cho biết hai lỗi `Unavailable` và `ReadTimeout` khác nhau thế nào khi chỉ một hoặc hai replica phản hồi.
7. Giả sử `INSERT` trả `WriteTimeout` nhưng một replica đã ghi dữ liệu. Vì sao tự retry một thao tác tăng counter có thể sai? Đề xuất cách đối soát.
8. Giả sử Java báo `DriverTimeoutException` sau 5 giây trong khi CQL có thể vẫn đang thực thi. Tại sao không được kết luận server đã hủy câu lệnh?
9. Bật `TRACING ON` cho một `SELECT` nhỏ, đọc trace rồi `TRACING OFF`. Liệt kê các metrics/log cần xem thêm nếu trace không đủ kết luận.
10. Java Driver kết nối contact point nhưng báo `AllNodesFailedException` tại peer được công bố bằng IP container. Nêu cách phân biệt đây là lỗi native networking/driver discovery, không phải Unavailable do CL.

**Tiêu chí hoàn thành:** bạn có thể giải thích bằng ngữ cảnh cụ thể tại sao lỗi xuất hiện, phân biệt lỗi parse/auth/quyền/replica/deadline, biết dùng đúng câu kiểm tra và nêu được **một hành động khắc phục an toàn** cho mỗi nhóm.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY`, `TRACING`, `DESCRIBE` và thao tác kết nối.
- [Apache Cassandra — CQL documentation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): cú pháp CQL, primary key, bảng, `INSERT`, `SELECT` và điều kiện truy vấn.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): coordinator/replica, replication và các mức consistency.
- [Apache Cassandra — Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization và cấu hình bảo mật.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): quan sát trạng thái node, gossip, streaming và compaction.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): sessions, statements, timeout, consistency, execution và exceptions.
- [Apache Cassandra Java Driver 4.x — Retry policy](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/index.html): idempotence và cách lựa chọn retry theo lỗi.
