# Thu hồi khóa bị lộ và đánh giá các token chịu ảnh hưởng

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Khóa và JWKS  
> **Phạm vi:** Ứng phó sự cố khóa JWT/JOSE ở mức mật mã, giao thức và vận hành; không phụ thuộc Java, Spring hay framework cụ thể.

Khi private key ký JWT hoặc secret HMAC bị lộ, kẻ tấn công có thể tạo token giả được các verifier tin cậy chấp nhận nếu chúng vẫn dùng khóa đó. Với khóa giải mã JWE bị lộ, dữ liệu mã hóa có thể bị đọc trái phép. Nếu nguồn phân phối JWKS hoặc metadata tin cậy bị chiếm quyền, verifier có thể nhận nhầm public key do kẻ tấn công kiểm soát.

**Thu hồi khóa trong một sự cố khác với luân chuyển khóa định kỳ.** Rotation bình thường thường có giai đoạn overlap để token cũ tiếp tục được xác minh. Khi khóa bị xâm phạm, giữ khóa đó trong giai đoạn overlap có thể tiếp tục cho phép giả mạo hoặc giải mã trái phép. Cần chặn khóa bị xâm phạm, xác định mọi nơi đã tin khóa, đánh giá token và dữ liệu chịu ảnh hưởng, sau đó khôi phục trust bằng khóa mới qua một kênh đã xác minh.

Không có một trường JWT/JWK tiêu chuẩn duy nhất khiến mọi verifier lập tức thu hồi một khóa. Xóa public key khỏi JWKS không tự động xóa bản cache hoặc khóa đã được ghim trong từng dịch vụ. Vì vậy, kế hoạch ứng phó phải kết hợp **chặn khóa tại verifier, cập nhật JWKS, làm mới cache, thu hồi token/trạng thái và kiểm tra các hệ thống phụ thuộc**.

## 1. Hiểu đúng loại sự cố khóa

### 1.1. Private key ký bất đối xứng bị lộ

Ví dụ issuer ký access token bằng RS256 hoặc PS256. Private key bị sao chép, hoặc attacker có quyền gọi thao tác ký trong KMS/HSM.

Hậu quả:

- Attacker có thể tạo chữ ký hợp lệ cho token mới mà verifier không phân biệt được chỉ bằng kiểm tra chữ ký.
- Attacker có thể tự đặt payload, subject, audience, scope, thời hạn và các claim khác trong phạm vi verifier chấp nhận.
- Mọi verifier tin cùng public key có thể bị ảnh hưởng, kể cả khi private key chỉ bị lộ ở một hệ thống.
- Nếu cùng private key được dùng cho nhiều token profile hoặc môi trường, phạm vi sự cố mở rộng theo toàn bộ các nơi dùng khóa đó.

Không cần private key phải được export thành file mới có thể xem là compromise. Nếu attacker có thể gọi dịch vụ ký với quyền đủ rộng, khả năng phát hành chữ ký giả đã tồn tại.

### 1.2. Secret HMAC bị lộ

Với HS256, HS384 hoặc HS512, issuer và verifier dùng chung secret. Bất kỳ bên nào có secret đều có thể tạo MAC hợp lệ.

Hậu quả:

- Attacker có thể giả mạo token tại mọi verifier dùng cùng secret.
- Nếu secret được chia sẻ giữa nhiều issuer, API hoặc môi trường, tất cả các miền đó cần được đánh giá.
- Không thể giữ một verifier như “chỉ xác minh” nếu verifier đó vẫn nắm secret HMAC.
- Thay secret ở issuer mà không thay/chặn secret cũ tại tất cả verifier là chưa thu hồi xong.

Khi secret HMAC bị lộ, cần coi mọi bên từng được cấp secret là có khả năng ký token. Phạm vi tin cậy vốn có của thiết kế HMAC phải được tính vào đánh giá tác động.

### 1.3. Private key giải mã JWE bị lộ

Khóa dùng để giải mã JWE có mục đích khác với khóa ký JWS. Khi private decryption key hoặc secret quản lý khóa JWE bị lộ:

- Attacker có thể giải mã các ciphertext mà khóa đó bảo vệ, tùy thuật toán quản lý khóa và cách thiết lập khóa.
- Nếu attacker đã thu thập JWE trước đó, một số thuật toán dùng khóa recipient dài hạn có thể khiến dữ liệu lịch sử cũng bị lộ.
- Việc lộ khóa giải mã không tự động cho phép tạo chữ ký JWS hợp lệ.
- Nếu cùng key material được tái sử dụng cho ký và mã hóa, sự cố có thể ảnh hưởng cả hai chức năng; thiết kế đúng phải tách khóa theo mục đích.

Với JWE, phải xem xét cả bí mật trong token đã lưu, token đã truyền qua mạng, log, queue, backup và bản sao ở các hệ thống trung gian. Thu hồi khóa không thể làm ciphertext đã bị sao chép biến mất.

### 1.4. Public key bị lộ không đồng nghĩa khóa bị xâm phạm

Public key trong JWKS được thiết kế để phân phối công khai. Việc attacker biết RSA/EC public key không cho phép họ tạo chữ ký hợp lệ.

Phân biệt:

| Tình huống | Đánh giá |
|---|---|
| Public key được tải xuống hoặc xuất hiện trong log công khai | Thông thường không phải sự cố bí mật khóa |
| Private key hoặc HMAC secret bị truy cập trái phép | Compromise khóa mật mã |
| Attacker có quyền ký qua KMS/HSM | Compromise năng lực ký, kể cả private key không exportable |
| JWKS/metadata bị sửa để trỏ tới public key của attacker | Compromise kênh phân phối/trust |
| DNS, TLS, tài khoản quản trị hoặc kho cấu hình JWKS bị chiếm quyền | Có thể làm verifier nhận khóa giả; cần xử lý như sự cố trust |

