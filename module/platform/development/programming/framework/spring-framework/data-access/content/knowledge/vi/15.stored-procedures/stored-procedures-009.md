# Nhận diện lớp StoredProcedure khi làm việc với mã hiện có

## 1. Mục tiêu: đọc hiểu một đoạn mã Spring JDBC kiểu cũ

Khi bảo trì ứng dụng Spring, bạn có thể gặp lớp Java kế thừa `StoredProcedure`, một bean `GenericStoredProcedure`, hoặc một lớp repository gọi `execute(...)` và nhận về `Map`. Nếu chỉ nhìn tên, dễ nhầm chúng với lệnh SQL, với `SimpleJdbcCall` hoặc với JPA. Bài này hướng dẫn **nhận diện đúng `org.springframework.jdbc.object.StoredProcedure` trong mã đã tồn tại, lần theo nơi cấu hình, tham số, lời gọi và kết quả**, để hiểu hành vi trước khi debug hay cân nhắc chỉnh sửa.

Đối tượng cần nhận diện là lớp:

```java
org.springframework.jdbc.object.StoredProcedure
```

Đây là **lớp trừu tượng** của Spring JDBC, thuộc kiểu thiết kế *RDBMS operation object*: một đối tượng Java đại diện cho lời gọi stored procedure hoặc stored function của cơ sở dữ liệu. Lớp đó **không phải bản thân thủ tục SQL**, không tự định nghĩa SQL routine trong database. Nó dùng hạ tầng Spring JDBC để tạo và thực thi JDBC `CallableStatement`.

Quan hệ kế thừa:

```text
java.lang.Object
    └── org.springframework.jdbc.object.RdbmsOperation
            └── org.springframework.jdbc.object.SqlCall
                    └── org.springframework.jdbc.object.StoredProcedure
                            └── Lớp con do dự án định nghĩa
```

Các ý cần nắm trước khi xem ví dụ:

- `RdbmsOperation` chịu trách nhiệm cấu hình data source, khai báo tham số và trạng thái `compile`.
- `SqlCall` mô tả lời gọi procedure/function, có tùy chọn `setFunction(true)` khi gọi hàm.
- `StoredProcedure` cung cấp các `execute(...)` nhận tham số, trả về các kết quả OUT dưới dạng `Map<String, Object>`.
- **Lớp con** thường đặt tên theo nghiệp vụ, ví dụ `ReadCustomerProcedure`, tự tạo phương thức kiểu mạnh như `findCustomerName(long id)` để che phần `Map`.
- `GenericStoredProcedure` là một triển khai cụ thể khác để dùng mà không phải tự viết lớp con với phương thức kiểu mạnh.

Đây là một API vẫn có thể gặp trong dự án Spring JDBC; nhận diện được mã hiện có **không đồng nghĩa** cần tự động thay nó bằng API mới. Các hành vi về parameter, transaction, driver và kiểu dữ liệu phải được xác minh trước khi thay đổi.

## 2. Dấu hiệu nhận diện nhanh trong mã nguồn

Một lớp điển hình trông như sau:

```java
// File: ReadCustomerNameProcedure.java
import java.sql.Types;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.object.StoredProcedure;

public final class ReadCustomerNameProcedure extends StoredProcedure {

    public ReadCustomerNameProcedure(DataSource dataSource) {
        // "read_customer_name" là tên routine trong database.
        super(dataSource, "read_customer_name");

        // Chữ IN/OUT và thứ tự khai báo phản ánh chữ ký routine.
        declareParameter(new SqlParameter("in_customer_id", Types.BIGINT));
        declareParameter(new SqlOutParameter("out_name", Types.VARCHAR));

        // Hoàn tất cấu hình để tái sử dụng nhiều lần.
        compile();
    }

    public String findName(long customerId) {
        Map<String, Object> result =
                super.execute(Map.of("in_customer_id", customerId));

        Object value = result.get("out_name");
        return value == null ? null : (String) value;
    }
}
```

Đây là lớp Java **có thể biên dịch khi đã có Spring JDBC và các phụ thuộc của nó**, nhưng **không tự chạy độc lập**: cần database có procedure tên `read_customer_name` với chữ ký IN/OUT tương ứng và `DataSource` được cấu hình đúng. Tên procedure và tên tham số trong ví dụ là giả định để minh họa cách đọc mã; chúng không phải một procedure mặc định của Spring.

Đọc đoạn trên theo từng dấu hiệu:

1. `extends StoredProcedure` xác nhận đây là lớp adapter cho routine SQL, không phải repository thông thường chỉ dùng `JdbcTemplate.update`.
2. `super(dataSource, "read_customer_name")` cung cấp **DataSource và tên routine**. Không suy luận đây là tên bảng hay một câu `SELECT`.
3. `declareParameter(new SqlParameter(...))` khai báo tham số IN kiểu SQL tương ứng với `Types.BIGINT`.
4. `declareParameter(new SqlOutParameter(...))` khai báo OUT; key dự kiến trong kết quả là `"out_name"`, chưa biết giá trị thực cho đến khi thực thi.
5. `compile()` đánh dấu cấu hình lời gọi đã hoàn thành và chuẩn bị các thành phần nội bộ; **không phải lệnh chạy procedure và không phải biên dịch file Java**.
6. `findName(...)` là phương thức nghiệp vụ do người viết lớp con đặt tên; **`super.execute(...)` mới là lời gọi xuống Spring JDBC**.
7. `Map` đầu vào ánh xạ tên tham số sang giá trị; `Map` đầu ra ánh xạ tên tham số OUT sang giá trị trả về.

Nếu bạn chỉ nhìn một phương thức DAO gọi:

```java
String name = readCustomerNameProcedure.findName(42L);
```

hãy truy ngược **kiểu của `readCustomerNameProcedure` → constructor → `super(...)`/`setSql(...)` → các `declareParameter(...)` → `super.execute(...)`**. Đó là chuỗi thường quyết định đúng procedure nào chạy, nhận những tham số nào và trả gì.

## 3. Một quy trình đọc mã cũ theo đúng thứ tự

Khi bắt gặp `StoredProcedure` trong project, dùng các câu hỏi dưới đây để không suy đoán từ tên biến:

| Bước | Cần tìm | Điều cần kết luận |
| --- | --- | --- |
| 1 | `import org.springframework.jdbc.object.StoredProcedure` hoặc `extends StoredProcedure` | Đúng abstraction của Spring JDBC, không phải class trùng tên ở package khác. |
| 2 | `super(dataSource, routineName)`, `setSql(...)`, `setDataSource(...)`, `setJdbcTemplate(...)` | Routine nào được gọi? Dùng connection pool/DataSource nào? |
| 3 | `setFunction(true)`, `setSqlReadyForUse(true)`, `setSql(...)` | Đây là function hay procedure? Spring tự dựng cú pháp gọi hay dùng SQL call string sẵn có? |
| 4 | Các `declareParameter(...)` | Thứ tự, tên, `java.sql.Types`, IN/OUT/INOUT và ánh xạ dữ liệu có khớp routine? |
| 5 | `compile()`, `afterPropertiesSet()`, `isCompiled()` | Cấu hình hoàn tất ở đâu, trước lần gọi đầu tiên hay khi Spring khởi tạo bean? |
| 6 | `execute(Object...)`, `execute(Map)`, `execute(ParameterMapper)` | Truyền giá trị theo thứ tự hay theo tên? Có xử lý vendor-specific? |
| 7 | `result.get("...")` hoặc mã convert map sang DTO | OUT nào thực sự được sử dụng, có thể `null` không, kiểu dữ liệu là gì? |
| 8 | Nơi gọi repository và transaction | Lời gọi được kích hoạt bởi nghiệp vụ nào? Có giao dịch và tác dụng phụ nào? |

Đừng dừng ở `execute(...)`: ý nghĩa nghiệp vụ thường nằm trong tên procedure ở database cùng **chữ ký thực tế** và phần convert giá trị OUT. Nếu có thể truy cập schema, hãy đối chiếu định nghĩa routine trong database đang được triển khai. Không giả định mọi môi trường dùng cùng schema hoặc version của routine.

### Ví dụ lần dấu ngược từ nơi gọi

```text
OrderService.confirmOrder(orderId)
    ↓
OrderRepository.confirm(orderId)
    ↓
ConfirmOrderProcedure.executeConfirmation(orderId)
    ↓
super.execute(Map.of("in_order_id", orderId))
    ↓
JdbcTemplate.call(...) / JDBC CallableStatement
    ↓
database routine: confirm_order
    ↓
Map output ["out_status", "out_message"]
    ↓
Service quyết định ghi log/trả response/ném lỗi
```

Dòng trên là **sơ đồ kiến trúc minh họa**, không mô tả một triển khai có sẵn của Spring. Cần đọc cả các lớp ngoài procedure wrapper: transaction và business validation có thể nằm ở service, không nằm ở lớp con `StoredProcedure`.

