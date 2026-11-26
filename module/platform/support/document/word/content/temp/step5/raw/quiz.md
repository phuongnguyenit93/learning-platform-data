Đặc điểm nào mô tả đúng cách DOCX lưu trữ tài liệu?
A. Một luồng XML duy nhất chứa mọi nội dung
B. Một tệp nhị phân chứa các vùng cố định
C. Một cơ sở dữ liệu bảng nội bộ
D. Gói ZIP chứa XML và tài nguyên DOCX
Đáp án đúng: D

Tệp quan hệ .rels trong gói DOCX chủ yếu dùng để làm gì?
A. Định nghĩa các liên kết giữa phần và đích
B. Xác định vị trí xuống dòng của từng đoạn
C. Ghi lại thay đổi nội dung theo từng phiên bản
D. Lưu danh sách phông chữ đang được sử dụng
Đáp án đúng: A

Trong DOCX, word/document.xml thường chứa thông tin nào?
A. Bảng định nghĩa toàn bộ phông chữ nhúng
B. Các thuộc tính tài liệu như tác giả, tiêu đề
C. Danh sách các ảnh và dữ liệu nhị phân của ảnh
D. Cấu trúc và nội dung của thân tài liệu chính
Đáp án đúng: D

Vai trò chủ yếu của word/styles.xml là gì?
A. Xác định đường dẫn tới các hình ảnh nhúng
B. Quản lý luồng thao tác sửa đổi từng ký tự
C. Lưu thứ tự các phần trong gói nén của Word
D. Định nghĩa các style để nội dung tham chiếu
Đáp án đúng: D

Vai trò chính của word/numbering.xml trong DOCX là gì?
A. Mức nén ZIP của các phần tài liệu
B. Lưu toàn bộ trường dữ liệu trong biểu mẫu
C. Quy tắc và kiểu đánh số cho các danh sách
D. Lưu số trang đã tính cho mọi trang tài liệu
Đáp án đúng: C

Vị trí nào thường lưu dữ liệu ảnh được nhúng trong DOCX?
A. Các thuộc tính số của từng đoạn văn bản
B. Các nút văn bản trực tiếp trong styles.xml
C. Các phần ghi chú thuần văn bản của tài liệu
D. Các tệp ảnh tại đường dẫn word/media
Đáp án đúng: D

Khi cần xử lý tệp .doc đời cũ bằng Apache POI, bạn thường xem xét API nào?
A. API HWPF xử lý tệp Word nhị phân
B. XWPF xử lý Word nhị phân cũ
C. XSSF dành cho định dạng Word nhị phân cũ
D. HSLF dành cho tệp Word nhị phân đời cũ
Đáp án đúng: A

Trong Apache POI, XWPF được dùng chủ yếu với định dạng nào?
A. Tài liệu ODT theo bộ tiêu chuẩn OpenDocument
B. Tài liệu DOCX dựa trên Office Open XML
C. Tài liệu RTF theo cú pháp văn bản có thẻ
D. Tài liệu DOC dựa trên luồng nhị phân cũ
Đáp án đúng: B

Đối tượng XWPFDocument biểu diễn thành phần nào?
A. Tài liệu DOCX được mở để chỉnh sửa
B. Một kiểu đoạn văn đang áp dụng cho tài liệu
C. Một mục đánh số thuộc danh sách của tài liệu
D. Hình ảnh chèn vào thân tài liệu
Đáp án đúng: A

Đối tượng XWPFParagraph chủ yếu biểu diễn điều gì?
A. Một phần ảnh với dữ liệu nội dung nhị phân
B. Một danh sách liên kết ra ngoài tài liệu
C. Một bảng chứa các hàng và những ô dữ liệu
D. Đoạn văn gồm các run và các thuộc tính định dạng
Đáp án đúng: D

Đối tượng XWPFRun thường gắn với thông tin nào?
A. Bảng các đoạn trên cùng trang
B. Một trang vật lý đã được Word dàn trang sẵn
C. Một tệp tài nguyên được đóng gói riêng biệt
D. Nội dung có định dạng riêng trong đoạn
Đáp án đúng: D

Vì sao thay thế chuỗi qua getText của từng run có thể thất bại?
A. Run chỉ có thể chứa thông tin kiểu định dạng
B. DOCX chỉ cho phép lưu mỗi đoạn thành một run
C. Cụm cần tìm có thể bị chia qua nhiều run
D. Văn bản trong Word không nằm trong các đoạn
Đáp án đúng: C

