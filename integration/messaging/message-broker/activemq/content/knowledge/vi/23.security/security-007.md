# Quản lý bí mật, đổi chứng thư và luân chuyển mật khẩu trong ActiveMQ

> **Chương:** Bảo mật  
> **Phạm vi:** ActiveMQ Classic và ActiveMQ Artemis phục vụ producer/consumer Java/JMS. Bài tập trung vào **bí mật đăng nhập**, **keystore/truststore**, **gia hạn hoặc thay certificate TLS**, **thay CA tin cậy**, **rotation không gián đoạn** và **chứng minh credential cũ đã bị thu hồi**. Ví dụ XML dành cho broker được chỉ định riêng; không sao chép schema của Classic sang Artemis hoặc ngược lại.

## 1. Một connection JMS có nhiều lớp bí mật

Ứng dụng Billing dùng user `billing-producer` để gửi vào queue `billing.commands` qua TLS endpoint `broker.messaging.internal.example:61617`. Đường gửi liên quan ít nhất ba loại thông tin:

1. **JMS username/password**: broker kiểm tra danh tính ứng dụng qua JAAS, user store, LDAP hoặc security plugin được cấu hình.
2. **TLS private key + certificate chain**: broker chứng minh danh tính máy chủ; client có private key/certificate riêng nếu bật **mutual TLS (mTLS)**.
3. **Trust anchors**: CA/certificate mà client tin để xác thực server, và CA/certificate mà broker tin để xác thực client nếu dùng mTLS.

Thay đổi một lớp **không tự cập nhật** hai lớp còn lại.

| Thay đổi | Cần thay ở đâu? | Rủi ro đặc thù |
|---|---|---|
| Đổi mật khẩu đăng nhập JMS | User backend broker và cấu hình producer/consumer | Client reconnect với password cũ → login fail |
| Đổi password keystore PKCS#12 | Store file và password mà process dùng mở store | Process không mở được private key dù certificate còn hạn |
| Gia hạn server cert **cùng CA** | Broker keystore/TLS listener, hoặc TLS-terminating proxy | SAN sai, thiếu intermediate, cert mới chưa được listener đọc |
| **Chuyển CA** ký server cert | Client truststore **trước**, server cert **sau**, cleanup cuối | Client không tin server mới nếu đổi thứ tự |
| Đổi client cert mTLS | Broker truststore/identity mapping + client keystore | TLS handshake có thể thành công nhưng client thiếu role |
| Thu hồi khẩn cấp secret lộ | User backend, connection đang sống, deployment secrets/audit | Đổi password có thể **không** cắt session đang đăng nhập |

**Điều kiện hoàn tất rotation** không phải “Secret đã cập nhật”, mà là: **kết nối mới bằng thông tin mới thành công**, quyền send/consume đúng, **kết nối mới bằng credential cũ thất bại** sau khi thu hồi, và luồng nghiệp vụ không bị mất tác động do reconnect.

### 1.1. Bốn điểm kiểm tra bảo mật độc lập

~~~mermaid
flowchart LR
    P["Producer / Consumer"] -->|TLS handshake| T["Broker TLS endpoint"]
    T -->|JMS login| A["JAAS / User store"]
    A -->|Check roles| Z["Authorization policy"]
    Z -->|send / consume| Q["Queue / Topic"]
~~~

- **TLS server authentication**: client xác minh chain, thời hạn và hostname trong **Subject Alternative Name (SAN)**.
- **JMS authentication**: broker xác minh principal/password hoặc cách nhận diện khác.
- **Authorization**: principal/roles có quyền gửi, nhận, duyệt hoặc quản trị destination?
- **mTLS client authentication**: broker kiểm tra certificate client, nhưng **chứng thư hợp lệ chưa tự cấp quyền JMS**; phải có identity mapping/role nếu dùng cert-based login.

Có thể gặp **TLS thành công nhưng `JMSSecurityException`**, hoặc **JMS login thành công nhưng send bị từ chối**. Chẩn đoán phải đi từng lớp thay vì nới lỏng TLS hay ACL.

## 2. Inventory secret trước khi rotate

Trước bất kỳ thay đổi nào, lập danh mục:

| Trường inventory | Thông tin cần có |
|---|---|
| Owner | Nhóm sở hữu secret/certificate, kênh liên hệ sự cố |
| Consumer | Broker node, Spring Boot app, batch worker, connector, bridge, management agent nào sử dụng? |
| Nguồn cấp | Vault/cloud secret manager, Kubernetes Secret, filesystem hoặc directory backend |
| Runtime path | File mount / biến cấu hình / connector alias / Java ConnectionFactory |
| Secret version | Version đang hoạt động; ngày phát hành, hết hạn, cần thu hồi |
| Quyền | JMS roles/destinations; quyền file private key; CA được tin |
| Rotation mechanism | Broker reload/restart, app restart/rebuild pool, HA failover |
| Fault domain | Các broker node, load balancer, region, standby, DR environment |
| Bằng chứng | Fingerprint/serial cert, auth log, fresh connection test, audit timestamp |

Không được **đoán** backend user từ việc thấy file tên `artemis-users.properties` hoặc `users.properties`. Broker có thể dùng LDAP, JAAS khác hoặc custom plugin; phải xác nhận backend **đang có hiệu lực**.

### 2.1. Cất giữ và phát hành secret

Nên lưu nguồn sự thật trong secret manager/PKI, phân quyền cấp phát tối thiểu. Trong runtime có thể dùng file mount chỉ đọc hoặc secret integration phù hợp.

~~~text
/run/secrets/messaging/
    server-keystore.p12        # Private key broker
    server-keystore.pass       # Mật khẩu mở keystore
    server-truststore.p12      # CA/cert mà broker tin (mTLS)
    server-truststore.pass
    app-keystore.p12           # Private key riêng client mTLS
    app-keystore.pass
    app-truststore.p12         # CA xác minh broker
    app-truststore.pass
    jms-username
    jms-password
~~~

Đây là **cấu trúc ví dụ**, không phải yêu cầu Artemis/Classic tự tạo. Không mount **server-keystore.p12** vào producer/consumer: private key broker không được chia sẻ với client. Mỗi service/instance mTLS có thể có certificate/key riêng để thu hồi độc lập.

**Không đưa bí mật vào** Git, Dockerfile layer, JAR, build artifact, ticket, dashboard, CI log, command line hoặc tracing baggage. Password đã “mask” trong một file cấu hình có thể vẫn giải mã được khi người tấn công lấy cả cấu hình lẫn key; masking **không thay thế** secret manager và quyền truy cập.

