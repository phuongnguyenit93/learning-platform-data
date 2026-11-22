# Lựa chọn kiểu Java nguyên thủy và kiểu bao khi làm việc với JDBC

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java đọc và ghi dữ liệu từ cơ sở dữ liệu quan hệ thông qua các kiểu dữ liệu của Java. Một lựa chọn tưởng như nhỏ — dùng **int** hay **Integer**, **long** hay **Long**, **boolean** hay **Boolean** — có thể quyết định việc chương trình biểu diễn đúng hay làm mất ý nghĩa của giá trị **SQL NULL**.

Đây là nội dung cốt lõi của chương **Kiểu dữ liệu và NULL**: phân biệt kiểu Java nguyên thủy (*primitive*) với kiểu bao (*wrapper*), xác định khi nào dữ liệu có thể vắng mặt và dùng các API JDBC để không nhầm **NULL** với **0** hoặc **false**.

Trong một câu:

> Dùng **kiểu nguyên thủy** khi giá trị chắc chắn tồn tại và không có trạng thái NULL trong mô hình Java; dùng **kiểu bao** khi cần biểu diễn thêm trạng thái không có giá trị, nhưng phải xử lý NULL một cách có chủ đích.

## 1. Kiểu nguyên thủy và kiểu bao khác nhau ở đâu?

Java có tám kiểu nguyên thủy và các lớp bao tương ứng:

| Kiểu nguyên thủy | Kiểu bao | Ví dụ giá trị | Có thể chứa Java null? |
| --- | --- | --- | --- |
| **byte** | **Byte** | 8 | Chỉ Byte |
| **short** | **Short** | 125 | Chỉ Short |
| **int** | **Integer** | 42 | Chỉ Integer |
| **long** | **Long** | 100000L | Chỉ Long |
| **float** | **Float** | 2.5f | Chỉ Float |
| **double** | **Double** | 3.14 | Chỉ Double |
| **boolean** | **Boolean** | true, false | Chỉ Boolean |
| **char** | **Character** | 'A' | Chỉ Character |

Ví dụ:

~~~java
int stock = 0;                // Luôn có một giá trị int.
Integer minimumStock = null;  // Có thể biểu diễn "chưa được cấu hình".

boolean enabled = false;      // Chỉ có true hoặc false.
Boolean approved = null;      // Có thể là true, false hoặc chưa biết.
~~~

**Kiểu nguyên thủy** lưu một giá trị thuộc miền xác định của kiểu đó; không thể gán null. **Kiểu bao** là kiểu tham chiếu, có thể trỏ tới một đối tượng chứa giá trị hoặc chứa null. Ví dụ, trạng thái của Boolean có thể biểu diễn ba trường hợp: **true**, **false** và **null**.

Trong Java, giá trị mặc định của **field** nguyên thủy chưa khởi tạo lần lượt là 0, false hoặc ký tự NUL tùy kiểu; field kiểu bao có mặc định là null. **Biến cục bộ** phải được gán trước khi đọc, không tự được khởi tạo theo các mặc định này.

Khi làm việc với JDBC, kiểu bao hữu ích vì **SQL NULL** là một trạng thái dữ liệu hợp lệ ở những cột cho phép NULL. Tuy nhiên, không phải cứ dùng kiểu bao thì JDBC tự trả về null; phương thức đọc dữ liệu cũng phải được chọn đúng.

## 2. SQL NULL không phải số 0, false hay chuỗi rỗng

Trong SQL, **NULL** biểu diễn giá trị không có hoặc không xác định theo mô hình dữ liệu. Điều này khác với các giá trị thực:

~~~sql
-- Ví dụ mô hình dữ liệu; cú pháp kiểu BOOLEAN tùy hệ quản trị.
CREATE TABLE notification_preferences (
    user_id       BIGINT PRIMARY KEY,
    retry_limit   INTEGER NULL,
    email_enabled BOOLEAN NULL,
    note          VARCHAR(200) NULL
);
~~~

Các bản ghi có thể mang những ý nghĩa khác nhau:

