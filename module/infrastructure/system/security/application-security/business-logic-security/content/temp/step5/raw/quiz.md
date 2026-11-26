1. API nhận request đổi trạng thái đơn hàng sang `Approved`. Backend nên xác định transition hợp lệ bằng cách nào?
A. Kiểm tra trạng thái cũ trong giao diện rồi tin giá trị hidden field gửi lên.
B. Tải trạng thái từ server và kiểm tra transition theo state machine.
C. Cho phép mọi transition nếu request có chữ ký hợp lệ của người dùng đăng nhập.
D. Chấp nhận trạng thái client gửi nếu user có quyền gọi endpoint cập nhật đơn.
Đáp án đúng: B

2. Yêu cầu mua hàng đã được duyệt nhưng người tạo sửa số tiền trước khi thực thi. Cách bảo vệ quyết định phê duyệt phù hợp là gì?
A. Giữ trạng thái Approved và chỉ ghi nhận số tiền mới trong audit log.
B. Cho phép sửa số tiền nếu người tạo vẫn giữ role Requester trên hệ thống.
C. Chỉ khóa nút sửa trên giao diện cho tới khi bộ phận tài chính thực thi.
D. Gắn phê duyệt với phiên bản dữ liệu; thay đổi thì duyệt lại.
Đáp án đúng: D

3. API hủy đơn nhận `orderId` từ client. Kiểm tra nào ngăn IDOR hiệu quả nhất?
A. Ẩn orderId trên giao diện và dùng UUID khó đoán cho các đơn hàng.
B. Xác minh user có role Customer trước khi xử lý mọi orderId được gửi.
C. Kiểm tra order tồn tại và trạng thái Pending trước khi hủy.
D. Tải đơn trong tenant hợp lệ và kiểm tra quyền hủy trên chính đơn.
Đáp án đúng: D

4. API cập nhật hồ sơ cho phép client gửi thêm `creditLimit` và `riskStatus`. Cách sửa nào phù hợp?
A. Cho phép mọi field nhưng chỉ ghi nhận thay đổi nhạy cảm trong audit log.
B. Ẩn hai field khỏi response để client không biết chúng tồn tại trong model.
C. Dùng allowlist field và lệnh riêng cho thuộc tính đặc quyền ở backend.
D. Bind toàn bộ JSON vào entity rồi loại các field lạ ở tầng giao diện.
Đáp án đúng: C

5. Nhân viên có thể tạo và tự duyệt yêu cầu hoàn ứng vì có cả hai role. Kiểm soát nào cần thiết?
A. Yêu cầu hai request dùng hai session khác nhau dù cùng một tài khoản.
B. So sánh người tạo và người duyệt theo cùng principal.
C. Chỉ kiểm tra role Approver ở endpoint duyệt và tin assignment hiện có.
D. Ghi cảnh báo sau khi duyệt để quản lý rà soát các trường hợp trùng người.
Đáp án đúng: B

6. Một quy trình cần hai người phê duyệt độc lập nhưng một nhân viên dùng hai tài khoản để chiếm cả hai bước. Cần ràng buộc theo gì?
A. Hai role khác nhau được gán cho hai tài khoản trong cùng directory.
B. Ràng buộc hai bước theo danh tính nhân sự duy nhất, không theo account.
C. Tên đăng nhập khác nhau và hai phiên đăng nhập không dùng chung cookie.
D. Địa chỉ IP khác nhau để xác định hai người phê duyệt riêng biệt.
Đáp án đúng: B

7. Client gửi `unitPrice` thấp hơn giá đã báo khi xác nhận thanh toán. Nguồn giá nào nên được backend sử dụng?
A. Giá cache tại gateway vì gateway nhận request trước các service khác.
B. Giá lịch sử của sản phẩm tại thời điểm user mở trang chi tiết lần đầu.
C. Dùng quote hoặc catalog server còn hiệu lực cho order.
D. Giá client gửi nếu tổng tiền khớp với phép nhân số lượng và đơn giá.
Đáp án đúng: C

