# Kế hoạch lưu lại, biên dịch lại và chi phí lập kế hoạch

## Mục tiêu bài học

Trước khi thực thi một câu SQL, hệ quản trị cơ sở dữ liệu phải hiểu cú pháp, xác định đối tượng dữ liệu, đánh giá các cách truy cập và chọn một kế hoạch thực thi. Công việc này có chi phí CPU và bộ nhớ. Để giảm chi phí lặp lại, nhiều hệ quản trị lưu kế hoạch đã tạo và tái sử dụng khi câu lệnh được thực hiện lần sau. Tuy nhiên, một kế hoạch được lưu lại có thể không còn phù hợp với dữ liệu, thống kê hoặc giá trị tham số hiện tại. Khi đó, hệ quản trị có thể tự biên dịch lại hoặc cần được hướng dẫn để tạo kế hoạch khác.

Trong chương **Bộ tối ưu truy vấn** của module **DATABASE_PERFORMANCE**, bài học này giải thích cách hoạt động của plan cache, nguyên nhân kế hoạch bị vô hiệu hóa, sự đánh đổi giữa tái sử dụng và biên dịch lại, cũng như cách đo chi phí lập kế hoạch. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy cần đánh giá cả thời gian lập kế hoạch lẫn thời gian thực thi trước khi thay đổi cấu hình hoặc SQL.

Sau bài học, bạn có thể:

- Mô tả các giai đoạn chính từ câu SQL đến kế hoạch thực thi.
- Phân biệt cache kế hoạch với cache dữ liệu và kết quả truy vấn.
- Giải thích khi nào một kế hoạch có thể được tái sử dụng, bị vô hiệu hóa hoặc được biên dịch lại.
- Nhận diện rủi ro kế hoạch không phù hợp với giá trị tham số và phân bố dữ liệu.
- Đo chi phí parse/compile/plan, thời gian thực thi và mức độ tái sử dụng kế hoạch.
- Chọn cách xử lý phù hợp giữa tái sử dụng kế hoạch, tham số hóa câu lệnh và biên dịch lại có chọn lọc.

## 1. Từ câu SQL đến kế hoạch thực thi

Khi nhận một câu SQL, hệ quản trị thường thực hiện một số công việc logic sau. Tên gọi và thứ tự chi tiết khác nhau giữa các sản phẩm, nhưng ý tưởng chung tương tự:

1. **Phân tích cú pháp (parse):** kiểm tra câu lệnh có đúng ngữ pháp SQL hay không và tạo cấu trúc nội bộ biểu diễn câu lệnh.
2. **Phân giải tên và kiểm tra ngữ nghĩa:** xác định bảng, cột, hàm, kiểu dữ liệu, quyền truy cập và các đối tượng được tham chiếu.
3. **Viết lại truy vấn (rewrite):** áp dụng các quy tắc biến đổi, mở rộng view hoặc chuẩn hóa biểu thức theo cơ chế của hệ quản trị.
4. **Tối ưu hóa (optimization/planning):** xem xét các đường truy cập, chỉ mục, thứ tự nối, thuật toán join, cách sắp xếp và tổng hợp; ước lượng chi phí dựa trên thống kê và mô hình chi phí.
5. **Tạo kế hoạch thực thi:** tạo cấu trúc mà execution engine có thể sử dụng để đọc, lọc, nối, cập nhật và trả dữ liệu.

Các giai đoạn trên có thể được gộp hoặc lặp lại trong nội bộ engine. Điều quan trọng đối với người tối ưu là phân biệt **chi phí tạo kế hoạch** với **chi phí chạy kế hoạch**. Một câu lệnh có thể lập kế hoạch rất nhanh nhưng thực thi chậm vì quét nhiều dữ liệu; câu lệnh khác có thể thực thi nhanh nhưng tốn tỷ lệ đáng kể thời gian để phân tích và tối ưu do được gọi hàng chục nghìn lần với cấu trúc SQL thay đổi liên tục.

### 1.1. Chi phí lập kế hoạch và chi phí thực thi

