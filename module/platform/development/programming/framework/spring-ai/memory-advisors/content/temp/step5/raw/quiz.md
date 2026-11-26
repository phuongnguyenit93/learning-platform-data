Câu 1. Trong ứng dụng ChatClient gọi model nhiều lượt, ChatMemory giải quyết nhu cầu nào?
A. Ghi lại độ trễ của mọi request gửi đến provider.
B. Lưu HTTP response để bỏ qua mọi lần gọi model về sau.
C. Cung cấp lại lịch sử liên quan của hội thoại cho lượt sau.
D. Tạo vector embedding từ câu hỏi trước mỗi request.
Đáp án đúng: C

Câu 2. Vì sao cần `conversationId` riêng cho các cuộc hội thoại khi dùng ChatMemory?
A. Phân tách lịch sử để không trộn các phiên khác nhau.
B. Gắn cố định mỗi hội thoại với một model embedding.
C. Thay yêu cầu kiểm tra quyền bằng một giá trị ID.
D. Buộc mọi người dùng chia sẻ chung một vùng lịch sử.
Đáp án đúng: A

Câu 3. Với `ChatMemory` của Spring AI, cách nào lấy lại thông điệp đã lưu?
A. Gọi VectorStore để trả mọi tài liệu không có filter.
B. Truy xuất message theo `conversationId` của hội thoại.
C. Tạo lại ChatClient để model trả nguyên lịch sử.
D. Đọc HTTP header từ lượt chat vừa hoàn tất trước.
Đáp án đúng: B

Câu 4. Vai trò chính của `ChatMemoryRepository` trong Spring AI là gì?
A. Tự thay schema vector khi model embedding đổi.
B. Điều khiển token sampling của từng lượt hội thoại.
C. Cung cấp cơ chế lưu và đọc message hội thoại.
D. Xây prompt system riêng cho mọi model provider.
Đáp án đúng: C

Câu 5. `InMemoryChatMemoryRepository` thích hợp nhất với bối cảnh nào?
A. Dịch vụ phải giữ được lịch sử sau khi khởi động lại.
B. Thử nghiệm lưu lịch sử ngắn hạn trong một tiến trình.
C. Ứng dụng buộc lưu lịch sử bền vững trong PostgreSQL.
D. Hệ thống nhiều replica luôn cần chung một bộ nhớ.
Đáp án đúng: B

Câu 6. Vì sao nên dùng repository bền vững khi chạy nhiều replica ChatClient?
A. Để các replica cùng truy cập lịch sử đã lưu theo ID.
B. Để bỏ mọi lần gọi embedding model khi tìm lịch sử.
C. Để tự động cấp quyền admin cho mọi conversationId.
D. Để không còn tình huống ghi đồng thời trên cùng ID.
Đáp án đúng: A

Câu 7. `MessageWindowChatMemory` chủ yếu chọn lịch sử theo nguyên tắc nào?
A. Giữ những message có embedding giống truy vấn nhất.
B. Giữ những message có số token bằng nhau trong bộ nhớ.
C. Giữ toàn bộ message thuộc tất cả các conversationId.
D. Giữ một cửa sổ thông điệp gần đây của hội thoại.
Đáp án đúng: D

Câu 8. Khi cấu hình `maxMessages` cho bộ nhớ cửa sổ, hiểu đúng là gì?
A. Giới hạn số kết quả gần nhất khi gọi VectorStore.
B. Giới hạn số token prompt do model xử lý mỗi lượt.
C. Giới hạn số phiên ChatClient chạy trên một instance.
D. Giới hạn số thông điệp, không trực tiếp số token.
Đáp án đúng: D

Câu 9. `MessageChatMemoryAdvisor` thường tích hợp lịch sử vào lời gọi model ra sao?
A. Nạp các message hội thoại vào request gửi đến model.
B. Chuyển lịch sử thành token xác thực trên HTTP header.
C. Biên dịch message thành schema của repository lưu trữ.
D. Gắn lịch sử vào metadata của PGvector ngay lúc hỏi.
Đáp án đúng: A

Câu 10. `PromptChatMemoryAdvisor` khác `MessageChatMemoryAdvisor` ở điểm nào?
A. Thay ChatModel bằng một EmbeddingModel khi sinh đáp án.
B. Thay lịch sử bằng một HTTP cache key cố định của chat.
C. Chèn lịch sử vào văn bản prompt thay vì message riêng.
D. Tự dùng VectorStore cho mọi lịch sử có nhiều message.
Đáp án đúng: C

Câu 11. Muốn ChatClient sử dụng ChatMemory trong các lượt gọi, làm gì phù hợp?
A. Chỉ đặt tên một biến trong controller là `chatMemory`.
B. Chỉ trả cookie của phiên qua HTTP response của server.
C. Tăng context window bên model mà không lưu lịch sử.
D. Gắn memory advisor vào chuỗi advisor của ChatClient.
Đáp án đúng: D

