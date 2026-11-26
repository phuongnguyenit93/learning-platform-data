Câu 1. Nhóm đã bật hook quét secret trên máy lập trình viên nhưng một số người có thể bỏ qua hook trước khi push. Biện pháp nào chặn secret vào remote hiệu quả nhất?
A. Yêu cầu mọi developer tự chạy lệnh quét trước commit.
B. Bật cảnh báo trong IDE khi developer mở repository.
C. Gửi báo cáo quét định kỳ cho chủ sở hữu repository.
D. Bật push protection ở phía server để từ chối secret.
Đáp án đúng: D

Câu 2. Scanner cần phát hiện token có tiền tố và cấu trúc đặc thù của một nhà cung cấp. Phương pháp nào phù hợp nhất?
A. Chỉ cảnh báo chuỗi có entropy cao trong mọi tệp mã nguồn.
B. Dùng mẫu định dạng token kèm kiểm tra cấu trúc hợp lệ.
C. Chỉ tìm chuỗi mang tên biến `password` trong source.
D. Chỉ so độ dài token với các chuỗi ngẫu nhiên khác.
Đáp án đúng: B

Câu 3. Công cụ quét theo entropy cảnh báo UUID và checksum trong source. Bước nào giúp phân loại cảnh báo chính xác hơn?
A. Xét ngữ cảnh sử dụng và xác minh dấu hiệu credential.
B. Đưa mọi chuỗi entropy cao vào danh sách bị rò rỉ.
C. Loại bỏ toàn bộ kết quả trong tệp có phần mở rộng JSON.
D. Chỉ phân loại theo số ký tự mà không xét vị trí tệp.
Đáp án đúng: A

Câu 4. Một access token đã bị commit ở nhánh cũ, sau đó được xóa ở commit mới. Phạm vi nào cần quét để còn phát hiện dấu vết?
A. Chỉ quét các tệp đang có trong working tree hiện tại.
B. Chỉ quét nhánh chính kể từ commit merge gần nhất.
C. Chỉ quét diff giữa hai bản build mới nhất trên CI.
D. Quét lịch sử commit và các ref còn truy cập được.
Đáp án đúng: D

Câu 5. Job secret scanning chạy trên merge request từ fork lạ. Thiết kế quyền nào an toàn cho chính job quét đó?
A. Dùng quyền đọc mã tối thiểu, không cấp secret phát hành.
B. Cấp token deploy được masked để scanner đọc đủ log.
C. Cho scanner dùng tài khoản ghi repository để sửa diff.
D. Cho scanner chạy cùng quyền với job deploy production đã duyệt.
Đáp án đúng: A

Câu 6. API key thật bị ghi vào log của CI và đã có người xem log. Hành động ứng phó đầu tiên nào phù hợp?
A. Thu hồi hoặc xoay key, kiểm tra quyền xem log và phạm vi lộ.
B. Xóa log khỏi giao diện CI rồi giữ key vì source chưa hề chứa key.
C. Thay tên biến môi trường, giữ nguyên giá trị key đã lộ.
D. Thêm masked variable để che log cũ và tiếp tục dùng key.
Đáp án đúng: A

Câu 7. Muốn xác định token được scanner phát hiện còn hiệu lực hay không, cách kiểm chứng nào phù hợp?
A. Thử gọi API quản trị có quyền xóa dữ liệu để xác nhận.
B. Gọi endpoint có quyền ghi dữ liệu cao nhất mà token cho phép.
C. Dùng cơ chế kiểm tra được phép, ít quyền và giới hạn truy vấn.
D. Mở token dưới dạng URL công khai để đối chiếu phản hồi.
Đáp án đúng: C

Câu 8. Repository có tệp test chứa chuỗi giả trông như token thật, đã xác nhận không có quyền truy cập. Cách giảm báo sai nào có kiểm soát?
A. Tắt toàn bộ rule của nhà cung cấp token trên mọi repo.
B. Bỏ quét tất cả tệp test của dự án trong mọi trường hợp.
C. Cho phép ngoại lệ hẹp có lý do và định kỳ xem xét lại.
D. Chuyển mọi cảnh báo về mức thấp mà không cần xác minh.
Đáp án đúng: C

