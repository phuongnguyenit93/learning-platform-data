# Tối ưu theo chi phí và giới hạn của mô hình chi phí

Bộ tối ưu truy vấn (query optimizer) phải lựa chọn cách thực thi một câu SQL trong số nhiều phương án có thể cho cùng kết quả. Với một truy vấn nối nhiều bảng, lọc dữ liệu, sắp xếp và tổng hợp, số phương án có thể rất lớn. Bộ tối ưu thường dùng mô hình chi phí (cost model) để ước lượng tài nguyên cần thiết cho từng phương án, rồi chọn kế hoạch có chi phí ước lượng thấp theo mục tiêu của hệ quản trị.

Tối ưu theo chi phí là nền tảng của nhiều hệ quản trị cơ sở dữ liệu quan hệ. Tuy nhiên, chi phí trong kế hoạch thực thi là một ước lượng theo mô hình, không phải lời cam kết về số mili giây khi chạy thật. Chất lượng lựa chọn phụ thuộc vào thống kê dữ liệu, ước lượng số dòng, giả định về CPU, I/O, bộ nhớ, tính đồng thời và cách hệ quản trị xây dựng kế hoạch. Hiểu cả cách mô hình hoạt động lẫn giới hạn của nó giúp người phát triển đọc execution plan đúng cách, tìm nguyên nhân truy vấn chậm và lựa chọn điều chỉnh có thể kiểm chứng.

Nội dung thuộc chương **Bộ tối ưu truy vấn** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, việc đọc cost estimate cần kết hợp với số liệu thực tế, thống kê và đặc điểm workload trước khi thay đổi SQL, chỉ mục hoặc cấu hình.

## 1. Tối ưu truy vấn theo chi phí là gì?

Một câu SQL mô tả kết quả cần nhận được, nhưng thường không quy định duy nhất cách cơ sở dữ liệu phải lấy dữ liệu. Ví dụ, để tìm các đơn hàng của một khách hàng, hệ quản trị có thể:

- Quét toàn bộ bảng rồi lọc theo customer_id.
- Dùng chỉ mục trên customer_id để tìm các dòng phù hợp.
- Dùng một chỉ mục kết hợp nếu truy vấn còn lọc theo trạng thái hoặc sắp xếp theo thời gian.
- Đọc dữ liệu từ một bảng trước, sau đó nối với bảng khác.
- Thay đổi thứ tự nối để giảm lượng dữ liệu trung gian.

Mỗi phương án có lượng đọc, số phép so sánh, bộ nhớ trung gian, chi phí sắp xếp và khả năng tận dụng tài nguyên khác nhau. Bộ tối ưu truy vấn sinh hoặc khảo sát một tập các phương án hợp lệ, ước lượng chi phí và lựa chọn kế hoạch dựa trên mô hình chi phí cùng các ràng buộc của hệ quản trị.

Quy trình khái quát:

1. Phân tích cú pháp và kiểm tra ý nghĩa câu SQL.
2. Viết lại truy vấn theo các phép biến đổi tương đương mà hệ quản trị hỗ trợ.
3. Tạo các phương án truy cập dữ liệu và thứ tự thực hiện phép nối.
4. Ước lượng số dòng, kích thước dữ liệu trung gian và chi phí toán tử.
5. Kết hợp chi phí của các toán tử thành chi phí của kế hoạch.
6. Chọn kế hoạch có chi phí ước lượng phù hợp nhất trong không gian tìm kiếm.

Kế hoạch cuối cùng có thể gồm quét bảng, quét chỉ mục, nested loop join, hash join, merge join, sort, aggregate, filter hoặc các toán tử riêng của hệ quản trị. Không phải mọi phương án đều được khảo sát: bộ tối ưu thường dùng quy tắc loại bỏ phương án kém, giới hạn thời gian tìm kiếm hoặc chiến lược tìm kiếm riêng để tránh bùng nổ số lượng kế hoạch.

## 2. Mô hình chi phí ước lượng những gì?

Mô hình chi phí là tập quy tắc và hệ số mà bộ tối ưu dùng để ước lượng tài nguyên của một toán tử hoặc kế hoạch. Tùy hệ quản trị, mô hình có thể xem xét:

- **I/O:** số trang hoặc khối dữ liệu cần đọc/ghi, xác suất dữ liệu nằm trong cache và chi phí truy cập lưu trữ.
- **CPU:** số phép so sánh, tính toán biểu thức, kiểm tra điều kiện, xử lý từng dòng và xây dựng cấu trúc dữ liệu.
- **Bộ nhớ:** vùng nhớ cho sort, hash table, aggregate và dữ liệu trung gian.
- **Truyền dữ liệu:** chi phí di chuyển dữ liệu giữa các nút, tiến trình hoặc máy trong hệ thống phân tán.
- **Khởi tạo toán tử:** chi phí mở tài nguyên, chuẩn bị cấu trúc và bắt đầu xử lý.
- **Tính song song:** chi phí phân chia công việc, đồng bộ, trao đổi dữ liệu và kết hợp kết quả.

