# Mã hóa bất đối xứng bằng keystore, alias và cặp khóa

Spring Cloud Config Server có thể giải mã các giá trị cấu hình đã được mã hóa trước khi gửi chúng đến Config Client. Với mã hóa bất đối xứng, người tạo cấu hình dùng public key để mã hóa; private key tương ứng được giữ trong keystore ở Config Server và chỉ server mới dùng nó để giải mã. Cách làm này giúp lưu ciphertext trong Git mà không phải lưu private key cùng repository cấu hình.

Bài viết tập trung vào cách tạo cặp khóa RSA, đóng gói khóa trong keystore PKCS12, chọn alias, cấu hình Config Server, sử dụng các endpoint mã hóa/giải mã và đánh dấu giá trị bằng tiền tố {cipher}. Phần cuối trình bày cách kiểm tra, xoay vòng khóa và bảo vệ đường đi của secret trong hệ thống nhiều ứng dụng Spring Boot.

## 1. Mã hóa bất đối xứng trong Config Server

Một cặp khóa bất đối xứng gồm:

- **Public key**: có thể phân phối cho pipeline hoặc nhóm tạo cấu hình; dùng để mã hóa dữ liệu.
- **Private key**: phải được giữ bí mật; dùng để giải mã dữ liệu đã được mã hóa bằng public key tương ứng.

Luồng xử lý trong Spring Cloud Config:

~~~mermaid
flowchart LR
    A[Secret plaintext<br/>quy trình cấp secret] --> B[Public key]
    B --> C[Encrypt]
    C --> D[Ciphertext]
    D --> E[Git repository<br/>property có tiền tố {cipher}]
    E --> F[Config Server]
    K[Keystore<br/>private key + alias] --> F
    F --> G[Decrypt server-side]
    G --> H[Config Environment]
    H --> I[Config Client]
~~~

Khi một giá trị được mã hóa, Git chỉ lưu ciphertext. Config Server đọc property source, nhận diện tiền tố mã hóa, dùng private key tương ứng để giải mã rồi trả giá trị đã giải mã trong Environment cho client.

Client không cần sở hữu private key. Điều này tập trung khả năng giải mã ở Config Server, nhưng cũng khiến server trở thành ranh giới bảo mật quan trọng: caller được phép đọc cấu hình có thể nhận secret đã giải mã thuộc application/profile mà caller được truy cập.

Mã hóa bất đối xứng bảo vệ dữ liệu khi lưu trong repository. Nó không thay thế HTTPS, xác thực client, phân quyền truy cập Config Server hoặc bảo vệ secret trong bộ nhớ và log của ứng dụng.

## 2. Keystore, alias và cặp khóa

Keystore là một kho chứa khóa và chứng thư. Với cấu hình mã hóa của Spring Cloud Config, keystore thường chứa một private key entry cùng chứng thư có public key tương ứng.

Các khái niệm cần phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| Keystore file | File chứa entry khóa, ví dụ định dạng PKCS12 |
| Keystore password | Mật khẩu mở hoặc bảo vệ nội dung keystore |
| Key password | Mật khẩu bảo vệ private key entry |
| Alias | Tên định danh entry trong keystore |
| Public key | Thành phần dùng để mã hóa |
| Private key | Thành phần bí mật dùng để giải mã |

Alias không phải mật khẩu và cũng không phải tên application. Nó là tên để Config Server chọn đúng key entry trong keystore. Một keystore có thể chứa nhiều entry; cấu hình alias xác định entry được dùng cho hoạt động mã hóa/giải mã hiện tại.

Keystore PKCS12 là định dạng trao đổi phổ biến và được Java hỗ trợ. Khi tạo bằng keytool, công cụ tạo một cặp khóa cùng chứng thư tự ký chứa public key. Chứng thư ở đây là vật chứa public key cho chức năng mã hóa cấu hình; nó không tự động thay thế chứng thư TLS dùng để bảo vệ kết nối HTTPS.

## 3. Tạo keystore RSA bằng keytool

Có thể dùng keytool đi kèm JDK để tạo cặp khóa RSA:

~~~bash
keytool -genkeypair -alias config-encryption -keyalg RSA -keysize 3072 -storetype PKCS12 -keystore config-server.p12 -validity 3650
~~~

