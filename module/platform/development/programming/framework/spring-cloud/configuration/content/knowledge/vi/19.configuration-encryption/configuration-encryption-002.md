# Cơ chế {cipher} trong giá trị cấu hình

Spring Cloud Config cho phép lưu giá trị nhạy cảm ở dạng mã hóa trong repository cấu hình. Cơ chế này dùng tiền tố **`{cipher}`** để đánh dấu một giá trị đã được mã hóa, nhờ đó Config Server biết cần giải mã trước khi trả cấu hình cho Config Client. Cách làm này giúp tránh lưu mật khẩu hoặc token ở dạng rõ trong Git, nhưng chỉ an toàn khi khóa mã hóa được quản lý riêng và các endpoint mã hóa/giải mã được bảo vệ.

Trong hệ thống có nhiều ứng dụng Spring Boot, Config Server là điểm tập trung đọc cấu hình từ Git hoặc backend khác. Khi một property source chứa giá trị bắt đầu bằng `{cipher}`, server sử dụng khóa hoặc keystore đã cấu hình để giải mã giá trị đó trước khi cung cấp cho client. Client thông thường nhận giá trị đã giải mã; khóa bí mật không cần được phân phối đến từng client.

## 1. `{cipher}` đánh dấu giá trị đã mã hóa

`{cipher}` là marker đặt ở đầu giá trị cấu hình để cho biết phần tiếp theo là ciphertext. Ví dụ:

```yaml
spring:
  datasource:
    username: orders_app
    password: "{cipher}AQB7...ciphertext..."
```

Trong ví dụ này:

- `spring.datasource.username` là giá trị không mã hóa.
- `spring.datasource.password` chứa marker `{cipher}` và dữ liệu đã mã hóa.
- Config Server nhận diện marker, giải mã ciphertext bằng khóa phù hợp và trả giá trị rõ trong property source cho client theo cơ chế mặc định.

Nên đặt toàn bộ giá trị có marker trong dấu nháy YAML. Ký tự `{` ở đầu một scalar có thể được YAML hiểu là dấu mở flow mapping nếu không được quote, gây lỗi phân tích cú pháp hoặc tạo ra giá trị không như mong muốn.

`{cipher}` không phải placeholder Spring như `${DB_PASSWORD}`. Placeholder yêu cầu Spring tìm một giá trị khác trong `Environment`; marker cipher yêu cầu Config Server giải mã phần dữ liệu được đánh dấu.

## 2. Luồng mã hóa và giải mã

Một quy trình điển hình gồm hai giai đoạn:

1. Người vận hành gửi plaintext đến endpoint mã hóa của Config Server hoặc công cụ mã hóa được tin cậy.
2. Công cụ trả ciphertext.
3. Người vận hành thêm tiền tố `{cipher}` vào ciphertext và lưu giá trị đó trong file cấu hình.
4. File được review và commit vào repository.
5. Config Server đọc property source, nhận diện `{cipher}` và giải mã bằng khóa riêng của server.
6. Config Client nhận cấu hình theo cơ chế đã thiết lập.

```mermaid
flowchart TD
    P[Plaintext secret] --> E[Config Server /encrypt]
    E --> C[Ciphertext]
    C --> M[Add {cipher} marker]
    M --> G[(Git config repository)]
    G --> S[Config Server reads property source]
    S --> D[Decrypt with server key]
    D --> R[Return resolved Environment]
    R --> CL[Config Client]
```

Mục tiêu là bảo vệ dữ liệu nhạy cảm khi lưu trữ và review trong repository. Khi Config Server giải mã để phục vụ client, plaintext vẫn tồn tại trong bộ nhớ và có thể xuất hiện ở các hệ thống downstream nếu ứng dụng ghi log hoặc hiển thị sai cách. Mã hóa trong Git không loại bỏ yêu cầu bảo vệ secret ở runtime.

## 3. Endpoint /encrypt và /decrypt

Config Server cung cấp endpoint để mã hóa và giải mã dữ liệu. Với server chạy ở cổng `8888`, có thể gọi endpoint mã hóa bằng HTTP POST:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "example-secret" \
  http://localhost:8888/encrypt
