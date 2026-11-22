# Quản lý phiên bản công cụ, JDBC và các thư viện mở rộng

Một lần triển khai Liquibase phụ thuộc vào nhiều thành phần chạy cùng nhau: phiên bản Liquibase, Java runtime, JDBC driver, thư viện mở rộng và đôi khi cả plugin của Maven hoặc Gradle. Những thành phần này có vòng đời phát hành và ma trận tương thích riêng. Nếu chỉ cập nhật một JAR hoặc thay driver trên máy triển khai, kết quả có thể khác giữa máy phát triển, CI và production dù changelog không đổi.

Trong phạm vi `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, quản lý phiên bản có nghĩa là xác định rõ thành phần nào chịu trách nhiệm chạy migration, khóa phiên bản của từng dependency, kiểm tra khả năng tương thích với Java và database, rồi triển khai cùng một bộ công cụ đã được kiểm chứng qua các môi trường. Điều này hỗ trợ mục tiêu quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời giúp migration có thể lặp lại, rollback có kế hoạch và tích hợp ổn định với Spring Boot hoặc CI/CD.

## 1. Bản đồ các thành phần và trách nhiệm

| Thành phần | Vai trò | Câu hỏi tương thích cần trả lời |
|---|---|---|
| Liquibase CLI | Chạy migration độc lập từ terminal hoặc pipeline. | Phiên bản CLI dùng Java nào, hỗ trợ database nào và nạp thư viện từ classpath nào? |
| Liquibase Core | Engine phân tích changelog, kiểm tra lịch sử và thực thi changeset. | Phiên bản Core có tương thích với Java, extension và cách tích hợp đang dùng không? |
| Maven/Gradle plugin | Gọi Liquibase từ quy trình build. | Plugin đang dùng Core phiên bản nào và dependency của plugin được nạp từ classloader nào? |
| Spring Boot integration | Tự khởi chạy Liquibase trong vòng đời ứng dụng. | Phiên bản Spring Boot, Liquibase Core, Java và cấu hình `DataSource` có tương thích không? |
| JDBC driver | Cung cấp giao tiếp giữa Liquibase và database qua JDBC. | Driver có hỗ trợ Java runtime, phiên bản server, giao thức và cơ chế xác thực cần thiết không? |
| Liquibase extension | Bổ sung kiểu database, change, parser, snapshot hoặc chức năng đặc thù. | Extension được xây dựng cho phiên bản Core nào và có hỗ trợ database mục tiêu không? |
| Java runtime | Chạy CLI, plugin hoặc ứng dụng chứa Liquibase. | Phiên bản Java có đáp ứng yêu cầu của mọi thành phần trong cùng tiến trình không? |

Các thành phần này không nhất thiết nằm trong cùng một tiến trình. Ví dụ, pipeline có thể chạy Liquibase CLI bằng một JDK riêng, trong khi ứng dụng Spring Boot dùng một runtime khác. Tuy nhiên, từng tiến trình phải có bộ dependency nhất quán và được kiểm thử với database đích.

## 2. Chọn cách cài đặt và nơi quản lý phiên bản

Có ba cách tổ chức phổ biến:

1. **Liquibase CLI độc lập:** cài CLI trên máy phát triển hoặc image của pipeline, sau đó gọi `liquibase update`. Cách này phù hợp khi nhóm nền tảng quản lý migration như một bước phát hành riêng.
2. **Tích hợp qua build plugin:** Maven hoặc Gradle gọi Liquibase trong một task của quy trình build. Plugin có cấu hình và classpath riêng, thuận tiện khi muốn chuẩn hóa lệnh migration trong repository.
3. **Tích hợp trong ứng dụng:** thêm Liquibase Core vào ứng dụng, thường qua Spring Boot auto-configuration. Migration có thể chạy trong lúc ứng dụng khởi động.

Chọn một cơ chế triển khai có chủ sở hữu rõ ràng cho mỗi môi trường. Nếu cả pipeline và mọi instance ứng dụng đều tự chạy migration, chúng có thể cùng yêu cầu khóa, làm chậm khởi động hoặc khiến thời điểm cập nhật schema khó dự đoán. `DATABASECHANGELOGLOCK` điều phối những lần chạy đồng thời trên cùng database, nhưng không thay thế thiết kế phát hành.

### 2.1. Cài đặt CLI

CLI phù hợp với pipeline có bước migration riêng. Sau khi cài Java đáp ứng yêu cầu của bản Liquibase đã chọn và cài gói Liquibase theo hướng dẫn chính thức, xác minh binary đang được gọi:

```bash
liquibase --version
liquibase --help
```

Kết quả `--version` giúp xác nhận executable thực tế trên `PATH`. Trên máy có nhiều bản cài đặt, kiểm tra đường dẫn executable để tránh vô tình dùng bản cũ. Trong CI, nên dùng image hoặc package được khóa phiên bản thay vì cài bản mới nhất không kiểm soát ở mỗi lần chạy.

CLI cần truy cập JDBC driver và các extension cần thiết. Tùy cách đóng gói, các JAR bổ sung có thể được đặt trong thư mục thư viện của Liquibase hoặc được truyền qua tùy chọn classpath. Ví dụ:

```bash
liquibase --classpath="drivers/postgresql-driver.jar:extensions/custom-extension.jar" --driver="org.postgresql.Driver" --url="jdbc:postgresql://db.example.internal:5432/app" --changelog-file="db/changelog/db.changelog-master.yaml" validate
```

Ví dụ trên minh họa cách truyền classpath trên hệ điều hành kiểu Unix; dấu phân cách classpath trên Windows thường là dấu chấm phẩy. Tên JAR và đường dẫn phải trỏ đến artifact đã được khóa phiên bản trong quy trình. Với môi trường có nhiều database, không nên đưa mọi driver và extension từng thử nghiệm vào một thư mục chung nếu chúng có dependency xung đột.

### 2.2. Dùng Maven hoặc Gradle

Khi dùng build plugin, cần phân biệt phiên bản plugin với phiên bản Liquibase Core mà plugin sử dụng. Plugin là thành phần điều phối task; Core là engine thực thi. JDBC driver thường phải được khai báo trong dependency của plugin hoặc classpath migration theo đúng cách plugin hỗ trợ.

Ví dụ Maven tối giản:

```xml
<properties>
    <liquibase.plugin.version>PINNED_LIQUIBASE_PLUGIN_VERSION</liquibase.plugin.version>
    <liquibase.core.version>PINNED_LIQUIBASE_CORE_VERSION</liquibase.core.version>
    <postgresql.version>PINNED_POSTGRESQL_DRIVER_VERSION</postgresql.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.liquibase</groupId>
            <artifactId>liquibase-maven-plugin</artifactId>
            <version>${liquibase.plugin.version}</version>
            <dependencies>
                <dependency>
                    <groupId>org.liquibase</groupId>
                    <artifactId>liquibase-core</artifactId>
                    <version>${liquibase.core.version}</version>
                </dependency>
                <dependency>
                    <groupId>org.postgresql</groupId>
                    <artifactId>postgresql</artifactId>
                    <version>${postgresql.version}</version>
                </dependency>
            </dependencies>
            <configuration>
                <propertyFile>liquibase.properties</propertyFile>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là cấu trúc minh họa; cần đối chiếu phiên bản plugin đang chọn để biết chính xác cách khai báo dependency và thuộc tính cấu hình. Không đưa mật khẩu production vào `liquibase.properties` được commit. Hãy cấp thông tin kết nối từ secret của CI hoặc biến môi trường.

