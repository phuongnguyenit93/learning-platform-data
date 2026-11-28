# Cấu hình ghi đè phía máy chủ bằng `server.overrides`

Spring Cloud Config Server có thể bổ sung một nhóm thuộc tính do đội nền tảng quản lý vào cấu hình mà server phân phối cho các ứng dụng. Tính năng này được cấu hình bằng `spring.cloud.config.server.overrides`. Các thuộc tính override được đưa vào Environment trả về cho Config Client với độ ưu tiên cao, giúp áp dụng một số quy tắc chung mà cấu hình riêng của từng ứng dụng không nên tự ý thay đổi.

`server.overrides` hữu ích cho những giá trị thực sự cần thống nhất trên toàn bộ client do một Config Server phục vụ, chẳng hạn metadata của nền tảng hoặc một số chính sách cấu hình chung. Vì phạm vi tác động rộng, cần chọn key cẩn thận, quản lý thay đổi có review và kiểm tra kết quả thực tế. Đây là cơ chế ưu tiên cấu hình; nó không thay thế xác thực, phân quyền truy cập hay hệ thống quản lý bí mật.

## 1. `server.overrides` giải quyết vấn đề gì?

Thông thường, Config Server kết hợp cấu hình dùng chung và cấu hình riêng từ backend, ví dụ Git:

- `application.yml` chứa giá trị dùng chung.
- `{application}.yml` chứa cấu hình của một ứng dụng.
- Các file theo profile cung cấp phần khác biệt cho `staging` hoặc `production`.

Trong một số trường hợp, tổ chức cần một giá trị do nhóm vận hành kiểm soát tập trung và muốn nó có ưu tiên cao hơn các giá trị cùng tên trong cấu hình ứng dụng. Ví dụ, một số metadata về nền tảng, mã định danh môi trường hoặc cờ chính sách bắt buộc có thể cần được cung cấp đồng nhất cho mọi client.

Nếu đặt giá trị đó trong `application.yml` của Git, một file ứng dụng hoặc profile cụ thể có thể khai báo lại cùng key. Khi đó, kết quả phụ thuộc vào thứ tự property source thông thường. `server.overrides` tạo một property source riêng có ưu tiên cao trong Environment mà Config Server trả về, dành cho những giá trị cần được quản trị từ phía server.

## 2. Khai báo `spring.cloud.config.server.overrides`

Thuộc tính được cấu hình trên chính ứng dụng Config Server, thường trong `application.yml` của server hoặc qua biến môi trường và nguồn cấu hình triển khai.

Ví dụ:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        overrides:
          platform.config.owner: platform-team
          platform.config.managed: "true"
          platform.region: ap-southeast-1
```

Trong ví dụ này, Config Server bổ sung ba thuộc tính vào cấu hình phân phối cho các client mà server phục vụ. Các key được đặt dưới namespace `platform` để thể hiện đây là dữ liệu do nền tảng quản lý, giảm nguy cơ vô tình trùng với thuộc tính nghiệp vụ của từng ứng dụng.

Có thể cấu hình qua biến môi trường khi triển khai Config Server:

```bash
SPRING_CLOUD_CONFIG_SERVER_OVERRIDES_PLATFORM_CONFIG_OWNER=platform-team
SPRING_CLOUD_CONFIG_SERVER_OVERRIDES_PLATFORM_CONFIG_MANAGED=true
SPRING_CLOUD_CONFIG_SERVER_OVERRIDES_PLATFORM_REGION=ap-southeast-1
```

Tên biến môi trường được tạo theo quy tắc relaxed binding của Spring Boot. Khi dùng key có dấu chấm hoặc dấu gạch ngang, cần xác minh cách chuyển đổi tên biến trong môi trường thực tế. Đối với các giá trị phức tạp hoặc cần giữ nguyên định dạng, cấu hình trong YAML thường dễ đọc và ít nhầm lẫn hơn.

`overrides` là một map các key/value. Hãy giữ các giá trị đơn giản, rõ kiểu và tránh đưa cả cấu trúc cấu hình lớn vào map này. Nếu một thuộc tính có nhiều phần con, cân nhắc đặt từng key cần quản trị rõ ràng hoặc dùng nguồn cấu hình phù hợp hơn.

## 3. Phạm vi áp dụng và độ ưu tiên

Các thuộc tính trong `spring.cloud.config.server.overrides` được Config Server thêm vào Environment trả về cho client dưới dạng property source ưu tiên cao. Mục đích của tính năng là cho phép nhà vận hành cung cấp các giá trị có quyền ưu tiên trên cấu hình ứng dụng thông thường. Vì vậy, không nên coi đây là nơi đặt các giá trị mặc định mềm mà nhóm ứng dụng cần tự do thay đổi.

Ví dụ repository Git có:

```yaml
# application.yml trong config repository
platform:
  region: default-region

