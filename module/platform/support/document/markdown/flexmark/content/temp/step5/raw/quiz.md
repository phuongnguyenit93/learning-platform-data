Trong flexmark-java, thành phần nào chuyển Markdown thành mô hình có thể duyệt?
A. HtmlRenderer chuyển trực tiếp chuỗi nguồn thành các node AST
B. Parser phân tích nguồn thành cây AST với các node tài liệu
C. Formatter tạo mô hình dữ liệu trước khi mọi phân tích bắt đầu
D. Extension tự xây cây AST mà không cần một bộ Parser
Đáp án đúng: B

Sau khi parse Markdown thành AST, thành phần nào thường tạo HTML?
A. HtmlRenderer xuất HTML từ cây AST đã được phân tích
B. Parser tự đổi mọi node sang HTML khi hoàn thành phân tích
C. Formatter chuyển AST thành HTML để hiển thị trên trình duyệt
D. DataSet ghép tên node thành các thẻ HTML khi ghi cấu hình
Đáp án đúng: A

Vai trò chính của Formatter trong flexmark-java là gì?
A. Kết xuất AST lại thành Markdown theo quy tắc định dạng
B. Đánh giá mã Java trong các fenced code block của tài liệu
C. Chuyển mọi thẻ HTML nhúng thành CSS để thống nhất bố cục
D. Tính toán các liên kết ngoài và tải trước tài nguyên từ URL
Đáp án đúng: A

CommonMark đóng vai trò gì khi dùng flexmark-java?
A. Yêu cầu mọi tài liệu Markdown phải khai báo extension cho từng đoạn
B. Tự định nghĩa cấu trúc bảng nâng cao cho mọi parser không cấu hình
C. Cung cấp quy tắc cú pháp Markdown cơ sở để phân tích nhất quán
D. Định nghĩa cách CSS tô màu các thẻ HTML khi kết xuất
Đáp án đúng: C

Khi muốn hỗ trợ bảng theo cú pháp mở rộng, cần làm gì?
A. Bật extension bảng trong cấu hình parser và renderer
B. Thêm thuộc tính table=true vào từng Heading của tài liệu
C. Đổi phần mở rộng .md thành .html mà không đổi nội dung
D. Dùng Formatter để tự suy ra bảng từ mọi đoạn có dấu gạch
Đáp án đúng: A

Nếu Parser và HtmlRenderer dùng cấu hình extension không tương thích, rủi ro nào xuất hiện?
A. Nội dung sẽ tự động chuyển thành XML bất kể cấu hình đã chọn
B. Các link được chuyển thành hình ảnh nếu renderer không nhận node
C. Node đã parse có thể không render đúng theo extension dự kiến
D. Trình biên dịch Java sẽ thay đổi kiểu dữ liệu các node AST
Đáp án đúng: C

Một quy trình chuyển tài liệu Markdown thành HTML hợp lý là gì?
A. Parse Markdown thành Document rồi render AST sang HTML
B. Render Markdown ra HTML trước rồi parse lại như nguồn Mermaid
C. Format trực tiếp Java source rồi dùng HTML parser tạo markdown
D. Xây dữ liệu CSV từ Markdown rồi chuyển CSV thành thẻ HTML
Đáp án đúng: A

Vì sao AST hữu ích hơn thay chuỗi bằng regex khi chỉnh Markdown có cấu trúc?
A. AST tự chứng minh mọi liên kết Internet đều truy cập được khi render
B. Regex không thể tìm được bất kỳ dấu gạch hay dấu sao nào trong chuỗi
C. AST phân biệt loại node và quan hệ lồng nhau của các thành phần
D. AST tự bảo đảm tài liệu tuân thủ mọi chính sách bảo mật khi xuất HTML
Đáp án đúng: C

