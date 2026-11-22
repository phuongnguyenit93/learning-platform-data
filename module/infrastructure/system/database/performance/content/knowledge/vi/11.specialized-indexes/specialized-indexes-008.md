# Columnstore và đánh đổi giữa tải phân tích với cập nhật dữ liệu

Trong chương **Chỉ mục chuyên biệt** của module **DATABASE_PERFORMANCE**, columnstore là một cách tổ chức dữ liệu phù hợp với những truy vấn phải đọc nhiều dòng nhưng chỉ cần một số cột. Cơ sở dữ liệu dạng hàng (*rowstore*) lưu các cột của một dòng gần nhau, thuận tiện khi ứng dụng tra cứu hoặc cập nhật một vài dòng. Cơ sở dữ liệu dạng cột (*columnstore*) lưu dữ liệu theo từng cột hoặc từng nhóm giá trị cột, nhờ đó có thể đọc ít dữ liệu hơn khi truy vấn phân tích cần quét hàng triệu dòng để tính tổng, đếm, lọc hoặc nhóm.

Columnstore thường giúp giảm I/O nhờ chỉ đọc những cột cần thiết, nén dữ liệu hiệu quả và xử lý theo lô. Đổi lại, các thao tác ghi nhỏ, cập nhật thường xuyên và tra cứu từng dòng có thể kém thuận lợi hơn rowstore. Khi chọn columnstore, cần xem xét hình dạng workload: tỷ lệ đọc phân tích so với giao dịch, kích thước batch ghi, độ mới dữ liệu cần có, yêu cầu độ trễ và chi phí duy trì chỉ mục.

## 1. Rowstore và columnstore khác nhau thế nào?

Giả sử bảng `sales` có các cột `sale_id`, `customer_id`, `product_id`, `sale_date`, `quantity`, `unit_price` và `region`.

Với rowstore, dữ liệu của một giao dịch được lưu gần nhau theo dòng:

| sale_id | customer_id | product_id | sale_date | quantity | unit_price | region |
|---:|---:|---:|---|---:|---:|---|
| 1001 | 42 | 17 | 2026-01-05 | 2 | 150 | South |
| 1002 | 18 | 31 | 2026-01-05 | 1 | 90 | North |
| 1003 | 42 | 22 | 2026-01-06 | 4 | 45 | South |

Rowstore phù hợp với câu lệnh lấy một giao dịch theo khóa chính hoặc cập nhật một vài cột của một dòng. Khi đọc một dòng, hệ quản trị thường lấy cả trang dữ liệu chứa dòng đó; các cột liên quan nằm cùng một cấu trúc lưu trữ.

Với columnstore, giá trị của cùng một cột được lưu cùng nhau theo segment hoặc nhóm dữ liệu:

| sale_id | 1001 | 1002 | 1003 | ... |
|---|---:|---:|---:|---|
| customer_id | 42 | 18 | 42 | ... |
| product_id | 17 | 31 | 22 | ... |
| sale_date | 2026-01-05 | 2026-01-05 | 2026-01-06 | ... |
| quantity | 2 | 1 | 4 | ... |
| unit_price | 150 | 90 | 45 | ... |
| region | South | North | South | ... |

Đây là hình minh họa logic; định dạng vật lý cụ thể tùy hệ quản trị. Nếu báo cáo chỉ cần `sale_date`, `quantity` và `unit_price`, columnstore có thể chỉ đọc các segment của những cột này. Với rowstore, engine thường phải đọc các trang chứa những dòng liên quan, trong đó dữ liệu của nhiều cột khác cũng nằm cùng trang.

### 1.1. Vì sao columnstore thường nén tốt

Các giá trị trong cùng một cột thường có kiểu dữ liệu và miền giá trị tương tự. Ví dụ, một cột `region` có thể chỉ chứa một số mã lặp lại; một cột ngày tháng có thể có nhiều giá trị gần nhau. Hệ quản trị có thể dùng những kỹ thuật như dictionary encoding, run-length encoding, bit packing hoặc các dạng nén theo miền giá trị để giảm dung lượng.

Nén không chỉ tiết kiệm đĩa. Khi một truy vấn đọc ít byte hơn, nó có thể giảm I/O và tăng số dòng xử lý trong cùng lượng bộ nhớ. Tuy nhiên, dữ liệu vẫn cần được giải mã hoặc xử lý bằng các toán tử phù hợp; mức nén cao không tự động bảo đảm mọi truy vấn nhanh hơn.