Cách nào phù hợp để đóng tài nguyên khi đọc DOCX từ Java?
A. Giữ luồng mở đến khi JVM kết thúc
B. Dùng try-with-resources khi mở tài liệu
C. Chờ bộ gom rác tự giải phóng mọi tệp mở
D. Chỉ đóng đầu ra sau khi gọi garbage collector
Đáp án đúng: B

Khi ghi XWPFDocument ra một tệp mới, thao tác nào phù hợp?
A. Gọi read lên luồng đầu ra rồi đóng tài nguyên
B. Gọi save lên từng run trước khi đóng tài liệu
C. Gọi write với OutputStream rồi đóng tài nguyên
D. Gọi flush trên đoạn đầu tiên của tài liệu
Đáp án đúng: C

Khi trích xuất đoạn và bảng theo đúng thứ tự xuất hiện, nên duyệt gì?
A. Danh sách các bảng rồi đến danh sách các đoạn
B. Đọc các run theo style trước bảng
C. Duyệt các bodyElements theo thứ tự
D. Danh sách các đoạn rồi đến danh sách các bảng
Đáp án đúng: C

Trong XWPF, xuống dòng trong cùng đoạn khác gì với thêm đoạn mới?
A. Xuống dòng sẽ thêm section mới vào gói tài liệu
B. Ngắt dòng giữ đoạn, tạo đoạn mới thêm phần tử
C. Đoạn mới chỉ thêm ký tự ngắt dòng vào run cũ
D. Hai thao tác luôn tạo cùng một cấu trúc OOXML
Đáp án đúng: B

Khi sửa một run và muốn giữ phần chữ đậm gốc, cách nào an toàn hơn?
A. Chuyển run thành văn bản thuần để ghi
B. Đổi style của mọi paragraph trước khi thay nội dung
C. Chỉ sửa phần chữ trên run cần thay thế
D. Xóa toàn bộ paragraph rồi tạo văn bản mới mặc định
Đáp án đúng: C

Đâu là rủi ro của việc áp dụng định dạng trực tiếp quá nhiều?
A. Khó giữ định dạng nhất quán giữa các mục
B. Các ảnh trong tài liệu bị mất liên kết ngay
C. Word sẽ tự đổi định dạng sang kiểu nhị phân
D. Các đoạn sẽ không thể chứa ký tự tiếng Việt
Đáp án đúng: A

Khi run có định dạng trực tiếp và style cũng định dạng cùng thuộc tính, điều gì thường xảy ra?
A. Hai giá trị luôn bị loại bỏ khỏi tệp DOCX gốc
B. Style của trang luôn ghi đè mọi thuộc tính trực tiếp
C. Word tách run thành hai đoạn độc lập
D. Định dạng trực tiếp thường được ưu tiên
Đáp án đúng: D

Muốn các tiêu đề tham gia cấu trúc heading của Word, nên làm gì?
A. Áp dụng style heading cho đoạn tiêu đề
B. Chỉ in đậm dòng đầu tiên trong mọi đoạn
C. Chỉ thêm dấu thăng trước văn bản tiêu đề
D. Chỉ tăng kích thước chữ của các đoạn tiêu đề
Đáp án đúng: A

Giữa abstractNum và num trong cơ chế numbering, quan hệ nào đúng?
A. AbstractNum luôn tham chiếu đến đoạn văn đầu tiên
B. Hai đối tượng không tham chiếu nhau trong DOCX
C. Num lưu dữ liệu ảnh trong danh sách
D. Num tham chiếu tới định nghĩa abstractNum
Đáp án đúng: D

Khi chuyển đoạn đánh số giữa hai DOCX, vấn đề nào cần kiểm tra?
A. Định dạng nén ZIP có còn sử dụng cùng mức nén
B. Kiểm tra tham chiếu numbering tại tệp đích
C. Tên tệp DOCX có còn giữ nguyên chữ hoa chữ thường
D. Thời gian chỉnh sửa của tệp có trùng với bản gốc
Đáp án đúng: B

