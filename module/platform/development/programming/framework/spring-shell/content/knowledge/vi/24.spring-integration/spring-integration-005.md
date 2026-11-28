# Kết nối cơ sở dữ liệu và đóng tài nguyên sau khi xử lý

Một ứng dụng Spring Shell có thể cung cấp command để tra cứu, tạo hoặc cập nhật dữ liệu trong cơ sở dữ liệu. Command là giao diện cho người vận hành; việc kết nối database, chạy SQL và quản lý transaction nên nằm ở các bean nghiệp vụ của Spring.

Spring Boot tự cấu hình **DataSource** từ các thuộc tính kết nối và có thể cung cấp **JdbcTemplate**, **NamedParameterJdbcTemplate** hoặc **JdbcClient** để truy cập dữ liệu. Các abstraction này quản lý việc lấy và giải phóng tài nguyên JDBC, giúp command không phải tự mở rồi đóng connection trong mỗi lần chạy.

Khi cần dùng JDBC trực tiếp, ứng dụng phải đóng **ResultSet** và **Statement** sau khi xử lý. Connection cần được trả về pool đúng cách; nếu đang tham gia transaction do Spring quản lý, phải dùng cơ chế giải phóng tương thích transaction. Bài này kết hợp Spring Shell 4, Spring Boot 4 và Spring JDBC để trình bày các quy tắc đó.

## 1. Kiến trúc kết nối từ command đến database

Một thiết kế dễ bảo trì tách trách nhiệm thành các lớp:

| Thành phần | Trách nhiệm |
|---|---|
| Spring Shell command | Nhận option/argument, gọi service và trình bày kết quả |
| Application service | Điều phối nghiệp vụ và xác định ranh giới transaction |
| Repository/DAO | Chạy truy vấn SQL và ánh xạ kết quả |
| JdbcTemplate/JdbcClient | Quản lý JDBC resource, thực thi SQL và chuyển đổi lỗi |
| DataSource | Cung cấp connection từ connection pool |
| JDBC driver | Giao tiếp với hệ quản trị cơ sở dữ liệu |

Luồng gọi điển hình:

~~~mermaid
flowchart TD
    A["Người dùng gọi command"] --> B["Spring Shell @Command"]
    B --> C["Application service"]
    C --> D["Repository"]
    D --> E["JdbcTemplate / JdbcClient"]
    E --> F["DataSource / connection pool"]
    F --> G["JDBC Driver"]
    G --> H[("Database")]
    H --> G
    G --> F
    F --> E
    E --> D
    D --> C
    C --> B
    B --> I["Hiển thị kết quả"]
~~~

Command không nên giữ **Connection**, **PreparedStatement** hoặc **ResultSet** trong field. Những đối tượng này đại diện cho tài nguyên có vòng đời ngắn và không phù hợp với bean command singleton được Spring quản lý.

## 2. Thêm dependency JDBC và driver

Với Spring Boot 4 và Spring Shell 4, có thể khai báo các dependency bằng Gradle:

~~~gradle
dependencies {
    implementation("org.springframework.shell:spring-shell-starter")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Trong ví dụ này:

- **spring-shell-starter** cung cấp nền tảng Spring Shell.
- **spring-boot-starter-jdbc** cung cấp Spring JDBC và các thành phần auto-configuration cho JDBC.
- **postgresql** là JDBC driver cho PostgreSQL và chỉ cần ở runtime.

Nếu dùng MySQL, thay driver bằng dependency phù hợp:

~~~gradle
runtimeOnly("com.mysql:mysql-connector-j")
~~~

Dùng Spring Boot dependency management và Spring Shell BOM hoặc dependency management của Spring Initializr để giữ các phiên bản tương thích. Spring Shell 4 yêu cầu nền tảng Spring Boot 4 và Spring Framework 7.

Spring Boot ưu tiên HikariCP khi có trên classpath. Khi dùng **spring-boot-starter-jdbc**, HikariCP được đưa vào như dependency mặc định của connection pool. Không cần tự tạo pool bằng code cho trường hợp thông thường.

## 3. Cấu hình DataSource bằng application.yml

Spring Boot đọc cấu hình kết nối từ prefix **spring.datasource**. Ví dụ với PostgreSQL:

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/taskdb}
    username: ${DB_USERNAME:task_app}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      idle-timeout: 600000