### 2.2. Những giới hạn Kubernetes cần nhớ

- Secret mount dạng projected volume có thể cập nhật file theo chu kỳ, **không đồng nghĩa broker/JVM tự reload TLS context**.
- Secret mount qua `subPath` không nhận cập nhật theo cách projected volume thông thường; cần rollout lại.
- Secret inject thành environment variable không tự thay giá trị trong process đang chạy.
- Secret bản thân không được coi là mã hóa an toàn ở mọi tầng; cần RBAC, encryption-at-rest, audit, service account least privilege.
- Ứng dụng dùng connection pool/caching có thể giữ password hoặc TLS session **cũ trong bộ nhớ** dù secret file đã được cập nhật.

## 3. Certificate, private key, PKCS#12 và truststore

Một chứng thư TLS **không** chứa private key. Keystore PKCS#12 có thể chứa **private key + leaf certificate + intermediate chain**. Truststore thường chứa CA/cert công khai dùng để kiểm tra phía còn lại.

### 3.1. Quy trình phát hành chứng thư broker

1. Chốt hostname client **thực sự dùng**: ví dụ `broker.messaging.internal.example` hoặc DNS của load balancer.
2. Tạo **key pair mới** ở nơi được phép; phát hành CSR có SAN chính xác.
3. PKI cấp leaf cert, intermediate chain, thời hạn và EKU server authentication thích hợp.
4. Đóng gói key/cert/chain thành PKCS#12, gán alias rõ ràng.
5. Ghi certificate serial, issuer, SAN, `notBefore`, `notAfter` và SHA-256 fingerprint.
6. Cấp CA tin cậy cho client, **không cấp private key broker** cho client.
7. Thử keystore mới có thể mở được bằng password phiên bản mới; đối chiếu public key và private key.

Để rotate vì nghi ngờ lộ private key, không chỉ gia hạn leaf cert trên private key cũ. Cần key pair mới và quy trình thu hồi key/cert cũ.

### 3.2. Lệnh xem certificate và keystore, không in private key

~~~bash
openssl x509 -in broker-leaf.pem \
  -noout -subject -issuer -serial -dates \
  -fingerprint -sha256 -ext subjectAltName
~~~

~~~bash
# Nhập password tương tác, không đặt password vào command line.
keytool -list -v -storetype PKCS12 \
  -keystore /run/secrets/messaging/server-keystore.p12
~~~

~~~bash
# Fresh server TLS handshake + kiểm tra CA và hostname.
openssl s_client \
  -connect broker.messaging.internal.example:61617 \
  -servername broker.messaging.internal.example \
  -verify_hostname broker.messaging.internal.example \
  -verify_return_error \
  -CAfile org-messaging-ca.pem
~~~

Với **mTLS**, probe cần thêm certificate/key client hợp lệ (ví dụ `-cert client.pem -key client.key`) để handshake hoàn thành. Lệnh `s_client` **chưa xác minh JMS user/password hoặc quyền queue**; sau TLS test phải thực hiện một thao tác send/consume thực.

### 3.3. Những lỗi phải đọc đúng nguồn

| Dấu hiệu | Lớp lỗi và nguyên nhân hay gặp |
|---|---|
| `PKIX path building failed` | Client thiếu CA/intermediate hoặc nạp sai truststore |
| `No subject alternative DNS name matching` | SAN không chứa hostname dùng trong broker URL |
| `certificate expired/not yet valid` | Cert hoặc đồng hồ hệ thống không hợp lệ |
| `bad_certificate` / `certificate_required` | Broker yêu cầu mTLS, client cert thiếu/không được tin |
| `UnrecoverableKeyException` | Keystore password, key password, type hoặc alias không đúng |
| TLS hoàn tất nhưng JMS login bị từ chối | JMS authentication backend/credential sai |
| JMS login được nhưng send bị cấm | Authorization, ACL theo queue/address sai |

**Không sửa** lỗi chain/SAN bằng `trustAll=true`, tắt kiểm tra hostname hoặc tạm cho phép mọi role trong production.

## 4. Artemis broker: cấu hình TLS và security settings

ActiveMQ **Artemis** sử dụng Netty acceptor trong `etc/broker.xml`. Ví dụ **lab** TLS/mTLS, cấu hình phần tử trong `<acceptors>` của `<core>`:

~~~xml
<acceptor name="netty-tls">
  tcp://0.0.0.0:61617?sslEnabled=true;keyStoreType=PKCS12;keyStorePath=/run/secrets/messaging/server-keystore.p12;keyStorePassword=LAB_ONLY_KEY_PASS;trustStoreType=PKCS12;trustStorePath=/run/secrets/messaging/server-truststore.p12;trustStorePassword=LAB_ONLY_TRUST_PASS;needClientAuth=true
</acceptor>
~~~

Giải thích:

- `sslEnabled=true` bật TLS cho acceptor; `keyStore*` là danh tính máy chủ.
- `trustStore*` cùng `needClientAuth=true` dùng khi broker xác thực **client certificate**.
- `0.0.0.0` là địa chỉ lắng nghe, **không** phải SAN certificate; client phải kết nối bằng hostname hợp lệ.
- Nếu chỉ dùng **TLS server authentication + JMS password**, bỏ `needClientAuth=true` và phần truststore dành xác minh client certificate nếu không cần; **client vẫn phải tin CA broker**.
- Các giá trị `LAB_ONLY_*` chỉ là placeholder để **thay trong môi trường lab**. Không commit password production vào `broker.xml`.

Production nên lấy file/password từ secret manager hoặc render cấu hình ở thời điểm deploy bằng pipeline có quyền chặt, tránh log cấu hình chứa bí mật. **Đừng khẳng định** một cú pháp `${ENV_VAR}` bất kỳ trong broker.xml sẽ được Artemis version đang dùng nội suy nếu chưa kiểm chứng tính năng/đường nạp thuộc tính.

### 4.1. Authorization vẫn cần role, ngay cả khi TLS chạy tốt

Fragment Artemis minh họa quyền tối thiểu:

~~~xml
<security-settings>
  <security-setting match="billing.commands">
    <permission type="send" roles="billing-producer"/>
    <permission type="consume" roles="billing-worker"/>
    <permission type="browse" roles="billing-operator"/>
    <permission type="createDurableQueue" roles="broker-admin"/>
    <permission type="deleteDurableQueue" roles="broker-admin"/>
  </security-setting>