Khi sinh DOCX tiếng Việt, điều gì cần kiểm tra trước tiên?
A. Định dạng ngày tháng của thông tin siêu dữ liệu
B. Mã hóa ANSI và bảng ký tự ASCII mặc định
C. Chế độ nén ảnh và chất lượng ảnh nhúng
D. Mã Unicode và phông hiển thị ký tự tiếng Việt
Đáp án đúng: D

Vì sao chỉ khai báo tên phông trong DOCX chưa đủ cho hiển thị đồng nhất?
A. Chỉ các trang lẻ mới hỗ trợ thuộc tính phông
B. Tên phông luôn bị xóa mỗi khi mở tệp DOCX
C. Máy nhận thiếu phông nên dùng phông dự phòng
D. Mọi định dạng phông luôn bị ghi thành hình ảnh
Đáp án đúng: C

Khi sinh văn bản trong các ngôn ngữ khác nhau, thuộc tính nào cần lưu ý?
A. Tên tệp tạm, cấp độ nén và số lượt mở
B. Hướng chữ, ngôn ngữ và thiết lập phông phù hợp
C. Ngày chỉnh sửa cuối, tên người tạo và đường dẫn
D. Mật khẩu lưu trữ, độ lớn gói và checksum
Đáp án đúng: B

Để căn giữa nội dung của một paragraph trong XWPF, nên sửa gì?
A. Thay đổi căn chỉnh trên đối tượng paragraph
B. Thuộc tính kích thước của từng ảnh trong run
C. Thuộc tính chú thích của từng ô trong bảng
D. Thuộc tính hướng giấy của toàn bộ tài liệu
Đáp án đúng: A

Trong DOCX, thông số lề và kích thước giấy thường gắn với đâu?
A. Siêu dữ liệu ngày tạo trong phần core properties
B. Thuộc tính màu chữ của từng paragraph riêng
C. Thiết lập trang trong section tương ứng
D. Các style đánh số của bảng dữ liệu
Đáp án đúng: C

Khi tài liệu có hai phần cần hướng giấy khác nhau, phương án nào phù hợp?
A. Tạo các section với thiết lập trang riêng biệt
B. Chỉ tăng độ rộng của cột trong bảng cuối
C. Chỉ đổi hướng giấy của một run nằm giữa tài liệu
D. Đặt một hyperlink tại chỗ cần xoay trang
Đáp án đúng: A

Khi cần mở đoạn mới ở trang kế tiếp, giải pháp nào phù hợp?
A. Chèn thêm thật nhiều dấu cách ở cuối dòng
B. Chèn đoạn không có chữ đến đủ chiều cao
C. Ngắt trang hoặc page break trước đoạn
D. Chèn ảnh trắng để đẩy nội dung qua trang
Đáp án đúng: C

Để hạn chế tiêu đề bị tách khỏi đoạn ngay sau nó, nên dùng gì?
A. Thuộc tính đổi tên tác giả của phần tài liệu
B. Thuộc tính keepWithNext để giữ đoạn theo sau
C. Thuộc tính đặt URL cho phần thân tài liệu
D. Thuộc tính tự nén văn bản trong tệp ZIP
Đáp án đúng: B

Trong bảng DOCX, cấu trúc dữ liệu cơ bản nào là phù hợp?
A. Bảng gồm các hàng, hàng gồm ô có nội dung
B. Bảng chứa run, run chứa hàng, hàng chứa các ô
C. Bảng chứa style, style chứa hàng, hàng chứa ô
D. Bảng gồm style, style gồm hàng và ô
Đáp án đúng: A

Với XWPFTable, muốn thêm hàng để nhập dữ liệu, bạn cần thao tác gì?
A. Ghi lại tệp ZIP trước khi thêm từng ô mới
B. Đổi toàn bộ đoạn văn trong bảng thành hyperlink
C. Tạo section mới rồi chuyển bảng sang section đó
D. Tạo hoặc chèn hàng và cập nhật các ô của hàng
Đáp án đúng: D

Trong một ô bảng Word, nội dung nào có thể tồn tại?
A. Một danh sách style nhưng không có nội dung
B. Nhiều đoạn văn và cả bảng lồng bên trong
C. Chỉ một run và không thể có thêm đoạn
D. Chỉ một chuỗi văn bản không có định dạng
Đáp án đúng: B

