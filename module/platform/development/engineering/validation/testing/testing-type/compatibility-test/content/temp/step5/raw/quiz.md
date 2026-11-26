Câu 1. Sản phẩm hỗ trợ nhiều JDK, OS và trình duyệt; nên chọn ma trận kiểm thử thế nào khi thời gian hạn chế?
A. Thử mọi tổ hợp có cùng mức ưu tiên như nhau
B. Chỉ dùng máy mới nhất của nhóm phát triển
C. Chỉ kiểm thử môi trường có tốc độ chạy cao
D. Ưu tiên tổ hợp theo người dùng và mức rủi ro
Đáp án đúng: D

Câu 2. Ứng dụng build trên JDK 21 nhưng chạy trên JDK 17; điều kiện nào quyết định khả năng tải class?
A. Tên tệp JAR giống nhau trên hai môi trường
B. Mã bytecode và API cần tương thích JDK 17
C. Số lượng dependency nhỏ hơn số module Java
D. Package ứng dụng không chứa các lớp abstract
Đáp án đúng: B

Câu 3. Ứng dụng chạy trên Windows nhưng lỗi tìm tệp khi chuyển sang Linux; nguyên nhân nào đáng kiểm tra?
A. Khác biệt phân biệt hoa thường của tên tệp
B. Java tự thay đổi định dạng Unicode của tên lớp
C. Linux chỉ cho phép đường dẫn dùng chữ số
D. Windows luôn chuyển mọi tên tệp thành chữ hoa
Đáp án đúng: A

Câu 4. Một báo cáo xuất ngày ở UTC+7 nhưng sai trên máy UTC-5; test tương thích nên tập trung gì?
A. Số lượng thread được cấp cho trình duyệt
B. Cách chuyển timezone và hiển thị thời gian
C. Độ lớn bộ nhớ heap của tiến trình Java
D. Thứ tự các trường của đối tượng JSON đầu ra
Đáp án đúng: B

Câu 5. Giao diện dùng một Web API chỉ hỗ trợ ở vài phiên bản trình duyệt; cách phát hiện sớm vấn đề là gì?
A. Chỉ kiểm thử trình duyệt đang dùng ở máy dev
B. Coi mọi trình duyệt đều hỗ trợ Web API giống nhau
C. Kiểm tra bảng hỗ trợ và thử tính năng liên quan
D. Tăng timeout cho mọi test giao diện trên CI
Đáp án đúng: C

Câu 6. Với trình duyệt cũ chưa hỗ trợ API cần thiết, polyfill dùng để làm gì?
A. Thay đổi cấu trúc bảng dữ liệu phía database
B. Tự nâng phiên bản trình duyệt của người dùng
C. Bắt buộc frontend chạy lại trong JDK của server
D. Cung cấp phần chức năng API còn thiếu
Đáp án đúng: D

Câu 7. Vì sao kiểm thử trên màn hình rộng chưa đủ để khẳng định tương thích thiết bị di động?
A. Thiết bị di động luôn có tốc độ mạng bằng Wi-Fi
B. Mọi điện thoại đều dùng cùng engine trình duyệt
C. Viewport, tương tác chạm và bộ nhớ có thể khác
D. Trình duyệt di động không xử lý được CSS
Đáp án đúng: C

Câu 8. Sau deploy frontend, một trình duyệt vẫn chạy JavaScript cũ; yếu tố nào nên kiểm tra?
A. Chiến lược cache và version của tài nguyên tĩnh
B. Chỉ số bytecode mà compiler Java phát sinh
C. Quy tắc commit trong repository của backend
D. Số lượng request do người dùng tạo mỗi giờ
Đáp án đúng: A

Câu 9. Backend thêm một field JSON tùy chọn vào response; khi nào client cũ thường vẫn tương thích?
A. Client cũ yêu cầu mọi field đều phải biết trước
B. Client cũ bỏ qua field lạ theo hợp đồng đã có
C. Backend đổi kiểu các field cũ sang kiểu khác
D. Backend xóa các field bắt buộc khỏi response
Đáp án đúng: B

Câu 10. Thay tên field response từ amount sang totalAmount mà không hỗ trợ tên cũ có nguy cơ nào?
A. Giảm hoàn toàn nhu cầu cập nhật phía client
B. Tự giữ tương thích nếu dữ liệu vẫn là số
C. Khiến client cũ xử lý nhanh hơn sau lần gọi
D. Phá vỡ client đang phụ thuộc field amount
Đáp án đúng: D

Câu 11. Thư viện mới dùng API chỉ có từ JDK 21 nhưng sản phẩm hỗ trợ JDK 17; nên làm gì?
A. Kiểm thử đường chạy trên JDK thấp nhất hỗ trợ
B. Chỉ chạy unit test bằng JDK mới nhất của nhóm
C. Giữ phiên bản thư viện dù JDK 17 không tải được
D. Xem kết quả compile trên JDK 21 là đủ điều kiện
Đáp án đúng: A

Câu 12. Thêm cột NOT NULL không có DEFAULT vào bảng đang được writer phiên bản cũ sử dụng có thể gây gì?
A. Writer cũ tự sinh trường bắt buộc một cách an toàn
B. Reader cũ lập tức ngừng đọc mọi bảng không liên quan
C. Hệ quản trị tự lược bỏ cột mới trong mọi lệnh INSERT
D. Lệnh INSERT cũ có thể lỗi do thiếu giá trị cột mới
Đáp án đúng: D

