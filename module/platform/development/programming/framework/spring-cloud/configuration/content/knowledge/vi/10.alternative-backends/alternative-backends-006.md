# Redis backend và cách tổ chức dữ liệu cấu hình

Spring Cloud Config Server có thể lấy thuộc tính cấu hình từ Redis thay vì đọc file trong Git. Redis backend lưu mỗi nhóm thuộc tính trong một Redis hash: tên hash gắn với tên ứng dụng hoặc tên ứng dụng kèm profile, còn field trong hash là tên property và value là giá trị của property đó.

Cách tổ chức này phù hợp khi hệ thống đã dùng Redis làm hạ tầng dữ liệu và muốn cập nhật cấu hình trực tiếp qua các thao tác Redis. Tuy nhiên, Redis hash không tự mang lại lịch sử commit, pull request hay branch như Git. Vì vậy, cần thiết kế rõ phạm vi cấu hình dùng chung, cấu hình theo ứng dụng, profile, quyền ghi và quy trình lưu vết thay đổi.

Sau bài học, bạn có thể:

- Kích hoạt Redis backend trong Spring Cloud Config Server.
- Tổ chức Redis hash cho cấu hình dùng chung, cấu hình ứng dụng và profile.
- Ghi, đọc và cập nhật property bằng các lệnh Redis hash.
- Giải thích cách cấu hình dùng chung và cấu hình riêng được hợp nhất.
- Nhận biết giới hạn về label, versioning, audit và vận hành của Redis backend.

## 1. Redis nằm ở đâu trong kiến trúc Config?

Config Server sử dụng một `EnvironmentRepository` để lấy các `Environment` chứa property sources cho Config Client. Git là backend mặc định, nhưng Spring Cloud Config cũng hỗ trợ các backend khác. Với Redis backend, Config Server đọc thuộc tính từ Redis thông qua Spring Data Redis và trả kết quả theo API Config Server quen thuộc.

~~~mermaid
flowchart LR
    O["Người vận hành / pipeline"] -->|"HSET / cập nhật dữ liệu"| R[("Redis hashes")]
    R -->|"Spring Data Redis"| S["Spring Cloud Config Server"]
    C["Spring Boot Config Client"] -->|"application / profile / label"| S
    S -->|"Environment và PropertySources"| C
    C --> A["Environment / @ConfigurationProperties"]
~~~

Redis là nơi lưu các cặp tên property và value. Config Server chịu trách nhiệm tìm các hash liên quan đến application và profile, hợp nhất chúng thành property sources rồi trả cho client. Client vẫn sử dụng `Environment`, `@Value` hoặc `@ConfigurationProperties`; ứng dụng không cần truy cập Redis trực tiếp.

Điều này giúp tách quyền truy cập: chỉ Config Server cần kết nối Redis backend. Các Config Client chỉ cần quyền gọi Config Server.

## 2. Bật Redis backend cho Config Server

Redis backend được kích hoạt bằng cách thêm Spring Data Redis vào classpath và bật profile `redis` của Config Server.

Với Maven, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Ví dụ cấu hình Config Server dùng Spring Boot 3.x:

~~~yaml
spring:
  application:
    name: config-server
  profiles:
    active: redis
  data:
    redis:
      host: redis.internal
      port: 6379
      database: 0
      username: config-server
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
~~~

Profile `redis` chọn RedisEnvironmentRepository. Các thuộc tính `spring.data.redis.*` cấu hình kết nối Redis của Spring Boot 3.x và các phiên bản mới. Với Spring Boot 2.x, prefix kết nối thường là `spring.redis.*`; hãy dùng đúng prefix theo phiên bản Spring Boot mà dependency Spring Cloud của dự án hỗ trợ.

Không commit mật khẩu Redis vào repository. Hãy inject `REDIS_PASSWORD` từ secret manager hoặc secret của nền tảng triển khai. Redis nên được đặt trong mạng riêng, bật xác thực và TLS khi phù hợp, đồng thời giới hạn ACL cho danh tính của Config Server.

Cấu hình trên là cấu hình kết nối của chính Config Server. Không đặt `spring.profiles.active: redis` trong repository cấu hình của các ứng dụng client; đó là profile để chọn backend phía server.

