# `SQLException`: cause, SQLState và chuỗi `nextException` trong Java JDBC

`java.sql.SQLException` là ngoại lệ **checked** mà JDBC dùng để báo nhiều loại thất bại trong thao tác với cơ sở dữ liệu: lỗi kết nối, thực thi SQL, ràng buộc dữ liệu, transaction hoặc sự cố do JDBC driver báo. Khác với một `Exception` thông thường chỉ có message/cause, `SQLException` còn có **SQLState**, **vendor error code** và một **chuỗi `SQLException` bổ sung** truy cập qua `getNextException()`.

Điểm mấu chốt của bài học:

> Một `SQLException` có thể đồng thời có **cause**, **nextException** và **suppressed exceptions**. Đây là **ba quan hệ khác nhau**. Đọc riêng `getCause()` thường chưa đủ để hiểu mọi lỗi JDBC mà driver hoặc thao tác dọn dẹp đã báo.

Ví dụ:

~~~java
SQLException error = new SQLException(
        "Không thể hoàn tất giao dịch",
        "40001",
        1205,
        new java.io.IOException("socket read failed"));

error.setNextException(
        new SQLException("duplicate key", "23505", 1062));
~~~

Đây là một mảnh Java minh họa trong phạm vi có import `java.sql.SQLException`. `error` có:

- `getMessage()`: thông điệp của lỗi chính, `"Không thể hoàn tất giao dịch"`.
- `getSQLState()`: chuỗi `"40001"`, mô tả nhóm/điều kiện theo hệ thống mã SQLState.
- `getErrorCode()`: số `1205`, là **mã được định nghĩa theo vendor**, không phải mã lỗi Java chung.
- `getCause()`: đối tượng `IOException` có message `"socket read failed"`.
- `getNextException()`: một **`SQLException` khác** mang SQLState `23505`, thông điệp và mã riêng.

Những mã trên là dữ liệu **giả lập cho mục đích học tập**; không thể từ một ví dụ tự tạo suy ra mọi JDBC driver đều trả cùng mã vendor hoặc cùng cấu trúc chuỗi.

## 1. Vị trí của `SQLException` trong phân cấp ngoại lệ

~~~text
java.lang.Object
└── java.lang.Throwable
    └── java.lang.Exception
        └── java.sql.SQLException
            ├── java.sql.SQLTransientException
            │   ├── java.sql.SQLTimeoutException
            │   ├── java.sql.SQLTransientConnectionException
            │   └── java.sql.SQLTransactionRollbackException
            ├── java.sql.SQLNonTransientException
            │   ├── java.sql.SQLIntegrityConstraintViolationException
            │   └── java.sql.SQLSyntaxErrorException
            ├── java.sql.SQLRecoverableException
            ├── java.sql.BatchUpdateException
            └── java.sql.SQLWarning
~~~

Đây là cây **rút gọn** các nhánh tiêu biểu, không phải danh sách đầy đủ.

`SQLException extends Exception` và không kế thừa `RuntimeException`, nên nó là **checked exception**. Nếu một phương thức gọi API JDBC có thể ném `SQLException`, code phải bắt hoặc khai báo đúng quy tắc checked exception:

~~~java
static int executeUpdate(java.sql.Statement statement, String sql)
        throws SQLException {
    return statement.executeUpdate(sql);
}
~~~

Đoạn trên là phương thức Java hợp lệ khi import `SQLException`. Việc khai báo `throws SQLException` chỉ mô tả khả năng lỗi, **không có nghĩa mọi lần gọi đều thất bại**.

`SQLException` còn triển khai `Iterable<Throwable>`, cho phép duyệt thông tin JDBC có liên quan bằng vòng `for-each`. Điểm này được trình bày riêng sau khi làm rõ hai kiểu liên kết cause và next.

### Các lớp con nói lên điều gì?

- `SQLTransientException`: nhóm lỗi mà tác vụ **có thể** thành công nếu thực hiện lại trong điều kiện phù hợp; không phải bảo đảm retry luôn an toàn.
- `SQLNonTransientException`: nhóm lỗi mà retry y hệt không được kỳ vọng thành công nếu không sửa nguyên nhân.
- `SQLRecoverableException`: nhóm lỗi có thể cần một thao tác khôi phục, ví dụ tái tạo kết nối, trước khi thử lại.
- `SQLIntegrityConstraintViolationException`: lỗi vi phạm ràng buộc toàn vẹn.
- `SQLSyntaxErrorException`: lỗi cú pháp SQL hoặc truy cập không hợp lệ được API/driver biểu diễn bằng subclass.
- `SQLTimeoutException`: một subtype của `SQLTransientException` báo timeout theo hợp đồng JDBC tương ứng.

Không phải driver nào cũng phân loại mọi sự cố giống nhau. **Đọc cả subtype, SQLState, vendor code và tài liệu driver** trước khi tự động quyết định khôi phục hoặc retry.

## 2. Bốn thông tin chẩn đoán chính trên một `SQLException`

Xét constructor:

~~~java
SQLException e = new SQLException(
        "update failed", "23505", 1062);
~~~

Các accessor:

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `e.getMessage()` | `String` | Thông điệp (*reason*) của ngoại lệ |
| `e.getSQLState()` | `String` | Mã SQLState nếu có |
| `e.getErrorCode()` | `int` | Mã lỗi riêng của database vendor |
| `e.getCause()` | `Throwable` | Nguyên nhân trực tiếp nếu có |
| `e.getNextException()` | `SQLException` | `SQLException` kế tiếp trong chuỗi nếu có |
| `e.getSuppressed()` | `Throwable[]` | Lỗi phụ được giữ, thường khi dọn dẹp tài nguyên |

**`getMessage()` không phải SQLState.** Một message như `"duplicate key"` là văn bản dành cho người đọc; `23505` là một mã có ý nghĩa theo quy ước SQLState của môi trường cụ thể. Vendor code `1062` lại thuộc hệ mã khác. Không trộn ba giá trị này thành một “mã lỗi chung”.

### Giá trị có thể thiếu

~~~java
SQLException e = new SQLException("unknown failure");

System.out.println(e.getSQLState()); // null
System.out.println(e.getErrorCode()); // 0
System.out.println(e.getNextException()); // null
~~~

