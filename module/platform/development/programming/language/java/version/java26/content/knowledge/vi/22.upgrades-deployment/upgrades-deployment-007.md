# Kiểm tra JDBC, giao thức mạng và chính sách thuật toán

Nâng cấp JDK chỉ được xem là sẵn sàng khi ứng dụng kết nối được database, thương lượng đúng giao thức mạng, xác minh chứng thư và thực hiện được các thao tác mật mã mà production đang cần. Việc ứng dụng biên dịch thành công hoặc một lệnh `java -version` chạy được chưa chứng minh các phụ thuộc này tương thích.

Khi nâng lên JDK 26, cần kiểm tra thêm JDBC 4.5 MR5 và HTTP/3 trong HTTP Client API. JDK 26 cũng bổ sung security property `jdk.crypto.disabledAlgorithms`, hỗ trợ PBMAC1 cho PKCS12 và thay đổi một số thành phần truststore/provider. Nếu target là JDK 27, cần kiểm tra thêm hybrid key exchange hậu lượng tử cho TLS 1.3 và định dạng PKCS#8 của ML-KEM/ML-DSA.

Bài học thuộc module **JAVA_VERSION_JAVA26**. Mục tiêu là xây dựng một bộ kiểm thử nâng cấp có thể chạy trên đúng JDK, driver, database, proxy và security policy của môi trường đích; phát hiện lỗi trước khi rollout; đồng thời giữ khả năng rollback. Chỉ sử dụng những tính năng còn được hỗ trợ trên JDK 26/27 và phân biệt API stable với các thay đổi phụ thuộc provider hoặc database.

## 1. Lập ma trận tương thích trước khi nâng cấp

Trước khi chạy test, ghi lại những thành phần thực tế mà ứng dụng sử dụng. Một môi trường có thể chạy nhiều JDK, nhiều JDBC driver và nhiều truststore khác nhau giữa terminal, IDE, service và container.

| Thành phần | Thông tin cần ghi nhận | Vì sao cần |
|---|---|---|
| JDK | Vendor, version đầy đủ, build/update, đường dẫn runtime | Provider, security policy và truststore có thể khác giữa các bản build |
| Compiler | JDK compiler và `--release` đang dùng | Tránh biên dịch bằng JDK mới nhưng deploy runtime cũ không có API |
| JDBC driver | Tên, version, artifact, vendor và ma trận hỗ trợ JDK | Driver phải tương thích với runtime và database server |
| Database | Engine, version, protocol, TLS mode, schema | SQL type, transaction và TLS support phụ thuộc server |
| Connection pool | Tên/version, validation, timeout, wrapper/proxy | Pool có thể giữ connection cũ hoặc che lỗi driver |
| HTTP client | JDK HttpClient hay thư viện khác, version preference | HTTP/3 chỉ có ý nghĩa nếu client và đường mạng hỗ trợ |
| Proxy/load balancer | HTTP version, TLS termination, UDP/QUIC forwarding | Có thể làm HTTP/3 không được thương lượng hoặc bị fallback |
| Trust material | Truststore, keystore, certificate chain, alias | JDK update có thể thay đổi CA và algorithm constraints |
| Security policy | `java.security`, system properties, provider order | Thuật toán có thể bị chặn dù provider vẫn có implementation |
| Artifact signing | JAR signer, digest, certificate và timestamp | JDK mới có thể cảnh báo hoặc từ chối thuật toán ký cũ |

Nên có một dòng cho mỗi tổ hợp cần hỗ trợ, ví dụ JDK 26 với driver/database production, JDK 27 với cùng driver/database, và JDK đích với provider HSM nếu có. Không suy ra rằng driver hỗ trợ JDK 26 chỉ vì driver đó chạy được trên JDK 25; kiểm tra ma trận tương thích chính thức của nhà cung cấp và xác nhận bằng integration test.

## 2. Xác nhận đúng JDK và cấu hình của process triển khai

Ghi nhận version của các công cụ:

    java --version
    javac --version
    keytool -J-version
    jarsigner -J-version

Trên Windows PowerShell, có thể kiểm tra đường dẫn executable đang được shell chọn:

    $env:JAVA_HOME
    Get-Command java, javac, keytool, jarsigner |
        Select-Object Name, Source

Trong service hoặc container, kiểm tra command line, environment và image thực tế. Kết quả từ terminal của developer không chứng minh service dùng cùng runtime. Nếu ứng dụng khởi chạy qua script, service manager hoặc container entrypoint, ghi lại đường dẫn Java và toàn bộ JVM arguments đã áp dụng.

Giữ cố định các thông tin sau trong báo cáo test:

- JDK vendor, version, build và update.
- OS, architecture, container image và CPU/memory limit.
- JDBC driver và connection pool version.
- Database server version và cấu hình TLS.
- HTTP client preference và proxy route.
- Truststore/keystore, security properties và provider order.
- JVM arguments, environment variables và module/class path.

Khi so sánh JDK 25, 26 và 27, chạy cùng artifact nếu bytecode tương thích. Nếu đồng thời thay JDK, driver, database hoặc security policy, hãy ghi rõ để không quy nhầm nguyên nhân cho một thay đổi duy nhất.

## 3. Kiểm tra JDBC driver và database bằng kết nối thật

JDK 26 tích hợp **JDBC 4.5 Maintenance Release 5 (MR5)**. Các cập nhật chuẩn gồm type code JSON/DECFLOAT, AutoCloseable cho Array/Blob/Clob/NClob/SQLXML, các phương thức quote identifier/literal trên Connection và một vùng SQL escape mới. Đây là API Java SE ổn định trong module `java.sql`, không phải preview.

Tuy vậy, JDBC API mới không tự bổ sung kiểu dữ liệu cho database. Driver và database phải hỗ trợ tính năng cụ thể. Một driver có thể kết nối bình thường nhưng không hỗ trợ JSON, DECFLOAT hoặc một cú pháp SQL MR5.

Lấy metadata từ chính connection production-like:

    try (Connection connection = dataSource.getConnection()) {
        DatabaseMetaData metadata = connection.getMetaData();

        System.out.println("Database: "
                + metadata.getDatabaseProductName());
        System.out.println("Database version: "
                + metadata.getDatabaseProductVersion());
        System.out.println("Driver: "
                + metadata.getDriverName());
        System.out.println("Driver version: "
                + metadata.getDriverVersion());
        System.out.println("JDBC version: "
                + metadata.getJDBCMajorVersion() + "."
                + metadata.getJDBCMinorVersion());

        System.out.println("Valid: " + connection.isValid(5));
    }

Các giá trị metadata giúp nhận diện runtime thực tế nhưng không thay thế kiểm thử. Driver có thể công bố mức JDBC tương thích mà không hỗ trợ mọi tính năng tùy chọn hoặc kiểu dữ liệu riêng của server. `Connection.isValid(timeout)` chỉ là phép kiểm tra khả năng kết nối theo implementation của driver; vẫn cần thực thi SQL nghiệp vụ.

### Các thao tác JDBC cần có trong integration test

| Nhóm | Phép thử trên database staging | Điều cần xác nhận |
|---|---|---|
| Kết nối | Lấy connection qua DataSource/pool và chạy truy vấn nhẹ | Driver, credentials, DNS, firewall và TLS đều hoạt động |
| Transaction | Commit, rollback, isolation và auto-commit | Hành vi transaction không đổi sau nâng cấp |
| Prepared statement | Bind các kiểu dữ liệu thực tế | Mapping kiểu Java/SQL và parameter binding đúng |
| Batch | Batch insert/update với kích thước production-like | Update count, lỗi giữa batch và rollback đúng |
| Generated keys | Insert và lấy generated key | Driver trả đúng key theo database |
| LOB/Array | Đọc/ghi Blob, Clob, NClob, SQLXML và Array nếu dùng | Resource đóng đúng, không giữ locator sau transaction |
| Timeout | Query timeout, pool acquisition timeout và network timeout | Request không treo vô hạn khi DB chậm hoặc mất mạng |
| Failover | Ngắt kết nối staging hoặc chuyển primary theo kịch bản được hỗ trợ | Pool loại connection hỏng và phục hồi đúng |
| TLS | Kết nối bằng truststore/client certificate production-like | Chain, hostname và thuật toán được chấp nhận |
| Concurrency | Nhiều transaction và connection cùng lúc | Không mất dữ liệu, deadlock hoặc vượt pool limit ngoài dự kiến |

Không chạy phép thử phá hoại trên production. Dùng schema staging riêng và dữ liệu kiểm thử có thể rollback hoặc xóa theo quy trình.

## 4. Kiểm tra JDBC 4.5 MR5 khi ứng dụng dùng tính năng mới

Nếu ứng dụng sử dụng JSON hoặc DECFLOAT, hãy kiểm tra khả năng của database bằng metadata và thao tác đọc/ghi thật. JDBC 4.5 ánh xạ JSON sang `String` và DECFLOAT sang `BigDecimal`.

Ví dụ ghi JSON:

    String sql = """
            INSERT INTO integration_probe (probe_id, payload)
            VALUES (?, ?)
            """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, "jdk26-probe");
        statement.setObject(
                2,
                "{\"status\":\"ok\"}",
                JDBCType.JSON
        );
        statement.executeUpdate();
    }

