Mục tiêu nào được cung cấp trực tiếp bởi mã hóa dữ liệu bằng khóa bí mật?
A. Phát hiện mọi thay đổi dữ liệu mà không cần khóa.
B. Giữ nội dung bí mật với bên không có khóa phù hợp.
C. Chứng minh danh tính người tạo ra thông điệp.
D. Ngăn người gửi phủ nhận việc đã tạo thông điệp.
Đáp án đúng: B

Trong mã hóa đối xứng, bên gửi và bên nhận cần điều kiện nào?
A. Bên nhận dùng private key để mở ciphertext từ public key bên gửi.
B. Hai bên tự tạo khóa riêng, không đồng bộ bí mật dùng chung.
C. Khóa giải mã được gửi kèm ciphertext qua cùng kênh truyền.
D. Hai bên cùng giữ khóa bí mật để mã hóa và giải mã.
Đáp án đúng: D

Đặc điểm nào mô tả đúng mật mã bất đối xứng?
A. Luôn nhanh hơn mã hóa đối xứng với dữ liệu lớn.
B. Dùng một khóa bí mật duy nhất cho cả hai chiều.
C. Không cần bảo vệ private key khi đã có chứng chỉ.
D. Dùng cặp khóa công khai và riêng tư có quan hệ toán học.
Đáp án đúng: D

Vì sao hệ thống thường dùng mô hình mã hóa lai?
A. Bất đối xứng thiết lập khóa; đối xứng mã hóa dữ liệu.
B. Dùng hash để mã hóa dữ liệu rồi dùng MAC để giải mã.
C. Dùng khóa công khai cho toàn bộ dữ liệu nhằm tăng tốc.
D. Dùng hai thuật toán đối xứng cùng khóa cho mọi payload.
Đáp án đúng: A

Điểm yếu chính của chế độ AES-ECB khi mã hóa dữ liệu có mẫu lặp là gì?
A. ECB dùng IV ngẫu nhiên cho mỗi message để che mẫu lặp.
B. ECB liên kết mỗi khối với khối trước để khuếch tán thay đổi.
C. Khối plaintext lặp tạo ra khối ciphertext giống nhau.
D. ECB tự xác minh MAC tag trước khi trả plaintext.
Đáp án đúng: C

AES-GCM cung cấp những thuộc tính nào khi được dùng đúng cách?
A. Cung cấp mã hóa kèm xác thực tính toàn vẹn dữ liệu.
B. GCM chỉ xác thực AAD mà không xác thực ciphertext payload.
C. GCM che payload nhưng không xác thực thay đổi ciphertext.
D. GCM cần chữ ký số riêng để kiểm tra toàn vẹn mỗi message.
Đáp án đúng: A

Điều kiện quan trọng nào áp dụng cho nonce khi dùng AES-GCM với cùng khóa?
A. Nonce không được lặp lại dưới cùng một khóa.
B. Nonce phải giữ bí mật giống như khóa mã hóa.
C. Nonce có thể lặp nếu plaintext của hai message khác nhau.
D. Nonce cần ngẫu nhiên, không cần bảo đảm duy nhất.
Đáp án đúng: A

Trong AEAD, Associated Data (AAD) có đặc điểm nào?
A. AAD được xác thực và cũng được mã hóa cùng ciphertext.
B. AAD chỉ được dùng làm nonce khi giải mã message.
C. AAD được mã hóa cùng payload nhưng không tham gia xác thực.
D. AAD được xác thực cùng ciphertext nhưng không mã hóa.
Đáp án đúng: D

Vì sao dùng AES-CBC đơn lẻ thường chưa đủ để bảo vệ thông điệp?
A. CBC bảo đảm toàn vẹn nếu IV được tạo ngẫu nhiên và bí mật.
B. CBC cần MAC riêng hoặc chế độ AEAD để bảo vệ toàn vẹn.
C. CBC chống sửa đổi nếu padding được kiểm tra trước khi trả dữ liệu.
D. CBC tự xác thực nguồn gốc bằng IV duy nhất của mỗi message.
Đáp án đúng: B

