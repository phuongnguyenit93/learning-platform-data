# Kiểm tra `isClosed` và `isValid` theo đúng mục đích trong JDBC

## 1. Vì sao cần phân biệt hai phép kiểm tra?

Trong chương **Quản lý kết nối**, một câu hỏi thường gặp là: trước khi chạy SQL, làm sao biết `Connection` vẫn sử dụng được? JDBC (**Java Database Connectivity**) là API để Java truy cập cơ sở dữ liệu quan hệ; giao diện `java.sql.Connection` có hai phương thức liên quan nhưng trả lời **hai câu hỏi khác nhau**:

- **`isClosed()`:** đối tượng `Connection` này có đang ở trạng thái *đã đóng* theo JDBC không?
- **`isValid(timeout)`:** theo phép kiểm tra của JDBC driver, kết nối này có còn **hợp lệ và sử dụng được** tại thời điểm kiểm tra không?

Một kết nối có thể **chưa bị đóng ở phía Java** nhưng không thể liên lạc với cơ sở dữ liệu vì mạng bị ngắt, máy chủ khởi động lại hoặc phiên kết nối hết hạn. Khi đó, `isClosed()` vẫn có thể trả `false`. Ngược lại, `isValid(2)` yêu cầu driver thực hiện phép xác minh thực tế, thay vì chỉ nhìn trạng thái đóng cục bộ.

| Tiêu chí | `Connection.isClosed()` | `Connection.isValid(int timeout)` |
| --- | --- | --- |
| Câu hỏi chính | Đối tượng JDBC đã đóng chưa? | Kết nối hiện còn dùng được không? |
| Giá trị trả về | `true` khi đã đóng; `false` khi chưa được xác định là đóng | `true` khi còn hợp lệ; `false` khi đóng hoặc không hợp lệ |
| Có bắt buộc xác minh với DBMS? | **Không**; không được thiết kế để kiểm tra kết nối mạng | **Có kiểm tra tính hợp lệ** bằng cơ chế do driver triển khai |
| Có tham số timeout? | Không | Có: `timeout` tính bằng **giây** |
| Khi thích hợp | Kiểm tra vòng đời, nhận diện handle đã đóng, hỗ trợ chẩn đoán | Health check, kiểm tra theo yêu cầu, chức năng xác minh kết nối của pool |
| Có đảm bảo câu SQL tiếp theo sẽ thành công? | Không | **Không**: kết nối có thể hỏng ngay sau khi kiểm tra |

**Quy tắc nền tảng:** `!connection.isClosed()` không đồng nghĩa với `connection.isValid(2)`. Và `connection.isValid(2) == true` cũng không đảm bảo rằng mọi thao tác SQL kế tiếp sẽ thành công.

## 2. Hiểu đúng `isClosed()`: trạng thái vòng đời của Connection

Chữ ký phương thức:

~~~java
boolean closed = connection.isClosed(); // throws SQLException
~~~

Khi gọi `Connection.close()`, ứng dụng thông báo đã sử dụng xong kết nối. Với kết nối trực tiếp, điều này thường giải phóng phiên hoặc tài nguyên kết nối bên dưới. Với kết nối do **connection pool** quản lý, `close()` thường chỉ đóng *handle logic* rồi trả kết nối vật lý về pool để tái sử dụng.

~~~java
Connection connection = dataSource.getConnection();
try {
    System.out.println(connection.isClosed()); // Thường là false.
    // Sử dụng connection.
} finally {
    connection.close();
}

System.out.println(connection.isClosed()); // true sau khi close thành công.
~~~

Ví dụ này giả định `close()` thành công. Không nên tiếp tục dùng đối tượng `Connection` đã đóng để chạy SQL, ngay cả khi cơ sở dữ liệu và kết nối vật lý trong pool vẫn hoạt động.

