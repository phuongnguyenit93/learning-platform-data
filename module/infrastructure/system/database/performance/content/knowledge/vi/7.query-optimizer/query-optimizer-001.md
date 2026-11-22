# Các giai đoạn phân tích cú pháp, biến đổi truy vấn và chọn kế hoạch

Khi ứng dụng gửi một câu lệnh SQL, hệ quản trị cơ sở dữ liệu không lập tức đọc bảng theo đúng thứ tự câu lệnh được viết. Trước khi truy cập dữ liệu, hệ quản trị phải phân tích cú pháp, xác định ý nghĩa của tên bảng và cột, biến đổi truy vấn thành các dạng tương đương, rồi lựa chọn một kế hoạch thực thi phù hợp. Những quyết định này ảnh hưởng trực tiếp đến số hàng được đọc, thứ tự nối bảng, cách dùng chỉ mục, lượng bộ nhớ và I/O cần thiết.

Trong chương **Bộ tối ưu truy vấn** của module **DATABASE_PERFORMANCE**, bài học này giải thích các giai đoạn từ SQL đầu vào đến kế hoạch thực thi. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy, hiểu quy trình của bộ tối ưu giúp bạn biết cần đọc phần nào của kế hoạch, vì sao hệ quản trị chọn một đường truy cập và bằng chứng nào có thể chỉ ra lựa chọn chưa phù hợp.

## 1. Từ câu SQL đến thao tác trên dữ liệu

SQL mô tả kết quả mong muốn theo cách khai báo. Người viết thường nêu bảng, điều kiện lọc, phép nối, nhóm và thứ tự kết quả. Hệ quản trị chịu trách nhiệm quyết định cách lấy dữ liệu để tạo ra kết quả đó.

Một đường xử lý khái quát có thể gồm các giai đoạn:

~~~text
Câu lệnh SQL
    |
    v
Phân tích cú pháp (Parsing)
    |
    v
Phân giải tên và kiểm tra ngữ nghĩa
    |
    v
Biểu diễn truy vấn nội bộ
    |
    v
Viết lại truy vấn (Query Rewrite)
    |
    v
Kế hoạch logic và các phương án tương đương
    |
    v
Tạo, ước lượng và chọn kế hoạch vật lý
    |
    v
Kế hoạch thực thi
    |
    v
Thực thi toán tử và truy cập dữ liệu
~~~

Đây là mô hình khái niệm. Tên gọi, thứ tự chi tiết và mức độ tách biệt giữa các giai đoạn khác nhau tùy hệ quản trị. Một số hệ thống kết hợp phân giải tên với phân tích ngữ nghĩa; một số thực hiện nhiều lần biến đổi trong quá trình tối ưu; một số có thể biên dịch lại hoặc điều chỉnh kế hoạch khi thực thi.

Điểm quan trọng là phải phân biệt hai nhóm công việc:

- **Xác định ý nghĩa:** câu SQL có hợp lệ không, tên đối tượng trỏ đến đâu, kiểu dữ liệu có tương thích không và kết quả cần tuân theo ngữ nghĩa nào?
- **Tìm cách thực hiện:** trong các phương án giữ nguyên ý nghĩa, phương án nào có chi phí dự kiến thấp hơn với dữ liệu và tài nguyên hiện tại?

Bộ tối ưu không được tự ý thay đổi kết quả mà câu SQL yêu cầu. Một kế hoạch nhanh nhưng trả về hàng khác, làm thay đổi số lần xuất hiện của hàng hoặc vi phạm ngữ nghĩa NULL là không hợp lệ.

## 2. Phân tích cú pháp: kiểm tra cấu trúc câu lệnh

Phân tích cú pháp (parsing) biến chuỗi SQL thành cấu trúc mà hệ quản trị có thể xử lý. Bộ phân tích nhận diện từ khóa, tên định danh, toán tử, biểu thức, dấu ngoặc và cấu trúc các mệnh đề.

Ví dụ:

~~~sql
SELECT order_id, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
~~~

Hệ quản trị nhận ra đây là một câu SELECT, danh sách cột cần trả về, bảng nguồn và biểu thức điều kiện. Từ đó, parser tạo cây cú pháp (syntax tree hoặc parse tree) phản ánh cấu trúc câu lệnh.

Nếu cú pháp không hợp lệ, câu lệnh thường dừng ở giai đoạn này và trả lỗi. Ví dụ thiếu dấu phẩy, dùng từ khóa sai vị trí hoặc thiếu dấu ngoặc sẽ khiến parser không thể tạo cấu trúc hợp lệ.

