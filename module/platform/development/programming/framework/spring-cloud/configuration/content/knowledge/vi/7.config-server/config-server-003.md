# Kết nối kho Git bằng `spring.cloud.config.server.git.uri`

Spring Cloud Config Server có thể lấy cấu hình từ nhiều backend. Git là lựa chọn phổ biến vì mỗi thay đổi cấu hình được lưu thành commit, có thể review, so sánh, gắn tag và quay lại phiên bản trước. Để dùng Git backend, Config Server cần biết địa chỉ repository, nhánh hoặc label mặc định, cách xác thực và vị trí lưu bản clone cục bộ.

Thuộc tính trung tâm là `spring.cloud.config.server.git.uri`. Giá trị của nó trỏ đến repository mà Config Server sẽ clone và đọc. Sau khi kết nối, server cung cấp property source theo tên ứng dụng, profile và label thông qua API HTTP.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Khai báo `spring.cloud.config.server.git.uri` trong cấu hình Config Server.
- Chuẩn bị repository Git và tổ chức file cấu hình theo ứng dụng/profile.
- Chọn branch mặc định bằng `default-label` và hiểu quan hệ giữa label với API.
- Cấu hình `search-paths` và thư mục clone cục bộ.
- Kết nối repository công khai hoặc riêng tư qua HTTPS/SSH bằng thông tin xác thực an toàn.
- Kiểm tra Config Server đã clone và đọc đúng cấu hình từ Git.
- Nhận biết các lỗi thường gặp khi kết nối repository.

## Điều kiện cần có

Trước khi cấu hình Git backend, cần chuẩn bị:

- Một ứng dụng Spring Boot có dependency `spring-cloud-config-server`.
- Lớp khởi động có annotation `@EnableConfigServer`.
- Một repository Git chứa các file YAML hoặc properties.
- Địa chỉ repository mà máy hoặc container chạy Config Server có thể truy cập.
- Credential phù hợp nếu repository là private.

Ví dụ lớp khởi động:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Dependency và annotation có vai trò riêng: dependency cung cấp implementation của Config Server, còn `@EnableConfigServer` bật chức năng server trong ứng dụng.

## Khai báo `spring.cloud.config.server.git.uri`

Trong `application.yml` của Config Server, đặt URI của repository dưới nhánh `spring.cloud.config.server.git`:

```yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: https://github.com/acme/platform-config.git
          default-label: main
          clone-on-start: true
```

Trong ví dụ này:

- `uri` là địa chỉ Git repository. Có thể dùng HTTPS hoặc SSH tùy chính sách truy cập.
- `default-label` chỉ định branch, tag hoặc label mặc định khi client không truyền label. Ví dụ dùng branch `main`; hãy đặt đúng tên nhánh thực tế của repository.
- `clone-on-start: true` yêu cầu server clone repository khi khởi động. Nhờ đó lỗi sai URI hoặc quyền truy cập có thể được phát hiện sớm trong quá trình triển khai.

Nếu bỏ `clone-on-start` hoặc đặt `false`, việc clone có thể diễn ra khi có yêu cầu cấu hình đầu tiên. Cách này có thể giúp server khởi động khi backend Git chưa sẵn sàng, nhưng lỗi kết nối sẽ xuất hiện muộn hơn khi client truy vấn. Trong môi trường cần phát hiện lỗi cấu hình triển khai sớm, bật clone-on-start thường dễ vận hành hơn.

`uri` phải là địa chỉ repository mà tiến trình Config Server có thể truy cập. Địa chỉ trên máy phát triển không tự động có nghĩa container hoặc máy chủ production cũng truy cập được. Hãy kiểm tra DNS, route mạng, proxy, firewall và chứng thư TLS từ đúng môi trường chạy server.

## Chuẩn bị repository cấu hình

Config Server đọc các file cấu hình có tên theo application và profile. Một repository đơn giản có thể có cấu trúc:

```text
platform-config/
├── application.yml
├── application-prod.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── inventory-service.yml
└── inventory-service-prod.yml
```

Ý nghĩa các file:

- `application.yml`: thuộc tính chung có thể áp dụng cho nhiều ứng dụng.
- `application-prod.yml`: thuộc tính chung dành cho profile `prod`.
- `order-service.yml`: thuộc tính mặc định riêng của ứng dụng `order-service`.
- `order-service-dev.yml`: thuộc tính của `order-service` khi dùng profile `dev`.
- `order-service-prod.yml`: thuộc tính của `order-service` khi dùng profile `prod`.
- `inventory-service*.yml`: cấu hình tương ứng cho ứng dụng kho.

