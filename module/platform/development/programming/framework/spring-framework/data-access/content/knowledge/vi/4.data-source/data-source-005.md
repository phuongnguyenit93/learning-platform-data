# Số kết nối tối đa, thời gian chờ mượn và thời gian sống của DataSource

Một ứng dụng Spring truy cập cơ sở dữ liệu thông qua **DataSource**. Khi DataSource được quản lý bằng **connection pool** (ví dụ HikariCP), ứng dụng thường tái sử dụng kết nối JDBC thay vì thiết lập kết nối vật lý mới cho mỗi truy vấn. Ba giới hạn phải phân biệt là:

1. **Số kết nối tối đa**: pool được phép duy trì bao nhiêu kết nối tới database đồng thời.
2. **Thời gian chờ mượn**: một lời gọi xin kết nối được phép đợi bao lâu trước khi thất bại.
3. **Thời gian sống**: một kết nối vật lý được giữ trong pool đến bao lâu trước khi được thay thế.

Bài này lấy **HikariCP với Spring Boot** làm ví dụ cụ thể. Đây là cấu hình pool thường gặp khi ứng dụng dùng spring-boot-starter-jdbc hoặc spring-boot-starter-data-jpa và HikariCP có trên classpath. Các giới hạn ở tầng pool khác với timeout của SQL, transaction và hạ tầng database.

## 1. Vòng đời mượn và trả kết nối

Hãy hình dung một pool chứa một số kết nối vật lý tới database:

~~~text
                         DataSource / HikariCP
                  +--------------------------------+
Yêu cầu A -------> | Kết nối nhàn rỗi? -> cho mượn | ----> Connection A
Yêu cầu B -------> | Chưa đạt giới hạn? -> tạo mới | ----> Connection B
Yêu cầu C -------> | Đã đầy? -> chờ kết nối trả về | ----> đợi / timeout
                  +--------------------------------+
                         ^                 |
                         |                 v
              Connection.close()      JDBC tới DB
                   trả lại pool      (SQL/transaction)
~~~

Về mặt logic, pool theo dõi:

- **Active (in-use)**: kết nối đang được ứng dụng mượn.
- **Idle**: kết nối đang rảnh, có thể được mượn.
- **Total**: tổng số kết nối mà pool đang quản lý, gần với Active + Idle ở trạng thái ổn định.
- **Pending / Waiting**: số lời gọi đang đợi được cấp kết nối; **không phải** một phần của Total.

Khi ứng dụng gọi **DataSource.getConnection()**, HikariCP chọn kết nối sẵn có, thử tạo kết nối mới khi còn chỗ hoặc đợi khi toàn bộ khả năng cấp kết nối đang bận. Khi ứng dụng gọi **Connection.close()** trên kết nối mượn từ pool, kết nối thường được **trả lại pool**, không đóng socket vật lý ngay. Kết nối chỉ bị đóng vật lý khi pool quyết định loại bỏ, kết nối hỏng hoặc pool tắt.

Trong mã JDBC tự quản lý, phải dùng try-with-resources để trả kết nối kể cả khi có exception. Trong Spring, **JdbcTemplate** và các thành phần transaction của Spring quản lý việc nhận/trả theo ngữ cảnh; đặc biệt, không đóng thủ công kết nối đang được transaction của Spring quản lý chỉ vì muốn “giải phóng sớm”.

## 2. maximumPoolSize — số kết nối tối đa

**maximumPoolSize** là giới hạn trên số kết nối vật lý do **một instance pool** quản lý, tính cả Active lẫn Idle. Trong HikariCP, mặc định thông thường là **10** nếu không có cấu hình khác; cần kiểm tra phiên bản thư viện và cấu hình Spring Boot thực tế trước khi dựa vào mặc định.

Ví dụ khi **maximumPoolSize = 8**:

| Trạng thái tại một thời điểm | Active | Idle | Tổng | Điều xảy ra |
| --- | ---: | ---: | ---: | --- |
| Có chỗ | 3 | 2 | 5 | Yêu cầu mới có thể mượn một kết nối Idle |
| Hết Idle nhưng chưa đầy | 5 | 0 | 5 | Pool có thể tạo thêm kết nối đến tối đa 8 |
| Bão hòa | 8 | 0 | 8 | Yêu cầu mới phải chờ kết nối được trả, tối đa theo connectionTimeout |
| Có một kết nối trả về | 7 | 1 | 8 | Một yêu cầu đang chờ có thể nhận kết nối đó |

