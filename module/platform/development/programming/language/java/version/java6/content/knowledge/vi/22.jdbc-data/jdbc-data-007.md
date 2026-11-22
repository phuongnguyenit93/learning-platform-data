# RowId và kiểm tra RowIdLifetime của cơ sở dữ liệu trong JDBC

## 1. Vì sao cần hiểu RowId trước khi sử dụng?

Trong ứng dụng Java, cách nhận diện một bản ghi bền vững thường là **khóa chính (primary key)**, ví dụ `customer_id`, `order_id` hoặc UUID được quản lý theo thiết kế dữ liệu. Tuy nhiên một số hệ quản trị còn có khái niệm **địa chỉ/định danh của hàng ở tầng cơ sở dữ liệu**, thường được gọi là `ROWID`. JDBC hỗ trợ kiểu này thông qua `java.sql.RowId`, và cung cấp một phép kiểm tra quan trọng: **`DatabaseMetaData.getRowIdLifetime()`**.

Mục tiêu của bài **“RowId và kiểm tra RowIdLifetime của cơ sở dữ liệu”** trong nhóm **JDBC dữ liệu** là hiểu ba điều phải đi cùng nhau:

1. **Giá trị RowId là gì?** Nó biểu diễn một SQL `ROWID` có thể được data source hiểu như địa chỉ hàng, dạng logic hoặc vật lý tùy database.
2. **RowId còn hiệu lực đến bao giờ?** Driver công bố thông tin qua `RowIdLifetime`. Không được tự giả định rằng mọi RowId có thể dùng qua `COMMIT`, qua một session mới hay nhiều năm sau.
3. **Sử dụng với JDBC như thế nào?** Chỉ truy cập khi driver/database hỗ trợ, dùng `ResultSet.getRowId` và `PreparedStatement.setRowId` trong phạm vi phù hợp, xử lý `SQLException` và SQL `NULL`, ưu tiên khóa chính để nhận diện logic lâu dài.

**Nguyên tắc xuyên suốt:** `RowId` **không mặc nhiên là primary key**, `RowIdLifetime.ROWID_VALID_FOREVER` **không bảo đảm một key nghiệp vụ vĩnh viễn**, và một pseudo-column có tên `rowid`/`ctid` của database cụ thể **không tự đồng nghĩa** với JDBC `java.sql.RowId`.

Bài ưu tiên các API còn được hỗ trợ trong Java SE 26. Ví dụ kiểm thử độc lập dùng **Java 17+**, biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24 với **29/29 kiểm tra PASS**. Chương trình tạo mock JDBC qua Java dynamic proxies để không cần database thật; các ví dụ Oracle/PostgreSQL được đánh dấu riêng là **driver/database-specific** và cần integration test.

### Kết quả học tập

Sau bài, bạn sẽ có thể:

- Liệt kê chính xác **năm** giá trị `RowIdLifetime` và phân biệt `UNSUPPORTED`, `OTHER`, `TRANSACTION`, `SESSION`, `FOREVER`.
- Gọi `connection.getMetaData().getRowIdLifetime()`, phân loại rủi ro theo **thời gian sử dụng**, không theo phỏng đoán.
- Đọc SQL `ROWID` từ `ResultSet.getRowId(int/String)`, bind nó bằng `PreparedStatement.setRowId`, không chuyển sang chuỗi tùy tiện.
- Hiểu `RowId.getBytes()`, `equals`, `hashCode` và `toString()` đều có ràng buộc về **nguồn gốc, bảng và hiệu lực**.
- Phân biệt RowId với row number trong ResultSet, generated keys, database PK, PostgreSQL `ctid` và SQLite `rowid`.
- Chọn fallback sang PK khi JDBC driver không hỗ trợ `ROWID` hoặc lifetime không phù hợp.
- Test positive/negative paths từ metadata tới fetch/bind, và kiểm thử trên database thật trước khi dùng trong production.

## 2. `java.sql.RowId`: một SQL ROWID được ánh xạ sang Java

Javadoc của `java.sql.RowId` mô tả đây là **ánh xạ của SQL `ROWID` sang ngôn ngữ Java**. Hình dung nó như địa chỉ để data source xác định hàng, nhưng **ý nghĩa của địa chỉ** — logic, vật lý hay hỗn hợp — do database quyết định.

Các method chính:

```java
public interface RowId {
    boolean equals(Object obj);
    byte[] getBytes();
    int hashCode();
    String toString();
}
```

Đây là **hình minh họa chữ ký API**, không phải một file Java cần tự khai báo lại. Trong ứng dụng phải import `java.sql.RowId`.

Một `RowId` **không** cung cấp:

- Method chuẩn `getTableName()` hoặc `getDatabaseId()`.
- Phép tự nhận biết PK được gán cho hàng.
- API portable để tái tạo lại RowId từ một `byte[]` tùy ý.
- Cơ chế đảm bảo hàng vẫn còn tồn tại.
- Một transaction lock hoặc quyền đọc/sửa dữ liệu.

Một database có thể dùng row address mang tính vật lý; database khác có thể không hỗ trợ SQL ROWID, hoặc cung cấp một địa chỉ hàng hoàn toàn khác.

### RowId và các kiểu dễ bị nhầm

| Khái niệm | Bản chất | Có dùng làm khóa nghiệp vụ lâu dài? |
| --- | --- | --- |
| `java.sql.RowId` | JDBC representation của SQL ROWID do driver cấp | **Không mặc định**; phụ thuộc lifetime/nguồn/bảng và schema |
| `RowIdLifetime` | Enum mô tả khoảng hiệu lực được database công bố | Không phải key |
| `ResultSet.getRow()` | Số thứ tự hàng hiện tại của cursor ResultSet | **Không**: chỉ mô tả vị trí cursor |
| `ResultSet.getRowId(...)` | Đọc giá trị SQL ROWID của cột đang chọn | Tùy driver và SQL |
| `Statement.getGeneratedKeys()` | Các khóa được tạo khi INSERT (nếu hỗ trợ) | Có thể là PK; không tự là ROWID |
| Primary key | Định danh logic do schema ràng buộc | **Thông thường có**, theo business policy |
| Oracle `ROWID` pseudocolumn | Định danh/vị trí hàng đặc thù Oracle | Có thể dùng tình huống chuyên biệt, không tự thay PK |
| PostgreSQL `ctid` | Vị trí vật lý của **row version** | **Không**; thay đổi khi UPDATE/move |
| SQLite `rowid` | Một dạng integer key theo storage model của SQLite | Không tự là `java.sql.RowId`; semantics của SQLite riêng |

**Đặc biệt:** Tên cột `ROWID` trong SQL của một database không có nghĩa JDBC driver chắc chắn hỗ trợ `ResultSet.getRowId` hay `PreparedStatement.setRowId`. Cần kiểm tra metadata, driver và thao tác thực tế.

## 3. `DatabaseMetaData.getRowIdLifetime()` là bước đầu tiên

Mọi ứng dụng muốn dùng RowId theo JDBC nên kiểm tra metadata của **kết nối thực tế đang dùng**:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.RowIdLifetime;
import java.sql.SQLException;

