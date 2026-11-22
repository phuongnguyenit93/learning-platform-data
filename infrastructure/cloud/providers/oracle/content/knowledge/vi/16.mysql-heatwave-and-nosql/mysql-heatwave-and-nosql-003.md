# Kết nối MySQL từ ứng dụng và quản lý người dùng

## 1. Mục tiêu và phạm vi

Trong chương **MySQL HeatWave và NoSQL** của lộ trình Oracle Cloud Infrastructure (OCI), bài này tập trung vào đường kết nối giữa ứng dụng và MySQL HeatWave, cùng cách quản lý tài khoản MySQL theo quyền tối thiểu.

Một kết nối sử dụng được trong vận hành cần đáp ứng đồng thời:

1. Ứng dụng có đường mạng tới đúng endpoint và port.
2. Kết nối dùng TLS với mức xác minh phù hợp.
3. Tài khoản đăng nhập được từ nguồn kết nối thực tế.
4. Tài khoản chỉ được thực hiện các thao tác nghiệp vụ cần thiết.
5. Ứng dụng quản lý connection, timeout, bí mật và lỗi kết nối đúng cách.

Sau bài học, bạn có thể cấu hình kết nối Java/JDBC, tạo user và role cho ứng dụng, kiểm tra quyền thực tế, lập ngân sách connection pool và xử lý các lỗi theo từng lớp.

Các ví dụ dùng **MySQL classic protocol**, Connector/J và tài khoản xác thực bằng mật khẩu. HeatWave vẫn được ứng dụng truy cập qua endpoint MySQL của DB system; không cấu hình JDBC trỏ vào một node xử lý HeatWave riêng. Bài không hướng dẫn kết nối Oracle NoSQL Database vì dịch vụ đó dùng API và mô hình quyền khác.

Tên database, địa chỉ, ngưỡng timeout và giới hạn trong bài là giá trị minh họa. Phiên bản driver, phương thức xác thực và certificate phải phù hợp DB system thực tế.

## 2. Phân biệt IAM, mạng và tài khoản database

### 2.1. Ba lớp quyền độc lập

| Lớp | Ví dụ | Điều lớp này kiểm soát |
| --- | --- | --- |
| OCI IAM | User/group, policy, quyền đọc secret | Quản lý hoặc truy cập tài nguyên dịch vụ theo policy |
| Mạng | VCN, subnet, NSG, security list, tuyến và firewall | Gói tin có đến được endpoint hay không |
| MySQL | Account, authentication, role, GRANT | Ai đăng nhập database và được làm gì bên trong |

Một người có quyền xem DB system trên Console chưa tự có quyền SELECT bảng nghiệp vụ. Ngược lại, biết mật khẩu MySQL nhưng không có đường mạng hoặc không khớp account host vẫn có thể không đăng nhập được.

Một workload được IAM cho phép đọc secret cũng chưa tự được cấp quyền MySQL. Secret chỉ cung cấp thông tin xác thực; account và grant vẫn phải tồn tại ở database.

### 2.2. Ngoại lệ có cấu hình rõ ràng: xác thực tích hợp OCI

