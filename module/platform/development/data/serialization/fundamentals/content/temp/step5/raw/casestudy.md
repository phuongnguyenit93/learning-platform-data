Một cảm biến công nghiệp gửi số nguyên 16 bit theo thứ tự byte lớn trước, còn ứng dụng nhận giải mã byte nhỏ trước; cùng một nhiệt độ được hiển thị thành giá trị phi lý sau khi truyền qua mạng.
Ứng dụng Java lưu bộ đếm thiết bị dưới dạng số nguyên có dấu 32 bit rồi truyền sang hệ thống dùng số nguyên không dấu; các giá trị gần giới hạn khiến hai phía hiểu khác nhau về số lượng.
Nhóm xây định dạng nhị phân riêng để ghi giao dịch, trong đó trường chiều dài được lưu bằng hai byte; một bản ghi lớn vượt giới hạn làm bộ đọc lấy thiếu dữ liệu ở các trường phía sau.
Dịch vụ xuất bảng giá sang JSON giữ số tiền bằng số thực nhị phân; sau nhiều lần serialize rồi deserialize qua các hệ thống, phần thập phân của số tiền có sai lệch nhỏ gây lỗi đối soát.
Một API chuyển mã định danh 64 bit qua JSON cho giao diện JavaScript; vài mã lớn bị làm tròn khi client parse dữ liệu, khiến yêu cầu cập nhật trỏ tới mã không tồn tại.
Một ứng dụng cắt chuỗi UTF-8 theo giới hạn byte của gói tin nhưng không xét ranh giới ký tự đa byte; tên khách hàng tiếng Việt bị mất dấu hoặc xuất hiện ký tự thay thế sau giải mã.
Nhóm hợp nhất tên người dùng từ hai hệ thống, một bên lưu ký tự có dấu ở dạng Unicode tổ hợp, bên kia lưu ký tự dựng sẵn; sau round-trip, phép so sánh chuỗi vẫn cho kết quả khác.
Dữ liệu CSV chứa ký tự tiếng Việt được xuất bằng một bộ mã cũ, trong khi dịch vụ Java nhập mặc định UTF-8; một số tên sản phẩm trở thành chuỗi lỗi dù phần dấu phẩy vẫn được đọc đúng.
Một file văn bản có dấu BOM được ứng dụng coi là một phần tên trường đầu tiên; tên cột đầu tiên không khớp schema dù người dùng mở bằng trình soạn thảo vẫn thấy bình thường.
API khách hàng trả về JSON thiếu trường phone khi chưa được nhập, nhưng consumer lại phân biệt việc thiếu trường với phone có giá trị null để quyết định giữ hay xóa dữ liệu cũ.
Trong dữ liệu cấu hình JSON, hai trường status có cùng tên nhưng giá trị khác nhau xuất hiện sau khi ghép payload; hai thư viện parse ưu tiên vị trí khác nhau nên hệ thống không thống nhất trạng thái.
Một dịch vụ giao dịch muốn biểu diễn NaN hoặc Infinity từ phép đo bằng JSON thông thường; bước xuất dữ liệu thất bại hoặc tạo giá trị không tương thích với consumer khác.
Nhóm xuất thông tin thiết bị thành JSON nhưng ứng dụng nhận phụ thuộc vào thứ tự xuất hiện các khóa trong object; một phiên bản serializer mới sắp xếp lại khóa khiến quy trình xác minh không còn hoạt động.
Ứng dụng gửi thời gian họp dưới dạng chuỗi không có múi giờ; server ở Việt Nam và client tại châu Âu giải mã thành hai thời điểm tuyệt đối khác nhau dù cùng văn bản.
Nhóm serialize đối tượng ngày giờ có phần nano giây sang định dạng chỉ giữ mili giây; phép round-trip làm mất độ chính xác và khiến thứ tự các sự kiện gần nhau thay đổi.
Trong hệ thống XML, hai đối tác dùng cùng tên phần tử Customer nhưng URI namespace khác nhau; bộ đọc dựa vào tên cục bộ ghép nhầm hai loại dữ liệu với ý nghĩa khác.
Một bản tin XML biểu diễn mã đơn hàng dưới dạng attribute ở phiên bản cũ và element ở phiên bản mới; consumer hiện tại chỉ đọc một kiểu nên bỏ trống mã trên một phần giao dịch.
Nhóm nhận XML do đối tác bên ngoài gửi nhưng parser vẫn cho phép tải external entity; quá trình phân tích tài liệu có nguy cơ truy cập tài nguyên mà hệ thống nhập dữ liệu không cần tới.
Một file CSV lưu ghi chú có dấu phẩy, dấu xuống dòng và dấu nháy kép; bộ tách dòng và split theo dấu phẩy của ứng dụng biến một bản ghi thành nhiều bản ghi sai cấu trúc.
Bộ nhập CSV của cửa hàng quốc tế được cấu hình dấu phẩy làm dấu phân tách, nhưng tập tin từ một thị trường dùng dấu chấm phẩy và dấu phẩy trong số thập phân; kết quả ánh xạ cột bị lệch.
Nhóm xuất danh sách khách hàng sang CSV để nhân viên mở bằng bảng tính; tên công ty có ký tự đầu là dấu bằng hoặc cộng và bị phần mềm bảng tính hiểu thành công thức.
Một cấu hình YAML có cấu trúc lồng nhau cho quyền truy cập; việc thụt lề lệch một cấp khiến một nhóm quyền được gắn vào đối tượng khác mà trình đọc vẫn chấp nhận file.
Hệ thống nhập YAML từ nhiều đối tác, một parser tự suy diễn on, off thành boolean còn parser khác giữ nguyên chuỗi; giá trị cùng hiển thị trên file nhưng logic ứng dụng chạy khác nhau.
Một file YAML chứa trùng tên khóa timeout trong cùng một mapping; công cụ này dùng giá trị đầu, công cụ khác dùng giá trị cuối và pipeline cấu hình tạo ra những thời hạn chờ khác nhau.
Đội thiết kế bản tin nhị phân tối ưu băng thông nhưng bỏ mô tả field nào là bắt buộc, cách đánh dấu null và độ dài dữ liệu biến thiên; một consumer mới không giải mã được phiên bản cũ.
Nhóm chuyển schema giao dịch từ version 1 sang version 2 bằng cách đổi tên field amount thành totalAmount; hệ thống cũ vẫn chạy nhưng không tìm được số tiền trong các bản tin mới.
Một trường địa chỉ tùy chọn trong schema trước được chuyển thành bắt buộc trong schema mới; dữ liệu lịch sử không có trường này khiến job đọc lại toàn bộ lưu trữ thất bại.
Service sản phẩm bổ sung giá trị enum BACKORDER vào hợp đồng truyền dữ liệu; các consumer phiên bản cũ không có nhánh xử lý giá trị mới và một số đơn bị bỏ qua.
Trong quá trình triển khai rolling update, producer mới gửi payload theo cấu trúc mới khi một nửa consumer vẫn chạy bản cũ; cùng topic sự kiện được nhận nhưng không được giải mã đồng nhất.
Đội phát triển đánh dấu phiên bản schema trong nội dung tài liệu mà không ghi vào envelope bản tin; consumer nhận nhiều loại payload không thể xác định trình giải mã phù hợp trước khi parse.
Chức năng kiểm thử round-trip với dữ liệu tiền tệ cho rằng đối tượng sau deserialize phải giống tuyệt đối bản gốc; serializer bỏ trailing zero khiến 10.00 được đọc thành 10.0 và phép so sánh theo scale thất bại.
Một bộ kiểm thử chỉ serialize rồi deserialize object Java thành công mà không thử tương tác với serializer viết bằng ngôn ngữ khác; bản tin đa hệ thống thiếu thống nhất về ký hiệu null và số nguyên lớn.
Trong pipeline xử lý file nén, chương trình giải nén rồi parse ngay dữ liệu mà không kiểm tra giới hạn kích thước; một file đầu vào rất nhỏ có thể mở rộng thành dữ liệu lớn ngoài khả năng bộ nhớ.
API nhận một chuỗi JSON chứa mảng hàng triệu phần tử và tải toàn bộ thành cây đối tượng trước khi xử lý dòng đầu; dịch vụ hết bộ nhớ dù tác vụ chỉ cần thống kê từng phần tử.
Nhóm đọc JSON streaming theo từng khối byte từ mạng; một ký tự Unicode bị chia qua hai khối và bộ giải mã hiện tại coi đó là hai ký tự lỗi riêng biệt.
Một trình giải mã bản tin nhận trường số lượng phần tử từ client rồi cấp phát ngay mảng theo số lượng được khai báo; payload không đáng tin cậy có thể buộc dịch vụ cấp phát bộ nhớ rất lớn.
Ứng dụng nội bộ nhận một đối tượng Java serialized từ hàng đợi mà trước đây chỉ nhân viên sử dụng; khi mở tích hợp bên ngoài, nhóm chưa đánh giá rủi ro của deserialization đối tượng không tin cậy.
Đội triển khai phiên bản mới của lớp Serializable đã thay đổi cấu trúc thuộc tính mà không xác định hợp đồng serialVersionUID; các dữ liệu phiên cũ trên ổ đĩa không còn đọc được sau nâng cấp.
Nhóm đánh dấu một trường token là transient trong đối tượng Java; sau khi object được lưu và phục hồi từ Java Serialization, một luồng nghiệp vụ vẫn giả định token được giữ nguyên như trước.
Hệ thống ghi lại biểu đồ đối tượng Java có quan hệ hai chiều giữa Account và Transaction; khi chuyển sang định dạng JSON cây thông thường, quá trình serialize lặp qua các tham chiếu theo vòng hoặc tạo payload rất lớn.
