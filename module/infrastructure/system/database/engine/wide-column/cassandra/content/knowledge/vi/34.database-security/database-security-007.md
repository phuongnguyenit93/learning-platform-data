# TLS cho kết nối ứng dụng và giữa các nút

> **Chương:** Bảo mật  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra và mô hình wide-column phân tán: khóa phân vùng, thiết kế bảng theo truy vấn, nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý sự cố và kết nối từ ứng dụng Java.

Apache Cassandra giao tiếp qua hai đường mạng rất khác nhau: ứng dụng/driver nói chuyện với node bằng **native protocol**, còn các node trao đổi mutation, kết quả đọc, gossip/điều phối và dữ liệu streaming qua **kết nối internode**. Nếu chỉ bật TLS cho ứng dụng, lưu lượng giữa các replica vẫn có thể đi qua mạng dưới dạng không mã hóa. Ngược lại, chỉ bật TLS giữa các node không bảo vệ password hoặc dữ liệu CQL truyền từ ứng dụng đến coordinator.

Bài học này hướng dẫn cách bảo vệ **cả hai đường** bằng TLS, chọn mức xác minh chứng thư phù hợp, thực hiện rollout an toàn, kiểm tra kết nối từ Java Driver/cqlsh và vận hành chu kỳ cấp lại/luân chuyển khóa. Trọng tâm là hiểu **phạm vi bảo vệ thực tế**, không chỉ đặt `enabled: true` rồi coi cluster đã an toàn.

> **Lưu ý phiên bản:** các khóa cấu hình được minh họa chủ yếu theo Apache Cassandra 4.x–5.x. Cassandra 3.11 và các bản phân phối/managed service có thể khác cú pháp, cổng TLS và cách reload chứng thư. Cần kiểm tra file `cassandra.yaml` và tài liệu đúng release, tham số thực chạy, rồi thử trong cluster staging trước khi thay đổi production. Các đoạn YAML chỉ là mẫu khái niệm, **không phải file hoàn chỉnh có thể dùng nguyên trạng**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **TLS client-to-node**, **TLS internode**, **mTLS** với **authentication/authorization CQL**.
2. Hiểu vai trò của server certificate, private key, CA chain, keystore, truststore, Subject Alternative Name (SAN), hạn dùng và hostname verification.
3. Đọc hai khối `client_encryption_options` và `server_encryption_options`; chọn các mức `internode_encryption` phù hợp với yêu cầu an ninh.
4. Giải thích khi nào `optional: true` có ích trong giai đoạn chuyển tiếp và vì sao **không được để lâu dài** khi chính sách đòi mã hóa bắt buộc.
5. Cấu hình client Java Driver 4.x, `cqlsh` và kiểm tra TLS handshake/chứng thư mà không để lộ bí mật.
6. Lập kế hoạch triển khai/rotation/khôi phục có bước kiểm tra, rollback và theo dõi tác động latency, CPU, kết nối và repair/streaming.

## 2. Threat model: TLS bảo vệ cái gì và không bảo vệ cái gì?

### 2.1. Hai đường truyền độc lập

~~~mermaid
flowchart TB
    App["Java service / cqlsh"] -- "Native protocol: TLS client-to-node" --> C["Node A: coordinator"]
    C -- "Internode TLS" --> B["Node B: replica"]
    C -- "Internode TLS" --> D["Node C: replica"]
    B -. "Streaming / repair / replication" .- D
    K["CA / PKI + secret manager"] -. "Cert chain và key" .-> App
    K -. "Cert chain và key" .-> C
    K -. "Cert chain và key" .-> B
    K -. "Cert chain và key" .-> D
~~~

| Đường | Mục đích | Cấu hình Cassandra chính | Đối tượng cần xác thực |
|---|---|---|---|
| **Client → node** | Ứng dụng gửi CQL, bind values, nhận dữ liệu | `client_encryption_options` | Client kiểm tra chứng thư server; nếu bật mTLS server còn kiểm tra cert client |
| **Node ↔ node** | Replica messaging, đọc/ghi phân tán và hoạt động internode | `server_encryption_options` | Hai peer thiết lập TLS; mức xác minh danh tính phụ thuộc mTLS/endpoint verification |
| **JMX/admin** | Giám sát, chạy công cụ quản trị | Cấu hình JMX/JVM riêng | Không tự được bảo vệ chỉ vì đã bật hai mục trên |
| **SSH, backup object store, KMS, ứng dụng khác** | Vận hành hoặc truyền backup | Công cụ/cơ chế riêng | Phải kiểm tra độc lập |

TLS giúp **bảo mật dữ liệu trên đường truyền**, cung cấp xác thực của peer theo chain/trust policy và bảo vệ tính toàn vẹn của TLS record. TLS **không** thay thế:

- **Authentication** Cassandra: xác định user/role CQL được đăng nhập, ví dụ qua `PasswordAuthenticator`.
- **Authorization**: user/role nào được `SELECT`, `MODIFY`, `ALTER`, v.v.; ví dụ qua `CassandraAuthorizer`.
- **Encryption at rest**: mã hóa SSTable, commit log, backup, secret storage; TLS chỉ bảo vệ dữ liệu **đang truyền**.
- **Firewall/segmentation**: mạng internode, native transport và JMX vẫn phải giới hạn nguồn truy cập.
- **Backup/repair**: TLS không biến một replica bị thiếu dữ liệu thành replica đã được đồng bộ.

### 2.2. Ba cách xác minh thường bị nhầm

