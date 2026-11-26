Câu 1. Khi dùng ChatModel.call(Prompt), kết quả trả về thuộc kiểu nào?
A. Flux<ChatResponse> phát các phần khi stream
B. String là nội dung do content() lấy ra
C. Prompt là cấu trúc message sau khi xử lý
D. ChatResponse chứa kết quả sinh và metadata
Đáp án đúng: D

Câu 2. Vai trò cốt lõi của ChatModel trong Spring AI là gì?
A. Cung cấp API riêng để tạo embedding vector
B. Cung cấp API chung để gọi mô hình chat
C. Cung cấp API quản lý chat history trong DB
D. Cung cấp API thay thế cơ chế prompt template
Đáp án đúng: B

Câu 3. ChatClient bổ sung điều gì so với gọi ChatModel trực tiếp?
A. Một bộ lưu hội thoại bắt buộc cho mọi request
B. Một mô hình tạo embedding thay cho chat model
C. Fluent API để xây prompt và lấy kết quả
D. Một bộ phân tích schema JSON không cần model
Đáp án đúng: C

Câu 4. Trong ChatClient, user("...") khi dựng prompt biểu diễn gì?
A. Một thông điệp vai trò user gửi tới model
B. Một system message đặt quy tắc chung cho model
C. Một assistant message mô phỏng câu trả lời
D. Một tool message thể hiện kết quả công cụ
Đáp án đúng: A

Câu 5. Trong ChatClient, call().content() phù hợp khi cần gì?
A. Lấy text phản hồi sau khi lời gọi hoàn tất
B. Lấy Flux<String> từ phiên streaming đang chạy
C. Lấy Prompt chứa các message đã gửi đi
D. Lấy bản ghi usage cho mọi lượt gọi trước
Đáp án đúng: A

Câu 6. ChatClient.call().chatResponse() khác content() ở điểm nào?
A. Trả Mono<String> thay vì một kết quả hoàn tất
B. Trả ChatResponse thay vì chỉ nội dung text
C. Trả PromptTemplate thay vì thông điệp hoàn chỉnh
D. Trả ChatMemory thay vì phản hồi của model
Đáp án đúng: B

Câu 7. Trong ChatResponse, metadata được dùng để làm gì?
A. Mang toàn bộ lịch sử hội thoại của người dùng
B. Giữ các biến template chưa được thay vào prompt
C. Mang thông tin về lượt sinh như usage nếu có
D. Giữ API key để tái sử dụng ở lần gọi tiếp
Đáp án đúng: C

Câu 8. Mục đích của các role trong danh sách message là gì?
A. Phân biệt từng bean ChatClient theo tên provider
B. Phân biệt token đầu vào với token đầu ra
C. Phân biệt đồng hồ streaming và đồng hồ timeout
D. Phân biệt system, user và các vai trò hội thoại
Đáp án đúng: D

Câu 9. Để chỉ dẫn chung về phong cách trả lời, message nào phù hợp?
A. System message chứa quy tắc cho hội thoại
B. User message chứa câu hỏi mới nhất từ client
C. Assistant message chứa câu trả lời đã được tạo
D. Tool message chứa kết quả gọi công cụ bên ngoài
Đáp án đúng: A

Câu 10. Khi đưa câu hỏi thực tế của người dùng vào prompt, nên dùng gì?
A. User message cho nội dung người dùng gửi
B. System message để thay thông tin role của client
C. Assistant message thay cho dữ liệu từ người dùng
D. Tool message để giả lập câu trả lời của model
Đáp án đúng: A

Câu 11. PromptTemplate trong Spring AI chủ yếu dùng làm gì?
A. Chuyển prompt thành embedding mặc định
B. Thay placeholder bằng biến để tạo prompt
C. Lưu các prompt đã sử dụng vào chat memory
D. Chạy prompt trực tiếp mà không cần chat model
Đáp án đúng: B

Câu 12. Khi xây PromptTemplate với nhiều biến, cần làm gì?
A. Chỉ đặt temperature là template tự điền biến
B. Gửi request rỗng cho model để suy ra mọi biến
C. Truyền đúng giá trị cho placeholder cần thay
D. Dùng token usage thay giá trị của placeholder
Đáp án đúng: C

Câu 13. Vì sao PromptTemplate không tự chặn prompt injection?
A. Placeholder luôn được kiểm tra quyền theo role
B. Giá trị biến vẫn có thể chứa chỉ dẫn độc hại
C. Template tự ký số và xác thực mọi nội dung
D. Model tự bỏ qua instruction trong dữ liệu nhập
Đáp án đúng: B

