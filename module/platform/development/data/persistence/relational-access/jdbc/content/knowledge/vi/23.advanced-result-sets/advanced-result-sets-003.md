# Di chuyển tới bản ghi đầu, cuối, trước và vị trí cụ thể trong JDBC

## 1. Vì sao cần di chuyển con trỏ ResultSet?

Trong JDBC, `PreparedStatement.executeQuery()` trả về một `ResultSet`. Đối với cách truy vấn thông dụng, con trỏ của `ResultSet` bắt đầu **trước hàng đầu tiên**; mỗi lần gọi `next()` sẽ đi tới hàng tiếp theo. Cách đọc tuần tự này phù hợp với xử lý nhiều hàng theo luồng, nhưng đôi khi ứng dụng cần:

- Đọc nhanh hàng **đầu** hoặc hàng **cuối** trong tập kết quả.
- Lùi về hàng **trước** sau khi đã xem một hàng.
- Nhảy tới hàng thứ 3, thứ 20 hoặc hàng tính từ cuối.
- Quay về đầu để duyệt lại tập kết quả mà không gửi lại SQL.
- Xác định vị trí hiện tại của con trỏ trong một tập kết quả có khả năng cuộn.

Ví dụ, ứng dụng quản trị nhân viên đã lấy danh sách nhân viên của một phòng ban và muốn xem người đầu tiên, người cuối cùng rồi nhảy về nhân viên ở vị trí thứ 2. Với `ResultSet` mặc định chỉ tiến tới trước, không thể giả định các thao tác này được hỗ trợ.

Bài thuộc chương **ResultSet nâng cao** của module **JDBC**, sử dụng driver, `DataSource`, `PreparedStatement`, `ResultSet`, câu SQL tham số hóa, quản lý kết nối, transaction và xử lý lỗi theo API Java chuẩn. Trọng tâm là **khả năng cuộn con trỏ** (*scrollable result set*), nhất là các phương thức `first()`, `last()`, `previous()`, `absolute()` và `relative()`.

Sau bài này, bạn có thể chọn loại `ResultSet` phù hợp, di chuyển con trỏ đúng cách, phân biệt “không có hàng” với “con trỏ đang ngoài vùng hàng hợp lệ”, kiểm tra khả năng hỗ trợ của driver và đánh giá chi phí của việc đọc ngẫu nhiên trong tập dữ liệu lớn.

## 2. Mô hình con trỏ: hàng hiện tại không phải lúc nào cũng tồn tại

Giả sử câu truy vấn trả về ba hàng theo thứ tự `ORDER BY id`:

| Vị trí (JDBC) | `id` | `full_name` |
|---:|---:|---|
| 1 | 101 | An |
| 2 | 105 | Bình |
| 3 | 109 | Chi |

Con trỏ có các trạng thái khái niệm:

```text
beforeFirst   hàng 1       hàng 2       hàng 3       afterLast
    |           |            |            |             |
    v           v            v            v             v
  [  ]   ->   [101]   ->    [105]   ->    [109]   ->    [  ]
               An           Bình          Chi

Chỉ ở vị trí hàng 1, 2 hoặc 3 mới có "current row" để đọc cột.
```

Lúc mới mở một `ResultSet` thông thường, con trỏ ở vị trí **before-first**. Khi `next()` trả `true`, nó đứng trên một hàng hợp lệ; khi tiếp tục `next()` qua hàng cuối, nó trả `false` và con trỏ ở **after-last**.

Với `ResultSet` có thể cuộn, ứng dụng còn có thể đi ngược hoặc nhảy vị trí. Nhưng **di chuyển con trỏ không tương đương với đọc dữ liệu**: chỉ sau khi thao tác định vị thành công mới được gọi `getLong(...)`, `getString(...)` hoặc getter khác.

### 2.1. Các vị trí đặc biệt

| Vị trí | Có hàng hiện tại để đọc không? | Ý nghĩa |
|---|---|---|
| Before-first | Không | Đứng ngay trước hàng đầu |
| Hàng thứ `n`, với `1 <= n <= N` | Có | Đang đứng trên một hàng của tập kết quả |
| After-last | Không | Đứng ngay sau hàng cuối |
| Tập kết quả rỗng | Không | Không tồn tại hàng đầu hay hàng cuối |

Với kết quả rỗng, nhiều phương thức như `first()` và `last()` trả `false`; các phương thức kiểm tra `isBeforeFirst()` hoặc `isAfterLast()` cũng có thể trả `false` vì không có hàng nào. Vì vậy, đừng dùng riêng `!rs.isBeforeFirst()` để kết luận con trỏ đã đứng trên một hàng hợp lệ.

## 3. Ba loại ResultSet ảnh hưởng đến khả năng điều hướng

JDBC định nghĩa các hằng trong `java.sql.ResultSet`:

| Loại | Khả năng di chuyển | Đặc tính chính |
|---|---|---|
| `TYPE_FORWARD_ONLY` | Chủ yếu đi tới trước bằng `next()` | Loại phổ biến/mặc định; không giả định hỗ trợ `first()`, `previous()` hoặc `absolute()` |
| `TYPE_SCROLL_INSENSITIVE` | Đi tới trước, lùi lại, nhảy tới hàng cụ thể | Theo hợp đồng JDBC, kết quả không nhạy với những thay đổi của người khác đối với dữ liệu nền sau khi tạo tập kết quả |
| `TYPE_SCROLL_SENSITIVE` | Có thể cuộn và nhạy với những thay đổi dữ liệu nền ở mức driver hỗ trợ | Khả năng quan sát thay đổi cụ thể phụ thuộc driver, DB, isolation và loại thay đổi |

