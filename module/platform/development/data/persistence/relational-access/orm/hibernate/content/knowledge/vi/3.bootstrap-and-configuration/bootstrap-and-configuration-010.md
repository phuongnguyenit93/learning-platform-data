# Quản lý thông tin xác thực, đóng tài nguyên và lỗi trong giai đoạn khởi động Hibernate

## 1. Vì sao giai đoạn khởi động cần được thiết kế riêng?

Khởi tạo Hibernate ORM không chỉ là gọi `buildSessionFactory()`. Ứng dụng phải lấy cấu hình kết nối cơ sở dữ liệu, xác thực bằng thông tin hợp lệ, thiết lập cách lấy JDBC `Connection`, đọc mapping của entity, xây dựng các dịch vụ Hibernate, xác minh sự tương thích với schema, rồi mới cho phép các request sử dụng dữ liệu. Một lỗi ở bất kỳ giai đoạn nào đều có thể khiến ứng dụng khởi động một phần: pool đã mở nhưng `SessionFactory` chưa hình thành, một số tài nguyên còn tồn tại, hoặc HTTP server đã nhận traffic khi Hibernate chưa dùng được.

Trong chủ đề **khởi tạo và cấu hình Hibernate**, cần giải quyết đồng thời ba vấn đề:

1. **Thông tin xác thực và cấu hình nhạy cảm:** lấy từ nguồn được quản lý, phân quyền tối thiểu, không đưa mật khẩu vào source code hay log.
2. **Quyền sở hữu và đóng tài nguyên:** xác định ai tạo và ai chịu trách nhiệm đóng `SessionFactory`, connection pool, `Session` và các tài nguyên tạo dở khi khởi động lỗi.
3. **Phát hiện, phân loại và phản hồi lỗi khởi động:** phân biệt lỗi cấu hình có thể sửa bằng deployment với lỗi database tạm thời; báo lỗi rõ ràng mà không làm lộ thông tin bí mật.

Một sơ đồ vòng đời mong muốn:

```text
Đọc cấu hình + secret
        │
        ▼
Kiểm tra các tham số bắt buộc
        │
        ▼
Tạo DataSource / JDBC connection pool
        │
        ▼
Kiểm tra kết nối và quyền cần thiết
        │
        ▼
Tạo ServiceRegistry → Metadata → SessionFactory
        │
        ▼
Validate schema / mapping; xác nhận readiness
        │
        ▼
Cho phép nghiệp vụ truy cập dữ liệu
        │
        ├── Mỗi nghiệp vụ: Session + Transaction → close/commit/rollback
        │
        ▼
Shutdown: dừng nhận việc mới → chờ việc đang chạy
        │
        ▼
Đóng SessionFactory → đóng pool do ứng dụng sở hữu

LỖI Ở BẤT CỨ GIAI ĐOẠN NÀO:
        └── Giải phóng các tài nguyên đã tạo thành công
            → báo lỗi đã được làm sạch thông tin nhạy cảm
            → ứng dụng chưa sẵn sàng phục vụ
```

**Nguyên tắc bao trùm:** tài nguyên được cấp ở bước nào thì phải có đường giải phóng tương ứng nếu bước tiếp theo thất bại. Đặc biệt, tạo `SessionFactory` là thao tác tương đối tốn kém; nó thường chỉ chạy một lần cho mỗi cấu hình persistence ở thời điểm ứng dụng khởi động.

## 2. Phân biệt credentials, connection configuration và quyền truy cập

Thông tin kết nối gồm nhiều loại dữ liệu khác nhau:

| Thành phần | Ví dụ | Độ nhạy cảm và cách quản lý |
|---|---|---|
| JDBC URL | `jdbc:postgresql://db.internal:5432/library` | Thường là cấu hình môi trường; có thể tiết lộ topology nội bộ, không nên log tùy tiện |
| Username | `library_app` | Thông tin nhận dạng tài khoản dịch vụ; quản lý cùng cấu hình runtime |
| Password hoặc token DB | Giá trị lấy từ secret manager | **Bí mật**; không hard-code, không đưa vào log, exception đã format, crash dump hoặc tài liệu |
| TLS/SSL settings | `sslmode=verify-full`, đường dẫn trust store | Bảo vệ kết nối và xác minh server; certificate/private key cũng có thể cần bảo vệ |
| Pool settings | Maximum pool size, timeout | Tham số vận hành; có thể lưu trong cấu hình thông thường |
| Schema/migration settings | `hibernate.hbm2ddl.auto=validate` | Quy định cách đối chiếu mapping và schema; có thể tác động dữ liệu nếu cấu hình sai |

Credentials trả lời câu hỏi “ứng dụng **đăng nhập bằng danh tính nào**”, còn phân quyền database trả lời “danh tính đó **được phép làm gì**”. Tài khoản đăng nhập hợp lệ nhưng thiếu quyền `SELECT`, `INSERT` hoặc quyền trên schema vẫn khiến nghiệp vụ hoặc bước startup thất bại.

### Nguồn cung cấp credentials

Các lựa chọn thường gặp, từ môi trường đơn giản đến hệ thống vận hành lớn:

