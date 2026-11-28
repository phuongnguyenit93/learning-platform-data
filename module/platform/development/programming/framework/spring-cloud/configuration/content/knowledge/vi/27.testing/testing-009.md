# Gây lỗi timeout, mất quyền, label thiếu và ciphertext không hợp lệ

Kiểm thử Spring Cloud Config không chỉ xác nhận trường hợp Config Server trả cấu hình đúng. Một hệ thống cấu hình tập trung còn phải có hành vi an toàn khi mạng bị gián đoạn, thông tin xác thực sai, Git label không tồn tại hoặc Config Server không giải mã được secret.

Bài thực hành này tạo bốn nhóm lỗi có chủ đích trong môi trường cô lập. Với mỗi nhóm, cần ghi nhận request, response, log ở đúng thành phần và trạng thái cuối của Config Client. Mục tiêu là xác nhận ứng dụng **thất bại đúng cách**, không dùng cấu hình cũ hoặc ciphertext như thể đó là secret hợp lệ.

## 1. Mục tiêu và phạm vi kiểm thử

Sau bài này, người học có thể:

- Tái hiện lỗi connect timeout và read timeout giữa Config Client với Config Server.
- Phân biệt lỗi client không kết nối được Config Server với lỗi Config Server không truy cập được Git backend.
- Kiểm tra 401/403 khi client thiếu quyền hoặc dùng credential sai.
- Kiểm tra lỗi quyền đọc repository ở phía Config Server.
- Gọi một label không tồn tại và nhận diện hành vi default-label/fallback.
- Tạo ciphertext không giải mã được và xác minh response có `invalid.<property>`.
- Đặt tiêu chí fail-fast, retry, fallback và kiểm tra secret bắt buộc.
- Viết ma trận kiểm thử âm có thể chạy lại trong CI/staging.

```mermaid
flowchart TD
    C[Config Client] -->|1. Timeout / 401 / 403| S[Config Server]
    S -->|2. Git credentials / network| G[(Git backend)]
    S -->|3. application/profile/label| R[Git ref và property files]
    R -->|4. {cipher} value| D[Server-side decrypt]
    D -->|Thành công| E[Environment response]
    D -->|Thất bại| I[invalid.property = <n/a>]
    E --> C
    I --> C
```

## 2. Chuẩn bị môi trường thử nghiệm an toàn

Dùng một Config Server và Config Client dành riêng cho lab. Repository cấu hình chỉ chứa giá trị giả, không dùng password database, token, private key hoặc credential thật.

Các thành phần cần có:

- Git repository kiểm thử có branch `main` và một branch/tag được tạo có chủ đích.
- Spring Cloud Config Server trỏ tới repository lab.
- Một Config Client dùng `spring-cloud-starter-config`.
- Một lớp tạo độ trễ hoặc ngắt kết nối, ví dụ WireMock, Toxiproxy hoặc firewall rule trong network namespace kiểm thử.
- Một bộ khóa mã hóa dành riêng cho lab để Config Server giải mã giá trị `{cipher}`.

Ví dụ cấu hình Git backend phía Config Server:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.test/config-lab.git
          default-label: main
          try-master-branch: false
          clone-on-start: true
          refresh-rate: 0

encrypt:
  key: ${CONFIG_LAB_ENCRYPT_KEY}
```

`try-master-branch: false` giúp bài lab không vô tình chuyển sang branch `master` khi label mặc định `main` không tồn tại. `clone-on-start: true` khiến lỗi repository có thể được phát hiện ngay khi Config Server khởi động. Trong một số bài test backend authorization, có thể tắt clone-on-start để quan sát lỗi ở request đầu tiên.

Tạo một file cấu hình dùng chung:

```yaml
# application.yml
lab:
  marker: config-lab
  required-secret-name: payment.api-key
```

Tạo file theo application và profile:

```yaml
# order-service-production.yml
payment:
  endpoint: https://payments.example.test
  timeout: 3s
  api-key: '{cipher}VALID_LAB_CIPHERTEXT'