~~~

Các biến môi trường giữ thông tin môi trường triển khai bên ngoài mã nguồn. Không commit mật khẩu database thật vào Git hoặc đóng gói nó trong file cấu hình phân phối.

Spring Boot thường suy ra JDBC driver từ URL. Nếu URL là PostgreSQL, driver PostgreSQL phải có trên runtime classpath. Chỉ đặt **driver-class-name** khi cần ghi đè cách suy luận mặc định.

Một số thuộc tính pool thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| **maximum-pool-size** | Số connection tối đa trong pool |
| **minimum-idle** | Số connection nhàn rỗi tối thiểu mà pool cố duy trì |
| **connection-timeout** | Thời gian tối đa chờ lấy connection từ pool |
| **idle-timeout** | Thời gian connection nhàn rỗi có thể được giữ trong pool |

Không tăng pool size tùy tiện. Tổng số connection từ tất cả instance của ứng dụng phải nằm trong giới hạn database cho phép. Khi pool cạn, command mới có thể phải chờ hoặc nhận timeout.

## 4. Spring Boot tự cấu hình DataSource và JdbcTemplate

Khi có JDBC starter, driver và cấu hình phù hợp, Spring Boot có thể tạo bean **DataSource**. Ứng dụng inject bean này vào thành phần cần kết nối.

Spring Boot cũng auto-configure **JdbcTemplate** và **NamedParameterJdbcTemplate**. Có thể inject trực tiếp qua constructor:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DatabaseHealthRepository {

    private final JdbcTemplate jdbcTemplate;

    public DatabaseHealthRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int ping() {
        return jdbcTemplate.queryForObject("select 1", Integer.class);
    }
}
~~~

Không cần tạo mới **JdbcTemplate** trong mỗi command. Hãy inject bean đã được cấu hình để dùng chung DataSource và các thiết lập Spring JDBC.

Nếu ứng dụng khai báo bean **DataSource** riêng, auto-configuration tạo DataSource mặc định sẽ không còn áp dụng. Spring Boot vẫn có thể cấu hình các thành phần JDBC dựa trên DataSource đó nếu các điều kiện tương ứng được đáp ứng. Hãy kiểm tra pool, transaction manager và vòng đời bean khi thay thế cấu hình mặc định.

## 5. Dùng JdbcTemplate để truy vấn và cập nhật

**JdbcTemplate** quản lý các bước JDBC lặp lại:

- Lấy connection từ DataSource.
- Tạo và thực thi statement.
- Duyệt ResultSet hoặc chuyển kết quả qua callback.
- Đóng statement và result set.
- Giải phóng connection đúng cách.
- Chuyển SQLException sang hệ thống exception của Spring DAO.

Ví dụ repository đọc danh sách công việc:

~~~java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {

    private final JdbcTemplate jdbcTemplate;

    public TaskRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<TaskSummary> findByStatus(String status) {
        return jdbcTemplate.query(
                """
                select id, title, status
                from task
                where status = ?
                order by id
                """,
                (rs, rowNum) -> new TaskSummary(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getString("status")
                ),
                status
        );
    }

    public int insert(String title) {
        return jdbcTemplate.update(
                "insert into task(title, status) values (?, ?)",
                title,
                "OPEN"
        );
    }
}
~~~

DTO kết quả:

~~~java
public record TaskSummary(
        long id,
        String title,
        String status) {
}
~~~

Dấu **?** là placeholder của PreparedStatement. Giá trị người dùng nhập được truyền riêng qua tham số, không nối trực tiếp vào câu SQL. Điều này giúp tránh SQL injection và xử lý đúng việc quote giá trị.

Callback **RowMapper** chỉ đọc dữ liệu từ hàng hiện tại và tạo object. Không đóng ResultSet hoặc Connection trong callback vì JdbcTemplate đang quản lý vòng đời của chúng.

## 6. Dùng NamedParameterJdbcTemplate hoặc JdbcClient

