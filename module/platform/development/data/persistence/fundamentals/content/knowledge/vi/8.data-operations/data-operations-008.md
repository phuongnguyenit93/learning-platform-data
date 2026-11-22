# Đọc một bản ghi và đọc tập kết quả

## 1. Vì sao cần phân biệt hai kiểu đọc?

Trong một hệ thống Java xử lý đơn hàng, hai yêu cầu thường gặp là:

- **Mở chi tiết một đơn hàng:** người dùng cung cấp **order_id**, hệ thống tìm đúng đơn đó, hoặc thông báo không tồn tại.
- **Liệt kê đơn hàng của một khách:** người dùng cung cấp **customer_id**, hệ thống lấy một danh sách có thể rỗng, có thể dài hàng nghìn đơn, thường kèm sắp xếp và phân trang.

Cả hai đều sử dụng lệnh **SELECT** của SQL, nhưng có hợp đồng dữ liệu, cách xử lý lỗi và yêu cầu hiệu năng khác nhau. Đọc một bản ghi thường có kết quả **0 hoặc 1 hàng hợp lệ**; đọc tập kết quả có thể trả về **0 đến N hàng**, hoặc một luồng dữ liệu được xử lý dần. Một truy vấn nghiệp vụ mong “đúng một” có thể gặp trường hợp có **nhiều hàng** do dữ liệu không duy nhất hoặc JOIN sai, nên không thể tùy tiện lấy hàng đầu tiên rồi coi là thành công.

Bài học thuộc chương **Thao tác dữ liệu** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung gắn với mục tiêu thiết kế tầng persistence cho Java: xác định hợp đồng truy vấn, đọc dữ liệu từ cơ sở dữ liệu bền vững, ánh xạ hàng/cột, quản lý kết nối, giao dịch và tối ưu những đường đọc phổ biến.

Sau bài học, người học có thể:

1. Phân biệt kết quả **không có bản ghi**, **một bản ghi** và **nhiều bản ghi**, cũng như ý nghĩa của chúng với API Java.
2. Viết truy vấn SQL đọc theo khóa chính, điều kiện nghiệp vụ và tập hàng có thứ tự.
3. Dùng JDBC **PreparedStatement** và **ResultSet** để đọc một hàng hoặc nhiều hàng một cách an toàn.
4. Xử lý cột **NULL**, lỗi ánh xạ dữ liệu, đóng tài nguyên và truyền tham số.
5. Đọc danh sách có giới hạn, phân trang theo offset và theo cursor, và nhận biết các giới hạn nhất quán.
6. Đọc kết quả bằng JPA, phân biệt các phương thức dành cho thực thể và tập kết quả.
7. Biết khi nào cần đọc toàn bộ vào bộ nhớ, khi nào cần xử lý từng phần và khi nào phải tối ưu SQL/chỉ mục.

## 2. Cùng một bảng nhưng có nhiều hợp đồng đọc