| Thành phần | Bao gồm | Câu hỏi chẩn đoán |
|---|---|---|
| Parse/compile/plan | Phân tích câu lệnh, kiểm tra đối tượng, tối ưu và tạo kế hoạch | Mỗi lần gọi có phải tạo lại kế hoạch không? SQL có quá nhiều biến thể không? |
| Execution | Đọc/ghi dữ liệu, lọc, join, sort, aggregate, gửi kết quả | Kế hoạch có truy cập quá nhiều dòng hoặc dùng tài nguyên không hiệu quả không? |
| Wait time | Chờ khóa, I/O, log, bộ nhớ, mạng hoặc tài nguyên khác trong khi xử lý | Phiên đang chờ điều gì và ai hoặc tài nguyên nào gây chờ? |
| Client/application | Chờ ứng dụng gửi tham số, nhận kết quả hoặc xử lý dữ liệu | Thời gian đo ở ứng dụng có bao gồm thời gian ngoài cơ sở dữ liệu không? |

Không được lấy tổng thời gian ở ứng dụng rồi xem đó là thời gian lập kế hoạch. Cũng không nên xem trường `cost` trong một kế hoạch là số mili giây thực tế. Cost là giá trị ước lượng theo mô hình của bộ tối ưu, chủ yếu hữu ích để so sánh các phương án trong cùng ngữ cảnh.

### 1.2. Hard parse, soft parse và cách gọi theo từng hệ quản trị

Một số hệ quản trị, đặc biệt trong tài liệu Oracle, dùng các thuật ngữ **hard parse** và **soft parse**:

- Hard parse thường chỉ việc phải phân tích và tối ưu câu lệnh để tạo một cursor/kế hoạch mới, với chi phí cao hơn.
- Soft parse thường chỉ việc tìm được cursor phù hợp để tái sử dụng, nên tránh được phần lớn công việc tối ưu lại.

Các hệ quản trị khác có thuật ngữ và cơ chế riêng. SQL Server nói về plan cache và compile/recompile; PostgreSQL có prepared statements với custom plan hoặc generic plan; MySQL có prepared statement và cơ chế chuẩn bị lại khi metadata phụ thuộc thay đổi. Không nên mặc định rằng một tên gọi hoặc quy tắc cache của sản phẩm này áp dụng nguyên xi cho sản phẩm khác.

## 2. Kế hoạch được lưu lại để làm gì?

Plan cache lưu thông tin cần thiết để hệ quản trị có thể tái sử dụng kế hoạch của một câu lệnh khi điều kiện phù hợp. Nhờ đó, hệ quản trị giảm công việc parse, kiểm tra và tối ưu lặp đi lặp lại. Lợi ích thường rõ với workload OLTP có nhiều câu lệnh ngắn, được gọi thường xuyên và có cấu trúc ổn định.

Ví dụ, một ứng dụng gọi truy vấn lấy đơn hàng theo mã khách hàng hàng nghìn lần mỗi phút. Nếu mỗi lần gửi một chuỗi SQL khác nhau chỉ vì giá trị `customer_id` được ghép trực tiếp vào văn bản, engine có thể phải xử lý nhiều biến thể câu lệnh. Dùng tham số giúp giữ cấu trúc SQL ổn định và tạo cơ hội tái sử dụng kế hoạch hoặc prepared statement.

```sql
-- Mẫu không nên tạo bằng cách ghép giá trị vào chuỗi SQL:
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 101;

-- Cấu trúc tham số hóa (placeholder cụ thể tùy driver/hệ quản trị):
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = ?;
```

Đoạn thứ hai là minh họa placeholder phổ biến ở tầng driver. Cú pháp thực tế có thể là `$1` trong PostgreSQL, `@CustomerId` trong SQL Server hoặc placeholder do thư viện kết nối hỗ trợ. Ứng dụng nên truyền giá trị qua API tham số của driver thay vì tự nối chuỗi. Tham số hóa cũng giúp giảm nguy cơ SQL injection và tăng khả năng tái sử dụng câu lệnh.