| retry_limit | email_enabled | Ý nghĩa minh họa |
| --- | --- | --- |
| **0** | **FALSE** | Không thử lại; tắt thông báo email. |
| **3** | **TRUE** | Thử lại tối đa 3 lần; bật email. |
| **NULL** | **NULL** | Chưa cấu hình số lần thử lại; chưa quyết định trạng thái email. |

Nếu ứng dụng đọc retry_limit = NULL thành int **0**, hoặc email_enabled = NULL thành boolean **false**, ứng dụng có thể nhầm **chưa cấu hình** với **đã chọn rõ giá trị 0/false**.

Ngược lại, nếu schema quy định một cột **NOT NULL**, mô hình Java có thể dùng nguyên thủy vì trạng thái NULL không hợp lệ theo hợp đồng dữ liệu. Khi đó phải bảo đảm dữ liệu được kiểm tra và schema thực sự thực thi ràng buộc.

**Lưu ý:** SQL NULL và Java null thuộc hai ngữ cảnh khác nhau. JDBC giúp chuyển đổi giữa chúng, nhưng kết quả phụ thuộc loại getter, kiểu Java được yêu cầu và khả năng của JDBC driver.

## 3. Bẫy thường gặp: getInt(), getLong() và getBoolean() khi cột là NULL

Các getter trả về kiểu nguyên thủy không thể trả về Java null. Vì vậy JDBC quy định:

| Getter của ResultSet | Khi giá trị SQL là NULL | Cách nhận biết |
| --- | --- | --- |
| **getInt(...)** | Trả **0** | Gọi **wasNull()** |
| **getLong(...)** | Trả **0L** | Gọi **wasNull()** |
| **getShort(...)** | Trả **0** | Gọi **wasNull()** |
| **getDouble(...)** | Trả **0.0** | Gọi **wasNull()** |
| **getFloat(...)** | Trả **0.0f** | Gọi **wasNull()** |
| **getBoolean(...)** | Trả **false** | Gọi **wasNull()** |
| **getString(...)** | Trả **null** | Kiểm tra **== null** |
| **getBigDecimal(...)** | Trả **null** | Kiểm tra **== null** |

Giả sử câu SQL trả về một dòng có **retry_limit = NULL**:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        int retryLimit = resultSet.getInt("retry_limit");
        System.out.println(retryLimit); // In ra 0 dù SQL là NULL.
    }
}
~~~

Chương trình không lỗi, nhưng thông tin **NULL** đã bị mất nếu chỉ xem retryLimit. Để phân biệt, dùng **ResultSet.wasNull()**:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        int rawLimit = resultSet.getInt("retry_limit");
        Integer retryLimit =
                resultSet.wasNull() ? null : Integer.valueOf(rawLimit);

        if (retryLimit == null) {
            System.out.println("Chưa cấu hình giới hạn thử lại.");
        } else {
            System.out.println("Giới hạn: " + retryLimit);
        }
    }
}
~~~

**wasNull() cho biết cột vừa đọc có phải SQL NULL hay không**, không phải toàn bộ ResultSet có dòng nào hoặc tất cả cột đều NULL. Do đó, phải gọi nó **ngay sau getter cần kiểm tra**:

~~~java
int rawLimit = resultSet.getInt("retry_limit");
boolean limitWasNull = resultSet.wasNull();  // Đúng: kiểm tra retry_limit.

boolean rawEnabled = resultSet.getBoolean("email_enabled");
boolean enabledWasNull = resultSet.wasNull(); // Kiểm tra email_enabled.
~~~

Không nên đọc thêm cột khác rồi mới gọi wasNull() để hỏi về cột đã đọc trước đó:

~~~java
int rawLimit = resultSet.getInt("retry_limit");
boolean rawEnabled = resultSet.getBoolean("email_enabled");

// SAI VỀ Ý ĐỊNH: kết quả dưới đây nói về email_enabled, không phải retry_limit.
boolean retryLimitWasNull = resultSet.wasNull();
~~~

Phương thức wasNull() chỉ có ý nghĩa sau một lần đọc cột hợp lệ; nó không thay thế **resultSet.next()**.