Bảng là **mô hình minh họa**; quá trình tạo/kiểm tra kết nối là bất đồng bộ và thời điểm quan sát metric có thể có sai lệch nhỏ. Điều bất biến cần nhớ: tăng số thread gọi database không làm tăng pool vô hạn, còn số thread chờ **không biến thành** kết nối mới vượt quá giới hạn.

### 2.1. Giới hạn theo từng pool, không theo toàn hệ thống

Nếu có ba instance ứng dụng, mỗi instance một pool có maximumPoolSize = 8, thì ứng dụng **có thể** sử dụng tổng cộng đến 3 × 8 = **24 kết nối** database. Nếu mỗi instance có hai DataSource độc lập cùng giới hạn 8, trần lý thuyết là 3 × 2 × 8 = **48**. Database còn cần kết nối cho migration, admin, job và các dịch vụ khác.

Một điều kiện ngân sách sơ bộ:

~~~text
(số instance) × (số pool mỗi instance) × (maximumPoolSize)
    + (kết nối từ các client khác) + (phần dự phòng)
    <= (giới hạn kết nối hữu dụng của database)
~~~

Đây là **kiểm tra trần kết nối**, không phải công thức tìm kích thước pool tối ưu. Các giới hạn theo user/database, proxy, failover hoặc database được quản lý trên cloud có thể thấp hơn tổng max_connections công bố. Không tăng maximumPoolSize chỉ vì lượng request HTTP lớn: chỉ những công việc đang **giữ kết nối JDBC** mới chiếm Active.

### 2.2. Chọn kích thước pool bằng đo đạc

Bắt đầu từ cấu hình vừa phải và đo trong cùng điều kiện vận hành: thông lượng, độ trễ p95/p99, số kết nối Active/Idle/Pending, thời gian mượn/giữ kết nối, độ trễ truy vấn, CPU/I/O database, khóa và giới hạn kết nối. Tăng kích thước pool đôi khi cải thiện khả năng phục vụ, nhưng cũng có thể khiến database chạy quá nhiều truy vấn đồng thời, tăng tranh chấp, latency và giảm throughput.

Quan hệ định hướng từ Little's Law:

~~~text
Số kết nối Active trung bình ≈ tốc độ công việc DB hoàn tất mỗi giây
                            × thời gian trung bình mỗi công việc giữ kết nối
~~~

Nếu công việc DB hoàn tất **100 lần/giây**, mỗi lần giữ kết nối **0,04 giây**, số Active trung bình xấp xỉ **4**. Đây chỉ là trung bình trong trạng thái ổn định, không đủ để quyết định maximumPoolSize: phải xét burst, phân phối thời gian giữ kết nối, giao dịch dài, tài nguyên DB và yêu cầu độ trễ. Thời gian chờ pool không nằm trong thời gian **giữ** kết nối.

## 3. connectionTimeout — thời gian chờ mượn

**connectionTimeout** của HikariCP là thời gian tối đa một lời gọi **getConnection()** chờ để nhận được một kết nối khả dụng. Nếu hết thời gian mà pool chưa cấp được, lời gọi thất bại với **SQLException** (trong đường Spring có thể được chuyển thành một DataAccessException tương ứng). Đơn vị cấu hình HikariCP là **mili giây**. Mặc định HikariCP thông thường: **30.000 ms = 30 giây**; giới hạn tối thiểu theo tài liệu HikariCP là 250 ms.

Ví dụ đặt **connectionTimeout = 2.000 ms** và **maximumPoolSize = 8**:

~~~text
t = 0 ms      8 kết nối đang Active; yêu cầu thứ 9 gọi getConnection()
t = 700 ms    chưa có kết nối được trả -> tiếp tục chờ
t = 1.200 ms  nếu có kết nối khả dụng -> lời gọi có thể thành công
t ≈ 2.000 ms  nếu vẫn chưa được cấp -> lời gọi thất bại do timeout
~~~

Mỗi lời gọi có bộ đếm thời gian riêng. Bảng này mô tả nguyên lý, không đảm bảo lịch chạy giữa nhiều thread. Thời gian xin kết nối còn có thể bao gồm bước mở/kiểm tra kết nối khi pool cần tạo mới; vì vậy không nên diễn giải rằng timeout chỉ xảy ra khi Total bằng maximumPoolSize.