Các giá trị mặc định ở ví dụ là thuộc tính của constructor được dùng, **không chứng minh** rằng mọi `SQLException` có vendor code `0` đều không có sự cố. Một driver có thể dùng `0` theo quy ước riêng; SQLState có thể là null khi không được cung cấp.

Đừng gọi `e.getSQLState().substring(0, 2)` trước khi kiểm tra null và độ dài.

## 3. `getCause()`: quan hệ nguyên nhân kiểu `Throwable`

`SQLException` kế thừa cơ chế cause từ `Throwable`:

~~~java
java.io.IOException root =
        new java.io.IOException("TCP connection reset");

SQLException sqlError = new SQLException(
        "database request failed",
        "08006",
        0,
        root);

System.out.println(sqlError.getCause() == root);
// true
~~~

Cause ở đây là **chính đối tượng `IOException`**, không phải chỉ bản sao chuỗi `getMessage()`. Cause có thể là bất kỳ subtype nào của `Throwable`, không nhất thiết là `SQLException`.

Mối quan hệ:

~~~text
SQLException: database request failed
    └── cause -> IOException: TCP connection reset
~~~

Nó giải thích “thất bại JDBC này bắt nguồn từ điều gì?”. Khi wrapper đi qua nhiều tầng:

~~~java
IllegalStateException serviceError =
        new IllegalStateException(
                "Không thể khởi động dịch vụ", sqlError);
~~~

chuỗi cause sẽ là:

~~~text
IllegalStateException
    └── cause -> SQLException
                   └── cause -> IOException
~~~

Constructor nhận `cause` là lựa chọn được ưu tiên khi lớp hỗ trợ. Chỉ sao chép `sqlError.getMessage()` vào message wrapper **không** bảo toàn tham chiếu và stack trace của nguyên nhân.

### `getCause()` chỉ truy cập một mắt xích

Nếu muốn biết lỗi gốc sâu nhất, phải lần lượt đọc cause. Tuy nhiên đừng mặc định một thuật toán duyệt các `Throwable` tùy biến sẽ không có vòng gián tiếp; tiện ích phân tích lỗi tổng quát nên có bảo vệ vòng lặp bằng **object identity**.

**Không đồng nhất “cause sâu nhất” với “lỗi duy nhất cần xử lý”.** Một `SQLException` ở giữa chuỗi còn giữ SQLState và vendor code, những dữ liệu mà `IOException` sâu nhất không có.

## 4. `getNextException()`: chuỗi riêng của JDBC

API:

~~~java
public SQLException getNextException()
public void setNextException(SQLException ex)
~~~

Đây là chữ ký minh họa. `getNextException()` trả `SQLException` kế tiếp đã được liên kết; nếu không có, trả `null`. `setNextException(ex)` **thêm ngoại lệ vào cuối chuỗi**.

Ví dụ:

~~~java
SQLException first =
        new SQLException("batch failed", "40001", 10);
SQLException second =
        new SQLException("row rejected", "23505", 11);
SQLException third =
        new SQLException("statement timeout", "HYT00", 12);

first.setNextException(second);
first.setNextException(third);
~~~

Sau đó:

~~~text
first
  └── nextException -> second
                          └── nextException -> third
                                                  └── null
~~~

Thao tác `first.setNextException(third)` **không thay thế** `second` đã gắn trước. Nó thêm `third` vào **cuối** chuỗi.

### Vì sao JDBC cần chuỗi này?

Một thao tác database có thể sinh nhiều thông tin lỗi, chẳng hạn:

- Lệnh đầu tiên thất bại và driver trả thêm chẩn đoán từ server.
- Một batch gồm nhiều statement gặp nhiều vấn đề cần được trình bày cùng một lỗi tổng.
- Driver và database cung cấp một tập hợp lỗi với SQLState/vendor code khác nhau.

Chuỗi `nextException` cho phép một lỗi JDBC tổng **chứa các `SQLException` khác**, mỗi lỗi có message, SQLState, vendor code và cause riêng. Nhưng **không phải mọi driver hay mọi thao tác đều tạo nhiều phần tử**. Chuỗi rỗng là tình huống bình thường.

### Đặc điểm khác cause

`getNextException()` yêu cầu một `SQLException` khác; `getCause()` có thể là `IOException`, `IllegalStateException` hoặc `Throwable` khác. Một đối tượng SQLException có thể có **cả hai** mà không có mối liên hệ bắt buộc giữa chúng.

## 5. Cause, nextException và suppressed khác nhau như thế nào?

Đây là ba cấu trúc không nên gộp.

~~~text
SQLException main: transaction failed
├── cause -> IOException: socket read failed
├── nextException -> SQLException: duplicate key
│                     └── nextException -> SQLException: timeout
└── suppressed[0] -> IOException: resource close failed
~~~

| Quan hệ | Kiểu dữ liệu | Hình thành khi nào? | Ý nghĩa chính |
| --- | --- | --- | --- |
| Cause | Một `Throwable` hoặc null | Constructor có cause, hoặc `initCause` hợp lệ | Nguyên nhân gốc/được bọc |
| Next exception | Một `SQLException` hoặc null mỗi mắt xích | Driver hoặc code gọi `setNextException` | Các chẩn đoán JDBC liên kết |
| Suppressed | Mảng `Throwable[]` | `addSuppressed`, hoặc cơ chế try-with-resources | Lỗi phụ không nên thay lỗi chính |

Giả sử bạn viết:

~~~java
SQLException primary =
        new SQLException("operation failed", "42000");
primary.setNextException(
        new SQLException("detail A", "23505"));
primary.addSuppressed(
        new java.io.IOException("close failed"));
~~~

Lúc này `primary.getCause()` vẫn có thể là `null` dù có next và suppressed. Việc thêm next **không** tự tạo cause; việc thêm suppressed **không** tự tạo next.

**Cần nhớ:** nếu chỉ log `e.getMessage()`, bạn có thể bỏ lỡ mọi thông tin còn lại; nếu chỉ đọc `e.getCause()`, vẫn có thể bỏ qua các lỗi JDBC nằm trong `getNextException()`.

## 6. SQLState là gì?

**SQLState** là một chuỗi mã dùng để phân loại điều kiện SQL theo những quy ước như X/Open và tiêu chuẩn SQL. Dạng chuẩn thường là **năm ký tự**: hai ký tự đầu mô tả **class** (nhóm điều kiện), ba ký tự sau mô tả **subclass** (điều kiện cụ thể).

