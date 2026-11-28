# Xoay vòng khóa và đọc cấu hình cũ trong giai đoạn chuyển đổi

Khi Spring Cloud Config lưu giá trị nhạy cảm dưới dạng ciphertext trong Git hoặc backend khác, Config Server cần khóa phù hợp để giải mã trước khi trả cấu hình cho client. Đến lúc thay khóa, hệ thống thường phải phục vụ đồng thời hai nhóm dữ liệu: ciphertext cũ được mã hóa bằng khóa trước và ciphertext mới dùng khóa thay thế. Nếu đổi khóa đang hoạt động quá sớm, các cấu hình cũ có thể không giải mã được và ứng dụng sẽ thiếu những property quan trọng.

Spring Cloud Config hỗ trợ nhiều khóa khi dùng keystore: ciphertext có thể mang metadata chỉ rõ alias khóa qua tiền tố {key:alias}. Config Server dùng TextEncryptorLocator để chọn bộ giải mã tương ứng. Cách chuyển đổi an toàn là giữ khóa cũ và mới cùng khả dụng trong giai đoạn chuyển tiếp, gắn alias rõ ràng cho ciphertext, chuyển dần dữ liệu sang khóa mới, rồi chỉ loại khóa cũ khi mọi phiên bản cấu hình còn cần hỗ trợ đã được xử lý.

## 1. Mục tiêu và phạm vi của key rotation

Xoay vòng khóa là thay vật liệu mã hóa đang dùng bằng khóa mới theo một kế hoạch có kiểm soát. Các lý do thường gặp:

- Thay khóa theo lịch bảo mật của tổ chức.
- Thay khóa khi có dấu hiệu lộ hoặc truy cập trái phép.
- Thay đổi quyền sở hữu hoặc ranh giới tin cậy của Config Server.
- Thay keystore, thuật toán hoặc chính sách quản lý khóa.
- Tách khóa theo môi trường hoặc nhóm ứng dụng.

Phải phân biệt hai mục tiêu:

1. **Khả năng đọc liên tục:** Config Server vẫn giải mã được các ciphertext cũ trong lúc dữ liệu mới bắt đầu dùng khóa mới.
2. **Thu hồi khóa:** khóa cũ được loại khỏi môi trường hoạt động sau khi không còn ciphertext cần đọc bằng khóa đó.

Với rotation định kỳ, có thể duy trì hai alias trong một khoảng chuyển đổi để tránh gián đoạn. Nếu khóa cũ đã bị xâm phạm, cần xử lý như sự cố bảo mật: ưu tiên thay các credential thực tế, chuyển ciphertext sang khóa mới và thu hồi khóa cũ sớm nhất có thể. Việc giữ khóa bị lộ trong runtime chỉ để hỗ trợ rollback có thể duy trì rủi ro.

## 2. Config Server chọn khóa giải mã như thế nào?

Giá trị được mã hóa trong repository thường có tiền tố {cipher}. Khi Config Server đọc Environment, server nhận diện tiền tố này và giải mã trước khi gửi property source đến client theo cấu hình mặc định.

Với keystore, có thể thêm metadata khóa ngay sau {cipher}:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-key-v1}BASE64_CIPHERTEXT'
~~~

Trong ví dụ, alias config-key-v1 cho biết Config Server phải dùng khóa có alias đó trong keystore. Nếu không có metadata key, locator mặc định sử dụng alias đang được cấu hình làm khóa mặc định. Vì vậy, ciphertext cũ không có alias tường minh có thể ngừng giải mã sau khi alias mặc định được đổi.

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| Keystore | Chứa key entry và alias tương ứng |
| encrypt.keyStore.alias | Alias mặc định được chọn cho thao tác mã hóa |
| Tiền tố {key:alias} | Chỉ rõ alias cần dùng cho ciphertext cụ thể |
| TextEncryptorLocator | Tìm bộ mã hóa/giải mã phù hợp với metadata của ciphertext |
| Config Server | Giải mã remote property trước khi trả về client theo chế độ mặc định |

Spring Cloud Config có locator mặc định hỗ trợ chọn alias trong keystore thông qua tiền tố key. Nếu dùng cơ chế khóa khác hoặc cần tra khóa từ hệ thống bên ngoài, có thể triển khai TextEncryptorLocator tùy chỉnh.

