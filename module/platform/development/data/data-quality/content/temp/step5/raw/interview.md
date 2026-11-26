Bạn định nghĩa chất lượng dữ liệu dựa trên mục đích sử dụng và quyết định nghiệp vụ như thế nào?
Vì sao dữ liệu đúng định dạng vẫn có thể không đáp ứng yêu cầu chất lượng của hệ thống?
Bạn phân biệt độ đầy đủ, hợp lệ, chính xác, nhất quán, duy nhất và tính kịp thời qua ví dụ nào?
Bạn sẽ xác định các trường dữ liệu quan trọng nhất cần theo dõi chất lượng dựa trên mức độ rủi ro ra sao?
Khi một bảng có nhiều giá trị null, bạn xác định trường hợp nào là thiếu dữ liệu thực sự như thế nào?
Bạn thiết kế chỉ số completeness cho bản ghi và từng cột trong tập dữ liệu như thế nào?
Bạn sẽ kiểm tra validity của một trường bằng schema, miền giá trị và quy tắc nghiệp vụ ra sao?
Để đánh giá accuracy, bạn lựa chọn nguồn đối chiếu đáng tin cậy và cách lấy mẫu như thế nào?
Bạn nhận diện consistency giữa hai bảng hoặc hai hệ thống cùng lưu một thông tin bằng cách nào?
Khi một người có nhiều bản ghi định danh khác nhau, bạn thiết kế quy tắc uniqueness và deduplication ra sao?
Bạn sẽ phân biệt bản ghi trùng hoàn toàn với bản ghi có thể đại diện cùng một thực thể như thế nào?
Bạn đánh giá timeliness dựa trên thời điểm sự kiện, thời điểm nhận và thời điểm xử lý như thế nào?
Khi pipeline nhận dữ liệu đến muộn, bạn tính độ mới và độ trễ theo mốc thời gian nào?
Những rủi ro nào phát sinh nếu chỉ dùng một điểm chất lượng tổng hợp cho toàn bộ bảng dữ liệu?
Bạn sẽ thực hiện data profiling ban đầu để thống kê null, distinct, min, max và phân phối giá trị ra sao?
Bạn dùng histogram, quantile và tần suất top value để phát hiện phân phối bất thường như thế nào?
Khi một cột có nhiều giá trị đặc biệt như N/A hoặc UNKNOWN, bạn tìm hiểu ngữ nghĩa trước khi xử lý ra sao?
Bạn sẽ dùng SQL để đo tỷ lệ bản ghi vi phạm miền giá trị hoặc điều kiện ngày tháng như thế nào?
Bạn xây dựng truy vấn SQL phát hiện duplicate theo khóa nghiệp vụ và khoảng thời gian ra sao?
Khi dữ liệu có quan hệ cha con, bạn kiểm tra referential integrity bằng SQL như thế nào?
Bạn sẽ phát hiện dữ liệu không nhất quán về đơn vị tiền tệ hoặc múi giờ bằng những quy tắc nào?
Một tập dữ liệu có cỡ mẫu nhỏ ảnh hưởng thế nào đến cách chọn ngưỡng cảnh báo chất lượng?
Bạn phân biệt hard constraint phải chặn xử lý với soft threshold chỉ cần cảnh báo ra sao?
Bạn sẽ thiết lập ngưỡng tỷ lệ lỗi theo lịch sử dữ liệu, chi phí sửa và SLA như thế nào?
Khi dữ liệu có tính mùa vụ, bạn xây dựng baseline phát hiện bất thường tránh cảnh báo sai ra sao?
Bạn dùng so sánh theo lô trước và sau để phát hiện số lượng bản ghi sụt giảm bất ngờ như thế nào?
Khi phân phối một thuộc tính thay đổi đột ngột, bạn điều tra đó là lỗi pipeline hay thay đổi nghiệp vụ ra sao?
Bạn đánh giá schema drift và biến động tỷ lệ null trong quá trình ingestion như thế nào?
Bạn sẽ bổ sung kiểm tra chất lượng ngay tại source, trong pipeline và tại điểm phục vụ dữ liệu ra sao?
Trong pipeline batch, bạn xử lý trường hợp một phần bản ghi hợp lệ và phần còn lại sai như thế nào?
Bạn thiết kế dead-letter queue hoặc quarantine để lưu bản ghi lỗi và nguyên nhân vi phạm ra sao?
Bạn sẽ tạo quy trình sửa, phát lại và chống xử lý trùng các bản ghi bị quarantine như thế nào?
Khi sửa dữ liệu nguồn, bạn kiểm tra ảnh hưởng đến bảng downstream và báo cáo lịch sử ra sao?
Bạn phân biệt sửa dữ liệu tại nguồn với bổ sung logic làm sạch trong bước biến đổi như thế nào?
Bạn sẽ sử dụng Java để viết bộ kiểm tra quality rule có thể tái sử dụng trên nhiều nguồn như thế nào?
Khi validation theo từng bản ghi làm pipeline chậm, bạn tối ưu chiến lược kiểm tra bằng cách nào?
Bạn sẽ thiết kế test dữ liệu cho các giá trị biên, null, Unicode và trường hợp dữ liệu trái ngữ nghĩa ra sao?
Bạn kiểm tra tính idempotent của pipeline để một batch chạy lại không tạo bản ghi trùng như thế nào?
Khi tích hợp dữ liệu từ hai hệ thống, bạn định nghĩa khóa khớp và quy tắc giải quyết xung đột ra sao?
Bạn sẽ quản lý version của bộ quality rule khi business thay đổi điều kiện hợp lệ như thế nào?
Những chỉ số data freshness, error rate, drift và quarantine count nào bạn đưa vào dashboard giám sát?
Bạn thiết kế cảnh báo thế nào để chỉ kích hoạt khi vấn đề chất lượng có tác động thực tế tới người dùng?
Khi một quy tắc chất lượng báo sai liên tục, bạn xác minh và điều chỉnh mà vẫn bảo đảm kiểm soát ra sao?
Bạn sẽ ghi lại owner, nguồn gốc, công thức tính và ngưỡng chấp nhận cho một chỉ số chất lượng như thế nào?
Bạn thiết kế SLA hoặc SLO về độ mới và độ đầy đủ cho một dataset được nhiều nhóm sử dụng ra sao?
Khi kiểm tra chất lượng phát hiện lỗi ở production, bạn phân loại mức độ ảnh hưởng và ưu tiên xử lý thế nào?
Bạn sẽ truy vết lineage để xác định bước biến đổi đầu tiên làm sai lệch dữ liệu như thế nào?
Bạn xác nhận dữ liệu đã phục hồi đúng sau khi sửa lỗi và chạy bù một pipeline ra sao?
Bạn lựa chọn chỉ số nào để chứng minh chương trình cải thiện chất lượng dữ liệu có hiệu quả sau nhiều sprint?
Nếu một bảng có mọi trường đúng schema nhưng tổng doanh thu sai, bạn sẽ xây dựng chuỗi kiểm tra để tìm nguyên nhân như thế nào?