Giả sử cơ sở dữ liệu PostgreSQL quản lý khách hàng và đơn hàng:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE purchase_order (
    order_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id   BIGINT NOT NULL REFERENCES customer(customer_id),
    status        VARCHAR(20) NOT NULL
                  CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount  NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Bảng **purchase_order** có thể có dữ liệu:

| order_id | customer_id | status | total_amount | created_at (UTC) |
| ---: | ---: | --- | ---: | --- |
| 101 | 7 | PAID | 300000.00 | 2026-11-20 09:00 |
| 102 | 7 | NEW | 150000.00 | 2026-11-20 09:00 |
| 103 | 7 | PAID | 90000.00 | 2026-11-19 15:30 |
| 104 | 8 | NEW | 200000.00 | 2026-11-20 10:00 |

Với dữ liệu trên:

| Nhu cầu | Hợp đồng kết quả | Cách dùng thường gặp |
| --- | --- | --- |
| Tìm đơn **101** theo khóa chính | 0 hoặc 1 | **Optional<OrderSummary>** |
| Tìm khách hàng theo email duy nhất | 0 hoặc 1 | **Optional<Customer>** |
| Tìm đơn theo mã truy cập bắt buộc tồn tại | Đúng 1 theo nghiệp vụ; không có là lỗi | Đối tượng hoặc ngoại lệ nghiệp vụ |
| Liệt kê đơn của khách **7** | 0 đến nhiều hàng | **List<OrderSummary>** |
| Liệt kê đơn của khách 7, mỗi trang 20 hàng | 0 đến 20 hàng/trang | **Page** hoặc **Slice** tự định nghĩa |
| Xuất báo cáo hàng triệu dòng | Tập kết quả lớn | Duyệt theo lô hoặc streaming có giới hạn |
| Chỉ kiểm tra đơn có tồn tại không | Boolean | **EXISTS** hoặc truy vấn giới hạn |

**Không có bản ghi** thường là tình huống bình thường khi tìm theo ID hoặc danh sách, nhưng có thể là lỗi nghiệp vụ khi quy trình yêu cầu thực thể phải tồn tại. Cần lựa chọn ở tầng service, tránh để repository tùy tiện biến “không có” thành một đối tượng giả.

### 2.1. Đọc theo khóa chính khác đọc “hàng đầu tiên”

~~~sql
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE order_id = 101;
~~~

Vì **order_id** là PRIMARY KEY, cơ sở dữ liệu bảo đảm tối đa một hàng thỏa điều kiện. Nếu không có ID đó, kết quả gồm 0 hàng.

Trái lại:

~~~sql
SELECT order_id, status
FROM purchase_order
WHERE customer_id = 7
LIMIT 1;
~~~

Truy vấn này **không phải** truy vấn “đọc đơn duy nhất”. Khách 7 có ba đơn; **LIMIT 1** chỉ cắt kết quả xuống một hàng và không chỉ rõ hàng nào nếu không có **ORDER BY**. Nếu nghiệp vụ cần đơn mới nhất, phải đặt tiêu chí sắp xếp rõ ràng:

~~~sql
SELECT order_id, status
FROM purchase_order
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 1;
~~~

Dùng thêm **order_id DESC** làm tiêu chí phụ giúp thứ tự được xác định ngay cả khi hai đơn có cùng **created_at**.

## 3. Hợp đồng kết quả: 0, 1 hoặc nhiều hàng

Đối với một thao tác được thiết kế để trả **tối đa một bản ghi**, cần xử lý từng trường hợp:

| Số hàng tìm được | Truy vấn theo khóa duy nhất | Truy vấn kỳ vọng duy nhất theo nghiệp vụ |
| ---: | --- | --- |
| 0 | Trả về Optional.empty hoặc lỗi “không tìm thấy” ở service | Có thể trả empty hoặc lỗi tùy hợp đồng |
| 1 | Trả đúng bản ghi | Trả đúng bản ghi |
| 2 trở lên | Vi phạm giả định hoặc kết quả JOIN đã nhân hàng; cần điều tra | Báo lỗi dữ liệu không duy nhất, không âm thầm chọn hàng đầu |

Đối với một truy vấn danh sách, kết quả hợp lý thường là **List rỗng** khi không có hàng. Trả về **null** cho “không có kết quả” khiến mã gọi phải xử lý hai trạng thái không cần thiết: **null** và **List.of()**.

### 3.1. Vì sao không nên dùng LIMIT 1 để che dữ liệu trùng?

Một người quản trị cần tìm người dùng theo **employee_code**, nhưng cột chưa có ràng buộc UNIQUE:

~~~sql
SELECT user_id, full_name
FROM app_user
WHERE employee_code = ?;
~~~

Nếu hai người dùng cùng mã, việc thêm **LIMIT 1** sẽ che lỗi dữ liệu và trả một người bất kỳ. Cách khắc phục là:

1. Xác định mã nhân viên có bắt buộc duy nhất theo phạm vi tenant hay không.
2. Thiết kế **UNIQUE(employee_code)** hoặc **UNIQUE(tenant_id, employee_code)** nếu đúng nghiệp vụ.
3. Phân biệt trường hợp không có, có một và có nhiều kết quả trong giai đoạn phát hiện lỗi hoặc chuyển đổi dữ liệu.
4. Xử lý dữ liệu trùng trước khi thêm ràng buộc.

Nếu chỉ muốn phát hiện có nhiều hơn một kết quả mà không đọc vô hạn, có thể dùng **LIMIT 2**, kiểm tra số hàng 0, 1 hoặc 2. Tuy nhiên, **LIMIT 2** vẫn không thay thế ràng buộc duy nhất ở database khi có các giao dịch ghi đồng thời.

### 3.2. Một hàng SQL không phải lúc nào cũng là một thực thể

Câu SQL sau có thể trả nhiều hàng cho cùng một đơn:

~~~sql
SELECT o.order_id, o.status, oi.product_id, oi.quantity
FROM purchase_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
WHERE o.order_id = 101;
~~~

Ví dụ này giả định có bảng **order_item** với một dòng mỗi sản phẩm trong đơn. Nếu đơn 101 có ba dòng sản phẩm, kết quả JOIN có thể trả **ba hàng mang order_id = 101** dù bảng **purchase_order** chỉ có một đơn 101.

Do đó cần phân biệt:

- **Một hàng kết quả SQL**: một hàng trong kết quả sau phép JOIN.
- **Một thực thể đơn hàng**: một hàng cha có một định danh nghiệp vụ.
- **Một aggregate chứa nhiều dòng**: đơn hàng với danh sách order_item, phải được gom hoặc đọc theo cách phù hợp.

Không nên dùng **getSingleResult()** cho truy vấn JOIN một–nhiều chỉ vì điều kiện WHERE lọc theo một đơn.

## 4. Đọc một bản ghi bằng JDBC

### 4.1. Dùng PreparedStatement và Optional

Với **order_id** là khóa chính, một repository có thể trả về **Optional<OrderSummary>**:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Optional;

public final class OrderQueries {
    public record OrderSummary(
            long id,
            long customerId,
            String status,
            BigDecimal totalAmount,
            Instant createdAt
    ) {}

    public static Optional<OrderSummary> findById(
            Connection connection,
            long orderId
    ) throws SQLException {
        String sql = """
                SELECT order_id, customer_id, status,
                       total_amount, created_at
                FROM purchase_order
                WHERE order_id = ?
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, orderId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                OrderSummary order = mapOrder(rs);
                return Optional.of(order);
            }
        }
    }

    static OrderSummary mapOrder(ResultSet rs) throws SQLException {
        OffsetDateTime timestamp =
                rs.getObject("created_at", OffsetDateTime.class);

        return new OrderSummary(
                rs.getLong("order_id"),
                rs.getLong("customer_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"),
                timestamp.toInstant()
        );
    }
}
~~~

Đoạn mã sử dụng **Java 17+** (record và text block), JDBC, PostgreSQL và driver hỗ trợ ánh xạ **TIMESTAMPTZ** sang **OffsetDateTime**, như pgJDBC. Phương thức nhận **Connection** có sẵn; lớp gọi sở hữu vòng đời connection và giao dịch.

Những bước quan trọng:

1. **prepareStatement(sql)** tạo đối tượng thực thi câu SQL có tham số.
2. **setLong(1, orderId)** bind ID vào dấu **?** thứ nhất, không nối chuỗi đầu vào vào SQL.
3. **executeQuery()** trả **ResultSet** chứa các hàng từ SELECT.
4. **rs.next()** di chuyển con trỏ sang hàng tiếp theo và trả **false** khi không còn hàng.
5. Khi **rs.next()** đầu tiên trả false, **Optional.empty()** thể hiện đúng hợp đồng “không tìm thấy”.
6. Khi có hàng, ánh xạ từng cột sang DTO rồi trả **Optional.of(...)**.
7. **try-with-resources** đóng **ResultSet** và **PreparedStatement**, kể cả khi mapping thất bại.

Hàm này đọc một hàng vì **order_id có PRIMARY KEY**. Nếu truy vấn không có ràng buộc duy nhất, phải kiểm tra thêm **rs.next() lần thứ hai** trước khi kết luận kết quả là duy nhất.

### 4.2. Đọc đúng một hàng theo quy tắc nghiệp vụ

Đôi khi ứng dụng yêu cầu “phải tìm thấy một đơn hàng còn tồn tại” và không xem thiếu bản ghi là kết quả thông thường. Có thể giữ repository trả **Optional**, rồi chuyển thành ngoại lệ có ý nghĩa tại service:

~~~java
OrderQueries.OrderSummary order =
        OrderQueries.findById(connection, requestedOrderId)
                .orElseThrow(() ->
                        new OrderNotFoundException(requestedOrderId));
~~~

**OrderNotFoundException** là ngoại lệ nghiệp vụ do ứng dụng cần định nghĩa. Tránh để repository trả một DTO toàn giá trị rỗng/0 khi không có hàng; cách đó làm mất phân biệt giữa “không tồn tại” và “có bản ghi với giá trị hợp lệ bằng 0”.

Không nên tự động biến mọi **SQLException** thành “không tìm thấy”. **SQLException** có thể do mất kết nối, timeout, quyền truy cập hoặc lỗi SQL; đó là các nhóm lỗi khác với kết quả rỗng.

### 4.3. Đọc cột NULL một cách có chủ ý

Giả sử bổ sung cột tùy chọn:

~~~sql
ALTER TABLE purchase_order
ADD COLUMN approved_by BIGINT NULL;
~~~

Trong JDBC, **getLong("approved_by")** trả **0** nếu SQL NULL, vì **long primitive** không chứa được null. Muốn phân biệt phải kiểm tra **rs.wasNull()** ngay sau lời gọi:

~~~java
long approvedByValue = rs.getLong("approved_by");
Long approvedBy = rs.wasNull() ? null : approvedByValue;
~~~

Một số driver hỗ trợ **getObject("approved_by", Long.class)** cho kiểu boxed, nhưng tính portable và ánh xạ thực tế cần được xác minh bằng driver sử dụng. Với **VARCHAR**, **getString(...)** thường trả null khi cột SQL NULL. Với **NUMERIC**, **getBigDecimal(...)** có thể trả null. Mapper cần căn cứ vào **NULLability** của cột và hợp đồng Java.

Nếu một cột được khai báo NOT NULL nhưng mã Java thường xuyên gặp null, nên điều tra sự không nhất quán giữa schema thực tế, truy vấn JOIN và mapping thay vì che lỗi bằng một giá trị mặc định vô căn cứ.

## 5. Đọc một tập kết quả bằng JDBC

Đọc nhiều hàng là cách lặp qua **ResultSet** đến khi hết kết quả. Ví dụ liệt kê đơn hàng của một khách:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class CustomerOrderQueries {
    public static List<OrderQueries.OrderSummary> findByCustomer(
            Connection connection,
            long customerId
    ) throws SQLException {
        String sql = """
                SELECT order_id, customer_id, status,
                       total_amount, created_at
                FROM purchase_order
                WHERE customer_id = ?
                ORDER BY created_at DESC, order_id DESC
                """;

        List<OrderQueries.OrderSummary> result = new ArrayList<>();

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, customerId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(OrderQueries.mapOrder(rs));
                }
            }
        }

        return result;
    }
}
~~~

**while (rs.next())** duyệt qua từng hàng. Nếu khách không có đơn, vòng lặp không chạy và phương thức trả một **List rỗng**, không phải null. **ORDER BY** đặt ở SQL giúp mọi người gọi nhận thứ tự có chủ đích.

Ví dụ với **customer_id = 7**, các đơn được sắp theo **created_at giảm dần**, rồi **order_id giảm dần**; vì đơn 101 và 102 cùng timestamp, thứ tự hai đơn do ID quyết định.

### 5.1. Vì sao phải sắp xếp trong SQL?

Không có **ORDER BY**, SQL không cam kết thứ tự hàng. Kể cả một truy vấn hôm nay trả về đúng thứ tự ID, ngày mai thêm chỉ mục hoặc thay đổi kế hoạch thực thi có thể khiến thứ tự khác.

Nếu kết quả được phân trang, sắp xếp càng quan trọng: cùng một bộ tiêu chí cần có **thứ tự xác định**, tốt nhất dùng một khóa duy nhất làm tiêu chí cuối để xử lý các giá trị bằng nhau.

### 5.2. Truy vấn chỉ những cột cần dùng

Nếu giao diện danh sách chỉ hiển thị **order_id**, **status**, **total_amount**, không nhất thiết phải đọc mọi cột hoặc JOIN toàn bộ bảng chi tiết. Ví dụ:

~~~sql
SELECT order_id, status, total_amount
FROM purchase_order
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC;
~~~

Một DTO nhỏ dành cho danh sách có thể giảm lượng dữ liệu truyền và chi phí ánh xạ. Truy vấn theo use case thường rõ nghĩa và hiệu quả hơn việc luôn tải một aggregate lớn rồi bỏ phần lớn trường không sử dụng.

### 5.3. Khi đọc toàn bộ danh sách không còn phù hợp

**List** tích lũy toàn bộ hàng trong bộ nhớ ứng dụng. Nếu truy vấn trả vài chục hàng, điều này thường đơn giản và hợp lý; nếu trả hàng triệu hàng, bộ nhớ và GC có thể trở thành điểm nghẽn.

Khi tập kết quả lớn, cân nhắc:

- **Phân trang** để API giới hạn số hàng trên mỗi lần gọi.
- **Đọc theo lô** để xử lý import/export hoặc công việc định kỳ.
- **Streaming/cursor** để đọc và xử lý từng hàng trong lúc tài nguyên DB còn mở.
- **Tổng hợp ở database** nếu thực tế chỉ cần số lượng/tổng tiền, không cần mọi hàng chi tiết.

Không nên trả **List** rất lớn từ repository rồi mong controller tự cắt còn 20 hàng; làm vậy đã tốn chi phí truy vấn, truyền dữ liệu và cấp phát bộ nhớ trước khi cắt.

## 6. Kiểm tra tồn tại và đếm khác với lấy bản ghi

Khi nghiệp vụ chỉ hỏi **“Có đơn nào của khách 7 đang ở trạng thái NEW không?”**, lấy cả danh sách rồi kiểm tra trong Java làm nhiều việc không cần thiết.

Ví dụ PostgreSQL:

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM purchase_order
    WHERE customer_id = 7
      AND status = 'NEW'
) AS has_new_order;
~~~

**EXISTS** trả kiểu boolean, có ý nghĩa trực tiếp với nhu cầu kiểm tra tồn tại. Tùy kế hoạch thực thi, database có thể dừng khi thấy hàng phù hợp.

Nếu cần biết **số đơn**:

~~~sql
SELECT COUNT(*) AS order_count
FROM purchase_order
WHERE customer_id = 7;
~~~

Đếm và đọc danh sách là hai hợp đồng khác nhau. **COUNT(*)** trả một hàng chứa số lượng, ngay cả khi không có đơn; giá trị khi đó là 0. Còn **SELECT ... WHERE customer_id=7** có thể trả nhiều hàng hoặc 0 hàng.

Khi dùng JOIN, **COUNT(*)** có thể đếm số hàng *sau JOIN*, không đếm số thực thể cha. Nếu JOIN đơn hàng với chi tiết đơn, một đơn có nhiều dòng sẽ bị nhân lên; cần cân nhắc **COUNT(DISTINCT o.order_id)** hoặc đếm trên bảng cha tùy bài toán.

## 7. Phân trang: giới hạn số hàng đọc

Dữ liệu tăng lên theo thời gian, nên API danh sách thường giới hạn số bản ghi mỗi lần đọc. Hai kiểu phổ biến là **OFFSET pagination** và **keyset/cursor pagination**.

### 7.1. Phân trang bằng LIMIT và OFFSET

~~~sql
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
~~~

Truy vấn lấy tối đa **20 hàng**, bắt đầu sau **40 hàng đầu tiên** của thứ tự truy vấn. Nếu mỗi trang có 20 bản ghi, đây là trang thứ ba khi đánh số trang bắt đầu từ 1.

Cần chú ý:

- Kiểm tra đầu vào **pageSize > 0**, đặt giới hạn tối đa phù hợp như 100 hoặc 200 theo yêu cầu hệ thống.
- Kiểm tra **offset >= 0** và phép nhân **(pageNumber - 1) × pageSize** tránh tràn số.
- Không cho người dùng truyền một đoạn ORDER BY tùy ý trực tiếp vào SQL. Với sắp xếp động, dùng **danh sách cột cho phép** và tạo phần cú pháp SQL từ các lựa chọn đã kiểm soát.
- Với OFFSET lớn, database thường vẫn phải đi qua hoặc loại bỏ nhiều hàng trước khi trả trang đích; có thể chậm khi bảng lớn.
- Khi dữ liệu thay đổi giữa các lần gọi, một số hàng có thể xuất hiện lặp hoặc bị bỏ qua do vị trí offset bị dịch chuyển.

**LIMIT** giúp giảm số hàng trả về, nhưng không tự bảo đảm ít công việc đọc ở mọi kế hoạch thực thi. Nếu thiếu chỉ mục phù hợp với WHERE/ORDER BY, database vẫn có thể quét và sắp xếp một tập lớn.

### 7.2. Phân trang theo khóa tiếp nối (keyset)

Khi người dùng cuộn danh sách từ mới đến cũ, thay vì nói “bỏ qua 10.000 hàng”, ta có thể nói “lấy các hàng đứng sau bản ghi cuối của trang trước”.

Trang đầu:

~~~sql
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
~~~

Nếu giao diện chỉ cần 20 hàng, có thể đọc **21 hàng** để biết còn trang tiếp hay không rồi chỉ trả 20. Lấy **created_at** và **order_id** của hàng thứ 20 làm cursor.

Giả sử hàng cuối hiển thị là:

~~~text
created_at = 2026-11-20T09:00:00Z
order_id   = 101
~~~

Trang kế tiếp:

~~~sql
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE customer_id = 7
  AND (
      created_at < TIMESTAMPTZ '2026-11-20 09:00:00+00'
      OR (
          created_at = TIMESTAMPTZ '2026-11-20 09:00:00+00'
          AND order_id < 101
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
~~~

Vì sắp xếp giảm dần trên **created_at** và **order_id**, điều kiện **<** trên bộ giá trị tương ứng sẽ tiến về các hàng đứng sau cursor. PostgreSQL còn hỗ trợ so sánh theo tuple như **(created_at, order_id) < (?, ?)**, nhưng cú pháp và quy tắc NULL cần kiểm tra khi chuyển sang DB khác.

Đối với ứng dụng Java thực tế, các giá trị cursor phải được **bind bằng tham số**. Ví dụ trên dùng literal để giải thích. Cursor nên chứa cả timestamp và ID bởi hai đơn có thể cùng created_at.

**Điều kiện quan trọng:** keyset pagination cần khóa sắp xếp ổn định. Nếu một trường sắp xếp có thể thay đổi trong lúc người dùng phân trang, bản ghi có thể di chuyển giữa các trang. Keyset thường giảm nhược điểm của OFFSET với dữ liệu chèn mới ở đầu danh sách, nhưng **không tự tạo một snapshot nhất quán giữa các HTTP request**.

### 7.3. Page, Slice và số lượng tổng

Nếu màn hình yêu cầu **“Trang 3/57”**, thường cần biết tổng số kết quả bằng một truy vấn COUNT riêng, hoặc kỹ thuật khác phù hợp.

Nếu màn hình chỉ cần nút **“Xem thêm”**, đọc **pageSize + 1** để xác định **hasNext** thường đủ và tránh phải COUNT toàn bộ tập kết quả trong mỗi lần gọi.

| Giao diện mong muốn | Hợp đồng gợi ý | Đánh đổi |
| --- | --- | --- |
| Số trang và tổng số bản ghi | **Page(items, totalCount, pageNumber)** | Có thêm công việc đếm; dữ liệu có thể đổi giữa hai truy vấn |
| Cuộn vô hạn, “xem thêm” | **Slice(items, nextCursor)** | Không cần tổng số; khó nhảy thẳng đến trang N |
| Xuất toàn bộ báo cáo | Xử lý theo lô/stream | Quản lý thời gian chạy và tài nguyên |

Trong hệ thống đồng thời, **SELECT COUNT(*)** và **SELECT danh sách** ở hai thời điểm có thể quan sát trạng thái dữ liệu khác nhau. Nếu yêu cầu nhất quán chặt, cần thiết kế chiến lược transaction/isolation hoặc snapshot theo nghiệp vụ.

## 8. Ánh xạ nhiều hàng thành cấu trúc Java

Khi đọc tập kết quả, không phải lúc nào một hàng SQL cũng ánh xạ thành một entity đầy đủ. Một số cách dùng phổ biến:

| Loại truy vấn | Hình dạng Java hợp lý | Lưu ý |
| --- | --- | --- |
| SELECT theo khóa chính | **Optional<OrderSummary>** | Phân biệt 0 và 1 |
| SELECT nhiều đơn hàng | **List<OrderSummary>** | Danh sách có thể rỗng |
| SELECT COUNT(*) | **long** | Là số đếm, không phải List |
| SELECT EXISTS | **boolean** | Không cần đọc hàng chi tiết |
| SELECT GROUP BY status | **List<StatusCount>** | Một hàng là một nhóm thống kê |
| SELECT JOIN order_item | **List<OrderLine>** hoặc aggregate đã gom | Nhiều hàng có thể thuộc cùng một đơn |
| SELECT nhiều triệu hàng | Consumer theo lô hoặc stream có vòng đời rõ | Tránh tích hết vào heap |

Ví dụ DTO thống kê:

~~~java
public record StatusCount(String status, long count) {}
~~~

Có thể ánh xạ kết quả:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM purchase_order
WHERE customer_id = ?
GROUP BY status
ORDER BY status;
~~~

Mỗi hàng là một **nhóm trạng thái**, không phải một đơn hàng. Đặt tên DTO theo kết quả thực giúp tránh nhầm lẫn và làm API bền vững khi lược đồ thay đổi.

### 8.1. Tránh SELECT * trong tầng API ổn định

**SELECT \*** thường tiện khi thử nghiệm, nhưng mã repository nên chọn cột có chủ đích:

- DDL có thể thêm cột nhạy cảm hoặc cột lớn mà danh sách không cần.
- Kết quả nhiều cột hơn làm tăng lượng truyền và chi phí ánh xạ.
- Truy vấn JOIN nhiều bảng có thể có cột trùng tên, gây ánh xạ mơ hồ.
- Kết quả cần một DTO nhất định nên được mô tả bằng danh sách cột tường minh và alias rõ ràng.

Không phải mọi trường hợp **SELECT \*** đều sai; tuy nhiên, trong persistence API cần hợp đồng ổn định, chọn cột cụ thể dễ bảo trì hơn.

## 9. Đọc tập dữ liệu rất lớn: cursor và streaming

Một truy vấn trả 1.000.000 đơn hàng sẽ khó xử lý nếu phương thức luôn tạo **List** chứa toàn bộ kết quả. Có thể duyệt và gửi từng hàng đến một **Consumer**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.function.Consumer;

public final class OrderExportQueries {
    public static void forEachByCustomer(
            Connection connection,
            long customerId,
            Consumer<OrderQueries.OrderSummary> consumer
    ) throws SQLException {
        String sql = """
                SELECT order_id, customer_id, status,
                       total_amount, created_at
                FROM purchase_order
                WHERE customer_id = ?
                ORDER BY created_at, order_id
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setFetchSize(500);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    consumer.accept(OrderQueries.mapOrder(rs));
                }
            }
        }
    }
}
~~~

