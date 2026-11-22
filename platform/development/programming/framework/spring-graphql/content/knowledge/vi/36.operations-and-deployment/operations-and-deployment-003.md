# Health check cho transport

## 1. Vì sao cần health check cho transport?

Một Spring for GraphQL application có thể phục vụ request qua nhiều transport: HTTP, WebSocket, Server-Sent Events (SSE) hoặc RSocket. Mỗi transport có cách thiết lập kết nối, trao đổi message và kết thúc request khác nhau.

Một ứng dụng có thể khởi động thành công nhưng GraphQL HTTP route bị cấu hình sai. WebSocket endpoint có thể chưa được bật, handshake có thể thất bại hoặc server không gửi `connection_ack`. RSocket server có thể mở cổng TCP nhưng route GraphQL chưa được đăng ký. Vì vậy, chỉ kiểm tra tiến trình Java còn chạy chưa đủ để khẳng định client có thể sử dụng API.

Health check cần trả lời các câu hỏi khác nhau:

- Tiến trình còn sống và có thể tiếp tục chạy không?
- Instance đã sẵn sàng nhận traffic chưa?
- Transport cụ thể có thể thiết lập kết nối không?
- GraphQL engine có thể nhận, validate và thực thi một operation không?
- Những dependency thiết yếu cho operation có hoạt động không?

Không nên gộp tất cả câu hỏi này vào một probe duy nhất. Liveness, readiness và synthetic transport check phục vụ các mục đích khác nhau.

## 2. Phân biệt liveness, readiness và transport health

| Loại kiểm tra | Câu hỏi | Hành động khi thất bại |
| --- | --- | --- |
| Liveness | Instance có bị kẹt hoặc ở trạng thái không thể phục hồi tại chỗ không? | Orchestrator có thể khởi động lại instance |
| Readiness | Instance có thể nhận request mới không? | Load balancer hoặc orchestrator ngừng route traffic đến instance |
| Transport health | HTTP, WebSocket, SSE hoặc RSocket có thể nhận request theo giao thức tương ứng không? | Báo lỗi transport, cảnh báo hoặc loại endpoint khỏi traffic theo chính sách |
| GraphQL smoke test | GraphQL document có parse, validate và thực thi được không? | Cảnh báo lỗi schema, wiring hoặc runtime |
| Dependency health | Database hoặc dịch vụ thiết yếu có đáp ứng không? | Có thể đánh dấu instance chưa sẵn sàng nếu dependency thực sự bắt buộc |

Liveness nên phản ánh sức khỏe nội tại của process. Không đưa database, message broker hoặc API bên ngoài vào liveness vì sự cố của dependency dùng chung có thể khiến Kubernetes khởi động lại toàn bộ instance và tạo cascading failure.

Readiness có thể kiểm tra dependency nếu dependency đó thực sự cần để instance phục vụ traffic. Quyết định này phải dựa trên kiến trúc: dependency có thể có fallback, circuit breaker hoặc không được dùng trong mọi request hay không.

## 3. Các transport mà Spring for GraphQL hỗ trợ

Spring for GraphQL hỗ trợ GraphQL request qua HTTP, WebSocket và RSocket. Spring GraphQL 2.1 còn cung cấp SSE handler để stream response của Subscription qua HTTP.

| Transport | Kiểu kết nối | Operation phù hợp |
| --- | --- | --- |
| HTTP | Request/response, thường là POST JSON | Query và Mutation; có thể dùng GET nếu bật rõ ràng |
| WebSocket | Kết nối hai chiều tồn tại lâu | Subscription và cả Query/Mutation có một response |
| SSE | HTTP connection stream theo hướng server đến client | Subscription |
| RSocket | Session trên TCP hoặc WebSocket, hỗ trợ nhiều interaction model | Query/Mutation bằng request-response; Subscription bằng request-stream |

Các transport dùng chung GraphQL schema và execution engine, nhưng health check phải đi qua đúng transport cần kiểm tra. Actuator HTTP endpoint không chứng minh WebSocket hoặc RSocket route hoạt động.

## 4. Spring Boot Actuator cung cấp health endpoint