### 1.2. Đọc theo cột và xử lý theo lô

Columnstore thường có lợi khi truy vấn đọc một tập lớn nhưng chỉ tham chiếu một phần nhỏ các cột. Một số hệ quản trị kết hợp columnstore với *batch mode* hoặc vectorized execution: thay vì xử lý từng dòng riêng lẻ, engine áp dụng phép toán lên một nhóm giá trị cùng lúc. Cách xử lý này có thể giảm overhead của iterator và tận dụng CPU hiệu quả hơn.

Ví dụ truy vấn phân tích:

```sql
SELECT region,
       SUM(quantity * unit_price) AS revenue,
       COUNT(*) AS sale_count
FROM sales
WHERE sale_date >= '2026-01-01'
  AND sale_date <  '2026-02-01'
GROUP BY region;
```

Truy vấn cần đọc ngày bán, số lượng, đơn giá và khu vực, sau đó lọc và tổng hợp một tập lớn. Columnstore có thể đọc đúng các cột liên quan, loại bỏ segment không thuộc khoảng ngày và thực hiện tổng hợp theo lô.

Ngược lại, truy vấn lấy một giao dịch theo `sale_id` thường cần tìm một dòng. Rowstore với chỉ mục B-tree trên khóa chính thường phù hợp hơn vì columnstore không được thiết kế chủ yếu cho các phép tra cứu điểm có độ chọn lọc rất cao.

## 2. Các thành phần thường gặp trong columnstore

Tên gọi và chi tiết triển khai khác nhau giữa các sản phẩm, nhưng nhiều columnstore có những khái niệm sau:

- **Row group:** một nhóm dòng được nén và tổ chức thành các segment cột. Kích thước nhóm ảnh hưởng hiệu quả nén, khả năng song song và mức loại bỏ dữ liệu.
- **Column segment:** phần lưu trữ giá trị của một cột trong một row group. Truy vấn chỉ cần một số cột có thể chỉ đọc các segment tương ứng.
- **Metadata min/max:** thông tin giá trị nhỏ nhất và lớn nhất của segment hoặc nhóm dữ liệu. Optimizer có thể bỏ qua segment nếu điều kiện lọc chắc chắn không khớp (*segment elimination*).
- **Dictionary:** bảng ánh xạ giá trị sang mã nhỏ hơn để nén các cột có nhiều giá trị lặp lại.
- **Delta store hoặc vùng ghi đệm:** nơi nhận các dòng mới trước khi chúng được gom và nén thành row group, trong các kiến trúc hỗ trợ cơ chế này.
- **Delete bitmap hoặc metadata xóa:** ghi nhận các dòng đã bị xóa logic khỏi row group; việc dọn và nén lại có thể diễn ra sau đó.

Không phải mọi hệ quản trị đều sử dụng cùng cấu trúc hoặc có tên thành phần giống nhau. Hãy xem tài liệu của sản phẩm và phiên bản đang vận hành trước khi áp dụng quy trình bảo trì cụ thể.

## 3. Workload nào phù hợp với columnstore?

| Đặc điểm workload | Rowstore thường phù hợp | Columnstore thường phù hợp |
|---|---|---|
| Tra cứu theo khóa chính, trả một vài dòng | Rất phù hợp | Có thể không hiệu quả bằng chỉ mục hàng |
| Ghi một dòng hoặc cập nhật một vài cột liên tục | Rất phù hợp | Có thể phát sinh chi phí duy trì và gom nhóm dữ liệu |
| Quét hàng triệu dòng để tính tổng | Có thể phải đọc nhiều trang và cột không cần thiết | Thường có lợi nhờ đọc theo cột và nén |
| Báo cáo đọc một số ít cột trong bảng rộng | Có thể tốn I/O nếu không có covering index | Thường có lợi vì chỉ đọc các cột được tham chiếu |
| Nạp dữ liệu theo batch lớn | Phù hợp tùy thiết kế | Thường phù hợp khi có thể tạo row group lớn và nén hiệu quả |
| Cập nhật/xóa hàng loạt theo partition | Có thể đơn giản với chỉ mục hàng | Có thể hiệu quả nếu dùng quy trình partition hoặc batch phù hợp |
| Truy vấn hỗn hợp OLTP và phân tích | Cần chỉ mục và thiết kế cẩn thận | Có thể kết hợp rowstore với columnstore tùy hệ quản trị |