**Lưu ý:** **setFetchSize(500)** là gợi ý cho driver, không phải lời hứa chung rằng mỗi lần luôn chỉ đọc 500 hàng hoặc ứng dụng không bao giờ đệm toàn bộ. Với **pgJDBC**, streaming dựa trên cursor thường đòi hỏi connection ở trạng thái **autoCommit = false**, ResultSet kiểu forward-only và những điều kiện driver cụ thể. Đoạn ví dụ giả định tầng gọi đã cấu hình connection/giao dịch theo chế độ phù hợp; nếu không, driver có thể lấy toàn bộ kết quả vào bộ nhớ.

### 9.1. Vòng đời tài nguyên là một phần của hợp đồng

Trong khi lặp **ResultSet**, các tài nguyên có thể vẫn đang mở:

- Connection từ pool.
- Statement và ResultSet phía driver.
- Giao dịch đọc và snapshot dữ liệu nếu database đang giữ.
- Cursor hoặc bộ nhớ đệm ở database.

Không trả một **Stream** từ phương thức đã đóng connection/result set rồi mong người gọi tiếp tục đọc được. Nếu API trả stream, phải thiết kế chủ thể chịu trách nhiệm đóng nó, phạm vi transaction và quy tắc xử lý lỗi. Với use case xuất file, mẫu **forEach** thực hiện tiêu thụ dữ liệu trong cùng phạm vi tài nguyên thường dễ quản lý hơn.