**connectionTimeout không giới hạn thời gian truy vấn SQL.** Ví dụ gọi getConnection() thành công trong 100 ms, sau đó chạy một SQL mất 20 giây thì connectionTimeout = 2 giây không tự ngắt truy vấn đó. Cũng không có nghĩa rằng request HTTP sẽ hoàn tất trong 2 giây, vì còn nhiều bước trước/sau việc mượn.

### 3.1. Phân biệt các loại timeout

| Giới hạn | Đo ở đâu? | Bảo vệ việc gì? |
| --- | --- | --- |
| HikariCP connectionTimeout | Chờ trong DataSource.getConnection() | Không chờ mượn kết nối mãi |
| HikariCP validationTimeout | Kiểm tra kết nối còn sống | Giới hạn thời gian xác thực kết nối |
| JDBC Statement.setQueryTimeout() | Thực thi statement, tùy driver/DBMS | Giới hạn thời gian chạy câu SQL |
| Spring @Transactional(timeout = ...) | Phạm vi transaction Spring, tùy transaction manager/tích hợp | Giới hạn thời gian giao dịch theo ngữ nghĩa framework |
| Driver connect/socket/network timeout | Bắt tay hoặc đọc/ghi mạng tới DB | Phát hiện vấn đề kết nối/hạ tầng |
| HTTP server/client timeout | Luồng request ứng dụng | Giới hạn thời gian ở tầng HTTP |

Không ghép tất cả thành một con số “timeout của database”. Đặc biệt, timeout transaction hay query chưa chắc lập tức giải phóng mọi tài nguyên nếu driver, DBMS hoặc hủy truy vấn phản ứng chậm. Phải xem hành vi thực tế của stack.

### 3.2. Chờ lâu hay thất bại sớm?

- **Quá ngắn**: các burst hợp lệ cũng có thể gây lỗi khi một số kết nối sắp được trả.
- **Quá dài**: nhiều request/thread đợi treo, làm tăng thời gian phản hồi, dễ đẩy tình trạng nghẽn lan sang server HTTP.
- **Hợp lý**: nằm trong ngân sách độ trễ end-to-end và được kiểm chứng bằng load test; ứng dụng xử lý lỗi mượn kết nối bằng phản hồi phù hợp, không tự retry dồn dập làm pool nghẽn thêm.

Trong thực tế, tăng connectionTimeout có thể chỉ khiến người dùng **chờ lâu hơn** nếu nguyên nhân gốc là query chậm, transaction giữ connection quá lâu hoặc pool quá nhỏ so với workload. Cần điều tra trước khi đổi timeout.

## 4. maxLifetime — thời gian sống của kết nối vật lý

**maxLifetime** giới hạn tuổi tối đa mong muốn của **mỗi kết nối vật lý** trong pool, tính từ khi nó được tạo. HikariCP thường mặc định **1.800.000 ms = 30 phút** (tùy phiên bản/cấu hình). Nó được dùng để chủ động luân chuyển kết nối trước khi DB, proxy, firewall hoặc load balancer chấm dứt socket theo chính sách riêng.

Quy tắc then chốt: **HikariCP không cưỡng bức đóng một kết nối đang được ứng dụng mượn chỉ vì đạt maxLifetime**. Khi kết nối quá tuổi và đang Idle, pool có thể loại bỏ nó; khi đang Active, việc nghỉ hưu thường diễn ra sau khi nó được trả lại. Vì vậy maxLifetime **không phải** giới hạn thời lượng câu SQL hay transaction.

~~~text
00:00  Kết nối vật lý X được tạo
12:00  X được mượn để thực thi nghiệp vụ
25:00  X đạt maxLifetime ví dụ 25 phút
25:00  Nếu X vẫn Active, nghiệp vụ không tự bị ngắt
27:00  X được trả; pool có thể loại X và tạo kết nối thay thế khi cần
~~~

HikariCP có cơ chế điều chỉnh nhẹ thời điểm hết tuổi giữa các kết nối để tránh đồng loạt đóng/mở tất cả một lúc. Đừng giả định việc loại bỏ sẽ đúng chính xác từng mili giây.

### 4.1. Phải xét chính sách tuổi thọ từ database và hạ tầng

Giả sử một DB proxy đặt **tuổi tối đa của mỗi connection là 30 phút**. Có thể chọn maxLifetime ở phía pool là **25 phút**, tạo khoảng đệm trước khi proxy đóng; đây là số minh họa, không phải cấu hình chuẩn cho mọi hệ thống. Nếu proxy giới hạn **15 phút**, đặt maxLifetime 25 phút sẽ không bảo vệ trước giới hạn đó.

