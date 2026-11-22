# HikariCP và mức hỗ trợ CRaC theo phiên bản thư viện

HikariCP là JDBC connection pool phổ biến trong ứng dụng Java. Pool giữ các kết nối đến database để ứng dụng có thể mượn và trả connection thay vì tạo một kết nối TCP và đăng nhập database cho mỗi request. Cách làm này giảm chi phí kết nối, nhưng tạo ra một vấn đề khi dùng CRaC (Coordinated Restore at Checkpoint): checkpoint có thể giữ lại trạng thái Java object trong khi database, network hoặc firewall vẫn tiếp tục hoạt động bên ngoài tiến trình.

Một connection đang nằm trong pool tại thời điểm checkpoint có thể đã bị database server đóng, hết timeout hoặc mất trạng thái session khi ứng dụng được restore. Vì vậy, pool cần tham gia vòng đời checkpoint/restore: chuẩn bị và xử lý các connection trước checkpoint, sau đó xác thực hoặc tạo lại kết nối trước khi ứng dụng nhận traffic.

HikariCP đã bổ sung tích hợp CRaC trong dòng **5.1.0**. Khi chọn phiên bản, cần phân biệt tính năng được tích hợp sẵn trong thư viện với việc ứng dụng tự quản lý DataSource bằng CRaC Resource. Dùng phiên bản mới hơn không tự động chứng minh mọi phần của ứng dụng đã an toàn với checkpoint; JDBC driver, transaction đang chạy, thứ tự callback và cấu hình runtime vẫn cần được xử lý.

## 1. Vì sao JDBC connection cần được xử lý khi checkpoint?

Một JDBC connection không chỉ là một object Java. Phía sau object đó thường có:

- TCP socket đến database server.
- Trạng thái xác thực và session ở database.
- Transaction đang mở hoặc trạng thái auto-commit.
- Protocol state giữa JDBC driver và database.
- Timeout, keepalive và trạng thái network phụ thuộc môi trường.

CRaC lưu trạng thái tiến trình để khôi phục sau đó. Trong khoảng thời gian tiến trình bị checkpoint, database server vẫn có thể tiếp tục chạy. Server có thể đóng session vì idle timeout, network có thể thay đổi hoặc connection bị firewall loại bỏ.

Do đó, sau restore, một object Connection còn tồn tại trong heap không có nghĩa kết nối phía database vẫn hợp lệ.

### 1.1. Connection pool làm gì?

Khi ứng dụng khởi tạo HikariCP, pool thường:

1. Đọc cấu hình JDBC URL, username, credential và các giới hạn pool.
2. Tạo một số connection ban đầu hoặc tạo connection khi có nhu cầu.
3. Giữ connection rảnh để request tiếp theo có thể mượn nhanh.
4. Kiểm tra và loại bỏ connection không còn hợp lệ theo chính sách.
5. Đóng connection khi pool shutdown.

Luồng request:

~~~text
HTTP request
    │
    ▼
Service gọi DataSource.getConnection()
    │
    ▼
HikariCP cấp connection từ pool
    │
    ▼
JDBC driver giao tiếp với database
    │
    ▼
Service commit/rollback và close connection
    │
    ▼
Connection trở lại pool để tái sử dụng
~~~

Thông thường, gọi close() trên connection do HikariCP cấp sẽ trả connection về pool thay vì đóng socket vật lý ngay lập tức. Pool mới là thành phần sở hữu vòng đời connection vật lý.

### 1.2. Điều gì có thể xảy ra nếu checkpoint giữ connection cũ?

~~~text
Trước checkpoint
  HikariCP
    ├── Connection A ── Database session A
    ├── Connection B ── Database session B
    └── Connection C ── Database session C

Checkpoint
  JVM được lưu trạng thái

Trong thời gian checkpoint
  Database tiếp tục chạy
  Session có thể timeout hoặc bị đóng
  Network có thể thay đổi

Sau restore
  Java object Connection A/B/C vẫn xuất hiện
  Nhưng session phía database có thể không còn hợp lệ
~~~

Nếu ứng dụng sử dụng lại connection cũ mà không xử lý đúng, request có thể gặp lỗi I/O, connection reset, communications link failure hoặc lỗi transaction. Những lỗi này thường chỉ xuất hiện sau restore, dù ứng dụng đã hoạt động bình thường trước checkpoint.

