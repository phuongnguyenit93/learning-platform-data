# Nguồn truy cập trong Audit Logging Java

## 1. “Nguồn truy cập” là gì và vì sao phải ghi lại?

**Audit logging** ghi nhận những hành động cần có khả năng truy vết: ai đã truy cập tài nguyên nào, làm gì, khi nào, kết quả ra sao và dựa trên ngữ cảnh/bằng chứng nào. Trong đó, **nguồn truy cập (access origin/source)** giúp trả lời: *yêu cầu hoặc thao tác này được đưa vào hệ thống từ đâu, qua kênh nào, và bằng chứng về nguồn đó đáng tin tới mức nào?*

Ví dụ khi tài liệu nội bộ bị mở trái phép, chỉ có dòng `DOCUMENT_READ result=ALLOW` là không đủ. Người điều tra còn cần biết actor đã được xác thực, loại client, request ID, địa chỉ mạng mà server quan sát, proxy/gateway nào chuyển yêu cầu, và nguồn thông tin nào được tin cậy để xác định client.

Tuy nhiên, **nguồn truy cập không đồng nghĩa với danh tính người dùng**. Địa chỉ IP có thể thuộc NAT, VPN, reverse proxy hoặc mạng dùng chung. Một HTTP header như `X-Forwarded-For` có thể bị client giả mạo nếu hạ tầng không kiểm soát ranh giới tin cậy. Audit log phải diễn đạt rõ **điều hệ thống quan sát được** và **điều hệ thống suy ra từ bằng chứng đã kiểm chứng**, không biến một chuỗi client tự khai thành “sự thật”.

Sau bài học, bạn có thể:
- Phân biệt **actor/principal**, **nguồn kết nối**, **nguồn client suy ra**, **ứng dụng gọi**, **kênh truy cập** và **tài nguyên đích**.
- Thiết kế schema cho sự kiện truy cập có đủ thông tin điều tra nhưng không ghi token, cookie hoặc dữ liệu không cần thiết.
- Hiểu cách reverse proxy/load balancer/API gateway ảnh hưởng đến `remoteAddr`, `Forwarded` và `X-Forwarded-For`.
- Viết ví dụ Java 17 chạy độc lập với JUL để ghi audit event và phân biệt socket peer với forwarded client đã được xác minh.
- Kiểm thử tình huống giả mạo header, nhiều proxy, yêu cầu không xác thực, API service-to-service và lỗi hệ thống.

## 2. Mô hình tư duy: ai, từ đâu, qua đâu, làm gì?

Một sự kiện audit về truy cập nên tách rõ các chiều:

| Trường | Câu hỏi được trả lời | Ví dụ mang tính minh họa |
| --- | --- | --- |
| `actor_id` | Principal nào thực hiện hành động? | `principal-17` |
| `actor_type` | Loại actor? | `USER`, `SERVICE`, `JOB` |
| `action` | Đã yêu cầu làm gì? | `DOCUMENT_READ`, `ROLE_UPDATE` |
| `resource_type` / `resource_id` | Tài nguyên nào là đối tượng bị truy cập? | `DOCUMENT` / `doc:42` |
| `result` | Hành động được cho phép, từ chối hay lỗi? | `ALLOW`, `DENY`, `ERROR` |
| `occurred_at` | Hành động xảy ra lúc nào? | Timestamp UTC do hệ thống ghi |
| `request_id` / `trace_id` | Sự kiện thuộc request/luồng nào? | `req-101` |
| `source_socket_peer` | Server nhìn thấy peer mạng nào trên kết nối vào? | `192.0.2.7` |
| `source_client_ip` | Địa chỉ client được lấy từ nguồn đã được chấp nhận? | `203.0.113.50` |
| `source_evidence` | Bằng chứng/đường xác định client IP? | `SOCKET_PEER`, `TRUSTED_PROXY` |
| `source_channel` | Kênh truy cập nào đã được xác định? | `WEB`, `API`, `INTERNAL_JOB` |
| `client_app_id` | Ứng dụng/client nào đã được xác thực? | `billing-service` |
| `service` / `instance_id` | Service/instance nào ghi audit event? | `document-api` / `node-a` |

Các địa chỉ thuộc dải ví dụ `192.0.2.0/24` và `203.0.113.0/24` chỉ được dùng để minh họa, không phải thông tin về người dùng thật.

Phân biệt vài trường dễ nhầm:

- **Actor** là danh tính được hệ thống xác thực hoặc phân loại (`principal-17`, `service-billing`). Nó không nhất thiết là người thật; job nền cũng là actor.
- **Source** chỉ nguồn hoặc tuyến truy cập: địa chỉ kết nối, client IP có bằng chứng, ứng dụng gọi, gateway và kênh.
- **Resource/target** là thứ được truy cập (`doc:42`). Đừng dùng từ `source` để chỉ tài nguyên đích hoặc file Java phát ra log.
- **Observer** là service ghi audit event. Khi nhiều microservice nhận cùng một request, mỗi service có thể thấy nguồn mạng khác nhau; cần biết **tại điểm nào** một giá trị được quan sát.
- **Correlation ID** giúp ghép log nhưng **không phải chứng cứ xác thực danh tính**: request ID do client tự gửi có thể bị thay đổi, trùng hoặc giả mạo.

Tách các trường này giúp điều tra một chuỗi như “người dùng U qua mobile app gọi gateway G, gateway chuyển tới document service S, yêu cầu đọc document D bị từ chối”.

## 3. Các cấp độ tin cậy của nguồn truy cập

Không phải thông tin nào có trong HTTP request cũng đáng tin như nhau. Một số ví dụ:

