Cấu trúc nào quyết định thứ tự trang trong PDF?
A. Thứ tự content stream được tạo trước
B. Thứ tự object trong bảng cross-reference
C. Thứ tự resource dictionary được khai báo
D. Cây Page được tham chiếu từ catalog
Đáp án đúng: D

Khi đặt nội dung bằng tọa độ PDF, cần tính đến yếu tố nào?
A. Thứ tự text operator trong stream
B. Độ lớn font đang dùng trên trang
C. Hộp trang và ma trận tọa độ hiện hành
D. Giá trị MediaBox và bỏ qua rotation
Đáp án đúng: C

Để hiển thị Unicode tiếng Việt ổn định, nên ưu tiên gì?
A. Chuyển mọi chuỗi thành WinAnsiEncoding
B. Nhúng font có đủ glyph cần thiết
C. Đặt ToUnicode map mà bỏ font
D. Chọn Base14 font không kèm dữ liệu glyph
Đáp án đúng: B

Mục đích chính khi nhúng subset font vào PDF là gì?
A. Bỏ cmap để giảm kích thước tối đa
B. Chuyển font vector thành ảnh bitmap
C. Giữ toàn bộ bộ glyph để dễ tìm kiếm
D. Nhúng subset glyph đã sử dụng
Đáp án đúng: D

Vì sao PDF tự vẽ text không tự chia trang?
A. Bố trí là thao tác đặt vị trí tường minh
B. PDF không cho phép nhiều đoạn trong trang
C. Mọi trang chỉ có đúng một content stream
D. Mọi text stream chỉ hỗ trợ một dòng
Đáp án đúng: A

Khi vẽ bảng nhiều trang bằng thư viện PDF, cần gì?
A. Chèn tất cả hàng rồi sửa số trang
B. Tính chiều cao và xử lý ngắt trang
C. Chia đều hàng bất kể chiều cao chữ
D. Tăng giới hạn kích thước content stream
Đáp án đúng: B

Làm sao giữ đúng tỉ lệ ảnh khi chèn vào PDF?
A. Co đều theo cả hai chiều của ảnh
B. Kéo ngang theo lề trái và phải
C. Dùng kích thước trang làm chiều ảnh
D. Giảm chiều cao để vừa trang
Đáp án đúng: A

Trong PDFBox, PDDocument có vai trò nào?
A. Quản lý lệnh vẽ cho một trang
B. Quản lý mô hình tài liệu và trang
C. Đóng vai trò trình đánh giá chữ ký
D. Chứa thông tin font được nhúng
Đáp án đúng: B

PDPageContentStream trong PDFBox dùng chủ yếu để làm gì?
A. Giải mã toàn bộ tệp đính kèm
B. Ghi các lệnh vẽ lên một trang
C. Phân tích chứng thư trong chữ ký
D. Thêm mục lục ngoài cây tài liệu
Đáp án đúng: B

Sau khi xuất PDF bằng Java, thao tác nào cần thiết?
A. Đóng tài liệu và stream đúng vòng đời
B. Giải phóng font rồi giữ stream
C. Đợi GC tự xử lý các stream đã mở
D. Đóng FileOutputStream nhưng giữ document
Đáp án đúng: A

Khi chọn iText hoặc OpenPDF, yếu tố nào cần xem trước?
A. Mức hỗ trợ đổi tên phương thức
B. Số lượng file class trong JAR
C. Tốc độ biên dịch mã nguồn
D. Giấy phép của phiên bản thư viện
Đáp án đúng: D

Để tránh lỗi khi tạo PDF đồng thời, nên làm gì?
A. Dùng document riêng cho mỗi tác vụ
B. Chia sẻ một content stream giữa các luồng
C. Cho nhiều luồng sửa chung một PDPage
D. Dùng một OutputStream chung cho mọi tệp
Đáp án đúng: A

Vì sao HTML sang PDF dễ lệch bố cục so với browser?
A. PDF buộc mọi phần tử nằm một cột
B. HTML không cho phép dùng font trong PDF
C. Engine kết xuất hỗ trợ CSS khác nhau
D. Trình duyệt luôn dùng đơn vị khác CSS
Đáp án đúng: C