1. **Encryption without peer identity verification:** dữ liệu có mã hóa nhưng nếu client tin mọi cert hoặc tắt hostname verification, kết nối có thể bị kẻ tấn công giả mạo đích trong một số threat model. Tránh cấu hình “trust all”.
2. **Server-authenticated TLS:** client chỉ tin cert được CA hợp lệ ký và xác minh SAN tương ứng với tên/IP đang kết nối. Đây là mức căn bản cho hầu hết ứng dụng.
3. **Mutual TLS (mTLS):** phía server còn yêu cầu client đưa cert được CA đáng tin cậy ký; mỗi peer chứng minh danh tính bằng private key của mình. Dùng mTLS cho client hoặc internode khi chính sách cần, song **mTLS không tự cấp quyền CQL** trừ khi bạn có cơ chế ánh xạ chứng thư vào danh tính/role đã được cấu hình và kiểm chứng.

**Ví dụ:** Java Driver đã hoàn tất mTLS nhưng tài khoản CQL không có quyền `SELECT` vẫn phải bị từ chối câu truy vấn. Và ngược lại, username/password đúng nhưng kết nối TLS không tin CA của node sẽ thất bại **trước** bước chạy CQL.

## 3. Chứng thư và khóa: phải đúng danh tính, thời gian, quyền truy cập

### 3.1. Những thành phần bắt buộc

| Thành phần | Chứa gì? | Ai sử dụng? | Cách bảo vệ |
|---|---|---|---|
| **Server certificate** | Public key, tên DNS/IP trong SAN, CA issuer, thời hạn | Node phục vụ TLS, client xác minh | Có thể phân phối cho bên cần tin cậy theo PKI |
| **Server private key** | Khóa bí mật tương ứng với cert | Node ký/chứng minh danh tính | Secret manager, volume ACL, không commit Git |
| **CA certificate/chain** | Trust anchor/intermediate | Java, cqlsh, các node | Phân phối có kiểm soát; kiểm tra đúng CA |
| **Truststore** | Các CA/cert được tin | Bên **xác minh** peer | Bảo vệ tính toàn vẹn, tránh thêm CA ngoài ý muốn |
| **Keystore** | Cert chain và thường có private key | Bên **trình bày** cert | Giới hạn quyền đọc, bảo vệ password/secret ref |
| **Passphrase** | Mở khóa keystore/private key | Tiến trình node/client khi load key | Quản lý ngoài source code và không in log |

Java có thể dùng JKS hoặc PKCS#12; Cassandra hiện đại cũng hỗ trợ cấu hình SSL context dựa trên PEM thông qua factory phù hợp. **Đuôi file không quyết định** định dạng: cần khớp `store_type`/factory, chain và password. Với Kubernetes, cert/key có thể được mount từ Secret hoặc tích hợp KMS/secret manager; vẫn cần kiểm tra quyền truy cập của process.

**SAN quan trọng hơn tên hiển thị:** nếu driver kết nối tới `db-1.internal.example` thì cert của node phải có DNS SAN phù hợp, hoặc nếu dùng địa chỉ IP thì phải có IP SAN tương ứng khi bật hostname verification. Chỉ có Common Name (CN) không phải cách cấu hình nên dựa vào với TLS hiện đại.

### 3.2. Một bộ kiểm tra chứng thư không lộ private key

Trong môi trường lab có bản cert public:

~~~bash
# Kiểm tra ngày hiệu lực, issuer, subject và Subject Alternative Names.
openssl x509 -in server-cert.pem \
  -noout -dates -issuer -subject -ext subjectAltName

# Kiểm tra một keystore được cấp phép; keytool sẽ hỏi mật khẩu qua prompt.
keytool -list -v -keystore server-keystore.p12 -storetype PKCS12
~~~

Không đưa `-storepass <password>` vào command ghi trong lịch sử shell, CI log hoặc tài liệu. Trong production, dùng secret injection/file bảo vệ theo cơ chế mà Cassandra release hỗ trợ. **Không bật `-nodes` hoặc xuất private key plaintext** chỉ để thí nghiệm nhanh trên một cụm thật.

### 3.3. CA và chứng thư cho internode

Trong một cluster nhiều node/DC, mỗi node thường có **identity riêng** theo PKI, truststore tin vào CA phát hành cho các node hợp lệ, và SAN phản ánh endpoint kết nối thực. Nếu nhiều node dùng chung một private key, việc compromise một node có thể cho phép giả mạo node khác; cần hiểu chính sách và tránh chia sẻ tùy tiện.

Phân biệt:

- **Chứng thư riêng từng node**: dễ thu hồi/kiểm soát vòng đời và audit theo node.
- **CA chuyên cho internode**: giúp hạn chế vùng tin cậy cho cluster, có thể tách CA cho client mTLS.
- **outbound keystore** (ở các release có hỗ trợ): có thể xác định cert mà node dùng khi **đóng vai client** cho kết nối internode mTLS; mặc định hoặc hành vi khi không khai báo phải đối chiếu file cấu hình thực tế.
- **Endpoint verification**: kiểm tra danh tính peer theo endpoint đã kết nối; phải cấp SAN đúng **trước** khi bật để tránh làm cluster bị chia cắt bởi lỗi hostname.

Chỉ tin CA không có nghĩa chỉ những node Cassandra hợp lệ mới có cert: nếu CA chung ký chứng thư cho nhiều dịch vụ, mTLS có thể chấp nhận identity ngoài ý muốn trừ khi cơ chế xác minh endpoint/authorization bổ sung được cấu hình đúng. Thiết kế PKI và scope CA là một phần của threat model.

## 4. TLS cho ứng dụng: client_encryption_options

### 4.1. Khác nhau giữa `enabled`, `optional` và `require_client_auth`

Cấu hình client-to-node nằm trong `cassandra.yaml`:

| Tùy chọn | Vai trò | Rủi ro nếu hiểu sai |
|---|---|---|
| `enabled: true` | Bật khả năng TLS cho native transport | Không đủ để **bắt buộc** TLS nếu `optional: true` |
| `optional: false` | Khi TLS được bật, không cho plaintext đi cùng cổng được bảo vệ | Client cũ chưa cấu hình TLS sẽ không kết nối |
| `optional: true` | Cho phép cả TLS và plaintext trong giai đoạn tương thích/chuyển tiếp | Không đạt mục tiêu “mọi CQL phải mã hóa” nếu giữ lâu |
| `keystore`, thông tin mở keystore | Nguồn cert/private key mà node trình bày | Sai path/password/format khiến TLS handshake hoặc node startup thất bại |
| `require_client_auth: true` | Yêu cầu client trình bày chứng thư được tin cậy (mTLS) | Mọi driver/cqlsh không có cert sẽ bị từ chối |
| `truststore` khi bật mTLS | CA/cert mà node tin để kiểm tra client | Truststore quá rộng có thể chấp nhận nhiều identity ngoài chủ đích |

**Minh họa đích production muốn TLS bắt buộc với server authentication:**

~~~yaml
# Chỉ là khối minh họa. Phải bổ sung secret theo cơ chế được hỗ trợ
# trên đúng Cassandra release. Không để password plaintext trong Git.
client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/tls/native-server.p12
  # keystore_password: được cung cấp an toàn, không in giá trị ở đây
  store_type: PKCS12
  require_client_auth: false
~~~

Trong ví dụ này, server **không yêu cầu client certificate**, nhưng ứng dụng vẫn nên xác minh CA/SAN của server. Nếu cần mTLS, đổi `require_client_auth: true`, cấu hình truststore phù hợp và cấp cert/key cho ứng dụng. Cần đọc hướng dẫn release để biết các trường SSLContextFactory và cách khai báo secret/password file; **không coi comment của YAML là một cấu hình runnable**.

### 4.2. Cổng native transport

Native protocol thường dùng **9042/TCP** (`native_transport_port`), nhưng port có thể được cấu hình khác. Trong nhiều bản 4.x, `enabled: true` cùng `optional: true` hỗ trợ cả TLS/plaintext trên cùng cổng. Các bản cũ có tùy chọn cổng TLS riêng `native_transport_port_ssl`; tài liệu Cassandra 5.0 đã đánh dấu lựa chọn này **deprecated**. Không dựa vào 9142 hoặc port từ một bài hướng dẫn cũ khi chưa xác minh thực tế.

**Không công khai 9042 ra Internet** chỉ vì TLS đã bật. Giới hạn bằng security groups, firewall, mạng riêng, kết nối riêng/VPN, network policy và authentication/authorization theo nguyên tắc least privilege.

### 4.3. Xác minh từ client cqlsh

Với cqlsh phiên bản hỗ trợ SSL và cấu hình CA phù hợp:

~~~bash
# Lệnh minh họa: cert/trust config được đặt ở cqlshrc bảo vệ riêng.
cqlsh db-1.internal.example 9042 --ssl
~~~

Tập tin `cqlshrc` hoặc tham số SSL của cqlsh cần được kiểm tra theo release; khi bật validation, cqlsh phải xác minh chứng thư/trust chain phù hợp. **Kết nối bằng `--ssl` chưa tự chứng minh hostname validation đang bật và đúng**: cần đối chiếu cấu hình xác minh của client và thử kết nối với endpoint không khớp chứng thư để bảo đảm việc từ chối diễn ra như mong muốn.

## 5. TLS giữa các nút: server_encryption_options

### 5.1. Chọn phạm vi mã hóa

`server_encryption_options.internode_encryption` xác định **loại peer** mà node sẽ dùng kênh mã hóa khi kết nối. Những giá trị phổ biến:

| Giá trị | Ý nghĩa khái quát | Khi nào phù hợp |
|---|---|---|
| `none` | Không chủ động mã hóa kết nối internode | Chỉ môi trường thử nghiệm cô lập; không đạt yêu cầu mã hóa toàn bộ |
| `dc` | Mã hóa kết nối giữa các datacenter khác nhau, có thể plaintext trong cùng DC | Khi policy chỉ yêu cầu bảo vệ lưu lượng liên DC và đã chấp nhận rủi ro nội DC |
| `rack` | Mã hóa kết nối giữa các rack khác nhau; cùng rack có thể plaintext | Phụ thuộc topology/rack metadata tin cậy; không đảm bảo mã hóa mọi node |
| `all` | Mã hóa mọi kết nối internode | Lựa chọn rõ nhất khi policy yêu cầu mã hóa toàn bộ peer traffic |

Ví dụ: nếu RF=3 và ba replica cùng `dc1`, đặt `internode_encryption: dc` **không** có nghĩa mutation giữa ba replica được mã hóa, vì chúng cùng DC. Tương tự, `rack` dựa vào cách node được gán rack; cấu hình snitch/rack sai có thể tạo khoảng trống an ninh. Khi mục tiêu là không có plaintext trên mạng internode, dùng `all` cùng kiểm soát tương thích/chứng thư.

### 5.2. Mẫu internode TLS bắt buộc

~~~yaml
# Minh họa target state của một cluster lab đã cấp đủ cert cho mọi node.
server_encryption_options:
  internode_encryption: all
  optional: false
  keystore: /etc/cassandra/tls/node-internode.p12
  # keystore_password: lấy từ secret manager/password file hợp lệ
  store_type: PKCS12
  require_client_auth: true
  truststore: /etc/cassandra/tls/internode-trust.p12
  # truststore_password: cấp an toàn ngoài mã nguồn
  require_endpoint_verification: true
~~~

Đây là **mô hình mục tiêu**, không phải chỉ việc chèn một khối vào production sẽ chạy: để `require_client_auth: true`, các peer cần cert đóng vai client khi nối đến node khác; trust chain và endpoint SAN phải đúng. Ở một số release có cấu hình outbound keystore/SSL context factory riêng. Tên và hỗ trợ từng trường phải kiểm tra `cassandra.yaml` của đúng bản đã cài.

