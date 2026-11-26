1. Trong dự án Java, build tool thường tự động hóa chuỗi hoạt động nào?
A. Chỉ soạn source rồi chạy ứng dụng qua IDE
B. Chỉ quản lý kết nối database của ứng dụng
C. Chỉ theo dõi CPU khi ứng dụng chạy production
D. Biên dịch, kiểm thử, đóng gói và phát hành
Đáp án đúng: D

2. Trong đồ thị task của build tool, cạnh phụ thuộc có ý nghĩa gì?
A. Hai task phải được gọi đồng thời trong mọi lần build
B. Task tiền đề phải hoàn thành trước task phụ thuộc
C. Task sau tự động thay đổi version của task trước
D. Hai task bắt buộc dùng chung thư mục output đã tạo
Đáp án đúng: B

3. Vì sao cùng lệnh build có thể chỉ chạy một phần task?
A. Build tool chỉ chọn task cho mục tiêu được yêu cầu
B. Build tool luôn chạy tất cả task khai báo trong dự án
C. Build tool chỉ chạy task có tên theo thứ tự chữ cái
D. Build tool bỏ qua toàn bộ task của plugin được áp dụng
Đáp án đúng: A

4. Điều gì phân biệt dependency artifact với task dependency?
A. Cả hai chỉ là cách khai báo thứ tự biên dịch class
B. Cả hai chỉ định nơi xuất bản gói thư viện hoàn chỉnh
C. Một bên là thư viện, bên kia là quan hệ giữa task
D. Một bên dùng cho CI; bên kia chỉ dùng khi mở IDE
Đáp án đúng: C

5. Vì sao tách source chính và source test thành các tập riêng?
A. Bắt buộc test được đóng chung vào artifact production
B. Giúp runtime tự gọi mọi unit test khi chạy chương trình
C. Làm cho kiểm thử không cần thêm bất kỳ dependency nào
D. Cho phép chọn classpath và bước biên dịch phù hợp
Đáp án đúng: D

6. Trong quy trình build, packaging diễn ra để đạt mục tiêu gì?
A. Biến mọi warning compiler thành lỗi runtime bắt buộc
B. Tự động nâng version của các dependency bắc cầu
C. Thay thế toàn bộ bước kiểm thử tích hợp bằng unit test
D. Đóng gói class và tài nguyên thành artifact phát hành
Đáp án đúng: D

7. Build plugin thường cung cấp chức năng gì cho build script?
A. Thay thế hoàn toàn source Java của toàn bộ dự án
B. Thêm task và quy ước build theo mục tiêu dự án
C. Chỉ lưu kết quả chạy thực tế của sản phẩm production
D. Chỉ định dung lượng tối đa của heap cho mọi class
Đáp án đúng: B

8. Repository trong quản lý dependency thường chứa những gì?
A. Chỉ mã nguồn chưa được đưa vào hệ thống Git
B. Chỉ báo cáo kiểm thử của một lần chạy ở IDE
C. Artifact và metadata để tải về hoặc xuất bản
D. Chỉ tập tin cấu hình biến môi trường của máy local
Đáp án đúng: C

9. Để tránh tải thư viện không cần thiết vào runtime, cần phân loại gì?
A. Số lượng dòng comment của từng module trong repository
B. Tên file source theo chữ cái đầu của package Java
C. Phạm vi dependency cho compile, runtime và test
D. Thứ tự task theo thời điểm chúng được khai báo
Đáp án đúng: C

10. Vì sao cần phân biệt dependency trực tiếp và bắc cầu?
A. Thư viện trực tiếp không bao giờ có version rõ ràng
B. Thư viện bắc cầu luôn là source nằm trong dự án
C. Thư viện bắc cầu chỉ được sử dụng khi chạy IDE
D. Thư viện trực tiếp có thể kéo theo thư viện khác
Đáp án đúng: D

11. Một dự án đa module thường chia sẻ bước build nào tốt nhất?
A. Nhân bản cấu hình thủ công cho từng module không liên quan
B. Tái sử dụng cấu hình chung và khai báo quan hệ module
C. Buộc mọi module có cùng tên và đường dẫn của artifact
D. Gộp toàn bộ source của các module vào một thư mục
Đáp án đúng: B

12. Trong build đa module, khai báo project dependency giúp gì?
A. Đưa đầu ra của module phụ thuộc vào classpath cần dùng
B. Buộc các module con phát hành cùng một artifact duy nhất
C. Bỏ qua mọi bước kiểm thử của module cung cấp thư viện
D. Chuyển mã Java của module nguồn thành script build
Đáp án đúng: A