Padding oracle có thể xuất hiện khi hệ thống xử lý lỗi CBC như thế nào?
A. Phản hồi lỗi khác nhau có thể tiết lộ trạng thái padding.
B. Server trả lỗi chung cho mọi ciphertext nên không tiết lộ padding.
C. Attacker phải biết private key mới tạo được ciphertext sửa đổi.
D. Lỗi padding chỉ tiết lộ IV, không cho biết trạng thái giải mã.
Đáp án đúng: A

Khi dùng ChaCha20-Poly1305, yêu cầu nào tương tự AES-GCM?
A. Nonce có thể dùng lại nếu mỗi message có tag mới.
B. Nonce phải duy nhất khi dùng lại cùng khóa AEAD.
C. Poly1305 tự sinh nonce nên caller không cần quản lý.
D. Tag phải được gửi qua một kênh bí mật riêng.
Đáp án đúng: B

Một digest SHA-256 công khai có thể chứng minh điều gì?
A. Chỉ xác nhận nội dung khớp với digest đã biết.
B. Dữ liệu không thể bị thay đổi bởi người có chủ đích.
C. Người gửi chắc chắn là chủ sở hữu của dữ liệu.
D. Thông điệp được giữ bí mật trong quá trình truyền.
Đáp án đúng: A

HMAC khác hash thông thường ở điểm cốt lõi nào?
A. HMAC tạo tag bằng khóa bí mật được các bên chia sẻ.
B. HMAC dùng private key để tạo chữ ký có thể công khai.
C. HMAC tự mã hóa payload trước khi tạo digest.
D. HMAC không cần khóa vì dựa trên collision resistance.
Đáp án đúng: A

Trong chữ ký số thông thường, khóa nào được dùng để ký và xác minh?
A. Cùng một secret key được cả hai bên dùng để ký.
B. Private key người nhận ký, public key người gửi giải mã.
C. Private key ký; public key tương ứng xác minh chữ ký.
D. Public key ký, private key của người nhận xác minh.
Đáp án đúng: C

Chữ ký số hợp lệ có tự chứng minh signer là một tổ chức đáng tin không?
A. Không; chữ ký số chỉ dùng để mã hóa nội dung bí mật.
B. Có; chữ ký hợp lệ tự xác nhận danh tính pháp lý của signer.
C. Không; cần tin cậy binding giữa public key và signer.
D. Có; mọi public key đều mặc nhiên thuộc chủ thể ghi trong file.
Đáp án đúng: C

Nguồn ngẫu nhiên mật mã cần đáp ứng yêu cầu nào?
A. Chỉ cần chuỗi trông ngẫu nhiên khi quan sát bằng mắt.
B. Có thể dùng timestamp hiện tại làm seed duy nhất.
C. Nên dùng bộ sinh giả ngẫu nhiên thông thường cho khóa.
D. CSPRNG cần entropy đủ từ nguồn ngẫu nhiên tin cậy.
Đáp án đúng: D

Salt và nonce khác nhau chủ yếu ở mục đích nào?
A. Salt là IV cho block cipher; nonce là salt cho password hash.
B. Salt dùng để giải mã; nonce dùng để ký dữ liệu.
C. Salt và nonce đều phải giữ bí mật như khóa mật mã.
D. Salt phân biệt đầu vào hash; nonce tạo tính mới trong giao thức.
Đáp án đúng: D

HKDF thường được dùng để làm gì?
A. HKDF dẫn xuất khóa con theo context và mục đích.
B. Tạo chữ ký số mà không cần cặp khóa.
C. Mã hóa trực tiếp file lớn bằng một passphrase.
D. Thay thế CSPRNG để tạo entropy từ timestamp.
Đáp án đúng: A