```

Giá trị `VALID_LAB_CIPHERTEXT` chỉ là placeholder minh họa. Khi thực hành kiểm thử giải mã, thay bằng ciphertext được tạo bằng khóa lab, hoặc bằng một chuỗi cố ý không hợp lệ ở bước tương ứng.

## 3. Kiểm thử timeout giữa Config Client và Config Server

Có hai loại timeout khác nhau:

- **Connect timeout:** thời gian tối đa client chờ thiết lập kết nối TCP tới Config Server.
- **Read timeout:** thời gian tối đa client chờ dữ liệu response sau khi kết nối đã được thiết lập.

Spring Cloud Config Client cấu hình chúng bằng `spring.cloud.config.request-connect-timeout` và `spring.cloud.config.request-read-timeout`. Giá trị số được tính bằng mili giây.

Ví dụ cấu hình client với timeout ngắn để kiểm thử:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      request-connect-timeout: 1000
      request-read-timeout: 1500
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 3
        initial-interval: 250
        max-interval: 500
        multiplier: 1.5
```

Với Spring Cloud Config 5.1, retry cần `fail-fast: true` và `spring.cloud.config.retry.enabled: true`. `max-attempts` tính cả lần gọi đầu tiên; `3` nghĩa là tối đa ba lần gọi, gồm một lần đầu và hai lần retry. Các khoảng backoff ở ví dụ là mili giây.

Nếu dùng phiên bản Spring Cloud Config cũ hơn 5.1, cơ chế retry có thể yêu cầu Spring Retry trên classpath. Hãy đối chiếu release train của dự án trước khi áp dụng dependency hoặc cấu hình retry.

### 3.1. Tái hiện connect timeout

Một cổng không có process lắng nghe thường trả lỗi `Connection refused` rất nhanh; đó không phải lúc nào cũng là timeout. Để kiểm thử connect timeout thực sự, cần mô phỏng gói tin bị drop hoặc một đường mạng không hoàn tất bắt tay TCP. Có thể dùng Toxiproxy hoặc network policy trong môi trường lab.

Quy trình:

1. Cho client gọi Config Server qua proxy kiểm thử.
2. Cấu hình proxy drop kết nối hoặc không phản hồi SYN/ACK.
3. Khởi động client với `request-connect-timeout: 1000`.
4. Ghi thời gian từ lúc khởi động tới khi client báo lỗi.
5. Xác minh client không chờ vô hạn và không nhận một bộ cấu hình không đầy đủ.

Kết quả mong đợi là lỗi kết nối/timeout xuất hiện gần ngưỡng đã cấu hình, có thể dài hơn một chút do scheduler và retry. Nếu retry bật, tổng thời gian khởi động còn phụ thuộc số lần thử và backoff.

### 3.2. Tái hiện read timeout

Read timeout xảy ra khi TCP đã kết nối nhưng Config Server không gửi response trong khoảng thời gian cho phép. Dùng WireMock hoặc một HTTP stub để trả response sau một độ trễ lớn hơn `request-read-timeout`.

Ví dụ WireMock mapping cho một endpoint cấu hình:

```json
{
  "request": {
    "method": "GET",
    "urlPathMatching": "/order-service/.*"
  },
  "response": {
    "status": 200,
    "fixedDelayMilliseconds": 4000,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "name": "order-service",
      "profiles": ["production"],
      "label": "main",
      "version": "lab-version",
      "propertySources": []
    }
  }
}
```

Cho client gọi WireMock qua cổng thử nghiệm, đặt read timeout 1.500 ms và fixed delay 4.000 ms. Client phải timeout trước khi stub trả response.

### 3.3. Kiểm tra fail-fast và optional import

Với Config Data import:

```yaml
spring:
  config:
    import: "configserver:http://localhost:8888"
```

Import không có tiền tố `optional:` là bắt buộc. Nếu Config Server không truy cập được và các lần retry thất bại, ứng dụng phải dừng khởi động.

Nếu viết:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

ứng dụng có thể tiếp tục bằng các nguồn cấu hình còn lại khi Config Server không sẵn sàng. Chỉ dùng cách này nếu fallback local đã được thiết kế an toàn và các secret bắt buộc vẫn được kiểm tra trước khi nhận traffic.

Nếu `spring.config.import` được đặt trong file profile-specific, các tham số retry có thể được đặt ngay trên URL import:

```yaml
spring:
  config:
    import: "configserver:http://localhost:8888?fail-fast=true&max-attempts=3&initial-interval=250&max-interval=500&multiplier=1.5"
```

Với import profile-specific, dùng query parameters theo cú pháp tài liệu Config Data thay vì giả định retry properties trong một file khác đã được nạp trước location đó.