Node gốc của kết quả parse thường biểu diễn điều gì?
A. Heading chứa mọi bảng và danh sách của toàn bộ nguồn Markdown
B. Link chứa mọi đoạn văn và siêu dữ liệu dù tài liệu không có URL
C. Text chứa toàn bộ node chuyên biệt như code block và table
D. Document chứa các node con tương ứng cấu trúc của tài liệu
Đáp án đúng: D

Khi duyệt một cây AST, thông tin nào cần dùng để hiểu cấu trúc?
A. Thứ tự màu CSS của mỗi thẻ sau khi trình duyệt đã render
B. Tổng số request HTTP được thực hiện bởi trang đang hiển thị
C. Dựa vào quan hệ parent, child và sibling của các node AST
D. Tên tệp chứa thư viện Maven của từng loại node trong AST
Đáp án đúng: C

Muốn thu thập tất cả heading trong tài liệu, cách nào phù hợp?
A. Duyệt toàn bộ thẻ HTML đã được browser tính layout cuối cùng
B. Chuyển mọi dấu # thành dấu sao rồi đếm số lần xuất hiện
C. Duyệt AST và chọn node Heading theo cấp tiêu đề cần lấy
D. Dựa vào số dòng trống để suy ra mọi Heading của Markdown
Đáp án đúng: C

Trong AST, vì sao Paragraph và Heading không nên coi là cùng một loại node?
A. Chúng có cùng cấu trúc và chỉ khác nhau ở chiều rộng màn hình
B. Heading khác Paragraph về ngữ nghĩa dù cùng chứa văn bản inline
C. Paragraph luôn là block chứa bảng còn Heading luôn là URL
D. Heading không thể có văn bản thường nên buộc phải dùng Link
Đáp án đúng: B

Khi cần trích xuất văn bản, điều gì có thể xảy ra nếu chỉ lấy chuỗi nguồn của node?
A. Chuỗi nguồn đã loại bỏ mọi cú pháp Markdown và chỉ còn nội dung hiển thị
B. Ký hiệu Markdown và cấu trúc lồng nhau có thể lẫn vào nội dung văn bản
C. Trình parser sẽ tự giải mã mọi tài nguyên trong link rồi chèn vào chuỗi
D. AST sẽ tự thay mọi đường dẫn tương đối bằng URL tuyệt đối đã tải
Đáp án đúng: B

Với fenced code block, ứng dụng cần hiểu phần bên trong như thế nào?
A. Giữ mã như nội dung của block, không phân tích inline Markdown
B. Dấu sao bên trong code luôn tạo ra node nhấn mạnh riêng lẻ trong AST
C. Mỗi dòng code phải được chuyển thành Heading mới khi đọc tài liệu
D. Parser chạy thử đoạn mã để xác nhận cú pháp trước khi tạo AST
Đáp án đúng: A

Trong Markdown, một liên kết inline gồm thông tin chính nào cần giữ khi parse?
A. Tên bảng dữ liệu và bội số quan hệ trong mô hình ER
B. ID node và vị trí font sau khi trình duyệt dựng trang
C. Ngày biên dịch của ứng dụng và tên hệ thống lưu tài liệu
D. Giữ phần chữ hiển thị và địa chỉ đích của liên kết
Đáp án đúng: D

Khi xử lý reference link, điều gì cần được phân giải đúng?
A. Các reference link phải trỏ tới Heading có cùng tên trong trang
B. Định nghĩa tham chiếu được dùng để lựa chọn theme cho toàn bộ trang
C. Tham chiếu link tự tìm trang trên Internet nếu không có định nghĩa
D. Nhãn tham chiếu phải được liên kết với định nghĩa URL tương ứng
Đáp án đúng: D

Nếu một extension định nghĩa cú pháp riêng, nhiệm vụ nào thuộc phần tích hợp?
A. Thay đổi bytecode của Parser để nhận mọi cú pháp mới khi chạy
B. Gắn tên extension vào đuôi file mà không cập nhật cấu hình
C. Bật extension phù hợp cho Parser và renderer liên quan
D. Đổi mọi node được parse thành Text để giữ nguyên phân tích
Đáp án đúng: C

