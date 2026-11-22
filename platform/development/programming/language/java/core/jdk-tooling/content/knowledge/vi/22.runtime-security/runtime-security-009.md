# Audit bảo mật runtime Java

**Audit bảo mật runtime** là quá trình kiểm tra JDK/JRE đang chạy ứng dụng, cấu hình bảo mật, dependency, chứng chỉ, kết nối mạng, tham số JVM, quyền hệ điều hành và bằng chứng vận hành. Mục tiêu là xác định điểm yếu có thể khai thác trong môi trường thực tế, đánh giá mức độ ảnh hưởng và đưa ra hành động khắc phục có thể xác minh.

Một ứng dụng Java an toàn không chỉ phụ thuộc vào mã nguồn. Cùng một JAR có thể có mức rủi ro rất khác nhau tùy JDK đang dùng, security providers, truststore, TLS configuration, JVM flags, quyền của process, secret management và cách triển khai trên máy chủ hoặc container.

Bài học này dùng các công cụ có sẵn trong JDK 17 trở lên, với ghi chú riêng cho thay đổi quan trọng từ JDK 24. Các lệnh kiểm tra là bước thu thập bằng chứng; chúng không thay thế kiểm thử xâm nhập, đánh giá kiến trúc hoặc rà soát chính sách của tổ chức.

## 1. Phạm vi của một runtime security audit

Một cuộc audit nên bao gồm cả cấu hình Java và môi trường bao quanh JVM.

| Phạm vi | Câu hỏi cần trả lời | Bằng chứng tiêu biểu |
|---|---|---|
| JDK/runtime | Đang chạy vendor, version và patch level nào? Có còn được hỗ trợ không? | java --version, image/package metadata |
| Security properties | Thuật toán yếu, protocol cũ hoặc provider không mong muốn có được bật không? | java -XshowSettings:security |
| Dependency | Có thư viện lỗi thời, API nội bộ hoặc dependency không rõ nguồn gốc không? | SBOM, SCA report, jdeps |
| Artifact | JAR có chữ ký hợp lệ, entry chưa ký hoặc signer không đáng tin không? | jarsigner -verify |
| Certificate/keystore | Certificate còn hạn, đúng mục đích và chain có được tin cậy không? | keytool, certificate inventory |
| TLS/network | Endpoint thực tế dùng TLS nào, hostname validation và trust có đúng không? | JSSE config, endpoint scan, handshake evidence |
| JVM process | Có agent, debug port, module override hoặc system property nhạy cảm không? | jcmd, process/service configuration |
| OS/container | Process có chạy bằng quyền tối thiểu và chỉ truy cập tài nguyên cần thiết không? | OS identity, filesystem/network policy |
| Secrets | Password, token, private key có bị lộ trong args, env, log hoặc dump không? | Secret inventory, log review |
| Logging/response | Có audit trail và quy trình xử lý sự cố không? | Log policy, alert, incident runbook |

Nên xác định trước phạm vi hệ thống: môi trường production, staging hay development; các service, JAR, plugin, native library và runtime image nào được triển khai; phiên bản Java tối thiểu cần hỗ trợ; và ai chịu trách nhiệm xử lý từng finding.

Không thu thập dữ liệu nhạy cảm không cần thiết. Đầu ra như JVM command line, system properties, environment variables, heap dump và thread dump có thể chứa thông tin bí mật hoặc dữ liệu người dùng. Giới hạn người được truy cập và che dữ liệu trước khi đưa vào ticket hoặc báo cáo.

## 2. Kiểm tra JDK và runtime đang chạy

Bắt đầu bằng việc xác định chính xác runtime. Đừng chỉ ghi “Java 17” hoặc “Java 24”; cần lưu vendor, build number, architecture và nơi cài đặt.

~~~bash
java --version
javac --version
jcmd -l
~~~

Ý nghĩa:

- java --version hiển thị JDK/JRE đang được launcher gọi.
- javac --version xác nhận compiler nếu máy có JDK đầy đủ.
- jcmd -l liệt kê các JVM process cục bộ mà tài khoản hiện tại có thể quan sát.

Một máy có thể cài nhiều JDK. Lệnh java trong PATH chưa chắc là runtime được service production sử dụng. Hãy kiểm tra service unit, Windows service, container image, startup script và biến JAVA_HOME của đúng process.

### Những thông tin cần ghi lại

- JDK vendor và version đầy đủ.
- Build number và ngày phát hành.
- Kiến trúc CPU và hệ điều hành.
- Nguồn cài đặt: package manager, container base image, archive hay image nội bộ.
- Ngày cập nhật bảo mật gần nhất.
- Ngày kết thúc hỗ trợ của vendor.
- Các JDK khác nhau giữa build, test, staging và production.

Không dùng JDK chỉ vì phiên bản mới nhất có sẵn. Chọn release được vendor hỗ trợ, đáp ứng chính sách cập nhật và đã được kiểm thử với ứng dụng. Đồng thời lập lịch cập nhật security patch định kỳ và quy trình xử lý bản vá khẩn cấp.

### Kiểm tra runtime image

