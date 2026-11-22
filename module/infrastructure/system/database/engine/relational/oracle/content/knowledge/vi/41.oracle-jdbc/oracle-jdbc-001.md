# Chọn Oracle JDBC driver theo JDK và ma trận tương thích database

Khi một ứng dụng Java kết nối Oracle Database, việc chọn JDBC driver cần xét đồng thời ba yếu tố:

1. **JDK của ứng dụng**: driver JAR phải chạy được trên Java runtime đang triển khai.
2. **Phiên bản Oracle Database**: tổ hợp driver/database phải nằm trong ma trận tương thích hoặc được Oracle xác nhận cho release cụ thể.
3. **Tính năng và chính sách hỗ trợ**: JDBC API level, Thin/OCI, UCP, TLS/wallet, kiểu dữ liệu Oracle và thời hạn hỗ trợ phải phù hợp với ứng dụng.

Tên file như ojdbc8.jar, ojdbc11.jar hay ojdbc17.jar chủ yếu chỉ dòng JAR tương ứng với mức Java được biên dịch/hỗ trợ. Con số trong tên file **không phải** phiên bản Oracle Database và cũng không trực tiếp cho biết driver release. Ví dụ, một bản driver 26ai có thể cung cấp cả ojdbc8.jar, ojdbc11.jar và ojdbc17.jar để phục vụ nhiều JDK khác nhau.

Oracle khuyến nghị dùng bản JDBC driver mới nhất có hỗ trợ JDK và database mà ứng dụng đang dùng, đồng thời phù hợp với yêu cầu hỗ trợ của tổ chức. Không chọn driver chỉ bằng cách nhìn phiên bản database hoặc copy một JAR từ ứng dụng khác.

## 1. JDBC driver nằm ở đâu trong kiến trúc kết nối?

JDBC là API chuẩn của Java cho truy cập cơ sở dữ liệu. Ứng dụng gọi các interface trong java.sql và javax.sql; JDBC driver hiện thực các interface đó để giao tiếp với Oracle Database.

Luồng kết nối JDBC Thin điển hình:

~~~text
Java application
      |
      v
JDBC API (java.sql / javax.sql)
      |
      v
Oracle JDBC driver (ojdbcX.jar)
      |
      v
Oracle Net over TCP/IP or TCPS
      |
      v
Listener / database service
      |
      v
Oracle Database
~~~

JDBC driver chịu trách nhiệm chuyển lời gọi JDBC thành giao thức và thông điệp mà Oracle Database hiểu. Driver cũng xử lý mapping kiểu dữ liệu, bind variable, transaction, metadata, statement, result set và các extension đặc thù Oracle.

### 1.1. Ba phiên bản độc lập cần phân biệt

- **JDK version**: Java runtime/compiler mà ứng dụng sử dụng, ví dụ JDK 8, 11, 17, 21 hoặc 25.
- **JDBC specification version**: chuẩn API mà driver triển khai, ví dụ JDBC 4.2 hoặc JDBC 4.3.
- **Oracle JDBC driver release**: dòng phát hành của driver, ví dụ 19c, 21c, 23ai/26ai.

Ví dụ, ojdbc17.jar thuộc dòng JAR cho JDK 17 trở lên theo chứng nhận cụ thể của release. Nó có thể triển khai JDBC 4.3 và có thể kết nối tới nhiều phiên bản database theo ma trận tương thích. Không có nghĩa nó chỉ kết nối với Oracle Database 17.

### 1.2. Driver không thay thế database feature

Driver mới có thể kết nối với database cũ nếu tổ hợp được hỗ trợ, nhưng không thể tạo ra tính năng mà database server không có. Ví dụ, một kiểu dữ liệu hoặc SQL feature chỉ được giới thiệu ở database release mới sẽ không tự xuất hiện trên database cũ chỉ vì ứng dụng dùng JDBC driver mới.

Tương tự, việc kết nối thành công không chứng minh mọi tính năng đặc thù, authentication method, datatype hoặc HA feature đều được chứng nhận cho tổ hợp đó.

## 2. Quy trình chọn driver

Thực hiện theo thứ tự sau để thu hẹp lựa chọn:

1. Xác định JDK thực tế của tiến trình chạy ứng dụng, không chỉ JDK trên máy phát triển.
2. Chọn các JAR Oracle JDBC được chứng nhận với JDK đó.
3. Đối chiếu driver release với phiên bản Oracle Database theo interoperability/certification matrix.
4. Kiểm tra JDBC API level và tính năng ứng dụng cần dùng.
5. Chọn Thin hoặc OCI theo yêu cầu kết nối.
6. Chọn artifact và companion JAR cần thiết cho pooling, TLS/wallet, NLS hoặc HA.
7. Pin phiên bản trong Maven/Gradle và kiểm tra dependency tree để loại trùng JAR.
8. Kiểm thử trên đúng JDK, database release, service, authentication và môi trường triển khai.
9. Ghi lại driver version, database version, JDK version và kết quả kiểm thử để phục vụ nâng cấp.

Không suy luận tương thích chỉ từ việc compile thành công. Compiler có thể tìm thấy class và method nhưng runtime, database protocol hoặc tính năng server vẫn có thể không tương thích.

## 3. Các Oracle JDBC JAR phổ biến theo JDK

Bảng sau mô tả lựa chọn trong dòng Oracle JDBC 26ai hiện hành tại thời điểm biên soạn. Chứng nhận có thể thay đổi theo quarterly release; luôn kiểm tra đúng release notes của artifact sẽ triển khai.

| JDK chạy ứng dụng | JAR nên xem xét | JDBC API | Ghi chú |
| --- | --- | --- | --- |
| JDK 8 | ojdbc8.jar | JDBC 4.2 | Lựa chọn cho ứng dụng còn chạy Java 8 |
| JDK 11 | ojdbc11.jar | JDBC 4.3 | Phù hợp khi cần JDBC 4.3; ojdbc8 cũng có thể chạy nhưng chỉ cung cấp JDBC 4.2 |
| JDK 17 | ojdbc17.jar | JDBC 4.3 | Lựa chọn mặc định cho ứng dụng Java 17 mới |
| JDK 19 | ojdbc17.jar | JDBC 4.3 | Được liệt kê trong chứng nhận của dòng driver hiện hành |
| JDK 21 | ojdbc17.jar hoặc ojdbc11.jar | JDBC 4.3 | Chọn theo API baseline và chứng nhận release cụ thể |
| JDK 25 | ojdbc17.jar | JDBC 4.3 | Trang tải 26ai hiện liệt kê JDK 25; kiểm tra release notes và các giới hạn companion artifact |

