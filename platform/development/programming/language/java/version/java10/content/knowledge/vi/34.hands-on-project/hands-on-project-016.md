# Kiểm tra chuỗi tin cậy TLS bằng truststore được quản lý

## 1. Vì sao cần kiểm tra chuỗi tin cậy thay vì chỉ “có file truststore”?

Một dịch vụ Java gọi HTTPS không thể chỉ nhìn thấy **một chứng thư X.509** rồi mặc định tin tưởng máy chủ. Trình xác thực TLS phải xác định rằng chứng thư máy chủ phù hợp với một **đường chứng thư (certification path)** dẫn tới **trust anchor** được ứng dụng cho phép, sau đó kiểm tra **danh tính endpoint** và các ràng buộc bảo mật liên quan.

Sơ đồ thường gặp:

~~~text
                 TRUSTSTORE CUA CLIENT
                 +------------------------+
                 | Lab Root CA certificate |
                 | public / trusted anchor |
                 +-----------+------------+
                             |
                      ky Intermediate CA
                             |
                             v
                 +------------------------+
                 | Intermediate CA cert   |
                 | CA=true; keyCertSign   |
                 +-----------+------------+
                             |
                      ky Server cert
                             |
                             v
                 +------------------------+
                 | Server leaf cert       |
                 | SAN=127.0.0.1          |
                 | EKU=serverAuth         |
                 +-----------+------------+
                             |
                  Private key tuong ung
                             |
                             v
                         TLS SERVER

     TLS CLIENT:
       1. Nhan leaf va cac intermediate phu hop
       2. Kiem tra duong ky so toi root da duoc tin
       3. Kiem tra thoi han, rang buoc, thuat toan
       4. Kiem tra SAN/hostname cho endpoint can ket noi
       5. Chi trao doi du lieu ung dung sau handshake hop le
~~~

Một **truststore được quản lý** không chỉ là một file `.p12` bất kỳ. Nó cần có **nguồn cấp root CA đáng tin, phạm vi sử dụng, kiểm tra fingerprint, quyền cập nhật, phiên bản, quy trình rotation, triển khai và kiểm thử từ đúng runtime**.

Ngữ cảnh của bài: **“Thực hành tổng hợp”**, Java 10. Đề mục trực tiếp: **“Kiểm tra chuỗi tin cậy TLS bằng truststore được quản lý”**.

Mốc Java 10 liên quan: **JEP 319 — Root Certificates** đã đưa một tập root CA công khai vào OpenJDK `cacerts`. Trong JDK hiện đại, root CA program, `cacerts` và các hạn chế thuật toán tiếp tục được cập nhật. Bài tập trung vào **JSSE, PKIX, PKCS12 và quản trị trust anchors còn áp dụng hiện nay**, không đề xuất kích hoạt giao thức hay thuật toán TLS đã không còn an toàn.

### Mục tiêu học tập

- Phân biệt root CA, intermediate CA, server leaf certificate, private key, certificate chain và trust anchor.
- Nắm được **certificate path validation theo PKIX** khác với **HTTPS hostname verification**.
- Hiểu vì sao intermediate certificate thiếu có thể gây lỗi dù root CA đã nằm trong truststore.
- Biết truststore nên giữ **public trusted certificates**, không bao giờ cần root CA private key để xác minh server.
- Tạo truststore riêng ở định dạng **PKCS12** và chỉ tin CA đã được phê duyệt.
- Biết `KeyStore`, `TrustManagerFactory`, `KeyManagerFactory`, `SSLContext`, `SSLParameters` và `SSLSocket` phối hợp như thế nào.
- Biết JSSE mặc định tìm `jssecacerts` rồi `cacerts` khi không có đường dẫn truststore tường minh.
- Hiểu vì sao đặt `javax.net.ssl.trustStore` riêng **không tự hợp nhất** các CAs mặc định của JDK.
- Thực hiện **bốn kiểm thử thật**: chuỗi đúng, truststore chứa CA sai, hostname không khớp, server thiếu intermediate.
- Đọc `keytool -list -v`, `keytool -printcert`, fingerprint SHA-256 và JSSE debug đúng mục đích.
- Quản lý truststore theo **version, owner, checksum, secret mount, change review, CA rotation, restart/reload và rollback**.
- Phân biệt CA trust, direct leaf trust/pinning và authorization; tránh thói quen “trust-all”.
- Chạy chương trình **Java 17+**, biên dịch bằng `--release 17`, đối chiếu stdout đã được kiểm chứng với OpenJDK 21.
- Đọc đúng nguyên nhân `PKIX path building failed`, lỗi hostname, algorithm constraints, expiry và revocation.
- Biết các giới hạn của bài lab: đây là PKI tạo cục bộ, không phải CA công khai hay chính sách phát hành production.

## 2. Các khái niệm PKI trước khi chạy thử

### 2.1. Root CA: nơi bắt đầu niềm tin

**Root Certificate Authority (root CA)** là một CA được ứng dụng/người vận hành chọn làm **trust anchor**. Chứng thư gốc có thể là self-signed nhưng **self-signed không tự động có nghĩa đáng tin**.

Một truststore có thể chứa:

~~~text
Alias: lab-root
Entry type: trustedCertEntry
Subject: CN=Lab Root,O=Example
Public key: RSA ...
~~~

Client cần **public certificate** của root CA. Client **không cần và không được nhận** root CA private key. Chữ ký của server certificate và intermediate certificate được kiểm tra bằng public keys trong chain và trust anchor.

Trong Java, `java.security.cert.TrustAnchor` thể hiện một CA được tin, có thể dựa trên X.509 certificate hoặc thông tin CA name/public key. Quyết định “được tin” là **chính sách**, không phải kết quả của việc certificate tự ký.

### 2.2. Intermediate CA: cầu nối có ràng buộc

CA gốc thường không ký trực tiếp mọi chứng thư server. Một intermediate CA có thể được root ký, rồi tiếp tục ký leaf certificate.

Thông thường intermediate cần:

- `BasicConstraints` chỉ rõ `CA=true`.
- `KeyUsage` cho phép `keyCertSign`.
- Những ràng buộc như **path length constraint**, name constraints hay certificate policies theo cấu hình PKI.
- Chữ ký hợp lệ từ CA cấp trên.
- Thời hạn và thuật toán được phép theo chính sách runtime.

Bài lab ký intermediate với `BC:c=ca:true,pathlen:0`, nghĩa intermediate **không được phát hành thêm subordinate CA** theo ràng buộc path length; nó vẫn có thể ký leaf certificate.

**Thiếu intermediate** là lỗi triển khai phổ biến: client có root CA trong truststore nhưng server chỉ gửi leaf certificate, nên path builder không tìm được chứng thư nối tới root.

### 2.3. Leaf certificate: danh tính server

Chứng thư cuối của server có:

- Public key tương ứng private key server giữ.
- Subject/Issuer, chữ ký, validity.
- **Subject Alternative Name (SAN)** chứa DNS names hoặc IP addresses server được cấp.
- `ExtendedKeyUsage=serverAuth` khi PKI/TLS server validation yêu cầu.
- `KeyUsage` phù hợp với key type và TLS protocol.
- Những certificate policies/constraints khác theo hệ thống.

Không coi `CN=localhost` là cách thay thế cho SAN trong thiết kế TLS hiện đại. Nếu client kết nối đến `127.0.0.1`, bài lab phát hành leaf certificate có `IP:127.0.0.1` trong SAN.

**Private key** không nằm trong chứng thư và không được gửi qua handshake. Server sử dụng nó để chứng minh quyền sở hữu danh tính tương ứng theo giao thức TLS.

### 2.4. Certificate chain ≠ truststore

| Thành phần | Nằm ở đâu trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `server-identity.p12` | Phía server | Private key của server + certificate chain. |
| Server leaf | Phía server và có thể được gửi qua handshake | Danh tính server đang được xác minh. |
| Intermediate CA certificate | Server gửi cùng leaf, hoặc client có qua nguồn tin cậy/khả dụng | Nối chữ ký từ leaf lên root. |
| Root CA certificate | `managed-trust.p12` trên client | Trust anchor được quản lý; public certificate. |
| `wrong-trust.p12` | Client test âm | Cố tình tin root CA khác; phải từ chối server lab. |

Một `KeyStore.PrivateKeyEntry` của server **có thể chứa certificate chain gồm leaf, intermediate, root**. Nhưng **certification path** mà `CertPathValidator` kiểm tra thông thường **không bao gồm chính trust anchor như một phần tử được xác minh trong path**. Root là điểm tin cậy được cấu hình sẵn.

Việc server gửi root CA kèm chain **không biến root thành trusted** nếu client chưa cấu hình tin root đó.

## 3. Có ít nhất bốn loại xác minh khác nhau

Một HTTPS client nên phân biệt:

| Tầng | Câu hỏi | Ví dụ thất bại |
| --- | --- | --- |
| **Path building/PKIX trust** | Chứng thư có nối tới trust anchor được phép không? | Root CA không tồn tại trong managed truststore. |
| **Certificate/path constraints** | Chữ ký, validity, CA constraints, KU/EKU, thuật toán và policies phù hợp không? | Intermediate thiếu `CA=true`; chứng thư hết hạn; chữ ký không hợp lệ. |
| **Endpoint identity** | SAN của server có khớp tên/IP mà client muốn kết nối không? | Kết nối `api.example` nhưng cert chỉ có SAN của `other.example`. |
| **Application authorization** | Endpoint đã xác thực có được phép gọi resource/method này không? | TLS hợp lệ nhưng tài khoản/API principal không có quyền nghiệp vụ. |

**TLS trust không thay authorization.** Một chứng thư hợp lệ cho `service.example` không tự chứng minh dịch vụ được gọi một API nội bộ cụ thể. Ngoài ra, **HTTPS hostname verification không chỉ là PKIX path validation**: path hợp lệ tới CA vẫn có thể bị từ chối nếu SAN khác endpoint.

### 3.1. Path building và path validation