### 2.1. Plan cache không phải result cache

Hai loại cache thường bị nhầm lẫn:

| Loại cache | Lưu gì? | Khi tái sử dụng |
|---|---|---|
| Plan cache | Kế hoạch hoặc cấu trúc thực thi của câu SQL | Engine vẫn đọc dữ liệu và tính kết quả theo trạng thái dữ liệu hiện tại |
| Data/buffer cache | Trang dữ liệu hoặc khối dữ liệu đã đọc từ lưu trữ | Engine có thể lấy trang từ bộ nhớ thay vì đọc lại từ thiết bị |
| Result/query cache (nếu sản phẩm có hỗ trợ) | Kết quả của một truy vấn theo cơ chế và điều kiện cụ thể | Có thể trả kết quả đã lưu khi điều kiện hợp lệ; nhiều engine không cung cấp cache kết quả tổng quát |

Tái sử dụng kế hoạch không có nghĩa là tái sử dụng kết quả cũ. Nếu một đơn hàng vừa đổi trạng thái, câu truy vấn được thực hiện bằng kế hoạch cache vẫn phải đọc dữ liệu phù hợp với cơ chế nhất quán của transaction hiện tại.

### 2.2. Điều kiện nhận diện một kế hoạch có thể tái sử dụng

Engine cần xác định câu lệnh mới có tương thích với mục cache hiện có hay không. Tùy sản phẩm, các yếu tố có thể bao gồm:

- Nội dung câu SQL hoặc dạng biểu diễn đã chuẩn hóa.
- Kiểu và cách truyền tham số.
- Database, schema, chủ sở hữu và ngữ cảnh phân giải tên.
- Quyền truy cập và các đối tượng phụ thuộc.
- Thiết lập phiên ảnh hưởng đến ngữ nghĩa hoặc cách tối ưu.
- Phiên bản schema, chỉ mục, thống kê hoặc metadata liên quan.

Vì vậy, chỉ thay một giá trị tham số không nhất thiết làm kế hoạch cache mất hiệu lực; ngược lại, hai câu SQL nhìn giống nhau cũng chưa chắc dùng chung một kế hoạch nếu ngữ cảnh hoặc kiểu tham số khác nhau. Quy tắc chính xác cần tra theo hệ quản trị và phiên bản đang triển khai.

## 3. Khi nào kế hoạch bị vô hiệu hóa hoặc biên dịch lại?

Kế hoạch được tạo dựa trên một tập giả định về cấu trúc dữ liệu, thống kê, chỉ mục, tham số và môi trường thực thi. Khi các giả định quan trọng thay đổi, kế hoạch cũ có thể không còn hợp lệ hoặc không còn đáng tin cậy. Engine có thể đánh dấu kế hoạch không hợp lệ, tự lập kế hoạch lại ở lần chạy tiếp theo, hoặc tạo một phiên bản kế hoạch mới.

Các nguyên nhân thường gặp gồm:

1. **Thay đổi schema hoặc đối tượng phụ thuộc:** thêm/xóa/đổi cột, thay đổi bảng, view, hàm hoặc đối tượng mà câu SQL tham chiếu.
2. **Thay đổi chỉ mục:** tạo, xóa hoặc thay đổi chỉ mục có thể làm thay đổi tập đường truy cập mà bộ tối ưu cân nhắc.
3. **Thống kê thay đổi:** cập nhật thống kê hoặc phân bố dữ liệu thay đổi đáng kể có thể khiến kế hoạch cần được đánh giá lại.
4. **Thay đổi ngữ cảnh hoặc thiết lập:** một số tùy chọn phiên, quyền, schema hoặc tham số cấu hình có thể ảnh hưởng khả năng tái sử dụng.
5. **Cơ chế nội bộ của engine:** cache bị thu hồi do áp lực bộ nhớ, phiên bản kế hoạch mới được tạo, hoặc prepared statement phải được chuẩn bị lại sau thay đổi metadata.

