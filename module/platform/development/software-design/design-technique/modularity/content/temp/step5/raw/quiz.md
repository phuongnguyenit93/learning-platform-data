Câu 1. Khi phân chia ứng dụng thành module, tiêu chí nào giúp ranh giới phản ánh trách nhiệm rõ ràng?
A. Gom các lớp theo độ dài của tên package
B. Gom chức năng cùng năng lực nghiệp vụ và quy tắc
C. Tách một module mới cho từng phương thức Java
D. Gom tất cả lớp có cùng annotation trong một module
Đáp án đúng: B

Câu 2. High cohesion trong module thể hiện qua đặc điểm nào?
A. Module import nhiều dependency từ các phần khác
B. Module chứa các phần không liên quan để tái dùng
C. Module có nhiều public class nhất trong hệ thống
D. Các phần cùng phục vụ một trách nhiệm chính
Đáp án đúng: D

Câu 3. Low coupling giữa các module thường có nghĩa gì?
A. Các module có thể trực tiếp sửa state private của nhau
B. Mọi module đều truy cập chung một schema dữ liệu
C. Ít phụ thuộc vào chi tiết nội bộ module khác
D. Các module phải có cùng số lớp để dễ build
Đáp án đúng: C

Câu 4. Một module thanh toán muốn giấu cách gọi ngân hàng cụ thể; nên công khai phần nào?
A. Toàn bộ HTTP client và API key trong package
B. Các lớp implementation để mọi module tự tạo
C. Mọi method nội bộ để consumer có nhiều lựa chọn
D. Hợp đồng nghiệp vụ ổn định cho consumer dùng
Đáp án đúng: D

Câu 5. Tại sao phụ thuộc vòng giữa module A và B gây khó khăn cho hệ thống?
A. Vòng phụ thuộc luôn làm ứng dụng chậm gấp đôi
B. Compiler Java không bao giờ hỗ trợ nhiều module
C. Khó build và đổi module độc lập khi nối vòng
D. Mọi vòng phụ thuộc đều buộc chia một JVM thread
Đáp án đúng: C

Câu 6. Module domain cần dữ liệu từ lưu trữ nhưng không muốn phụ thuộc adapter SQL; hướng thiết kế nào phù hợp?
A. Cho domain import trực tiếp repository JDBC cụ thể
B. Domain khai báo port, hạ tầng thực thi qua adapter
C. Đưa toàn bộ truy vấn SQL vào class nghiệp vụ domain
D. Cho cả hai module cùng tham chiếu package của nhau
Đáp án đúng: B

Câu 7. Trong JPMS, directive nào dùng để công khai package cho module khác truy cập thông thường?
A. opens package cho phép gọi public type lúc compile
B. requires package để mở lớp private cho module khác
C. exports package để công khai các public type
D. uses package để xuất toàn bộ type qua module path
Đáp án đúng: C

Câu 8. Trong module Java có `requires com.example.core;`, ý nghĩa chính của khai báo là gì?
A. Cung cấp implementation service cho module khác
B. Mở mọi package nội bộ để reflection tùy ý
C. Tự tạo instance của mọi public class trong core
D. Cho phép module đọc module com.example.core
Đáp án đúng: D

Câu 9. Một framework cần reflection vào package domain nhưng không cần xuất API compile-time; directive JPMS nào phù hợp?
A. opens package theo phạm vi reflection cần thiết
B. exports package để mọi private field đều truy cập được
C. requires transitive package để mở toàn bộ lớp private
D. provides package để tự động cấp quyền reflection
Đáp án đúng: A

Câu 10. Trong JPMS, `requires transitive M;` có tác động gì cho module phụ thuộc module hiện tại?
A. Module đọc module hiện tại cũng đọc được M
B. Chỉ cho phép phản xạ tới các trường private của M
C. Tự nhân bản toàn bộ package của M vào module hiện tại
D. Tự chuyển mọi dependency của M sang runtime-only
Đáp án đúng: A

Câu 11. Để tích hợp service provider qua JPMS ServiceLoader, cách khai báo nào thường đúng?
A. Consumer khai báo provides; provider khai báo opens
B. Consumer dùng uses, provider dùng provides ... with
C. Cả hai module chỉ cần khai báo exports cùng package
D. Consumer khai báo requires transitive thay cho uses
Đáp án đúng: B

Câu 12. Ứng dụng Spring có nhiều package và component scanning; nhận định nào đúng về ranh giới module?
A. Component scanning tự chặn mọi tham chiếu giữa module
B. Mọi bean của Spring bắt buộc nằm trong cùng package
C. Scan bean không tự áp đặt ranh giới kiến trúc
D. Tất cả module Spring bắt buộc là JPMS module
Đáp án đúng: C