- **Path building:** tìm chuỗi ứng viên từ leaf qua các issuing CA tới một trust anchor.
- **Path validation:** kiểm tra chữ ký, thời hạn, constraints, chính sách và những yêu cầu của certification path.
- **TLS peer validation:** ứng dụng JSSE có thể áp các yêu cầu TLS, như KU/EKU, disabled algorithms và endpoint identification, trong ngữ cảnh handshake.

Java cung cấp `java.security.cert.CertPathBuilder`, `CertPathValidator`, `PKIXBuilderParameters`, `TrustAnchor`. Trong TLS thông thường, ứng dụng thường để **`X509ExtendedTrustManager` của JSSE** thực hiện xác thực trong handshake thay vì tự viết path builder riêng.

### 3.2. Truststore đúng vẫn có thể không đủ

Giả sử managed truststore đã có root CA đúng, nhưng server:

- Chỉ gửi leaf, không gửi intermediate.
- Gửi intermediate sai issuer hoặc thiếu constraints.
- Dùng chứng thư hết hạn.
- Dùng SAN sai hoặc thiếu.
- Dùng thuật toán bị JDK security policy vô hiệu hóa.
- Có status revocation theo chính sách tổ chức.

Bất kỳ trường hợp phù hợp nào ở trên đều có thể làm handshake thất bại. **Không chữa bằng cách import tùy tiện thêm root certificates hoặc tắt hostname validation.**

### 3.3. Revocation không được tự động giả định

Theo **SunJSSE Java SE 25 Reference Guide**, khi `TrustManagerFactory` dùng PKIX và được khởi tạo bằng `init(KeyStore)`, mặc định của cấu hình đó **không bật revocation checking**.

Do đó, **không khẳng định** rằng chỉ cần một root CA trong truststore là client tự kiểm tra mọi CRL/OCSP và từ chối tất cả chứng thư đã bị thu hồi. Khi chính sách yêu cầu revocation, cần cấu hình và kiểm thử PKIX/OCSP/CRL có chủ đích, cân nhắc hành vi khi dịch vụ kiểm tra revocation không khả dụng.

Không dùng `trust-all TrustManager` hoặc bỏ qua chain validation để “lách” lỗi revocation, SAN hoặc thiếu CA.

## 4. Truststore được quản lý khác gì một file tùy ý?

Một **managed truststore** nên có các thuộc tính vận hành:

1. **Owner rõ ràng:** nhóm PKI/security hoặc đơn vị được ủy quyền quản lý CA trust.
2. **Nguồn gốc CA đáng tin:** root certificate lấy từ nguồn được phê duyệt; kiểm tra fingerprint SHA-256 qua **kênh độc lập**.
3. **Scope tối thiểu:** chỉ tin những CAs cần cho những endpoints/workloads đã định.
4. **Format rõ ràng:** ví dụ PKCS12, type/provider xác định.
5. **Integrity protection:** artifact version, checksum/signature, read-only mount và change control.
6. **Confidentiality đúng mức:** public CA certificate không phải private key, nhưng không cho phép attacker sửa truststore.
7. **Secret/password handling:** bảo vệ mật khẩu keystore theo policy; không hard-code vào Git, logs hay process arguments production.
8. **Deployment an toàn:** đường dẫn trong container, file permissions, owner, SELinux/AppArmor nếu có.
9. **Rotation:** có giai đoạn cho phép CA cũ/mới đồng thời khi được phê duyệt, kiểm thử và kế hoạch thu hồi anchor cũ.
10. **Validation:** kiểm tra manifest/metadata, số lượng aliases, fingerprint, expiry và TLS kết nối thật.
11. **Audit/rollback:** log thay đổi, version theo artifact, khôi phục nhanh khi phân phối nhầm.
12. **Monitoring:** TLS validation failures, certificate expiry, thay đổi root CAs và những thay đổi từ JDK vendor.

**Managed không có nghĩa “luôn tin nhiều CAs hơn”.** Hợp đồng tốt là danh sách trust anchors có kiểm soát, mức tin cậy thích hợp và các negative tests chứng minh rằng **server không đáng tin vẫn bị từ chối**.

### 4.1. Nên tránh sửa `cacerts` của JDK cho từng ứng dụng

JDK có kho `cacerts` mặc định, nhưng việc import trực tiếp một CA nội bộ vào `$JAVA_HOME/lib/security/cacerts` có thể:

- Ảnh hưởng nhiều ứng dụng dùng chung JDK image.
- Khó audit, khó so sánh các bản build.
- Mất hoặc thay đổi sau cập nhật JDK/container image.
- Trộn chính sách root CA public và CA nội bộ.
- Dẫn tới môi trường dev/CI/prod có danh sách CA khác nhau.

**Gợi ý:** Dùng một managed truststore riêng cho ứng dụng hoặc trust configuration rõ ràng qua framework/SSLContext. Nếu doanh nghiệp chọn quản lý `cacerts` tập trung, phải version và kiểm soát ở cấp image/runtime, không sửa thủ công sau triển khai.

### 4.2. Explicit truststore có thể thay thế default roots

Với SunJSSE, khi đặt:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/app-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

default trust manager sử dụng truststore được chỉ định. **Không mặc định hợp nhất** với root CA mặc định trong `cacerts`.

Nếu ứng dụng cần gọi cả website công khai và service nội bộ, một truststore chỉ chứa CA nội bộ có thể khiến calls công khai bị `PKIX path building failed`. Cần chính sách trust **có chủ đích** để xây tập CA phù hợp, không nhập mọi CA từ mọi nguồn.

### 4.3. Đường dẫn truststore sai không phải fallback đáng tin

Oracle JSSE Guide nêu: nếu `javax.net.ssl.trustStore` **đã được đặt** nhưng file tường minh **không tồn tại**, SunJSSE có thể khởi tạo default trust manager với **empty keystore**, thay vì tự tìm `cacerts`.

Trong Kubernetes, trường hợp này có thể đến từ:

- Secret/volume chưa mount.
- Container dùng path khác host.
- Filename bị typo hoặc case-sensitive trên Linux.
- Ownership/permissions sai.
- Thứ tự startup và quá trình tạo truststore chưa đúng.

Do đó cần **kiểm tra path và file type trước khi tạo SSLContext**, không chỉ đợi handshake lỗi rồi import thêm chứng thư.

### 4.4. Cấu hình mặc định của SunJSSE

Khi **không** có `javax.net.ssl.trustStore`, SunJSSE tìm truststore theo trình tự:

1. `<java-home>/lib/security/jssecacerts` nếu tồn tại.
2. Nếu không, `<java-home>/lib/security/cacerts`.
3. Nếu không có trust material phù hợp, ứng dụng không thể tự suy ra một root CA bất kỳ là trusted.

Đây là mô tả cho **SunJSSE reference implementation**, không phải một hợp đồng rằng mọi JSSE provider đều có cùng đường dẫn/behavior. Nên xác minh JDK vendor, security provider và application framework thực tế.

### 4.5. Truststore không nhất thiết chỉ lưu root

`KeyStore.TrustedCertificateEntry` có thể biểu diễn certificates mà tổ chức quyết định tin, bao gồm trong một số mô hình CA intermediate hoặc direct leaf trust. Nhưng đưa một intermediate CA trực tiếp thành trust anchor có thể thay đổi phạm vi tin, còn pinning leaf/public key cần rotation strategy riêng.

Trong bài lab, lựa chọn rõ ràng và dễ kiểm chứng nhất là **truststore chỉ chứa public root CA certificate**. Không sử dụng root private key trong truststore.

## 5. Các API Java liên quan

| API | Vai trò | Dùng trong lab? |
| --- | --- | --- |
| `KeyStore.getInstance("PKCS12")` | Nạp kho chứng thư/khóa từ file PKCS12. | Có. |
| `KeyStore.PrivateKeyEntry` | Entry chứa private key và certificate chain. | Kiểm tra server identity. |
| `KeyStore.TrustedCertificateEntry` | Entry public certificate được tin. | Kiểm tra client truststore. |
| `KeyManagerFactory` | Tạo key managers cung cấp local identity cho TLS server. | Có. |
| `TrustManagerFactory` | Tạo trust managers từ managed truststore. | Có. |
| `SSLContext` | Tạo TLS socket factories với managers đã cấu hình. | Có. |
| `SSLServerSocket` | TLS server listen trên loopback. | Có. |
| `SSLSocket` | TLS client connect và thực hiện handshake. | Có. |
| `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` | Bật HTTPS hostname/IP verification trong TLS handshake. | Có. |
| `X509ExtendedTrustManager` | Phần triển khai JSSE xử lý peer validation trong socket/engine context. | Sử dụng gián tiếp. |
| `CertPathValidator` / `PKIXParameters` | API cấp thấp cho certification path validation. | Không cần tự gọi trong lab. |
| `TrustAnchor` | Mô hình CA được tin khi kiểm tra PKIX path. | Khái niệm nền. |

### 5.1. Phân biệt hai manager factories

~~~java
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(serverIdentityStore, privateKeyPassword);

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(managedTruststore);
~~~

**Đây là snippet cấu hình**, biến `serverIdentityStore`, `privateKeyPassword` và `managedTruststore` phải được nạp trong ứng dụng. Phần chương trình hoàn chỉnh sẽ thực hiện đúng bước này.

- **Server KeyManager:** lựa chọn private key và certificate chain để trình danh tính server.
- **Client TrustManager:** xác minh server certificate theo trust anchors.
- **Không cần đưa root CA private key vào client**.
- Trong TLS server-authentication thông thường, client có thể gọi `SSLContext.init(null, trustManagers, null)`: không cấp local key managers, nhưng vẫn xác minh server.

### 5.2. Kiểm tra hostname là thao tác tường minh khi dùng raw socket

Đối với `SSLSocket` tự tạo, JSSE không tự suy luận mọi yêu cầu hostname verification của ứng dụng. Hãy bật:

~~~java
SSLParameters parameters = client.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(parameters);
client.startHandshake();
~~~

`client` ở snippet là `SSLSocket` được tạo với **expected hostname** phù hợp. Đừng tự viết TrustManager chấp nhận mọi chứng thư hoặc bỏ qua hostname chỉ vì server lab có certificate “do mình tạo”.