| Thông tin | Nguồn thu thập | Có thể kết luận gì? |
| --- | --- | --- |
| Socket peer | Tầng kết nối mà service/servlet container quan sát | Địa chỉ peer của **kết nối đang tới service** tại điểm quan sát; có thể là proxy |
| `Forwarded` / `X-Forwarded-For` | Header HTTP | Là dữ liệu **do bên gửi HTTP cung cấp**; chỉ đáng tin sau xử lý tại ranh giới proxy được cấu hình |
| Actor ID | Security context sau xác thực | Principal được hệ thống xác thực theo phương thức đã cấu hình; độ tin cậy phụ thuộc authn/authz |
| Client app ID | Được xác thực qua mTLS, OAuth client identity hoặc cơ chế khác | Định danh ứng dụng gọi theo cơ chế chứng thực; không lấy từ header tùy ý |
| User-Agent | Client tự gửi header | Chỉ là thông tin tự khai, dễ thay đổi, không phải chứng cứ thiết bị duy nhất |
| Host/Referer/Origin header | Client hoặc browser gửi | Có ích cho xử lý giao thức khi được kiểm tra phù hợp, nhưng không phải chứng cứ chắc chắn về nguồn vật lý |
| Trace ID | Tracing middleware hoặc client gửi | Mã tương quan phục vụ điều tra, có thể cần kiểm tra/chuẩn hóa trước khi dùng |
| Thông tin ingress/load balancer | Hạ tầng được kiểm soát | Có thể là bằng chứng mạnh hơn nếu được chuyển qua kênh đã xác thực và không cho client ghi đè |

Một schema tốt có thể có `source_evidence` hoặc `source_resolution` để nói rõ **quy tắc xác định** giá trị nguồn. Ví dụ `SOCKET_PEER` nghĩa là chỉ tin peer của kết nối; `TRUSTED_PROXY` nghĩa là đã dùng chuỗi proxy mà hạ tầng cho phép; `INTERNAL_JOB` nghĩa là hoạt động không có HTTP client IP theo nghĩa thông thường.

**Đừng đặt trường `real_ip` rồi coi nó luôn là IP thật của người dùng.** Ngay cả địa chỉ client được xác định đúng qua proxy vẫn có thể là IP NAT/VPN/corporate egress. Tên trường trung tính như `client_ip` cùng `source_evidence` thường chính xác hơn.

## 4. Proxy và vấn đề giả mạo nguồn

### 4.1. Vì sao `getRemoteAddr()` có thể không phải địa chỉ client?

Một luồng triển khai thường gặp:

```text
Browser / mobile client
        |
        v
Internet / NAT / VPN
        |
        v
CDN / Load balancer / Reverse proxy
        |
        v
API Gateway
        |
        v
Java service
```

Đối với Java service, địa chỉ peer của kết nối TCP cuối thường là **gateway hoặc reverse proxy**, không phải IP nơi browser phát yêu cầu. Servlet API có `HttpServletRequest.getRemoteAddr()` nhưng ý nghĩa cụ thể còn chịu ảnh hưởng của container và cơ chế xử lý forwarded headers đã cấu hình. Nếu có một filter/valve tin cậy đã viết lại request, giá trị này có thể là client IP đã được xử lý, không còn là raw socket peer.

Vì thế, thiết kế audit cần ghi rõ **giá trị nào được lấy từ đâu**:
- Raw peer do tầng socket/ingress quan sát (nếu có thể truy xuất an toàn).
- Client address đã được **trusted proxy resolver** xử lý.
- Identity người/ứng dụng từ security context.
- Gateway/instance ghi sự kiện.

Không gán ý nghĩa cho `getRemoteAddr()` chỉ dựa trên tên phương thức; cần xác minh cấu hình framework và môi trường chạy.

### 4.2. `X-Forwarded-For` có thể bị giả mạo

Một request do client tự tạo có thể gửi:

```http
GET /documents/42 HTTP/1.1
Host: example.test
X-Forwarded-For: 203.0.113.50
```

`203.0.113.50` chỉ là **giá trị do client khai**, không có bằng chứng nào ở request trên xác nhận đây là nguồn thật. Nếu ứng dụng ghi `clientIp=request.getHeader("X-Forwarded-For")` và gán nó là nguồn đáng tin, kẻ tấn công có thể giả mạo địa chỉ.

Khi có nhiều proxy, header còn có thể là một chuỗi địa chỉ. **Không mặc định lấy phần tử đầu tiên hoặc cuối cùng**; quy tắc phải xuất phát từ topology và trusted proxy policy. Nếu ingress có thể bị gọi trực tiếp từ Internet, hoặc proxy chỉ *append* vào header chưa được chuẩn hóa, một chuỗi do client tự khai vẫn có thể nằm trong danh sách.

Hệ thống cần:
1. Xác định chính xác proxy/load balancer nào được tin, dựa trên đường kết nối/hạ tầng được quản lý; không tin một cờ do client gửi.
2. Ngăn truy cập trực tiếp bỏ qua proxy nếu kiến trúc yêu cầu một ingress duy nhất.
3. Ở ranh giới, **loại bỏ hoặc chuẩn hóa** các header forwarding do client không đáng tin gửi, theo cấu hình proxy được kiểm soát.
4. Dùng cơ chế resolver/framework phù hợp với topology, dải proxy đáng tin, số hop và cú pháp header.
5. Ghi lại nguồn chứng cứ: `SOCKET_PEER` hay `TRUSTED_PROXY`, và có thể tên gateway/ingress đã xác minh.
6. Kiểm thử trực tiếp lẫn qua proxy với header giả mạo để chắc rằng thay header từ client không sửa được giá trị audit đáng tin.