- **Local development:** biến môi trường hoặc tệp cấu hình local nằm ngoài version control; secret giả lập cho database local riêng biệt.
- **Container/orchestrator:** inject credentials qua cơ chế secret mount hoặc secret environment của nền tảng. Giới hạn ai được đọc secret và tránh hiển thị giá trị trong lệnh chẩn đoán.
- **Secret manager:** ứng dụng hoặc nền tảng lấy credentials từ dịch vụ quản lý secret, cấp quyền theo workload identity/role, có thể tự động xoay vòng.
- **Workload/identity-based authentication:** một số database và nền tảng hỗ trợ token ngắn hạn thay mật khẩu tĩnh. Khi đó cần đảm bảo pool có cơ chế nhận credential mới trước khi hết hạn.

Biến môi trường thường tiện lợi nhưng **không tự trở thành secret manager**: giá trị vẫn có thể bị xem qua hệ thống vận hành, bản dump hoặc quyền truy cập process. Trong môi trường production, cách inject và quyền truy cập phải được thiết kế phù hợp với nền tảng.

Không đưa mật khẩu vào:

```properties
# KHÔNG làm như sau trong file được commit vào Git:
hibernate.connection.url=jdbc:postgresql://db.internal:5432/library
hibernate.connection.username=library_app
hibernate.connection.password=real-production-password
```

Và cũng tránh nhúng secret trực tiếp vào URL:

```text
# Không nên lưu hoặc log URL chứa credentials:
jdbc:postgresql://db.internal:5432/library?user=library_app&password=secret
```

Thay vào đó, đưa riêng URL, username và password vào đối tượng cấu hình tại runtime, truyền cho pool/JDBC driver, và kiểm soát việc in log ở các lớp đó.

### Kiểm tra đầu vào trước khi tạo tài nguyên

Đối với cấu hình bắt buộc, nên **fail fast** với thông điệp chỉ chứa *tên biến bị thiếu*:

```java
static String requiredEnv(String key) {
    String value = System.getenv(key);
    if (value == null || value.isBlank()) {
        throw new IllegalStateException(
                "Thiếu cấu hình bắt buộc: " + key);
    }
    return value;
}
```

Hàm trên không xuất nội dung secret. Không viết `System.out.println(System.getenv())` hoặc log toàn bộ `Properties`/`Map` của Hibernate vì các cấu trúc đó có thể chứa password. Nên rà soát cả công cụ thu thập log, diagnostics, actuator/config endpoints và lỗi được trả về cho HTTP client.

### Phân quyền database theo nguyên tắc tối thiểu

Ví dụ một ứng dụng chỉ cần đọc/ghi dữ liệu nghiệp vụ:

- Dùng **service account** riêng cho từng ứng dụng hoặc workload.
- Chỉ cấp quyền trên các schema/table/sequence cần thiết. Tránh dùng tài khoản superuser hoặc database owner cho traffic thông thường.
- Tách danh tính **chạy migration DDL** khỏi tài khoản **chạy nghiệp vụ DML** khi hệ thống có quy trình migration.
- Tách credentials của dev, test, staging và production; không tái sử dụng một mật khẩu giữa các môi trường.
- Có quy trình thu hồi và xoay vòng khi nghi ngờ secret lộ hoặc tài khoản bị vô hiệu hóa.

Trong PostgreSQL, cấu hình cụ thể cần xét cả quyền `CONNECT` vào database, `USAGE` trên schema, quyền thao tác table và quyền sequence nếu mapping dùng sequence. Chính sách `GRANT` cần được viết theo mô hình schema thực tế.

## 3. TLS, timeout và pool cũng thuộc cấu hình an toàn

Đăng nhập thành công không đồng nghĩa đường truyền an toàn. Ứng dụng cần xác minh mình đang nói chuyện với **đúng database server**, nhất là khi kết nối qua mạng.

Với PostgreSQL JDBC, một ví dụ URL sử dụng kiểm tra TLS đầy đủ là:

```text
jdbc:postgresql://db.internal.example:5432/library?sslmode=verify-full
```

Chế độ `verify-full` yêu cầu thiết lập chứng chỉ/tin cậy và hostname phù hợp. Đây là ví dụ riêng của PostgreSQL; driver/database khác có tham số khác. Không tắt xác thực hostname hoặc chuyển về chế độ không kiểm tra certificate chỉ để “khắc phục” lỗi cấu hình TLS ở production.

Các timeout cần có ý nghĩa rõ ràng:

| Timeout | Bảo vệ khỏi điều gì? | Đặt ở đâu? |
|---|---|---|
| Connection acquisition timeout | Chờ quá lâu khi pool cạn hoặc không cấp được connection | Pool, ví dụ HikariCP `connectionTimeout` |
| Connection/login timeout | Kết nối mạng/đăng nhập DB treo quá lâu | JDBC driver, network và/hoặc DataSource |
| Socket/read timeout | Câu lệnh hoặc trao đổi với DB không phản hồi | Tham số JDBC driver, phối hợp query timeout |
| Validation timeout | Kiểm tra một connection có còn sống | Pool/JDBC validation |
| Transaction/query timeout | Nghiệp vụ hoặc SQL chạy quá lâu | Transaction manager/Session/query; database có thể có statement timeout |
| Shutdown/grace period | Chờ request đang xử lý và trả lại connection | HTTP server, orchestrator, pool lifecycle |