Không phải mọi thay đổi dữ liệu đều bắt buộc biên dịch lại. Nếu mỗi lần `INSERT` đều khiến toàn bộ kế hoạch phụ thuộc vào bảng bị biên dịch lại thì plan cache gần như không còn giá trị. Engine thường phân biệt thay đổi nội dung dữ liệu với thay đổi metadata hoặc thống kê có ảnh hưởng tới kế hoạch. Cách đánh giá và ngưỡng invalidation khác nhau theo sản phẩm.

### 3.1. Biên dịch lại có chi phí

Biên dịch lại có thể tạo kế hoạch phù hợp hơn, nhưng cũng tiêu thụ CPU và thời gian. Nếu một câu SQL ngắn được gọi với tần suất rất cao và luôn bị recompile, chi phí lập kế hoạch cộng dồn có thể đáng kể. Trong hệ thống nhiều phiên, việc nhiều câu lệnh cùng compile có thể tạo CPU spike hoặc tranh chấp trong các cấu trúc quản lý cache.

Ngược lại, cố giữ một kế hoạch quá lâu dù thống kê hoặc điều kiện truy cập đã thay đổi có thể làm tăng thời gian thực thi. Cần cân bằng hai loại chi phí:

\[
T_{total} = T_{planning} + T_{execution} + T_{waiting}
\]

Đây là cách phân rã khái niệm để tư duy. Số liệu thực tế của hệ quản trị có thể tính hoặc báo cáo các thành phần theo cách khác nhau; thời gian ứng dụng còn có thể bao gồm network và xử lý ở client.

## 4. Kế hoạch nhạy cảm với tham số

Một nguyên nhân quan trọng khiến kế hoạch được tái sử dụng nhưng hiệu năng thay đổi là **parameter sensitivity**: các giá trị tham số khác nhau có thể chọn ra lượng dữ liệu rất khác nhau.

Giả sử bảng `orders` có 100 triệu dòng. Phần lớn khách hàng chỉ có vài chục đơn hàng, nhưng một khách hàng lớn có vài triệu đơn. Truy vấn sau dùng cùng cấu trúc nhưng độ chọn lọc của tham số khác biệt:

```sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :customer_id;
```

Với khách hàng nhỏ, dùng index seek/lookup rồi đọc một số ít dòng có thể hiệu quả. Với khách hàng rất lớn, một kế hoạch đọc tuần tự hoặc cách truy cập khác có thể rẻ hơn. Nếu engine chọn kế hoạch dựa trên một giá trị tham số rồi tái sử dụng cho mọi giá trị, một số lần gọi có thể chậm bất thường.

### 4.1. Parameter sniffing và plan reuse

Một số engine sử dụng giá trị tham số tại thời điểm compile để ước lượng số dòng và chọn kế hoạch. Trong SQL Server, hành vi này thường được gọi là parameter sniffing. Nếu lần compile đầu tiên gặp giá trị rất hiếm, kế hoạch có thể tối ưu cho ít dòng; sau đó cùng kế hoạch được dùng cho giá trị phổ biến và xử lý nhiều dòng hơn dự kiến. Trường hợp ngược lại cũng có thể xảy ra.

Không nên mặc định parameter sniffing luôn xấu. Khi phân bố dữ liệu tương đối đồng đều hoặc workload có mẫu tham số ổn định, dùng giá trị tham số để tối ưu thường giúp kế hoạch tốt hơn. Vấn đề xuất hiện khi độ chọn lọc biến thiên lớn nhưng chỉ một kế hoạch được dùng cho mọi trường hợp.

### 4.2. Cách nhận diện

- So sánh thời gian thực thi của cùng câu SQL với các nhóm giá trị tham số khác nhau.
- Xem kế hoạch thực tế, số dòng ước lượng và số dòng thực tế ở từng toán tử.
- Kiểm tra lịch sử kế hoạch để xác định thời điểm thay đổi kế hoạch trùng với lúc hiệu năng xấu đi.
- Đối chiếu thống kê và histogram của cột lọc, độ lệch phân bố, số lượng giá trị phân biệt và tương quan giữa các cột.
- Xem liệu một kế hoạch có được dùng cho nhiều nhóm tham số có độ chọn lọc khác nhau hay không.

