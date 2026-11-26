Câu 01. Khi đánh giá độ trễ truy vấn ở môi trường thật, p95 biểu thị điều gì?
A. Khoảng 95% lượt đo có độ trễ lớn hơn giá trị p95.
B. Độ trễ trung bình cộng của 95 truy vấn chậm nhất.
C. Giá trị độ trễ cao nhất trong 95 lượt đo gần nhất.
D. 95% lượt đo có độ trễ không vượt quá ngưỡng p95.
Đáp án đúng: D

Câu 02. Một dịch vụ có throughput ổn định nhưng p99 latency tăng mạnh. Nên kết luận gì trước?
A. Thời gian thực thi trung bình chắc chắn tăng bằng p99.
B. Mọi truy vấn cơ sở dữ liệu đều chậm đúng cùng tỷ lệ.
C. Một phần nhỏ yêu cầu ở đuôi phân phối đang chịu độ trễ tăng cao.
D. Tổng số truy vấn mỗi giây đang tăng theo p99 latency.
Đáp án đúng: C

Câu 03. Để so sánh hiệu năng SQL trước và sau tối ưu, cần giữ điều kiện nào?
A. Đo với số phiên khác nhau để tối ưu luôn trông rõ rệt.
B. Giữ tải, dữ liệu và điều kiện tài nguyên tương đương.
C. Đo sau khi đổi cả schema và cấu hình máy chủ cùng lúc.
D. Đo lượt trước khi cache ấm và lượt sau khi cache đã ấm.
Đáp án đúng: B

Câu 04. Vì sao chỉ dùng thời gian trung bình có thể bỏ sót sự cố hiệu năng?
A. Một số lượt thực thi rất chậm có thể bị nhiều lượt nhanh che khuất.
B. Mọi truy vấn được đưa vào trung bình đều có cùng thời lượng.
C. Trung bình luôn bằng với truy vấn chậm nhất của khoảng đo.
D. Giá trị trung bình chỉ dùng được cho truy vấn không có index.
Đáp án đúng: A

Câu 05. Khi làm benchmark đọc dữ liệu, vì sao cần xét trạng thái cache?
A. Cache ấm khiến mọi câu truy vấn luôn có độ trễ bằng nhau.
B. Cache ấm làm thay đổi khóa chính của dữ liệu trong bảng.
C. Cache ấm và cache lạnh có thể cho độ trễ rất khác nhau.
D. Cache lạnh buộc bộ tối ưu không sử dụng chỉ mục hiện hữu.
Đáp án đúng: C

Câu 06. Một phép thử chịu tải chỉ dùng truy vấn đơn giản có hạn chế gì?
A. Luôn kích hoạt tranh chấp khóa mạnh hơn mọi workload khác.
B. Tự đảm bảo ngẫu nhiên hóa dữ liệu đọc ở mức ứng dụng.
C. Không thể ghi nhận băng thông mạng dù có client tạo tải.
D. Khó phản ánh tỷ lệ đọc, ghi và độ phức tạp SQL thực tế.
Đáp án đúng: D

Câu 07. Trong kiểm thử tăng tải, dấu hiệu bão hòa tài nguyên thường là gì?
A. Throughput tăng tuyến tính không giới hạn theo số client.
B. Độ trễ và hàng đợi tăng nhanh dù throughput gần như đứng.
C. Độ trễ giữ nguyên khi lượng request vượt khả năng xử lý.
D. Máy chủ giảm số phiên kết nối trong khi hàng đợi luôn rỗng.
Đáp án đúng: B

Câu 08. Vì sao cần theo dõi thời gian chờ cùng với CPU khi chẩn đoán chậm?
A. I/O cao luôn có nghĩa câu truy vấn không bị chờ khóa.
B. Mọi truy vấn chậm luôn tiêu tốn CPU bằng thời gian chờ.
C. Truy vấn có thể chờ khóa hoặc chờ I/O ngay cả khi CPU còn dư tải.
D. CPU thấp chứng tỏ câu SQL đã chọn index tối ưu nhất.
Đáp án đúng: C

Câu 09. Execution plan của câu SQL chủ yếu giúp hiểu điều gì?
A. Địa chỉ từng máy khách đang kết nối với cơ sở dữ liệu.
B. Thứ tự và cách DB truy cập, JOIN rồi xử lý dữ liệu.
C. Các thông báo lỗi mạng xuất hiện trước lúc SQL thực thi.
D. Lịch sử mọi thay đổi schema trên toàn bộ database.
Đáp án đúng: B

Câu 10. Nếu estimated rows khác actual rows rất lớn, nên điều tra gì?
A. Chỉ tham số timeout của socket giữa ứng dụng và database.
B. Chỉ lịch chạy backup và tuổi của file log giao dịch.
C. Kiểm tra thống kê và phân bố dữ liệu dùng để ước lượng số hàng.
D. Chỉ số lượng người dùng đang mở dashboard của hệ thống.
Đáp án đúng: C