Đối với bảng Markdown, khi kiểm thử parser cần xác minh yếu tố nào?
A. Các cột phải có độ rộng pixel bằng nhau trên mọi trình duyệt
B. Các hàng, cột và nội dung ô được nhận diện theo extension bảng
C. Parser phải tự tính công thức như các ô trong một workbook Excel
D. Cú pháp bảng buộc phải nằm trong một thẻ HTML table sẵn có
Đáp án đúng: B

Thông tin ngay sau dấu mở của fenced code block thường phục vụ điều gì?
A. Mô tả ngôn ngữ hoặc metadata cho việc hiển thị khối mã
B. Quy định số lượng Heading được phép tồn tại trong phần tài liệu
C. Định nghĩa sẵn URL cho toàn bộ liên kết tương đối ở phía dưới
D. Xác định tên file Java sẽ tự chạy khi Markdown được kết xuất
Đáp án đúng: A

Khi xuất fenced code block sang HTML, cách xử lý nội dung nào an toàn?
A. Thực thi đoạn code để thay bằng kết quả trả về từ chương trình
B. Escape ký tự đặc biệt để đoạn mã hiển thị như văn bản trong HTML
C. Chuyển mọi toán tử dấu nhỏ hơn thành thẻ HTML đang hoạt động
D. Loại bỏ dấu nháy trong code mà không xem xét nội dung cần bảo toàn
Đáp án đúng: B

Nếu tài liệu có HTML viết trực tiếp bên trong Markdown, điều gì cần cân nhắc?
A. Parser buộc chuyển mọi HTML thô thành văn bản JSON hợp lệ
B. HTML nhúng luôn được bỏ qua kể cả khi cấu hình renderer cho phép
C. Cách renderer xử lý HTML thô và chính sách an toàn khi hiển thị
D. Các thẻ HTML được mặc định coi là một fenced code block
Đáp án đúng: C

Khi link Markdown có URL do người dùng nhập, ứng dụng nên kiểm tra điều gì?
A. Số ký tự của anchor text để tự xác thực quyền truy cập tài liệu
B. Màu link do theme chọn để xác định URL đã được kiểm duyệt hay chưa
C. Scheme và đích URL theo chính sách để tránh điều hướng nguy hiểm
D. Vị trí của Link trong AST vì node đứng đầu luôn được tin cậy
Đáp án đúng: C

Khi tài liệu có YAML front matter, cách xử lý phù hợp là gì?
A. Gán toàn bộ front matter vào thuộc tính mặc định của mọi node Text
B. Dùng extension hoặc bộ đọc metadata, không coi là CommonMark lõi
C. Dùng HtmlRenderer để tự kiểm tra schema YAML và sửa mọi trường sai
D. Đổi phần đầu tài liệu thành bảng vì CommonMark luôn parse metadata
Đáp án đúng: B

Khi mở rộng cú pháp cho footnote hoặc bảng, điều nào đúng?
A. Cú pháp mở rộng được coi là thành phần bắt buộc của CommonMark
B. Bất kỳ ký hiệu lạ nào cũng tự thành node mới mà không cần cấu hình
C. Thay đổi theme là đủ để parser hiểu cú pháp mở rộng
D. Khả năng hỗ trợ phụ thuộc extension và cấu hình đã được bật
Đáp án đúng: D

Nếu cần đánh dấu một loại node tùy biến trong tài liệu, lựa chọn nào phù hợp?
A. Viết extension parser/renderer xác định ngữ nghĩa node mới
B. Đổi tên Heading bất kỳ thành node mới mà không cấu hình bộ phân tích
C. Viết CSS tự tạo node AST cho cú pháp chưa tồn tại khi parse
D. Dùng Formatter xóa node hiện tại rồi dựa vào CSS để khôi phục lại
Đáp án đúng: A

