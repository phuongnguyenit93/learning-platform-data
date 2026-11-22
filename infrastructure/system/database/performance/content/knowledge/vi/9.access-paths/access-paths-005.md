# Chỉ mục phân cụm và tổ chức bảng theo hệ quản trị

Cách một hệ quản trị cơ sở dữ liệu tổ chức các hàng trên lưu trữ ảnh hưởng trực tiếp đến số trang phải đọc, tính cục bộ của truy cập, chi phí cập nhật và hiệu năng của các truy vấn. Một chỉ mục có thể giúp tìm nhanh khóa, nhưng nếu các hàng cần đọc nằm rải rác trên nhiều trang thì DBMS vẫn phải thực hiện nhiều lần truy cập dữ liệu. Ngược lại, khi dữ liệu được sắp xếp gần với thứ tự truy cập thường gặp, một truy vấn phạm vi có thể đọc ít trang hơn và tận dụng I/O tuần tự tốt hơn.

Trong module **DATABASE_PERFORMANCE**, việc tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Cơ chế truy cập** giúp người học hiểu chỉ mục phân cụm, heap table và các cách tổ chức bảng khác nhau giữa PostgreSQL, SQL Server, InnoDB và Oracle. Từ đó, người học có thể lựa chọn khóa phù hợp, dự đoán tác động của truy vấn đọc/ghi, đọc dấu hiệu trong execution plan và kiểm chứng liệu việc thay đổi tổ chức dữ liệu có thực sự cải thiện workload hay không.

Sau bài học, người học có thể:

- Giải thích tính cục bộ dữ liệu và mối liên hệ giữa thứ tự lưu trữ với chi phí I/O.
- Phân biệt clustered index, heap table, index-organized table và lệnh sắp xếp lại bảng.
- Mô tả cách PostgreSQL, SQL Server, InnoDB và Oracle tổ chức dữ liệu ở mức khái niệm.
- Nhận biết tác động của clustered key, primary key và secondary index đến truy vấn đọc/ghi.
- Đánh giá clustering factor, page split, fragmentation và kích thước khóa trong bối cảnh phù hợp.
- Chọn access path dựa trên điều kiện truy vấn, phân bố dữ liệu và kế hoạch thực thi.
- Lập phép đo trước/sau để xác nhận lợi ích và chi phí của thay đổi.

## 1. Vì sao tổ chức dữ liệu ảnh hưởng đến hiệu năng?

### 1.1. Bảng, hàng và trang dữ liệu

DBMS thường lưu dữ liệu trên thiết bị theo các trang hoặc khối. Một trang chứa nhiều hàng, tùy kích thước hàng, cấu trúc trang và phần không gian còn trống. Khi truy vấn cần một hàng, DBMS phải xác định trang chứa hàng đó và đưa trang vào vùng bộ đệm nếu chưa có sẵn.

Nếu các hàng được truy cập thường xuyên nằm gần nhau trên lưu trữ, DBMS có thể đọc ít trang hơn để lấy một tập kết quả. Nếu các hàng nằm rải rác, cùng một truy vấn có thể phải chạm đến nhiều trang riêng biệt. Đây là khác biệt về tính cục bộ dữ liệu (data locality).

Ví dụ, một ứng dụng thường lấy các đơn hàng của cùng một khách hàng theo thời gian. Nếu những đơn hàng liên quan được tổ chức gần nhau, truy vấn có thể đọc một vùng dữ liệu tương đối liên tục. Nếu các hàng phân tán trên nhiều trang, truy vấn có thể phải thực hiện nhiều lần truy cập rời rạc.

Tổ chức dữ liệu không chỉ ảnh hưởng đến đọc. Khi thêm hoặc cập nhật hàng, DBMS có thể phải tìm vị trí phù hợp, sửa chỉ mục, phân bổ trang mới hoặc di chuyển dữ liệu. Vì vậy, một cách tổ chức tối ưu cho đọc có thể làm ghi tốn kém hơn.

### 1.2. I/O ngẫu nhiên và I/O tuần tự

Có hai kiểu truy cập lưu trữ cần phân biệt:

- **I/O ngẫu nhiên:** đọc hoặc ghi các trang ở vị trí phân tán. Mỗi thao tác có thể chịu chi phí định vị, lập lịch và độ trễ riêng.
- **I/O tuần tự:** đọc một chuỗi trang gần nhau. Thiết bị và hệ điều hành thường có thể xử lý hiệu quả hơn nhờ đọc trước và truy cập theo vùng.

Thiết bị SSD giảm đáng kể độ trễ so với ổ đĩa cơ trong nhiều kiểu truy cập ngẫu nhiên, nhưng tính cục bộ vẫn quan trọng. Một truy vấn phải đọc hàng nghìn trang rời rạc vẫn tiêu thụ băng thông, CPU, bộ nhớ đệm và thời gian xử lý. Với lưu trữ mạng hoặc dịch vụ cloud, số lượng yêu cầu và hàng đợi cũng có thể ảnh hưởng rõ rệt.

Không nên giả định mọi truy vấn phạm vi đều nhanh hơn chỉ vì dữ liệu được sắp xếp. Lợi ích phụ thuộc vào số hàng được chọn, kích thước hàng, thứ tự truy cập, mức cache hit và khả năng DBMS tận dụng thứ tự lưu trữ.

### 1.3. Tính cục bộ theo khóa và theo thời gian

Một workload có thể truy cập dữ liệu theo nhiều chiều:

- Theo khóa định danh, chẳng hạn một đơn hàng cụ thể.
- Theo phạm vi khóa, chẳng hạn tất cả đơn hàng từ một mã đến mã khác.
- Theo thời gian, chẳng hạn các sự kiện mới nhất của một khách hàng.
- Theo nhóm nghiệp vụ, chẳng hạn các dòng chi tiết của một hóa đơn.
- Theo phân vùng hoặc tenant, chẳng hạn dữ liệu của một khách hàng doanh nghiệp.