Không đặt tất cả timeout bằng một giá trị tùy ý. Ví dụ pool timeout chỉ giới hạn thời gian **chờ mượn connection**, không tự giới hạn thời gian query đã bắt đầu chạy. Phải chọn các giá trị dựa trên SLO, độ trễ và chính sách retry của ứng dụng.

Pool size cũng là một tài nguyên cần quản lý: nếu có 20 instance, mỗi instance cho phép 30 connections, tổng nhu cầu lý thuyết có thể lên tới 600 connections, chưa kể migration, admin và các dịch vụ khác. Pool quá lớn dễ đẩy database tới giới hạn connection và làm lỗi startup lan rộng khi nhiều instance cùng được triển khai.

## 4. Quyền sở hữu tài nguyên trong một lần bootstrap

Các thành phần Hibernate liên quan:

| Tài nguyên | Người tạo thường gặp | Ai đóng? | Điều cần nhớ khi lỗi |
|---|---|---|---|
| `StandardServiceRegistry` | Code Hibernate bootstrap | Khi xây factory thành công: vòng đời gắn với Hibernate/SessionFactory; nếu thất bại trước đó: code bootstrap dọn registry | Không bỏ quên registry tạo dở |
| `SessionFactory` | Application root hoặc framework | Owner của factory: application lifecycle hoặc container | Đóng khi shutdown hoặc khi bước init kế tiếp thất bại |
| `DataSource`/Hikari pool | Ứng dụng tự tạo hoặc dependency injection framework | **Ai sở hữu pool thì đóng pool** | Hibernate không mặc nhiên sở hữu pool được inject từ bên ngoài |
| `Session` | Mỗi nghiệp vụ hoặc framework transaction manager | Người mở session hoặc framework | Try-with-resources đối với session tự quản lý |
| `Transaction` | Business/transaction manager | Người tạo phải commit hoặc rollback dứt điểm | `Session.close()` không thay cho rollback |
| JDBC `Connection` lấy từ pool | Pool phát cho session hoặc code JDBC | Trả qua `close()`/framework quản lý | Đóng logical connection thường là **trả về pool**, không phải đóng socket vật lý |

**Quy tắc một owner:** nếu Spring Boot đã tạo và quản lý `DataSource`/`EntityManagerFactory` thì code nghiệp vụ không gọi `dataSource.close()` hay `sessionFactory.close()` khi xử lý request. Ngược lại, ứng dụng Java SE tự xây pool và factory phải tự đóng cả hai khi dừng. Đừng đóng tài nguyên dùng chung ngay sau khi tạo vì tất cả request sau đó sẽ thất bại.

Sự khác nhau giữa vòng đời startup và request:

```text
Toàn bộ tiến trình:
┌────────────────────────── SessionFactory ─────────────────────────┐
│                                                                   │
│ ┌──────────────────── DataSource / pool ────────────────────────┐  │
│ │                                                               │  │
│ │  Request A: Session A + Transaction A → close                 │  │
│ │  Request B: Session B + Transaction B → close                 │  │
│ │  Batch C:   Session C + Transaction C → close                 │  │
│ │                                                               │  │
│ └───────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
          Shutdown: dừng workload → factory.close → pool.close
```

`SessionFactory` có khả năng chia sẻ giữa các luồng; `Session` không thread-safe. Đừng tạo `SessionFactory` mỗi request, đừng lưu một `Session` vào singleton, và đừng đưa `Session` ra khỏi vòng đời sở hữu nó.

## 5. Ví dụ Java thuần: bootstrap có cleanup khi lỗi

Ví dụ sau dùng **Hibernate ORM với `jakarta.persistence`**, PostgreSQL JDBC và HikariCP; đây là kiểu tự quản lý *resource-local*. Giả sử dependencies tương thích đã được thêm và bảng `books(id BIGINT PRIMARY KEY)` đã tồn tại. Trong project thực tế, schema được quản lý bởi migration thay vì để Hibernate tự tạo khi khởi động.

Cấu hình cần inject vào process:

```text
DB_JDBC_URL=jdbc:postgresql://localhost:5432/library
DB_USERNAME=library_app
DB_PASSWORD=(cung cấp qua cơ chế secret của môi trường)
```

Với PostgreSQL production, bổ sung TLS và chính sách timeout thích hợp vào cấu hình JDBC driver/DataSource. Các tên biến ở trên chỉ là contract của ví dụ, có thể thay bằng cơ chế configuration binding của project.

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.sql.Connection;
import java.sql.SQLException;
import org.hibernate.SessionFactory;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;

public final class HibernateRuntime implements AutoCloseable {
    private final SessionFactory sessionFactory;
    private final HikariDataSource pool;

    private HibernateRuntime(SessionFactory sessionFactory,
                             HikariDataSource pool) {
        this.sessionFactory = sessionFactory;
        this.pool = pool;
    }

    public SessionFactory sessionFactory() {
        return sessionFactory;
    }