Nếu ứng dụng chạy bằng runtime image tạo từ jlink, hãy xác định image được tạo từ JDK nào và module nào được đóng gói. Runtime image tối giản giúp giảm thành phần không cần thiết, nhưng không tự đảm bảo bảo mật. Vẫn phải cập nhật image khi có security fix và kiểm tra dependency động, provider, locale data, TLS support cùng các thành phần thực sự cần dùng.

## 3. Kiểm tra security properties và providers

Java Security Architecture sử dụng security properties để cấu hình provider, thuật toán, keystore mặc định, TLS và các cơ chế bảo mật khác. Cấu hình thực tế có thể khác giữa các vendor, bản phát hành và file override.

### In cấu hình bảo mật đang hoạt động

JDK 17 trở lên hỗ trợ các dạng sau:

~~~bash
java -XshowSettings:security -version
java -XshowSettings:security:properties -version
java -XshowSettings:security:providers -version
java -XshowSettings:security:tls -version
~~~

Các dạng cụ thể:

- security:properties hiển thị security properties đang có hiệu lực.
- security:providers hiển thị provider và thứ tự ưu tiên.
- security:tls hiển thị TLS configuration của provider JSSE.
- security in ra các nhóm thông tin bảo mật tổng hợp.

Đây là lệnh chẩn đoán. Output có thể dài và khác theo JDK/vendor; hãy lưu kết quả cùng version runtime và kiểm soát quyền truy cập.

### Security properties cần chú ý

| Property | Mục đích audit |
|---|---|
| jdk.tls.disabledAlgorithms | Protocol, cipher suite, key exchange hoặc thuật toán TLS không được phép thương lượng |
| jdk.certpath.disabledAlgorithms | Thuật toán/key size bị hạn chế khi xác thực certificate path |
| jdk.jar.disabledAlgorithms | Thuật toán không được chấp nhận khi xác minh signed JAR |
| jdk.security.legacyAlgorithms | Thuật toán yếu hoặc cũ được phân loại legacy |
| security.provider.n | Provider mật mã và thứ tự tìm implementation |
| keystore.type | Loại keystore mặc định |
| ssl.KeyManagerFactory.algorithm | Thuật toán KeyManagerFactory mặc định |
| ssl.TrustManagerFactory.algorithm | Thuật toán TrustManagerFactory mặc định |
| securerandom.source | Nguồn entropy được cấu hình cho SecureRandom |
| jdk.tls.keyLimits | Giới hạn dữ liệu mã hóa theo một bộ khóa TLS |

Không chỉ tìm xem một property có tồn tại hay không. Hãy so sánh giá trị đang hoạt động với baseline của tổ chức, JDK vendor và yêu cầu tương thích. Một property có thể bị thay đổi bởi file cấu hình tùy chỉnh, tham số startup hoặc security provider khác.

### Kiểm tra file cấu hình và override

Trên JDK hiện đại, master security properties file thường nằm trong:

~~~text
<java-home>/conf/security/java.security
~~~

Kiểm tra file đang thuộc runtime được triển khai và mọi file bổ sung được nạp qua cấu hình. Tìm các tham số startup liên quan đến:

~~~text
-Djava.security.properties=...
-Djava.security.properties==...
~~~

Dạng một dấu bằng dùng file bổ sung theo cơ chế cấu hình của JDK; dạng hai dấu bằng yêu cầu thay thế master security properties file. Cần xem xét kỹ mọi override vì nó có thể thay đổi provider, algorithm constraints hoặc TLS behavior. Không sửa trực tiếp file mặc định mà không có quản lý cấu hình, review và kiểm thử tương thích.

### Kiểm tra provider

Provider là implementation của các dịch vụ mật mã như Signature, MessageDigest, Cipher, KeyStore, SecureRandom và TLS. Audit cần xác nhận:

- Provider có nguồn gốc và version được phê duyệt.
- Thứ tự provider đúng với thiết kế.
- Không có provider lạ được thêm qua startup option hoặc file security.
- Provider native/HSM/PKCS#11 được cấu hình và bảo vệ đúng.
- Các thuật toán quan trọng thực sự có implementation tương thích.
- Việc cập nhật provider có quy trình kiểm thử và rollback.

Không tự động xóa provider chỉ vì tên không quen thuộc. Một số provider là thành phần chuẩn của JDK hoặc phục vụ smart card, HSM, LDAP, Kerberos và TLS.

## 4. Thay đổi lớn từ JDK 24: Security Manager đã bị vô hiệu hóa

Security Manager từng được dùng để giới hạn một số thao tác của mã Java thông qua permission checks. Nó đã bị deprecated for removal từ JDK 17 và **bị vô hiệu hóa vĩnh viễn từ JDK 24** theo JEP 486.

Điều này có ý nghĩa trực tiếp đối với audit:

- Không thể bật Security Manager khi khởi động JVM từ JDK 24.
- Không thể cài một custom Security Manager trong runtime.
- Các API liên quan có thể trả null/false, cho phép thao tác đi tiếp hoặc ném exception theo thay đổi của JDK.
- Các system/security properties chỉ phục vụ Security Manager không còn là cơ chế bảo vệ hiệu lực.
- File policy của Security Manager không còn là sandbox bảo vệ ứng dụng trong JDK 24.

