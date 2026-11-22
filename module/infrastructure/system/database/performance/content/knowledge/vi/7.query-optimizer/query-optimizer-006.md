# Câu lệnh chuẩn bị sẵn, tham số hóa và lựa chọn kế hoạch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách prepared statement tách cấu trúc SQL khỏi giá trị tham số và hỗ trợ tái sử dụng câu lệnh.
- Phân biệt lợi ích bảo mật của tham số hóa với lợi ích hiệu năng của việc tái sử dụng kế hoạch.
- Mô tả cách bộ tối ưu chọn kế hoạch dựa trên thống kê, kiểu dữ liệu và độ chọn lọc của tham số.
- Nhận diện parameter sensitivity, parameter sniffing và trường hợp một kế hoạch dùng chung không phù hợp với mọi giá trị.
- Đo, so sánh và lựa chọn chiến lược kế hoạch phù hợp với workload thực tế.

## 1. Vì sao cần câu lệnh chuẩn bị sẵn và tham số hóa?

Trong module DATABASE_PERFORMANCE, tối ưu truy vấn cần dựa trên đo đạc tải, thống kê và kế hoạch thực thi. Một ứng dụng thường gửi cùng một mẫu SQL nhiều lần, chỉ thay đổi giá trị như mã khách hàng, trạng thái đơn hàng hoặc khoảng thời gian. Nếu mỗi lần gửi một chuỗi SQL khác nhau, hệ quản trị có thể phải phân tích và lập kế hoạch lặp lại, đồng thời khó nhận diện các lần thực thi thuộc cùng một mẫu truy vấn.

Prepared statement (câu lệnh chuẩn bị sẵn) cho phép ứng dụng chuẩn bị cấu trúc câu SQL rồi thực thi nhiều lần với các giá trị tham số khác nhau. Parameterization (tham số hóa) giữ phần cấu trúc SQL cố định và truyền dữ liệu riêng qua các tham số có kiểu.

Ví dụ, thay vì ghép giá trị trực tiếp vào chuỗi:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
```

ứng dụng gửi một mẫu câu lệnh có tham số:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = $1
  AND status = $2;
```

Ở lần thực thi, ứng dụng truyền `42` và `PAID` làm giá trị. Cấu trúc câu lệnh không thay đổi theo dữ liệu đầu vào.

Tham số hóa có hai lợi ích cần phân biệt:

- **Bảo mật và tính đúng đắn:** dữ liệu được truyền như giá trị, không bị diễn giải thành cú pháp SQL. Điều này giúp phòng tránh SQL injection khi dùng đúng API bind parameter.
- **Hiệu năng:** mẫu SQL ổn định có thể giúp driver hoặc hệ quản trị tái sử dụng trạng thái chuẩn bị, kế hoạch hoặc thông tin liên quan, giảm chi phí phân tích và lập kế hoạch trong một số tình huống.

Tham số hóa không bảo đảm mọi lần thực thi sẽ dùng cùng một kế hoạch tốt. Bộ tối ưu vẫn phải cân nhắc thống kê và đặc điểm của giá trị đầu vào; đôi khi một kế hoạch riêng cho từng nhóm tham số tốt hơn kế hoạch dùng chung.

## 2. Vòng đời thực thi một câu lệnh

Tùy hệ quản trị và giao thức, các bước có thể được tách hoặc gộp khác nhau, nhưng một câu SQL thường trải qua các công đoạn khái quát sau:

1. **Parse (phân tích cú pháp):** kiểm tra cú pháp và tạo cấu trúc biểu diễn câu SQL.
2. **Resolve và kiểm tra ngữ nghĩa:** xác định bảng, cột, hàm, quyền truy cập và kiểu dữ liệu.
3. **Rewrite (viết lại):** áp dụng các quy tắc viết lại của hệ quản trị, chẳng hạn xử lý view hoặc quy tắc.
4. **Plan/optimize (lập kế hoạch):** ước lượng số dòng, chi phí CPU/I/O và lựa chọn cách truy cập, thứ tự join, thuật toán join, sắp xếp hoặc aggregate.
5. **Bind (gắn tham số):** gắn các giá trị thực tế vào vị trí tham số theo giao thức và cơ chế của hệ quản trị.
6. **Execute (thực thi):** chạy kế hoạch, đọc/ghi dữ liệu và trả kết quả.

