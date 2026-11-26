Bạn sẽ mô tả cấu trúc cơ bản của một tài liệu XML hợp lệ và phân biệt well-formed với schema-valid như thế nào?
Khi thiết kế XML trao đổi dữ liệu, bạn sẽ lựa chọn phần tử hay thuộc tính để biểu diễn một thông tin dựa trên tiêu chí nào?
Bạn sẽ phân biệt phần tử gốc, phần tử con, nội dung văn bản và thuộc tính trong một tài liệu có cấu trúc lồng nhau ra sao?
Khi dữ liệu chứa ký tự đặc biệt, bạn sẽ xác định trường hợp cần escape và trường hợp có thể dùng CDATA như thế nào?
Bạn sẽ phân tích ảnh hưởng của khoảng trắng và xuống dòng đối với các kiểu nội dung XML khác nhau ra sao?
Bạn sẽ kiểm tra khai báo encoding và xử lý nguy cơ ký tự tiếng Việt bị sai khi đọc ghi XML bằng Java như thế nào?
Vì sao XML namespace dùng URI định danh và bạn sẽ phân biệt URI đó với địa chỉ cần truy cập qua mạng ra sao?
Khi hai hệ thống dùng phần tử trùng tên, bạn sẽ thiết kế namespace để tránh va chạm ý nghĩa dữ liệu như thế nào?
Bạn sẽ giải thích sự khác nhau giữa namespace mặc định của phần tử và namespace của thuộc tính không có tiền tố ra sao?
Khi tài liệu thay tiền tố namespace nhưng giữ URI, bạn sẽ viết mã xử lý sao cho kết quả không bị ảnh hưởng như thế nào?
Bạn sẽ lựa chọn cách tổ chức nhiều namespace trong tài liệu để vừa dễ đọc vừa tương thích với các hệ thống nhận ra sao?
Bạn sẽ phân biệt vai trò của DTD và XSD đối với kiểm tra cấu trúc cùng các rủi ro bảo mật liên quan như thế nào?
Khi thiết kế XSD, bạn sẽ sử dụng simple type và complex type cho những loại dữ liệu nào?
Bạn sẽ mô tả cách ràng buộc kiểu dữ liệu, giá trị cho phép và số lần xuất hiện của phần tử bằng XSD ra sao?
Bạn sẽ cân nhắc ràng buộc thứ tự các phần tử trong XSD để cân bằng tính chặt chẽ và khả năng mở rộng như thế nào?
Khi thêm trường mới vào tài liệu XML, bạn sẽ đánh giá tương thích với phiên bản schema và các client cũ ra sao?
Bạn sẽ phân biệt kiểm tra cấu trúc theo XSD với xác minh các quy tắc nghiệp vụ vượt ngoài khả năng schema như thế nào?
Khi tài liệu không hợp lệ theo XSD, bạn sẽ tạo thông báo lỗi có vị trí và nguyên nhân đủ rõ cho người dùng ra sao?
Bạn sẽ chọn DOM, SAX hay StAX để đọc XML dựa trên kích thước tài liệu, bộ nhớ và kiểu truy cập dữ liệu như thế nào?
Bạn sẽ giải thích cây DOM phù hợp với việc điều hướng và chỉnh sửa nhiều vị trí trong tài liệu bằng những đặc điểm nào?
Khi xử lý XML rất lớn bằng DOM, bạn sẽ xác định nguy cơ bộ nhớ và những lựa chọn thay thế ra sao?
Bạn sẽ thiết kế một SAX handler để tích lũy dữ liệu của một phần tử qua các sự kiện bắt đầu, ký tự và kết thúc như thế nào?
Vì sao callback chứa ký tự trong SAX có thể chia nội dung văn bản thành nhiều lần và bạn sẽ ghép dữ liệu đúng ra sao?
Khi các phần tử lặp lại có cùng tên ở nhiều cấp, bạn sẽ quản lý ngữ cảnh đường dẫn khi dùng SAX như thế nào?
Bạn sẽ giải thích cách StAX cho phép ứng dụng chủ động kéo từng sự kiện so với mô hình callback của SAX ra sao?
Khi chỉ cần trích xuất một phần nhỏ của XML lớn, bạn sẽ tổ chức xử lý streaming và dừng đọc hợp lệ như thế nào?
Bạn sẽ quản lý việc đóng stream, reader và các tài nguyên parser khi lỗi xảy ra giữa quá trình đọc ra sao?
Bạn sẽ ghi XML từ dữ liệu Java bằng cách nào để bảo đảm escape đúng và không tự nối chuỗi thủ công nguy hiểm?
Khi cần tạo tài liệu XML nhiều namespace, bạn sẽ kiểm soát tên đầy đủ và khai báo tiền tố lúc ghi ra sao?
Bạn sẽ lựa chọn JAXB để ánh xạ lớp Java sang XML trong điều kiện nào thay vì tự duyệt DOM hoặc StAX?
Bạn sẽ thiết kế ánh xạ JAXB cho phần tử, thuộc tính và danh sách lặp mà không làm lộ chi tiết serialization vào nghiệp vụ ra sao?
Khi một trường XML tùy chọn không xuất hiện, bạn sẽ xử lý giá trị mặc định và phân biệt với phần tử rỗng trong Java như thế nào?
Bạn sẽ định nghĩa kiểm thử round-trip marshal và unmarshal để phát hiện mất dữ liệu hoặc thay đổi cấu trúc như thế nào?
Bạn sẽ dùng XPath để chọn một tập nút theo điều kiện mà không cần tự viết nhiều vòng lặp duyệt DOM ra sao?
Khi truy vấn XPath trên tài liệu có namespace mặc định, bạn sẽ cấu hình ánh xạ prefix trong bộ đánh giá thế nào?
Bạn sẽ phân biệt kết quả XPath trả về nút, danh sách nút, chuỗi và số khi tích hợp Java như thế nào?
Khi người dùng cung cấp điều kiện tìm kiếm, bạn sẽ tránh ghép trực tiếp biểu thức XPath thiếu kiểm soát như thế nào?
Bạn sẽ sử dụng XSLT để biến đổi một cấu trúc XML sang cấu trúc khác trong tình huống tích hợp dữ liệu nào?
Bạn sẽ phân biệt phần nội dung XSLT đảm nhiệm với phần kiểm tra nghiệp vụ nên giữ trong ứng dụng Java ra sao?
Khi biến đổi XML bằng XSLT, bạn sẽ kiểm thử namespace, thiếu phần tử và dữ liệu có ký tự đặc biệt như thế nào?
Bạn sẽ cấu hình bộ xử lý XSLT để hạn chế truy cập tài nguyên bên ngoài và tránh tải nội dung không được phép ra sao?
Bạn sẽ giải thích lỗ hổng XXE phát sinh như thế nào khi parser xử lý external entity từ tài liệu không đáng tin cậy?
Khi nhận XML từ bên ngoài, bạn sẽ cấu hình DOM, SAX và StAX để vô hiệu hóa các tính năng phân giải thực thể hoặc tài nguyên ngoài không cần thiết ra sao?
Bạn sẽ đánh giá nguy cơ tấn công làm tiêu hao tài nguyên qua khai báo thực thể và áp dụng giới hạn xử lý XML như thế nào?
Khi xác thực XSD được yêu cầu, bạn sẽ hạn chế việc tải schema và các tham chiếu phụ từ địa chỉ bên ngoài ra sao?
Bạn sẽ thiết kế bộ kiểm thử bảo mật XML bằng tài liệu chứa DTD, external entity và tham chiếu mạng để kiểm chứng cấu hình parser như thế nào?
Khi cần xử lý tệp XML không đáng tin cậy, bạn sẽ đặt giới hạn kích thước, độ sâu lồng nhau và thời gian xử lý ra sao?
Bạn sẽ thiết kế cơ chế ghi log lỗi phân tích XML đủ hữu ích mà không ghi toàn bộ dữ liệu nhạy cảm ra sao?
Bạn sẽ so sánh cách xác minh tương thích giữa các phiên bản tài liệu khi kết hợp namespace, XSD và lớp Java JAXB như thế nào?
Bạn sẽ đánh giá hiệu quả của một pipeline đọc, xác thực, truy vấn và biến đổi XML bằng những chỉ số về độ đúng, bộ nhớ và hiệu năng nào?
