# Java 7 — JDBC: Xử lý SQLFeatureNotSupportedException và driver

## 1. Mục tiêu và bối cảnh

`JDBC` (Java Database Connectivity) là bộ API chuẩn trong `java.sql` và `javax.sql` để ứng dụng Java kết nối, thực thi SQL, đọc kết quả và quản lý giao dịch với cơ sở dữ liệu thông qua **JDBC driver**. Java 7 giới thiệu nhiều cải tiến JDBC, nhưng JDBC là một API phát triển liên tục: cùng một mã nguồn biên dịch được trên Java 17 **không đảm bảo mọi driver và cơ sở dữ liệu đều hỗ trợ tất cả phương thức, overload hoặc tùy chọn**.

Bài học tập trung đúng vào mục: **“Xử lý SQLFeatureNotSupportedException và driver”**, thuộc nhóm **JDBC**. Giới hạn nội dung theo yêu cầu cập nhật: chỉ giới thiệu kiến thức vẫn dùng trên Java 17+; không coi workaround cũ như bắt buộc `Class.forName` trong mọi ứng dụng, không sử dụng driver lỗi thời hay API đã deprecated làm giải pháp mặc định.

Mục tiêu sau khi học:

1. Hiểu chính xác khi nào JDBC ném `SQLFeatureNotSupportedException`.
2. Phân biệt class exception với mã `SQLState` nhóm `0A`.
3. Phân biệt unsupported feature với **không tìm thấy driver**, **kết nối thất bại**, **timeout**, **lỗi cú pháp** và **vi phạm ràng buộc dữ liệu**.
4. Hiểu cấu trúc `SQLException`, `SQLNonTransientException`, `SQLTransientException` và cách lấy chuỗi nguyên nhân.
5. Chẩn đoán driver từ JDBC URL, dependency/runtime classpath, service-provider, version, database server và classloader.
6. Biết `DriverManager` và lý do `DataSource` / connection pool thường phù hợp cho production.
7. Dùng `DatabaseMetaData` kiểm tra những capability có API tương ứng mà không coi metadata là bằng chứng toàn năng.
8. Chỉ fallback khi giữ được **semantics, bảo mật và transaction correctness**.
9. Không retry mù quáng khi tính năng không được hỗ trợ; không chạy lại câu SQL ghi có side effect khi chưa biết trạng thái commit.
10. Dùng try-with-resources, rollback, exception chains và structured logging đúng.
11. Thiết kế integration tests theo **driver + DB + version** thực tế.
12. Thực hành 13 chương trình Java 17 độc lập, kiểm thử được **không cần cài database** nhờ mock driver/`Proxy`, đồng thời biết giới hạn của mock tests.

## 2. JDBC gồm hai thành phần không được đánh đồng

```text
         APPLICATION — Java 17+
                  |
       JDBC interfaces: java.sql
                  |
      DriverManager / DataSource
                  |
        JDBC DRIVER (vendor)
                  |
           DATABASE SERVER
                  |
       Dialect / permissions / types
```

**JDBC API** đưa ra những interface như `Connection`, `Statement`, `PreparedStatement`, `ResultSet`, `DatabaseMetaData`, `Driver`. Nhưng **driver cụ thể** phải triển khai các lệnh tương thích với **DBMS server** và phiên bản đang kết nối.

Nếu một phương thức JDBC “có trong interface” nhưng driver không thực hiện được tính năng **tùy chọn** đó, chương trình có thể nhận `SQLFeatureNotSupportedException`.

### 2.1. Biên dịch thành công không có nghĩa runtime hỗ trợ

```java
Array array = connection.createArrayOf(
        "INTEGER", new Object[] {1, 2});
```

Đây là **mảnh minh họa**, cần `Connection connection` đang mở và driver hỗ trợ. Code có thể **biên dịch được** trên Java 17, nhưng một driver có thể không hỗ trợ tạo SQL ARRAY, hoặc database không có kiểu mảng phù hợp.

### 2.2. Database và driver đều ảnh hưởng

Một driver hỗ trợ batch update khi kết nối DB server phiên bản này nhưng không hỗ trợ tính năng khác ở phiên bản khác. Một số feature phụ thuộc vào SQL dialect, kiểu dữ liệu, quyền truy cập, transaction mode và cấu hình connection.

**Không có một “JDBC 4.x supported” boolean duy nhất** đảm bảo mọi optional operation.

## 3. SQLFeatureNotSupportedException là gì?

Java 17 có:

```java
public class SQLFeatureNotSupportedException
        extends SQLNonTransientException
```

Đây là **chữ ký class trích yếu**, không phải chương trình độc lập.

Javadoc dùng exception này cho **SQLState class `0A`**, tức tính năng tùy chọn không được JDBC driver hỗ trợ. Những tình huống theo API:

- **Optional feature** hoàn toàn không được hỗ trợ.
- **Optional overloaded method** không được driver thực hiện.
- **Optional mode** của method không được hỗ trợ, thường được chọn qua constants/arguments.
  
Ví dụ có thể gặp ở các driver/DB khác nhau:

- Một API tạo `Array` hoặc `Clob` không được triển khai.
- `ResultSet.getObject(column, SomeClass.class)` không hỗ trợ mapping kiểu được yêu cầu.
- Tùy chọn generated keys hoặc result-set mode chưa được hỗ trợ.
- Một overload `executeLargeUpdate` / `setObject` trong driver chỉ hỗ trợ các dạng cơ bản.
- Một feature metadata hoặc method mới hơn JDBC implementation driver.
- Một chế độ statement/connection mà driver không thực hiện.

**Không được suy:** “Java không hỗ trợ JDBC”, “SQL sai cú pháp”, “cần retry sau 2 giây”, “mọi drivers đều không hỗ trợ”, hoặc “bỏ qua exception luôn an toàn”.

### 3.1. Cây kế thừa

```text
Throwable
  |
Exception
  |
SQLException
  |
SQLNonTransientException
  |
SQLFeatureNotSupportedException
```

`SQLNonTransientException` nói việc **retry lại y nguyên** sẽ không thành công trừ khi nguyên nhân được thay đổi. Nếu driver không có feature, delay 1/3/5 giây không khiến feature xuất hiện.

### 3.2. SQLState class 0A

Trong SQL standard/JDBC, **hai ký tự đầu `0A`** của `SQLState` biểu thị *feature not supported*. Một mã thường thấy là `0A000`.

Tuy nhiên **cực kỳ quan trọng:** constructor `new SQLFeatureNotSupportedException("unsupported")` **không tự gắn `0A000`**; `getSQLState()` của object đó là `null`. Vì thế:

- Ưu tiên nhận diện class `instanceof SQLFeatureNotSupportedException` khi driver ném đúng subtype.
- Kiểm `SQLState` khi có, đặc biệt `startsWith("0A")`, như tín hiệu bổ sung.
- Không dereference `getSQLState().startsWith(...)` nếu state có thể null.
- Driver có thể trả `SQLException` chung hoặc vendor code thay vì subclass mong muốn.
- Không hardcode chỉ một mã `0A000` cho mọi driver.
- Dựa thêm documentation của vendor khi phân loại lỗi quan trọng.

## 4. Chương trình A — FeatureExceptionDemo.java

```java
import java.sql.*;

public final class FeatureExceptionDemo {
 public static void main(String[] args) {
   SQLException failure = new SQLFeatureNotSupportedException(
       "generated keys unavailable", "0A000", 901);

   System.out.println("featureSubclass=" +
       (failure instanceof SQLFeatureNotSupportedException));
   System.out.println("nonTransient=" +
       (failure instanceof SQLNonTransientException));
   System.out.println("sqlState=" + failure.getSQLState());
   System.out.println("vendorCode=" + failure.getErrorCode());
   System.out.println("reason=" + failure.getMessage());
 }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 FeatureExceptionDemo.java
java FeatureExceptionDemo
```

**Stdout đã kiểm thử:**

```text
featureSubclass=true
nonTransient=true
sqlState=0A000
vendorCode=901
reason=generated keys unavailable
```

`901` là vendor code **giả lập do ví dụ truyền vào**, không phải số mã chính thức áp dụng cho mọi driver. Các thông tin `getSQLState`, `getErrorCode` và `getMessage` giúp chẩn đoán; nhưng đừng giả định message cố định để viết logic production.

## 5. Chương trình B — ConstructorStateDemo.java

Đây là ví dụ cho lỗi rất phổ biến: coi class exception luôn có mã SQLState `0A000`.

```java
import java.sql.*;

public final class ConstructorStateDemo {
 public static void main(String[] args) {
   SQLFeatureNotSupportedException a =
       new SQLFeatureNotSupportedException("unsupported");
   SQLFeatureNotSupportedException b =
       new SQLFeatureNotSupportedException(
           "unsupported", "0A000");

   System.out.println("reasonOnlyStateIsNull=" +
       (a.getSQLState() == null));
   System.out.println("reasonOnlyVendorCode=" +
       a.getErrorCode());
   System.out.println("explicitState=" +
       b.getSQLState());
   System.out.println("classIsStillFeatureUnsupported=" +
       (a instanceof SQLFeatureNotSupportedException));
 }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 ConstructorStateDemo.java
java ConstructorStateDemo
```

