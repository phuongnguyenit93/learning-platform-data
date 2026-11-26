Trong trình biên dịch Java thu nhỏ, cây cú pháp có các nút Literal, BinaryExpression và Variable; mỗi lần thêm chức năng in cây, kiểm tra kiểu hay tính giá trị, nhóm lại sửa logic của mọi lớp nút.
Một trình soạn thảo tài liệu lưu đoạn văn, bảng và hình ảnh thành các loại phần tử riêng; tính năng đếm từ đang phải phân biệt loại phần tử bằng nhiều nhánh instanceof rải khắp ứng dụng.
Đội phát triển cây biểu thức sử dụng Visitor để tính giá trị và xuất chuỗi; sau khi thêm nút ConditionalExpression, nhiều visitor cũ vẫn biên dịch qua nhánh xử lý chung nhưng bỏ qua logic điều kiện.
Trong hệ thống phân tích mã nguồn, một lớp nút kế thừa Expression nhưng không override accept; visitor dành cho biểu thức cụ thể không được gọi và báo cáo loại biểu thức thiếu dữ liệu.
Một nhóm viết visitor có các phương thức visit cho Shape và Circle; khi gọi visit qua biến tham chiếu kiểu Shape thay vì đi qua accept của Circle, phương thức tổng quát được chọn dù đối tượng thực là Circle.
Ứng dụng đồ họa quản lý Circle, Rectangle và Polygon; bộ xuất SVG và bộ tính diện tích đã dùng visitor, nhưng lớp Polygon mới chỉ được hỗ trợ ở bộ xuất còn bộ tính diện tích trả giá trị mặc định.
Trong công cụ phân tích hợp đồng, các phần tử Clause, Signature và Attachment được xử lý bởi nhiều visitor; nhóm bổ sung loại phụ lục mới nhưng không xác định được những tác vụ nào bắt buộc hiểu loại này.
Một hệ thống báo cáo tài chính dùng visitor để tổng hợp Invoice, CreditNote và Payment; tổng doanh thu bị đếm cả khoản thanh toán lẫn hóa đơn vì visitor không phân biệt loại nghiệp vụ khi cộng.
Trong cây thư mục, visitor tính tổng kích thước được áp dụng lên Folder chứa các File; cả Folder.accept và visitor.visitFolder đều duyệt con, khiến cùng file được cộng hai lần.
Ứng dụng quản lý sơ đồ công trình có các phần tử dùng chung ở nhiều nhánh; visitor đi theo mọi tham chiếu và ghi nhận cùng thiết bị nhiều lần dù báo cáo chỉ yêu cầu thiết bị duy nhất.
Một mô hình quy trình cho phép hai bước tham chiếu lẫn nhau để mô tả vòng lặp; visitor duyệt theo quan hệ tham chiếu mà không nhận biết chu trình nên xử lý không kết thúc.
Trong công cụ kiểm tra tài liệu, visitor lưu số lỗi tìm thấy vào field và được tái sử dụng cho nhiều tài liệu; kết quả của tài liệu sau bao gồm lỗi từ tài liệu trước.
Đội chạy kiểm tra cấu trúc AST song song bằng cùng một instance visitor có danh sách lỗi mutable; thông báo của hai file nguồn bị trộn vào cùng một báo cáo.
Một visitor xác minh thứ tự điều khoản trong hợp đồng; khi cây tài liệu được duyệt theo thứ tự khác, kết quả thay đổi dù nội dung và quan hệ giữa các điều khoản giữ nguyên.
Trong hệ thống báo giá, visitor tính tổng tiền cần giữ ngữ cảnh loại tiền và thuế suất; một giá trị tiền từ nhánh con bị quy đổi theo ngữ cảnh của nhánh trước đó.
Một bộ đánh giá biểu thức có visitor trả về kiểu Object cho mọi loại nút; khi kết quả của phép cộng bị chuyển thành chuỗi ở một nhánh, lỗi ép kiểu chỉ xảy ra lúc chạy.
Ứng dụng xuất báo cáo HTML dùng một visitor vừa tích lũy nội dung vừa ghi trực tiếp ra file; nếu gặp nút lỗi giữa tài liệu, file đầu ra đã chứa một phần nội dung không hợp lệ.
Một trình phân tích cú pháp muốn visitor bỏ qua comment và whitespace, nhưng bộ xuất mã nguồn lại cần giữ chúng; một quy tắc duyệt chung làm một trong hai tác vụ bị mất thông tin.
Trong kho tài liệu doanh nghiệp, visitor trích xuất văn bản được cấp quyền truy cập toàn bộ node; khi xuất nội dung xem trước, nó vô tình đọc cả phần thông tin nhạy cảm ẩn khỏi người dùng.
Đội xây visitor kiểm tra quy tắc chính tả cho tài liệu đa ngôn ngữ; trạng thái ngôn ngữ của tiêu đề cha không được khôi phục sau khi duyệt bảng lồng bên trong.
Ứng dụng tạo hóa đơn có visitor cho từng loại dòng hàng; visitor chiết khấu sửa trực tiếp đối tượng LineItem nên visitor kiểm toán chạy sau thấy dữ liệu đã đổi mà không còn giá trị gốc.
Trong một công cụ refactor, visitor sửa cấu trúc cây cú pháp trong khi đang duyệt danh sách con; một số node bị bỏ qua hoặc xử lý lại do vị trí phần tử thay đổi.
Nhóm dùng visitor để tính hash của cây biểu thức; cùng một node có thể được chia sẻ giữa nhiều nhánh nên cách duyệt và ghi nhận danh tính làm hai cây tương đương có hash khác nhau.
Đội phát triển thêm thao tác chuyển đổi tiền tệ vào hệ thống có hàng chục loại phần tử giao dịch; visitor mới phải cài đặt hàng chục phương thức dù phần lớn loại không mang số tiền.
Trong ứng dụng sơ đồ tổ chức, hierarchy Employee, Department và Contractor thay đổi thường xuyên; mỗi lần có loại node mới, nhiều visitor cho báo cáo và phân quyền đều phải cập nhật dù tính năng không liên quan.
Một thư viện plugin cho phép bên thứ ba thêm loại node nhưng API visitor hiện có tập phương thức visit cố định; plugin chạy được với lớp gốc nhưng báo lỗi khi tác vụ cần xử lý riêng node mở rộng.
Đội dùng Visitor qua các module Java độc lập; interface Visitor được mở rộng thêm một overload và các thư viện consumer đã biên dịch từ trước gặp vấn đề tương thích khi nâng phiên bản.
Một framework xử lý cây tài liệu có phương thức visitUnknown mặc định; khi bổ sung loại nội dung mới, báo cáo phát hành vẫn PASS dù mọi visitor cũ đang âm thầm bỏ qua nội dung đó.
Trong trình tính toán biểu thức, một visitor chỉ chấp nhận node có hai toán hạng; node mới biểu diễn phép toán một ngôi xuất hiện và phương thức xử lý cũ lấy nhầm toán hạng không tồn tại.
Ứng dụng phân tích cấu hình nhận các node dạng scalar, list và map; visitor xuất JSON không phân biệt null với trường vắng mặt, làm thay đổi ý nghĩa cấu hình sau chuyển đổi.
Nhóm xây bộ kiểm tra tính hợp lệ cho mô hình đặt hàng gồm Customer, Order và OrderLine; một visitor duyệt mọi entity nhưng không biết khi nào nên dừng ở ranh giới aggregate.
Trong phần mềm thiết kế UI, visitor tạo cây accessibility cho Button, TextField và Container; nhiều nút trang trí không được đưa vào kết quả, nhưng visitor kiểm tra tương tác lại mặc định chúng vẫn tồn tại.
Một trình đọc file dữ liệu dùng visitor để xuất CSV từ các node văn bản, hình ảnh và bảng; khi gặp bảng lồng nhau, kết quả không còn giữ quan hệ hàng và cột như kỳ vọng.
Trong hệ thống phân tích giao dịch, visitor tạo báo cáo rủi ro dùng biến toàn cục lưu khách hàng đang xử lý; một khoản thanh toán tham chiếu tới khách hàng khác khiến trạng thái bị ghi đè giữa quá trình duyệt.
Một bộ kiểm tra quy tắc nghiệp vụ dùng visitor để sinh nhiều cảnh báo cho một phần tử; khi phần tử đầu tiên có lỗi nghiêm trọng, exception làm dừng toàn bộ cây và các lỗi còn lại không được thu thập.
Đội chuyển từ các nhánh instanceof sang Visitor cho mô hình hình học; các lớp hình được xem là ổn định nhưng lộ trình sản phẩm liên tục bổ sung hình mới hơn là bổ sung thao tác mới.
Trong trình biên dịch, visitor phân giải biến phải duy trì ngăn xếp scope khi đi qua block lồng nhau; khi một nhánh có lỗi và thoát sớm, scope cũ không được phục hồi.
Một ứng dụng kiểm tra biểu mẫu sử dụng cùng visitor để tính lỗi bắt buộc và hiển thị nhãn trường; bộ tính lỗi không cần tài nguyên UI nhưng visitor vẫn kéo theo phụ thuộc trình bày.
Nhóm kiểm thử visitor in biểu thức chỉ bằng cây gồm một node; với cây có nhiều phép toán lồng nhau, kết quả bị mất ngoặc và thay đổi ý nghĩa biểu thức nhưng bộ test không phát hiện.
Trong thư viện thao tác cây đối tượng, nhóm muốn thêm đồng thời loại phần tử mới và thao tác xuất định dạng mới; mỗi thay đổi gây sửa cả hệ thống phần tử lẫn hệ thống visitor, khiến phạm vi tương thích khó đánh giá.
