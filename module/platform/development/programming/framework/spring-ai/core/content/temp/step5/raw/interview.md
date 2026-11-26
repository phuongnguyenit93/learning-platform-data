Bạn giải thích vai trò của Spring AI trong kiến trúc ứng dụng Spring Boot tích hợp mô hình ngôn ngữ như thế nào?
Bạn phân biệt trách nhiệm của ứng dụng Spring Boot và dịch vụ mô hình AI trong một luồng xử lý yêu cầu ra sao?
Bạn xác định tiêu chí để tích hợp mô hình qua Spring AI thay vì gọi HTTP API của provider trực tiếp như thế nào?
Bạn mô tả hành trình của một yêu cầu người dùng từ controller tới mô hình và quay về qua Spring AI như thế nào?
Bạn sẽ xác định ranh giới giữa logic nghiệp vụ và lớp truy cập mô hình trong một dự án như thế nào?
Bạn thiết kế một service AI có hợp đồng rõ ràng để nhiều controller sử dụng như thế nào?
Bạn giải thích sự khác nhau giữa lời gọi mô hình AI và truy vấn dữ liệu có kết quả xác định ra sao?
Bạn xác định những nghiệp vụ nào phù hợp hoặc không phù hợp để sử dụng kết quả do mô hình sinh như thế nào?
Bạn đánh giá độ tin cậy, chi phí và thời gian phản hồi khi đưa tính năng AI vào ứng dụng như thế nào?
Bạn phân tích những rủi ro khi chuyển chức năng dựa trên quy tắc cố định sang dùng mô hình sinh như thế nào?
Bạn lựa chọn xử lý đồng bộ hay bất đồng bộ cho một tác vụ AI dựa trên yêu cầu sản phẩm ra sao?
Bạn mô tả sự khác nhau giữa cấu hình provider và cấu hình hành vi của từng yêu cầu AI như thế nào?
Bạn tổ chức cấu hình Spring Boot cho model, credentials và endpoint ở nhiều môi trường như thế nào?
Bạn ngăn mã nguồn và log vô tình chứa API key của provider bằng những cơ chế nào?
Bạn phân biệt việc dùng starter Spring AI với việc phụ thuộc trực tiếp vào SDK của nhà cung cấp như thế nào?
Bạn xác định phiên bản Spring AI tương thích với phiên bản Spring Boot hiện có ra sao?
Bạn đánh giá tác động của việc nâng cấp Spring AI đối với cấu hình, API và định dạng response như thế nào?
Bạn thiết kế phương án thay provider mà không sửa toàn bộ logic nghiệp vụ ra sao?
Bạn giải thích vai trò của ChatModel trong Spring AI so với ChatClient như thế nào?
Bạn phân biệt tương tác mức thấp qua ChatModel với cách xây dựng yêu cầu qua ChatClient như thế nào?
Bạn sử dụng ChatModel khi cần kiểm soát trực tiếp Prompt và ChatResponse trong trường hợp nào?
Bạn mô tả cách tạo một Prompt để gửi tới ChatModel và nhận kết quả như thế nào?
Bạn đọc nội dung câu trả lời từ ChatResponse mà vẫn giữ thông tin metadata cần thiết ra sao?
Bạn phân biệt nội dung văn bản trả về với đối tượng response đầy đủ của mô hình như thế nào?
Bạn sử dụng metadata của ChatResponse để kiểm soát chi phí hoặc phân tích lỗi như thế nào?
Bạn lựa chọn cấu hình ChatClient dùng chung hay tạo theo từng nghiệp vụ dựa trên tiêu chí nào?
Bạn thiết kế lớp bao ChatClient để các phần khác không phụ thuộc trực tiếp vào cú pháp gọi mô hình như thế nào?
Bạn mô tả quy trình xây dựng một lời gọi ChatClient có system instruction và user input như thế nào?
Bạn phân biệt kết quả văn bản đơn giản với response đầy đủ khi gọi ChatClient ra sao?
Bạn tổ chức xử lý lỗi của ChatClient để không phân tán khắp các controller như thế nào?
Bạn xác định phần cấu hình ChatClient nào nên đặt mặc định và phần nào thay đổi theo request như thế nào?
Bạn phân biệt tùy chọn provider ở cấp model với tùy chọn ghi đè cho một yêu cầu cụ thể ra sao?
Bạn đánh giá việc dùng chung một đối tượng client giữa các request đồng thời như thế nào?
Bạn quản lý phụ thuộc ChatModel để viết unit test cho service mà không gọi provider thật ra sao?
Bạn phân biệt Prompt, Message và các role trong một cuộc hội thoại AI như thế nào?
Bạn giải thích mục đích của system message so với user message trong một yêu cầu AI như thế nào?
Bạn thiết kế system instruction để mô hình tuân thủ phạm vi nhiệm vụ nhưng không lẫn dữ liệu người dùng như thế nào?
Bạn phân biệt chỉ dẫn đáng tin cậy của ứng dụng với nội dung chưa được tin cậy do người dùng gửi lên ra sao?
Bạn mô tả cách các message được sắp xếp trong Prompt để duy trì ngữ cảnh cuộc hội thoại như thế nào?
Bạn đánh giá rủi ro khi nhiều system instruction gây xung đột hoặc mơ hồ trong prompt như thế nào?
Bạn sử dụng prompt template để tách cấu trúc chỉ dẫn khỏi dữ liệu thay đổi như thế nào?
Bạn thiết kế các biến trong prompt template để hạn chế nội dung không mong muốn ra sao?
Bạn phân biệt chèn biến template với thực thi biểu thức của ứng dụng như thế nào?
Bạn xác định đầu vào nào cần kiểm tra trước khi đưa vào prompt template ra sao?
Bạn đặt ràng buộc về ngôn ngữ, định dạng và phạm vi câu trả lời trong prompt như thế nào?
Bạn thiết kế prompt để tóm tắt tài liệu nhưng nêu rõ cách xử lý khi thiếu thông tin ra sao?
Bạn giải thích sự khác nhau giữa zero-shot và few-shot prompting khi xây dựng template như thế nào?
Bạn chọn ví dụ few-shot để tránh thiên lệch về nhãn hoặc trường hợp hiếm như thế nào?
Bạn xác định khi nào nên dùng nhiều prompt chuyên biệt thay vì một prompt lớn cho mọi nhiệm vụ ra sao?
Bạn quản lý phiên bản prompt template cùng mã nguồn và quy trình phát hành như thế nào?
Bạn thiết kế cơ chế đánh giá tác động của thay đổi nhỏ trong prompt tới kết quả như thế nào?
Bạn phân biệt nhiệm vụ trích xuất thông tin với nhiệm vụ sinh nội dung khi thiết kế prompt ra sao?
Bạn yêu cầu mô hình trả về nguồn thông tin thế nào mà không giả định nguồn được nêu luôn tồn tại?
Bạn nhận diện dấu hiệu prompt quá dài hoặc chứa thông tin không liên quan đến nhiệm vụ như thế nào?
Bạn cân đối giữa việc cung cấp đủ ngữ cảnh và giới hạn context window của model ra sao?
Bạn mô tả cách token hóa ảnh hưởng đến độ dài đầu vào và chi phí lời gọi như thế nào?
Bạn xử lý cuộc hội thoại nhiều lượt khi lịch sử vượt giới hạn context window như thế nào?
Bạn quyết định khi nào nên tóm tắt lịch sử hội thoại và khi nào cần giữ nguyên thông tin quan trọng ra sao?
Bạn đánh giá nguy cơ mất ngữ cảnh khi dùng bản tóm tắt lịch sử làm đầu vào mới như thế nào?
Bạn xác định vai trò của các message trước đó đối với chất lượng câu trả lời hiện tại như thế nào?
Bạn thiết kế lưu lịch sử chat với thời hạn phù hợp và bảo vệ dữ liệu cá nhân như thế nào?
Bạn phân biệt thông tin phiên hội thoại với dữ liệu nghiệp vụ bền vững trong ứng dụng AI ra sao?
Bạn thiết kế cách cô lập ngữ cảnh giữa hai người dùng hoặc hai tenant khi sử dụng ChatClient như thế nào?
Bạn ngăn ngữ cảnh của request trước lọt vào request mới không liên quan ra sao?
Bạn phân biệt model identifier và provider khi cấu hình một tính năng AI như thế nào?
Bạn so sánh provider dựa trên chất lượng, độ trễ, khả năng hỗ trợ tính năng và tuân thủ dữ liệu ra sao?
Bạn kiểm tra một model có hỗ trợ loại message và định dạng dữ liệu mà ứng dụng cần như thế nào?
Bạn phân tích ảnh hưởng của temperature đến độ biến thiên đầu ra và khả năng tái lập kết quả như thế nào?
Bạn phân biệt temperature với top-p khi provider hỗ trợ các tham số lấy mẫu này ra sao?
Bạn lựa chọn giới hạn số token đầu ra để cân bằng chất lượng câu trả lời và thời gian phản hồi như thế nào?
Bạn kiểm soát tác động của cấu hình model mặc định thay đổi giữa các môi trường ra sao?
Bạn phân biệt lỗi do prompt với lỗi do năng lực hoặc cấu hình model bằng những thử nghiệm nào?
Bạn đánh giá khi nào cần model mạnh hơn thay vì chỉ điều chỉnh prompt hoặc hậu xử lý ra sao?
Bạn thiết kế cách chọn model theo độ nhạy dữ liệu và mức quan trọng của nhiệm vụ như thế nào?
Bạn xây dựng fallback khi provider chính lỗi nhưng model thay thế có năng lực không tương đương ra sao?
Bạn kiểm tra thay đổi chất lượng đầu ra khi chuyển giữa các provider như thế nào?
Bạn đánh giá rủi ro phụ thuộc một provider vào hợp đồng dữ liệu hoặc cách diễn giải role đặc thù ra sao?
Bạn thiết kế retry khác nhau cho lỗi rate limit và lỗi xác thực của provider như thế nào?
Bạn phân biệt lời gọi đồng bộ trả kết quả hoàn chỉnh với streaming từng phần nội dung như thế nào?
Bạn xác định nhu cầu sản phẩm nào thực sự cần streaming từ mô hình ra sao?
Bạn mô tả cách ứng dụng Spring AI nhận luồng kết quả và chuyển tiếp tới client qua một transport phù hợp như thế nào?
Bạn giải thích vì sao các chunk streaming không nhất thiết tương ứng với một câu hoặc token nguyên vẹn như thế nào?
Bạn ghép các chunk streaming để tạo câu trả lời hoàn chỉnh mà không làm sai thứ tự như thế nào?
Bạn thiết kế giao diện hiển thị nội dung AI dần dần nhưng vẫn xử lý lỗi giữa chừng ra sao?
Bạn phân biệt kết thúc luồng bình thường với lỗi ngắt kết nối khi stream đang được gửi như thế nào?
Bạn giải phóng tài nguyên khi người dùng hủy request streaming trước khi mô hình trả hết kết quả ra sao?
Bạn phân tích cancellation từ client ảnh hưởng tới subscription và lời gọi provider phía sau như thế nào?
Bạn quyết định có nên retry một stream đã gửi một phần nội dung tới người dùng theo tiêu chí nào?
Bạn xử lý trường hợp client reconnect và muốn lấy lại câu trả lời bị ngắt như thế nào?
Bạn giới hạn số kết nối streaming đồng thời để bảo vệ ứng dụng và quota provider ra sao?
Bạn đánh giá tác động của backpressure khi model sinh nhanh hơn client có thể nhận như thế nào?
Bạn phân biệt timeout toàn bộ lời gọi với thời gian chờ giữa các chunk streaming như thế nào?
Bạn ghi nhận token usage hoặc metadata khi streaming và provider trả chúng không đồng đều ra sao?
Bạn kiểm tra kết quả streaming tương đương về nội dung với cách gọi thông thường bằng phương pháp nào?
Bạn phân biệt structured output với việc yêu cầu mô hình trả văn bản tự do như thế nào?
Bạn xác định khi nào ứng dụng nên buộc phản hồi về DTO hoặc schema cụ thể ra sao?
Bạn giải thích vai trò của cơ chế chuyển đổi output thành kiểu Java trong Spring AI như thế nào?
Bạn thiết kế schema đầu ra biểu diễn trường bắt buộc, trường tùy chọn và enum ra sao?
Bạn phân biệt JSON hợp lệ cú pháp với dữ liệu hợp lệ theo ràng buộc nghiệp vụ như thế nào?
Bạn thiết kế validation sau khi deserialize đầu ra AI bằng các quy tắc nào?
Bạn xử lý trường hợp model trả JSON kèm lời giải thích ngoài cấu trúc đã yêu cầu như thế nào?
Bạn ứng phó với phản hồi thiếu thuộc tính bắt buộc hoặc sai kiểu dữ liệu ra sao?
Bạn phân tích rủi ro khi tin tưởng trực tiếp dữ liệu do mô hình trích xuất mà không kiểm tra nguồn như thế nào?
Bạn lựa chọn giữa structured output do provider hỗ trợ và việc hướng dẫn bằng prompt theo điều kiện nào?
Bạn kiểm tra provider hỗ trợ JSON schema hoặc output format ràng buộc ở mức nào như thế nào?
Bạn thiết kế retry hoặc yêu cầu sửa cấu trúc khi phản hồi không vượt qua validation ra sao?
Bạn cân nhắc khi nào cần xử lý thủ công thay vì tiếp tục yêu cầu mô hình sửa dữ liệu như thế nào?
Bạn thiết kế kết quả trích xuất để phân biệt trường không tìm thấy với trường có giá trị null ra sao?
Bạn đánh giá độ tin cậy của trường do mô hình suy luận so với trường tìm thấy trực tiếp như thế nào?
Bạn phân biệt confidence tự báo cáo của model với độ chính xác được kiểm chứng bằng dữ liệu như thế nào?
Bạn xử lý nội dung có dấu ngoặc, ký tự xuống dòng hoặc dấu phân cách làm hỏng parser như thế nào?
Bạn thiết kế versioning của schema đầu ra để hỗ trợ frontend cũ khi yêu cầu AI thay đổi ra sao?
Bạn kiểm thử structured output với trường hợp rỗng, quá dài và ký tự Unicode như thế nào?
Bạn thiết kế API trả lỗi validation thay vì DTO chứa dữ liệu không đáng tin cậy như thế nào?
Bạn giải thích điều kiện nào khiến model nhận được cả văn bản và hình ảnh trong một yêu cầu như thế nào?
Bạn tổ chức prompt đa phương thức chứa chỉ dẫn và dữ liệu hình ảnh như thế nào?
Bạn phân biệt khả năng multimodal của provider với khả năng biểu diễn dữ liệu của Spring AI ra sao?
Bạn xác định giới hạn loại tệp và kích thước dữ liệu đầu vào trước khi gửi tới model như thế nào?
Bạn kiểm tra MIME type và nội dung thực tế của dữ liệu đa phương thức để tránh tệp giả mạo ra sao?
Bạn đánh giá tác động độ phân giải ảnh tới chất lượng phân tích và chi phí token như thế nào?
Bạn cân nhắc truyền ảnh dưới dạng tài nguyên nội bộ hoặc tham chiếu mà model có thể đọc ra sao?
Bạn xử lý hình ảnh có văn bản nhạy cảm trước khi gửi tới mô hình đa phương thức như thế nào?
Bạn thiết kế phản hồi khi provider không hỗ trợ loại media người dùng gửi lên như thế nào?
Bạn phân biệt lỗi tải dữ liệu đầu vào với lỗi model không diễn giải được nội dung như thế nào?
Bạn kiểm thử ảnh mờ, ảnh không liên quan và ảnh thiếu thông tin như thế nào?
Bạn đánh giá câu trả lời đa phương thức mà không giả định model nhận dạng mọi chi tiết chính xác ra sao?
Bạn thiết kế bước người dùng xác nhận khi model trích xuất thông tin quan trọng từ hình ảnh như thế nào?
Bạn so sánh luồng audio hoặc media khác với luồng text theo khả năng hỗ trợ của provider như thế nào?
Bạn tổ chức fallback cho client khi provider không hỗ trợ một modality cụ thể ra sao?
Bạn xác định cách chống prompt injection từ văn bản nằm trong ảnh hoặc tài liệu tải lên như thế nào?
Bạn phân biệt dữ liệu người dùng cung cấp với chỉ dẫn hệ thống khi nội dung đa phương thức chứa lệnh như thế nào?
Bạn hạn chế một phản hồi AI gây tác dụng phụ trực tiếp trong hệ thống bằng những ranh giới nào?
Bạn xác định hành động nghiệp vụ nào cần xác nhận người dùng trước khi áp dụng kết quả AI như thế nào?
Bạn thiết kế kiểm soát truy cập dựa trên danh tính thật thay vì lời model diễn giải như thế nào?
Bạn phân quyền truy cập dữ liệu gửi tới model theo nguyên tắc quyền tối thiểu ra sao?
Bạn phân biệt xác thực với provider và xác thực người dùng cuối trong ứng dụng Spring Boot như thế nào?
Bạn quản lý API key, token và endpoint theo môi trường mà không lộ vào mã nguồn ra sao?
Bạn xác định khi nào phải ẩn hoặc làm sạch dữ liệu cá nhân trước khi gửi tới nhà cung cấp AI như thế nào?
Bạn thiết kế ghi nhận sự đồng ý và mục đích xử lý dữ liệu khi sử dụng mô hình bên ngoài ra sao?
Bạn đánh giá rủi ro lưu log toàn bộ prompt và response khi chúng có dữ liệu nhạy cảm như thế nào?
Bạn lựa chọn metadata được ghi log để điều tra sự cố mà không làm lộ nội dung hội thoại ra sao?
Bạn thiết kế chính sách lưu trữ và xóa lịch sử yêu cầu AI theo yêu cầu bảo mật như thế nào?
Bạn giải thích vì sao system prompt không phải ranh giới bảo mật tuyệt đối như thế nào?
Bạn xây dựng kiểm thử prompt injection từ đầu vào người dùng và dữ liệu không đáng tin cậy như thế nào?
Bạn xử lý yêu cầu AI cố vượt quyền hoặc tiết lộ cấu hình bí mật như thế nào?
Bạn kiểm soát kết quả AI trước khi hiển thị dưới dạng HTML để tránh lỗi injection hoặc XSS ra sao?
Bạn đánh giá tác động gửi cùng dữ liệu tới nhiều provider đối với quyền riêng tư như thế nào?
Bạn kiểm soát chi phí cho mỗi người dùng, mỗi tính năng và toàn ứng dụng như thế nào?
Bạn giám sát số token đầu vào, đầu ra và chi phí ước tính theo từng loại lời gọi như thế nào?
Bạn phân tích độ dài prompt, model được chọn và thời gian phản hồi ảnh hưởng lẫn nhau ra sao?
Bạn thiết kế giới hạn input để một yêu cầu không chiếm quá nhiều quota như thế nào?
Bạn phân biệt rate limiting tại ứng dụng với quota do provider áp dụng như thế nào?
Bạn triển khai backoff và jitter cho lỗi rate limit mà không tạo đợt retry đồng loạt ra sao?
Bạn xác định số lần retry tối đa và timeout của tác vụ AI dựa trên SLA như thế nào?
Bạn giải thích vì sao retry có thể tăng chi phí và tạo hai phản hồi khác nhau cho cùng yêu cầu như thế nào?
Bạn phân biệt lỗi mạng, xác thực, cấu hình model và lỗi giới hạn nội dung trong xử lý ngoại lệ như thế nào?
Bạn thiết kế thông báo lỗi khi model từ chối yêu cầu hoặc không thể tạo nội dung ra sao?
Bạn xác định khi nào trả kết quả dự phòng thay vì yêu cầu AI chạy lại như thế nào?
Bạn sử dụng circuit breaker để bảo vệ ứng dụng khi provider liên tục lỗi ra sao?
Bạn thiết kế bulkhead hoặc giới hạn đồng thời để tính năng AI không làm nghẽn toàn hệ thống như thế nào?
Bạn xử lý fallback giữa các model có giới hạn context và chất lượng khác nhau ra sao?
Bạn ngăn cache câu trả lời chứa dữ liệu riêng của người dùng khác như thế nào?
Bạn đánh giá khả năng cache kết quả AI khi cùng prompt vẫn có thể tạo đầu ra khác nhau ra sao?
Bạn thiết kế khóa cache xét tới provider, model, prompt version và phạm vi người dùng như thế nào?
Bạn đo chất lượng tính năng AI khi đầu ra không tất định như thế nào?
Bạn phân biệt unit test code tích hợp với evaluation chất lượng nội dung do mô hình sinh như thế nào?
Bạn viết test cho quá trình tạo Prompt mà không cần gọi provider thật như thế nào?
Bạn thiết kế fake hoặc stub ChatModel để kiểm tra response, lỗi và fallback ra sao?
Bạn lựa chọn assertion phù hợp với đầu ra AI không cố định từng ký tự như thế nào?
Bạn xác định tiêu chí kiểm thử structured output dựa trên schema và quy tắc nghiệp vụ ra sao?
Bạn tạo bộ dữ liệu đánh giá đại diện cho nhiều người dùng và các trường hợp biên như thế nào?
Bạn thiết kế bộ mẫu đầu vào có đáp án tham chiếu cho nhiệm vụ trích xuất như thế nào?
Bạn lựa chọn chỉ số đánh giá mức đúng sai, đủ thông tin và bám nguồn theo từng nhiệm vụ ra sao?
Bạn phân biệt hallucination với phản hồi thiếu thông tin hoặc bị cắt bởi giới hạn token như thế nào?
Bạn đánh giá sự nhất quán của phản hồi qua nhiều lần chạy cùng prompt như thế nào?
Bạn thiết kế A/B test khi thay đổi prompt hoặc model trong điều kiện đầu ra có biến động như thế nào?
Bạn xác định ngưỡng chấp nhận chất lượng trước khi triển khai phiên bản prompt mới ra sao?
Bạn phát hiện hồi quy chất lượng khi provider thay đổi model phía sau cùng một tên định danh như thế nào?
Bạn cân nhắc khi nào cần người đánh giá thủ công thay vì chỉ dùng model khác chấm điểm như thế nào?
Bạn nhận diện thiên lệch hoặc nội dung không phù hợp bằng bộ kiểm thử nào trước khi triển khai AI ra sao?
Bạn thiết kế kiểm thử bảo mật cho đầu vào cố tiết lộ secret hoặc yêu cầu vượt quyền như thế nào?
Bạn mô phỏng lỗi 429, lỗi 5xx và timeout từ provider để xác minh retry như thế nào?
Bạn kiểm thử streaming bị ngắt giữa chừng và thao tác hủy của người dùng như thế nào?
Bạn kiểm thử parser structured output với tiền tố thừa, dữ liệu thiếu hoặc enum lạ ra sao?
Bạn phân biệt kết quả kiểm thử mô phỏng provider với kiểm thử tích hợp thật như thế nào?
Bạn thiết kế contract test để phát hiện thay đổi response metadata hoặc tùy chọn provider như thế nào?
Bạn lập kế hoạch đánh giá định kỳ mà không phụ thuộc một seed duy nhất như thế nào?
Bạn lựa chọn các chỉ số observability giám sát latency, token usage, lỗi và tỷ lệ thành công của lời gọi AI ra sao?
Bạn thiết kế trace qua controller, service Spring AI và provider để tìm điểm nghẽn như thế nào?
Bạn phân biệt độ trễ trước token đầu tiên với độ trễ hoàn tất streaming như thế nào?
Bạn xác định khi nào thu thập metadata response nhưng không lưu toàn bộ nội dung ra sao?
Bạn thiết kế dashboard theo provider và model để phát hiện biến động chất lượng hoặc chi phí như thế nào?
Bạn cảnh báo khi tỷ lệ lỗi AI tăng nhưng HTTP endpoint vẫn trả thành công như thế nào?
Bạn ghi nhận lý do fallback hoặc retry trong telemetry để dễ điều tra sự cố ra sao?
Bạn gắn correlation ID vào xử lý AI mà không đưa thông tin định danh nhạy cảm vào prompt như thế nào?
Bạn điều tra phản hồi sai mà không lưu dữ liệu người dùng vượt thời hạn cho phép như thế nào?
Bạn triển khai versioning cho prompt, cấu hình model và schema để truy vết kết quả production như thế nào?
Bạn xây dựng rollout hoặc rollback khi thay đổi prompt làm giảm chất lượng đầu ra như thế nào?
Bạn phân tích việc provider ngừng hỗ trợ model ảnh hưởng hợp đồng API đã công bố ra sao?
Bạn thiết kế feature flag để tắt riêng tính năng AI khi có sự cố như thế nào?
Bạn xác định khi nào nên dùng hàng đợi xử lý nền thay vì giữ HTTP request chờ mô hình như thế nào?
Bạn báo tiến độ cho người dùng khi tác vụ AI dài không thể streaming trực tiếp như thế nào?
Bạn lựa chọn model cục bộ hay model qua mạng dựa trên dữ liệu, chi phí và độ trễ như thế nào?
Bạn xác định vai trò của việc gọi công cụ trong ứng dụng Spring AI và quyền hạn cần kiểm soát ra sao?
Bạn phân biệt việc model đề xuất lời gọi công cụ với việc ứng dụng cho phép thực thi công cụ như thế nào?
Bạn kiểm tra tham số do model đề xuất trước khi gọi hàm nghiệp vụ có tác dụng phụ như thế nào?
Bạn giới hạn số lần gọi công cụ trong hội thoại để tránh vòng lặp và phát sinh chi phí ra sao?
Bạn phân biệt lỗi khi gọi công cụ với lỗi sinh nội dung của model bằng những tín hiệu nào?
Bạn cân nhắc khi nào đưa dữ liệu từ API nội bộ vào prompt và khi nào chỉ trả kết quả từ API ra sao?
Bạn đánh giá prompt injection khi model đọc kết quả từ công cụ hoặc nguồn ngoài như thế nào?
Nếu ChatClient trả nội dung rỗng dù HTTP thành công, bạn sẽ kiểm tra những tín hiệu và metadata nào?
Nếu ChatModel trả hai câu khác nhau cho cùng Prompt, bạn sẽ giải thích và kiểm thử hành vi như thế nào?
Nếu prompt template nhận ký tự đặc biệt làm chỉ dẫn bị hiểu sai, bạn sẽ thiết kế lại template ra sao?
Nếu JSON phản hồi thiếu trường DTO bắt buộc, bạn sẽ thiết kế validation và retry như thế nào?
Nếu streaming ngừng giữa câu trả lời, bạn sẽ thông báo và phục hồi trải nghiệm người dùng ra sao?
Nếu provider chính báo rate limit giờ cao điểm, bạn sẽ điều tiết tải, retry và fallback như thế nào?
Nếu ảnh tải lên chứa chỉ dẫn trái với system prompt, bạn sẽ kiểm soát độ tin cậy của dữ liệu đó ra sao?
Nếu dữ liệu nhạy cảm bị đưa vào prompt do nhầm mapping, bạn sẽ kiểm soát nội dung trước request như thế nào?
Nếu model cập nhật làm giảm chất lượng phân loại, bạn sẽ đánh giá hồi quy và rollback như thế nào?
Nếu ứng dụng Spring Boot cần structured output, streaming và đổi provider được, bạn sẽ thiết kế và kiểm thử ra sao?