Không kết luận chỉ từ một lần chạy chậm. Cache dữ liệu, mức tải đồng thời, khóa, I/O và các yếu tố ngoài kế hoạch có thể làm cùng một SQL có thời gian thực thi khác nhau.

## 5. Các cách xử lý và sự đánh đổi

Không có một chính sách cache hoặc recompile phù hợp cho mọi workload. Lựa chọn cần dựa trên bằng chứng và phạm vi ảnh hưởng.

| Cách xử lý | Khi có thể hữu ích | Chi phí/rủi ro cần xem |
|---|---|---|
| Tham số hóa SQL | Nhiều câu lệnh chỉ khác giá trị literal; muốn giảm biến thể SQL và tận dụng prepared statement/plan cache | Kiểu tham số, schema context và phân bố dữ liệu vẫn có thể ảnh hưởng kế hoạch |
| Tái sử dụng kế hoạch | Cấu trúc truy vấn ổn định, kế hoạch tốt trên các nhóm tham số chính | Một kế hoạch duy nhất có thể không phù hợp với mọi độ chọn lọc |
| Biên dịch lại có chọn lọc | Tham số thay đổi mạnh hoặc kế hoạch cache đã lỗi thời và cần tối ưu theo giá trị hiện tại | Tăng CPU và latency lập kế hoạch; có thể gây compile storm nếu áp dụng rộng |
| Tách câu truy vấn theo nhóm nghiệp vụ | Có các nhóm tham số với hành vi dữ liệu rất khác nhau | Tăng số câu lệnh và chi phí bảo trì; phải xác định ngưỡng phân nhóm hợp lý |
| Cải thiện thống kê | Ước lượng số dòng sai do thống kê cũ, thiếu hoặc không mô tả đúng phân bố | Thu thập thống kê có chi phí và có thể làm thay đổi kế hoạch nhiều truy vấn |
| Điều chỉnh index hoặc mô hình dữ liệu | Đường truy cập hiện tại không phù hợp workload | Tăng dung lượng, chi phí ghi, bảo trì và có thể ảnh hưởng kế hoạch khác |

### 5.1. Tham số hóa trước khi nghĩ tới xóa cache

Nếu ứng dụng tạo SQL bằng cách ghép giá trị vào chuỗi, có thể sinh ra nhiều câu lệnh gần giống nhau:

```sql
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 102;
SELECT * FROM orders WHERE customer_id = 103;
```

Tham số hóa giúp giữ câu lệnh ổn định:

```sql
SELECT *
FROM orders
WHERE customer_id = @CustomerId;
```

Tên placeholder trên minh họa kiểu SQL Server. Ở ứng dụng, cần dùng prepared statement hoặc API parameter binding của driver. Không nên thay tham số bằng cách nối chuỗi thủ công.

Tham số hóa có thể tăng khả năng dùng lại kế hoạch nhưng cũng làm rõ bài toán parameter sensitivity. Vì vậy, sau khi tham số hóa, hãy kiểm tra kế hoạch với các nhóm tham số đại diện thay vì cho rằng reuse chắc chắn làm mọi lần chạy nhanh hơn.

### 5.2. Recompile theo câu lệnh thay vì toàn hệ thống

Khi đã xác định một câu SQL có kế hoạch không phù hợp do tham số biến thiên, một số hệ quản trị cung cấp tùy chọn recompile ở phạm vi câu lệnh hoặc thủ tục. Ví dụ trong SQL Server:

```sql
SELECT order_id, created_at, status
FROM dbo.Orders
WHERE customer_id = @CustomerId
OPTION (RECOMPILE);
```

Tùy chọn này yêu cầu biên dịch lại câu lệnh cho lần thực thi, cho phép optimizer cân nhắc giá trị tham số hiện tại. Nó có thể cải thiện truy vấn nhạy tham số, nhưng thêm chi phí compile cho mỗi lần gọi. Chỉ nên dùng sau khi đo và so sánh tổng thời gian compile cộng execution trên tải đại diện.

