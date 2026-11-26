# Lỗi xác thực, phân quyền, DNS và TLS trong Spring Data Cassandra

Trong ứng dụng sử dụng **Spring Data Cassandra**, một thao tác đơn giản như `repository.findById(id)` hoặc `CassandraTemplate.selectOne(...)` có thể thất bại trước khi câu CQL thực sự được chạy. Nguyên nhân có thể nằm ở tên miền của node Cassandra, kết nối mạng, bắt tay TLS, thông tin đăng nhập hoặc quyền của role đối với bảng. Chẩn đoán đúng tầng giúp tránh sửa nhầm cấu hình, tránh retry vô ích và tránh làm lộ bí mật truy cập.

Bài này tập trung vào bốn nhóm lỗi **xác thực (authentication)**, **phân quyền (authorization)**, **DNS** và **TLS** khi Spring Data Cassandra làm việc với Apache Cassandra qua Java Driver và giao thức CQL. Ngoài việc sửa lỗi, ta cần hiểu vì sao cấu hình của một cụm phân tán khiến hiện tượng khác với cơ sở dữ liệu chạy trên một máy.

## 1. Đường đi của một thao tác CQL

~~~mermaid
flowchart TD
    A["Repository / CassandraTemplate"] --> B["Cassandra Java Driver"]
    B --> C["Phân giải DNS và định tuyến tới node"]
    C --> D["Kết nối TCP tới cổng CQL"]
    D --> E{"Node yêu cầu TLS?"}
    E -->|Có| F["TLS handshake: CA, SAN, thời hạn, mTLS"]
    E -->|Không| G["CQL protocol handshake"]
    F --> G
    G --> H["Xác thực role / credentials"]
    H --> I["Kiểm tra quyền trên tài nguyên CQL"]
    I --> J["Thực thi câu lệnh và trả kết quả"]
~~~

Sơ đồ thể hiện **thứ tự chẩn đoán**, không phải cam kết mọi lỗi đều xuất hiện đúng một lần theo chuỗi. Driver có thể mở nhiều kết nối, khám phá topology và chuyển request giữa các node. Vì vậy một contact point kết nối thành công vẫn chưa chứng minh các node được driver khám phá đều có DNS, đường mạng hoặc chứng chỉ hợp lệ.

Phân biệt hai thuật ngữ thường bị nhầm:

- **Authentication – xác thực:** Cassandra có nhận diện và chấp nhận role đăng nhập hay không? Kiểm tra credentials, tình trạng role có quyền `LOGIN` và cơ chế xác thực của cluster.
- **Authorization – phân quyền:** Role đã đăng nhập có quyền thực hiện thao tác `SELECT`, `MODIFY`, `CREATE`… trên tài nguyên đang truy cập hay không?

Không nên suy ra lỗi đăng nhập chỉ từ việc API phía ngoài trả HTTP 401, hoặc suy ra thiếu quyền CQL chỉ từ việc API trả HTTP 403. Đây là hai lớp bảo mật độc lập: người dùng HTTP của ứng dụng và role Cassandra mà ứng dụng sử dụng.

## 2. Bảng nhận diện lỗi theo tầng

| Tầng | Dấu hiệu thường gặp | Kiểm tra ưu tiên | Hướng xử lý |
| --- | --- | --- | --- |
| DNS | `UnknownHostException`; tên contact point không phân giải được; node được khám phá có tên/địa chỉ không dùng được | DNS từ **chính runtime** của ứng dụng; hostname của contact point và các node đã khám phá | Sửa bản ghi DNS, search domain, cấu hình service discovery hoặc địa chỉ node quảng bá |
| TCP / mạng | Connection refused, connect timeout, không tới được cổng CQL | Firewall, route, cổng CQL thực tế, network policy | Mở đúng luồng kết nối; sửa địa chỉ hoặc cổng |
| TLS | `SSLHandshakeException`, `PKIX path building failed`, hostname mismatch, lỗi client certificate | Chứng chỉ server, chuỗi CA, SAN, truststore, mTLS, cổng TLS | Cập nhật truststore/chứng chỉ và cấu hình TLS tương ứng |
| Xác thực | Authentication failed, invalid credentials, role không được phép đăng nhập | Role, cơ chế authenticator, username/password hiện hành, thời điểm rotation | Sửa secret hoặc role với quyền `LOGIN`; đồng bộ cấu hình client/server |
| Phân quyền | Unauthorized / missing permission khi `SELECT`, `INSERT`, `UPDATE`… | CQL thực tế, keyspace/table và quyền của role ứng dụng | Cấp quyền tối thiểu cần thiết cho đúng tài nguyên |