Ở một số hệ quản trị, việc bind xảy ra trước hoặc trong quá trình chọn kế hoạch; một số hệ thống có thể tạo kế hoạch tùy giá trị tham số. Vì vậy, không nên hiểu thứ tự trên là một pipeline bắt buộc giống hệt nhau ở mọi sản phẩm.

Prepared statement thường giữ một định danh hoặc đối tượng đã chuẩn bị trong phạm vi kết nối, phiên làm việc hoặc cơ chế cache của driver. Khi thực thi lại, ứng dụng truyền bộ giá trị mới thay vì gửi lại toàn bộ cấu trúc SQL.

Điều này có thể giảm chi phí parse và plan khi cùng một câu lệnh được gọi thường xuyên. Tuy nhiên, lợi ích phụ thuộc vào tần suất tái sử dụng, cách driver triển khai, phạm vi cache, khả năng cache của hệ quản trị và việc kế hoạch có phải lập lại hay không.

## 3. Tham số hóa đúng cách

### Truyền giá trị bằng bind parameter

Hãy dùng API tham số hóa của driver hoặc ORM. Ví dụ Java JDBC:

```java
String sql = "SELECT order_id, total_amount "
        + "FROM orders "
        + "WHERE customer_id = ? AND status = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long orderId = result.getLong("order_id");
            BigDecimal total = result.getBigDecimal("total_amount");
            // Xử lý kết quả
        }
    }
}
```

Ví dụ dùng JDBC minh họa việc truyền dữ liệu riêng với cấu trúc SQL. Trong thực tế, cần chọn setter khớp kiểu cột và quản lý connection theo vòng đời của ứng dụng.

Không ghép dữ liệu đầu vào vào SQL:

```java
// Không an toàn: dữ liệu đầu vào trở thành một phần cú pháp SQL
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
```

Khi `email` đến từ người dùng, chuỗi đặc biệt có thể thay đổi ý nghĩa câu lệnh. Dùng bind parameter khiến giá trị được xử lý như dữ liệu.

### Tham số không thay thế được tên bảng, tên cột hoặc từ khóa

Bind parameter thường chỉ đại diện cho giá trị biểu thức. Không thể dùng một tham số thông thường để thay tên cột, tên bảng, hướng `ASC`/`DESC` hoặc một đoạn cú pháp SQL tùy ý.

Nếu cần sắp xếp theo lựa chọn người dùng, hãy ánh xạ lựa chọn vào danh sách tên cột và hướng sắp xếp đã cho phép:

```java
String sortColumn = switch (requestedSort) {
    case "date" -> "created_at";
    case "amount" -> "total_amount";
    default -> "order_id";
};

String direction = descending ? "DESC" : "ASC";
String sql = "SELECT order_id, created_at, total_amount "
        + "FROM orders ORDER BY " + sortColumn + " " + direction;
```

Ở ví dụ này, phần được ghép chỉ đến từ danh sách cho phép do ứng dụng kiểm soát. Mọi giá trị dữ liệu khác vẫn nên bind qua tham số.

### Dùng đúng kiểu dữ liệu

Kiểu của tham số nên tương thích với kiểu cột. Nếu cột là `BIGINT` nhưng ứng dụng bind chuỗi ký tự, hệ quản trị có thể phải chuyển kiểu ngầm định. Tùy hệ quản trị, phép chuyển đổi có thể làm thay đổi ước lượng cardinality hoặc khiến điều kiện không còn dùng được đường truy cập chỉ mục mong muốn.

Ví dụ, nếu `customer_id` là số nguyên lớn, hãy bind số nguyên bằng setter tương ứng. Tránh ép kiểu cột trong điều kiện nếu không cần thiết:

```sql
-- Có thể cản trở việc dùng chỉ mục thông thường trên customer_id
WHERE CAST(customer_id AS VARCHAR(30)) = ?

-- Thường thuận lợi hơn nếu tham số được chuyển sang kiểu của cột
WHERE customer_id = ?
```

Khả năng dùng chỉ mục còn phụ thuộc hệ quản trị, collation, toán tử và biểu thức. Hãy xác nhận bằng kế hoạch thực thi thay vì suy luận chỉ từ hình thức SQL.

## 4. Tái sử dụng câu lệnh và kế hoạch thực thi

Có hai khái niệm thường bị nhầm lẫn:

- **Tái sử dụng prepared statement:** ứng dụng hoặc driver giữ cấu trúc câu lệnh đã chuẩn bị để gọi lại mà không phải dựng và gửi lại toàn bộ câu SQL.
- **Tái sử dụng execution plan:** hệ quản trị giữ kế hoạch đã tối ưu và dùng lại cho những lần thực thi tương thích.

Hai việc này có liên quan nhưng không đồng nghĩa. Một prepared statement có thể được chuẩn bị lại hoặc lập kế hoạch lại khi cần. Ngược lại, một hệ quản trị có thể cache kế hoạch cho câu SQL được gửi lặp lại dù ứng dụng không gọi API prepared statement tường minh.

Plan cache thường dùng thông tin nhận diện câu lệnh, kiểu tham số và một số ngữ cảnh thực thi. Khóa cache chính xác khác nhau giữa các hệ quản trị. Những yếu tố như nội dung SQL, kiểu dữ liệu, schema, quyền, session setting, phiên bản đối tượng hoặc thay đổi thống kê có thể ảnh hưởng việc một kế hoạch có được dùng lại hay phải biên dịch lại.

Việc tái sử dụng có lợi khi:

- Cùng một mẫu SQL được gọi nhiều lần.
- Chi phí parse/plan đáng kể so với thời gian thực thi.
- Phân bố tham số tương đối đồng nhất hoặc một kế hoạch chung phù hợp.
- Kế hoạch không bị vô hiệu hóa thường xuyên bởi thay đổi schema hoặc các điều kiện khác.

Việc tái sử dụng có thể ít lợi khi câu lệnh chỉ chạy một lần, truy vấn rất ngắn, cache bị churn, hoặc các giá trị tham số có độ chọn lọc khác nhau đến mức cần kế hoạch riêng.

## 5. Vì sao cùng một câu SQL có thể cần nhiều kế hoạch?

Bộ tối ưu thường dựa trên thống kê để ước lượng số dòng thỏa điều kiện. Thống kê có thể gồm số giá trị phân biệt, tần suất giá trị, histogram, tỷ lệ NULL và thông tin tương quan giữa các cột. Những ước lượng này ảnh hưởng lựa chọn giữa index scan, table scan, nested loop, hash join, merge join và các phương án khác.

Giả sử bảng `orders` có 50 triệu dòng. Một số khách hàng lớn tạo ra 20% tổng số đơn, trong khi phần lớn khách hàng chỉ có vài chục đơn. Câu lệnh:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?;
```

có thể có hai trường hợp:

- Với khách hàng nhỏ, chỉ mục trên `customer_id` có thể tìm được vài chục dòng rất nhanh.
- Với khách hàng lớn, truy vấn có thể trả về hàng triệu dòng; đọc tuần tự hoặc một kế hoạch khác có thể ít tốn kém hơn việc thực hiện rất nhiều lần tra cứu chỉ mục.

Nếu hệ quản trị chọn một kế hoạch dựa trên giá trị tham số đầu tiên rồi dùng lại cho mọi khách hàng, kế hoạch có thể tốt với nhóm này nhưng kém với nhóm kia. Đây là vấn đề độ nhạy theo tham số (parameter sensitivity).

Trong SQL Server, hiện tượng một kế hoạch bị ảnh hưởng mạnh bởi giá trị tham số dùng khi biên dịch thường được gọi là parameter sniffing. PostgreSQL có cơ chế lựa chọn giữa custom plan và generic plan cho prepared statement. Oracle có các cơ chế như bind peeking và adaptive cursor sharing. Tên gọi và hành vi cụ thể phụ thuộc hệ quản trị và phiên bản.

Không phải mọi khác biệt giữa các tham số đều cần nhiều kế hoạch. Nếu số dòng trả về và đường truy cập gần giống nhau, một kế hoạch dùng chung thường hiệu quả và tiết kiệm chi phí biên dịch.

## 6. Generic plan và custom plan

Đây là cách phân biệt hữu ích khi phân tích prepared statement:

- **Generic plan:** kế hoạch được xây dựng để dùng cho nhiều giá trị tham số. Bộ tối ưu không dựa vào một giá trị cụ thể ở từng lần chạy, hoặc dùng ước lượng chung cho tham số.
- **Custom plan:** kế hoạch được xây dựng dựa trên giá trị tham số của lần thực thi cụ thể, nên có thể tận dụng độ chọn lọc riêng của giá trị đó.

| Đặc điểm | Generic plan | Custom plan |
| --- | --- | --- |
| Chi phí lập kế hoạch | Có thể thấp hơn khi tái sử dụng nhiều lần | Có thể phát sinh mỗi lần hoặc theo từng lần cần lập kế hoạch |
| Khả năng thích ứng tham số | Một kế hoạch phải phù hợp với nhiều giá trị | Có thể tối ưu theo giá trị hiện tại |
| Phù hợp khi | Phân bố tham số tương đối đồng nhất | Độ chọn lọc thay đổi mạnh giữa các giá trị |
| Rủi ro | Kế hoạch thỏa hiệp có thể kém với nhóm cực trị | Chi phí lập kế hoạch tăng và có thể tạo nhiều kế hoạch |

Không có lựa chọn nào luôn tốt hơn. Một custom plan rất tốt cho truy vấn nặng có thể tốn thời gian lập kế hoạch đáng kể nếu truy vấn được gọi hàng chục nghìn lần mỗi giây. Một generic plan giảm chi phí biên dịch nhưng có thể chọn sai chiến lược truy cập cho một giá trị hiếm hoặc rất phổ biến.

### Ví dụ với PostgreSQL

Trong PostgreSQL, `PREPARE` tạo một prepared statement trong phiên làm việc:

```sql
PREPARE orders_by_customer(bigint) AS
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = $1;

