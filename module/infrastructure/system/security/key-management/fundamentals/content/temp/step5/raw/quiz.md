1. Mục tiêu chính của quản lý vòng đời khóa mật mã là gì?
A. Kiểm soát khóa suốt vòng đời, từ tạo đến hủy.
B. Tập trung mọi khóa vào một tài khoản để dễ vận hành.
C. Giữ khóa không đổi để mọi hệ thống luôn tương thích.
D. Chỉ bảo vệ khóa khi dữ liệu đang được truyền qua mạng.
Đáp án đúng: A

2. Nguồn nào phù hợp để tạo key material cho hệ thống mật mã?
A. Bộ sinh số giả ngẫu nhiên thông thường có seed cố định.
B. Timestamp hiện tại ghép với tên máy chủ triển khai.
C. Hash của username và tên ứng dụng đang sử dụng khóa.
D. CSPRNG của nền tảng mật mã với entropy phù hợp.
Đáp án đúng: D

3. Entropy của khóa ảnh hưởng trực tiếp đến thuộc tính nào?
A. Tốc độ truyền ciphertext qua mạng nội bộ.
B. Số bản sao khóa có thể lưu trong backup.
C. Khả năng chống dự đoán và vét cạn khóa.
D. Khả năng tự gia hạn chứng thư của khóa.
Đáp án đúng: C

4. Khi chọn kích thước khóa đối xứng, yếu tố nào cần được cân nhắc?
A. Độ dài ciphertext mà ứng dụng muốn lưu trữ.
B. Mức an toàn cần đạt và hỗ trợ thuật toán.
C. Số người dùng có quyền đọc dữ liệu đã mã hóa.
D. Tên file cấu hình nơi lưu metadata của khóa.
Đáp án đúng: B

5. Private key trong hệ mật mã bất đối xứng cần được bảo vệ ra sao?
A. Giữ bí mật, chỉ cho phép thao tác được cấp quyền.
B. Phân phối cho mọi client cùng với public key.
C. Ghi vào certificate để bên nhận có thể kiểm tra.
D. Lưu công khai để mọi node tự đồng bộ khi khởi động.
Đáp án đúng: A

6. Vai trò phù hợp của KMS trong quản lý khóa là gì?
A. Thay thế mọi quyết định phân quyền trong ứng dụng.
B. Lưu plaintext của mọi dữ liệu mà hệ thống xử lý.
C. Tự động xác định người dùng cuối từ access log.
D. Quản lý vòng đời và thao tác mật mã qua API.
Đáp án đúng: D

7. HSM tăng cường bảo vệ khóa bằng cơ chế nào?
A. Đưa mọi private key vào biến môi trường của máy chủ.
B. Sao chép khóa thô sang mọi node để tăng tính sẵn sàng.
C. Giữ thao tác khóa trong phần cứng bảo vệ.
D. Thay chữ ký số bằng hash không khóa khi xác minh dữ liệu.
Đáp án đúng: C

8. Envelope encryption thường phân chia vai trò DEK và KEK thế nào?
A. DEK mã hóa dữ liệu; KEK dùng để bọc DEK.
B. KEK mã hóa từng block dữ liệu; DEK ký metadata.
C. DEK xác minh danh tính; KEK cấp quyền đọc bản ghi.
D. Cả DEK và KEK đều công khai để đơn giản phân phối.
Đáp án đúng: A

9. Khi lưu encrypted data key cùng ciphertext, thông tin nào cần được giữ?
A. DEK plaintext để giải mã khi KMS tạm ngừng.
B. DEK đã bọc kèm ID/version của KEK tương ứng.
C. Toàn bộ danh sách private key đang có trong KMS.
D. Mật khẩu quản trị đã dùng lúc tạo KEK ban đầu.
Đáp án đúng: B

10. Vì sao nên tách khóa theo mục đích sử dụng?
A. Giúp cùng một ciphertext giải mã bằng nhiều thuật toán.
B. Loại bỏ nhu cầu kiểm soát quyền sử dụng khóa.
C. Cho phép chia sẻ một private key cho mọi dịch vụ.
D. Giới hạn ảnh hưởng khi một khóa bị lộ hoặc dùng sai.
Đáp án đúng: D

11. Nguyên tắc least privilege áp dụng cho key usage như thế nào?
A. Cấp quyền decrypt và administer cho mọi workload.
B. Dùng một role quản trị chung cho cả người và dịch vụ.
C. Chỉ cấp principal thao tác cần thiết trên đúng key.
D. Cho phép mọi tài khoản đọc key material để dự phòng.
Đáp án đúng: C

12. Khi xoay KEK trong envelope encryption, cách nào thường tránh mã hóa lại toàn bộ dữ liệu?
A. Giải mã toàn bộ dữ liệu rồi lưu plaintext tạm thời.
B. Unwrap DEK bằng KEK cũ rồi wrap lại bằng KEK mới.
C. Giữ nguyên wrapped DEK và chỉ đổi tên key version.
D. Tạo ciphertext mới từ hash của encrypted data key.
Đáp án đúng: B