Câu 11. Khi bảng có phân bố giá trị lệch mạnh, histogram hỗ trợ điều gì?
A. Giảm kích thước dữ liệu của mỗi hàng bằng phép nén từ điển.
B. Cho biết tần suất không đồng đều giữa các giá trị của một cột.
C. Buộc optimizer quét toàn bộ bảng khi gặp điều kiện bằng nhau.
D. Thay mọi index bằng một bảng lưu danh sách SQL đã chạy.
Đáp án đúng: B

Câu 12. Nếu thống kê bảng lỗi thời sau nạp dữ liệu lớn, việc nào hợp lý?
A. Đổi tất cả cột số thành chuỗi để thống kê dễ lưu.
B. Thu thập lại thống kê để optimizer ước lượng số hàng tốt hơn.
C. Tắt thu thập thống kê để tránh thay đổi kế hoạch SQL.
D. Tăng timeout của client để kế hoạch cũ chạy lâu hơn.
Đáp án đúng: B

Câu 13. Chỉ số rows examined lớn hơn rows returned rất nhiều gợi ý điều gì?
A. Mọi hàng kiểm tra đều được trả về đủ hai lần cho client.
B. Truy vấn chắc chắn đã dùng index bao phủ tất cả cột.
C. Đã kiểm tra nhiều hàng ở DB nhưng chỉ trả về một phần nhỏ.
D. Giá trị trả về chắc chắn có đầy đủ trong cache bộ nhớ.
Đáp án đúng: C

Câu 14. Trong plan, full table scan không nhất thiết là lỗi vì sao?
A. Quét bảng luôn bỏ qua mọi dữ liệu đã có trong bộ nhớ đệm.
B. Quét bảng luôn nhanh nhất với điều kiện khóa có độ chọn lọc cao.
C. Index luôn được sử dụng khi truy vấn cần ít hơn một hàng.
D. Quét bảng có thể rẻ hơn index khi phải lấy nhiều hàng.
Đáp án đúng: D

Câu 15. B-tree index thường hữu ích nhất với loại điều kiện nào?
A. Thay đổi liên tục hầu hết hàng trong một bảng rất nhỏ.
B. Lọc theo biểu thức không liên quan tới các cột của index.
C. Lọc giá trị chọn lọc hoặc quét một khoảng có thứ tự.
D. Đọc gần như mọi hàng của bảng cho báo cáo tổng hợp.
Đáp án đúng: C

Câu 16. Với index ghép (tenant_id, created_at), truy vấn nào phù hợp hơn?
A. Chỉ lọc created_at mà không cung cấp giá trị tenant_id.
B. Chỉ lọc status không nằm trong hai cột của chỉ mục.
C. Chỉ lọc order_total không nằm trong hai cột của chỉ mục.
D. Lọc tenant_id trước rồi giới hạn khoảng created_at cần tìm.
Đáp án đúng: D

Câu 17. Điểm mạnh của covering index trong một truy vấn là gì?
A. Ngăn các transaction đồng thời cập nhật hàng khác.
B. Buộc trình tối ưu bỏ qua các điều kiện lọc còn lại.
C. Giữ mọi bảng nằm hoàn toàn trong bộ nhớ suốt phiên.
D. Có thể lấy cột cần đọc trực tiếp từ index.
Đáp án đúng: D

Câu 18. Vì sao tạo thêm quá nhiều index có thể làm ghi dữ liệu chậm?
A. Mọi câu INSERT sẽ tự chuyển thành truy vấn toàn bảng.
B. Index buộc toàn bộ DB chạy dưới mức cô lập SERIALIZABLE.
C. Các index liên quan phải được duy trì khi bản ghi thay đổi.
D. Mọi index mới yêu cầu tạo thêm một phiên giao dịch từ client.
Đáp án đúng: C

Câu 19. Với cột có rất ít giá trị khác nhau, điều gì cần xét trước khi tạo index?
A. Độ chọn lọc thực tế và tỉ lệ hàng mà truy vấn phải đọc.
B. Chỉ độ dài tên cột và thời điểm tạo khóa chính của bảng.
C. Chỉ số lượng connection trong pool phía ứng dụng web.
D. Chỉ tốc độ gửi log từ ứng dụng tới nơi tập trung log.
Đáp án đúng: A

Câu 20. Viết WHERE DATE(created_at)=:d có thể gây bất lợi gì cho index thường trên created_at?
A. Điều kiện luôn trả mọi hàng bất kể giá trị tham số ngày.
B. Hàm bọc cột có thể hạn chế việc dùng index cho tìm khoảng.
C. Trình tối ưu bắt buộc dùng phép nối hash ở mọi câu truy vấn.
D. Cột created_at tự động mất mọi giá trị timestamp đã lưu.
Đáp án đúng: B