Với Gradle, plugin Liquibase và dependency runtime của migration cũng cần được khóa rõ ràng. Cấu hình có thể dùng version catalog hoặc dependency constraints để tránh khai báo rải rác. Không để một task migration tự kéo phiên bản động như `latest.release`, vì cùng một commit có thể chạy bằng engine khác nhau ở hai thời điểm.

## 3. Khóa phiên bản Liquibase một cách có kiểm soát

### 3.1. Chọn phiên bản nền

Trước khi chọn bản Liquibase, xác định:

- Phiên bản Java được phép chạy trên máy phát triển, agent CI và môi trường triển khai.
- Database engine và phiên bản server đang dùng ở từng môi trường.
- Cách chạy migration: CLI, Maven/Gradle plugin hay tích hợp Spring Boot.
- Các extension cần có và phiên bản tương ứng.
- Các thay đổi tương thích hoặc yêu cầu nâng cấp được ghi trong release notes.

Sau đó đối chiếu ma trận hỗ trợ và tài liệu phát hành của đúng phiên bản Liquibase. Không suy ra tương thích chỉ vì ứng dụng biên dịch thành công: driver có thể không hỗ trợ server cũ, extension có thể không tương thích Core, hoặc CLI có thể yêu cầu Java mới hơn runtime hiện tại.

