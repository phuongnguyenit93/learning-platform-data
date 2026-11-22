# So sánh dữ liệu mất khi dừng tiến trình với dữ liệu đã lưu bền vững

## Mục tiêu học tập

Sau khi hoàn thành bài thực hành, người học có thể:

1. Phân biệt dữ liệu nằm trong **heap của JVM**, dữ liệu **đã thực hiện câu lệnh ghi**, dữ liệu **đã COMMIT** và dữ liệu **được bảo vệ trước một loại sự cố cụ thể**.
2. Thử nghiệm việc mất dữ liệu `HashMap` khi kết thúc JVM và xác minh dữ liệu đã commit trong PostgreSQL vẫn có thể đọc lại từ một JVM mới.
3. Phân biệt dừng JVM bình thường, dừng đột ngột, đóng JDBC connection, crash PostgreSQL, mất storage và failover.
4. Thực hiện `INSERT` trong transaction rồi `ROLLBACK`, xác nhận câu SQL thành công không đồng nghĩa ghi bền.
5. Giải thích vai trò của PostgreSQL WAL, flush, `synchronous_commit`, replication và backup đối với durability, RPO và RTO.
6. Xử lý trường hợp mất phản hồi `COMMIT` bằng idempotency key, đối soát và retry có kiểm soát.
7. Thiết kế ma trận kiểm thử, bằng chứng quan sát và tiêu chí nghiệm thu để phân biệt cache miss với mất dữ liệu nguồn.

Bài thuộc chương **Thực hành tổng hợp** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module giúp người học thiết kế ranh giới persistence trong Java, nắm mô hình dữ liệu, schema, truy vấn, chỉ mục, giao dịch, cô lập, kiểm soát đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Bài này kết nối các nội dung đó qua một câu hỏi:

> Nếu ứng dụng in ra “đã lưu” rồi tiến trình bị dừng, bằng chứng nào cho biết dữ liệu còn tồn tại khi khởi động lại?

Đáp án phụ thuộc **đã ghi ở đâu, transaction đã commit hay chưa, DB/storage nào còn sống và sự cố nào đang được kiểm tra**.

## 1. Không có một nghĩa duy nhất cho từ “dừng”

| Kịch bản | Thành phần mất khả năng chạy | Điều có thể còn nguyên | Phép kiểm chứng |
| --- | --- | --- | --- |
| Java thoát bình thường | JVM ứng dụng | PostgreSQL chạy độc lập | Khởi động JVM mới, đọc DB |
| Java bị dừng đột ngột | JVM không chạy shutdown hooks bình thường | DB độc lập; hàng đã commit | Kiểm tra bằng connection mới |
| Container Java bị hủy | Process và filesystem tạm của container | DB ở nơi khác hoặc volume bền | Xác định topology/storage |
| JDBC session kết thúc trước COMMIT | Session DB và transaction chưa commit | Các transaction đã commit khác | Đọc bảng sau session close |
| PostgreSQL process crash/restart | Tiến trình DB | WAL/storage nếu còn nguyên | DB recovery và đọc lại |
| Mất điện DB host | RAM và cache dễ bay hơi | Dữ liệu được storage bảo vệ đúng | Fault model flush/storage |
| Mất primary node/volume | Compute và/hoặc storage của primary | Replica/backup ở miền lỗi khác | Failover/restore drill |
| Failover async standby | Primary thay đổi | Dữ liệu đã tới standby được promote | RPO và tiến độ WAL |

**Kill ứng dụng Java không phải kill PostgreSQL.** Một database ở server riêng không tự mất bản ghi đã commit khi JVM gọi đến nó bị dừng. Ngược lại, nếu database lưu trên filesystem ephemeral bị xóa khi container bị thay thế, chưa thể hứa dữ liệu vẫn còn.

### 1.1. Bốn trạng thái khác nhau

- **In memory:** dữ liệu ở `Map`, object heap hoặc local cache; không mặc định có bản sao bền.
- **Statement executed:** PostgreSQL đã thực thi một lệnh như `INSERT` hay `UPDATE`; transaction có thể chưa commit.
- **Committed:** database đã chấp nhận transaction và gửi xác nhận theo giao thức/cấu hình; cần xét trường hợp ACK bị mất.
- **Durable under fault model:** dữ liệu vẫn tồn tại khi xảy ra **một tập sự cố được định nghĩa**, chẳng hạn JVM crash, PostgreSQL process crash hay mất cả vùng.

Không diễn đạt “đã lưu bền vững” nếu chỉ có bằng chứng gọi `map.put` hoặc `executeUpdate` trong một transaction chưa commit.

## 2. Mô hình hai nơi lưu trữ

Thực hành dùng cùng một khóa và giá trị trong hai nơi:

- `HashMap<String,String>` giữ bản trong **heap của một JVM cụ thể**.
- Bảng PostgreSQL giữ bản trong **database độc lập**, qua JDBC transaction.

~~~text
                      Tiến trình Java P1
                  +------------------------+
Request --------> | Heap Map               |
                  | key -> value            |   mất khi P1 kết thúc
                  +-----------+------------+
                              |
                              | JDBC
                              v
                  +------------------------+
                  | PostgreSQL             |
                  | durability_lab.records |
                  | transaction + WAL      |   nằm ngoài heap P1
                  +------------------------+

                     Dừng P1, tạo P2

                  +------------------------+
                  | Tiến trình Java P2     |
                  | Heap Map mới: rỗng     |
                  +-----------+------------+
                              |
                              | JDBC
                              v
                  +------------------------+
                  | PostgreSQL             |
                  | Records đã COMMIT      |
                  +------------------------+
~~~

