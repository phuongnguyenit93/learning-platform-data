# Hoàn tất cấu hình trước khi dùng chung đối tượng SimpleJdbcInsert

## 1. Ý nghĩa của “cấu hình xong rồi mới dùng chung”

Trong Spring JDBC, `SimpleJdbcInsert` đóng gói **cấu hình một thao tác INSERT**: bảng nào được ghi, những cột nào được gửi, cột nào sinh khóa và có dùng metadata JDBC hay không. Nó không phải đối tượng lưu dữ liệu riêng của một request. Sau khi cấu hình hoàn chỉnh, cùng một instance có thể nhận **nhiều bộ tham số khác nhau** để thêm các dòng khác nhau.

Ví dụ, một `AuditRepository` singleton được gọi đồng thời bởi nhiều request. Mọi request có thể dùng cùng một `SimpleJdbcInsert` đã được cấu hình cho bảng `audit_event`, nhưng mỗi request tự tạo `MapSqlParameterSource` mới chứa dữ liệu của mình.

~~~text
Tạo đối tượng           Khai báo toàn bộ cấu hình              Chốt cấu hình         Dùng lại
new SimpleJdbcInsert -> withTableName(...)                  -> compile()       -> execute(...)
                        usingColumns(...)                                      executeAndReturnKey(...)
                        usingGeneratedKeyColumns(...)                         executeBatch(...)
                        tùy chọn metadata / schema...
~~~

**Quy tắc:** hoàn thiện cấu hình **trước khi xuất bản tham chiếu** cho những thành phần có thể gọi đồng thời. `SimpleJdbcInsert` được Spring thiết kế để dùng lại trong nhiều luồng khi cấu hình đã ổn định. Không nên coi nó như một builder được sửa tiếp theo từng request.

## 2. Những lựa chọn cần chốt trước `compile()`

| API | Mục đích | Ví dụ/cảnh báo |
| --- | --- | --- |
| `new SimpleJdbcInsert(dataSource)` | Chọn `DataSource` | Dùng `DataSource` do ứng dụng quản lý |
| `withTableName(...)` | Chọn bảng | `audit_event` |
| `withSchemaName(...)`, `withCatalogName(...)` | Chọn schema/catalog nếu cần | Phụ thuộc hệ quản trị DB |
| `usingColumns(...)` | Giới hạn danh sách cột được ghi | `actor_name`, `event_type` |
| `usingGeneratedKeyColumns(...)` | Xác định cột database sinh khóa | `event_id` |
| `withoutTableColumnMetaDataAccess()` | Tắt xử lý metadata **cột bảng** | Phải khai báo cột cần ghi rõ ràng |
| `usingQuotedIdentifiers()` | Quote các định danh SQL | Chỉ bật khi schema/case/keyword đòi hỏi |
| `compile()` | Hoàn tất cấu hình, chuẩn bị mô tả INSERT | Gọi sau các lựa chọn ở trên |

Ví dụ cấu hình rõ ràng:

~~~java
// Mảnh mã: dataSource là DataSource đã có,
// và bảng audit_event đã tồn tại trước khi đọc metadata.
SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");

insert.compile();
~~~

Khi `event_id` do DB tự sinh, mỗi lần gọi không phải cung cấp giá trị cho cột này. Danh sách `usingColumns` giúp hợp đồng SQL không thay đổi ngoài ý muốn khi database có thêm cột với default, hoặc khi bảng có những cột bạn không định ghi.

Hãy chọn đúng tên bảng, cột và schema theo database thực tế. Tên đối tượng SQL là **cấu hình**, không phải một parameter để thay đổi tự do theo dữ liệu request.

## 3. `compile()` thực hiện việc gì?

`SimpleJdbcInsert` kế thừa `compile()` và `isCompiled()` từ `AbstractJdbcInsert`. Trong giai đoạn compile, Spring dùng cấu hình cùng metadata JDBC (khi được bật) để xác định câu INSERT, các cột và thông tin tham số tương ứng.

