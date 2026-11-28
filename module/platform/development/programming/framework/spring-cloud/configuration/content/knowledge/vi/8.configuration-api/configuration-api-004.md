# Truy xuất cấu hình dưới dạng YAML hoặc properties

Spring Cloud Config Server cung cấp cấu hình qua HTTP để ứng dụng, pipeline triển khai hoặc người vận hành có thể lấy cấu hình theo tên ứng dụng, profile và label. Ngoài endpoint Environment mặc định trả về JSON, Config Server còn có các endpoint đuôi `.yml`, `.yaml` và `.properties` để biểu diễn cấu hình dưới dạng YAML hoặc Java properties.

Khả năng này hữu ích khi cần xem nhanh cấu hình hiệu lực của một ứng dụng, tạo file cấu hình cho công cụ khác, kiểm tra thay đổi trong pipeline hoặc hỗ trợ chẩn đoán mà không phải clone repository Git trên máy đang truy vấn. Cần phân biệt endpoint trả về cấu hình đã được Config Server phân giải với endpoint phục vụ một file nguyên bản trong repository; hai loại endpoint phục vụ mục đích khác nhau.

## 1. Chuẩn bị Config Server và kho cấu hình

Config Server đọc repository và cung cấp HTTP API. Ví dụ repository:

```text
config-repo/
├── application.yml
├── orders-service.yml
└── orders-service-prod.yml
```

`application.yml` chứa thuộc tính dùng chung:

```yaml
platform:
  region: ap-southeast-1
  connect-timeout: 2s
```

`orders-service.yml` chứa cấu hình mặc định riêng cho dịch vụ:

```yaml
orders:
  http:
    read-timeout: 5s
  retry:
    max-attempts: 2
```

`orders-service-prod.yml` điều chỉnh giá trị cho production:

```yaml
orders:
  http:
    read-timeout: 10s
  retry:
    max-attempts: 4
```

Config Server có thể cấu hình Git backend như sau:

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
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
```

Ứng dụng server cần bật `@EnableConfigServer`:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Config Server cần có quyền đọc repository. Với repository riêng tư, cấp credential qua secret hoặc cơ chế quản lý thông tin xác thực của môi trường triển khai; không ghi token hay private key trực tiếp vào file cấu hình được commit.

## 2. Endpoint Environment mặc định trả JSON

Endpoint phổ biến nhất có dạng:

```text
/{application}/{profile}[/{label}]
```

Trong đó:

- `application` là tên ứng dụng, thường trùng với `spring.application.name` của Config Client.
- `profile` là một hoặc nhiều profile mà server cần tìm cấu hình, ví dụ `dev` hoặc `prod`.
- `label` là branch, tag hoặc revision của repository. Nếu bỏ qua, Config Server dùng label mặc định đã cấu hình.

Ví dụ lấy cấu hình production của `orders-service` ở branch `main`:

```bash
curl http://localhost:8888/orders-service/prod/main
```

Endpoint này trả về một đối tượng Environment dạng JSON. Response thường chứa tên ứng dụng, các profile, label, revision và danh sách property source. Ví dụ rút gọn:

```json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "main",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": "orders-service-prod.yml",
      "source": {
        "orders.http.read-timeout": "10s",
        "orders.retry.max-attempts": 4
      }
    },
    {
      "name": "application.yml",
      "source": {
        "platform.region": "ap-southeast-1",
        "platform.connect-timeout": "2s"
      }
    }
  ]
}
```

Đây là response minh họa rút gọn. Tên property source, thứ tự và trường revision thực tế phụ thuộc backend và cấu hình server. Mỗi phần tử trong `propertySources` cho biết nguồn và các key-value mà nguồn đó cung cấp. Khi có key trùng nhau, thứ tự property source là thông tin quan trọng để hiểu giá trị hiệu lực.

Endpoint JSON phù hợp khi cần kiểm tra nguồn gốc, profile, label và revision. Nó cũng hữu ích cho công cụ tự động muốn phân tích response thành cấu trúc dữ liệu.

## 3. Lấy cấu hình dưới dạng YAML

Để nhận cấu hình đã được phân giải dưới dạng YAML, thêm đuôi `.yml` hoặc `.yaml` vào endpoint:

```text
/{application}-{profile}.yml
/{application}-{profile}.yaml
/{label}/{application}-{profile}.yml
/{label}/{application}-{profile}.yaml
```

Ví dụ lấy cấu hình production của `orders-service` từ label mặc định:

```bash
curl http://localhost:8888/orders-service-prod.yml
```

Hoặc chỉ định rõ label:

```bash
curl http://localhost:8888/main/orders-service-prod.yml
```

Kết quả là biểu diễn YAML của các thuộc tính đã được Config Server tổng hợp cho application và profile tương ứng. Một response minh họa:

```yaml
platform:
  region: ap-southeast-1
  connect-timeout: 2s