Không xem cấu hình policy cũ là bằng chứng rằng ứng dụng đang bị giới hạn quyền. Nếu hệ thống từng dựa vào Security Manager để cô lập plugin hoặc mã không tin cậy, cần thiết kế lại ranh giới bảo mật.

### Cách cô lập thay thế

Dùng ranh giới ở cấp hệ điều hành hoặc hạ tầng:

- Chạy service bằng tài khoản riêng, không có quyền administrator/root.
- Giới hạn quyền đọc/ghi filesystem và chỉ cấp các thư mục cần thiết.
- Chạy trong container hoặc sandbox được cấu hình đúng; tránh privileged mode.
- Giới hạn network ingress/egress theo service và port cần dùng.
- Dùng seccomp, AppArmor, SELinux hoặc cơ chế tương đương khi nền tảng hỗ trợ.
- Tách plugin hoặc code không tin cậy sang process/container riêng.
- Giới hạn CPU, memory, file descriptor, process count và thời gian thực thi.
- Không dùng module system như một sandbox bảo mật cho mã không tin cậy.

Module boundaries và encapsulation giúp tổ chức API; chúng không thay thế OS access control. Nếu cần chạy mã không tin cậy, hãy thiết kế giao tiếp qua IPC với process được cô lập và cấp quyền tối thiểu.

## 5. Audit dependency và API nội bộ của JDK

Dependency là một phần của bề mặt tấn công. Một thư viện dễ bị khai thác có thể làm ứng dụng mất an toàn dù code của nhóm không có lỗi trực tiếp.

### Lập danh mục dependency

Thu thập:

- Direct và transitive dependencies.
- Version, checksum và nguồn repository.
- JAR được đóng gói trong ứng dụng hoặc plugin.
- Native libraries và thư viện được nạp lúc runtime.
- SBOM của artifact phát hành.
- Finding CVE từ công cụ Software Composition Analysis (SCA).
- License, provenance và chính sách cập nhật dependency.

jdeps phân tích quan hệ phụ thuộc tĩnh; nó không phải công cụ tìm CVE. Hãy kết hợp dependency inventory với SCA scanner, vulnerability database và quy trình theo dõi advisory của vendor.

### Tìm dependency đến JDK internal API

~~~bash
jdeps --jdk-internals app.jar
~~~

Lệnh này tìm class-level dependency đến JDK internal APIs. Theo help của jdeps, tùy chọn này không thể dùng cùng summary, package filter hoặc regex filter. Hãy chạy nó như một bước riêng.

Nếu ứng dụng dùng internal API, ưu tiên chuyển sang API Java SE được hỗ trợ. Các tham số như --add-exports hoặc --add-opens có thể làm mã truy cập package vốn được đóng; hãy ghi nhận từng trường hợp, owner, lý do và kế hoạch loại bỏ.

### Tìm API deprecated for removal

~~~bash
jdeprscan --release 24 --for-removal app.jar
~~~

Chọn release phù hợp với runtime mục tiêu. Chạy thêm scan đầy đủ nếu cần kiểm kê mọi API deprecated, vì --for-removal chỉ tập trung vào API được đánh dấu dự định loại bỏ.

### Hạn chế của phân tích tĩnh

jdeps và jdeprscan không thể nhìn thấy mọi dependency được tạo động qua reflection, plugin, configuration hoặc native code. Bổ sung kiểm tra runtime, tìm tên class trong cấu hình, rà soát ServiceLoader/plugin registry và test các profile triển khai thực tế.

## 6. Xác minh artifact và chữ ký số

Không đưa JAR không rõ nguồn gốc vào production chỉ vì nó tải được từ repository. Audit artifact cần kiểm tra checksum, nguồn tải, chữ ký, signer identity và certificate chain.

### Xác minh signed JAR

~~~bash
jarsigner -verify -strict -verbose -certs app.jar
~~~

- verify kiểm tra chữ ký và digest của JAR.
- verbose hiển thị trạng thái chi tiết theo entry.
- certs hiển thị thông tin certificate khi xác minh.
- strict khiến severe warning ảnh hưởng đến exit code.

Phải phân biệt chữ ký toán học hợp lệ với signer được tin cậy. JAR ký bằng chứng chỉ tự ký có thể có digest và signature hợp lệ nhưng vẫn không đáp ứng trust policy của tổ chức.

### Kiểm tra checksum và nguồn artifact

Tính SHA-256 bằng công cụ của hệ điều hành hoặc build pipeline rồi đối chiếu với checksum lấy từ kênh phát hành tin cậy. Checksum không thay thế chữ ký số; nó chỉ nhận diện bytes chính xác của artifact.

Ghi lại:

- Tên artifact và version.
- Repository hoặc nguồn phát hành.
- SHA-256 checksum.
- Signer certificate fingerprint.
- Subject, issuer và validity period.
- Kết quả jarsigner verify strict.
- JDK/vendor dùng để xác minh.
- Finding unsigned entry hoặc thuật toán bị vô hiệu hóa.

## 7. Audit keystore, truststore và certificate

Keystore thường lưu private key, secret key hoặc trusted certificate. Truststore chứa các certificate được chấp nhận làm trust anchor hoặc dùng trong quá trình xác thực peer.