- **Trước compile:** có thể gọi các method cấu hình; chưa nên chia sẻ instance nếu các method đó vẫn còn được gọi.
- **Trong compile:** Spring chuẩn bị câu INSERT và có thể truy xuất thông tin bảng qua `DatabaseMetaData`; lỗi cấu hình hoặc schema không phù hợp có thể được phát hiện.
- **Sau compile thành công:** `isCompiled()` là `true`. Cấu hình đã được chốt. Spring có cơ chế từ chối sửa cấu hình sau thời điểm này.
- **Không compile thủ công:** `SimpleJdbcInsert` hỗ trợ **lazy compile** ở lần thực thi đầu tiên. Đây là hành vi hợp lệ của API. Tuy nhiên, với đối tượng singleton, compile sớm giúp lỗi cấu hình/schema xuất hiện trong lúc khởi tạo thay vì trong request đầu tiên.

~~~java
// Mảnh mã: insert đã được tạo và khai báo table/columns.
insert.compile();
System.out.println(insert.isCompiled()); // true

// Sai vòng đời: không đổi bảng sau compile.
insert.withTableName("other_table"); // Bị từ chối sau khi compiled.
~~~

Các yêu cầu sửa cấu hình sau compile có thể ném `InvalidDataAccessApiUsageException`. Việc gọi `compile()` lần nữa cũng không phải cơ chế “recompile với cấu hình mới”: tài liệu API nói những lần compile tiếp theo sẽ bị bỏ qua khi đã hoàn tất.

`compile()` ở đây **không** biên dịch mã Java và **không đảm bảo** một server-side prepared statement được giữ mãi trong database. Nó chuẩn bị thao tác INSERT ở tầng Spring. Khi thực thi, JDBC driver/database vẫn có thể lỗi vì constraint, quyền truy cập, dữ liệu, kết nối hoặc thay đổi schema. `isCompiled() == true` không phải phép thử sức khỏe DB.

## 4. Chương trình Java 17 chạy được: dùng chung sau compile

Ví dụ sau tự tạo bảng H2, cấu hình và compile đúng một lần rồi cho **hai luồng** dùng chung một `SimpleJdbcInsert`. Mỗi luồng có tham số riêng.

Sử dụng Spring JDBC **6.1.20** và H2 **2.3.232**. Đây là ứng dụng Java thuần dùng lớp của Spring JDBC; không cần tạo Spring Boot project chỉ để kiểm chứng nguyên tắc.

~~~text
simple-insert-demo/
├── pom.xml
└── src/main/java/demo/SharedInsertDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>simple-insert-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.20</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SharedInsertDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/SharedInsertDemo.java**