Không nên giữ transaction streaming nhiều phút nếu hệ thống có tải cập nhật lớn, vì giao dịch dài có thể giữ snapshot và cản trở dọn dẹp phiên bản dữ liệu (tùy engine). Thay vào đó, chia lô theo ID hoặc cursor có giới hạn, ghi kết quả ra nơi cần và giải phóng kết nối thường xuyên.

### 9.2. Xử lý lỗi khi đang stream

Một stream có thể thành công ở 100.000 hàng đầu nhưng lỗi kết nối ở hàng 100.001. Trong lúc đó, ứng dụng có thể đã gửi một phần response hoặc ghi một phần file.

Khi thiết kế xuất dữ liệu:

1. Xác định có chấp nhận kết quả một phần hay không.
2. Nếu cần file cuối cùng nguyên vẹn, cân nhắc ghi vào tệp tạm hoặc vùng staging và chỉ công bố sau khi thành công.
3. Nếu retry, xác định cách bỏ qua những hàng đã xử lý và tránh trùng lặp.
4. Nếu dữ liệu thay đổi trong lúc xuất, xác định snapshot hoặc yêu cầu nhất quán cần thiết.

Đó là vấn đề nghiệp vụ và vòng đời thao tác đọc, không thể giải quyết chỉ bằng việc gọi **ResultSet.next()** trong một vòng lặp.