Các hệ quản trị khác có cơ chế tương đương hoặc khác biệt. Ví dụ PostgreSQL cho phép điều khiển lựa chọn custom/generic plan cho prepared statement bằng `plan_cache_mode` trong các phiên bản hỗ trợ. Không chuyển cú pháp hoặc giả định của SQL Server sang PostgreSQL, MySQL hay Oracle.

### 5.3. Tránh xóa toàn bộ plan cache như một biện pháp thường trực

Xóa cache toàn hệ thống có thể làm mất các kế hoạch đang được tái sử dụng. Sau thao tác, nhiều truy vấn phải parse/compile lại, tạo thêm tải CPU và độ trễ trong giai đoạn cache được làm nóng. Nó cũng làm mất bối cảnh cần thiết để xác định kế hoạch nào thực sự gây vấn đề.

Nếu cần xử lý kế hoạch xấu, ưu tiên xác định câu SQL hoặc plan cụ thể, xem lịch sử và dùng cơ chế kiểm soát có phạm vi nhỏ nhất mà hệ quản trị hỗ trợ. Chỉ thực hiện thao tác ảnh hưởng diện rộng theo quy trình vận hành và sau khi đánh giá tác động.

## 6. Ví dụ quan sát prepared plan trong PostgreSQL

PostgreSQL hỗ trợ prepared statement trong một session. Ví dụ:

```sql
PREPARE orders_by_customer(bigint) AS
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = $1;

EXPLAIN EXECUTE orders_by_customer(42);
```

Kế hoạch của prepared statement có thể là **custom plan** (được lập kế hoạch dựa trên giá trị tham số cụ thể) hoặc **generic plan** (không phụ thuộc một giá trị cụ thể). Ở các phiên bản PostgreSQL có `plan_cache_mode`, có thể thử so sánh hai chế độ trong môi trường kiểm thử:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE orders_by_customer(42);

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE orders_by_customer(42);
```

Hãy lặp lại với các giá trị đại diện cho nhóm khách hàng nhỏ và lớn. So sánh cấu trúc kế hoạch, số dòng ước lượng, chỉ mục được chọn và thời gian thực thi. Chế độ `force_custom_plan` có thể tăng chi phí lập kế hoạch; `force_generic_plan` có thể dùng một kế hoạch không tối ưu cho một số tham số. Không nên đặt chế độ ép buộc toàn cục chỉ từ một truy vấn thử.

`EXPLAIN` thông thường hiển thị kế hoạch và cost ước lượng nhưng không thực thi truy vấn. Để đo thời gian chạy và số dòng thực tế, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn đọc trong môi trường kiểm thử:

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_customer(42);
```

`ANALYZE` thực sự thực thi câu lệnh. Với `UPDATE`, `DELETE` hoặc câu lệnh có tác dụng phụ, phải kiểm soát transaction và dữ liệu thử cẩn thận; không chạy tùy tiện trên production. Thời gian `Planning Time` và `Execution Time` trong kết quả giúp tách hai thành phần trong phạm vi đo của PostgreSQL.

Sau khi hoàn tất so sánh, giải phóng prepared statement và trả cấu hình phiên về mặc định:

```sql
DEALLOCATE orders_by_customer;
RESET plan_cache_mode;
```

## 7. Ví dụ đo compile và execution trong SQL Server

SQL Server cung cấp `SET STATISTICS TIME ON` để hiển thị thời gian parse/compile và thời gian thực thi trong Messages:

```sql
SET STATISTICS TIME ON;

DECLARE @CustomerId int = 42;

SELECT order_id, created_at, status
FROM dbo.Orders
WHERE customer_id = @CustomerId;

SET STATISTICS TIME OFF;
```

Để quan sát lịch sử hiệu năng, có thể kết hợp Query Store (nếu đã bật và cấu hình phù hợp), execution plan thực tế, và các DMV như `sys.dm_exec_query_stats` hoặc `sys.dm_exec_cached_plans`. Các DMV thường phản ánh cache hiện tại hoặc số liệu tích lũy kể từ khi kế hoạch được đưa vào cache; chúng không thay thế hệ thống giám sát lịch sử dài hạn. Quyền xem DMV phụ thuộc phiên bản và quyền máy chủ.