Trong OOXML, thuộc tính nào thường dùng để gộp ô theo chiều ngang?
A. numId xác định danh sách số của một đoạn
B. rId là mã quan hệ bên ngoài
C. gridSpan là số cột ô trải rộng
D. vMerge mô tả dãy hàng của một ô gộp dọc
Đáp án đúng: C

Trong OOXML, cơ chế nào thường mô tả ô gộp theo chiều dọc?
A. gridSpan với số cột sử dụng trong mỗi ô
B. vMerge với cờ bắt đầu hoặc tiếp tục
C. pStyle với tên style áp dụng cho paragraph
D. rFonts chỉ định phông của một run
Đáp án đúng: B

Khi đặt chiều rộng cột bảng, vì sao vẫn cần xem layout của bảng?
A. Các comment thường tự đặt lại chiều rộng trang
B. Thứ tự ảnh nhúng luôn xác định chiều rộng cột
C. Cơ chế tự co giãn ảnh hưởng độ rộng thực tế
D. Ngày tạo tệp có thể thay đổi độ rộng từng ô bảng
Đáp án đúng: C

Muốn hàng tiêu đề của bảng lặp lại trên trang sau, nên chú ý gì?
A. Thuộc tính chỉ số ảnh dùng trong từng hàng
B. Thuộc tính bắt buộc đổi style của mọi ô trong bảng
C. Bật chế độ lặp hàng tiêu đề của bảng
D. Thuộc tính tên tác giả của toàn bộ tài liệu DOCX
Đáp án đúng: C

Khi không muốn một hàng bảng bị tách qua nhiều trang, cần kiểm tra gì?
A. Thiết lập liên kết tới tệp hình của hàng dữ liệu
B. Thiết lập số thứ tự mặc định của paragraph đầu tiên
C. Thiết lập phiên bản thư viện Java đang sử dụng
D. Cấu hình hạn chế việc tách một hàng khi phân trang
Đáp án đúng: D

Khi trích xuất dữ liệu từ bảng lồng trong ô, nên làm gì?
A. Chuyển mọi ô thành chuỗi bằng dấu cách cố định
B. Giả định ô chỉ có một đoạn văn và đọc đoạn đầu
C. Duyệt các phần tử nội dung trong ô theo thứ tự
D. Chỉ lấy hàng bảng ngoài, bỏ bảng lồng
Đáp án đúng: C

Khi cấu trúc bảng có ô gộp, cách nào an toàn hơn để đọc dữ liệu?
A. Tái dựng lưới từ thông tin ô gộp
B. Bỏ qua ô trống và nối các giá trị theo thứ tự
C. Coi mọi hàng đều có cùng số ô vật lý trong XML
D. Lấy chỉ số cột chỉ bằng vị trí run trong mỗi ô
Đáp án đúng: A

Để chèn ảnh vào nội dung đoạn, thao tác XWPF nào thường phù hợp?
A. Thêm ảnh bằng cách đổi siêu dữ liệu tài liệu
B. Chèn ảnh vào thuộc tính số trang
C. Thêm ảnh bằng cách thay nội dung của styles.xml
D. Chèn ảnh qua run của đoạn văn tương ứng
Đáp án đúng: D

Khi đặt kích thước ảnh chèn trong XWPF, cần chú ý đơn vị nào?
A. Điểm ảnh màn hình luôn được lưu trực tiếp trong XML
B. Số lượng run dùng để tính kích thước hình vẽ
C. Dùng EMU để biểu diễn kích thước trong DrawingML
D. Đơn vị byte dùng để xác định chiều rộng và cao
Đáp án đúng: C

Trong DOCX, một hình ảnh được tham chiếu từ nội dung qua cơ chế nào?
A. Chỉ số trang trong bố cục tài liệu
B. Tên tệp được chép vào mọi run chứa hình ảnh
C. Tên style của đoạn ngay trước vị trí chèn ảnh
D. Quan hệ tới phần ảnh theo mã tham chiếu rId
Đáp án đúng: D

Khi trích xuất ảnh kèm vị trí xuất hiện, vì sao chỉ lấy danh sách ảnh là chưa đủ?
A. Danh sách ảnh không tự nêu chỗ ảnh được tham chiếu
B. Danh sách ảnh luôn sắp theo số trang hiển thị
C. Danh sách ảnh loại bỏ dữ liệu nhị phân khi đọc tệp
D. Danh sách ảnh luôn trả về chuỗi văn bản đã dàn trang
Đáp án đúng: A