### 3.2. Khóa phiên bản chính xác

Khai báo phiên bản cụ thể trong một vị trí quản lý tập trung, chẳng hạn Maven properties, Gradle version catalog, dependency management hoặc image tag. Tránh các khai báo động như `+`, `latest` hoặc `latest.release` trong dependency quan trọng.

Một bộ phiên bản có thể được ghi trong bảng tương thích nội bộ:

| Thành phần | Giá trị cần ghi nhận |
|---|---|
| Java | Vendor, phiên bản runtime và kiến trúc nếu có yêu cầu đặc biệt. |
| Liquibase CLI/Core | Phiên bản chính xác và nguồn phân phối. |
| Maven/Gradle plugin | Phiên bản plugin và Core thực tế được plugin nạp. |
| JDBC driver | Tọa độ artifact và phiên bản chính xác. |
| Extension | Tên artifact, phiên bản và phiên bản Core được hỗ trợ. |
| Database | Loại database, phiên bản server và cấu hình kết nối quan trọng. |
| Ứng dụng | Phiên bản Spring Boot và cách khởi chạy migration. |

Tệp dependency lock hoặc image digest giúp tái tạo môi trường. Nếu dùng image container, khóa tag bất biến hoặc digest thay vì chỉ dùng tag chung như `latest`. Ghi lại nguồn artifact và checksum package khi chính sách chuỗi cung ứng phần mềm yêu cầu.

### 3.3. Tránh trộn nhiều bản Core

Một tiến trình chỉ nên nạp một phiên bản Liquibase Core đã được xác định. Nếu classpath chứa nhiều bản `liquibase-core`, thứ tự nạp có thể quyết định class nào được dùng, dẫn đến lỗi khó tái hiện như `NoSuchMethodError`, `ClassNotFoundException` hoặc hành vi khác giữa máy local và CI.

Khi điều tra dependency, xem cây dependency của đúng cấu hình chạy migration. Ví dụ, `mvn dependency:tree` hoặc `./gradlew dependencies` giúp tìm dependency bắc cầu và phiên bản bị kéo vào. Lưu ý dependency của ứng dụng, dependency của plugin và thư viện trong CLI có thể thuộc các classloader khác nhau; kiểm tra đúng tiến trình đang chạy thay vì chỉ xem dependency của ứng dụng.

## 4. Quản lý JDBC driver

JDBC driver là cầu nối giữa Liquibase và database. Driver nhận JDBC URL, mở kết nối, cung cấp metadata và chuyển các lệnh SQL đến server. Liquibase không thay thế driver; một changelog hợp lệ vẫn không thể chạy nếu driver không được tìm thấy, không hiểu URL hoặc không tương thích với server.

### 4.1. Chọn đúng driver