## 2. Mức hỗ trợ CRaC theo phiên bản HikariCP

Mốc quan trọng khi lựa chọn HikariCP là **5.1.0**, phiên bản đưa hỗ trợ CRaC vào thư viện.

| Dòng phiên bản | Hỗ trợ CRaC | Cách tiếp cận |
|---|---|---|
| Trước 5.1.0, bao gồm 5.0.x | Chưa có tích hợp CRaC sẵn trong HikariCP | Ứng dụng phải tự điều phối vòng đời pool bằng Resource callback |
| 5.1.0 | Bổ sung tích hợp CRaC | Dùng tích hợp của HikariCP khi chạy với CRaC runtime/API tương thích |
| Các phiên bản mới hơn | Tiếp tục kiểm tra release notes và dependency của đúng artifact | Ưu tiên tích hợp có sẵn, kiểm chứng với JDBC driver và JDK thực tế |

Không nên chỉ nhìn số Java target hoặc số major của HikariCP để kết luận có hỗ trợ CRaC. Cần kiểm tra chính xác artifact đang được resolve trong build, phiên bản API CRaC có trên runtime và hướng dẫn của release tương ứng.

### 2.1. Trước HikariCP 5.1.0

Các phiên bản cũ không tự tham gia CRaC lifecycle. Nếu ứng dụng checkpoint mà không xử lý pool, connection cũ có thể được khôi phục cùng tiến trình.

Ứng dụng phải tự quản lý việc:

- Ngừng nhận request và công việc mới.
- Đợi transaction hoặc thao tác JDBC đang chạy hoàn tất.
- Đóng pool trước checkpoint.
- Tạo lại pool sau restore.
- Chỉ mở traffic sau khi pool mới có thể kết nối database.

Việc tự quản lý cần một DataSource facade hoặc một lifecycle coordinator để các service tiếp tục sử dụng cùng một đối tượng DataSource logic trong khi delegate HikariDataSource bên trong được thay thế. Nếu chỉ đóng một HikariDataSource rồi tạo object mới ở callback nhưng các bean khác vẫn giữ reference đến object cũ, ứng dụng có thể tiếp tục gọi pool đã đóng.

### 2.2. HikariCP 5.1.0 và tích hợp CRaC

Từ 5.1.0, HikariCP có tích hợp để tham gia vòng đời CRaC. Tích hợp này nhằm xử lý trạng thái connection pool ở hai giai đoạn checkpoint và restore, giảm nhu cầu viết adapter riêng cho các thao tác nội bộ của pool.

Để sử dụng đúng:

- Dùng artifact HikariCP có hỗ trợ CRaC.
- Đảm bảo CRaC API cần thiết có mặt theo cách mà release đó yêu cầu.
- Chạy bằng JDK distribution có hỗ trợ CRaC.
- Không đăng ký thêm callback thứ hai để đóng/mở cùng một pool nếu thư viện đã quản lý pool đó.
- Vẫn điều phối request, transaction và các resource khác của ứng dụng.

Tích hợp của HikariCP quản lý vòng đời pool; nó không thể tự biết toàn bộ transaction nghiệp vụ của ứng dụng đã hoàn tất hay chưa. Ứng dụng vẫn phải đưa hệ thống về trạng thái an toàn trước checkpoint.

### 2.3. Các phiên bản mới hơn

Khi nâng cấp HikariCP, hãy đọc release notes của đúng phiên bản và kiểm tra dependency tree. Không suy ra tính tương thích chỉ từ việc phiên bản cao hơn 5.1.0.

Các yếu tố cần xác nhận:

- HikariCP release có giữ tích hợp CRaC và dùng API nào.
- Phiên bản org.crac API có tương thích với JDK CRaC đang chạy không.
- JDBC driver có hỗ trợ việc tạo lại connection sau restore không.
- Framework có tự đăng ký hoặc quản lý resource callback khác hay không.
- Cấu hình pool, timeout và validation có phù hợp với database sau thời gian checkpoint không.

Một bản nâng cấp thư viện có thể thay đổi yêu cầu Java, dependency hoặc hành vi nội bộ. Vì vậy, cần kiểm thử checkpoint/restore với đúng bộ phiên bản dự kiến triển khai.

## 3. Xác định phiên bản HikariCP đang được ứng dụng sử dụng

