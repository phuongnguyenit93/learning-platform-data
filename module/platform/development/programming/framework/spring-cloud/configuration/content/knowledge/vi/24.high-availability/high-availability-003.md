# Nhiều URI trong Config Client so với nhiều vị trí Config Data import

Spring Cloud Config Client có hai cách thường gặp để kết nối tới nhiều Config Server: khai báo danh sách URL trong `spring.cloud.config.uri`, hoặc khai báo nhiều location `configserver:` trong `spring.config.import`. Cả hai đều có thể giúp ứng dụng tiếp tục lấy cấu hình khi một endpoint gặp sự cố, nhưng chúng có ngữ nghĩa khác nhau về failover, thứ tự xử lý, độ ưu tiên property source và cách điều khiển lỗi.

Với `spring.cloud.config.uri`, client thử các địa chỉ theo thứ tự cho tới khi một request thành công theo chiến lược đã chọn. Cách này phù hợp khi các URL là các replica tương đương của cùng một Config Server. Với nhiều Config Data import, các location được xử lý theo thứ tự khai báo và import sau có độ ưu tiên cao hơn. Cách này có thể tạo nhiều lớp cấu hình từ các nguồn khác nhau; nếu dùng nhiều replica giống nhau, cần cân nhắc nguy cơ một nguồn ghi đè nguồn còn lại.

## 1. Hai cách cấu hình và mục đích

| Cách | Thuộc tính | Mục đích chính | Độ ưu tiên |
|---|---|---|---|
| Danh sách URI Config Client | `spring.cloud.config.uri` | Thử endpoint Config Server theo thứ tự để tìm một endpoint phục vụ được request | Dùng endpoint thành công đầu tiên theo chiến lược failover; không ghép property source từ tất cả URI |
| Nhiều Config Data import | `spring.config.import` | Khai báo nhiều location Config Server; các import được xử lý theo thứ tự và import sau có thể ghi đè import trước | Import khai báo sau có độ ưu tiên cao hơn khi cùng key |

Một cách ghi nhớ hữu ích:

- **Nhiều URI trong `spring.cloud.config.uri`:** nhiều địa chỉ thay thế cho cùng một nguồn cấu hình.
- **Nhiều location `configserver:` trong `spring.config.import`:** nhiều lần import cấu hình theo thứ tự, có thể tạo các lớp property source.

Không nên dùng nhiều import chỉ để giả lập danh sách replica mà không hiểu thứ tự precedence. Nếu các server là bản sao tương đương, danh sách URI thường thể hiện đúng ý định failover hơn.

## 2. Danh sách URI qua `spring.cloud.config.uri`

`spring.cloud.config.uri` nhận danh sách URL phân tách bằng dấu phẩy. Config Client thử URL theo thứ tự đã khai báo. Mặc định, `spring.cloud.config.multiple-uri-strategy` là `always`: client tiếp tục thử URL kế tiếp cho tới khi một lần lấy cấu hình thành công.

Ví dụ:

```yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:"
  cloud:
    config:
      uri: "https://config-a.internal:8888,https://config-b.internal:8888"
      multiple-uri-strategy: always
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Ở đây `configserver:` không chỉ rõ hostname, vì vậy client dùng các URI được khai báo trong `spring.cloud.config.uri`. Client ưu tiên `config-a`; nếu request không thành công theo chiến lược `always`, nó thử `config-b`.

Danh sách này không phải round-robin load balancing. Client thử theo thứ tự, không chia đều request giữa các URI. Nếu `config-a` luôn trả thành công, `config-b` có thể rất ít khi được sử dụng. Nếu cần phân phối tải thường xuyên, dùng load balancer hoặc service discovery được thiết kế cho mục đích đó.

### Chọn `multiple-uri-strategy`

Có hai lựa chọn quan trọng:

| Giá trị | Hành vi |
|---|---|
| `always` (mặc định) | Tiếp tục thử URI tiếp theo khi request trước không thành công, bất kể loại lỗi |
| `connection-timeout-only` | Chỉ failover khi Config Server không chạy hoặc xảy ra lỗi timeout kết nối; các lỗi phản hồi như HTTP 401 hoặc 500 không làm client thử URI kế tiếp |

Ví dụ:

```yaml
spring:
  cloud:
    config:
      uri: "https://config-a.internal:8888,https://config-b.internal:8888"
      multiple-uri-strategy: connection-timeout-only
