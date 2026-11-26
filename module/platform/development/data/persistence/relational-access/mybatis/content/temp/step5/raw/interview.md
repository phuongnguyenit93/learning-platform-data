Bạn giải thích MyBatis khác Hibernate ORM và JDBC thuần về quyền kiểm soát SQL, ánh xạ dữ liệu và chi phí bảo trì như thế nào?
Bạn lựa chọn MyBatis cho một dự án Java dựa trên độ phức tạp truy vấn, kinh nghiệm nhóm và yêu cầu tối ưu ra sao?
Bạn mô tả mối quan hệ giữa SqlSessionFactory, SqlSession, mapper interface và câu SQL được thực thi như thế nào?
Bạn tổ chức XML mapper hoặc annotation mapper theo ranh giới nghiệp vụ để các câu SQL dễ tìm và bảo trì ra sao?
Bạn bảo đảm namespace và statement id trong mapper XML khớp với phương thức Java và tránh lỗi liên kết như thế nào?
Bạn thiết kế kiểu tham số đầu vào cho mapper với nhiều điều kiện tùy chọn và quyết định khi nào dùng DTO hoặc @Param ra sao?
Bạn giải thích sự khác biệt giữa cú pháp #{...} và ${...} của MyBatis và cách phòng tránh SQL injection như thế nào?
Khi người dùng được chọn cột sắp xếp hoặc tên bảng động, bạn thiết kế danh sách cho phép thay vì đưa chuỗi tùy ý vào SQL ra sao?
Bạn lựa chọn resultType hoặc resultMap khi ánh xạ một kết quả SQL về đối tượng Java như thế nào?
Bạn thiết kế resultMap cho tên cột khác tên thuộc tính và các kiểu dữ liệu không tương thích trực tiếp ra sao?
Bạn ánh xạ khóa chính và generated key từ lệnh INSERT vào đối tượng Java với MyBatis như thế nào?
Bạn xử lý giá trị SQL NULL khi ánh xạ vào kiểu nguyên thủy, wrapper và thuộc tính tùy chọn ra sao?
Bạn thiết kế TypeHandler cho enum hoặc kiểu giá trị nghiệp vụ riêng và kiểm chứng việc đọc ghi đối xứng như thế nào?
Bạn quyết định dùng constructor mapping hay setter/property mapping khi đối tượng kết quả là bất biến ra sao?
Bạn thiết kế ánh xạ association giữa hai bảng và tránh lấy nhầm dữ liệu khi nhiều cột trùng tên như thế nào?
Bạn thiết kế ánh xạ collection cho quan hệ một-nhiều và lựa chọn nested result hay nested select theo đặc điểm tải ra sao?
Bạn nhận diện vấn đề N+1 khi dùng nested select và thay đổi cách truy vấn để giảm số lượt gọi cơ sở dữ liệu như thế nào?
Bạn đánh giá rủi ro dữ liệu lặp trong JOIN khi ánh xạ nhiều collection vào một object graph ra sao?
Bạn dùng discriminator hoặc ánh xạ có điều kiện để xử lý các dạng bản ghi cùng cấu trúc bảng như thế nào?
Bạn sử dụng <if> trong SQL động để chỉ thêm điều kiện khi tham số hợp lệ mà không làm thay đổi ngữ nghĩa truy vấn ra sao?
Bạn dùng <where>, <trim> hoặc <set> để tạo câu SQL động đúng cú pháp khi nhiều nhánh điều kiện bị bỏ qua như thế nào?
Bạn sử dụng <choose>, <when> và <otherwise> để biểu diễn các nhánh lọc loại trừ lẫn nhau ra sao?
Bạn thiết kế <foreach> cho danh sách tham số IN và xử lý trường hợp danh sách rỗng hoặc rất lớn như thế nào?
Bạn dùng SQL fragments và <include> để tái sử dụng truy vấn mà vẫn tránh các mảnh ghép khó hiểu như thế nào?
Bạn thiết kế cập nhật từng phần bằng SQL động để phân biệt trường không được gửi với trường cần đặt về NULL ra sao?
Bạn xác định vị trí thực hiện logic nghiệp vụ và logic xây dựng truy vấn để mapper không trở thành tầng service thứ hai như thế nào?
Bạn tổ chức vòng đời SqlSession và đóng tài nguyên đúng lúc khi sử dụng MyBatis không thông qua Spring ra sao?
Bạn giải thích vì sao SqlSession không nên chia sẻ tùy tiện giữa các luồng và thiết kế phạm vi sử dụng an toàn như thế nào?
Bạn quản lý commit, rollback và auto-commit bằng MyBatis khi một thao tác nghiệp vụ có nhiều lệnh ghi như thế nào?
Bạn phân biệt hành vi quản lý transaction của MyBatis thuần và MyBatis tích hợp Spring như thế nào?
Bạn cấu hình Spring Boot để nhận diện mapper, DataSource và transaction manager mà không tạo phiên làm việc chồng chéo ra sao?
Khi nhiều mapper cùng tham gia một transaction Spring, bạn xác nhận chúng sử dụng đúng kết nối và ranh giới commit như thế nào?
Bạn thiết kế optimistic locking với cột version trong SQL MyBatis và xác định cập nhật xung đột ra sao?
Bạn xử lý lỗi ràng buộc, timeout hoặc deadlock từ MyBatis và phân loại trường hợp nào có thể thử lại như thế nào?
Bạn giải thích phạm vi và vòng đời của cache cấp một trong SqlSession và tác động đến kết quả truy vấn ra sao?
Bạn cân nhắc bật cache cấp hai khi ứng dụng có nhiều phiên và dữ liệu thay đổi thường xuyên như thế nào?
Bạn cấu hình và đánh giá useCache, flushCache hoặc cơ chế vô hiệu cache để tránh trả dữ liệu cũ ra sao?
Bạn phân biệt SIMPLE, REUSE và BATCH executor rồi chọn chế độ phù hợp cho khối lượng ghi như thế nào?
Bạn tổ chức batch INSERT hoặc UPDATE bằng MyBatis và phát hiện lỗi từng phần trước khi commit ra sao?
Bạn xử lý tập kết quả lớn bằng cursor hoặc ResultHandler và bảo đảm SqlSession vẫn mở trong lúc tiêu thụ dữ liệu như thế nào?
Bạn thiết kế phân trang SQL trong MyBatis dựa trên keyset hoặc offset và bảo đảm thứ tự kết quả ổn định ra sao?
Bạn xác minh hiệu quả của các tham số fetch size, timeout và executor type với driver và hệ quản trị thực tế như thế nào?
Khi MyBatis báo lỗi không tìm thấy statement hoặc mapper, bạn lần theo cấu hình quét mapper và namespace như thế nào?
Khi ánh xạ kết quả sai hoặc mất thuộc tính, bạn kiểm tra alias cột, resultMap, TypeHandler và auto-mapping ra sao?
Bạn cấu hình log câu SQL và thời gian thực thi để dễ phân tích sự cố mà không làm lộ dữ liệu nhạy cảm như thế nào?
Bạn kết hợp thông tin SQL do MyBatis thực thi với EXPLAIN của cơ sở dữ liệu để tối ưu chỉ mục ra sao?
Bạn thiết kế kiểm thử mapper trên cơ sở dữ liệu thật để xác minh câu SQL, ánh xạ kết quả và nhánh SQL động như thế nào?
Bạn xây dựng tập dữ liệu kiểm thử bao gồm giá trị NULL, bản ghi thiếu liên kết và nhiều bản ghi con để phát hiện lỗi mapping ra sao?
Bạn quản lý sự khác biệt cú pháp SQL giữa nhiều hệ quản trị và xác định phần nào của mapper phụ thuộc nhà cung cấp ra sao?
Bạn phối hợp thay đổi schema với các statement MyBatis để triển khai tương thích trong giai đoạn ứng dụng cũ và mới cùng chạy như thế nào?
Bạn áp dụng điều kiện tenant hoặc phân quyền dữ liệu cho mọi câu truy vấn MyBatis nhằm tránh bỏ sót bộ lọc như thế nào?
Bạn thiết kế soft delete và các truy vấn khôi phục dữ liệu để những record bị ẩn không vô tình xuất hiện trong kết quả ra sao?
Bạn cân nhắc sử dụng plugin/interceptor MyBatis để xử lý chức năng chung mà không làm sai SQL hoặc transaction như thế nào?
Bạn đo số truy vấn, độ trễ p95, tần suất cache hit và số kết nối sử dụng để đánh giá chất lượng truy cập MyBatis ra sao?
