# Phân biệt tham số có tên phía Spring với hỗ trợ của trình điều khiển JDBC

> **Ngữ cảnh:** Spring Framework Data Access → Thủ tục và hàm (stored procedures/functions). Khi truyền `Map<String, Object>` hay `MapSqlParameterSource` vào `SimpleJdbcCall`, chúng ta đang dùng **tên ở tầng Spring**. Điều này **không chứng minh** JDBC driver có thể gọi `CallableStatement.setXxx(String parameterName, ...)` hoặc `getXxx(String parameterName)`. Hiểu đúng các tầng giúp tránh cấu hình sai khi gọi thủ tục/hàm, đặc biệt lúc đổi hệ quản trị cơ sở dữ liệu (DBMS).

## 1. Mục tiêu và vấn đề cốt lõi

Sau bài này, bạn có thể:

1. Phân biệt ba khái niệm: **placeholder có tên trong SQL phía Spring**, **khớp tên tham số IN/OUT của `SimpleJdbcCall`**, và **hỗ trợ tham số theo tên của JDBC driver/DBMS**.
2. Giải thích vì sao `SimpleJdbcCall.execute(Map)` có thể hoạt động dù bên dưới driver chỉ bind bằng vị trí 1, 2, 3.
3. Chọn đúng `SqlParameter`, `SqlOutParameter`, `SqlInOutParameter`, xử lý metadata và thứ tự khai báo.
4. Biết khi nào nên dùng `withNamedBinding()`, vì sao phương thức này khác với việc truyền `Map`, và cách kiểm chứng tính tương thích.
5. Chạy một ví dụ Java 17 + Spring JDBC + MySQL thật, kiểm tra kết quả Spring và JDBC trực tiếp.

Một câu cần nhớ:

**Tên trong API Spring phục vụ việc ánh xạ dữ liệu; vị trí hoặc cú pháp gọi thủ tục do Spring tạo và khả năng driver/DBMS hỗ trợ mới quyết định lời gọi thực tế.**

## 2. Bốn tầng thường bị gọi chung là “named parameter”

| Tầng | API/cú pháp ví dụ | Ai xử lý tên? | Có cần driver hỗ trợ JDBC binding theo tên? |
| --- | --- | --- | --- |
| Câu SQL thông thường tại Spring | `NamedParameterJdbcTemplate`: `SELECT :amount - :discount` | Spring phân tích `:amount`, `:discount`, tạo các dấu `?` và sắp giá trị theo vị trí | **Không** |
| Input cho stored procedure/function tại Spring | `SimpleJdbcCall.execute(Map.of("p_amount", 80, "p_discount", 15))` | Spring khớp key của Map với các `SqlParameter` đã khai báo hoặc metadata | **Không**, nếu đường gọi mặc định dùng vị trí |
| Cú pháp named argument trong lời gọi DBMS | `withNamedBinding()` có thể sinh đoạn `p_amount => ?` hoặc dạng riêng của DB | Spring tạo **SQL call string**, DBMS/driver phải hiểu cú pháp gọi đó | Phụ thuộc DBMS/driver; khác JDBC `setInt(String,...)` |
| Named API thực sự ở JDBC | `CallableStatement.setInt("p_amount", 80)`; `registerOutParameter("p_net", Types.INTEGER)` | Chính JDBC driver phải phân giải tên | **Có**; cần kiểm tra triển khai thực tế |

Đặc biệt, ký hiệu `:amount` là quy ước của **Spring `NamedParameterJdbcTemplate`**, không phải một dạng placeholder bắt buộc của `PreparedStatement` trong JDBC chuẩn. Tại JDBC thông thường, lời gọi vẫn được thực hiện bằng `?` và chỉ số bắt đầu từ **1**.

### 2.1. Cùng một ý nghĩa, hai đường đi