**Không đồng nhất khả năng cuộn với khả năng cập nhật.** Một `ResultSet` có thể **cuộn được nhưng chỉ đọc**. Hai hằng `CONCUR_READ_ONLY` và `CONCUR_UPDATABLE` mô tả **chế độ cập nhật**, không mô tả hướng di chuyển. Với các ví dụ chỉ đọc trong bài, hãy dùng `CONCUR_READ_ONLY`.

Ngoài ra, `TYPE_SCROLL_INSENSITIVE` không có nghĩa một truy vấn chạy lại ở thời điểm sau sẽ luôn nhận cùng dữ liệu. Nó chỉ mô tả đặc tính của **đối tượng ResultSet đang mở** trong khuôn khổ hỗ trợ driver. Tính nhất quán khi nhiều giao dịch cùng thay đổi dữ liệu còn phụ thuộc isolation và cách hệ quản trị thực thi truy vấn.

### 3.1. Tạo PreparedStatement yêu cầu ResultSet cuộn được

Overload chuẩn:

```java
PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY
);
```

Hai tham số số nguyên sau `sql` là **loại ResultSet** và **chế độ concurrency**; chúng không phải `fetchSize`, không phải số hàng tối đa và không phải tham số của SQL.

Ứng dụng vẫn bind các placeholder `?` bằng `setLong`, `setString` hoặc setter phù hợp rồi gọi `executeQuery()`. Ví dụ đầy đủ ở mục 6.

Nếu chỉ gọi `connection.prepareStatement(sql)` mà không chỉ định loại ResultSet, không nên giả định kết quả sẽ cuộn được. Muốn dùng `last()` hay `absolute()` một cách đáng tin cậy, phải yêu cầu loại phù hợp và kiểm tra hỗ trợ thực tế.

## 4. Các phương thức di chuyển con trỏ

### 4.1. Bảng tham chiếu nhanh

Giả sử có đúng `N` hàng, đánh số từ 1 đến `N`:

| Phương thức | Hành động | Giá trị trả về/điểm cần nhớ |
|---|---|---|
| `next()` | Đi tới hàng tiếp theo | `true` nếu đứng trên hàng hợp lệ; `false` nếu qua cuối |
| `previous()` | Đi tới hàng trước | `true` nếu đứng trên hàng hợp lệ; `false` nếu qua đầu |
| `first()` | Đến hàng đầu tiên | `true` nếu có hàng; `false` nếu tập rỗng |
| `last()` | Đến hàng cuối cùng | `true` nếu có hàng; `false` nếu tập rỗng |
| `beforeFirst()` | Đưa con trỏ về trước hàng đầu | Không trả boolean; không có hàng hiện tại sau thao tác |
| `afterLast()` | Đưa con trỏ về sau hàng cuối | Không trả boolean; không có hàng hiện tại sau thao tác |
| `absolute(int row)` | Nhảy tới vị trí tuyệt đối | Số dương tính từ đầu; số âm tính từ cuối; `0` là before-first |
| `relative(int rows)` | Nhảy tương đối từ hàng hiện tại | Số dương đi tới trước; số âm đi lùi; dùng từ vị trí hợp lệ để tránh lỗi trạng thái |
| `getRow()` | Hỏi số thứ tự hàng hiện tại | Bắt đầu từ 1; `0` nếu không có hàng hiện tại |
| `isFirst()` / `isLast()` | Kiểm tra có ở hàng đầu/cuối không | Trả boolean; trên tập rỗng là `false` |
| `isBeforeFirst()` / `isAfterLast()` | Kiểm tra có đứng ngoài đầu/cuối không | Không được dùng một mình để khẳng định kết quả không rỗng |

Các phương thức định vị yêu cầu ResultSet hỗ trợ kiểu cuộn tương ứng. Nếu gọi trên `TYPE_FORWARD_ONLY`, driver có thể ném `SQLException`, thường là `SQLFeatureNotSupportedException` trong các trường hợp báo không hỗ trợ tính năng. Một số phương thức kiểm tra vị trí cũng có giới hạn trên forward-only; đừng dựa vào việc chúng luôn hoạt động trên mọi driver.

### 4.2. Di chuyển tới đầu bằng first()

```java
if (rs.first()) {
    long id = rs.getLong("id");
    String name = rs.getString("full_name");
    System.out.println("Đầu tiên: " + id + " - " + name);
} else {
    System.out.println("Không có hàng nào");
}
```

`rs.first()` sẽ điều hướng tới hàng 1 nếu nó tồn tại, bất kể trước đó con trỏ ở hàng nào. Nếu không có hàng, `false` là nhánh hợp lệ và không được đọc cột ngay sau đó.

### 4.3. Di chuyển tới cuối bằng last()

```java
if (rs.last()) {
    System.out.println("Cuối cùng: " + rs.getString("full_name"));
    System.out.println("Vị trí: " + rs.getRow());
}
```

Với ba hàng mẫu, `last()` đứng ở hàng 3 và `getRow()` trả `3`. Nhưng **đừng xem `last()` là phép toán luôn O(1)**. Tùy driver, nó có thể cần đọc hoặc giữ toàn bộ tập kết quả trong bộ nhớ/phía máy chủ để biết hàng cuối.