Câu 21. Với index B-tree thông thường, LIKE '%abc' thường khó tối ưu bằng gì?
A. Phép tìm kiếm theo tiền tố đầu chuỗi của index B-tree.
B. Phép nối với bảng nhỏ có index trên khóa ngoại.
C. Phép đọc dữ liệu có điều kiện thời gian gần nhất.
D. Phép lọc bằng giá trị khóa chính kiểu số nguyên.
Đáp án đúng: A

Câu 22. Vì sao không nên SELECT * trong API chỉ cần vài cột?
A. Truy vấn nhiều cột luôn khiến khóa chính bị thay đổi.
B. Đọc các cột thừa làm tăng truyền dữ liệu và xử lý.
C. SELECT * tự động vô hiệu hóa mọi ràng buộc trên bảng.
D. SELECT * bắt buộc tạo transaction ghi cho mỗi request.
Đáp án đúng: B

Câu 23. Mẫu N+1 query thường làm chậm ứng dụng theo cách nào?
A. Tự xóa các index sau khi chạy hết các câu SQL có JOIN.
B. Chỉ đọc dữ liệu của N hàng cuối bảng và bỏ hàng đầu.
C. Luôn dùng đúng một truy vấn duy nhất để tải mọi quan hệ.
D. Phát sinh nhiều truy vấn nhỏ để lấy quan hệ liên quan.
Đáp án đúng: D

Câu 24. Khi lọc điều kiện trước GROUP BY, cách viết nào thường tốt hơn?
A. Đặt điều kiện trên hàng nguồn trong WHERE khi tương đương.
B. Chỉ đặt các điều kiện lọc trong HAVING dù chưa tổng hợp.
C. Đưa điều kiện lọc vào tên bảng để DB tự chọn đúng dữ liệu.
D. Đặt toàn bộ điều kiện hàng nguồn vào ORDER BY sau GROUP BY.
Đáp án đúng: A

Câu 25. Vì sao OFFSET rất lớn có thể làm phân trang SQL chậm?
A. DB luôn phải xoá các hàng bị bỏ qua khỏi bảng nguồn.
B. OFFSET làm mất khóa chính của các hàng được phân trang.
C. OFFSET luôn chuyển phép lọc sang giao dịch ghi dữ liệu.
D. DB phải xử lý nhiều hàng bị bỏ qua trước trang cần lấy.
Đáp án đúng: D

Câu 26. Khi dữ liệu có thứ tự ổn định, keyset pagination thường giúp gì?
A. Gộp tất cả trang dữ liệu thành một transaction kéo dài.
B. Tính tổng số trang bằng cách đọc toàn bộ bảng sau mỗi yêu cầu.
C. Dùng khóa trang trước để tránh bỏ qua nhiều hàng.
D. Buộc mọi truy vấn phân trang dùng OFFSET ngày càng lớn hơn.
Đáp án đúng: C

Câu 27. Index trên (status, created_at) có thể hỗ trợ ORDER BY khi nào?
A. Khi lọc và sắp xếp theo thứ tự các khóa trong index.
B. Khi mọi hàng trong bảng được cập nhật cùng một lúc.
C. Khi status có thể nhận giá trị khác nhau trên từng shard.
D. Khi ORDER BY dùng cột không xuất hiện trong chỉ mục nào.
Đáp án đúng: A

Câu 28. Với tham số truy vấn có phân bố dữ liệu rất lệch, vì sao một plan có thể kém cho một số giá trị?
A. Optimizer luôn tạo một plan mới cho mỗi lần đọc một hàng.
B. Plan tốt cho giá trị này có thể kém với giá trị khác.
C. Giá trị tham số khác nhau tự thay đổi số cột của bảng.
D. Plan đã biên dịch luôn chọn full scan với mọi điều kiện.
Đáp án đúng: B

Câu 29. Partition pruning giúp truy vấn cải thiện hiệu năng theo cách nào?
A. Bỏ qua phân vùng không thỏa điều kiện partition key.
B. Thay phân vùng không khớp bằng các hàng chứa NULL.
C. Quét mọi phân vùng song song bất kể điều kiện truy vấn.
D. Chuyển mọi partition sang một bảng chung trước khi lọc.
Đáp án đúng: A

Câu 30. Nếu truy vấn join hai bảng lớn bị chậm, bước điều tra đầu tiên là gì?
A. Luôn thay INNER JOIN thành CROSS JOIN để tăng song song.
B. Luôn tăng số connection trong pool trước khi đọc execution plan.
C. Luôn thêm index trên mọi cột của cả hai bảng ngay lập tức.
D. Xem số hàng ước lượng, điều kiện join và thuật toán join.
Đáp án đúng: D

