# Kiểm tra trường hợp mong đợi không quá một bản ghi

Trong **JDBC (Java Database Connectivity)**, `ResultSet` cho phép chương trình Java duyệt các hàng mà câu lệnh SQL trả về từ cơ sở dữ liệu quan hệ. Với truy vấn danh sách, ứng dụng thường lặp `while (rs.next())`. Nhưng với truy vấn tìm **một khách hàng theo khóa**, **một cấu hình theo tên**, hoặc **một bản ghi theo cặp khóa nghiệp vụ**, yêu cầu có thể là **không quá một hàng**.

“Không quá một hàng” có nghĩa là chấp nhận **0 hoặc 1 hàng** và xem **từ 2 hàng trở lên là vi phạm giả định**. Đây là quy tắc về *số lượng kết quả* (cardinality), không phải quy tắc tự động chọn hàng đầu tiên. Chỉ gọi `rs.next()` một lần rồi trả dữ liệu có thể vô tình che giấu lỗi dữ liệu trùng, lỗi `JOIN` hoặc truy vấn thiếu điều kiện.

Bài thuộc chương **Đọc ResultSet** này giải thích cách kiểm tra chính xác cả ba trạng thái `0 / 1 / >1`, trình bày mã JDBC hoàn chỉnh, phân biệt kỳ vọng “tối đa một” với “đúng một”, và nêu những giới hạn của việc kiểm tra ở tầng ứng dụng.

## 1. Định nghĩa rõ hợp đồng kết quả

Ví dụ cần tìm khách hàng bằng cặp `(tenant_id, email)`. Theo thiết kế, có thể chưa có khách hàng tương ứng, hoặc có một khách hàng. Nếu có nhiều hàng cùng khớp, ứng dụng cần phát hiện một bất thường.

| Số hàng SQL trả về | “Không quá một bản ghi” | “Phải đúng một bản ghi” | Cách ứng dụng xử lý |
| --- | --- | --- | --- |
| **0** | Hợp lệ | Không hợp lệ | Trả `Optional.empty()`/`null` theo hợp đồng hoặc báo không tìm thấy |
| **1** | Hợp lệ | Hợp lệ | Đọc và trả về bản ghi |
| **2 trở lên** | Không hợp lệ | Không hợp lệ | Báo lỗi vi phạm tính duy nhất; không âm thầm lấy hàng đầu |

Trong ứng dụng Java hiện đại, `Optional<T>` thường diễn đạt tốt hợp đồng **0 hoặc 1 đối tượng**. Nếu nghiệp vụ yêu cầu **đúng một** đối tượng, dùng kiểu `T` và báo lỗi cho cả trường hợp không có hàng lẫn trường hợp nhiều hàng. Hai hợp đồng này cần được đặt tên và xử lý riêng.

**Điểm cần phân biệt:** một hàng có cột SQL `NULL` vẫn là **một hàng**. `ResultSet.next()` xác định sự tồn tại của hàng; `getString(...) == null` hay `getObject(...) == null` chỉ nói về giá trị của **một cột**, không xác định số hàng.

## 2. `ResultSet.next()` hoạt động như thế nào?

Với `ResultSet` dạng **forward-only** thông thường, con trỏ ban đầu nằm **trước hàng đầu tiên**:

~~~text
Trạng thái ban đầu:
  [trước hàng 1] -> [hàng 1] -> [hàng 2] -> ... -> [sau hàng cuối]

Lần next() thứ nhất:
  true  -> chuyển tới hàng 1
  false -> tập kết quả rỗng, không có hàng 1

Lần next() thứ hai (chỉ khi lần đầu là true):
  true  -> tồn tại hàng 2; kết quả vi phạm kỳ vọng "không quá một"
  false -> hàng 1 là hàng duy nhất trong tập kết quả đang duyệt
~~~

Vì vậy, chỉ cần **tối đa hai lần gọi `next()`** để kiểm tra kỳ vọng, không cần đếm hết toàn bộ số hàng.