## 4. Ý nghĩa của constructor và thuộc tính SQL

Hai kiểu khởi tạo thường gặp:

```java
// Kiểu A — constructor của lớp con gọi super:
super(dataSource, "calculate_discount");
```

```java
// Kiểu B — JavaBean-style trong constructor của lớp con:
setDataSource(dataSource);
setSql("calculate_discount");
```

Cả hai đều xác định routine trong database. `StoredProcedure` có constructor bảo vệ (protected); vì vậy thông thường phải kế thừa, hoặc dùng lớp cụ thể `GenericStoredProcedure`.

Đôi khi lớp dùng:

```java
setFunction(true);
```

Lúc đó lời gọi nhắm tới **stored function có giá trị trả về** thay vì procedure theo quy ước thông thường. Dấu hiệu này đặc biệt quan trọng vì function return thường chiếm một vị trí OUT trong JDBC call string; **không được tự xóa OUT parameter vì nhầm nó là tham số input**.

Trường hợp khác:

```java
setSqlReadyForUse(true);
setSql("{call legacy_proc(?, ?)}");
```

Đây là cấu hình có chủ ý để cung cấp sẵn **JDBC call string**; không mặc nhiên diễn giải `sql` là tên routine đơn giản khi có `setSqlReadyForUse(true)`. Cách viết `{call ...}` và `{? = call ...}` theo JDBC escape syntax có ý nghĩa riêng, phụ thuộc driver và thứ tự tham số. Đọc cả các `declareParameter` để biết placeholder nào được bind/register.

**Quy tắc:** Không khẳng định mã đang gọi procedure hay function chỉ dựa vào tên class `XxxProcedure`; hãy kiểm tra `setFunction(...)`, call string và định nghĩa routine.

## 5. Các loại tham số là chìa khóa đọc đúng hành vi

Các khai báo thường xuất hiện trong constructor:

```java
declareParameter(new SqlParameter("in_customer_id", Types.BIGINT));
declareParameter(new SqlOutParameter("out_name", Types.VARCHAR));
declareParameter(new SqlInOutParameter("io_total", Types.DECIMAL));
```

Ba dòng là các **loại tham số minh họa**, không phải chữ ký của cùng một procedure trong ví dụ ở phần 2.

| Loại | Ý nghĩa | Dữ liệu đi đâu? |
| --- | --- | --- |
| `SqlParameter(name, sqlType)` | IN | Nhận giá trị Java khi gọi và đưa vào `CallableStatement`. |
| `SqlOutParameter(name, sqlType)` | OUT | Đăng ký giá trị trả từ DB và lấy theo key `name` trong map kết quả. |
| `SqlInOutParameter(name, sqlType)` | INOUT | Vừa truyền giá trị đầu vào, vừa đọc lại giá trị đã được routine thay đổi. |
| `SqlOutParameter(name, type, rowMapper)` | OUT dạng REF CURSOR/result có row mapping phù hợp | Giúp map các hàng kết quả, tùy kiểu cursor và database. |
| `SqlReturnResultSet(name, rowMapper)` | Result set trực tiếp từ JDBC results | Dùng trong các driver/procedure trả result set trực tiếp; không đồng nhất với OUT scalar. |
| `SqlReturnUpdateCount(name)` | Số hàng cập nhật từ chuỗi JDBC results | Không phải khóa sinh hay giá trị OUT của routine. |

Với `SqlOutParameter` kiểu cursor, có thể gặp mã vendor-specific như `OracleTypes.CURSOR` hoặc `Types.REF_CURSOR`. Không mặc định mọi driver hỗ trợ chúng giống nhau; cách database trả cursor, tên key và thứ tự kết quả cần được test thật.

**Thứ tự `declareParameter` có ý nghĩa.** Cấu trúc được dùng để tạo `CallableStatement`, và khi gọi bằng `execute(Object...)` thì thứ tự các giá trị IN phải khớp thứ tự những tham số nhận input theo khai báo. Việc đổi thứ tự khai báo trong refactor có thể làm biến đổi hành vi ngay cả khi không thay đổi tên tham số.

**Chi tiết tương thích cũ:** khác với cách xử lý của `SimpleJdbcCall`, lớp `StoredProcedure` có một số cơ chế tương thích cho phép truyền giá trị input cho cả tham số được khai báo dưới dạng `SqlOutParameter`. Đừng coi tất cả mã dùng `SqlOutParameter` làm input là lỗi ngay lập tức, và đừng tự động chuyển chữ ký sang `SimpleJdbcCall` trước khi xác minh cách routine thật sự hoạt động. Đây là một trong những khác biệt dễ gây regression khi thay API.

