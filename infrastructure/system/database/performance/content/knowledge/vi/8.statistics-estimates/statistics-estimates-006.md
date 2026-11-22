# Thống kê lỗi thời, thay đổi dữ liệu lớn và thời điểm cập nhật

Bộ tối ưu truy vấn cần ước lượng số hàng sẽ đi qua từng bước của kế hoạch thực thi. Những ước lượng này ảnh hưởng đến việc chọn quét bảng hay chỉ mục, thứ tự nối bảng, thuật toán nối, cách sắp xếp và lượng bộ nhớ dành cho các thao tác trung gian. Nếu thống kê mô tả dữ liệu đã khác xa dữ liệu hiện tại, bộ tối ưu có thể chọn một kế hoạch hợp lý theo thông tin cũ nhưng kém hiệu quả khi thực thi.

Trong chương **Thống kê và ước lượng** của module **DATABASE_PERFORMANCE**, bài học này tập trung vào cách nhận diện thống kê lỗi thời, hiểu tác động của những đợt thay đổi dữ liệu lớn và chọn thời điểm cập nhật phù hợp. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, cập nhật thống kê cần dựa trên bằng chứng về phân bố dữ liệu và workload, sau đó được kiểm chứng bằng kế hoạch cùng số liệu thực tế.

## 1. Thống kê giúp bộ tối ưu dự đoán điều gì?

Thống kê là thông tin tóm tắt về dữ liệu mà hệ quản trị dùng để ước lượng chi phí của các phương án truy vấn. Tùy hệ quản trị, thống kê có thể được lưu ở cấp bảng, phân vùng, cột, nhóm cột, chỉ mục hoặc biểu thức.

Một số thông tin thường gặp:

- Số hàng và số trang dữ liệu của bảng.
- Số giá trị khác nhau trong một cột (distinct count).
- Tỷ lệ NULL.
- Giá trị phổ biến và tần suất xuất hiện.
- Histogram mô tả phân bố giá trị theo khoảng hoặc nhóm.
- Tương quan giữa các cột hoặc thống kê mở rộng.
- Số trang, độ cao, độ phân biệt và các đặc điểm của chỉ mục.
- Thông tin riêng cho từng phân vùng và thông tin tổng hợp ở bảng cha.

Ví dụ, bảng orders có 20 triệu hàng. Thống kê cho biết cột status có bốn giá trị khác nhau, trong đó PAID chiếm 90%, PENDING chiếm 7%, CANCELLED chiếm 2% và FAILED chiếm 1%. Bộ tối ưu có thể dùng phân bố này để dự đoán số hàng của điều kiện lọc.

Nếu một truy vấn lọc status = 'FAILED', số hàng dự kiến có thể nhỏ. Nếu truy vấn lọc status = 'PAID', số hàng dự kiến có thể rất lớn. Chỉ biết có bốn giá trị khác nhau là chưa đủ để phân biệt hai trường hợp này; thông tin về tần suất và histogram có ý nghĩa quan trọng.

Thống kê không phải bản sao đầy đủ của bảng. Nhiều hệ quản trị dùng lấy mẫu hoặc cấu trúc tóm tắt để giảm chi phí thu thập và lưu trữ. Do đó, ước lượng luôn có thể có sai số. Mục tiêu là cung cấp thông tin đủ tốt cho bộ tối ưu, không phải mô tả chính xác từng hàng.

## 2. Thống kê lỗi thời hình thành như thế nào?

Thống kê trở nên lỗi thời khi dữ liệu thực tế thay đổi đáng kể so với thời điểm hoặc phạm vi thu thập gần nhất. Các thay đổi thường gặp gồm:

- Chèn thêm lượng lớn hàng sau một lần import hoặc bulk load.
- Xóa hoặc cập nhật hàng trên một tỷ lệ lớn của bảng.
- Dữ liệu mới tập trung vào một khoảng thời gian hoặc một nhóm giá trị.
- Một trạng thái nghiệp vụ tăng hoặc giảm mạnh theo thời gian.
- Phân bố dữ liệu thay đổi theo tenant, khu vực hoặc loại khách hàng.
- Một cột có tương quan khác trước với cột khác.
- Một phân vùng mới được tạo và nạp dữ liệu nhưng thống kê tổng hợp chưa phản ánh nó.
- Bảng tăng trưởng nhanh trong khi lịch tự động thu thập thống kê không chạy đủ thường xuyên.