    public static HibernateRuntime start() {
        // Đọc/kiểm tra credential trước khi cấp tài nguyên.
        String url = requiredEnv("DB_JDBC_URL");
        String username = requiredEnv("DB_USERNAME");
        String password = requiredEnv("DB_PASSWORD");

        HikariDataSource pool = null;
        StandardServiceRegistry registry = null;
        SessionFactory factory = null;

        try {
            HikariConfig poolConfig = new HikariConfig();
            poolConfig.setPoolName("library-db");
            poolConfig.setJdbcUrl(url);
            poolConfig.setUsername(username);
            poolConfig.setPassword(password);
            poolConfig.setMaximumPoolSize(8);
            poolConfig.setConnectionTimeout(5_000);
            poolConfig.setValidationTimeout(2_000);
            poolConfig.setInitializationFailTimeout(10_000);

            pool = new HikariDataSource(poolConfig);

            // Kiểm tra explicit rằng tại thời điểm startup
            // có thể mượn một connection hợp lệ.
            try (Connection connection = pool.getConnection()) {
                if (!connection.isValid(3)) {
                    throw new IllegalStateException(
                            "Không xác nhận được kết nối database");
                }
            } catch (SQLException ex) {
                throw new IllegalStateException(
                        "Không xác nhận được kết nối database", ex);
            }

            registry = new StandardServiceRegistryBuilder()
                    .applySetting("hibernate.connection.datasource", pool)
                    .applySetting("hibernate.hbm2ddl.auto", "validate")
                    .applySetting("hibernate.show_sql", false)
                    .build();

            factory = new MetadataSources(registry)
                    .addAnnotatedClass(Book.class)
                    .buildMetadata()
                    .buildSessionFactory();

            // Chuyển quyền sở hữu tài nguyên sang HibernateRuntime.
            // Registry ở trạng thái thành công thuộc vòng đời factory.
            return new HibernateRuntime(factory, pool);
        } catch (RuntimeException | Error startupFailure) {
            // Chỉ dọn phần đã tạo được; ưu tiên giữ nguyên lỗi gốc.
            try {
                if (factory != null) {
                    factory.close();
                } else if (registry != null) {
                    StandardServiceRegistryBuilder.destroy(registry);
                }
            } catch (RuntimeException | Error cleanupFailure) {
                startupFailure.addSuppressed(cleanupFailure);
            }

            if (pool != null) {
                try {
                    pool.close();
                } catch (RuntimeException | Error cleanupFailure) {
                    startupFailure.addSuppressed(cleanupFailure);
                }
            }
            throw startupFailure;
        }
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu cấu hình bắt buộc: " + key);
        }
        return value;
    }

    @Override
    public void close() {
        RuntimeException firstFailure = null;

        try {
            sessionFactory.close();
        } catch (RuntimeException ex) {
            firstFailure = ex;
        }

        try {
            pool.close();
        } catch (RuntimeException ex) {
            if (firstFailure == null) {
                firstFailure = ex;
            } else {
                firstFailure.addSuppressed(ex);
            }
        }

        if (firstFailure != null) {
            throw firstFailure;
        }
    }

    @Entity
    @Table(name = "books")
    public static class Book {
        @Id
        private Long id;

        protected Book() {
        }
    }
}
```

Ở đây `HibernateRuntime` là **owner** của `SessionFactory` và Hikari pool do chính nó tạo. Nếu `pool` đã mở nhưng metadata mapping thất bại, nhánh `catch` sẽ dọn registry rồi đóng pool. Nếu factory đã hình thành nhưng bước sau gặp lỗi, nhánh dọn dẹp đóng factory trước khi đóng pool. Dùng `addSuppressed()` giúp giữ **lỗi khởi động ban đầu** làm nguyên nhân chính ngay cả khi quá trình giải phóng tài nguyên cũng lỗi.

Một cách sử dụng ở application root:

```java
public static void main(String[] args) {
    try (HibernateRuntime runtime = HibernateRuntime.start()) {
        // Bắt đầu các thành phần ứng dụng cần SessionFactory.
        // Khi dừng, đảm bảo các request/worker đã kết thúc
        // trước khi thoát khối try để đóng tài nguyên.
        runApplication(runtime.sessionFactory());
    }
}
```

`runApplication(...)` là hàm minh họa cho vòng đời service do ứng dụng triển khai. Với HTTP server chạy bất đồng bộ, cần cơ chế shutdown signal/graceful stop để hàm không trả về ngay khi vừa khởi động server; nếu trả về ngay thì `try-with-resources` sẽ đóng Hibernate quá sớm.

### Vì sao không để Hibernate tự tạo connection bằng DriverManager trong production?

Hibernate có cơ chế kết nối JDBC tích hợp để bootstrap đơn giản; nó hữu ích cho bài học và phát triển cục bộ. Nhưng với workload nhiều request, nên ưu tiên `DataSource`/connection pool được cấu hình, giám sát và sở hữu rõ ràng, thường do framework hoặc infrastructure layer cung cấp. Pool hỗ trợ tái sử dụng kết nối, giới hạn lượng connection, validation và metrics. Hibernate không thay thế các trách nhiệm vận hành này.

### Thứ tự tạo và thứ tự đóng

Một nguyên tắc tổng quát: **tạo theo thứ tự phụ thuộc, đóng theo thứ tự ngược lại**. Factory sử dụng pool nên đóng factory trước khi đóng pool. Database migration hoặc HTTP server cũng có vị trí riêng trong chuỗi: migration hoàn thành trước khi Hibernate validate, HTTP server chỉ nhận traffic sau khi dependencies cốt lõi sẵn sàng. Trong quá trình shutdown, dừng nhận việc mới trước rồi mới đóng các tài nguyên được việc đó sử dụng.

## 6. Failure path là một phần bắt buộc của bootstrap

Viết code “happy path” mà không có cleanup dễ khiến lỗi thứ cấp làm hệ thống khó chẩn đoán. Ví dụ:

```java
// Mẫu thiếu xử lý lỗi, chỉ nhằm minh họa vấn đề:
HikariDataSource pool = new HikariDataSource(config);
SessionFactory factory = createFactory(pool); // Có thể throw
startServer(factory);                         // Có thể throw
```

Nếu `createFactory(pool)` ném lỗi, pool đã tạo có thể còn threads/connections. Nếu `startServer(factory)` ném lỗi, factory và pool cùng cần đóng. Cần bao ranh giới sở hữu **toàn bộ** chuỗi startup trong một lớp lifecycle hoặc try/finally phù hợp.

### Các tình huống có thể xảy ra

| Điểm thất bại | Những gì đã tạo? | Hành động |
|---|---|---|
| Thiếu biến môi trường/secret | Chưa có pool | Báo tên cấu hình thiếu; không khởi tạo tiếp |
| Hikari config sai | Pool chưa tạo thành công | Giữ lỗi cấu hình; không cố mở Hibernate |
| Authentication DB thất bại | Pool có thể đã khởi tạo một phần | Đóng pool nếu đã tạo; kiểm tra danh tính/secret |
| Network timeout hoặc DNS không phân giải | Có thể đã có pool/service nền | Dọn pool; phân loại lỗi phụ thuộc hạ tầng |
| JDBC driver hoặc dialect không tương thích | Registry hoặc pool có thể đã tạo | Dọn registry/factory và pool; sửa dependency/config |
| Mapping entity trùng, sai kiểu hoặc thiếu identifier | Registry/metadata tạo dở | Destroy registry; không cho ứng dụng ready |
| Schema validation thất bại | Pool/registry đã tạo, factory có thể chưa xong | Dọn tài nguyên; xử lý migration/schema |
| HTTP server/startup hook thất bại sau khi Hibernate ready | Factory và pool đã tạo | Dừng các thành phần đã start, đóng factory, pool |

Nguyên tắc xử lý: giữ nguyên exception gốc để vận hành có thể tìm root cause, nhưng **không đưa nguyên văn stack trace chứa bí mật** vào HTTP response hoặc màn hình người dùng. Sổ log nội bộ cần giới hạn quyền xem và có chính sách che cấu hình nhạy cảm.

### Không được xem “đã tạo factory” là bảo đảm DB luôn sẵn sàng

Một số kiểu khởi tạo có thể trì hoãn việc mượn connection hoặc bỏ qua bước kiểm tra schema. Khi đó ứng dụng có thể dựng xong factory dù database đang không khả dụng, rồi request đầu tiên mới nổ lỗi. Nếu yêu cầu của hệ thống là *fail fast* khi DB không kết nối được, cần thiết kế **explicit health/connectivity check** và schema validation như trong ví dụ, thay vì suy luận chỉ từ sự tồn tại của `SessionFactory`. Ngay cả khi check thành công lúc startup, kết nối vẫn có thể mất về sau; runtime health và retry của nghiệp vụ là mối quan tâm riêng.

## 7. Nhận diện và phân loại lỗi khởi động

Các exception thực tế khác nhau giữa Hibernate, JDBC driver, database và framework; vì vậy nên phân loại theo **nguyên nhân** thay vì chỉ khớp tên exception.

| Nhóm lỗi | Triệu chứng | Điều cần kiểm tra |
|---|---|---|
| Config/secret missing | `IllegalStateException` khi đọc config; null/empty password | Biến bắt buộc, inject secret, tên key, quyền đọc secret |
| Authentication/authorization | SQLState liên quan login/permission, thông báo authentication failed | Username, password, secret version, quyền CONNECT/USAGE/DML |
| Network/DB availability | Connection refused, DNS error, timeout, pool init failure | Host/port, network policy, service endpoint, DB đã khởi động chưa |
| TLS/certificate | Handshake failure, hostname mismatch, certificate path error | CA, trust store, hostname, expiry, TLS mode |
| Hibernate mapping | MappingException/AnnotationException hoặc lỗi metadata | `@Entity`, `@Id`, association, type, dialect, package scan |
| Schema mismatch | Schema validation failure, thiếu table/column/sequence | Chạy đúng migration, schema/search_path, quyền metadata |
| Driver/dependency | Driver not found, `NoClassDefFoundError`, incompatibility | JDBC driver, Hibernate/Jakarta versions, classpath |
| Resource exhaustion | DB “too many connections”, pool timeout, out of file descriptors | Tổng pool size, số instance, leak, capacity |
| Database state | DB đang restart, read-only, maintenance, failover | Readiness của DB, khả năng ghi và cơ chế chuyển đổi |

JDBC `SQLException` có `getSQLState()` và `getErrorCode()` giúp chuẩn hóa chẩn đoán. Với PostgreSQL, các nhóm SQLState thường tham khảo gồm `08xxx` (connection exception), `28xxx` (authorization specification), `42xxx` (syntax/access rule violation) và mã cụ thể cho database không tồn tại. Mã cần tra theo **driver và database thực tế**; đừng xây logic retry dựa trên một chuỗi thông báo tiếng Anh vốn có thể thay đổi.

Ví dụ trích xuất SQLState từ chuỗi nguyên nhân:

```java
import java.sql.SQLException;