```

Response chứa ciphertext. Đưa ciphertext đó vào file cấu hình với tiền tố `{cipher}`:

```yaml
app:
  integration:
    api-token: "{cipher}AQB...ciphertext-returned-by-server..."
```

Endpoint giải mã nhận ciphertext qua POST:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "AQB...ciphertext..." \
  http://localhost:8888/decrypt
```

`/encrypt` và `/decrypt` là endpoint thao tác dữ liệu nhạy cảm. Không gửi secret thật đến Config Server không đáng tin cậy, không copy plaintext vào ticket hoặc chat công khai và không bật log body request/response ở môi trường production. Endpoint cần được bảo vệ bằng xác thực, phân quyền và giới hạn mạng quản trị.

Kết quả của `/encrypt` thường là ciphertext để lưu trữ; khi đặt vào file cấu hình, cần thêm marker `{cipher}`. Khi gọi `/decrypt`, gửi phần ciphertext theo định dạng endpoint yêu cầu, không tự thêm hoặc sửa ký tự làm thay đổi dữ liệu.

## 4. Cấu hình khóa mã hóa đối xứng

Cách đơn giản là dùng một khóa đối xứng được cung cấp cho Config Server qua thuộc tính `encrypt.key`:

```yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
```

Biến `CONFIG_ENCRYPT_KEY` phải được cung cấp từ secret manager hoặc cơ chế quản lý bí mật của nền tảng khi tiến trình khởi động. Không ghi giá trị khóa thật vào `application.yml`, Docker image hoặc repository cấu hình.

Với khóa đối xứng, cùng một khóa được dùng để mã hóa và giải mã. Điều này đơn giản khi một Config Server quản lý cấu hình, nhưng cần bảo vệ khóa rất chặt vì bất kỳ ai có khóa đều có thể giải mã ciphertext và có thể tạo ciphertext mới.

Trong môi trường nhiều Config Server instance, các instance cần dùng khóa tương thích để cùng giải mã những giá trị đã lưu. Nếu mỗi instance dùng khóa khác nhau, một client có thể nhận cấu hình thành công từ instance này nhưng thất bại khi được định tuyến đến instance khác.

## 5. Dùng keystore và khóa bất đối xứng

Spring Cloud Config cũng hỗ trợ cấu hình keystore để quản lý khóa bất đối xứng. Ví dụ:

```yaml
encrypt:
  keyStore:
    location: file:/run/secrets/config-server-keystore.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    secret: ${CONFIG_KEY_PASSWORD}
```

Ý nghĩa các thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| `location` | Đường dẫn keystore chứa cặp khóa. Có thể là tài nguyên classpath hoặc file được mount. |
| `password` | Mật khẩu bảo vệ keystore. |
| `alias` | Tên entry trong keystore được dùng cho thao tác mã hóa/giải mã. |
| `secret` | Mật khẩu bảo vệ private key entry nếu khác mật khẩu keystore. |

Với mã hóa bất đối xứng, dữ liệu có thể được mã hóa bằng public key và giải mã bằng private key tương ứng. Private key phải được bảo vệ trong Config Server hoặc hệ thống quản lý khóa; không đưa private key vào Git hay phân phối cho client.

Keystore phải tồn tại trong runtime của Config Server và tiến trình phải có quyền đọc. Đường dẫn `file:` trong container cần được mount chính xác; đường dẫn trên máy host không tự xuất hiện bên trong container. Với production, thường nên mount keystore dưới dạng secret chỉ đọc.

## 6. Giải mã phía Config Server và dữ liệu client nhận được

Trong cách dùng thông thường, Config Server giải mã các giá trị `{cipher}` khi chuẩn bị response Environment. Client nhận giá trị đã giải mã như một property thông thường và có thể bind vào `@Value` hoặc `@ConfigurationProperties`.

Ví dụ repository lưu:

```yaml
app:
  payment:
    endpoint: https://payments.internal.example.com
    api-key: "{cipher}AQB...encrypted-value..."
```

Ứng dụng client có thể bind:

```java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;
    private String apiKey;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
```

Client không cần biết ciphertext hay khóa mã hóa nếu server đã giải mã trước khi trả response. Vì plaintext được truyền qua mạng nội bộ, vẫn cần TLS giữa client và Config Server, xác thực client và giới hạn quyền đọc cấu hình theo ứng dụng.

