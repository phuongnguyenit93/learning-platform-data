Bạn sẽ giải thích mục tiêu của modularity khi chia một hệ thống Java thành các phần có trách nhiệm và ranh giới rõ ràng như thế nào?
Bạn sẽ xác định tiêu chí để một tập hợp lớp trở thành module có ý nghĩa thay vì chỉ là một package lớn ra sao?
Bạn sẽ dùng mức độ cohesion để đánh giá các lớp trong một module có cùng phục vụ một mục đích như thế nào?
Bạn sẽ phân biệt coupling giữa module với sự phụ thuộc hợp lý vào API công khai của module khác ra sao?
Bạn sẽ nhận diện dấu hiệu một module đang gánh quá nhiều trách nhiệm và cần xem xét tách nhỏ như thế nào?
Bạn sẽ đánh giá tình huống nhiều module quá nhỏ khiến mã tích hợp và quản lý phiên bản tăng không cần thiết ra sao?
Bạn sẽ phân chia module theo năng lực nghiệp vụ thay vì theo controller, service và repository trong trường hợp nào?
Bạn sẽ so sánh cách chia module theo tầng kỹ thuật và theo tính năng khi các nhóm phát triển thay đổi chức năng độc lập ra sao?
Bạn sẽ xác định các bất biến và dữ liệu cần thuộc cùng một module để giữ nhất quán nghiệp vụ như thế nào?
Bạn sẽ thiết kế API công khai của module sao cho chỉ bộc lộ thao tác cần thiết với consumer ra sao?
Bạn sẽ phân biệt interface công khai, implementation nội bộ và DTO dùng trao đổi dữ liệu giữa các module như thế nào?
Bạn sẽ kiểm soát việc module khác truy cập trực tiếp bảng dữ liệu hoặc lớp triển khai bên trong thay vì gọi API như thế nào?
Bạn sẽ lựa chọn dữ liệu cần chuyển qua ranh giới module để tránh chia sẻ một domain object có thể bị sửa tùy ý ra sao?
Bạn sẽ xử lý tình huống nhiều module cần cùng sử dụng một khái niệm nghiệp vụ nhưng có ý nghĩa khác nhau như thế nào?
Bạn sẽ đánh giá khi nào một thư viện dùng chung thực sự có giá trị và khi nào nó trở thành nơi gom mã thiếu liên quan ra sao?
Bạn sẽ xác định mô hình sở hữu dữ liệu để một thay đổi schema không buộc nhiều module sửa cùng lúc như thế nào?
Bạn sẽ tổ chức giao tiếp đồng bộ giữa các module mà không tạo chuỗi gọi quá sâu hoặc phụ thuộc vòng ra sao?
Bạn sẽ lựa chọn sự kiện nội bộ khi cần thông báo thay đổi giữa các module mà không buộc bên phát biết bên nhận như thế nào?
Bạn sẽ xử lý yêu cầu nghiệp vụ trải qua nhiều module và cần tính nhất quán dữ liệu theo ranh giới nào?
Bạn sẽ phân biệt phụ thuộc thời điểm biên dịch với phụ thuộc xảy ra khi chạy khi đánh giá đồ thị module như thế nào?
Bạn sẽ vẽ đồ thị phụ thuộc giữa các module để tìm mối liên hệ vòng và điểm tập trung phụ thuộc ra sao?
Bạn sẽ xử lý một chu trình phụ thuộc giữa hai module mà không chỉ di chuyển interface sang một package chung tùy tiện như thế nào?
Bạn sẽ dùng nguyên tắc dependency inversion để thay đổi chiều phụ thuộc giữa module nghiệp vụ và module hạ tầng ra sao?
Bạn sẽ xác định các phụ thuộc transitive khiến một module vô tình dùng thư viện không được khai báo trực tiếp như thế nào?
Bạn sẽ giới hạn các dependency được phép trong cấu hình Maven hoặc Gradle của từng module như thế nào?
Bạn sẽ tổ chức cấu hình build đa module để thay đổi một module không buộc biên dịch và chạy lại mọi phần không liên quan ra sao?
Bạn sẽ đánh giá ảnh hưởng của việc thay đổi API công khai lên các module consumer trước khi phát hành như thế nào?
Bạn sẽ xác định quy tắc versioning khi module được phát hành độc lập hoặc cùng phiên bản với toàn ứng dụng ra sao?
Bạn sẽ thiết kế chiến lược di chuyển API cũ sang API mới mà consumer không phải cập nhật đồng loạt như thế nào?
Bạn sẽ sử dụng Java Platform Module System để khai báo những module khác mà một module cần phụ thuộc ra sao?
Bạn sẽ phân biệt việc export một package cho consumer với việc giữ package nội bộ trong JPMS như thế nào?
Bạn sẽ giải thích khi nào JPMS cần mở package cho reflection và vì sao mở rộng quá mức có thể làm yếu tính đóng gói ra sao?
Bạn sẽ đánh giá việc dùng service provider và service consumer của Java để thay implementation mà không tạo phụ thuộc cứng như thế nào?
Bạn sẽ xử lý vấn đề hai module cùng đưa ra package trùng tên hoặc xung đột khi chuyển sang JPMS như thế nào?
Bạn sẽ cân nhắc chi phí chuyển một ứng dụng dùng classpath truyền thống sang module path dựa trên thư viện phụ thuộc như thế nào?
Bạn sẽ tổ chức Spring bean và cấu hình dependency injection để các module không phải truy cập trực tiếp lớp nội bộ của nhau ra sao?
Bạn sẽ phân biệt module logic trong ứng dụng Spring với module biên dịch và module triển khai độc lập như thế nào?
Bạn sẽ đánh giá khi nào cần tách một module trong monolith thành dịch vụ riêng và những chi phí phân tán phát sinh ra sao?
Bạn sẽ xác định các kiểm thử unit, integration và contract cần thiết để xác minh ranh giới của một module như thế nào?
Bạn sẽ viết quy tắc kiểm thử kiến trúc để chặn package nội bộ bị gọi từ module khác ra sao?
Bạn sẽ phát hiện vi phạm dependency graph trong CI mà không làm pipeline chậm quá mức như thế nào?
Bạn sẽ lựa chọn test tích hợp nào cần chạy khi API công khai của module thay đổi nhưng implementation nội bộ vẫn được che giấu ra sao?
Bạn sẽ đo số lượng phụ thuộc, chu trình và mức lan truyền thay đổi để đánh giá sức khỏe cấu trúc module như thế nào?
Bạn sẽ kiểm tra liệu việc tách module có thực sự cải thiện khả năng phát triển song song của nhiều nhóm ra sao?
Bạn sẽ xác định dấu hiệu hai module liên tục thay đổi cùng nhau và có thể nên được gộp lại như thế nào?
Bạn sẽ xử lý module có quá nhiều interface công khai chỉ để đáp ứng một consumer duy nhất như thế nào?
Bạn sẽ lập kế hoạch tách dần một ứng dụng nguyên khối thành module có ranh giới rõ mà không dừng phát triển tính năng ra sao?
Bạn sẽ bảo vệ hành vi hiện có bằng kiểm thử và các bước triển khai nhỏ khi chuyển lớp giữa các module như thế nào?
Bạn sẽ đánh giá sự khác nhau giữa ranh giới thể hiện trong sơ đồ kiến trúc và ranh giới thực tế qua import, build và runtime như thế nào?
Bạn sẽ xử lý tình huống một thay đổi nhỏ trong module dùng chung khiến hàng chục module khác phải sửa dù không có thay đổi nghiệp vụ như thế nào?