**Lợi ích:** tránh plaintext trên đường peer traffic phù hợp policy. **Chi phí:** TLS handshake, crypto CPU, certificate verification, quản trị cert/CA và khả năng mất kết nối khi cert hết hạn. Không tự giả định TLS là nguyên nhân mọi latency tăng; đo CPU, p95/p99, network và số lần handshake.

### 5.3. Cổng internode và thay đổi từ bản cũ

Lưu lượng internode truyền thống dùng **7000/TCP** (`storage_port`); một số cấu hình trước đây dùng cổng TLS riêng **7001/TCP** (`ssl_storage_port`). Từ Cassandra 4.0, cổng SSL internode riêng được xem là **legacy/deprecated** trong cấu hình và một cổng có thể xử lý kết nối bảo mật theo tính năng được hỗ trợ. Không suy rằng “có lưu lượng 7000” thì plaintext, hoặc “7001 đóng” thì TLS chưa được bật. **Kiểm tra release, file thực, log và handshake/telemetry** thay vì phán đoán theo port.

### 5.4. TLS có che toàn bộ rủi ro của giao tiếp peer?

Không. Dù có TLS:

- Node có private key bị đánh cắp vẫn là một mối nguy; cần revoke/rotate và cô lập node.
- Nếu `require_endpoint_verification` bị tắt, việc xác minh CA chỉ là một phần của identity assurance.
- Một node bị compromise **sau** khi TLS giải mã vẫn có thể đọc và ghi dữ liệu mà role node được phép.
- Firewalls, quyền quản trị JMX/SSH, audit, credential hygiene và keyspace RF/repair vẫn cần được duy trì.
- TLS internode không tự bật TLS cho cổng native CQL hoặc JMX.

## 6. Kế hoạch triển khai dần để tránh chia cắt cluster

### 6.1. Vì sao không bật bắt buộc toàn bộ ngay?

Giả sử ba node A/B/C đang giao tiếp plaintext. Nếu chỉnh riêng A sang `internode_encryption: all` với `optional: false` trước khi B/C có khả năng chấp nhận TLS, A có thể **không thiết lập được kết nối tới peer cũ**. Cùng lúc, application client chưa bật TLS sẽ bị từ chối nếu node chuyển sang `client_encryption_options.optional: false`.

Vì thế Cassandra hiện đại hỗ trợ lựa chọn **mixed TLS/plaintext tạm thời** trong một số giai đoạn rollout; tài liệu configuration mô tả quy trình hai pha.

### 6.2. Pha chuẩn bị

1. Kiểm kê **Cassandra release/JVM**, số node, DC/rack, seed/routing, port thực tế, driver/cqlsh phiên bản và network ACL.
2. Phát hành chứng thư theo CA/PKI, cấp riêng private key cho node, kiểm tra SAN, issuer, expiry, EKU/key usage và chain; bảo vệ secret ngay từ lúc cấp.
3. Đưa file keystore/truststore đến mỗi node bằng secret manager/volume với owner và permissions phù hợp; xác minh quyền đọc của tiến trình Cassandra.
4. Cấp truststore/CA cho mọi Java service, test driver TLS và hostname verification trong staging; chuẩn bị cert client nếu dùng mTLS.
5. Thiết lập alert về hết hạn cert, handshake failures, native connection failures, internode dropped messages và latency/CPU; chuẩn bị rollback và maintenance window.
6. Kiểm tra `nodetool status`, schema agreement, số replica Up, thông lượng đọc/ghi baseline. Không cùng lúc thay đổi compaction, RF hoặc nâng phiên bản nếu không cần.

### 6.3. Pha tương thích tạm thời

Theo tài liệu Cassandra 4.x/5.x, một hướng triển khai phổ biến:

~~~yaml
# Trạng thái chuyển tiếp, KHÔNG phải đích bảo mật lâu dài.
client_encryption_options:
  enabled: true
  optional: true
  keystore: /etc/cassandra/tls/native-server.p12

server_encryption_options:
  internode_encryption: all
  optional: true
  keystore: /etc/cassandra/tls/node-internode.p12
~~~

Trong mỗi khối còn cần password/SSL factory/trust và các trường theo phiên bản thực. **Lưu ý:** đây là minh họa trạng thái hỗn hợp cho mục đích triển khai, không khẳng định mọi kết nối đã được mã hóa. Sau rollout/restart theo quy trình của release, xác nhận các node/client có thể chuyển sang TLS và không rơi vào trạng thái kết nối thất bại.

Giai đoạn `optional: true` làm giảm bảo đảm an ninh: **plaintext vẫn được chấp nhận**. Phải đặt thời hạn, đo số client cũ, chặn ingress plaintext khi phù hợp, và chuyển sang bắt buộc ngay khi mọi thành phần hỗ trợ.

### 6.4. Chuyển sang bắt buộc và mTLS

Khi tất cả node và client đã sẵn sàng:

1. Chuyển client sang TLS có xác minh CA/SAN; theo dõi handshake, connections, p99, errors và khả năng reconnect.
2. Bật `client_encryption_options.optional: false` khi không còn client plaintext; nếu dùng client mTLS, cấp cert/CA và xác minh driver trước khi đặt `require_client_auth: true`.
3. Khi internode đã tương thích TLS, chuyển `server_encryption_options.optional: false` trên các node theo **runbook rolling/restart**. Đối với mTLS, bảo đảm truststore và chứng thư outbound của peer sẵn sàng.
4. Kiểm tra `nodetool status` từ các node khác nhau, replica reachability, Java đọc/ghi ở CL dự kiến, repair/streaming trong cửa sổ kiểm thử và metric network/CPU.
5. Xác nhận **kết nối plaintext bị từ chối**, kết nối cert sai bị từ chối và cert hợp lệ thành công. Chỉ sau khi kiểm tra mới kết luận đã đạt chính sách.

### 6.5. Bảng tiêu chí trước/sau