</security-settings>
~~~

Roles phải được user backend/JAAS hoặc identity mapping cấp đúng. Nếu broker bật auto-create, thao tác tạo queue có thể cần quyền bổ sung. Certificate mTLS được tin **không tự biến** thành role `billing-producer`; cần cấu hình provider xác thực dựa certificate và mapping cụ thể.

### 4.2. TLS reload trên Artemis có giới hạn phiên bản

Thay file `.p12` **không mặc định** làm acceptor đang chạy sử dụng chứng thư mới. Khả năng auto-reload/reload phụ thuộc phiên bản Artemis, loại acceptor và tùy chọn cụ thể; phải chứng minh bằng một **fresh handshake** tới node vừa cập nhật.

Nếu không có reload mechanism đã được thử nghiệm:

1. Đặt keystore mới ở đường dẫn version riêng.
2. Chuẩn bị broker config và password mới như **một bản triển khai**.
3. Rolling restart/failover từng node theo HA policy, có quorum/fencing.
4. Fresh TLS handshake + JMS send/consume tới **từng endpoint**, kể cả backup.
5. Chỉ dọn cert cũ sau khi tất cả node đã chuyển và hết cửa sổ rollback.

Replication/journal HA **không tự sao chép** file key/truststore trong đường dẫn riêng của từng broker node.

## 5. ActiveMQ Classic: SSL transport, không dùng Netty acceptor của Artemis

ActiveMQ **Classic 5.x** thường cấu hình SSL transport connector trong `conf/activemq.xml` với XBean `sslContext`. Fragment **bên trong phần tử broker**:

~~~xml
<sslContext
    keyStore="file:/run/secrets/messaging/server-keystore.p12"
    keyStorePassword="LAB_ONLY_KEY_PASS"
    keyStoreType="PKCS12"
    trustStore="file:/run/secrets/messaging/server-truststore.p12"
    trustStorePassword="LAB_ONLY_TRUST_PASS"
    trustStoreType="PKCS12"/>

<transportConnectors>
  <transportConnector
      name="ssl"
      uri="ssl://0.0.0.0:61617?needClientAuth=true"/>
</transportConnectors>
~~~

Đây là **fragment mẫu của Classic XBean**: kiểm tra namespace/phiên bản SSL context và vị trí phần tử phù hợp template hiện tại, không thay thế file XML hoàn chỉnh. Với broker-only TLS, cấu hình `needClientAuth` cho phù hợp và không bắt buộc truststore dành client certificate.

| Mục | Classic | Artemis |
|---|---|---|
| Broker file | `activemq.xml` | `broker.xml` |
| TLS listener | `ssl://` connector + `sslContext` | Netty `tcp://...?sslEnabled=true;...` |
| Password login | `SimpleAuthenticationPlugin`/JAAS/LDAP/plugin | JAAS/PropertiesLoginModule/LDAP/plugin |
| Phân quyền | Authorization plugin/destination policy | `security-settings` và roles theo address |
| Reload secret/cert | Phụ thuộc backend/transport/version | Phụ thuộc backend/acceptor/version |
| Client certificate mapping | Cần cấu hình auth/JAAS phù hợp | Cần cấu hình auth/JAAS phù hợp |

**Không chép `<sslContext>` Classic sang `broker.xml` Artemis**, hoặc cấu hình `sslEnabled` Netty của Artemis sang Classic `activemq.xml`.

### 5.1. Đổi user/password trên broker không đồng nghĩa mọi session bị cắt

Classic và Artemis đều có thể dùng properties-based users, LDAP hoặc plugin khác. Khi password A bị thay/thu hồi ở nguồn xác thực:

- Backend có thể cần reload/restart để thay đổi hiệu lực.
- Đổi password thường ảnh hưởng **lần đăng nhập kế tiếp**, không nhất thiết đóng connection đã xác thực.
- Phải thử **new JMS connection** bằng password mới và bằng password cũ sau thu hồi.
- Nếu secret bị lộ, cần kế hoạch đóng session/connection cũ hoặc cô lập actor, không chỉ đổi file.

Không giả định file tên `users.properties` luôn là user store hoạt động. Phải xác minh JAAS/security plugin mà process thực tế đang dùng.

## 6. Luân chuyển mật khẩu JMS không gián đoạn: hai identity A/B

Đổi password **tại chỗ** trên một user đang được hàng trăm client dùng có thể làm mọi client reconnect đồng loạt thất bại. Chiến lược dễ kiểm chứng hơn là **tạo user B mới, dùng chồng lấn tạm thời, chuyển client, rồi thu hồi A**.

~~~text
A = billing-producer-v1   # đang hoạt động
B = billing-producer-v2   # identity mới
Queue được phép gửi = billing.commands
Cả A và B chỉ có role tối thiểu trong giai đoạn overlap.
~~~

### 6.1. Trình tự A/B và bằng chứng

| Bước | Broker/user backend | Client | Bằng chứng |
|---|---|---|---|
| 0. Inventory | Tìm user store thật, roles và destinations của A | Liệt kê app/instance dùng A | Có owner cho từng consumer/producer |
| 1. Tạo B | Cấp B quyền tối thiểu tương đương A | Chưa thay đổi | New login B thành công |
| 2. Kiểm quyền B | Kiểm tra mọi broker node đã cập nhật | Probe dùng B gửi đúng queue | Send được; destination bị cấm vẫn từ chối |
| 3. Phân phối secret B | A và B cùng hợp lệ tạm thời | Tạo secret version mới | Không lộ password trong Git/log |
| 4. Rolling rollout | Giữ A để không làm gián đoạn instance chưa đổi | Recreate factory/connection; lần lượt chuyển sang B | App mới dùng B; queue lag ổn |
| 5. Đối soát | Xem login/active sessions A/B | Mọi instance đã dùng B | Fresh reconnect của từng nhóm đạt |
| 6. Thu hồi A | Disable/delete A đúng backend | Không còn config A | **Fresh login A bị từ chối**, B vẫn chạy |
| 7. Cleanup | Thu hồi bản sao A theo retention | Cập nhật audit/runbook | Cửa sổ overlap đóng rõ ràng |

**Không đánh dấu hoàn tất ở bước 3.** Secret file đổi nhưng connection pool chưa recreate có thể vẫn giữ password A.

### 6.2. Khi user bị lộ phải thu hồi khẩn cấp