### 4.4. Đi lùi bằng previous()

```java
if (rs.last()) {
    // Từ hàng 3 chuyển sang hàng 2.
    if (rs.previous()) {
        System.out.println(rs.getString("full_name")); // Bình
    }
}
```

Nếu chỉ có một hàng, `last()` thành công nhưng `previous()` trả `false` và di chuyển ra trước hàng đầu. Nếu con trỏ đang `afterLast` trong một tập có hàng, `previous()` có thể di chuyển về hàng cuối.

Quy tắc an toàn: đọc hàng sau `previous()` **chỉ khi** nó trả `true`.

### 4.5. Nhảy tới vị trí bằng absolute(row)

Với ba hàng ở bảng mẫu:

| Lệnh | Vị trí sau khi gọi | Kết quả |
|---|---|---|
| `rs.absolute(1)` | Hàng 1 (An) | `true` |
| `rs.absolute(2)` | Hàng 2 (Bình) | `true` |
| `rs.absolute(3)` | Hàng 3 (Chi) | `true` |
| `rs.absolute(-1)` | Hàng cuối: hàng 3 (Chi) | `true` |
| `rs.absolute(-2)` | Hàng áp cuối: hàng 2 (Bình) | `true` |
| `rs.absolute(-3)` | Hàng đầu: hàng 1 (An) | `true` |
| `rs.absolute(0)` | Before-first | `false` |
| `rs.absolute(4)` | After-last | `false` |
| `rs.absolute(-4)` | Before-first | `false` |

Đặc biệt, **`absolute(-1)` không phải “hàng trước”**; nó là **hàng cuối cùng**. Nếu muốn đi lùi một hàng tính từ vị trí hiện tại, hãy dùng `previous()` hoặc `relative(-1)`.

```java
if (rs.absolute(-2)) {
    System.out.printf(
            "Áp cuối: row=%d, id=%d%n",
            rs.getRow(),
            rs.getLong("id")
    );
}
```

Nếu tập có ít hơn hai hàng, `absolute(-2)` trả `false`; code phải xử lý tình huống đó thay vì mặc định luôn có hàng áp cuối.

### 4.6. Di chuyển tương đối bằng relative(rows)

`relative(n)` di chuyển từ **hàng hiện tại**. Ví dụ:

```java
if (rs.absolute(3)) {               // ở hàng 3 (Chi)
    if (rs.relative(-2)) {          // về hàng 1 (An)
        System.out.println(rs.getString("full_name"));
    }
}
```

Với một tập có 3 hàng, từ hàng 2 gọi `relative(1)` sẽ sang hàng 3; từ hàng 3 gọi `relative(1)` sẽ vượt ra sau cuối, trả `false`. Lời gọi `relative(0)` trên một hàng hợp lệ giữ nguyên vị trí.

Không nên gọi `relative(...)` tùy tiện khi con trỏ chưa ở hàng hiện tại, chẳng hạn ngay sau một lần `absolute(99)` trả `false`. Trong một số trạng thái/driver, phép di chuyển tương đối từ outside-row có thể ném `SQLException`. Khi cần đặt lại vị trí từ bất kỳ trạng thái nào, `absolute(n)`, `first()` hoặc `beforeFirst()` thường dễ lập luận hơn.

## 5. Tập rỗng, tập một hàng và trạng thái ngoài vùng hợp lệ

### 5.1. Tập kết quả rỗng

Ví dụ truy vấn không có hàng nào cho `department_id = 999`. Với ResultSet có thể cuộn:

```java
boolean hasFirst = rs.first(); // false
boolean hasLast  = rs.last();  // false
int rowNumber = rs.getRow();   // 0 vì không có hàng hiện tại
```

Các giá trị `rs.isBeforeFirst()` và `rs.isAfterLast()` thường đều là `false` nếu ResultSet không có hàng. Vì vậy, muốn biết có dữ liệu hay không, hãy kiểm tra kết quả của thao tác điều hướng trả boolean, ví dụ `rs.first()`, hoặc `rs.next()` sau `beforeFirst()`.

**Không đọc getter** như `getLong("id")` sau khi `first()` trả `false`. Hầu hết driver sẽ báo `SQLException` vì con trỏ không đứng trên hàng hợp lệ.

### 5.2. Chỉ một hàng

Khi tập kết quả có đúng một hàng:

- `first()` và `last()` đều thành công, cùng chỉ tới hàng 1.
- `isFirst()` và `isLast()` đều có thể là `true` trên hàng đó.
- `previous()` từ hàng duy nhất trả `false` và đưa con trỏ về trước hàng đầu.
- `absolute(-1)` trả `true`, nhưng `absolute(-2)` trả `false`.
- `getRow()` bằng `1` khi con trỏ ở hàng hợp lệ; bằng `0` khi không có hàng hiện tại.

Đây là tình huống kiểm thử quan trọng vì code “lấy hàng áp cuối” không được mặc định luôn có kết quả.

### 5.3. Đọc tiếp sau khi di chuyển thất bại là lỗi thường gặp

```java
// Sai: absolute(5) có thể trả false nếu tập có < 5 hàng.
rs.absolute(5);
String name = rs.getString("full_name");
```

Sửa thành:

```java
if (rs.absolute(5)) {
    String name = rs.getString("full_name");
    // Xử lý name tại hàng hợp lệ.
} else {
    // Không có hàng thứ 5.
}
```

