Một doanh nghiệp dùng Spring AI xây trợ lý nội bộ từ hàng trăm PDF quy trình; nhiều tài liệu là bản quét hình ảnh nên bước nạp chỉ tạo Document rỗng và bot không tìm được nội dung khi nhân viên hỏi.
Hệ thống tra cứu hợp đồng bảo hiểm trích xuất văn bản từ PDF có bảng quyền lợi nhiều cột; sau khi nạp vào kho tri thức, số tiền và điều kiện của các hàng bị ghép nhầm.
Nhóm nhân sự nạp các trang Markdown từ wiki công ty vào pipeline RAG; khi bỏ các heading trước khi chia tài liệu, đoạn quy định thử việc không còn liên kết được với phòng ban áp dụng.
Trợ lý bán hàng lấy dữ liệu từ các trang HTML sản phẩm; phần menu, footer và banner được lưu lặp trong mọi Document khiến kết quả tìm kiếm vector ưu tiên thông tin điều hướng.
Một hệ thống quản lý thiết bị nạp file Word có hình minh họa và chú thích kỹ thuật; thông tin trong hình không có trong phần text được trích xuất khiến câu trả lời thiếu bước cảnh báo quan trọng.
Kho tài liệu pháp chế chứa các bản PDF được bảo vệ bằng mật khẩu; luồng ingestion vẫn đánh dấu đợt nạp hoàn tất dù nhiều tệp không được đọc thành công.
Nhóm triển khai trợ lý du lịch hợp nhất dữ liệu từ website, tệp CSV và PDF; cùng thông tin giờ hoạt động được thể hiện khác định dạng ngày và múi giờ nên câu trả lời đôi khi mâu thuẫn.
Dịch vụ tra cứu chính sách giữ nguyên tên file nhưng không lưu phiên bản và thời điểm hiệu lực trong metadata Document; nhân viên không biết một kết quả tìm kiếm thuộc bản chính sách nào.
Một chuỗi bán lẻ quét lại toàn bộ kho tài liệu mỗi đêm; các đoạn giống hệt từ cùng một tệp được thêm thành vector mới và chiếm nhiều vị trí trong top-k retrieval.
Trợ lý hỗ trợ khách hàng nạp tài liệu bằng tác vụ chạy nền; công việc dừng giữa chừng nhưng dashboard không chỉ ra những tệp chưa được embedding nên bot trả lời đầy đủ với nhóm sản phẩm này và thiếu với nhóm khác.
Doanh nghiệp cập nhật giá sản phẩm hàng giờ; dữ liệu trong website đã mới nhưng vector store chỉ nhận bản nạp theo lịch ban đêm nên RAG vẫn báo mức giá cũ.
Hệ thống vận hành thu hồi một quy trình không còn hợp lệ; bản Document nguồn đã bị xóa nhưng các embedding tương ứng còn trong vector store và tiếp tục xuất hiện trong câu trả lời.
Trợ lý mua sắm nhận nhiều phiên bản hợp đồng cùng lúc; phiên bản cũ có số lần xuất hiện trong kết quả retrieval cao hơn bản mới và chi phối câu trả lời cuối.
Nhóm tích hợp dùng bộ đọc tài liệu từ kho lưu trữ mạng; trong lúc đọc một file lớn, kết nối bị ngắt khiến bản text chỉ còn nửa cuối nhưng pipeline vẫn gắn nhãn đã nạp thành công.
Một ngân hàng nạp tài liệu tiếng Việt chứa ký tự tổ hợp Unicode khác nhau; những câu hỏi đúng từ khóa đôi khi không tìm thấy tài liệu vì dữ liệu nguồn và truy vấn có cách chuẩn hóa khác.
Ứng dụng RAG về bảo trì máy công nghiệp có tài liệu chứa sơ đồ điện và chỉ dẫn trong ảnh; câu trả lời dựa trên phần text thiếu các ký hiệu nối mạch quan trọng.
Một trợ lý trường học ingest các file CSV có hàng nghìn học phí; bộ đọc chỉ chuyển tên cột mà không giữ liên hệ giữa mã ngành và mức học phí của từng dòng.
Trung tâm hỗ trợ sản phẩm lưu Document metadata về ngôn ngữ và thị trường; khi chuyển đổi nguồn dữ liệu, trường thị trường bị bỏ và câu trả lời trộn chính sách Việt Nam với quốc gia khác.
Doanh nghiệp có 20.000 trang tài liệu kỹ thuật; một lần ingest đồng thời toàn bộ dữ liệu khiến bộ nhớ ứng dụng Spring AI tăng cao và nhiều lần gọi embedding bị nghẽn.
Trợ lý tuân thủ phải xử lý tài liệu chứa thông tin cá nhân; khi lập chỉ mục, các đoạn văn bản gốc được gửi tới dịch vụ embedding ngoài mà bộ phận bảo mật chưa kiểm soát phạm vi dữ liệu truyền đi.
Pipeline dùng TokenTextSplitter chia tài liệu hợp đồng; điều kiện ngoại lệ nằm ở cuối chunk trước còn nghĩa vụ áp dụng ở đầu chunk sau nên model diễn giải sai quy định.
Một bộ hướng dẫn cài đặt có từng bước đánh số; chiến lược chunk theo số ký tự cắt giữa bước lệnh và cảnh báo, khiến retrieval trả về một bước thiếu bối cảnh.
Nhóm phát triển tăng overlap giữa các chunk để giữ ngữ cảnh; cùng một điều khoản xuất hiện ở nhiều kết quả gần như giống nhau làm top-k mất chỗ dành cho các nguồn bổ sung.
Một ứng dụng hỏi đáp chính sách dùng chunk rất nhỏ; truy vấn về điều kiện đủ và ngoại lệ trả về hai mảnh riêng biệt nên model thường chỉ đọc được một nửa quy định.
Dịch vụ xử lý hồ sơ pháp lý chia chunk quá lớn so với giới hạn token của model embedding; nhiều Document lỗi hoặc bị cắt bớt ngay trước khi tạo vector.
Trợ lý kỹ thuật nạp Markdown có bảng cấu hình và đoạn lệnh nhiều dòng; quá trình chunking chia đôi bảng và đoạn lệnh khiến kết quả truy xuất thiếu cột hoặc mất ngữ nghĩa.
Nhóm tài chính chia tài liệu thành chunk cố định mà không lưu tiêu đề chương; nhiều đoạn về hạn mức có nội dung giống nhau nhưng thuộc loại khách hàng khác nhau.
Một hệ thống RAG từ tài liệu sản phẩm không giữ số trang và tọa độ nguồn sau chunking; khi khách yêu cầu dẫn nguồn, ứng dụng chỉ hiển thị tên tài liệu mà không xác định được đoạn chứng cứ.
Ứng dụng hỗ trợ pháp lý lưu footnote và phụ lục ở đoạn tách biệt; câu trả lời viện dẫn điều khoản chính nhưng bỏ sót ngoại lệ chỉ được định nghĩa trong phụ lục.
Một kho tri thức chứa tài liệu tiếng Việt, tiếng Nhật và tiếng Anh; chunker dùng ước lượng token không phù hợp với mọi ngôn ngữ nên độ dài chunk và chi phí embedding biến động lớn.
Dịch vụ nạp lại tài liệu sau khi sửa lỗi OCR; cùng câu hỏi chuyển từ trả lời đúng sang thiếu thông tin vì điểm chia chunk thay đổi khiến các vector không còn giống lần đánh giá trước.
Nhóm triển khai chọn model embedding mới có số chiều vector khác với chỉ mục cũ; một phần bản ghi thêm mới bị từ chối còn truy vấn tiếp tục dùng vector chưa đồng nhất.
Trợ lý nhân sự tạo embedding cho tài liệu bằng một model nhưng chuyển model embedding của truy vấn sang phiên bản khác; kết quả similarity suy giảm dù nội dung dữ liệu không đổi.
Hệ thống ingest gọi dịch vụ embedding theo từng Document nhỏ; khi số tài liệu tăng, chi phí request và thời gian hoàn thành đợt cập nhật vượt ngân sách vận hành.
Một dịch vụ embedding trả lỗi giới hạn tốc độ giữa batch hàng trăm chunk; pipeline lưu một phần vector nhưng không ghi rõ chunk nào chưa thành công để phục hồi.
Ứng dụng dùng PGvector làm vector store; sau khi tăng quy mô lên hàng triệu vector, truy vấn similarity chậm dần vào giờ cao điểm dù độ dài câu hỏi không thay đổi.
Nhóm triển khai hai môi trường RAG dùng cùng tên collection trong vector store; dữ liệu thử nghiệm vô tình xuất hiện trong kết quả tìm kiếm production.
Một hệ thống đa tenant dùng metadata filter để phân quyền truy xuất tài liệu của doanh nghiệp đang đăng nhập; một nhánh tìm kiếm fallback không mang bộ lọc tenant khiến kết quả từ khách hàng khác lọt vào context.
Ứng dụng tạo ID vector mới mỗi lần tái nạp cùng một chunk; tài liệu bị nhân bản trong chỉ mục và số lượng vector tăng dù kho nguồn không thêm tài liệu.
Trợ lý pháp chế xóa dữ liệu theo yêu cầu của khách hàng; nội dung gốc đã bị loại khỏi kho lưu trữ nhưng bản sao trong vector index và snapshot dự phòng vẫn có thể được truy xuất.
Nhóm vận hành cấu hình quyền kết nối tới vector store bằng tài khoản dùng chung; các dịch vụ không liên quan đều có thể đọc hoặc xóa embedding của toàn bộ phòng ban.
Ứng dụng RAG dùng cơ chế lưu cache embedding theo nội dung; hai tài liệu có câu giống nhau nhưng quyền truy cập khác nhau bị ghép metadata sai khi tái sử dụng bản ghi cache.
Hệ thống doanh nghiệp phục hồi vector store từ bản snapshot cũ sau sự cố; dữ liệu nguồn đã thay đổi trong thời gian gián đoạn nhưng bot vẫn trả lời dựa trên chỉ mục trước sự cố.
Trợ lý bảo trì truy vấn mã lỗi thiết bị rất hiếm; tìm kiếm vector ưu tiên các đoạn mô tả chung có ngữ nghĩa gần giống thay vì tài liệu chứa đúng mã lỗi.
Dịch vụ thương mại điện tử nhận câu hỏi về mã SKU có chữ và số; embedding truy xuất dòng sản phẩm tương tự nhưng bỏ qua đúng SKU mà khách đang hỏi.
Nhóm thử nghiệm hybrid retrieval kết hợp tìm kiếm từ khóa và vector; câu hỏi về tên API chính xác lại nhận ít kết quả đúng hơn khi trọng số hai nguồn được thay đổi.
Một ứng dụng dùng top-k bằng ba cho mọi yêu cầu; câu hỏi yêu cầu đối chiếu năm điều kiện từ các trang khác nhau khiến context thiếu chứng cứ dù vector store chứa đủ tài liệu.
Trợ lý quy định nội bộ tăng top-k từ năm lên hai mươi; model bắt đầu kết hợp nhiều đoạn có nội dung tương tự nhưng khác hiệu lực, còn độ trễ và token đầu vào tăng.
Pipeline đặt similarity threshold quá cao khi tìm tài liệu về thuật ngữ mới; hệ thống coi kho tri thức không có đáp án dù chuyên gia xác nhận có tài liệu phù hợp.
Nhóm phát triển hạ ngưỡng similarity để tăng recall; các truy vấn không liên quan bắt đầu nhận nhiều đoạn nhiễu và model đưa ra câu trả lời dựa trên nội dung không phù hợp.
Ứng dụng tư vấn khách hàng nhận câu hỏi nhiều ý trong cùng một câu; vector search trả về đoạn phù hợp với ý thứ nhất nhưng không tìm thấy tài liệu cho ý thứ hai.
Hệ thống hỏi đáp dành cho người vận hành dùng câu hỏi ngắn như 'cách reset?'; kết quả retrieval thay đổi mạnh giữa các loại thiết bị vì truy vấn thiếu tên máy và phiên bản firmware.
Trợ lý nhân sự cho phép đặt câu hỏi theo phòng ban; truy vấn hỏi về chính sách của khối kinh doanh nhưng metadata filter vẫn sử dụng phòng ban mặc định từ phiên trước.
Một kho tài liệu có chính sách theo ngày hiệu lực; kết quả tìm kiếm ưu tiên đoạn bản cũ do mức tương đồng cao hơn dù bản hiện hành được đánh dấu mới hơn.
Ứng dụng hỗ trợ kỹ thuật dùng reranker sau bước vector search; sau khi thay model rerank, tài liệu chứa điều kiện loại trừ bị đẩy khỏi danh sách cuối và câu trả lời thiếu cảnh báo.
Trợ lý y tế nhận truy vấn tiếng Việt trong khi tài liệu chuyên môn lưu bằng tiếng Anh; tìm kiếm cross-language thất bại với thuật ngữ có nhiều cách dịch nên context chỉ gồm tài liệu phổ thông.
Ngân hàng sử dụng Spring AI ChatClient để trả lời với context truy xuất; một bước refactor bỏ kết quả vector search khỏi prompt nên model vẫn tạo câu trả lời trôi chảy nhưng không còn căn cứ tài liệu.
Ứng dụng RAG thêm nhiều hướng dẫn hệ thống và lịch sử chat vào prompt; các đoạn truy xuất quan trọng bị cắt do vượt context window nên câu trả lời mất chi tiết ngoại lệ.
Trợ lý mua bảo hiểm phải dùng cả hồ sơ khách hàng lẫn điều khoản từ vector store; prompt kết hợp thông tin của hai sản phẩm khác nhau và model đưa ra mức quyền lợi không tồn tại.
Nhóm phát triển dùng QuestionAnswerAdvisor trong quy trình hỏi đáp; sau khi thay cấu hình advisor, kết quả tìm kiếm vẫn có tài liệu nhưng model không được cung cấp đúng đoạn liên quan.
Một hệ thống dùng RetrievalAugmentationAdvisor để thêm context; hai luồng yêu cầu tương tự áp dụng bộ lọc và cơ chế reranking khác nhau khiến chất lượng câu trả lời rất không ổn định.
Trợ lý chăm sóc khách hàng lưu lịch sử hội thoại; người dùng hỏi 'chính sách đó' sau nhiều lượt nhưng bước retrieval chỉ dùng câu hiện tại, khiến tài liệu truy xuất không đúng chủ đề đã đề cập.
Một chatbot doanh nghiệp dùng câu hỏi viết lại dựa trên lịch sử để truy xuất tài liệu; phép viết lại làm mất mã đơn hàng quan trọng nên kết quả đúng không còn trong context.
Nhóm tích hợp cache câu trả lời RAG theo câu hỏi gốc; cùng một câu hỏi từ hai tenant có quyền tài liệu khác nhau lại nhận phản hồi lấy từ cache chung.
Trợ lý pháp chế nhận một tài liệu từ nguồn ngoài có đoạn văn giả mạo chỉ dẫn hệ thống; model làm theo chỉ dẫn nằm trong tài liệu thay vì chỉ dùng nó làm bằng chứng cho câu hỏi.
Hệ thống báo giá đưa dữ liệu hợp đồng mật vào context của model; phản hồi không chứa dữ liệu nhạy cảm nhưng trace và log request lưu nguyên phần context khiến nhân viên ngoài nhóm có thể đọc được.
Ứng dụng hỏi đáp cố tạo trả lời ngay cả khi không tìm được chunk phù hợp; model tự đưa ra thông tin chính sách giả định nhưng giao diện vẫn hiển thị biểu tượng dẫn nguồn như câu trả lời đã được kiểm chứng.
Trợ lý tra cứu sổ tay kỹ thuật trả lời đúng thông số sản phẩm nhưng citation trỏ đến một trang không chứa thông số đó; khách hàng không xác minh được kết luận đã nhận.
Một RAG bot tổng hợp hai tài liệu có cùng tên nhưng khác mã phiên bản; citation chỉ hiện tên file khiến người dùng tưởng mọi kết luận đều dựa trên bản hiện hành.
Ứng dụng gắn đường dẫn nguồn vào từng chunk nhưng URI nguồn bị đổi sau di chuyển kho tài liệu; câu trả lời vẫn đúng song toàn bộ liên kết kiểm chứng trả lỗi.
Nhóm sản phẩm dùng model tạo citation bằng cách tự sinh số trang; báo cáo có định dạng trích dẫn đẹp nhưng nhiều số trang không khớp trang thực tế trong PDF.
Trợ lý tài chính trả lời bằng phép tính từ hai bảng định mức khác nhau; mỗi con số đều có dẫn nguồn hợp lệ nhưng phép kết hợp sai ngữ cảnh khiến kết quả cuối không đúng.
Một hệ thống RAG xử lý câu hỏi về một sản phẩm mới chưa xuất hiện trong tài liệu; bot suy diễn dựa trên sản phẩm tương tự thay vì thể hiện rằng không đủ bằng chứng.
Trung tâm hỗ trợ cần phân biệt lỗi retrieval với lỗi sinh câu trả lời; sau một thay đổi prompt, điểm relevance của context vẫn ổn nhưng tỷ lệ trả lời thiếu chứng cứ tăng.
Nhóm kiểm thử tạo dataset có câu hỏi, câu trả lời tham chiếu và các đoạn nguồn được chuyên gia chọn; sau khi update vector index, top-k retrieval có similarity cao nhưng thiếu nhiều tài liệu chuẩn.
Ứng dụng dùng các ví dụ đánh giá RAG từ tài liệu đã sử dụng để tinh chỉnh prompt; điểm benchmark nội bộ cao nhưng câu hỏi mới của người dùng thực có tỷ lệ hallucination lớn.
Một dự án xây bài kiểm thử tự động relevance dựa vào so khớp từ khóa giữa câu trả lời và nguồn; những câu trả lời dùng cách diễn đạt khác vẫn đúng ý bị chấm điểm thấp.
Nhóm triển khai đánh giá groundedness bằng model chấm điểm; cùng một câu trả lời được chấm khác nhau giữa các lần chạy khiến quyết định phát hành prompt mới trở nên thiếu ổn định.
Trợ lý nội bộ cho phép cả câu hỏi tiếng Việt lẫn tiếng Anh; tập đánh giá chỉ có tiếng Anh nên việc đổi embedding làm chất lượng tiếng Việt suy giảm nhưng điểm tổng thể vẫn tăng.
Doanh nghiệp kiểm thử cả câu hỏi có đáp án và câu hỏi không có tài liệu; một phiên bản pipeline tăng recall nhưng cũng tăng tỷ lệ trả lời bịa khi không có nguồn thích hợp.
Nhóm đánh giá RAG chỉ chấm chất lượng câu trả lời cuối cùng; một phiên bản mới đạt điểm tương tự bản cũ dù số lượt truy xuất và lượng context xử lý tăng gấp ba.
Ứng dụng RAG đo latency tổng từ HTTP request đến response; sau một đợt tối ưu, người dùng phản ánh chờ lâu nhưng nhóm không biết chậm ở bước đọc embedding, vector retrieval hay model generation.
Dịch vụ RAG streaming vẫn trả phản hồi đầy đủ nhanh như trước nhưng thời gian chờ token đầu tiên tăng mạnh; dashboard chỉ theo dõi thời gian hoàn tất nên không thấy sự suy giảm trải nghiệm.
Nhóm vận hành ghi traces cho bước embedding, vector search và chat completion; một phần lời gọi không mang cùng correlation ID, khiến các span không nối được thành một chuỗi request.
Doanh nghiệp thêm nhãn raw question và Document ID vào metrics; số lượng time series tăng rất nhanh khi lưu lượng lớn và hạ tầng quan sát bắt đầu quá tải.
Một hệ thống Spring AI phát telemetry chứa đầy đủ prompt và đoạn truy xuất; khi hỗ trợ người dùng điều tra lỗi, nhóm vận hành vô tình truy cập thông tin cá nhân và tài liệu thuộc bộ phận khác.
Đội kỹ thuật tính chi phí token của lượt chat cuối nhưng không tính bước embedding khi ingest và các lần gọi model để viết lại truy vấn; tổng phí nhà cung cấp cao hơn dự toán trên dashboard.
Ứng dụng hỏi đáp tạo lại embedding cho toàn bộ tài liệu mỗi lần triển khai dù dữ liệu chỉ đổi vài tệp; chi phí vận hành tăng mạnh và cửa sổ cập nhật chỉ mục kéo dài.
Nhóm phát triển dùng embedding model giá rẻ để giảm chi phí; sau khi thay model, recall giảm với câu hỏi thuật ngữ chuyên ngành nhưng báo cáo tài chính chỉ thể hiện lợi ích chi phí.
Trợ lý doanh nghiệp tăng top-k và thêm reranking để nâng chất lượng; chi phí model, thời gian vector retrieval và mức dùng CPU tăng khiến p95 latency vượt giới hạn sản phẩm.
Một hệ thống tích hợp Spring AI bị lỗi 429 từ nhà cung cấp model khi truy vấn tăng đột biến; nhiều lần retry khiến cùng câu hỏi xuất hiện trong nhiều request và chi phí phát sinh không được gộp.
Nhóm triển khai so sánh hai phiên bản RAG theo số token và điểm đánh giá trung bình; phiên bản mới phục vụ nhiều câu hỏi dài hơn nên việc so sánh chi phí trên mỗi request không phản ánh độ khó tương đương.
Ứng dụng RAG cập nhật nhiều tệp tài liệu cùng lúc; trong vài phút chuyển đổi chỉ mục, các truy vấn nhận được context gồm cả chunk cũ và mới của cùng một quy trình.
Trợ lý phục vụ hàng nghìn nhân viên đồng thời; vector store bắt đầu trả timeout dưới tải cao và model vẫn tạo phản hồi không có context mà không ghi rõ nguồn đã thất bại.
Doanh nghiệp thay thế vector store hiện tại bằng dịch vụ mới; độ tương đồng và thứ tự trả về của cùng một truy vấn thay đổi sau migration dù embedding và tài liệu đầu vào giữ nguyên.
Nhóm vận hành khôi phục RAG sau sự cố khu vực dữ liệu; các Document nguồn còn đầy đủ nhưng metadata, embedding và checkpoint ingest phục hồi ở các thời điểm khác nhau khiến citation bị lệch.
Một trợ lý quản lý tri thức dùng RAG cho cả tài liệu công khai và tài liệu hạn chế; nhân viên bị thu hồi quyền truy cập vẫn nhìn thấy nội dung từ cache hoặc truy vấn vector chưa áp dụng quyền mới.
Đội phát triển rollback prompt sau khi phát hiện câu trả lời sai; vector index và tài liệu nguồn đã thay đổi nên chất lượng không trở về mức đo được ở phiên bản prompt cũ.
Người dùng báo lỗi một câu trả lời thiếu thông tin từ phụ lục; hệ thống không lưu phiên bản embedding, chính sách chunking, tham số retrieval và các chunk thực tế từng đưa vào model nên khó tái hiện lỗi.