## 10. Đọc một bản ghi và tập kết quả bằng JPA

JPA cung cấp tầng ánh xạ thực thể thay cho việc tự tạo mọi **PreparedStatement**. Ví dụ ánh xạ bảng **purchase_order**:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.OffsetDateTime;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrderEntity {
    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected PurchaseOrderEntity() {}

    public Long getId() { return id; }
    public String getStatus() { return status; }
}
~~~

Đây là ví dụ ánh xạ đọc giản lược. Ứng dụng thực tế phải quản lý entity lifecycle, ID strategy nếu ghi, kiểu thời gian tương thích với provider/driver và cách biểu diễn quan hệ **customer_id** theo thiết kế.

### 10.1. Đọc theo khóa chính với EntityManager.find

~~~java
PurchaseOrderEntity entity =
        entityManager.find(PurchaseOrderEntity.class, 101L);

if (entity == null) {
    // Không có bản ghi tương ứng.
}
~~~

**find** nhận khóa chính, trả entity nếu có, hoặc **null** nếu không có. Có thể chuyển sang **Optional.ofNullable(...)** tại repository để service dùng một hợp đồng thống nhất.

Đọc qua EntityManager có thể liên quan **persistence context** và cache cấp một; không nên tự suy luận mỗi lời gọi find đều phát một SELECT, cũng không nên coi dữ liệu trong persistence context luôn phản ánh các thay đổi từ một nguồn ghi bên ngoài ngay lập tức.