Không ghi giá trị `apiKey` ra log, exception message, actuator endpoint hoặc metric label. Mã hóa tại repository không bảo vệ plaintext sau khi ứng dụng đã nhận nó.

## 7. Khi giải mã thất bại

Giải mã có thể thất bại nếu:

- Config Server không có khóa hoặc keystore phù hợp.
- Khóa đã bị thay đổi nhưng ciphertext chưa được mã hóa lại.
- Keystore path, password, alias hoặc private key password không đúng.
- Ciphertext bị cắt, thêm khoảng trắng hoặc thay đổi ký tự khi copy vào YAML.
- Ciphertext được tạo bằng một khóa khác với khóa server đang sử dụng.
- Thuật toán hoặc định dạng khóa không tương thích với cấu hình hiện tại.

Khi không giải mã được, Config Server không thể cung cấp plaintext mong muốn. Tùy phiên bản và ngữ cảnh xử lý, response có thể đánh dấu thuộc tính lỗi bằng tên `invalid.` hoặc giá trị thay thế thay vì trả secret hợp lệ. Hãy kiểm tra log Config Server và response Environment để nhận diện lỗi, đồng thời tránh làm lộ ciphertext hoặc thông tin khóa trong log.

Không nên bỏ tiền tố `{cipher}` để “sửa tạm” lỗi giải mã trong production. Làm vậy có thể khiến ciphertext được chuyển thẳng đến ứng dụng như thể đó là mật khẩu thật. Hãy xác minh key, keystore, alias và toàn vẹn ciphertext trước.

## 8. Mã hóa không thay thế TLS và quản lý quyền

`{cipher}` bảo vệ giá trị khi lưu trong repository, nhưng không thay thế các lớp bảo mật khác:

- **TLS:** bảo vệ dữ liệu trên đường truyền giữa client và Config Server, giữa Config Server và broker/backend khi có hỗ trợ.
- **Authentication:** xác định ứng dụng hoặc người vận hành nào đang gọi Config Server.
- **Authorization:** giới hạn client chỉ đọc cấu hình cần thiết; giới hạn người vận hành được gọi `/encrypt` và `/decrypt`.
- **Secret management:** bảo vệ khóa đối xứng, keystore, passphrase và secret runtime.
- **Logging hygiene:** ngăn plaintext, ciphertext nhạy cảm và credential xuất hiện trong log hoặc telemetry.

Endpoint `/encrypt` có thể được dùng để tạo ciphertext cho repository; endpoint `/decrypt` có thể trả plaintext. Nếu để các endpoint này mở rộng rãi, người gọi có thể dùng chúng như một oracle giải mã hoặc lạm dụng tài nguyên. Chỉ cho phép nhóm quản trị được ủy quyền truy cập và ưu tiên giới hạn chúng trong mạng nội bộ.

## 9. Quy trình xoay vòng khóa

Khi khóa mã hóa bị lộ, sắp hết vòng đời hoặc cần thay theo chính sách bảo mật, không thể chỉ đổi `encrypt.key` rồi giả định ciphertext cũ vẫn giải mã được. Ciphertext đã tạo bằng khóa cũ cần được xử lý theo một kế hoạch chuyển đổi.

Quy trình xoay vòng có kiểm soát:

1. Lập danh sách các repository, application, profile và property đang lưu giá trị `{cipher}`.
2. Xác định khóa hiện tại, phạm vi instance Config Server sử dụng và các bản backup được bảo vệ.
3. Tạo khóa mới hoặc keystore mới trong hệ thống quản lý bí mật.
4. Giải mã các giá trị cũ trong môi trường được kiểm soát và mã hóa lại bằng khóa mới.
5. Review thay đổi ciphertext, bảo đảm không đưa plaintext vào commit, diff hoặc log.
6. Triển khai khóa mới đồng bộ đến các Config Server instance.
7. Xác minh từng ứng dụng/profile có thể nhận cấu hình và giải mã thành công.
8. Thu hồi khóa cũ sau khi xác nhận không còn ciphertext cần giải mã bằng khóa đó và hoàn tất yêu cầu lưu trữ/khôi phục theo chính sách.