static RowIdLifetime inspectLifetime(Connection connection)
        throws SQLException {
    DatabaseMetaData metadata = connection.getMetaData();
    return metadata.getRowIdLifetime();
}
```

Đây là **method minh họa**, đặt bên trong một class có `Connection` đang mở; không phải một chương trình standalone.

Phương thức `DatabaseMetaData.getRowIdLifetime()` trả về **`RowIdLifetime`**, không phải `boolean`. Nó thông báo data source có hỗ trợ SQL ROWID hay không và RowId còn hiệu lực ít nhất tới mốc nào.

### Năm enum values và ý nghĩa chính xác

| `RowIdLifetime` | Ý nghĩa theo Java SE | Cách hiểu an toàn |
| --- | --- | --- |
| `ROWID_UNSUPPORTED` | Data source không hỗ trợ kiểu SQL `ROWID` | Không dùng JDBC RowId API; dùng PK/fallback |
| `ROWID_VALID_OTHER` | Lifetime **không xác định**, không thuộc ba loại được đặt tên | Không mặc định suy ra có thể dùng dù chỉ một transaction; cần contract vendor |
| `ROWID_VALID_TRANSACTION` | RowId còn hiệu lực **ít nhất trong transaction chứa nó** | Chỉ dựa vào RowId trong **cùng transaction** theo chính sách thận trọng |
| `ROWID_VALID_SESSION` | RowId còn hiệu lực **ít nhất trong session chứa nó** | Có thể dùng trong cùng session, kể cả nhiều transaction, nếu hàng còn hợp lệ |
| `ROWID_VALID_FOREVER` | Lifetime **về thực chất không giới hạn** | Có thể phù hợp phạm vi dài hơn, nhưng vẫn không phải bảo đảm PK/bản ghi không bị xóa |

Từ khóa **“at least” (ít nhất)** rất quan trọng. `ROWID_VALID_TRANSACTION` không có nghĩa RowId **chắc chắn hết hiệu lực ngay sau COMMIT**; nó có nghĩa JDBC chỉ cung cấp đảm bảo tối thiểu trong transaction. Driver/database **có thể** giữ lâu hơn, nhưng application không được dựa vào giả định đó nếu không có contract bổ sung.

Tương tự, `ROWID_VALID_SESSION` không bảo đảm identifier có thể mang sang **physical database session khác**, ví dụ sau khi pool trả connection và cấp một connection mới.

### Một số quy tắc suy luận đúng

- `TRANSACTION`: dùng trong transaction tạo RowId; không mặc định qua commit.
- `SESSION`: dùng trong session tạo RowId, bao gồm phạm vi transaction trong session; không mặc định qua session khác.
- `FOREVER`: không có giới hạn lifetime hữu hạn được metadata công bố; vẫn cần **bảng, nguồn gốc, sự tồn tại của hàng, quyền truy cập và tính nhất quán**.
- `OTHER`: không có một mốc đảm bảo chuẩn nào để suy từ enum; coi là **không đủ thông tin**.
- `UNSUPPORTED`: không gọi `getRowId/setRowId` như một nhánh logic bắt buộc.

Một application vẫn phải xử lý `SQLException`, vì ngay cả metadata cũng có thể không đọc được do connection lỗi.

## 4. Ma trận quyết định sử dụng RowId theo phạm vi

Đặt câu hỏi **sẽ sử dụng RowId ở đâu và lúc nào?**

| Ý định sử dụng | TRANSACTION | SESSION | FOREVER | OTHER / UNSUPPORTED |
| --- | --- | --- | --- | --- |
| Trong transaction đang đọc RowId | Có bảo đảm lifetime tối thiểu | Có | Có | Không mặc định |
| Sau COMMIT, cùng database session | Không được bảo đảm | Có | Có | Không mặc định |
| Qua một session khác | Không được bảo đảm | Không được bảo đảm | Có giới hạn lifetime tối thiểu rộng hơn | Không mặc định |
| Lưu lâu dài làm business identifier | **Không** | **Không** | **Vẫn không nên** thay PK | **Không** |

“Có” ở bảng nghĩa là **metadata cung cấp đủ thông tin lifetime để thử sử dụng trong cùng bảng/data source và với hàng còn hợp lệ**, không có nghĩa SQL operation nhất định thành công hoặc database miễn nhiễm transaction isolation, concurrent update, move và authorization.

### Một policy kiểm tra bảo thủ

```java
enum Scope {
    CURRENT_TRANSACTION,
    SAME_SESSION_AFTER_COMMIT,
    OTHER_SESSION
}

static boolean allowed(RowIdLifetime lifetime, Scope scope) {
    return switch (lifetime) {
        case ROWID_VALID_FOREVER -> true;
        case ROWID_VALID_SESSION ->
                scope != Scope.OTHER_SESSION;
        case ROWID_VALID_TRANSACTION ->
                scope == Scope.CURRENT_TRANSACTION;
        case ROWID_VALID_OTHER, ROWID_UNSUPPORTED -> false;
    };
}
```

Đây là snippet từ chương trình chạy đầy đủ ở phần 8, sử dụng **Java 17 switch expression**. Nó là **chính sách thận trọng của bài học**, không phải phương thức mặc định của JDK.

Nếu app đòi lưu lâu dài trong API/DB/cache, ngay cả `FOREVER` cũng không đủ để mặc định biến RowId thành business key: key có thể không định danh row ở bảng/nguồn khác, hàng có thể bị xóa và row addresses có thể bị tái sử dụng theo semantics DB.

### “Session” là gì trong ứng dụng có connection pool?

Một **physical database session** có thể sống lâu hơn logical `Connection` mà ứng dụng mượn. Khi app gọi `connection.close()`, pool thường nhận logical handle về nhưng vẫn giữ underlying database session. Sau đó một request khác có thể mượn cùng hoặc session khác.

Vì vậy **“cùng DataSource” không tương đương “cùng session”**. Không lưu RowId lấy từ lần mượn connection A rồi cho rằng lần mượn connection B được bảo đảm vẫn nằm trong `ROWID_VALID_SESSION`, ngay cả khi cả hai đến từ một pool.

Nếu cần sử dụng trong một transaction, quản lý transaction boundaries rõ ràng. Nếu cần qua requests, tốt hơn là lưu **primary key**.

## 5. RowId được lấy từ đâu trong JDBC?

`RowId` thường được đọc từ một **cột SQL có kiểu ROWID** trong `ResultSet`. Java cung cấp:

```java
RowId id = resultSet.getRowId(1);
RowId id2 = resultSet.getRowId("rid");
```

- Index cột trong JDBC bắt đầu từ **1**.
- `"rid"` phải là column label đúng với query, thường dùng `AS rid` để rõ ràng.
- Cursor phải ở hàng hợp lệ (`resultSet.next() == true`).
- Với SQL `NULL`, `getRowId` trả **`null`**.
- `getRowId` có thể ném `SQLException` khi lỗi DB/column/cursor/closed result.
- `getRowId` có thể ném `SQLFeatureNotSupportedException` nếu driver không hỗ trợ method.

**Không phải mọi query đều có ROWID column.** Nếu `SELECT id, name FROM ...` chỉ chứa PK và name, gọi `getRowId("rid")` sẽ không tự làm database tạo thêm một cột đặc biệt. Query phải chọn đúng ROWID column/pseudocolumn theo cú pháp của database tương ứng.

Đừng nhầm:

```java
resultSet.getRow();  // Số thứ tự hàng của cursor
resultSet.getRowId(1); // SQL ROWID value ở cột thứ nhất
```

Hai API có mục đích hoàn toàn khác nhau.

## 6. Dùng `PreparedStatement.setRowId` đúng cách

Khi driver hỗ trợ SQL ROWID, `PreparedStatement` cho phép bind parameter bằng:

```java
void setRowId(int parameterIndex, RowId value)
        throws SQLException;
```

Một query update minh họa cho Oracle:

```sql
UPDATE app_events SET status = ? WHERE ROWID = ?
```

Dùng statement:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE app_events SET status = ? WHERE ROWID = ?")) {
    ps.setString(1, "DONE");
    ps.setRowId(2, rowId);
    int changed = ps.executeUpdate();
}
```

Đây là **snippet tích hợp**, cần một `Connection` thật, `rowId` đọc từ đúng database/table, cùng lifecycle hợp lệ và SQL dialect hỗ trợ `ROWID`. Đừng coi lệnh trên là SQL universal cho PostgreSQL, MySQL hay SQLite.