Câu 14. ChatOptions thường chứa nhóm cấu hình nào?
A. Danh sách message role của toàn bộ prompt
B. Trạng thái session và nội dung chat memory
C. Đối tượng ChatResponse được sinh ở lần trước
D. Thông số sinh như temperature và token limit
Đáp án đúng: D

Câu 15. Khi giảm temperature đối với model hỗ trợ, thường kỳ vọng gì?
A. Giới hạn input token luôn giảm tương ứng
B. Model tự bảo đảm không còn mọi hallucination
C. Phân phối đầu ra bớt ngẫu nhiên hơn
D. Kết quả luôn giống hệt qua mọi lần gọi
Đáp án đúng: C

Câu 16. Giới hạn max output tokens nên được hiểu là gì?
A. Giới hạn số token có thể được sinh ra
B. Giới hạn số message được lưu vào chat history
C. Giới hạn số request gửi song song cho provider
D. Giới hạn số biến được đưa vào PromptTemplate
Đáp án đúng: A

Câu 17. Khi chuyển provider cho cùng ứng dụng, nên xác minh điều gì?
A. Tất cả tham số đều luôn tương đương tuyệt đối
B. Chỉ tên model cần đổi, test contract không cần
C. Khả năng hỗ trợ model, option và định dạng output
D. Mọi provider luôn cung cấp cùng token metadata
Đáp án đúng: C

Câu 18. Khi cần đầu vào hình ảnh, model được chọn phải có gì?
A. Khả năng xuất ra JSON với schema do client chọn
B. Khả năng lưu embedding cho mỗi tài khoản
C. Model phải hỗ trợ đọc ảnh ở loại input được gửi
D. Khả năng tăng temperature với mọi loại prompt
Đáp án đúng: C

Câu 19. Khóa API nhà cung cấp nên được lưu và cấp qua đâu?
A. Chuỗi hardcode trong lớp Java gọi ChatClient
B. Secret manager và cấu hình bảo mật môi trường
C. Nội dung system prompt để tái sử dụng về sau
D. Query string của endpoint ứng dụng công khai
Đáp án đúng: B

Câu 20. Nếu provider trả lỗi rate-limit, chính sách nào phù hợp?
A. Retry vô hạn liên tục để token quota tự hồi phục
B. Gửi đồng thời nhiều bản request để vượt hạn mức
C. Retry hữu hạn có backoff và tôn trọng tín hiệu chờ
D. Coi response bị từ chối như một output hợp lệ
Đáp án đúng: C

Câu 21. Khi model không phản hồi trong deadline, ứng dụng nên làm gì?
A. Áp dụng timeout và trả lỗi hoặc fallback rõ ràng
B. Bỏ timeout vì mô hình luôn hoàn tất sau cùng
C. Mở thêm request tương tự mà không kiểm soát retry
D. Dùng temperature thấp để chắc chắn hết timeout
Đáp án đúng: A

Câu 22. Temperature bằng 0 có đảm bảo cùng một output qua mọi lần không?
A. Không; kết quả có thể đổi theo model và version
B. Có; kết quả luôn bất biến qua mọi provider và version
C. Có; output được lưu cache trên provider mặc định
D. Không; model sẽ tự chuyển sang kết quả streaming
Đáp án đúng: A

Câu 23. Trong ChatClient, stream().content() có dạng kết quả nào?
A. String chứa toàn văn sau khi gọi kết thúc
B. Flux<String> phát dần từng đoạn nội dung
C. ChatResponse chứa kết quả và usage một lần
D. PromptTemplate chứa tham số của template đầu vào
Đáp án đúng: B

Câu 24. Khi hiển thị kết quả streaming trên giao diện, cần nhớ gì?
A. Mỗi chunk luôn là một câu hoàn chỉnh đã chấm dứt
B. Mỗi chunk luôn chứa một JSON object độc lập
C. Mỗi chunk luôn tương ứng đúng một token nội bộ
D. Chunk có thể là một phần của câu đang sinh
Đáp án đúng: D

Câu 25. Khi phía client hủy luồng streaming, server nên xử lý gì?
A. Lan truyền cancel và thu dọn tài nguyên liên quan
B. Tiếp tục giữ stream mở để chắc chắn model hoàn tất
C. Phát lại toàn bộ prompt để client nhận dữ liệu sau
D. Giữ vô hạn chunk cũ trong RAM cho lần kết nối mới
Đáp án đúng: A