static String findSqlState(Throwable problem) {
    Throwable current = problem;
    while (current != null) {
        if (current instanceof SQLException sql) {
            return sql.getSQLState();
        }
        current = current.getCause();
    }
    return null;
}
```

Ở production, exception chain có thể chứa các `SQLException` bổ sung (`getNextException()`), nên hệ thống chẩn đoán chuyên dụng cần đọc chúng nếu có. Khi phát log, ưu tiên metadata an toàn như failure category, SQLState, elapsed time, DB alias (không chứa secret) và correlation ID. Hạn chế in toàn bộ URL/secret payload. Không tự động gửi password vào telemetry hoặc error reporting.

### Ví dụ thông điệp log an toàn hơn

```text
ERROR startup.database category=AUTHENTICATION
      db_alias=primary sql_state=28P01
      message="Database authentication failed; check workload credentials"
```

```text
ERROR startup.hibernate category=SCHEMA_VALIDATION
      persistence_unit=library
      message="Schema differs from Hibernate mapping; check migrations"
```

Ví dụ trên là **định dạng log minh họa**. Mã `28P01` của PostgreSQL tương ứng tình huống password authentication failed; không phải mọi database đều có mã này. Thông điệp nên được ghi vào kênh vận hành có phân quyền, tránh phản chiếu trực tiếp chi tiết nhạy cảm tới client.

## 8. Cách phản ứng với lỗi: fail fast, retry có giới hạn và readiness

Không phải mọi lỗi cần cùng một chính sách.

**Lỗi gần như chắc chắn cần sửa cấu hình** như thiếu secret, mật khẩu sai, mapping invalid, thiếu driver, schema chưa đúng version hoặc thiếu quyền bắt buộc không nên retry liên tục trong cùng một process. Retry không sửa được sai cấu hình; nó chỉ tạo thêm log, connection attempts và có thể gây lock tài khoản.

**Lỗi tạm thời** như DB chưa sẵn sàng lúc deploy, một lần DNS failure hoặc một giai đoạn failover có thể được xử lý bằng:

- Một số lần thử lại **có giới hạn** với backoff và jitter ở tầng khởi động hoặc do orchestration platform khởi động lại workload.
- Timeout rõ ràng cho mỗi lần thử; tránh treo startup vô thời hạn.
- Giới hạn tổng thời gian retry phù hợp với startup budget và rollout.
- Chỉ retry những trường hợp được nhận diện là transient; logging có cấu trúc để biết số lần và thời gian.

Không retry vô hạn mọi `HibernateException` vì phần lớn lỗi mapping/schema không tự biến mất. Cũng không nên để hàng trăm instance cùng retry đồng thời với khoảng cách cố định 100 ms: chúng có thể làm tăng tải vào database đúng lúc nó đang hồi phục.

### Readiness và liveness

- **Readiness** cho biết instance đã đủ điều kiện nhận request. Nếu database là dependency bắt buộc, chỉ đánh dấu ready sau khi bootstrap Hibernate và kiểm tra điều kiện cần thiết.
- **Liveness** cho biết process còn hoạt động và cần được khởi động lại hay không. Không nên khiến một sự cố database ngắn lập tức biến mọi liveness probe thành thất bại và tạo vòng khởi động lại dây chuyền.
- **Startup probe** (nếu nền tảng hỗ trợ) cho phép ứng dụng có thời gian bootstrap/migration hợp lý trước khi liveness bắt đầu được áp dụng.

Sau startup, readiness có thể giảm khi phụ thuộc không còn hoạt động; tuy nhiên health-check phải có timeout, tần suất hợp lý, tránh tạo truy vấn tốn kém. Việc ứng dụng mất kết nối DB trong lúc đang chạy không thể khắc phục chỉ bằng kiểm tra connection tại thời điểm bootstrap.

### Schema migration và trình tự khởi động

Một chuỗi thường gặp:

```text
Lấy cấu hình/credentials
        ↓