Nếu A đã bị lộ, không nhất thiết được giữ overlap đến khi mọi client hoàn thành vì mục tiêu availability. Chuyển nhanh sang B, khóa A theo ưu tiên xử lý sự cố và **cắt các active sessions cũ** nếu backend không tự cắt. Có thể chấp nhận gián đoạn có kiểm soát để bảo vệ hệ thống.

Sau sự cố, kiểm kê message send/consume, quyền admin, thời điểm truy cập, và khả năng side effect đã xảy ra từ principal A. Không tái kích hoạt A đã compromise chỉ vì rollback tiện hơn.

### 6.3. Tại sao “đổi mật khẩu cùng username” dễ lỗi?

~~~text
09:59 Client-1 đã login A và đang dùng connection dài hạn.
10:00 Broker chỉ chấp nhận password mới.
10:01 Client-2 reconnect bằng password cũ trong env -> AUTH FAIL.
10:02 Consumer-3 mất mạng, reconnect cũng AUTH FAIL.
10:05 Queue backlog tăng dù broker vẫn online.
~~~

Một số user backend có cơ chế chấp nhận nhiều secret song song, nhưng **không phải chuẩn của JMS hay mặc định của Classic/Artemis**. Nếu không hỗ trợ thì dùng hai identity hoặc maintenance window rõ ràng.

## 7. Gia hạn server certificate khi CA không đổi

Quy trình chuẩn cho cert do **cùng CA vẫn được client tin cậy** ký:

1. Xác minh SAN của certificate mới chứa hostname client đang dùng, EKU/issuer/chain hợp lệ.
2. Tạo **private key và certificate mới**; đóng gói thành keystore version N+1.
3. Thử mở keystore bằng password mới; ghi serial/fingerprint/expiry.
4. Cấp file keystore và password mới như **một cặp version**, không ghi đè dở dang lên file đang sử dụng.
5. Reload TLS **chỉ khi version đã được thử**; nếu không rolling restart broker/proxy theo HA.
6. Mở **new TLS handshake** tới từng endpoint; xác minh serial/cert mới, SAN và chain.
7. Thử JMS login/send/consume thực tế; kiểm tra lỗi TLS/JMS, queue lag, redelivery.
8. Sau khi mọi endpoint đã cập nhật, dọn private key/cert cũ theo retention và rollback policy.

### 7.1. Certificate mới không ảnh hưởng mọi kết nối đang sống

TLS xác minh certificate ở **handshake**. Connection JMS lâu sống có thể tiếp tục hoạt động bằng session TLS đã lập trước đổi cert; một lần gửi thành công qua connection cũ **không chứng minh** listener đang trình cert mới.

Cần probe **kết nối mới** và ghi serial/fingerprint thực tế; khi chính sách đòi mọi client chuyển sang cert mới, phải drain/reconnect các connection cũ.

### 7.2. Sai hostname SAN là lỗi cấu hình, không phải lý do tắt kiểm tra

~~~text
Client kết nối: mq-prod.svc.cluster.local
SAN server: DNS:broker.messaging.internal.example
Kết quả: hostname verification thất bại
~~~

Giải pháp: cấp cert có SAN đúng hostname dùng trong URI hoặc đổi URI sang DNS được chứng thư xác minh hợp lệ. Không dùng `verifyHost=false` hoặc `trustAll` để “giải quyết”.

## 8. Thay CA: luôn phát trust mới trước khi đổi broker cert

Nếu client chỉ tin **CA-A**, còn broker mới sẽ trình cert ký bởi **CA-B**, handshake bị từ chối nếu đổi broker cert trước.

~~~mermaid
sequenceDiagram
    participant PKI as PKI / Secret Manager
    participant C as JMS Clients
    participant B as Broker TLS
    PKI->>C: Cấp truststore CA-A + CA-B
    C->>C: Rollout/recreate TLS context
    C->>B: Kiểm tra vẫn tin cert-A
    PKI->>B: Cấp cert-B ký CA-B
    B->>B: Reload/restart TLS có kiểm soát
    C->>B: Fresh TLS + JMS connection
    B-->>C: Certificate B
    C->>C: Verify chain, SAN, JMS send/consume
    Note over C,B: Sau khi mọi endpoint chuyển xong
    PKI->>C: Loại CA-A khỏi truststore
    C->>C: Rollout + fresh negative test CA-A
~~~

| Giai đoạn | Truststore client | Cert broker |
|---|---|---|
| Ban đầu | Chỉ CA-A | Cert-A ký CA-A |
| **Overlap** | **CA-A + CA-B** | Vẫn Cert-A |
| Cutover | CA-A + CA-B | **Cert-B** ký CA-B |
| Cleanup | **Chỉ CA-B** | Cert-B |

**Đừng loại CA-A trước khi tất cả broker nodes/LB endpoint chuyển cert-B.** Nếu có cross-signed chain, cần kiểm tra chain thật và chính sách PKI; bảng minh họa giả định CA-A/CA-B độc lập.

### 8.1. mTLS có thêm chiều trust ngược

Nếu client cũng trình certificate:

1. **Broker truststore** được thêm CA-B cho **client certificates**, vẫn giữ CA-A trong overlap.
2. Client được cấp private key/cert mới ký CA-B; deploy và **reconnect**.
3. Broker xác minh cert và ánh xạ đúng identity/roles.
4. Chỉ khi mọi client đã dùng cert-B, broker mới loại CA-A khỏi truststore.
5. Probe fresh client cert cũ xác nhận bị từ chối nếu policy yêu cầu.

Không gộp tùy tiện **client trust CA để xác minh broker** và **broker trust CA để xác minh clients**. Chúng bảo vệ hai hướng khác nhau.

## 9. Thay mật khẩu PKCS#12 khác thay chứng thư và khác JMS password

Cùng một broker có thể dùng **hai loại mật khẩu** không liên quan:

- **Password của user JMS**: `billing-producer` dùng để đăng nhập broker.
- **Password của PKCS#12**: process dùng để mở keystore/truststore, lấy private key/certificate.

Có thể đổi password keystore **mà không đổi cert**, hoặc đổi cert/key giữ password keystore cũ, tùy chính sách. Nhưng với hoạt động bảo mật định kỳ, version hóa cả file lẫn secret giúp triển khai và rollback dễ kiểm soát hơn.

### 9.1. Triển khai cặp file + password như một version

