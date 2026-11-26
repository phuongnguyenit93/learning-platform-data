Câu 1. Trong JCA, Security Provider có vai trò chính nào?
A. Quản lý principal của user trong mọi JAAS LoginContext
B. Sinh certificate chain TLS từ mọi class trong JAR
C. Giữ session key của mọi TLS connection đang mở
D. Provider cung cấp implementation qua service chuẩn
Đáp án đúng: D

Câu 2. Trong JCA, MessageDigest.getInstance("SHA-256") thường làm gì?
A. Tạo khóa bí mật cho mọi lệnh mã hóa AES-GCM
B. Lấy MessageDigest SHA-256 từ provider hỗ trợ
C. Đăng ký một truststore mới cho toàn bộ JVM
D. Sinh chữ ký RSA bằng private key mặc định
Đáp án đúng: B

Câu 3. Để biết provider thực thi một đối tượng Cipher đã lấy, dùng API nào?
A. cipher.getProvider() cho biết Provider của engine đó
B. cipher.getParameters() trả Provider trong keyStore
C. cipher.getBlockSize() trả mã định danh của Provider
D. cipher.getAlgorithm() trả tên class của provider
Đáp án đúng: A

Câu 4. Để sinh key material bằng Java, loại API nào phù hợp để lấy bytes ngẫu nhiên an toàn?
A. Random.nextBytes có cùng cam kết bảo mật mặc định
B. ThreadLocalRandom.nextBytes bảo đảm chống đoán seed
C. SplittableRandom tự tạo entropy từ truststore của JVM
D. SecureRandom.nextBytes điền dữ liệu ngẫu nhiên mật mã
Đáp án đúng: D

Câu 5. Với SecureRandom.setSeed(bytes), phát biểu nào đúng về trạng thái bộ sinh?
A. Mọi provider buộc reset state về bytes được cấp làm seed
B. Seed được trộn thêm, không nhất thiết reset bộ sinh
C. setSeed biến một SecureRandom thành Random không mã hóa
D. setSeed tự thay nội dung của keyStore mặc định trong JVM
Đáp án đúng: B

Câu 6. Trong giao thức mã hóa, phân biệt salt với nonce/IV phù hợp nhất là gì?
A. Salt thường cho KDF; nonce/IV dùng trong chế độ mã hóa
B. Salt là private key; nonce là public key của cùng cặp
C. Salt phải bí mật; nonce dùng thay authentication tag
D. Salt luôn chính là ciphertext; IV là chữ ký số
Đáp án đúng: A

Câu 7. API MessageDigest.digest(data) của SHA-256 dùng để tạo kết quả nào?
A. Chữ ký số kiểm chứng được bằng public key
B. MAC cần khóa bí mật của phía gửi và phía nhận
C. Digest cố định độ dài từ dữ liệu đầu vào
D. Bản mã AES có thể giải bằng cùng secret key
Đáp án đúng: C

Câu 8. Tại sao không nên dùng SHA-256 trực tiếp để lưu mật khẩu người dùng?
A. SHA-256 chỉ chấp nhận dữ liệu nhị phân không hỗ trợ text
B. SHA-256 đòi certificate X.509 trước khi tính digest
C. SHA-256 có thể giải ngược thành plaintext bằng API Cipher
D. SHA-256 quá nhanh cho password; nên dùng KDF chuyên dụng
Đáp án đúng: D

Câu 9. Trong Java, cặp API và thuật toán nào phù hợp để tạo khóa từ mật khẩu?
A. MessageDigest với SHA-256 và RSAPrivateKeySpec
B. Cipher với AES/GCM/NoPadding và PKCS8EncodedKeySpec
C. SecretKeyFactory với PBKDF2WithHmacSHA256 và PBEKeySpec
D. Signature với SHA256withRSA và GCMParameterSpec
Đáp án đúng: C

Câu 10. Salt riêng cho mỗi mật khẩu khi dùng PBKDF2 giúp ích chủ yếu thế nào?
A. Salt riêng làm hash khác nhau và chống bảng đoán sẵn
B. Thay vai trò iteration count nên có thể chọn vòng lặp bằng một
C. Cho phép bỏ lưu salt vì có thể phục hồi từ kết quả KDF
D. Biến PBKDF2 thành thuật toán mã hóa có thể giải ngược
Đáp án đúng: A