Kiểm tra DB connectivity
        ↓
Chạy migration (Flyway/Liquibase hoặc quy trình deploy riêng)
        ↓
Khởi tạo Hibernate với hbm2ddl.auto=validate
        ↓
Kiểm tra health → sẵn sàng nhận traffic
```

Không tùy tiện dùng `hibernate.hbm2ddl.auto=create` hay `create-drop` ở production vì có thể xóa/tạo lại bảng và dữ liệu. Khi nhiều instance cùng khởi động, migration nên được phối hợp để tránh chạy song song không kiểm soát. Nếu migration nằm trong job độc lập, application chỉ cần chờ schema đạt đúng version rồi validate.

## 9. Xoay vòng credentials khi ứng dụng đang hoạt động

Secret không cố định mãi. Thay đổi password ở secret manager **không bảo đảm** một `HikariDataSource` đã chạy tự động dùng password mới. Pool có thể vẫn giữ thông tin đăng nhập đã nhận khi khởi tạo; connection đang mở có thể tiếp tục hoạt động hoặc bị database đóng, tùy chính sách server.

Một quy trình thay đổi an toàn cần xem xét:

1. Phát hành credentials mới, phân phối đến workload theo cơ chế được hỗ trợ; nếu có thể, tạo khoảng thời gian credential cũ và mới cùng hợp lệ.
2. Đảm bảo pool **mở connection mới bằng thông tin mới**: qua API rotate credential được pool/driver hỗ trợ hoặc tạo pool và factory thay thế, tùy kiến trúc.
3. Đưa workload mới vào trạng thái ready, chuyển lưu lượng, chờ transaction đang chạy hoàn tất.
4. Đóng factory/pool cũ theo đúng ownership, thu hồi credentials cũ và xác minh không còn kết nối dùng secret đã bị thu hồi.

Nếu dùng token ngắn hạn hoặc IAM database auth, credential acquisition cần tương thích với thời hạn sống của token và cơ chế tạo connection mới; dùng một token được lấy đúng một lần rồi giữ vô hạn trong cấu hình pool thường không đáp ứng được mục tiêu xoay vòng.

Không ghi password mới ra log để “xác minh cấu hình”; dùng số phiên bản secret, định danh môi trường hoặc phép kiểm tra kết nối có giới hạn quyền để đối chiếu. Không lưu một bản “fallback password” hard-coded trong code để vượt qua trường hợp secret store tạm lỗi.

## 10. Khác biệt khi dùng Spring Boot hoặc container quản lý

Với Spring Boot/JPA, ứng dụng thường khai báo connection settings và để container tạo `DataSource`, `EntityManagerFactory` cùng transaction manager. Các property thông dụng:

```properties
# Ví dụ tên biến ở môi trường được Spring bind vào các property:
spring.datasource.url=jdbc:postgresql://db.internal:5432/library
spring.datasource.username=library_app
spring.datasource.password=(inject từ secret, không commit giá trị thực)