Parsing không quyết định bảng nào nên được quét hay chỉ mục nào nên được dùng. Một câu lệnh có thể hoàn toàn đúng cú pháp nhưng vẫn tham chiếu cột không tồn tại, dùng kiểu dữ liệu không tương thích hoặc không có quyền truy cập. Những vấn đề đó cần được xử lý ở các bước kiểm tra ngữ nghĩa và quyền.

Một số hệ quản trị hỗ trợ prepared statement, trong đó câu lệnh có thể được phân tích và chuẩn bị trước rồi tái sử dụng với các tham số khác nhau. Tuy nhiên, cách tái sử dụng parse tree, kế hoạch logic và kế hoạch vật lý khác nhau giữa các hệ quản trị và chế độ prepared statement.

## 3. Phân giải tên và kiểm tra ngữ nghĩa

Sau khi có cấu trúc cú pháp, hệ quản trị phải xác định chính xác các đối tượng được nhắc đến:

- Bảng hoặc view nào được tham chiếu?
- Cột nào thuộc bảng nào?
- Tên không ghi schema được tìm trong schema hoặc search path nào?
- Hàm và toán tử nào phù hợp với kiểu dữ liệu?
- Kiểu dữ liệu của biểu thức và phép so sánh có tương thích không?
- Người dùng hiện tại có quyền thực hiện thao tác không?
- Các ràng buộc, kiểu dữ liệu và quy tắc collation nào có liên quan?

Ví dụ:

~~~sql
SELECT id, status
FROM orders
JOIN customers ON customer_id = id;
~~~

Nếu cả orders và customers đều có cột id, tên id trong biểu thức có thể không rõ ràng. Hệ quản trị có thể yêu cầu chỉ rõ bảng hoặc bí danh:

~~~sql
SELECT o.id, o.status
FROM orders AS o
JOIN customers AS c ON o.customer_id = c.id;
~~~

Phân giải tên tạo ra liên kết giữa tên được viết trong SQL với đối tượng thực tế trong catalog hoặc metadata của hệ quản trị. Việc này quan trọng khi nhiều schema có bảng cùng tên, view che giấu bảng nguồn hoặc search path thay đổi.

Kiểm tra ngữ nghĩa cũng phải bảo toàn các quy tắc của SQL, đặc biệt là NULL, kiểu dữ liệu, phép ép kiểu, collation, hàm và toán tử. Ví dụ, điều kiện so sánh với NULL không giống so sánh bằng một giá trị thông thường. Một phép biến đổi biểu thức chỉ hợp lệ khi giữ được kết quả theo logic ba giá trị của SQL.

Quyền truy cập và cơ chế bảo mật như row-level security cũng có thể ảnh hưởng đến tập dữ liệu mà truy vấn nhìn thấy. Khi đọc kế hoạch, cần nhớ rằng truy vấn được tối ưu trong ngữ cảnh người dùng, quyền và chính sách áp dụng tại thời điểm thực thi.

## 4. Biểu diễn truy vấn nội bộ

Sau parsing và phân giải ngữ nghĩa, hệ quản trị thường tạo một biểu diễn nội bộ thuận tiện cho việc biến đổi và tối ưu. Biểu diễn này có thể là cây truy vấn, đồ thị quan hệ hoặc một cấu trúc nội bộ khác.

Ví dụ, câu lệnh:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND c.region = 'NORTH';
~~~

Có thể được hiểu về mặt quan hệ như sau:

1. Lấy dữ liệu từ orders và customers.
2. Ghép các hàng theo customer_id.
3. Chỉ giữ hàng có status là PAID và region là NORTH.
4. Chiếu ra order_id và customer_name.

Biểu diễn nội bộ tách ý nghĩa của truy vấn khỏi cách thực thi cụ thể. Nó có thể mô tả phép lọc (selection), phép chiếu (projection), phép nối (join), gom nhóm (aggregation), sắp xếp và giới hạn số hàng.

Từ biểu diễn này, bộ tối ưu có thể xem xét nhiều cách thực hiện tương đương. Ví dụ, điều kiện lọc trên orders có thể được đẩy xuống trước phép nối để giảm số hàng đầu vào. Việc chọn quét chỉ mục hay quét tuần tự chỉ được quyết định khi xem xét các phương án truy cập vật lý và chi phí của chúng.

## 5. Viết lại truy vấn (Query Rewrite)

Query Rewrite biến đổi biểu diễn truy vấn thành dạng khác nhưng phải giữ nguyên ngữ nghĩa. Mục tiêu là tạo cơ hội cho bộ tối ưu tìm được kế hoạch hiệu quả hơn hoặc đơn giản hóa công việc.

Một số phép biến đổi phổ biến gồm:

### 5.1. Đẩy điều kiện lọc xuống gần nguồn dữ liệu