8. Coupon chỉ còn một lượt nhưng hai request đồng thời cùng vượt qua bước đọc quota. Cách enforce nào phù hợp?
A. Trừ quota nguyên tử trong transaction khi còn lượt.
B. Đọc quota trong service rồi ghi giảm sau khi cả hai request hoàn tất.
C. Tăng cache TTL để các request đồng thời dùng chung một giá trị quota.
D. Giới hạn tốc độ tại API gateway nhưng vẫn kiểm tra quota ở bước đọc riêng.
Đáp án đúng: A

9. Kho còn một sản phẩm nhưng hai đơn đồng thời cùng được xác nhận. Cách bảo vệ invariant tồn kho nào tốt nhất?
A. Chạy job đối soát cuối ngày để hủy các đơn vượt quá số lượng tồn kho.
B. Đọc tồn kho trước, rồi trừ ở transaction sau khi tạo đơn.
C. Dùng atomic update hoặc lock để trừ kho có điều kiện đủ số lượng.
D. Kiểm tra tồn kho ở giao diện và từ chối đơn khi trình duyệt hiển thị zero.
Đáp án đúng: C

10. Nhiều yêu cầu hoàn tiền cùng tham chiếu một payment. Invariant nào cần được enforce nguyên tử?
A. Mỗi nhân viên chỉ được tạo một refund trong một phiên đăng nhập.
B. Tổng refund không vượt số tiền đã capture, kể cả phần đang giữ chỗ.
C. Mỗi refund phải nhỏ hơn payment gốc khi xét riêng từng request.
D. Mỗi request refund có ID khác nhau và amount không âm trước khi lưu.
Đáp án đúng: B

11. Hai request chuyển tiền cùng đọc một số dư rồi cùng debit, dẫn đến số dư âm. Cách xử lý nào phù hợp?
A. Đọc số dư trước transaction và tăng isolation chỉ ở truy vấn báo cáo.
B. Debit có điều kiện số dư đủ trong transaction hoặc khóa bản ghi.
C. Kiểm tra số dư trong cache rồi ghi hai debit bằng request riêng biệt.
D. Retry mọi lỗi ghi dữ liệu mà không đọc lại số dư hiện tại.
Đáp án đúng: B

12. Client đổi `currencyCode` từ USD sang VND nhưng giữ nguyên con số amount. Backend nên làm gì?
A. Xác thực currency và amount như một cặp, dùng quote tỷ giá có thẩm quyền.
B. Chuyển currency sau khi thanh toán và điều chỉnh chênh lệch ở báo cáo.
C. Chấp nhận currency mới vì amount là số nguyên và không có phần thập phân.
D. Tự suy ra currency theo locale trình duyệt rồi giữ nguyên amount client gửi.
Đáp án đúng: A

13. Các service tính phí bằng số thực và làm tròn khác nhau. Cách nào giảm sai lệch có thể bị khai thác?
A. Lưu tổng tiền dạng chuỗi để tránh database tự chuyển đổi kiểu số.
B. Làm tròn từng thành phần theo locale của client trước khi gửi backend.
C. Dùng floating point ở mọi service và làm tròn riêng theo giao diện hiển thị.
D. Dùng decimal hoặc minor units cùng một quy tắc làm tròn được định nghĩa rõ.
Đáp án đúng: D

14. Client timeout sau khi payment thành công rồi retry cùng idempotency key. Backend nên phản hồi thế nào?
A. Tạo payment mới vì request retry có một HTTP request ID khác.
B. Từ chối mọi retry sau timeout để tránh phải kiểm tra trạng thái giao dịch.
C. Gọi lại cổng thanh toán rồi so sánh hai kết quả sau khi hoàn tất.
D. Trả lại kết quả đã lưu cho key đó mà không thực hiện side effect lần nữa.
Đáp án đúng: D