**Lưu ý:** `AllNodesFailedException` của Cassandra Java Driver là lỗi *tổng hợp*. Nó không tự nói rằng tất cả node đã bị tắt. Các nguyên nhân bên dưới có thể khác nhau ở từng node, ví dụ một node lỗi TLS, một node bị timeout, một node không phân giải được DNS. Phải đọc **các lỗi theo từng node và chuỗi nguyên nhân** trước khi kết luận.

## 3. Lỗi xác thực: kết nối được nhưng không đăng nhập được

Trong cluster bật `PasswordAuthenticator`, ứng dụng phải cung cấp thông tin đăng nhập hợp lệ cho Cassandra. Nếu cluster dùng phương thức xác thực khác, cần cấu hình nhà cung cấp xác thực (auth provider) tương thích trên Java Driver; ví dụ username/password chỉ áp dụng khi cơ chế phía server hỗ trợ.

Một cấu hình Spring Boot 3.x điển hình:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-1.internal.example:9042
      - cassandra-2.internal.example:9042
    local-datacenter: dc1
    keyspace-name: catalog
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
~~~

Các giá trị trên chỉ để minh họa: thay `dc1`, hostname, cổng và keyspace theo cluster đang dùng. Bí mật được cấp từ biến môi trường hoặc secret manager, không hard-code vào repository hay ghi lại trong log. Tên property có thể khác nếu dự án đang dùng nhánh Spring Boot cũ; ví dụ Spring Boot 2.x có cách đặt prefix Cassandra khác.

Trình tự kiểm tra khi lỗi đăng nhập:

1. **Xác nhận có kết nối TCP/TLS trước đó:** nếu lỗi sớm hơn ở DNS hoặc TLS, thay mật khẩu sẽ không sửa được.
2. **Xác nhận đúng cluster:** hostname có thể trỏ sang môi trường staging/production khác với nơi role được tạo.
3. **Kiểm tra role và credentials:** username chính xác, mật khẩu chưa bị đổi hoặc hết hiệu lực qua secret rotation, role còn được phép `LOGIN`.
4. **Kiểm tra cơ chế xác thực:** server có bật authenticator phù hợp? Ứng dụng đang sử dụng auth provider nào?
5. **Kiểm tra các kết nối đang tồn tại:** thông tin xác thực thường được dùng khi tạo kết nối; sau rotation có thể cần để các session/kết nối tái tạo theo cách vận hành đã thiết kế.

Ví dụ CQL do người quản trị có quyền thích hợp thực hiện:

~~~sql
CREATE ROLE catalog_reader
WITH PASSWORD = '<secret-duoc-cap-an-toan>'
AND LOGIN = true
AND SUPERUSER = false;
~~~

Dấu `<secret-duoc-cap-an-toan>` là ký hiệu mô tả, **không phải mật khẩu được sử dụng thật**. Trong môi trường thực, tránh nhập plaintext secret vào script chia sẻ, command history hay pipeline log. Tạo role mới cũng chưa đủ: role cần quyền truy cập tài nguyên như phần tiếp theo.

**Không retry liên tục** với cùng một username/password đã bị Cassandra từ chối. Retry không tạo ra quyền mới, có thể tăng tải và che khuất lỗi cấu hình gốc. Trả cảnh báo nội bộ hoặc đánh dấu dependency chưa sẵn sàng để người vận hành xử lý.

## 4. Lỗi phân quyền: đã đăng nhập nhưng CQL bị từ chối

Cassandra phân quyền cho **role Cassandra**, không tự kế thừa các vai trò `USER`, `ADMIN` hoặc JWT scope trong Spring Security. Một service có thể xác thực thành công khi khởi động, đọc metadata được, nhưng vẫn bị từ chối khi `findById` trên một bảng cụ thể.