Khi câu SQL có nhiều tham số, tên tham số giúp câu truy vấn dễ đọc hơn:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NamedTaskRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public NamedTaskRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<TaskSummary> findByStatus(String status) {
        return jdbc.query(
                """
                select id, title, status
                from task
                where status = :status
                order by id
                """,
                Map.of("status", status),
                (rs, rowNum) -> new TaskSummary(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getString("status")
                )
        );
    }
}
~~~

Spring Boot auto-configure **NamedParameterJdbcTemplate** dựa trên JdbcTemplate. Nó dùng lại JdbcTemplate bên dưới để thực thi và quản lý tài nguyên.

Spring Framework cũng cung cấp **JdbcClient** để viết truy vấn theo API fluent. Spring Boot auto-configure JdbcClient khi có NamedParameterJdbcTemplate. Có thể dùng nó nếu muốn API gọn hơn; quy tắc quản lý connection vẫn do Spring JDBC đảm nhiệm.

~~~java
import java.util.List;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcClientTaskRepository {

    private final JdbcClient jdbcClient;

    public JdbcClientTaskRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public List<TaskSummary> findByStatus(String status) {
        return jdbcClient.sql("""
                        select id, title, status
                        from task
                        where status = :status
                        order by id
                        """)
                .param("status", status)
                .query((rs, rowNum) -> new TaskSummary(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getString("status")
                ))
                .list();
    }
}
~~~

Chọn một abstraction phù hợp với dự án và dùng nhất quán. Không cần trộn nhiều kiểu truy cập chỉ cho một truy vấn đơn giản.

## 7. Đặt transaction ở application service

Một command có thể gọi nhiều thao tác repository. Nếu các thao tác phải thành công hoặc thất bại cùng nhau, đặt transaction ở phương thức service:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final TaskRepository taskRepository;

    public TaskService(TaskRepository taskRepository) {
        this.taskRepository = taskRepository;
    }

    @Transactional(readOnly = true)
    public List<TaskSummary> list(String status) {
        return taskRepository.findByStatus(status);
    }

    @Transactional
    public void create(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên công việc không được để trống.");
        }
        taskRepository.insert(title.strip());
    }
}
~~~

**@Transactional(readOnly = true)** thể hiện một transaction chỉ đọc. **@Transactional** trên phương thức ghi dữ liệu cho phép Spring commit khi thành công và rollback khi có exception phù hợp với quy tắc rollback.

JdbcTemplate sử dụng **DataSourceUtils** để lấy connection. Nếu có transaction đang hoạt động, nó sử dụng connection được gắn với transaction đó. Vì vậy, nhiều thao tác JdbcTemplate trong cùng một transaction có thể dùng chung connection và được commit/rollback cùng nhau.

Đặt ranh giới transaction ở service thay vì command. Đặc biệt với shell tương tác, không mở transaction trước khi hỏi người dùng hoặc giữ connection trong lúc người dùng suy nghĩ. Chỉ bắt đầu transaction khi đã có đủ input và sẵn sàng thực thi nghiệp vụ.

## 8. Tích hợp command Spring Shell 4 với service

Trong Spring Shell 4, command annotation được đặt trên method của một Spring bean. Khi chạy cùng Spring Boot, command scanning được auto-configure; không cần dùng các annotation legacy **@ShellComponent** và **@ShellMethod** của Spring Shell 3.

Ví dụ command gọi service:

~~~java
import java.io.PrintWriter;
import java.util.List;

import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class TaskCommands {

    private final TaskService taskService;

    public TaskCommands(TaskService taskService) {
        this.taskService = taskService;
    }

    @Command(
            name = {"task", "list"},
            description = "Liệt kê công việc theo trạng thái."
    )
    public void list(
            @Option(longName = "status", defaultValue = "OPEN") String status,
            CommandContext context) {

        List<TaskSummary> tasks = taskService.list(status);
        PrintWriter out = context.outputWriter();

        if (tasks.isEmpty()) {
            out.println("Không có công việc phù hợp.");
        }
        else {
            for (TaskSummary task : tasks) {
                out.printf(
                        "%d | %s | %s%n",
                        task.id(),
                        task.title(),
                        task.status()
                );
            }
        }

        out.flush();
    }

    @Command(
            name = {"task", "create"},
            description = "Tạo công việc mới."
    )
    public String create(
            @Argument(index = 0, description = "Tên công việc") String title) {
        taskService.create(title);
        return "Đã tạo công việc.";
    }
}
~~~