Quan trọng: **tuổi kết nối tối đa** và **timeout vì nhàn rỗi (idle)** của DB/proxy là hai chính sách khác nhau. maxLifetime ngắn hơn tuổi tối đa bên ngoài giúp làm mới chủ động. Nhưng nếu hạ tầng cắt kết nối nhàn rỗi rất sớm, cần xem thêm keepalive/idle policy, driver TCP keepalive và cách pool kiểm tra tính sống trước khi cấp lại.

## 5. idleTimeout, minimumIdle và keepaliveTime — không nhầm với maxLifetime

Ba tham số bổ trợ giải thích vì sao kết nối Idle bị giữ hay loại bỏ.

### 5.1. idleTimeout — thời gian nhàn rỗi

**idleTimeout** là thời gian một kết nối **không được sử dụng trong pool** trước khi có thể bị loại vì dư thừa. Trong HikariCP, cơ chế giảm Idle này có ý nghĩa khi **minimumIdle nhỏ hơn maximumPoolSize**. HikariCP không loại bỏ Idle xuống thấp hơn mức tối thiểu được duy trì vì idleTimeout. Mặc định HikariCP thông thường của idleTimeout là **600.000 ms = 10 phút**; sự kiện loại bỏ có thể trễ hơn mốc do lịch bảo trì.

**minimumIdle** là số kết nối Idle mục tiêu tối thiểu mà pool cố gắng duy trì. Nếu không cấu hình minimumIdle, HikariCP thường lấy giá trị tương đương maximumPoolSize và hoạt động theo kiểu pool kích thước ổn định. Cấu hình này không bảo đảm tất cả kết nối được mở ngay đúng lúc khởi động; pool vẫn có quy trình tạo kết nối và phục hồi riêng.

Ví dụ **maximumPoolSize = 8**, **minimumIdle = 2**, **idleTimeout = 10 phút**:

- Khi tải cao, pool có thể tăng đến 8 kết nối.
- Khi tải giảm, các kết nối nhàn rỗi vượt quá mục tiêu 2 có thể lần lượt được loại sau thời gian idle.
- Pool vẫn cố duy trì 2 Idle khi khả thi; một kết nối Active không bị idleTimeout đóng vì nó **không Idle**.

Nếu không đặt minimumIdle và mặc định bằng maximumPoolSize, đừng trông chờ idleTimeout làm tổng số kết nối co xuống còn 2. HikariCP thường khuyến nghị giữ pool ổn định (không đặt minimumIdle) trừ khi có nhu cầu vận hành cụ thể.

### 5.2. keepaliveTime — kiểm tra sống cho kết nối Idle

**keepaliveTime** quy định khoảng thời gian pool chủ động kiểm tra kết nối còn sống để tránh hạ tầng ngắt kết nối vì không hoạt động. HikariCP chỉ thực hiện keepalive trên **kết nối Idle**: tạm lấy ra, kiểm tra bằng JDBC Connection.isValid() hoặc câu lệnh kiểm tra được cấu hình, rồi đưa lại pool. Giá trị khác 0 phải nhỏ hơn maxLifetime và đáp ứng giới hạn tối thiểu của HikariCP (thường 30 giây). Giá trị mặc định có thể khác theo phiên bản, nên kiểm tra bản thư viện đang dùng.

- keepalive **không** đặt giới hạn tuổi của connection.
- keepalive **không** tự dừng SQL đang chạy hoặc bảo vệ kết nối Active khỏi mọi timeout của DB/proxy.
- keepalive ở tầng pool và TCP keepalive ở OS/JDBC driver là các cơ chế khác nhau; tùy hạ tầng có thể cần cả hai.

### 5.3. Bảng đối chiếu nhanh

| Tham số | Khi nào tính/áp dụng? | Có đóng kết nối Active ngay không? | Thường giải quyết |
| --- | --- | --- | --- |
| maximumPoolSize | Số kết nối pool đang quản lý | Không | Giới hạn tải kết nối lên database |
| connectionTimeout | Thời gian lời gọi getConnection() chờ | Không | Chặn chờ pool vô hạn |
| maxLifetime | Tuổi kết nối kể từ khi tạo | Không | Luân chuyển kết nối trước ngưỡng hạ tầng |
| idleTimeout | Khoảng không sử dụng khi kết nối Idle | Không | Thu hồi Idle vượt minimumIdle |
| minimumIdle | Mức Idle pool cố duy trì | Không | Cân bằng sẵn sàng và tài nguyên |
| keepaliveTime | Định kỳ kiểm tra kết nối Idle | Không | Giảm xác suất nhận kết nối chết vì timeout nhàn rỗi |