Giả sử ứng dụng chỉ đọc bảng `catalog.products`:

~~~sql
GRANT SELECT ON TABLE catalog.products TO catalog_reader;
LIST ALL PERMISSIONS OF catalog_reader;
~~~

Nếu service còn ghi dữ liệu, chỉ cấp thêm quyền phù hợp với thao tác:

~~~sql
GRANT MODIFY ON TABLE catalog.products TO catalog_writer;
~~~

Trong Cassandra, quyền `MODIFY` áp dụng cho các thao tác thay đổi dữ liệu như `INSERT`, `UPDATE` và `DELETE`; quyền `SELECT` dành cho đọc. Quyền được gán cho keyspace có phạm vi rộng hơn quyền gán cho một bảng. Nếu dùng role inheritance, cần kiểm tra cả quyền kế thừa, không chỉ quyền được cấp trực tiếp.

Khi chẩn đoán, phải đối chiếu **CQL mà driver thực sự gửi** với **tài nguyên thực tế**:

| Thao tác Spring Data | CQL điển hình | Quyền Cassandra cần xem |
| --- | --- | --- |
| `repository.findById(id)` | `SELECT ... FROM catalog.products WHERE ...` | `SELECT` trên bảng |
| `repository.save(entity)` | `INSERT` hoặc `UPDATE` tùy mapping/luồng ghi | `MODIFY` trên bảng |
| `repository.deleteById(id)` | `DELETE FROM catalog.products ...` | `MODIFY` trên bảng |
| Khởi tạo schema nếu bật tính năng tạo bảng | `CREATE TABLE ...` | Quyền DDL tương ứng trên keyspace |
| Ứng dụng dùng custom CQL qua `CassandraTemplate` | Phụ thuộc câu CQL cụ thể | Kiểm tra chính thao tác được gọi |

Đừng nhầm lỗi thiếu quyền với lỗi bảng không tồn tại, keyspace sai, hoặc câu CQL không hợp lệ. Những lỗi này có nguyên nhân và cách sửa khác nhau. Với một service production, nên quản trị schema và role qua luồng migration/provisioning có kiểm soát; không cấp `SUPERUSER` để làm cho một truy vấn hoạt động.

## 5. Lỗi DNS: contact point và địa chỉ node được khám phá

Driver Cassandra sử dụng **contact points** để khởi tạo kết nối, rồi lấy thông tin topology và có thể kết nối đến các node khác. Do đó có hai nhóm vấn đề:

- **Contact point không phân giải được:** ví dụ hostname sai, search domain không đúng, private DNS không khả dụng trong container, hoặc cấu hình Kubernetes Service bị đổi.
- **Contact point phân giải được nhưng các node được khám phá không truy cập được:** địa chỉ node quảng bá cho client không có route phù hợp, hostname chỉ dùng được bên trong mạng khác, bản ghi DNS của từng node thiếu hoặc stale. Khi đó ứng dụng có thể kết nối ban đầu rồi lỗi khi thực hiện request.

Trên máy chạy ứng dụng, có thể kiểm tra bằng:

~~~bash
nslookup cassandra-1.internal.example
getent hosts cassandra-1.internal.example
nc -vz cassandra-1.internal.example 9042
~~~

`getent` và `nc` không có trên mọi hệ điều hành hoặc container image; trong PowerShell có thể dùng:

~~~powershell
Resolve-DnsName cassandra-1.internal.example
Test-NetConnection cassandra-1.internal.example -Port 9042
~~~

**Giới hạn của kiểm tra:** DNS thành công chỉ chứng minh phân giải tên tại nơi thực thi; TCP thành công chỉ chứng minh cổng có thể nhận kết nối. Cả hai không chứng minh TLS, đăng nhập hoặc quyền CQL. Chạy cùng phép thử từ **pod/container/VM của ứng dụng** vì DNS, proxy và route ở máy phát triển có thể khác.

Các điểm cần đối chiếu thêm trong cluster nhiều node:

1. Danh sách contact point và local datacenter được khai báo đúng với cluster.
2. Mỗi địa chỉ node mà driver khám phá có thể phân giải và kết nối từ runtime ứng dụng.
3. Thiết lập node quảng bá cho client (ví dụ `broadcast_rpc_address` trong những triển khai Cassandra sử dụng cơ chế này) phản ánh địa chỉ thật mà client có thể truy cập.
4. Địa chỉ private/public, DNS theo vùng và network policy không làm một phần node bị cô lập.

Nếu tên miền hoạt động lúc được lúc mất, thu thập thời điểm, resolver được sử dụng, câu trả lời DNS và node bị ảnh hưởng. Chỉ thay contact point có thể che triệu chứng mà không giải quyết địa chỉ quảng bá của các node còn lại.

## 6. Lỗi TLS: tin cậy chứng chỉ và xác minh danh tính node

TLS bảo vệ kênh kết nối giữa ứng dụng và endpoint CQL. Bắt tay TLS xảy ra **trước** bước xác thực Cassandra trong một kết nối dùng TLS. Cần phân biệt ba kiểm tra:

1. **Tính tin cậy:** truststore của client tin CA ký chứng chỉ server và chuỗi chứng chỉ đầy đủ.
2. **Danh tính endpoint:** hostname mà client kết nối phải khớp tên hợp lệ trong SAN của chứng chỉ (theo cấu hình xác minh hostname của client).
3. **mTLS nếu cluster yêu cầu:** ngoài chứng chỉ server, client phải cung cấp chứng chỉ và private key hợp lệ.

Một số lỗi điển hình:

| Triệu chứng | Cách hiểu và hướng điều tra |
| --- | --- |
| `PKIX path building failed` | CA hoặc chuỗi chứng chỉ chưa được truststore tin cậy |
| `No subject alternative DNS name matching ...` | SAN không chứa hostname đang dùng; có thể node quảng bá IP trong khi chứng chỉ chỉ có DNS |
| `certificate expired` / `not yet valid` | Thời hạn chứng chỉ hoặc đồng hồ hệ thống có vấn đề |
| `bad_certificate` / `certificate_required` | Cần kiểm tra chứng chỉ client, private key và cấu hình mTLS |
| `wrong version number` / `unrecognized_name` / kết nối bị đóng khi handshake | Có thể sai cổng TLS/plaintext, sai SNI hoặc endpoint không tương thích; cần đối chiếu cấu hình server và dấu vết handshake |

Kiểm tra endpoint TLS (chạy khi đã xác nhận endpoint CQL **có bật TLS**):

~~~bash
openssl s_client \
  -connect cassandra-1.internal.example:9042 \
  -servername cassandra-1.internal.example \
  -verify_hostname cassandra-1.internal.example \
  -showcerts
~~~

Lệnh trên hiển thị chứng chỉ và thông tin xác minh; nó không phải phép thử quyền CQL. Nếu dùng địa chỉ IP để kết nối, chứng chỉ cần tương thích với cách xác minh IP/hostname đang bật. Đừng giải quyết lỗi SAN bằng cách tắt hostname verification trên production.

Với Java Driver, TLS có thể được thiết lập qua SSL engine factory và truststore/keystore, hoặc qua `SSLContext` khi ứng dụng chủ động cấu hình `CqlSession`. Ví dụ phần cốt lõi của session builder:

~~~java
CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("cassandra-1.internal.example", 9042))
    .withLocalDatacenter("dc1")
    .withAuthCredentials(username, password)
    .withSslContext(sslContext)
    .build();
~~~

Ở ví dụ này, `sslContext` phải được **khởi tạo trước** với trust manager tin CA của cluster và key manager nếu cần mTLS. Đây là đoạn minh họa cho cách gắn TLS vào driver; không nên tạo thêm một `CqlSession` ở mỗi request. Trong ứng dụng Spring Boot, chọn **một** cơ chế quản lý session nhất quán với auto-configuration hoặc cấu hình session tùy biến của dự án. Khi triển khai thật, phải kiểm tra cả tùy chọn xác minh danh tính endpoint của driver/SSL engine factory theo phiên bản đang dùng.