Một biểu diễn khái quát của chi phí kế hoạch có thể là:

\[
C_{\text{plan}} \approx C_{\text{I/O}} + C_{\text{CPU}}
+ C_{\text{memory}} + C_{\text{network}} + C_{\text{startup}}
\]

Đây là cách mô tả khái niệm, không phải công thức chuẩn được mọi hệ quản trị sử dụng. Nhiều hệ thống quy đổi các thành phần sang đơn vị chi phí nội bộ với trọng số riêng; một số thành phần chỉ được mô hình hóa gần đúng hoặc không được tính trực tiếp.

### Chi phí không phải thời gian thực thi

Giá trị cost thường là đơn vị tương đối hoặc đơn vị nội bộ của hệ quản trị. Cost 100 không có nghĩa truy vấn chạy trong 100 ms; cost 200 cũng không nhất thiết chạy lâu gấp đôi cost 100. Chi phí hữu ích nhất để so sánh các phương án thực thi cùng truy vấn trên cùng hệ quản trị, cùng cấu hình và cùng ngữ cảnh thống kê.

Không nên so sánh trực tiếp cost giữa hai hệ quản trị khác nhau, giữa hai phiên bản có mô hình khác nhau hoặc giữa hai máy có cấu hình rất khác nhau. Ngay cả trong cùng một hệ thống, thay đổi tham số cấu hình, thống kê hoặc trạng thái cache có thể làm cost và kế hoạch thay đổi.

### Startup cost và total cost

Một số hệ quản trị phân biệt chi phí khởi tạo (startup cost) với chi phí hoàn thành toàn bộ toán tử (total cost). Startup cost là phần công việc cần thiết trước khi toán tử có thể trả dòng đầu tiên; total cost là ước lượng để xử lý hết đầu vào và tạo toàn bộ kết quả.

Phân biệt này quan trọng với truy vấn có LIMIT, phân trang hoặc ứng dụng chỉ đọc một phần kết quả. Một kế hoạch có startup cost thấp có thể trả những dòng đầu nhanh hơn, dù total cost cao hơn. Nếu ứng dụng cần toàn bộ kết quả, total cost và thông lượng tổng thể có thể quan trọng hơn.

Ví dụ:

| Phương án | Startup cost minh họa | Total cost minh họa | Đặc điểm |
| --- | ---: | ---: | --- |
| A | 5 | 900 | Có thể trả dòng đầu sớm, tổng công việc lớn |
| B | 80 | 500 | Cần chuẩn bị nhiều hơn, tổng công việc thấp hơn |

Nếu truy vấn lấy một số dòng đầu, phương án A có thể được ưu tiên tùy cách bộ tối ưu đánh giá row goal. Nếu cần đọc toàn bộ kết quả, phương án B có thể có lợi hơn. Các số liệu trên chỉ minh họa cách phân biệt hai loại chi phí, không phải giá trị thực tế của một hệ quản trị.

## 3. Ước lượng số dòng là nền tảng của cost model

Để ước lượng chi phí toán tử, bộ tối ưu cần dự đoán số dòng đi qua từng bước. Đây là cardinality estimation (ước lượng lực lượng). Nếu số dòng ước lượng sai, cost model có thể đánh giá sai toàn bộ kế hoạch.

Ví dụ truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
~~~

Bộ tối ưu cần ước lượng có bao nhiêu dòng thỏa mãn hai điều kiện. Ước lượng này có thể dựa trên:

- Tổng số dòng trong bảng.
- Số giá trị phân biệt của từng cột (NDV).
- Histogram hoặc thống kê phân bố giá trị.
- Tỷ lệ NULL.
- Thống kê tương quan giữa các cột nếu hệ quản trị hỗ trợ.
- Thống kê chỉ mục và đặc điểm phân bố dữ liệu.

Giả sử bảng có 10 triệu đơn hàng. Nếu customer_id có hàng triệu giá trị khác nhau, truy vấn một khách hàng có thể chỉ khớp một số ít dòng. Nhưng nếu một khách hàng lớn chiếm tỷ lệ đơn hàng rất cao, giả định phân bố đồng đều sẽ dẫn đến ước lượng thấp. Tương tự, trạng thái PAID có thể chiếm phần lớn dữ liệu trong khi CANCELLED chỉ chiếm tỷ lệ nhỏ.

### Sai số cardinality lan truyền qua kế hoạch

Sai số ở một toán tử có thể ảnh hưởng đến các toán tử phía sau. Nếu bộ tối ưu dự đoán một phép lọc trả về 10 dòng nhưng thực tế trả về 500.000 dòng, kế hoạch nối hoặc sắp xếp tiếp theo có thể được chọn dựa trên giả định quá lạc quan. Kết quả là:

1. Một nested loop được chọn vì bộ tối ưu nghĩ tập ngoài rất nhỏ.
2. Khi chạy thật, tập ngoài lớn hơn nhiều so với ước lượng.
3. Truy vấn thực hiện rất nhiều lần tra cứu ở bảng trong.
4. Thời gian thực thi tăng mạnh và có thể phát sinh I/O lớn.

Vì vậy, khi đọc execution plan, cần so sánh số dòng ước lượng với số dòng thực tế ở từng toán tử nếu công cụ cung cấp. Một sai lệch lớn thường là dấu hiệu cần kiểm tra thống kê, phân bố dữ liệu, tương quan cột hoặc giá trị tham số.

## 4. Thống kê dữ liệu và các giả định của mô hình

Thống kê (statistics) cung cấp thông tin tóm tắt về dữ liệu để bộ tối ưu ước lượng số dòng và chi phí. Thống kê thường được thu thập tự động hoặc cập nhật theo lệnh của hệ quản trị, nhưng cách lưu và độ chi tiết khác nhau.

Các loại thông tin thường gặp:

- Số dòng ước lượng trong bảng hoặc phân vùng.
- Số giá trị phân biệt của cột.
- Tần suất hoặc histogram của các giá trị.
- Tỷ lệ NULL.
- Độ rộng trung bình của dòng.
- Thống kê chỉ mục và phân bố khóa.
- Tương quan giữa thứ tự vật lý và giá trị logic của dữ liệu.
- Thống kê mở rộng về tương quan nhiều cột, nếu hệ quản trị hỗ trợ.

### Thống kê cũ hoặc thiếu

Khi dữ liệu thay đổi mạnh nhưng thống kê chưa được cập nhật, bộ tối ưu có thể dựa vào bức tranh cũ. Ví dụ, một bảng ban đầu có 90% đơn hàng ở trạng thái PENDING, sau một đợt xử lý hàng loạt tỷ lệ này giảm còn 5%. Histogram cũ có thể khiến bộ tối ưu đánh giá sai số dòng trả về.

Khi gặp kế hoạch bất thường, hãy kiểm tra thời điểm cập nhật thống kê, số dòng ước lượng, số dòng thực tế và mức biến động dữ liệu. Cập nhật thống kê theo cơ chế phù hợp của hệ quản trị rồi đo lại kế hoạch. Không nên cập nhật hoặc xóa toàn bộ thống kê một cách tùy tiện trên hệ thống đang phục vụ tải thật.

### Giả định độc lập giữa các cột

Một số mô hình ước lượng đơn giản giả định các điều kiện lọc độc lập. Nếu điều kiện là country = 'VN' và currency = 'VND', hai cột này có thể tương quan rất mạnh. Nhân xác suất của từng điều kiện như thể chúng độc lập có thể làm sai số dòng ước lượng.

Ví dụ, nếu mỗi điều kiện riêng lẻ có xác suất 10%, mô hình độc lập có thể ước lượng xác suất kết hợp là 1%. Nhưng nếu gần như mọi bản ghi ở Việt Nam đều dùng VND, xác suất kết hợp thực tế có thể gần 10%. Sai số này ảnh hưởng đến lựa chọn chỉ mục, thứ tự nối và thuật toán join.

Một số hệ quản trị có thống kê nhiều cột hoặc extended statistics để mô tả tương quan. Khi có sai lệch rõ rệt giữa ước lượng và thực tế, cần xem khả năng sử dụng thống kê phù hợp, đồng thời đánh giá tần suất cập nhật và chi phí thu thập.

### Phân bố lệch (data skew)

Giá trị dữ liệu có thể phân bố không đồng đều. Một số khách hàng có hàng triệu giao dịch, trong khi phần lớn chỉ có vài giao dịch. Một số trạng thái hoặc mã vùng xuất hiện rất thường xuyên, những giá trị khác rất hiếm.

Giá trị trung bình hoặc số giá trị phân biệt không luôn mô tả được phần đuôi của phân bố. Histogram, most-common values hoặc thống kê tần suất có thể giúp mô hình nhận biết các giá trị phổ biến. Tuy vậy, histogram vẫn có giới hạn về số bucket, cách lấy mẫu và khả năng mô tả tương quan nhiều chiều.

## 5. Cost model lựa chọn đường truy cập dữ liệu

Đối với một bảng, bộ tối ưu có thể cân nhắc quét tuần tự, quét chỉ mục hoặc các biến thể truy cập khác. Việc lựa chọn phụ thuộc vào số dòng cần đọc, độ chọn lọc điều kiện, chi phí I/O và khả năng tận dụng dữ liệu đã nằm trong bộ nhớ.