EXPLAIN EXECUTE orders_by_customer(42);
```

`EXPLAIN EXECUTE` giúp xem kế hoạch được dùng cho lần gọi đó. Khi PostgreSQL sử dụng custom plan, biểu thức trong kế hoạch thường thể hiện giá trị tham số cụ thể; với generic plan, tham số có thể vẫn xuất hiện dưới dạng `$1`.

Để thử nghiệm có kiểm soát, PostgreSQL cung cấp `plan_cache_mode` ở các phiên bản hỗ trợ:

```sql
-- Ép lập kế hoạch theo giá trị của lần thực thi để so sánh
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE orders_by_customer(42);

-- Ép dùng kế hoạch chung để so sánh
SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE orders_by_customer(42);

DEALLOCATE orders_by_customer;
```

Đây là công cụ chẩn đoán và so sánh, không phải lời khuyên bật một chế độ cưỡng bức cho toàn hệ thống. Hãy kiểm tra tài liệu đúng phiên bản PostgreSQL đang dùng, đo nhiều giá trị đại diện và khôi phục cấu hình phù hợp sau thử nghiệm.

### Ví dụ với SQL Server

SQL Server có thể thực thi SQL tham số hóa bằng `sp_executesql`. Câu lệnh và khai báo kiểu tham số được truyền riêng:

```sql
EXEC sys.sp_executesql
    N'SELECT OrderId, CreatedAt, TotalAmount
      FROM dbo.Orders
      WHERE CustomerId = @customerId',
    N'@customerId bigint',
    @customerId = 42;