Theo hợp đồng JDBC, `isClosed()` báo `true` khi kết nối đã được đóng hoặc một số lỗi nghiêm trọng khiến kết nối được coi là đóng. Tuy nhiên, **nó không chủ động xác minh trạng thái mạng/DBMS**. Chẳng hạn:

~~~text
Thời điểm T1: Java lấy Connection -> isClosed() = false.
Thời điểm T2: DBMS khởi động lại hoặc đường truyền bị ngắt.
Thời điểm T3: Java chưa thực thi thêm SQL; driver chưa nhận ra sự cố.
             isClosed() vẫn có thể = false.
Thời điểm T4: Câu SQL tiếp theo phát sinh SQLException.
~~~

Đây là lý do không thể viết:

~~~java
// Cách kiểm tra không đủ để kết luận DBMS còn truy cập được.
if (!connection.isClosed()) {
    // Không có gì đảm bảo câu lệnh bên dưới sẽ thành công.
    // preparedStatement.executeQuery();
}
~~~

`isClosed()` có thể hữu ích sau một lỗi để biết handle có bị driver đóng hay không, nhưng không nên dùng nó làm bằng chứng rằng kết nối vẫn khỏe.

## 3. Hiểu đúng `isValid(timeout)`: kiểm tra khả năng sử dụng

JDBC 4.0 bổ sung:

~~~java
boolean valid = connection.isValid(2); // Tối đa 2 giây cho phép kiểm tra.
~~~

`isValid()` yêu cầu driver xác minh tích cực khả năng sử dụng kết nối bằng truy vấn kiểm tra hoặc cơ chế khác do driver/DBMS hỗ trợ. Theo hợp đồng API:

- Trả `true` nếu kết nối chưa đóng và còn hợp lệ.
- Trả `false` nếu kết nối đã đóng hoặc không còn hợp lệ.
- Có thể ném `SQLException`, chẳng hạn khi tham số `timeout` âm.
- Một số driver cũ hoặc triển khai không đầy đủ có thể không hỗ trợ tính năng và báo lỗi liên quan.

### Timeout là giây, không phải mili giây

| Cách gọi | Ý nghĩa |
| --- | --- |
| `connection.isValid(2)` | Yêu cầu driver giới hạn phép xác minh trong **2 giây**. |
| `connection.isValid(5)` | Giới hạn mong muốn là **5 giây**. |
| `connection.isValid(0)` | Không đặt giới hạn timeout cho phép xác minh bằng tham số này. |
| `connection.isValid(-1)` | Không hợp lệ; có thể dẫn đến `SQLException`. |

Với các driver chuẩn, timeout được hiểu theo đơn vị giây; mức độ thực thi chính xác khi mạng gặp sự cố vẫn phụ thuộc driver và cơ chế hủy thao tác. **`isValid(2)` không phải giới hạn thời gian cho cả quá trình `dataSource.getConnection()`, truy vấn ứng dụng hoặc toàn bộ HTTP request.**

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

public final class ConnectionChecks {
    private ConnectionChecks() {}

    public static boolean isUsableNow(Connection connection)
            throws SQLException {
        if (connection == null) {
            return false;
        }
        // isValid() tự kiểm tra trường hợp connection đã đóng;
        // không bắt buộc gọi isClosed() trước.
        return connection.isValid(2);
    }
}
~~~

`isValid()` cho phép biết trạng thái tại **một thời điểm**, không giữ kết nối luôn sống. Sau kết quả `true`, mất mạng vẫn có thể xảy ra trước câu `executeQuery()` tiếp theo. Vì vậy, cách duy nhất để biết một thao tác đã thành công là **thực thi thao tác đó và kiểm tra kết quả/xử lý lỗi**.

### Phép kiểm tra có thể có chi phí