Predicate pushdown đưa điều kiện lọc đến sớm hơn trong cây truy vấn để giảm số hàng phải chuyển qua các toán tử tiếp theo.

Trước biến đổi, có thể hình dung:

~~~text
Project
  |
Filter orders.status = 'PAID'
  |
Join orders với customers
  |
Scan orders và customers
~~~

Sau khi đẩy điều kiện xuống:

~~~text
Project
  |
Join
  |----------------|
Filter             Scan customers
  |
Scan orders
~~~

Nếu điều kiện lọc chỉ tham chiếu orders và việc biến đổi giữ nguyên ngữ nghĩa, hệ quản trị có thể lọc orders trước khi nối với customers. Khi số đơn hàng PAID nhỏ so với toàn bộ orders, số hàng tham gia phép nối có thể giảm đáng kể.

Tuy nhiên, không phải mọi điều kiện đều có thể đẩy qua mọi phép nối. Với outer join, điều kiện đặt ở WHERE và điều kiện đặt trong ON có thể tạo kết quả khác nhau. Hàm không xác định, biểu thức có tác dụng phụ hoặc điều kiện phụ thuộc thứ tự đánh giá cũng có thể hạn chế biến đổi. Bộ tối ưu phải tôn trọng ngữ nghĩa SQL.

### 5.2. Loại bỏ cột không cần thiết

Projection pruning loại bỏ những cột trung gian không cần để tạo kết quả cuối cùng. Nếu truy vấn chỉ trả order_id và customer_name, hệ quản trị có thể không cần mang theo các cột lớn như ghi chú hoặc nội dung JSON qua các bước nối và sắp xếp.

Giảm số cột trung gian có thể giảm lượng dữ liệu truyền giữa toán tử, bộ nhớ cho sort/hash và I/O. Tuy nhiên, các cột dùng cho điều kiện lọc, nối, nhóm, sắp xếp hoặc biểu thức kết quả vẫn cần được giữ ở nơi cần thiết.

### 5.3. Rút gọn biểu thức và tính toán hằng

Constant folding tính trước những biểu thức có thể xác định từ hằng số:

~~~sql
WHERE quantity > 2 * 5
~~~

Có thể được rút gọn thành:

~~~sql
WHERE quantity > 10
~~~

Tương tự, các biểu thức logic đơn giản có thể được rút gọn hoặc chuẩn hóa để bộ tối ưu nhận diện điều kiện dễ hơn. Nhưng biểu thức có hàm phụ thuộc thời gian, trạng thái phiên, dữ liệu hoặc tính không xác định không thể tùy tiện tính trước.

### 5.4. Biến đổi subquery và phép nối

Một số subquery có thể được chuyển thành semi join, anti join hoặc phép nối tương đương. Ví dụ, EXISTS thường biểu đạt ý định kiểm tra sự tồn tại:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Hệ quản trị có thể biến đổi truy vấn thành dạng semi join để dừng tìm kiếm khi tìm thấy một hàng phù hợp, tùy kế hoạch và hệ quản trị.

NOT EXISTS có thể được biến đổi thành anti join trong một số điều kiện. Nhưng không nên tự thay NOT IN bằng NOT EXISTS hoặc ngược lại mà không kiểm tra NULL. Nếu tập con chứa NULL, ngữ nghĩa của NOT IN có thể khác với phép kiểm tra không tồn tại thông thường.

### 5.5. Loại bỏ phép nối không cần thiết

Nếu hệ quản trị chứng minh một bảng được nối không ảnh hưởng đến kết quả, không tạo hàng trùng và không làm thay đổi ngữ nghĩa, nó có thể loại bỏ phép nối đó. Khả năng này phụ thuộc ràng buộc khóa, tính duy nhất, quan hệ khóa ngoại và cách truy vấn sử dụng cột.

Ràng buộc toàn vẹn không chỉ bảo vệ dữ liệu; khi được khai báo và được hệ quản trị tin cậy, chúng còn có thể giúp bộ tối ưu suy luận về tính duy nhất hoặc quan hệ giữa các bảng. Nếu dữ liệu thực tế đúng nhưng ràng buộc không được khai báo, bộ tối ưu có thể không tận dụng được thông tin đó.

### 5.6. Mở rộng view và xử lý CTE

View thường được mở rộng thành truy vấn nguồn để hệ quản trị tối ưu cùng với câu lệnh bên ngoài. Một số CTE có thể được inline, một số có thể được materialize thành kết quả trung gian. Hành vi này tùy hệ quản trị, phiên bản và từ khóa.

