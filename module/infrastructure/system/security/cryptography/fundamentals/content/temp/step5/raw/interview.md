Bạn phân biệt mục tiêu bí mật, toàn vẹn, xác thực nguồn gốc và chống chối bỏ trong thiết kế mật mã như thế nào?
Bạn lựa chọn primitive mật mã dựa trên mô hình đe dọa và yêu cầu bảo vệ dữ liệu ra sao?
Bạn phân biệt mã hóa, hàm băm, MAC và chữ ký số về đầu vào, đầu ra và mục tiêu bảo mật như thế nào?
Bạn giải thích vì sao mã hóa không tự động bảo đảm dữ liệu không bị sửa đổi như thế nào?
Bạn phân biệt mã hóa đối xứng và bất đối xứng về cách phân phối khóa, hiệu năng và mô hình tin cậy ra sao?
Bạn mô tả cách mã hóa lai kết hợp trao đổi hoặc đóng gói khóa bất đối xứng với mã hóa dữ liệu đối xứng như thế nào?
Bạn lựa chọn giữa mã hóa toàn bộ dữ liệu và mã hóa từng trường dựa trên yêu cầu truy cập, tìm kiếm và vận hành nào?
Bạn phân biệt dữ liệu đang truyền, dữ liệu đang lưu và dữ liệu đang được xử lý về nhu cầu bảo vệ mật mã ra sao?
Bạn giải thích vì sao không nên tự thiết kế thuật toán hoặc giao thức mật mã riêng khi đã có chuẩn được kiểm chứng như thế nào?
Bạn đánh giá tính phù hợp của thuật toán dựa trên mức độ an toàn hiện tại, khả năng tương thích và vòng đời hệ thống như thế nào?
Bạn phân biệt key size với security strength và xác định vì sao số bit khóa không thể so sánh trực tiếp giữa mọi thuật toán ra sao?
Bạn giải thích các thuộc tính preimage resistance, second-preimage resistance và collision resistance của hàm băm như thế nào?
Bạn lựa chọn SHA-256 hoặc SHA-3 cho mục đích integrity checking và xác định giới hạn của checksum không có khóa ra sao?
Bạn phân biệt hash mật mã với checksum hoặc hash không mật mã khi phát hiện sửa đổi có chủ đích như thế nào?
Bạn giải thích vì sao MD5 và SHA-1 không còn phù hợp cho các mục đích cần chống va chạm như thế nào?
Bạn đánh giá nguy cơ collision attack và các tình huống thực tế mà collision resistance quan trọng ra sao?
Bạn phân biệt salt, pepper và nonce về mục đích và cách quản lý như thế nào?
Bạn giải thích vai trò của KDF khi dẫn xuất nhiều khóa từ một secret gốc như thế nào?
Bạn phân biệt HKDF với password hashing KDF như Argon2id, scrypt hoặc PBKDF2 về đầu vào và mục tiêu sử dụng ra sao?
Bạn lựa chọn KDF dựa trên entropy nguồn bí mật, yêu cầu tương thích và chi phí tính toán như thế nào?
Bạn giải thích vì sao password hashing cần salt riêng cho từng mật khẩu và chi phí tính toán phù hợp như thế nào?
Bạn mô tả MAC cung cấp tính toàn vẹn và xác thực thông điệp giữa các bên cùng chia sẻ khóa như thế nào?
Bạn phân biệt HMAC với hash thông thường và giải thích vai trò của khóa bí mật trong MAC ra sao?
Bạn lựa chọn HMAC-SHA-256 cho xác thực thông điệp và xác định cách quản lý khóa dùng chung như thế nào?
Bạn phân biệt MAC với chữ ký số về khả năng xác minh của nhiều bên và tính chất chống chối bỏ ra sao?
Bạn giải thích chữ ký số được tạo và xác minh bằng cặp khóa riêng, khóa công khai như thế nào?
Bạn lựa chọn RSA-PSS, ECDSA hoặc EdDSA theo yêu cầu bảo mật, hiệu năng và khả năng tương thích ra sao?
Bạn đánh giá vì sao khóa riêng ký số phải được bảo vệ nghiêm ngặt hơn khóa công khai như thế nào?
Bạn phân biệt chữ ký trên dữ liệu gốc với chữ ký trên digest đã được băm theo chuẩn thuật toán như thế nào?
Bạn xác định cách canonicalize hoặc serialize dữ liệu trước khi ký để hai bên xác minh cùng một nội dung như thế nào?
Bạn giải thích vì sao so sánh MAC hoặc chữ ký cần xử lý an toàn về thời gian và định dạng như thế nào?
Bạn phân biệt mã hóa bằng khóa công khai với ký bằng khóa riêng để tránh nhầm lẫn mục đích của hai thao tác như thế nào?
Bạn mô tả trao đổi khóa Diffie-Hellman và ECDHE tạo ra bí mật chung qua kênh công khai như thế nào?
Bạn giải thích forward secrecy và cách ephemeral key exchange hạn chế ảnh hưởng khi khóa dài hạn bị lộ về sau như thế nào?
Bạn phân biệt key transport với key agreement về cách hình thành khóa phiên ra sao?
Bạn lựa chọn chế độ mã hóa khối phù hợp và giải thích vì sao ECB làm lộ mẫu dữ liệu như thế nào?
Bạn phân biệt CBC, CTR và GCM về yêu cầu IV/nonce, khả năng phát hiện sửa đổi và cách sử dụng an toàn ra sao?
Bạn giải thích authenticated encryption và vai trò của AEAD trong việc kết hợp bí mật với toàn vẹn như thế nào?
Bạn phân biệt AES-GCM với ChaCha20-Poly1305 về primitive, hiệu năng và môi trường triển khai phù hợp ra sao?
Bạn lựa chọn Additional Authenticated Data để xác thực metadata như tenant ID, phiên bản hoặc header mà không mã hóa chúng như thế nào?
Bạn xác định điều gì xảy ra khi ciphertext hoặc AAD bị sửa trong một chế độ AEAD và cách ứng dụng phải xử lý lỗi xác thực ra sao?
Bạn giải thích vì sao không được sử dụng lại nonce với cùng một khóa trong AES-GCM hoặc ChaCha20-Poly1305 như thế nào?
Bạn phân biệt nonce cần duy nhất với IV cần ngẫu nhiên theo yêu cầu cụ thể của từng chế độ mã hóa như thế nào?
Bạn thiết kế cách sinh, lưu hoặc quản lý nonce để tránh trùng lặp khi nhiều instance mã hóa đồng thời ra sao?
Bạn lựa chọn random nonce hay counter-based nonce và đánh giá rủi ro khi process restart hoặc counter bị rollback như thế nào?
Bạn xử lý trường hợp nonce bị tái sử dụng đã xảy ra trong production bằng cách đánh giá phạm vi khóa và dữ liệu bị ảnh hưởng như thế nào?
Bạn phân biệt CSPRNG với PRNG thông thường và xác định vì sao bảo mật cần nguồn ngẫu nhiên mật mã như thế nào?
Bạn giải thích entropy và cách hệ điều hành cung cấp dữ liệu ngẫu nhiên cho ứng dụng như thế nào?
Bạn đánh giá rủi ro dùng timestamp, UUID không phù hợp hoặc số ngẫu nhiên tự viết để tạo khóa và nonce ra sao?
Bạn xác định cách khởi tạo seed và xử lý trạng thái RNG sau fork, snapshot hoặc clone máy ảo như thế nào?
Bạn kiểm tra dấu hiệu entropy yếu hoặc RNG bị lặp giữa các container và instance như thế nào?
Bạn phân biệt random salt, secret key, IV và nonce về yêu cầu bí mật, ngẫu nhiên hoặc duy nhất ra sao?
Bạn thiết kế envelope encryption với data encryption key và key encryption key để mã hóa dữ liệu quy mô lớn như thế nào?
Bạn phân biệt key wrapping với mã hóa dữ liệu nghiệp vụ trực tiếp bằng master key ra sao?
Bạn tổ chức key hierarchy và key separation để một khóa không được tái sử dụng cho nhiều mục đích mật mã khác nhau như thế nào?
Bạn giải thích domain separation trong dẫn xuất khóa giúp tránh dùng nhầm cùng một khóa cho các giao thức hoặc mục đích khác nhau ra sao?
Bạn xác định vòng đời khóa gồm tạo, phân phối, kích hoạt, xoay vòng, thu hồi, lưu trữ và hủy như thế nào?
Bạn lựa chọn nơi lưu khóa giữa secret manager, KMS và HSM dựa trên mức độ nhạy cảm cùng yêu cầu kiểm soát nào?
Bạn phân biệt KMS với HSM về chức năng quản lý vòng đời khóa và ranh giới bảo vệ thao tác mật mã như thế nào?
Bạn thiết kế quyền truy cập khóa theo least privilege và tách biệt quyền quản trị với quyền sử dụng khóa như thế nào?
Bạn tổ chức key rotation để dữ liệu đã mã hóa bằng khóa cũ vẫn giải mã được trong giai đoạn chuyển đổi ra sao?
Bạn phân biệt rotation khóa ký với rotation khóa mã hóa dữ liệu và cách xác minh chữ ký cũ sau khi thay khóa như thế nào?
Bạn xác định khi nào cần re-encrypt dữ liệu và khi nào chỉ cần re-wrap data encryption key như thế nào?
Bạn xử lý khóa bị lộ hoặc nghi bị lộ bằng quy trình thu hồi, thay thế, đánh giá dữ liệu và điều tra ra sao?
Bạn lập kế hoạch backup và recovery khóa để tránh mất khả năng giải mã dữ liệu khi KMS hoặc vùng triển khai gặp sự cố như thế nào?
Bạn xác định điều kiện hủy khóa an toàn và tác động của cryptographic erasure tới dữ liệu lưu trữ ra sao?
Bạn giải thích PKI liên kết public key với danh tính thông qua chứng thư số và CA như thế nào?
Bạn phân biệt root CA, intermediate CA và end-entity certificate trong chuỗi tin cậy ra sao?
Bạn kiểm tra certificate chain, validity period, SAN và key usage khi xác minh danh tính máy chủ như thế nào?
Bạn phân biệt Common Name với Subject Alternative Name và xác định cách kiểm tra hostname hiện đại ra sao?
Bạn giải thích certificate signing request và vai trò của khóa riêng khi xin cấp chứng thư như thế nào?
Bạn phân biệt certificate renewal, reissuance và revocation trong vận hành PKI ra sao?
Bạn lựa chọn CRL hoặc OCSP để kiểm tra trạng thái thu hồi chứng thư và đánh giá hành vi khi dịch vụ kiểm tra không khả dụng như thế nào?
Bạn mô tả TLS handshake thiết lập phiên mã hóa và xác thực server hoặc client như thế nào?
Bạn phân biệt TLS certificate authentication với xác thực người dùng ở tầng ứng dụng ra sao?
Bạn giải thích TLS 1.3 thay đổi handshake và loại bỏ các cấu hình mật mã yếu so với phiên bản cũ như thế nào?
Bạn lựa chọn cipher suite và nhóm trao đổi khóa dựa trên tính tương thích, hiệu năng và chính sách bảo mật ra sao?
Bạn xác định rủi ro khi tắt certificate validation hoặc chấp nhận mọi hostname trong HTTP client như thế nào?
Bạn phân biệt TLS termination tại load balancer với mã hóa end-to-end giữa các service trong một kiến trúc như thế nào?
Bạn thiết kế mutual TLS để xác thực hai đầu kết nối và quản lý danh tính workload như thế nào?
Bạn xác định cách xử lý certificate expiry, clock skew và chain không đầy đủ khi TLS handshake thất bại ra sao?
Bạn giải thích downgrade attack và cách giao thức hiện đại ngăn hai bên bị ép dùng cấu hình yếu như thế nào?
Bạn đánh giá những sai sót phổ biến như hard-code key, ECB mode, nonce reuse, tự viết crypto và log secret ảnh hưởng tới bảo mật ra sao?
Bạn thiết kế bộ test vector và kiểm thử liên thông để xác minh triển khai mật mã giữa các ngôn ngữ hoặc thư viện khác nhau như thế nào?
Bạn lựa chọn dữ liệu và chỉ số nào để giám sát lỗi giải mã, xác minh MAC/chữ ký, rotation và trạng thái chứng thư mà không làm lộ bí mật như thế nào?
Bạn xác định bằng chứng cần có để chứng minh lựa chọn thuật toán, quản lý khóa và triển khai mật mã đáp ứng yêu cầu bảo mật trong production như thế nào?