`HttpsURLConnection` và nhiều HTTP clients hiện đại có hostname verification theo cấu hình API riêng. Khi dùng frameworks, kiểm tra chính xác đường khởi tạo SSLContext/TrustManager và policy xác minh tên, không chỉ dựa vào system properties.

### 5.3. Truststore được đọc khi tạo manager/context

Nếu Java code gọi:

~~~java
TrustManagerFactory tmf = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(truststore);
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
~~~

thì `context` đã được khởi tạo với tập managers đó. **Ghi đè file truststore trên đĩa không tự bảo đảm** mọi existing contexts hoặc pooled connections sẽ nạp lại nội dung mới.

Khi áp CA rotation, cần xác định framework/JDK có **reload hooks** hay phải tạo context mới/restart process; thực hiện full handshakes mới để kiểm thử, tránh diễn giải sai bởi existing TLS sessions.

## 6. Thiết kế phòng lab: chỉ trust root CA được quản lý

Tất cả artifacts được tạo **cục bộ** bằng `keytool`, không cần network ngoài, chỉ TLS qua `127.0.0.1`.

~~~text
tls-trust-lab/
    root-private.p12          -> private key Root CA (CHI LAB)
    root.cer                  -> PUBLIC root certificate
    intermediate-private.p12  -> private key Intermediate CA (CHI LAB)
    intermediate.csr
    intermediate.cer          -> PUBLIC cert signed by root
    server-identity.p12       -> server private key + chain
    server.csr
    server.cer                -> PUBLIC leaf signed by intermediate
    managed-trust.p12         -> PUBLIC trusted Root CA only
    wrong-root-private.p12    -> another CA private key (CHI LAB)
    wrong-root.cer            -> PUBLIC wrong root
    wrong-trust.p12           -> PUBLIC wrong root only
    ManagedTrustChainLab.java -> JSSE handshake test harness
~~~

**Certificate topology:**

~~~text
Lab Root CA (CA=true)
   |
   +-- Lab Intermediate CA (CA=true, pathLen=0)
         |
         +-- Server leaf
               SAN=dns:localhost,ip:127.0.0.1
               EKU=serverAuth

ManagedTruststore:
  lab-root -> Lab Root CA public certificate

WrongTruststore:
  wrong-root -> unrelated root public certificate
~~~

**Mật khẩu `LabOnlyChange123` chỉ là dữ liệu lab**. Không dùng nó ở production. Trong shell, arguments của `keytool -storepass` có thể bị quan sát qua process list, command history hoặc CI logs. Môi trường production phải dùng secret-management/protected password input theo chính sách của tổ chức.

### 6.1. Điều kiện chạy

- Có **JDK 17+** với `javac`, `java`, `keytool`.
- Có quyền tạo một thư mục thử nghiệm mới.
- Cổng TCP loopback được phép.
- Runtime JSSE/PKIX hiện đại có hỗ trợ PKCS12, RSA 3072 và TLS.
- Không bật các system properties can thiệp AIA/revocation/trust ở môi trường lab.
- Code sẽ thực hiện ba **negative TLS tests**, nên một vài handshake bị từ chối là **kết quả đúng**, không phải “sửa bằng trust-all”.

**Đã kiểm chứng:** toàn bộ chuỗi tạo CA và Java handshake trên **OpenJDK 21.0.12.1 Linux** với `javac --release 17`; không yêu cầu JDK 10 để chạy các APIs hiện đại. Những nguyên tắc PKI/truststore cốt lõi vẫn liên quan Java 10 và JEP 319.

## 7. Tạo root CA và intermediate CA

Các lệnh dưới đây dùng **Bash** trên Linux/macOS. Hãy tạo **thư mục trống mới**, sau đó chạy lệnh trong đó:

~~~bash
mkdir tls-trust-lab
cd tls-trust-lab
export LAB_STORE_PASSWORD='LabOnlyChange123'
~~~

Không tạo thư mục nếu đường dẫn đã có chứa dữ liệu thật; không ghi đè một PKCS12 keystore tồn tại của ứng dụng. Khi thực hành production, tuyệt đối không đặt CA private keys cùng server image. Việc này chỉ minh họa cấu trúc chứng thư trong một lab cô lập.

### 7.1. Tạo root CA keypair và root certificate

~~~bash
keytool -genkeypair \
  -alias lab-root \
  -keyalg RSA -keysize 3072 -sigalg SHA256withRSA \
  -dname "CN=Lab Root,O=Example" \
  -ext "BC:c=ca:true" \
  -ext "KU:c=keyCertSign,cRLSign" \
  -validity 365 \
  -keystore root-private.p12 -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -keypass "$LAB_STORE_PASSWORD" \
  -noprompt
~~~

Mục đích: tạo **root private key** chỉ dùng ký chứng thư trong lab. `BC:c=ca:true` đánh dấu root là CA, `KU` gồm quyền ký certificates và CRLs.

Export **public certificate**:

~~~bash
keytool -exportcert \
  -alias lab-root \
  -keystore root-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -rfc -file root.cer

keytool -printcert -file root.cer
~~~

`root.cer` **không chứa root private key**. Nó có thể được đưa tới client sau khi đã **kiểm tra fingerprint và nguồn tin cậy**. Trong lab, ta tự tạo chứng thư nên biết nguồn gốc; trong hệ thống thật, không lấy certificate từ kết nối TLS đang báo lỗi rồi trust ngay mà không xác minh ngoài băng.

### 7.2. Tạo intermediate CA keypair và CSR

~~~bash
keytool -genkeypair \
  -alias lab-intermediate \
  -keyalg RSA -keysize 3072 -sigalg SHA256withRSA \
  -dname "CN=Lab Intermediate,O=Example" \
  -ext "BC:c=ca:true" \
  -validity 300 \
  -keystore intermediate-private.p12 -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -keypass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -certreq \
  -alias lab-intermediate \
  -keystore intermediate-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -file intermediate.csr
~~~

Lệnh `-genkeypair` ban đầu tạo một self-signed certificate tạm thời cho keypair. Sau khi CA gốc ký CSR và nhập certificate reply, private key vẫn thuộc intermediate, còn certificate chain phản ánh issuer thật.

### 7.3. Root CA ký intermediate certificate

~~~bash
keytool -gencert \
  -alias lab-root \
  -keystore root-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -infile intermediate.csr -outfile intermediate.cer \
  -rfc -validity 270 \
  -ext "BC:c=ca:true,pathlen:0" \
  -ext "KU:c=keyCertSign,cRLSign"
~~~

Ở đây:

- Issuer là **Lab Root**.
- Subject/public key là của **Lab Intermediate** từ CSR.
- `CA=true` cho phép intermediate phát hành certificates.
- `pathlen:0` giới hạn số **non-self-issued subordinate CA** được phép xuất hiện dưới intermediate trong certification path, không cấm leaf certificates.
- `keyCertSign` phù hợp với vai trò CA.

Đây là **CA tự tạo để học**, không phải hướng dẫn vận hành một production root CA. Production phải có PKI policy, HSM hoặc bảo vệ CA key tương xứng, logging, approvals và revocation process.

### 7.4. Nhập root rồi nhập intermediate certificate reply

~~~bash
keytool -importcert \
  -alias lab-root \
  -file root.cer \
  -keystore intermediate-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -importcert \
  -alias lab-intermediate \
  -file intermediate.cer \
  -keystore intermediate-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt
~~~

Thứ tự quan trọng cho bài lab: khi nhập certificate reply cho alias `lab-intermediate`, `keytool` cần xây được chain phù hợp từ intermediate tới root. Public root certificate được nhập trước để hỗ trợ việc đó.

**Không nhầm** việc nhập root **certificate** vào intermediate store với việc sao chép root **private key**. Chỉ có root certificate công khai được nhập.

## 8. Tạo server identity với chuỗi ba chứng thư

### 8.1. Tạo server keypair và CSR

~~~bash
keytool -genkeypair \
  -alias server \
  -keyalg RSA -keysize 3072 -sigalg SHA256withRSA \
  -dname "CN=localhost,O=Example" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -validity 240 \
  -keystore server-identity.p12 -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -keypass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -certreq \
  -alias server \
  -keystore server-identity.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -file server.csr
~~~

Trình duyệt hoặc TLS client **không được** tự tin leaf self-signed tạm thời ở bước này. Mục tiêu là đưa certificate reply do intermediate ký vào alias `server`.

### 8.2. Intermediate ký server leaf

~~~bash
keytool -gencert \
  -alias lab-intermediate \
  -keystore intermediate-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -infile server.csr -outfile server.cer \
  -rfc -validity 120 \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "KU:c=digitalSignature,keyEncipherment" \
  -ext "EKU=serverAuth"
~~~

Chứng thư server mới được cấp bởi **Lab Intermediate**, không phải trực tiếp bởi root. SAN bao gồm cả hostname `localhost` và IP `127.0.0.1`.

**Lưu ý:** Đây là một profile phát hành dành cho demo RSA/TLS. Trong production, thuật toán, KU/EKU, key size, policy constraints và certificate lifetime phải theo CA policy/JDK security requirements đang áp dụng, không copy một lệnh lab làm tiêu chuẩn cấp phát.

### 8.3. Nạp public CA certificates rồi import server reply

~~~bash
keytool -importcert \
  -alias lab-root \
  -file root.cer \
  -keystore server-identity.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -importcert \
  -alias lab-intermediate \
  -file intermediate.cer \
  -keystore server-identity.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -importcert \
  -alias server \
  -file server.cer \
  -keystore server-identity.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt
~~~

Để kiểm tra:

~~~bash
keytool -list -v \
  -alias server \
  -keystore server-identity.p12 \
  -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD"
~~~

Hai dòng quan trọng đã được kiểm chứng:

~~~text
Entry type: PrivateKeyEntry
Certificate chain length: 3
~~~

Chain nội bộ của identity entry gồm **leaf → intermediate → root**. Trong TLS production, việc gửi root CA qua handshake không nhất thiết bắt buộc hoặc cần thiết; client đã có trust anchor trong truststore. Không nhầm **chain length của private key entry** với số certificates mà mọi server bắt buộc truyền đi.