13. Khi xoay DEK đã dùng mã hóa dữ liệu, điều gì có thể cần thiết?
A. Chỉ đổi nhãn version mà không cập nhật ciphertext.
B. Xóa KEK hiện tại trước khi kiểm tra dữ liệu cũ.
C. Thay public key của mọi client dù không dùng khóa đó.
D. Giải mã dữ liệu cũ rồi mã hóa lại bằng DEK mới.
Đáp án đúng: D

14. Trong giai đoạn chuyển khóa, chính sách sử dụng key version nào hợp lý?
A. Dùng key cũ cho mã hóa mới và xóa key mới ngay.
B. Từ chối mọi ciphertext cũ trước khi hoàn tất migration.
C. Mã hóa bằng key mới; giải mã dữ liệu cũ bằng key cũ.
D. Cho mọi phiên bản khóa quyền ký và giải mã như nhau.
Đáp án đúng: C

15. Khi nghi ngờ một key bị compromise, hành động ưu tiên nào phù hợp?
A. Cô lập key, đánh giá ảnh hưởng và thay thế.
B. Chỉ đổi tên key để attacker không tìm thấy metadata.
C. Giữ nguyên key để tránh làm gián đoạn ứng dụng.
D. Xóa audit log để ngăn lộ thông tin về key usage.
Đáp án đúng: A

16. Thu hồi một khóa khác gì với xóa vật lý key material?
A. Revoke chặn dùng; destroy loại bỏ khả năng khôi phục.
B. Thu hồi chỉ đổi alias; xóa vật lý chỉ đổi version.
C. Hai thao tác giống nhau và luôn diễn ra đồng thời.
D. Xóa vật lý giữ quyền decrypt còn thu hồi thì xóa backup.
Đáp án đúng: A

17. Cryptographic erasure dựa trên nguyên lý nào?
A. Ghi đè ciphertext bằng plaintext ngẫu nhiên có cùng độ dài.
B. Hủy mọi bản sao khóa cần thiết để giải mã ciphertext.
C. Xóa metadata hiển thị nhưng giữ nguyên key trong backup.
D. Đổi tên thuật toán để ciphertext cũ không còn được nhận diện.
Đáp án đúng: B

18. Vì sao backup key material cần được bảo vệ và kiểm thử khôi phục?
A. Backup khóa giúp giảm số lần phải xác minh quyền truy cập.
B. Khóa backup luôn có thể được tái tạo từ ciphertext.
C. Chỉ cần backup public key vì private key không ảnh hưởng phục hồi.
D. Mất khóa có thể làm backup không thể giải mã.
Đáp án đúng: D

19. Dual control trong thao tác khóa nhạy cảm có ý nghĩa gì?
A. Một quản trị viên dùng hai tài khoản để tự phê duyệt.
B. Yêu cầu nhiều người độc lập phê duyệt hoặc cùng kiểm soát.
C. Hai hệ thống tự chia sẻ một mật khẩu quản trị chung.
D. Mọi người dùng đều có quyền thực hiện thao tác key admin.
Đáp án đúng: B

20. Split knowledge được áp dụng để giảm rủi ro nào?
A. Nhiều người cùng đọc được plaintext mà không cần quyền.
B. Một khóa được chia thành nhiều alias trong cùng vault.
C. Một cá nhân không nắm đủ thành phần để tái tạo bí mật.
D. Public key bị chia nhỏ để client ghép lại trước khi dùng.
Đáp án đúng: C

21. Audit log về thao tác khóa nên ghi thông tin nào?
A. Principal, key ID, thao tác, thời điểm, kết quả.
B. Giá trị key thô để điều tra mọi sự cố về sau.
C. Plaintext và ciphertext đầy đủ của mọi lần decrypt.
D. Mật khẩu quản trị cùng token truy cập của principal.
Đáp án đúng: A

22. Khi cấp quyền decrypt qua KMS, nên đánh giá điều gì?
A. Chỉ hostname của máy chủ vì mạng nội bộ đã tin cậy.
B. Tên hiển thị của người tạo ciphertext ban đầu.
C. Số byte ciphertext mà client gửi trong request.
D. Danh tính gọi, key scope, context và mục đích nghiệp vụ.
Đáp án đúng: D

23. Public key dùng để xác minh chữ ký cần được phân phối thế nào?
A. Nhận từ bất kỳ request nào có chữ ký đúng định dạng.
B. Đặt trong log công khai mà không cần kiểm tra fingerprint.
C. Xác thực nguồn công bố và danh tính key.
D. Tạo lại từ private key của người nhận khi cần xác minh.
Đáp án đúng: C

24. Vì sao khóa ký số thường cần chính sách riêng với khóa mã hóa?
A. Khóa ký luôn có thể được công khai sau lần sử dụng đầu.
B. Khóa mã hóa chỉ dùng cho TLS còn khóa ký chỉ dùng file.
C. Hai loại khóa không thể được quản lý bởi cùng một KMS.
D. Có vòng đời và rủi ro lộ khóa khác nhau.
Đáp án đúng: D