Command chỉ chuyển input đến service và trình bày kết quả. Nó không biết cách mở connection, tạo PreparedStatement hoặc đóng ResultSet.

Không giữ **TaskService**, **JdbcTemplate** hoặc repository trong một biến tĩnh. Hãy để Spring inject các bean qua constructor để container quản lý dependency và transaction proxy.

## 9. Đóng resource khi dùng JdbcTemplate

Với JdbcTemplate, thông thường không cần tự viết **finally** hoặc **try-with-resources** cho connection, statement và result set do template tạo ra.

Ví dụ:

~~~java
List<TaskSummary> tasks = jdbcTemplate.query(
        "select id, title, status from task where status = ?",
        rowMapper,
        status
);
~~~

Sau khi query hoàn tất, JdbcTemplate đóng ResultSet và Statement, rồi giải phóng connection. Nếu connection thuộc transaction đang hoạt động, Spring giữ connection đó cho đến khi transaction kết thúc; nếu không, connection được trả về DataSource/pool.

Không gọi **connection.close()** hoặc **dataSource.close()** từ command khi sử dụng JdbcTemplate. Bạn không sở hữu connection nội bộ mà template đang dùng. DataSource và pool là bean do Spring quản lý.

## 10. Đóng resource khi dùng JDBC thuần

Đôi khi cần dùng API JDBC trực tiếp vì thư viện bên thứ ba yêu cầu Connection hoặc truy vấn có xử lý đặc biệt. Khi tự lấy connection ngoài transaction Spring, dùng **try-with-resources**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public class RawJdbcTaskReader {

    private static final String SQL =
            "select id, title, status from task where status = ?";

    private final DataSource dataSource;

    public RawJdbcTaskReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<TaskSummary> findOpenTasks() throws SQLException {
        List<TaskSummary> tasks = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(SQL)) {

            statement.setString(1, "OPEN");

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    tasks.add(new TaskSummary(
                            resultSet.getLong("id"),
                            resultSet.getString("title"),
                            resultSet.getString("status")
                    ));
                }
            }
        }

        return tasks;
    }
}
~~~

Các resource được đóng theo thứ tự ngược với thứ tự mở:

1. **ResultSet** đóng trước.
2. **PreparedStatement** đóng tiếp theo.
3. **Connection** được đóng cuối cùng.

Nếu có exception ở giữa vòng lặp, Java vẫn thực hiện đóng các resource. Với connection lấy từ pool, gọi **close()** thường có nghĩa là trả connection về pool để tái sử dụng, không nhất thiết đóng socket vật lý đến database.

Không lưu Connection hoặc Statement trong field để dùng cho command lần sau. Mỗi thao tác cần lấy và giải phóng tài nguyên trong cùng phạm vi xử lý.

## 11. JDBC thuần bên trong transaction Spring

Ví dụ ở phần trước dùng **DataSource.getConnection()** và **try-with-resources** cho một thao tác JDBC độc lập. Nếu phương thức đang chạy trong transaction do Spring quản lý, lấy connection trực tiếp bằng DataSource có thể không tham gia connection đã gắn với transaction.

Khi cần JDBC thuần nhưng vẫn muốn tham gia transaction Spring, dùng **DataSourceUtils**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class TransactionAwareTaskReader {

    private final DataSource dataSource;

    public TransactionAwareTaskReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Transactional(readOnly = true)
    public long countOpenTasks() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement statement =
                         connection.prepareStatement(
                                 "select count(*) from task where status = ?")) {
                statement.setString(1, "OPEN");

                try (ResultSet resultSet = statement.executeQuery()) {
                    resultSet.next();
                    return resultSet.getLong(1);
                }
            }
        }
        finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
~~~