## 9. Tạo managed truststore và một truststore sai để kiểm thử âm

### 9.1. Import **chỉ public root** vào managed truststore

~~~bash
keytool -importcert \
  -alias lab-root \
  -file root.cer \
  -keystore managed-trust.p12 \
  -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt
~~~

Kiểm tra entry:

~~~bash
keytool -list -v \
  -alias lab-root \
  -keystore managed-trust.p12 \
  -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD"
~~~

Kết quả loại entry:

~~~text
Entry type: trustedCertEntry
~~~

Trong Java, `isKeyEntry("lab-root")` phải là `false`. Truststore này không chứa root private key.

**Bảo mật:** `-noprompt` chỉ thích hợp ở đây vì root cert **do chính lab tạo** và nguồn đã rõ. Khi nhận một root CA từ bên ngoài, luôn kiểm tra fingerprint SHA-256 qua kênh quản trị đáng tin **trước** khi import; không dùng `-noprompt` để tự động tin certificate chưa xác minh.

### 9.2. Tạo một CA khác, không liên quan tới server

Để chứng minh negative behavior, tạo “Wrong Lab Root” với private key/certificate riêng:

~~~bash
keytool -genkeypair \
  -alias wrong-root \
  -keyalg RSA -keysize 3072 -sigalg SHA256withRSA \
  -dname "CN=Wrong Lab Root,O=Example" \
  -ext "BC:c=ca:true" \
  -validity 365 \
  -keystore wrong-root-private.p12 -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt

keytool -exportcert \
  -alias wrong-root \
  -keystore wrong-root-private.p12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -rfc -file wrong-root.cer

keytool -importcert \
  -alias wrong-root \
  -file wrong-root.cer \
  -keystore wrong-trust.p12 \
  -storetype PKCS12 \
  -storepass "$LAB_STORE_PASSWORD" \
  -noprompt
~~~

`wrong-trust.p12` chứa một root CA hoàn toàn khác. Nó được tạo có chủ đích làm **negative fixture**. Nếu client dùng truststore này mà vẫn chấp nhận server ký bởi Lab Root, bộ test phải báo **FAIL** vì trust validation đã bị mở quá rộng hoặc bị bỏ qua.

### 9.3. Lab chỉ kiểm tra certificates, không trao private CA key qua TLS

Ở cuối bước này:

| Store/file | Chứa gì? | Ai dùng? |
| --- | --- | --- |
| `root-private.p12` | **Root CA private key**, certificate. | Chỉ quy trình phát hành lab. |
| `intermediate-private.p12` | **Intermediate CA private key**, chain. | Chỉ quy trình ký leaf lab. |
| `server-identity.p12` | **Server private key**, leaf + CA chain. | TLS server trong chương trình Java. |
| `managed-trust.p12` | **Public Lab Root cert**, trustedCertEntry. | TLS client để xác minh server. |
| `wrong-trust.p12` | **Public Wrong Root cert**, trustedCertEntry. | TLS client negative test. |

Đừng chuyển những file `*-private.p12` hay `server-identity.p12` tới máy client chỉ để client xác minh server. Quyền tin cậy của client là **public root certificate**, không phải quyền ký của private keys.

## 10. Chương trình Java 17+ kiểm tra bốn tình huống TLS

Bài lab dùng một process Java, chạy server trên TCP loopback và bốn client connections tuần tự.

| Kịch bản | Truststore client | Chain phía server | Hostname kỳ vọng | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| **Positive** | Managed root đúng | Leaf + intermediate + root | `127.0.0.1` | **ACCEPTED** |
| **Negative 1 — wrongRoot** | Root CA khác | Chain đúng | `127.0.0.1` | **REJECTED** |
| **Negative 2 — wrongHostname** | Root CA đúng | Chain đúng | `wrong.example.invalid` | **REJECTED** |
| **Negative 3 — missingIntermediate** | Root CA đúng | Chỉ leaf | `127.0.0.1` | **REJECTED** |

Điểm kỹ thuật của negative hostname test: chương trình tạo TCP transport tới **127.0.0.1** rồi bọc vào `SSLSocket` với expected logical hostname `wrong.example.invalid`. Nó **không tìm DNS** cho hostname giả và **không mở kết nối ra Internet**; nó chỉ kiểm tra rằng SAN validation không chấp nhận một tên khác.

Missing-intermediate test tạo một `KeyStore` **in-memory** có server private key + **chỉ leaf certificate**; không ghi đè identity keystore trên đĩa. Với isolated JSSE lab này, client chỉ tin root và không được cung cấp intermediate từ nguồn khác, nên phải từ chối path không hoàn chỉnh.

Tạo file **`ManagedTrustChainLab.java`**:

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class ManagedTrustChainLab {

    private static KeyStore load(String file, char[] password)
            throws Exception {
        KeyStore result = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            result.load(in, password);
        }
        return result;
    }

    private static SSLContext serverContext(KeyStore store,
                                            char[] password)
            throws Exception {
        KeyManagerFactory factory = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        factory.init(store, password);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(factory.getKeyManagers(), null, null);
        return context;
    }

    private static SSLContext clientContext(KeyStore trusted)
            throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(trusted);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);
        return context;
    }

    private static boolean attempt(SSLContext serverCtx,
                                   SSLContext clientCtx,
                                   String endpointName)
            throws Exception {
        InetAddress loopback =
                InetAddress.getByName("127.0.0.1");

        try (SSLServerSocket listener =
                     (SSLServerSocket) serverCtx
                             .getServerSocketFactory()
                             .createServerSocket(0, 1, loopback)) {
            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<Boolean> serverDone =
                        executor.submit(() -> {
                    try (SSLSocket peer =
                                 (SSLSocket) listener.accept()) {
                        peer.setSoTimeout(5000);
                        peer.startHandshake();
                        peer.getOutputStream().write(42);
                        peer.getOutputStream().flush();
                        return true;
                    } catch (java.io.IOException
                             expectedWhenRejected) {
                        return false;
                    }
                });

                boolean accepted;

                try (Socket transport =
                             new Socket(
                                     loopback,
                                     listener.getLocalPort());
                     SSLSocket client =
                             (SSLSocket) clientCtx
                                     .getSocketFactory()
                                     .createSocket(
                                             transport,
                                             endpointName,
                                             listener.getLocalPort(),
                                             true)) {

                    client.setSoTimeout(5000);

                    SSLParameters parameters =
                            client.getSSLParameters();
                    parameters.setEndpointIdentificationAlgorithm(
                            "HTTPS");
                    client.setSSLParameters(parameters);

                    client.startHandshake();

                    if (client.getInputStream().read() != 42) {
                        throw new AssertionError(
                                "Unexpected application byte");
                    }
                    if (client.getSession()
                            .getPeerCertificates().length < 1) {
                        throw new AssertionError(
                                "Peer certificate missing");
                    }
                    accepted = true;

                } catch (SSLException
                         rejectedByTlsValidation) {
                    accepted = false;
                }

                boolean serverAccepted =
                        serverDone.get(10, TimeUnit.SECONDS);

                if (accepted && !serverAccepted) {
                    throw new AssertionError(
                            "Server did not complete handshake");
                }
                return accepted;
            } finally {
                executor.shutdownNow();
            }
        }
    }

    private static void verify(
            String label, boolean actual, boolean expected) {
        if (actual != expected) {
            throw new AssertionError(
                    label + " unexpected=" + actual);
        }
        System.out.println(label + "=" +
                (actual ? "ACCEPTED" : "REJECTED"));
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: identity.p12 trusted-root.p12 wrong-root.p12");
        }

        String secret =
                System.getenv("LAB_STORE_PASSWORD");

        if (secret == null || secret.isEmpty()) {
            throw new IllegalStateException(
                    "LAB_STORE_PASSWORD is required");
        }

        char[] password = secret.toCharArray();

        KeyStore identity =
                load(args[0], password);
        KeyStore trust =
                load(args[1], password);
        KeyStore wrong =
                load(args[2], password);

        Certificate[] chain =
                identity.getCertificateChain("server");

        if (chain == null || chain.length != 3) {
            throw new AssertionError(
                    "Expected leaf -> intermediate -> root");
        }

        if (!identity.entryInstanceOf(
                "server",
                KeyStore.PrivateKeyEntry.class)) {
            throw new AssertionError(
                    "Server identity must contain private key");
        }

        if (!trust.entryInstanceOf(
                "lab-root",
                KeyStore.TrustedCertificateEntry.class)) {
            throw new AssertionError(
                    "Truststore must contain trusted root certificate");
        }

        if (trust.isKeyEntry("lab-root")) {
            throw new AssertionError(
                    "Truststore should not have root private key");
        }

        System.out.println("identity.chainLength=" +
                chain.length);

        System.out.println("trust.rootIsPublicOnly=" +
                !trust.isKeyEntry("lab-root"));

        System.out.println("chain.issuerMatches=" +
                ((X509Certificate) chain[0])
                        .getIssuerX500Principal()
                        .equals(
                                ((X509Certificate) chain[1])
                                        .getSubjectX500Principal()));

        SSLContext fullServer =
                serverContext(identity, password);

        SSLContext trustedClient =
                clientContext(trust);

        SSLContext wrongClient =
                clientContext(wrong);

        verify("validRootAndChain",
                attempt(fullServer, trustedClient, "127.0.0.1"),
                true);

        verify("wrongRoot",
                attempt(fullServer, wrongClient, "127.0.0.1"),
                false);

        verify("wrongHostname",
                attempt(fullServer, trustedClient,
                        "wrong.example.invalid"),
                false);

        KeyStore leafOnly =
                KeyStore.getInstance("PKCS12");
        leafOnly.load(null, password);

        PrivateKey privateKey =
                (PrivateKey) identity.getKey("server", password);

        leafOnly.setKeyEntry("server", privateKey, password,
                new Certificate[] { chain[0] });

        verify("missingIntermediate",
                attempt(
                        serverContext(leafOnly, password),
                        trustedClient,
                        "127.0.0.1"),
                false);

        System.out.println("RESULT=PASS");
    }
}
~~~