Vì sao không nên lưu mật khẩu bằng một lần SHA-256 đơn giản?
A. Salt riêng cho từng mật khẩu khiến một vòng hash đủ chậm.
B. SHA-256 luôn giải mã ngược được về mật khẩu gốc.
C. SHA-256 yêu cầu public key để xác minh digest.
D. Hash nhanh cho phép thử rất nhiều mật khẩu mỗi giây.
Đáp án đúng: D

RSA-OAEP và RSA-PSS thường phục vụ mục đích nào tương ứng?
A. OAEP cho chữ ký; PSS cho mã hóa dữ liệu.
B. Cả hai đều là chế độ mã hóa xác thực AEAD.
C. OAEP cho băm; PSS cho trao đổi khóa đối xứng.
D. OAEP dùng để mã hóa; PSS tạo chữ ký số.
Đáp án đúng: D

Sau ECDH, ứng dụng nên xử lý shared secret như thế nào?
A. Dùng KDF để dẫn xuất khóa phiên từ shared secret.
B. Công bố shared secret để xác minh public key.
C. Dùng trực tiếp làm nonce cho mọi bản tin.
D. Ghi shared secret vào log để hai bên đối chiếu.
Đáp án đúng: A

Forward secrecy trong một phiên TLS thường được hỗ trợ bởi cơ chế nào?
A. Dùng khóa trao đổi tạm thời và xóa private key tạm thời.
B. Dùng một RSA private key cố định để mã hóa mọi phiên.
C. Lưu lại toàn bộ ephemeral private key để phục hồi phiên.
D. Dùng chung một session key cho tất cả kết nối.
Đáp án đúng: A

Khi xác minh chứng chỉ TLS cho một hostname, client cần làm gì?
A. Chỉ kiểm tra chữ ký của leaf certificate bằng chính nó.
B. Chấp nhận mọi chứng chỉ nếu handshake hoàn tất.
C. Chỉ kiểm tra Common Name và bỏ qua hostname thực tế.
D. Kiểm tra chain tin cậy và hostname trong SAN phù hợp.
Đáp án đúng: D

Chứng chỉ máy chủ còn hạn và có chữ ký CA hợp lệ nhưng sai hostname thì sao?
A. Client nên thử mã hóa dữ liệu rồi mới quyết định tin cậy.
B. Client có thể chấp nhận nếu khóa công khai đủ dài.
C. Client chỉ cần kiểm tra OCSP rồi bỏ qua hostname.
D. Sai hostname thì client phải từ chối chứng chỉ.
Đáp án đúng: D

PKI dùng certificate chủ yếu để cung cấp điều gì?
A. Cơ chế mã hóa mọi dữ liệu mà không cần private key.
B. Certificate ràng buộc public key với danh tính hoặc thuộc tính.
C. Một bản sao private key để các bên dùng chung.
D. Bằng chứng rằng mọi ứng dụng trong CA đều an toàn.
Đáp án đúng: B

Base64 có vai trò gì khi truyền dữ liệu mật mã?
A. Tạo chữ ký số có thể xác minh bằng public key.
B. Bảo vệ toàn vẹn bằng MAC với khóa dùng chung.
C. Base64 biểu diễn byte dạng văn bản, không giữ bí mật.
D. Mã hóa nội dung bằng khóa đối xứng có độ dài cố định.
Đáp án đúng: C

Vì sao so sánh MAC tag hoặc secret nên dùng constant-time comparison?
A. Tự động xác minh nguồn gốc public key của bên gửi.
B. Constant-time giảm rò rỉ qua thời gian so sánh byte.
C. Tăng entropy của tag trong quá trình xác minh.
D. Ngăn mọi loại replay mà không cần nonce hoặc trạng thái.
Đáp án đúng: B

Key separation giúp giảm rủi ro nào trong thiết kế mật mã?
A. Loại bỏ nhu cầu xác minh certificate chain trong TLS.
B. Cho phép dùng lại nonce giữa các thuật toán khác nhau.
C. Dùng khóa riêng cho từng mục đích và ngữ cảnh.
D. Giúp một khóa ngắn đạt mức an toàn của khóa dài.
Đáp án đúng: C