```

`connection-timeout-only` hữu ích khi muốn phân biệt lỗi hạ tầng với lỗi cấu hình hoặc xác thực. Nếu server trả 401 do credential sai hoặc 500 do lỗi xử lý, chuyển sang replica khác có thể che giấu một vấn đề chung. Với chiến lược này, client dừng ở lỗi phản hồi đó thay vì thử URI tiếp theo.

Tài liệu Spring Cloud Config lưu ý rằng lỗi 400 thường phản ánh request không hợp lệ, ngoại trừ trường hợp 404 cần được xem xét theo ngữ cảnh. Ví dụ, Config Server dùng Git backend nhưng không truy cập được Git server có thể trả 404. Vì vậy, khi chẩn đoán 404 cần xem log Config Server và backend, không chỉ kết luận application/profile/label sai.

## 3. Nhiều vị trí `configserver:` trong `spring.config.import`

Spring Boot Config Data cho phép khai báo nhiều location trong một `spring.config.import`. Các location được xử lý theo thứ tự khai báo; import sau có độ ưu tiên cao hơn khi trùng key.

Ví dụ:

```yaml
spring:
  application:
    name: order-service
  config:
    import:
      - "configserver:https://config-platform.internal:8888"
      - "configserver:https://config-commerce.internal:8888"
```

Trong ví dụ này, ứng dụng import cấu hình từ hai location. Nếu cả hai cùng cung cấp `checkout.timeout`, giá trị từ location được xử lý sau có thể ghi đè giá trị của location trước. Đây là cách layering cấu hình, không đơn thuần là chọn một replica trong danh sách.

Ví dụ về thứ tự:

| Location | `checkout.timeout` | `logging.level.root` |
|---|---:|---|
| `config-platform` (import trước) | `2s` | `INFO` |
| `config-commerce` (import sau) | `5s` | `DEBUG` |
| Giá trị có hiệu lực sau import | `5s` | `DEBUG` |

Mô hình này phù hợp khi các Config Server cung cấp các lớp cấu hình khác nhau, ví dụ một nguồn nền tảng và một nguồn theo domain/đội. Tuy nhiên, hãy đảm bảo việc layering là chủ đích, được tài liệu hóa và có kiểm thử các key trùng.

### Hành vi lỗi với nhiều Config Data import

Khi dùng nhiều Config Server location trong `spring.config.import`, `spring.cloud.config.fail-fast` ảnh hưởng tới cách xử lý lỗi:

- Khi `fail-fast=true`, Config Client thất bại nếu lần gọi Config Server đầu tiên không thành công.
- Khi `fail-fast=false`, client thử các URL cho tới khi có một lần gọi thành công, bất kể lý do lỗi trước đó.
- `spring.cloud.config.multiple-uri-strategy` không áp dụng cho các URL được khai báo trực tiếp trong `spring.config.import`.

Ví dụ khai báo rõ chính sách:

```yaml
spring:
  cloud:
    config:
      fail-fast: false
  config:
    import:
      - "configserver:https://config-a.internal:8888"
      - "configserver:https://config-b.internal:8888"
```

Đọc kỹ mục tiêu của cấu hình trước khi chọn cách này: nhiều import được xử lý theo thứ tự và import sau có precedence cao hơn; chính sách fail-fast điều khiển phản ứng khi lần gọi thất bại. Không áp dụng `multiple-uri-strategy` rồi kỳ vọng nó điều khiển các import riêng lẻ.

Nếu nguồn Config Server là bắt buộc, tránh thêm tiền tố `optional:` chỉ để che lỗi. Nếu nguồn thực sự tùy chọn và ứng dụng có fallback đã kiểm chứng, có thể dùng `optional:configserver:` theo quy tắc Config Data. Hãy kiểm thử trường hợp tất cả location không sẵn sàng với đúng phiên bản Spring Boot/Spring Cloud đang triển khai.

## 4. URI được khai báo trong import có precedence cao hơn `spring.cloud.config.uri`

Khi `spring.config.import` chứa URL cụ thể, URL trong import có precedence cao hơn giá trị `spring.cloud.config.uri`.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      uri: "https://config-a.internal:8888,https://config-b.internal:8888"
  config:
    import: "configserver:https://config-special.internal:8888"
```