Thông tin cụ thể trên trang tải Oracle JDBC 26ai hiện ghi:
- ojdbc17.jar: JDBC 4.3; chứng nhận JDK 17, 19, 21 và 25; tương thích Jakarta APIs.
- ojdbc11.jar: JDBC 4.3; chứng nhận JDK 11 và 21.
- ojdbc8.jar: JDBC 4.2; chứng nhận JDK 8 và 11.

Oracle JDBC Developer's Guide 26ai cũng liệt kê ojdbc17 cho JDK 17/19/21, ojdbc11 cho JDK 11 và ojdbc8 cho JDK 8/11. Bảng trong Developer's Guide và trang Downloads chưa hoàn toàn đồng nhất về JDK 21/25. Vì vậy, với JDK 21 hoặc 25, hãy xác minh release notes của đúng JAR tải về; không áp dụng một bảng cũ cho mọi quarterly release.

### 3.1. ojdbc8.jar

Dùng khi:
- Ứng dụng phải chạy trên JDK 8.
- Cần JDBC 4.2.
- Framework hoặc application server chưa thể nâng lên JDK mới hơn.
- Driver release được chọn có chứng nhận với database server đang dùng.

ojdbc8.jar có thể chạy trên JDK 11 trong các tổ hợp được chứng nhận, nhưng nó vẫn triển khai JDBC 4.2. Nếu ứng dụng cần API JDBC 4.3, chọn JAR phù hợp hơn như ojdbc11 hoặc ojdbc17.

### 3.2. ojdbc11.jar

Dùng khi:
- Ứng dụng chạy trên JDK 11.
- Cần JDBC 4.3.
- Muốn dùng một driver baseline JDK 11 trên các JDK được release chứng nhận.

Một số quarterly release chứng nhận ojdbc11 với JDK 21. Không mặc định mọi bản ojdbc11 cũ đều chạy hoặc được hỗ trợ trên JDK 21; kiểm tra đúng release.

### 3.3. ojdbc17.jar

Dùng khi:
- Ứng dụng chạy JDK 17 trở lên trong phạm vi JDK được chứng nhận.
- Cần JDBC 4.3.
- Muốn dùng driver mới với các Jakarta API integration được hỗ trợ.
- Ứng dụng đang nâng cấp lên JDK 17, 21 hoặc 25.

Tên ojdbc17 thể hiện dòng JAR biên dịch cho Java 17 baseline, không có nghĩa chỉ chạy trên đúng JDK 17. Các JDK mới hơn được hỗ trợ khi Oracle chứng nhận cho release tương ứng.

### 3.4. ojdbc10.jar và các JAR cũ

ojdbc10.jar thuộc dòng Oracle JDBC 19c và chỉ nên xem xét khi cần duy trì một hệ thống legacy có ràng buộc cụ thể. Tài liệu Oracle liệt kê ojdbc10 cho JDK 11 và 17 ở dòng 19c. Với ứng dụng mới, ưu tiên dòng JAR hiện hành tương ứng với JDK thay vì chọn ojdbc10 chỉ vì tên có số 10.

Các JAR như ojdbc6.jar, ojdbc7.jar và ojdbc5.jar thuộc những thế hệ Java cũ. Nếu ứng dụng còn phụ thuộc chúng, cần lập kế hoạch nâng cấp JDK, driver và database; không dùng các JAR legacy cho một dự án mới.

## 4. Ma trận tương thích JDBC driver và Oracle Database

Tương thích driver/database là phép kiểm tra riêng với tương thích driver/JDK. Sau khi chọn được JAR chạy trên JDK, vẫn phải kiểm tra driver release có được chứng nhận với database release hay không.

### 4.1. Ma trận trong Oracle JDBC Developer's Guide 26ai

Oracle JDBC Developer's Guide 26ai công bố interoperability matrix sau:

| JDBC driver release | Database 26.x | Database 21.x | Database 19.x |
| --- | --- | --- | --- |
| JDBC 26 | Yes | Yes | Yes |
| JDBC 21.x | Yes | Yes | Yes |
| JDBC 19.x | Yes | Yes | Yes |

Ma trận này thể hiện các tổ hợp được Oracle liệt kê trong tài liệu 26ai. Driver release không nhất thiết phải có cùng số với database release.

### 4.2. Lưu ý riêng với Oracle Database 23ai

Trang Oracle JDBC Downloads cho gói 26ai hiện ghi driver release 26ai hỗ trợ Oracle Database 26ai, 23ai, 21c và 19c. Trong khi đó, bảng interoperability trong Developer's Guide 26ai chỉ liệt kê 26.x, 21.x và 19.x, không có cột 23.x.

Với database 23ai, hãy kiểm tra JDBC-UCP Release Notes của đúng gói 26ai và xác nhận tổ hợp cụ thể trước khi đưa vào production. Không nên tự kết luận không hỗ trợ chỉ vì một bảng không liệt kê, cũng không nên bỏ qua khác biệt giữa hai trang tài liệu.

Oracle JDBC FAQ có ma trận riêng cho dòng driver 23.x:

| JDBC driver release | Database 23.x | Database 21.x | Database 19.x | Database 18.3 | Database 12.2/12.1 |
| --- | --- | --- | --- | --- | --- |
| JDBC 23.x | Yes | Yes | Yes | No | No |
| JDBC 21.x | Yes | Yes | Yes | Was | Was |
| JDBC 19.x | Yes | Yes | Yes | Was | Was |
| JDBC 18.x | No | Was | Was | Was | Was |
| JDBC 12.2/12.1 | No | Was | Was | Was | Was |

Trong FAQ, trạng thái Was có nghĩa tổ hợp từng được hỗ trợ nhưng hiện không còn được bao phủ bởi các mức hỗ trợ Oracle tương ứng; không được hiểu là một chứng nhận hỗ trợ hiện hành. Với database cũ như 18c, 12c hoặc 11g, cần kiểm tra chính sách hỗ trợ và ma trận lịch sử trước khi giữ lại driver cũ.

### 4.3. Vì sao không nên chỉ chọn driver cùng số với database?

