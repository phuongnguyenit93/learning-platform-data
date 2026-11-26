Một tổ chức muốn quản lý khóa từ lúc tạo đến khi không còn cần thiết. Trình tự nào mô tả đầy đủ vòng đời khóa hợp lý nhất?
A. Tạo, lưu, phân phối, kích hoạt, sử dụng, xoay vòng, thu hồi và tiêu hủy.
B. Tạo, phân phối, sao lưu, sử dụng, rồi xóa khóa khi ứng dụng ngừng chạy.
C. Tạo, kích hoạt, công bố, sử dụng, rồi giữ khóa cũ vô thời hạn.
D. Tạo, lưu, sử dụng, đổi thuật toán, rồi xóa mọi bản ghi kiểm toán.
Đáp án đúng: A

Một hệ thống cần sinh khóa đối xứng dùng cho mã hóa dữ liệu. Nguồn nào phù hợp để tạo khóa có thể chống đoán?
A. Bộ sinh số giả ngẫu nhiên thông thường được khởi tạo từ timestamp.
B. Hash của tên máy và thời điểm triển khai được dùng làm khóa.
C. Một chuỗi ký tự dễ nhớ được kéo dài đến đủ số byte yêu cầu.
D. Sinh khóa bằng CSPRNG với đủ entropy cho kích thước chọn.
Đáp án đúng: D

Một nhóm phát triển chọn khóa AES-256 cho dữ liệu nhạy cảm. Điều gì vẫn cần được bảo đảm ngoài độ dài khóa?
A. Sinh ngẫu nhiên an toàn và dùng AEAD với nonce đúng cách.
B. Khóa phải được tạo từ mật khẩu quản trị có độ dài tương đương.
C. Khóa phải được lưu cùng ciphertext để hệ thống dễ phục hồi.
D. Khóa phải dùng chung giữa mọi môi trường để tránh lỗi tương thích.
Đáp án đúng: A

Một hệ thống cần ký artifact để bên nhận kiểm tra nguồn gốc và tính toàn vẹn. Loại khóa nào phù hợp cho thao tác ký?
A. Khóa công khai dùng để ký và khóa riêng tương ứng dùng để xác minh.
B. Một khóa đối xứng dùng chung cho tất cả bên nhận mà không cần quản lý danh tính.
C. Dùng private key của chủ thể để ký; public key tương ứng xác minh chữ ký.
D. Khóa mã hóa dữ liệu dùng trực tiếp làm khóa ký để giảm số lượng khóa.
Đáp án đúng: C

Một nền tảng mã hóa lượng lớn dữ liệu bằng các data encryption key riêng. Vai trò phù hợp của key encryption key là gì?
A. KEK wrap DEK để bảo vệ khóa dữ liệu khi lưu trữ hoặc phân phối.
B. KEK mã hóa trực tiếp mọi block dữ liệu thay cho DEK.
C. KEK được gửi tới client để client tự sinh DEK từ nội dung file.
D. KEK dùng để xác minh chữ ký của ciphertext sau khi giải mã DEK.
Đáp án đúng: A

Một ứng dụng áp dụng envelope encryption cho file lớn. Quy trình nào đúng?
A. Mã hóa file bằng KEK rồi dùng DEK để ký ciphertext trước khi lưu.
B. Gửi file rõ tới KMS để KMS tự lưu dữ liệu và trả về DEK.
C. Mã hóa DEK bằng chính nó rồi dùng KEK để giải mã file khi đọc.
D. Ứng dụng mã hóa payload bằng DEK rồi dùng KEK bảo vệ DEK đó.
Đáp án đúng: D

Một tổ chức xoay KEK đang bảo vệ hàng triệu DEK. Nếu thuật toán và DEK không thay đổi, thao tác nào thường giảm chi phí?
A. Giải mã và mã hóa lại mọi dữ liệu bằng cùng DEK hiện tại.
B. Thay mọi DEK bằng KEK mới rồi lưu KEK cũ cạnh ciphertext.
C. Rewrap DEK bằng KEK mới; payload dữ liệu và DEK không đổi.
D. Chỉ đổi tên phiên bản KEK trong metadata mà không cập nhật wrapped DEK.
Đáp án đúng: C