| Database | Artifact thường gặp | Driver class thường dùng |
|---|---|---|
| PostgreSQL | `org.postgresql:postgresql` | `org.postgresql.Driver` |
| MySQL | `com.mysql:mysql-connector-j` | `com.mysql.cj.jdbc.Driver` |
| MariaDB | `org.mariadb.jdbc:mariadb-java-client` | `org.mariadb.jdbc.Driver` |
| Oracle Database | `com.oracle.database.jdbc:ojdbc11` hoặc artifact phù hợp với Java | `oracle.jdbc.OracleDriver` |
| Microsoft SQL Server | `com.microsoft.sqlserver:mssql-jdbc` | `com.microsoft.sqlserver.jdbc.SQLServerDriver` |

Tên artifact và class minh họa có thể thay đổi theo dòng phát hành. Luôn kiểm tra hướng dẫn chính thức của nhà cung cấp driver để chọn phiên bản hỗ trợ Java runtime và phiên bản database server. Với Oracle, cần chọn đúng biến thể driver theo Java và yêu cầu triển khai; với SQL Server, cần kiểm tra thêm yêu cầu TLS và authentication.

### 4.2. JDBC URL và tự đăng ký driver

JDBC URL thường có dạng `jdbc:<vendor>://<host>:<port>/<database>` nhưng chi tiết phụ thuộc nhà cung cấp. URL phải khớp driver đã cài. Ví dụ PostgreSQL:

```properties
url=jdbc:postgresql://localhost:5432/customer_db
username=liquibase_user
driver=org.postgresql.Driver
```

Mật khẩu được cấp riêng cho tiến trình từ secret store hoặc cơ chế bảo mật của pipeline; không lưu mật khẩu thật trong file cấu hình.

Nhiều driver hiện đại tự đăng ký thông qua JDBC service provider khi JAR có mặt trên classpath, nên không phải lúc nào cũng cần khai báo tên driver class. Tuy nhiên, CLI hoặc cấu hình tích hợp có thể yêu cầu thuộc tính `driver`; hãy theo tài liệu của phiên bản Liquibase và driver đang dùng.

Kiểm tra kết nối cần xem cả hostname, port, database/service name, schema mặc định, quyền user, SSL/TLS, truststore và phương thức xác thực. Lỗi kết nối không nhất thiết là lỗi changelog. Hãy phân biệt lỗi DNS/network, xác thực, driver không có trên classpath, URL sai và quyền database.

### 4.3. Tách driver migration và driver ứng dụng

Ứng dụng và Liquibase có thể dùng cùng một driver, nhưng hai classpath không nhất thiết giống nhau. Trong Spring Boot, driver thường được khai báo là runtime dependency của ứng dụng và `DataSource` được dùng để chạy Liquibase. Với CLI độc lập, driver phải có mặt trên classpath của CLI. Với Maven/Gradle plugin, driver cần được nạp trong môi trường thực thi của plugin.

Nếu CLI chạy được nhưng ứng dụng Spring Boot báo không tìm thấy driver, kiểm tra runtime dependency của ứng dụng. Nếu ứng dụng chạy được nhưng Maven plugin không kết nối được, kiểm tra dependency của plugin. Sao chép JAR vào một thư mục bất kỳ không đảm bảo tiến trình sẽ tự động nhìn thấy nó.

## 5. Quản lý thư viện mở rộng Liquibase

Extension bổ sung khả năng ngoài những change và database support có sẵn trong Core. Tùy dự án, extension có thể cung cấp hỗ trợ cho database, kiểu change, parser, snapshot hoặc tích hợp với mô hình schema khác. Một số thư viện được phát hành riêng, một số chức năng có thể đã được đưa vào Core ở phiên bản mới hơn.

Trước khi thêm extension, xác định vấn đề cụ thể cần giải quyết và kiểm tra liệu Core hiện tại đã hỗ trợ hay chưa. Sau đó kiểm tra:

1. Extension có tương thích với phiên bản Liquibase Core dự định dùng không?
2. Extension hỗ trợ phiên bản Java và database server nào?
3. Extension có kéo theo dependency bắc cầu hoặc phiên bản thư viện trùng lặp không?
4. Extension có cần cấu hình, service registration hoặc quyền đặc biệt không?
5. Có thể chạy `validate`, sinh SQL và kiểm thử trên database đại diện để chứng minh extension hoạt động không?