## 3. Chuẩn bị keystore chứa khóa cũ và khóa mới

Ví dụ này dùng keystore PKCS12 có hai alias:

- config-key-v1: khóa đang giải mã dữ liệu cũ.
- config-key-v2: khóa mới sẽ dùng cho ciphertext mới.

Kiểm tra alias hiện có:

~~~bash
keytool -list -keystore config-keys.p12 -storetype PKCS12
~~~

Thêm key pair mới vào keystore hiện tại:

~~~bash
keytool -genkeypair \
  -alias config-key-v2 \
  -keyalg RSA \
  -keysize 3072 \
  -storetype PKCS12 \
  -keystore config-keys.p12
~~~

Lệnh sẽ yêu cầu mật khẩu keystore và thông tin chứng thư. Khi cập nhật keystore hiện hữu, hãy dùng đúng file và mật khẩu đang quản lý; không tạo một file keystore mới rồi vô tình làm mất alias cũ. Có thể dùng công cụ quản lý khóa tập trung thay cho keytool nếu tổ chức đã có quy trình cấp phát.

Kiểm tra lại cả hai alias:

~~~bash
keytool -list -keystore config-keys.p12 -storetype PKCS12
~~~

Config Server cần đọc được keystore có cả key entry cũ và mới. Bảo vệ file bằng quyền filesystem tối thiểu, mount từ secret volume hoặc lấy từ hệ thống quản lý khóa. Không commit keystore, private key hoặc mật khẩu vào Config Repository.

## 4. Cấu hình Config Server dùng keystore

Ví dụ cấu hình keystore:

~~~yaml
encrypt:
  keyStore:
    location: file:/run/secrets/config-keys.p12
    type: PKCS12
    alias: config-key-v1
~~~

Hãy cấp thuộc tính encrypt.keyStore.password qua biến môi trường ENCRYPT_KEYSTORE_PASSWORD hoặc secret manager theo cơ chế binding của Spring Boot. Ví dụ trên giữ alias mặc định là config-key-v1 trong giai đoạn chuẩn bị, trong khi keystore đã chứa config-key-v2.

Nếu dùng bootstrap context cũ, các thuộc tính mã hóa phải được đặt ở nguồn có sẵn trong giai đoạn khởi tạo Config Server theo hướng dẫn của phiên bản đang dùng. Với cấu hình hiện đại, bảo đảm key store location, password và alias được nạp trước khi các endpoint mã hóa/giải mã xử lý request.

Các thuộc tính quan trọng:

- encrypt.keyStore.location: vị trí resource của keystore.
- encrypt.keyStore.password: mật khẩu mở keystore.
- encrypt.keyStore.alias: alias mặc định cho khóa đang hoạt động.
- encrypt.keyStore.type: loại keystore, ví dụ PKCS12 hoặc JKS.

Đối với keystore bất đối xứng, thao tác mã hóa sử dụng public key và giải mã cần private key tương ứng. Giữ private key trong phạm vi Config Server và hệ thống quản lý khóa được kiểm soát. Client thông thường không cần giữ private key nếu Config Server giải mã trước khi phân phối cấu hình qua HTTPS.

## 5. Hiểu rõ ciphertext cũ không có alias

Trước khi rotation, cấu hình có thể chứa ciphertext dạng:

~~~yaml
spring:
  datasource:
    password: '{cipher}OLD_CIPHERTEXT'
~~~

Giá trị này phụ thuộc alias mặc định của Config Server tại thời điểm giải mã. Nếu đổi alias mặc định từ config-key-v1 sang config-key-v2 trong khi ciphertext vẫn không có {key:...}, locator có thể thử khóa mới và thất bại khi giải mã dữ liệu vốn được mã hóa bằng khóa cũ.

Trước khi đổi alias mặc định, cần gắn metadata cũ một cách tường minh:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-key-v1}OLD_CIPHERTEXT'
~~~

Việc thêm tiền tố alias không mã hóa lại dữ liệu. Nó chỉ chỉ định khóa mà Config Server phải dùng để giải mã ciphertext hiện có. Chỉ thực hiện khi đã xác minh ciphertext đó thực sự được tạo bằng config-key-v1.