Ví dụ ghi DECFLOAT:

    BigDecimal value = new BigDecimal("12345678901234567890.123456789");

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
                 "INSERT INTO decimal_probe (probe_id, amount) VALUES (?, ?)")) {

        statement.setString(1, "jdk26-probe");
        statement.setObject(2, value, JDBCType.DECFLOAT);
        statement.executeUpdate();
    }

Cú pháp DDL để tạo cột JSON/DECFLOAT phụ thuộc database. Đừng sao chép câu lệnh tạo bảng của một nhà cung cấp sang database khác. Kiểm tra precision, scale, NULL, giá trị lớn và round trip đọc lại bằng `getString` hoặc `getBigDecimal`.

Nếu dùng Connection.enquoteIdentifier/enquoteLiteral hoặc SQL escape region của JDBC 4.5 MR5, chạy test riêng trên driver được triển khai. Đặc biệt, cú pháp `{\\ ... \\}` dùng để tắt xử lý JDBC escape và parameter marker trong vùng SQL cần driver hỗ trợ MR5. Không giả định một driver cũ hiểu cú pháp đó chỉ vì code biên dịch thành công.

Các interface Array, Blob, Clob, NClob và SQLXML trong JDBC 4.5 mở rộng AutoCloseable. Hãy thử đóng chúng bằng try-with-resources cả khi thành công lẫn khi exception xảy ra. Kiểm tra driver có còn cho phép thao tác sau khi transaction/connection kết thúc hay không; không giữ locator vượt quá vòng đời mà driver bảo đảm.

## 5. Kiểm tra connection pool và wrapper

Ứng dụng thường không gọi driver trực tiếp mà thông qua connection pool, proxy hoặc framework ORM. Vì vậy, test driver đơn lẻ chưa đủ.

Kiểm tra các tình huống:

1. Khởi động pool mới trên JDK đích và xác nhận pool nạp đúng driver.
2. Mượn connection, chạy query, commit/rollback và trả connection về pool.
3. Mượn lại connection đó và xác nhận trạng thái session đã được reset theo hợp đồng pool.
4. Làm connection timeout hoặc đóng socket staging, xác nhận pool loại bỏ connection hỏng.
5. Kiểm tra giới hạn maximum pool size, acquisition timeout và leak detection.
6. Dừng ứng dụng, xác nhận pool đóng connection và background thread.
7. Kiểm tra proxy/wrapper có triển khai hoặc chuyển tiếp đúng các phương thức JDBC mới.

JDK 26 bổ sung default methods cho Connection. Driver hoặc wrapper có method cùng chữ ký nhưng visibility không phù hợp, hoặc lớp triển khai nhiều interface có default method xung đột, có thể cần nâng cấp. Kiểm tra release notes của driver và pool; không chỉ kiểm tra compile.

Không đặt maximum pool size quá lớn để che latency database. Giới hạn pool phải phù hợp với giới hạn connection của server và số instance ứng dụng. Nếu triển khai nhiều replica, tính tổng connection tối đa của toàn cụm, không chỉ từng instance.

## 6. Kiểm tra giao thức HTTP/1.1, HTTP/2 và HTTP/3

JDK 26 bổ sung HTTP/3 cho **java.net.http.HttpClient** qua JEP 517. Có thể chọn `HttpClient.Version.HTTP_3` làm phiên bản ưu tiên. Đây là API Java SE ổn định, không cần `--enable-preview`.

Các giao thức có đặc tính vận chuyển khác nhau:

| Giao thức | Vận chuyển | Điều kiện mạng cần kiểm tra |
|---|---|---|
| HTTP/1.1 | TCP, thường qua TLS với HTTPS | TCP port, proxy và certificate |
| HTTP/2 | TCP + TLS, thương lượng ALPN `h2` | TCP, TLS, ALPN và hỗ trợ của server/proxy |
| HTTP/3 | QUIC trên UDP, dùng TLS 1.3 trong QUIC, ALPN `h3` | UDP, QUIC forwarding, TLS 1.3, server/CDN và proxy route |

HTTP/3 không chạy trên TCP. Một firewall chỉ cho phép TCP/443 nhưng chặn UDP/443 có thể khiến HTTP/3 không thiết lập được và client sử dụng giao thức fallback nếu đường kết nối hỗ trợ. Proxy, VPN, load balancer, TLS inspection appliance và NAT cũng có thể làm thay đổi kết quả.

Không kết luận HTTP/3 đã hoạt động chỉ vì server có quảng bá hỗ trợ. Phải kiểm tra phiên bản HTTP thực tế của response hoặc log phía server.