## 4. Khi nào có thể dùng getObject(..., Integer.class)?

JDBC cung cấp getter **getObject(column, Class<T>)** để yêu cầu chuyển cột sang một kiểu Java cụ thể. Với JDBC 4.1 và driver hỗ trợ ánh xạ tương ứng, có thể lấy **Integer**, **Long** hoặc **Boolean** mà vẫn giữ null:

~~~java
Integer retryLimit = resultSet.getObject("retry_limit", Integer.class);
Boolean emailEnabled = resultSet.getObject("email_enabled", Boolean.class);
~~~

Khi giá trị SQL là NULL, các đối tượng tham chiếu này có thể nhận **null**, nên không cần gọi wasNull() cho từng cột. Đây là cú pháp gọn khi ánh xạ kiểu được driver hỗ trợ đúng.

Tuy nhiên, khả năng chuyển đổi từ một kiểu cột SQL cụ thể sang một lớp Java cụ thể có thể khác nhau theo **driver và phiên bản**. Nếu driver không hỗ trợ một ánh xạ, phương thức có thể ném SQLException hoặc SQLFeatureNotSupportedException. Đừng giả định Boolean.class luôn tương thích với mọi cách DB biểu diễn cờ (BOOLEAN, BIT, TINYINT hoặc dạng khác).

Một cách tương thích rộng và biểu đạt rõ ý định là dùng **getter nguyên thủy + wasNull()**, đặc biệt khi làm việc với driver có hỗ trợ typed getObject không đồng đều.

**Không nên suy đoán kiểu từ getObject(column) rồi cast vô điều kiện:**

~~~java
// Rủi ro: đối tượng do driver trả về có thể không phải Integer.
Integer count = (Integer) resultSet.getObject("counter");
~~~

Kiểu Java được trả về bởi getObject() không chỉ dựa vào hình dạng giá trị; nó còn phụ thuộc **kiểu SQL** và ánh xạ của driver. Có thể dùng typed getObject có kiểm soát, hoặc getter cụ thể đã xác định.

## 5. Chọn kiểu cho mô hình dữ liệu Java

Xét các thuộc tính của một bản ghi:

| Trường | Ràng buộc/ý nghĩa | Kiểu Java gợi ý | Lý do |
| --- | --- | --- | --- |
| **id** | Khóa chính **BIGINT NOT NULL**, đã tồn tại trong DB | **long** | Luôn có giá trị khi đọc bản ghi đã lưu. |
| **quantity** | **INTEGER NOT NULL**, số lượng có thể bằng 0 | **int** | 0 là giá trị thật, không có trạng thái vắng mặt. |
| **retry_limit** | **INTEGER NULL**, chưa thiết lập có ý nghĩa riêng | **Integer** | Phân biệt null với 0. |
| **email_enabled** | **BOOLEAN NULL**, trạng thái chưa quyết định | **Boolean** | Phân biệt null với false. |
| **total_amount** | **DECIMAL NOT NULL** | **BigDecimal** | Tiền tệ/thập phân cần giữ độ chính xác, BigDecimal là kiểu tham chiếu. |
| **note** | **VARCHAR NULL** | **String** | String là tham chiếu nên có thể null. |
| **created_on** | **DATE NOT NULL** | **LocalDate** | Kiểu ngày hiện đại là tham chiếu, cần kiểm tra hợp đồng NOT NULL. |

Kiểu **BigDecimal**, **String** và **LocalDate** không phải wrapper của primitive tương ứng. Chúng vốn là **kiểu tham chiếu**; dùng chúng không có nghĩa mọi cột phải cho phép SQL NULL. Hãy dựa trên ngữ nghĩa và ràng buộc dữ liệu.

Đừng dùng **int** cho một cột SQL INTEGER NULL chỉ vì “mặc định bằng 0 cũng được”, nếu 0 có ý nghĩa nghiệp vụ khác. Tương tự, đừng dùng **Boolean** chỉ để “linh hoạt” khi nghiệp vụ thật sự chỉ có hai trạng thái được bảo đảm bởi **NOT NULL**: chọn kiểu nên thể hiện hợp đồng dữ liệu.

