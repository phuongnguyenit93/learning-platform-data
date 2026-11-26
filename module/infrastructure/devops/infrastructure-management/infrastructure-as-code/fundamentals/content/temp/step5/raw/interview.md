Bạn giải thích tư duy mô tả trạng thái mong muốn trong Infrastructure as Code khác với việc chạy tuần tự các lệnh cấu hình như thế nào, và điều gì giúp áp dụng lại cấu hình một cách nhất quán?
Khi xây dựng hạ tầng gồm mạng, cơ sở dữ liệu và dịch vụ ứng dụng, bạn xác định quan hệ phụ thuộc giữa các tài nguyên ra sao và sẽ xử lý trường hợp xuất hiện phụ thuộc vòng như thế nào?
Bạn thiết kế cấu trúc mã IaC và cách truyền biến, đầu ra giữa các thành phần như thế nào để tái sử dụng cho development, staging và production nhưng vẫn cô lập thay đổi của từng môi trường?
Nếu hai pipeline cùng muốn thay đổi một môi trường, bạn sẽ tổ chức lưu trữ state từ xa, cơ chế khóa và phân quyền như thế nào để tránh ghi đè hoặc tạo hạ tầng không nhất quán?
Khi đưa một tài nguyên cloud đã được tạo thủ công vào quản lý bằng IaC, bạn sẽ đối chiếu trạng thái thực tế, mã cấu hình và state như thế nào để tránh vô tình thay thế hoặc xóa tài nguyên đó?
Nếu phát hiện cấu hình production bị thay đổi trực tiếp ngoài quy trình IaC, bạn sẽ xác minh nguyên nhân drift và quyết định cập nhật mã hay đưa hạ tầng về trạng thái đã khai báo theo tiêu chí nào?
Khi bản kế hoạch thay đổi cho thấy một tài nguyên quan trọng sẽ bị thay thế thay vì cập nhật tại chỗ, bạn sẽ đánh giá tác động, dữ liệu liên quan và điều kiện phê duyệt trước khi áp dụng ra sao?
Bạn kiểm soát phiên bản công cụ, provider và module dùng chung trong dự án IaC như thế nào để các lần chạy sau vẫn tái tạo được hạ tầng và có thể nâng cấp thành phần an toàn?
Bạn sẽ quản lý thông tin xác thực và dữ liệu nhạy cảm trong mã IaC, biến đầu vào, kết quả kế hoạch, state và nhật ký pipeline ra sao để hạn chế rò rỉ bí mật?
Trước khi cho phép thay đổi hạ tầng production, bạn sẽ phối hợp kiểm tra cú pháp, kiểm thử module, phân tích chính sách bảo mật và thử nghiệm trên môi trường tách biệt như thế nào?
Bạn thiết kế pipeline CI/CD cho IaC như thế nào để người duyệt xem đúng bản kế hoạch, bước áp dụng dùng đúng phiên bản mã đã duyệt và tài khoản thực thi chỉ có quyền cần thiết?
Nếu lần áp dụng IaC thất bại giữa chừng và state có nguy cơ mất đồng bộ với tài nguyên thực tế, bạn sẽ kiểm tra, khôi phục và xác nhận trạng thái hệ thống trước khi chạy lại hoặc quay lui như thế nào?
