Entropy trong bối cảnh mật mã nên được hiểu chính xác là gì?
A. Số lượng byte được tạo ra trong mỗi lần gọi bộ sinh.
B. Tốc độ sinh dữ liệu ngẫu nhiên của thiết bị.
C. Số lượng mẫu đầu ra khác nhau trong một giờ.
D. Mức độ bất định của giá trị trước khi quan sát.
Đáp án đúng: D

Min-entropy hữu ích khi đánh giá nguồn ngẫu nhiên vì lý do nào?
A. Đo tốc độ lấy mẫu tối đa của cảm biến vật lý.
B. Đếm số lần nguồn tạo ra hai giá trị khác nhau.
C. Ước lượng xác suất đoán đúng cao nhất của một kết quả.
D. Đo tổng số bit được lưu trong mỗi mẫu dữ liệu đầu ra.
Đáp án đúng: C

Vì sao thời gian hệ thống, PID và hostname thường không đủ làm seed cho CSPRNG?
A. Các giá trị này thường xuất hiện trong log hoặc thông tin vận hành.
B. Các giá trị này dễ đoán hoặc có không gian biến thiên nhỏ.
C. Số lượng byte được tạo ra trong mỗi lần gọi bộ sinh ngẫu nhiên.
D. Các giá trị này không bảo đảm độc lập giữa nhiều máy hoặc lần khởi động.
Đáp án đúng: B

Một máy chủ khởi động rất sớm khi entropy hệ thống còn thiếu; lựa chọn nào an toàn hơn?
A. Chờ nguồn ngẫu nhiên mật mã sẵn sàng trước khi sinh khóa.
B. Dùng timestamp làm seed tạm rồi thay khóa sau khi hệ thống khởi động.
C. Tự tạo seed từ PID để tránh chờ bộ tạo ngẫu nhiên.
D. Dùng đầu ra PRNG thông thường cho đến lần reboot sau.
Đáp án đúng: A

Đặc tính cốt lõi nào phân biệt CSPRNG với PRNG thông thường?
A. Đầu ra kế tiếp khó dự đoán khi trạng thái trước chưa biết.
B. Đầu ra không bao giờ lặp lại trong toàn bộ vòng đời.
C. Đầu ra được tạo bằng phần cứng thay vì phần mềm.
D. Đầu ra luôn có phân bố đều trên mọi tập byte có thể có ở mọi lần gọi.
Đáp án đúng: A

Reseeding một CSPRNG nhằm đạt mục tiêu nào?
A. Tăng độ dài khóa mà không cần tạo lại khóa mới.
B. Đổi định dạng đầu ra mà không thay đổi trạng thái nội bộ.
C. Bổ sung entropy mới để làm mới trạng thái bộ sinh.
D. Bảo đảm mọi byte đầu ra trước đó chưa từng xuất hiện.
Đáp án đúng: C

Nếu hệ thống không thể cung cấp nguồn ngẫu nhiên an toàn khi tạo khóa, ứng dụng nên xử lý thế nào?
A. Dừng thao tác nhạy cảm và báo lỗi rõ ràng.
B. Chuyển sang PRNG đơn giản để duy trì khả năng hoạt động.
C. Dùng timestamp và PID để tạo seed thay thế tạm thời.
D. Dùng seed cũ mà không kiểm tra nguồn và trạng thái.
Đáp án đúng: A

DRBG trong tiêu chuẩn mật mã thường hoạt động theo mô hình nào?
A. Mã hóa dữ liệu đầu vào bằng khóa công khai cố định.
B. Sinh đầu ra xác định từ trạng thái đã khởi tạo bằng entropy.
C. Băm timestamp rồi dùng kết quả làm khóa cho mỗi lần gọi.
D. Lấy trực tiếp từng bit từ cảm biến vật lý cho mọi yêu cầu sinh số.
Đáp án đúng: B

Một API SecureRandom có thể khác nhau giữa các nền tảng ở điểm nào?
A. API luôn dùng một thuật toán và nguồn phần cứng cố định.
B. Provider và thuật toán mặc định có thể phụ thuộc môi trường.
C. API luôn tạo cùng một chuỗi đầu ra cho cùng ứng dụng.
D. API tự động bảo đảm mọi seed do ứng dụng truyền đều đủ entropy.
Đáp án đúng: B