## 3. Redis hash là cấu trúc lưu trữ chính

Redis hash lưu nhiều field-value dưới cùng một key. Với Config Server Redis backend:

- **Tên Redis key (hash name):** xác định phạm vi application hoặc application/profile.
- **Field:** tên property, ví dụ `server.port`, `order.retry.max-attempts`.
- **Value:** giá trị của property, thường được lưu dưới dạng chuỗi.

Ví dụ, hash `sample-app`:

~~~redis
HSET sample-app server.port "8100" sample.topic.name "test" test.property1 "property1"
~~~

Đọc toàn bộ hash:

~~~redis
HGETALL sample-app
~~~

Kết quả có thể được hình dung như sau:

~~~text
1) "server.port"
2) "8100"
3) "sample.topic.name"
4) "test"
5) "test.property1"
6) "property1"
~~~

Một hash tương ứng với một nhóm cấu hình. Các property key được giữ theo tên phân cấp có dấu chấm. Ví dụ `order.retry.max-attempts` là một field duy nhất trong hash, không phải một Redis key lồng nhau.

Redis backend sử dụng các thao tác hash thông qua Spring Data Redis. Khi thao tác thủ công, nên dùng `HSET` để thêm hoặc cập nhật một hay nhiều field. Lệnh `HMSET` xuất hiện trong tài liệu cũ vẫn có thể gặp ở ví dụ lịch sử, nhưng đã được Redis đánh dấu deprecated; hãy ưu tiên `HSET`.

## 4. Quy ước đặt tên hash theo application và profile

Redis backend tổ chức dữ liệu theo application và profile. Có hai nhóm hash chính:

1. **Cấu hình dùng chung:** hash tên `application` chứa thuộc tính áp dụng cho mọi ứng dụng. Có thể thêm hậu tố profile, ví dụ `application-dev` hoặc `application-prod`.
2. **Cấu hình riêng của ứng dụng:** hash tên theo `spring.application.name`, có thể thêm hậu tố profile, ví dụ `order-service`, `order-service-dev`, `order-service-prod`.

Một repository Redis có thể tổ chức như sau:

| Redis hash | Phạm vi |
|---|---|
| `application` | Mặc định dùng chung cho mọi ứng dụng |
| `application-dev` | Thuộc tính dùng chung khi profile `dev` hoạt động |
| `application-prod` | Thuộc tính dùng chung khi profile `prod` hoạt động |
| `order-service` | Cấu hình mặc định riêng của order-service |
| `order-service-dev` | Cấu hình riêng order-service trong profile dev |
| `order-service-prod` | Cấu hình riêng order-service trong profile prod |
| `inventory-service` | Cấu hình mặc định riêng của inventory-service |
| `inventory-service-prod` | Cấu hình riêng inventory-service trong profile prod |

Nếu client không chỉ định profile, profile `default` được sử dụng. Tên hash không có hậu tố profile là nơi lưu các thuộc tính không gắn với một profile cụ thể. Khi cần xác nhận cách phân giải của nhiều profile, hãy kiểm tra Environment trả về bởi đúng phiên bản Config Server đang triển khai.

### Ví dụ dữ liệu

Ghi thuộc tính mặc định dùng chung:

~~~redis
HSET application company.timezone "Asia/Ho_Chi_Minh" feature.audit.enabled "true"
~~~

Ghi thuộc tính dùng chung cho production:

~~~redis
HSET application-prod logging.level.root "INFO" management.endpoint.health.show-details "never"
~~~

Ghi thuộc tính riêng của order-service:

~~~redis
HSET order-service order.api.timeout "2s" order.retry.max-attempts "3"
~~~

Ghi giá trị riêng cho order-service ở production:

~~~redis
HSET order-service-prod order.api.timeout "5s" order.retry.max-attempts "5"
~~~

Đọc từng hash để kiểm tra:

~~~redis
HGETALL application
HGETALL application-prod
HGETALL order-service
HGETALL order-service-prod
~~~

Cách đặt tên này làm rõ giá trị nào được dùng chung và giá trị nào chỉ áp dụng cho một ứng dụng hoặc profile. Hãy thống nhất tên ứng dụng với `spring.application.name` của Config Client; sai khác một ký tự có thể khiến Config Server tìm một hash khác.