```text
SQL SELECT :amount - :discount
    └─ NamedParameterJdbcTemplate
          └─ Spring parse SQL, thay :name bằng ?
                └─ PreparedStatement: SELECT ? - ?
                      └─ setInt(1, 80); setInt(2, 15)

Stored procedure calc_net
    └─ SimpleJdbcCall.execute(MapSqlParameterSource)
          ├─ khớp "p_amount" / "p_discount" với tham số đã khai báo
          ├─ mặc định tạo {call calc_net(?, ?, ?)}
          └─ CallableStatement: vị trí 1 = 80, 2 = 15, OUT vị trí 3
                └─ JDBC driver → DBMS
```

**Điểm khác:** `NamedParameterJdbcTemplate` phù hợp SQL query/update; `SimpleJdbcCall` giải quyết thêm **chữ ký procedure/function, tham số OUT/INOUT, kết quả trả về và metadata**. Không xem một lệnh `NamedParameterJdbcTemplate.update("CALL ...")` là thay thế tổng quát cho cơ chế nhận OUT parameter của `SimpleJdbcCall`.

## 3. Spring chuyển Map thành lời gọi procedure như thế nào?

Giả sử có thủ tục MySQL:

```sql
CREATE PROCEDURE calc_net(
    IN p_amount INT,
    IN p_discount INT,
    OUT p_net INT
)
BEGIN
    SET p_net = p_amount - p_discount;
END;
```

Chữ ký đúng thứ tự trên DB là **IN amount → IN discount → OUT net**. Dữ liệu vào `80` và `15` tạo đầu ra `65`.

Khai báo `SimpleJdbcCall` rõ ràng:

```java
SimpleJdbcCall call = new SimpleJdbcCall(dataSource)
        .withProcedureName("calc_net")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_amount", Types.INTEGER),
                new SqlParameter("p_discount", Types.INTEGER),
                new SqlOutParameter("p_net", Types.INTEGER)
        );

MapSqlParameterSource in = new MapSqlParameterSource()
        .addValue("p_discount", 15) // cố ý đảo thứ tự key
        .addValue("p_amount", 80);

Map<String, Object> out = call.execute(in);
int net = ((Number) out.get("p_net")).intValue(); // 65
```

Trong ví dụ này:

- Spring tra giá trị bằng tên `p_amount` và `p_discount`; **thứ tự thêm key vào Map không ảnh hưởng**.
- Khi tắt lấy metadata bằng `withoutProcedureColumnMetaDataAccess()`, **thứ tự các `declareParameters(...)` phải khớp chữ ký thực tế của DB**. Thay `p_amount` và `p_discount` cho nhau trong phần khai báo sẽ dẫn đến binding sai theo vị trí. Với phép trừ, lỗi này dễ nhận thấy: có thể biến `80 - 15` thành `15 - 80`.
- `SqlOutParameter("p_net", Types.INTEGER)` cho Spring biết vị trí OUT và kiểu JDBC để đăng ký trước khi `execute()`. Spring đưa giá trị OUT vào Map trả về theo tên tham số.
- **Không cần** `withNamedBinding()` để truyền Map có key là tên. Với cấu hình mặc định, `SimpleJdbcCall` có thể dùng `{call calc_net(?, ?, ?)}` và thao tác theo **chỉ số** trên `CallableStatement`.

Nếu dựa vào metadata, Spring hỏi `DatabaseMetaData` từ driver để xác định chữ ký thủ tục/hàm. Thông tin metadata đáng tin giúp đỡ phải khai báo thủ công, nhưng hiệu quả phụ thuộc **DBMS, phiên bản, driver, schema, overload và kiểu tham số**. Việc driver đọc được tên từ metadata cũng không đồng nghĩa nó hỗ trợ mọi overload `CallableStatement` nhận tên.

### 3.1. Khai báo IN, OUT và INOUT