### 10.1. Biên dịch và chạy

Sau khi đã tạo đủ các files PKCS12 trong thư mục bài lab:

~~~bash
javac -encoding UTF-8 --release 17 ManagedTrustChainLab.java

java ManagedTrustChainLab \
  server-identity.p12 \
  managed-trust.p12 \
  wrong-trust.p12
~~~

Biến môi trường `LAB_STORE_PASSWORD` phải được khai báo trong **cùng terminal/session** như bước đầu. Nếu thiếu password hoặc file, chương trình sẽ báo lỗi; không diễn giải đó là lỗi trust validation thành công.

### 10.2. Stdout đã kiểm chứng trên OpenJDK 21.0.12.1 Linux

~~~text
identity.chainLength=3
trust.rootIsPublicOnly=true
chain.issuerMatches=true
validRootAndChain=ACCEPTED
wrongRoot=REJECTED
wrongHostname=REJECTED
missingIntermediate=REJECTED
RESULT=PASS
~~~

**Đây là kết quả đã chạy thật**, không phải stdout giả định. Script tạo certificates bằng `keytool`, `javac --release 17` biên dịch thành công, `java` hoàn tất exit code 0.

### 10.3. Cách đọc từng dòng

- `identity.chainLength=3`: private key entry trên server có leaf + intermediate + root.
- `trust.rootIsPublicOnly=true`: alias `lab-root` không chứa private key trong truststore; chỉ chứa trusted public root certificate.
- `chain.issuerMatches=true`: Issuer DN của leaf trùng Subject DN của intermediate. Đây là **kiểm tra mối liên hệ tên**; tự nó không chứng minh chữ ký hợp lệ.
- `validRootAndChain=ACCEPTED`: handshake thành công với truststore chứa root CA đúng và endpoint identity `127.0.0.1`; sau handshake client nhận byte `42`.
- `wrongRoot=REJECTED`: client chỉ tin wrong root nên không có trust path chấp nhận server hiện tại.
- `wrongHostname=REJECTED`: chain có thể hợp lệ, nhưng expected hostname `wrong.example.invalid` không có trong SAN.
- `missingIntermediate=REJECTED`: server chỉ trình leaf; client root-only không thể hoàn thiện path trong lab cô lập.
- `RESULT=PASS`: tất cả expectations được thỏa. Nếu một case được chấp nhận/từ chối ngược lại, hàm `verify` sẽ ném `AssertionError`, không in dòng kết quả PASS.

**Ranh giới của test:** Negative cases bắt `SSLException` để xác nhận handshake bị từ chối. Để chẩn đoán sâu hơn **lý do cụ thể**, cần thu/đối chiếu `SSLHandshakeException`, `CertPathValidatorException` hoặc JSSE debug trong môi trường kiểm thử, thay vì bắt mọi exception rồi tự động cho PASS. Bộ lab có positive control chứng minh server/JSSE có thể bắt tay khi trust và SAN đúng.

### 10.4. Tại sao không kiểm thử remote TLS thật bằng IP/domain ngẫu nhiên?

Điều đó khiến kết quả phụ thuộc mạng, DNS, certificate rotation và root CA program của máy người học. Lab chạy toàn bộ trên **loopback 127.0.0.1**, với root/intermediate/leaf do chính script phát hành. Việc dùng `wrong.example.invalid` chỉ là **logical expected hostname** để kiểm thử SAN mismatch, không truy cập tên miền đó.

Sau khi hiểu nguyên lý, đội vận hành có thể áp dụng cùng các kiểm tra với endpoint thật qua cấu hình an toàn của hệ thống, nhưng phải dùng **CA public certificates được kiểm nguồn** và các công cụ/permissions được phê duyệt.

## 11. Negative tests: vì sao có giá trị ngang positive tests?

Một hệ thống chỉ thử kết nối server đúng, rồi báo “TLS đã an toàn” là chưa đủ.

### 11.1. Wrong root — phải REJECTED

~~~text
Server chain: Lab Root -> Lab Intermediate -> Server
Client truststore: Wrong Lab Root only
Expected: REJECTED
~~~

Nếu vẫn được chấp nhận, cần điều tra:

- Client có thực sự dùng `wrong-trust.p12` không?
- Có library/framework tạo SSLContext khác và dùng `cacerts` không?
- Có TrustManager tùy biến chấp nhận mọi chứng thư không?
- Có skip certificate verification không?
- Có reuse TLS session từ context cũ trong test không?

Bài lab dùng **SSLContext riêng** cho good truststore và wrong truststore, tạo handshake mới mỗi lần để giảm nhầm lẫn.

### 11.2. Wrong hostname — phải REJECTED

~~~text
Trust anchor: Lab Root (correct)
Certificate SAN: DNS localhost, IP 127.0.0.1
Expected hostname: wrong.example.invalid
Expected: REJECTED
~~~

Đây là lỗi **endpoint identification**, không nhất thiết là lỗi CA trust. Nếu sửa bằng cách tắt hostname verification, bạn đã bỏ mất một tầng xác thực quan trọng.

**Không** xem “đã có CN trong certificate” là lý do bỏ qua SAN. Tên/IP mà client muốn kết nối cần được certificate cho phép theo HTTPS matching rules.

### 11.3. Missing intermediate — phải REJECTED trong lab

~~~text
Client trust anchor: Lab Root
Server sends: server leaf only
Missing: Lab Intermediate certificate
Expected: REJECTED
~~~

Trong một số hệ thống thực, client có thể đã cache intermediate hoặc lấy intermediate từ certificate store/AIA theo provider và cấu hình. Bởi vậy **không tuyên bố mọi client trên thế giới chắc chắn fail khi server thiếu intermediate**.

Nhưng một server production nên cung cấp chain đủ để client thông thường xây path, không phụ thuộc vào việc client tình cờ có intermediate. Lab đã tạo root-only truststore, không cung cấp intermediate bên ngoài và xác minh kết quả REJECTED.

### 11.4. Additional negative tests cần xem xét

Bên cạnh ba ca đã chạy:

| Test đề xuất | Dữ liệu thử | Kết quả mong đợi |
| --- | --- | --- |
| Expired leaf | Chứng thư đã quá `NotAfter` theo thời gian kiểm thử. | TLS peer validation từ chối theo chính sách. |
| Not-yet-valid leaf | `NotBefore` trong tương lai. | Từ chối theo certificate validity rules. |
| Invalid intermediate | Intermediate không có CA/basic constraints phù hợp. | PKIX không chấp nhận path. |
| Disabled algorithm | Certificate chain dùng thuật toán bị security policy cấm. | Từ chối theo JDK policy. |
| Wrong EKU | Chứng thư không được cấp cho TLS server auth khi yêu cầu. | Từ chối. |
| Truststore path missing | App cấu hình file không tồn tại. | Startup/config validation fail-fast hoặc trust thất bại. |
| Unapproved CA | Chain hợp lệ về mật mã nhưng anchor không được phê duyệt. | REJECTED. |
| Revoked certificate | Có CRL/OCSP và revocation checking đã được cấu hình. | Từ chối theo policy. |

**Các ca trong bảng này là đề xuất mở rộng, không phải kết quả đã chạy** của chương trình `ManagedTrustChainLab`. Đừng ghi stdout cho chúng nếu chưa thực nghiệm.

## 12. Vì sao không chỉ dùng `keytool -list` để chứng minh TLS hợp lệ?

`keytool -list -v` giúp đọc entries và metadata, nhưng bản thân nó không mô phỏng đầy đủ:

- SSLContext thực tế đang sử dụng truststore nào.
- Server trình chain gì trong handshake.
- Client đang đối chiếu hostname/IP nào.
- Thuật toán TLS và certificate policy hiện hành.
- Các cấu hình mặc định của JDK/security provider.
- Session caching, proxy hoặc framework custom trust managers.

Do đó quy trình tốt gồm **cả hai lớp**:

1. **Artifact inspection:** PKCS12 format, alias, entry type, root fingerprint, SAN, issuer, validity, EKU.
2. **Real TLS verification:** kết nối có endpoint identification, có positive và negative test trong chính runtime/JDK triển khai.

Một chứng thư `CN=Lab Root` trong file không chứng minh client tin nó; chứng thư ấy phải nằm trong trust material **thực sự được `TrustManager` sử dụng**.

### 12.1. Kiểm tra SHA-256 fingerprint

Trong lab:

~~~bash
keytool -printcert -file root.cer
~~~

Công cụ cho biết Subject, Issuer, validity và fingerprints, trong đó có SHA-256 theo bản JDK. Với root CA ngoài tổ chức, kiểm tra SHA-256 fingerprint qua **kênh đáng tin độc lập**, ví dụ PKI admin registry đã được ký/phê duyệt.

**Không lấy fingerprint từ cùng một certificate chưa kiểm nguồn rồi nói “đã xác minh”.** So sánh với chính nguồn không đáng tin không tạo thêm niềm tin.

### 12.2. Kiểm tra SAN, EKU và intermediate constraints

Để xem certificate:

~~~bash
keytool -printcert -v -file server.cer
keytool -printcert -v -file intermediate.cer
~~~

Cần kiểm tra:

- Issuer của server là Lab Intermediate.
- Intermediate Subject và public key phù hợp path.
- SAN chứa `127.0.0.1` và `localhost`.
- Server certificate EKU gồm serverAuth.
- Intermediate có BasicConstraints CA=true và KeyUsage keyCertSign.
- Certificate validity là giai đoạn được phép.
- Chữ ký, chain và policy được JSSE thực thi trong handshake.

**Không** lấy tên `Issuer` trùng `Subject` làm chứng minh đầy đủ về chữ ký; một kẻ tấn công cũng có thể tạo certificate với cùng chuỗi văn bản Issuer. Public key/chữ ký, path và trust anchor mới quyết định.

## 13. Chẩn đoán TLS trong một ứng dụng Java thật

### 13.1. Thông báo `PKIX path building failed`

Một lỗi thường thấy:

~~~text
javax.net.ssl.SSLHandshakeException
  caused by: sun.security.validator.ValidatorException:
  PKIX path building failed