Câu 12. Vì sao các lượt cùng cuộc hội thoại phải truyền đúng `conversationId`?
A. Để ChatClient đổi ngẫu nhiên model provider khi gọi API.
B. Để EmbeddingModel tăng số chiều vector ở lượt kế tiếp.
C. Để database thay toàn bộ message role bằng tên người dùng.
D. Để advisor nạp và ghi đúng lịch sử của cuộc hội thoại.
Đáp án đúng: D

Câu 13. ChatClient dùng chung cho nhiều người dùng; cách bảo vệ lịch sử nào đúng?
A. Tin mọi conversationId client gửi mà không kiểm tra sở hữu.
B. Chỉ phân tách dữ liệu bằng tên model được cấu hình.
C. Ánh xạ danh tính đã xác thực vào conversationId được phép.
D. Cho các request dùng một conversationId cố định cho nhanh.
Đáp án đúng: C

Câu 14. Vì sao chỉ biết `conversationId` chưa đủ để được đọc lịch sử?
A. ID tự thay thế mọi bước xác thực danh tính ở server.
B. ID chỉ hợp lệ khi toàn bộ ký tự đều là chữ số ngẫu nhiên.
C. ID làm cho message luôn được mã hóa khi lưu repository.
D. ID nhận diện hội thoại, ứng dụng vẫn phải kiểm tra quyền.
Đáp án đúng: D

Câu 15. Hai request ghi cùng lịch sử hội thoại đồng thời có thể dẫn đến gì?
A. Repository bắt buộc tuần tự hóa mọi lần ghi theo thời gian.
B. Mất cập nhật hoặc các message bị xếp thứ tự sai.
C. VectorStore tự xóa metadata của cuộc hội thoại đó.
D. Model tự hủy tất cả token trả về cho cả hai request.
Đáp án đúng: B

Câu 16. Để giảm xung đột khi ghi cùng `conversationId`, cách nào phù hợp?
A. Tuần tự hóa cập nhật hoặc kiểm tra phiên bản ghi.
B. Chỉ ghi lịch sử sau khi mọi phiên khác đã bị xóa.
C. Tăng maxMessages và bỏ mọi transaction ở database.
D. Giảm temperature của model để bảo đảm thứ tự cập nhật.
Đáp án đúng: A

Câu 17. Khi người dùng yêu cầu xóa toàn bộ lịch sử của họ, cần làm gì?
A. Chỉ xóa đoạn prompt của lượt tiếp theo rồi giữ vector.
B. Xóa các bản ghi liên quan trong mọi kho thuộc phạm vi.
C. Đổi tên conversationId nhưng giữ các bản ghi cũ.
D. Chỉ ẩn lịch sử khỏi giao diện mà giữ dữ liệu lưu trữ.
Đáp án đúng: B

Câu 18. Thiết lập thời hạn lưu trữ dữ liệu hội thoại nhằm mục đích gì?
A. Giảm số chiều embedding của các message đã lưu.
B. Giảm lưu giữ quá hạn và chi phí lưu trữ dữ liệu.
C. Tăng độ chính xác tuyệt đối của mọi câu trả lời model.
D. Thay thế hoàn toàn quyền truy cập đến repository.
Đáp án đúng: B

Câu 19. Trước khi ghi chat memory có thông tin mật, kiểm soát nào phù hợp?
A. Phân loại và loại bỏ hoặc che dữ liệu nhạy cảm.
B. Chuyển mật khẩu vào system prompt của hội thoại.
C. Đảo thứ tự message trước khi ghi xuống database.
D. Lưu nguyên access token để tiện kiểm tra ở lượt sau.
Đáp án đúng: A

Câu 20. Với lịch sử chứa thông tin cá nhân, cần áp dụng biện pháp nào?
A. Chỉ cắt message ở dấu xuống dòng đầu tiên.
B. Chuyển độ đo similarity thành cosine trong VectorStore.
C. Đặt chung một conversationId cho mọi tenant của app.
D. Giới hạn quyền, mã hóa và quy định thời hạn lưu.
Đáp án đúng: D

Câu 21. Khác biệt chính giữa memory cửa sổ và memory ngữ nghĩa là gì?
A. Cả hai phải quét toàn bộ document bằng SQL mỗi lượt.
B. Cả hai bắt buộc giữ đúng một message gần nhất.
C. Cửa sổ chỉ dùng embedding; ngữ nghĩa không dùng vector.
D. Cửa sổ ưu tiên mới nhất; ngữ nghĩa ưu tiên liên quan.
Đáp án đúng: D

