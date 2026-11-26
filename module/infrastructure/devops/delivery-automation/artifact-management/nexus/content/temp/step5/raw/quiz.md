Câu 1. Nhóm phát triển muốn đẩy JAR nội bộ từ pipeline vào Nexus để đồng nghiệp dùng làm dependency Maven. Nên tạo repository nào?
A. Maven proxy, trỏ remote đến kho thư viện công khai.
B. Maven hosted, nhận JAR do pipeline Maven xuất bản.
C. Maven group, hợp nhất các kho thành URL tải chung.
D. Raw hosted, lưu JAR như tệp không có Maven metadata.
Đáp án đúng: B

Câu 2. Máy build thường xuyên tải thư viện từ Maven Central. Đội muốn Nexus lấy từ nguồn đó và giữ bản tải để dùng lại. Cần cấu hình repository nào?
A. Maven hosted, để CI upload tất cả thư viện phụ thuộc.
B. Maven group, chỉ gom các repository nội bộ hiện có.
C. Maven hosted, bật chính sách lưu trữ lâu cho release.
D. Maven proxy, cấu hình remote URL tới Maven Central.
Đáp án đúng: D

Câu 3. Ứng dụng dùng JAR nội bộ và dependency từ Maven Central; muốn một endpoint đọc duy nhất cho Maven client. Nexus nên cấp gì?
A. Một Maven hosted dành riêng cho artifact nội bộ phát hành.
B. Một Maven group gồm hosted nội bộ và proxy tới Central.
C. Một Maven proxy chỉ kết nối Maven Central làm upstream.
D. Hai URL khác nhau cho hosted và proxy trong cấu hình.
Đáp án đúng: B

Câu 4. CI chạy `mvn deploy` cho phiên bản `3.0.0-SNAPSHOT` nhưng Maven hosted dành cho release chặn upload. Cần thay đổi cấu hình nào?
A. Thêm URL snapshot vào `repositories` để Maven tải về.
B. Đặt `distributionManagement` tới Maven hosted snapshot.
C. Thêm repository snapshot vào Maven group rồi deploy vào group.
D. Bật metadata cache cho proxy đang trỏ tới Maven Central.
Đáp án đúng: B

Câu 5. Developer muốn công bố gói npm nội bộ lên Nexus để các dự án khác cài bằng npm. Địa chỉ publish nên trỏ tới đâu?
A. npm hosted có quyền ghi dành cho tài khoản phát hành.
B. npm proxy để lấy gói từ registry công khai và lưu cache.
C. npm group kết hợp các kho để client tải package.
D. npm group gồm hosted đứng đầu và proxy phía sau.
Đáp án đúng: A

Câu 6. Pipeline dùng `docker push` để xuất bản image mới lên Nexus. Repo đích phù hợp, cùng điều kiện kết nối nào?
A. Docker hosted có endpoint registry và quyền push image.
B. Docker proxy có remote registry để cache các lần pull.
C. Docker group tổng hợp nhiều kho cho client pull image.
D. Raw hosted có đường dẫn lưu trữ file tar của image.
Đáp án đúng: A

Câu 7. CI chạy `npm ci` từ Nexus và nhận `E401`, trong khi URL registry đã đúng. Kiểm tra nào hữu ích nhất đầu tiên?
A. Rà phiên bản Node cục bộ và lockfile của dự án.
B. Rà thứ tự các thành viên npm group trong Nexus đang được dùng.
C. Rà token và URL registry tương ứng trong `.npmrc`.
D. Rà TTL của npm proxy với registry ở upstream.
Đáp án đúng: C

Câu 8. Một npm package đã được publish vào Nexus hosted theo phiên bản release. CI muốn publish nội dung khác nhưng giữ nguyên version. Cách xử lý nào giữ tính bất biến?
A. Ghi đè bản cũ nếu pipeline chạy lại cùng commit.
B. Xóa package release rồi publish lại cùng version.
C. Đổi npm dist-tag nhưng vẫn publish lại cùng version.
D. Giữ bản release cũ, phát hành bản mới với version khác.
Đáp án đúng: D