spring.jpa.hibernate.ddl-auto=validate
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.connection-timeout=5000
```

Trong Spring, cách tốt hơn là để giá trị password đến từ environment/config binding của nền tảng triển khai, không lưu trong file `application.properties` được commit. Ví dụ deployment có thể inject:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

Các biến trên minh họa convention environment của Spring Boot. Trong cấu hình nâng cao, secret manager integration hoặc Kubernetes Secret mount có thể cấp giá trị bằng cách khác.

Ví dụ service sử dụng persistence context do Spring quản lý:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookLookupService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public boolean exists(Long id) {
        return entityManager.find(HibernateRuntime.Book.class, id) != null;
    }
}
```

Ở đây `@Transactional`, `EntityManager`/Hibernate `Session` và connection participation do Spring transaction manager phối hợp. Code trong service **không gọi** `entityManager.close()`, `sessionFactory.close()` hoặc tự đóng pool. Những tài nguyên thuộc Spring ApplicationContext được đóng khi context shutdown; nếu application startup lỗi, Spring cũng có cơ chế dọn bean đã khởi tạo theo lifecycle. Muốn thêm resource tự tạo ngoài context, cần đăng ký đúng destroy callback/`AutoCloseable` hoặc `@PreDestroy`, không chỉ dựa vào garbage collector.

Một số lỗi khởi động Spring Boot sẽ xuất hiện bên ngoài như `BeanCreationException` hoặc lỗi khởi tạo `entityManagerFactory`; cần lần theo root cause (DataSource/JDBC, mapping, migration, permissions) thay vì sửa thông điệp lớp bao ngoài. Không tăng retry hoặc tắt schema validation khi chưa hiểu nguyên nhân.

Nếu dùng Hibernate native trực tiếp trong Spring, tránh đồng thời tạo một `SessionFactory` riêng trong controller/service khi đã có factory do context quản lý. Hai factory không chỉ tốn tài nguyên; chúng còn có persistence context/cache/config có thể khác nhau và làm khó transaction consistency.

## 11. Shutdown đúng cách để tránh mất việc và leak kết nối

Khi process nhận tín hiệu dừng, thứ tự shutdown quan trọng không kém startup:

```text
Nhận SIGTERM / sự kiện dừng
        │
        ▼
Đánh dấu not ready, dừng nhận request / message mới
        │
        ▼
Chờ request và transaction đang chạy kết thúc
        │
        ├── thành công → commit
        └── thất bại/hủy → rollback
        ▼
Đóng consumer, scheduler, session tự quản lý
        │
        ▼
SessionFactory.close()
        │
        ▼
DataSource / pool.close() nếu ứng dụng sở hữu
        │
        ▼
Process thoát
```

Các dấu hiệu một tài nguyên không được đóng đúng:

- Sau một lần restart mềm hoặc context refresh, số connection trong database tăng dần.
- Thread của pool còn hoạt động dù module đã dừng.
- Một instance không nhận traffic nhưng vẫn giữ nhiều connection idle.
- Lỗi “too many connections” xuất hiện nhanh hơn mỗi lần deploy.
- Shutdown không kết thúc vì background worker còn dùng session hoặc pool.

Thông thường có thể theo dõi Hikari metrics (active, idle, pending, total connections), thời gian acquire connection, lỗi timeout, số transaction chờ và DB connection count. Tránh dùng metric label chứa credential hoặc JDBC URL đầy đủ vì chúng có thể làm lộ cấu hình hoặc tạo cardinality lớn.

**Lưu ý:** Hibernate đóng `SessionFactory` không tự xác nhận các transaction tùy ý đang chạy trong những thread khác. Nên ngừng cấp công việc mới và chờ/hủy công việc đang chạy theo deadline trước. Session thuộc framework cần để framework đóng; session tự quản lý cần có `try-with-resources` hoặc `finally` ở phạm vi nghiệp vụ.

