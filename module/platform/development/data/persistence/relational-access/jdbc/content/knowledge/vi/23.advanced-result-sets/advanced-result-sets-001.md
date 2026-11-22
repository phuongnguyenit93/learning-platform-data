# Phân biệt con trỏ chỉ tiến và con trỏ có thể cuộn trong JDBC

Trong JDBC (**Java Database Connectivity**, API Java để truy cập cơ sở dữ liệu quan hệ), một câu lệnh `SELECT` thường trả về `java.sql.ResultSet`. Đối tượng này cung cấp **con trỏ** (*cursor*) để xác định hàng hiện tại và các phương thức để đọc dữ liệu trên hàng đó.

Sự khác biệt quan trọng nhất giữa **con trỏ chỉ tiến** (*forward-only*) và **con trỏ có thể cuộn** (*scrollable*) là **khả năng di chuyển giữa các hàng**. Con trỏ chỉ tiến duyệt kết quả theo thứ tự từ đầu đến cuối; con trỏ có thể cuộn còn có thể quay lại hàng trước, nhảy đến một vị trí hoặc đi đến hàng cuối. Việc chọn loại con trỏ ảnh hưởng đến tính năng có thể sử dụng, mức hỗ trợ của driver và chi phí xử lý.

## 1. Con trỏ của ResultSet nằm ở đâu?

Khi vừa nhận một `ResultSet`, con trỏ **nằm trước hàng đầu tiên** (*before first*), chưa trỏ vào hàng dữ liệu hợp lệ. Sau mỗi lần `next()` thành công, con trỏ đi đến hàng tiếp theo và các phương thức như `getInt()`, `getString()` đọc giá trị ở hàng hiện tại.

```text
Ban đầu
  [trước hàng 1] -> [hàng 1] -> [hàng 2] -> [hàng 3] -> [sau hàng cuối]
                      ^ next()      ^ next()     ^ next()

Forward-only:
  chỉ duyệt tiến bằng next()  ------------------------------->

Scrollable:
  có thể next(), previous(), first(), last(), absolute(), relative()...
  <----------------------------------------------------------->
```

Ví dụ duyệt kết quả theo cách phổ biến nhất:

```java
try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(
             "SELECT id, name FROM customers ORDER BY id")) {

    while (rs.next()) {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        System.out.println(id + ": " + name);
    }
}
```

Với cả hai loại con trỏ, `next()` trả về `true` nếu chuyển đến một hàng hợp lệ và `false` khi không còn hàng kế tiếp. Sau khi `next()` trả về `false` ở cuối kết quả, không được tiếp tục đọc giá trị cột bằng `getString()` hoặc `getInt()` cho đến khi con trỏ được đặt lại vào hàng hợp lệ.

> Trong bài này, các ví dụ giả định có bảng `customers(id, name)`. Cấu trúc bảng, dữ liệu và driver JDBC cần được cấu hình sẵn theo hệ quản trị mà ứng dụng sử dụng.

## 2. Ba loại ResultSet được JDBC định nghĩa

JDBC dùng ba hằng số của `java.sql.ResultSet` để yêu cầu loại con trỏ:

| Loại | Khả năng di chuyển | Thay đổi dữ liệu do giao dịch khác thực hiện |
|---|---|---|
| `TYPE_FORWARD_ONLY` | Theo hướng tiến, thường dùng `next()` | Không được phân loại theo cơ chế nhạy/không nhạy với thay đổi; mức nhìn thấy dữ liệu phụ thuộc driver và DBMS |
| `TYPE_SCROLL_INSENSITIVE` | Tiến, lùi, đến đầu/cuối, đến vị trí chỉ định | Về nguyên tắc **không phản ánh** thay đổi của giao dịch khác sau khi tập kết quả được tạo |
| `TYPE_SCROLL_SENSITIVE` | Tiến, lùi, đến đầu/cuối, đến vị trí chỉ định | Có khả năng phản ánh một số thay đổi bên ngoài, nhưng **không bảo đảm mọi thay đổi đều hiển thị tức thì** |

Hai kiểu `TYPE_SCROLL_INSENSITIVE` và `TYPE_SCROLL_SENSITIVE` cùng thuộc nhóm **scrollable**. Sự khác biệt giữa chúng liên quan đến **mức độ nhạy với thay đổi của dữ liệu**, không phải số lượng thao tác điều hướng.

### 2.1. TYPE_FORWARD_ONLY: chỉ tiến