Nếu thứ tự vật lý hoặc cấu trúc chỉ mục phù hợp với mẫu truy cập thường xuyên, số trang cần đọc có thể giảm. Nhưng một bảng thường phục vụ nhiều mẫu truy cập khác nhau. Không có một thứ tự vật lý duy nhất tối ưu cho mọi truy vấn.

Ví dụ, sắp xếp bảng đơn hàng theo ngày có thể giúp báo cáo theo thời gian nhưng không nhất thiết giúp truy vấn theo customer_id. Sắp xếp theo customer_id có thể cải thiện truy vấn khách hàng nhưng làm truy vấn theo thời gian phải truy cập nhiều vùng dữ liệu. Thiết kế cần dựa trên workload quan trọng và mục tiêu dịch vụ.

## 2. Các khái niệm tổ chức bảng và chỉ mục

### 2.1. Heap table

Heap table là bảng mà các hàng được lưu trong các vị trí không được duy trì theo thứ tự của một khóa chỉ mục cụ thể. DBMS có thể tìm hàng qua địa chỉ hàng, row identifier hoặc cơ chế tra cứu nội bộ.

Heap không có nghĩa là dữ liệu được lưu hoàn toàn ngẫu nhiên hoặc không có cấu trúc. DBMS vẫn quản lý trang, không gian trống, visibility, free space và metadata. Khái niệm heap chỉ nói rằng thứ tự vật lý của hàng không được duy trì như một clustered index theo khóa.

Một bảng heap có thể có nhiều secondary index. Truy vấn dùng chỉ mục để tìm khóa phù hợp rồi theo con trỏ hoặc định danh hàng đến trang dữ liệu. Nếu các hàng cần thiết nằm trên nhiều trang khác nhau, bước truy cập bảng có thể tạo nhiều I/O rời rạc.

### 2.2. Clustered index

Clustered index là cấu trúc chỉ mục gắn trực tiếp với cách lưu trữ hàng dữ liệu hoặc xác định thứ tự các hàng ở mức trang lá. Thuật ngữ và cơ chế cụ thể khác nhau giữa các DBMS.

Ở hệ quản trị mà clustered index là cấu trúc dữ liệu của bảng, trang lá của B-tree chứa chính hàng dữ liệu. Tìm khóa qua clustered index cũng đưa truy vấn đến dữ liệu, không cần thêm bước tra cứu heap riêng như một số mô hình heap + secondary index.

Một bảng thường chỉ có một thứ tự clustered chính vì một tập hàng không thể đồng thời được lưu vật lý theo nhiều thứ tự khóa độc lập. Các mẫu truy cập khác vẫn cần secondary index hoặc cấu trúc khác.

### 2.3. Secondary index

Secondary index là chỉ mục bổ sung để truy cập dữ liệu theo một khóa khác với cấu trúc tổ chức chính của bảng. Tùy DBMS:

- Secondary index có thể lưu row locator hoặc row identifier trỏ đến hàng trong heap.
- Secondary index có thể lưu clustered key làm định danh hàng trong bảng clustered.
- Secondary index có thể bao gồm thêm các cột để đáp ứng truy vấn mà không cần đọc lại hàng đầy đủ.

Secondary index giúp mở rộng các access path, nhưng mỗi chỉ mục bổ sung làm tăng dung lượng và chi phí ghi. INSERT, DELETE và UPDATE các cột được lập chỉ mục có thể phải sửa nhiều cấu trúc. Khi khóa clustered thay đổi, secondary index trong một số hệ quản trị còn phải cập nhật phần định danh hàng.

### 2.4. Index-organized table

Index-organized table (IOT) là cách tổ chức trong đó dữ liệu hàng được lưu trong cấu trúc chỉ mục theo khóa chính, thay vì giữ một heap riêng rồi dùng chỉ mục để trỏ đến heap. Oracle hỗ trợ IOT như một lựa chọn tổ chức bảng.

IOT có thể phù hợp khi phần lớn truy vấn truy cập theo khóa chính hoặc theo một phạm vi của khóa đó. Tuy nhiên, các cột không nằm trong cấu trúc chính hoặc các truy vấn theo khóa khác có thể cần secondary index và bước truy cập bổ sung. Hàng lớn hoặc có nhiều cột ngoài phần lưu trữ chỉ mục có thể cần cơ chế overflow tùy thiết kế.

IOT không phải lựa chọn mặc định cho mọi bảng. Cần đánh giá kích thước hàng, khóa chính, tỷ lệ đọc/ghi, truy vấn theo khóa khác và chi phí duy trì cấu trúc.

### 2.5. Phân biệt thứ tự logic và thứ tự vật lý

Thứ tự kết quả SQL chỉ được bảo đảm khi câu truy vấn có ORDER BY. Việc một bảng được tổ chức theo clustered key không có nghĩa truy vấn không có ORDER BY sẽ luôn trả hàng theo thứ tự đó.

Optimizer có thể chọn access path khác, thực hiện parallel scan, join hoặc sort. Ứng dụng không được dựa vào thứ tự vật lý tình cờ của bảng để đảm bảo thứ tự kết quả.

## 3. Mô hình tổ chức dữ liệu theo hệ quản trị

Cùng một thuật ngữ có thể mang ý nghĩa khác nhau giữa các sản phẩm. Khi đọc tài liệu hoặc execution plan, cần gắn khái niệm với đúng DBMS và phiên bản.

### 3.1. PostgreSQL: heap table và lệnh CLUSTER

PostgreSQL lưu hàng trong heap table. B-tree index lưu khóa và thông tin định vị tuple trong heap. Khi truy vấn dùng index scan, PostgreSQL có thể phải truy cập heap để kiểm tra hoặc lấy các cột chưa được đáp ứng bởi chỉ mục.

PostgreSQL có lệnh CLUSTER để sắp xếp lại các hàng của một bảng theo thứ tự của một chỉ mục đã có:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);

CLUSTER orders USING idx_orders_customer_created;
~~~

Lệnh này viết lại bảng theo thứ tự chỉ mục tại thời điểm thực hiện. Nó có thể cải thiện tính cục bộ cho truy vấn đọc các hàng theo customer_id và created_at nếu mẫu truy cập phù hợp.