## 12. Transaction failure khác với startup failure

Một lỗi phát sinh trong nghiệp vụ sau khi ứng dụng ready **không nên** khiến code đóng ngay `SessionFactory` toàn ứng dụng:

```java
import org.hibernate.Session;
import org.hibernate.Transaction;

public static void renameBook(SessionFactory factory,
                              Long bookId,
                              String title) {
    try (Session session = factory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            BookEntity book = session.get(BookEntity.class, bookId);
            if (book == null) {
                throw new IllegalArgumentException("Không tìm thấy sách");
            }
            book.setTitle(title);
            tx.commit();
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        }
    }
}
```

`BookEntity` trong ví dụ nghiệp vụ là entity đã khai báo mapping và có `setTitle()`; tên khác với class `Book` tối giản dùng để diễn giải bootstrap. Sau lỗi Hibernate/JDBC trong transaction, rollback rồi bỏ session đó; một `Session` có thể không còn trạng thái nhất quán để tiếp tục. Factory và pool dùng chung vẫn sống để phục vụ các request khác, trừ khi hệ thống đã quyết định thực hiện graceful shutdown vì lỗi hạ tầng toàn cục.

Nếu Hibernate được quản lý bởi Spring, việc rollback/close session cần tuân theo `@Transactional` và transaction manager; không chép nguyên mẫu tự quản lý resource-local vào method của Spring.

## 13. Các tình huống thực tế để xác định hướng xử lý

### Tình huống A: Secret chưa được inject

Startup báo `Thiếu cấu hình bắt buộc: DB_PASSWORD`. Không nên tự thử password rỗng, password mẫu hay credential của môi trường khác. Giải pháp là sửa deployment/secret mapping, phân quyền đọc secret và khởi động lại. Vì lỗi xảy ra trước khi pool được tạo, không cần dọn factory/pool.

### Tình huống B: DB vừa restart, kết nối bị từ chối

Startup có thể thất bại ở Hikari pool hoặc explicit `getConnection()`. Đóng pool đã tạo, ghi lại nhóm lỗi connection, sau đó retry có giới hạn hoặc để orchestrator restart tùy chính sách. Khi database hồi phục, lần startup sau kiểm tra được kết nối rồi khởi tạo Hibernate.

### Tình huống C: Password đúng nhưng Hibernate không thấy bảng

Connection thành công, nhưng `validate` báo thiếu bảng `books`. Lỗi có thể do migration chưa chạy, connect nhầm database/schema, search path sai hoặc metadata permissions thiếu. Chẩn đoán theo schema version và privileges; **không** đổi sang `hbm2ddl.auto=create` để “sửa nhanh” môi trường chứa dữ liệu.

### Tình huống D: Mapping entity sai

DB hoạt động nhưng `MetadataSources.buildMetadata()` hoặc `buildSessionFactory()` thất bại vì annotation/mapping không hợp lệ. Không retry theo mạng. Sửa mapping hoặc phiên bản thư viện, rồi triển khai lại. Registry và pool đã tạo trước đó phải được giải phóng.

### Tình huống E: Application server lỗi sau khi factory thành công

Lúc này code cần đóng các thành phần đã khởi tạo, `SessionFactory` và pool theo đúng thứ tự. Chỉ bọc try/catch quanh `buildSessionFactory()` là chưa đủ nếu startup còn nhiều bước khác.

### Tình huống F: Secret bị xoay vòng giữa lúc chạy

Các physical connection cũ có thể vẫn sống, nhưng tạo connection mới có thể thất bại vì pool còn credentials cũ. Cần hỗ trợ thay credentials theo cơ chế của pool hoặc thay thế cả pool/factory theo lifecycle; kiểm tra readiness và đóng tài nguyên cũ sau khi xử lý hết transaction. Đừng ngầm kỳ vọng sửa một biến môi trường trong container sẽ thay đổi cấu hình Java object đã khởi tạo.

## 14. Mẫu checklist triển khai cho một ứng dụng Hibernate

| Thời điểm | Điều cần xác định |
|---|---|
| Trước deploy | Nguồn secret, quyền account DB, TLS, JDBC driver, network policy và hạn mức connection |
| Trước tạo pool | Cấu hình bắt buộc đầy đủ; không log secret; giá trị timeout/pool size có căn cứ |
| Tạo pool | Fail-fast policy, khả năng lấy connection, đường đóng pool khi exception |
| Tạo Hibernate | Entity mapping, dialect/driver, registry lifecycle, schema validation, thứ tự migration |
| Hoàn tất startup | Health/readiness phản ánh dependency cần thiết; chưa nhận traffic khi khởi tạo dở |
| Trong runtime | Session/transaction có phạm vi rõ, metrics pool, timeout, rollback/close khi lỗi |
| Rotate secret | Pool nhận credential mới, drain connection cũ, theo dõi lỗi xác thực |
| Shutdown | Dừng nhận việc, chờ transaction, đóng factory, đóng pool đúng ownership |

Khi các bước này được thiết kế nhất quán, hệ thống có thể khởi động lại một cách có kiểm soát, phát hiện nhanh sai cấu hình, tránh rò rỉ connection và giữ bí mật xác thực khỏi source code, log và thông điệp lỗi.
