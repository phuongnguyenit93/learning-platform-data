1. Một data inventory cần hỗ trợ phân loại và xóa dữ liệu. Bộ metadata nào hữu ích nhất?
A. Nhóm vận hành, số dòng, tốc độ truy vấn và mức sử dụng CPU.
B. Owner, vị trí, mục đích, nhãn, retention và bản sao liên quan.
C. Tên ứng dụng, phiên bản triển khai, vùng mạng và loại database.
D. Tên bảng, dung lượng, định dạng và ngày tạo gần nhất.
Đáp án đúng: B

2. Ngày sinh và mã bưu chính riêng lẻ ít nhạy cảm nhưng kết hợp có thể nhận diện người. Nên phân loại thế nào?
A. Giữ nhãn thấp vì từng trường không phải định danh trực tiếp.
B. Gắn nhãn theo trường có độ nhạy cao nhất khi đứng riêng.
C. Đánh giá độ nhạy của tổ hợp theo rủi ro tái nhận diện.
D. Chỉ nâng nhãn nếu tên và email cũng xuất hiện trong cùng bảng.
Đáp án đúng: C

3. Một tập dữ liệu nhạy cảm không còn data owner sau tái cơ cấu. Hành động nào phù hợp?
A. Sao chép dữ liệu sang kho mới rồi tìm owner sau khi migration.
B. Giữ quyền hiện tại vì hệ thống vẫn cần phục vụ nghiệp vụ.
C. Chuyển nhãn sang Internal để nhóm vận hành dễ tiếp tục dùng.
D. Hạn chế truy cập và chỉ định owner có trách nhiệm rà soát.
Đáp án đúng: D

4. Dữ liệu Restricted được xuất sang kho cộng tác nhưng nhãn không đi theo file. Kiểm soát nào cần thiết?
A. Gắn nhãn lại theo mặc định của kho đích sau khi upload.
B. Truyền nhãn và policy cùng dữ liệu qua export và import.
C. Chỉ ghi nhãn trong catalog nguồn và không đưa vào file xuất.
D. Dựa vào tên file và thư mục để người nhận tự suy ra nhãn.
Đáp án đúng: B

5. Công cụ tự động phân loại có confidence thấp nhưng gắn trường định danh là Public. Nên xử lý thế nào?
A. Giữ Public vì mô hình đã trả về một nhãn có xác suất cao nhất.
B. Bỏ nhãn tự động và cho mọi nhóm tự chọn theo nhu cầu sử dụng.
C. Đưa kết quả vào review và áp dụng nhãn bảo thủ trong lúc chờ.
D. Hạ nhãn các trường lân cận để tránh tạo quá nhiều dữ liệu Restricted.
Đáp án đúng: C

6. Một nhóm muốn dùng dữ liệu chăm sóc khách hàng để huấn luyện mô hình mới. Bước đầu tiên nên làm gì?
A. Xin quyền truy cập rộng hơn rồi ghi mục đích mới vào audit log.
B. Dùng ngay vì dữ liệu đã được thu thập hợp lệ cho dịch vụ.
C. Chỉ xóa tên trước khi train vì mục đích phân tích luôn tương thích.
D. Đánh giá mục đích mới, tính tương thích và cơ sở xử lý.
Đáp án đúng: D

7. Form chỉ cần xác minh người dùng đủ tuổi nhưng yêu cầu ngày sinh đầy đủ. Cách giảm dữ liệu nào phù hợp?
A. Tính kết quả đủ tuổi ở phía tin cậy và chỉ lưu kết quả cần thiết.
B. Yêu cầu thêm giấy tờ và địa chỉ để tăng độ chính xác xác minh.
C. Mã hóa ngày sinh trước khi lưu nhưng vẫn thu thập nguyên giá trị.
D. Lưu ngày sinh đầy đủ để có thể xác minh lại trong mọi tình huống.
Đáp án đúng: A

8. Client chỉ cần tên hiển thị và trạng thái nhưng API trả toàn bộ hồ sơ. Cách sửa nào phù hợp?
A. Trả entity đầy đủ và yêu cầu client tự bỏ các trường nhạy cảm.
B. Dùng response projection hoặc allowlist field theo mục đích.
C. Ẩn trường trong giao diện nhưng giữ nguyên dữ liệu trong response.
D. Nén payload để giảm lượng dữ liệu truyền qua mạng.
Đáp án đúng: B

9. SDK analytics ghi email và nội dung màn hình vào telemetry. Kiểm soát nào giảm rò rỉ hiệu quả nhất?
A. Mã hóa payload sau khi SDK đã thu thập toàn bộ trường dữ liệu.
B. Giữ nguyên dữ liệu rồi giới hạn quyền xem dashboard phân tích.
C. Chặn hoặc lọc trường nhạy cảm trước khi gửi telemetry.
D. Rút ngắn thời hạn lưu nhưng tiếp tục gửi mọi thuộc tính.
Đáp án đúng: C

