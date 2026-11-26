Khi rà soát một repository, bạn sẽ phân biệt các rủi ro do API key, access token, mật khẩu và khóa riêng bị lộ như thế nào dựa trên mục đích sử dụng và phạm vi quyền của từng loại?
Bạn sẽ kết hợp nhận diện theo định dạng, mẫu biểu thức chính quy, entropy và kiểm chứng theo nhà cung cấp như thế nào để phát hiện secret mà vẫn hạn chế cảnh báo sai và tránh tiết lộ giá trị cần kiểm tra?
Một secret đã bị xóa khỏi phiên bản mã nguồn hiện tại nhưng từng được commit, bạn sẽ xác định phạm vi quét lịch sử Git qua các nhánh, tag và commit như thế nào để đánh giá khả năng nó vẫn bị truy cập?
Bạn sẽ tích hợp secret scanning tại máy phát triển, pull request và pipeline CI/CD như thế nào để ngăn secret mới bị đưa vào repository nhưng vẫn phát hiện được các giá trị đã tồn tại từ trước?
Nếu công cụ báo một chuỗi có entropy cao trong dữ liệu kiểm thử là secret, bạn sẽ điều tra cảnh báo đó dựa trên những bằng chứng nào và thiết kế ngoại lệ ra sao để không bỏ qua những rò rỉ thật về sau?
Khi pipeline vô tình ghi token vào log, build artifact hoặc cache, bạn sẽ tìm các bản sao có thể tiếp cận được và xác định phạm vi ảnh hưởng như thế nào ngoài việc kiểm tra mã nguồn?
Bạn sẽ ưu tiên xử lý các phát hiện secret scanning như thế nào khi các cảnh báo khác nhau về quyền truy cập, thời gian bị lộ, mức độ công khai và bằng chứng sử dụng trái phép?
Nếu một access token bị commit lên repository công khai rồi được xóa bằng commit mới, bạn sẽ tổ chức thu hồi, xoay khóa và xử lý lịch sử Git theo thứ tự nào để kiểm soát rủi ro còn sót lại?
Một credential đang được nhiều dịch vụ production sử dụng bị phát hiện rò rỉ, bạn sẽ phối hợp thay thế credential và kiểm tra hệ thống như thế nào để giảm nguy cơ gián đoạn và tránh tiếp tục dùng giá trị cũ?
Nếu khóa riêng dùng để ký artifact phát hành bị lộ, bạn sẽ đánh giá tính tin cậy của các bản phát hành đã ký và xác định những hành động khắc phục nào đối với khóa, hệ thống xác minh chữ ký và người dùng?
Bạn sẽ thiết kế cách cấp thông tin xác thực cho các job CI/CD như thế nào để giảm việc lưu secret dài hạn trong repository, giới hạn quyền của runner và kiểm soát khả năng secret xuất hiện trong log?
Bạn sẽ xây dựng quy trình quản lý cảnh báo secret scanning như thế nào để xác định người chịu trách nhiệm, ghi nhận bằng chứng xử lý, giới hạn thời hạn ngoại lệ và theo dõi liệu secret có bị đưa trở lại mã nguồn?