### Quét tuần tự và quét chỉ mục

Quét tuần tự đọc lần lượt các trang của bảng. Nếu truy vấn cần phần lớn dòng hoặc bảng nhỏ, quét tuần tự có thể rẻ hơn việc đi qua chỉ mục rồi đọc từng trang dữ liệu rời rạc.

Quét chỉ mục phù hợp khi điều kiện lọc chọn được ít dòng và chỉ mục có thể xác định nhanh vị trí dữ liệu. Nhưng nếu truy vấn trả về tỷ lệ lớn của bảng, nhiều lần tra cứu trang dữ liệu có thể làm I/O ngẫu nhiên tăng lên. Khi đó, quét tuần tự có thể có cost thấp hơn.

Ví dụ:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'CANCELLED';
~~~

Nếu CANCELLED chỉ chiếm 0,1% bảng, chỉ mục trên status có thể hữu ích. Nếu CANCELLED chiếm 80% bảng, quét tuần tự có thể là lựa chọn hợp lý. Không thể kết luận chỉ mục luôn nhanh hơn chỉ vì điều kiện WHERE sử dụng cột có chỉ mục.

### Điều kiện sắp xếp và phân trang

Một chỉ mục phù hợp có thể cung cấp dữ liệu theo thứ tự cần thiết, giảm hoặc loại bỏ thao tác sort. Nhưng nếu thứ tự cột chỉ mục không phù hợp với điều kiện lọc hoặc thứ tự ORDER BY, bộ tối ưu có thể vẫn phải sắp xếp.

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 50;
~~~

Một chỉ mục có customer_id làm cột dẫn đầu và created_at theo thứ tự phù hợp có thể giúp truy cập và trả các dòng đầu nhanh hơn. Lợi ích cần được xác nhận bằng kế hoạch và đo thực tế. Với phân trang sâu bằng OFFSET lớn, hệ quản trị có thể vẫn phải bỏ qua nhiều dòng; keyset pagination có thể giảm công việc trong một số workload nhưng phải giữ đúng ngữ nghĩa phân trang.

## 6. Cost model lựa chọn thuật toán JOIN

Nối bảng là nơi sai số cardinality có thể gây ảnh hưởng lớn. Các thuật toán phổ biến gồm nested loop join, hash join và merge join. Mỗi thuật toán có điều kiện phù hợp khác nhau.

| Thuật toán | Cách hoạt động | Thường phù hợp khi |
| --- | --- | --- |
| Nested loop join | Với mỗi dòng từ đầu vào ngoài, tìm dòng khớp ở đầu vào trong | Đầu vào ngoài nhỏ và đầu vào trong có đường tra cứu hiệu quả |
| Hash join | Xây dựng hash table từ một đầu vào rồi dò các dòng của đầu vào còn lại | Nối theo điều kiện tương đương và một đầu vào đủ nhỏ để xây dựng cấu trúc hash |
| Merge join | Đọc hai đầu vào đã được sắp xếp theo khóa nối và ghép các dòng tương ứng | Hai đầu vào có thứ tự phù hợp hoặc chi phí sắp xếp hợp lý |

Không có thuật toán JOIN nào luôn tốt nhất. Nested loop có thể rất nhanh khi chỉ có vài dòng và chỉ mục phù hợp; nếu đầu vào ngoài lớn, số lần tra cứu lặp lại có thể tăng mạnh. Hash join có thể hiệu quả với tập dữ liệu lớn nhưng cần bộ nhớ; nếu hash table vượt ngân sách, hệ quản trị có thể chia partition hoặc ghi dữ liệu tạm ra lưu trữ. Merge join có thể tiết kiệm chi phí khi dữ liệu đã được sắp xếp, nhưng việc sort hai đầu vào lớn có thể tốn CPU, bộ nhớ và I/O.

### Thứ tự JOIN

Với nhiều bảng, thứ tự nối ảnh hưởng đến kích thước dữ liệu trung gian. Bộ tối ưu thường cố gắng thực hiện các phép lọc sớm và nối những tập dữ liệu có kích thước phù hợp, nhưng lựa chọn tốt phụ thuộc vào ước lượng số dòng.

Ví dụ:

~~~sql
SELECT c.customer_name, o.order_id, p.payment_status
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
JOIN payments p ON p.order_id = o.order_id
WHERE c.region = 'NORTH'
  AND o.created_at >= DATE '2026-01-01';
~~~

Bộ tối ưu có thể bắt đầu từ khách hàng thuộc vùng NORTH, từ đơn hàng trong khoảng ngày, hoặc chọn một thứ tự khác dựa trên thống kê và đường truy cập. Nếu vùng NORTH rất hiếm, lọc khách hàng trước có thể giảm tập dữ liệu trung gian. Nếu khoảng ngày chỉ chứa rất ít đơn hàng, bắt đầu từ orders có thể hiệu quả hơn.