Nếu cần giai đoạn chuyển tiếp mà hệ thống phải đọc đồng thời ciphertext cũ và mới, cần thiết kế hỗ trợ nhiều khóa hoặc một quy trình migrate theo đợt đã được kiểm thử. Không giả định một cấu hình `encrypt.key` đơn giản tự động quản lý key ring hay tự thử mọi khóa cũ.

## 10. Kiểm tra cấu hình mã hóa

Trước khi đưa một secret mã hóa vào repository, hãy xác minh:

1. Config Server đang dùng đúng khóa hoặc keystore trong runtime.
2. Endpoint `/encrypt` trả ciphertext hợp lệ.
3. Giá trị được lưu với marker `{cipher}` và được quote đúng trong YAML.
4. Config Server đọc được file và giải mã thành công.
5. Environment API trả thuộc tính đúng cho application/profile/label dự kiến.
6. Client có thể bind giá trị mà không ghi secret ra log.
7. Các Config Server instance khác cũng giải mã được cùng giá trị.

Có thể kiểm tra endpoint mã hóa trong môi trường thử nghiệm:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "test-value" \
  http://localhost:8888/encrypt
```

Sau đó kiểm tra giải mã ciphertext bằng endpoint `/decrypt` trong môi trường được bảo vệ. Không dùng secret production thật cho thử nghiệm ở máy cá nhân hoặc môi trường không được phép xử lý dữ liệu đó.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client nhận chuỗi `{cipher}...` thay vì plaintext | Server không thực hiện decrypt, marker bị định dạng sai hoặc xử lý mã hóa bị vô hiệu hóa theo cấu hình. | Kiểm tra Config Server, phiên bản và định dạng giá trị. |
| Environment có thuộc tính `invalid...` hoặc giá trị lỗi | Decrypt thất bại. | Kiểm tra key, keystore, alias, passphrase và ciphertext. |
| `/encrypt` trả lỗi | Khóa mã hóa chưa cấu hình hoặc endpoint bị chặn/xác thực. | Kiểm tra `encrypt.key`/keystore và quyền endpoint. |
| `/decrypt` không trả giá trị mong đợi | Ciphertext bị thay đổi hoặc được tạo bằng khóa khác. | Dùng đúng khóa và dữ liệu ciphertext nguyên vẹn. |
| Chỉ một Config Server instance giải mã được | Các instance dùng key/keystore khác nhau hoặc mount secret không đồng nhất. | Đồng bộ key version và xác minh từng runtime. |
| YAML không đọc được sau khi thêm `{cipher}` | Giá trị chưa được quote hoặc ciphertext có ký tự làm sai cú pháp. | Đặt toàn bộ giá trị trong dấu nháy và kiểm tra YAML. |
| Secret bị lộ dù đã mã hóa trong Git | Plaintext xuất hiện trong log, endpoint, diff hoặc client telemetry. | Rà soát luồng runtime, log redaction, Actuator và quyền truy cập. |

## 12. Tổng kết

- `{cipher}` đánh dấu giá trị cấu hình đã mã hóa để Config Server giải mã khi phục vụ client.
- Dùng `/encrypt` để tạo ciphertext và lưu ciphertext với tiền tố `{cipher}`; bảo vệ `/decrypt` vì endpoint này trả plaintext.
- `encrypt.key` cấu hình khóa đối xứng; `encrypt.keyStore.*` cấu hình keystore và khóa bất đối xứng.
- Khóa mã hóa phải được quản lý ngoài Git và được cung cấp an toàn cho mọi Config Server instance cần giải mã.
- Client thông thường nhận plaintext từ Config Server; cần TLS, authentication, authorization và bảo vệ secret trong runtime.
- Giải mã thất bại thường liên quan đến sai khóa, keystore, alias, passphrase hoặc ciphertext bị thay đổi.
- Xoay vòng khóa cần mã hóa lại ciphertext và triển khai đồng bộ; không giả định thay khóa là đủ.
- Mã hóa trong repository là một lớp bảo vệ, không thay thế secret manager, bảo mật endpoint, TLS và kiểm soát log.