logging:
  level:
    root: INFO
```

Và file riêng của ứng dụng:

```yaml
# order-service-production.yml
platform:
  region: app-selected-region

logging:
  level:
    root: WARN
```

Trong khi đó, Config Server khai báo:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.region: ap-southeast-1
```

Khi client lấy cấu hình từ server, `platform.region` trong property source override có độ ưu tiên cao hơn giá trị cùng tên được lấy từ cấu hình ứng dụng trong Git. Thuộc tính `logging.level.root` không nằm trong map override nên vẫn được quyết định bởi các property source còn lại theo quy tắc ưu tiên thông thường.

Thứ tự ưu tiên tổng thể còn có thể liên quan đến các nguồn cấu hình phía client như biến môi trường, tham số dòng lệnh, file local và các tùy chọn cho phép ghi đè remote property source. Vì vậy, khi cần xác nhận một key thực sự có giá trị nào ở runtime, hãy kiểm tra Environment cuối cùng của ứng dụng và cấu hình `allowOverride`, `overrideNone`, `overrideSystemProperties` nếu hệ thống có sử dụng. Đừng suy ra thứ tự cuối cùng chỉ từ một file YAML hoặc một response riêng lẻ.

## 4. Phân biệt server overrides với các cơ chế override phía client

Spring Cloud Config có nhiều thuộc tính mang chữ `override`, nhưng chúng nằm ở những vị trí và phục vụ các mục đích khác nhau:

| Thuộc tính | Nơi cấu hình | Ý nghĩa |
|---|---|---|
| `spring.cloud.config.server.overrides` | Ứng dụng Config Server | Bổ sung property source do server quản lý, có độ ưu tiên cao trong Environment trả về |
| `spring.cloud.config.allowOverride` | Cấu hình remote được phân phối cho client | Cho phép client áp dụng quy tắc ghi đè remote property source theo cơ chế Spring Cloud Config |
| `spring.cloud.config.overrideNone` | Cấu hình remote được phân phối cho client | Điều chỉnh vị trí remote property source để các nguồn local có thể được ưu tiên theo cơ chế tương ứng |
| `spring.cloud.config.overrideSystemProperties` | Cấu hình remote được phân phối cho client | Điều chỉnh khả năng các system properties, biến môi trường hoặc tham số khởi chạy ghi đè remote source |

Ba thuộc tính phía client kiểm soát quan hệ ưu tiên giữa remote property source và các nguồn thuộc tính ở phía ứng dụng. `server.overrides` là một property source do Config Server tạo ra. Không nên đặt các thuộc tính này cùng một chỗ hoặc giả định chúng là các tên gọi khác nhau của một cơ chế.

Khi dùng đồng thời, hãy tạo một ví dụ kiểm thử có cùng key xuất hiện ở server override, Git `application.yml`, file theo ứng dụng/profile, file local, biến môi trường và tham số dòng lệnh. Gọi Config Server để xem response, sau đó kiểm tra Environment thực tế ở client. Đây là cách xác nhận đáng tin cậy cho phiên bản Spring Boot và Spring Cloud đang chạy.

## 5. Chọn key nào để đưa vào server overrides?

Chỉ đưa vào `server.overrides` các thuộc tính đáp ứng đồng thời những điều kiện sau:

- Cần áp dụng nhất quán cho mọi ứng dụng hoặc mọi client trong phạm vi Config Server đó.
- Có một chủ sở hữu trung tâm chịu trách nhiệm về ý nghĩa và thay đổi của key.
- Giá trị không phụ thuộc vào nghiệp vụ riêng của một ứng dụng.
- Tác động của việc thay đổi trên toàn bộ client đã được đánh giá.
- Giá trị không phải bí mật cần được cấp phát theo danh tính hoặc luân chuyển.

Ví dụ phù hợp có thể là metadata nền tảng như tên miền quản trị, mã định danh cụm hoặc một số cờ biểu thị chính sách vận hành được áp dụng chung. Dù vậy, cần đánh giá từng key để tránh làm ứng dụng nhận một giá trị không phù hợp với vai trò của nó.

Không nên đưa vào map này:

- Timeout, retry hoặc connection pool riêng cho một dịch vụ.
- URL, tên queue hoặc giới hạn nghiệp vụ khác nhau giữa các ứng dụng.
- Giá trị cần thay đổi độc lập theo profile nhưng không có chủ sở hữu trung tâm.
- Mật khẩu, API token, private key hoặc credential dạng rõ.
- Những key không được tất cả ứng dụng hiểu hoặc có kiểu dữ liệu giống nhau.

Một override chung sai có thể ảnh hưởng đến hàng chục dịch vụ cùng lúc. Vì vậy, càng ít key và càng rõ mục đích thì càng dễ quản trị.

## 6. `server.overrides` không phải cơ chế bảo mật

Độ ưu tiên cấu hình không đồng nghĩa với quyền kiểm soát truy cập. Nếu Config Server trả một thuộc tính cho client, client có thể nhận được giá trị đó; `server.overrides` không tự xác thực danh tính ứng dụng và không quyết định ai được gọi endpoint.

Không dùng map override để phân phối bí mật. Các giá trị như database password, API token, private key và khóa ký cần được quản lý trong Vault hoặc secret manager, có policy theo danh tính workload, audit và quy trình rotation/thu hồi. Việc đưa một bí mật vào property source ưu tiên cao vẫn làm bí mật được phân phối tới mọi client có quyền nhận Environment đó.

Để bảo vệ Config Server, cần:

- Bật TLS cho kết nối client-server và server-backend.
- Yêu cầu xác thực client và phân quyền theo ứng dụng hoặc nhóm ứng dụng.
- Giới hạn quyền truy cập repository cấu hình và credential Git.
- Bảo vệ endpoint quản trị và Actuator; không công khai thông tin Environment nhạy cảm.
- Theo dõi các yêu cầu lấy cấu hình và thay đổi cấu hình override.
- Tách Config Server theo ranh giới bảo mật nếu các nhóm client không được phép nhận cùng một tập thuộc tính.

Nếu hai nhóm ứng dụng cần các override khác nhau, một map global trên cùng server có thể quá rộng. Có thể tách Config Server hoặc thiết kế cách phân phối theo backend/namespace và authorization phù hợp. Không nên dựa vào việc đặt tên key khác nhau để thay thế kiểm soát truy cập.

## 7. Quản trị thay đổi override

Vì một thay đổi trong `server.overrides` có thể tác động tới nhiều ứng dụng, hãy quản lý file cấu hình của Config Server như một phần hạ tầng quan trọng.

Quy trình gợi ý:

1. Mở pull request thay đổi map override và mô tả lý do, phạm vi client chịu tác động.
2. Chỉ định Platform owner review; mời các nhóm ứng dụng bị ảnh hưởng khi thay đổi key hoặc giá trị.
3. Kiểm tra key trùng, kiểu dữ liệu, quy ước namespace và giá trị hợp lệ.
4. Chạy integration test để xác nhận Config Server trả override đúng và các client nhận giá trị dự kiến.
5. Triển khai Config Server theo rollout có kiểm soát; theo dõi lỗi lấy cấu hình và hành vi ứng dụng.
6. Lưu commit/tag của cấu hình server và phương án quay lại phiên bản trước.

Nên kiểm thử cả trường hợp key override chưa tồn tại trong Git và trường hợp cùng key được khai báo ở nhiều file/profile. Kiểm tra thêm một ứng dụng đại diện cho từng loại client để phát hiện khác biệt do cấu hình local hoặc property source riêng.

## 8. Kiểm tra kết quả từ Config Server và Config Client

Có thể gọi endpoint Environment của Config Server để xem property sources mà server trả về. Ví dụ:

```bash
curl -u config-user:CONFIG_PASSWORD \
  https://config.example.internal/order-service/production/config-release-2026.11.0
```

Đây là ví dụ minh họa; không đưa mật khẩu thật vào lịch sử shell hoặc tài liệu. Trong môi trường thực tế, dùng cơ chế xác thực an toàn và TLS với chứng thư được xác minh.

Khi xem response, kiểm tra:

- Có property source override do server tạo hay không.
- Key override có đúng giá trị và xuất hiện ở vị trí ưu tiên mong đợi hay không.
- Các property source từ Git có chứa key trùng hay không.
- Application, profile và label trong request có đúng với môi trường đang kiểm tra hay không.

Ở phía client, có thể dùng Actuator `env` hoặc `configprops` trong môi trường phát triển để quan sát giá trị cuối cùng và nguồn cung cấp. Các endpoint này có thể tiết lộ cấu hình nội bộ; cần giới hạn quyền truy cập, che dữ liệu nhạy cảm và không mở công khai trong production.

