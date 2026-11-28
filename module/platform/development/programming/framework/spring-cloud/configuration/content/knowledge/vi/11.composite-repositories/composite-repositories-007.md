# Kiểm chứng nguồn gốc giá trị sau khi tổng hợp

Khi Spring Cloud Config Server tổng hợp cấu hình từ nhiều repository, một thuộc tính có thể xuất hiện ở nhiều nguồn với các giá trị khác nhau. Ví dụ, repository nền tảng đặt `orders.timeout` là `2s`, còn repository của nhóm đơn hàng đặt cùng khóa thành `5s`. Client nhận giá trị nào phụ thuộc thứ tự ưu tiên của composite repository, thứ tự các property source bên trong từng repository và những nguồn cấu hình khác được áp dụng ở phía client.

Vì vậy, kiểm tra rằng API trả `200 OK` hoặc nhìn thấy khóa trong response là chưa đủ. Nhóm cần xác định repository nào cung cấp giá trị thắng, file và profile nào chứa khóa đó, label nào đã được đọc, và giá trị cuối cùng mà Spring Boot bind vào ứng dụng. Quá trình này được gọi là truy vết nguồn gốc cấu hình (configuration provenance).

## 1. Composite Environment Repository ghép cấu hình ra sao?

Composite Environment Repository cho phép Config Server đọc nhiều backend cấu hình và ghép các kết quả thành một Environment. Các backend có thể là nhiều Git repository hoặc những loại repository được Spring Cloud Config hỗ trợ. Client vẫn gửi một request theo application, profile và label; Config Server truy vấn các repository đã cấu hình rồi trả về danh sách `propertySources`.

Ví dụ Config Server sử dụng hai Git repository:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.com/orders/orders-config.git
            default-label: main
          - type: git
            uri: https://git.example.com/platform/platform-config.git
            default-label: main
```

Trong composite repository, thứ tự khai báo quyết định độ ưu tiên. Repository đầu tiên có ưu tiên cao nhất. Nếu cùng một khóa tồn tại trong nhiều repository, giá trị ở repository đứng trước sẽ thắng giá trị ở repository đứng sau. Với ví dụ trên, `orders-config` có ưu tiên cao hơn `platform-config`.

Điều này có nghĩa nhóm có thể đặt mặc định ở kho nền tảng và cho phép từng nhóm dịch vụ ghi đè bằng repository riêng. Nếu muốn mặc định nền tảng thắng mọi giá trị riêng, phải đổi thứ tự và ghi rõ ý định đó trong tài liệu thiết kế.

Ví dụ hai repository chứa cùng khóa:

```yaml
# orders-config/order-service-prod.yml
orders:
  timeout: 5s
  retry-limit: 2
```

```yaml
# platform-config/application.yml
orders:
  timeout: 2s
  retry-limit: 3
```

Với thứ tự `[orders-config, platform-config]`, kết quả tổng hợp dự kiến là `orders.timeout=5s` và `orders.retry-limit=2`. Nếu đổi thứ tự thành `[platform-config, orders-config]`, hai khóa trùng sẽ nhận giá trị từ kho nền tảng.

Thứ tự repository chỉ giải quyết xung đột giữa các nguồn trong composite. Nó không tự quyết định mọi ưu tiên trong toàn bộ Spring Boot Environment của Config Client. Biến môi trường, tham số dòng lệnh, system properties, cấu hình đóng gói và các property source khác vẫn có thể tác động đến giá trị cuối cùng. Vì vậy, phải kiểm tra cả response của Config Server lẫn Environment ở phía client.

### Trường hợp dùng nhiều backend profile thay cho `composite`

Nếu các backend có loại khác nhau và nhóm kích hoạt các profile backend riêng thay vì profile `composite` (ví dụ `git,vault`), có thể dùng thuộc tính `order` trên từng backend để xác định ưu tiên. Giá trị số `order` càng nhỏ thì ưu tiên càng cao. Đây là cơ chế cấu hình khác với thứ tự danh sách trong `spring.cloud.config.server.composite`; khi truy vết, cần ghi nhận đúng kiểu triển khai mà Config Server đang chạy.

## 2. Phân biệt thứ tự repository và thứ tự file trong một repository

Có hai lớp ưu tiên riêng biệt:

1. **Giữa các repository:** composite repository ưu tiên theo thứ tự khai báo; repository đầu tiên thắng khi trùng khóa.
2. **Bên trong mỗi repository:** Config Server áp dụng quy tắc phân giải application/profile tương tự Spring Boot. File theo application và profile cụ thể thường có ưu tiên cao hơn file mặc định dùng chung.

Ví dụ Config Client yêu cầu:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: dev,mysql
```