Không thay thế hàng loạt tiền tố bằng một alias dựa trên giả định. Nếu repository từng dùng nhiều khóa, hãy xác định nguồn gốc từng ciphertext trước khi gắn alias; gắn sai alias có thể làm cấu hình không giải mã được.

## 6. Chiến lược chuyển đổi hai khóa

Một rotation có thời gian chuyển tiếp có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Đang dùng key-v1] --> B[Thêm key-v2 vào keystore]
    B --> C[Giữ alias mặc định v1]
    C --> D[Gắn key-v1 cho ciphertext cũ]
    D --> E[Kiểm tra v1 và v2 đều giải mã được]
    E --> F[Chuyển alias mặc định sang v2]
    F --> G[Mã hóa mới bằng v2]
    G --> H[Mã hóa lại dữ liệu cũ]
    H --> I[Quét mọi ref và môi trường]
    I --> J[Hết phụ thuộc v1]
    J --> K[Thu hồi alias v1 theo chính sách]
~~~

### Giai đoạn A: thêm khóa mới nhưng chưa đổi mặc định

1. Sao lưu keystore theo quy trình bảo vệ khóa.
2. Thêm alias config-key-v2 vào keystore đang chứa config-key-v1.
3. Giữ encrypt.keyStore.alias là config-key-v1.
4. Khởi động hoặc reload Config Server theo cách triển khai.
5. Kiểm tra server đọc được keystore và giải mã được một ciphertext kiểm thử bằng v1.
6. Tạo ciphertext thử nghiệm có chỉ định alias v2 và xác nhận server giải mã được.

Trong giai đoạn này, dữ liệu cũ tiếp tục dùng alias mặc định v1. Ciphertext mới có thể được tạo rõ ràng bằng v2 qua metadata key. Như vậy, hệ thống có thể xác nhận cả hai khóa trước khi chuyển mặc định.

### Giai đoạn B: gắn alias cho toàn bộ ciphertext cũ

Tìm các property bắt đầu bằng {cipher} nhưng chưa có metadata key. Với dữ liệu đã xác định dùng v1, cập nhật thành:

~~~yaml
database:
  password: '{cipher}{key:config-key-v1}OLD_CIPHERTEXT'
~~~

Giữ nguyên phần ciphertext sau tiền tố. Commit thay đổi metadata và kiểm tra Config Server vẫn trả giá trị đã giải mã. Việc này làm các bản cấu hình cũ không còn phụ thuộc alias mặc định.

### Giai đoạn C: chuyển alias mặc định sang khóa mới

Sau khi các ciphertext cũ đã được gắn alias, đổi cấu hình:

~~~yaml
encrypt:
  keyStore:
    location: file:/run/secrets/config-keys.p12
    type: PKCS12
    alias: config-key-v2
~~~

Password vẫn được cấp từ secret manager hoặc biến môi trường. Sau khi Config Server khởi động với alias mới, kiểm tra:

- Ciphertext có key-v1 vẫn giải mã bằng alias cũ.
- Ciphertext có key-v2 giải mã bằng alias mới.
- Giá trị không có metadata key được mã hóa mới dùng alias mặc định v2.
- Endpoint Environment không trả ciphertext thô thay cho property cần dùng.

Từ thời điểm này, mọi giá trị mới nên được tạo với alias v2 tường minh để việc truy vết và rotation tiếp theo dễ dàng.

### Giai đoạn D: mã hóa lại dữ liệu cũ

Đối với mỗi property còn dùng v1:

1. Lấy plaintext qua quy trình giải mã được ủy quyền và bảo vệ.
2. Mã hóa plaintext bằng config-key-v2.
3. Thay ciphertext cũ trong đúng repository và label.
4. Giữ metadata {key:config-key-v2} trong giá trị mới.
5. Kiểm tra Config Server giải mã được giá trị mới.
6. Không ghi plaintext ra log, terminal history, pull request hoặc file tạm không bảo vệ.

Ví dụ sau khi hoàn tất:

~~~yaml
database:
  password: '{cipher}{key:config-key-v2}NEW_CIPHERTEXT'
~~~