Đừng chỉ xem version khai báo trong file build. Maven hoặc Gradle có thể chọn một phiên bản khác do dependency mediation hoặc version catalog.

### 3.1. Maven

Nếu dùng Maven, xem dependency tree:

~~~bash
./mvnw -B dependency:tree -Dincludes=com.zaxxer:HikariCP
~~~

Kết quả sẽ cho biết HikariCP được resolve từ dependency nào và phiên bản cuối cùng là gì.

Nếu dự án dùng dependency management hoặc BOM, kiểm tra cả nơi quản lý version. Tránh khai báo một phiên bản ở module này và một phiên bản khác ở module khác mà không có chủ đích.

### 3.2. Gradle

Với Gradle:

~~~bash
./gradlew dependencyInsight \
    --dependency HikariCP \
    --configuration runtimeClasspath
~~~

Lệnh này cho biết phiên bản được chọn và lý do Gradle chọn nó. Nếu ứng dụng chạy trong Spring Boot, hãy kiểm tra dependency do BOM của Spring Boot quản lý trước khi ghi đè version.

### 3.3. Kiểm tra CRaC API trên classpath

Nếu release HikariCP sử dụng CRaC API như dependency tùy chọn, ứng dụng cần bảo đảm API có mặt ở runtime. Kiểm tra dependency tree hoặc runtime classpath để tránh tình trạng compile thành công nhưng lúc khởi tạo pool lại thiếu class cần thiết.

JDK CRaC và artifact org.crac là hai phần liên quan nhưng không nên nhầm lẫn: JDK distribution cung cấp khả năng checkpoint/restore ở runtime; API dependency giúp code thư viện và ứng dụng tham chiếu các kiểu Resource/Context theo cơ chế mà bản build sử dụng. Hãy theo đúng yêu cầu dependency của HikariCP release đang chọn, không thêm nhiều phiên bản org.crac khác nhau vào classpath.

## 4. Khai báo dependency

Ví dụ Maven với HikariCP 5.1.0:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>5.1.0</version>
    </dependency>

    <!-- Khai báo nếu release/runtime cần CRaC API ở application classpath. -->
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
        <version>1.4.0</version>
    </dependency>

    <!-- JDBC driver của database, ví dụ PostgreSQL. -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.3</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Các version trong ví dụ là version minh họa để dependency được khai báo tường minh. Khi áp dụng, hãy chọn version tương thích với Java baseline, database server, JDBC driver và CRaC JDK của dự án. Nếu dependency management của framework đã quản lý version, hãy kiểm tra version thực tế trước khi ghi đè.

Không thêm dependency CRaC một cách mù quáng. Trước hết kiểm tra POM của HikariCP đang dùng và xác định org.crac API được khai báo theo scope nào. Nếu thư viện đã đưa API cần thiết vào runtime theo cách phù hợp, không tạo thêm một bản API xung đột. Nếu là optional/provided, ứng dụng cần cung cấp dependency tương thích theo tài liệu của release.

## 5. Cấu hình HikariCP trong ứng dụng

Ví dụ tạo DataSource:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {

    private DataSourceFactory() {
    }

    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(
                System.getenv("DB_JDBC_URL"));
        config.setUsername(
                System.getenv("DB_USERNAME"));
        config.setPassword(
                System.getenv("DB_PASSWORD"));

        config.setPoolName("orders-pool");
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(30_000);
        config.setValidationTimeout(5_000);
        config.setMaxLifetime(1_800_000);
        config.setKeepaliveTime(120_000);

        return new HikariDataSource(config);
    }
}
~~~

Các giá trị trên chỉ minh họa cách cấu hình. Hãy chọn pool size, timeout và lifetime dựa trên giới hạn connection của database, tải thực tế, số instance ứng dụng và latency mạng.

Một số tham số đáng chú ý:

| Tham số | Ý nghĩa |
|---|---|
| maximumPoolSize | Số connection tối đa trong pool |
| minimumIdle | Số connection rảnh mục tiêu mà pool cố duy trì |
| connectionTimeout | Thời gian tối đa chờ mượn connection |
| validationTimeout | Thời gian tối đa cho thao tác kiểm tra connection |
| maxLifetime | Tuổi thọ tối đa của connection trong pool |
| keepaliveTime | Chu kỳ kiểm tra/giữ sống connection rảnh khi cấu hình cho phép |