## 5. Cấu hình dùng chung và cấu hình riêng được hợp nhất ra sao?

Config Server đọc cả hash dùng chung và hash riêng của ứng dụng. Theo tài liệu Redis backend, giá trị trong hash của ứng dụng được yêu cầu có độ ưu tiên cao hơn giá trị tương ứng trong hash dùng chung.

Ví dụ:

~~~redis
HSET application order.api.timeout "2s" order.retry.max-attempts "3" company.timezone "Asia/Ho_Chi_Minh"
HSET order-service order.api.timeout "4s" order.retry.max-attempts "5"
~~~

Khi `order-service` lấy cấu hình, kết quả mong đợi là:

| Property | Giá trị cuối cùng | Nguồn |
|---|---|---|
| `order.api.timeout` | `4s` | `order-service` |
| `order.retry.max-attempts` | `5` | `order-service` |
| `company.timezone` | `Asia/Ho_Chi_Minh` | `application` |

Hash riêng ghi đè các field trùng tên từ hash dùng chung. Những field chỉ có ở hash dùng chung vẫn được kế thừa.

Profile-specific hash cho phép tinh chỉnh thêm theo môi trường. Ví dụ, `application-prod` có thể đặt mức log và chính sách health check dùng chung, còn `order-service-prod` điều chỉnh timeout riêng cho dịch vụ đặt hàng. Khi có nhiều profile hoạt động, Spring Cloud Config áp dụng mô hình ưu tiên profile của Spring; profile hoạt động được ưu tiên hơn mặc định và profile đứng sau trong danh sách có thể ghi đè profile đứng trước. Hãy kiểm tra danh sách property sources và giá trị cuối cùng qua endpoint Config Server khi dùng nhiều profile.

## 6. Dùng nhiều application name

Config Client có thể yêu cầu nhiều application name bằng danh sách phân tách dấu phẩy. Redis backend đọc các hash ứng với từng tên. Theo tài liệu, tên application xuất hiện sau có độ ưu tiên cao hơn tên trước.

Ví dụ:

~~~yaml
spring:
  application:
    name: shared-platform,order-service
~~~

Config Server sẽ đọc hash `shared-platform` và `order-service` cùng các hash profile tương ứng. Nếu hai hash có cùng field, giá trị từ `order-service` sẽ thắng vì tên này đứng sau trong danh sách.

Cách này có thể dùng để chia sẻ một nhóm cấu hình giữa nhiều ứng dụng. Tuy nhiên, cần cân nhắc ownership: nếu một hash dùng chung có quá nhiều thuộc tính, nhóm vận hành khó xác định ứng dụng nào chịu trách nhiệm cho từng field. Hãy dùng tên application bổ sung khi có ranh giới chia sẻ rõ ràng, và kiểm tra thứ tự ưu tiên bằng một bài test có field trùng nhau.

## 7. Label và versioning khi dùng Redis

API Config Server có tham số application, profile và label. Tuy nhiên, cấu trúc Redis hash được tài liệu backend mô tả dựa trên application và profile; tên hash chuẩn không có thành phần label như Git branch hoặc tag.

Điều này có ý nghĩa khi thiết kế quy trình triển khai:

- Không nên mặc định rằng thay đổi label từ `main` sang `release-2026-11` sẽ tự chọn một tập hash Redis riêng.
- Redis backend không tự cung cấp lịch sử commit, branch, tag hoặc rollback tương đương Git.
- Nếu cần nhiều phiên bản cấu hình song song, cần thiết kế versioning riêng, chẳng hạn namespace/hash theo revision cùng một `EnvironmentRepository` tùy chỉnh, hoặc chọn backend hỗ trợ label theo đúng yêu cầu.
- Nếu vẫn dùng Redis backend mặc định, hãy xác minh hành vi label của phiên bản Spring Cloud Config đang chạy trước khi dùng label như cơ chế phát hành.

Ví dụ, tự tạo hash tên `order-service-release-2026-11` không có nghĩa Redis backend mặc định sẽ tự đọc hash đó. Backend chỉ tìm các tên hash theo quy ước mà nó triển khai. Muốn dùng một namespace tùy chỉnh, cần có lớp tích hợp biết cách ánh xạ application/profile/label sang key Redis tương ứng.