Không giả định mọi extension có cùng nhịp phát hành với Liquibase Core. Một extension có thể chậm hơn Core hoặc chỉ hỗ trợ một dải phiên bản nhất định. Đọc release notes và compatibility information của chính extension trước khi nâng cấp.

### 5.1. Đặt extension đúng classpath

Với CLI, JAR extension phải được nạp cùng Core trong tiến trình Liquibase. Với plugin, dependency phải nằm trong classpath mà plugin sử dụng. Với Spring Boot, extension phải có mặt trong runtime classpath của ứng dụng khi Liquibase khởi chạy. Đưa extension vào classpath biên dịch nhưng không có ở runtime sẽ dẫn đến lỗi khi Liquibase tìm service hoặc lớp mở rộng.

Không nên chép một bản extension mới vào thư mục cài đặt dùng chung mà không cập nhật manifest phiên bản. Khi nâng cấp, thay bộ JAR như một đơn vị đã kiểm thử và bảo đảm không còn bản cũ cùng tên được nạp trước.

### 5.2. Kiểm soát dependency bắc cầu

Extension có thể phụ thuộc vào thư viện logging, parser, JDBC, Hibernate hoặc API khác. Nếu hai extension yêu cầu các phiên bản không tương thích của cùng một thư viện, ứng dụng có thể khởi động thất bại hoặc lỗi chỉ xuất hiện khi chạy một loại change cụ thể.

Giữ danh sách extension ngắn, có chủ sở hữu và lý do sử dụng. Kiểm tra dependency tree, cảnh báo bảo mật và giấy phép theo quy trình của tổ chức. Không thêm JAR thủ công để sửa lỗi thiếu class nếu chưa xác định dependency và phiên bản mà extension thực sự yêu cầu.

## 6. Tích hợp phiên bản với Spring Boot

Trong Spring Boot, Liquibase thường được thêm bằng dependency `org.liquibase:liquibase-core`; JDBC driver được khai báo riêng theo database. Spring Boot quản lý một số phiên bản dependency thông qua dependency management/BOM. Nếu dự án dùng Spring Boot BOM, nên ưu tiên để BOM quản lý phiên bản đã được kiểm chứng, chỉ override khi có lý do và đã kiểm tra tương thích.

Ví dụ Maven với các phiên bản được quản lý tập trung:

```xml
<properties>
    <liquibase.core.version>PINNED_LIQUIBASE_CORE_VERSION</liquibase.core.version>
    <postgresql.version>PINNED_POSTGRESQL_DRIVER_VERSION</postgresql.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
        <version>${liquibase.core.version}</version>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>${postgresql.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Trong dự án dùng Spring Boot BOM, hãy cân nhắc bỏ version trực tiếp nếu BOM đã quản lý đúng artifact; không khai báo override chỉ để tất cả dependency có cùng số phiên bản. Liquibase Core và JDBC driver là hai sản phẩm độc lập, nên số phiên bản của chúng không cần giống nhau.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
```

Thông tin URL và credential thường được cấu hình ở `spring.datasource` hoặc một `DataSource` riêng cho Liquibase. Nếu cần tài khoản migration có quyền rộng hơn tài khoản runtime, cấu hình `spring.liquibase.url`, `user`, `password` và các thuộc tính liên quan theo phiên bản Spring Boot. Không chia sẻ mật khẩu qua repository.

Khi nâng cấp Spring Boot, cần kiểm tra phiên bản Liquibase Core mà BOM mới quản lý, yêu cầu Java tối thiểu, thay đổi auto-configuration và JDBC driver. Đừng nâng riêng Core lên phiên bản bất kỳ mà không xem xét các dependency và API mà Spring Boot integration dựa vào.

## 7. Kiểm chứng một bộ phiên bản trước khi phát hành

Một bộ phiên bản chỉ được xem là sẵn sàng khi đã kiểm tra cả khả năng nạp thư viện và hành vi migration trên database đại diện. Có thể tổ chức kiểm chứng theo các bước sau:

1. **Xác nhận runtime:** ghi lại phiên bản Java và Liquibase thực tế trong log pipeline.
2. **Xác nhận dependency:** kiểm tra Core, plugin, JDBC driver và extension được nạp đúng phiên bản, không có bản trùng lặp ngoài dự kiến.
3. **Kiểm tra kết nối:** mở kết nối đến database thử nghiệm bằng cùng URL scheme, TLS và authentication như môi trường đích.
4. **Chạy `validate`:** phát hiện lỗi cấu trúc changelog và checksum trước khi thực thi.
5. **Chạy `status`:** xác định changeset còn chờ triển khai.
6. **Sinh SQL:** dùng `updateSQL` để review SQL mà bộ phiên bản mới dự kiến phát ra.
7. **Chạy migration thử:** triển khai trên database có dữ liệu và schema gần với môi trường thật.
8. **Kiểm tra lịch sử:** đối chiếu `DATABASECHANGELOG`, checksum, thứ tự thực thi và kết quả thực tế.
9. **Kiểm tra phục hồi:** thử rollback hoặc phương án phục hồi dữ liệu phù hợp với loại migration.
10. **Phát hành cùng bộ artifact:** đưa đúng CLI/image/dependency đã kiểm chứng qua các môi trường.

Không chỉ kiểm thử database trống. Database đang vận hành có thể chứa dữ liệu vi phạm giả định của precondition, index lớn, lock kéo dài hoặc khác biệt schema do lịch sử triển khai. Nên có bộ kiểm thử đại diện cho trạng thái nâng cấp thực tế.

## 8. Quy trình nâng cấp Liquibase, JDBC và extension

Nâng cấp công cụ không đồng nghĩa nâng cấp schema. Cần quản lý hai thay đổi này có chủ đích để khi có lỗi, nhóm biết lỗi đến từ engine, driver, extension hay changelog.

### 8.1. Chuẩn bị

- Đọc release notes của Liquibase, driver và từng extension trong phạm vi nâng cấp.
- Kiểm tra yêu cầu Java và database server được hỗ trợ.
- Xem thay đổi parser, cú pháp, checksum, SQL generator, snapshot và API extension.
- Ghi lại bộ phiên bản hiện tại và bộ phiên bản dự kiến.
- Tạo môi trường kiểm thử từ schema/lịch sử gần với môi trường đích.

### 8.2. Thử nghiệm có kiểm soát

Trước tiên cập nhật bộ công cụ ở môi trường phát triển, chạy validation và migration trên database thử. Tiếp theo chạy cùng artifact ở staging, kiểm tra thời gian chạy, SQL sinh ra, lock, log và lịch sử. Khi kết quả ổn định, phát hành chính bộ artifact đó sang production theo quy trình kiểm soát thay đổi.

Nếu cần đổi Liquibase Core, JDBC driver và extension cùng lúc, hãy ghi rõ lý do và kiểm tra tổ hợp đầy đủ. Khi có thể, tách các thay đổi để dễ xác định nguyên nhân nếu lỗi xuất hiện. Không thay đổi changelog đã triển khai chỉ để thích ứng một lỗi của công cụ mới mà chưa xác định nguyên nhân.

### 8.3. Theo dõi sau nâng cấp

Quan sát lỗi kết nối, thời gian lấy khóa, thời gian thực thi changeset, câu lệnh SQL, cảnh báo checksum và thay đổi trong `DATABASECHANGELOG`. Đặc biệt chú ý khác biệt SQL giữa database engine hoặc driver phiên bản mới. Nếu có sự cố, dừng đợt triển khai tiếp theo, xác định changeset đã commit, rồi chọn cách khôi phục công cụ hoặc database dựa trên trạng thái thực tế.

Hạ phiên bản CLI hoặc driver không tự động hoàn tác migration đã chạy. Nếu migration đã thay đổi schema, việc quay lại binary cũ chỉ khôi phục môi trường thực thi; nó không đưa database về trạng thái trước đó. Phải đánh giá khả năng tương thích ngược của ứng dụng và dùng rollback/restore phù hợp.