Trong một location dạng file, thứ tự property source thường đi từ ưu tiên cao xuống thấp như sau:

1. `order-service-mysql.yml`
2. `application-mysql.yml`
3. `order-service-dev.yml`
4. `application-dev.yml`
5. `order-service.yml`
6. `application.yml`

Profile active có ưu tiên cao hơn cấu hình mặc định; khi có nhiều profile, profile được liệt kê sau có ưu tiên cao hơn profile đứng trước theo quy tắc phân giải của Spring. File riêng ứng dụng cũng có ưu tiên cao hơn file `application` dùng chung ở cùng lớp profile.

Khi có composite, hai lớp này cùng tồn tại. Không nên nhìn riêng tên file rồi kết luận đó là giá trị cuối cùng. Cần quan sát danh sách property source mà Config Server trả về, theo đúng application/profile/label mà client yêu cầu.

## 3. Đọc `propertySources` trong response của Config Server

Endpoint Environment của Config Server có dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```bash
curl -sS \
  http://localhost:8888/order-service/prod/main
```

Response chứa tên ứng dụng, danh sách profile, label và các property source. Cấu trúc minh họa:

```json
{
  "name": "order-service",
  "profiles": ["prod"],
  "label": "main",
  "propertySources": [
    {
      "name": "https://git.example.com/orders/orders-config.git/order-service-prod.yml",
      "source": {
        "orders.timeout": "5s",
        "orders.retry-limit": 2
      }
    },
    {
      "name": "https://git.example.com/platform/platform-config.git/application.yml",
      "source": {
        "orders.timeout": "2s",
        "orders.retry-limit": 3
      }
    }
  ]
}
```

Đây là dữ liệu minh họa để giải thích cách đọc response; tên property source thực tế phụ thuộc backend và phiên bản. Trong response thật, hãy xem:

- `name`, `profiles` và `label` để xác nhận đúng request đã được xử lý.
- Thứ tự các phần tử trong `propertySources`; phần tử đứng trước có độ ưu tiên cao hơn.
- Tên của từng property source để nhận diện repository, file hoặc location nếu backend cung cấp thông tin đó.
- `source` để tìm tất cả nơi khai báo một khóa và so sánh các giá trị trùng.

Nếu `orders.timeout` xuất hiện trong property source đầu tiên với giá trị `5s`, còn property source sau có `2s`, thì giá trị thắng trong Environment do Config Server tổng hợp là `5s`. Property source phía sau vẫn có thể xuất hiện trong response; sự hiện diện của nó không có nghĩa nó đang thắng.

Có thể lọc nhanh một khóa bằng `jq`:

```bash
curl -sS http://localhost:8888/order-service/prod/main |
  jq '{name, profiles, label,
       propertySources: [.propertySources[] |
         {name, value: .source["orders.timeout"]}]}'
```

Kết quả cho thấy khóa có mặt ở những nguồn nào và tên nguồn tương ứng. Nếu công cụ hoặc backend không cung cấp tên repository/file rõ ràng, cần đối chiếu cấu trúc repository và log server để xác định nguồn chính xác.

## 4. Truy vết một thuộc tính từ repository đến ứng dụng

Một quy trình kiểm chứng tốt cần theo dõi một khóa cụ thể qua toàn bộ đường đi:

```text
Config Client
  application name + active profiles + requested label
        |
        v
Config Server Environment endpoint
        |
        v
Composite Environment Repository
  repository order: 1 -> 2 -> 3
        |
        v
Property sources của từng repository
  application/profile-specific files
        |
        v
Giá trị thắng trong Environment trả về
        |
        v
Config Client Environment
  remote config + local sources + overrides
        |
        v
@ConfigurationProperties / bean sử dụng giá trị
```

Với mỗi khóa cần kiểm tra, ghi lại ít nhất các thông tin sau:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Property key | Khóa chính xác là gì, có đúng prefix và cách viết không? |
| Application | Client yêu cầu tên ứng dụng nào? |
| Profile | Những profile nào đang active và theo thứ tự nào? |
| Label | Config Server đọc branch, tag hoặc commit nào? |
| Repository | Khóa xuất hiện trong những repository nào? |
| File/property source | File nào cung cấp giá trị ở từng repository? |
| Composite order | Repository nào có ưu tiên cao nhất? |
| Winning value | Giá trị nào xuất hiện đầu tiên theo thứ tự ưu tiên? |
| Client override | Có nguồn cấu hình phía client ghi đè kết quả từ xa không? |
| Bound value | Bean hoặc `@ConfigurationProperties` thực tế nhận giá trị nào? |