Nếu có nhiều repository, branch, tag hoặc label production, phải xử lý tất cả phiên bản còn được phép triển khai hoặc rollback. Chỉ cập nhật branch chính mà bỏ sót tag cũ có thể khiến một lần rollback sau này cần alias v1.

## 7. Tạo ciphertext có chỉ định alias

Config Server cung cấp endpoint POST /encrypt và POST /decrypt khi được cấu hình khóa. Endpoint /encrypt có thể nhận metadata {key:alias} cùng plaintext để chọn khóa mã hóa:

~~~bash
curl -X POST \
  -H 'Content-Type: text/plain' \
  --data-urlencode '={key:config-key-v2}VALUE_TO_ENCRYPT' \
  https://config-server.internal/encrypt
~~~

Thay VALUE_TO_ENCRYPT bằng giá trị lấy từ secret manager hoặc công cụ an toàn. Không đưa secret thật trực tiếp vào shell history, log CI hoặc ticket. Hãy lưu kết quả ciphertext và giữ nguyên tiền tố key mà endpoint trả về nếu có.

Endpoint /decrypt có thể dùng để kiểm tra một ciphertext đã được mã hóa bằng alias cũ hoặc mới. Đây là endpoint rất nhạy cảm vì trả plaintext. Chỉ gọi từ mạng quản trị, với danh tính được phân quyền riêng; không mở công khai và không ghi response vào log.

Nếu muốn tạo ciphertext theo application/profile riêng, Spring Cloud Config hỗ trợ đường dẫn encrypt/decrypt theo application và profile khi có TextEncryptorLocator tùy chỉnh phù hợp. Locator mặc định không tự tạo khóa riêng theo từng application/profile; không giả định chỉ đổi URL là đã có key isolation.

## 8. Trường hợp dùng khóa đối xứng encrypt.key

Một số Config Server dùng khóa đối xứng qua thuộc tính encrypt.key hoặc biến môi trường ENCRYPT_KEY. Cách này đơn giản nhưng chỉ có một giá trị khóa mặc định trong cấu hình chuẩn. Cơ chế chọn alias {key:...} của locator mặc định được mô tả cho keystore, không tự động biến một encrypt.key đơn lẻ thành kho nhiều khóa.

Khi rotation khóa đối xứng, có hai lựa chọn:

- Triển khai TextEncryptorLocator tùy chỉnh để đọc metadata phiên bản và chọn đúng TextEncryptor cho ciphertext cũ/mới trong thời gian chuyển tiếp.
- Dùng một cửa sổ bảo trì có kiểm soát: giải mã và mã hóa lại toàn bộ ciphertext bằng khóa mới, xác minh không còn dữ liệu cũ, rồi thay encrypt.key và khởi động lại Config Server.

Không đổi ENCRYPT_KEY trước khi xử lý toàn bộ ciphertext cũ nếu server không có locator hỗ trợ đồng thời hai khóa. Nếu có nhiều instance Config Server, phải triển khai khóa và cấu hình nhất quán trên tất cả instance; tránh trạng thái một node giải mã được còn node khác trả lỗi.

## 9. Xác minh server vẫn đọc được cấu hình cũ và mới

Kiểm thử cần bao gồm cả thao tác giải mã trực tiếp và endpoint Environment:

1. Tạo ciphertext kiểm thử bằng alias v1 và alias v2, không dùng secret production.
2. Gọi /decrypt qua kênh quản trị để xác nhận từng alias được nhận diện.
3. Gọi endpoint Environment cho application/profile/label có property cũ và mới.
4. Xác nhận response chứa giá trị đã giải mã ở property source tương ứng.
5. Khởi động một Config Client thử nghiệm và xác nhận property bind thành công.
6. Kiểm tra log Config Server để phát hiện lỗi decrypt hoặc invalid property.
7. Thử lại với tất cả Config Server instance sau rollout.

Ví dụ endpoint Environment:

~~~bash
curl --fail \
  https://config-server.internal/order-service/prod/release-2026.11
~~~

Trong kiểm thử, chỉ xác nhận property tồn tại và có thể bind; không in password, token hoặc private key ra output. Nếu cần đối chiếu plaintext, dùng một giá trị kiểm thử không nhạy cảm hoặc phép so sánh an toàn trong chương trình.