Thời gian kể từ lần cập nhật gần nhất chỉ là một tín hiệu. Thống kê cập nhật hôm qua vẫn có thể không đại diện cho dữ liệu hiện tại nếu sáng nay vừa nạp thêm hàng trăm triệu bản ghi. Ngược lại, thống kê đã vài tháng tuổi có thể vẫn đủ tốt với bảng ít thay đổi và phân bố ổn định.

Cần phân biệt hai khái niệm:

- **Tuổi của thống kê:** đã bao lâu kể từ lần thu thập hoặc cập nhật gần nhất.
- **Mức độ lỗi thời:** thống kê còn đại diện cho dữ liệu mà workload hiện tại truy vấn hay không.

Không nên dùng tuổi thống kê như tiêu chí duy nhất để quyết định cập nhật. Hãy kết hợp lịch sử thay đổi dữ liệu, mức độ lệch giữa ước lượng và thực tế, kế hoạch truy vấn và ảnh hưởng đến workload.

## 3. Thay đổi dữ liệu lớn có thể làm sai lệch ước lượng ra sao?

### 3.1. Bulk load hoặc import dữ liệu

Giả sử bảng events ban đầu có 2 triệu hàng, phần lớn được tạo trong hai năm trước. Một đợt import nạp thêm 30 triệu sự kiện chỉ trong một ngày. Nếu thống kê chưa được cập nhật, bộ tối ưu có thể tiếp tục dự đoán quy mô bảng và phân bố thời gian dựa trên dữ liệu cũ.

Một truy vấn lấy sự kiện trong ngày gần nhất có thể được ước lượng là rất ít hàng hoặc ngược lại, tùy thống kê trước đó. Kế hoạch có thể chọn đường truy cập không phù hợp, cấp bộ nhớ không đủ cho sort/hash hoặc chọn sai thứ tự nối.

Sau bulk load, hãy xác định các truy vấn quan trọng cần chạy ngay và thu thập thống kê phù hợp trước khi workload đó bắt đầu nếu quy trình vận hành cho phép. Đừng giả định tác vụ tự động sẽ cập nhật tức thì sau khi nạp dữ liệu.

### 3.2. Xóa hoặc cập nhật hàng loạt

Một thao tác xóa lớn có thể làm số hàng và phân bố giá trị thay đổi đáng kể. Một thao tác cập nhật có thể chuyển hàng loạt bản ghi từ trạng thái cũ sang trạng thái mới, làm histogram trước đó không còn phản ánh tần suất hiện tại.

Ví dụ, chiến dịch xử lý đơn hàng chuyển 8 triệu bản ghi từ PENDING sang PAID. Thống kê cũ vẫn cho rằng PENDING chiếm phần lớn bảng, khiến truy vấn lọc PENDING được ước lượng cao hơn thực tế. Nếu truy vấn đó nằm trong đường nghiệp vụ quan trọng, kế hoạch đã chọn có thể không còn phù hợp.

Cần đánh giá thống kê sau khi hoàn tất thay đổi dữ liệu, nhất là khi thay đổi tập trung vào một số giá trị hoặc cột được dùng trong điều kiện lọc.

### 3.3. Dữ liệu mới có phân bố khác dữ liệu cũ

Một bảng có thể tăng trưởng nhưng phân bố tổng thể thay đổi ít. Tuy nhiên, dữ liệu mới đôi khi có đặc điểm rất khác. Ví dụ, một nền tảng thương mại điện tử mở thêm khu vực mới, nơi phần lớn đơn hàng thuộc một nhóm trạng thái hoặc tenant có quy mô lớn hơn nhiều các tenant trước đó.

Thống kê tổng hợp có thể che giấu sự khác biệt này. Một giá trị hiếm trên toàn bảng có thể rất phổ biến trong một tenant cụ thể. Nếu workload thường lọc đồng thời theo tenant_id và status, thống kê riêng lẻ của từng cột có thể không đủ để ước lượng kết hợp.

Đây là lúc cần xem xét thống kê đa cột, thống kê mở rộng hoặc histogram phù hợp nếu hệ quản trị hỗ trợ. Trước khi tạo thống kê bổ sung, hãy chứng minh rằng sai lệch ước lượng xuất phát từ tương quan hoặc phân bố cụ thể.

### 3.4. Dữ liệu tăng theo thời gian

Bảng giao dịch, log và sự kiện thường có tính thời gian: phần lớn truy vấn quan tâm đến dữ liệu gần đây, trong khi dữ liệu cũ ít được truy cập. Phân bố giá trị ở đầu và cuối dải thời gian có thể khác nhau.

