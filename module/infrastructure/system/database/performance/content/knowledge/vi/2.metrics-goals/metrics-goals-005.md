# Chỉ số đọc logic, đọc vật lý, dung lượng tạm và lượng dữ liệu trả về

Khi tối ưu hiệu năng cơ sở dữ liệu, cảm giác “truy vấn này có vẻ chậm” chưa đủ để quyết định cần tạo chỉ mục, viết lại SQL hay tăng tài nguyên. Ta cần đo xem truy vấn đã truy cập bao nhiêu trang dữ liệu, phải nạp bao nhiêu trang từ tầng lưu trữ, dùng bao nhiêu không gian làm việc tạm và cuối cùng chuyển bao nhiêu dữ liệu cho ứng dụng.

Bốn nhóm chỉ số này bổ sung cho nhau. Đọc logic phản ánh khối lượng truy cập dữ liệu ở tầng bộ đệm; đọc vật lý cho biết mức độ phải nạp trang vào bộ đệm; dung lượng tạm cho thấy chi phí của các phép sắp xếp, băm và xử lý trung gian; lượng dữ liệu trả về thể hiện công việc truyền kết quả tới ứng dụng. Đặt chúng cạnh thời gian thực thi, kế hoạch thực thi và tải đồng thời sẽ giúp xác định nút thắt có căn cứ.

## 1. Đọc logic: truy vấn đã chạm vào bao nhiêu trang?

Hệ quản trị cơ sở dữ liệu thường lưu dữ liệu trong các trang (page hoặc block). Khi thực hiện truy vấn, nó tìm các trang cần thiết trong vùng nhớ đệm, thường gọi là buffer pool hoặc shared buffers.

**Đọc logic (logical reads)** là số lượt truy cập trang dữ liệu qua cơ chế bộ đệm theo cách hệ quản trị cơ sở dữ liệu định nghĩa. Một trang có thể được truy cập nhiều lần trong cùng truy vấn, vì vậy chỉ số này không đồng nghĩa với số trang duy nhất, số hàng được trả về hay số lần đọc đĩa.

Ví dụ, một truy vấn có thể đọc đi đọc lại các trang của bảng đơn hàng trong vòng lặp join. Dù các trang đã nằm trong RAM, mỗi lượt truy cập vẫn tiêu tốn CPU và băng thông bộ nhớ, đồng thời có thể làm tăng tranh chấp khi nhiều phiên cùng truy cập. Vì thế, truy vấn có ít đọc vật lý nhưng rất nhiều đọc logic vẫn có thể chậm.

Đọc logic cao thường gợi ý một hoặc nhiều khả năng:

- Truy vấn quét một vùng bảng hoặc chỉ mục lớn trong khi chỉ cần một phần nhỏ dữ liệu.
- Điều kiện lọc chưa đủ chọn lọc hoặc không tận dụng được chỉ mục phù hợp.
- Thứ tự cột trong chỉ mục ghép chưa phù hợp với điều kiện lọc và cách join.
- Một phép join, subquery hoặc vòng lặp thực thi lặp lại việc truy cập cùng tập dữ liệu.
- Truy vấn đọc nhiều cột hoặc hàng hơn mức cần thiết.

Đọc logic cao không tự động chứng minh rằng truy vấn cần thêm chỉ mục. Một báo cáo hợp lệ có thể phải đọc phần lớn bảng; thêm chỉ mục trong trường hợp đó có thể tăng chi phí ghi và dung lượng lưu trữ mà không cải thiện đáng kể. Hãy đối chiếu chỉ số với số hàng thực tế, điều kiện lọc, kế hoạch thực thi và mục tiêu nghiệp vụ.

## 2. Đọc vật lý: có bao nhiêu trang phải được nạp vào bộ đệm?

**Đọc vật lý (physical reads)** thường chỉ các trang phải được nạp từ tầng lưu trữ vào bộ đệm vì chúng chưa có sẵn trong vùng nhớ mà hệ quản trị sử dụng. Việc đọc này có thể phát sinh độ trễ I/O và làm tăng thời gian truy vấn.

