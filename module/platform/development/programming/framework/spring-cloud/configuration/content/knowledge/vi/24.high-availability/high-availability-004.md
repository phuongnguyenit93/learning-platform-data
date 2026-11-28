# Chuyển máy chủ khi timeout khác khi sai quyền hoặc sai cấu hình

Một Config Client có thể được cấu hình với nhiều địa chỉ Spring Cloud Config Server để tiếp tục khởi động khi một máy chủ không truy cập được. Tuy nhiên, không phải lỗi nào cũng nên khiến client chuyển sang máy chủ kế tiếp. Timeout khi thiết lập kết nối thường là dấu hiệu máy chủ hiện tại không sẵn sàng; HTTP 401/403 thường cho biết danh tính hoặc quyền truy cập sai; HTTP 404 thường cho biết application, profile, label hoặc tài nguyên cấu hình không tồn tại. Chuyển máy chủ trong mọi trường hợp có thể che giấu lỗi cấu hình và làm các instance nhận dữ liệu không đồng nhất.

Spring Cloud Config Client cung cấp `spring.cloud.config.multiple-uri-strategy` để lựa chọn hành vi khi có nhiều Config Server URI. `ALWAYS` cho phép thử URL tiếp theo khi request đến URL hiện tại gặp lỗi. `CONNECTION_TIMEOUT_ONLY` chỉ chuyển URL khi kết nối bị timeout. Chiến lược này giúp phân biệt lỗi không thể kết nối với lỗi nhận được phản hồi HTTP có ý nghĩa.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Cấu hình nhiều Config Server URI cho Config Client.
- Phân biệt connection timeout, read timeout, connection refused và lỗi HTTP.
- Chọn `ALWAYS` hoặc `CONNECTION_TIMEOUT_ONLY` theo chính sách failover.
- Hiểu vì sao 401/403/404 thường cần sửa cấu hình thay vì đổi máy chủ.
- Kết hợp failover với retry, timeout và fail-fast mà không kéo dài khởi động ngoài dự kiến.
- Bảo đảm các Config Server replica phục vụ cùng revision và chính sách truy cập.
- Kiểm thử failover bằng fault injection và quan sát kết quả ở client.

## 1. Vì sao cần phân loại lỗi trước khi failover?

Giả sử ứng dụng `catalog-service` được cấu hình hai Config Server:

- `config-a.internal`: máy chủ chính trong vùng triển khai.
- `config-b.internal`: máy chủ dự phòng ở vùng khác.

Nếu `config-a` không phản hồi do mạng bị gián đoạn, chuyển sang `config-b` có thể giúp ứng dụng tiếp tục lấy cấu hình. Nhưng nếu `config-a` trả về HTTP 403 vì token của client thiếu quyền, `config-b` có thể trả cùng lỗi vì hai server dùng chung policy. Chuyển máy chủ chỉ làm tăng thời gian chờ và khiến nguyên nhân thật khó nhận ra.

Tình huống khác: `config-a` trả HTTP 404 vì request dùng sai profile hoặc label. Nếu `config-b` có dữ liệu cũ hoặc cấu trúc repository khác, client có thể khởi động với cấu hình khác thay vì báo rằng request không hợp lệ.

Do đó, failover cần trả lời hai câu hỏi:

1. Lỗi cho biết máy chủ hiện tại không thể phục vụ request hay cho biết chính request/credential đang sai?
2. Máy chủ tiếp theo có cùng dữ liệu, quyền truy cập và khả năng phục vụ application/profile/label đó không?

## 2. Nhiều Config Server URI

Trong cấu hình Config Client sử dụng `spring.cloud.config.uri`, có thể khai báo danh sách URL phân tách bằng dấu phẩy:

```yaml
spring:
  application:
    name: catalog-service
  cloud:
    config:
      uri: https://config-a.internal:8888,https://config-b.internal:8888
      multiple-uri-strategy: CONNECTION_TIMEOUT_ONLY
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Client thử các URI theo cơ chế của phiên bản Spring Cloud Config đang sử dụng. `request-connect-timeout` giới hạn thời gian thiết lập kết nối; `request-read-timeout` giới hạn thời gian chờ response sau khi kết nối đã được thiết lập. Hai timeout này có ý nghĩa khác nhau khi quyết định failover.

Danh sách URI không tự đồng nghĩa với load balancing cho mọi request. Trong mô hình failover tuần tự, client sử dụng URL theo thứ tự và chuyển sang URL khác khi lỗi thỏa chiến lược đã chọn. Nếu cần phân phối tải thường xuyên giữa nhiều Config Server, hãy dùng load balancer hoặc service discovery theo kiến trúc đã triển khai.

Tên thuộc tính và cơ chế chọn nhiều URI có thể phụ thuộc phiên bản/release train. Hãy kiểm tra cấu hình của phiên bản dự án, nhất là khi chuyển từ bootstrap context cũ sang Config Data import.

### Lưu ý khi dùng Config Data import

Ví dụ `spring.cloud.config.uri` ở trên mô tả cách cấu hình danh sách URL của Config Client trong cơ chế hỗ trợ thuộc tính này. Với Config Data hiện đại, địa chỉ Config Server thường được khai báo ngay trong `spring.config.import`:

```yaml
spring:
  config:
    import: "configserver:https://config-a.internal:8888"
```

Không tự chuyển ví dụ danh sách URI thành nhiều mục `configserver:` độc lập rồi coi chúng chắc chắn là một nhóm failover. Nhiều import có thể được xử lý như nhiều nguồn Config Data và tham gia precedence, khác với một danh sách endpoint dự phòng. Cách khai báo nhiều server cho Config Data và mức hỗ trợ `multiple-uri-strategy` cần được xác nhận theo đúng release train đang dùng; hãy kiểm thử bằng cách làm endpoint đầu timeout và quan sát URI thực tế được gọi.

## 3. Hai chiến lược multiple-uri-strategy

`spring.cloud.config.multiple-uri-strategy` kiểm soát khi nào Config Client thử URI tiếp theo trong danh sách.

| Chiến lược | Hành vi | Trường hợp phù hợp |
|---|---|---|
| `ALWAYS` | Thử URI tiếp theo khi request tới URI hiện tại thất bại, bao gồm nhiều loại lỗi kết nối hoặc HTTP. | Các endpoint là bản sao tương đương, chính sách cho phép failover khi server trả lỗi và hệ thống có cách phát hiện lỗi cấu hình riêng. |
| `CONNECTION_TIMEOUT_ONLY` | Chỉ chuyển sang URI tiếp theo khi kết nối đến URI hiện tại bị timeout. | Muốn tránh che giấu lỗi HTTP như 401, 403 hoặc 404 và chỉ failover khi không thiết lập được kết nối trong thời hạn. |

Ví dụ chọn failover chỉ khi connect timeout:

```yaml
spring:
  cloud:
    config:
      multiple-uri-strategy: CONNECTION_TIMEOUT_ONLY
```

Ví dụ cho phép thử URI tiếp theo khi gặp lỗi rộng hơn:

```yaml
spring:
  cloud:
    config:
      multiple-uri-strategy: ALWAYS
```

Không nên chọn `ALWAYS` chỉ vì muốn hệ thống “tự chạy tiếp”. Khi lỗi do token, TLS trust, sai profile hoặc dữ liệu không tồn tại, fallback có thể biến lỗi rõ ràng thành một lần khởi động thành công với dữ liệu khác.

## 4. Connection timeout khác read timeout

Một request đến Config Server có hai giai đoạn mạng quan trọng:

1. Thiết lập kết nối TCP/TLS tới server.
2. Gửi request và chờ server xử lý rồi trả response.

`request-connect-timeout` giới hạn giai đoạn đầu. `request-read-timeout` giới hạn thời gian chờ dữ liệu phản hồi. Nếu kết nối đã thành công nhưng server xử lý lâu, đây là read timeout, không phải connection timeout.

```text
Config Client                    Config Server
     |                                  |
     |------ TCP/TLS connect ---------->|  connect timeout áp dụng ở đây
     |                                  |
     |------ HTTP request ------------->|
     |                                  |  xử lý request
     |<----- HTTP response -------------|  read timeout áp dụng khi chờ