### Thử HTTP/3 bằng JDK 26

    import java.net.URI;
    import java.net.http.HttpClient;
    import java.net.http.HttpRequest;
    import java.net.http.HttpResponse;
    import java.time.Duration;

    public class HttpProtocolProbe {
        public static void main(String[] args) throws Exception {
            URI uri = URI.create(args[0]);

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_3)
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(20))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            System.out.println("Preferred: " + client.version());
            System.out.println("Negotiated: " + response.version());
            System.out.println("Status: " + response.statusCode());
        }
    }

Biên dịch và chạy:

    javac --release 26 -d out src/HttpProtocolProbe.java
    java -cp out HttpProtocolProbe https://service.example.com/health

`client.version()` cho biết phiên bản ưu tiên đã cấu hình; `response.version()` cho biết phiên bản thực tế của response. Nếu yêu cầu HTTP/3 nhưng response dùng HTTP/2 hoặc HTTP/1.1, ghi nhận fallback và điều tra đường mạng/server. Một lần fallback không nhất thiết là lỗi ứng dụng nếu hệ thống cho phép fallback; nhưng nếu SLA yêu cầu HTTP/3, cần xác định rõ nguyên nhân và ngưỡng chấp nhận.

Chạy cùng phép thử với `HTTP_2` và `HTTP_1_1` để có baseline. Dùng endpoint staging có hỗ trợ các phiên bản cần kiểm tra, không chỉ endpoint nội bộ vốn có thể kết thúc TLS ở một proxy không hỗ trợ QUIC.

## 7. Kiểm tra HTTP/3 qua proxy, firewall và load balancer

Để HTTP/3 được dùng từ client đến endpoint, kiểm tra từng đoạn của đường mạng:

- DNS trả về địa chỉ phù hợp và endpoint có quảng bá HTTP/3 theo cơ chế được client hỗ trợ.
- UDP/443 được phép qua firewall và NAT.
- Load balancer/CDN hỗ trợ QUIC và chuyển tiếp đến origin theo cấu hình tương ứng.
- Proxy/VPN không buộc lưu lượng đi qua đường chỉ hỗ trợ HTTP/1.1 hoặc HTTP/2.
- Server hỗ trợ TLS 1.3 và ALPN `h3`.
- Certificate chain, hostname và truststore hợp lệ.
- Đường fallback HTTP/2/HTTP/1.1 vẫn hoạt động nếu thiết kế yêu cầu.

Không bật HTTP/3 trên client rồi giả định mọi request sẽ đi qua QUIC. Kiểm tra response.version, log của server/load balancer và telemetry mạng. Nếu HTTP/3 không khả dụng do môi trường, xác định rõ ứng dụng sẽ fallback, retry hay từ chối request theo SLA.

Nếu hệ thống dùng proxy hoặc custom SSLContext, chạy test với đúng cấu hình đó. Không dùng TrustManager chấp nhận mọi certificate hoặc tắt hostname verification để làm handshake thành công. Cách làm đó vô hiệu hóa một phần quan trọng của kiểm thử bảo mật.

## 8. Kiểm tra TLS và chứng thư của database/HTTP endpoint

Một kết nối TCP thành công chưa chứng minh TLS handshake và xác minh chứng thư thành công. Với mỗi endpoint, cần kiểm tra:

1. Protocol TLS được thương lượng.
2. Cipher suite và key exchange được chọn.
3. Signature scheme phù hợp với certificate.
4. Certificate chain nối tới trust anchor được tin cậy.
5. SAN khớp hostname endpoint.
6. Certificate nằm trong thời gian hiệu lực.
7. Algorithm constraints không chặn thuật toán hoặc kích thước khóa.
8. Client certificate được gửi và xác minh đúng nếu dùng mutual TLS.

Đối với HTTP client, dùng SSLContext/truststore production-like. Với JDBC, cấu hình TLS phụ thuộc driver/database; đọc tài liệu nhà cung cấp để bật xác minh hostname và certificate. Không có một URL property JDBC chung cho tất cả database.

Có thể bật JSSE handshake debug trong môi trường kiểm thử:

    java -Djavax.net.debug=ssl:handshake,trustmanager -cp out TlsProbe

Với HTTP/3, QUIC tích hợp TLS 1.3 vào transport QUIC; không dựa duy nhất vào log TLS-over-TCP để chứng minh HTTP/3. Kết hợp response.version, log server/QUIC và packet telemetry phù hợp.