Quy trình chuyển Markdown có cấu trúc sang PDF phù hợp là gì?
A. Phân tích Markdown rồi kết xuất PDF
B. Chuyển mã nguồn Markdown thành ảnh
C. Nối toàn bộ các dòng rồi xuất text
D. Đổi trực tiếp extension .md sang .pdf
Đáp án đúng: A

Khi render HTML với web font, điều gì quan trọng?
A. Đổi font-weight sang giá trị 400
B. Khai báo font-family là đủ mọi máy
C. Dùng @media screen để xuất PDF
D. Engine có thể truy cập và nhúng font
Đáp án đúng: D

Vì sao text extraction từ PDF có thể sai thứ tự đọc?
A. Mỗi trang chỉ được trích từ cuối lên đầu
B. Văn bản trong PDF luôn được sắp theo từ điển
C. Lệnh vẽ không bảo đảm thứ tự ngữ nghĩa
D. Bảng xref luôn đảo thứ tự từng từ
Đáp án đúng: C

PDF được scan thành hình ảnh cần bước gì để lấy chữ?
A. Tăng độ phân giải khi render PDF
B. Nhận dạng ký tự bằng OCR phù hợp
C. Thay thế font mặc định của PDF
D. Đọc ToUnicode map của ảnh bitmap
Đáp án đúng: B

Khi trích ảnh từ PDF, điều gì cần phân biệt?
A. Content stream với lớp bảo mật tệp
B. Image XObject với nội dung vector
C. Annotation liên kết với trường form
D. Outline bookmark với metadata trang
Đáp án đúng: B

Khi ghép PDF từ nhiều nguồn, điều gì cần giữ nguyên?
A. Giữ tham chiếu tài nguyên của trang
B. Chuỗi text được trích từ trang
C. Nội dung metadata của file đầu
D. Thứ tự byte của các object gốc
Đáp án đúng: A

Khi tách PDF, cách nào giúp giữ nguyên nội dung trang?
A. Tái tạo trang bằng văn bản trích xuất
B. Cắt file theo các offset byte
C. Sao chép trang kèm tài nguyên tham chiếu
D. Tạo trang cùng kích thước gốc
Đáp án đúng: C

Outline hay bookmark trong PDF chủ yếu phục vụ gì?
A. Phân quyền chỉnh sửa từng dòng chữ
B. Tối ưu nén hình ảnh giữa các trang
C. Điều hướng theo mục lục phân cấp
D. Mã hóa tài liệu bằng chứng thư số
Đáp án đúng: C

Để tạo hyperlink nhấp được trên trang PDF, cần gì?
A. Thêm URL vào metadata trang
B. Dùng annotation có đích liên kết
C. Tạo một text field không giá trị
D. Gạch chân và tô màu văn bản
Đáp án đúng: B

Trường trong PDF AcroForm biểu diễn điều gì?
A. Mục lục điều hướng từ trang đầu
B. Lệnh vẽ cố định trên canvas trang
C. Nhóm object nén riêng cho ảnh
D. Trường cho nhập hoặc chọn dữ liệu
Đáp án đúng: D

Khi flatten AcroForm, kết quả mong đợi là gì?
A. Đưa giá trị field thành phần hiển thị tĩnh
B. Tự động ký số mọi trường sau khi điền
C. Đổi field thành các liên kết ngoài tài liệu
D. Giữ field chỉnh sửa và chỉ khóa metadata
Đáp án đúng: A

Điều gì làm một chữ ký số PDF có thể kiểm chứng?
A. Tên người ký trong thuộc tính Author
B. Chữ ký mật mã bảo vệ dữ liệu được ký
C. Ảnh chữ ký sắc nét đặt vào trang cuối
D. Dấu thời gian ghi thủ công vào footer
Đáp án đúng: B