Ví dụ:
- Oracle Database 19c có thể dùng driver release mới hơn nếu tổ hợp được chứng nhận.
- Oracle Database 26ai có thể dùng JDBC 21.x hoặc 19.x theo ma trận 26ai đã công bố.
- Ứng dụng chạy JDK 8 vẫn cần JAR hỗ trợ JDK 8, ngay cả khi database là 26ai.

Chọn theo ma trận và JDK, không chọn theo quy tắc “19c phải dùng ojdbc19” hoặc “database 21c phải dùng ojdbc21”.

### 4.4. Tương thích không đồng nghĩa thời hạn hỗ trợ

Một driver/database pair có thể kết nối được nhưng database release hoặc driver release đã hết giai đoạn hỗ trợ. Khi lập kế hoạch production, kiểm tra riêng:
- Driver release có nằm trong dòng Oracle đang hỗ trợ không.
- Database release có còn Premier/Extended Support hoặc hỗ trợ phù hợp không.
- Có quarterly security/bug fix mới không.
- Tổ chức có yêu cầu chứng nhận từ Oracle Support hoặc vendor application không.

Không dùng kết quả smoke test thành công để thay thế chính sách support/certification.

## 5. Chọn Thin hay OCI driver

Oracle cung cấp nhiều kiểu JDBC driver. Với ứng dụng Java client thông thường, Oracle khuyến nghị JDBC Thin trừ khi có yêu cầu đặc thù chỉ OCI đáp ứng.

### 5.1. JDBC Thin (Type 4)

Đặc điểm:
- Pure Java.
- Không cần cài Oracle Client ở máy chạy ứng dụng.
- Dùng Oracle Net trên TCP/IP hoặc TCPS.
- Dễ đóng gói trong ứng dụng, container và cloud runtime.
- Có tính di động cao giữa Linux, Windows và các nền tảng JVM được hỗ trợ.

Ví dụ URL:

~~~java
String url = "jdbc:oracle:thin:@//dbhost.example.com:1521/app_service";
~~~

Thin driver cần listener TCP/IP ở phía database và service name hợp lệ.

### 5.2. JDBC OCI (Type 2)

OCI driver gọi Oracle Call Interface qua native library. Nó cần:
- Oracle Client hoặc Instant Client tương thích.
- Native OCI libraries đúng nền tảng và kiến trúc.
- Library path được cấu hình đúng.
- Phiên bản client/library phù hợp với hệ điều hành.

Chỉ chọn OCI khi ứng dụng thực sự cần tính năng đặc thù của OCI, ví dụ môi trường Oracle Client hiện hữu hoặc adapter/protocol không được Thin hỗ trợ. OCI làm deployment phức tạp hơn do phụ thuộc native library.

Oracle có thông báo deprecation liên quan JDBC-OCI/Type 2 driver trong tài liệu hỗ trợ. Trước khi bắt đầu dự án mới dùng OCI, kiểm tra MOS note 2953282.1 và chính sách hỗ trợ hiện hành.

### 5.3. So sánh

| Tiêu chí | Thin | OCI |
| --- | --- | --- |
| Kiểu driver | Type 4, pure Java | Type 2, Java + native code |
| Oracle Client ở client host | Không cần | Cần |
| TCP/IP và TCPS | Có | Có |
| Phụ thuộc OS/native library | Thấp | Cao |
| Portability/container | Thuận lợi | Cần đóng gói native client |
| Lựa chọn mặc định | Được Oracle khuyến nghị | Chỉ khi có yêu cầu OCI-specific |

## 6. Chọn dependency từ Maven Central

Oracle phát hành JDBC artifacts trên Maven Central. Group ID thường dùng là com.oracle.database.jdbc. Cần pin version cụ thể và dùng cùng một dòng release cho driver, UCP và companion artifacts.

### 6.1. Maven dependency tối thiểu

Ví dụ cho ứng dụng JDK 17 dùng ojdbc17. Phiên bản 23.26.4.0.0 là một bản 26ai JDBC release đang được liệt kê trên Maven Central tại thời điểm biên soạn; hãy kiểm tra version mới nhất trước khi triển khai:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>23.26.4.0.0</version>
</dependency>
~~~

Với JDK 11, chọn artifact ojdbc11. Với JDK 8, chọn ojdbc8. Không thêm đồng thời nhiều driver artifact vào runtime classpath nếu không có lý do đặc biệt.

### 6.2. Maven với production companion dependencies

Oracle cung cấp các artifact dạng production POM để kéo JDBC driver và các companion JAR cần thiết cho các use case được định nghĩa:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17-production</artifactId>
    <version>23.26.4.0.0</version>
    <type>pom</type>
</dependency>
~~~

Dùng production POM khi ứng dụng cần các companion artifacts do Oracle chỉ định. Nếu chỉ dùng JDBC Thin cơ bản, JAR ojdbc chính có thể đã đủ; không thêm thư viện chỉ vì chúng xuất hiện trong một gói full archive.

### 6.3. Maven với UCP

Nếu sử dụng Oracle Universal Connection Pool cùng ojdbc17:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc17</artifactId>
        <version>23.26.4.0.0</version>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ucp17</artifactId>
        <version>23.26.4.0.0</version>
    </dependency>
</dependencies>
~~~

Chọn UCP artifact tương ứng với dòng JDK/driver: ucp17 đi với ojdbc17, ucp11 đi với ojdbc11, và ucp.jar với dòng ojdbc8 tương ứng. Kiểm tra release notes của cùng version để xác nhận chứng nhận JDK.

### 6.4. Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.database.jdbc
~~~

Tìm các trường hợp:
- Hai version ojdbc cùng xuất hiện.
- Framework kéo một driver cũ gián tiếp.
- UCP không cùng release family với ojdbc.
- Companion JAR bị trùng version.
- Một dependency đóng gói ojdbc trong shaded/fat JAR trong khi ứng dụng cũng khai báo ojdbc.

Giữ một driver version rõ ràng trong runtime. Nếu một thư viện bên thứ ba khai báo driver khác, xử lý dependency mediation hoặc exclusion có kiểm soát.

## 7. Gradle dependency

Ví dụ cho ứng dụng JDK 17:

~~~groovy
dependencies {
    implementation("com.oracle.database.jdbc:ojdbc17:23.26.4.0.0")
}
~~~

Thêm UCP khi cần:

~~~groovy
dependencies {
    implementation("com.oracle.database.jdbc:ojdbc17:23.26.4.0.0")
    implementation("com.oracle.database.jdbc:ucp17:23.26.4.0.0")
}
~~~

Xem runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight \
    --dependency ojdbc \
    --configuration runtimeClasspath
~~~

Đảm bảo Gradle toolchain, compiler và runtime của ứng dụng dùng JDK đúng như môi trường triển khai. Máy build có thể dùng JDK 21 trong khi container production lại chạy JDK 17; kiểm tra cả hai.

## 8. Companion JAR và khi nào cần chúng

ojdbc JAR cung cấp driver chính. Một số tính năng cần thêm thư viện đi kèm.

| Artifact | Công dụng điển hình |
| --- | --- |
| ucp17/ucp11/ucp | Oracle Universal Connection Pool |
| orai18n | Globalization/NLS support cho các trường hợp cần bổ sung |
| oraclepki | Oracle PKI/wallet support trong các cấu hình tương ứng |
| osdt_core, osdt_cert | Thành phần bảo mật Oracle dùng với một số wallet/certificate setup |
| ons | Oracle Notification Service cho các tính năng HA tương ứng |
| simplefan | Fast Application Notification integration |
| xdb, xmlparserv2 | Một số chức năng XML/Oracle XML DB |
| rsi | Reactive Streams Ingestion cho workload ingest tương ứng |

Không phải ứng dụng nào cũng cần tất cả companion JAR. Xác định tính năng cần dùng rồi thêm đúng artifact theo Oracle Maven Central Guide và tài liệu của tính năng đó.

### 8.1. Wallet và TLS

Nếu kết nối TCPS hoặc dùng Oracle Wallet, có thể cần các thư viện security companion tương ứng và cấu hình wallet/truststore. Không copy một bộ JAR bảo mật ngẫu nhiên từ Oracle Home cũ sang ứng dụng mới; phải dùng đúng bộ artifact/version được tài liệu hỗ trợ.

### 8.2. NLS và dữ liệu quốc tế

Ứng dụng lưu tiếng Việt có dấu hoặc dữ liệu Unicode thường dùng Thin driver với Unicode support tích hợp. Một số Oracle object/collection types và character set đặc thù có thể cần orai18n. Xác định nhu cầu thực tế và kiểm tra tài liệu NLS của driver release.

### 8.3. UCP không phải JDBC driver

UCP là connection pool. Nó quản lý vòng đời và tái sử dụng connection; ojdbc vẫn là driver giao tiếp database. Cài UCP không thay thế ojdbc.

## 9. Xác định JDK thực tế

Một lỗi phổ biến là chọn driver theo JDK cài trên laptop nhưng ứng dụng production chạy bằng JDK khác.

### 9.1. Kiểm tra Java runtime

~~~bash
java -version
~~~

Kiểm tra compiler:

~~~bash
javac -version
~~~

Kiểm tra Maven đang dùng JDK nào:

~~~bash
mvn -version
~~~

Với Gradle:

~~~bash
./gradlew -version
~~~

Các lệnh này giúp xác định toolchain, nhưng môi trường production vẫn cần được kiểm tra riêng. Có thể ghi version lúc ứng dụng khởi động:

~~~java
System.out.println("Runtime Java: " + Runtime.version());
~~~

### 9.2. Build JDK và runtime JDK

Maven/Gradle có thể compile bằng một JDK nhưng đóng gói ứng dụng chạy bằng JDK khác. Driver phải tương thích với runtime JVM cuối cùng, không chỉ compiler.

Ví dụ:
- Compile bằng JDK 21.
- Container production chạy JDK 17.
- Nếu driver cần JDK 21 bytecode, ứng dụng sẽ lỗi khi chạy trên JDK 17.

Ngược lại, một driver baseline JDK 17 có thể chạy trên JDK mới hơn nếu Oracle chứng nhận release đó.

### 9.3. Java bytecode version

JDK không đọc được class file được biên dịch cho Java release mới hơn. Lỗi thường gặp là UnsupportedClassVersionError. Đây là dấu hiệu cần kiểm tra class version và runtime JDK, không phải lỗi network/database.

## 10. Xác định phiên bản Oracle Database

Không dựa vào tên service hoặc tên môi trường như PROD/DEV để suy ra database version.

Có thể hỏi DBA hoặc truy vấn:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Hoặc từ JDBC:

~~~java
DatabaseMetaData meta = connection.getMetaData();

System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
~~~

Với môi trường multitenant, kết nối tới service/PDB thực tế mà ứng dụng dùng. Database home version, CDB/PDB compatibility và service endpoint có thể là các thông tin khác nhau cần ghi nhận.

### 10.1. Ghi lại DB identity

Trong hệ thống có nhiều database:
- DB_NAME và DB_UNIQUE_NAME.
- Database release và RU.
- Service name.
- CDB/PDB nếu có.
- Primary/standby role nếu dùng Data Guard.
- RAC/SCAN endpoint nếu có.

Ma trận tương thích cần được áp dụng cho database server thật sự nhận kết nối.

## 11. Xác định version của JDBC driver

Oracle hướng dẫn có thể chạy JAR trực tiếp để xem version:

~~~bash
java -jar ojdbc17.jar
~~~

Tương tự:

~~~bash
java -jar ojdbc11.jar
java -jar ojdbc8.jar
~~~

Trong ứng dụng, đọc metadata:

~~~java
DatabaseMetaData meta = connection.getMetaData();

System.out.println("Driver name: " + meta.getDriverName());
System.out.println("Driver version: " + meta.getDriverVersion());
System.out.println("JDBC API: " +
    meta.getJDBCMajorVersion() + "." +
    meta.getJDBCMinorVersion());
System.out.println("Database: " + meta.getDatabaseProductVersion());
~~~

Đây là cách hữu ích để xác minh runtime thực tế đang nạp driver nào. Nó cũng giúp phát hiện server application hoặc container đang dùng JAR cũ từ shared library.

## 12. Kiểm tra kết nối JDBC Thin tối thiểu