Thêm Actuator để có health endpoint và các probe trạng thái ứng dụng:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
```

Health endpoint mặc định được expose qua HTTP tại `/actuator/health`. Spring Boot có các health indicator cho application availability, trong đó có `livenessState` và `readinessState`.

Với ứng dụng chạy Kubernetes, Boot tự cấu hình liveness và readiness health groups. Có thể bật rõ ràng trong mọi môi trường bằng cấu hình sau:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Các endpoint probe mặc định:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Với `add-additional-paths: true`, Boot còn expose `/livez` và `/readyz` trên main application server port. Điều này hữu ích khi Actuator chạy trên management port riêng: probe đi qua cùng HTTP server mà GraphQL endpoint sử dụng, tránh trường hợp management port vẫn hoạt động nhưng main server đã lỗi.

## 5. Cấu hình Kubernetes probes

Ví dụ Deployment sử dụng các endpoint bổ sung trên main server port:

```yaml
spec:
  containers:
    - name: spring-graphql
      ports:
        - name: http
          containerPort: 8080
      startupProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        failureThreshold: 30
      livenessProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3
      readinessProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 3
```

`startupProbe` cho ứng dụng đủ thời gian khởi động. Trong thời gian startup probe chưa thành công, Kubernetes chưa dùng liveness và readiness để quyết định restart hoặc route traffic như bình thường.

Readiness failure sẽ loại instance khỏi endpoint routing; liveness failure có thể dẫn đến restart. Không dùng cùng một điều kiện phụ thuộc bên ngoài cho cả hai probe.

## 6. Readiness trong vòng đời ứng dụng

Spring Boot quản lý `ApplicationAvailability` và cập nhật trạng thái khi startup/shutdown:

| Giai đoạn | Liveness | Readiness | HTTP server |
| --- | --- | --- | --- |
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Chưa bắt đầu |
| Started | `CORRECT` | `REFUSING_TRAFFIC` | Chưa nhận traffic |
| Ready | `CORRECT` | `ACCEPTING_TRAFFIC` | Nhận request |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Từ chối request mới và xử lý request đang chạy nếu được bật |
| Shutdown complete | Không còn | Không còn | Đã đóng |

Điều này giúp orchestrator ngừng gửi request mới trước khi process kết thúc. Với WebSocket và RSocket, cần bổ sung chiến lược drain session, đóng connection có kiểm soát và để client reconnect với backoff; HTTP readiness không tự kiểm tra hoặc kết thúc các session đang tồn tại.

## 7. Readiness và health indicator của dependency

Boot không tự thêm mọi external health indicator vào readiness group. Nếu ứng dụng có dependency bắt buộc, có thể đưa indicator đó vào group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
```

Ví dụ này chỉ phù hợp khi database là dependency bắt buộc cho instance phục vụ request. Nếu API có thể tiếp tục phục vụ một phần traffic khi database tạm thời lỗi, việc đưa `db` vào readiness có thể loại bỏ toàn bộ instance dù một số operation vẫn hoạt động.

Không đưa dependency dùng chung hoặc có fallback vào liveness. Hãy cân nhắc kỹ trước khi đưa dependency dùng chung vào readiness, vì nếu tất cả instance cùng chuyển sang `REFUSING_TRAFFIC`, service có thể không còn nhận connection nào.

## 8. Actuator health không phải GraphQL transport check

`/actuator/health` cho biết trạng thái health contributor đã đăng ký. Nó không mặc định gửi GraphQL document qua `/graphql`, không thực hiện WebSocket handshake và cũng không gọi RSocket GraphQL route.

Do đó nên phân biệt hai lớp:

1. **Platform probe:** kiểm tra process và trạng thái sẵn sàng bằng `/livez`, `/readyz` hoặc health group tương ứng.
2. **Synthetic transport probe:** một client bên ngoài gửi request thực qua HTTP, WebSocket, SSE hoặc RSocket và xác nhận response đúng giao thức.

Không nên tạo một HTTP health endpoint giả rồi dùng kết quả của nó để kết luận mọi transport đều hoạt động. Mỗi transport có thể có dependency, endpoint mapping, security và network path riêng.

## 9. Thiết kế một GraphQL smoke query

Để kiểm tra GraphQL engine và resolver, có thể cung cấp một field nhẹ dành cho probe:

```graphql
type Query {
    serviceHealth: String!
}
```

```java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ServiceHealthController {

    @QueryMapping
    public String serviceHealth() {
        return "UP";
    }
}
```

Operation kiểm tra:

```graphql
query TransportHealth {
    serviceHealth
}
```

Field này chỉ kiểm tra request đã đi qua transport, GraphQL parser, schema validation, DataFetcher mapping và resolver. Nó không chứng minh database hoặc các service nghiệp vụ đang khỏe.