Keytool sẽ hỏi mật khẩu keystore, thông tin chứng thư và mật khẩu của private key entry. Với PKCS12, một số cấu hình JDK/provider yêu cầu mật khẩu key entry trùng với mật khẩu keystore; dùng cùng một mật khẩu là lựa chọn tương thích phổ biến. Nếu môi trường hỗ trợ mật khẩu riêng, lưu chúng thành hai secret riêng.

Các tham số chính:

- -genkeypair tạo cặp khóa mới.
- -alias config-encryption đặt tên entry.
- -keyalg RSA chọn thuật toán RSA.
- -keysize 3072 chọn kích thước khóa.
- -storetype PKCS12 chọn định dạng keystore.
- -keystore config-server.p12 đặt tên file.
- -validity 3650 đặt thời hạn chứng thư tự ký theo ngày.

Kích thước khóa cần tuân thủ chính sách mật mã của tổ chức. RSA 2048 bit là mức phổ biến tối thiểu trong nhiều môi trường; 3072 bit có thể được chọn khi chính sách yêu cầu biên an toàn cao hơn và hiệu năng cho phép. Không tự ý hạ kích thước khóa để xử lý lỗi tương thích.

Kiểm tra entry vừa tạo:

~~~bash
keytool -list -v -keystore config-server.p12 -alias config-encryption
~~~

Xác nhận alias tồn tại, entry là loại private key entry và keystore mở được bằng mật khẩu đã chọn. Bảo vệ file keystore như một tài sản bí mật vì nó chứa private key. Không đưa file này vào Git, artifact chia sẻ hoặc Docker image công khai.

## 4. Cấu hình Config Server dùng keystore

Config Server cần dependency hỗ trợ mã hóa của Spring Cloud Config và Spring Security RSA tương thích với release train đang dùng. Dependency management nên được quản lý bằng Spring Cloud BOM thay vì tự chọn phiên bản thư viện rời rạc.

Ví dụ Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-rsa</artifactId>
</dependency>
~~~

Cấu hình Config Server:

~~~yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main

encrypt:
  key-store:
    location: file:/etc/config-server/keys/config-server.p12
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    secret: ${CONFIG_KEY_PASSWORD}
~~~

Ý nghĩa các thuộc tính:

- encrypt.key-store.location là vị trí keystore. Có thể dùng classpath location hoặc file URI; trong triển khai container nên dùng đường dẫn tuyệt đối được mount từ secret storage.
- encrypt.key-store.password là mật khẩu keystore.
- encrypt.key-store.alias là alias của key entry được chọn.
- encrypt.key-store.secret là mật khẩu của private key entry.

Nếu PKCS12 được tạo với cùng mật khẩu cho store và key entry, có thể cấp cùng một secret cho hai biến môi trường. Nếu dùng mật khẩu riêng, cấp đúng từng giá trị. Tên biến môi trường chỉ là ví dụ; hãy dùng secret injection của nền tảng, không ghi giá trị thật vào file cấu hình được commit.

Lớp khởi động vẫn bật Config Server:

~~~java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
~~~

Keystore chỉ cần có ở Config Server. Không mount private key vào Config Client. Nếu Config Server chạy nhiều replica, các replica cần dùng cùng bộ khóa đang hoạt động hoặc một cơ chế quản lý khóa thống nhất; nếu mỗi replica dùng key khác nhau, một client có thể nhận kết quả khác nhau tùy replica xử lý request.

## 5. Đặt keystore trong container an toàn

Với Docker, mount keystore từ thư mục secret được quản lý riêng:

~~~yaml
services:
  config-server:
    image: example/config-server:1.0
    environment:
      ENCRYPT_KEY_STORE_LOCATION: file:/run/config-keys/config-server.p12
      ENCRYPT_KEY_STORE_PASSWORD: ${CONFIG_KEYSTORE_PASSWORD}
      ENCRYPT_KEY_STORE_ALIAS: config-encryption
      ENCRYPT_KEY_STORE_SECRET: ${CONFIG_KEY_PASSWORD}
    volumes:
      - ./secure-keys/config-server.p12:/run/config-keys/config-server.p12:ro
    ports:
      - "127.0.0.1:8888:8888"
~~~

