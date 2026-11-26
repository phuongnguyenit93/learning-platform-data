Câu 1. Embedding văn bản phục vụ tìm kiếm ngữ nghĩa nhằm mục đích gì?
A. Biểu diễn nội dung thành ID để nối nhiều bảng dữ liệu.
B. Biểu diễn nội dung thành vector để so sánh ý nghĩa.
C. Biểu diễn nội dung thành token để tìm nguyên văn.
D. Biểu diễn nội dung thành schema để kiểm kiểu.
Đáp án đúng: B

Câu 2. Trong Spring AI, `EmbeddingModel` đảm nhận nhiệm vụ chính nào?
A. Tạo vector số biểu diễn nội dung được cung cấp.
B. Sắp xếp các kết quả từ bộ lọc metadata riêng.
C. Đánh chỉ mục HNSW cho bảng PostgreSQL đang dùng.
D. Tự gộp các đoạn tài liệu trước khi lưu database.
Đáp án đúng: A

Câu 3. Khi ghi embedding vào cột `vector(n)` của PGvector, điều gì cần khớp?
A. Số chiều embedding phải tương thích với giá trị n.
B. Số trường metadata phải khớp số chiều của cột.
C. Số kết quả topK phải bằng số chiều của vector.
D. Số token của văn bản phải đúng bằng số chiều của cột.
Đáp án đúng: A

Câu 4. Muốn so sánh vector truy vấn và tài liệu một cách hợp lệ, nên làm gì?
A. Dùng hai tokenizer bất kỳ miễn là chunk đủ ngắn.
B. Dùng hai kho vector khác nhau nhưng chung tên bảng.
C. Dùng hai mô hình khác nhau nhưng cùng tên trường.
D. Dùng mô hình embedding tương thích cho hai phía.
Đáp án đúng: D

Câu 5. Đối tượng `Document` trong Spring AI thường giúp lưu thông tin gì?
A. Lưu toàn bộ câu trả lời do LLM tạo ra trước đó.
B. Nội dung tài liệu cùng metadata phục vụ truy xuất.
C. Chỉ vector đã chuẩn hóa, không giữ nội dung tài liệu nguồn.
D. Chỉ định cấu hình mạng của embedding provider.
Đáp án đúng: B

Câu 6. Khi gọi `VectorStore.add(List<Document>)`, thao tác dự kiến là gì?
A. Chuyển tất cả tài liệu thành SQL bảng thông thường.
B. Chỉ đo độ trễ của mỗi tài liệu mà không ghi gì.
C. Chỉ tìm các chunk đã lưu gần nội dung đầu vào.
D. Tạo embedding và lưu các tài liệu vào vector store.
Đáp án đúng: D

Câu 7. Trong Spring AI, `similaritySearch` thường trả về dữ liệu nào?
A. Các row sắp theo ID tạo mới trong PostgreSQL.
B. Các bảng index gần nhất với connection hiện tại.
C. Các `Document` phù hợp với truy vấn ngữ nghĩa.
D. Các đoạn raw có số ký tự bằng văn bản truy vấn.
Đáp án đúng: C

Câu 8. `topK` trong yêu cầu tìm kiếm vector dùng để điều chỉnh gì?
A. Số kết quả gần nhất tối đa cần trả về cho client.
B. Số lần thử lại khi model embedding timeout.
C. Số chiều của embedding được sinh cho truy vấn.
D. Số lượng connection database được mở đồng thời.
Đáp án đúng: A

Câu 9. Tăng ngưỡng similarity trong một truy vấn có thể gây hệ quả nào?
A. Ít kết quả qua ngưỡng hơn, nhưng tập kết quả sát hơn.
B. Ép PGvector luôn trả về đúng topK kể cả điểm rất thấp.
C. Giảm thời gian tạo embedding cho các văn bản dài hơn.
D. Tăng tự động số chiều vector của mọi Document đã lưu.
Đáp án đúng: A

Câu 10. Khi so sánh điểm truy xuất giữa hai VectorStore khác metric, cần lưu ý gì?
A. Chỉ cần đổi `topK` để mọi score trở thành đồng nhất.
B. Không nên so trực tiếp score nếu thang đo khác nhau.
C. Có thể coi mọi distance nhỏ đều là similarity lớn.
D. Có thể dùng chung threshold dù metric và chuẩn hóa đổi.
Đáp án đúng: B

Câu 11. Với cosine similarity giữa hai vector khác không, đặc điểm nào đúng?
A. Đo sai khác từng tọa độ như khoảng cách Euclid.
B. Chỉ kiểm tra số chiều bằng nhau mà không xét giá trị.
C. Ưu tiên tuyệt đối vector có độ dài Euclid lớn nhất.
D. Đo độ gần hướng của vector, không phụ thuộc độ lớn.
Đáp án đúng: D

