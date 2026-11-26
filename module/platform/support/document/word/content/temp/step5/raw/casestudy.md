Một cổng tiếp nhận hồ sơ cho phép tải lên tệp Word, nhưng bộ xử lý Java dùng Apache POI XWPF báo không đọc được một số tài liệu có phần mở rộng .doc do khách hàng gửi từ hệ thống cũ.
Một dịch vụ tạo hợp đồng DOCX và gửi ngay qua HTTP; khi mạng chập chờn, người nhận đôi lúc tải được tệp có kích thước nhỏ hơn dự kiến và Microsoft Word báo tài liệu bị hỏng.
Một nhóm chỉnh sửa trực tiếp tệp XML bên trong gói DOCX để thêm thành phần mới; sau khi đóng gói lại, Word yêu cầu sửa chữa tài liệu dù các đoạn văn còn hiển thị bình thường.
Một biểu mẫu DOCX do phần mềm bên thứ ba xuất ra mở bình thường trong Word nhưng không thể đọc bằng luồng xử lý tài liệu đang chạy trong Java; nhóm hỗ trợ cần tái hiện lỗi bằng chính tệp khách hàng cung cấp.
Một mẫu hợp đồng chứa đối tượng nhúng và các thành phần Office Open XML ít gặp; sau khi ứng dụng Java cập nhật vài dòng văn bản và lưu lại, một số thành phần không còn hiển thị giống tài liệu gốc.
Khách hàng gửi tài liệu DOCX đã đặt mật khẩu mở tệp; quy trình trích xuất nội dung tự động không lấy được đoạn văn nào dù người dùng vẫn mở được bằng Word sau khi nhập mật khẩu.
Một hệ thống tạo báo cáo nhiều trăm trang kèm ảnh độ phân giải cao; tiến trình Java tăng bộ nhớ đột ngột và bị dừng khi có nhiều yêu cầu xuất tài liệu đồng thời.
Hai nhân viên cùng tải về hợp đồng được sinh từ một mẫu chung; tệp của người thứ hai đôi khi chứa tên hoặc địa chỉ của người thứ nhất khi các yêu cầu đến sát nhau.
Một doanh nghiệp yêu cầu giữ chữ ký số trên tài liệu đã duyệt; sau khi hệ thống tự động chèn thêm thông tin vào DOCX, phần mềm kiểm tra báo chữ ký không còn hợp lệ.
Một dịch vụ nhập hàng nghìn DOCX từ nguồn không tin cậy; chỉ một tệp có cấu trúc nén bất thường đã khiến CPU và bộ nhớ tăng mạnh trong giai đoạn mở gói tài liệu.
Mẫu thư mời có chỗ trống tên người nhận, nhưng thao tác thay chuỗi trong từng XWPFRun không tìm thấy toàn bộ ký hiệu cần thay dù Word hiển thị ký hiệu ấy liền mạch.
Một hóa đơn có phần tên công ty được in đậm nằm giữa câu; sau khi tự động thay tên bằng giá trị mới, cả câu bị mất kiểu chữ hoặc chỉ một phần tên được thay.
Một hợp đồng chứa cùng mã khách hàng ở thân bài, trong bảng và ở footer; quá trình sinh tài liệu thay đúng ở thân bài nhưng để nguyên các vị trí còn lại.
Người dùng nhập địa chỉ gồm nhiều dòng vào biểu mẫu; tài liệu sinh ra dồn mọi dòng thành một đoạn hoặc xuất hiện các ký tự xuống dòng lạ ngay trong câu.
Một nhân viên chỉnh sửa mẫu bằng cách chèn thêm dấu cách và xuống dòng giữa các ký hiệu biến; bản phát hành hôm sau bỏ sót trường dữ liệu mà không phát sinh lỗi lúc chạy.
Mẫu quyết định có một đoạn tùy chọn chỉ xuất hiện khi có thông tin người đại diện; khi bỏ phần nội dung này, tài liệu vẫn để lại khoảng trống lớn trước chữ ký.
Một mẫu dùng tab để căn dòng ngày tháng và nơi ký; khi thay dữ liệu có độ dài lớn hơn dự kiến, các cột nhìn thẳng hàng trong Word chuyển thành lệch nhau.
Đội sản phẩm đưa chuỗi có dấu xuống dòng và tab từ cơ sở dữ liệu vào tài liệu; phần hiển thị khác nhau giữa trường nhập thủ công và trường sinh từ Apache POI XWPF.
Một báo cáo được tạo với tiêu đề lớn và đậm, nhưng Word không nhận các tiêu đề ấy trong Navigation Pane và người dùng không thể tạo mục lục dựa trên heading.
Hai mẫu DOCX có kiểu đoạn văn cùng tên hiển thị nhưng định nghĩa khác nhau; sau khi sao chép nội dung giữa mẫu, màu sắc và khoảng cách của các tiêu đề thay đổi.
Tài liệu tự động sinh có khoảng cách trước và sau đoạn đúng trên máy phát triển, nhưng khi bộ phận kế toán chuyển sang PDF trên máy chủ khác thì các đoạn bị giãn bất thường.
Một câu trong văn bản có nhiều phần định dạng nghiêng, đậm và gạch chân; quá trình thay dữ liệu hoặc gộp các XWPFRun làm mất ranh giới định dạng mà biên tập viên đã đặt.
Báo cáo tiếng Việt hiển thị dấu đúng trên máy người phát triển nhưng một số ký tự bị đổi phông khi Word mở tài liệu trên máy khách không cài cùng bộ phông.
Một hợp đồng song ngữ có đoạn tiếng Ả Rập xen số tiền và tên công ty viết bằng ký tự Latin; thứ tự hiển thị dấu câu thay đổi sau khi nội dung được sinh tự động.
Một biểu mẫu nhân sự chứa tên người dùng có emoji hoặc ký tự nằm ngoài bộ ký tự thông dụng; Word trên một số máy hiển thị ô vuông thay vì ký tự mong đợi.
Một tài liệu hướng dẫn có danh sách nhiều cấp được tạo từ các đoạn văn thông thường; dấu đầu dòng hiển thị nhưng người dùng không thể tăng giảm cấp danh sách theo cách quen thuộc trong Word.
Phụ lục hợp đồng có ba danh sách đánh số ở các phần khác nhau; bản xuất cuối cùng nối tiếp số thứ tự từ danh sách trước trong khi mẫu mong muốn mỗi phần bắt đầu lại.
Một quy trình nghiệp vụ yêu cầu danh sách cấp một dùng số, cấp hai dùng chữ và cấp ba dùng số La Mã; trong Word một số cấp bị thụt đầu dòng sai sau khi tạo bằng Java.
Ứng dụng sao chép một đoạn có liên kết và đánh số từ mẫu sang báo cáo mới; văn bản trông giống bản gốc nhưng liên kết hoặc số thứ tự không hoạt động khi người dùng chỉnh sửa.
Một báo cáo kinh doanh có bảng với số hàng thay đổi theo tháng; khi xuất hàng nghìn dòng, thao tác tạo tài liệu chậm rõ rệt và bộ nhớ tăng theo kích thước bảng.
Một bảng báo giá có cột đơn vị và cột thành tiền; khi nội dung sản phẩm quá dài, một cột bị co hẹp khiến số tiền bị xuống dòng giữa các chữ số.
Một ô tiêu đề phải trải ngang ba cột trong bảng; kết quả từ chương trình chỉ tô màu ba ô liền nhau, còn Word vẫn cho phép chọn và chỉnh sửa chúng như các ô riêng.
Một bảng kê tài sản có nhóm dữ liệu cần gộp ô theo chiều dọc; tài liệu mở trong Word nhưng cùng một nhãn nhóm xuất hiện lặp lại hoặc đường viền chia ô vẫn còn.
Mẫu phiếu khảo sát chứa bảng lồng trong một ô của bảng ngoài; quá trình đọc dữ liệu chỉ thu được các ô ngoài và bỏ sót nhiều câu trả lời trong bảng lồng.
Một ứng dụng nhân bản hàng mẫu để tạo danh sách sản phẩm; sau khi xuất, một số hàng giữ nguyên tên hàng mặc định hoặc dùng sai định dạng số từ hàng trước.
Bảng hợp đồng có tiêu đề cột ở hàng đầu tiên; khi bảng kéo dài qua nhiều trang, người đọc không còn thấy hàng tiêu đề ở đầu các trang sau.
Một dòng bảng chứa mô tả dài bị chia qua hai trang khiến chữ ký bên dưới tách khỏi phần nội dung cần xác nhận; bản in khó đọc dù dữ liệu không mất.
Một hóa đơn được thiết kế theo khổ A4 với chiều rộng cột cố định; cùng tệp DOCX mở trên Word và LibreOffice cho kết quả căn bảng và ngắt trang khác nhau.
Nhân viên nhập giá trị tiền tệ với dấu chấm và dấu phẩy theo vùng; sau khi ứng dụng điền các ô bảng, số tiền trong tài liệu hiển thị không thống nhất với mẫu kế toán.
Một báo cáo sử dụng ô bảng có nội dung xoay dọc và nền màu; ứng dụng cập nhật giá trị thành công nhưng phần căn chỉnh và nền ô thay đổi sau khi lưu.
Một hợp đồng có đường viền bảng phức tạp; sau khi tạo thêm hàng mới bằng XWPFTable, một số đường viền giữa các hàng bị gấp đôi hoặc biến mất khi in.
Một bảng động phải giữ nguyên các dòng trống để người dùng viết tay bổ sung; sau khi điền dữ liệu tự động, chiều cao các dòng trống không còn đồng đều.
Một bảng đánh giá cần đặt dấu chọn vào nhiều ô tùy kết quả; bản sinh từ dữ liệu lưu đúng trạng thái nhưng ký hiệu hiển thị khác nhau giữa Word desktop và Word trên web.
Một trang báo cáo chứa bảng rất rộng đặt trong phần tài liệu nằm ngang; chương trình thêm dữ liệu vào đúng bảng nhưng trang tiếp theo lại trở về hướng giấy dọc không như mẫu.
Một bảng tổng hợp nhiều trang phải kết thúc trước phần xác nhận; khi dữ liệu tăng thêm vài hàng, vùng ký tên bị đẩy sang trang mới chỉ với một dòng trống phía trên.
Một ứng dụng tạo hồ sơ nhân viên bằng cách đưa ảnh đại diện vào DOCX; ảnh dọc được hiển thị ngang dù tệp JPEG gốc nhìn đúng trong trình xem ảnh.
Đội marketing cung cấp logo kích thước pixel rất lớn nhưng muốn đặt trong ô nhỏ; tài liệu xuất ra chứa ảnh quá khổ và logo chèn lên phần văn bản lân cận.
Một hệ thống chèn cùng logo vào header của hàng nghìn hợp đồng; kích thước các DOCX đầu ra tăng bất thường dù mỗi hợp đồng chỉ có một logo hiển thị.
Mẫu báo cáo có hình ảnh minh họa gắn với đoạn văn; khi thêm các đoạn nội dung ở phía trước, ảnh trôi sang trang khác và che mất phần chú thích.
Một tài liệu giới thiệu sản phẩm chứa ảnh ở định dạng mới; máy của nhóm phát triển hiển thị ảnh đầy đủ nhưng người dùng mở trên một phiên bản Word cũ chỉ thấy vùng trống.
Một quy trình tải ảnh từ dịch vụ lưu trữ trước khi chèn vào hợp đồng; khi đường truyền gián đoạn, tệp DOCX vẫn sinh ra nhưng một số trang không có ảnh và không có thông báo cụ thể.
Tài liệu báo cáo có hình kèm chú thích đánh số; sau khi thêm hoặc xóa hình bằng chương trình, thứ tự chú thích mà Word hiển thị không còn khớp các hình.
Một mẫu dùng hình nền mờ phía sau chữ ký; sau khi thay ảnh bằng logo mới, nền che chữ ký trên một số ứng dụng xem DOCX nhưng không che trên máy tạo mẫu.
Một báo cáo có nhiều hình chụp màn hình cần đọc bằng trình hỗ trợ tiếp cận; hình vẫn hiển thị đúng nhưng người đọc không nhận được mô tả nội dung từ tài liệu sinh tự động.
Đơn vị tuyển dụng dùng ảnh chữ ký viết tay trong hợp đồng; khi tài liệu được chuyển sang PDF, chữ ký bị vỡ nét và thay đổi kích thước so với lúc xem trong Word.
Một mẫu Word đặt logo bên trong khung văn bản nổi; chương trình thay nội dung ở các đoạn thông thường thành công nhưng không tìm thấy logo và dòng tên đơn vị trong khung.
Một báo cáo có biểu đồ được chèn từ ứng dụng bảng tính; sau khi cập nhật dữ liệu bằng Java, hình biểu đồ trong Word vẫn thể hiện dữ liệu của kỳ trước.
Một mẫu hợp đồng có header khác nhau cho trang bìa và các trang sau; file sinh tự động hiển thị header trang bìa trên tất cả các trang khi mở bằng Word.
Một quyển sổ tay yêu cầu header trang chẵn chứa tên chương còn header trang lẻ chứa tên đơn vị; sau khi xuất từ mẫu DOCX, hai loại trang xuất hiện cùng một header.
Một báo cáo có footer đánh số trang theo định dạng trang hiện tại trên tổng số trang; trong tài liệu vừa sinh, người xem thấy mã trường hoặc giá trị cũ chưa cập nhật.
Một tập tài liệu có nhiều section, mỗi section cần bắt đầu đếm trang lại từ một; bản sinh từ Java tiếp tục số trang từ section trước và ảnh hưởng đến mục lục.
Một hợp đồng có phần phụ lục nằm ngang ở giữa những phần khổ dọc; sau khi thêm nội dung vào trước phụ lục, định dạng khổ giấy của các trang tiếp theo bị thay đổi.
Một thông báo hành chính yêu cầu lề trái, lề phải và khoảng cách header theo quy chuẩn; tệp DOCX nhìn ổn trên màn hình nhưng bị cắt một phần nội dung khi in trên máy văn phòng.
Một biểu mẫu có nội dung bắt buộc không được tách chữ ký khỏi đoạn xác nhận; khi địa chỉ khách hàng dài hơn mẫu, chữ ký xuất hiện riêng ở đầu trang sau.
Một mẫu sử dụng ngắt trang và ngắt section liên tiếp; sau khi tạo thêm nội dung bằng Apache POI, tài liệu xuất hiện một trang trắng ngoài dự kiến.
Một báo cáo cần đánh số trang sau trang bìa, trong khi trang bìa không hiển thị số; Word hiển thị số đúng trên một số bản mẫu nhưng bắt đầu sai ở bản được nhân từ template khác.
Một mẫu có đường kẻ và thông tin liên hệ ở footer; sau khi tạo bảng dài, footer đè lên hàng cuối cùng trong bản PDF dù nhìn trong Word vẫn đủ dữ liệu.
Một mẫu hành chính cần chèn watermark chữ DỰ THẢO lên mọi trang; ứng dụng xuất tài liệu có watermark trang đầu nhưng thiếu trên trang ngang của phụ lục.
Một hồ sơ chứa chú thích cuối trang ở các điều khoản quan trọng; sau khi hệ thống sao chép điều khoản vào tài liệu khác, số chú thích và nội dung chú thích không còn khớp.
Một báo cáo có mục lục tự động ở đầu tài liệu; chương trình sinh thêm ba chương nhưng mục lục vẫn chỉ liệt kê các chương có trong mẫu gốc.
Một hợp đồng dùng trường ngày tháng được chèn qua chức năng Field của Word; khi Java lưu tệp, trường hiển thị ngày cũ dù dữ liệu nghiệp vụ đã thay đổi.
Một mẫu thư có các trường trộn thư từ danh sách khách hàng; khi chương trình điền dữ liệu như văn bản thông thường, người mở tài liệu vẫn thấy một số mã trường trộn thư.
Một biểu mẫu DOCX chứa ô nhập nội dung và hộp chọn dưới dạng content control; công cụ đọc đoạn văn chỉ lấy được nhãn câu hỏi mà thiếu giá trị người dùng nhập.
Một hệ thống phát hành mẫu khảo sát có hộp kiểm được thiết kế trong Word; sau khi điền kết quả bằng Java, dấu chọn xuất hiện nhưng người nhận không thể thao tác lại với ô chọn.
Một mẫu đề nghị mua hàng có vùng lặp thông tin theo biểu mẫu; khi nhập ba mặt hàng, phần mềm chỉ điền mặt hàng đầu tiên và để nguyên vùng nhập còn lại.
Một hợp đồng có bookmark đánh dấu nơi cần nhảy đến từ trang mục lục; sau khi nhân bản một khối điều khoản, các liên kết nội bộ dẫn người đọc đến vị trí không mong muốn.
Một báo cáo có liên kết ngoài với dòng chữ hiển thị là tên dự án; chương trình thay tên dự án nhưng địa chỉ liên kết vẫn trỏ tới dự án cũ.
Một mẫu chứa comment của người duyệt và thay đổi đang được theo dõi bằng Track Changes; sau khi hệ thống sinh bản gửi khách, người nhận nhìn thấy nội dung hoặc bình luận nội bộ.
Một tài liệu chỉ cho phép chỉnh sửa một số vùng nhất định; sau khi được sinh tự động, người nhận không thể điền vào các ô dự kiến dù xem và in bình thường.
Một hợp đồng có hai người phê duyệt và vùng chữ ký riêng; khi thông tin người phê duyệt thứ hai không tồn tại, tài liệu vẫn giữ tên người mẫu của bản gốc.
Một biểu mẫu có trường số tiền tính từ các ô phía trên; khi ứng dụng cập nhật số lượng và đơn giá, tổng tiền trong Word chưa thay đổi theo giá trị mới.
Một báo cáo dùng phần Document Properties để chèn tên tác giả, đơn vị và ngày tạo; người nhận xem thuộc tính tệp thấy tên người xây dựng mẫu thay vì người phát hành báo cáo.
Một biểu mẫu nhập hợp đồng cần giữ định dạng ngày theo tiếng Việt; trên máy chủ đặt vùng ngôn ngữ khác, cùng dữ liệu đầu vào được điền thành ngày có thứ tự tháng và ngày không như mong muốn.
Một công cụ Java trích xuất văn bản từ DOCX bằng cách duyệt các XWPFParagraph; kết quả bỏ qua toàn bộ số liệu trong các bảng dù khi mở Word tài liệu đầy đủ.
Một biểu mẫu khảo sát chứa bảng lồng trong bảng và các đoạn văn trước sau mỗi bảng; bản xuất văn bản thuần đưa các câu trả lời vào vị trí sai so với thứ tự đọc trong Word.
Một hợp đồng có danh sách đánh số tự động; quy trình trích xuất văn bản lấy được nội dung từng mục nhưng không thu được các số thứ tự hiển thị trên màn hình.
Một tài liệu chứa header với mã hợp đồng và footer với số phiên bản; hệ thống đối chiếu nội dung chỉ trích xuất thân bài nên không phát hiện hai tệp có thông tin nhận diện khác nhau.
Một báo cáo có nhiều hyperlink; công cụ trích xuất nội dung lấy đúng chữ hiển thị nhưng báo cáo kiểm thử không thể xác định liên kết nào đang dẫn đến địa chỉ lỗi thời.
Một tài liệu chứa hình ảnh và caption mô tả số liệu; khi chuyển sang dữ liệu có cấu trúc, phần văn bản được trích xuất nhưng không xác định được hình tương ứng với mỗi caption.
Một hợp đồng sử dụng chú thích cuối trang và chú thích cuối tài liệu; quy trình phân tích điều khoản không lấy được phần dẫn giải quan trọng nằm ngoài thân bài.
Một bản DOCX có các thay đổi chưa được chấp nhận; hệ thống trích xuất đưa cả nội dung cũ và nội dung mới vào tìm kiếm, tạo ra kết quả không giống những gì người đọc thấy trong Word.
Một tài liệu điền biểu mẫu có giá trị ẩn trong content control hoặc ô văn bản nổi; quá trình trích xuất từ các đoạn và bảng chính cho kết quả thiếu dữ liệu bắt buộc.
Một hệ thống tìm kiếm lưu văn bản trích từ DOCX vào cơ sở dữ liệu; người dùng tìm tên công ty có dấu tiếng Việt không ra kết quả vì chuỗi nhận được có biểu diễn Unicode khác với chuỗi truy vấn.
Một dịch vụ tạo DOCX từ mẫu chung được dùng trong nhiều yêu cầu đồng thời; khi tăng tải, vài tài liệu xuất ra có bảng hoặc ảnh của yêu cầu khác dù truy vấn dữ liệu đầu vào độc lập.
Một tác vụ tạo một nghìn DOCX trong một lần chạy; số mô tả tệp đang mở tăng liên tục cho đến khi tiến trình không thể mở thêm template hoặc tệp đầu ra.
Một ứng dụng đọc DOCX từ InputStream của tệp upload rồi lưu sang nơi khác; lỗi chỉ xuất hiện khi tệp đầu vào có kích thước lớn và luồng bị đóng trước khi tài liệu được xử lý xong.
Một hệ thống tạo tài liệu trong bộ nhớ trước khi tải về; người dùng hủy kết nối giữa chừng khiến yêu cầu trên máy chủ tiếp tục chiếm tài nguyên lâu sau khi tải về đã thất bại.
Một dịch vụ xử lý tài liệu xuất hiện lỗi rất hiếm sau khi tạo hàng trăm biểu mẫu liên tiếp; khi chạy độc lập từng biểu mẫu, mọi tệp đều mở bình thường, nhưng bản xuất theo lô đôi khi bị Word yêu cầu sửa chữa.
Một pipeline cần loại bỏ thông tin cá nhân khỏi hợp đồng mẫu trước khi chia sẻ; sau khi thay nội dung hiển thị, tên khách hàng cũ vẫn còn trong comment, thuộc tính tài liệu hoặc nội dung không hiện trên trang.
Một người dùng tải lên DOCX do bên ngoài tạo và yêu cầu chương trình lấy hình ảnh và văn bản; file có các quan hệ tới tài nguyên ngoài khiến thao tác xử lý trong môi trường không có Internet cho kết quả khác lúc chạy nội bộ.
Một ứng dụng phải xác minh nội dung DOCX sau khi sinh; tệp vượt qua kiểm tra tồn tại và kích thước nhưng khi mở trong Word lại xuất hiện cảnh báo sửa chữa, thiếu ảnh hoặc mất một số trang.
Một bộ kiểm thử so sánh XML nội bộ của hai tệp DOCX và kết luận khác nhau mặc dù người dùng thấy bố cục và nội dung giống nhau trong Word.
Một quy trình tự động so khớp văn bản trích xuất của DOCX với yêu cầu đầu vào; kiểm thử luôn thành công dù số trang, vị trí bảng và định dạng tiêu đề bị thay đổi sau khi cập nhật template.
Một báo cáo DOCX do Apache POI XWPF sinh nhìn đúng trên Windows với Microsoft Word nhưng khi xem trên Linux bằng LibreOffice thì tiêu đề, bảng và số trang có vị trí khác nhau.
Một hệ thống xuất tài liệu trên máy chủ Linux không có các phông chữ được dùng trong mẫu; bản PDF chuyển đổi từ DOCX có xuống dòng và phân trang khác với khi nhân viên mở trên máy Windows.
Một nhóm dùng cùng mẫu hợp đồng cho Word desktop, Word trên web và ứng dụng điện thoại; ở một số trình xem, watermark, hình nổi và ô đánh dấu hiển thị không nhất quán.
Một phòng pháp chế yêu cầu mẫu DOCX có thể được người nhận chỉnh sửa tiếp; tài liệu mở đúng nhưng sau khi người nhận thêm điều khoản, bảng và phần đánh số tự động hoạt động khác mẫu do con người soạn.
Một tổ chức cần chứng minh tài liệu phát hành chính xác với dữ liệu phê duyệt; các tệp DOCX được sinh từ cùng một bộ dữ liệu đôi khi khác metadata, thời điểm tạo và cấu trúc nén dù phần hiển thị tương tự.
Một hệ thống chuyển DOCX sang PDF để gửi khách hàng; bản PDF thiếu một trang phụ lục chứa bảng hoặc thay đổi vị trí chữ ký so với tệp DOCX đã được bộ phận nghiệp vụ duyệt.
Một dịch vụ sửa hàng loạt hợp đồng cũ bằng Apache POI XWPF; sau khi chạy, các tệp đều mở được nhưng lịch sử chỉnh sửa, bình luận và một số đối tượng trong mẫu gốc không còn đúng như trước.