15. Cùng idempotency key được gửi lại với payload amount khác lần đầu. Cách xử lý nào đúng?
A. Tạo key mới tự động từ amount để request tiếp tục được thực hiện.
B. Từ chối xung đột vì key đã gắn với fingerprint payload ban đầu.
C. Trả kết quả cũ nhưng ghi đè payload mới vào bản ghi idempotency hiện tại.
D. Coi đây là request mới nếu timestamp hoặc địa chỉ IP đã thay đổi.
Đáp án đúng: B

16. Hai request đồng thời dùng cùng idempotency key và cùng payload. Cơ chế nào ngăn cả hai cùng thực thi?
A. Claim key nguyên tử bằng unique constraint hoặc lock trong transaction.
B. Dùng UUID cho payment record nhưng không ràng buộc idempotency key.
C. Chỉ khóa theo user ID ở gateway trong thời gian nhận request.
D. Kiểm tra key trong cache rồi để từng request tự ghi kết quả sau xử lý.
Đáp án đúng: A

17. Gọi cổng thanh toán bị timeout và không rõ provider đã thu tiền hay chưa. Retry an toàn nên dựa vào gì?
A. Tạo payment intent mới để tránh chờ kết quả của lần gọi bị timeout.
B. Retry liên tục với request ID mới cho tới khi nhận HTTP response thành công.
C. Dùng provider idempotency key và đối soát trạng thái trước retry.
D. Đánh dấu payment thất bại ngay khi client timeout rồi cho phép thanh toán lại.
Đáp án đúng: C

18. Webhook `PaymentCaptured` có thể được gửi nhiều lần. Cách xử lý nào tránh tạo nhiều tác động nghiệp vụ?
A. Chỉ kiểm tra chữ ký webhook vì chữ ký hợp lệ chứng minh event chưa xử lý.
B. Dựa vào timestamp để bỏ mọi webhook đến sau event đầu tiên của payment.
C. Từ chối webhook trùng theo IP nguồn mà không lưu event identifier.
D. Ghi event ID duy nhất cùng side effect trong transaction.
Đáp án đúng: D

19. Database đã cập nhật Order nhưng publish event thất bại. Mẫu thiết kế nào giúp đồng bộ trạng thái và sự kiện?
A. Dùng cron quét bảng Order và suy ra mọi event cần gửi từ trạng thái hiện tại.
B. Ghi thay đổi nghiệp vụ và outbox record trong cùng database transaction.
C. Đặt hai thao tác trong cùng một HTTP request để chúng thành transaction phân tán.
D. Publish event trước rồi cập nhật Order nếu broker xác nhận nhận message.
Đáp án đúng: B

20. Consumer xử lý message thành công nhưng ACK bị mất, broker gửi lại message. Cách nào tránh side effect lặp?
A. Dùng inbox hoặc deduplication record nguyên tử với thay đổi nghiệp vụ.
B. Tắt redelivery của broker và bỏ message khi consumer không ACK đúng hạn.
C. Dùng timestamp message để loại mọi message đến sau một khoảng thời gian ngắn.
D. ACK trước khi xử lý để broker không gửi lại trong mọi trường hợp.
Đáp án đúng: A

21. Consumer nhận `OrderCancelled` version 8 rồi nhận event `OrderApproved` version 7 muộn. Nên xử lý ra sao?
A. Đưa order về trạng thái Approved rồi chạy job sửa lại khi có event mới.
B. Luôn áp dụng event đến sau cùng vì thứ tự nhận là thứ tự nghiệp vụ.
C. Dùng timestamp máy gửi để ghi đè trạng thái bất kể version của order.
D. So sánh version và bỏ event cũ hơn trạng thái hiện tại.
Đáp án đúng: D

22. Saga đã trừ tiền nhưng bước cấp kho thất bại và thao tác hoàn tiền cũng timeout. Cách xử lý nào phù hợp?
A. Đánh dấu saga hoàn tất vì bước cấp kho đã báo lỗi vĩnh viễn.
B. Lưu compensation pending để retry và đối soát tới khi hoàn tất.
C. Gửi lệnh hoàn tiền mới với ID khác mỗi lần timeout để tăng cơ hội thành công.
D. Rollback database của service thanh toán để xóa dấu vết lần trừ tiền.
Đáp án đúng: B