Columnstore đặc biệt hữu ích cho fact table trong kho dữ liệu, bảng sự kiện lớn, dữ liệu đo lường và báo cáo tổng hợp. Rowstore thường phù hợp với bảng giao dịch có nhiều thao tác đọc/ghi theo khóa. Nhiều hệ thống cần cả hai: rowstore phục vụ giao dịch và columnstore hoặc nền tảng phân tích phục vụ báo cáo.

## 4. Đánh đổi khi dữ liệu được cập nhật thường xuyên

Columnstore được tối ưu cho việc nạp và đọc các nhóm dòng lớn. Khi ứng dụng liên tục chèn, sửa hoặc xóa từng dòng, engine phải xử lý thêm các vùng ghi đệm, trạng thái xóa và quá trình nén.

### 4.1. Chèn dữ liệu

Một số triển khai không nén từng dòng mới ngay lập tức. Dữ liệu có thể đi vào delta store hoặc hàng đợi ghi, sau đó được gom thành row group khi đủ điều kiện. Điều này giúp tránh tạo nhiều row group rất nhỏ, nhưng có thể làm dữ liệu mới chưa đạt mức nén tối ưu ngay.

Nếu workload chỉ chèn từng dòng với tốc độ cao, cần đo:

- Độ trễ insert và throughput ghi.
- Số row group nhỏ hoặc chưa nén.
- Dung lượng vùng ghi đệm và tốc độ chuyển dữ liệu sang vùng nén.
- Độ trễ để dữ liệu mới xuất hiện trong truy vấn phân tích.
- Mức tranh chấp giữa luồng nạp dữ liệu và truy vấn quét lớn.

Nạp theo batch thường giúp tạo row group lớn hơn, cải thiện nén và giảm overhead trên mỗi dòng. Kích thước batch cần phù hợp với bộ nhớ, log, cửa sổ ETL và yêu cầu độ mới dữ liệu.

### 4.2. Cập nhật dữ liệu

Trong một số columnstore, cập nhật có thể được thực hiện như đánh dấu phiên bản cũ đã bị xóa và chèn phiên bản mới vào vùng ghi hoặc row group khác. Cách triển khai này thuận lợi cho đọc phân tích nhưng có thể tạo thêm delete bitmap, dòng tồn dư và công việc bảo trì.

Nếu ứng dụng cập nhật cùng một nhóm dòng nhiều lần, hãy kiểm tra số dòng bị đánh dấu xóa, số row group chưa tối ưu, chi phí log và tốc độ cập nhật thực tế. Các cập nhật nhỏ thường xuyên có thể kém hiệu quả hơn một batch update được tổ chức hợp lý.

### 4.3. Xóa dữ liệu

Xóa logic có thể được ghi vào metadata thay vì lập tức tái ghi toàn bộ segment. Điều này giúp thao tác xóa hoàn tất mà không phải nén lại ngay, nhưng dữ liệu đã xóa vẫn có thể chiếm dung lượng cho tới khi được dọn hoặc row group được tổ chức lại.

Với dữ liệu lịch sử, partitioning theo ngày/tháng có thể cho phép loại bỏ một partition cũ thay vì xóa từng dòng. Partition switch, detach hoặc drop partition có thể giảm lượng công việc so với xóa hàng triệu dòng, tùy khả năng hệ quản trị và quy trình lưu trữ.

### 4.4. Nén và bảo trì row group

Row group quá nhỏ thường nén kém, tăng metadata và giảm hiệu quả scan. Row group quá lớn hoặc batch nạp quá lớn cũng có thể tạo áp lực bộ nhớ, thời gian nạp hoặc độ trễ sẵn sàng. Cần theo dõi số lượng row group, trạng thái nén, số dòng đã xóa và kích thước segment.

Các thao tác reorganize, merge, compress hoặc rebuild có thể cải thiện chất lượng row group, nhưng tiêu thụ CPU, I/O, bộ nhớ và log. Một số thao tác có thể cạnh tranh với workload đang chạy hoặc yêu cầu khóa tùy phiên bản/edition. Lập lịch bảo trì và đo tác động trước khi thực hiện trên production.

## 5. SQL Server: clustered và nonclustered columnstore

SQL Server cung cấp columnstore index ở cấp bảng hoặc như một chỉ mục bổ sung trên rowstore.

### 5.1. Clustered columnstore index