Đọc vật lý chịu ảnh hưởng lớn bởi trạng thái bộ đệm. Cùng một truy vấn có thể đọc vật lý nhiều ở lần chạy đầu khi dữ liệu chưa được nạp, rồi giảm mạnh ở những lần sau khi trang đã nằm trong cache. Vì vậy, cần ghi nhận điều kiện cache khi đo và tránh so sánh một lần chạy cache lạnh với một lần chạy cache nóng.

Một số cách diễn giải thường gặp:

- **Đọc logic cao, đọc vật lý thấp:** phần lớn trang đã có trong bộ đệm, nhưng truy vấn vẫn phải xử lý quá nhiều trang. Hãy kiểm tra scan, số vòng lặp join, điều kiện lọc và các lần truy cập lặp lại. CPU hoặc tranh chấp bộ đệm có thể là nút thắt.
- **Đọc vật lý cao:** truy vấn phải nạp nhiều trang từ tầng lưu trữ. Hãy kiểm tra kích thước tập dữ liệu được truy cập, tính chọn lọc của điều kiện lọc, chỉ mục, dung lượng bộ nhớ dành cho cache và tải I/O của hệ thống.
- **Đọc logic và đọc vật lý đều thấp nhưng truy vấn vẫn chậm:** nguyên nhân có thể nằm ở khóa và chờ giao dịch, CPU cho phép tính, mạng, thời gian chờ kết quả từ ứng dụng hoặc một nút thắt khác ngoài đọc trang.

Không nên coi mọi bộ đếm mang tên “physical read” là số lần ổ đĩa thực sự phải truy cập thiết bị. Cách định nghĩa khác nhau giữa các hệ quản trị. Chẳng hạn, trong PostgreSQL, bộ đếm shared read của EXPLAIN BUFFERS cho biết block được đọc vào shared buffers; dữ liệu vẫn có thể đã nằm trong cache của hệ điều hành. SQL Server có các bộ đếm logical reads, physical reads và read-ahead reads với cách phân loại riêng. Khi phân tích, hãy đọc định nghĩa của bộ đếm trên đúng hệ quản trị và phiên bản đang dùng.

## 3. Dung lượng tạm: chi phí của xử lý trung gian

Truy vấn có thể cần tạo cấu trúc trung gian để sắp xếp, nhóm, join, loại trùng hoặc tính toán cửa sổ. Hệ quản trị thường cố gắng thực hiện các thao tác này trong bộ nhớ. Khi dữ liệu trung gian lớn hơn vùng nhớ được cấp hoặc cấu hình cho phép, một phần công việc có thể tràn ra tệp tạm trên đĩa (spill).

**Dung lượng tạm (temporary space)** có thể được thể hiện qua số trang hoặc byte đọc/ghi tệp tạm, dung lượng bảng tạm, hoặc mức sử dụng vùng làm việc tạm. Phải phân biệt cấu trúc tạm nằm trong bộ nhớ với dữ liệu đã tràn ra đĩa: cả hai đều tiêu thụ tài nguyên, nhưng spill thường kéo theo I/O và độ trễ lớn hơn.

Các thao tác dễ phát sinh dung lượng tạm gồm:

- ORDER BY trên tập dữ liệu lớn khi không có đường truy cập phù hợp để cung cấp thứ tự.
- GROUP BY hoặc DISTINCT trên nhiều hàng hay nhiều cột có độ rộng lớn.
- Hash join hoặc hash aggregate khi tập dữ liệu trung gian vượt quá bộ nhớ được cấp.
- Window function cần sắp xếp hoặc giữ lại nhiều hàng.
- Materialize một kết quả trung gian lớn để tái sử dụng.

Khi thấy dung lượng tạm tăng, hãy tìm nút Sort, Hash, Aggregate hoặc Materialize trong kế hoạch thực thi và kiểm tra số hàng thực tế, kích thước hàng, ước lượng của bộ tối ưu và thông tin spill. Ước lượng sai về số hàng có thể khiến bộ tối ưu chọn thuật toán hoặc cấp bộ nhớ không phù hợp.

Một số hướng xử lý cần cân nhắc:

1. Giảm số hàng trước thao tác tốn bộ nhớ bằng điều kiện lọc có thể áp dụng sớm, nếu điều đó vẫn giữ nguyên ngữ nghĩa truy vấn.
2. Chỉ chọn các cột cần thiết, nhất là khi các hàng trung gian chứa nhiều cột văn bản hoặc dữ liệu lớn.
3. Xem xét chỉ mục có thể hỗ trợ thứ tự hoặc điều kiện lọc, sau khi đánh giá lợi ích và chi phí ghi.
4. Rà soát điều kiện join, thống kê và ước lượng số hàng để bộ tối ưu chọn kế hoạch phù hợp.
5. Điều chỉnh bộ nhớ làm việc khi đã xác định đúng loại thao tác và phạm vi ảnh hưởng. Tăng bộ nhớ cho mọi phiên có thể làm tổng mức sử dụng RAM vượt giới hạn khi nhiều truy vấn chạy đồng thời.

Không phải cứ có bảng hoặc tệp tạm là truy vấn kém hiệu quả. Một số phép toán cần vùng tạm theo thiết kế. Mục tiêu là xác định dung lượng, thời gian và I/O phát sinh có đáng kể trong tải thực tế hay không.

## 4. Lượng dữ liệu trả về: chi phí sau khi truy vấn đã tính xong

Kết quả truy vấn cần được chuyển từ máy chủ cơ sở dữ liệu đến ứng dụng. **Lượng dữ liệu trả về** nên được quan sát qua ít nhất hai đại lượng:

- Số hàng trả về.
- Tổng kích thước dữ liệu truyền, thường tính bằng byte hoặc MB.

Hai đại lượng này không thay thế cho nhau. Một nghìn hàng chỉ có vài cột số có thể nhỏ hơn nhiều so với một trăm hàng chứa văn bản dài, JSON hoặc dữ liệu nhị phân. Kích thước còn phụ thuộc định dạng truyền, giao thức, cách mã hóa và việc ứng dụng có thực sự đọc hết kết quả hay không.

Truy vấn trả về nhiều dữ liệu có thể làm tăng thời gian truyền mạng, cấp phát bộ nhớ, giải mã, ánh xạ đối tượng và xử lý ở tầng ứng dụng. Thời gian truy vấn phía máy chủ có thể thấp nhưng thời gian hoàn tất yêu cầu của người dùng vẫn cao.

Các dấu hiệu thường gặp:

- Dùng SELECT * khiến ứng dụng nhận nhiều cột không cần thiết.
- Truy vấn trả về toàn bộ lịch sử trong khi màn hình chỉ hiển thị một trang.
- Join làm nhân bản hàng hoặc trả lại các cột lặp.
- Ứng dụng tải toàn bộ kết quả vào bộ nhớ trước khi xử lý.
- API gửi các bản ghi lớn dù người dùng chỉ cần số liệu tổng hợp.

Hướng xử lý là chọn đúng cột, lọc theo điều kiện nghiệp vụ, phân trang ổn định, giới hạn phạm vi thời gian, tổng hợp ở cơ sở dữ liệu khi phù hợp và dùng cơ chế đọc theo luồng cho tập kết quả lớn. Phân trang cần có thứ tự xác định, thường dựa trên khóa duy nhất hoặc khóa ghép ổn định; OFFSET rất lớn có thể vẫn khiến cơ sở dữ liệu phải đi qua nhiều hàng trước khi trả trang sau. Với tập dữ liệu lớn, có thể cân nhắc phân trang theo khóa (keyset pagination).

Không dùng LIMIT hoặc TOP như cách che giấu một truy vấn có kế hoạch kém. Giới hạn số hàng trả về có thể giảm truyền dữ liệu, nhưng bộ máy vẫn có thể phải quét, join hoặc sắp xếp một tập dữ liệu rất lớn trước khi xác định các hàng cần trả.

## 5. Đọc bốn nhóm chỉ số cùng nhau

Bảng dưới đây là khung chẩn đoán ban đầu. Các kết luận cần được xác nhận bằng kế hoạch thực thi, thời gian, số hàng thực tế và tải của hệ thống.

