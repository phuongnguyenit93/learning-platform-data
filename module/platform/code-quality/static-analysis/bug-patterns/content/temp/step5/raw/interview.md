Bạn giải thích phân tích tĩnh nhận diện mẫu lỗi tiềm ẩn trong mã Java khác với biên dịch và kiểm thử động như thế nào?
Những loại lỗi nào thường có thể được phát hiện sớm bằng công cụ phân tích tĩnh mà code review dễ bỏ sót?
Bạn sẽ lần theo luồng điều khiển và dữ liệu để đánh giá một cảnh báo null dereference như thế nào?
Khi một tham số có thể nhận null nhưng hợp đồng API chưa rõ, bạn sẽ xác minh và làm rõ hợp đồng ra sao?
Bạn sẽ sử dụng thông tin về khả năng null của giá trị trả về để ngăn lỗi tại các điểm gọi như thế nào?
Bạn sẽ quyết định khi nào cần kiểm tra null, khi nào cần thay đổi hợp đồng API và khi nào nên điều chỉnh mô hình dữ liệu ra sao?
Nếu công cụ báo lỗi null dù lập trình viên tin rằng nhánh đó không thể xảy ra, bạn sẽ kiểm chứng giả định bằng cách nào?
Bạn sẽ nhận diện những sai sót liên quan đến hợp đồng equals và hashCode trong các lớp Java ra sao?
Khi đối tượng thay đổi trạng thái sau khi được dùng làm khóa trong collection, bạn sẽ phân tích rủi ro như thế nào?
Bạn sẽ điều tra một cảnh báo về việc bỏ qua giá trị trả về của phương thức bằng những bước nào?
Những lỗi nào có thể xuất hiện khi so sánh sai kiểu giá trị hoặc sử dụng sai hợp đồng của API thư viện Java?
Bạn sẽ nhận ra một ngoại lệ bị nuốt hoặc bị xử lý theo cách che giấu lỗi thật bằng cách nào?
Khi phương thức tạo tài nguyên I/O rồi gặp ngoại lệ ở giữa, bạn sẽ kiểm tra nguy cơ rò rỉ tài nguyên ra sao?
Bạn sẽ lựa chọn cách quản lý vòng đời tài nguyên như stream, socket hoặc kết nối dữ liệu theo tiêu chí nào?
Bạn sẽ đánh giá một cảnh báo tài nguyên chưa đóng khi quyền sở hữu tài nguyên được chuyển sang hàm khác như thế nào?
Khi nhiều luồng cùng cập nhật một biến chia sẻ, bạn sẽ xác định nguy cơ race condition ra sao?
Bạn sẽ phân biệt tính nguyên tử và khả năng nhìn thấy thay đổi giữa các luồng trong mã Java như thế nào?
Bạn sẽ kiểm tra đoạn mã dùng khóa đồng bộ có nguy cơ deadlock hay thứ tự khóa bất nhất bằng cách nào?
Khi mã sử dụng collection từ nhiều luồng, bạn sẽ đánh giá giả định về thread safety như thế nào?
Bạn sẽ tìm hiểu một tác vụ nền không dừng hoặc executor không được đóng đúng cách theo các hướng nào?
Bạn sẽ xác định khả năng overflow trong phép tính với kiểu số nguyên và tác động nghiệp vụ của nó ra sao?
Khi logic tài chính sử dụng số thực dấu phẩy động, bạn sẽ phân tích rủi ro sai số và lựa chọn cách sửa thế nào?
Bạn sẽ đánh giá những lỗi có thể xảy ra trong phép chia, ép kiểu và chuyển đổi đơn vị ở một đoạn tính toán như thế nào?
Khi mã xử lý thời gian và múi giờ cho dữ liệu người dùng, bạn sẽ tìm các giả định có thể gây lỗi ra sao?
Bạn sẽ xác minh cảnh báo liên quan đến chỉ số mảng, điều kiện biên hoặc vòng lặp tránh kết luận vội như thế nào?
Bạn sẽ nhận diện nguy cơ đưa dữ liệu không tin cậy vào câu truy vấn hoặc lệnh hệ thống từ cảnh báo phân tích tĩnh ra sao?
Khi ứng dụng xây dựng đường dẫn tệp từ đầu vào người dùng, bạn sẽ đánh giá khả năng truy cập ngoài thư mục cho phép như thế nào?
Bạn sẽ xem xét việc sử dụng bộ sinh số ngẫu nhiên cho chức năng bảo mật dựa trên những yêu cầu gì?
Khi cảnh báo liên quan đến dữ liệu nhạy cảm được ghi log, bạn sẽ xác minh mức độ lộ lọt và phương án sửa ra sao?
Bạn sẽ so sánh cách SpotBugs, Error Prone và PMD tiếp cận phát hiện mẫu lỗi để chọn công cụ phù hợp thế nào?
Bạn sẽ thiết lập việc chạy phân tích tĩnh trong dự án dùng Maven hoặc Gradle sao cho kết quả tái lập được ra sao?
Bạn sẽ chọn tập quy tắc phân tích tĩnh ban đầu như thế nào để tập trung vào rủi ro lớn và giảm nhiễu?
Bạn sẽ đọc một cảnh báo phân tích tĩnh gồm vị trí, đường suy luận và mức độ nghiêm trọng theo trình tự nào?
Bạn sẽ phân biệt cảnh báo nguy hiểm thực sự, cảnh báo sai và cảnh báo chỉ phản ánh sở thích phong cách bằng cách nào?
Khi chưa thể tái hiện lỗi mà công cụ cảnh báo, bạn sẽ thu thập thêm bằng chứng nào trước khi sửa mã?
Bạn sẽ ưu tiên sửa các cảnh báo dựa trên khả năng xảy ra lỗi, hậu quả và phạm vi ảnh hưởng như thế nào?
Bạn sẽ thiết kế bài kiểm thử hồi quy để chứng minh một bản sửa cho lỗi được phát hiện tĩnh thực sự giải quyết vấn đề ra sao?
Khi bản sửa làm cảnh báo biến mất nhưng có nguy cơ thay đổi hành vi chương trình, bạn sẽ kiểm chứng thêm điều gì?
Bạn sẽ quyết định trường hợp nào được phép tắt một quy tắc hoặc suppress một cảnh báo, và ghi lý do thế nào?
Bạn sẽ theo dõi các cảnh báo đã được chấp nhận tạm thời để chúng không bị bỏ quên qua nhiều bản phát hành ra sao?
Khi đưa phân tích tĩnh vào repository cũ có rất nhiều cảnh báo, bạn sẽ xây dựng baseline và quy tắc ngăn lỗi mới thế nào?
Bạn sẽ tích hợp kết quả phân tích tĩnh vào CI và pull request để người viết mã nhận phản hồi đủ sớm ra sao?
Bạn sẽ xử lý trường hợp kết quả phân tích tĩnh khác nhau giữa máy lập trình viên và CI theo những bước nào?
Bạn sẽ điều chỉnh phạm vi phân tích đối với mã sinh tự động, mã kiểm thử hoặc thư viện bên thứ ba như thế nào?
Bạn sẽ đánh giá hiệu quả của công cụ phân tích tĩnh thông qua tỷ lệ cảnh báo hữu ích, lỗi lọt và thời gian xử lý ra sao?
Nếu công cụ mới cập nhật tạo ra hàng loạt cảnh báo, bạn sẽ phân loại, kiểm chứng và triển khai thay đổi quy tắc như thế nào?
Khi có cảnh báo bảo mật nghiêm trọng ngay trước thời điểm phát hành, bạn sẽ phối hợp xác minh và quyết định xử lý theo tiêu chí nào?