## 6. Ba kiểu execute(...) và cách đọc giá trị

### A. `execute(Map<String, ?>)` — truyền theo tên

```java
Map<String, Object> outputs =
        super.execute(Map.of("in_customer_id", 42L));
String name = (String) outputs.get("out_name");
```

Đây là đoạn minh họa **bên trong lớp con `StoredProcedure`** đã khai báo IN/OUT tương ứng. Key đầu vào phải phù hợp tên tham số khai báo. Với giá trị `null`, **không dùng `Map.of`** vì factory này từ chối `null`; dùng `HashMap` hoặc một cách chứa giá trị nullable phù hợp.

Map kết quả không nhất thiết chứa một entity, danh sách hàng hoặc ID. Nó là tập giá trị mà Spring tổng hợp theo các tham số OUT và các kết quả được khai báo. Không giả định map nhận được là một hàng dữ liệu của bảng.

### B. `execute(Object...)` — truyền theo vị trí

```java
Map<String, Object> outputs = super.execute(42L);
```

Đây là một overload khác bên trong lớp con, phù hợp khi có đúng **một input**. Với nhiều input, thứ tự các giá trị phải tương ứng thứ tự các tham số nhận input đã khai báo:

```java
// Nếu đã khai báo IN "in_id" trước rồi IN "in_region" sau:
Map<String, Object> outputs = super.execute(42L, "APAC");
```

Hai đoạn không thuộc cùng một chữ ký procedure ở phần 2; chúng minh họa hình thức gọi. Khi đọc code cũ, không thể xác định `42L` là tham số gì nếu chưa xem thứ tự `declareParameter`.

### C. `execute(ParameterMapper)` — tùy biến bind tham số

Khi thấy `execute(ParameterMapper)`, callback được trao `Connection` để tạo map tham số. Mẫu này từng được dùng cho dữ liệu/vendor-specific cần cách truyền đặc biệt. Trong review, cần kiểm tra mapper có phụ thuộc loại JDBC driver nào, có tạo object SQL đặc thù và có quản lý tài nguyên đúng cách không. Đừng áp dụng một refactor thuần `Map` khi chưa hiểu logic này.

### Kết quả thường được chuyển sang kiểu miền nghiệp vụ

```java
public String findName(long customerId) {
    Map<String, Object> out =
            super.execute(Map.of("in_customer_id", customerId));
    Object value = out.get("out_name");
    return value == null ? null : (String) value;
}
```

Phương thức public của lớp con giúp lớp service không cần biết tên key OUT. Đây là lý do một lớp `StoredProcedure` có thể tồn tại nhiều năm trong mã hiện có: nó đóng gói giao thức gọi database trong một API nghiệp vụ có kiểu rõ ràng.

## 7. Demo nhỏ chạy được: nhận diện và gọi một stored function qua StoredProcedure

Để thấy toàn bộ luồng `extends StoredProcedure → declareParameter → compile → super.execute → kết quả OUT` mà không cần triển khai procedure riêng trên máy chủ database, ta dùng hàm SQL `ABS` có sẵn trong H2 in-memory. **Đây là ví dụ về function**, vì vậy có `setFunction(true)`. Mã wrapper kiểu cũ vẫn dùng chính `StoredProcedure`, minh họa rằng tên lớp Java này không giới hạn lời gọi chỉ ở SQL procedure.

Tạo dự án:

```text
stored-procedure-recognition/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── Demo.java
```

`build.gradle` (Groovy DSL, JDK 17+, Gradle 8.x):

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'Demo'
}
```

`src/main/java/Demo.java`:

```java
import java.sql.Types;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.object.StoredProcedure;

public class Demo {

    // Lớp adapter có cấu trúc tương tự code legacy trong dự án.
    static final class AbsFunction extends StoredProcedure {

        AbsFunction(DataSource dataSource) {
            super(dataSource, "ABS");
            setFunction(true); // JDBC function: {? = call ABS(?)}

            // OUT cho kết quả hàm; IN cho đối số của ABS.
            declareParameter(
                    new SqlOutParameter("absolute_result", Types.INTEGER));
            declareParameter(
                    new SqlParameter("input_value", Types.INTEGER));

            compile();
        }

