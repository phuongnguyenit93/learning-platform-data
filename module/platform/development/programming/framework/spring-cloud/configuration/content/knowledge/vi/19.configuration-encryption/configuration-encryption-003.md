# Dùng /encrypt và /decrypt với dữ liệu được truyền đúng định dạng

Spring Cloud Config Server cung cấp hai endpoint HTTP để mã hóa và giải mã một giá trị cấu hình: <code>POST /encrypt</code> và <code>POST /decrypt</code>. Người vận hành dùng <code>/encrypt</code> để biến plaintext thành ciphertext trước khi lưu vào repository; khi Config Server đọc một thuộc tính có tiền tố <code>{cipher}</code>, server dùng khóa tương ứng để giải mã trước khi cung cấp cấu hình cho client.

Điểm dễ gây lỗi là định dạng request. Hai endpoint này nhận **nội dung cần xử lý trong request body**. Hãy gửi chuỗi văn bản thuần với đúng encoding, không bọc nó thành JSON object hoặc một form field như <code>value=...</code>. Với dữ liệu có dấu cách, dấu cộng, dấu phần trăm, dấu ampersand hoặc ký tự Unicode, cách gửi body và quoting ảnh hưởng trực tiếp tới dữ liệu được mã hóa.

Bài học này trình bày cách cấu hình khóa mã hóa, gửi plaintext và ciphertext đúng cách, đọc response, lưu giá trị dưới dạng <code>{cipher}</code>, hiểu luồng giải mã khi Config Server trả Environment, và xử lý lỗi mà không làm lộ bí mật.

Sau bài học, bạn có thể:

- Phân biệt plaintext, ciphertext và marker <code>{cipher}</code>.
- Gọi <code>POST /encrypt</code> và <code>POST /decrypt</code> bằng raw request body.
- Chọn <code>Content-Type</code> và cách truyền dữ liệu phù hợp.
- Giữ nguyên ký tự đặc biệt, encoding UTF-8 và byte của ciphertext.
- Cấu hình khóa đối xứng hoặc keystore cho Config Server.
- Lưu ciphertext vào Git và hiểu thời điểm Config Server giải mã.
- Bảo vệ endpoint, khóa và output chẩn đoán.
- Chẩn đoán lỗi sai định dạng, sai khóa và ciphertext không tương thích.

## 1. Hai endpoint xử lý nội dung trong request body

Spring Cloud Config Server cung cấp hai endpoint:

| Endpoint | Phương thức | Nội dung gửi lên | Kết quả |
|---|---|---|---|
| <code>/encrypt</code> | POST | Plaintext cần mã hóa | Ciphertext |
| <code>/decrypt</code> | POST | Ciphertext cần giải mã | Plaintext |

Cả hai endpoint nhận dữ liệu trong body. Ví dụ khái niệm:

~~~http
POST /encrypt
Content-Type: text/plain

my-database-password
~~~

Server trả về một chuỗi ciphertext. Để giải mã, gửi chính ciphertext đó trong body của request POST tới <code>/decrypt</code>.

Không coi các endpoint này như REST API nhận JSON theo dạng:

~~~json
{
  "value": "my-database-password"
}
~~~

Nếu gửi JSON object, server có thể mã hóa toàn bộ nội dung JSON thành một chuỗi hoặc từ chối request tùy phiên bản và message converter. Kết quả không phải là cách truyền giá trị cấu hình đơn giản mà endpoint được thiết kế để xử lý.

Tương tự, không gửi form field như:

~~~text
value=my-database-password
~~~

Body phải chứa đúng giá trị cần mã hóa, không thêm tên field.

## 2. Cấu hình khóa cho Config Server

Trước khi gọi endpoint, Config Server phải có cơ chế mã hóa được cấu hình. Hai lựa chọn phổ biến là khóa đối xứng và keystore bất đối xứng.

### Khóa đối xứng

Với khóa đối xứng, cùng một secret key được dùng để mã hóa và giải mã. Cấu hình minh họa:

~~~yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
~~~