Tuy nhiên, PostgreSQL CLUSTER không biến heap thành một clustered index được duy trì liên tục. Các INSERT và UPDATE sau đó không được tự động giữ đúng thứ tự đã sắp xếp. Theo thời gian, tính cục bộ có thể giảm và cần đánh giá việc chạy lại CLUSTER theo kế hoạch bảo trì.

CLUSTER cần khóa mạnh trên bảng trong thời gian thực hiện và có thể cần thêm không gian đĩa để tạo bản viết lại. Trước khi chạy trên hệ thống thật, phải xem kích thước bảng, thời gian khóa, dung lượng trống, replication, lịch bảo trì và tác động tới workload. Không nên dùng lệnh này như một thao tác tức thời cho bảng lớn đang phục vụ tải cao.

PostgreSQL cũng có thể sử dụng BRIN index cho dữ liệu có tương quan vật lý với một giá trị, chẳng hạn bảng sự kiện được nạp gần theo thứ tự thời gian. BRIN lưu thông tin tóm tắt theo vùng block, có kích thước nhỏ và hữu ích khi dữ liệu có tính cục bộ tốt. Nó không phải clustered index và không bảo đảm thứ tự hàng.

### 3.2. SQL Server: clustered index và heap

Trong SQL Server, clustered index xác định cách các hàng dữ liệu được tổ chức ở các trang lá của B-tree. Trang lá chứa chính dữ liệu hàng. Nếu bảng không có clustered index, nó là heap.

Một bảng SQL Server có thể có một clustered index. Các nonclustered index thường lưu khóa chỉ mục cùng row locator. Nếu bảng có clustered index, row locator trong nonclustered index thường là clustered key; nếu bảng là heap, locator có thể là RID.

Ví dụ:

~~~sql
CREATE CLUSTERED INDEX CX_Orders_OrderId
ON dbo.Orders (OrderId);
~~~

Khi truy vấn cần một dải OrderId, clustered index có thể cung cấp các trang lá theo thứ tự khóa. Truy vấn có thể đọc một vùng trang liên tiếp và lấy trực tiếp dữ liệu từ đó.

Nếu truy vấn chỉ cần các cột có trong nonclustered index, SQL Server có thể dùng covering index để tránh Key Lookup về clustered index hoặc RID Lookup về heap. Nếu cần nhiều hàng nhưng chỉ mục không bao phủ, nhiều lookup riêng lẻ có thể làm I/O tăng.

Khóa clustered có ảnh hưởng rộng vì được tham chiếu trong các nonclustered index. Một clustered key rộng làm tăng kích thước các chỉ mục phụ; khóa không ổn định hoặc thường xuyên cập nhật có thể gây chi phí duy trì. Vì vậy, clustered key thường nên có kích thước gọn, ổn định và phù hợp với các truy vấn quan trọng.

### 3.3. InnoDB của MySQL: primary key là clustered index

Trong InnoDB, dữ liệu của bảng được tổ chức trong clustered index, thường dựa trên primary key. Trang lá của clustered index chứa dữ liệu hàng. Nếu không khai báo primary key, InnoDB chọn một unique index không nullable phù hợp; nếu không có, InnoDB tạo định danh hàng nội bộ.

Các secondary index của InnoDB lưu khóa secondary cùng giá trị primary key để xác định hàng. Khi truy vấn dùng secondary index và cần cột không có trong secondary index, InnoDB có thể phải tra cứu clustered index bằng primary key. Đây thường được gọi là bước đọc kép (secondary index lookup rồi clustered index lookup).

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_created (customer_id, created_at)
) ENGINE = InnoDB;
~~~

Truy vấn theo customer_id và created_at có thể dùng secondary index. Nếu cần total_amount mà chỉ mục không chứa cột này, engine có thể truy cập clustered index để lấy phần còn lại của hàng.

Một secondary index bao gồm các cột cần truy vấn có thể trở thành covering index và giảm bước đọc clustered index. Tuy nhiên, mở rộng index làm tăng kích thước, buffer pool footprint và chi phí cập nhật. Chỉ nên thêm cột sau khi đo workload.

Khóa chính của InnoDB nên được chọn cẩn thận. Khóa dài làm mọi secondary index chứa phần định danh dài hơn. Khóa tăng tuần tự thường tạo vị trí chèn tập trung ở cuối cây, giúp tính cục bộ và giảm phân tán trang trong nhiều workload, nhưng có thể tạo điểm nóng ở mức ghi rất cao. Khóa ngẫu nhiên có thể phân tán vị trí chèn, làm page split và phân mảnh tăng; tuy nhiên, lựa chọn còn phụ thuộc tính duy nhất, phân tán ghi và yêu cầu nghiệp vụ.

### 3.4. Oracle: heap table, index và index-organized table

Oracle thường tổ chức bảng dưới dạng heap table, trong đó hàng có vị trí lưu trữ riêng và index dùng ROWID để định vị hàng. Một index range scan có thể tìm ROWID rồi thực hiện table access by rowid để lấy các cột còn thiếu.

Oracle cũng hỗ trợ index-organized table (IOT), trong đó dữ liệu được tổ chức theo primary key trong cấu trúc B-tree. IOT có thể giảm bước truy cập bảng cho truy vấn theo khóa chính hoặc phạm vi khóa chính.

Oracle có khái niệm clustering factor trong thống kê index. Clustering factor phản ánh mức độ tương quan giữa thứ tự khóa trong index và vị trí vật lý của hàng trong bảng heap. Giá trị gần với số block của bảng thường cho thấy các khóa gần nhau thường nằm trên các block gần nhau; giá trị gần với số hàng có thể cho thấy hàng theo thứ tự index phân tán qua nhiều block. Đây là chỉ số ước lượng chi phí table access by rowid, không phải phần trăm phân mảnh hoặc số block trống.

Nếu clustering factor cao đối với truy vấn thường xuyên quét một dải index rồi truy cập heap, số lần đọc block có thể lớn. IOT hoặc thay đổi cách tổ chức dữ liệu có thể đáng cân nhắc, nhưng phải đánh giá truy vấn khác và chi phí ghi.