~~~

Đây là **ví dụ dạng thông báo**, không phải output đã quan sát của toàn bộ môi trường. Chi tiết lớp exception/message phụ thuộc JDK/provider.

Các nguyên nhân có thể gồm:

- Root CA không có trong truststore **đang được dùng**.
- Server thiếu intermediate.
- Truststore path sai/empty hoặc không được mount.
- Client dùng truststore riêng nhưng nghĩ nó được hợp nhất với `cacerts`.
- Chứng thư/constraints/algorithms không phù hợp.
- Hệ thống sử dụng custom trust managers/configuration mà operator không biết.

**Không** khắc phục bằng cách import certificate của server vào global `cacerts` ngay lập tức, và **không** viết TrustManager chấp nhận tất cả certificates.

### 13.2. Lỗi hostname hoặc IP

Thông báo có thể chứa:

~~~text
No subject alternative names present
No subject alternative names matching IP address ... found
No name matching ... found
~~~

Đây là **những ví dụ của triệu chứng**, không phải hợp đồng nguyên văn mọi JDK. Kiểm tra expected endpoint name và SAN của leaf certificate.

Sửa certificate/SAN hoặc endpoint configuration; không tắt `setEndpointIdentificationAlgorithm("HTTPS")` trong raw SSLSocket client.

### 13.3. Lỗi thiếu private key hoặc chain phía server

Một server có truststore nhưng không có **server identity private key** có thể không trình được certificate phù hợp. Đừng nhầm:

- **Server identity keystore:** private key + leaf/chain.
- **Client managed truststore:** CA public certificate.
- **Server truststore trong mTLS:** CA cho phép xác minh client, nếu có mutual TLS.
- **Client identity keystore trong mTLS:** private key + chain của client.

Lab chỉ thực hiện **one-way TLS server authentication**. Nó **không chứng minh** server xác thực client theo mTLS. Muốn mTLS, cần bật `needClientAuth` và chuẩn bị cả client key material/server trust policy thích hợp.

### 13.4. JSSE debug

Trong **môi trường kiểm thử**, có thể bật:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager \
  ManagedTrustChainLab \
  server-identity.p12 managed-trust.p12 wrong-trust.p12
~~~

Chú ý:

- Debug chỉ có giá trị nếu chương trình dùng JSSE và các managers đang kiểm tra.
- Logs có thể rất lớn, chứa subjects, chain, endpoints, certificate details và paths; không bật thường trực ở production.
- Phân biệt **handshake certificate processing** với **application data**; không cố log private keys.
- Đọc đúng bước fail: path building, algorithm constraints, hostname, client authentication hay timeout.
- Khi thêm debug, stdout của lab vẫn có các dòng xác định, nhưng JSSE diagnostic logging có thể xuất thêm dòng trên stderr. Đừng kỳ vọng toàn bộ console output giống phần `10.2`.

### 13.5. Security properties cũng tác động

JDK có các policies như:

~~~text
jdk.certpath.disabledAlgorithms
jdk.tls.disabledAlgorithms
~~~

Chúng có thể làm một chain không hợp lệ dù truststore chứa root đúng. Khi nâng JDK, đừng chỉ kiểm tra nội dung `.p12`; cần test TLS thực tế theo runtime mới.

**Không** tháo bỏ disabledAlgorithms chỉ để ép giao thức/chữ ký yếu chạy tiếp. Cách đúng là thay certificates, algorithms hoặc endpoints phù hợp security policy hiện hành.

## 14. Mẫu triển khai managed truststore trong ứng dụng

### 14.1. Load tường minh qua Java API

Trong ứng dụng production, một cách kiểm soát rõ ràng là nạp file truststore theo cấu hình, xác thực trước khi init SSLContext:

~~~java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(trustPath)) {
    trust.load(in, trustPassword);
}

TrustManagerFactory factory = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
factory.init(trust);

SSLContext tls = SSLContext.getInstance("TLS");
tls.init(null, factory.getTrustManagers(), null);
~~~

Đây là **snippet minh họa**, các biến `trustPath`/`trustPassword` đến từ nguồn cấu hình an toàn và cần xử lý exceptions. Chương trình lab `ManagedTrustChainLab` có phiên bản đầy đủ đã được chạy.

Điểm mạnh:

- Biết chính xác truststore nào tạo managers.
- Có thể kiểm tra certificate aliases/fingerprints trước khi cho app phục vụ traffic.
- Không phải phụ thuộc hoàn toàn vào default JSSE properties.
- Dễ viết unit/integration tests cho CA đúng/sai.

Nhưng **SSLContext này không tự có cơ chế file watcher/reload định kỳ**. Cần thiết kế reload, session lifecycle và failure handling nếu ứng dụng có CA rotation không restart.

### 14.2. Dùng JSSE system properties theo framework

Một client dựa vào default JSSE có thể dùng:

~~~text
-Djavax.net.ssl.trustStore=/run/secrets/managed-trust.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Password không nên hiện trong command line. JSSE có property `javax.net.ssl.trustStorePassword`, nhưng cách đưa password vào runtime phải bảo vệ nó khỏi process arguments, configs thế giới có thể đọc và CI logs.

Frameworks như HTTP clients, application servers và service meshes có thể tạo context/TrustManager riêng; **system property không nhất thiết ảnh hưởng SSLContext đã được tạo tường minh**. Xác nhận bằng chính framework configuration và handshake tests.

### 14.3. Vì sao password không phải là biện pháp bảo mật duy nhất?

Truststore chứa public certificates thường không có private key, nhưng password/integrity protection vẫn có ý nghĩa tùy provider/format. Điều quan trọng hơn là:

- Không cho process ngoài quyền sửa file.
- Artifact được phát hành từ CI/secret store có kiểm soát.
- Có checksum/signature và audit trail.
- Root CA additions/removals được phê duyệt.
- Không mount read-write từ một thư mục không đáng tin.

Nếu attacker có quyền chèn một root CA giả vào truststore đang được JVM sử dụng, client có thể chấp nhận các certificates do root đó ký. Truststore public nhưng **quyền sửa truststore là quyền bảo mật rất lớn**.

## 15. Quy trình quản lý vòng đời truststore

### 15.1. Inventory và source of truth

Tổ chức nên duy trì một manifest cho mỗi bộ trust anchors:

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| Artifact | `payments-trust-v4.p12` | Bản đang phát hành. |
| Owner | PKI/security team | Ai duyệt changes. |
| Environment/scope | staging/prod, nhóm service | Giới hạn áp dụng. |
| CA alias | `corp-root-2026` | Dễ theo dõi identity trong store. |
| Subject/issuer | Theo certificate | Metadata tham khảo. |
| SHA-256 fingerprint | Giá trị đã xác minh qua PKI source | Đối chiếu không nhầm CA. |
| NotBefore/NotAfter | Theo certificate | Thời gian hiệu lực. |
| Reason | CA rotation/incident/new environment | Audit. |
| Approver/ticket | Change record | Truy vết. |
| Rollback artifact | Phiên bản được phép quay lại | Khôi phục có kiểm soát. |

**Không** dùng CN/subject name làm khóa định danh tin cậy duy nhất; hai certificates khác nhau có thể cùng tên. Fingerprint/public key và nguồn phê duyệt cần được đối chiếu.

### 15.2. Khi onboarding một CA mới

1. Xác định **service cần tin** và threat model.
2. Thu CA public certificate qua nguồn quản trị đáng tin.
3. Kiểm tra SHA-256 fingerprint qua kênh độc lập.
4. Kiểm tra BasicConstraints, KU, validity và policy.
5. Xác định root/intermediate/leaf trust model được phép.
6. Xem **các CAs đã có**; tránh import quá mức hoặc duplicates không cần.
7. Đưa CA vào truststore được version trong CI/secure process.
8. Chạy negative tests với wrong CA/hostname/expired/constraints.
9. Triển khai staging, chạy handshake từ đúng Java image.
10. Phê duyệt rollout production theo deployment process.

**Không** dùng `-noprompt` để bỏ qua xác minh CA chưa được duyệt. Trong lab, `-noprompt` chỉ giúp reproducible sau khi biết CA là chính mình tạo.

### 15.3. Root CA rotation với overlap

Ví dụ root CA nội bộ sắp được thay:

~~~text
Stage A: managed truststore contains OLD root.
Stage B: after approval, contains OLD + NEW roots.
Stage C: server chain begins using NEW root.
Stage D: validate all clients and server chains.
Stage E: retire OLD root after migration and safety review.
~~~

Không xóa root cũ trước khi mọi endpoints/certs đã được chuyển đổi theo kế hoạch; cũng không giữ root đã bị compromise chỉ vì sợ outage. Với **compromise incident**, chính sách thu hồi có thể yêu cầu phản ứng khẩn cấp khác với rotation định kỳ.

Khi overlap, tổng số CA được tin tăng tạm thời; đây là quyết định bảo mật cần phê duyệt và có ngày kết thúc, không phải mặc định tin cậy vô thời hạn.

### 15.4. Runtime reload và TLS session lifecycle

Đổi file `managed-trust.p12` trên disk **không đồng nghĩa** những SSLContext/TrustManager instances đang hoạt động sẽ tự thay.

Các hệ thống thường chọn một trong các chiến lược:

- Restart/redeploy app với truststore mới.
- Framework-specific SSLContext/TrustManager reload.
- Tạo context mới có kiểm tra và chuyển traffic theo policy.

Sau khi reload/restart, kiểm tra **full new handshake** với anchor mới và anchor bị bỏ, tránh kết luận từ một connection hoặc TLS session đã tái sử dụng.

### 15.5. Rollback và quan sát

Theo dõi:

- Số lượng/tỷ lệ TLS handshake failures theo endpoint.
- Phân loại trust path errors, SAN errors, expired certs, algorithm policy failures.
- Deadline CA/certificate expiry.
- Sai lệch truststore version/hash giữa các pod/instances.
- Tỷ lệ traffic dùng versions cũ trong rollout.
- Sự khác biệt JDK vendor, JSSE provider, container image.