1. Từ nguồn PKI/secret manager, tạo **keystore bản N+1** có key/cert/chain đã xác minh.
2. Cấp **keystore password N+1**, không viết thẳng vào image hoặc Git.
3. Kiểm tra mở store với password N+1 bằng công cụ có chế độ nhập tương tác.
4. Đưa file và password mới vào node như **một phiên bản deploy**; tránh cập nhật file trước mà password đến sau.
5. Reload TLS nếu được version hỗ trợ và đã kiểm thử; nếu không, rolling restart.
6. Dùng **fresh TLS handshake** xác minh broker trình cert mong đợi.
7. Khi mọi node/app đã chuyển và hết cửa sổ rollback, xóa file/password N khỏi đường runtime cần thiết.

Với password truststore, nhớ rằng **đổi password không loại CA-A khỏi trust**. Muốn chuyển CA thì nội dung truststore cũng phải được tạo lại.

### 9.2. Thay file an toàn

Không ghi từng byte đè lên file `.p12` đang được process mở. Nên phát file mới với tên version, đặt quyền file phù hợp, kiểm tra checksum rồi chuyển tham chiếu cấu hình nguyên tử theo khả năng của runtime.

Với filesystem, file mới và password phải cùng một phiên bản; với Kubernetes, projected Secret có thể thay nội dung file nhưng không bắt buộc broker **nạp lại**, và `subPath` không tự cập nhật.

**Rollback đúng là cặp `store-N.p12 + pass-N`, không phải `store-N.p12 + pass-N+1`.**

## 10. Java Artemis Core: chứng minh một connection dùng TLS và credential mới

Để đánh giá rotation, phải **tạo connection mới**, không chỉ thấy một connection đang sống còn gửi được. Ví dụ Artemis Core (khác Jakarta JMS) dùng Netty transport parameters. Code minh họa **Artemis Core client** với Java 17+ và `org.apache.activemq:artemis-core-client` cùng nhánh phù hợp broker.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

import org.apache.activemq.artemis.api.core.TransportConfiguration;
import org.apache.activemq.artemis.api.core.client.ActiveMQClient;
import org.apache.activemq.artemis.api.core.client.ClientSession;
import org.apache.activemq.artemis.api.core.client.ClientSessionFactory;
import org.apache.activemq.artemis.api.core.client.ServerLocator;
import org.apache.activemq.artemis.core.remoting.impl.netty.NettyConnectorFactory;

public final class ArtemisTlsLoginProbe {

    private static String secret(Path path) throws Exception {
        // File nhỏ do secret manager mount; giữ nguyên dấu cách hợp lệ.
        // Chỉ loại dòng mới ở cuối do cách tạo file.
        return Files.readString(path, StandardCharsets.UTF_8)
                .replaceFirst("[\\r\\n]+$", "");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArtemisTlsLoginProbe <secretDirectory>");
        }
        Path secrets = Path.of(args[0]);

        Map<String, Object> params = new HashMap<>();
        params.put("host", "broker.messaging.internal.example");
        params.put("port", 61617);
        params.put("sslEnabled", true);
        params.put("verifyHost", true);

        params.put("trustStoreType", "PKCS12");
        params.put("trustStorePath",
                secrets.resolve("app-truststore.p12").toString());
        params.put("trustStorePassword",
                secret(secrets.resolve("app-truststore.pass")));

        // Chỉ cần khi broker bật mTLS:
        params.put("keyStoreType", "PKCS12");
        params.put("keyStorePath",
                secrets.resolve("app-keystore.p12").toString());
        params.put("keyStorePassword",
                secret(secrets.resolve("app-keystore.pass")));

        TransportConfiguration transport = new TransportConfiguration(
                NettyConnectorFactory.class.getName(), params);
        ServerLocator locator =
                ActiveMQClient.createServerLocatorWithoutHA(transport);

        ClientSessionFactory factory = null;
        ClientSession session = null;
        try {
            factory = locator.createSessionFactory();

            // Lấy version mới từ mounted files tại thời điểm createSession.
            String user = secret(secrets.resolve("jms-username"));
            String pass = secret(secrets.resolve("jms-password"));

            session = factory.createSession(
                    user, pass,
                    false, true, true, false, 0);

            System.out.println("CONNECTED_AND_AUTHENTICATED");
        } finally {
            if (session != null) session.close();
            if (factory != null) factory.close();
            locator.close();
        }
    }
}
~~~

**Chú ý để dùng đúng:**

- `verifyHost=true` buộc tên endpoint phù hợp certificate SAN. Không tắt nó để thử cert mới.
- `app-keystore.p12` là **private key của client**, không phải của broker. Nếu không dùng mTLS, **bỏ toàn bộ ba tham số `keyStore*`**.
- Chương trình mới kiểm chứng **TLS + user authentication**, chưa chứng minh quyền trên queue. Tạo thêm phép thử send/consume với test destination được cấp quyền và thử bị từ chối với destination không được cấp.
- Một session hiện hữu không tự đọc lại file secret khi file đổi; chạy probe mới hoặc recreate connection factory/pool.
- API client Core này không phải interface JMS; với Spring Boot/`JmsTemplate` cần cấu hình JMS `ConnectionFactory` đúng provider và quản lý lifecycle tương tự.
- Password là `String` vì API nhận String; Java không đảm bảo xóa bộ nhớ String. Tránh log, heap dump không kiểm soát và scope tồn tại lâu, sử dụng secret integration của runtime nếu có.

### 10.1. Classic: tạo connection SSL mới

Ví dụ **ActiveMQ Classic 5.x** và `javax.jms` với `ActiveMQSslConnectionFactory`:

~~~java
import javax.jms.Connection;
import org.apache.activemq.ActiveMQSslConnectionFactory;

// Phần minh họa bên trong một method đã có secret loader.
ActiveMQSslConnectionFactory cf =
        new ActiveMQSslConnectionFactory(
                "ssl://broker.messaging.internal.example:61617");

cf.setTrustStore("/run/secrets/messaging/app-truststore.p12");
cf.setTrustStorePassword(loadSecret("app-truststore.pass"));

// Cần khi broker bật mTLS:
cf.setKeyStore("/run/secrets/messaging/app-keystore.p12");
cf.setKeyStorePassword(loadSecret("app-keystore.pass"));

Connection connection = cf.createConnection(
        loadSecret("jms-username"),
        loadSecret("jms-password"));
try {
    connection.start();
    // Tạo session và thử send/consume trên queue test được cấp quyền.
} finally {
    connection.close();
}
~~~