Câu 26. Khi stream trả lỗi sau một số chunk, cách phản hồi nào đúng?
A. Coi các chunk đã nhận là câu trả lời đã hoàn tất
B. Tự nối một dấu kết thúc và bỏ qua lỗi của provider
C. Báo kết quả còn dang dở và trạng thái lỗi
D. Luôn trả thành công vì stream từng phát được data
Đáp án đúng: C

Câu 27. Trong ChatClient, entity(MyDto.class) được dùng nhằm mục đích gì?
A. Ghi trực tiếp DTO trả về vào bảng database tương ứng
B. Ánh xạ nội dung model trả về sang đối tượng DTO
C. Chuyển class DTO thành các vector embedding
D. Tạo controller REST mới dựa trên các trường DTO
Đáp án đúng: B

Câu 28. Khi model được yêu cầu trả JSON, điều gì vẫn có thể xảy ra?
A. Mọi phản hồi đều khớp schema với mọi provider
B. Dữ liệu luôn đúng nghiệp vụ vì JSON parse được
C. Dữ liệu có thể sai schema dù có chỉ dẫn format
D. Model không bao giờ trả thông tin ngoài schema
Đáp án đúng: C

Câu 29. Sau khi ánh xạ output sang DTO thành công, nên làm gì?
A. Bỏ bước kiểm tra vì việc parse đã đủ bảo đảm
B. Lưu DB ngay cả khi dữ liệu vượt quyền người dùng
C. Tin tất cả giá trị do model sinh như dữ kiện thật
D. Validate field và logic nghiệp vụ trước khi dùng
Đáp án đúng: D

Câu 30. Khi phản hồi không parse được sang DTO, cách xử lý nào hợp lý?
A. Gán ngẫu nhiên các trường bắt buộc còn thiếu
B. Báo lỗi có kiểm soát hoặc retry có giới hạn
C. Bỏ qua mọi lỗi parse để trả DTO đã tạo một phần
D. Tự chuyển dữ liệu sai thành transaction hợp lệ
Đáp án đúng: B

Câu 31. Structured output dạng native của provider cần lưu ý gì?
A. Mọi provider thực thi giống nhau không cần test
B. Cấu hình native luôn bảo đảm nội dung chính xác
C. Việc tuân thủ schema còn tùy model và provider
D. JSON mode của provider luôn là luật nghiệp vụ
Đáp án đúng: C

Câu 32. Khi đưa ảnh và text vào yêu cầu chat, cần làm gì?
A. Chuyển toàn bộ ảnh thành thuộc tính của ChatOptions
B. Ghi ảnh trực tiếp vào ChatResponse trước khi call
C. Lưu ảnh vào ChatMemory mà không gửi đến model
D. Tạo message có nội dung văn bản và media phù hợp
Đáp án đúng: D

Câu 33. Để request ảnh được model xử lý, yêu cầu nào quan trọng?
A. Model cần hỗ trợ loại media ảnh của request
B. Chỉ cần có MIME type mà model bất kỳ đều hiểu
C. Chỉ cần dùng streaming là model đọc được hình
D. Chỉ cần bọc URL ảnh vào system prompt là đủ
Đáp án đúng: A

Câu 34. Khi nhận ảnh người dùng tải lên, kiểm tra nào nên có?
A. Chỉ dựa vào tên file để quyết định dữ liệu an toàn
B. Tự tin rằng model sẽ chặn mọi file nguy hiểm
C. Giữ mọi file trong log để thuận tiện chẩn đoán
D. Kiểm tra loại media, kích thước và quyền truy cập
Đáp án đúng: D

Câu 35. Nếu ảnh có dữ liệu nhạy cảm, trước khi gọi provider nên làm gì?
A. Luôn gửi ảnh gốc để provider tự lọc thông tin
B. Đặt ảnh trong URL công khai để model dễ tải
C. Ghi toàn bộ ảnh vào trace để dễ kiểm tra phản hồi
D. Chỉ gửi phần cần thiết và che nội dung nhạy cảm
Đáp án đúng: D

Câu 36. Một ChatClient có mặc định ghi nhớ nội dung mọi lần gọi trước không?
A. Không, cần đưa history hoặc cấu hình chat memory
B. Có, framework tự lưu toàn bộ session vào DB
C. Có, model nhớ được mọi request qua ID bean
D. Không, history không bao giờ dùng được với model
Đáp án đúng: A

