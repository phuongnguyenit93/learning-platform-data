1. Mục tiêu chính của DPAPI là gì?
A. Bảo vệ dữ liệu theo ngữ cảnh Windows.
B. Quản lý quyền truy cập mạng cho mọi tiến trình Windows.
C. Thay thế mã hóa ổ đĩa cho toàn bộ thiết bị.
D. Cấp và thu hồi chứng thư số cho ứng dụng desktop.
Đáp án đúng: A

2. CryptProtectData thực hiện thao tác nào?
A. Giải mã blob và trả về dữ liệu ban đầu.
B. Tạo chứng thư X.509 cho tài khoản đăng nhập.
C. Sao lưu master key của user lên domain controller.
D. Mã hóa DATA_BLOB và trả về blob được bảo vệ.
Đáp án đúng: D

3. CryptUnprotectData được dùng khi nào?
A. Tạo blob mới từ dữ liệu plaintext.
B. Cấp quyền đọc file cho nhóm Windows.
C. Giải mã blob đã được DPAPI bảo vệ.
D. Xoay vòng chứng thư TLS của máy chủ.
Đáp án đúng: C

4. Nếu không đặt CRYPTPROTECT_LOCAL_MACHINE, DPAPI mặc định gắn bảo vệ với gì?
A. Mọi tài khoản cục bộ trên cùng máy tính.
B. Ngữ cảnh user đã thực hiện thao tác bảo vệ.
C. Một nhóm Active Directory được chọn khi khởi tạo.
D. Danh tính máy chủ DNS của mạng hiện tại.
Đáp án đúng: B

5. CRYPTPROTECT_LOCAL_MACHINE thay đổi phạm vi giải mã ra sao?
A. User trên máy có thể unprotect nếu đọc được blob.
B. Chỉ tài khoản tạo blob mới giải mã được trên máy.
C. Cho phép mọi máy trong domain giải mã cùng blob.
D. Chỉ tài khoản SYSTEM mới giải mã được blob.
Đáp án đúng: A

6. Khi dùng machine scope, kiểm soát nào vẫn cần áp dụng cho file blob?
A. Mã hóa lại blob bằng password riêng từng user.
B. Đổi tên file theo SID của tài khoản đang chạy.
C. Đặt blob trong thư mục công khai cho mọi service.
D. ACL giới hạn tài khoản nào có thể đọc blob.
Đáp án đúng: D

7. Optional entropy trong CryptProtectData có ý nghĩa gì?
A. Thay thế master key Windows dùng nội bộ.
B. Tạo salt tự động lưu trong blob để giải mã.
C. Bổ sung entropy do ứng dụng cung cấp.
D. Đặt tên hiển thị cho blob trong giao diện.
Đáp án đúng: C

8. Ứng dụng đã dùng optional entropy khi bảo vệ blob. Điều gì cần khi unprotect?
A. Cung cấp đúng cùng giá trị entropy đã dùng.
B. Tạo entropy mới có cùng độ dài với giá trị cũ.
C. Để entropy rỗng vì Windows đã lưu giá trị đó.
D. Dùng password đăng nhập thay entropy ban đầu.
Đáp án đúng: A

9. Description của CryptProtectData nên được sử dụng thế nào?
A. Lưu khóa giải mã để người dùng khôi phục.
B. Làm nhãn mô tả blob, không dùng như bí mật.
C. Xác định principal duy nhất được unprotect blob.
D. Thay entropy phụ và làm khóa mật mã.
Đáp án đúng: B

10. DPAPI blob có thể được xem là cơ chế lưu trữ hoàn chỉnh không?
A. Có; DPAPI tự quản lý database và vòng đời blob.
B. Có; blob tự đồng bộ tới mọi máy cùng domain.
C. Không; DPAPI chỉ bảo vệ dữ liệu truyền mạng.
D. Không; ứng dụng vẫn tự lưu blob và đặt ACL.
Đáp án đúng: D

11. DPAPI có bảo vệ bí mật trước malware chạy cùng user đã đăng nhập không?
A. Có; chỉ tiến trình ký số mới được unprotect.
B. Có; DPAPI yêu cầu MFA mỗi lần giải mã.
C. Không; malware cùng user có thể gọi unprotect.
D. Có; blob chỉ giải mã sau khi khởi động lại máy.
Đáp án đúng: C

12. Ứng dụng desktop lưu token bằng DPAPI user scope. Khi nào token thường có thể được unprotect?
A. Khi bất kỳ user nào đăng nhập trên máy đó.
B. Khi ứng dụng chạy trong đúng ngữ cảnh user.
C. Khi tiến trình chạy bằng tài khoản mạng bất kỳ.
D. Khi ứng dụng được sao chép sang máy bất kỳ.
Đáp án đúng: B

