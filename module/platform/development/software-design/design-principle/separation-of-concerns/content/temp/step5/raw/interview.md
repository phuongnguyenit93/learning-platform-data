Separation of Concerns giải quyết những vấn đề bảo trì nào khi một thành phần xử lý đồng thời giao diện, nghiệp vụ và dữ liệu?
Bạn phân biệt một concern với một chức năng cụ thể trong cùng hệ thống bằng những tiêu chí nào?
Khi thiết kế một ứng dụng Java từ đầu, bạn xác định ranh giới giữa trình bày, nghiệp vụ và lưu trữ như thế nào?
Bạn nhận biết dấu hiệu controller đang chứa quy tắc nghiệp vụ thông qua các thay đổi thường gặp ra sao?
Nếu một lớp vừa đọc HTTP request vừa mở kết nối database, bạn sẽ phân tích các trách nhiệm đang bị trộn lẫn như thế nào?
Bạn tổ chức đường đi của một request từ controller qua application service đến repository sao cho từng lớp có mục tiêu rõ ràng ra sao?
Bạn xác định vị trí đặt quy tắc tính chiết khấu để không phụ thuộc vào màn hình hoặc giao thức gọi như thế nào?
Khi cùng một nghiệp vụ được dùng bởi giao diện web và tác vụ chạy nền, cách phân tách concern giúp tái sử dụng ra sao?
Bạn phân biệt validation về cú pháp đầu vào với invariant nghiệp vụ cần được bảo vệ ở miền như thế nào?
Khi yêu cầu thay đổi định dạng response nhưng quy tắc nghiệp vụ giữ nguyên, bạn muốn những thành phần nào phải sửa?
Bạn thiết kế hợp đồng giữa lớp ứng dụng và lớp truy cập dữ liệu để không lộ chi tiết SQL ra sao?
Khi một API dùng DTO khác entity lưu trữ, bạn tổ chức ánh xạ và kiểm soát ranh giới dữ liệu như thế nào?
Bạn xác định mức trừu tượng phù hợp của interface repository dựa trên nhu cầu nghiệp vụ nào?
Nếu dịch vụ nghiệp vụ biết tên bảng và câu SQL cụ thể, bạn sẽ tách phụ thuộc đó từng bước như thế nào?
Bạn phân biệt dependency có thể chấp nhận với liên kết làm rò rỉ chi tiết triển khai qua ranh giới concern ra sao?
Khi sử dụng framework web, bạn tránh để annotation và kiểu dữ liệu của framework lan vào domain như thế nào?
Bạn đánh giá việc tách giao diện và nghiệp vụ chỉ bằng package so với module biên dịch độc lập ra sao?
Nếu các module phụ thuộc vòng nhau, bạn sẽ truy tìm concern bị đặt sai vị trí bằng cách nào?
Bạn thiết kế xử lý lỗi sao cho lỗi nghiệp vụ, lỗi lưu trữ và thông báo HTTP không trộn vào cùng một lớp như thế nào?
Bạn xác định nơi quản lý transaction khi một thao tác nghiệp vụ phải cập nhật nhiều repository như thế nào?
Nếu repository tự gửi email sau khi lưu dữ liệu, bạn phân tích vấn đề phân tách trách nhiệm và hướng sửa ra sao?
Bạn lựa chọn cách đưa sự kiện nghiệp vụ ra khỏi lớp lưu trữ mà vẫn bảo đảm thứ tự commit như thế nào?
Bạn phân tách cơ chế xác thực với kiểm tra quyền thực hiện hành động nghiệp vụ bằng cách nào?
Khi xử lý logging, tracing và metrics xuyên nhiều lớp, bạn áp dụng cơ chế nào để tránh lặp mã ở mọi phương thức?
Bạn phân biệt cross-cutting concern với một quy tắc nghiệp vụ đặc thù như thế nào?
Bạn cân nhắc middleware, interceptor hoặc decorator để xử lý quan tâm chung dựa trên điều kiện nào?
Khi đưa cache vào một use case, bạn giữ chính sách cache không làm thay đổi ý nghĩa của dữ liệu trả về ra sao?
Bạn thiết kế hợp đồng cho hệ thống gửi thông báo để có thể thay đổi nhà cung cấp mà không sửa domain như thế nào?
Bạn quyết định concern nào nên nằm trong cùng một module thay vì bị chia nhỏ thành nhiều lớp như thế nào?
Những dấu hiệu nào cho thấy việc phân tách quá mức đang làm tăng số lớp và chi phí điều hướng mã nguồn?
Khi giao diện cần dữ liệu tổng hợp từ nhiều nguồn, bạn phân biệt logic trình bày với điều phối use case ra sao?
Bạn xử lý trường hợp định dạng dữ liệu bên ngoài khác mô hình nghiệp vụ mà không làm méo domain như thế nào?
Bạn sử dụng adapter để cô lập thay đổi từ thư viện hoặc API bên ngoài như thế nào?
Nếu một service chứa hàng chục phương thức không liên quan, bạn nhóm chúng theo lý do thay đổi nào?
Bạn thiết kế unit test cho quy tắc nghiệp vụ mà không khởi động web server hoặc database bằng cách nào?
Khi một unit test cần mock quá nhiều dependency, bạn dùng tín hiệu đó để xem lại ranh giới concern ra sao?
Bạn lựa chọn những kiểm thử tích hợp nào để xác nhận hợp đồng giữa tầng nghiệp vụ và tầng lưu trữ?
Khi refactor một phương thức vừa parse input vừa tính toán vừa ghi database, bạn chọn thứ tự tách các bước ra sao?
Bạn bảo toàn hành vi hiện tại trong quá trình tách concern bằng các characterization test như thế nào?
Nếu mã cũ không có test, bạn lựa chọn đường tách an toàn và các điểm đo rủi ro thay đổi ra sao?
Bạn dùng sơ đồ phụ thuộc ra sao để phát hiện các module đang gọi ngược sang chi tiết hạ tầng?
Khi một tính năng mới yêu cầu thay đổi ở quá nhiều thành phần không liên quan, bạn đánh giá vấn đề ghép nối ra sao?
Bạn sẽ theo dõi số file phải sửa cho cùng một loại yêu cầu để kiểm chứng hiệu quả phân tách như thế nào?
Bạn đánh giá ảnh hưởng của một lớp mapping bổ sung đến độ trễ, độ phức tạp và khả năng bảo trì như thế nào?
Khi triển khai nhiều phiên bản API, bạn giữ logic nghiệp vụ chung nhưng tách phần biểu diễn khác nhau ra sao?
Bạn xây dựng quy tắc kiểm tra kiến trúc để ngăn domain import trực tiếp lớp web hoặc persistence như thế nào?
Nếu đội ngũ chia theo frontend, backend và dữ liệu, bạn phối hợp quyền sở hữu concern với ranh giới nghiệp vụ ra sao?
Bạn xử lý yêu cầu cần thay đổi đồng thời cả UI và quy tắc nghiệp vụ mà vẫn giữ hợp đồng giữa hai phía như thế nào?
Khi một thư viện utility dùng chung trở nên phụ thuộc mọi tầng, bạn đánh giá lại trách nhiệm của nó ra sao?
Bạn chọn những bằng chứng nào để kết luận việc áp dụng Separation of Concerns đã giảm rủi ro thay đổi thay vì chỉ tăng số lượng lớp?