Header chuẩn `Forwarded` và header phổ biến `X-Forwarded-For` không phải cơ chế xác thực. Chúng chỉ có thể giúp nhận diện nguồn khi việc **tạo và truyền** header được kiểm soát bởi ranh giới tin cậy.

### 4.3. Không nhầm `source_ip` với actor

Hai người dùng ở cùng mạng văn phòng có thể dùng chung public IP. Một người có thể đổi IP do mạng di động/VPN. Nhiều request có thể đi qua cùng API gateway; cũng có thể một service dùng nhiều outbound IP.

Đối chiếu audit nên kết hợp `actor_id`, `auth_method`/client identity, `request_id`, time, result, resource và IP theo chính sách. IP là **tín hiệu điều tra**, không phải chứng minh một người cụ thể đã thao tác.

## 5. Thiết kế một audit event về nguồn truy cập

Ví dụ JSON chỉ chứa các trường được phép và có mục đích:

```json
{
  "event_id": "evt-001",
  "occurred_at": "2026-11-10T03:00:00Z",
  "service": "document-api",
  "actor_type": "USER",
  "actor_id": "principal-17",
  "action": "DOCUMENT_READ",
  "resource_type": "DOCUMENT",
  "resource_id": "doc:42",
  "result": "DENY",
  "request_id": "req-002",
  "source": {
    "socket_peer": "192.0.2.7",
    "client_ip": "203.0.113.50",
    "evidence": "TRUSTED_PROXY",
    "channel": "API",
    "client_app_id": "portal-web"
  }
}
```

Đây là **schema minh họa**, không phải log thu thập từ hệ thống thật. Timestamp/ID/IP là dữ liệu ví dụ.

Một vài quyết định thiết kế quan trọng:

- `event_id`: mã duy nhất cho **sự kiện audit**, hữu ích khi chuyển tiếp/retry và phát hiện duplicate; không nên thay nó bằng `request_id` vì một request có thể gây nhiều event.
- `request_id`/`trace_id`: dùng để tìm các log kỹ thuật liên quan; có thể cần kiểm tra ký tự và độ dài.
- `actor_id`: lấy từ principal đã được xác thực, không phải từ request field do client khai. Với request chưa xác thực, dùng `ANONYMOUS` hoặc giá trị null/chuỗi đại diện theo schema, **không tự dựng một actor đáng tin từ IP**.
- `source.socket_peer`: địa chỉ quan sát tại điểm kết nối đã xác định; nếu chỉ có địa chỉ sau proxy rewriting thì ghi rõ nguồn và không giả vờ đó là raw peer.
- `source.client_ip`: giá trị đã qua trusted resolver nếu có. Khi không xác định được, nên ghi null hoặc địa chỉ peer với `evidence=SOCKET_PEER`; tránh đặt một IP “ước lượng” không có bằng chứng.
- `result`: cần nhất quán giữa `ALLOW`, `DENY`, `ERROR` hoặc trạng thái nghiệp vụ; phân biệt **quyết định cấp quyền** với **thao tác thực thi đã thành công**.
- `resource_id`: chỉ đưa định danh được phép ghi. Với tài nguyên cực kỳ nhạy cảm, có thể cần tokenization hoặc lưu ID nội bộ thay cho tên/đường dẫn chứa PII.
- `client_app_id`: dùng định danh client đã chứng thực nếu có. Không dùng trực tiếp một trường `X-Client-Name` tự khai rồi gọi nó là client identity.

Một event tốt phải giúp trả lời **cái gì đã quan sát, cái gì đã xác thực, cái gì chỉ là claim**. Nếu hai giá trị có mức tin cậy khác nhau, cần tách thành hai trường hoặc bỏ trường ít đáng tin thay vì trộn thành một chuỗi chung.

## 6. Ví dụ Java 17 chạy độc lập: phân biệt nguồn kết nối và nguồn đã xác minh

Chương trình sau dùng **JUL** (`java.util.logging`) có sẵn trong JDK 17, không cần Maven, Gradle hay thư viện ngoài. Nó mô phỏng hai đường truy cập:
- Request thứ nhất có `X-Forwarded-For` tự khai nhưng **không đi qua proxy tin cậy**: chỉ ghi socket peer vào `clientIp`.
- Request thứ hai đi qua proxy do hạ tầng đã xác định tin cậy và cung cấp `validatedForwardedClient`: ghi cả peer và client IP đã được xác minh.

Cờ `socketPeerIsTrustedProxy` và giá trị `validatedForwardedClient` trong ví dụ là **giả lập đầu ra của hạ tầng/resolver tin cậy**, không lấy trực tiếp từ header do client gửi. Trong production, tuyệt đối không cung cấp cờ này bằng query/body/header chưa được xác minh.