**Giả định quan trọng:** PostgreSQL và data directory không bị dừng/xóa cùng JVM ứng dụng, data directory có storage bền theo thiết kế, database không bị reset giữa hai lượt, và không có một tác vụ khác xóa các hàng trong lúc thử.

Không dùng thử nghiệm restart JVM này để kết luận về khả năng chịu mất ổ đĩa hoặc mất dữ liệu sau failover.

## 3. Bảng dự đoán trước khi chạy

| Tác vụ | Heap JVM đang chạy | DB nhìn từ connection khác | Sau restart JVM |
| --- | --- | --- | --- |
| Chỉ `map.put(k,v)` | Có k=v | Không có k | Heap mới rỗng; DB vẫn không có k |
| `INSERT; COMMIT` thành công | Có thể lưu cache k=v | Có k=v | Heap mới rỗng; DB vẫn có k=v |
| `INSERT` rồi `ROLLBACK` | Không nên xem là ghi thành công | Không có hàng commit từ transaction | Không có hàng đó |
| `INSERT` rồi session đóng trước COMMIT | Có thể SQL đã chạy | Không còn hàng chưa commit khi session kết thúc | Không có hàng commit từ transaction |
| COMMIT đã gửi, ACK mất | Java không chắc kết quả | Có thể có hoặc không có hàng | Đối soát theo key |
| Mất DB storage | Không liên quan đến heap của JVM cũ | Phụ thuộc replica/backup | Cần đánh giá RPO/RTO |

Đặt dự đoán trước giúp xác định bài test chứng minh điều gì, tránh việc chỉ xem một log “success” rồi diễn giải quá mức.

## 4. Chuẩn bị phòng lab an toàn

Cần JDK 17, PostgreSQL trong môi trường thử nghiệm, PostgreSQL JDBC driver trên classpath, cùng một database thử nghiệm để nhiều JVM nối vào. Không sử dụng DB production hoặc dữ liệu khách hàng thật.

### 4.1. Giữ vòng đời Java và PostgreSQL độc lập

Nếu dùng container, cách bố trí hợp lý:

~~~text
Container/Process A: Java application lab
Container/Service B: PostgreSQL lab
Persistent volume:   PostgreSQL data directory
~~~

Bài chính chỉ yêu cầu dừng **Java A**; không xóa container/volume B. Nếu không mount volume bền, việc thay thế database container có thể xóa dữ liệu do storage, tạo một bài kiểm thử **khác hẳn**.

### 4.2. Cấu hình truy cập

Chương trình Java đọc:

~~~text
LAB_JDBC_URL=jdbc:postgresql://localhost:5432/durability_lab
LAB_DB_USER=<tài khoản chỉ dùng cho lab>
LAB_DB_PASS=<secret của tài khoản lab>
~~~

Không đặt password trong source, Git hoặc argument command line. Giữ quyền database/schema vừa đủ cho thí nghiệm. Kiểm tra JDBC URL đúng database lab trước khi chạy DDL.

## 5. Tạo bảng thử nghiệm

Thực thi trên **database lab độc lập được phép**:

~~~sql
CREATE SCHEMA IF NOT EXISTS durability_lab;