**Không khắc phục bằng cách** dùng trust manager tin mọi chứng chỉ, tắt kiểm tra hostname, chuyển sang plaintext tùy tiện hoặc copy private key vào mã nguồn. Những thay đổi này có thể khiến kết nối “hoạt động” nhưng phá vỡ mục tiêu bảo mật của TLS.

## 7. Chẩn đoán đúng tầng khi Spring ném ngoại lệ

Spring Data Cassandra và Java Driver có thể bọc nhiều ngoại lệ. Vì vậy tên ngoại lệ bắt được tại service layer không phải lúc nào cũng là nguyên nhân gốc.

Ví dụ:

~~~text
org.springframework.dao.DataAccessResourceFailureException
  caused by: AllNodesFailedException
    node A -> SSLHandshakeException: PKIX path building failed
    node B -> ConnectTimeoutException
~~~

Đây chỉ là **sơ đồ minh họa** một chuỗi lỗi, không phải cam kết về lớp exception hoặc định dạng thông điệp của mọi phiên bản. Thực tế phải kiểm tra cause chain và các node errors mà driver cung cấp.

Cách xử lý thực tế:

1. Xác định **thời điểm**: tạo session, truy cập repository lần đầu, đổi node sau khi hoạt động một lúc, hay chỉ khi gọi một truy vấn cụ thể.
2. Xác định **phạm vi**: tất cả node, một vài node, một role, một bảng, một thao tác đọc/ghi, hoặc chỉ một môi trường triển khai.
3. Ghi nhận **lớp lỗi gần nguyên nhân nhất**: `UnknownHostException`, lỗi TLS, authentication failed hay unauthorized CQL.
4. Thử nghiệm tối thiểu theo thứ tự DNS → TCP → TLS → đăng nhập → quyền của một truy vấn đại diện.
5. Sau khi sửa, kiểm thử lại bằng **chính role và mạng của ứng dụng**, không chỉ bằng tài khoản admin từ laptop.

Có thể dùng một bảng quyết định ngắn:

~~~mermaid
flowchart TD
    A["Thao tác Cassandra thất bại"] --> B{"Tên node phân giải được?"}
    B -->|Không| C["Kiểm tra DNS / địa chỉ quảng bá"]
    B -->|Có| D{"Tới được cổng CQL?"}
    D -->|Không| E["Kiểm tra TCP / route / firewall"]
    D -->|Có| F{"TLS handshake thành công?"}
    F -->|Không| G["Kiểm tra CA / SAN / mTLS / cổng TLS"]
    F -->|Có| H{"Đăng nhập thành công?"}
    H -->|Không| I["Kiểm tra credentials / LOGIN / authenticator"]
    H -->|Có| J{"CQL được cho phép?"}
    J -->|Không| K["Kiểm tra quyền role trên keyspace/bảng"]
    J -->|Có| L["Tiếp tục chẩn đoán CQL, consistency và hiệu năng"]
~~~

Ở cluster không bật TLS, bỏ qua nhánh handshake TLS nhưng vẫn kiểm tra cấu hình bảo mật theo chính sách triển khai.

### Ghi log đủ để điều tra mà không rò rỉ bí mật

Log nên có thời gian, môi trường, cluster/datacenter, tên thao tác logic, loại lỗi, node liên quan và correlation/request ID. Nếu dùng CQL động hoặc có dữ liệu nhạy cảm, cần kiểm soát việc ghi nguyên câu query và bind values.

Không ghi:

- Password, token, nội dung secret, private key, truststore password.
- Nguyên chuỗi kết nối chứa thông tin xác thực.
- Thông tin cá nhân trong bind parameters hoặc stack trace được trả trực tiếp cho người dùng cuối.

Với dịch vụ HTTP gọi Cassandra, lỗi **đăng nhập của service vào Cassandra** thường là vấn đề hạ tầng/cấu hình nội bộ; không nên tự động trả HTTP 401 cho người dùng, vì 401 hàm ý người dùng HTTP cần xác thực lại. Ánh xạ trạng thái phía API theo hợp đồng API và tính chất lỗi (ví dụ 503 cho dependency tạm thời không sẵn sàng); luôn giữ thông tin chi tiết trong hệ thống quan sát nội bộ.