Ở đây, **ResultSet** và **PreparedStatement** vẫn được đóng bằng try-with-resources. Connection được giải phóng bằng **DataSourceUtils.releaseConnection()** thay vì đóng trực tiếp trong try-with-resources.

Nếu connection đang được transaction manager gắn với thread hiện tại, **releaseConnection()** không đóng connection đó ngay. Transaction manager sẽ giải phóng connection khi transaction hoàn tất. Nếu không có transaction gắn với connection, helper sẽ đóng hoặc trả connection về pool.

Không viết như sau khi connection lấy từ DataSourceUtils:

~~~java
try (Connection connection = DataSourceUtils.getConnection(dataSource)) {
    // JDBC operation
}
~~~

Try-with-resources sẽ gọi close ngay khi block kết thúc. Điều này có thể đóng connection đang được transaction quản lý trước khi transaction hoàn tất. Hãy dùng cặp **getConnection()** và **releaseConnection()** của DataSourceUtils.

Nếu code cũ bắt buộc nhận một DataSource chuẩn và tự gọi **getConnection()**, có thể cân nhắc **TransactionAwareDataSourceProxy**. Với code mới, ưu tiên JdbcTemplate hoặc DataSourceUtils.

## 12. Phân biệt Connection, DataSource và connection pool

Ba đối tượng có vòng đời khác nhau:

| Đối tượng | Vòng đời | Ai quản lý |
|---|---|---|
| **DataSource** | Tồn tại trong application context | Spring container |
| **Connection pool** | Tồn tại cùng DataSource | Spring container và pool implementation |
| **Connection** | Mượn trong một thao tác hoặc transaction | JdbcTemplate, DataSourceUtils hoặc code JDBC |
| **PreparedStatement** | Trong một truy vấn/cập nhật | Template hoặc try-with-resources |
| **ResultSet** | Trong lúc đọc kết quả | Template hoặc try-with-resources |

Không đóng DataSource sau mỗi command. Khi ứng dụng Spring Boot tắt, application context hủy bean DataSource và pool có thể đóng các kết nối vật lý của nó. Việc đóng pool thuộc vòng đời ứng dụng, không thuộc vòng đời của một truy vấn.

Với pool như HikariCP, **Connection.close()** trên connection mượn từ pool trả connection về pool. Nếu quên gọi close/release, connection có thể bị giữ đến khi pool cạn và các command khác phải chờ.

## 13. Không giữ connection khi chờ người dùng nhập

Một shell tương tác có thể chờ người vận hành trong nhiều phút. Không mở transaction hoặc mượn connection trước khi hiển thị prompt.

Ví dụ luồng không nên dùng:

1. Command lấy connection.
2. Command mở transaction.
3. Shell hỏi người dùng tên dự án và môi trường.
4. Người dùng đọc hướng dẫn hoặc rời máy.
5. Command mới chạy SQL và đóng connection.

Trong khoảng thời gian chờ, connection và transaction bị giữ dù database không được sử dụng. Điều này có thể làm pool cạn, giữ lock hoặc khiến transaction timeout.

Luồng nên dùng:

1. Thu thập input trong shell.
2. Kiểm tra input và trình bày bản xem trước nếu cần.
3. Người dùng xác nhận.
4. Gọi application service.
5. Service mở transaction, thực hiện truy vấn và kết thúc transaction.
6. Spring giải phóng connection.

Đây cũng là lý do không đặt **@Transactional** trên toàn bộ command nếu method có thể chờ input tương tác.

## 14. Xử lý lỗi database và bảo vệ thông tin kết nối

Spring JDBC chuyển nhiều lỗi SQLException sang hệ thống **DataAccessException**. Có thể bắt các loại lỗi phù hợp với nghiệp vụ, nhưng không nên nuốt mọi exception rồi trả thông báo thành công.

Ví dụ command chỉ hiển thị thông báo an toàn:

~~~java
try {
    taskService.create(title);
    return "Đã tạo công việc.";
}
catch (DataAccessException ex) {
    logger.error("Không thể lưu công việc vào database.", ex);
    return "Không thể lưu dữ liệu. Hãy kiểm tra kết nối hoặc thử lại.";
}
~~~