Khi gặp ảnh nổi với cách neo phức tạp, nên tiếp cận ra sao?
A. Xem DrawingML nếu XWPF thiếu hỗ trợ trực tiếp
B. Bỏ qua mọi quan hệ trong gói DOCX để tìm ảnh
C. Chỉ đổi thuộc tính màu chữ của paragraph chứa ảnh
D. Chuyển mọi hình nổi thành tên tệp thuần văn bản
Đáp án đúng: A

Khi thêm hyperlink vào một đoạn DOCX, thông tin nào cần duy trì?
A. Chỉ số các ô gộp trong bảng Word
B. Chữ hiển thị và quan hệ URL tương ứng
C. Số lượng trang đã được Word dàn và hiển thị
D. Kích thước giấy và tên phông của mọi section
Đáp án đúng: B

Header và footer của DOCX thường được quản lý gắn với đâu?
A. Mỗi run mặc định chứa nguyên một header và footer
B. Phần header và footer được liên kết bởi section
C. Một hàng ẩn trong bảng đầu tiên của tài liệu
D. Chỉ các giá trị metadata tiêu đề và tác giả
Đáp án đúng: B

Để trang đầu có header khác các trang sau, cần thiết lập gì?
A. Đặt chế độ header riêng cho trang đầu
B. Số trang bắt đầu bằng giá trị âm trong section
C. Một bảng rỗng trong footer của trang cuối
D. Một đoạn văn rỗng được đặt đầu thân tài liệu
Đáp án đúng: A

Khi chèn số trang tự động vào footer, nên dùng cơ chế gì?
A. Tên tệp DOCX được nối vào cuối mọi trang
B. Một chữ số viết thẳng vào run của footer
C. Chỉ số hàng cuối trong bảng của tài liệu
D. Trường PAGE thể hiện số trang hiện tại
Đáp án đúng: D

Khi tạo trường tổng số trang, điều gì cần lưu ý?
A. Tổng số trang lưu trong tên tệp ảnh
B. POI luôn tính đầy đủ số trang ngay khi ghi tệp
C. Trình đọc cần cập nhật giá trị trường
D. Mỗi section chỉ có thể xuất hiện một trường số
Đáp án đúng: C

Khi tài liệu có nhiều section, header của section sau có thể thế nào?
A. Luôn gắn trực tiếp vào run đầu của document.xml
B. Kế thừa header cũ hoặc liên kết phần mới
C. Chỉ tồn tại nếu mỗi trang đều chứa một bảng
D. Luôn được tạo hoàn toàn mới trong mọi trường hợp
Đáp án đúng: B

Khi cần đặt thông tin tiêu đề và tác giả tài liệu, nơi nào phù hợp?
A. Mỗi hàng đầu tiên của các bảng trong tài liệu
B. Phần core properties trong metadata của DOCX
C. Mọi thuộc tính màu và phông của đoạn đầu tiên
D. Chỉ các quan hệ hình ảnh dưới word/media
Đáp án đúng: B

Khi sửa nội dung nằm tại một bookmark, điều gì cần bảo toàn?
A. Cùng số lượng tệp ảnh đã có trong phần media
B. Giá trị numId của paragraph liền trước bookmark
C. Mức nén ZIP ban đầu của toàn bộ gói DOCX
D. Giữ đúng cặp mốc bookmarkStart và bookmarkEnd
Đáp án đúng: D

Đối với content control trong biểu mẫu Word, thành phần nào cần xem xét?
A. Chỉ các style của đoạn trong biểu mẫu
B. Các SDT kèm thuộc tính và nội dung tương ứng
C. Chỉ dữ liệu ngày chỉnh sửa trong core properties
D. Chỉ danh sách ảnh nhúng mà không cần nội dung
Đáp án đúng: B

Khi trích xuất tài liệu có tracked changes, cần xác định điều gì?
A. Độ rộng lề của section cuối cùng trong tài liệu
B. Chọn bản gốc, phần thêm hoặc phần đã xóa
C. Kiểu nén ảnh trong run đã sửa đổi
D. Bảng mã hệ thống của máy đã cài đặt Word
Đáp án đúng: B