Tương tự, `getRow() == 0` là dấu hiệu không có hàng hiện tại, **không phải** hàng thứ 0 của tập kết quả.

## 6. Ví dụ hoàn chỉnh: đọc hàng đầu, cuối, trước cuối và vị trí chỉ định

### 6.1. Dữ liệu SQL minh họa

Giả sử có bảng:

```sql
CREATE TABLE employees (
    id            BIGINT PRIMARY KEY,
    full_name     VARCHAR(150) NOT NULL,
    department_id BIGINT NOT NULL
);

INSERT INTO employees (id, full_name, department_id)
VALUES (101, 'An', 7),
       (105, 'Bình', 7),
       (109, 'Chi', 7),
       (201, 'Dung', 8);
```

Đoạn DDL/DML chỉ minh họa; khả năng chạy nhiều hàng trong một `INSERT` phụ thuộc SQL dialect, nhưng được nhiều hệ quản trị thông dụng hỗ trợ. Truy vấn của ứng dụng:

```sql
SELECT id, full_name
FROM employees
WHERE department_id = ?
ORDER BY id
```

**Tại sao phải có `ORDER BY id`?** Vị trí “đầu”, “cuối” hay “thứ 2” chỉ có ý nghĩa nếu ứng dụng xác định thứ tự. Một câu `SELECT` **không có `ORDER BY` không cam kết thứ tự**, ngay cả khi kết quả có vẻ được trả theo khóa chính. `ORDER BY id` dùng khóa duy nhất để tránh việc nhiều hàng trùng tiêu chí sắp xếp tạo thứ tự không ổn định.

### 6.2. Repository Java 17+ dùng DataSource và PreparedStatement

Ví dụ dưới đây sử dụng một `ResultSet` loại `TYPE_SCROLL_INSENSITIVE` và trả về các DTO độc lập với vòng đời connection:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Objects;
import java.util.Optional;

public final class EmployeeNavigator {
    public record Employee(long id, String fullName) {}

    public record Snapshot(
            Optional<Employee> first,
            Optional<Employee> last,
            Optional<Employee> previousFromLast,
            Optional<Employee> second,
            int secondRowNumber,
            Optional<Employee> secondFromEnd
    ) {}

    private static final String SQL = """
            SELECT id, full_name
            FROM employees
            WHERE department_id = ?
            ORDER BY id
            """;

    private final DataSource dataSource;

    public EmployeeNavigator(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Snapshot inspect(long departmentId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(
                     SQL,
                     ResultSet.TYPE_SCROLL_INSENSITIVE,
                     ResultSet.CONCUR_READ_ONLY)) {

            ps.setLong(1, departmentId);

            try (ResultSet rs = ps.executeQuery()) {
                // Một số driver có thể đổi loại được yêu cầu.
                if (rs.getType() == ResultSet.TYPE_FORWARD_ONLY) {
                    throw new SQLFeatureNotSupportedException(
                            "Driver không cung cấp ResultSet cuộn được");
                }

                Optional<Employee> first = readAt(rs.first(), rs);

                boolean positionedLast = rs.last();
                Optional<Employee> last =
                        readAt(positionedLast, rs);

                // Đi từ hàng cuối đến hàng ngay trước nó.
                Optional<Employee> previousFromLast =
                        positionedLast
                                ? readAt(rs.previous(), rs)
                                : Optional.empty();

                boolean positionedSecond = rs.absolute(2);
                Optional<Employee> second =
                        readAt(positionedSecond, rs);
                int secondRowNumber =
                        positionedSecond ? rs.getRow() : 0;

                // -2 là vị trí áp cuối, tính từ cuối tập.
                Optional<Employee> secondFromEnd =
                        readAt(rs.absolute(-2), rs);

                return new Snapshot(
                        first,
                        last,
                        previousFromLast,
                        second,
                        secondRowNumber,
                        secondFromEnd);
            }
        }
    }