Câu 22. Khi tìm semantic memory bằng VectorStore, đầu vào truy vấn cần gì?
A. Một chunk có cùng document ID cho mọi cuộc hội thoại.
B. Tên PostgreSQL schema mới gắn với conversationId.
C. Embedding của truy vấn cùng không gian với dữ liệu lưu.
D. Một HTTP status code được đổi từ similarity score.
Đáp án đúng: C

Câu 23. Muốn semantic memory không trả dữ liệu tenant khác, cách nào đúng?
A. Xóa tenant ID khỏi tất cả metadata trước khi query.
B. Tăng topK để ký ức đúng tenant có cơ hội xuất hiện.
C. Đổi temperature của ChatModel để tự tách tenant.
D. Áp metadata filter theo tenant từ phía server đã xác thực.
Đáp án đúng: D

Câu 24. Trong tìm kiếm semantic memory, cấu hình `topK` điều chỉnh điều gì?
A. Số message tối đa repository được phép ghi mỗi phiên.
B. Số ký ức gần nhất tối đa được lấy vào ngữ cảnh.
C. Số connection tối đa PostgreSQL có thể mở cùng lúc.
D. Số lần model chat được tự động thử lại khi lỗi.
Đáp án đúng: B

Câu 25. Nếu ký ức cũ mâu thuẫn với dữ liệu mới, giải pháp nào phù hợp?
A. Luôn ưu tiên ký ức cũ vì có thời gian tồn tại dài hơn.
B. Ưu tiên nguồn có thẩm quyền và phiên bản mới phù hợp.
C. Giữ cả hai như kết luận chắc chắn mà không cảnh báo.
D. Xóa mọi cuộc hội thoại khác để tránh sai lệch ký ức.
Đáp án đúng: B

Câu 26. Vì sao không nên đưa mọi ký ức tìm được vào prompt mỗi lượt?
A. Vì VectorStore luôn buộc trả chính xác một message.
B. Vì metadata không bao giờ được phép xuất hiện trong prompt.
C. Có thể tốn token và đưa vào thông tin không liên quan.
D. Vì EmbeddingModel luôn tự xóa chunk sau mỗi lần tìm.
Đáp án đúng: C

Câu 27. Khi người dùng yêu cầu quên dữ liệu đã nhúng, nên xử lý thế nào?
A. Xóa record vector liên quan và bản sao được quản lý.
B. Chỉ xóa cửa sổ chat, giữ vector từng lưu để tái dùng.
C. Đặt topK về không trong toàn bộ truy vấn của user.
D. Đổi metadata nhưng không xóa nội dung vector cũ.
Đáp án đúng: A

Câu 28. Muốn đánh giá chất lượng truy xuất semantic memory, nên kiểm thử gì?
A. Chỉ theo dõi RAM khi repository khởi động lần đầu.
B. Chỉ tăng message lưu rồi đánh giá câu trả lời dài hơn.
C. Truy vấn có nhãn liên quan và các metric retrieval.
D. Chỉ so số ký tự trong conversationId giữa các phiên.
Đáp án đúng: C

Câu 29. Chi phí token tăng khi hội thoại kéo dài; cách tối ưu nào phù hợp?
A. Đính kèm tất cả lịch sử để không mất chút ngữ cảnh nào.
B. Giới hạn lịch sử, tóm tắt chọn lọc và đo token.
C. Luôn lưu lại bản sao mọi request trực tiếp vào prompt.
D. Tăng topK mà không kiểm tra độ dài ngữ cảnh thực tế.
Đáp án đúng: B

Câu 30. Khi lịch sử dài hơn context window của ChatModel, nên làm gì?
A. Cắt hoặc tóm tắt có kiểm soát, giữ phần liên quan.
B. Tin provider luôn tiếp nhận message vượt giới hạn token.
C. Tăng replica database để model có thêm context window.
D. Bỏ metadata filter để đưa thêm tất cả ký ức vào prompt.
Đáp án đúng: A

Câu 31. Khi kiểm thử memory advisor, cần xác minh gì giữa hai cuộc hội thoại?
A. Phiên mới đọc được message của mọi phiên trước trên server.
B. Chỉ đo thời gian startup của repository lưu lịch sử.
C. Mỗi phiên chỉ nạp lịch sử thuộc conversationId của mình.
D. Chỉ kiểm tra HTTP status mà bỏ qua nội dung prompt.
Đáp án đúng: C

Câu 32. Muốn tìm nguyên nhân memory advisor làm prompt dài, theo dõi gì?
A. Số token đầu vào, message được nạp và latency.
B. Chỉ số lượng bean Spring khi application khởi động.
C. Chỉ phiên bản Java và kích thước file artifact build.
D. Chỉ tên bảng lưu trữ mà không đo token hoặc thời gian.
Đáp án đúng: A
