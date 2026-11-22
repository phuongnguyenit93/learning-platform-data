# Mô hình con trỏ và vị trí trước bản ghi đầu tiên

## 1. `ResultSet` đại diện cho điều gì?

Trong **JDBC (Java Database Connectivity)**, API dùng để truy cập cơ sở dữ liệu quan hệ từ Java, `java.sql.ResultSet` biểu diễn kết quả dạng bảng của một truy vấn SQL. Mỗi hàng là một bản ghi (row), mỗi cột chứa một giá trị có thể đọc bằng các phương thức như `getLong`, `getString` hoặc `getTimestamp`.

Điểm quan trọng nhất: **`ResultSet` có con trỏ (cursor) chỉ vị trí hàng hiện tại**. Khi gọi một phương thức `getXxx(...)`, JDBC đọc giá trị ở **hàng mà con trỏ đang đứng**. `ResultSet` không hoạt động như `List` để có thể truy cập trực tiếp hàng đầu tiên bằng chỉ số `0`.

Ngay sau khi `executeQuery()` trả về một `ResultSet` mới, con trỏ ở vị trí **trước hàng đầu tiên** (*before first*), dù truy vấn có trả về hàng hay không. Vì vậy, cần gọi `next()` thành công trước khi đọc dữ liệu hàng.

## 2. Hình dung các vị trí của con trỏ

Giả sử truy vấn `SELECT id, full_name FROM customers ORDER BY id` trả về ba hàng:

```text
                    ResultSet (3 hàng)

  BEFORE FIRST      Hàng 1       Hàng 2       Hàng 3       AFTER LAST
       ●       ---> [id=11] ---> [id=12] ---> [id=13] --->     ●
   (ban đầu)           ^
                       |
              next() lần thứ nhất
```

`BEFORE FIRST` và `AFTER LAST` là **hai vị trí biên**, không phải hai hàng dữ liệu. Không có giá trị cột hợp lệ để lấy tại các vị trí này.

| Vị trí | Có hàng hiện tại để đọc? | Kết quả của thao tác tiếp theo |
|---|---|---|
| Trước hàng đầu tiên (*before first*) | Không | `next()` trả về `true` và chuyển đến hàng 1, nếu có |
| Tại một hàng hợp lệ | Có | `getXxx(...)` đọc giá trị cột của hàng đó; `next()` thử chuyển sang hàng kế |
| Sau hàng cuối (*after last*) | Không | Lượt `next()` đưa con trỏ vượt hàng cuối trả về `false` |

Phân biệt **số thứ tự hàng** và **số thứ tự cột**: cả vị trí hàng của `getRow()` (khi đang ở hàng hợp lệ) lẫn chỉ số cột của `getXxx(int columnIndex)` đều bắt đầu từ **1**. Giá trị `0` của `getRow()` chỉ ra rằng không có số hàng hiện tại, chẳng hạn khi ở trước hàng đầu hoặc sau hàng cuối.

## 3. `next()` là thao tác đưa con trỏ đến hàng có thể đọc

Phương thức `boolean next()` thử di chuyển con trỏ **tiến một hàng**:

- Trả về `true`: đã đến một hàng dữ liệu hợp lệ; lúc này có thể gọi `getXxx(...)`.
- Trả về `false`: không còn hàng kế tiếp; không được tiếp tục đọc cột như thể vẫn đứng ở hàng vừa duyệt.
- Có thể ném `SQLException` nếu xảy ra lỗi truy cập dữ liệu.

Với kết quả ba hàng, các lần gọi được hiểu như sau:

| Lần gọi | Giá trị trả về | Vị trí sau lời gọi | Có thể gọi `getString("full_name")`? |
|---|---|---|---|
| Trước khi gọi `next()` | — | Trước hàng 1 | Không |
| `next()` lần 1 | `true` | Hàng 1 | Có |
| `next()` lần 2 | `true` | Hàng 2 | Có |
| `next()` lần 3 | `true` | Hàng 3 | Có |
| `next()` lần 4 | `false` | Sau hàng cuối | Không |

Không nên gọi `getString`, `getInt` hoặc các getter khác trước khi `next()` trả về `true`. Ví dụ sau sai vì con trỏ **chưa đứng ở hàng dữ liệu**:

```java
try (ResultSet rs = statement.executeQuery()) {
    // SAI: rs vẫn ở vị trí trước hàng đầu tiên.
    String name = rs.getString("full_name");
}
```

Một trình điều khiển JDBC tuân thủ hợp đồng sẽ báo `SQLException` khi cố đọc cột ở vị trí con trỏ không hợp lệ. Cách đúng là kiểm tra kết quả của `next()` trước:

```java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        String name = rs.getString("full_name");
        System.out.println(name);
    } else {
        System.out.println("Truy vấn không trả về bản ghi nào.");
    }
}
```

Ở hai ví dụ này, `statement` được hiểu là một `PreparedStatement` đã tạo từ trước và còn mở.

## 4. Mẫu duyệt tất cả hàng bằng `while (rs.next())`