### 3.4. Phân biệt lỗi client–server với lỗi server–Git

Config Client có thể kết nối Config Server thành công, nhưng Config Server lại không thể đọc Git backend. Đây là một chặng mạng khác và có timeout riêng.

Ví dụ Git backend:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.test/config-lab.git
          timeout: 2
          clone-on-start: true
```

`spring.cloud.config.server.git.timeout` được tính bằng giây và điều khiển thời gian chờ kết nối HTTP/SSH tới Git server. Nó không thay thế `request-connect-timeout` hoặc `request-read-timeout` ở Config Client.

Một chi tiết quan trọng khi kiểm thử: sau khi Config Server clone repository thành công, nó giữ working copy cục bộ. Nếu Git server mất kết nối sau đó, Config Server có thể tiếp tục phục vụ cấu hình từ bản local đã có. Để kiểm thử lỗi clone/permission một cách xác định, dùng một Config Server lab mới hoặc một repository/cache chưa từng clone; đừng chỉ chặn Git server sau khi clone thành công rồi kỳ vọng mọi request đều thất bại.

## 4. Kiểm thử mất quyền truy cập Config Server

Mất quyền có thể xảy ra ở hai vị trí độc lập:

1. Config Client không được phép gọi Config Server.
2. Config Server không được phép đọc Git repository.

Không gộp hai tình huống thành một bài test vì thành phần phát sinh lỗi và cách khắc phục khác nhau.

### 4.1. Client thiếu hoặc sai credential

Nếu Config Server dùng HTTP Basic, client có thể cấu hình username/password qua environment variables:

```yaml
spring:
  cloud:
    config:
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

Kiểm thử ba trường hợp:

| Trường hợp | Cách thực hiện | Kết quả HTTP mong đợi |
|---|---|---|
| Không gửi credential | Gọi endpoint mà không có Authorization header | `401 Unauthorized` nếu server yêu cầu xác thực Basic |
| Credential sai | Gửi username/password không hợp lệ | `401 Unauthorized` |
| Đã xác thực nhưng thiếu role | Dùng tài khoản hợp lệ nhưng không có quyền đọc cấu hình | `403 Forbidden` theo security policy |

Ví dụ gọi endpoint không có credential:

```bash
curl --include \
  http://localhost:8888/order-service/production/main
```

Ví dụ gọi với credential được cấp từ môi trường:

```bash
curl --include \
  --user "${CONFIG_SERVER_USERNAME}:${CONFIG_SERVER_PASSWORD}" \
  http://localhost:8888/order-service/production/main
```

Không đặt password thật trực tiếp trong command line hoặc commit vào YAML. Một số shell lưu lệnh trong history; process inspection hoặc log proxy cũng có thể làm lộ credential. Dùng biến môi trường của phiên kiểm thử hoặc secret injection và xóa chúng sau lab.

Khi dùng `spring.cloud.config.multiple-uri-strategy: connection-timeout-only`, lỗi 401/403 không được xem là lỗi kết nối để chuyển sang URI dự phòng. Với chiến lược `always`, client có thể thử URL kế tiếp khi request thất bại; cần kiểm tra chính sách phiên bản đang dùng và tránh để failover che giấu lỗi phân quyền chung.

### 4.2. Config Server mất quyền đọc Git

Đặt credential Git trong cấu hình Config Server bằng secret injection:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.test/config-lab.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_PASSWORD}
          clone-on-start: true
```

Tái hiện lỗi bằng tài khoản Git không có quyền đọc repository hoặc token đã bị thu hồi. Chạy một Config Server lab mới để tránh sử dụng working copy đã clone trước đó.

Kết quả cần quan sát:

- Nếu `clone-on-start: true`, Config Server có thể thất bại ngay trong quá trình khởi động vì không clone được repository.
- Nếu clone-on-start tắt, lỗi có thể chỉ xuất hiện ở request đầu tiên cần đọc repository.
- Log server phải cho biết lỗi authentication/authorization ở Git backend, nhưng không được ghi password/token.
- HTTP status mà client nhận phụ thuộc exception và xử lý lỗi của phiên bản/backend; cần kiểm tra response cùng server log thay vì giả định mọi lỗi Git đều là 401/403 từ Config Server.

### 4.3. Phân biệt hai đường quyền truy cập

| Đường đi | Danh tính cần có quyền | Nơi kiểm tra |
|---|---|---|
| Client → Config Server | Service account/client identity | Spring Security, gateway, OAuth2 hoặc mTLS của Config Server |
| Config Server → Git | Credential/SSH key của Config Server | Git provider, repository permission, deploy key/token |

Một client có quyền gọi Config Server không có nghĩa Config Server có quyền đọc Git. Ngược lại, Config Server đọc được Git cũng không có nghĩa mọi client đều được phép lấy mọi application/profile.

## 5. Kiểm thử label không tồn tại

Config Server Git backend ánh xạ `{label}` thành branch, tag hoặc commit ID. Gọi trực tiếp endpoint với label cố ý không tồn tại:

```bash
curl --include \
  http://localhost:8888/order-service/production/no-such-label
