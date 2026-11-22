# Chứng thực, thông tin đăng nhập và kết nối TLS

## 1. Vì sao kết nối được Cassandra chưa có nghĩa là truy cập an toàn?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Ứng dụng Java hoặc `cqlsh` kết nối đến một node qua **native protocol**, mặc định trên cổng TCP **9042**; node này làm coordinator và chuyển yêu cầu đến các replica theo partition key, replication và consistency. Đường truyền mạng hoạt động mới chỉ là điều kiện đầu tiên. Một hệ thống thực tế còn phải biết **client đang nói chuyện với server nào, client là ai, và client được phép làm gì**.

Ba cơ chế giải quyết ba câu hỏi độc lập:

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **TLS (Transport Layer Security)** | Dữ liệu có được mã hóa khi truyền? Client có xác minh đúng server không? | Java Driver xác minh chứng chỉ server của `db.example.internal` do CA tổ chức phát hành. |
| **Authentication (xác thực)** | Danh tính đăng nhập của client là ai? | `PasswordAuthenticator` kiểm tra username/password của role `report_reader`. |
| **Authorization (phân quyền)** | Danh tính đã xác thực có được chạy câu CQL cụ thể không? | Role `report_reader` chỉ được `SELECT` một bảng, không được `INSERT` hoặc `DROP`. |

Kết nối TCP, TLS handshake và CQL login là **các bước khác nhau**. Một kết nối có thể qua được TLS nhưng đăng nhập thất bại; hoặc đăng nhập được nhưng bị `Unauthorized` vì thiếu quyền.

Bài thuộc chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, liên quan trực tiếp đến truy cập dữ liệu theo partition key, replication của keyspace, mức consistency đọc ghi và vận hành ứng dụng Java. Hiểu các lớp bảo vệ giúp triển khai, quan sát và xử lý lỗi Cassandra mà không nhầm vấn đề bảo mật với lỗi CQL hay topology.

**Sau bài học, bạn có thể:**

1. Phân biệt TLS, username/password, role và CQL permissions.
2. Hiểu các lựa chọn cấu hình `authenticator`, `authorizer` và `client_encryption_options` theo phiên bản Cassandra.
3. Tạo role chỉ đọc, cấp quyền tối thiểu và xác nhận một thao tác bị từ chối đúng thiết kế.
4. Kết nối cqlsh và Java Driver 4.x với TLS, CA tin cậy và credentials.
5. Chẩn đoán lỗi từ DNS/TCP, TLS handshake đến authentication/authorization và lỗi consistency sau khi đăng nhập.
6. Đề xuất cách bảo vệ, luân chuyển credentials/chứng chỉ và quản lý quyền trong cluster nhiều node.

## 2. Luồng kết nối: mạng → TLS → xác thực → cấp quyền → truy vấn

~~~mermaid
sequenceDiagram
    participant App as cqlsh / Java Driver
    participant Node as Cassandra native endpoint
    participant Replica as Replica của partition
    App->>Node: TCP đến host:9042
    opt Native transport được bật TLS
        App->>Node: TLS ClientHello / kiểm tra CA, hostname
        Node-->>App: TLS handshake và chứng chỉ server
    end
    App->>Node: Native protocol STARTUP
    opt Server yêu cầu đăng nhập
        Node-->>App: AUTHENTICATE
        App->>Node: AUTH_RESPONSE với credentials
        Node-->>App: AUTH_SUCCESS hoặc ERROR
    end
    App->>Node: QUERY/EXECUTE với CQL và consistency
    Node->>Node: Kiểm tra permission của role
    alt Có quyền
        Node->>Replica: Yêu cầu tới replica cần thiết
        Replica-->>Node: Phản hồi đọc/ghi
        Node-->>App: RESULT hoặc lỗi thực thi
    else Không có quyền
        Node-->>App: Unauthorized
    end
~~~

Sơ đồ thể hiện luồng điển hình, không cố định số lần trao đổi hay mọi loại thông điệp của từng phiên bản protocol. TLS (nếu được bật) bảo vệ kết nối **client ↔ node**; các kết nối **node ↔ node** có cơ chế TLS riêng. Sau khi xác thực thành công, Cassandra vẫn phải xét quyền mỗi thao tác.

**Tách biệt quan trọng:**

- **TLS server authentication** xác minh server bằng chứng chỉ. Nó không tự chứng minh username/password Cassandra hợp lệ.
- **mTLS (mutual TLS)** có thêm bước server yêu cầu chứng chỉ client. Chứng chỉ client chỉ trở thành danh tính CQL khi hệ thống cấu hình **authenticator hỗ trợ ánh xạ chứng chỉ sang role**, không tự động thay thế mọi cơ chế password.
- **CQL authentication** khác **JMX authentication** mà công cụ quản trị `nodetool` có thể sử dụng.
- **TLS của native transport** cấu hình khác **TLS internode**. Bảo vệ 9042 không tự mã hóa giao tiếp giữa các node trên 7000.