Đường dẫn ở bên trái là file trên host; đường dẫn bên phải là file trong container. Mount read-only để Config Server chỉ đọc keystore. Trong production, dùng Docker secrets, Kubernetes Secret được mã hóa tại rest, external secret operator hoặc secret manager của nền tảng thay cho thư mục local.

Giới hạn quyền đọc file theo user chạy Config Server. Không copy keystore vào image bằng Dockerfile, vì private key có thể còn trong các image layer và registry history ngay cả khi file bị xóa ở layer sau. Không in biến môi trường chứa password trong log hoặc lệnh chẩn đoán.

## 6. Mã hóa giá trị bằng endpoint /encrypt

Config Server cung cấp endpoint POST /encrypt để mã hóa plaintext bằng bộ mã hóa đang cấu hình. Ví dụ:

~~~bash
curl --fail --silent --show-error -X POST -H "Content-Type: text/plain" --data-binary "replace-with-a-test-secret" https://config.example.internal/encrypt
~~~

Response là ciphertext. Với RSA, nội dung được mã hóa bằng public key của key entry đang hoạt động; private key tương ứng được dùng ở bước giải mã.

Không gửi secret production qua endpoint không được bảo vệ. Endpoint /encrypt nhận plaintext, vì vậy cần HTTPS, xác thực, phân quyền và audit. Nếu pipeline gọi endpoint này, giới hạn quyền của pipeline và tránh lưu request body hoặc response chứa dữ liệu nhạy cảm trong log CI.

Có thể lấy public key qua endpoint GET /key:

~~~bash
curl --fail --silent --show-error https://config.example.internal/key
~~~

Endpoint trả public key tương ứng với cấu hình mã hóa bất đối xứng đang hoạt động. Public key không phải bí mật và có thể được phân phối cho nhóm hoặc pipeline cần mã hóa dữ liệu. Tuy vậy, hãy xác nhận nguồn public key đáng tin cậy và kiểm soát endpoint theo chính sách của tổ chức.

Nếu muốn mã hóa offline, công cụ thực hiện phải dùng đúng public key, thuật toán và định dạng ciphertext tương thích với Spring Cloud Config. Không giả định mọi công cụ OpenSSL hoặc mọi padding RSA đều tạo ciphertext có thể giải mã bởi server; hãy kiểm tra bằng một giá trị thử nghiệm trước khi đưa vào pipeline.

## 7. Lưu ciphertext trong Git với tiền tố {cipher}

Sau khi nhận ciphertext từ endpoint /encrypt, đặt nó vào property tương ứng và thêm tiền tố {cipher}. Ví dụ YAML:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "{cipher}AQB-example-ciphertext-from-encrypt-endpoint"
~~~

Ví dụ properties:

~~~properties
spring.datasource.username=orders_app
spring.datasource.password={cipher}AQB-example-ciphertext-from-encrypt-endpoint
~~~

Trong YAML, nên đặt giá trị có tiền tố {cipher} trong dấu nháy để parser coi toàn bộ nội dung là một chuỗi. Thay chuỗi minh họa bằng ciphertext thực do Config Server hoặc công cụ tương thích tạo ra.

Commit file cấu hình đã mã hóa vào repository theo quy trình review bình thường. Người review có thể thấy key nào được mã hóa và ciphertext đã thay đổi, nhưng không cần nhìn thấy plaintext. Vẫn phải giới hạn quyền đọc repository và kiểm soát lịch sử commit; ciphertext không phải lý do để công khai repository.

Không mã hóa toàn bộ file một cách tùy tiện. Chỉ mã hóa giá trị thực sự nhạy cảm như password, API token hoặc credential. Các thuộc tính không nhạy cảm như timeout, pool size và endpoint nên giữ dạng rõ để review, diff và vận hành dễ dàng.

## 8. Config Server giải mã trước khi trả Environment

Khi Config Client yêu cầu cấu hình theo application, profile và label, Config Server đọc các property source từ backend. Nếu giá trị có tiền tố {cipher}, server dùng private key từ keystore để giải mã trước khi trả Environment.

Ví dụ file trong Git:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "{cipher}AQB-example-ciphertext"
~~~

Config Client nhận thuộc tính đã giải mã trong Environment, về mặt logic tương đương:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: plaintext-value-delivered-to-client
~~~