`loadSecret(String)` là **hàm của ứng dụng phải tự triển khai**, snippet không phải class hoàn chỉnh. Kiểm tra loại truststore/keystore PKCS#12 mà **Classic SSL factory và JDK thực tế** sử dụng; cấu hình store type theo API/JSSE được phiên bản hỗ trợ. **Kiểm tra hostname verification bằng negative test** (hostname không thuộc SAN phải thất bại), không dựa vào giả định của một bản Classic cũ.

## 11. Spring Boot JMS: restart/rebuild ConnectionFactory khi secret đổi

Trong ứng dụng Spring Boot, có thể sử dụng:

~~~yaml
# Classic application.yml
spring:
  activemq:
    broker-url: ssl://broker.messaging.internal.example:61617
    user: PLACEHOLDER_FROM_SECRET_SOURCE
    password: PLACEHOLDER_FROM_SECRET_SOURCE
~~~

Hoặc với Artemis:

~~~yaml
# Artemis application.yml
spring:
  artemis:
    mode: native
    broker-url: tcp://broker.messaging.internal.example:61617
    user: PLACEHOLDER_FROM_SECRET_SOURCE
    password: PLACEHOLDER_FROM_SECRET_SOURCE
~~~

**Các placeholder này chỉ minh họa việc cấu hình phải được cấp từ secret source thực**; bản YAML trên không phải hướng dẫn chạy production nguyên xi. Với Artemis native TLS, cần bật `sslEnabled` và trust/hostname verification bằng **URI/provider SSL options hoặc custom factory** được Spring Boot version hỗ trợ; chỉ có `broker-url=tcp://...` ở trên **không tự bật TLS**. Với Classic `ssl://`, cấu hình truststore/client keystore và kiểm tra hostname theo client/JDK đang dùng là điều kiện bắt buộc.

Nội dung quan trọng hơn syntax YAML là **lifecycle**:

1. Secret manager cấp bản B.
2. Runtime nhận bản B (file/env/config).
3. Ứng dụng **rebuild** `ConnectionFactory`/pool hoặc được rolling restart.
4. `JmsTemplate` và listener container tạo **new connection** bằng B.
5. Broker ghi nhận login B; producer/consumer chạy thật.
6. Sau khi tất cả instance chuyển, broker mới thu hồi A.

Caching/pooled JMS factory có thể giữ connection trong thời gian dài. Thay environment variable trong cluster hoặc cập nhật Secret object **không** tự thay password đã lưu trong một bean Java.

Đối với kết nối dài hạn, không dùng “password đã thu hồi nhưng connection vẫn gửi được” làm bằng chứng rotation thất bại của **new logins**. Tuy nhiên nó cho thấy active session cũ chưa được cắt; nếu yêu cầu thu hồi hoàn toàn, phải drain/close theo quy trình.

## 12. Rotation trên HA và nhiều endpoint

Trong hệ nhiều node, phải kiểm kê cả:

- TLS listener JMS client của từng primary/backup broker.
- Client URLs chứa nhiều endpoint (Classic Failover Transport, Artemis topology/reconnect).
- Cluster/replication connector nếu dùng TLS/auth riêng.
- Load balancer, ingress hoặc reverse proxy nơi TLS **kết thúc thực sự**.
- Management console/API, monitoring agents, bridge connectors, integration tests.
- DR site/standby và automation jobs có credential hiếm khi sử dụng.

**Không kiểm tra chỉ một hostname load balancer**: nó có thể đang đưa bạn tới một node đã rotate trong khi node backup vẫn dùng cert hoặc user backend cũ.

### 12.1. Failover khi đổi cert có thể gây nhiều lớp lỗi

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Broker A
    participant B as Broker B
    P->>A: JMS send trong TLS session
    Note over A: Rotation/restart của A
    A--xP: Connection mất trước response commit
    P->>B: TLS handshake + JMS login mới
    Note over B: B cần cert, CA, user/role mới
    B-->>P: New connection OK
    Note over P: Commit ở A có thể chưa biết kết quả
    P->>B: Retry với cùng business eventId
~~~

Ba việc cần kiểm chứng độc lập:

1. **TLS mới tới B** có cert đúng và client trust đúng.
2. **Credential B** được backend broker B nhận và có role đúng.
3. Producer/consumer có thể xử lý **unknown commit/redelivery** mà không bỏ message hoặc tạo side effect trùng.

Thành công của (1) và (2) **không tự bảo đảm** (3).

## 13. Bài toán giao dịch JMS khi rotation làm đứt kết nối

Producer đang gửi event `InvoiceRequested(eventId=E-1001)`:

~~~text
Producer send()/commit()
  -> Broker commit message thành công
  -> TLS connection bị ngắt trước khi response về Java
  -> Producer thấy JMSException/timeout
  -> Kết quả lần gửi là UNKNOWN, không chắc đã rollback
  -> Retry bằng credential mới B
  -> Có thể tồn tại hai bản gửi cùng eventId
~~~

**Không tạo event ID mới cho lần retry**. Producer nên có transactional outbox giữ ý định publish bền, payload và `eventId` ổn định. Consumer dùng inbox/unique constraint để bảo đảm một event không tạo side effect nghiệp vụ trùng.

Chiều nhận cũng có khoảng lỗi:

~~~text
Consumer xử lý và COMMIT hóa đơn trong DB
  -> TLS/JMS connection ngắt trước JMS ACK/commit
  -> Broker có thể redeliver sau reconnect
  -> Nếu không idempotent sẽ tạo thêm một hóa đơn
~~~

Rotation cần có **redelivery metrics và business completion metrics**, không chỉ TLS/JMS uptime.

### 13.1. Rollout an toàn với in-flight work

1. Ghi baseline queue depth, oldest pending age, send latency, số consumer và error rate.
2. Drain/giảm traffic cho instance đang chuyển khi workload cho phép.
3. Bảo đảm instance mới dùng secret B đã online trước khi gỡ instance cũ.
4. Cho transaction đang chạy thời gian hoàn tất trong giới hạn shutdown/grace period.
5. Với kết quả commit không rõ, giữ outbox event ở trạng thái pending/unknown; retry có backoff và idempotency.
6. Sau rollout, đối soát queue pending/inflight, redelivery, DLQ và business results.
7. Với topic durable subscription, giữ client ID/subscription name theo hợp đồng; thay credential không có nghĩa được tự tạo subscription mới.

**Không hứa zero downtime tuyệt đối** chỉ vì A/B credentials. Kết quả phụ thuộc broker HA/reload, network, client retries và độ dài transaction.

## 14. Runbook kiểm chứng: có cả positive và negative tests

### 14.1. Ma trận trường hợp