Một HSM lưu khóa ký không cho phép xuất private key ra ngoài thiết bị. Lợi ích bảo mật chính là gì?
A. Ngăn mọi ứng dụng được cấp quyền gọi HSM sử dụng khóa sai mục đích.
B. Bảo đảm chữ ký không thể bị giả mạo kể cả khi thuật toán đã lỗi thời.
C. HSM giữ key material trong phần cứng; ứng dụng chỉ gọi thao tác được cấp.
D. Tự động thu hồi mọi chữ ký đã tạo nếu HSM mất kết nối mạng.
Đáp án đúng: C

Một workload cần gọi KMS để giải mã DEK. Kiểm soát nào phù hợp nhất với least privilege?
A. Cấp quyền quản trị KMS cho mọi tiến trình trong cùng subnet.
B. Cấp quyền đúng workload, thao tác và key scope.
C. Dùng một access key tĩnh chung cho tất cả ứng dụng trong tổ chức.
D. Cho phép mọi workload gọi decrypt nếu đã truy cập được mạng nội bộ.
Đáp án đúng: B

Một tổ chức yêu cầu hai người cùng phê duyệt thao tác xuất hoặc hủy khóa gốc. Mục tiêu chính của dual control là gì?
A. Tăng tốc thao tác bằng cách cho hai người thực hiện song song không cần phối hợp.
B. Buộc thao tác nhạy cảm có phê duyệt độc lập, tránh một người tự quyết.
C. Đảm bảo hai người đều biết toàn bộ secret key để dễ xử lý sự cố.
D. Thay thế xác thực đa yếu tố vì có hai người cùng tham gia thao tác.
Đáp án đúng: B

Một key ceremony cần chia bí mật thành nhiều phần để không cá nhân nào nắm đủ quyền khôi phục. Mô hình nào phù hợp?
A. Sao chép nguyên khóa vào N USB rồi yêu cầu M USB cắm cùng lúc.
B. Mã hóa khóa bằng mật khẩu chung rồi gửi mật khẩu cho toàn bộ người tham gia.
C. Chia khóa thành các đoạn văn bản độc lập và ghép theo thứ tự tên người giữ.
D. Khôi phục cần đủ M trong N shares được chia và quản lý riêng.
Đáp án đúng: D

Một doanh nghiệp đặt cryptoperiod cố định cho mọi loại khóa là một năm. Cách xác định cryptoperiod nào hợp lý hơn?
A. Dùng cùng thời hạn cho mọi khóa để đơn giản hóa việc lập lịch.
B. Xét loại khóa, thuật toán, dữ liệu và mức đe dọa.
C. Chỉ dựa vào ngày tạo khóa vì mức sử dụng không ảnh hưởng rủi ro.
D. Để khóa tồn tại đến khi hết dung lượng lưu trữ của hệ thống.
Đáp án đúng: B

Một khóa mã hóa dữ liệu giao dịch đã được dùng nhiều năm và vượt ngưỡng cryptoperiod. Hành động nào phù hợp?
A. Tiếp tục dùng khóa vì dữ liệu đã mã hóa vẫn giải mã được bình thường.
B. Xóa ngay khóa cũ trước khi xác nhận dữ liệu và backup đã chuyển đổi.
C. Dừng dùng khóa cho dữ liệu mới, chuyển sang key version mới.
D. Đổi tên key alias để hệ thống coi khóa cũ là một khóa mới.
Đáp án đúng: C

Một hệ thống xoay DEK để mã hóa dữ liệu mới. Dữ liệu cũ vẫn cần được đọc trong thời gian chuyển đổi. Thiết kế nào phù hợp?
A. Xóa DEK cũ ngay sau khi tạo DEK mới rồi dùng DEK mới giải mã dữ liệu cũ.
B. Ghi đè DEK cũ bằng DEK mới để mọi ciphertext tự động được cập nhật.
C. Giữ bản cũ để giải mã; ghi key version cùng ciphertext.
D. Dùng một key alias chung và không lưu thông tin phiên bản trong ciphertext.
Đáp án đúng: C

Một tổ chức cần chuyển dữ liệu đã mã hóa sang DEK mới. Quy trình nào thực hiện rotation dữ liệu đúng?
A. Chỉ thay key identifier trong metadata để ciphertext được đọc bằng DEK mới.
B. Giải mã bằng DEK cũ rồi mã hóa lại dữ liệu bằng DEK mới.
C. Wrap DEK cũ bằng DEK mới và xem như dữ liệu đã được mã hóa lại.
D. Chỉ xoay KEK bảo vệ DEK cũ, không tạo DEK mới hay mã hóa lại payload.
Đáp án đúng: B