~~~mermaid
flowchart TD
    A["Thực thi truy vấn, nhận ResultSet"] --> B{"rs.next() lần 1?"}
    B -->|"false"| C["0 hàng: Optional.empty()"]
    B -->|"true"| D["Đọc / ánh xạ hàng đầu tiên"]
    D --> E{"rs.next() lần 2?"}
    E -->|"false"| F["1 hàng: trả đối tượng"]
    E -->|"true"| G["Có ít nhất 2 hàng: báo vi phạm kỳ vọng"]
~~~

Hãy chú ý rằng lần gọi `next()` thứ hai **di chuyển con trỏ**. Nếu cần ánh xạ hàng đầu tiên, phải làm việc đó **trước** khi gọi `next()` lần hai, hoặc thiết kế cách lưu dữ liệu phù hợp. Không thể mặc định quay lại hàng đầu trên mọi `ResultSet`.

## 3. Ví dụ Java hoàn chỉnh: đọc 0 hoặc 1 khách hàng

Giả sử bảng `customer` có các cột `id`, `tenant_id`, `full_name` và `email`. Hàm sau nhận kết nối do bên gọi quản lý, mã tenant **đã được xác thực** và email cần tra cứu.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

public final class CustomerLookup {
    private CustomerLookup() {}

    // Record yêu cầu Java 16 trở lên.
    public record Customer(long id, String fullName, String email) {}

