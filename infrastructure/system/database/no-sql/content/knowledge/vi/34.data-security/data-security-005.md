# TLS giữa ứng dụng/nút và kiểm tra danh tính máy chủ

## 1. Bối cảnh: kết nối đã mã hóa nhưng có chắc là đúng database?

Một hệ thống Java kết nối tới một cụm NoSQL để lưu thông tin khách hàng. Trong cấu hình, đội phát triển đã bật `tls=true`; báo cáo vận hành cho thấy đường truyền được mã hóa. Tuy nhiên, khi triển khai vào môi trường mới, client nhận lỗi:

~~~text
javax.net.ssl.SSLHandshakeException:
No subject alternative DNS name matching db-prod.internal found
~~~

Một người đề xuất tắt **hostname verification** để ứng dụng chạy ngay. Nếu làm vậy, kết nối có thể được mã hóa nhưng ứng dụng **không còn kiểm tra đầy đủ server có đúng là dịch vụ mà nó định truy cập hay không**.

Điểm cần hiểu:

- **Mã hóa** bảo vệ nội dung dữ liệu trên đường truyền trước người quan sát không có khóa.
- **Xác thực chứng chỉ** kiểm chứng chứng chỉ server được cấp bởi một nguồn tin cậy theo chính sách, còn hạn và phù hợp các ràng buộc.
- **Kiểm tra danh tính máy chủ (hostname/IP identity verification)** đối chiếu tên hoặc địa chỉ endpoint dự định kết nối với định danh trong chứng chỉ.
- **Xác thực ứng dụng hoặc người dùng** quyết định ai được phép thực hiện truy vấn; đó là một lớp khác.
- **Mã hóa giữa các node** phải được cấu hình cho những đường kết nối nội bộ thực sự tồn tại, không tự kế thừa từ cấu hình app-to-database.

Bài học này thuộc module **Database No SQL**, chương **Bảo mật dữ liệu**, chủ đề **TLS giữa ứng dụng/nút và kiểm tra danh tính máy chủ**.

Mục tiêu không chỉ là làm lỗi handshake biến mất, mà là **xây một kết nối đúng endpoint, có chứng chỉ hợp lệ, bảo vệ được từng hop và có thể vận hành an toàn khi chứng chỉ/CA thay đổi**.

### Sau bài này bạn sẽ làm được gì?

1. Giải thích TLS bảo vệ điều gì và không bảo vệ điều gì trong NoSQL.
2. Phân biệt TCP, TLS, PKIX trust chain, SAN hostname verification, mTLS và database authorization.
3. Hiểu sự khác nhau giữa TLS ứng dụng–node và TLS node–node.
4. Chọn đúng truststore/keystore và thiết kế CA trust theo môi trường.
5. Thiết lập endpoint identification đúng khi dùng Java JSSE hoặc NoSQL driver.
6. Phân tích DNS, SNI, IP, SRV discovery, load balancer và service mesh.
7. Tránh các cách “sửa nhanh” nguy hiểm: trust-all, `insecureSkipVerify`, bỏ qua hostname hoặc dùng HTTP plaintext.
8. Lên kế hoạch tự động cấp mới/luân chuyển chứng chỉ và CA mà không cắt đồng loạt kết nối.
9. Chẩn đoán handshake errors bằng log và công cụ phù hợp, không làm lộ bí mật.
10. Viết kiểm thử xác minh client từ chối server sai danh tính và vẫn hoạt động khi thay chứng chỉ đúng cách.

---

## 2. Threat model: TLS đang ngăn kiểu tấn công nào?

Một NoSQL client truyền:

~~~text
username/password or token
query and parameters
document payload
database response
session metadata
```

qua mạng. Kẻ tấn công hoặc một điểm trung gian không đáng tin có thể cố:

- Nghe lén nội dung nếu đường truyền plaintext.
- Đọc thông tin xác thực hoặc dữ liệu cá nhân.
- Chèn/sửa nội dung hoặc mạo danh một endpoint.
- Đưa client tới một server khác qua DNS, routing hoặc proxy bị chiếm.
- Khai thác cấu hình cho phép chứng chỉ tùy ý.
- Buộc downgrade nếu hệ cho fallback sang plaintext không an toàn.

TLS được cấu hình đúng giúp **bảo mật và phát hiện thay đổi nội dung trong quá trình truyền**, đồng thời cho phép kiểm tra peer identity theo chính sách. TLS không tự chặn tất cả kiểu tấn công:

- Client hoặc database server bị chiếm quyền vẫn có thể thấy plaintext sau khi giải mã.
- TLS không mã hóa dữ liệu lúc nằm trên disk, log hay backup.
- TLS không thay quyền database (`SELECT`, `INSERT`, role/ACL).
- TLS không làm query có consistency hoặc durability cao hơn.
- TLS không giải quyết injection, exposed API, data exfiltration bằng tài khoản có quyền.
- TLS không tự bảo đảm database node đang khỏe hoặc trả dữ liệu nghiệp vụ đúng.
- TLS không đảm bảo traffic mọi hop đều được mã hóa nếu có nơi kết thúc TLS ở giữa.

### 2.1. Bốn yêu cầu phải xét độc lập

| Yêu cầu | Câu hỏi kiểm tra | Cơ chế điển hình |
|---|---|---|
| **Confidentiality** | Người ở giữa có đọc được payload không? | TLS encryption |
| **Integrity** | Payload có bị sửa khi truyền không? | TLS record protection |
| **Server identity** | Đây có đúng `db-prod.example.internal` không? | Trust chain + hostname/SAN verification |
| **Client identity/authorization** | Client này có được đọc bảng người khác không? | mTLS hoặc authentication + DB ACL |

Một service có TLS mà cho phép mọi user đọc mọi document vẫn không đáp ứng yêu cầu bảo mật dữ liệu.

---

## 3. Sơ đồ các kết nối phải bảo vệ

~~~mermaid
flowchart LR
    A["Java service A"] -->|"TLS + server verification"| LB["DB gateway / load balancer"]
    LB -->|"TLS riêng nếu terminate"| N1["NoSQL node 1"]
    N1 <-->|"Inter-node TLS"| N2["NoSQL node 2"]
    N2 <-->|"Inter-node TLS"| N3["NoSQL node 3"]
    A -.->|"Discovery / redirects"| N2
    B["Java service B"] -->|"TLS + optional mTLS"| LB
~~~

### 3.1. Client-to-node

Ứng dụng Java hoặc batch job kết nối tới NoSQL endpoint. Client thường cần kiểm tra **chứng chỉ server và endpoint identity**; server có thể yêu cầu client certificate hoặc một cơ chế auth ứng dụng riêng.

### 3.2. Node-to-node

NoSQL nodes truyền replication, gossip, consensus, streaming, backup hoặc cluster metadata. Các hop này có thể dùng cổng/protocol/cấu hình TLS **khác hẳn cổng client**.

### 3.3. Proxy/load balancer

Nếu TLS kết thúc tại gateway, ứng dụng xác thực **gateway endpoint**. Đoạn gateway → database cần được đánh giá và bảo vệ riêng theo threat model. Một TLS icon ở ngoài Internet không tự bảo đảm đoạn mạng nội bộ đã được mã hóa.

### 3.4. CDC, monitoring, admin và backup cũng là client

Không chỉ HTTP API: connector CDC, data migration, CLI quản trị, monitoring exporter, Spark job và backup agent cũng có thể kết nối NoSQL. Những client này cần trust/identity/rotation policy của riêng chúng.

---

## 4. TLS handshake diễn ra thế nào?

Một luồng đơn giản:

~~~mermaid
sequenceDiagram
    participant C as Java NoSQL client
    participant S as NoSQL server
    C->>S: ClientHello (versions, suites, optional SNI)
    S-->>C: ServerHello + certificate + handshake data
    Note over C: Verify chain, validity, usages, SAN endpoint
    Note over C,S: Establish authenticated encryption keys
    C->>S: Handshake Finished (verified)
    S-->>C: Handshake Finished (verified)
    C->>S: Encrypted authentication/query
    S-->>C: Encrypted response
~~~

Sơ đồ đã lược bớt thông điệp, đặc biệt khác biệt giữa TLS 1.2 và TLS 1.3.

### 4.1. `ClientHello`

Client thông báo các TLS versions, cipher suites và tham số hỗ trợ; với DNS endpoint có thể gửi **SNI (Server Name Indication)** để server/proxy chọn đúng chứng chỉ.

### 4.2. Chứng chỉ server

Server gửi leaf certificate và thường gửi các intermediate certificates cần thiết để client xây trust chain.

### 4.3. Client xác minh trước khi gửi bí mật ứng dụng

Ứng dụng cần chắc chắn trust chain và endpoint identity đúng trước khi trao database credentials/query. Khi handshake hoặc identity verification thất bại, **không fallback plaintext**.

### 4.4. Thỏa thuận khóa và bảo vệ phiên

Các phiên TLS hiện đại sử dụng các thuật toán theo bộ cấu hình và phiên bản đã thương lượng. TLS 1.3 dùng cơ chế trao đổi khóa ephemeral cho đường handshake chuẩn; TLS 1.2 có nhiều cipher suites nên phải chọn cấu hình bảo mật phù hợp.

### 4.5. TLS không phải giao thức của document

Sau handshake, protocol NoSQL (MongoDB wire protocol, Cassandra native protocol, Redis RESP, HTTP API...) đi **bên trong** TLS. Bật TLS không thay đổi cấu trúc document hoặc tính chất query logic.

---

## 5. Xác minh server có hai phần: tin CA và đúng danh tính

Một kiểm tra an toàn điển hình:

~~~text
Leaf certificate for db-prod.example.internal
         |
         v
Intermediate CA certificate
         |
         v
Root CA trusted by client
         |
         +--> Signature chain valid?
         +--> Validity dates acceptable?
         +--> Certificate usages/constraints acceptable?
         +--> Revocation policy satisfied as configured?
         +--> Requested DNS/IP matches SAN?
                    |
                    v
             Connection accepted
~~~

### 5.1. Chain validation

Client xác minh chuỗi chữ ký tới trust anchor được phép và các điều kiện PKIX liên quan. **Chỉ biết chứng chỉ “do CA nào đó ký” chưa đủ** nếu CA đó không nằm trong trust policy được phê duyệt.

### 5.2. Validity

Kiểm `notBefore` và `notAfter` theo thời gian tin cậy. Đồng hồ hệ thống lệch có thể làm chứng chỉ chưa hiệu lực hoặc hết hạn.

### 5.3. Extended Key Usage và Key Usage

Chứng chỉ TLS server/client cần phù hợp key usage, extended key usage (ví dụ `serverAuth`, `clientAuth`) và các ràng buộc CA. Một chứng chỉ ký cho mục đích khác không mặc định dùng được làm TLS server cert.

### 5.4. Hostname/SAN verification

Một client truy cập `db-prod.example.internal` phải đối chiếu **tên mà client kỳ vọng** với các danh tính trong chứng chỉ, chủ yếu ở trường **Subject Alternative Name (SAN)**.

### 5.5. Không biến truststore thành danh sách “tin mọi thứ”

Cài mọi CA chưa được đánh giá vào truststore làm mở rộng bề mặt tin cậy. Nên sử dụng tập CA phù hợp với môi trường/endpoint, quản trị vòng đời và phân quyền chỉnh truststore.

---

## 6. SAN là gì và vì sao Common Name không đủ?

Một certificate ví dụ:

~~~text
Subject:
  CN = db-prod.example.internal

Subject Alternative Name:
  DNS:db-prod.example.internal
  DNS:db-read.example.internal
  IP Address:10.20.30.40
~~~

Trong mô hình hiện đại, **SAN là nơi quan trọng để khai báo danh tính endpoint**. Không thiết kế chỉ dựa vào `CN` vì hành vi fallback CN có thể không được hỗ trợ hoặc bị hạn chế bởi nhiều clients/libraries.

### 6.1. Tên DNS

Kết nối bằng `db-prod.example.internal` yêu cầu DNS identity phù hợp với chứng chỉ.

### 6.2. Địa chỉ IP

Nếu client kết nối thẳng tới `10.20.30.40`, thông thường identity matching yêu cầu **IP SAN** tương ứng; có một DNS SAN nhưng không có IP SAN không tự đủ cho việc kết nối bằng IP.

### 6.3. Đổi CNAME

Nếu `db.customer.internal` là CNAME trỏ tới `db-01.internal`, client nên xác minh theo **tên endpoint mà nó định kết nối**, không tùy tiện dùng reverse DNS hoặc IP của node rồi bỏ qua kiểm tra. Cách driver xử lý discovery có thể khác nhau và phải được thử.

### 6.4. Wildcard

Trong những trường hợp được thư viện hỗ trợ, `*.db.example.internal` thường phù hợp một label như `n1.db.example.internal`, nhưng không phù hợp tên gốc `db.example.internal` hoặc tên nhiều cấp `x.y.db.example.internal`.

Không sử dụng wildcard như công cụ cấp phép truy cập mọi máy. Một wildcard certificate quá rộng làm tăng tác động nếu private key bị lộ.

### 6.5. IDN và chuẩn hóa tên

Internationalized domain names và các quy tắc case/normalization có xử lý riêng trong thư viện. Không tự viết `endsWith(domain)` để kiểm hostname; dùng bộ kiểm tra danh tính TLS chuẩn của driver/JDK.

### 6.6. Certificate identity không phải database role

Chứng chỉ đúng `db-prod.example.internal` chứng minh danh tính peer TLS theo trust policy, **không chứng minh** tài khoản Java có quyền `DROP TABLE` hay quyền truy cập tenant khác.

---

## 7. Một ví dụ kết nối sai danh tính

Giả sử Java app kết nối:

~~~text
Requested host: db-prod.example.internal
DNS resolves:   10.20.30.40

Server presents:
  SAN DNS: db-staging.example.internal
  Issued by trusted Corporate CA
~~~

Chain có thể hợp lệ nhưng **hostname không khớp**. Kết nối phải bị từ chối nếu expected server identity là `db-prod.example.internal`.

### 7.1. Điều gì xảy ra nếu tắt hostname verification?

Ứng dụng có thể chấp nhận staging server hoặc một endpoint khác cũng có chứng chỉ từ CA tin cậy. Hậu quả có thể là:

- Gửi dữ liệu khách hàng production sang môi trường khác.
- Rò database credentials hoặc token.
- Ghi sai collection/cluster.
- Cho phép một endpoint hợp lệ về CA nhưng không phải dịch vụ dự kiến mạo nhận traffic.

### 7.2. Cách sửa đúng

Chọn một trong những hướng phù hợp, qua quy trình cấp cert:

1. Dùng đúng DNS endpoint được chứng chỉ bao phủ.
2. Cấp lại server certificate có SAN của DNS endpoint dự kiến.
3. Sửa routing/SNI/proxy để server gửi đúng certificate.
4. Nếu cần kết nối IP, bổ sung IP SAN và quản lý thay đổi IP.
5. Kiểm khả năng driver dùng discovery/topology addresses khác initial seed.

### 7.3. Không sửa bằng “trust all”

Trusting mọi certificates hoặc vô hiệu hóa tên máy chủ là bỏ đi một phần bảo vệ TLS. Một lỗi cấu hình xác thực **không phải lý do** để tắt xác thực.

---

## 8. DNS, SNI và nhiều database node

### 8.1. DNS giải quyết địa chỉ, không chứng minh danh tính

DNS chuyển tên thành địa chỉ theo cấu hình/record trả về. TLS identity verification mới giúp client quyết định chứng chỉ server có phù hợp tên kỳ vọng không.

### 8.2. SNI giải quyết vấn đề nhiều chứng chỉ trên cùng endpoint

Một proxy phục vụ `db-prod.internal` và `db-stage.internal` có thể chọn certificate bằng SNI. Nếu client kết nối bằng IP hoặc driver không gửi đúng SNI, proxy có thể trả certificate mặc định và handshake/hostname check fail.

### 8.3. Seed host và discovery host khác nhau

Một Cassandra/MongoDB/Redis Cluster client ban đầu dùng seed DNS, sau đó có thể nhận địa chỉ các node thực tế.

~~~text
seed.db.internal -> node-1
Topology response -> 10.11.0.21, 10.11.0.22, 10.11.0.23
~~~

Nếu certificates chỉ chứa `seed.db.internal` nhưng client bắt đầu kết nối thẳng tới node IPs, các kết nối sau có thể fail identity check.

### 8.4. Hướng thiết kế

- Cấp certificate với danh tính **mọi endpoint được client kết nối**, theo topology.
- Ưu tiên ổn định DNS names cho nodes khi hợp lý.
- Cấu hình advertised addresses/discovery đúng môi trường.
- Kiểm IP SAN nếu kết nối bằng IP là một phần thiết kế.
- Không bỏ hostname validation để “hỗ trợ cluster mode”.

### 8.5. SRV discovery

Một driver hỗ trợ DNS SRV có thể nhận danh sách hosts khác với tên gốc. TLS phải xác minh theo contract của driver và các hosts được khám phá; không tự giả định một chứng chỉ wildcard áp được cho mọi target SRV.

---

## 9. TLS versions và cipher suites

### 9.1. Ưu tiên TLS hiện đại

Với các thành phần hỗ trợ, chọn TLS 1.3 và/hoặc TLS 1.2 được cấu hình an toàn theo chính sách tổ chức. Tránh các phiên bản lỗi thời như SSLv2/SSLv3 và TLS 1.0/1.1 khi không có lý do hợp lệ được phê duyệt.

### 9.2. Không chỉ kiểm phiên bản

TLS 1.2 hỗ trợ nhiều cipher suites, trong đó không phải bộ nào cũng phù hợp yêu cầu hiện hành. Cần xét:

- Key exchange có forward secrecy phù hợp.
- Authenticated encryption.
- Certificate key size/algorithm.
- JDK crypto provider.
- Managed service policy.
- FIPS/compliance khi bắt buộc.

### 9.3. TLS 1.3 không tự giải mọi lỗi

Vẫn cần kiểm certificate chain, hostname, client identity và database authorization. TLS 1.3 với trust-all vẫn là cấu hình sai về xác thực peer.

### 9.4. Negotiation failure

Nếu server chỉ cho TLS 1.3 còn client/JDK chỉ hỗ trợ TLS 1.2, handshake có thể thất bại. Cần nâng driver/JDK/server policy theo kế hoạch, **không quay về plaintext**.

### 9.5. TLS 0-RTT

Một số TLS deployments có thể hỗ trợ early data/0-RTT và có **replay considerations**. Không bật hoặc sử dụng 0-RTT cho mutation/transaction nhạy cảm nếu protocol/driver và threat model không có thiết kế chống replay rõ ràng.

---

## 10. mTLS: xác thực cả hai phía

Trong TLS một chiều phổ biến:

~~~text
Java client --> validates server certificate
Server      --> may authenticate application via password/token
~~~

Với **mutual TLS (mTLS)**:

~~~text
Java client --> validates server certificate/identity
Server      --> validates client certificate/identity
```

### 10.1. mTLS cung cấp gì?

- Server xác thực peer client ở tầng TLS theo CA/trust/identity policy.
- Client vẫn cần xác thực server.
- Có thể ánh xạ client certificate identity tới role/service account theo backend policy.
- Giảm phụ thuộc vào shared passwords trong những kiến trúc phù hợp.

### 10.2. mTLS không tự cấp quyền truy vấn

Một certificate được trust không đồng nghĩa client được đọc mọi keyspace/collection hoặc mọi tenant. NoSQL vẫn cần authentication mapping và authorization policy.

### 10.3. Server certificate và client certificate khác mục đích

Có thể dùng CA/policy riêng, `serverAuth`/`clientAuth` EKU và quy tắc cấp danh tính. Không dùng một shared certificate/private key cho mọi ứng dụng để “đỡ cấu hình”, vì khi lộ khóa khó truy vết và thu hồi chọn lọc.

### 10.4. Node-to-node mTLS

Mỗi node có thể vừa là TLS client vừa là TLS server khi trao replication/gossip; tùy engine, nó cần certificate có usage phù hợp và rules tin cậy cho peer nodes.

### 10.5. Revocation và vòng đời

Với mTLS, một client key bị lộ cần có khả năng ngừng cấp quyền và triển khai certificate rotation/revocation strategy. Không giả định mọi Java driver mặc định kiểm CRL/OCSP đầy đủ; cần xác minh hành vi thực tế của trust engine và policy.

---

## 11. Truststore, keystore và private key trong Java

| Thành phần | Nội dung thường có | Dùng để |
|---|---|---|
| **Truststore** | Trusted CA certificates/trust anchors | Xác minh peer |
| **Keystore/identity store** | Private key + certificate chain của client/server | Chứng minh danh tính phía mình |
| **Server certificate** | Public identity và SAN | Cho client kiểm tra server |
| **Private key** | Bí mật mật mã của peer | Ký/chứng minh sở hữu key trong handshake |
| **Certificate chain** | Leaf + intermediate issuers | Xây đường tin cậy |
| **CA root/intermediate** | Chứng chỉ của authority | Cấp và xác minh leaf |

### 11.1. Public certificate không phải secret

Certificate công khai có thể được xem và phân phối; **private key phải bảo vệ**. Tuy nhiên certificate metadata vẫn có thể để lộ tên nội bộ cần cân nhắc khi đăng public.

### 11.2. Truststore không chứa plaintext password database

Database credentials cần quản lý riêng qua secrets provider/auth system. Truststore password dùng để bảo vệ file keystore/truststore format không phải database password.