**Stdout đã kiểm thử:**

```text
reasonOnlyStateIsNull=true
reasonOnlyVendorCode=0
explicitState=0A000
classIsStillFeatureUnsupported=true
```

**Bài học:** subclass và `SQLState` là **hai nguồn thông tin có liên quan nhưng không thay thế nhau**. Một vendor wrapper có thể giữ nguyên SQLState nhưng mất concrete subtype, hoặc một constructor chỉ điền reason và để state null.

## 6. Phân biệt exception: unsupported, transient, syntax, constraint và connection

| Kiểu lỗi | Ví dụ class | Gợi ý xử lý |
| --- | --- | --- |
| Optional feature unsupported | `SQLFeatureNotSupportedException` | Không blind retry; đổi feature, driver, plan hoặc fail-fast |
| Lỗi tạm thời | `SQLTransientException` và subclasses | Xem xét retry **có giới hạn**, chỉ khi operation idempotent/safe |
| Timeout | `SQLTimeoutException` | Có thể statement/server vẫn đang xử lý; phân tích outcome trước retry |
| Transaction rollback | `SQLTransactionRollbackException` | Xem transaction isolation, retry unit of work khi thực sự an toàn |
| Constraint violation | `SQLIntegrityConstraintViolationException` | Sửa data/unique/key, không retry y nguyên |
| SQL syntax | `SQLSyntaxErrorException` | Sửa SQL/dialect/query, không retry giống cũ |
| Connection failure | `SQLNonTransientConnectionException` / `SQLTransientConnectionException` | Kiểm URL/network/credentials/server/pool; phân loại trước retry |
| Data conversion | `SQLDataException` | Sửa type/value mapping |
| SQLException chung | `SQLException` | Đọc SQLState/vendor code/cause/next exceptions |

**Cẩn thận:** Runtime JDBC driver có thể dùng subclasses không đúng như ví dụ của bạn; một exception từ DB server có thể được driver wrap. Cần dùng class, SQLState, vendor docs và context nghiệp vụ cùng nhau.

### 6.1. SQLTransientException không cấp giấy phép retry mọi thứ

Một lỗi transient có thể phù hợp retry với **SELECT idempotent** hoặc transaction được rollback xác nhận. Với **INSERT/UPDATE** đã gửi mà outcome không rõ (network timeout sau khi DB có thể commit), retry mù quáng có thể tạo giao dịch trùng.

### 6.2. Unsupported method khác unsupported SQL dialect

Một SQL query dùng cú pháp mà DB không hiểu có thể gây `SQLSyntaxErrorException`, không phải `SQLFeatureNotSupportedException`. Đừng catch `SQLFeatureNotSupportedException` rồi bỏ qua lỗi syntax; đó là hai nguyên nhân khác nhau.

### 6.3. Error message không là API ổn định

String `"not implemented"`/`"unsupported"` có thể thay đổi theo vendor/version/locale. Không dựa vào `message.contains("unsupported")` để thực thi fallback có side effects. Ưu tiên type/SQLState/documented error code và capability check.

## 7. Chương trình C — SQLExceptionPolicyDemo.java

```java
import java.sql.*;

public final class SQLExceptionPolicyDemo {
 static String decide(SQLException e) {
   if (e instanceof SQLFeatureNotSupportedException)
     return "UNSUPPORTED_NO_BLIND_RETRY";
   if (e instanceof SQLTransientException)
     return "TRANSIENT_REVIEW_RETRY";
   if (e instanceof SQLIntegrityConstraintViolationException)
     return "CONSTRAINT_FAILURE";
   if (e instanceof SQLSyntaxErrorException)
     return "FIX_SQL";
   return "OTHER_SQL_ERROR";
 }

 public static void main(String[] args) {
   System.out.println("optional=" + decide(
       new SQLFeatureNotSupportedException(
           "unsupported", "0A000")));
   System.out.println("timeout=" + decide(
       new SQLTimeoutException("too slow")));
   System.out.println("constraint=" + decide(
       new SQLIntegrityConstraintViolationException(
           "duplicate")));
   System.out.println("syntax=" + decide(
       new SQLSyntaxErrorException("bad SQL")));
   System.out.println("unknown=" + decide(
       new SQLException("unknown")));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SQLExceptionPolicyDemo.java
java SQLExceptionPolicyDemo
```

**Stdout đã kiểm thử:**

```text
optional=UNSUPPORTED_NO_BLIND_RETRY
timeout=TRANSIENT_REVIEW_RETRY
constraint=CONSTRAINT_FAILURE
syntax=FIX_SQL
unknown=OTHER_SQL_ERROR
```

Đây là **mô hình phân loại**, không phải hệ thống retry hoàn chỉnh. Production cần thêm operation idempotency, transaction state, SQLState class, vendor code, timeout/deadline, backoff và audit.

## 8. Chuỗi SQLException: nextException, cause, suppressed

JDBC error reporting có ba đường cần biết:

1. **`SQLException.getNextException()`**: danh sách SQLExceptions mà driver đính vào cùng một chuỗi.
2. **`Throwable.getCause()`**: nguyên nhân ném exception theo cơ chế Java.
3. **`Throwable.getSuppressed()`**: lỗi bổ sung, thường gặp khi close resource trong try-with-resources trong lúc một exception khác đã xảy ra.

Một exception có thể có **cả ba**; đừng chỉ log `e.getMessage()` và làm mất SQLState/vendor codes của errors phía sau.

### 8.1. Chương trình D — ExceptionChainDemo.java

```java
import java.sql.*;

public final class ExceptionChainDemo {
 public static void main(String[] args) {
   SQLException root =
       new SQLException("top-level", "HY000", 11);
   SQLException unsupported =
       new SQLFeatureNotSupportedException(
           "no arrays", "0A000", 22);
   SQLException other =
       new SQLTimeoutException("timeout", "HYT00", 33);

   root.setNextException(unsupported);
   unsupported.setNextException(other);
   root.addSuppressed(
       new IllegalStateException("cleanup"));

   int count=0, features=0;
   for (SQLException e=root;
        e!=null;
        e=e.getNextException()) {
     count++;
     if (e instanceof SQLFeatureNotSupportedException)
       features++;
   }

   System.out.println("chainCount=" + count);
   System.out.println("featureEntries=" + features);
   System.out.println("suppressedCount=" +
       root.getSuppressed().length);
   System.out.println("firstState=" +
       root.getSQLState());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ExceptionChainDemo.java
java ExceptionChainDemo
```

**Stdout đã kiểm thử:**

```text
chainCount=3
featureEntries=1
suppressedCount=1
firstState=HY000
```

`HY000` và `HYT00` trong ví dụ là **giá trị minh họa** gắn vào exceptions giả lập. Đừng tự cho rằng driver cụ thể luôn dùng hai mã này.

### 8.2. Log nên chứa gì?

- Operation name, không log raw SQL chứa bí mật.
- Driver name/version, database product/version (nếu an toàn).
- `SQLState`, vendor error code, exception class, safe reason.
- IDs cho request/transaction nhưng không log passwords/tokens/PII.
- `getNextException()` chain, `getCause`, suppressed close/rollback errors.
- Có thể log stack trace ở nơi được bảo vệ; không trả toàn bộ stack trace cho client.

## 9. Tại sao cần JDBC driver?

JDK 17 cung cấp JDBC API, **không mặc định đi kèm driver cho mọi cơ sở dữ liệu**. Khi kết nối PostgreSQL, MySQL, MariaDB, SQL Server, Oracle hoặc DBMS khác, ứng dụng cần dependency driver tương ứng, phiên bản tương thích với JDK, database và framework.

```text
java.sql.DriverManager.getConnection(jdbcUrl)
           |
           +-- discover registered/visible drivers
           |
           +-- ask driver that accepts URL
           |
           +-- driver contacts DB / authenticates / negotiates
           |
           +-- returns java.sql.Connection
                OR throws SQLException
```

### 9.1. “No suitable driver” không phải optional feature unsupported

Nếu JDBC URL không được driver nào đang visible chấp nhận, `DriverManager.getConnection` thường ném `SQLException` báo không có driver phù hợp. Đây là **dependency/URL/classloader/discovery** problem, không phải bằng chứng driver đã kết nối rồi nhưng thiếu optional feature.

### 9.2. Driver jar có phải được đóng gói đúng không?

Kiểm build và runtime:
- Dependency được khai báo cho **runtime** chứ không chỉ test/compile classpath.
- JDBC URL scheme và driver version đúng.
- Driver artifact đi cùng application package/container image.
- Nếu dùng modules hoặc app server, classloader/service-provider visibility đúng.
- Không bị shade/minify làm mất `META-INF/services/java.sql.Driver`.
- Có compatible database/JDK/driver version.
- Cấu hình credentials/SSL/network đúng.

Không log URL có credentials hoặc các giá trị bí mật.

## 10. DriverManager và auto-discovery trên Java hiện đại

`DriverManager` tải drivers thông qua cơ chế **service-provider** (và cấu hình `jdbc.drivers`) khi initialization. JDBC 4.0+ drivers hợp chuẩn thường tự đăng ký khi jar hiện diện trên runtime classpath/module path phù hợp.