Khi muốn render tài liệu có bảng, điều gì cần được kiểm tra?
A. Thêm tên table vào file để browser tự dựng các hàng
B. Bật extension bảng tương ứng khi parse và render
C. Dùng cùng số lượng Heading và Paragraph để bảng được nhận dạng
D. Định dạng ngày trong tài liệu phải giống kiểu ngày của Excel
Đáp án đúng: B

Khi một nhóm dùng nhiều cấu hình Markdown, cách giảm kết quả không nhất quán là gì?
A. Tạo ngẫu nhiên cấu hình mỗi lần parse để tăng khả năng tương thích
B. Để mỗi renderer tự suy ra extension từ màu theme đang áp dụng
C. Bỏ mọi bộ test vì parser đã tuân thủ một chuẩn ngôn ngữ cơ sở
D. Thống nhất bộ options và extension giữa các luồng xử lý
Đáp án đúng: D

Khi chuẩn hóa tài liệu, pipeline nào phù hợp với flexmark-java?
A. HtmlRenderer tạo ra HTML rồi đổi đuôi tệp thành .md để chuẩn hóa
B. Sao chép văn bản qua Excel rồi dùng định dạng ô để sửa Markdown
C. Parse thành AST rồi dùng Formatter chuẩn hóa Markdown
D. Tách mọi dòng ra và xóa khoảng trắng mà không xét loại node
Đáp án đúng: C

Điểm khác nhau quan trọng giữa Formatter và HtmlRenderer là gì?
A. Formatter xuất Markdown, còn HtmlRenderer xuất HTML để hiển thị
B. Formatter tạo AST, còn HtmlRenderer mới phân tích cú pháp nguồn
C. Formatter kết xuất XML, còn HtmlRenderer kết xuất workbook Excel
D. Formatter xác thực URL, còn HtmlRenderer chịu trách nhiệm lưu file
Đáp án đúng: A

Khi Formatter thay đổi khoảng trắng, điều gì nên được kiểm thử?
A. Số byte nguồn luôn không đổi sau mọi lần format và ghi lại tài liệu
B. Bảo toàn ngữ nghĩa và nội dung code khi thay đổi khoảng trắng
C. Thay đổi dòng trống tự chuyển thành code block có thể thực thi
D. Kết quả Markdown tự trở thành an toàn để hiển thị dưới mọi dạng HTML
Đáp án đúng: B

Khi chuẩn hóa heading, trường hợp nào cần tránh?
A. Tránh đổi cấp heading hoặc phá cấu trúc phân cấp
B. Đổi cách ghi dấu heading nhưng vẫn giữ đúng cấp và nội dung
C. Giữ nội dung tiêu đề và loại bỏ khoảng trắng thừa không cần thiết
D. Áp dụng một quy ước nhất quán cho cùng cấp heading trong tài liệu
Đáp án đúng: A

Khi xử lý danh sách lồng nhau, vì sao không nên tự xóa mọi indentation?
A. Thụt lề chỉ phục vụ căn giữa văn bản và không ảnh hưởng cú pháp
B. Các mục danh sách đều có cùng cấp dù thụt lề khác nhau
C. Thụt lề có thể thể hiện cấu trúc lồng nhau và phạm vi đoạn code
D. Parser mặc định chuyển mọi danh sách thành một đoạn văn duy nhất
Đáp án đúng: C

Khi chuẩn hóa bảng bằng Formatter, điều gì cần được bảo toàn?
A. Bắt buộc mọi bảng chỉ chứa văn bản và không bao giờ có link
B. Giữ ranh giới ô, số cột và nội dung dù ký tự căn chỉnh thay đổi
C. Gộp các hàng trống và tự tính tổng công thức trong các ô dữ liệu
D. Đổi mọi bảng thành danh sách vì Markdown không có extension bảng
Đáp án đúng: B

Khi định dạng lại fenced code, yếu tố nào quan trọng?
A. Chạy toàn bộ code block để kiểm tra cú pháp trước khi xuất tài liệu
B. Không làm thay đổi nội dung code và thông tin ngôn ngữ đã khai báo
C. Chuyển code block thành đoạn văn thường rồi để renderer tự nhận
D. Thay tên ngôn ngữ bằng tên file Markdown để giữ tính tương thích
Đáp án đúng: B