    private static Optional<Employee> readAt(
            boolean positioned, ResultSet rs
    ) throws SQLException {
        if (!positioned) {
            return Optional.empty();
        }

        long id = rs.getLong("id");
        if (rs.wasNull()) {
            throw new SQLException("id không được NULL");
        }
        String name = rs.getString("full_name");
        if (name == null) {
            throw new SQLException("full_name không được NULL");
        }

        return Optional.of(new Employee(id, name));
    }
}
```

Đoạn code trên tuân thủ những điều quan trọng:

1. `DataSource` cấp `Connection`; `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` đúng vòng đời.
2. `PreparedStatement` dùng placeholder `?` cho `department_id`, tránh nối tham số trực tiếp vào SQL.
3. Yêu cầu `TYPE_SCROLL_INSENSITIVE` và `CONCUR_READ_ONLY` trước khi thực thi. Sau khi lấy kết quả, kiểm tra `getType()` để phát hiện trường hợp chỉ có `TYPE_FORWARD_ONLY`.
4. Mỗi thao tác định vị `first()`, `last()`, `previous()`, `absolute()` chỉ được đọc cột nếu trả `true`.
5. `previousFromLast` chỉ thực hiện `previous()` khi `last()` đã thành công; vì thế không đọc sai trạng thái trên tập rỗng.
6. `secondRowNumber` bằng `0` khi không có hàng thứ 2, theo hợp đồng DTO của ví dụ.
7. DTO `Employee` dùng `long` và `String`. `rs.wasNull()` được gọi ngay sau `getLong()` để kiểm tra SQL NULL của khóa, dù schema khai báo khóa là `NOT NULL`.

Ví dụ không giả định có thể giữ `ResultSet` sau khi connection đã đóng: các đối tượng trả về đã được ánh xạ xong khi tài nguyên JDBC còn mở.

### 6.3. Kết quả kỳ vọng

Nếu chạy `inspect(7)` với dữ liệu minh họa, các trường của `Snapshot` là:

| Trường | Kết quả |
|---|---|
| `first` | `Employee(101, "An")` |
| `last` | `Employee(109, "Chi")` |
| `previousFromLast` | `Employee(105, "Bình")` |
| `second` | `Employee(105, "Bình")` |
| `secondRowNumber` | `2` |
| `secondFromEnd` | `Employee(105, "Bình")` |

Với `inspect(8)` (một nhân viên), `first` và `last` đều là nhân viên 201, còn `previousFromLast`, `second`, `secondFromEnd` đều rỗng. Với `inspect(999)` (không có hàng), mọi `Optional<Employee>` đều rỗng và `secondRowNumber = 0`.

**Không coi đây là chỉ dẫn rằng mọi truy vấn cần lưu đủ sáu vị trí:** ví dụ cố ý minh họa sự khác biệt của các thao tác. Trong nghiệp vụ thật, chỉ lấy những hàng cần thiết.

## 7. Quay về đầu, đi tới sau cuối và duyệt ngược

### 7.1. Duyệt từ đầu sau khi đã đọc cuối

Giả sử con trỏ vừa gọi `last()`. Muốn duyệt tuần tự lại:

```java
rs.beforeFirst();

while (rs.next()) {
    System.out.printf(
            "row=%d id=%d%n",
            rs.getRow(),
            rs.getLong("id")
    );
}
```

`beforeFirst()` không trả boolean và **không đứng trên hàng 1**: sau khi gọi, cần `next()` để bước vào hàng đầu. Nếu viết `rs.beforeFirst(); rs.getLong("id")`, code đang đọc cột khi chưa có hàng hiện tại.

### 7.2. Duyệt từ cuối về đầu

```java
rs.afterLast();

while (rs.previous()) {
    System.out.printf(
            "row=%d name=%s%n",
            rs.getRow(),
            rs.getString("full_name")
    );
}
```

`afterLast()` đưa con trỏ ra sau hàng cuối; mỗi lần `previous()` tiến về phía đầu của tập kết quả. Với ba hàng, output theo thứ tự **Chi → Bình → An**. Nếu tập kết quả rỗng, vòng lặp không chạy.

### 7.3. Nhảy một khoảng cố định

Để đọc hàng 1, 3, 5, ... trong một ResultSet cuộn được, có thể dùng:

```java
if (rs.first()) {
    do {
        System.out.println(rs.getLong("id"));
    } while (rs.relative(2));
}
```

Mẫu này giả định `relative(2)` từ một hàng hợp lệ di chuyển thêm 2 vị trí. Tuy nhiên, truy cập kiểu “bỏ qua một số hàng” **không bảo đảm tiết kiệm I/O tương ứng**: driver có thể đã đọc/cached những hàng đó. Nếu thực sự chỉ cần một tập con, hãy lọc bằng SQL thay vì cố tối ưu bằng điều hướng con trỏ.

## 8. Kiểm tra driver hỗ trợ trước khi dùng

### 8.1. Metadata hỗ trợ ResultSet type và concurrency

JDBC có `DatabaseMetaData`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;

static boolean canUseScrollableReadOnly(Connection connection)
        throws SQLException {
    DatabaseMetaData meta = connection.getMetaData();

    return meta.supportsResultSetType(
                    ResultSet.TYPE_SCROLL_INSENSITIVE)
            && meta.supportsResultSetConcurrency(
                    ResultSet.TYPE_SCROLL_INSENSITIVE,
                    ResultSet.CONCUR_READ_ONLY);
}
```

Có thể gọi hàm trước khi tạo `PreparedStatement` để đưa ra phương án dự phòng nếu driver báo không hỗ trợ. Nhưng kết quả từ metadata chỉ là thông tin **driver công bố**; vẫn nên kiểm tra sau khi truy vấn thực thi:

```java
int actualType = rs.getType();
int actualConcurrency = rs.getConcurrency();

if (actualType == ResultSet.TYPE_FORWARD_ONLY) {
    throw new SQLFeatureNotSupportedException(
            "Yêu cầu scrollable nhưng driver trả forward-only");
}
```

Với truy vấn chỉ đọc, có thể kiểm tra thêm `actualConcurrency == ResultSet.CONCUR_READ_ONLY` nếu hợp đồng repository cần nghiêm ngặt. Một số driver có thể không hỗ trợ đúng tổ hợp được yêu cầu, điều chỉnh kiểu ResultSet hoặc ném `SQLFeatureNotSupportedException`/`SQLException`. Lựa chọn hành vi thay thế phải được kiểm thử trên DB và driver thật.

### 8.2. Kiểm tra SQLWarning khi driver thay đổi tùy chọn

`Statement.getWarnings()` hoặc `ResultSet.getWarnings()` có thể cung cấp thêm cảnh báo, nếu driver phát sinh:

```java
SQLWarning warning = ps.getWarnings();
while (warning != null) {
    System.out.printf(
            "SQLWarning state=%s code=%d%n",
            warning.getSQLState(),
            warning.getErrorCode()
    );
    warning = warning.getNextWarning();
}
```

Đoạn này giả định `ps` là `PreparedStatement` còn mở, cần import `java.sql.SQLWarning`. Không nên dựa **duy nhất** vào warning vì không phải driver nào cũng phát ra cảnh báo cho một thao tác hạ cấp tính năng; kiểm tra `rs.getType()` vẫn rõ ràng hơn.

### 8.3. Fallback khi chỉ có TYPE_FORWARD_ONLY

Một số phương án thay thế:

- **Chỉ cần hàng đầu:** viết `ORDER BY ...` và dùng `next()`; không cần scrollable ResultSet.
- **Chỉ cần hàng cuối:** đặt thứ tự SQL ngược lại và lấy hàng đầu, ví dụ `ORDER BY id DESC` rồi `next()`; cần xác định đúng điều kiện sắp xếp nghiệp vụ.
- **Cần một hàng tại vị trí cụ thể:** dùng phân trang trong SQL theo dialect, ví dụ `LIMIT/OFFSET` hoặc `OFFSET ... FETCH`, hoặc truy vấn theo khóa; lưu ý chi phí OFFSET lớn và tính ổn định của thứ tự.
- **Cần duyệt lại tập nhỏ, độc lập với connection:** ánh xạ hàng thành `List<DTO>` rồi truy cập theo index của Java. Chấp nhận chi phí bộ nhớ tỷ lệ với số hàng/độ lớn dữ liệu.
- **Cần xử lý tập rất lớn tuần tự:** giữ `TYPE_FORWARD_ONLY` và xử lý từng hàng thay vì cố cuộn/ngốn bộ nhớ.

Chọn phương án dựa trên **mục tiêu nghiệp vụ và quy mô kết quả**, không mặc định scrollable là lựa chọn “nâng cao nên tốt hơn”.

## 9. Hiệu năng và ảnh hưởng của việc cuộn tới dữ liệu lớn

Một ResultSet cuộn được có thể cần khả năng truy cập lại các hàng trước đó. Tùy JDBC driver và DB, việc này có thể dùng:

- Bộ nhớ trong JVM để cache nhiều hàng.
- Cursor hoặc cấu trúc lưu trữ phía server.
- Tài nguyên transaction/session lâu hơn so với cách đọc một chiều.
- Trao đổi mạng thêm để lấy hàng ở vị trí chưa đọc hoặc để di chuyển con trỏ.
- Tài nguyên cho việc đánh giá vị trí tương đối, đặc biệt với `last()` hoặc `absolute(-1)`.

Không được suy luận mọi driver đều dùng bộ nhớ ở JVM hay mọi `last()` đều phải đọc hết toàn bộ hàng; những chi tiết đó phụ thuộc implementation. Nhưng khi kết quả lớn, **phải đo lường** thay vì chọn scrollable vô điều kiện.

### 9.1. last() không phải cách tốt nhất để đếm hàng

Một mẫu đôi khi được đề xuất:

```java
rs.last();
int total = rs.getRow();
rs.beforeFirst();
```

Với một ResultSet cuộn được, `getRow()` sau `last()` cho vị trí hàng cuối và vì vậy có thể phản ánh số hàng. Tuy nhiên, phép đếm này có thể buộc driver xử lý toàn tập dữ liệu và giữ tài nguyên lớn. Nó không phải giải pháp mặc định cho thống kê hàng triệu bản ghi hoặc pagination.

Nếu cần **đếm số hàng theo điều kiện**, hãy cân nhắc truy vấn `SELECT COUNT(*) FROM ... WHERE ...` phù hợp, với điều kiện và transaction nhất quán theo yêu cầu. Nếu chỉ cần kiểm tra có hàng hay không, `rs.next()` có thể đủ. Nếu cần dữ liệu cuối theo thứ tự, truy vấn `ORDER BY ... DESC` kết hợp giới hạn hàng theo DB thường hiệu quả hơn việc tạo ResultSet lớn rồi gọi `last()`.

### 9.2. setFetchSize không phải lệnh di chuyển con trỏ

`PreparedStatement.setFetchSize(int)` hoặc `ResultSet.setFetchSize(int)` đưa ra **gợi ý** về số hàng nên lấy trong một đợt. Nó không làm cho ResultSet forward-only trở thành scrollable và không biểu thị vị trí con trỏ.

```java
ps.setFetchSize(200); // Gợi ý fetch, không phải absolute(200).
```

Một số DB/driver chỉ kích hoạt server-side cursor hoặc streaming khi có cấu hình transaction/fetch size riêng. Hãy kiểm tra tài liệu driver trước khi suy đoán việc dùng `setFetchSize` giúp giảm RAM hay round-trip.

### 9.3. Không dùng ResultSet cuộn thay cho phân trang API

Nếu endpoint trả danh sách nhân viên theo trang, tạo `ResultSet` gồm mọi nhân viên, gọi `absolute(offset + 1)` rồi lấy 20 hàng có thể lãng phí DB I/O và bộ nhớ. Việc di chuyển con trỏ của một tập kết quả đã mở không tương đương cơ chế phân trang ổn định.