10. Đối tác cần đối soát giao dịch nhưng yêu cầu dump toàn bộ bảng khách hàng. Phản hồi nào phù hợp?
A. Gửi bản dump sau khi nén và đặt mật khẩu trong email riêng.
B. Ẩn tên khách hàng nhưng giữ mọi định danh và thuộc tính khác.
C. Gửi toàn bộ bảng vì đối tác đã ký hợp đồng bảo mật dữ liệu.
D. Chia sẻ tập trường tối thiểu cần cho đối soát theo thỏa thuận.
Đáp án đúng: D

11. Môi trường kiểm thử cần dữ liệu đại diện nhưng không cần bản ghi production thật. Cách nào phù hợp?
A. Sao chép production rồi giới hạn quyền đọc của đội QA.
B. Ẩn tên và email trên bản dump nhưng giữ mọi giá trị khác.
C. Dùng một vài bản ghi thật vì dữ liệu tổng hợp thiếu tính thực tế.
D. Tạo dữ liệu tổng hợp có quan hệ và phân bố cần thiết.
Đáp án đúng: D

12. Pseudonymization thay định danh bằng token ổn định. Bảng ánh xạ nên được bảo vệ ra sao?
A. Mã hóa bảng ánh xạ bằng khóa dùng chung với mọi kho dữ liệu.
B. Lưu riêng và giới hạn quyền truy cập bảng ánh xạ.
C. Đặt cùng tập dữ liệu đã thay thế để dễ tái liên kết khi cần.
D. Cấp quyền đọc cho nhóm phân tích để họ tự xử lý dữ liệu.
Đáp án đúng: B

13. Một tập dữ liệu xóa tên và email nhưng vẫn giữ nghề nghiệp hiếm và khu vực nhỏ. Rủi ro chính là gì?
A. Chỉ có nguy cơ nếu khóa mã hóa dữ liệu bị lộ ra ngoài.
B. Tập dữ liệu chỉ rủi ro khi còn giữ số tài khoản hoặc mật khẩu.
C. Dữ liệu luôn được anonymize khi không còn định danh trực tiếp.
D. Có thể tái nhận diện bằng cách liên kết thuộc tính gián tiếp.
Đáp án đúng: D

14. Báo cáo tổng hợp có một nhóm chỉ gồm hai người. Cách giảm suy luận thuộc tính cá nhân nào phù hợp?
A. Cho hiển thị nhóm nhỏ nhưng làm tròn tổng số liệu đến số nguyên.
B. Thêm tên nhóm vào báo cáo để người xem hiểu ngữ cảnh dữ liệu.
C. Ẩn hoặc gộp nhóm nhỏ theo ngưỡng công bố đã xác định.
D. Tăng số bộ lọc để người dùng tự chọn nhóm so sánh phù hợp.
Đáp án đúng: C

15. Một dịch vụ công bố nhiều thống kê gần giống nhau từ cùng dữ liệu cá nhân. Differential privacy cần kiểm soát điều gì?
A. Theo dõi privacy budget và giới hạn truy vấn tích lũy.
B. Bỏ kiểm soát truy vấn vì mỗi kết quả riêng lẻ đã được làm nhiễu.
C. Tăng kích thước mẫu mà không cần theo dõi số lần truy vấn.
D. Chỉ thêm nhiễu ở truy vấn đầu tiên rồi cache mọi biến thể.
Đáp án đúng: A

16. Nhân viên cần đối chiếu bốn số cuối tài khoản nhưng giao diện chỉ cho xem toàn bộ hoặc che hết. Cải tiến nào phù hợp?
A. Hiển thị toàn bộ giá trị trong thời gian ngắn rồi tự ẩn.
B. Che toàn bộ dữ liệu và yêu cầu khách hàng tự xác minh.
C. Cho phép tải bản CSV đầy đủ khi nhân viên có role hỗ trợ.
D. Hiển thị có kiểm soát phần cuối cần cho tác vụ.
Đáp án đúng: D

17. Một log cần liên kết các sự kiện cùng giao dịch mà không lưu số định danh thật. Cách nào phù hợp?
A. Ghi số định danh nguyên bản rồi hạn chế quyền truy cập log.
B. Dùng surrogate identifier hoặc token không tiết lộ giá trị gốc.
C. Băm nhanh số định danh bằng hash không khóa trong mọi trường hợp.
D. Cắt bớt vài ký tự đầu nhưng giữ phần còn lại của định danh.
Đáp án đúng: B