| Bằng chứng | Trước rollout | Đích sau rollout |
|---|---|---|
| Client connections | Có thể còn plaintext | TLS bắt buộc và hostname/CA validation |
| Internode connections | Tùy DC/rack/none | Nếu policy yêu cầu: `internode_encryption: all`, optional false |
| Authentication | CQL roles/permissions đúng | Giữ nguyên hoặc nâng theo policy, không phá quyền truy cập |
| Network | ACL mở đúng phạm vi | Vẫn giới hạn nguồn truy cập; không expose 9042/JMX |
| Cert inventory | Chưa đủ hoặc chưa giám sát | Mỗi endpoint có cert chain/SAN/expiry, rotation owner |
| Điều kiện thất bại | Client TLS cũ chưa sẵn sàng | Plaintext/CA sai/hostname sai/mTLS thiếu cert bị chặn |
| Hiệu năng | p50/p95/p99, CPU, error baseline | SLO không suy giảm quá ngưỡng chấp nhận |

Không coi số liệu `nodetool status` toàn UN là bằng chứng TLS đang bật: node có thể Up dù client được phép plaintext. Cần kiểm tra **đường kết nối và cấu hình**.

## 7. Java Driver 4.x: bật TLS và xác minh server

### 7.1. Cấu hình kết nối có CA

Ví dụ Java Driver 4.x theo cơ chế `application.conf`, được nạp từ vùng cấu hình được bảo vệ:

~~~hocon
datastax-java-driver {
  basic.contact-points = ["db-1.internal.example:9042"]
  basic.load-balancing-policy.local-datacenter = "dc1"

  advanced.ssl-engine-factory {
    class = DefaultSslEngineFactory
    truststore-path = "/run/secrets/cassandra/client-truststore.p12"
    truststore-password = "ONLY_FOR_DEMO_REPLACE_WITH_SECRET_SOURCE"
    hostname-validation = true
  }
}
~~~

**Cảnh báo:** chuỗi `ONLY_FOR_DEMO_REPLACE_WITH_SECRET_SOURCE` là placeholder, không phải password thật và không được đưa vào artifact triển khai. Thực tế nên dùng config loader được tích hợp với secret manager/secure config injection; tên khóa config và hỗ trợ provider có thể khác theo driver 4.x patch release. Đối với tệp PKCS#12, xác minh loại keystore mặc định của JVM hoặc cấu hình JSSE tương ứng trên bản Java đang chạy; `DefaultSslEngineFactory` 4.x không cung cấp tùy chọn `truststore-type` trong cấu hình driver thông thường. **Phải kiểm tra đúng tài liệu DataStax/Apache Java Driver bạn dùng** trước khi chạy.

Với mTLS, client còn phải trình bày cert/private key hợp lệ (ví dụ keystore path/type và password do secure source cấp); việc chỉ cung cấp truststore **không** đủ. CQL authentication (username/password/token) được cấu hình riêng, không trộn lẫn với chứng thư TLS.

### 7.2. Java tạo CqlSession từ cấu hình bảo mật

Đoạn sau giả định file cấu hình ngoài ứng dụng đã chứa endpoint, local DC và TLS engine factory như trên:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.io.File;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .withConfigLoader(
            DriverConfigLoader.fromFile(
                new File("/etc/myapp/cassandra-driver.conf")))
        .build()) {

    PreparedStatement ps = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM security_lab.events_by_device WHERE device_id = ?");

    BoundStatement stmt = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"));

    session.execute(stmt).forEach(row -> {
        // Chỉ xử lý dữ liệu cần thiết, không log secret/payload nhạy cảm.
        row.getUuid("event_id");
    });
}
~~~

Đoạn này là ví dụ tích hợp, không phải chương trình độc lập: bảng `security_lab.events_by_device` phải tồn tại; CQL user/role phải có `SELECT`. Nếu cluster cần authentication, thêm auth provider với credential lấy từ nguồn bảo mật, **không** viết mật khẩu trong Java source. Driver nhận danh sách contact points, sau đó khám phá topology và có thể kết nối đến nhiều node; vì thế **mọi endpoint mà driver có thể chọn đều phải có cert hợp lệ** với tên/IP tương ứng.

### 7.3. Những lỗi đặc trưng khi kết nối Java

| Triệu chứng | Giả thuyết cần kiểm tra | Cách khắc phục |
|---|---|---|
| `PKIX path building failed` hoặc không tin server | Thiếu CA/intermediate, truststore sai | Cấp đúng CA chain, kiểm tra truststore và issuer |
| `No subject alternative names ...` | Host/IP mà driver kết nối không nằm trong SAN | Phát hành cert có SAN đúng, sửa DNS/endpoints; không tắt validation |
| `handshake_failure` | Không chung TLS version/cipher, mTLS thiếu cert, keystore sai | So TLS/JVM options, cert chain, server/client logs |
| `bad_certificate` / `unknown_ca` | Peer từ chối client cert hoặc CA | Kiểm tra mTLS truststore, EKU và thời hạn cert |
| `Connection refused` | Port/listen/firewall, node chưa chạy | Kiểm tra native transport, network policy và port |
| `AuthenticationException` sau TLS thành công | CQL role/credential không hợp lệ | Kiểm tra authenticator và quyền, không thay đổi TLS vô cớ |
| `UnauthorizedException` | Đã đăng nhập nhưng thiếu quyền cho CQL | Kiểm tra role grants; TLS không cấp quyền SELECT |
| Timeout lúc một số node mới cấp cert | Một số endpoint handshake sai, driver đổi node liên tục | Kiểm tra cert/trust/hostname trên **mọi node**, không chỉ seed |

Một lỗi TLS **khác** lỗi CL/replication: nếu driver không thể mở kết nối tới phần lớn node vì cert không hợp lệ, ứng dụng có thể thấy Unavailable/timeout nhưng gốc rễ là **reachability/TLS**. Phải đối chiếu error chain, cert expiry và node logs.