        int absolute(int value) {
            Map<String, Object> output =
                    super.execute(Map.of("input_value", value));

            Object result = output.get("absolute_result");
            if (!(result instanceof Number number)) {
                throw new IllegalStateException(
                        "Function ABS did not return a numeric result");
            }
            return number.intValue();
        }
    }

    public static void main(String[] args) {
        // H2 in-memory và DataSource đơn giản để minh họa, không pooling.
        DataSource ds = new DriverManagerDataSource(
                "jdbc:h2:mem:legacy_proc;DB_CLOSE_DELAY=-1", "sa", "");

        AbsFunction wrapper = new AbsFunction(ds);

        System.out.println("ABS(-7)=" + wrapper.absolute(-7));
        System.out.println("ABS(12)=" + wrapper.absolute(12));
    }
}
```

Từ thư mục dự án, chạy:

```bash
gradle run
```

Nếu đã có Gradle Wrapper thì dùng `./gradlew run` (Linux/macOS) hoặc `.\gradlew.bat run` (PowerShell Windows). Các dependency cần được tải từ kho Maven ở lần đầu. Phần output do **`Demo.main`** tạo ra, không tính log Gradle, là:

```text
ABS(-7)=7
ABS(12)=12
```

Giải thích từng mốc:

1. Constructor `AbsFunction` gắn đối tượng với `DataSource` và tên hàm SQL `ABS`.
2. `setFunction(true)` cho Spring biết lời gọi này có giá trị trả về ở vị trí OUT đầu tiên.
3. `SqlOutParameter("absolute_result", Types.INTEGER)` khai báo kết quả hàm; `SqlParameter("input_value", Types.INTEGER)` khai báo đầu vào.
4. `compile()` chuẩn bị cấu hình lời gọi JDBC; nó không tính giá trị tuyệt đối.
5. `super.execute(Map.of(...))` mới thực hiện call qua `JdbcTemplate`/`CallableStatement`.
6. Spring trả về map với key `absolute_result`, sau đó phương thức `absolute` chuyển kết quả thành `int`.
7. Hai lần gọi sử dụng **cùng một** wrapper đã cấu hình xong; đó là mô hình tái sử dụng điển hình của `RdbmsOperation`.

Demo dùng chức năng function call của H2. Một database khác có thể có quy tắc tên hàm, schema, kiểu kết quả hoặc cú pháp gọi khác; không dùng output của demo để suy ra chữ ký của procedure nghiệp vụ trong dự án.

### Nếu trong mã đang thấy một procedure có OUT

So với demo function, một wrapper cho procedure có thể chỉ khai báo:

```java
super(dataSource, "read_stock");
declareParameter(new SqlParameter("in_sku", Types.VARCHAR));
declareParameter(new SqlOutParameter("out_quantity", Types.INTEGER));
compile();
```

Đây là **đoạn constructor minh họa, không phải chương trình độc lập**. Nó giả định database có routine `read_stock` nhận `in_sku` và trả `out_quantity`, cùng driver hỗ trợ OUT parameter. Không thêm `setFunction(true)` vì đây là procedure thông thường.

Trong wrapper, lời gọi có thể là:

```java
Map<String, Object> out =
        super.execute(Map.of("in_sku", "SKU-10"));
Object quantity = out.get("out_quantity");
```

Nếu `out_quantity` có thể SQL NULL, cần xử lý `null`; nếu là số, không cast mù quáng sang `Integer` nếu driver trả `Long`/`BigDecimal`. `Map.of(...)` chỉ thích hợp khi `in_sku` khác `null`.

## 8. Tình huống GenericStoredProcedure: không thấy extends thì sao?

Trong mã hiện có, không phải lúc nào người viết cũng tạo lớp con `extends StoredProcedure`. Spring có `org.springframework.jdbc.object.GenericStoredProcedure`, lớp cụ thể kế thừa `StoredProcedure` và cho phép cấu hình generic.

Ví dụ JavaBean-style:

```java
GenericStoredProcedure procedure = new GenericStoredProcedure();
procedure.setDataSource(dataSource);
procedure.setSql("read_stock");
procedure.declareParameter(
        new SqlParameter("in_sku", Types.VARCHAR));
procedure.declareParameter(
        new SqlOutParameter("out_quantity", Types.INTEGER));
procedure.compile();

Map<String, Object> output =
        procedure.execute(Map.of("in_sku", "SKU-10"));