| Khai báo Spring | Ý nghĩa | Tác động khi thực thi |
| --- | --- | --- |
| `new SqlParameter("p_in", Types.INTEGER)` | Giá trị chỉ đi vào thủ tục | Lấy từ Map/SqlParameterSource và bind vào vị trí tương ứng |
| `new SqlOutParameter("p_out", Types.INTEGER)` | Giá trị từ thủ tục trả về | Đăng ký OUT, lấy kết quả và đưa vào output Map |
| `new SqlInOutParameter("p_both", Types.INTEGER)` | Cùng tham số vừa IN vừa OUT | Bind giá trị đầu vào, đăng ký và lấy giá trị đầu ra |
| `new SqlReturnResultSet("rows", rowMapper)` | Kết quả ResultSet trực tiếp | Map danh sách hàng được trả về; không luôn tương đương một tham số OUT cursor |

Đối với hàm trả một giá trị, dùng `withFunctionName("...")` và `executeFunction(ReturnType.class, args)` khi driver/DBMS hỗ trợ kiểu gọi phù hợp. Cú pháp escape chuẩn thường có dạng `{? = call function_name(?)}`: dấu `?` đầu tiên dành cho **return value**, không phải IN argument đầu tiên. Không tự áp cùng chỉ số của thủ tục cho hàm.

Lưu ý `SqlOutParameter` thuần tuý **không** phải nơi cung cấp giá trị IN. Với tham số vừa nhập vừa xuất, dùng `SqlInOutParameter` đúng vai trò. Khi gặp `NULL`, kiểu JDBC khai báo rõ ràng giúp driver xử lý nhất quán hơn.

## 4. `withNamedBinding()`: tên trong **SQL call string** và giới hạn tương thích

Trong `SimpleJdbcCall`, hai thao tác sau có ý nghĩa khác nhau:

```java
// A. API Spring nhận Map có tên, dùng cách binding mặc định theo vị trí:
new SimpleJdbcCall(dataSource).withProcedureName("calc_net");

// B. Thay đổi cách Spring tạo cú pháp tham số trong lời gọi:
new SimpleJdbcCall(dataSource).withProcedureName("calc_net")
        .withNamedBinding();
```

Theo mã nguồn Spring JDBC, `AbstractJdbcCall` mặc định `namedBinding=false`. Khi bật `withNamedBinding()`, Spring nhờ `CallMetaDataProvider` tạo **mảnh cú pháp tham số có tên trong call string**. Dạng thường gặp là `parameterName => ?` (với provider chung) hoặc `parameterName = ?` (với provider dành riêng cho một số DBMS). Chẳng hạn, **chỉ để minh hoạ cơ chế**, một chuỗi có thể trông như:

```sql
{call calc_net(p_amount => ?, p_discount => ?, p_net => ?)}
```

**Không giả định** cú pháp minh hoạ trên chạy được ở mọi DB, đặc biệt **không bật nó trong ví dụ MySQL** ở mục 5. DBMS phải hiểu cú pháp named argument tương ứng và JDBC driver phải biến đổi/chuyển tiếp lời gọi đúng cách. Việc Spring chèn tên vào SQL call string cũng **không đồng nghĩa** Spring gọi `CallableStatement.setInt("p_amount", 80)` bên dưới; ở đường thực thi thông thường, `CallableStatementCreatorFactory` vẫn có thể gán placeholder bằng **chỉ số**.

Có ba quyết định độc lập:

1. **Bạn muốn gọi Spring bằng Map có tên?** Dùng `SimpleJdbcCall.execute(Map)` hoặc `execute(SqlParameterSource)`; không cần bật named binding.
2. **Bạn muốn Spring xác định thứ tự/tên IN/OUT từ DB?** Dùng metadata nếu tin cậy; nếu không, tắt metadata và khai báo thủ công đủ thứ tự/kiểu.
3. **Bạn muốn tên xuất hiện trong cú pháp lời gọi thực gửi DB?** Chỉ cân nhắc `withNamedBinding()` sau khi kiểm chứng DBMS + JDBC driver cụ thể, nhất là với procedure overload, tham số mặc định hoặc cú pháp vendor-specific.

### 4.1. Named binding trực tiếp của `CallableStatement` là chuyện riêng

JDBC định nghĩa hai nhóm thao tác (ví dụ):