Đây là loại mặc định khi tạo `Statement` hoặc `PreparedStatement` bằng những overload thông dụng, không chỉ định `resultSetType`:

```java
Statement statement = connection.createStatement();

// Tương đương về yêu cầu mặc định:
// connection.createStatement(
//     ResultSet.TYPE_FORWARD_ONLY,
//     ResultSet.CONCUR_READ_ONLY
// );
```

Mô hình làm việc:

1. Gọi `next()` để đến hàng thứ nhất.
2. Đọc giá trị các cột tại hàng hiện tại.
3. Gọi `next()` lần nữa để chuyển sang hàng tiếp theo.
4. Dừng khi `next()` trả về `false`.

Không dùng `previous()`, `first()`, `last()` hoặc `absolute()` với `TYPE_FORWARD_ONLY`. Những phương thức điều hướng này không được đảm bảo hỗ trợ và thường ném `SQLException`.

Loại này thích hợp với xuất báo cáo tuần tự, đọc dữ liệu theo từng hàng, xử lý dữ liệu hàng loạt, hoặc luồng duyệt một chiều mà ứng dụng không cần quay lại hàng đã đọc.

### 2.2. TYPE_SCROLL_INSENSITIVE: cuộn, không nhạy với thay đổi bên ngoài

Đây là lựa chọn thích hợp nếu ứng dụng cần duyệt kết quả theo nhiều hướng nhưng muốn có góc nhìn kết quả tương đối ổn định trong suốt thời gian sử dụng `ResultSet`.

Ví dụ, sau khi đã ở hàng thứ ba, ứng dụng có thể gọi `previous()` để trở lại hàng thứ hai hoặc `absolute(1)` để trở về hàng đầu tiên. Các thay đổi mà giao dịch khác thực hiện sau khi tạo `ResultSet` thường không được phản ánh trong tập kết quả này theo ngữ nghĩa của loại con trỏ.

Tuy vậy, định nghĩa “không nhạy” không đồng nghĩa với bảo đảm một transaction snapshot theo mọi mức cô lập. Hành vi cụ thể của khóa, giao dịch và việc nhìn thấy cập nhật của chính ứng dụng vẫn phụ thuộc DBMS và cách driver triển khai.

### 2.3. TYPE_SCROLL_SENSITIVE: cuộn, có khả năng thấy thay đổi bên ngoài

Loại này hỗ trợ các thao tác điều hướng giống `TYPE_SCROLL_INSENSITIVE`, nhưng được thiết kế để có thể nhận biết thay đổi do giao dịch khác thực hiện khi `ResultSet` còn mở.

**Không nên mặc định rằng dữ liệu luôn tự cập nhật ngay lập tức.** Mức cô lập transaction, caching, loại thay đổi (thêm/sửa/xóa), con trỏ phía server và driver đều ảnh hưởng đến những gì được quan sát. Một số driver không hỗ trợ loại này; một số có thể thay loại con trỏ được yêu cầu. `refreshRow()` chỉ nên sử dụng sau khi kiểm tra khả năng hỗ trợ và đặc tính DBMS, thay vì xem là cách bảo đảm làm mới toàn bộ tập kết quả.

## 3. Tạo ResultSet theo loại con trỏ

Loại con trỏ được **yêu cầu khi tạo statement**, không phải bằng cách gọi setter trên `ResultSet` đã mở.

### 3.1. Dùng Statement

```java
try (Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
     ResultSet rs = statement.executeQuery(
        "SELECT id, name FROM customers ORDER BY id")) {

    // rs có thể hỗ trợ first(), last(), previous(), absolute()...
}
```

### 3.2. Dùng PreparedStatement

```java
String sql = "SELECT id, name FROM customers WHERE id >= ? ORDER BY id";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY)) {

    statement.setLong(1, 100L);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id") + " - " + rs.getString("name"));
        }
    }
}
```

Đối số thứ nhất là **loại con trỏ**; đối số thứ hai là **khả năng cập nhật** (*concurrency*) của tập kết quả:

- `CONCUR_READ_ONLY`: chỉ đọc dữ liệu qua `ResultSet`.
- `CONCUR_UPDATABLE`: yêu cầu tập kết quả có thể cập nhật qua các phương thức tương ứng, nếu câu truy vấn và driver hỗ trợ.

Đây là **hai thuộc tính độc lập**: scrollable không mặc nhiên có thể cập nhật, và forward-only không mặc nhiên là read-only trong mọi cấu hình được hỗ trợ.