Một KMS hỗ trợ re-encryption hoặc rewrap cho wrapped DEK. Khác biệt quan trọng so với mã hóa lại payload là gì?
A. Rewrap thay lớp bảo vệ của DEK; ciphertext payload không cần thay đổi.
B. Rewrap giải mã toàn bộ payload rồi chuyển dữ liệu sang thuật toán mới.
C. Rewrap chỉ thay nonce của payload mà không thay đổi key wrapping.
D. Rewrap làm thay đổi plaintext để dữ liệu không còn tương thích với ứng dụng.
Đáp án đúng: A

Một ứng dụng cache DEK trong bộ nhớ để giảm số lần gọi KMS. Rủi ro nào cần cân nhắc khi đặt cache TTL quá dài?
A. Ciphertext đã lưu sẽ tự động bị xóa khi cache hết hạn.
B. DEK còn trong cache có thể tiếp tục dùng dù quyền hoặc trạng thái key đã đổi.
C. KMS sẽ mất khả năng kiểm toán mọi lần dùng DEK trong thời gian cache.
D. DEK trong cache sẽ tự đổi thành khóa công khai khi TTL vượt cryptoperiod.
Đáp án đúng: B

Một hệ thống lưu ciphertext nhưng không lưu key ID, algorithm hoặc version tương ứng. Vấn đề vận hành nào dễ phát sinh?
A. Thiếu metadata gây khó chọn đúng key và thuật toán.
B. Ciphertext sẽ tự chứa đủ thông tin khóa nên không cần metadata nào khác.
C. KMS có thể suy ra khóa chỉ từ kích thước file mà không cần định danh.
D. Việc thiếu metadata chỉ ảnh hưởng tốc độ mã hóa, không ảnh hưởng phục hồi.
Đáp án đúng: A

Một dịch vụ có quyền gọi KMS decrypt nhưng không cần tạo hay quản trị khóa. Cách phân quyền nào phù hợp?
A. Cấp quyền quản trị toàn bộ key ring để tránh phải quản lý nhiều role.
B. Cho dịch vụ quyền export key material để không phụ thuộc KMS khi giải mã.
C. Workload chỉ được dùng thao tác cần thiết, không sửa policy hay xóa key.
D. Dùng một tài khoản quản trị chung cho cả ứng dụng và nhóm bảo mật.
Đáp án đúng: C

Một nhà cung cấp hỗ trợ import key material vào KMS. Để bảo vệ khóa trong quá trình nhập, phương án nào phù hợp?
A. Gửi key material dạng rõ qua email nội bộ rồi xóa email sau khi import.
B. Đặt key material trong biến môi trường của pipeline và truyền qua log build.
C. Dùng public wrapping key do KMS cấp để wrap key material trước import.
D. Mã hóa key material bằng chính khóa cần import rồi gửi kèm plaintext để dự phòng.
Đáp án đúng: C

Một tổ chức dùng BYOK để đưa key material do mình tạo vào KMS của cloud provider. Điều này bảo đảm điều gì?
A. BYOK kiểm soát nguồn key; không tự bảo đảm quyền và nơi lưu.
B. Nhà cung cấp cloud không thể thực hiện bất kỳ thao tác nào trên khóa sau import.
C. Khóa không bao giờ được xử lý trong phần cứng hoặc hạ tầng của nhà cung cấp.
D. BYOK tự động bảo đảm mọi bản sao, backup và cache khóa đều nằm ngoài cloud.
Đáp án đúng: A

Một ứng dụng có thể gọi HSM ký dữ liệu bằng khóa không xuất được. Nếu ứng dụng bị chiếm quyền, rủi ro nào vẫn còn?
A. Attacker chắc chắn lấy được private key từ HSM vì ứng dụng có quyền ký.
B. HSM tự phát hiện mọi request độc hại và thu hồi khóa ngay lập tức.
C. Attacker có thể gọi HSM ký nội dung tùy ý bằng quyền của ứng dụng.
D. Không còn rủi ro nào vì non-exportable đồng nghĩa mọi lần sử dụng đều hợp lệ.
Đáp án đúng: C

Một khóa bị nghi lộ nhưng chưa xác định được dữ liệu nào đã bị giải mã. Hành động ứng phó ban đầu nào phù hợp?
A. Hạn chế sử dụng, điều tra phạm vi và chuẩn bị thay khóa.
B. Xóa khóa vĩnh viễn ngay lập tức trước khi thu thập bằng chứng và xác định phụ thuộc.
C. Giữ nguyên quyền sử dụng khóa cho đến khi tìm được toàn bộ ciphertext liên quan.
D. Chỉ đổi alias của khóa để ngăn attacker tìm thấy tên khóa cũ.
Đáp án đúng: A