18. Retention period nên được xác định dựa trên yếu tố nào?
A. Khoảng thời gian dài nhất mà nhóm phân tích có thể cần dữ liệu.
B. Dung lượng kho còn trống và tốc độ tăng dữ liệu hàng tháng.
C. Mục đích, nghĩa vụ lưu giữ và nhu cầu vận hành đã chứng minh.
D. Thời hạn mặc định của nền tảng lưu trữ đang được sử dụng.
Đáp án đúng: C

19. Dữ liệu được migration sang kho mới và timestamp tạo bản sao bị cập nhật. Điều gì ngăn retention bị kéo dài ngoài ý muốn?
A. Giữ metadata thời điểm gốc và chuyển tiếp retention policy.
B. Tạo retention schedule mới theo ngày ingest ở kho đích.
C. Tắt job xóa ở nguồn cho đến khi kho mới ổn định hoàn toàn.
D. Dùng timestamp migration làm mốc mới cho toàn bộ bản ghi.
Đáp án đúng: A

20. Yêu cầu xóa đã xử lý ở database chính nhưng dữ liệu còn trong cache, index và replica. Cách nào phù hợp?
A. Đánh dấu bản ghi đã xóa trong database chính và kết thúc yêu cầu.
B. Xóa cache gần nhất vì index và replica sẽ tự đồng bộ ngay.
C. Ẩn kết quả khỏi giao diện nhưng giữ bản sao để phục hồi nhanh.
D. Theo dõi và thực hiện deletion propagation trên mọi bản sao.
Đáp án đúng: D

21. Backup bất biến còn chứa bản ghi đã xóa. Khi restore, làm thế nào tránh dữ liệu quay lại hoạt động?
A. Tạo backup mới ngay sau restore để ghi đè bản backup cũ.
B. Khôi phục nguyên trạng rồi chờ lần xóa định kỳ tiếp theo.
C. Bỏ qua yêu cầu xóa vì backup được bảo vệ chống chỉnh sửa.
D. Áp dụng lại deletion ledger hoặc tombstone sau restore.
Đáp án đúng: D

22. Legal hold được áp dụng cho toàn bộ kho thay vì hồ sơ liên quan. Vấn đề nào cần khắc phục?
A. Chuyển toàn bộ kho sang nhãn Restricted để đáp ứng hold.
B. Giới hạn hold theo phạm vi dữ liệu và thời hạn được phê duyệt.
C. Xóa legal hold khỏi kho và lưu một bản dump riêng biệt.
D. Giữ toàn bộ dữ liệu cho đến khi mọi cuộc điều tra kết thúc.
Đáp án đúng: B

23. Cryptographic erasure được dùng để xóa dữ liệu. Thiết kế khóa nào hỗ trợ xóa đúng phạm vi?
A. Dùng khóa dữ liệu riêng hoặc tách biệt theo tập cần xóa.
B. Dùng một khóa chung để giảm chi phí quản lý và backup.
C. Lưu bản sao khóa trong cùng backup với dữ liệu đã mã hóa.
D. Xoay khóa định kỳ nhưng vẫn giữ mọi khóa cũ để giải mã.
Đáp án đúng: A

24. Một job xóa báo completed dù một partition bị timeout. Cách xác minh nào đáng tin cậy?
A. Xác nhận log không có exception nghiêm trọng trong lần chạy.
B. Tin trạng thái completed do scheduler trả về sau khi chạy job.
C. Kiểm tra một vài dòng ngẫu nhiên trong database chính.
D. Đối soát kết quả theo partition và kiểm tra bản sao liên quan.
Đáp án đúng: D

25. Application log ghi query string chứa email và số hồ sơ. Điểm kiểm soát nào nên áp dụng?
A. Mã hóa log sau khi toàn bộ request đã được ghi ra file.
B. Redact dữ liệu nhạy cảm trước khi ghi hoặc chuyển tiếp log.
C. Chỉ tắt quyền tìm kiếm các trường email trong dashboard.
D. Giữ nguyên log nhưng giới hạn retention xuống một ngày.
Đáp án đúng: B

26. Distributed trace tự động thu thập toàn bộ request header và body. Cách giảm rủi ro phù hợp là gì?
A. Giữ toàn bộ trace nhưng giảm sampling rate của request.
B. Chỉ thu thập attribute allowlist và loại trường nhạy cảm.
C. Chỉ ẩn dữ liệu trong giao diện xem trace sau khi lưu trữ.
D. Bật mã hóa exporter nhưng không thay đổi các attribute được thu thập.
Đáp án đúng: B

27. Audit log cần hỗ trợ điều tra truy cập dữ liệu nhạy cảm. Nguyên tắc ghi nhận nào phù hợp?
A. Ghi actor, hành động, đối tượng và kết quả mà không sao chép giá trị nhạy cảm.
B. Chỉ ghi số lượng request thành công theo từng tài khoản.
C. Ghi toàn bộ bản ghi được đọc để điều tra có đủ nội dung.
D. Ghi access token và payload để liên kết chính xác mọi request.
Đáp án đúng: A