~~~text
SQLState: 23505
          ^^---
          || └── subclass: 505
          └└── class: 23
~~~

Cách ghi hình trên chỉ là minh họa chia chuỗi; đọc chính xác nên lấy:

~~~java
String state = "23505";
String sqlClass = state.substring(0, 2);    // "23"
String subclass = state.substring(2);       // "505"
~~~

Một số nhóm thường gặp:

| Hai ký tự đầu | Nhóm điều kiện tham khảo |
| --- | --- |
| `00` | Successful completion |
| `01` | Warning |
| `02` | No data |
| `08` | Connection exception |
| `22` | Data exception |
| `23` | Integrity constraint violation |
| `28` | Invalid authorization specification |
| `40` | Transaction rollback |
| `42` | Syntax error or access rule violation |

Những nhóm này hữu ích để **định hướng**. Giá trị cụ thể và cách phân loại của driver phải được đối chiếu với tài liệu database và JDBC driver. Một số mã như `HYT00` mang tính quy ước driver/ODBC và không nên bị ép hiểu như mã tiêu chuẩn của mọi database.

### Ví dụ mã thường thấy

- `23505` được một số hệ quản trị dùng cho vi phạm ràng buộc unique.
- `40001` thường gắn với thất bại transaction do serialization hoặc dạng rollback tương ứng.
- `08001` thường mô tả client không thể thiết lập kết nối SQL theo quy ước liên quan.
- `42...` có thể gợi ý vấn đề cú pháp hoặc access rule.

**Không hard-code một cặp “SQLState → hành động” cho mọi vendor** nếu chưa kiểm tra driver. Chẳng hạn lỗi kết nối có thể xuất hiện **sau** khi server đã thực hiện thao tác ghi; retry mù quáng có thể tạo tác dụng phụ trùng lặp.

## 7. `getErrorCode()` là mã vendor, không phải SQLState

~~~java
SQLException error =
        new SQLException("unique violation", "23505", 1062);

System.out.println(error.getSQLState());   // 23505
System.out.println(error.getErrorCode());  // 1062
~~~

`getErrorCode()` trả `int` do vendor quyết định. Ý nghĩa của `1062` trong một hệ quản trị nhất định **không thể suy ra chỉ bằng Java API**. Không chuyển mọi vendor code thành một enum chung nếu ứng dụng hỗ trợ nhiều database mà chưa thiết kế mapping riêng.

Mã `0` thường xuất hiện khi không cung cấp vendor code:

~~~java
SQLException e = new SQLException("message", "08001");
System.out.println(e.getErrorCode()); // 0
~~~

`0` không phải một bằng chứng chắc chắn rằng sự cố không có mã lỗi nội bộ ở database; nó chỉ là số nguyên được API trả về trong tình huống cụ thể.

### Thông điệp và mã lỗi có mức ổn định khác nhau

- `getMessage()`: văn bản dành cho người đọc, có thể khác theo ngôn ngữ, phiên bản và cấu hình driver.
- `getSQLState()`: mã theo hệ SQLState, có thể giúp phân nhóm.
- `getErrorCode()`: mã vendor, chỉ diễn giải chính xác trong bối cảnh driver/database phù hợp.
- Subclass `SQLException`: một tín hiệu bổ sung về tính chất transient, integrity, timeout.

Khi xây monitoring hoặc retry policy, cần ghi **đúng các trường**, không trộn chúng thành một chuỗi rồi parse ngược.

## 8. Constructor của `SQLException` và dữ liệu được khởi tạo

Các overload quan trọng trong Java 17:

~~~java
new SQLException()
new SQLException(String reason)
new SQLException(String reason, String sqlState)
new SQLException(String reason, String sqlState, int vendorCode)
new SQLException(Throwable cause)
new SQLException(String reason, Throwable cause)
new SQLException(String reason, String sqlState, Throwable cause)
new SQLException(
        String reason,
        String sqlState,
        int vendorCode,
        Throwable cause)
~~~

Các dòng trên là **chữ ký minh họa**; không đặt nguyên văn tất cả vào một phương thức như biểu thức thực thi vì `reason`/`cause` chỉ là tên loại tham số trong cách ghi API.

**Constructor nhận cause** giữ tham chiếu nguyên nhân ngay lúc tạo. Với overload không nhận cause, trạng thái cause thường chưa được khởi tạo và `initCause(...)` có thể dùng một lần trong điều kiện hợp lệ. Tuy nhiên, nếu đã chọn một overload **có tham số cause**, trạng thái cause được khởi tạo ngay cả khi truyền `null`: không thể gọi `initCause` để thay thế.

Ví dụ:

~~~java
SQLException a = new SQLException("operation failed");
a.initCause(new java.io.IOException("network failed"));
// Thành công: constructor không khởi tạo cause.

SQLException b = new SQLException(
        "operation failed", "08001", 0, null);
b.initCause(new java.io.IOException("later"));
// Ném IllegalStateException: cause đã khởi tạo bằng null.
~~~

Đây là mảnh **phản ví dụ gây lỗi runtime ở cuối**; không chạy mà không bắt exception nếu muốn tiếp tục.

### Constructor nhận duy nhất cause

~~~java
SQLException e = new SQLException(
        new java.io.IOException("socket closed"));
~~~

Ở dạng cause-only, reason thường được tạo từ `cause.toString()`, tức có thể chứa cả tên lớp lẫn message của cause. Nếu đang chuyển đổi lỗi ở tầng JDBC, overload nhận **reason + SQLState + vendor code + cause** thường biểu đạt nhiều ngữ cảnh rõ hơn.

## 9. Duyệt tất cả `nextException` bằng vòng lặp

Cách duyệt dễ hiểu:

~~~java
SQLException current = primary;
while (current != null) {
    System.out.println(
            current.getMessage() + " / " + current.getSQLState());
    current = current.getNextException();
}
~~~

Đoạn minh họa giả định `primary` có sẵn. Nó đọc lần lượt **lỗi chính và tất cả next exceptions**. Mỗi mắt xích có thể mang SQLState/vendor code khác nhau.

Nếu viết công cụ logging tổng quát nhận dữ liệu từ nhiều nguồn, hãy phòng trường hợp cấu trúc next bị tạo sai hoặc tạo vòng gián tiếp. Một giải pháp đơn giản là dùng tập tham chiếu:

~~~java
java.util.Set<SQLException> seen =
        java.util.Collections.newSetFromMap(
                new java.util.IdentityHashMap<SQLException, Boolean>());

for (SQLException current = primary;
        current != null && seen.add(current);
        current = current.getNextException()) {
    System.out.println(current.getMessage());
}
~~~

Đây là mảnh minh họa với `primary` đã khai báo. `IdentityHashMap` phân biệt bằng **đồng nhất đối tượng**, không dùng `equals()`, thích hợp khi câu hỏi là “đã gặp chính object này chưa?”. Với chuỗi do JDBC driver tạo thông thường, bạn không cần cố dựng chuỗi vòng; việc phát hiện vòng là biện pháp bảo vệ cho tiện ích chẩn đoán.

### `setNextException` có nên được gọi trong code nghiệp vụ?

Thông thường, **driver hoặc thư viện JDBC** tạo chuỗi chẩn đoán. Mã ứng dụng có thể dùng `setNextException` khi tự tổ chức thông tin lỗi JDBC liên quan, nhưng không nên biến nó thành danh sách lỗi nghiệp vụ không liên quan hoặc dùng thay cho cause trong exception chaining thông thường.

Nếu bạn bọc `SQLException` ở tầng service:

~~~java
throw new IllegalStateException(
        "Không thể lưu đơn hàng", sqlException);
~~~

thì hãy **giữ cả đối tượng `sqlException` làm cause**. Nhờ đó `getNextException()` của chính object JDBC vẫn có thể được đọc sau khi truy cập cause.

## 10. `SQLException implements Iterable<Throwable>`

Một tiện ích ít được biết: có thể duyệt một `SQLException` bằng enhanced for:

~~~java
for (Throwable detail : sqlException) {
    System.out.println(
            detail.getClass().getSimpleName()
                    + ": " + detail.getMessage());
}
~~~

Đây là mảnh minh họa có biến `sqlException` kiểu `SQLException`.

Iterator của `SQLException` được thiết kế để duyệt các `SQLException` được nối và **các nguyên nhân tương ứng** nếu có, không chỉ mỗi exception đầu tiên. Vì kiểu phần tử là `Throwable`, một phần tử có thể **không phải `SQLException`** (ví dụ `IOException` làm cause). Muốn đọc `getSQLState()`:

~~~java
for (Throwable detail : sqlException) {
    if (detail instanceof SQLException sql) {
        System.out.println(sql.getSQLState());
    }
}
~~~

Đừng ép trực tiếp mọi phần tử iterator sang `SQLException` vì cause có thể không thuộc lớp đó.

### Iterator khác `getNextException()` ở phạm vi

- Vòng `current = current.getNextException()` cho bạn **chỉ các đối tượng `SQLException` trong next chain**.
- `for (Throwable detail : sqlException)` có thể gồm **cả các cause** liên quan, theo hợp đồng iterator.
- `getSuppressed()` vẫn là một quan hệ khác; không nên mặc định suppressed được bao gồm trong iterator.

Khi viết hệ thống ghi log với nhiều nhánh, hãy tránh **in lặp** cùng một lỗi nếu đã dùng iterator rồi lại tự duyệt cause riêng. Chọn một chiến lược rõ ràng để giữ đầy đủ thông tin mà không nhân bản mọi message.

## 11. Ví dụ Java 17+ đầy đủ, không cần database hoặc JDBC driver

Chương trình sau **tự tạo** đối tượng `SQLException`, `SQLTimeoutException` và `IOException`. Nó không kết nối database, nên đầu ra có thể kiểm chứng ổn định và không phụ thuộc SQL dialect.

Lưu tệp **`SQLExceptionDiagnosticsDemo.java`**:

~~~java
import java.io.IOException;
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransientException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public class SQLExceptionDiagnosticsDemo {

    public static void main(String[] args) {
        SQLException main = sampleFailure();

        System.out.println("== primary ==");
        System.out.println("type="
                + main.getClass().getSimpleName());
        System.out.println("message=" + main.getMessage());
        System.out.println("SQLState=" + main.getSQLState());
        System.out.println("vendorCode=" + main.getErrorCode());
        System.out.println("category=" + category(main));

        System.out.println("== next chain ==");
        Set<SQLException> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<SQLException, Boolean>());
        SQLException current = main;
        int index = 0;
        while (current != null && seen.add(current)) {
            System.out.println(
                    "item" + index + "="
                            + current.getClass().getSimpleName()
                            + "|" + current.getSQLState()
                            + "|" + current.getErrorCode()
                            + "|" + current.getMessage());
            index++;
            current = current.getNextException();
        }
        System.out.println("chainCount=" + index);

        System.out.println("== distinct relationships ==");
        Throwable root = main.getCause();
        System.out.println("cause="
                + root.getClass().getSimpleName()
                + ": " + root.getMessage());
        System.out.println(
                "suppressedCount=" + main.getSuppressed().length);
        System.out.println(
                "suppressed0="
                        + main.getSuppressed()[0]
                                .getClass().getSimpleName()
                        + ": " + main.getSuppressed()[0].getMessage());
        System.out.println(
                "nextIsCause=" + (main.getNextException() == root));

        System.out.println("== classifications ==");
        System.out.println("firstNextCategory="
                + category(main.getNextException()));
        System.out.println("noStateCategory="
                + category(new SQLException("unknown")));
        System.out.println(
                "timeoutIsTransient="
                        + (main.getNextException()
                                   .getNextException()
                                instanceof SQLTransientException));

        System.out.println("== wrapped exception ==");
        IllegalStateException wrapped =
                new IllegalStateException(
                        "cannot save order", main);
        System.out.println(
                "wrapperCauseSame=" + (wrapped.getCause() == main));
        SQLException recovered = (SQLException) wrapped.getCause();
        System.out.println(
                "recoveredNextMessage="
                        + recovered.getNextException().getMessage());

        System.out.println("== try-with-resources ==");
        resourceFailure();
    }

    static SQLException sampleFailure() {
        IOException network =
                new IOException("socket read failed");

        SQLException primary = new SQLException(
                "transaction failed", "40001", 1205, network);

        primary.setNextException(new SQLException(
                "duplicate key", "23505", 1062));

        primary.setNextException(new SQLTimeoutException(
                "statement timed out", "HYT00", 0));

        primary.addSuppressed(
                new IOException("resource close failed"));

        return primary;
    }

    static String category(SQLException failure) {
        String state = failure.getSQLState();
        if (state == null || state.length() < 2) {
            return "unknown";
        }
        return switch (state.substring(0, 2)) {
            case "08" -> "connection";
            case "23" -> "integrity";
            case "40" -> "transaction";
            default -> "other";
        };
    }

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws SQLException {
            throw new SQLException("close failed", "HY000", 99);
        }
    }

    static void resourceFailure() {
        try (FailingResource ignored = new FailingResource()) {
            throw new SQLException("execute failed", "42000", 7);
        } catch (SQLException failure) {
            System.out.println("primaryMessage="
                    + failure.getMessage());
            System.out.println("primaryState="
                    + failure.getSQLState());
            System.out.println("suppressedLength="
                    + failure.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + failure.getSuppressed()[0].getMessage());
            System.out.println("next="
                    + failure.getNextException());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SQLExceptionDiagnosticsDemo.java
java SQLExceptionDiagnosticsDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
== primary ==
type=SQLException
message=transaction failed
SQLState=40001
vendorCode=1205
category=transaction
== next chain ==
item0=SQLException|40001|1205|transaction failed
item1=SQLException|23505|1062|duplicate key
item2=SQLTimeoutException|HYT00|0|statement timed out
chainCount=3
== distinct relationships ==
cause=IOException: socket read failed
suppressedCount=1
suppressed0=IOException: resource close failed
nextIsCause=false
== classifications ==
firstNextCategory=integrity
noStateCategory=unknown
timeoutIsTransient=true
== wrapped exception ==
wrapperCauseSame=true
recoveredNextMessage=duplicate key
== try-with-resources ==
primaryMessage=execute failed
primaryState=42000
suppressedLength=1
suppressedMessage=close failed
next=null
~~~

### Phân tích kết quả phần primary

`sampleFailure()` tạo `SQLException` đầu tiên với đầy đủ reason, SQLState, vendor code và cause. Vì đối tượng là chính `SQLException`, `getClass().getSimpleName()` trả `"SQLException"`. Bộ phân loại `category` chỉ kiểm tra **hai ký tự đầu** của SQLState, nên `"40001"` trả `"transaction"`.

Hàm `category` trong ví dụ là **một tiện ích nhận diện nhóm**, không phải quy trình chuẩn để quyết định retry. Nó không kiểm tra vendor, trạng thái connection hoặc side effect của giao dịch.

### Phân tích chuỗi next

Hai lệnh `primary.setNextException(...)` tạo thứ tự:

1. Lỗi chính `transaction failed`, SQLState `40001`, vendor code `1205`.
2. Lỗi tiếp `duplicate key`, SQLState `23505`, vendor code `1062`.
3. Lỗi cuối `statement timed out`, SQLState `HYT00`, vendor code `0`.

Vòng duyệt bắt đầu từ chính `primary`, nên `chainCount=3`. Kiểm tra identity bằng `seen.add(current)` là lớp bảo vệ cho trường hợp một chuỗi bị xây dựng bất thường; ví dụ bình thường không có vòng.

### Phân tích cause và suppressed

`main.getCause()` trả `IOException("socket read failed")`. Mục `nextException` đầu tiên là một `SQLException` **khác**, nên `nextIsCause=false`. `main.getSuppressed()[0]` lại là một `IOException("resource close failed")` thứ ba, không trở thành cause hoặc next.

### Phân tích loại transient

`SQLTimeoutException` là subtype của `SQLTransientException` trong JDK 17, nên phép kiểm tra `instanceof SQLTransientException` trả `true`. Điều này **không tự động có nghĩa thao tác ghi có thể retry an toàn**: code còn phải xét idempotency, transaction state, timeout và hợp đồng của database.

### Phân tích wrapping

`IllegalStateException("cannot save order", main)` giữ chính `SQLException` làm cause, nên toàn bộ dữ liệu trên `main`, kể cả next chain, có thể truy xuất sau khi cast với kiểu đã xác nhận. Nếu chỉ tạo `IllegalStateException(main.getMessage())`, caller sẽ không còn liên kết đối tượng tới SQLState và chuỗi next qua `getCause()`.

### Phân tích try-with-resources

Thân `try` ném `SQLException("execute failed", "42000", 7)`. Khi rời scope, `FailingResource.close()` ném một `SQLException("close failed", "HY000", 99)` khác. Java giữ lỗi đóng làm **suppressed exception** trên lỗi chính.

Lưu ý: **lỗi đóng ở đây không được tự thêm vào `nextException`**. `getNextException()` của lỗi chính vẫn `null`. Đây là sự khác biệt quan trọng giữa cơ chế ngôn ngữ try-with-resources và chuỗi lỗi JDBC do driver/API chủ động thiết lập.

## 12. Ví dụ thực tế: log đầy đủ một ngoại lệ JDBC

Với JDBC thật, ta thường bắt `SQLException` ở ranh giới quản lý database:

~~~java
try {
    statement.executeUpdate(sql);
} catch (SQLException e) {
    logSQLException(e);
    throw e;
}
~~~

Đây là mảnh minh họa trong một phương thức khai báo/bắt checked `SQLException` phù hợp; `statement` và `sql` đã có sẵn. Không nên log ở mọi tầng nếu lỗi còn được truyền và log lại nhiều lần.

Một logger tối thiểu:

~~~java
static void logSQLException(SQLException first) {
    for (SQLException e = first;
            e != null;
            e = e.getNextException()) {
        System.err.println(
                "SQLState=" + e.getSQLState()
                + ", vendorCode=" + e.getErrorCode()
                + ", message=" + e.getMessage());
        if (e.getCause() != null) {
            System.err.println(
                    "cause=" + e.getCause().getClass().getName());
        }
    }
}
~~~

Đây là phương thức minh họa, có thể đặt trong một lớp với import `SQLException`. Logger production nên dùng thư viện logging đã thiết lập, cấu trúc dữ liệu phù hợp, chính sách redaction và giới hạn log thay vì phụ thuộc `System.err` trong mọi trường hợp.

**Bảo mật:** reason, cause hoặc SQL do driver báo có thể chứa tên bảng, khóa, giá trị input, chuỗi kết nối hoặc dữ liệu nhạy cảm. Đừng gửi nguyên toàn bộ thông điệp, SQL text hay stack trace ra response công khai. Có thể hiển thị mã lỗi ứng dụng an toàn và gắn correlation ID để tra cứu log nội bộ.

## 13. Khi bọc `SQLException` trong một exception của tầng service

Nếu module nghiệp vụ muốn che công nghệ JDBC khỏi API công khai, có thể định nghĩa custom exception:

~~~java
public final class RepositoryFailure extends Exception {
    public RepositoryFailure(
            String message, SQLException cause) {
        super(message, cause);
    }
}
~~~

Đây là class Java độc lập nếu lưu trong `RepositoryFailure.java`. Caller không cần phụ thuộc trực tiếp vào `SQLException` ở chữ ký phương thức; nhân viên vận hành vẫn có thể tìm SQLState, vendor code và next chain từ cause.

Một method ví dụ:

~~~java
static void saveOrder(java.sql.Connection connection)
        throws RepositoryFailure {
    try (java.sql.Statement statement =
                 connection.createStatement()) {
        statement.executeUpdate(
                "UPDATE orders SET processed = 1 WHERE id = 42");
    } catch (SQLException cause) {
        throw new RepositoryFailure(
                "Không thể cập nhật trạng thái đơn hàng", cause);
    }
}
~~~

Đây là phương thức Java hợp lệ khi đã định nghĩa/import `RepositoryFailure` và `SQLException` tương ứng. SQL trong ví dụ chỉ để thể hiện cấu trúc JDBC; không có bảo đảm bảng `orders` tồn tại trong một database thực tế.

**Tại sao giữ `cause` nguyên vẹn?** Khi một `SQLException` gốc có next chain, bạn không nên chỉ sao chép `cause.getMessage()` vào custom exception. Hãy giữ **chính đối tượng cause** để các lớp chẩn đoán có thể truy xuất `getSQLState()` và `getNextException()` khi cần.

### Có nên bọc luôn toàn bộ next chain thành các cause lồng nhau?

Thông thường **không cần**. `nextException` là quan hệ JDBC riêng; đừng tự làm phẳng thành chuỗi cause rồi đánh mất khác biệt. Một custom wrapper giữ `SQLException` gốc đã bảo toàn cả chuỗi.

## 14. `SQLWarning`: ngoại lệ JDBC liên quan nhưng ý nghĩa khác

`java.sql.SQLWarning extends SQLException`, nên nó cùng mang reason, SQLState, vendor code và chuỗi warning. Tuy nhiên, theo JDBC, warning thường được **gắn với `Connection`, `Statement` hoặc `ResultSet`** và có thể đọc qua `getWarnings()` thay vì luôn được ném ra như thất bại của một thao tác.

Ví dụ minh họa:

~~~java
SQLWarning warning = statement.getWarnings();
for (SQLWarning current = warning;
        current != null;
        current = current.getNextWarning()) {
    System.out.println(current.getMessage());
}
~~~

Đây là mảnh mã trong phạm vi có `statement` kiểu `Statement` và import `SQLWarning`. `getNextWarning()` là API chuyên cho chuỗi warning.

**Đừng suy ra mọi `SQLException` là một warning** hoặc cứ có SQLState class `01` thì JDBC nhất thiết ném lỗi. Mã warning và cơ chế báo warning của driver cần đọc theo API cụ thể.

## 15. `BatchUpdateException` và các thông tin bổ sung

Khi chạy batch JDBC, một thao tác có thể thất bại và API báo `BatchUpdateException`, là subclass của `SQLException`. Ngoài các trường chẩn đoán chung, nó có dữ liệu về những kết quả update của batch:

~~~java
catch (java.sql.BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();
    System.out.println(counts.length);
}
~~~

Đây là đoạn `catch` minh họa cần nằm trong một khối `try` có thể ném `BatchUpdateException`. Có API `getLargeUpdateCounts()` khi cần giá trị `long`.

Điểm quan trọng:

- `getUpdateCounts()` không thay `getNextException()`.
- Một `BatchUpdateException` có thể giữ các SQLException tiếp theo cung cấp thêm chẩn đoán theo driver.
- Nội dung mảng update counts phụ thuộc hành vi JDBC driver: driver có thể dừng sau lỗi hoặc tiếp tục xử lý một phần batch theo hợp đồng.
- **Không khôi phục transaction chỉ bằng cách nhìn một count**, vì có thể đã có một phần dữ liệu được ghi.

Nếu xử lý batch có nhiều side effect, phải xem xét transaction boundary, rollback, autocommit và chính sách idempotency của ứng dụng.

## 16. SQLException, transaction và quyết định retry

Một lỗi có SQLState class `40`, hoặc subtype `SQLTransientException`, có thể gợi ý điều kiện có khả năng phục hồi. Nhưng việc retry cần **nhiều điều kiện ngoài loại exception**.

Trước khi retry, xác minh:

1. **Thao tác có idempotent không?** Gửi lại câu lệnh có thể gây side effect trùng không?
2. **Trạng thái transaction là gì?** Đã rollback, đã commit, hay kết quả commit chưa biết?
3. **Connection có còn hợp lệ không?** Có cần lấy connection mới từ pool hoặc thiết lập lại session?
4. **Driver và database có khuyến nghị retry cho mã này không?** SQLState/vendor code chỉ là một phần tín hiệu.
5. **Có giới hạn retry/backoff không?** Tránh tạo vòng lặp lỗi gây tải lớn hơn.
6. **Có transaction spanning multiple calls không?** Retry từng statement có thể sai nếu toàn bộ transaction phải được chạy lại.
7. **Có idempotency key hoặc deduplication không?** Đặc biệt quan trọng với thao tác ghi có thể đã thành công trước khi timeout.
8. **Có yêu cầu phân biệt lỗi validation, authentication và constraint violation không?** Những lỗi này thường không được sửa bằng retry y hệt.

Phản ví dụ thiết kế:

~~~java
catch (SQLException e) {
    while (true) {
        executeAgain();
    }
}
~~~

Đây là mảnh pseudocode Java minh họa với `executeAgain()` giả định: retry vô hạn không phân loại lỗi có thể khiến hệ thống quá tải hoặc nhân đôi tác dụng phụ. Không dùng làm thực hành production.

**Nguyên tắc:** loại exception và SQLState hỗ trợ **phân loại**, còn quyết định retry là một phần của **hợp đồng giao dịch và tính đúng đắn nghiệp vụ**.

## 17. Dọn dẹp tài nguyên JDBC và suppressed exceptions

JDBC objects như `Connection`, `Statement` và `ResultSet` triển khai/đi theo `AutoCloseable` trong API hiện đại. Nên dùng try-with-resources khi sở hữu tài nguyên đó:

~~~java
try (java.sql.Connection connection = dataSource.getConnection();
     java.sql.PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT name FROM users WHERE id = ?")) {
    statement.setLong(1, userId);
    try (java.sql.ResultSet results = statement.executeQuery()) {
        if (results.next()) {
            System.out.println(results.getString(1));
        }
    }
} catch (SQLException e) {
    // Xử lý/log/lan truyền có chính sách.
}
~~~

Đây là **mảnh minh họa**: cần `dataSource`, `userId`, thư viện JDBC và một database thực. Không phải chương trình độc lập để chạy khi chưa cấu hình driver.

Khi thân `try` đã ném một `SQLException` và `close()` của một tài nguyên cũng ném lỗi, Java thường gắn lỗi đóng vào **`getSuppressed()` của ngoại lệ chính**. Mỗi suppressed throwable có thể bản thân là `SQLException` với SQLState/vendor code của nó.

Điều này **khác** với `setNextException`: JVM không tự thêm lỗi từ `close()` vào JDBC next chain.

### Một lỗi `close()` có thể là primary

Nếu thân `try` **hoàn tất bình thường** nhưng `close()` ném `SQLException`, ngoại lệ đóng có thể là **lỗi chính được ném ra**, không phải suppressed. Vì thế khi nhìn thấy `SQLException` có liên quan đóng kết nối, không được mặc định nó luôn chỉ là lỗi phụ.

Đọc cấu trúc thực tế: `getCause()`, `getSuppressed()` và `getNextException()`.

## 18. Lỗi thiết kế thường gặp với `SQLException`

### 18.1. Chỉ in `getMessage()` rồi bỏ qua SQLState

Message có thể không đủ để phân loại, đặc biệt khi driver có các mã khác nhau cho kết nối, constraint hay transaction.

### 18.2. Nhầm `getNextException()` với `getCause()`

Next chain là danh sách chẩn đoán JDBC nối các `SQLException`. Cause là liên kết nguyên nhân `Throwable` và có thể là `IOException` hoặc lỗi khác.

### 18.3. Tưởng `getSuppressed()` chính là next chain

Sai. Suppressed thường đến từ quá trình dọn dẹp; chúng không tự trở thành `nextException`.

### 18.4. Chỉ kiểm tra `getNextException()` đầu tiên

Một chain có thể có nhiều mắt xích. Dùng vòng lặp hoặc iterator theo hợp đồng khi cần thông tin đầy đủ.

### 18.5. Cho rằng mọi `SQLException` đều có SQLState

Không. `getSQLState()` có thể trả null; code phân loại phải xử lý null và chuỗi không chuẩn.

### 18.6. Cho rằng vendor code là mã SQLState

Sai. `getErrorCode()` là số nguyên theo vendor; `getSQLState()` là String theo quy ước SQLState.

### 18.7. Dùng nguyên văn reason làm mã máy

Không nên parse `"duplicate key"` hay các message được dịch/thay đổi theo version. Ưu tiên SQLState/subtype/vendor code có kiểm chứng khi cần phân nhánh.

### 18.8. Retry mọi `SQLTransientException`

Ngay cả khi lỗi transient, một thao tác ghi không idempotent có thể đã chạy ở server. Kiểm tra transaction, side effects và chính sách driver trước retry.

### 18.9. Retry mọi lỗi class `23`

Lỗi ràng buộc toàn vẹn không nhất thiết biến mất khi thử lại. Có thể cần sửa dữ liệu đầu vào hoặc xử lý conflict.

### 18.10. Chuyển checked `SQLException` thành unchecked mà bỏ cause

Nếu module cần bọc lỗi, truyền nguyên `SQLException` vào constructor wrapper để giữ cause và next chain.

### 18.11. Bắt `Exception` rồi mặc định mọi exception là lỗi database

Handler quá rộng có thể nuốt lỗi lập trình. `catch(SQLException)` khi xử lý JDBC thường thể hiện rõ trách nhiệm hơn.

### 18.12. Nhầm `SQLWarning` với lỗi làm thao tác thất bại

Warning có thể được báo qua `getWarnings()`. Không nhất thiết mọi warning đều ném khỏi lời gọi JDBC.

### 18.13. In toàn bộ SQL statement và tham số người dùng ra log

Log có thể làm lộ dữ liệu cá nhân, mã truy cập, token hoặc giá trị nhạy cảm. Cần redaction và quyền truy cập log phù hợp.

### 18.14. Bỏ qua `BatchUpdateException.getUpdateCounts()`

Đối với batch, thông tin thành công/thất bại từng phần có thể rất quan trọng để quyết định rollback, phục hồi hoặc ghi nhận kết quả.

### 18.15. Đoán tên database chỉ từ một vendor code

Một con số riêng lẻ không đủ khi hệ thống có nhiều driver. Phải biết database, driver version và mapping chính thức.

### 18.16. Tự tạo vòng next chain

`setNextException` được thiết kế để thêm vào cuối chuỗi. Không nên nối các object theo cách tạo vòng hoặc tái sử dụng chúng cho nhiều sự cố không liên quan, vì có thể khiến tiện ích duyệt lỗi gặp vấn đề.

## 19. Checklist chẩn đoán lỗi JDBC

Khi nhận `SQLException e`, hãy lần lượt:

1. **Ghi nhận loại exception**: `e.getClass().getName()`, các subtype hữu ích.
2. **Lấy reason/message** an toàn, không hiển thị thông tin nhạy cảm ra client.
3. **Đọc SQLState** và phân loại nhóm khi mã hợp lệ.
4. **Đọc vendor code** với thông tin database/driver tương ứng.
5. **Duyệt toàn bộ next chain** khi cần chẩn đoán nhiều lỗi.
6. **Duyệt cause** để tìm ngoại lệ thấp tầng như I/O/network.
7. **Kiểm tra suppressed exceptions**, nhất là lỗi đóng tài nguyên.
8. **Nếu là batch**, đọc counts và trạng thái giao dịch.
9. **Nếu có warning**, kiểm tra `getWarnings()` theo API phù hợp.
10. **Kiểm tra transaction state/connection state** trước khi quyết định retry.
11. **Dùng log có cấu trúc** và correlation ID; tránh ghi lại cùng lỗi ở mọi tầng.
12. **Không coi stack trace hay message là giao thức machine-readable ổn định**.
13. **Định nghĩa phản hồi người dùng tách biệt** với chi tiết SQL nội bộ.
14. **Đọc tài liệu JDBC driver và database** cho các mã cụ thể thay vì đoán.

Không nhất thiết mọi application flow đều tự thực hiện đủ mười bốn bước. Đây là danh sách dành cho tầng chẩn đoán/observability hoặc khi phân tích một sự cố khó.

## 20. Bài tập tự kiểm tra

1. `SQLException` là checked hay unchecked? Vì sao?
2. Nó nằm dưới `Exception` hay `RuntimeException`?
3. `getMessage()` và `getSQLState()` khác nhau thế nào?
4. `getErrorCode()` có phải SQLState dạng số không?
5. `getSQLState()` có thể là `null` không?
6. Hai ký tự đầu của SQLState thường biểu diễn gì?
7. SQLState class `08` gợi ý nhóm điều kiện nào?
8. SQLState class `23` gợi ý nhóm điều kiện nào?
9. `getCause()` trả một `SQLException` hay luôn có thể là loại `Throwable` khác?
10. `getNextException()` có thể trả loại `IOException` trực tiếp không?
11. Gọi `setNextException` hai lần trên exception đầu sẽ thay thế phần tử trước hay nối thêm?
12. Vì sao driver có thể tạo nhiều next exceptions?
13. `getSuppressed()` liên quan thế nào tới try-with-resources?
14. Lỗi từ `close()` có tự chuyển thành `nextException` không?
15. `SQLException implements Iterable<Throwable>` hữu ích thế nào?
16. Vì sao không được ép mọi phần tử của iterator thành `SQLException`?
17. Có thể giữ cả cause và next chain khi bọc lỗi trong `IllegalStateException` không?
18. Nếu wrapper chỉ chép message mà không truyền cause, điều gì bị mất?
19. `SQLTimeoutException` có thuộc `SQLTransientException` không?
20. Có thể retry thao tác ghi ngay khi gặp `SQLTransientException` không?
21. Vì sao `23505` không được giả định có ý nghĩa y hệt ở mọi driver?
22. `getErrorCode()==0` có chứng minh không có vendor error nào không?
23. `SQLWarning` thường có thể được lấy từ API nào?
24. `BatchUpdateException` cung cấp thêm thông tin nào?
25. Khi có lỗi ở lần close, vì sao cần phân biệt primary và suppressed?
26. Có nên trả stack trace SQL/JDBC nguyên vẹn cho HTTP client không?
27. Vì sao một lỗi class `40` cần kiểm tra transaction state trước retry?
28. Một tiện ích duyệt next chain tổng quát nên phòng tình huống bất thường nào?
29. Khi xử lý đa database, cần nguồn nào để hiểu vendor code?
30. Ba quan hệ chẩn đoán dễ nhầm của `SQLException` là gì?

### Đáp án gợi ý

1. Checked; kế thừa `Exception`, không thuộc `RuntimeException`.
2. `Exception`.
3. Message là văn bản; SQLState là mã điều kiện SQL.
4. Không; nó là mã integer riêng của vendor.
5. Có.
6. Class/nhóm điều kiện SQL.
7. Vấn đề kết nối.
8. Vi phạm ràng buộc toàn vẹn.
9. `Throwable` bất kỳ hoặc null.
10. Không; giá trị next thuộc kiểu `SQLException`.
11. Nối thêm vào cuối chuỗi.
12. Để lưu thêm các thông báo chẩn đoán JDBC có mã và message riêng.
13. Lỗi đóng tài nguyên có thể được gắn làm suppressed lên lỗi chính.
14. Không tự động.
15. Duyệt các SQLException liên kết và cause theo hợp đồng iterator.
16. Cause có thể là `IOException` hoặc loại `Throwable` khác.
17. Có, nếu truyền chính SQLException làm cause của wrapper.
18. Mất liên kết tới object gốc, SQLState/vendor code và next chain qua cause.
19. Có.
20. Không tự động; phải xét idempotency, transaction và hợp đồng driver.
21. Vendor và database có thể dùng/mở rộng quy ước mã khác nhau.
22. Không; phải xét quy ước driver cụ thể.
23. `Connection.getWarnings()`, `Statement.getWarnings()`, `ResultSet.getWarnings()`.
24. Counts của batch qua `getUpdateCounts()`/`getLargeUpdateCounts()`.
25. Lỗi thân try và lỗi close có vai trò khác nhau; close có thể được suppressed.
26. Không; có thể lộ thông tin kỹ thuật và dữ liệu nhạy cảm.
27. Vì thao tác ghi có thể đã có một phần tác dụng hoặc transaction cần rollback.
28. Vòng liên kết hoặc cấu trúc dữ liệu lỗi bất thường.
29. Tài liệu chính thức của database và JDBC driver theo phiên bản.
30. `cause`, `nextException` và `suppressed exceptions`.

## 21. Ghi nhớ và tham khảo API

**`SQLException` cung cấp nhiều lớp thông tin hơn một `Exception` thông thường.** Dùng `getMessage()` cho reason, `getSQLState()` cho mã điều kiện SQL, `getErrorCode()` cho mã vendor; dùng `getCause()` để truy tìm nguyên nhân, `getNextException()` để đọc chuỗi chẩn đoán JDBC, và `getSuppressed()` để phát hiện lỗi phụ khi dọn dẹp. Chúng không thay thế nhau. `SQLException` là checked exception; việc bọc nó sang lỗi tầng cao nên **giữ nguyên đối tượng cause**. Không quyết định retry hoặc lỗi nghiệp vụ chỉ dựa trên message hay một SQLState mà chưa xét driver, connection, transaction và idempotency.

Tài liệu chuẩn Java 17:

- `SQLException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html
- `SQLTransientException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTransientException.html
- `SQLTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTimeoutException.html
- `SQLWarning`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLWarning.html
- `BatchUpdateException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html