## 4. Ví dụ hoàn chỉnh: so sánh hai kiểu duyệt

Ví dụ sau dùng cùng truy vấn và hai kiểu `PreparedStatement`. `Connection` do phương thức gọi sở hữu; các phương thức chỉ đóng `PreparedStatement` và `ResultSet` mà chúng tạo.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;

public final class CursorComparison {

    private static final String SQL =
            "SELECT id, name FROM customers ORDER BY id";

    // Duyệt một chiều: tương thích rộng và đơn giản.
    public static void forwardOnly(Connection connection) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                SQL,
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_READ_ONLY);
             ResultSet rs = statement.executeQuery()) {

            while (rs.next()) {
                System.out.printf("ID=%d, name=%s%n",
                        rs.getLong("id"), rs.getString("name"));
            }

            // Không gọi rs.previous() hoặc rs.first() tại đây.
        }
    }

    // Duyệt hai chiều: kiểm tra hỗ trợ trước khi sử dụng.
    public static void scrollable(Connection connection) throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();

        if (!metadata.supportsResultSetType(
                ResultSet.TYPE_SCROLL_INSENSITIVE)) {
            throw new SQLFeatureNotSupportedException(
                    "Driver/DBMS không hỗ trợ TYPE_SCROLL_INSENSITIVE");
        }

        try (PreparedStatement statement = connection.prepareStatement(
                SQL,
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.CONCUR_READ_ONLY);
             ResultSet rs = statement.executeQuery()) {

            // Xác minh kiểu thực tế vì driver có thể điều chỉnh yêu cầu.
            if (rs.getType() != ResultSet.TYPE_SCROLL_INSENSITIVE) {
                throw new SQLException("ResultSet thực tế không đúng loại yêu cầu");
            }

            // Đi đến hàng cuối và lấy số thứ tự hàng.
            if (rs.last()) {
                System.out.println("Số hàng trong ResultSet: " + rs.getRow());
            } else {
                System.out.println("Không có bản ghi");
            }

            // Trở về trước hàng đầu tiên để duyệt lại từ đầu.
            rs.beforeFirst();

            while (rs.next()) {
                System.out.printf("ID=%d, name=%s%n",
                        rs.getLong("id"), rs.getString("name"));
            }

            // Nhảy đến hàng thứ ba nếu tồn tại.
            if (rs.absolute(3)) {
                System.out.println("Hàng 3: " + rs.getString("name"));

                // Lùi về hàng thứ hai.
                if (rs.previous()) {
                    System.out.println("Hàng 2: " + rs.getString("name"));
                }
            }
        }
    }

    private CursorComparison() {
    }
}
```

Quan sát được hai điểm:

- Trong `forwardOnly()`, bài toán chỉ yêu cầu đọc lần lượt; không có thao tác nào cần quay về hàng cũ.
- Trong `scrollable()`, ứng dụng có thể đến cuối kết quả, trở về đầu, duyệt lại và nhảy đến hàng thứ ba. Lời gọi `last()` trả về `false` nếu không có hàng; vì vậy chỉ lấy `getRow()` bên trong nhánh thành công.

`getRow()` trả về **vị trí hàng hiện tại** (đánh số từ 1), không phải phép đếm số lượng hàng được tối ưu cho mọi tình huống. Mẹo `last()` rồi `getRow()` có thể buộc driver duyệt hoặc nạp toàn bộ tập kết quả. Nếu chỉ cần đếm số bản ghi trong dữ liệu lớn, thông thường nên dùng truy vấn `SELECT COUNT(*)` với cùng bộ lọc thay vì mở con trỏ cuộn.

## 5. Những phương thức điều hướng cần nhớ

| Phương thức | Con trỏ chỉ tiến | Con trỏ có thể cuộn | Ý nghĩa |
|---|---|---|---|
| `next()` | Có | Có | Sang hàng tiếp theo; `false` nếu hết |
| `previous()` | Không được đảm bảo | Có | Về hàng trước |
| `first()` | Không được đảm bảo | Có | Đến hàng đầu tiên |
| `last()` | Không được đảm bảo | Có | Đến hàng cuối cùng |
| `beforeFirst()` | Không được đảm bảo | Có | Đặt trước hàng đầu tiên |
| `afterLast()` | Không được đảm bảo | Có | Đặt sau hàng cuối cùng |
| `absolute(n)` | Không được đảm bảo | Có | Đến hàng có vị trí `n` |
| `relative(n)` | Không được đảm bảo | Có | Dịch `n` hàng từ vị trí hiện tại |
| `getRow()` | Có thể dùng tại hàng hợp lệ | Có thể dùng tại hàng hợp lệ | Lấy số thứ tự hàng hiện tại |

Cần hiểu chính xác tham số di chuyển:

```java
// Các lời gọi dưới đây yêu cầu ResultSet có thể cuộn:
rs.first();        // Hàng 1, nếu có.
rs.absolute(3);    // Hàng 3, nếu có.
rs.absolute(-1);   // Hàng cuối, nếu có.
rs.relative(-2);   // Lùi 2 hàng từ vị trí hiện tại.
rs.beforeFirst();  // Trước hàng 1.
rs.next();         // Đến hàng 1, nếu có.
rs.afterLast();    // Sau hàng cuối.
rs.previous();     // Về hàng cuối, nếu có.
```

Các giá trị trả về của `first()`, `last()`, `absolute()`, `relative()`, `next()` và `previous()` nên được kiểm tra trước khi đọc cột. Nếu kết quả rỗng, không có hàng hiện tại để đọc. `absolute(0)` đưa con trỏ đến vị trí trước hàng đầu tiên. Tham số âm của `absolute()` được tính từ cuối tập kết quả; `absolute(-1)` là hàng cuối.

**Một lỗi thường gặp:** sau `while (rs.next())`, con trỏ đã ở sau hàng cuối; gọi `rs.getString("name")` khi đó là sai. Với con trỏ cuộn, có thể gọi `beforeFirst()` rồi duyệt lại; với con trỏ chỉ tiến, phương pháp an toàn là xử lý dữ liệu ngay trong vòng lặp hoặc thực hiện truy vấn lại khi cần thiết.

## 6. Kiểm tra khả năng hỗ trợ và loại con trỏ thực tế

Không phải mọi driver JDBC đều hỗ trợ đầy đủ ba loại. Trước khi dựa vào thao tác cuộn, kiểm tra metadata:

```java
DatabaseMetaData meta = connection.getMetaData();

