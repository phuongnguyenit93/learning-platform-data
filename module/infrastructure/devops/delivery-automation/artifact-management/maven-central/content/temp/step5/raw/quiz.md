Câu 1: Bộ ba GAV nào xác định một phiên bản thư viện trong hệ sinh thái Maven?
A. `groupId`, `artifactId`, `classifier`.
B. `groupId`, `artifactId`, `repository`.
C. `groupId`, `packaging`, `version`.
D. `groupId`, `artifactId`, `version`.
Đáp án đúng: D

Câu 2: Việc xác minh namespace trước khi xuất bản lên Maven Central chủ yếu nhằm mục đích gì?
A. Ràng buộc namespace với thời hạn sử dụng token phát hành CI.
B. Kiểm tra license của tất cả dependency trong POM.
C. Chứng minh quyền kiểm soát namespace được yêu cầu.
D. Đảm bảo groupId không trùng artifactId của dự án.
Đáp án đúng: C

Câu 3: Một phiên bản `1.4.0` đã được phát hành lên Maven Central. Khi phải sửa mã, nên làm gì?
A. Tăng phiên bản rồi phát hành artifact mới.
B. Ghi đè cùng GAV bằng artifact đã sửa trong CI.
C. Đổi timestamp rồi giữ nguyên GAV cũ.
D. Xóa checksum rồi upload lại cùng GAV.
Đáp án đúng: A

Câu 4: POM của thư viện công khai cần nhóm metadata nào để làm rõ nguồn gốc và điều khoản sử dụng?
A. Tên, mô tả, URL, license, danh sách mirror và SCM.
B. Tên, mô tả, URL, license, cấu hình proxy và SCM.
C. Tên, mô tả, URL, license, developers và SCM.
D. Tên, mô tả, URL, license, báo cáo test và SCM.
Đáp án đúng: C

Câu 5: Vì sao thư viện JVM thường phát hành thêm `-sources.jar` và `-javadoc.jar`?
A. Để đưa các dependency runtime vào cùng artifact.
B. Để người dùng xem mã nguồn và tài liệu API.
C. Để ghi đè file POM khi consumer resolve GAV.
D. Để thay thế file JAR nhị phân trên repository.
Đáp án đúng: B

Câu 6: Khi phát hành artifact lên Maven Central, chữ ký OpenPGP `.asc` dùng để kiểm tra điều gì?
A. Artifact được build từ máy chủ CI mặc định.
B. Artifact có quyền truy cập tới registry riêng.
C. Artifact đã được quét hết lỗi trong mã nguồn.
D. Artifact khớp chữ ký của khóa công khai tin cậy.
Đáp án đúng: D

Câu 7: Plugin Maven nào tạo chữ ký `.asc` cho artifact trong bước phát hành?
A. `maven-gpg-plugin`.
B. `maven-jar-plugin`.
C. `maven-deploy-plugin`.
D. `maven-source-plugin`.
Đáp án đúng: A

Câu 8: Với Gradle `maven-publish`, cấu hình nào xác định artifact và metadata để sinh POM?
A. Đặt `repositories` trong `publishing` cho artifact.
B. Đặt `MavenPublication` trong `publications` cho artifact.
C. Đặt `signing` trong `dependencies` cho artifact.
D. Đặt `resolutionStrategy` trong `configurations` cho artifact.
Đáp án đúng: B

Câu 9: Bundle đã upload lên Central Portal nhưng người dùng chưa tìm được bản phát hành. Nên kiểm tra gì?
A. Version trong dự án tiêu thụ đã đổi theo tag Git mới chưa.
B. Deployment đã qua validation và được publish chưa.
C. Maven Wrapper đã tải artifact vào cache hay chưa.
D. Plugin compiler đã tạo timestamp mới hay chưa.
Đáp án đúng: B

Câu 10: Thư viện khai báo dependency trong POM có thể ảnh hưởng thế nào khi consumer resolve GAV?
A. Maven có thể kéo dependency bắc cầu theo scope.
B. Maven tự gộp dependency vào JAR nhị phân của thư viện.
C. Maven bỏ qua version khi dependency cùng groupId.
D. Maven chỉ tải dependency khi artifact được ký PGP.
Đáp án đúng: A

Câu 11: Pipeline CI nên quản lý token phát hành và khóa ký thư viện như thế nào?
A. Commit chúng vào POM của nhánh release để audit.
B. Cấp qua secret store, giới hạn quyền và tránh ghi log.
C. Đặt chúng vào cache build để job khác tái sử dụng.
D. Nhúng chúng vào artifact để kiểm tra sau khi release.
Đáp án đúng: B

Câu 12: Checksum của artifact khớp nhưng chưa xác minh chữ ký với khóa tin cậy. Kết luận nào đúng?
A. Artifact chắc chắn do đúng publisher tạo và nguyên vẹn.
B. Artifact đã qua kiểm tra lỗ hổng bảo mật của Central.
C. Artifact chắc chắn trùng commit được gắn tag release.
D. Checksum khớp nhưng chưa xác thực nguồn gốc publisher.
Đáp án đúng: D

Câu 13: Với Maven Central, chiến lược nào phù hợp cho phiên bản phát hành ổn định?
A. Dùng version không có `-SNAPSHOT` và giữ GAV bất biến.
B. Dùng `-SNAPSHOT` rồi thay binary dưới cùng GAV mỗi lần.
C. Dùng version cố định và ghi đè khi sửa lỗi nhỏ.
D. Dùng tag Git thay cho trường version trong POM.
Đáp án đúng: A

Câu 14: Trong Maven, `distributionManagement` khác `repositories` ở vai trò nào?
A. `distributionManagement` chọn mirror; `repositories` chọn signer.
B. `distributionManagement` chọn compiler; `repositories` chọn deploy.
C. `distributionManagement` chọn đích deploy; `repositories` chọn nguồn resolve.
D. `distributionManagement` chọn version; `repositories` chọn namespace.
Đáp án đúng: C

Câu 15: Pipeline bị timeout sau khi gửi bản phát hành. Trước khi retry nên làm gì?
A. Tự tăng version và đăng bản mới ngay từ CI.
B. Xóa cache local rồi chạy lại bước upload.
C. Gửi lại cùng GAV mà không kiểm tra trạng thái ở Central.
D. Tra trạng thái deployment để biết đã publish chưa.
Đáp án đúng: D

Câu 16: Sau khi publish, cách nào kiểm tra thư viện thật sự dùng được từ Maven Central?
A. Chỉ xem log upload trả mã thoát thành công trên CI.
B. Chỉ kiểm tra file JAR nằm trong workspace.
C. Resolve GAV từ môi trường sạch, xem POM và chữ ký.
D. Chỉ đối chiếu tag Git với version của CI.
Đáp án đúng: C
