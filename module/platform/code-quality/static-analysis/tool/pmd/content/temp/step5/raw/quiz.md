Câu 1: PMD đánh giá Java chủ yếu từ nguồn thông tin nào?
A. Nhật ký truy cập được đối chiếu theo các quy tắc
B. Bytecode chạy thử được đối chiếu theo các quy tắc
C. Hồ sơ phụ thuộc được rà soát theo các quy tắc
D. Cú pháp mã nguồn được phân tích theo các quy tắc
Đáp án đúng: D

Câu 2: Khi dùng CPD, đơn vị chính để phát hiện các đoạn lặp là gì?
A. Chuỗi token của mã nguồn trong các vùng được quét
B. Chuỗi commit của nhánh đang được so sánh
C. Chuỗi cảnh báo của bộ quy tắc PMD đã bật
D. Chuỗi phụ thuộc trong tệp cấu hình build
Đáp án đúng: A

Câu 3: Muốn gom các quy tắc PMD dùng chung vào cấu hình dự án, nên làm gì?
A. Khai báo ruleset XML với các tham chiếu đến rule
B. Khai báo profile Maven với danh sách thư viện runtime
C. Khai báo workflow CI với danh sách nhánh cần build
D. Khai báo class Java với danh sách phép thử tích hợp
Đáp án đúng: A

Câu 4: Khi tích hợp PMD vào Maven, cấu hình ruleset thường đặt tại đâu?
A. Trong cấu hình maven-surefire-plugin của dự án
B. Trong cấu hình maven-pmd-plugin của dự án
C. Trong cấu hình maven-jar-plugin của dự án
D. Trong cấu hình maven-clean-plugin của dự án
Đáp án đúng: B

Câu 5: Khi áp dụng plugin PMD cho dự án Java trong Gradle, task nào quét mã nguồn chính?
A. pmdTest
B. testMain
C. pmdMain
D. pmdCheck
Đáp án đúng: C

Câu 6: Vì sao cần cố định phiên bản PMD trong build CI?
A. Để tác vụ CI bỏ qua các file mã nguồn chưa commit
B. Để quy tắc và kết quả không trôi theo bản cập nhật
C. Để CPD luôn chạy không cần cấu hình ngưỡng token
D. Để Java compiler tự nhận các quy tắc PMD tùy biến
Đáp án đúng: B

Câu 7: Muốn tắt một cảnh báo PMD cụ thể tại đoạn Java đã xem xét, cách phù hợp?
A. Áp dụng Deprecated với tên rule PMD tương ứng
B. Áp dụng Override với tên rule PMD tương ứng
C. Áp dụng FunctionalInterface với tên rule PMD tương ứng
D. Áp dụng SuppressWarnings với tên rule PMD tương ứng
Đáp án đúng: D

Câu 8: Khi gặp cảnh báo sai do ngữ cảnh nghiệp vụ, bước đầu hợp lý là gì?
A. Tăng mức nghiêm trọng của rule để dễ theo dõi cảnh báo
B. Tắt mọi rule cùng nhóm để loại bớt cảnh báo lặp lại
C. Chuyển toàn bộ cảnh báo sang loại lỗi build ngay
D. Đọc rule và đoạn mã liên quan rồi kiểm chứng ngữ cảnh
Đáp án đúng: D

Câu 9: Rule CyclomaticComplexity thường đo khía cạnh nào?
A. Số lời gọi thư viện làm tăng độ sâu cây phụ thuộc
B. Số lệnh ghi file làm tăng chi phí truy cập ổ đĩa
C. Số nhánh quyết định làm tăng độ phức tạp luồng điều khiển
D. Số phương thức public làm tăng kích thước giao diện
Đáp án đúng: C

Câu 10: NPathComplexity khác CyclomaticComplexity ở trọng tâm nào?
A. Ước lượng số lời gọi hàm đệ quy trong một phương thức
B. Ước lượng số đường thực thi không lặp trong một phương thức
C. Ước lượng số lần cấp phát đối tượng trong một phương thức
D. Ước lượng số truy cập thuộc tính private trong một phương thức
Đáp án đúng: B

Câu 11: Trong PMD, priority 1 thường có ý nghĩa gì?
A. Mức ưu tiên cảnh báo thấp nhất trong thang priority
B. Mức ưu tiên cảnh báo cao nhất trong thang priority
C. Số lượng vi phạm tối đa cho mỗi tệp mã nguồn
D. Số lần tối thiểu rule phải khớp mới tạo cảnh báo
Đáp án đúng: B

Câu 12: Nếu chỉ muốn quét một phần source tree trong dự án, nên làm gì?
A. Giới hạn các thư mục hoặc pattern include/exclude quét
B. Giảm ngưỡng CPD và giữ nguyên vùng source được quét
C. Tăng mức log của PMD và giữ nguyên vùng source được quét
D. Đổi report XML sang HTML và giữ nguyên vùng source được quét
Đáp án đúng: A