Khi xoay KEK trong envelope encryption, thao tác nào thường đủ nếu DEK vẫn an toàn?
A. Rewrap DEK bằng KEK mới, không mã hóa lại payload.
B. Đổi nonce nhưng giữ nguyên KEK và DEK đã lộ.
C. Băm payload bằng khóa mới để thay ciphertext hiện tại.
D. Xóa payload cũ rồi tạo lại toàn bộ dữ liệu từ đầu.
Đáp án đúng: A

Vì sao nên tách khóa mã hóa dữ liệu và khóa ký số?
A. Khóa mã hóa không thể được xoay vòng khi còn dữ liệu.
B. Tách khóa để giới hạn quyền và rủi ro dùng sai.
C. Khóa ký luôn có thể dùng thay khóa mã hóa đối xứng.
D. Một khóa dùng chung giúp chữ ký tự động có tính bí mật.
Đáp án đúng: B

Nonce dạng bộ đếm có ưu điểm nào khi được quản lý đúng?
A. Không cần lưu trạng thái vì mọi node tự chọn cùng giá trị.
B. Luôn bí mật nên attacker không thể quan sát nonce.
C. Bộ đếm giúp nonce duy nhất nếu quản lý trạng thái đúng.
D. Có thể reset bộ đếm sau restart mà không ảnh hưởng an toàn.
Đáp án đúng: C

Điều gì có thể xảy ra nếu hai node dùng cùng khóa và bộ đếm nonce độc lập?
A. Ciphertext tự động thêm salt để tránh va chạm.
B. Hai node có thể sinh nonce trùng dưới cùng khóa.
C. Nonce trùng chỉ ảnh hưởng hiệu năng chứ không ảnh hưởng an toàn.
D. Chữ ký số tự chuyển thành MAC khi nonce bị trùng.
Đáp án đúng: B

Độ dài khóa đối xứng nên được lựa chọn dựa trên yếu tố nào?
A. Số lượng người dùng có quyền truy cập cùng hệ thống.
B. Chọn theo mức an toàn và thời gian bảo vệ dữ liệu.
C. Kích thước file lớn nhất mà ứng dụng cần mã hóa.
D. Độ dài hostname của máy chủ nhận ciphertext.
Đáp án đúng: B

Cryptographic agility có ý nghĩa gì trong một hệ thống lâu dài?
A. Tự chọn thuật toán bất kỳ từ header do client gửi.
B. Giữ nguyên thuật toán cũ để dữ liệu luôn tương thích.
C. Cho phép thay thuật toán và tham số khi tiêu chuẩn đổi.
D. Bỏ metadata thuật toán nhằm đơn giản hóa định dạng.
Đáp án đúng: C

Vì sao không nên tự thiết kế thuật toán hoặc chế độ mật mã mới?
A. Mọi thuật toán tự viết đều chậm hơn mọi thuật toán chuẩn.
B. Chỉ thư viện thương mại mới được phép thực hiện mật mã.
C. Thiết kế sai dễ tạo lỗi khó phát hiện bằng kiểm thử.
D. Thuật toán chuẩn không thể chạy trên phần cứng hiện đại.
Đáp án đúng: C

Khi giải mã AEAD, ứng dụng nên xử lý plaintext khi nào?
A. Ghi plaintext ra file tạm trước khi xác minh tag.
B. Chỉ dùng plaintext sau khi tag xác thực thành công.
C. Đọc plaintext trước rồi kiểm tra tag sau khi xử lý nghiệp vụ.
D. Bỏ qua tag nếu ciphertext đến từ mạng nội bộ.
Đáp án đúng: B

Trong mã hóa lai cho thông điệp gửi tới người nhận, ai dùng khóa nào?
A. Mã hóa dữ liệu bằng public key người gửi và bọc bằng private key.
B. Dùng private key người nhận để mã hóa payload rồi công bố DEK.
C. DEK mã hóa payload; public key bọc DEK cho người nhận.
D. Băm payload bằng public key người nhận để có thể giải mã sau.
Đáp án đúng: C
