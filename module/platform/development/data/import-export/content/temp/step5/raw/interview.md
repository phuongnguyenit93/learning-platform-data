Bạn sẽ xác định hợp đồng dữ liệu, nguồn nhập và đích xuất trước khi thiết kế một luồng import/export trong ứng dụng Java như thế nào?
Bạn lựa chọn CSV, JSON, XML, Excel hoặc định dạng chuyên dụng dựa trên đặc điểm dữ liệu và yêu cầu trao đổi ra sao?
Bạn sẽ phân biệt trách nhiệm của tầng đọc định dạng, ánh xạ dữ liệu, kiểm tra hợp lệ và lưu trữ trong kiến trúc import như thế nào?
Bạn sẽ mô tả schema và quy tắc bắt buộc của một tệp trao đổi để các hệ thống sử dụng thống nhất ra sao?
Bạn sẽ kiểm soát khác biệt giữa phiên bản schema mới và dữ liệu do đối tác dùng phiên bản cũ gửi tới như thế nào?
Bạn sẽ phát hiện và xử lý trường hợp encoding không khớp, xuất hiện BOM hoặc ký tự Unicode bị hỏng ra sao?
Bạn sẽ lựa chọn cách xử lý các kiểu xuống dòng khác nhau khi đọc tệp từ nhiều hệ điều hành như thế nào?
Bạn sẽ phân tích cách dấu phân cách, dấu nháy và ký tự xuống dòng bên trong ô ảnh hưởng đến việc đọc CSV ra sao?
Bạn sẽ xử lý một dòng CSV có số cột không đúng hoặc dấu nháy chưa đóng mà vẫn ghi nhận lỗi chính xác như thế nào?
Bạn sẽ thiết kế cơ chế nhận diện và ánh xạ tên cột CSV khi thứ tự cột thay đổi ra sao?
Bạn sẽ chuyển đổi giá trị số theo locale mà không làm sai dấu thập phân hoặc dấu phân tách hàng nghìn như thế nào?
Bạn sẽ xác định hợp đồng cho dữ liệu ngày giờ, múi giờ và độ chính xác khi nhập xuất qua nhiều hệ thống ra sao?
Bạn sẽ phân biệt giá trị trống, null và trường hoàn toàn vắng mặt trong dữ liệu đầu vào như thế nào?
Bạn sẽ lựa chọn giữa một tài liệu JSON lớn và nhiều bản ghi JSON theo dòng để xử lý khối lượng dữ liệu lớn ra sao?
Bạn sẽ triển khai đọc JSON dạng luồng trong Java để tránh giữ toàn bộ nội dung trong bộ nhớ như thế nào?
Bạn sẽ xử lý các trường JSON không nhận diện được, khóa trùng hoặc sai kiểu dữ liệu theo chính sách nào?
Bạn sẽ ánh xạ các cấu trúc JSON lồng nhau vào mô hình dữ liệu nội bộ mà vẫn giữ thông tin đường dẫn lỗi như thế nào?
Bạn sẽ phân tích tác động của namespace và schema XML đối với việc kiểm tra và ánh xạ tài liệu như thế nào?
Bạn sẽ cấu hình bộ phân tích XML để giảm rủi ro từ thực thể ngoài và tham chiếu tới tài nguyên không đáng tin cậy ra sao?
Bạn sẽ chọn mô hình xử lý XML dạng sự kiện hay dạng cây dựa trên kích thước và thao tác cần thực hiện như thế nào?
Bạn sẽ xác định sheet, hàng tiêu đề và vùng dữ liệu khi nhập một workbook Excel có cấu trúc không đồng nhất ra sao?
Bạn sẽ xử lý ô Excel chứa công thức, ngày tháng và giá trị đã định dạng để tránh hiểu sai dữ liệu như thế nào?
Bạn sẽ thiết kế xuất Excel khối lượng lớn để hạn chế bộ nhớ, đồng thời giữ được kiểu dữ liệu và cấu trúc cột ra sao?
Bạn sẽ phòng tránh việc dữ liệu do người dùng nhập trở thành công thức nguy hiểm khi xuất sang CSV hoặc Excel như thế nào?
Bạn sẽ xây dựng adapter cho một định dạng trao đổi chuyên dụng mà không làm phức tạp phần logic nghiệp vụ như thế nào?
Bạn sẽ thiết kế ánh xạ từ bản ghi nhập thành DTO và thực thể nghiệp vụ để kiểm soát trường nào được phép cập nhật ra sao?
Bạn sẽ xác định các bước chuẩn hóa dữ liệu và giới hạn việc chuẩn hóa để tránh thay đổi ý nghĩa dữ liệu gốc như thế nào?
Bạn sẽ phân biệt lỗi cú pháp tệp, lỗi schema và lỗi nghiệp vụ ở từng bản ghi trong báo cáo nhập như thế nào?
Bạn sẽ xây dựng validation liên trường và validation dựa trên dữ liệu đã tồn tại như thế nào?
Bạn sẽ ghi nhận số dòng, tên cột, đường dẫn trường và giá trị có vấn đề để người dùng sửa tệp dễ dàng ra sao?
Bạn sẽ quyết định khi nào dừng toàn bộ quá trình nhập và khi nào tiếp tục bỏ qua bản ghi lỗi theo những tiêu chí nào?
Bạn sẽ thiết kế báo cáo kết quả nhập có tổng số bản ghi, số thành công và danh sách lỗi mà vẫn bảo vệ dữ liệu nhạy cảm ra sao?
Bạn sẽ xử lý bản ghi trùng khóa hoặc trùng nội dung trong một tệp và giữa nhiều lần nhập như thế nào?
Bạn sẽ bảo đảm một tác vụ nhập có thể chạy lại sau timeout mà không tạo dữ liệu trùng hoặc cập nhật sai ra sao?
Bạn sẽ định nghĩa ranh giới giao dịch khi một tệp chứa hàng trăm nghìn bản ghi cần được ghi vào cơ sở dữ liệu như thế nào?
Bạn sẽ sử dụng vùng dữ liệu tạm và bước xác nhận để tránh công bố dữ liệu nhập chưa hoàn tất ra sao?
Bạn sẽ xử lý tình huống tác vụ nhập dừng giữa chừng sau khi một số lô đã được lưu thành công như thế nào?
Bạn sẽ phân tích các phụ thuộc khóa ngoại và thứ tự nhập giữa nhiều loại bản ghi liên quan như thế nào?
Bạn sẽ chọn kích thước lô phù hợp để cân bằng tốc độ ghi, áp lực bộ nhớ và khả năng phục hồi ra sao?
Bạn sẽ áp dụng cơ chế backpressure để nguồn đọc nhanh không làm quá tải bước xác minh hoặc ghi dữ liệu như thế nào?
Bạn sẽ đóng đúng các tài nguyên đọc ghi và quản lý lỗi phát sinh trong quá trình đóng stream Java ra sao?
Bạn sẽ thiết kế tác vụ import/export chạy nền có thể theo dõi tiến độ, hủy và tiếp tục an toàn như thế nào?
Bạn sẽ kiểm soát dung lượng tệp, số cột, độ sâu lồng nhau và giới hạn thời gian để chống đầu vào gây cạn kiệt tài nguyên ra sao?
Bạn sẽ kiểm tra đường dẫn, tên tệp và quyền truy cập khi người dùng cung cấp tệp nhập hoặc đích xuất như thế nào?
Bạn sẽ bảo vệ dữ liệu cá nhân và bí mật nghiệp vụ trong tệp tạm, log, báo cáo lỗi và tệp xuất ra sao?
Bạn sẽ bảo đảm dữ liệu xuất từ nhiều bảng nhất quán tại cùng một thời điểm khi hệ thống vẫn có giao dịch cập nhật như thế nào?
Bạn sẽ lựa chọn xuất toàn bộ dữ liệu hay chỉ phần thay đổi và quản lý mốc đồng bộ giữa hai hệ thống ra sao?
Bạn sẽ tổ chức kiểm thử với tệp hợp lệ, tệp lỗi, dữ liệu biên và dữ liệu rất lớn để đánh giá độ tin cậy ra sao?
Bạn sẽ đo thời gian, bộ nhớ và tỉ lệ bản ghi lỗi của luồng import/export để xác định điểm nghẽn như thế nào?
Bạn sẽ xử lý tình huống một đối tác đổi cấu trúc tệp mà không báo trước, trong khi các tác vụ nhập đang chạy hằng ngày như thế nào?