**Thông thường không cần** lệnh `Class.forName("vendor.jdbc.Driver")` trong một ứng dụng Java hiện đại đã cấu hình driver jar đúng. Nếu cần debug classloader hay driver không công bố service-provider, có thể dùng explicit driver loading/registration theo tài liệu vendor — đó là **biện pháp có mục đích**, không phải default boilerplate.

### 10.1. Java SE 17 khuyến nghị DataSource

`DriverManager` rất tiện cho demo/standalone. Javadoc hiện đại nói `javax.sql.DataSource` là phương tiện được **ưu tiên** cho kết nối data source; trong ứng dụng thực thường dùng datasource được cấu hình cùng connection pool.

Ưu điểm:
- Tách code khỏi URL/credentials.
- Pooling/lifecycle do container/framework quản lý.
- Dễ inject mock/test datasource.
- Tránh mở vật lý một kết nối mới cho mọi request khi cần pooling.
- Quản lý TLS, timeouts, metrics và credential rotation theo infrastructure.

**Không tự gọi `close` để phá một pooled connection**: `Connection.close()` trong pooled connection thường trả handle về pool theo thiết kế datasource; vẫn dùng try-with-resources và để pool quyết định kết nối vật lý.

## 11. Chương trình E — MissingDriverDemo.java

Một URL demo chưa có driver nào đăng ký sẽ bị từ chối. Code không kết nối database thật.

```java
import java.sql.*;

public final class MissingDriverDemo {
 public static void main(String[] args) {
   boolean rejected=false;
   try {
     DriverManager.getConnection(
         "jdbc:missing-demo-protocol:sample");
   } catch (SQLException expected) {
     rejected=true;
   }
   System.out.println(
       "unrecognizedJdbcUrlRejected=" + rejected);
   System.out.println("driverJarStillRequired=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MissingDriverDemo.java
java MissingDriverDemo
```

**Stdout đã kiểm thử trong môi trường demo không đăng ký scheme đó:**

```text
unrecognizedJdbcUrlRejected=true
driverJarStillRequired=true
```

**Giới hạn:** Kết quả phụ thuộc runtime không có driver tùy biến cho scheme `jdbc:missing-demo-protocol:`. Trong môi trường có driver cố tình chấp nhận scheme ấy, test có thể không còn đúng. Dùng URL demo duy nhất, không gửi credentials thật.

## 12. DriverManager.registerDriver: minh họa driver giả lập

`DriverManager.registerDriver(Driver)` cho phép đăng ký driver rõ ràng; `deregisterDriver` hủy đăng ký. Đây là API vẫn hoạt động trên Java 17.

Trong production, để driver JDBC 4.x được runtime tự phát hiện qua service-provider là đường bình thường. Trong **unit test**, tự đăng ký một driver giả lập cho URL riêng là cách kiểm logic mà không cần DB vendor jar.

### 12.1. Driver implementation cần biết gì?

Interface `java.sql.Driver` gồm:
- `connect(String url, Properties info)`: thử kết nối khi hiểu URL; **trả null** khi URL không thuộc driver.
- `acceptsURL(String url)`: kiểm một URL có thuộc driver không.
- `getPropertyInfo`: mô tả properties.
- `getMajorVersion/getMinorVersion`: phiên bản driver.
- `jdbcCompliant()`: báo mức tuân thủ JDBC theo contract.
- `getParentLogger()`: logger của driver; có thể ném `SQLFeatureNotSupportedException` theo method contract khi không hỗ trợ.

**Không được viết custom driver như thế này cho production**; test mock chỉ minh họa workflow, không thực hiện SQL, authentication hoặc network I/O.

## 13. Chương trình F — FakeDriverDemo.java

Ví dụ đăng ký một driver nhận URL `jdbc:labmock:` và dùng `java.lang.reflect.Proxy` tạo Connection chỉ hỗ trợ vài method; `createArrayOf` cố tình ném unsupported.

```java
import java.sql.*;
import java.lang.reflect.*;
import java.util.Properties;
import java.util.concurrent.atomic.*;
import java.util.logging.Logger;

public final class FakeDriverDemo {
 static final class LabDriver implements Driver {
   final AtomicBoolean closed=new AtomicBoolean();

   public boolean acceptsURL(String url) {
     return url!=null && url.startsWith("jdbc:labmock:");
   }

   public Connection connect(String url,Properties props)
       throws SQLException {
     if(!acceptsURL(url))return null;

     InvocationHandler h=(p,m,a)->{
       switch(m.getName()){
         case "close":closed.set(true);return null;
         case "isClosed":return closed.get();
         case "getAutoCommit":return true;
         case "toString":return "LabConnection";
         case "isWrapperFor":return false;
         case "unwrap":throw new SQLException("no wrapper");
         default:throw new SQLFeatureNotSupportedException(
             "mock lacks "+m.getName(),"0A000");
       }
     };

     return (Connection)Proxy.newProxyInstance(
       Connection.class.getClassLoader(),
       new Class<?>[]{Connection.class},h);
   }

   public DriverPropertyInfo[] getPropertyInfo(
       String url,Properties info) {
     return new DriverPropertyInfo[0];
   }
   public int getMajorVersion(){return 1;}
   public int getMinorVersion(){return 0;}
   public boolean jdbcCompliant(){return false;}
   public Logger getParentLogger(){
     return Logger.getLogger("jdbc.labmock");
   }
 }

 public static void main(String[] args)throws Exception {
   LabDriver d=new LabDriver();
   DriverManager.registerDriver(d);
   try {
     Driver selected=DriverManager.getDriver(
         "jdbc:labmock:test");
     boolean featureCaught=false;
     try(Connection c=DriverManager.getConnection(
         "jdbc:labmock:test")){
       System.out.println("selectedFakeDriver="+
           (selected==d));
       System.out.println("autoCommit="+
           c.getAutoCommit());

       try {
         c.createArrayOf(
             "INTEGER",new Object[]{1,2});
       }catch(SQLFeatureNotSupportedException e){
         featureCaught=true;
       }
     }

     System.out.println("optionalFeatureRejected="+
         featureCaught);
     System.out.println("connectionClosed="+
         d.closed.get());
   }finally{
     DriverManager.deregisterDriver(d);
   }

   boolean remains=false;
   for(java.util.Enumeration<Driver> en=
          DriverManager.getDrivers();
       en.hasMoreElements();) {
     if(en.nextElement()==d)remains=true;
   }
   System.out.println("driverDeregistered="+
       (!remains));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FakeDriverDemo.java
java FakeDriverDemo
```

**Stdout đã kiểm thử:**

```text
selectedFakeDriver=true
autoCommit=true
optionalFeatureRejected=true
connectionClosed=true
driverDeregistered=true
```

### 13.1. Điều gì được chứng minh?

1. DriverManager nhận driver mock do demo đăng ký.
2. `getDriver` chọn đúng driver cho URL demo.
3. `getConnection` gọi mock driver và trả Connection.
4. `getAutoCommit` được mock hỗ trợ.
5. `createArrayOf` không được hỗ trợ và ném `SQLFeatureNotSupportedException`.
6. try-with-resources gọi `Connection.close()` ngay cả khi có lỗi.
7. `deregisterDriver` tránh giữ driver giả lập sau test.

Không kết nối DB thật; **không được suy** driver/vendor cụ thể nào ngoài môi trường demo thiếu `createArrayOf`.

### 13.2. Register/deregister liên quan memory leaks như thế nào?

Trong app servers hoặc plugin environments, việc tự register driver với classloader sống lâu hơn module có thể giữ references không mong muốn. Driver lifecycle phải do container/framework/owner quản lý. Demo chủ động deregister trong finally.

## 14. Khi driver đã tìm thấy nhưng kết nối vẫn thất bại

“Driver được tải” không đảm bảo database đang chạy hoặc thông tin kết nối đúng.

| Tình huống | Phương án chẩn đoán |
| --- | --- |
| Không có suitable driver | Kiểm dependency jar, URL prefix, service-provider/classloader |
| Driver nhận URL nhưng network lỗi | Kiểm hostname/port/DNS/firewall/TLS |
| Wrong credentials | Kiểm secret configuration/permissions |
| Unsupported auth protocol | Cập nhật driver/server, kiểm security docs |
| Server quá tải / connection limit | Pool sizing, server metrics, backpressure |
| Schema/SQL không phù hợp | SQL dialect/permissions/schema migration |
| Optional JDBC method unsupported | Capability, driver version, feature policy, fallback hợp lệ |

Đừng để catch block `SQLException e` tự chuyển tất cả thành “feature unsupported” và chạy một đường fallback không an toàn.

## 15. Chương trình G — ConnectFailureDemo.java

Driver giả lập này **nhận URL đúng**, nhưng báo lỗi kết nối thay vì lỗi feature.