Một smoke test nhỏ nên xác minh:
- JDK chạy được.
- Driver được load.
- URL/service hợp lệ.
- Authentication hoạt động.
- Listener/network thông suốt.
- Database trả kết quả.

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class OracleJdbcSmokeTest {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("DB_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {

            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("Driver: " + meta.getDriverName());
            System.out.println("Driver version: " + meta.getDriverVersion());
            System.out.println("Database: " +
                               meta.getDatabaseProductVersion());

            try (Statement statement = connection.createStatement();
                 ResultSet result =
                     statement.executeQuery("SELECT SYSDATE FROM DUAL")) {

                if (result.next()) {
                    System.out.println("Database time: " +
                                       result.getTimestamp(1));
                }
            }
        }
    }
}
~~~

JDBC 4 tự đăng ký driver qua service provider khi JAR nằm trong classpath/module path đúng cách. Ứng dụng hiện đại thường không cần gọi Class.forName("oracle.jdbc.OracleDriver") thủ công. Chỉ dùng Class.forName nếu framework hoặc môi trường legacy yêu cầu.

### 12.1. URL dùng service name

Dạng thường dùng:

~~~text
jdbc:oracle:thin:@//hostname:1521/service_name
~~~

Ví dụ:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/salespdb.example.com
~~~

Ưu tiên service name cho môi trường có PDB, RAC hoặc service routing. SID-style URL cũ có thể tồn tại trong ứng dụng legacy nhưng không nên dùng thay cho service khi kiến trúc yêu cầu service-level routing.

### 12.2. Không ghi mật khẩu vào source code

Dùng secret manager, environment injection hoặc cấu hình bảo mật của nền tảng. Không commit DB_PASSWORD vào repository, Docker image, log hoặc command history.

## 13. DataSource và connection pool trong production

Driver là thành phần tạo connection; ứng dụng production thường nên lấy connection qua DataSource và connection pool thay vì mở một TCP/database session mới cho mỗi request.

### 13.1. OracleDataSource

Oracle cung cấp OracleDataSource. Ví dụ cấu hình cơ bản:

~~~java
import java.sql.Connection;
import oracle.jdbc.pool.OracleDataSource;

public class OracleDataSourceExample {
    public static void main(String[] args) throws Exception {
        OracleDataSource dataSource = new OracleDataSource();

        dataSource.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/app_service"
        );
        dataSource.setUser(System.getenv("DB_USER"));
        dataSource.setPassword(System.getenv("DB_PASSWORD"));

        try (Connection connection = dataSource.getConnection()) {
            System.out.println(
                connection.getMetaData().getDatabaseProductVersion()
            );
        }
    }
}
~~~

Đây là DataSource đơn giản, chưa phải pool. Với production, dùng UCP hoặc pool phù hợp với framework.

### 13.2. UCP

UCP cung cấp connection pooling và tích hợp các tính năng Oracle HA theo cấu hình được hỗ trợ. Chọn ucp artifact cùng dòng JDK/driver, cấu hình min/max pool size, timeout, validation và failover behavior theo workload.

### 13.3. Pool bên thứ ba

HikariCP và các pool khác cũng có thể dùng với Oracle JDBC Thin. Trong trường hợp đó, chỉ cần ojdbc driver cùng các companion artifacts thực sự cần thiết. Không thêm UCP nếu ứng dụng không sử dụng UCP.

### 13.4. Pool size không phải càng lớn càng tốt

Pool quá lớn có thể làm tăng session/process, PGA, contention và tải database. Chọn pool size theo concurrency, database capacity, transaction duration và số instance ứng dụng. Đặt connection timeout, idle timeout, max lifetime và validation theo hướng dẫn của pool.

## 14. Framework và application server

### 14.1. Spring Boot

Ví dụ cấu hình:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/app_service
spring.datasource.username=your_database_user
spring.datasource.password=inject_from_secret_store
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver
~~~

Đảm bảo dependency ojdbc có trong runtime classpath của ứng dụng. Spring Boot có thể tự suy ra driver từ URL trong nhiều cấu hình, nhưng khai báo rõ driver class giúp dễ kiểm tra khi môi trường phức tạp.

### 14.2. Jakarta EE / application server

Application server có thể quản lý JDBC driver ở shared module và cấu hình DataSource ở server. Khi deploy:
- Kiểm tra driver module server đang nạp.
- Kiểm tra ứng dụng có đóng gói thêm một ojdbc version khác không.
- Kiểm tra classloader isolation.
- Kiểm tra datasource JNDI và pool.
- Kiểm tra transaction manager/XA driver requirements.

Không giả định JAR trong WAR/EAR sẽ luôn được ưu tiên hơn JAR ở server module.

### 14.3. Container và Kubernetes

Với JDBC Thin:
- Đóng gói JAR trong application artifact.
- Không cần Oracle Client native library.
- Quản lý wallet/certificate bằng secret/volume an toàn nếu dùng TCPS.
- Đặt connection pool phù hợp với replica count.
- Giám sát số connection tổng từ tất cả pod.
- Kiểm tra DNS, network policy và listener/service routing.

Nếu mỗi pod tạo pool tối đa 50 connection và có 20 pod, database có thể nhận tới 1.000 connection từ service đó. Capacity planning phải tính theo toàn bộ replica, không chỉ một JVM.

## 15. TLS, wallet và authentication

JDK/driver compatibility chưa đủ để bảo đảm kết nối bảo mật hoạt động. Cần kiểm tra authentication và TLS feature support của driver/database.

### 15.1. TCP và TCPS

- TCP là kết nối Oracle Net không mã hóa ở tầng transport.
- TCPS sử dụng TLS để mã hóa và xác thực certificate server.
- Mutual TLS (mTLS) có thể yêu cầu cả client credential/wallet.

Nếu hệ thống yêu cầu TCPS, kiểm tra TLS protocol, cipher suite, truststore/wallet, certificate expiry, hostname/DN validation và network policy.

### 15.2. Oracle Wallet và companion JAR

Một số cấu hình wallet/security cần các artifact như oraclepki, osdt_core và osdt_cert. Thêm đúng version và cấu hình theo Oracle JDBC documentation; không đưa wallet private key hoặc password vào source code.

### 15.3. Authentication protocol

Driver quá cũ có thể không hỗ trợ authentication policy mới của database. Nếu gặp ORA-28040 hoặc lỗi xác thực tương tự:
- Kiểm tra JDBC driver version.
- Kiểm tra database authentication policy.
- Kiểm tra password verifier và account status.
- Đọc alert log và client error detail.
- Nâng driver theo ma trận trước khi xem xét thay đổi security policy.

Không hạ thấp chính sách xác thực database chỉ để một client cũ kết nối được nếu chưa có đánh giá bảo mật và phê duyệt.

