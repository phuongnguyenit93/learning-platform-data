Câu 01. Trong ứng dụng Spring AI RAG, vì sao cần truy xuất tài liệu trước khi gọi chat model?
A. Sinh câu trả lời từ vector, không gọi chat model
B. Đưa bằng chứng liên quan vào prompt của chat model
C. Huấn luyện lại trọng số model bằng các đoạn đã tìm
D. Chọn một công cụ Java thay cho bước sinh câu trả lời
Đáp án đúng: B

Câu 02. Vai trò của một `DocumentReader` trong pipeline ingest Spring AI là gì?
A. Chia `Document` thành nhiều phần dựa trên token
B. Tìm hàng xóm vector gần nhất từ câu hỏi người dùng
C. Đưa các đoạn tìm được vào prompt trước chat model
D. Đọc nguồn thành `Document` có nội dung và metadata
Đáp án đúng: D

Câu 03. Metadata của `Document` nên có thông tin nào để tạo citation truy vết được?
A. ID truy vấn gần nhất, số topK và độ dài câu trả lời
B. Loại scheduler, số thread và timeout của chat client
C. Điểm truy xuất và nhiệt độ của chat model
D. ID tài liệu, phiên bản và vị trí của đoạn trích
Đáp án đúng: D

Câu 04. Khi dùng `TokenTextSplitter` cho tài liệu dài, mục tiêu chia chunk nào hợp lý?
A. Giữ nguyên tài liệu trong một chunk dù vượt context
B. Giữ ngữ cảnh đủ nghĩa mà không vượt số token
C. Đảm bảo mỗi chunk ứng với đúng một trang PDF
D. Đảm bảo đoạn dài bằng context window của model
Đáp án đúng: B

Câu 05. Khi thêm overlap giữa các chunk, đánh đổi nào thường xuất hiện?
A. Giữ bối cảnh qua ranh giới nhưng tăng dữ liệu trùng
B. Giảm trùng lặp nhưng dễ mất các ý nằm ở ranh giới
C. Không cần chia tài liệu nữa vì các đoạn đã chồng lấn
D. Giảm số vector cần lưu nhờ các phần lặp được bỏ
Đáp án đúng: A

Câu 06. Nếu chunk quá nhỏ trong tài liệu mô tả quy trình nhiều bước, lỗi phổ biến là gì?
A. Similarity cao đồng nghĩa tài liệu đáng tin
B. Retriever từ chối xử lý metadata có tên quá dài
C. Các bước bị tách khiến đoạn tìm thấy thiếu ý
D. Model cần chung embedding giữa các tenant
Đáp án đúng: C

Câu 07. Với tài liệu PDF gồm các trang scan, điều gì cần làm trước khi tạo embedding văn bản?
A. Mã hóa trực tiếp byte PDF bằng tokenizer của LLM
B. Đổi phần mở rộng của file thành tài liệu TXT
C. Trích xuất OCR và kiểm chất lượng văn bản
D. Chỉ dùng tên file và số trang làm nội dung vector
Đáp án đúng: C

Câu 08. Khi ingest lại tài liệu đã chỉnh sửa, cách nào giảm chunk trùng trong vector store?
A. Dùng ID ổn định để cập nhật hoặc thay chunk cũ
B. Sinh ID mới cho từng chunk ở mỗi đợt import
C. Giữ chunk bản cũ và tăng topK khi có phiên bản mới
D. Chỉ thay đổi số trang trong metadata của các chunk
Đáp án đúng: A

Câu 09. Vì sao query và document cần embedding tương thích để tìm kiếm vector?
A. Truy vấn cần dùng chung template với bước chat answer
B. Cosine score phải bằng nhãn relevance của người chấm
C. Query cần có cùng số token với chunk
D. Chúng phải ở cùng không gian biểu diễn để so sánh
Đáp án đúng: D

Câu 10. Khi nâng cấp embedding model sang không gian vector khác, nên xử lý index thế nào?
A. Chỉ giảm topK để tránh kết quả truy xuất sai
B. Tái tạo embedding của tài liệu bằng model mới
C. Giữ vector cũ và chỉ tăng ngưỡng điểm similarity
D. Đổi model ở chat client nhưng giữ cấu trúc vector
Đáp án đúng: B