Tạo tệp `AuditAccessSourceDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AuditAccessSourceDemo {
    private record Origin(
            String socketPeer, String clientIp, String evidence) {}

    private record AuditEvent(
            String eventId, String actor, String action,
            String resource, String result, Origin origin) {}

    private static Origin resolveOrigin(
            String socketPeer,
            boolean socketPeerIsTrustedProxy,
            String validatedForwardedClient) {

        if (socketPeerIsTrustedProxy
                && validatedForwardedClient != null
                && !validatedForwardedClient.isBlank()) {
            return new Origin(
                    socketPeer, validatedForwardedClient, "TRUSTED_PROXY");
        }
        return new Origin(socketPeer, socketPeer, "SOCKET_PEER");
    }

    private static String safe(String value) {
        return value.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("|", "\\|");
    }

    private static void writeAudit(Logger logger, AuditEvent event) {
        Origin source = event.origin();
        logger.info("AUDIT eventId=" + safe(event.eventId())
                + " actor=" + safe(event.actor())
                + " action=" + safe(event.action())
                + " resource=" + safe(event.resource())
                + " result=" + safe(event.result())
                + " socketPeer=" + safe(source.socketPeer())
                + " clientIp=" + safe(source.clientIp())
                + " evidence=" + safe(source.evidence()));
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("audit.access.source.demo");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        logger.addHandler(output);

        try {
            Origin untrusted = resolveOrigin(
                    "192.0.2.7", false, "203.0.113.50");
            Origin trusted = resolveOrigin(
                    "192.0.2.7", true, "203.0.113.50");

            writeAudit(logger, new AuditEvent(
                    "evt-01", "principal-17", "DOCUMENT_READ",
                    "doc:42", "ALLOW", untrusted));

            writeAudit(logger, new AuditEvent(
                    "evt-02", "principal-17", "DOCUMENT_READ",
                    "doc:42", "DENY", trusted));
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac AuditAccessSourceDemo.java
java AuditAccessSourceDemo
```

**Stdout chính xác** khi chạy trong JVM mới, không có cấu hình ngoài can thiệp vào logger của ví dụ:

```text
AUDIT eventId=evt-01 actor=principal-17 action=DOCUMENT_READ resource=doc:42 result=ALLOW socketPeer=192.0.2.7 clientIp=192.0.2.7 evidence=SOCKET_PEER
AUDIT eventId=evt-02 actor=principal-17 action=DOCUMENT_READ resource=doc:42 result=DENY socketPeer=192.0.2.7 clientIp=203.0.113.50 evidence=TRUSTED_PROXY
```

### Giải thích vì sao ví dụ hữu ích

1. Cả hai lần gọi nhận **cùng một chuỗi được đưa vào tham số `validatedForwardedClient`**, nhưng chỉ lần thứ hai được phép dùng nó vì cờ `socketPeerIsTrustedProxy=true` giả lập bằng chứng từ ranh giới hạ tầng đã tin cậy. Lần thứ nhất không nâng claim client thành nguồn đáng tin.
2. `socketPeer` luôn được giữ riêng, giúp biết địa chỉ kết nối trực tiếp đến service trong mô hình ví dụ.
3. `safe` escape các ký tự xuống dòng, tab, dấu gạch chéo ngược và dấu phân tách `|` trong giá trị log, giảm nguy cơ **log injection** với định dạng text. Đây **không phải** bộ lọc bí mật, không phải bộ validate IP hoàn chỉnh và không thay thế JSON encoder chuẩn.
4. `actor` là một principal đã xác thực **giả lập**; ví dụ không tự gán danh tính từ địa chỉ IP.
5. Demo cố tình không dùng timestamp động để stdout dễ đối chiếu. Audit production phải có thời điểm sự kiện đủ chính xác, service/instance ID, chiến lược durability, retention và quyền truy cập phù hợp.
6. `Handler` tự viết chỉ để minh họa. Nó không bảo đảm đồng thời, ghi xuống đĩa bền vững, chống sửa log hay retry sau crash. Đừng thay thế audit store production bằng handler in stdout đơn giản như trên.

**Giới hạn rất quan trọng:** Hàm `resolveOrigin` không có logic tự xác định proxy đáng tin, phân tích IPv4/IPv6, xử lý chuỗi proxy hoặc xác minh forwarded header; nó **đòi đầu vào đã được hạ tầng xác minh**. Trong sản phẩm thật, phải thực hiện trust resolution trước khi gọi hàm tương tự, hoặc dùng một integration được cấu hình chuẩn theo container/gateway của bạn.

## 7. Tích hợp trong Java web application

### 7.1. Servlet request và thông tin mạng

Trong ứng dụng Jakarta Servlet (ví dụ Spring Boot hiện đại dùng stack Servlet), có thể quan sát những giá trị sau:

```java
// Mảnh code tích hợp, yêu cầu jakarta.servlet.http.HttpServletRequest.
String observedRemote = request.getRemoteAddr();
String claimedForwarded = request.getHeader("X-Forwarded-For");
```

**Đừng lập tức ghi `claimedForwarded` thành `client_ip`.** Nó là claim từ request trừ khi bạn đã thiết lập và xác nhận tuyến xử lý proxy tin cậy. `observedRemote` cũng cần được hiểu trong ngữ cảnh container và forwarded header filter/valve hiện tại; nó có thể đã được chuyển đổi bởi middleware.

Cách triển khai đáng tin thường là:

1. Ở ingress/gateway, chỉ cho phép đường request mong muốn và định danh proxy tin cậy.
2. Chuẩn hóa forwarded metadata theo topology, loại giá trị do client không đáng tin có thể tiêm vào.
3. Ở service, sử dụng **một resolver đã được cấu hình** để trả về `ClientOrigin` (client IP, socket peer nếu có, evidence, gateway).
4. Gắn nguồn này vào **request-scoped context** nội bộ, chỉ truyền các field an toàn.
5. Khi quyết định truy cập xảy ra, tạo audit event từ security principal, action/resource, result và context đã xác minh; không đọc rải rác các header ở từng controller.

Trên Spring Boot/Tomcat/Jetty/Undertow, một số thành phần có thể hỗ trợ xử lý forwarded headers hoặc trusted proxies, nhưng cách đặt option và semantics khác nhau theo stack và phiên bản. Hãy cấu hình phù hợp với hạ tầng thực, không sao chép một property vào mọi hệ thống rồi cho rằng IP đã được chứng thực.

### 7.2. Actor phải đến từ security context

Ví dụ conceptual flow:

```text
Authentication / mTLS / token verification
                |
                v
  Verified principal or service identity
                |
                v
Authorization checks for resource/action
                |
                +--> ALLOW / DENY / ERROR
                |
                v
  Audit event + verified source metadata
```

`actor_id` nên lấy từ kết quả **xác thực đã hoàn tất**, không lấy từ `?userId=`, `X-User-Id` hoặc body. Nếu upstream gateway truyền thông tin principal, service phải xác nhận kênh tin cậy và cơ chế xác thực giữa gateway và service. Cũng không nên mặc định rằng JWT claim `sub` có nghĩa đúng đắn nếu token chưa được kiểm tra chữ ký, issuer, audience và thời hạn theo chính sách.

Một request **không xác thực** cũng có thể cần audit event, nhất là khi bị chặn ở login/gateway. Khi đó `actor_type=ANONYMOUS`, `actor_id=null` và result `DENY` cùng source evidence phù hợp thường trung thực hơn việc lấy IP làm “actor”.

### 7.3. Kênh truy cập và ứng dụng gọi

Không phải mọi truy cập đều là HTTP request từ browser:

| Kịch bản | Nguồn hữu ích để audit | Điều không nên suy đoán |
| --- | --- | --- |
| Browser qua gateway | Principal xác thực, trusted client IP, gateway, session reference an toàn | IP là người dùng duy nhất |
| Mobile API | Client identity nếu đã chứng thực, request ID, IP được xử lý tin cậy | `User-Agent` chứng minh app thật |
| Service-to-service | Service principal từ mTLS/OAuth hoặc workload identity, network peer/gateway | Tự khai `X-Service-Name` là identity |
| Scheduled job | Job ID, scheduler, service account, execution ID | Gán một “client IP người dùng” không tồn tại |
| Message consumer | Producer identity nếu xác minh được, topic/queue, message ID, trace context | Message header bất kỳ là actor được xác thực |
| Admin console | Admin principal, loại action, nguồn đã tin cậy, kết quả | Chỉ IP nội bộ đủ chứng minh quyền quản trị |
| Database integration | Principal ứng dụng và tên thao tác, nơi quan sát | JDBC connection string là danh tính người dùng cuối |

Dùng `source_channel` như `WEB`, `API`, `SERVICE`, `BATCH`, `MESSAGE` theo danh sách quản lý. Nếu kênh chỉ suy ra từ header/client tự khai, có thể thêm trường phân loại `UNVERIFIED` hoặc không ghi để tránh tạo bằng chứng giả.

## 8. Thiết kế audit event với SLF4J và structured logging

SLF4J là facade; việc lưu dữ liệu và xuất JSON phụ thuộc Logback, Log4j 2 hoặc backend thực tế. Đoạn dưới là **mã tích hợp** dùng fluent API của SLF4J 2.x, không phải chương trình Java thuần có thể chạy ngay không có dependency:

```java
// Các biến đã được tạo từ security context và origin resolver tin cậy.
// logger là một SLF4J 2.x logger được cấu hình trong ứng dụng.
auditLogger.atInfo()
    .addKeyValue("event_id", eventId)
    .addKeyValue("actor_id", principalId)
    .addKeyValue("action", "DOCUMENT_READ")
    .addKeyValue("resource_id", safeResourceId)
    .addKeyValue("result", "DENY")
    .addKeyValue("source_client_ip", verifiedOrigin.clientIp())
    .addKeyValue("source_evidence", verifiedOrigin.evidence())
    .addKeyValue("request_id", requestId)
    .log("Access decision recorded");
```

Lưu ý:
- `principalId` phải lấy từ security context **sau xác thực**, không từ query/header chưa chứng thực.
- `verifiedOrigin` đại diện cho object do resolver đáng tin cung cấp, **không phải một class có sẵn của SLF4J**; bạn phải định nghĩa nó trong ứng dụng.
- Backend/encoder phải hỗ trợ đưa key-value pairs vào structured output. Không phải pattern text nào cũng tự xuất toàn bộ field.
- Không thêm `authorization_header`, raw JWT, password, Cookie, API key, session token hoặc request body.
- Nếu `safeResourceId` là dữ liệu cá nhân, cần áp chính sách tối thiểu hóa hoặc pseudonymization tương ứng.
- Logging ở level INFO qua pipeline ứng dụng có thể bị filter/drop hoặc ghi lỗi; với audit bắt buộc, cần cơ chế lưu trữ và kiểm soát tính toàn vẹn có cam kết phù hợp thay vì mặc định dựa vào log thông thường.

### 8.1. Audit không chỉ là debug logging

Một câu lệnh `logger.info("user {} accessed ...")` không tự tạo một hệ thống audit đáng tin. Audit cần những thuộc tính bổ sung như:
- Schema/version, event identity và phân loại actor/action/result thống nhất.
- Dòng ghi có thể truy xuất và chống sửa/xóa trái phép theo policy.
- Quy trình đồng bộ đồng hồ/timestamp và đánh dấu thời điểm event được ghi.
- Chính sách bảo vệ/retention/backup, khả năng phát hiện thiếu và duplicate.
- Kiểm soát ai được đọc, xuất và xóa log, bao gồm log của chính hành động quản trị log.

Tùy yêu cầu, có thể cần **append-only audit store**, event outbox gắn transaction hoặc cơ chế lưu bền vững riêng. Audit logging trong pipeline thông thường có thể dùng cho điều tra best-effort nhưng **không tự bảo đảm exactly-once, tính bất biến hoặc độ bền sau crash**.

### 8.2. Ghi nguồn ở đúng thời điểm