## 3. Cấu hình authentication và authorization

Trong Cassandra, `cassandra.yaml` có các thuộc tính liên quan đến đăng nhập/phân quyền. Ví dụ cơ bản cho những bản hỗ trợ các thành phần sau:

~~~yaml
# Trích đoạn khái niệm, không phải file production hoàn chỉnh.
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
role_manager: CassandraRoleManager
~~~

| Thành phần | Mục đích |
| --- | --- |
| `AllowAllAuthenticator` | Không yêu cầu xác thực danh tính bằng username/password. Chỉ phù hợp môi trường kiểm soát chặt, ví dụ lab cô lập. |
| `PasswordAuthenticator` | Xác thực role Cassandra bằng username/password qua native protocol. |
| `AllowAllAuthorizer` | Không áp đặt kiểm tra quyền CQL theo role; không phù hợp hệ thống cần phân quyền. |
| `CassandraAuthorizer` | Kiểm soát các quyền CQL như `SELECT`, `MODIFY`, `CREATE` và `ALTER`. |
| `CassandraRoleManager` | Quản lý role, đăng nhập và các quan hệ role trong Cassandra. |

**Không tự ý bật `PasswordAuthenticator` nhưng giữ `AllowAllAuthorizer` trong hệ cần hạn chế quyền**: người đăng nhập thành công khi đó vẫn có thể được phép thực hiện nhiều thao tác hơn dự kiến. Ngược lại, chỉ bật authorizer mà không có chiến lược cấp quyền/đăng nhập phù hợp dễ làm ứng dụng mất truy cập.

Việc đổi `authenticator`, `authorizer` hoặc TLS liên quan đến cấu hình node và thường cần quản lý khởi động/rolling restart theo phiên bản. Trên cluster đang phục vụ ứng dụng, phải chuẩn bị role, thông tin đăng nhập, certificate/truststore và kiểm tra đường truy cập quản trị trước khi áp dụng; không thử thay cấu hình trực tiếp trên production như một thao tác lab.

### 3.1. Role, login và permission không phải một

Một **role** có thể đại diện cho danh tính đăng nhập, nhóm quyền hoặc cả hai. Role có `LOGIN = true` có thể được dùng để đăng nhập nếu authenticator hỗ trợ; role không có `LOGIN` có thể dùng để nhóm quyền.

Ví dụ trong một cluster đã bật `PasswordAuthenticator` + `CassandraAuthorizer` và phiên cqlsh hiện tại có quyền quản trị role:

~~~sql
-- Lệnh mẫu: thay bằng mật khẩu mạnh, chỉ dùng trên môi trường lab.
-- Cần tránh để password thật xuất hiện trong history, log và file CQL.
CREATE ROLE IF NOT EXISTS report_reader
WITH PASSWORD = 'REPLACE_WITH_A_UNIQUE_LAB_SECRET'
AND LOGIN = true;

-- Xem các role mà tài khoản hiện tại có quyền liệt kê.
LIST ROLES;
~~~

Chuỗi `REPLACE_WITH_A_UNIQUE_LAB_SECRET` **chỉ là placeholder**, không phải mật khẩu để sử dụng. Vì câu CQL `CREATE ROLE ... PASSWORD ...` chứa plaintext secret, một quy trình thật cần hạn chế/kiểm soát lịch sử lệnh, quyền xem log, đường truyền TLS, file script và hệ thống lưu vết. Dùng công cụ provision role/quản lý secrets của tổ chức khi có.

**Lưu ý:** role có `LOGIN = true` không đồng nghĩa được phép đọc mọi bảng. Quyền CQL vẫn được cấp độc lập. Trong nhiều hệ thống, nên tạo role quyền không có login, sau đó cấp role đó cho các danh tính đăng nhập cần dùng chung permission.

### 3.2. Ví dụ cấp quyền tối thiểu vào một bảng

Để lab tự chứa, giả sử session quản trị đã kết nối vào cluster **đơn node**. Tạo keyspace và bảng theo truy vấn “đọc sự kiện của một thiết bị theo ngày”:

~~~sql
CREATE KEYSPACE IF NOT EXISTS security_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS security_lab.readings_by_device_day (
  device_id text,
  reading_day date,
  reading_time timestamp,
  reading_id uuid,
  value double,
  PRIMARY KEY ((device_id, reading_day), reading_time, reading_id)
) WITH CLUSTERING ORDER BY (reading_time DESC, reading_id ASC);

INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 25.3);

GRANT SELECT ON TABLE security_lab.readings_by_device_day
TO report_reader;
~~~

`SimpleStrategy`/RF = 1 chỉ dành cho lab một node. Ở cluster thật, nên xem xét `NetworkTopologyStrategy` cùng số replica theo datacenter thực tế; số replica không liên quan đến việc role có quyền nào.

Với role chỉ đọc, thử kết nối ở phiên khác rồi chạy:

~~~sql
SELECT reading_time, value
FROM security_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 10;
~~~

Kết quả kỳ vọng có hai hàng, giá trị đọc hợp lệ, thời gian mới nhất đứng trước do clustering order. Điều kiện `WHERE` bao gồm **composite partition key** `(device_id, reading_day)`, phù hợp bảng được thiết kế theo truy vấn.

Thử thao tác không được cấp quyền:

~~~sql
-- Thực thi bằng report_reader, không phải tài khoản admin.
INSERT INTO security_lab.readings_by_device_day
  (device_id, reading_day, reading_time, reading_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:10:00Z',
        33333333-3333-4333-8333-333333333333, 25.7);
~~~

Khi role chỉ được cấp `SELECT`, câu `INSERT` phải bị từ chối quyền (thường là `Unauthorized`). Nếu lệnh vẫn chạy thành công, hãy xem lại authorizer, superuser flag, role inheritance và các quyền đã được cấp trước đó. Không nên kết luận chỉ từ một dòng `GRANT` mà bỏ qua các quyền kế thừa khác.

### 3.3. GRANT/REVOKE và xác minh quyền

~~~sql
-- Dùng từ phiên quản trị khi cần kiểm tra permission.
LIST ALL PERMISSIONS OF report_reader;

-- Ví dụ lệnh thu hồi quyền khi thay đổi yêu cầu nghiệp vụ.
REVOKE SELECT ON TABLE security_lab.readings_by_device_day
FROM report_reader;

-- Khôi phục quyền cho các bước thực hành tiếp theo.
GRANT SELECT ON TABLE security_lab.readings_by_device_day
TO report_reader;
~~~

Một số phiên bản/tùy chọn quyền và cách hiển thị `LIST ... PERMISSIONS` có thể khác. Nếu vừa `GRANT`/`REVOKE`, bộ nhớ đệm quyền (authorization cache) có thể khiến thay đổi cần một khoảng thời gian để hiện ở các node; điều chỉnh/kiểm chứng theo cấu hình cluster. Không suy đoán `REVOKE` đã có hiệu lực tức thì trên mọi request đang chạy.

### 3.4. Auth state và hệ thống phân tán

Khi dùng các provider của Cassandra, dữ liệu role/permission được quản lý trong **system_auth**. Trên cluster nhiều node, phải xem xét replication của keyspace này để tránh sự cố một node ảnh hưởng đăng nhập hoặc quản lý quyền. Cấu hình replication của `system_auth` theo chiến lược/datacenter phù hợp là **việc quản trị cluster riêng**, có thể cần repair sau khi thay đổi; không chỉnh sửa trực tiếp các bảng hệ thống bằng các câu `INSERT` tự chế.

Cần dự kiến cách một thay đổi role/password được các node quan sát qua cache và replication; đồng thời bảo đảm các tài khoản quản trị phục hồi vẫn dùng được trong kế hoạch thay cấu hình.

## 4. TLS cho kết nối client ↔ Cassandra

TLS bảo vệ dữ liệu (bao gồm credentials và nội dung truy vấn) trên đường mạng giữa client và Cassandra. TLS còn giúp client xác minh chứng chỉ đúng của server; nếu tắt xác minh, một kết nối “đã mã hóa” vẫn có thể bị chuyển tới server giả mạo.

### 4.1. Cassandra server: client_encryption_options

Ví dụ **chỉ minh họa cấu trúc**, theo các phiên bản Cassandra dùng keystore kiểu JKS:

~~~yaml
# cassandra.yaml - chỉ minh họa; đường dẫn và bí mật là placeholder.
client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: false
  keystore: /secure/cassandra/server-keystore.jks
  keystore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
~~~

Ý nghĩa:

- `enabled: true`: bật TLS cho native client transport trong cấu hình phiên bản hỗ trợ.
- `optional: false`: yêu cầu các kết nối client dùng TLS; trong những phiên bản cho phép `optional: true`, có thể chấp nhận cả client TLS và plaintext khi phục vụ chuyển đổi có kiểm soát.
- `keystore`: nơi chứa chứng chỉ và private key server; quản lý quyền file chặt chẽ.
- `keystore_password`: bí mật cần cấp bằng **cơ chế quản lý secrets an toàn** của hệ thống triển khai. Chuỗi trên không phải mật khẩu thật và không nên commit mật khẩu thực vào repository.
- `require_client_auth: false`: không yêu cầu client cung cấp chứng chỉ của chính nó ở tầng TLS. Client vẫn có thể phải đăng nhập bằng role/password Cassandra.