### 3.5. Bảng so sánh

| Hệ quản trị | Tổ chức mặc định/khái niệm chính | Cách secondary index định vị dữ liệu | Điểm cần chú ý |
|---|---|---|---|
| PostgreSQL | Heap table; index tách biệt | TID/định vị tuple trong heap | CLUSTER chỉ sắp xếp lại một lần; không tự duy trì thứ tự |
| SQL Server | Clustered index hoặc heap | Clustered key hoặc RID | Một clustered index; nonclustered index mang row locator |
| MySQL InnoDB | Clustered index theo primary key hoặc khóa thay thế nội bộ | Secondary key cộng primary key | Khóa chính ảnh hưởng kích thước mọi secondary index |
| Oracle | Heap table hoặc IOT | ROWID ở heap; cấu trúc khóa ở IOT | Clustering factor giúp đánh giá tính cục bộ của index-to-table access |

Không nên chuyển nguyên một thiết kế clustered index từ SQL Server sang PostgreSQL hoặc InnoDB. Tên gọi giống nhau nhưng cơ chế lưu trữ, chi phí và cách duy trì khác nhau.

## 4. Tính cục bộ và các dấu hiệu trong access path

### 4.1. Index seek hoặc index scan không đảm bảo ít I/O

Một truy vấn dùng index vẫn có thể đọc nhiều trang. Ví dụ, một index range scan tìm được 100.000 khóa nhưng các hàng nằm trên nhiều trang heap khác nhau. DBMS phải thực hiện nhiều lần truy cập bảng để lấy các cột không nằm trong index.

Khi xem execution plan, hãy phân biệt:

- Số dòng được tìm thấy trong index.
- Số lần truy cập bảng hoặc heap.
- Số block hoặc page được đọc.
- Số lần lặp của nút con.
- Số dòng bị lọc sau khi lấy từ bảng.
- Index có bao phủ các cột truy vấn hay không.

Một access path dùng index có thể tốt hơn full scan khi điều kiện chọn lọc cao. Nhưng nếu truy vấn cần tỷ lệ lớn các hàng, việc đi qua index rồi đọc heap rời rạc có thể đắt hơn quét bảng tuần tự.

### 4.2. Range scan và tính cục bộ

Truy vấn phạm vi có thể tận dụng thứ tự khóa của B-tree. Ví dụ:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at < TIMESTAMP '2026-02-01 00:00:00'
ORDER BY created_at;
~~~

Một chỉ mục ghép trên (customer_id, created_at) có thể tìm đến vùng khóa của khách hàng 42 rồi đọc phạm vi thời gian liên quan. Nếu thứ tự vật lý của hàng hoặc các trang lá index có tính cục bộ tốt, số lần truy cập dữ liệu có thể giảm.

Cần nhớ B-tree index duy trì thứ tự khóa trong cấu trúc index, không nhất thiết đồng nghĩa heap table cũng được sắp xếp theo cùng thứ tự. Trong PostgreSQL và Oracle heap, bước truy cập heap vẫn có thể phân tán. Trong SQL Server clustered index và InnoDB clustered index, dữ liệu ở trang lá gắn với thứ tự khóa chính của cấu trúc clustered.

### 4.3. Covering index và index-only access

Một chỉ mục bao phủ truy vấn khi chứa đủ cột cần để lọc, nối, sắp xếp và trả kết quả. Khi đó, DBMS có thể tránh một phần hoặc toàn bộ bước truy cập bảng.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created_amount
ON orders (customer_id, created_at, total_amount);
~~~

Chỉ mục này có thể hỗ trợ truy vấn lấy total_amount theo customer_id và created_at. Tuy nhiên, việc đưa cột lớn hoặc nhiều cột vào index làm tăng kích thước và chi phí ghi.

Trong PostgreSQL, index-only scan còn phụ thuộc visibility map. Nếu trang heap chưa được đánh dấu all-visible, engine vẫn có thể phải kiểm tra heap để xác nhận khả năng nhìn thấy phiên bản hàng. Vì vậy, kế hoạch có thể ghi Index Only Scan nhưng vẫn có Heap Fetches. Cần đọc số liệu thực tế thay vì chỉ nhìn tên nút.

Trong SQL Server, nonclustered index có thể dùng INCLUDE để lưu các cột ở tầng lá mà không đưa chúng vào khóa sắp xếp. InnoDB không có cú pháp INCLUDE tương đương; các cột được thêm vào secondary index sẽ tham gia cấu trúc index theo quy tắc của engine.

### 4.4. Random lookup và lookup lặp

Một nested loop có thể chạy inner lookup nhiều lần. Mỗi lần lookup chỉ đọc ít trang, nhưng tổng số lần truy cập có thể rất lớn.

Ví dụ, outer relation có 50.000 dòng và mỗi dòng kích hoạt một lần lookup sang bảng khách hàng. Nếu các trang không nằm trong cache hoặc truy cập phân tán, tổng I/O có thể cao dù mỗi lookup riêng lẻ rẻ.

Khi xem kế hoạch, hãy nhân số lần thực hiện với chi phí mỗi lần ở mức phù hợp, đọc loops và buffer statistics. Nếu có thể, giảm số dòng outer trước khi join, dùng join strategy khác phù hợp hoặc bảo đảm index trên khóa nối.

## 5. Chọn clustered key và khóa chính

### 5.1. Tiêu chí lựa chọn

Khóa dùng để tổ chức dữ liệu nên được đánh giá theo nhiều thuộc tính:

- **Độ rộng:** khóa càng dài, cấu trúc index và các index tham chiếu có thể càng lớn.
- **Tính ổn định:** khóa ít thay đổi giúp giảm chi phí cập nhật cấu trúc.
- **Tính duy nhất:** khóa phải xác định hàng đúng theo yêu cầu.
- **Thứ tự chèn:** giá trị tăng dần, ngẫu nhiên hay phân bố theo tenant.
- **Tính cục bộ:** khóa có phù hợp với truy vấn phạm vi thường xuyên không?
- **Phân bố ghi:** chèn tập trung vào một vùng có tạo điểm nóng hay không?
- **Mức độ tương thích với workload:** truy vấn quan trọng thường lọc hoặc sắp xếp theo trường nào?