Clustered columnstore lưu bảng chính theo định dạng columnstore. Đây là lựa chọn phổ biến cho fact table lớn trong data warehouse, nơi phần lớn truy vấn đọc và tổng hợp nhiều dòng.

Ví dụ tạo clustered columnstore index:

```sql
CREATE CLUSTERED COLUMNSTORE INDEX CCI_FactSales
ON dbo.FactSales;
```

Khi bảng đã có clustered columnstore, các truy vấn phân tích có thể dùng columnstore scan, segment elimination và batch mode khi đủ điều kiện. Truy vấn theo khóa đơn lẻ vẫn có thể cần cấu trúc bổ trợ hoặc thiết kế khác tùy workload.

### 5.2. Nonclustered columnstore index

Nonclustered columnstore index bổ sung một bản biểu diễn theo cột cho bảng rowstore. Bảng chính vẫn có thể phục vụ OLTP bằng clustered index hoặc heap; columnstore index giúp một số truy vấn phân tích đọc và tổng hợp hiệu quả hơn.

Ví dụ:

```sql
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_SalesAnalytics
ON dbo.Sales
(
    sale_date,
    region,
    product_id,
    quantity,
    unit_price
);
```

Chọn các cột thực sự cần cho nhóm truy vấn phân tích. Mỗi cột bổ sung làm tăng dung lượng và chi phí duy trì khi dữ liệu thay đổi. Nonclustered columnstore có thể hữu ích với operational analytics, nhưng cần kiểm tra giới hạn DML, tính năng và phiên bản SQL Server đang dùng.

### 5.3. Delta store, delete bitmap và tuple mover

SQL Server có thể đưa các dòng mới vào delta rowgroup ở dạng rowstore trước khi nén thành compressed rowgroup. Quá trình nền gọi là tuple mover có nhiệm vụ chuyển các nhóm đủ điều kiện sang định dạng nén. Xóa dòng được ghi nhận trong delete bitmap; các dòng đã xóa có thể vẫn nằm trong rowgroup cho tới khi được loại bỏ qua hoạt động tổ chức lại hoặc rebuild.

Những cơ chế này giúp hỗ trợ DML trên columnstore, nhưng workload ghi nhỏ và liên tục có thể tạo nhiều delta rowgroup hoặc delete bitmap lớn. Cần theo dõi trạng thái rowgroup thay vì chỉ xem kích thước chỉ mục tổng.

Có thể kiểm tra thông tin rowgroup bằng DMV:

```sql
SELECT object_id,
       index_id,
       partition_number,
       row_group_id,
       state_desc,
       total_rows,
       deleted_rows,
       size_in_bytes
FROM sys.dm_db_column_store_row_group_physical_stats
WHERE object_id = OBJECT_ID('dbo.FactSales')
ORDER BY partition_number, row_group_id;
```

Quyền xem DMV và các cột sẵn có tùy phiên bản. Dựa trên kết quả, hãy xem có nhiều rowgroup nhỏ, trạng thái chưa nén hoặc tỷ lệ dòng xóa cao hay không.

### 5.4. Đo hiệu quả columnstore trong SQL Server

Kết hợp Actual Execution Plan với:

```sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT region,
       SUM(quantity * unit_price) AS revenue
FROM dbo.FactSales
WHERE sale_date >= '2026-01-01'
  AND sale_date <  '2026-02-01'
GROUP BY region;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Kiểm tra columnstore scan, batch mode, số dòng thực tế, segment elimination, logical reads, CPU time, elapsed time và memory grant. So sánh với rowstore trên cùng dữ liệu và điều kiện tải. Nếu truy vấn đọc ít dòng nhưng vẫn quét nhiều segment, kiểm tra thứ tự dữ liệu, min/max của segment, predicate và khả năng loại bỏ segment.

## 6. Oracle Database: In-Memory Column Store

Oracle Database In-Memory có thể duy trì biểu diễn dữ liệu theo cột trong In-Memory Column Store, đồng thời vẫn giữ định dạng hàng truyền thống cho các thao tác OLTP. Cách tổ chức hai định dạng giúp truy vấn phân tích quét cột và xử lý theo vector trong khi giao dịch vẫn dùng đường truy cập hàng.

Tùy cấu hình và phiên bản, có thể đánh dấu bảng hoặc partition để đưa vào vùng In-Memory:

```sql
ALTER TABLE sales INMEMORY;
```

Hoặc chỉ chọn một số cột:

```sql
ALTER TABLE sales
  INMEMORY MEMCOMPRESS FOR QUERY
  (sale_date, region, quantity, unit_price);