Không nên viết lại thứ tự bảng trong SQL với giả định rằng thứ tự xuất hiện luôn quyết định thứ tự thực thi. Nhiều hệ quản trị có thể tự sắp xếp lại phép nối. Hãy đọc execution plan để biết kế hoạch thực tế.

## 7. Giới hạn quan trọng của mô hình chi phí

Cost model không mô phỏng hoàn hảo mọi trạng thái runtime. Mô hình cần đơn giản và đủ nhanh để đánh giá nhiều kế hoạch, nên luôn có giả định và sai số.

### Sai số thống kê và cardinality

Nếu thống kê cũ, lấy mẫu không đại diện hoặc thiếu thông tin về tương quan và độ lệch, cardinality estimation sẽ sai. Khi số dòng ước lượng sai, các cost ở bước sau cũng sai. Đây là một trong những nguyên nhân phổ biến khiến kế hoạch được đánh giá tốt nhưng chạy thực tế chậm.

### Khác biệt giữa tham số

Cùng một fingerprint có thể nhận các giá trị tham số có độ chọn lọc rất khác nhau. Kế hoạch phù hợp với khách hàng có ít đơn hàng có thể không phù hợp với khách hàng có hàng triệu đơn hàng. Cơ chế parameter sniffing, bind peeking, plan cache hoặc generic plan của từng hệ quản trị ảnh hưởng đến cách kế hoạch được tạo và tái sử dụng.

Khi nghi ngờ parameter sensitivity, hãy so sánh số dòng thực tế, thời gian và plan theo nhóm tham số an toàn. Không lưu giá trị nhạy cảm chỉ để phân tích. Có thể dùng nhóm độ chọn lọc, khoảng giá trị hoặc mẫu đã khử định danh.

### Cache và I/O thực tế

Cost model thường phải giả định tỷ lệ cache hit hoặc dùng các hệ số I/O được cấu hình. Trạng thái cache thật có thể thay đổi theo workload và thời điểm. Một kế hoạch có nhiều lần đọc trang có thể chạy nhanh khi dữ liệu nằm trong bộ nhớ nhưng chậm khi phải đọc từ lưu trữ. Ngược lại, ước lượng I/O ngẫu nhiên có thể không phản ánh chính xác đặc tính thiết bị lưu trữ hiện đại.

### Tải đồng thời và tranh chấp

Cost model thường ước lượng công việc của truy vấn trong một trạng thái hệ thống nhất định, nhưng không phải lúc nào cũng dự đoán chính xác việc chờ khóa, latch, CPU scheduler, connection pool hoặc hàng đợi I/O do các phiên khác tạo ra. Một truy vấn có cost thấp vẫn có thể chậm nếu phải chờ giao dịch khác giữ khóa hoặc hệ thống đang bão hòa.

### Bộ nhớ và spill ra đĩa

Sort hoặc hash operation có thể cần nhiều bộ nhớ hơn dự kiến. Khi không đủ memory grant hoặc work memory, hệ quản trị có thể spill dữ liệu trung gian ra đĩa. Cost model có thể ước lượng chi phí này chưa chính xác nếu kích thước dòng, số dòng hoặc mức đồng thời khác với giả định. Cần kiểm tra cảnh báo spill, temp I/O và memory grant trong execution plan hoặc công cụ giám sát tương ứng.

### Hàm, biểu thức và logic tùy biến

Các hàm do người dùng định nghĩa, hàm bên ngoài, biểu thức phức tạp hoặc logic có chi phí không rõ có thể khó được ước lượng. Bộ tối ưu có thể dùng một giả định mặc định về số dòng hoặc chi phí CPU, dẫn đến đánh giá sai. Một điều kiện áp dụng hàm lên cột cũng có thể làm giảm khả năng dùng chỉ mục thông thường, tùy hệ quản trị và loại chỉ mục.

### Song song và hệ thống phân tán

Thực thi song song có thể giảm thời gian đồng hồ bằng cách chia công việc, nhưng cũng có chi phí khởi tạo worker, trao đổi dữ liệu và đồng bộ. Nếu số worker thực tế khác dự kiến hoặc một nhánh bị lệch tải, hiệu quả song song có thể thấp. Trong hệ phân tán, chi phí truyền dữ liệu qua mạng và phân phối dữ liệu giữa các nút có thể chi phối thời gian, trong khi mô hình ước lượng không phản ánh đầy đủ độ trễ mạng hoặc skew giữa các node.

### Không gian tìm kiếm bị giới hạn

Bộ tối ưu không phải lúc nào cũng kiểm tra mọi kế hoạch có thể. Với truy vấn phức tạp, số cách nối và toán tử tăng rất nhanh. Để giới hạn thời gian lập kế hoạch, hệ quản trị dùng heuristic, pruning, giới hạn tìm kiếm hoặc chiến lược tối ưu hóa riêng. Kế hoạch được chọn vì là phương án tốt nhất trong tập đã xem xét, không nhất thiết là phương án tốt nhất tuyệt đối.