### Lớp biểu diễn dữ liệu có NULL

Ví dụ lớp Java cho bảng notification_preferences:

~~~java
public final class NotificationPreference {
    private final long userId;
    private final Integer retryLimit;
    private final Boolean emailEnabled;
    private final String note;

    public NotificationPreference(
            long userId, Integer retryLimit,
            Boolean emailEnabled, String note) {
        this.userId = userId;
        this.retryLimit = retryLimit;
        this.emailEnabled = emailEnabled;
        this.note = note;
    }

    public long getUserId() {
        return userId;
    }

    public Integer getRetryLimit() {
        return retryLimit;
    }

    public Boolean getEmailEnabled() {
        return emailEnabled;
    }

    public String getNote() {
        return note;
    }
}
~~~

Lớp này phân biệt rõ một bản ghi **đã tồn tại** (userId có giá trị) và các thuộc tính **có thể chưa được đặt**. Một đối tượng NotificationPreference có retryLimit == null vẫn có thể biểu diễn một bản ghi hợp lệ.

## 6. Ví dụ đầy đủ: đọc bản ghi và giữ nguyên SQL NULL

Đoạn mã sau đọc một bản ghi theo user_id. Nó trả về **Optional.empty()** khi **không có dòng**, và trả về một **NotificationPreference** khi có dòng — kể cả khi một số cột trong dòng là SQL NULL.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class NotificationPreferenceRepository {

    public Optional<NotificationPreference> findByUserId(
            Connection connection, long userId) throws SQLException {
        String sql = "SELECT user_id, retry_limit, email_enabled, note " +
                     "FROM notification_preferences WHERE user_id = ?";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, userId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // Không có bản ghi.
                }

                long id = rs.getLong("user_id"); // Cột NOT NULL.

                int rawRetry = rs.getInt("retry_limit");
                Integer retryLimit = rs.wasNull() ? null : rawRetry;

                boolean rawEmail = rs.getBoolean("email_enabled");
                Boolean emailEnabled = rs.wasNull() ? null : rawEmail;

                String note = rs.getString("note"); // SQL NULL -> Java null.

                NotificationPreference preference =
                        new NotificationPreference(
                                id, retryLimit, emailEnabled, note);
                return Optional.of(preference);
            }
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
NotificationPreferenceRepository repository =
        new NotificationPreferenceRepository();

try (Connection connection = dataSource.getConnection()) {
    java.util.Optional<NotificationPreference> found =
            repository.findByUserId(connection, 1001L);

    if (!found.isPresent()) {
        System.out.println("Người dùng chưa có bản ghi cài đặt.");
    } else {
        NotificationPreference preference = found.get();
        Integer retryLimit = preference.getRetryLimit();
        if (retryLimit == null) {
            System.out.println("Giới hạn thử lại chưa được thiết lập.");
        } else {
            System.out.println("Giới hạn thử lại: " + retryLimit);
        }
    }
}
~~~

Đoạn mã sử dụng **dataSource** do ứng dụng cung cấp, các lớp NotificationPreference và NotificationPreferenceRepository như đã định nghĩa ở trên. Phương thức findByUserId() chỉ **mượn Connection** rồi đóng PreparedStatement và ResultSet do nó tạo; bên gọi chịu trách nhiệm đóng Connection mình lấy từ DataSource.

Điều cần ghi nhớ:

1. **Optional.empty()** mô tả **không tồn tại dòng dữ liệu**.
2. **Optional.of(preference)** mô tả **có dòng dữ liệu**.
3. **preference.getRetryLimit() == null** mô tả **dòng tồn tại, nhưng cột retry_limit có SQL NULL**.

Nếu chỉ trả Optional<Integer> của retry_limit bằng **Optional.ofNullable(value)**, cả “không có dòng” lẫn “có dòng nhưng cột NULL” đều biến thành Optional.empty(). Với nghiệp vụ cần phân biệt hai trạng thái, nên trả một đối tượng đại diện cho bản ghi, như ví dụ.

## 7. Ghi giá trị nullable bằng PreparedStatement