## 8. Retry, readiness và khôi phục an toàn

Bốn nhóm lỗi này không có cùng chính sách retry:

| Nhóm lỗi | Có nên retry tự động? | Vì sao |
| --- | --- | --- |
| Credentials sai / role bị khóa đăng nhập | Không retry vô hạn | Cấu hình sai sẽ tiếp tục sai cho đến khi cập nhật |
| Thiếu quyền CQL | Không | Retry không cấp thêm quyền |
| DNS không phân giải được | Retry có giới hạn khi nghi lỗi tạm thời | Resolver hoặc service discovery có thể phục hồi, nhưng hostname sai cần sửa cấu hình |
| TLS trust/SAN/mTLS sai | Không retry vô hạn | Chứng chỉ hoặc truststore cần được cập nhật |
| TCP timeout do gián đoạn mạng | Có thể retry giới hạn, kèm backoff | Cần xét idempotency và retry policy của driver |

Không mặc định retry các thao tác ghi CQL ngoài chính sách có đánh giá tính idempotent; một request có thể đã tới node trước khi client nhận timeout. Tránh tạo vòng lặp retry ở cả Java Driver, Spring service và API gateway cùng lúc.

Về giám sát:

- **Readiness:** nếu chức năng chính yêu cầu Cassandra, ứng dụng không nên nhận traffic trước khi dependency thiết yếu sẵn sàng. Readiness cần dựa trên khả năng thực hiện thao tác kiểm tra được thiết kế hợp lý, không chỉ việc DNS trả địa chỉ.
- **Liveness:** không đánh dấu tiến trình Java “đã chết” chỉ vì Cassandra đang lỗi tạm thời; nếu không sẽ gây vòng lặp restart làm điều tra khó hơn.
- **Metrics/log:** theo dõi tỷ lệ connection failure, TLS handshake error, authentication failure, unauthorized CQL theo node và thời điểm, cùng số request thành công/thất bại.

Nếu cần kiểm thử quyền truy cập, truy vấn `system.local` có thể kiểm tra kết nối và xác thực cơ bản nhưng **không chứng minh** role có quyền trên bảng nghiệp vụ. Hãy chạy thêm một truy vấn nhẹ tới đúng bảng được service sử dụng, ưu tiên truy vấn theo partition key đã biết và tránh `ALLOW FILTERING` hoặc quét bảng lớn chỉ để làm health check.

Khi xoay vòng credential hoặc chứng chỉ, nên có khoảng chuyển tiếp cho các giá trị mới/cũ theo chính sách của hệ thống, triển khai từng phần và xác minh các kết nối mới trước khi thu hồi giá trị cũ. Đặc biệt trong cluster Cassandra có nhiều node, chứng chỉ và cấu hình địa chỉ phải phù hợp **trên toàn bộ những node mà driver có thể chọn**.

## 9. Tình huống thực tế

### Tình huống A — Ứng dụng bật TLS rồi đột ngột không khởi động

Log có `AllNodesFailedException` và một lỗi con `PKIX path building failed`. DNS và TCP của contact point đều hoạt động.

**Phân tích:** kết nối tới server đủ xa để bắt đầu TLS, nhưng client không xây dựng được chuỗi tin cậy cho chứng chỉ server. Tập trung kiểm tra CA, intermediate certificates và truststore đã triển khai; không thay mật khẩu Cassandra để “thử”.

**Xác minh sau sửa:** kết nối TLS thành công từ runtime ứng dụng; driver tạo session được; truy vấn nghiệp vụ bằng role app hoạt động.

### Tình huống B — Đọc được, ghi bị từ chối

`repository.findById(id)` trả dữ liệu, nhưng `repository.save(entity)` thất bại với thông điệp unauthorized trên `catalog.products`.

**Phân tích:** xác thực và quyền `SELECT` đã đủ cho đọc. Kiểm tra role và quyền `MODIFY` trên bảng mà câu ghi thực sự nhắm đến. Không cấp `SUPERUSER`, không sửa cấu hình DNS/TLS.

