Câu 01. Muốn so chất lượng hai phiên bản prompt trên ứng dụng Spring AI, cách đánh giá offline nào phù hợp nhất?
A. Chạy cùng tập câu hỏi và rubric trên cả hai phiên bản
B. So tỷ lệ HTTP 200 trên hai giai đoạn có lượng tải khác
C. So độ dài câu trả lời trên hai tập câu hỏi khác nhau
D. Chạy mỗi prompt với câu hỏi do chính phiên bản đó tạo
Đáp án đúng: A

Câu 02. Đối với tập đánh giá câu hỏi đáp có dữ liệu tham chiếu, bản ghi test nên lưu thông tin nào?
A. Tập vector truy xuất và số token model dùng cho mỗi câu
B. Chỉ câu hỏi, điểm model tự cho và câu trả lời đã sinh
C. Câu hỏi, đáp án tham chiếu và bằng chứng đối chiếu
D. Câu hỏi, response trước đó và thời gian xử lý request
Đáp án đúng: C

Câu 03. Một tập test bị dùng để sửa prompt lặp đi lặp lại; nguy cơ khi báo điểm trên chính tập đó là gì?
A. Điểm giảm vì tập test trở thành dữ liệu production
B. Điểm chỉ phản ánh lỗi mạng vì model không đổi trọng số
C. Điểm được chuẩn hóa theo số lần sửa prompt trước đó
D. Điểm bị lạc quan do prompt đã khớp các mẫu được xem
Đáp án đúng: D

Câu 04. Ứng dụng RAG phục vụ hỏi đáp nhân sự và kỹ thuật; làm sao tránh điểm trung bình che lỗi của một nhóm?
A. Chỉ kiểm tra các câu hỏi được truy vấn nhiều nhất
B. Tính chất lượng theo từng nhóm câu hỏi và độ khó
C. Chỉ đánh giá dữ liệu của nhóm đạt kết quả cao nhất
D. Tính một điểm chung trên mọi câu hỏi đã lấy mẫu
Đáp án đúng: B

Câu 05. Trong RAG, đánh giá relevance của tài liệu được truy xuất chủ yếu kiểm tra điều gì?
A. Đoạn truy xuất có liên quan đến câu hỏi người dùng
B. Đoạn truy xuất đến từ index có thời gian phản hồi thấp
C. Đoạn truy xuất có cùng độ dài với câu trả lời sinh ra
D. Đoạn truy xuất được trả về trước khi LLM kết thúc
Đáp án đúng: A

Câu 06. Một câu trả lời RAG chứa thông tin không xuất hiện trong tài liệu được cấp; tiêu chí nào phát hiện trực tiếp?
A. Relevance chỉ đo tốc độ tìm tài liệu của retriever
B. Faithfulness đo mức khẳng định được nguồn hỗ trợ
C. Latency kiểm tỷ lệ token sinh ra mỗi giây
D. Availability kiểm tỷ lệ service không bị lỗi mạng
Đáp án đúng: B

Câu 07. Khi tính retrieval precision@k theo nhãn liên quan, công thức nào đúng?
A. Số tài liệu liên quan trong top-k chia cho k
B. Số tài liệu được truy xuất chia số token của câu hỏi
C. Số tài liệu trong index chia cho số tài liệu đã chọn
D. Số tài liệu liên quan trong top-k chia tổng liên quan
Đáp án đúng: A

Câu 08. Khi tính retrieval recall với tập tài liệu liên quan đã gán nhãn, mẫu số nên là gì?
A. Tổng số truy vấn người dùng trong phiên kiểm thử
B. Tổng số tài liệu mà retriever đã trả về trong top-k
C. Tổng số tài liệu liên quan trong tập tham chiếu
D. Tổng số token của các tài liệu đã nạp vào vector store
Đáp án đúng: C

Câu 09. Khi không có tài liệu đủ căn cứ trả lời một câu hỏi, hành vi nào nên được kiểm trong test RAG?
A. Model chọn một tài liệu gần nhất rồi khẳng định chắc chắn
B. Model thừa nhận thiếu căn cứ thay vì bịa chi tiết
C. Model lặp lại câu hỏi với từ khác và tự chấm đúng
D. Model tạo trích dẫn tới tài liệu không nằm trong kết quả
Đáp án đúng: B

Câu 10. Ứng dụng trả lời có trích dẫn, đánh giá nào kiểm tra citation thực sự có ích?
A. Kiểm chứng citation có định dạng URL hợp lệ về cú pháp
B. So độ dài của tên tài liệu với phần trả lời đã sinh
C. Đối chiếu từng khẳng định với đúng đoạn tài liệu dẫn
D. Đếm số đường dẫn citation mà câu trả lời đã hiển thị
Đáp án đúng: C