Nếu chỉ public key bị công khai, không cần thu hồi chỉ vì tính công khai đó. Nếu nguồn tin cậy phân phối public key bị chiếm quyền, cần xác minh lại trust chain và các khóa mà verifier đã nhận.

### 1.5. Phân loại theo tài sản bị xâm phạm

| Tài sản | Năng lực attacker có thể có | Phạm vi cần điều tra |
|---|---|---|
| JWS private signing key | Ký token giả | Mọi issuer/profile/verifier dùng khóa |
| HMAC secret | Tạo MAC giả | Mọi bên và môi trường dùng secret |
| JWE private decryption key | Đọc ciphertext | Token và dữ liệu được mã hóa bằng khóa |
| KMS/HSM signing permission | Yêu cầu ký bằng khóa | Mọi thao tác ký trong phạm vi quyền bị lộ |
| JWKS publishing credential | Thay đổi khóa công khai được công bố | Verifier tin nguồn JWKS đó |
| Discovery/issuer metadata | Thay đổi trust endpoint hoặc JWKS URI | Các verifier dùng metadata bị ảnh hưởng |
| Backup, snapshot hoặc secret store | Có thể lấy lại key material | Mọi bản sao và hệ thống khôi phục |

## 2. Khi nào phải kích hoạt quy trình thu hồi khẩn cấp?

Kích hoạt quy trình sự cố khi có bằng chứng hoặc nghi vấn đáng tin cậy về:

- Private key/secret xuất hiện ngoài nơi lưu trữ được phép.
- Quyền ký hoặc giải mã được cấp cho danh tính, workload hay người không được ủy quyền.
- KMS/HSM ghi nhận thao tác ký bất thường, không giải thích được hoặc vượt phạm vi.
- Credential quản trị JWKS, discovery metadata hoặc trust store bị lộ.
- Có token hợp lệ về chữ ký nhưng chứa claim/subject/audience bất thường và có dấu hiệu được ký trái phép.
- Backup, snapshot, image hoặc log có chứa key material bị truy cập trái phép.
- Nhà cung cấp, nhóm vận hành hoặc hệ thống giám sát xác nhận khóa đã bị xâm phạm.

Không chờ xác định được attacker đã phát hành token giả hay chưa mới chặn khóa nếu bằng chứng cho thấy attacker có thể ký. Thời gian trì hoãn làm tăng số token giả có thể được chấp nhận.

### 2.1. Mức độ ưu tiên

| Mức | Ví dụ | Hành động |
|---|---|---|
| Khẩn cấp | Private signing key/HMAC secret bị lộ; attacker có quyền ký | Chặn khóa tại verifier và ngừng phát hành bằng khóa đó ngay |
| Cao | KMS/HSM hoặc JWKS publishing account bị chiếm quyền, chưa xác định thao tác | Cô lập quyền, bảo toàn log, xác minh trust và chuẩn bị chặn khóa |
| Cần điều tra | Chỉ phát hiện public key công khai hoặc một cảnh báo chưa có bằng chứng truy cập khóa riêng | Xác minh nguồn, quyền và log; không nhầm public key công khai với secret |

Mức độ thực tế phải dựa trên dữ liệu, phạm vi hệ thống và chính sách ứng phó sự cố của tổ chức.

## 3. Những việc cần làm ngay khi phát hiện

### 3.1. Mở incident và chỉ định người điều phối

Ghi nhận:

- Thời điểm phát hiện và thời điểm nghi ngờ bắt đầu bị xâm phạm.
- Loại khóa, key identifier, issuer và môi trường liên quan.
- Ai phát hiện, nguồn cảnh báo và bằng chứng ban đầu.
- Các hệ thống có quyền ký/giải mã hoặc đang tin khóa.
- Người điều phối sự cố, người vận hành issuer, verifier, KMS/HSM và truyền thông nội bộ.

Dùng một incident ID để liên kết log, quyết định thu hồi, thay khóa, kiểm thử và báo cáo sau sự cố.

### 3.2. Bảo toàn bằng chứng trước khi thay đổi có thể xóa dấu vết

Thu thập và bảo vệ:

- Audit log của KMS/HSM, secret manager và hệ thống quản trị khóa.
- Lịch sử truy cập kho bí mật, backup, snapshot và CI/CD.
- Lịch sử phát hành token và metadata key rotation.
- JWKS snapshots, discovery metadata và lịch sử thay đổi cấu hình.
- Log xác minh token, API gateway, resource server và authorization server.
- Network/access log liên quan tới tải JWKS, gọi signing API hoặc truy cập kho khóa.

Ghi thời gian theo nguồn đồng hồ đã đồng bộ, giữ nguyên bản gốc và kiểm soát quyền truy cập bằng quy trình forensic của tổ chức. Không gửi private key/secret vào ticket, chat hoặc log để minh họa sự cố.

### 3.3. Cô lập khả năng tiếp tục sử dụng khóa

Tùy loại sự cố:

- Dừng issuer ký token bằng khóa bị xâm phạm.
- Thu hồi credential hoặc quyền gọi thao tác ký trong KMS/HSM.
- Cô lập tài khoản, workload, pipeline hoặc host có thể truy cập khóa.
- Với HMAC, xác định mọi bản sao secret và chuẩn bị thay tại tất cả verifier.
- Với JWE, dừng mã hóa mới bằng khóa bị lộ và đánh giá dữ liệu đã mã hóa.
- Bảo vệ tài khoản có quyền sửa JWKS, discovery metadata và trust configuration.

