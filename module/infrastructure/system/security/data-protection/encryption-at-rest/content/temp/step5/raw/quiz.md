1. Một tổ chức cần bảo vệ database dump bị đánh cắp khỏi kho backup; bước đầu tiên khi thiết kế encryption at rest là gì?
A. Lập threat model cho tài sản, đối thủ và ranh giới tin cậy.
B. Chọn thuật toán mạnh nhất rồi áp dụng đồng nhất cho mọi hệ thống lưu trữ.
C. Bật mã hóa ổ đĩa ở production và giả định mọi bản sao đều được bảo vệ.
D. Chỉ kiểm tra quyền truy cập kho backup vì dữ liệu đã nằm trong mạng nội bộ.
Đáp án đúng: A

2. Full-disk encryption bảo vệ dữ liệu tốt nhất trong tình huống nào?
A. Ứng dụng đang chạy bị khai thác và đọc dữ liệu qua tài khoản hợp lệ.
B. Thiết bị tắt hoặc media bị tháo và kẻ tấn công thiếu khóa mở volume.
C. Quản trị viên đã đăng nhập truy cập file bằng quyền hệ điều hành được cấp.
D. Dữ liệu được gửi qua mạng từ máy chủ tới client không đáng tin cậy.
Đáp án đúng: B

3. Một máy chủ đã mở khóa volume và đang phục vụ ứng dụng; giới hạn chính của disk encryption là gì?
A. Volume không thể mã hóa lại sau khi hệ điều hành đã khởi động thành công.
B. Mọi file được ghi sau khi boot đều phải dùng một khóa riêng biệt.
C. Disk encryption chỉ bảo vệ metadata và không mã hóa nội dung file.
D. OS hoặc ứng dụng có quyền vẫn đọc được plaintext.
Đáp án đúng: D

4. Transparent Database Encryption (TDE) thường bảo vệ dữ liệu ở lớp nào?
A. Mọi giá trị trả về cho ứng dụng đều được mã hóa trước khi truy vấn.
B. Data file và log được mã hóa khi lưu trữ ở tầng database engine.
C. Các trường dữ liệu được mã hóa đầu cuối trước khi tới database server.
D. Quyền đọc từng hàng được kiểm soát độc lập bằng khóa riêng cho người dùng.
Đáp án đúng: B

5. Một ứng dụng cần ngăn DBA đọc một số trường nhạy cảm từ database dump; lựa chọn nào bổ sung cho TDE?
A. Bật thêm mã hóa volume trên máy database và giữ quyền DBA hiện tại.
B. Dùng TLS giữa ứng dụng và database nhưng lưu plaintext trên data file.
C. Mã hóa trường ở tầng ứng dụng trước khi ghi dữ liệu vào database.
D. Ẩn cột khỏi giao diện quản trị nhưng giữ giá trị rõ trong bảng.
Đáp án đúng: C

6. Với object storage, khác biệt cốt lõi giữa server-side và client-side encryption là gì?
A. Client-side chỉ mã hóa metadata; server-side chỉ mã hóa payload của object.
B. Client-side dùng khóa do storage provider giữ; server-side do uploader giữ.
C. Client mã hóa trước upload; server mã hóa khi lưu.
D. Hai cách chỉ khác vị trí đặt bucket và không khác ranh giới tin cậy.
Đáp án đúng: C

7. Dữ liệu nhạy cảm có thể rơi vào swap, crash dump và file tạm; biện pháp nào phù hợp?
A. Mã hóa hoặc hạn chế các vùng lưu tạm và kiểm soát việc tạo dump.
B. Chỉ bật TDE vì mọi dữ liệu tạm đều được database engine mã hóa.
C. Tắt audit để tiến trình không ghi dữ liệu nhạy cảm ra ổ đĩa.
D. Chỉ xóa file tạm khi shutdown vì swap và dump không giữ plaintext.
Đáp án đúng: A

8. Một hệ thống cần cả bí mật và phát hiện sửa đổi ciphertext; primitive nào phù hợp?
A. Mã hóa AES-CBC kết hợp padding mặc định mà không cần kiểm tra tag.
B. Hash SHA-256 dữ liệu rồi lưu digest cạnh plaintext trong cùng object.
C. Base64 payload và ký tên file bằng checksum không có khóa bí mật.
D. Authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305.
Đáp án đúng: D

9. Khi dùng AES-GCM với cùng một khóa, yêu cầu quan trọng nhất đối với nonce là gì?
A. Không tái sử dụng nonce dưới cùng một khóa AES-GCM.
B. Nonce phải được giữ bí mật và chỉ KMS mới được phép đọc giá trị.
C. Nonce phải giống nhau cho các bản sao để giải mã đồng nhất giữa vùng.
D. Nonce phải được tạo từ password người dùng để tránh lưu metadata.
Đáp án đúng: A