```

Đây là **đoạn minh họa**; cần import `GenericStoredProcedure`, `SqlParameter`, `SqlOutParameter`, `Types`, `Map` và có biến `dataSource` cùng stored procedure thực tế. Nó không tự chạy với H2 từ demo trước.

Khi kiểm tra bean Spring XML hoặc cấu hình cũ, tìm class name `org.springframework.jdbc.object.GenericStoredProcedure`, property `dataSource`/`jdbcTemplate`, `sql`, danh sách tham số và cách khởi tạo bean. Spring có thể gọi `afterPropertiesSet()` để hoàn thành compile nếu cấu hình bean phù hợp; không kết luận rằng mã thiếu `compile()` trong constructor thì nhất định chưa compile. Với cấu hình thuần Java, gọi `compile()` sau khi khai báo đầy đủ là rõ ràng nhất.

## 9. Phân biệt StoredProcedure với các API trông giống nhau

| Bạn tìm thấy trong dự án | Thực chất | Cách đọc đúng |
| --- | --- | --- |
| `org.springframework.jdbc.object.StoredProcedure` | Spring JDBC RDBMS object trừu tượng; thường có lớp con. | Xem `super`/`setSql`, `declareParameter`, `compile` và `super.execute`. |
| `org.springframework.jdbc.object.GenericStoredProcedure` | Bản cụ thể dùng cấu hình generic. | Xem bean properties, declared parameters và caller của `execute`. |
| `org.springframework.jdbc.core.simple.SimpleJdbcCall` | API Spring JDBC để gọi procedure/function, có hỗ trợ metadata. | Xem `withProcedureName`/`withFunctionName`, `declareParameters`, `execute`/`executeFunction`. |
| `org.springframework.jdbc.core.JdbcTemplate.call(...)` | Lời gọi thẳng qua `CallableStatementCreator` và danh sách tham số. | Xem callback tạo `CallableStatement` và cách register/bind. |
| `java.sql.CallableStatement` | JDBC API mức thấp. | Xem `prepareCall`, `registerOutParameter`, `setXxx`, `execute` và `getXxx`. |
| `jakarta.persistence.StoredProcedureQuery` | API JPA cho stored procedure. | Xem `EntityManager`, `registerStoredProcedureParameter`, `execute`. |
| `org.springframework.data.jpa.repository.query.Procedure` | Annotation Spring Data JPA trên repository method. | Xem JPA mapping, annotation và phương thức repository. |

**Điểm dễ nhầm:** Có một kiểu tên gần giống là `SimpleJdbcCall`, và có những codebase dùng cả hai cách. Việc chúng đều gọi stored procedure không chứng minh chúng bind tham số, metadata, return value hay result set hoàn toàn giống nhau.

### So sánh cấu hình một procedure với SimpleJdbcCall

`StoredProcedure` kiểu cũ:

```java
class ReadStockProcedure extends StoredProcedure {
    ReadStockProcedure(DataSource ds) {
        super(ds, "read_stock");
        declareParameter(new SqlParameter("in_sku", Types.VARCHAR));
        declareParameter(
                new SqlOutParameter("out_quantity", Types.INTEGER));
        compile();
    }
}
```

`SimpleJdbcCall` cho cùng chữ ký theo giả định:

```java
SimpleJdbcCall readStock = new SimpleJdbcCall(dataSource)
        .withProcedureName("read_stock")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("in_sku", Types.VARCHAR),
                new SqlOutParameter("out_quantity", Types.INTEGER));

Map<String, Object> out =
        readStock.execute(Map.of("in_sku", "SKU-10"));