Khi Config Server không giải mã được ciphertext, property có thể bị loại khỏi nguồn trả về và xuất hiện marker invalid để tránh client vô tình sử dụng chuỗi ciphertext như mật khẩu. Vì thế, một HTTP response thành công không đủ chứng minh mọi secret đã được giải mã. Cần kiểm tra các key bắt buộc và hành vi khởi động của client.

## 10. Quản lý rollback trong giai đoạn chuyển đổi

Rollback cấu hình thường đưa ứng dụng về Git tag hoặc label trước đó. Nếu phiên bản đó chứa ciphertext v1, Config Server vẫn phải có khả năng giải mã v1 trong suốt thời gian phiên bản còn được hỗ trợ.

Trước khi loại alias cũ, kiểm tra:

- Các branch đang triển khai có còn ciphertext v1 không.
- Tag/release được dùng để rollback có còn ciphertext v1 không.
- Backup repository hoặc bản snapshot cấu hình có cần phục hồi không.
- Mọi Config Server instance đã có alias v2 và đã xác minh decrypt.
- Có quy trình khôi phục keystore hoặc key material được phê duyệt không.

Với rotation định kỳ, có thể giữ v1 trong keystore runtime đến hết rollback window, sau đó chuyển nó sang kho lưu trữ được kiểm soát hoặc hủy theo chính sách. Với khóa bị xâm phạm, không nên giữ nó hoạt động chỉ để tiện rollback; cần mã hóa lại các bản cấu hình được hỗ trợ và dùng secret mới trước khi thu hồi.

Rollback ứng dụng không đồng nghĩa rollback khóa. Nếu đã chuyển alias mặc định sang v2, bản cấu hình cũ phải mang metadata v1 rõ ràng hoặc được mã hóa lại bằng v2 để vẫn đọc được.

## 11. Xử lý khi khóa cũ bị lộ

Khi nghi ngờ private key hoặc khóa đối xứng đã bị lộ, ciphertext trong Git có thể bị giải mã nếu kẻ tấn công có cả ciphertext và khóa. Chỉ mã hóa lại cùng plaintext bằng khóa mới không thay thế credential thực tế.

Quy trình ứng phó nên gồm:

1. Thu hẹp quyền truy cập Config Server, keystore và repository; lưu bằng chứng cần thiết.
2. Xác định phạm vi ciphertext và secret có thể bị ảnh hưởng.
3. Tạo khóa mới trong hệ thống quản lý khóa được kiểm soát.
4. Thay credential thật ở hệ thống đích: database password, API token, signing secret hoặc certificate.
5. Mã hóa credential mới bằng khóa mới và cập nhật cấu hình.
6. Triển khai Config Server có khóa mới, xác minh client kết nối thành công.
7. Thu hồi credential cũ ở hệ thống đích.
8. Loại khóa cũ khỏi runtime khi các bản cấu hình cần hỗ trợ đã được chuyển đổi.
9. Kiểm tra log truy cập, audit và các bản sao có thể còn chứa ciphertext cũ.

Nếu có dấu hiệu khóa bị sử dụng trái phép, rotation phải được phối hợp với incident response của tổ chức. Giữ khóa cũ hoạt động quá lâu sẽ làm kéo dài thời gian rủi ro.

## 12. Bảo vệ key material và endpoint mã hóa

- Lưu keystore và mật khẩu trong secret manager, HSM hoặc secret volume có quyền truy cập tối thiểu.
- Không commit keystore, private key, mật khẩu keystore hoặc khóa đối xứng vào Git.
- Phân tách khóa giữa dev, staging và production; tránh dùng cùng key material ở mọi môi trường.
- Bảo vệ /encrypt và đặc biệt /decrypt bằng authentication, authorization, HTTPS và mạng quản trị.
- Hạn chế ai có thể gọi /decrypt; ghi audit danh tính, thời điểm và mục đích nhưng không ghi plaintext.
- Không đưa plaintext vào log ứng dụng, exception message, CI artifact hoặc shell history.
- Backup keystore được mã hóa và kiểm thử khả năng khôi phục theo quy trình.
- Giới hạn quyền đọc file keystore của tiến trình Config Server.
- Theo dõi thời hạn chứng thư, quyền truy cập và thay đổi alias.