Ví dụ thứ hai chỉ minh họa trạng thái sau giải mã; không ghi plaintext thật vào repository. Config Server không gửi private key cho client. Tuy nhiên, plaintext vẫn được truyền đến client sau khi giải mã, nên kết nối Config Server phải được bảo vệ bằng TLS và client phải được xác thực/phân quyền.

Nếu giải mã thất bại, Spring Cloud Config có thể đánh dấu property không hợp lệ, ví dụ tạo key hậu tố .invalid và giá trị invalid trong Environment. Cần kiểm tra log Config Server và response Environment để phát hiện lỗi; không để ứng dụng tiếp tục với credential mặc định hoặc chuỗi ciphertext chưa giải mã.

Client không nên tự gọi /decrypt để giải mã secret. Luồng chuẩn là Config Server giải mã khi tạo Environment rồi client nhận giá trị cần dùng. Việc cấp private key cho từng client sẽ phá vỡ mô hình tập trung và mở rộng đáng kể phạm vi rò rỉ khóa.

## 9. Kiểm tra mã hóa và giải mã

Có thể kiểm thử toàn bộ chu trình trong môi trường phát triển bằng một secret giả:

1. Khởi động Config Server với keystore và alias đã cấu hình.
2. Gửi plaintext thử nghiệm đến POST /encrypt.
3. Lưu ciphertext tạm thời trong file cấu hình test với tiền tố {cipher}.
4. Gọi POST /decrypt với ciphertext để xác nhận giá trị ban đầu.
5. Gọi endpoint Environment của application/profile/label chứa property đã mã hóa.
6. Xác nhận Config Server trả giá trị đã giải mã cho client được phép.
7. Kiểm tra log và artifact không chứa plaintext ngoài ý muốn.

Ví dụ gọi /decrypt:

~~~bash
curl --fail --silent --show-error -X POST -H "Content-Type: text/plain" --data-binary "AQB-example-ciphertext" https://config.example.internal/decrypt
~~~

Chỉ dùng ciphertext thực lấy từ lần gọi /encrypt. Endpoint /decrypt có thể trả plaintext trực tiếp; không lưu response vào log hoặc ticket. Hãy thực hiện kiểm thử bằng secret giả và xóa dữ liệu thử nghiệm sau khi hoàn tất.

Kiểm tra Environment từ Config Server:

~~~bash
curl --fail --silent --show-error https://config.example.internal/orders-service/prod/main
~~~

Response JSON có thể chứa giá trị đã giải mã. Khi kiểm tra production, chỉ xác minh property source hoặc sự hiện diện của key; tránh in hoặc lưu giá trị secret. Endpoint Environment cũng cần xác thực và phân quyền vì nó có thể cung cấp dữ liệu nhạy cảm.

## 10. Quản lý alias và nhiều cặp khóa

Alias xác định key entry mà Config Server dùng. Ví dụ một keystore có thể có các alias:

~~~text
config-encryption-2025
config-encryption-2026
config-encryption-staging
~~~

Tách alias có thể hỗ trợ môi trường hoặc giai đoạn phát hành khác nhau, nhưng một cấu hình Config Server thông thường chọn một alias hoạt động qua encrypt.key-store.alias. Không giả định chỉ thêm nhiều alias vào keystore sẽ tự động khiến server thử lần lượt tất cả private key khi giải mã.

Có thể dùng keystore riêng cho từng môi trường để giảm phạm vi ảnh hưởng. Ví dụ staging và production không dùng chung private key; một sự cố ở môi trường thử nghiệm không làm lộ khả năng giải mã ciphertext production. Nếu nhiều Config Server replica phục vụ cùng một môi trường, chúng phải đồng nhất alias và private key để giải mã nhất quán.

Không dùng lại một alias chung cho nhiều mục đích nếu chính sách yêu cầu tách quyền. Alias không phải cơ chế phân quyền; quyền truy cập file keystore, mật khẩu và danh tính workload mới quyết định ai có thể sử dụng private key.

## 11. Xoay vòng khóa và tái mã hóa dữ liệu

Private key cần có vòng đời, chủ sở hữu, nơi lưu backup và kế hoạch thay thế. Khi tạo key pair mới, ciphertext cũ vẫn được mã hóa bằng public key cũ. Nếu Config Server chỉ được cấu hình với private key mới, server không thể giải mã ciphertext cũ.

