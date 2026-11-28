# Xử lý ciphertext hỏng, thiếu khóa và giá trị giải mã không hợp lệ

Spring Cloud Config có thể giải mã thuộc tính được đánh dấu bằng tiền tố `{cipher}` trước khi gửi Environment cho Config Client. Nhờ đó, repository Git có thể lưu ciphertext thay vì plaintext. Khi Config Server không giải mã được một giá trị, nó không nên âm thầm gửi ciphertext đó như thể đây là mật khẩu hợp lệ. Theo mặc định, server loại thuộc tính lỗi khỏi property source và thêm một thuộc tính có tên bắt đầu bằng `invalid` cùng giá trị thường là `<n/a>`.

Thông báo `invalid.*` là tín hiệu cần điều tra ngay. Nguyên nhân có thể là ciphertext bị cắt hoặc thay đổi khi copy, Config Server không có khóa giải mã, keystore sai alias, hoặc giá trị được mã hóa bằng một khóa khác. Cần xác định đúng nguyên nhân trước khi sửa dữ liệu, bởi mã hóa lại bằng khóa không phù hợp có thể làm tình trạng khó khôi phục hơn.

## 1. Hiểu cách Config Server xử lý giá trị mã hóa

Trong mô hình server-side decryption, file cấu hình từ xa lưu giá trị dạng ciphertext với tiền tố `{cipher}`. Config Server đọc file, nhận diện tiền tố và giải mã bằng khóa hoặc `TextEncryptor` đã cấu hình. Khi thành công, plaintext được đưa vào Environment response trả cho client qua HTTP.

```mermaid
flowchart TD
    A[Git: property có giá trị {cipher}...] --> B[Config Server đọc application/profile/label]
    B --> C[Chọn encryptor và khóa]
    C --> D{Giải mã thành công?}
    D -->|Có| E[Property source chứa plaintext]
    D -->|Không| F[Loại property gốc khỏi source]
    F --> G[Thêm invalid.property = <n/a>]
    E --> H[Environment response]
    G --> H
    H --> I[Config Client]
```

Việc giải mã diễn ra ở Config Server trước khi client nhận cấu hình. Vì vậy, nếu client nhận một giá trị sai, hãy kiểm tra response và log ở Config Server trước khi kết luận lỗi nằm trong bean hoặc thư viện kết nối database.

## 2. Dấu hiệu `invalid.*` trong Environment response

Ví dụ repository có hai nguồn cấu hình:

```yaml
# application-production.yml
spring:
  datasource:
    password: '{cipher}ENCRYPTED_VALUE_FROM_PRODUCTION'
```

```yaml
# application.yml
spring:
  datasource:
    password: 'SAFE_FALLBACK_VALUE'
```

Nếu Config Server không giải mã được mật khẩu trong file production, response có thể chứa property source tương tự:

```json
{
  "propertySources": [
    {
      "name": "application-production.yml",
      "source": {
        "invalid.spring.datasource.password": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "spring.datasource.password": "SAFE_FALLBACK_VALUE"
      }
    }
  ]
}
```

Tên key trong ví dụ được rút gọn để minh họa. Hành vi quan trọng là property gốc bị lỗi giải mã được thay bằng key có tiền tố `invalid`. Khi client tra cứu `spring.datasource.password`, giá trị từ property source thấp hơn có thể trở thành giá trị được phân giải, như ví dụ fallback trong tài liệu Spring Cloud Config.

Đây là một nguy cơ vận hành: ứng dụng có thể khởi động thành công với fallback cũ hoặc không đúng môi trường, trong khi secret production mới không được dùng. Không xem việc ứng dụng vẫn kết nối được database là bằng chứng ciphertext đã được giải mã thành công.

Mặc định, `spring.cloud.config.server.encrypt.prefix-invalid-properties` bật hành vi thêm tiền tố `invalid`. Nếu đặt thuộc tính này thành `false`, Config Server giữ ciphertext dưới tên key gốc trong response. Khi đó client có thể nhận chuỗi ciphertext thay cho plaintext; điều này dễ khiến ciphertext bị dùng nhầm như password. Không tắt cơ chế đánh dấu lỗi chỉ để response trông giống cấu hình bình thường.

## 3. Phân loại nguyên nhân trước khi sửa

Không phải mọi lỗi giải mã đều có cùng nguyên nhân. Hãy phân loại theo dấu hiệu và kiểm tra từng lớp:

| Nhóm nguyên nhân | Ví dụ | Dấu hiệu thường gặp |
|---|---|---|
| Ciphertext hỏng | Bị cắt, thiếu ký tự, dính newline hoặc ký tự thừa | Lỗi giải mã/định dạng, Base64 không hợp lệ hoặc kết quả không thể xác thực |
| Sai khóa đối xứng | Mã hóa bằng `ENCRYPT_KEY` khác khóa Config Server hiện dùng | Ciphertext có vẻ đúng định dạng nhưng giải mã thất bại |
| Thiếu private key | Config Server chỉ có public key hoặc không mount private keystore | Mã hóa được nhưng server không giải mã được |
| Sai keystore/alias | Sai đường dẫn, password, alias hoặc loại keystore | Không mở được keystore, không tìm thấy key hoặc lỗi chọn encryptor |
| Sai key alias trong ciphertext | `{key:old-key}` nhưng server không có alias đó | Không tìm được khóa tương ứng cho ciphertext |
| Sai cú pháp file cấu hình | Thiếu `{cipher}`, quote sai trong properties, YAML parse sai | Server coi chuỗi là plaintext hoặc không nhận diện giá trị mã hóa |
| Sai nguồn/version | Client yêu cầu nhầm application, profile hoặc label | Một profile giải mã được, profile khác tạo `invalid.*` |
| Khác chế độ giải mã | Server/client-side decryption được cấu hình không như dự kiến | Response chứa ciphertext hoặc client nhận kết quả không như mô hình thiết kế |

Trước khi đổi khóa hoặc mã hóa lại, hãy xác minh application, profile, label và property source mà Config Server đang trả. Có thể client đang đọc một file hoặc tag khác với file nhóm vận hành vừa sửa.

## 4. Kiểm tra cú pháp ciphertext trong YAML và properties

Giá trị mã hóa cần có tiền tố `{cipher}` ngay trước ciphertext. Trong YAML, nên đặt toàn bộ giá trị trong dấu nháy để `{` không bị parser hiểu như cấu trúc flow mapping:

```yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}BASE64_CIPHERTEXT'
```

Trong `application.properties`, giá trị mã hóa không được bọc trong dấu nháy:

```properties
spring.datasource.username=app_user
spring.datasource.password={cipher}BASE64_CIPHERTEXT
```

Tài liệu Spring Cloud Config nêu rõ encrypted value trong file `.properties` không được bọc trong quotes; nếu có dấu nháy, server có thể không giải mã giá trị đó. Với YAML, ví dụ tài liệu đặt chuỗi `{cipher}...` trong quotes.

Các lỗi format cần kiểm tra:

- Thiếu tiền tố `{cipher}` hoặc gõ sai chính tả.
- Có khoảng trắng trước tiền tố hoặc ký tự thừa sau ciphertext.
- Copy thiếu một phần cuối chuỗi hoặc dính dấu nháy vào giá trị.
- Ciphertext bị xuống dòng ngoài ý muốn.
- Giá trị trong properties bị đặt trong quotes.
- Ciphertext được copy từ output có kèm thống kê hoặc thông báo của terminal.

Không tự cắt, nối hoặc thay ký tự Base64 để “làm cho chuỗi hợp lệ”. Ciphertext phải được tạo lại từ plaintext nguồn bằng đúng quy trình và khóa đã xác định.

## 5. Kiểm tra khóa đối xứng

Với khóa đối xứng, Config Server dùng cùng một secret key để mã hóa và giải mã. Cấu hình thường dùng:

```yaml
encrypt:
  key: ${ENCRYPT_KEY}
```

`ENCRYPT_KEY` phải được cấp từ secret manager hoặc môi trường triển khai an toàn. Không commit khóa vào Git config repository, không ghi nó vào log và không chia sẻ qua ticket/chat.

Nếu ứng dụng có `spring-cloud-starter-bootstrap` hoặc bật bootstrap legacy bằng `spring.cloud.bootstrap.enabled=true`, tài liệu Spring Cloud Config yêu cầu đặt `encrypt.key` trong `bootstrap.properties`/`bootstrap.yml` cho mô hình bootstrap đó. Với Config Data hiện đại, cần xác định rõ nơi cấu hình khóa được nạp trước khi mã hóa/giải mã và tuân theo phiên bản Spring Cloud đang dùng.

Các câu hỏi cần xác minh:

1. Config Server đang chạy có nhận đúng `ENCRYPT_KEY` không?
2. Giá trị được mã hóa ban đầu bằng đúng khóa hiện tại hay khóa cũ?
3. Có khác biệt giữa local, staging và production về secret injection không?
4. Tất cả replica Config Server có cùng bộ khóa cần thiết không?
5. Có ký tự xuống dòng hoặc khoảng trắng ngoài ý muốn trong secret được inject không?

Không in giá trị khóa để so sánh. Hãy xác minh nguồn secret, phiên bản secret hoặc fingerprint được quản lý bởi hệ thống secret manager theo quy trình nội bộ. Nếu không xác định được khóa cũ, hãy khôi phục từ secret store có kiểm soát hoặc xoay secret gốc theo quy trình nghiệp vụ; không thử nhiều khóa ngẫu nhiên trên production.

## 6. Kiểm tra RSA keystore và private key

Với mã hóa bất đối xứng, Config Server có thể dùng keystore chứa cặp khóa RSA. Dữ liệu được mã hóa bằng public key; cần private key tương ứng để giải mã.

Ví dụ cấu hình YAML:

```yaml
encrypt:
  key-store:
    location: file:/run/secrets/config-server.p12
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-server
    type: PKCS12
```

Các thuộc tính cần kiểm tra:

| Thuộc tính | Câu hỏi chẩn đoán |
|---|---|
| `encrypt.key-store.location` | File có tồn tại trong filesystem/container của Config Server không? |
| `encrypt.key-store.password` | Secret có mở được keystore không? |
| `encrypt.key-store.alias` | Alias có tồn tại và trỏ tới đúng key entry không? |
| `encrypt.key-store.type` | Loại keystore có khớp file thực tế, ví dụ JKS hoặc PKCS12, không? |

Lưu ý: nếu server chỉ có public key thì server có thể mã hóa nhưng không thể giải mã ciphertext cần private key. Với server-side decryption, phải bảo đảm private key phù hợp có mặt và có thể truy cập được.

Trong môi trường container, đường dẫn trên host không nhất thiết là đường dẫn mà process nhìn thấy. Kiểm tra mount, quyền đọc, UID/GID, secret volume và việc file có được mount vào mọi replica hay không. Không copy keystore/private key vào repository hoặc image công khai.

## 7. Kiểm tra key alias trong ciphertext

Khi dùng nhiều key, ciphertext có thể chứa metadata prefix để chọn alias:

```yaml
service:
  api-token: '{cipher}{key:config-key-2026}BASE64_CIPHERTEXT'
```

Config Server dùng `{key:...}` để tìm alias tương ứng trong keystore thông qua `TextEncryptorLocator`. Nếu alias không tồn tại, sai chính tả hoặc không trỏ tới key phù hợp, giải mã sẽ thất bại.

Checklist:

- Alias trong `{key:...}` khớp chính xác alias trong keystore.
- Alias đó tồn tại trên tất cả Config Server replica.
- Key entry có private key nếu server cần giải mã.
- Ciphertext được tạo bằng đúng key alias được khai báo.
- Nếu dùng `TextEncryptorLocator` tùy chỉnh, logic chọn key phù hợp với metadata trong ciphertext.

Không xóa alias cũ ngay sau khi tạo alias mới. Các ciphertext cũ vẫn cần khóa cũ cho đến khi mọi property đã được mã hóa lại và mọi client/label liên quan đã chuyển sang phiên bản mới.

## 8. Kiểm tra an toàn bằng `/decrypt`

Config Server cung cấp endpoint `/decrypt` để kiểm tra ciphertext nếu server có khóa hoặc key pair phù hợp. Đây là endpoint nhạy cảm vì response chứa plaintext. Chỉ người vận hành được ủy quyền mới được sử dụng; cần bảo vệ bằng TLS, authentication, authorization và mạng quản trị.

Khi kiểm tra:

1. Lấy ciphertext chính xác từ file/label đang được Config Server phục vụ.
2. Bỏ tiền tố `{cipher}` khi gửi phần ciphertext tới `/decrypt` theo cách endpoint mong đợi.
3. Gửi body dạng text thuần để tránh biến đổi ký tự `+` hoặc ký tự đặc biệt.
4. Ghi response plaintext vào vùng tạm có quyền truy cập hạn chế.
5. Không in plaintext vào terminal, CI log, chat hoặc ticket.
6. Xóa file tạm theo chính sách lưu trữ sau khi xác minh.

Ví dụ dưới đây dùng file tạm; các file phải được tạo trong vùng bảo vệ và không được upload thành artifact:

```bash
umask 077
curl --fail --silent --show-error \
  --request POST \
  --header 'Content-Type: text/plain' \
  --data-binary @ciphertext.txt \
  --output decrypted-check.txt \
  https://config-server.internal/decrypt
```

`ciphertext.txt` chỉ chứa ciphertext chính xác, không chứa `{cipher}` nếu endpoint được gọi theo dạng ví dụ tài liệu. `decrypted-check.txt` chứa plaintext; không dùng `cat` hoặc đính kèm file này vào ticket. Nếu cần gửi dữ liệu có ký tự đặc biệt qua form encoding, tài liệu Spring gợi ý dùng `--data-urlencode` đúng cách hoặc đặt `Content-Type: text/plain` để tránh ký tự `+` bị diễn giải thành dấu cách.

Nếu `/decrypt` thất bại, hãy đối chiếu loại khóa, alias, cấu hình keystore và nguồn ciphertext. Nếu `/decrypt` thành công nhưng Environment response vẫn có `invalid.*`, kiểm tra Config Server replica khác, label khác, property source khác hoặc cấu hình `TextEncryptorLocator` mà request Environment thực tế đang sử dụng.

## 9. Dùng `/encrypt` để tạo lại ciphertext

Sau khi xác minh khóa và plaintext nguồn, có thể dùng `/encrypt` của Config Server để tạo ciphertext mới. Endpoint này cũng nhạy cảm vì request chứa plaintext và response chứa ciphertext; chỉ gọi qua kênh quản trị được bảo vệ.

Ví dụ an toàn hơn là đọc plaintext từ file tạm có quyền truy cập hạn chế và ghi ciphertext vào file riêng:

```bash
umask 077
curl --fail --silent --show-error \
  --request POST \
  --header 'Content-Type: text/plain' \
  --data-binary @plaintext-secret.txt \
  --output ciphertext-new.txt \
  https://config-server.internal/encrypt
```

`plaintext-secret.txt` không được lưu trong repository, shell history, thư mục chia sẻ hoặc CI artifact. `ciphertext-new.txt` là output để đưa vào file cấu hình sau khi kiểm tra định dạng; cần thêm tiền tố `{cipher}` trước khi commit. Không sao chép output có kèm progress/statistics của curl vào repository.

Nếu plaintext chứa ký tự đặc biệt, đặc biệt là `+`, dùng body text thuần hoặc encoding đúng theo hướng dẫn để tránh mã hóa nhầm nội dung đã bị biến đổi. Không dùng ví dụ với mật khẩu thật trong lệnh hiển thị hoặc tài liệu công khai.

## 10. Phân biệt server-side và client-side decryption

Mô hình mặc định thường là Config Server giải mã giá trị trước khi gửi Environment cho client. Trong một số kiến trúc, tổ chức muốn client tự giải mã. Khi đó, Config Server có thể giữ ciphertext trong response bằng cách tắt giải mã outgoing properties với:

```yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
```

Đây là lựa chọn kiến trúc riêng, cần thiết kế khóa và quyền giải mã cho client. Không nhầm thuộc tính này với `prefix-invalid-properties=false`:

| Thuộc tính | Mục đích |
|---|---|
| `spring.cloud.config.server.encrypt.enabled=false` | Không giải mã outgoing properties ở server để client có thể nhận ciphertext theo kiến trúc client-side decryption |
| `spring.cloud.config.server.encrypt.prefix-invalid-properties=false` | Khi server giải mã thất bại, không đổi tên property thành `invalid.*`; ciphertext có thể còn dưới key gốc |

Không tắt prefix-invalid chỉ để làm mất dấu lỗi. Nếu thiết kế client-side decryption, phải cấu hình rõ ràng cách client lấy khóa, giải mã, bảo vệ khóa và xử lý lỗi. Việc phân phối private key tới nhiều client làm tăng phạm vi ảnh hưởng khi một client bị xâm nhập.

## 11. Xử lý fallback và ngăn ứng dụng dùng giá trị sai

Khi một property bị đổi tên thành `invalid.<key>`, property gốc trong source lỗi không còn được cung cấp dưới tên ban đầu. Một source có độ ưu tiên thấp hơn có thể cung cấp cùng key, khiến client dùng fallback.

Đối với secret quan trọng như database password, API token hoặc signing key, không nên để fallback plaintext hoặc giá trị mặc định yếu có thể được dùng âm thầm. Hãy kiểm tra rõ các điều kiện:

- Response không có `invalid.<secret-key>`.
- Secret key bắt buộc tồn tại trong Environment cuối.
- Giá trị đến từ property source/label được phê duyệt.
- Ứng dụng không khởi động hoặc không nhận traffic nếu secret bắt buộc thiếu hoặc sai.
- Không log giá trị secret để xác minh.

Có thể thêm startup validation để yêu cầu property bắt buộc có mặt và có định dạng phù hợp. Validation chỉ kiểm tra sự hiện diện/định dạng hoặc thử kết nối theo cách an toàn; không in secret ra exception hoặc log.

## 12. Quy trình khôi phục theo từng tình huống

| Tình huống | Hành động khôi phục |
|---|---|
| Ciphertext bị cắt hoặc thay đổi | Lấy plaintext từ nguồn bí mật có thẩm quyền, mã hóa lại bằng key đang hoạt động, cập nhật file và review |
| Config Server thiếu symmetric key | Khôi phục đúng secret từ secret manager hoặc triển khai lại secret đúng phiên bản; sau đó kiểm tra tất cả replica |
| Sai symmetric key | Xác định key đã mã hóa ciphertext; khôi phục key tương ứng hoặc re-encrypt toàn bộ giá trị theo key chuẩn |
| Thiếu private key/keystore | Khôi phục keystore đúng, mount vào runtime, xác minh password và alias; không thay bằng public key đơn lẻ để giải mã |
| Sai `{key:alias}` | Sửa alias sau khi xác nhận key tương ứng hoặc re-encrypt với alias chuẩn |
| Sai cú pháp YAML/properties | Sửa quoting/prefix theo đúng loại file, kiểm tra parser và yêu cầu Config Server đọc lại |
| Client nhận fallback không mong muốn | Loại bỏ fallback yếu, thêm validation bắt buộc và phát hành cấu hình đã xác minh |
| Không còn khóa cũ | Tìm bản sao khóa được lưu trữ có kiểm soát; nếu không thể khôi phục, lấy lại secret gốc từ nguồn có thẩm quyền và mã hóa lại bằng khóa mới |

Không ghi đè ciphertext hỏng bằng một chuỗi khác do tự chỉnh sửa. Giữ nguyên commit lỗi để audit, tạo commit sửa có liên kết sự cố và kiểm tra lại trên staging trước khi phát hành production.

## 13. Xoay khóa mà không làm gián đoạn cấu hình

Khi khóa cũ cần thay thế, ví dụ bị lộ hoặc chính sách bảo mật yêu cầu, cần lập kế hoạch để Config Server có thể giải mã cả ciphertext cũ trong thời gian chuyển đổi.

Một quy trình tổng quát:

1. Tạo key/alias mới và lưu trong secret manager hoặc keystore được bảo vệ.
2. Triển khai key mới lên tất cả Config Server replica; giữ key cũ còn khả dụng để giải mã dữ liệu hiện tại.
3. Xác minh alias mới tồn tại và có thể được chọn bởi `TextEncryptorLocator`.
4. Mã hóa lại từng secret bằng key mới; cập nhật metadata prefix như `{key:new-alias}` nếu dùng nhiều key.
5. Commit thay đổi, kiểm thử staging và xác nhận response không còn `invalid.*`.
6. Promote cùng phiên bản cấu hình sang production và kiểm tra ứng dụng dùng đúng secret.
7. Chỉ gỡ key cũ sau khi xác nhận không còn ciphertext nào cần key đó ở các branch, tag, profile và label còn được phục vụ.

Nếu khóa cũ bị lộ, cần phối hợp rotation secret nghiệp vụ ở database/API provider. Đổi khóa mã hóa ciphertext không tự đổi mật khẩu database hoặc thu hồi token đã bị lộ. Hãy rotate cả credential gốc theo quy trình của hệ thống đích.

## 14. Bảo vệ endpoint và log giải mã

`/encrypt` và đặc biệt `/decrypt` có thể nhận/trả plaintext. Cần:

- Chỉ cho phép danh tính vận hành được chỉ định gọi endpoint.
- Bắt buộc HTTPS, authentication và authorization.
- Giới hạn endpoint trong mạng quản trị hoặc gateway nội bộ.
- Không ghi request body, response body, plaintext, private key hoặc password keystore vào log.
- Không để reverse proxy/APM ghi payload nhạy cảm.
- Giới hạn kích thước request và theo dõi truy cập bất thường.
- Ghi audit ai thực hiện, lúc nào, với application/profile nào nhưng không ghi secret.
- Cất key và keystore ngoài Git; cấp quyền tối thiểu cho process Config Server.