## 9. Quản lý khác biệt giữa các môi trường

Development, staging và production nên dùng cùng một bộ phiên bản Liquibase, JDBC driver và extension cho một đợt phát hành. Mỗi môi trường có thể khác URL, credential, schema hoặc tham số vận hành, nhưng không nên tự động chọn một bản Liquibase khác nhau theo môi trường.

Một ma trận phát hành giúp phát hiện lệch cấu hình:

| Thành phần | Development | Staging | Production |
|---|---|---|---|
| Liquibase | Cùng phiên bản đã khóa | Cùng phiên bản | Cùng phiên bản |
| Java runtime | Theo chuẩn pipeline | Theo chuẩn pipeline | Theo chuẩn pipeline |
| JDBC driver | Cùng artifact/phiên bản | Cùng artifact/phiên bản | Cùng artifact/phiên bản |
| Extension | Cùng danh sách và phiên bản | Cùng danh sách và phiên bản | Cùng danh sách và phiên bản |
| Database | Có thể khác dữ liệu, phải tương thích | Gần cấu hình production | Database thực tế |
| Credential | Secret riêng | Secret riêng | Secret production riêng |

Nếu production dùng database engine hoặc phiên bản server khác staging, phải có kiểm thử tương thích riêng. Cùng một JDBC driver không đảm bảo mọi tính năng DDL có hành vi giống nhau trên mọi phiên bản server.

Lưu manifest bộ công cụ cùng artifact phát hành hoặc metadata pipeline: phiên bản Java, Liquibase, plugin, driver, extension, database server và commit changelog. Khi điều tra một migration, thông tin này giúp tái tạo chính xác môi trường đã tạo ra SQL và lịch sử triển khai.

## 10. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `No suitable driver` hoặc không tìm thấy driver | JAR không nằm trong classpath của tiến trình thực thi, hoặc JDBC URL không khớp driver. | Kiểm tra classpath CLI/plugin/app, artifact và URL. |
| `ClassNotFoundException` cho driver hoặc extension | Thiếu JAR ở runtime hoặc cấu hình classloader sai. | Kiểm tra dependency của đúng tiến trình và scope runtime. |
| `NoSuchMethodError` / `NoClassDefFoundError` | Core và extension không tương thích hoặc có nhiều bản dependency. | Kiểm tra dependency tree, classpath và compatibility matrix. |
| Kết nối thất bại sau khi nâng driver | Thay đổi TLS, authentication, URL, Java baseline hoặc khả năng tương thích server. | Đọc release notes driver và kiểm tra kết nối độc lập. |
| CLI chạy được nhưng Spring Boot lỗi | CLI và ứng dụng dùng classpath hoặc cấu hình khác nhau. | Kiểm tra runtime dependency và `DataSource` của ứng dụng. |
| Maven/Gradle task chạy Core khác ứng dụng | Plugin có dependency/classloader riêng. | Xác định phiên bản Core plugin thực tế nạp. |
| SQL sinh ra khác sau nâng cấp | SQL generator, driver, extension hoặc database metadata thay đổi. | So sánh `updateSQL`, phiên bản và database thử nghiệm. |
| Checksum validation thất bại | Changeset đã triển khai bị sửa, hoặc có khác biệt liên quan phiên bản/cơ chế checksum. | Xác định changeset và lịch sử; không vội xóa checksum. |

Không dùng `clearCheckSums` như thao tác sửa lỗi mặc định sau nâng cấp. Trước hết xác định checksum thay đổi vì nội dung changeset, phiên bản Liquibase hay nguyên nhân khác. Chỉ xóa và tính lại checksum khi đã hiểu tác động, có quy trình phê duyệt và xác minh lịch sử giữa các môi trường.

## 11. Ví dụ một quy ước quản lý phiên bản trong nhóm

Một nhóm có thể duy trì một bảng manifest trong tài liệu phát hành hoặc metadata pipeline với các trường:

```text
java.runtime=PINNED_JAVA_VERSION
liquibase.cli=PINNED_LIQUIBASE_CLI_VERSION
liquibase.core=PINNED_LIQUIBASE_CORE_VERSION
liquibase.maven-plugin=PINNED_PLUGIN_VERSION
jdbc.postgresql=PINNED_POSTGRESQL_DRIVER_VERSION
extension.custom=PINNED_EXTENSION_VERSION
database.postgresql=SUPPORTED_SERVER_VERSION_RANGE
changelog.commit=GIT_COMMIT_ID
```

Các giá trị `PINNED_*` là chỗ điền phiên bản đã được nhóm chọn sau khi kiểm tra tài liệu tương thích; đây không phải phiên bản mặc định có thể sao chép vào production. Nếu chỉ dùng CLI, không cần khai báo Maven plugin. Nếu không có extension, không cần thêm dòng extension.

Quy ước review thay đổi dependency có thể yêu cầu người sửa nêu lý do nâng cấp, release notes đã đọc, ma trận tương thích, kết quả `validate`/`updateSQL`, database đã thử và phương án phục hồi. Điều này biến việc nâng cấp thành thay đổi có thể xem xét và tái tạo, thay vì một cập nhật không rõ nguồn gốc trên máy chạy migration.

## 12. Checklist trước khi đưa bộ công cụ vào production

- [ ] Phiên bản Java đáp ứng yêu cầu của Liquibase, plugin, driver và extension.
- [ ] Phiên bản Liquibase CLI/Core và plugin được khóa, nguồn cài đặt rõ ràng.
- [ ] JDBC driver đúng database, tương thích server và có mặt trong classpath thực thi.
- [ ] Extension có lý do sử dụng, phiên bản tương thích Core và không xung đột dependency.
- [ ] Spring Boot BOM hoặc dependency management không âm thầm ghi đè phiên bản đã chọn.
- [ ] Không có phiên bản Core hoặc driver trùng lặp ngoài dự kiến trong cùng tiến trình.
- [ ] CI dùng cùng bộ artifact đã kiểm thử cho staging và production.
- [ ] `validate`, `status` và `updateSQL` đã được kiểm tra trên đúng changelog.
- [ ] Migration đã được thử trên database đại diện, có xem xét dữ liệu và lock.
- [ ] Lịch sử `DATABASECHANGELOG`, checksum và phương án rollback/restore đã được xác minh.
- [ ] Secret, quyền database và TLS được cấu hình riêng cho từng môi trường.

## 13. Câu hỏi tự kiểm tra

1. Liquibase CLI, Core và Maven/Gradle plugin khác nhau ở trách nhiệm nào? Vì sao cần ghi nhận phiên bản của từng thành phần?
2. Tại sao driver có trong dependency của ứng dụng nhưng plugin migration vẫn có thể báo không tìm thấy driver?
3. Khi chọn JDBC driver, cần kiểm tra những yếu tố nào ngoài tên database?
4. Vì sao không thể giả định một extension mới nhất luôn tương thích với Core đang dùng?
5. `NoSuchMethodError` có thể chỉ ra vấn đề gì trong classpath và dependency bắc cầu?
6. Vì sao hạ phiên bản Liquibase sau một lần triển khai lỗi không tự hoàn tác schema đã thay đổi?
7. Nên kiểm tra những gì khi nâng cấp Liquibase có khả năng ảnh hưởng checksum hoặc SQL generator?
8. Làm thế nào để bảo đảm development, staging và production dùng cùng một bộ công cụ đã kiểm chứng?

Quản lý phiên bản công cụ, JDBC và extension là một phần của độ tin cậy migration. Khi nhóm khóa được bộ dependency, hiểu classpath của từng cách tích hợp và kiểm tra tương thích trên database đại diện, cùng một changelog có thể được thực thi nhất quán hơn qua các môi trường. Đây là nền tảng để Liquibase vận hành ổn định trong dự án Java và quy trình CI/CD.