### Liệt kê entry trong keystore

~~~bash
keytool -list -v -keystore app-keystore.p12 -storetype PKCS12
~~~

Keytool yêu cầu password tương tác nếu cần. Output verbose có thể hiển thị alias, entry type, Subject, Issuer, serial number, validity period, fingerprint và certificate extensions.

Đừng nhầm các loại entry:

- PrivateKeyEntry chứa private key và certificate chain.
- SecretKeyEntry chứa symmetric key.
- TrustedCertificateEntry chứa public certificate được tin cậy.

### Kiểm tra truststore mặc định

~~~bash
keytool -list -v -cacerts
~~~

Lệnh dùng truststore cacerts mặc định của runtime. Nếu ứng dụng cấu hình truststore riêng, phải kiểm tra đúng file đó thay vì chỉ kiểm tra cacerts.

### Kiểm tra certificate độc lập

~~~bash
keytool -printcert -file partner-ca.pem
~~~

Đối chiếu SHA-256 fingerprint với thông tin nhận qua kênh độc lập đáng tin cậy trước khi nhập một certificate làm trusted entry.

### Các điểm cần audit

- Alias có tên rõ ràng và owner chịu trách nhiệm.
- Private key có được bảo vệ bằng quyền file tối thiểu hoặc HSM/token.
- Certificate còn hiệu lực và đúng mục đích sử dụng.
- Subject Alternative Name khớp hostname/service.
- KeyUsage và ExtendedKeyUsage phù hợp với server/client/code signing.
- Certificate chain dẫn đến trust anchor được phê duyệt.
- Không còn CA cũ, certificate hết hạn hoặc entry không rõ nguồn gốc.
- Có lịch gia hạn, rotation và thu hồi certificate.
- Backup keystore được mã hóa, kiểm soát quyền và thử khôi phục.
- Password không nằm trong source, command history hoặc file cấu hình công khai.

Không xuất hoặc gửi private key để làm bằng chứng audit. Chỉ thu thập metadata và fingerprint cần thiết.

## 8. Audit TLS và cấu hình kết nối

Java Secure Socket Extension (JSSE) cung cấp TLS/DTLS, encryption, server authentication, message integrity và optional client authentication.

### Xem TLS configuration của JDK

~~~bash
keytool -showinfo -tls
java -XshowSettings:security:tls -version
~~~

Hai lệnh hiển thị protocol và cipher suites được bật trong cấu hình/provider hiện tại. Trên OpenJDK 24.0.2 đã kiểm tra, output cho thấy TLSv1.3 và TLSv1.2 được bật. Kết quả thực tế thay đổi theo vendor, version, provider và security properties.

Output này không chứng minh endpoint của ứng dụng đang thương lượng đúng các protocol đó. Ứng dụng có thể dùng SSLContext riêng, cấu hình SSLParameters, proxy hoặc TLS termination ở load balancer. Cần kiểm tra cả endpoint thực tế từ mạng và cấu hình của service.

### Security properties liên quan TLS

- jdk.tls.disabledAlgorithms: protocol/cipher/key exchange bị cấm trong TLS negotiation.
- jdk.certpath.disabledAlgorithms: giới hạn thuật toán trong certificate path validation.
- jdk.tls.legacyAlgorithms: thuật toán legacy không được ưu tiên thương lượng.
- ssl.TrustManagerFactory.algorithm: thuật toán TrustManagerFactory mặc định.
- ssl.KeyManagerFactory.algorithm: thuật toán KeyManagerFactory mặc định.

Oracle JSSE docs giải thích rằng disabled algorithms có thể ngăn thương lượng một protocol hoặc cipher suite ngay cả khi ứng dụng cố bật rõ ràng.

### Các kiểm tra TLS cần thực hiện

1. Endpoint chỉ hỗ trợ protocol được chính sách cho phép.
2. Không cho phép SSLv3, TLS 1.0 hoặc TLS 1.1 trong môi trường hiện đại.
3. Không dùng cipher suite yếu, NULL, anonymous hoặc key exchange không an toàn.
4. Certificate có SAN đúng hostname và còn hiệu lực.
5. Client kiểm tra hostname và certificate chain.
6. Không dùng TrustManager chấp nhận mọi certificate.
7. Không tắt hostname verification để xử lý lỗi kết nối.
8. Nếu dùng mutual TLS, xác minh cả client certificate và server certificate.
9. Kiểm tra certificate rotation, revocation policy và OCSP/CRL khi phù hợp.
10. Kiểm tra TLS termination tại reverse proxy/load balancer, không chỉ JVM phía sau.

### Tránh cấu hình trust không an toàn

Không dùng TrustManager tùy chỉnh luôn trả lời tin cậy, không cài truststore chứa mọi certificate và không bỏ hostname verification. Nếu cần thêm CA nội bộ, chỉ thêm trust anchor đã được xác minh và giới hạn phạm vi ảnh hưởng.

Các tham số như javax.net.ssl.trustStore, javax.net.ssl.keyStore và store type cần được kiểm tra trong startup configuration. Không truyền password keystore bằng system property trên command line vì có thể bị lộ qua process inspection hoặc diagnostic output.