Câu 31. Metric lock wait tăng cùng thời gian giao dịch, nguyên nhân đáng kiểm tra là gì?
A. Transaction giữ khóa lâu khiến truy vấn khác phải chờ.
B. Cache ứng dụng đang chứa nhiều dữ liệu tĩnh không hết hạn.
C. Bộ tối ưu luôn chọn index có kích thước nhỏ nhất.
D. Hệ thống sao lưu đang tự đổi kiểu dữ liệu của bảng.
Đáp án đúng: A

Câu 32. Cách nào thường làm giảm thời gian giữ khóa trong giao dịch OLTP?
A. Giữ transaction ngắn, tránh I/O mạng ngoài khi đang giữ khóa.
B. Tăng số bảng bị khóa khi thực hiện cùng một thao tác ghi.
C. Mở transaction trước mọi phép gọi dịch vụ ngoài để dễ rollback.
D. Giữ kết nối và transaction mở trong suốt phiên người dùng.
Đáp án đúng: A

Câu 33. Khi hai giao dịch chờ khóa của nhau theo vòng, hiện tượng nào xảy ra?
A. Cache miss và tất cả query plan bị DB xóa khỏi bộ nhớ.
B. Index scan và bộ tối ưu phải chạy lại thống kê toàn bảng.
C. Dirty read và mọi hàng đều tự động bị rollback ngay.
D. Deadlock và cần xử lý lỗi, có thể thử lại có kiểm soát.
Đáp án đúng: D

Câu 34. Khi mức cô lập giao dịch được tăng, đánh đổi hiệu năng có thể là gì?
A. Loại bỏ hoàn toàn mọi chờ khóa ở tất cả hệ quản trị.
B. Bắt mọi thao tác ghi hoàn tất mà không cần kiểm tra xung đột.
C. Giảm một số bất thường đọc nhưng tăng tranh chấp hoặc chờ.
D. Luôn giảm độ trễ dù các giao dịch chạy đồng thời rất nhiều.
Đáp án đúng: C

Câu 35. Pool kết nối có active đạt max, idle bằng 0 và nhiều pending. Dấu hiệu gì?
A. Tất cả transaction đã commit và không còn dùng connection.
B. Pool đang bão hòa và có request chờ được cấp kết nối.
C. Pool có quá nhiều kết nối rảnh cần được thu hồi ngay.
D. Database đã trả mọi kết quả truy vấn cho ứng dụng.
Đáp án đúng: B

Câu 36. Vì sao tăng kích thước connection pool có thể làm DB chậm hơn?
A. Pool lớn sẽ tự tắt cache ở mọi cơ sở dữ liệu quan hệ.
B. Pool lớn buộc database sử dụng một isolation level chung.
C. Nhiều kết nối luôn làm mất mọi index hiện có trên bảng.
D. Nhiều truy vấn song song khiến DB tranh chấp nhiều hơn.
Đáp án đúng: D

Câu 37. Khi đo thấy thời gian đọc đĩa cao và I/O queue tăng, cần kiểm tra gì?
A. Chỉ số lượng token xác thực của API quản trị database.
B. Kiểm tra lượt đọc, kiểu truy cập và mức bão hòa I/O.
C. Chỉ kiểu chữ và độ dài nhãn hiển thị trên dashboard.
D. Chỉ thời gian hết hạn của cookie đăng nhập ứng dụng.
Đáp án đúng: B

Câu 38. Khi phép sort hoặc hash join phải spill ra đĩa, điều này cho biết gì?
A. Database chỉ truy vấn được dữ liệu khi không có buffer cache.
B. Truy vấn đã tìm được tất cả hàng từ index mà không cần đĩa.
C. Bộ nhớ làm việc không đủ cho thao tác nên phát sinh I/O phụ.
D. Datafile đã được nén nên transaction tự động dừng lại.
Đáp án đúng: C

Câu 39. Khi chọn tăng buffer cache, điều kiện nào cho thấy có thể hữu ích?
A. Tập dữ liệu nóng được đọc lại và hiện có nhiều lần đọc đĩa.
B. Chỉ có một truy vấn chạy một lần và dữ liệu không được tái dùng.
C. Bộ nhớ máy chủ đã thiếu và đang swap vì cache chiếm quá nhiều.
D. Ứng dụng chậm do khóa dù dữ liệu đang nằm hoàn toàn trong RAM.
Đáp án đúng: A

Câu 40. Sau khi tối ưu SQL, cách xác nhận hiệu quả đáng tin cậy nhất là gì?
A. So sánh p95, tài nguyên và tính đúng dưới tải tương đương.
B. Chỉ nhìn một lượt truy vấn nhanh nhất trên máy dev cá nhân.
C. Chỉ dựa vào số index mới được tạo mà không đo tải thật.
D. Chỉ so sánh số dòng mã SQL ít đi sau khi được viết lại.
Đáp án đúng: A