Nếu cần kiểm tra dependency, có thể tạo một probe riêng có timeout và chỉ thực hiện thao tác rất nhẹ. Không chạy truy vấn nghiệp vụ nặng, không trả connection string hoặc chi tiết nội bộ ra response. Bảo vệ field probe bằng network policy, authentication hoặc chỉ expose trên mạng quản trị nếu phù hợp.

Một lựa chọn khác là query `{ __typename }` để kiểm tra GraphQL engine mà không thêm field vào public schema. Tuy nhiên, query này không gọi resolver nghiệp vụ nên không phát hiện lỗi mapping của custom DataFetcher.

## 10. Health check cho HTTP transport

Spring for GraphQL xử lý GraphQL HTTP qua `GraphQlHttpHandler`. Spring Boot mặc định expose HTTP POST tại `/graphql`; path có thể được cấu hình khác theo Boot version.

HTTP transport probe nên:

1. Mở kết nối tới đúng host, port và path mà client thật sử dụng.
2. Gửi HTTP POST với `Content-Type: application/json`.
3. Gửi một GraphQL operation nhẹ như `TransportHealth`.
4. Kiểm tra HTTP status, response JSON, `errors` và giá trị trong `data`.
5. Áp dụng timeout ngắn, có giới hạn retry và không gửi quá thường xuyên.

Ví dụ dùng `curl` và `jq`:

```bash
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"query":"query TransportHealth { serviceHealth }"}' \
  http://localhost:8080/graphql \
  | jq -e '.errors == null and .data.serviceHealth == "UP"'
```

Chỉ kiểm tra HTTP status là chưa đủ. Với GraphQL over HTTP, sau khi request đã được validate thành công, lỗi phát sinh trong quá trình thực thi thường nằm trong `errors` của GraphQL response và HTTP status vẫn có thể là `200 OK`. Probe phải xác nhận cả GraphQL payload.

Nếu dùng media type `application/graphql-response+json`, một số lỗi parse/validation có thể được biểu diễn bằng HTTP 4xx theo GraphQL over HTTP specification. Vì vậy, kiểm tra payload vẫn cần thiết để phân biệt transport failure với GraphQL execution error.

## 11. Path HTTP giữa Spring Boot 3 và Spring Boot 4

Tên property cho HTTP GraphQL path đã thay đổi ở các major version:

| Phiên bản | Property | Giá trị mặc định |
| --- | --- | --- |
| Spring Boot 3.x | `spring.graphql.path` | `/graphql` |
| Spring Boot 4.x | `spring.graphql.http.path` | `/graphql` |

WebSocket vẫn dùng `spring.graphql.websocket.path`; RSocket route dùng `spring.graphql.rsocket.mapping`. Khi cấu hình probe, phải dùng đúng path thực tế sau khi áp dụng profile, reverse proxy và ingress rewrite.

Ví dụ cấu hình HTTP path:

```yaml
spring:
  graphql:
    http:
      path: /api/graphql
```

Đoạn cấu hình `http.path` dành cho Spring Boot 4.x. Với Boot 3.x, dùng `spring.graphql.path: /api/graphql`.

## 12. Health check cho WebSocket transport

WebSocket health check cần kiểm tra nhiều hơn HTTP Upgrade handshake. Spring for GraphQL dùng GraphQL over WebSocket protocol `graphql-transport-ws`.

Quy trình probe nên gồm:

1. Kết nối WebSocket tới đúng endpoint và yêu cầu subprotocol `graphql-transport-ws`.
2. Chờ handshake thành công.
3. Gửi `connection_init` với payload xác thực nếu server yêu cầu.
4. Chờ server gửi `connection_ack`.
5. Có thể gửi `ping` và chờ `pong` để kiểm tra đường truyền hai chiều.
6. Gửi một single-result GraphQL operation để xác nhận execution qua WebSocket.
7. Nhận `next` với dữ liệu mong đợi và `complete`, sau đó đóng connection sạch sẽ.

Ví dụ luồng protocol:

```text
Client -> Server: WebSocket handshake
                  Sec-WebSocket-Protocol: graphql-transport-ws

Client -> Server: {"type":"connection_init"}
Server -> Client: {"type":"connection_ack"}
Client -> Server: {"type":"ping"}
Server -> Client: {"type":"pong"}
Client -> Server: {
                    "id":"health-1",
                    "type":"subscribe",
                    "payload":{
                      "query":"query { serviceHealth }"
                    }
                  }
Server -> Client: {
                    "id":"health-1",
                    "type":"next",
                    "payload":{"data":{"serviceHealth":"UP"}}
                  }
Server -> Client: {"id":"health-1","type":"complete"}
```