Không có một loại khóa tối ưu cho mọi ứng dụng. Khóa tự tăng có thể thuận lợi cho chèn tuần tự và gọn, nhưng không nhất thiết phù hợp cho mọi truy vấn. UUID ngẫu nhiên có thể thuận lợi cho định danh phân tán nhưng có thể làm index lớn và chèn rải rác. UUID có thứ tự thời gian hoặc khóa kết hợp có thể cân bằng một số đặc tính, nhưng phải xét cách sinh khóa và yêu cầu hệ thống.

### 5.2. Khóa rộng ảnh hưởng secondary index

Trong InnoDB, mỗi secondary index lưu primary key để tìm hàng trong clustered index. Trong SQL Server, nonclustered index dùng clustered key làm row locator khi bảng có clustered index. Vì vậy, khóa chính hoặc clustered key rộng có thể làm tất cả index phụ lớn hơn.

Ví dụ, nếu bảng có tám secondary index và khóa chính là một chuỗi dài, phần khóa lặp lại trong các index phụ có thể làm tăng đáng kể dung lượng, số trang và áp lực cache. Một khóa thay thế nhỏ, ổn định có thể giảm chi phí này; khóa nghiệp vụ vẫn có thể được bảo vệ bằng unique constraint hoặc unique index riêng.

Tuy nhiên, thêm khóa thay thế cũng tạo thêm một cấu trúc và có thể thay đổi truy vấn. Cần đo tổng chi phí và không thay đổi khóa chỉ dựa trên kích thước lý thuyết.

### 5.3. Khóa tuần tự và điểm nóng ghi

Khóa tăng tuần tự thường khiến các bản ghi mới được chèn gần vùng cuối của B-tree. Điều này có thể giảm phân tán và cải thiện tính cục bộ. Nhưng khi số luồng ghi rất cao, nhiều giao dịch có thể cùng cập nhật vùng trang gần cuối, tạo tranh chấp latch hoặc page contention tùy engine.

Khóa ngẫu nhiên phân tán vị trí chèn, giảm tập trung ở một vùng nhưng có thể gây page split, phân mảnh và truy cập cache kém cục bộ. Các khóa có thứ tự gần thời gian có thể giảm một phần vấn đề phân tán mà vẫn giữ tính tăng trưởng.

Cần xác định vấn đề thực tế bằng wait statistics, page split, throughput ghi, buffer usage và độ trễ. Không nên đổi kiểu khóa chỉ dựa trên một nhận định chung rằng sequential luôn tốt hoặc random luôn xấu.

## 6. Page split, fragmentation và fill factor

### 6.1. Page split là gì?

B-tree lưu khóa trong các trang được sắp xếp. Khi một trang lá không còn đủ chỗ cho khóa mới ở vị trí cần chèn, engine có thể phải tách trang (page split), phân phối các mục sang trang mới và cập nhật cấu trúc liên quan.

Page split có thể:

- Tạo thêm thao tác ghi và WAL/transaction log.
- Làm tăng số trang trong index.
- Thay đổi tính cục bộ của trang.
- Tạo thêm công việc cho backup, replication và cache.
- Làm tăng độ trễ của thao tác chèn hoặc cập nhật trong một số workload.

Mức độ và cách xử lý page split khác nhau giữa các engine. Không nên dùng số lượng page split riêng lẻ để kết luận index thiết kế sai; cần xem tốc độ split, loại workload và tác động đến latency.

### 6.2. Fragmentation và tính cục bộ

Fragmentation thường mô tả tình trạng trang hoặc vùng dữ liệu không còn được tổ chức thuận lợi cho mẫu truy cập. Tùy DBMS, thuật ngữ có thể nói đến mức lấp đầy trang, thứ tự logic so với thứ tự vật lý hoặc sự phân tán của các trang.

Trong heap, việc UPDATE làm hàng dài hơn có thể cần chuyển phiên bản hàng hoặc tạo tuple mới ở vị trí khác. Trong B-tree, chèn khóa ngẫu nhiên có thể làm trang tách và thứ tự vật lý của các trang không còn liền mạch trên lưu trữ. Tuy nhiên, trên SSD, tác động của phân mảnh vật lý khác với HDD; không nên mặc định rebuild mọi index theo một lịch cố định mà không đo.

### 6.3. Fill factor

Fill factor quy định mức độ lấp đầy mục tiêu của trang khi tạo hoặc xây dựng lại một số loại index/bảng. Để lại không gian trống có thể giảm page split khi dữ liệu mới được chèn gần vị trí hiện có, đổi lại index lớn hơn và có thể cần thêm trang để đọc.

Ví dụ trên PostgreSQL, có thể đặt fillfactor cho một B-tree index:

~~~sql
CREATE INDEX idx_events_tenant_time
ON events (tenant_id, created_at)
WITH (fillfactor = 85);
~~~

Giá trị 85 chỉ là ví dụ, không phải mức khuyến nghị chung. Nếu workload chủ yếu đọc và ít cập nhật, mức lấp đầy cao có thể tiết kiệm dung lượng. Nếu có nhiều cập nhật hoặc chèn vào giữa khóa, để lại khoảng trống có thể giúp giảm split. Phải kiểm tra tài liệu của DBMS và đo trên workload thật.

### 6.4. Rebuild hoặc reorganize có luôn cải thiện không?

Rebuild hoặc reorganize index có thể thay đổi cách trang được sắp xếp và mức lấp đầy, nhưng cũng tiêu thụ I/O, CPU, dung lượng tạm và có thể khóa hoặc cạnh tranh với workload. Với một số engine, thao tác có thể chạy online ở mức giới hạn nhất định; với engine khác, cần cửa sổ bảo trì.

Chỉ thực hiện khi số liệu cho thấy vấn đề cụ thể và lợi ích dự kiến lớn hơn chi phí. Sau thao tác, đo lại kế hoạch, số trang, latency đọc/ghi và ảnh hưởng tới hệ thống.