### 10.2. getSingleResult và các trường hợp ngoại lệ

~~~java
import jakarta.persistence.TypedQuery;
import jakarta.persistence.NoResultException;
import jakarta.persistence.NonUniqueResultException;

TypedQuery<PurchaseOrderEntity> query = entityManager.createQuery(
        "SELECT o FROM PurchaseOrderEntity o " +
        "WHERE o.customerId = :customerId AND o.status = :status",
        PurchaseOrderEntity.class
);

query.setParameter("customerId", 7L);
query.setParameter("status", "PAID");

try {
    PurchaseOrderEntity one = query.getSingleResult();
    // Dùng một kết quả.
} catch (NoResultException missing) {
    // Không có kết quả.
} catch (NonUniqueResultException duplicated) {
    // Nhiều hơn một kết quả: trái hợp đồng lấy một bản ghi.
}
~~~

Trong JPA, **getSingleResult()** yêu cầu đúng một kết quả theo ngữ nghĩa truy vấn: khi không có kết quả, nó ném **NoResultException**; khi có nhiều hơn một kết quả, nó ném **NonUniqueResultException**. Ví dụ trên chỉ nên dùng getSingleResult nếu nghiệp vụ thực sự bảo đảm một đơn PAID cho khách 7; thông thường một khách có thể có nhiều đơn PAID, vì vậy hợp đồng trên cần xem lại.

Một số phiên bản Jakarta Persistence/provider có phương thức trả kết quả đơn hoặc null để giảm xử lý ngoại lệ, nhưng vẫn phải xác định cách đối xử với kết quả không duy nhất. Khi đọc theo khóa chính, **EntityManager.find** thường diễn đạt ý định rõ hơn.

### 10.3. getResultList cho tập kết quả

~~~java
import java.util.List;

List<PurchaseOrderEntity> orders = entityManager.createQuery(
        "SELECT o FROM PurchaseOrderEntity o " +
        "WHERE o.customerId = :customerId " +
        "ORDER BY o.createdAt DESC, o.id DESC",
        PurchaseOrderEntity.class
).setParameter("customerId", 7L)
 .setMaxResults(20)
 .getResultList();
~~~

**getResultList()** trả một danh sách; khi không có kết quả thì danh sách rỗng. **setMaxResults(20)** giới hạn số bản ghi được trả theo ngữ nghĩa truy vấn. Cần kết hợp với **ORDER BY** để tránh trang kết quả không xác định.

Có thể dùng **setFirstResult(offset)** để phân trang kiểu OFFSET, nhưng nhược điểm offset lớn và dữ liệu thay đổi vẫn tồn tại. Những query fetch join nhiều collection cần kiểm tra kỹ cách ORM áp dụng paging; một số trường hợp ORM có thể phải đọc nhiều hàng rồi giới hạn trong bộ nhớ hoặc báo cảnh báo.

### 10.4. Đọc entity hay DTO?

Entity được quản lý có thể kích hoạt dirty checking, lazy loading và các quan hệ bổ sung. Nếu một màn hình chỉ cần ID, trạng thái, tổng tiền, dùng **DTO projection** có thể giảm dữ liệu:

~~~java
public record OrderListItem(Long id, String status, BigDecimal total) {}
~~~

~~~java
List<OrderListItem> items = entityManager.createQuery(
        "SELECT new com.example.OrderListItem(" +
        "o.id, o.status, o.totalAmount) " +
        "FROM PurchaseOrderEntity o " +
        "WHERE o.customerId = :customerId " +
        "ORDER BY o.createdAt DESC, o.id DESC",
        OrderListItem.class
).setParameter("customerId", 7L)
 .setMaxResults(20)
 .getResultList();
~~~

Ví dụ này giả định **OrderListItem** nằm trong package **com.example** và constructor tương ứng với record. Trong mã thực tế, dùng đầy đủ tên lớp theo package thực. JPQL đọc theo **thuộc tính entity**, không dùng tên cột SQL trực tiếp.

DTO projection đặc biệt hữu ích khi endpoint chỉ đọc và không cần thao tác trên vòng đời entity.

## 11. Quan hệ giữa đọc dữ liệu và tính nhất quán giao dịch

Một SELECT đơn lẻ có thể đọc được dữ liệu hợp lệ tại thời điểm nó thực thi, nhưng **hai SELECT liên tiếp** trong cùng một thao tác nghiệp vụ không nhất thiết quan sát cùng một trạng thái khi có người khác cập nhật dữ liệu.

Ví dụ:

1. Service SELECT đơn hàng **101**, thấy status = NEW.
2. Giao dịch khác cập nhật đơn đó thành CANCELLED và commit.
3. Service SELECT các dòng hàng của đơn 101.
4. Service ghép dữ liệu từ hai lần đọc để trả về API.

Tùy mức cô lập và ranh giới giao dịch, service có thể kết hợp dữ liệu ở các thời điểm khác nhau. Với PostgreSQL mặc định **READ COMMITTED**, mỗi câu lệnh thường quan sát snapshot riêng tại đầu câu lệnh. Nếu nghiệp vụ yêu cầu đọc nhất quán giữa nhiều câu lệnh, cần thiết kế giao dịch đọc với isolation phù hợp hoặc truy vấn gộp phù hợp.

Không có một mức isolation luôn tốt nhất. Mức cao hơn có thể tăng chi phí, phát sinh xung đột/serialization failure và cần retry. Đọc cho giao diện liệt kê sản phẩm thường chấp nhận một mức thay đổi nhất định; đọc phục vụ quyết định chuyển tiền hay xác nhận trạng thái cần hợp đồng mạnh hơn.

### 11.1. Đọc trước rồi ghi không tự động an toàn

Một quy trình:

~~~text
SELECT available_stock
if stock >= quantity:
    UPDATE stock
~~~

có thể sai khi hai yêu cầu đồng thời đọc cùng số tồn kho rồi cùng trừ. **Đọc một bản ghi thành công** không có nghĩa giá trị đó vẫn đúng tại thời điểm UPDATE.

Cần thiết kế cơ chế kiểm soát đồng thời phù hợp, chẳng hạn:

- Cập nhật có điều kiện **UPDATE ... WHERE available_stock >= ?**, rồi kiểm tra số hàng bị ảnh hưởng.
- Khóa hàng bằng **SELECT ... FOR UPDATE** trong giao dịch phù hợp.
- Optimistic locking với cột phiên bản, nếu phù hợp.