Ví dụ phiếu truy vết:

| Thuộc tính | Nguồn | Giá trị | Kết luận |
|---|---|---:|---|
| `orders.timeout` | `orders-config/order-service-prod.yml` | `5s` | Thắng do repository đứng đầu |
| `orders.timeout` | `platform-config/application.yml` | `2s` | Bị ghi đè bởi nguồn ưu tiên cao hơn |
| `orders.retry-limit` | `orders-config/order-service-prod.yml` | `2` | Thắng do repository đứng đầu |
| `orders.retry-limit` | `platform-config/application.yml` | `3` | Giá trị mặc định ở nguồn thấp hơn |

Phiếu này có thể lưu cùng pull request hoặc hồ sơ triển khai cho những thay đổi rủi ro cao. Nó giúp người review nhìn thấy cả giá trị thắng lẫn giá trị bị ghi đè.

## 5. Kiểm tra nguồn gốc ở phía Config Client bằng Actuator

Response Config Server cho biết cấu hình được tổng hợp từ các repository như thế nào. Nhưng giá trị cuối cùng trong ứng dụng còn có thể bị tác động bởi các nguồn cấu hình của chính client. Spring Boot Actuator cung cấp endpoint `env` để xem Environment và nguồn của từng thuộc tính khi endpoint được bật.

Ví dụ cấu hình chỉ expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
```

Trên Config Client, truy vấn một thuộc tính cụ thể:

```bash
curl -sS \
  http://localhost:8080/actuator/env/orders.timeout
```

Response của Actuator có thể cho biết:

- `property.value`: giá trị đã phân giải cho khóa được truy vấn.
- `property.source`: property source cung cấp giá trị đang có hiệu lực.
- `property.origin`: nguồn gốc chi tiết nếu có metadata origin, ví dụ file và vị trí dòng/cột.
- `propertySources`: danh sách các property source theo thứ tự ưu tiên, bao gồm những nguồn có khai báo khóa đó.

Với Config Client dùng Spring Cloud Config, tên property source có thể chứa URL của repository/file từ xa, ví dụ dạng `configserver:<repository>/<file>`. Metadata origin nếu được truyền có thể chỉ ra file cấu hình và vị trí của khóa. Tên và mức độ chi tiết phụ thuộc backend, phiên bản và việc nguồn có cung cấp origin metadata hay không.

`/actuator/env` là nơi kiểm tra nguồn thuộc tính trong Environment của client. `/actuator/configprops` hữu ích để xem các thuộc tính đã bind vào `@ConfigurationProperties`; hai endpoint phục vụ mục đích khác nhau. Nếu Environment có giá trị đúng nhưng bean nhận giá trị khác, hãy kiểm tra prefix, kiểu dữ liệu, validation, default trong lớp cấu hình và thời điểm bean được tạo.

## 6. Phân biệt giá trị trong Config Server và giá trị hiệu lực trong Client

Một lỗi phổ biến là kiểm tra response Config Server, thấy `orders.timeout=5s`, rồi kết luận ứng dụng chắc chắn đang dùng `5s`. Điều đó chỉ chứng minh Config Server trả giá trị này trong Environment từ xa.

Ví dụ Config Client có biến môi trường:

```text
ORDERS_TIMEOUT=1s
```

Hoặc được khởi chạy với tham số:

```bash
java -jar order-service.jar --orders.timeout=750ms
```

Các property source phía client có thể có độ ưu tiên cao hơn cấu hình từ xa theo quy tắc Spring Boot đang áp dụng. Khi đó, Config Server vẫn trả `5s`, nhưng ứng dụng cuối cùng dùng giá trị khác. Cần kiểm tra `/actuator/env/orders.timeout` trên đúng instance client và xác định nguồn đang thắng.

Ngoài biến môi trường và tham số dòng lệnh, hãy xem xét:

- `application.yml` hoặc `application-prod.yml` được đóng gói cùng client.
- System properties truyền qua JVM.
- Cấu hình từ Config Data import khác.
- Placeholder hoặc default trong `@Value` và `@ConfigurationProperties`.
- `spring.cloud.config.server.overrides` nếu Config Server được cấu hình property overrides cho tất cả client.
- Giá trị được gán lại trong code, cache hoặc logic khởi tạo riêng.

Không nên suy luận thứ tự ưu tiên toàn cục chỉ từ thứ tự repository. Composite order chỉ giải quyết thứ tự giữa các Environment Repository trong composite. Các nguồn ở những tầng khác phải được kiểm tra trên client.

## 7. Label và profile phải nhất quán giữa các repository

Composite request sử dụng một bộ application, profile và label để truy vấn các repository. Với các composite repository, tất cả repository cần có label tương ứng. Nếu client yêu cầu label `release-2026.11` nhưng một repository không có branch/tag tương ứng, request composite có thể thất bại.

Ví dụ, nếu composite có ba Git repository:

```text
orders-config       -> release-2026.11
platform-config     -> release-2026.11
security-config     -> main only
```

Yêu cầu label `release-2026.11` có thể thất bại do `security-config` không có label đó, ngay cả khi hai repository còn lại đã sẵn sàng. Trước khi phát hành, cần tạo hoặc xác nhận label tương ứng ở tất cả repository được composite sử dụng.

Đối với production, nên lưu lại commit SHA của từng repository cùng phiên bản ứng dụng. Một label tên giống nhau ở các kho không bảo đảm các commit được tạo cùng thời điểm hoặc cùng một đợt phát hành. Hồ sơ triển khai nên ghi:

- application/profile được yêu cầu;
- label được gửi;
- Git URI của từng repository;
- commit SHA thực tế được sử dụng;
- thứ tự ưu tiên composite tại thời điểm phát hành.

Điều này đặc biệt quan trọng khi rollback hoặc điều tra sự cố xảy ra sau khi một repository được cập nhật nhưng các repository khác chưa được cập nhật.

## 8. Xử lý khi một repository trong composite bị lỗi

Theo mặc định, lỗi khi lấy dữ liệu từ một repository trong composite có thể làm toàn bộ composite request thất bại. Điều này tránh việc server âm thầm trả về một tập cấu hình thiếu nguồn.

Có thể cấu hình:

```yaml
spring:
  cloud:
    config:
      server:
        fail-on-composite-error: false