13. Windows service dùng DPAPI user scope nhưng không nạp user profile. Rủi ro nào cần điều tra?
A. DPAPI tự chuyển sang machine scope khi thiếu profile.
B. Windows tự tạo domain backup key cho service.
C. Blob được giải mã bằng tài khoản tương tác gần nhất.
D. Profile chưa nạp có thể khiến user-scope DPAPI lỗi.
Đáp án đúng: D

14. Điều gì thường xảy ra khi user đổi password theo quy trình bình thường?
A. Mọi DPAPI blob bị xóa ngay khi password thay đổi.
B. DPAPI tự chuyển tất cả blob sang machine scope.
C. Windows cập nhật bảo vệ master key khi đổi password.
D. Mọi blob được mã hóa lại bằng password mới tại chỗ.
Đáp án đúng: C

15. Administrative password reset có thể ảnh hưởng DPAPI user data thế nào?
A. Reset admin có thể làm mất quyền giải mã.
B. Luôn giải mã và mã hóa lại mọi blob tự động.
C. Không ảnh hưởng vì DPAPI chỉ dựa trên SID user.
D. Chỉ ảnh hưởng machine-scope blob trên máy domain joined.
Đáp án đúng: A

16. Domain DPAPI backup key hỗ trợ tình huống nào?
A. Khôi phục master key user trong domain.
B. Khôi phục mọi password plaintext trong Active Directory.
C. Giải mã mọi machine-scope blob từ bất kỳ máy nào.
D. Thay private key TLS của domain controller.
Đáp án đúng: A

17. Khi backup dữ liệu DPAPI user scope, thành phần nào cần được tính đến?
A. Chỉ file blob vì mọi key material nằm trong đó.
B. Blob, user profile và recovery material.
C. Chỉ password hiện tại, không cần hồ sơ user.
D. Chỉ SID user vì Windows tái tạo mọi master key.
Đáp án đúng: B

18. Vì sao machine-scope blob thường không giải mã được sau khi chuyển sang máy khác?
A. Blob chỉ hợp lệ trong cùng phiên đăng nhập tương tác.
B. Blob được mã hóa bằng địa chỉ MAC của card mạng.
C. Blob chỉ giải mã nếu hostname không thay đổi.
D. Blob gắn với material bảo vệ của máy đã tạo nó.
Đáp án đúng: D

19. DPAPI machine scope phù hợp với tình huống nào?
A. Chia sẻ bí mật giữa máy không liên quan trên Internet.
B. Dùng chung blob giữa các service cùng máy.
C. Đồng bộ password người dùng giữa domain độc lập.
D. Phát hành credential dùng chung cho mọi máy trạm.
Đáp án đúng: B

20. DPAPI có cung cấp toàn vẹn cho blob được bảo vệ không?
A. Không; DPAPI chỉ mã hóa và bỏ qua sửa đổi.
B. Có; nhưng chỉ khi ứng dụng tự thêm CRC.
C. Có; sửa blob thường khiến unprotect thất bại.
D. Không; ứng dụng phải ký blob bằng certificate.
Đáp án đúng: C

21. CRYPTPROTECT_UI_FORBIDDEN hữu ích nhất trong môi trường nào?
A. Ngăn UI prompt trong tác vụ chạy nền.
B. Ứng dụng bắt buộc user xác nhận mỗi lần protect.
C. Dịch vụ cần prompt khi không có desktop session.
D. Ứng dụng muốn user bỏ qua kiểm tra integrity.
Đáp án đúng: A

22. Vì sao prompt tương tác không phù hợp với Windows service chạy nền?
A. Service không được phép gọi API mã hóa.
B. Prompt tự chuyển service sang tài khoản LocalMachine.
C. Service không thể đọc dữ liệu từ DATA_BLOB.
D. Service không có desktop session để trả lời prompt.
Đáp án đúng: D

23. Sau khi CryptUnprotectData trả plaintext trong output DATA_BLOB, ứng dụng nên làm gì?
A. Giữ buffer vĩnh viễn để lần sau không cần unprotect.
B. Ghi plaintext vào log để xác minh kết quả.
C. Giải phóng buffer output sau khi đọc xong.
D. Chuyển buffer cho tiến trình khác không kiểm soát.
Đáp án đúng: C

24. Vì sao nên giảm thời gian plaintext tồn tại trong bộ nhớ?
A. Giúp DPAPI tự xoay vòng master key nhanh hơn.
B. Ngăn hệ điều hành tạo user profile cho ứng dụng.
C. Làm blob có thể giải mã trên máy khác.
D. Giảm nguy cơ lộ plaintext qua memory dump.
Đáp án đúng: D