**Không sao chép nguyên ví dụ vào production.** Cú pháp, tên tùy chọn và format keystore/PEM có thể khác theo phiên bản Cassandra/Java đang sử dụng. Một số bản hỗ trợ thêm kiểu cấu hình chứng chỉ hoặc định dạng khác; phải đối chiếu tài liệu đúng phiên bản, cách cung cấp secrets và thực tế chứng chỉ.

### 4.2. Xác minh chứng chỉ server: CA, SAN và hostname

Khi kết nối tới `db.example.internal`:

1. Client mở TCP đúng host/port native.
2. Nếu server yêu cầu TLS, nó gửi chứng chỉ server trong handshake.
3. Client xác minh **chuỗi CA tin cậy**, thời hạn, công dụng chứng chỉ và tên đích kết nối (thường dựa trên **SAN**, Subject Alternative Name).
4. Nếu xác minh đúng, native protocol mới tiếp tục trao đổi auth/CQL qua kênh được bảo vệ.

Ví dụ chứng chỉ được cấp cho `db-a.example.internal` thì Java client kết nối bằng IP `10.0.2.15` có thể bị lỗi hostname verification nếu chứng chỉ không có **IP SAN** tương ứng. Đổi sang địa chỉ IP khác không sửa chứng chỉ. Có thể dùng tên DNS đã được ghi trong SAN hoặc phát hành chứng chỉ phù hợp endpoint ứng dụng.

Trong cluster nhiều node, driver có thể kết nối tới các **peer native endpoints đã khám phá**. Chứng chỉ của mỗi node/endpoint cần phù hợp địa chỉ mà client sử dụng, nhất là khi có DNS, NAT, Kubernetes hoặc proxy. Kết nối được contact point đầu tiên không chứng minh tất cả peer sẽ qua TLS.

### 4.3. mTLS: chứng chỉ hai chiều

Nếu tổ chức yêu cầu client xuất trình chứng chỉ riêng, cấu hình server có thể gồm:

~~~yaml
# Bổ sung theo cấu hình/phiên bản có hỗ trợ mTLS.
client_encryption_options:
  enabled: true
  optional: false
  require_client_auth: true
  keystore: /secure/cassandra/server-keystore.jks
  keystore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
  truststore: /secure/cassandra/client-ca-truststore.jks
  truststore_password: "REPLACE_VIA_SECRET_MANAGEMENT"
~~~

`require_client_auth: true` yêu cầu phía client xuất trình chứng chỉ TLS hợp lệ, và server cần tin tưởng CA của client qua truststore phù hợp. Java Driver/cqlsh lúc này cần cung cấp **client certificate + private key** theo API/cấu hình SSL được phiên bản hỗ trợ.

**mTLS không mặc định biến Subject DN của chứng chỉ thành role Cassandra.** Nếu Cassandra vẫn sử dụng `PasswordAuthenticator`, client có thể phải cung cấp **cả chứng chỉ TLS và username/password**. Nếu dùng authenticator dựa trên chứng chỉ do phiên bản hoặc môi trường hỗ trợ, cần quy định rõ ánh xạ certificate identity sang role và cách thu hồi/quản lý chứng chỉ.

### 4.4. Native TLS trên cổng nào?

Thông thường native CQL sử dụng `9042/TCP`, và Cassandra có thể được cấu hình TLS **ngay trên cổng này**. Một số bản/cấu hình lịch sử có thêm cổng native TLS riêng thường minh họa là **9142**, nhưng cổng phụ **không tự có**; trong Cassandra 5.0 tùy chọn `native_transport_port_ssl` được đánh dấu deprecated.

Không suy luận `9042 = plaintext` hoặc `9142 = luôn có TLS`. Xác nhận listener và `client_encryption_options` của bản đang chạy, rồi thử TLS handshake.

**TLS internode là đường khác:** `server_encryption_options` bảo vệ giao tiếp giữa các node, thường qua `storage_port`, mặc định 7000; cổng TLS internode legacy 7001 chỉ dùng nếu deployment thực sự cấu hình. Bật TLS native không tự mã hóa mạng internode.

## 5. cqlsh: kết nối an toàn và quản lý credentials

### 5.1. Kết nối khi chỉ yêu cầu username/password

Từ máy có cqlsh:

~~~bash
# Server bật PasswordAuthenticator, không yêu cầu TLS: chỉ thích hợp lab cô lập.
cqlsh 127.0.0.1 9042 -u report_reader
~~~

Tùy phiên bản, cqlsh sẽ hỏi mật khẩu khi không truyền tham số `-p`, hoặc cần cấu hình credentials phù hợp. **Tránh cung cấp mật khẩu trực tiếp trên command line**, vì có thể lộ qua lịch sử shell, danh sách tiến trình hoặc log của hệ thống giám sát.

Không sử dụng kết nối password plaintext trên đường mạng không tin cậy: thông tin đăng nhập của native protocol cần được bảo vệ bằng TLS.

### 5.2. Kết nối TLS và kiểm tra CA

~~~bash
# Kết nối native transport có bật TLS.
cqlsh db.example.internal 9042 --ssl -u report_reader
~~~

Ở các phiên bản cqlsh có cấu hình `cqlshrc`, phần TLS có thể dùng tương đương:

~~~ini
# Ví dụ phần [ssl] trong cqlshrc (đối chiếu với bản cqlsh đang dùng).
[ssl]
validate = true
certfile = /secure/ca/cassandra-ca.pem
~~~

`validate = true` yêu cầu kiểm tra chứng chỉ server theo hành vi cqlsh phiên bản đang chạy; `certfile` chỉ ra CA certificate được tin cậy trong các bản dùng định dạng này. **Phải xác minh thêm hostname/SAN và chính sách verify thực tế**: cách kiểm tra hostname của cqlsh có thể khác thư viện TLS/phiên bản, nên không mặc định chỉ bật `--ssl` là đủ kiểm chứng server identity. Không tắt certificate verification để xử lý lâu dài lỗi CA.

Tùy phiên bản, cqlsh hỗ trợ cấu hình user/cert/key, tệp credentials được bảo vệ hoặc cơ chế xác thực khác. Hãy xem `cqlsh --help` và hướng dẫn `cqlshrc` của bản Cassandra tương ứng; tránh commit `cqlshrc` chứa plaintext password hoặc private key. Trên môi trường dùng mTLS, cần cấu hình thêm chứng chỉ và private key client theo bản cqlsh.

### 5.3. Kiểm tra sau khi đăng nhập

~~~sql
SHOW HOST;
SHOW VERSION;

-- Query kiểm tra phiên nếu role có quyền phù hợp.
SELECT reading_time, value
FROM security_lab.readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21';
~~~

Một phiên không có `CREATE`/`ALTER`/`MODIFY` vẫn có thể truy vấn các bảng được cấp `SELECT`. Đăng nhập thành công không đồng nghĩa được xem toàn bộ keyspace; để phát hiện quyền thiếu, thử **chính câu truy vấn ứng dụng cần dùng**.

## 6. Java Driver 4.x: TLS, credentials và câu truy vấn có tham số

Giả sử tổ chức đã phát hành CA và cấu hình JVM truststore chứa chứng chỉ CA tin cậy. Đoạn Java sau minh họa Java Driver 4.x với `PasswordAuthenticator`, TLS server authentication và prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import javax.net.ssl.SSLContext;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public final class CassandraTlsDemo {
    public static void main(String[] args) throws Exception {
        String host = System.getenv("CASSANDRA_HOST");
        String dc = System.getenv("CASSANDRA_DC");
        String username = System.getenv("CASSANDRA_USER");
        String password = System.getenv("CASSANDRA_PASSWORD");
        if (host == null || dc == null || username == null || password == null) {
            throw new IllegalStateException("Thiếu cấu hình kết nối Cassandra");
        }

        // SSLContext mặc định dựa trên truststore của JVM.
        // Phải cấu hình CA tin cậy và kiểm tra hostname cho môi trường thực.
        SSLContext tlsContext = SSLContext.getDefault();

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .withAuthCredentials(username, password)
                .withSslContext(tlsContext)
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT reading_time, value " +
                "FROM security_lab.readings_by_device_day " +
                "WHERE device_id = ? AND reading_day = ?");

            for (Row row : session.execute(
                    query.bind("sensor-01", LocalDate.of(2026, 11, 21)))) {
                System.out.println(
                    row.getInstant("reading_time") + " : " +
                    row.getDouble("value"));
            }
        }
    }
}
~~~

**Điều kiện chạy ví dụ:**