| Quan sát | Khả năng cần kiểm tra | Hướng điều tra |
|---|---|---|
| Đọc logic cao, đọc vật lý thấp | Truy cập nhiều trang đã nằm trong cache; scan hoặc lặp truy cập | Số hàng được đọc, số vòng lặp join, điều kiện lọc, chỉ mục |
| Đọc vật lý cao | Nhiều trang phải nạp vào buffer; cache miss hoặc tập dữ liệu truy cập lớn | I/O, cache, working set, kế hoạch scan, mức chọn lọc |
| Dung lượng tạm cao | Sort, hash, aggregate hoặc materialize lớn; có thể đã spill | Nút trong execution plan, ước lượng số hàng, độ rộng hàng, bộ nhớ làm việc |
| Số hàng hoặc byte trả về cao | Truy vấn truyền nhiều kết quả hơn nhu cầu của ứng dụng | Cột được chọn, bộ lọc, join, phân trang, cách ứng dụng fetch |
| Cả đọc logic, đọc vật lý và dung lượng tạm đều cao | Truy vấn xử lý tập dữ liệu lớn qua nhiều giai đoạn | Xem toàn bộ kế hoạch và xác định nút chi phí lớn nhất trước khi thay đổi |
| Các chỉ số đọc thấp nhưng thời gian cao | Có thể chờ khóa, chờ tài nguyên, tốn CPU, mạng hoặc xử lý ở ứng dụng | Wait events, blocking, CPU, thời gian truyền và thời gian tiêu thụ kết quả |

Không đặt một ngưỡng đọc logic hoặc dung lượng tạm chung cho mọi hệ thống. Kích thước trang, cấu trúc dữ liệu, phần cứng, phiên bản hệ quản trị và tải đồng thời đều ảnh hưởng đến ý nghĩa của con số. Hãy so sánh cùng truy vấn, cùng tham số, cùng môi trường và cùng cách đo; theo dõi cả mức tuyệt đối lẫn xu hướng.

## 6. Ví dụ phân tích một truy vấn báo cáo

Giả sử một báo cáo cần tính doanh thu theo khách hàng trong một khoảng thời gian. Cú pháp dưới đây dùng dạng tham số và LIMIT phổ biến ở PostgreSQL/MySQL; cần điều chỉnh theo hệ quản trị cụ thể.

~~~sql
SELECT
    c.id,
    c.name,
    SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY c.id, c.name
ORDER BY total_revenue DESC
LIMIT 50;
~~~

Giả sử một lần đo trong môi trường thử nghiệm cho kết quả minh họa như sau:

| Chỉ số | Giá trị minh họa | Cách đọc |
|---|---:|---|
| Đọc logic | 82.000 trang | Truy vấn đã truy cập nhiều trang dù phần lớn có thể ở cache |
| Đọc vật lý | 1.200 trang | Một phần trang cần được nạp vào buffer |
| Ghi/đọc vùng tạm | 14.000 trang | Một thao tác trung gian có thể đã tạo lượng dữ liệu tạm đáng kể |
| Kết quả trả về | 50 hàng, khoảng 18 KB | Dữ liệu gửi đến ứng dụng nhỏ so với công việc xử lý bên trong |

Các con số trên chỉ nhằm minh họa cách suy luận, không phải ngưỡng chuẩn. Vì kết quả chỉ có 50 hàng nhưng đọc logic và dung lượng tạm cao, vấn đề có thể nằm ở số đơn hàng và mặt hàng phải xử lý trước khi nhóm và sắp xếp, chứ không nằm ở kích thước kết quả gửi về.

Quy trình điều tra hợp lý:

1. Mở kế hoạch thực thi và xác định nút nào đọc nhiều hàng nhất, nút nào thực hiện Sort hoặc Hash. So sánh số hàng ước lượng với số hàng thực tế.
2. Kiểm tra đường truy cập vào orders theo khoảng created_at và điều kiện join theo customer_id. Xác nhận chỉ mục hiện có, thứ tự cột và tính chọn lọc của bộ lọc.
3. Kiểm tra đường join order_items theo order_id. Nếu đây là khóa ngoại được dùng thường xuyên để lấy chi tiết đơn hàng, chỉ mục phù hợp có thể giảm lượng trang phải truy cập.
4. Kiểm tra Sort/Hash có spill hay không, kích thước dữ liệu trung gian và nguyên nhân ước lượng sai. Đánh giá liệu lọc sớm hơn hoặc giảm cột trung gian có giữ nguyên kết quả hay không.
5. Đo lại cả bốn nhóm chỉ số, thời gian thực thi và tài nguyên khi chạy cùng khoảng thời gian, cùng tham số và điều kiện cache tương đương.