Nếu thống kê chỉ phản ánh phân bố tổng thể, bộ tối ưu có thể ước lượng chưa tốt cho điều kiện khoảng thời gian rất mới. Một số hệ quản trị hỗ trợ histogram hoặc thống kê theo cột để mô tả phân bố, nhưng khả năng nhận diện xu hướng mới còn phụ thuộc cách lấy mẫu và cập nhật.

Khi điều tra, hãy so sánh truy vấn trên nhiều khoảng thời gian: vài phút gần nhất, vài ngày gần nhất và một khoảng lịch sử. Nếu chỉ một vùng dữ liệu bị chậm hoặc sai ước lượng, hãy kiểm tra xem thống kê có đại diện vùng đó hay không.

## 4. Dấu hiệu cho thấy thống kê có thể không còn phù hợp

Không có một cảnh báo duy nhất chứng minh thống kê đã lỗi thời. Hãy tìm nhiều dấu hiệu cùng lúc:

| Dấu hiệu | Điều có thể xảy ra | Bằng chứng cần kiểm tra |
|---|---|---|
| Số hàng ước lượng lệch xa số hàng thực tế | Bộ tối ưu dự đoán sai cardinality | EXPLAIN và số liệu thực thi thực tế |
| Kế hoạch đổi sau một đợt nạp hoặc xóa dữ liệu | Phân bố dữ liệu hoặc metadata thay đổi | Lịch sử thay đổi dữ liệu, thời điểm cập nhật thống kê |
| Truy vấn trước đây nhanh nay chậm dù SQL không đổi | Dữ liệu và workload đã thay đổi | Kế hoạch hiện tại, số hàng đọc, I/O và tham số |
| Một giá trị tham số nhanh, giá trị khác rất chậm | Phân bố lệch hoặc tham số nhạy cảm | Kế hoạch theo từng nhóm giá trị, histogram |
| Sort hoặc hash tràn ra vùng tạm | Ước lượng số hàng hoặc bộ nhớ không phù hợp | Estimated rows, actual rows, spill và memory |
| Thống kê không được cập nhật sau bulk load | Tác vụ tự động chưa chạy hoặc ngưỡng chưa đạt | Metadata thống kê, lịch sử job và số hàng thay đổi |
| Truy vấn lọc hai cột có sai lệch lớn | Tương quan giữa cột chưa được mô tả | Thống kê đa cột và phân bố thực tế |

Một sai lệch nhỏ ở bước đầu có thể khuếch đại qua nhiều phép nối. Nếu bộ tối ưu ước lượng đầu vào của join thấp hơn thực tế hàng nghìn lần, các toán tử phía sau cũng có thể được chọn dựa trên giả định sai.

Khi dùng EXPLAIN ANALYZE hoặc chế độ tương đương, hãy nhớ rằng một số lệnh phân tích thực tế sẽ thực thi câu lệnh. Với thao tác ghi, hãy đọc tài liệu hệ quản trị và dùng môi trường hoặc cơ chế giao dịch an toàn. Không chạy một lệnh phân tích có thể gây thay đổi dữ liệu trên production chỉ để lấy số liệu mà chưa đánh giá tác động.

## 5. Cập nhật thống kê bằng cách nào?

Phần lớn hệ quản trị có lệnh hoặc tác vụ để thu thập lại thống kê. Tên lệnh, phạm vi, mức lấy mẫu, quyền cần thiết và tác động vận hành khác nhau.

Ví dụ với PostgreSQL:

~~~sql
ANALYZE orders;
~~~

Lệnh ANALYZE thu thập thống kê cho bảng được chỉ định. Có thể thu thập thống kê cho một số cột cụ thể khi cần:

~~~sql
ANALYZE orders (tenant_id, status, created_at);
~~~

Trong PostgreSQL, VACUUM và ANALYZE là hai công việc khác nhau. VACUUM xử lý các phiên bản hàng chết và hỗ trợ bảo trì bảng; ANALYZE thu thập thống kê cho bộ tối ưu. VACUUM ANALYZE kết hợp hai công việc, nhưng không phải lúc nào cũng cần chạy cả hai chỉ để làm mới thống kê.

Ví dụ này chỉ áp dụng cho PostgreSQL. Với hệ quản trị khác, hãy dùng lệnh hoặc API thống kê chính thức của nền tảng đó và kiểm tra tài liệu về phạm vi, mức lấy mẫu, quyền, khóa và cách cập nhật metadata.

### 5.1. Thu thập toàn bảng hay một số cột?

Nếu vấn đề liên quan đến nhiều cột và nhiều truy vấn, thu thập thống kê ở cấp bảng có thể là lựa chọn phù hợp. Nếu một vài cột có thay đổi lớn hoặc được truy vấn thường xuyên, thu thập riêng các cột đó có thể giảm công việc trong một số hệ quản trị.