`setRowId` sẽ chuyển object RowId thành SQL ROWID value theo driver; nó **không dùng `toString()` làm SQL literal**. JDBC Javadoc quy định có thể ném `SQLFeatureNotSupportedException` nếu driver không hỗ trợ method.

### Vì sao nên dùng bind thay vì ghép chuỗi RowId?

Không nên:

```java
String sql = "UPDATE app_events SET status='DONE' "
        + "WHERE ROWID='" + rowId.toString() + "'";
```

Ví dụ này là **anti-pattern**. `RowId.toString()` có format phụ thuộc driver và **không nhất thiết là SQL ROWID literal hợp lệ**. Ngoài ra việc ghép dữ liệu vào SQL bỏ qua parameter binding và tạo thói quen dễ gây injection.

Dùng:

```java
ps.setRowId(2, rowId);
```

mới bám theo JDBC type system. Nếu một driver không hỗ trợ typed binding, cần tìm **documented vendor-specific alternative** hoặc chuyển sang primary key; đừng tự đoán cách encode bytes thành SQL string.

### Kiểm tra số hàng tác động

`executeUpdate()` trả update count. Nếu bạn kỳ vọng đúng **một** hàng mà kết quả là `0`, row có thể không còn tồn tại, RowId có thể không còn chỉ tới row mong muốn, điều kiện WHERE không match hoặc transaction/concurrency thay đổi dữ liệu.

Nếu kết quả khác `1` trong một thao tác yêu cầu sửa một row, nên xử lý như **concurrency/business integrity issue**, không âm thầm bỏ qua.

## 7. `RowId.getBytes()`, `equals` và `toString()`: cần hiểu điều kiện so sánh

### 7.1. Bytes là representation do driver quyết định

`RowId.getBytes()` trả `byte[]` biểu diễn SQL ROWID. Javadoc nói **độ dài do driver quyết định**. Không nên giả định:

- Độ dài luôn là 8/16 bytes.
- Đó là UUID.
- Đó là UTF-8 encoded form của `toString()`.
- Có thể gửi mảng bytes sang driver khác rồi tạo lại RowId portable.
- Có thể dùng bytes như khóa duy nhất toàn hệ thống.

Nếu muốn debug bằng hex:

```java
byte[] raw = rowId.getBytes();
String hex = java.util.HexFormat.of().formatHex(raw);
```

`HexFormat` có từ Java 17, phù hợp với ví dụ của bài. Chỉ log khi ID data được phép ghi log; dù là địa chỉ hàng, nó vẫn có thể tiết lộ thông tin database hoặc tạo security/privacy concerns.

### 7.2. `toString()` không nhất thiết là SQL literal

Javadoc `RowId.toString()` nêu rõ format do driver cung cấp và **có thể không trùng SQL literal form**. Đừng tự tạo prepared SQL từ nó, đừng dựa vào một format string như `"AAAB..."` cho mọi driver.

### 7.3. `equals` có ràng buộc về nguồn gốc và lifetime

Theo Javadoc `RowId.equals`, nếu hai RowId:
- **Cả hai còn hiệu lực**, và
- **Cùng bảng** trên **cùng data source**,

thì nếu chúng bằng nhau, chúng chỉ đến **cùng hàng**.

Nhưng nếu:
- Một hoặc cả hai không còn được bảo đảm hiệu lực,
- Chúng đến từ các data sources khác nhau,
- Hoặc từ hai bảng khác nhau trên cùng database,

thì **hai RowId có thể `equals == true` mà vẫn không cùng hàng**. Vì vậy cần lưu identity context ngoài giá trị RowId nếu application có nhiều bảng/nguồn dữ liệu.

### 7.4. Đừng tự đặt `RowId` làm primary key của business entities

Ví dụ một application lưu `order_id = 42` (PK) và `rowId` để thao tác tối ưu trong một transaction. `order_id` là định danh logic mà nghiệp vụ dùng lâu dài. `rowId` là token database-specific, có thể hữu ích trong phạm vi được bảo đảm.

Nếu bạn lưu RowId vào URL `/orders/<row-id>` hoặc message queue lâu dài, hệ thống có thể mất khả năng tra cứu khi chuyển database, thay pool/session, đổi bảng hoặc RowId không còn hiệu lực. PK/UUID vẫn là lựa chọn mặc định tốt hơn để thiết kế API và liên kết bền vững.

## 8. Chương trình Java 17+ tự chạy: 29 kiểm thử toàn bộ vòng xử lý

Bài thực hành tạo một **database mock trong bộ nhớ** dùng Java dynamic proxies:

```text
Connection (proxy)
  ├── getMetaData()
  │      └── DatabaseMetaData (proxy)
  │              └── getRowIdLifetime()
  ├── prepareStatement("SELECT rid ...")
  │      └── PreparedStatement (proxy)
  │              └── ResultSet (proxy)
  │                     └── getRowId("rid" hoặc 1)
  └── prepareStatement("UPDATE ... WHERE rid = ?")
         └── PreparedStatement (proxy)
                 └── setRowId(...)
                 └── executeUpdate()
```

**Tại sao dùng mock?** Java SE có các JDBC interfaces nhưng không cung cấp sẵn database thật. Demo tách **cơ chế API** khỏi một SQL dialect cụ thể, nên có thể chạy chỉ với JDK 17+. Chương trình không dùng network, pool, credentials hay thư viện ngoài. Khi tích hợp thật vẫn phải test driver và server cụ thể.

Chương trình kiểm tra:
- Tập enum có đúng 5 values.
- Chính sách lifetime theo transaction/session/other session.
- `RowId` bytes, identity context, equals/hashCode và toString của **mock**.
- Metadata đọc qua `Connection.getMetaData`.
- `getRowId` theo column index và label.
- `setRowId` trên `PreparedStatement` và update count.
- Unsupported driver ném `SQLFeatureNotSupportedException`.
- SQL `NULL` được trả dưới dạng `null`.
- Tài nguyên được đóng bằng try-with-resources.

### 8.1. Lưu file `RowIdLifetimeDemo.java`

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.RowId;
import java.sql.RowIdLifetime;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;

public final class RowIdLifetimeDemo {

    enum Scope {
        CURRENT_TRANSACTION,
        SAME_SESSION_AFTER_COMMIT,
        OTHER_SESSION
    }

    static boolean allowed(RowIdLifetime lifetime, Scope scope) {
        return switch (lifetime) {
            case ROWID_VALID_FOREVER -> true;
            case ROWID_VALID_SESSION ->
                    scope != Scope.OTHER_SESSION;
            case ROWID_VALID_TRANSACTION ->
                    scope == Scope.CURRENT_TRANSACTION;
            case ROWID_VALID_OTHER, ROWID_UNSUPPORTED -> false;
        };
    }

    private static int passed;

    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    static final class MockRowId implements RowId {
        final String source;
        final String table;
        private final byte[] bytes;

        MockRowId(String source, String table, byte[] bytes) {
            this.source = source;
            this.table = table;
            this.bytes = bytes.clone();
        }

        @Override public byte[] getBytes() {
            return bytes.clone();
        }

        @Override public String toString() {
            return "mock@" + HexFormat.of().formatHex(bytes);
        }

        @Override public boolean equals(Object other) {
            return other instanceof MockRowId x
                    && source.equals(x.source)
                    && table.equals(x.table)
                    && Arrays.equals(bytes, x.bytes);
        }

        @Override public int hashCode() {
            return Objects.hash(
                    source, table, Arrays.hashCode(bytes));
        }
    }

    @SuppressWarnings("unchecked")
    static <T> T create(Class<T> api, InvocationHandler handler) {
        return (T) Proxy.newProxyInstance(
                RowIdLifetimeDemo.class.getClassLoader(),
                new Class<?>[] { api }, handler);
    }

    static final class MiniDb {
        final RowIdLifetime lifetime;
        final MockRowId rid;
        String note = "old";

        MiniDb(RowIdLifetime lifetime, MockRowId rid) {
            this.lifetime = lifetime;
            this.rid = rid;
        }

