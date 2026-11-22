# SQLSyntaxErrorException và SQLInvalidAuthorizationSpecException trong JDBC (Java 17+)

## 1. Khi nào gặp hai ngoại lệ này?

Trong ứng dụng Java dùng JDBC, lỗi không chỉ xuất hiện khi server ngắt kết nối. Hai tình huống thường gặp ở các giai đoạn khác nhau:

- **Câu lệnh SQL không hợp lệ**: SQL viết sai ngữ pháp, gọi bảng/cột không tồn tại, dùng cú pháp không tương thích dialect DBMS, hoặc vi phạm các quy tắc truy cập liên quan SQL. JDBC có subclass `java.sql.SQLSyntaxErrorException` dành cho nhóm lỗi có SQLState **class `42`** hoặc các trường hợp khác do driver vendor quy định.
- **Thông tin xác thực/ủy quyền khi thiết lập kết nối không hợp lệ**: sai username/password, cấu hình authentication không phù hợp, credential hết hiệu lực hoặc một quy tắc đăng nhập bị từ chối tùy DBMS. JDBC có subclass `java.sql.SQLInvalidAuthorizationSpecException` dành cho SQLState **class `28`** hoặc trường hợp do driver vendor quy định.

Cả hai là **`SQLNonTransientException`**: theo phân loại JDBC, retry **cùng yêu cầu với cùng điều kiện** không được kỳ vọng sẽ tự thành công nếu chưa sửa nguyên nhân. Không giải quyết bằng vòng lặp retry nhanh vô hạn.

Hai ngoại lệ được khai báo trong **module `java.sql`**, có mặt từ JDBC 4 và vẫn được hỗ trợ ở Java 17, 21, 25 và các JDK hiện đại. Không cần dùng API legacy hoặc tự tạo thư viện lỗi để đọc các thông tin mà `SQLException` đã cung cấp.

Tình huống điển hình:

```text
        Java application
                |
       DataSource/DriverManager
                |
      JDBC connection handshake
                |
       credential/authentication
                |
             lỗi class 28
                |
    SQLInvalidAuthorizationSpecException

         Connection OK
                |
     PreparedStatement/execute
                |
      parse/bind/plan/check rules
                |
            lỗi class 42
                |
       SQLSyntaxErrorException
```

**Quan trọng:** sơ đồ giúp hiểu nguyên nhân phổ biến, **không bảo đảm một JDBC driver nhất định sẽ ném đúng subclass** trong mọi trường hợp. Một driver có thể ném `SQLException` chung với SQLState phù hợp, hoặc một loại ngoại lệ riêng theo vendor. Cần kiểm tra **subclass + SQLState + vendor code + tài liệu driver**, không chỉ kiểm tra tên class.

Mục tiêu bài học:
1. Biết chính xác class hierarchy và ý nghĩa SQLState `42`/`28`.
2. Phân biệt lỗi cú pháp SQL, lỗi quyền truy cập bảng và lỗi xác thực lúc kết nối.
3. Đọc `getSQLState()`, `getErrorCode()`, `getNextException()`, `getCause()` an toàn.
4. Bắt ngoại lệ theo đúng thứ tự, thiết kế retry/fallback thực tế.
5. Viết code JDBC parameterized, cấu hình credentials an toàn và observability phù hợp.
6. Chạy ví dụ Java 17+ độc lập không cần database, sau đó áp dụng vào integration test với driver thật.

## 2. Cây kế thừa: SQLException → SQLNonTransientException

```text
java.lang.Exception
  |
  +-- java.sql.SQLException
          |
          +-- java.sql.SQLNonTransientException
                   |
                   +-- SQLSyntaxErrorException
                   |
                   +-- SQLInvalidAuthorizationSpecException

Các nhánh khác của SQLException:
  +-- SQLTransientException       (một nhóm lỗi có thể thử lại)
  +-- SQLRecoverableException     (cần bước recovery)
  +-- SQLWarning                  (cảnh báo)
```

Hai class trong chủ đề **không trực tiếp extends SQLException**; chúng extends `SQLNonTransientException`, mà lớp này extends `SQLException`.

| Class | Nhóm | Ý nghĩa chung |
| --- | --- | --- |
| `SQLException` | Gốc | Lỗi truy cập dữ liệu/JDBC có SQLState, vendor code và chain. |
| `SQLNonTransientException` | Không tạm thời theo contract | Sửa điều kiện/nguyên nhân trước khi thử lại. |
| `SQLSyntaxErrorException` | Non-transient | SQLState class `42` hoặc điều kiện do vendor chỉ định; vấn đề câu lệnh SQL/quy tắc truy cập. |
| `SQLInvalidAuthorizationSpecException` | Non-transient | SQLState class `28` hoặc điều kiện do vendor chỉ định; credential/authorization lúc lập kết nối không hợp lệ. |
| `SQLTransientException` | Có khả năng tạm thời | Cùng operation có thể thành công khi retry nếu điều kiện thay đổi tự nhiên, nhưng vẫn cần policy giới hạn. |
| `SQLRecoverableException` | Cần recovery | Có thể phải tái tạo connection hoặc khôi phục trạng thái trước khi retry toàn bộ transaction. |

**Từ “non-transient” không đồng nghĩa “sự cố vĩnh viễn”**. Nếu sửa SQL, hoàn tất migration, cấp quyền đúng hoặc xoay credential hợp lệ, operation có thể thành công. Nó có nghĩa **retry y nguyên mà không sửa nguyên nhân** không được xem là cách xử lý thích hợp.

Cũng không suy kết luận ngược: nếu driver chỉ ném `SQLException` chung, không thể kết luận lỗi transient. **Runtime subclass** và **khả năng retry thực tế** là hai thông tin khác nhau.

### 2.1. Constructor của hai lớp

Hai lớp đều có những constructor phổ biến:

```java
new SQLSyntaxErrorException(
        "Invalid SQL", "42601", 0);

new SQLInvalidAuthorizationSpecException(
        "Invalid credentials", "28P01", 0);
```

Đây là **snippet để tạo lỗi mô phỏng**, không phải lỗi đã được driver tạo ra. SQLState minh họa theo cách đặt mã thường gặp ở PostgreSQL: `42601` liên quan syntax error, `28P01` liên quan invalid password. Những chuỗi này **không phải output bắt buộc của mọi DBMS**. `vendorCode=0` được truyền trực tiếp vào constructor chứ không phải mã mặc định phải xuất hiện khi database lỗi.

Ngoài constructor ba tham số còn có overload với `Throwable cause`:

```java
new SQLSyntaxErrorException(
        "Database rejected SQL", "42000", 101, cause);
```

Đây là snippet, với `Throwable cause` đã có; không phải file Java độc lập. `reason` là diagnostic message, `SQLState` thường gồm năm ký tự, `vendorCode` là số do vendor xác định, `cause` lưu lỗi gốc. Tự tạo subclass không khiến JDBC engine tự thực thi SQL hay kiểm tra credential.

## 3. SQLSyntaxErrorException: SQLState class 42

Theo Javadoc Java SE 17/25, `SQLSyntaxErrorException` là subclass của `SQLNonTransientException` được dùng khi **SQLState class `42`** hoặc dưới các điều kiện vendor-specific.

**SQLState class** là hai ký tự đầu của chuỗi SQLState. Trong quy ước SQL chuẩn, class `42` thường được mô tả là **“syntax error or access rule violation”**. Vì vậy, khi xử lý ứng dụng, nhóm này rộng hơn câu chữ “SQL typo” trong tên Java class.