## 8. Đọc execution plan để kiểm tra ước lượng

Execution plan thể hiện cách hệ quản trị dự định hoặc đã thực hiện truy vấn. Tên toán tử và cách trình bày khác nhau theo nền tảng, nhưng các điểm cần quan sát thường gồm:

- Loại scan và đường truy cập: sequential/table scan, index scan, index seek hoặc biến thể tương ứng.
- Thứ tự và thuật toán JOIN.
- Số dòng ước lượng và số dòng thực tế.
- Chi phí startup và total nếu được hiển thị.
- Số lần thực thi của toán tử (loops hoặc executions).
- Số trang đọc, buffer hit, CPU, elapsed time và wait nếu công cụ cung cấp.
- Sort, hash, aggregate, spool hoặc dữ liệu tạm.
- Cảnh báo spill, memory grant, implicit conversion hoặc truy cập không mong muốn.

### Ví dụ kế hoạch giả định

Giả sử kế hoạch hiển thị một toán tử lọc có số dòng ước lượng là 100 nhưng số dòng thực tế là 80. Sai lệch nhỏ trong ví dụ này có thể không đáng lo. Nếu số dòng thực tế là 200.000, chênh lệch rất lớn và có thể làm kế hoạch JOIN phía sau không phù hợp.

| Toán tử | Dòng ước lượng | Dòng thực tế | Nhận xét |
| --- | ---: | ---: | --- |
| Filter orders | 100 | 200.000 | Sai lệch cardinality lớn |
| Nested loop | 100 | 200.000 | Có thể phát sinh nhiều lượt tra cứu hơn dự kiến |
| Lookup payments | 1 mỗi dòng ngoài | 1 mỗi dòng ngoài | Tổng số lần lookup tăng theo đầu vào ngoài |

Các số liệu trên chỉ minh họa. Trong thực tế, cần đọc cả số lần thực thi và số dòng mỗi lần; một toán tử có thể trả ít dòng mỗi vòng nhưng được lặp hàng trăm nghìn lần.

Một số hệ quản trị cung cấp chế độ phân tích kế hoạch khi thực thi, ví dụ EXPLAIN ANALYZE hoặc công cụ tương đương. Lệnh này có thể thực sự chạy truy vấn và tạo tải; với câu DML, tùy hệ quản trị và cách sử dụng, nó có thể tác động dữ liệu. Hãy đọc tài liệu của nền tảng, dùng môi trường kiểm thử hoặc giao dịch có thể rollback khi phù hợp, và tránh chạy truy vấn nặng tùy tiện trên production.

## 9. Cách xử lý khi cost estimate không phản ánh thực tế

Khi truy vấn có cost thấp nhưng chạy chậm, hoặc kế hoạch chọn toán tử bất thường, hãy điều tra theo thứ tự có hệ thống.

### Bước 1: Xác nhận phạm vi và phép đo

Đảm bảo thời gian đang so sánh cùng loại: elapsed time, CPU time, thời gian chờ hay tổng thời gian của các lần thực thi. Kiểm tra workload, tham số, số client, trạng thái cache và khoảng thời gian. Một truy vấn có thời gian elapsed cao nhưng CPU thấp thường cần điều tra wait hoặc I/O.

### Bước 2: So sánh số dòng ước lượng và thực tế

Tìm toán tử đầu tiên có sai lệch lớn. Sai số ở đầu kế hoạch thường lan truyền đến các phép JOIN, sort và aggregate phía sau. Kiểm tra thống kê bảng/cột, histogram, số dòng và độ lệch dữ liệu.

### Bước 3: Kiểm tra đường truy cập và chỉ mục

Xác định truy vấn có đang quét nhiều trang không, có dùng đúng chỉ mục không, điều kiện lọc có sargable không và có implicit conversion hay biểu thức làm mất khả năng seek không. Đánh giá độ chọn lọc, thứ tự cột trong chỉ mục và tác động đến workload ghi.

### Bước 4: Kiểm tra thuật toán JOIN và dữ liệu trung gian

Nếu nested loop lặp quá nhiều lần, xem kích thước đầu vào và khả năng tra cứu ở bảng trong. Nếu hash join spill, xem bộ nhớ, kích thước hash và temp I/O. Nếu merge join phải sort đầu vào lớn, kiểm tra khả năng cung cấp thứ tự từ chỉ mục.

### Bước 5: Kiểm tra wait và tài nguyên

Đối chiếu CPU, bộ nhớ, I/O, lock wait, latch wait, network và mức đồng thời. Cost thấp không loại trừ khả năng truy vấn phải chờ tài nguyên bên ngoài phần công việc được mô hình hóa.