Nếu attacker vẫn có quyền gọi signing service, chỉ xóa file private key khỏi một máy không đủ để ngăn phát hành chữ ký giả.

### 3.4. Chọn phương án chặn ngay

Đối với khóa ký bị lộ, phương án chặn hiệu quả nhất là buộc mọi verifier từ chối chữ ký được xác minh bằng khóa đó. Có thể thực hiện bằng:

- Denylist key identity ở verifier.
- Cập nhật cấu hình trust để loại khóa khỏi tập khóa chấp nhận.
- Cập nhật JWKS và buộc refresh cache.
- Cập nhật policy tại gateway và các resource server độc lập.
- Vô hiệu hóa issuer/profile nếu chưa thể xác định chính xác các khóa liên quan.

Không chỉ dựa vào việc xóa key khỏi JWKS; cache hoặc fallback có thể tiếp tục chấp nhận khóa cũ.

## 4. Xác định phạm vi khóa bị ảnh hưởng

### 4.1. Xác định danh tính khóa ổn định

Không dựa duy nhất vào **kid** để xác định một khóa. kid là định danh do bên phát hành đặt, không phải định danh toàn cục và có thể bị thiếu, trùng hoặc tái sử dụng.

Nên đối chiếu:

- Issuer hoặc trust domain đã cấu hình.
- Key ID (**kid**) trong JWKS/token header.
- JWK thumbprint hoặc fingerprint mật mã của public key theo RFC 7638 khi phù hợp.
- Key version/resource ID trong KMS/HSM.
- Key type, algorithm, use, key_ops và purpose.
- Thời gian tạo, kích hoạt, luân chuyển, thu hồi và xóa.

Đối với HMAC secret hoặc private key không công khai, dùng định danh tài sản/key version trong kho khóa; không tạo fingerprint bằng cách ghi secret vào log. Định danh sự cố phải cho phép verifier chặn đúng key material kể cả khi header có kid khác hoặc bị thiếu.

### 4.2. Lập inventory mọi nơi dùng khóa

Tìm tất cả:

| Phạm vi | Câu hỏi |
|---|---|
| Issuer | Dịch vụ nào ký hoặc mã hóa bằng khóa? |
| Verifier | API/client nào xác minh bằng public key hoặc HMAC secret? |
| Token profile | Access token, ID token, service token hay token nghiệp vụ nào dùng khóa? |
| Audience | Những resource server nào chấp nhận token từ khóa? |
| Môi trường | Production, staging, development, DR hoặc tenant nào dùng chung key material? |
| KMS/HSM | Ai có quyền ký, export, rotate hoặc thay policy? |
| JWKS | Khóa được công bố ở endpoint nào, cache ở đâu? |
| Backup/replica | Có bản sao khóa ở vùng, account hoặc hệ thống khôi phục nào? |
| Downstream | Token exchange hoặc service khác có phát hành token tiếp theo dựa trên token bị ảnh hưởng không? |

Nếu cùng key material được tái sử dụng ở nhiều contract, phải đánh giá tất cả contract đó. Không giới hạn điều tra vào service đầu tiên phát hiện sự cố.

### 4.3. Phân biệt khóa bị lộ và kênh trust bị lộ

Nếu private key vẫn an toàn nhưng attacker sửa được JWKS, có thể xảy ra việc verifier tải public key của attacker. Khi đó cần:

1. Khôi phục quyền kiểm soát tài khoản và kênh publish.
2. Xác minh metadata issuer và JWKS URI qua nguồn độc lập đã tin cậy.
3. Kiểm tra mọi phiên bản JWKS mà verifier có thể đã tải.
4. Tìm các key entry lạ và khoảng thời gian chúng được công bố.
5. Xóa cache bị nhiễm và thay thế trust configuration.
6. Xác minh lại các key fingerprint được phép trước khi bật xác minh.

Không đưa một JWKS mới vào trust chỉ vì nó được tải thành công qua endpoint vừa bị nghi chiếm quyền.

## 5. Chặn khóa và thu hồi trong hệ thống phân tán

### 5.1. Chặn theo issuer và key identity

Một denylist khẩn cấp nên gắn với issuer/trust domain và định danh khóa đã chọn, ví dụ:

~~~yaml
emergency_key_blocks:
  - issuer: "https://id.example.com"
    kid: "signing-2026-01"
    key_thumbprint: "sha256-thumbprint-placeholder"
    reason: "suspected_signing_key_compromise"
    blocked_at: "2026-11-16T12:00:00Z"
    status: blocked
~~~

Đây là dữ liệu minh họa, không phải schema tiêu chuẩn. Thời điểm và định danh phải lấy từ incident record và inventory thực tế.

Verifier nên kiểm tra key identity sau khi resolver chọn khóa từ nguồn tin cậy. Nếu có thể chặn sớm theo cặp issuer/key ID đã cấu hình, vẫn phải bảo đảm alias hoặc kid khác không thể dẫn tới cùng key material bị chặn. JWK thumbprint hoặc key version giúp nhận diện khóa ổn định hơn kid đơn lẻ.

Không tin claim **iss** chưa xác minh như nguồn duy nhất để chọn denylist. Issuer được chọn từ contract của endpoint; header/payload chỉ là dữ liệu đầu vào chưa tin cậy.

### 5.2. Xóa khóa khỏi JWKS

Sau khi chặn tại verifier, loại public key bị xâm phạm khỏi JWKS công khai để ngăn verifier mới tải khóa đó. Cần:

- Cập nhật JWKS tại mọi region, replica và CDN.
- Xóa key entry bị xâm phạm khỏi bộ khóa đang được công bố.
- Kiểm tra endpoint discovery có còn trỏ tới JWKS đúng không.
- Kiểm tra CDN, reverse proxy và cache trung gian đã nhận bản cập nhật chưa.
- Đảm bảo không còn bản publish cũ được khôi phục tự động.

JWKS removal là một bước trong quy trình, không phải cơ chế thu hồi tức thời cho mọi verifier.

### 5.3. Xử lý cache và stale fallback

Verifier có thể giữ public key trong bộ nhớ hoặc cache theo HTTP cache policy. Một số hệ thống còn dùng stale-if-error hoặc cache nội bộ để tiếp tục xác minh khi JWKS không khả dụng.

Trong sự cố:

1. Phát lệnh refresh/purge cache tới mọi verifier, gateway và region.
2. Xóa key bị xâm phạm khỏi cache đang hoạt động.
3. Kiểm tra thư viện hoặc dịch vụ có giữ bản key cũ trong memory lâu hơn TTL hay không.
4. Tắt cơ chế stale fallback cho key bị chặn; lỗi tải JWKS không được làm sống lại key đã thu hồi.
5. Xác nhận verifier đang dùng policy/denylist mới trước khi coi sự cố đã được containment.

Không cần tăng cache TTL để giảm tải trong lúc đang thu hồi. Trong sự cố, khả năng áp dụng lệnh chặn đáng tin cậy quan trọng hơn việc tiếp tục xác minh bằng khóa cũ.

### 5.4. Chặn phải lan tới tất cả verifier

Một issuer có thể phát token cho nhiều API; mỗi API có cache và lịch deploy riêng. Cần có xác nhận:

- Tất cả resource server đã nhận denylist hoặc cấu hình chặn.
- Gateway, edge, batch worker và consumer xử lý queue đã cập nhật.
- Các vùng DR/standby không tiếp tục tin key cũ.
- Verifier cũ hoặc dịch vụ ít hoạt động không còn dùng JWKS snapshot cũ.
- Bộ xác minh bên thứ ba đã được thông báo theo hợp đồng.

Nếu một verifier không thể cập nhật lệnh chặn, phải cô lập nó khỏi lưu lượng được bảo vệ hoặc áp dụng chế độ từ chối theo policy. Không tuyên bố khóa đã thu hồi toàn hệ thống chỉ vì JWKS trung tâm đã được sửa.

## 6. Tạo và phân phối khóa thay thế

### 6.1. Tạo khóa mới trong miền tin cậy đã được khôi phục

Trước khi phát hành bằng khóa mới:

- Xác minh attacker không còn quyền truy cập KMS/HSM, secret manager, pipeline hoặc tài khoản quản trị.
- Tạo key material mới bằng quy trình đã phê duyệt.
- Không sao chép hoặc tái sử dụng private key/secret bị nghi lộ.
- Dùng key version và **kid** mới, duy nhất.
- Gắn khóa với đúng issuer, thuật toán và mục đích.
- Giới hạn quyền ký/giải mã theo workload và nguyên tắc least privilege.
- Ghi nhận key fingerprint/version trong incident record.

Nếu miền quản trị hoặc tài khoản quản trị khóa vẫn bị chiếm quyền, tạo khóa mới trong cùng miền đó không khôi phục được trust.

### 6.2. Phân phối public key thay thế

Với chữ ký bất đối xứng:

1. Công bố public key mới qua JWKS đã được khôi phục và xác minh.
2. Verifier tải và kiểm tra key type, thuật toán, mục đích và fingerprint.
3. Kiểm tra cache ở các region và dịch vụ.
4. Chạy test token mới qua mọi verifier liên quan.
5. Chỉ sau khi xác nhận, issuer mới bắt đầu ký bằng private key mới.

Trong rotation bình thường, có thể giữ khóa cũ trong overlap. Với khóa bị xâm phạm, **không duy trì overlap chấp nhận khóa đó**. Khóa cũ phải bị chặn độc lập với việc key mới đã sẵn sàng hay chưa.

### 6.3. Thay secret HMAC

Với HMAC:

- Tạo secret mới trong kho bí mật đã khôi phục.
- Thay secret ở issuer và tất cả verifier được phép xác minh.
- Xóa hoặc vô hiệu hóa bản sao secret cũ ở mọi vùng và backup có thể truy cập.
- Chặn secret cũ bằng key version/secret identifier; không giữ nó trong danh sách fallback.
- Kiểm tra mọi service không còn dùng secret cũ trước khi mở lại lưu lượng.

Nếu verifier không thể cập nhật secret mới, cần từ chối token hoặc cô lập verifier đó. Không tiếp tục chấp nhận secret đã lộ để duy trì tương thích.

### 6.4. Thay khóa giải mã JWE

Với khóa giải mã:

- Tạo recipient key mới và công bố/cấu hình public encryption key mới cho bên gửi theo contract.
- Ngừng mã hóa mới cho recipient bằng khóa bị lộ.
- Cập nhật bên gửi, verifier/decryptor và mọi queue/worker liên quan.
- Xác định ciphertext cũ nào cần giải mã, tái mã hóa hoặc loại bỏ.
- Nếu dữ liệu plaintext có thể đã bị đọc, xử lý như sự cố lộ dữ liệu; thay các secret hoặc credential chứa trong payload nếu cần.

Không coi việc thay khóa JWE là đủ để khôi phục bí mật của ciphertext đã bị attacker sao chép và giải mã.

## 7. Đánh giá các token chịu ảnh hưởng

### 7.1. Xác định token theo key identity và thời gian

Thu thập các dữ liệu sau từ log và hệ thống phát hành:

| Dữ liệu | Dùng để làm gì |
|---|---|
| Issuer / contract ID | Xác định miền tin cậy và profile |
| **kid** / key version / thumbprint | Liên kết token với khóa ký/giải mã |
| Thuật toán và key use | Phân biệt chữ ký, MAC và mã hóa |
| Thời điểm phát hành ghi nhận ở server | Đối chiếu với thời gian khóa có thể bị lộ |
| **iat**, **nbf**, **exp** | Tham khảo thời hạn và cửa sổ sử dụng, sau khi cân nhắc độ tin cậy |
| **jti** | Tìm token cụ thể nếu issuer lưu issuance record |
| **sub**, **client_id**, **act** | Đánh giá principal/actor bị ảnh hưởng |
| **aud**, scope và token profile | Xác định resource và quyền có thể bị tác động |
| Verifier logs | Tìm token đã được chấp nhận và request liên quan |
| KMS/HSM audit | Tìm thao tác ký/giải mã bất thường |

Nếu token không có **kid**, hoặc nhiều kid cùng trỏ tới một key material, phải liên kết bằng key resolver history, key version hoặc fingerprint thay vì chỉ tìm chuỗi kid trong log.

### 7.2. Không dùng iat làm bằng chứng duy nhất

Khi private signing key hoặc HMAC secret đã bị lộ, attacker có thể tự tạo token với **iat** cũ, **exp** dài hoặc **jti** bất kỳ. Vì vậy:

- **iat** trong token không chứng minh token được ký tại thời điểm đó.
- **jti** không giúp liệt kê token giả nếu attacker tự tạo ID mới.
- Claim **sub**, **aud**, **scope** hoặc **client_id** do attacker ký bằng khóa bị lộ cũng có thể là giả.
- Dấu thời gian tin cậy từ issuance database, KMS/HSM audit và log server có giá trị điều tra cao hơn claim do token tự khai.

Không thể phân biệt chắc chắn token hợp lệ và token giả chỉ bằng chữ ký nếu attacker có đúng khóa ký. Chữ ký xác nhận token được tạo bằng khóa; sau khi khóa bị lộ, nó không còn chứng minh issuer đã phê duyệt nội dung.

### 7.3. Xác định khoảng thời gian phơi nhiễm

Xây dựng timeline:

1. Thời điểm sớm nhất có bằng chứng key material/quyền ký bị truy cập.
2. Thời điểm bắt đầu có hành vi bất thường.
3. Thời điểm cuối cùng khóa còn được dùng hợp lệ.
4. Thời điểm issuer dừng ký hoặc dùng khóa.
5. Thời điểm mọi verifier đã chặn khóa.
6. Thời điểm khóa thay thế được xác minh và đưa vào sử dụng.

Nếu không biết chính xác thời điểm compromise, dùng mốc sớm nhất hợp lý theo bằng chứng và mở rộng phạm vi điều tra tương ứng. Không lấy thời điểm phát hiện làm thời điểm bắt đầu sự cố.

### 7.4. Phân loại token và dữ liệu chịu ảnh hưởng

| Nhóm | Cách đánh giá |
|---|---|
| Token được issuer ghi nhận đã phát hành bằng khóa bị lộ | Là token hợp lệ trước sự cố theo issuance record, nhưng cần đánh giá thời hạn và policy thu hồi |
| Token có chữ ký bằng khóa bị lộ nhưng không có issuance record | Có thể là token giả; không thể tin claim chỉ dựa trên chữ ký |
| Token đã được verifier chấp nhận trong khoảng phơi nhiễm | Điều tra request, tài nguyên, hành động và dữ liệu đã truy cập |
| Token chưa hết hạn và vẫn dùng khóa bị chặn | Phải từ chối sau khi denylist được áp dụng |
| Refresh token hoặc token exchange được ký bằng khóa bị lộ | Đánh giá grant, session và các token con đã được cấp |
| JWE được mã hóa bằng khóa giải mã bị lộ | Đánh giá khả năng plaintext đã bị đọc, gồm cả ciphertext lịch sử |
| Token dùng khóa khác nhưng được cấp dựa trên token bị giả mạo | Điều tra chuỗi phát hành downstream và thu hồi token dẫn xuất khi cần |

### 7.5. Không thể chỉ thu hồi những token đã tìm thấy

Nếu signing key bị lộ, attacker có thể tạo token giả chưa từng xuất hiện trong issuance database. Do đó, denylist chỉ theo các **jti** đã tìm thấy không đủ.

Biện pháp mạnh và rõ ràng nhất là từ chối mọi token được xác minh bằng key identity bị xâm phạm trong phạm vi issuer/profile liên quan. Điều này có thể làm mất hiệu lực cả token hợp lệ đã phát hành bằng khóa đó; đó là hệ quả cần dự kiến và truyền thông trong incident plan.

## 8. Thu hồi token, session và quyền liên quan

### 8.1. Access token JWT

Nếu resource server xác minh access token offline, token có thể tiếp tục hợp lệ cho tới **exp** nếu verifier vẫn tin public key cũ. Trong sự cố khóa ký:

- Chặn key identity để từ chối mọi token ký bằng khóa đó.
- Nếu cần, thu hồi theo **jti** đối với các token đã biết; đây là lớp bổ sung, không thay thế chặn khóa.
- Cập nhật gateway, API và cache authorization.
- Yêu cầu token mới được phát hành bằng khóa thay thế sau khi xác minh lại grant và principal.
- Theo dõi các request tiếp tục gửi token dùng key cũ.

Không chỉ rút ngắn thời hạn token ở issuer; token giả đã được ký trước đó hoặc attacker tự tạo vẫn có thể mang **exp** trong tương lai.