```

Khi đặt `fail-on-composite-error: false`, composite có thể tiếp tục dù một repository gặp lỗi. Cách này có thể hữu ích khi một nguồn thực sự là tùy chọn, nhưng nó cũng tạo nguy cơ trả cấu hình một phần. Nếu repository chứa khóa bắt buộc bị lỗi, giá trị từ nguồn ưu tiên thấp hơn có thể trở thành giá trị thắng hoặc ứng dụng có thể rơi về default.

Không nên bật tùy chọn này chỉ để tránh lỗi khởi động. Trước khi sử dụng, phải phân loại repository bắt buộc và tùy chọn, xác định khóa nào bị ảnh hưởng khi nguồn lỗi, giám sát trạng thái từng repository và thể hiện rõ trong response/log rằng composite đang thiếu nguồn. Với cấu hình bảo mật, endpoint thanh toán, quyền truy cập hoặc giới hạn giao dịch, phản hồi thất bại rõ ràng thường an toàn hơn cấu hình một phần.

## 9. Kiểm chứng thứ tự ưu tiên bằng một thử nghiệm có chủ đích

Khi thiết kế composite mới hoặc đổi thứ tự repository, nên tạo một thử nghiệm trong môi trường phát triển với cùng một khóa có giá trị khác nhau ở từng nguồn.

Ví dụ:

```yaml
# repo-first/application.yml
provenance:
  marker: FROM_REPO_FIRST
```

```yaml
# repo-second/application.yml
provenance:
  marker: FROM_REPO_SECOND
```

Đặt thứ tự composite là `repo-first`, sau đó `repo-second`, rồi gọi endpoint:

```bash
curl -sS \
  http://localhost:8888/order-service/prod/main