23. Người dùng bị thu hồi quyền sau khi yêu cầu được duyệt nhưng trước lúc Execute chạy. Backend nên kiểm tra gì?
A. Tin quyết định phê duyệt cũ vì quyền đã được xác nhận khi tạo request.
B. Đánh giá lại quyền và điều kiện nghiệp vụ tại thời điểm thực thi.
C. Chỉ kiểm tra session còn hiệu lực và user đã xác thực.
D. Dựa vào role trong cache của bước duyệt để giữ hành vi nhất quán.
Đáp án đúng: B

24. Job nền dùng service account rộng để xử lý hành động thay mặt user đã mất quyền truy cập. Rủi ro nào cần khắc phục?
A. Chỉ kiểm tra user còn active trong directory khi job chạy.
B. Tăng quyền service account để job không bị lỗi khi user rời hệ thống.
C. Bỏ actor khỏi audit log vì job kỹ thuật là chủ thể thực hiện trực tiếp.
D. Giữ actor context và kiểm tra lại quyền trên object lúc chạy.
Đáp án đúng: D

25. Bulk import gồm 500 dòng, trong đó có tài nguyên thuộc tenant khác. Authorization nên được thực hiện thế nào?
A. Chỉ kiểm tra quyền trên dòng đầu tiên vì các dòng thuộc cùng một batch.
B. Chấp nhận toàn bộ rồi lọc các dòng sai tenant trong báo cáo sau import.
C. Kiểm tra tenant và quyền cho từng đối tượng trong batch.
D. Chỉ xác minh tenant của file upload rồi tin tất cả ID trong nội dung.
Đáp án đúng: C

26. Người dùng chia một giao dịch lớn thành nhiều giao dịch nhỏ để né ngưỡng phê duyệt. Kiểm soát nào phù hợp?
A. Gom giao dịch theo chủ thể, đối tượng và cửa sổ thời gian.
B. Chỉ tăng hạn mức của mỗi request để người dùng ít phải gửi nhiều lần.
C. Chỉ kiểm tra amount từng giao dịch vì mỗi giao dịch đều dưới ngưỡng.
D. Chặn mọi giao dịch liên tiếp của cùng user bất kể đối tượng và mục đích.
Đáp án đúng: A

27. Quota rút tiền theo ngày bị vượt khi client thay timezone trong request. Nguồn thời gian nào nên được dùng?
A. Dùng ngày UTC cho mọi sản phẩm dù hợp đồng quy định ngày địa phương.
B. Dùng timezone client vì người dùng cần tự chọn ngày bắt đầu hạn mức.
C. Dùng thời gian nhận request tại từng service mà không đồng bộ quy tắc.
D. Dùng timezone và lịch nghiệp vụ do server quy định.
Đáp án đúng: D

28. Feature flag trong production có thể tắt kiểm tra hạn mức nhưng không có audit. Kiểm soát nào cần bổ sung?
A. Cho phép mọi operator đổi flag nhưng gửi email tổng hợp vào cuối tháng.
B. Cache flag lâu hơn để thay đổi cấu hình ít ảnh hưởng các request đang chạy.
C. Giới hạn người sửa, yêu cầu phê duyệt độc lập và audit mọi lần đổi flag.
D. Ẩn flag khỏi dashboard và chỉ cho phép thay đổi bằng request nội bộ.
Đáp án đúng: C

29. Endpoint REST kiểm tra invariant nhưng cùng nghiệp vụ còn được gọi qua GraphQL, batch và message consumer. Cách nào bảo đảm nhất quán?
A. Đặt invariant tại lớp nghiệp vụ dùng chung và kiểm thử mọi entry point.
B. Sao chép cùng một đoạn kiểm tra vào từng controller và consumer handler.
C. Chỉ bảo vệ REST vì các entry point nội bộ được xem là đáng tin cậy.
D. Chặn batch và consumer truy cập database trực tiếp nhưng bỏ kiểm tra service.
Đáp án đúng: A