Ví dụ, chỉ mục trên orders có thể được xem xét theo điều kiện lọc thời gian và cột join khách hàng; chỉ mục trên order_items theo order_id cũng có thể hữu ích. Không áp dụng máy móc một định nghĩa chỉ mục cho mọi hệ quản trị: kiểu dữ liệu, phân bố dữ liệu, thứ tự cột, khả năng index-only/covering và chi phí cập nhật phải được đánh giá từ kế hoạch thực tế. Chỉ mục mới cũng làm tăng dung lượng và chi phí INSERT, UPDATE, DELETE.

Nếu sau điều chỉnh, đọc logic giảm nhưng thời gian không cải thiện, hãy kiểm tra chờ khóa, CPU, mạng và phần xử lý của ứng dụng. Nếu thời gian máy chủ giảm nhưng thời gian API không đổi, hãy đo thời gian fetch và kích thước payload ở phía ứng dụng.

## 7. Thu thập chỉ số theo từng hệ quản trị

Tên lệnh và cách đếm phụ thuộc hệ quản trị. Một số điểm bắt đầu phổ biến:

| Hệ quản trị | Công cụ hoặc lệnh | Thông tin cần xem |
|---|---|---|
| PostgreSQL | EXPLAIN (ANALYZE, BUFFERS) | Thời gian thực tế, số hàng, shared hit/read, temp read/written và các nút Sort/Hash |
| SQL Server | SET STATISTICS IO ON; SET STATISTICS TIME ON; kết hợp Actual Execution Plan | Logical reads, physical reads, read-ahead reads, CPU, elapsed time, cảnh báo spill |
| MySQL 8.0.18 trở lên | EXPLAIN ANALYZE; Performance Schema và chỉ số engine liên quan | Thời gian và số hàng theo iterator; thống kê I/O, temporary table và workload từ công cụ giám sát |

Ví dụ trên PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
~~~

Trong kết quả, shared hit biểu thị block được tìm thấy trong shared buffers; shared read biểu thị block được đọc vào shared buffers. Nếu có temp read hoặc temp written, hãy kiểm tra thao tác trung gian gây sử dụng tệp tạm. EXPLAIN ANALYZE thực sự thực thi câu lệnh, vì vậy cần thận trọng với truy vấn ghi dữ liệu và truy vấn nặng trên môi trường đang phục vụ người dùng.

Ví dụ trên SQL Server:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT id, created_at
FROM dbo.orders
WHERE created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

Đọc logical reads cùng physical reads, read-ahead reads và thời gian CPU. Kết hợp với Actual Execution Plan để nhận biết scan, lookup lặp lại, sort/hash spill và chênh lệch giữa số hàng ước lượng với số hàng thực tế.

Trên MySQL, EXPLAIN ANALYZE cho biết thời gian và số hàng qua các iterator trong những phiên bản hỗ trợ. Để đánh giá đọc trang và bảng tạm, cần kết hợp Performance Schema, thống kê của storage engine và công cụ giám sát phù hợp. Không suy ra số lần đọc đĩa trực tiếp chỉ từ thời gian của EXPLAIN ANALYZE.

## 8. Quy trình đo và xác nhận sau tối ưu

Một phép đo chỉ có giá trị khi có thể so sánh. Hãy dùng quy trình nhất quán:

1. **Chọn truy vấn và tình huống tải.** Ghi lại SQL, tham số, kích thước dữ liệu, số phiên đồng thời và mục tiêu thời gian đáp ứng.
2. **Lấy đường cơ sở.** Đo thời gian, CPU, đọc logic, đọc vật lý, dung lượng tạm, số hàng và kích thước kết quả. Ghi lại kế hoạch thực thi và trạng thái cache.
3. **Lặp phép đo.** Chạy nhiều lần trong điều kiện tương đương, phân biệt lần chạy cache lạnh và cache nóng. Không xóa cache trên hệ thống production chỉ để tạo một phép đo.
4. **Tìm nút thắt.** Dựa vào kế hoạch và các chỉ số để xác định chi phí chủ đạo: scan, join, sort/hash, I/O, truyền kết quả hay chờ giao dịch.
5. **Thay đổi có kiểm soát.** Điều chỉnh một yếu tố chính mỗi lần, chẳng hạn chỉ mục, câu SQL hoặc cấu hình bộ nhớ; giữ nguyên dữ liệu và tham số để biết thay đổi nào tạo ra kết quả.
6. **Đo lại dưới tải đại diện.** So sánh không chỉ một lần chạy đơn lẻ mà cả p50/p95, throughput, CPU, I/O và ảnh hưởng đến các truy vấn khác.
7. **Kiểm tra tính đúng đắn.** Đối chiếu số hàng, giá trị tổng hợp, trường hợp biên và kết quả nghiệp vụ trước/sau. Một truy vấn nhanh hơn nhưng trả dữ liệu sai không phải là tối ưu thành công.