Khi rollback, xác định nguyên nhân trước: một bản truststore cũ có thể chứa CA bị thu hồi và không được phép khôi phục vì lý do bảo mật.

## 16. Docker/Kubernetes: “file đã mount” chưa chắc đã được JVM dùng

Các điểm cần kiểm tra:

- Secret/config volume chứa đúng file `.p12`.
- Đường dẫn bên trong container trùng với config.
- JVM user có quyền đọc file và directory.
- File không bị ghi đè sau khi SSLContext đã khởi tạo mà app không reload.
- Init process không nạp truststore trước khi mount sẵn sàng.
- Cả server identity và client truststore dùng đúng version/ownership.
- Không trộn JDK `cacerts` không kiểm soát với app-managed root set.

**Sơ đồ:**

~~~text
Versioned PKI trust artifact
           |
       CI security checks
           |
      Config/Secret distribution
           |
    /run/secrets/app-trust.p12
           |
      Java service startup
           |
      KeyStore.load(PKCS12)
           |
      TrustManagerFactory
           |
      SSLContext / TLS client
           |
      Handshake + SAN/PKIX checks
~~~

**Khuyến nghị:** thực hiện startup validation và có error message rõ nếu file không tồn tại, sai format/password hoặc không có trust anchors bắt buộc. Fail closed tốt hơn tự bật trust-all.

### 16.1. Truststore không nên “tự cập nhật từ kết nối lỗi”

Một hệ thống có thể bắt được `SSLHandshakeException` rồi tải server certificate và import vào truststore. Nếu không xác minh nguồn, đó chính là cơ hội để một kẻ tấn công chèn root/leaf giả trong lúc MITM.

Không dùng cơ chế trust-on-first-use cho service quan trọng nếu chưa có threat model/policy chấp nhận nó. Với CA nội bộ, nguồn tin cậy phải là PKI registry hoặc kênh quản trị đã xác thực.

### 16.2. Không để password thử nghiệm trong startup args

Trong lab, `LAB_STORE_PASSWORD` và `-storepass` được dùng để tiết kiệm thao tác. Production không nên:

~~~text
-Djavax.net.ssl.trustStorePassword=actual-secret
keytool -storepass actual-secret
~~~

trong logs, scripts commit lên Git hoặc process args quan sát được. Dùng hệ thống secrets phù hợp và phân quyền file/keystore. **Environment variables** cũng cần threat model; không phải một secret store tuyệt đối an toàn.

## 17. Một số biến thể chứng thư cần cân nhắc

### 17.1. Public CA trust và CA nội bộ

Ứng dụng gọi website công khai có thể dùng root certificates từ JDK `cacerts`. Nhưng service nội bộ dùng CA riêng cần bổ sung theo chính sách.

Nếu chọn **managed truststore riêng**, xác định tập CAs mong muốn một cách minh bạch; không assume JDK roots tự hợp nhất. Nếu áp composite trust managers, cần thiết kế và test kỹ scope/precedence và không làm điều kiện “chấp nhận nếu bất kỳ trust manager nào vô tình cho qua” trở thành bypass security policy.

### 17.2. Leaf pinning hoặc public key pinning

Pinning giới hạn trust vào certificate/public key cụ thể, tạo thêm constraints so với tin CA rộng. Nhưng:

- Khó rotation nếu thay key/certificate.
- Cần backup pins hoặc rollout process.
- Nếu pin leaf, thay leaf thường xuyên có thể gây outage.
- Pinning không đồng nghĩa một cách mặc định với `List` các CA trong PKCS12.

Khi không có yêu cầu cụ thể, bài lab dùng root CA anchor, dễ hiểu và phù hợp PKIX.

### 17.3. mTLS là bài toán hai phía

Ở **mTLS**:

- Client giữ private key/certificate chain của mình.
- Server có truststore để xác minh CA của client.
- Client vẫn có truststore để xác minh server.
- Server phải bật client authentication đúng cách.

Bài lab **không bật mTLS**, chỉ xác minh server. Đừng hiểu kết quả `validRootAndChain=ACCEPTED` thành “server cũng đã xác thực danh tính client”.

### 17.4. Revoked và expired certificates

Một truststore chứa đúng root không chứng minh một leaf cert chưa expired hoặc chưa revoked. Certificate path validation và revocation policies là các tầng khác nhau. Đối với nghiệp vụ yêu cầu kiểm tra thu hồi, phải chủ động cấu hình và kiểm thử theo JDK/provider, OCSP/CRL availability và chính sách fail-open/fail-closed.

**Không** thay đổi đồng hồ hệ thống production để test expired/not-yet-valid cert. Dùng test certificates với validity được lập sẵn trong môi trường lab kiểm soát.

## 18. Bảng lỗi thường gặp

| Hiện tượng | Khả năng | Cách kiểm tra đúng |
| --- | --- | --- |
| `PKIX path building failed` | Không xây được path tới trust anchor đúng. | Xem chain thực tế server gửi, root trong truststore, intermediate và provider. |
| Root có trong `cacerts` nhưng app vẫn fail | App đang dùng explicit truststore riêng không có root đó. | Kiểm tra `SSLContext`/`TrustManagerFactory` thực tế. |
| Truststore path sai trong container | Empty truststore/fail startup tùy provider. | Kiểm tra mounts, path, type, permissions trước handshake. |
| Đúng root nhưng thiếu intermediate | Path building thiếu mắt xích. | Sửa server chain; không tự import CA chưa kiểm. |
| SAN không chứa hostname | Endpoint identification fail. | Cấp lại certificate đúng SAN hoặc dùng đúng endpoint. |
| Certificate expired | Validity check fail. | Rotation certificate, kiểm tra thời gian tin cậy. |
| Algorithm constraints fail | Thuật toán/chữ ký/key size không đáp ứng policy. | Cấp lại certificates theo JDK policy hiện hành. |
| Truststore bị thêm CA lạ | Trust expansion không phê duyệt. | Kiểm tra manifest, fingerprint, audit và incident response. |
| Khi thay truststore app vẫn tin CA cũ | SSLContext/session cache chưa reload. | Restart/reinit context, kiểm tra new full handshake. |
| TLS thành công nhưng API báo 403 | Authorization nghiệp vụ từ chối. | Không đổ lỗi cho truststore; xem quyền principal/resource. |
| Server không có PrivateKeyEntry | Không trình được identity phù hợp. | Kiểm tra server identity keystore, alias và key passwords. |
| CA private key bị sao chép vào client | Rủi ro PKI nghiêm trọng. | Chỉ phân phối public CA certificate; xử lý sự cố nếu lộ. |
| `UnrecoverableKeyException` | Key/password/format hoặc provider không khớp. | Kiểm tra protected key entries, không hạ security policy. |
| New root rollout bị outage | Chuyển server chain quá sớm hoặc clients chưa update. | Version kiểm soát, overlap plan, rollout tests. |
| Negative wrongRoot lại ACCEPTED | Trust-all, context nhầm hoặc root set quá rộng. | Fail deployment, điều tra managers/properties. |
| Negative hostname lại ACCEPTED | Hostname checking bị tắt hoặc socket tạo sai peer name. | Bật HTTPS endpoint identification, kiểm tra SAN/expectedName. |

## 19. Phản mẫu cần tránh

| Phản mẫu | Vì sao sai |
| --- | --- |
| “Có file `trust.p12` là TLS an toàn.” | Phải xác định trust anchors và managers thực sự dùng. |
| “Chứng thư có chữ ROOT trong CN là CA đáng tin.” | Trust do chính sách, không do tên Subject. |
| “Server gửi root cert nghĩa client phải tin root.” | Root phải được client cho phép trước. |
| “Chỉ kiểm tra issuer name trùng là đủ.” | Cần kiểm tra public-key signature/path/constraints. |
| “Truststore phải có private key của root.” | Xác minh dùng public CA certificate. |
| “Cứ import leaf server khi gặp PKIX error.” | Có thể mở trust không kiểm soát và khó rotation. |
| “Tự tắt hostname verification vì chain đã đúng.” | Mất xác minh danh tính endpoint. |
| “Tự tạo TrustManager rỗng chấp nhận mọi server.” | Phá hủy TLS peer authentication. |
| “`-Djavax.net.ssl.trustStore` luôn cộng với JDK `cacerts`.” | SunJSSE explicit store thường thay default trust material. |
| “File truststore không tồn tại nên Java chắc dùng `cacerts`.” | Với explicit path sai, SunJSSE có thể dùng empty store. |
| “Có root CA đúng thì thiếu intermediate không sao.” | Không phải mọi client tự tìm được intermediate. |
| “TLS thành công nghĩa revocation được kiểm tra.” | SunJSSE default PKIX init(KeyStore) không bật revocation check. |
| “PKCS12 là private-key store, JKS là truststore.” | Format không quyết định vai trò. PKCS12 được dùng cho cả hai. |
| “Root CA từ Java 10 là danh sách cố định mãi mãi.” | JDK vendor/update có thể thay root program. |
| “Thay file truststore là contexts cũ tự nhận.” | Cần reload/restart theo framework, kiểm tra sessions. |
| “Wrong-root negative test chỉ làm mất thời gian.” | Nó phát hiện trust-all hoặc cấu hình trust mở quá mức. |
| “Thấy `SSLException` bất kỳ là đã test PKIX đúng.” | Cần positive control và chẩn đoán đúng cause. |
| “Dùng mật khẩu lab trong shell production cũng được.” | Process args/history/logs có thể lộ, thiếu secret management. |
| “Tin đúng CA nghĩa luôn có quyền ứng dụng.” | TLS identity và application authorization khác nhau. |
| “Cứ giữ CA cũ vô thời hạn để tránh lỗi.” | Trust anchors lỗi thời/compromised cần policy thu hồi. |

## 20. Bài tập có đáp án

### Câu 1 — Trust anchor

**Hỏi:** Server trình chuỗi hợp lệ về chữ ký tới root CA R, nhưng client chỉ tin root CA S. Có phải ACCEPTED?

**Đáp án:** **Không** theo chính sách root-only của bài lab. Root R không là trust anchor của client, nên test `wrongRoot` phải **REJECTED**.

