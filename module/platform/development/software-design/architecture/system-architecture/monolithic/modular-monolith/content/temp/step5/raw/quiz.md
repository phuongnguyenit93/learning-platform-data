1. Đặc trưng cốt lõi của Modular Monolith so với microservices là gì?
A. Mỗi module được phát hành thành một dịch vụ chạy riêng
B. Mỗi module buộc sử dụng cơ sở dữ liệu vật lý khác nhau
C. Một artifact triển khai nhưng có nhiều module nghiệp vụ
D. Mỗi thao tác nghiệp vụ đều phải đi qua message broker
Đáp án đúng: C

2. Vì sao một ứng dụng monolith lớn chưa chắc là Modular Monolith?
A. Vì monolith luôn phải chạy trong một tiến trình duy nhất
B. Vì monolith không được phép sử dụng một module Java
C. Có thể thiếu ranh giới và hợp đồng giữa các module
D. Vì monolith không thể có transaction trong cơ sở dữ liệu
Đáp án đúng: C

3. Khi xác định ranh giới module, tiêu chí nào nên ưu tiên?
A. Chỉ số class trong mỗi package và số file source
B. Năng lực nghiệp vụ với quy tắc và vòng đời chung
C. Số endpoint HTTP và số trang của một giao diện
D. Tên bảng database và thứ tự tạo migration
Đáp án đúng: B

4. Hợp đồng công khai của một module nên gồm những gì?
A. Toàn bộ repository, entity và bảng dữ liệu nội bộ
B. Mọi lớp triển khai và hàm private của module
C. API nghiệp vụ cùng kiểu dữ liệu cần trao đổi
D. Đường dẫn file cấu hình môi trường của module
Đáp án đúng: C

5. Vì sao module Đơn hàng không nên gọi thẳng repository của module Thanh toán?
A. Lộ chi tiết lưu trữ và tăng phụ thuộc giữa hai module
B. Giúp tận dụng giao dịch chung mà không cần phân quyền
C. Tự động nâng hiệu năng khi hai module cùng database
D. Đảm bảo không còn dependency giữa hai module
Đáp án đúng: A

6. Khi module A cần dữ liệu do module B sở hữu, cách truy cập nào phù hợp?
A. Gọi interface công khai do module B cung cấp
B. Truy vấn trực tiếp bảng B và sửa dữ liệu khi cần
C. Đọc thẳng entity B và giữ tham chiếu lâu dài
D. Sao chép mọi repository của B sang module A
Đáp án đúng: A

7. Vì sao chia sẻ cùng entity mutable giữa nhiều module là rủi ro?
A. Mọi module bắt buộc triển khai cùng ngôn ngữ Java
B. Mọi bảng sẽ tự động được chuyển sang schema khác
C. Khi đó không thể viết unit test cho một module
D. Các module có thể phụ thuộc invariant của nhau
Đáp án đúng: D

8. Trong Modular Monolith, shared kernel nên được giới hạn như thế nào?
A. Đưa mọi entity nghiệp vụ vào một gói dùng chung
B. Đưa toàn bộ quyền ghi của các module về kernel
C. Giữ nhỏ và ổn định để tránh lan truyền thay đổi
D. Chuyển mọi use case sang shared package để tiện dùng
Đáp án đúng: C

9. Chu trình phụ thuộc `Orders → Billing → Orders` thường gây vấn đề gì?
A. Giúp phân tách ownership của hai module rõ hơn
B. Làm khó thay đổi và kiểm tra module độc lập
C. Cho phép module Billing bỏ qua API của Orders
D. Tự động bảo đảm build graph luôn có thể tách rời
Đáp án đúng: B

10. Architecture test trong modular monolith nên kiểm tra điều gì?
A. Chỉ đếm thời gian compile của ứng dụng trong IDE
B. Chỉ xác nhận mọi class đều có tên giống tên bảng
C. Chỉ kiểm tra số thread của runtime monolith
D. Cấm truy cập package nội bộ của module khác
Đáp án đúng: D

11. Để ranh giới module không chỉ tồn tại trong tài liệu, nên dùng gì?
A. Chỉ đặt tên package dài hơn và bỏ mọi kiểm tra
B. Kiểm soát visibility, dependency và test kiến trúc
C. Chỉ tạo sơ đồ UML rồi cho các module import tùy ý
D. Chỉ dùng chung một thư mục source cho mọi module
Đáp án đúng: B

12. Modular Monolith có bắt buộc mỗi module phải có database riêng không?
A. Không; có thể chung DB với ownership dữ liệu rõ
B. Có; mỗi module luôn phải chạy một DBMS riêng biệt
C. Có; dùng chung DB khiến không thể dùng module boundary
D. Không; vì tất cả module phải dùng chung bảng nghiệp vụ
Đáp án đúng: A