## 7. Đọc execution plan để đánh giá access path

### 7.1. Những nút cần nhận diện

Tên nút khác nhau theo DBMS, nhưng có thể nhóm theo ý nghĩa:

| Loại access path | Ý nghĩa khái quát | Câu hỏi khi phân tích |
|---|---|---|
| Table/Sequential Scan | Đọc nhiều hoặc toàn bộ bảng | Có thực sự cần quét nhiều hàng không? |
| Index Seek/Range Scan | Tìm khóa hoặc quét một dải index | Bao nhiêu khóa được tìm và bao nhiêu hàng được đọc? |
| Index Scan | Duyệt một phần hoặc toàn bộ index | Có phải index nhỏ hơn bảng hoặc bao phủ truy vấn? |
| Bitmap access | Gom vị trí hàng rồi truy cập bảng theo nhóm | Số block heap có giảm so với lookup rời rạc không? |
| Key Lookup/RowID Lookup | Dùng định danh từ index để lấy hàng | Có quá nhiều lookup riêng lẻ không? |
| Index Only/Covering access | Lấy kết quả từ index mà không cần đọc bảng ở mức có thể | Có heap fetch hoặc cột thiếu nào không? |

Không thể kết luận một access path tốt chỉ từ tên. Hãy xem actual rows, loops, logical/physical reads, buffer counts, lookup count và thời gian.

### 7.2. SQL Server: Key Lookup và RID Lookup

Với bảng có clustered index, nonclustered index có thể tìm được một tập khóa nhưng thiếu các cột cần trả về. SQL Server phải thực hiện Key Lookup để lấy hàng từ clustered index.

Nếu bảng là heap, bước tương tự có thể là RID Lookup. Khi số dòng cần lookup nhỏ, chi phí này có thể chấp nhận được. Khi hàng chục nghìn hoặc hàng triệu lookup được thực hiện, chi phí ngẫu nhiên có thể lớn.

Một hướng thử là tạo covering nonclustered index với các cột INCLUDE phù hợp. Nhưng chỉ mục mới tăng chi phí ghi và dung lượng. Hãy đo số lần lookup, logical reads và tác động của truy vấn ghi.

### 7.3. PostgreSQL: Index Scan, Bitmap Heap Scan và Index Only Scan

PostgreSQL có thể chọn:

- Index Scan: duyệt index và truy cập heap theo TID.
- Bitmap Index Scan kết hợp Bitmap Heap Scan: gom các vị trí tuple rồi truy cập heap theo nhóm block, có thể giảm truy cập ngẫu nhiên khi nhiều hàng được chọn.
- Index Only Scan: trả kết quả từ index khi dữ liệu cần thiết có trong index và visibility map cho phép tránh heap fetch.

Một Bitmap Heap Scan có thể xuất hiện khi điều kiện chọn nhiều hàng hơn mức phù hợp với các lần lookup riêng lẻ nhưng vẫn không cần quét toàn bảng. Nếu bitmap trở nên lossy, DBMS phải kiểm tra lại điều kiện trên các hàng trong block. Execution plan có thể cho biết số heap blocks exact/lossy và số dòng bị recheck.

Hãy đọc cả số block, heap fetches và actual rows để hiểu vì sao optimizer chọn đường truy cập.

### 7.4. Oracle: Index Range Scan và Table Access by ROWID

Oracle thường có thể thực hiện Index Range Scan để tìm khóa trong B-tree, sau đó dùng ROWID để lấy hàng từ heap table. Nếu clustering factor cao, các ROWID có thể trỏ đến nhiều block phân tán, làm bước table access tốn nhiều I/O.

Index-only access có thể tránh đọc bảng nếu mọi cột cần thiết đã có trong index và điều kiện phù hợp. Nhưng thêm cột vào index làm tăng dung lượng và chi phí duy trì. Hãy kiểm tra actual plan và số buffer gets/physical reads khi có thống kê thực thi phù hợp.

## 8. Ví dụ lựa chọn tổ chức dữ liệu

### 8.1. Bảng đơn hàng truy vấn theo khách hàng và thời gian

Giả sử bảng orders có hàng trăm triệu dòng. Những truy vấn quan trọng thường lấy 50 đơn hàng gần nhất của một khách hàng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

Một chỉ mục ghép trên customer_id và created_at có thể hỗ trợ lọc theo khách hàng rồi đọc theo thời gian. Trong PostgreSQL heap, truy vấn có thể dùng index scan và sau đó truy cập heap; nếu index bao phủ các cột cần thiết và visibility map phù hợp, có thể dùng index-only scan. Trong SQL Server, clustered key hoặc nonclustered covering index có thể được chọn tùy cách tổ chức bảng. Trong InnoDB, secondary index sẽ chứa primary key và có thể cần tra cứu clustered index để lấy total_amount nếu cột này không được bao phủ.

Câu hỏi thiết kế:

- Truy vấn này chiếm bao nhiêu phần trăm workload?
- Có nhiều truy vấn khác lọc theo thời gian toàn cục không?
- Dữ liệu của một khách hàng có thường được đọc liên tục không?
- Tổng số hàng trả về mỗi khách hàng có nhỏ so với toàn bảng không?
- Chi phí cập nhật total_amount hoặc created_at có đáng kể không?
- Thêm total_amount vào index có làm index quá lớn không?

Nếu truy vấn theo khách hàng chiếm tỷ trọng lớn và dữ liệu có tính cục bộ phù hợp, một index ghép có thể là lựa chọn tốt. Việc cluster vật lý bảng theo cùng thứ tự chỉ đáng xem xét khi nhiều truy vấn heap access được hưởng lợi và chi phí duy trì phù hợp.

### 8.2. Bảng sự kiện ghi liên tục theo thời gian

Một bảng events nhận dữ liệu liên tục và thường được truy vấn theo khoảng thời gian gần đây. Nếu dữ liệu được nạp gần theo thứ tự created_at, các trang có thể có tương quan vật lý với thời gian.