Ví dụ `order-service-prod.yml`:

```yaml
server:
  port: 8081

spring:
  datasource:
    url: jdbc:postgresql://db-prod.internal:5432/orders

orders:
  reservation-timeout: 15s
  max-items-per-order: 50
```

Chỉ đưa các giá trị cấu hình phù hợp vào Git. Mật khẩu, token và private key cần lấy từ secret manager hoặc nguồn cấp runtime được bảo vệ. File cấu hình có thể chứa placeholder hoặc tên tham chiếu đến secret, tùy cách tích hợp của hệ thống.

## Branch, tag và label

Config Server dùng label để chọn phiên bản trong repository Git. Label thường là tên branch, tag hoặc commit. Nếu client không gửi label, server dùng giá trị `default-label` đã cấu hình; vì vậy, hãy khai báo rõ nhánh mặc định thay vì phụ thuộc vào giả định về tên branch.

Ví dụ repository có các nhánh:

```text
main
release/2026.11
feature/new-pricing
```

Client có thể yêu cầu cấu hình theo label `main` hoặc `release/2026.11`, tùy phiên bản và cách mã hóa label trong URL. Với API thông thường, đường dẫn có dạng:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```text
GET http://localhost:8888/order-service/prod/main
```

Yêu cầu trên có nghĩa là lấy cấu hình cho ứng dụng `order-service`, profile `prod`, từ label `main`. Nếu cần một cấu hình có thể tái lập, có thể dùng tag phát hành hoặc commit cụ thể thay vì branch tiếp tục thay đổi. Khi dùng label có dấu `/`, cần tuân theo quy tắc mã hóa label của Spring Cloud Config và proxy đứng trước server; một số cấu hình URL dùng cách biểu diễn đặc biệt cho dấu gạch chéo.

## Tổ chức thư mục bằng `search-paths`

Mặc định Config Server tìm file ở thư mục gốc repository. Khi repository lớn, có thể tổ chức cấu hình theo thư mục và khai báo `search-paths`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/acme/platform-config.git
          default-label: main
          search-paths:
            - shared
            - '{application}'
```

Repository khi đó có thể được tổ chức như sau:

```text
platform-config/
├── shared/
│   ├── application.yml
│   └── application-prod.yml
├── order-service/
│   ├── order-service.yml
│   └── order-service-prod.yml
└── inventory-service/
    ├── inventory-service.yml
    └── inventory-service-prod.yml
```

`shared` chứa cấu hình dùng chung; `{application}` được thay bằng tên ứng dụng trong yêu cầu. Các đường dẫn trong `search-paths` là đường dẫn tương đối trong repository đã clone. Có thể dùng placeholder như `{profile}` hoặc `{label}` trong các mẫu thư mục khi cấu trúc repository cần phân tách sâu hơn. Hãy kiểm tra kết quả API sau khi thay đổi search path để bảo đảm server thực sự đọc được file mong muốn.

Nếu không cần chia thư mục, giữ file ở root giúp cấu hình đơn giản hơn. Không thêm `search-paths` tùy tiện vì cấu trúc thư mục và tên file cùng quyết định những property source được trả về.

## Lưu bản clone cục bộ

Config Server clone repository từ xa vào một thư mục trên máy hoặc container. Có thể chỉ định thư mục clone bằng `basedir`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/acme/platform-config.git
          basedir: /var/lib/config-server/git/platform-config
          clone-on-start: true
```

Thư mục này cần có quyền ghi cho user chạy Config Server và đủ dung lượng. Trong container, hãy chọn volume hoặc đường dẫn có vòng đời phù hợp với cách triển khai. Không dùng một thư mục bị nhiều tiến trình Config Server không phối hợp cùng sửa trực tiếp. Khi cần nhiều instance, mỗi instance nên có vùng clone riêng hoặc dùng cơ chế triển khai được hỗ trợ.

Bản clone là cache làm việc của server, không phải nguồn dữ liệu chính. Repository Git từ xa vẫn là nơi quản lý lịch sử và phát hành cấu hình. Không sửa file trực tiếp trong thư mục clone để thay đổi cấu hình; thay đổi cần được commit và review trong repository nguồn.

## Kết nối repository công khai qua HTTPS

Với repository công khai, URI HTTPS thường không cần credential:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/acme/platform-config.git
          default-label: main
          clone-on-start: true