## 16. JDBC API 4.2 và 4.3

JDBC specification version cho biết API chuẩn mà driver triển khai. Nó không phải phiên bản Oracle Database.

### 16.1. JDBC 4.2

Một số JAR như ojdbc8.jar triển khai JDBC 4.2. Ứng dụng dùng các API có từ JDBC 4.2 có thể hoạt động theo phạm vi driver hỗ trợ.

### 16.2. JDBC 4.3

ojdbc11 và ojdbc17 của các release tương ứng triển khai JDBC 4.3. Nếu ứng dụng hoặc framework cần API JDBC 4.3, không chọn ojdbc8 chỉ vì JDK runtime có thể load JAR đó.

### 16.3. API chuẩn và extension Oracle

Ứng dụng nên ưu tiên API chuẩn java.sql/javax.sql khi đủ đáp ứng. Các package Oracle như oracle.jdbc có extension cho kiểu dữ liệu, performance, LOB, object types và HA. Khi dùng extension, mức độ phụ thuộc vào driver release sẽ cao hơn; cần kiểm tra Javadoc và compatibility notes.

### 16.4. Jakarta APIs

Oracle ghi nhận ojdbc17 từ các release tương ứng có khả năng tương thích Jakarta APIs. Nếu ứng dụng dùng Jakarta EE hoặc thư viện đã chuyển từ javax sang jakarta, kiểm tra chính xác API nào được hỗ trợ và dependency tương ứng. Không đồng nhất việc driver tương thích Jakarta APIs với việc toàn bộ ứng dụng có thể đổi namespace mà không sửa code.

## 17. Kiểu dữ liệu và tính năng đặc thù Oracle

Khi nâng driver, kiểm thử các datatype ứng dụng thực sự dùng:
- NUMBER và precision/scale.
- DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE.
- CLOB/BLOB/NCLOB.
- RAW và binary data.
- ARRAY, STRUCT, REF CURSOR.
- XMLType hoặc XML-related APIs.
- JSON types và JSON APIs theo database release.
- VECTOR hoặc kiểu dữ liệu mới ở database release hỗ trợ.
- PL/SQL associative array và stored procedure binding.

Một driver mới có thể cung cấp API để biểu diễn datatype mới, nhưng database server phải có datatype/feature tương ứng. Driver cũ có thể kết nối nhưng không biết cách ánh xạ một datatype mới theo API hiện đại.

### 17.1. Kiểm tra stored procedure

Nếu ứng dụng dùng CallableStatement, REF CURSOR, array binding hoặc PL/SQL object type, thêm test cho:
- IN, OUT và IN OUT parameters.
- Null handling.
- Type mapping.
- Transaction behavior.
- LOB lifecycle.
- Cursor close.
- Error propagation.

### 17.2. Kiểm tra Unicode và NLS

Kiểm tra tiếng Việt có dấu, supplementary characters, NCHAR/NVARCHAR2, CLOB/NCLOB và character set database. Đảm bảo dữ liệu không bị chuyển mã sai khi bind hoặc đọc ResultSet.

## 18. Các lỗi thường gặp khi chọn hoặc nạp driver

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| ClassNotFoundException: oracle.jdbc.OracleDriver | JAR không có trong runtime classpath | Kiểm tra dependency tree, WAR/EAR/container module |
| No suitable driver | Driver chưa được load, URL sai hoặc JAR không nằm trong classpath | Kiểm tra URL jdbc:oracle:thin, service provider và dependency |
| UnsupportedClassVersionError | Driver hoặc dependency được compile cho JDK mới hơn runtime | Kiểm tra java -version và class-file baseline |
| NoSuchMethodError | Nhiều version driver/companion JAR xung đột | Kiểm tra runtime dependency và classloader |
| ORA-28040 | Authentication protocol/verifier không tương thích | Kiểm tra driver version và database security policy |
| ORA-12514 | Listener không nhận biết service name | Kiểm tra service registration, listener và URL |
| ORA-12541 | Không có listener tại host/port | Kiểm tra network, listener và port |
| ORA-12154 | Không phân giải được connect identifier | Kiểm tra TNS_ADMIN, tnsnames hoặc URL |
| ORA-01017 | Username/password không hợp lệ | Kiểm tra credential và account |
| ORA-17002 / I/O error | Network/socket bị gián đoạn | Kiểm tra firewall, timeout, listener và network |
| TLS handshake failure | Certificate, truststore, wallet hoặc TLS policy | Kiểm tra certificate chain, hostname, protocol và companion JAR |

### 18.1. ClassNotFoundException

Đảm bảo artifact nằm trong runtime package. Với Maven, scope provided hoặc test có thể khiến driver không được đóng gói. Với application server, driver có thể nằm trong server module thay vì WAR.

### 18.2. No suitable driver

Kiểm tra:
- URL có bắt đầu bằng jdbc:oracle:thin: hay không.
- Oracle driver có mặt ở runtime hay chỉ có ở compile time.
- Driver có được JDBC 4 service loader phát hiện không.
- Có classloader isolation hay không.
- URL có ký tự/format sai không.

### 18.3. NoSuchMethodError

Đây thường là xung đột binary dependency. Ví dụ, ojdbc17 và một companion JAR từ version cũ cùng nằm trong classpath. Xem dependency tree và danh sách JAR thực tế trong container.

### 18.4. ORA-28040

Đừng giải quyết bằng cách tự động giảm authentication version. Trước hết xác nhận driver release, database authentication settings và password verifier. Nâng driver lên release được hỗ trợ thường là bước đầu hợp lý.

## 19. Kiểm thử compatibility trước production

Một lần connect thành công chỉ là smoke test. Bộ kiểm thử cần xác nhận tính năng và tải mà ứng dụng thật sử dụng.

### 19.1. Ma trận test tối thiểu

| Hạng mục | Kiểm tra |
| --- | --- |
| JDK | Đúng runtime production |
| Driver JAR | Version và JDBC API level |
| Database | Release/RU và service thực tế |
| Connection | Thin/OCI, TCP/TCPS |
| Authentication | Password, wallet, Kerberos hoặc phương thức đang dùng |
| Datatypes | NUMBER, DATE, TIMESTAMP, LOB, JSON/object types liên quan |
| Transactions | Commit, rollback, isolation và timeout |
| Pool | Validation, timeout, leak detection và reconnect |
| HA | RAC service, FAN, failover hoặc Data Guard nếu ứng dụng dùng |
| Deployment | Classloader, container, application server |
| Performance | Batch, fetch size, LOB streaming, pool concurrency |
| Observability | Driver version, SQL exception và connection metrics |