- Đã tạo bảng `security_lab.readings_by_device_day` và cấp quyền `SELECT` cho `report_reader` như mục 3.
- Cluster bật TLS và role/password; `CASSANDRA_HOST` là **native endpoint có thể truy cập**, `CASSANDRA_DC` trùng tên datacenter thực. Có thể tra `SELECT data_center FROM system.local;` bằng phiên quản trị/cqlsh phù hợp.
- JVM đã được cấu hình **truststore đúng CA**; chỉ lấy `SSLContext.getDefault()` không tự thêm CA nội bộ của tổ chức vào JVM.
- TLS config của Java Driver 4.x phải thực sự bật **hostname verification** theo cấu hình driver và endpoint đang dùng. SSLContext mặc định **không phải lời đảm bảo đủ mọi chính sách xác minh tên host**; cần đối chiếu tài liệu bản driver và kiểm tra negative test.
- Nếu Cassandra yêu cầu **mTLS**, còn phải đưa client key/certificate vào `SSLContext`; chỉ truststore để xác minh server là chưa đủ.

Các biến môi trường làm rõ đầu vào nhưng **không phải hệ thống quản lý secrets**: trong production, nên lấy password/tokens/certificates từ secret manager của tổ chức, hạn chế quyền đọc biến môi trường hoặc file mount, không ghi secret ra log.

`CqlSession` nên có vòng đời dài trong service và được tái sử dụng; ví dụ `try-with-resources` đóng session khi chương trình demo kết thúc. Java Driver có thể khám phá nhiều peer native endpoints, nên chứng chỉ, routing và quyền trên **toàn bộ các node client được phép kết nối** cần thống nhất. Nếu app chỉ kết nối được contact point mà không kết nối được peer, xem `broadcast_rpc_address`, NAT, DNS, TLS certificate và local datacenter.

### 6.1. Phân biệt lỗi TLS với query, replication và consistency

Khi Java Driver thông báo `AllNodesFailedException`, đừng quy mọi lỗi về mật khẩu. Các nguyên nhân trên từng node có thể là DNS, port, TLS, native protocol mismatch, auth hoặc endpoint không reachable. Nếu kết nối đã thành công nhưng `ReadTimeout`, `WriteTimeout` hoặc `Unavailable`, phải xem replica, consistency, network internode và tải hệ thống. Tăng RF hay thay CL không sửa lỗi chứng chỉ; đổi password không sửa partition key.

## 7. Quản lý vòng đời credentials và chứng chỉ

### 7.1. Nguyên tắc quyền tối thiểu

Thực tế nên tách các vai trò:

| Vai trò | Đặc điểm | Ví dụ quyền |
| --- | --- | --- |
| **Admin vận hành có kiểm soát** | Quản lý schema/role theo quy trình được cấp phép. | Quyền tạo role, thay đổi keyspace/bảng khi thực sự cần. |
| **Application reader** | Đăng nhập cho service chỉ đọc. | `SELECT` trên bảng mà service đọc. |
| **Application writer** | Đăng nhập cho service ghi. | `MODIFY`/`SELECT` tùy truy vấn thực tế, chỉ trên tài nguyên cần thiết. |
| **Role nhóm quyền** | `LOGIN = false`, dùng làm nhóm permission. | Được cấp quyền CQL rồi cấp lại cho các login role phù hợp. |

Không dùng tài khoản superuser chung cho mọi ứng dụng; hạn chế reuse mật khẩu giữa môi trường. Cấp quyền ở phạm vi **TABLE** khi có thể, mở rộng lên KEYSPACE khi có nhu cầu nghiệp vụ rõ ràng.

### 7.2. Luân chuyển password

Trong môi trường chỉ có username/password, có thể quản lý việc đổi mật khẩu role bằng lệnh CQL thích hợp (chạy từ tài khoản đủ quyền):

~~~sql
-- Chỉ là mẫu cú pháp, placeholder KHÔNG phải password được dùng thật.
ALTER ROLE report_reader
WITH PASSWORD = 'REPLACE_WITH_NEW_UNIQUE_SECRET';
~~~

Nếu đổi mật khẩu tại chỗ trong lúc ứng dụng đang chạy, các kết nối native đã được xác thực có thể tiếp tục tồn tại trong một khoảng thời gian, trong khi kết nối mới dùng secret cũ sẽ thất bại. Vì vậy, cần đồng bộ secret manager và quy trình rollout/connection refresh. Với độ sẵn sàng cao, cân nhắc mô hình **hai danh tính thay phiên**: cấp quyền tương đương, triển khai credential mới, xác nhận traffic mới thành công rồi thu hồi credential cũ. Không giả định xoay password là thao tác nguyên tử đối với tất cả kết nối đang sống.

**Đừng ghi mật khẩu thật vào file `.cql` lưu trong Git**, lịch sử shell, screenshot, ticket hoặc kết quả tracing. Cân nhắc trường hợp log hệ thống/giám sát có thể ghi CQL statement chứa secret khi tạo role.