```

Nếu `no-such-label` không phải branch, tag hoặc commit trong repository, Config Server sẽ báo lỗi không tìm thấy label. Tùy phiên bản và cách backend ánh xạ exception, HTTP status/response body có thể khác nhau; kiểm tra log để xác nhận nguyên nhân `NoSuchLabelException` hoặc ref không thể resolve.

### 5.1. Kiểm tra default label và fallback `main`/`master`

Config Server Git backend hiện dùng `main` làm default label. Nếu không khai báo `default-label`, branch `main` không tồn tại và `try-master-branch` được bật, server có thể thử branch `master`.

Để test thiếu label một cách xác định, khai báo:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          default-label: main
          try-master-branch: false
```

Sau đó:

1. Tạo repository lab chỉ có branch `main`.
2. Gọi `/order-service/production/main` và xác nhận request thành công.
3. Gọi `/order-service/production/no-such-label` và xác nhận request lỗi.
4. Đổi `default-label` thành một label không tồn tại trong một Config Server lab mới.
5. Xác nhận server không tự chuyển sang `master` khi `try-master-branch: false`.

Không dùng fallback `master` để che lỗi đặt sai tên branch release. Nếu quy trình yêu cầu một label cụ thể, hãy cấu hình tường minh và kiểm tra label trước khi rollout.

### 5.2. Kiểm tra label có dấu `/`

Nếu branch hoặc tag chứa dấu `/`, ví dụ `release/2026.11`, URL Config Server cần thay dấu `/` trong label bằng chuỗi đặc biệt `(_)` để tránh nhầm với segment URL:

```bash
curl --include \
  'http://localhost:8888/order-service/production/release(_)2026.11'
```

Trong bài test, trước hết thử label đơn giản như `main` để tách lỗi thiếu ref khỏi lỗi URL encoding. Sau đó mới kiểm tra branch có dấu `/`.

### 5.3. Cẩn thận với danh sách nhiều label

Config Client có thể được cấu hình danh sách label phân tách bằng dấu phẩy. Hành vi nhiều label phụ thuộc phiên bản Config Client/Server và thuộc tính `spring.cloud.config.send-all-labels`. Với Config Server Git backend, nếu request chứa nhiều label và một label không resolve được, mặc định server có thể trả lỗi thay vì tự bỏ qua label đó. Có thể cấu hình `spring.cloud.config.server.git.continue-on-multiple-label-failure: true` nếu muốn server tiếp tục thử các label còn lại.

Để kiểm thử một label thiếu, chỉ gửi đúng một label. Không dùng danh sách fallback trong bài test cơ bản vì sẽ khó xác định request thành công nhờ label nào.

## 6. Kiểm thử ciphertext không hợp lệ

Khi Config Server nhận một property có tiền tố `{cipher}`, server cố giải mã bằng key/encryptor đã cấu hình. Nếu giải mã thất bại, server loại property gốc khỏi property source và thêm key có tiền tố `invalid`, thường có giá trị `<n/a>`.

Tạo một file trong repository lab:

```yaml
# order-service-production.yml
payment:
  endpoint: https://payments.example.test
  api-key: '{cipher}not-a-valid-ciphertext'
```

Đảm bảo Config Server có khóa lab được cấu hình để việc test thực sự đi qua bước decrypt. Nếu server không có encryptor/key hoặc cấu hình sai, đó cũng là một tình huống lỗi giải mã cần ghi nhận riêng. Chuỗi giả ở ví dụ không phải ciphertext hợp lệ và không chứa secret thật.

Gọi Environment endpoint:

```bash
curl --fail --silent --show-error \
  http://localhost:8888/order-service/production/main
```

Trong `propertySources`, tìm key tương tự:

```json
{
  "source": {
    "payment.endpoint": "https://payments.example.test",
    "invalid.payment.api-key": "<n/a>"
  }
}
```

Kết quả mong đợi là `invalid.payment.api-key` xuất hiện và `payment.api-key` của source bị lỗi không còn được trả dưới tên gốc.

### 6.1. Kiểm tra nguy cơ fallback

Giả sử một property source thấp hơn có giá trị `payment.api-key`. Khi source profile-specific không giải mã được và key bị đổi thành `invalid.payment.api-key`, client có thể phân giải `payment.api-key` từ source thấp hơn.

Để nhìn thấy tình huống này trong lab, có thể tạm thêm một sentinel không nhạy cảm vào `application.yml`:

```yaml
payment:
  api-key: DO_NOT_USE_FALLBACK
```

Khi truy vấn profile production có ciphertext lỗi, kiểm tra response có cả `invalid.payment.api-key` ở source profile-specific và `payment.api-key` ở source dùng chung. Ứng dụng kiểm thử phải từ chối sentinel `DO_NOT_USE_FALLBACK`. Đây chỉ là dữ liệu minh họa trong repository lab, tuyệt đối không dùng fallback plaintext cho secret thật.

Đây là lý do không nên có fallback plaintext yếu cho secret bắt buộc. Bài test cần xác minh:

- Response có `invalid.payment.api-key`.
- Ứng dụng không âm thầm dùng secret mặc định không đúng môi trường.
- Startup validation hoặc readiness check từ chối nhận traffic khi secret bắt buộc thiếu.
- Log chỉ ghi tên property và trạng thái lỗi, không ghi ciphertext, plaintext hoặc key mã hóa.

Không kiểm tra secret bằng cách in toàn bộ Environment hoặc `/actuator/env` ra log. Dùng một assertion boolean hoặc health indicator chỉ trả trạng thái “present/valid”.

### 6.2. Không tắt dấu `invalid` để bài test xanh giả

`spring.cloud.config.server.encrypt.prefix-invalid-properties` mặc định bật. Nếu đặt thành `false`, Config Server giữ ciphertext dưới tên key gốc trong response. Khi đó client có thể nhận chuỗi ciphertext như giá trị của password/API key.

Trong bài kiểm thử, hãy giữ mặc định bật và xác nhận key `invalid.*`. Có thể chạy một test phụ với prefix bị tắt để minh họa rủi ro, nhưng không dùng cấu hình đó trong production.

### 6.3. Cú pháp YAML và properties

Với YAML, đặt giá trị `{cipher}` trong dấu nháy:

```yaml
payment:
  api-key: '{cipher}INVALID_TEST_VALUE'
```

Với `.properties`, không bọc encrypted value trong dấu nháy:

```properties
payment.api-key={cipher}INVALID_TEST_VALUE
```

Nếu `.properties` bọc ciphertext trong quotes, Config Server có thể không nhận diện và giải mã như mong đợi. Khi kiểm thử, xác minh đúng format trước khi kết luận khóa giải mã sai.

## 7. Ma trận kiểm thử lỗi

| Nhóm lỗi | Cách gây lỗi | Bằng chứng phía server/client | Kết quả an toàn mong đợi |
|---|---|---|---|
| Connect timeout | Drop TCP handshake qua proxy/firewall lab | Client log có connect timeout; request không tới Config Server | Client fail theo fail-fast/retry policy; không chờ vô hạn |
| Read timeout | Server/stub chấp nhận kết nối nhưng trì hoãn response | Client log có read timeout; server có thể ghi nhận request | Client dừng theo timeout/retry budget; không dùng response một phần |
| Config Server 401 | Thiếu hoặc sai credential | HTTP 401, security log có danh tính/đường dẫn nhưng không có password | Client không nhận cấu hình; không fallback sang local secret yếu |
| Config Server 403 | Đã xác thực nhưng thiếu quyền | HTTP 403 và authorization log | Request bị từ chối; không cấp quyền rộng để vượt test |
| Git backend access denied | Config Server dùng token/deploy key không có quyền | Git clone/fetch log báo authorization; lỗi có thể xuất hiện lúc startup hoặc request đầu | Server không phục vụ dữ liệu mới như thể fetch thành công; alert rõ nguồn lỗi |
| Label không tồn tại | Request branch/tag/commit không có trong repo | Config Server báo ref/label không resolve | Request lỗi; không âm thầm dùng branch khác ngoài fallback đã định nghĩa |
| Ciphertext không hợp lệ | Giá trị `{cipher}` bị cố ý làm sai | Response chứa `invalid.<key>`; server có decrypt error log | Secret bắt buộc bị coi là không hợp lệ; ứng dụng fail closed |
| Key giải mã thiếu/sai | Không mount key lab hoặc dùng key khác | Nhiều property mã hóa có thể cùng xuất hiện `invalid.*` | Phân biệt lỗi key/config server với lỗi riêng một ciphertext |