Tuy nhiên, chỉ cập nhật một cột có thể không giải quyết sai lệch do tương quan giữa các cột. Nếu truy vấn lọc đồng thời theo tenant_id và status, thống kê riêng của hai cột có thể vẫn khiến bộ tối ưu giả định phân bố độc lập. Hãy kiểm tra khả năng thống kê mở rộng hoặc đa cột của hệ quản trị.

### 5.2. Mức lấy mẫu và chất lượng thống kê

Thu thập thống kê có thể đọc toàn bộ dữ liệu hoặc lấy mẫu tùy hệ quản trị và cấu hình. Mẫu lớn hơn có thể cải thiện độ chính xác của histogram và tần suất, nhưng làm tăng I/O và thời gian thu thập.

Nếu dữ liệu có phân bố rất lệch hoặc một số giá trị hiếm nhưng quan trọng, mẫu ngẫu nhiên nhỏ có thể không đại diện. Trước khi tăng mức lấy mẫu, hãy xác định cột và truy vấn chịu ảnh hưởng, sau đó so sánh chất lượng ước lượng và chi phí thu thập.

Không phải lúc nào tăng sample cũng tốt. Bảng lớn, nhiều cột và nhiều phân vùng có thể khiến chi phí thu thập cao. Chọn mức lấy mẫu dựa trên lợi ích đo được và khả năng vận hành.

## 6. Chọn thời điểm cập nhật thống kê

Thời điểm cập nhật quan trọng vì thống kê mới có thể giúp kế hoạch phù hợp hơn, nhưng quá trình thu thập cũng tiêu thụ tài nguyên. Một đợt cập nhật lớn có thể đọc nhiều trang, dùng CPU, tạo tải I/O và làm ảnh hưởng workload đang chạy.

Các thời điểm thường đáng cân nhắc:

- Sau bulk load hoặc import dữ liệu lớn.
- Sau khi xóa hoặc cập nhật một tỷ lệ đáng kể hàng.
- Sau khi tạo hoặc thay đổi cấu trúc chỉ mục nếu hệ quản trị cần thống kê liên quan.
- Sau khi tạo phân vùng mới hoặc nạp dữ liệu vào phân vùng.
- Khi truy vấn quan trọng có sai lệch ước lượng rõ rệt.
- Trong cửa sổ bảo trì hoặc thời điểm tải thấp, nếu việc thu thập có thể ảnh hưởng hệ thống.

Không cần cập nhật thống kê sau mọi câu INSERT hoặc UPDATE. Với workload giao dịch liên tục, hệ quản trị thường có cơ chế tự động theo dõi thay đổi và kích hoạt thu thập khi đạt ngưỡng. Hãy hiểu ngưỡng và hành vi của nền tảng trước khi tạo lịch chạy thủ công trùng lặp.

### 6.1. Tự động cập nhật và ngưỡng thay đổi

Cơ chế tự động có thể dùng số hàng thay đổi, tỷ lệ phần trăm, kích thước bảng, thời gian kể từ lần cập nhật gần nhất hoặc các điều kiện khác để quyết định khi nào cần thu thập thống kê. Một số hệ thống chạy tác vụ nền; một số có thể kích hoạt thu thập khi tối ưu truy vấn hoặc khi truy cập đối tượng.

Ngưỡng không giống nhau giữa các hệ quản trị, phiên bản hoặc cấu hình. Một ngưỡng cố định có thể phù hợp với bảng nhỏ nhưng không phù hợp với bảng rất lớn. Một số hệ quản trị điều chỉnh ngưỡng theo kích thước bảng hoặc cho phép cấu hình riêng từng bảng.

Hãy kiểm tra:

- Thống kê có bật chế độ tự động không?
- Số hàng thay đổi được theo dõi bằng cách nào?
- Ngưỡng áp dụng là cố định hay tỷ lệ theo quy mô?
- Tác vụ tự động chạy đồng bộ hay bất đồng bộ?
- Khi hệ thống quá tải, tác vụ có bị trì hoãn không?
- Có log hoặc metadata cho biết lần cập nhật gần nhất và lý do chạy không?

Tác vụ tự động giúp giảm thao tác thủ công nhưng không thay thế việc quan sát. Sau một đợt thay đổi dữ liệu bất thường, hãy kiểm tra thống kê đã được cập nhật trước khi truy vấn quan trọng chạy với kế hoạch mới.

### 6.2. Tránh cập nhật quá thường xuyên

