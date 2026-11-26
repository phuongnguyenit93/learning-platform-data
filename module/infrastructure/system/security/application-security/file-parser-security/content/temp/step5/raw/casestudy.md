Một cổng tuyển dụng cho phép ứng viên tải CV lên bằng cách kiểm tra phần mở rộng .pdf, nhưng người dùng đổi tên tệp thực thi thành resume.pdf và hệ thống lưu tệp vào vùng được web server phục vụ trực tiếp.
Một dịch vụ nhận ảnh đại diện chỉ kiểm tra MIME type do trình duyệt gửi trong multipart request; kẻ tấn công gửi tệp HTML với Content-Type image/png khiến nội dung được lưu và phục vụ như ảnh.
Một nền tảng tài liệu dùng magic bytes để nhận diện PDF nhưng chấp nhận tệp polyglot vừa hợp lệ với parser ảnh vừa chứa cấu trúc có thể bị trình duyệt diễn giải như nội dung chủ động.
Một API upload đọc toàn bộ request vào RAM trước khi kiểm tra kích thước, khiến một client gửi nhiều tệp lớn đồng thời làm worker cạn bộ nhớ và dịch vụ liên tục khởi động lại.
Một endpoint multipart cho phép số lượng part không giới hạn và chấp nhận header part rất dài; request có kích thước tổng thể vừa phải nhưng làm CPU tăng mạnh trong lúc parser xử lý.
Một hệ thống xử lý ảnh chấp nhận ảnh có chiều rộng và chiều cao cực lớn dù kích thước tệp nén nhỏ, khiến thư viện giải mã cấp phát hàng gigabyte bộ nhớ.
Một dịch vụ chuyển đổi PDF nhận tệp vài megabyte nhưng cấu trúc đối tượng lồng sâu khiến parser tiêu thụ CPU trong nhiều phút và chiếm hết worker xử lý.
Một hệ thống nhập dữ liệu cho phép người dùng upload ZIP, trong đó một tệp nén nhỏ bung ra hàng trăm gigabyte dữ liệu và làm đầy volume tạm trong lúc giải nén.
Một bộ xử lý archive giới hạn tổng dung lượng giải nén nhưng không giới hạn tỷ lệ nén, số entry và độ sâu archive lồng nhau nên vẫn bị zip bomb làm cạn CPU và inode.
Một dịch vụ tự động giải nén archive lồng nhiều cấp; mỗi archive riêng lẻ nằm dưới giới hạn kích thước nhưng tổng tài nguyên tiêu thụ sau nhiều vòng lồng vượt xa quota dự kiến.
Một hệ thống backup giải nén ZIP bằng cách nối tên entry vào thư mục đích; archive chứa đường dẫn ../../ khiến tệp ghi đè lên cấu hình nằm ngoài thư mục khôi phục.
Một bộ xử lý TAR chạy trên Linux gặp entry có đường dẫn tuyệt đối bắt đầu bằng /etc, khiến nội dung archive được ghi ra ngoài thư mục giải nén.
Một archive chứa tên entry dùng dấu gạch chéo ngược và ký tự ổ đĩa kiểu Windows; bộ lọc chỉ kiểm tra ../ theo kiểu Unix nên đường dẫn thoát khỏi thư mục đích trên worker Windows.
Một dịch vụ giải nén kiểm tra đường dẫn sau khi chuẩn hóa chuỗi nhưng không xử lý đúng symlink entry; archive tạo symlink trỏ ra ngoài thư mục đích rồi ghi tệp qua liên kết đó.
Một công cụ phục hồi dữ liệu chấp nhận hard link và symbolic link trong archive; các entry liên kết tới tệp hệ thống làm thay đổi nội dung ngoài phạm vi dữ liệu người dùng.
Một pipeline quét malware giải nén archive vào thư mục tạm dùng chung; hai job chạy đồng thời có thể ghi đè hoặc đọc nhầm tệp của nhau do tên entry trùng lặp.
Một dịch vụ quét tệp kiểm tra file trong thư mục quarantine rồi chuyển file sang vùng xử lý bằng đường dẫn; giữa lúc kiểm tra và lúc mở file, một tiến trình khác thay thế nội dung tại đường dẫn đó.
Một nền tảng tải tệp cho phép tên file chứa Unicode normalization khác nhau và ký tự điều khiển; hai tên hiển thị giống nhau nhưng ánh xạ tới đối tượng lưu trữ hoặc đường dẫn khác nhau.
Một dịch vụ lưu upload theo tên gốc do người dùng cung cấp; tên chứa ký tự phân cách, tên thiết bị dành riêng hoặc hậu tố khoảng trắng khiến hành vi khác nhau giữa Linux, Windows và object storage.
Một ứng dụng ghi tệp tải lên vào thư mục public cùng origin với trang quản trị; tệp HTML hoặc SVG được mở trực tiếp và chạy script trong ngữ cảnh đáng tin cậy của website.
Một hệ thống tài liệu trả file người dùng tải lên với Content-Type suy ra từ phần mở rộng và không đặt Content-Disposition phù hợp, khiến browser sniff nội dung và hiển thị tệp chủ động.
Một dịch vụ lưu trữ dùng URL có thể đoán được và không kiểm tra quyền sở hữu khi tải xuống; người dùng thay object key trong URL để lấy tài liệu của tenant khác.
Một hệ thống tạo presigned upload URL với thời hạn dài và quyền ghi rộng; URL bị lộ trong ticket hỗ trợ vẫn cho phép thay thế đối tượng đã upload sau khi quy trình kiểm tra hoàn tất.
Một pipeline xử lý tệp chạy antivirus trước khi parse, nhưng parser và scanner nhận các phiên bản nội dung khác nhau do tệp có thể bị thay thế giữa hai bước.
Một hệ thống upload đưa tệp vào trạng thái approved ngay khi antivirus trả về không phát hiện mã độc; parser chuyên biệt chỉ chạy sau đó và gặp lỗi khai thác làm lộ dữ liệu trên worker.
Một dịch vụ đọc XML từ đối tác chấp nhận DOCTYPE và external entity; một tài liệu XML tham chiếu file nội bộ khiến parser đọc nội dung hệ thống rồi đưa vào kết quả xử lý.
Một endpoint chuyển đổi XML sang JSON bật XInclude và tải tài nguyên bên ngoài; tệp đầu vào khiến worker gửi request đến địa chỉ nội bộ của hạ tầng.
Một parser XML giới hạn kích thước đầu vào nhưng không giới hạn entity expansion; một tài liệu nhỏ tạo ra lượng nội dung mở rộng khổng lồ và làm cạn bộ nhớ.
Một dịch vụ xác thực hóa đơn dùng XML schema từ URL trong tài liệu; parser tự tải schema bên ngoài và có thể truy cập dịch vụ nội bộ qua mạng của worker.
Một hệ thống nhập cấu hình YAML sử dụng loader hỗ trợ object construction tùy ý; tệp do người dùng upload kích hoạt hành vi ngoài ý muốn trong lúc deserialize.
Một dịch vụ nhận dữ liệu cache đã serialize từ nhiều nguồn nhưng không xác minh nguồn gốc hoặc kiểu đối tượng; payload crafted kích hoạt gadget chain trong quá trình giải tuần tự.
Một nền tảng lưu phiên bản tài liệu dùng định dạng object serialization nhị phân có tham chiếu lớp; sau khi thư viện phụ thuộc được nâng cấp, một tệp cũ không tin cậy gây thực thi hành vi nguy hiểm khi deserialize.
Một API nhận tệp CSV và tự động mở bằng phần mềm bảng tính; các ô bắt đầu bằng ký tự công thức khiến dữ liệu do người dùng kiểm soát được thực thi khi nhân viên mở báo cáo.
Một dịch vụ render Markdown cho phép HTML nhúng và URL scheme không an toàn; tài liệu được upload chứa nội dung chủ động và thực thi trong trang xem trước của người dùng khác.
Một nền tảng xem trước SVG sử dụng renderer có thể tải font, ảnh hoặc stylesheet từ URL bên ngoài; tệp SVG do khách hàng gửi khiến parser truy cập metadata endpoint trong mạng nội bộ.
Một hệ thống chuyển đổi Office document sang PDF chạy parser có plugin macro và external link; tệp tải lên kích hoạt tải tài nguyên từ xa hoặc xử lý nội dung chủ động trên máy chuyển đổi.
Một worker xử lý PDF và ảnh chạy cùng quyền với ứng dụng chính, có quyền đọc secret và truy cập mạng nội bộ; lỗ hổng trong thư viện parser cho phép tệp crafted ảnh hưởng toàn bộ môi trường ứng dụng.
Một nền tảng upload chạy parser trong container nhưng chia sẻ thư mục host nhạy cảm và socket quản trị; tiến trình parser bị khai thác có thể thoát khỏi ranh giới cô lập dự kiến.
Một dịch vụ chuyển đổi tệp cho phép parser mở kết nối outbound tùy ý; một tài liệu tham chiếu URL nội bộ làm worker gửi request đến control plane và dịch vụ metadata.
Một pipeline xử lý tài liệu có hàng đợi retry vô hạn đối với tệp parser luôn crash; một tệp độc hại được gửi lặp lại khiến worker liên tục restart và hàng đợi không thể tiêu thụ.
Một nhóm phát triển nâng cấp thư viện xử lý ảnh để vá CVE nhưng thay đổi hành vi parser; một số tệp hợp lệ trước đây bị từ chối và một số định dạng cũ lại đi qua nhánh parser khác.
Một bộ parser hỗ trợ hàng chục định dạng bằng cách đoán định dạng từ phần mở rộng; dữ liệu nhị phân không xác định được đưa tới parser mặc định có bề mặt tấn công lớn.
Một hệ thống kiểm tra file chỉ fuzz parser ở chế độ happy path và không theo dõi crash, timeout hoặc memory growth; một đầu vào biên làm parser treo nhưng pipeline CI vẫn báo thành công.
Một đội bảo mật fuzz thư viện parser bằng corpus nhỏ không lưu lại seed gây lỗi; lỗi chỉ xuất hiện ngẫu nhiên trên production và không thể tái hiện để xác minh bản vá.
Một dịch vụ nhận tệp có cấu trúc đệ quy cho phép nesting không giới hạn; đầu vào hợp lệ về cú pháp nhưng gây stack exhaustion và làm worker chết.
Một parser xử lý archive có thể tạo hàng triệu file rỗng; giới hạn tổng byte không bị vượt nhưng số inode và thời gian tạo file khiến filesystem tạm không còn phục vụ job khác.
Một hệ thống xóa tệp tạm sau khi parse thất bại nhưng không dọn dẹp khi process bị kill; các tệp lớn tích tụ qua nhiều ngày và lấp đầy vùng lưu trữ.
Một nền tảng phân tích dữ liệu giữ nguyên bản gốc, bản giải nén và bản chuyển đổi mà không có retention policy; một đợt upload lớn làm chi phí lưu trữ tăng và dữ liệu nhạy cảm tồn tại lâu hơn dự kiến.
Một dịch vụ cho phép người dùng tải lên tệp đã mã hóa bằng mật khẩu nhưng scanner không thể kiểm tra nội dung; quy trình vẫn tự động chuyển tệp sang vùng được tin cậy.
Một hệ thống xử lý tệp chấp nhận archive có entry trùng tên; scanner kiểm tra bản đầu tiên nhưng extractor ghi đè bằng bản cuối cùng, tạo khác biệt giữa nội dung đã quét và nội dung được xử lý.
Một bộ chuyển đổi định dạng dùng hai thư viện parser khác nhau ở bước kiểm tra và bước xử lý; hai parser diễn giải cùng một tệp theo cách khác nhau khiến nội dung bị bỏ qua kiểm tra an toàn.
Một nền tảng lưu tệp tải lên trong bucket dùng chung với quyền đọc rộng; tên object ngẫu nhiên nhưng policy IAM cho phép worker của tenant này đọc dữ liệu của tenant khác.
Một dịch vụ xử lý tài liệu ghi toàn bộ nội dung lỗi parse, đường dẫn nội bộ và một phần dữ liệu đầu vào vào log; log tập trung trở thành nơi lưu trữ PII và nội dung độc hại.
Một hệ thống tiếp nhận tệp từ đối tác cần xử lý khẩn cấp sau khi parser phát hiện crash lặp lại; nhóm vận hành chưa có thông tin về định dạng, phiên bản thư viện, hash tệp và phạm vi worker bị ảnh hưởng.