```java
import java.sql.*;
import java.util.Properties;
import java.util.logging.Logger;

public final class ConnectFailureDemo {
 static final class BrokenDriver implements Driver {
   public boolean acceptsURL(String url) {
     return url!=null &&
         url.startsWith("jdbc:brokenlab:");
   }

   public Connection connect(String url,Properties props)
       throws SQLException {
     if(!acceptsURL(url))return null;
     throw new SQLNonTransientConnectionException(
         "mock network unavailable","08001");
   }

   public DriverPropertyInfo[] getPropertyInfo(
       String url,Properties props) {
     return new DriverPropertyInfo[0];
   }
   public int getMajorVersion(){return 1;}
   public int getMinorVersion(){return 0;}
   public boolean jdbcCompliant(){return false;}
   public Logger getParentLogger(){
     return Logger.getLogger("jdbc.brokenlab");
   }
 }

 public static void main(String[] args)throws Exception {
   BrokenDriver d=new BrokenDriver();
   DriverManager.registerDriver(d);
   boolean connectionFailure=false,featureFailure=false;
   try {
     try {
       DriverManager.getConnection(
           "jdbc:brokenlab:test");
     }catch(SQLException e){
       connectionFailure=
           e instanceof SQLNonTransientConnectionException;
       featureFailure=
           e instanceof SQLFeatureNotSupportedException;
     }
   }finally{
     DriverManager.deregisterDriver(d);
   }
   System.out.println("connectionFailure="+
       connectionFailure);
   System.out.println("featureUnsupported="+
       featureFailure);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConnectFailureDemo.java
java ConnectFailureDemo
```

**Stdout đã kiểm thử:**

```text
connectionFailure=true
featureUnsupported=false
```

Đây là mock cố tình ném lỗi kết nối `08001`. Không phải một lần thử kết nối network; không có server database thật. Nó minh họa lý do **hai nhóm lỗi cần hai runbook khác nhau**.

## 16. DatabaseMetaData: capability của driver và DB

`Connection.getMetaData()` trả `DatabaseMetaData`, cho phép đọc thông tin về driver/DB và một số feature:

```java
DatabaseMetaData meta = connection.getMetaData();
String driver = meta.getDriverName();
String version = meta.getDriverVersion();
int major = meta.getJDBCMajorVersion();
boolean batch = meta.supportsBatchUpdates();
boolean generatedKeys = meta.supportsGetGeneratedKeys();
```

Đây là **mảnh minh họa**: cần Connection đang mở và có thể ném SQLException.

Một số useful methods:

| Metadata method | Ý nghĩa |
| --- | --- |
| `getDriverName()` | Tên driver |
| `getDriverVersion()` | Version driver |
| `getDriverMajorVersion()` / `getDriverMinorVersion()` | Driver version components |
| `getJDBCMajorVersion()` / `getJDBCMinorVersion()` | JDBC spec version driver báo |
| `getDatabaseProductName()` | DBMS product |
| `getDatabaseProductVersion()` | DBMS version |
| `supportsBatchUpdates()` | Batch updates capability |
| `supportsGetGeneratedKeys()` | Generated keys capability |
| `supportsTransactions()` | Transactions capability |
| `supportsResultSetType(int type)` | Result set type capability |
| `supportsResultSetConcurrency(type, concurrency)` | Result-set concurrency mode capability |

### 16.1. Metadata là tín hiệu, không phải toàn bộ hợp đồng

- `supportsBatchUpdates() == true` không bảo đảm mọi statement/batch SQL hợp lệ trên mọi schema.
- `getJDBCMajorVersion()==4` không bảo đảm **mọi** method/overload của JDBC 4.x được driver triển khai.
- Một feature có thể phụ thuộc SQL dialect, server config, privileges hoặc data types.
- Driver có bug hoặc reports không chính xác; hãy test trên DB mục tiêu.
- Không có flag metadata tương ứng cho **mọi** overload JDBC.
- Capability checks và actual operation có thể xảy ra trong những trạng thái khác nhau; vẫn phải bắt SQLException.

## 17. Chương trình H — MetadataCapabilitiesDemo.java

Mock metadata trả capability values cố định; **không phải nhận định một DB vendor thật**.

```java
import java.sql.*;
import java.lang.reflect.*;

public final class MetadataCapabilitiesDemo {
 public static void main(String[] args)throws Exception {
   DatabaseMetaData meta=(DatabaseMetaData)
     Proxy.newProxyInstance(
       DatabaseMetaData.class.getClassLoader(),
       new Class<?>[]{DatabaseMetaData.class},
       (p,m,a)->{
         switch(m.getName()){
           case "getDriverName":return "DemoDriver";
           case "getDriverVersion":return "1.2.3";
           case "getDatabaseProductName":return "MockDB";
           case "getJDBCMajorVersion":return 4;
           case "getJDBCMinorVersion":return 3;
           case "supportsBatchUpdates":return false;
           case "supportsGetGeneratedKeys":return false;
           case "supportsTransactions":return true;
           default:throw new SQLFeatureNotSupportedException(
               "mock missing "+m.getName(),"0A000");
         }
       });

   System.out.println("driver="+
       meta.getDriverName());
   System.out.println("jdbcVersion="+
       meta.getJDBCMajorVersion()+"."+
       meta.getJDBCMinorVersion());
   System.out.println("batchSupported="+
       meta.supportsBatchUpdates());
   System.out.println("generatedKeysSupported="+
       meta.supportsGetGeneratedKeys());
   System.out.println("transactionsSupported="+
       meta.supportsTransactions());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MetadataCapabilitiesDemo.java
java MetadataCapabilitiesDemo
```

**Stdout đã kiểm thử:**

```text
driver=DemoDriver
jdbcVersion=4.3
batchSupported=false
generatedKeysSupported=false
transactionsSupported=true
```

Demo chỉ trả metadata từ Proxy. **Không** suy ra PostgreSQL/MySQL/Oracle/SQL Server có capability giống những giá trị này. Cần chạy integration tests với **driver jar và DBMS thật** mới đánh giá portability.

## 18. Kế hoạch fallback: luôn xác định mục đích trước

Khi gặp `SQLFeatureNotSupportedException`, câu hỏi quan trọng nhất:

**Tính năng đó có bắt buộc cho correctness/bảo mật không, hay chỉ là tối ưu hóa/biểu diễn khác?**

### 18.1. Nếu feature chỉ là tối ưu hóa

Ví dụ:
- Batch updates chưa hỗ trợ, nhưng các thao tác `executeUpdate` đơn lẻ tương đương và transaction policy cho phép.
- Một typed getter chưa hỗ trợ, nhưng getter loại DATE chuẩn trả được cùng giá trị theo schema.
- Một tùy chọn hiệu năng/metadata không cần thiết có fallback documented.

Có thể làm fallback **khi chưa bắt đầu side effects**, hoặc với read-only operation an toàn và well-defined mapping.

### 18.2. Nếu feature cần cho correctness

Ví dụ:
- Ứng dụng cần chọn **tenant schema** để bảo đảm isolation.
- Cần enforce transaction isolation/rollback behavior.
- Cần network timeout bắt buộc để kiểm soát liveness.
- Cần key retrieval có thể xác định đúng entity.
- Cần generated keys cho foreign key setup trong cùng transaction.

Khi driver không hỗ trợ, **fail closed** hoặc thay driver/DB/config; **không silent ignore** và tiếp tục như thể operation đã thành công.

### 18.3. Không fallback bằng cách lặp lại INSERT

Nếu câu lệnh `INSERT` có thể đã commit, rồi `getGeneratedKeys()` không được hỗ trợ, việc “fallback” bằng **INSERT lại** để lấy key có thể tạo duplicate. Không được làm.

### 18.4. Fallback SQL dialect phải được kiểm chứng

`INSERT ... RETURNING ...`, vendor-specific functions và generated-key retrieval khác nhau giữa DBMS. Nếu dùng một đường thay thế, chọn nó **trước khi ghi**, tham số hóa query và test với DB mục tiêu; không ghép SQL từ user input.

## 19. Fallback an toàn cho đọc dữ liệu: getObject(type) → getDate

Một số drivers/DBMS có thể chưa hỗ trợ một overload typed `ResultSet.getObject(column, LocalDate.class)`.

Nếu column theo schema chắc chắn là **SQL DATE** và `ResultSet.getDate` được hỗ trợ, có thể fallback sang:

```java
java.sql.Date sqlDate = resultSet.getDate("created_on");
LocalDate value =
    (sqlDate == null) ? null : sqlDate.toLocalDate();
```

Đây là mảnh minh họa. `getDate` và `toLocalDate` phù hợp cho **SQL DATE**, không mặc định cho TIMESTAMP, TIMESTAMP WITH TIME ZONE hay mọi kiểu JDBC khác.

### 19.1. Chỉ catch subtype phù hợp

```java
try {
    return rs.getObject(column, LocalDate.class);
} catch (SQLFeatureNotSupportedException unsupported) {
    Date d=rs.getDate(column);
    return d==null ? null : d.toLocalDate();
}
```

Đây là **mảnh minh họa** (trong method trả LocalDate và có `throws SQLException`). **Không** catch mọi `SQLException` rồi fallback, bởi lỗi permissions, disconnect, invalid column, conversion hoặc SQL syntax có thể cần được report/handled khác.

## 20. Chương trình I — DateGetterFallbackDemo.java