Đây là cách đọc `ResultSet` phổ biến và phù hợp với kiểu kết quả chỉ được phép đi tới. Ví dụ dưới đây giả định chương trình đã có một đối tượng `javax.sql.DataSource` tên là `dataSource` và bảng `customers(id, full_name)`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class CustomerReader {
    private final DataSource dataSource;

    public CustomerReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printCustomers() throws SQLException {
        String sql = "SELECT id, full_name FROM customers ORDER BY id";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet rs = statement.executeQuery()) {

            while (rs.next()) {
                long id = rs.getLong("id");
                String name = rs.getString("full_name");
                System.out.println(id + " - " + name);
            }
        }
    }
}
```

Với dữ liệu mẫu `(11, "An")`, `(12, "Bình")`, `(13, "Chi")`, kết quả in ra là:

```text
11 - An
12 - Bình
13 - Chi
```

Diễn biến của mỗi vòng lặp:

1. **Điều kiện `rs.next()` chạy trước thân vòng lặp.** Lần đầu tiên, nó đưa con trỏ từ *before first* đến hàng 1.
2. Khi `next()` trả về `true`, thân vòng lặp đọc các cột của đúng hàng hiện tại.
3. Vòng lặp tiếp tục: `next()` chuyển sang hàng 2, rồi hàng 3.
4. Khi hết hàng, `next()` trả về `false`; thân vòng lặp không chạy nữa.

Trong ví dụ, `ORDER BY id` xác định thứ tự xuất ra. **Con trỏ tuần tự đọc theo thứ tự kết quả SQL trả về**; nếu bỏ `ORDER BY`, không nên mặc định rằng cơ sở dữ liệu sẽ luôn trả các hàng theo thứ tự `id`.

`try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` khi rời khối, kể cả lúc có ngoại lệ. Việc đóng tài nguyên quan trọng vì `ResultSet` thường gắn với statement và tài nguyên của trình điều khiển/cơ sở dữ liệu.

## 5. Kết quả rỗng: không bao giờ xuất hiện hàng hợp lệ

Giả sử truy vấn có điều kiện `WHERE id = ?`, nhưng không có khách hàng trùng `id`:

```java
String sql = "SELECT id, full_name FROM customers WHERE id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, -1L);

    try (ResultSet rs = statement.executeQuery()) {
        if (!rs.next()) {
            System.out.println("Không tìm thấy khách hàng.");
        }
    }
}
```

Với `ResultSet` rỗng, **lần gọi `next()` đầu tiên trả về `false`**. Không có bất kỳ thời điểm nào mà các getter được phép đọc một hàng. Đây là lý do nên dùng trực tiếp giá trị boolean của `next()` để quyết định có dữ liệu hay không, thay vì cố đọc một cột rồi bắt ngoại lệ.

Hai phương thức kiểm tra vị trí biên có một chi tiết dễ nhầm:

| Trạng thái kết quả | `isBeforeFirst()` | `isAfterLast()` |
|---|---|---|
| Có ít nhất một hàng; con trỏ vừa khởi tạo | `true` | `false` |
| Có ít nhất một hàng; đã gọi `next()` đến khi trả `false` | `false` | `true` |
| **Không có hàng** | **`false`** | **`false`** |

Như vậy, **`isBeforeFirst() == false` không chứng minh đã đọc hàng đầu tiên**, và **`isAfterLast() == false` không chứng minh kết quả có dữ liệu**. `getRow() == 0` cũng không cho biết kết quả rỗng hay chỉ là con trỏ đang ở ngoài các hàng hợp lệ. Ngoài ra, khả năng hỗ trợ các thao tác kiểm tra vị trí trên `ResultSet` kiểu `TYPE_FORWARD_ONLY` có thể phụ thuộc trình điều khiển; cấu trúc vòng lặp `next()` không cần dựa vào chúng.

## 6. Đọc một hàng hay nhiều hàng: chọn cấu trúc phù hợp

Nếu chỉ cần **hàng đầu tiên** (ví dụ tìm một bản ghi theo khóa chính), dùng `if (rs.next())`:

```java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        System.out.println("Khách hàng đầu tiên: " + rs.getString("full_name"));
    }
}
```

Nếu cần **tất cả hàng**, dùng `while (rs.next())`. Một lỗi thường gặp là gọi `next()` để kiểm tra trước, rồi lại mở vòng `while (rs.next())`:

```java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        // Lúc này con trỏ ĐÃ ở hàng 1.
        while (rs.next()) {
            // SAI: bắt đầu từ hàng 2, bỏ mất hàng 1.
            System.out.println(rs.getString("full_name"));
        }
    }
}
```

Nếu phải vừa kiểm tra có dữ liệu vừa xử lý **toàn bộ** các hàng, có thể dùng `do ... while` sau lần `next()` đầu:

```java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        do {
            System.out.println(rs.getString("full_name"));
        } while (rs.next());
    } else {
        System.out.println("Danh sách rỗng.");
    }
}
```

Trong đa số trường hợp, `while (rs.next())` đơn giản hơn và ít gây nhầm lẫn hơn.

## 7. `TYPE_FORWARD_ONLY` và khả năng quay lại *before first*

Với cách tạo `Statement`/`PreparedStatement` thông thường, kiểu `ResultSet` mặc định là `ResultSet.TYPE_FORWARD_ONLY`: con trỏ tiến về phía trước bằng `next()`. **Đừng giả định có thể quay lại hàng đầu hoặc duyệt lần thứ hai** sau khi đã đọc hết.

JDBC còn định nghĩa các kiểu có thể cuộn (*scrollable*), chẳng hạn `TYPE_SCROLL_INSENSITIVE` và `TYPE_SCROLL_SENSITIVE`. Trên `ResultSet` hỗ trợ cuộn, `beforeFirst()` có thể đưa con trỏ về vị trí **trước hàng đầu tiên** để bắt đầu duyệt lại:

```java
String sql = "SELECT id, full_name FROM customers ORDER BY id";