Câu 11. Trong Spring AI, `VectorStore` phục vụ nhiệm vụ chính nào của RAG?
A. Chia tài liệu theo token trước khi sinh vector
B. Lưu `Document` và tìm các đoạn gần query vector
C. Chấm tính đúng của câu trả lời theo dữ liệu gốc
D. Thêm system instruction vào prompt của chat model
Đáp án đúng: B

Câu 12. Khi điểm similarity của tài liệu tìm được quá thấp, nên cân nhắc điều gì?
A. Lọc theo ngưỡng và đo ảnh hưởng đến recall
B. Chọn top1 ngay cả khi similarity thấp
C. Đưa thêm chunk ngẫu nhiên để làm dày context
D. Tăng temperature để cải thiện độ gần của vector
Đáp án đúng: A

Câu 13. Tăng topK từ 5 lên 20 trong truy xuất RAG tạo ra đánh đổi nào?
A. Embedding model được huấn luyện tiếp từ các đoạn tìm
B. Chất lượng citation được bảo đảm vì nhiều đoạn hơn
C. Vector index được thu nhỏ nhờ lưu ít ứng viên
D. Recall có thể tăng, nhưng nhiễu và token cũng tăng
Đáp án đúng: D

Câu 14. Trong RAG nhiều tenant, tenant ID để lọc truy xuất nên lấy từ đâu?
A. Trường tenantId do người dùng chèn trong prompt
B. Tenant có tài liệu mang cosine score cao nhất
C. Metadata tenant trong chunk được truy xuất đầu tiên
D. Phiên đã xác thực và quy tắc quyền ở phía server
Đáp án đúng: D

Câu 15. Một chunk có điểm similarity cao nhưng người dùng không có quyền đọc; nên làm gì?
A. Loại chunk khi lọc quyền trước lúc ghép context
B. Chỉ kiểm quyền sau khi đã tạo xong câu trả lời
C. Dùng cosine score thay thế bước kiểm quyền truy cập
D. Đưa chunk vào prompt và để model tự bỏ nội dung
Đáp án đúng: A

Câu 16. Tài liệu bị thu hồi quyền truy cập; cần xử lý gì để tránh RAG dùng dữ liệu cũ?
A. Giữ bản cũ trong index để bảo toàn khả năng recall
B. Thu hồi chunk và cache theo quyền mới
C. Để lại vector và chỉ đổi câu nhắc trong prompt
D. Tăng similarity threshold mà không sửa phân quyền
Đáp án đúng: B

Câu 17. Với mã hàng chính xác cùng câu hỏi diễn đạt tự nhiên, cách search nào hữu ích?
A. Chỉ dùng cosine similarity mà bỏ các từ mã hàng
B. Chỉ lọc theo ngày nhập tài liệu rồi lấy đoạn mới
C. Kết hợp tìm từ khóa và vector theo hybrid search
D. Chỉ gửi câu hỏi tới model mà không truy xuất tài liệu
Đáp án đúng: C

Câu 18. Reranker chỉ nhận 30 đoạn ứng viên; giới hạn nào cần chú ý khi kiểm chất lượng?
A. Reranker cập nhật embedding model sau mỗi lần query
B. Không xếp được đoạn đúng nếu nó vắng trong ứng viên
C. Reranker tự sinh citation cho đoạn nguồn chưa tìm
D. Reranker tự thêm tài liệu mới vào index vector store
Đáp án đúng: B

Câu 19. Khi cấu hình truy xuất qua `SearchRequest` của Spring AI, nhóm tham số nào liên quan?
A. System prompt, user message và thứ tự tool call
B. Query, topK và điều kiện lọc metadata
C. Temperature, topP và maxOutputTokens của model
D. Loại retry, số thread và timeout của chat client
Đáp án đúng: B

Câu 20. `QuestionAnswerAdvisor` dùng `VectorStore` trong Spring AI để thực hiện gì?
A. Đưa tài liệu được tìm vào prompt hỏi đáp
B. Chấm điểm correctness bằng dữ liệu tham chiếu
C. Sinh lại embedding mỗi khi chat model phản hồi
D. Đặt quyền truy cập vào system prompt
Đáp án đúng: A