Không nên mặc định CTE luôn là hàng rào tối ưu hoặc luôn được inline. Materialization có thể tránh tính lại một biểu thức được dùng nhiều lần, nhưng cũng có thể buộc hệ quản trị tạo tập kết quả trung gian lớn. Inline có thể mở ra cơ hội đẩy điều kiện, nhưng đôi khi làm biểu thức phức tạp hơn hoặc lặp lại công việc. Hãy kiểm tra kế hoạch thực tế.

## 6. Từ kế hoạch logic đến kế hoạch vật lý

Kế hoạch logic mô tả các phép toán cần thực hiện theo ý nghĩa quan hệ, chẳng hạn lọc, nối, nhóm và chiếu. Kế hoạch vật lý chỉ ra hệ quản trị sẽ thực hiện chúng bằng toán tử cụ thể nào.

Ví dụ, một phép nối logic giữa orders và customers có thể được triển khai bằng:

- Nested loop join.
- Hash join.
- Merge join.

Một phép lọc logic có thể được thực hiện bằng cách quét tuần tự bảng, quét chỉ mục hoặc tìm kiếm theo chỉ mục. Một phép sắp xếp logic có thể được thực hiện bằng sort trong bộ nhớ, sort tràn ra vùng tạm hoặc tận dụng thứ tự có sẵn từ chỉ mục.

Chọn kế hoạch vật lý là quá trình cân nhắc chi phí và đặc điểm dữ liệu. Không có một toán tử luôn nhanh nhất trong mọi trường hợp.

### 6.1. Nested loop join

Nested loop thường lặp qua các hàng của một phía và tìm hàng phù hợp ở phía còn lại. Nó có thể rất hiệu quả khi phía ngoài nhỏ và phía trong có chỉ mục phù hợp.

Ví dụ, nếu truy vấn lấy 10 khách hàng rồi tìm đơn hàng theo customer_id, một phép tìm kiếm chỉ mục cho từng khách hàng có thể rẻ hơn việc đọc toàn bộ orders.

Nhưng nếu phía ngoài có hàng triệu hàng và mỗi hàng phải quét lại một tập dữ liệu lớn, nested loop có thể tạo ra lượng công việc rất lớn. Cần xem số vòng lặp, số hàng đầu vào và số hàng được truy cập ở phía trong.

### 6.2. Hash join

Hash join thường xây dựng cấu trúc hash từ một phía rồi dò tìm hàng khớp từ phía còn lại. Nó phù hợp với nhiều phép nối bằng giữa hai tập dữ liệu có kích thước đáng kể, đặc biệt khi không có thứ tự sẵn có hoặc chỉ mục thích hợp.

Hash join cần bộ nhớ. Nếu tập dữ liệu xây dựng lớn hơn vùng bộ nhớ được cấp, hệ quản trị có thể chia partition hoặc ghi dữ liệu trung gian ra vùng lưu trữ tạm. Vì vậy, một hash join có thể nhanh ở tải thấp nhưng chậm khi nhiều truy vấn đồng thời tranh chấp bộ nhớ.

### 6.3. Merge join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Nếu dữ liệu đã có thứ tự phù hợp từ chỉ mục hoặc toán tử trước đó, merge join có thể tránh một phần chi phí sắp xếp. Nếu chưa có thứ tự, việc sắp xếp hai phía có thể làm kế hoạch tốn kém.

### 6.4. Quét tuần tự và truy cập chỉ mục

Sequential scan đọc các trang của bảng theo cách tuần tự. Nó có thể phù hợp khi truy vấn cần phần lớn hàng, bảng nhỏ hoặc việc truy cập theo chỉ mục sẽ tạo nhiều lần đọc rời rạc.

Index scan hoặc index seek tìm hàng qua cấu trúc chỉ mục. Chúng có thể hiệu quả khi điều kiện chọn lọc và truy vấn chỉ cần một phần nhỏ dữ liệu. Nhưng nếu phải truy cập nhiều hàng nằm rải rác, chi phí đọc trang dữ liệu có thể lớn hơn quét tuần tự.

Index-only scan hoặc cơ chế tương đương có thể trả dữ liệu từ chỉ mục mà không cần đọc thêm trang bảng trong những điều kiện nhất định. Điều này phụ thuộc hệ quản trị, loại chỉ mục, cột cần dùng và trạng thái visibility hoặc metadata liên quan.

## 7. Bộ tối ưu dựa trên chi phí chọn kế hoạch

Cost-based optimizer (CBO) ước lượng chi phí của các phương án rồi chọn một phương án có chi phí dự kiến thấp theo mô hình của hệ quản trị.

Chi phí có thể phản ánh nhiều yếu tố:

- Số hàng dự kiến đi qua từng toán tử.
- Số trang phải đọc từ bộ nhớ hoặc thiết bị lưu trữ.
- CPU cần cho lọc, nối, sắp xếp và biểu thức.
- Bộ nhớ cần cho hash, sort hoặc thao tác trung gian.
- Chi phí ghi/đọc dữ liệu tạm khi tràn bộ nhớ.
- Chi phí truyền dữ liệu giữa worker hoặc node trong hệ thống phân tán.
- Chi phí khởi tạo toán tử và số lần lặp.

Con số cost trong EXPLAIN thường là đơn vị nội bộ tương đối của hệ quản trị, không phải số mili giây. Không nên so sánh cost giữa hai hệ quản trị khác nhau hoặc diễn giải cost 100 là 100 ms. Dùng cost để hiểu lựa chọn tương đối trong cùng một môi trường và cùng cách tính của hệ quản trị.

Bộ tối ưu thường không thể thử mọi kế hoạch có thể có. Số phương án tăng nhanh theo số bảng nối và các phép biến đổi. Hệ quản trị dùng heuristic, giới hạn tìm kiếm, quy tắc cắt tỉa hoặc thuật toán tìm kiếm để kiểm soát thời gian tối ưu. Do đó, kế hoạch được chọn là phương án tốt nhất theo mô hình và phạm vi tìm kiếm mà hệ quản trị đã xét, không phải lời bảo đảm rằng đó là phương án nhanh nhất trong mọi điều kiện thực tế.

## 8. Thống kê và ước lượng số hàng

Một trong những đầu vào quan trọng nhất của cost-based optimizer là cardinality estimate: số hàng mà hệ quản trị dự đoán một toán tử sẽ tạo ra.

Ước lượng này có thể dựa trên:

- Số hàng và số trang của bảng.
- Số giá trị phân biệt (distinct values).
- Histogram hoặc phân bố tần suất.
- Tỷ lệ NULL.
- Thống kê trên nhiều cột hoặc tương quan giữa các cột nếu hệ quản trị hỗ trợ.
- Ràng buộc duy nhất, khóa chính, khóa ngoại.
- Thông tin về tham số hoặc giá trị literal trong câu truy vấn.

Nếu ước lượng sai, chi phí của các phương án cũng sai. Ví dụ, bộ tối ưu nghĩ điều kiện lọc trả về 10 hàng nhưng thực tế trả về 500.000 hàng. Nó có thể chọn nested loop với nhiều lần tìm kiếm chỉ mục, trong khi hash join hoặc quét tuần tự sẽ phù hợp hơn.

Một ví dụ về phân bố lệch:

| status | Tỷ lệ hàng minh họa |
|---|---:|
| PAID | 88% |
| PENDING | 8% |
| CANCELLED | 4% |

Chỉ mục trên status không đảm bảo có lợi như nhau cho mọi giá trị. Lọc PAID có thể trả về phần lớn bảng; lọc CANCELLED có thể chọn lọc hơn nhiều. Nếu thống kê chỉ biết số giá trị phân biệt mà không mô tả được độ lệch, ước lượng có thể kém chính xác.

Khi đọc kế hoạch, hãy so sánh số hàng ước lượng với số hàng thực tế nếu hệ quản trị cung cấp. Sai lệch lớn ở một toán tử sớm có thể lan truyền sang các phép nối và sắp xếp phía sau. Cần kiểm tra thống kê có cũ không, dữ liệu có phân bố lệch hoặc tương quan giữa cột không, và tham số hiện tại có đại diện cho workload hay không.

## 9. Chọn thứ tự nối bảng

Khi truy vấn nối nhiều bảng, thứ tự thực hiện phép nối có thể ảnh hưởng lớn đến số hàng trung gian và chi phí. Bộ tối ưu có thể xem xét nhiều thứ tự khác nhau, dựa trên cardinality estimate và chi phí.

Giả sử có ba bảng:

- customers: thông tin khách hàng.
- orders: đơn hàng.
- order_items: chi tiết đơn hàng.

Một truy vấn có thể nối customers với orders trước, sau đó nối order_items; hoặc xử lý order_items và orders trước rồi mới nối customers. Phương án tốt phụ thuộc điều kiện lọc, độ chọn lọc và phân bố dữ liệu.

Nếu truy vấn lọc customers theo một khu vực chỉ có 100 khách hàng, có thể hữu ích khi bắt đầu từ tập khách hàng nhỏ rồi tìm orders tương ứng. Nếu truy vấn lọc orders theo một khoảng thời gian rất hẹp, có thể hiệu quả hơn khi bắt đầu từ orders.