JDK 26 loại bỏ một số root certificate AffirmTrust không còn hoạt động khỏi cacerts mặc định. SunJSSE cũng áp dụng thay đổi distrust đối với một số chứng thư neo vào Chunghwa root CA theo mốc phát hành được nêu trong release notes. Vì vậy, kết nối từng hoạt động trên JDK cũ có thể thất bại sau nâng cấp. Kiểm tra chain và trust anchor thực tế; cập nhật certificate từ CA theo quy trình PKI, không thêm lại root đã bị distrust hoặc nới lỏng policy để che lỗi.

## 9. Kiểm tra security properties và algorithm constraints

Các chính sách mật mã của Java có nhiều phạm vi riêng:

| Property | Phạm vi |
|---|---|
| `jdk.certpath.disabledAlgorithms` | Thuật toán và điều kiện bị chặn khi xác minh đường dẫn chứng thư |
| `jdk.tls.disabledAlgorithms` | Protocol, cipher, key exchange, signature và key size trong TLS/DTLS |
| `jdk.jar.disabledAlgorithms` | Thuật toán dùng để xác minh chữ ký JAR |
| `jdk.crypto.disabledAlgorithms` | Các dịch vụ JCA/JCE được hỗ trợ như Cipher, KeyStore, MessageDigest và Signature |
| `jdk.security.legacyAlgorithms` | Đánh dấu thuật toán legacy để công cụ bảo mật có thể cảnh báo |
| `jdk.tls.legacyAlgorithms` | Thuật toán TLS legacy mà SunJSSE chỉ dùng khi không còn lựa chọn phù hợp hơn |
| `crypto.policy` | Giới hạn độ mạnh mật mã theo jurisdiction policy |

JDK 26 bổ sung `jdk.crypto.disabledAlgorithms`; property này ban đầu không chặn thuật toán nào theo mặc định. Phạm vi ban đầu gồm Cipher, KeyStore, MessageDigest và Signature. Không suy ra property này kiểm soát mọi service hoặc mọi provider.

Đọc security settings:

    java -XshowSettings:security -version

Đọc property từ chính ứng dụng:

    import java.security.Security;

    String[] names = {
        "jdk.certpath.disabledAlgorithms",
        "jdk.tls.disabledAlgorithms",
        "jdk.jar.disabledAlgorithms",
        "jdk.crypto.disabledAlgorithms",
        "jdk.security.legacyAlgorithms",
        "jdk.tls.legacyAlgorithms",
        "crypto.policy"
    };

    for (String name : names) {
        System.out.println(
                name + " = " + Security.getProperty(name)
        );
    }

Nếu runtime dùng system property override, ghi lại cả `System.getProperty(...)` và `Security.getProperty(...)`. Với JDK 27, có thể xem security properties của process đang chạy bằng:

    jcmd <pid> VM.security_properties

Lệnh này là tiện ích JDK 27; không giả định có trong JDK 26. Một số security properties được đọc/cached khi lớp bảo mật khởi tạo. Khi thay đổi cấu hình, khởi chạy process mới để kiểm thử, không chỉ gọi `Security.setProperty()` trong một JVM đã chạy lâu.

## 10. Kiểm tra provider và thuật toán thực sự được dùng

Liệt kê provider chỉ cho biết service đã đăng ký. Nó không chứng minh một phép toán cụ thể thành công với key type, parameters, algorithm constraints và dữ liệu thật.

Kiểm tra provider:

    for (Provider provider : Security.getProviders()) {
        System.out.println(
                provider.getName() + " " + provider.getVersionStr()
        );
    }

Sau đó chạy các phép thử phù hợp với ứng dụng:

- MessageDigest: tính digest và so sánh kết quả kỳ vọng.
- Cipher: tạo khóa, mã hóa/giải mã round trip và xác nhận tag AEAD.
- Signature: ký và xác minh bằng cặp khóa đúng loại.
- KeyStore: load, đọc alias, lấy certificate/private key và thực hiện thao tác ký.
- CertPath: xác minh chuỗi chứng thư với trust anchor thực tế.
- TLS: handshake với endpoint thật bằng trust manager production-like.

Ví dụ kiểm tra một thuật toán JCA/JCE:

    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    System.out.println("Provider: " + cipher.getProvider().getName());

    int maxAesKeyBits = Cipher.getMaxAllowedKeyLength("AES");
    System.out.println("Max AES key length: " + maxAesKeyBits);

Nếu dùng HSM hoặc provider bên thứ ba, chạy test qua chính provider đó. Không dùng SunJCE smoke test để kết luận HSM production hỗ trợ cùng thuật toán. Kiểm tra cả provider order, cơ chế nạp provider và xác thực chữ ký provider JAR.

## 11. Kiểm tra PKCS12, PBMAC1 và keystore cũ