boolean canScrollInsensitive =
        meta.supportsResultSetType(ResultSet.TYPE_SCROLL_INSENSITIVE);

boolean canScrollSensitive =
        meta.supportsResultSetType(ResultSet.TYPE_SCROLL_SENSITIVE);

boolean canScrollReadOnly =
        meta.supportsResultSetConcurrency(
                ResultSet.TYPE_SCROLL_INSENSITIVE,
                ResultSet.CONCUR_READ_ONLY);

System.out.println("Scrollable insensitive: " + canScrollInsensitive);
System.out.println("Scrollable sensitive: " + canScrollSensitive);
System.out.println("Scrollable read-only: " + canScrollReadOnly);
```

`supportsResultSetType()` trả lời khả năng hỗ trợ kiểu con trỏ; `supportsResultSetConcurrency()` kiểm tra tổ hợp **kiểu con trỏ + khả năng cập nhật**. Khi xây dựng chương trình cần kiểm tra tính năng, đây là hai phép kiểm tra bổ sung cho nhau.

Ngay cả khi yêu cầu một kiểu cụ thể, hãy xác minh kết quả thực tế:

```java
try (Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
     ResultSet rs = statement.executeQuery(
        "SELECT id, name FROM customers")) {

    int actualType = rs.getType();
    int actualConcurrency = rs.getConcurrency();

    System.out.println("Type: " + actualType);
    System.out.println("Concurrency: " + actualConcurrency);
}
```

Một số driver có thể giảm cấp (*downgrade*) kiểu hoặc concurrency đã yêu cầu và cung cấp cảnh báo `SQLWarning`; driver khác có thể phát sinh `SQLException` khi không hỗ trợ. Vì vậy không nên giả định rằng chỉ cần truyền hằng số khi tạo statement là mọi tính năng đều sẵn có.

Nếu driver không hỗ trợ scrollable, ứng dụng có thể **thiết kế lại để chỉ duyệt tiến**, lưu những hàng thực sự cần xem lại vào một danh sách có giới hạn, hoặc chạy một truy vấn mới có điều kiện phù hợp. Chọn cách xử lý theo kích thước dữ liệu và yêu cầu nghiệp vụ.

## 7. So sánh về bộ nhớ, tốc độ và tính đúng đắn

Khả năng cuộn có thể khiến driver hoặc DBMS cần lưu thêm trạng thái của kết quả (ví dụ lưu các hàng để di chuyển ngược). Trong khi đó, kiểu chỉ tiến thường phù hợp cho luồng xử lý tuần tự. Đây là **xu hướng thiết kế**, không phải lời bảo đảm rằng `TYPE_FORWARD_ONLY` luôn truyền dữ liệu theo streaming hay `TYPE_SCROLL_INSENSITIVE` luôn nạp hết dữ liệu vào RAM.

| Tiêu chí | Chỉ tiến | Có thể cuộn |
|---|---|---|
| Bài toán điển hình | Quét dữ liệu, xuất file, xử lý một lần | Xem lại hàng, duyệt qua lại, nhảy tới vị trí |
| Hỗ trợ trên driver | Thường rộng | Phụ thuộc driver/DBMS và loại scrollable |
| Di chuyển ngược | Không | Có |
| Chi phí trạng thái | Có thể thấp hơn | Có thể cao hơn do phải duy trì khả năng di chuyển |
| Thấy thay đổi đồng thời | Phụ thuộc driver, transaction | Còn phụ thuộc insensitive/sensitive và isolation |
| Thích hợp cho dữ liệu rất lớn | Thường là lựa chọn đầu tiên khi chỉ cần duyệt tuần tự | Cần đo đạc bộ nhớ/độ trễ trước khi áp dụng |

Các yếu tố quan trọng ngoài kiểu con trỏ:

- **`setFetchSize(int)` là gợi ý** cho driver về cách lấy dữ liệu theo lô; nó không tự biến `ResultSet` chỉ tiến thành con trỏ cuộn, cũng không bảo đảm streaming.
- **`setFetchDirection()` là gợi ý** về hướng lấy dữ liệu; `FETCH_REVERSE` không tạo khả năng gọi `previous()` nếu kiểu ResultSet không hỗ trợ cuộn.
- **Transaction isolation** quyết định phần nào việc kết quả có thể nhìn thấy cập nhật từ transaction khác.
- **Số lượng hàng và câu SQL** tác động đáng kể đến chi phí; điều hướng đến hàng cuối của một kết quả lớn có thể tốn thời gian.
- **Phân trang trong SQL** (ví dụ `LIMIT/OFFSET`, `FETCH FIRST` hoặc keyset pagination tùy DBMS) thường phù hợp hơn việc tạo scrollable ResultSet dài hạn cho giao diện phân trang nhiều trang.

Cần đóng `ResultSet` và `Statement` sớm bằng `try-with-resources`. Một con trỏ mở lâu có thể giữ tài nguyên phía driver hoặc database. Không chia sẻ cùng một `ResultSet` đang thay đổi vị trí con trỏ cho nhiều luồng xử lý độc lập.

## 8. Các khái niệm dễ nhầm lẫn

### 8.1. Scrollable khác updatable

`TYPE_SCROLL_INSENSITIVE` / `TYPE_SCROLL_SENSITIVE` nói về **di chuyển con trỏ** và khả năng nhìn thấy thay đổi bên ngoài. `CONCUR_READ_ONLY` / `CONCUR_UPDATABLE` nói về **khả năng cập nhật thông qua ResultSet**. Ví dụ, `TYPE_SCROLL_INSENSITIVE + CONCUR_READ_ONLY` cho phép điều hướng hai chiều nhưng không cấp quyền sửa hàng thông qua `ResultSet`.

### 8.2. Sensitive không đồng nghĩa với dữ liệu luôn mới nhất

Nếu một transaction đang hoạt động ở mức cô lập có snapshot ổn định, `TYPE_SCROLL_SENSITIVE` không thể mặc nhiên bỏ qua cơ chế isolation đó. Khả năng nhìn thấy insert, update và delete cũng có thể khác nhau theo driver. Nếu ứng dụng bắt buộc lấy trạng thái mới nhất theo một nghiệp vụ cụ thể, hãy thiết kế transaction và truy vấn tương ứng, rồi thử nghiệm trên DBMS thật.

### 8.3. Con trỏ cuộn không thay thế ORDER BY

`absolute(3)` có nghĩa là **hàng thứ ba của tập kết quả đang có**, không phải bản ghi có khóa chính bằng 3. Nếu muốn thứ tự có thể dự đoán và lặp lại, truy vấn cần có `ORDER BY` với tiêu chí sắp xếp đủ xác định (ví dụ cả một cột khóa duy nhất).

### 8.4. Di chuyển con trỏ không tạo truy vấn mới

`previous()` hay `absolute()` không tương đương với việc chạy lại `SELECT` để truy xuất một phiên bản dữ liệu mới. Mỗi `ResultSet` gắn với quá trình thực thi truy vấn và có vòng đời riêng. Kết thúc hoặc đóng statement, đóng connection hay cấu hình commit có thể ảnh hưởng đến vòng đời result set theo driver và holdability.

## 9. Chọn kiểu con trỏ theo tình huống

**Tình huống A — Xuất CSV hàng triệu bản ghi:** chỉ cần duyệt một lần. Ưu tiên `TYPE_FORWARD_ONLY` và thử nghiệm cơ chế fetch/streaming thực tế của driver, xử lý từng hàng và ghi tuần tự. Nếu cần phân trang hoặc chia lô lớn, cân nhắc chiến lược truy vấn phù hợp thay vì giữ một tập kết quả khổng lồ.

**Tình huống B — Màn hình kiểm tra một tập dữ liệu nhỏ:** người dùng cần xem lại bản ghi trước hoặc nhảy đến hàng cuối. `TYPE_SCROLL_INSENSITIVE` với `CONCUR_READ_ONLY` có thể phù hợp nếu driver hỗ trợ và kích thước tập kết quả được kiểm soát.

**Tình huống C — Màn hình theo dõi cập nhật từ người dùng khác:** có thể cân nhắc `TYPE_SCROLL_SENSITIVE` nếu được hỗ trợ, nhưng cần xác minh loại thay đổi thực sự xuất hiện dưới mức cô lập đang dùng. Trong nhiều hệ thống, truy vấn lại theo chu kỳ hoặc cơ chế thông báo thay đổi đáng tin cậy hơn.

**Tình huống D — Ứng dụng web phân trang sản phẩm:** dùng truy vấn phân trang và thứ tự ổn định để lấy đúng trang người dùng cần. Giữ một `ResultSet` cuộn mở qua nhiều HTTP request thường gây khó khăn về vòng đời connection và tài nguyên.

## 10. Tự kiểm tra

**Câu 1.** `connection.createStatement()` mặc định yêu cầu loại ResultSet nào?

**Đáp án:** `TYPE_FORWARD_ONLY` và `CONCUR_READ_ONLY`.

**Câu 2.** Muốn gọi `previous()`, nên yêu cầu loại nào?

**Đáp án:** `TYPE_SCROLL_INSENSITIVE` hoặc `TYPE_SCROLL_SENSITIVE`, nếu driver và DBMS hỗ trợ.

**Câu 3.** Trong `TYPE_SCROLL_INSENSITIVE`, gọi `absolute(-1)` có ý nghĩa gì?

**Đáp án:** Di chuyển đến hàng cuối, trả về `true` nếu có hàng; nếu tập kết quả rỗng, trả về `false`.

**Câu 4.** `TYPE_SCROLL_SENSITIVE` có bảo đảm nhìn thấy tức thì mọi sửa đổi của transaction khác không?

**Đáp án:** Không. Khả năng và thời điểm phản ánh thay đổi phụ thuộc driver, DBMS và mức cô lập.

**Câu 5.** `ResultSet.TYPE_SCROLL_INSENSITIVE` có đồng nghĩa với `CONCUR_UPDATABLE` không?

**Đáp án:** Không. Kiểu con trỏ và khả năng cập nhật là hai tham số khác nhau.

**Câu 6.** Vì sao `rs.last(); rs.getRow();` không phải cách đếm hàng tối ưu cho mọi truy vấn?

**Đáp án:** Nó có thể khiến driver phải duyệt hoặc tải nhiều hàng; khi chỉ cần số lượng bản ghi, `SELECT COUNT(*)` với bộ lọc tương ứng thường phù hợp hơn.

Khi cần chọn con trỏ, hãy bắt đầu từ câu hỏi ứng dụng có thực sự phải **di chuyển ngược hoặc nhảy đến hàng bất kỳ** hay không. Nếu chỉ đọc một lượt, `TYPE_FORWARD_ONLY` là lựa chọn đơn giản. Nếu phải điều hướng, yêu cầu một loại scrollable, kiểm tra khả năng hỗ trợ, xác minh loại thực tế và đánh giá chi phí trên cơ sở dữ liệu mà hệ thống sử dụng.