## 9. Kiểm tra tham số JVM và quyền truy cập runtime

Một số JVM option có thể mở rộng quyền truy cập hoặc bật giao diện chẩn đoán từ xa. Audit cần kiểm tra command line của đúng service.

### Liệt kê JVM process

~~~bash
jcmd -l
~~~

### Kiểm tra process cụ thể

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> help
~~~

Thay <pid> bằng process ID thực tế. Lệnh help của process cho biết các diagnostic command mà JVM đó hỗ trợ.

Các lệnh này có thể cần cùng user/OS identity với JVM. jcmd là công cụ quản trị mạnh; giới hạn ai có thể attach và ai được phép chạy diagnostic command.

### Những option cần rà soát

| Option hoặc nhóm option | Rủi ro cần đánh giá |
|---|---|
| -agentlib:jdwp | Bật Java debugger; không để cổng debug mở ra mạng production |
| -javaagent | Agent có thể instrument và thay đổi bytecode |
| -agentpath | Nạp native agent có quyền ở cấp process |
| --add-opens | Mở package cho reflection sâu |
| --add-exports | Export package nội bộ cho module khác |
| --patch-module | Thay thế hoặc bổ sung nội dung module |
| -Djava.security.properties | Thay đổi security configuration |
| -Djavax.net.ssl.* | Thay đổi keystore/truststore hoặc TLS behavior |
| -Djava.io.tmpdir | Ảnh hưởng nơi ghi file tạm |
| -XX:+HeapDumpOnOutOfMemoryError | Có thể tạo heap dump chứa dữ liệu nhạy cảm |

Không phải option nào trong bảng cũng mặc nhiên là lỗ hổng. Hãy xác định lý do, phạm vi và owner; loại bỏ option không còn cần thiết và bảo vệ dữ liệu diagnostic.

### Debug port và JMX

- Không bật JDWP listener trên interface công khai trong production.
- Nếu cần remote management, dùng authentication, TLS, firewall và network binding phù hợp.
- Không bật JMX remote không xác thực.
- Hạn chế ai được attach bằng jcmd hoặc truy cập local management interface.
- Không để port quản trị, actuator hoặc diagnostic endpoint lộ ra Internet.

### System properties và command line có thể chứa secret

Các lệnh VM.command_line và VM.system_properties có thể in giá trị truyền bằng -D. Nếu password/token được đặt ở đó, output audit có thể làm lộ secret. Không đính kèm output nguyên bản vào ticket hoặc chat; lọc và redaction trước khi lưu.

## 10. Audit JNI, native library và agent

Java application có thể gọi mã native qua JNI, Foreign Function & Memory API, native agent hoặc provider dùng thư viện native. Mã native có thể truy cập bộ nhớ và tài nguyên ở mức process, nên cần được xem xét như thành phần có quyền cao.

Kiểm tra:

- Các file .dll, .so, .dylib và nguồn tải của chúng.
- JNI methods và FFM usage.
- java.library.path và đường dẫn nạp native library.
- -agentlib, -agentpath và -javaagent.
- Native provider như PKCS#11/HSM.
- Version, checksum, signature và CVE của native dependencies.
- Quyền filesystem của thư mục chứa native library.

JDK 24 phát cảnh báo liên quan đến việc sử dụng JNI nhằm chuẩn bị cho việc hạn chế truy cập native code ở các bản phát hành sau. Hãy rà soát warning, xác định module cần native access và chỉ cấp quyền cần thiết theo hướng dẫn của JDK mục tiêu.

Không nạp native library từ thư mục tạm, thư mục người dùng có quyền ghi rộng hoặc nguồn không được xác thực.

## 11. Audit secrets, filesystem và process identity

JVM chạy với quyền của tài khoản hệ điều hành khởi chạy nó. Nếu service chạy bằng root/Administrator, lỗi trong ứng dụng có thể gây hậu quả lớn hơn nhiều.

### Process identity và quyền hệ điều hành

- Dùng service account riêng cho từng ứng dụng hoặc nhóm service có cùng trust boundary.
- Không chạy bằng root/Administrator nếu không cần.
- Chỉ cấp quyền đọc file cấu hình, chứng chỉ và thư mục ứng dụng cần thiết.
- Chỉ cấp quyền ghi vào thư mục dữ liệu, log, temp hoặc upload đã xác định.
- Hạn chế network egress và inbound port.
- Giới hạn CPU, memory, process count, file descriptor và thời gian chạy.
- Dùng read-only filesystem/container root khi phù hợp.
- Không chạy container privileged hoặc mount host filesystem rộng không cần thiết.

Java Security Manager không thay thế các kiểm soát này trong JDK 24.

### Secrets

Không lưu password, API token, private key hoặc database credential trong:

- Git repository và file build.
- JVM arguments hoặc system properties.
- Log, exception message và tracing attributes.
- Docker image layer hoặc artifact phát hành.
- Heap dump, core dump hoặc JFR recording không được bảo vệ.
- Script có thể đọc bởi người dùng khác.

Dùng secret manager hoặc cơ chế cấp secret phù hợp với hạ tầng. Giới hạn quyền truy cập, luân chuyển định kỳ và thu hồi secret khi nhân sự, service hoặc môi trường thay đổi.