Các tham số này giúp quản lý pool khi ứng dụng chạy bình thường. Chúng không thay thế callback CRaC và không bảo đảm connection cũ sẽ hợp lệ sau restore.

## 6. Vòng đời pool khi dùng CRaC

Có thể mô hình hóa vòng đời mong muốn như sau:

~~~text
Ứng dụng khởi động
      │
      ▼
HikariDataSource tạo pool
      │
      ▼
Ứng dụng READY
      │
      │ yêu cầu checkpoint
      ▼
Dừng nhận request mới
      │
      ▼
Đợi transaction/JDBC work đang chạy
      │
      ▼
CRaC beforeCheckpoint
      │
      ▼
HikariCP chuẩn bị pool/connection
      │
      ▼
Checkpoint tiến trình
      │
      ▼
Thời gian tiến trình tạm dừng
      │
      ▼
Restore tiến trình
      │
      ▼
CRaC afterRestore
      │
      ▼
HikariCP khôi phục pool/connection
      │
      ▼
Kiểm tra database và dependency
      │
      ▼
Ứng dụng READY trở lại
~~~

Với HikariCP có tích hợp CRaC, thư viện tham gia xử lý vòng đời pool. Với phiên bản cũ, ứng dụng phải tự hiện thực bước chuẩn bị và khôi phục. Trong cả hai trường hợp, việc drain request và transaction thuộc trách nhiệm của ứng dụng.

### 6.1. Trước checkpoint

Ứng dụng nên:

1. Chuyển readiness sang NOT_READY để load balancer ngừng gửi request mới.
2. Dừng nhận công việc mới từ message consumer hoặc scheduler.
3. Đợi các request đang dùng JDBC hoàn tất trong thời gian giới hạn.
4. Đảm bảo transaction đã commit hoặc rollback.
5. Cho HikariCP thực hiện phần xử lý pool theo tích hợp của phiên bản đang dùng.
6. Chỉ để checkpoint tiếp tục khi các resource bắt buộc đã đạt trạng thái an toàn.

Không đóng pool trong khi một request vẫn giữ connection. Nếu transaction đang mở bị snapshot, ứng dụng có thể khôi phục một object connection nhưng transaction phía database đã timeout hoặc bị rollback.

### 6.2. Sau restore

Sau restore, ứng dụng cần:

1. Để callback của HikariCP hoàn tất theo thứ tự resource đã đăng ký.
2. Xác nhận pool có thể cấp connection mới.
3. Kiểm tra database endpoint, credential và network.
4. Khôi phục các service phụ thuộc database.
5. Chỉ chuyển readiness sang READY sau khi dependency bắt buộc hoạt động.

Không gọi thủ công callback của HikariCP. CRaC runtime gọi callback theo lifecycle. Nếu cần kiểm tra pool, hãy dùng health check hoặc lấy một connection thử rồi đóng để trả về pool.

## 7. Không quản lý cùng một pool hai lần

Khi dùng HikariCP version có tích hợp CRaC, tránh tạo thêm một Resource callback độc lập chỉ để đóng và mở lại cùng pool. Hai lifecycle manager cùng điều khiển một HikariDataSource có thể dẫn đến:

- Callback đóng pool trước, callback khác lại cố dùng pool đã đóng.
- Pool được khởi tạo hai lần sau restore.
- Connection bị đóng lặp hoặc executor nội bộ bị dừng sai thời điểm.
- Thứ tự callback giữa pool và service bị sai.
- Ứng dụng đánh dấu READY trước khi pool thực sự sẵn sàng.

Hãy phân chia ownership rõ ràng:

| Thành phần | Trách nhiệm |
|---|---|
| HikariCP CRaC integration | Quản lý lifecycle nội bộ của connection pool |
| Ứng dụng/service | Dừng nhận request, drain transaction và công việc |
| Resource coordinator của ứng dụng | Điều phối các resource khác và readiness |
| JDBC driver | Tạo và thực hiện kết nối theo giao thức database |
| Database server | Quản lý session, transaction và connection phía server |

Nếu dùng HikariCP cũ chưa có tích hợp, chỉ một adapter nên sở hữu việc đóng/mở pool. Adapter phải phối hợp với dependency injection để mọi service tiếp tục sử dụng cùng một DataSource facade, dù HikariDataSource delegate được thay thế sau restore.