Vì sao không nên tự seed bộ sinh an toàn chỉ bằng vài byte dễ đoán?
A. Seed ngắn luôn khiến bộ sinh trả về ít byte hơn số byte được yêu cầu.
B. Seed yếu có thể khiến các instance khởi tạo gần nhau có trạng thái tương tự.
C. Seed yếu có thể làm giảm độ khó đoán của trạng thái ban đầu.
D. Seed do ứng dụng cung cấp luôn thay thế hoàn toàn entropy của hệ điều hành.
Đáp án đúng: C

Cách nào phù hợp để tạo khóa bí mật đối xứng mới?
A. Dùng bộ sinh mật mã an toàn với độ dài khóa phù hợp.
B. Mã hóa một timestamp bằng khóa công khai của máy chủ.
C. Lấy một đoạn đầu của UUID thời gian làm khóa bí mật.
D. Băm tên ứng dụng cùng ngày tạo khóa thành chuỗi byte.
Đáp án đúng: A

Khi chọn độ dài khóa đối xứng, yếu tố nào cần được cân nhắc?
A. Số bit đầu ra mà hàm băm được dùng trong hệ thống có thể tạo.
B. Mức an toàn mục tiêu, thuật toán và yêu cầu tương thích.
C. Độ dài lớn nhất mà định dạng lưu trữ hiện tại cho phép.
D. Số byte mà bộ sinh ngẫu nhiên trả về trong một mili giây.
Đáp án đúng: B

Khi cần tạo nhiều khóa con từ một bí mật gốc, cơ chế nào phù hợp?
A. Dùng cùng khóa gốc trực tiếp cho mọi mục đích mã hóa.
B. Cắt khóa gốc thành các đoạn không cần phân tách ngữ cảnh.
C. Băm khóa gốc một lần rồi dùng chung kết quả cho mọi dịch vụ.
D. Dùng KDF với salt và thông tin ngữ cảnh tách biệt.
Đáp án đúng: D

Nonce trong giao thức mật mã thường có vai trò nào?
A. Mã xác thực người dùng được gửi kèm mọi request.
B. Giá trị dùng một lần để phân biệt lần thực thi hoặc thông điệp.
C. Giá trị công khai dùng thay thế chứng thư của máy chủ.
D. Khóa bí mật thứ hai được dùng để giải mã bản mã.
Đáp án đúng: B

Với AES-GCM, vì sao không được tái sử dụng nonce cùng một khóa?
A. Nonce lặp chỉ ảnh hưởng hiệu năng của phép giải mã.
B. Tái sử dụng nonce chỉ khiến bản mã dài thêm vài byte.
C. Tái sử dụng nonce có thể làm lộ dữ liệu và phá xác thực.
D. GCM sẽ tự đổi khóa bí mật khi phát hiện nonce bị lặp.
Đáp án đúng: C

Với AES-CBC, IV nên đáp ứng yêu cầu nào?
A. IV phải giữ bí mật như khóa mã hóa chính trong suốt vòng đời dữ liệu.
B. IV phải bằng không để mọi block có cùng định dạng.
C. IV cần khó đoán và không được tái sử dụng theo cùng khóa.
D. IV phải được tạo từ plaintext để bên nhận tự tính lại.
Đáp án đúng: C

Trong chế độ CTR, điều kiện quan trọng nhất với nonce và counter là gì?
A. Counter phải được tạo ngẫu nhiên lại cho từng block.
B. Nonce phải giống nhau giữa mọi phiên để đồng bộ giải mã.
C. Mỗi nonce phải được giữ bí mật khỏi bên nhận dữ liệu.
D. Không để tổ hợp nonce-counter lặp dưới cùng khóa.
Đáp án đúng: D

Một bearer token ngẫu nhiên cần chống đoán; thuộc tính nào quan trọng nhất?
A. Có checksum để phát hiện lỗi gõ khi token được sao chép.
B. Có tiền tố dễ nhớ để người dùng nhận ra token của mình.
C. Đủ entropy, sinh bằng CSPRNG và có độ dài phù hợp.
D. Được tạo từ username và thời điểm đăng nhập gần nhất.
Đáp án đúng: C