Tiến trình Config Server nhận biến môi trường <code>CONFIG_ENCRYPT_KEY</code> từ secret manager hoặc nền tảng triển khai. Không commit khóa thật vào Git, không đặt khóa trong repository cấu hình mà chính Config Server đang đọc, và không ghi khóa vào log.

Ưu điểm của khóa đối xứng là cấu hình đơn giản. Nhược điểm là thành phần cần giải mã phải có quyền truy cập cùng khóa bí mật. Nếu khóa bị lộ, người có ciphertext và khóa có thể giải mã dữ liệu.

### Keystore bất đối xứng

Với mô hình bất đối xứng, Config Server sử dụng key pair được lưu trong keystore. Một cấu hình minh họa:

~~~yaml
encrypt:
  key-store:
    location: classpath:/config-server.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-server-key
    secret: ${CONFIG_KEYSTORE_KEY_PASSWORD}
~~~

Các giá trị password được cấp từ môi trường bảo mật. Đường dẫn, alias và tên thuộc tính cần được đối chiếu với phiên bản Spring Cloud Config đang dùng.

Keystore giúp tách việc phân phối public key và bảo vệ private key. Tuy nhiên, private key và mật khẩu keystore vẫn phải được bảo vệ nghiêm ngặt. Nếu mất private key hoặc thay key mà không còn giữ khả năng giải mã ciphertext cũ, các giá trị đã lưu có thể không đọc lại được.

### Chọn cơ chế nào?

| Tiêu chí | Khóa đối xứng | Keystore bất đối xứng |
|---|---|---|
| Vận hành ban đầu | Đơn giản | Cần quản lý keystore/key pair |
| Bí mật cần bảo vệ | Một khóa dùng cho mã hóa và giải mã | Private key và mật khẩu keystore |
| Phân phối public key | Không có public key riêng | Có thể phân phối public key cho bên mã hóa |
| Quản lý vòng đời | Phải kiểm soát việc thay khóa dùng chung | Có thể tổ chức vòng đời key pair và certificate |
| Phù hợp | Môi trường đơn giản, số thành phần ít | Hệ thống cần tách quyền mã hóa và giải mã |

Dù chọn cách nào, hãy lưu lại key version và quy trình khôi phục. Không thay khóa tùy tiện khi repository còn ciphertext được mã hóa bằng khóa cũ.

## 3. Gửi plaintext tới /encrypt đúng định dạng

Cách rõ ràng nhất là gửi raw text body và khai báo <code>Content-Type: text/plain</code>:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "my-database-password" \
  https://config.internal/encrypt
~~~

Trong ví dụ:

- HTTP method là POST.
- Body chứa đúng chuỗi plaintext.
- <code>Content-Type</code> chỉ ra nội dung là văn bản.
- <code>--data-binary</code> truyền nội dung mà không áp dụng xử lý URL-encoding như <code>--data-urlencode</code>.

Server trả ciphertext trong response body. Ciphertext thực tế phụ thuộc thuật toán, key và phiên bản thư viện. Không tự sửa, cắt, nối hoặc thay thế ký tự trong chuỗi trả về.

### Vì sao nên dùng raw body?

Giả sử plaintext là:

~~~text
p@ss word+blue&green=42
~~~

Nếu dữ liệu được gửi dưới dạng form URL-encoded, các ký tự như <code>+</code>, <code>&</code> và <code>=</code> có thể được diễn giải theo quy tắc của form. Nếu client và server không cùng cách giải mã form, plaintext được mã hóa có thể khác chuỗi ban đầu.

Dùng raw body với <code>text/plain</code> làm rõ rằng toàn bộ body chính là dữ liệu cần mã hóa.

### Không bọc giá trị trong JSON

Không dùng:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"value":"my-database-password"}' \
  https://config.internal/encrypt
~~~

Request trên gửi một JSON object. Endpoint nhận body dạng chuỗi nên không tự hiểu field <code>value</code> là plaintext cần mã hóa. Nếu server chấp nhận body, nó có thể mã hóa nguyên văn JSON thay vì chỉ mã hóa password.