Câu 11. Một câu trả lời trùng đáp án tham chiếu nhưng không có căn cứ trong context truy xuất; nên đánh giá thế nào?
A. Correctness có thể đạt nhưng faithfulness có thể trượt
B. Tool accuracy chắc chắn đạt vì không phát sinh ngoại lệ
C. Faithfulness chắc chắn đạt vì đáp án cuối trùng tham chiếu
D. Retrieval recall chắc chắn đạt vì model đã trả lời đúng
Đáp án đúng: A

Câu 12. Khi fact checking một câu trả lời RAG, cách kiểm nào phù hợp?
A. Chỉ kiểm câu trả lời có đúng định dạng Markdown
B. Đối chiếu mệnh đề thực tế với nguồn có thể xác minh
C. Chỉ so số token của câu trả lời với tài liệu nguồn
D. Chỉ kiểm HTTP status của request tới chat model
Đáp án đúng: B

Câu 13. Dùng LLM làm giám khảo cho hai câu trả lời A/B; rủi ro nào cần đo khi hoán đổi thứ tự hiển thị?
A. Position bias làm kết quả phụ thuộc vị trí A/B
B. Tokenization làm mọi phép so cặp trở thành xác định
C. Vector dimension làm điểm không phụ thuộc thứ tự
D. Cache hit làm điểm lệ thuộc số lần chạy hệ thống
Đáp án đúng: A

Câu 14. Muốn kiểm độ tin cậy của điểm do LLM-as-judge chấm, bộ đối chứng nào nên dùng?
A. Mẫu có nhãn người chấm và rubric được thống nhất
B. Mẫu lấy từ tài liệu chưa chạy qua bước chunking
C. Mẫu chỉ chứa phản hồi model tự chấm điểm cao nhất
D. Mẫu không có nhãn nhưng được truy xuất rất nhanh
Đáp án đúng: A

Câu 15. Hai người chấm bất đồng về độ đúng của câu trả lời; cách xử lý nào giúp chuẩn hóa điểm?
A. Lấy nhãn của người chấm hoàn thành sớm hơn
B. Loại hết các mẫu bất đồng khỏi tập đánh giá
C. Đối chiếu rubric và phân xử mẫu có nhãn bất đồng
D. Lấy nhãn của model đang được triển khai làm chuẩn
Đáp án đúng: C

Câu 16. Khi so hai phiên bản model bằng pairwise evaluation, cách tổ chức test nào giảm thiên lệch?
A. Chạy mỗi model trên bộ câu hỏi do chính nó sinh
B. Cho một model nhiều tài liệu nguồn hơn model còn lại
C. Cho giám khảo biết phiên bản được đề xuất triển khai
D. Ẩn danh phiên bản và so trên cùng một đầu vào
Đáp án đúng: D

Câu 17. Một commit đổi prompt cần kiểm thử hồi quy chất lượng; cách đặt quality gate nào hợp lý?
A. Chặn khi điểm trên tập chuẩn giảm quá ngưỡng đã chọn
B. Chặn khi mã nguồn có thêm một dependency mới
C. Chặn khi số lượt gọi model trong test ít hơn hôm trước
D. Chặn khi prompt mới ngắn hơn prompt cũ theo ký tự
Đáp án đúng: A

Câu 18. Model sinh câu trả lời hơi khác nhau giữa các lần gọi; nên thiết kế evaluation ra sao?
A. Chọn lần trả lời có điểm tốt nhất làm kết quả cố định
B. Đổi tập kiểm thử ở mỗi lần chạy để tăng tính đa dạng
C. Giữ một phản hồi duy nhất và coi mọi điểm là ổn định
D. Chạy nhiều lượt, tổng hợp biến thiên với cùng cấu hình
Đáp án đúng: D

Câu 19. Để quy nguyên nhân thay đổi chất lượng cho prompt mới, cần cố định yếu tố nào khi so sánh?
A. Chỉ giữ số lượng request bằng nhau giữa hai phiên bản
B. Giữ số dòng log bằng nhau khi chạy hai prompt khác nhau
C. Đồng thời đổi retriever, model và bộ nhãn đánh giá
D. Giữ dataset, cấu hình model và pipeline truy xuất
Đáp án đúng: D