Vì sao thay đổi PDF sau ký có thể làm chữ ký không hợp lệ?
A. Số trang luôn tự tăng sau thao tác lưu
B. Mọi font tự chuyển sang một mã hóa khác
C. Byte thuộc phạm vi ký bị thay đổi
D. Outline của tài liệu tự bị xóa sạch
Đáp án đúng: C

Đâu là cách hiểu đúng về bảo vệ PDF bằng mật khẩu?
A. Mật khẩu user luôn loại bỏ được metadata
B. Đổi mật khẩu không cần xem thuật toán mã hóa
C. Hạn chế in luôn chống được mọi công cụ
D. Mã hóa và giới hạn quyền là hai khía cạnh
Đáp án đúng: D

Khi cần xóa bí mật khỏi PDF, biện pháp nào an toàn?
A. Thu nhỏ chữ về kích thước thấp
B. Đổi màu chữ sang nền trắng
C. Redact thực sự xóa nội dung nguồn
D. Đặt khối màu đen che vùng chữ
Đáp án đúng: C

Đối với lưu trữ PDF lâu dài, cần xem xét gì?
A. Các yêu cầu tương thích của PDF/A
B. Ghi năm vào tên tệp đầu ra
C. Sử dụng độ nén ảnh cao nhất
D. Giữ dữ liệu OCR và bỏ các trang
Đáp án đúng: A

Vì sao cần kiểm tra font fallback trong báo cáo tiếng Việt?
A. Fallback luôn giữ nguyên độ rộng từng glyph
B. Fallback luôn chuyển mọi chữ sang font nhúng
C. Font Unicode nào cũng có cùng bảng glyph
D. Font thay thế có thể thiếu glyph và sai bố cục
Đáp án đúng: D

Khi xuất PDF chứa dữ liệu nhạy cảm, metadata nên được xử lý ra sao?
A. Dùng metadata thay cơ chế phân quyền truy cập
B. Đưa toàn bộ thông tin tài khoản vào Author
C. Ghi token xác thực vào trường Producer
D. Loại bỏ metadata nhạy cảm trước khi xuất
Đáp án đúng: D

Điều gì tăng khả năng tiếp cận PDF cho trình đọc màn hình?
A. Tăng độ phân giải trang PDF
B. Tô màu các heading thật đậm
C. Tag cấu trúc và thứ tự đọc hợp lý
D. Chuyển toàn bộ trang thành hình ảnh
Đáp án đúng: C

Vì sao footer có thể đè lên bảng cuối trang?
A. Lề dưới chưa dành chỗ cho footer
B. File thiếu thông tin tên người tạo
C. Chưa bật chế độ nén content stream
D. Bảng thiếu định danh trong metadata
Đáp án đúng: A

Khi đánh số trang X trên Y trong PDF, thách thức chính là gì?
A. Không có cách đặt chữ vào footer
B. Chỉ biết số trang sau khi dàn trang
C. Mỗi trang có giới hạn một số nguyên
D. PDF không cho chèn tổng số trang
Đáp án đúng: B

Khi thêm watermark, yếu tố nào cần kiểm soát?
A. Cần xét thứ tự vẽ và opacity
B. Tốc độ mạng khi xuất file
C. Tên font dùng trong tên tệp
D. Số lượng từ của metadata
Đáp án đúng: A

Để kiểm soát bộ nhớ khi tạo PDF lớn, cách nào phù hợp?
A. Tạo một font mới cho mỗi dòng văn bản
B. Giải phóng tài nguyên theo giai đoạn
C. Giữ mọi ảnh giải nén tới cuối quá trình
D. Tạo bản sao toàn bộ trang sau mỗi lần vẽ
Đáp án đúng: B

Vì sao PDF ít trang vẫn có dung lượng lớn?
A. Số lượng thuộc tính của Page object
B. Nhiều chữ in hoa trong file nguồn
C. Ảnh lớn hoặc font nhúng dư
D. Thiếu mục lục bookmark cho tài liệu
Đáp án đúng: C