Ví dụ:
- `SELECT` thiếu từ khóa, dấu phẩy, dấu ngoặc hoặc biểu thức không hợp lệ.
- Truy vấn nhầm cột/bảng/schema sau khi thay đổi migration.
- SQL dialect khác nhau: cú pháp hợp lệ ở DBMS A nhưng không hợp lệ ở B.
- Câu SQL bị từ chối do **SQL access rule** hoặc thiếu quyền cho bảng/view theo cách driver biểu diễn.
- Tham chiếu object bị ẩn hoặc không tồn tại với principal hiện tại.
- Query tạo bởi ứng dụng có dấu nháy/identifier không đúng dialect.

**Không khẳng định mọi lỗi thiếu bảng hoặc thiếu quyền đều thuộc class `42` trên mọi driver.** DBMS thường có nhiều error codes và subclass mapping khác nhau; driver có thể ném `SQLException` chung hoặc loại khác dù SQLState có tiền tố `42`.

### 3.1. SQLState class 42 và vendor codes: ví dụ, không phải bảng chuẩn toàn cầu

| SQLState ví dụ | Diễn giải thường gặp | Chú ý tính portable |
| --- | --- | --- |
| `42000` | Syntax error/access rule violation tổng quát. | Nhiều driver dùng code này nhưng ngữ cảnh và vendor code khác nhau. |
| `42601` | PostgreSQL: syntax_error. | Vendor-specific subclass code, không phải mọi DBMS đều sử dụng. |
| `42501` | PostgreSQL: insufficient_privilege. | Thuộc class `42` dù vấn đề chính là privilege; không nhất thiết là câu SQL viết sai. |
| `42S02` | SQLSTATE thường dùng ở một số hệ để báo base table/view not found. | Không đồng nhất trên các DBMS; cần vendor docs. |

**Điểm dễ nhầm:** `SQLSyntaxErrorException` không phải một trình phân tích cú pháp Java có thể sửa SQL cho bạn. Nó chỉ mô tả **nhóm lỗi do driver cung cấp**. App không nên lấy SQL text từ exception rồi tự thêm/bỏ ký tự để retry, vì có thể tạo SQL injection hoặc thao tác sai dữ liệu.

### 3.2. Sửa lỗi loại 42 trong vòng đời triển khai

Khi lỗi này xuất hiện:
1. Xác định operation và SQL statement **đã được chuẩn hóa/kiểm soát**, tránh in raw user input hoặc secrets.
2. Kiểm tra `getSQLState()`, `getErrorCode()` và error chain.
3. Đối chiếu **schema thực**, migrations đã áp dụng, tên cột/bảng, schema search path và identifier quoting.
4. Kiểm tra dialect SQL của database đang chạy và JDBC driver version.
5. Nếu SQLState thể hiện **access rule violation**, kiểm tra database principal/roles/grants. Không tự đổi mật khẩu chỉ vì subclass tên “syntax”.
6. Sửa SQL/migration/cấp quyền theo nguyên tắc least privilege và chạy integration test.
7. **Không retry nhanh vô hạn** với cùng SQL chưa sửa.

Ví dụ câu SQL sau là *sai có chủ ý*:

```sql
SELEC user_id FROM app_users WHERE user_id = ?
```

Khi thực thi, DBMS có thể báo lỗi parser, thường liên quan class `42`, nhưng **không có nghĩa mọi JDBC driver chắc chắn ném `SQLSyntaxErrorException`**. Với câu SQL hợp lệ, dùng placeholder cho dữ liệu:

```sql
SELECT user_id FROM app_users WHERE user_id = ?
```

Dấu `?` là bind parameter cho **giá trị**, không thay thế được tên bảng/cột hay từ khóa SQL. Không tạo SQL bằng cách nối `"WHERE name = '" + input + "'"`. Khi SQL object name phải động, dùng allowlist và quoting phù hợp DBMS.

## 4. SQLInvalidAuthorizationSpecException: SQLState class 28

`SQLInvalidAuthorizationSpecException` là subclass `SQLNonTransientException` được dùng khi **SQLState class `28`** hoặc điều kiện vendor-specific. Theo Javadoc, nó chỉ ra **authorization credentials gửi trong quá trình thiết lập kết nối không hợp lệ**.

Các khả năng cần điều tra (phụ thuộc DBMS/driver):
- Username/password không đúng hoặc tài khoản bị khóa/hết hạn.
- Ứng dụng đang dùng nhầm secret của môi trường dev/staging/prod.
- Credential rotation đã diễn ra nhưng service/pool chưa được cập nhật.
- Authentication method, database principal hoặc connection endpoint không phù hợp.
- Server policy từ chối một principal trong bước connection authorization.
- Driver/server phát sinh thông báo class `28` với mã cụ thể về truy cập.

Ví dụ:
- SQLState `28000` thường dùng cho nhóm *invalid authorization specification*.
- SQLState `28P01` ở PostgreSQL thường nghĩa *invalid_password*.

Đây là **ví dụ theo quy ước SQLState/vendor**, không phải tất cả database đều trả `28000` hoặc `28P01` trong trường hợp password sai. Có driver báo `SQLException` chung, `SQLNonTransientConnectionException` hoặc mã khác; cần tài liệu của chính vendor.

### 4.1. Xác thực lúc kết nối khác quyền thực thi SQL

Đây là phân biệt trung tâm của chủ đề.

| Tình huống | Ví dụ | Nhóm cần điều tra |
| --- | --- | --- |
| Không đăng nhập được DB | Credential sai, tài khoản hết quyền CONNECT. | Authentication/authorization khi **connection establishment**, thường class `28`. |
| Đăng nhập DB được nhưng không được `SELECT` bảng | Connection OK, query bị từ chối do GRANT/role. | Quy tắc truy cập **ở mức SQL statement**, có thể class `42`/`42501` tùy vendor. |
| Câu SQL sai cú pháp | Gõ `SELEC`. | SQL parser/dialect, thường class `42`. |
| Kết nối bị ngắt | Network/socket/server restart. | Có thể class `08` và các connection exceptions; **không tự gán** là class `28`. |
| Vi phạm foreign key/unique key | INSERT duplicate key, FK không tồn tại. | Thường class `23`/`SQLIntegrityConstraintViolationException`, không phải hai class này. |

**Không đánh đồng database login với end-user login.** Nếu ứng dụng web dùng service account để nối DB mà secret bị sai, lỗi `SQLInvalidAuthorizationSpecException` là sự cố **cấu hình/backend**. Không tự trả thông báo “mật khẩu của người dùng cuối sai” chỉ vì database connection thất bại.

**Không giải quyết mọi permission failure bằng đổi database password.** Nếu connection đã thành công và statement bị từ chối do `GRANT`, sửa roles/quyền/schema mới là hướng liên quan; giữ nguyên nguyên tắc cấp quyền tối thiểu.

### 4.2. Kiểm tra quyền an toàn