CREATE TABLE IF NOT EXISTS durability_lab.records (
    request_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Lược đồ cố ý đơn giản:

- `request_key` là định danh thao tác logic, ngăn hàng trùng khóa.
- `payload` là nội dung cần so sánh giữa heap/DB.
- `created_at` là thời điểm PostgreSQL gán default, **không phải timestamp COMMIT được đo chính xác**.
- Chỉ với một bảng, có thể hiểu rõ sự khác biệt giữa `INSERT`, `ROLLBACK` và `COMMIT` trước khi làm ví dụ nhiều bảng.

Truy vấn quan sát độc lập:

~~~sql
SELECT request_key, payload, created_at
FROM durability_lab.records
ORDER BY request_key;

SELECT COUNT(*) AS committed_rows
FROM durability_lab.records;
~~~

Nếu đã chạy lab trước đó, dùng key mới cho mỗi lượt; **không TRUNCATE một database đang được dùng chung**.

## 6. Java 17: chương trình console ghi cả heap và database

Ví dụ này chạy một command loop trong **một JVM riêng**, giúp cùng một process nhận nhiều thao tác rồi được dừng. Dữ liệu trong Map chỉ sống trong process đó; dữ liệu PostgreSQL được đọc bằng connection mới.

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class DurableVsHeapLab {
    private static final Map<String, String> HEAP = new HashMap<>();

    private static Connection connect() throws SQLException {
        String url = System.getenv("LAB_JDBC_URL");
        String user = System.getenv("LAB_DB_USER");
        String pass = System.getenv("LAB_DB_PASS");
        if (url == null || user == null || pass == null
                || !url.startsWith("jdbc:postgresql:")) {
            throw new IllegalStateException(
                    "Missing or invalid lab database configuration");
        }
        return DriverManager.getConnection(url, user, pass);
    }

    private static String readDb(Connection c, String key)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement("""
                SELECT payload FROM durability_lab.records
                WHERE request_key = ?
                """)) {
            p.setString(1, key);
            try (ResultSet rows = p.executeQuery()) {
                return rows.next() ? rows.getString(1) : null;
            }
        }
    }

    private static String readCommitted(String key)
            throws SQLException {
        try (Connection c = connect()) {
            return readDb(c, key);
        }
    }

    private static void commitRecord(String key, String value)
            throws SQLException {
        try (Connection c = connect()) {
            c.setAutoCommit(false);
            boolean commitAttempted = false;
            try {
                int inserted;
                try (PreparedStatement p = c.prepareStatement("""
                        INSERT INTO durability_lab.records
                            (request_key, payload)
                        VALUES (?, ?)
                        ON CONFLICT (request_key) DO NOTHING
                        """)) {
                    p.setString(1, key);
                    p.setString(2, value);
                    inserted = p.executeUpdate();
                }

                if (inserted == 0) {
                    String existing = readDb(c, key);
                    if (!Objects.equals(existing, value)) {
                        throw new IllegalArgumentException(
                                "Same key used with different payload");
                    }
                }

                commitAttempted = true;
                c.commit();
                // Cache updated only after COMMIT returned successfully.
                HEAP.put(key, value);
                System.out.println("COMMIT ACK for " + key);
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                if (commitAttempted) {
                    System.err.println(
                            "Commit outcome may be UNKNOWN for " + key);
                }
                throw failure;
            }
        }
    }

    private static void rollbackRecord(String key, String value)
            throws SQLException {
        try (Connection c = connect()) {
            c.setAutoCommit(false);
            try (PreparedStatement p = c.prepareStatement("""
                    INSERT INTO durability_lab.records
                        (request_key, payload)
                    VALUES (?, ?)
                    """)) {
                p.setString(1, key);
                p.setString(2, value);
                p.executeUpdate();
                System.out.println("INSERT executed but not committed");
            }
            c.rollback();
            System.out.println("Transaction rolled back");
        }
    }

    private static void require(String[] args, int n) {
        if (args.length < n || args[1].isBlank()
                || (n == 3 && args[2].isBlank())) {
            throw new IllegalArgumentException(
                    "Expected command, key and optional value");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("""
            Commands:
              memory <key> <value>   store in heap only
              write  <key> <value>   commit to PostgreSQL, cache in heap
              rollback <key> <value> INSERT then rollback
              show   <key>           compare heap and committed DB
              crash                  abruptly halt this lab JVM
              exit                   exit normally
            """);

        BufferedReader in = new BufferedReader(
                new InputStreamReader(System.in));
        while (true) {
            System.out.print("lab> ");
            String line = in.readLine();
            if (line == null) {
                return;
            }
            String[] parts = line.trim().split("\\s+", 3);
            String command = parts[0];

            try {
                switch (command) {
                    case "memory" -> {
                        require(parts, 3);
                        HEAP.put(parts[1], parts[2]);
                        System.out.println("Heap only");
                    }
                    case "write" -> {
                        require(parts, 3);
                        commitRecord(parts[1], parts[2]);
                    }
                    case "rollback" -> {
                        require(parts, 3);
                        rollbackRecord(parts[1], parts[2]);
                    }
                    case "show" -> {
                        require(parts, 2);
                        System.out.println("HEAP=" + HEAP.get(parts[1]));
                        System.out.println(
                                "DB=" + readCommitted(parts[1]));
                    }
                    case "crash" -> {
                        System.err.println("Stopping lab JVM abruptly");
                        Runtime.getRuntime().halt(9);
                    }
                    case "exit" -> {
                        return;
                    }
                    default -> System.out.println("Unknown command");
                }
            } catch (SQLException | IllegalArgumentException failure) {
                System.err.println(
                        "Operation failed: "
                        + failure.getClass().getSimpleName());
            }
        }
    }
}
~~~

### 6.1. Giới hạn cần hiểu

- Chương trình là **đoạn lab**, không phải repository production. Chỉ chạy trên database/tiến trình test.
- `Runtime.getRuntime().halt(9)` dừng ngay **JVM chứa chương trình lab**, bỏ qua shutdown hooks thông thường. Không gõ `crash` trong một server JVM có tác vụ khác hoặc hệ thống thật.
- `HashMap` chỉ dùng trong command loop đơn luồng; nó không có bảo đảm chia sẻ dữ liệu giữa các JVM và không tự thread-safe.
- Câu `HEAP.put` xảy ra sau `COMMIT` trả thành công, nhưng **không nguyên tử** với DB; process crash giữa hai bước có thể làm cache thiếu trong khi DB vẫn có dữ liệu.
- Nếu COMMIT ném exception, chương trình phân loại `UNKNOWN`. Gọi rollback sau đó là best effort, **không thể đảo ngược commit đã thành công**.
- `ON CONFLICT DO NOTHING` chống bản ghi trùng khóa, còn `readDb` và `Objects.equals` kiểm tra payload khác nhau không được chấp nhận như retry tương đương.
- Test dùng primary PostgreSQL có thẩm quyền; đọc từ replica trễ có thể cho kết quả khác với trạng thái đã commit.
- Chương trình không tự tạo bảng; chạy DDL phần 5 trước.
- `show` mở một connection khác để đọc dữ liệu đã commit, giúp tránh ngộ nhận chỉ do cache/transaction hiện tại.

### 6.2. Hướng dẫn chạy

Biên dịch/chạy lớp Java 17 với PostgreSQL JDBC driver trên classpath của lab:

~~~text
java -cp "<classpath của .class và PostgreSQL JDBC driver>" DurableVsHeapLab
~~~

Classpath, biến môi trường và cách khởi chạy thực tế tùy hệ điều hành/IDE. Giữ chương trình mở để gửi nhiều command; sau `exit` hoặc `crash`, khởi động **một JVM mới** kết nối đến **cùng PostgreSQL database**. Không cần dừng PostgreSQL cho ba thí nghiệm đầu.

## 7. Thí nghiệm A: chỉ lưu trong heap

Trên JVM thứ nhất:

~~~text
lab> memory only-memory-001 alpha
Heap only

lab> show only-memory-001
HEAP=alpha
DB=null
~~~

Gõ `crash` trong tiến trình lab. Khởi động JVM mới, kết nối cùng DB:

~~~text
lab> show only-memory-001
HEAP=null
DB=null
~~~