Với API nhiều người dùng, cân nhắc phân trang bằng SQL, ưu tiên thứ tự duy nhất và **keyset pagination** cho các tập lớn khi phù hợp. Nếu dùng `OFFSET`, các thay đổi dữ liệu giữa các request có thể khiến bản ghi xuất hiện trùng hoặc bị bỏ qua, tùy isolation và trật tự sắp xếp.

## 10. Transaction, khả năng thấy thay đổi và holdability

### 10.1. Scroll-sensitive không đồng nghĩa đồng bộ tức thời

`TYPE_SCROLL_SENSITIVE` được thiết kế để có thể phản ánh thay đổi dữ liệu nền trong khi ResultSet vẫn mở. Tuy nhiên, không nên suy rằng:

- Mọi thay đổi từ transaction khác lập tức hiển thị.
- Hàng được chèn mới luôn xuất hiện trong tập đã mở.
- Một lần `absolute(2)` luôn trả đúng cùng bản ghi khi dữ liệu nền bị sửa.
- Cùng một loại ResultSet trên hai driver có cùng ngữ nghĩa quan sát thay đổi.

Isolation level, cursor DB, transaction và tài liệu driver quyết định cụ thể thay đổi nào nhìn thấy được. Nếu nghiệp vụ yêu cầu **snapshot nhất quán**, hãy dùng ranh giới transaction/isolation phù hợp và kiểm thử với các giao dịch đồng thời; chỉ chọn loại ResultSet là chưa đủ.

### 10.2. Commit có thể ảnh hưởng tới ResultSet đang mở

JDBC có hai dạng holdability phổ biến:

- `ResultSet.HOLD_CURSORS_OVER_COMMIT`: giữ con trỏ khi commit nếu DB/driver hỗ trợ.
- `ResultSet.CLOSE_CURSORS_AT_COMMIT`: đóng các cursor tương ứng khi commit.

Có thể hỏi `connection.getHoldability()`, `rs.getHoldability()` và `connection.getMetaData().supportsResultSetHoldability(...)`; một số overload `prepareStatement(...)` còn nhận tham số holdability.

Dù chọn kiểu cuộn được, ResultSet có thể không còn sử dụng được sau `commit()` tùy holdability, driver và DB. Vì vậy, đừng thực hiện commit ở giữa vòng điều hướng rồi cho rằng `previous()` chắc chắn tiếp tục hoạt động.

Để giữ code dễ bảo trì, thường nên hoàn tất việc đọc/ánh xạ dữ liệu khi ResultSet còn mở, rồi mới kết thúc transaction tại tầng sở hữu `Connection`.

### 10.3. Không chia sẻ một ResultSet đang cuộn giữa nhiều thread

`ResultSet` chứa trạng thái con trỏ có thể thay đổi. Nếu hai thread gọi `next()` và `absolute(1)` trên cùng đối tượng, chúng có thể phá vỡ giả định về hàng hiện tại của nhau. Không nên chia sẻ `ResultSet` hoặc `Connection` như một tài nguyên dùng chung tự do giữa các tác vụ song song. Cần giữ quyền sở hữu và vòng đời rõ ràng.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Gọi `previous()` trên ResultSet forward-only | Có thể nhận `SQLException` do không hỗ trợ | Yêu cầu kiểu scrollable và kiểm tra metadata/getType |
| Gọi `getString()` sau `absolute(999) == false` | Không có hàng hiện tại | Chỉ đọc khi thao tác định vị trả `true` |
| Nhầm `absolute(0)` là hàng đầu | Con trỏ bị đưa về before-first | Dùng `absolute(1)` hoặc `first()` |
| Nhầm `absolute(-1)` với “lùi một hàng” | Nhảy đến hàng cuối, không phải hàng ngay trước | Dùng `previous()` hoặc `relative(-1)` |
| Dùng `getRow()` như chỉ số mảng 0-based | Sai vị trí một đơn vị | JDBC bắt đầu từ 1; index Java `List` bắt đầu từ 0 |
| Không dùng `ORDER BY` | “Hàng đầu/cuối” có thể thay đổi giữa các lần chạy | Chọn thứ tự SQL ổn định, thêm khóa phân giải hòa |
| Đọc `isBeforeFirst() == false` như có dữ liệu | Kết quả rỗng cũng có thể trả false | Kiểm tra `first()` hoặc `next()` |
| Dùng `last()` để đếm hàng lớn | Có thể tải/cache nhiều hàng, tăng latency | Cân nhắc `COUNT(*)` theo nhu cầu |
| Nhầm scrollable với updatable | Chọn sai concurrency hoặc thất bại do giới hạn driver | Dùng `CONCUR_READ_ONLY` nếu chỉ cần đọc |
| Driver hạ cấp kiểu được yêu cầu | Code dùng lệnh cuộn trên forward-only | Kiểm tra `rs.getType()`, chuẩn bị fallback |
| Trả `ResultSet` sau khi đóng connection | Lỗi tài nguyên đã đóng | Ánh xạ DTO khi trong scope `try-with-resources` |
| Commit khi còn dùng con trỏ | Cursor có thể bị đóng | Xem holdability và tổ chức transaction |
| Nhiều thread cùng di chuyển con trỏ | Hàng hiện tại bị thay đổi ngoài dự kiến | Giữ ResultSet trong một luồng xử lý đồng bộ |