Tùy driver, `isValid()` có thể gây thêm một lượt trao đổi qua mạng hoặc chạy một truy vấn kiểm tra. Nó không phải là một phép đọc cờ cục bộ miễn phí. Nếu driver xác minh bằng SQL, phép xác minh có thể diễn ra trong ngữ cảnh giao dịch hiện tại. Tránh chèn `isValid()` giữa nhiều câu lệnh trong giao dịch chỉ để “đảm bảo” trạng thái, vì vừa phát sinh chi phí vừa không loại bỏ rủi ro kết nối hỏng sau đó.

## 4. Chọn phương thức theo từng tình huống

| Tình huống | Cách phù hợp |
| --- | --- |
| Muốn biết handle đã bị `close()` chưa | `isClosed()`. |
| Cần kiểm tra DB có truy cập được từ ứng dụng không | Lấy kết nối và gọi `isValid(timeout)` hoặc dùng cơ chế health check của pool. |
| Vừa lấy kết nối từ pool khỏe mạnh để chạy truy vấn | **Dùng kết nối trực tiếp**; pool thường đã quản lý xác minh và tái sử dụng. |
| Vừa gặp `SQLException` khi thực thi SQL | Xử lý ngoại lệ, rollback khi cần, đóng/trả hoặc loại bỏ kết nối lỗi theo cơ chế pool; không mặc định `isClosed() == false` là có thể tiếp tục. |
| Muốn biết một giao dịch đã commit thành công | Xem kết quả `commit()` và cơ chế nghiệp vụ đối soát khi kết quả không xác định; hai phương thức trên không chứng minh commit. |
| Muốn biết một truy vấn đang chạy có quá thời gian không | Cấu hình timeout truy vấn/cơ chế cancellation phù hợp; `isValid(timeout)` không giám sát truy vấn đó. |

Một sơ đồ ra quyết định:

~~~mermaid
flowchart TD
    A["Cần kiểm tra điều gì?"] --> B{"Đối tượng JDBC đã close?"}
    B -->|Có| C["isClosed()"]
    B -->|Không| D{"Cần xác minh kết nối ở thời điểm hiện tại?"}
    D -->|Có| E["isValid(timeout) hoặc health check của pool"]
    D -->|Không, cần chạy SQL| F["Thực thi SQL và xử lý SQLException"]
    E --> F
    F --> G["Đóng/trả kết nối khi hoàn tất"]
~~~

## 5. Ví dụ: sử dụng kết nối bình thường không cần kiểm tra thừa

Trong ứng dụng Java dùng `DataSource`, luồng phổ biến là **lấy kết nối → chạy SQL → đọc kết quả → đóng kết nối**. `isClosed` hoặc `isValid` thường không cần được gọi trước mỗi câu SQL.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProductReader {
    private final DataSource dataSource;

    public ProductReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long id) throws SQLException {
        String sql = "SELECT name FROM product WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("name") : null;
            }
        }
    }
}
~~~

Trong ví dụ này, tài nguyên được giải phóng tự động theo thứ tự `ResultSet` → `PreparedStatement` → `Connection`. Nếu mất kết nối hoặc SQL thất bại, JDBC ném `SQLException`; tầng gọi quyết định cách xử lý và thông báo. Thêm `if (!connection.isClosed())` trước `prepareStatement` không làm luồng an toàn hơn. Thêm `isValid(2)` trước mọi truy vấn còn có thể tăng chi phí mạng mà không đảm bảo câu truy vấn kế tiếp thành công.

Khi dùng pool, phần mềm quản lý pool thường có cơ chế kiểm tra kết nối khi mượn/trả hoặc theo chính sách cấu hình. Ứng dụng nên dùng chính cơ chế đó và theo dõi timeout/lỗi, thay vì tự tạo nhiều phép kiểm tra song song.

## 6. Ví dụ: viết phép health check khi thực sự cần xác minh

