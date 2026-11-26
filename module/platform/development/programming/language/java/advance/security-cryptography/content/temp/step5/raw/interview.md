Bạn giải thích mục đích của Java Cryptography Architecture (JCA) và Java Cryptography Extension (JCE) trong nền tảng Java như thế nào?
Bạn phân biệt API mật mã chuẩn của Java với implementation do security provider cung cấp theo cơ chế nào?
Bạn mô tả vai trò của java.security.Security trong việc đăng ký và truy vấn các security providers như thế nào?
Bạn sẽ dùng Security.getProviders để kiểm tra những provider đang khả dụng trong một JVM ra sao?
Bạn phân biệt Provider, Service và thuật toán được đăng ký trong JCA theo quan hệ nào?
Bạn sẽ xác định vì sao cùng một tên thuật toán nhưng implementation khác nhau giữa hai JVM hoặc providers ra sao?
Bạn mô tả cách Cipher.getInstance hoặc MessageDigest.getInstance tìm implementation từ các providers như thế nào?
Bạn phân biệt yêu cầu thuật toán bằng tên chung với chỉ định provider tường minh về tính di động và kiểm soát ra sao?
Bạn sẽ xác định rủi ro thay đổi thứ tự providers làm ứng dụng nhận implementation mật mã ngoài dự kiến như thế nào?
Bạn phân tích vì sao provider được thêm vào runtime phải được coi là executable code có quyền chạy trong JVM ra sao?
Bạn sẽ kiểm tra cấu hình provider và tên thuật toán khi nhận NoSuchAlgorithmException như thế nào?
Bạn phân biệt NoSuchProviderException với NoSuchAlgorithmException trong quá trình tạo đối tượng mật mã ra sao?
Bạn sẽ xác minh hỗ trợ thuật toán và key sizes của runtime thay vì giả định mọi JDK đều có cùng capabilities như thế nào?
Bạn mô tả java.security.Provider giúp khám phá các loại dịch vụ như Signature, KeyPairGenerator và KeyAgreement ra sao?
Bạn phân biệt Cipher, MessageDigest, Mac và Signature theo tính chất bảo mật và loại dữ liệu đầu ra nào?
Bạn sẽ lựa chọn công cụ mật mã khi yêu cầu chỉ kiểm toàn vẹn, giữ bí mật hoặc xác minh nguồn gốc theo tiêu chí nào?
Bạn phân tích vì sao dùng mã hóa dữ liệu không đồng nghĩa đã có xác thực người gửi hoặc phân quyền truy cập ra sao?
Bạn sẽ xác định cách Java Security API phân biệt key material, algorithm parameters và transformation strings ra sao?
Bạn mô tả SecretKey, PublicKey và PrivateKey thuộc các vai trò mật mã khác nhau như thế nào?
Bạn phân biệt KeySpec với Key trong JCA theo mục đích biểu diễn và chuyển đổi khóa ra sao?
Bạn sẽ sử dụng KeyFactory để tái tạo public/private key từ một KeySpec hợp lệ như thế nào?
Bạn phân biệt SecretKeyFactory với KeyFactory khi xử lý khóa đối xứng hoặc khóa bất đối xứng ra sao?
Bạn phân tích nguy cơ lưu SecretKeySpec từ dữ liệu không đủ entropy rồi tin rằng khóa đã an toàn ra sao?
Bạn sẽ xác định trường hợp nào cần dùng AlgorithmParameters thay vì hardcode tham số thuật toán theo thói quen như thế nào?
Bạn mô tả cách java.security.spec hỗ trợ mô tả tham số và định dạng khóa cho các algorithm implementations ra sao?
Bạn phân biệt chuẩn mã hóa khóa X.509 SubjectPublicKeyInfo với PKCS#8 cho private keys như thế nào?
Bạn sẽ đánh giá rủi ro dựa vào Sun internal APIs thay vì JCA public APIs khi nâng cấp JDK ra sao?
Bạn phân tích vì sao provider-specific configuration có thể làm Java application khó triển khai sang runtime khác như thế nào?
Bạn sẽ xây dựng kiểm tra startup để phát hiện cipher, signature hoặc provider thiếu hỗ trợ trước khi phục vụ request ra sao?
Bạn sẽ thiết kế lớp cryptographic service cô lập JCA provider selection khỏi business code theo cách nào?
Bạn phân biệt lỗi cấu hình mật mã ở startup với dữ liệu mã hóa không hợp lệ ở một request đang chạy như thế nào?
Bạn giải thích nguồn số ngẫu nhiên có thể đoán được gây hại thế nào cho khóa, nonce và token bảo mật?
Bạn phân biệt java.util.Random, ThreadLocalRandom và SecureRandom về mục tiêu sử dụng như thế nào?
Bạn sẽ dùng SecureRandom để sinh cryptographic key material hoặc session token theo quy trình nào?
Bạn mô tả SecureRandom.nextBytes được dùng để tạo bytes ngẫu nhiên cho salt hoặc nonce như thế nào?
Bạn sẽ đánh giá khi nào SecureRandom.getInstanceStrong phù hợp và ảnh hưởng của provider hoặc blocking như thế nào?
Bạn phân biệt cryptographically secure pseudorandom generator với entropy source trên hệ điều hành ra sao?
Bạn sẽ xác định vì sao cố định seed của SecureRandom trong production có thể làm suy yếu độ khó dự đoán như thế nào?
Bạn phân tích khi nào việc dùng seed tái lập cho unit test không được phép lan sang production ra sao?
Bạn sẽ cân nhắc thread-safety và hiệu năng khi nhiều threads cùng sử dụng một SecureRandom theo cách nào?
Bạn mô tả vai trò của DRBG và cách kiểm tra thuật toán SecureRandom có thực sự được provider hỗ trợ như thế nào?
Bạn sẽ tính nhu cầu số byte entropy khi tạo token có mức bảo mật mục tiêu cụ thể như thế nào?
Bạn phân biệt nguồn random cho mã định danh không nhạy cảm với nguồn random cho mật mã theo yêu cầu nào?
Bạn sẽ sử dụng KeyGenerator để tạo khóa AES có độ dài đúng với chính sách ứng dụng ra sao?
Bạn phân biệt việc sinh khóa bằng KeyGenerator với tự cắt chuỗi password thành AES key như thế nào?
Bạn sẽ xác định khi nào cần cấp phát entropy ở backend thay vì nhận key bytes do client tự đề xuất như thế nào?
Bạn phân tích nguy cơ lặp lại nonce hoặc IV khi nhiều instances cùng sử dụng bộ đếm không được phối hợp ra sao?
Bạn sẽ đánh giá cách phát hiện entropy hoặc DRBG setup failure khi khởi động môi trường container tối giản như thế nào?
Bạn sẽ tổ chức tests chứng minh token generation đủ length và không cố tình suy luận tính ngẫu nhiên chỉ từ vài mẫu ra sao?
Bạn giải thích hash function mật mã biến đổi input có độ dài bất kỳ thành digest cố định như thế nào?
Bạn phân biệt collision resistance và preimage resistance theo loại rủi ro ứng dụng ra sao?
Bạn sẽ sử dụng MessageDigest.getInstance với SHA-256 để tính digest của dữ liệu theo cách nào?
Bạn mô tả MessageDigest.update và digest hỗ trợ hash dữ liệu streaming thay vì nạp toàn bộ file ra sao?
Bạn phân tích vì sao MD5 và SHA-1 không phù hợp cho mục đích cần collision resistance mạnh như thế nào?
Bạn phân biệt checksum như CRC32 với cryptographic hash trong kiểm tra toàn vẹn chống sửa đổi ác ý ra sao?
Bạn sẽ xác định lý do chỉ gửi hash cạnh dữ liệu không đủ bảo đảm authenticity nếu attacker có thể thay cả hai ra sao?
Bạn phân biệt dùng hash để nhận diện nội dung với password hashing có salt và work factor như thế nào?
Bạn sẽ cân nhắc cách so sánh hash bí mật để hạn chế timing side channels khi cần quyết định truy cập ra sao?
Bạn phân tích vì sao chuyển bytes thành hex hoặc Base64 không làm dữ liệu trở thành encrypted hay secure ra sao?
Bạn sẽ kiểm tra digest output length và algorithm identifier khi giao tiếp với hệ thống ngoài như thế nào?
Bạn sẽ thiết kế migration khỏi hash algorithm cũ mà vẫn xác minh được dữ liệu lịch sử theo hợp đồng nào?
Bạn giải thích Message Authentication Code (MAC) cung cấp loại bảo đảm nào khi hai bên chia sẻ secret key?
Bạn phân biệt MAC với hash không khóa về khả năng phát hiện sửa đổi ác ý như thế nào?
Bạn sẽ sử dụng javax.crypto.Mac và SecretKeySpec để tính HMAC-SHA256 theo dữ liệu nhập ra sao?
Bạn mô tả Mac.init, update và doFinal tham gia tính HMAC trên dữ liệu lớn như thế nào?
Bạn phân biệt HMAC-SHA256 với AES-CMAC theo cấu trúc thuật toán và khả năng provider hỗ trợ ra sao?
Bạn sẽ chọn cách chuẩn hóa bytes được ký MAC trong một HTTP request để tránh hai cách biểu diễn tương đương như thế nào?
Bạn phân tích nguy cơ kiểm HMAC bằng String.equals thông thường đối với dữ liệu nhạy cảm như thế nào?
Bạn sẽ sử dụng MessageDigest.isEqual khi so sánh MAC hoặc digest với hiểu biết về giới hạn chống timing attack nào?
Bạn phân biệt secret dành cho HMAC với key dành cho AES encryption trong thiết kế phân tách mục đích sử dụng ra sao?
Bạn sẽ tổ chức key rotation cho HMAC khi client và server có giai đoạn chuyển tiếp giữa key versions như thế nào?
Bạn phân tích vì sao replay protection không tự có chỉ nhờ một HMAC hợp lệ trên request cũ ra sao?
Bạn sẽ thiết kế timestamp, nonce và replay cache cùng HMAC để hạn chế phát lại request như thế nào?
Bạn phân biệt HMAC integrity với digital signature có khóa công khai về khả năng xác minh giữa nhiều tổ chức ra sao?
Bạn sẽ tránh log shared MAC secrets hoặc raw signed payloads chứa PII theo những quy tắc nào?
Bạn giải thích vì sao lưu password bằng một vòng SHA-256 không thay thế password hashing chuyên dụng như thế nào?
Bạn phân biệt password salt với secret pepper và nguyên tắc lưu trữ chúng ra sao?
Bạn sẽ sử dụng PBEKeySpec và SecretKeyFactory với PBKDF2WithHmacSHA256 để dẫn xuất khóa từ password như thế nào?
Bạn mô tả iteration count của PBKDF2 ảnh hưởng chi phí thử đoán password và latency xác minh ra sao?
Bạn phân biệt PBKDF2, scrypt và Argon2 theo khả năng chống tấn công phần cứng và sự hiện diện trong Java providers ra sao?
Bạn sẽ xác minh thuật toán password KDF mà một JDK/provider hỗ trợ trước khi lựa chọn implementation như thế nào?
Bạn sẽ thiết kế password hash record chứa algorithm, salt, work factor và derived bytes theo cấu trúc nào?
Bạn phân tích vì sao dùng cùng salt cho mọi user làm giảm hiệu quả bảo vệ password database ra sao?
Bạn sẽ nâng work factor cho các tài khoản cũ theo hình thức rehash khi đăng nhập thành công như thế nào?
Bạn phân biệt dẫn xuất encryption key từ password với lưu password verifier trong hệ thống xác thực như thế nào?
Bạn sẽ xử lý char[] password và xóa buffer tạm thời khi API hỗ trợ mà vẫn nhận thức giới hạn của Java GC ra sao?
Bạn phân tích vì sao chuyển password thành String có thể kéo dài thời gian dữ liệu nhạy cảm còn trong heap ra sao?
Bạn sẽ dùng PBEKeySpec.clearPassword để giảm thời gian dữ liệu mật khẩu tồn tại trong object ra sao?
Bạn sẽ thiết kế giới hạn rate và lockout để bổ sung bảo vệ password verification thay vì chỉ dựa vào thuật toán KDF như thế nào?
Bạn giải thích mục tiêu của symmetric encryption và điều kiện giữ bí mật khóa giữa các bên như thế nào?
Bạn phân biệt block cipher AES với block mode như GCM hoặc CBC khi dùng Cipher trong Java ra sao?
Bạn sẽ sử dụng Cipher.getInstance("AES/GCM/NoPadding") để xây authenticated encryption theo thứ tự nào?
Bạn mô tả GCMParameterSpec chứa authentication tag length và IV khi init Cipher như thế nào?
Bạn phân biệt nonce của AES-GCM với secret key và lý do nonce không cần giữ bí mật ra sao?
Bạn phân tích vì sao tái sử dụng cùng nonce với cùng AES-GCM key có thể gây hỏng confidentiality và integrity ra sao?
Bạn sẽ thiết kế quy tắc tạo nonce không trùng giữa các tiến trình, shards hoặc lần khởi động theo yêu cầu nào?
Bạn phân biệt random nonce và counter-based nonce trong GCM về cách kiểm soát uniqueness ra sao?
Bạn sẽ chọn GCM tag length và nonce policy dựa trên yêu cầu giao thức cùng khả năng tương thích nào?
Bạn mô tả Cipher.updateAAD thêm associated data vào phép xác thực AEAD mà không mã hóa associated data như thế nào?
Bạn sẽ quyết định dùng AAD để ràng buộc tenantId hoặc recordId với ciphertext theo chính sách nào?
Bạn phân tích vì sao sửa AAD hoặc ciphertext sẽ khiến xác thực AES-GCM thất bại khi decrypt ra sao?
Bạn sẽ xử lý AEADBadTagException sao cho không trả lỗi xác thực chi tiết tạo oracle cho kẻ tấn công như thế nào?
Bạn phân biệt encryption error do sai key, sai nonce, sai AAD và dữ liệu bị sửa theo khả năng chẩn đoán an toàn nào?
Bạn sẽ thiết kế định dạng envelope lưu algorithm version, key identifier, nonce, ciphertext và tag như thế nào?
Bạn phân tích vì sao không được lấy nonce GCM từ timestamp đơn giản khi có nhiều requests đồng thời ra sao?
Bạn sẽ phân biệt AES-ECB với AES-GCM theo khả năng lộ cấu trúc plaintext và bảo vệ toàn vẹn như thế nào?
Bạn phân tích nguy cơ dùng AES/CBC/PKCS5Padding mà không có MAC và để lộ padding errors ra sao?
Bạn sẽ thiết kế encrypt-then-MAC cho giao thức legacy CBC nếu chưa thể chuyển sang AEAD theo quy tắc nào?
Bạn phân biệt IV của AES-CBC với nonce của AES-GCM về yêu cầu không đoán được hoặc không trùng ra sao?
Bạn sẽ dùng IvParameterSpec trong một giao thức legacy có IV theo chuẩn và tránh áp dụng nó sai cho GCM như thế nào?
Bạn mô tả Cipher.init, update và doFinal ảnh hưởng thứ tự xử lý streaming encryption ra sao?
Bạn sẽ xác định vì sao Cipher instance không nên chia sẻ tùy tiện giữa các threads hoặc các yêu cầu độc lập như thế nào?
Bạn sẽ quản lý CipherInputStream và CipherOutputStream theo yêu cầu xử lý ngoại lệ xác thực trước khi tin plaintext ra sao?
Bạn phân tích nguy cơ xử lý một phần plaintext AEAD như dữ liệu đáng tin cậy trước khi authentication tag được kiểm tra ra sao?
Bạn sẽ dùng KeyGenerator và SecretKey để tránh hardcode AES keys trong source code như thế nào?
Bạn sẽ quyết định thời điểm xoay AES key và lưu key version để giải mã được dữ liệu cũ như thế nào?
Bạn phân tích vì sao encryption-at-rest không tự bảo vệ dữ liệu nếu khóa được lưu ngay cạnh ciphertext trong cùng quyền truy cập ra sao?
Bạn sẽ phân biệt key encryption key với data encryption key trong mô hình envelope encryption ra sao?
Bạn sẽ thiết kế xác thực nội dung tệp mã hóa lớn với AEAD hoặc chia chunks có xác thực riêng theo giới hạn nào?
Bạn phân tích rủi ro dùng một key/nonce pair chung cho nhiều chunks khi mã hóa streaming lớn ra sao?
Bạn sẽ kiểm thử GCM decrypt với ciphertext bị đổi byte, AAD sai và tag sai để xác minh fail-closed như thế nào?
Bạn sẽ xử lý trường hợp application khôi phục từ backup nhưng bộ đếm nonce quay lại giá trị cũ theo chiến lược nào?
Bạn giải thích asymmetric cryptography dùng cặp public/private key cho những tác vụ nào trong hệ thống Java?
Bạn phân biệt RSA encryption với RSA digital signature về vai trò khóa và thuật toán ra sao?
Bạn sẽ dùng KeyPairGenerator để tạo RSA key pair với thông số phù hợp chính sách bảo mật như thế nào?
Bạn mô tả KeyFactory tạo PublicKey từ X509EncodedKeySpec và PrivateKey từ PKCS8EncodedKeySpec như thế nào?
Bạn sẽ phân biệt public key có thể phân phối công khai với private key phải được bảo vệ khi lưu trữ như thế nào?
Bạn phân tích vì sao không nên dùng RSA/ECB/PKCS1Padding cho encryption mới khi có OAEP phù hợp như thế nào?
Bạn sẽ sử dụng Cipher với RSA/ECB/OAEPWithSHA-256AndMGF1Padding theo kiểm tra tham số OAEP nào?
Bạn mô tả OAEPParameterSpec giúp cấu hình digest, MGF và các tham số OAEP khi cần interoperability như thế nào?
Bạn sẽ xác định kích thước plaintext tối đa có thể mã hóa trực tiếp bằng RSA-OAEP theo kích thước modulus và hash ra sao?
Bạn phân tích vì sao RSA không phù hợp để mã hóa một file lớn trực tiếp thay vì dùng hybrid encryption như thế nào?
Bạn sẽ thiết kế hybrid encryption dùng AES data key được bảo vệ bởi public-key mechanism theo quy trình nào?
Bạn phân biệt RSA key transport với Diffie-Hellman key agreement về cách hình thành shared secret ra sao?
Bạn sẽ sử dụng KeyAgreement cho ECDH với private key của mình và public key của peer như thế nào?
Bạn phân tích vì sao raw ECDH shared secret cần được xử lý qua KDF trước khi sử dụng làm symmetric key ra sao?
Bạn sẽ xác định provider và API phù hợp khi dùng X25519 hoặc các thuật toán key agreement hiện đại ra sao?
Bạn phân biệt static ECDH và ephemeral ECDH về forward secrecy theo điều kiện nào?
Bạn sẽ kiểm tra public key do peer cung cấp có đúng type/parameters và được xác thực theo protocol như thế nào?
Bạn phân tích nguy cơ man-in-the-middle khi dùng ECDH nhưng không xác thực danh tính và public keys ra sao?
Bạn sẽ mô tả ECGenParameterSpec cho phép chọn named elliptic curve khi sinh EC key pair như thế nào?
Bạn phân biệt Curve25519 dành cho key agreement với Ed25519 dành cho chữ ký số như thế nào?
Bạn sẽ xác định lý do cùng một tên EC curve không bảo đảm các provider đều hỗ trợ cùng thuật toán như thế nào?
Bạn phân tích vì sao private key bytes không nên được gửi qua logging hay exception messages của crypto helper ra sao?
Bạn sẽ thiết kế key identifier không tiết lộ secret nhưng đủ để chọn private key khi decrypt nhiều key versions như thế nào?
Bạn phân biệt tạo private key mới với import private key từ PKCS#8 theo mục tiêu vận hành nào?
Bạn sẽ xác định cách lưu khóa bất đối xứng trong hardware-backed provider hoặc HSM thay vì xuất raw private key như thế nào?
Bạn phân tích vì sao một PrivateKey.getEncoded trả null có thể là hành vi hợp lệ của khóa không thể xuất từ phần cứng ra sao?
Bạn sẽ kiểm thử key agreement cho hai peers sinh ra cùng shared secret nhưng không làm lộ secret trong logs như thế nào?
Bạn giải thích digital signature cung cấp kiểm tra integrity và chứng minh sở hữu private key trong mô hình nào?
Bạn phân biệt chữ ký số với HMAC khi nhiều bên độc lập cần xác minh mà không chia sẻ secret key ra sao?
Bạn sẽ sử dụng Signature.getInstance và Signature.initSign để ký dữ liệu bằng private key như thế nào?
Bạn mô tả Signature.update và sign cho phép ký dữ liệu streaming theo quy trình nào?
Bạn sẽ dùng Signature.initVerify với public key để xác minh chữ ký trên dữ liệu đã nhận ra sao?
Bạn phân biệt SHA256withRSA với RSASSA-PSS về lược đồ chữ ký và tham số thuật toán như thế nào?
Bạn sẽ dùng PSSParameterSpec để đồng bộ digest, MGF và salt length giữa bên ký và bên xác minh theo cách nào?
Bạn phân tích vì sao chữ ký RSASSA-PSS có thể không xác minh được nếu hai bên dùng tham số PSS khác nhau ra sao?
Bạn sẽ lựa chọn ECDSA hoặc Ed25519 theo khả năng hỗ trợ provider và định dạng chữ ký cần trao đổi như thế nào?
Bạn phân biệt ECDSA signature encoding ASN.1 DER với định dạng r và s nối thẳng do một giao thức quy định như thế nào?
Bạn sẽ xác định cần chuẩn hóa payload trước khi ký JSON/XML để tránh hai phía ký các byte sequences khác nhau ra sao?
Bạn phân tích vì sao ký dữ liệu đã deserialize rồi serialize lại có thể cho signature mismatch dù nội dung nghiệp vụ giống nhau ra sao?
Bạn sẽ thiết kế ký một gói dữ liệu có timestamp, audience và request identifier để hạn chế replay theo cách nào?
Bạn phân biệt signature verification thành công với kiểm tra certificate chain hoặc identity owner của public key ra sao?
Bạn sẽ xác định vì sao dùng public key từ chính request chưa xác thực có thể làm phép xác minh chữ ký vô nghĩa ra sao?
Bạn phân tích nguy cơ dùng cùng một cặp khóa cho encryption và signing khi hai mục tiêu có vòng đời hoặc policy khác nhau ra sao?
Bạn sẽ lưu signature algorithm identifier và key ID ở định dạng message như thế nào để hỗ trợ key rotation?
Bạn sẽ xử lý InvalidKeyException và SignatureException mà không tiết lộ thông tin nhạy cảm cho bên gửi ra sao?
Bạn sẽ xây dựng test ký rồi xác minh, sửa message, đổi public key và thay signature bytes để kiểm tra negative cases như thế nào?
Bạn phân tích rủi ro chỉ test signature happy path mà không kiểm tra nguyên tắc tin cậy của khóa công khai ra sao?
Bạn sẽ đánh giá khi nào cần timestamping service hoặc audit record để chứng minh thời điểm ký trong quy trình dài hạn như thế nào?
Bạn sẽ xác định chữ ký của JAR artifact qua jarsigner hỗ trợ mục tiêu kiểm tra nguồn gốc như thế nào?
Bạn phân biệt chữ ký artifact khi phân phối phần mềm với TLS certificate của service đang phục vụ ra sao?
Bạn sẽ lập kế hoạch rotation signing private key nhưng vẫn có khả năng xác minh chữ ký lịch sử như thế nào?
Bạn giải thích KeyStore API của Java dùng quản lý những dạng key entries và certificates nào?
Bạn phân biệt KeyStore.PrivateKeyEntry, SecretKeyEntry và TrustedCertificateEntry theo loại dữ liệu lưu trữ như thế nào?
Bạn sẽ lựa chọn loại KeyStore PKCS12 thay vì JKS cho ứng dụng mới dựa trên tính tương thích nào?
Bạn mô tả KeyStore.load lấy dữ liệu từ stream hoặc provider-specific store theo cấu hình ra sao?
Bạn phân biệt keystore password với key entry password theo mức bảo vệ và những hỗ trợ của provider như thế nào?
Bạn sẽ sử dụng KeyStore.getKey, getCertificate và aliases để lựa chọn đúng key entry theo mục đích nào?
Bạn phân tích vì sao lưu private key vào file KeyStore nhưng hardcode password trong ứng dụng vẫn là nguy cơ lớn ra sao?
Bạn sẽ tổ chức việc cung cấp passwords qua secret manager hoặc environment theo quy trình vận hành nào?
Bạn sẽ lựa chọn KeyStore provider backed by HSM hoặc PKCS11 khi private key không được phép xuất khỏi thiết bị ra sao?
Bạn phân biệt javax.crypto.SecretKey với PrivateKey khi lưu vào KeyStore và cách provider hỗ trợ như thế nào?
Bạn sẽ dùng keytool để kiểm tra aliases, certificate validity và fingerprints mà không xuất private key ra sao?
Bạn mô tả X509Certificate chứa subject, issuer, validity period và public key như thế nào?
Bạn phân biệt self-signed certificate với end-entity certificate được chứng thực bởi CA tin cậy ra sao?
Bạn sẽ xác định certificate chain từ leaf qua intermediate CA đến trust anchor theo cách nào?
Bạn giải thích TrustManagerFactory dùng truststore hỗ trợ kiểm tra certificate chain như thế nào?
Bạn phân biệt kiểm tra chứng chỉ được ký hợp lệ với việc chứng chỉ được tin cậy bởi một trust anchor ra sao?
Bạn sẽ dùng CertPathValidator và PKIXParameters để kiểm tra certificate path theo policy như thế nào?
Bạn mô tả CertificateFactory tạo đối tượng X.509 certificate từ bytes hoặc stream theo cách nào?
Bạn sẽ xác định vì sao kiểm tra thời hạn X.509 certificate chỉ là một bước trong PKIX validation ra sao?
Bạn phân tích tác động của Basic Constraints, Key Usage và Extended Key Usage tới mục đích TLS server/client authentication ra sao?
Bạn sẽ kiểm tra Subject Alternative Name (SAN) trong xác minh hostname của HTTPS server như thế nào?
Bạn phân biệt certificate subject display name với SAN phục vụ kiểm tra tên máy chủ theo chính sách nào?
Bạn sẽ giải thích certificate revocation bằng CRL và OCSP có các giới hạn về tính sẵn sàng và độ mới ra sao?
Bạn sẽ lựa chọn revocation checking policy khi OCSP responder không khả dụng dựa trên rủi ro nào?
Bạn phân tích vì sao gọi remote OCSP/CRL mỗi request có thể gây latency và availability problems ra sao?
Bạn sẽ kiểm tra certificate renewal khi CA thay intermediate certificate hoặc chain order theo cách nào?
Bạn sẽ tổ chức rotation key/certificate đồng thời trên nhiều replicas mà không làm client mất khả năng xác minh ra sao?
Bạn phân tích vì sao import một root CA không tin cậy vào truststore của application làm mở rộng toàn bộ trust boundary ra sao?
Bạn sẽ thiết kế truststore riêng cho một đối tác thay vì vô hiệu hóa trust checks trên JVM như thế nào?
Bạn sẽ quản lý backup và recovery của KeyStore mà không làm lộ encryption keys hoặc key passwords ra sao?
Bạn sẽ đánh giá compatibility của PKCS12 giữa Java provider và hệ thống bên ngoài khi import/export certificates như thế nào?
Bạn giải thích JSSE cung cấp cơ chế triển khai TLS qua những API nào của Java?
Bạn mô tả SSLContext kết hợp key managers, trust managers và secure random khi tạo kết nối TLS như thế nào?
Bạn sẽ dùng KeyManagerFactory khởi tạo private key và certificate chain cho một TLS server ra sao?
Bạn phân biệt KeyManager với TrustManager về phía nào trình bày certificate và phía nào xác minh nó ra sao?
Bạn sẽ dùng TrustManagerFactory với truststore riêng để xác minh một TLS peer theo điều kiện nào?
Bạn phân tích nguy cơ X509TrustManager bỏ qua mọi lỗi validation để kết nối test thành công ra sao?
Bạn sẽ tạo SSLSocketFactory từ SSLContext và cấu hình TLS socket tới host theo cách nào?
Bạn mô tả SSLServerSocketFactory tạo server socket có TLS và các lựa chọn client authentication như thế nào?
Bạn sẽ yêu cầu mutual TLS (mTLS) bằng SSLParameters hoặc SSLServerSocket policy theo trường hợp nào?
Bạn phân biệt wantClientAuth với needClientAuth khi TLS server yêu cầu client certificate như thế nào?
Bạn sẽ xác định vì sao TLS authentication thành công chưa đủ để client được phép thực hiện business action ra sao?
Bạn mô tả SSLParameters.setEndpointIdentificationAlgorithm("HTTPS") giúp kiểm tra server identity ở những tình huống nào?
Bạn sẽ kiểm tra hostname verification không bị bỏ qua khi dùng SSLSocket thay vì HTTPS client framework như thế nào?
Bạn phân tích nguy cơ tắt hostname verification bằng HostnameVerifier luôn trả true trong production ra sao?
Bạn sẽ xử lý certificate SAN mismatch bằng cách sửa cấu hình endpoint hoặc chứng chỉ thay vì bỏ validation như thế nào?
Bạn sẽ xác định protocol version và cipher suite được bật trên SSLSocket theo security policy nào?
Bạn phân biệt TLS handshake với TCP connect và application request timeout theo giai đoạn thất bại ra sao?
Bạn sẽ chẩn đoán SSLHandshakeException do trust chain sai, key usage không phù hợp hoặc protocol mismatch như thế nào?
Bạn mô tả Server Name Indication (SNI) giúp TLS server chọn certificate theo hostname như thế nào?
Bạn sẽ cấu hình SNIHostName khi một Java client cần kết nối vào TLS virtual host theo cách nào?
Bạn phân biệt ALPN protocol negotiation với TLS cipher suite negotiation khi HTTP/2 hoạt động qua TLS ra sao?
Bạn sẽ xác định cách Java HttpClient dùng SSLContext và SSLParameters mà vẫn duy trì xác minh hostname an toàn như thế nào?
Bạn phân tích vì sao thay SSLContext toàn JVM có thể vô tình ảnh hưởng các kết nối TLS tới nhiều đối tác ra sao?
Bạn sẽ tạo SSLContext riêng theo service để tránh truststore của đối tác A áp dụng sai cho B như thế nào?
Bạn sẽ dùng SSLEngine.wrap và unwrap để triển khai TLS trên SocketChannel nonblocking theo vòng đời nào?
Bạn mô tả trạng thái NEED_WRAP, NEED_UNWRAP và NEED_TASK của SSLEngine trong quá trình handshake như thế nào?
Bạn sẽ xử lý BUFFER_UNDERFLOW và BUFFER_OVERFLOW khi kích thước buffers chưa đủ cho TLS records ra sao?
Bạn phân tích vì sao quên xử lý close_notify có thể gây rủi ro truncation khi đọc stream TLS như thế nào?
Bạn sẽ đặt giới hạn thời gian TLS handshake và số kết nối đồng thời để giảm nguy cơ slow handshake DoS như thế nào?
Bạn sẽ xác định khi nào TLS session resumption giúp giảm latency nhưng vẫn cần chính sách rotation và cache như thế nào?
Bạn phân biệt TLS 1.3 forward secrecy với việc data-at-rest encryption key bị lộ sau này theo phạm vi bảo vệ nào?
Bạn sẽ thiết kế test TLS với certificate hợp lệ, expired certificate và hostname mismatch từ một test server riêng như thế nào?
Bạn sẽ tạo runbook điều tra TLS alert, certificate chain và cipher mismatch mà không ghi session keys ra logs ra sao?
Bạn giải thích JAAS (Java Authentication and Authorization Service) cung cấp mô hình xác thực dựa trên Subject như thế nào?
Bạn phân biệt Subject, Principal và credentials trong Java JAAS theo chức năng nào?
Bạn sẽ dùng LoginContext để yêu cầu một chuỗi LoginModule xác thực user trong ứng dụng theo cách nào?
Bạn mô tả giao diện LoginModule và các phương thức initialize, login, commit, abort, logout như thế nào?
Bạn phân biệt giai đoạn login với commit của LoginModule khi có nhiều authentication modules phối hợp ra sao?
Bạn sẽ xác định vai trò của CallbackHandler khi LoginModule cần nhận username, password hoặc thông tin bổ sung như thế nào?
Bạn mô tả NameCallback và PasswordCallback được dùng để lấy input xác thực theo hướng nào?
Bạn sẽ xử lý PasswordCallback.clearPassword để giảm thời gian password nằm trong bộ nhớ theo cách nào?
Bạn phân biệt sharedState giữa nhiều LoginModules với state của Subject sau login thành công ra sao?
Bạn sẽ thiết kế cách sử dụng các JAAS control flags required, requisite, sufficient và optional theo kỳ vọng xác thực nào?
Bạn phân tích nguy cơ đặt module yếu ở trạng thái sufficient khiến một bước xác thực mạnh khác bị bỏ qua ra sao?
Bạn sẽ xác định khi nào custom LoginModule nên trả false hay ném LoginException theo chính sách authentication ra sao?
Bạn mô tả cách gắn Principal vào Subject mà không để anonymous user tự tạo quyền cao hơn ra sao?
Bạn phân biệt Principal thể hiện danh tính với GrantedAuthority trong Spring Security theo mô hình authorization nào?
Bạn sẽ tích hợp JAAS LoginModule với Spring Security mà không đồng nhất credential verification với authorization policy như thế nào?
Bạn phân tích vì sao Subject chỉ mang credentials không đồng nghĩa những dữ liệu đó được bảo vệ khỏi code tin cậy sai phạm ra sao?
Bạn sẽ xác định API thực thi tác vụ trong ngữ cảnh Subject nào còn phù hợp ở phiên bản JDK mục tiêu như thế nào?
Bạn phân biệt JAAS authentication với vai trò lịch sử của SecurityManager theo giới hạn an toàn trong Java hiện đại ra sao?
Bạn sẽ kiểm tra thay đổi hoặc deprecation của Java security authorization APIs khi nâng JDK theo tài liệu phiên bản như thế nào?
Bạn sẽ thiết kế logout JAAS để làm sạch principals và credentials thuộc vòng xác thực đã kết thúc ra sao?
Bạn sẽ kiểm thử một LoginContext với nhiều LoginModules khi một module thành công và module khác thất bại như thế nào?
Bạn sẽ bảo vệ cấu hình JAAS khỏi bị sửa đổi bởi người dùng không tin cậy để tránh nạp LoginModule lạ ra sao?
Bạn sẽ xác định sự khác nhau giữa xác thực hệ điều hành bằng JAAS và xác thực TLS peer theo nguồn danh tính nào?
Bạn phân biệt kiểm thử unit các hàm mã hóa với integration tests sử dụng JCA provider thực theo mục tiêu nào?
Bạn sẽ tạo deterministic test vectors cho SHA-256 và HMAC mà không cố định nguồn ngẫu nhiên production như thế nào?
Bạn sẽ kiểm thử AES-GCM round-trip và kiểm tra giải mã thất bại khi sửa nonce, AAD, ciphertext hoặc tag ra sao?
Bạn sẽ thiết kế test phát hiện cùng nonce bị sử dụng lại trong một tập messages với cùng key như thế nào?
Bạn phân tích vì sao chỉ có happy-path encryption/decryption tests chưa xác nhận dữ liệu đã được authenticate như thế nào?
Bạn sẽ kiểm thử RSA-OAEP với message vượt giới hạn kích thước và key pair sai như thế nào?
Bạn sẽ dùng reference test vectors hoặc cross-provider tests để phát hiện bất tương thích tham số OAEP ra sao?
Bạn sẽ kiểm tra Signature RSASSA-PSS verify thất bại khi digest hoặc salt length không khớp như thế nào?
Bạn sẽ xây dựng interoperability tests trao đổi JWK/PEM/DER keys với một hệ thống khác mà vẫn xác nhận đúng key format ra sao?
Bạn sẽ kiểm thử KeyStore PKCS12 load, private key access và wrong password trong bộ fixtures không chứa production secrets ra sao?
Bạn sẽ dùng keytool hoặc jarsigner trong CI để kiểm tra certificates và ký artifact theo các mục đích nào?
Bạn sẽ mô phỏng certificate expiry, revoked certificate hoặc trust anchor sai trong một TLS integration test ra sao?
Bạn sẽ kiểm thử Java HttpClient không chấp nhận certificate hợp lệ về chain nhưng sai hostname như thế nào?
Bạn sẽ thiết kế JAAS LoginModule tests cho commit, abort, logout và control flags khi kết quả pha trước thay đổi như thế nào?
Bạn sẽ kiểm tra dữ liệu nhạy cảm không xuất hiện trong exception messages, stack traces, debug logs hoặc metrics như thế nào?
Bạn sẽ dùng code review checklist để phát hiện Cipher transformation thiếu mode hoặc IV được hardcode như thế nào?
Bạn phân tích vì sao static analysis phát hiện thuật toán yếu nhưng vẫn cần runtime tests với provider cụ thể như thế nào?
Bạn sẽ kiểm tra hiệu năng của PBKDF2 và AES-GCM dưới tải lớn mà không làm lộ secret test key trong report ra sao?
Bạn sẽ đo entropy generation latency và tác động lên startup khi một ứng dụng tạo nhiều keys như thế nào?
Bạn sẽ quản lý KeyStore và certificate rotation trong pipeline triển khai nhiều replicas theo kế hoạch nào?
Bạn sẽ thiết kế key version migration để mã hóa dữ liệu mới bằng key mới nhưng vẫn đọc được ciphertext cũ như thế nào?
Bạn phân tích nguy cơ cấp quyền decrypt rộng cho mọi microservice khiến blast radius của một service bị xâm nhập tăng ra sao?
Bạn sẽ tổ chức audit events cho key use, signing và failed verifications mà không ghi raw plaintext hoặc private keys ra sao?
Bạn sẽ bảo vệ cached secrets trong heap và cân nhắc giới hạn xóa dữ liệu của garbage-collected runtime như thế nào?
Bạn sẽ áp dụng nguyên tắc crypto agility để thay thế thuật toán cũ mà không thay đổi toàn bộ business data model ra sao?
Bạn sẽ tạo runbook xử lý sự cố mất private key, hết hạn certificate và ciphertext không thể giải mã theo thứ tự nào?
Bạn sẽ xác định điểm khác nhau giữa breach of symmetric key và compromise of signing private key để lập kế hoạch ứng phó ra sao?
Bạn phân tích vì sao thay đổi TrustManager toàn cục khi một kết nối lỗi có thể tạo lỗ hổng cho toàn hệ thống như thế nào?
Bạn sẽ định nghĩa metrics an toàn cho TLS handshake failure, invalid signature và crypto operation latency như thế nào?
Bạn sẽ xây dựng checklist production về algorithm choices, nonce uniqueness, key storage, certificate validation và permissions như thế nào?
Nếu một hệ thống dùng SHA-256 thuần để lưu mật khẩu, bạn sẽ thiết kế chuyển đổi sang password hashing có salt và work factor như thế nào?
Nếu một API trả 200 nhưng HMAC verification không kiểm tra đúng bytes của request, bạn sẽ kiểm tra canonicalization và key selection ra sao?
Nếu hai replicas tạo cùng AES-GCM nonce sau khi restart từ snapshot, bạn sẽ thiết kế lại nonce generation như thế nào?
Nếu decrypt GCM trả AEADBadTagException, bạn sẽ phân biệt dữ liệu không hợp lệ với lỗi triển khai mà không tạo oracle như thế nào?
Nếu Java service đang dùng AES/ECB cho dữ liệu nhiều blocks, bạn sẽ thiết kế migration sang AEAD ra sao?
Nếu đối tác dùng RSA-OAEP với MGF digest khác, bạn sẽ kiểm tra OAEPParameterSpec và interoperability như thế nào?
Nếu Signature.verify thất bại dù cả hai bên dùng RSA-PSS, bạn sẽ kiểm tra hash, MGF và salt length như thế nào?
Nếu ECDH tạo shared secret nhưng chưa xác thực public key của peer, bạn sẽ bổ sung cơ chế xác thực nào?
Nếu private key HSM trả getEncoded bằng null, bạn sẽ thay đổi code quản lý khóa thay vì cố xuất bytes ra sao?
Nếu Java service nạp được KeyStore nhưng không tìm thấy private key alias, bạn sẽ kiểm tra entry type, password và provider như thế nào?
Nếu certificate chain được ký hợp lệ nhưng SAN không khớp hostname, bạn sẽ sửa trust configuration theo chính sách nào?
Nếu OCSP endpoint bị outage khiến nhiều TLS handshakes chậm, bạn sẽ đánh giá revocation policy và availability như thế nào?
Nếu mTLS handshake thành công nhưng một client không có quyền truy cập tenant khác, bạn sẽ xây dựng authorization layer ra sao?
Nếu SSLEngine liên tục báo BUFFER_OVERFLOW, bạn sẽ xác định packet/application buffer sizes và handshake state như thế nào?
Nếu JAAS LoginModule trả success nhưng không commit Principal, bạn sẽ kiểm tra LoginContext lifecycle và module flags như thế nào?
Nếu nâng JDK khiến security provider cũ không còn algorithm hỗ trợ, bạn sẽ kiểm tra providers và regression tests ra sao?
Nếu một security audit phát hiện private key bị đưa vào logs, bạn sẽ xử lý containment, rotation và redaction như thế nào?
Nếu ứng dụng có nhiều API cần hash, MAC, encryption, TLS và signing, bạn sẽ thiết kế JCA/JCE wrappers, key lifecycle, tests và guardrails như thế nào?