Một test round-trip Markdown đáng tin cậy cần xác nhận điều gì?
A. Chuỗi đầu ra luôn giống từng byte với bản nguồn chưa format
B. Kết quả HTML phải có cùng số dòng văn bản với Markdown đầu vào
C. Mỗi node AST được cấp lại đúng cùng địa chỉ bộ nhớ ban đầu
D. Cấu trúc và ngữ nghĩa sau parse-format-parse vẫn tương thích
Đáp án đúng: D

Khi cần tìm lỗi trong cây AST, thông tin nào giúp truy vết nguồn?
A. Màu background của node sau khi trình duyệt hiển thị HTML
B. Tên class Java của font chữ đang dùng khi đọc tài liệu
C. Tổng số request HTTP mà trang render gửi tới server
D. Dùng đoạn nguồn và vị trí node để đối chiếu lỗi
Đáp án đúng: D

Trong ứng dụng cần xử lý Markdown nhiều lần, tối ưu nào hợp lý?
A. Tạo cấu hình extension mới trên mỗi ký tự để tránh giữ trạng thái
B. Chuyển mọi tài liệu sang ảnh trước khi phân tích từng đoạn văn
C. Tái sử dụng cấu hình Parser và Renderer được khởi tạo phù hợp
D. Giữ toàn bộ AST của mọi người dùng trong bộ nhớ vô thời hạn
Đáp án đúng: C

Khi một tài liệu Markdown rất lớn được parse, cần lưu ý gì?
A. Parser chỉ đọc từng dòng rồi bỏ ngay nên không dùng thêm bộ nhớ
B. Bộ nhớ xử lý không thay đổi dù tài liệu có hàng triệu node
C. Formatter tự giới hạn tài liệu mà không cần chính sách ứng dụng
D. Đặt hạn mức vì AST sử dụng bộ nhớ theo kích thước đầu vào
Đáp án đúng: D

Khi xóa hoặc di chuyển node trong lúc duyệt AST, điều gì dễ gây lỗi?
A. Quan hệ sibling có thể thay đổi, nên quản lý vị trí duyệt cẩn thận
B. Renderer tự khôi phục mọi node đã bị xóa khi người dùng mở tài liệu
C. Đổi tên biến Java có thể làm AST mất toàn bộ vị trí nguồn
D. Heading là node duy nhất có parent, các node khác không chịu ảnh hưởng
Đáp án đúng: A

Khi cần trích xuất plain text từ tài liệu Markdown, cách làm nào hợp lý?
A. Duyệt node nội dung và xử lý link, code block theo ngữ nghĩa
B. Lấy chuỗi HTML thô rồi coi thẻ và thuộc tính là văn bản người dùng
C. Tách ký tự dấu sao trong nguồn rồi khẳng định phần còn lại là text
D. Chạy mọi code block và dùng output để thay thế nội dung chú thích
Đáp án đúng: A

Nếu ứng dụng xuất HTML từ Markdown người dùng, bước bảo mật nào là trọng tâm?
A. Tin tưởng đầu ra HtmlRenderer tự loại bỏ mọi script theo mọi cấu hình
B. Sanitize HTML và kiểm soát URL cùng chính sách cho raw HTML
C. Bỏ xác thực tài liệu vì cú pháp Markdown không thể chứa HTML
D. Đổi đuôi Markdown thành .txt rồi cho trình duyệt xử lý như HTML
Đáp án đúng: B

Khi render link có scheme nguy hiểm, phương án nào phù hợp?
A. Giữ nguyên URL vì nội dung của link đã được Parser chấp nhận
B. Đổi màu link sang xám để mọi hành vi điều hướng được vô hiệu
C. Đặt URL trong tiêu đề HTML thay cho href để liên kết vẫn hoạt động
D. Từ chối hoặc chuyển đổi URL theo allowlist trước khi hiển thị
Đáp án đúng: D

