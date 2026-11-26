Một ngân hàng triển khai trợ lý Spring AI trả lời câu hỏi về biểu phí; bộ dữ liệu đánh giá chỉ chứa câu hỏi ngắn, trong khi khách hàng thực tế thường đặt nhiều điều kiện và ngoại lệ trong cùng một lượt.
Đội bảo hiểm sử dụng tập câu hỏi có đáp án tham chiếu từ năm trước để đánh giá chatbot RAG; sau đợt thay đổi điều khoản hợp đồng, nhiều câu trả lời đúng theo tài liệu mới bị chấm là sai.
Hai chuyên viên hỗ trợ khách hàng gán nhãn relevance khác nhau cho cùng câu trả lời về hạn mức giao dịch; điểm đánh giá giữa các lần chạy thay đổi đáng kể dù prompt và model không đổi.
Một nền tảng tuyển dụng xây dựng bộ benchmark từ ví dụ đã dùng để tinh chỉnh prompt; kết quả kiểm thử nội bộ rất cao nhưng chất lượng giảm mạnh khi nhận hồ sơ có cấu trúc khác.
Dịch vụ tư vấn học tập diễn đạt cùng một yêu cầu bằng nhiều cách tiếng Việt; bộ chấm điểm so khớp chuỗi văn bản đánh giá thấp những câu trả lời đúng ý nhưng khác câu chữ tham chiếu.
Một ứng dụng quản lý bệnh viện đánh giá bot bằng các câu hỏi đều có đáp án trong kho tài liệu; khi người dùng hỏi quy trình chưa được công bố, bot vẫn đưa ra câu trả lời chắc chắn không có căn cứ.
Nhóm vận hành thiết lập tập kiểm thử gồm cả câu hỏi có đáp án và câu hỏi không đủ dữ kiện; sau khi cập nhật prompt, tỷ lệ từ chối trả lời tăng nhưng báo cáo chỉ hiển thị độ chính xác của các câu có đáp án.
Doanh nghiệp logistics cung cấp câu hỏi đánh giá trích từ cuộc trò chuyện khách thật; tập dữ liệu vô tình chứa mã vận đơn, số điện thoại và địa chỉ mà nhóm đánh giá bên ngoài không cần biết.
Trợ lý pháp chế hỗ trợ câu hỏi bằng tiếng Việt và tiếng Anh; tập benchmark chủ yếu viết tiếng Anh nên một thay đổi model làm chất lượng tiếng Việt giảm nhưng điểm trung bình vẫn tăng.
Một chatbot nội bộ trả lời đúng các câu hỏi phổ biến về ngày nghỉ nhưng thất bại với thuật ngữ nghiệp vụ đặc thù; báo cáo tổng thể không tách kết quả theo nhóm câu hỏi để nhận ra chỗ yếu.
Nhóm sản phẩm trộn câu hỏi dễ và câu hỏi nhiều bước vào cùng một điểm trung bình; phiên bản prompt mới cải thiện các câu đơn giản nhưng suy giảm rõ ở các tình huống đối chiếu nhiều nguồn.
Ứng dụng thương mại điện tử tạo tập kiểm thử có hàng nghìn biến thể hỏi cùng một chính sách trả hàng; điểm aggregate bị chi phối bởi một chủ đề trong khi các chủ đề ít mẫu không được phản ánh đủ.
Một hệ thống trợ giúp lập trình sử dụng model khác để chấm tính đúng đắn của lời giải; cùng model chấm điểm cao cho câu trả lời dài và tự tin dù chứa nhận định kỹ thuật sai.
Đội kỹ thuật chạy đánh giá định kỳ với model có đầu ra không hoàn toàn xác định; cùng một bản prompt cho điểm relevance khác nhau giữa các lượt và không ai phân biệt được dao động tự nhiên với hồi quy.
Một nhóm thay đổi phiên bản model trong Spring AI nhưng không lưu lại phiên bản bộ câu hỏi và tài liệu tham chiếu; khi điểm fact checking giảm, không rõ nguyên nhân đến từ model hay dữ liệu đánh giá.
Ứng dụng tuyển sinh so sánh hai phiên bản prompt bằng bộ câu hỏi offline; bản mới được chấm cao nhưng khách hàng dùng production vẫn phàn nàn rằng câu trả lời quá dài và khó tìm thông tin chính.
Nhóm triển khai canary cho model mới trên một phần lưu lượng người dùng; các yêu cầu khó lại tập trung vào một nhóm khách hàng khiến tỷ lệ phản hồi tốt giữa hai phiên bản không thể so sánh trực tiếp.
Ứng dụng chăm sóc khách hàng có luồng chuyển tiếp cho nhân viên khi bot không chắc chắn; kết quả đánh giá tự động tính chuyển tiếp là lỗi dù nhân viên sau đó xử lý đúng yêu cầu của khách.
Trợ lý chính sách nhân sự trả lời đúng một câu về chế độ làm thêm giờ nhưng viện dẫn đoạn tài liệu không liên quan; chỉ số relevance của câu trả lời cao trong khi đánh giá căn cứ nguồn thấp.
Một hệ thống RAG trả lời câu hỏi về quy trình mua sắm dựa trên đoạn trích phù hợp; bản sinh câu trả lời bổ sung điều kiện phê duyệt không xuất hiện trong bất kỳ tài liệu được truy xuất nào.
Dịch vụ tra cứu quy định giao thông tạo câu trả lời kèm trích dẫn chính xác tên văn bản nhưng số điều bị sai; bộ kiểm thử chỉ kiểm tồn tại citation nên không phát hiện sai sót fact checking.
Trợ lý pháp lý nhận hai văn bản chính sách mâu thuẫn do một văn bản đã bị thay thế; RAG tổng hợp hai nội dung thành một quy định mới không tồn tại trong tài liệu hiện hành.
Một hệ thống trợ lý kỹ thuật lấy đủ dữ kiện để trả lời trong ba đoạn tài liệu nhưng model chỉ đọc đoạn đầu; câu trả lời bỏ sót cảnh báo an toàn dù retrieval đã đưa đủ nguồn vào context.
Nhóm kiểm thử RAG nhận thấy câu trả lời đúng dù không có đoạn truy xuất nào chứa bằng chứng; quá trình kiểm tra chỉ nhìn kết quả cuối nên không phân biệt tri thức model với tri thức doanh nghiệp.
Bot hỗ trợ sản phẩm dùng dữ liệu catalog có ngày hiệu lực; sau khi tài liệu đổi giá, chỉ số fact checking không xét mốc thời gian và coi báo giá cũ là đúng với một số câu hỏi.
Hệ thống nhân sự tìm tài liệu qua vector store nhưng kết quả top-k thường chứa chính sách ở đơn vị khác; câu trả lời có từ ngữ tương tự song không áp dụng cho phòng ban của người hỏi.
Ứng dụng hỏi đáp tài liệu nhận truy vấn có nhiều từ viết tắt nội bộ; một thay đổi embedding khiến recall giảm cho các từ viết tắt dù chỉ số similarity trung bình của kết quả vẫn cao.
Dịch vụ hỗ trợ tài chính thay đổi kích thước chunk và mức overlap khi nạp tài liệu; đoạn trích chứa điều kiện áp dụng bị tách khỏi bảng phí khiến kết quả retrieval vẫn trông liên quan nhưng thiếu căn cứ quan trọng.
Nhóm triển khai query rewriting trước bước tìm kiếm; câu hỏi về một sản phẩm đời cũ bị viết lại thành sản phẩm mới, làm tài liệu đúng không còn xuất hiện trong nhóm kết quả đầu.
Ứng dụng RAG tăng top-k từ ba lên mười để giảm bỏ sót thông tin; câu trả lời bắt đầu trộn dữ kiện giữa nhiều chính sách, còn độ trễ và lượng token đầu vào tăng đáng kể.
Trợ lý quản lý dự án dùng bộ lọc metadata theo tenant trong truy vấn vector; một phiên bản pipeline bỏ mất điều kiện lọc khiến kết quả retrieval liên quan về nội dung nhưng thuộc doanh nghiệp khác.
Nhóm thử nghiệm kết hợp tìm kiếm từ khóa và vector cho tên mã thiết bị; một chiến lược xếp hạng mới nâng điểm relevance chung nhưng làm các mã thiết bị chính xác rơi xuống cuối danh sách.
Ứng dụng tri thức doanh nghiệp thêm bước reranking sau retrieval; tập đánh giá retrieval chưa tách chỉ số trước và sau rerank nên nhóm không biết bước mới thực sự cải thiện hay làm mất tài liệu hữu ích.
Bot tra cứu hợp đồng tìm thấy đoạn văn chứa số liệu nhưng bỏ mất đơn vị và tiêu đề bảng; model kết luận sai giá trị thanh toán dù kết quả retrieval có mức tương đồng cao.
Doanh nghiệp cập nhật model embedding để cải thiện tiếng Việt nhưng vẫn giữ nhiều vector tạo bởi model cũ; kết quả tìm kiếm thay đổi khó dự đoán và chất lượng RAG suy giảm theo từng nguồn tài liệu.
Một vector store được làm mới sau khi quy trình nội bộ thay đổi; bản index cập nhật chậm nhiều giờ khiến chatbot tiếp tục trích dẫn các bước phê duyệt đã bỏ.
Ứng dụng trợ lý chính sách cho phép tìm đồng thời tài liệu cũ và mới; kết quả đầu tiên có điểm similarity cao nhưng là bản nháp, trong khi bản chính thức nằm ngoài giới hạn top-k.
Nhóm đo retrieval precision nhưng không ghi nhận những tài liệu đúng bị bỏ khỏi top-k; một phiên bản mới giữ ít kết quả nhiễu hơn song không còn đủ bằng chứng để trả lời câu hỏi nhiều bước.
Trợ lý bảo hành cần tổng hợp thời hạn theo dòng sản phẩm và ngày mua từ hai nguồn; từng kết quả retrieval riêng lẻ có relevance cao nhưng câu trả lời cuối vẫn ghép nhầm chính sách.
Một dịch vụ RAG phải xử lý truy vấn không có tài liệu phù hợp; bộ kiểm thử hiện không có câu hỏi âm tính nên model có xu hướng tự đưa ra hướng dẫn thay vì thể hiện thiếu thông tin.
Ứng dụng hỏi đáp có kho tài liệu rất lớn và giới hạn context window; bước cắt ngắn context loại mất đoạn chứa ngoại lệ hợp đồng, nhưng metric retrieval vẫn báo đã tìm thấy tài liệu cần thiết.
Nhóm vận hành phát hiện câu trả lời sai tăng đột ngột sau khi đổi tokenizer và cách tính token; các câu hỏi dài bị cắt context ở điểm khác trước nhưng hệ thống không ghi nhận độ dài context thực tế.
Một chatbot nội bộ sử dụng lời nhắc kèm đoạn tài liệu người dùng tải lên; tài liệu có câu chỉ dẫn giả mạo vai trò hệ thống khiến model bỏ qua yêu cầu gốc, trong khi bài đánh giá chỉ kiểm relevance của đoạn trích.
Trợ lý bán hàng có công cụ truy vấn tồn kho; câu trả lời đưa ra số lượng sản phẩm hợp lý nhưng không hề gọi công cụ ở lượt yêu cầu có dữ liệu tồn kho thay đổi liên tục.
Một ứng dụng Spring AI cho phép model gọi công cụ tra cứu đơn hàng; sau khi đổi prompt, model chọn đúng tên công cụ nhưng truyền sai kiểu dữ liệu của mã đơn, khiến lỗi phát sinh ở tầng thực thi.
Dịch vụ tài chính sử dụng công cụ đổi tiền tệ cho báo giá; model gọi công cụ nhiều lần với cùng tham số dù kết quả đầu đã đủ, làm chi phí và thời gian phản hồi tăng bất thường.
Một chatbot đặt lịch có công cụ tạo lịch hẹn gây side effect; bộ kiểm thử tích hợp gọi công cụ thật và vô tình tạo nhiều cuộc hẹn khi chạy lại cùng test case.
Trợ lý đặt hàng được phép đọc giỏ hàng nhưng không được tự xác nhận thanh toán; khi yêu cầu từ khách nhập nhằng, model gọi nhầm công cụ có quyền thay đổi trạng thái đơn hàng.
Một quy trình dùng hai công cụ lấy thông tin khách hàng và chính sách giá; kết quả công cụ thứ hai đến trước công cụ thứ nhất, khiến model ghép giá của một khách vào yêu cầu khách khác.
Ứng dụng hỗ trợ khách hàng gọi API vận chuyển qua Spring AI tool calling; nhà cung cấp trả lỗi tạm thời và model tự suy đoán thời gian giao hàng mà không ghi nhận lỗi công cụ.
Nhóm kiểm thử kiểm tra câu trả lời đúng khi gọi công cụ thành công nhưng bỏ qua tình huống công cụ timeout; luồng agent tiếp tục phát lời khẳng định dù không có dữ liệu trả về.
Một trợ lý vận hành có nhiều công cụ gần giống nhau để xem và chỉnh sửa trạng thái máy chủ; bài kiểm thử chỉ đánh giá lời giải thích cuối cùng chứ không đối chiếu chuỗi công cụ đã được chọn.
Dịch vụ chatbot tư vấn học phí nhận câu hỏi nhiều lượt; khi lịch sử hội thoại bị rút gọn, model gọi lại công cụ của một học viên trước đó làm câu trả lời chứa dữ liệu sai người.
Nhóm triển khai thay thứ tự mô tả các công cụ mà không đổi API; điểm chất lượng câu trả lời không giảm rõ nhưng số lần gọi công cụ sai hoặc không cần thiết tăng.
Ứng dụng RAG kết hợp truy xuất tài liệu với gọi công cụ tính giá; nhóm đánh giá chỉ chấm kết quả cuối, không nhận biết số liệu tính đúng nhưng được áp dụng trên chính sách đã hết hiệu lực.
Trong ứng dụng Spring AI, một request có các bước embedding, vector search, rerank và chat generation; log chỉ ghi thời gian tổng nên đội vận hành không xác định được bước nào làm p95 latency tăng.
Trợ lý hỏi đáp dùng streaming phản hồi từng phần; thời gian hoàn tất toàn bộ phản hồi vẫn ổn định nhưng người dùng phản ánh phải chờ quá lâu trước token đầu tiên.
Một dashboard đo thời gian trung bình cho lời gọi model; sau khi tăng số người dùng đồng thời, p99 latency cao gấp nhiều lần nhưng giá trị trung bình hầu như không đổi.
Đội triển khai ghi metric số token đầu vào và đầu ra cho mỗi request; dashboard gộp chúng thành một tổng và không phát hiện prompt mới đang tiêu thụ context dài hơn rõ rệt.
Hệ thống hỏi đáp báo chi phí thấp hơn hóa đơn của nhà cung cấp model; phần tính toán chỉ xét lần chat cuối và bỏ qua token của embedding, reranking cùng các lượt gọi công cụ dẫn đến model bổ sung.
Một ứng dụng Spring AI chuyển từ model giá thấp sang model có biểu phí khác; báo cáo cost per request vẫn dùng mức giá cũ nên lựa chọn triển khai dựa trên dự toán sai.
Nhóm sản phẩm so sánh chi phí của hai prompt nhưng lưu lượng có độ dài câu hỏi khác nhau; phiên bản nhiều câu dài bị đánh giá đắt hơn dù chi phí trên một tác vụ tương đương chưa được chuẩn hóa.
Một chatbot có cơ chế retry khi provider trả lỗi 429; metric request thành công không ghi số lần thử, khiến chi phí token tăng và latency biến động mà báo cáo không chỉ ra được nguyên nhân.
Ứng dụng phục vụ doanh nghiệp ghi nhận lỗi timeout ở bước embedding nhưng trace kết thúc như một lỗi chat model; nhóm vận hành tối ưu nhầm thành phần và không cải thiện được tỷ lệ thành công.
Một request Spring AI gọi RAG rồi gọi hai công cụ bất đồng bộ; trace không giữ cùng correlation ID qua các luồng xử lý nên không thể nối từng span với câu trả lời của người dùng.
Đội vận hành muốn so sánh chất lượng theo phiên bản prompt, model và vector index; metrics hiện chỉ có tên endpoint nên kết quả của các đợt triển khai bị trộn lẫn.
Ứng dụng thêm nhãn request ID làm metric dimension cho từng lời gọi; hệ thống quan sát sinh quá nhiều time series khiến chi phí lưu metrics tăng nhanh khi người dùng tăng.
Nhóm phát triển bật ghi toàn bộ prompt và retrieved context vào traces để điều tra hallucination; bản ghi quan sát vô tình chứa tài liệu mật và dữ liệu cá nhân của người dùng.
Một hệ thống observability chỉ lấy mẫu một phần nhỏ các trace; số lỗi công cụ hiếm gặp không xuất hiện trong mẫu nên dashboard đánh giá chất lượng vận hành quá lạc quan.
Ứng dụng Spring AI xuất metrics và traces qua một dịch vụ collector; collector ngừng hoạt động nhưng API vẫn trả kết quả, khiến nhóm vận hành nhầm thiếu telemetry với việc không còn lỗi.
Nhóm tối ưu pipeline thêm nhiều sự kiện trace ở từng token streaming; khi tải tăng, overhead ghi log và xuất telemetry làm phản hồi người dùng chậm hơn chính thời điểm chưa bật giám sát.
Ứng dụng đánh giá chất lượng bằng một bài test offline mỗi lần phát hành; sau khi ra mắt, các câu hỏi thực tế chuyển dần sang sản phẩm mới và độ chính xác giảm mà bộ benchmark không phản ánh.
Một hệ thống hỗ trợ bán lẻ thu phản hồi người dùng bằng nút hữu ích hoặc không hữu ích; nhiều lượt bị đánh giá thấp chỉ vì câu trả lời chậm, nhưng dữ liệu bị dùng trực tiếp làm nhãn fact checking.
Trợ lý chăm sóc khách hàng được triển khai phiên bản prompt mới; dashboard cho thấy relevance tăng nhưng số lần khách phải hỏi lại cũng tăng, khiến hai chỉ số chất lượng mâu thuẫn nhau.
Nhóm phát triển thêm một bước kiểm tra fact checking sau khi model sinh câu trả lời; tỷ lệ nội dung sai giảm nhưng request bị timeout nhiều hơn và đội sản phẩm chưa có tiêu chí đánh đổi rõ ràng.
Doanh nghiệp chạy bộ đánh giá định kỳ trên cùng dataset nhưng một số bài test truy cập vector store đang được cập nhật; điểm thay đổi giữa hai lần chạy không chỉ do phiên bản prompt.
Một ứng dụng Spring AI thử nghiệm song song hai nhà cung cấp model cho cùng bộ câu hỏi; một bên trả timeout cao hơn khi tải tăng, còn hệ thống chấm điểm bỏ qua hoàn toàn các request không có phản hồi.
Nhóm phát triển sửa prompt để tránh bịa nguồn trong RAG; điểm faithfulness tăng ở tập câu hỏi chuẩn nhưng tỷ lệ từ chối với câu hỏi có tài liệu phù hợp cũng tăng rõ rệt.
Trợ lý phân tích báo cáo nhận dữ liệu tài chính có số âm, đơn vị nghìn và phần trăm; câu trả lời nghe hợp lý nhưng kết quả kiểm tra fact checking chỉ dựa trên sự xuất hiện của các con số trong nguồn.
Một chatbot dịch vụ công được yêu cầu đưa ra câu trả lời có trích dẫn theo từng kết luận; sau khi chuyển model, citation vẫn tồn tại nhưng nhiều trích dẫn không hỗ trợ đúng mệnh đề mà chúng gắn vào.
Ứng dụng Spring AI gộp kết quả retrieval từ hai kho dữ liệu với độ tin cậy khác nhau; phiên bản pipeline mới ưu tiên tài liệu ít tin cậy hơn làm câu trả lời suy giảm mặc dù top-k relevance gần như không đổi.
Một hệ thống trợ lý pháp chế kiểm thử truy vấn dài gồm nhiều điều kiện ngoại lệ; kết quả đánh giá chung đạt nhưng model thường bỏ mất một điều kiện trong câu trả lời cuối, gây sai hướng dẫn nghiệp vụ.
Nhóm phát triển thay chính sách lưu cache cho câu trả lời RAG; độ trễ và chi phí giảm mạnh nhưng các phản hồi về biểu phí thay đổi mỗi ngày trở nên lỗi thời so với dữ liệu nguồn.
Một nền tảng đa tenant so sánh độ chính xác giữa các khách hàng nhưng chỉ số được gộp toàn cụm; tenant nhỏ có chỉ số thấp kéo dài dù điểm trung bình toàn hệ thống vẫn tốt.
Ứng dụng dùng bộ test tự động để quyết định triển khai prompt mới; lần phát hành vượt ngưỡng chất lượng trên bộ benchmark nhưng phát sinh lỗi quyền truy cập công cụ chỉ khi người dùng thực có vai trò hạn chế.
Đội vận hành khôi phục phiên bản prompt cũ sau khi chất lượng giảm; hệ thống không ghi lại chính xác cấu hình retrieval, model và tài liệu dùng lúc đánh giá nên bản rollback không tái hiện kết quả trước đó.