### 19.2. Test trên đúng runtime

Chạy smoke test trong chính container hoặc application server sẽ triển khai. Test trên laptop có thể dùng JDK khác, ojdbc JAR khác, TNS_ADMIN khác, wallet khác, network route khác hoặc DNS khác.

Vì vậy, kết quả local không thay thế kiểm thử staging/pre-production.

### 19.3. Test upgrade driver

Trước khi thay JAR:
1. Lưu driver version hiện tại.
2. Lưu dependency tree.
3. Chạy integration test trên version cũ.
4. Nâng driver trong branch riêng.
5. Chạy lại test datatype, transaction, pool và HA.
6. Đo latency/throughput với workload đại diện.
7. Kiểm tra log và SQL exception.
8. Deploy canary hoặc staging.
9. Chuẩn bị rollback dependency nếu có regression.

## 20. Các tình huống chọn driver thường gặp

### 20.1. JDK 8, database 19c

- Chọn ojdbc8.jar.
- Chọn một driver release được chứng nhận với JDK 8 và Database 19c.
- Kiểm tra JDBC 4.2 có đáp ứng ứng dụng không.
- Nếu cần JDBC 4.3, phải nâng JDK và chọn driver phù hợp.

### 20.2. JDK 11, database 19c

- Ưu tiên xem xét ojdbc11.jar nếu cần JDBC 4.3.
- ojdbc8.jar cũng có thể chạy trên JDK 11 trong phạm vi chứng nhận, nhưng chỉ cung cấp JDBC 4.2.
- Xác minh database 19c và quarterly driver release trong matrix.

### 20.3. JDK 17, database 19c hoặc 21c

- Ưu tiên ojdbc17.jar của dòng driver hiện hành nếu tổ hợp được chứng nhận.
- Kiểm tra các feature Oracle-specific mà ứng dụng dùng.
- Nếu application server quản lý driver, nâng shared module và loại bỏ JAR trùng trong ứng dụng.

### 20.4. JDK 21, database 19c hoặc 21c

- Xem xét ojdbc17.jar của dòng hiện hành.
- ojdbc11.jar có thể là lựa chọn ở release được chứng nhận.
- Kiểm tra chính xác JDK 21 support trong download page/release notes của JAR.
- Không suy ra từ một ojdbc11 cũ rằng mọi quarterly release đều hỗ trợ JDK 21.

### 20.5. JDK 25, database 26ai hoặc 19c

- Trang Oracle JDBC Downloads hiện liệt kê ojdbc17.jar của gói 26ai cho JDK 25.
- Database 26ai và 19c nằm trong danh sách database version mà gói 26ai JDBC hỗ trợ.
- Kiểm tra release notes cho đúng artifact; trang tải có ghi chú về một số lỗi đã xác định trong JDK 25 certification của companion RSI artifact.
- Nếu ứng dụng dùng RSI, phải đánh giá riêng các bug ID được nêu trong release notes.

### 20.6. JDK 8, database 26ai

- Xem ojdbc8.jar trong gói driver 26ai vì trang tải liệt kê JDK 8/11.
- Đối chiếu database 26ai trong interoperability matrix.
- Chấp nhận JDBC 4.2 và kiểm thử datatype/feature mà ứng dụng cần.
- Nếu ứng dụng cần API JDBC 4.3, nâng JDK thay vì cố dùng ojdbc8.

### 20.7. Database 23ai

- Trang tải 26ai JDBC ghi hỗ trợ database 23ai.
- Developer's Guide 26ai matrix không có cột 23.x.
- FAQ dòng 23.x có ma trận riêng cho JDBC 23.x.
- Xác minh exact release notes và Oracle Support certification cho JDK/driver/database pair đang định triển khai.

## 21. Quản lý nhiều driver trong môi trường enterprise

Các hệ thống enterprise thường có nhiều ứng dụng cùng chạy trên một application server hoặc một cluster. Một số lỗi phát sinh do nhiều driver version cùng tồn tại.

### 21.1. Một runtime nên có một driver version rõ ràng

Nếu ứng dụng dùng hai ojdbc version:
- Classloader có thể load nhầm class.
- Driver auto-registration có thể đăng ký nhiều driver.
- Metadata hiển thị version không như mong đợi.
- Companion JAR có thể gọi API không tồn tại trong version đang nạp.

Đặt driver ở một vị trí được quản lý và xác định rõ classloader precedence.

### 21.2. Driver trong server module và driver trong WAR/EAR

Application server có thể cung cấp driver ở module chung. Nếu WAR cũng đóng gói ojdbc, cần hiểu quy tắc parent-first/child-first và isolation. Không thay JAR trong thư mục server trực tiếp khi chưa có change plan.

### 21.3. Driver trong fat JAR

Spring Boot executable JAR hoặc shaded JAR có thể đóng gói driver. Kiểm tra nội dung artifact cuối cùng, không chỉ POM. Dependency exclusion và shading có thể khiến runtime khác với dependency tree dự kiến.

## 22. Nâng cấp driver và chính sách patch

Oracle JDBC được phát hành theo các release/quarterly updates. Chọn bản mới nhất phù hợp không có nghĩa phải cập nhật không kiểm thử.

Quy trình patch:
- Theo dõi Oracle JDBC Downloads và release notes.
- Xem bug fixes và known issues.
- Xem security advisories và vulnerability scanning.
- Kiểm tra JDK/database matrix.
- Pin version trong build.
- Không dùng dynamic version như latest hoặc version range không kiểm soát.
- Chạy integration/regression test.
- Cập nhật SBOM và license inventory.
- Lưu driver version vào log khởi động.
- Có rollback plan.

### 22.1. Phiên bản database và driver có lifecycle riêng

Database 19c có lifecycle support riêng; JDBC driver 26ai có lifecycle release riêng. Không suy ra thời hạn hỗ trợ driver chỉ từ database. Kiểm tra Oracle Lifetime Support Policy và JDBC FAQ khi lập kế hoạch dài hạn.

### 22.2. Không trộn JAR của nhiều quarterly release

