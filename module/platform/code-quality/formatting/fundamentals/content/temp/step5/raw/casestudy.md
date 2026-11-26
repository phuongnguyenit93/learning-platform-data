Trong một dự án Java có thành viên dùng tab và thành viên dùng khoảng trắng để thụt lề, các tệp được sửa qua nhiều IDE liên tục thay đổi căn lề; nhóm cần thống nhất quy tắc có thể áp dụng và kiểm tra tự động.
Hai nhóm backend dùng hai cách đặt dấu ngoặc nhọn cho khối điều kiện, khiến khi chuyển mã giữa các thư viện nội bộ, mỗi PR phát sinh hàng trăm dòng chỉ khác vị trí ngoặc.
Một chuỗi gọi phương thức Java dài bị từng IDE ngắt dòng ở vị trí khác nhau; reviewer không nhìn rõ thay đổi nghiệp vụ khi hai lập trình viên chỉnh sửa cùng một đoạn trong tuần.
Một API Java có nhiều tham số và annotation dài khiến tên phương thức bị đẩy xa khỏi phần tham số khi đọc trên màn hình nhỏ; nhóm cần xác định chuẩn ngắt dòng và căn lề phù hợp với nhiều IDE.
Một tệp Java dùng import tường minh, tệp khác dùng import ký tự đại diện; khi thêm hai lớp cùng tên từ các package khác nhau, build bắt đầu báo mơ hồ và quy tắc tổ chức import trở thành chủ đề tranh luận.
Một nhóm lạm dụng static import cho các hàm tiện ích có tên chung, khiến người đọc khó xác định nguồn của phương thức; nhóm chuẩn hóa cần phân biệt sở thích cá nhân với quy tắc import nhất quán.
Các lớp dịch vụ trong dự án đặt trường, constructor, phương thức công khai và phương thức hỗ trợ theo thứ tự khác nhau; khi bảo trì, thành viên mới phải tìm kiếm nhiều lần để xác định vị trí chức năng.
Trong một lớp Java dài, khoảng trắng giữa các nhóm phương thức và dòng trống trong thân hàm được dùng tùy ý; các PR tổ chức lại mã gây nhiễu nhưng việc bỏ mọi dòng trống lại làm giảm khả năng đọc.
Một lập trình viên bật tính năng xóa khoảng trắng cuối dòng trong IDE, người khác không bật; lần sửa nhỏ tạo ra nhiều thay đổi không liên quan và một số diff chỉ hiển thị khác biệt vô hình.
Nhóm phát triển trên Windows, Linux và macOS liên tục tạo khác biệt giữa CRLF và LF trong cùng kho mã; một pull request một dòng bị Git hiển thị như thể toàn bộ tệp đã thay đổi.
Một dự án Java cũ có tệp UTF-8 với BOM xen lẫn tệp không có BOM; công cụ build và formatter khác nhau về cách xử lý đầu tệp, làm xuất hiện thay đổi không mong muốn khi lưu.
Kho mã chứa tài liệu và bình luận bằng tiếng Việt, nhưng một số thành viên lưu tệp với encoding mặc định của hệ điều hành; ký tự dấu bị biến dạng sau khi định dạng và commit.
Đội dự án đã có EditorConfig nhưng cấu hình thụt lề của IntelliJ, Eclipse và VS Code không đồng nhất; một người sửa đúng theo IDE vẫn bị CI báo lỗi định dạng.
Một dự án dùng formatter của IDE trong khi pipeline CI dùng một bộ quy tắc độc lập; PR được xem là chuẩn trên máy tác giả nhưng thất bại ở bước kiểm tra định dạng.
Sau khi nâng cấp phiên bản formatter, hàng nghìn dòng Java đổi cách xuống dòng dù nhóm không sửa quy ước; người phụ trách cần xác định chính sách cố định phiên bản và cách cập nhật có kiểm soát.
Một nhóm bật format-on-save tự động trên toàn dự án; khi mở tệp Java cũ để sửa một lỗi nhỏ, IDE lập tức thay đổi bố cục của cả tệp và khiến diff khó review.
Trên CI, bước định dạng tự động sửa tệp ngay trong workspace rồi tiếp tục build thành công nhưng không tạo commit chứa thay đổi; nhóm cần làm rõ ý nghĩa của kiểm tra định dạng và hành vi mong đợi khi phát hiện sai lệch.
Một hook trước commit tự động định dạng một tập tin nhưng chạy khác nhau giữa máy Windows và Linux; hai thành viên liên tục thấy các thay đổi lặp lại sau mỗi lần commit cùng nội dung.
Trong dự án đa module Gradle, formatter được cấu hình ở module ứng dụng nhưng bỏ qua module thư viện; các package cùng được phát hành lại không tuân thủ một chuẩn định dạng.
Nhóm chuyển một dự án Maven nhiều năm tuổi sang bộ formatter thống nhất và muốn áp dụng ngay cho toàn bộ tệp Java; hàng nghìn thay đổi định dạng chen lẫn lỗi cần sửa gấp trong nhánh phát hành.
Một PR định dạng lại toàn bộ kho mã khiến việc truy vết bằng Git blame khó nhìn ra người thay đổi logic trước đây; nhóm cần cân nhắc quy trình ghi nhận lịch sử và cách review đợt chuẩn hóa.
Khi hai nhánh dài hạn cùng được áp dụng formatter ở thời điểm khác nhau, thao tác hợp nhất phát sinh xung đột ở hàng trăm tệp dù chỉnh sửa chức năng gần như độc lập.
Một lập trình viên mở PR chỉ để chuẩn hóa khoảng trắng trên các tệp do nhóm khác sở hữu, ngay lúc các nhóm đó đang sửa tính năng; người quản lý cần chọn phạm vi và thứ tự triển khai để giảm xung đột.
Trong repository có nhiều tệp Java được sinh bởi công cụ từ schema, formatter tự động sửa các tệp này rồi lần sinh mã tiếp theo ghi đè; đội cần phân định quyền sở hữu và phạm vi xử lý mã sinh.
Một bộ kiểm thử snapshot so sánh nguyên văn tệp cấu hình được lưu làm fixture; bước format toàn kho vô tình thay đổi khoảng trắng cần thiết cho bài kiểm thử và tạo hàng loạt kết quả khác biệt.
Một ứng dụng Java sử dụng text block để chứa câu truy vấn SQL nhạy với xuống dòng; khi cập nhật quy chuẩn định dạng, nhóm cần xác định phần nào là bố cục nguồn và phần nào tác động trực tiếp đến dữ liệu chuỗi.
Một dự án có Javadoc dài chứa ví dụ và đường dẫn, mỗi IDE xuống dòng tài liệu theo cách khác nhau; những thay đổi chỉ ở chú thích chiếm phần lớn diff của các PR sửa API.
Nhóm nâng cấp lên cú pháp Java mới nhưng formatter phiên bản hiện tại không xử lý được một số cấu trúc nguồn; lập trình viên phải tắt kiểm tra ở các tệp mới và chính sách ngoại lệ chưa rõ ràng.
Trong một dự án, thứ tự annotation và khoảng cách quanh khai báo được một nhóm tự chỉnh thủ công, trong khi formatter khác lại sắp xếp theo quy tắc riêng; reviewer liên tục yêu cầu sửa qua sửa lại.
Một quy tắc giới hạn độ dài dòng quá chặt khiến đường dẫn, chuỗi thông báo và chú thích bị ngắt khó đọc; nhóm cần đánh giá tiêu chí ngoại lệ và cách biểu đạt chúng trong công cụ định dạng.
Một team muốn đưa kiểm tra định dạng vào CI bắt buộc nhưng repository hiện có hàng trăm tệp vi phạm từ trước; họ cần thiết kế lộ trình áp dụng với nhánh tính năng đang hoạt động và không làm tắc bản vá khẩn cấp.
Sau một quý dùng formatter tự động, số lỗi căn lề trong review giảm nhưng thời gian merge và xung đột không cải thiện; nhóm muốn dựa vào dữ liệu PR để kiểm tra xem chính sách và cách triển khai cần điều chỉnh ở đâu.