Một quy trình điều tra:
1. Xác định environment/endpoint đang được kết nối (không in toàn bộ JDBC URL chứa secret).
2. Kiểm tra datasource/connection pool sử dụng **đúng principal**, chính sách authentication, mật khẩu/token mới.
3. Kiểm tra secret manager, vòng đời rotation, version của config và thời gian cache credential.
4. Kiểm tra account lock/expiration, quyền CONNECT hoặc mapping auth do DBMS quy định.
5. Nếu SSL/TLS handshake lỗi, xác định đó là lỗi network/TLS hay credentials, không tự suy dựa trên thông báo ngắn.
6. Sửa cấu hình/credential theo quy trình của tổ chức, không retry hàng nghìn lần khiến account lockout nặng hơn.
7. Sau khi sửa, thiết lập lại connection pool (nếu cần), test connection có kiểm soát và khôi phục hoạt động.

**Cảnh báo:** Không log password, token, private key, connection string chứa credentials hoặc nội dung SQL tham số nhạy cảm. Một số driver exception message/cause có thể bao gồm thông tin kết nối; không xuất nguyên message ra log công khai nếu chưa rà soát.

## 5. SQLException cung cấp thông tin chẩn đoán nào?

Hai subclass kế thừa các method của `SQLException`:

| Method | Trả về | Ứng dụng |
| --- | --- | --- |
| `getSQLState()` | `String` (có thể null) | Xem nhóm class `42`, `28` và các trạng thái chi tiết. |
| `getErrorCode()` | `int` | Mã lỗi vendor-specific; code `0` không tự kết luận “không có lỗi”. |
| `getMessage()` | `String` | Lời giải thích của driver, có thể chứa thông tin nhạy cảm. |
| `getNextException()` | `SQLException` hoặc null | Đọc các lỗi SQL được driver chain. |
| `getCause()` | `Throwable` hoặc null | Lỗi underlying network/auth/parser/driver. |
| `iterator()` | `Iterator<Throwable>` | Duyệt SQLExceptions và causes theo iterator API. |
| `getSuppressed()` | `Throwable[]` | Các lỗi khác bị suppress trong try-with-resources/rollback. |

**SQLState không nhất thiết luôn có:** constructor `new SQLException("message")` không tự tạo SQLState, nên `getSQLState()` có thể là `null`. Vì thế, **đừng viết `ex.getSQLState().startsWith("42")`** khi chưa kiểm tra null.

**SQLState không phải vendor code:** `getSQLState()` là mã chuỗi theo quy tắc XOPEN/SQL standard mà driver công bố; `getErrorCode()` là số nguyên vendor-specific. Chúng không thay thế nhau.

**SQLState class** thường là hai ký tự đầu, còn ba ký tự sau cho subcondition. Muốn quyết định hành động theo SQLState nên dùng **bảng mapping có test cho driver thực tế**, thay vì chỉ tiền tố hai ký tự để quyết định hướng recovery phức tạp. Đặc biệt class `42` bao gồm cả SQL access rule violation, không thuần parser typo.

### 5.1. getSQLStateType

`DatabaseMetaData.getSQLStateType()` có thể cho biết driver sử dụng quy ước SQLState kiểu XOPEN hay SQL-standard. Với một môi trường tích hợp cần tương thích nhiều driver, kiểm tra metadata/vendor docs thay vì giả định mọi subcode có cùng ý nghĩa. Chỉ phân nhóm `28`/`42` là một bước chẩn đoán sơ bộ, không phải cơ chế phiên dịch SQLState hoàn chỉnh.

### 5.2. getNextException khác getCause

`SQLException.getNextException()` tạo **chuỗi các SQL exceptions** mà driver cung cấp thêm; `Throwable.getCause()` là nguyên nhân gốc của **một lỗi**. Một exception có thể đồng thời có cả hai. `SQLException` cũng implements `Iterable<Throwable>` để duyệt chain và causes.

Ví dụ:

```java
SQLException head =
        new SQLException("Operation failed", "HY000", 5);

head.setNextException(
        new SQLSyntaxErrorException("Bad SQL", "42000", 7));

for (SQLException current = head;
        current != null;
        current = current.getNextException()) {
    System.out.println(
            current.getSQLState() + ":" + current.getErrorCode());
}
```

Đây là **snippet**, có imports `java.sql.SQLException`, `SQLSyntaxErrorException`. Nó duyệt chain `getNextException()`, **không tự duyệt cause/suppressed exceptions**. Với driver tạo chain bất thường hoặc rất dài, production cần giới hạn số items log; không in nguyên messages chứa thông tin nhạy cảm.

`getNextException` không phải `getSuppressed()`. Try-with-resources có thể suppress lỗi khi đóng `Connection`/`Statement`; đọc suppressed khi điều tra cleanup thất bại, không coi suppressed là lỗi gốc của SQL statement.

## 6. Demo Java 17+ chạy độc lập: phân loại hai nhóm và SQLState

Để học contract mà không phụ thuộc JDBC driver, chúng ta **tự tạo exception bằng constructor chính thức của JDK**. Ví dụ kiểm tra:
- `instanceof SQLSyntaxErrorException` và `instanceof SQLInvalidAuthorizationSpecException`.
- SQLState class `42`/`28` khi driver **chỉ đưa ra `SQLException`**.
- `SQLNonTransientException` là class-hierarchy runtime, không phải thuật toán quyết định retry tự động.
- SQLState `null` xử lý an toàn.
- `getNextException()` duyệt chuỗi SQL exceptions.

Tạo file **`JdbcExceptionClassifierDemo.java`**:

```java
import java.sql.SQLException;
import java.sql.SQLNonTransientException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLInvalidAuthorizationSpecException;

public final class JdbcExceptionClassifierDemo {

    enum Category {
        SQL_STATEMENT_OR_ACCESS_RULE,
        INVALID_LOGIN_AUTHORIZATION,
        OTHER
    }

    static Category classify(SQLException ex) {
        if (ex instanceof SQLInvalidAuthorizationSpecException) {
            return Category.INVALID_LOGIN_AUTHORIZATION;
        }
        if (ex instanceof SQLSyntaxErrorException) {
            return Category.SQL_STATEMENT_OR_ACCESS_RULE;
        }

        String state = ex.getSQLState();
        if (state == null || state.length() < 2) {
            return Category.OTHER;
        }

        return switch (state.substring(0, 2)) {
            case "28" -> Category.INVALID_LOGIN_AUTHORIZATION;
            case "42" -> Category.SQL_STATEMENT_OR_ACCESS_RULE;
            default -> Category.OTHER;
        };
    }

    private static void show(SQLException ex) {
        System.out.println(ex.getClass().getSimpleName()
                + " state=" + ex.getSQLState()
                + " category=" + classify(ex)
                + " nonTransientType="
                + (ex instanceof SQLNonTransientException));
    }

    public static void main(String[] args) {
        show(new SQLSyntaxErrorException(
                "Invalid statement", "42601", 0));
        show(new SQLInvalidAuthorizationSpecException(
                "Invalid credentials", "28P01", 0));
        show(new SQLException(
                "Access rule violated", "42501", 0));
        show(new SQLException("No SQLState"));

        SQLException root = new SQLException(
                "Operation failed", "HY000", 5);
        root.setNextException(new SQLSyntaxErrorException(
                "SQL grammar problem", "42000", 7));

        int i = 0;
        for (SQLException next = root;
                next != null;
                next = next.getNextException()) {
            System.out.println("chain[" + i++ + "]="
                    + next.getSQLState()
                    + " vendorCode=" + next.getErrorCode());
        }
    }
}
```

### 6.1. Biên dịch và chạy

Với **JDK 17 trở lên**, không cần tải JDBC driver:

```bash
javac -encoding UTF-8 JdbcExceptionClassifierDemo.java
java JdbcExceptionClassifierDemo
```

**Stdout chính xác đã kiểm chứng bằng `javac` và `java`:**

```text
SQLSyntaxErrorException state=42601 category=SQL_STATEMENT_OR_ACCESS_RULE nonTransientType=true
SQLInvalidAuthorizationSpecException state=28P01 category=INVALID_LOGIN_AUTHORIZATION nonTransientType=true
SQLException state=42501 category=SQL_STATEMENT_OR_ACCESS_RULE nonTransientType=false
SQLException state=null category=OTHER nonTransientType=false
chain[0]=HY000 vendorCode=5
chain[1]=42000 vendorCode=7
```

### 6.2. Giải thích từng phần output

1. `SQLSyntaxErrorException` với `42601` được phân loại **SQL_STATEMENT_OR_ACCESS_RULE**, bởi subclass đúng và class `42`.
2. `SQLInvalidAuthorizationSpecException` với `28P01` được phân loại **INVALID_LOGIN_AUTHORIZATION**, bởi subclass đúng và class `28`.
3. `SQLException` chung với `42501` **không** là instance của `SQLNonTransientException` nên `nonTransientType=false`; tuy nhiên classifier vẫn nhận class `42` từ SQLState. Điều này chứng minh **phân loại qua SQLState khác phân loại theo runtime class**.
4. `SQLException` không có SQLState trả `null`, không làm chương trình lỗi `NullPointerException` vì đã kiểm tra.
5. Hai dòng `chain` chứng minh `setNextException` và `getNextException` có thể lưu/đọc thêm SQL exceptions với state và vendor code khác nhau.

**Giới hạn của ví dụ:** Nó tự tạo exception; không kiểm tra JDBC driver nào ném type nào, không kết nối database và không chứng minh `42601`/`28P01` là mã portable toàn cầu. `classify` trả loại chẩn đoán **sơ bộ**; không quyết định xử lý đặc thù như đổi credential, chỉnh quyền SQL hoặc retry khi chưa có bằng chứng từ hệ thống thực.

### 6.3. Tại sao đặt tên SQL_STATEMENT_OR_ACCESS_RULE?

Nếu đặt tên `SYNTAX_TYPO` cho mọi SQLState bắt đầu bằng `42`, bạn có thể hướng người vận hành sửa câu SQL trong khi lỗi thật là `42501`: principal không có `SELECT` hoặc quy tắc truy cập bị từ chối. Nhóm rộng hơn giúp tránh kết luận sai; sau đó dùng SQLState đầy đủ, vendor code và driver docs để chẩn đoán.

### 6.4. Khi subtype và SQLState mâu thuẫn

Javadoc cho phép **vendor-specified conditions**. Nếu nhận `SQLSyntaxErrorException` nhưng SQLState khác `42`, hay `SQLInvalidAuthorizationSpecException` với SQLState null, đó không nhất thiết là bug trong code của bạn. Trong ví dụ, classifier xét subtype trước và SQLState fallback sau; production nên ghi nhận cả hai và có logic không tự động retry/rotate secret khi tín hiệu mâu thuẫn.

## 7. Chương trình JDBC Java 17+ có thể biên dịch, cần driver/DB để chạy

Đoạn sau minh họa lỗi đăng nhập có thể xảy ra khi **mở connection**, trong khi lỗi class `42` có thể xảy ra khi **prepare hoặc execute câu SQL**. Code không yêu cầu driver ở compile time (chỉ dùng `java.sql`), nhưng để chạy phải có database/driver và schema tương ứng.

Ứng dụng giả định một bảng:

```sql
-- SQL chỉ minh họa, cần tạo bảng theo dialect/schema của DBMS.
-- app_users(user_id BIGINT, display_name VARCHAR(...))
SELECT display_name FROM app_users WHERE user_id = ?
```

Bảng/SQL phải được chỉnh cho database thật. Không khẳng định driver nào cũng hỗ trợ bảng tên `app_users`. SQL `?` dùng để bind **userId**, không nối user input vào câu SQL.

### 7.1. File JdbcFailureHandling.java

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLInvalidAuthorizationSpecException;
import java.sql.SQLSyntaxErrorException;
import java.util.Properties;

public final class JdbcFailureHandling {

    private static void report(SQLException e) {
        for (SQLException current = e;
                current != null;
                current = current.getNextException()) {

            String state = current.getSQLState();
            String category;

            if (current instanceof SQLInvalidAuthorizationSpecException
                    || (state != null && state.startsWith("28"))) {
                category = "LOGIN_AUTHORIZATION";
            } else if (current instanceof SQLSyntaxErrorException
                    || (state != null && state.startsWith("42"))) {
                category = "SQL_STATEMENT_OR_ACCESS_RULE";
            } else {
                category = "OTHER_JDBC_FAILURE";
            }

            System.err.println("category=" + category
                    + " sqlState=" + state
                    + " vendorCode=" + current.getErrorCode());
        }
    }

    public static void main(String[] args) throws SQLException {
        if (args.length != 2) {
            System.err.println(
                "Usage: java JdbcFailureHandling <jdbc-url> <user-id>");
            return;
        }

        long userId = Long.parseLong(args[1]);
        Properties login = new Properties();

        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (user != null) {
            login.setProperty("user", user);
        }
        if (password != null) {
            login.setProperty("password", password);
        }

        try (Connection connection =
                     DriverManager.getConnection(args[0], login);
             PreparedStatement ps = connection.prepareStatement(
                "SELECT display_name FROM app_users WHERE user_id = ?")) {

            ps.setLong(1, userId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(rs.getString(1));
                }
            }
        } catch (SQLException e) {
            report(e);
            throw e;
        }
    }
}
```

### 7.2. Biên dịch

```bash
javac -encoding UTF-8 JdbcFailureHandling.java
```

Cả chương trình `JdbcFailureHandling.java` và `JdbcExceptionClassifierDemo.java` đã được **biên dịch thành công** trên JDK hiện đại. `JdbcFailureHandling` không có stdout cố định khi chưa biết URL, driver, credentials, schema và dữ liệu. Chỉ chương trình mô phỏng đầu tiên có **stdout xác định đã chạy kiểm chứng**.

### 7.3. Chạy trên Linux/macOS

Giả sử driver JAR của vendor được đặt tên `driver.jar` (đây là **tên giả định**); sử dụng JDBC URL của môi trường kiểm thử trong biến `JDBC_URL`:

```bash
java -cp ".:driver.jar" JdbcFailureHandling "$JDBC_URL" 42
```

Trên **Windows PowerShell** (classpath separator khác):

```powershell
java -cp '.;driver.jar' JdbcFailureHandling $env:JDBC_URL 42
```

Nếu cần credentials, demo đọc `DB_USER` và `DB_PASSWORD` từ environment. **Environment không phải secret vault**; production nên dùng secret manager, datasource/pool quản lý credentials và cấu hình TLS/connection security thích hợp. Không đặt password trong source, Git, JDBC URL, process arguments hoặc stdout. Trong công cụ build Maven/Gradle, đặt driver trong runtime dependencies; `driver.jar` không phải một artifact được JDK tự cài.

### 7.4. Vì sao catch một SQLException chung trong ví dụ JDBC?

Vì không thể bắt tất cả sự khác biệt driver chỉ bằng hai subclass. Code:
- Bắt một lần `SQLException` bao gồm lỗi khi connect, prepare hoặc execute.
- Xét `instanceof` trước, rồi xét SQLState **class `28`/`42`** nếu driver trả superclass.
- Duyệt `getNextException()` và chỉ in **category, SQLState, vendor code**, tránh in password/SQL values/message.
- Ném lại exception gốc để caller/connection pool có thể quản lý fail state; không giả định cứ log là có thể tiếp tục.
- **Không** tự retry khi category là `LOGIN_AUTHORIZATION` hoặc `SQL_STATEMENT_OR_ACCESS_RULE`.

Ví dụ chỉ là bước observability. Trong ứng dụng thật, trả response/health status thích hợp, quản lý rollback, pool reset và incident escalation theo bối cảnh service. Không tự sửa schema, cấp quyền hay đổi secret từ error handler.

## 8. Cách bắt chuyên biệt hai subclass trong service

Nếu driver xác nhận dùng đúng JDBC subclasses, có thể dùng nhiều nhánh catch:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
             "SELECT display_name FROM app_users WHERE user_id = ?")) {

    ps.setLong(1, userId);

    try (ResultSet rs = ps.executeQuery()) {
        // Tiêu thụ dữ liệu khi ResultSet còn mở.
    }

} catch (SQLInvalidAuthorizationSpecException e) {
    // Xác thực/ủy quyền lúc mở connection: kiểm tra secret,
    // principal và chính sách authentication.
} catch (SQLSyntaxErrorException e) {
    // Kiểm tra SQL dialect/schema, và có thể GRANT/access rules.
} catch (SQLException e) {
    // Các lỗi JDBC khác hoặc driver không dùng subclass cụ thể.
}
```