## 8. Tự quản lý HikariCP ở phiên bản chưa có tích hợp CRaC

Với HikariCP trước 5.1.0, có thể tạo một adapter CRaC Resource. Mẫu kiến trúc:

~~~text
Service
   │
   ▼
RestartableDataSource (DataSource facade)
   │
   ▼
Current HikariDataSource
   │
   ▼
Database

beforeCheckpoint:
  1. Mark facade unavailable
  2. Drain application work
  3. Close current HikariDataSource
  4. Checkpoint

afterRestore:
  1. Create a new HikariDataSource
  2. Validate a connection
  3. Publish new delegate
  4. Mark facade available
~~~

Điểm quan trọng là service phụ thuộc vào facade ổn định, không giữ trực tiếp delegate sẽ bị thay thế.

Pseudocode minh họa:

~~~java
public final class RestartableDataSource
        implements javax.sql.DataSource, org.crac.Resource {

    private final HikariConfig config;
    private volatile HikariDataSource delegate;

    public RestartableDataSource(HikariConfig config) {
        this.config = new HikariConfig(config);
        this.delegate = new HikariDataSource(this.config);
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        HikariDataSource current = delegate;
        delegate = null;

        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        HikariDataSource restored =
                new HikariDataSource(config);

        try (Connection connection = restored.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        } catch (Exception failure) {
            restored.close();
            throw failure;
        }

        delegate = restored;
    }

    private HikariDataSource currentDataSource() throws SQLException {
        HikariDataSource current = delegate;

        if (current == null) {
            throw new SQLException(
                    "DataSource is not ready during checkpoint/restore");
        }

        return current;
    }

    @Override
    public Connection getConnection() throws SQLException {
        return currentDataSource().getConnection();
    }

    // Các phương thức DataSource còn lại phải delegate tới
    // currentDataSource(), bao gồm getConnection(username, password),
    // log writer, login timeout, unwrap và isWrapperFor.
}
~~~

Đây là pseudocode mô tả ownership và trình tự, không phải một implementation DataSource hoàn chỉnh để copy nguyên trạng. Một implementation thực tế phải triển khai đầy đủ các method của DataSource, quản lý thread-safety và bảo đảm không có request mới lấy delegate trong lúc callback đang đóng pool.

Ngoài ra, HikariConfig chứa credential và cấu hình kết nối. Không ghi password vào log hoặc checkpoint artifact chia sẻ. Sau restore, cân nhắc đọc credential mới từ secret provider nếu credential có thể thay đổi trong thời gian tiến trình tạm dừng.

### 8.1. Vì sao không chỉ gọi close rồi tạo pool mới trong callback?

Nếu ứng dụng inject trực tiếp một HikariDataSource vào nhiều service, sau restore tạo một object mới không tự thay đổi reference mà các service đã giữ. Các service vẫn gọi object cũ đã đóng.

DataSource facade giải quyết vấn đề này bằng cách giữ một reference ổn định trong dependency injection và thay đổi delegate bên trong. Một lựa chọn khác là để application context quản lý việc thay thế bean, nhưng cần bảo đảm mọi consumer đều nhận được reference mới và lifecycle hook không chạy trùng với CRaC callback.

## 9. JDBC transaction và request đang chạy

Tích hợp CRaC của HikariCP không thể thay thế việc quản lý transaction nghiệp vụ. Trước checkpoint, ứng dụng cần xử lý các request đang chạy.

Ví dụ một request:

~~~text
HTTP request bắt đầu
      │
      ▼
Mượn JDBC connection
      │
      ▼
BEGIN transaction
      │
      ▼
Cập nhật dữ liệu
      │
      ▼
COMMIT
      │
      ▼
Trả connection về pool
~~~

Checkpoint nên được yêu cầu sau khi request hoàn tất, connection đã được trả về pool và không còn transaction cần bảo toàn.

Nếu checkpoint xảy ra trong transaction:

- Database có thể vẫn giữ transaction trong khi client process bị dừng.
- Server có thể rollback transaction khi session timeout.
- Restore có thể không khôi phục được session cũ.
- Ứng dụng có thể không biết thao tác nghiệp vụ đã commit hay chưa nếu kết nối mất đúng thời điểm.
- Retry request có thể gây thực hiện lặp nếu nghiệp vụ không idempotent.