Câu 20. Một evaluator chấm cao vì câu trả lời lưu loát nhưng thiếu nguồn hỗ trợ; nên bổ sung kiểm tra gì?
A. Tiêu chí đo thời gian tạo kết nối tới model
B. Đo grounding tách khỏi độ trôi chảy của câu chữ
C. Tiêu chí tính số ký tự trung bình của câu trả lời
D. Tiêu chí đếm số lần API trả HTTP 200 từ model
Đáp án đúng: B

Câu 21. Trong luồng tool calling, muốn kiểm model chọn đúng công cụ, test case nên xác nhận gì?
A. Model gửi request tới tool nhanh hơn tới retriever
B. Tên tool được gọi phù hợp mục đích câu hỏi
C. Tool trả payload có kích thước nhỏ hơn câu hỏi
D. Model luôn ưu tiên tool đầu tiên trong danh sách
Đáp án đúng: B

Câu 22. Một tool nhận `orderId` và `currency`; kiểm thử điều gì để tránh gọi sai dù chọn đúng tool?
A. Kiểm kích thước vector embedding của câu hỏi
B. Kiểm tên thread đã thực thi bước gọi model
C. Kiểm độ dài response cuối mà model vừa tạo ra
D. So đối số thực tế với schema và dữ liệu yêu cầu
Đáp án đúng: D

Câu 23. Tool tra đơn hàng trả trạng thái `PENDING`; model trả `DELIVERED`; phép đánh giá nào bắt được lỗi?
A. So câu trả lời với trạng thái HTTP của ứng dụng
B. Đối chiếu câu trả lời và dữ liệu tool trong trace
C. So câu trả lời với độ trễ của request tới tool
D. So câu trả lời với số lần model gọi vector store
Đáp án đúng: B

Câu 24. Khi test một tool có tác dụng trừ tiền, thiết kế nào tránh tạo giao dịch thật và vẫn kiểm độ an toàn?
A. Gọi tool thật nhiều lần để lấy kết quả thống kê chính xác
B. Dùng tool giả và kiểm số lần gọi cùng khóa idempotency
C. Ẩn log tool để model không thấy thông tin giao dịch
D. Tăng timeout tool để test không phải tạo dữ liệu giả
Đáp án đúng: B

Câu 25. Retriever không tìm được đoạn liên quan nhưng model vẫn trả lời nghe hợp lý; bước nào giúp chẩn đoán?
A. Đo recall truy xuất và grounding câu trả lời
B. Chỉ xem tổng số document còn lưu trong vector store
C. Chỉ đo thời gian HTTP request đến response cuối
D. Chỉ so tốc độ token output giữa hai phiên bản model
Đáp án đúng: A

Câu 26. Thay đổi cách chia chunk của tài liệu; thử nghiệm nào đo tác động trực tiếp tới RAG?
A. So thời gian deploy của hai bản cập nhật vector store
B. So số byte prompt trên các query ngẫu nhiên không nhãn
C. So số lần service khởi động trong mỗi ngày làm việc
D. So mức tìm đúng evidence trên bộ query gán nhãn
Đáp án đúng: D

Câu 27. Reranker chỉ được đưa 20 ứng viên đã truy xuất; hạn chế nào cần nhớ khi đo hiệu quả?
A. Tự thêm tài liệu liên quan mới vào index trước khi xếp hạng
B. Buộc model trả một citation ngay cả khi thiếu context
C. Chuyển câu trả lời thành structured output không cần tool
D. Không tìm lại tài liệu đúng nếu thiếu trong ứng viên
Đáp án đúng: D

Câu 28. Query rewriting giúp tìm thêm thông tin nhưng có thể đổi ý nghĩa câu hỏi; metric nào nên bổ sung?
A. Chỉ đo CPU khi bước rewrite chạy trên worker
B. Chỉ đo số request kết thúc trong một lần thử
C. Đo mức giữ ý định và relevance sau rewrite
D. Chỉ đo số token giảm ở phần câu hỏi được viết lại
Đáp án đúng: C

Câu 29. Hybrid retrieval kết hợp tìm kiếm lexical và vector phù hợp vì lý do nào?
A. Kết hợp từ khóa chính xác và tương đồng ngữ nghĩa
B. Chỉ cho phép tài liệu được nhập bằng định dạng JSON
C. Giữ kết quả lexical và bỏ tất cả điểm từ vector
D. Thay thế cần thiết của đánh giá ground truth RAG
Đáp án đúng: A

Câu 30. Trace cho request RAG có các bước retrieve, rerank và chat model; cách gắn trace nào giúp tìm nút thắt?
A. Chỉ lưu tổng thời gian request và bỏ bước truy xuất
B. Ghi mỗi bước thành một trace không gắn correlation
C. Tạo span liên kết trong cùng trace để phân tách độ trễ
D. Gắn mọi span vào một request ID cố định cho cả hệ thống
Đáp án đúng: C