Cập nhật thống kê sau mỗi thay đổi nhỏ có thể tạo chi phí I/O và CPU không cần thiết. Ngoài ra, thống kê thay đổi liên tục có thể khiến kế hoạch được tối ưu lại, thay đổi hành vi truy vấn hoặc làm phát sinh biến động hiệu năng khó giải thích.

Cần chọn lịch phù hợp với nhịp thay đổi dữ liệu và mức quan trọng của truy vấn. Bảng giao dịch có thể cần cơ chế tự động thường xuyên hơn bảng lịch sử gần như chỉ đọc. Bảng log tăng nhanh có thể cần cập nhật sau mỗi đợt nạp lớn hoặc theo cửa sổ định kỳ.

Đừng đặt lịch ANALYZE quá dày chỉ vì một truy vấn thỉnh thoảng chậm. Trước tiên hãy xác định thống kê có sai lệch hay không và liệu cập nhật có thể cải thiện ước lượng.

## 7. Thống kê trên bảng phân vùng

Với bảng phân vùng (partitioned table), dữ liệu được chia thành nhiều phần theo khóa phân vùng, thường là thời gian, vùng hoặc tenant. Hệ quản trị có thể duy trì thống kê ở cấp từng phân vùng và thống kê tổng hợp ở cấp bảng cha.

Một số tình huống cần chú ý:

- Phân vùng mới được tạo nhưng chưa có thống kê.
- Chỉ một phân vùng gần đây thay đổi mạnh.
- Thống kê từng phân vùng đã cập nhật nhưng thống kê toàn cục vẫn cũ.
- Truy vấn chỉ truy cập một số phân vùng nhờ partition pruning.
- Phân bố giữa các phân vùng khác nhau đáng kể.

Ví dụ, bảng events chia theo tháng. Phân vùng tháng hiện tại có lượng dữ liệu gấp nhiều lần tháng trước vì một chiến dịch mới. Nếu truy vấn chỉ lấy dữ liệu tháng hiện tại, thống kê tổng thể có thể không mô tả đủ chính xác phân bố riêng của phân vùng đó.

Một số hệ quản trị hỗ trợ incremental statistics hoặc cơ chế tổng hợp thống kê từ các phân vùng đã thay đổi. Cách triển khai và giới hạn khác nhau. Hãy xác định thống kê nào được bộ tối ưu sử dụng cho truy vấn phân vùng và cập nhật đúng phạm vi cần thiết.

Không nên giả định chạy lệnh thu thập thống kê ở bảng cha luôn cập nhật tất cả thống kê cục bộ, hoặc cập nhật một phân vùng tự động làm mới thống kê tổng hợp. Kiểm tra tài liệu và metadata của hệ quản trị đang dùng.

## 8. Thống kê đa cột và phân bố lệch

Thống kê riêng từng cột có thể không đủ khi các cột có tương quan. Ví dụ, tenant_id và status có thể liên hệ với nhau: một tenant chuyên bán hàng trả trước có tỷ lệ PAID rất cao, trong khi tenant khác có tỷ lệ PENDING cao.

Nếu bộ tối ưu giả định hai điều kiện độc lập, nó có thể nhân xác suất chọn lọc của từng điều kiện để ước lượng số hàng. Khi hai cột có tương quan, kết quả ước lượng có thể sai đáng kể.

Một số hệ quản trị hỗ trợ extended statistics, multicolumn statistics, column groups hoặc thống kê biểu thức. Chúng giúp mô tả:

- Tương quan giữa các cột.
- Số tổ hợp giá trị khác nhau.
- Phân bố của biểu thức hoặc nhóm cột.
- Các phụ thuộc thống kê mà bộ tối ưu có thể tận dụng.

Ví dụ trong PostgreSQL, có thể khai báo thống kê mở rộng cho nhóm cột:

~~~sql
CREATE STATISTICS orders_tenant_status_stats
    (dependencies, ndistinct, mcv)
ON tenant_id, status
FROM orders;

ANALYZE orders;
~~~

Các loại thống kê và khả năng sử dụng phụ thuộc phiên bản PostgreSQL. Ví dụ này minh họa cách khai báo, không bảo đảm mọi truy vấn sẽ tự động có ước lượng tốt hơn. Hãy xác định truy vấn nào bị sai lệch, loại tương quan nào đang tồn tại và kiểm tra kế hoạch sau khi thu thập thống kê.

## 9. Thống kê chỉ mục và tác động đến lựa chọn đường truy cập

Bộ tối ưu cần ước lượng chi phí của việc truy cập qua chỉ mục so với quét bảng. Ngoài thống kê cột, hệ quản trị có thể lưu thông tin về kích thước chỉ mục, số trang, độ cao, mức độ phân bố và khả năng chọn lọc.