Nếu ghi audit lúc **ra quyết định cấp quyền**, `result=ALLOW` thường có nghĩa là “được phép thực hiện”, **chưa chắc** dữ liệu đã được trả thành công. Nếu ghi lúc **truy cập hoàn tất**, có thể bổ sung outcome kỹ thuật, bytes, error code hoặc thông tin thực thi. Cần định nghĩa rõ loại event để không lẫn:
- `AUTHZ_DENIED`: bị từ chối bởi kiểm tra quyền.
- `ACCESS_ATTEMPTED`: đã bắt đầu yêu cầu.
- `ACCESS_COMPLETED`: thao tác hoàn tất.
- `ACCESS_FAILED`: lỗi kỹ thuật/nghiệp vụ xảy ra.

Không ghi cùng một event dưới nhiều tên mà không có event ID/correlation, vì người điều tra có thể đếm nhầm số lần truy cập.

## 9. Những bẫy về dữ liệu nguồn

### 9.1. Log injection và đầu vào không tin cậy

Client có thể gửi header với chuỗi lạ, ký tự điều khiển hoặc giá trị rất dài. Nếu nối trực tiếp chúng vào một log text, event có thể bị chia thành nhiều dòng hoặc gây nhiễu bộ phân tích. Hãy:
- Chỉ ghi field thật sự cần thiết và có nguồn tin cậy phù hợp.
- Validate cú pháp, chuẩn hóa và giới hạn độ dài.
- Dùng structured encoder có escaping đúng; không tự tạo JSON bằng nối chuỗi.
- Nếu ghi text, escape các ký tự xuống dòng, carriage return và dấu phân cách.
- Tránh log raw toàn bộ `X-Forwarded-For` chain hoặc User-Agent dài chỉ để tìm IP.

### 9.2. IPv4, IPv6, NAT và các định danh mạng

IP có thể là IPv4 hoặc IPv6. Một chuỗi header có thể chứa port, dấu ngoặc quanh địa chỉ, hoặc địa chỉ IPv6 có ký hiệu `:`. **Không tự tách bằng dấu phẩy/colon rồi coi là parser IP hoàn chỉnh**. Dùng parser/resolver được kiểm thử cho chuẩn và topology đang chạy.

Với NAT/VPN, một IP không xác định duy nhất một người. Với IPv6 privacy addresses, địa chỉ có thể thay đổi theo thời gian. Địa chỉ nội bộ/private hoặc proxy IP cũng có thể là thông tin nhạy cảm về hạ tầng. Chính sách retention và hiển thị nên xét cả hai họ địa chỉ.

### 9.3. Hệ thống có nhiều proxy

Một request qua CDN và load balancer có thể sinh nhiều hop metadata. Khai báo trusted proxy list và vị trí trust boundary ở đúng lớp hạ tầng; nếu dùng một chuỗi `X-Forwarded-For`, quyết định hop cần lấy phải theo chính sách chính thức của resolver, không dựa trên mẹo “lấy IP đầu tiên” không có điều kiện.

Nếu chỉ tin gateway A mà A tiếp nhận header không làm sạch từ client, gateway A **không tự động biến mọi phần tử trong header thành đáng tin**. Phải kiểm tra việc sanitize/overwrite/append thực tế ở từng hop.

### 9.4. Service identity và nguồn mạng có thể bất đồng

Nếu mTLS xác thực client `billing-service` nhưng TCP peer là proxy sidecar, audit có thể hợp lệ khi lưu:
- `actor_type=SERVICE`, `actor_id=billing-service` (từ workload identity được kiểm tra).
- `source_socket_peer` là sidecar/gateway quan sát được.
- `source_channel=SERVICE`.
- `source_client_ip` nếu resolver cung cấp bằng chứng đáng tin.

Không “sửa” source IP cho trùng actor hoặc nghĩ rằng hai giá trị khác nhau là lỗi. Chúng đo **những chiều khác nhau**.

## 10. Quyền riêng tư và tối thiểu hóa nguồn truy cập

Thông tin nguồn rất hữu ích để điều tra nhưng có thể đồng thời là **dữ liệu cá nhân hoặc dữ liệu hệ thống nhạy cảm**. IP, thiết bị, lịch sử truy cập tài nguyên, vị trí và correlation ID có thể được kết hợp để suy ra hoạt động một người.

Các nguyên tắc:
1. **Chỉ ghi dữ liệu cần để phục vụ mục đích audit cụ thể.** Không mặc định thu thập full header, geolocation, fingerprint hay token.
2. **Tách danh tính và thông tin mạng.** Actor ID có thể là ID nội bộ; tránh log tên thật/email nếu không cần.
3. **Giới hạn quyền xem audit log.** Người có quyền debug kỹ thuật không nhất thiết cần xem lịch sử truy cập tài nguyên nhạy cảm.
4. **Retention có hạn**, có chính sách xóa/ẩn danh và kiểm soát export/backup theo yêu cầu của tổ chức và pháp luật áp dụng.
5. **Bảo vệ đường truyền/lưu trữ**, audit truy cập vào chính audit store, kiểm tra dấu hiệu sửa/xóa bất thường.
6. **Không lưu raw credential**, cookie, JWT, API key, client secret hoặc signed URL để “xác minh nguồn”.
7. **Cẩn thận với pseudonymization.** Hash IP hoặc user ID đơn thuần có thể vẫn liên kết được hoạt động và không tự động biến nó thành dữ liệu vô danh. Khi cần giảm khả năng liên kết, thiết kế theo chính sách cụ thể.

Nếu cần lưu dữ liệu nguồn cho phòng chống gian lận, hãy nêu mục đích, thời gian giữ và nhóm được phép đọc. Không suy đoán tất cả audit log đều được phép giữ vô hạn chỉ vì phục vụ bảo mật.