Câu 11. Để so sánh hai MAC hoặc digest nhạy cảm, cách nào phù hợp trong JDK?
A. Dùng String.equals vì Java tự so sánh hằng thời gian
B. Dùng MessageDigest.isEqual để giảm rò rỉ thời gian so sánh
C. Dùng Arrays.hashCode vì hash code luôn không phụ thuộc input
D. Dùng Comparator.naturalOrder để chống timing attack
Đáp án đúng: B

Câu 12. Với HmacSHA256, Java API nào thường tạo đối tượng tính MAC?
A. MessageDigest.getInstance("HmacSHA256") với public key
B. Signature.getInstance("HmacSHA256") với X509Certificate
C. Mac.getInstance("HmacSHA256") với SecretKey thích hợp
D. Cipher.getInstance("HmacSHA256") với RSA private key
Đáp án đúng: C

Câu 13. MAC khác hash không khóa ở tính chất nào?
A. MAC mặc định công khai và không bao giờ dùng khóa bí mật
B. Hash không khóa có thể chứng minh danh tính người gửi
C. Hash không khóa tự ngăn thay đổi nếu đối thủ sửa cả digest
D. MAC dùng secret key để xác thực tính toàn vẹn dữ liệu
Đáp án đúng: D

Câu 14. SecretKeySpec trong JCE thường được dùng để làm gì?
A. Tạo số ngẫu nhiên mới từ mật khẩu và salt bằng PBKDF2
B. Lưu cặp khóa riêng/công khai theo định dạng PKCS12
C. Gói byte khóa và tên thuật toán thành một SecretKey
D. Xác minh certificate chain bằng các trust anchors JVM
Đáp án đúng: C

Câu 15. Để sinh khóa AES mới theo độ dài lựa chọn, API nào phù hợp?
A. KeyPairGenerator.getInstance("AES") rồi lấy private key
B. KeyGenerator.getInstance("AES") rồi sinh SecretKey mới
C. MessageDigest.getInstance("AES") rồi digest dữ liệu
D. CertificateFactory.getInstance("AES") rồi generateKey
Đáp án đúng: B

Câu 16. Trong AES, độ dài khóa nào là một giá trị hợp lệ theo chuẩn?
A. 160, 224 hoặc 384 bit là các độ dài khóa AES
B. 112, 168 hoặc 336 bit là các độ dài khóa AES
C. 96, 160 hoặc 512 bit là các độ dài khóa AES
D. 128, 192 hoặc 256 bit là các độ dài khóa AES
Đáp án đúng: D

Câu 17. Để mã hóa dữ liệu có bảo vệ cả toàn vẹn trong JCE, transformation nào phù hợp?
A. Cipher.getInstance("AES/GCM/NoPadding") cho AEAD
B. Cipher.getInstance("AES/ECB/NoPadding") cho AEAD
C. Cipher.getInstance("AES/CBC/PKCS5Padding") cho AEAD
D. Cipher.getInstance("AES/CTR/NoPadding") cho AEAD
Đáp án đúng: A

Câu 18. Khi tạo GCMParameterSpec(128, iv), số 128 chỉ giá trị nào?
A. Độ dài AES key dùng trong Cipher.init theo đơn vị byte
B. Độ dài IV AES-GCM dùng trong Cipher.init theo đơn vị bit
C. 128 là số bit của authentication tag, không phải IV
D. Số vòng PBKDF2 dùng để tạo secret key cho AES
Đáp án đúng: C

Câu 19. Tái sử dụng IV/nonce với cùng khóa AES-GCM có nguy cơ chính nào?
A. Chỉ khiến ciphertext dài hơn dù plaintext không đổi
B. Lặp nonce cùng khóa làm GCM mất an toàn và tính xác thực
C. Chỉ làm chậm bắt tay TLS khi hai bên dùng cùng khóa
D. Tự tăng kích thước authentication tag sau mỗi lần mã hóa
Đáp án đúng: B