```

Hai đoạn chỉ minh họa **cấu hình tương ứng**, cần import và môi trường cơ sở dữ liệu thực tế. `SimpleJdbcCall` không yêu cầu tạo subclass và có thể suy luận metadata trong những trường hợp driver đủ thông tin; ví dụ trên tắt metadata tham số để mô tả một chữ ký cố định. Đừng xem ví dụ này là bằng chứng refactor sẽ tương đương trên mọi DB.

Cần kiểm tra riêng nếu mã cũ có: `setFunction(true)`, `setSqlReadyForUse(true)`, `SqlInOutParameter`, OUT cursor, `SqlOutParameter` được dùng như input vì tương thích cũ, thứ tự output hoặc SQL dùng schema/catalog. Đây là những điểm cần viết test hồi quy trước khi cân nhắc chuyển sang `SimpleJdbcCall`.

## 10. Khi nhận diện trong một hệ thống thật: kiểm tra gì để không sửa sai?

Hãy trả lời các câu hỏi sau bằng **mã hiện có và schema thực tế**:

1. **Routine tồn tại ở đâu?** `super(ds, "proc_name")` chỉ cho biết tên cấu hình; tìm database migration/DDL và schema đang kết nối trước khi kết luận đây là thủ tục xử lý nghiệp vụ gì.
2. **Ai sở hữu transaction?** `StoredProcedure` tự nó không nói transaction bắt đầu/commit ở đâu. Xem `@Transactional`, transaction manager và lời gọi ở service. Routine có thể ghi dữ liệu nhiều bảng, không chỉ trả một giá trị.
3. **Tham số có đúng thứ tự và kiểu không?** Đối chiếu `declareParameter` với chữ ký DB; đặc biệt kiểm tra `Object...` và function return.
4. **Các OUT có thể null không?** Tránh chuyển `null` sang primitive hoặc ép kiểu sai; chuyển `Number` một cách có kiểm tra.
5. **Result set hay cursor được đọc ở đâu?** Tìm `SqlReturnResultSet`, `SqlOutParameter` có `RowMapper`, tên result key và code consume danh sách.
6. **Có phụ thuộc driver không?** REF CURSOR, custom SQL types, schema, chữ hoa/thường, metadata và callable syntax cần test bằng database tương đương production.
7. **Có cạnh tranh luồng không?** Wrapper được cấu hình/compile một lần và tái sử dụng; không mutate configuration trong lúc các thread đang gọi. Mỗi lần execute chứa dữ liệu tham số riêng.
8. **Ngoại lệ đi đâu?** Spring JDBC ném hệ `DataAccessException` runtime thay cho việc buộc caller bắt `SQLException` trực tiếp. Xem handler và transaction rollback rules.
9. **Khi nào kết quả được công bố ra ngoài?** Thủ tục có side effect có thể chạy trong giao dịch sẽ rollback; việc nhận OUT thành công không tự chứng minh commit thành công.

### Ví dụ: đọc lỗi theo vị trí trong pipeline

Giả sử code gọi:

```java
Map<String, Object> output =
        myProcedure.execute(Map.of("in_id", id));
```

- Nếu lỗi ngay khi khởi tạo `myProcedure` hoặc gọi `compile()`, xem cấu hình `DataSource`, tên routine, danh sách tham số và lỗi compile.
- Nếu lỗi khi thực thi, xem database routine, quyền `EXECUTE`, schema, SQL type, thứ tự bind, driver và transaction.
- Nếu gọi thành công nhưng map không có key `out_name`, xem danh sách OUT đã khai báo, case của key, callback/result set và kiểu kết quả.
- Nếu map có giá trị nhưng service hỏng, xem chuyển đổi kiểu, `null`, contract phương thức nghiệp vụ và xử lý ngoại lệ của caller.

Không tự suy đoán lỗi là do JDBC driver chỉ từ một `ClassCastException` trong code lấy OUT: đó có thể là lỗi Java mapping sau khi DB đã trả đúng giá trị.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “StoredProcedure là annotation SQL chạy trực tiếp” | Đây là class Java của Spring JDBC. | Một instance bao lời gọi routine ở database thông qua `CallableStatement`. |
| “`compile()` chạy procedure” | Compile là bước chuẩn bị cấu hình. | Lời gọi thực tế diễn ra khi `execute(...)`. |
| “Tên class Java chính là tên routine SQL” | Class Java do dự án đặt tên. | Tìm `super(ds, name)`, `setSql`, hoặc raw call string. |
| “`execute(Map)` trả toàn bộ hàng của bảng” | Output map phản ánh OUT/result được khai báo. | Đọc từng key và mapper; không coi mặc nhiên là entity. |
| “`execute(Object...)` nhận mọi giá trị theo tên” | Overload này nhận theo vị trí. | Xem thứ tự `declareParameter`. |
| “Tham số OUT không ảnh hưởng lời gọi function” | Function return thường cần vị trí OUT. | Kiểm tra `setFunction(true)` và khai báo OUT thích hợp. |
| “Mỗi lần chạy phải tạo mới StoredProcedure” | Kiểu RDBMS operation hỗ trợ tái sử dụng sau khi cấu hình. | Khởi tạo/compile một lần, gọi nhiều lần với tham số riêng. |
| “Đổi tất cả sang SimpleJdbcCall sẽ tương đương” | Có khác biệt metadata, cách lấy input/OUT, cursor và hành vi tương thích. | Viết integration test cho chữ ký DB trước khi thay. |
| “Đã có OUT thì dữ liệu chắc chắn commit” | Transaction có thể rollback sau khi routine thực thi. | Kiểm tra transaction boundary và hành vi side effect. |
| “Phải import jakarta.sql.DataSource” | `DataSource` là API JDBC trong Java SE. | Dùng `javax.sql.DataSource`; `jakarta.persistence.StoredProcedureQuery` là API khác. |

## 12. Bài tập đọc mã ngắn

Xem đoạn code:

```java
final class StatusFunction extends StoredProcedure {
    StatusFunction(DataSource ds) {
        super(ds, "order_status_code");
        setFunction(true);
        declareParameter(
                new SqlOutParameter("status", Types.INTEGER));
        declareParameter(
                new SqlParameter("in_order_id", Types.BIGINT));
        compile();
    }