## 11. Độ tin cậy của bản ghi: toàn vẹn và mất log

Nguồn được xác định đúng sẽ vô ích nếu event bị mất, bị chỉnh sửa hoặc không thể xác minh ai đã đọc bản ghi.

Một hệ thống audit nghiêm túc cần xem xét:
- **Ghi bền vững**: khi một transaction được commit nhưng process crash trước khi ghi audit, có thể mất bản ghi. Nếu audit bắt buộc, cân nhắc outbox/transactional event hoặc audit storage có đồng bộ phù hợp.
- **Tính toàn vẹn**: append-only/WORM, kiểm soát sửa/xóa, ký hoặc liên kết hash khi phù hợp, kiểm toán thao tác quản trị; chỉ hash không tự giải quyết quyền ghi.
- **Sắp xếp thời gian**: UTC timestamp có offset, đồng bộ clock, event ID/sequence cho từng stream, phân biệt occurred_at và recorded_at.
- **Ràng buộc latency**: async queue có thể drop khi đầy hoặc shutdown; theo dõi accepted/emitted/dropped, deadline flush.
- **Duplicate**: retry và failover có thể đưa một event vào nhiều sink; event ID giúp deduplicate downstream.
- **Nguồn quan sát**: nếu gateway và service cùng ghi audit, cần service/observer ID để biết bản ghi từ đâu; đừng coi hai bản ghi là hai lần truy cập riêng khi chúng mô tả cùng một request.

Không khẳng định logger.info trả về là “bản ghi đã lưu thành công”. Ý nghĩa của thành công phụ thuộc handler/appender, queue, collector và cơ chế acknowledgement.

## 12. Kiểm thử nguồn truy cập với tình huống tích cực và tiêu cực

Hãy kiểm tra cả giá trị đúng lẫn **các trường hợp giả mạo/bị thiếu**:

| Kịch bản | Kỳ vọng nguồn audit |
| --- | --- |
| Client truy cập trực tiếp không proxy | Client IP dựa vào peer quan sát, evidence=SOCKET_PEER |
| Client gửi `X-Forwarded-For` nhưng peer không phải trusted proxy | Header không được dùng để nâng client IP |
| Request qua proxy tin cậy đã chuẩn hóa header | Resolver lấy client IP theo topology; ghi evidence=TRUSTED_PROXY |
| Client cố đưa nhiều IP giả vào header | Thông tin giả không được biến thành client IP đáng tin |
| Có nhiều proxy đáng tin | Chọn đúng hop theo cấu hình; không dùng rule “phần tử đầu tiên” mù quáng |
| Service bị truy cập trực tiếp bỏ qua gateway | Không dùng forwarding claim như nguồn có chứng thực; có thể chặn request nếu policy yêu cầu |
| IPv6 hợp lệ | Parser và storage hỗ trợ đúng IPv6 |
| IP/header malformed hoặc quá dài | Fail closed theo trust policy; không ghi giá trị tùy ý như nguồn đã xác minh |
| Request không xác thực | actor=ANONYMOUS/unknown đúng schema; source vẫn có thể ghi bằng chứng |
| mTLS service-to-service | actor từ danh tính mTLS; địa chỉ peer lưu riêng |
| Job không qua HTTP | source channel=JOB, job/execution ID; không phát minh client IP |
| User-Agent giả | Không dùng nó làm bằng chứng định danh client |
| Logging queue đầy hoặc collector lỗi | Có telemetry/failure policy; không tuyên bố audit hoàn tất nếu bản ghi chưa được bảo đảm |
| User dữ liệu nhạy cảm trong URL | Không in toàn URL/query; dùng route template/resource ID được phép |

### Một quy trình kiểm thử end-to-end

1. Dựng staging có cùng topology proxy/gateway và phiên bản framework với production.
2. Sinh hai actor xác thực giả lập khác nhau và một anonymous request; tạo event cho ALLOW/DENY/ERROR.
3. Phát request trực tiếp cùng header forwarding tự khai để thử spoofing; xác minh audit vẫn dùng socket peer hoặc từ chối request.
4. Phát request qua proxy tin cậy, kiểm tra trusted client IP được lấy đúng theo resolver và được gắn evidence.
5. Kiểm tra event ở **đích cuối** (audit store/index), không chỉ trong console; đối chiếu event ID, actor, action, resource, outcome, request ID, source và thời gian.
6. Thử duplicate/retry, shutdown/queue overflow và trường hợp mất collector; quan sát error metrics và báo cáo thiếu event.
7. Kiểm tra không có Authorization token, cookie, password, raw query secret hay header giả mạo trong log.

Lưu bằng chứng kiểm thử theo loại request, topology và cấu hình đang dùng. Kết quả của một request thành công qua proxy A không chứng minh mọi đường ingress khác đều được xử lý an toàn.