```java
// Theo vị trí: cách thông dụng, chỉ số bắt đầu từ 1.
cs.setInt(1, 80);
cs.setInt(2, 15);
cs.registerOutParameter(3, Types.INTEGER);
cs.execute();
int net = cs.getInt(3);

// Theo tên: chỉ sử dụng khi driver/DBMS cụ thể hỗ trợ.
cs.setInt("p_amount", 80);
cs.setInt("p_discount", 15);
cs.registerOutParameter("p_net", Types.INTEGER);
cs.execute();
int netByName = cs.getInt("p_net");
```

Hai đoạn là **hai phương án thay thế**, không thực hiện nối tiếp trên cùng một đối tượng đã execute. Phương án thứ hai cần được xác nhận qua tài liệu driver và phép thử tích hợp thực tế; có thể gặp `SQLFeatureNotSupportedException`, `SQLException` hoặc hành vi không đúng với chữ ký DB nếu tên bị chuẩn hoá/khác kiểu. Đừng lấy việc `SimpleJdbcCall.execute(Map)` thành công làm bằng chứng rằng nhóm phương thức JDBC theo tên này đã hoạt động.

**Bẫy metadata:** `ParameterMetaData` của `PreparedStatement` mô tả **số lượng, loại, độ chính xác, mode IN/OUT, ...**, không có phương thức chuẩn `getParameterName()`. Đối với tên tham số thủ tục, Spring dựa vào các API `DatabaseMetaData` dành cho procedure/function cùng provider chuyên biệt; kết quả nhận được vẫn phụ thuộc driver.

## 5. Ví dụ đầy đủ, chạy được: Spring JDBC và MySQL 8.4

Ví dụ này cố tình dùng **cả hai phương án** trên cùng procedure:

- Spring `SimpleJdbcCall.execute(MapSqlParameterSource)`: key đầu vào được đưa vào ngược thứ tự để chứng minh cơ chế khớp tên của Spring.
- JDBC `CallableStatement`: gán ba tham số theo chỉ số, đăng ký OUT và đọc kết quả.

Kết quả hai lối gọi phải là `65` dù `SimpleJdbcCall` **không** dùng `withNamedBinding()`. Cần JDK 17+, Maven 3.9+, Docker và quyền chạy container. Chạy trong một thư mục thực hành riêng với cấu trúc:

```text
named-call-demo/
├── pom.xml
└── src/main/java/CallDemo.java
```

### 5.1. Khởi động MySQL thử nghiệm

Dùng **một dòng** cho lệnh Docker (chạy được trong PowerShell hoặc Bash):

```bash
docker run --rm -d --name mysql-call-demo -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=proc_lab -e MYSQL_USER=lab -e MYSQL_PASSWORD=labpass -p 33079:3306 mysql:8.4
```

Chờ MySQL khởi tạo DB và người dùng `lab`; kiểm tra đến khi báo `mysqld is alive`:

```bash
docker exec mysql-call-demo mysqladmin ping -h127.0.0.1 -u lab -plabpass
```

Thông tin đăng nhập này **chỉ dành cho DB thực hành cô lập**. Không mở cổng, bỏ TLS hoặc dùng mật khẩu mẫu này với DB thật.

### 5.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>named-call-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.mysql</groupId>
            <artifactId>mysql-connector-j</artifactId>
            <version>9.4.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
                <configuration>
                    <mainClass>CallDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là dự án Maven độc lập để tái hiện hành vi, không cần Spring Boot. Khi áp dụng trong ứng dụng Boot, nên lấy phiên bản Spring/driver từ dependency management của ứng dụng.