### 7.3. Luân chuyển chứng chỉ và CA

Quy trình thường gồm:

1. Chuẩn bị CA/truststore mới và các chứng chỉ server/client với SAN phù hợp endpoint thật.
2. Có giai đoạn **chồng lấp trust** nếu cần đổi CA để client còn tin cả chứng chỉ cũ và mới trong lúc rolling rollout.
3. Triển khai truststore/keystore/cấu hình server và client theo phiên bản, bảo đảm quản lý reload/restart hợp lệ.
4. Kiểm tra TLS tới **nhiều node**, bao gồm peer sau driver discovery, không chỉ một contact point.
5. Sau khi chuyển đổi xong và kiểm tra, gỡ CA/cert cũ và cập nhật quy trình cấp phát/thu hồi.

TLS certificate hết hạn, thiếu SAN hoặc CA không được tin cậy thường gây lỗi **handshake**, trước khi Cassandra kịp kiểm tra role/password. Thời gian đồng hồ node/client sai có thể làm chứng chỉ bị coi là chưa hiệu lực/hết hạn; kiểm tra đồng bộ thời gian khi gặp lỗi liên quan thời hạn.

## 8. Chẩn đoán lỗi theo từng lớp

~~~mermaid
flowchart TD
    A["Client Java/cqlsh kết nối tới host:9042"] --> B{"DNS/IP và TCP reachable?"}
    B -->|"Không"| C["Kiểm tra hostname, listener, firewall, route, container"]
    B -->|"Có"| D{"Server yêu cầu TLS?"}
    D -->|"Có"| E{"TLS handshake và verify thành công?"}
    E -->|"Không"| F["Kiểm tra CA, SAN/hostname, keystore, TLS mode, mTLS"]
    E -->|"Có"| G{"Đăng nhập Cassandra thành công?"}
    D -->|"Không"| G
    G -->|"Không"| H["Kiểm tra authenticator, role LOGIN, mật khẩu, auth backend"]
    G -->|"Có"| I{"CQL được cấp quyền?"}
    I -->|"Không"| J["Kiểm tra authorizer, GRANT/REVOKE, role kế thừa"]
    I -->|"Có"| K["Kiểm tra truy vấn, partition key, RF, consistency, replica"]
~~~

| Hiện tượng | Lớp lỗi có khả năng | Cần kiểm tra |
| --- | --- | --- |
| `Connection refused` tới 9042 | Native listener/TCP | Host/IP/port, `start_native_transport`, `rpc_address`, firewall reject. |
| TCP timeout | Routing/firewall/container/cloud security group | Thử từ **chính máy chạy client** đến IP và port đích. |
| `SSLHandshakeException` hoặc `certificate verify failed` | TLS | Client/server cùng chế độ TLS? CA, certificate chain, hạn chứng chỉ, SAN/hostname, mTLS keypair. |
| `wrong version number` hoặc tương đương | TLS mismatch/nhầm cổng | Một phía nói plaintext, phía kia nói TLS; xác nhận native TLS port. |
| `AuthenticationException` / thông báo credentials sai | Authentication | `PasswordAuthenticator`, role `LOGIN`, mật khẩu hiện tại, account state, auth keyspace. |
| `Unauthorized` với `SELECT` / `INSERT` | Authorization | `CassandraAuthorizer`, quyền trên bảng/keyspace, role inheritance/cache, user thực sự được dùng. |
| Admin đăng nhập được nhưng app không | Credential/role/cấu hình app | So sánh endpoint, TLS, username, role privileges và secret được deploy cho app. |
| Kết nối contact point được nhưng peer khác lỗi | Topology/native endpoints | `broadcast_rpc_address`, DNS, routing, cert của từng peer, local DC và logs driver. |
| `ReadTimeout`, `WriteTimeout`, `Unavailable` | Replica/CL/đường internode | Replication factor, consistency, số replica sẵn sàng, tải, compaction, mạng 7000. |
| Query thiếu partition key hoặc bị từ chối lọc | CQL và thiết kế bảng | `DESCRIBE TABLE`, primary key, query pattern; không chỉnh TLS/GRANT để chữa. |
| `nodetool` không kết nối được nhưng cqlsh vào được | JMX/quản trị | Cấu hình JMX/7199 và quyền quản trị riêng, không nhầm với native 9042. |

### 8.1. Thử TLS và TCP trước khi sửa mật khẩu

Trên Linux/macOS, từ máy client:

~~~bash
# Chỉ kiểm tra TCP.
nc -vz db.example.internal 9042