**Kết luận:** dữ liệu `HashMap` chỉ nằm trong address space của JVM đầu tiên. `static final` không có nghĩa persistent; object/field mới được tạo trong JVM mới. Không có INSERT ở DB nên DB không chứa hàng.

Nếu thử `exit` bình thường rồi mở JVM mới, Map cũng mất. Tuy nhiên, một ứng dụng thật có shutdown hook hoặc snapshot ra file có thể tạo kết quả khác; đó là **cơ chế lưu riêng** phải được kiểm chứng. Không dựa vào shutdown hooks để hứa an toàn trước crash đột ngột.

## 8. Thí nghiệm B: COMMIT rồi mới dừng JVM

Trên JVM thứ nhất, dùng key chưa tồn tại:

~~~text
lab> write durable-001 beta
COMMIT ACK for durable-001

lab> show durable-001
HEAP=beta
DB=beta
~~~

Gõ `crash`; khởi động JVM thứ hai:

~~~text
lab> show durable-001
HEAP=null
DB=beta
~~~

Đối chiếu qua một công cụ SQL độc lập:

~~~sql
SELECT request_key, payload
FROM durability_lab.records
WHERE request_key = 'durable-001';
~~~

Điều được chứng minh là **restart JVM ứng dụng không tự xóa dữ liệu đã commit trong PostgreSQL độc lập**. Điều *chưa* được chứng minh: dữ liệu còn sau khi database process crash, storage bị mất, power loss hoặc failover sang replica.

### 8.1. Phân biệt dữ liệu mất với cache chưa được nạp lại

Sau restart, cache rỗng có thể làm API đọc từ Map báo “không có”, dù database có hàng. Đây là lỗi **đường đọc/caching**, không phải bằng chứng nguồn bền đã mất.

~~~text
PostgreSQL: durable-001 -> beta
Cache JVM mới: chưa nạp
API chỉ đọc cache: kết quả sai nếu coi cache là source of truth
API cache-aside: cache miss -> đọc PostgreSQL -> nạp lại
~~~

Tái tạo cache cần chú ý stampede, TTL, invalidation race và quyền tenant, nhưng **cache không thay thế WAL/backup của nguồn dữ liệu**.

## 9. Thí nghiệm C: INSERT đã chạy nhưng rollback

Với key mới:

~~~text
lab> rollback rollback-001 gamma
INSERT executed but not committed
Transaction rolled back

lab> show rollback-001
HEAP=null
DB=null
~~~

Truy vấn riêng:

~~~sql
SELECT COUNT(*)
FROM durability_lab.records
WHERE request_key = 'rollback-001';
~~~

Kỳ vọng `0`, với giả định key mới và không có writer khác. `executeUpdate()` đã chạy thành công nhưng transaction được rollback nên không có hàng được commit.

### 9.1. Bài học về `autoCommit`

- `autoCommit=true`: một statement thành công có thể được tự commit; lỗi mạng sau statement ghi có thể tạo **kết quả chưa rõ** dù code không gọi `commit()`.
- `autoCommit=false`: các statement trong transaction cần COMMIT; `executeUpdate()==1` không chứng minh giao dịch đã được ghi bền.
- `rollback()` hủy phần chưa commit của transaction. Nếu COMMIT đã hoàn tất, rollback sau đó không xóa giao dịch vừa commit.
- Không được chia một nghiệp vụ cần tính nguyên tử thành hai connection autocommit độc lập chỉ vì mỗi statement đều chạy nhanh.

Với nhiều bảng, cần đặt cập nhật stock, tạo order và outbox vào **cùng một transaction** để tránh trạng thái commit nửa chừng.

## 10. Thí nghiệm D: đóng session trước COMMIT