## 8. Cập nhật property an toàn

Redis cho phép cập nhật field trực tiếp. Lệnh `HSET` thay đổi giá trị của field đã có hoặc thêm field mới:

~~~redis
HSET order-service-prod order.api.timeout "6s"
~~~

Xóa một field:

~~~redis
HDEL order-service-prod order.retry.max-attempts
~~~

Xóa toàn bộ hash:

~~~redis
DEL order-service-prod
~~~

`DEL` có ảnh hưởng rộng hơn nhiều so với `HDEL`; trước khi xóa hash, hãy xác nhận đúng môi trường và phạm vi. Không dùng `FLUSHDB` hoặc `FLUSHALL` để sửa một cấu hình đơn lẻ.

Nếu cần cập nhật nhiều field liên quan, có thể gửi một lệnh `HSET` với nhiều cặp field-value. Với quy trình gồm nhiều lệnh, cân nhắc Redis transaction (`MULTI/EXEC`) hoặc cách ghi phiên bản mới rồi chuyển đổi có kiểm soát để tránh client đọc được trạng thái cập nhật dở dang. Kiểm tra cách đọc của Config Server trong lúc cập nhật và xác minh sau khi ghi xong.

Không đặt TTL ngắn cho hash cấu hình production nếu chưa có chủ đích rõ ràng. Key hết hạn sẽ làm cấu hình biến mất và có thể khiến ứng dụng nhận thiếu thuộc tính khi khởi động hoặc refresh.

## 9. Kiểm tra dữ liệu và kết quả từ Config Server

Một số lệnh hữu ích khi kiểm tra Redis:

| Lệnh | Mục đích |
|---|---|
| `TYPE order-service-prod` | Xác nhận key là Redis hash |
| `EXISTS order-service-prod` | Kiểm tra hash có tồn tại |
| `HLEN order-service-prod` | Đếm số field |
| `HGET order-service-prod order.api.timeout` | Đọc một property |
| `HGETALL order-service-prod` | Đọc toàn bộ field-value |
| `HDEL order-service-prod order.api.timeout` | Xóa một property |
| `SCAN 0 MATCH order-service*` | Tìm hash theo mẫu trong lúc kiểm tra |

Không dùng `KEYS *` trên Redis production có lượng key lớn vì thao tác này có thể chặn Redis trong thời gian quét. Ưu tiên `SCAN` với cursor và giới hạn phù hợp. Các lệnh đọc toàn bộ hash cũng có thể trả về dữ liệu nhạy cảm; chỉ chạy bằng danh tính được phép và không dán output vào log công khai.

Sau khi ghi dữ liệu, gọi endpoint Config Server tương ứng với application và profile để xác nhận các property sources. Kiểm tra tên application, danh sách profile và các giá trị trùng khóa để chắc chắn precedence đúng. Sau đó kiểm tra ở Config Client bằng `Environment` hoặc `@ConfigurationProperties`. Việc Redis có dữ liệu không tự chứng minh client đã nhận hoặc áp dụng cấu hình đó.

## 10. Bảo mật và vận hành Redis backend

Redis backend biến Redis thành kho cấu hình có thể ảnh hưởng trực tiếp đến nhiều ứng dụng. Quyền ghi vào hash cấu hình tương đương quyền thay đổi hành vi runtime của những ứng dụng đọc hash đó.

Một số nguyên tắc cần áp dụng:

- Chỉ cho phép Config Server và pipeline cấu hình được truy cập Redis; không mở Redis trực tiếp ra mạng công cộng.
- Dùng Redis ACL với user riêng, giới hạn command và key pattern phù hợp.
- Bật TLS khi kết nối qua mạng không tin cậy; quản lý password bằng secret manager.
- Phân tách dữ liệu dev, staging và production bằng Redis deployment hoặc vùng cô lập phù hợp.
- Hạn chế người có quyền `HSET`, `HDEL` và `DEL`; tách quyền đọc khỏi quyền thay đổi nếu quy trình cho phép.
- Không ghi mật khẩu, token hoặc toàn bộ hash cấu hình vào log.
- Bật persistence và backup phù hợp với yêu cầu khôi phục; kiểm tra khả năng restore định kỳ.
- Ghi lại người thay đổi, ticket/phê duyệt, thời điểm, hash, field và giá trị trước/sau ở hệ thống audit bên ngoài.