Việc dùng **Integer** hoặc **Boolean** trong Java không tự khiến lệnh SQL hiểu được null. Khi bind tham số, phải xác định kiểu SQL của tham số NULL.

Ví dụ phương thức cập nhật cài đặt, cho phép đưa các cột trở về NULL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;

public int updatePreference(
        Connection connection,
        long userId,
        Integer retryLimit,
        Boolean emailEnabled) throws SQLException {

    if (retryLimit != null && retryLimit < 0) {
        throw new IllegalArgumentException("retryLimit không được âm");
    }

    String sql = "UPDATE notification_preferences " +
                 "SET retry_limit = ?, email_enabled = ? WHERE user_id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        if (retryLimit == null) {
            statement.setNull(1, Types.INTEGER);
        } else {
            statement.setInt(1, retryLimit);
        }

        if (emailEnabled == null) {
            statement.setNull(2, Types.BOOLEAN);
        } else {
            statement.setBoolean(2, emailEnabled);
        }

        statement.setLong(3, userId);
        return statement.executeUpdate();
    }
}
~~~

Trong ví dụ này:

- **setInt** và **setBoolean** nhận các giá trị nguyên thủy; Java tự *unbox* kiểu bao không null khi gọi.
- **setNull(index, sqlType)** thể hiện rõ SQL NULL và kiểu JDBC tương ứng.
- **Types.INTEGER** và **Types.BOOLEAN** là các hằng **java.sql.Types**. Với DB lưu boolean theo BIT, TINYINT hoặc kiểu khác, hãy dùng kiểu SQL và cách bind phù hợp với schema/driver.
- **setObject(index, value, sqlType)** cũng là cách bind có chỉ rõ kiểu, bao gồm trường hợp null, khi được driver hỗ trợ.
- Dùng **setString(1, null)** hoặc **setObject(1, null)** không kèm kiểu có thể tạo phụ thuộc vào cách driver suy luận loại SQL; nên chỉ rõ kiểu cho NULL, nhất là trong truy vấn có kiểu dữ liệu nhạy cảm.

**Lưu ý quan trọng về API cập nhật:** Ở đây null có nghĩa **ghi SQL NULL**. Trong một API cập nhật từng phần, đôi khi “không gửi trường” lại có nghĩa **giữ nguyên giá trị cũ**. Hai ý định này khác nhau; nếu cần phân biệt “không thay đổi”, “đặt NULL” và “đặt giá trị”, hãy thiết kế DTO/bộ đánh dấu sự hiện diện riêng, không dựa duy nhất vào một Integer nullable.

## 8. Tránh lỗi tự động đóng gói và mở gói (autoboxing/unboxing)

Java tự chuyển giữa nguyên thủy và kiểu bao trong nhiều biểu thức:

~~~java
int x = 5;
Integer boxed = x; // Autoboxing: int -> Integer.
int y = boxed;     // Unboxing: Integer -> int.
~~~

Nhưng nếu kiểu bao là **null**, thao tác unboxing sẽ ném **NullPointerException**:

~~~java
Integer retryLimit = null;

// NGUY HIỂM: so sánh với 0 cần unbox retryLimit.
if (retryLimit > 0) {
    System.out.println("Có thử lại.");
}

// NGUY HIỂM: phép gán cần unbox null.
int value = retryLimit;
~~~

Một cách xử lý là quyết định rõ ý nghĩa nghiệp vụ:

~~~java
if (retryLimit == null) {
    System.out.println("Chưa cấu hình.");
} else if (retryLimit > 0) {
    System.out.println("Được phép thử lại.");
} else {
    System.out.println("Đã cấu hình không thử lại.");
}
~~~

Nếu nghiệp vụ **thực sự quy định** rằng thiếu cấu hình được hiểu là 0, có thể chuyển đổi một cách tường minh:

~~~java
int effectiveRetryLimit = (retryLimit == null) ? 0 : retryLimit;
~~~

Việc thay null bằng 0 là **quyết định nghiệp vụ**, không nên xảy ra âm thầm vì vô tình chọn getInt() thay vì getter nullable.