Để phân biệt rollback với crash, ta có thể mở connection vật lý trực tiếp, INSERT rồi đóng trước COMMIT:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class UncommittedSessionDemo {
    static Connection open() throws SQLException {
        return DriverManager.getConnection(
                System.getenv("LAB_JDBC_URL"),
                System.getenv("LAB_DB_USER"),
                System.getenv("LAB_DB_PASS"));
    }

    static void insertWithoutCommit(String key, String value)
            throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try (PreparedStatement p = c.prepareStatement("""
                    INSERT INTO durability_lab.records
                        (request_key, payload)
                    VALUES (?, ?)
                    """)) {
                p.setString(1, key);
                p.setString(2, value);
                p.executeUpdate();
                // Cố ý không gọi c.commit().
            }
            // Kết thúc JDBC physical session; uncommitted tx bị rollback.
        }
    }

    static boolean exists(String key) throws SQLException {
        try (Connection c = open();
             PreparedStatement p = c.prepareStatement("""
                    SELECT 1 FROM durability_lab.records
                    WHERE request_key = ?
                    """)) {
            p.setString(1, key);
            try (ResultSet rs = p.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

Sau khi gọi `insertWithoutCommit("no-commit-001","delta")` với key mới, kiểm tra `exists("no-commit-001") == false` từ connection khác.

Những giới hạn cần nhớ:

- `DriverManager.getConnection` ở đây tạo connection trực tiếp. Với HikariCP, `Connection.close()` thường trả handle về pool; phải kiểm tra pool có rollback/reset đúng không.
- Nếu **mạng bị cắt** nhưng PostgreSQL chưa phát hiện connection chết, transaction có thể vẫn tồn tại tạm thời. “Java bị timeout” không chứng minh DB đã rollback ngay lập tức.
- Trong chương trình thật, khi muốn hủy transaction, nên gọi `rollback()` rõ ràng; ví dụ cố ý đóng mà không commit để kiểm chứng session cleanup.
- Thí nghiệm này khác với **mất phản hồi COMMIT** sau khi server đã commit.

## 11. Mất phản hồi COMMIT không phải rollback chắc chắn

Có hai lịch sử khác nhau nhưng cùng triệu chứng lỗi socket:

~~~text
Lịch sử A                      Lịch sử B
Java gửi COMMIT                Java gửi COMMIT
COMMIT chưa đến DB             DB COMMIT thành công
Connection hỏng                ACK bị mất trên đường về
Java thấy SQLException         Java thấy SQLException
DB không có row                DB có row
~~~

Ứng dụng chỉ biết rằng **không nhận được câu trả lời đáng tin từ kết nối cũ**. Không thể suy chắc A hay B chỉ từ exception.

### 11.1. Fault injection ở ranh giới ứng dụng

Một hook dành riêng cho integration test có thể gọi COMMIT thật rồi làm caller quan sát lỗi:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLTransientConnectionException;

public final class CommitFailureHook {
    @FunctionalInterface
    public interface CommitAction {
        void commit(Connection c) throws SQLException;
    }

    public static CommitAction commitThenLoseAck() {
        return c -> {
            c.commit();
            throw new SQLTransientConnectionException(
                    "Synthetic lost COMMIT response", "08006");
        };
    }
}
~~~

Đây là **mô phỏng kết quả quan sát của caller**, không phải mô phỏng TCP packet loss thật vì `c.commit()` đã trả thành công trong JVM trước khi hook ném lỗi.

Kết quả cần kiểm:

1. Database có đúng một hàng đã commit theo request key.
2. Caller báo trạng thái `UNKNOWN`, không tuyên bố rollback.
3. Retry **cùng key và cùng payload** không ghi lại hai lần.
4. Retry cùng key nhưng **khác payload** bị từ chối.
5. Việc gọi `rollback()` sau lost ACK không được xem là hành động đảo ngược COMMIT trước đó.

### 11.2. Đối soát trên nguồn có thẩm quyền

~~~text
COMMIT response unknown
        |
        v
Mở connection mới tới primary/authority phù hợp
        |
        +-- Có row cùng key và payload
        |       -> trả outcome đã lưu
        |
        +-- Có row cùng key, payload khác
        |       -> conflict, không ghi trùng
        |
        +-- Không thấy row
                -> chưa kết luận rollback chỉ vì thiếu row
                -> cân nhắc transaction cũ, lag/failover
                -> retry cùng key với UNIQUE và transaction
                   theo deadline/reconciliation protocol
~~~

Đọc replica đang trễ không phải cách đáng tin để quyết định một COMMIT vừa rồi có thất bại hay không. Nếu primary mới mất một commit đã ACK vì async failover, cần bằng chứng ngoài DB/đối tác theo kế hoạch RPO.

## 12. PostgreSQL WAL: vì sao COMMIT có thể bền dù trang bảng chưa flush?

**WAL (Write-Ahead Log)** cho phép PostgreSQL ghi thông tin phục hồi trước khi những trang dữ liệu thay đổi được ghi tới storage. Trong cấu hình bền phù hợp, WAL commit record được flush theo chính sách trước khi COMMIT trả ACK.

~~~text
Java transaction
      |
      v
PostgreSQL thực hiện SQL trong transaction
      |
      v
WAL record / commit record
      |
      v
Flush theo chính sách durability
      |
      v
COMMIT ACK
      |
      v
Data pages có thể tiếp tục được ghi sau đó
~~~

Điều cần phân biệt:

- Bộ đệm Java/JDBC ≠ PostgreSQL shared buffers ≠ OS page cache ≠ storage không bay hơi.
- COMMIT không bắt buộc mọi trang bảng đã được flush ngay khi trả ACK; WAL có thể dùng để redo trong crash recovery.
- `fsync`, chất lượng storage flush, filesystem và thiết bị tác động đến durability sau power loss.
- `synchronous_commit=on` thường chờ local WAL flush; khi có synchronous standby được cấu hình đúng còn có mức ACK standby tương ứng.
- `synchronous_commit=off` có thể ACK trước khi WAL commit được flush cục bộ, mở cửa sổ mất commit gần crash.
- Thí nghiệm dừng JVM **không** đo hoặc chứng minh những chi tiết storage này.

**Không tắt `fsync`, xóa WAL hoặc đổi cấu hình durability trên production** để làm bài thử. Muốn kiểm tra power loss, phải dùng phòng lab có fault model an toàn và phù hợp.

## 13. Dừng Java, crash PostgreSQL và mất storage là ba bài khác nhau

### 13.1. Chỉ dừng Java

- Heap P1 mất.
- PostgreSQL vẫn còn process/data directory.
- Hàng đã commit đọc được từ connection mới nếu DB vẫn hoạt động đúng.
- Transaction chưa commit của session bị kết thúc sẽ rollback.

Đây là nội dung chính của bài.

### 13.2. Crash PostgreSQL process rồi restart

Nếu storage và WAL bền vẫn còn, PostgreSQL có thể recovery transaction theo trạng thái commit được bảo vệ. Cần xem log recovery và đọc dữ liệu từ DB sau restart.

Nhưng việc restart một container có persistent volume **không mô phỏng đầy đủ mất điện vật lý hoặc hỏng thiết bị**. Kết quả phải được báo với đúng phạm vi đã kiểm tra.

### 13.3. Mất volume hoặc cả node primary

Nếu không thể phục hồi data directory của primary, phải dùng replica hoặc backup ở failure domain khác. Một transaction đã commit cục bộ vẫn có thể bị mất nếu chưa được sao chép và primary storage không còn.

**Tính bền vững phải được mô tả theo loại lỗi**, chẳng hạn “vượt qua crash một process khi volume còn nguyên” khác “vượt qua mất toàn vùng”.

## 14. Async replication và RPO

~~~text
Java         PostgreSQL primary              Standby
 |                  |                            |
 |-- COMMIT ------->|                            |
 |                  | Flush WAL cục bộ           |
 |<-- COMMIT OK ----|                            |
 |                  |--- WAL đang truyền ------>|
 |                  X primary bị mất             |
 |                                               |
 |                         Standby có thể thiếu commit
~~~

Khi PostgreSQL dùng replication bất đồng bộ, primary có thể trả COMMIT OK trước khi standby nhận/flush dữ liệu. Nếu primary mất, promote standby đang trễ có thể làm mất những commit **đã ACK**.

Nếu dùng synchronous replication, có thể giảm rủi ro mất ACKed writes trong mô hình sự cố được hỗ trợ, đổi lại commit latency và availability khi không có standby cần thiết. Cần kiểm tra `synchronous_standby_names`, `synchronous_commit`, trạng thái standby, promote/fencing và failover policy.

- **RPO:** mất dữ liệu tối đa có thể chấp nhận theo thời gian khi phục hồi.
- **RTO:** thời gian tối đa có thể chấp nhận để đưa dịch vụ hoạt động lại.
- **Retention:** giữ backup/WAL bao lâu.
- **Replica lag:** bản sao chậm ra sao, chỉ là một tín hiệu chứ không phải chứng minh duy nhất về RPO.

Một bài thử Java restart không trả lời câu hỏi **có đạt RPO khi mất cả node database hay không**.

## 15. Backup/PITR và dữ liệu hỏng do lỗi logic

Replication không thay thế backup. Nếu ứng dụng chạy `DELETE` sai rồi transaction commit, replication có thể nhân bản lệnh xóa rất nhanh; cả primary và standby đều “nhất quán” nhưng dữ liệu nghiệp vụ không còn như mong muốn.

Với PostgreSQL, PITR cần một physical base backup hợp lệ, WAL liên tục, quyền truy cập/giải mã và quy trình restore được kiểm chứng. Một `pg_dump` logic độc lập không tự kết hợp tùy ý với WAL để PITR.

Ví dụ:

~~~text
01:00 base backup
13:59 WAL cuối đã bảo vệ ở kho ngoài vùng
14:00 mất primary

Nếu chuỗi backup/WAL đầy đủ và restore được:
  điểm có thể khôi phục hướng tới khoảng 13:59.
Cửa sổ mất dữ liệu theo thời gian có thể khoảng 1 phút.
~~~

Đây là ví dụ lý thuyết. Để công bố RPO cần đo **mốc recoverable đã kiểm chứng**, không chỉ dựa vào timestamp file backup.

Khi lỗi logic bắt đầu từ 09:00 nhưng phát hiện lúc 14:00, PITR về trước 09:00 có thể bỏ gần 5 giờ thay đổi hợp lệ. Cần khôi phục chọn lọc/đối soát, không tự tuyên bố RPO 1 phút cho mọi dạng corruption.

## 16. Transaction nhiều bảng và outbox

Một nghiệp vụ “đặt hàng thành công” không chỉ là một hàng dữ liệu. Nó có thể cần:

~~~text
BEGIN
  UPDATE inventory có điều kiện
  INSERT order theo request_key duy nhất
  INSERT outbox_event
COMMIT
        |
        v
Worker gửi event qua message broker
        |
        v
Consumer xử lý idempotent
~~~

Nếu ba thay đổi DB cùng transaction, chúng commit hoặc rollback cùng nhau; nếu SQL thứ ba lỗi, không được commit riêng hai câu đầu.

Ví dụ minh họa, **giả định bảng đã tồn tại**:

~~~sql
BEGIN;

UPDATE inventory
SET available = available - 1
WHERE tenant_id = 42
  AND product_id = 101
  AND available >= 1;

INSERT INTO orders (tenant_id, request_key, status)
VALUES (42, 'checkout-001', 'CONFIRMED');

INSERT INTO outbox_events (tenant_id, request_key, event_type)
VALUES (42, 'checkout-001', 'OrderConfirmed');

COMMIT;
~~~

Ví dụ chưa kiểm tra `UPDATE` ảnh hưởng đúng một hàng nên **không dùng nguyên xi cho production**. Service thực phải kiểm tra số hàng cập nhật, ràng buộc tồn kho, khóa duy nhất và transaction boundary trước khi commit.

Outbox chỉ có ý nghĩa nếu lưu trong cùng transaction với nghiệp vụ. Nếu worker gửi event rồi crash trước khi đánh dấu hoàn tất, nó có thể gửi lại; consumer phải chống side effect trùng. Rollback PostgreSQL không tự rollback email, thanh toán hay request HTTP gửi ra ngoài.

## 17. Log in “thành công” không chứng minh COMMIT

Một trình tự Java có thể như sau:

~~~java
logger.info("Start saving order");
repository.insertOrder(...);
logger.info("INSERT finished");
connection.commit();
logger.info("COMMIT acknowledged");
~~~

Nếu JVM crash sau log “INSERT finished” nhưng trước COMMIT, transaction có thể rollback. Ngược lại, DB có thể đã commit nhưng JVM crash trước khi log “COMMIT acknowledged” được flush.

Những điều không tương đương:

~~~text
INSERT executed      !=  transaction committed
Console output       !=  durable database record
COMMIT ACKed local   !=  WAL on every replica
HTTP response sent   !=  client has received it
Cache entry missing  !=  database record missing
DB restored          !=  external side effects undone
~~~

Cần ghi nhận giai đoạn acquire/execute/commit/respond, request/correlation key, SQLSTATE và kết quả đối soát. Không log PII, secret hoặc payload khách hàng để chứng minh durability.

## 18. Ma trận kiểm thử tổng hợp

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| T01 | `memory k v` rồi crash JVM | Map mới rỗng, DB chưa có k |
| T02 | `write k v` COMMIT OK rồi crash JVM | Map mới rỗng, DB vẫn có k=v |
| T03 | `write k v` rồi exit bình thường | Map mới rỗng, DB còn k=v |
| T04 | `rollback k v` | DB không có hàng commit của k |
| T05 | INSERT trong transaction chưa COMMIT | Connection khác không thấy uncommitted row ở READ COMMITTED |
| T06 | Đóng session trước COMMIT | Transaction chưa commit rollback khi session kết thúc |
| T07 | COMMIT thành công, giả lập mất ACK | Caller unknown, DB có k, retry không thêm hàng |
| T08 | Cùng key/cùng payload | Trả kết quả cũ, không ghi trùng |
| T09 | Cùng key/payload khác | Conflict, dữ liệu cũ giữ nguyên |
| T10 | Hai thread cùng key | UNIQUE không cho hai hàng trùng commit |
| T11 | Crash sau COMMIT trước cache update | DB có dữ liệu, cache mới thiếu |
| T12 | DB process restart, volume bền còn | Recovery theo WAL/config; xác minh dữ liệu |
| T13 | Mất DB storage, chỉ còn standby async | Có thể thiếu commit chưa replicate |
| T14 | Restore từ backup+WAL | Kiểm chứng mốc phục hồi thực |
| T15 | DB còn dữ liệu, cache bị xóa | Cache miss phải fallback an toàn |
| T16 | Crash sau DB commit trước publish | Outbox row còn nếu đã được commit |
| T17 | HTTP response mất sau COMMIT | Client retry cùng key, không có side effect lặp |
| T18 | Concurrent inventory với hai key khác | Transaction/conditional UPDATE giữ stock không âm |

### 18.1. Định nghĩa một test đạt

Một test phải có:

1. Trạng thái trước: key, payload, giá trị nguồn, version, session.
2. Điểm dừng xác định: JVM exit/halt, rollback, session close, commit ACK loss hoặc DB failover.
3. Nguồn đọc sau sự cố: **JVM mới và DB connection mới**; không chỉ một Map cũ.
4. Assertion nghiệp vụ: có/không có hàng, số bản ghi, không có side effect trùng.
5. Bằng chứng: SQLSTATE, query, thời điểm, trạng thái transaction.
6. Giới hạn: đã kiểm chứng JVM crash hay DB power loss, không đánh đồng.
7. Dọn dẹp: không để test ảnh hưởng môi trường khác.

Một test crash process Java một lần **không thể chứng minh toàn bộ fault model của hệ phân tán**.

## 19. Quan sát PostgreSQL và JVM

### 19.1. Session và transaction đang mở

~~~sql
SELECT pid,
       application_name,
       state,
       xact_start,
       wait_event_type
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
~~~

`idle in transaction` nghĩa session còn giữ transaction mở, **không có nghĩa transaction đã commit**. Quyền quan sát có thể hạn chế thông tin session khác; không log raw query có PII.

### 19.2. Cấu hình liên quan durability

~~~sql
SELECT name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name IN (
    'fsync',
    'synchronous_commit',
    'full_page_writes',
    'wal_level',
    'archive_mode'
)
ORDER BY name;
~~~

Chỉ quan sát, **không thay cấu hình durability trên production**. `synchronous_commit=on` ở session riêng không tự chứng minh có synchronous standby đang bảo vệ mọi commit.

### 19.3. Replication và WAL archive

~~~sql
SELECT application_name,
       state,
       sync_state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn
FROM pg_stat_replication;
~~~

~~~sql
SELECT archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time
FROM pg_stat_archiver;
~~~

Không suy trực tiếp số giây RPO từ chênh lệch LSN (đơn vị byte log). Archive có thống kê “success” cũng chưa chứng minh toàn chuỗi backup/WAL có thể restore.

### 19.4. Metrics Java hữu ích

- JVM uptime và số restart.
- Cache entry count, cache hit/miss và thời gian warm-up.
- Pool active/idle/pending và acquisition timeout.
- Transaction duration, rollback count, JDBC SQLSTATE.
- Commit attempt/ACK/unknown outcome theo request key có phạm vi bảo mật.
- Retry attempts, idempotency conflict và reconciliation backlog.
- API p95/p99, business success rate và duplicate effects.
- Replication lag, WAL archiver health và restore drill outcome.

Không gắn raw request key, tên người dùng hoặc secret vào metrics label có cardinality cao.

## 20. Những sai lầm thường gặp

**“`static final` nghĩa là dữ liệu tồn tại qua restart.”** Nó chỉ mô tả field trong một JVM/classloader, không phải dữ liệu bền.

**“Đã `map.put` là dữ liệu đã lưu.”** Map không tự viết ra DB/disk.

**“`executeUpdate() == 1` chứng minh transaction commit.”** Với autocommit tắt, transaction còn có thể rollback.

**“Log đã in ra success là đủ.”** Log trước COMMIT không bảo đảm thay đổi đã commit.

**“COMMIT bắt buộc ghi mọi data page xuống disk ngay.”** PostgreSQL có thể dựa vào WAL bền để recovery.

**“Kill JVM giống power-off PostgreSQL.”** Khác process, storage và failure domain.

**“Đóng pooled connection chắc chắn đóng session vật lý.”** Pool thường chỉ thu hồi logical handle.

**“SQLException ở COMMIT nghĩa là rollback.”** ACK có thể bị mất sau khi server đã commit.

**“Retry bằng key mới giúp yêu cầu thành công.”** Có thể tạo side effect trùng.

**“Có một standby nghĩa mọi commit đã ACK đều ở standby.”** Async replication có lag.

**“Replication thay thế backup.”** Lỗi logic có thể được nhân bản; PITR cần backup/WAL.

**“Không có cache entry nghĩa dữ liệu nguồn đã mất.”** Cache có thể chưa warm hoặc bị evict.

**“Có thể lấy kết quả trên JVM cũ để chứng minh restart.”** Phải tạo process mới.

**“Restart PostgreSQL thành công chứng minh dữ liệu sống qua mọi loại mất storage.”** Chỉ chứng minh đúng mô hình sự cố đã thử.

**“Rollback DB hoàn tác được gửi email/thanh toán.”** Tác dụng phụ ngoài DB cần idempotency và đối soát.

## 21. Bài tập thực hành

**Bài 1 — dự đoán.** Chạy `memory k1 alpha`, `write k2 beta` rồi `crash`. Dự đoán `HEAP/DB` cho mỗi key trên JVM mới. Giải thích cơ chế.

**Bài 2 — rollback.** INSERT với autocommit=false rồi rollback. Dùng connection mới kiểm tra; vì sao số hàng update thành công không đồng nghĩa đã commit?

**Bài 3 — session.** So sánh đóng `DriverManager` connection và trả `HikariCP` pooled connection về pool trong lúc transaction chưa commit. Pool cần đảm bảo trạng thái nào?

**Bài 4 — race.** Java cập nhật heap cache trước khi ghi DB, rồi DB INSERT lỗi. Hãy thiết kế lại thứ tự cập nhật và invalidation để không hiển thị dữ liệu chưa commit.

**Bài 5 — mất ACK.** Dùng commit hook “commit thật rồi throw”. Viết assertion cho trạng thái `UNKNOWN`, tra cứu kết quả và retry cùng idempotency key.

**Bài 6 — WAL.** Giải thích tại sao PostgreSQL có thể phục hồi bằng WAL dù data pages chưa flush, và ảnh hưởng của `fsync`/`synchronous_commit`.

**Bài 7 — failover.** Primary async đã ACK một commit, standby chưa nhận WAL. Khi primary mất, có thể xảy ra điều gì và RPO phụ thuộc yếu tố nào?

**Bài 8 — PITR.** Có base backup lúc 01:00 và WAL tới 13:59, sự cố lúc 14:00. Nêu mục tiêu restore, cách đo mốc hợp lệ và giới hạn của chỉ số thời gian.

**Bài 9 — outbox.** Thiết kế transaction tạo order, trừ stock và outbox; crash sau COMMIT trước publish. Định nghĩa quy trình reprocess mà không phát side effect hai lần.

**Bài 10 — cache.** JVM mới có Map rỗng nhưng DB còn hàng. Thiết kế cache miss và chống cache stampede/stale repopulation.

**Bài 11 — fault model.** Phân biệt JVM halt, DB process crash, mất volume, mất vùng và logical corruption. Mỗi loại cần bài kiểm thử nào?

**Bài 12 — integration test.** Viết JUnit 5/Testcontainers suite cho commit/rollback/lost ACK hook. Nêu điều kiện cô lập DB test và tránh dữ liệu production.

**Bài 13 — multi-tenancy.** Mở rộng khóa thành `(tenant_id, request_key)`; xác minh cùng request key ở hai tenant không xung đột hoặc lộ dữ liệu.

**Bài 14 — runbook.** Sau restart, API trả danh sách trống. Kiểm tra theo thứ tự cache, JDBC URL, tenant context/RLS, replica lag, transaction rollback, rồi mới kết luận mất dữ liệu thực.

## 22. Checklist nghiệm thu

- [ ] PostgreSQL lab chạy độc lập với JVM và có storage phù hợp.
- [ ] Dữ liệu `memory` chỉ trong heap mất sau khi tạo JVM mới.
- [ ] Dữ liệu `write` đã COMMIT tồn tại trong DB sau JVM restart.
- [ ] Trạng thái DB được kiểm tra qua connection độc lập.
- [ ] `rollback` không để lại hàng đã commit từ transaction đó.
- [ ] Test trước COMMIT và test mất ACK COMMIT được tách riêng.
- [ ] Retry giữ nguyên request key/payload và không ghi trùng.
- [ ] Không nhầm cache miss với mất dữ liệu nguồn.
- [ ] Nêu rõ giả định WAL/flush/storage/replication và fault model.
- [ ] Không thao tác phá hoại trên production và không dùng dữ liệu thật.
- [ ] Kết quả có timeline, kỳ vọng, quan sát, SQL/metrics và giới hạn.
- [ ] Báo cáo có thể được người khác tái hiện trên một database lab sạch.

## Ghi nhớ

**Dữ liệu chỉ nằm trong heap của JVM sẽ mất khi tiến trình kết thúc**, trừ khi ứng dụng có cơ chế ghi và nạp lại độc lập. **Dữ liệu đã được PostgreSQL commit theo chính sách độ bền phù hợp có thể tồn tại sau khi JVM ứng dụng dừng**, vì database không phụ thuộc vào vòng đời của heap Java. Tuy nhiên, SQL đã thực thi mà chưa COMMIT vẫn có thể rollback; còn lỗi mạng khi chờ COMMIT có thể làm kết quả **chưa xác định**.

Để thiết kế persistence đáng tin, hãy so sánh bằng **JVM và connection mới**, xác nhận transaction boundary, quan sát source of truth thay vì cache, sử dụng idempotency khi retry và nói rõ **loại sự cố được bảo vệ**. Restart Java mới là phép thử đầu tiên; WAL, replication, backup/PITR, RPO và restore drill là những tầng đánh giá rộng hơn. **Chỉ tuyên bố đã lưu bền vững khi có bằng chứng về điểm commit và phạm vi bảo vệ dữ liệu.**