| Test | Trước thay | Trong overlap | Sau dọn |
|---|---|---|---|
| Fresh JMS login bằng A | PASS | PASS | **FAIL** |
| Fresh JMS login bằng B | Chưa cấp | **PASS** | PASS |
| B gửi queue được cấp quyền | Chưa cấp | PASS | PASS |
| B gửi queue bị cấm | FAIL | **FAIL** | FAIL |
| Client tin CA-A nối tới cert-A | PASS | PASS trước cutover | Không còn tương thích nếu chỉ tin CA-A và broker dùng cert-B |
| Client tin CA-A+CA-B nối tới cert-B | Trước cutover tùy cấu hình | **PASS** sau cutover | PASS |
| Client dùng hostname không thuộc SAN | **FAIL** | **FAIL** | **FAIL** |
| Client mTLS có cert đã bị thu hồi trust | Theo overlap | Có thể còn được tin | **FAIL trên fresh connection** |

Giả định CA-A/CA-B độc lập và không có cross-signed chain bổ sung. Sau rotation, kiểm tra **cert/CA thực** thay vì chỉ suy ra từ tên file.

### 14.2. Chạy thử TLS xác minh CA-B

~~~bash
openssl s_client \
  -connect broker.messaging.internal.example:61617 \
  -servername broker.messaging.internal.example \
  -verify_hostname broker.messaging.internal.example \
  -verify_return_error \
  -CAfile org-messaging-ca-B.pem
~~~

Khi broker bật mTLS, cần chứng thư client thích hợp để hoàn thành handshake. Dùng program JMS **tạo connection mới**, gửi một test message có ID riêng và nhận từ queue được cấp quyền, đồng thời thử thao tác queue bị cấm.

Thử **fresh login A bị từ chối** sau thu hồi; nhưng còn phải kiểm tra **các connection cũ của A** có bị đóng hay không khi yêu cầu thu hồi triệt để.

### 14.3. Ghi bằng chứng không lộ bí mật

~~~json
{
  "rotationId": "ROT-2026-11-17-001",
  "brokerEndpoint": "broker.messaging.internal.example:61617",
  "secretVersion": "B",
  "newCertificateSerial": "example-serial",
  "expectedSAN": "DNS:broker.messaging.internal.example",
  "freshTlsVerified": true,
  "freshJmsAuthenticated": true,
  "allowedDestinationSucceeded": true,
  "deniedDestinationRejected": true,
  "oldCredentialRejected": true
}
~~~

Các giá trị là **minh họa**, không phải kết quả kiểm thử thực. Log certificate serial/fingerprint và secret **version ID** là đủ cho kiểm toán; không ghi private key, password, token hay truststore toàn bộ.

## 15. Metrics và cảnh báo rotation

| Metric/audit | Dùng để làm gì? |
|---|---|
| Certificate expiry (days) | Alert trước hạn, ví dụ 30/14/7 ngày |
| Certificate serial/fingerprint theo broker endpoint | Phát hiện node/LB chưa chuyển cert |
| TLS handshake failures theo nguyên nhân | Nhận biết lỗi CA/SAN/client cert/protocol |
| JMS authentication failures theo user | Phát hiện client còn dùng password A |
| JMS authorization denials theo destination/role | Phát hiện identity B thiếu hoặc thừa quyền |
| Active connections theo user/node | Tìm session A chưa đóng |
| Secret version deployed theo app instance | Biết còn instance nào chưa chuyển sang B |
| Producer send latency/errors | Kiểm tra rollout gây timeout/backpressure |
| Consumer reconnect/redelivery | Kiểm tra listener resume và xử lý trùng |
| Queue pending/inflight/oldest age/DLQ | Thấy tác động tới business backlog |
| DR/standby configuration drift | Chứng minh backup node/DR site được cập nhật |

Metric names ở bảng là **đề xuất observability**, không phải tên JMX/API mặc định giống nhau trên Classic/Artemis.

Không gắn password hoặc secret value vào metric tag. Với audit danh tính, lưu ở hệ log có quyền truy cập phù hợp, không dump toàn bộ Java environment vào log.

## 16. Fault injection: năm thử nghiệm bắt buộc

### A — Password A/B: một client quên chuyển

1. Hai consumer dùng A; tạo B và cấp quyền chỉ `rotation.test.jobs`.
2. Rollout consumer 1 sang B và kiểm tra fresh login/send/consume.
3. Giữ consumer 2 dùng A, thu hồi A trong lab.
4. Ép consumer 2 reconnect: phải bị từ chối; xác nhận alert.
5. Chuyển consumer 2 sang B rồi restart/rebuild pool; kiểm tra queue drain.

**Kết luận:** cập nhật user store là chưa đủ; phải kiểm tra tất cả connection factories và consumer instances.

### B — Chuyển CA với overlap

1. Broker cert-A/CA-A, client ban đầu chỉ tin CA-A.
2. Rollout truststore CA-A+CA-B tới mọi client.
3. Thay server cert-B/CA-B trên một broker node đã được cô lập/HA phù hợp.
4. Fresh TLS + JMS probe tới từng endpoint trực tiếp.
5. Sau khi mọi node dùng cert-B, bỏ CA-A khỏi client truststores.
6. Fresh client chỉ tin CA-A phải thất bại.

**Kết luận:** thay CA theo **tin trước, đổi cert sau, thu hồi cuối**.

### C — mTLS hợp lệ nhưng thiếu quyền

1. Client dùng cert hợp lệ với CA broker tin.
2. Broker không map cert identity sang role được phép consume.
3. TLS có thể PASS nhưng JMS login/consume có thể FAIL tùy security integration.
4. Sửa role mapping least privilege và thử lại.
5. Thử send vào destination bị cấm vẫn phải FAIL.

**Kết luận:** chứng thư và JMS authorization là hai ranh giới độc lập.

### D — Pool vẫn dùng password cũ

1. Tạo pool lâu sống với A.
2. Thay secret mount sang B nhưng **không rebuild pool**.
3. Ép reconnect; xem client có còn dùng A không.
4. Recreate connection factory/pool hoặc rolling restart app.
5. Kiểm tra fresh login B, sau đó mới disable A.

**Kết luận:** secret được ghi vào file **không đồng nghĩa** secret đã được runtime nạp lại.

### E — Broker restart đúng lúc JMS commit

1. Trong broker lab, producer gửi persistent transacted event có `eventId` ổn định.
2. Inject restart/TLS disconnect gần thời điểm commit.
3. Ghi outcome **unknown** nếu mất phản hồi.
4. Retry bằng credential B nhưng **cùng eventId**.
5. Consumer inbox chỉ cho phép một business side effect.
6. Quan sát redelivery/queue lag trước khi kết luận rotation không mất dữ liệu.