Một quy trình rotation cần giữ khả năng giải mã trong suốt giai đoạn chuyển đổi:

1. Tạo key pair mới và lưu keystore mới trong secret storage.
2. Backup keystore cũ ở vị trí được mã hóa, giới hạn quyền và có thể khôi phục.
3. Xác định toàn bộ property có tiền tố {cipher}, application/profile/label và revision chứa chúng.
4. Dùng quy trình migration được kiểm soát để giải mã ciphertext cũ bằng private key cũ và mã hóa lại bằng public key mới.
5. Chỉ ghi ciphertext mới vào Git; không ghi plaintext ra file tạm, log hoặc artifact.
6. Kiểm thử giải mã ciphertext mới trên Config Server đã cấu hình key mới.
7. Triển khai đồng bộ keystore mới đến mọi Config Server replica.
8. Refresh hoặc rollout client theo quy trình.
9. Xác nhận không còn ciphertext cần private key cũ.
10. Chỉ thu hồi hoặc hủy key cũ sau khi hết thời gian rollback và đã xác nhận migration hoàn tất.

Cấu hình alias đơn lẻ không tự tạo cơ chế dual-key rotation. Nếu cần giải mã đồng thời ciphertext cũ và mới trong thời gian chuyển tiếp, phải thiết kế migration service hoặc cơ chế key locator tùy chỉnh có kiểm soát, hoặc chạy quy trình chuyển đổi theo giai đoạn. Đừng đổi alias trên production trước khi đã có kế hoạch xử lý mọi ciphertext đang lưu bằng khóa cũ.

Ghi nhận key ID hoặc alias version trong metadata phát hành để truy vết. Không ghi private key, password hoặc plaintext secret vào metadata. Giữ backup private key cũ đủ lâu để rollback nhưng giới hạn người và workload có thể truy cập.

## 12. Giới hạn và lựa chọn thuật toán

RSA phù hợp với các giá trị bí mật ngắn như password, token hoặc credential. Mã hóa RSA có giới hạn kích thước plaintext phụ thuộc key size và padding; không dùng nó để mã hóa file lớn hoặc toàn bộ cấu hình dài. Nếu cần bảo vệ lượng dữ liệu lớn, dùng cơ chế mã hóa đối xứng hoặc secret manager phù hợp, với quy trình quản lý khóa riêng.

Việc chọn key size, padding, provider và định dạng ciphertext phải tương thích giữa bên mã hóa và Config Server. Một ciphertext tạo bằng công cụ khác có thể không giải mã được nếu padding hoặc encoding khác với implementation mà Spring Cloud Config sử dụng. Hãy kiểm thử liên thông trên đúng phiên bản trước khi phát hành.

Mã hóa bất đối xứng cũng không chứng minh người tạo ciphertext là người có quyền thay đổi cấu hình. Bất kỳ ai có public key đều có thể mã hóa dữ liệu mới; quyền thay đổi Git repository, review pull request và quyền gọi Config Server vẫn phải được kiểm soát riêng.

## 13. Bảo mật endpoint và dữ liệu đã giải mã

Các endpoint mã hóa và giải mã có mức độ nhạy cảm khác nhau:

| Endpoint | Vai trò | Kiểm soát |
| --- | --- | --- |
| GET /key | Cung cấp public key | Có thể phân phối rộng hơn, nhưng phải bảo đảm tính xác thực của nguồn khóa |
| POST /encrypt | Nhận plaintext và trả ciphertext | Xác thực, phân quyền, TLS, audit và hạn chế log body |
| POST /decrypt | Nhận ciphertext và trả plaintext | Quyền rất hạn chế, chỉ công cụ vận hành được phê duyệt |
| GET /{application}/{profile}/{label} | Trả Environment đã giải mã | Phân quyền theo application/môi trường và bảo vệ TLS |

Không expose /encrypt hoặc /decrypt công khai. Nếu pipeline cần gọi /encrypt, dùng identity riêng có quyền tối thiểu và chỉ cho phép truy cập từ network CI được kiểm soát. Endpoint /decrypt nên giới hạn nghiêm ngặt hơn vì response là plaintext.

Các biện pháp bổ sung:

- Lưu keystore và password trong secret manager hoặc secret volume.
- Giới hạn quyền đọc keystore theo user chạy Config Server.
- Bảo vệ Git repository và review mọi thay đổi ciphertext.
- Dùng TLS giữa Config Client và Config Server.
- Xác thực client, giới hạn quyền đọc application/profile.
- Không expose Actuator env/configprops hoặc endpoint cấu hình không cần thiết.
- Không log request body, plaintext, private key hoặc keystore password.
- Kiểm soát backup và quy trình khôi phục keystore.
- Theo dõi truy cập endpoint và hành vi giải mã bất thường.

Khi Config Server trả Environment, plaintext có thể xuất hiện trong bộ nhớ của client, bean cấu hình hoặc thư viện kết nối. Cần bảo vệ log, heap dump, diagnostic endpoint và quyền truy cập vào tiến trình ứng dụng.

## 14. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Config Server không khởi động | Sai location, mật khẩu hoặc alias | Kiểm tra keystore tồn tại, mở được và alias có trong entry |
| /encrypt trả lỗi | Thiếu dependency mã hóa, keystore không nạp được hoặc request sai | Kiểm tra dependency và log server |
| /decrypt không khôi phục plaintext | Ciphertext được tạo bằng key khác, padding khác hoặc bị cắt | Dùng ciphertext mới từ cùng server để kiểm tra |
| Client nhận giá trị invalid | Config Server không giải mã được giá trị {cipher} | Kiểm tra alias, private key, ciphertext và server log |
| Một replica giải mã được, replica khác lỗi | Các replica dùng keystore hoặc alias khác nhau | So sánh key version và cấu hình runtime |
| Đổi alias làm cấu hình cũ lỗi | Ciphertext cũ vẫn dùng public key trước đó | Khôi phục khả năng giải mã khóa cũ hoặc hoàn tất migration |
| Secret xuất hiện trong log | Debug response hoặc in toàn bộ Environment | Loại bỏ log body và rà soát quyền Actuator |
| Keystore không đọc được trong container | Sai mount path hoặc file permission | Kiểm tra volume, URI file và user chạy server |

Khi chẩn đoán, kiểm tra theo thứ tự: Config Server có đọc được keystore không; alias có đúng không; endpoint /encrypt có tạo ciphertext không; /decrypt có khôi phục đúng secret thử nghiệm không; property trong Git có tiền tố và ciphertext đầy đủ không; client có lấy Environment từ đúng server/profile/label không.

Không thử khắc phục bằng cách đưa private key vào client hoặc commit mật khẩu keystore vào repository. Nếu nghi ngờ private key đã lộ, xem đó là sự cố khóa và thực hiện rotation theo quy trình, đồng thời đánh giá các secret từng được mã hóa bằng khóa đó.

## 15. Nguyên tắc sử dụng trong hệ thống nhiều ứng dụng

- Dùng public key để mã hóa; giữ private key trong keystore được bảo vệ tại Config Server.
- Dùng alias để chọn key entry rõ ràng và có quy ước version.
- Cấp keystore password và key password qua secret manager.
- Lưu giá trị đã mã hóa trong Git với tiền tố {cipher}; giữ các thuộc tính không nhạy cảm ở dạng rõ.
- Để Config Server giải mã trước khi gửi Environment; không phân phối private key cho Config Client.
- Đồng nhất keystore và alias giữa các replica của cùng môi trường.
- Kiểm thử mã hóa/giải mã bằng secret giả trước khi phát hành.
- Lập kế hoạch re-encrypt ciphertext khi xoay vòng khóa; không xóa key cũ quá sớm.
- Bảo vệ /encrypt, /decrypt, Config Server API và log.
- Dùng Vault hoặc secret manager khi cần quản lý secret theo policy, version và rotation chuyên biệt.

Mã hóa bất đối xứng giúp tách quyền mã hóa khỏi quyền giải mã: public key có thể được dùng trong quy trình tạo cấu hình, còn private key được giữ ở Config Server. Keystore lưu cặp khóa, alias chọn entry và các mật khẩu bảo vệ quyền truy cập. Khi ciphertext được lưu trong Git với tiền tố {cipher}, Config Server giải mã trước khi phân phối Environment. Quy trình chỉ an toàn khi private key được bảo vệ, endpoint được kiểm soát, các replica dùng khóa nhất quán và rotation có kế hoạch tái mã hóa toàn bộ dữ liệu liên quan.