`connection_ack` xác nhận server chấp nhận connection initialization; nó chưa chứng minh một resolver có thể thực thi thành công. `ping/pong` kiểm tra khả năng trao đổi message trên connection, còn single-result operation kiểm tra thêm GraphQL execution.

## 13. Bật và quản lý WebSocket endpoint

GraphQL WebSocket endpoint không được expose mặc định trong Spring Boot. Để bật:

- Ứng dụng Servlet cần dependency `spring-boot-starter-websocket`.
- Ứng dụng WebFlux không cần dependency bổ sung cho WebSocket handler.
- Cả hai cần cấu hình `spring.graphql.websocket.path`.

Ví dụ:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql-ws
      connection-init-timeout: 10s
      keep-alive: 20s
```

`connection-init-timeout` giới hạn thời gian client gửi `connection_init`. `keep-alive` cấu hình chu kỳ server gửi ping khi connection idle. Keep-alive giúp phát hiện connection bị mất, nhưng không thay thế probe thực thi GraphQL operation.

WebSocket connection tồn tại lâu và có thể chứa nhiều subscription đồng thời. Cần giới hạn số connection, kích thước message và số subscription trên mỗi session bằng cấu hình server/handler phù hợp. Không tạo một subscription probe tồn tại vô hạn cho mỗi lần Kubernetes kiểm tra.

## 14. Health check cho SSE transport

Spring for GraphQL có `GraphQlSseHandler` để trả kết quả Subscription qua Server-Sent Events. Client gửi HTTP POST với `Content-Type: application/json` và `Accept: text/event-stream`; response chứa một hoặc nhiều SSE event.

SSE chỉ phù hợp với Subscription. Query và Mutation nên dùng HTTP JSON thông thường.

Một SSE probe có thể:

1. Mở request Subscription qua đúng SSE endpoint.
2. Xác nhận HTTP response có media type `text/event-stream`.
3. Chờ event đầu tiên trong khoảng timeout đã định.
4. Xác nhận payload GraphQL hợp lệ và chứa dữ liệu mong đợi.
5. Hủy stream sau khi nhận đủ dữ liệu probe.

Không để probe giữ stream mãi. Spring for GraphQL triển khai SSE ở chế độ distinct connections; mỗi stream chiếm một connection riêng, vì vậy cần cân nhắc khả năng mở rộng và HTTP/2 khi sử dụng.

## 15. Health check cho RSocket transport

Spring for GraphQL hỗ trợ RSocket trên TCP hoặc WebSocket. `GraphQlRSocketHandler` xử lý Query/Mutation dưới dạng RSocket `request-response`, còn Subscription dưới dạng `request-stream`.

Một probe RSocket cần kiểm tra:

1. Thiết lập RSocket session đến đúng TCP/WebSocket server.
2. Gửi GraphQL request đến đúng route được cấu hình bởi `spring.graphql.rsocket.mapping`.
3. Nhận response từ interaction model phù hợp.
4. Kiểm tra GraphQL `data` và `errors`, không chỉ kiểm tra session đã mở.
5. Đóng hoặc tái sử dụng session theo chính sách của probe client.

Ví dụ Boot configuration:

```yaml
spring:
  graphql:
    rsocket:
      mapping: graphql