orders:
  http:
    read-timeout: 10s
  retry:
    max-attempts: 4
```

Endpoint YAML thuận tiện cho người đọc và các công cụ nhận đầu vào YAML. Cấu trúc cụ thể trong response do bộ chuyển đổi định dạng tạo ra từ các property source; không nên dựa vào thứ tự key trong YAML để suy luận thứ tự ưu tiên. Nếu cần biết nguồn nào cung cấp một giá trị, hãy dùng endpoint Environment JSON.

## 4. Lấy cấu hình dưới dạng Java properties

Endpoint tương ứng cho định dạng properties:

```text
/{application}-{profile}.properties
/{label}/{application}-{profile}.properties
```

Ví dụ:

```bash
curl http://localhost:8888/orders-service-prod.properties
curl http://localhost:8888/main/orders-service-prod.properties
```

Kết quả minh họa:

```properties
platform.region=ap-southeast-1
platform.connect-timeout=2s
orders.http.read-timeout=10s
orders.retry.max-attempts=4
```

Định dạng properties phù hợp với công cụ Java, script hoặc hệ thống triển khai đang mong đợi key-value dạng dòng. Các thuộc tính lồng nhau thường được biểu diễn bằng tên key có dấu chấm. Nếu giá trị chứa ký tự đặc biệt, khoảng trắng, dấu `=` hoặc ký tự xuống dòng, cần chú ý quy tắc escape của Java properties khi xử lý response.

Không cần đổi file nguồn trong Git từ YAML sang properties để yêu cầu endpoint properties. Config Server phân tích các nguồn cấu hình rồi cung cấp kết quả theo định dạng được yêu cầu. Tương tự, repository có thể chứa file properties nhưng client hoặc công cụ truy vấn vẫn có thể yêu cầu biểu diễn YAML.

## 5. So sánh các dạng endpoint

| Mục đích | Ví dụ endpoint | Dữ liệu nhận được |
| --- | --- | --- |
| Xem Environment và property source | `/orders-service/prod/main` | JSON có metadata và danh sách nguồn |
| Nhận cấu hình YAML | `/orders-service-prod.yml` | Thuộc tính đã tổng hợp dưới dạng YAML |
| Nhận cấu hình properties | `/orders-service-prod.properties` | Thuộc tính đã tổng hợp dưới dạng Java properties |
| Ghim revision Git | `/main/orders-service-prod.yml` | YAML từ label `main` |
| Kiểm tra revision khác | `/release-2026.11/orders-service-prod.properties` | Properties từ label phát hành |

Ba loại endpoint đầu tiên có thể dùng chung application và profile nhưng khác mục đích. JSON hữu ích để quan sát metadata và property source; YAML/properties thuận tiện để đọc hoặc chuyển tiếp cấu hình đã được phân giải.

Các endpoint đuôi mở rộng có dạng rút gọn, không mang đầy đủ metadata như endpoint Environment. Khi điều tra sự cố hoặc so sánh nguồn, hãy gọi thêm endpoint JSON để biết server đã chọn profile, label và property source nào.

## 6. Truy vấn nhiều profile

Config Server hỗ trợ yêu cầu nhiều profile trong cùng một request bằng cách phân tách tên profile bằng dấu phẩy. Ví dụ:

```bash
curl "http://localhost:8888/orders-service/dev,prod/main"
```

Có thể dùng cùng cách biểu diễn ở endpoint đuôi mở rộng khi cần lấy cấu hình theo tổ hợp profile:

```bash
curl "http://localhost:8888/orders-service-dev,prod.yml"
```

Kết quả phụ thuộc thứ tự và cách Spring xử lý các profile đang hoạt động. Nếu nhiều profile cùng định nghĩa một key, property source có độ ưu tiên cao hơn sẽ quyết định giá trị cuối cùng. Hãy kiểm tra endpoint Environment JSON để thấy danh sách profile và property source được trả về; tránh dựa vào một file riêng lẻ để kết luận giá trị cuối cùng.

Trong triển khai thực tế, nên giữ tổ hợp profile đơn giản. Nếu một profile group luôn đi cùng nhau, có thể cấu hình profile group ở ứng dụng client. Cần phân biệt profile group của Spring Boot với việc truyền một danh sách profile trong URL Config Server: group được client mở rộng khi kích hoạt, còn URL biểu diễn trực tiếp các profile mà server nhận được.

## 7. Chỉ định label và xử lý tên branch

Label có thể là branch, tag hoặc commit SHA. Nếu không truyền label trong endpoint, server dùng `spring.cloud.config.server.git.default-label`. Khi cần kiểm tra một bản cấu hình cụ thể, hãy truyền label rõ ràng.

Ví dụ với tag:

```bash
curl http://localhost:8888/config-v2.4.0/orders-service-prod.yml
```

Ví dụ với branch có dấu gạch chéo như `release/2026.11`, phần label trong URL path cần được biểu diễn theo quy tắc của Config Server. Spring Cloud Config hỗ trợ cách thay dấu `/` bằng `(_)` trong path:

```bash
curl "http://localhost:8888/release(_)2026.11/orders-service-prod.yml"
```

Khi sử dụng label là commit SHA, response Environment JSON có thể giúp xác nhận revision server đã đọc. Branch có thể tiến lên theo thời gian, vì vậy cùng một URL dùng branch `main` có thể trả cấu hình khác sau một commit mới. Với production, ưu tiên tag bất biến hoặc commit đã được phê duyệt và lưu lại revision thực tế.

## 8. Phân biệt cấu hình đã phân giải và file nguyên bản

Config Server còn có endpoint phục vụ file theo đường dẫn:

```text
/{application}/{profile}/{label}/{path}
```

Ví dụ:

```bash
curl http://localhost:8888/orders-service/prod/main/banner.txt
```

Endpoint này dùng để lấy một resource theo đường dẫn từ repository và trả nội dung file. Nếu file là YAML hoặc properties, nội dung nhận được là file resource đó, không phải Environment đã hợp nhất các property source của application và profile.

Sự khác biệt rất quan trọng:

- Dùng `/{application}-{profile}.yml` hoặc `.properties` khi cần cấu hình đã được Config Server phân giải theo application/profile.
- Dùng `/{application}/{profile}/{label}/{path}` khi cần đọc một file cụ thể trong repository.
- Dùng `/{application}/{profile}/{label}` khi cần metadata, property source và revision của Environment.

Không dùng endpoint resource để suy ra giá trị cuối cùng của một key nếu key đó có thể xuất hiện trong nhiều file hoặc nhiều nguồn.

## 9. Dùng curl để lưu kết quả vào file

Có thể lưu response YAML hoặc properties vào file để kiểm tra, so sánh hoặc chuyển cho một công cụ khác. Ví dụ:

```bash
curl --fail --silent --show-error \
  http://localhost:8888/orders-service-prod.yml \
  --output orders-service-prod.yml