```

Với `CONNECTION_TIMEOUT_ONLY`, read timeout không phải điều kiện failover theo tên chiến lược. Nếu server chấp nhận kết nối nhưng treo khi đọc Git hoặc truy vấn backend, client có thể hết read timeout mà không thử URL tiếp theo. Nếu muốn failover với read timeout hoặc các lỗi rộng hơn, cần đánh giá `ALWAYS` và tác động của việc che giấu lỗi ứng dụng.

Connection refused và DNS resolution failure cũng khác timeout. Chúng có thể thất bại ngay mà không chờ hết connect timeout. Không giả định `CONNECTION_TIMEOUT_ONLY` sẽ xử lý mọi trường hợp server không thể truy cập; kiểm thử hành vi thực tế với phiên bản HTTP client và Spring Cloud đang dùng.

## 5. Phân loại lỗi HTTP

Khi Config Server trả HTTP response, client đã kết nối và nhận được phản hồi. Mã trạng thái thường cung cấp thông tin để xác định có nên thử URL khác hay không.

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `401 Unauthorized` | Thiếu hoặc sai thông tin xác thực | Kiểm tra token, username/password, issuer, audience và credential rotation. |
| `403 Forbidden` | Danh tính đã xác thực nhưng không có quyền | Kiểm tra role, scope, ACL và policy trên Config Server/backend. |
| `404 Not Found` | Application, profile, label hoặc endpoint không tồn tại | Kiểm tra `spring.application.name`, active profiles, label và URL. |
| `400 Bad Request` | Request không hợp lệ hoặc tham số sai | Kiểm tra encoding, tên profile/label và định dạng request. |
| `429 Too Many Requests` | Server hoặc gateway giới hạn lưu lượng | Kiểm tra rate limit và backoff; không tạo thêm tải bằng retry dồn dập. |
| `5xx` | Lỗi nội bộ Config Server hoặc dependency phía server | Kiểm tra log server, Git/Vault backend, broker hoặc database liên quan. |

Trong `CONNECTION_TIMEOUT_ONLY`, các HTTP status không phải connection timeout nên không phải lý do chuyển URI. Với `ALWAYS`, client có thể thử URI tiếp theo khi request thất bại; điều đó hữu ích nếu server đầu tiên thực sự lỗi, nhưng cũng có thể che giấu 401/403/404 nếu server sau trả kết quả thành công.

Một phản hồi 404 không phải lúc nào cũng có nghĩa toàn bộ Config Server bị lỗi. Có thể chỉ một application/profile/label không tồn tại. Không nên chuyển sang server dự phòng nếu server đó có dữ liệu khác và làm request tưởng như thành công.

## 6. Ma trận quyết định failover

Ma trận dưới đây mô tả cách hai chiến lược phân biệt các lỗi phổ biến. Kết quả cuối cùng vẫn phụ thuộc loại exception mà HTTP client và phiên bản Spring Cloud phát sinh.

| Tình huống | `CONNECTION_TIMEOUT_ONLY` | `ALWAYS` | Khuyến nghị vận hành |
|---|---|---|---|
| TCP connect timeout | Thử URI tiếp theo | Thử URI tiếp theo | Failover hợp lý nếu server dự phòng tương đương. |
| Read timeout | Không chuyển chỉ vì read timeout | Có thể thử URI tiếp theo | Điều tra server/backend chậm; đặt read timeout hợp lý. |
| Connection refused | Không được đảm bảo vì không phải timeout | Có thể thử URI tiếp theo | Kiểm tra process, port, firewall và readiness. |
| DNS resolution failure | Không được đảm bảo là timeout | Có thể thử URI tiếp theo | Sửa DNS/service discovery; không coi là lỗi xác thực. |
| HTTP 401 | Không chuyển | Có thể chuyển | Sửa credential; tránh fallback che lỗi auth. |
| HTTP 403 | Không chuyển | Có thể chuyển | Sửa policy/role/ACL. |
| HTTP 404 | Không chuyển | Có thể chuyển | Sửa application/profile/label hoặc đồng bộ repository. |
| HTTP 5xx | Không chuyển chỉ vì status 5xx | Có thể chuyển | Xác minh replica sau có cùng backend/revision. |

Nếu chiến lược được chọn không cho phép failover, client sẽ xử lý lỗi theo retry/fail-fast/optional import đã cấu hình. Không nên diễn giải “không chuyển server” thành “ứng dụng luôn dừng”; chính sách khởi động là lớp điều khiển riêng.

## 7. Vì sao không nên dùng failover để chữa lỗi quyền?

Giả sử `config-a` trả 403 do token chỉ có quyền đọc `catalog-service/dev`, trong khi ứng dụng yêu cầu profile `prod`. Nếu `config-b` có policy rộng hơn và trả cấu hình thành công, `ALWAYS` có thể khiến client khởi động mà không báo lỗi quyền.

Điều này tạo ra ba rủi ro:

- **Sai lệch quyền giữa replica:** hai Config Server không áp dụng cùng policy hoặc cùng danh tính truy cập backend.
- **Sai lệch cấu hình:** server dự phòng có thể phục vụ revision hoặc profile khác.
- **Khó kiểm toán:** lỗi quyền ở server đầu tiên bị che bởi response thành công từ server sau.

Hãy đồng bộ cấu hình security, secret, truststore, policy và quyền Git/Vault giữa các replica. Nếu một replica trả 403 trong khi replica khác trả 200, đó là lỗi triển khai cần sửa, không phải trạng thái failover bình thường.

## 8. Vì sao không nên dùng failover để chữa sai application/profile/label?

Config Server nhận context từ `spring.application.name`, active profiles và label. Nếu một thành phần sai, mọi replica đúng cấu hình đều có thể trả lỗi tương tự.

Ví dụ:

```yaml
spring:
  application:
    name: catalog-service
  cloud:
    config:
      label: release-2026-11