Trong cấu hình này, location `configserver:https://config-special.internal:8888` được dùng cho import đó. Không nên giả định danh sách `spring.cloud.config.uri` vẫn là fallback cho URL cụ thể được nhúng trong import.

Nếu muốn dùng danh sách URI trong `spring.cloud.config.uri` cùng Config Data, hãy dùng import không kèm hostname:

```yaml
spring:
  config:
    import: "configserver:"
  cloud:
    config:
      uri: "https://config-a.internal:8888,https://config-b.internal:8888"
```

Điều này giúp phân biệt rõ vị trí nguồn do import lựa chọn với danh sách endpoint do Config Client quản lý.

## 5. Không nhầm nhiều request Config Data với failover

Spring Boot Config Data có thể gọi Config Server nhiều lần trong một lần khởi động. Đầu tiên, client tải cấu hình với profile `default` để tìm các cấu hình có thể kích hoạt profile bổ sung. Sau khi xác định active profiles, client tải tiếp cấu hình cho các profile đó.

Vì vậy, log có hai hoặc nhiều request tới cùng Config Server chưa chắc là failover sang URI khác. Hãy kiểm tra URL đích, application, profile và label của từng request.

Ví dụ một ứng dụng có profile `production` có thể thực hiện:

1. Request với profile `default`.
2. Xác định profile `production` từ cấu hình đã tải.
3. Request tiếp theo với profile `production`.

Đây là quy trình bình thường của Config Data, không phải dấu hiệu client đã thử hết các replica.

## 6. Legacy bootstrap và Config Data

`spring.cloud.config.uri` được dùng trong cả mô hình bootstrap legacy và Config Data, nhưng vị trí cấu hình và cơ chế khởi tạo khác nhau.

**Bootstrap legacy:**

- Bật bằng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`.
- Thường đặt danh sách URI trong `bootstrap.yml`/`bootstrap.properties` hoặc truyền từ environment/system property.
- Config Client kết nối Config Server trong bootstrap phase để tạo remote property sources.

Ví dụ:

```yaml
# bootstrap.yml
spring:
  cloud:
    config:
      uri: "https://config-a.internal:8888,https://config-b.internal:8888"
      multiple-uri-strategy: always
```

**Config Data:**

- Là cách mặc định từ Spring Boot 2.4 trở lên.
- Dùng `spring.config.import=configserver:`.
- Không cần `bootstrap.yml`.
- Có thể dùng `spring.cloud.config.uri` làm danh sách URI khi import không chỉ rõ hostname, hoặc ghi URL cụ thể ngay trong import.

Không bật cả hai cơ chế chỉ vì muốn có nhiều URI. Chọn một cách khởi tạo theo phiên bản và cấu trúc ứng dụng, sau đó kiểm thử thứ tự nạp property sources.

## 7. Chọn giữa failover URI và nhiều import

| Nhu cầu | Cách phù hợp | Vì sao |
|---|---|---|
| Có hai replica Config Server phục vụ cùng repository, cùng dữ liệu | `spring.cloud.config.uri` với danh sách URL | Client thử endpoint kế tiếp khi endpoint trước không phục vụ được |
| Cần primary/secondary theo thứ tự | Danh sách URI | Endpoint đầu được ưu tiên; endpoint sau là phương án tiếp theo |
| Cần ghép cấu hình nền tảng và cấu hình theo domain | Nhiều `configserver:` import | Các property sources được nạp theo thứ tự, import sau có thể ghi đè import trước |
| Cần dùng một endpoint cân bằng tải | Một URI trỏ tới load balancer | Load balancer chọn replica; client không cần tự quản lý từng node |
| Config Server được đăng ký trong Eureka/Consul và dùng discovery-first | Discovery-first bootstrap | Client tìm service instance qua registry; cần cấu hình discovery đúng cách |

Danh sách URI là lựa chọn tốt khi các endpoint tương đương. Nếu endpoint B có dữ liệu khác endpoint A, việc client chuyển sang B khi A lỗi có thể khiến cùng một ứng dụng nhận bộ cấu hình khác nhau tùy thời điểm. Đó là một thay đổi hành vi, không chỉ là cải thiện availability.

## 8. Tính nhất quán giữa các Config Server replica

Failover chỉ có ý nghĩa nếu các server có thể thay thế cho nhau. Các replica nên đồng nhất về:

- Git repository hoặc backend nguồn cấu hình.
- Branch, tag hoặc commit được phục vụ.
- Application name, profile và label resolution.
- Cách ghép composite repository và thứ tự property source.
- Chính sách giải mã secret và bộ khóa cần thiết.
- Authentication, authorization và TLS trust.
- Phiên bản ứng dụng và hành vi API tương thích.

Nếu `config-a` đã fetch commit mới nhưng `config-b` vẫn đang phục vụ commit cũ, client có thể nhận cấu hình khác nhau tùy endpoint thành công đầu tiên. Config Client không so sánh checksum hoặc chọn response mới nhất giữa các server; nó dừng theo cơ chế lấy cấu hình của mình khi một request thành công.

Vì vậy, cần có cách xác định version đang được phục vụ, chẳng hạn commit SHA, label hoặc metadata phát hành. Trước khi đưa một replica vào danh sách failover, kiểm tra nó đã đồng bộ với nguồn cấu hình chuẩn.

## 9. Failover không thay thế timeout và retry

Nhiều URI không tự đặt timeout phù hợp và không nhất thiết giải quyết mọi lỗi mạng. Nếu request tới URI đầu bị treo quá lâu, client phải chờ timeout trước khi thử URI kế tiếp.

Có thể cấu hình:

```yaml
spring:
  cloud:
    config:
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