Nếu chỉ mục mới được tạo hoặc dữ liệu thay đổi mạnh, thống kê liên quan đến chỉ mục có thể cần được cập nhật theo cơ chế của hệ quản trị. Một số nền tảng tự cập nhật metadata khi tạo chỉ mục; một số có các tác vụ riêng để thu thập thống kê chỉ mục.

Cần phân biệt:

- **Thống kê cột:** mô tả phân bố giá trị, số giá trị phân biệt và histogram.
- **Thống kê chỉ mục:** mô tả cấu trúc, kích thước hoặc đặc điểm truy cập của chỉ mục.
- **Thống kê bảng:** mô tả số hàng, số trang và các thông tin tổng thể.

Một chỉ mục có thể tồn tại nhưng không được chọn vì truy vấn cần phần lớn hàng, ước lượng chọn lọc thấp hoặc chi phí truy cập ngẫu nhiên cao. Nếu ước lượng sai, cập nhật thống kê có thể thay đổi quyết định của bộ tối ưu. Nhưng không nên tạo chỉ mục mới chỉ để bù cho thống kê cũ mà chưa kiểm tra nguyên nhân.

## 10. Cập nhật thống kê có thể làm kế hoạch thay đổi

Sau khi thống kê được cập nhật, bộ tối ưu có thể chọn kế hoạch khác. Đây thường là kết quả mong muốn nếu kế hoạch cũ dựa trên ước lượng sai. Tuy nhiên, kế hoạch mới không phải lúc nào cũng nhanh hơn trong mọi trường hợp.

Một số nguyên nhân gây biến động:

- Thống kê mới phản ánh phân bố dữ liệu khác trước.
- Thứ tự nối hoặc thuật toán nối thay đổi.
- Quét chỉ mục chuyển thành quét tuần tự hoặc ngược lại.
- Tham số truy vấn được tối ưu theo cách khác.
- Kế hoạch được biên dịch lại hoặc cache kế hoạch bị thay thế.
- Thống kê lấy mẫu khác nhau tạo ra sai số ước lượng khác nhau.

Vì vậy, cần ghi lại kế hoạch trước và sau khi cập nhật, cùng tham số đại diện và điều kiện tải. Đừng kết luận chỉ dựa vào việc tên toán tử thay đổi hoặc cost giảm. Hãy đo elapsed time, CPU, I/O, số hàng đọc, số hàng trả về và wait events.

Một số hệ quản trị có cơ chế plan cache, plan baseline, query store hoặc khả năng ép kế hoạch. Nếu kế hoạch mới gây hồi quy, cần xem xét khả năng khôi phục kế hoạch trước hoặc giới hạn thay đổi theo công cụ chính thức. Không nên xóa cache kế hoạch hàng loạt hoặc ép một kế hoạch cố định khi chưa hiểu ảnh hưởng đến các giá trị tham số khác.

## 11. Quy trình cập nhật thống kê sau thay đổi dữ liệu lớn

Một quy trình vận hành có kiểm soát có thể gồm:

1. **Ghi nhận thay đổi:** bảng nào được nạp, xóa hoặc cập nhật; số hàng thay đổi và các cột bị ảnh hưởng.
2. **Xác định workload quan trọng:** truy vấn nào dùng bảng/cột đó và khi nào chúng cần chạy.
3. **Kiểm tra trạng thái thống kê:** thời điểm cập nhật, số hàng thay đổi kể từ lần gần nhất, phạm vi bảng/cột/phân vùng và tác vụ tự động.
4. **Đo trước khi cập nhật nếu có thể:** lưu kế hoạch, ước lượng, số hàng thực tế và hiệu năng của truy vấn đại diện.
5. **Chọn phạm vi thu thập:** bảng, cột, nhóm cột, chỉ mục hoặc phân vùng cần cập nhật.
6. **Chọn thời điểm:** cân nhắc tải I/O/CPU, lịch ETL, batch job và thời điểm truy vấn quan trọng bắt đầu.
7. **Thu thập thống kê:** dùng cơ chế được hệ quản trị hỗ trợ, theo dõi thời gian và tài nguyên tiêu thụ.
8. **Kiểm tra trạng thái sau cập nhật:** xác nhận metadata được làm mới và không có lỗi hoặc tác vụ bị trì hoãn.
9. **So sánh kế hoạch:** dùng cùng nhóm tham số, cùng dữ liệu và cùng điều kiện đo.
10. **Đo lại workload:** theo dõi p50/p95/p99, thông lượng, CPU, I/O, lock wait, spill và lỗi.
11. **Theo dõi hồi quy:** kiểm tra các truy vấn khác dùng cùng bảng hoặc chỉ mục.
12. **Ghi lại kết quả:** lưu thời điểm, phạm vi, cấu hình, kế hoạch và kết luận để lần sau có cơ sở so sánh.