10. Một object được mã hóa bằng AEAD và cần ràng buộc tenant ID cùng object ID nhưng không cần che giấu hai giá trị đó; nên dùng gì?
A. Nối hai giá trị vào cuối ciphertext rồi bỏ qua kiểm tra integrity.
B. Dùng tenant ID làm nonce và object ID làm khóa mã hóa payload.
C. Đưa tenant ID và object ID vào associated data được xác thực.
D. Lưu hai giá trị trong log rồi so sánh sau khi giải mã thành công.
Đáp án đúng: C

11. AEAD giải mã thất bại vì authentication tag không hợp lệ; ứng dụng nên xử lý thế nào?
A. Trả phần plaintext đã giải mã trước khi tag được kiểm tra xong.
B. Thử giải mã lại bằng cách bỏ qua tag nếu nonce và key ID hợp lệ.
C. Thay tag bằng giá trị mới rồi tiếp tục xử lý payload ban đầu.
D. Từ chối plaintext khi kiểm tra authentication tag thất bại.
Đáp án đúng: D

12. Envelope encryption bảo vệ một object lớn bằng cách kết hợp hai loại khóa nào?
A. DEK mã hóa payload; KEK wrap DEK để bảo vệ khóa.
B. KEK mã hóa từng block dữ liệu; DEK xác thực người gọi KMS.
C. DEK xác thực metadata; KEK tạo nonce mới cho mỗi lần đọc object.
D. Một khóa mã hóa payload; khóa còn lại ký audit log của object.
Đáp án đúng: A

13. Trong envelope encryption, khóa nào thường được lưu cùng ciphertext dưới dạng đã được wrap?
A. KEK ở dạng plaintext để mọi worker có thể giải mã object độc lập.
B. Private key của workload dùng để ký request tới storage service.
C. DEK được wrap bằng KEK, kèm key ID và metadata cần thiết.
D. Root key của HSM để client có thể tự phục hồi toàn bộ key hierarchy.
Đáp án đúng: C

14. Vì sao envelope encryption phù hợp hơn việc gọi KMS mã hóa trực tiếp mọi byte của object lớn?
A. KMS bảo vệ DEK nhỏ; ứng dụng mã hóa payload cục bộ.
B. Envelope encryption loại bỏ nhu cầu dùng nonce và authentication tag.
C. KMS chỉ lưu metadata nên không thể xử lý bất kỳ thao tác mã hóa nào.
D. Mỗi object được mã hóa bằng KEK công khai nên không cần quyền decrypt.
Đáp án đúng: A

15. Một service cần tạo DEK mới cho từng object; cách nào giảm nguy cơ khóa bị đoán hoặc tái sử dụng sai?
A. Dùng object ID làm DEK để dễ truy xuất và bảo đảm mỗi object khác nhau.
B. Sinh DEK bằng CSPRNG hoặc yêu cầu KMS GenerateDataKey.
C. Tạo DEK từ timestamp và tên tenant bằng hàm băm không khóa.
D. Dùng chung một DEK tĩnh cho mọi object trong cùng tiến trình.
Đáp án đúng: B

16. Một tổ chức dùng HSM để bảo vệ key material; lợi ích chính của HSM là gì?
A. Ngăn mọi ứng dụng có quyền hợp lệ yêu cầu HSM giải mã dữ liệu.
B. Giữ key material trong HSM và thực thi crypto trong phần cứng.
C. Tự động phân quyền theo tenant mà không cần policy hoặc identity.
D. Đảm bảo dữ liệu plaintext không xuất hiện trong bộ nhớ ứng dụng.
Đáp án đúng: B

17. Một khóa được đánh dấu non-exportable trong HSM; điều đó bảo đảm điều gì?
A. Không workload nào có thể yêu cầu thao tác decrypt bằng khóa đó.
B. Dữ liệu sau giải mã không thể bị đọc bởi ứng dụng gọi HSM.
C. Mọi bản sao backup dùng khóa đó đều tự động bị xóa khi khóa rotate.
D. Không xuất key material khỏi HSM theo policy.
Đáp án đúng: D

18. Một workload chỉ cần giải mã DEK cho tenant A; policy KMS nên giới hạn điều gì?
A. Cho phép decrypt mọi key trong account nếu workload chạy ở production.
B. Chỉ giới hạn theo IP nguồn vì mọi request KMS đều đã xác thực.
C. Principal, key, action và encryption context của tenant A.
D. Cấp quyền quản trị key để workload tự xử lý mọi trường hợp lỗi.
Đáp án đúng: C