Không in JDBC URL có credential, password, access token hoặc toàn bộ SQL parameter nhạy cảm ra terminal. Khi ghi log, chỉ ghi thông tin cần thiết để chẩn đoán và áp dụng chính sách bảo vệ log của hệ thống.

Với truy vấn có dữ liệu người dùng, luôn dùng parameter binding:

~~~java
jdbcTemplate.update(
        "update task set status = ? where id = ?",
        newStatus,
        taskId
);
~~~

Không nối trực tiếp input vào SQL:

~~~java
// Không dùng
String sql = "select * from task where title = '" + title + "'";
~~~

Nếu command có thể chạy lại sau lỗi mạng hoặc timeout không rõ kết quả, cần xem xét idempotency để tránh tạo dữ liệu trùng.

## 15. Tạo schema và quản lý thay đổi database

Không nên tạo bảng hoặc thay đổi schema trong mỗi lần command chạy. Schema là một phần của vòng đời ứng dụng và nên được quản lý bằng công cụ migration như Flyway hoặc Liquibase.

Trong môi trường phát triển nhỏ, có thể dùng **schema.sql** hoặc **data.sql** để khởi tạo. Với môi trường triển khai lâu dài, migration có version giúp theo dõi thay đổi, kiểm tra thứ tự áp dụng và hỗ trợ rollback theo quy trình.

Ví dụ schema PostgreSQL:

~~~sql
create table if not exists task (
    id bigint generated always as identity primary key,
    title varchar(200) not null,
    status varchar(30) not null,
    created_at timestamp with time zone not null default current_timestamp
);
~~~

Repository và service giả định bảng đã được tạo trước khi command chạy. Nếu schema không tồn tại, hãy sửa migration hoặc cấu hình khởi tạo thay vì để mỗi command tự tạo bảng.

## 16. Kiểm thử kết nối và vòng đời resource

Kiểm thử nên xác nhận cả kết quả truy vấn và việc giải phóng tài nguyên:

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| Cấu hình DataSource hợp lệ | Spring context khởi tạo được DataSource |
| Sai URL hoặc credential | Ứng dụng báo lỗi kết nối rõ ràng, không lộ password |
| Query có kết quả | Repository ánh xạ đúng các cột |
| Query không có kết quả | Trả danh sách rỗng hoặc trạng thái phù hợp |
| Insert thành công | Dữ liệu được lưu và có thể truy vấn lại |
| SQL lỗi | Exception được chuyển thành DataAccessException |
| Transaction rollback | Các thay đổi trong transaction bị rollback khi có lỗi |
| Nhiều command liên tiếp | Connection được trả về pool sau từng thao tác |
| Lỗi trong lúc đọc ResultSet | ResultSet, Statement và Connection vẫn được giải phóng |
| Ứng dụng shutdown | Pool được Spring đóng theo vòng đời bean |
| Pool cạn | Timeout và thông báo lỗi có thể chẩn đoán |
| Interactive prompt lâu | Không có connection hoặc transaction bị giữ trong lúc chờ |

Có thể dùng H2 cho kiểm thử nhanh hoặc Testcontainers để kiểm thử với loại database gần môi trường triển khai. Test tích hợp cần kiểm tra cả transaction và cách Spring quản lý connection.