Ví dụ ojdbc17 version 23.26.4.0.0 không nên đi cùng ucp17 hoặc security companion JAR từ một release không tương thích nếu Oracle không hướng dẫn. Dùng cùng release family và theo dependency guidance.

## 23. Kiểm tra driver trong CI/CD

Một pipeline có thể tự xác nhận JDK, dependency và database integration.

Các bước gợi ý:
1. In JDK version trong build log.
2. Lưu dependency tree của runtime.
3. Kiểm tra chỉ một Oracle JDBC driver version được resolve.
4. Kiểm tra artifact checksum hoặc nguồn repository.
5. Chạy unit test không phụ thuộc database.
6. Chạy integration test với Oracle Database version mục tiêu.
7. Test TLS/wallet nếu production dùng.
8. Test pool startup/reconnect.
9. Lưu driver/database/JDK version trong test report.
10. Block release nếu tổ hợp ngoài matrix hoặc chưa được phê duyệt.

Không để secret database nằm trong build log. Dùng secret store và ephemeral test credentials.

## 24. Checklist trước khi phát hành ứng dụng

- [ ] Đã xác định JDK runtime production.
- [ ] Đã xác định Oracle Database release và RU.
- [ ] Đã kiểm tra driver/JDK certification.
- [ ] Đã kiểm tra driver/database interoperability matrix.
- [ ] Đã xác nhận JDBC API level cần dùng.
- [ ] Đã chọn Thin hay OCI theo yêu cầu.
- [ ] Đã pin artifact/version.
- [ ] Không có nhiều ojdbc version trong runtime.
- [ ] UCP/companion JAR cùng release family nếu có dùng.
- [ ] Đã kiểm tra URL/service name.
- [ ] Đã test authentication và TLS/wallet.
- [ ] Đã test datatype và PL/SQL features ứng dụng dùng.
- [ ] Đã test connection pool, timeout và reconnect.
- [ ] Đã chạy smoke test trên đúng container/server.
- [ ] Đã lưu driver/database/JDK version vào log.
- [ ] Đã kiểm tra release notes, known issues và support policy.
- [ ] Có rollback plan cho driver upgrade.

## 25. Tài liệu tham chiếu chính thức

Các bảng tương thích thay đổi theo release. Khi triển khai, ưu tiên tài liệu Oracle của đúng driver version và database release, sau đó xác nhận với Oracle Support nếu tổ hợp nằm ngoài bảng công khai.

1. **Oracle JDBC Developer's Guide 26ai — Getting Started, Version Compatibility**  
   https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-getting-started.html

2. **Oracle JDBC Developer's Guide 26ai — Introducing JDBC, Choosing the Appropriate Driver**  
   https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/introducing-JDBC.html

3. **Oracle JDBC and UCP Downloads** — driver JAR, JDK certification, database versions, release notes và companion archive  
   https://www.oracle.com/database/technologies/appdev/jdbc-downloads.html

4. **Oracle JDBC FAQ** — interoperability matrix, JDK/JAR guidance và release-specific questions  
   https://www.oracle.com/database/technologies/faq-jdbc.html

5. **Oracle Maven Central Developer's Guide** — group ID, artifacts, BOM và production dependencies  
   https://www.oracle.com/database/technologies/maven-central-guide.html

6. **Maven Central — Oracle ojdbc17 artifact**  
   https://central.sonatype.com/artifact/com.oracle.database.jdbc/ojdbc17

Các thông tin về 26ai driver/JDK/database matrix trong bài được đối chiếu ngày 14-11-2026. Version 23.26.4.0.0 là ví dụ dependency đang được liệt kê trên Maven Central tại thời điểm đó; kiểm tra bản phát hành mới hơn trước khi tạo build production.

## 26. Bài tập tự luyện

1. Phân biệt JDK version, JDBC specification version và Oracle JDBC driver release.
2. Vì sao ojdbc17.jar không có nghĩa chỉ kết nối với Oracle Database 17?
3. Nêu ba yếu tố cần kiểm tra trước khi chọn driver.
4. JDK 8 nên bắt đầu xem xét JAR nào?
5. JDK 11 cần JDBC 4.3 nên chọn JAR nào?
6. Phân biệt ojdbc8 và ojdbc11 về JDBC API.
7. Vì sao ojdbc17 có thể chạy trên JDK mới hơn JDK 17?
8. Khi nào cần kiểm tra ojdbc10?
9. Giải thích driver/database interoperability matrix.
10. Vì sao driver release không cần cùng số với database release?
11. Ma trận JDBC 26ai công bố những database release nào trong Developer's Guide?
12. Vì sao cần kiểm tra lại riêng database 23ai khi các trang Oracle liệt kê khác nhau?
13. Trạng thái Was trong FAQ có nghĩa gì?
14. Phân biệt driver compatibility và Oracle product support lifecycle.
15. So sánh JDBC Thin và JDBC OCI.
16. Vì sao Thin phù hợp với container?
17. Khi nào cần Oracle Client native library?
18. Viết Maven dependency cho ojdbc17.
19. Viết Gradle dependency cho ojdbc17.
20. Vì sao không nên đóng gói hai ojdbc version trong cùng runtime?
21. UCP khác JDBC driver ở điểm nào?
22. Nêu vai trò của orai18n và oraclepki.
23. Viết lệnh kiểm tra JDK và Maven runtime.
24. Viết lệnh kiểm tra version của ojdbc JAR.
25. Dùng DatabaseMetaData để in driver và database version.
26. Viết JDBC Thin URL dùng service name.
27. Giải thích lỗi UnsupportedClassVersionError.
28. Phân tích nguyên nhân No suitable driver và NoSuchMethodError.
29. Thiết kế test plan nâng ojdbc trong ứng dụng Spring Boot.
30. Lập ma trận kiểm thử gồm JDK, driver, database, TLS, datatype, UCP và application server cho một hệ thống production.

**Chọn Oracle JDBC driver là bài toán giao nhau giữa JDK runtime, driver release, database release và tính năng ứng dụng.** Hãy xác định JDK thật sự chạy ứng dụng, chọn JAR được chứng nhận cho JDK đó, kiểm tra interoperability matrix với database, rồi mới chốt dependency và companion artifacts. Ưu tiên Thin cho ứng dụng Java thông thường, pin một driver version rõ ràng, kiểm thử trên đúng môi trường triển khai và đọc release notes trước mỗi lần nâng cấp.