Bài học này tập trung vào cách đọc; ví dụ cho thấy ranh giới giữa **lấy dữ liệu** và **ra quyết định dựa trên dữ liệu** phải được thiết kế có ý thức về concurrency.

## 12. Bảo mật và quyền đọc

Một ID hợp lệ không có nghĩa người gọi có quyền xem bản ghi. Ví dụ tài khoản A có thể đoán ID của đơn thuộc khách B:

~~~sql
-- Chỉ lọc theo ID có thể trả đơn của khách khác nếu tầng trên không kiểm soát quyền.
SELECT order_id, customer_id, status
FROM purchase_order
WHERE order_id = ?;
~~~

Trong hệ thống nhiều tenant hoặc nhiều người dùng, truy vấn thường cần thêm phạm vi được ủy quyền:

~~~sql
SELECT order_id, customer_id, status
FROM purchase_order
WHERE order_id = ?
  AND customer_id = ?;
~~~

Đây là ví dụ đơn giản khi người dùng chỉ được phép xem đơn của đúng customer_id đã xác thực. Thực tế có thể có vai trò quản trị, người chăm sóc khách hàng hoặc chia sẻ quyền; điều kiện lọc phải theo chính sách nghiệp vụ.

**Không lấy customer_id từ body hoặc query parameter của người dùng rồi coi là đã xác thực.** Quyền truy cập phải xuất phát từ danh tính, phiên/credential và chính sách phân quyền đã được kiểm tra.

Tương tự, **đọc danh sách** phải giới hạn ngay trong SQL theo tenant hoặc phạm vi quyền. Đừng đọc tất cả đơn của mọi khách về Java rồi lọc trong bộ nhớ, vì có nguy cơ lộ dữ liệu qua log, cache, lỗi phân trang hoặc bộ nhớ dùng chung.

### 12.1. Parametrized SQL không thay cho phân quyền

**PreparedStatement** bảo vệ cách truyền giá trị và giảm nguy cơ SQL injection khi dùng đúng. Nó không xác định người gọi có quyền đọc bản ghi nào. Hai lớp này giải quyết hai vấn đề khác nhau.

Cũng cần tránh trả chi tiết lỗi SQL, stack trace hoặc toàn bộ thông tin kết nối ra API. Log phục vụ vận hành phải hạn chế dữ liệu cá nhân và thông tin nhạy cảm từ các hàng được đọc.

## 13. Hiệu năng: đọc đúng số hàng và đúng cột

Một đường đọc chậm có thể đến từ:

- Truy vấn lọc bằng cột thiếu chỉ mục phù hợp.
- SELECT quá nhiều cột hoặc JOIN những bảng không cần.
- Dùng OFFSET sâu trên tập dữ liệu lớn.
- Duyệt từng hàng nhưng thực tế chỉ cần COUNT/EXISTS.
- ORM tạo chuỗi N+1 truy vấn khi truy cập quan hệ.
- Kết quả lớn bị giữ toàn bộ trong List.
- Connection pool bị chiếm lâu bởi stream hoặc giao dịch đọc kéo dài.

Với truy vấn liệt kê đơn của khách:

~~~sql
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Có thể cân nhắc chỉ mục hỗ trợ lọc và sắp xếp:

~~~sql
CREATE INDEX idx_order_customer_created_id
ON purchase_order (customer_id, created_at DESC, order_id DESC);
~~~

Trong PostgreSQL, **PRIMARY KEY** thường đi kèm chỉ mục duy nhất; **FOREIGN KEY** ở bảng tham chiếu không tự động tạo chỉ mục tương ứng. Chỉ mục trên **customer_id, created_at, order_id** có thể hữu ích với mẫu truy vấn này, nhưng cũng tốn dung lượng và chi phí ghi. Chỉ quyết định sau khi xem dữ liệu và kế hoạch thực thi thực tế.

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, status, total_amount, created_at
FROM purchase_order
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

**EXPLAIN ANALYZE** thực thi câu SELECT để đo thực tế; chỉ nên chạy khi phù hợp về tải và dữ liệu. Đánh giá số hàng đọc, thời gian, thao tác sort, dùng index và số buffer truy cập. Không khẳng định một index luôn nhanh hơn trong mọi phân bố dữ liệu.

### 13.1. N+1 khi đọc quan hệ trong JPA

Nếu service lấy 100 đơn, rồi mỗi đơn lại truy cập **order.getCustomer()** và ORM phát thêm một truy vấn cho từng customer, ứng dụng có thể tạo **1 + 100** truy vấn. Đó là vấn đề **N+1**.

Một số cách xử lý theo nhu cầu:

- **JOIN FETCH** khi tập quan hệ và phân trang cho phép.
- **DTO projection** lấy các cột từ nhiều bảng trong một truy vấn.
- **Batch fetching** hoặc cơ chế fetch phù hợp của ORM.
- Đọc danh sách ID rồi lấy dữ liệu liên quan theo lô.

JOIN FETCH collection một–nhiều kết hợp paging có thể làm nhân số hàng và hạn chế trong bộ nhớ. Không có một tùy chọn fetch tối ưu cho mọi endpoint; cần đo SQL thực sự, số hàng trả về và bộ nhớ.

## 14. Lỗi đọc dữ liệu và xử lý kết quả bất thường

Trong một hệ thống production, đọc dữ liệu có thể thất bại vì nhiều nguyên nhân:

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy bản ghi | rs.next() đầu tiên trả false | Optional.empty hoặc lỗi nghiệp vụ ở service |
| Kỳ vọng 1 nhưng có nhiều bản ghi | Query không duy nhất, getSingleResult thất bại | Tìm lỗi mô hình/ràng buộc; không che bằng LIMIT 1 |
| SQL NULL ở cột kiểu primitive | getLong trả 0 | Dùng wasNull()/boxed type khi nullable |
| Không mở được kết nối | SQLException | Quan sát pool, DB, mạng; retry nếu chính sách cho phép |
| Query timeout | SQLException hoặc lỗi provider | Tối ưu SQL/chỉ mục; giới hạn thời gian truy vấn |
| Thiếu quyền đọc | Lỗi database hoặc dữ liệu bị lọc | Kiểm tra phân quyền và quyền DB |
| Mapping sai kiểu hoặc cột | SQLException, conversion error | Đồng bộ DDL, query và DTO |
| ResultSet đã đóng | Lỗi khi đọc tiếp | Xử lý dữ liệu trước khi đóng tài nguyên |
| Tập kết quả quá lớn | Dùng nhiều heap, GC hoặc OOM | Pagination, streaming, batch |
| Dữ liệu thay đổi trong lúc phân trang | Trùng hoặc thiếu bản ghi giữa trang | Keyset/snapshot, hợp đồng nhất quán rõ ràng |