UUIDv4 khác UUIDv1 ở đặc điểm nào liên quan đến tính khó đoán?
A. UUIDv1 luôn có entropy cao hơn vì chứa timestamp chính xác.
B. UUIDv4 dùng bit ngẫu nhiên; UUIDv1 có thành phần thời gian và node.
C. UUIDv4 được mã hóa bằng khóa riêng còn UUIDv1 thì không.
D. Hai phiên bản đều bảo đảm bí mật và an toàn làm bearer token.
Đáp án đúng: B

Khi chọn số ngẫu nhiên trong một khoảng không chia hết cho không gian đầu ra, cần tránh lỗi nào?
A. Floating-point drift làm bộ sinh mất seed sau mỗi lần gọi.
B. Endianness khiến cùng một số được lưu thành hai khóa khác nhau.
C. Integer overflow khiến mọi kết quả trở thành số âm.
D. Modulo bias khiến một số kết quả xuất hiện thường xuyên hơn.
Đáp án đúng: D

Cách nào tạo phép xáo trộn Fisher-Yates không thiên lệch?
A. Hoán đổi mỗi phần tử với một chỉ số cố định được sinh đầu tiên.
B. Chọn chỉ số bất kỳ trong toàn mảng cho từng phần tử.
C. Chọn chỉ số đều trong phần chưa xáo trộn ở mỗi bước.
D. Sắp xếp phần tử theo giá trị hash của chỉ số ban đầu.
Đáp án đúng: C

Vì sao một ID ngẫu nhiên khó đoán không thể thay thế kiểm tra quyền truy cập?
A. ID ngẫu nhiên luôn được xem là dữ liệu công khai trong mọi hệ thống.
B. ID có entropy cao tự động giới hạn quyền theo từng người dùng.
C. ID khó đoán làm máy chủ không cần xác minh danh tính phiên.
D. Tính khó đoán của ID không chứng minh người gọi được phép truy cập.
Đáp án đúng: D

Băm timestamp bằng SHA-256 có tạo ra token mật mã an toàn không?
A. Có, nếu timestamp được kết hợp với salt công khai trước khi băm.
B. Không, vì hàm hash không bổ sung entropy cho đầu vào.
C. Có, vì SHA-256 luôn tạo ra đầu ra có entropy tối đa.
D. Không, đầu vào dễ đoán nên đầu ra hash cũng có thể bị đoán.
Đáp án đúng: D

Salt trong quy trình lưu mật khẩu nên được tạo như thế nào?
A. Salt ngẫu nhiên riêng cho mỗi mật khẩu bằng nguồn an toàn.
B. Salt lấy từ username để dễ tái tạo khi xác minh đăng nhập.
C. Salt bí mật dùng chung để mọi tài khoản có cùng cấu hình lưu trữ.
D. Salt cố định theo tên ứng dụng để hỗ trợ tra cứu nhanh.
Đáp án đúng: A

HKDF thường được dùng cho mục đích nào?
A. Dẫn xuất các khóa có ngữ cảnh từ đầu vào khóa đã có entropy.
B. Tạo entropy mới từ dữ liệu đầu vào hoàn toàn có thể đoán.
C. Thay thế CSPRNG để sinh trực tiếp nonce cho mọi giao thức.
D. Mã hóa dữ liệu dung lượng lớn bằng một khóa bất kỳ.
Đáp án đúng: A

Với ECDSA, việc tái sử dụng nonce ký có thể gây hậu quả nào?
A. Nonce lặp chỉ làm hai chữ ký có cùng giá trị hash đầu vào.
B. Có thể làm lộ private key từ các chữ ký liên quan.
C. Chỉ khiến chứng thư X.509 bị sai định dạng khi truyền.
D. Chỉ làm chữ ký dài hơn và chậm xác minh hơn.
Đáp án đúng: B

Tại sao RSA-PSS hoặc RSA-OAEP cần cơ chế ngẫu nhiên trong quá trình sử dụng?
A. Salt ngẫu nhiên thay thế nhu cầu xác minh chữ ký sau giải mã.
B. Ngẫu nhiên tạo một public key mới cho từng thông điệp.
C. Padding ngẫu nhiên tự bảo đảm nội dung không thể bị sửa đổi.
D. Salt hoặc padding ngẫu nhiên giúp đạt thuộc tính bảo mật mong muốn.
Đáp án đúng: D