### Với Boolean, cần phân biệt ba trạng thái

~~~java
Boolean emailEnabled = null;

// SAI: emailEnabled có thể null -> NullPointerException.
// if (emailEnabled) { ... }

if (emailEnabled == null) {
    System.out.println("Chưa quyết định bật/tắt email.");
} else if (emailEnabled) {
    System.out.println("Bật email.");
} else {
    System.out.println("Tắt email.");
}
~~~

Biểu thức **Boolean.TRUE.equals(emailEnabled)** an toàn với null và phù hợp nếu chỉ muốn hỏi “có đúng là true không?”. Nhưng nó trả false với **cả false và null**; không sử dụng cách đó khi nghiệp vụ cần giữ riêng trạng thái “chưa quyết định”.

Những phép toán tự unbox có thể xuất hiện ở **toán tử số học, so sánh, toán tử ba ngôi, tham số phương thức** và khi gán kiểu bao cho nguyên thủy. Cần kiểm tra null trước những vị trí đó.

## 9. Ràng buộc NOT NULL, giá trị mặc định và dữ liệu chưa lưu

Một cách lựa chọn kiểu hợp lý là đi từ hợp đồng dữ liệu:

~~~mermaid
flowchart TD
    A[Thuộc tính cần ánh xạ từ SQL] --> B{SQL NULL có ý nghĩa hợp lệ?}
    B -- Có --> C[Dùng kiểu có thể null]
    C --> D[Đọc getter giữ được NULL]
    B -- Không --> E{Có giá trị hợp lệ tại thời điểm tạo object?}
    E -- Có --> F[Cân nhắc primitive phù hợp]
    E -- Không --> G[Dùng trạng thái chưa khởi tạo riêng hoặc wrapper có hợp đồng]
    D --> H[Kiểm tra null trước khi dùng]
    F --> I[Giữ ràng buộc NOT NULL tại DB và ứng dụng]
    G --> H
~~~

Ví dụ, cột **id BIGINT NOT NULL** trong bản ghi đã được lưu có thể ánh xạ sang **long**. Nhưng trước khi insert, một đối tượng chưa được cấp ID có thể cần **Long id = null** để biểu diễn “chưa được gán khóa”. Đây là hai **giai đoạn vòng đời** khác nhau:

- **DTO/đối tượng chuẩn bị tạo:** ID chưa có, có thể biểu diễn bằng Long nullable hoặc thiết kế đối tượng tạo không chứa ID.
- **Đối tượng đã đọc từ DB:** ID bắt buộc có, có thể dùng long với hợp đồng rõ ràng.

Vì vậy, **SQL NOT NULL không tự động buộc mọi lớp Java đều dùng primitive**. Có thể cần kiểu bao ở một tầng của ứng dụng dù bản ghi đã lưu không cho phép NULL. Điều quan trọng là đặt và kiểm tra ranh giới hợp đồng.

Ngược lại, **giá trị mặc định của SQL** cũng không nhất thiết có nghĩa Java có thể tùy ý thay NULL bằng 0. Ví dụ **DEFAULT 0** áp dụng khi cách INSERT khiến DB sử dụng default; việc gửi **NULL tường minh** vào cột nullable có thể lưu NULL, còn gửi NULL vào cột NOT NULL có thể gây lỗi, tùy định nghĩa và DB. Không nên mặc định **DEFAULT** sẽ thay thế mọi NULL được gửi vào.

## 10. Những trường hợp đặc biệt cần cân nhắc

### 10.1. Hàm tổng hợp SUM và COUNT

Với truy vấn không có GROUP BY:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
WHERE customer_id = ?
~~~

Ngay cả khi không có đơn hàng thỏa điều kiện, **COUNT(*)** thường trả một dòng chứa **0**, còn **SUM(total_amount)** trả **SQL NULL** vì không có giá trị đầu vào khác NULL để cộng.

~~~java
if (resultSet.next()) {
    long orderCount = resultSet.getLong("order_count");
    java.math.BigDecimal total =
            resultSet.getBigDecimal("total_amount"); // Có thể null.
}
~~~