Nếu không cần API mã hóa/giải mã từ xa, cân nhắc không expose chúng qua mạng truy cập chung. Đừng dựa vào việc URL khó đoán như một biện pháp bảo mật.

## 15. Ma trận chẩn đoán

| Quan sát | Kiểm tra tiếp theo | Kết luận có thể |
|---|---|---|
| Config Server response có `invalid.db.password` | Kiểm tra ciphertext, key, alias và log decrypt của server | Server không giải mã được property ở source đó |
| `/decrypt` cũng thất bại với ciphertext chính xác | Kiểm tra loại khóa, key version, alias và định dạng | Ciphertext không tương thích với key/encryptor đang dùng hoặc bị hỏng |
| `/decrypt` thành công nhưng Environment có `invalid.*` | Kiểm tra replica, label, profile, property source và locator | Request Environment có thể đi qua cấu hình/replica khác |
| Environment không có `invalid.*` nhưng ứng dụng vẫn dùng secret cũ | Kiểm tra property source precedence, fallback và client refresh | Client có thể đang dùng giá trị từ source khác hoặc chưa refresh |
| Environment chứa chuỗi ciphertext dưới key gốc | Kiểm tra `prefix-invalid-properties`, `encrypt.enabled` và client-side mode | Cần phân biệt chế độ giữ ciphertext có chủ đích với lỗi decrypt bị che dấu |
| Chỉ production lỗi, staging thành công | So sánh profile/label, key injection và keystore alias ở production | Môi trường production có cấu hình khóa hoặc nguồn khác |
| Một replica lỗi, replica khác thành công | So sánh secret version, mount, alias và cấu hình runtime | Các Config Server replica không đồng nhất |

## 16. Checklist trước khi đóng sự cố

- [ ] Đã xác định đúng application, profile, label và property source.
- [ ] Đã kiểm tra response có `invalid.*` mà không in plaintext/ciphertext nhạy cảm.
- [ ] Đã xác minh `{cipher}` prefix và cú pháp YAML/properties.
- [ ] Đã xác minh symmetric key hoặc keystore/private key có mặt và đúng phiên bản.
- [ ] Đã kiểm tra alias trong ciphertext khớp alias trong keystore.
- [ ] Đã kiểm tra tất cả Config Server replica dùng cùng bộ khóa cần thiết.
- [ ] Đã dùng `/decrypt` trong môi trường quản trị an toàn nếu cần xác minh ciphertext.
- [ ] Đã loại bỏ fallback yếu hoặc bổ sung validation để secret thiếu không bị bỏ qua.
- [ ] Đã re-encrypt bằng khóa đúng và cập nhật Git qua pull request.
- [ ] Đã kiểm thử staging và xác nhận không còn `invalid.*` trước production.
- [ ] Đã bảo vệ endpoint, log, secret manager và file tạm chứa plaintext.
- [ ] Nếu rotation do lộ khóa, đã đánh giá cả việc rotate credential gốc.

## 17. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích vì sao Config Server tạo `invalid.<property>` khi giải mã thất bại.
- Phân biệt ciphertext hỏng, thiếu/sai symmetric key, lỗi keystore/private key và alias không tồn tại.
- Kiểm tra đúng cú pháp `{cipher}` trong YAML và properties.
- Dùng `/decrypt` và `/encrypt` an toàn để xác minh hoặc tạo lại ciphertext.
- Nhận diện nguy cơ fallback khi property bị loại khỏi source lỗi.
- Phân biệt `prefix-invalid-properties` với chế độ client-side decryption.
- Khôi phục ciphertext và khóa theo quy trình có kiểm soát.
- Lập kế hoạch key rotation và xác minh mọi Config Server replica.

**Tự kiểm tra:** Config Server trả `invalid.spring.datasource.password` ở profile production, trong khi `application.yml` có một password mặc định. Hãy nêu các bước kiểm tra ciphertext, symmetric key/keystore alias, giải thích giá trị nào client có thể nhận, cách dùng `/decrypt` an toàn và cách phát hành bản sửa mà không để fallback yếu được dùng âm thầm.

## Tài liệu tham khảo

- [Spring Cloud Config — Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
- [Spring Cloud Config — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html)
- [Spring Cloud Config — Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html)
- [Spring Cloud Config — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html)