```

Kiểu tham số nên khớp kiểu cột. SQL Server có thể tái sử dụng kế hoạch cho câu lệnh tương thích, nhưng giá trị tham số ở thời điểm biên dịch và phân bố dữ liệu có thể ảnh hưởng chất lượng kế hoạch. Query Store, execution plan và các tính năng xử lý parameter-sensitive plan tùy phiên bản có thể hỗ trợ điều tra; hãy xác minh tính năng sẵn có trên phiên bản đang vận hành.

## 7. Nhận diện kế hoạch không phù hợp với tham số

Các dấu hiệu đáng điều tra gồm:

- Cùng query fingerprint nhưng thời gian thực thi khác nhau rất lớn theo tham số.
- Một số giá trị chạy nhanh, một số giá trị chậm dù câu SQL và cấu hình không đổi.
- Kế hoạch có ước lượng số dòng lệch xa số dòng thực tế.
- Kế hoạch dùng nested loop với số lần lặp rất lớn hoặc quét bảng khi một index seek có thể phù hợp.
- Một truy vấn có thời gian lập kế hoạch hoặc biên dịch cao so với thời gian thực thi.
- Kế hoạch thay đổi sau khi cập nhật thống kê, tạo chỉ mục hoặc thay đổi dữ liệu.
- Chỉ một kết nối hoặc một ứng dụng có độ trễ khác do session setting, kiểu tham số hoặc cache khác nhau.

Không nên kết luận parameter sniffing chỉ vì một truy vấn chậm. Cần loại trừ nguyên nhân như I/O tăng, cache lạnh, lock wait, network, connection pool, thay đổi dữ liệu, thống kê cũ hoặc tải đồng thời khác nhau.

### Phân tích ước lượng và số dòng thực tế

Khi đọc execution plan, tập trung vào các nút có chênh lệch lớn giữa estimated rows và actual rows. Sai lệch có thể khiến bộ tối ưu chọn thứ tự join hoặc thuật toán không phù hợp. Kiểm tra thêm:

- Điều kiện lọc có dùng đúng cột và kiểu dữ liệu không.
- Thống kê có đủ mới và đủ chi tiết cho phân bố dữ liệu không.
- Các cột có tương quan nhưng bộ tối ưu đang ước lượng độc lập không.
- Có implicit conversion hoặc biểu thức trên cột làm giảm khả năng dùng index không.
- Tham số thử nghiệm có đại diện cho nhóm phổ biến, hiếm và cực trị không.

## 8. Các cách xử lý khi kế hoạch phụ thuộc tham số

Chọn biện pháp dựa trên nguyên nhân đã xác nhận. Không nên cưỡng bức biên dịch lại hoặc tạo thêm chỉ mục chỉ vì một kế hoạch trông khác mong đợi.

### Cập nhật và cải thiện thống kê

Nếu ước lượng sai vì thống kê cũ hoặc thiếu thông tin về phân bố, hãy xem xét cập nhật thống kê, tăng độ chi tiết histogram hoặc dùng thống kê đa cột khi hệ quản trị hỗ trợ. Cần cân nhắc chi phí thu thập thống kê và tác động lên các truy vấn khác.

### Chia nhóm truy vấn theo nghiệp vụ

Nếu một số giá trị đại diện cho hai kiểu truy cập rất khác nhau, có thể thiết kế các nhánh truy vấn rõ ràng cho từng nhóm. Ví dụ, truy vấn khách hàng nhỏ và truy vấn báo cáo khách hàng lớn có thể cần cách phân trang hoặc tổng hợp khác nhau.

Tránh tạo quá nhiều biến thể SQL chỉ để né cache. Mỗi biến thể làm tăng độ phức tạp bảo trì và có thể tăng số kế hoạch trong cache.

### Dùng custom plan hoặc biên dịch lại có chọn lọc

Một số hệ quản trị cho phép yêu cầu lập kế hoạch lại hoặc biên dịch lại cho câu lệnh cụ thể. Cách này có thể cải thiện truy vấn có độ nhạy tham số cao, nhưng làm tăng CPU và thời gian lập kế hoạch. Hãy áp dụng theo phạm vi nhỏ và đo tổng chi phí.

### Dùng hint khi đã có bằng chứng

Optimizer hint hoặc query hint có thể giới hạn lựa chọn của bộ tối ưu. Đây là biện pháp đặc thù hệ quản trị, dễ trở nên lỗi thời khi dữ liệu và thống kê thay đổi. Chỉ dùng khi đã đo các phương án, hiểu rõ hệ quả và có quy trình xem xét lại.

### Thiết kế chỉ mục và câu SQL phù hợp

Chỉ mục có thể giúp một nhóm tham số nhưng gây chi phí ghi và dung lượng lưu trữ. Câu SQL có thể được viết lại để tách trường hợp đặc biệt, giảm số dòng trung gian hoặc tránh biểu thức không sargable. Mọi thay đổi cần kiểm chứng bằng cùng workload và phân bố tham số.

## 9. Các mẫu SQL dễ làm giảm hiệu quả kế hoạch

### Điều kiện tùy chọn dạng OR

Mẫu thường gặp:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = $1
  AND ($2 IS NULL OR status = $2);
```

Cách viết này tiện cho một API có bộ lọc tùy chọn, nhưng điều kiện `OR` có thể làm ước lượng và lựa chọn đường truy cập khó hơn, tùy hệ quản trị. Nếu hai trường hợp có hành vi khác nhau, có thể tạo hai mẫu câu lệnh rõ ràng: một mẫu chỉ lọc khách hàng và một mẫu lọc thêm trạng thái. Cần cân bằng lợi ích kế hoạch với số biến thể câu lệnh.

### Hàm hoặc ép kiểu trên cột

```sql
-- Hàm trên cột có thể khiến chỉ mục thông thường khó được sử dụng
WHERE LOWER(email) = $1;
```