## 8. Lab cô lập: chứng minh TLS thực sự bắt buộc

### 8.1. Điều kiện

Chuẩn bị:

- Cluster lab 3 node nếu muốn kiểm tra internode và RF=3; mọi node có cert riêng, CA/truststore đầy đủ.
- Java Driver 4.x, cqlsh và openssl/công cụ TLS tương ứng; dùng hostnames đúng SAN.
- Bảng CQL đơn giản với RF theo tên DC thực tế, ví dụ `dc1` có đủ ba node.
- Hai cấu hình kiểm thử **TLS hợp lệ** và **plaintext/cert sai**, chỉ chạy trong mạng thử nghiệm.

Ví dụ CQL trong cqlsh đã kết nối qua TLS:

~~~sql
CREATE KEYSPACE IF NOT EXISTS security_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS security_lab.events_by_device (
  device_id uuid,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO security_lab.events_by_device
  (device_id, event_time, event_id, payload)
VALUES (
  d654b0fe-7357-497f-8db4-59b165d58a0f,
  '2026-11-21T09:00:00Z',
  80aaeac3-1f11-4f66-877f-d9ccfca2216d,
  'tls-lab-event'
);

SELECT event_time, event_id, payload
FROM security_lab.events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f;
~~~

`IF NOT EXISTS` không sửa cấu hình đối tượng cũ; dùng `DESCRIBE KEYSPACE`/`DESCRIBE TABLE` để kiểm tra schema. Đo cùng CL, cùng dữ liệu/driver khi so kết nối trước và sau TLS. **Không lấy một SELECT đơn lẻ làm benchmark mã hóa**.

### 8.2. Kiểm tra đường client-to-node

Có thể thử TLS handshake ở cổng native protocol:

~~~bash
# Trên host lab có CA public và DNS khớp SAN:
openssl s_client \
  -connect db-1.internal.example:9042 \
  -servername db-1.internal.example \
  -CAfile ca-public.pem \
  -verify_return_error
~~~

Nếu cần kiểm tra **hostname** riêng, cách dùng flags của OpenSSL phụ thuộc release, ví dụ `-verify_hostname db-1.internal.example` ở bản hỗ trợ. `s_client` giúp quan sát cert chain và handshake; nó **không** thực hiện native-protocol authentication/CQL. Đọc kỹ mã thoát và kết quả verify, tránh suy ra “đã an toàn” chỉ từ dòng “CONNECTED”.

Thử ba điều kiện:

| Lần thử | Kỳ vọng khi TLS bắt buộc và xác minh đúng |
|---|---|
| Client có CA đúng và hostname khớp | TLS handshake thành công; CQL chỉ thành công nếu auth/grants đúng |
| Client dùng CA sai/hostname không khớp | **Bị từ chối khi client kiểm tra cert** |
| Client plaintext đến cổng TLS-only | **Không phục vụ CQL plaintext** |

Nếu dùng mTLS, thêm lần thử client thiếu cert hoặc cert do CA không được tin ký: server phải từ chối theo chính sách. Với `optional: true`, plaintext có thể **được chấp nhận**, nên phải coi kết quả đó là bằng chứng rollout chưa kết thúc, không phải lỗi test.

### 8.3. Kiểm tra internode và replica

Trên node:

~~~bash
nodetool status
nodetool describecluster
nodetool netstats
nodetool tpstats
~~~

Theo dõi cùng log Cassandra và các metric handshake/internode connection failures, dropped messages, replica response latency, streaming/repair. Một cluster RF=3 có thể chạy ở CL `LOCAL_QUORUM` ngay cả khi một replica gặp lỗi kết nối; **một ghi thành công không đủ chứng minh tất cả kết nối internode đều bảo mật**.

Kiểm tra:

1. Tất cả node có thể nhìn thấy nhau trong trạng thái đúng, không chia mạng thành hai nhóm do CA/SAN lỗi.
2. Những đường internode bắt buộc được cấu hình TLS theo policy (`all` nếu yêu cầu mọi peer traffic); không còn `optional: true` ở target state.
3. Trong lab, xác minh thực tế với network telemetry/capture được phê duyệt hoặc cơ chế quan sát TLS của release. **Không diễn giải port 7000/7001 một mình** là bằng chứng mã hóa.
4. Sau thay cert, thử kết nối mới và một thao tác tạo network traffic phù hợp, ví dụ đọc/ghi qua RF=3; đo latency/CPU so với baseline.

Không tạo sự cố bằng cách xóa private key đang được node production sử dụng hoặc ngắt mọi peer cùng lúc. Trước khi test failure injection, phải có snapshot/rollback, khả năng kết nối quản trị và giới hạn ảnh hưởng.

### 8.4. Bảng kết quả cần điền số thực

| Bằng chứng | Trước TLS | Sau TLS bắt buộc | Đạt? |
|---|---|---|---|
| Java kết nối có CA/SAN đúng | _điền_ | _điền_ | _điền_ |
| Java client plaintext bị từ chối | _điền_ | _điền_ | _điền_ |
| Hostname/CA sai bị từ chối | _điền_ | _điền_ | _điền_ |
| Internode all + optional false trên mọi node | _điền_ | _điền_ | _điền_ |
| Client p50/p95/p99 (ms) | _điền_ | _điền_ | _điền_ |
| CPU %, TLS handshakes/s | _điền_ | _điền_ | _điền_ |
| Query lỗi/timeout và dropped messages | _điền_ | _điền_ | _điền_ |
| Node status và streaming/repair | _điền_ | _điền_ | _điền_ |

Không điền kết quả tưởng tượng. Khi đo, giữ ổn định RF/CL, số kết nối, QPS, kích thước mutation, compaction nền và cấu hình JVM để phân biệt chi phí TLS với thay đổi workload.

## 9. Vận hành chứng thư: reload, rotation và khôi phục

### 9.1. TLS certificate hot reload từ Cassandra 4

Tài liệu Cassandra mô tả **hot reload SSL certificates** từ nhánh 4: khi sử dụng key/trust material dạng file tương thích, node có thể phát hiện file được cập nhật và reload định kỳ; trong các release hỗ trợ có lệnh:

~~~bash
# Chỉ khi nodetool help của bản chạy xác nhận có lệnh này:
nodetool reloadssl
~~~

**Không đồng nhất “reload thành công” với mọi kết nối cũ đã đổi cert**: TLS session tồn tại có thể tiếp tục dùng trạng thái handshake cũ; kết nối **mới** mới kiểm chứng được cert/CA vừa cập nhật. Nếu đổi cả mật khẩu keystore, cần đối chiếu cơ chế reload và file cấu hình; một số triển khai yêu cầu restart hoặc quy trình khác. Không để certificate renewal phụ thuộc vào một giả định về hot reload chưa kiểm thử.

### 9.2. Thứ tự luân chuyển CA/chứng thư tránh mất kết nối

Khi CA cũ sẽ được thay bằng CA mới, một quy trình **có hai giai đoạn tin cậy chồng lấn** thường an toàn hơn:

1. **Kiểm kê:** tất cả node/client, cert hiện tại, SAN, expiry, CA, truststore, ứng dụng offline hoặc ít hoạt động, chứng thư mTLS và keystore outbound.
2. **Mở rộng trust:** cập nhật truststores trên tất cả peer/client để tạm tin **cả CA cũ và CA mới** nếu chính sách cho phép.
3. **Xác minh trust mới:** test client/ngang hàng với chứng thư ký bởi CA mới trong staging; xác minh cert chain, SAN, EKU và đường kết nối.
4. **Đổi keypair/chứng thư:** thay từng node/client, dùng hot reload/rolling restart theo khả năng của bản triển khai, kiểm tra kết nối mới ngay sau từng bước.
5. **Thu hẹp trust:** sau khi mọi endpoint đã chuyển CA mới và xác nhận không còn cert cũ, bỏ CA cũ theo lịch, kiểm tra lại negative tests.
6. **Thu hồi và lưu vết:** revoke cert/CA cũ nếu cần, cập nhật inventory, backup/DR secrets, expiry alerts và audit log.

Với sự cố **private key compromise**, không tiếp tục tin hoặc khôi phục key đã lộ chỉ vì chứng thư chưa hết hạn. Cần cô lập endpoint, revoke/rotate, xem xét ảnh hưởng auth và đáp ứng sự cố; có thể cần tái cấp identity cho node và kiểm tra toàn cluster.

### 9.3. Phòng mất cả cluster lẫn secret manager

Sao lưu chỉ chứa SSTables/schema nhưng **không có đường phục hồi CA, private key, KMS/truststore** có thể khiến cluster restored không kết nối được. Bản backup security cần:

- Bí mật được mã hóa và có kiểm soát truy cập; lưu **tham chiếu** trong manifest thường, không ghi private key vào tài liệu/CI artifact công khai.
- Kế hoạch backup/DR của PKI/KMS, quyền break-glass và cách cấp lại cert khi không thể khôi phục key.
- Thời hạn cert, chủ sở hữu rotation, cảnh báo trước expiry và diễn tập từ cluster/Java driver sạch.
- Kiểm tra không có node dùng cert cũ khi thay CA; không tự bypass hostname validation để “cứu” sự cố.
- Phân tách TLS transport key với **data-at-rest encryption key**; chúng bảo vệ hai thứ khác nhau.

## 10. Chẩn đoán các sự cố thường gặp

### 10.1. Quy trình điều tra không bỏ qua bảo mật

~~~mermaid
flowchart TB
    A["Client/node không kết nối được"] --> B{"TCP reachability?"}
    B -->|Không| C["Kiểm tra port, firewall, DNS, listen/broadcast"]
    B -->|Có| D{"TLS handshake/CA/SAN hợp lệ?"}
    D -->|Không| E["Cert expiry, CA chain, SAN, mTLS, keystore, JVM"]
    D -->|Có| F{"CQL authentication/authorization?"}
    F -->|Sai| G["Role credentials, grants, system_auth, CL"]
    F -->|Đúng| H["Đo timeout, replica, CL, CPU, GC, network"]
    C --> I["Kiểm tra lại theo chính sách TLS"]
    E --> I
    G --> I
    H --> I
~~~

| Vấn đề | Triệu chứng | Điều cần kiểm tra |
|---|---|---|
| CA không được tin | `unknown_ca`, `PKIX path building failed` | Truststore client/node, intermediate chain, issuer |
| SAN không khớp | Hostname verification failure | DNS/IP endpoint và SAN thực của cert |
| Chứng thư hết hạn/chưa có hiệu lực | TLS handshake thất bại sau mốc thời gian | `notBefore/notAfter`, NTP, cơ chế renewal |
| Client mTLS thiếu cert | Server reject handshake | `require_client_auth`, keystore client, EKU/chain |
| Internode chia cắt sau rollout | Node Down/unreachable, dropped messages | `optional`, peer trust, outbound keystore, SAN, restart order |
| TLS CPU tăng | p99/handshake latency tăng | Số kết nối tạo mới, connection pooling, codec/GC/CPU |
| CQL Unauthorized | TLS đã thành công nhưng query bị từ chối | CQL grants/roles, không tắt TLS |
| Port hoặc network ACL sai | Connection refused/timed out | `storage_port`, `native_transport_port`, policies |
| Client kết nối được vài node | Hostname/CA khác nhau giữa endpoints | Inventory cert từng node và routing metadata |
| Reload cert mà không có hiệu lực | New sessions vẫn thấy cert cũ | Release hot reload support, file path/password, log, restart policy |

Không đưa bí mật TLS/private key vào bug report, trace, chat hoặc public issue. Tập hợp **serial number/fingerprint public cert**, SAN, issuer, hạn dùng, error type và timestamp thường đủ để điều tra bước đầu.

## 11. Bài tập và câu hỏi vận dụng

### Bài 1 — TLS native nhưng internode plaintext

Một cluster bật `client_encryption_options.enabled: true` và `optional: false`; `server_encryption_options.internode_encryption: none`. Đội bảo mật tuyên bố toàn bộ dữ liệu trên mạng đã được bảo vệ. Nhận định này đúng không?

**Gợi ý:** sai. Kết nối ứng dụng đến node được bảo vệ nếu client thực sự kiểm tra server cert, nhưng **internode chưa bật encryption**. Cần chọn chế độ thích hợp, thường `all` nếu mọi peer traffic đều phải mã hóa.

### Bài 2 — optional và plaintext

Trong quá trình rolling upgrade, `client_encryption_options.enabled: true` nhưng `optional: true`. Ứng dụng cũ không dùng TLS vẫn kết nối được. Đây là lỗi phần mềm hay trạng thái cấu hình?

**Gợi ý:** đó là trạng thái **cho phép cả TLS và plaintext** theo thiết kế để chuyển tiếp. Không đáp ứng chính sách “TLS bắt buộc”. Phải hoàn tất migration client và đặt `optional: false`, kèm test kết nối plaintext bị từ chối.

### Bài 3 — hostname không khớp

Chứng thư của node có DNS SAN `db-1.internal.example`, Java Driver liên hệ bằng IP không nằm trong SAN. Handshake thất bại khi hostname validation được bật. Có nên tắt validation?

**Gợi ý:** không. Sửa endpoints để dùng DNS khớp cert hoặc cấp lại cert có IP SAN đúng. Tắt kiểm tra làm yếu xác minh danh tính, nhất là khi ứng dụng có thể bị điều hướng sang một node giả mạo.

### Bài 4 — mTLS đã chạy nhưng SELECT bị cấm

Ứng dụng cung cấp chứng thư client hợp lệ và TLS handshake thành công, nhưng nhận `UnauthorizedException` khi `SELECT`. TLS có bị cấu hình sai không?

**Gợi ý:** chưa chắc; mTLS xác minh certificate phía client, còn CQL authorization quyết định quyền truy vấn. Kiểm tra authenticator/role manager/authorizer và grants; không cấp quyền quá rộng chỉ để bypass kiểm thử.

### Bài 5 — chia cắt mạng khi bật internode TLS

Node A đã đặt `internode_encryption: all`, `optional: false`; B và C vẫn dùng plaintext, chưa có truststore. Cluster bắt đầu báo peer connection failures. Hãy đề xuất cách làm lại.

**Gợi ý:** rollback an toàn theo runbook để khôi phục reachability, cấp đúng cert/trust cho mọi node, dùng pha tương thích `optional: true` trong thời gian có giới hạn, xác minh peer TLS, cuối cùng chuyển sang bắt buộc theo thứ tự đã thử trong staging.

### Bài 6 — luân chuyển CA

CA dùng để ký chứng thư internode hết hạn sau một tháng. Vì sao không đổi toàn bộ node sang CA mới trước khi cập nhật truststores?

**Gợi ý:** các peer còn tin CA cũ có thể từ chối chứng thư mới và chia cắt cluster. Cần thời gian overlap nơi peer/client tin CA cũ và mới, rồi đổi cert/key từng node, xác minh kết nối mới, sau cùng gỡ CA cũ và revoke theo chính sách.

### Checklist hoàn thành lab

- [ ] Phân biệt native TLS, internode TLS, mTLS, CQL auth/authz và at-rest encryption.
- [ ] Kiểm tra SAN, CA chain, expiry, private key/keystore/truststore và ACL của file.
- [ ] Đã xác nhận phiên bản Cassandra/JVM/driver, DC/rack và các cổng native/internode thực tế.
- [ ] Giải thích được `none/dc/rack/all` và vì sao `dc` không mã hóa traffic nội DC.
- [ ] Chạy được kết nối CQL qua TLS với CA/hostname đúng; từ chối CA sai và plaintext ở target state.
- [ ] Nếu dùng mTLS, test client thiếu chứng thư bị từ chối và role không có quyền vẫn không được truy vấn.
- [ ] Kiểm tra `nodetool status`, peer TLS, read/write và CL ở RF phù hợp.
- [ ] Ghi nhận p95/p99, CPU, handshake failures và driver reconnects trước/sau rollout.
- [ ] Có kế hoạch rotate/revoke cert và khôi phục secret/KMS khi node/DC hỏng.
- [ ] Không để `optional: true` hoặc hostname validation bị tắt nếu policy yêu cầu mã hóa/xác minh bắt buộc.

## 12. Tài liệu tham khảo

1. Apache Cassandra Documentation — [Security: TLS/SSL, client-to-node và inter-node encryption](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/security.html).
2. Apache Cassandra Documentation — [cassandra.yaml reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `client_encryption_options`, `server_encryption_options`, optional/endpoint verification, truststore/keystore.
3. Apache Cassandra Documentation — [Cassandra 4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html): khác biệt cấu hình và cổng từ nhánh cũ.
4. Apache Cassandra Documentation — [Cassandra 3.11 cassandra.yaml](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html): đối chiếu tham số khi nâng cấp.
5. Apache Cassandra Documentation — [nodetool reloadssl](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/reloadssl.html): kiểm tra hỗ trợ reload certificate theo release.
6. Apache Cassandra Documentation — [CQL authentication và authorization](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/security.html): phân quyền khác với TLS.
7. Apache Cassandra Java Driver — [SSL configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/ssl/): cấu hình truststore, keystore, hostname validation và SSL engine factory theo phiên bản driver.