Đây là **snippet**, không phải file Java độc lập: `dataSource` là `javax.sql.DataSource` đã cấu hình, `userId` là long/biến hợp lệ; cần import các JDBC classes. Nhánh exception cụ thể nên **đặt trước** `catch (SQLException e)` vì chúng kế thừa `SQLException`; nếu catch superclass trước, các catch subclass sẽ không thể tới và compiler báo lỗi.

**Nhưng ngay cả khi dùng catch chuyên biệt, vẫn nên có nhánh SQLException chung**. Một số driver trả generic SQLException với SQLState có ý nghĩa; chỉ bắt hai subclass có thể làm mất phân loại. Nếu một JDBC operation đang chạy trong transaction có lỗi, xử lý rollback phù hợp và không tiếp tục sử dụng transaction/connection với giả định nó khỏe mạnh.

### 8.1. Không bắt sai chỗ

**`SQLInvalidAuthorizationSpecException` thường xuất hiện khi tạo connection**, trước khi code có PreparedStatement. Bắt nó chỉ quanh `ps.executeQuery()` không bao quát lỗi xác thực trong `dataSource.getConnection()`. Dùng try-with-resources hoặc try/catch bao cả connect + SQL execution, như hai ví dụ.

**`SQLSyntaxErrorException` có thể được phát hiện ở `prepareStatement` hoặc `executeQuery`** tùy driver/server có prepare trên server lúc nào. Không viết test phụ thuộc tuyệt đối rằng parser error chỉ ném khi gọi `executeQuery`.

## 9. Retry policy: vì sao hai loại lỗi này khác deadlock?

**Không retry y nguyên**:
- SQL viết sai cú pháp: câu SQL vẫn sai trong mỗi lần gửi.
- Thiếu bảng/schema: migration/schema chưa sửa.
- Thiếu privilege: chưa cấp quyền phù hợp.
- Credential đăng nhập sai: cùng password vẫn bị từ chối, retry dồn dập còn có thể khóa account hoặc tăng alert noise.

**Chỉ thử lại sau khi đã có hành động sửa nguyên nhân**, ví dụ:
- Deploy phiên bản SQL đúng/sửa migration.
- DBA cấp quyền chuẩn theo process, không tự động cấp đặc quyền mở rộng.
- Secret rotation hoàn tất, pool lấy credential mới và kết nối được tạo lại.
- DB configuration/role policy đã sửa.

So sánh với những lớp khác:
- `SQLTransientException`: lỗi được mô tả là có thể thành công khi retry không có thay đổi ở application-level, ví dụ một số contention/transient connection cases; vẫn phải có backoff và giới hạn.
- `SQLTransactionRollbackException`: có thể liên quan deadlock/serialization failure; nếu retry, phải thiết kế idempotency và **retry toàn bộ transaction** theo contract của DBMS.
- `SQLRecoverableException`: có thể cần đóng/tạo lại connection hoặc các bước recovery trước khi thử lại operation.
- `SQLNonTransientException`: nguyên nhân cần được sửa; retry-loop tự động thường vô ích.

**Không đưa mọi SQLState prefix vào một bảng “retry true/false” toàn cục** mà bỏ qua vendor docs và business semantics. Ví dụ `42501` là quyền SQL, không phải parsing typo, và hành động khắc phục khác. Một số lỗi hiển thị transient sau khi deployment/config rollout nhưng không vì vậy mà nên retry vô hạn ở tầng request.

### 9.1. Vòng lặp retry sai có chủ ý

```java
// Mẫu SAI: không sử dụng trong production.
for (;;) {
    try {
        executeBrokenSql();
        break;
    } catch (SQLSyntaxErrorException error) {
        // Lặp lại cùng câu SQL sai; không bao giờ sửa được nguyên nhân.
    }
}
```

Đây là **pseudocode**; `executeBrokenSql()` chưa được định nghĩa. Nó minh họa anti-pattern chứ không phải chương trình Java có thể chạy. Đối với `SQLInvalidAuthorizationSpecException`, vòng lặp tương tự với password cũ vừa không giúp gì vừa gây account lock hoặc làm DB authentication service quá tải.

## 10. SQL injection, quyền database và ranh giới tin cậy

Một backend có thể nhận “syntax error” không phải do developer viết sai, mà do **nối chuỗi SQL từ dữ liệu không tin cậy**:

```java
// SAI: SQL injection và quoting lỗi.
String sql = "SELECT * FROM app_users WHERE name = '"
        + userInput + "'";
```

Đây là snippet sai có chủ ý, không dùng trong thực tế. Nếu `userInput` chứa dấu quote hay SQL markup, có thể phát sinh lỗi syntax hoặc truy vấn bị thay đổi trái phép. **Không chữa bằng cách catch SQLSyntaxErrorException rồi xóa dấu quote và thử lại**.

Sử dụng parameter binding:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT user_id FROM app_users WHERE name = ?")) {

    ps.setString(1, userInput);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả, không nối giá trị vào SQL text.
    }
}
```

Đây là snippet trong method có `Connection connection`, `String userInput`. `PreparedStatement` bind dữ liệu thành parameter, giúp giảm nguy cơ SQL injection và lỗi quoting. Nó **không** cho phép bind table name/column name qua `?`; với SQL identifiers động phải có allowlist và identifier quoting theo vendor.

**Nguyên tắc least privilege**: kết nối chỉ cần quyền SQL phù hợp service. Khi gặp `42501`, việc cấp rộng `SUPERUSER` hoặc bỏ toàn bộ policy chỉ để query chạy là rủi ro nghiêm trọng. Kiểm tra grants cụ thể và migrations.

## 11. Quan sát lỗi: log an toàn và đủ dùng

Các trường tương đối an toàn để đưa vào log/metric **sau khi kiểm tra theo quy định tổ chức**:
- Một **operation ID** tự định nghĩa từ ứng dụng (không cần raw SQL text).
- Tên loại lỗi JDBC runtime (`SQLSyntaxErrorException`, `SQLException`…).
- SQLState đầy đủ (hoặc prefix) và vendor error code.
- Service/environment code không chứa secret.
- Connection pool identifier hoặc datasource alias không bao gồm URL có password.
- Correlation ID/trace ID đã được cấp phát theo policy.
- Số lần xảy ra/latency/endpoint ở mức aggregate, hạn chế cardinality.

Ví dụ:

```java
String state = ex.getSQLState();