13. Build tăng dần dựa vào điều kiện nào để bỏ qua task an toàn?
A. Đầu vào và đầu ra không đổi so với trạng thái đã ghi
B. Task đã từng chạy thành công trên bất kỳ máy nào
C. Tất cả file trong repository vẫn có cùng dung lượng byte
D. Thời gian bắt đầu build gần với lần chạy trước
Đáp án đúng: A

14. Cách nào giúp build cache tái sử dụng kết quả đúng?
A. Dựa duy nhất vào tên task dù đầu vào đã thay đổi
B. Băm đầu vào và cấu hình có ảnh hưởng đến output
C. Lưu mọi output vào một thư mục có thể ghi đè tùy ý
D. Chỉ so sánh số lượng source file của hai lần build
Đáp án đúng: B

15. Nguyên tắc nào giúp build tái lập trên máy CI khác nhau?
A. Luôn lấy phiên bản dependency mới nhất từ repository
B. Luôn dùng mọi cài đặt IDE riêng của từng người
C. Cố định toolchain, version thư viện và dữ liệu vào
D. Cho phép script phụ thuộc thời gian hệ thống hiện tại
Đáp án đúng: C

16. Vì sao nên dùng Wrapper của build tool trong repository?
A. Dùng đúng phiên bản build tool đã chốt sẵn
B. Giúp build bỏ qua bước tải dependency của dự án
C. Giúp JVM tự tải code Java trước khi đóng gói
D. Giúp mọi module tự động chuyển sang cùng group ID
Đáp án đúng: A

17. Với artifact từ repository công cộng, kiểm tra checksum hỗ trợ gì?
A. Tự phát hiện tất cả license không tương thích
B. Tự tạo dependency graph chính xác từ source code
C. Thay đổi thuật toán biên dịch khi artifact trùng tên
D. Phát hiện nội dung tải về khác với giá trị mong đợi
Đáp án đúng: D

18. Trong CI, thứ tự kiểm tra phù hợp trước khi phát hành là gì?
A. Biên dịch và test đạt rồi mới publish artifact
B. Publish artifact trước rồi mới quyết định có cần test
C. Bỏ qua test nếu source được lưu trong Git thành công
D. Chỉ phân tích log production rồi mới chạy compile
Đáp án đúng: A

19. Sự khác nhau giữa unit test và integration test trong build là gì?
A. Một loại kiểm thử đơn vị; loại kia kiểm tra tương tác
B. Cả hai luôn cần kết nối database thật ở mọi trường hợp
C. Integration test chỉ kiểm tra định dạng tên file source
D. Unit test chỉ chạy khi artifact đã được đưa lên repository
Đáp án đúng: A

20. Với lỗi thiếu artifact trong repository, bước chẩn đoán nào nên làm đầu tiên?
A. Tăng RAM của JVM mà không cần kiểm tra log
B. Xem tọa độ, version, repo và quyền truy cập
C. Đổi mọi dependency từ compile sang test runtime
D. Xóa toàn bộ source Java rồi thử tạo lại module
Đáp án đúng: B

21. Khi thay đổi API thư viện dùng chung, điều gì cần kiểm tra trong build đa module?
A. Chỉ chạy task định dạng mã của module không bị ảnh hưởng
B. Biên dịch và kiểm thử các module đang phụ thuộc vào API
C. Chỉ kiểm tra task đóng gói trong module UI độc lập
D. Chỉ xem số lượng commit của module chứa thư viện
Đáp án đúng: B

22. Tại sao cần phân biệt version release và snapshot trong pipeline?
A. Release luôn được tải từ máy local; snapshot luôn từ CI
B. Release chỉ dùng để chạy test; snapshot chỉ để publish
C. Release ổn định; snapshot có thể thay đổi theo bản build
D. Release không có metadata; snapshot không có tọa độ
Đáp án đúng: C

23. Khi tạo artifact cho môi trường production, yếu tố nào hỗ trợ truy vết?
A. Đổi tên artifact theo tên người chạy build thủ công
B. Xóa toàn bộ thông tin dependency để giảm metadata
C. Chỉ lưu timestamp máy local trong tên gói output
D. Ghi version, commit và provenance của bản build
Đáp án đúng: D

24. Để kiểm soát thời gian build tăng cao, bước đo lường nào hợp lý?
A. Chỉ tăng số core của CI mà không xem task chậm
B. Chỉ xóa báo cáo test để giảm kích thước artifact
C. Đo từng task, cache hit và phạm vi thay đổi
D. Chỉ so thời gian tải trang quản trị trong trình duyệt
Đáp án đúng: C