Khi đánh giá một truy vấn, ghi nhận riêng compile time, execution CPU/time, logical reads, physical reads, số lần thực thi và plan handle. Một câu lệnh compile nhanh nhưng có hàng triệu logical reads cần tối ưu execution; một câu lệnh chạy rất nhanh nhưng compile mỗi lần với tần suất cao có thể cần xem lại cách gọi và tái sử dụng.

## 8. Đo lường và quy trình chẩn đoán

Áp dụng quy trình sau khi một truy vấn có biểu hiện chậm hoặc chi phí lập kế hoạch tăng:

**Bước 1 — Xác định workload.** Ghi nhận câu SQL, tần suất gọi, số biến thể, kiểu tham số, nhóm giá trị thường gặp, mức đồng thời và SLA. Xác định truy vấn thuộc OLTP, OLAP hay tải hỗn hợp.

**Bước 2 — Tách thời gian.** Thu thập parse/compile/plan time, execution time, CPU time, wait time và thời gian ở tầng ứng dụng theo công cụ của engine. Kiểm tra metric là trung bình, tổng tích lũy hay phân vị.

**Bước 3 — Xác định mức tái sử dụng.** Kiểm tra số lần compile/recompile, cache hit hoặc số lần thực thi trên một kế hoạch nếu engine cung cấp. Tìm các biến thể SQL do literal, khác kiểu tham số hoặc khác ngữ cảnh.

**Bước 4 — So sánh kế hoạch theo tham số.** Chạy với các giá trị đại diện cho dữ liệu ít, trung bình và nhiều. Đối chiếu estimated rows với actual rows, đường truy cập, join strategy, sort/hash, số trang đọc và mức tiêu thụ tài nguyên.

**Bước 5 — Kiểm tra lý do invalidation.** Đối chiếu thời điểm recompile với thay đổi schema, index, statistics, cấu hình, quyền hoặc sự kiện cache eviction. Không suy đoán từ một lần compile mới.

**Bước 6 — Thử một thay đổi có kiểm soát.** Có thể tham số hóa, cập nhật thống kê phù hợp, điều chỉnh SQL/index hoặc thử recompile có phạm vi nhỏ. Chỉ thay một yếu tố mỗi lần để dễ xác định tác động.

**Bước 7 — Đo lại trong cùng điều kiện.** So sánh tổng chi phí lập kế hoạch và thực thi, p95/p99, CPU, logical/physical reads, wait events, thông lượng và tác động tới các câu lệnh khác. Lặp lại đủ số lần để tránh kết luận từ một mẫu nhiễu.

### 8.1. Bảng diễn giải một số dấu hiệu

| Dấu hiệu | Khả năng cần kiểm tra | Hướng điều tra tiếp |
|---|---|---|
| Compile time cao, execution ngắn | SQL phức tạp, quá nhiều biến thể, compile/recompile liên tục | Đếm lần compile, kiểm tra tham số hóa, cache churn và số lần gọi |
| Compile time thấp, execution cao | Kế hoạch truy cập dữ liệu kém, thống kê sai, I/O hoặc blocking | Xem actual plan, estimated/actual rows, buffers, wait events |
| Cùng SQL có lúc nhanh, lúc rất chậm theo tham số | Parameter sensitivity hoặc khác biệt cache/tải | So sánh kế hoạch và nhóm tham số; loại trừ blocking, cache và tải nền |
| Recompile tăng sau DDL hoặc cập nhật thống kê | Kế hoạch phụ thuộc bị invalidation hoặc thay đổi ước lượng | Đối chiếu lịch sử thay đổi và kế hoạch mới |
| Nhiều kế hoạch gần giống nhau trong cache | SQL text/context khác nhau hoặc nhiều phiên bản kế hoạch | Xem nguyên nhân phân mảnh cache; không xóa cache ngay |
| Sau khi xóa cache, CPU và latency tăng | Nhiều truy vấn phải compile lại và cache đang warm-up | Khôi phục theo cơ chế tự nhiên, theo dõi compile rate và tải |