### 5.3. Tệp `src/main/java/CallDemo.java`

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.Statement;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class CallDemo {

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("com.mysql.cj.jdbc.Driver");
        ds.setUrl(System.getenv().getOrDefault(
                "DB_URL",
                "jdbc:mysql://127.0.0.1:33079/proc_lab"
                + "?sslMode=DISABLED&allowPublicKeyRetrieval=true"));
        ds.setUsername(System.getenv().getOrDefault("DB_USER", "lab"));
        ds.setPassword(System.getenv().getOrDefault("DB_PASSWORD", "labpass"));

        // Chuẩn bị procedure tại DB thực hành, chưa dùng dữ liệu production.
        try (Connection con = ds.getConnection();
             Statement statement = con.createStatement()) {
            statement.execute("DROP PROCEDURE IF EXISTS calc_net");
            // JDBC gửi CREATE PROCEDURE như một câu SQL: không dùng DELIMITER
            // vì DELIMITER chỉ là lệnh của MySQL CLI.
            statement.execute("""
                CREATE PROCEDURE calc_net(
                    IN p_amount INT,
                    IN p_discount INT,
                    OUT p_net INT
                )
                BEGIN
                    SET p_net = p_amount - p_discount;
                END
                """);

            DatabaseMetaData md = con.getMetaData();
            System.out.println("Driver: " + md.getDriverName());
        }

        // A. SQL query có :name: Spring chuyển sang dấu ? trước khi gửi JDBC.
        NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(ds);
        MapSqlParameterSource sqlArgs = new MapSqlParameterSource()
                .addValue("discount", 15)
                .addValue("amount", 80);
        Integer queryResult = named.queryForObject(
                "SELECT :amount - :discount", sqlArgs, Integer.class);
        System.out.println("Named SQL result: " + queryResult);

        // B. Stored procedure: tên key trong Map được Spring khớp với
        // SqlParameter; khai báo theo THỨ TỰ procedure trên DB.
        SimpleJdbcCall springCall = new SimpleJdbcCall(ds)
                .withProcedureName("calc_net")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_amount", Types.INTEGER),
                        new SqlParameter("p_discount", Types.INTEGER),
                        new SqlOutParameter("p_net", Types.INTEGER));

        MapSqlParameterSource procedureArgs = new MapSqlParameterSource()
                .addValue("p_discount", 15)
                .addValue("p_amount", 80); // cố ý đảo thứ tự các key
        Map<String, Object> out = springCall.execute(procedureArgs);
        Number springNet = (Number) out.get("p_net");
        System.out.println("Spring procedure result: " + springNet.intValue());

        // C. JDBC thuần: ràng buộc theo ordinal index, không theo tên.
        try (Connection con = ds.getConnection();
             CallableStatement cs =
                     con.prepareCall("{call calc_net(?, ?, ?)}")) {
            cs.setInt(1, 80);
            cs.setInt(2, 15);
            cs.registerOutParameter(3, Types.INTEGER);
            cs.execute();
            int jdbcNet = cs.getInt(3);
            if (cs.wasNull()) {
                throw new IllegalStateException("Unexpected SQL NULL");
            }
            System.out.println("JDBC indexed result: " + jdbcNet);

            if (queryResult == null || queryResult != 65
                    || springNet.intValue() != 65 || jdbcNet != 65) {
                throw new IllegalStateException("Results differ");
            }
        }
    }
}
```

Cách viết `CREATE PROCEDURE` trong `Statement.execute(...)` là một câu SQL truyền qua JDBC, nên **không thêm** `DELIMITER //` của tiện ích MySQL CLI. Tên thủ tục `calc_net`, kiểu và thứ tự các tham số luôn khớp giữa SQL và khai báo Spring.

### 5.4. Chạy và đọc output

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Khi MySQL chạy thành công, ba dòng **do chương trình in ra** có nội dung chính xác như sau:

```text
Named SQL result: 65
Spring procedure result: 65
JDBC indexed result: 65
```

Ngoài ra còn có dòng `Driver: ...` hiển thị tên driver thực tế; giá trị tên có thể khác theo phiên bản. Maven có thể có log riêng. Điều cần quan sát: **tên key `p_discount` được thêm trước `p_amount`, nhưng kết quả Spring vẫn là 65**; tại JDBC thuần, kết quả có được nhờ `setInt(1,...)`, `setInt(2,...)` và `registerOutParameter(3,...)`.