Trong PostgreSQL, BRIN index trên created_at có thể giúp loại bỏ các vùng block không liên quan mà không cần B-tree lớn như một index đầy đủ. BRIN hiệu quả khi thứ tự vật lý tương quan tốt với giá trị cột. Nếu các sự kiện được ghi trễ hoặc chèn thời gian ngẫu nhiên, hiệu quả có thể giảm.

Trong SQL Server, một clustered index theo thời gian có thể làm dữ liệu nằm theo thứ tự khóa, nhưng cần đánh giá điểm nóng ghi ở vùng cuối và truy vấn theo tenant hoặc event_type. Trong InnoDB, chọn created_at làm primary key có thể làm mọi secondary index mang khóa thời gian; đây có thể là lựa chọn không phù hợp nếu định danh nghiệp vụ khác hoặc truy vấn theo khóa khác chiếm ưu thế.

Không nên áp dụng cùng một thiết kế cho mọi hệ quản trị. Hãy đánh giá cách mỗi engine tổ chức bảng và secondary index.

### 8.3. Bảng giao dịch cập nhật nhiều

Một bảng giao dịch có nhiều INSERT và UPDATE, trong khi truy vấn đọc theo nhiều khóa khác nhau. Clustered key nên ổn định và gọn; các secondary index chỉ nên được tạo cho access path có giá trị cao.

Nếu tạo quá nhiều index để phục vụ mọi truy vấn, mỗi INSERT/UPDATE phải duy trì thêm cấu trúc, tăng WAL hoặc transaction log, áp lực cache và dung lượng lưu trữ. Nếu một khóa clustered thay đổi thường xuyên, chi phí có thể lan sang các index phụ ở engine dùng clustered key làm locator.

Hãy ưu tiên workload có tần suất cao hoặc mục tiêu độ trễ nghiêm ngặt. Những truy vấn ít dùng có thể chấp nhận scan hoặc được xử lý bằng báo cáo/tác vụ nền riêng.

## 9. Quy trình kiểm chứng thay đổi tổ chức dữ liệu

Một thay đổi clustered key, index hoặc cách sắp xếp bảng có ảnh hưởng rộng. Hãy kiểm chứng theo trình tự:

1. **Chọn workload:** liệt kê các truy vấn đọc/ghi quan trọng, tỷ lệ gọi và mức đồng thời.
2. **Ghi đường cơ sở:** lưu kế hoạch thực thi, logical reads, buffer hit/read, physical I/O, latency p50/p95/p99, throughput và lỗi.
3. **Đo tính cục bộ:** xem số block hoặc page được truy cập, clustering factor nếu DBMS cung cấp, heap fetches, lookup count và phân bố dữ liệu.
4. **Nêu giả thuyết:** ví dụ một truy vấn phạm vi đọc quá nhiều trang heap do hàng phân tán hoặc secondary index gây quá nhiều lookup.
5. **Thử một thay đổi:** tạo index ghép, covering index, thay đổi clustered key hoặc sắp xếp lại bảng trong môi trường thử nghiệm.
6. **Chạy cùng workload:** giữ nguyên dữ liệu, tham số, mức đồng thời, cache policy và cửa sổ đo.
7. **Đánh giá cả đọc lẫn ghi:** đo latency và throughput của truy vấn mục tiêu cùng INSERT, UPDATE, DELETE và các truy vấn khác.
8. **Kiểm tra chi phí vận hành:** dung lượng index, thời gian build/rebuild, khóa, log, replication và không gian đĩa.
9. **Giữ hoặc hoàn tác:** chỉ giữ thay đổi khi lợi ích có thể lặp lại và hệ thống vẫn đáp ứng các mục tiêu khác.

### 9.1. Bảng so sánh trước và sau

| Chỉ số | Trước | Sau | Ý nghĩa |
|---|---:|---:|---|
| p95 truy vấn khách hàng | 180 ms | 65 ms | Cải thiện truy vấn mục tiêu |
| Logical/buffer reads | 8.500 | 2.100 | Giảm lượng trang được chạm tới |
| Physical reads | 900 | 180 | Giảm đọc từ tầng lưu trữ được đo |
| INSERT p95 | 12 ms | 19 ms | Chi phí ghi tăng |
| Index size | 4 GB | 6 GB | Tăng dung lượng |
| Deadlock | 0 | 0 | Không tăng trong lần thử |

Các con số là ví dụ minh họa, không phải ngưỡng chuẩn. Một thay đổi có thể chấp nhận nếu lợi ích đọc phù hợp mục tiêu và chi phí ghi, dung lượng vẫn nằm trong ngân sách. Nếu chỉ cải thiện một truy vấn nhưng làm nhiều transaction ghi chậm vượt mục tiêu, thiết kế cần được xem lại.

### 9.2. Kiểm tra tính đúng đắn và độ bền

Tổ chức dữ liệu và index không được làm thay đổi ngữ nghĩa truy vấn hoặc bảo đảm giao dịch. Sau khi thay đổi, cần kiểm tra:

- Kết quả truy vấn giống với tập dữ liệu chuẩn.
- Unique constraint và foreign key vẫn được bảo đảm.
- INSERT/UPDATE/DELETE không tạo mất hoặc trùng hàng.
- Transaction và isolation vẫn hoạt động đúng.
- Replication, backup và recovery đáp ứng yêu cầu.
- Các truy vấn không thuộc workload chính không bị suy giảm nghiêm trọng.

Không dùng kết quả benchmark đơn thuần để kết luận một thay đổi phù hợp cho production.

## 10. Những sai lầm thường gặp

**Cho rằng clustered index có nghĩa mọi truy vấn đều nhanh hơn.**  
Clustered order chỉ ưu tiên một thứ tự dữ liệu. Truy vấn theo khóa khác có thể vẫn cần secondary index hoặc đọc nhiều trang.

**Cho rằng PostgreSQL CLUSTER tự duy trì thứ tự sau mỗi lần ghi.**  
Lệnh CLUSTER sắp xếp lại bảng tại thời điểm chạy. Các thay đổi sau đó không được tự động tổ chức lại theo thứ tự index.