PKCS12 là định dạng keystore được khuyến nghị cho triển khai mới. JDK 26 bổ sung hỗ trợ PBMAC1 cho integrity protection của PKCS12. Tuy nhiên, file keystore được tạo trước đó vẫn dùng thuật toán mà file đã được tạo với; không tự động đổi định dạng khi runtime nâng cấp.

Liệt kê keystore bằng JDK đích:

    keytool -list -v -keystore service.p12 -storetype PKCS12

Trong integration test, kiểm tra:

- File được load bằng đúng JDK/vendor.
- Alias và loại entry đúng.
- Certificate chain và ngày hiệu lực đúng.
- Private key có thể được lấy bằng credential phù hợp.
- Khóa thực hiện được ký/xác minh hoặc handshake cần thiết.
- File tạo trên JDK mới đọc được bởi mọi runtime/công cụ downstream cần hỗ trợ.

Nếu bật PBMAC1 cho file PKCS12 mới, xác minh property `keystore.pkcs12.macAlgorithm` và thử đọc file trên mọi runtime đích. Không giả định công cụ bên ngoài như OpenSSL hoặc một JDK cũ có cùng mức hỗ trợ PBMAC1.

JDK 26 cảnh báo việc sử dụng JKS/JCEKS và định hướng chuyển sang PKCS12. Với keystore cũ, chuyển một bản sao:

    keytool -importkeystore -srckeystore legacy.jks -srcstoretype JKS -destkeystore migrated.p12 -deststoretype PKCS12

Sau đó kiểm tra alias, entry, certificate chain và thao tác mật mã bằng file mới trước khi thay cấu hình production. Không xóa bản gốc cho đến khi quá trình khôi phục và rollback đã được xác nhận.

## 12. Kiểm tra chữ ký JAR và custom provider

Dùng `jarsigner` thuộc JDK đích để xác minh artifact:

    jarsigner -verify -strict -verbose -certs application.jar

Đọc toàn bộ warning về digest, signature algorithm, certificate chain, timestamp và disabled algorithms. Một JAR có thể có chữ ký nhưng vẫn không đáp ứng policy hiện hành. Nếu quy trình yêu cầu kiểm tra thu hồi certificate, đánh giá thêm `-revCheck` trong môi trường có thể truy cập OCSP/CRL.

Nếu dùng custom JCE provider, xác minh JAR provider và thử nạp trong đúng distribution. Oracle JDK có yêu cầu xác thực chữ ký provider; một provider JAR ký bằng certificate JCE cũ/hết hạn có thể bị từ chối dù cùng provider đó hoạt động trong một OpenJDK build khác. Làm việc với nhà cung cấp để có bản ký hợp lệ; không tắt kiểm tra chữ ký provider để ép nạp JAR không đáng tin cậy.

Nếu pipeline ký JAR dùng ML-DSA, xác minh cả bước ký và bước kiểm tra trên mọi JDK/toolchain đích. Không chỉ kiểm tra JAR trên máy build.

## 13. Kiểm tra các thay đổi hậu lượng tử khi target là JDK 27

JDK 27 bổ sung hybrid key exchange cho TLS 1.3, gồm các named group như:

- `X25519MLKEM768`
- `SecP256r1MLKEM768`
- `SecP384r1MLKEM1024`

`X25519MLKEM768` được bật mặc định và có mức ưu tiên cao. Tuy nhiên, client hỗ trợ group không bảo đảm handshake đã sử dụng nó; server, proxy và thiết bị trung gian cũng phải hỗ trợ. Kiểm tra nhóm thực tế trong TLS 1.3 ServerHello/handshake telemetry và kiểm tra server logs. Nếu nhóm hybrid không được thương lượng, ghi rõ fallback group đang được sử dụng.

JDK 27 cũng thay đổi định dạng PKCS#8 mặc định của private key ML-KEM/ML-DSA sang dạng `seed`. Các hệ thống còn dùng JDK 26 hoặc công cụ cũ cần kiểm tra khả năng đọc định dạng này. Nếu phải tạo khóa trên JDK 27 nhưng trao đổi với runtime cũ, JDK 27 cung cấp các property để chọn định dạng `expandedKey` tương thích:

    -Djdk.mlkem.pkcs8.encoding=expandedKey
    -Djdk.mldsa.pkcs8.encoding=expandedKey

Chỉ áp dụng property liên quan đến thuật toán thực tế sử dụng và đặt trước khi tạo/translate key. Kiểm tra key bằng thao tác encapsulate/decapsulate hoặc sign/verify trên cả hai runtime; đừng chỉ so sánh chuỗi Base64 hay độ dài file PKCS#8.