Trong chế độ mặc định, Config Server giải mã property trước khi trả cho Config Client. Do đó, ciphertext được bảo vệ khi lưu trữ trong Git nhưng client được cấp quyền đọc cấu hình có thể nhận plaintext qua HTTP. Cần bảo vệ endpoint Config Server bằng HTTPS và authorization theo ứng dụng/nhóm dịch vụ. Encryption at rest không thay thế kiểm soát truy cập.

## 13. Lỗi thường gặp trong rotation

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Ciphertext cũ không giải mã sau khi đổi alias mặc định | Giá trị cũ không có tiền tố key và vẫn phụ thuộc alias cũ | Gắn {key:alias-cũ} trước khi đổi mặc định |
| Alias mới không được tìm thấy | Keystore triển khai chưa chứa key entry mới hoặc sai tên alias | Dùng keytool -list trên đúng keystore mà Config Server đang mount |
| Một Config Server giải mã được, node khác thất bại | Các instance dùng keystore hoặc cấu hình alias khác nhau | So sánh phiên bản keystore, alias, secret và rollout từng node |
| Property trả về marker invalid | Sai alias, sai key material hoặc ciphertext bị hỏng | Kiểm tra metadata key, log decrypt và ciphertext nguồn |
| /encrypt tạo ciphertext không đọc được | Request dùng alias chưa có hoặc cấu hình encryptor không khớp | Thử decrypt ngay trên Config Server bằng alias vừa dùng |
| Rollback về release cũ bị lỗi | Release cũ dùng khóa đã bị xóa | Giữ alias cũ trong rollback window hoặc mã hóa lại các release cần hỗ trợ |
| Khóa đối xứng mới không đọc được dữ liệu cũ | encrypt.key đã bị thay khi ciphertext cũ vẫn còn | Dùng locator nhiều khóa hoặc hoàn tất migration trước khi đổi key |
| Client khởi động nhưng thiếu password | Property decrypt thất bại hoặc key bị loại khỏi Environment | Kiểm tra key bắt buộc, response Environment và validation startup |
| Plaintext xuất hiện trong log | Script gọi /decrypt hoặc CI ghi response ra output | Rà soát pipeline, masking, quyền log và xóa artifact nhạy cảm theo incident procedure |

## 14. Checklist hoàn tất rotation

- [ ] Đã xác định loại khóa: keystore bất đối xứng hay encrypt.key đối xứng.
- [ ] Keystore có cả alias cũ và mới trong giai đoạn chuyển đổi.
- [ ] Config Server đọc được key entry và secret mở keystore.
- [ ] Ciphertext cũ đã được gắn alias tường minh nếu trước đó phụ thuộc alias mặc định.
- [ ] Ciphertext mới được tạo bằng alias mới.
- [ ] Tất cả Config Server instance đã được kiểm thử decrypt.
- [ ] Endpoint Environment trả property đã giải mã cho các application/profile/label cần thiết.
- [ ] Client thử nghiệm bind được các property bắt buộc.
- [ ] Các branch, tag, label và backup còn trong rollback window đã được rà soát.
- [ ] Không còn ciphertext dùng alias cũ trước khi thu hồi alias, trừ các bản lưu trữ đã có kế hoạch riêng.
- [ ] Credential thật đã được thay nếu rotation do sự cố lộ khóa.
- [ ] Endpoint /encrypt và /decrypt được bảo vệ và audit.
- [ ] Có bản ghi thời điểm chuyển alias, phạm vi dữ liệu và người phê duyệt.

Xoay vòng khóa thành công khi Config Server vẫn đọc được dữ liệu cũ trong thời gian chuyển đổi, mọi ciphertext mới dùng khóa mới và không còn phiên bản cấu hình đang được hỗ trợ phụ thuộc vào khóa đã thu hồi. Với keystore, tiền tố {key:alias} cho phép chọn khóa theo từng ciphertext; với khóa đối xứng đơn, cần locator tùy chỉnh hoặc một lần migration phối hợp. Luôn xác minh cả Config Server lẫn Config Client và tính đến các bản cấu hình cần dùng khi rollback.