logger.warn("jdbc.failure operation={} sqlState={} vendorCode={}",
        operationName, state, ex.getErrorCode());
```

Đây là **snippet**, `logger` của logging framework ứng dụng, `SQLException ex` và `String operationName` phải có sẵn. API placeholder `{}` là phong cách của nhiều logger như SLF4J; **JDK không cung cấp sẵn một logger tên `logger`** trong snippet này. Không biên dịch độc lập nếu chưa cấu hình thư viện logger.

Không log vô điều kiện:
- Raw username/password/token.
- SQL có giá trị nhạy cảm được nối trực tiếp.
- JDBC URL chứa credentials hoặc network secrets.
- Entire exception chain/message/cause từ driver nếu chưa scrub.
- User-provided form input hoặc PII.

**SQLState `28` không nên được trả chi tiết cho người dùng cuối.** Nếu service account của backend hết hiệu lực, đó là lỗi nội bộ cần alert đội vận hành; không nên để public API nói tài khoản DB cụ thể đã bị khóa hoặc gợi ý chính sách xác thực.

### 11.1. SQLState và metrics

Để tránh metrics cardinality bùng nổ:
- Gắn label bằng **class prefix `28`/`42`** hoặc nhãn phân loại đã chuẩn hóa.
- Không gắn dynamic SQL string, query parameters hoặc entire exception message làm label.
- Theo dõi xu hướng sau mỗi deployment/migration/credential rotation.
- Tách lỗi **connection establishment** khỏi lỗi **statement execution** nếu application có dữ liệu phase đó.

Đừng tự gắn label `retryable=true` chỉ vì SQLState không rõ. Unknown state cần quyết định theo policy riêng.

## 12. Connection pooling và xoay thông tin xác thực

Trong ứng dụng thực tế, `DataSource` hoặc pool thường tạo và tái sử dụng connections. Một lỗi `SQLInvalidAuthorizationSpecException` có thể ảnh hưởng:
- **Pool startup**: tạo connection ban đầu thất bại vì secret sai.
- **Pool refill**: những connection cũ vẫn còn chạy, nhưng pool không tạo connection mới vì credential đã đổi.
- **Credential rotation**: token mới được cập nhật nhưng pool vẫn cache secret hoặc physical connections cũ; cần cơ chế reload/recreate theo vendor/pool.
- **Multi-tenant setup**: định danh/principal bị chọn sai do map tenant → connection config.
- **Failover**: endpoint mới có quy tắc authentication khác hoặc user chưa được provision đúng.

Quy trình vận hành nên gồm:
1. Dùng secret manager và datasource config theo môi trường.
2. Xác minh quyền database của service principal theo least privilege.
3. Theo dõi login failures có rate limiting và cảnh báo đúng mức.
4. Sau rotation, cập nhật pool/connection factories theo hướng dẫn của thư viện.
5. Kiểm tra credential mới bằng connection test có kiểm soát, không retry không giới hạn.
6. Xóa/rotate secrets cũ theo chính sách, không giữ password trong logs hay ticket screenshots.
7. Không tự mở lại connection vào endpoint không tin cậy chỉ để “vượt” lỗi authentication.

**Đừng dùng `Connection.setClientInfo("ClientUser", "...")` để đổi principal**. Client info chỉ là metadata chẩn đoán, không thực hiện authentication/authorization cho JDBC connection.

### 12.1. Quyền SELECT và login có thể thất bại khác nhau

Một account có thể connect thành công nhưng không có `SELECT` trên bảng `app_users`. Khi đó, lỗi có thể là `42501`/class `42` hoặc mã vendor khác, **không nhất thiết `SQLInvalidAuthorizationSpecException`**. Phải tách kiểm tra identity của connection với grants trên object.

Khi schema migrations thay đổi owner/grants, có thể vừa có syntax/undefined-table errors vừa có access errors trong nhóm `42`. Thực hành tốt là migration tests chạy với chính **role của service**, không chỉ với admin role trên developer machine.

## 13. Sai lầm phổ biến và cách khắc phục

| Hiểu sai | Hậu quả | Điều đúng |
| --- | --- | --- |
| “Tên class SQLSyntaxErrorException nghĩa là chỉ có typo.” | Bỏ sót SQL access rule violation. | SQLState class `42` có thể gồm access rule; xem mã chi tiết/vendor. |
| “Bất kỳ permission error nào cũng là SQLInvalidAuthorizationSpecException.” | Sai hướng sửa credential. | Class `28` chủ yếu liên quan credentials lúc connection; query privilege có thể class `42`. |
| “Cứ ném SQLSyntaxErrorException thì SQLState luôn 42.” | Bỏ qua vendor-specific conditions/null state. | Ghi nhận subtype và SQLState riêng. |
| “Driver phải ném đúng hai JDBC subclasses.” | Bỏ sót generic SQLException. | Catch SQLException chung và xem SQLState/vendor code. |
| “Non-transient nghĩa là sự cố không bao giờ sửa được.” | Ngại sửa và phục hồi. | Phải sửa nguyên nhân rồi mới thử lại. |
| “Non-transient có thể retry 10.000 lần chờ tự hết.” | Tăng tải, lockout và log spam. | Không retry không giới hạn; có cơ chế recovery rõ ràng. |
| “42501 là lỗi cú pháp cần sửa SQL text.” | Có thể cấp nhầm hướng fix. | Kiểm tra thiếu quyền SQL theo vendor. |
| “28P01 được mọi DBMS dùng cho password sai.” | Chẩn đoán sai vendor khác. | Mã ví dụ PostgreSQL, kiểm tra driver docs. |
| “getErrorCode() giống getSQLState().” | Sai kiểu và ý nghĩa. | SQLState chuỗi, vendor code số. |
| “getSQLState() không bao giờ null.” | NullPointerException trong error handler. | Kiểm tra null và độ dài trước khi phân loại prefix. |
| “getNextException giống getCause.” | Mất dữ liệu chain hoặc cause. | Duyệt đúng chuỗi SQL exceptions và Throwable causes riêng. |
| “Không có SQLNonTransientException subtype nghĩa là retry được.” | Retry sai với generic SQLException. | Runtime class không tự bảo đảm transient semantics. |
| “Đặt catch SQLException trước catch subclasses.” | Java báo unreachable catch. | Catch subclass trước superclass hoặc xử lý chung một lần. |
| “DataSource.getConnection thành công thì mọi query có quyền.” | Query fail vì grants/schema. | Test quyền trên chính tables/views với service principal. |
| “SQLSTATE 42 là SQL injection.” | Kết luận bảo mật vội. | Lỗi syntax/access rule không chứng minh attack; dùng bind parameters/validation. |
| “SQLSTATE 28 là người dùng cuối nhập sai password.” | Lộ nội bộ và trả response sai. | Phân biệt DB service principal với end-user auth. |
| “Log toàn bộ JDBC exception luôn an toàn.” | Rò connection info/PII/secrets. | Scrub logs và metric labels, dùng operation ID. |
| “Tạo lại pool một lần sẽ luôn sửa login failure.” | Vẫn thất bại nếu secret/role sai. | Sửa nguyên nhân, kiểm tra connection rồi quản lý pool. |

## 14. Phân biệt với những SQLException khác

Hai class trong bài là một phần của hierarchy rộng hơn. Khi thiết kế code bắt lỗi, cần tránh gom sai:

| Subclass/SQLState class thường gặp | Dấu hiệu | Vì sao không dùng hai class này? |
| --- | --- | --- |
| `SQLIntegrityConstraintViolationException` / `23` | Unique key, foreign key, check violation. | Dữ liệu vi phạm constraint; sửa data/transaction. |
| `SQLDataException` / `22` | Numeric overflow, invalid conversion, data exceptions. | Sai giá trị/kiểu dữ liệu, không thuần SQL syntax. |
| `SQLTransactionRollbackException` / `40` | Transaction rollback/deadlock/serialization. | Có thể cần retry toàn transaction sau điều kiện tạm. |
| `SQLTransientConnectionException` / `08` trong vài trường hợp | Connection tạm thời lỗi. | Liên quan availability/connectivity, không nhất thiết credentials. |
| `SQLNonTransientConnectionException` / `08` trong vài trường hợp | Connection không thể khôi phục tự nhiên. | Sai trạng thái connection/network, không đồng nghĩa SQLState 28. |
| `SQLTimeoutException` | Timeout ở query/login theo API. | Hết thời gian; cần kiểm soát timeout/cancellation. |
| `SQLFeatureNotSupportedException` / `0A` | Driver không hỗ trợ JDBC feature. | Cần đổi feature/mapping/driver, không phải syntax/login. |

Bảng chỉ giúp định hướng. SQLState class và JDBC subclass còn phụ thuộc vendor-specific behavior, ví dụ cùng `08` có thể được các subclass khác nhau phản ánh theo tình huống và driver.

Không suy từ hierarchy rằng mọi `SQLException` có thể được phân loại hoàn chỉnh bằng hai ký tự SQLState. Khi cần retry policy đáng tin, phải có **test integration** và chính sách cụ thể cho từng database.

## 15. Kiểm thử có hệ thống

### 15.1. Unit tests không cần DB

Dùng `JdbcExceptionClassifierDemo` ở mục 6 để xác minh:
- `instanceof` phát hiện đúng hai subclass.
- SQLState `"42601"` được phân loại `42`.
- `"28P01"` được phân loại `28`.
- Generic `SQLException("...", "42501")` vẫn được nhận `42` qua SQLState.
- SQLState null không gây exception trong handler.
- `getNextException` được duyệt và in mã chính xác.

Có thể thêm unit cases cho SQLState `""`, `"4"` hoặc vendor-specific nonstandard codes để đảm bảo fallback `OTHER` an toàn, không dùng `substring` mà không kiểm tra độ dài.

### 15.2. Integration tests với JDBC driver/DBMS thực

**Test 1 — SQL syntax:** chạy một câu SQL sai có chủ ý trên database test. Bắt `SQLException`, ghi runtime class, SQLState và vendor code. **Không khẳng định subclass trước khi test**.

**Test 2 — Missing table/column:** dùng schema test, gọi object không tồn tại. Kiểm tra SQLState có theo class `42` trên driver không và diagnostic message thực.

**Test 3 — Privilege:** tạo principal với quyền kết nối nhưng thiếu `SELECT` trên một table test; xác minh type/SQLState. Không làm thử nghiệm với production user/role.

**Test 4 — Invalid login:** dùng credential test cố ý sai và giới hạn số lần; tránh brute force/account lockout. Đọc exception từ `getConnection`; không log secret.

**Test 5 — Credential rotation:** sau khi cập nhật đúng secret, kiểm tra pool refresh và tạo physical connection mới theo hướng dẫn của driver/pool.

**Test 6 — SQLState missing/generic:** nếu driver ném generic SQLException, handler vẫn phân loại theo state mà không mất lỗi gốc; nếu state null, trả `OTHER`.

**Test 7 — Exception chain:** với driver có `getNextException`, xác minh logging/metrics không bỏ mất các lỗi phụ nhưng cũng không làm lộ dữ liệu.

**Test 8 — Transaction:** nếu lỗi xảy ra giữa transaction, rollback và kiểm tra connection state. Không tiếp tục commit khi statement đã thất bại mà chưa xử lý.

**Test 9 — Multi-vendor:** chạy trên DBMS/driver versions thực tế, so sánh subclass + SQLState + code; không clone logic PostgreSQL sang SQL Server/Oracle/MySQL mà không kiểm chứng.

**Test 10 — Security:** xác nhận logs không chứa password, raw SQL với PII hoặc JDBC URL bí mật; parameter binding chống injection.

**Test 11 — Observability:** dashboard đếm class `28` riêng class `42`, alert khi deployment làm class `42` tăng đột biến hoặc credential rotation làm class `28` tăng.

**Test 12 — Recovery:** thay đổi SQL/schema/grants/credential trong môi trường test rồi xác nhận operation **sau sửa nguyên nhân** mới thành công, không phải do retry y nguyên.

### 15.3. JDBC driver version và schema migration là phần của test

Một JDBC code snippet biên dịch trên JDK không chứng minh driver sẽ trả đúng exception subclass. Integration suite cần cố định/mô tả:
- Java runtime và JDBC driver version.
- DBMS version, SQL dialect, database/schema name.
- Connection principal và role grants trong môi trường test.
- Migration version và trạng thái schema.
- SQLState + vendor code dự kiến cho *từng* test/vendor.
- Expected application action (fail fast, alert, blocked retry, correction).

Khi nâng JDBC driver, database server hoặc đổi authentication plugin, chạy lại test. Java exception APIs ổn định, nhưng ánh xạ lỗi cụ thể từ server sang subclass thường là logic của vendor driver.

## 16. Thiết kế xử lý sự cố trong ứng dụng backend

### 16.1. Khi lỗi class 42 xuất hiện sau deploy

Ví dụ deployment vừa đổi tên `display_name` thành `name_display` nhưng một service còn dùng truy vấn cũ. Mọi request đọc user thất bại:

1. Alert dựa trên lỗi statement với class `42`/vendor code.
2. So sánh schema migration của database và SQL trong release.
3. Khoanh vùng service/revision gây lỗi; rollback deployment hoặc phát hành fix theo quy trình.
4. Không retry mỗi request hàng chục lần vì chỉ tăng tải.
5. Sau sửa, chạy smoke test với database role của service, không chỉ admin.
6. Không tiết lộ raw SQL/personal data ra public response.

### 16.2. Khi lỗi class 28 xuất hiện lúc startup

Ví dụ secret rotation hoàn tất nhưng deployment vẫn dùng password cũ:

1. Fail connection initialization có kiểm soát, tránh trả service “healthy” nếu chức năng cần DB.
2. Alert nhóm vận hành, kiểm tra secret version và pool configuration.
3. Chỉ cập nhật secret/roles thông qua kênh an toàn, không tự in password.
4. Refresh pool hoặc restart được quản lý nếu cần.
5. Test connection đã có principal đúng sau sửa, rồi phục hồi traffic.
6. Không áp dụng “retry vô hạn cho đến khi hết lỗi”, có thể gây account lockout.

### 16.3. Khi query permission bị từ chối

Đây có thể là SQLState class `42` nhưng không phải parser bug:
1. Xác định principal đang kết nối.
2. Kiểm tra quyền cụ thể trên table, view, sequence hoặc function mà statement cần.
3. Xem schema ownership/default privileges và quyền được tạo trong migration.
4. Đề xuất cấp **chỉ quyền cần thiết**, không mở rộng vai trò admin.
5. Test lại bằng service role trong integration environment.

**Ba kịch bản dùng ba hành động khác nhau** dù tất cả có thể bị bọc trong `SQLException`. Vì vậy, handler cần phân loại nhưng không thay con người hoặc quy trình vận hành quyết định cấp quyền/credential.

## 17. Câu hỏi ôn tập

**Câu 1.** `SQLSyntaxErrorException` và `SQLInvalidAuthorizationSpecException` có chung superclass nào?

**Đáp án:** Cả hai extends `SQLNonTransientException`, lớp này extends `SQLException`.

**Câu 2.** SQLState class nào gắn với SQLSyntaxErrorException?

**Đáp án:** Class `42`, theo API là syntax rules, trong quy ước SQL có thể bao gồm syntax error hoặc access rule violation. Các điều kiện vendor-specific cũng có thể tồn tại.

**Câu 3.** SQLState class nào gắn với SQLInvalidAuthorizationSpecException?

**Đáp án:** Class `28`, liên quan thông tin xác thực/ủy quyền không hợp lệ được cung cấp khi thiết lập kết nối, hoặc điều kiện do vendor định nghĩa.

**Câu 4.** `42501` luôn là lỗi SQL viết sai cú pháp không?

**Đáp án:** Không. Với PostgreSQL, mã đó thường là insufficient_privilege; cần kiểm tra grants, SQL access rule và vendor docs.

**Câu 5.** `28P01` có phải mã password sai universal không?

**Đáp án:** Không. Đó là mã thường gặp ở PostgreSQL; database khác có mã và exception mapping khác.

**Câu 6.** Vì sao `nonTransientType=false` ở generic `SQLException` với state `42501` trong demo?

**Đáp án:** Vì `instanceof SQLNonTransientException` kiểm tra runtime class, còn instance được tạo là `SQLException` chung. Không suy từ `false` rằng lỗi có thể retry an toàn.

**Câu 7.** `SQLException.getSQLState()` có thể null không?

**Đáp án:** Có. Constructor hoặc driver có thể không cung cấp SQLState. Kiểm tra null/length trước khi dùng `startsWith` hoặc `substring`.

**Câu 8.** `getNextException()` có giống `getCause()` không?

**Đáp án:** Không. `getNextException` là chuỗi SQLExceptions bổ sung; `getCause` là nguyên nhân Throwable của một exception.

**Câu 9.** Tại sao không retry cùng password hoặc cùng SQL sai nhiều lần?

**Đáp án:** Đây thường là lỗi non-transient cần sửa nguyên nhân; retry vô hạn không cải thiện, tăng tải và có thể khóa tài khoản database.

**Câu 10.** App dùng service account kết nối DB và gặp SQLInvalidAuthorizationSpecException có nên trả “người dùng cuối nhập sai mật khẩu” không?

**Đáp án:** Không. Đó là lỗi đăng nhập/authorization của backend database principal, không chứng minh end-user password sai.

**Câu 11.** Làm sao ngăn SQLSyntaxErrorException do SQL injection/quoting?

**Đáp án:** Dùng `PreparedStatement` bind dữ liệu, validate input, allowlist SQL identifiers động và không nối raw input vào SQL.

**Câu 12.** Vì sao bắt hai subclasses thôi chưa đủ?

**Đáp án:** Driver có thể ném `SQLException` chung với SQLState `28`/`42` hoặc class khác. Cần catch chung và kiểm tra SQLState/vendor code.

**Câu 13.** `SQLNonTransientException` có nghĩa sau khi sửa migration/credential không thể thử lại không?

**Đáp án:** Không. Sửa nguyên nhân rồi thử lại có kiểm soát là hợp lý; chỉ không kỳ vọng retry **không sửa nguyên nhân** tự giải quyết lỗi.

**Câu 14.** Catch `SQLException` trước `SQLSyntaxErrorException` có compile được không?

**Đáp án:** Không nếu là các catch tuần tự cho cùng try và catch subclass sau superclass; subclass catch sẽ không thể đạt, compiler báo lỗi.

## 18. Checklist production

1. Bắt đủ `SQLException`, có nhánh chuyên biệt hoặc classifier cho class `42`/`28`.
2. Kiểm tra `instanceof` nhưng cũng đọc `getSQLState()`, `getErrorCode()` và vendor docs.
3. Không giả định mọi driver ném đúng subclass; không gán subtype khi SQLState null.
4. Đừng nhầm **SQL access rule** với **DB login credential**.
5. Xử lý lỗi SQL syntax bằng sửa SQL/dialect/schema/migration và integration test.
6. Xử lý lỗi authentication bằng kiểm tra principal, secret rotation, endpoint và pool lifecycle.
7. Xử lý quyền SQL bằng least privilege, không cấp admin để bỏ qua lỗi.
8. Không retry vô hạn các lỗi non-transient; chỉ thử lại sau sửa nguyên nhân có kiểm soát.
9. Dùng `PreparedStatement` bind parameters, whitelist SQL identifiers nếu cần tạo SQL động.
10. Với connection/transaction lỗi, rollback/close/recreate theo tài liệu driver và pool.
11. Không log password, tokens, raw SQL chứa PII, JDBC URL với credentials hoặc exception message chưa scrub.
12. Quan sát SQLState/vendor code có giới hạn cardinality; tách lỗi connect khỏi lỗi execute.
13. Chạy unit tests với SQLState null/generic/subclass/exception chain.
14. Chạy integration tests trên driver + DBMS + service role thực tế, kiểm tra migration/grants.
15. Khi nâng Java/driver/server hoặc auth plugin, chạy lại contract tests, không dựa vào mappings cũ.
16. Giữ các API hiện hành của `java.sql` trên Java 17+; không cần thêm thư viện legacy cho hai classes này.

## 19. Tài liệu chính thức

- [Java SE 17 — SQLSyntaxErrorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLSyntaxErrorException.html): contract SQLState class 42 và vendor-specified conditions.
- [Java SE 25 — SQLSyntaxErrorException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLSyntaxErrorException.html): đối chiếu API vẫn được hỗ trợ trong JDK mới.
- [Java SE 17 — SQLInvalidAuthorizationSpecException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLInvalidAuthorizationSpecException.html): contract SQLState class 28 và authorization credentials khi kết nối.
- [Java SE 25 — SQLInvalidAuthorizationSpecException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLInvalidAuthorizationSpecException.html): API và constructor hiện hành.
- [Java SE 17 — SQLNonTransientException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLNonTransientException.html): ý nghĩa lỗi cần sửa nguyên nhân.
- [Java SE 25 — SQLException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, getNextException, iterator, cause.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): bind parameters và execute.
- [Java SE 17 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getSQLStateType()` và driver metadata.
- [Java SE 17 — DriverManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DriverManager.html): tạo JDBC connection.
- [Java SE 17 — SQLTransactionRollbackException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): phân biệt nhóm lỗi transaction rollback.