Khi hiển thị văn bản người dùng trong HTML, cần xử lý gì?
A. Escape văn bản không tin cậy để tránh bị hiểu thành HTML
B. Giữ nguyên ký tự góc nhọn vì renderer luôn coi là văn bản thường
C. Đưa mọi văn bản vào style CSS để trình duyệt tự kiểm tra dữ liệu
D. Gộp mọi Heading thành một Link để giới hạn số thẻ hiển thị
Đáp án đúng: A

Khi Markdown chứa mã trong code block, điều gì không được nhầm lẫn?
A. Bôi màu cú pháp mã luôn có nghĩa ứng dụng đã thực thi được mã
B. Khối code luôn phải được phân tích thành HTML raw trước khi render
C. Chuyển code thành TextNode làm mất yêu cầu escape ký tự HTML
D. Hiển thị mã như văn bản khác với việc cho phép mã được thực thi
Đáp án đúng: D

Khi trích xuất metadata và nội dung, cách tổ chức nào phù hợp?
A. Coi mọi metadata là tiêu đề cấp một của đoạn văn đầu tiên
B. Thêm metadata vào toàn bộ liên kết trong Document để dễ tìm lại
C. Đưa metadata vào tên tệp và bỏ việc kiểm tra nội dung tài liệu
D. Dùng phần xử lý metadata riêng và giữ nội dung AST có cấu trúc
Đáp án đúng: D

Vì sao không nên bật mọi extension cho mọi nguồn Markdown?
A. Extension luôn làm mọi tài liệu nhanh hơn nên cần bật toàn bộ
B. Extension có thể đổi cách hiểu cú pháp và tăng chi phí xử lý
C. Bật extension không ảnh hưởng gì đến kết quả parse và render
D. Extension chỉ đổi icon của tài liệu, không can thiệp cú pháp
Đáp án đúng: B

Kiểm thử snapshot HTML cho flexmark-java nên quản lý thế nào?
A. Xem mọi thay đổi HTML là hợp lệ nếu quá trình render không lỗi
B. Bỏ toàn bộ trường hợp XSS khỏi test vì renderer đã parse tài liệu
C. Cố định cấu hình và so sánh đầu ra có chủ đích khi nâng version
D. So sánh kích thước ảnh chụp thay vì cấu trúc hoặc nội dung HTML
Đáp án đúng: C

Khi tài liệu gồm tiếng Việt và ký tự Unicode, test nên chú ý gì?
A. Thay mọi ký tự ngoài ASCII bằng dấu hỏi trước khi đưa vào AST
B. Tự chuẩn hóa tiếng Việt thành chữ không dấu để tăng tốc render
C. Kiểm thử văn bản tiếng Anh vì trình hiển thị tự xử lý Unicode
D. Giữ nguyên nội dung và encoding qua parse, format và render
Đáp án đúng: D

Khi một bản nâng cấp flexmark-java thay đổi output của extension, nhóm nên làm gì?
A. Chạy regression tests theo cú pháp đang dùng và duyệt khác biệt
B. Giữ bản mới vì mọi khác biệt về HTML đều là cải tiến hợp lệ
C. Tắt test table và link vì extension không thuộc phần Markdown lõi
D. Đổi tên thư mục tài liệu để làm mất cảnh báo xuất HTML
Đáp án đúng: A

Trong một hệ thống tài liệu nội bộ, cách nào giảm rủi ro khi nhúng Markdown bên ngoài?
A. Lưu thẳng HTML vào web mà không cần kiểm soát vì đầu vào là Markdown
B. Áp dụng giới hạn đầu vào, sanitize kết quả và kiểm soát liên kết
C. Cho phép raw HTML mặc định để nội dung tác giả được giữ đầy đủ
D. Tạo Parser riêng cho mỗi request nhưng không cần quy tắc bảo mật
Đáp án đúng: B