### 11.3. PKCS#12 và JKS

Java hỗ trợ keystore formats như `PKCS12`, `JKS` tùy provider/JDK. PKCS#12 thường thuận tiện cho certificate/key import; sử dụng theo chính sách hệ thống và compatibility của driver.

### 11.4. JVM default trust anchors

Một Java driver có thể dùng default JSSE truststore/trust manager, **hoặc** có TLS context riêng. Không suy mọi driver đọc đúng một file chỉ vì đã đặt JVM system property.

### 11.5. Scope của trust

Tránh thêm corporate root CA quá rộng vào truststore **của mọi ứng dụng** nếu chỉ một NoSQL service cần CA đó. Có thể ưu tiên TLS context riêng cho driver, nhưng phải bảo đảm nó vẫn xác minh đúng chain và hostname.

---

## 12. Java JSSE: bật hostname verification đúng cách

Ví dụ dưới đây dùng `SSLSocket` để minh họa **một kết nối TLS tới đúng DNS endpoint**. Đây không phải driver NoSQL đầy đủ, và không trao protocol database.

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class VerifiedTlsSocket {

    public static void main(String[] args) throws Exception {
        String host = "db-prod.example.internal";
        int port = 12345; // Port giả định của dịch vụ TLS.

        SSLSocketFactory factory =
            (SSLSocketFactory)
                SSLSocketFactory.getDefault();

        try (SSLSocket socket =
                (SSLSocket) factory.createSocket(host, port)) {

            SSLParameters parameters =
                socket.getSSLParameters();

            // Dùng cơ chế endpoint identity checking của JSSE.
            // Tên algorithm "HTTPS" dùng được cho DNS
            // hostname matching ở TLS socket dù protocol
            // ứng dụng nằm bên trong không phải HTTP.
            parameters.setEndpointIdentificationAlgorithm(
                "HTTPS"
            );

            socket.setSSLParameters(parameters);

            // Nếu chain hoặc hostname không hợp lệ,
            // quá trình handshake phải thất bại.
            socket.startHandshake();

            System.out.println(
                "TLS handshake and endpoint check passed"
            );
        }
    }
}
~~~

### 12.1. Điều gì được kiểm?

Với default trust managers phù hợp, handshake kiểm trust chain và endpoint identification khi `HTTPS` algorithm được đặt trước handshake.

### 12.2. Điều gì không được kiểm?

Ví dụ chưa chạy MongoDB/Cassandra/Redis protocol, chưa xác thực database user, chưa cấu hình mTLS và chưa thiết lập application authorization.

### 12.3. `SSLContext` và trust managers

`SSLSocketFactory.getDefault()` có thể sử dụng JSSE defaults của process. Một ứng dụng thực tế có thể cần `SSLContext` riêng với truststore nội bộ; điều này không thay yêu cầu hostname matching.

### 12.4. Không tự so CN/SAN bằng code thủ công

Đừng tự parse Subject rồi làm `subject.contains(host)` hoặc `dns.endsWith(...)`. Wildcard, IDN, IP SAN và các rule RFC phức tạp hơn; dùng built-in endpoint identification hoặc driver verify-peer implementation đáng tin.

### 12.5. Không kết nối IP rồi sửa identity expectation tùy tiện

Nếu server có DNS SAN, kết nối bằng DNS. Nếu bắt buộc kết nối IP, certificate cần IP SAN đúng và driver cần hỗ trợ matching phù hợp.

---

## 13. Java HttpClient: HTTPS tới managed NoSQL endpoint

Một số NoSQL/managed APIs dùng HTTPS. Java 11+ `HttpClient` có TLS theo HTTPS URL.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpsHealthCheck {

    public static void main(String[] args) throws Exception {
        URI endpoint = URI.create(
            "https://api-db.example.internal/health"
        );

        try (HttpClient client =
                HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build()) {

            HttpRequest request =
                HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response =
                client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
                );

            System.out.println(response.statusCode());
        }
    }
}
~~~

**Lưu ý về phiên bản:** `HttpClient` có lifecycle/`close()` khác nhau theo JDK. Ví dụ dùng API đóng client ở JDK hỗ trợ `AutoCloseable` tương ứng (như JDK mới). Nếu dự án dùng Java 11/17, quản lý lifecycle theo API đúng của bản JDK đang chạy, không sao chép nguyên `try-with-resources` nếu `HttpClient` chưa implement `AutoCloseable`.

### 13.1. HTTPS hostname verification

Đường HTTPS của `HttpClient` chuẩn thường thực hiện xác minh certificate/hostname theo cấu hình TLS hợp lệ. Không dùng system properties không an toàn để tắt hostname check trong production.

### 13.2. SDK managed service

Nếu dùng AWS SDK để gọi DynamoDB qua HTTPS, hãy để SDK quản lý endpoint, TLS và authentication/signing đúng cách. Một HTTPS health check tùy ý **không thay** AWS Signature Version 4, authorization hoặc chính sách endpoint.

### 13.3. Cẩn trọng redirect

Nếu HTTP client tự follow redirect tới host khác, cần có domain/redirect policy phù hợp và không gửi credentials nhạy cảm sang destination không được phép.

---

## 14. Tạo SSLContext với truststore riêng

Một ứng dụng nội bộ có thể cần trust một Private CA của cụm database mà không thay global JVM truststore.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class DbTlsContext {

    public static SSLContext fromTruststore(
            Path truststorePath,
            char[] truststorePassword) throws Exception {

        KeyStore truststore = KeyStore.getInstance("PKCS12");

        try (InputStream in =
                Files.newInputStream(truststorePath)) {
            truststore.load(in, truststorePassword);
        }

        TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );

        trustManagerFactory.init(truststore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            null,
            trustManagerFactory.getTrustManagers(),
            null
        );

        return context;
    }
}
~~~

### 14.1. Điều quan trọng nhất

`SSLContext` này cung cấp trust policy từ truststore. **Nó không tự bảo đảm** một NoSQL driver sẽ thực hiện hostname verification nếu driver không bật endpoint checking. Phải xác nhận **cả hai**.

### 14.2. Nếu dùng custom truststore

Một custom truststore có thể **thay thế** root CAs của JDK, làm các HTTPS calls khác thất bại nếu dùng global SSL context. Tách TLS contexts theo client hoặc thiết kế trustset có chủ đích.

### 14.3. Secret loading

Đừng hardcode mật khẩu truststore trong Git, command-line history hoặc application logs. Dùng secrets manager/volume/mount theo chính sách, giới hạn quyền đọc.

### 14.4. Truststore rotation

Khi thay CA, deploy truststore chứa cả old/new CA trong giai đoạn chuyển tiếp có kiểm soát, sau đó mới phát leaf certificates từ CA mới rồi retire CA cũ.

### 14.5. Tránh “trust manager chấp nhận mọi certificate”

Một custom `X509TrustManager` với `checkServerTrusted(...)` rỗng phá chain verification. Đừng dùng trong production, staging tích hợp traffic thật hoặc công cụ kiểm thử mà sau đó có thể copy vào service.

---

## 15. Java mTLS: client identity và server trust cùng lúc

Ví dụ khái niệm dùng PKCS#12 keystore chứa client key/cert chain và truststore chứa server CA.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public final class MutualTlsContext {

    public static SSLContext create(
            Path clientKeyStoreFile,
            char[] clientKeyPassword,
            Path serverTrustStoreFile,
            char[] trustStorePassword) throws Exception {

        KeyStore identity = KeyStore.getInstance("PKCS12");

        try (InputStream in =
                Files.newInputStream(clientKeyStoreFile)) {
            identity.load(in, clientKeyPassword);
        }

        KeyManagerFactory kmf =
            KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
            );
        kmf.init(identity, clientKeyPassword);

        KeyStore trust = KeyStore.getInstance("PKCS12");

        try (InputStream in =
                Files.newInputStream(serverTrustStoreFile)) {
            trust.load(in, trustStorePassword);
        }

        TrustManagerFactory tmf =
            TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
        tmf.init(trust);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
            kmf.getKeyManagers(),
            tmf.getTrustManagers(),
            new SecureRandom()
        );

        return context;
    }
}
~~~

### 15.1. Server vẫn phải yêu cầu client certificate

Client có identity store không có nghĩa server chắc chắn yêu cầu mTLS. Server-side configuration phải yêu cầu/kiểm client certificate đúng policy.

### 15.2. Hostname verification vẫn phải bật

`SSLContext` có `KeyManagers` và `TrustManagers` nhưng driver vẫn phải xác minh hostname ở phía client; client cert không thay thế kiểm tra server.

### 15.3. Không dùng một certificate cho mọi service

Mỗi workload/service identity nên có lifecycle và permission boundaries phù hợp. Nếu mọi ứng dụng dùng cùng private key, khó biết ai đang kết nối và khó thu hồi khi một ứng dụng bị xâm phạm.

### 15.4. Quản lý private key

- Giới hạn filesystem permissions.
- Dùng short-lived identities/secret manager nếu hạ tầng hỗ trợ.
- Không log private keys hoặc keystore bytes.
- Cấp lại khi nghi khóa bị lộ, không chỉ thay mật khẩu keystore.
- Tránh phân phối key qua image/container layers.

---

## 16. Cấu hình JSSE ở JVM: quyền hạn và rủi ro

Một ứng dụng có thể được cấu hình truststore thông qua system properties:

~~~text
-Djavax.net.ssl.trustStore=/etc/app/tls/db-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

Trên môi trường production, cách cung cấp mật khẩu, file permissions và service startup cần thiết kế riêng. Tránh đưa secret trực tiếp vào startup flags vì có thể bị lộ qua process listings/diagnostics.

### 16.1. System property có thể ảnh hưởng toàn process

Nếu một app dùng đồng thời NoSQL, OAuth HTTPS endpoint và payment SDK, đổi default truststore có thể ảnh hưởng mọi kết nối dùng default JSSE context.

### 16.2. Driver có thể không dùng default JSSE

Một số driver/transport có custom SSL engine hoặc Netty pipeline. Chúng có thể cần cấu hình TLS riêng, không tự lấy tất cả `javax.net.ssl.*` settings.

### 16.3. Không cấu hình “trustStore = leaf cert” mà quên rotation

Tin trực tiếp leaf certificate có thể hoạt động ngắn hạn, nhưng khi cert được cấp lại thì client mất trust. Pinning leaf key/identity cần thiết kế rotation đặc biệt; trust vào CA phù hợp thường linh hoạt hơn.

### 16.4. Password khác encryption

Truststore password không tự làm lưu trữ các CA certificates thành bí mật cần tuyệt đối; nhưng keystore chứa private key phải được bảo vệ nghiêm ngặt. Không đánh đồng hai loại file.

---

## 17. MongoDB Java Driver: TLS và server identity