Câu 13. Với dự án Gradle đa module, cấu hình dependency `implementation` thường hữu ích ở đâu?
A. Ẩn dependency khỏi compile classpath của consumer
B. Buộc mọi API của module được xuất qua JPMS exports
C. Tự động tạo REST endpoint cho module có phụ thuộc
D. Xóa hoàn toàn các dependency bắc cầu ở runtime
Đáp án đúng: A

Câu 14. Nhóm muốn ngăn presentation module import thẳng persistence adapter; kiểm thử nào phù hợp?
A. Test đo thời gian phản hồi API theo từng request
B. Test so kích thước artifact build trước và sau
C. Test kiến trúc chặn phụ thuộc sai ranh giới
D. Unit test chỉ xác nhận JSON field trả đúng kiểu
Đáp án đúng: C

Câu 15. Khi nào nên cân nhắc tách một module lớn thành hai module?
A. Khi module có số file Java vượt một ngưỡng cố định
B. Khi cần deploy mọi thay đổi thành microservice riêng
C. Khi hai phần dùng cùng một bảng database tạm thời
D. Khi hai phần có nhịp thay đổi tương đối riêng
Đáp án đúng: D

Câu 16. Một module A và B nhỏ nhưng thay đổi cùng nhau, chia sẻ hầu hết invariant; hướng nào hợp lý?
A. Luôn chuyển A và B sang hai service deploy riêng
B. Cân nhắc gộp vì invariant và thay đổi gắn chặt
C. Thêm tầng facade giữa mọi class của A và B
D. Nhân bản toàn bộ model giữa hai module để tách
Đáp án đúng: B

Câu 17. Một module có 30 public class nhưng consumer chỉ cần ba thao tác; cải tiến nào đáng xem xét?
A. Đưa toàn bộ class ra package công khai để dễ debug
B. Tạo facade/API nhỏ, giấu implementation chi tiết
C. Bắt consumer dùng reflection để gọi method nội bộ
D. Gộp các consumer thành một package duy nhất
Đáp án đúng: B

Câu 18. Khi thay đổi public API của module đang có nhiều consumer, bước nào giảm lỗi tương thích?
A. Review breaking change với consumer liên quan
B. Chỉ build riêng module cung cấp, không build consumer
C. Đổi toàn bộ tên class thành dạng ngắn hơn
D. Chuyển mọi method public sang private ngay lập tức
Đáp án đúng: A

Câu 19. Bộ test module theo hợp đồng public API có lợi ích gì khi thay implementation?
A. Kiểm tra hành vi public dù đổi implementation
B. Bắt consumer luôn kết nối tới cùng database thực tế
C. Kiểm tra trực tiếp tất cả field private được đánh dấu
D. Đảm bảo mọi module dùng chung framework test giống nhau
Đáp án đúng: A

Câu 20. Hai module giao tiếp qua event bất đồng bộ; đổi lại giảm gọi trực tiếp, cần quản lý thêm gì?
A. Không cần versioning vì thông điệp luôn tương thích
B. Mọi bên đều được phép thay schema không thông báo
C. Hành vi nhất quán tức thời giữa các module được bảo đảm
D. Schema event, retry và tính nhất quán cuối cùng
Đáp án đúng: D

Câu 21. Nếu module nội bộ bị xuất công khai quá rộng, hệ quả dài hạn nào dễ xảy ra?
A. Các consumer sẽ tự động dùng chung một transaction
B. Số package luôn giảm sau mỗi lần build release
C. Mọi dependency trở thành optional tại compile time
D. Consumer bám vào chi tiết, làm refactor khó
Đáp án đúng: D

Câu 22. Module graph có chu kỳ A → B → C → A; biện pháp thiết kế nào phù hợp?
A. Bổ sung thêm module D phụ thuộc vào cả ba module
B. Chuyển toàn bộ public API thành static helper
C. Tách abstraction và điều chỉnh hướng phụ thuộc
D. Giữ vòng và chỉ đổi tên ba module để dễ theo dõi
Đáp án đúng: C

Câu 23. Trong dependency graph, module có rất nhiều module khác phụ thuộc vào cần được quản trị thế nào?
A. Ưu tiên API ổn định và kiểm soát tác động khi thay
B. Cho mọi consumer truy cập trực tiếp class implementation
C. Đổi public API thường xuyên để buộc các module cập nhật
D. Gộp mọi module tiêu thụ vào module lõi để đơn giản
Đáp án đúng: A

Câu 24. Khi rút một phần code từ monolith thành module riêng, bước nào giảm rủi ro thiết kế?
A. Sao chép toàn bộ package sang module mới, giữ gọi vòng
B. Xác định API, chuyển dần consumer và test phụ thuộc
C. Chặn mọi kiểm thử tích hợp để chuyển code nhanh nhất
D. Tách trước theo cấu hình build dù trách nhiệm chưa rõ
Đáp án đúng: B