Câu 13: Giảm minimumTokens của CPD thường dẫn tới hiệu ứng nào?
A. Phát hiện nhiều đoạn trùng ngắn hơn nhưng dễ gây nhiễu
B. Bỏ qua nhiều đoạn trùng ngắn hơn nhưng giảm báo cáo
C. Chỉ xét trùng ở cấp lớp thay vì ở cấp phương thức
D. Chỉ xét trùng giữa các nhánh Git thay vì giữa các tệp
Đáp án đúng: A

Câu 14: Khi CPD báo lặp trong các đoạn mã tạo sẵn (generated code), xử lý nào hợp lý?
A. Bật thêm rule complexity để phân biệt mã sinh ra
B. Chuyển báo cáo CPD sang XML để bỏ qua mã sinh ra
C. Hạ ngưỡng token để loại bớt báo cáo mã sinh ra
D. Loại vùng mã sinh ra khỏi phạm vi CPD theo cấu hình
Đáp án đúng: D

Câu 15: Khi một rule PMD bắt quá nhiều trường hợp hợp lệ, chỉnh ruleset thế nào?
A. Giữ nguyên rule và tắt toàn bộ quá trình build CI
B. Giữ nguyên rule và nâng mọi cảnh báo thành lỗi biên dịch
C. Chuyển mọi rule sang CPD để gom các cảnh báo lặp
D. Điều chỉnh thuộc tính rule hoặc phạm vi áp dụng phù hợp
Đáp án đúng: D

Câu 16: Một rule PMD viết bằng XPath thường dựa vào gì để phát hiện lỗi?
A. Mẫu request và response trong log của ứng dụng
B. Mẫu truy vấn SQL trong cơ sở dữ liệu đang chạy
C. Mẫu nút và quan hệ trong cây cú pháp của ngôn ngữ
D. Mẫu bytecode sinh ra từ các bài kiểm thử đơn vị
Đáp án đúng: C

Câu 17: Khi phát triển custom rule Java, yếu tố nào cần kiểm tra lúc nâng PMD?
A. API và cấu trúc AST mà phiên bản PMD cung cấp
B. API và định dạng log mà phiên bản JVM cung cấp
C. API và cấu trúc JAR mà trình đóng gói cung cấp
D. API và cổng mạng mà agent CI cung cấp
Đáp án đúng: A

Câu 18: Cách triển khai PMD trên codebase nhiều nợ kỹ thuật để tránh chặn CI ngay?
A. Tắt toàn bộ ruleset cho đến khi có bản phát hành
B. Bỏ quy trình code review để ưu tiên sửa cảnh báo
C. Lập baseline lỗi cũ và áp gate cho thay đổi mới
D. Chỉ chạy PMD ở môi trường production sau deploy
Đáp án đúng: C

Câu 19: Khi PMD cảnh báo mã có độ phức tạp cao, cải tiến nào thường phù hợp?
A. Bổ sung nhiều điều kiện lồng nhau để gom logic lại
B. Chuyển tất cả biến cục bộ thành thuộc tính dùng chung
C. Tách bớt nhánh xử lý thành các hàm có mục đích rõ
D. Bọc toàn bộ thân hàm trong try/catch để ít nhánh
Đáp án đúng: C

Câu 20: Dùng PMD và CPD cùng nhau có ích ở điểm nào?
A. Kiểm tra quy tắc chất lượng lẫn phát hiện đoạn mã lặp
B. Kiểm tra độ bao phủ test lẫn đo thời gian chạy
C. Kiểm tra giao thức HTTP lẫn phát hiện cấu hình cổng
D. Kiểm tra phiên bản máy ảo lẫn đóng gói artifact
Đáp án đúng: A

Câu 21: Nếu PMD chỉ báo lỗi trên CI mà máy cục bộ không có, nên đối chiếu gì?
A. Phiên bản trình duyệt, CSS và kích thước viewport
B. Phiên bản database, schema và danh sách index
C. Phiên bản hệ điều hành, DNS và tốc độ mạng
D. Phiên bản công cụ, ruleset và tập file được quét
Đáp án đúng: D

Câu 22: Khi đặt ngưỡng chất lượng trong CI, cách nào giúp dùng PMD hiệu quả?
A. Đặt ngưỡng thay đổi tùy người commit và nhánh làm việc
B. Đặt ngưỡng nhất quán, ghi lý do ngoại lệ và theo dõi
C. Đặt ngưỡng cực thấp cho mọi module dù chưa kiểm kê
D. Đặt ngưỡng theo kích thước báo cáo mà bỏ mức độ lỗi
Đáp án đúng: B

Câu 23: Muốn hệ thống CI tự tổng hợp vi phạm PMD, đầu ra nào phù hợp?
A. Báo cáo ảnh chụp màn hình của terminal
B. Báo cáo văn bản tự do trong phần README
C. Báo cáo định dạng có cấu trúc như XML
D. Báo cáo comment thủ công trong từng PR
Đáp án đúng: C

Câu 24: Khi cân nhắc suppress một violation, tiêu chí nào quan trọng nhất?
A. Có số lượng test lớn, phạm vi rộng và chạy nhanh
B. Có lý do cụ thể, phạm vi hẹp và được review
C. Có nhiều comment mô tả, phạm vi rộng và ít rule
D. Có nhiều file tương tự, phạm vi lớn và build xanh
Đáp án đúng: B