Câu 12. Điểm mạnh của tìm kiếm ngữ nghĩa so với dò từ khóa thuần là gì?
A. Chỉ tìm tài liệu có đúng độ dài như truy vấn đầu vào.
B. Chỉ tìm tài liệu có cùng chuỗi ký tự như câu hỏi.
C. Chỉ tìm tài liệu có cùng vị trí từ trong từng câu.
D. Có thể tìm tài liệu đồng nghĩa dù ít từ trùng khớp.
Đáp án đúng: D

Câu 13. Nếu chunk quá nhỏ khi lập chỉ mục văn bản, rủi ro chính là gì?
A. Thiếu bối cảnh để xác định nội dung câu trả lời.
B. Buộc PGvector dùng index chính thay vì index phụ.
C. Tăng số chiều embedding dù không đổi mô hình.
D. Ép mọi lần tìm kiếm phải quét tuần tự toàn bảng.
Đáp án đúng: A

Câu 14. Nếu chunk quá dài và chứa nhiều chủ đề, hệ quả nào có thể xảy ra?
A. Embedding tự thay đổi số chiều theo số lượng câu.
B. PGvector không thể lưu các vector được chuẩn hóa.
C. Kết quả truy xuất kém tập trung vào một ý cụ thể.
D. Bộ lọc metadata bị vô hiệu hóa trên các document.
Đáp án đúng: C

Câu 15. Cho phép overlap giữa các chunk nhằm cân bằng điều gì?
A. Tạo ra số chiều vector cao hơn cho mỗi chunk sau.
B. Loại bỏ toàn bộ đoạn trùng để giảm số vector lưu.
C. Đảm bảo kết quả tìm được không cần kiểm tra nguồn.
D. Giữ bối cảnh ở ranh giới nhưng tăng lượng token.
Đáp án đúng: D

Câu 16. Trong xử lý tài liệu, `TokenTextSplitter` được dùng cho việc gì?
A. Chia kết quả theo nhãn do PGvector tự suy luận.
B. Chia văn bản thành các đoạn theo ngân sách token.
C. Chia request ra nhiều kết nối tới vector database.
D. Chia dữ liệu thành nhiều bảng theo ID PostgreSQL.
Đáp án đúng: B

Câu 17. Metadata gắn với chunk hữu ích nhất cho tình huống nào?
A. Thay embedding bằng điểm similarity lưu sẵn.
B. Lưu mã tài liệu và trang để dẫn nguồn và lọc kết quả.
C. Thay truy vấn tìm kiếm bằng mã giao dịch SQL trong kho.
D. Ghi mật khẩu kết nối provider theo từng chunk.
Đáp án đúng: B

Câu 18. Bộ lọc metadata trong tìm kiếm VectorStore thường có tác dụng nào?
A. Chỉ trả tài liệu thỏa điều kiện thuộc tính đã chọn.
B. Chuyển mọi điểm khoảng cách thành HTTP status.
C. Thay model embedding bằng bộ đếm tần suất từ.
D. Tự thay schema của bảng vector theo từng truy vấn tìm kiếm.
Đáp án đúng: A

Câu 19. Trong hệ thống nhiều tenant, giới hạn truy xuất vector nên triển khai ra sao?
A. Tin tham số tenant do client gửi mà không kiểm tra.
B. Chỉ ẩn tenant ID trong kết quả trả về cho client.
C. Áp tenant filter phía server từ danh tính xác thực.
D. Chỉ dùng tên collection chung để tránh lọc truy cập.
Đáp án đúng: C

Câu 20. PGvector trong PostgreSQL cung cấp thành phần chính nào?
A. Chức năng tự động tạo chunk từ mọi cột văn bản.
B. Trình chạy model embedding tích hợp bên trong SQL.
C. Kiểu dữ liệu vector và toán tử tìm tương đồng.
D. Thành phần thay thế toàn bộ transaction PostgreSQL.
Đáp án đúng: C

Câu 21. Index HNSW trong PGvector có đánh đổi kỹ thuật nào?
A. Tăng tốc truy xuất gần đúng nhưng tốn công index.
B. Cho kết quả chính xác tuyệt đối mà không tốn RAM.
C. Đảm bảo mọi truy vấn luôn đọc đủ mọi row dữ liệu.
D. Bỏ nhu cầu tính embedding cho tài liệu mới chèn.
Đáp án đúng: A

Câu 22. Khi tăng tham số search effort của ANN index, xu hướng nào thường đúng?
A. Thời gian tính embedding bằng model sẽ bằng không.
B. Recall luôn giảm ngay cả khi tài nguyên không đổi.
C. Recall có thể tốt hơn nhưng độ trễ truy vấn tăng.
D. Số chiều embedding tự tăng theo số lần truy vấn.
Đáp án đúng: C