- `request-connect-timeout`: giới hạn thời gian thiết lập kết nối.
- `request-read-timeout`: giới hạn thời gian chờ response sau khi kết nối.

Retry và failover cũng là hai khái niệm riêng:

- **Failover URI:** thử endpoint khác khi endpoint hiện tại không thành công theo chiến lược.
- **Retry:** thử lại request, thường trên cùng endpoint hoặc theo cơ chế retry đã cấu hình.

Nếu bật retry với số lần thử lớn và có nhiều URI, tổng thời gian khởi động có thể tăng đáng kể. Hãy tính startup budget từ connect timeout, read timeout, số URI, số lần retry và backoff. Tránh cấu hình retry quá lớn để che giấu một Config Server hoặc Git backend thường xuyên lỗi.

## 10. Xử lý authentication và TLS với nhiều URI

Mọi endpoint trong danh sách cần có phương thức xác thực và trust phù hợp. Nếu một URI dùng certificate hoặc credential khác, phải kiểm tra khả năng cấu hình của phiên bản Spring Cloud Config đang dùng.

Với HTTP Basic, tài liệu Spring Cloud Config nêu rằng credential riêng cho từng Config Server hiện chỉ có thể hỗ trợ bằng cách nhúng username/password trong từng URL của `spring.cloud.config.uri`. Nếu dùng các cơ chế xác thực khác, hiện chưa hỗ trợ cấu hình authorization riêng theo từng Config Server theo cách tương tự.

Ví dụ cú pháp minh họa (không dùng credential thật):

```yaml
spring:
  cloud:
    config:
      uri: "https://user-a:REDACTED@config-a.internal:8888,https://user-b:REDACTED@config-b.internal:8888"
```

Không lưu password thật trực tiếp trong file YAML, Git hoặc log. URL có thể xuất hiện trong process arguments, exception hoặc telemetry. Hãy cấp credential qua secret manager và kiểm tra cơ chế authentication thực tế mà ứng dụng sử dụng.

Nếu khai báo chung `spring.cloud.config.username` và `spring.cloud.config.password`, các giá trị này ghi đè thông tin tương ứng trong URI. Điều này có thể làm mất ý nghĩa của credential khác nhau theo từng URL.

Với TLS/mTLS, truststore và client certificate phải tin cậy tất cả endpoint cần truy cập. Nếu endpoint dự phòng dùng CA hoặc client identity khác, hãy kiểm tra khả năng cấu hình per-server trước khi triển khai; không tắt xác minh certificate để làm cho failover hoạt động.

## 11. Rủi ro khi dùng nhiều import như bản sao dự phòng

Giả sử hai import trỏ tới hai replica có cùng nội dung:

```yaml
spring:
  config:
    import:
      - "configserver:https://config-a.internal:8888"
      - "configserver:https://config-b.internal:8888"
```

Nếu cả hai import đều được xử lý thành công, import sau có precedence cao hơn. Điều này có thể không gây khác biệt khi dữ liệu hoàn toàn giống nhau, nhưng vẫn tạo thêm request, thêm phụ thuộc mạng và tăng độ phức tạp.