        DatabaseMetaData meta() {
            return create(DatabaseMetaData.class, (p, m, a) -> {
                if (m.getName().equals("getRowIdLifetime")) {
                    return lifetime;
                }
                throw new SQLFeatureNotSupportedException(m.getName());
            });
        }

        Connection connection() {
            return create(Connection.class, new InvocationHandler() {
                boolean closed;

                @Override
                public Object invoke(
                        Object p, java.lang.reflect.Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException("closed handle");
                            }
                            yield switch (m.getName()) {
                                case "getMetaData" -> meta();
                                case "prepareStatement" ->
                                        statement((String) a[0]);
                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }

        ResultSet result(boolean found) {
            return create(ResultSet.class, new InvocationHandler() {
                boolean closed;
                boolean visited;
                boolean onRow;

                @Override
                public Object invoke(
                        Object p, java.lang.reflect.Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException("result closed");
                            }
                            yield switch (m.getName()) {
                                case "next" -> {
                                    onRow = !visited && found;
                                    visited = true;
                                    yield onRow;
                                }
                                case "getRowId" -> {
                                    if (!onRow) {
                                        throw new SQLException("no row");
                                    }
                                    if (lifetime
                                            == RowIdLifetime.ROWID_UNSUPPORTED) {
                                        throw new SQLFeatureNotSupportedException(
                                                "ROWID unsupported");
                                    }
                                    Object col = a[0];
                                    if (!(Integer.valueOf(1).equals(col)
                                            || "rid".equals(col))) {
                                        throw new SQLException("unknown column");
                                    }
                                    yield rid;
                                }
                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }

        PreparedStatement statement(String sql) {
            boolean find = sql.equals(
                    "SELECT rid FROM demo WHERE id = ?");
            boolean update = sql.equals(
                    "UPDATE demo SET note = ? WHERE rid = ?");

            if (!find && !update) {
                throw new IllegalArgumentException(
                        "SQL not supported by mock");
            }

            return create(PreparedStatement.class,
                    new InvocationHandler() {
                boolean closed;
                Integer rowPk;
                String newNote;
                RowId whereRid;

                @Override
                public Object invoke(
                        Object p, java.lang.reflect.Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            closed = true;
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException("statement closed");
                            }
                            yield switch (m.getName()) {
                                case "setInt" -> {
                                    if (!find || (Integer) a[0] != 1) {
                                        throw new SQLException(
                                                "wrong parameter");
                                    }
                                    rowPk = (Integer) a[1];
                                    yield null;
                                }
                                case "setString" -> {
                                    if (!update || (Integer) a[0] != 1) {
                                        throw new SQLException(
                                                "wrong parameter");
                                    }
                                    newNote = (String) a[1];
                                    yield null;
                                }
                                case "setRowId" -> {
                                    if (lifetime
                                            == RowIdLifetime.ROWID_UNSUPPORTED) {
                                        throw new SQLFeatureNotSupportedException(
                                                "ROWID unsupported");
                                    }
                                    if (!update || (Integer) a[0] != 2) {
                                        throw new SQLException(
                                                "wrong parameter");
                                    }
                                    whereRid = (RowId) a[1];
                                    yield null;
                                }
                                case "executeQuery" -> {
                                    if (!find || rowPk == null) {
                                        throw new SQLException(
                                                "wrong query state");
                                    }
                                    yield result(rowPk == 7);
                                }
                                case "executeUpdate" -> {
                                    if (!update || newNote == null
                                            || whereRid == null) {
                                        throw new SQLException(
                                                "wrong update state");
                                    }
                                    if (!whereRid.equals(rid)) {
                                        yield 0;
                                    }
                                    note = newNote;
                                    yield 1;
                                }
                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }
    }

    private static final byte[] RAW = {
            0x10, 0x20, 0x30, 0x40
    };

    public static void main(String[] args) throws Exception {
        check("five-lifetimes",
                RowIdLifetime.values().length == 5);

        check("transaction-current",
                allowed(RowIdLifetime.ROWID_VALID_TRANSACTION,
                        Scope.CURRENT_TRANSACTION));
        check("transaction-not-next",
                !allowed(RowIdLifetime.ROWID_VALID_TRANSACTION,
                        Scope.SAME_SESSION_AFTER_COMMIT));
        check("transaction-not-other-session",
                !allowed(RowIdLifetime.ROWID_VALID_TRANSACTION,
                        Scope.OTHER_SESSION));

        check("session-current",
                allowed(RowIdLifetime.ROWID_VALID_SESSION,
                        Scope.CURRENT_TRANSACTION));
        check("session-after-commit",
                allowed(RowIdLifetime.ROWID_VALID_SESSION,
                        Scope.SAME_SESSION_AFTER_COMMIT));
        check("session-not-other-session",
                !allowed(RowIdLifetime.ROWID_VALID_SESSION,
                        Scope.OTHER_SESSION));

        check("forever-other-session",
                allowed(RowIdLifetime.ROWID_VALID_FOREVER,
                        Scope.OTHER_SESSION));
        check("other-not-assumed",
                !allowed(RowIdLifetime.ROWID_VALID_OTHER,
                        Scope.CURRENT_TRANSACTION));
        check("unsupported-not-assumed",
                !allowed(RowIdLifetime.ROWID_UNSUPPORTED,
                        Scope.CURRENT_TRANSACTION));

        MockRowId rid = new MockRowId("source-A", "demo", RAW);
        MockRowId same = new MockRowId("source-A", "demo", RAW);
        MockRowId otherTable =
                new MockRowId("source-A", "elsewhere", RAW);
        MockRowId otherSource =
                new MockRowId("source-B", "demo", RAW);

        check("rowid-hex",
                HexFormat.of().formatHex(rid.getBytes())
                        .equals("10203040"));

        byte[] copy = rid.getBytes();
        copy[0] = 0;
        check("bytes-defensive-copy",
                rid.getBytes()[0] == 0x10);

        check("same-id-equals",
                rid.equals(same)
                && rid.hashCode() == same.hashCode());
        check("different-table-not-equal-in-mock",
                !rid.equals(otherTable));
        check("different-source-not-equal-in-mock",
                !rid.equals(otherSource));
        check("tostring-vendor-specific",
                rid.toString().equals("mock@10203040"));

        MiniDb db = new MiniDb(
                RowIdLifetime.ROWID_VALID_SESSION, rid);

        try (Connection c = db.connection()) {
            RowIdLifetime life =
                    c.getMetaData().getRowIdLifetime();

            check("jdbc-metadata-session",
                    life == RowIdLifetime.ROWID_VALID_SESSION);
            check("metadata-allows-in-scope",
                    allowed(life, Scope.CURRENT_TRANSACTION));

            RowId selected;
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT rid FROM demo WHERE id = ?")) {
                ps.setInt(1, 7);
                try (ResultSet rs = ps.executeQuery()) {
                    check("resultset-has-row", rs.next());
                    selected = rs.getRowId("rid");
                    check("getrowid-by-label",
                            selected.equals(rid));
                    check("getrowid-by-index",
                            rs.getRowId(1).equals(selected));
                    check("resultset-exhausted", !rs.next());
                }
            }

            try (PreparedStatement ps = c.prepareStatement(
                    "UPDATE demo SET note = ? WHERE rid = ?")) {
                ps.setString(1, "new");
                ps.setRowId(2, selected);
                check("bind-rowid-updated-one",
                        ps.executeUpdate() == 1);
            }

            check("updated-record",
                    db.note.equals("new"));

            try (PreparedStatement ps = c.prepareStatement(
                    "UPDATE demo SET note = ? WHERE rid = ?")) {
                ps.setString(1, "not-used");
                ps.setRowId(2, otherSource);
                check("other-source-id-no-match-in-mock",
                        ps.executeUpdate() == 0);
            }
        }

        MiniDb unsupported = new MiniDb(
                RowIdLifetime.ROWID_UNSUPPORTED, rid);

        try (Connection c = unsupported.connection()) {
            check("metadata-unsupported",
                    c.getMetaData().getRowIdLifetime()
                            == RowIdLifetime.ROWID_UNSUPPORTED);

            boolean failedRead = false;
            try (PreparedStatement ps = c.prepareStatement(
                    "SELECT rid FROM demo WHERE id = ?")) {
                ps.setInt(1, 7);
                try (ResultSet rs = ps.executeQuery()) {
                    rs.next();
                    try {
                        rs.getRowId(1);
                    } catch (SQLFeatureNotSupportedException expected) {
                        failedRead = true;
                    }
                }
            }
            check("unsupported-getrowid-throws",
                    failedRead);

            boolean failedBind = false;
            try (PreparedStatement ps = c.prepareStatement(
                    "UPDATE demo SET note = ? WHERE rid = ?")) {
                try {
                    ps.setRowId(2, rid);
                } catch (SQLFeatureNotSupportedException expected) {
                    failedBind = true;
                }
            }
            check("unsupported-setrowid-throws",
                    failedBind);
        }

        MiniDb nullable = new MiniDb(
                RowIdLifetime.ROWID_VALID_FOREVER, null);

        try (Connection c = nullable.connection();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT rid FROM demo WHERE id = ?")) {
            ps.setInt(1, 7);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                check("sql-null-rowid-is-null",
                        rs.getRowId("rid") == null);
            }
        }

        System.out.println("passed=" + passed);
    }
}
```

### 8.2. Chạy trên JDK 17+

Đặt terminal tại thư mục có file `RowIdLifetimeDemo.java`:

```bash
javac --release 17 -encoding UTF-8 RowIdLifetimeDemo.java
java RowIdLifetimeDemo
```

Các lệnh tương tự dùng được trên Windows PowerShell; `-encoding UTF-8` chỉ định charset của source Java. Không cần database driver hay cấu hình `jdbc:...`.

**Vì sao dùng dynamic proxies?** Java `Connection`/`PreparedStatement`/`ResultSet`/`DatabaseMetaData` có rất nhiều methods. `Proxy.newProxyInstance` cùng `InvocationHandler` cho phép fixture chỉ hiện thực đúng những method dùng trong bài. Các phương thức còn lại ném `SQLFeatureNotSupportedException`. Đây không phải database thật, không hỗ trợ SQL tùy ý.

### 8.3. Stdout chính xác từ phiên chạy đã xác minh

```text
PASS five-lifetimes
PASS transaction-current
PASS transaction-not-next
PASS transaction-not-other-session
PASS session-current
PASS session-after-commit
PASS session-not-other-session
PASS forever-other-session
PASS other-not-assumed
PASS unsupported-not-assumed
PASS rowid-hex
PASS bytes-defensive-copy
PASS same-id-equals
PASS different-table-not-equal-in-mock
PASS different-source-not-equal-in-mock
PASS tostring-vendor-specific
PASS jdbc-metadata-session
PASS metadata-allows-in-scope
PASS resultset-has-row
PASS getrowid-by-label
PASS getrowid-by-index
PASS resultset-exhausted
PASS bind-rowid-updated-one
PASS updated-record
PASS other-source-id-no-match-in-mock
PASS metadata-unsupported
PASS unsupported-getrowid-throws
PASS unsupported-setrowid-throws
PASS sql-null-rowid-is-null
passed=29
```

Bộ fixture này được biên dịch **`javac --release 17`**, thực thi trên **OpenJDK 24**, và đã cho **29/29 assertions PASS**.

### 8.4. Những gì bài test thực sự chứng minh

| Nhóm | Kiểm thử | Ý nghĩa |
| --- | --- | --- |
| Enum | `five-lifetimes` | Có đúng 5 trạng thái chuẩn |
| Transaction | `transaction-*` | Không mặc định tin RowId sau COMMIT hoặc session khác |
| Session | `session-*` | Có thể dùng trong session nhưng không bảo đảm session khác |
| Forever | `forever-other-session` | Lifetime không giới hạn theo metadata được policy cho phép |
| Unknown/Unsupported | `other-not-assumed`, `unsupported-not-assumed` | Fail-closed khi không có mốc đảm bảo |
| Bytes | `rowid-hex`, `bytes-defensive-copy` | Mock row ID có bytes riêng và trả bản sao |
| Identity | `same-id-equals`, `different-*-not-equal-in-mock` | Mock gắn source và table vào equality |
| SQL Metadata | `jdbc-metadata-session` | Đọc qua `Connection.getMetaData().getRowIdLifetime()` |
| SQL ResultSet | `getrowid-by-label/index` | Getter typed có hai overload |
| SQL PreparedStatement | `bind-rowid-updated-one` | Binder nhận RowId và mock update được đúng một hàng |
| Negative source | `other-source-id-no-match-in-mock` | Mock từ chối id ngoài source |
| Unsupported JDBC | `unsupported-getrowid-throws`, `unsupported-setrowid-throws` | Exception kiểu `SQLFeatureNotSupportedException` |
| SQL NULL | `sql-null-rowid-is-null` | Getter có thể trả `null` |

**Quan trọng:** `MockRowId` cố ý đưa `source` và `table` vào `equals/hashCode` để giúp người học nhìn thấy identity context. JDBC **không bắt buộc** mọi driver đưa thông tin này vào chính object. Trên một driver thật, hai RowId ở hai nguồn/bảng khác nhau *có thể bằng nhau* nhưng không định danh cùng hàng. Đừng biến hành vi của mock thành nhận định áp dụng mọi database.

Tương tự, `MiniDb` không mô phỏng đầy đủ transaction isolation, concurrency, row movement hoặc physical storage. Test chỉ kiểm tra **việc dùng đúng Java API**, không chứng nhận một database cụ thể hỗ trợ RowId lâu dài.

## 9. Ví dụ tích hợp thực tế: Oracle ROWID trong cùng transaction

Oracle Database cung cấp `ROWID` pseudocolumn theo SQL dialect của Oracle và Oracle JDBC driver có khả năng xử lý ROWID. Có thể kết hợp `getRowIdLifetime` với một transaction rõ ràng khi cần update theo ROWID.

### 9.1. Ý tưởng SQL

Giả sử ứng dụng có bảng:

```sql
CREATE TABLE app_events (
    id NUMBER PRIMARY KEY,
    status VARCHAR2(40) NOT NULL
);
```

**Đây là Oracle SQL minh họa**, không phải DDL portable cho mọi database. Điều kiện dùng `ROWID` là Oracle database, đúng quyền SQL và driver hỗ trợ typed ROWID methods.

Đọc ROWID:

```sql
SELECT ROWID AS rid
FROM app_events
WHERE id = ?
FOR UPDATE
```

Vì `id` là PK, query xác định **row logic** trước, còn ROWID dùng để tham chiếu hàng trong cùng transaction. `FOR UPDATE` được sử dụng để **khóa hàng** theo semantics Oracle nhằm giảm khả năng concurrent update gây mâu thuẫn, không phải cách biến ROWID thành PK lâu dài.

Update:

```sql
UPDATE app_events
SET status = ?
WHERE ROWID = ?
```

### 9.2. Method JDBC minh họa

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.RowId;
import java.sql.RowIdLifetime;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

static int updateWithOracleRowId(
        Connection conn, long eventId, String newStatus)
        throws SQLException {

    // Caller owns a live connection and transaction.
    if (conn.getAutoCommit()) {
        throw new SQLException(
                "Explicit transaction required for this example");
    }

    DatabaseMetaData meta = conn.getMetaData();
    RowIdLifetime lifetime = meta.getRowIdLifetime();

    if (lifetime == RowIdLifetime.ROWID_UNSUPPORTED
            || lifetime == RowIdLifetime.ROWID_VALID_OTHER) {
        throw new SQLFeatureNotSupportedException(
                "No guaranteed ROWID lifetime for this operation");
    }

    RowId rid;
    try (PreparedStatement read = conn.prepareStatement(
            "SELECT ROWID AS rid FROM app_events "
            + "WHERE id = ? FOR UPDATE")) {
        read.setLong(1, eventId);

        try (ResultSet rs = read.executeQuery()) {
            if (!rs.next()) {
                return 0;
            }

            rid = rs.getRowId("rid");
            if (rid == null) {
                throw new SQLException("Unexpected null ROWID");
            }
        }
    }

    try (PreparedStatement update = conn.prepareStatement(
            "UPDATE app_events SET status = ? WHERE ROWID = ?")) {
        update.setString(1, newStatus);
        update.setRowId(2, rid);

        int changed = update.executeUpdate();
        if (changed != 1) {
            throw new SQLException(
                    "Expected one row, updated " + changed);
        }
        return changed;
    }
}
```

Đây là **method tích hợp Java**, chưa phải chương trình standalone. Nó cần Oracle JDBC driver, một `Connection` tới Oracle Database, bảng `app_events` và dữ liệu mẫu. Bởi không chạy với Oracle server trong fixture, **không khẳng định stdout hoặc kết quả DB cụ thể** cho snippet này.

**Quan trọng về ownership:** Method **không tự commit, rollback hoặc close** `conn`. Caller sở hữu transaction:

```java
// Minh họa: caller có DataSource thật và quản lý transaction.
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);

    try {
        int changed = updateWithOracleRowId(
                c, 42L, "DONE");
        c.commit();
    } catch (SQLException ex) {
        c.rollback();
        throw ex;
    }
}
```

Đây cũng là snippet minh họa. Trong ứng dụng dùng transaction manager/framework, không tự quản lý `commit/rollback/setAutoCommit` nếu framework đang giữ quyền điều phối. Chọn đúng boundary transaction và pool reset policy.

### 9.3. Vì sao query trước dùng PK, rồi mới ROWID?

- PK `id` là danh tính logic ổn định của sự kiện.
- `SELECT ... FOR UPDATE` khóa hàng trong cùng transaction theo SQL dialect tương ứng.
- `ROWID` chỉ dùng như một địa chỉ DB-specific **ngắn hạn** cho thao tác update kế tiếp.
- Nếu database/driver không hỗ trợ typed ROWID, fallback `UPDATE app_events SET status=? WHERE id=?` thường đơn giản, portable và dễ bảo trì hơn.

Trong nhiều ứng dụng CRUD, **không cần ROWID**. Sử dụng PK ngay từ đầu dễ hiểu và ít phụ thuộc vendor hơn. RowId chỉ có ích nếu có case tối ưu/driver capability rõ và benchmark/integration test chứng minh lợi ích.

## 10. PostgreSQL `ctid` và SQLite `rowid` không được đánh đồng với Java RowId

### 10.1. PostgreSQL `ctid`

PostgreSQL có system column `ctid` là vị trí vật lý của **row version** trong bảng. Tài liệu PostgreSQL hiện hành cảnh báo:
- `ctid` có thể giúp tìm row version nhanh trong một số thao tác nội bộ/ngắn hạn.
- `ctid` thay đổi khi một row được **UPDATE** hoặc dịch chuyển do `VACUUM FULL`.
- Vì vậy **không sử dụng `ctid` như định danh hàng lâu dài**; nên dùng primary key.

Ví dụ PostgreSQL SQL:

```sql
SELECT ctid, id FROM app_events WHERE id = ?;
```

Đây là query minh họa của PostgreSQL. **Không khẳng định** pgJDBC `ResultSet.getRowId("ctid")` sẽ trả `java.sql.RowId` hợp lệ; `ctid` có type/semantics riêng của PostgreSQL, không phải bằng chứng JDBC SQL `ROWID` được hỗ trợ.

Nếu bạn đang dùng pgJDBC, hãy đọc metadata của driver thật và dùng APIs mà driver tài liệu hóa cho system column; với nghiệp vụ lâu dài, **dùng PK**.

### 10.2. SQLite `rowid`

SQLite có một khái niệm `rowid` gắn với một số loại bảng. Nó có semantics **SQLite-specific**, không tự tương đương `java.sql.RowId` của mọi SQLite JDBC driver. Đặc biệt bảng `WITHOUT ROWID` không dùng mô hình `rowid` thông thường.

Nếu SQLite schema dùng `INTEGER PRIMARY KEY`, quan hệ của nó với SQLite rowid phụ thuộc cụ thể quy tắc SQLite. Với Java, cách truy cập phù hợp thường là qua numeric key theo driver/schema, không ép `RowId` nếu JDBC driver không hỗ trợ typed API.

### 10.3. Oracle `ROWID` và SQL ROWID support

Oracle là ví dụ rõ của ROWID pseudocolumn và Java RowId mapping, nhưng ngay cả ở Oracle:
- Bảng/tính năng cụ thể và row movement có thể ảnh hưởng cách sử dụng.
- Phải kiểm tra lifetime, transaction và driver.
- `ROWID` không nên thay thế primary key cho public API/business entity.
- `toString()` không nên được coi là SQL literal portable.

**Quy tắc chung:** SQL có một từ/biến thể tên “rowid” ≠ JDBC driver hỗ trợ `RowId` typed methods. Chỉ tin những gì metadata và driver API thực sự cung cấp.

## 11. Vì sao chỉ kiểm tra metadata chưa đủ?

`DatabaseMetaData.getRowIdLifetime()` cho biết capability/lifetime **theo data source**; nó không tự đảm bảo:

- Mọi table đều có SQL ROWID column có thể select.
- Mọi pseudo-column đều ánh xạ ra `Types.ROWID`.
- Query cụ thể được driver convert hợp lệ qua `ResultSet.getRowId`.
- `PreparedStatement.setRowId` hỗ trợ đúng parameter/SQL statement.
- Hàng chưa bị xóa/di chuyển hoặc đổi transaction visibility.
- User có quyền SELECT/UPDATE.
- Cùng `RowId` có thể dùng across connections/pool sessions theo application policy.

Vì vậy nên làm **hai lớp kiểm tra**:

1. **Capability/lifetime check:** `conn.getMetaData().getRowIdLifetime()` và policy phù hợp với phạm vi dùng.
2. **Feature integration check:** SELECT cột ROWID thật, đọc bằng `getRowId`, bind bằng `setRowId` và xác nhận affected rows/dữ liệu theo schema & driver.

Nếu metadata trả `ROWID_VALID_OTHER`, không tự suy mốc an toàn. Nếu trả `ROWID_UNSUPPORTED`, dừng RowId path và dùng khóa chính. Nếu API ném `SQLFeatureNotSupportedException`, đừng cố convert bytes/string bằng thủ thuật không được driver document.

### Lỗi và ngoại lệ

| Tình huống | Lỗi có thể gặp | Cách xử lý |
| --- | --- | --- |
| Metadata query thất bại | `SQLException` | Ghi diagnostic và xử lý DB connection/error |
| RowId method không được driver hỗ trợ | `SQLFeatureNotSupportedException` | Chuyển sang PK/fallback nếu có |
| Column label/index sai | `SQLException` | Kiểm tra SELECT/AS alias |
| ResultSet cursor không ở hàng hợp lệ | `SQLException` | Chỉ đọc sau `rs.next()` |
| SQL NULL | `getRowId` trả `null` | Xử lý rõ, không gọi method trên null |
| RowId hết lifetime hoặc hàng biến mất | Update count 0 hoặc DB exception | Không retry vô hạn; dùng PK/transaction policy |
| Dùng sai driver/SQL dialect | SQL syntax/type conversion error | Thiết kế vendor-specific adapter |
| Connection đã close | `SQLException` | Không giữ RowId/ResultSet ngoài scope |
| Dùng RowId từ nguồn/table khác | Có thể không định danh row mong muốn | Buộc kiểm tra source/table context |
| Concurrency conflict | Update count sai, lock/deadlock/timeout | Transaction/optimistic locking/retry policy |

## 12. Design pattern: ưu tiên PK, RowId là optimization/capability

Với entity thông thường, query theo PK là mặc định:

```java
try (PreparedStatement ps = conn.prepareStatement(
        "UPDATE app_events SET status = ? WHERE id = ?")) {
    ps.setString(1, newStatus);
    ps.setLong(2, eventId);
    int changed = ps.executeUpdate();
}
```

Đây là **snippet minh họa** trong scope có `conn`, `eventId` và `newStatus`, áp dụng khi schema có `id` là PK. Nó không cần RowId API và portable hơn giữa databases.

Chỉ xem RowId khi:
- Database/driver hỗ trợ type rõ ràng.
- Ứng dụng cần tính năng/tối ưu có cơ sở đo đạc.
- Phạm vi hiệu lực được metadata và workflow bảo đảm.
- SQL query/driver được kiểm thử thực tế.
- Product có kế hoạch fallback khi database không hỗ trợ.
- Truy cập không vi phạm quyền/transaction/pool semantics.

### Adapter tránh rải vendor SQL

Có thể định nghĩa interface ở tầng persistence:

```java
interface RowLocator {
    int updateStatus(long id, String status)
            throws java.sql.SQLException;
}
```

Đây là interface minh họa, không chứa implementation. Một adapter Oracle có thể tối ưu theo RowId ở một transaction, adapter chung dùng PK. Business code chỉ gọi method trên interface thay vì chứa SQL ROWID từ nhiều vendors.

### Bảo vệ optimistic concurrency

Nếu dữ liệu bị sửa đồng thời và product yêu cầu không ghi đè thay đổi của người khác, chỉ dùng RowId **không đủ**. Nên có version column hoặc điều kiện `WHERE id=? AND version=?`, kiểm tra affected rows, retry/collision policy theo domain.

RowId mô tả địa chỉ/identifier ở tầng DB; nó **không thay thế lock hoặc optimistic version checks**.

## 13. Kiểm thử integration theo database/driver

| Test case | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Metadata | `getRowIdLifetime()` | Một trong năm enum, xử lý đúng policy |
| Unsupported | `ROWID_UNSUPPORTED` | Không bắt buộc getRowId/setRowId |
| Unknown | `ROWID_VALID_OTHER` | Không tự phán valid qua COMMIT |
| Transaction lifetime | Read + bind trong same transaction | Chỉ coi đó là phạm vi được bảo đảm |
| Session lifetime | Same session qua commit | Phù hợp minimum guarantee nếu row còn |
| Cross-session | Connection mới từ pool | Không tin `SESSION` RowId qua borrowed handles |
| Forever | Sử dụng sau boundary phù hợp | Vẫn kiểm tra same source/table và row existence |
| Oracle typed SELECT | `SELECT ROWID AS rid ...` | `getRowId("rid")` không null khi có row |
| Oracle typed bind | `setRowId(2,rid)` | Update count đúng |
| SQL NULL | `ResultSet.getRowId(...)` | Trả `null` |
| Driver not supported | get/set methods | `SQLFeatureNotSupportedException` |
| Wrong column | `getRowId("missing")` | `SQLException`, không im lặng |
| Different table/source | So RowIds có context khác | Không suy identity chỉ từ equals/bytes |
| Delete/update/move | Thay hàng giữa các thời điểm | Hành vi được kiểm tra theo database semantics |
| Pool release/reborrow | Connection A close, B borrow | Không giả định same physical session |
| Database restore/migration | IDs từ môi trường cũ | Không tái sử dụng như business PK |
| Security | Không log raw IDs/connection secrets | Chỉ ghi diagnostic được phép |
| SQL dialect | PostgreSQL/SQLite/Oracle | Không suy `ctid`/`rowid` = JDBC `RowId` |
| Isolation | Concurrent writers | Kiểm tra lock/version/update count |
| Driver upgrade | Thay JDBC driver/JDK | Re-run capability/feature tests |

**Đừng ép fake test làm “bằng chứng production”.** Test Java thuần có 29 PASS chứng minh bạn dùng đúng Java API và chính sách; integration test với database thật mới chứng minh driver hỗ trợ SQL ROWID với schema/SQL và workflow của bạn.

### Test bất biến cho RowId

Với hai RowId được driver cấp trong **cùng bảng, cùng data source và đang còn hiệu lực**:
- `a.equals(b)` true → chúng đại diện cùng ROWID theo Javadoc.
- `a.equals(b)` true → `a.hashCode() == b.hashCode()` theo Java equality contract.
- Đừng dùng byte equality hoặc `toString()` equality **một mình** để suy cùng row across sources/tables.

Với RowId khác nguồn/table, không có giả định portable về uniqueness toàn hệ thống.

## 14. Lưu ý bảo mật, hiệu năng và vận hành

**Đừng biến RowId thành user-facing secret hoặc access token.** Một identifier của database không thay thế authorization. Mọi query sử dụng RowId vẫn phải áp dụng quyền user/tenant và server policy.

**Đừng đặt RowId vào cache lâu dài** trừ khi có contract rõ: phạm vi lifetime, database/table identity, invalidation, row movement và xóa bản ghi. Cache theo business PK an toàn và portable hơn.

**Không gửi `RowId.toString()` vào SQL bằng string concatenation**. Dùng `PreparedStatement.setRowId` khi hỗ trợ; nếu không, dùng PK hoặc documented vendor API. Thói quen nối chuỗi vừa không portable vừa khó bảo đảm injection safety.

**Không lấy RowId như tối ưu mặc định.** Query theo indexed PK thường đã tối ưu và đơn giản. Bất kỳ lợi ích của ROWID cần được chứng minh trên database thật bằng profiling, không chỉ vì nó nghe giống “physical address”.

**Không chuyển RowId giữa microservices như global identifier**. Nếu hai hệ thống dùng different database/schema/table, RowIds không có identity contract chung; dùng event ID/PK/UUID theo schema.

**Giữ transactions ngắn** nếu workflow cần same-transaction RowId. Transaction dài và locking có thể ảnh hưởng concurrency/performance.

**Chú ý connection pool**. `ROWID_VALID_SESSION` không có nghĩa hai lần `DataSource.getConnection()` được bảo đảm cùng physical session. Trả connection về pool kết thúc scope của application.

**Nếu RowIdLifetime là OTHER**, luôn ghi ra một trạng thái chưa xác định thay vì map về “FOREVER” hoặc “SESSION” tùy tiện. Chỉ bật feature nếu vendor/DB docs cung cấp hợp đồng rõ ràng và integration test đủ mạnh.

## 15. Lỗi phổ biến cần tránh

**1. Coi RowId là primary key luôn ổn định.**  
Sai. RowId là SQL row locator do driver/data source quyết định; PK mới thường là identity logic dài hạn.

**2. Không đọc `DatabaseMetaData.getRowIdLifetime()` trước khi sử dụng.**  
Sai khi workflow phụ thuộc lifetime; cần capability detection và handling cho cả 5 enum values.

**3. Coi `ROWID_VALID_TRANSACTION` nghĩa RowId chắc chắn mất ngay sau COMMIT.**  
Không. Nó bảo đảm **ít nhất** transaction, không kết luận điều gì lâu hơn.

**4. Coi `ROWID_VALID_SESSION` có hiệu lực qua mọi connection của cùng pool.**  
Không. Borrowed logical handles không chắc cùng physical session.

**5. Coi `ROWID_VALID_FOREVER` như một PK vĩnh viễn của business entity.**  
Không. Nó không loại bỏ chuyện row bị xóa, đổi source/table hoặc concurrency.

**6. Coi `ROWID_VALID_OTHER` tương đương `FOREVER`.**  
Không. Đây là lifetime **indeterminate**. Policy bảo thủ nên không chấp nhận mặc định.

**7. Gọi `getRowId` trên mọi ResultSet dù query không có ROWID.**  
Sai. Phải chọn đúng cột/pseudocolumn của database.

**8. Nhầm `ResultSet.getRow()` với `ResultSet.getRowId()`.**  
Một cái là vị trí cursor; một cái là SQL ROWID typed value.

**9. Ghép `RowId.toString()` vào SQL literal.**  
Không portable; Javadoc không bảo đảm đây là SQL literal. Dùng typed `setRowId`.

**10. Tưởng `RowId.getBytes()` luôn có cùng độ dài hoặc bằng UTF-8 toString.**  
Sai. Bytes representation và length do driver quyết định.

**11. So hai RowId từ hai data sources rồi suy chúng cùng row.**  
Javadoc cảnh báo chúng **có thể equals** nhưng khác row; luôn xét source/table/lifetime.

**12. Không xử lý `null` từ `getRowId`.**  
SQL NULL có thể thành Java `null`.

**13. Không xử lý `SQLFeatureNotSupportedException`.**  
API tồn tại trong JDBC không buộc mọi driver hỗ trợ method.

**14. Giữ RowId trong hàng đợi/event message nhiều ngày khi chỉ có session lifetime.**  
Không có bảo đảm. Dùng business PK.

**15. Dùng PostgreSQL `ctid` làm định danh hàng lâu dài.**  
PostgreSQL documents ghi rõ `ctid` thay đổi sau UPDATE/move và không phải PK.

**16. Coi SQLite `rowid` là một object `java.sql.RowId` trên mọi JDBC driver.**  
Không. SQLite semantics và JDBC driver support là hai hợp đồng khác nhau.

**17. Không kiểm tra affected row count khi UPDATE bằng RowId.**  
Có thể update 0 row do row không tồn tại/không match; kiểm tra theo kỳ vọng.

**18. Tưởng metadata status đủ chứng minh SQL update chạy.**  
Chưa. Còn dialect, privileges, column mapping, driver support và transaction state.

**19. Dùng RowId để bỏ qua tenant filtering/authorization.**  
Sai. Identifier không là quyền truy cập; vẫn cần scope user/tenant và SQL policy.

**20. Không quản lý transaction và connection lifecycle.**  
RowId lifetime phụ thuộc transaction/session; try-with-resources và commit/rollback phải rõ ràng.

## 16. Câu hỏi tự kiểm tra

**1. `java.sql.RowId` biểu diễn gì?**  
Ánh xạ Java của SQL ROWID, một dạng địa chỉ hàng mà ý nghĩa logic/vật lý do data source quyết định.

**2. Method chuẩn kiểm tra RowId có hiệu lực bao lâu là gì?**  
`connection.getMetaData().getRowIdLifetime()`.

**3. Enum `RowIdLifetime` có mấy giá trị?**  
Năm: `ROWID_UNSUPPORTED`, `ROWID_VALID_OTHER`, `ROWID_VALID_TRANSACTION`, `ROWID_VALID_SESSION` và `ROWID_VALID_FOREVER`.

**4. `ROWID_VALID_TRANSACTION` có nghĩa RowId chỉ tồn tại đến COMMIT và chắc chắn invalid sau đó không?**  
Không. Nó bảo đảm **ít nhất** trong transaction, không cam kết sau đó.

**5. `ROWID_VALID_SESSION` có bảo đảm qua một connection mới của pool không?**  
Không. Connection pool có thể cấp physical session khác.

**6. `ROWID_VALID_FOREVER` có bảo đảm row không bị xóa không?**  
Không. Nó mô tả hiệu lực RowId từ data source, không bảo đảm hàng còn tồn tại hoặc thay thế PK.

**7. `getRowId("rid")` khác `getRow()` thế nào?**  
`getRowId` đọc giá trị SQL ROWID, `getRow` là số thứ tự của cursor.

**8. SQL NULL trong cột ROWID trả về Java giá trị gì?**  
`null` theo `ResultSet.getRowId`.

**9. `setRowId` có portable ở mọi JDBC driver không?**  
Method là chuẩn JDBC, nhưng driver có thể không hỗ trợ và ném `SQLFeatureNotSupportedException`.

**10. Có thể dựng SQL bằng `rowId.toString()` không?**  
Không nên. Format không nhất thiết là ROWID SQL literal; bind qua `setRowId`.

**11. So bằng nhau của hai RowId khác bảng có chứng minh cùng row không?**  
Không. Javadoc yêu cầu xét cùng bảng, cùng data source và còn hiệu lực.

**12. PostgreSQL `ctid` có phải key lâu dài không?**  
Không. Nó mô tả vị trí physical row version, thay đổi khi UPDATE hoặc move.

**13. Nếu metadata trả `ROWID_VALID_OTHER`, nên xử lý mặc định thế nào?**  
Không suy tự động một lifetime chuẩn; fallback sang PK hoặc yêu cầu hợp đồng vendor.

**14. Tại sao phải test trên database thật sau khi demo JDK-only 29 PASS?**  
Vì mock chỉ chứng minh Java API behavior; database thực tế còn driver, SQL dialect, table mapping, transaction/isolation và permissions.

**15. Khi nào nên chọn PK thay cho RowId?**  
Khi dữ liệu cần identity logic, tồn tại lâu dài, qua sessions/services, hoặc cần portability; đó là mặc định tốt cho phần lớn CRUD.

## 17. Nguồn tham khảo chính thức còn hiệu lực

- [Oracle Java SE 26 — `java.sql.RowId`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/RowId.html): định nghĩa ROWID, bytes/strings, caveat của `equals` về nguồn/bảng/lifetime.
- [Oracle Java SE 26 — `java.sql.RowIdLifetime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/RowIdLifetime.html): năm enum values và minimum validity.
- [Oracle Java SE 26 — `java.sql.DatabaseMetaData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getRowIdLifetime()` và database capability metadata.
- [Oracle Java SE 26 — `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getRowId(int/String)`, cursor và SQL NULL.
- [Oracle Java SE 26 — `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setRowId(int, RowId)` và `SQLFeatureNotSupportedException`.
- [Oracle Java SE 26 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): connection, transactions, lifetime/close.
- [Oracle Java SE 26 — `java.sql.SQLFeatureNotSupportedException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): method không được driver hỗ trợ.
- [Oracle Java SE 26 — `java.sql.Types`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Types.html): SQL type code `ROWID` nếu driver trả metadata type phù hợp.
- [Oracle Database 26 JDBC — `oracle.sql.ROWID`](https://docs.oracle.com/en/database/oracle/oracle-database/26/jajdb/oracle/sql/ROWID.html): mapping ROWID của Oracle driver; một implementation cụ thể, không đồng nghĩa toàn bộ chuẩn.
- [Oracle JDBC FAQ](https://www.oracle.com/database/technologies/faq-jdbc.html): cách Oracle driver expose ROWID trong ResultSet và bind operations.
- [PostgreSQL 18 — System Columns, `ctid`](https://www.postgresql.org/docs/current/ddl-system-columns.html): `ctid` là vị trí row version, thay đổi khi UPDATE/`VACUUM FULL`; primary key dùng cho identity logic.

**Ghi nhớ:** `RowIdLifetime` trả lời “data source bảo đảm **tối thiểu** RowId còn hiệu lực trong phạm vi nào?”, chứ không trả lời “đây có phải khóa chính vĩnh viễn không?”. Hãy kiểm tra metadata, thao tác bằng `getRowId/setRowId` khi hỗ trợ, giữ cùng nguồn/bảng và transaction/session phù hợp, kiểm tra update count, và ưu tiên **primary key** cho định danh nghiệp vụ lâu dài.