Câu 37. Khi hội thoại kéo dài, giới hạn nào thường ảnh hưởng đến prompt?
A. Số lượng @Component của ứng dụng Spring Boot
B. Độ dài tên method được viết trong ChatClient
C. Số hàng trong bảng quan hệ lưu thông tin user
D. Giới hạn context window và token history
Đáp án đúng: D

Câu 38. Khi đưa tài liệu ngoài vào prompt, ranh giới tin cậy nào đúng?
A. Xem nội dung trích xuất là system message mới
B. Tin yêu cầu quyền truy cập ghi trong tài liệu
C. Bỏ kiểm tra injection vì tài liệu có metadata
D. Xem tài liệu là dữ liệu, không phải lệnh system
Đáp án đúng: D

Câu 39. Khi model gợi ý hành động gây side effect, ứng dụng nên làm gì?
A. Thực thi mọi lệnh nếu có trong ChatResponse
B. Kiểm soát hành động bằng quyền và quy tắc server
C. Dùng nội dung model làm bằng chứng đã phân quyền
D. Mở quyền tool mặc định cho mọi user có prompt
Đáp án đúng: B

Câu 40. Khi model yêu cầu đọc dữ liệu của tài khoản khác, cần gì?
A. Tin account ID vì nó có trong output của model
B. Tin tài liệu truy xuất được vì model đã phân tích
C. Kiểm tra quyền principal với dữ liệu được hỏi
D. Bỏ xác thực nếu prompt có system message tin cậy
Đáp án đúng: C

Câu 41. Để hạn chế lộ PII khi gọi dịch vụ AI, nên áp dụng gì?
A. Gửi toàn bộ thông tin khách hàng cho mỗi prompt
B. Lưu đầy đủ prompt nhạy cảm trong log chung
C. Truyền dữ liệu cá nhân qua query string public
D. Tối thiểu hóa dữ liệu và che trường cần bảo vệ
Đáp án đúng: D

Câu 42. Nếu cần log lỗi khi gọi provider, cách nào tốt hơn?
A. Lưu mã lỗi và trace ID, tránh ghi secret và PII
B. Log toàn bộ access token để dễ thử lại request
C. Log đầy đủ ảnh gốc và prompt không cần kiểm tra
D. Tắt mọi correlation ID để giảm chi phí lưu log
Đáp án đúng: A

Câu 43. Khi test ChatClient với output không tất định, nên ưu tiên gì?
A. So khớp nguyên văn một câu trả lời duy nhất
B. Kiểm thử hợp đồng và các tiêu chí ngữ nghĩa
C. Chỉ xác minh HTTP 200 mà không xem nội dung
D. Bỏ toàn bộ test vì không thể biết output trước
Đáp án đúng: B

Câu 44. Để unit test không gọi provider AI thật, cách nào phù hợp?
A. Gọi API thật lặp nhiều lần rồi chọn một kết quả
B. Đưa token provider thật vào source test để ổn định
C. Dùng test double ChatModel tạo phản hồi kiểm soát
D. Tắt hoàn toàn kiểm thử cho những service gọi model
Đáp án đúng: C

Câu 45. Khi integration test kết nối provider thật, cần đặc biệt kiểm tra gì?
A. Bỏ mọi timeout để bài test luôn nhận được output
B. Timeout, lỗi provider và kiểm soát chi phí gọi API
C. Khẳng định mọi model luôn sinh đúng một chuỗi text
D. Coi thay đổi version model không liên quan đến test
Đáp án đúng: B

Câu 46. Để theo dõi chất lượng vận hành model, nên chọn metric nào?
A. Độ trễ, lỗi, token usage và chất lượng đầu ra
B. Chỉ số bean Spring tạo trong một lần khởi động
C. Số lượng controller dùng cùng một ChatClient
D. Tổng số trường được khai báo ở các lớp DTO
Đáp án đúng: A

Câu 47. ChatResponse metadata có lưu ý nào khi dùng đa provider?
A. Token usage luôn được đo giống nhau trên mọi model
B. Response metadata luôn chứa toàn bộ prompt gốc
C. Metadata luôn bảo đảm câu trả lời đã được xác thực
D. Usage có thể thiếu hoặc khác nhau theo provider
Đáp án đúng: D

Câu 48. Khi ứng dụng tự retry bước có side effect sau lời gọi AI, cần gì?
A. Tạo transaction mới cho từng retry không cần kiểm tra
B. Dùng idempotency key để tránh ghi lặp nghiệp vụ
C. Đặt temperature thấp để không xảy ra tác dụng phụ
D. Tự coi mọi thao tác ghi bên ngoài là idempotent
Đáp án đúng: B