MongoDB Java synchronous client có thể bật TLS qua connection string và SSL settings.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoTlsClient {

    public static MongoClient connect() {
        ConnectionString connectionString =
            new ConnectionString(
                "mongodb://db-prod.example.internal:27017/"
                    + "?tls=true"
            );

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(connectionString)
                .applyToSslSettings(ssl -> {
                    ssl.enabled(true);
                    ssl.invalidHostNameAllowed(false);
                })
                .build();

        return MongoClients.create(settings);
    }
}
~~~

### 17.1. Vì sao `invalidHostNameAllowed(false)` đáng chú ý?

Nó thể hiện chủ đích **không cho phép hostname không khớp**. Trong driver configurations hiện đại, verify thường được bật mặc định, nhưng vẫn nên kiểm tra đúng version và options đang chạy.

### 17.2. CA trust

Có thể dùng default truststore hoặc custom SSLContext theo driver API. Trust phải khớp server certificate chain; nếu dùng private CA, hãy đưa CA phù hợp vào truststore, **không tắt certificate validation**.

### 17.3. `mongodb+srv`

Đường SRV discovery có quy tắc chọn hosts/TLS behavior riêng tùy driver; cần kiểm endpoint mà client thật sự kết nối cùng SAN của các node. Không coi một seed name duy nhất bảo đảm mọi discovered host có matching certificate.

### 17.4. X.509 authentication

MongoDB có thể dùng X.509 client certificates cho authentication ở những cấu hình phù hợp. Đây là phần **client identity**, khác server identity và khác read/write authorization.

### 17.5. Replica set và sharding

Kiểm TLS ở **mọi mongos/mongod endpoint** có thể được client chọn sau topology discovery, không chỉ hostname kết nối đầu tiên. Những certificates khác nhau giữa nodes có thể gây lỗi chỉ khi failover.

### 17.6. Không dùng `tlsAllowInvalidCertificates` hay cho phép invalid hostnames để chữa sản xuất

Nếu app báo lỗi host mismatch, giải pháp là sửa DNS/topology/cert SAN/trust chain. Cho phép invalid certificates/hostnames làm yếu security boundary.

---

## 18. Cassandra Java Driver: client TLS khác inter-node TLS

Trong Cassandra, phải phân biệt:

- **Client-to-node encryption:** native protocol từ Java driver tới Cassandra.
- **Server-to-server encryption:** trao đổi giữa Cassandra nodes cho cluster operations, theo engine/version configuration.

### 18.1. Java Driver 4.x ví dụ cấu trúc

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import javax.net.ssl.SSLContext;

public final class CassandraTls {

    public static CqlSession create(
            SSLContext trustedContext) {

        return CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress(
                    "cassandra-1.example.internal",
                    9042
                )
            )
            .withLocalDatacenter("dc1")
            .withSslContext(trustedContext)
            .build();
    }
}
~~~

### 18.2. Giới hạn quan trọng của code

Truyền một `SSLContext` giúp cung cấp trust managers/ciphers nhưng **không tự chứng minh hostname validation đang bật ở mọi driver version/configuration**. Cần cấu hình/kiểm `SslEngineFactory`, hostname verification và discovered node addresses theo driver version.

### 18.3. Contact point vs advertised addresses

Java driver dùng contact point ban đầu, sau đó khám phá nhiều nodes. Chứng chỉ phải phù hợp danh tính của các endpoints mà driver thực sự dùng. Nếu driver chọn IP mà certificate chỉ có DNS SAN, hãy sửa topology/identity thay vì tắt verification.

### 18.4. Node encryption

Trong Cassandra, những cấu hình như `client_encryption_options` và `server_encryption_options` (tên/options chính xác theo version) xử lý các mục tiêu khác nhau. Bật client TLS **không tự bật inter-node TLS**.

### 18.5. DC và cross-region

Replication giữa datacenters có thể đi qua mạng ít tin cậy hơn. Cần bảo vệ inter-node connections, xác minh peer identity và quản trị CA/certs phù hợp region/DC.

### 18.6. Performance

TLS tạo handshake/crypto overhead, nhưng không thể kết luận phải tắt TLS khi Cassandra latency tăng. Trước tiên đo connection churn, TLS handshake rate, pool reuse, query/compaction và replication/network latency.

---

## 19. Redis và Lettuce: TLS, verify-peer, cluster redirects

Redis có thể được triển khai qua TLS (trực tiếp hoặc proxy/managed endpoint) và Java Lettuce hỗ trợ cấu hình SSL/TLS.

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;

public final class LettuceTls {

    public static RedisClient createClient() {
        RedisURI uri = RedisURI.builder()
            .withHost("cache-prod.example.internal")
            .withPort(6380) // Chỉ là port ví dụ.
            .withSsl(true)
            .withVerifyPeer(true)
            .build();

        return RedisClient.create(uri);
    }
}
~~~

### 19.1. Verify-peer phải thực sự kiểm chain và endpoint

Tên option và default cụ thể thay đổi theo Lettuce version/transport configuration. Hãy kiểm certificate + host mismatch tests thay vì chỉ nhìn `withSsl(true)`.

### 19.2. Cluster redirects

Trong Redis Cluster, client có thể nhận redirects tới những nodes khác. Cần chứng chỉ/SAN phù hợp từng node address. Một endpoint qua load balancer không tự giải quyết certificate của mọi redirect target.

### 19.3. Redis auth vẫn cần

Ngay cả khi TLS được thiết lập, Redis ACL/password/user authentication vẫn là lớp phân quyền theo deployment. mTLS nếu được hỗ trợ và cấu hình không mặc định thay các nguyên tắc least privilege.

### 19.4. TLS replication/cluster bus

Redis có những cấu hình riêng cho TLS giữa replicas và cluster nodes tùy version. Đừng chỉ mã hóa client port rồi cho rằng replication traffic đã được bảo vệ.

### 19.5. Không bật port plaintext “dự phòng” tùy tiện

Nếu tổ chức bắt buộc TLS, việc mở cổng không mã hóa cho client “khi lỗi cert” có thể làm mất toàn bộ bảo đảm truyền dữ liệu. Cần policy cấm downgrade và kiểm firewall.

---

## 20. DynamoDB và managed HTTPS NoSQL

Amazon DynamoDB sử dụng HTTPS endpoints qua AWS SDK trong mô hình phổ biến.

### 20.1. TLS và request signing là hai việc

- **TLS** xác thực HTTPS endpoint và bảo vệ request trên đường truyền.
- **AWS Signature Version 4** giúp xác thực và kiểm tính hợp lệ của signed requests theo AWS auth protocol.
- **IAM policy** kiểm quyền thực hiện API với table/index/resources.

Một HTTPS connection thành công không đồng nghĩa caller có quyền `PutItem`.

### 20.2. Không thay endpoint bằng HTTP tùy tiện

Custom endpoint (ví dụ local emulator trong phát triển) có thể dùng HTTP trong một môi trường cách ly, nhưng production phải dùng secure endpoints và không bypass trust validation.

### 20.3. VPC endpoints/private connectivity

Private network path không thay TLS peer authentication. Internal network vẫn có threats do cấu hình sai, quyền truy cập rộng hoặc node bị chiếm.

### 20.4. Không tự cấu hình inter-node TLS của managed service

Với DynamoDB, customers không quản trị certificate cho từng storage node nội bộ như Cassandra self-hosted. Tập trung vào SDK client HTTPS, IAM, network controls, region/endpoint validation và service encryption guarantees.

---

## 21. Elasticsearch/OpenSearch, Couchbase và Neo4j: nhiều giao thức, nhiều port

### 21.1. Elasticsearch/OpenSearch

Phân biệt:

- HTTP/REST layer TLS cho clients.
- Transport/inter-node TLS cho cluster communications.

Cấu hình và client libraries thay đổi theo version/deployment; cần cert riêng/usage phù hợp và xác minh identity giữa nodes. Một REST endpoint `https://` không chứng minh transport layer đã được mã hóa.

### 21.2. Couchbase

Có nhiều services/endpoints: KV, query, search, analytics, management và cluster traffic. Không chỉ bảo vệ một cổng HTTPS quản trị. Kiểm TLS support/trust/peer identity của từng SDK connection mode và node discovery.

### 21.3. Neo4j

Bolt driver có connection schemes/encryption/trust settings tùy driver/version. Không dùng cấu hình kiểu “trust all” để khắc phục certificate mismatch. Cluster routing có thể kết nối nhiều members nên phải kiểm certificates theo addresses được quảng bá.

### 21.4. Không sao chép flags của engine này sang engine khác

Cùng là TLS nhưng driver có thể dùng JSSE, Netty, OpenSSL hoặc transport SDK riêng. **Cú pháp và default verification** không nhất thiết giống nhau.

---

## 22. TLS giữa NoSQL nodes: replication, election và streaming

Một cluster có thể trao:

~~~text
node A <-> node B: replication
node B <-> node C: cluster metadata
node A <-> node C: repair/anti-entropy
node C <-> node D: bootstrap/streaming
```

Những kết nối này thường có data sensitivity cao, vì có thể mang toàn bộ partitions, logs hoặc checkpoints.

### 22.1. Encryption in transit cần tính mọi path

Không chỉ write forwarding mà cả:

- Replica synchronization.
- Node bootstrap.
- Repair/compaction streaming.
- Backup/restore transfers.
- Cluster gossip/metadata nếu chứa thông tin nhạy cảm.
- Multi-region replication.

### 22.2. Peer identity

Một node mới gia nhập phải được phân biệt với node giả mạo. Chain validation và peer identity/authorization (có thể mTLS) phải bảo đảm node hợp lệ theo cluster membership policy.

### 22.3. Certificate lifecycle phức tạp hơn client TLS

Một node có thể cần cả serverAuth và clientAuth roles. Khi thay CA, phải duy trì compatibility giữa nodes đang chạy version khác nhau trong rolling rollout.

### 22.4. Network partitions

TLS không giải quyết election/quorum/split-brain của database. Nó chỉ bảo vệ và xác thực các links mà cluster protocol sử dụng.

### 22.5. Không tắt inter-node TLS để chữa bootstrap

Một lỗi `unknown_ca` khi node mới join thường cần sửa node certificate/trust/advertised address. Cho phép plaintext node traffic có thể lộ dữ liệu replica.

---

## 23. Load balancer TLS termination và end-to-end security

Xét:

~~~text
Java client --TLS A--> Proxy --TLS B--> NoSQL node
```

Có **hai phiên TLS**, mỗi phiên có certificate/trust/identity và key riêng.

### 23.1. TLS A

Java app xác thực proxy service endpoint: ví dụ `db-gateway.prod.internal`.

### 23.2. TLS B

Proxy xác thực backend node theo policy; backend có thể xác thực proxy qua mTLS hoặc service credentials.

### 23.3. “TLS ở client” không chứng minh hop B bảo mật

Nếu proxy giải mã rồi dùng plaintext tới database qua một mạng có rủi ro, bảo đảm end-to-end không như kỳ vọng.