## 13. Những lỗi phổ biến khi ghi nguồn truy cập

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Mọi request có cùng IP nội bộ | Java service chỉ thấy reverse proxy/gateway | Dùng trusted proxy resolver đúng topology; giữ peer riêng |
| Client đổi header là audit IP đổi theo | Ứng dụng tin raw `X-Forwarded-For` | Chỉ tin proxy được cấu hình, sanitize header ở ingress |
| Audit source IP trông hợp lý nhưng actor sai | Lấy username/userId từ payload thay vì security principal | Dùng identity đã xác thực |
| IP được dùng để chứng minh “ai” truy cập | Đồng nhất địa chỉ mạng với danh tính | Kết hợp actor, authn evidence, source và correlation |
| Không thấy nguồn cho job nền | Mặc định mọi event có HTTP request | Dùng job/service identity và source_channel phù hợp |
| Source của gateway và microservice khác nhau | Mỗi service quan sát một hop khác | Ghi observer/service ID và bằng chứng tại mỗi điểm |
| Địa chỉ IPv6 bị parse sai | Tự split header hoặc thiếu chuẩn hóa | Dùng parser hỗ trợ IPv6 và proxy chain |
| Header chứa dấu xuống dòng gây log giả | Log raw text không escape/truncate | Validate, giới hạn độ dài, dùng structured encoder |
| User-Agent được xem như thiết bị đã xác thực | Dữ liệu do client tự khai | Chỉ dùng như metadata không đáng tin nếu thật cần |
| Audit chứa bearer token/cookie | Log toàn bộ headers/request | Chọn allowlist, không đưa bí mật vào event |
| Audit cho phép nhưng thao tác vẫn lỗi | Nhầm authorization ALLOW với execution SUCCESS | Tách event quyết định và event hoàn tất |
| Không tìm đủ event sau crash | Async logging queue chưa flush hoặc collector lỗi | Chọn durability/ack phù hợp, đo loss và shutdown |
| Một thao tác có hai audit event | Gateway và service đều ghi, hoặc retry | Event ID và observer ID, mô hình dedup/correlation |

## 14. Bài tập và đáp án

**Bài 1 — Header giả mạo.** Service thấy socket peer `192.0.2.7`. Client gửi `X-Forwarded-For: 203.0.113.50`, nhưng peer không nằm trong trusted proxy set. Bạn nên ghi `source_client_ip` là gì?

**Đáp án:** nếu schema của bạn dùng fallback về peer, ghi `192.0.2.7` với `source_evidence=SOCKET_PEER`. Không ghi `203.0.113.50` như IP đáng tin. Nếu chính sách yêu cầu mọi request phải qua proxy, có thể từ chối đường truy cập đó và audit hành vi vi phạm.

**Bài 2 — Hai nguồn khác nhau.** Gateway log client IP `203.0.113.50`, service log peer `10.0.0.8`. Có nhất thiết một bên sai?

**Đáp án:** không. Gateway quan sát client gần ngoài biên; service quan sát gateway là socket peer. Để điều tra thống nhất, cần observer ID, trusted forwarding provenance và correlation ID.

**Bài 3 — Principal không xác thực.** Request chưa đăng nhập cố mở tài liệu, audit nên ghi `actor_id=request.getParameter("user")` hay `ANONYMOUS`?

**Đáp án:** `ANONYMOUS` hoặc dạng unknown theo schema. Tham số do client tự khai không phải danh tính đã xác thực.

**Bài 4 — Service-to-service.** Hệ thống xác thực `billing-service` qua mTLS. Có thể chỉ dùng IP để ghi “nguồn” không?

**Đáp án:** chưa đủ. Nên lưu verified service identity trong actor/client app field và địa chỉ peer riêng; IP có thể là sidecar/gateway, không thay thế xác thực mTLS.

**Bài 5 — Actor và outcome.** Khi kiểm tra quyền trả ALLOW nhưng truy vấn database thất bại, nên ghi `result=ALLOW` hay `SUCCESS`?

**Đáp án:** tùy loại event. Với `AUTHZ_DECISION`, `ALLOW` là đúng cho kết quả quyết định. Với `ACCESS_COMPLETED`, thao tác thực tế thất bại và cần result/error tương ứng. Dùng event type rõ ràng để không trộn hai nghĩa.

## 15. Checklist áp dụng trong hệ thống Java

Trước khi triển khai audit logging cho nguồn truy cập, xác nhận:

1. **Actor, source, target, observer** được định nghĩa và lưu ở các field khác nhau.
2. Actor lấy từ **security principal/workload identity đã xác thực**; anonymous request được mô tả trung thực.
3. Tầng socket peer và client address qua proxy **không bị nhầm lẫn**; có evidence/trust provenance.
4. `Forwarded`/`X-Forwarded-For` chỉ được xử lý bằng cấu hình trusted proxy và topology đã kiểm chứng; không tin raw header.
5. Parser hỗ trợ IPv4/IPv6, nhiều hop, header malformed, giới hạn độ dài và ranh giới ingress.
6. Source channel và client app identity xuất phát từ tín hiệu đáng tin; User-Agent tự khai không chứng minh danh tính.
7. Audit event có action, resource, outcome đúng nghĩa, event ID, request/trace ID và timestamp UTC phù hợp.
8. Không ghi token/password/cookie/raw request body/URL query bí mật; dữ liệu cá nhân được tối thiểu hóa theo policy.
9. Log injection được kiểm soát bằng validation/escaping/structured encoder chuẩn.
10. Audit store có quyền truy cập, retention, bảo vệ toàn vẹn, đo loss/duplicate và chính sách failover thích hợp.
11. Đã kiểm thử qua direct access, trusted/untrusted proxy, service-to-service, job, anonymous, async failure và recovery.
12. Người điều tra có thể đối chiếu bằng chứng nguồn với danh tính, thời gian, hành động và kết quả **mà không phải suy đoán**.

**Kết luận:** Nguồn truy cập trong audit logging là **tập bằng chứng về nơi và cách một hành động đi vào hệ thống**, không đơn thuần là một chuỗi IP. Trong Java, hãy kết hợp nguồn kết nối được quan sát, client address đã qua trusted resolver, actor đã xác thực, kênh truy cập và event metadata; ghi rõ độ tin cậy, tránh giả mạo forwarded headers và bảo vệ quyền riêng tư. Chỉ khi phân biệt được *điều đã quan sát*, *điều đã xác minh* và *điều do client tự khai*, audit log mới hữu ích cho truy vết và điều tra.