**Retry truy vấn đọc** có thể hợp lý khi lỗi kết nối tạm thời và không có tác dụng phụ, nhưng phải có giới hạn số lần, timeout và quan sát lỗi. Một “truy vấn đọc” trong ứng dụng có thể đi kèm ghi audit, tăng counter hoặc gọi dịch vụ khác; không tự động retry toàn bộ thao tác mà không xem tác dụng phụ.

### 14.1. Đóng tài nguyên theo đúng chủ sở hữu

Nếu repository **nhận Connection từ bên ngoài**, repository nên đóng statement/result set mà nó tạo, còn tầng gọi quản lý connection. Nếu repository tự lấy connection từ **DataSource**, nó phải đóng connection theo quy ước pool (trả lại pool), thường qua try-with-resources.

Không đóng connection được quản lý bởi transaction framework giữa chừng; cũng không để statement/result set sống lâu hơn phạm vi connection đã đóng.

## 15. Bài tập thực hành và tự kiểm tra

### Bài tập 1: một bản ghi hay danh sách?

Giả sử cần thiết kế các method:

1. **findById(101)** với order_id là PRIMARY KEY.
2. **findByCustomerId(7)**.
3. **countByCustomerId(7)**.
4. **existsOpenOrder(7)** với yêu cầu chỉ biết có đơn NEW hay không.

**Gợi ý trả lời:** các hợp đồng tương ứng có thể là **Optional<Order>**, **List<OrderSummary>**, **long**, **boolean**. Nếu không có đơn cho khách, danh sách rỗng và count = 0 là kết quả bình thường.

### Bài tập 2: đếm hàng của JOIN

Đơn 101 có ba dòng hàng. Truy vấn JOIN purchase_order với order_item và WHERE order_id = 101 trả bao nhiêu hàng?

**Gợi ý:** thường **ba hàng**, mỗi hàng cho một order_item, nếu cả ba dòng thỏa điều kiện JOIN. Điều đó không có nghĩa có ba đơn 101. Để tạo một object Order chứa các dòng, phải gom theo order_id hoặc truy vấn cha–con có kiểm soát.

### Bài tập 3: dữ liệu trùng

Một truy vấn theo employee_code đáng lẽ trả tối đa một người nhưng hiện trả hai. Có nên thêm LIMIT 1?

**Gợi ý:** Không nên coi LIMIT 1 là cách sửa lỗi. Phải làm rõ quy tắc duy nhất, sửa dữ liệu trùng và thêm ràng buộc UNIQUE đúng phạm vi. Trong giai đoạn phát hiện, có thể đọc tối đa hai hàng để xác định tình trạng nhiều kết quả.

### Bài tập 4: NULL và JDBC

Cột approved_by cho phép NULL. Khi dùng **getLong("approved_by")**, mã nhận 0. Điều đó có chứng minh người phê duyệt có ID 0 không?

**Gợi ý:** Không. Cần gọi **wasNull()** ngay sau getLong, hoặc chọn phép đọc boxed type thích hợp với driver.

### Bài tập 5: trang kết quả không ổn định

Một API dùng:

~~~sql
SELECT order_id, status
FROM purchase_order
WHERE customer_id = ?
LIMIT 20 OFFSET 20;
~~~

Vì sao cùng một truy vấn có thể cho kết quả khác sau khi tạo index hoặc có đơn mới?

**Gợi ý:** Thiếu ORDER BY nên không có thứ tự bảo đảm. Ngay cả khi bổ sung ORDER BY, OFFSET có thể dịch chuyển khi dữ liệu bị thêm/xóa giữa các lần gọi. Có thể dùng thứ tự xác định và keyset pagination nếu phù hợp.

### Bài tập 6: viết truy vấn chỉ kiểm tra tồn tại

Yêu cầu: xác định khách 7 có đơn PAID nào không. Viết SQL chỉ trả một boolean.

~~~sql
SELECT EXISTS (
    SELECT 1 FROM purchase_order
    WHERE customer_id = 7 AND status = 'PAID'
) AS has_paid_order;
~~~

Truy vấn này thể hiện trực tiếp ý định, không cần đọc toàn bộ các đơn PAID về bộ nhớ Java.

### Bài tập 7: chọn cách xuất báo cáo

Cần xuất 5 triệu đơn hàng ra một file. Vì sao không nên dùng **List<Order> findAll()**?

**Gợi ý:** List giữ toàn bộ kết quả trong heap, dễ tốn bộ nhớ. Nên chia lô theo cursor/keyset hoặc stream với transaction, driver fetch size và vòng đời tài nguyên được kiểm soát; cần định nghĩa cách xử lý khi xuất được nửa file rồi lỗi.

## 16. Ghi nhớ

**Đọc một bản ghi** thường dùng khóa chính hoặc khóa duy nhất, có hợp đồng **0 hoặc 1**; trong Java, **Optional<T>** giúp diễn đạt “không tìm thấy”. Khi nghiệp vụ yêu cầu **đúng một**, cần xử lý cả trường hợp không có và nhiều hơn một kết quả. **Đọc tập kết quả** trả nhiều hàng, thường là **List<T>** có thể rỗng, hoặc một quá trình đọc theo lô/stream khi dữ liệu lớn.

Trong JDBC, **ResultSet.next()** quyết định có còn hàng để đọc và **try-with-resources** giúp đóng tài nguyên đúng phạm vi. Trong JPA, **EntityManager.find**, **getSingleResult** và **getResultList** có ngữ nghĩa khác nhau, cần chọn theo hợp đồng truy vấn. Với danh sách, luôn xác định **ORDER BY**, giới hạn số hàng, phân trang và phạm vi quyền đọc; với nhiều lần truy vấn, phải cân nhắc tính nhất quán giao dịch.

Một tầng persistence Java đáng tin cậy trả về đúng **hình dạng dữ liệu mà nghiệp vụ cần**, phân biệt “không tìm thấy” với lỗi hạ tầng, không tải quá nhiều và bảo vệ tính toàn vẹn khi dữ liệu thay đổi đồng thời.