### 23.4. SNI và host header/metadata

Proxy có thể chọn certificate/upstream bằng SNI hoặc protocol metadata. Cần bảo đảm tenant/cluster routing và TLS identity không bị trộn, tránh đưa production request sang staging.

### 23.5. Service mesh

Một mesh có thể triển khai mTLS giữa workload proxies. Nhưng một app kết nối localhost tới sidecar có thể không tự kiểm tên **database**; cần hiểu workload identity, mesh policy và boundary thực tế. Không xem “mesh STRICT mTLS” là bằng chứng mọi NoSQL native protocol đã có authorization đúng.

---

## 24. Certificate pinning: khi nào nên cân nhắc?

Một số hệ muốn pin leaf certificate hoặc public key để giảm phạm vi CA trust.

### 24.1. Lợi ích

Có thể hạn chế tập identities/keys được chấp nhận ngoài chính sách CA thông thường, trong threat model cụ thể.

### 24.2. Chi phí

- Leaf certificate rotation có thể làm client outage.
- Failover sang node có key khác có thể bị từ chối.
- CA migration thêm độ phức tạp.
- Managed provider có thể đổi certificates theo lịch mà bạn không kiểm soát.

### 24.3. Không thay hostname validation

Pinning key không luôn chứng minh endpoint name/role đúng nếu pin được dùng chung trên nhiều services. Chúng là các biện pháp bổ sung, cần threat model và lifecycle rõ.

### 24.4. Ưu tiên đơn giản

Đối với nhiều hệ thống nội bộ, private CA trust được quản trị chặt, SAN verification, mTLS identity, rotation và authorization thường dễ vận hành hơn pin leaf certificate lâu dài. Nhưng điều này không phải quyết định thay security review của sản phẩm.

---

## 25. Cấp chứng chỉ cho cluster: định danh nào nên xuất hiện trong SAN?

Một thiết kế self-hosted:

~~~text
cassandra-0.db.svc.cluster.local
cassandra-1.db.svc.cluster.local
cassandra-2.db.svc.cluster.local

db-read.prod.example.internal
db-write.prod.example.internal
```

### 25.1. Theo đúng connection endpoints

Liệt kê mọi nơi client/peer thật sự kết nối:

- Client seed/primary endpoint.
- Discovered member hostnames.
- Internal node DNS.
- Proxy/gateway endpoint.
- Disaster recovery region endpoints.

### 25.2. Đừng cấp certificate chứa cả mọi dịch vụ nếu không cần

Một certificate với hàng trăm SAN names dùng chung private key có blast radius lớn. Có thể dùng identity riêng từng node/gateway và quản trị rotation tự động.

### 25.3. IP churn trong Kubernetes

Pod IP dễ thay đổi; cấp certificate dựa vào Pod IP có thể tốn vận hành. Stateful DNS identity hoặc workload identity có thể phù hợp hơn, nếu driver có thể dùng DNS và verify được.

### 25.4. Tránh mismatch khi topology discovery

Nếu driver nhận `10.0.1.23` qua gossip nhưng certificate chỉ chứa `cassandra-1.db.svc.cluster.local`, cần xem advertised address/driver config hoặc IP SAN có chủ đích.

### 25.5. Region failover

DR endpoint như `db-dr.example.internal` phải được cover/trust đúng. Đừng chỉ kiểm primary region trong staging mà bỏ qua alternate region certificate chain.

---

## 26. Quản lý CA: root, intermediate và trust anchor

### 26.1. Root CA

Một root CA được đưa vào truststore có quyền tạo cơ sở tin cậy cho certificates mà client chấp nhận theo PKIX/name rules. Bảo vệ CA private key và giới hạn issuance policy là yêu cầu nền tảng.

### 26.2. Intermediate CA

Một tổ chức có thể dùng intermediate CAs cho từng environment/region/tenant và kiểm soát path length/name constraints khi thích hợp.

### 26.3. Không tự tin leaf nếu có thể thiết kế CA lifecycle rõ

Import trực tiếp server leaf certificate vào mọi application truststore có thể gây outage khi leaf đổi. Trust vào CA phù hợp thường cho phép leaf rotate mà client không cần deploy đồng loạt; vẫn phải xác minh SAN.

### 26.4. Trust scope

Một corporate root cấp cho nhiều internal services có thể mở rộng tập certificates có thể hợp lệ. Một private intermediate riêng cho database có thể giảm phạm vi tin cậy tùy path constraints và config.

### 26.5. Certificate authority cũng có thể bị chiếm

TLS không bảo vệ nếu CA issuing policy sai hoặc private key CA bị lộ. Cần quy trình revoke/replace, audit issuance, limited access và khôi phục khi CA compromise.

---

## 27. Luân chuyển certificate: tránh downtime hàng loạt

Một quy trình có thể theo các bước:

~~~mermaid
flowchart TD
    A["Inventory current certs/CA/clients"] --> B["Distribute trust for new CA"]
    B --> C["Verify dual trust period"]
    C --> D["Issue new server certificates with correct SAN"]
    D --> E["Canary node/connection handshake"]
    E --> F["Roll server certificates incrementally"]
    F --> G["Roll client identities if mTLS"]
    G --> H["Check all endpoints/failover"]
    H --> I["Retire old CA after safe overlap"]
~~~

### 27.1. Distribute trust trước khi thay issuer

Nếu server đã đổi sang CA mới nhưng clients chỉ trust CA cũ, handshake fail hàng loạt. Đảm bảo client trust new CA trước khi rollout leaf mới.

### 27.2. Rolling rollout

Một số nodes sẽ có certificate old issuer, một số new issuer trong transition. Client và node peers cần trust cả hai trong khoảng được phê duyệt.

### 27.3. SNI/SAN phải có trong certificate mới

Một leaf được ký hợp lệ nhưng thiếu SAN vẫn không dùng được. Kiểm node aliases, DR endpoints, Kubernetes DNS, IP SAN.

### 27.4. Tự động reload

Không phải mọi NoSQL engine hoặc Java driver tự reload certificate/truststore mỗi khi file đổi. Một số cần restart listener, recreate client/connection pool hoặc API reload. Kiểm **version-specific reload behavior** trước khi đặt rotation SLA.

### 27.5. Graceful draining

Khi đổi client/server TLS contexts, giữ request in-flight theo policy, thiết lập connections mới đã verify và drain connections cũ. Không kill đồng loạt cluster nodes khi replication/quorum đang mong manh.

### 27.6. Kết thúc transition

Chỉ remove old CA khi inventory xác nhận không còn clients/peers dùng old trust. Đừng để dual trust kéo dài vô hạn nếu CA cũ có vấn đề bảo mật.

---

## 28. Chứng chỉ sắp hết hạn: cảnh báo sớm ra sao?

Cần theo dõi:

- Leaf server certificate `notAfter`.
- Intermediate/root CA validity.
- Client certificates nếu dùng mTLS.
- Secrets/keystore version và reload status.
- Chứng chỉ trên mọi discovered node, không chỉ VIP.
- DR/standby endpoint certificates.
- Handshake success/failure rate theo nhóm phiên bản/zone.

### 28.1. Ví dụ ngưỡng vận hành

~~~text
T-30 days: warning if not scheduled
T-14 days: urgent investigation
T-7 days: incident-risk review
T-1 day: critical
Expired: stop unsafe connection fallback and remediate
~~~

Đây là ví dụ phụ thuộc chính sách cấp cert, automation và thời gian rollout. Với short-lived certificates (vài giờ/ngày), ngưỡng phải đặt theo **tỷ lệ vòng đời và automation SLA**, không sao chép 30 ngày.

### 28.2. Đừng chỉ nhìn cert trong keystore local

Server có thể đang trình một certificate cũ do listener chưa reload, proxy còn dùng config cũ hoặc DNS đưa client tới node khác. Test **actual network handshake** tới endpoint.

### 28.3. Clock skew

Một node có đồng hồ lệch có thể reject cert chưa đến `notBefore` hoặc đã vượt `notAfter`. Đồng bộ thời gian là yếu tố vận hành bảo mật, không phải lý do tắt certificate validity checks.

---

## 29. Test certificate với OpenSSL và keytool

Các lệnh sau là ví dụ quản trị, chạy trong môi trường và endpoint được phép kiểm tra.

### 29.1. Xem certificate đã có trên đĩa

~~~bash
openssl x509 \
  -in server.crt \
  -noout \
  -subject -issuer -dates \
  -ext subjectAltName
~~~

Dùng để kiểm SAN, issuer, hiệu lực. Không cần xuất private key.

### 29.2. Handshake tới endpoint với SNI và hostname check

~~~bash
openssl s_client \
  -connect db-prod.example.internal:443 \
  -servername db-prod.example.internal \
  -verify_hostname db-prod.example.internal \
  -verify_return_error \
  -CAfile trusted-ca.pem
~~~

Cổng 443 là ví dụ HTTPS endpoint; NoSQL native protocol có thể chạy cổng khác. Chỉ dùng đúng port TLS, nếu không sẽ gặp handshake errors dù certificate hoàn toàn ổn.

### 29.3. Đừng đọc mỗi dòng “CONNECTED”

TCP connection thành công không chứng minh certificate được trust. Xem verify result, chain, SAN và expected hostname. Nếu command cần CA/chain bổ sung, không bỏ qua validation để có output xanh.

### 29.4. Xem truststore Java

~~~bash
keytool -list -v \
  -keystore db-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh có thể yêu cầu mật khẩu tương tác; tránh đưa password vào command line hoặc CI logs.

### 29.5. So kết quả OpenSSL với Java

OpenSSL CLI và JDK/driver có thể dùng truststores, crypto providers và endpoint matching policies khác. “OpenSSL pass” chưa chứng minh Java service pass. Test bằng **chính driver và JDK production**.

### 29.6. Thu thập chứng chỉ qua proxy

Nếu endpoint nằm sau proxy hoặc service mesh, certificate bạn nhìn thấy có thể thuộc proxy chứ không phải node backend. Kiểm cả hop backend ở vị trí được phép.

---

## 30. JSSE debug: hữu ích nhưng có rủi ro

Trong môi trường kiểm thử có thể dùng debug options như:

~~~text
-Djavax.net.debug=ssl,handshake
```

Một số JDK có thêm các chế độ debug/certpath; cú pháp, lượng log và nội dung thay đổi theo version.

### 30.1. Vì sao hữu ích?

Có thể thấy:

- Negotiated TLS version/cipher.
- Certificate chain.
- Trust/handshake failure.
- SNI và các extension liên quan.
- Thời điểm handshake bị ngắt.

### 30.2. Vì sao không bật lâu trên production?

- Log rất lớn.
- Tăng CPU/I/O và chi phí lưu trữ.
- Có thể chứa thông tin cấu hình/định danh nhạy cảm.
- Dễ lộ secrets gián tiếp khi kết hợp nhiều log.
- Có thể tạo log storm lúc reconnect.

