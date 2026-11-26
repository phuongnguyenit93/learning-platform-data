Một nhóm xây DSL mô tả quy tắc giảm giá, trong đó biểu thức A hoặc B và C được hai thành viên hiểu theo thứ tự ưu tiên toán tử khác nhau; cùng một file cấu hình cho hai kết quả tính tiền.
Khi viết parser cho ngôn ngữ dạy học, cấu trúc if lồng nhau không có dấu phân cách rõ ràng khiến mệnh đề else có thể gắn với hai nhánh khác nhau, làm cây cú pháp gây tranh cãi.
Công cụ chuyển mã từ ngôn ngữ dùng khối bằng thụt lề sang ngôn ngữ dùng dấu ngoặc gặp một file có tab và space trộn lẫn, khiến ranh giới khối lệnh bị hiểu khác nhau.
Một bộ biên dịch tự xây nhận cú pháp vòng lặp mới nhưng thông báo lỗi chỉ trỏ vào cuối file thay vì chỗ thiếu dấu đóng; người học cần phân biệt lỗi phân tích từ vựng và cú pháp.
Trong quá trình mở rộng ngôn ngữ cấu hình, đội muốn cho phép tên biến trùng với từ khóa trước đây; bộ phân tích cú pháp hiện tại không còn phân biệt được khai báo biến và câu lệnh.
Một chương trình đổi từ tính toán biểu thức có short-circuit sang hàm đánh giá mọi đối số; một phép kiểm tra null trước khi truy cập thuộc tính không còn ngăn được lỗi.
Nhóm chuyển logic kiểm tra từ Python sang JavaScript và dùng cùng một biểu thức so sánh; các trường hợp chuỗi chứa số hoặc giá trị rỗng cho kết quả khác kỳ vọng vì quy tắc ép kiểu.
Dịch vụ mã hóa trạng thái dùng so sánh tham chiếu thay cho so sánh giá trị đối tượng; dữ liệu sau khi giải tuần tự không còn trùng kết quả dù các trường giống hệt nhau.
Trong công cụ mô phỏng, hai toán hạng của một phép cộng đều gây tác dụng phụ lên cùng biến; kết quả thay đổi khi chuyển sang ngôn ngữ có quy định thứ tự đánh giá khác.
Nhóm phát triển thư viện generic nhận danh sách số trong Java và tưởng có thể truyền danh sách số nguyên vào nơi đòi hỏi danh sách Number; trình biên dịch báo lỗi dù các phần tử đều là Number.
Khi áp dụng Kotlin để giảm lỗi null, một tham số có kiểu nullable được chuyển qua nhiều nhánh điều kiện; hệ thống kiểu không thể chứng minh giá trị khác null tại điểm truy cập cuối.
Một API TypeScript khai báo union type cho trạng thái thanh toán nhưng code chỉ xử lý hai trong ba biến thể; khi thêm trạng thái mới, phần logic không được bao phủ trong một số nhánh.
Đội chuyển mô hình plugin từ interface danh nghĩa sang structural typing; một đối tượng vô tình có đủ phương thức được chấp nhận dù không được thiết kế như plugin hợp lệ.
Một ứng dụng Java overload hai phương thức có kiểu tham số gần nhau; khi truyền null hoặc một kiểu được tự động chuyển đổi, bộ phân giải lời gọi không chọn được phương thức mong đợi.
Trong dự án sử dụng kiểu suy luận, một hàm trả về nhiều hình dạng dữ liệu theo nhánh; kiểu được suy ra rộng đến mức client mất khả năng kiểm tra đầy đủ thuộc tính cần dùng.
Người viết trình thông dịch mong một hàm nhận giá trị biến tại nơi được gọi, trong khi cơ chế lexical scope khiến nó đọc binding tại nơi được định nghĩa; kết quả biến đổi khi lồng hàm.
Một chương trình khai báo tên count ở phạm vi toàn cục, trong hàm và trong vòng lặp; một nhánh cập nhật nhầm biến bị che khuất khiến bộ đếm hệ thống không thay đổi.
Một danh sách callback được tạo trong vòng lặp để xử lý các nút giao diện; khi người dùng bấm từng nút, mọi callback lại cùng hiển thị giá trị biến cuối vòng lặp.
Một closure lưu giữ đối tượng phiên làm việc lớn sau khi request đã kết thúc; ứng dụng chiếm bộ nhớ ngày càng tăng vì vòng đời dữ liệu bị kéo dài ngoài dự kiến.
Một ngôn ngữ giả lập cho phép khai báo biến cục bộ bên trong khối nhưng người viết interpreter dùng một bảng tên chung cho cả chương trình, khiến giá trị còn tồn tại sau khi rời khối.
Trong dịch vụ Java, hàm nhận tham số là một đối tượng cấu hình rồi gán tham số sang đối tượng mới; người gọi ngạc nhiên vì biến tham chiếu bên ngoài không trỏ sang cấu hình mới.
Một engine xử lý truy vấn thử triển khai đánh giá đối số lười để tránh phép toán đắt tiền; biểu thức có ghi log bên trong đôi khi không được thực thi nên thứ tự log không còn ổn định.
Nhóm tối ưu chương trình hàm có đệ quy sâu bằng cách đặt lời gọi đệ quy ở cuối hàm; khi chạy trên môi trường không bảo đảm tối ưu đệ quy đuôi, tiến trình vẫn tràn stack.
Ứng dụng Java overload phương thức theo kiểu tham số ở lớp cha và override một chữ ký trong lớp con; nhóm hiểu sai thời điểm chọn chữ ký và chọn bản triển khai của lời gọi.
Trong engine xử lý giao dịch, hai biến cùng tham chiếu một danh sách có thể thay đổi; khi luồng A xóa phần tử, kết quả xử lý của luồng B cũng bị ảnh hưởng dù mỗi bên tưởng có bản sao riêng.
Nhóm chuyển thành phần từ C sang Rust để giảm lỗi bộ nhớ; thiết kế trả về tham chiếu tới dữ liệu cục bộ bị bộ kiểm tra vòng đời từ chối, dù lập trình viên tin rằng dữ liệu vẫn tồn tại.
Một module C cấp phát vùng nhớ cho chuỗi rồi giải phóng nó trước khi callback bất đồng bộ chạy; chỉ trên máy production mới phát sinh lỗi đọc dữ liệu đã được giải phóng.
Ứng dụng dùng garbage collector nhưng cache giữ tham chiếu mạnh đến tất cả kết quả từ khi khởi động; heap tăng mãi dù không thấy lời gọi cấp phát bộ nhớ thủ công bất thường.
Khi truyền dữ liệu giữa hai tác vụ, đội chọn copy sâu một cây đối tượng lớn để tránh chia sẻ mutable state; throughput giảm mạnh và tài liệu chưa làm rõ nhu cầu độc lập của hai bản sao.
Trong dự án hướng đối tượng, lớp con thay đổi nghĩa của phương thức rút tiền thành thao tác bất đồng bộ nhưng client lớp cha mặc định kết quả đã hoàn tất ngay sau lời gọi.
Nhóm xây cấu trúc danh sách bất biến nhưng phương thức getter trả về tham chiếu tới mảng nội bộ có thể thay đổi; client sửa phần tử và phá vỡ bất biến mà module hứa hẹn.
Một chương trình dùng composition giữa các đối tượng để thay thế hệ phân cấp lớp kế thừa nhiều tầng; người dùng API gặp hành vi khác nhau khi phương thức được ủy quyền hay override.
Đội phân tích số liệu chuyển hàm chuẩn hóa dữ liệu sang phong cách hàm thuần, nhưng hàm vẫn đọc biến cấu hình toàn cục có thể thay đổi khiến cùng đầu vào cho ra hai kết quả.
Trong pipeline xử lý dữ liệu theo kiểu functional, một bước map tạo side effect ghi database; khi hệ thống thực thi lại pipeline để phục hồi, bản ghi bị nhân đôi.
Nhóm dùng lazy stream để xử lý tập dữ liệu rất lớn nhưng một phép toán cuối cùng yêu cầu thu toàn bộ kết quả vào bộ nhớ, gây out-of-memory ngay khi kích hoạt tính toán.
Một engine luật bằng Prolog có hai quy tắc suy luận có thể dẫn tới cùng kết quả; đội nghiệp vụ thấy truy vấn trả về nhiều nghiệm giống nhau và không hiểu vai trò của backtracking.
Hệ thống chat dùng mô hình actor, nhưng một nhóm vẫn chia sẻ trực tiếp danh sách phiên mutable giữa các actor; lỗi đồng thời xuất hiện dù mỗi actor xử lý tuần tự hộp thư của riêng mình.
Một thư viện async tạo nhiều tác vụ con từ một request nhưng không thu hồi tác vụ khi request bị hủy; log xuất hiện tác vụ hoàn thành sau khi client đã ngắt kết nối.
Nhóm xây macro để sinh mã kiểm tra đầu vào; macro tự đặt tên biến tạm trùng với tên biến của người dùng khiến biểu thức được mở rộng thay đổi hành vi.
Một đội tạo DSL mô tả workflow phê duyệt cho người nghiệp vụ, nhưng cú pháp ngày càng cho phép biểu thức tùy ý và việc kiểm tra ý nghĩa trước khi thực thi trở nên khó khăn.
