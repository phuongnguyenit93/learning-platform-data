# Mã hóa đối xứng bằng `encrypt.key`

Spring Cloud Config cho phép lưu giá trị cấu hình nhạy cảm dưới dạng ciphertext trong repository hoặc backend từ xa. Với mã hóa đối xứng, Config Server dùng cùng một bí mật để mã hóa và giải mã. Thuộc tính `encrypt.key` cung cấp bí mật đó; biến môi trường `ENCRYPT_KEY` là cách thuận tiện để cấp khóa khi triển khai mà không ghi nó vào file cấu hình.

Khi repository chứa một property bắt đầu bằng `{cipher}`, Config Server mặc định giải mã giá trị trước khi trả property source cho Config Client. Nhờ vậy, Git chỉ lưu ciphertext, còn ứng dụng nhận giá trị rõ qua kết nối HTTP được bảo vệ. Cơ chế này bảo vệ dữ liệu khi lưu trữ trong repository; nó không thay thế TLS, xác thực, phân quyền hoặc một hệ thống quản lý secret chuyên dụng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách mã hóa đối xứng dùng chung một khóa trong Spring Cloud Config.
- Cấu hình `encrypt.key` hoặc cấp khóa qua `ENCRYPT_KEY`.
- Mã hóa và giải mã giá trị bằng endpoint `/encrypt` và `/decrypt`.
- Đặt tiền tố `{cipher}` đúng cách trong YAML và properties.
- Hiểu Config Server giải mã property source trước khi gửi cho client.
- Nhận biết phản hồi khi giải mã thất bại và kiểm tra giá trị fallback.
- Bảo vệ khóa, endpoint mã hóa/giải mã và quy trình luân chuyển khóa.

## Mã hóa đối xứng hoạt động như thế nào?

Mã hóa đối xứng sử dụng cùng một bí mật cho cả hai chiều:

- Khi mã hóa, hệ thống dùng khóa bí mật và plaintext để tạo ciphertext.
- Khi giải mã, hệ thống dùng chính khóa đó và ciphertext để khôi phục plaintext.

Trong Spring Cloud Config, Config Server giữ `encrypt.key`. Người có khóa có thể giải mã dữ liệu đã mã hóa bằng khóa đó, vì vậy khóa cần được bảo vệ như một credential có quyền đọc tất cả giá trị ciphertext được mã hóa bằng nó.

```mermaid
flowchart TD
    P[Plaintext: giá trị cấu hình nhạy cảm] --> E[Config Server /encrypt]
    K[encrypt.key: khóa bí mật] --> E
    E --> C[Ciphertext]
    C --> R[Git hoặc repository cấu hình]
    R --> S[Config Server đọc property {cipher}...]
    K --> D[Config Server giải mã]
    S --> D
    D --> H[Plaintext trong phản hồi Config Server]
    H --> L[Config Client qua HTTPS]
```

Khóa không được lưu cùng ciphertext trong Git. Nếu người đọc repository đồng thời lấy được `encrypt.key`, lớp bảo vệ dữ liệu khi lưu trữ không còn ý nghĩa. Cũng không dùng `encrypt.key` làm mật khẩu database, token dịch vụ hoặc khóa TLS; mỗi mục đích cần credential riêng.

## Cấu hình `encrypt.key`

Trên Config Server, `encrypt.key` là một chuỗi bí mật. Có thể khai báo qua placeholder:

```yaml
encrypt:
  key: ${ENCRYPT_KEY}
```

Khi triển khai, nền tảng cấp `ENCRYPT_KEY` từ secret manager, Kubernetes Secret được bảo vệ, workload secret injection hoặc cơ chế tương đương. Không thay placeholder bằng giá trị khóa thật rồi commit file vào Git.

Spring Boot cũng ánh xạ trực tiếp biến môi trường `ENCRYPT_KEY` thành thuộc tính `encrypt.key`; do đó có thể chỉ cấp biến môi trường mà không cần khai báo thuộc tính trong YAML. Ví dụ tên biến:

```text
ENCRYPT_KEY=<secret được cấp tại runtime>
```

Hãy dùng một giá trị ngẫu nhiên có entropy cao được tạo và lưu bởi hệ thống quản lý bí mật. Không dùng câu dễ đoán, mật khẩu dùng lại, tên công ty hoặc chuỗi có trong repository. Ví dụ dưới đây chỉ là lệnh tạo giá trị ngẫu nhiên để tham khảo, không phải khóa để đưa vào tài liệu hoặc commit:

```bash
openssl rand -base64 32
```