25. Ứng dụng nên xử lý lỗi CryptUnprotectData như thế nào?
A. Coi blob lỗi là plaintext và tiếp tục sử dụng.
B. Kiểm tra kết quả và lấy mã lỗi hệ thống để chẩn đoán.
C. Thử lần lượt password của mọi user trên máy.
D. Bỏ qua lỗi rồi dùng output chưa xác thực.
Đáp án đúng: B

26. DPAPI-NG mở rộng mô hình bảo vệ dữ liệu theo hướng nào?
A. Chỉ mã hóa dữ liệu cho user đang đăng nhập.
B. Thay DPAPI bằng dịch vụ sao lưu Windows tự động.
C. Bảo vệ dữ liệu cho principal được mô tả trong descriptor.
D. Cấp quyền truy cập mạng dựa trên IP máy.
Đáp án đúng: C

27. API nào thuộc nhóm DPAPI-NG để bảo vệ và giải bảo vệ dữ liệu?
A. CryptProtectData và CryptUnprotectData với LocalMachine.
B. NCryptProtectSecret và NCryptUnprotectSecret.
C. CertProtectData và CertUnprotectData trong certificate store.
D. EncryptFile và DecryptFile trong Windows file system.
Đáp án đúng: B

28. Protection descriptor trong DPAPI-NG dùng để xác định điều gì?
A. Principal hoặc nhóm được phép unprotect dữ liệu.
B. Thuật toán nén và định dạng file blob đầu ra.
C. Thư mục mặc định lưu master key người dùng.
D. Tên máy chủ sẽ chạy ứng dụng giải mã.
Đáp án đúng: A

29. Khi cần chia sẻ secret cho một nhóm domain, DPAPI-NG có lợi thế nào?
A. Bảo vệ blob theo nhóm principal được chỉ định.
B. Mọi thành viên domain tự giải mã mọi blob không cần policy.
C. Không cần xác thực danh tính principal nhận dữ liệu.
D. Tự phân phối plaintext tới mọi máy khi user đăng nhập.
Đáp án đúng: A

30. DPAPI-NG khác DPAPI truyền thống chủ yếu ở điểm nào?
A. DPAPI-NG chỉ mã hóa file còn DPAPI mã hóa token.
B. DPAPI-NG bỏ qua xác thực blob để tăng tốc.
C. DPAPI-NG chỉ chạy khi ứng dụng có quyền LocalSystem.
D. Chỉ định principal được phép giải mã blob.
Đáp án đúng: D

31. Khi chọn giữa DPAPI user scope và DPAPI-NG, yếu tố nào quan trọng?
A. Chỉ kích thước blob và số byte plaintext đầu vào.
B. Tên giao diện desktop và loại file được lưu trữ.
C. Xét principal cần truy cập và môi trường.
D. Số lượng cửa sổ UI ứng dụng cần hiển thị.
Đáp án đúng: C

32. DPAPI có nên được dùng thay một secret manager tập trung không?
A. Có; DPAPI tự cấp phát, rotate và audit mọi credential.
B. Có; DPAPI tự phân phối secret tới cloud workload.
C. Không; DPAPI không thay secret manager.
D. Không; DPAPI chỉ dùng để ký số tài liệu Office.
Đáp án đúng: C

33. Khi thiết kế phục hồi DPAPI, điều gì cần kiểm thử định kỳ?
A. Chỉ kiểm tra file blob có tồn tại sau backup.
B. Khôi phục profile, master key cùng blob.
C. Chỉ đăng nhập user bằng password trên máy nguồn.
D. Chỉ kiểm tra app khởi động mà không giải mã.
Đáp án đúng: B

34. DPAPI có tự giới hạn ứng dụng nào được gọi unprotect trong cùng user không?
A. Có; chỉ app cùng tên file với blob được phép.
B. Có; DPAPI kiểm tra publisher certificate của caller.
C. Không; chỉ khi blob đặt trong thư mục Windows.
D. Không; cần ACL, isolation và kiểm soát tiến trình.
Đáp án đúng: D

35. Ứng dụng cần bảo vệ blob nhưng cũng muốn audit ai đọc bí mật. Nên làm gì?
A. Dựa vào blob DPAPI để tự ghi mọi lần unprotect.
B. Audit ở ứng dụng và kiểm soát truy cập storage.
C. Đưa plaintext vào Windows Event Log sau mỗi lần đọc.
D. Dùng description làm nhật ký truy cập đầy đủ.
Đáp án đúng: B

36. Khi chuyển ứng dụng sang máy mới, chiến lược nào an toàn cho DPAPI data?
A. Migration cần xét scope và khả năng khôi phục key.
B. Chép blob sang máy mới và giả định giải mã thành công.
C. Đổi hostname máy mới thành hostname cũ để dùng blob.
D. Đổi tên blob để Windows tạo master key tương thích.
Đáp án đúng: A