Câu 9. Developer xóa credential đã lộ khỏi HEAD và đề xuất rewrite lịch sử Git. Điều gì vẫn phải thực hiện để xử lý rủi ro?
A. Kiểm tra commit hiện tại đã sạch là đủ để đóng cảnh báo.
B. Thu hồi credential vì clone, fork và bản sao vẫn có thể giữ.
C. Chỉ xóa branch cũ vì rewrite sẽ tự vô hiệu hóa credential.
D. Đổi SHA commit mới vì server sẽ quên credential từ lịch sử.
Đáp án đúng: B

Câu 10. Hai cảnh báo phát hiện được: token còn hiệu lực trên repo công khai và token mẫu không có quyền trong fixture. Nên ưu tiên cái nào?
A. Ưu tiên token mẫu vì fixture có thể được chạy ở CI.
B. Ưu tiên cảnh báo xuất hiện sớm hơn trong hai tệp mã.
C. Ưu tiên token thật theo hiệu lực, mức phơi lộ và đặc quyền.
D. Ưu tiên chuỗi dài hơn vì entropy cao thường gợi ý rủi ro lớn hơn.
Đáp án đúng: C

Câu 11. Pipeline đóng gói ứng dụng và xuất bản `build.zip`; thư mục build vô tình chứa `.env` với credential. Kiểm soát nào đúng điểm rủi ro?
A. Chỉ quét Git diff vì archive luôn lấy từ mã nguồn đã được quét.
B. Quét nội dung artifact và chặn xuất bản khi chứa secret.
C. Chỉ quét Dockerfile vì `build.zip` không được chạy.
D. Chỉ giới hạn thời gian lưu artifact sau khi phát hành.
Đáp án đúng: B

Câu 12. Nhóm muốn phát hiện secret trước commit nhưng cũng ngăn lộ khi người dùng bỏ qua hook. Cấu hình nhiều lớp nào phù hợp?
A. Chạy hook cục bộ rồi tin kết quả, không quét phía server.
B. Quét sớm ở máy và áp gate trong CI hoặc phía server.
C. Quét định kỳ sau release để không làm chậm bước commit.
D. Chỉ dùng plugin IDE vì CI không đọc được lịch sử Git.
Đáp án đúng: B

Câu 13. Chứng chỉ TLS dùng private key bị lộ trong repository và có thể đã được tải xuống. Biện pháp nào phù hợp nhất?
A. Đổi tên tệp `.pem` rồi chỉ cho tài khoản triển khai truy cập tệp đó.
B. Xóa commit mới nhất để khóa riêng không còn trong HEAD.
C. Tạo cặp khóa mới, thay chứng chỉ và thu hồi chứng chỉ cũ.
D. Chỉ đổi quyền đọc tệp mới, giữ khóa đã bị lộ trước đó.
Đáp án đúng: C

Câu 14. Một secret được biểu diễn dưới dạng Base64 rồi đưa vào YAML. Muốn tăng khả năng phát hiện dạng này mà vẫn kiểm soát báo sai, nên làm gì?
A. Chỉ quét chuỗi ASCII có ký tự `=` ở cuối mọi giá trị.
B. Bỏ quét YAML vì giá trị mã hóa không còn là credential.
C. Giải mã tất cả tệp nhị phân và coi mọi kết quả là secret.
D. Giải mã có giới hạn, áp quy tắc và xác minh ngữ cảnh.
Đáp án đúng: D

Câu 15. Scanner không nhận ra mật khẩu tự đặt không theo mẫu token nhà cung cấp. Nhận định nào đúng về phạm vi công cụ?
A. Chỉ cần bổ sung regex theo tiền tố token phổ biến.
B. Cứ dùng entropy cao sẽ phát hiện mọi mật khẩu chắc chắn.
C. Chỉ quét tệp `.env` là đủ để tìm mọi mật khẩu.
D. Phối hợp mẫu, entropy, ngữ cảnh; vẫn có thể bỏ sót.
Đáp án đúng: D

Câu 16. Sau khi xoay token bị lộ, đội muốn xác nhận ứng phó đã hoàn tất. Kiểm chứng nào đáng tin cậy nhất?
A. Token cũ hết hiệu lực, token mới hoạt động và nguồn lộ được xử lý.
B. Token mới đã được commit để người vận hành dễ theo dõi.
C. Log CI được đổi tên và số lượng finding giảm xuống một.
D. Tệp chứa token cũ đã được xóa khỏi nhánh chính và các nhánh phát hành.
Đáp án đúng: A