Khi bắt lỗi JDBC, nên giữ `SQLException.getSQLState()`, `getErrorCode()` và nguyên nhân cho hệ thống quan sát, nhưng không log password hoặc tham số nhạy cảm. Nếu driver không hỗ trợ tính năng, cần có phương án thay thế; không bắt mọi `SQLException` rồi tự phát lại câu truy vấn ghi dữ liệu.

## 12. Kiểm thử tích hợp điều hướng

Hãy kiểm thử với **cơ sở dữ liệu và JDBC driver thật** gần môi trường triển khai; mock ResultSet có thể kiểm tra logic điều hướng cơ bản nhưng không xác nhận khả năng hỗ trợ loại cursor, downgrade hay holdability của driver.

### 12.1. Ma trận kiểm thử

| Kịch bản | Thao tác | Kỳ vọng |
|---|---|---|
| 3 hàng đã sắp xếp | `first()` | Hàng 1, `getRow() == 1` |
| 3 hàng đã sắp xếp | `last()` | Hàng 3, `getRow() == 3` |
| Từ hàng cuối | `previous()` | Hàng 2, trả `true` |
| Từ hàng 3 | `relative(-2)` | Hàng 1, trả `true` |
| Từ vị trí bất kỳ | `absolute(2)` | Hàng 2, trả `true` |
| 3 hàng | `absolute(-1)` | Hàng cuối |
| 3 hàng | `absolute(-2)` | Hàng áp cuối |
| 3 hàng | `absolute(0)` | Trả `false`, con trỏ before-first |
| 3 hàng | `absolute(4)` | Trả `false`, con trỏ after-last |
| 3 hàng | `absolute(-4)` | Trả `false`, con trỏ before-first |
| Từ after-last | `previous()` | Đến hàng cuối nếu tập không rỗng |
| Từ before-first | `next()` | Đến hàng đầu nếu tập không rỗng |
| Tập rỗng | `first()` và `last()` | Đều `false`; không đọc getter |
| Một hàng | `isFirst()` và `isLast()` | Đều `true` khi đứng trên hàng duy nhất |
| Một hàng | `absolute(-2)` | Trả `false` |
| Driver chỉ forward-only | `previous()` hoặc `absolute()` | Không có bảo đảm hỗ trợ; nhận lỗi hoặc dùng fallback |
| Thay đổi dữ liệu đồng thời | Scroll-insensitive/sensitive | Ghi nhận ngữ nghĩa thực tế dưới isolation đã chọn |
| Commit khi cursor mở | Theo holdability cấu hình | Kiểm tra cursor còn mở hoặc bị đóng đúng hợp đồng DB |

### 12.2. Bài tập tự thực hành

1. Tạo bảng `employees` và bốn bản ghi như mục 6.
2. Viết `EmployeeNavigator.inspect(7)` với `TYPE_SCROLL_INSENSITIVE`, đối chiếu đầy đủ `Snapshot`.
3. Thử thay `TYPE_SCROLL_INSENSITIVE` bằng `TYPE_FORWARD_ONLY` nhưng giữ nguyên `first()/last()/absolute()`. Quan sát exception hoặc giới hạn thực tế của driver; không mặc định một loại exception duy nhất.
4. Thêm chức năng lấy nhân viên ở vị trí `n`, trả `Optional<Employee>` khi không tồn tại và từ chối `n == 0` nếu nghiệp vụ đánh số từ 1.
5. Dùng `beforeFirst()`/`next()` để duyệt xuôi rồi `afterLast()`/`previous()` để duyệt ngược, kiểm tra thứ tự ID.
6. Thử với kết quả **0 hàng** và **1 hàng**, xác nhận không đọc cột khi thao tác định vị trả `false`.
7. Bỏ `ORDER BY`, chạy truy vấn nhiều lần; giải thích vì sao thứ tự không được DB bảo đảm ngay cả khi kết quả thử nghiệm trông không đổi.
8. Đo thời gian và bộ nhớ khi gọi `last()` trên 100, 10.000 và nhiều hơn 100.000 hàng, so sánh với truy vấn lấy hàng cuối theo SQL trong cùng môi trường.

## 13. Ghi nhớ

- **`TYPE_FORWARD_ONLY` chủ yếu dùng `next()`; muốn `first()`, `last()`, `previous()` và `absolute()`, hãy yêu cầu ResultSet scrollable** và kiểm tra mức hỗ trợ của driver.
- **Chỉ số hàng JDBC bắt đầu từ 1.** `absolute(1)` là hàng đầu; `absolute(0)` là before-first; `absolute(-1)` là hàng cuối.
- **`previous()` và `relative(-1)` lùi tương đối; `absolute(-1)` nhảy thẳng đến cuối.**
- **Luôn kiểm tra boolean trả về** trước khi đọc giá trị cột; ngoài vùng hàng hợp lệ không có current row.
- **`ORDER BY` là điều kiện để “đầu/cuối/vị trí thứ n” có nghĩa nhất quán**, nên dùng tiêu chí duy nhất khi cần thứ tự xác định hoàn toàn.
- **Scrollable không đồng nghĩa rẻ hơn**: có thể tốn bộ nhớ, cursor server hoặc thêm I/O; với dữ liệu lớn, cân nhắc SQL phân trang, query hàng đầu/cuối hoặc xử lý forward-only.
- **Kiểu cursor, visibility, holdability và transaction phụ thuộc DB/driver**, cần kiểm thử và quản lý vòng đời `ResultSet`, `PreparedStatement` và `Connection` theo đúng phạm vi.
