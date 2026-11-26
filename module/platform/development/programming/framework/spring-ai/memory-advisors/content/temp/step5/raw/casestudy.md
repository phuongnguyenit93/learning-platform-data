Một chatbot tư vấn học phí dùng Spring AI ChatClient trả lời đúng ở lượt đầu, nhưng sang lượt sau lại quên ngành học người dùng đã chọn dù giao diện vẫn hiển thị toàn bộ lịch sử.
Ứng dụng tích hợp ChatMemory vào trợ lý bán hàng nhưng mỗi HTTP request tạo conversation ID ngẫu nhiên; khách phải lặp lại địa chỉ giao hàng ở mọi lượt trao đổi.
Một nền tảng hỗ trợ trực tuyến sử dụng chung conversation ID mặc định cho nhiều phiên đăng nhập, khiến nội dung tư vấn của khách này xuất hiện trong câu trả lời cho khách khác.
Khách hàng mở hai cửa sổ trình duyệt vào hai hội thoại khác nhau nhưng ứng dụng tái sử dụng một khóa phiên, làm ChatMemory trộn yêu cầu đổi trả với câu hỏi bảo hành.
Nhóm phát triển truyền conversation ID từ client mà không kiểm tra quyền sở hữu; một người dùng đoán được ID của người khác và xem được ngữ cảnh hội thoại cũ.
Ứng dụng dùng ChatClient với Advisor ghi nhớ hội thoại nhưng một route mới quên gắn Advisor; cùng một người dùng thấy chatbot nhớ lịch sử trên web mà quên hoàn toàn trong ứng dụng mobile.
Một chatbot nội bộ chạy nhiều instance Spring Boot và dùng memory trong tiến trình; khi load balancer chuyển request sang pod khác, trợ lý không nhận được các tin nhắn trước đó.
Ứng dụng chuyển từ bộ nhớ trong RAM sang ChatMemoryRepository lưu bền vững, nhưng sau khởi động lại vẫn mất một số lượt vì chỉ ghi lịch sử của người dùng mà không ghi câu trả lời.
Đội vận hành chia ChatMemoryRepository giữa hai môi trường staging và production; một cuộc hội thoại thử nghiệm bất ngờ xuất hiện trong hệ thống phục vụ khách hàng thật.
Nhóm cấu hình repository lưu hội thoại theo userId nhưng không phân biệt conversationId; khi người dùng mở nhiều phiên tư vấn, các câu hỏi của dự án khác nhau bị ghép thành một luồng.
Một ứng dụng Spring AI lưu tin nhắn theo conversationId nhưng không có thời điểm tạo ổn định; sau khi khôi phục từ database, thứ tự hội thoại khác lúc người dùng gửi.
Khách gửi hai câu hỏi liên tiếp trong cùng phiên trước khi phản hồi đầu tiên hoàn tất; hai request cạnh tranh cập nhật ChatMemory và lịch sử hiển thị thiếu một lượt.
Nhóm triển khai chatbot trên hai node với repository dùng chung, nhưng mỗi node có thêm cache cục bộ chưa đồng bộ; câu trả lời luân phiên dựa trên hai phiên bản lịch sử khác nhau.
Một trợ lý đặt lịch ghi lời đáp vào ChatMemory trước khi đặt lịch thực sự hoàn tất; sau lỗi dịch vụ lịch, lượt tiếp theo của khách dựa trên xác nhận sai từ hội thoại trước.
Ứng dụng ghi mỗi thông điệp ChatClient vào ChatMemory khi xử lý nhưng một lần retry từ gateway tạo thêm bản ghi giống hệt, làm trợ lý nghĩ người dùng nhắc yêu cầu hai lần.
Một luồng phản hồi streaming bị ngắt ở giữa câu; repository vẫn lưu phần trả lời chưa hoàn chỉnh và chatbot dùng mảnh nội dung đó như lời cam kết ở lượt sau.
ChatClient gọi model thành công nhưng kết nối tới ChatMemoryRepository thất bại; người dùng nhận câu trả lời trong khi lịch sử trên máy chủ không phản ánh lượt vừa xảy ra.
Người dùng xóa một tin nhắn nhầm trong giao diện nhưng backend không xóa bản tương ứng khỏi ChatMemory; chatbot tiếp tục nhắc lại thông tin đã được rút khỏi cuộc trò chuyện.
Một nhân viên hỗ trợ đổi thiết bị khi đang trò chuyện, nhưng phiên mới không khôi phục đúng conversation ID; các yêu cầu đã xác nhận trước đó không còn trong ngữ cảnh.
Ứng dụng cho phép tiếp tục hội thoại từ email cũ nhưng conversation ID đã được tái cấp phát cho phiên khác; nội dung mới vô tình nối vào lịch sử không liên quan.
Một người dùng gửi tin nhắn rỗng hoặc chỉ chứa khoảng trắng qua API ChatClient; hệ thống vẫn lưu lượt trao đổi vào ChatMemory và làm cửa sổ lịch sử nhanh chóng đầy.
Nhóm kiểm thử chỉ tạo một cuộc trò chuyện tuần tự; khi có hàng nghìn conversationId hoạt động đồng thời, repository tăng độ trễ và người dùng gặp câu trả lời thiếu ngữ cảnh.
Trợ lý khách hàng dùng MessageChatMemoryAdvisor để bổ sung thông điệp cũ, nhưng cấu hình default Advisor của ChatClient khác cấu hình cho từng request khiến số lượt ghi nhớ không nhất quán.
Ứng dụng thay thứ tự các Advisor khi thêm cơ chế kiểm soát nội dung; dữ liệu đưa vào ChatMemory không còn trùng với thông điệp thực sự được gửi tới model.
Một nhóm dùng PromptChatMemoryAdvisor để chèn lịch sử thành văn bản trong prompt, nhưng nội dung cũ chứa chỉ dẫn trái với quy tắc hệ thống và câu trả lời bị dẫn lệch.
ChatClient được tạo một lần cho nhiều loại nhiệm vụ nhưng Advisor ghi nhớ cũng chạy trên yêu cầu phân loại dữ liệu không phải hội thoại; bộ nhớ chứa hàng nghìn kết quả máy móc.
Một service dùng Advisor để viết lại câu hỏi theo lịch sử trước khi truy xuất tài liệu, nhưng thứ tự Advisor làm bước tìm kiếm nhìn thấy câu hỏi chưa có ngữ cảnh và trả sai nguồn.
Ứng dụng có một Advisor theo dõi chi phí và một Advisor ghi nhớ, nhưng số lượng thông điệp quan sát được khác nhau giữa chúng khiến việc đối soát token theo phiên gặp khó.
Nhóm triển khai custom Advisor ghi log prompt sau khi lịch sử được thêm vào; log tập trung vô tình chứa những thông tin cá nhân từ nhiều lượt trao đổi cũ.
ChatClient dùng cấu hình memory Advisor toàn cục cho mọi endpoint, kể cả chức năng tạo bản tóm tắt độc lập; kết quả mới bị ảnh hưởng bởi hội thoại trước dù người dùng không yêu cầu.
Một bot phân tích hóa đơn cần nhớ ngữ cảnh nhiều lượt nhưng không được dùng các ví dụ nội bộ làm dữ liệu lịch sử; custom Advisor vẫn lưu toàn bộ prompt mẫu vào ChatMemory.
Ứng dụng bật một Advisor truy xuất ngữ nghĩa bên cạnh Advisor lịch sử gần, nhưng cả hai cùng chèn lại những câu giống nhau làm ngữ cảnh lặp và tăng token.
Một chatbot đổi ChatClient builder trong đợt nâng cấp Spring AI; phần cấu hình Advisor đang dùng không được áp vào client mới, khiến sản phẩm mất tính năng nhớ mà không có lỗi biên dịch.
Trợ lý công nghệ hỗ trợ các tác vụ tool calling, nhưng Advisor chỉ lưu câu trả lời cuối mà không ghi lại ngữ cảnh thực hiện thao tác; lượt sau khó giải thích vì sao dữ liệu đã đổi.
Một ứng dụng lưu cả kết quả công cụ gọi API thanh toán vào lịch sử hội thoại; khi dữ liệu trạng thái thay đổi, chatbot tiếp tục tin vào kết quả cũ thay vì tra cứu lại.
Người dùng yêu cầu chatbot quên một chi tiết đã nói, nhưng Advisor vẫn đưa chi tiết đó từ lịch sử vào prompt ở những lượt sau; giao diện báo xóa trong khi câu trả lời còn nhắc tới.
Một phần mềm CRM cho phép người dùng chuyển chatbot giữa các vai trò bán hàng và chăm sóc khách; Advisor tái sử dụng lịch sử không đúng ngữ cảnh quyền hạn của vai trò mới.
Trong hệ thống quản lý dự án, người dùng nhắc tới hai sản phẩm bằng cùng một tên viết tắt; bộ nhớ lịch sử giữ diễn giải từ sản phẩm cũ và chatbot hiểu sai các câu hỏi của dự án mới.
Trợ lý học ngoại ngữ cần nhớ những lỗi phát âm người dùng từng mắc, nhưng cửa sổ hội thoại chỉ giữ vài tin gần nhất nên việc cá nhân hóa biến mất sau buổi học dài.
Một bot hỏi đáp chính sách giữ 20 thông điệp mới nhất trong MessageWindowChatMemory, nhưng một phản hồi dài chứa nhiều bảng làm tổng token vượt giới hạn model dù số lượt vẫn hợp lệ.
ChatMemory được cấu hình cửa sổ quá nhỏ để giảm token, khiến câu hỏi 'vậy điều khoản thứ ba thì sao' mất tham chiếu đến hợp đồng đã nhắc từ đầu phiên.
Nhóm tăng kích thước cửa sổ hội thoại để cải thiện trí nhớ, nhưng chi phí mỗi request tăng theo chiều dài phiên và độ trễ người dùng chờ phản hồi ngày càng cao.
Ứng dụng loại bỏ các thông điệp cũ theo số lượng cố định, nhưng một thông điệp hệ thống chứa quy tắc bắt buộc lại bị xử lý giống như lịch sử thông thường.
Trong một hội thoại hỗ trợ kỹ thuật, người dùng cung cấp log lỗi ở đầu phiên và hỏi thêm sau nhiều lượt; log đã bị rơi khỏi cửa sổ khiến chatbot đưa ra chẩn đoán không dựa trên bằng chứng.
Một ứng dụng ChatMemory giữ các tin từ khách nhưng bỏ qua phản hồi của trợ lý; ở lượt tiếp theo model không biết lời khuyên nào đã được đưa ra và lặp lại hướng dẫn.
Nhóm làm sạch lịch sử bằng cách chỉ giữ phản hồi của trợ lý, nhưng không giữ câu hỏi đi kèm; model tưởng các đoạn trả lời cũ là những yêu cầu độc lập của người dùng.
Chatbot tư vấn bảo hiểm dùng cửa sổ theo số tin nhắn thay vì theo lượt hỏi–đáp; sau khi cắt lịch sử, câu trả lời gần nhất không còn câu hỏi tương ứng nên rất dễ bị hiểu sai.
Một ứng dụng chèn toàn bộ lịch sử dài vào prompt trước khi cắt bớt; yêu cầu bị từ chối vì vượt context window dù bộ nhớ đáng lẽ phải giới hạn đầu vào.
Một doanh nghiệp giảm ngưỡng lưu lịch sử từ 50 xuống 10 thông điệp, nhưng các cuộc hội thoại đang mở tiếp tục mang dữ liệu cũ trong một số instance chưa nhận cấu hình.
Trợ lý quản lý lịch công tác ghi nhớ thời gian họp do người dùng thay đổi nhiều lần; cửa sổ cuối chỉ giữ thông báo hủy mà mất lịch ban đầu khiến chatbot hiểu sai trạng thái cuộc hẹn.
Nhóm triển khai tóm tắt lịch sử cũ để tiết kiệm token, nhưng bản tóm tắt bỏ sót điều kiện 'không gọi điện sau 18 giờ' và bot tiếp tục đề xuất hành động trái mong muốn.
Một ứng dụng tạo bản tóm tắt bộ nhớ sau mỗi năm lượt nhưng không lưu phiên bản nguồn; khi người dùng sửa thông tin cá nhân, bản tóm tắt cũ vẫn được ưu tiên ở prompt.
Trong hội thoại dài, hai bản tóm tắt được tạo đồng thời từ các mốc khác nhau; ChatMemory lưu cả hai với thông tin trái ngược về yêu cầu của khách.
Chatbot chăm sóc sức khỏe giữ những khuyến nghị cũ nhưng thiếu thời điểm ghi nhận; khi người dùng báo tình trạng mới, câu trả lời lại dựa trên dữ liệu đã lỗi thời.
Nhóm áp giới hạn token chung cho system prompt, memory và tài liệu truy xuất nhưng không phân bổ ngân sách từng phần; một lượt truy vấn dài làm mất toàn bộ dữ liệu từ nguồn quan trọng.
Ứng dụng dùng bộ đếm token của một model để quyết định cắt lịch sử cho model khác; cùng một đoạn ChatMemory có số token thực tế vượt dự tính ở môi trường production.
Một bot viết nội dung lưu nhiều tin trả lời dài do model tạo; lịch sử chiếm phần lớn ngân sách ngữ cảnh và các chỉ dẫn mới của người dùng bị cắt bớt.
Hệ thống cho người dùng đính kèm hình ảnh và văn bản trong hội thoại, nhưng bộ nhớ chỉ hiểu nội dung text; lượt sau chatbot không còn biết người dùng đang nói đến ảnh nào.
Trong một buổi họp dài, ChatMemory giữ cả các câu nhắc lại tự động từ trợ lý, khiến nội dung trùng lặp đẩy những quyết định thật của người tham gia ra khỏi cửa sổ.
Trợ lý lập kế hoạch du lịch ghi nhớ ngân sách cũ dù người dùng vừa đổi mức chi tiêu, làm các đề xuất sau đó không nhất quán với thông tin mới nhất.
Một hệ thống đào tạo lưu tiến độ học trong ChatMemory như văn bản tự do; khi người học mở lại sau vài tuần, bot trả lời về bài cũ thay vì tiến độ chính thức từ database.
Ứng dụng hỗ trợ thuê xe nhận yêu cầu bằng tiếng Việt rồi người dùng đổi sang tiếng Anh; lịch sử có các tên địa điểm khác cách viết khiến model không nối được cùng một điểm đến.
Chatbot văn phòng ghi nhớ biệt danh người dùng tự đặt cho dự án, nhưng cửa sổ mới không còn câu giải thích biệt danh; các bước sau gán sai tên dự án.
Một phần mềm kế toán muốn nhớ lựa chọn đơn vị tiền tệ trong phiên, nhưng đồng thời phải lấy tỷ giá mới ở mỗi request; dữ liệu lịch sử bị hiểu nhầm là tỷ giá hiện hành.
Ứng dụng ChatMemoryRepository sử dụng PostgreSQL chung với nghiệp vụ; khi một giao dịch batch làm database chậm, mọi request ChatClient phải chờ ghi lịch sử.
Đội phát triển cấu hình repository in-memory để thử nghiệm nhưng quên thay bằng backend bền vững khi lên production; sau mỗi lần redeploy, tất cả hội thoại mất.
Nhóm vận hành triển khai ChatMemoryRepository dựa vào JDBC nhưng chưa cấu hình schema tương ứng trong môi trường mới; ChatClient kết nối model thành công nhưng chức năng lưu lịch sử thất bại.
Một repository lưu nhiều triệu thông điệp mà không có chiến lược truy vấn theo conversationId hiệu quả; thời gian tải lịch sử tăng dần theo số tháng vận hành.
Ứng dụng dùng một bảng lưu chat chung cho nhiều tenant, nhưng chỉ lọc theo conversationId; khi hai tenant có ID phiên trùng nhau, lịch sử của họ bị gộp.
Nhóm triển khai repository với trường metadata gồm userId nhưng API đọc lịch sử chỉ kiểm tra conversationId; một người dùng đoán ID có thể mở được dữ liệu của người khác.
Một job dọn dữ liệu xóa message của các hội thoại đã hết hạn trong lúc request ChatClient đang đọc lịch sử; phản hồi tạo ra dựa trên tập tin nhắn bị thiếu một phần.
Ứng dụng gửi tin nhắn và ghi memory trong hai transaction tách biệt; database của nghiệp vụ đã xác nhận nhưng lịch sử chat không phản ánh hành động được thực hiện.
Đội vận hành chuyển dữ liệu ChatMemoryRepository sang vùng mới, nhưng một số bản ghi bị thiếu thứ tự hoặc timestamp; chatbot tiếp tục cuộc nói chuyện với diễn biến bị đảo.
Nhóm sao lưu database hội thoại mỗi đêm nhưng không kiểm tra khôi phục theo conversationId; sau một sự cố chỉ có một phần thông điệp trong phiên được phục hồi.
Ứng dụng ghi cùng một tin nhắn từ webhook và giao diện vào ChatMemoryRepository; không có khóa nhận diện nguồn khiến lịch sử xuất hiện hai bản của cùng lời nhắn.
Một cơ sở dữ liệu hội thoại có thể ghi thành công nhưng phản hồi xác nhận cho ứng dụng bị mất; retry thao tác lưu làm bản ghi trùng lặp và thay đổi nội dung prompt.
Nhóm xây endpoint xuất lịch sử từ repository nhưng không giữ vai trò USER hay ASSISTANT của từng thông điệp; dữ liệu đưa lại vào ChatMemory bị hiểu sai bên phát ngôn.
Ứng dụng trộn tin nhắn hệ thống và tin của người dùng trong cùng định dạng lưu trữ mà không kiểm soát quyền sửa; một yêu cầu từ trình duyệt có thể giả dạng chỉ dẫn cấp cao.
Một ChatMemoryRepository giữ lịch sử mãi mãi để hỗ trợ điều tra lỗi, nhưng chính sách lưu giữ của doanh nghiệp chỉ cho phép lưu hội thoại trong thời hạn ngắn.
Nhóm nâng cấp Spring AI thay đổi cách biểu diễn message lưu trữ; các bản ghi từ phiên bản cũ được khôi phục với thiếu nội dung hoặc vai trò không đúng.
Ứng dụng dùng cache lịch sử cho những phiên phổ biến nhưng không xóa cache khi người dùng rút lại một tin nhắn; model vẫn thấy nội dung đã bị xóa ở repository.
Đội vận hành mở rộng chatbot sang hai vùng địa lý, repository đồng bộ bất đồng bộ; người dùng chuyển vùng giữa phiên thấy thiếu những lượt vừa gửi ở vùng còn lại.
Một ứng dụng chat thực hiện trả lời streaming đồng thời ghi message cuối vào repository; khi người dùng bấm gửi tiếp trước khi stream kết thúc, lượt tiếp theo tải lịch sử chưa hoàn chỉnh.
ChatMemory lưu lời khuyên từ trợ lý và câu hỏi người dùng vào cùng phiên nhưng không có mã tương quan lượt; khi hai request cùng chạy, câu trả lời bị ghép với câu hỏi khác.
Một trợ lý quản lý nhân sự lưu câu hỏi tuyển dụng có dữ liệu cá nhân nhưng không mã hóa repository; tài khoản hỗ trợ hệ thống có quyền đọc raw message ngoài nhu cầu công việc.
Nhóm dùng ChatMemoryRepository lưu thông điệp đã được mã hóa, nhưng bước ghi log exception vô tình chứa nguyên văn câu hỏi trước khi mã hóa.
Ứng dụng cho khách yêu cầu tải xuống lịch sử của chính họ, nhưng truy vấn xuất dữ liệu dựa trên userId hiện tại và vô tình bao gồm cả cuộc trò chuyện của tài khoản dùng chung.
Một doanh nghiệp thực hiện quyền xóa dữ liệu hội thoại nhưng chỉ xóa bản ghi trong ChatMemoryRepository; bản tóm tắt và embedding bộ nhớ dài hạn vẫn tồn tại ở Vector Store.
Đội hỗ trợ tạo tài khoản tạm để kiểm tra lỗi và mượn conversationId của khách thật; dữ liệu tư vấn riêng tư bị gửi vào prompt của tài khoản kỹ thuật.
Một ứng dụng chatbot được nhúng trên nhiều website đối tác, nhưng cookie phiên bị chia sẻ cùng domain và không phân tách tenant; lịch sử của hai đối tác có thể lẫn nhau.
Người dùng thay đổi quyền truy cập dự án trong ngày, nhưng ChatMemory vẫn giữ trích đoạn tài liệu mật của quyền cũ; câu hỏi mới có thể khiến model tiết lộ thông tin không còn được cấp.
Nhóm bảo mật tắt tính năng ghi memory cho chủ đề nhạy cảm ở giao diện, nhưng một endpoint ChatClient chạy nền vẫn lưu nội dung người dùng vào ChatMemoryRepository.
Trợ lý nội bộ nhận một đoạn văn bản do người dùng dán chứa chỉ dẫn 'ghi nhớ vĩnh viễn'; custom Advisor coi đó là lệnh hệ thống và lưu thông tin không được phép.
Một kẻ tấn công để lại thông điệp trong hội thoại chung yêu cầu bot bỏ qua kiểm tra danh tính ở các lượt sau; ChatMemory đưa lại câu này trong prompt của người dùng khác.
Ứng dụng lưu token truy cập mà người dùng vô tình gửi vào chat, rồi Advisor đưa token cũ vào nhiều request tiếp theo và hệ thống quan sát lưu lại bản sao.
Người dùng đã rút quyền cho chatbot lưu dữ liệu cá nhân nhưng repository vẫn tiếp tục được cập nhật từ những lượt mới; trạng thái đồng ý ở frontend không được áp tại backend.
Một chatbot trong ứng dụng ngân hàng tạo tên khóa hội thoại từ email người dùng, rồi ghi khóa đó vào log metrics; địa chỉ khách hàng xuất hiện trong nhãn giám sát.
Đội phát triển cho phép nhân viên hỗ trợ xem lịch sử hội thoại để gỡ lỗi nhưng không ghi audit người đã xem; sau khi có khiếu nại, không thể truy vết truy cập nội bộ.
Ứng dụng cần giữ ngữ cảnh giữa các phiên nhưng không được lưu số giấy tờ định danh; bước chuẩn hóa memory không tách được thông tin nhạy cảm khỏi dữ kiện hữu ích.
Chatbot bán hàng phục vụ khách chưa đăng nhập và tự gắn conversationId từ trình duyệt; một phiên ẩn danh có thể bị người khác sử dụng lại trên máy công cộng.
Nhóm QA ghi toàn bộ prompt sau khi Advisor chèn lịch sử vào hệ thống log chia sẻ; dữ liệu khách từ những lượt trước bị nhân bản qua nhiều môi trường giám sát.
Một cuộc hội thoại chứa yêu cầu xóa lịch sử, nhưng dịch vụ tìm kiếm bộ nhớ ngữ nghĩa trả lại thông tin đó từ index cập nhật chậm vào ngay lượt trả lời tiếp theo.
Ứng dụng dùng ChatMemory để nhớ một số sở thích lâu dài nhưng bộ nhớ cửa sổ chỉ giữ lượt gần; sau khi người dùng quay lại một tháng, thông tin cá nhân hóa không còn.
Nhóm tích hợp Vector Store để tìm các đoạn hội thoại tương tự theo embedding, nhưng không giữ conversationId trong metadata; chatbot lấy lại lời nói từ các phiên khác.
Một hệ thống đa tenant lưu semantic memory trong cùng Vector Store và chỉ áp filter quyền sau bước topK; kết quả gần nhất của tenant khác vẫn ảnh hưởng tới câu trả lời.
Trợ lý học tập ghi nhớ những chủ đề người dùng từng hỏi qua vector, nhưng embedding của các câu phủ định như 'không muốn học Java' bị xếp gần lời đề xuất học Java.
Một khách đã đổi sở thích từ xe chạy xăng sang xe điện, nhưng Vector Store vẫn trả về nhiều đoạn chat cũ về xe xăng do số lượng bản ghi quá lớn.
Nhóm dùng vector memory cho các chi tiết chính xác như số hợp đồng và mã đặt chỗ; truy xuất theo ngữ nghĩa trả một mã tương tự và trợ lý tham chiếu nhầm khách hàng.
Một chatbot đặt bàn ghi nhớ nhiều lần người dùng thích ăn chay, nhưng không phân biệt câu hỏi về sở thích người khác; bộ nhớ dài hạn gán sai khẩu vị cho chủ tài khoản.
Ứng dụng ghi embedding cho toàn bộ nội dung các cuộc trò chuyện kể cả lời chào và tin tự động; kết quả tìm semantic memory bị lấp bởi những câu không mang thông tin lâu dài.
Nhóm ingest các tóm tắt hội thoại vào Vector Store nhưng không lưu thời điểm và nguồn gốc; trợ lý đưa sở thích cũ vào câu trả lời mà không biết đã lỗi thời.
Một nền tảng hỗ trợ chuyên gia dùng semantic memory để tìm quyết định trước đó của nhóm, nhưng các đoạn lấy về thiếu ngữ cảnh người đã phê duyệt và thời điểm hiệu lực.
Chatbot dùng cả cửa sổ lịch sử gần và semantic retrieval, nhưng cùng một quyết định xuất hiện ở hai nguồn với cách diễn đạt khác nhau; model xem đó là hai sự kiện độc lập.
Người dùng muốn tìm lại một chi tiết được nhắc ở giữa cuộc trò chuyện rất dài, nhưng topK của Vector Store quá thấp và trả về các lần nhắc gần đây ít liên quan.
Nhóm tăng topK của semantic memory để tránh bỏ sót thông tin, khiến prompt chứa hàng nghìn token trùng lặp và câu trả lời chậm hơn đáng kể.
Ứng dụng áp similarity threshold cho bộ nhớ dài hạn dựa trên mô hình embedding cũ; sau nâng cấp model, nhiều thông tin liên quan không còn được tìm lại.
Đội phát triển tạo embedding cho lịch sử bằng model một phiên bản và câu hỏi bằng model khác; Vector Store vẫn nhận truy vấn nhưng độ tương đồng không còn đáng tin.
Nhóm chuyển toàn bộ semantic memory sang PGvector nhưng không giữ metadata nguồn; khi khách yêu cầu xóa một cuộc trò chuyện, các vector liên quan không thể xác định chính xác.
Ứng dụng ghi cả các câu trả lời sai của trợ lý vào semantic memory; ở những cuộc trò chuyện sau, những câu trả lời cũ được truy xuất và làm tăng lỗi lặp lại.
Một trợ lý cá nhân dùng vector memory để lưu thông tin do người dùng khẳng định, nhưng một câu nói mỉa mai lại được ghi thành sự thật và ảnh hưởng các đề xuất lâu dài.
Nhóm xây cơ chế kết hợp memory ngắn hạn với Vector Store nhưng không có quy tắc ưu tiên dữ liệu; khi sở thích hiện tại trái với bản ghi cũ, câu trả lời dao động giữa hai phương án.
Ứng dụng đồng bộ ChatMemoryRepository và Vector Store theo hai job riêng; sau khi khách chỉnh sửa lời nhắn, lịch sử gần đã đúng nhưng vector vẫn biểu diễn bản cũ.
Một chatbot tìm thông tin từ tài liệu nội bộ và lịch sử cá nhân trong cùng Vector Store; thiếu loại nguồn metadata khiến câu nói của người dùng bị coi là chính sách công ty.
Nhóm dự tính dùng semantic memory cho người dùng đã đồng ý cá nhân hóa nhưng trong quá trình thử nghiệm vẫn tạo embedding cho cả khách đã từ chối lưu dữ liệu.
Ứng dụng dùng kết quả vector để nhắc lại thông tin đã nói trong cuộc trò chuyện, nhưng không kiểm tra quyền xem của người dùng hiện tại đối với đoạn lịch sử nguồn.
Một người dùng kể chuyện hư cấu trong chat, nhưng hệ thống lưu nhân vật và sự kiện vào long-term semantic memory dưới dạng dữ kiện đời thực.
Nhóm triển khai tóm tắt hội thoại trước khi embedding nhưng bản tóm tắt được sinh bất đồng bộ; người dùng hỏi lại ngay sau đó mà memory chưa chứa dữ kiện vừa nêu.
Một Vector Store lưu cả các đoạn chat đã hết hạn và bản tóm tắt của chúng; job xóa chính chỉ dọn repository nên kết quả truy xuất vẫn có thông tin lẽ ra phải xóa.
Trợ lý tài chính dùng semantic memory chứa những lời khuyên đầu tư trước đây, nhưng không kiểm tra thị trường hiện tại; lời khuyên cũ được trình bày như dữ liệu mới.
Ứng dụng khởi tạo Advisor ghi nhớ bằng một thứ tự khác giữa hai profile Spring; kết quả memory retrieval trên staging và production khác nhau dù input giống hệt.
ChatClient gắn cả Advisor lưu memory và Advisor truy xuất vector, nhưng custom logic thêm lịch sử trùng lặp khiến request chứa cùng câu hỏi nhiều lần và tăng token.
Nhóm muốn tối ưu chi phí bằng cách gọi model nhỏ để tóm tắt lịch sử, nhưng bản tóm tắt không giữ các ràng buộc nghiệp vụ và làm tăng số lượt người dùng phải hỏi lại.
Đội vận hành lưu toàn bộ câu trả lời streaming thành nhiều mảnh trong ChatMemoryRepository thay vì một thông điệp hoàn chỉnh; số bản ghi và thời gian tải lịch sử tăng nhanh.
Một ứng dụng có vài triệu phiên chat nhưng không thu hồi memory của cuộc hội thoại đã kết thúc; dung lượng repository tăng và các thao tác truy vấn bắt đầu vượt SLA.
Nhóm tạo embedding cho mọi lượt chat để có semantic memory, nhưng những câu lặp đi lặp lại của bot làm hóa đơn embedding tăng mà độ chính xác truy xuất không cải thiện.
Trợ lý tư vấn đa ngôn ngữ cần tra cứu trí nhớ từ các phiên tiếng Anh khi người dùng hỏi tiếng Việt; embedding model chưa được đánh giá xuyên ngôn ngữ và thường bỏ sót dữ kiện.
Ứng dụng có hàng nghìn conversationId cùng hoạt động, nhưng truy vấn repository và Vector Store trên một pool kết nối nhỏ; giờ cao điểm xuất hiện queue chờ và timeout.
Nhóm đo latency của ChatClient chỉ tính thời gian gọi model, bỏ qua truy xuất ChatMemoryRepository và Vector Store; biểu đồ báo nhanh dù người dùng phải chờ lâu.
Đội triển khai ghi metrics với conversationId làm nhãn trực tiếp; số lượng chuỗi thời gian giám sát tăng quá nhanh và gây áp lực lên hệ thống quan sát.
Ứng dụng bật log chi tiết cho Advisor nhằm tìm lỗi lịch sử, nhưng log chứa toàn bộ prompt đã chèn memory và chi phí lưu trữ tăng nhanh cùng rủi ro lộ dữ liệu.
Một chatbot tính token bằng độ dài ký tự thay vì tokenizer của model; cấu hình giới hạn ngữ cảnh thường xuyên không ngăn được yêu cầu vượt ngưỡng.
Nhóm giới hạn số tin nhắn lưu trong MessageWindowChatMemory nhưng không theo dõi tốc độ tạo token; một phiên với câu trả lời dài vẫn chiếm ngân sách gấp nhiều lần dự kiến.
Trợ lý thương mại chạy chiến dịch khiến số hội thoại mới tăng đột biến; ChatMemoryRepository ghi nhiều lần mỗi lượt và database đạt giới hạn IOPS trước khi model quá tải.
Một dịch vụ dùng cache semantic memory theo conversationId nhưng không làm mới khi vector mới xuất hiện; người dùng vừa cung cấp sở thích nhưng hệ thống tiếp tục đọc bản cache cũ.
Nhóm rút ngắn thời gian lưu hội thoại để giảm chi phí nhưng không tính đến việc khách quay lại sau kỳ nghỉ; bot mất thông tin đã xác nhận và yêu cầu khách nhập lại giấy tờ.
Ứng dụng tạo cuộc trò chuyện mới sau khi khách đăng xuất, nhưng các bản ghi semantic memory vẫn gắn với tài khoản cũ trên thiết bị dùng chung và người đăng nhập sau được cá nhân hóa sai.
Đội QA chỉ kiểm thử hội thoại hai lượt; khi chạy chuỗi 100 lượt có đổi chủ đề, cửa sổ lịch sử và vector memory cùng đưa những dữ kiện không còn phù hợp vào prompt.
Nhóm kiểm thử song song hai cuộc hội thoại có cùng userId nhưng khác conversationId; hệ thống hiển thị đúng ở UI song bộ nhớ backend lại trộn thông điệp.
Một bài test giả lập lỗi repository ngay sau khi model trả lời; kết quả trả cho người dùng thành công nhưng lượt sau không thể giải thích câu trả lời vừa có.
Nhóm giả lập timeout giữa chừng trong phản hồi streaming nhưng chỉ kiểm tra nội dung hiển thị; ChatMemory lưu những đoạn chưa hoàn chỉnh mà bài test không phát hiện.
Đội tích hợp thử restart pod trong khi chatbot đang trả lời, nhưng không kiểm tra thứ tự và độ đầy đủ của thông điệp sau khi phiên mới tải lại repository.
Một bài kiểm thử quyền riêng tư chỉ xóa lịch sử ChatMemoryRepository mà không tìm kiếm lại trong Vector Store; kiểm toán sau đó vẫn truy xuất được các thông tin bị yêu cầu xóa.
Nhóm thử thay đổi vai trò người dùng giữa hai lượt chat nhưng chỉ kiểm tra endpoint truy xuất tài liệu; Advisor vẫn đính kèm memory được tạo dưới quyền trước đó.
Đội đánh giá chất lượng chỉ chấm câu trả lời đúng theo lượt riêng lẻ, không có bộ test hỏi lại để đo khả năng giữ ngữ cảnh qua nhiều lượt và nhiều phiên.
Một ứng dụng đo tỷ lệ nhớ đúng sở thích của người dùng trên một tập khách thử nghiệm nhỏ; khi triển khai đa tenant, các lỗi lẫn bộ nhớ gây rủi ro lớn hơn độ chính xác tìm kiếm.
Nhóm bảo trì nâng cấp Spring AI và thay cấu hình ChatMemory Advisor, nhưng không chạy regression test các cuộc hội thoại cũ; người dùng phát hiện bot quên toàn bộ dự án đang làm.
Trong một đợt chuyển vùng dữ liệu, ChatMemoryRepository được phục hồi đến thời điểm khác Vector Store; memory gần và semantic memory đưa hai phiên bản sở thích mâu thuẫn.
Một chatbot trên Spring Boot được health check là hoạt động dù repository lưu lịch sử bị ngắt kết nối; các câu trả lời vẫn tạo được nhưng tính năng giữ ngữ cảnh âm thầm thất bại.
Đội vận hành phát hành phiên bản mới của Advisor đọc lịch sử theo cách khác, nhưng trace không ghi memory version và conversationId an toàn; không thể tái hiện vì sao một lượt chat cho kết quả sai.