```

Nếu clone bằng HTTPS thất bại, kiểm tra URL có đúng là URL clone của repository hay không. URL trang web của repository và URL Git clone thường giống phần gốc nhưng có thể khác hậu tố hoặc yêu cầu quyền truy cập. Hãy kiểm tra bằng `git ls-remote` từ đúng máy/container chạy server nếu môi trường cho phép.

## Kết nối repository riêng tư qua HTTPS

Với repository private, Config Server cần username và password/token được nhà cung cấp Git chấp nhận. Ví dụ dùng placeholder môi trường:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/acme/platform-config.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          default-label: main
          clone-on-start: true
```

Trong nhiều nền tảng Git, trường password có thể nhận personal access token hoặc credential tương đương thay cho mật khẩu tài khoản. Token nên có quyền đọc repository cần thiết và thời hạn phù hợp. Hãy tạo token riêng cho Config Server, giới hạn phạm vi repository và cấp token từ secret manager hoặc cơ chế quản lý secret của nền tảng.

Không ghi trực tiếp token vào `application.yml`, Dockerfile, image, command line hoặc log. Placeholder chỉ an toàn khi môi trường chạy thực sự cấp giá trị từ nguồn được bảo vệ. Cũng cần giới hạn quyền truy cập vào cấu hình môi trường và endpoint Actuator để tránh lộ thông tin xác thực qua diagnostic endpoint.

## Kết nối repository riêng tư qua SSH

Nếu tổ chức sử dụng SSH deploy key, URI có thể dùng dạng SSH:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: git@github.com:acme/platform-config.git
          default-label: main
          clone-on-start: true
          ignore-local-ssh-settings: true
          private-key: ${CONFIG_GIT_PRIVATE_KEY}
          strict-host-key-checking: true
          known-hosts-file: /etc/config-server/ssh/known_hosts
```

`private-key` là khóa riêng dùng để xác thực với Git server. Khóa phải được cấp cho tiến trình Config Server từ secret manager hoặc nguồn bảo vệ tương đương. `known-hosts-file` cung cấp host key đã xác minh của Git server; `strict-host-key-checking: true` yêu cầu xác minh máy chủ SSH thay vì chấp nhận host không xác định. `ignore-local-ssh-settings` giúp dùng các thiết lập SSH được khai báo cho ứng dụng thay cho cấu hình SSH cục bộ của tài khoản chạy server.

Deploy key nên chỉ có quyền đọc repository cấu hình. Không tái sử dụng private key cá nhân của lập trình viên trên production. Không tắt host key checking chỉ để vượt qua lỗi kết nối; hãy cập nhật `known_hosts` từ nguồn đáng tin cậy và xác minh fingerprint của máy chủ.

Chi tiết thuộc tính SSH có thể khác theo phiên bản Spring Cloud Config và JGit đi kèm. Nếu đang dùng phiên bản cũ, kiểm tra tài liệu đúng release train trước khi áp dụng các thuộc tính nâng cao.

## Nhiều repository Git

Một Config Server có thể phục vụ nhiều nhóm ứng dụng từ các repository khác nhau. Khi đó, thay vì chỉ dùng một `git.uri`, có thể khai báo các repository con dưới `spring.cloud.config.server.git.repos` và dùng `pattern` để chọn repository theo tên ứng dụng/profile.

Ví dụ minh họa:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          repos:
            commerce:
              pattern:
                - order-service
                - cart-service
              uri: https://github.com/acme/commerce-config.git
              default-label: main
            warehouse:
              pattern:
                - inventory-service
                - shipping-service
              uri: https://github.com/acme/warehouse-config.git
              default-label: main
```

Khi yêu cầu đến cho `order-service`, server chọn repository `commerce`; `inventory-service` được phục vụ từ repository `warehouse`. Cấu hình nhiều repository hữu ích khi nhóm cần phân quyền hoặc vòng đời phát hành tách biệt. Nếu tất cả ứng dụng có cùng quyền truy cập và quy trình phát hành, một repository duy nhất có thể dễ quản lý hơn.

Khi dùng nhiều repository, cần kiểm tra pattern không bị chồng lấn ngoài ý muốn, credential của từng repository được cấp đúng, và mỗi repository có branch/label mặc định phù hợp. Cũng cần xác minh bằng API cho từng application để phát hiện server chọn nhầm nguồn.

## Kiểm tra kết nối Git backend

Sau khi cấu hình, khởi động Config Server và kiểm tra log. Với `clone-on-start: true`, log khởi động thường thể hiện quá trình clone/fetch repository. Không đưa token hoặc private key vào câu lệnh kiểm tra hay chia sẻ log chứa credential.