Đối với thao tác ghi dữ liệu, hãy dùng transaction boundary rõ ràng và idempotency key hoặc cơ chế deduplication khi retry. CRaC không cung cấp một transaction snapshot phân tán giữa JVM và database.

## 10. Cấu hình pool và giới hạn connection của database

CRaC có thể làm nhiều instance restore gần như cùng lúc. Nếu tất cả instance cùng tạo lại connection pool, database có thể nhận một đợt connection burst.

Ví dụ, 10 instance, mỗi instance có maximumPoolSize là 20, có thể tạo ra nhu cầu tối đa 200 connection. Nếu database chỉ cho phép 100 connection ứng dụng, restore đồng thời có thể khiến một số pool không khởi tạo được.

Khi thiết kế:

- Tính tổng connection tối đa trên tất cả replica.
- Dành chỗ cho admin, migration, monitoring và các ứng dụng khác.
- Chọn minimumIdle hợp lý để tránh tạo quá nhiều connection ngay sau restore.
- Dùng retry/backoff có giới hạn nếu database tạm thời chưa sẵn sàng.
- Không để mọi instance retry đồng bộ liên tục.
- Chọn readiness policy để instance chỉ nhận traffic khi pool đã hoạt động.

Ví dụ:

| Số replica | Maximum pool size | Tổng connection tối đa |
|---:|---:|---:|
| 2 | 10 | 20 |
| 5 | 10 | 50 |
| 10 | 20 | 200 |
| 20 | 10 | 200 |

Đây là phép tính giới hạn lý thuyết; pool có thể không mở đủ connection ngay lập tức nếu minimumIdle thấp. Tuy nhiên, database capacity vẫn cần được tính theo maximumPoolSize nhân với số instance có thể hoạt động đồng thời.

## 11. Kiểm tra hành vi HikariCP với CRaC

Không kết luận hỗ trợ CRaC chỉ vì ứng dụng build thành công hoặc JVM restore thành công. Cần kiểm tra pool và database sau restore.

### 11.1. Kịch bản cơ bản

1. Xác nhận HikariCP version bằng dependency tree.
2. Xác nhận CRaC JDK và CRIU hoạt động trên môi trường thử nghiệm.
3. Khởi động database và ứng dụng.
4. Gửi request thực hiện query để pool có connection.
5. Kiểm tra health endpoint và log pool.
6. Đưa ứng dụng về trạng thái không còn transaction hoặc request đang dùng connection.
7. Tạo checkpoint.
8. Restore tiến trình.
9. Gửi query mới qua service.
10. Kiểm tra pool có cấp connection mới và query thành công.

### 11.2. Kiểm tra log và trạng thái pool

Có thể quan sát pool qua HikariPoolMXBean nếu MBean được bật hoặc truy cập thông qua DataSource:

~~~java
HikariPoolMXBean pool =
        dataSource.getHikariPoolMXBean();

if (pool != null) {
    System.out.println(
            "active=" + pool.getActiveConnections());
    System.out.println(
            "idle=" + pool.getIdleConnections());
    System.out.println(
            "total=" + pool.getTotalConnections());
    System.out.println(
            "waiting=" + pool.getThreadsAwaitingConnection());
}
~~~

Các số liệu này giúp hiểu pool đang có bao nhiêu connection active, idle, total và thread đang chờ. Không dùng một snapshot số liệu duy nhất để kết luận pool đã sẵn sàng; hãy kết hợp health check thực hiện query thực tế.

### 11.3. Kịch bản lỗi cần thử

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Database tạm thời unavailable khi restore | Pool không báo READY giả; lỗi có thể quan sát và retry theo policy |
| Credential hết hạn | Ứng dụng refresh credential hoặc fail restore có kiểm soát |
| Connection cũ bị database đóng | Request sau restore sử dụng connection hợp lệ mới |
| Request đang chạy khi chuẩn bị checkpoint | Ứng dụng drain hoặc từ chối checkpoint theo policy |
| Nhiều replica restore đồng thời | Database không bị vượt connection limit |
| HikariCP cũ tự quản lý bằng adapter | Không có request nào gọi delegate đã đóng |
| HikariCP đã có CRaC integration | Không đăng ký callback đóng/mở trùng pool |