Câu 20. Khi giải mã AES-GCM với authentication tag sai, hành vi nào nên mong đợi?
A. Cipher.doFinal trả plaintext và chỉ thêm warning vào log
B. Cipher.doFinal ném AEADBadTagException nếu tag không hợp lệ
C. Cipher.doFinal sinh lại IV mới rồi chấp nhận message
D. Cipher.doFinal luôn trả null thay cho bất kỳ exception
Đáp án đúng: B

Câu 21. Để ràng buộc metadata không mã hóa vào AES-GCM, dùng API nào?
A. Cipher.getIV sau khi đã gọi doFinal để ký metadata
B. Cipher.getProvider rồi thay key AES bằng metadata
C. Cipher.updateAAD dùng trước khi xử lý payload mã hóa
D. Cipher.wrap trên AAD để tạo authentication tag riêng
Đáp án đúng: C

Câu 22. Vì sao AES/CBC có padding không tự thay thế authenticated encryption?
A. CBC chỉ cung cấp mã hóa, cần cơ chế xác thực phù hợp
B. CBC tự tạo MAC tag độc lập với ciphertext trong doFinal
C. CBC xác minh certificate X.509 trước khi trả plaintext
D. CBC ngăn replay cho mọi IV dù không có kiểm tra nào
Đáp án đúng: A

Câu 23. AES/ECB bị khuyến cáo tránh dùng cho dữ liệu nhiều block vì sao?
A. ECB mặc định thêm tag và khiến dữ liệu bị kéo dài gấp đôi
B. Plaintext block trùng có thể tạo ciphertext block trùng
C. ECB luôn sinh IV bí mật nên client không giải mã được
D. ECB chỉ mã hóa đúng một block, không thể nhận input dài hơn
Đáp án đúng: B

Câu 24. Khi mã hóa bằng Cipher, phương thức nào thường hoàn tất bước cuối và padding/tag?
A. Cipher.getAlgorithm hoàn tất và trả bytes bản mã
B. Cipher.getProvider ghi authentication tag vào keyStore
C. Cipher.getBlockSize tự xuất ciphertext sau khi update
D. Cipher.doFinal hoàn tất tác vụ xử lý bản mã
Đáp án đúng: D

Câu 25. Nếu giải mã AEAD thất bại xác thực, cách xử lý an toàn nào phù hợp?
A. Không sử dụng plaintext chưa xác thực và từ chối message
B. Dùng các bytes đã update để xử lý nghiệp vụ trước doFinal
C. Tự bỏ tag rồi chấp nhận plaintext nếu padding hợp lệ
D. Đổi sang AES/ECB rồi thử giải mã lại cùng ciphertext
Đáp án đúng: A

Câu 26. Khi mã hóa một khóa đối xứng nhỏ bằng RSA hiện đại, padding nào thích hợp?
A. RSA/ECB/NoPadding để tránh overhead khi mã hóa khóa
B. RSA/ECB/PKCS1Padding cho OAEP với SHA-256 mặc định
C. RSA/GCM/NoPadding để tạo AEAD trực tiếp từ RSA
D. Dùng RSA/ECB/OAEPWithSHA-256AndMGF1Padding khi hỗ trợ
Đáp án đúng: D

Câu 27. Tại sao ứng dụng thường dùng hybrid encryption thay vì RSA cho dữ liệu lớn?
A. RSA luôn nhanh hơn AES khi dữ liệu đầu vào lớn
B. RSA tạo ciphertext ngắn bằng plaintext với mọi key size
C. AES-GCM không cho phép chia payload thành nhiều bytes
D. RSA bọc khóa phiên; AES-GCM mã hóa payload dung lượng lớn
Đáp án đúng: D

Câu 28. Trong JCA, API nào thường tạo cặp khóa bất đối xứng RSA hoặc EC?
A. KeyPairGenerator tạo KeyPair theo thuật toán được chọn
B. KeyGenerator tạo đồng thời private key và public key
C. MessageDigest sinh public key từ digest của password
D. Mac.getInstance sinh KeyPair từ khóa HMAC hiện tại
Đáp án đúng: A