Câu 13. File CSV dùng dấu phẩy để phân tách nhưng môi trường khác dùng dấu phẩy thập phân; nên kiểm tra gì?
A. Chỉ cách viết hoa tên tệp trước khi xuất báo cáo
B. Chỉ số lượng dòng comment trong chương trình
C. Định dạng số, locale và quy tắc quote/delimiter
D. Độ lớn màn hình hiển thị khi mở ứng dụng
Đáp án đúng: C

Câu 14. Vì sao cùng một API endpoint cần thử qua cả client phiên bản cũ và mới?
A. Hai phiên bản client luôn gửi cùng body từng byte
B. Hai phiên bản có thể có kỳ vọng field khác nhau
C. Client mới luôn tự động sửa payload của client cũ
D. Provider có thể bỏ mọi cấu hình phiên bản khi test
Đáp án đúng: B

Câu 15. Trước khi bỏ hỗ trợ một phiên bản trình duyệt ít dùng, dữ liệu nào giúp quyết định?
A. Số lượng file CSS trong ứng dụng hiện tại
B. Số lượng developer thích dùng trình duyệt mới
C. Lượng sử dụng, mức rủi ro và cam kết hỗ trợ
D. Tên engine có nhiều chữ cái nhất trong danh sách
Đáp án đúng: C

Câu 16. Trong ma trận gồm 20 cấu hình hỗ trợ, cách nào duy trì phản hồi nhanh trên mỗi pull request?
A. Chạy smoke test thiết yếu theo cấu hình ưu tiên
B. Chạy thử tải toàn bộ môi trường trong mọi commit
C. Chỉ kiểm tra mã nguồn mà không chạy test thực tế
D. Bỏ luôn các cấu hình cũ khỏi kế hoạch kiểm thử
Đáp án đúng: A

Câu 17. Khi cần kiểm tra lỗi render khác nhau giữa các trình duyệt, yếu tố nào đáng chú ý?
A. Tên repository chứa mã nguồn của giao diện
B. Số lượng bảng SQL trong tầng lưu trữ backend
C. Phiên bản hệ thống build của lớp domain
D. Khác biệt engine dựng layout và xử lý CSS
Đáp án đúng: D

Câu 18. Một lỗi chỉ xuất hiện với phiên bản dependency cụ thể; báo cáo tương thích cần ghi gì?
A. Phiên bản thư viện, runtime và cấu hình tái hiện
B. Chỉ ảnh chụp màn hình không kèm môi trường
C. Chỉ tên người phát hiện và thời điểm báo cáo
D. Chỉ tổng số test đã chạy của cả bản phát hành
Đáp án đúng: A

Câu 19. Giao diện hoạt động ở chế độ dọc nhưng lỗi ở chế độ ngang; cần đưa yếu tố gì vào kiểm thử?
A. Cách database cấp khóa chính cho mọi bảng
B. Tư thế xoay màn hình và kích thước viewport
C. Tên file triển khai backend của phiên bản mới
D. Các phiên bản compiler dùng để tạo bytecode
Đáp án đúng: B

Câu 20. Phần mềm hỗ trợ điều khiển bằng bàn phím trên desktop; khi kiểm tra trên tablet, nên xác minh thêm gì?
A. Hành vi tương tác chạm và điều hướng tương ứng
B. Mọi thao tác chạm phải chuyển thành phím Enter
C. Chỉ cần nhập liệu bằng bàn phím vật lý gắn ngoài
D. Tất cả thiết bị phải có cùng độ phân giải màn hình
Đáp án đúng: A

Câu 21. Nâng một thư viện làm thay đổi phiên bản phụ thuộc bắc cầu có thể gây lỗi gì?
A. Mọi tệp dữ liệu JSON tự đổi sang định dạng XML
B. JDK tự hạ bytecode xuống phiên bản cũ hơn
C. Không khớp API hoặc liên kết lớp lúc chạy
D. Mọi cấu hình hỗ trợ tự được cập nhật đồng loạt
Đáp án đúng: C

Câu 22. Với phiên bản API mới dự định phát hành, chiến lược nào giảm nguy cơ phá vỡ tích hợp cũ?
A. Xóa ngay endpoint cũ mà không chạy kiểm thử
B. Chỉ chạy thử với consumer nội bộ mới nhất
C. Thay kiểu dữ liệu cũ mà không thông báo trước
D. Kiểm tra client cũ và duy trì lộ trình chuyển đổi
Đáp án đúng: D

Câu 23. Test một ứng dụng trên máy ảo nhưng lỗi chỉ xảy ra trên thiết bị thật; nhận định nào phù hợp?
A. Môi trường ảo luôn chứng minh đủ mọi phần cứng
B. Cần bổ sung test thiết bị thật cho rủi ro đặc thù
C. Chỉ cần tăng độ phân giải giả lập để loại mọi lỗi
D. Có thể bỏ lỗi vì kết quả trên máy ảo là chuẩn
Đáp án đúng: B

Câu 24. Phát hành hỗ trợ nhiều hệ điều hành; release gate tương thích nên dựa vào điều gì?
A. Số lượng commit của mỗi nhóm ở sprint hiện tại
B. Kết quả chạy compile trên máy phát triển chính
C. Kết quả test theo ma trận hỗ trợ và ngoại lệ rõ ràng
D. Số lượng bài kiểm thử viết thêm trong tuần cuối
Đáp án đúng: C