Nếu dữ liệu khác nhau, các key trùng có thể bị import sau ghi đè. Nếu chỉ một server đã đồng bộ commit mới, ứng dụng có thể nhận một phần key từ server trước và một phần key từ server sau, tùy property source và lỗi ở từng import. Điều này có thể tạo ra một bộ cấu hình không nhất quán về mặt nghiệp vụ.

Vì vậy:

- Dùng danh sách `spring.cloud.config.uri` cho replica tương đương.
- Dùng nhiều import khi thực sự muốn ghép các nguồn cấu hình độc lập.
- Nếu nhiều import là bản sao dự phòng, kiểm tra thứ tự, fail-fast, optionality và response của từng endpoint bằng một bài test staging.
- Không coi việc startup thành công là bằng chứng hai nguồn đồng bộ.

## 12. Quan sát và kiểm thử failover

Nên ghi nhận metadata đủ để biết client đã dùng endpoint nào, profile nào và label nào, nhưng không log secret hoặc toàn bộ Environment.

Theo dõi:

- URI được thử và endpoint cuối cùng phục vụ cấu hình.
- Connect/read timeout, HTTP status và số lần failover.
- Application, profile, label và commit/version đang được phục vụ.
- Thời gian lấy cấu hình khi startup.
- Sự khác biệt giữa các Config Server replica.
- Lỗi authentication, TLS, Git backend và property source parsing.

Ma trận kiểm thử cơ bản:

| Tình huống | `uri` + `always` | `uri` + `connection-timeout-only` | Nhiều Config Data import |
|---|---|---|---|
| URI đầu timeout kết nối | Thử URI tiếp theo | Thử URI tiếp theo | Xử lý theo `fail-fast`; `false` cho phép thử URL tiếp theo |
| URI đầu trả 401 | Có thể thử URI tiếp theo | Không thử URI tiếp theo | `fail-fast=false` cho phép thử URL tiếp theo |
| URI đầu trả 500 | Có thể thử URI tiếp theo | Không thử URI tiếp theo | `fail-fast=false` cho phép thử URL tiếp theo |
| Các nguồn đều thành công | Dùng response từ URI thành công đầu tiên | Dùng response từ URI thành công đầu tiên | Import theo thứ tự; import sau có precedence cao hơn |
| Hai server trả nội dung khác nhau | Client không đối chiếu nội dung; endpoint thành công được dùng | Tương tự | Có thể ghép property source và import sau ghi đè key trùng |

Với lỗi 404, cần kiểm tra cả Config Server và backend Git vì Config Server có thể trả 404 khi backend không truy cập được repository. Hãy xác nhận hành vi thực tế trên đúng release train.

## 13. Quy trình kiểm thử staging

Một quy trình có thể xác minh cả failover và tính nhất quán:

1. Chuẩn bị hai Config Server replica cùng repository, branch/label và cấu hình bảo mật.
2. Gọi trực tiếp từng endpoint với cùng application/profile/label và xác minh metadata version giống nhau.
3. Cấu hình client dùng `spring.cloud.config.uri` với URI A đứng trước URI B.
4. Khởi động client khi A và B đều hoạt động; xác nhận A được ưu tiên.
5. Dừng A hoặc chặn kết nối tới A trong môi trường kiểm thử; xác nhận client chuyển sang B theo `multiple-uri-strategy`.
6. Thử phản hồi 401 và 500 để xác minh khác biệt giữa `always` và `connection-timeout-only`.
7. Khôi phục A và kiểm tra client lại ưu tiên URI đầu.
8. Nếu dùng nhiều Config Data import, xác minh thứ tự property source và key trùng; cố tình đặt giá trị khác nhau trong staging để quan sát precedence.
9. Kiểm tra tổng thời gian khởi động với timeout/retry thực tế.
10. Xác nhận log không chứa credential, token hoặc secret.