Với JDBC thuần, có thể dùng mock hoặc proxy DataSource để xác nhận **close()** được gọi trong trường hợp độc lập và **DataSourceUtils.releaseConnection()** được dùng khi transaction Spring quản lý connection. Không nên chỉ kiểm tra rằng method trả về kết quả đúng; cần xác nhận đường đi giải phóng tài nguyên.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tạo được DataSource | Thiếu URL, driver hoặc credential | Kiểm tra spring.datasource.* và runtime driver |
| Không inject được JdbcTemplate | Thiếu spring-boot-starter-jdbc hoặc cấu hình DataSource lỗi | Kiểm tra dependency và auto-configuration |
| Connection pool cạn | Connection bị quên release hoặc transaction kéo dài | Dùng JdbcTemplate, try-with-resources hoặc DataSourceUtils đúng cách |
| Command chờ lâu rồi timeout | Đang giữ connection khi prompt người dùng | Chỉ gọi service sau khi thu thập input |
| Transaction không rollback cùng truy vấn | Code dùng connection không gắn với transaction | Dùng JdbcTemplate hoặc DataSourceUtils |
| ResultSet bị đóng quá sớm | Đóng ResultSet trước khi xử lý xong | Giữ việc đọc trong callback hoặc try-with-resources |
| SQL injection | Nối input trực tiếp vào SQL | Dùng placeholder và parameter binding |
| Mật khẩu database xuất hiện trong log | Log cấu hình hoặc exception không được lọc | Ẩn credential và giảm thông tin nhạy cảm trong log |
| Đóng DataSource sau mỗi command | Nhầm vòng đời pool với connection mượn | Để Spring container quản lý DataSource |
| Kết nối bị giữ sau khi command kết thúc | Quên close/release connection | Kiểm tra mọi đường return và exception |
| Dữ liệu bị ghi một phần | Transaction không bao trùm các thao tác cần nguyên tử | Đặt @Transactional ở application service |
| Tạo bảng lặp lại trong command | Trộn schema lifecycle vào command nghiệp vụ | Dùng Flyway, Liquibase hoặc script khởi tạo |

## 18. Checklist tích hợp Spring Shell với database

- [ ] Đã thêm spring-boot-starter-jdbc và JDBC driver đúng hệ quản trị.
- [ ] Đã cấu hình DataSource qua biến môi trường hoặc secret store.
- [ ] Đã kiểm tra connection pool và giới hạn kết nối phù hợp.
- [ ] DataSource được Spring container quản lý.
- [ ] Repository dùng JdbcTemplate, NamedParameterJdbcTemplate hoặc JdbcClient.
- [ ] SQL dùng parameter binding, không nối chuỗi input.
- [ ] Command chỉ nhận input và gọi application service.
- [ ] Transaction được đặt ở ranh giới nghiệp vụ.
- [ ] Không giữ connection hoặc transaction trong lúc chờ prompt.
- [ ] JDBC thuần dùng try-with-resources cho Statement và ResultSet.
- [ ] JDBC thuần trong transaction dùng DataSourceUtils.getConnection/releaseConnection.
- [ ] Không đóng DataSource hoặc connection của template bằng tay.
- [ ] Không log credential hoặc dữ liệu nhạy cảm.
- [ ] Schema được quản lý bằng migration.
- [ ] Có test cho rollback, lỗi truy vấn và giải phóng tài nguyên.

Khi command Spring Shell chỉ đóng vai trò giao diện, còn service và repository quản lý truy vấn, transaction và tài nguyên, ứng dụng có thể tái sử dụng nghiệp vụ từ các kênh khác và tránh giữ connection ngoài thời gian cần thiết. Hãy ưu tiên Spring JDBC abstraction; chỉ dùng JDBC thuần khi có lý do rõ ràng và luôn giải phóng resource theo đúng cơ chế transaction đang hoạt động.

## Tài liệu tham khảo

- [Spring Boot 4 — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html) — cấu hình DataSource, connection pool, JdbcTemplate, NamedParameterJdbcTemplate và JdbcClient.
- [Spring Boot 4 — Data Access How-to](https://docs.spring.io/spring-boot/how-to/data-access.html) — cấu hình và tùy chỉnh DataSource.
- [Spring Framework 7 — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html) — JdbcTemplate, query, update, callback và xử lý lỗi.
- [Spring Framework 7 — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html) — DataSourceUtils và connection gắn với transaction.
- [Spring Framework 7 API — DataSourceUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) — getConnection, releaseConnection và nhận diện connection transactional.
- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — khai báo command trong Spring-managed bean và đăng ký tự động với Spring Boot.
- [Spring Shell 4 API — Argument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html) — khai báo positional argument cho command.
- [Spring Shell 4 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) — khai báo option, tên dài, giá trị mặc định và trạng thái bắt buộc.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi annotation command và cách tích hợp với Spring Boot 4.
- [Java SE — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html) — hợp đồng đóng tài nguyên và try-with-resources.