### Không gửi multipart hoặc form field

Không dùng:

~~~bash
curl --request POST \
  --form "value=my-database-password" \
  https://config.internal/encrypt
~~~

Multipart form gửi một cấu trúc nhiều phần có tên field và metadata. Đây không phải raw text body.

## 4. Xử lý ký tự đặc biệt và dữ liệu UTF-8

Lỗi định dạng thường chỉ xuất hiện khi plaintext có ký tự đặc biệt. Ví dụ:

~~~text
P@ss word + blue & green = 42
Mật khẩu thử nghiệm: tiếng Việt có dấu
token%with?reserved#characters
~~~

Một số nguyên tắc:

- Dùng dấu nháy phù hợp với shell để bảo toàn khoảng trắng và ký tự.
- Không dùng <code>--data-urlencode</code> nếu mục tiêu là gửi nguyên văn plaintext.
- Dùng UTF-8 thống nhất giữa nơi tạo dữ liệu và nơi gửi request.
- Không tự chuẩn hóa Unicode hoặc đổi newline trước khi mã hóa.
- Nếu dùng file, bảo đảm file không có newline cuối ngoài ý muốn.
- Không copy ciphertext qua công cụ có thể tự đổi dấu cộng, dấu gạch chéo hoặc ký tự đặc biệt.

Với plaintext lưu trong file UTF-8, có thể dùng:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "@plaintext.txt" \
  https://config.internal/encrypt
~~~

Ký tự <code>@</code> trước tên file yêu cầu curl đọc nội dung file làm request body. Kiểm tra file có chứa đúng byte cần mã hóa; một newline cuối file cũng là một phần của plaintext.

Đối với secret thật, hạn chế dùng command line literal vì shell history hoặc process inspection có thể lưu/hiển thị giá trị. Ưu tiên file tạm có quyền truy cập hạn chế, secret input an toàn hoặc công cụ nội bộ đã được phê duyệt; xóa file tạm theo quy trình sau khi dùng.

## 5. Đọc response từ /encrypt

Ví dụ request:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "my-database-password" \
  https://config.internal/encrypt
~~~

Response body có thể là một chuỗi ciphertext, ví dụ minh họa:

~~~text
AQB3c2FtcGxlLWVuY3J5cHRlZC1ieXRlcw==
~~~

Chuỗi trên chỉ là ví dụ định dạng, không phải ciphertext có thể dùng trong hệ thống. Ciphertext thật phụ thuộc key và thuật toán được cấu hình.

Khi lưu vào repository, thêm marker <code>{cipher}</code> trước ciphertext để Config Server nhận biết giá trị đã mã hóa:

~~~yaml
spring:
  datasource:
    password: "{cipher}AQB3c2FtcGxlLWVuY3J5cHRlZC1ieXRlcw=="
~~~

Marker <code>{cipher}</code> là tiền tố nhận diện trong cấu hình. Nó không phải phần ciphertext do endpoint nhất thiết trả về. Vì vậy:

- Response từ <code>/encrypt</code> là ciphertext.
- Giá trị lưu trong YAML/Properties có dạng <code>{cipher}</code> + ciphertext.
- Khi gửi ciphertext tới <code>/decrypt</code>, thông thường gửi phần ciphertext thuần, không thêm marker <code>{cipher}</code>.

Dùng dấu nháy quanh giá trị YAML giúp giữ chuỗi rõ ràng, nhất là khi ciphertext chứa ký tự có ý nghĩa đặc biệt với YAML.

## 6. Gửi ciphertext tới /decrypt đúng định dạng

Để giải mã, gửi đúng ciphertext nhận được từ <code>/encrypt</code> trong raw body:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "AQB3c2FtcGxlLWVuY3J5cHRlZC1ieXRlcw==" \
  https://config.internal/decrypt
~~~

Response body là plaintext ban đầu nếu:

- Ciphertext không bị thay đổi.
- Config Server dùng đúng khóa hoặc private key tương ứng.
- Thuật toán và định dạng tương thích.
- Request body chứa đúng ciphertext, không thêm dấu nháy hoặc marker không được endpoint mong đợi.

### Giải mã từ file

Nếu ciphertext được lưu trong file:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "@ciphertext.txt" \
  https://config.internal/decrypt
~~~

File chỉ nên chứa ciphertext. Không thêm tiền tố <code>{cipher}</code> nếu đang gọi endpoint giải mã trực tiếp, và tránh newline cuối file nếu newline đó không thuộc ciphertext.

### Kiểm tra vòng đời encrypt/decrypt

Một bài kiểm tra an toàn dùng giá trị giả:

1. Chọn một chuỗi test không phải secret production.
2. Gửi chuỗi tới <code>/encrypt</code> bằng raw body.
3. Lưu ciphertext response vào biến hoặc file tạm.
4. Gửi ciphertext tới <code>/decrypt</code> bằng raw body.
5. So sánh plaintext trả về với chuỗi ban đầu theo đúng encoding.
6. Xóa dữ liệu test tạm và không ghi secret thật vào log.

Kết quả mong đợi là plaintext sau giải mã khớp chính xác với plaintext ban đầu. Không so sánh ciphertext với nhau giữa hai lần mã hóa nếu thuật toán có random salt/IV; cùng plaintext có thể tạo ciphertext khác nhau.

## 7. Config Server giải mã thuộc tính {cipher} khi nào?

Sau khi ciphertext được lưu trong repository:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "{cipher}AQB3c2FtcGxlLWVuY3J5cHRlZC1ieXRlcw=="
~~~

Config Server đọc repository và xử lý thuộc tính có marker <code>{cipher}</code> bằng cơ chế giải mã đã cấu hình. Khi client yêu cầu Environment, server giải mã giá trị trước khi trả cấu hình theo hành vi mặc định của Config Server.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Plaintext bí mật"] --> B["POST /encrypt"]
    B --> C["Ciphertext"]
    C --> D["Thêm marker {cipher}"]
    D --> E["Lưu vào config repository"]
    E --> F["Config Server đọc property source"]
    F --> G["Giải mã bằng key/private key"]
    G --> H["Trả Environment cho Config Client"]
    H --> I["Ứng dụng bind thuộc tính"]
~~~

Config Client thông thường không cần biết khóa mã hóa của Config Server khi server thực hiện giải mã trước khi trả Environment. Vì vậy, khóa giải mã phải được bảo vệ ở Config Server.

Nếu hệ thống được cấu hình để không giải mã phía server hoặc dùng một luồng mã hóa khác, hành vi trả về có thể khác. Hãy xác minh phiên bản và cấu hình của server, không giả định client tự giải mã marker.

### Giá trị giải mã không còn được mã hóa khi truyền tới client

Mã hóa ciphertext trong Git bảo vệ giá trị lưu trữ khi người chỉ có quyền đọc repository không có khóa giải mã. Khi Config Server giải mã và trả giá trị cho client, plaintext đi qua mạng và tồn tại trong bộ nhớ ứng dụng.

Vì vậy, vẫn cần:

- HTTPS giữa Config Server và Config Client.
- Authentication và authorization cho endpoint cấu hình.
- Hạn chế quyền đọc theo application/profile.
- Không log Environment hoặc secret.
- Bảo vệ heap dump, diagnostic endpoint và process memory.
- Dùng secret manager khi cần policy, audit và rotation chuyên biệt.

Mã hóa cấu hình trong Git không thay thế TLS hoặc secret management.

## 8. Cấu hình endpoint và xác thực

Các endpoint <code>/encrypt</code> và <code>/decrypt</code> có thể tạo hoặc tiết lộ dữ liệu bí mật. Không nên mở chúng công khai.

Một số nguyên tắc triển khai:

1. Chỉ expose endpoint qua mạng quản trị nội bộ hoặc gateway bảo mật.
2. Yêu cầu xác thực mạnh cho người vận hành được phép mã hóa/giải mã.
3. Phân quyền riêng cho thao tác encrypt và decrypt nếu kiến trúc hỗ trợ.
4. Dùng HTTPS và xác minh chứng thư.
5. Rate-limit hoặc audit request nếu endpoint được dùng bởi automation.
6. Không log request body, response body hoặc khóa mã hóa.
7. Hạn chế truy cập shell, process environment và file keystore trên host Config Server.

Endpoint <code>/encrypt</code> thường cần quyền sử dụng khóa để tạo ciphertext. Endpoint <code>/decrypt</code> còn nhạy cảm hơn vì trả plaintext; chỉ cấp cho nhóm vận hành thật sự cần. Một endpoint giải mã bị lộ có thể biến Config Server thành công cụ lấy secret.

Nếu ứng dụng dùng Spring Security, cần kiểm tra rule hiện tại để bảo đảm các POST endpoint này không vô tình được mở cho anonymous access. Không chỉ dựa vào việc endpoint không được liệt kê trong tài liệu công khai.

## 9. Lỗi thường gặp do truyền sai định dạng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Server mã hóa cả chuỗi JSON | Request gửi JSON object thay vì raw text | Xem <code>Content-Type</code> và body thực tế |
| Plaintext sau decrypt khác chuỗi ban đầu | Shell đã biến đổi ký tự, encoding hoặc newline | Dùng file UTF-8 và <code>--data-binary</code> |
| Dữ liệu có <code>+</code> hoặc <code>&</code> bị sai | Gửi qua form URL-encoded hoặc shell quoting không đúng | Gửi raw body với <code>text/plain</code> |
| Endpoint báo lỗi parse/decrypt | Body chứa marker <code>{cipher}</code>, dấu nháy hoặc field thừa | Gửi ciphertext thuần |
| Encrypt trả lỗi | Config Server chưa có key/keystore hoặc key sai cấu hình | Kiểm tra cấu hình <code>encrypt</code> và startup log đã mask |
| Decrypt báo lỗi padding hoặc bad ciphertext | Ciphertext bị cắt, đổi ký tự hoặc dùng sai key | Lấy lại nguyên ciphertext và kiểm tra key version |
| Config Server không giải mã property | Thiếu marker, sai prefix hoặc không có key tương ứng | Kiểm tra property value và key backend |
| Client nhận giá trị lỗi | Server không giải mã được hoặc property source có vấn đề | Kiểm tra server response và <code>invalid.*</code> nếu được tạo |
| HTTP 401/403 | Thiếu xác thực hoặc không đủ quyền | Kiểm tra security policy |
| HTTP 404 | Endpoint không có trong bản server hoặc request sai base path | Kiểm tra phiên bản và route |
| HTTP 5xx | Key store không đọc được, thuật toán hoặc provider lỗi | Kiểm tra log server không chứa dữ liệu nhạy cảm |

Khi decrypt thất bại, một số phiên bản Config Server có thể loại bỏ giá trị gốc khỏi property source và thêm thuộc tính có tiền tố <code>invalid.</code>, chẳng hạn <code>invalid.spring.datasource.password</code>, để báo lỗi giải mã. Hành vi và nội dung chi tiết phụ thuộc phiên bản; hãy kiểm tra Environment response mà không công khai ciphertext hoặc secret.

## 10. Vận hành khóa và thay đổi ciphertext

Ciphertext phụ thuộc khóa mã hóa. Khi thay khóa, ciphertext cũ có thể không giải mã được bằng khóa mới.

Một quy trình thay khóa cần có:

1. Xác định key version hiện tại và các thuộc tính đã mã hóa bằng key đó.
2. Sao lưu hoặc bảo đảm có thể khôi phục keystore/key cũ theo chính sách bảo mật.
3. Tạo key mới và cấp cho môi trường mã hóa/giải mã phù hợp.
4. Mã hóa lại các giá trị bằng key mới theo kế hoạch.
5. Kiểm thử giải mã bằng Config Server ở môi trường thử nghiệm.
6. Phát hành repository mới và xác nhận client nhận giá trị cần thiết.
7. Chỉ thu hồi key cũ khi chắc chắn không còn ciphertext cần giải mã bằng key đó.