25. Một khóa đối xứng được chia sẻ cho nhiều dịch vụ độc lập. Rủi ro nào tăng lên?
A. Ciphertext sẽ tự thay đổi mỗi khi dịch vụ đọc dữ liệu.
B. Khó truy vết và giới hạn thiệt hại khi lộ khóa.
C. Mọi dịch vụ sẽ có cùng thời hạn certificate TLS.
D. Thuật toán đối xứng không còn tạo authentication tag.
Đáp án đúng: B

26. Key metadata nên lưu những thuộc tính nào để hỗ trợ quản trị?
A. Plaintext của khóa cùng mật khẩu đăng nhập quản trị.
B. Toàn bộ payload đã mã hóa bằng khóa đang quản lý.
C. Owner, mục đích, thuật toán, version, trạng thái.
D. Access token của mọi principal từng gọi KMS.
Đáp án đúng: C

27. Một key version đã retire nhưng còn cần giải mã backup cũ. Nên làm gì?
A. Xóa key ngay vì trạng thái retire đồng nghĩa destroy.
B. Giữ quyền decrypt có kiểm soát đến hết retention cần thiết.
C. Cho phép key tiếp tục mã hóa dữ liệu mới vô thời hạn.
D. Sao chép key ra file cấu hình để tránh phụ thuộc KMS.
Đáp án đúng: B

28. KDF được dùng để tạo các khóa con từ một key gốc nhằm mục đích gì?
A. Tạo key tách biệt theo context và mục đích sử dụng.
B. Nén key material để giảm dung lượng lưu trữ.
C. Khôi phục plaintext khi key gốc đã bị hủy hoàn toàn.
D. Thay thế entropy đầu vào bằng timestamp dễ dự đoán.
Đáp án đúng: A

29. Vì sao không nên dùng trực tiếp password người dùng làm encryption key?
A. Password thường thiếu entropy và cần KDF chuyên dụng.
B. Password luôn dài hơn key AES nên không thể tương thích.
C. Password không thể được chuyển thành byte trong thuật toán.
D. KMS chỉ chấp nhận key được tạo bởi HSM phần cứng.
Đáp án đúng: A

30. Khi tạo khóa từ password, lựa chọn nào giúp chống vét cạn offline?
A. Dùng hash nhanh không salt để giảm thời gian đăng nhập.
B. Dùng Base64 để tăng độ dài biểu diễn password.
C. Dùng một salt cố định chung cho toàn bộ người dùng.
D. Dùng password KDF có salt và cost phù hợp.
Đáp án đúng: D

31. Nonce hoặc IV có cần được giữ bí mật như encryption key không?
A. Có; nonce và IV phải nằm trong HSM cùng private key.
B. Có; nếu lộ IV thì mọi ciphertext tự giải mã được.
C. Không bí mật; phải tuân thủ uniqueness hoặc unpredictability.
D. Không; vì vậy có thể tái sử dụng với mọi key.
Đáp án đúng: C

32. Khi KMS hỗ trợ key grants hoặc policy, cách nào giới hạn quyền tạm thời?
A. Cấp quyền admin vĩnh viễn rồi dựa vào audit để phát hiện.
B. Chia sẻ master credential cho workload trong lúc triển khai.
C. Grant theo principal, thao tác và thời hạn.
D. Tắt kiểm tra policy khi ứng dụng chạy trong private subnet.
Đáp án đúng: C

33. KMS nhiều vùng cần được thiết kế thế nào để tránh mất khả năng dùng khóa?
A. Sao chép key plaintext vào mọi vùng mà không giới hạn.
B. Replication, failover và khôi phục được kiểm thử.
C. Chỉ giữ một endpoint duy nhất để tránh lệch trạng thái.
D. Tạo key độc lập ở mỗi vùng mà không đồng bộ metadata.
Đáp án đúng: B

34. Khi xóa key, điều gì cần xác minh trước khi thực hiện?
A. Key không xuất hiện trong danh sách recent activity.
B. Alias của key đã được đổi sang tên mới.
C. Mọi principal đã đăng xuất khỏi giao diện quản trị.
D. Không còn dữ liệu hay backup cần khóa.
Đáp án đúng: D

35. Crypto agility trong quản lý khóa giúp xử lý thay đổi nào?
A. Giữ một thuật toán cố định bất kể khuyến nghị thay đổi.
B. Đổi thuật toán và version theo chính sách.
C. Dùng cùng key material cho mọi phiên bản thuật toán.
D. Xóa metadata cũ để ứng dụng luôn dùng key mới nhất.
Đáp án đúng: B

36. Chỉ số nào giúp đánh giá hiệu quả vận hành key management?
A. Rotation success, key age, denied usage và thời gian revoke.
B. Số lượng ciphertext tạo ra mà không xét trạng thái khóa.
C. Dung lượng log thô và số alias được tạo mỗi ngày.
D. Số người dùng đăng nhập thành công vào hệ thống ứng dụng.
Đáp án đúng: A