Khi có nhiều truy vấn đồng thời, hãy quan sát tổng mức tiêu thụ tài nguyên. Một thay đổi làm một truy vấn đơn lẻ nhanh hơn vẫn có thể khiến hệ thống kém ổn định nếu nó tăng số lần đọc, lượng bộ nhớ mỗi phiên hoặc chi phí ghi trên toàn workload.

## 9. Những sai lầm thường gặp khi đọc số liệu

- **Đồng nhất đọc logic với số hàng.** Đọc logic thường đếm lượt truy cập trang, không phải số hàng được trả về.
- **Cho rằng đọc vật lý luôn là I/O trực tiếp từ thiết bị.** Cache của hệ điều hành và định nghĩa bộ đếm có thể làm cách diễn giải khác nhau.
- **So sánh số liệu giữa các hệ quản trị hoặc cấu hình khác nhau.** Kích thước trang và cách đếm không giống nhau; hãy so sánh trong cùng môi trường.
- **Chỉ đo một lần.** Cache, dữ liệu, lịch chạy nền và tải đồng thời có thể làm kết quả biến động.
- **Chỉ nhìn thời gian trung bình.** p95 hoặc p99 có thể bộc lộ truy vấn chậm bất thường mà trung bình che khuất.
- **Coi mọi dung lượng tạm là lỗi.** Cần xác định đó là vùng nhớ tạm hay spill ra đĩa và nó có ảnh hưởng đáng kể không.
- **Chỉ đếm số hàng mà bỏ qua kích thước payload.** Vài hàng chứa dữ liệu lớn vẫn có thể gây truyền mạng và cấp phát bộ nhớ đáng kể.
- **Tối ưu một truy vấn mà bỏ qua workload.** Chỉ mục, bộ nhớ và kế hoạch truy vấn ảnh hưởng đến các thao tác đọc/ghi khác.
- **Bỏ qua tính đúng đắn.** Luôn xác minh kết quả nghiệp vụ sau khi viết lại SQL hoặc thay đổi chỉ mục.

## 10. Checklist khi đánh giá một truy vấn

- [ ] Đã ghi lại SQL, tham số, dữ liệu thử nghiệm và mức tải đồng thời.
- [ ] Đã thu thập kế hoạch thực thi có số liệu thực tế.
- [ ] Đã đo đọc logic và hiểu bộ đếm theo đúng hệ quản trị.
- [ ] Đã đo đọc vật lý, trạng thái cache và tải I/O.
- [ ] Đã xác định dung lượng tạm đến từ thao tác nào và có spill ra đĩa không.
- [ ] Đã đo cả số hàng lẫn kích thước dữ liệu trả về.
- [ ] Đã xem xét CPU, thời gian chờ khóa và thời gian xử lý ở ứng dụng.
- [ ] Đã so sánh trước/sau trong điều kiện tương đương.
- [ ] Đã kiểm tra kết quả nghiệp vụ và tác động đến workload tổng thể.

Đọc logic, đọc vật lý, dung lượng tạm và lượng dữ liệu trả về tạo thành một bức tranh về khối lượng công việc mà truy vấn gây ra ở các tầng khác nhau. Khi kết hợp chúng với kế hoạch thực thi, thống kê, thời gian và tải đồng thời, ta có thể chọn đúng điểm cần cải thiện, kiểm chứng hiệu quả bằng số liệu và tránh thay đổi chỉ mục hoặc cấu hình theo phỏng đoán.