Có thể kiểm tra trực tiếp repository từ máy chạy server:

```bash
git ls-remote https://github.com/acme/platform-config.git
```

Lệnh này xác nhận URL và quyền truy cập Git ở mức transport; nó không xác nhận Config Server đã bind đúng thuộc tính hoặc đang dùng đúng label. Tiếp theo, gọi API Config Server:

```bash
curl -i http://localhost:8888/order-service/prod/main
```

Phản hồi thành công thường chứa tên ứng dụng, profile, label, phiên bản commit và danh sách `propertySources`. Kiểm tra `propertySources` có file và giá trị mong đợi. Nếu server trả về cấu hình rỗng hoặc không tìm thấy, kiểm tra tên ứng dụng, profile, label, file name và `search-paths`.

Trên PowerShell có thể dùng:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8888/order-service/prod/main'
```

Hãy kiểm tra endpoint từ cùng mạng mà Config Client sử dụng. Nếu Config Server đặt sau reverse proxy hoặc có context path, URL thực tế cần tính đến các thiết lập đó.

## Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| `clone-on-start` làm Config Server không khởi động | URI sai, DNS hoặc mạng không truy cập được, credential không hợp lệ | Kiểm tra URL, DNS, firewall và quyền đọc repository từ môi trường chạy server |
| HTTP 401/403 khi clone HTTPS | Token hết hạn, thiếu quyền hoặc sai username/token | Tạo credential đọc repository, cập nhật secret và kiểm tra quyền |
| SSH báo host key verification failed | Host key chưa có hoặc fingerprint thay đổi | Xác minh fingerprint từ nguồn đáng tin cậy rồi cập nhật `known_hosts` |
| SSH báo public key denied | Deploy key chưa được gắn vào repository hoặc sai private key | Kiểm tra cặp khóa và quyền read-only của deploy key |
| API trả về cấu hình không đúng | Sai application/profile/label hoặc file nằm ngoài search path | Kiểm tra endpoint, tên file, nhánh và `search-paths` |
| Cấu hình cũ vẫn xuất hiện | Server đang dùng label/commit khác, bản clone chưa cập nhật hoặc cache theo cấu hình | Kiểm tra label, commit trả về, log fetch và chính sách refresh của backend |
| Chạy được trên máy cá nhân nhưng lỗi trong container | Container thiếu route, CA certificate, credential hoặc quyền ghi thư mục clone | Kiểm tra từ container và cấu hình volume/secret/network tương ứng |

Không xử lý lỗi TLS bằng cách tắt xác minh chứng thư trong production. Hãy cài CA certificate đúng vào trust store của runtime và xác nhận chuỗi chứng thư của Git host.

## Quy trình thay đổi cấu hình qua Git

Khi đã kết nối, nên quản lý thay đổi theo quy trình có thể truy nguyên:

1. Tạo branch cho thay đổi cấu hình và chỉnh file đúng ứng dụng/profile.
2. Chạy kiểm tra cú pháp, schema và secret scanning.
3. Review diff, xác nhận không có credential hoặc dữ liệu nhị phân/dữ liệu lớn bị thêm nhầm.
4. Merge vào branch hoặc tạo tag phát hành theo chính sách môi trường.
5. Xác minh Config Server trả về đúng label/commit và các property source mong đợi.
6. Cho client refresh hoặc khởi động lại theo quy trình triển khai, sau đó quan sát trạng thái instance.

Git cung cấp lịch sử thay đổi và điểm quay lại. Config Server cung cấp cấu hình theo yêu cầu. Việc một commit đã được merge không tự đảm bảo tất cả client đang chạy đã nhận và áp dụng phiên bản mới; cần có bước phân phối/refresh và xác nhận sau thay đổi.

## Kết luận

`spring.cloud.config.server.git.uri` là thuộc tính xác định repository Git mà Config Server dùng làm nguồn cấu hình. Để kết nối ổn định, cần khai báo đúng URI, label mặc định, search path và thư mục clone; repository riêng tư cần credential HTTPS hoặc SSH được cấp từ nguồn an toàn và có quyền tối thiểu.

Khi repository được tổ chức rõ theo application/profile, mỗi thay đổi có thể review và gắn với commit/label cụ thể. Kiểm tra từ đúng môi trường chạy server, gọi API theo application/profile/label và xác nhận commit cùng property source giúp bảo đảm Config Server đang phân phối đúng cấu hình mà nhóm đã phát hành.
