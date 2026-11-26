Bạn sẽ giải thích mục tiêu của Domain-Driven Design và những dấu hiệu nào cho thấy một hệ thống có độ phức tạp nghiệp vụ đáng để áp dụng?
Khi bắt đầu một miền nghiệp vụ chưa quen thuộc, bạn sẽ khai thác kiến thức của chuyên gia bằng những câu hỏi nào?
Bạn sẽ xây dựng ubiquitous language để chuyên gia và lập trình viên dùng cùng một thuật ngữ trong hội thoại, tài liệu và mã nguồn ra sao?
Nếu hai phòng ban dùng cùng từ nhưng hiểu khác nhau, bạn sẽ phát hiện sự khác biệt về ngữ nghĩa như thế nào?
Bạn sẽ nhận biết một quy tắc nghiệp vụ cốt lõi so với một chi tiết thao tác giao diện hoặc lưu trữ bằng tiêu chí nào?
Bạn sẽ sử dụng ví dụ thực tế và các trường hợp ngoại lệ để kiểm chứng mô hình miền ban đầu như thế nào?
Bạn sẽ tổ chức một buổi khám phá luồng sự kiện nghiệp vụ để tìm ra khái niệm và quy tắc bị bỏ sót ra sao?
Bạn sẽ phân biệt core domain, supporting subdomain và generic subdomain dựa trên giá trị cạnh tranh và tính đặc thù như thế nào?
Khi nguồn lực phát triển hạn chế, bạn sẽ ưu tiên đầu tư mô hình sâu vào subdomain nào và vì sao?
Bạn sẽ xác định ranh giới một bounded context dựa trên ngôn ngữ, quy tắc và quyền sở hữu mô hình như thế nào?
Nếu một khái niệm Khách hàng có ý nghĩa khác nhau trong Bán hàng và Hỗ trợ, bạn sẽ mô hình hóa hai bounded context ra sao?
Vì sao một bounded context không nhất thiết tương ứng một microservice hoặc một cơ sở dữ liệu riêng?
Bạn sẽ quyết định khi nào nên tách một bounded context đang quá lớn và đâu là dấu hiệu tách sai ranh giới?
Bạn sẽ xây dựng context map để biểu diễn quan hệ phụ thuộc giữa các nhóm và các bounded context như thế nào?
Khi một đội cung cấp dữ liệu cho nhiều đội khác, bạn sẽ xác định quan hệ upstream và downstream trong context map ra sao?
Bạn sẽ so sánh shared kernel, customer-supplier và conformist theo mức độ phối hợp cần thiết giữa các nhóm như thế nào?
Bạn sẽ sử dụng anti-corruption layer để ngăn mô hình từ hệ thống cũ làm sai lệch ngôn ngữ miền mới ra sao?
Khi hai bounded context trao đổi sự kiện, bạn sẽ quyết định trường dữ liệu và thuật ngữ nào thuộc hợp đồng tích hợp như thế nào?
Bạn sẽ phân biệt tích hợp qua dữ liệu dùng chung với tích hợp qua API hoặc sự kiện về nguy cơ rò rỉ mô hình ra sao?
Khi ranh giới tổ chức và ranh giới mô hình không trùng nhau, bạn sẽ xử lý các điểm giao trách nhiệm như thế nào?
Bạn sẽ phân biệt entity với value object dựa trên danh tính và tính thay thế được qua một ví dụ nghiệp vụ nào?
Bạn sẽ thiết kế value object Tiền tệ hoặc Địa chỉ để giữ bất biến và tránh tình trạng đối tượng thiếu hợp lệ ra sao?
Khi một entity thay đổi thuộc tính nhưng vẫn là cùng một đối tượng miền, bạn sẽ giải thích vai trò của định danh như thế nào?
Bạn sẽ xác định những thuộc tính nào cần xuất hiện trong mô hình miền thay vì phản chiếu toàn bộ cột của bảng dữ liệu?
Bạn sẽ chọn aggregate boundary theo những bất biến nào cần được bảo vệ trong cùng một giao dịch?
Nếu một đơn hàng chứa nhiều dòng hàng, bạn sẽ quyết định điều gì được phép thay đổi thông qua aggregate root ra sao?
Bạn sẽ bảo đảm code bên ngoài không sửa trực tiếp trạng thái của entity con để phá vỡ bất biến aggregate như thế nào?
Khi hai aggregate cần phối hợp để hoàn thành quy trình, bạn sẽ chọn nhất quán tức thời hay cuối cùng dựa trên điều kiện nào?
Bạn sẽ phân tích vì sao aggregate quá lớn có thể gây tranh chấp ghi và làm giảm khả năng mở rộng như thế nào?
Bạn sẽ phân tích hậu quả khi chia aggregate quá nhỏ khiến bất biến nghiệp vụ cần bảo vệ bị tách rời ra sao?
Khi nhiều yêu cầu đồng thời sửa cùng một aggregate, bạn sẽ sử dụng phiên bản hoặc khóa để bảo vệ tính nhất quán như thế nào?
Bạn sẽ phân biệt hành vi nghiệp vụ nằm trong entity với logic điều phối của application service như thế nào?
Khi một quy tắc miền không thuộc tự nhiên về một entity hoặc value object, bạn sẽ thiết kế domain service ra sao?
Bạn sẽ nhận biết mô hình miền thiếu hành vi và chỉ chứa getter, setter bằng những dấu hiệu nào?
Bạn sẽ thiết kế một phương thức miền như xác nhận đơn hàng để diễn đạt ý định nghiệp vụ thay vì chỉ gán trạng thái như thế nào?
Bạn sẽ xác định lúc nào cần factory để tạo aggregate hợp lệ và khi nào constructor thông thường là đủ?
Bạn sẽ giải thích vai trò của repository trong việc truy xuất aggregate mà không đưa chi tiết cơ sở dữ liệu vào mô hình như thế nào?
Bạn sẽ thiết kế hợp đồng repository theo nhu cầu của miền mà không để nó biến thành API truy vấn tổng quát quá mức ra sao?
Khi thiết kế domain event, bạn sẽ phân biệt sự kiện đã xảy ra với câu lệnh yêu cầu thực hiện hành động như thế nào?
Bạn sẽ quyết định thời điểm tạo và công bố domain event so với thời điểm transaction commit như thế nào?
Bạn sẽ đặt tên và payload domain event sao cho biểu đạt ngữ nghĩa nghiệp vụ mà không làm lộ cấu trúc lưu trữ nội bộ ra sao?
Khi một sự kiện miền được xử lý lặp lại ở bounded context khác, bạn sẽ bảo vệ tác động nghiệp vụ bằng cách nào?
Bạn sẽ phân biệt domain event trong nội bộ một bounded context với integration event dùng để liên lạc ra bên ngoài ra sao?
Bạn sẽ tổ chức kiểm thử entity và aggregate để xác minh bất biến cùng các chuyển trạng thái không hợp lệ như thế nào?
Bạn sẽ xây dựng bài kiểm thử ứng dụng để bảo đảm application service gọi đúng repository và domain service mà không kiểm thử chi tiết hạ tầng ra sao?
Khi một quy tắc nghiệp vụ đổi nghĩa, bạn sẽ tìm các nơi có mô hình hoặc hợp đồng bị ảnh hưởng bằng cách nào?
Bạn sẽ lập kế hoạch chuyển một hệ thống có bảng dữ liệu dùng chung sang các bounded context mà vẫn giữ hoạt động liên tục như thế nào?
Bạn sẽ lựa chọn cách xử lý sự khác biệt giữa mô hình miền và mô hình persistence để tránh ràng buộc DDD vào ORM như thế nào?
Bạn sẽ đánh giá hiệu quả DDD qua tốc độ trao đổi với chuyên gia, mức độ rõ của bất biến và tần suất sai lệch ngữ nghĩa như thế nào?
Khi việc chia bounded context gây nhiều trao đổi qua mạng và công việc đồng bộ dữ liệu, bạn sẽ đánh giá lại ranh giới và mức độ phức tạp như thế nào?