13. Lợi thế giao dịch của modular monolith khi dùng chung database là gì?
A. Mọi thao tác giữa module bắt buộc xử lý qua Saga
B. Mọi transaction mặc nhiên bao trùm cả hệ thống phân tán
C. Không thể rollback thay đổi từ hai module cùng lúc
D. Có thể phối hợp một transaction ACID khi thật sự cần
Đáp án đúng: D

14. Vì sao không nên lạm dụng transaction chạy qua quá nhiều module?
A. Giảm đáng kể việc dùng chung schema trong database
B. Bảo đảm mọi module được triển khai độc lập ngay
C. Tăng coupling và mở rộng phạm vi khóa, lỗi giao dịch
D. Tự động chuyển mọi lời gọi module thành event
Đáp án đúng: C

15. Giao tiếp trực tiếp trong cùng tiến trình có ưu thế nào so với HTTP?
A. Bảo đảm các module không có bất kỳ phụ thuộc nào
B. Cho phép triển khai riêng từng module mà không restart
C. Đảm bảo mọi lời gọi đều bất đồng bộ và không thể lỗi
D. Giảm chi phí mạng và serialization giữa các module
Đáp án đúng: D

16. Khi dùng event nội bộ để giảm coupling, yếu tố nào cần xác định?
A. Tên chủ đề Kafka cho mọi event nội bộ trong bộ nhớ
B. Thời điểm xử lý và cam kết nhất quán giữa các module
C. Mỗi event luôn tạo một transaction phân tán mới
D. Event nội bộ luôn có bảo đảm exactly-once mặc định
Đáp án đúng: B

17. Vì sao phát event ra hệ ngoài trước commit database có thể gây lỗi?
A. Làm module không thể biên dịch nếu thiếu DTO tương ứng
B. Bắt controller tạo lại toàn bộ aggregate trong source
C. Consumer thấy sự kiện dù transaction nguồn bị rollback
D. Vì event chắc chắn được broker xử lý đồng bộ tức thì
Đáp án đúng: C

18. Khi quy trình nhiều module cần điều phối theo thứ tự, giải pháp nào dễ kiểm soát?
A. Application service gọi các API module theo use case
B. Cho mọi module ghi trực tiếp trạng thái của module khác
C. Đặt mọi quy tắc phối hợp trong UI của người dùng
D. Chỉ tạo bảng join chung rồi bỏ kiểm tra trạng thái
Đáp án đúng: A

19. Kiểm thử tích hợp giữa module nên tập trung vào điều gì?
A. Chỉ đo kích thước artifact JAR sau khi đóng gói
B. Hợp đồng API và invariant tại ranh giới phối hợp
C. Chỉ so tên class controller ở hai module khác nhau
D. Chỉ kiểm tra số lượng method trong mỗi repository
Đáp án đúng: B

20. Modular Monolith giúp các nhóm phát triển độc lập tới mức nào?
A. Tự chủ mã nhưng vẫn theo nhịp triển khai chung
B. Mỗi nhóm luôn phát hành độc lập không ảnh hưởng bản khác
C. Mỗi nhóm bắt buộc sở hữu một cluster Kubernetes riêng
D. Mỗi nhóm có thể thay schema của mọi module tùy ý
Đáp án đúng: A

21. Về mở rộng hạ tầng, giới hạn phổ biến của modular monolith là gì?
A. Từng module luôn có thể scale riêng ngay lập tức
B. Các module thường scale cùng artifact triển khai
C. Không thể mở rộng ngang khi số lượng request tăng
D. Mọi module đều buộc dùng một CPU vật lý duy nhất
Đáp án đúng: B

22. Khi nào việc tách một module thành microservice đáng cân nhắc?
A. Khi module có hơn một class domain trong package
B. Khi muốn bỏ hoàn toàn mọi hợp đồng giữa các module
C. Khi nhiều module vẫn dùng chung mọi bảng và invariant
D. Khi cần triển khai riêng và ranh giới đã đủ ổn định
Đáp án đúng: D

23. Trước khi tách một module ra khỏi monolith, điều gì cần được làm rõ?
A. Chỉ độ dài tên package ở phần source code
B. Chỉ số lượng icon hiển thị trong màn hình sản phẩm
C. Chỉ mức độ quen thuộc với Docker của một thành viên
D. Ownership dữ liệu, API và phụ thuộc vượt ranh giới
Đáp án đúng: D

24. Lợi ích của kiểm thử kiến trúc liên tục trong CI là gì?
A. Phát hiện import trái chiều và xói mòn ranh giới sớm
B. Chỉ kiểm tra tốc độ build nhanh hơn phiên trước
C. Chỉ xác nhận ứng dụng đáp ứng p99 khi không có tải
D. Bảo đảm không còn lỗi nghiệp vụ dù không chạy test
Đáp án đúng: A