Nếu hệ thống hỗ trợ cập nhật thống kê bất đồng bộ, cần hiểu khi nào thống kê mới trở nên có hiệu lực và truy vấn nào vẫn có thể dùng kế hoạch cũ. Đừng coi lệnh thu thập hoàn tất là bằng chứng duy nhất rằng mọi phiên đã dùng kế hoạch mới.

## 12. Ví dụ: bảng orders sau đợt import lớn

Giả sử bảng orders có 10 triệu hàng và được tối ưu cho truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE status = 'PENDING'
  AND created_at >= :from_time
ORDER BY created_at DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Ban đầu, PENDING chiếm 40% số hàng. Sau một đợt import lịch sử, bảng tăng lên 60 triệu hàng, nhưng chỉ 2% số hàng mới có status là PENDING. Phần lớn hàng mới có trạng thái PAID.

Nếu thống kê chưa phản ánh dữ liệu import, bộ tối ưu có thể ước lượng tỷ lệ PENDING không chính xác. Tùy kế hoạch và phân bố, nó có thể chọn quét quá nhiều dữ liệu hoặc chọn một đường truy cập chỉ mục không phù hợp.

Cách điều tra:

**Trước tiên**, ghi nhận số hàng thực tế theo status và thời gian, kiểm tra thời điểm import và thời điểm thu thập thống kê gần nhất. Không chỉ nhìn tổng số hàng; cần xem phân bố trên cột mà truy vấn sử dụng.

**Tiếp theo**, thu thập kế hoạch trước cập nhật nếu có thể, so sánh estimated rows với actual rows. Nếu số hàng thực tế lệch lớn ở bước lọc, hãy kiểm tra histogram và chất lượng thống kê cột status, created_at.

**Sau đó**, cập nhật thống kê trong cửa sổ phù hợp hoặc dùng cơ chế thu thập được hệ quản trị khuyến nghị. Nếu bảng lớn và việc thu thập toàn bộ gây tải đáng kể, đánh giá mức lấy mẫu và phạm vi cột cần thiết.

**Cuối cùng**, chạy lại truy vấn với nhiều mốc thời gian và giá trị tham số đại diện. So sánh kế hoạch, số hàng đọc, I/O, p95 và tác động lên các truy vấn khác. Nếu kế hoạch tốt hơn cho dữ liệu mới nhưng kém với truy vấn lịch sử, hãy xem xét phân bố, phân vùng, thống kê mở rộng hoặc tính nhạy cảm theo tham số.

Ví dụ này cho thấy một đợt import có thể thay đổi cả quy mô lẫn phân bố dữ liệu. Chỉ cập nhật tổng số hàng có thể chưa đủ nếu histogram hoặc tương quan cột vẫn không đại diện.

## 13. Những lưu ý vận hành khi thu thập thống kê

**Tác động tài nguyên.** Thu thập thống kê cần đọc dữ liệu và tiêu thụ CPU/I/O. Với bảng lớn, nhiều cột hoặc nhiều phân vùng, thời gian chạy có thể đáng kể. Theo dõi tác động và chọn cửa sổ phù hợp.

**Đồng thời với DML.** Hệ quản trị có quy tắc riêng về snapshot, khóa và khả năng chạy đồng thời với INSERT/UPDATE/DELETE. Không giả định thao tác thu thập luôn không chặn hoặc không bị ảnh hưởng bởi thay đổi dữ liệu đang diễn ra.

**Quyền và phạm vi.** Một số lệnh cần quyền quản trị hoặc quyền trên đối tượng. Cần xác định đúng schema, bảng và phân vùng; tránh thu thập nhầm phạm vi rộng gây tải không cần thiết.

**Thống kê bị khóa hoặc không tự cập nhật.** Một số nền tảng cho phép khóa thống kê hoặc cấu hình không thu thập tự động. Nếu có cơ chế này, hãy biết lý do và quy trình mở khóa/cập nhật. Không ép cập nhật nếu hệ thống đang cố ý giữ thống kê ổn định mà chưa đánh giá mục đích.

**Lưu giữ và phục hồi kế hoạch.** Nếu cập nhật thống kê làm phát sinh hồi quy, cần có khả năng xem lại kế hoạch trước, phiên bản cấu hình và metadata liên quan. Không phải hệ quản trị nào cũng lưu lịch sử thống kê đầy đủ, nên quy trình quan sát cần ghi nhận những dữ liệu quan trọng trước khi thay đổi.