Dừng và tự xoá container khi hoàn thành:

```bash
docker stop mysql-call-demo
```

Không lấy ví dụ này làm cam kết rằng JDBC driver sẽ hỗ trợ `setInt(String,...)`; chương trình chỉ yêu cầu các API **theo vị trí** ở tầng JDBC.

## 6. Metadata và tính di động khi gọi thủ tục/hàm

### 6.1. Bật metadata khi phù hợp

```java
SimpleJdbcCall call = new SimpleJdbcCall(dataSource)
        .withProcedureName("calc_net");
Map<String, Object> result = call.execute(
        Map.of("p_amount", 80, "p_discount", 15));
```

Ở dạng trên, `SimpleJdbcCall` có thể suy ra IN/OUT/type và thứ tự từ metadata do driver cung cấp. Cách này giúp giảm mã cấu hình khi hệ quản trị và driver công bố **metadata đáng tin**. Nhưng một số trường hợp có thể phức tạp: cùng tên thủ tục ở nhiều schema, tên có chữ hoa/chữ thường/quoted identifiers, overload, tham số không hỗ trợ type mapping, procedure trả cursor, hoặc thông tin hàm/procedure không nhất quán giữa driver và DB.

Vì vậy, **đo đúng với hệ thống đang triển khai**: kiểm tra DBMS/version, driver/version, schema/procedure thực tế và loại IN/OUT trước khi mặc định Spring luôn suy ra chính xác.

### 6.2. Tắt metadata khi chữ ký cần kiểm soát

```java
new SimpleJdbcCall(dataSource)
        .withProcedureName("calc_net")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_amount", Types.INTEGER),
                new SqlParameter("p_discount", Types.INTEGER),
                new SqlOutParameter("p_net", Types.INTEGER)
        );
```

Đây là cách rõ ràng khi metadata thiếu/sai, routine có overload, muốn kiểm soát `Types`, hoặc dùng driver chưa được Spring hỗ trợ đầy đủ. **Hệ quả** là bạn sở hữu trách nhiệm cập nhật chữ ký theo DB; đổi thứ tự hoặc kiểu SQL trong procedure phải cập nhật khai báo tương ứng.

`useInParameterNames(...)` có thể giới hạn các tên IN được cân nhắc khi xử lý metadata, chẳng hạn nếu cần chọn chữ ký; phương thức này **không tự sửa** một chữ ký sai, không thay thế khai báo OUT và không cấp thêm khả năng named binding cho driver.

### 6.3. Chú ý tên OUT và giá trị NULL

Tên key trả về trong `Map` có thể theo metadata và quy tắc chữ hoa/thường của DBMS. Có thể cấu hình `JdbcTemplate.setResultsMapCaseInsensitive(true)` rồi truyền `JdbcTemplate` ấy vào `SimpleJdbcCall` nếu ứng dụng cần tra cứu tên OUT không phân biệt chữ hoa/thường.

```java
JdbcTemplate jdbc = new JdbcTemplate(dataSource);
jdbc.setResultsMapCaseInsensitive(true);
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withProcedureName("calc_net");
```

Đây là ví dụ cấu hình, chưa thay thế cho phần khai báo metadata/type khi driver không trả đầy đủ. Kiểu `OUT` phải phù hợp giá trị trả về: dùng `Number` rồi chuyển kiểu khi phù hợp, và kiểm tra `NULL` thay vì ép kiểu/auto-unboxing một cách mù quáng. Với input `NULL`, có thể dùng `addValue("p_amount", null, Types.INTEGER)` để cung cấp kiểu JDBC rõ ràng.

## 7. Kiểm chứng từng khả năng, không suy ra từ một lần chạy thành công