Redis không tự cung cấp luồng review thay đổi cấu hình như pull request Git. Nếu nhóm cần audit và rollback, hãy xây dựng pipeline quản lý thay đổi: lưu bản cấu hình đã phê duyệt, kiểm tra trước khi ghi, ghi nhận revision bên ngoài và giữ snapshot để phục hồi. Có thể dùng Git làm nguồn review rồi đồng bộ giá trị đã duyệt sang Redis, nhưng cần có bước xác minh đồng bộ và xử lý lỗi.

Với bí mật ứng dụng, hãy đánh giá việc lưu plaintext trong Redis có phù hợp hay không. Có thể dùng cơ chế mã hóa thuộc tính của Spring Cloud Config hoặc secret manager chuyên dụng. Bảo vệ kết nối Redis không thay thế việc kiểm soát nội dung secret được trả về cho Config Client.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Config Server không chọn Redis backend | Chưa thêm Spring Data Redis hoặc chưa kích hoạt profile `redis` | Kiểm tra dependency, active profile và log khởi động |
| Config Server không kết nối Redis | Host, port, ACL, password, TLS hoặc network sai | Kiểm tra kết nối từ chính Config Server và secret version |
| Client không nhận property | Hash name không khớp application/profile hoặc field sai tên | So sánh `spring.application.name`, profile và tên hash |
| Giá trị dùng chung không được ghi đè | Hash ứng dụng không được đọc hoặc field name khác nhau | Kiểm tra HGETALL hai hash và response property sources |
| Giá trị của profile không như dự kiến | Profile chưa active hoặc hash profile bị đặt sai hậu tố | Xác nhận active profiles và hash `application-{profile}` / `{application}-{profile}` |
| Thay label nhưng dữ liệu không đổi | Đang kỳ vọng Redis hash có version theo Git label | Kiểm tra mô hình key; thiết kế versioning/custom backend nếu cần |
| Cấu hình biến mất | Hash hoặc field bị xóa, key hết TTL hoặc nhầm Redis database | Kiểm tra EXISTS, TTL, database và audit |
| Một môi trường nhận cấu hình của môi trường khác | Dùng chung Redis keyspace hoặc sai database/namespace | Tách deployment, database hoặc quy ước namespace phù hợp |

## 12. Tự kiểm tra

1. Vì sao Redis backend dùng hash thay vì lưu toàn bộ cấu hình thành một chuỗi duy nhất?
2. Hash `application-prod` khác `order-service-prod` ở phạm vi áp dụng như thế nào?
3. Nếu cùng property xuất hiện trong `application` và `order-service`, giá trị nào được ưu tiên?
4. Khi client dùng `spring.application.name=shared-platform,order-service`, hash nào có độ ưu tiên cao hơn?
5. Vì sao không nên mặc định Redis backend hỗ trợ branch và commit label giống Git?
6. Khi cập nhật nhiều field liên quan, làm thế nào để giảm khả năng client đọc trạng thái dở dang?
7. Những quyền Redis nào cần được giới hạn để tránh thay đổi cấu hình trái phép?
8. Nếu cần audit và rollback, cần bổ sung những cơ chế nào ngoài Redis hash?

Hãy dựng Redis test và một Config Server có profile `redis`. Tạo các hash `application`, `application-dev`, `order-service` và `order-service-dev`; ghi một field trùng tên ở hash dùng chung và hash ứng dụng. Gọi Config Server với application `order-service` và profile `dev`, sau đó xác nhận giá trị riêng của ứng dụng được ưu tiên. Tiếp tục cập nhật một field bằng HSET, kiểm tra lại response, rồi thử khôi phục snapshot trước đó. Thực hiện toàn bộ bài tập với dữ liệu giả lập, không dùng secret production.

## Tài liệu tham khảo

- [Spring Cloud Config — Redis Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/redis-backend.html)
- [Spring Cloud Config — Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Boot — Working with NoSQL Technologies (Redis)](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Redis Commands — HSET](https://redis.io/docs/latest/commands/hset/)
- [Redis Commands — HGETALL](https://redis.io/docs/latest/commands/hgetall/)