### Bước 6: Thay đổi một yếu tố và đo lại

Có thể cập nhật thống kê, điều chỉnh chỉ mục, viết lại SQL, thay đổi cách phân trang hoặc giảm thời gian giữ giao dịch. Ghi lại giả thuyết, kế hoạch cũ/mới và chỉ số trước/sau. Không thay nhiều yếu tố cùng lúc nếu mục tiêu là xác định nguyên nhân.

## 10. Vai trò của hint và cấu hình cost model

Một số hệ quản trị cung cấp optimizer hint hoặc tham số để ảnh hưởng đến lựa chọn kế hoạch. Chúng có thể hữu ích khi đã xác định rõ mô hình đang đánh giá sai và có bằng chứng rằng kế hoạch khác ổn định hơn. Tuy nhiên, hint có thể khóa hệ thống vào một phương án không còn phù hợp khi dữ liệu, tham số hoặc phiên bản thay đổi.

Trước khi dùng hint, hãy:

- Xác nhận thống kê còn mới và đủ đại diện.
- Kiểm tra số dòng ước lượng với số dòng thực tế.
- Đánh giá khả năng tạo chỉ mục hoặc sửa câu SQL để mô hình nhận biết đường truy cập phù hợp.
- Đo nhiều nhóm tham số và workload liên quan.
- Ghi lại lý do, phạm vi, phiên bản và điều kiện cần xem xét lại hint.
- Chuẩn bị cách gỡ hint hoặc hoàn nguyên cấu hình.

Không nên chỉnh hệ số cost model chỉ để một truy vấn cụ thể chọn kế hoạch mong muốn. Hệ số có thể ảnh hưởng đến nhiều truy vấn trong toàn hệ thống. Chỉ thay đổi khi có số liệu đại diện cho workload, hiểu tác động rộng và có quy trình kiểm chứng/hoàn tác.

## 11. Ví dụ thực hành: vì sao kế hoạch có cost thấp lại chạy chậm?

Một API lấy lịch sử đơn hàng có truy vấn nối orders với payments. Khi kiểm tra execution plan, nhóm thấy bộ tối ưu chọn nested loop join với cost ước lượng thấp. Tuy nhiên, thời gian thực tế tăng mạnh vào giờ cao điểm.

### Quan sát ban đầu

Nhóm ghi nhận:

- Fingerprint truy vấn và nhóm tham số khách hàng.
- Số lần thực thi, p50/p95/p99 và tổng thời gian.
- Kế hoạch thực thi, số dòng ước lượng/thực tế và số lần lookup.
- Thống kê trên orders.customer_id, orders.status và payments.order_id.
- CPU, logical reads, physical reads, lock wait và mức đồng thời.

Kế hoạch ước lượng đầu vào ngoài của nested loop chỉ có 20 dòng. Khi đo với một khách hàng lớn, số dòng thực tế lên tới 150.000. Mỗi dòng lại kích hoạt một lần tra cứu ở payments, khiến số lượt lookup tăng rất lớn. Đây là dấu hiệu cost model đã dựa trên ước lượng cardinality không đại diện cho giá trị tham số này.

### Điều tra nguyên nhân

Nhóm kiểm tra histogram và thống kê, nhận thấy phân bố customer_id lệch mạnh. Một số khách hàng có lượng đơn hàng lớn hơn nhiều so với phần còn lại. Kế hoạch dùng chung hoặc kế hoạch được tái sử dụng cho các giá trị tham số khác nhau chưa phù hợp với nhóm khách hàng lớn.

Nhóm cũng kiểm tra chỉ mục trên khóa nối payments.order_id, số dòng đọc và chi phí lookup. Nếu thống kê hoặc chỉ mục thiếu, cần xử lý trước khi kết luận thuật toán JOIN là nguyên nhân duy nhất.

### Thử phương án và xác nhận

Nhóm thử cập nhật thống kê phù hợp và đánh giá các phương án kế hoạch trong môi trường có dữ liệu đại diện. Với nhóm tham số có nhiều đơn hàng, một hash join hoặc một kế hoạch khác có thể giảm số lượt tra cứu lặp lại; lựa chọn cụ thể phải dựa trên cost, bộ nhớ, spill và số liệu thực tế.

Sau mỗi thay đổi, nhóm so sánh:

- Số dòng ước lượng và thực tế.
- Thuật toán JOIN và số lần thực thi từng toán tử.
- p95/p99, tổng thời gian và throughput.
- CPU, bộ nhớ, I/O, temp spill và lock wait.
- Kết quả đơn hàng và thanh toán trả về.