Khi đọc footnote hoặc comment, vì sao không chỉ đọc thân tài liệu?
A. Nội dung nằm ở phần riêng và có tham chiếu
B. Chúng luôn được lưu thành ảnh bên trong header
C. Chúng chỉ xuất hiện dưới dạng tên file ZIP
D. Chúng luôn được trộn vào đoạn đầu tiên của thân
Đáp án đúng: A

Nếu placeholder bị chia qua nhiều run, cách xử lý nào phù hợp?
A. Đổi placeholder thành tên tệp trước đọc
B. Tìm từng run riêng và bỏ qua các phần bị tách
C. Chỉ thay thế khi mỗi dấu ngoặc ở một paragraph
D. Tìm chuỗi logic rồi ánh xạ trở về các run
Đáp án đúng: D

Khi nhân bản hàng mẫu trong bảng, phần nào cần giữ hoặc điều chỉnh?
A. Giữ cấu trúc hàng, định dạng ô và tham chiếu
B. Chỉ số trang của section chứa bảng dữ liệu
C. Chỉ nội dung chữ của ô đầu tiên trong hàng mẫu
D. Chỉ ngày tạo và tên tác giả của tài liệu mẫu
Đáp án đúng: A

Với vùng có điều kiện trong template DOCX, cách nào đáng tin cậy hơn?
A. Dựa vào số thứ tự dòng hiển thị trên một trang
B. Chỉ tìm các trang có cùng kích thước phông chữ
C. Đánh dấu và xử lý vùng theo cấu trúc Word
D. Xóa mọi đoạn chứa ký tự dấu cách trong tài liệu
Đáp án đúng: C

Để tránh xuất DOCX còn thiếu trường bắt buộc, cần thêm bước nào?
A. Chỉ đổi toàn bộ ký tự của tài liệu thành chữ in đậm
B. Chỉ bật chế độ nén cao nhất khi ghi tệp Word
C. Kiểm tra dữ liệu đầu vào và placeholder chưa thay
D. Chỉ thêm ngày tạo mới cho mọi lần sinh tài liệu
Đáp án đúng: C

Khi người dùng chỉnh sửa template, cơ chế nào giúp phát hiện mẫu sai?
A. Xác thực cấu trúc và các trường của mẫu
B. Chỉ kiểm tra phần mở rộng của tệp là .docx
C. Giả định placeholder thuộc cùng run
D. Bỏ qua các bảng và chỉ kiểm tra đoạn văn đầu
Đáp án đúng: A

Để giảm chi phí khi sinh nhiều tài liệu, cách nào phù hợp?
A. Chia sẻ cùng một XWPFDocument để mọi luồng cùng sửa
B. Giới hạn công việc đồng thời và đóng tài nguyên
C. Mở lại cùng một template sau từng câu chữ được ghi
D. Giữ toàn bộ tài liệu kết quả trong RAM đến cuối ngày
Đáp án đúng: B

Với xử lý đa luồng, rủi ro của việc chia sẻ một XWPFDocument để sửa là gì?
A. Sửa đồng thời dễ làm sai trạng thái đối tượng
B. POI tự sao chép các đoạn trước khi sửa
C. Tệp đầu ra luôn được mã hóa dù không đặt mật khẩu
D. Các đối tượng XWPF tự chuyển sang chỉ đọc giữa các luồng
Đáp án đúng: A

Để tránh để lại tệp DOCX kết quả ghi dở, nên áp dụng gì?
A. Ghi ra tệp tạm rồi thay thế đích sau khi hoàn tất
B. Xóa tệp đích trước rồi tạo nhiều luồng ghi song song
C. Bỏ qua lỗi đầu ra và tiếp tục dùng tệp đang dở
D. Ghi trực tiếp lên tệp đích và đóng tệp khi gặp lỗi
Đáp án đúng: A

Vì DOCX là gói ZIP, khi nhận tệp không tin cậy cần phòng ngừa gì?
A. Dùng tên tệp ngắn hơn để tránh quá tải bộ nhớ
B. Chỉ đổi tên .docx thành .zip rồi đọc không giới hạn
C. Tắt mọi phép kiểm tra phần mở rộng của tệp
D. Giới hạn giải nén và phát hiện ZIP bất thường
Đáp án đúng: D