## 6. Cấu hình trong Spring Boot

Khi Spring Boot tự cấu hình HikariDataSource, các tham số HikariCP thường được đặt dưới **spring.datasource.hikari**. Spring Boot ưu tiên HikariCP khi thư viện có mặt; nếu ứng dụng tạo DataSource thủ công hoặc có nhiều DataSource, cần kiểm tra đúng bean và prefix mà ứng dụng bind.

Một cấu hình **minh họa**, giả định URL/username/password datasource đã cấu hình riêng và phía DB/proxy cho phép kết nối vật lý tồn tại **lâu hơn 25 phút**:

Tệp application.yml:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: app-main
      maximum-pool-size: 8
      connection-timeout: 2000     # 2 giây; thời gian chờ mượn
      max-lifetime: 1500000        # 25 phút; tuổi kết nối vật lý
~~~

Ba con số là **ví dụ học tập**, không nên sao chép thành cấu hình production khi chưa đo tải và kiểm tra giới hạn DB/proxy. Các giá trị số này là **mili giây** đối với thuộc tính timeout HikariCP. Khi chỉ có một datasource, Spring Boot có thể tự cấu hình pool từ starter JDBC/JPA; cần cung cấp dependency JDBC driver phù hợp và kết nối database hợp lệ.

Nếu thực sự cần pool **co giãn số kết nối Idle**, có thể bổ sung:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 8
      minimum-idle: 2
      idle-timeout: 600000        # 10 phút
      connection-timeout: 2000
      max-lifetime: 1500000
      keepalive-time: 120000     # 2 phút, chỉ kiểm tra Idle
~~~

Khi áp dụng cấu hình thứ hai, bảo đảm keepaliveTime < maxLifetime; chọn thời gian sống dựa trên chính sách hạ tầng và đo sự thay đổi connection churn. Cấu hình này thay thế cấu hình minh họa thứ nhất, **không phải** một file YAML cần ghép nối hai khối spring ở cùng cấp.

Cấu hình tương đương (chỉ ba tham số chính) trong application.properties:

~~~properties
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.max-lifetime=1500000
~~~

Với DataSource tự khai báo, Spring Boot có thể không auto-bind các thuộc tính này theo prefix trên; cần khai báo @ConfigurationProperties/binding cho bean tương ứng. Không đoán rằng chỉnh application.yml luôn tác động đến pool đang chạy: kiểm tra cấu hình effective lúc khởi động, profile, biến môi trường và số lượng DataSource.

### 6.1. Khởi tạo và trả kết nối trong Java

Đoạn dưới là **mã minh họa bên trong ứng dụng Spring Boot đã cấu hình JdbcTemplate, driver và database**; không phải chương trình Java độc lập chạy bằng javac. Mục đích là cho thấy application code sử dụng DataSource thông qua Spring JDBC và không tự quản lý socket kết nối:

Tệp DatabaseProbeRepository.java:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DatabaseProbeRepository {
    private final JdbcTemplate jdbcTemplate;

    public DatabaseProbeRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int probe() {
        Integer value = jdbcTemplate.queryForObject(
            "SELECT 1", Integer.class
        );
        if (value == null) {
            throw new IllegalStateException("Database returned NULL");
        }
        return value;
    }
}
~~~

Với PostgreSQL, SELECT 1 trả giá trị 1. JdbcTemplate mượn và giải phóng kết nối theo quy tắc Spring; khi phương thức ở trong một Spring transaction, kết nối có thể được giữ cho đến khi transaction kết thúc. Thời điểm getConnection() thực sự xảy ra phụ thuộc cơ chế truy cập và transaction manager. Vì vậy **thời gian chạy một phương thức** chưa chắc bằng **thời gian giữ kết nối**.

Khi dùng JDBC trực tiếp ngoài transaction Spring, cần đóng tài nguyên bằng try-with-resources:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class DirectJdbcProbe {
    public static int probe(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement("SELECT 1");
             ResultSet result = statement.executeQuery()) {
            return result.next() ? result.getInt(1) : 0;
        }
    }
}
~~~