### 8.2. Refresh token và grant

Nếu refresh token là JWT được ký bằng khóa bị lộ:

- Chặn khóa để từ chối refresh token ký bằng key identity đó.
- Thu hồi grant/session liên quan theo dữ liệu server-side.
- Xem xét refresh token rotation family và phát hiện reuse.
- Không cho phép refresh token cũ cấp access token mới sau sự cố.

Nếu refresh token là opaque token, kiểm tra kho trạng thái và thu hồi các token/grant trong phạm vi bị ảnh hưởng. Không giả định mọi refresh token đều có **kid** hoặc là JWT.

### 8.3. ID token và phiên đăng nhập

Nếu ID token dùng khóa bị lộ:

- Relying party phải từ chối ID token xác minh bằng khóa bị chặn.
- Đánh giá phiên đăng nhập được thiết lập trong khoảng phơi nhiễm.
- Thu hồi hoặc yêu cầu xác thực lại các phiên có rủi ro theo policy.
- Kiểm tra nonce/session binding và các sự kiện đăng nhập liên quan.

Việc một ID token cũ từng được xác minh không tự chứng minh session hiện tại còn an toàn sau khi issuer bị xâm phạm.

### 8.4. Token nghiệp vụ và token dẫn xuất

Password reset, email verification, action token hoặc service token có thể dùng cùng khóa ký. Nếu vậy, các endpoint nghiệp vụ cũng phải chặn khóa đó và đánh giá:

- Yêu cầu đã hoàn tất hay chưa.
- Token một lần đã được sử dụng hay vẫn còn hiệu lực.
- Tài khoản, email, giao dịch hoặc resource nào bị tác động.
- Token exchange hoặc dịch vụ trung gian có phát hành token mới từ token bị giả mạo không.

Nếu token bị giả mạo đã kích hoạt thay đổi mật khẩu, xác minh email hoặc giao dịch, cần điều tra trạng thái nghiệp vụ và hoàn tác/khóa theo quy trình riêng.

### 8.5. Đánh giá hành động đã được thực hiện

Không dừng ở việc tìm token. Tìm các request đã được xác thực bằng khóa bị xâm phạm:

- Tài nguyên được đọc hoặc tải xuống.
- Dữ liệu được tạo, sửa, xóa hoặc xuất.
- Quyền, role, tenant membership hoặc thông tin xác thực được thay đổi.
- Giao dịch hoặc hành động nhạy cảm được phê duyệt.
- Token mới được phát hành hoặc trao đổi.
- Hệ thống khác đã tin kết quả xác minh từ verifier bị ảnh hưởng.

Phân biệt **token có thể bị giả mạo** với **hành động trái phép đã được xác nhận**. Báo cáo sự cố cần nêu rõ bằng chứng và mức độ chưa chắc chắn.

## 9. Khôi phục dịch vụ và xác lập lại trust

### 9.1. Điều kiện trước khi mở lại

Chỉ khôi phục phát hành/xác minh sau khi:

- Nguồn compromise đã được cô lập hoặc xử lý.
- Quyền truy cập KMS/HSM, secret manager, JWKS publisher và pipeline đã được rà soát.
- Khóa mới được tạo trong miền quản trị tin cậy.
- Public key/secret mới đã được phân phối an toàn tới đúng bên.
- Tất cả verifier cần thiết đã áp dụng lệnh chặn khóa cũ.
- Cache và stale fallback không thể làm sống lại khóa bị thu hồi.
- Bộ test xác minh thành công và từ chối được chạy qua mọi verifier quan trọng.
- Quy trình cấp lại token, đăng nhập lại hoặc khôi phục trạng thái đã sẵn sàng.

### 9.2. Xác minh qua kênh độc lập

Nếu JWKS/discovery hoặc tài khoản publish từng bị xâm phạm, xác minh fingerprint khóa mới qua một kênh độc lập đã được tổ chức tin cậy. Không dùng chính endpoint đang bị nghi chiếm quyền làm bằng chứng duy nhất cho khóa mới.

Kênh độc lập có thể là quy trình quản trị khóa được phê duyệt, hệ thống cấu hình có kiểm soát hoặc thông báo ký/xác thực từ nhóm chịu trách nhiệm. Cách cụ thể phải phù hợp kiến trúc trust của tổ chức.

### 9.3. Cấp lại token và yêu cầu xác thực lại

- Chỉ cấp token mới sau khi principal, client, grant và quyền được kiểm tra lại.
- Yêu cầu đăng nhập/xác thực lại khi session hoặc ID token có thể bị giả mạo.
- Yêu cầu client lấy access token mới bằng quy trình cấp token bình thường.
- Không tự chuyển tiếp claim từ token cũ chưa còn đáng tin.
- Với token nghiệp vụ một lần, tạo yêu cầu mới và liên kết trạng thái server-side mới.

### 9.4. Không rollback về khóa bị lộ

Nếu khóa mới gặp lỗi triển khai, dùng khóa dự phòng khác đã được tạo, bảo vệ và xác minh độc lập. Không bật lại khóa bị xâm phạm để khôi phục availability. Nếu chưa có đường tin cậy, tạm từ chối chức năng phụ thuộc vào khóa thay vì chấp nhận token có thể giả mạo.

## 10. Playbook ứng phó mẫu

### 10.1. Các giai đoạn