```

Nếu Git repository chỉ có label `release-2026-10`, lỗi không tồn tại label phải được xử lý ở quy trình phát hành. Chuyển server không giúp ích nếu tất cả server cùng đọc một repository. Nếu server dự phòng có label cũ hơn và trả response, ứng dụng có thể nhận cấu hình không đúng release.

Quy trình đúng là xác minh Environment endpoint với đúng application/profile/label trước khi rollout client. Nếu label được tạo riêng cho từng replica hoặc repository chưa đồng bộ, cần sửa tính nhất quán backend.

## 9. Retry khác failover

Retry là thử lại request sau một khoảng chờ. Failover là chuyển sang một server khác. Hai cơ chế giải quyết các vấn đề khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Retry | Cho lỗi tạm thời ở cùng endpoint cơ hội tự phục hồi | Git backend hoặc Config Server vừa quá tải trong thời gian ngắn. |
| Failover | Chuyển endpoint khi server hiện tại không thể phục vụ theo chính sách | Config Server vùng A bị mất kết nối. |
| Fail-fast | Quyết định ứng dụng có dừng khởi động khi không lấy được cấu hình hay không | Production không thể chạy với cấu hình thiếu. |
| Optional import | Cho phép bỏ qua nguồn Config Data không sẵn sàng | Local development có thể chạy với cấu hình mặc định. |

Không đặt retry quá lớn cùng với nhiều URI và timeout dài. Tổng thời gian khởi động có thể tăng theo số lần thử, số URI và thời gian chờ của mỗi request.

Ví dụ cấu hình retry trong các chế độ Config Client hỗ trợ Spring Retry:

```yaml
spring:
  cloud:
    config:
      retry:
        max-attempts: 4
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
```

Các thuộc tính retry và dependency cần thiết phụ thuộc cách ứng dụng dùng legacy bootstrap hay Config Data import và phiên bản Spring Cloud. Xác nhận retry đang áp dụng cho request nào, thứ tự giữa retry và failover ra sao, thay vì giả định hai cơ chế luôn được xếp theo một thứ tự cố định.

## 10. Fail-fast và optional Config Data import

Hai lựa chọn này ảnh hưởng đến hành vi khởi động khi không lấy được cấu hình:

```yaml
spring:
  config:
    import: "configserver:https://config-a.internal:8888"
```

Import không có `optional:` biểu thị nguồn cấu hình bắt buộc trong Config Data. Nếu không thể lấy cấu hình, ứng dụng có thể không khởi động. Trong môi trường local có thể cho phép bỏ qua nguồn:

```yaml
spring:
  config:
    import: "optional:configserver:https://config-a.internal:8888"