```

Cú pháp, mức nén và khả năng áp dụng phụ thuộc phiên bản, cấu hình và quyền sử dụng tính năng. Sau khi cấu hình, cần xác nhận dữ liệu đã được populate vào In-Memory Column Store; thuộc tính `INMEMORY` không đồng nghĩa mọi segment đã lập tức sẵn sàng trong bộ nhớ.

Oracle duy trì biểu diễn row format và column format để phục vụ hai loại workload. DML có thể làm mất hiệu lực một phần đơn vị In-Memory và cần cơ chế duy trì hoặc populate lại. Do đó, cần đo tốc độ cập nhật, độ mới dữ liệu phân tích, dung lượng In-Memory và tác động tới các workload khác. Cũng cần xác minh điều kiện cấp phép và cấu hình trước khi triển khai tính năng In-Memory trong môi trường thực tế.

Không nên nhầm In-Memory Column Store với Hybrid Columnar Compression (HCC). HCC là một cơ chế nén lưu trữ theo nhóm dòng với đặc tính phù hợp cho dữ liệu ít thay đổi hoặc nạp theo batch trong những cấu hình lưu trữ được hỗ trợ; nó không phải cùng một cơ chế với biểu diễn columnar trong bộ nhớ dùng để tăng tốc truy vấn phân tích.

## 7. PostgreSQL và MySQL: lựa chọn kiến trúc khi cần phân tích dạng cột

PostgreSQL core và InnoDB của MySQL chủ yếu tổ chức bảng theo dạng hàng. Không nên giả định có thể tạo một columnstore index tương đương clustered columnstore của SQL Server bằng cú pháp chỉ mục B-tree thông thường.

Với PostgreSQL, các lựa chọn thường gặp tùy phiên bản và hệ sinh thái gồm:

- Dùng B-tree, BRIN và partitioning để giảm phạm vi đọc cho workload phù hợp.
- Tạo materialized view hoặc bảng tổng hợp để phục vụ báo cáo lặp lại.
- Đưa dữ liệu phân tích sang kho dữ liệu hoặc engine columnar chuyên dụng.
- Đánh giá extension hoặc giải pháp columnar bên ngoài theo mức độ tương thích, khả năng DML, backup/restore, replication và hỗ trợ vận hành.

Với MySQL/InnoDB, có thể dùng:

- Chỉ mục B-tree ghép hoặc covering index cho truy vấn đọc có chọn lọc.
- Partitioning, bảng tổng hợp và materialized-result pattern do ứng dụng quản lý khi phù hợp.
- Nền tảng phân tích hoặc engine columnar tích hợp/riêng biệt nếu workload cần quét dữ liệu lớn.

Các giải pháp columnar bên ngoài có thể khác nhau về độ trễ đồng bộ, tính nhất quán, khả năng cập nhật từng dòng, SQL compatibility và chi phí vận hành. Trước khi chọn, cần xác định dữ liệu phân tích phải mới đến mức nào, có chấp nhận replication lag hay không và hệ thống nào chịu trách nhiệm lưu dữ liệu chuẩn.

## 8. Thiết kế hệ thống kết hợp OLTP và phân tích

Một kiến trúc phổ biến là giữ bảng giao dịch ở rowstore và cung cấp dữ liệu cho workload phân tích bằng một trong các cách sau:

1. **Nonclustered columnstore trên rowstore:** phù hợp khi hệ quản trị hỗ trợ và cần phân tích gần dữ liệu giao dịch.
2. **Replica đọc hoặc kho dữ liệu riêng:** giảm cạnh tranh CPU/I/O giữa báo cáo và giao dịch; cần quản lý độ trễ đồng bộ.
3. **ETL/ELT theo batch:** gom dữ liệu mới, nạp theo lô và nén thành row group lớn; đổi lại dữ liệu phân tích có thể trễ theo lịch nạp.
4. **Partitioning theo thời gian:** giúp nạp, lưu trữ, chuyển vùng dữ liệu và loại bỏ dữ liệu cũ hiệu quả hơn.
5. **Bảng tổng hợp hoặc materialized view:** giảm công việc lặp lại cho báo cáo cố định; cần thiết kế refresh và xử lý dữ liệu đến muộn.

Hãy chọn theo yêu cầu nghiệp vụ. Dashboard điều hành có thể chấp nhận dữ liệu trễ vài phút; hệ thống giám sát gian lận có thể yêu cầu gần thời gian thực; báo cáo tài chính có thể ưu tiên tính nhất quán và quy trình chốt dữ liệu.

### 8.1. Đánh đổi về độ mới dữ liệu

Nếu dữ liệu mới nằm trong delta store, vùng ghi đệm hoặc chưa được đồng bộ sang engine phân tích, truy vấn có thể phải đọc nhiều định dạng hoặc chờ quá trình cập nhật. Một số engine có thể kết hợp vùng dữ liệu mới và vùng đã nén trong cùng truy vấn, nhưng hiệu năng có thể khác nhau tùy tỷ lệ dữ liệu mới.

Đo thời gian từ lúc giao dịch commit tới lúc dữ liệu xuất hiện trong báo cáo. Theo dõi độ trễ theo p50/p95, không chỉ một lần đo trung bình. Nếu yêu cầu freshness rất thấp, cân nhắc duy trì rowstore cho đường giao dịch và thiết kế luồng CDC/streaming hoặc cơ chế đồng bộ phù hợp.

### 8.2. Đánh đổi về tài nguyên

Columnstore có thể giảm dung lượng lưu trữ và I/O, nhưng vẫn tiêu thụ CPU để giải nén, lọc, join và aggregate. Truy vấn phân tích lớn có thể cần memory grant đáng kể; nếu bộ nhớ không đủ, sort/hash có thể spill ra vùng tạm. Nếu nhiều truy vấn phân tích cùng chạy, chúng có thể cạnh tranh CPU, memory và băng thông lưu trữ với workload OLTP.

Đừng đánh giá columnstore chỉ bằng tỷ lệ nén. Cần đo tổng chi phí của hệ thống: dung lượng rowstore/columnstore, CPU, I/O, memory, log, tốc độ ghi, độ trễ giao dịch và thông lượng báo cáo.

## 9. Quy trình thử nghiệm trước khi triển khai

1. **Phân loại workload.** Liệt kê truy vấn tra cứu, insert/update/delete, báo cáo tổng hợp, thời gian chạy và tần suất.
2. **Chọn truy vấn đại diện.** Bao gồm truy vấn quét nhiều dòng, truy vấn chỉ đọc ít cột, truy vấn tra cứu theo khóa và truy vấn có cập nhật thường xuyên.
3. **Chuẩn bị dữ liệu thực tế.** Giữ phân bố, độ lệch, số dòng, kích thước cột và tỷ lệ dữ liệu mới gần production.
4. **Tạo phương án đối chứng.** So sánh rowstore hiện tại với columnstore hoặc kiến trúc phân tích dự kiến; giữ nguyên logic truy vấn và điều kiện dữ liệu.
5. **Đo đọc phân tích.** Ghi elapsed, CPU, I/O, số cột/segment đọc, tỷ lệ nén, batch mode, memory grant, spill và throughput.
6. **Đo tải ghi.** Chạy insert/update/delete theo mẫu thực tế; ghi độ trễ commit, throughput, log generation, lượng dữ liệu trong delta store hoặc trạng thái rowgroup.
7. **Đo hỗn hợp.** Chạy giao dịch và báo cáo đồng thời để xác định ảnh hưởng tới p95/p99, timeout và hàng đợi tài nguyên.
8. **Đo độ mới.** Ghi thời gian từ commit hoặc nạp dữ liệu đến lúc truy vấn phân tích nhìn thấy dữ liệu.
9. **Đánh giá bảo trì.** Đo thời gian và tài nguyên cho nén, merge, reorganize, rebuild, refresh hoặc ETL.
10. **Quyết định theo workload.** Chỉ triển khai nếu lợi ích phân tích đáp ứng mục tiêu và chi phí ghi, lưu trữ, độ mới cùng vận hành nằm trong giới hạn chấp nhận.

### Ví dụ ma trận đo

| Phép thử | Chỉ số chính | Kết quả cần đạt |
|---|---|---|
| Báo cáo tổng hợp 30 ngày | p95 elapsed, CPU, logical/physical reads | Báo cáo nhanh hơn và giảm I/O trong giới hạn CPU |
| Tra cứu theo khóa chính | p95 latency, logical reads | Không suy giảm đáng kể so với rowstore |
| Nạp batch 100 nghìn dòng | rows/second, log, thời gian nén | Đạt cửa sổ ETL và tạo row group đủ lớn |
| Cập nhật một dòng | commit latency, throughput | Chi phí ghi vẫn đáp ứng SLO giao dịch |
| Báo cáo và OLTP đồng thời | p95/p99, timeout, CPU, I/O, memory | Báo cáo không làm giao dịch vượt SLO |
| Dữ liệu mới sau commit | freshness lag | Độ trễ dữ liệu đáp ứng yêu cầu nghiệp vụ |

Các con số trong ma trận cần được đặt theo SLO của hệ thống. Không có một ngưỡng chung cho mọi database hoặc mọi loại báo cáo.

## 10. Những sai lầm thường gặp

- **Cho rằng columnstore luôn nhanh hơn rowstore:** tra cứu một vài dòng hoặc cập nhật nhỏ thường không phải trường hợp columnstore có lợi nhất.
- **Chỉ đo truy vấn báo cáo:** bỏ qua chi phí insert/update/delete và ảnh hưởng tới giao dịch trực tuyến.
- **Nạp dữ liệu từng dòng trong workload cần batch:** có thể tạo nhiều row group nhỏ hoặc tăng chi phí ghi và nén.
- **Không theo dõi delta store và delete bitmap:** dữ liệu chưa nén hoặc dòng đã xóa có thể làm giảm hiệu quả scan và tăng dung lượng.
- **Chỉ nhìn tỷ lệ nén:** tỷ lệ nén cao không bảo đảm CPU, memory grant hoặc elapsed đều tốt hơn.
- **Đưa mọi cột vào nonclustered columnstore:** làm tăng dung lượng và chi phí duy trì mà không đem lại lợi ích cho truy vấn.
- **Không kiểm tra segment elimination:** truy vấn lọc theo ngày nhưng vẫn đọc nhiều segment có thể do dữ liệu không được tổ chức phù hợp hoặc điều kiện lọc không hỗ trợ pruning.
- **Rebuild/reorganize thiếu kế hoạch:** bảo trì có thể tiêu thụ nhiều I/O, CPU, log và ảnh hưởng truy vấn đang chạy.
- **Bỏ qua độ trễ đồng bộ sang hệ phân tích:** kết quả báo cáo có thể chưa phản ánh giao dịch mới nhất.
- **So sánh hai phương án với dữ liệu hoặc cache khác nhau:** kết luận có thể sai vì điều kiện thử không tương đương.

## 11. Checklist chọn và vận hành columnstore

- [ ] Đã phân loại rõ workload OLTP, báo cáo và phân tích.
- [ ] Đã xác định truy vấn nào quét nhiều dòng và chỉ đọc một số cột.
- [ ] Đã đánh giá kích thước bảng, độ rộng cột, phân bố dữ liệu và khả năng nén.
- [ ] Đã chọn clustered hay nonclustered columnstore hoặc kiến trúc phân tích riêng phù hợp hệ quản trị.
- [ ] Đã kiểm tra segment elimination, row group, delta store và delete bitmap nếu nền tảng cung cấp.
- [ ] Đã đo tốc độ insert/update/delete và độ trễ commit.
- [ ] Đã đo truy vấn phân tích và tra cứu theo khóa trên cùng dữ liệu.
- [ ] Đã kiểm thử tải hỗn hợp và theo dõi p95/p99 của giao dịch.
- [ ] Đã xác định độ mới dữ liệu và thời gian đồng bộ tới engine phân tích.
- [ ] Đã lập lịch và đo chi phí nén, reorganize, rebuild hoặc refresh.
- [ ] Đã tính dung lượng, CPU, memory, I/O, log và chi phí vận hành tổng thể.
- [ ] Đã lưu baseline và kết quả trước/sau để quyết định dựa trên số liệu.

Columnstore phù hợp khi workload đọc phân tích nhiều dòng, cần ít cột và có thể tận dụng nén cùng xử lý theo lô. Rowstore vẫn là lựa chọn tự nhiên cho nhiều giao dịch đọc/ghi theo dòng. Trong hệ thống hỗn hợp, quyết định tốt thường đến từ việc phân loại workload, chọn đúng cơ chế lưu trữ cho từng đường truy cập và đo cả tốc độ báo cáo lẫn chi phí cập nhật trước khi triển khai.