Thử nghiệm trên database riêng hoặc môi trường staging. Ghi log phiên bản HikariCP, JDBC driver, CRaC JDK, database server và thời điểm checkpoint/restore để kết quả có thể tái lập.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request sau restore gặp connection reset | Connection cũ không còn hợp lệ | Xác nhận HikariCP CRaC integration hoặc adapter đã xử lý pool |
| Thiếu class org.crac khi khởi tạo | API dependency không có trên runtime classpath | Kiểm tra POM, dependency tree và scope |
| Pool đã đóng nhưng service vẫn gọi được reference cũ | DataSource delegate bị thay thế sai cách | Dùng facade ổn định hoặc framework-managed bean lifecycle |
| Pool tạo connection quá nhiều sau restore | minimumIdle, số replica hoặc warm-up gây burst | Điều chỉnh pool sizing, stagger restore và backoff |
| Checkpoint bị treo | Request/transaction hoặc resource chưa drain | Xem thread dump, timeout và thứ tự callback |
| Database từ chối kết nối | Credential, network hoặc connection limit | Kiểm tra secret, network và capacity database |
| Pool được đóng/mở hai lần | Có cả integration của HikariCP và custom Resource | Chọn một owner cho lifecycle của pool |
| Ứng dụng READY trước khi query thành công | Readiness không kiểm tra database | Chỉ đánh dấu READY sau health check thực tế |

## 13. Chọn cách tích hợp phù hợp

Có thể dùng quy tắc lựa chọn sau:

~~~text
Xác định HikariCP runtime version
             │
             ▼
        Version < 5.1.0?
          /       \
        Có         Không
        │            │
        ▼            ▼
Tự quản lý pool   Kiểm tra release có
qua CRaC Resource  CRaC integration
        │            │
        ▼            ▼
Dùng DataSource   Bảo đảm CRaC API/runtime
facade ổn định    đúng yêu cầu
        │            │
        └─────┬──────┘
              ▼
     Drain request/transaction
              │
              ▼
      Checkpoint và restore
              │
              ▼
      Query/health check thật
              │
              ▼
       Mới đánh dấu READY
~~~

Nếu đang dùng HikariCP 5.1.0 trở lên, hãy ưu tiên tích hợp CRaC đã có trong release và xác nhận hành vi của đúng phiên bản. Nếu đang ở phiên bản cũ, hãy xây dựng adapter quản lý pool một cách tường minh. Trong cả hai trường hợp, tránh hai thành phần cùng đóng/mở một pool.

## 14. Các điểm cần ghi nhận khi nâng cấp HikariCP

Khi nâng từ phiên bản cũ lên 5.1.0 hoặc phiên bản mới hơn, nên ghi lại:

- Version cũ và version mới của HikariCP.
- JDBC driver và database server version.
- JDK vendor, version, build và CRaC capability.
- Phiên bản org.crac API nếu ứng dụng khai báo dependency.
- Cách pool tham gia callback trong release đang dùng.
- Có custom Resource callback nào trước đây đang quản lý pool không.
- Thứ tự đăng ký giữa pool, service, consumer và HTTP server.
- Kết quả query trước checkpoint và sau restore.
- Số connection active/idle/total và thời gian pool sẵn sàng sau restore.

Nếu chuyển sang release có tích hợp sẵn, xem xét loại bỏ adapter cũ sau khi đã xác nhận thư viện mới thực sự quản lý pool. Không để custom callback và callback nội bộ cùng thực hiện thao tác lifecycle.

## 15. Nguyên tắc vận hành

HikariCP giúp quản lý JDBC connection hiệu quả trong vòng đời thông thường của ứng dụng. Khi thêm CRaC, cần xem connection pool là một resource có vòng đời gắn với database server và network bên ngoài tiến trình.

Hãy xác định đúng HikariCP runtime version. Từ 5.1.0, thư viện đã có tích hợp CRaC; các phiên bản cũ cần ứng dụng tự điều phối vòng đời pool. Sau đó, phối hợp việc quản lý pool với drain request và transaction, khôi phục dependency theo thứ tự và chỉ mở traffic khi query thực tế thành công.

Điểm quyết định là trạng thái của database connection sau restore. Java object còn tồn tại không chứng minh session phía database còn sống. Một lần restore chỉ hoàn tất về mặt ứng dụng khi HikariCP cấp được connection hợp lệ và các thao tác JDBC quan trọng có thể chạy bình thường.