30. Hai request cùng cập nhật một đơn dựa trên version 12. Cách nào phát hiện một request đã dùng dữ liệu cũ?
A. Dùng update theo version và xử lý conflict khi không khớp.
B. Cho phép ghi đè rồi đối soát sau khi cập nhật xong.
C. Ghi cả hai bản cập nhật rồi dùng timestamp mới hơn để chọn kết quả.
D. Dùng cache để khóa đơn trong một instance ứng dụng duy nhất.
Đáp án đúng: A

31. Coupon chỉ được dùng một lần cho mỗi user. Kiểm soát nào bảo vệ invariant khi nhiều request đến đồng thời?
A. Ẩn coupon sau lần đầu người dùng bấm Apply trên giao diện mua hàng.
B. Đặt rate limit theo IP để ngăn user gửi nhiều request song song.
C. Kiểm tra lịch sử sử dụng ở ứng dụng rồi ghi redemption trong transaction khác.
D. Unique constraint theo user và coupon, kết hợp transaction redemption.
Đáp án đúng: D

32. Nhân viên sửa tài khoản ngân hàng của nhà cung cấp sau khi hóa đơn đã duyệt. Điều gì cần ràng buộc?
A. Chỉ kiểm tra user sửa có role Vendor Editor trước khi lưu tài khoản mới.
B. Giữ hóa đơn Approved và ghi tài khoản ngân hàng mới vào audit log.
C. Gắn approval với phiên bản thông tin thanh toán và yêu cầu duyệt lại khi đổi.
D. Khóa toàn bộ hồ sơ nhà cung cấp ngay khi một hóa đơn được duyệt.
Đáp án đúng: C

33. Một workflow có nhiều bước và side effect không được lặp khi endpoint hoàn tất bị gọi lại. Cách nào phù hợp?
A. Tạo một bản ghi workflow mới cho mỗi request hoàn tất để tách side effect.
B. Trả HTTP 200 cho mọi request lặp mà không kiểm tra trạng thái hiện tại.
C. Dùng transition nguyên tử và side effect idempotent cho mỗi transition.
D. Dựa vào frontend disable nút Complete sau lần click đầu tiên.
Đáp án đúng: C

34. Một service tính điểm loyalty dựa trên tổng trước giảm giá dù chính sách yêu cầu số tiền thực thu. Cần sửa gì?
A. Tính điểm từ amount thực thu theo quy tắc công bố của chương trình.
B. Tính điểm ở từng service theo dữ liệu sẵn có rồi cộng kết quả cuối.
C. Chỉ cập nhật công thức trên báo cáo vì điểm đã ghi không ảnh hưởng quyền lợi.
D. Dùng subtotal do client gửi để khớp số tiền người dùng nhìn thấy.
Đáp án đúng: A

35. Muốn kiểm thử lạm dụng state machine qua chuỗi tạo, sửa, duyệt, hủy và thực thi, phương pháp nào phù hợp?
A. Chỉ test từng endpoint độc lập với một trạng thái hợp lệ được chuẩn bị sẵn.
B. Chạy happy path trên giao diện và xác nhận các nút hiển thị đúng thứ tự.
C. Model-based test sinh chuỗi transition và kiểm tra invariant.
D. Kiểm tra response code của từng API mà không đọc trạng thái lưu trữ cuối.
Đáp án đúng: C

36. Test concurrency cần tái hiện hai request cùng tranh chấp lượt cuối của quota. Cách nào đáng tin cậy?
A. Dùng barrier đồng bộ request rồi xác minh chỉ một claim thành công.
B. Mock database response giống nhau cho hai request mà không chạy transaction thật.
C. Gửi hai request tuần tự nhanh nhất có thể từ cùng một test client.
D. Chạy test nhiều lần và giả định xác suất gặp race condition sẽ đủ cao.
Đáp án đúng: A