Một khóa ký số bị xâm phạm. Tổ chức cần xử lý chữ ký và bên xác minh như thế nào?
A. Thu hồi khóa, cập nhật verifier và đánh giá chữ ký tạo trong thời gian bị lộ.
B. Xóa public key khỏi mọi hệ thống để mọi chữ ký cũ tự động trở nên hợp lệ.
C. Tiếp tục tin chữ ký cũ và mới vì chữ ký đã tạo không thể bị ảnh hưởng.
D. Chỉ tạo khóa mới; không cần cập nhật trust store hoặc quy trình xác minh.
Đáp án đúng: A

Một khóa mã hóa bị thu hồi do nghi bị lộ nhưng dữ liệu hợp lệ cũ vẫn cần truy cập. Chính sách nào cân bằng được yêu cầu?
A. Cho phép tiếp tục encrypt và decrypt không giới hạn để duy trì tương thích.
B. Chặn encrypt mới; kiểm soát ngoại lệ decrypt dữ liệu cũ.
C. Xóa ngay khóa cùng mọi ciphertext trước khi xác định yêu cầu lưu trữ.
D. Đổi key alias và coi mọi thao tác tiếp theo là sử dụng khóa mới.
Đáp án đúng: B

Một KMS cung cấp các trạng thái disable, schedule deletion và delete. Cách hiểu nào đúng?
A. Disable xóa key material ngay, còn schedule deletion chỉ đổi nhãn hiển thị.
B. Schedule deletion chỉ chặn encrypt nhưng luôn cho phép mọi thao tác khác.
C. Delete chỉ xóa alias nên key material vẫn luôn có thể khôi phục vô thời hạn.
D. Disable chặn mã hóa hoặc giải mã; xóa khóa là bước riêng của KMS.
Đáp án đúng: D

Một khóa mã hóa backup bị mất nhưng ciphertext backup còn nguyên. Yếu tố nào quyết định khả năng khôi phục?
A. Chỉ cần có checksum của backup là có thể tái tạo khóa đã mất.
B. Có thể dùng khóa của bản backup mới hơn để giải mã mọi bản cũ.
C. Nhà cung cấp lưu mọi khóa đã xóa nên không cần kế hoạch backup khóa.
D. Phải có bản sao khóa hoặc recovery path tương thích với định dạng backup.
Đáp án đúng: D

Một tổ chức muốn backup khóa quan trọng để phục hồi sau thảm họa. Thiết kế nào phù hợp?
A. Sao chép khóa dạng rõ vào cùng storage với dữ liệu đã mã hóa để dễ phục hồi.
B. Backup tách biệt, mã hóa, dual control và thử restore.
C. Để một quản trị viên giữ bản sao duy nhất trên laptop cá nhân được mã hóa.
D. Chỉ backup cấu hình KMS vì key material luôn có thể tạo lại giống hệt.
Đáp án đúng: B

Một khóa gốc cần có cơ chế escrow để phục hồi khi người quản lý vắng mặt. Kiểm soát nào quan trọng?
A. Escrow cần custody tách biệt, ngưỡng phê duyệt và audit mọi lần truy cập.
B. Cho toàn bộ đội vận hành biết một mật khẩu escrow chung để tránh chậm trễ.
C. Đặt escrow key trong cùng hệ thống production và cấp quyền đọc cho service account.
D. Cho phép người giữ escrow tự giải mã mọi dữ liệu mà không cần phê duyệt.
Đáp án đúng: A

Một tổ chức muốn hủy dữ liệu bằng crypto-erasure. Điều kiện nào phải được xác minh trước khi hủy khóa?
A. Chỉ cần xóa key alias khỏi giao diện quản trị mà không cần kiểm tra bản sao.
B. Phải xác minh bản chính, replica và backup đều phụ thuộc khóa sẽ hủy.
C. Chỉ cần xóa bản ciphertext chính; backup và replica không ảnh hưởng kết quả.
D. Đổi KEK đang hoạt động là đủ dù các DEK cũ vẫn tồn tại ở nơi khác.
Đáp án đúng: B