### 30.3. Bật theo thời gian ngắn và phạm vi nhỏ

Dùng một canary/test instance hoặc temporary diagnostic với quyền/phân quyền rõ; thu chứng cứ tối thiểu, redact trước khi chia sẻ.

---

## 31. Ma trận lỗi TLS thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách điều tra an toàn |
|---|---|---|
| `PKIX path building failed` | CA không được trust, thiếu intermediate, chain sai | Kiểm issuer, chain, truststore được dùng |
| `No subject alternative DNS name matching` | DNS endpoint không có trong SAN | Kiểm requested host và cert SAN |
| `No subject alternative IP address matching` | Kết nối IP nhưng thiếu IP SAN | Sửa endpoint/cert, không disable verify |
| `certificate expired` | Leaf/intermediate hết hạn | Xem `notAfter`, rotation/reload |
| `certificate not yet valid` | Clock skew hoặc cert hiệu lực tương lai | Kiểm NTP/time/issuance |
| `unknown_ca` | Peer không trust issuer | Xem CA distribution và intermediate |
| `bad_certificate` | Client cert không phù hợp hoặc bị từ chối | Kiểm mTLS client cert/EKU/policy |
| `handshake_failure` | TLS version/cipher/client auth mismatch | Kiểm policies và server/client support |
| `protocol_version` | Version negotiation không tương thích | Nâng JDK/driver hoặc config đúng |
| `unrecognized_name` / wrong cert | SNI mismatch trên proxy | Kiểm SNI và virtual host mapping |
| `connection reset` | Network, proxy, TLS policy, timeout | Correlate both endpoints/network logs |
| `wrong version number` | Gửi TLS tới plaintext port hoặc ngược lại | Kiểm port/protocol và TLS listener |
| `unable to find valid certification path` | Truststore sai path/CA hoặc chain | Kiểm file path, permissions, content |
| Works via seed, fails after discovery | Per-node SAN/IP topology mismatch | Kiểm advertised/discovered addresses |
| Works until failover | Standby node/proxy có cert khác | Test mọi failover targets |
| Only one JVM fails | JDK/truststore/provider khác | So runtime/flags/driver |
| Only one region fails | DR CA/SAN/cert rollout khác | Kiểm trust/region routes |
| mTLS works but user denied | Database ACL/authz sai | Kiểm role/permission, không sửa TLS |
| TLS works but credentials fail | Database authentication khác | Kiểm credential rotation/auth mechanism |
| Inter-node connections fail | Node CA/usage/identity mismatch | Kiểm server-to-server TLS riêng |
| Errors after rotation | Listener/client chưa reload, trust overlap thiếu | Kiểm rollout sequence và live chain |
| Errors during clock incident | NotBefore/NotAfter affected | Đồng bộ clock, xác minh thời gian thực |
| Encrypted connection to wrong cluster | Host verification tắt/routing sai | Khôi phục verify, audit dữ liệu gửi sai |

**Không dùng lỗi “certificate invalid” làm lý do mặc định để bỏ kiểm tra.** Đây thường chính là tín hiệu TLS đang bảo vệ bạn khỏi kết nối sai.

---

## 32. Bẫy: `tls=true` không nhất thiết đồng nghĩa verify đúng

Một số ứng dụng dùng các cờ:

~~~text
TLS enabled = true
Trust all certificates = true
Hostname verification = false
```

Khi đó **mã hóa vẫn có thể hoạt động**, nhưng danh tính peer không được xác thực đủ mạnh.

### 32.1. Kiểm cấu hình theo cặp

- TLS enabled?
- Chain trust validation enabled?
- Hostname/IP identity check enabled?
- Expected host là gì?
- Server certificate SAN là gì?
- Client cert required?
- Authentication/authorization riêng đã bật?

### 32.2. Không che lỗi trên mọi môi trường

Một dev environment dùng self-signed certificate vẫn có thể **tin đúng test CA** thay vì trust-all. Thực hành này giúp phát hiện SAN/rotation issues trước production.

### 32.3. Tự ký không tự đồng nghĩa “không bảo mật”

Một self-signed certificate có thể được cài làm trust anchor **theo chính sách cụ thể** và được kiểm SAN tương ứng. Rủi ro đến từ việc tin arbitrary certificate hoặc bỏ qua identity, không chỉ nhãn self-signed. Nhưng quản lý trust/rotation self-signed thường đòi công sức hơn CA-backed issuance.

### 32.4. Không cho fallback plaintext tự động

Nếu TLS handshake fail, application nên fail closed đối với kênh truyền bắt buộc TLS. Fallback plaintext để “không mất availability” có thể biến một lỗi chứng chỉ thành rò dữ liệu.

---

## 33. Bảo vệ database credentials ngoài TLS

TLS giữ bí mật credentials trong đường truyền, nhưng không bảo vệ nếu secrets bị lộ ở nơi khác.

### 33.1. Secrets manager

- Lấy credentials từ secret provider/identity management.
- Không hardcode password trong source code.
- Không commit `.env`, keystore private key hoặc token vào Git.
- Đặt rotation policy và audit.

### 33.2. Least privilege

Một account chỉ đọc analytics không nên có quyền xóa collection. TLS xác thực peer không sửa được lỗi phân quyền.

### 33.3. Không log connection string đầy đủ

MongoDB URI có thể chứa username/password; log lỗi driver phải được redact. Không in raw password/token ở log khi debug TLS.

### 33.4. Tách staging/production

Dùng endpoint, CA, credentials, role policies riêng để giảm rủi ro app staging ghi dữ liệu production. Hostname verification giúp nhưng không thay authorization và environment isolation.

### 33.5. Kiểm TLS trước credentials

Không gửi secrets qua connection chưa verify. Một số client có thể cố fallback/retry sang endpoint khác; kiểm policy thực thi và test negative scenarios.

---

## 34. Khi nào certificate validation cần kiểm revocation?

Một certificate có thể chưa hết hạn nhưng private key đã bị đánh cắp hoặc quyền phục vụ đã bị thu hồi.

### 34.1. CRL và OCSP

Certificate Revocation List (CRL) và Online Certificate Status Protocol (OCSP) là các cơ chế liên quan tới trạng thái thu hồi. Hỗ trợ/hành vi của JDK, TLS provider và driver thay đổi theo cấu hình.

### 34.2. Không giả định bật mặc định

Một client `PKIX` chain-valid không nhất thiết chủ động gọi OCSP/CRL và fail closed khi không truy cập được responder. Cần xác minh revocation policy thực tế theo threat model/compliance.

### 34.3. Short-lived certificates

Certificate sống ngắn có thể giảm thời gian lộ diện khi không có revocation hiệu quả; nhưng yêu cầu automation rotation tốt và xử lý clock/cert issuance outage.

### 34.4. Compromised server key

Thay leaf cert bằng key mới, revoke identity/key cũ, cập nhật trust/issuer nếu cần và điều tra phạm vi traffic đã bị ảnh hưởng. Không chỉ restart server.

### 34.5. Revocation không thay authorization

Một node đã mất quyền cluster membership có thể cần cơ chế membership/authz riêng. Một certificate còn hạn chưa chắc node được phép tham gia cluster hiện tại.

---

## 35. TLS có gây tăng latency không?

TLS có overhead:

- Handshake: tính toán mật mã, round trips.
- Certificate chain verification.
- Encryption/decryption CPU.
- Record framing và buffers.
- Session resumption/caching.
- Certificate rotation reconnects.

### 35.1. Chỉ số quan trọng là handshake rate

Nếu ứng dụng tạo `MongoClient`/`RedisClient` mới cho mỗi request, nó có thể gây rất nhiều TLS handshakes và kết nối TCP. Dùng client/connection pooling đúng lifecycle giúp giảm overhead hơn việc giảm an toàn TLS.

### 35.2. TLS 1.3 và session resumption

TLS 1.3 có thiết kế handshake hiệu quả hơn trong nhiều tình huống, nhưng real latency phụ thuộc network, CPU, resumption policy và driver. Không lấy một con số “TLS tốn X ms” làm định luật.

### 35.3. Reconnect storm

Sau certificate rotation/failover, hàng nghìn clients có thể reconnect cùng lúc. Đặt backoff/jitter và connection pool limits để tránh overload server/CA infrastructure.

### 35.4. Chỉ đo TLS overhead đúng scope

~~~text
DNS + TCP connect
TLS handshake
DB authentication
Connection acquisition from pool
Query execution
Network response
Deserialization
```

Nếu query p99 tăng do compaction/tombstones, tắt TLS sẽ không sửa được nguyên nhân.

### 35.5. Không “tối ưu” bằng cách bỏ xác thực server

Tắt hostname verification có thể giảm một lượng nhỏ work so với TLS handshake nhưng làm mất bảo vệ cốt lõi. Tối ưu bằng reuse, resumption, appropriate ciphers/hardware, không hạ security contract.

---

## 36. Theo dõi TLS trong production

Một dashboard hữu ích:

| Nhóm | Metric/biến quan sát | Ý nghĩa |
|---|---|---|
| Connection | Active TLS connections, new connections/s | Phát hiện churn, reconnect storm |
| Handshake | Success/failure counts | Nhận diện cert/config errors |
| Handshake latency | p50/p95/p99 khi có instrumentation | Đo setup overhead |
| Cert expiry | Days/seconds to expiry | Dự báo rotation |
| Cert version | Issuer/key ID/serial theo log an toàn | Kiểm rollout |
| Peer identity | Hostname mismatch/invalid SAN | Chặn sai routing |
| Trust chain | Unknown CA/PKIX failures | Truststore/CA migration |
| TLS version | TLS 1.2/1.3 distribution | Theo dõi downgrade/config |
| mTLS | Client cert rejection | Phát hiện auth issues |
| Driver pool | Acquisition wait/size | Tách handshake vs pool |
| Database | Query p99, errors, retries | Đo user impact |
| Inter-node | Node link handshake failures | Cluster health |
| Security | Plaintext accepted connection count | Kiểm policy |
| Deploy | Cert reload success, CA rollout phase | Trace incident cause |

### 36.1. Đừng đưa certificate identity thành label không giới hạn

Serial numbers theo từng lần reconnect/leaf rotation có thể tạo high cardinality. Dùng bounded labels như service, role, environment và failure type; chi tiết serial/subject qua secure logs.

### 36.2. Đo ở client và server

Client có thể báo `PKIX` trong khi server chỉ thấy `handshake aborted`. Hai phía cần correlate timestamps, endpoint, connection IDs theo chính sách không làm lộ data.

### 36.3. Không để monitor tự tạo load quá lớn

Một TLS probe từ mọi app instance mỗi giây vào mọi node có thể tạo hàng nghìn handshakes không cần thiết. Giới hạn probe rate và tận dụng exporter/cert inventory.

---