Giới hạn quyền đọc secret ở tài khoản chạy Config Server và nhóm vận hành có trách nhiệm. Bảo vệ cả pipeline, deployment manifest, log và nơi lưu backup; việc dùng biến môi trường chỉ tránh hard-code trong file, không tự động làm cho mọi nơi trong runtime đều an toàn.

### Trường hợp dùng bootstrap legacy

Nếu Config Server bật bootstrap context bằng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`, tài liệu Spring Cloud Config yêu cầu đặt `encrypt.key` trong `bootstrap.properties` để khóa có sẵn ở giai đoạn bootstrap. Nếu server dùng Config Data API hiện đại, cấp thuộc tính theo cơ chế cấu hình khởi động tương ứng của phiên bản đang chạy.

Điểm này áp dụng cho chính ứng dụng Config Server. Không nhầm file bootstrap của Config Client với nơi lưu khóa mã hóa phía server.

## Mã hóa một giá trị bằng `/encrypt`

Config Server cung cấp endpoint:

```text
POST /encrypt
```

Endpoint nhận plaintext trong request body và trả ciphertext. Ví dụ với một giá trị giả lập không nhạy cảm:

```bash
curl --fail --silent --show-error \
  -H "Content-Type: text/plain" \
  --data-binary "sample-value-only" \
  http://localhost:8888/encrypt
```

Phản hồi là ciphertext, thường được biểu diễn bằng chuỗi ký tự Base64. Endpoint không tự sửa repository, không tự thêm `{cipher}` vào file và không commit kết quả. Người phát hành cấu hình cần lấy ciphertext rồi đặt nó vào đúng property trong file cấu hình.

Nếu plaintext chứa dấu `+`, `&`, ký tự Unicode hoặc ký tự có ý nghĩa đặc biệt trong form encoding, hãy bảo đảm request body được gửi như `text/plain` hoặc dùng `--data-urlencode` theo hướng dẫn curl. Không để curl trộn thống kê tiến trình vào ciphertext; dùng `--silent` và `--show-error` để output chỉ chứa dữ liệu cần xử lý.

Không đưa secret production trực tiếp vào command line hoặc shell history trên máy dùng chung. Ví dụ trên dùng giá trị giả. Trong quy trình thật, hãy dùng công cụ nội bộ có kiểm soát quyền, truyền dữ liệu qua kênh được bảo vệ và hạn chế nơi ciphertext/plaintext xuất hiện.

## Giải mã bằng `/decrypt`

Endpoint tương ứng:

```text
POST /decrypt
```

Ví dụ với ciphertext giả lập:

```bash
curl --fail --silent --show-error \
  -H "Content-Type: text/plain" \
  --data-binary "<ciphertext>" \
  http://localhost:8888/decrypt