Một hệ thống cần tiêu hủy khóa trên thiết bị HSM đã ngừng sử dụng. Bằng chứng nào hữu ích nhất?
A. Chỉ xóa tài khoản người dùng đã từng gọi HSM trước khi tháo thiết bị.
B. Đổi nhãn thiết bị sang retired và giữ nguyên key slot để dùng lại sau.
C. Ghi lại zeroization và xác minh key slot không còn sử dụng được.
D. Xóa log quản trị nhằm bảo đảm không còn dữ liệu liên quan tới khóa.
Đáp án đúng: C

Một hệ thống cần lưu bằng chứng ai đã yêu cầu decrypt hoặc rotate khóa. Audit log nên ghi nhận điều gì?
A. Chỉ lưu plaintext được giải mã để nhóm kiểm toán kiểm tra lại nội dung.
B. Ghi actor, key identifier, thao tác, thời điểm, kết quả và request context.
C. Chỉ lưu tên alias của khóa vì không cần biết ai thực hiện thao tác.
D. Lưu toàn bộ key material và credential của caller để chứng minh tính xác thực.
Đáp án đúng: B

Một nhóm bảo mật muốn phát hiện việc một workload đột ngột gọi decrypt với tần suất tăng cao. Cơ chế nào phù hợp?
A. Chỉ kiểm tra ngày hết hạn và thời điểm tạo khóa theo lịch định kỳ hàng tháng.
B. Tắt log chi tiết để giảm tải rồi suy ra hành vi từ số lượng ciphertext.
C. Cấp thêm quyền decrypt cho workload để tránh các request bị từ chối bất thường.
D. Theo dõi audit theo workload, key, tần suất và mẫu sử dụng.
Đáp án đúng: D

Một hệ thống cần thay thuật toán mã hóa vì thuật toán cũ sắp bị loại bỏ. Thiết kế nào hỗ trợ crypto agility?
A. Gắn cố định thuật toán vào code và giải mã mọi dữ liệu theo thuật toán mới ngay lập tức.
B. Xóa mọi ciphertext cũ khi chuyển thư viện để không phải hỗ trợ nhiều định dạng.
C. Dùng một khóa duy nhất cho mọi thuật toán để tránh quản lý phiên bản.
D. Lưu thuật toán và key version; duy trì giải mã dữ liệu cũ khi chuyển đổi.
Đáp án đúng: D

Một ứng dụng dùng cùng một khóa cho mã hóa dữ liệu và ký thông điệp. Nguy cơ thiết kế nào cần được khắc phục?
A. Dùng key material riêng cho từng mục đích và thuật toán mật mã.
B. Tăng độ dài khóa hiện tại là đủ để loại bỏ rủi ro dùng chéo mục đích.
C. Chuyển khóa dùng chung sang HSM sẽ làm việc tái sử dụng trở nên an toàn.
D. Đổi tên hai alias nhưng giữ nguyên cùng key material cho cả hai thao tác.
Đáp án đúng: A

Một KMS phục vụ nhiều region và cần duy trì khả năng giải mã khi region chính gặp sự cố. Thiết kế nào cần được kiểm tra?
A. Chỉ sao chép ciphertext sang region dự phòng vì khóa luôn được suy ra từ dữ liệu.
B. Dùng cùng một endpoint region chính và dựa vào DNS để tự chuyển key material.
C. Tạo khóa mới ở region dự phòng nhưng không cần lưu metadata liên kết ciphertext cũ.
D. Kiểm tra replication, quyền, endpoint và dependency dự phòng.
Đáp án đúng: D

Một nhóm vận hành tự động hóa key rotation cho nhiều dịch vụ. Điều gì giúp tránh gián đoạn khi chuyển phiên bản khóa?
A. Xóa khóa cũ ngay khi khóa mới được tạo để buộc mọi dịch vụ cập nhật.
B. Triển khai từng bước, kiểm thử consumer rồi mới thu hồi khóa cũ.
C. Đổi alias trỏ sang khóa mới mà không kiểm tra khả năng đọc ciphertext cũ.
D. Xoay tất cả khóa cùng lúc rồi xử lý lỗi từng ứng dụng sau khi triển khai.
Đáp án đúng: B

Một tổ chức cần đánh giá hiệu quả chương trình quản lý khóa. Bộ chỉ số nào phản ánh tốt hơn mức độ kiểm soát?
A. Số lượng khóa đã tạo và tổng dung lượng ciphertext đang lưu trữ.
B. Số lần ứng dụng gọi encrypt và số alias xuất hiện trong dashboard.
C. Số quản trị viên có quyền truy cập KMS và số khóa chưa đổi tên.
D. Theo dõi inventory, owner, rotation, access review và restore.
Đáp án đúng: D