| Điều muốn biết | Bài kiểm chứng | Kết luận được phép |
| --- | --- | --- |
| Spring hiểu `:name` trong SELECT | Dùng `NamedParameterJdbcTemplate` với hai key đảo thứ tự | Chứng minh Spring ghép đúng tên → vị trí cho SQL thông thường |
| Spring hiểu key trong Map procedure | `SimpleJdbcCall.execute(MapSqlParameterSource)` như demo | Chứng minh khớp tên tại API Spring và lời gọi positional chuẩn chạy đúng |
| Metadata của driver đủ dùng | Bỏ `withoutProcedureColumnMetaDataAccess()`, đối chiếu chữ ký/OUT với DB | Chứng minh metadata **cho đúng routine** đang đủ, không chứng minh mọi routine đều tương thích |
| JDBC driver hỗ trợ named API thật | Tạo `CallableStatement`, thử `setInt("p_amount", ...)`, `registerOutParameter("p_net", ...)`, `getInt("p_net")` | Chỉ nếu chạy đúng trên driver/version đích mới xác nhận được named API |
| DB hỗ trợ named arguments trong call string | Thử `withNamedBinding()` trên môi trường riêng, kiểm tra SQL tạo ra và kết quả | Xác nhận cú pháp call tương thích cho chữ ký này, không phải mọi DB |
| Khai báo đúng thứ tự | Cố ý đảo hai khai báo IN **trong bài thử nghiệm** và so kết quả 65 với -65 | Làm rõ vì sao Map order và declared parameter order là hai khái niệm khác nhau |

Trong báo cáo kiểm thử, ghi `DatabaseMetaData.getDatabaseProductName()`, `getDatabaseProductVersion()`, `getDriverName()`, `getDriverVersion()`, phiên bản Spring JDBC, chữ ký SQL và kết quả OUT. Với phương thức named API của driver, bắt `SQLException`/`SQLFeatureNotSupportedException` và xem SQLState/mã lỗi của driver. Lỗi có thể xuất phát từ **không hỗ trợ tên**, **tên không khớp**, **khác kiểu**, **routine không tìm thấy** hoặc **cú pháp SQL sai** — không quy tất cả thành “Spring không nhận tên”.

## 8. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `MapSqlParameterSource` có key đúng nhưng kết quả sai | Khai báo `SqlParameter` sai thứ tự khi tắt metadata | Đối chiếu từng ordinal index IN/OUT với chữ ký DB; thêm test dùng phép toán không giao hoán |
| `Required input parameter ... is missing` | Key Spring không khớp tham số IN đã khai báo/metadata, hoặc sai chữ hoa-thường/tên | So khớp key, tên ở DB và `declareParameters`; log tên **không log giá trị nhạy cảm** |
| `CallableStatement.setXxx("name")` ném ngoại lệ | Driver không hỗ trợ named access hoặc tên không đúng | Kiểm tra tài liệu driver/version; ưu tiên phương án positional khi phù hợp |
| Gọi `withNamedBinding()` tạo lỗi SQL syntax | DBMS không nhận cú pháp named arguments của provider | Bỏ `withNamedBinding()`, dùng Map tại Spring + vị trí JDBC |
| OUT không có trong Map | Thiếu `SqlOutParameter`, thứ tự OUT sai, metadata bị thiếu hoặc tên OUT khác case | Khai báo OUT đúng `Types`, vị trí và xem key thực trả về |
| Hàm trả giá trị sai vị trí | Quên vị trí return của `{? = call ...}` | Dùng `withFunctionName` và `executeFunction`; kiểm tra chữ ký và driver |
| Driver metadata báo sai khi có overload | DBMS trả nhiều chữ ký hoặc không đủ tên/kiểu | Xác định schema/chữ ký cụ thể, khai báo tham số thủ công và test tích hợp |
| `null` bị suy sai kiểu | Driver không suy ra kiểu JDBC từ null | Chỉ định `Types` trong `MapSqlParameterSource`/`SqlParameter` |
| Procedure đổi chữ ký nhưng mã Spring không đổi | Thứ tự/tham số mới khác khai báo hiện tại | Quản lý migration và test procedure cùng mã client |