```

Với legacy bootstrap, `spring.cloud.config.fail-fast` điều khiển việc thất bại khởi động khi không lấy được Config Server. Với Config Data import, tiền tố `optional:` là yếu tố quan trọng quyết định nguồn có bắt buộc hay không. Không sao chép một thuộc tính fail-fast từ cấu hình bootstrap cũ sang Config Data rồi cho rằng nó thay thế semantics của `optional:`.

Trong production, nếu ứng dụng cần secret, endpoint hoặc policy từ Config Server để hoạt động đúng, không nên dùng optional chỉ để bỏ qua lỗi kết nối. Ứng dụng khởi động với cấu hình mặc định thiếu có thể tạo ra lỗi khó phát hiện hoặc chạy sai môi trường.

## 11. Replica phải phục vụ cùng một cấu hình

Failover chỉ an toàn khi các Config Server có thể thay thế nhau về dữ liệu và chính sách. Kiểm tra các yếu tố:

- Cùng repository URI, backend type và quyền truy cập Git/Vault/Consul.
- Cùng application/profile/label resolution.
- Cùng phiên bản cấu hình hoặc cùng một revision bất biến.
- Cùng key material nếu cần giải mã `{cipher}`.
- Cùng authentication, authorization, TLS trust và policy.
- Cùng cách xử lý composite repository, thứ tự property source và default label.
- Cùng quy tắc refresh/fetch để không có replica phục vụ dữ liệu cũ kéo dài.

Với Git backend, mỗi Config Server có thể giữ local clone riêng. Nếu `refresh-rate` hoặc thời điểm fetch khác nhau, server A và B có thể trả revision khác nhau trong một khoảng thời gian. Dùng label/tag bất biến cho release và xác minh trường `version` trong Environment response.

Với Vault hoặc Consul, cần bảo đảm replica có cùng namespace, mount, path, ACL và version secret. Nếu dùng mã hóa, tất cả replica phải giải mã được cùng ciphertext trong giai đoạn triển khai.

## 12. Bảo vệ danh sách URI và kết nối TLS

Mỗi URI trong danh sách cần được kiểm tra độc lập:

- Hostname phải phân giải đúng và certificate phải hợp lệ cho hostname đó.
- Truststore của client phải tin CA của tất cả endpoint.
- Credential và scope phải được chấp nhận đồng nhất ở các replica.
- Firewall/network policy phải cho phép client đến từng endpoint dự phòng.
- Không đưa username/password hoặc token vào URL nếu có thể tránh; URL có thể xuất hiện trong log và process metadata.
- Không tắt hostname verification hoặc certificate validation để làm cho failover hoạt động.

Nếu các endpoint dùng certificate CA khác nhau, client cần truststore chứa đủ CA được phê duyệt. Nếu endpoint yêu cầu mTLS, certificate client và private key phải được cấp an toàn, có thể sử dụng cho từng endpoint theo chính sách PKI.

Một endpoint dự phòng không hữu ích nếu chỉ được kiểm tra khi sự cố xảy ra. Đưa health/readiness và một phép thử lấy Environment vào kiểm tra định kỳ có kiểm soát.

## 13. Load balancing và service discovery là lựa chọn khác

Danh sách nhiều URI phù hợp với failover tĩnh. Nếu Config Server được đăng ký trong service registry hoặc nằm sau một load balancer, có thể dùng discovery/load balancing để chọn instance.

| Mô hình | Cách chọn server | Khi phù hợp |
|---|---|---|
| Nhiều URI tĩnh | Client thử danh sách URI theo chiến lược failover | Môi trường ít thay đổi, endpoint dự phòng cố định. |
| Load balancer | Proxy/load balancer phân phối request đến replica healthy | Muốn phân phối tải và health-based routing ở tầng hạ tầng. |
| Service discovery | Client tìm service ID rồi load balance qua instance | Hạ tầng đã có registry và client-side load balancing. |

Không cấu hình đồng thời nhiều cơ chế định tuyến nếu chưa xác định rõ thứ tự. Ví dụ, nếu `configserver` import đi qua load balancer, danh sách URI tĩnh bên trong client có thể không cần thiết. Hãy chọn một lớp chịu trách nhiệm health check và failover để dễ quan sát.

## 14. Cách kiểm thử từng loại lỗi

Một kiểm thử failover cần chứng minh cả điều kiện chuyển server lẫn điều kiện không chuyển server.

| Bài kiểm thử | Cách mô phỏng | Kết quả mong đợi với `CONNECTION_TIMEOUT_ONLY` |
|---|---|---|
| Connect timeout | Drop packet hoặc làm endpoint không phản hồi khi bắt tay kết nối | Client thử URI tiếp theo. |
| Read timeout | Cho phép kết nối nhưng làm server trì hoãn response quá read timeout | Không chuyển chỉ vì read timeout; request thất bại theo timeout/retry policy. |
| Connection refused | Dừng listener hoặc đóng port | Không giả định sẽ failover; xác minh behavior của HTTP client. |
| 401 | Cấp token sai hoặc hết hạn | Không chuyển; lỗi xác thực được báo rõ. |
| 403 | Dùng token thiếu scope/ACL | Không chuyển; sửa policy. |
| 404 | Yêu cầu label hoặc profile không tồn tại | Không chuyển; sửa request hoặc phát hành cấu hình. |
| 5xx | Làm Config Server trả lỗi nội bộ | Không chuyển chỉ theo điều kiện connection timeout. |

Lặp lại các bài test với `ALWAYS` để xác nhận URI tiếp theo được thử khi lỗi xảy ra, đồng thời kiểm tra xem fallback có che giấu lỗi 401/403/404 hay không. Chỉ dùng môi trường test hoặc staging; không cố tình làm gián đoạn Config Server production để thử.

## 15. Quan sát và chẩn đoán

Để biết client đã failover hay chưa, cần ghi nhận metadata vừa đủ:

- URI đã thử (ẩn userinfo/query chứa credential nếu có).
- Loại lỗi: connect timeout, read timeout, connection refused, TLS, HTTP status.
- Thời gian kết nối và thời gian nhận response.
- URI nào trả kết quả thành công.
- Application, profile, label và revision `version` của Environment.
- Số lần retry và thời gian khởi động tổng cộng.

Không ghi access token, password, secret trong Environment hoặc toàn bộ property source. Log lỗi 401/403 nên có request ID và danh tính đã được che/mã hóa phù hợp để đội vận hành tra cứu audit log.

Khi chỉ một số instance gặp lỗi, so sánh danh sách URI, DNS resolution, truststore, credential, active profile và revision. Khác biệt giữa các instance thường cho thấy lỗi rollout hoặc cấu hình runtime hơn là lỗi chung của Config Server.

## 16. Ví dụ chính sách cho production

Giả sử `catalog-service` có hai Config Server replica với cùng Git repository, label phát hành và policy:

```yaml
spring:
  application:
    name: catalog-service
  cloud:
    config:
      uri: https://config-a.internal:8888,https://config-b.internal:8888
      multiple-uri-strategy: CONNECTION_TIMEOUT_ONLY
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Chính sách được chọn:

1. Nếu không thiết lập được kết nối đến `config-a` trong 2 giây, client thử `config-b`.
2. Nếu `config-a` kết nối được nhưng trả 401/403/404, client báo lỗi để đội vận hành sửa credential, policy hoặc request.
3. Nếu `config-a` kết nối được nhưng không trả dữ liệu trong 5 giây, client xử lý read timeout theo retry/fail-fast policy; không coi đây là connect timeout.
4. Cả hai server phải trả cùng `version` cho application/profile/label được yêu cầu.
5. Nếu không server nào cung cấp cấu hình bắt buộc, production instance không được khởi động với cấu hình mặc định thiếu.

Đây là ví dụ chính sách, không phải một bộ timeout tối ưu cho mọi hệ thống. Đo thời gian kết nối và thời gian Config Server đọc backend trong điều kiện tải thực tế để chọn giá trị phù hợp.

## 17. Những điểm cần ghi nhớ

- `spring.cloud.config.multiple-uri-strategy` điều khiển điều kiện thử URI tiếp theo khi có nhiều Config Server URL.
- `ALWAYS` cho phép chuyển URL khi request thất bại rộng hơn; có thể che giấu lỗi HTTP nếu replica không nhất quán.
- `CONNECTION_TIMEOUT_ONLY` chỉ failover khi kết nối timeout; read timeout, connection refused, DNS và HTTP status không được mặc định xem là cùng loại lỗi.
- 401/403 thường là lỗi xác thực/phân quyền; 404 thường là sai application/profile/label hoặc endpoint.
- `request-connect-timeout` khác `request-read-timeout`; đặt timeout hợp lý để giới hạn thời gian chờ.
- Retry, failover, fail-fast và optional import là các cơ chế riêng; cần tính tổng thời gian khởi động.
- Các Config Server replica phải đồng bộ repository revision, label, key material, TLS, authentication và policy.
- Kiểm thử cả trường hợp phải failover lẫn trường hợp tuyệt đối không được fallback.
- Log loại lỗi, URI đã thử và revision, nhưng không ghi token hoặc secret.

Failover tốt giúp Config Client tiếp tục lấy cấu hình khi một Config Server thực sự không thể kết nối. Phân loại đúng timeout và lỗi HTTP giúp hệ thống phát hiện sớm sai quyền hoặc sai context, đồng thời ngăn một replica dự phòng trả về cấu hình khác với release đã được phê duyệt.

## Tài liệu tham khảo

- [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