Một chữ ký số an toàn phụ thuộc vào nguồn ngẫu nhiên ở khâu nào?
A. Xác minh chữ ký bằng public key ở phía người nhận.
B. Chuyển chữ ký nhị phân sang định dạng văn bản PEM.
C. Tạo khóa và các thuật toán ký có thành phần ngẫu nhiên.
D. So sánh tên chủ thể trong chứng thư với tên người ký.
Đáp án đúng: C

Trong TLS hiện đại, nguồn ngẫu nhiên chất lượng cao hỗ trợ cơ chế nào?
A. Thay thế xác minh hostname bằng giá trị ngẫu nhiên trong chứng thư.
B. Tạo cùng một seed cố định để client và server đồng bộ khóa phiên.
C. Tạo khóa phiên và giá trị mật mã tạm thời trong handshake.
D. Chọn địa chỉ IP của máy chủ và cổng TCP cho kết nối.
Đáp án đúng: C

Ephemeral Diffie-Hellman đóng góp forward secrecy như thế nào?
A. Lưu bí mật phiên trong chứng thư để client có thể tải lại.
B. Dùng bí mật tạm thời mới cho mỗi phiên và loại bỏ sau sử dụng.
C. Dùng lại một private key dài hạn cho mọi phiên TLS.
D. Mã hóa private key máy chủ bằng nonce gửi trong ClientHello.
Đáp án đúng: B

Vì sao session ticket encryption key cần được luân chuyển định kỳ?
A. Giúp giải mã mọi ticket cũ mà không cần giữ khóa ticket cũ.
B. Giới hạn tác động khi khóa ticket bị lộ và quản lý thời hạn ticket.
C. Bảo đảm mỗi ticket được cấp có một session key khác nhau.
D. Làm thời hạn ticket tự động bằng chu kỳ xoay khóa.
Đáp án đúng: B

Serial number của chứng thư X.509 cần được tạo và quản lý ra sao?
A. Lấy serial từ private key để bên nhận có thể tái tạo.
B. Đặt serial theo thời gian hiện tại mà không cần kiểm tra trùng.
C. Dùng chung một serial cho mọi chứng thư cùng Subject.
D. Bảo đảm duy nhất trong phạm vi CA và tuân thủ yêu cầu chuẩn.
Đáp án đúng: D

Khi dùng HSM có bộ sinh số ngẫu nhiên phần cứng, kiểm soát nào vẫn cần thiết?
A. Kiểm tra trạng thái, cấu hình nguồn entropy và quy trình vận hành HSM.
B. Dùng cùng seed cố định để các HSM tạo ra khóa tương thích.
C. Tin cậy mọi đầu ra phần cứng mà không cần kiểm tra sức khỏe.
D. Tắt kiểm soát truy cập vì private key không rời khỏi HSM.
Đáp án đúng: A

Một TRNG phần cứng thường cần bước nào trước khi đầu ra dùng làm entropy cho CSPRNG?
A. Kiểm tra sức khỏe nguồn và conditioning theo thiết kế.
B. Mã hóa đầu ra bằng khóa công khai rồi bỏ qua kiểm tra thống kê.
C. Nối các mẫu thô liên tiếp mà không cần đánh giá chất lượng.
D. Loại bỏ byte trùng rồi xem phần còn lại có phân bố đều.
Đáp án đúng: A

Sau khi khôi phục VM từ snapshot, vì sao cần chú ý trạng thái CSPRNG?
A. VM khôi phục không thể truy cập nguồn ngẫu nhiên của hệ điều hành.
B. Hệ điều hành khách luôn nhận biết bản clone và reseed trước lần đọc đầu.
C. Snapshot luôn xóa toàn bộ entropy đã thu thập trước đó.
D. Snapshot có thể nhân bản trạng thái khiến hai VM sinh cùng chuỗi.
Đáp án đúng: D

Vì sao kiểm thử thống kê đầu ra không đủ chứng minh một bộ sinh là CSPRNG an toàn?
A. Phân bố đẹp không chứng minh khả năng chống dự đoán trước tấn công.
B. Một chuỗi kiểm thử dài đạt yêu cầu chứng minh nguồn entropy không bị lệch.
C. Bộ sinh vượt kiểm định phân bố thì đầu ra không thể bị dự đoán.
D. CSPRNG an toàn phải tạo đầu ra không bao giờ có byte lặp.
Đáp án đúng: A