```

Kiểm tra response để xác nhận:

1. Cả hai property source đều xuất hiện nếu cả hai repository cung cấp file phù hợp.
2. Property source từ `repo-first` đứng trước property source từ `repo-second`.
3. Giá trị hiệu lực của `provenance.marker` là `FROM_REPO_FIRST`.
4. Khi đổi thứ tự repository, giá trị thắng thay đổi theo thiết kế mới.
5. Trên Config Client, `/actuator/env/provenance.marker` xác nhận nguồn và giá trị cuối cùng.

Thử nghiệm này biến quy tắc ưu tiên thành hành vi có thể quan sát. Sau khi xác nhận, hãy giữ lại kết quả hoặc kiểm tra tự động trong pipeline để phát hiện việc đổi thứ tự ngoài ý muốn.

## 10. Bảo vệ endpoint chẩn đoán và dữ liệu nhạy cảm

Endpoint Config Server trả về nội dung cấu hình. Endpoint Actuator `env` có thể cho biết tên property source, origin và giá trị của thuộc tính nếu được phép hiển thị. Những thông tin này hữu ích cho vận hành nhưng có thể tiết lộ endpoint nội bộ, tên repository, cấu trúc hạ tầng hoặc bí mật.

Các nguyên tắc bảo vệ:

- Chỉ expose `/actuator/env` và `/actuator/configprops` trong mạng quản trị hoặc cho nhóm vận hành được cấp quyền.
- Bật xác thực và phân quyền cho endpoint; không dựa vào việc URL khó đoán.
- Giữ cơ chế sanitization giá trị nhạy cảm theo mặc định; không bật hiển thị toàn bộ secret chỉ để debug.
- Không gửi response Environment đầy đủ vào log công khai hoặc ticket không được bảo vệ.
- Nếu cần kiểm tra một khóa nhạy cảm, xác nhận source/origin và trạng thái có giá trị mà không tiết lộ nội dung bí mật.
- Dùng request ID để nối log giữa Config Client, Config Server, proxy và hệ thống Git.

Nếu một property source tùy chỉnh không cung cấp origin metadata, đừng giả định Actuator có thể xác định chính xác file hoặc dòng. Hãy bổ sung metadata nguồn trong implementation hoặc tạo audit record ở pipeline cấu hình. Tên property source có thể cho biết backend nhưng không nhất thiết chỉ ra vị trí chính xác của từng khóa.

## 11. Checklist truy vết trước khi phát hành

| Kiểm tra | Điều kiện đạt |
|---|---|
| Composite order | Danh sách repository và thứ tự ưu tiên được review, có chủ sở hữu |
| Duplicate keys | Các khóa trùng được liệt kê; giá trị thắng được xác nhận có chủ đích |
| Application/profile | Client gửi đúng application và profile; profile được sắp theo quy tắc đã thống nhất |
| Label | Tất cả repository có label được yêu cầu; commit SHA được ghi nhận |
| Property sources | Response Config Server cho thấy đúng nguồn và thứ tự mong đợi |
| Client Environment | Actuator env trên instance thực tế cho thấy đúng source và effective value |
| Bound configuration | `@ConfigurationProperties` nhận đúng giá trị và vượt qua validation |
| Client overrides | Biến môi trường, JVM args, command line và file local không ghi đè ngoài dự kiến |
| Repository availability | Tất cả nguồn bắt buộc truy cập được; không có composite partial ngoài ý muốn |
| Security | Endpoint chẩn đoán được bảo vệ và giá trị nhạy cảm được sanitization |
| Rollback | Có thể tái tạo tổ hợp label/commit trước đó và xác minh lại nguồn thắng |

## 12. Nguyên tắc cần ghi nhớ

- Repository đầu tiên trong cấu hình `composite` có ưu tiên cao nhất; khóa trùng ở nguồn sau bị ghi đè.
- Thứ tự file/profile bên trong từng repository là một lớp ưu tiên riêng.
- `propertySources` trong Environment được sắp theo độ ưu tiên; tên nguồn và nội dung source giúp nhận diện nơi khai báo khóa.
- Config Server Environment cho biết giá trị tổng hợp từ xa; Actuator `env` trên Config Client cho biết nguồn và giá trị trong Environment cuối cùng.
- `configprops` giúp xác nhận giá trị đã bind vào bean; cần đối chiếu với `env` nếu có chênh lệch.
- Composite repository cần label tương ứng ở tất cả backend; một label thiếu có thể làm request thất bại.
- Mặc định lỗi một repository có thể làm cả composite thất bại; chỉ cho phép lỗi một phần khi nguồn đó thật sự tùy chọn và có giám sát.
- Ghi nhận repository, file, label, commit SHA và thứ tự ưu tiên cho các lần phát hành production.
- Bảo vệ endpoint Actuator và không làm lộ giá trị bí mật khi truy vết.

Kiểm chứng nguồn gốc giá trị sau khi tổng hợp là việc nối được ba câu trả lời: repository nào đã cung cấp thuộc tính, quy tắc ưu tiên nào khiến giá trị đó thắng, và Config Client cuối cùng đang sử dụng giá trị nào. Khi kiểm tra cả `propertySources` ở Config Server lẫn `env`/`configprops` ở client, nhóm có thể giải thích và tái lập hành vi cấu hình thay vì chỉ đoán dựa trên file YAML.

## Tài liệu tham khảo

- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
- [Spring Cloud Config — Environment Repository và quy tắc profile](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html)
- [Spring Boot Actuator — Environment (`env`) endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/env.html)