Không ghi key version hoặc key material vào cùng nơi có ciphertext theo cách làm mất mục tiêu bảo vệ. Có thể lưu metadata không nhạy cảm về phiên bản key để phục vụ audit và migration.

Nếu key bị lộ, cần xử lý như sự cố bảo mật: thu hồi hoặc thay key, đánh giá ciphertext đã bị truy cập, xoay vòng secret gốc và kiểm tra audit. Chỉ mã hóa lại ciphertext không đủ nếu password hoặc token plaintext đã bị lộ ở nơi khác.

## 11. Ví dụ hoàn chỉnh với cấu hình database

Giả sử Config Server được triển khai với biến môi trường khóa:

~~~yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
~~~

Người vận hành có plaintext test:

~~~text
orders-db-password-test
~~~

Gửi request:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "orders-db-password-test" \
  https://config.internal/encrypt
~~~

Giả sử response là ciphertext minh họa:

~~~text
AQB...ciphertext...
~~~

Lưu trong <code>orders-service-prod.yml</code>:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "{cipher}AQB...ciphertext..."
~~~

Sau khi commit và Config Server đọc label tương ứng, client yêu cầu:

~~~http
GET /orders-service/prod/release-2026.11
~~~

Config Server giải mã thuộc tính password trước khi trả Environment. Config Client bind giá trị vào cấu hình datasource. Không cần đưa plaintext password vào Git.

Để kiểm tra riêng ciphertext, gửi đúng phần ciphertext tới:

~~~bash
curl --request POST \
  --header "Content-Type: text/plain; charset=UTF-8" \
  --data-binary "AQB...ciphertext..." \
  https://config.internal/decrypt
~~~

Kết quả giải mã phải khớp plaintext test. Với secret production, chỉ xác minh trong môi trường được bảo vệ và không đưa response plaintext vào terminal log hoặc ticket chia sẻ.

## 12. Checklist trước khi dùng /encrypt và /decrypt

- [ ] Config Server có khóa đối xứng hoặc keystore hợp lệ.
- [ ] Khóa được cấp từ secret manager hoặc môi trường bảo mật, không commit vào Git.
- [ ] Request dùng POST và raw body chứa đúng giá trị cần xử lý.
- [ ] Dùng <code>Content-Type: text/plain</code> và encoding đã thống nhất.
- [ ] Không gửi JSON object, multipart hoặc form field.
- [ ] Dùng <code>--data-binary</code> khi cần bảo toàn byte và ký tự.
- [ ] Đã kiểm tra dấu cách, dấu cộng, dấu phần trăm, Unicode và newline.
- [ ] Ciphertext được giữ nguyên; marker <code>{cipher}</code> chỉ được thêm khi lưu thuộc tính trong repository.
- [ ] Request decrypt gửi ciphertext thuần, không vô tình thêm marker hoặc field.
- [ ] Config Server có thể giải mã bằng đúng key đã dùng để mã hóa.
- [ ] Endpoint encrypt/decrypt được bảo vệ bằng HTTPS, authentication và authorization.
- [ ] Không log plaintext, ciphertext nhạy cảm, key hoặc response giải mã.
- [ ] Có kế hoạch version hóa, backup và rotation khóa.
- [ ] Đã kiểm thử vòng encrypt/decrypt bằng dữ liệu giả trước khi dùng secret thật.

<code>/encrypt</code> và <code>/decrypt</code> làm việc trực tiếp với chuỗi trong request body. Gửi đúng raw text, giữ nguyên encoding và ciphertext, cấu hình khóa an toàn, rồi thêm marker <code>{cipher}</code> khi lưu giá trị vào repository. Khi Config Server giải mã để trả Environment, plaintext vẫn cần được bảo vệ trên đường truyền và trong runtime của ứng dụng.