try (PreparedStatement statement = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY);
     ResultSet rs = statement.executeQuery()) {

    while (rs.next()) {
        System.out.println(rs.getString("full_name"));
    }

    rs.beforeFirst(); // Hợp lệ trên ResultSet cuộn hỗ trợ thao tác này.

    while (rs.next()) {
        System.out.println("Đọc lại: " + rs.getString("full_name"));
    }
}
```

**Lưu ý về tính tương thích:** không phải mọi driver/cơ sở dữ liệu đều hỗ trợ tất cả kiểu cuộn. Có thể kiểm tra `connection.getMetaData().supportsResultSetType(ResultSet.TYPE_SCROLL_INSENSITIVE)` trước khi yêu cầu. Phương thức `beforeFirst()` không được dùng để tua lại một `TYPE_FORWARD_ONLY`; nếu kết quả rỗng thì gọi `beforeFirst()` trên tập kết quả cuộn cũng không tạo ra hàng dữ liệu nào.

Chỉ nên chọn kết quả cuộn khi thực sự cần nhảy tới lui. Việc tải lại truy vấn hoặc giữ dữ liệu đã đọc trong một cấu trúc Java đôi khi phù hợp hơn, tùy dung lượng và yêu cầu ứng dụng.

## 8. Những nhầm lẫn dễ dẫn đến lỗi

| Nhầm lẫn | Hệ quả | Cách đúng |
|---|---|---|
| `executeQuery()` tự đặt con trỏ ở hàng 1 | Gọi getter quá sớm, gặp `SQLException` | Gọi `next()` và kiểm tra `true` trước khi đọc |
| `next()` chỉ *kiểm tra*, không di chuyển | Kiểm tra hai lần làm bỏ sót hàng | Nhớ rằng mỗi `next()` thành công đều tiến một hàng |
| Hàng đầu tiên có số thứ tự `0` | Dùng sai ý nghĩa `getRow()`/chỉ số cột | Chỉ số hàng/cột JDBC bắt đầu từ `1` |
| `next() == false` nhưng vẫn còn hàng hiện tại để lấy dữ liệu | Cố đọc sau khi đã vượt hàng cuối | Chỉ đọc trong nhánh `true` hoặc trong thân `while` |
| `isBeforeFirst() == false` nghĩa là truy vấn có hàng | Kết luận sai với `ResultSet` rỗng | Dùng `next()` để kiểm tra sự tồn tại của hàng |
| Có thể gọi `beforeFirst()` trên mọi `ResultSet` | Lỗi khi dùng kết quả chỉ đi tới | Chỉ sử dụng thao tác quay lại khi đã yêu cầu và được hỗ trợ kiểu cuộn |
| Thứ tự hàng luôn giống thứ tự chèn dữ liệu | Kết quả thay đổi khi DB tối ưu truy vấn | Dùng `ORDER BY` nếu nghiệp vụ cần thứ tự ổn định |

## 9. Tự kiểm tra bằng cách lần theo con trỏ

Xét kết quả gồm hai hàng theo thứ tự `An`, `Bình`:

```java
try (ResultSet rs = statement.executeQuery()) {
    System.out.println(rs.next());
    System.out.println(rs.getString("full_name"));
    System.out.println(rs.next());
    System.out.println(rs.getString("full_name"));
    System.out.println(rs.next());
}
```

Nếu truy vấn thực sự trả về đúng hai hàng theo thứ tự trên, đầu ra là:

```text
true
An
true
Bình
false
```

Sau dòng `false`, con trỏ không còn đứng trên một hàng hợp lệ. Nếu kết quả **rỗng**, dòng `rs.next()` đầu tiên đã trả về `false`, và dòng `getString(...)` kế tiếp sẽ sai do không có hàng hiện tại. Ví dụ trên chủ đích chỉ minh họa diễn biến của con trỏ khi **biết chắc** có hai hàng; trong mã ứng dụng thực tế, luôn dùng `if` hoặc `while` để bảo vệ thao tác đọc.

**Ghi nhớ:** trạng thái ban đầu của `ResultSet` là **trước hàng đầu tiên**; `next()` vừa **di chuyển** vừa **trả về thông tin có đến được một hàng hợp lệ hay không**. Đây là nguyên tắc nền tảng để đọc kết quả truy vấn quan hệ qua JDBC đúng cách, kể cả khi kết quả có một hàng, nhiều hàng hoặc không có hàng nào.