Environment variable có thể thuận tiện hơn hard-code, nhưng không tự động là kho bí mật an toàn. Process cùng quyền hoặc tài khoản quản trị có thể đọc chúng tùy hệ điều hành và cách triển khai.

### File tạm và dump

Xác định nơi ghi:

- java.io.tmpdir.
- Heap dump và core dump.
- JFR recording.
- Log và file audit.
- Upload, cache và extracted native library.

Kiểm tra quyền file, dung lượng, retention và quy trình xóa. Diagnostic dump có thể chứa object graph, token, request payload hoặc dữ liệu cá nhân.

## 12. Audit deserialization, XML và input không tin cậy

Một số API của Java có rủi ro cao khi nhận dữ liệu không tin cậy. Audit runtime nên xác định các điểm nhận dữ liệu và cấu hình parser tương ứng.

### Java native serialization

Không deserialize ObjectInputStream từ nguồn không tin cậy nếu không có kiểm soát. Khi bắt buộc phải dùng, áp dụng ObjectInputFilter để giới hạn class được phép, độ sâu graph, số reference, số byte và kích thước array theo nghiệp vụ.

Không coi việc kiểm tra class sau khi deserialize là biện pháp đủ an toàn; object graph có thể kích hoạt hành vi trong quá trình khôi phục.

### XML parser

Kiểm tra parser có bật secure processing và vô hiệu hóa external entity/DOCTYPE khi không cần. Đánh giá nguy cơ XXE, đọc file cục bộ và truy cập network ngoài ý muốn. Cấu hình phải áp dụng cho đúng parser/provider mà ứng dụng thực sự sử dụng.

### Input và expression

- Giới hạn kích thước request và upload.
- Validate input theo schema và kiểu dữ liệu mong đợi.
- Tránh đưa dữ liệu người dùng trực tiếp vào script engine, expression language hoặc command line.
- Dùng parameterized query cho database.
- Không dựa vào regex đơn lẻ để kiểm tra dữ liệu có cấu trúc phức tạp.
- Kiểm tra giới hạn recursion, nesting và thời gian xử lý để giảm DoS.

## 13. Logging, monitoring và incident readiness

Audit không hoàn chỉnh nếu không thể phát hiện và điều tra sự cố.

Nên có log cho:

- Đăng nhập thất bại và thành công theo chính sách.
- Thay đổi quyền, cấu hình và tài khoản quản trị.
- Thao tác cấp, đổi, thu hồi certificate và key.
- Thay đổi JDK/runtime image và dependency.
- Khởi động lại service, lỗi TLS và lỗi xác thực.
- Thao tác quản trị JVM, agent hoặc debug configuration.
- Các thay đổi trong truststore, provider và security properties.

Không ghi password, access token, private key, session cookie hoặc dữ liệu nhạy cảm nguyên bản. Dùng correlation ID để liên kết sự kiện mà không phải ghi toàn bộ payload.

Thiết lập cảnh báo cho certificate sắp hết hạn, JDK hết hỗ trợ, dependency có CVE nghiêm trọng, TLS handshake failure tăng bất thường, debug port xuất hiện ngoài dự kiến và thay đổi startup option.

Incident runbook nên chỉ rõ cách cô lập service, thu thập bằng chứng, thu hồi/rotate credential, thay artifact, khôi phục runtime image và xác minh lại sau xử lý.

## 14. Ví dụ Java 17+: tạo snapshot cấu hình bảo mật

Chương trình sau đọc một số security properties, provider names và TLS defaults của JVM hiện tại. Nó chỉ tạo snapshot cấu hình; không kiểm tra endpoint từ xa và không đánh giá trust policy của tổ chức.

Tạo file RuntimeSecuritySnapshot.java:

~~~java
import java.security.Provider;
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class RuntimeSecuritySnapshot {
    public static void main(String[] args) throws Exception {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));

        String[] properties = {
            "keystore.type",
            "jdk.tls.disabledAlgorithms",
            "jdk.certpath.disabledAlgorithms",
            "jdk.jar.disabledAlgorithms",
            "jdk.security.legacyAlgorithms"
        };

        for (String name : properties) {
            String value = Security.getProperty(name);
            if (value == null) {
                value = "(not set)";
            } else {
                value = value.replaceAll("\\s+", " ").trim();
            }
            System.out.println(name + "=" + value);
        }

        for (Provider provider : Security.getProviders()) {
            System.out.println("provider=" + provider.getName());
        }

        SSLParameters tls =
                SSLContext.getDefault().getDefaultSSLParameters();

        System.out.println("default TLS protocols=" +
                Arrays.toString(tls.getProtocols()));
        System.out.println("default TLS cipher suites=" +
                Arrays.toString(tls.getCipherSuites()));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 RuntimeSecuritySnapshot.java
~~~

Chạy:

~~~bash
java RuntimeSecuritySnapshot
~~~

Output phụ thuộc JDK vendor/version, provider và security properties đang hoạt động. Ví dụ, các dòng sẽ có dạng:

~~~text
java.version=<runtime version>
java.vendor=<runtime vendor>
keystore.type=<default keystore type>
jdk.tls.disabledAlgorithms=<active TLS restrictions>
jdk.certpath.disabledAlgorithms=<active certificate restrictions>
provider=<provider name>
default TLS protocols=[...]
default TLS cipher suites=[...]
~~~

Các dấu <...> ở trên chỉ biểu thị giá trị thay đổi theo môi trường, không phải output literal. Khi chạy audit thực tế, lưu output trong vùng có kiểm soát, đối chiếu với baseline đã phê duyệt và redaction trước khi chia sẻ.

## 15. Quy trình audit theo từng giai đoạn

Một quy trình có thể lặp lại nên gồm các bước sau:

### Giai đoạn 1: Xác định scope

- Chọn service, environment, JAR, plugin và runtime image.
- Xác định target JDK và hệ điều hành.
- Xác định dữ liệu nhạy cảm và trust boundary.
- Chỉ định owner kỹ thuật và người chấp nhận rủi ro.

### Giai đoạn 2: Thu thập baseline

- Ghi java --version và vendor/build.
- Thu thập security properties, provider và TLS settings.
- Lưu startup arguments và JVM flags đã redaction.
- Ghi process identity, container image và OS permissions.
- Lập inventory dependency, keystore, truststore và certificates.

### Giai đoạn 3: Phân tích kỹ thuật

- Chạy SCA trên direct/transitive dependencies.
- Chạy jdeps --jdk-internals.
- Chạy jdeprscan theo release mục tiêu.
- Xác minh signed artifacts.
- Kiểm tra certificate, trust chain và TLS endpoint.
- Rà soát agent, debug/JMX, module overrides và native libraries.
- Rà soát serialization, XML parser và input boundary.

### Giai đoạn 4: Đánh giá rủi ro

Với mỗi finding, ghi:

- Thành phần và môi trường bị ảnh hưởng.
- Bằng chứng có thể tái lập.
- Điều kiện khai thác.
- Tác động đến confidentiality, integrity và availability.
- Khả năng bị khai thác và mức độ phơi nhiễm.
- Biện pháp giảm thiểu hiện có.
- Mức độ ưu tiên, owner và thời hạn.

Có thể dùng thang mức độ Critical/High/Medium/Low theo quy trình của tổ chức. Không xếp hạng chỉ dựa vào số lượng warning; cần tính đến exposure, privilege, exploitability và dữ liệu bị ảnh hưởng.

### Giai đoạn 5: Khắc phục và xác minh

- Nâng cấp JDK hoặc dependency có lỗ hổng.
- Loại bỏ API nội bộ và option mở rộng không cần thiết.
- Sửa TLS, truststore và certificate lifecycle.
- Bảo vệ secret, keystore và diagnostic output.
- Giảm quyền OS/container và đóng port quản trị.
- Chạy lại cùng lệnh audit và test nghiệp vụ.
- Lưu bằng chứng trước/sau, kết quả và người phê duyệt.

### Giai đoạn 6: Duy trì

- Tự động chạy audit trong CI/CD và định kỳ trên production.
- Theo dõi security advisory của JDK vendor và dependency.
- Quét lại sau mỗi lần nâng JDK, thay provider hoặc certificate.
- Theo dõi certificate expiry và secret rotation.
- Review accepted risk theo thời hạn.
- Lưu baseline theo release để phát hiện thay đổi cấu hình ngoài dự kiến.

## 16. Mẫu bảng ghi nhận finding

| ID | Finding | Bằng chứng | Mức độ | Owner | Hành động | Trạng thái |
|---|---|---|---|---|---|---|
| SEC-001 | Runtime JDK hết hỗ trợ | java --version và vendor lifecycle | High | Platform | Nâng lên JDK được hỗ trợ | Open |
| SEC-002 | Debug listener đang bật | JVM args/service config | Critical | Operations | Tắt hoặc giới hạn network access | Open |
| SEC-003 | Dependency có CVE | SBOM và SCA report | High | Application | Nâng version và regression test | Open |
| SEC-004 | TLS policy còn protocol yếu | Endpoint scan và JSSE settings | High | Security | Cấu hình lại TLS và kiểm thử client | Open |
| SEC-005 | Truststore có certificate không rõ owner | keytool inventory | Medium | Platform | Xác minh, gán owner hoặc loại bỏ | Investigating |
| SEC-006 | Module mở rộng package không cần thiết | JVM startup options | Medium | Application | Xóa --add-opens dư thừa | Planned |

Đây là ví dụ về cách ghi nhận, không phải kết quả audit của một hệ thống thật. Mức độ cần được xác định dựa trên evidence và tiêu chí của tổ chức.

## 17. Lỗi thường gặp khi audit runtime Java

### Chỉ kiểm tra version Java

Version chưa đủ để biết cấu hình provider, patch, runtime image và security properties. Kiểm tra đúng runtime process và file cấu hình đang hoạt động.

### Tin rằng Security Manager đang cô lập ứng dụng

Từ JDK 24, Security Manager bị vô hiệu hóa vĩnh viễn. Dùng OS/container isolation và process boundary để giới hạn quyền.

### Chỉ xem TLS settings của JDK