| Giai đoạn | Mục tiêu | Hành động trọng tâm | Bằng chứng hoàn tất |
|---|---|---|---|
| 0. Detect | Xác nhận nghi vấn | Ghi incident ID, loại khóa, issuer và thời điểm | Incident được mở |
| 1. Contain | Ngăn attacker tiếp tục ký/giải mã | Dừng ký, thu hồi quyền, chặn key identity | Issuer không còn dùng khóa; verifier áp dụng deny |
| 2. Scope | Xác định phạm vi | Inventory, log, token, profile, audience, dữ liệu | Danh sách hệ thống và token chịu ảnh hưởng |
| 3. Recover | Khôi phục trust | Tạo khóa mới, publish an toàn, cập nhật verifier | Test pass ở mọi verifier quan trọng |
| 4. Revoke | Vô hiệu hóa quyền cũ | Thu hồi token/grant/session và token dẫn xuất | Trạng thái cũ bị chặn |
| 5. Review | Rút kinh nghiệm | Forensic, tác động dữ liệu, cải thiện kiểm soát | Incident report và action items |

Các giai đoạn có thể chạy song song bởi các nhóm khác nhau, nhưng việc mở lại xác minh phải phụ thuộc vào bằng chứng containment và trust recovery.

### 10.2. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Phát hiện nghi vấn khóa] --> B{Loại khóa/tài sản?}
    B -->|Signing private key hoặc HMAC secret| C[Dừng ký và chặn key identity]
    B -->|JWE decryption key| D[Dừng giải mã/mã hóa mới bằng khóa bị lộ]
    B -->|JWKS hoặc metadata trust| E[Cô lập publisher và xác minh trust độc lập]
    B -->|Chỉ public key công khai| F[Kiểm tra nguồn và quyền; không coi public key là secret]
    C --> G[Inventory issuer, verifier, profile và token]
    D --> H[Đánh giá ciphertext và dữ liệu có thể lộ]
    E --> G
    F --> I{Có bằng chứng trust bị sửa?}
    I -->|Có| E
    I -->|Không| J[Đóng cảnh báo hoặc tiếp tục theo dõi]
    G --> K[Thu hồi token/session/grant chịu ảnh hưởng]
    H --> K
    K --> L[Tạo và phân phối khóa thay thế qua trust đã khôi phục]
    L --> M[Kiểm thử tất cả verifier]
    M --> N[Giám sát và hoàn tất incident]
~~~

### 10.3. Mẫu thông tin sự cố

~~~yaml
incident:
  id: SEC-INC-EXAMPLE
  status: active
  detected_at: "2026-11-16T12:00:00Z"
  suspected_start: "unknown"
  key:
    issuer: "https://id.example.com"
    kid: "signing-2026-01"
    key_version: "kms-key-version-placeholder"
    thumbprint: "sha256-thumbprint-placeholder"
    purpose: signing
    algorithm: PS256
  containment:
    issuer_signing_stopped: true
    verifier_key_blocked: true
    jwks_entry_removed: true
    caches_purged: pending
  impact:
    contracts_under_review:
      - orders-access-v1
      - inventory-access-v1
    verifiers_confirmed_blocked: []
    tokens_and_sessions_under_review: true
    data_access_review: pending
  recovery:
    replacement_key_created: pending
    replacement_jwks_verified: pending
    verifier_conformance_passed: pending
~~~

Mẫu này chỉ minh họa cấu trúc incident record. Không ghi key material, secret, bearer token hoặc dữ liệu nhạy cảm trực tiếp vào YAML sự cố.

## 11. Kiểm thử khả năng thu hồi trước khi có sự cố

Một quy trình chỉ tồn tại trên tài liệu chưa chứng minh có thể thực thi trong thời gian cần thiết. Nên kiểm thử định kỳ trong môi trường kiểm soát.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| K01 | Chặn một key ID đang được verifier cache | Token dùng key đó bị từ chối sau khi policy chặn có hiệu lực |
| K02 | Xóa key khỏi JWKS nhưng verifier giữ cache cũ | Kiểm thử chứng minh denylist/cache purge chặn key cũ |
| K03 | Token dùng kid alias nhưng cùng key material | Key fingerprint/version vẫn bị chặn |
| K04 | Token thiếu kid nhưng resolver chọn key bị lộ | Verifier vẫn từ chối theo key identity |
| K05 | Một region chưa nhận JWKS mới | Region bị phát hiện và không tiếp tục chấp nhận key bị chặn |
| K06 | JWKS endpoint lỗi và stale fallback được bật | Key đã bị thu hồi không được sống lại từ cache |
| K07 | Issuer còn một replica dùng private key cũ | Kiểm thử phát hiện replica và xác nhận dừng ký |
| K08 | HMAC secret còn ở một verifier cũ | Verifier chưa cập nhật bị cô lập hoặc từ chối |
| K09 | Refresh token JWT dùng key bị lộ | Token endpoint từ chối và grant/family được xử lý |
| K10 | Token nghiệp vụ đã dùng nhưng còn exp | Replay vẫn bị từ chối theo trạng thái |
| K11 | Khóa giải mã JWE bị thu hồi | Ciphertext mới không còn được xử lý bằng khóa cũ; dữ liệu lịch sử được đánh giá |
| K12 | Khóa thay thế được publish | Mọi verifier lấy đúng key mới và xác minh token thử thành công |
| K13 | Khóa mới không tương thích một verifier | Verifier đó không được mở lại bằng cách bật khóa cũ |
| K14 | KMS signing permission bị thu hồi | Các danh tính cũ không thể tiếp tục gọi thao tác ký |

### 11.1. Mục tiêu thời gian thu hồi

Tổ chức nên đặt mục tiêu đo được, chẳng hạn:

- Thời gian từ phát hiện đến dừng ký.
- Thời gian từ quyết định đến khi mọi verifier chặn key identity.
- Thời gian để purge cache ở mọi region.
- Thời gian để thu hồi refresh token/grant/session.
- Thời gian để xác minh khóa mới và mở lại từng dịch vụ.

Không dùng một con số mẫu làm SLA chung. Mục tiêu phải dựa trên kiến trúc, rủi ro, số lượng verifier và khả năng tự động hóa. Điều quan trọng là biết chính xác khi nào lệnh chặn đã có hiệu lực ở từng nơi.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ xóa key khỏi JWKS | Cache có thể tiếp tục tin khóa cũ | Denylist tại verifier và purge cache |
| Chờ token cũ hết hạn | Attacker có thể tiếp tục tạo token mới | Chặn khóa ngay |
| Chỉ thu hồi các jti đã tìm thấy | Không bao phủ token giả chưa từng được ghi nhận | Chặn toàn bộ key identity bị xâm phạm |
| Tin iat để phân biệt token giả | Attacker có thể backdate claim | Dùng log/issuance record tin cậy; chặn khóa |
| Giữ khóa bị lộ trong overlap | Tiếp tục chấp nhận chữ ký/MAC giả | Không overlap với key đã compromise |
| Chỉ thay private key ở issuer | Verifier hoặc replica vẫn dùng cấu hình cũ | Đồng bộ chặn và cập nhật tất cả verifier |
| Quên staging/DR/region phụ | Một miền vẫn chấp nhận token giả | Inventory toàn bộ môi trường và replica |
| Quên refresh token hoặc token con | Attacker có thể tiếp tục xin token mới | Thu hồi grant, family và token dẫn xuất |
| Nhầm public key công khai với secret bị lộ | Thu hồi không cần thiết, gây gián đoạn | Phân loại đúng private/public material |
| Dùng lại key material hoặc kid | Resolver có thể chọn nhầm khóa | Key mới, kid/version mới, fingerprint riêng |
| Tin JWKS vừa được cập nhật từ nguồn đã bị chiếm | Attacker có thể tiếp tục phân phối khóa giả | Khôi phục trust qua kênh độc lập |
| Khôi phục bằng cách bật lại khóa cũ | Tái mở đường giả mạo | Chỉ dùng khóa thay thế đã xác minh |

## 13. Checklist thu hồi và đánh giá tác động

**Phân loại và containment**

- [ ] Xác định đúng loại khóa: signing private key, HMAC secret, JWE decryption key hay trust/distribution credential.
- [ ] Mở incident, ghi thời điểm phát hiện và mốc compromise sớm nhất có thể.
- [ ] Bảo toàn KMS/HSM, JWKS, issuer, verifier và access logs.
- [ ] Dừng thao tác ký/giải mã trái phép và thu hồi quyền truy cập liên quan.
- [ ] Chặn key identity ở mọi verifier; không chỉ xóa khỏi JWKS.

**JWKS và trust**

- [ ] Loại khóa bị xâm phạm khỏi JWKS và mọi replica/CDN.
- [ ] Purge cache, memory cache và stale fallback.
- [ ] Chặn theo issuer cùng key version/fingerprint; xử lý alias hoặc kid thiếu.
- [ ] Xác minh metadata/JWKS qua kênh độc lập nếu publisher/trust bị xâm phạm.
- [ ] Có xác nhận từ từng verifier, region, gateway và DR site.

**Đánh giá token và nghiệp vụ**

- [ ] Inventory mọi contract, issuer, audience, profile và môi trường dùng khóa.
- [ ] Tìm token theo key identity, issuance record và log xác minh.
- [ ] Không dựa riêng vào iat, jti hoặc claim chưa còn đáng tin để phân biệt token giả.
- [ ] Thu hồi access token, refresh token, grant, session và token nghiệp vụ chịu ảnh hưởng.
- [ ] Điều tra request, dữ liệu đã truy cập và token dẫn xuất.
- [ ] Đánh giá riêng ảnh hưởng bảo mật dữ liệu khi JWE decryption key bị lộ.

**Khôi phục**

- [ ] Xác nhận nguồn compromise đã được xử lý và quyền quản trị đã được rà soát.
- [ ] Tạo key material mới và key ID/version mới trong miền tin cậy.
- [ ] Publish/trao đổi khóa thay thế qua kênh đã xác minh.
- [ ] Mọi verifier đã áp dụng denylist cũ và xác minh được token mới.
- [ ] Không tái kích hoạt khóa bị xâm phạm để rollback.
- [ ] Có giám sát token cũ, lỗi xác minh và hoạt động bất thường sau khôi phục.

**Điều cần nhớ:** Khi khóa ký hoặc secret HMAC bị lộ, không thể tin chữ ký để phân biệt token hợp lệ với token giả do attacker tạo bằng chính khóa đó. Hãy chặn toàn bộ key identity tại verifier, xử lý cache/JWKS, đánh giá mọi token và hành động liên quan, thu hồi session/grant cần thiết rồi khôi phục bằng khóa mới qua trust đã được xác minh. Với khóa giải mã JWE, phải đánh giá cả ciphertext lịch sử và dữ liệu plaintext có thể đã bị lộ.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cơ chế chữ ký/MAC và protected header.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): Mã hóa, quản lý khóa và authentication tag.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và tham số khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): Thuật toán JOSE và yêu cầu khóa.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): Fingerprint ổn định cho JWK.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Ràng buộc issuer, audience, thuật toán và khóa khi xác minh JWT.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi token OAuth.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Bảo vệ refresh token và thực hành xử lý OAuth token.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): Quản lý vòng đời và bảo vệ khóa mật mã.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): Tổ chức ứng phó và phục hồi sau sự cố an ninh mạng.