**Dùng một clustered key cho mọi workload.**  
Một khóa phù hợp truy vấn phạm vi theo thời gian có thể không phù hợp truy vấn theo tenant hoặc khóa nghiệp vụ khác.

**Chọn khóa chính quá rộng.**  
Trong InnoDB và SQL Server, khóa chính hoặc clustered key có thể được lặp trong secondary index. Khóa rộng làm tăng dung lượng và áp lực cache.

**Cho rằng index seek luôn rẻ hơn scan.**  
Nếu truy vấn cần nhiều hàng và phải lookup rời rạc, scan có thể rẻ hơn. Hãy so sánh số trang và thời gian thực tế.

**Tạo covering index cho mọi truy vấn.**  
Index lớn làm tăng chi phí ghi, build, backup và cache. Chỉ thêm cột khi workload chứng minh lợi ích.

**Nhầm fragmentation với một nguyên nhân duy nhất.**  
Page split, mức lấp đầy, thứ tự vật lý và cache là những yếu tố khác nhau. Chọn biện pháp theo chỉ số cụ thể.

**Chạy CLUSTER hoặc rebuild trên bảng lớn mà không tính thời gian khóa và dung lượng.**  
Các thao tác viết lại dữ liệu có thể cần không gian và cửa sổ bảo trì đáng kể.

**Dựa vào thứ tự vật lý để bảo đảm kết quả SQL.**  
Chỉ ORDER BY mới bảo đảm thứ tự kết quả.

## 11. Mẫu phân tích access path

Khi review một truy vấn hoặc đề xuất thay đổi tổ chức bảng, có thể ghi nhận theo mẫu:

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Workload | Truy vấn nào quan trọng, tần suất và mức đồng thời ra sao? |
| Điều kiện truy cập | Lọc theo khóa đơn, phạm vi, thời gian hay nhiều cột? |
| Tổ chức bảng | Heap, clustered index, InnoDB clustered primary key hay IOT? |
| Chỉ mục | Khóa, thứ tự cột, độ rộng và cột bao phủ là gì? |
| Access path | Scan, seek, range scan, lookup, bitmap hay index-only? |
| Tính cục bộ | Hàng liên quan có nằm gần nhau không? Có clustering factor hoặc số block hỗ trợ không? |
| Chi phí đọc | Logical reads, buffer reads, physical I/O, heap fetches và latency? |
| Chi phí ghi | Page split, index maintenance, log, lock và throughput ghi? |
| Chi phí vận hành | Dung lượng, build/rebuild, khóa và ảnh hưởng replication? |
| Kiểm chứng | Cùng workload trước/sau có cải thiện lặp lại không? |

Ví dụ nhận định có cơ sở:

“Truy vấn lấy đơn hàng gần nhất của một khách hàng đang dùng secondary index nhưng phải thực hiện nhiều lần đọc heap. Các hàng được truy cập phân tán trên nhiều block. Một covering index có thể giảm bước đọc bảng; cần thử và đo kích thước index, chi phí INSERT/UPDATE cùng p95 của các truy vấn liên quan.”

Hoặc:

“Trong SQL Server, nonclustered index tìm được các khóa nhưng Key Lookup được thực hiện hàng chục nghìn lần. Một covering index có INCLUDE cho các cột trả về có thể giảm lookup. Cần xác nhận logical reads và chi phí ghi sau thay đổi.”

Một nhận định tốt phân biệt rõ dữ liệu quan sát được, giả thuyết và biện pháp cần thử. Nó không kết luận chỉ từ tên index hoặc một chỉ số fragmentation.

## 12. Kết luận

Chỉ mục phân cụm và cách tổ chức bảng quyết định cách DBMS đặt dữ liệu trên các trang, cách secondary index định vị hàng và số lần truy cập cần thiết cho một workload. Heap table, clustered index và index-organized table có cơ chế khác nhau; PostgreSQL, SQL Server, InnoDB và Oracle cũng có cách triển khai riêng. Vì vậy, phải hiểu đúng semantics của hệ quản trị đang dùng trước khi áp dụng một thiết kế.

Khi lựa chọn access path, hãy xem tính chọn lọc, số dòng thực tế, số trang được truy cập, lookup count, covering access, clustering factor hoặc heap fetches nếu có. Clustered key cần được đánh giá theo độ rộng, tính ổn định, thứ tự chèn, phân bố ghi và truy vấn quan trọng. Một chỉ mục giúp đọc nhanh có thể làm ghi chậm và tăng dung lượng; một thao tác sắp xếp lại bảng có thể cải thiện locality nhưng cần khóa và không gian vận hành.

Quyết định tối ưu chỉ được xác nhận khi phép đo lặp lại dưới workload đại diện cho thấy lợi ích về độ trễ hoặc thông lượng, chi phí ghi và vận hành vẫn chấp nhận được, và dữ liệu giữ nguyên tính đúng đắn.

## Câu hỏi tự kiểm tra

1. Data locality ảnh hưởng thế nào đến số trang cần đọc và chi phí I/O?
2. Heap table và clustered index khác nhau ở cách tổ chức hàng dữ liệu nào?
3. Vì sao PostgreSQL CLUSTER không tương đương clustered index được duy trì liên tục trong SQL Server?
4. InnoDB lưu primary key trong secondary index để phục vụ mục đích gì?
5. Clustering factor của Oracle giúp ước lượng điều gì?
6. Vì sao một Index Scan có thể gây nhiều I/O hơn một Sequential Scan?
7. Covering index giảm bước truy cập nào và tạo thêm chi phí gì?
8. Khóa clustered rộng hoặc thường xuyên thay đổi có thể ảnh hưởng secondary index ra sao?
9. Page split và fill factor liên quan thế nào đến workload ghi?
10. Hãy thiết kế phép thử để so sánh heap access với một phương án tổ chức dữ liệu có tính cục bộ tốt hơn, bao gồm cả truy vấn đọc và ghi.

Một thiết kế access path tốt là thiết kế được chứng minh bằng số liệu của workload thật: dữ liệu cần đọc được tìm thấy hiệu quả, chi phí ghi có thể kiểm soát và hệ thống duy trì đúng các bảo đảm dữ liệu.