```

Client cần gửi request đến route `graphql`. RSocket keep-alive hoặc một connection setup thành công chỉ xác nhận session ở tầng transport; nó chưa chứng minh GraphQL route đã được đăng ký và operation chạy được.

Với subscription, probe riêng có thể gửi request-stream, chờ event đầu tiên rồi cancel subscription. Không dùng request-response để kiểm tra stream semantics.

## 16. Bảng chọn probe theo transport

| Transport | Kiểm tra kết nối | Kiểm tra GraphQL execution | Kết thúc probe |
| --- | --- | --- | --- |
| HTTP | TCP/TLS và HTTP POST đến GraphQL path | Kiểm tra `data.serviceHealth` và không có `errors` | Đóng response |
| WebSocket | Upgrade + `graphql-transport-ws` + `connection_ack` | Gửi single-result query qua `subscribe`, kiểm tra `next` | Nhận `complete`, đóng socket |
| SSE | HTTP response `text/event-stream` | Gửi Subscription và kiểm tra event đầu tiên | Cancel stream |
| RSocket | Mở session và route | Request-response query hoặc request-stream subscription | Đóng/cancel interaction |

Không nhất thiết phải probe mọi transport nếu ứng dụng không expose transport đó. Chỉ tạo probe cho endpoint client thực sự sử dụng.

## 17. Tích hợp synthetic check vào monitoring

Platform probe thường chạy từ kubelet hoặc container runtime. Synthetic transport check nên chạy từ một thành phần độc lập có network path gần giống client thật, chẳng hạn monitoring agent hoặc black-box exporter.

Một synthetic check nên ghi nhận:

- Transport và endpoint được kiểm tra.
- Thời gian thiết lập connection/handshake.
- Thời gian GraphQL operation hoàn tất.
- Kết quả `UP`, `DOWN` hoặc `DEGRADED`.
- HTTP status hoặc protocol close/error code khi thất bại.
- GraphQL error code đã được sanitize, không chứa raw query variables nhạy cảm.
- Timestamp, timeout và số lần retry.

Tách metric theo transport và outcome. Không đưa token, user ID, query document hoặc variables vào metric label vì gây cardinality cao và có thể lộ dữ liệu.

## 18. Timeout, retry và tần suất probe

Health check phải nhẹ hơn operation nghiệp vụ. Cần đặt timeout nhỏ hơn timeout của load balancer hoặc client, đồng thời tránh retry dồn dập.

Một cấu hình tham khảo:

| Thành phần | Gợi ý ban đầu |
| --- | --- |
| HTTP connect timeout | 1–2 giây |
| HTTP GraphQL response timeout | 2–3 giây |
| WebSocket handshake + ack timeout | 2–3 giây |
| WebSocket smoke operation timeout | 2–3 giây |
| RSocket connect + request timeout | 2–3 giây |
| Retry | Tối đa 1 lần có jitter cho synthetic monitor; Kubernetes probe dùng threshold riêng |
| Probe interval | Chọn theo SLO và tải; tránh gửi quá dày trên toàn bộ replica |

Đây là giá trị khởi đầu để thử nghiệm, không phải chuẩn cố định. Điều chỉnh theo latency baseline, môi trường mạng và startup behavior. Nếu probe có tần suất cao trên nhiều replica, nên dùng query rất nhẹ và tránh gọi database mỗi lần.

## 19. Bảo mật endpoint health

Health endpoint có thể tiết lộ trạng thái database, broker, schema hoặc thông tin nội bộ. Chỉ expose dữ liệu tối thiểu cần cho orchestrator.

- Dùng firewall, network policy hoặc security rule để giới hạn nguồn truy cập.
- Không trả stack trace, hostname nội bộ, JDBC URL, credentials hoặc tên bảng.
- Giữ chi tiết Actuator ở chế độ phù hợp; không bật `show-details=always` trên endpoint public.
- Nếu GraphQL smoke field được expose qua API công khai, chỉ trả trạng thái tổng quát và cân nhắc authorization.
- Nếu probe cần token, lưu token trong secret và xoay vòng định kỳ.
- Không ghi token hoặc payload xác thực WebSocket `connection_init` vào log.
- Tách health endpoint quản trị khỏi business endpoint khi cần, nhưng vẫn kiểm tra main server port bằng additional probe paths.

## 20. Kiểm thử health check trong môi trường Spring

Nên kiểm tra từng lớp độc lập:

1. Kiểm tra `/actuator/health/liveness` và `/actuator/health/readiness` khi application availability chuyển trạng thái.
2. Kiểm tra `/livez` và `/readyz` đi qua main server port nếu bật additional paths.
3. Gửi HTTP GraphQL smoke query và xác nhận `data` đúng, `errors` rỗng.
4. Với WebSocket, kiểm tra handshake, `connection_init`, `connection_ack`, ping/pong và một single-result operation.
5. Với SSE, kiểm tra response media type, event đầu tiên và cancel.
6. Với RSocket, kiểm tra session, route, request-response và request-stream nếu có Subscription.
7. Mô phỏng timeout, connection refused, unauthorized, invalid GraphQL document và resolver error.
8. Kiểm tra shutdown: readiness chuyển `REFUSING_TRAFFIC`, request mới bị từ chối và session dài hạn được drain theo chính sách.

`GraphQlTester` phù hợp để kiểm tra schema và GraphQL execution độc lập với transport. Để kiểm tra transport thật, hãy dùng HTTP/WebSocket/RSocket client tương ứng hoặc test tích hợp với server đang chạy.

## 21. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/actuator/health` UP nhưng `/graphql` lỗi | Actuator không thực thi GraphQL request | Thêm synthetic HTTP GraphQL probe |
| HTTP status 200 nhưng probe báo sai | GraphQL execution error nằm trong response `errors` | Kiểm tra payload và field kết quả |
| WebSocket handshake thành công nhưng không có ack | Sai subprotocol, auth payload hoặc connection init timeout | Kiểm tra `graphql-transport-ws`, `connection_init` và server logs |
| WebSocket ack thành công nhưng query lỗi | GraphQL engine/schema/resolver có lỗi | Gửi single-result smoke operation sau ack |
| WebSocket endpoint trả 404 | Endpoint chưa bật hoặc path không đúng | Thêm dependency phù hợp và cấu hình `spring.graphql.websocket.path` |
| SSE trả JSON thay vì event stream | Thiếu `Accept: text/event-stream` hoặc endpoint không bật SSE | Kiểm tra request header và handler mapping |
| RSocket session mở nhưng GraphQL request lỗi | Sai route hoặc GraphQL handler chưa được map | Kiểm tra `spring.graphql.rsocket.mapping` và route client |
| Probe luôn DOWN khi management port riêng | Probe chỉ kiểm tra management server, main server bị lỗi | Bật `probes.add-additional-paths` và probe main port |
| Tất cả replica bị restart khi DB lỗi | Liveness phụ thuộc DB hoặc dependency dùng chung | Chuyển kiểm tra dependency sang readiness hoặc monitor riêng |
| Readiness DOWN dù một số API còn chạy | Readiness group chứa dependency không thiết yếu | Rà soát indicator và fallback/circuit breaker |
| Probe làm tăng tải database | Query probe thực hiện nghiệp vụ nặng hoặc chạy quá thường xuyên | Dùng resolver nhẹ, giảm tần suất và giới hạn timeout |