Câu 23. Đổi sang embedding model tạo không gian vector khác cần xử lý gì?
A. Chỉ đổi tên index, không cần sửa vector đã lưu.
B. Tính lại vector tài liệu và truy vấn bằng model mới.
C. Chỉ tăng topK để dữ liệu cũ so được với dữ liệu mới.
D. Chỉ thay metadata để chuyển tọa độ vector sang mới.
Đáp án đúng: B

Câu 24. Khi sửa nội dung tài liệu đã lập chỉ mục, cần thực hiện điều gì?
A. Chỉ đổi topK để tài liệu mới được truy xuất đúng.
B. Giữ embedding cũ để điểm similarity không thay đổi.
C. Cập nhật embedding và bỏ chunk cũ không còn hợp lệ.
D. Chỉ sửa tiêu đề Document dù body đã khác hoàn toàn.
Đáp án đúng: C

Câu 25. Khi thêm lại một tài liệu nhiều lần, cách nào hạn chế tạo chunk trùng?
A. Phát sinh ID ngẫu nhiên mới mỗi lần ingest lại.
B. Chỉ dùng timestamp hiện tại để phân biệt mọi chunk.
C. Chỉ tăng topK sau mỗi lần ingest cùng tài liệu.
D. Dùng ID chunk ổn định để upsert hoặc dọn bản cũ.
Đáp án đúng: D

Câu 26. Trong đánh giá retrieval, `recall@k` đo điều gì?
A. Số token trung bình của embedding cho mỗi truy vấn.
B. Tỷ lệ tài liệu không liên quan nằm trong top k.
C. Độ trễ trung bình để lấy đủ k kết quả từ kho.
D. Tỷ lệ tài liệu liên quan được tìm thấy trong top k.
Đáp án đúng: D

Câu 27. Trong đánh giá retrieval, `precision@k` đo điều gì?
A. Số lượng truy vấn có kết quả đứng vị trí đầu.
B. Tỷ lệ kết quả liên quan nằm trong top k trả về.
C. Tổng chi phí tính embedding của từng chunk đã lập chỉ mục.
D. Tỷ lệ toàn bộ mục liên quan đã được tìm thấy.
Đáp án đúng: B

Câu 28. Trong đánh giá thứ hạng retrieval, MRR thường phản ánh điều gì?
A. Trung bình nghịch đảo hạng của kết quả đúng đầu.
B. Độ phủ toàn bộ tài liệu liên quan trong top k.
C. Tỷ lệ tài liệu có metadata được điền đầy đủ.
D. Độ trễ đầu cuối của bước sinh embedding truy vấn.
Đáp án đúng: A

Câu 29. Muốn so sánh hai cấu hình chunking, tập kiểm thử nào đáng tin hơn?
A. Chỉ dùng vài câu hỏi tự viết rồi xem câu trả lời dài.
B. Bộ câu hỏi có nhãn liên quan và thước đo retrieval.
C. Chỉ so tốc độ startup, không kiểm tra kết quả tìm kiếm.
D. Chỉ tính tổng số chunk tạo ra sau mỗi lần tách tài liệu.
Đáp án đúng: B

Câu 30. Khi retrieval không trả về tài liệu đủ liên quan, hệ thống RAG nên làm gì?
A. Bỏ qua ngưỡng lọc và khẳng định mọi kết quả đều đúng.
B. Chọn ngẫu nhiên tài liệu và coi nó là bằng chứng đáng tin.
C. Trả lại tài liệu khác tenant để tăng lượng thông tin.
D. Không tạo trích dẫn giả, xử lý trường hợp thiếu ngữ cảnh.
Đáp án đúng: D

Câu 31. Để giảm chi phí tạo embedding khi tài liệu thay đổi ít, cách nào phù hợp?
A. Tính lại embedding mọi chunk ở mỗi request truy vấn.
B. Nhúng lại toàn bộ corpus sau mỗi lần thay metadata.
C. Cache và chỉ nhúng lại chunk có nội dung thay đổi.
D. Đổi model embedding cho mỗi lần thêm một tài liệu.
Đáp án đúng: C

Câu 32. Khi gửi văn bản nhạy cảm cho EmbeddingModel bên ngoài, cần làm gì?
A. Chỉ bỏ tenant ID khỏi metadata rồi gửi toàn bộ.
B. Chỉ bật cache vector để thay quyền truy cập dữ liệu.
C. Kiểm soát dữ liệu được phép gửi và cơ chế bảo mật.
D. Chỉ mã hóa văn bản thành base64 trước khi gửi.
Đáp án đúng: C