~~~java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcInsert;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class SharedInsertDemo {
    public static void main(String[] args) throws Exception {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:shared_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE audit_event (
                    event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    actor_name VARCHAR(50) NOT NULL,
                    event_type VARCHAR(30) NOT NULL
                )
                """);

        // 1. Cấu hình xong khi bảng đã tồn tại.
        SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
                .withTableName("audit_event")
                .usingColumns("actor_name", "event_type")
                .usingGeneratedKeyColumns("event_id");

        // 2. Chốt cấu hình TRƯỚC khi chia sẻ.
        insert.compile();
        System.out.println("Compiled: " + insert.isCompiled());

        // 3. Hai task dùng chung insert, tham số của mỗi task là riêng.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        long id1;
        long id2;
        try {
            Future<Long> first = pool.submit(
                    () -> insertEvent(insert, "alice", "CREATE"));
            Future<Long> second = pool.submit(
                    () -> insertEvent(insert, "bob", "UPDATE"));
            id1 = first.get();
            id2 = second.get();
        } finally {
            pool.shutdown();
        }

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_event",
                Integer.class);
        System.out.println("Rows: " + rows);
        System.out.println("Distinct keys: " + (id1 != id2));
    }

    private static long insertEvent(
            SimpleJdbcInsert insert, String actor, String eventType) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("actor_name", actor)
                .addValue("event_type", eventType);
        return insert.executeAndReturnKey(params).longValue();
    }
}
~~~

Từ thư mục `simple-insert-demo/`, với JDK 17+ và Maven 3.9+, chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng chương trình in ra (không kể log từ công cụ build):

~~~text
Compiled: true
Rows: 2
Distinct keys: true
~~~

**Giải thích kết quả:** H2 sinh ID cho từng bản ghi. Hai task có thể hoàn tất theo bất kỳ thứ tự nào, nên ví dụ chỉ in số dòng và sự khác nhau của hai khóa, không dựa vào giá trị ID cụ thể. Cả hai dùng **cùng tham chiếu `insert`** đã compile nhưng tạo `MapSqlParameterSource` trong method `insertEvent`; do đó dữ liệu request không bị lưu trong một field dùng chung.

`DriverManagerDataSource` thích hợp để minh họa ngắn vì tạo connection khi cần, nhưng không cung cấp connection pool. Trong production, hãy dùng `DataSource` và pool được cấu hình/giám sát theo ứng dụng. Demo này không có transaction chung giữa hai task; **dùng chung instance không tự tạo một transaction chung**.

## 5. Tích hợp vào Spring bean singleton

Trong ứng dụng Spring Boot, hãy cấu hình một lần ở tầng data access và để Spring công bố bean đã hoàn chỉnh. Ví dụ với `@Bean` và constructor injection:

~~~java
// Mảnh mã để tích hợp vào ứng dụng Spring, không phải file độc lập.
// Cần import DataSource, @Bean, @Configuration, @Repository,
// @Qualifier, SimpleJdbcInsert và MapSqlParameterSource.

@Configuration(proxyBeanMethods = false)
class InsertConfig {
    @Bean
    SimpleJdbcInsert auditEventInsert(DataSource dataSource) {
        SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
                .withTableName("audit_event")
                .usingColumns("actor_name", "event_type")
                .usingGeneratedKeyColumns("event_id");
        insert.compile();
        return insert;
    }
}

@Repository
class AuditRepository {
    private final SimpleJdbcInsert insert;

    AuditRepository(
            @Qualifier("auditEventInsert") SimpleJdbcInsert insert) {
        this.insert = insert;
    }

    long add(String actor, String eventType) {
        MapSqlParameterSource args = new MapSqlParameterSource()
                .addValue("actor_name", actor)
                .addValue("event_type", eventType);
        return insert.executeAndReturnKey(args).longValue();
    }
}
~~~

Thứ tự có chủ đích: **tạo instance → khai báo bảng/cột/khóa → compile → trả bean → inject vào repository**. Constructor injection giúp repository nhận một tham chiếu ổn định. Cũng có thể tạo và compile `SimpleJdbcInsert` trong constructor DAO nếu đó là nơi quản lý cấu hình phù hợp.

**Điều kiện bắt buộc:** bảng và các cột phải có sẵn khi bạn compile dựa trên metadata. Nếu dùng Flyway, Liquibase, `schema.sql` hay cơ chế migration khác, hãy bảo đảm việc tạo schema hoàn tất **trước** thời điểm compile. Đừng mặc nhiên giả định mọi method `@Bean` bất kỳ đều được Spring Boot tự sắp xếp sau mọi migration; hãy thiết kế dependency/lifecycle đúng với cách ứng dụng khởi tạo database. Khi compile thất bại lúc tạo bean, lỗi được phát hiện ngay lúc khởi động, dễ điều tra hơn lỗi ở request đầu tiên.

Có thể chọn lazy compile do API hỗ trợ, nhưng dù vậy vẫn phải **hoàn tất mọi lựa chọn cấu hình trước khi bean được sử dụng**. Không để hai thread cùng thay cấu hình trong lúc các thread khác execute.

## 6. Thread safety đúng nghĩa: tách dữ liệu từng lần gọi

`SimpleJdbcInsert` có khả năng tái sử dụng đồng thời **sau khi cấu hình không còn bị sửa**. Điều đó không có nghĩa mọi đối tượng được truyền cho nó cũng có thể chia sẻ tùy tiện.

| Thành phần | Có thể dùng chung? |
| --- | --- |
| `SimpleJdbcInsert` đã cấu hình/compile | Có, nếu không sửa cấu hình |
| `DataSource` thích hợp, thường là connection pool | Có, theo hợp đồng của DataSource/pool |
| `MapSqlParameterSource` đang được sửa | Không nên chia sẻ giữa các lời gọi |
| `Map` dữ liệu được các thread chỉnh đồng thời | Không an toàn nếu không đồng bộ/phân tách |
| `Connection`, `PreparedStatement` JDBC thô | Không chia sẻ tùy tiện giữa các request |
| Transaction của request | Thuộc ngữ cảnh xử lý từng request, không phải field của insert |

**Phản ví dụ:**

~~~java
// Mảnh mã SAI: mọi thread có thể thay chung sharedParams.
private final MapSqlParameterSource sharedParams =
        new MapSqlParameterSource();

long unsafeSave(String actor, String eventType) {
    sharedParams.addValue("actor_name", actor);
    sharedParams.addValue("event_type", eventType);
    return insert.executeAndReturnKey(sharedParams).longValue();
}
~~~

Trong hai lời gọi xen kẽ, giá trị `actor_name` có thể thuộc request thứ nhất, còn `event_type` thuộc request thứ hai. Chỉ cần chuyển `MapSqlParameterSource` thành biến **cục bộ** trong `save` để mỗi lần gọi có dữ liệu độc lập. Không cần khóa toàn bộ thao tác INSERT nếu vấn đề chỉ là dùng sai đối tượng tham số.

Các lời gọi `execute` và `executeAndReturnKey` không yêu cầu chia sẻ một JDBC `Connection`; `JdbcTemplate` lấy kết nối theo cơ chế `DataSource`/Spring transaction của ngữ cảnh gọi. Một đối tượng `SimpleJdbcInsert` dùng chung cũng không bảo đảm lần nào thực thi sẽ thành công: constraint, timeout, deadlock và lỗi mạng vẫn xảy ra.

## 7. Metadata và cấu hình tường minh

Theo mặc định, `SimpleJdbcInsert` tận dụng `DatabaseMetaData` để xác định thông tin cột, giảm lượng cấu hình phải viết. Điều này phụ thuộc driver cung cấp metadata đúng, schema đã tồn tại và quyền truy cập phù hợp.

Nếu muốn tránh xử lý metadata cột bảng hoặc DB/driver hỗ trợ metadata hạn chế, có thể khai báo cột tường minh:

~~~java
// Mảnh minh họa khác; không thay đổi instance đã compile.
SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .withoutTableColumnMetaDataAccess()
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");
insert.compile();
~~~

Khi tắt metadata cột, bạn chịu trách nhiệm khớp danh sách cột với DDL thực tế. Việc tắt phần metadata này **không** bảo đảm mọi tính năng JDBC khác (đặc biệt lấy generated key) không còn phụ thuộc khả năng của driver/DB. Hãy kiểm thử đường insert và generated key trên driver triển khai.

Nếu cột cần giữ chữ hoa/thường hoặc trùng keyword, `usingQuotedIdentifiers()` cần được chọn **trước compile** và theo đúng quy tắc quote của database. Không bật quote theo phỏng đoán vì tên bảng/cột tạo không quote có thể được database chuẩn hóa chữ hoa/thường.

Một thay đổi lớn về schema, bảng đích, danh sách cột hay chính sách khóa sinh có thể đòi hỏi **tạo instance mới với cấu hình mới**. Không tìm cách tái cấu hình một instance đã compile trong lúc các request vẫn đang dùng nó.

## 8. Transaction là vấn đề riêng với cấu hình dùng chung

`compile()` chỉ xử lý cấu hình thao tác INSERT. Nó không mở một transaction dài hạn hoặc giữ một connection cố định cho toàn bộ đời sống bean.

~~~java
// Mảnh mã trong Spring service; AuditRepository được inject.
@Service
class AuditService {
    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void recordTwo() {
        repository.add("alice", "CREATE");
        repository.add("alice", "UPDATE");
    }
}
~~~

Với transaction manager phù hợp, hai thao tác trong `recordTwo()` có thể tham gia cùng một transaction của **lời gọi service**. Một request khác vẫn có thể dùng cùng `SimpleJdbcInsert` mà có ngữ cảnh transaction riêng. Spring `@Transactional` thường dựa trên proxy: gọi nội bộ qua `this.recordTwo()` thường bỏ qua proxy và không tạo transaction như bạn kỳ vọng.

Nếu có xung đột khóa UNIQUE hay vi phạm ràng buộc, `DataAccessException` vẫn có thể phát sinh. Khả năng share instance an toàn không thay thế thiết kế transaction, isolation, idempotency và retry.

## 9. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Công bố instance cho request trước khi cấu hình xong | Request có thể chạy trong lúc cấu hình chưa ổn định | Cấu hình đầy đủ, compile, rồi công bố |
| Gọi `usingColumns` / `withTableName` sau compile | API từ chối sửa cấu hình | Đặt mọi tùy chọn trước compile |
| Tạo một instance mỗi lần INSERT | Lặp lại khởi tạo/metadata không cần thiết | Tái sử dụng singleton cấu hình ổn định |
| Chia sẻ mutable `MapSqlParameterSource` | Dữ liệu request có thể lẫn nhau | Mỗi lời gọi tạo tham số mới |
| Dùng field `Connection` trong repository singleton | Kết nối có state, dễ lỗi khi đồng thời | Dùng `DataSource` và Spring JDBC |
| Compile khi migration chưa chạy | Lỗi metadata/bảng/cột khi startup | Đảm bảo thứ tự migration và compile |
| Đổi bảng theo từng tenant trên một instance | Sai hợp đồng cố định, rủi ro tranh chấp | Tách cấu hình/instance theo biến thể cần thiết |
| Cho rằng compile đảm bảo DB luôn sẵn sàng | Không phát hiện lỗi runtime/constraint | Kiểm tra DB và xử lý exception riêng |
| Dựa vào ID được sinh để suy ra thứ tự hai luồng | Thứ tự scheduler/commit không cố định | So sánh dữ liệu hậu điều kiện, không suy từ lịch luồng |

### Một tình huống dễ mắc lỗi

~~~java
// PHẢN VÍ DỤ: gán cho field dùng chung khi chưa cấu hình xong.
private SimpleJdbcInsert insert;

void init(DataSource ds) {
    insert = new SimpleJdbcInsert(ds).withTableName("audit_event");
    // Có nguy cơ field được đọc bởi code khác trước khi hoàn chỉnh.
    insert.usingGeneratedKeyColumns("event_id");
}
~~~

Nếu cần tự khởi tạo một field trong lifecycle Spring, có thể dùng biến cục bộ và chỉ gán một lần sau compile:

~~~java
// Mảnh minh họa bên trong constructor/initialization method.
SimpleJdbcInsert ready = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");
ready.compile();
this.insert = ready;
~~~

Thông thường constructor injection hoặc `@Bean` factory mang lại cách công bố đã hoàn chỉnh rõ ràng hơn việc quản lý thủ công một field mutable.

## 10. Checklist kiểm chứng trước khi dùng chung

1. **Schema sẵn sàng:** bảng, cột và quyền ghi đã được migration tạo trước `compile()`.
2. **Cấu hình duy nhất:** tên bảng/schema, danh sách cột, generated key và lựa chọn metadata được quyết định trong một chỗ.
3. **Đã compile:** `compile()` thành công; khi cần có thể assert `isCompiled()` trong test khởi tạo.
4. **Không sửa sau compile:** test hoặc review xác nhận không có code đổi table/columns khi đang xử lý request.
5. **Tham số riêng:** mọi `execute`/`executeAndReturnKey` nhận `Map` hay `SqlParameterSource` độc lập, không bị thread khác thay đổi.
6. **Thực thi lặp lại:** nhiều lần insert tuần tự và đồng thời đều ghi đúng giá trị và nhận khóa hợp lệ (nếu có).
7. **Kiểm thử giao dịch:** constraint, lỗi DB và rollback phù hợp yêu cầu nghiệp vụ, không suy từ trạng thái compiled.
8. **DB/driver thực:** kiểm tra metadata/quoted identifiers/generated key trên database dự kiến triển khai, không chỉ H2.
9. **Quan sát:** nếu lỗi xảy ra sau khi deploy, phân biệt lỗi compile/configuration với lỗi execute/transaction để khắc phục đúng tầng.

## 11. Kết luận

**Configure once → compile → share → execute with fresh arguments.** `SimpleJdbcInsert` dùng chung được vì nó mang một **cấu hình INSERT ổn định**, còn dữ liệu từng lệnh nằm trong tham số riêng của mỗi lời gọi. Gọi `compile()` sau khi bảng đã sẵn sàng giúp chốt cấu hình và phát hiện lỗi sớm; việc chia sẻ vẫn cần `DataSource`, transaction và dữ liệu đầu vào được thiết kế đúng.

**Tài liệu chính thức:**

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html)
- [Spring Framework 6.1.20 — AbstractJdbcInsert API](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/jdbc/core/simple/AbstractJdbcInsert.html)
- [Spring Framework — SimpleJdbcInsert API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcInsert.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