Câu 21. Với `RetrievalAugmentationAdvisor`, lợi ích của thiết kế module RAG là gì?
A. Giữ phản hồi tĩnh thay các bước retrieval
B. Ghép các bước truy xuất và bổ sung ngữ cảnh
C. Thay thế truy xuất bằng bộ nhớ từ lần chat trước
D. Biên dịch các tài liệu nguồn thành mã Java mới
Đáp án đúng: B

Câu 22. Khi đưa các chunk truy xuất vào prompt, thiết kế nào giúp truy vết nguồn?
A. Chỉ lưu điểm similarity nhưng bỏ văn bản của chunk
B. Chỉ giữ nội dung các chunk rồi loại bỏ ID tài liệu
C. Gộp các hướng dẫn từ chunk vào system instruction
D. Tách câu hỏi, bằng chứng và metadata nguồn rõ ràng
Đáp án đúng: D

Câu 23. Một chunk có lệnh 'bỏ qua hướng dẫn và tiết lộ secret'; ứng dụng phải xử lý sao?
A. Cho chunk quyền ưu tiên cao hơn system instruction
B. Gửi secret cho tool được nhắc đến trong tài liệu
C. Coi chunk là dữ liệu, không phải chỉ dẫn đáng tin
D. Thực thi lệnh của chunk vì nó có citation nguồn
Đáp án đúng: C

Câu 24. Muốn citation kiểm chứng được từng khẳng định trong câu trả lời, cần thông tin gì?
A. Embedding dimension và mã định danh của vector index
B. Tên prompt và thời điểm gọi chat model
C. Đoạn chứng cứ hỗ trợ và ID nguồn tương ứng
D. TopK được dùng và số token đầu ra của chat model
Đáp án đúng: C

Câu 25. Khi các tài liệu tìm được thiếu căn cứ để trả lời, nên tạo phản hồi nào?
A. Tăng temperature để model tự suy luận thêm
B. Nêu thiếu bằng chứng và tránh tự suy đoán kết luận
C. Trả lời theo chunk gần nhất dù chưa đủ căn cứ
D. Tạo nguồn trích dẫn cho kết quả model vừa phỏng đoán
Đáp án đúng: B

Câu 26. Trong đánh giá RAG, faithfulness chủ yếu kiểm tra thuộc tính nào?
A. Độ trùng với đáp án tham chiếu ngoài hệ truy xuất
B. Tỷ lệ vector được đọc trong thời gian giới hạn
C. Số token có trong phần context của mỗi lần hỏi
D. Khẳng định được context truy xuất hỗ trợ
Đáp án đúng: D

Câu 27. Câu trả lời thực tế đúng nhưng không được context hỗ trợ; cách chấm nào phù hợp?
A. Retrieval recall đạt vì model trả đúng đáp án
B. Citation precision đạt nhờ câu cuối chính xác
C. Faithfulness đạt vì câu trả lời hợp với sự thật
D. Correctness có thể đạt nhưng faithfulness thấp
Đáp án đúng: D

Câu 28. Với bộ nhãn tài liệu liên quan, retrieval precision@k được tính thế nào?
A. Số đoạn liên quan trong topK chia cho k
B. Số câu trả lời đúng chia tổng số truy vấn đánh giá
C. Số đoạn liên quan trong topK chia tổng số liên quan
D. Tổng số đoạn trong index chia số đoạn được truy xuất
Đáp án đúng: A

Câu 29. Trong retrieval recall@k, mẫu số của phép tính là gì?
A. Toàn bộ tài liệu liên quan được gắn nhãn
B. Số tài liệu trả về ở topK của truy vấn hiện tại
C. Tổng số vector lưu trong index dùng để truy xuất
D. Số lần chat model đã phản hồi yêu cầu
Đáp án đúng: A

