Một nhóm Java dùng Gradle có lập trình viên làm việc trên Windows và Linux; mỗi lần một người lưu file trong IDE thì pull request xuất hiện hàng trăm thay đổi khoảng trắng dù không chỉnh logic.
Pipeline CI của dự án Spring Boot chạy bước kiểm tra Spotless và thất bại vì thứ tự import, trong khi cả nhóm đều thấy mã đã được định dạng đúng trên IntelliJ IDEA.
Một repository Gradle nhiều module chỉ áp dụng cấu hình Spotless ở dự án gốc, khiến các module mới bổ sung không được kiểm tra định dạng trong build của nhóm.
Ứng dụng Java dùng Maven có cấu hình formatter trong pluginManagement ở parent POM; lập trình viên chạy lệnh kiểm tra tại module con nhưng không thấy ràng buộc định dạng được thực thi.
Một đội nâng dự án từ Java 11 lên Java 21 và đổi phiên bản formatter; các pull request đang mở liên tục bị xung đột vì cùng một phương thức bị xuống dòng khác nhau.
Nhóm sử dụng Google Java Format trong Spotless nhưng đối tác gửi bản vá đã được định dạng bằng profile Eclipse; pull request chỉ thay đổi một điều kiện vẫn tạo diff lớn.
Trong dự án dùng Gradle Kotlin DSL, người duy trì chép cấu hình Spotless từ ví dụ Groovy DSL và pipeline báo lỗi cấu hình plugin trước khi biên dịch Java.
Một công ty muốn Spotless kiểm tra toàn bộ mã Java tự viết nhưng thư mục chứa mã sinh tự động từ OpenAPI cũng bị tính vào phạm vi, khiến mỗi lần sinh lại source đều phát sinh sai lệch.
Một repository chứa mã Java của nhà cung cấp để tham khảo; bước Spotless Apply chỉnh sửa cả mã vendor và gây khó khăn khi đồng bộ bản cập nhật từ upstream.
Nhóm muốn thêm header bản quyền cho các file Java mới nhưng dự án đã có nhiều file mang header cũ khác nhau, khiến việc áp dụng formatter có nguy cơ sửa hàng loạt file lịch sử.
Một lập trình viên bật chức năng tối ưu import tự động trong IDE, trong khi Spotless cấu hình tách nhóm static import; cùng một file liên tục bị thay đổi sau mỗi lần lưu.
Project Java hỗn hợp unit test và integration test đặt source trong các thư mục riêng; kiểm tra Spotless chỉ bao phủ mã production nên các file kiểm thử trôi dần khỏi quy ước chung.
Trong một nhánh sửa lỗi khẩn cấp, lập trình viên chỉ sửa một dòng Java nhưng công cụ formatter thay đổi hàng trăm dòng trong các file cũ, khiến reviewer khó nhận ra bản sửa cần đánh giá.
Team áp dụng Spotless trên kho mã hàng nghìn file và nhận thấy bước kiểm tra định dạng trong CI tăng đáng kể thời gian build, đặc biệt ở job chỉ thay đổi tài liệu.
Một dự án Maven chạy Spotless Apply trước khi đóng gói artifact, trong khi hệ thống CI kiểm tra trạng thái working tree sạch; quy trình release xuất hiện file Java đã được chỉnh nhưng chưa commit.
Trong một monorepo, module cũ dùng Eclipse formatter còn module mới dùng Google Java Format; thay đổi cấu hình chung ở parent build dẫn đến hàng loạt diff ngoài phạm vi tính năng.
Nhóm viết JavaDoc cho API công khai thấy nội dung chú thích bị ngắt dòng khác nhau giữa IDE và Spotless, làm bản diff tài liệu khó đọc và khó review.
Một thành viên chạy Spotless Apply khi đang có chỉnh sửa chưa stage ở file Java, rồi phát hiện các thay đổi format trộn lẫn với những phần chức năng họ định commit riêng.
CI chạy trên Linux phát hiện sai khác dấu xuống dòng ở các file Java vừa được chỉnh trên Windows, dù người viết không thấy vấn đề trong trình soạn thảo.
Một repository có quy định EditorConfig cho tab và khoảng trắng, nhưng cấu hình Spotless lại áp dụng quy tắc thụt dòng khác; lập trình viên liên tục thấy file thay đổi giữa các công cụ.
Dự án Gradle sử dụng plugin Spotless ở những phiên bản khác nhau giữa các module độc lập, khiến một file được di chuyển từ module này sang module khác tạo ra diff định dạng.
Trong bản vá do bot cập nhật dependency gửi lên, Spotless Check thất bại vì một file Java không có dấu xuống dòng cuối file; nhóm cần xác định nguồn tạo file và phạm vi trách nhiệm.
Một đội muốn chỉ kiểm tra các file Java thay đổi trong pull request để tiết kiệm thời gian, nhưng cấu hình hiện tại vẫn áp dụng trên mọi file và báo lỗi từ các file legacy chưa chuẩn hóa.
Nhóm cấu hình bỏ qua toàn bộ thư mục test fixtures để tránh file sinh tự động, nhưng trong cùng thư mục có các helper Java do lập trình viên viết thủ công cần được review.
Một lập trình viên cố dùng Spotless để định dạng file Java đang có lỗi cú pháp do merge conflict chưa giải quyết, khiến nhiệm vụ format dừng trước các bước kiểm tra khác.
Repository Java có cấu hình Gradle wrapper nhưng các developer chạy bản Gradle hệ thống khác nhau; có máy thực thi task Spotless thành công, có máy không nhận diện được cấu hình.
Một team chuyển quy tắc import từ thứ tự bảng chữ cái sang thứ tự nhóm do tổ chức quy định, trong khi các thư viện có tên package gần giống nhau gây tranh luận về thứ tự chuẩn.
Trong pipeline pull request, bước kiểm tra định dạng chỉ chạy sau toàn bộ test tích hợp kéo dài; lỗi Spotless thường được thông báo muộn dù chỉ liên quan tới một file Java.
Nhóm đang chuẩn hóa định dạng dự án Java lâu năm, nhưng một pull request áp dụng Spotless toàn kho khiến lịch sử blame của nhiều file khó theo dõi khi điều tra lỗi sản xuất.
Một đội dùng IntelliJ IDEA và VS Code cùng phát triển ứng dụng Java; thành viên mới không biết cách kiểm tra định dạng trước khi push nên thường chỉ phát hiện lỗi ở CI.