Những thay đổi JDK 27 này không phải yêu cầu để một ứng dụng JDK 26 hoạt động. Chúng là mục kiểm tra riêng khi JDK 27 nằm trong target deployment hoặc khi dữ liệu khóa cần được trao đổi giữa các phiên bản.

## 14. Chạy kiểm thử trong môi trường staging giống production

Một bộ kiểm thử có ích phải chạy qua cùng các thành phần và đường mạng với production:

1. Dùng đúng JDK vendor/build, container image và JVM arguments.
2. Dùng đúng JDBC driver, pool, database version và schema tương đương.
3. Dùng đúng truststore, certificate chain, client certificate và provider.
4. Dùng cùng proxy, firewall route, DNS, load balancer và CDN.
5. Kiểm tra HTTP/1.1, HTTP/2 và HTTP/3 theo yêu cầu thực tế.
6. Kiểm tra TLS handshake, certificate validation và algorithm constraints.
7. Thực hiện transaction, batch, timeout, rollback, failover và connection pool exhaustion test.
8. Xác minh keystore, JAR signature và custom provider.
9. Chạy load test đủ dài để quan sát connection churn, timeout, memory và retry.
10. Lặp lại với JDK 27 nếu đây là runtime đích, bao gồm hybrid TLS và key encoding nếu hệ thống dùng.

Không dùng một endpoint internet ngẫu nhiên để kết luận production route hỗ trợ HTTP/3. Dùng endpoint do hệ thống kiểm soát hoặc môi trường staging có cùng cấu hình CDN/proxy/load balancer.

## 15. Theo dõi khi rollout và chuẩn bị rollback

Triển khai theo từng bước để giới hạn phạm vi sự cố:

| Giai đoạn | Việc làm | Tiêu chí tiếp tục |
|---|---|---|
| Lab | Kiểm tra API, driver, protocol và policy trên JDK đích | Bộ test kỹ thuật pass |
| Staging | Chạy integration, load, failover và security tests qua hạ tầng tương đương production | Không có lỗi tương thích chưa giải thích |
| Canary | Chuyển một phần traffic hoặc một instance sang JDK mới | Error rate, latency, DB pool và TLS ổn định |
| Mở rộng | Tăng dần tỷ lệ instance | KPI ổn định qua chu kỳ tải đại diện |
| Hoàn tất | Cập nhật runtime chuẩn và tài liệu vận hành | Có bằng chứng và quy trình rollback được kiểm tra |

Theo dõi tối thiểu:

- JDBC connection failure, acquisition timeout, validation failure và pool exhaustion.
- SQLState, vendor error code, transaction rollback và query latency.
- HTTP response version, status code, retry, connect/request timeout và TLS failure.
- TLS protocol, cipher/group, certificate validation và handshake failure.
- Provider load failure, disabled algorithm exception và JAR signature warning.
- CPU, memory, GC, thread count và file descriptor.
- Khác biệt giữa HTTP/3 thực tế và fallback HTTP/2/HTTP/1.1.

Rollback cần giữ lại JDK cũ, driver/keystore/configuration tương thích và artifact đã được xác nhận. Nếu JDK mới tạo keystore hoặc private key ở định dạng mà runtime cũ không đọc được, phải kiểm tra khả năng đọc ngược trước khi phát hành. Không thay đổi định dạng key/keystore trong cùng đợt nâng JDK nếu chưa có kế hoạch tương thích và khôi phục.

## 16. Bảng phân loại lỗi khi kiểm thử

| Dấu hiệu | Nguyên nhân cần xem xét | Bằng chứng tiếp theo |
|---|---|---|
| JDBC driver không nạp hoặc lỗi linkage | Driver cũ, module/class path, xung đột dependency hoặc default method | Driver version, class loading log, vendor compatibility matrix |
| Connection timeout | DNS, firewall, DB quá tải, pool cạn hoặc TLS handshake chậm | Pool metrics, network trace, DB logs, TLS debug |
| JSON/DECFLOAT không bind được | Driver/server chưa hỗ trợ type hoặc mapping khác | DatabaseMetaData, driver docs và round-trip test |
| HTTP response dùng HTTP/2 dù yêu cầu HTTP/3 | UDP/QUIC bị chặn, peer không hỗ trợ, proxy/CDN không chuyển tiếp hoặc fallback | response.version, server/QUIC logs, firewall telemetry |
| SSLHandshakeException | Trust chain, hostname, TLS version, signature/group hoặc disabled policy | JSSE debug, certificate chain, security properties |
| CertPathValidatorException | CA không tin cậy, certificate hết hạn hoặc algorithm constraints | CertPath debug, truststore và issuer chain |
| NoSuchAlgorithmException | Provider không có service hoặc algorithm bị policy chặn | Provider list, exact service name và disabled property |
| KeyStore load thất bại | Password, MAC, format, PBMAC1 hoặc provider compatibility | keytool output và thử load trên runtime downstream |
| JAR signature warning/error | Digest/signature algorithm yếu, certificate hoặc timestamp | jarsigner strict output và policy |
| Provider bị SecurityException | JCE provider JAR không được xác thực bởi JDK distribution | jarsigner verify và certificate code-signing |