    int getStatus(long orderId) {
        Map<String, Object> out =
                super.execute(Map.of("in_order_id", orderId));
        Object value = out.get("status");
        if (!(value instanceof Number number)) {
            throw new IllegalStateException("Invalid status result");
        }
        return number.intValue();
    }
}
```

Đây là **đoạn minh họa**: các import và database function `order_status_code` được lược bỏ nên không phải chương trình độc lập.

Tự trả lời:

1. **Đây là procedure hay function?** Là function, vì có `setFunction(true)`. Tên class `StatusFunction` chỉ là gợi ý, cấu hình mới là căn cứ.
2. **Đầu vào là gì?** Một tham số IN `in_order_id` kiểu SQL `BIGINT`; giá trị lấy từ `orderId`.
3. **Đầu ra lấy ở đâu?** Trong map của `super.execute(...)` theo key `status`, khai báo bằng `SqlOutParameter`.
4. **`compile()` có gọi DB để lấy status không?** Không. Bước lấy kết quả ở `execute`.
5. **Điều gì cần kiểm tra trước khi chạy production?** Routine thực sự tồn tại, chữ ký return/IN đúng, driver hỗ trợ callable function, kiểu trả về có thể là `null` hoặc numeric khác, quyền thực thi và transaction nếu có side effect.

Nếu trả lời được năm câu này, bạn đã có thể nhận diện phần lớn wrapper `StoredProcedure` trong codebase trước khi debug hoặc chỉnh sửa.

## 13. Bảng ghi nhớ khi review code legacy

```text
extends StoredProcedure / GenericStoredProcedure
    │
    ├── super(dataSource, "routine") / setSql / setJdbcTemplate
    ├── [setFunction(true)]            -> function có return value
    ├── [setSqlReadyForUse(true)]      -> raw JDBC call string
    ├── declareParameter(...)         -> IN, OUT, INOUT, cursor/result
    └── compile() / afterPropertiesSet
                       │
                       ▼
              Phương thức domain wrapper
                       │
                       ▼
                super.execute(...)
                       │
                       ▼
            JdbcTemplate.call(...) 
                       │
                       ▼
             JDBC CallableStatement
                       │
                       ▼
                   DB routine
                       │
                       ▼
             Map kết quả OUT/result
                       │
                       ▼
            Mapping sang kiểu nghiệp vụ
```

**Điểm cần nhớ:** khi đọc mã Spring JDBC cũ, đừng chỉ tìm `execute()`. Hãy đọc **class/package → tên routine → loại procedure/function → khai báo tham số → cách truyền input → map OUT → caller/transaction**. Chuỗi này giải thích chính xác nơi phát sinh dữ liệu và thường chỉ ra điểm có thể gây lỗi khi nâng cấp.

### Nguồn tham khảo chính thức

- Spring Framework — *Modeling JDBC Operations as Java Objects*, bao gồm phần `StoredProcedure`: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/object.html
- Spring Framework — *Choosing an Approach for JDBC Database Access*: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/choose-style.html
- Spring Framework Javadoc — `StoredProcedure` (Spring 6.2): https://docs.spring.io/spring-framework/docs/6.2.14-SNAPSHOT/javadoc-api/org/springframework/jdbc/object/StoredProcedure.html
- Spring Framework Javadoc — `RdbmsOperation`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/object/RdbmsOperation.html
- Spring Framework Javadoc — `GenericStoredProcedure`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/object/GenericStoredProcedure.html
- Spring Framework — `SimpleJdbcCall` trong *Simplifying JDBC Operations*: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/simple.html
- H2 Database — *User-Defined Functions and Stored Procedures*: https://h2database.com/html/features.html