Cách giảm dung lượng ảnh PDF mà vẫn dễ đọc là gì?
A. Đổi tên hình ảnh đã được nhúng
B. Chuyển mọi ảnh sang một bảng font
C. Tăng không giới hạn kích thước trang
D. Giảm độ phân giải và nén phù hợp
Đáp án đúng: D

Khi mở PDF không tin cậy trong ứng dụng, nên làm gì?
A. Tin vào phần mở rộng để bỏ qua kiểm tra
B. Cho parser quyền truy cập hệ thống rộng
C. Giới hạn tài nguyên của bộ phân tích
D. Tắt mọi giới hạn tài nguyên của thư viện
Đáp án đúng: C

Trong kiểm thử tạo PDF, kiểm chứng nào có ý nghĩa?
A. Kiểm tra file được tạo cùng ngày
B. Kiểm tra trang, text và bố cục file
C. Kiểm tra tệp có tên kết thúc .pdf
D. Kiểm tra hàm Java trả về non-null
Đáp án đúng: B

Để so sánh PDF trước và sau refactor, nên kết hợp gì?
A. So sánh đường dẫn thư mục xuất
B. So sánh hash byte của hai file
C. Đối chiếu text và hình render
D. So sánh thuộc tính CreatedDate
Đáp án đúng: C

Khi HTML có bảng nhiều trang, cần test điểm nào?
A. Tên file HTML có khoảng trắng
B. Nội dung thuộc tính alt của ảnh
C. Chiều dài tiêu đề metadata PDF
D. Ngắt hàng, lặp tiêu đề và lề
Đáp án đúng: D

Vì sao thư viện PDF không tự thay thế được OCR?
A. Mọi hình scan đều có sẵn glyph map
B. Mọi PDF đều chứa text đã mã hóa đúng
C. OCR chỉ dùng để ghép tài liệu PDF
D. Vẽ PDF không thể tự nhận dạng chữ
Đáp án đúng: D

Khi chèn ảnh chữ ký vào trang, điều nào đúng?
A. Ảnh PNG luôn đi kèm chứng thư số
B. Ảnh chữ ký không thay chữ ký số
C. Độ nét ảnh quyết định xác thực chữ ký
D. Tên ảnh đủ để xác nhận người ký
Đáp án đúng: B

Khi đánh giá engine HTML-to-PDF, ưu tiên khả năng nào?
A. Xử lý HTML bằng regex từng dòng
B. CSS in ấn và khả năng nhúng font
C. Tạo ảnh rồi đổi đuôi thành PDF
D. Hỗ trợ screenshot của trang web
Đáp án đúng: B

Với PDF có nhiều khổ và hướng trang, cần xử lý gì?
A. Xét khổ và rotation của mỗi trang
B. Chiều rộng của trang cuối cùng
C. Kích thước trang đầu tiên
D. Tỷ lệ nén áp dụng toàn tài liệu
Đáp án đúng: A

Vì sao chữ vẽ ở tọa độ cố định có thể bị cắt?
A. Content stream không cho xuống dòng
B. Text stream luôn cắt tại ký tự thứ 100
C. Text có thể vượt phạm vi tọa độ vẽ
D. PDF tự bỏ ký tự sau dấu chấm cuối
Đáp án đúng: C

Khi đọc form PDF, thuộc tính nào cần xem xét?
A. Kiểu field và giá trị hiện hành
B. Phiên bản Java của người tạo
C. Cỡ giấy khai báo ở trang đầu
D. Tên file lưu trữ trên đĩa
Đáp án đúng: A

Để hỗ trợ văn bản đa ngôn ngữ trong PDF, cần gì?
A. Chuyển hết sang encoding Latin-1
B. Đổi chiều rộng trang theo ngôn ngữ
C. Dùng một Base14 font mặc định
D. Glyph và shaping cho hệ chữ
Đáp án đúng: D

Trong luồng xuất PDF cần ký số, thứ tự nào phù hợp?
A. Hoàn thiện tài liệu trước khi ký số
B. Ký số trước khi nhúng font còn thiếu
C. Ký số rồi thay đổi metadata tùy ý
D. Ký số trước khi thêm các trang nội dung
Đáp án đúng: A