# Với server thực sự bật TLS: thử handshake và chỉ định CA tin cậy.
# Một số bản OpenSSL hỗ trợ -verify_hostname; kiểm tra openssl s_client -help.
openssl s_client \
  -connect db.example.internal:9042 \
  -servername db.example.internal \
  -CAfile /secure/ca/cassandra-ca.pem \
  -verify_return_error \
  -verify_hostname db.example.internal
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

`nc` và `Test-NetConnection` chỉ chứng minh TCP có thể mở, chưa chứng minh TLS, native handshake, CQL login và permissions. `openssl s_client` thử TLS và xác minh theo các tùy chọn đã truyền, **không xác minh quyền CQL**. `-servername` gửi SNI; nó không đồng nghĩa với kiểm tra hostname nếu không bật cơ chế xác minh tên phù hợp.

### 8.2. Kiểm tra quyền bằng chính danh tính ứng dụng

Giả sử app dùng `report_reader`, hãy thực hiện truy vấn `SELECT` đúng bảng mà app cần, sau đó thử thao tác ghi bị cấm trong **lab**. Nếu `SELECT` thành công nhưng `INSERT` bị `Unauthorized`, xác thực lẫn phân quyền hoạt động đúng theo thiết kế chỉ đọc.

Với lỗi role/permission, kiểm tra logs và cấu hình auth/cache theo phiên bản. Không sử dụng tài khoản admin để kiểm tra rồi kết luận ứng dụng cũng có quyền tương tự. Nếu đổi permission hoặc password, theo dõi độ trễ lan truyền/caching trên cluster và sự khác nhau giữa kết nối cũ với kết nối mới.

## 9. Bài tập tự thực hành

1. Vẽ luồng **TCP → TLS → PasswordAuthenticator → CassandraAuthorizer → coordinator/replica**. Chỉ ra bước nào trả lỗi nếu CA không tin cậy, mật khẩu sai và role thiếu `SELECT`.
2. Cấu hình lab bật username/password và tạo role `report_reader` chỉ có `SELECT` trên `security_lab.readings_by_device_day`. Xác minh role không được phép `INSERT`.
3. Dùng `cqlsh -u report_reader --ssl` với CA tin cậy theo bản cqlsh. Giải thích vì sao `--ssl` và username/password có nhiệm vụ khác nhau.
4. Giả sử cert server chỉ có SAN `db-a.example.internal` nhưng ứng dụng kết nối bằng IP. Dự đoán lỗi và đề xuất cách sửa mà vẫn bảo đảm hostname verification.
5. Trên cluster nhiều node, `db-a` có cert hợp lệ nhưng `db-b` hết hạn. Vì sao Java Driver có thể kết nối contact point rồi gặp lỗi ở peer? Cần kiểm tra những endpoint nào?
6. Phân biệt `client_encryption_options` và `server_encryption_options`. Vì sao TLS client ở 9042 không tự bảo vệ gossip/streaming trên 7000?
7. Với `require_client_auth: true` và `PasswordAuthenticator`, giải thích vì sao client có thể cần cả client certificate lẫn username/password.
8. Mô tả quy trình luân chuyển password không làm toàn bộ client mất kết nối cùng lúc; nêu cách dùng hai role chuyển tiếp và kiểm tra quyền tối thiểu.
9. Trong Java Driver, cấu hình `SSLContext`, credentials và prepared statement; lý giải vì sao phải cấu hình truststore và local datacenter đúng.
10. Giả sử login đã thành công nhưng `SELECT` trả `ReadTimeout` ở `LOCAL_QUORUM`. Tại sao đổi password không giải quyết được lỗi? Bạn cần kiểm tra replication, replica và internode ra sao?

**Tiêu chí hoàn thành:** phân biệt được TLS, authentication, authorization; cấp và xác minh được quyền tối thiểu; thiết lập kết nối cqlsh/Java có CA tin cậy; nhận diện lỗi handshake, credentials, permission và lỗi truy vấn; giải thích được vì sao cấu hình bảo mật cần nhất quán trên cluster.

## Tài liệu tham khảo

- [Apache Cassandra — Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization và cơ chế bảo vệ đường truyền.
- [Apache Cassandra — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `authenticator`, `authorizer`, `client_encryption_options`, `server_encryption_options`.
- [Apache Cassandra — Database Roles](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/security.html): tạo role, quyền, `GRANT`, `REVOKE`.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `--ssl`, username/password, cqlshrc và các lệnh kiểm tra.
- [Apache Cassandra Java Driver 4.x — Authentication](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/authentication/index.html): auth provider và credentials.
- [Apache Cassandra Java Driver 4.x — SSL](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/ssl/index.html): SSL context, truststore, keystore và cấu hình client.
- [OWASP — TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): verify chain/hostname, private key và thực hành bảo vệ TLS.