Câu 29. Trong mã hóa RSA bằng public key của người nhận, khóa nào thường dùng để giải?
A. Public key của bất kỳ CA nào đã ký chứng chỉ
B. Private key tương ứng do người nhận kiểm soát
C. Private key của người gửi gắn với certificate TLS
D. Symmetric AES key lấy từ một digest SHA-256
Đáp án đúng: B

Câu 30. Chữ ký số thường mang lại đặc tính nào khi xác minh bằng public key?
A. Đảm bảo giữ bí mật plaintext khi người khác xem dữ liệu
B. Tự bảo đảm người ký được mọi tổ chức tin cậy
C. Chữ ký xác minh toàn vẹn và quyền giữ private key ký
D. Thay thế hoàn toàn chứng chỉ và quy trình trust validation
Đáp án đúng: C

Câu 31. Trong JCA, thao tác nào khởi tạo Signature để ký thông điệp?
A. signature.initVerify(privateKey) trước update và sign
B. signature.initSign(publicKey) trước verify và sign
C. signature.update(publicKey) trước khi gọi verify
D. signature.initSign(privateKey) trước update và sign
Đáp án đúng: D

Câu 32. Để xác minh chữ ký trên bytes thông điệp, luồng API nào phù hợp?
A. initVerify(publicKey), update(data), verify(signatureBytes)
B. initSign(publicKey), update(data), rồi sign() so sánh kết quả
C. MessageDigest.isEqual(key, signatureBytes) để xác thực RSA
D. Cipher.init(ENCRYPT_MODE, publicKey) rồi doFinal(signature)
Đáp án đúng: A

Câu 33. Với chữ ký RSA-PSS trong Java, cách tiếp cận nào phù hợp?
A. Dùng Signature RSASSA-PSS với tham số PSS nhất quán
B. Dùng Cipher AES/GCM để xác minh trực tiếp chữ ký RSA
C. Dùng Mac HmacSHA256 với public key RSA của certificate
D. Dùng MessageDigest SHA-256 để tự kiểm tra RSA padding
Đáp án đúng: A

Câu 34. Vì sao chỉ gửi SHA-256 digest cùng file không chứng minh người gửi đáng tin?
A. Digest SHA-256 luôn chứa private key của chủ sở hữu file
B. Đối thủ có thể sửa cả file lẫn digest nếu không có xác thực
C. Digest chỉ chính xác nếu chạy trong TLS client có keystore
D. Digest SHA-256 bắt buộc cần salt bí mật lưu trên server
Đáp án đúng: B

Câu 35. Trong ECDH KeyAgreement, kết quả chia sẻ nên được dùng như thế nào?
A. Gửi private key qua mạng để bên kia tính shared secret
B. Dùng trực tiếp shared secret làm X.509 certificate mới
C. Dùng KeyAgreement như Signature để ký mọi HTTP request
D. ECDH tính shared secret, sau đó dẫn xuất key bằng KDF
Đáp án đúng: D

Câu 36. KeyStore.getInstance("PKCS12") chủ yếu tạo engine để quản lý gì?
A. Nguồn random bytes có trạng thái từ entropy phần cứng
B. Quản lý key và chứng chỉ trong keystore PKCS#12
C. Cipher dùng AES-256 để giải mọi message PKCS#12
D. Bộ xử lý JAAS callback cho người dùng đăng nhập
Đáp án đúng: B

Câu 37. Trước khi truy cập entry của KeyStore lấy từ file, cần thao tác nào?
A. Gọi load với stream và mật khẩu bảo vệ phù hợp
B. Gọi doFinal để giải các alias trên keystore
C. Gọi SSLContext.init để nạp từng alias file
D. Gọi Signature.verify để parse metadata của kho
Đáp án đúng: A

Câu 38. Một KeyStore.PrivateKeyEntry thường chứa thành phần nào?
A. Chỉ certificate CA tin cậy, không có private key
B. Chỉ password char[] dùng làm seed cho SecureRandom
C. PrivateKey và certificate chain tương ứng
D. Public key và session cookie của TLS peer
Đáp án đúng: C