MySQL HeatWave có cơ chế ánh xạ người dùng MySQL với danh tính OCI qua thành phần xác thực được hỗ trợ. Cơ chế này cần mapping, plugin và client phù hợp; không xảy ra chỉ vì người dùng đã đăng nhập Console. [Kết nối bằng mapped MySQL user](https://docs.oracle.com/en-us/iaas/mysql-database/doc/connecting-mapped-mysql-user.html).

Ví dụ JDBC trong bài dùng mật khẩu. Không đưa OCID, API signing key hoặc mật khẩu Console vào trường mật khẩu JDBC rồi kỳ vọng chúng hoạt động như tài khoản MySQL thông thường.

## 3. Chuẩn bị đường mạng tới DB system

### 3.1. Lấy đúng endpoint

Ghi lại từ DB system:

- Endpoint dùng cho đọc/ghi.
- Hostname hoặc địa chỉ kết nối.
- Port MySQL classic protocol.
- VCN, subnet và các nhóm bảo mật liên quan.
- Cấu hình certificate và tên được certificate bảo vệ.

Port thường gặp của classic protocol là 3306; X Protocol thường dùng 33060. Nếu dịch vụ cấu hình port khác, dùng giá trị thực tế. URL `jdbc:mysql://...` trong bài dùng classic protocol, không dùng port X Protocol.

Đối với hệ thống có read endpoint hoặc read replica, phải chọn endpoint theo mục đích. Không đưa thao tác ghi vào endpoint chỉ phục vụ đọc. Ngữ nghĩa endpoint cần đối chiếu cấu hình DB system. [DB system endpoints](https://docs.oracle.com/en-us/iaas/mysql-database/doc/db-system-endpoints.html).

### 3.2. Endpoint riêng cần đường truy cập riêng

Endpoint DB system MySQL trong OCI không phải địa chỉ public để laptop bất kỳ kết nối trực tiếp. Các phương án truy cập gồm ứng dụng trong VCN, kết nối từ mạng được định tuyến phù hợp, VPN hoặc phiên Bastion phục vụ quản trị. [Tổng quan mạng MySQL HeatWave](https://docs.oracle.com/en-us/iaas/mysql-database/doc/overview-networking.html).

Một topology ứng dụng điển hình:

~~~mermaid
flowchart LR
    USER["Người dùng"]
    LB["Load balancer / API"]
    APP["Ứng dụng Java trong subnet ứng dụng"]
    DB["MySQL DB system: endpoint riêng"]
    SECRET["Dịch vụ quản lý secret"]

    USER --> LB
    LB --> APP
    APP -->|"MySQL classic protocol + TLS"| DB
    APP -->|"Đọc secret theo quyền IAM"| SECRET
~~~

Đường đọc secret và đường truy cập MySQL là hai kết nối khác nhau. Phải có route và quyền phù hợp cho từng đường.

### 3.3. Quy tắc mạng nên diễn đạt chính xác

Ví dụ thiết kế:

| Thành phần | Hướng và phạm vi |
| --- | --- |
| Ứng dụng | Cho phép egress tới endpoint DB trên port classic thực tế |
| DB system | Cho phép ingress từ nguồn ứng dụng được duyệt trên port đó |
| DNS | Ứng dụng phân giải được hostname dùng để kết nối |
| Kết nối quản trị | Chỉ cho nguồn quản trị được duyệt qua đường truy cập phù hợp |
| Firewall tại OS hoặc mạng ngoài OCI | Không chặn luồng ứng dụng–DB nếu có tham gia đường truyền |

Nếu NSG-to-NSG phù hợp topology và được hỗ trợ, có thể dùng để tránh phụ thuộc IP từng máy. Nếu dùng CIDR, giữ phạm vi cần thiết và ghi rõ đường đi thực.

Cần xem các rule đang áp dụng cùng nhau; không nghĩ thêm một NSG “hạn chế” sẽ tự thu hẹp quyền đã được một rule khác cho phép rộng hơn.

Không mở port database cho toàn internet để xử lý lỗi kết nối. Hãy xác định thiếu route, rule hay đường truy cập quản trị.

### 3.4. Nguồn kết nối MySQL nhìn thấy

Địa chỉ trong account `'user'@'host'` là nguồn client mà MySQL nhận diện, không phải địa chỉ của DB server.

Nếu có NAT, proxy, tunnel hoặc topology Kubernetes, địa chỉ nguồn MySQL thấy có thể khác IP pod hoặc laptop. Ghi nhận nguồn thực trước khi tạo host restriction.

Bastion/tunnel là phương tiện cho một đường truy cập cụ thể. Không mặc định host restriction dành cho application server cũng cho phép đường tunnel từ máy quản trị.

## 4. TLS: mã hóa và xác minh danh tính server

### 4.1. Các mức sslMode trong Connector/J

| Chế độ | Mã hóa | Kiểm tra CA | Kiểm tra tên/địa chỉ server với certificate |
| --- | --- | --- | --- |
| DISABLED | Không | Không | Không |
| PREFERRED | Có nếu server chấp nhận, có thể fallback | Không theo mức xác minh CA | Không |
| REQUIRED | Bắt buộc TLS | Không tương đương VERIFY_CA | Không |
| VERIFY_CA | Bắt buộc TLS | Có | Không |
| VERIFY_IDENTITY | Bắt buộc TLS | Có | Có |

Connector/J phân biệt các mức này; mặc định hoặc một tùy chọn “bật SSL” chưa chứng minh đã xác minh danh tính server. [Thuộc tính bảo mật Connector/J](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-security.html).

Ví dụ ứng dụng trong bài yêu cầu `VERIFY_IDENTITY`. Điều kiện để dùng được:

- Client tin cậy đúng CA/chuỗi chứng thư.
- Certificate server còn hiệu lực và hợp lệ.
- Hostname hoặc địa chỉ trong kết nối khớp danh tính được certificate bảo vệ.
- Phiên bản driver và JVM hỗ trợ cấu hình TLS của dịch vụ.

Nếu chưa đáp ứng, cần sửa certificate, DNS hoặc cấu hình trust phù hợp. Tắt xác minh chỉ làm phép thử kết nối thành công với mức bảo vệ khác, không xử lý nguyên nhân.

### 4.2. Certificate của dịch vụ và certificate do khách hàng cung cấp

MySQL HeatWave có tùy chọn certificate do dịch vụ xác định hoặc certificate do khách hàng đưa vào theo cơ chế được hỗ trợ. [Tùy chọn certificate của DB system](https://docs.oracle.com/en-us/iaas/mysql-database/doc/advanced-options.html).

Không mặc định mọi certificate do dịch vụ sinh đều khớp một DNS alias do bạn tự đặt. Cũng không tự đổi host trong JDBC URL sang IP nếu IP đó không nằm trong danh tính hợp lệ của certificate.

Trước khi chạy ví dụ:

1. Xác nhận endpoint và loại certificate thực tế.
2. Lấy CA/chain qua nguồn quản trị đáng tin cậy.
3. Xác nhận danh tính endpoint được certificate bảo vệ.
4. Cấp truststore hoặc CA file cho đúng runtime.
5. Thử từ cùng môi trường mạng với ứng dụng.

Kết nối bằng tunnel tới `localhost` có thể gặp lỗi identity vì certificate bảo vệ tên endpoint DB, không phải `localhost`. Phải thiết kế đường kết nối và cách giữ danh tính server phù hợp thay vì hạ mức xác minh.

### 4.3. Truststore Java

Connector/J có thể dùng truststore riêng hoặc cơ chế trust của JVM theo cấu hình. [Thiết lập server authentication với Connector/J](https://dev.mysql.com/doc/connector-j/en/connector-j-server-authentication.html).

Ví dụ tạo truststore PKCS12 riêng trong môi trường Linux của ứng dụng:

~~~bash
keytool -importcert -alias heatwave-root-ca -file /opt/app/certs/heatwave-ca.pem -keystore /opt/app/certs/heatwave-truststore.p12 -storetype PKCS12
~~~

Lệnh hỏi mật khẩu truststore và thông tin xác nhận chứng thư. Trước khi tin cậy, đối chiếu CA/fingerprint theo nguồn đã được phê duyệt. Nếu chain cần nhiều CA, chuẩn bị đầy đủ các chứng thư phù hợp bằng alias riêng.

Các đường dẫn trên là minh họa cho runtime Linux; khi chạy trên Windows phải dùng đường dẫn và file URL tương ứng.

Truststore chứa chứng thư tin cậy, không phải password MySQL. Đừng nhầm nó với keystore chứa private key để xác thực client bằng mTLS. Ví dụ trong bài không yêu cầu client certificate; nếu môi trường bắt buộc mTLS thì phải bổ sung keystore và cấu hình tương ứng.

Quản lý thay certificate cũng phải xét cả thời hạn, CA rotation và các replica ứng dụng chưa nhận truststore mới.

## 5. Chuẩn bị schema và tài khoản theo quyền tối thiểu

### 5.1. Tách người quản trị, migration và runtime

| Danh tính | Nhiệm vụ | Phạm vi điển hình |
| --- | --- | --- |
| Quản trị database | Tạo user/role, quản lý quyền và vận hành trong phạm vi dịch vụ | Quyền quản trị được dịch vụ hỗ trợ |
| Migration/deployment | Tạo hoặc thay đổi schema theo bản phát hành | DDL cần thiết trên schema được giao |
| Runtime ứng dụng | Thực hiện giao dịch nghiệp vụ | SELECT/INSERT/UPDATE cần thiết trên đối tượng cụ thể |
| Báo cáo | Đọc dữ liệu được phép | SELECT trên bảng hoặc view được duyệt |

Không dùng tài khoản administrator của DB system trong ứng dụng. Tài khoản quản trị của dịch vụ được quản lý cũng không có nghĩa có mọi quyền của root trên MySQL tự cài; một số quyền hoặc schema hệ thống bị giới hạn. [Quyền mặc định của DB system administrator](https://docs.oracle.com/en-us/iaas/mysql-database/doc/default-mysql-privileges.html).

### 5.2. Tạo dữ liệu mẫu

Trong môi trường học tập, người quản trị hoặc danh tính triển khai có quyền phù hợp chuẩn bị:

~~~sql
CREATE DATABASE orders CHARACTER SET utf8mb4;

CREATE TABLE orders.purchase_order (
    id BIGINT NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_purchase_order_request (request_id)
);

INSERT INTO orders.purchase_order
    (request_id, customer_id, total_amount, status)
VALUES
    ('LAB-ORDER-001', 101, 250000.00, 'CREATED');
~~~

Các lệnh tạo mới giả định schema chưa tồn tại; không chạy nguyên khối trên schema production đang dùng. Migration production cần công cụ và quy trình thay đổi của dự án.

### 5.3. Account MySQL có cả user và host

Hai account sau là hai danh tính khác nhau:

~~~text
'orders_app'@'10.20.1.25'
'orders_app'@'10.20.1.26'
~~~

Cùng tên user nhưng host khác có thể có mật khẩu và grant khác nhau. Host trong ví dụ phải thay bằng nguồn kết nối thực tế mà MySQL nhận diện.

Để phục vụ nhiều instance, có thể dùng nhiều account host cụ thể hoặc phạm vi mạng được phiên bản hỗ trợ. Không tự dùng `@'%'` cho mọi ứng dụng; lựa chọn phạm vi phải phù hợp topology. MySQL cũng có quy định riêng về netmask/CIDR và việc sử dụng wildcard host. [Cú pháp account MySQL](https://dev.mysql.com/doc/refman/8.4/en/account-names.html).

### 5.4. Tạo role và gán cho runtime

Ví dụ quản trị cho một application server có nguồn `10.20.1.25`:

~~~sql
CREATE ROLE 'orders_runtime';

GRANT SELECT, INSERT, UPDATE
ON orders.purchase_order
TO 'orders_runtime';

CREATE USER 'orders_app'@'10.20.1.25'
IDENTIFIED BY 'REPLACE_WITH_GENERATED_SECRET'
REQUIRE SSL;

GRANT 'orders_runtime'
TO 'orders_app'@'10.20.1.25';

SET DEFAULT ROLE 'orders_runtime'
TO 'orders_app'@'10.20.1.25';
~~~

`REPLACE_WITH_GENERATED_SECRET` là chỗ thay bằng bí mật được sinh và chuyển qua kênh quản trị phù hợp, không phải mật khẩu dùng chung cho bài thực hành. Tránh để mật khẩu thật trong repository, lịch sử terminal hoặc log SQL của pipeline.

Runtime ở đây được đọc, thêm và cập nhật đơn hàng; chưa được DELETE, DDL hoặc tự cấp quyền. Nếu nghiệp vụ không cần UPDATE thì bỏ quyền đó. Quyền tối thiểu xuất phát từ thao tác thực tế, không từ một mẫu GRANT cố định.

Role đã được gán chưa chắc tự active trong phiên; `SET DEFAULT ROLE` quy định role mặc định cho kết nối sau. Phiên đang mở cần được kiểm tra hoặc tạo lại. [Sử dụng role trong MySQL](https://dev.mysql.com/doc/refman/8.4/en/roles.html).

Tên role trong ví dụ không ghi host; host mặc định trong định danh role không có ý nghĩa wildcard kết nối như account đăng nhập. [Cú pháp role MySQL](https://dev.mysql.com/doc/refman/8.4/en/role-names.html).

`REQUIRE SSL` yêu cầu kênh mã hóa cho account ở phía server. Nó không thay cho việc client xác minh certificate, và không tự yêu cầu client certificate như một cấu hình mTLS.

## 6. Kiểm tra bằng client trước khi kết nối ứng dụng

### 6.1. Thử từ đúng nguồn mạng

Chạy client từ application server hoặc môi trường có đường đi tương đương. Việc đăng nhập thành công từ máy quản trị không chứng minh container ứng dụng cũng có DNS, route, CA và account host đúng.

Ví dụ với MySQL client trong shell Linux, sau khi đã cấu hình `DB_HOST` và `DB_PORT`:

~~~bash
mysql --host="$DB_HOST" --port="$DB_PORT" --user=orders_app --password --ssl-mode=VERIFY_IDENTITY --ssl-ca=/opt/app/certs/heatwave-ca.pem orders
~~~

Client hỏi mật khẩu tương tác. Không nối mật khẩu thật ngay sau `--password` hoặc đặt nó trong command line.

Tên host phải đáp ứng điều kiện certificate ở phần trước. Đường CA file dùng cho MySQL client không tự làm JVM tin cậy cùng CA; Java phải nhận truststore phù hợp.

### 6.2. Xác định account và quyền của phiên

Sau khi đăng nhập:

~~~sql
SELECT
    USER() AS client_identity,
    CURRENT_USER() AS authenticated_account,
    CURRENT_ROLE() AS active_roles,
    DATABASE() AS current_database;

SHOW GRANTS;

SHOW SESSION STATUS LIKE 'Ssl_cipher';

SELECT id, status
FROM orders.purchase_order
ORDER BY id
LIMIT 5;
~~~

Cách đọc:

- `USER()` phản ánh tên người dùng và nguồn client của kết nối.
- `CURRENT_USER()` cho biết account MySQL được dùng để xác thực phiên trong ngữ cảnh truy vấn trực tiếp này.
- `CURRENT_ROLE()` giúp xác nhận role đã active.
- `DATABASE()` xác nhận schema mặc định.
- `Ssl_cipher` có giá trị cho biết phiên đang dùng cipher TLS.

Cipher chứng minh có mã hóa, không chứng minh client đã kiểm tra đúng hostname. Bằng chứng identity verification còn nằm ở cấu hình client và việc kiểm chứng lỗi với certificate/host không hợp lệ trong môi trường thử.

`SHOW GRANTS` hiển thị grant/role đã gán; cần xem cả quyền của role khi kiểm tra quyền hiệu lực. Quản trị viên có thể dùng:

~~~sql
SHOW GRANTS FOR 'orders_runtime';

SHOW GRANTS FOR 'orders_app'@'10.20.1.25'
USING 'orders_runtime';
~~~

Không cấp quyền đọc toàn bộ bảng hệ thống chỉ để ứng dụng tự kiểm tra tài khoản. Công việc rà soát tài khoản khác thuộc danh tính quản trị phù hợp. [Tham chiếu SHOW GRANTS](https://dev.mysql.com/doc/refman/8.4/en/show-grants.html).

### 6.3. Thử cả thao tác bị cấm

Trong schema học tập, runtime phải đọc được bảng đã cấp quyền. Có thể kiểm tra việc thiếu DDL bằng một bảng thử riêng:

~~~sql
CREATE TABLE orders.runtime_should_not_create (
    id BIGINT PRIMARY KEY
);
~~~

Với role runtime ở trên và không có grant bổ sung, lệnh phải bị từ chối. Nếu thành công, dừng kiểm tra và rà lại quyền; để danh tính quản trị dọn bảng thử sau khi xác nhận nguyên nhân.

Không dùng DROP bảng nghiệp vụ hoặc xóa dữ liệu thật làm phép thử “quyền bị cấm”. Chỉ kiểm tra đối tượng thử không ảnh hưởng dữ liệu khác.

## 7. Kết nối Java bằng Connector/J

### 7.1. Dependency và khả năng tương thích

Connector/J có Maven coordinates `com.mysql:mysql-connector-j`. [Cài Connector/J bằng Maven](https://dev.mysql.com/doc/connector-j/en/connector-j-installing-maven.html).

Ví dụ dependency:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>${mysql.connector.version}</version>
</dependency>
~~~

Đây là đoạn cấu hình mẫu: cần định nghĩa `mysql.connector.version` bằng một phiên bản cụ thể đã kiểm tra tương thích với JDK và DB system. Nếu dependency management/BOM của dự án đã quản lý phiên bản phù hợp, dùng cơ chế đó và bỏ phần version trực tiếp khi thích hợp.

Không dùng nhãn phiên bản “latest” như một cấu hình production có thể tái lập. Cũng không ép server đổi sang authentication plugin cũ chỉ để giữ một driver quá cũ.

### 7.2. Cấu hình ngoài mã nguồn

Ví dụ các cấu hình runtime:

| Biến | Nội dung |
| --- | --- |
| DB_HOST | Hostname endpoint phù hợp DNS và certificate |
| DB_PORT | Port classic protocol thực tế |
| DB_USER | orders_app |
| DB_PASSWORD | Bí mật MySQL lấy qua cơ chế quản lý secret |
| DB_TRUSTSTORE_URL | File URL của truststore, ví dụ file:/opt/app/certs/heatwave-truststore.p12 |
| DB_TRUSTSTORE_PASSWORD | Mật khẩu truststore |

Schema mẫu là `orders`. Trong triển khai khác, đưa tên schema vào cấu hình đã kiểm soát.

Các giá trị cấu hình phải do môi trường triển khai tin cậy cung cấp. Không lấy hostname, JDBC URL hoặc thuộc tính driver trực tiếp từ request của người dùng.

### 7.3. Ví dụ Java đọc đơn hàng

Ví dụ dùng JDBC chuẩn để làm rõ cấu hình kết nối, không cần framework. Code dùng cú pháp phù hợp Java 17 trở lên; Connector/J vẫn phải có trong runtime classpath.

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Properties;

public final class OrderLookup {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu cấu hình: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = requiredEnv("DB_HOST");
        int port = Integer.parseInt(requiredEnv("DB_PORT"));
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("DB_PORT không hợp lệ");
        }

        long orderId = args.length == 0 ? 1L : Long.parseLong(args[0]);
        String url = "jdbc:mysql://" + host + ":" + port + "/orders";

        Properties properties = new Properties();
        properties.setProperty("user", requiredEnv("DB_USER"));
        properties.setProperty("password", requiredEnv("DB_PASSWORD"));
        properties.setProperty("sslMode", "VERIFY_IDENTITY");
        properties.setProperty("connectTimeout", "5000");
        properties.setProperty("socketTimeout", "15000");
        properties.setProperty(
            "trustCertificateKeyStoreUrl",
            requiredEnv("DB_TRUSTSTORE_URL")
        );
        properties.setProperty("trustCertificateKeyStoreType", "PKCS12");
        properties.setProperty(
            "trustCertificateKeyStorePassword",
            requiredEnv("DB_TRUSTSTORE_PASSWORD")
        );
        properties.setProperty("fallbackToSystemTrustStore", "false");

        String sql =
            "SELECT id, status FROM purchase_order WHERE id = ?";

        try (Connection connection =
                 DriverManager.getConnection(url, properties);
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, orderId);
            statement.setQueryTimeout(5);

            try (ResultSet result = statement.executeQuery()) {
                if (result.next()) {
                    System.out.printf(
                        "orderId=%d, status=%s%n",
                        result.getLong("id"),
                        result.getString("status")
                    );
                } else {
                    System.out.println("Không tìm thấy đơn hàng mẫu");
                }
            }
        } catch (SQLException exception) {
            System.err.printf(
                "Database operation failed: SQLState=%s, code=%d%n",
                exception.getSQLState(),
                exception.getErrorCode()
            );
            throw new IllegalStateException(
                "Kết nối hoặc truy vấn database thất bại"
            );
        }
    }
}
~~~

Các điểm cần hiểu:

- Mật khẩu được truyền bằng `Properties`, không nằm trong JDBC URL.
- TLS và xác minh identity được yêu cầu rõ ràng.
- Truststore riêng được cấu hình bắt buộc; ví dụ không fallback sang truststore hệ thống.
- `PreparedStatement` gắn giá trị tham số thay vì nối chuỗi SQL từ đầu vào.
- `try-with-resources` đóng result set, statement và connection.
- Log mẫu chỉ ghi SQLState và mã lỗi, không dump toàn bộ properties hay secret.

Dữ liệu mẫu thường có id đầu tiên bằng 1 trong bảng vừa tạo; nếu môi trường dùng id khác, truyền id thực tế. Việc không tìm thấy bản ghi không phải lỗi kết nối.

Ứng dụng thật cần xử lý lỗi bằng cơ chế logging và trả lỗi phù hợp của dịch vụ; không biến ví dụ console này thành chính sách xử lý lỗi duy nhất.

### 7.4. Không thêm các tùy chọn “chữa lỗi” thiếu căn cứ

Tránh các thay đổi như:

~~~text
sslMode=DISABLED
allowPublicKeyRetrieval=true
autoReconnect=true
~~~

Không phải mọi thuộc tính trên đều sai trong mọi môi trường, nhưng chúng không phải bộ tham số mặc định để sửa mọi lỗi kết nối.

Ví dụ, lỗi lấy RSA public key cần được đánh giá cùng authentication plugin và TLS. Ưu tiên thiết lập TLS và server authentication đúng, thay vì bật khả năng lấy key từ một server chưa được xác minh rồi coi kết nối đã được bảo vệ tương đương.

Tự reconnect ở driver cũng không phục hồi tự động trạng thái transaction hoặc xác định kết quả commit. Kết nối mới không đồng nghĩa giao dịch cũ được tiếp tục.

## 8. Timeout và connection pool

### 8.1. Mỗi timeout giới hạn một công việc khác nhau

| Cấu hình | Điều nó giới hạn | Không nên suy ra |
| --- | --- | --- |
| Driver connectTimeout | Thời gian chờ thiết lập socket theo hành vi driver | Toàn bộ request chắc chắn kết thúc trong thời gian đó |
| Driver socketTimeout | Thời gian chờ thao tác socket theo driver | Server đã rollback transaction |
| Statement query timeout | Yêu cầu giới hạn thời gian thực thi statement theo hỗ trợ JDBC/driver | Mọi truy vấn bị hủy tức thì và không có tác dụng phụ |
| Pool acquisition timeout | Thời gian chờ mượn connection | Thời gian chạy SQL |
| Request deadline | Ngân sách toàn request | Các tầng bên dưới tự biết và tuân thủ nếu chưa tích hợp |

Connector/J định nghĩa `connectTimeout` và `socketTimeout` theo mili giây. Giá trị trong ví dụ là lựa chọn minh họa, không phải khuyến nghị chung. [Thuộc tính networking Connector/J](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html).

Chọn timeout theo mục tiêu nghiệp vụ, độ trễ mạng và loại truy vấn. Một truy vấn báo cáo hợp lệ kéo dài có thể cần cấu hình khác với API tạo đơn.

Không cộng máy móc các timeout để tạo một bảo đảm tổng thời gian. Cần thiết kế deadline và quan sát hành vi hủy ở từng tầng.

### 8.2. Dùng pool cho ứng dụng phục vụ nhiều request

Mở TLS và xác thực cho mọi request gây thêm chi phí và độ trễ. Trong ứng dụng dài hạn, dùng `DataSource` có connection pool được framework hoặc thư viện phù hợp quản lý.

Mẫu truy cập:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT status FROM orders.purchase_order WHERE id = ?"
         )) {
    statement.setLong(1, orderId);
    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả trong thời gian đang giữ connection.
    }
}
~~~

Ở đây `dataSource` là pool đã khởi tạo với cùng cấu hình endpoint, user, TLS và truststore. `close()` trên connection do pool cung cấp thường trả connection về pool; không bỏ lệnh đóng chỉ vì dùng pool.

`MysqlDataSource` cung cấp cách cấu hình kết nối nhưng việc dùng một DataSource không tự chứng minh đã có pool vật lý. Phải xác định thành phần nào thực sự giữ và tái sử dụng connection.

Không chia sẻ một `Connection` singleton cho nhiều request đồng thời. Tách vòng đời pool của ứng dụng với vòng đời connection được mượn cho từng đơn vị công việc.

### 8.3. Tính tổng connection khi scale ứng dụng

Giả sử:

~~~text
6 replica ứng dụng × maximum pool 12 connection = 72
Migration, quan sát và công việc khác dự kiến   =  8
Tổng dự kiến                                  = 80
~~~

Nếu ngân sách phục vụ ứng dụng và công việc này là 80 connection sau khi đã dành phần quản trị, cấu hình trên không còn dư địa cho replica tăng thêm.

Khi autoscale lên 10 replica:

~~~text
10 × 12 + 8 = 128 connection
~~~

Chỉ sửa số replica mà không sửa ngân sách connection có thể gây lỗi khi tải tăng.

Cần tính cả:

- Số replica tối đa và số replica tạm khi rolling deployment.
- Batch worker, job, migration và công cụ giám sát.
- Connection tới các endpoint khác nhau.
- Phần dành cho vận hành và sự cố.
- Tài nguyên thực tế DB system có thể phục vụ, không chỉ giới hạn cấu hình.

Pool lớn hơn không tự tăng throughput. Quá nhiều transaction đồng thời có thể tăng chờ khóa, CPU và bộ nhớ.

### 8.4. Giới hạn theo account là hàng rào bổ sung

Người quản trị có thể đặt giới hạn phù hợp, ví dụ:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
WITH MAX_USER_CONNECTIONS 20;
~~~

Số 20 là minh họa và phải nhất quán với pool cùng các công việc dùng account đó. Giới hạn này tính theo account MySQL; nếu nhiều nguồn khớp cùng account, chúng cùng chia sẻ ngân sách tương ứng.

Khi vượt giới hạn, ứng dụng có thể nhận lỗi thay vì làm DB system tự mở thêm tài nguyên. Giám sát cả connection đang dùng, connection chờ trong pool và số request lỗi.

## 9. Transaction, retry và tình trạng commit chưa biết

### 9.1. Kết nối thành công chưa bảo đảm giao dịch đúng

JDBC connection mới thường dùng autocommit theo cấu hình mặc định. Khi nghiệp vụ cần nhiều statement trong một transaction, phải quản lý transaction bằng framework hoặc JDBC một cách nhất quán.

Nguyên tắc:

1. Mượn connection.
2. Bắt đầu phạm vi transaction.
3. Thực hiện các statement cần thiết.
4. Commit khi hoàn tất hoặc rollback khi còn có thể thực hiện.
5. Trả connection sau khi trạng thái được xử lý đúng.

Không giữ connection trong lúc chờ người dùng, gọi HTTP chậm hoặc xử lý file nếu không cần transaction bao trùm các thao tác đó. Thời gian giữ connection dài khiến pool cạn ngay cả khi database chưa hết CPU.

### 9.2. Không retry mù khi mất kết nối

Tình huống:

~~~text
Ứng dụng gửi COMMIT
    -> server có thể đã commit
    -> kết nối đứt trước khi ứng dụng nhận phản hồi
~~~

Ứng dụng chưa biết chắc kết quả. Chạy lại toàn bộ thao tác có thể tạo hai đơn hàng.

Bảng mẫu có `request_id` duy nhất để hỗ trợ thiết kế chống trùng. Cần lưu một khóa yêu cầu ổn định cho cùng nghiệp vụ và định nghĩa cách đối chiếu khi retry. Unique key là một cơ chế nền; vẫn phải kiểm tra request trùng có cùng nội dung và xử lý giao dịch bên ngoài phù hợp.

Retry nên có giới hạn, backoff và jitter cho lỗi tạm thời phù hợp. Không retry liên tục với mật khẩu sai, certificate sai, thiếu quyền hoặc SQL lỗi cú pháp.

### 9.3. Failover không giữ nguyên connection cũ

Khi bảo trì hoặc chuyển instance, các connection có thể bị ngắt. Ứng dụng cần loại bỏ connection không dùng được, mở kết nối mới qua endpoint đúng và xử lý transaction bị gián đoạn theo quy tắc nghiệp vụ.

Không ghim ứng dụng vào địa chỉ nội bộ của một backend không được dịch vụ quy định làm endpoint ứng dụng. HA của DB system không tự bảo đảm request đang chạy sẽ hoàn tất mà không cần xử lý ở client.

## 10. Quản lý bí mật của ứng dụng

### 10.1. Không đóng gói mật khẩu vào artifact

Không để password MySQL trong:

- Source code hoặc file cấu hình được commit.
- Container image.
- JDBC URL bị ghi vào log.
- Command line hoặc output của pipeline.
- Trang health check hoặc endpoint chẩn đoán.

Trong OCI, có thể dùng dịch vụ quản lý secret và danh tính workload được cấp quyền tối thiểu để lấy đúng bí mật cần dùng. Việc chọn secret OCID, phiên bản và quyền truy cập thuộc cấu hình triển khai; runtime MySQL chỉ nhận giá trị cần thiết cho xác thực.

Không cấp cho ứng dụng quyền liệt kê hoặc đọc mọi secret trong tenancy nếu chỉ cần một secret.

### 10.2. Biến môi trường chỉ là một cách truyền cấu hình

Ví dụ Java đọc environment variable để ngắn gọn và tách bí mật khỏi code. Điều này không biến environment variable thành vùng tuyệt đối bí mật.

Cần kiểm soát:

- Ai có quyền đọc cấu hình workload hoặc debug process.
- Log cấu hình có bị in khi khởi động không.
- Secret có xuất hiện trong bản chụp lỗi hoặc công cụ hỗ trợ không.
- Thời điểm ứng dụng đọc secret và cách nhận phiên bản mới.
- Quyền file truststore và file cấu hình nếu dùng volume.

Có thể dùng SDK, secret volume hoặc cơ chế tích hợp của nền tảng. Lựa chọn phải phù hợp vòng đời ứng dụng và quy trình rotation.

### 10.3. Không nhầm đọc secret mới với cập nhật pool

Nếu ứng dụng chỉ đọc password lúc khởi tạo pool, thay nội dung secret không tự thay thông tin xác thực trong pool đó.

Quy trình cần xác định một trong các cách:

- Tạo pool mới với secret mới rồi chuyển lưu lượng.
- Rolling restart để từng replica khởi tạo lại.
- Dùng cơ chế refresh đã được thư viện hỗ trợ và kiểm chứng.

Connection đã xác thực có thể vẫn dùng được sau khi password thay đổi. Vì vậy một ứng dụng “vẫn đang chạy bình thường” chưa chứng minh connection mới sẽ đăng nhập thành công.

## 11. Xoay mật khẩu có giai đoạn chuyển tiếp

### 11.1. Dùng dual password khi được hỗ trợ

MySQL hỗ trợ duy trì mật khẩu chính và mật khẩu phụ cho account trong các điều kiện phù hợp. `RETAIN CURRENT PASSWORD` giữ password hiện tại làm password phụ khi đổi, còn `DISCARD OLD PASSWORD` bỏ password phụ. Cần phiên bản, authentication plugin và quyền quản trị phù hợp. [ALTER USER và dual password](https://dev.mysql.com/doc/refman/8.4/en/alter-user.html).

Ví dụ do danh tính quản trị thực hiện:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
IDENTIFIED BY 'REPLACE_WITH_NEW_GENERATED_SECRET'
RETAIN CURRENT PASSWORD;
~~~

Không dùng chuỗi placeholder làm mật khẩu thật. Khi thao tác qua automation, bảo vệ cả đầu vào lẫn log của công cụ thực hiện SQL.

Trình tự chuyển tiếp:

1. Xác nhận account, plugin, quyền và trạng thái các instance ứng dụng.
2. Đổi sang password mới và giữ password cũ trong cửa sổ chuyển tiếp đã giới hạn.
3. Cập nhật phiên bản secret theo quy trình phát hành.
4. Chuyển từng replica/pool sang password mới.
5. Tạo **kết nối mới** từ các nguồn ứng dụng và xác nhận truy vấn cần thiết.
6. Xác nhận không còn workload phụ thuộc password cũ.
7. Bỏ password phụ:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25'
DISCARD OLD PASSWORD;
~~~

Sau bước cuối, thử lại kết nối mới bằng password mới; trong phép thử được kiểm soát, password cũ phải không xác thực được nữa.

Không gộp việc đổi authentication plugin vào cùng quy trình nếu chưa đánh giá riêng, vì nó có thể thay đổi hành vi dual password và khả năng tương thích client.

### 11.2. Khi không dùng dual password

Có thể tạo account thay thế với cùng phạm vi quyền đã kiểm tra:

~~~text
orders_app_a -> đang phục vụ
orders_app_b -> chuẩn bị, kiểm tra và chuyển dần
~~~

Mỗi account vẫn phải có host restriction và TLS phù hợp. Sau khi chuyển, khóa/thu hồi account cũ theo kế hoạch; không để cả hai tồn tại vô thời hạn mà không có người sở hữu.

Phương án hai account giúp có giai đoạn chuyển tiếp nhưng thêm công việc quản lý grant, account host và audit. Không tự sao chép toàn bộ quyền của administrator sang account mới.

### 11.3. Password hết hạn và machine account

Một account ứng dụng hết hạn password giữa giờ phục vụ có thể khiến connection mới thất bại trong khi connection cũ còn hoạt động. Triệu chứng do đó có thể xuất hiện dần theo vòng đời pool.

Thống nhất chính sách hết hạn với rotation, cảnh báo và phương thức cập nhật secret. Không dùng việc tắt mọi chính sách password như cách xử lý mặc định cho ứng dụng.

## 12. Rà soát, thay đổi quyền và thu hồi account

### 12.1. Ghi quyền theo nhu cầu nghiệp vụ

Ví dụ ma trận quyền:

| Danh tính | Đối tượng | Quyền | Lý do |
| --- | --- | --- | --- |
| orders_runtime | orders.purchase_order | SELECT | Tra cứu đơn hàng |
| orders_runtime | orders.purchase_order | INSERT | Tạo đơn |
| orders_runtime | orders.purchase_order | UPDATE | Cập nhật trạng thái theo nghiệp vụ |
| reporting_reader | View báo cáo được duyệt | SELECT | Đọc dữ liệu đã giới hạn |
| migration | Đối tượng schema được giao | DDL theo kế hoạch | Triển khai phiên bản |

Nếu có nhu cầu mới, bổ sung quyền cụ thể và kiểm tra. Không đổi thành `GRANT ALL ON *.*` chỉ vì một migration thất bại.

Quyền DDL và quyền cấp quyền cho người khác không nên xuất hiện trong runtime nếu ứng dụng không có nhiệm vụ đó. Cũng không cấp quyền quản trị server để xử lý lỗi một câu SELECT.

### 12.2. Role không thay cho phân quyền người dùng cuối

`orders_app` là danh tính kỹ thuật dùng chung của backend trong ví dụ. MySQL thấy account đó, không tự biết khách hàng HTTP nào đang gửi request.

Ứng dụng phải xác thực người dùng cuối, kiểm tra quyền nghiệp vụ và giới hạn dữ liệu phù hợp. Một query có `WHERE id = ?` cùng PreparedStatement không tự bảo đảm người gọi được xem đơn hàng đó.

PreparedStatement xử lý tham số giá trị; nếu ứng dụng cho phép chọn tên cột, bảng hoặc chiều sắp xếp động, phải kiểm soát bằng danh sách cho phép. Không nối trực tiếp các phần SQL tùy ý từ request.

### 12.3. Thu hồi quyền có xét ảnh hưởng của role

Ví dụ trong một thay đổi đã được đánh giá:

~~~sql
REVOKE UPDATE
ON orders.purchase_order
FROM 'orders_runtime';
~~~

Lệnh thay đổi role, nên ảnh hưởng đến các account sử dụng role đó. Nếu chỉ muốn bỏ toàn bộ role khỏi một account, dùng thao tác khác:

~~~sql
REVOKE 'orders_runtime'
FROM 'orders_app'@'10.20.1.25';
~~~

Hai lệnh minh họa hai phạm vi thay đổi; không chạy liên tiếp như quy trình mặc định. Cần biết account còn quyền trực tiếp hoặc role khác nào có thể cấp lại cùng khả năng.

Sau thay đổi, kiểm tra bằng một kết nối mới và account đúng nguồn. Thời điểm các loại thay đổi privilege có hiệu lực trên phiên đang mở không hoàn toàn giống nhau; không coi việc kiểm tra một session cũ là bằng chứng duy nhất.

Không cần `FLUSH PRIVILEGES` sau các lệnh quản lý account/grant chuẩn như CREATE USER, GRANT và REVOKE. Không sửa trực tiếp grant table để né giới hạn quản trị của dịch vụ.

### 12.4. Khóa account và xử lý phiên đang tồn tại

Ví dụ:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25' ACCOUNT LOCK;
~~~

Account lock ngăn xác thực mới, không tự chấm dứt các phiên hiện hữu. [Account locking trong MySQL](https://dev.mysql.com/doc/refman/8.4/en/account-locking.html).

Khi ngừng một ứng dụng hoặc xử lý sự cố lộ thông tin xác thực, quy trình có thể cần thêm dừng workload, thu hồi secret và chấm dứt các session liên quan bằng quyền quản trị được hỗ trợ.

Không tự dùng một câu lock làm bằng chứng đã cắt mọi truy cập. Phải xác nhận cả connection mới và session còn sống.

Nếu cần mở khóa sau khi đã xử lý nguyên nhân:

~~~sql
ALTER USER 'orders_app'@'10.20.1.25' ACCOUNT UNLOCK;
~~~

### 12.5. Xóa account

Chỉ xóa sau khi xác nhận không còn sử dụng và đã đánh giá phụ thuộc:

~~~sql
DROP USER 'orders_app'@'10.20.1.25';
~~~

Kiểm tra job, secret, pool, script triển khai và các đối tượng có DEFINER liên quan nếu có. Không giả định xóa account sẽ tự dọn mọi object hoặc mọi dữ liệu nó từng tạo.

Với các account cùng tên nhưng khác host, phải rà từng account. Xóa một host không có nghĩa đã xóa tất cả đường xác thực của tên user đó.

## 13. Chẩn đoán theo lớp, không mở rộng quyền ngẫu nhiên

### 13.1. Thứ tự kiểm tra

~~~text
Cấu hình driver và URL
    -> phân giải endpoint
    -> đường mạng và TCP port
    -> TLS và certificate
    -> authentication/account host
    -> schema, role và privilege
    -> pool, transaction và hành vi nghiệp vụ
~~~

Thứ tự này giúp giới hạn phạm vi điều tra. Ví dụ, một lỗi certificate xảy ra trước truy vấn không được sửa bằng GRANT SELECT.

### 13.2. Bảng triệu chứng

| Triệu chứng | Hướng kiểm tra đầu tiên | Cách sửa thiếu căn cứ cần tránh |
| --- | --- | --- |
| Không phân giải được host | Endpoint, DNS của VM/container và private zone | Đổi sang IP tùy ý rồi bỏ identity verification |
| TCP timeout | Route, NSG/security list, firewall, VPN/Bastion và port | Mở database cho toàn internet |
| Connection refused | Đúng endpoint/port và trạng thái dịch vụ | Đổi password nhiều lần |
| PKIX/path validation failure | Truststore, CA chain, thời hạn và file runtime đang đọc | Tắt xác minh certificate |
| Hostname/identity mismatch | Host trong URL có khớp certificate không | Dùng VERIFY_CA như thể đã đạt yêu cầu identity |
| Access denied khi login | Password, account host, plugin và trạng thái account | GRANT ALL cho một account không chắc đang được chọn |
| Login được nhưng không chọn được schema | Tên database và quyền tới schema/đối tượng | Dùng administrator làm runtime |
| SELECT/INSERT bị từ chối | Grant trực tiếp, role gán và role active | Thêm quyền toàn server |
| Too many connections | Tổng pool, leak, thời gian giữ connection và giới hạn DB | Chỉ tăng pool ở mọi replica |
| Vượt giới hạn user connection | MAX_USER_CONNECTIONS và account đang chia sẻ | Tạo account mới không giới hạn để né |
| Pool chờ lâu | Connection đang giữ, SQL chậm, lock và leak | Tăng request timeout vô hạn |
| Mất kết nối sau bảo trì | Endpoint, stale connection, retry và trạng thái transaction | Retry mù mọi thao tác ghi |
| No suitable driver | Dependency, runtime classpath và URL scheme | Đổi rule mạng |

Lỗi cụ thể còn phụ thuộc driver, server và cấu hình. Dùng SQLState, mã lỗi, thời điểm, endpoint định danh và correlation ID làm bằng chứng; không đưa password hoặc toàn bộ nội dung secret vào ticket.

### 13.3. Access denied: kiểm tra đúng account

Khi quản trị viên kiểm tra:

1. Xác định nguồn kết nối thực mà server thấy.
2. Rà account có tên và host phù hợp.
3. Kiểm tra password/phiên bản secret đang được workload dùng.
4. Kiểm tra authentication plugin, lock và password expiry.
5. Sau khi login được, kiểm tra CURRENT_USER, CURRENT_ROLE và grant.

Một account host cụ thể có thể được chọn thay vì account rộng cùng tên. Không chỉ sửa account `@'%'` rồi cho rằng mọi nguồn dùng cùng grant.

Không in password ra log để “so sánh” hai cấu hình. Có thể đối chiếu phiên bản secret và dấu vết triển khai mà không tiết lộ giá trị.

### 13.4. Kết nối thành công trên CLI nhưng Java lỗi

So sánh các điểm khác nhau:

- CLI và JVM có chạy cùng mạng và DNS không?
- Có dùng cùng endpoint, port và account host không?
- CLI dùng CA file nào, Java dùng truststore nào?
- Java có đang chạy image cũ hoặc secret cũ không?
- Driver có hỗ trợ plugin xác thực và TLS của DB system không?
- Java có cấu hình khác bị framework hoặc JDBC URL ghi đè không?

Thử nghiệm phải tái hiện điều kiện của ứng dụng. Một kết nối từ laptop qua tunnel với user quản trị không đại diện cho backend trên Compute/OKE dùng runtime account.

## 14. Giám sát kết nối và giới hạn chi phí vận hành

### 14.1. Các chỉ số cần theo dõi

| Lớp | Chỉ số hữu ích |
| --- | --- |
| Ứng dụng | Request latency, tỷ lệ lỗi, timeout và retry |
| Pool | Active/idle, pending, acquisition time, connection creation failure |
| Database | Connection đang mở/chạy, lỗi kết nối, truy vấn chậm, lock wait |
| Bảo mật | Login thất bại, account bị khóa, thay đổi user/role/grant |
| Certificate | Thời hạn, lỗi trust và thời điểm cập nhật CA |
| Secret | Phiên bản triển khai, lỗi đọc secret và kết quả rotation |

Đặt cảnh báo có người nhận và runbook. Trước khi tăng compute hoặc đổi shape do lỗi “database chậm”, kiểm tra pool cạn, leak, lock hoặc SQL không phù hợp.

Có thể quan sát một số trạng thái MySQL bằng danh tính có quyền phù hợp:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Connection_errors%';
~~~

Các chỉ số global phản ánh toàn server, không riêng một ứng dụng. Trong dịch vụ được quản lý, dùng thêm metric chính thức của dịch vụ và telemetry từ pool để phân biệt nguyên nhân.

Không cấp cho runtime quyền quan sát mọi session hoặc nội dung SQL của các ứng dụng khác chỉ để làm dashboard.

### 14.2. Kiểm soát connection storm

Sau deployment hoặc gián đoạn mạng, nhiều replica có thể đồng thời tạo lại pool.

Hướng kiểm soát:

- Khởi tạo và rollout theo mức song song phù hợp.
- Giới hạn pool theo ngân sách đã tính.
- Retry có backoff/jitter và số lần hữu hạn.
- Dành connection cho thao tác vận hành.
- Theo dõi tốc độ tạo connection, không chỉ tổng connection mở.

Pool idle quá lớn cũng tiêu thụ tài nguyên server. Giữ đủ để đáp ứng tải, rồi đo và điều chỉnh thay vì sao chép cấu hình pool của hệ thống khác.

## 15. Thực hành từ endpoint đến vòng đời account

### 15.1. Điều kiện thực hành

Chuẩn bị môi trường học tập có:

- Một MySQL DB system đang hoạt động.
- Đường mạng từ máy chạy ứng dụng tới endpoint.
- Danh tính quản trị có quyền cần thiết trong phạm vi dịch vụ.
- MySQL client, JDK và Connector/J tương thích.
- Certificate/CA cùng hostname đáp ứng phép kiểm tra identity.
- Cơ chế truyền bí mật không ghi vào repository.

Các thao tác database trong bài là hướng dẫn cho môi trường thực hành. Chưa có những điều kiện trên thì có thể đọc và lập cấu hình, nhưng chưa được báo kết nối thực tế đã kiểm chứng.

### 15.2. Trình tự

1. Ghi endpoint, port, nguồn ứng dụng và cấu hình certificate.
2. Kiểm tra DNS, route và rule mạng cần thiết.
3. Tạo schema/bảng mẫu bằng danh tính triển khai phù hợp.
4. Tạo role runtime, account host cụ thể và default role.
5. Đăng nhập bằng client với identity verification.
6. Ghi CURRENT_USER, CURRENT_ROLE, TLS cipher và kết quả SELECT.
7. Chạy ví dụ Java với cùng endpoint, secret và truststore.
8. Trong schema thử, kiểm tra runtime không được tạo bảng.
9. Tính tổng connection ở replica bình thường, autoscale tối đa và rolling deployment.
10. Diễn tập password rotation, buộc tạo connection mới và xác nhận credential cũ không còn dùng được sau khi kết thúc.
11. Diễn tập khóa account, quan sát khác biệt giữa session hiện hữu và login mới.
12. Dọn đối tượng/account thử bằng danh tính quản trị sau khi hoàn tất.

Không để nguyên account demo hoặc password tạm sau thực hành nếu không còn nhu cầu. Khi dọn, kiểm tra đúng schema và host để tránh tác động tài khoản đang dùng chung tên.

### 15.3. Bằng chứng hoàn thành

| Hạng mục | Điều kiện xác nhận |
| --- | --- |
| Đường mạng | Ứng dụng tới đúng endpoint qua nguồn và port đã duyệt |
| TLS | Client yêu cầu VERIFY_IDENTITY, CA hợp lệ và danh tính endpoint khớp |
| Account | CURRENT_USER đúng account host dự kiến |
| Role | Role cần thiết active ở kết nối mới |
| Quyền cho phép | Thao tác nghiệp vụ mẫu thành công |
| Quyền bị cấm | DDL thử bị từ chối với runtime |
| Java | Truy vấn thành công, tài nguyên được đóng và không log bí mật |
| Pool | Có ngân sách cho số replica tối đa và phần dự phòng |
| Rotation | Credential mới tạo được kết nối, credential cũ bị loại sau chuyển tiếp |
| Thu hồi | Đã phân biệt cắt login mới với chấm dứt session hiện hữu |

Nếu chỉ chứng minh được TCP port mở, chưa hoàn thành kiểm tra TLS, xác thực và quyền. Nếu chỉ đăng nhập bằng administrator, chưa chứng minh runtime account vận hành đúng.

## 16. Các nguyên tắc cần vận dụng

Kết nối MySQL từ ứng dụng là một chuỗi kiểm soát liên tục: **đúng endpoint, đúng đường mạng, đúng certificate, đúng account và đúng quyền**.

Giữ tài khoản quản trị ngoài runtime, quản lý quyền bằng nhu cầu nghiệp vụ và role rõ ràng. Tách bí mật khỏi code nhưng vẫn phải thiết kế refresh, rotation và thu hồi. Dùng pool có giới hạn, timeout theo mục đích và retry hiểu trạng thái transaction.

Khi có lỗi, dựa vào bằng chứng của từng lớp để sửa. Một kết nối đã mã hóa, một user đăng nhập được và một ứng dụng có thể phục vụ ổn định là ba mức kết quả cần kiểm chứng riêng.