Câu 9. Job CI chỉ cần đẩy image vào một Docker hosted repo. Nên cấp quyền cho tài khoản automation theo cách nào?
A. Chỉ quyền đọc và ghi cần thiết trên Docker hosted đích.
B. Quyền quản trị toàn bộ Nexus để tránh lỗi phân quyền.
C. Quyền quản lý tất cả Docker hosted để dùng chung token giữa các job.
D. Quyền xóa mọi component để xử lý trường hợp push lỗi.
Đáp án đúng: A

Câu 10. Pipeline `docker login` thành công nhưng `docker push` tới Nexus nhận HTTP 403. Điều nào cần kiểm tra trước?
A. Kích thước các layer và dung lượng bộ nhớ của client.
B. TTL cache trên Docker proxy trỏ tới registry upstream.
C. Quyền add/edit trên Docker hosted mà pipeline đang push.
D. Thứ tự thành viên Docker group được client dùng để pull.
Đáp án đúng: C

Câu 11. Upstream Maven đã công bố phiên bản mới, nhưng Nexus proxy vẫn trả metadata cũ trong lúc truy vấn. Nên kiểm tra gì?
A. Policy ghi đè version release trên Maven hosted nội bộ.
B. URL deploy của Maven CI đã trỏ tới Maven group chưa.
C. Retry và cache dependency của Maven trong máy runner.
D. TTL metadata và cơ chế làm mới cache của Maven proxy.
Đáp án đúng: D

Câu 12. Image có trong Docker hosted nhưng client dùng Docker group để pull lại nhận 404. Mục nào nên kiểm tra đầu tiên?
A. TTL trên Docker proxy đang trỏ đến registry upstream.
B. Chế độ đăng nhập anonymous trên Docker hosted đích.
C. Quyền ghi push vào endpoint Docker group đang gọi.
D. Thành viên của Docker group và quyền đọc image trên hosted.
Đáp án đúng: D

Câu 13. Kho Nexus tăng nhanh do artifact từ các pipeline thử nghiệm. Đội muốn dọn theo tuổi mà giữ nguyên release production. Nên cấu hình gì?
A. Áp cleanup policy theo tuổi cho mọi repository đang hoạt động.
B. Xóa trực tiếp các blob lớn trong thư mục dữ liệu Nexus.
C. Tách kho CI và áp cleanup policy cùng tác vụ dọn định kỳ.
D. Giảm TTL của các proxy để xóa artifact trong hosted.
Đáp án đúng: C

Câu 14. Sau khi chạy cleanup policy, artifact đã bị xóa nhưng dung lượng blob store chưa giảm tương ứng. Việc bảo trì nào phù hợp?
A. Tăng dung lượng cache trên các proxy repository hiện có.
B. Chạy rebuild index cho các repository vừa cleanup xong.
C. Chạy tác vụ compact blob store sau khi xóa hợp lệ.
D. Đổi version policy của các repository Maven hosted.
Đáp án đúng: C

Câu 15. Đội chuẩn bị kế hoạch phục hồi Nexus Repository sau sự cố mất máy chủ. Cặp dữ liệu nào cần sao lưu đồng bộ để phục hồi artifact nhất quán?
A. Cơ sở dữ liệu Nexus và blob store ở cùng mốc nhất quán.
B. Các log của pipeline CI và cache Maven ở máy build.
C. URL của từng proxy upstream và danh sách người sử dụng.
D. Tệp `.npmrc` của developer và script triển khai CI.
Đáp án đúng: A

Câu 16. Nexus chạy sau reverse proxy; `docker login` được nhưng push image lớn bị HTTP 413. Chỗ nào nên kiểm tra trước?
A. TTL của Docker proxy với registry upstream bên ngoài.
B. Giới hạn kích thước request tại reverse proxy trước Nexus.
C. Thứ tự các Docker hosted nằm trong Docker group.
D. Quy tắc cleanup theo tuổi của các image build cũ trong Nexus.
Đáp án đúng: B
