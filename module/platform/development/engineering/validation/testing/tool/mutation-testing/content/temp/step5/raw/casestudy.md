Một bộ tính chiết khấu Java đạt 100% line coverage, nhưng PIT đổi điều kiện nhận ưu đãi từ lớn hơn thành lớn hơn hoặc bằng mà mọi unit test vẫn xanh; nhóm cần xem lại những giá trị nằm sát ngưỡng nghiệp vụ.
Trong dịch vụ tính thuế, một mutant thay phép cộng bằng phép trừ vẫn sống sót vì bài kiểm thử chỉ xác nhận kết quả không âm; đội cần đánh giá sức mạnh của assertion khi công thức bị thay đổi.
Một lớp xác nhận đơn hàng có nhiều nhánh lỗi, nhưng PIT loại bỏ một lệnh kiểm tra mà không làm test thất bại; bộ test hiện chỉ kiểm tra trạng thái trả về cho đơn hợp lệ.
Ứng dụng phát thông báo sau khi ghi đơn hàng, nhưng mutant xóa lời gọi gửi thông báo vẫn sống sót; unit test không quan sát bất kỳ tác dụng phụ nào ngoài giá trị trả về của service.
Một bộ xử lý tính điểm có mutant đổi giá trị trả về sang giá trị mặc định, nhưng bài test so sánh hai kết quả với một ngưỡng sai số quá rộng; nhóm phải xác định độ chính xác yêu cầu và cách viết điều kiện kiểm tra.
Hàm phân trang có mutant thay điều kiện dừng vòng lặp khiến trang cuối mất một bản ghi; bộ test dùng duy nhất tập dữ liệu đúng một trang và không phát hiện sai lệch.
Một phương thức xử lý mã giảm giá có mutant đảo điều kiện kiểm tra ngày hết hạn, nhưng bộ test chỉ dùng mã chưa hết hạn; nhóm cần bổ sung những trạng thái nào để phân biệt hành vi đúng và sai.
Đội xây bộ kiểm thử tham số hóa cho hàm phân loại tuổi, nhưng các trường hợp chỉ nằm giữa từng khoảng; PIT cho thấy thay đổi các dấu so sánh tại ranh giới không bị phát hiện.
Một lớp chuyển đổi số tiền có mutant thay cách làm tròn ở một nhánh, nhưng các số đầu vào hiện tại đều có phần thập phân không gây khác biệt; nhóm cần tìm dữ liệu thể hiện rõ hợp đồng làm tròn.
Hàm tìm sản phẩm được bao phủ bởi nhiều bài test nhưng mỗi bài dùng repository mock trả cùng kết quả cho mọi mã; mutant thay mã truyền xuống repository vẫn không làm kết quả kiểm thử thay đổi.
Trong module xử lý đăng nhập, một mutant thay nhánh ném ngoại lệ thành trả về kết quả rỗng; test chỉ kiểm tra rằng lời gọi hoàn tất mà không xác nhận loại lỗi hoặc nội dung phản hồi.
PIT báo một mutant sống sót ở bước sắp xếp danh sách giao dịch, nhưng hợp đồng API không quy định thứ tự đối với các giao dịch cùng thời điểm; nhóm cần xác định sai lệch có thực sự quan sát được theo yêu cầu hay không.
Một mutant bỏ phép nhân với một trong biểu thức tính tổng và cho kết quả không đổi với mọi đầu vào; reviewer cần đánh giá liệu mutant có tương đương về ngữ nghĩa trước khi yêu cầu thêm test.
Trong một nhánh logic không thể chạy vì đã được loại bởi điều kiện trước đó, PIT vẫn tạo mutant còn sống; nhóm phải phân biệt mã không thể tiếp cận với lỗ hổng kiểm thử và quyết định cách xử lý.
Một dịch vụ chỉ nhận số lượng dương theo hợp đồng đầu vào, nhưng mutant khác biệt duy nhất khi số lượng âm; đội kiểm thử và nghiệp vụ không thống nhất liệu cần kiểm tra dữ liệu ngoài miền hay xem đó là trường hợp không hợp lệ.
Nhóm mở rộng bộ mutator của PIT để tạo nhiều kiểu biến đổi hơn, khiến mutation score giảm mạnh so với tháng trước dù không sửa code; quản lý cần đánh giá khả năng so sánh các mốc điểm có cấu hình khác nhau.
Một dự án Gradle Java hiển thị mutation score gần như hoàn hảo, nhưng bản báo cáo PIT chỉ chứa vài lớp tiện ích; nhóm cần kiểm tra phạm vi targetClasses và các phần logic quan trọng đã bị bỏ ngoài.
Trong dự án Maven đa module, cấu hình PIT chỉ nhận các lớp test của module ứng dụng, khiến mutant trong thư viện chung không được chạy với các bài kiểm thử liên quan.
Sau khi nâng lên JUnit Jupiter, bộ unit test chạy bình thường nhưng PIT báo không tìm được bài test phù hợp cho một số lớp; đội cần xem lại cấu hình tích hợp công cụ và cơ chế khám phá test.
Một dự án nâng phiên bản JDK trong CI và công cụ mutation testing đột nhiên báo lỗi khi xử lý bytecode, dù build và test JUnit vẫn thành công; nhóm cần xác minh tính tương thích giữa các phiên bản công cụ.
Lần chạy PIT đầy đủ mất hơn hai giờ trên kho mã lớn, khiến nhóm bắt đầu bỏ qua kiểm tra mutation trước khi merge; đội phải cân nhắc phạm vi chạy theo thay đổi và một đợt quét đầy đủ định kỳ.
Một pipeline chỉ chạy mutation testing trên các lớp có thay đổi nhưng không tính đến bài test mới thuộc module khác; mutation score sau PR cao bất thường và nhóm cần kiểm tra cách xác định các lớp cùng test liên quan.
Một mutant được phân loại sống sót dù bài test liên quan đôi khi thất bại khi chạy độc lập; kết quả mutation thay đổi giữa các lần chạy do test phụ thuộc đồng hồ và dữ liệu dùng chung.
PIT liên tục đánh dấu mutant timeout trong một thuật toán xử lý danh sách lớn; không rõ việc lặp vô hạn do biến đổi hay máy CI bị thiếu tài nguyên, khiến nhóm cần phân tích bằng chứng trước khi tính kết quả.
Một suite JUnit có các bài test sử dụng biến tĩnh chung; khi PIT chạy các mutant qua những tiến trình hoặc thứ tự khác nhau, kết quả giết mutant trở nên không ổn định.
Một mutant xóa thao tác ghi log vẫn sống sót, nhưng log chỉ phục vụ chẩn đoán và không nằm trong hợp đồng công khai; nhóm phải xác định mức độ ưu tiên thay vì viết test ràng buộc quá chặt vào chi tiết triển khai.
Sau khi thêm test để giết mutant, nhóm bắt đầu kiểm tra trực tiếp nhiều phương thức private bằng phản chiếu; một lần refactor cấu trúc nội bộ làm test hỏng dù hành vi bên ngoài không đổi.
Một lớp Java chứa phần lớn getter và setter đơn giản đạt mutation score cao, trong khi luồng xử lý hoàn tiền vẫn có nhiều mutant sống sót; quản lý muốn phân bổ công sức theo mức rủi ro nghiệp vụ thay vì điểm trung bình.
Đội đề xuất loại toàn bộ package chứa mã sinh tự động khỏi PIT vì hàng trăm mutant khó xử lý, nhưng cùng package có một vài lớp quy tắc nghiệp vụ do lập trình viên tự viết; phạm vi loại trừ cần được đánh giá kỹ.
Một dự án đặt quality gate yêu cầu mutation score ít nhất 90%, nhưng module vừa thêm một phương thức nhỏ nên chỉ một mutant sống sót đã làm điểm giảm mạnh và chặn toàn bộ bản vá khẩn cấp.
Sau khi thay đổi cơ chế cache, số mutant sống sót của một service tăng nhưng dashboard không cho thấy thay đổi ở những dòng nào; nhóm cần phân tích báo cáo PIT để nhận ra assertion thiếu, mutant tương đương hay phạm vi test không được chạy.
Sau hai quý theo dõi mutation score trên CI, số điểm trung bình tăng nhưng lỗi sản xuất liên quan giao dịch vẫn tái diễn; trưởng nhóm cần kết hợp dữ liệu mutant sống sót, các ca lỗi thực tế và rủi ro để đánh giá hiệu quả bộ test.