Giữ exception gốc, SQLState, vendor code và security debug tương ứng. Không chuyển mọi lỗi thành thông báo chung “JDK mới không tương thích”; phân loại theo lớp JDBC, network, TLS, provider, keystore hoặc artifact signing.

## 17. Checklist trước khi phát hành

- [ ] Đã xác nhận đúng JDK vendor/build/runtime của service.
- [ ] Đã kiểm tra JDBC driver và connection pool theo ma trận hỗ trợ.
- [ ] Đã thực thi transaction, prepared statement, batch, timeout và rollback.
- [ ] Đã kiểm tra JSON/DECFLOAT, LOB/Array và các API JDBC 4.5 nếu ứng dụng dùng.
- [ ] Đã kiểm tra database TLS bằng truststore và hostname verification thật.
- [ ] Đã thử HTTP/1.1, HTTP/2 và HTTP/3 trên đường mạng tương đương production.
- [ ] Đã xác nhận response.version thay vì chỉ nhìn cấu hình client.
- [ ] Đã kiểm tra UDP/QUIC, proxy, firewall, load balancer và fallback.
- [ ] Đã đọc security properties thực tế và phân biệt disabled với legacy algorithms.
- [ ] Đã thực hiện thao tác mật mã thật qua provider được triển khai.
- [ ] Đã kiểm tra PKCS12/PBMAC1 và khả năng đọc trên mọi runtime downstream.
- [ ] Đã xác minh JAR signature và custom provider.
- [ ] Nếu target JDK 27, đã kiểm tra hybrid TLS group và ML-KEM/ML-DSA key encoding khi có sử dụng.
- [ ] Đã chạy staging, load, failover và canary.
- [ ] Đã chuẩn bị và kiểm tra rollback, bao gồm keystore/key format và runtime cũ.

## Tài liệu chính thức

- [JEP 517 — HTTP/3 for the HTTP Client API](https://openjdk.org/jeps/517): hỗ trợ HTTP/3 trong Java HTTP Client API của JDK 26.
- [Java SE 26 API — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): chọn HTTP version, connect timeout và phiên bản response thực tế.
- [Java SE 26 API — HttpClient.Version](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Version.html): HTTP/1.1, HTTP/2 và HTTP/3.
- [Java SE 26 API — java.sql package](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.5 MR5 và các cập nhật API.
- [Java SE 26 API — DatabaseMetaData](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): metadata về database, driver và SQL type.
- [Oracle — JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): JDBC 4.5, HTTP/3, PBMAC1, security property và truststore/provider changes.
- [Oracle — Security Properties File, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html): security properties, include, override và cách xem cấu hình.
- [Oracle — Java Cryptography Architecture Reference Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html): provider, KeyStore và cryptographic services.
- [Java Security Standard Algorithm Names, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên chuẩn của Cipher, Signature, MessageDigest và các thuật toán.
- [Oracle — keytool Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html): kiểm tra, tạo và chuyển keystore.
- [Oracle — jarsigner Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html): xác minh chữ ký JAR, strict mode và revocation check.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): hybrid TLS key exchange, ML-KEM/ML-DSA PKCS#8 encoding và `jcmd VM.security_properties`.
- [Java SE 27 API — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): xác nhận HTTP Client API tiếp tục có trên JDK 27.
- [Java SE 27 API — java.sql package](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/package-summary.html): xác nhận JDBC 4.5 tiếp tục có trên JDK 27.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html): giao thức HTTP/3 trên QUIC.
- [RFC 9001 — Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001.html): TLS 1.3 và bảo vệ handshake QUIC.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html): giao thức TLS 1.3.

Một lần nâng JDK an toàn cần chứng minh được ba lớp: JDBC driver/database thực hiện đúng giao dịch; HTTP/TLS thương lượng đúng giao thức trên đường mạng thật; và provider/security policy chấp nhận các khóa, chứng thư, chữ ký đang dùng. JDK 26 bổ sung HTTP/3 và JDBC 4.5 cùng các thay đổi bảo mật; JDK 27 có thêm hybrid TLS và thay đổi key encoding. Chỉ rollout sau khi kiểm tra bằng đúng runtime, đúng phụ thuộc và đúng cấu hình production-like.