**Không nhầm ANALYZE với kiểm tra dữ liệu.** ANALYZE thường thu thập thông tin thống kê, không chứng minh dữ liệu không có lỗi nghiệp vụ hoặc vi phạm ràng buộc. Kiểm tra tính đúng đắn của dữ liệu là một công việc riêng.

## 14. Những sai lầm thường gặp

- **Cập nhật theo lịch nhưng không xem dữ liệu đã thay đổi chưa.** Lịch cố định có thể chạy quá thường xuyên trên bảng ổn định hoặc quá muộn sau bulk load.
- **Chỉ dựa vào thời điểm cập nhật gần nhất.** Thống kê mới vẫn có thể không đại diện cho phân bố hiện tại.
- **Chạy ANALYZE sau mọi giao dịch.** Việc này có thể tạo chi phí lớn và không cần thiết.
- **Cho rằng auto statistics luôn cập nhật ngay.** Tác vụ nền có thể bị trì hoãn hoặc chưa đạt ngưỡng kích hoạt.
- **Chỉ cập nhật thống kê bảng mà bỏ qua cột quan trọng.** Sai lệch có thể nằm ở histogram hoặc tương quan cột.
- **Tăng sample size mà không đo.** Mẫu lớn hơn tốn tài nguyên và không phải lúc nào cũng cải thiện quyết định của bộ tối ưu.
- **Coi cost giảm là hiệu năng đã tốt hơn.** Cần đo thời gian thực, I/O, CPU và phân vị trên workload đại diện.
- **Cập nhật thống kê rồi chỉ thử một tham số.** Kế hoạch có thể tốt với một giá trị nhưng xấu với giá trị khác.
- **Bỏ qua thống kê phân vùng.** Dữ liệu mới có thể tập trung trong một phân vùng và không được mô tả bởi thống kê tổng hợp.
- **Dùng hint để che sai lệch thống kê.** Hint có thể che nguyên nhân gốc và gây hồi quy khi dữ liệu thay đổi tiếp.

## 15. Checklist quyết định thời điểm cập nhật

- [ ] Đã xác định bảng, cột, chỉ mục hoặc phân vùng bị ảnh hưởng.
- [ ] Đã ghi nhận số hàng thêm, xóa hoặc cập nhật kể từ lần thu thập gần nhất.
- [ ] Đã xem thay đổi có làm biến đổi phân bố hoặc tương quan dữ liệu không.
- [ ] Đã xác định truy vấn quan trọng dùng các cột đó.
- [ ] Đã so sánh estimated rows với actual rows nếu có số liệu thực tế.
- [ ] Đã kiểm tra cơ chế auto statistics, ngưỡng kích hoạt và trạng thái job.
- [ ] Đã chọn phạm vi và mức lấy mẫu dựa trên bằng chứng.
- [ ] Đã chọn thời điểm phù hợp với tải CPU/I/O và workload.
- [ ] Đã hiểu tác động đồng thời, quyền và phạm vi của lệnh thu thập.
- [ ] Đã lưu kế hoạch và số liệu trước cập nhật.
- [ ] Đã kiểm tra kế hoạch sau cập nhật với nhiều tham số đại diện.
- [ ] Đã đo lại độ trễ, thông lượng, CPU, I/O, wait và spill.
- [ ] Đã kiểm tra truy vấn liên quan để phát hiện hồi quy.
- [ ] Đã ghi lại thời điểm, phạm vi và kết quả cập nhật.

## 16. Nguyên tắc cần ghi nhớ

Thống kê là đầu vào quan trọng của bộ tối ưu, nhưng giá trị của nó phụ thuộc vào việc có phản ánh đúng quy mô và phân bố dữ liệu hiện tại hay không. Những đợt bulk load, xóa/cập nhật hàng loạt, thay đổi phân bố theo thời gian, tenant hoặc phân vùng có thể khiến thống kê cũ dẫn đến ước lượng sai và kế hoạch kém hiệu quả.

Không cập nhật chỉ vì thống kê đã cũ theo lịch, cũng không chờ đến khi mọi truy vấn chậm mới hành động. Hãy theo dõi thay đổi dữ liệu, kiểm tra sai lệch ước lượng, hiểu ngưỡng tự động và chọn đúng phạm vi, thời điểm thu thập. Sau khi cập nhật, luôn so sánh kế hoạch và số liệu thực tế trên workload đại diện để xác nhận lợi ích và phát hiện hồi quy.