**Lỗi bảo mật cần tránh:** tên procedure, tên schema và tên cột là **định danh SQL**, không được thay bằng placeholder giá trị `?` hay `:name`. Nếu tên routine đến từ input người dùng, phải ánh xạ qua danh sách cho phép; đừng nối chuỗi trực tiếp. Tên parameter cũng không phải cơ chế tự kiểm tra quyền gọi procedure. DB user vẫn cần quyền `EXECUTE` và transaction cần được điều phối phù hợp.

**Lỗi hiệu năng cần tránh:** tạo `SimpleJdbcCall` rồi introspect metadata cho từng request. Cấu hình một lần như một DAO/service reusable, để Spring compile metadata/call string khi cần. Khi so benchmark có và không metadata, đo separately chi phí initialization với chi phí mỗi lần gọi; đừng trộn lẫn hai đại lượng.

## 9. Quy tắc lựa chọn trong dự án Spring

- Nếu chỉ truy vấn/cập nhật SQL thường và muốn `:name`, dùng `NamedParameterJdbcTemplate` hoặc `JdbcClient`. Đây là tiện ích ánh xạ tên của Spring, không yêu cầu named API của driver.
- Nếu gọi stored procedure/function với IN/OUT/return value, dùng `SimpleJdbcCall` với `Map`/`SqlParameterSource`. Mặc định Spring có thể bind JDBC theo vị trí; bạn **không cần** gọi `withNamedBinding()` chỉ vì đầu vào là Map.
- Nếu metadata driver chính xác và chữ ký đơn giản, tận dụng metadata. Nếu metadata không đáng tin hoặc routine phức tạp, dùng `withoutProcedureColumnMetaDataAccess()` + khai báo đủ tham số **đúng thứ tự**.
- Nếu muốn `CallableStatement` truy cập tham số bằng tên hoặc bật `withNamedBinding()`, phải kiểm chứng riêng trên **đúng DBMS + driver + version + chữ ký procedure/function**.
- Khi đổi DB hoặc driver, giữ test tích hợp kiểm tra cả **giá trị IN, OUT, INOUT, NULL, overload, lỗi và thứ tự**; một test “Spring khởi động thành công” chưa đủ.

### Câu hỏi tự kiểm tra

1. Vì sao `SimpleJdbcCall.execute(Map.of("b", ..., "a", ...))` có thể đúng dù `CallableStatement.setInt("a", ...)` không được driver hỗ trợ?
2. Khi tắt metadata và khai báo `SqlParameter("p_discount")` trước `SqlParameter("p_amount")`, chuyện gì xảy ra nếu procedure thật nhận amount trước discount?
3. `withNamedBinding()` thay đổi **cú pháp SQL** hay thay đổi thứ tự key trong Map? Có nên bật mặc định trên mọi DB?
4. Bạn cần những bằng chứng nào để tuyên bố driver hỗ trợ `registerOutParameter(String,...)`?

## Tài liệu tham khảo

- Spring Framework — *Using the JDBC Core Classes* (`NamedParameterJdbcTemplate`, `JdbcClient`): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — *Simplifying JDBC Operations with the SimpleJdbc Classes* (stored procedures, metadata, khai báo IN/OUT, hàm): https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework — `SimpleJdbcCall` Javadoc (`execute`, `withNamedBinding`, `withoutProcedureColumnMetaDataAccess`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html
- Spring Framework — `AbstractJdbcCall` Javadoc (mặc định `namedBinding=false`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/AbstractJdbcCall.html
- OpenJDK/Oracle Java 21 — `CallableStatement` (JDBC binding theo vị trí/tên, `SQLFeatureNotSupportedException`): https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/CallableStatement.html
- OpenJDK/Oracle Java 21 — `ParameterMetaData` (type/mode/count, không có `getParameterName()`): https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ParameterMetaData.html
- Spring JDBC source — `CallMetaDataContext.createParameterBinding()`, `GenericCallMetaDataProvider.namedParameterBindingToUse()`, `CallableStatementCreatorFactory`: https://github.com/spring-projects/spring-framework/tree/main/spring-jdbc/src/main/java/org/springframework/jdbc/core