## 37. Kiểm thử tích hợp: xác minh TLS bằng lỗi cố ý

Một test chỉ xác nhận kết nối TLS thành công **chưa đủ**. Cần test client **từ chối server sai**.

### 37.1. Valid certificate

~~~text
Client connects: db.test.internal
SAN: DNS:db.test.internal
Trust: test CA
Expected: handshake success
```

### 37.2. Wrong hostname

~~~text
Client connects: db.test.internal
SAN: DNS:other.test.internal
Trust: same test CA
Expected: handshake reject
```

Nếu case này thành công, có thể client đã tắt hostname verification.

### 37.3. Untrusted CA

~~~text
Client trusts: CA-A
Server certificate issued by: CA-B
Expected: handshake reject
```

### 37.4. Expired certificate

Client phải từ chối leaf hết hạn theo validity policy. Sử dụng test CA và certificate fixtures, không hạ đồng hồ production để thử.

### 37.5. mTLS client rejected

Server yêu cầu client certificate; client thiếu hoặc chứng chỉ không được trust. Expected: TLS handshake hoặc auth stage từ chối theo protocol.

### 37.6. Discovery node mismatch

Kết nối seed thành công nhưng discovered node trả cert thiếu SAN. Expected: không bypass; topology/config được sửa.

### 37.7. Không gửi database credentials trước verification

Test fixture có thể ghi nhận một server giả không nhận được application authentication payload khi handshake bị reject; đây là oracle bảo mật quan trọng.

---

## 38. Ma trận 32 kịch bản TLS và danh tính

| ID | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| T01 | Chain hợp lệ, DNS SAN đúng | TLS thành công |
| T02 | CA untrusted | Từ chối |
| T03 | SAN khác requested DNS | Từ chối |
| T04 | Kết nối bằng IP nhưng không có IP SAN | Từ chối |
| T05 | Certificate hết hạn | Từ chối |
| T06 | `notBefore` trong tương lai | Từ chối |
| T07 | Thiếu intermediate chain | Từ chối nếu không xây được path hợp lệ |
| T08 | Certificate không phù hợp serverAuth usage | Từ chối theo policy |
| T09 | Wrong SNI, proxy trả cert khác | Từ chối/mapping đúng |
| T10 | TLS version không giao nhau | Handshake fail, không plaintext fallback |
| T11 | Cipher suites không tương thích | Handshake fail |
| T12 | Client có mTLS cert hợp lệ | Server chấp nhận identity, authz riêng |
| T13 | Client thiếu cert khi server yêu cầu | Từ chối |
| T14 | Client cert bị thu hồi theo policy | Từ chối khi revocation enforcement được cấu hình |
| T15 | Driver seed đúng nhưng discovered node sai SAN | Từ chối node sai, alert |
| T16 | Redis Cluster redirect tới node sai SAN | Từ chối redirect peer sai |
| T17 | MongoDB failover tới node cert hết hạn | Fail an toàn, không disable verify |
| T18 | Cassandra client TLS bật, inter-node TLS tắt | Phát hiện bằng kiểm config/probes |
| T19 | Load balancer terminate TLS, backend plaintext | Phát hiện hop policy violation |
| T20 | Service mesh bật mTLS nhưng app tới sidecar plaintext | Phân tích đúng trust boundary |
| T21 | Rotation trust new CA trước đổi cert | Không downtime |
| T22 | Đổi cert trước cập nhật truststore | Handshake fail, rollback có kiểm soát |
| T23 | Listener không reload certificate mới | Inventory và live probe phát hiện |
| T24 | JVM clocks lệch | Invalid validity được phát hiện |
| T25 | Private key cũ bị lộ | Rotation/revocation/runbook |
| T26 | Test CA vô tình được thêm production trust | Policy test phát hiện |
| T27 | HTTP/plaintext endpoint được expose | Network scan/config audit phát hiện |
| T28 | Client tự reconnect liên tục | Bounded backoff/pool |
| T29 | TLS thành công nhưng database ACL deny | Phân biệt authz với TLS |
| T30 | Wrong production/staging DNS route | SAN/authz kiểm và chặn |
| T31 | Disaster recovery region certificate chain khác | Preflight trust/host validation |
| T32 | Managed endpoint đổi leaf certificate | Trust/rotation policy không pin leaf sai |

Tất cả tests chủ động gây lỗi certificate/failover phải chạy trong **staging/disposable environment được phê duyệt** hoặc theo quy trình production-safe đã định nghĩa.

---

## 39. Runbook khi TLS handshake fail sau deploy

### Bước 1 — Xác định đối tượng

- Java service nào, database nào?
- Endpoint DNS/IP nào và port nào?
- App-to-node hay node-to-node?
- Có proxy/service mesh không?
- Lỗi xảy ra với mọi nodes hay chỉ sau failover?
- Deployment JDK/driver/CA/cert thay đổi gì?

### Bước 2 — Phân loại lỗi

- `PKIX`/unknown CA.
- Expired/not-yet-valid.
- SAN/hostname/IP mismatch.
- TLS version/cipher.
- Client certificate.
- Wrong port/protocol.
- DNS/SNI/route.

### Bước 3 — Kiểm endpoint trực tiếp

Dùng approved TLS probe/OpenSSL với expected DNS hostname và đúng port. Xem live certificate, chain, SAN, issuer, validity. Kiểm proxy được cấp đúng certificate.

### Bước 4 — Kiểm client runtime

- Java version.
- SSL provider.
- Truststore path/type.
- File permissions.
- Driver TLS settings.
- Endpoint identification enabled.
- SNI behavior.
- Advertised/discovered node addresses.

### Bước 5 — Kiểm khác biệt giữa nodes

Đặc biệt trong cluster: một node có cert cũ, IP SAN thiếu hoặc truststore chưa rotate. Đừng kết luận lỗi đã hết chỉ vì một connection tới seed thành công.

### Bước 6 — Khôi phục an toàn

- Sửa DNS/advertised host.
- Deploy đúng CA chain.
- Renew server/client cert.
- Reconfigure/restart/reload listener theo engine.
- Roll back cert change bằng một phiên bản **còn hợp lệ và được trust**, nếu được phép.
- Chỉ mở traffic sau handshake + identity tests.

### Bước 7 — Không dùng workaround nguy hiểm

Không tắt hostname validation, không trust-all, không hạ TLS versions vô điều kiện và không bật plaintext cổng phụ để chữa tạm.

### Bước 8 — Đối soát

Kiểm liệu có requests đã gửi tới nhầm cluster không, secrets có lộ không, audit/tracing có biểu hiện unusual endpoint hay không. Nếu đã tắt verify trước đó, đây có thể là security incident.

---

## 40. Runbook certificate rotation không gián đoạn

### Chuẩn bị

1. Inventory ứng dụng, batch jobs, CDC agents, node peers.
2. Xác định CA cũ/mới, SAN, EKU, private key ownership.
3. Kiểm thời hạn cert và những legacy clients chưa hỗ trợ policy mới.
4. Cấp cert test và kiểm trust/hostname.
5. Xác định thời gian dual trust.
6. Có rollback plan và failover test.

### Thực thi

7. Phát CA mới đến truststores trước.
8. Xác minh clients/nodes trust được old và new CA.
9. Triển khai leaf cert mới trên một canary node.
10. Kiểm app-to-node và node-to-node handshake.
11. Rolling rollout qua nodes/zones.
12. Cập nhật mTLS client identities khi phù hợp.
13. Kiểm discovery, redirects và failover routes.
14. Đóng/dần thay connections cũ theo plan nếu reload không tự động.

### Hoàn tất

15. Đo handshake success/failure, query p99, reconnect rate.
16. Kiểm tất cả advertised/discovered endpoints.
17. Kiểm DR region và backup/CDC agents.
18. Chỉ retire old CA khi không còn peer phụ thuộc nó.
19. Thu hồi/tiêu hủy private keys cũ theo policy.
20. Cập nhật certificate inventory và lịch rotation tiếp theo.

---

## 41. Bài tập 1 — Hostname mismatch trong NoSQL cluster

Một ứng dụng Java dùng MongoDB:

~~~text
URI seed: mongodb://db.prod.internal:27017/?tls=true
Actual replica nodes:
  10.0.1.10
  10.0.1.11
  10.0.1.12

Certificate on each node:
  SAN DNS:db.prod.internal
  No IP SAN
```

Hãy trả lời:

1. Vì sao seed connection có thể pass nhưng kết nối tới nodes khác fail?
2. Vì sao chỉ trust certificate issuer không đủ?
3. Chọn sửa advertised hosts sang DNS hay cấp IP SAN trong bối cảnh nào?
4. Nếu tắt hostname verification, rủi ro gì?
5. Khi thay replica, cần test những endpoints nào?
6. Thiết kế một test tự động phát hiện node có cert sai.

---

## 42. Bài tập 2 — Phân biệt TLS, mTLS và database auth

Cho sơ đồ:

~~~text
App A --TLS--> Proxy P --TLS--> Database D
App B --mTLS--> Proxy P
```

Yêu cầu:

1. App A xác thực peer nào?
2. App B được xác thực ở tầng nào?
3. Database D có chắc biết identity của App B không?
4. Nếu P dùng cùng một DB account cho mọi apps, rủi ro authorization gì?
5. TLS hop P→D cần CA/SAN riêng không?
6. Nếu đoạn P→D là plaintext, có thể vẫn gọi end-to-end encrypted không?
7. Biện pháp nào giúp DB phân quyền theo application identity?

---

## 43. Bài tập 3 — Chẩn đoán lỗi Java SSLHandshakeException

Một Java service báo:

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
```

Những dữ kiện:

~~~text
Server leaf SAN đúng.
Server cert issued by new intermediate CA.
Client truststore chỉ chứa old root CA.
Proxy đã rollout certificate mới.
```

Hãy nêu:

1. Lỗi chain/trust hay lỗi hostname?
2. Có nên disable certificate validation không?
3. Phải thêm CA nào vào truststore theo issuance policy?
4. Làm sao kiểm intermediate chain của live endpoint?
5. Nếu nhiều JVM không reload truststore, rollout thế nào?
6. Thiết kế canary test sau khi đổi trust.
7. Vì sao cần dual trust period trước khi đổi certificate issuer?

---

## 44. Bài tập 4 — mTLS và private key bị lộ

Một batch job dùng chung client certificate với 30 ứng dụng. Private key của một container image bị lộ.

Hãy phân tích:

1. Có thể truy vết chính xác ứng dụng gây connection được không?
2. Cần revoke/rotate certificate/key thế nào?
3. Vì sao chỉ thay keystore password không đủ?
4. Client identities nên cấp theo đơn vị nào?
5. Server authorization mapping cần dựa vào cert identity ra sao?
6. Nếu client certificate không có EKU `clientAuth` phù hợp, điều gì xảy ra?
7. Nguy cơ nếu server trust cả một CA quá rộng và cho mọi cert cùng role?
8. Thiết kế quy trình không downtime cho 30 apps.

---

## 45. Bài tập 5 — Tạo cấu hình Java an toàn

Dùng `SSLContext` và NoSQL driver tùy chọn:

1. Tạo truststore PKCS#12 chứa private CA.
2. Mở TLS.
3. Bật endpoint identification.
4. Kiểm chứng chỉ đúng DNS SAN.
5. Thử certificate do CA lạ cấp.
6. Thử cert đúng CA nhưng sai hostname.
7. Nếu dùng mTLS, thêm KeyManagerFactory.
8. Xác định nơi lưu secrets và private key.
9. Viết unit/integration tests cho failure.
10. Ghi lý do không dùng trust-all manager.

Không yêu cầu tạo CA private key trên production hoặc lưu private key trong source repository.

---

## 46. Bài tập 6 — Certificate rotation cho cụm 5 node

Cụm Cassandra 5 nodes chạy 2 DC:

~~~text
DC-A: A1, A2, A3
DC-B: B1, B2
Clients: Java API, CDC, Admin CLI
Current CA: CA-old
New CA: CA-new
```