TLS endpoint có thể được terminate ở proxy hoặc cấu hình bằng SSLContext riêng. Kiểm tra cả cấu hình ứng dụng và handshake từ bên ngoài.

### Chỉ kiểm tra cacerts mặc định

Ứng dụng có thể dùng truststore riêng qua system properties, code hoặc framework configuration. Xác định truststore thực tế của từng service.

### Chỉ chạy jdeps rồi kết luận dependency an toàn

jdeps không tìm CVE và có thể bỏ sót dependency động. Kết hợp SBOM, SCA và runtime testing.

### Chỉ xác minh JAR mà không kiểm tra signer trust

Digest có thể hợp lệ nhưng signer certificate chưa được tin cậy. Kiểm tra chain, usage, validity, timestamp và trust policy.

### Đưa password vào JVM arguments

Process inspection, diagnostic output hoặc log có thể làm lộ secret. Dùng secret manager và cơ chế cấp credential phù hợp.

### Bật debug/JMX để xử lý production rồi quên tắt

Diagnostic port có thể tạo đường truy cập quản trị mạnh. Đóng sau khi xử lý hoặc giới hạn nghiêm ngặt theo network/authentication policy.

### Lưu heap dump hoặc thread dump không kiểm soát

Dump có thể chứa dữ liệu nhạy cảm. Giới hạn quyền đọc, retention, encryption và quy trình chia sẻ.

### Chỉ audit một lần

Runtime thay đổi khi JDK, dependency, certificate, provider, container image hoặc startup flags thay đổi. Tích hợp audit vào pipeline và lịch vận hành.

## 18. Checklist audit bảo mật runtime

- Xác định đúng JDK vendor, version, patch và runtime process.
- Xác nhận JDK còn được hỗ trợ và có security updates.
- Ghi security properties và provider order đang hoạt động.
- Kiểm tra TLS/certificate disabled algorithms và legacy algorithms.
- Rà soát security properties override và startup configuration.
- Không dựa vào Security Manager trong JDK 24 trở lên.
- Cô lập process bằng OS/container và quyền tối thiểu.
- Lập SBOM và chạy SCA cho direct/transitive dependencies.
- Chạy jdeps --jdk-internals và jdeprscan theo target release.
- Xác minh artifact bằng jarsigner -verify -strict.
- Kiểm tra keystore/truststore, certificate chain, SAN, expiry và fingerprint.
- Kiểm tra TLS endpoint thực tế, hostname validation và mTLS nếu có.
- Rà soát --add-opens, --add-exports, --patch-module và java agents.
- Đóng JDWP/JMX/management port không cần thiết.
- Kiểm tra JNI, FFM, native library và provider native.
- Bảo vệ password, token, private key và diagnostic dump.
- Rà soát deserialization, XML external entities và input limits.
- Kiểm tra filesystem permissions, network egress và container capabilities.
- Đảm bảo log có audit evidence nhưng không chứa secret.
- Gán owner, mức độ, remediation và deadline cho từng finding.
- Chạy lại audit sau khắc phục và lưu kết quả xác minh.

## 19. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Runtime security audit | Kiểm tra bảo mật JDK/JVM và môi trường triển khai |
| Security property | Cấu hình bảo mật được Java Security Architecture sử dụng |
| Security provider | Implementation của dịch vụ mật mã hoặc bảo mật |
| JSSE | Framework Java hỗ trợ TLS/DTLS |
| Truststore | Kho certificate được dùng để xác thực peer hoặc trust anchor |
| Keystore | Kho private key, secret key và certificate |
| Certificate chain | Chuỗi certificate dẫn từ thực thể đến CA/trust anchor |
| JDK internal API | API nội bộ không thuộc hợp đồng tương thích công khai |
| SBOM | Danh mục thành phần phần mềm trong artifact |
| SCA | Phân tích dependency để tìm lỗ hổng và rủi ro license |
| JEP 486 | JDK Enhancement Proposal vô hiệu hóa vĩnh viễn Security Manager từ JDK 24 |
| JDWP | Giao thức debug Java |
| JNI | Java Native Interface để gọi mã native |
| JFR | Java Flight Recorder, công cụ ghi sự kiện chẩn đoán runtime |
| Least privilege | Chỉ cấp quyền tối thiểu cần thiết |
| Trust anchor | Điểm tin cậy gốc trong certificate validation |
| Revocation | Thu hồi certificate trước hoặc trong thời hạn hiệu lực |

Audit bảo mật runtime cần kết hợp cấu hình JDK, dependency, chữ ký artifact, certificate, TLS, JVM process và quyền hệ điều hành. Hãy lưu bằng chứng theo từng release, khắc phục finding theo mức độ rủi ro và chạy lại cùng quy trình để xác nhận môi trường thực tế đã an toàn hơn.

## Tài liệu tham khảo

- Oracle JDK 24 — [Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-developer-guide.html)
- Oracle JDK 24 — [Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The keytool Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/keytool.html)
- Oracle JDK 24 — [The jarsigner Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jarsigner.html)
- Oracle JDK 24 — [The jdeps Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- Oracle JDK 24 — [The jdeprscan Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- Oracle JDK 24 — [Significant Changes in JDK 24](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
- OpenJDK — [JEP 486: Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- OpenJDK — [JEP 472: Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)