## 8. Kiểm thử bằng curl và assertion tự động

Với mỗi kịch bản, lưu HTTP status và response metadata, nhưng không lưu secret. Ví dụ kiểm tra một label thiếu:

```bash
status=$(curl --silent --output label-error.json \
  --write-out '%{http_code}' \
  http://localhost:8888/order-service/production/no-such-label)

printf 'HTTP status: %s\n' "$status"
```

Kiểm tra status theo phiên bản Config Server và backend đang chạy. Không hard-code cùng một mã HTTP cho mọi exception của Git backend nếu chưa xác nhận.

Với ciphertext lỗi, chỉ kiểm tra tên key và sentinel:

```bash
curl --fail --silent --show-error \
  http://localhost:8888/order-service/production/main \
  | jq -e 'any(.propertySources[]; .source["invalid.payment.api-key"] == "<n/a>")'
```

Lệnh trên xác minh sentinel mà không cần in giá trị secret. Nếu property source có thể thay đổi tên hoặc có nhiều nguồn, điều chỉnh JSON path theo response thực tế của phiên bản đang dùng.

Với kiểm thử 401/403:

```bash
curl --silent --output auth-error.json \
  --write-out '%{http_code}\n' \
  http://localhost:8888/order-service/production/main
```

Không đưa response body chứa stack trace, repository URL nội bộ hoặc thông tin xác thực vào artifact công khai. Nếu cần lưu bằng chứng, lọc response và log trước khi đính kèm vào test report.

## 9. Đưa các bài test vào CI

Chia test theo phạm vi để tránh suite chậm và khó chẩn đoán:

| Nhóm test | Cách chạy | Tần suất phù hợp |
|---|---|---|
| Label thiếu, ciphertext sai | Integration test với Config Server và repository lab | Mỗi pull request hoặc nightly |
| 401/403 | Integration test với Spring Security test account | Mỗi pull request |
| Read timeout | WireMock fixed delay hoặc proxy fault | Nightly hoặc resilience pipeline |
| Connect timeout | Toxiproxy/network fault injection | Nightly hoặc trước release |
| Git backend permission | Repository test credential/deploy key riêng | Nightly hoặc trước release |
| Git backend outage sau clone | Tắt kết nối Git sau khi Config Server đã clone | Resilience pipeline |

Không chạy fault injection lên Config Server production hoặc repository cấu hình thật. Mỗi job cần namespace, credential và dữ liệu riêng; khi job kết thúc, thu hồi token lab và xóa repository tạm.

## 10. Tiêu chí pass/fail cho từng tình huống

Một test chỉ pass khi chứng minh được cả lỗi dự kiến và hành vi an toàn:

- **Timeout:** request kết thúc trong ngân sách thời gian đã định; retry không vượt quá số lần; ứng dụng không nhận cấu hình thiếu.
- **401/403:** request bị từ chối; không có property source được áp dụng từ request không có quyền; credential không xuất hiện trong log.
- **Git permission:** Config Server không báo đã đồng bộ cấu hình mới khi clone/fetch bị từ chối; lỗi được quan sát ở server log/health.
- **Missing label:** request label không tồn tại thất bại rõ ràng; không âm thầm chuyển sang ref khác ngoài fallback được cấu hình có chủ đích.
- **Invalid ciphertext:** response có `invalid.<key>`; secret bắt buộc không được thay bằng fallback yếu; ứng dụng không nhận traffic khi validation thất bại.

Không dùng tiêu chí “ứng dụng vẫn khởi động” làm chuẩn duy nhất. Trong hệ thống có secret bắt buộc, khởi động thành công với credential cũ hoặc ciphertext có thể nguy hiểm hơn việc dừng khởi động có kiểm soát.