**Kết luận:** rotation có thể tạo failure window JMS mà TLS handshake thành công sau đó không giải quyết được.

## 17. Rollback, thu hồi và tiêu chí dừng rollout

| Tình huống | Hành động an toàn |
|---|---|
| Cert mới có SAN/chain sai | Dừng rollout, giữ endpoint cũ nếu an toàn; sửa chứng thư |
| B đăng nhập được nhưng thiếu permission | Dừng rollout, cấp đúng role qua review, không mở ACL toàn broker |
| Backup/DR node chưa chuyển | Không loại CA-A/credential A, hoàn tất inventory |
| Authentication failure tăng, queue lag vượt ngưỡng | Giảm tốc rollout, kiểm tra app secret version và broker node |
| Keystore mới mở không được | Rollback **cặp store + password** phiên bản đã kiểm thử |
| A đã bị xác nhận lộ | **Không rollback về A**; dùng credential sạch, incident response |
| Một app không thể reconnect bằng B | Cô lập app/traffic nếu cần, kiểm tra config/pool rồi retry có giới hạn |

Một rollback plan phải có owner, thời điểm quyết định, version cũ **chưa bị compromise**, kênh thông báo và quy trình đối soát message sau cutover. Không được tái kích hoạt một credential đã bị lộ chỉ vì muốn khôi phục nhanh.

**Tiêu chí đóng rotation:** tất cả endpoint dùng cert/version mới; fresh JMS connections dùng identity B; user A không thể login mới; active sessions A đã được xử lý theo chính sách; policy ACL giữ least privilege; redelivery/queue backlog ổn định; audit record hoàn tất.

## 18. Các hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Kubernetes Secret đổi nghĩa là ứng dụng đổi password.” | Bean/pool có thể giữ bản cũ, phải recreate/restart |
| “Disable A tự cắt mọi session đã login.” | Backend có thể chỉ kiểm tra password lúc login; cần xử lý session cũ |
| “Chứng thư chưa hết hạn thì luôn hợp lệ.” | Còn SAN, chain, EKU, trust, algorithm, hostname, clock |
| “mTLS thành công là được quyền send mọi queue.” | Role/authorization vẫn quyết định |
| “Cert broker mới đã deploy nên mọi client đã nhìn thấy.” | Connection cũ không bắt buộc handshake lại |
| “Thay password PKCS#12 là thay certificate.” | Store password khác nội dung key/cert |
| “Bỏ CA-A khỏi truststore là đủ nếu broker còn cert-A.” | Client chỉ tin CA-B sẽ không xác minh cert-A |
| “Đổi server CA trước rồi bổ sung trust CA-B sau.” | Client có thể outage; triển khai trust overlap trước |
| “Tắt verifyHost khi đổi SAN để khôi phục kết nối.” | Làm yếu danh tính server và tăng rủi ro MITM |
| “Classic và Artemis đều dùng sslEnabled URI trên broker.” | Classic dùng SSL transport/XBean; Artemis dùng Netty acceptor |
| “Failover TLS bảo đảm không gửi message trùng.” | Commit response có thể unknown; cần eventId/outbox/inbox |
| “Log secret file giúp debug nhanh.” | Dễ rò rỉ private key/password; log version, metadata, lỗi đã che |

## 19. Checklist trước khi triển khai rotation production

- [ ] Có inventory mọi broker nodes, producers/consumers, management/cluster connectors và secret sources?
- [ ] Xác định đang đổi JMS password, keystore password, TLS certificate, client cert hay CA?
- [ ] Secret được lưu/version hóa ở nơi có RBAC, audit, retention và cấp phát an toàn?
- [ ] Không có password/private key trong Git, image, CI output, command line hoặc logs?
- [ ] Cert mới có SAN/EKU/issuer/expiry/chain đúng và matching private key?
- [ ] TLS client kiểm tra hostname/chain, không có `trustAll` hoặc `verifyHost=false`?
- [ ] Với mTLS, đã kiểm tra identity mapping và quyền JMS riêng?
- [ ] Khi thay CA, client trust A+B **trước** khi broker dùng cert-B?
- [ ] Khi thay JMS password, đã dùng A/B hoặc maintenance window có chủ đích?
- [ ] File keystore + password được triển khai cùng version, không ghép bản cũ/mới?
- [ ] Đã xác minh runtime nạp secret mới và restart/rebuild pool khi cần?
- [ ] Có fresh TLS/JMS positive tests và negative tests cho credential/CA cũ, ACL bị cấm?
- [ ] Đã kiểm tra từng node/LB, backup, failover route và DR environment?
- [ ] Có outbox/eventId/idempotency bảo vệ JMS transaction bị ngắt trong rollout?
- [ ] Có cảnh báo certificate expiry, handshake/auth errors, queue lag, reconnect, DLQ?
- [ ] Có rollback về phiên bản **sạch** và tiêu chí dừng rollout được phê duyệt?
- [ ] Có audit xác nhận old secret đã mất hiệu lực, đã dọn bản sao theo retention?

## 20. Kết luận

**Quản lý bí mật, đổi chứng thư và luân chuyển mật khẩu** trong ActiveMQ không phải là việc thay một dòng cấu hình. Classic dùng SSL transport/XBean và backend authentication tương ứng; Artemis dùng Netty acceptor, JAAS/user backend và security settings trên address. Cả hai đều cần **TLS trust đúng, credential đúng, quyền đúng và runtime thật sự nạp secret mới**.

Chiến lược an toàn là **overlap có kiểm soát**: JMS password dùng **identity A/B**; CA server dùng **client trust CA-A+CA-B trước khi thay cert**; mTLS cần thêm chiều broker trust client CA mới. Mọi bước phải chứng minh bằng **fresh TLS handshake, fresh JMS authentication, thao tác queue thật và negative test** cho credential cũ sau thu hồi.

Cuối cùng, credential rotation có thể ngắt producer/consumer trong khi JMS commit chưa rõ kết quả. Một hệ thống vận hành đáng tin cậy phải có **event ID ổn định, outbox, idempotent consumer, observability và rollback plan không tái kích hoạt secret đã bị lộ**. Rotation chỉ hoàn tất khi **danh tính mới hoạt động, danh tính cũ mất hiệu lực và nghiệp vụ vẫn nhất quán**.