19. Một service có quyền decrypt rộng được yêu cầu giải mã object thay cho caller không đủ quyền; rủi ro nào cần kiểm soát?
A. Nonce collision do nhiều service dùng chung cùng một vùng lưu trữ.
B. Confused deputy khi service dùng quyền của nó vượt quyền caller.
C. Key escrow vì caller không giữ private key của service trung gian.
D. Ciphertext malleability do object được lưu ở nhiều bucket khác nhau.
Đáp án đúng: B

20. Một nền tảng nhiều tenant muốn giảm blast radius khi một khóa dữ liệu bị lộ; cách phân chia DEK nào hữu ích?
A. Dùng một DEK toàn cục để mọi tenant có thể phục hồi khi mất khóa.
B. Dùng một KEK riêng cho mỗi request nhưng chia sẻ DEK toàn hệ thống.
C. Dùng chung một khóa cho dữ liệu production và bản sao kiểm thử.
D. Dùng DEK riêng theo từng object hoặc theo tenant.
Đáp án đúng: D

21. Key rotation khác data re-encryption ở điểm nào?
A. Rotation luôn giải mã rồi mã hóa lại toàn bộ payload; re-encryption chỉ đổi metadata.
B. Rotation chỉ thay nonce; re-encryption chỉ cập nhật key identifier trong header.
C. Rotation đổi key version; re-encryption tạo ciphertext bằng DEK mới.
D. Hai thao tác giống nhau và luôn hoàn tất cùng lúc trên mọi object.
Đáp án đúng: C

22. Một tổ chức thay KEK nhưng muốn tránh đọc và mã hóa lại payload lớn; thao tác nào phù hợp?
A. Giải mã payload rồi mã hóa lại bằng KEK mới trực tiếp từng block.
B. Thay nonce của payload nhưng giữ nguyên DEK và authentication tag cũ.
C. Xóa ciphertext cũ rồi tạo object mới từ bản plaintext trong backup.
D. Rewrap DEK bằng KEK mới và giữ nguyên ciphertext dữ liệu.
Đáp án đúng: D

23. Ciphertext cũ vẫn cần giải mã sau nhiều lần rotation; metadata nào giúp chọn đúng khóa?
A. Lưu key ID và version cùng DEK đã wrap.
B. Tên người dùng đã tải object lần đầu và thời điểm upload.
C. Địa chỉ IP của KMS endpoint được gọi khi tạo ciphertext.
D. Phiên bản ứng dụng đang chạy tại thời điểm đọc object.
Đáp án đúng: A

24. Một key version mới đã được phát hành nhưng dữ liệu cũ vẫn dùng version trước; cách triển khai nào phù hợp?
A. Giữ khả năng decrypt bản cũ; dùng key mới cho dữ liệu mới.
B. Xóa key cũ ngay khi tạo key mới để buộc mọi object tự cập nhật.
C. Từ chối đọc ciphertext cũ cho đến khi người dùng tải lại dữ liệu.
D. Đổi key identifier trong metadata mà không cần rewrap hay re-encrypt.
Đáp án đúng: A

25. Backup database đã mã hóa nhưng KMS key hoặc quyền decrypt bị mất; hậu quả chính là gì?
A. Database tự tạo lại DEK từ checksum của backup khi restore.
B. Ciphertext còn nguyên nhưng không thể giải mã khi thiếu key.
C. Backup chuyển về plaintext vì key metadata không còn tồn tại.
D. KMS tự suy ra quyền giải mã từ quyền đọc object storage.
Đáp án đúng: B

26. Một đội kiểm thử disaster recovery cần xác minh backup có thể giải mã; cách nào phù hợp?
A. Chỉ xác nhận file backup tồn tại và kích thước trùng với bản gốc.
B. Restore cô lập với quyền key tối thiểu, rồi xác minh dữ liệu.
C. Dùng production key với quyền quản trị toàn account để kiểm tra nhanh.
D. Tắt kiểm tra AEAD tag trong môi trường test để tránh lỗi tương thích.
Đáp án đúng: B

27. Crypto-erasure được thực hiện bằng cách nào khi dữ liệu chỉ còn các bản mã được bảo vệ bởi khóa riêng?
A. Xóa key identifier trong metadata nhưng giữ nguyên key material trong KMS.
B. Đổi tên object và chuyển ciphertext sang bucket archive không truy cập.
C. Hủy mọi bản sao khóa còn có thể giải mã dữ liệu liên quan.
D. Xóa bản ghi trong database chính nhưng giữ backup cùng wrapped DEK.
Đáp án đúng: C