## 9. Những nhầm lẫn thường gặp

- **“Plan cache lưu kết quả truy vấn.”** Thông thường nó lưu kế hoạch; dữ liệu vẫn được đọc và đánh giá theo trạng thái hiện tại.
- **“Câu SQL giống nhau luôn dùng cùng một kế hoạch.”** Ngữ cảnh, kiểu tham số, quyền, schema, thiết lập và cơ chế của engine có thể khiến cache entry khác nhau.
- **“Biên dịch lại luôn tốt hơn.”** Kế hoạch mới có thể phù hợp hơn nhưng compile có chi phí và có thể làm tăng CPU khi workload có tần suất cao.
- **“Tái sử dụng kế hoạch luôn tốt hơn.”** Kế hoạch dùng chung có thể kém với một số nhóm tham số có độ chọn lọc khác biệt lớn.
- **“Cost là thời gian chạy tính bằng mili giây.”** Cost là ước lượng của bộ tối ưu, không phải đồng hồ đo thực tế.
- **“Thấy compile nhiều thì xóa toàn bộ cache.”** Cần tìm nguyên nhân compile và phạm vi câu lệnh trước; xóa cache có thể tạo đợt compile mới trên toàn hệ thống.
- **“Chỉ đo một giá trị tham số.”** Một giá trị không đại diện cho phân bố dữ liệu và hành vi của workload.
- **“Recompile giải quyết được mọi truy vấn chậm.”** Nếu nguyên nhân là I/O, khóa, thiếu index, ứng dụng đọc chậm hoặc truy vấn trả quá nhiều dữ liệu, recompile có thể không giúp.

## 10. Checklist đánh giá plan cache và recompile

- [ ] Đã xác định câu SQL, tần suất gọi, mức đồng thời và các nhóm tham số đại diện.
- [ ] Đã tách chi phí parse/compile/plan khỏi execution và wait time theo công cụ của engine.
- [ ] Đã kiểm tra SQL có được tham số hóa và có tạo nhiều biến thể không cần thiết không.
- [ ] Đã xác định kế hoạch có được tái sử dụng, bị invalidation hay recompile thường xuyên không.
- [ ] Đã đối chiếu thời điểm recompile với thay đổi schema, index, statistics và cache.
- [ ] Đã so sánh actual plan và estimated/actual rows trên các nhóm tham số khác nhau.
- [ ] Đã kiểm tra tác động của compile CPU, cache churn và bộ nhớ plan cache.
- [ ] Đã thử thay đổi có phạm vi nhỏ và ghi nhận điều kiện thử nghiệm.
- [ ] Đã đo lại p95/p99, compile time, execution time, CPU, I/O, waits và throughput.
- [ ] Đã xác nhận cải thiện của câu SQL không làm workload khác suy giảm đáng kể.

## Kết luận

Kế hoạch thực thi được lưu lại giúp giảm chi phí phân tích và tối ưu lặp lại. Khi schema, thống kê, metadata hoặc ngữ cảnh liên quan thay đổi, hệ quản trị có thể vô hiệu hóa và tạo kế hoạch mới. Việc tái sử dụng giúp tiết kiệm chi phí lập kế hoạch, nhưng một kế hoạch duy nhất có thể không phù hợp với mọi giá trị tham số khi dữ liệu phân bố lệch.

Muốn tối ưu đúng, hãy đo riêng chi phí lập kế hoạch, thực thi và chờ; kiểm tra mức tái sử dụng, nguyên nhân recompile và độ phù hợp của kế hoạch với các nhóm tham số. Tham số hóa, cập nhật thống kê, điều chỉnh truy vấn và recompile có chọn lọc đều là công cụ có đánh đổi. Chỉ kết luận sau khi so sánh bằng dữ liệu đại diện, cùng điều kiện tải và các chỉ số hiệu năng trước/sau thay đổi.