### Tình huống C — Khởi động được nhưng lỗi rải rác theo node

Một contact point được phân giải và kết nối thành công. Sau khi driver khám phá topology, một số request tới node có địa chỉ private không thể định tuyến từ cụm Kubernetes của ứng dụng.

**Phân tích:** không chỉ kiểm tra contact point; kiểm tra địa chỉ CQL mà từng node quảng bá, DNS của từng node và network policy. Nếu chỉ sửa danh sách contact point, lỗi có thể tái xuất hiện khi driver chọn node khác.

### Tình huống D — Di chuyển từ hostname sang IP gây lỗi TLS

Service đổi contact point sang IP để “né DNS” rồi gặp lỗi xác minh hostname/SAN.

**Phân tích:** chứng chỉ có thể hợp lệ với hostname cũ nhưng không hợp lệ cho địa chỉ IP đang dùng. Chọn địa chỉ kết nối được định danh đúng theo chứng chỉ hoặc cấp chứng chỉ có SAN phù hợp; giữ nguyên xác minh danh tính.

## 10. Bài tập tự kiểm tra

**Câu 1.** `AllNodesFailedException` có đủ để kết luận cluster Cassandra đã down toàn bộ chưa?

**Đáp án:** Chưa. Phải đọc lỗi con theo node; vấn đề có thể là DNS, TCP, TLS hoặc xác thực, xảy ra trên nhiều node vì các nguyên nhân khác nhau.

**Câu 2.** Service login được, nhưng `DELETE FROM catalog.products ...` bị từ chối. Nên kiểm tra gì đầu tiên?

**Đáp án:** Role mà service thực sự sử dụng và quyền `MODIFY` trên `catalog.products` (hoặc quyền kế thừa tương ứng). Không đổi mật khẩu khi xác thực đã thành công.

**Câu 3.** `nslookup` và `nc` đều thành công. Điều đó đã chứng minh kết nối Cassandra sử dụng được chưa?

**Đáp án:** Chưa. Cần xác minh TLS, cơ chế xác thực, quyền CQL và cả khả năng kết nối những node được driver khám phá.

**Câu 4.** Vì sao không nên tắt kiểm tra chứng chỉ để xử lý lỗi `PKIX` hoặc SAN?

**Đáp án:** Vì client có thể chấp nhận sai server hoặc kết nối bị chặn giữa đường; phải sửa truststore, certificate chain và danh tính endpoint.

**Câu 5.** Khi nào nên xem xét retry?

**Đáp án:** Với sự cố có khả năng tạm thời, như gián đoạn DNS/mạng, và chỉ khi có giới hạn, backoff và đánh giá idempotency. Xác thực sai, thiếu quyền hay chứng chỉ không hợp lệ thường cần can thiệp cấu hình.

---

## Checklist trước khi kết luận đã xử lý xong

- [ ] Ứng dụng phân giải được cả contact point **và** địa chỉ node mà driver cần truy cập.
- [ ] Cổng CQL thực tế kết nối được từ môi trường chạy ứng dụng.
- [ ] Nếu bật TLS, trust chain, SAN, thời hạn, mTLS và cổng được xác minh đúng.
- [ ] Role Cassandra đăng nhập được với credentials hiện hành và được phép `LOGIN`.
- [ ] Role có quyền tối thiểu để thực thi đúng các thao tác repository/template đang dùng.
- [ ] Không có secret hoặc bind value nhạy cảm trong log, cấu hình commit hay thông báo API.
- [ ] Đã kiểm thử một thao tác đọc/ghi đại diện từ cùng runtime, bằng cùng role của ứng dụng.
- [ ] Retry/readiness hoạt động theo loại sự cố và không che giấu lỗi cấu hình cần sửa.

**Ghi nhớ:** Trong Spring Data Cassandra, thất bại tại repository có thể bắt nguồn từ một tầng hoàn toàn khác với truy vấn CQL. Hãy bám theo chuỗi **DNS → TCP → TLS → xác thực → phân quyền → thực thi CQL**, đọc nguyên nhân sâu nhất theo từng node và kiểm chứng bằng đúng môi trường, đúng role của ứng dụng.