```java
import java.sql.*;
import java.lang.reflect.*;
import java.time.LocalDate;

public final class DateGetterFallbackDemo {
 static LocalDate getDateValue(ResultSet rs,String column)
     throws SQLException {
   try {
     return rs.getObject(column,LocalDate.class);
   } catch(SQLFeatureNotSupportedException unsupported) {
     Date date=rs.getDate(column);
     return date==null?null:date.toLocalDate();
   }
 }

 public static void main(String[] args)throws Exception {
   ResultSet rs=(ResultSet)Proxy.newProxyInstance(
       ResultSet.class.getClassLoader(),
       new Class<?>[]{ResultSet.class},
       (p,m,a)->{
         if(m.getName().equals("getObject")&&a.length==2)
           throw new SQLFeatureNotSupportedException(
               "typed getObject unsupported","0A000");
         if(m.getName().equals("getDate"))
           return Date.valueOf("2026-11-04");
         if(m.getName().equals("close"))return null;
         throw new SQLException(
             "Unexpected method: "+m.getName());
       });

   try(rs) {
     System.out.println("fallbackLocalDate="+
         getDateValue(rs,"created_on"));
     System.out.println(
         "readOnlyFallbackNoDuplicateWrite=true");
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DateGetterFallbackDemo.java
java DateGetterFallbackDemo
```

**Stdout đã kiểm thử:**

```text
fallbackLocalDate=2026-11-04
readOnlyFallbackNoDuplicateWrite=true
```

**Lợi ích:** Đây là một read-only conversion từ SQL DATE nên không có INSERT/UPDATE/DELETE phải chạy lại. **Giới hạn:** Mock không kiểm được mọi driver/date/time-zone behavior. Khi dùng DB thật, xác minh schema, nulls, daylight/time zone policy và JDBC mapping.

## 21. Batch updates: chọn capability trước khi gửi writes

`DatabaseMetaData.supportsBatchUpdates()` cho biết driver/DBMS báo có hỗ trợ batch update hay không. Khi false, application có thể chọn chạy **từng statement riêng** trong transaction thay vì gọi `addBatch/executeBatch`.

**Điểm an toàn:** Chọn đường xử lý **trước những writes đầu tiên**.

```text
             metadata.supportsBatchUpdates()
                         |
               +---------+---------+
               |                   |
              true                false
               |                   |
        addBatch/executeBatch   executeUpdate each
               |                   |
        handle BatchUpdateException + outcomes
                         |
              commit only after success
```

Nếu metadata true nhưng `addBatch`/`executeBatch` vẫn gặp unsupported/exception:
- Không tự rerun toàn bộ batch.
- Có thể một phần batch đã được thực thi (tùy driver/transaction).
- Xem `BatchUpdateException.getUpdateCounts()` khi gặp batch failure.
- Rollback nếu transaction hỗ trợ và operation được kiểm soát.
- Retry chỉ sau khi biết transaction outcome và idempotency.

Không dùng `supportsBatchUpdates()==false` để kết luận **DB không hỗ trợ mọi updates**, chỉ không thể sử dụng JDBC batch route ấy theo metadata.

## 22. Chương trình J — BatchFeatureDecisionDemo.java

Mock metadata báo không hỗ trợ batch, nên gọi `executeUpdate()` hai lần thay vì gọi `addBatch`. Test không truy cập DB, chỉ đếm số lời gọi.

```java
import java.sql.*;
import java.lang.reflect.*;
import java.util.concurrent.atomic.*;

public final class BatchFeatureDecisionDemo {
 public static void main(String[] args)throws Exception {
   AtomicInteger updates=new AtomicInteger();
   AtomicInteger batches=new AtomicInteger();

   DatabaseMetaData m=(DatabaseMetaData)
     Proxy.newProxyInstance(
       DatabaseMetaData.class.getClassLoader(),
       new Class<?>[]{DatabaseMetaData.class},
       (p,method,a)->{
         if(method.getName().equals(
             "supportsBatchUpdates"))return false;
         throw new SQLException(
             "unexpected metadata request");
       });

   PreparedStatement ps=(PreparedStatement)
     Proxy.newProxyInstance(
       PreparedStatement.class.getClassLoader(),
       new Class<?>[]{PreparedStatement.class},
       (p,method,a)->{
         switch(method.getName()){
           case "setInt":return null;
           case "executeUpdate":
             updates.incrementAndGet();return 1;
           case "addBatch":
             batches.incrementAndGet();
             throw new SQLFeatureNotSupportedException(
                 "no batch","0A000");
           case "close":return null;
           default:throw new SQLException(
               "unexpected "+method.getName());
         }
       });

   boolean batch=m.supportsBatchUpdates();
   try(ps) {
     if(batch) {
       for(int id=1;id<=2;id++){
         ps.setInt(1,id);
         ps.addBatch();
       }
       ps.executeBatch();
     }else{
       for(int id=1;id<=2;id++){
         ps.setInt(1,id);
         ps.executeUpdate();
       }
     }
   }

   System.out.println("batchSupported="+batch);
   System.out.println("individualUpdates="+updates.get());
   System.out.println("addBatchCalls="+batches.get());
   System.out.println("eachWriteExecutedOnce=true");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BatchFeatureDecisionDemo.java
java BatchFeatureDecisionDemo
```

**Stdout đã kiểm thử:**

```text
batchSupported=false
individualUpdates=2
addBatchCalls=0
eachWriteExecutedOnce=true
```

### 22.1. Quan trọng trong DB thật

Mock `PreparedStatement` không gửi SQL. Production nên:
1. Lấy Connection hợp lệ.
2. Kiểm `supportsBatchUpdates` (khi cần route này).
3. Chuẩn bị `PreparedStatement` với SQL tham số hóa.
4. Chọn batch hay single writes.
5. Quản lý transaction/commit/rollback và exceptions.
6. Đảm bảo không chạy lại operation đã commit mơ hồ.

Tuyệt đối không suy “hai method calls” trong mock đã chứng minh atomicity của một DB thật.

## 23. Khi fallback phải fail closed: tenant isolation

Giả sử ứng dụng dùng `Connection.setSchema("tenant_a")` để cô lập dữ liệu tenant. Nếu driver ném `SQLFeatureNotSupportedException`, việc bỏ qua và chạy SQL ở schema mặc định có thể gây **cross-tenant data access**.

**Quy tắc:** Khi một feature là điều kiện bảo mật/correctness, không fallback bằng “ignore error”. Thay vào đó:
- Chuyển sang đường truy vấn có schema-qualified SQL đã được review, hoặc
- Dùng configuration/driver được hỗ trợ, hoặc
- **Từ chối operation**.

Không bắt `SQLException` chung rồi silently continue.

## 24. Chương trình K — FailClosedSchemaDemo.java

```java
import java.sql.*;
import java.lang.reflect.*;

public final class FailClosedSchemaDemo {
 static void requireSchema(Connection c,String schema)
     throws SQLException {
   try {
     c.setSchema(schema);
   }catch(SQLFeatureNotSupportedException e){
     throw new SQLException(
         "Tenant schema isolation unavailable",
         "0A000",e);
   }
 }

 public static void main(String[] args)throws Exception {
   Connection c=(Connection)Proxy.newProxyInstance(
       Connection.class.getClassLoader(),
       new Class<?>[]{Connection.class},
       (p,m,a)->{
         if(m.getName().equals("setSchema"))
           throw new SQLFeatureNotSupportedException(
               "setSchema unsupported","0A000");
         if(m.getName().equals("close"))return null;
         throw new SQLException(
             "unexpected "+m.getName());
       });

   boolean refused=false,hasCause=false;
   try(c) {
     requireSchema(c,"tenant_a");
   }catch(SQLException e){
     refused=true;
     hasCause=e.getCause()
         instanceof SQLFeatureNotSupportedException;
   }
   System.out.println(
       "tenantOperationRefused="+refused);
   System.out.println(
       "originalCausePreserved="+hasCause);
   System.out.println(
       "unsafeIgnoreFeature=false");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FailClosedSchemaDemo.java
java FailClosedSchemaDemo
```

**Stdout đã kiểm thử:**

```text
tenantOperationRefused=true
originalCausePreserved=true
unsafeIgnoreFeature=false
```

**Ý nghĩa:** Thay vì truy cập tenant mặc định khi `setSchema` không hỗ trợ, code từ chối operation và giữ original cause. Đây là một ví dụ fail-closed đúng. Production phải review cả SQL qualification, permission model và connection-pool schema reset, không chỉ một method.

## 25. Xử lý transaction khi feature không hỗ trợ

`Connection` thường bắt đầu ở auto-commit mode. Khi một transaction gồm nhiều operations, application có thể gọi `setAutoCommit(false)`, thực thi statements, `commit()` sau khi thành công hoặc `rollback()` nếu lỗi.

Nếu một optional method ném `SQLFeatureNotSupportedException` trong transaction:

1. Không bỏ qua lỗi rồi commit phần còn lại.
2. Cố rollback khi connection/DB hỗ trợ và transaction còn hợp lệ.
3. Giữ **original SQLException**; nếu rollback thất bại, gắn lỗi rollback bằng `addSuppressed`.
4. Đóng Connection/Statements/ResultSets với try-with-resources.
5. Nếu trạng thái commit không chắc chắn (network failure), cần reconciliation/idempotency trước retry.
6. Driver/cơ sở dữ liệu không có transactions cần strategy khác; không gọi rollback là phép màu.