Yêu cầu lập kế hoạch:

- Danh sách mọi endpoints và SAN.
- Phân biệt client-to-node vs node-to-node.
- Trust distribution trước cert rollout.
- Canary node.
- Rolling order không phá quorum/availability.
- Failover test.
- Client mTLS rotation khi áp dụng.
- Certificate reload/restart semantics.
- Alert/cutover gates.
- Retire old CA.
- Rollback khi một node không bắt tay TLS.

---

## 47. Bài tập 7 — Đo TLS overhead đúng cách

Một benchmark cho thấy:

~~~text
Without connection reuse:
  2.000 TCP/TLS handshakes/s
  DB request p99=180 ms

With pooled connections:
  30 handshakes/s
  DB request p99=35 ms
```

1. Có đủ để nói TLS encryption chậm 145 ms không?
2. Những phần nào thuộc DNS/TCP/TLS/auth/pool wait?
3. Vì sao tạo client mới mỗi HTTP request nguy hiểm?
4. TLS session resumption giúp gì?
5. Mất database node gây reconnect storm thế nào?
6. Khi benchmark, phải giữ query/consistency/traffic tương đương?
7. Những metrics nên đo để chứng minh bottleneck?

---

## 48. Bài tập 8 — Soạn Security Acceptance Checklist

Viết một checklist tối thiểu 20 điều cho service Java → NoSQL bao gồm:

- TLS version/cipher policy.
- Chain trust verification.
- DNS/IP SAN verification.
- SNI/discovery/redirect.
- Keystore/truststore permissions.
- mTLS usage.
- Database ACL.
- Inter-node TLS.
- Load balancer/backend hops.
- Certificate/CA rotation.
- Automated expiry monitoring.
- Revocation strategy.
- Fail closed behavior.
- Negative integration tests.
- Secrets masking.
- Failover/DR region.
- Incident runbook.
- Tracing/metrics.
- Compliance/data residency.
- Rollback không hạ security.

---

## 49. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “`tls=true` nghĩa server chắc chắn đúng.” | Cần cả chain và SAN identity check |
| “Certificate do corporate CA ký thì bất kỳ service nào cũng hợp lệ.” | CA trust còn phải kết hợp expected hostname/usage |
| “Common Name đủ để xác minh DNS.” | SAN là nguồn identity hiện đại |
| “Kết nối IP có thể so DNS SAN tùy ý.” | IP matching cần IP SAN theo policy |
| “Kết nối seed pass thì mọi replicas pass.” | Discovery có thể dùng node addresses khác |
| “DNS trả IP đúng thì không cần TLS name verification.” | DNS routing không chứng minh peer identity |
| “SNI là xác thực người dùng.” | SNI hỗ trợ server chọn certificate; không thay auth |
| “Mã hóa TLS luôn có nếu dùng private network.” | Cần cấu hình/kiểm thực |
| “TLS tại gateway nghĩa backend TLS.” | Mỗi hop có trust boundary riêng |
| “Service mesh mTLS thay hết database auth.” | Mesh identity không tự cấp quyền query |
| “mTLS tự phân quyền theo tenant.” | Cần DB/application authorization |
| “Bật inter-node TLS tự bật client TLS.” | Có thể là hai cấu hình |
| “Client TLS tự mã hóa replication.” | Phải kiểm node-to-node riêng |
| “Truststore là nơi lưu client private key.” | Identity keystore và truststore có vai trò khác |
| “Trust-all chỉ ảnh hưởng performance.” | Nó phá server certificate verification |
| “Tắt hostname check chỉ bỏ một warning.” | Có thể cho client gửi dữ liệu tới sai cluster |
| “Self-signed luôn không dùng được.” | Có thể trust có chủ đích, nhưng phải quản lý nghiêm |
| “Import leaf cert một lần dùng mãi.” | Rotation có thể break pinning |
| “Cert còn hạn thì không cần revocation policy.” | Key có thể đã lộ |
| “Mọi Java driver dùng default truststore.” | Có thể dùng custom provider/SSL context |
| “Mọi driver tự kiểm hostname như HTTPS.” | Cần xem/config đúng version |
| “`SSLContext` tự bật hostname verification mọi nơi.” | Endpoint checking có thể cần cấu hình riêng |
| “TLS 1.3 nghĩa không cần kiểm identity.” | TLS version không thay PKIX/SAN verification |
| “0-RTT luôn an toàn cho database write.” | Early data có replay considerations |
| “Certificate rotation là thay file trên disk.” | Listener/driver có thể cần reload/reconnect |
| “Đổi CA trước rồi clients tự thích nghi.” | Cần trust overlap và rollout plan |
| “Clock lệch thì nên bỏ validity check.” | Sửa time sync/issuance |
| “Handshake fail thì fallback plaintext.” | Vi phạm security policy |
| “OpenSSL `CONNECTED` nghĩa xác thực thành công.” | Phải kiểm verify result và hostname |
| “Thêm nhiều connection làm TLS rẻ hơn.” | Connection churn thường tăng handshake |
| “TLS là lý do duy nhất của query p99.” | Cần đo compaction/network/pool/retries |
| “Password được mã hóa nên không cần least privilege.” | TLS không thay authorization |
| “Managed NoSQL không cần kiểm HTTPS identity.” | SDK vẫn phải xác thực endpoint |
| “Cert rotation có thể làm mọi nodes một lúc.” | Cần cân nhắc quorum/availability |

---

## 50. Checklist triển khai và vận hành TLS NoSQL

- [ ] Đã inventory mọi data paths: app, node, admin, CDC, backup.
- [ ] Mọi đường truyền nhạy cảm có TLS theo chính sách.
- [ ] Chặn plaintext fallback/downgrade.
- [ ] TLS versions và cipher suites đáp ứng chuẩn tổ chức.
- [ ] Server certificate có SAN đúng với các DNS/IP endpoints.
- [ ] Client thực hiện chain validation và hostname/IP verification.
- [ ] Đã có negative test cho trusted CA nhưng sai hostname.
- [ ] Đã có negative test cho untrusted CA/expired cert.
- [ ] Client dùng đúng SNI với gateway/proxy theo thiết kế.
- [ ] Discovery/redirect nodes được xác thực từng endpoint.
- [ ] Database credentials truyền sau TLS identity verification.
- [ ] mTLS client identity được cấp riêng khi cần.
- [ ] DB roles/ACL áp dụng least privilege.
- [ ] Keystore private keys được bảo vệ, không lưu trong image/Git.
- [ ] Truststore chỉ chứa trust anchors được phê duyệt.
- [ ] Không sử dụng trust-all hoặc `invalidHostNameAllowed(true)` production.
- [ ] Node-to-node TLS được cấu hình/kiểm tra độc lập.
- [ ] Proxy termination/back-end hop có policy rõ.
- [ ] DR/standby endpoints cũng có cert hợp lệ.
- [ ] Certificate inventory bao gồm leaf/intermediate/root và client certs.
- [ ] Certificate expiry alerts phù hợp lifecycle.
- [ ] Root/intermediate CA rotation có overlap protocol.
- [ ] Client/server reload behavior được xác minh.
- [ ] Reconnect storms có backoff/jitter/pooling.
- [ ] Revocation/compromised key procedure được định nghĩa.
- [ ] Clock synchronization có monitoring.
- [ ] Logs/diagnostics không lộ passwords/private keys.
- [ ] TLS handshake metrics phân biệt với database latency.
- [ ] Incident runbook ưu tiên sửa cert/trust/DNS, không disable verify.
- [ ] Staging test gồm failover, rotation, wrong SAN, wrong CA.
- [ ] Production rollback không hạ security contract.
- [ ] Security review được cập nhật sau khi đổi driver/JDK/topology.

---

## 51. Tổng kết

**TLS trong NoSQL không chỉ là công tắc mã hóa.** Nó là một hợp đồng xác thực và bảo vệ các connections mà dữ liệu đi qua. Một kết nối TLS chỉ đáng tin khi ứng dụng xác minh được **đúng peer** trong đúng trust boundary.

Những điểm cốt lõi:

1. **Mã hóa, certificate trust, hostname verification và authorization là bốn lớp riêng**; thiếu một lớp có thể tạo lỗ hổng.
2. **Server identity cần khớp SAN** với hostname/IP mà client thực sự dùng, kể cả sau topology discovery và failover.
3. **Không bỏ kiểm chứng danh tính** chỉ vì certificate do CA tin cậy ký hoặc vì ứng dụng chạy trong mạng nội bộ.
4. **mTLS xác thực client ở tầng TLS**, nhưng database role/tenant authorization vẫn cần kiểm soát riêng.
5. **App-to-node và node-to-node TLS phải được đánh giá độc lập**; proxy/service mesh thêm trust boundaries thay vì tự bảo đảm end-to-end.
6. **Truststore/keystore có vai trò khác nhau**; private key cần bảo vệ, CA cần chính sách phát hành và rotation.
7. **JDK/driver behavior khác nhau**; `SSLContext` không tự chứng minh MongoDB/Cassandra/Redis driver đã bật endpoint identification.
8. **Certificate rotation cần trust overlap, canary và test failover**, không chỉ chép file cert mới.
9. **TLS handshake failure phải được chẩn đoán và sửa nguyên nhân**; không trust-all hoặc tự fallback plaintext.
10. **Đo connection churn và handshake rate cùng query p99**, không dùng security disable như phương pháp performance tuning.

**Câu cần nhớ: “Đường truyền đã được mã hóa chưa đủ; ứng dụng còn phải biết mình đang mã hóa dữ liệu để gửi cho đúng máy chủ nào. Trong NoSQL phân tán, điều đó phải đúng ở mọi kết nối Java–node, node–node, proxy và cả khi cluster thay đổi topology.”**