    public static Optional<Customer> findAtMostOne(
            Connection connection,
            long authenticatedTenantId,
            String email
    ) throws SQLException {
        Objects.requireNonNull(connection, "connection");
        Objects.requireNonNull(email, "email");

        String sql = """
                SELECT id, full_name, email
                FROM customer
                WHERE tenant_id = ? AND email = ?
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, authenticatedTenantId);
            ps.setString(2, email);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty(); // 0 hàng.
                }

                // Ánh xạ khi con trỏ còn ở hàng đầu tiên.
                Customer customer = new Customer(
                        rs.getLong("id"),
                        rs.getString("full_name"),
                        rs.getString("email")
                );

                if (rs.next()) {
                    // Có ít nhất hai hàng. Không trả hàng đầu để che lỗi.
                    throw new IllegalStateException(
                            "Truy vấn trả nhiều hơn một khách hàng");
                }

                return Optional.of(customer); // Chính xác 1 hàng.
            }
        }
    }
}
~~~

Code minh họa Java 17 (hỗ trợ `record` và text block). Với Java cũ hơn, thay `record` bằng POJO, text block bằng chuỗi thông thường; **logic `rs.next()` hai lần không thay đổi**.

Lý do thiết kế:

1. `PreparedStatement` gắn `tenant_id` và `email` bằng tham số, tránh đưa giá trị đầu vào vào cú pháp SQL.
2. `rs.next()` đầu tiên kiểm tra có hàng hay không. Kết quả `false` dẫn đến `Optional.empty()`.
3. Khi có hàng đầu, ứng dụng ánh xạ đúng các cột cần thiết trước khi di chuyển con trỏ.
4. `rs.next()` thứ hai kiểm tra **sự tồn tại của hàng tiếp theo**. Nếu có, báo lỗi vi phạm kỳ vọng.
5. Chỉ khi lần `next()` thứ hai trả `false` mới trả `Optional.of(customer)`.
6. `try-with-resources` đóng `ResultSet` và `PreparedStatement` cả khi `return` hoặc ném ngoại lệ.

Hàm **không tự đóng `Connection`**, vì quyền sở hữu connection thuộc về mã gọi. Nếu connection lấy từ pool, bên gọi phải đóng/trả pool ở ranh giới nghiệp vụ phù hợp.

`authenticatedTenantId` phải lấy từ ngữ cảnh xác thực/ủy quyền đáng tin cậy. Việc dùng `PreparedStatement` ngăn SQL injection ở giá trị, nhưng không thay thế kiểm tra quyền truy cập.

## 4. Vì sao `if (rs.next())` một lần là chưa đủ?

Đoạn mã sau thường xuất hiện trong các ví dụ nhập môn:

~~~java
try (ResultSet rs = ps.executeQuery()) {
    if (rs.next()) {
        return new Customer(
                rs.getLong("id"),
                rs.getString("full_name"),
                rs.getString("email"));
    }
    return null;
}
~~~

Nó trả một kết quả nếu có hàng đầu, nhưng **không xác minh hàng thứ hai có tồn tại hay không**. Nếu SQL trả năm khách hàng, hàm vẫn lặng lẽ trả khách hàng đầu tiên. Trường hợp này chỉ phù hợp khi hợp đồng là **“lấy một hàng bất kỳ/đã xác định theo thứ tự”** hoặc tính duy nhất đã được đảm bảo bởi thiết kế khác và ta không cần kiểm tra vi phạm tại đây.

Với hợp đồng “không quá một”, cần thêm:

~~~java
if (!rs.next()) {
    return Optional.empty();
}

Customer first = mapCustomer(rs);
if (rs.next()) {
    throw new IllegalStateException("Có nhiều hơn một bản ghi");
}
return Optional.of(first);
~~~

Trong đoạn rút gọn này, `mapCustomer(rs)` là hàm giả định ánh xạ hàng hiện tại; ví dụ hoàn chỉnh ở phần trước đã viết trực tiếp việc ánh xạ. Không nên xem ví dụ rút gọn là một phương thức tự biên dịch độc lập.

### Tránh dùng `ResultSet.getRow()` để đếm kết quả

`rs.getRow()` trả chỉ số **hàng hiện tại** (theo hợp đồng JDBC), không phải tổng số hàng có trong tập kết quả. Khi con trỏ đang ở hàng đầu tiên, `getRow() == 1` vẫn **không chứng minh** chỉ có một hàng.

`rs.isLast()` hoặc chuyển `rs.last()` rồi đọc số thứ tự hàng cũng không phải lựa chọn mặc định: một số thao tác phụ thuộc loại result set/khả năng driver, có thể cần buffering hoặc di chuyển con trỏ phức tạp. **Hai lần `next()`** làm việc với kiểu `TYPE_FORWARD_ONLY` thông dụng và đủ để phát hiện từ hai hàng trở lên.

## 5. “Không quá một” khác “chính xác một”

Hai yêu cầu gần giống nhưng hành vi trường hợp 0 hàng khác nhau:

**Không quá một hàng:** người dùng có thể chưa tồn tại. Kết quả 0 hàng là bình thường.

~~~java
Optional<CustomerLookup.Customer> maybeCustomer =
        CustomerLookup.findAtMostOne(connection, tenantId, email);

if (maybeCustomer.isPresent()) {
    System.out.println(maybeCustomer.get().fullName());
} else {
    System.out.println("Chưa có khách hàng tương ứng");
}
~~~

**Chính xác một hàng:** nghiệp vụ biết chắc một cấu hình đã được khởi tạo hoặc một bản ghi khóa chính bắt buộc phải có. Không tìm thấy là lỗi kỳ vọng:

~~~java
CustomerLookup.Customer customer =
        CustomerLookup.findAtMostOne(connection, tenantId, email)
                .orElseThrow(() ->
                        new java.util.NoSuchElementException(
                                "Không tìm thấy khách hàng bắt buộc"));
~~~

Hàm `findAtMostOne` vẫn phát hiện lỗi nhiều hàng, còn `orElseThrow` xử lý 0 hàng. Trong API thực tế, có thể dùng hai phương thức đặt tên khác nhau như `findOptional(...)` và `getRequired(...)` để người gọi hiểu ngay hợp đồng.

Không nên trả `new Customer(0, "", "")` để biểu thị “không có hàng”: ID 0 hay chuỗi rỗng có thể là dữ liệu hợp lệ hoặc tạo nhầm lẫn với bản ghi thật.

## 6. Khi nào nên dùng `LIMIT 2` hoặc `FETCH FIRST 2 ROWS ONLY`?

Vòng lặp `next()` hai lần **không cần** đọc mọi hàng trong Java. Tuy vậy, driver/DBMS có thể đã bắt đầu tạo hoặc truyền nhiều dữ liệu cho một câu SQL trả hàng lớn. Nếu hệ quản trị hỗ trợ, giới hạn kết quả ở **tối đa hai hàng** có thể giảm lượng công việc cần truyền/đọc và vẫn đủ xác định vi phạm kỳ vọng.

Ví dụ với PostgreSQL/MySQL/SQLite và các DBMS có cú pháp tương ứng:

~~~sql
SELECT id, full_name, email
FROM customer
WHERE tenant_id = ? AND email = ?
LIMIT 2;
~~~

Ví dụ cú pháp tiêu chuẩn SQL được hỗ trợ bởi một số DBMS:

~~~sql
SELECT id, full_name, email
FROM customer
WHERE tenant_id = ? AND email = ?
FETCH FIRST 2 ROWS ONLY;
~~~

Khả năng hỗ trợ, vị trí cú pháp và chi tiết thực thi phụ thuộc DBMS/phiên bản. Một lựa chọn theo JDBC là `Statement.setMaxRows(2)` để giới hạn số hàng trong `ResultSet` mà statement tạo ra, nhưng vẫn cần kiểm chứng hiệu quả thực tế với driver:

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setMaxRows(2);
    ps.setLong(1, authenticatedTenantId);
    ps.setString(2, email);
    try (ResultSet rs = ps.executeQuery()) {
        // Dùng rs.next() hai lần như ví dụ hoàn chỉnh.
    }
}
~~~

**Tuyệt đối không đặt giới hạn bằng 1 khi nhiệm vụ là phát hiện bản ghi trùng**:

~~~sql
-- Sai cho mục tiêu KIỂM TRA tính duy nhất:
SELECT id, full_name
FROM customer
WHERE tenant_id = ? AND email = ?
LIMIT 1;
~~~

Nếu DB thực tế có 10 hàng trùng, `LIMIT 1` chỉ cho chương trình thấy một hàng; lần `rs.next()` thứ hai sẽ trả `false` dù dữ liệu bên dưới vi phạm kỳ vọng. **Giới hạn hai hàng** là đủ để phát hiện trường hợp `>1`; giới hạn một hàng che khuất nó.

Với mục tiêu **chọn hàng ưu tiên trong nhiều hàng**, `ORDER BY ... LIMIT 1` có thể hoàn toàn hợp lý, nhưng đó là một hợp đồng khác: “lấy hàng đứng đầu theo thứ tự đã định”, không phải “xác minh tập kết quả tối đa một hàng”.

## 7. Kiểm tra bằng Java không thay thế ràng buộc UNIQUE trong cơ sở dữ liệu

Giả sử cặp `(tenant_id, email)` phải là duy nhất. Vòng lặp `rs.next()` hai lần phát hiện trùng **khi đọc**, nhưng không ngăn một thao tác khác chèn bản ghi trùng vào DB.

Nếu tính duy nhất là **bất biến nghiệp vụ**, nên đặt ràng buộc ở cơ sở dữ liệu:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_tenant_email
UNIQUE (tenant_id, email);
~~~

Cú pháp trên là SQL minh họa phổ biến; cần kiểm tra hệ quản trị và cấu trúc schema. Giả sử hai cột `tenant_id`, `email` đều `NOT NULL`, ràng buộc đảm bảo không có hai hàng cùng cặp giá trị theo quy tắc so sánh/index của DB.

| Lớp kiểm soát | Làm được gì? | Không giải quyết được gì một mình? |
| --- | --- | --- |
| **`rs.next()` hai lần** | Phát hiện truy vấn hiện tại trả ít nhất 2 hàng | Không ngăn dữ liệu trùng được ghi vào DB |
| **`UNIQUE` constraint/index** | Ngăn các bản ghi trùng theo khóa được DB định nghĩa, kể cả khi ghi đồng thời | Không đảm bảo truy vấn `JOIN` hay phép chiếu tùy ý chỉ trả một hàng |
| **Kiểm tra nghiệp vụ trước khi `INSERT`** | Cho thông báo thuận tiện hoặc kiểm tra chính sách | Có thể bị race condition giữa kiểm tra và ghi |
| **Transaction** | Nhóm thao tác và điều khiển mức cô lập | Chỉ bắt đầu transaction không tự đảm bảo tính duy nhất |

Khi cột được phép chứa `NULL`, cách ràng buộc `UNIQUE` xử lý nhiều giá trị null có thể khác nhau giữa DBMS và cấu hình. Nếu mục tiêu là duy nhất theo email, cần xác định chính sách null/case/collation/chuẩn hóa email cho phù hợp.

### Race condition: hai request cùng thấy “chưa có”

~~~text
Request A: SELECT theo email -> 0 hàng
Request B: SELECT theo email -> 0 hàng
Request A: INSERT customer (...)
Request B: INSERT customer (...)
~~~

Hai truy vấn đọc ban đầu đều đúng tại thời điểm của chúng, nhưng nếu không có ràng buộc đủ mạnh, hai lệnh `INSERT` có thể gây dữ liệu trùng. Ràng buộc `UNIQUE` ở DB giúp bảo vệ bất biến trong trường hợp cạnh tranh; một request có thể nhận lỗi constraint và phải xử lý theo quy tắc nghiệp vụ.

Thậm chí `SELECT ... FOR UPDATE` đối với một hàng **chưa tồn tại** không phải cơ chế đảm bảo tính duy nhất có thể mang qua mọi DBMS/isolation. Không dựa vào việc “đã kiểm tra trước” để thay thế constraint.

## 8. Một `JOIN` có thể làm tăng số hàng dù thực thể là duy nhất

Giả sử bảng `customer` có duy nhất một khách hàng với `id = 42`, nhưng khách hàng đó có ba đơn hàng:

~~~sql
SELECT c.id, c.full_name, o.id AS order_id
FROM customer AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = ?;
~~~

Kết quả có thể gồm:

| `c.id` | `full_name` | `order_id` |
| --- | --- | --- |
| 42 | Mai | 701 |
| 42 | Mai | 702 |
| 42 | Mai | 703 |

Nếu hàm kỳ vọng **không quá một hàng** và dùng `rs.next()` hai lần, nó sẽ báo lỗi — đúng theo hợp đồng *số hàng của truy vấn*, nhưng chưa chắc vi phạm bất biến *một khách hàng*. Vấn đề là `JOIN` một-nhiều đã nhân bản hàng khách hàng.

Khi chỉ cần kiểm tra khách hàng **có đơn hàng hay không**, có thể dùng `EXISTS`:

~~~sql
SELECT c.id, c.full_name
FROM customer AS c
WHERE c.id = ?
  AND EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = c.id
  );
~~~

Truy vấn này không tạo thêm một hàng kết quả cho mỗi đơn hàng. Nếu cần cả danh sách đơn hàng, có thể lấy thực thể khách hàng trước rồi truy vấn danh sách đơn hàng riêng, hoặc thiết kế bộ ánh xạ one-to-many đúng cách; **đừng bắt một API “một hàng” xử lý một truy vấn trả nhiều hàng quan hệ rồi gọi đó là dữ liệu trùng**.

### Dùng `DISTINCT` có thể làm mất tín hiệu cần phát hiện

~~~sql
SELECT DISTINCT c.id, c.full_name
FROM customer AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = ?;
~~~

`DISTINCT` có thể gom nhiều hàng cùng giá trị cột được chọn thành một hàng. Điều đó đôi khi phù hợp khi nghiệp vụ chỉ cần một khách hàng; nhưng cũng có thể **che dữ liệu trùng** nếu bạn đang cố kiểm tra khóa logic không được DB đảm bảo. Hãy xác định mục tiêu là **duy nhất về hàng kết quả**, **duy nhất về thực thể** hay **duy nhất về khóa nghiệp vụ** trước khi thay truy vấn.

## 9. Dữ liệu `NULL` không phải là “không tìm thấy”

Ví dụ một hàng người dùng có `nickname = NULL`:

~~~sql
SELECT id, nickname
FROM app_user
WHERE id = ?;
~~~

Khi truy vấn trả đúng một hàng, `rs.next()` đầu tiên trả `true` dù `rs.getString("nickname")` là `null`.

~~~java
if (!rs.next()) {
    // Không có hàng.
    return Optional.empty();
}

long id = rs.getLong("id");
String nickname = rs.getString("nickname"); // Có thể null.

if (rs.next()) {
    throw new IllegalStateException("Nhiều hàng");
}
// Có một hàng, bất kể nickname null hay không.
~~~

Với `getInt`/`getLong` khi cột SQL có thể null, các phương thức trả kiểu nguyên thủy có thể trả `0`. Gọi `rs.wasNull()` ngay sau lần đọc đó nếu cần phân biệt `NULL` với giá trị số 0, hoặc chọn cách ánh xạ nullable phù hợp.

Đừng dùng `getString("nickname") != null` như một điều kiện xác định hàng tồn tại. Chỉ `next()` mới trả lời liệu có hàng hiện tại hay không.

## 10. Có nên chạy `SELECT COUNT(*)` trước?

Một cách khác là đếm:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE tenant_id = ? AND email = ?;
~~~

Sau đó nếu count bằng 1 thì chạy `SELECT` lần nữa để lấy nội dung. Cách này thường **không cần thiết** cho yêu cầu “trả 0/1 đối tượng và phát hiện trùng”:

- Cần thêm một lần thực thi SQL để lấy dữ liệu thật.
- `COUNT(*)` có thể phải xét nhiều hàng hơn việc chỉ lấy hai hàng, tùy kế hoạch truy vấn.
- Giữa câu đếm và câu lấy dữ liệu, một transaction khác có thể thay đổi số hàng nếu isolation không giữ hai truy vấn trên một snapshot thích hợp.
- Đếm bằng 1 trước đó **không đảm bảo** câu truy vấn sau vẫn có đúng một hàng.

Nếu nghiệp vụ thực sự cần **số lượng chính xác** để làm thống kê hoặc phân trang, `COUNT(*)` là công cụ đúng. Nếu chỉ muốn nhận biết **0, 1, hay từ 2 trở lên**, lấy tối đa hai hàng rồi gọi `next()` hai lần thường gọn hơn.

Trường hợp cần kiểm tra tính duy nhất **trong toàn DB**, ngoài ứng dụng phải dùng ràng buộc dữ liệu và kế hoạch kiểm tra phù hợp. Một truy vấn hạn chế hai hàng chỉ cho biết **tập kết quả theo điều kiện và thời điểm thực thi** có ít nhất hai hàng hay không.

## 11. Xử lý lỗi “nhiều hơn một bản ghi” ở tầng ứng dụng

Khi lần `next()` thứ hai trả `true`, ứng dụng có thể ném một ngoại lệ riêng:

~~~java
public final class NonUniqueResultException
        extends IllegalStateException {
    public NonUniqueResultException(String message) {
        super(message);
    }
}
~~~

Khi đó thay `IllegalStateException` trong ví dụ trước bằng `NonUniqueResultException` để tầng service có thể phân loại rõ lỗi.

Tùy nghiệp vụ, có thể phân biệt:

- **Không tìm thấy (0):** bình thường với tìm kiếm tùy chọn; trả `Optional.empty()` hoặc HTTP 404 ở API đọc theo ID, theo hợp đồng.
- **Một bản ghi (1):** trả dữ liệu.
- **Nhiều bản ghi (>=2):** lỗi chất lượng dữ liệu hoặc lỗi truy vấn; cần ghi nhận để điều tra và sửa bất biến/query. Không tự chọn ngẫu nhiên một hàng để trả như thành công.

Thông điệp ghi log nên cung cấp **tên truy vấn/chức năng**, loại lỗi và định danh tương quan khi cần, đồng thời tránh in toàn bộ dữ liệu cá nhân như email hoặc hồ sơ. Trường hợp vi phạm kỳ vọng không nhất thiết là lỗi do người dùng và không nên tiết lộ schema nội bộ ra phản hồi API.

**Không gọi ngoại lệ nhiều hàng là `SQLException` bắt buộc:** lỗi vi phạm kỳ vọng có thể do logic ứng dụng phát hiện sau khi JDBC đã trả dữ liệu thành công. Việc chọn exception checked hay unchecked phụ thuộc quy ước dự án. Nếu DB thực sự từ chối một `UNIQUE` constraint, lỗi đó thường đến qua `SQLException` hoặc exception đã được framework ánh xạ.

## 12. Kiểm thử đủ các trường hợp biên

Một bộ kiểm thử tích hợp có ích cần dùng bảng dữ liệu thử nghiệm có thể kiểm soát, giao dịch/cleanup được quản lý và truy vấn đúng như sản phẩm.

| Dữ liệu ứng với điều kiện | Kết quả mong đợi | Lỗi mã thường phát hiện |
| --- | --- | --- |
| **0 hàng** | `Optional.empty()` | Gọi `getXxx` trước `next()`, ném lỗi không cần thiết |
| **1 hàng** | `Optional.of(record)` | Gọi `next()` thêm mà quên lưu dữ liệu hàng đầu |
| **2 hàng** | Báo vi phạm tính duy nhất | Trả hàng đầu hoặc dùng `LIMIT 1` |
| **3+ hàng** | Báo vi phạm giống 2 hàng | Đếm toàn bộ không cần thiết |
| **1 hàng nhưng có cột NULL** | Vẫn xem là 1 hàng | Nhầm null với “không tồn tại” |
| **JOIN một-nhiều** | Xác định đúng số hàng theo SQL | Nhầm số hàng với số thực thể duy nhất |
| **Hai thao tác ghi đồng thời** | DB vẫn bảo vệ khóa duy nhất | Chỉ dựa vào `SELECT` kiểm tra trước khi `INSERT` |
| **Truy vấn có `LIMIT 2`** | Phát hiện hàng thứ hai | Thiếu `next()` lần hai |
| **Truy vấn có `LIMIT 1`** | Không đủ thông tin để kiểm tra | Báo sai là dữ liệu duy nhất |

### Kiểm tra dòng chảy với dữ liệu giả định

~~~text
Kịch bản A: 0 hàng
  rs.next() lần 1 = false
  -> Optional.empty()

Kịch bản B: 1 hàng
  rs.next() lần 1 = true
  ánh xạ hàng 1
  rs.next() lần 2 = false
  -> Optional.of(hàng 1)

Kịch bản C: ít nhất 2 hàng
  rs.next() lần 1 = true
  ánh xạ hàng 1
  rs.next() lần 2 = true
  -> báo lỗi; không trả hàng 1
~~~

Nếu bài kiểm thử tạo dữ liệu trùng trên cột đã có `UNIQUE`, DB có thể từ chối dữ liệu thử trước khi bạn kịp chạy truy vấn. Để thử nhánh “nhiều hàng”, có thể dùng một truy vấn trên bảng test không đặt ràng buộc đó, hoặc một truy vấn `JOIN` chủ đích trả nhiều hàng. Không tháo bỏ ràng buộc bảo vệ dữ liệu sản phẩm chỉ để chạy bài thử.

## 13. Những lỗi cần tránh khi triển khai thật

| Cách viết / giả định | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `if (rs.next()) return ...` mà không kiểm tra thêm | Che giấu nhiều hàng trùng | Gọi `rs.next()` lần hai |
| `SELECT ... LIMIT 1` để kiểm tra duy nhất | DB chỉ trả tối đa 1 dù có nhiều hàng thực tế | Dùng tối đa 2 hàng hoặc không giới hạn |
| Dùng `getRow()` để suy ra tổng số hàng | Chỉ biết vị trí con trỏ | Dùng `next()` để phát hiện hàng thứ hai |
| Gọi `rs.next()` lần hai trước khi đọc hàng đầu | Mất vị trí hàng đầu trên result set forward-only | Ánh xạ hàng đầu rồi mới kiểm tra tiếp |
| Dùng `COUNT(*)` rồi `SELECT` và coi kết quả bất biến | Có thể khác nhau khi dữ liệu thay đổi đồng thời | Kiểm tra trực tiếp trên một ResultSet; dùng constraint |
| Dùng truy vấn `JOIN` một-nhiều rồi yêu cầu một hàng | Nhầm bản ghi quan hệ với thực thể duy nhất | Thiết kế SQL/mapper theo cardinality thực |
| Lấy `getString(...) == null` làm kiểm tra tồn tại | Nhầm SQL NULL với thiếu hàng | Dùng `rs.next()` cho số hàng |
| Chỉ kiểm tra trước `INSERT`, không có `UNIQUE` | Hai request có thể đồng thời tạo trùng | Đặt ràng buộc DB và xử lý lỗi constraint |
| Quên đóng `ResultSet`/`PreparedStatement` | Rò rỉ cursor và tài nguyên DB | Dùng `try-with-resources` |
| Trả hàng đầu tiên khi thực tế có nhiều hàng | Che lỗi dữ liệu có thể ảnh hưởng người dùng | Báo lỗi có kiểm soát và điều tra nguyên nhân |

## 14. Quy trình thực hành khi viết hàm “tối đa một bản ghi”

1. **Xác định ý nghĩa duy nhất:** theo khóa chính, khóa nghiệp vụ, thực thể hay hàng SQL sau `JOIN`.
2. **Chọn hợp đồng trả về:** `Optional<T>` cho 0 hoặc 1; kiểu `T` với lỗi “không tìm thấy” nếu phải đúng 1.
3. **Viết SQL đủ điều kiện:** bao gồm tenant/quyền bắt buộc, cột cần đọc; bind các giá trị bằng `PreparedStatement`.
4. **Không dùng `LIMIT 1` để chứng minh duy nhất:** nếu cần giới hạn dữ liệu, chỉ giới hạn tối đa **2 hàng**.
5. **Gọi `rs.next()` thứ nhất:** nếu `false`, xử lý 0 hàng.
6. **Ánh xạ hàng đầu:** thực hiện khi con trỏ vẫn ở hàng đầu.
7. **Gọi `rs.next()` thứ hai:** nếu `true`, báo lỗi có ít nhất hai hàng; nếu `false`, trả bản ghi duy nhất.
8. **Đóng tài nguyên:** `ResultSet`/`PreparedStatement` bằng `try-with-resources` và quản lý `Connection` theo bên sở hữu.
9. **Bảo vệ bất biến ở DB:** thêm `UNIQUE` khi dữ liệu thực sự phải duy nhất; xử lý cạnh tranh ghi.
10. **Kiểm thử 0/1/2+ hàng**, trường hợp `NULL`, `JOIN` làm tăng số hàng và các đường lỗi.

**Quy tắc dễ nhớ:** với truy vấn JDBC mong đợi **không quá một bản ghi**, lần `rs.next()` thứ nhất trả lời “có hàng hay không”, còn lần thứ hai trả lời “có hơn một hàng hay không”. Chỉ trả đối tượng sau khi đã xác nhận lần thứ hai là `false`. Nếu tính duy nhất là yêu cầu dữ liệu lâu dài, hãy bảo vệ nó thêm bằng ràng buộc tương ứng ở cơ sở dữ liệu.
