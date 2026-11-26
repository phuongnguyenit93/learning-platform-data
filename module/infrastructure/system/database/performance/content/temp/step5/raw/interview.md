Bạn xác định hiệu năng cơ sở dữ liệu tốt hay kém dựa trên những yêu cầu nghiệp vụ và chỉ số kỹ thuật nào?
Độ trễ trung bình, p95, p99 và thông lượng phản ánh những khía cạnh khác nhau nào của tải cơ sở dữ liệu?
Bạn xây dựng SLO cho truy vấn đọc, truy vấn ghi và transaction dựa trên trải nghiệm người dùng như thế nào?
Bạn thu thập những thông tin nào về tỷ lệ đọc/ghi, mức đồng thời, kích thước dữ liệu và mẫu truy cập trước khi tối ưu?
Bạn thiết lập baseline hiệu năng có thể so sánh lại giữa các lần thay đổi bằng cách nào?
Bạn phân biệt độ trễ từ ứng dụng, connection pool, mạng và máy chủ cơ sở dữ liệu trong một yêu cầu chậm ra sao?
Bạn kết hợp tracing, metric và log như thế nào để tìm bước gây chậm trong một luồng xử lý dữ liệu?
Vì sao một hệ thống có thông lượng cao vẫn có thể gặp vấn đề nghiêm trọng về độ trễ đuôi?
Bạn nhận diện thay đổi về lưu lượng, phân bố khóa và tỷ lệ truy vấn có thể khiến benchmark khác production như thế nào?
Bạn thiết kế dữ liệu thử nghiệm đại diện cho số bản ghi, kích thước hàng và độ lệch phân bố của production ra sao?
Bạn kiểm soát ảnh hưởng của cache lạnh, cache nóng và giai đoạn warm-up khi đo hiệu năng như thế nào?
Bạn lựa chọn thời lượng, số lần chạy và tiêu chí ổn định của một phép thử tải như thế nào?
Khi tăng số người dùng đồng thời, bạn xác định tài nguyên nào chạm ngưỡng bão hòa đầu tiên bằng cách nào?
Khi tổng CPU còn thấp nhưng p99 tăng mạnh, bạn sẽ kiểm tra những loại hàng đợi hoặc nút thắt nào?
Bạn dùng các chỉ số thời gian CPU, chờ I/O, chờ khóa và chờ kết nối để phân rã thời gian truy vấn ra sao?
Bạn xác định các truy vấn có tổng chi phí lớn nhất dựa trên tần suất chạy và độ trễ mỗi lần như thế nào?
Bạn lựa chọn truy vấn cần tối ưu trước khi có nhiều truy vấn chậm với tần suất và tác động khác nhau ra sao?
Bạn dùng slow query log hoặc công cụ thống kê truy vấn để thu thập bằng chứng hiệu năng như thế nào?
Bạn bảo đảm việc bật logging và profiling không làm sai lệch đáng kể kết quả đo đạc ra sao?
Bạn đọc execution plan để tìm các bước scan, join, filter, sort và aggregate tốn tài nguyên như thế nào?
Bạn phân biệt chi phí ước lượng trong execution plan với thời gian thực tế đo được như thế nào?
Số dòng ước lượng chênh lệch lớn với số dòng thực tế có thể dẫn đến lựa chọn kế hoạch truy vấn kém ra sao?
Bạn đọc số lần lặp của một operator để phát hiện chi phí bị khuếch đại trong nested loop như thế nào?
Trong những điều kiện dữ liệu và truy vấn nào full table scan có thể hiệu quả hơn index scan?
Bạn so sánh nested loop, hash join và merge join theo kích thước tập dữ liệu, bộ nhớ và cách truy cập như thế nào?
Khi thứ tự join gây ra tập kết quả trung gian lớn, bạn kiểm tra và chỉnh lại truy vấn theo hướng nào?
Bạn phát hiện phép sort hoặc hash phải ghi dữ liệu tạm ra đĩa từ execution plan và metric như thế nào?
Bạn xác định một điều kiện lọc có tính chọn lọc cao hay thấp và tác động của nó đến truy vấn ra sao?
Bạn quyết định tạo B-tree index cho những điều kiện lọc và sắp xếp nào dựa trên tần suất và độ chọn lọc?
Thứ tự cột trong composite index ảnh hưởng như thế nào đến các truy vấn kết hợp equality, range và ORDER BY?
Bạn chọn covering index hoặc included column khi muốn giảm số lần truy cập bảng gốc theo tiêu chí nào?
Bạn sử dụng partial index để tối ưu tập dữ liệu thường được lọc mà không tăng quá nhiều chi phí ghi như thế nào?
Bạn cân nhắc expression index khi điều kiện lọc dùng phép biến đổi giá trị cột như thế nào?
Bạn phân biệt trường hợp cần index phục vụ tra cứu chính xác, tìm kiếm văn bản hoặc dữ liệu theo thời gian như thế nào?
Bạn kiểm tra xem optimizer có thực sự sử dụng index vừa thêm hay không bằng những bằng chứng nào?
Bạn đánh giá chi phí cập nhật index, dung lượng lưu trữ và write amplification trước khi thêm index ra sao?
Bạn sử dụng những chỉ số và kiểm tra nào để xác định index trùng lặp hoặc ít được dùng trước khi loại bỏ?
Thống kê phân bố dữ liệu và cardinality giúp optimizer chọn access path như thế nào?
Bạn phát hiện thống kê cũ hoặc không phản ánh dữ liệu lệch phân bố từ các dấu hiệu nào?
Bạn đánh giá hiệu quả của cập nhật thống kê hoặc thống kê nhiều cột khi planner ước lượng sai ra sao?
Vì sao cùng một câu SQL có thể có kế hoạch khác nhau khi tham số đầu vào thay đổi?
Bạn điều tra plan regression sau khi triển khai phiên bản mới hoặc dữ liệu tăng mạnh như thế nào?
Bạn biến điều kiện lọc có hàm bao quanh cột hoặc phép ép kiểu thành điều kiện tận dụng index bằng cách nào?
Bạn tối ưu truy vấn chỉ cần một vài cột nhưng đang đọc quá nhiều dữ liệu như thế nào?
Bạn xử lý tình huống ORM tạo nhiều truy vấn N+1 khi tải danh sách và các bản ghi liên quan ra sao?
Bạn lựa chọn JOIN, EXISTS hoặc subquery để diễn đạt cùng một nghiệp vụ dựa trên ngữ nghĩa và kế hoạch thực thi như thế nào?
Bạn dùng aggregation và lọc sớm để giảm số dòng truyền qua các bước truy vấn ra sao?
Bạn cải thiện truy vấn phân trang sâu bằng cách so sánh OFFSET/LIMIT với keyset pagination như thế nào?
Bạn cân nhắc dùng batch insert, batch update hoặc bulk load để giảm chi phí round trip khi ghi nhiều bản ghi ra sao?
Bạn đánh giá khi nào CTE, view hoặc materialized view giúp đơn giản hóa hoặc tăng tốc truy vấn dựa trên những tiêu chí nào?
Bạn đánh giá đánh đổi giữa dữ liệu chuẩn hóa, phi chuẩn hóa và bảng tổng hợp trước khi thay đổi thiết kế như thế nào?
Bạn nhận diện tình huống cần tách workload báo cáo nặng khỏi transaction thời gian thực dựa trên dấu hiệu nào?
Bạn đánh giá partition pruning có xảy ra đúng kỳ vọng khi truy vấn bảng phân vùng như thế nào?
Khi một partition lớn hoặc nóng bất thường, bạn điều chỉnh chiến lược phân vùng dựa trên thông tin nào?
Những đặc điểm về tần suất đọc, độ mới dữ liệu và chi phí truy vấn nào khiến bạn chọn cache ở tầng ứng dụng?
Bạn kiểm soát tính mới và invalidation của cache để không đánh đổi sai tính đúng đắn dữ liệu ra sao?
Bạn xác định ranh giới transaction hợp lý để giảm thời gian giữ khóa và tài nguyên như thế nào?
Bạn phân biệt truy vấn chạy chậm do xử lý dữ liệu với truy vấn chờ transaction khác nhả khóa như thế nào?
Bạn sử dụng thông tin phiên đang chờ, phiên giữ khóa và thời gian transaction để tìm chuỗi chặn như thế nào?
Bạn điều tra deadlock và thay đổi thứ tự thao tác hoặc phạm vi khóa để giảm khả năng tái diễn ra sao?
Các mức cô lập transaction ảnh hưởng đến tranh chấp, khả năng đọc song song và lỗi retry như thế nào?
Bạn giảm tranh chấp khi nhiều transaction cùng cập nhật một hàng hoặc một khóa nóng theo những hướng nào?
Bạn phát hiện transaction mở quá lâu làm tăng giữ khóa hoặc giữ lại phiên bản dữ liệu cũ như thế nào?
Bạn thiết kế retry có backoff và bảo đảm idempotency khi gặp deadlock hoặc lỗi tranh chấp như thế nào?
Bạn phân biệt nghẽn vì số kết nối, pool chờ kết nối và số truy vấn thực thi đồng thời quá lớn như thế nào?
Bạn định cỡ connection pool dựa trên năng lực xử lý thực của cơ sở dữ liệu thay vì chỉ dựa vào số request ra sao?
Vì sao tăng đồng thời hoặc số kết nối có thể làm thông lượng giảm khi CPU, I/O hoặc khóa đã bão hòa?
Bạn kết hợp cache hit ratio, số lần đọc đĩa và kích thước working set để kiểm chứng giả thuyết thiếu RAM ra sao?
Bạn phân biệt vấn đề do đọc ngẫu nhiên, đọc tuần tự và ghi đồng bộ lên thiết bị lưu trữ ra sao?
Bạn dùng latency của ổ đĩa, IOPS, throughput và độ sâu hàng đợi để nhận diện nghẽn I/O như thế nào?
Bạn xác định một truy vấn chậm do phải ghi dữ liệu tạm khi thiếu bộ nhớ cho sort hoặc hash như thế nào?
Bạn cân đối cấu hình bộ nhớ dùng chung với bộ nhớ cấp theo truy vấn khi có nhiều phiên chạy đồng thời ra sao?
Bạn nhận diện cạnh tranh CPU do truy vấn tính toán nặng, context switching hoặc quá nhiều worker như thế nào?
Bạn đánh giá lợi ích và chi phí của thực thi truy vấn song song trong điều kiện tải đồng thời như thế nào?
Bạn kiểm tra tác động của checkpoint, WAL flush hoặc cơ chế ghi log bền vững tới độ trễ ghi như thế nào?
Bạn phát hiện hoạt động bảo trì như VACUUM, compaction hoặc rebuild index đang tranh tài nguyên với truy vấn ra sao?
Bạn đánh giá mức độ phân mảnh hoặc bloat của dữ liệu và chỉ mục trước khi tiến hành bảo trì như thế nào?
Bạn phân biệt độ trễ do replication lag với độ trễ thực thi truy vấn tại replica như thế nào?
Bạn quyết định chuyển một phần lượt đọc sang replica khi xét đến tải đọc, tính nhất quán và độ trễ replication ra sao?
Bạn đánh giá tác động của backup, restore test và tác vụ nền tới cửa sổ cao điểm như thế nào?
Khi tăng số lượng bản ghi làm truy vấn từ nhanh chuyển sang rất chậm, bạn kiểm tra những thay đổi nào về plan và tài nguyên?
Bạn xác định nguyên nhân tăng độ trễ sau một migration thêm index hoặc thay đổi kiểu dữ liệu như thế nào?
Bạn dùng load test từng bước để phân biệt ngưỡng bão hòa với đột biến lỗi do cấu hình timeout ra sao?
Bạn so sánh các phương án tối ưu theo thông lượng, p95/p99, mức dùng tài nguyên và tỷ lệ lỗi như thế nào?
Bạn kiểm soát biến số và độ nhiễu khi thực hiện thử nghiệm trước và sau một thay đổi SQL hoặc index như thế nào?
Bạn xác định ý nghĩa thống kê và tác động thực tế của một cải thiện hiệu năng từ nhiều lần đo ra sao?
Bạn đánh giá một tối ưu giúp truy vấn đọc nhanh hơn nhưng làm giao dịch ghi chậm hơn như thế nào?
Bạn thiết lập tiêu chí rollback cho thay đổi cấu hình, index hoặc query rewrite dựa trên những chỉ số nào?
Bạn xây dựng dashboard và cảnh báo sớm cho truy vấn chậm, tranh chấp khóa, I/O, RAM và pool chờ kết nối ra sao?
Bạn dự báo khi nào cần mở rộng năng lực cơ sở dữ liệu dựa trên tăng trưởng dữ liệu, tải và xu hướng thời gian phản hồi như thế nào?
Bạn trình bày bằng chứng nguyên nhân gốc, giải pháp và kết quả đo sau tối ưu cho đội phát triển và vận hành như thế nào?