Câu 31. Luồng gửi tool call sang worker bất đồng bộ; để liên kết trace end-to-end nên làm gì?
A. Chỉ ghi thời gian của worker và bỏ request ID đầu vào
B. Chỉ đếm số worker đang hoạt động tại thời điểm gọi
C. Truyền trace context qua ranh giới xử lý bất đồng bộ
D. Đặt trace ID mới ở worker mà không tham chiếu span cũ
Đáp án đúng: C

Câu 32. Độ trễ p95 của chat model tăng nhưng p50 ổn định; cách diễn giải nào phù hợp?
A. Vì p50 không đổi nên người dùng không gặp chậm trễ
B. Thời gian của mọi request đều tăng bằng cùng một lượng
C. Nửa số request nhanh nhất đều chậm hơn phiên bản trước
D. Đuôi latency xấu đi ở một nhóm request
Đáp án đúng: D

Câu 33. Đối với chat streaming, chỉ số time-to-first-token phản ánh điều gì?
A. Khoảng thời gian từ yêu cầu tới toàn bộ response hoàn tất
B. Thời gian từ request đến khi nhận token đầu tiên
C. Khoảng thời gian giữa hai lần retriever tạo embeddings
D. Khoảng thời gian từ lúc startup tới request đầu tiên
Đáp án đúng: B

Câu 34. Muốn ước tính chi phí gọi chat model theo request, thông tin nào là cần thiết?
A. Số kết nối TCP mở tại thời điểm model sinh câu trả lời
B. Số tài liệu đích và số field của schema dữ liệu
C. Token đầu vào, đầu ra và đơn giá tương ứng của model
D. Số chunk trong index và thời gian build của ứng dụng
Đáp án đúng: C

Câu 35. Số request không đổi nhưng chi phí LLM tăng mạnh sau sửa prompt; nguyên nhân nào nên kiểm trước?
A. Thời gian startup worker đã tăng theo phiên bản
B. Thời gian build của ứng dụng Java đã tăng theo phiên bản
C. Số file Markdown trong repository đã tăng theo phiên bản
D. Token đầu vào/ra trung bình đã tăng sau thay đổi
Đáp án đúng: D

Câu 36. Một đợt giảm quality score trùng lúc tỷ lệ tool timeout tăng; bước điều tra nào nên làm?
A. Chỉ tăng số lần gọi model rồi so chi phí trung bình
B. Đối chiếu lỗi tool, trace và các phản hồi kém
C. Chỉ giảm logging để giảm ảnh hưởng lên CPU
D. Chỉ đổi model trước khi xem log gọi tool
Đáp án đúng: B

Câu 37. Phân bố câu hỏi production thay đổi so với tập evaluation ban đầu; rủi ro nào trực tiếp nhất?
A. Vector store sẽ tự bỏ toàn bộ embedding cũ khỏi index
B. Metric độ trễ tự biến thành tiêu chí fact checking
C. Điểm offline không còn đại diện tốt cho traffic mới
D. Điểm evaluation sẽ tự tăng nhờ lượng traffic thực tăng
Đáp án đúng: C

Câu 38. Lỗi RAG hiếm nhưng nghiêm trọng dễ bị chìm trong mẫu ngẫu nhiên; nên thiết kế giám sát mẫu thế nào?
A. Lấy mẫu theo nhóm lỗi hiếm và mức độ rủi ro
B. Chỉ chọn user có số lần truy cập nhiều nhất
C. Chỉ lấy mẫu các câu trả lời đã đạt điểm cao
D. Chỉ chọn request có độ trễ nhỏ nhất để so sánh
Đáp án đúng: A

Câu 39. Khi gắn quan sát Spring AI qua Micrometer, thuộc tính nào không nên làm tag metric tùy ý?
A. Tên loại model được dùng cho từng request
B. Tên operation như model-call hoặc retrieval
C. Nội dung prompt riêng của mỗi request người dùng
D. Trạng thái thành công hay lỗi của operation
Đáp án đúng: C

Câu 40. Khi chọn bản phát hành RAG mới, cách ra quyết định nào cân bằng mục tiêu vận hành và chất lượng?
A. Chỉ dựa vào chi phí thấp nhất bất kể độ đúng
B. Chỉ dựa vào tốc độ phản hồi ở một truy vấn đơn lẻ
C. Chỉ dựa vào điểm relevance cao nhất bất kể độ trễ
D. Đặt ngưỡng chất lượng, độ trễ p95 và chi phí
Đáp án đúng: D