Health check trả lời một câu hỏi hẹp: “Ứng dụng hiện có thể lấy một `Connection` và xác minh nó có khả năng giao tiếp với cơ sở dữ liệu hay không?” Đây là nhu cầu hợp lý của vận hành, nhưng **không nên chạy theo mỗi request nghiệp vụ**.

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DatabaseHealth {
    private final DataSource dataSource;

    public DatabaseHealth(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean isDatabaseReachable() {
        try (Connection connection = dataSource.getConnection()) {
            // Thực hiện xác minh có thời hạn và trả kết nối về pool.
            return connection.isValid(2);
        } catch (SQLException error) {
            // Ở ứng dụng thực, ghi log/metric nguyên nhân ở vị trí phù hợp.
            return false;
        }
    }
}
~~~

Đoạn mã có các đặc điểm:

1. **Lấy một kết nối thực sự** thay vì chỉ hỏi trạng thái của đối tượng đã `close()`.
2. Dùng `isValid(2)` để yêu cầu kiểm tra khả năng dùng kết nối.
3. Dùng `try-with-resources` để trả kết nối về pool ngay khi xong.
4. Chuyển `SQLException` thành `false` **chỉ tại ranh giới health check**, vì giao diện này có chủ đích trả trạng thái khỏe/không khỏe. Trong nghiệp vụ đọc/ghi dữ liệu, không được âm thầm đổi lỗi SQL thành một giá trị thành công giả.

Health check không chứng minh mọi kết nối trong pool đều tốt, cũng không chứng minh một giao dịch hay truy vấn sau đó chắc chắn thành công. Nếu pool đang chờ cấp kết nối, thời gian chờ ở `getConnection()` còn phụ thuộc cấu hình pool; thời hạn 2 giây ở `isValid(2)` không bao phủ toàn bộ thời gian chờ đó. Để dùng trong vận hành, cần điều chỉnh tần suất kiểm tra, timeout cấp kết nối và ngưỡng cảnh báo để tránh làm quá tải DBMS trong giai đoạn lỗi.

## 7. Minh họa sự cố: `isClosed() == false` nhưng SQL vẫn lỗi

Giả sử ứng dụng mượn một `Connection` và giữ nó trong thời gian dài:

~~~text
T0: connection = dataSource.getConnection()
    connection.isClosed() -> false

T1: Đường truyền mạng giữa ứng dụng và DB bị ngắt.
    Đối tượng connection trong Java chưa được close().

T2: connection.isClosed() -> có thể vẫn false
    vì driver chưa nhận diện kết nối đã mất.

T3: connection.isValid(2) -> thường false hoặc báo lỗi tương ứng
    khi driver phát hiện không thể xác minh kết nối.

T4: Thực thi SQL -> có thể ném SQLException.
~~~

Không nên coi đây là chuỗi kết quả cố định trên mọi driver. Một số driver phát hiện sự cố từ sớm và báo `isClosed() == true`; một số hệ thống có timeout mạng dài nên việc phát hiện không tức thời. Điều cần rút ra là **hai phương thức có hợp đồng khác nhau**, và kết quả của chúng chịu ảnh hưởng bởi thời điểm phát hiện lỗi.

### `isValid()` có thay thế việc xử lý `SQLException`?

Không. Xét đoạn mã:

~~~java
if (connection.isValid(2)) {
    // Giữa hai dòng vẫn có thể mất mạng, DB restart hoặc hết phiên.
    preparedStatement.executeUpdate();
}
~~~

Kể cả khi `isValid(2)` trả `true`, `executeUpdate()` vẫn có thể lỗi. Đó là khoảng hở **kiểm tra xong rồi mới sử dụng** (*time of check to time of use*). Không có kiểm tra trạng thái nào làm cho kết nối “miễn nhiễm” với sự cố sau thời điểm kiểm tra.

## 8. Khi đang ở trong một giao dịch thì sao?

Trong JDBC, các câu lệnh tạo từ cùng `Connection` có thể tham gia một giao dịch nếu `autoCommit=false`. Nếu `SQLException` xảy ra giữa giao dịch, đừng chỉ gọi `isClosed()` rồi tiếp tục công việc vì driver trả `false`. Giao dịch có thể đã ở trạng thái lỗi hoặc không còn hợp lệ, tùy DBMS.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // Thực hiện các UPDATE bằng statement tạo từ connection.
        // Có thể phát sinh SQLException.
        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
~~~

Đây là mã khái niệm minh họa luồng lỗi và rollback. Trong ứng dụng dùng pool, hãy quản lý cả việc khôi phục trạng thái kết nối sau khi giao dịch **đã kết thúc thành công** và xử lý kết nối lỗi theo chính sách pool. Đặc biệt, không tự ý bật lại `autoCommit=true` sau một lần rollback thất bại, bởi việc đổi chế độ có thể dẫn tới commit ngầm giao dịch còn mở trên một số kết nối.

**`isValid()` cũng không xác định trạng thái kết quả của `commit()` bị lỗi.** Chẳng hạn, mất liên lạc ngay khi `commit()` được gửi có thể khiến ứng dụng không biết DBMS đã commit hay chưa. Sau đó `isClosed()` hoặc `isValid()` không thể thay thế cơ chế đối soát kết quả, idempotency hoặc kiểm tra trạng thái nghiệp vụ trước khi thử lại.

## 9. Connection pool: trạng thái của handle và kết nối vật lý

Trong hệ thống có connection pool, cần phân biệt:

~~~mermaid
flowchart LR
    A["Mã Java"] -->|"dataSource.getConnection()"| B["Handle Connection logic"]
    B --> C["Connection vật lý được pool quản lý"]
    C --> D[("Cơ sở dữ liệu")]
    A -->|"handle.close()"| E["Trả handle về pool"]
    E --> C
~~~

Khi gọi `connection.close()` trên handle đã mượn, `connection.isClosed()` thường trả `true` đối với **handle đó**. Nhưng pool có thể giữ kết nối vật lý bên dưới để phục vụ một lượt mượn khác. Vì vậy:

- Không lưu lại handle đã `close()` để tái sử dụng.
- Không kết luận cơ sở dữ liệu “đang chết” chỉ vì một handle đã đóng.
- Không cố gọi `isValid()` trên handle đã đóng để kiểm tra mọi kết nối đang ở pool; nó không đại diện cho trạng thái toàn pool.
- Ưu tiên cấu hình validation, maximum lifetime, idle timeout và connection acquisition timeout bằng tùy chọn được hỗ trợ của pool.

Nếu ứng dụng dùng pool, `isValid()` có thể được pool gọi bên trong quá trình xác minh kết nối, nhưng chi tiết phụ thuộc thư viện. Mã nghiệp vụ không cần tự viết vòng lặp “ping” trước mọi truy vấn khi pool đã làm nhiệm vụ này.

## 10. Lỗi thường gặp và cách khắc phục

| Cách dùng hoặc giả định sai | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `if (!connection.isClosed())` trước mọi SQL | Không phát hiện chắc chắn mất mạng hoặc DB restart | Thực thi SQL, xử lý `SQLException`; dùng `isValid()` chỉ khi cần xác minh. |
| `isValid(0)` trong health check cần phản hồi nhanh | Giá trị `0` không đặt giới hạn timeout cho phép kiểm tra | Chọn timeout dương, cấu hình thêm timeout của pool/mạng nếu cần. |
| `isValid(2000)` vì tưởng đơn vị mili giây | Thực tế tham số tính bằng **giây** | Dùng `isValid(2)` nếu muốn yêu cầu 2 giây. |
| Dùng `isValid()` trên mọi request | Có thể gây thêm phép kiểm tra tốn thời gian | Dựa vào cơ chế validation của pool; gọi khi có lý do cụ thể. |
| `isClosed()==false` nên chắc chắn rollback được | Giao dịch có thể đã lỗi hoặc kết nối mạng bị mất | Thử rollback khi thích hợp, giữ cả lỗi rollback và xử lý kết nối không xác định. |
| Health check trả `true` nên giao dịch chắc chắn commit được | Tình trạng kết nối có thể thay đổi sau kiểm tra | Vẫn xử lý lỗi tại từng bước và kết quả commit. |
| Đóng connection rồi gọi `isValid()` để xác minh DB | Đang hỏi trạng thái của handle đã đóng | Mượn handle mới hoặc dùng health check của pool. |
| Kiểm tra kết nối trong vòng lặp retry vô hạn | Dễ làm nghẽn pool và tăng tải DBMS khi có sự cố | Đặt số lần thử, backoff, timeout và chính sách phục hồi phù hợp. |
| Gặp `SQLException` rồi bỏ qua vì `isClosed()==false` | Làm mất lỗi gốc và có thể tiếp tục trên giao dịch hỏng | Bảo toàn ngoại lệ, rollback/đóng kết nối thích hợp. |

Đối với driver cũ không hỗ trợ `isValid()`, hãy dùng chiến lược xác minh phù hợp theo tài liệu driver hoặc cơ chế health check/query kiểm tra của pool. Không tự giả định một câu `SELECT 1` hoạt động trên **mọi** DBMS; cả cú pháp và cách thiết lập timeout đều có thể khác nhau.

## 11. Bài thực hành và câu hỏi tự kiểm tra

### Bài 1 — Quan sát đóng kết nối

Lấy một kết nối từ `DataSource`, gọi `isClosed()`, sau đó gọi `close()` và kiểm tra `isClosed()` lần nữa. Nếu dùng pool, tiếp tục mượn kết nối mới và quan sát: việc đóng **handle cũ** không có nghĩa toàn bộ pool ngừng hoạt động.

### Bài 2 — Viết phép kiểm tra sức khỏe

Viết phương thức `boolean isDatabaseReachable()` với `try-with-resources`, `getConnection()`, `isValid(2)` và xử lý `SQLException`. Quan sát hành vi khi sai thông tin kết nối hoặc DBMS không truy cập được. Nhớ rằng timeout của `isValid` và thời gian chờ mượn kết nối có thể là hai giới hạn khác nhau.

### Bài 3 — Phân tích tình huống

**Tình huống A:** `isClosed()` trả `false`, rồi `executeQuery()` ném `SQLException` do mất mạng. Hai kết quả có mâu thuẫn không?

**Trả lời:** Không. `isClosed()` kiểm tra trạng thái đóng của đối tượng JDBC, không chứng minh kết nối vẫn có thể trao đổi dữ liệu với DBMS.

**Tình huống B:** `isValid(2)` trả `true`, vài mili giây sau `executeUpdate()` lỗi. Có thể bỏ xử lý lỗi SQL vì đã kiểm tra chưa?

**Trả lời:** Không. `isValid` chỉ xác minh tại thời điểm gọi; ứng dụng vẫn phải xử lý lỗi khi thực thi SQL.

**Tình huống C:** `connection.close()` được gọi trên handle từ pool. `connection.isClosed()` trả `true`, nhưng request tiếp theo mượn kết nối từ cùng pool thành công. Điều này có hợp lệ không?

**Trả lời:** Có. `close()` trên handle của pool thường trả kết nối vật lý về pool; trạng thái của handle cũ không phản ánh toàn bộ pool.

## 12. Ghi nhớ

Trong JDBC, **`isClosed()` trả lời câu hỏi vòng đời: handle đã đóng chưa; `isValid(timeout)` trả lời câu hỏi xác minh: kết nối còn hợp lệ ở thời điểm kiểm tra không**. Cả hai đều không thay thế việc thực thi SQL, quản lý giao dịch hoặc xử lý `SQLException`. Với luồng nghiệp vụ thông thường, hãy mượn kết nối từ `DataSource`, dùng nó trong phạm vi ngắn và giải phóng bằng `try-with-resources`; dành `isValid` cho health check và cơ chế validation thật sự cần thiết.