### 25.1. Template giao dịch (mảnh minh họa)

```java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);
    try {
        // Execute parameterized SQL and verify results.
        c.commit();
    } catch (SQLException failure) {
        try {
            c.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đây là **mảnh minh họa**, cần `DataSource dataSource` đã được cấu hình. Production còn phải xử lý exceptions không phải SQLException, chọn isolation level, deadline và restore connection state nếu có yêu cầu của pool. Một số DB/driver có transaction restrictions hoặc DDL implicit commits; test thật là bắt buộc.

## 26. Chương trình L — TransactionRollbackDemo.java

Mock Connection kiểm thứ tự: feature bị từ chối → gọi rollback đúng một lần → không commit → connection đóng.

```java
import java.sql.*;
import java.lang.reflect.*;
import java.util.concurrent.atomic.*;

public final class TransactionRollbackDemo {
 public static void main(String[] args)throws Exception {
   AtomicBoolean closed=new AtomicBoolean();
   AtomicInteger rollback=new AtomicInteger();
   AtomicInteger commit=new AtomicInteger();

   Connection c=(Connection)Proxy.newProxyInstance(
     Connection.class.getClassLoader(),
     new Class<?>[]{Connection.class},
     (p,m,a)->{
       switch(m.getName()){
         case "setAutoCommit":return null;
         case "createArrayOf":
           throw new SQLFeatureNotSupportedException(
               "arrays unsupported","0A000");
         case "rollback":
           rollback.incrementAndGet();return null;
         case "commit":
           commit.incrementAndGet();return null;
         case "close":
           closed.set(true);return null;
         default:
           throw new SQLException(
               "unexpected "+m.getName());
       }
     });

   boolean unsupportedCaught=false;
   try(Connection conn=c) {
     conn.setAutoCommit(false);
     try {
       conn.createArrayOf(
           "INTEGER",new Object[]{1,2});
       conn.commit();
     }catch(SQLException failure){
       try {
         conn.rollback();
       }catch(SQLException rollbackFailure){
         failure.addSuppressed(rollbackFailure);
       }
       throw failure;
     }
   }catch(SQLFeatureNotSupportedException expected){
     unsupportedCaught=true;
   }

   System.out.println("unsupportedCaught="+
       unsupportedCaught);
   System.out.println("rollbackCalls="+
       rollback.get());
   System.out.println("commitCalls="+commit.get());
   System.out.println("connectionClosed="+
       closed.get());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TransactionRollbackDemo.java
java TransactionRollbackDemo
```

**Stdout đã kiểm thử:**

```text
unsupportedCaught=true
rollbackCalls=1
commitCalls=0
connectionClosed=true
```

**Giới hạn:** Proxy chỉ ghi nhận method calls; đây **không phải bằng chứng** rollback trên một DB thật là atomic hoặc không có implicit commits. Ở integration test phải có bảng dữ liệu, transaction boundaries và assertions xác minh không có partial writes.

## 27. Try-with-resources và JDBC AutoCloseable

`Connection`, `Statement`, `PreparedStatement`, `ResultSet` đều có lifecycle và hỗ trợ cleanup qua try-with-resources trên Java hiện hành. Đây là tính năng có từ Java 7 vẫn rất quan trọng.

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
         "SELECT id FROM users WHERE email = ?")) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
            // Consume id.
        }
    }
}
```

Đây là mảnh minh họa: `dataSource`, `email` và schema `users` phải có trong ứng dụng thực. SQL dùng placeholder `?` và `setString` để tránh nối input vào query. Không dùng đoạn này trong demo không có database.

### 27.1. Catch bên ngoài try-with-resources

Khi exception xảy ra trong body, try-with-resources sẽ đóng resources. Nếu close cũng lỗi, Java có thể gắn close failure trong `getSuppressed()`. Đừng đặt catch `SQLFeatureNotSupportedException` rồi quên cleanup.

### 27.2. Connection pool và try-with-resources

Khi lấy Connection từ pooled DataSource, `close()` thường trả logical connection về pool. Vẫn bắt buộc close handle theo contract để tránh pool exhaustion; không tự cố đóng underlying physical connection.

## 28. Chương trình M — ConnectionCleanupDemo.java

```java
import java.sql.*;
import java.lang.reflect.*;
import java.util.concurrent.atomic.*;

public final class ConnectionCleanupDemo {
 public static void main(String[] args)throws Exception {
   AtomicBoolean closed=new AtomicBoolean();
   AtomicBoolean caught=new AtomicBoolean();

   Connection c=(Connection)Proxy.newProxyInstance(
     Connection.class.getClassLoader(),
     new Class<?>[]{Connection.class},
     (p,m,a)->{
       if(m.getName().equals("close")){
         closed.set(true);return null;
       }
       if(m.getName().equals("createClob"))
         throw new SQLFeatureNotSupportedException(
             "clob unsupported","0A000");
       throw new SQLException(
           "unexpected "+m.getName());
     });

   try(Connection use=c) {
     use.createClob();
   }catch(SQLFeatureNotSupportedException expected){
     caught.set(true);
   }
   System.out.println("featureCaught="+
       caught.get());
   System.out.println(
       "connectionClosedByTryWithResources="+
       closed.get());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConnectionCleanupDemo.java
java ConnectionCleanupDemo
```

**Stdout đã kiểm thử:**

```text
featureCaught=true
connectionClosedByTryWithResources=true
```

Một unsupported operation không làm bạn được phép bỏ cleanup. Demo xác nhận try-with-resources đóng Connection giả lập dù body ném `SQLFeatureNotSupportedException`.

## 29. Không có cùng cách fallback cho mọi optional feature

Một vài trường hợp cần các chính sách khác nhau:

| Tính năng | Fallback có thể xem xét | Rủi ro / điều kiện |
| --- | --- | --- |
| `ResultSet.getObject(col,LocalDate.class)` | `getDate(col).toLocalDate()` | Chỉ với SQL DATE đúng mapping |
| JDBC batch updates | Single prepared updates | Chọn trước write; transaction/partial updates |
| `getGeneratedKeys` | Dialect-specific RETURNING/sequence strategy | Phải chọn trước INSERT; không duplicate |
| `Connection.createArrayOf` | Vetted SQL/query strategy không cần array | Đảm bảo parameterization, giới hạn IN, types |
| Scrollable ResultSet | Forward-only iteration | Không dùng code cần seek/backward |
| Updatable ResultSet | Separate parameterized UPDATE | Concurrency control, row identity, optimistic locking |
| `Connection.setSchema` | Schema-qualified SQL hoặc fail | Không được bỏ qua tenant isolation |
| `Connection.setNetworkTimeout` | Pool/driver-specific network-timeout config | Timeout là liveness/security requirement; kiểm policy |
| `Statement.getGeneratedKeys` | Fail-fast nếu key bắt buộc | Không lặp INSERT sau hiệu ứng không rõ |
| Unsupported transaction mode | Driver/DB upgrade, architecture change | Không bỏ qua atomicity yêu cầu |
| Vendor extension | Standard JDBC alternative nếu đủ semantics | Không dựa vào class vendor đặc thù mọi DB |

### 29.1. Fallback phải bảo toàn semantics

Một phép chuyển từ typed getter sang getter cơ bản thường không có side effects. Một phép chuyển từ “INSERT with generated key” sang “INSERT không key rồi SELECT MAX(id)” **không an toàn dưới concurrency**; không dạy workaround như vậy.

### 29.2. Unsupported từ driver có thể là contract quan trọng

Khi feature bắt buộc cho tính toàn vẹn, error nên dẫn tới **configuration failure**, chứ không phải “best effort continue”. Một số chức năng như auditing/tenant boundaries nên fail closed.

## 30. Chẩn đoán driver/version theo một quy trình

Khi báo cáo `SQLFeatureNotSupportedException` ở production:

1. Ghi **operation** nào bị từ chối (method + overload/mode/argument class).
2. Ghi exception type, SQLState (có thể null), vendor code và next/cause chains.
3. Ghi driver name/version, JDBC spec version và DB product/version từ `DatabaseMetaData` khi có Connection.
4. Xác nhận DB server version và driver jar/runtime classpath chính xác.
5. Kiểm release notes và vendor support matrix cho feature.
6. Chạy reproduction tối thiểu với **driver/DB thật** thay vì chỉ mock.
7. Thử metadata supports flag tương ứng nếu có.
8. Quyết định: nâng driver/server, thay API, dùng vetted fallback hay fail-fast.
9. Viết integration test đối với driver/DB combinations được hỗ trợ.
10. Deploy theo canary/observability, kiểm outcome của transactions.

### 30.1. Những trường thông tin hữu ích

```text
javaRuntime=17.x
operation=Connection.createArrayOf
driverName=<driver>
driverVersion=<version>
databaseProduct=<dbms>
databaseVersion=<version>
jdbcVersion=<major.minor>
exceptionClass=SQLFeatureNotSupportedException
sqlState=0A000 (or null)
vendorCode=<vendor specific>
fallbackPolicy=READ_ONLY_ALLOWED | FAIL_CLOSED | CONFIG_UNSUPPORTED
```

Đây là **mẫu log minh họa**, không phải output một chương trình. Không log credentials, tokens, raw sensitive SQL parameters hay schema secrets.

### 30.2. Driver/server compatibility là một ma trận

Test combinations:
- Java runtime version.
- Driver artifact/version.
- DBMS name/version.
- Operating system/container image nếu driver có dependencies đặc biệt.
- TLS/protocol/auth configuration.
- JDBC feature + overload + mode.
- Transaction isolation/auto-commit.
- Connection pooling implementation nếu có.

Một test trên DB in-memory khác **không chứng minh** JDBC features chạy trên production DBMS.

## 31. Tính ổn định API và những giới hạn đặc biệt

### 31.1. Interface method tồn tại không đảm bảo driver đã triển khai

`Connection` trên Java 17 có methods như `createArrayOf`, `setSchema`, `setNetworkTimeout`. Một driver cũ hoặc không hoàn chỉnh có thể ném unsupported cho một số optional features.

### 31.2. getJDBCMajorVersion không quyết định toàn bộ

Driver báo JDBC 4.3 không đảm bảo mọi optional method hỗ trợ. Metadata hỗ trợ được áp dụng cho driver **kết hợp với** database server thực tế.

### 31.3. getParentLogger cũng có thể không hỗ trợ

`Driver.getParentLogger()` có thể ném `SQLFeatureNotSupportedException` theo API. Đó là vấn đề hỗ trợ logging, **không đồng nghĩa** connection phải thất bại, và cũng không phải lý do fallback sang driver không đáng tin.

### 31.4. Multi-classloader, service providers

Driver discovery có thể phụ thuộc context classloader mà `DriverManager` khởi tạo. Trong fat jar, app server, plugin-based runtimes hoặc JPMS, cần kiểm service-provider resource/`provides java.sql.Driver` module declaration và driver visibility. Không xử lý bằng cách tự bật illegal reflective access vào JDK.

### 31.5. Wrapper và vendor-specific interfaces

`Connection.unwrap(Class<T>)`/`isWrapperFor(Class<?>)` cho phép truy cập API vendor trong trường hợp được hỗ trợ. Điều đó làm ứng dụng kém portable; cần feature flag/adapter, document dependency và fallback. `unwrap` không đảm bảo thành công hoặc đúng driver vendor.

## 32. Kiến trúc adapter cho đa cơ sở dữ liệu

Khi ứng dụng hỗ trợ nhiều driver, tránh dàn trải `catch(SQLFeatureNotSupportedException)` ở mọi DAO.

Một hướng thiết kế:

```text
Business Service
    |
Repository Interface
    |
Dialect/Capability Adapter
    +--- Standard JDBC strategy
    +--- DB-A validated capability strategy
    +--- DB-B validated capability strategy
    |
Connection/DataSource
    |
JDBC Driver / DBMS
```

Adapter có thể:
- Đọc metadata tại startup.
- Kiểm feature cần thiết trước khi mở lưu lượng.
- Chọn SQL dialect/parameter binding policy.
- Có một nơi tập trung handling SQLExceptions.
- Định nghĩa rõ **features bắt buộc** và **optional enhancements**.
- Test against actual DBMS và run integration test khi driver version thay đổi.

### 32.1. Không cache capability mù quáng cho mọi môi trường

Một driver/version có thể kết nối nhiều database có capabilities khác nhau. Cache capability theo đúng datasource/configuration/DB; đừng dùng một static Boolean global cho mọi tenant/DB backend.

### 32.2. Startup fail-fast khi feature thiết yếu không có

Nếu tenancy hoặc transaction correctness đòi capability nhất định, một health/startup check nên phát hiện sớm và đưa ra lỗi cấu hình có thể hành động. Tắt feature quan trọng để “cho app lên” có thể tạo data corruption/security risk.

## 33. Unit tests với mock và integration tests với driver thật

Mock driver/Proxy giúp test:
- Đúng class exception được catch.
- Không catch quá rộng.
- Rollback path được gọi khi unsupported.
- Connection luôn close.
- Metadata điều khiển route lựa chọn.
- Không chạy lại side-effecting writes trong fallback.
- Logging chain/cause/suppressed.

Nhưng **mock không thể chứng minh**:
- Driver thật có hỗ trợ phương thức hay không.
- DB transactional atomicity.
- SQL dialect tương thích.
- Network/TLS/auth behavior.
- Generated keys/arrays đúng type.
- Pooling/schema reset behavior.
- Real JDBC metadata trung thực.
- Durability/serialization/isolation.

### 33.1. Phân loại tests thực tế

| Test | Mục đích |
| --- | --- |
| Compile Java 17 API | Code dùng các methods có mặt trên Java 17 |
| Unit mock Driver | Kiểm xử lý exception/capability/cleanup |
| Integration test DB mục tiêu | Xác nhận driver, SQL, transaction và type mappings thật |
| Migration test | Kiểm thay đổi khi nâng driver/server |
| Failure injection | Timeout, network reset, permissions, unsupported mode |
| Security test | Tenant isolation fail-closed, no credentials/log leaks |
| Production canary | Phát hiện regression/metadata differences sớm |

Không dùng H2 hoặc DB in-memory như phép kiểm duy nhất cho một DBMS khác nếu feature phụ thuộc dialect/provider.

## 34. Runbook khi nhận lỗi unsupported từ production

**Bước 1 — Phân loại:** Dùng class, SQLState group 0A, vendor docs. Nếu lỗi `SQLException` chung, kiểm cause/next chain. Nếu lỗi credential/network, đi runbook kết nối thay vì optional feature.

**Bước 2 — Đánh giá impact:** Operation chỉ đọc/optional hay chứa DML, transaction, tenant isolation, auditing?

**Bước 3 — Chặn rủi ro:** Nếu tính năng bắt buộc và fallback không chứng minh tương đương, fail closed; không tiếp tục ghi dữ liệu.

**Bước 4 — Chẩn đoán:** Xác minh driver jar đã đóng gói, version, URL, metadata, server version, service-provider/classloader.

**Bước 5 — Chọn giải pháp:** Driver/server upgrade, supported SQL strategy, alternate JDBC method hoặc fail-fast cho feature không có.

**Bước 6 — Kiểm thử:** Unit mock + integration DB/driver thật, transaction rollback/retry và concurrency.

**Bước 7 — Deploy:** Có metrics theo exception class/sqlState/driver version, redaction secrets, canary.

## 35. Những lỗi thường gặp

1. Nghĩ `SQLFeatureNotSupportedException` có nghĩa Java không hỗ trợ JDBC.
2. Cho rằng method có trong Java 17 ⇒ mọi driver phải hỗ trợ.
3. Coi lỗi “No suitable driver” là SQLFeatureNotSupportedException.
4. Coi “server refused connection” là tính năng SQL tùy chọn chưa hỗ trợ.
5. Catch mọi SQLException rồi giả định tất cả do unsupported.
6. Retry liên tục một SQLFeatureNotSupportedException.
7. Chờ vài giây để feature không tồn tại “tự hồi phục”.
8. Nhận diện mã SQLState bằng `e.getSQLState().equals("0A000")` mà không kiểm null.
9. Cho rằng exception class luôn tự gắn SQLState `0A000`.
10. Chỉ log message, bỏ SQLState/errorCode/next exceptions.
11. Bỏ suppressed rollback/close exceptions.
12. Tự nối SQL với user input khi fallback khỏi một API không hỗ trợ.
13. Retry INSERT sau `getGeneratedKeys()` thất bại, gây duplicate.
14. Dùng `SELECT MAX(id)` để lấy khóa vừa insert dưới concurrency.
15. Bỏ qua `Connection.setSchema` unsupported rồi truy cập schema mặc định.
16. Bỏ qua `setNetworkTimeout` dù timeout là yêu cầu vận hành.
17. Coi metadata supports flag true là bảo đảm mọi overload/mode đều được hỗ trợ.
18. Coi JDBC version 4.x là bảo đảm không có optional unsupported methods.
19. Không kiểm transaction outcomes khi fallback batch/single.
20. Xử lý `BatchUpdateException` mà bỏ qua partial update counts.
21. Không rollback khi transaction operation thất bại.
22. Tự retry DML khi không biết transaction đã commit chưa.
23. Không đóng Connection/PreparedStatement/ResultSet.
24. Coi `close()` trên pooled Connection là đóng socket vật lý luôn.
25. Hardcode credentials trong Java source.
26. In connection URL có password vào logs.
27. Dùng driver jar chỉ có trên compile/test classpath, không có runtime.
28. Shade jar làm mất service-provider registration.
29. Dùng `Class.forName` như bắt buộc cho mọi JDBC 4.x driver.
30. Dựa vào tên driver cố định trong vendor-neutral code.
31. Không kiểm DB server version/dialect.
32. Thử DB in-memory rồi suy production DBMS cũng hỗ trợ feature tương tự.
33. Cache capability theo một static flag dùng chung cho mọi DB backend.
34. Coi SQLState message ở mock là mã bắt buộc của một driver vendor.
35. Tự viết production JDBC driver bằng Proxy.
36. Tự dùng reflection vào driver internals để bật tính năng unsupported.
37. Không kiểm generated keys đã được retrieve/associated đúng row.
38. Coi lỗi timeout chắc chắn transaction chưa được thực thi.
39. Tự đổi driver jar trong prod mà không integration test.
40. Silent fallback đổi nghĩa SQL/transaction/bảo mật.

## 36. Câu hỏi và đáp án

**1.** `SQLFeatureNotSupportedException` kế thừa từ đâu? **`SQLNonTransientException` → `SQLException`**.

**2.** SQLState class “0A” biểu thị gì? **Optional feature not supported**.

**3.** Constructor chỉ có reason có tự đặt SQLState 0A000 không? **Không, SQLState có thể null**.

**4.** `SQLFeatureNotSupportedException` có luôn retry được nếu chờ lâu? **Không**.

**5.** “No suitable driver” chứng minh method JDBC chưa hỗ trợ? **Không**, đó là vấn đề driver availability/URL.

**6.** Driver jar có nhất thiết được JDK cung cấp cho mọi DB? **Không**, phải mang driver tương thích.

**7.** Modern JDBC 4.x driver có thường auto-discovered không? **Có qua service-provider khi dependency/classloader đúng**.

**8.** Có nên bắt buộc `Class.forName` cho mọi driver? **Không**.

**9.** DataSource hay DriverManager thường ưu tiên cho production? **`DataSource`**.

**10.** `DatabaseMetaData` mô tả capability của ai? **Driver và DBMS cùng nhau**.

**11.** `supportsBatchUpdates()==false` có nghĩa DB không làm được UPDATE? **Không**, chỉ không có JDBC batch capability theo metadata.

**12.** `supportsBatchUpdates()==true` bảo đảm mọi batch SQL thành công? **Không**.

**13.** Cần gì khi fallback từ batch sang single updates? **Chọn trước side effects; transaction và outcome checks**.

**14.** `getGeneratedKeys` không hỗ trợ sau INSERT, có nên INSERT lại? **Không**.

**15.** SQL DATE typed getObject không hỗ trợ, có thể fallback? **Có nếu column là SQL DATE và `getDate.toLocalDate` giữ đúng semantics**.

**16.** Có thể catch mọi SQLException rồi gọi getDate fallback không? **Không**, che lỗi khác.

**17.** `Connection.setSchema` không hỗ trợ với tenant isolation thì sao? **Fail closed hoặc dùng chiến lược tương đương đã review**.

**18.** Dùng try-with-resources có cần đóng Connection thủ công ở cuối body không? **Không, cơ chế close tự động ở scope exit**.

**19.** `Connection.close` pooled connection có thể trả handle về pool không? **Có**.

**20.** SQLTransientException luôn an toàn retry INSERT? **Không**, còn transaction/idempotency/outcome**.

**21.** `SQLException.getNextException` dùng để làm gì? **Đọc chain errors bổ sung**.

**22.** `Throwable.getSuppressed` thường thấy khi nào? **Close/rollback cleanup trong khi có exception chính**.

**23.** Có thể có SQLState null không? **Có**.

**24.** Có nên log password từ JDBC URL? **Không**.

**25.** Driver version và DBMS version có ảnh hưởng feature support không? **Có**.

**26.** Unit test mock driver đủ chứng minh DB thật transaction atomic? **Không**.

**27.** Connection/network failure có thể thuộc SQLNonTransientConnectionException? **Có**.

**28.** Lỗi syntax SQL nên làm gì? **Sửa câu SQL/dialect, không coi là optional feature failure**.

**29.** `getParentLogger` của Driver có thể ném SQLFeatureNotSupportedException? **Có theo contract**.

**30.** `isWrapperFor`/`unwrap` có tạo portability bảo đảm không? **Không**, vendor-specific features cần adapter**.

**31.** Vì sao schema isolation phải fail-closed? **Tránh truy cập nhầm tenant/database schema**.

**32.** `DriverManager.registerDriver` và `deregisterDriver` dùng khi nào? **Quản lý explicit driver registration; test mock hoặc owner-managed lifecycle**.

**33.** Driver.connect nên làm gì với URL không nhận ra? **Trả null**.

**34.** DriverManager không phù hợp hơn DataSource ở đâu? **Pooling/config/injection và quản lý kết nối production**.

**35.** Có thể xác định feature support chỉ bằng JDBC major version? **Không**.

**36.** `getObject(column,LocalDate.class)` thuộc Java 17 có thể vẫn unsupported? **Có, do driver/type mapping**.

**37.** SQLFeatureNotSupportedException có hỗ trợ getErrorCode? **Có, kế thừa SQLException**.

**38.** DML thất bại sau network timeout có chắc chưa commit? **Không**.

**39.** Cần test gì trước khi đổi JDBC driver? **Compatibility/integration feature/dialect/transaction tests**.

**40.** Nếu fallback không giữ được semantics, nên làm gì? **Fail-fast/fail-closed và yêu cầu driver/DB phù hợp**.

## 37. Checklist trước khi đưa JDBC feature vào production

- [ ] Xác định đúng driver artifact, runtime classpath/module path, URL và server version.
- [ ] Dùng `DataSource`/pooling phù hợp khi ứng dụng có traffic thực.
- [ ] Không dựa vào bắt buộc `Class.forName` cho JDBC 4.x driver hợp chuẩn.
- [ ] Đọc driver và DB metadata khi cần chẩn đoán/capability.
- [ ] Phân loại `SQLFeatureNotSupportedException` riêng với connection/syntax/timeout/constraint errors.
- [ ] Xử lý `getSQLState()==null` an toàn.
- [ ] Ghi vendor code và SQLState khi có.
- [ ] Không dùng error message làm duy nhất cơ chế phân loại.
- [ ] Không retry mù quáng unsupported feature.
- [ ] Kiểm meta supports flag phù hợp; không giả định một flag cho mọi method.
- [ ] Phân biệt optional optimization và required correctness/security feature.
- [ ] Fallback read-only giữ đúng SQL type và null semantics.
- [ ] Fallback writes chỉ sau khi chứng minh idempotency/transaction correctness.
- [ ] Không INSERT lại để lấy generated key.
- [ ] Không dùng SELECT MAX(id) thay generated-key retrieval.
- [ ] Khi cần transaction, rollback trên failure và giữ cause.
- [ ] Nếu rollback/close thất bại, giữ suppressed exceptions.
- [ ] Đóng Connection/Statement/ResultSet với try-with-resources.
- [ ] Không log credentials/raw SQL chứa PII/tokens.
- [ ] Pool connection state được reset theo policy sau transaction/schema changes.
- [ ] Tích hợp driver/DBMS thật trong CI cho các supported combinations.
- [ ] Có migration tests khi nâng driver hoặc server.
- [ ] Không dùng mock test để chứng minh tính năng DB thật.
- [ ] SQL dialect fallback được validate và parameterized.
- [ ] Fail-closed khi tenant isolation/security capability không có.
- [ ] Monitor exception class, SQLState, driver and DB version.
- [ ] Không ghi vào schema sai hoặc bỏ qua lỗi rồi commit.

## 38. Tài liệu chính thức Java SE 17 và JDBC

- [`SQLFeatureNotSupportedException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): class, optional features, SQLState group 0A, constructors.
- [`SQLException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, next exceptions.
- [`SQLNonTransientException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLNonTransientException.html): lý do retry cùng operation không thành công nếu chưa sửa nguyên nhân.
- [`SQLTransientException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTransientException.html): lỗi có thể thành công khi retry trong điều kiện phù hợp.
- [`DriverManager` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DriverManager.html): JDBC drivers, service-provider discovery, getConnection, getDrivers, register/deregister.
- [`Driver` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Driver.html): acceptsURL, connect, getParentLogger.
- [`Connection` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): createArrayOf, setSchema, transactions, cleanup.
- [`DatabaseMetaData` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html): driver/DB capabilities.
- [`ResultSet` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): getObject(type), getDate, type mapping.
- [`Statement` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): generated keys, batch, result-set modes.
- [`PreparedStatement` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): parameterized SQL, batch, typed setters.
- [`BatchUpdateException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html): partial batch outcomes.
- [`DataSource` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html): preferred production connection source.
- [`SQLTimeoutException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTimeoutException.html): timeout semantics.

**Kết luận:** `SQLFeatureNotSupportedException` thông báo JDBC driver/DB không hỗ trợ **một optional feature, overload hoặc mode**, không phải mọi loại SQL error. Trước khi xử lý, phân biệt lỗi driver discovery, lỗi kết nối và lỗi DB. Đọc metadata, driver version, SQLState, vendor code và exception chains, nhưng đừng giả định metadata bao trùm mọi trường hợp. Chỉ fallback khi giữ được semantics; với operations có side effects, tránh duplicate writes bằng transaction/outcome checks; với yêu cầu bảo mật/correctness như tenant schema isolation, **fail closed**. Dùng DataSource/try-with-resources và integration tests với driver + DB thật để xác minh — mock driver chỉ giúp kiểm Java control flow và cleanup.