Khi DOCX có quan hệ tới nguồn bên ngoài, rủi ro nào cần cân nhắc?
A. Việc phát sinh thêm trang do đặt lề quá hẹp
B. Việc xuất hiện thêm một cột không có trong bảng
C. Thay phông của một số tiêu đề nhỏ
D. Có thể gây truy cập ngoài hoặc lộ thông tin
Đáp án đúng: D

Khi mở DOCX bị thiếu phần được tham chiếu, ứng dụng nên làm gì?
A. Thêm các phần trống mà không kiểm tra quan hệ
B. Bỏ qua mọi lỗi rồi xuất dữ liệu như thể đầy đủ
C. Báo lỗi cấu trúc kèm phần tham chiếu sai
D. Đổi phông rồi thử mở lại tệp DOCX
Đáp án đúng: C

Khi cần chỉnh tính năng chưa có API XWPF thuận tiện, lựa chọn nào hợp lý?
A. Chỉnh byte ZIP tại vị trí cố định mà không đọc XML
B. Chuyển file thành văn bản thuần rồi đổi tên .docx
C. Giả định Word luôn tự tạo lại mọi phần bị thiếu
D. Thao tác OOXML cấp thấp cùng kiểm tra tương thích
Đáp án đúng: D

Khi nâng cấp Apache POI, cần kiểm tra yếu tố nào?
A. Chỉ tên thư mục chứa kết quả đã xuất
B. API, các phụ thuộc và mẫu điển hình
C. Chỉ màu nền mặc định của trình soạn thảo
D. Chỉ tốc độ mạng của máy lập trình viên
Đáp án đúng: B

Nếu cần chuyển DOCX sang PDF trong Java, phát biểu nào đúng?
A. Đổi phần mở rộng của DOCX là đủ tạo PDF hợp lệ
B. Cần công cụ chuyển đổi có khả năng dàn trang
C. Tạo InputStream mới sẽ tự sinh bản PDF tương đương
D. Gọi XWPFDocument.write để xuất PDF
Đáp án đúng: B

Sau khi sinh một DOCX, phép kiểm thử cấu trúc nào có ích?
A. Mở lại tệp để xác minh đoạn, bảng và ảnh
B. So sánh riêng kích thước tệp với ảnh mẫu gốc
C. Chỉ đối chiếu tên tệp với tên của template
D. Kiểm tra số byte có chia hết cho kích thước trang
Đáp án đúng: A

Vì sao không nên so sánh hai DOCX chỉ bằng byte ZIP?
A. Word luôn lưu mọi bảng dưới dạng ảnh khi mở lại
B. Metadata ZIP khác nhau dù nội dung giống
C. Đoạn văn đổi bảng mã sau khi lưu
D. DOCX luôn được mã hóa ngẫu nhiên mỗi khi ghi tệp
Đáp án đúng: B

Khi kiểm tra tương thích giữa Word và LibreOffice, nên làm gì?
A. Mở tài liệu mẫu trên cả hai trình đọc
B. Chỉ xem nội dung của phần core properties
C. Chỉ so sánh đuôi tệp với định dạng dự kiến
D. Chỉ xem DOCX có giải nén được
Đáp án đúng: A

Nếu tệp hiển thị lệch dòng trên máy khác, nguyên nhân nào hợp lý?
A. Dữ liệu bảng luôn được chuyển thành ảnh khác
B. Phần mở rộng .docx tự động thay đổi giữa hai máy
C. Phông dự phòng và bộ dàn trang có thể khác nhau
D. Số lượng file ZIP luôn chi phối chính xác số trang
Đáp án đúng: C

Khi nội dung có bảng lồng, ảnh và tiếng Việt, kiểm thử nào tốt nhất?
A. Chỉ kiểm tra ảnh đầu tiên của tệp
B. Chỉ đếm số đoạn văn đứng ngoài tất cả các bảng
C. So nội dung và cấu trúc khi mở lại DOCX
D. Chỉ so sánh tổng số ký tự ASCII trước và sau
Đáp án đúng: C

Trong quy trình tự động sinh Word, nên xử lý lỗi theo cách nào?
A. Gộp mọi lỗi thành thông báo không rõ nguyên nhân
B. Phân loại lỗi dữ liệu, mẫu, I/O và định dạng
C. Chỉ thử ghi lại vô hạn lần dù tệp đang bị hỏng
D. Bỏ qua lỗi không liên quan đến tên tệp đầu ra
Đáp án đúng: B