Đây cũng là **class helper trong ứng dụng có DataSource**, không phải tệp chạy độc lập vì không có main và cấu hình database. Khối try-with-resources trả connection về pool ngay cả khi statement/query thất bại. **Không dùng getConnection()/close() thô để tự quản lý kết nối trong một @Transactional khi muốn Spring quản lý cùng transaction**; nên dùng JdbcTemplate/DataSourceUtils hoặc cơ chế thích hợp.

### 6.2. Ví dụ Java 17+ độc lập tính ngân sách kết nối

Đây là bài tập tính giới hạn, **không mở kết nối database**. Lưu thành PoolBudget.java:

~~~java
public class PoolBudget {
    public static void main(String[] args) {
        int instances = 3;
        int poolsPerInstance = 1;
        int maximumPoolSize = 8;
        int databaseCapacity = 40;
        int reservedForOthers = 6;

        int applicationCeiling =
                instances * poolsPerInstance * maximumPoolSize;
        int remainingHeadroom =
                databaseCapacity - reservedForOthers - applicationCeiling;

        System.out.println("App connection ceiling: "
                + applicationCeiling);
        System.out.println("Remaining DB headroom: "
                + remainingHeadroom);
    }
}
~~~

Biên dịch/chạy trong thư mục chứa tệp, dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PoolBudget.java
java PoolBudget
~~~

Stdout chính xác:

~~~text
App connection ceiling: 24
Remaining DB headroom: 10
~~~

Nếu remainingHeadroom âm, các trần cấu hình đang vượt ngân sách DB giả định; ngay cả khi dương, vẫn phải đo hiệu năng và giới hạn thực tế. Công thức không bảo đảm DB chịu được số truy vấn chạy đồng thời đó.

## 7. Tình huống điển hình và hướng xử lý

### Tình huống A: pool bão hòa và mượn kết nối bị timeout

Giả sử maximumPoolSize = 8, Active = 8, Idle = 0 và Pending tăng liên tục. Sau connectionTimeout, một số lời gọi getConnection() thất bại. Cách xử lý hợp lý là:

1. Kiểm tra Active, Idle, Pending, số lần timeout và độ trễ borrow.
2. Tìm nơi giữ connection lâu: transaction bao quanh gọi HTTP bên ngoài, truy vấn thiếu index, lock wait, xử lý vòng lặp nặng bên trong transaction, stream ResultSet chưa đóng.
3. Giảm thời gian giữ connection, khắc phục query/lock hoặc connection leak.
4. Sau đó mới cân nhắc tăng pool nếu DB còn đủ CPU/I/O, giới hạn connection và tải thực nghiệm chứng minh có lợi.

**Không** tự động kết luận pool quá nhỏ chỉ vì có timeout; một pool đủ lớn cũng có thể cạn nếu connection không được trả hoặc DB chậm.

### Tình huống B: rất nhiều kết nối Idle

Nếu Total gần maximumPoolSize nhưng Active thấp và Pending = 0, chưa chắc có lỗi: mặc định minimumIdle có thể bằng maximumPoolSize. Có thể giữ nguyên để giảm thời gian tạo connection khi có đột biến, hoặc thử minimumIdle thấp hơn nếu chi phí giữ kết nối DB đáng kể và burst không đòi hỏi sẵn sàng cao.

Đổi sang minimumIdle nhỏ hơn khiến **idleTimeout** có tác dụng thu hẹp pool. Tuy nhiên, nếu tải tăng nhanh, pool phải thiết lập thêm kết nối và độ trễ mượn có thể tăng trong giai đoạn scale up.

### Tình huống C: kết nối bị database/proxy đóng bất ngờ

Triệu chứng có thể là lỗi I/O, connection reset, stale connection hoặc kiểm tra tính sống thất bại. Cần kiểm tra database idle timeout, tuổi kết nối tối đa của proxy, NAT/firewall và driver; chọn maxLifetime **nhỏ hơn giới hạn tuổi ở bên ngoài** và cân nhắc keepalive/TCP keepalive nếu môi trường cắt kết nối Idle.

Không hạ maxLifetime cực thấp để “chữa mọi lỗi mạng”: làm vậy có thể tạo vòng đóng/mở kết nối lớn, gây tốn CPU, TLS handshake và tài nguyên DB mà vẫn không giải quyết lỗi thực sự.

### Tình huống D: tăng pool nhưng truy vấn chậm hơn