### Câu 2 — Intermediate bị thiếu

**Hỏi:** Client đã có root R. Server chỉ gửi leaf do intermediate I ký nhưng client không có I. Có thể fail không?

**Đáp án:** Có. Path builder thiếu chứng thư intermediate. Một số client có thể tìm từ nguồn khác; server nên gửi intermediate cần thiết để không phụ thuộc vào cache/AIA.

### Câu 3 — Hostname sai

**Hỏi:** Root CA đúng nhưng SAN chỉ có `127.0.0.1`, client xác minh `wrong.example.invalid`. Kết quả?

**Đáp án:** **REJECTED** khi bật HTTPS endpoint identification; path đúng không thay thế tên đúng.

### Câu 4 — Có cần root private key trong client không?

**Đáp án:** **Không**. Client dùng root **public certificate** để làm trust anchor; root private key phải bảo mật tại CA.

### Câu 5 — Vì sao `chain.issuerMatches=true` chưa đủ?

**Đáp án:** Vì chỉ so DN Issuer/Subject, không kiểm tra chữ ký, public key hay path policies. Handshake PKIX mới thực hiện xác thực thực chất.

### Câu 6 — Root có trong `cacerts` nhưng ứng dụng không tin?

**Đáp án:** Có thể vì ứng dụng dùng `javax.net.ssl.trustStore` riêng, hoặc SSLContext custom; phải xác định trust material đang được sử dụng.

### Câu 7 — Truststore path không tồn tại

**Đáp án:** Trong SunJSSE, explicit path sai có thể khiến default trust manager sử dụng empty truststore; không assume fallback `cacerts`.

### Câu 8 — Managed nghĩa là gì?

**Đáp án:** Root CAs có nguồn gốc được phê duyệt, fingerprint đã kiểm tra, scope, version, permission, audit, rotation, test và rollback; không phải đặt tên file “managed” là xong.

### Câu 9 — Vì sao không nhập server identity PKCS12 vào client?

**Đáp án:** Nó chứa **server private key**; client không cần bí mật đó. Chỉ nhập đúng CA public certificate/trust anchor được phê duyệt.

### Câu 10 — Java 10 có JEP nào liên quan truststore?

**Đáp án:** **JEP 319 Root Certificates**, giúp OpenJDK có tập root CAs mặc định. Danh sách root CAs phụ thuộc bản JDK hiện hành.

### Câu 11 — Có bắt buộc gửi root certificate trong handshake?

**Đáp án:** Không. Server thường gửi leaf + intermediates; root thường đã có trong truststore client.

### Câu 12 — App thay truststore trên disk nhưng kết nối mới vẫn dùng CAs cũ?

**Đáp án:** Có thể SSLContext/TrustManagers đã được khởi tạo trước thay đổi. Xem reload/restart và session resumption behavior.

### Câu 13 — `SSLContext.init(null, tmf.getTrustManagers(), null)` có tắt xác thực server không?

**Đáp án:** Không. Tham số key managers `null` nghĩa không cấp local identity managers theo lời gọi; trust managers vẫn xác minh peer.

### Câu 14 — Chỉ test positive đủ chưa?

**Đáp án:** Không. Thêm negative wrongRoot, wrongHostname và missingIntermediate để phát hiện cấu hình tin cậy quá rộng hoặc tắt checks.

### Câu 15 — Revocation chắc chắn bật nếu PKIX handshake thành công?

**Đáp án:** Không. SunJSSE PKIX `TrustManagerFactory.init(KeyStore)` mặc định không bật revocation check; phải cấu hình theo chính sách nếu cần.

### Câu 16 — Đặt root CA tự ký trong truststore có tự an toàn không?

**Đáp án:** Không. Root phải được xác minh nguồn/fingerprint và có chính sách phê duyệt; self-signed không tự mang niềm tin.

### Câu 17 — Server certificate hết hạn nhưng root chưa hết hạn

**Đáp án:** TLS client có thể từ chối vì validity của leaf; root đúng không bỏ qua expired leaf.

### Câu 18 — TLS thành công nhưng API trả `403 Forbidden`

**Đáp án:** Đây có thể là lỗi authorization ở tầng ứng dụng; không tự kết luận truststore hay CA sai.

### Câu 19 — Có nên copy global `cacerts` vào từng container?

**Đáp án:** Không phải mặc định. Tập CAs cần được quản trị theo scope, provenance, vendor/update và image policy. Nếu kết hợp public+private roots, phải làm có chủ đích và test.

### Câu 20 — Intermediate `CA=true,pathlen:0` ký leaf có hợp lệ không?

**Đáp án:** Về ý nghĩa BasicConstraints, pathlen 0 hạn chế subordinate CA bên dưới, không cấm cấp leaf certificate. Vẫn phải đáp ứng chữ ký, KU, policies và các quy tắc khác.

## 21. Checklist trước khi deploy

- [ ] Tôi biết **JDK vendor/build**, JSSE provider, TLS framework và source configuration.
- [ ] Tôi phân biệt identity keystore của server và managed truststore của client.
- [ ] Tôi chỉ tin các root CA public certificates được PKI/security phê duyệt.
- [ ] Tôi đã kiểm tra SHA-256 fingerprint từ nguồn độc lập.
- [ ] Tôi ghi lại root alias, validity, owner, scope và artifact version.
- [ ] Tôi không đưa CA private key vào truststore client.
- [ ] Tôi xác minh server leaf SAN khớp hostname/IP thực tế.
- [ ] Tôi xác minh server gửi đủ intermediate chain cần thiết.
- [ ] Tôi không coi server gửi root certificate là làm root đó đáng tin.
- [ ] Tôi kiểm tra BasicConstraints, KeyUsage, ExtendedKeyUsage và thuật toán.
- [ ] Tôi xác định chính sách OCSP/CRL/revocation, không giả định mặc định bật.
- [ ] Tôi đã chạy positive TLS handshake với đúng managed root.
- [ ] Tôi đã chạy negative truststore **wrong root**.
- [ ] Tôi đã chạy negative **wrong hostname**.
- [ ] Tôi đã kiểm tra hành vi khi **missing intermediate**.
- [ ] Tôi không sửa lỗi bằng TrustManager trust-all hay bỏ qua hostname.
- [ ] Tôi biết JSSE default tìm `jssecacerts`/`cacerts` thế nào.
- [ ] Tôi không giả định custom `javax.net.ssl.trustStore` tự hợp nhất với `cacerts`.
- [ ] Tôi fail-fast khi truststore path/type/password không đúng.
- [ ] Tôi không lưu mật khẩu/key material trong Git hoặc logs.
- [ ] Tôi mount truststore read-only, kiểm tra ownership/ACL và checksums.
- [ ] Tôi xác nhận framework thực sự dùng SSLContext/TrustManager đã cấu hình.
- [ ] Tôi có CA rotation plan với overlap và ngày thu hồi old anchor.
- [ ] Tôi kiểm tra reload/restart và full new handshake sau thay đổi.
- [ ] Tôi có monitoring certificate expiry, TLS errors và truststore versions.
- [ ] Tôi có rollback policy **không** khôi phục CA đã bị compromise.
- [ ] Tôi phân biệt TLS trust với mTLS và application authorization.
- [ ] Tôi chỉ chạy lab CA private keys ở môi trường cô lập, không trong production.
- [ ] Tôi dùng Java 17+ cho chương trình lab và không bật lại TLS/algorithms legacy.

## 22. Tài liệu tham khảo còn áp dụng

1. [Oracle Java SE 25 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): trust managers, default stores, explicit `javax.net.ssl.trustStore`, endpoint identification và PKIX revocation defaults.
2. [Oracle Java SE 25 — Java PKI Programmer’s Guide](https://docs.oracle.com/en/java/javase/25/security/java-pki-programmers-guide.html): `TrustAnchor`, PKIX certificate path building và validation.
3. [Oracle Java SE 25 — keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html): `-genkeypair`, `-certreq`, `-gencert`, `-exportcert`, `-importcert`, extensions và PKCS12.
4. [Oracle Java SE 25 — KeyStore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyStore.html): PrivateKeyEntry/TrustedCertificateEntry và `KeyStore.getInstance("PKCS12")`.
5. [Oracle Java SE 25 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): trust manager initialization.
6. [Oracle Java SE 25 — SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): HTTPS endpoint identification.
7. [Oracle Java SE 25 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): TLS peer certificate verification trong socket/engine context.
8. [Oracle Java SE 25 — CertPathValidator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/CertPathValidator.html): PKIX algorithm, revocation checker options.
9. [Oracle Java SE 25 — TrustAnchor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/TrustAnchor.html): root of trust.
10. [OpenJDK JEP 319 — Root Certificates](https://openjdk.org/jeps/319): mốc root CA certificates có trong OpenJDK từ Java 10.
11. [RFC 5280 — Internet X.509 Public Key Infrastructure](https://www.rfc-editor.org/rfc/rfc5280): path validation, constraints, signature, X.509 CA model.
12. [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS protocol/handshake hiện đại.
13. [Oracle Java SE 25 — java Command and Security Properties](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-D` system properties và môi trường JVM.
14. [Oracle Java SE 25 — CertPathBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/cert/CertPathBuilder.html): xây certification paths.

**Kết luận:** Kiểm tra TLS trust đúng cách là **xác minh chuỗi chứng thư tới trust anchor đã được quản lý**, **xác minh tên/IP endpoint**, và áp dụng **certificate/path constraints** theo JSSE/PKIX cùng security policy của runtime. Một managed PKCS12 truststore phải chứa đúng CA public certificates được phê duyệt, có fingerprint, version, quyền đọc/ghi, rotation và tests. Bài lab đã chứng minh bằng handshake thật rằng **chuỗi Root → Intermediate → Server được chấp nhận khi root đúng và SAN đúng**, còn **root sai, hostname sai hoặc thiếu intermediate đều bị từ chối**. Không bỏ qua xác thực để “cho TLS chạy”, không gửi CA private key cho client, và không coi việc có file `truststore.p12` là bằng chứng hệ thống đã an toàn.