## 11. Troubleshooting theo dấu hiệu

| Dấu hiệu | Kiểm tra trước | Không nên kết luận vội |
|---|---|---|
| Client timeout nhưng Config Server không có access log | DNS, TCP, proxy, connect timeout và route | Không kết luận Git backend lỗi nếu request chưa tới server |
| Config Server nhận request nhưng client read timeout | Server log, Git fetch, decrypt và response latency | Không kết luận client credential sai |
| HTTP 401 | Authorization header, credential source và security chain | Không tăng timeout hoặc retry để sửa lỗi credential |
| HTTP 403 | Role/authority và rule theo application/profile | Không cấp quyền admin rộng chỉ để làm test pass |
| Config Server startup fail khi bật clone-on-start | Git URI, token, deploy key, host key và quyền repository | Không nhầm lỗi này với Config Client không gọi được Config Server |
| Label lỗi dù branch tồn tại trên Git provider | Config Server local clone/cache, ref đã fetch, URL encoding và `refresh-rate` | Không kết luận branch không tồn tại chỉ dựa trên giao diện Git |
| Có `invalid.*` cho nhiều key | Encrypt key/keystore/alias và cấu hình replica | Không mã hóa lại tất cả secret trước khi xác định lỗi key |
| Client dùng fallback sau lỗi decrypt | Thứ tự property source và validation secret bắt buộc | Không xem ứng dụng kết nối thành công là bằng chứng decrypt thành công |

## 12. Checklist hoàn thành bài lab

- [ ] Dùng Config Server, Config Client và Git repository riêng cho lab.
- [ ] Đã đặt connect timeout và read timeout ngắn để tái hiện lỗi.
- [ ] Đã phân biệt connection refused, connect timeout và read timeout.
- [ ] Đã thử fail-fast, optional import và retry budget.
- [ ] Đã kiểm thử timeout riêng trên chặng Config Server tới Git backend.
- [ ] Đã thử thiếu credential, credential sai và authenticated user thiếu role.
- [ ] Đã thử Git credential không có quyền trên một Config Server lab sạch.
- [ ] Đã gọi label không tồn tại và xác minh server log/ref resolution.
- [ ] Đã tắt `try-master-branch` để kiểm tra default label một cách xác định.
- [ ] Đã đưa ciphertext không hợp lệ vào repository lab.
- [ ] Đã xác minh response có `invalid.<key>` và sentinel `<n/a>`.
- [ ] Đã kiểm tra nguy cơ fallback từ property source thấp hơn.
- [ ] Đã xác nhận ứng dụng fail closed khi secret bắt buộc không hợp lệ.
- [ ] Log/test report không chứa plaintext, ciphertext nhạy cảm hoặc credential.
- [ ] Đã thu hồi credential lab và dọn dữ liệu thử nghiệm sau kiểm thử.

## 13. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Thiết kế test tái hiện connect timeout và read timeout ở đúng chặng mạng.
- Cấu hình và kiểm tra fail-fast, optional import, retry và timeout budget.
- Phân biệt quyền truy cập Config Server với quyền truy cập Git backend.
- Kiểm thử 401/403 và giải thích vì sao retry không sửa được lỗi authorization.
- Tái hiện label không tồn tại, hiểu default-label và fallback `main`/`master`.
- Nhận diện `invalid.<property>` khi ciphertext không giải mã được.
- Ngăn fallback không an toàn khi secret bắt buộc bị thiếu hoặc giải mã thất bại.
- Tổ chức fault-injection tests an toàn trong CI/staging và ghi nhận bằng chứng không lộ secret.

**Tự kiểm tra:** Trong staging, Config Client kết nối được Config Server nhưng nhận lỗi khi đọc cấu hình; log Config Server cho thấy Git token bị từ chối. Một test khác trả `invalid.payment.api-key`, trong khi `application.yml` có giá trị mặc định. Hãy phân tích hai lỗi thuộc hai chặng nào, cách tạo lại từng lỗi, bằng chứng cần thu thập và vì sao không được để ứng dụng dùng mặc định khi secret production không giải mã được.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Fail Fast, Retry, Timeouts and Security](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config Server — Git Backend and Clone Behavior](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Encryption, Decryption and Decryption Errors](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
- [Spring Cloud Config — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html)