Nếu một kế hoạch nhanh hơn cho khách hàng lớn nhưng chậm hơn đáng kể cho nhóm khách hàng nhỏ, cần đánh giá theo toàn bộ workload hoặc tách cách xử lý khi có lý do nghiệp vụ rõ ràng. Không thể chọn kế hoạch chỉ dựa trên một mẫu tham số.

## 12. Quy trình tối ưu dựa trên cost model

Một quy trình có thể lặp lại gồm:

1. **Thu thập workload:** chọn fingerprint, tần suất, tham số đại diện, độ trễ và mức tải.
2. **Ghi baseline:** lưu kế hoạch, cost estimate, số dòng ước lượng, số liệu thực tế và trạng thái thống kê.
3. **Tìm sai lệch:** xác định toán tử đầu tiên có cardinality estimate khác xa actual rows hoặc có cost không tương xứng với thời gian thực tế.
4. **Kiểm tra giả định:** xem histogram, độ lệch dữ liệu, tương quan cột, cache, memory, I/O và mức đồng thời.
5. **Đề xuất điều chỉnh:** cập nhật thống kê, điều chỉnh chỉ mục, viết lại truy vấn hoặc thay đổi cấu trúc workload nếu cần.
6. **Đo lại:** chạy cùng kịch bản với cùng nhóm tham số, trạng thái cache và mức tải; lưu plan mới và metric thực tế.
7. **Đánh giá tác động rộng:** xem các truy vấn khác, chi phí ghi, dung lượng, lỗi và độ ổn định.
8. **Theo dõi và hoàn nguyên:** chỉ giữ thay đổi khi có bằng chứng ổn định; chuẩn bị cách rollback nếu kế hoạch hoặc workload xấu đi.

Mỗi kết luận cần chỉ ra bằng chứng cụ thể. Ví dụ: “cập nhật thống kê giúp estimate của filter gần actual rows hơn, nested loop không còn lặp quá nhiều lần và p95 của nhóm tham số lớn giảm trong cùng mức tải”. Cách diễn đạt này có thể kiểm tra lại bằng execution plan và metric.

## 13. Những hiểu lầm thường gặp

- **Cost thấp nghĩa là truy vấn nhanh:** cost là ước lượng tương đối, không phải thời gian thực thi.
- **Chỉ mục luôn tốt hơn quét bảng:** quét tuần tự có thể rẻ hơn khi cần phần lớn dữ liệu hoặc bảng nhỏ.
- **Optimizer luôn chọn kế hoạch tốt nhất tuyệt đối:** nó chọn trong không gian tìm kiếm và theo mô hình, giả định hiện có.
- **Một fingerprint chỉ có một hành vi:** giá trị tham số và phân bố dữ liệu có thể tạo ra độ trễ rất khác nhau.
- **Sai số chỉ ảnh hưởng toán tử đầu tiên:** sai cardinality có thể lan truyền qua JOIN, sort, aggregate và các bước sau.
- **Cost không tính đến mọi loại chờ:** lock, scheduler, network, cache và tranh chấp runtime có thể không được mô hình đầy đủ.
- **Hint là cách sửa mặc định:** hint có thể che khuất vấn đề thống kê và gây kế hoạch kém khi workload thay đổi.
- **Cost giữa các hệ quản trị có thể so sánh:** mỗi nền tảng có đơn vị, hệ số và cách ước lượng riêng.

## 14. Nguyên tắc cần ghi nhớ

- Cost model giúp bộ tối ưu so sánh các phương án thực thi bằng cách ước lượng tài nguyên, không dự đoán chính xác thời gian chạy trong mọi tình huống.
- Cardinality estimation là đầu vào quan trọng; cần so sánh estimated rows với actual rows khi có thể.
- Thống kê cũ, dữ liệu lệch, tương quan cột và độ nhạy tham số có thể khiến bộ tối ưu chọn kế hoạch không phù hợp.
- Scan, index access và thuật toán JOIN đều có vùng sử dụng hiệu quả riêng; không có một lựa chọn luôn tốt nhất.
- Phân biệt startup cost và total cost, đặc biệt với truy vấn có LIMIT hoặc chỉ đọc một phần kết quả.
- Đọc execution plan cùng metric runtime, wait, CPU, memory, I/O và trạng thái cache.
- Dùng hint hoặc chỉnh cost parameter thận trọng, dựa trên workload đại diện và có kế hoạch hoàn tác.
- Kiểm chứng mọi thay đổi bằng cùng điều kiện tải, nhóm tham số và kiểm tra tính đúng đắn của kết quả.

Tối ưu theo chi phí giúp bộ tối ưu truy vấn lựa chọn phương án thực thi có cơ sở thay vì dựa vào quy tắc đơn giản. Khi hiểu cách cost model ước lượng công việc và nhận biết các giả định có thể sai, người phát triển có thể đọc kế hoạch chính xác hơn, tìm đúng nguồn sai lệch và cải thiện hiệu năng bằng các thay đổi được đo lường.