## 22. Checklist triển khai

- [ ] Thêm Spring Boot Actuator và expose health endpoint cần thiết.
- [ ] Bật liveness/readiness probes trong môi trường triển khai.
- [ ] Dùng liveness cho trạng thái nội tại, không phụ thuộc hệ thống bên ngoài.
- [ ] Chỉ thêm dependency thiết yếu vào readiness.
- [ ] Dùng additional paths để probe đi qua main server port khi cần.
- [ ] Xác nhận GraphQL HTTP path theo Spring Boot version.
- [ ] Tạo GraphQL smoke operation nhẹ và kiểm tra cả `data` lẫn `errors`.
- [ ] Với WebSocket, kiểm tra handshake, `connection_ack` và operation thực tế.
- [ ] Với SSE, kiểm tra event đầu tiên và cancel stream.
- [ ] Với RSocket, kiểm tra session, route và interaction model phù hợp.
- [ ] Đặt timeout, retry và interval theo SLO.
- [ ] Giới hạn quyền truy cập và dữ liệu trả về từ health endpoint.
- [ ] Kiểm thử failure mode, startup và graceful shutdown.
- [ ] Theo dõi latency và failure rate riêng cho từng transport.

## Kết luận

Health check cho Spring for GraphQL cần phân biệt trạng thái của process, khả năng nhận traffic và tình trạng của từng transport. Spring Boot Actuator cung cấp liveness/readiness health groups; Spring for GraphQL cung cấp handler cho HTTP, WebSocket, SSE và RSocket. Actuator health endpoint không tự thực hiện GraphQL operation và cũng không xác nhận các transport kết nối lâu dài đang hoạt động.

Một thiết kế vận hành tốt dùng liveness để phát hiện process không thể phục hồi tại chỗ, readiness để quyết định instance có nhận request mới hay không, và synthetic transport probe để kiểm tra đúng đường kết nối mà client sử dụng. HTTP probe cần kiểm tra cả GraphQL payload; WebSocket cần xác nhận protocol initialization và operation; SSE cần nhận event; RSocket cần kiểm tra session, route và interaction model. Giữ probe nhẹ, có timeout, giới hạn truy cập và không phụ thuộc external system trong liveness để tránh tạo cascading failure.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Actuator Endpoints and Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — GraphQL Web Endpoints](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [GraphQL over WebSocket Protocol — `graphql-transport-ws`](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