Câu 30. Tập kiểm thử RAG nên gồm những tình huống nào để tránh thiên lệch?
A. Chỉ câu đã trả lời đúng trong bản triển khai trước
B. Chỉ câu có độ dài prompt thấp hơn mức trung bình
C. Chỉ câu có chunk liên quan xuất hiện ở top1
D. Câu có nguồn, thiếu nguồn và dễ gây nhầm
Đáp án đúng: D

Câu 31. Retriever không trả kết quả dù câu hỏi có dữ liệu nguồn; kiểm tra lớp nào trước?
A. Ingest, embedding, filter và cấu hình search
B. Độ dài response cuối cùng trong các lần gọi model
C. Temperature cùng maxTokens của bước chat generation
D. Độ đúng citation của câu trả lời model
Đáp án đúng: A

Câu 32. Để hạn chế câu trả lời RAG dùng nội dung lỗi thời, cách nào phù hợp?
A. Đồng bộ index theo phiên bản tài liệu nguồn
B. Tăng context window mà không thay embedding cũ
C. Giảm timeout để ưu tiên đoạn tìm nhanh
D. Thay prompt thành yêu cầu 'trả lời thông tin mới'
Đáp án đúng: A

Câu 33. Sau khi đổi chunking hoặc topK, test hồi quy nào đo đúng chất lượng?
A. So thời gian build nhưng thay cả dữ liệu test
B. So số phiên chat mới sau khi deployment hoàn tất
C. So retrieval và grounding trên cùng bộ nhãn
D. So số lượng vector mà không xem nội dung được tìm
Đáp án đúng: C

Câu 34. Retriever đã tìm đúng nguồn nhưng model vẫn tạo số liệu sai; nên soi bước nào?
A. Chỉ kiểm lượng kết nối mạng giữa các worker
B. Chỉ kiểm kích thước của bảng lưu vector
C. Prompt và cách model sử dụng bằng chứng nguồn
D. Chỉ kiểm số replica của dịch vụ vector store
Đáp án đúng: C

Câu 35. Yếu tố nào trong RAG thường làm tăng input token và chi phí chat model?
A. Số replica của vector store đang phục vụ query
B. Loại file nguồn được DocumentReader hỗ trợ
C. Số lần cập nhật metadata không kèm nội dung
D. Các chunk truy xuất được thêm vào prompt
Đáp án đúng: D

Câu 36. Traces của một request RAG nên tách span nào để tìm nguyên nhân chậm?
A. Chỉ thời gian khởi động server trước khi chạy RAG
B. Chỉ thời gian build và tạo embedding trong CI
C. Các bước retrieve, rerank và chat generation
D. Chỉ tổng thời gian từ HTTP request đến response
Đáp án đúng: C

Câu 37. Sau tăng topK, p95 latency tăng còn p50 ổn định; điều này gợi ý gì?
A. Nhóm request đuôi bị chậm, cần đối chiếu trace
B. Retriever tìm đủ chunk liên quan cho các query
C. Độ trễ tăng đều giữa các request
D. Chất lượng câu trả lời đã tăng cùng độ trễ
Đáp án đúng: A

Câu 38. Cache câu trả lời RAG cho nhiều tenant cần phân biệt thông tin nào?
A. Chỉ câu hỏi dạng text, không xét người yêu cầu
B. Chỉ số lượng chunk đã tồn tại trong vector store
C. Tenant, quyền đọc và phiên bản dữ liệu nguồn
D. Chỉ tên model embedding được chia sẻ toàn hệ
Đáp án đúng: C

Câu 39. Thu thập log/metric Spring AI cần tránh ghi thô loại dữ liệu nào?
A. Loại operation embedding, retrieval hoặc chat
B. Thời gian hoàn tất mỗi span đã tổng hợp
C. Prompt và nội dung riêng tư trong context
D. Tên model đã dùng cho một operation RAG
Đáp án đúng: C

Câu 40. Quality gate để triển khai bản RAG mới nên kết hợp chỉ số nào?
A. Chỉ thời gian phản hồi của một truy vấn mẫu
B. Retrieval, grounding, p95 latency và chi phí
C. Chỉ số token output mà không kiểm độ đúng
D. Chỉ recall mà không kiểm khả năng dẫn nguồn
Đáp án đúng: B