Nếu truy vấn không thể đổi cách biểu diễn, cân nhắc chỉ mục biểu thức phù hợp và xác nhận hệ quản trị hỗ trợ. Một phương án khác là chuẩn hóa giá trị khi ghi và truy vấn theo cột đã chuẩn hóa. Không thay đổi ngữ nghĩa so sánh hoặc collation chỉ để ép dùng chỉ mục.

### LIKE và wildcard đầu chuỗi

`LIKE 'abc%'` có thể tận dụng một số loại chỉ mục tùy collation và hệ quản trị; `LIKE '%abc'` thường không dùng được B-tree thông thường để tìm theo tiền tố. Tham số hóa không thay đổi đặc tính này. Với tìm kiếm chứa chuỗi, cần cân nhắc full-text, trigram hoặc cơ chế tìm kiếm phù hợp.

### Danh sách IN có độ dài thay đổi

Việc tạo SQL khác nhau cho mỗi độ dài danh sách `IN` có thể làm giảm khả năng tái sử dụng statement hoặc plan. Một số hệ quản trị hỗ trợ array parameter, table-valued parameter hoặc bảng tạm. Hãy chọn cách phù hợp với driver và hệ quản trị, đồng thời đo chi phí truyền dữ liệu và ước lượng số dòng.

## 10. Prepared statement và connection pool

Prepared statement có thể gắn với phiên làm việc hoặc kết nối. Khi ứng dụng dùng connection pool, các lần gọi liên tiếp có thể đi qua những kết nối khác nhau. Nếu statement chỉ tồn tại trong một session, việc chuyển kết nối có thể khiến ứng dụng phải chuẩn bị lại.

Cần kiểm tra:

- Driver có cache prepared statement ở phía client hay không.
- Prepared statement được đặt tên và giữ trong phạm vi session nào.
- Pool dùng kết nối cố định, transaction pooling hay cơ chế multiplexing.
- Proxy hoặc connection pooler có hỗ trợ prepared statement theo giao thức đang dùng không.
- Statement có được đóng hoặc deallocate đúng lúc để tránh giữ tài nguyên không.
- Schema migration hoặc thay đổi kiểu dữ liệu có làm statement cần prepare lại không.

Không nên giả định prepared statement tồn tại xuyên suốt mọi kết nối chỉ vì ứng dụng gọi `prepareStatement`. Hành vi cụ thể phụ thuộc driver, pool, proxy và hệ quản trị. Hãy đo số lần prepare, thời gian prepare, cache hit/miss nếu có và số kế hoạch bị biên dịch lại.

## 11. Quy trình đo và lựa chọn chiến lược

1. **Chọn query fingerprint và workload.** Xác định câu SQL được gọi thường xuyên, nhóm tham số phổ biến/hiếm và mục tiêu cần cải thiện.
2. **Thu thập đường cơ sở.** Ghi số lần gọi, tổng thời gian, thời gian trung bình và phân vị độ trễ nếu có; tách thời gian lập kế hoạch, thực thi và chờ tài nguyên khi công cụ hỗ trợ.
3. **Chọn bộ tham số đại diện.** Bao gồm giá trị có độ chọn lọc cao, thấp, giá trị phổ biến, hiếm, NULL và biên nghiệp vụ.
4. **Đọc kế hoạch thực thi.** So sánh estimated rows, actual rows, loại scan, join, sort, số block đọc và bộ nhớ sử dụng.
5. **So sánh kế hoạch theo tham số.** Kiểm tra generic/custom hoặc các lần biên dịch khác nhau; xác định nhóm tham số nào bị ảnh hưởng.
6. **Kiểm tra kiểu dữ liệu và thống kê.** Tìm implicit conversion, thống kê cũ, cardinality sai và tương quan cột chưa được mô tả.
7. **Thử một thay đổi có kiểm soát.** Điều chỉnh thống kê, câu SQL, chỉ mục hoặc chiến lược kế hoạch; ghi lại cấu hình và lý do.
8. **Đo lại trong điều kiện tương đương.** Dùng cùng dữ liệu, tốc độ đến, concurrency, trạng thái cache và phân bố tham số.
9. **Đánh giá toàn workload.** So sánh throughput, p50/p95/p99, CPU, I/O, thời gian lập kế hoạch, dung lượng cache và hiệu năng các truy vấn khác.
10. **Theo dõi sau triển khai.** Quan sát plan regression, cache churn và thay đổi phân bố dữ liệu theo thời gian.

Ví dụ ma trận kiểm thử:

| Nhóm tham số | Đặc điểm | Câu hỏi cần trả lời |
| --- | --- | --- |
| Giá trị phổ biến | Xuất hiện thường xuyên, độ chọn lọc trung bình | Kế hoạch có hiệu quả với phần lớn tải không? |
| Giá trị hiếm | Ít dòng phù hợp | Có thể dùng index seek hoặc nested loop hiệu quả không? |
| Giá trị rất phổ biến | Trả về nhiều dòng | Có cần scan hoặc kế hoạch join khác không? |
| NULL hoặc bộ lọc bỏ trống | Nhánh điều kiện tùy chọn | Câu SQL có làm bộ tối ưu ước lượng sai hoặc mất khả năng dùng chỉ mục không? |
| Giá trị biên | Khoảng ngày, tenant lớn nhất, danh sách dài | Có thay đổi mạnh số dòng và mức tài nguyên không? |

## 12. Những sai lầm thường gặp

- **Cho rằng prepared statement luôn nhanh hơn.** Với truy vấn chạy một lần hoặc cần kế hoạch riêng theo tham số, chi phí chuẩn bị và kế hoạch chung có thể không có lợi.
- **Cho rằng một câu SQL chỉ có một kế hoạch tốt.** Phân bố dữ liệu lệch có thể khiến các nhóm tham số cần chiến lược truy cập khác nhau.
- **Dùng tham số sai kiểu.** Implicit conversion có thể ảnh hưởng ước lượng và khả năng sử dụng chỉ mục.
- **Ghép chuỗi để thay tên cột từ đầu vào.** Tham số không bind được identifier; phải dùng allowlist cho phần cú pháp động.
- **Cưỡng bức recompile mọi lần.** Chi phí biên dịch có thể trở thành nút thắt CPU.
- **Thêm hint khi chưa đo.** Hint có thể khóa hệ thống vào một kế hoạch kém khi dữ liệu thay đổi.
- **Đánh giá bằng một giá trị tham số.** Cần kiểm tra nhiều nhóm giá trị và cả phân bố tham số trong workload.
- **Bỏ qua connection pool.** Statement có thể chỉ tồn tại trên một kết nối hoặc session cụ thể.
- **Chỉ nhìn thời gian thực thi.** Cần xem thời gian lập kế hoạch, lock wait, I/O, số dòng thực tế và chi phí tổng.

## 13. Danh sách kiểm tra khi triển khai

- [ ] Giá trị đầu vào được bind bằng API tham số hóa.
- [ ] Tên bảng, tên cột và hướng sắp xếp động chỉ lấy từ allowlist.
- [ ] Kiểu tham số tương thích với kiểu cột.
- [ ] Đã xác định phạm vi sống và cache của prepared statement.
- [ ] Đã kiểm tra driver, connection pool và proxy có hỗ trợ cơ chế prepare đang dùng.
- [ ] Đã đo chi phí parse/plan và mức độ tái sử dụng.
- [ ] Đã kiểm tra độ nhạy theo các nhóm tham số phổ biến, hiếm và cực trị.
- [ ] Đã so sánh estimated rows với actual rows và kiểm tra chất lượng thống kê.
- [ ] Đã đánh giá generic/custom plan hoặc cơ chế tương đương của hệ quản trị.
- [ ] Thay đổi hint, recompile, SQL hoặc chỉ mục có bằng chứng đo lường.
- [ ] Đã kiểm tra throughput, p95/p99, CPU, I/O và truy vấn liên quan sau thay đổi.
- [ ] Có kế hoạch theo dõi plan regression và cập nhật khi phân bố dữ liệu đổi.

## Kết luận

Prepared statement và tham số hóa giúp tách dữ liệu khỏi cấu trúc SQL, tăng an toàn và có thể giảm chi phí chuẩn bị khi câu lệnh được gọi lặp lại. Tuy nhiên, tái sử dụng statement không đồng nghĩa một execution plan luôn phù hợp với mọi tham số. Bộ tối ưu vẫn phụ thuộc thống kê, độ chọn lọc và phân bố dữ liệu; các giá trị lệch mạnh có thể cần custom plan hoặc cách tổ chức truy vấn khác. Hãy kiểm tra kiểu dữ liệu, phạm vi cache, connection pool và kế hoạch thực thi theo nhiều nhóm tham số, sau đó đo lại trên workload đại diện để lựa chọn chiến lược có hiệu năng tốt cho toàn hệ thống.