Nếu DB đã chạm giới hạn CPU/I/O hoặc lock contention, cho phép thêm truy vấn chạy đồng thời có thể làm latency tăng. Giải pháp lúc này thường là phân tích execution plan, truy vấn, index, transaction và workload; giảm concurrency có thể tốt hơn tăng maximumPoolSize.

## 8. Quan sát metric và xác minh thay đổi

Khi dùng Spring Boot Actuator/Micrometer với cấu hình phù hợp, các metric liên quan DataSource/HikariCP thường có nhóm **jdbc.connections** và **hikaricp**. Các tên cụ thể phụ thuộc phiên bản và registry; truy vấn danh sách meter đang thực sự được expose trước khi đặt dashboard/alert.

Ví dụ nếu endpoint metrics đã được bật cho phép truy cập trên môi trường kiểm thử:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.idle
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

**Lệnh curl chỉ hoạt động khi ứng dụng đang chạy, đã có Actuator và expose endpoint metrics**; địa chỉ/cổng và tên metric phải xác minh với ứng dụng thực tế. Không mở endpoint nội bộ nhạy cảm ra Internet chỉ để tiện thử.

Quan sát tối thiểu:

| Chỉ số | Ý nghĩa khi theo dõi cùng nhau |
| --- | --- |
| Active gần Max liên tục | Pool có thể bị áp lực hoặc kết nối được giữ quá lâu |
| Idle = 0, Pending tăng | Có người chờ, pool chưa cấp kịp |
| Timeout rate tăng | Lời gọi mượn kết nối đã thất bại, cần điều tra nguyên nhân |
| Thời gian sử dụng connection cao | Query, transaction hoặc code giữ connection lâu |
| Database CPU / IO / lock wait | Phân biệt thiếu pool với nghẽn thực thi SQL |
| Total/max connections ở database | Kiểm tra tổng ngân sách của mọi app instance/pool |

Một điểm cần cảnh giác: **leakDetectionThreshold** của HikariCP nếu được bật chỉ ghi log khi connection bị giữ lâu hơn ngưỡng, **không tự thu hồi kết nối bị leak**. Transaction dài hợp lệ cũng có thể tạo cảnh báo giả. Vì thế phải dùng log, trace và thời gian giữ connection để xác định nguyên nhân, không chỉ tăng ngưỡng hoặc tắt log.

### Quy trình chỉnh cấu hình có kiểm chứng

1. Ghi nhận baseline về throughput, p95/p99, Pending, timeout, DB CPU và giới hạn kết nối.
2. Xác định mục tiêu: tránh mượn timeout, giảm phí giữ connection hay phòng kết nối bị mạng/DB ngắt.
3. Chỉnh **một nhóm tham số có liên quan** và kiểm tra ràng buộc giữa chúng; ví dụ maxLifetime < giới hạn tuổi bên ngoài, keepaliveTime < maxLifetime.
4. Chạy load test bao gồm tải bình thường, burst và lỗi database; theo dõi cả ứng dụng lẫn DB.
5. So sánh kết quả với baseline, kiểm tra thêm số instance, môi trường autoscaling, profile và DataSource thực sự đang hoạt động.
6. Giữ cấu hình đã chứng minh có lợi; nếu chỉ chuyển lỗi từ timeout sang DB quá tải, điều tra và điều chỉnh lại.

## 9. Lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| maximumPoolSize = 20 nghĩa là toàn bộ hệ thống chỉ mở 20 kết nối | Giới hạn áp dụng **mỗi pool**; phải nhân với số instance/nguồn độc lập |
| connectionTimeout = 2 giây thì SQL không thể chạy quá 2 giây | Chỉ giới hạn thời gian **mượn connection**; SQL/transaction cần timeout riêng |
| maxLifetime = 25 phút sẽ cắt transaction đúng phút 25 | HikariCP không chủ động đóng connection đang Active vì hết tuổi |
| idleTimeout = 10 phút khiến pool cố định luôn co lại | Cơ chế thu hồi Idle phụ thuộc **minimumIdle < maximumPoolSize** |
| Tăng maximumPoolSize chắc chắn làm ứng dụng nhanh hơn | Database có thể quá tải vì quá nhiều truy vấn chạy cùng lúc |
| Gọi Connection.close() luôn đóng socket vật lý | Với pooled DataSource, thông thường trả connection về pool |
| Pending = 5 nghĩa là pool đã mở thêm 5 kết nối | Pending là những lời gọi đang **chờ**, không phải Total |
| keepaliveTime thay thế maxLifetime | Keepalive thử duy trì kết nối Idle; maxLifetime luân chuyển theo tuổi |
| maxLifetime chữa được mọi timeout database | Phải phân biệt timeout do **tuổi kết nối** và timeout **nhàn rỗi** |
| leakDetectionThreshold sẽ tự sửa leak | Chỉ phát tín hiệu/log để điều tra |