Câu 39. Một KeyStore.TrustedCertificateEntry thích hợp để lưu gì?
A. Một private key được giữ bởi server và chain
B. Nonce AES-GCM kèm authentication tag của message
C. Chứng chỉ được tin cậy mà không kèm private key
D. Password hash PBKDF2 của toàn bộ user trong JAAS
Đáp án đúng: C

Câu 40. Java CertificateFactory.getInstance("X.509") dùng vào mục đích nào?
A. Parse chứng chỉ X.509 từ dữ liệu được mã hóa
B. Sinh RSA private key trực tiếp từ subject name
C. Tạo chứng chỉ mới đã ký bằng CA mà không có key
D. Xác minh private key khớp certificate bằng JFR
Đáp án đúng: A

Câu 41. Trong JSSE, truststore thường có vai trò nào đối với TLS client?
A. Chứa symmetric session keys đã thương lượng cho mọi host
B. Chứa HTTP proxy credential để giải DNS hostname
C. Chứa Cipher instance dùng để mã hóa plaintext của app
D. Cấp trust anchors để đánh giá certificate chain của peer
Đáp án đúng: D

Câu 42. Trong TLS Java, khác biệt giữa KeyManager và TrustManager là gì?
A. KeyManager giải DNS; TrustManager đặt Socket read timeout
B. KeyManager chọn danh tính; TrustManager xác minh peer
C. KeyManager mã hóa record; TrustManager phân bổ Java heap
D. KeyManager chỉ lưu public key; TrustManager sinh cặp RSA
Đáp án đúng: B

Câu 43. Để cấu hình JSSE SSLContext với danh tính và chính sách tin cậy, dùng gì?
A. sslContext.init(privateKey, certificate, certificateAuthority)
B. sslContext.init(keyStore, trustStore, SSLEngine)
C. sslContext.init(keyManagers, trustManagers, secureRandom)
D. sslContext.init(Cipher, Signature, MessageDigest)
Đáp án đúng: C

Câu 44. Với SSLSocket client dùng TLS thuần, để kiểm tra hostname đúng cách cần gì?
A. Bật endpoint identification phù hợp trong SSLParameters
B. Chỉ kiểm tra chain chứng chỉ; hostname tự luôn được đối chiếu
C. Chỉ đọc CN rồi bỏ qua SAN trên chứng chỉ của server
D. Tự tắt trust manager nếu certificate có cùng DNS hostname
Đáp án đúng: A

Câu 45. Với mutual TLS, điều kiện nào thêm so với TLS xác thực server thông thường?
A. Client chỉ gửi một SHA-256 digest thay cho certificate
B. Client gửi chứng chỉ và ký để chứng minh sở hữu private key
C. Server bỏ certificate của mình nếu client đã tin DNS
D. Hai bên chỉ cần dùng cùng AES key cố định trong file JAR
Đáp án đúng: B

Câu 46. Khi TLS handshake gặp certificate của peer hết hạn hoặc không tin cậy, xử lý nào đúng?
A. Bỏ kiểm tra chain để tiếp tục dùng TLS encryption
B. Đổi sang HTTP plaintext để tự tránh lỗi bắt tay
C. Thay verify bằng so sánh tên server trong URL
D. Từ chối kết nối và sửa chính sách/chứng chỉ tin cậy
Đáp án đúng: D

Câu 47. Với JAAS, LoginContext.login() thường hướng đến kết quả nào?
A. Tạo phiên TLS mới có server certificate mặc định
B. Tạo Cipher AES-GCM từ thông tin credential user
C. LoginModule xác thực rồi xây dựng Subject của người dùng
D. Tự mã hóa password bằng SHA-256 trong mọi callback
Đáp án đúng: C

Câu 48. Trong JAAS, CallbackHandler thường được dùng cho công việc nào?
A. Sinh public key từ X.509 certificate sau khi parse
B. Xác minh TLS hostname khi dùng SSLEngine wrap/unwrap
C. Cấp dữ liệu xác thực cho callback từ LoginModule
D. Đăng ký Provider của JCA khi khởi tạo MessageDigest
Đáp án đúng: C