curl --fail --silent --show-error \
  http://localhost:8888/orders-service-prod.properties \
  --output orders-service-prod.properties
```

Các tùy chọn có ý nghĩa:

- `--fail` làm curl trả lỗi khi HTTP response là mã lỗi, thay vì lưu trang lỗi như nội dung thành công.
- `--silent` giảm thông tin tiến trình.
- `--show-error` vẫn hiển thị thông báo lỗi khi kết hợp với silent.
- `--output` ghi body vào file đã chỉ định.

Nếu cần kiểm tra status code và header, dùng:

```bash
curl --include http://localhost:8888/orders-service-prod.yml
```

Header giúp kiểm tra HTTP status, content type và thông tin cache nếu server gửi. Không nên chỉ dựa vào việc file đã được tạo để kết luận truy vấn thành công; cần kiểm tra mã HTTP và nội dung nhận được.

Có thể dùng `diff` để so sánh hai revision:

```bash
curl --fail --silent --show-error \
  http://localhost:8888/release-2026.10/orders-service-prod.properties \
  --output previous.properties

curl --fail --silent --show-error \
  http://localhost:8888/release-2026.11/orders-service-prod.properties \
  --output current.properties

diff -u previous.properties current.properties
```

Kết quả so sánh giúp review thay đổi cấu hình giữa hai bản phát hành. Nếu file có chứa thông tin nhạy cảm, không đưa nội dung vào log CI hoặc lưu artifact có phạm vi truy cập rộng.

## 10. Xử lý lỗi khi truy xuất

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| HTTP 404 | Sai application, profile, label hoặc đường dẫn endpoint | Gọi endpoint JSON và kiểm tra Git ref/file |
| HTTP 401 hoặc 403 | Config Server yêu cầu xác thực hoặc tài khoản không có quyền | Kiểm tra credential và quyền truy cập |
| HTTP 5xx | Server không đọc được repository hoặc lỗi backend | Kiểm tra log Config Server, Git URI và kết nối |
| YAML/properties thiếu key | Key không tồn tại ở profile/label đang yêu cầu hoặc bị nguồn khác ghi đè | Xem Environment JSON và property source |
| Kết quả khác với file Git | Nhiều file cùng khai báo key hoặc đang dùng label khác | Xác nhận application/profile/label và thứ tự nguồn |
| Kết quả vẫn là revision cũ | Branch/tag, cache hoặc thời điểm fetch Git chưa như mong đợi | Kiểm tra revision, fetch policy và gọi lại endpoint |
| Không phân tích được response | Nhầm endpoint Environment với endpoint định dạng hoặc resource | Kiểm tra URL và Content-Type/body |

Khi chẩn đoán, nên thực hiện theo thứ tự:

1. Xác nhận Config Server có thể truy cập và trả HTTP status phù hợp.
2. Gọi endpoint JSON `/{application}/{profile}/{label}` để kiểm tra metadata và property source.
3. Gọi endpoint `.yml` hoặc `.properties` cho cùng application/profile/label để so sánh nội dung.
4. Kiểm tra revision Git và các file nguồn trong repository nếu response không đúng mong đợi.
5. Nếu client nhận giá trị khác, kiểm tra thêm property source ở phía Spring Environment của client; nguồn cục bộ, biến môi trường hoặc tham số dòng lệnh có thể ảnh hưởng kết quả cuối cùng.

Không nên xử lý mọi lỗi 404 bằng cách đổi profile tùy ý. Hãy xác nhận tên file và label tồn tại trong repository trước, sau đó kiểm tra chính xác URL mà client hoặc người vận hành đã gọi.

## 11. Bảo vệ API cấu hình

API Config Server có thể trả về endpoint, địa chỉ dịch vụ, feature flag và các thông tin vận hành. Nếu repository có dữ liệu nhạy cảm hoặc server hỗ trợ giải mã secret, quyền truy cập API cần được kiểm soát nghiêm ngặt.

Các nguyên tắc cơ bản:

- Bật HTTPS hoặc TLS ở lớp ingress/reverse proxy và bảo vệ kết nối nội bộ theo yêu cầu.
- Yêu cầu xác thực và phân quyền cho client, pipeline và người vận hành.
- Chỉ cấp quyền đọc những ứng dụng hoặc môi trường mà caller cần.
- Không expose Config Server trực tiếp ra internet nếu không có lớp bảo vệ phù hợp.
- Không lưu secret dạng rõ trong Git; dùng secret manager hoặc cơ chế mã hóa được quản lý an toàn.
- Giới hạn log truy vấn và không ghi body chứa secret vào log hoặc artifact CI.
- Bảo vệ các endpoint quản trị và endpoint hỗ trợ mã hóa/giải mã riêng biệt.

Endpoint YAML hoặc properties không tự động an toàn hơn endpoint JSON. Cả ba đều có thể cung cấp dữ liệu cấu hình; lựa chọn định dạng không thay thế xác thực và phân quyền. Cũng cần xem xét việc file đã lưu xuống máy người dùng hoặc artifact pipeline được bảo vệ như thế nào.

## 12. Chọn định dạng theo mục đích

- Chọn **JSON Environment** khi cần metadata, revision, profile và danh sách property source để chẩn đoán hoặc tự động hóa.
- Chọn **YAML** khi người vận hành cần đọc cấu hình phân cấp hoặc công cụ nhận YAML.
- Chọn **properties** khi hệ thống tích hợp cần key-value dạng Java properties.
- Chọn **resource endpoint** khi cần nội dung nguyên bản của một file cụ thể trong repository.

Các định dạng chỉ là những cách trình bày hoặc truy cập khác nhau của dữ liệu cấu hình. Application, profile và label vẫn xác định tập cấu hình được chọn. Property source và thứ tự ưu tiên quyết định giá trị hiệu lực; revision Git cho biết phiên bản cấu hình đã được dùng.

Khi cần truy vết một giá trị, hãy bắt đầu từ endpoint Environment JSON để thấy nguồn và revision, sau đó dùng YAML hoặc properties nếu cần lưu hoặc chia sẻ kết quả đã phân giải. Cách làm này giúp người vận hành hiểu rõ dữ liệu được lấy từ đâu và tránh nhầm lẫn giữa một file riêng lẻ với cấu hình tổng hợp mà ứng dụng thực sự nhận.