Không nên tự đổi thứ tự JOIN chỉ dựa trên thứ tự viết trong SQL. Nhiều hệ quản trị được phép tái sắp xếp phép nối inner join khi phép biến đổi giữ nguyên ngữ nghĩa. Outer join, lateral join, hàm không xác định, giới hạn hàng hoặc ràng buộc khác có thể hạn chế khả năng đổi thứ tự.

## 10. Kế hoạch phụ thuộc tham số và cache kế hoạch

Một truy vấn có thể được gọi với nhiều giá trị tham số có phân bố khác nhau. Ví dụ, tenant lớn có hàng triệu đơn hàng trong khi tenant nhỏ chỉ có vài trăm. Một kế hoạch tốt cho tenant nhỏ có thể không tốt cho tenant lớn.

Các hệ quản trị có thể:

- Tối ưu lại cho từng lần gọi hoặc từng nhóm lần gọi.
- Tạo kế hoạch dùng chung cho prepared statement.
- Tái sử dụng kế hoạch đã lưu trong cache.
- Dùng giá trị tham số khi biên dịch hoặc tối ưu.
- Chọn kế hoạch chung để tránh biên dịch lại quá thường xuyên.
- Hỗ trợ nhiều kế hoạch hoặc cơ chế thích ứng trong một số trường hợp.

Parameter sniffing hoặc parameter sensitivity là hiện tượng lựa chọn kế hoạch bị ảnh hưởng bởi giá trị tham số được dùng ở thời điểm tối ưu. Đây không nhất thiết là lỗi; nó trở thành vấn đề khi một kế hoạch được tái sử dụng cho giá trị có phân bố rất khác.

Khi điều tra, hãy thử nhiều nhóm tham số đại diện, không chỉ một giá trị. So sánh kế hoạch, số hàng ước lượng/thực tế và độ trễ theo nhóm dữ liệu. Trước khi dùng hint, ép kế hoạch hoặc tắt cache, hãy hiểu cơ chế cụ thể của hệ quản trị và đánh giá ảnh hưởng đến toàn bộ workload.

## 11. Đọc kế hoạch thực thi để hiểu quyết định của bộ tối ưu

EXPLAIN hoặc công cụ tương đương cho biết kế hoạch mà hệ quản trị dự kiến dùng. Một số hệ thống hỗ trợ chế độ thực thi phân tích như EXPLAIN ANALYZE để bổ sung số liệu thực tế.

Ví dụ minh họa:

~~~sql
EXPLAIN
SELECT o.order_id, o.created_at, o.total
FROM orders AS o
WHERE o.tenant_id = 42
  AND o.status = 'PAID'
  AND o.created_at >= DATE '2026-01-01'
ORDER BY o.created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Khi đọc kế hoạch, hãy xem:

1. Đường truy cập: sequential scan, index scan, index seek hoặc cách truy cập khác.
2. Điều kiện lọc: điều kiện nào được áp dụng tại bước đọc dữ liệu, điều kiện nào được áp dụng sau.
3. Số hàng ước lượng và số hàng thực tế.
4. Số vòng lặp của từng toán tử.
5. Phép nối và thứ tự nối bảng.
6. Sort, aggregate, hash và các toán tử trung gian.
7. Bộ nhớ, spill và dữ liệu tạm nếu được cung cấp.
8. Cost, elapsed time, CPU hoặc I/O theo khả năng của hệ quản trị.

EXPLAIN thường chỉ hiển thị kế hoạch ước lượng. EXPLAIN ANALYZE hoặc chế độ tương đương có thể thực thi câu lệnh. Đặc biệt với INSERT, UPDATE hoặc DELETE, lệnh phân tích có thể tạo thay đổi dữ liệu. Hãy đọc tài liệu hệ quản trị và sử dụng môi trường, dữ liệu hoặc cơ chế giao dịch an toàn trước khi chạy.

Một số lưu ý khi diễn giải:

- Quét toàn bảng không tự động là xấu; nếu cần phần lớn dữ liệu, nó có thể rẻ hơn chỉ mục.
- Index scan không tự động tốt; truy cập nhiều trang rời rạc có thể tốn I/O.
- Cost thấp không bảo đảm elapsed time thấp nếu máy chủ đang tranh chấp tài nguyên.
- Số hàng ước lượng thấp hơn nhiều so với thực tế có thể làm lựa chọn phép nối sai.
- Toán tử có thời gian cao chưa chắc là nguyên nhân duy nhất; nó có thể đang chờ dữ liệu từ bước trước.
- Số liệu thực tế của truy vấn song song cần được hiểu theo cách hệ quản trị tổng hợp worker và thời gian.

## 12. Ví dụ xuyên suốt: từ SQL đến kế hoạch

Giả sử API cần hiển thị 50 đơn hàng PAID mới nhất của một tenant:

~~~sql
SELECT o.order_id, o.created_at, o.total, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = :tenant_id
  AND o.status = 'PAID'
  AND o.created_at >= :from_time
ORDER BY o.created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

### Giai đoạn phân tích và phân giải

Parser tạo cấu trúc SELECT, FROM, JOIN, WHERE, ORDER BY và giới hạn số hàng. Resolver xác định orders, customers, các cột, kiểu dữ liệu và quyền truy cập. Nếu customer_id xuất hiện ở cả hai bảng, việc ghi rõ bí danh o và c giúp tránh mơ hồ.

### Giai đoạn viết lại

Bộ tối ưu có thể đẩy điều kiện lọc tenant_id, status và created_at xuống gần nguồn orders. Các cột không cần thiết có thể bị loại khỏi các bước trung gian. Nếu có view hoặc CTE, hệ quản trị có thể inline hoặc materialize theo quy tắc của nó.

### Giai đoạn ước lượng

Bộ tối ưu ước lượng số đơn hàng của tenant thỏa điều kiện, số khách hàng liên quan và số hàng sau phép nối. Thống kê về tenant_id, status và created_at ảnh hưởng đến ước lượng này. Nếu dữ liệu tenant lệch mạnh, thống kê không đủ chi tiết có thể làm ước lượng sai.

### Giai đoạn chọn kế hoạch vật lý

Một phương án có thể bắt đầu từ orders bằng chỉ mục kết hợp, lấy một tập hàng nhỏ theo điều kiện và thứ tự thời gian, rồi tìm khách hàng tương ứng bằng nested loop. Một phương án khác có thể quét một vùng orders, dùng hash join với customers và sắp xếp kết quả trước khi giới hạn 50 hàng.

Không thể kết luận phương án nào tốt hơn chỉ từ SQL. Cần xem số hàng ước lượng/thực tế, kế hoạch, mức độ chọn lọc và tải đọc/ghi. Chỉ mục kết hợp như (tenant_id, status, created_at) có thể là một ứng viên để thử, nhưng lợi ích còn phụ thuộc phân bố dữ liệu, thứ tự sắp xếp, cách hệ quản trị xử lý giới hạn hàng và chi phí cập nhật chỉ mục.

### Kiểm chứng

1. Ghi lại p50, p95, p99 và tần suất của endpoint.
2. Thu thập kế hoạch và thống kê của truy vấn với tenant nhỏ, tenant lớn và các giá trị status đại diện.
3. So sánh ước lượng với số hàng thực tế.
4. Xác định toán tử hoặc bước nào chiếm nhiều công việc.
5. Đưa ra một giả thuyết, chẳng hạn ước lượng cardinality sai hoặc đường truy cập đọc quá nhiều hàng.
6. Thử một thay đổi trong môi trường phù hợp.
7. Đo lại cùng nhóm tham số và mức tải, kiểm tra cả đọc, ghi, CPU, I/O và tính đúng đắn.

Nếu chỉ đo một tenant nhỏ, bạn có thể bỏ sót kế hoạch kém cho tenant lớn. Nếu chỉ xem một lần chạy sau khi cache đã nóng, bạn có thể đánh giá sai tác động của I/O. Hãy dùng nhiều trường hợp đại diện.

## 13. Khi nào bộ tối ưu không thể biến đổi như mong muốn?

Không phải mọi biểu thức SQL tương đương về trực giác đều có thể được biến đổi tự do. Một số yếu tố giới hạn không gian tìm kiếm:

- **Outer join:** vị trí điều kiện ON và WHERE có thể làm thay đổi việc giữ lại hàng không khớp.
- **NULL:** NOT IN, NOT EXISTS và phép so sánh có thể khác nhau khi tập dữ liệu chứa NULL.
- **Hàm không xác định:** hàm phụ thuộc thời gian hoặc trạng thái có thể không được tính lại hoặc đẩy xuống tùy tiện.
- **Thứ tự và giới hạn hàng:** ORDER BY, LIMIT/FETCH và phân trang có thể hạn chế đổi thứ tự phép nối.
- **Aggregation:** đẩy phép nhóm qua phép nối chỉ hợp lệ trong điều kiện nhất định, nếu không có thể làm thay đổi kết quả.
- **Window function:** thứ tự và phạm vi cửa sổ có thể phụ thuộc vào toàn bộ tập hàng trước đó.
- **CTE materialization:** ranh giới vật hóa có thể giới hạn việc đẩy điều kiện hoặc kết hợp các phép toán.
- **Security policy:** view, row-level security và quyền truy cập có thể tạo ranh giới mà bộ tối ưu phải bảo toàn.