28. Một bản dump production được dùng trong kiểm thử tích hợp. Biện pháp nào giảm nguy cơ lộ dữ liệu?
A. Ẩn tên và email nhưng giữ nguyên ngày sinh và địa chỉ chi tiết.
B. Mask hoặc tổng hợp trước khi đưa dữ liệu vào môi trường test.
C. Mã hóa dump rồi chia khóa giải mã cho toàn bộ nhóm phát triển.
D. Đặt dump trong thư mục dùng chung và giới hạn thời gian truy cập.
Đáp án đúng: B

29. Masking dữ liệu kiểm thử làm hỏng khóa ngoại và phân bố dữ liệu. Cách cải tiến nào phù hợp?
A. Thay mỗi trường bằng chuỗi ngẫu nhiên độc lập không lưu mapping.
B. Giữ nguyên khóa chính và chỉ thay đổi vài trường hiển thị.
C. Dùng masking nhất quán và bảo toàn quan hệ cùng đặc tính cần test.
D. Dùng dữ liệu production nguyên bản để bảo toàn mọi quan hệ.
Đáp án đúng: C

30. Dữ liệu tổng hợp được tạo để kiểm thử nhưng vô tình tái tạo bản ghi thật. Cần kiểm tra điều gì?
A. So sánh dung lượng file với bản production để bảo đảm tương đương.
B. Chỉ kiểm tra schema và số lượng dòng có đúng yêu cầu không.
C. Đánh giá nguy cơ memorization và khả năng trùng với dữ liệu nguồn.
D. Xác nhận generator chạy thành công và không tạo giá trị null.
Đáp án đúng: C

31. Nhà cung cấp dùng subprocessor để xử lý dữ liệu khách hàng. Điều kiện nào nên được quản lý?
A. Mục đích, phạm vi, thời hạn và nghĩa vụ xóa của từng bên nhận.
B. Quyền tự quyết định retention của subprocessor theo nền tảng.
C. Chỉ địa điểm đặt trung tâm dữ liệu và dung lượng lưu trữ.
D. Chỉ tên nhà cung cấp chính và thời hạn hợp đồng tổng thể.
Đáp án đúng: A

32. Classification label bị mất khi file được export rồi import vào kho khác. Kiểm soát nào ngăn việc hạ nhãn ngoài ý muốn?
A. Gán mọi file nhập mới thành Internal để tránh chặn pipeline.
B. Dựa vào thư mục upload để suy ra nhãn phù hợp của file.
C. Gắn nhãn vào metadata mang theo và xác minh khi ingest.
D. Yêu cầu người dùng chọn nhãn sau khi file đã được chia sẻ.
Đáp án đúng: C

33. Một schema mới thêm trường nhạy cảm nhưng thiếu owner và purpose tag. Policy-as-code nên làm gì?
A. Chặn hoặc yêu cầu phê duyệt trước khi schema được triển khai.
B. Chỉ cảnh báo trên dashboard mà không ảnh hưởng quy trình deploy.
C. Cho phép deploy rồi tạo ticket bổ sung metadata sau phát hành.
D. Tự gán nhãn Public để pipeline không bị gián đoạn.
Đáp án đúng: A

34. Tính năng mới bổ sung nguồn dữ liệu và bên nhận sau khi DPIA đã hoàn tất. Cần làm gì?
A. Đánh giá lại tác động theo thay đổi mục đích và luồng dữ liệu.
B. Chỉ cập nhật sơ đồ kiến trúc mà không xem xét rủi ro mới.
C. Chờ đánh giá định kỳ hằng năm để tránh làm chậm phát hành.
D. Giữ nguyên DPIA vì tính năng đã qua phê duyệt ban đầu.
Đáp án đúng: A

35. Người dùng rút lại sự đồng ý cho mục đích marketing. Hệ thống cần cập nhật điều gì?
A. Chỉ ẩn hồ sơ trong giao diện marketing và giữ các export cũ.
B. Xóa tài khoản chính nhưng không cần thông báo cho processor.
C. Trạng thái mục đích và các bản sao hoặc bên nhận phụ thuộc.
D. Giữ nguyên dữ liệu và đổi nhãn từ Confidential sang Internal.
Đáp án đúng: C

36. Một tổ chức cần chứng minh dữ liệu đã được xóa khỏi nhiều hệ thống và processor. Bằng chứng nào hữu ích nhất?
A. Kết quả đối soát theo hệ thống, bản sao, thời điểm và bên xử lý.
B. Ảnh chụp màn hình cho thấy bản ghi không còn trong giao diện.
C. Một log duy nhất từ job xóa tại database chính.
D. Email xác nhận chung của quản trị viên kho lưu trữ.
Đáp án đúng: A
