Một cổng chăm sóc khách hàng tích hợp ChatClient để trả lời câu hỏi đơn hàng, nhưng khi mô hình phản hồi chậm toàn bộ request HTTP của người dùng vượt thời hạn chờ.
Ứng dụng Spring Boot gọi ChatModel trực tiếp từ nhiều service, nhưng từng nhóm tự đặt tham số sinh văn bản khác nhau khiến cách trả lời cùng một câu hỏi không nhất quán.
Đội phát triển thay một lời gọi ChatModel bằng ChatClient để gom cấu hình chung, nhưng những phần xử lý cũ vẫn phụ thuộc vào đối tượng phản hồi đầy đủ thay vì chỉ văn bản.
Một hệ thống báo cáo lấy văn bản từ phản hồi AI rồi ghi vào hồ sơ khách hàng, nhưng mô hình trả về câu giải thích thay vì giá trị trường nghiệp vụ mà hệ thống đang chờ.
Dịch vụ đặt lịch dùng ChatClient để hiểu yêu cầu bằng tiếng Việt, nhưng khi khách nhập nhiều ý trong một tin nhắn phản hồi chỉ giải thích một phần nhu cầu.
Một ứng dụng cho phép nhiều bộ phận gọi chung một ChatModel, nhưng bộ phận tư vấn và bộ phận pháp chế cần quy tắc trả lời trái ngược nhau theo từng ngữ cảnh.
Nền tảng đào tạo dựng một Prompt từ hướng dẫn và nội dung học viên, nhưng thứ tự các message khiến yêu cầu về giọng điệu bị hiểu khác với kỳ vọng của nhóm sản phẩm.
Một chatbot nội bộ gửi câu hỏi mới mà không có lịch sử hội thoại, khiến câu trả lời cho lời nhắn tiếp theo không hiểu đại từ chỉ vấn đề đã trao đổi trước đó.
Ứng dụng lưu toàn bộ hội thoại rồi đưa lại vào mỗi Prompt, nhưng phiên tư vấn kéo dài khiến số token tăng nhanh và request vượt giới hạn ngữ cảnh của mô hình.
Một màn hình trợ lý hiển thị văn bản câu trả lời mà không lưu thông tin phản hồi khác, khiến đội vận hành không phân biệt được yêu cầu hoàn thành bình thường với yêu cầu bị cắt do giới hạn sinh.
Dịch vụ hỗ trợ lập đơn hàng coi văn bản do mô hình trả về là quyết định nghiệp vụ chính thức, nhưng mô hình đôi lúc suy đoán trạng thái thanh toán không có trong dữ liệu đầu vào.
Nhóm vận hành dùng chung ChatClient cho nhiều loại thao tác nhưng không gắn định danh yêu cầu, khiến log khó ghép câu hỏi của khách với phản hồi từ provider.
Một API trả kết quả AI dưới dạng chuỗi duy nhất cho ứng dụng di động, nhưng UI cần biết phần nào là nội dung hiển thị và phần nào là dữ liệu phục vụ hậu kiểm.
Hệ thống tạo thư xác nhận dùng Prompt có nhiều chỉ dẫn trùng nhau từ các tầng cấu hình, khiến mô hình đôi khi bỏ qua giới hạn độ dài mà thương hiệu yêu cầu.
Một ứng dụng dùng mặc định cấu hình provider trên toàn hệ thống, nhưng request cần chọn cấu hình riêng cho tác vụ phân loại lại nhận các tham số sinh văn bản của chatbot.
Đội sản phẩm chèn đoạn JSON minh họa có dấu ngoặc nhọn vào prompt template, nhưng cú pháp minh họa bị hiểu như biến mẫu cần thay thế và làm bước dựng Prompt báo lỗi.
Một dịch vụ phân tích hợp đồng dùng mẫu prompt chứa nhiều biến bắt buộc, nhưng dữ liệu từ CRM thiếu một biến nên chỉ một số hồ sơ gây lỗi khi dựng Prompt.
Nền tảng thương mại điện tử chèn tên sản phẩm do người bán nhập vào template, nhưng mô hình hiểu một đoạn tên sản phẩm như chỉ dẫn mới và thay đổi cách trả lời.
Một ứng dụng tư vấn du lịch tái sử dụng cùng prompt template cho nhiều ngôn ngữ, nhưng các ví dụ cố định bằng tiếng Anh làm câu trả lời tiếng Việt xen thuật ngữ không phù hợp.
Hệ thống tuyển dụng gửi thông tin ứng viên vào Prompt dưới dạng văn bản dài, nhưng quá nhiều nội dung ít liên quan che khuất tiêu chí tuyển dụng quan trọng.
Một nhóm xây prompt template cho dữ liệu ngày tháng, nhưng giá trị được định dạng theo vùng máy chủ khiến mô hình hiểu sai ngày phỏng vấn ở những quốc gia khác nhau.
Ứng dụng tạo mô tả sản phẩm thay đổi một phần template mà không đánh dấu phiên bản, khiến kết quả từ hai đợt triển khai khác nhau khó so sánh trong báo cáo chất lượng.
Nhóm CSKH giữ nguyên phần chỉ dẫn hệ thống nhưng thêm các yêu cầu người dùng trái ngược, khiến mô hình có lúc ưu tiên yêu cầu cuối thay vì chính sách trả lời đã đặt.
Một chatbot chăm sóc sức khỏe nhận dữ liệu tự khai từ người dùng, nhưng Prompt không phân biệt giả định của người dùng với thông tin đã được kiểm chứng nên trả lời quá chắc chắn.
Hệ thống hỗ trợ pháp lý yêu cầu trích dẫn điều khoản trong Prompt, nhưng tài liệu đầu vào chỉ chứa đoạn tóm tắt và mô hình vẫn tạo ra số điều khoản không có thật.
Một ứng dụng tóm tắt báo cáo tài chính đưa bảng số liệu qua template dưới dạng chuỗi không có nhãn đơn vị, khiến kết luận so sánh các khoản tiền khác nhau bị sai lệch.
Đội nội dung muốn thay đổi giọng điệu câu trả lời theo từng chiến dịch, nhưng các message hướng dẫn được tạo từ nhiều nguồn và thứ tự cuối cùng không ổn định.
Nền tảng giáo dục dùng một mẫu prompt với danh sách ví dụ, nhưng khi số ví dụ tăng dài quá mức mô hình không còn chỗ cho phần câu hỏi mới của học viên.
Dịch vụ dịch thuật dùng chỉ dẫn đầu vào không nói rõ cần giữ mã sản phẩm nguyên dạng, khiến mô hình dịch cả định danh mà hệ thống quản lý kho sử dụng.
Một hệ thống chấm điểm phản hồi khách hàng đặt tiêu chí trong Prompt, nhưng mô hình dùng thang điểm khác nhau giữa các request có cùng nội dung.
Ứng dụng tổng hợp phản hồi người dùng chỉ lấy phần văn bản đầu tiên trong ChatResponse, nhưng cấu trúc phản hồi thực tế có nhiều lựa chọn sinh khác nhau theo cấu hình.
Đội theo dõi chi phí cần phân tích token sử dụng trong ChatResponse, nhưng có những lần gọi provider không cung cấp đủ usage metadata như dự kiến.
Một hệ thống lưu finish reason của phản hồi AI để kiểm toán, nhưng bản ghi giao diện chỉ lưu đoạn chữ cuối và không cho biết nội dung đã bị cắt.
Ứng dụng tư vấn có cấu hình giới hạn output token quá thấp, khiến câu trả lời kết thúc giữa danh sách bước thao tác mà mã HTTP vẫn biểu thị thành công.
Nền tảng hỏi đáp đánh giá chất lượng dựa trên nội dung câu trả lời, nhưng đội phân tích bỏ qua metadata về model thực tế được chọn trong môi trường vận hành.
Một chatbot chuyển phản hồi mô hình thẳng vào cơ sở dữ liệu mà không gắn phiên bản prompt, khiến việc truy vết một câu trả lời gây tranh cãi không có đủ ngữ cảnh.
Ứng dụng phân loại khiếu nại ghi nhận thời gian phản hồi thành công, nhưng có những phản hồi chỉ trả thông báo từ chối nên thống kê hiệu quả bị tăng giả tạo.
Dịch vụ trích xuất nội dung tài liệu mong mỗi lần gọi chỉ có một lựa chọn câu trả lời, nhưng cấu hình thử nghiệm thay đổi số kết quả sinh và mã xử lý downstream chọn nhầm.
Một đội vận hành sử dụng ChatResponse để đối soát chi phí giữa các nhà cung cấp, nhưng trường usage không cùng cách quy đổi token trên những mô hình khác nhau.
Hệ thống giám sát ghi riêng trạng thái kết nối HTTP và trạng thái sinh nội dung, nhưng hai nhóm báo cáo lại hiểu một response thành công là nội dung đã đáp ứng yêu cầu nghiệp vụ.
Ứng dụng trợ lý bán hàng cần hiển thị câu trả lời ngay khi mô hình bắt đầu tạo văn bản, nhưng cách gọi đồng bộ khiến giao diện phải chờ đến khi hoàn tất toàn bộ.
Một chatbot dùng luồng streaming để gửi từng phần văn bản cho trình duyệt, nhưng ký tự tiếng Việt bị tách qua các chunk và bộ hiển thị ghép sai nội dung.
Trang hỏi đáp nhận các chunk từ ChatClient theo thời gian thực, nhưng nhóm frontend coi mỗi chunk là một câu hoàn chỉnh khiến dấu câu và khoảng trắng hiển thị bất thường.
Dịch vụ streaming trả lời người dùng đang đăng nhập, nhưng kết nối trình duyệt bị ngắt giữa chừng và provider vẫn tiếp tục sinh nội dung có tính phí.
Ứng dụng hỗ trợ kỹ thuật nối văn bản từ các chunk để lưu lại, nhưng khi tín hiệu hoàn tất đến bản ghi cuối khác với nội dung người dùng đã nhìn thấy.
Một dashboard hiển thị câu trả lời theo stream nhưng bộ kiểm duyệt nội dung chỉ chạy sau khi hoàn tất, khiến đoạn nội dung chưa được kiểm tra đã xuất hiện trên màn hình.
Một client di động đọc dữ liệu streaming qua mạng chậm, trong khi tốc độ sinh chunk cao hơn tốc độ tiêu thụ và bộ đệm truyền ngày càng tăng.
Đội tích hợp phát sự kiện streaming tới nhiều người dùng qua một pipeline dùng chung, nhưng phần nội dung của các phiên chat khác nhau bị trộn khi ánh xạ sai định danh.
Dịch vụ trợ lý gửi token đầu tiên rất nhanh nhưng mất thời gian dài mới sinh hết nội dung, khiến chỉ số latency trung bình không phản ánh trải nghiệm đọc của khách.
Một ứng dụng bật streaming cho thao tác cần ghi JSON hoàn chỉnh, nhưng phía xử lý cố parse từng phần JSON chưa khép kín và báo lỗi liên tục.
Nền tảng tạo bài đăng nhận stream văn bản trong lúc người dùng hủy tác vụ, nhưng hệ thống vẫn lưu đoạn nội dung dở dang như một bản nháp hoàn chỉnh.
Một proxy giữa Spring Boot và trình duyệt giữ bộ đệm cho response streaming, khiến các chunk do provider trả về không được người dùng nhìn thấy đúng thời điểm.
Ứng dụng cần theo dõi lỗi xuất hiện sau vài chunk của luồng AI, nhưng tầng giao tiếp đã gửi HTTP status thành công nên giao diện không biết câu trả lời bị gián đoạn.
Một dịch vụ hiển thị văn bản theo stream và đồng thời tính mức sử dụng token, nhưng metadata tổng kết chỉ xuất hiện ở cuối luồng khiến báo cáo chi phí cập nhật thiếu.
Đội phát triển kiểm thử streaming bằng mock chỉ phát một chunk, nhưng lỗi sắp xếp và hủy subscription chỉ xuất hiện khi provider trả nhiều chunk không đều.
Một ứng dụng dùng structured output để trích tên, địa chỉ và mã đơn hàng, nhưng mô hình đôi lúc sinh chuỗi giải thích bên ngoài JSON khiến bước chuyển đối tượng thất bại.
Dịch vụ lập lịch yêu cầu ngày bắt đầu trong đối tượng đầu ra, nhưng mô hình trả ngày theo định dạng khác chuẩn hệ thống nên không thể chuyển thành kiểu dữ liệu ứng dụng.
Hệ thống phân loại phiếu hỗ trợ mong trường mức ưu tiên chỉ thuộc ba giá trị cố định, nhưng mô hình tạo ra một nhãn mới chưa có trong enum nghiệp vụ.
Ứng dụng dùng converter để nhận danh sách sản phẩm từ mô hình, nhưng mô hình đôi khi trả một đối tượng duy nhất khi chỉ tìm thấy một sản phẩm.
Đội tuyển dụng chuyển kết quả phân tích ứng viên thành Java record, nhưng mô hình bỏ qua một trường bắt buộc và việc ánh xạ đối tượng gây lỗi ở một số hồ sơ.
Hệ thống khai báo schema cho phản hồi có số tiền và đơn vị tiền tệ, nhưng mô hình trả giá trị số dưới dạng chuỗi kèm ký hiệu khiến dữ liệu không qua được bước kiểm tra.
Một ứng dụng tạo phiếu giao hàng yêu cầu địa chỉ trong cấu trúc nhiều cấp, nhưng mô hình tự bổ sung quận không có trong thông tin gốc và phiếu bị chuyển sai nơi.
Nền tảng xử lý phản ánh của cư dân dùng structured output để lấy tọa độ địa lý, nhưng mô hình trả các giá trị ngoài miền hợp lệ và bản đồ không hiển thị.
Một dịch vụ phân loại thông tin bảo hiểm nhận dữ liệu nhạy cảm và yêu cầu JSON, nhưng phần giải thích của mô hình vô tình chứa thông tin cá nhân không được phép lưu.
Nhóm phát triển sửa trường trong lớp Java ánh xạ kết quả, nhưng prompt hướng dẫn định dạng vẫn mô tả tên trường cũ khiến lỗi chuyển đổi tăng sau triển khai.
Ứng dụng cần phân biệt trường không được trích xuất với trường có giá trị rỗng, nhưng phản hồi mô hình dùng null và chuỗi rỗng lẫn lộn làm sai trạng thái xác minh.
Một hệ thống nhập liệu tự động chấp nhận đối tượng Java đã parse thành công, nhưng các trường nội dung vẫn mâu thuẫn với nhau nên dữ liệu nghiệp vụ bị ghi sai.
Dịch vụ trích xuất hóa đơn lớn yêu cầu hàng trăm dòng sản phẩm trong một đối tượng JSON, nhưng phản hồi chạm giới hạn token và bị cắt giữa cấu trúc.
Ứng dụng trợ lý nhân sự yêu cầu kết quả phân loại chính xác theo schema, nhưng provider được chọn chỉ hỗ trợ hướng dẫn định dạng ở mức văn bản nên phản hồi không ổn định.
Đội sản phẩm đo tỷ lệ lỗi converter mà không phân biệt JSON sai cú pháp với giá trị sai nghiệp vụ, khiến nguyên nhân các lần trích xuất thất bại bị gộp chung.
Một chatbot tạo kế hoạch học tập bằng structured output, nhưng thay đổi nhỏ ở prompt khiến thứ tự hoặc số lượng mục trong danh sách khác nhau dù đầu vào giống nhau.
Nền tảng thanh toán yêu cầu mô hình sinh số tài khoản theo dữ liệu đính kèm, nhưng nội dung được tạo có vẻ đúng cấu trúc mà không khớp với nguồn chính thức.
Ứng dụng tư vấn học viên dùng schema có trường nhận xét tùy chọn, nhưng client cũ mặc định mọi trường luôn tồn tại nên gặp lỗi khi mô hình bỏ trống nhận xét.
Dịch vụ chuyển văn bản sang biểu mẫu yêu cầu phân biệt điểm tin cậy với mức độ ưu tiên, nhưng mô hình sinh cùng một con số và hệ thống downstream hiểu nhầm ý nghĩa.
Một hệ thống dựa vào tên trường của JSON để định tuyến công việc, nhưng mô hình đôi khi thêm dấu cách vào giá trị định danh khiến tác vụ được chuyển sang nhóm không tồn tại.
Ứng dụng kiểm kê cho phép nhân viên gửi ảnh nhãn sản phẩm vào câu hỏi, nhưng model được cấu hình chỉ nhận văn bản nên yêu cầu đa phương thức không được xử lý.
Nền tảng chăm sóc cây trồng gửi nhiều ảnh lá cùng mô tả vào Prompt, nhưng thứ tự ảnh không được giữ trong kết quả tổng hợp khiến nhận xét áp vào nhầm mẫu.
Một chatbot hỗ trợ bảo trì nhận hình ảnh đồng hồ thiết bị, nhưng ảnh chụp mờ vẫn khiến mô hình trả một giá trị đo rất cụ thể mà không nêu mức độ không chắc chắn.
Dịch vụ xử lý biên lai đính kèm ảnh có độ phân giải rất cao, khiến request lớn hơn giới hạn provider và thời gian truyền dữ liệu tăng đột biến.
Ứng dụng du lịch gửi ảnh hộ chiếu vào provider bên ngoài để trích thông tin, nhưng cơ chế log request vẫn lưu bản sao dữ liệu nhạy cảm của khách.
Một trợ lý học trực tuyến gửi ảnh bài tập kèm câu hỏi văn bản, nhưng nhóm chỉ kiểm thử trường hợp một ảnh và không phát hiện lỗi khi học viên đính kèm nhiều ảnh.
Nền tảng tổng đài muốn phân tích file âm thanh từ cuộc gọi, nhưng endpoint đang dùng chỉ nhận nội dung văn bản và hình ảnh theo khả năng của model đã chọn.
Hệ thống tóm tắt video nội bộ gửi một file lớn như thể là một đoạn văn bản trong prompt, khiến nhà cung cấp từ chối yêu cầu vì định dạng media không được hỗ trợ.
Một ứng dụng đọc hình ảnh tài liệu tải từ đường dẫn tạm, nhưng file bị xóa trước lúc request đa phương thức thực sự truyền đi và mô hình không thấy nội dung.
Đội phát triển dùng dữ liệu ảnh do khách hàng tải lên mà không kiểm tra kích thước và loại file, khiến một số request quá lớn hoặc sai định dạng gây lỗi không dự đoán.
Dịch vụ dùng hình ảnh nhãn thuốc để trích chữ rồi tự động gửi cảnh báo, nhưng chữ nhỏ bị mô hình đọc sai làm cảnh báo không phù hợp với nội dung thực tế.
Một chatbot bảo hiểm nhận nhiều tài liệu ảnh từ các trang hợp đồng, nhưng mô hình được cung cấp thiếu vài trang và vẫn kết luận như đã phân tích toàn bộ hồ sơ.
Ứng dụng so sánh khả năng hiểu ảnh giữa hai provider, nhưng một bên tự thay đổi kích thước ảnh đầu vào khiến kết quả và chi phí xử lý khác nhau đáng kể.
Hệ thống kiểm thử một prompt có ảnh và văn bản nhưng sử dụng mock chỉ nhận text, khiến lỗi gắn media vào message không được phát hiện trước khi triển khai.
Một trợ lý hiện trường cần phản hồi hình ảnh trong lúc mạng di động yếu, nhưng quá trình tải media lên provider kéo dài hơn thời gian chờ mà người dùng có thể chấp nhận.
Nền tảng Spring Boot cấu hình hai ChatModel từ các provider khác nhau, nhưng bean mặc định được chọn không nhất quán giữa môi trường thử nghiệm và sản xuất.
Một sản phẩm chuyển provider để giảm chi phí, nhưng cùng Prompt tạo ra mức chi tiết khác nhau khiến các bước xử lý dựa trên văn bản trả lời bị lệch.
Dịch vụ yêu cầu structured output theo schema, nhưng mô hình thay thế không hỗ trợ cùng cơ chế ràng buộc định dạng khiến tỷ lệ lỗi giải mã tăng.
Một hệ thống gọi provider dự phòng khi nhà cung cấp chính lỗi, nhưng model dự phòng có giới hạn context ngắn hơn nên các cuộc hội thoại dài vẫn thất bại.
Đội sản phẩm so sánh các model bằng kết quả một vài câu hỏi mẫu, nhưng hành vi sinh văn bản thay đổi theo tham số cấu hình và thời điểm chạy kiểm thử.
Ứng dụng dùng cùng tên model trong cấu hình của hai môi trường, nhưng nhà cung cấp cập nhật phiên bản phía sau khiến kết quả thực tế khác nhau sau triển khai.
Một chatbot tư vấn sản phẩm thay đổi nhiệt độ sinh văn bản để tăng tính sáng tạo, nhưng tên sản phẩm và thông số kỹ thuật bắt đầu bị trình bày thiếu nhất quán.
Một dịch vụ phân loại yêu cầu đầu ra ổn định, nhưng dù đặt tham số sinh với mức ngẫu nhiên thấp các lần gọi vẫn có thể trả câu chữ khác nhau.
Hệ thống đặt giới hạn số token sinh nhưng không tính lượng token trong prompt chứa lịch sử, khiến request bị từ chối trước khi mô hình bắt đầu tạo câu trả lời.
Một nhóm tích hợp chuyển từ provider tính chi phí theo token sang dịch vụ có bảng giá khác, nhưng hệ thống báo cáo vẫn áp đơn giá cũ cho mọi request.
Đội phát triển bật tính năng streaming khi đổi model nhưng provider được cấu hình có hành vi streaming khác, khiến ứng dụng phải chờ hoặc nhận kết quả dưới dạng không mong đợi.
Ứng dụng phát triển dùng khóa API chung cho cả môi trường thử nghiệm và sản xuất, khiến các đợt test tải ảnh hưởng hạn mức của người dùng thật.
Một startup sử dụng một model lớn cho cả phân loại ngắn và tạo nội dung dài, khiến độ trễ và chi phí của các yêu cầu đơn giản cao bất thường.
Ứng dụng cần lưu lịch sử theo nhiều ngôn ngữ, nhưng khi đổi model mới một số câu trả lời mặc định bằng tiếng Anh dù prompt vẫn yêu cầu tiếng Việt.
Nhóm vận hành nhận phản hồi từ provider dự phòng có cấu trúc metadata khác, khiến mã thu thập mức sử dụng và lý do kết thúc bị thiếu dữ liệu.
Một ứng dụng chọn model theo tenant nhưng cấu hình phân tuyến bị lưu cache sai, khiến yêu cầu của khách hàng giới hạn dữ liệu bị gửi sang provider không được phê duyệt.
Ứng dụng phân tích phản hồi khách hàng vô tình gửi email và số điện thoại thật của người dùng tới provider AI trong khi mục tiêu chỉ cần phân loại chủ đề.
Một nhân viên nhập văn bản có chỉ dẫn giả làm chính sách hệ thống vào biểu mẫu hỏi đáp, khiến chatbot có lúc bỏ qua hướng dẫn ban đầu và tiết lộ nội dung không phù hợp.
Dịch vụ tóm tắt email coi mọi câu chữ bên trong email là mệnh lệnh cho mô hình, khiến một thư do bên ngoài gửi có thể thay đổi yêu cầu tóm tắt ban đầu.
Nền tảng hỗ trợ nội bộ chuyển câu trả lời do AI tạo thành quyết định khóa tài khoản tự động, nhưng mô hình có lúc suy đoán sai danh tính người bị báo cáo.
Một ứng dụng nhiều tenant sử dụng chung mẫu prompt nhưng đưa nhầm lịch sử trò chuyện của tenant khác vào Prompt, khiến câu trả lời chứa dữ liệu của khách hàng không liên quan.
Đội vận hành muốn lưu mọi prompt để tái hiện lỗi, nhưng nhiều request chứa dữ liệu sức khỏe hoặc hợp đồng mà nhóm logging không có quyền truy cập.
Một hệ thống tiếp nhận dữ liệu từ website công cộng rồi dùng để đặt ngữ cảnh cho ChatClient, nhưng đoạn web chứa lệnh yêu cầu tiết lộ thông tin cấu hình ứng dụng.
Ứng dụng tạo email bán hàng tự động lấy phản hồi mô hình làm nội dung gửi ngay, nhưng một lần sinh nội dung đã chèn khẳng định sai về chính sách hoàn tiền.
Nền tảng xử lý khiếu nại để người dùng nhập chỉ dẫn dài tùy ý, khiến nội dung tấn công làm prompt phình to và chi phí xử lý tăng ngoài hạn mức.
Một chatbot được cấp quyền xem dữ liệu nhân sự nhạy cảm trong Prompt, nhưng phản hồi cho người dùng thông thường có lúc trích lại thông tin vượt quyền của họ.
Dịch vụ định dạng Markdown từ nội dung mô hình rồi hiển thị trực tiếp trên trang quản trị, khiến một số đầu ra có liên kết và nội dung HTML không đáng tin cậy.
Đội sản phẩm gắn một token truy cập của dịch vụ nội bộ vào prompt để mô hình tham khảo, khiến token có nguy cơ xuất hiện trong bản ghi phía provider hoặc câu trả lời.
Ứng dụng yêu cầu mô hình không lưu dữ liệu khách nhưng vẫn gửi nội dung nhạy cảm tới một cấu hình provider chưa được phê duyệt về lưu trữ và xử lý.
Một hệ thống tóm tắt hồ sơ ứng viên đặt hướng dẫn không sử dụng thông tin nhạy cảm, nhưng dữ liệu đầu vào vẫn chứa thuộc tính dễ dẫn đến quyết định tuyển dụng thiếu công bằng.
Dịch vụ chấm điểm bài luận đưa nhận xét do AI sinh cho giáo viên, nhưng mô hình đôi lúc dùng từ ngữ mang tính quy kết dù chưa có bằng chứng trong bài làm.
Một chatbot thương mại điện tử để mô hình tự tạo đường dẫn giảm giá trong phản hồi, khiến người dùng nhận các URL không tồn tại nhưng trông giống tên miền thật của doanh nghiệp.
Ứng dụng cho phép người dùng đính kèm tài liệu rồi hỏi về tài liệu, nhưng mô hình trả lời dựa trên kiến thức tổng quát thay vì nêu rõ thông tin còn thiếu trong tệp.
Một cửa hàng triển khai ChatClient vào luồng checkout, nhưng provider trả lỗi vượt hạn mức và dịch vụ không phân biệt được sự cố AI với lỗi thanh toán chính.
Hệ thống tạo bài đăng bị timeout khi provider quá tải, nhưng phía gọi tiếp tục retry không giới hạn khiến hàng đợi request và chi phí xử lý tăng mạnh.
Ứng dụng gửi lại Prompt sau khi mất kết nối ngay lúc provider có thể đã tạo xong kết quả, khiến một nội dung được sinh nhiều lần và bị tính phí lặp.
Dịch vụ quản lý hồ sơ nhận lỗi xác thực API key sau khi xoay vòng khóa, nhưng hệ thống tự retry như lỗi mạng tạm thời và tiếp tục thất bại hàng nghìn lần.
Một request AI có kích thước vượt giới hạn context, nhưng lớp xử lý trả thông báo chung là lỗi server khiến người dùng không biết nội dung gửi quá dài.
Đội tích hợp chỉ đặt connect timeout cho lời gọi model, khiến một số kết nối đã mở vẫn chờ rất lâu khi provider sinh phản hồi chậm.
Nền tảng gửi hàng loạt tác vụ phân loại song song, nhưng giới hạn request mỗi phút của provider làm nhiều tác vụ nhận lỗi rate limit giữa chừng.
Một workflow dùng kết quả ChatClient để tạo phiếu giao hàng rồi retry toàn bộ chuỗi khi mất phản hồi, khiến phiếu có thể được tạo nhiều lần dù khách chỉ gửi một yêu cầu.
Ứng dụng đánh dấu toàn bộ phản hồi AI lỗi thành kết quả rỗng, khiến thống kê chất lượng hiển thị nhiều trường hợp không có dữ liệu như thể khách không đặt câu hỏi.
Đội phát triển định nghĩa fallback sang model khác khi lỗi, nhưng model dự phòng có quy định xử lý dữ liệu khác khiến một số yêu cầu vi phạm chính sách của khách hàng.
Một hệ thống đồng thời gọi mô hình để phân loại hàng nghìn bình luận, nhưng không giới hạn concurrency nên số request đang chờ chiếm hết kết nối và luồng thực thi.
Ứng dụng lưu phản hồi AI xuống cơ sở dữ liệu trước khi kiểm tra tính hợp lệ, khiến một nội dung bị cắt nửa chừng vẫn được công bố như kết quả hoàn chỉnh.
Nền tảng đặt giới hạn chi phí theo ngày nhưng chỉ đếm request thành công, khiến các request bị lỗi và thử lại vẫn tiêu tốn token ngoài dự toán.
Một dịch vụ muốn hủy lời gọi AI khi người dùng đóng màn hình, nhưng tác vụ từ provider vẫn có thể tiếp tục và chi phí không giảm như dự kiến.
Đội đánh giá chất lượng dùng so sánh chuỗi tuyệt đối cho phản hồi ChatClient, khiến bài kiểm thử thất bại khi mô hình diễn đạt khác nhưng giữ nguyên ý nghĩa.
Một bộ kiểm thử dùng mock ChatModel luôn trả văn bản hợp lệ, khiến nhánh lỗi chuyển đổi structured output không được thực thi trước khi phát hành.
Nhóm QA kiểm thử một prompt bằng một kết quả mẫu, nhưng không phát hiện trường hợp mô hình trả câu trả lời rỗng hoặc lời từ chối cho cùng loại đầu vào.
Một dịch vụ kiểm thử cấu hình ChatClient mà không phân biệt system message với user message, khiến những sai lệch thứ tự chỉ xuất hiện khi chạy với provider thật.
Nền tảng phân loại phiếu hỗ trợ dựa vào phản hồi AI nhưng bài test không bao gồm văn bản có dấu tiếng Việt và ký tự đặc biệt, khiến dữ liệu thực tế bị gắn nhãn sai.
Đội phát triển chạy thử tích hợp với provider thật trên CI nhưng không có giới hạn số lần gọi, khiến chi phí kiểm thử tăng mạnh khi pipeline được chạy lại.
Một hệ thống kiểm thử định dạng JSON bằng cách kiểm tra có dấu ngoặc, khiến đối tượng thiếu trường bắt buộc vẫn được chấp nhận và đưa vào workflow.
Ứng dụng cần kiểm tra luồng streaming, nhưng mock chỉ gửi một chunk hoàn chỉnh nên không phát hiện lỗi ghép ký tự và xử lý ngắt kết nối.
Một bộ test so sánh đầu ra từ hai model với cùng prompt mà không kiểm soát tham số sinh, khiến sự khác biệt do cấu hình bị hiểu nhầm là do provider.
Đội vận hành muốn đánh giá tỷ lệ câu trả lời không có căn cứ, nhưng dashboard chỉ đo HTTP status và thời gian phản hồi thay vì chất lượng nội dung.
Ứng dụng ghi log chi tiết mọi Prompt và ChatResponse để debug, nhưng không che thông tin cá nhân khiến dữ liệu nhạy cảm xuất hiện trong nền tảng quan sát chung.
Hệ thống giám sát ghi số request nhưng không thu thập token usage, khiến đợt tăng chi phí do prompt dài không hiện trên dashboard.
Một dịch vụ gửi hàng loạt request streaming và thường bị hủy giữa chừng, nhưng cách tính tổng thời gian chỉ dựa trên các request hoàn tất nên báo cáo độ trễ sai lệch.
Nền tảng phát triển chatbot muốn so sánh chất lượng trước và sau khi đổi prompt, nhưng bộ dữ liệu đánh giá không được cố định nên kết quả hai lần đo không thể đối chiếu.
Một hệ thống cảnh báo khi mô hình trả phản hồi bị cắt nhưng không ghi model ID hoặc thông số giới hạn token, khiến nhóm trực không tái tạo được tình huống.
Đội kiểm thử chỉ kiểm tra văn bản câu trả lời, nhưng bỏ qua usage và finish reason nên không phát hiện một số request phải dừng do giới hạn sinh.
Một dịch vụ ghi trace qua nhiều lớp Spring Boot nhưng không liên kết lần gọi ChatModel với request gốc, khiến đội vận hành không xác định được người dùng nào gây tăng latency.
Ứng dụng tích hợp model mới nhưng không theo dõi tỷ lệ từ chối, JSON không hợp lệ và thông báo lỗi provider, khiến suy giảm chất lượng chỉ được phát hiện qua khiếu nại.
Nhóm sản phẩm cập nhật prompt cho trợ lý ngân hàng nhưng không lưu tập phản hồi chuẩn để đánh giá hồi quy, khiến thay đổi làm sai lời giải thích giao dịch vẫn lọt qua kiểm thử.