Đây là lý do không nên áp dụng mẹo viết lại SQL một cách máy móc. Hãy kiểm tra kết quả tương đương và kế hoạch thực tế. Nếu một phép biến đổi làm truy vấn nhanh hơn nhưng thay đổi tập hàng hoặc thứ tự cần thiết, đó không phải tối ưu hợp lệ.

## 14. Các sai lầm thường gặp khi hiểu bộ tối ưu

**Cho rằng SQL được thực hiện theo thứ tự viết.** SQL mô tả kết quả; hệ quản trị có thể đổi thứ tự lọc, nối và truy cập dữ liệu nếu giữ nguyên ngữ nghĩa.

**Cho rằng parser quyết định chỉ mục.** Parsing và phân giải ngữ nghĩa tạo cấu trúc hợp lệ; lựa chọn đường truy cập thuộc giai đoạn tối ưu và lập kế hoạch vật lý.

**Cho rằng cost là thời gian thực.** Cost thường là đơn vị tương đối nội bộ, cần dùng để hiểu lựa chọn trong cùng hệ quản trị và cấu hình.

**Cho rằng chỉ mục luôn tốt hơn quét bảng.** Độ chọn lọc, số trang cần đọc, thứ tự dữ liệu và kích thước bảng quyết định lợi ích.

**Cho rằng kế hoạch ước lượng luôn đúng.** Thống kê cũ, phân bố lệch, tương quan cột và tham số nhạy cảm có thể làm cardinality estimate sai.

**Cho rằng mọi subquery đều chậm.** Bộ tối ưu có thể biến đổi subquery thành join hoặc semi/anti join. Cần xem kế hoạch thay vì đánh giá theo hình thức SQL.

**Cho rằng hint là cách sửa mặc định.** Hint có thể khóa hệ thống vào một lựa chọn phù hợp với dữ liệu hiện tại nhưng kém khi workload hoặc phân bố dữ liệu thay đổi. Chỉ dùng khi có bằng chứng và có kế hoạch theo dõi.

**Chỉ thử một bộ tham số.** Kế hoạch tốt cho giá trị phổ biến có thể rất kém cho giá trị hiếm hoặc tenant lớn. Cần thử các nhóm đại diện.

## 15. Checklist đọc và đánh giá quá trình tối ưu

- [ ] Câu SQL hợp lệ về cú pháp và ngữ nghĩa.
- [ ] Đã xác định đúng schema, bảng, cột, kiểu dữ liệu và quyền truy cập.
- [ ] Hiểu các điều kiện lọc, phép nối, nhóm, sắp xếp và giới hạn kết quả.
- [ ] Biết những phép viết lại có thể xuất hiện trong kế hoạch.
- [ ] Đã phân biệt kế hoạch logic với kế hoạch vật lý.
- [ ] Đã xem loại scan, join algorithm, sort và aggregate.
- [ ] Đã kiểm tra cardinality estimate so với số hàng thực tế.
- [ ] Đã xem thống kê, phân bố lệch và tương quan cột.
- [ ] Đã kiểm tra nhiều giá trị tham số đại diện.
- [ ] Không diễn giải cost như mili giây.
- [ ] Không kết luận quét bảng hoặc dùng chỉ mục luôn tốt/xấu.
- [ ] Đã xác nhận các phép biến đổi giữ nguyên ngữ nghĩa SQL.
- [ ] Đã thử thay đổi có giả thuyết và đo lại trên workload đại diện.
- [ ] Đã kiểm tra tác động lên CPU, I/O, bộ nhớ, ghi dữ liệu và tính đúng đắn.

## 16. Nguyên tắc cần ghi nhớ

Bộ tối ưu truy vấn biến câu SQL khai báo thành một kế hoạch thực thi cụ thể qua nhiều giai đoạn: phân tích cú pháp, phân giải tên và ngữ nghĩa, biểu diễn nội bộ, viết lại truy vấn, ước lượng chi phí và lựa chọn toán tử vật lý. Mỗi giai đoạn giải quyết một loại vấn đề khác nhau và đều phải giữ nguyên kết quả mà câu lệnh yêu cầu.

Muốn tối ưu hiệu năng, hãy đọc kế hoạch để hiểu hệ quản trị đã biến đổi và chọn cách thực hiện nào, sau đó kiểm tra ước lượng hàng, thống kê và số liệu thực tế. Khi kế hoạch chưa phù hợp, hãy tìm nguyên nhân trong dữ liệu, thống kê, tham số, chỉ mục hoặc ngữ nghĩa truy vấn trước khi thay đổi SQL hay dùng hint. Một quyết định tốt phải được kiểm chứng trên nhiều trường hợp tải đại diện và bảo toàn tính đúng đắn của dữ liệu.