Với số tiền, dùng **BigDecimal** để giữ độ chính xác thập phân; không đổi sang double chỉ để tránh null. Nếu nghiệp vụ muốn tổng 0 thay vì NULL, có thể quyết định điều đó ở SQL:

~~~sql
SELECT COALESCE(SUM(total_amount), 0) AS total_amount
FROM orders
WHERE customer_id = ?
~~~

**COALESCE** là lựa chọn có chủ đích: nó biến trường hợp không có tổng thành giá trị 0, phù hợp với một số nghiệp vụ nhưng đồng thời làm mất sự phân biệt giữa 0 và NULL.

### 10.2. Các phép so sánh với SQL NULL

Chọn Integer thay int **không làm thay đổi quy tắc NULL của SQL**:

~~~sql
-- Khi bind NULL vào dấu ?, phép so sánh không trở thành true.
SELECT user_id FROM notification_preferences WHERE retry_limit = ?;

-- Muốn tìm các dòng có retry_limit là SQL NULL:
SELECT user_id FROM notification_preferences WHERE retry_limit IS NULL;
~~~

Trong SQL, biểu thức **retry_limit = NULL** không có kết quả TRUE ngay cả khi cột cũng NULL. Khi bộ lọc đầu vào null có nghĩa tìm các giá trị NULL, phải tạo điều kiện **IS NULL**; khi đầu vào không null, dùng **= ?** và bind giá trị.

### 10.3. Collection và generic

Java generic không nhận trực tiếp kiểu nguyên thủy:

~~~java
java.util.List<Integer> ids = new java.util.ArrayList<>();
ids.add(101); // Tự đóng gói int -> Integer.

// Không hợp lệ trong Java: List<int>.
~~~

Kiểu bao là cần thiết khi dùng collection generic tiêu chuẩn; điều đó không có nghĩa mỗi phần tử nên cho phép null. Nếu danh sách ID không được chứa null, hãy xác thực đầu vào trước khi gọi JDBC **setLong()** hoặc **setInt()** để tránh NullPointerException.

### 10.4. Kích thước và độ chính xác

Lựa chọn kiểu phải xét cả **miền giá trị**. Cột SQL BIGINT thường phù hợp với long/Long; INTEGER thường phù hợp với int/Integer khi driver và schema tương thích. **double/Double** không bảo đảm biểu diễn chính xác mọi giá trị thập phân; dữ liệu tiền tệ kiểu DECIMAL/NUMERIC nên ưu tiên **BigDecimal**.

Đừng giải quyết NULL bằng cách chọn kiểu quá lớn hoặc quá nhỏ. **Nullability**, **phạm vi số** và **độ chính xác** là ba tiêu chí độc lập.

## 11. Hiệu năng có nên quyết định primitive hay wrapper?

Primitive có thể tránh cấp phát đối tượng và thao tác boxing trong một số tình huống, nhưng **truy vấn cơ sở dữ liệu thường còn chịu chi phí mạng, driver và thực thi SQL**. Không nên đánh đổi tính đúng đắn của dữ liệu chỉ để thay Integer bằng int khi cột có SQL NULL.

Hãy ưu tiên theo thứ tự:

1. **Đúng ý nghĩa dữ liệu:** Có cần phân biệt NULL với 0/false không?
2. **Đúng hợp đồng của DB và mô hình Java:** Cột nullable, NOT NULL, giá trị chưa được khởi tạo.
3. **Đúng cách đọc/ghi JDBC:** Getter, wasNull(), getObject(), setNull() và kiểu SQL.
4. **Đo hiệu năng khi cần:** Với khối lượng rất lớn, benchmark đường đi thực tế trước khi tối ưu việc boxing.