Ví dụ kiểm thử tư duy với cùng một key:

| Nguồn | Giá trị `platform.region` |
|---|---|
| Git `application.yml` | `default-region` |
| Git `order-service-production.yml` | `app-selected-region` |
| Config Server `server.overrides` | `ap-southeast-1` |

Response của Config Server phải thể hiện property source override với giá trị `ap-southeast-1` và độ ưu tiên cao hơn các nguồn cấu hình ứng dụng trên. Sau đó vẫn cần xác minh giá trị cuối ở client nếu có nguồn local hoặc cờ điều khiển override remote.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Client không nhận key override | Khai báo sai prefix hoặc đặt map ở repository Git thay vì cấu hình Config Server | Kiểm tra `spring.cloud.config.server.overrides` trong Environment của server |
| Giá trị override áp dụng cho quá nhiều ứng dụng | Dùng map global cho thuộc tính chỉ phù hợp một số dịch vụ | Thu hẹp phạm vi, tách server hoặc dùng cấu hình theo application/profile |
| Giá trị phía client khác response Config Server | Có nguồn local, biến môi trường, tham số dòng lệnh hoặc quy tắc override remote tác động | Kiểm tra Environment cuối cùng và các thuộc tính điều khiển precedence |
| Ứng dụng không thể thay đổi một key | Key đang nằm trong property source override có ưu tiên cao | Xác nhận key có thật sự cần bị khóa ở cấp nền tảng; nếu không, chuyển về cấu hình ứng dụng thông thường |
| Thay đổi override gây lỗi diện rộng | Không kiểm thử đủ các client hoặc không đánh giá phạm vi ảnh hưởng | Thêm integration test theo nhóm ứng dụng và rollout có kiểm soát |
| Giá trị bí mật xuất hiện trong nhiều ứng dụng | Dùng override để phân phối credential | Thu hồi/rotate nếu đã lộ và chuyển sang secret manager với policy theo workload |

## 10. Ví dụ hoàn chỉnh

Giả sử Platform cần cung cấp một mã vùng triển khai và một cờ nhận diện cấu hình do nền tảng quản lý cho các ứng dụng. Config Server có thể khai báo:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          default-label: main
        overrides:
          platform.region: ap-southeast-1
          platform.config.source: central-config
          platform.config.managed: "true"
```

Repository Git tiếp tục lưu cấu hình theo ứng dụng:

```yaml
# order-service.yml
checkout:
  timeout: 2s
  max-retries: 2
```

```yaml
# inventory-service.yml
inventory:
  reservation-timeout: 5s
```

Khi `order-service` hoặc `inventory-service` lấy cấu hình, Config Server phân phối property source từ Git cùng các giá trị override của nền tảng. Các key nghiệp vụ riêng vẫn nằm trong file của từng ứng dụng. Nếu một ứng dụng khai báo lại `platform.region`, property source override có ưu tiên cao trong Environment được trả về và được thiết kế để giữ quyền kiểm soát giá trị đó ở phía server.

Khi Platform cần đổi vùng triển khai, nhóm có thể thay đổi override, review, kiểm thử các client đại diện rồi phát hành Config Server. Thay đổi này cần được quản trị như một thay đổi có phạm vi rộng; không nên sửa nhanh mà không đánh giá ứng dụng bị ảnh hưởng.

## 11. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích được vai trò của `spring.cloud.config.server.overrides` và vị trí khai báo trên Config Server.
- Viết được map override đơn giản trong cấu hình YAML hoặc nguồn cấu hình triển khai.
- Mô tả được vì sao property source override có độ ưu tiên cao và tác động tới cấu hình ứng dụng.
- Phân biệt `server.overrides` với `allowOverride`, `overrideNone` và `overrideSystemProperties` phía client.
- Chọn được key phù hợp để quản trị toàn cục và tránh đưa cấu hình nghiệp vụ riêng hoặc bí mật vào map.
- Kiểm tra được property source từ Config Server và giá trị cuối cùng trong Config Client.
- Thiết kế quy trình review, kiểm thử, rollout và rollback cho thay đổi override.

**Tự kiểm tra:** Git repository khai báo `platform.region=default-region`, file `order-service-production.yml` khai báo `platform.region=app-region`, còn Config Server đặt `platform.region=ap-southeast-1` trong `server.overrides`. Hãy giải thích giá trị mà property source override cung cấp, vì sao cần kiểm tra thêm Environment cuối ở client và tại sao không nên dùng cùng cơ chế này để phát tán database password.