## 10. Tự kiểm tra với các tình huống

**Câu 1.** Một instance có maximumPoolSize = 6, hiện 6 Active và 0 Idle. Một thread mới gọi getConnection(), connectionTimeout = 1.500 ms. Nếu không có connection nào được trả và không có đường cấp kết nối thành công, điều gì xảy ra?

**Đáp án:** thread đợi tối đa khoảng 1.500 ms rồi thất bại vì không được cấp kết nối. Nó không làm pool tự tăng lên 7 kết nối.

**Câu 2.** Có bốn replica, mỗi replica hai pool, mỗi pool maximumPoolSize = 8. Trần kết nối từ các pool này là bao nhiêu?

**Đáp án:** 4 × 2 × 8 = **64**. Cần thêm ngân sách cho kết nối ngoài ứng dụng, migration và thao tác quản trị; 64 không nói gì về throughput tối ưu.

**Câu 3.** Connection X được tạo lúc 10:00 và mượn lúc 10:24. maxLifetime = 25 phút; transaction trả X lúc 10:28. X có bị pool cưỡng bức đóng giữa giao dịch lúc 10:25 không?

**Đáp án:** **Không**. Connection đang được mượn không bị HikariCP cắt chỉ vì đạt maxLifetime; nó có thể bị nghỉ hưu khi trả về. Lỗi hạ tầng độc lập vẫn có thể làm giao dịch mất kết nối.

**Câu 4.** maximumPoolSize = 8, minimumIdle không khai báo và idleTimeout = 30 giây. Có nên mặc định kỳ vọng Total tự co về 1 sau 30 giây không?

**Đáp án:** **Không**. Khi minimumIdle mặc định bằng maximumPoolSize, idleTimeout không dùng để co pool xuống 1. Muốn co giãn Idle thì cần đặt minimumIdle nhỏ hơn maximumPoolSize và hiểu chi phí mở lại kết nối.

**Câu 5.** Monitoring thấy Active = 8/8, Pending cao, DB CPU cao, query p99 chậm. Ưu tiên tăng maximumPoolSize lên 30 ngay?

**Đáp án:** **Chưa**. Cần kiểm tra query plan, index, lock wait, thời gian giữ connection và khả năng DB chịu tải. Tăng kết nối có thể làm nghẽn DB nặng hơn.

**Câu 6.** Proxy đóng socket vật lý của mọi connection sau 20 phút, pool maxLifetime = 30 phút. Hướng chỉnh cần thử là gì?

**Đáp án:** chọn maxLifetime nhỏ hơn **20 phút**, chừa biên an toàn, kết hợp kiểm tra nguyên nhân network/idle timeout và thực nghiệm trong đúng hạ tầng. Nếu proxy quy định timeout **nhàn rỗi**, còn phải xét keepalive và chính sách Idle chứ không chỉ maxLifetime.

## 11. Ghi nhớ khi cấu hình DataSource

- **maximumPoolSize** quản lý **bao nhiêu kết nối có thể đồng thời tồn tại** trong một pool.
- **connectionTimeout** quản lý **được phép chờ bao lâu để mượn một kết nối**.
- **maxLifetime** quản lý **tuổi vật lý của một kết nối trước khi được nghỉ hưu**.
- **idleTimeout + minimumIdle** quyết định **kết nối rảnh dư thừa có được thu hồi hay không**.
- **keepaliveTime** hỗ trợ kiểm tra kết nối Idle còn sống, không giới hạn truy vấn.
- Một cấu hình tốt phải phù hợp **tải thực tế, giới hạn database, số replica, network và thời gian giao dịch**; hãy đo metric ở cả ứng dụng lẫn DB.

### Nguồn tham khảo để đối chiếu phiên bản

- HikariCP chính thức: https://github.com/brettwooldridge/HikariCP (mục Configuration, các thuộc tính maximumPoolSize, connectionTimeout, maxLifetime, minimumIdle, idleTimeout, keepaliveTime).
- Spring Boot — SQL Databases / Configure a DataSource: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Boot — Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