Khi field chắc chắn luôn có giá trị và mô hình yêu cầu nó, primitive có thể là lựa chọn **đơn giản, rõ ràng**. Khi null là trạng thái nghiệp vụ hợp lệ, wrapper hoặc một cấu trúc trạng thái riêng là công cụ mô tả đúng hơn.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đọc cột INTEGER NULL bằng getInt() rồi coi 0 là dữ liệu thật | Mất phân biệt NULL và 0 | Gọi wasNull() ngay sau getInt(), hoặc typed getObject nếu hỗ trợ. |
| Đọc BOOLEAN NULL bằng getBoolean() rồi coi false là dữ liệu thật | Mất trạng thái “chưa quyết định” | Dùng wasNull() và Boolean nullable. |
| Dùng getObject(column) rồi ép kiểu sang Integer không kiểm tra | Có thể ClassCastException | Dùng getter rõ kiểu hoặc typed getObject tương thích driver. |
| So sánh Integer nullable với 0 mà không kiểm tra | NullPointerException khi unboxing | Kiểm tra null hoặc áp dụng default rõ ràng. |
| Dùng if (nullableBoolean) | NullPointerException với null | Kiểm tra null hoặc dùng Boolean.TRUE.equals theo đúng nghiệp vụ. |
| Bind null vào setInt()/setBoolean() qua wrapper | NullPointerException trước hoặc khi gọi JDBC | Dùng setNull(index, SQL type). |
| Dùng Optional<Integer> để trả kết quả truy vấn một cột nullable | Không phân biệt “không có dòng” và “dòng có NULL” | Trả Optional của đối tượng biểu diễn bản ghi. |
| Giả định NOT NULL là đủ để field Java luôn được khởi tạo | Có thể sai với object chưa lưu hoặc mapping lỗi | Xác định vòng đời object và kiểm tra hợp đồng. |
| Dùng double để tránh BigDecimal nullable | Mất chính xác số thập phân | Giữ BigDecimal và xử lý NULL. |
| Truy vấn WHERE column = ? với tham số NULL để tìm cột NULL | Không khớp theo ngữ nghĩa SQL | Dùng IS NULL khi cần tìm NULL. |
| Mặc định null luôn có nghĩa “không cập nhật trường” | Có thể vô tình ghi SQL NULL | Thiết kế riêng trạng thái vắng mặt và ý định gán NULL trong API update. |

## 13. Câu hỏi tự kiểm tra

1. Nếu SQL cột **retry_limit** có giá trị NULL, **resultSet.getInt("retry_limit")** trả về gì? Làm thế nào biết đó không phải số 0 thật?
2. Vì sao **Boolean** diễn đạt được ba trạng thái mà **boolean** không diễn đạt được?
3. Sau khi gọi **getInt("a")** rồi **getBoolean("b")**, lệnh **wasNull()** phản ánh cột nào?
4. Khi nào nên dùng **getObject("retry_limit", Integer.class)** và cần lưu ý điều gì về driver?
5. Muốn ghi SQL NULL vào cột INTEGER qua PreparedStatement, dùng phương thức nào?
6. Một phương thức trả về Optional<Integer> có thể phân biệt “không có bản ghi” và “bản ghi có cột NULL” không?
7. Tại sao việc dùng Integer nullable trong biểu thức **retryLimit > 0** có thể gây lỗi?
8. Với bản ghi đã lưu có khóa BIGINT NOT NULL, vì sao **long** có thể phù hợp, trong khi đối tượng chưa được cấp khóa lại có thể cần **Long**?
9. Kết quả **SUM(amount)** khi không có dữ liệu khác NULL khác thế nào với **COUNT(*)**?
10. Trong API cập nhật một phần, vì sao cần phân biệt “không gửi trường”, “gửi NULL” và “gửi giá trị 0”?

**Ghi nhớ:** Trong JDBC, **kiểu nguyên thủy** phù hợp với dữ liệu luôn có giá trị, còn **kiểu bao** giúp mô tả trạng thái có thể NULL khi nghiệp vụ cần phân biệt. Getter nguyên thủy của ResultSet trả **0/false** cho SQL NULL, vì vậy phải dùng **wasNull()** hoặc getter đối tượng phù hợp; khi ghi NULL, hãy dùng **setNull()** với kiểu SQL thích hợp. Thiết kế đúng từ schema đến lớp Java giúp tránh mất dữ liệu ngữ nghĩa, NullPointerException và lỗi xử lý khi một cột chưa có giá trị.