```

Nếu ciphertext được tạo bằng khóa hiện tại và đúng định dạng, Config Server trả plaintext. Nếu khóa không khớp, ciphertext bị hỏng hoặc thuật toán/định dạng không tương thích, thao tác giải mã thất bại.

`/decrypt` nhạy cảm hơn `/encrypt`: người gọi có thể gửi ciphertext và nhận lại dữ liệu rõ. Chỉ cho phép nhóm phát hành hoặc vận hành được ủy quyền sử dụng endpoint này. Trong nhiều môi trường production, có thể không cần mở endpoint `/decrypt` cho người dùng; hãy giới hạn bằng Spring Security, gateway và network policy.

## Đưa ciphertext vào repository bằng `{cipher}`

Sau khi mã hóa, thêm tiền tố `{cipher}` vào trước ciphertext. Config Server nhận biết tiền tố này để giải mã property khi đọc nguồn cấu hình.

### Trong YAML

Giá trị cần đặt trong dấu nháy vì `{...}` có ý nghĩa cú pháp trong YAML:

```yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}AQB...ciphertext...'
```

### Trong `.properties`

Không đặt giá trị mã hóa trong dấu nháy. Tài liệu Spring Cloud Config lưu ý dấu nháy có thể khiến property không được nhận diện để giải mã:

```properties
spring.datasource.username=app_user
spring.datasource.password={cipher}AQB...ciphertext...
```

Ciphertext trong ví dụ chỉ là phần giữ chỗ. Khi phát hành, phải thay bằng toàn bộ kết quả trả về từ `/encrypt`; không tự cắt chuỗi, thêm khoảng trắng hoặc xuống dòng vào giữa ciphertext.

Sau đó commit file đã chứa ciphertext vào repository theo quy trình review bình thường. Người đọc repository nhìn thấy ciphertext thay vì plaintext, nhưng vẫn cần bảo vệ repository vì nó có thể chứa metadata, endpoint nội bộ và các cấu hình không mã hóa khác.

## Config Server giải mã trước khi trả cho Config Client

Theo mặc định, khi remote property source chứa giá trị bắt đầu bằng `{cipher}`, Config Server giải mã trước khi gửi phản hồi HTTP. Client nhận giá trị rõ trong `Environment` và có thể bind nó vào `@ConfigurationProperties` hoặc dùng trong auto-configuration.

Luồng mặc định:

1. Nhóm phát hành mã hóa secret bằng `/encrypt`.
2. Ciphertext có tiền tố `{cipher}` được commit vào Git.
3. Config Server đọc file theo application, profile và label.
4. Config Server giải mã property bằng `encrypt.key`.
5. Config Server gửi property source đã giải mã cho Config Client qua kết nối HTTP/TLS.
6. Ứng dụng dùng plaintext trong runtime; không cần biết `encrypt.key`.

Điều này tập trung quyền giải mã ở Config Server và tránh phân phối cùng một khóa đối xứng đến tất cả client. Tuy nhiên, plaintext vẫn tồn tại trong bộ nhớ client và được truyền từ server đến client; vì vậy phải bật TLS, xác thực client, phân quyền theo application/profile và tránh ghi giá trị vào log.

### Trường hợp client tự giải mã

Spring Cloud Config có thể được cấu hình để server giữ ciphertext khi trả property source, để client giải mã cục bộ. Khi dùng mô hình này, cần đặt:

```yaml
# bootstrap.yml của Config Server khi dùng bootstrap context
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
```

Theo tài liệu Spring Cloud Config hiện hành, đặt thuộc tính này trong `bootstrap.yml` hoặc `bootstrap.properties` của Config Server. Kiểm tra hướng dẫn của release train đang dùng nếu ứng dụng đã chuyển hoàn toàn sang Config Data.

Thuộc tính này tắt giải mã các property gửi đi; nó không có nghĩa là mã hóa đầu vào hoặc endpoint `/encrypt` và `/decrypt` tự động bị tắt. Client phải có khả năng truy cập khóa để giải mã. Với mã hóa đối xứng, điều đó đồng nghĩa phải phân phối cùng secret đến các client, làm tăng số nơi có quyền giải mã. Chỉ chọn mô hình này khi có yêu cầu kiến trúc rõ ràng và có kế hoạch bảo vệ khóa trên từng workload.

## Xử lý lỗi giải mã

Nếu Config Server không giải mã được property, nó loại property gốc khỏi property source và thêm một property có tên được đặt tiền tố `invalid`. Giá trị thường là `<n/a>`. Cách xử lý này nhằm tránh việc ciphertext vô tình được dùng như password hoặc credential trong ứng dụng.

Ví dụ phản hồi rút gọn:

```json
{
  "propertySources": [
    {
      "name": "order-service-prod.yml",
      "source": {
        "invalid.spring.datasource.password": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "spring.datasource.password": "local-placeholder"
      }
    }
  ]
}
```

Nếu client có một property cùng tên ở nguồn có độ ưu tiên thấp hơn, ứng dụng có thể nhận giá trị đó thay vì ciphertext bị lỗi. Vì vậy, một ứng dụng vẫn khởi động được không chứng minh secret đã được giải mã đúng. Cần kiểm tra property source và giá trị hiệu lực trong môi trường thử nghiệm.

Có thể tắt hành vi thêm tiền tố `invalid` bằng:

```yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          prefix-invalid-properties: false
```

Khi tắt, Config Server có thể gửi ciphertext dưới tên property gốc. Điều này dễ khiến ứng dụng dùng chuỗi mã hóa như password thật; vì vậy chỉ thay đổi hành vi mặc định khi đã hiểu rõ tác động và có cơ chế phát hiện lỗi phù hợp.

### Các nguyên nhân giải mã thất bại

| Hiện tượng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| Property xuất hiện dưới tên `invalid.*` | Khóa server không khớp ciphertext hoặc ciphertext hỏng | Kiểm tra `ENCRYPT_KEY`, giá trị ciphertext và log server |
| `/decrypt` trả lỗi | Gửi nhầm plaintext, sai body encoding hoặc khóa không đúng | Kiểm tra Content-Type, ký tự đặc biệt và key đang nạp |
| Client nhận chuỗi mã hóa thay vì secret | Prefix sai, file properties đặt dấu nháy hoặc server không giải mã | Kiểm tra `{cipher}`, cú pháp file và `server.encrypt.enabled` |
| Server khởi động nhưng không có chức năng giải mã | Khóa chưa được cấp đúng thời điểm hoặc cấu hình bootstrap không đúng | Kiểm tra property `encrypt.key` trong context khởi động của Config Server |
| Một instance giải mã được, instance khác không | Các Config Server replica đang dùng khóa khác nhau | Đồng bộ secret version và restart/rollout tất cả replica theo kế hoạch |

## Bảo vệ khóa và endpoint

Mã hóa chỉ có ích khi khóa được bảo vệ tốt hơn ciphertext. Các nguyên tắc sau cần được áp dụng:

- **Không commit khóa:** không lưu `encrypt.key`, `ENCRYPT_KEY` hoặc bản sao khóa trong Git, image, Dockerfile hay manifest công khai.
- **Cấp từ secret manager:** chỉ workload Config Server được quyền đọc khóa; hạn chế quyền truy cập thủ công và audit việc lấy secret.
- **Đồng bộ replica:** mọi Config Server instance phục vụ cùng một tập ciphertext phải dùng khóa tương thích. Quản lý version khóa thống nhất trong rollout.
- **Bảo vệ `/encrypt` và `/decrypt`:** yêu cầu TLS, xác thực, phân quyền và giới hạn mạng. Đặc biệt giới hạn `/decrypt` vì endpoint trả plaintext.
- **Bảo vệ API cấu hình:** Config Client chỉ được đọc đúng application/profile cần thiết; không cho mọi client truy cập toàn bộ cấu hình production.
- **Không log plaintext:** tránh log request body, response body, exception chứa secret hoặc dump `Environment`.
- **Giới hạn quyền đọc repository:** ciphertext vẫn cần kiểm soát truy cập và kiểm tra lịch sử commit.
- **Bảo vệ backup:** bản sao lưu chứa khóa và repository phải được bảo vệ riêng, không gom khóa vào cùng nơi với ciphertext.

Endpoint `/encrypt` và `/decrypt` không nên được xem như API công khai cho mọi developer. Tạo một quy trình phát hành secret có kiểm soát: người được phép gửi giá trị, nhận ciphertext và cập nhật repository; người đọc repository không mặc nhiên có quyền gọi `/decrypt`.

Nếu một secret từng được commit ở dạng plaintext, mã hóa commit mới không xóa plaintext khỏi lịch sử Git, clone, fork, cache CI hoặc backup. Hãy coi credential đó là đã lộ: rotate credential tại hệ thống đích trước, sau đó làm sạch lịch sử repository nếu chính sách yêu cầu và rà soát các bản sao có thể đã nhận nội dung.

## Một khóa cho nhiều ứng dụng và profile

Mặc định, `TextEncryptorLocator` của Config Server dùng cùng một key cho các lần mã hóa. Endpoint `/encrypt` và `/decrypt` hỗ trợ path có application và profile để thiết kế mã hóa theo context, nhưng muốn dùng encryptor khác nhau cho từng ứng dụng/profile thì cần cung cấp bean `TextEncryptorLocator` tùy chỉnh.

Ví dụ endpoint có context:

```text
POST /encrypt/{application}/{profiles}
POST /decrypt/{application}/{profiles}
```

Để các endpoint theo application/profile thực sự chọn encryptor riêng, hãy cung cấp bean `TextEncryptorLocator` tùy chỉnh. Locator mặc định vẫn dùng cùng một khóa cho mọi application/profile. Nếu cần tách khóa theo môi trường hoặc ứng dụng, hãy triển khai locator có quy tắc rõ ràng, quản lý từng khóa bằng secret manager và kiểm thử việc chọn đúng key trước khi phát hành.

Tách khóa giúp giới hạn phạm vi ảnh hưởng khi một khóa bị lộ, nhưng tăng độ phức tạp vận hành: phải quản lý version, quyền truy cập, mapping application/profile, backup và rotation cho từng key.

## Luân chuyển khóa đối xứng

Với cấu hình `encrypt.key` đơn giản, Config Server có một khóa đối xứng đang hoạt động. Thay khóa ngay lập tức trong khi repository còn ciphertext tạo bằng khóa cũ sẽ khiến server không thể giải mã các giá trị đó. Không đổi `ENCRYPT_KEY` tùy tiện rồi chờ hệ thống tự chuyển đổi.

Một quy trình rotation có kiểm soát có thể gồm:

1. **Chuẩn bị khóa mới:** tạo secret ngẫu nhiên mới trong secret manager, phân quyền và ghi nhận version; không đưa khóa vào Git.
2. **Kiểm kê ciphertext:** xác định mọi property đang có `{cipher}` trong các repository, branch, tag và profile mà Config Server phục vụ.
3. **Tạo ciphertext mới:** dùng công cụ migration được bảo vệ để giải mã bằng khóa cũ trong bộ nhớ và mã hóa bằng khóa mới. Không ghi plaintext ra file tạm hoặc log.
4. **Kiểm thử trước rollout:** kiểm tra ciphertext mới giải mã được bằng khóa mới, xác nhận không bỏ sót application/profile và có bản sao lưu repository phù hợp.
5. **Chuyển đổi đồng bộ:** phối hợp thời điểm cập nhật repository và secret version của toàn bộ Config Server replica để không có instance dùng khóa mới trong khi còn property cũ.
6. **Xác minh:** gọi API cấu hình trong môi trường kiểm thử, kiểm tra không còn `invalid.*` và ứng dụng nhận đúng giá trị.
7. **Thu hồi khóa cũ:** chỉ thu hồi sau khi xác nhận mọi ciphertext đã chuyển và không còn workload cần khóa cũ.

Nếu cần chuyển đổi không gián đoạn, có thể cần một `TextEncryptorLocator` tùy chỉnh hỗ trợ nhiều key trong giai đoạn chuyển tiếp hoặc một cơ chế versioned key khác đã được thiết kế và kiểm thử. Không giả định một `encrypt.key` đơn lẻ tự hỗ trợ giải mã đồng thời ciphertext cũ và mới.

Nếu khóa bị lộ, chỉ rotate khóa mã hóa là chưa đủ. Hãy xem ciphertext có thể đã bị giải mã và thay luôn các credential thực tế được bảo vệ, ví dụ database password, API token hoặc private key. Đồng thời rà soát quyền đọc repository, log, backup và các bản clone có thể đã nhận ciphertext.

## Kiểm thử quy trình mã hóa

Trước khi đưa cơ chế vào production, kiểm tra các bước sau trong môi trường thử nghiệm:

1. Cấp `ENCRYPT_KEY` từ secret manager và xác nhận Config Server nhận đúng thuộc tính mà không in giá trị khóa.
2. Gửi một chuỗi giả lập qua `/encrypt`, lưu ciphertext và xác nhận output không chứa plaintext.
3. Gửi ciphertext qua `/decrypt`, xác nhận nhận lại đúng chuỗi giả lập.
4. Đặt `{cipher}` trước ciphertext trong YAML có dấu nháy đơn và trong `.properties` không có dấu nháy.
5. Gọi Environment API của Config Server, xác nhận property source đã giải mã và không chứa ciphertext.
6. Khởi động Config Client, xác nhận ứng dụng bind đúng giá trị và không ghi secret vào log.
7. Thử sai khóa hoặc ciphertext hỏng, xác nhận xuất hiện `invalid.*` theo mặc định và cảnh báo được phát hiện.
8. Kiểm tra `/encrypt` và `/decrypt` bị chặn với danh tính không được phép.
9. Với nhiều Config Server replica, xác nhận tất cả replica dùng cùng key version.
10. Thực hành rotation trong môi trường thử nghiệm và xác minh rollback nếu một bước chuyển đổi thất bại.

Không dùng secret production để kiểm thử round-trip. Không đưa plaintext hoặc khóa thật vào issue, chat, tài liệu, test fixture hay pipeline log.

## Kết luận

`encrypt.key` cấu hình một bí mật đối xứng để Spring Cloud Config mã hóa và giải mã giá trị cấu hình. Cấp khóa qua `ENCRYPT_KEY` hoặc secret manager, mã hóa plaintext bằng `/encrypt`, thêm tiền tố `{cipher}` vào ciphertext rồi lưu trong repository. Theo mặc định, Config Server giải mã trước khi trả cấu hình cho Config Client; client không cần biết khóa đối xứng.

Mã hóa này bảo vệ secret khi lưu trong repository nhưng không thay thế TLS, xác thực hoặc phân quyền. Bảo vệ `/decrypt`, giữ khóa ngoài Git, đồng bộ khóa giữa các replica, phát hiện `invalid.*` và luân chuyển khóa có kế hoạch là các phần bắt buộc của vận hành. Nếu cần tách khóa theo ứng dụng/profile, phải thiết kế `TextEncryptorLocator` phù hợp thay vì cho rằng endpoint context tự động tạo khóa riêng.

## Tài liệu tham khảo

- [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
- [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html)
- [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html)