28. Một KMS key bị disable tạm thời; điều này khác key deletion như thế nào?
A. Disable xóa vĩnh viễn key material và không thể khôi phục bằng policy.
B. Deletion chỉ tạm dừng decrypt còn disable làm mất toàn bộ ciphertext.
C. Hai trạng thái có cùng tác động và chỉ khác nhãn hiển thị trong console.
D. Disable chặn sử dụng; key material vẫn được giữ.
Đáp án đúng: D

29. Ứng dụng cache plaintext DEK để giảm latency; kiểm soát nào cân bằng hiệu năng và rủi ro?
A. Giữ DEK trong cache vô thời hạn để tránh gọi KMS khi có tải cao.
B. Chia sẻ DEK qua cache dùng chung cho mọi tenant trong cùng region.
C. Giới hạn TTL, phạm vi cache và quyền truy cập bộ nhớ chứa DEK.
D. Ghi DEK vào file cache để có thể phục hồi sau khi tiến trình khởi động.
Đáp án đúng: C

30. KMS tạm thời không khả dụng nhưng ứng dụng cần đọc dữ liệu quan trọng; thiết kế nào phù hợp?
A. Bỏ kiểm tra quyền KMS và cho phép mọi worker dùng key dự phòng chung.
B. Dự phòng KMS và cache DEK có TTL, scope giới hạn.
C. Lưu master key plaintext trong cấu hình để ứng dụng tự giải mã khi lỗi.
D. Tự động hạ cấp ciphertext thành plaintext cho đến khi KMS hoạt động lại.
Đáp án đúng: B

31. Một hệ thống multi-region cần phục hồi dữ liệu ở vùng dự phòng; yếu tố nào cần được thiết kế cùng backup?
A. Chỉ đồng bộ ciphertext vì key luôn được suy ra từ tên bucket.
B. Key và quyền decrypt phải sẵn sàng tại vùng khôi phục.
C. Sao chép root key plaintext sang mọi region để giảm thời gian khôi phục.
D. Dùng chung role quản trị cho tất cả region để tránh cấu hình khác nhau.
Đáp án đúng: B

32. Audit KMS cần hỗ trợ điều tra mà không làm lộ bí mật; sự kiện nào nên được ghi?
A. Ghi principal, key ID, action, context và kết quả.
B. Plaintext DEK, master key và payload sau giải mã để tái hiện đầy đủ.
C. Chỉ ghi tổng số lần gọi KMS theo ngày mà không có principal.
D. Ghi access token và secret request để đối chiếu người gọi khi cần.
Đáp án đúng: A

33. Một workload đột ngột decrypt số lượng lớn object ngoài giờ hoạt động; biện pháp nào hữu ích?
A. Tự động tăng quota KMS để workload hoàn tất nhanh hơn.
B. Chỉ theo dõi số lần encrypt vì decrypt không làm thay đổi ciphertext.
C. Tắt audit log trong thời gian cao điểm để giảm tải dịch vụ KMS.
D. Cảnh báo lệch baseline và giới hạn decrypt theo scope.
Đáp án đúng: D

34. Một ciphertext bị thay đổi một bit trước khi giải mã bằng AEAD; kết quả mong đợi là gì?
A. Từ chối ciphertext nếu AEAD không xác thực được tag.
B. Payload giải mã khác một bit nhưng tag vẫn được xem là hợp lệ.
C. Ứng dụng tự sửa ciphertext bằng cách dùng associated data làm checksum.
D. KMS tạo tag mới cho ciphertext đã bị thay đổi trước khi trả dữ liệu.
Đáp án đúng: A

35. Một tổ chức muốn kiểm chứng plaintext không rò vào log và file tạm; cách thử nghiệm nào phù hợp?
A. Chỉ xác minh object storage chứa ciphertext và bỏ qua đường xử lý ứng dụng.
B. Kiểm tra log không có tên trường dữ liệu nhưng không tìm giá trị thực.
C. Đo CPU khi mã hóa để suy ra plaintext không được ghi ra đĩa.
D. Dùng dữ liệu canary rồi quét log, dump, swap và file tạm.
Đáp án đúng: D

36. Một ứng dụng mã hóa object rất lớn; cách triển khai nào hỗ trợ streaming mà vẫn giữ integrity?
A. Dùng lại một nonce cho mọi chunk để giảm metadata cần lưu trữ.
B. Bỏ authentication tag ở chunk giữa và chỉ xác minh chunk cuối.
C. Mã hóa từng chunk với nonce riêng và xác thực từng phần.
D. Nối các chunk plaintext vào file tạm rồi mã hóa sau khi upload xong.
Đáp án đúng: C