Không dừng Config Server production để kiểm thử failover. Sử dụng môi trường staging có dữ liệu giả và cùng cấu hình mạng/broker/TLS tương tự production.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Client chỉ gọi URI đầu | URI đầu trả thành công nên không cần failover | Đây là hành vi mong đợi; kiểm thử bằng cách làm URI đầu không sẵn sàng ở staging |
| Client không thử URI sau khi nhận 401 | Đang dùng `connection-timeout-only` | Kiểm tra credential và chọn `always` nếu chính sách thực sự cần thử tiếp khi lỗi phản hồi |
| URI trong `spring.config.import` được dùng thay cho danh sách `spring.cloud.config.uri` | URL cụ thể trong import có precedence cao hơn | Dùng `configserver:` không hostname nếu muốn dùng danh sách `uri` |
| Import sau ghi đè giá trị của import trước | Config Data xử lý theo thứ tự, import sau có precedence cao hơn | Sắp xếp import và tài liệu hóa key được phép override |
| Ứng dụng gửi nhiều request khi startup | Config Data tải `default` profile rồi active profiles; có thể có nhiều import/URI | Kiểm tra profile và URL từng request; không kết luận là retry ngay |
| Client nhận cấu hình cũ khi failover | Replica dự phòng chưa đồng bộ repository/label | Đồng bộ nguồn, kiểm tra commit/version trước khi đưa replica vào danh sách |
| Startup kéo dài khi cả hai URI lỗi | Timeout và retry tích lũy | Điều chỉnh connect/read timeout, retry budget và startup budget |
| Authentication khác nhau giữa các server không hoạt động | Cấu hình credential per-server bị giới hạn | Kiểm tra HTTP Basic URL credentials và giới hạn hỗ trợ auth của phiên bản |

## 15. Checklist thiết kế high availability

- [ ] Đã xác định các URL là replica tương đương hay các nguồn cấu hình độc lập.
- [ ] Nếu là replica, ưu tiên dùng danh sách `spring.cloud.config.uri`.
- [ ] URI được sắp xếp theo thứ tự ưu tiên và hiểu rõ đây không phải round-robin.
- [ ] Đã chọn `multiple-uri-strategy` phù hợp với loại lỗi cần failover.
- [ ] Nếu dùng nhiều Config Data import, đã kiểm tra precedence của import sau.
- [ ] Đã xác nhận URL cụ thể trong `spring.config.import` ghi đè `spring.cloud.config.uri`.
- [ ] Đã xác định `fail-fast`, optionality và retry policy.
- [ ] Các replica có cùng application/profile/label behavior, repository và commit version.
- [ ] Connect/read timeout phù hợp với startup budget.
- [ ] Authentication, credential, TLS và truststore hoạt động trên mọi endpoint.
- [ ] Đã kiểm thử timeout, 401, 500, 404 và lỗi Git backend.
- [ ] Có log/metric để xác định endpoint được sử dụng và version cấu hình.
- [ ] Không ghi credential hoặc secret vào log và file cấu hình.

## 16. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích khác biệt giữa danh sách URI trong `spring.cloud.config.uri` và nhiều `configserver:` location trong `spring.config.import`.
- Cấu hình failover URI theo thứ tự và lựa chọn `multiple-uri-strategy`.
- Phân tích khác biệt giữa `always` và `connection-timeout-only` khi gặp lỗi kết nối, 401 hoặc 500.
- Giải thích vì sao URL cụ thể trong Config Data import có precedence cao hơn `spring.cloud.config.uri`.
- Hiểu thứ tự import và tác động tới property source precedence.
- Phân biệt failover với layering, retry, load balancing và discovery-first.
- Thiết kế tính nhất quán giữa các Config Server replica.
- Kiểm thử timeout, authentication, backend failure và thứ tự cấu hình trên staging.

**Tự kiểm tra:** Một ứng dụng khai báo `spring.cloud.config.uri` gồm `config-a` và `config-b`, đồng thời có `spring.config.import=configserver:https://config-special`. Hãy xác định URL nào được dùng cho import, giải thích khi nào client thử URI dự phòng, sự khác biệt giữa `always` và `connection-timeout-only`, và vì sao khai báo thêm `configserver:` thứ hai có thể làm thay đổi giá trị cuối của một key trùng.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Specifying Multiple URLs for the Config Server](https://docs.spring.io/spring-cloud-config/reference/client.html#specifying-multiple-urls-for-the-config-server)
- [Spring Cloud Config Client — Config Data Import](https://docs.spring.io/spring-cloud-config/reference/client.html#spring-boot-config-data-import)
- [Spring Boot — Externalized Configuration and Import Ordering](https://docs.spring.io/spring-boot/reference/features/external-config.html)
